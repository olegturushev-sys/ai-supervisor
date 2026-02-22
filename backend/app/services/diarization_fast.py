"""
Fast CPU diarization: Silero VAD + ECAPA-TDNN + Mean Shift.

Uses L2-normalized embeddings and Mean Shift with Euclidean (equivalent to cosine
on unit vectors). Maps to client/therapist by total duration.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)


def _load_wav_float32(
    wav_path_or_audio: Union[str, tuple[Any, int]],
) -> tuple[Any, int]:
    """Load or accept (wav_float32, sr). Returns (wav_float32_mono, sr)."""
    import numpy as np  # type: ignore
    import soundfile as sf  # type: ignore

    if isinstance(wav_path_or_audio, (list, tuple)) and len(wav_path_or_audio) == 2:
        wav = np.asarray(wav_path_or_audio[0], dtype=np.float32)
        sr = int(wav_path_or_audio[1])
    else:
        wav, sr = sf.read(str(wav_path_or_audio), dtype="float32", always_2d=False)
    if hasattr(wav, "ndim") and wav.ndim == 2:
        wav = wav.mean(axis=1)
    return np.asarray(wav, dtype=np.float32), int(sr)

_VAD_CACHE: dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class DiarizationFastConfig:
    """Configuration for fast CPU diarization."""

    device: str = "auto"  # auto = mps if available else cpu
    embedding_model: str = "speechbrain/spkrec-ecapa-voxceleb"
    vad_threshold: float = 0.5
    min_speech_duration_ms: int = 250
    min_silence_duration_ms: int = 100
    mean_shift_bandwidth: float = 0.4
    min_segment_s: float = 0.5
    batch_size: int = 8
    therapy_mode: bool = True
    client_label: str = "Клиент"
    therapist_label: str = "Терапевт"


def _resolve_device(prefer_mps: bool = True) -> str:
    """Resolve device: mps if available on macOS, else cpu."""
    try:
        import torch  # type: ignore

        if prefer_mps and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _load_silero_vad(device: str) -> Any:
    """Lazy load Silero VAD via torch.hub."""
    with _CACHE_LOCK:
        if device in _VAD_CACHE:
            return _VAD_CACHE[device]
    try:
        import torch  # type: ignore

        t0 = time.perf_counter()
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
            trust_repo=True,
        )
        get_speech_timestamps = utils[0]
        with _CACHE_LOCK:
            _VAD_CACHE[device] = (model, get_speech_timestamps)
        logger.info("Silero VAD loaded in %.2fs", time.perf_counter() - t0)
        return (model, get_speech_timestamps)
    except Exception as e:
        logger.exception("Failed to load Silero VAD: %s", e)
        raise RuntimeError(f"Silero VAD load failed: {e}") from e


def _get_speech_segments(
    wav: Any,
    sr: int,
    vad: tuple[Any, Any],
    *,
    threshold: float = 0.5,
    min_speech_duration_ms: int = 250,
    min_silence_duration_ms: int = 100,
) -> list[tuple[float, float]]:
    """Get speech segments (start_s, end_s) from WAV using Silero VAD."""
    import numpy as np  # type: ignore

    model, get_speech_timestamps = vad
    if hasattr(wav, "numpy"):
        wav_np = wav.numpy()
    else:
        wav_np = np.asarray(wav, dtype=np.float32)
    if wav_np.ndim == 2:
        wav_np = wav_np.mean(axis=1)
    if wav_np.dtype != np.float32:
        wav_np = wav_np.astype(np.float32)
    torch_wav = None
    try:
        import torch  # type: ignore

        torch_wav = torch.from_numpy(wav_np)
    except Exception:
        torch_wav = wav_np  # fallback if already tensor

    timestamps = get_speech_timestamps(
        torch_wav,
        model=model,
        sampling_rate=sr,
        threshold=threshold,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
    )
    if not timestamps:
        return []
    return [(t["start"] / sr, t["end"] / sr) for t in timestamps]


def _get_ecapa_encoder(embedding_model: str, device: str) -> Any:
    """Get or create cached ECAPA-TDNN encoder (delegates to shared embedding_cache)."""
    from ..embedding_cache import get_ecapa_encoder
    return get_ecapa_encoder(embedding_model, device)


def _linear_resample(x: Any, sr_in: int, sr_out: int) -> Any:
    import numpy as np  # type: ignore

    if sr_in == sr_out:
        return x
    x = np.asarray(x, dtype=np.float32)
    if x.size == 0:
        return x
    ratio = float(sr_out) / float(sr_in)
    n_out = max(1, int(round(x.shape[0] * ratio)))
    t_in = np.linspace(0.0, 1.0, num=x.shape[0], endpoint=False, dtype=np.float64)
    t_out = np.linspace(0.0, 1.0, num=n_out, endpoint=False, dtype=np.float64)
    return np.interp(t_out, t_in, x).astype(np.float32, copy=False)


def _encode_batch(encoder: Any, chunks: list[Any], device: str) -> list[Any]:
    import numpy as np  # type: ignore
    import torch  # type: ignore

    if not chunks:
        return []
    lens = [int(c.shape[0]) for c in chunks]
    max_len = max(lens)
    if max_len <= 0:
        return []

    batch = torch.zeros((len(chunks), max_len), dtype=torch.float32, device=device)
    for i, c in enumerate(chunks):
        n = int(c.shape[0])
        if n > 0:
            batch[i, :n] = torch.from_numpy(np.asarray(c, dtype=np.float32)).to(device)

    wav_lens = torch.tensor(lens, dtype=torch.float32, device=device) / float(max_len)
    with torch.no_grad():
        emb_t = encoder.encode_batch(batch, wav_lens)
    if hasattr(emb_t, "ndim") and emb_t.ndim == 3:
        emb_t = emb_t[:, 0, :]
    emb = emb_t.detach().cpu().numpy()
    return [emb[i] for i in range(emb.shape[0])]


def _mean_shift_cosine(X: Any, bandwidth: float) -> Any:
    """Mean Shift on L2-normalized embeddings (Euclidean on unit vectors ~ cosine)."""
    import numpy as np  # type: ignore

    from sklearn.cluster import MeanShift  # type: ignore

    X = np.asarray(X, dtype=np.float32)
    n = np.linalg.norm(X, axis=1, keepdims=True) + 1e-12
    Xn = X / n
    clusterer = MeanShift(bandwidth=bandwidth, cluster_all=True)
    return clusterer.fit_predict(Xn).astype(np.int32, copy=False)


def _cluster_n_speakers(X: Any, n: int) -> Any:
    """Agglomerative clustering for fixed n speakers (therapy mode: exactly 2 clusters). Ward minimizes within-cluster variance for balanced splits."""
    import numpy as np  # type: ignore

    from sklearn.cluster import AgglomerativeClustering  # type: ignore

    X = np.asarray(X, dtype=np.float32)
    xn = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)
    cl = AgglomerativeClustering(n_clusters=n, linkage="ward", metric="euclidean")
    return cl.fit_predict(xn).astype(np.int32, copy=False)


def _map_to_roles(
    labels: list[int],
    durations: list[float],
    *,
    client_label: str = "Клиент",
    therapist_label: str = "Терапевт",
) -> dict[int, str]:
    """Map cluster ids to client (more total duration) / therapist (fewer)."""
    from collections import defaultdict

    total: dict[int, float] = defaultdict(float)
    for lbl, dur in zip(labels, durations):
        total[lbl] += dur
    if len(total) < 2:
        return {k: client_label for k in total}
    sorted_clusters = sorted(total.keys(), key=lambda c: -total[c])
    return {
        sorted_clusters[0]: client_label,
        sorted_clusters[1]: therapist_label,
    }


def diarize_segments_by_embedding(
    wav_path_or_audio: Union[str, tuple[Any, int]],
    segments: list[dict[str, Any]],
    cfg: DiarizationFastConfig,
) -> list[dict[str, Any]]:
    """
    Therapy-mode path: encode each transcript segment, cluster into 2, assign speaker directly.
    Avoids Silero VAD / overlap mapping and gives balanced Client/Therapist labels.
    """
    import numpy as np  # type: ignore

    if len(segments) < 2:
        return segments

    device = cfg.device
    if device in ("auto", "mps"):
        device = _resolve_device()
    if device == "mps":
        try:
            import torch  # type: ignore
            if not (getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()):
                device = "cpu"
        except Exception:
            device = "cpu"

    wav, sr = _load_wav_float32(wav_path_or_audio)
    if sr != 16000:
        wav = _linear_resample(wav, int(sr), 16000)
        sr = 16000

    encoder = _get_ecapa_encoder(cfg.embedding_model, device)
    batch_size = max(1, min(int(cfg.batch_size), 64))
    emb_list: list[Any] = []
    durations: list[float] = []

    for i in range(0, len(segments), batch_size):
        batch_segs = segments[i : i + batch_size]
        chunks = []
        for seg in batch_segs:
            start = float(seg.get("start") or 0)
            end = float(seg.get("end") or start)
            dur = max(0, end - start)
            durations.append(dur)
            s0 = max(0, min(int(start * sr), wav.shape[0]))
            s1 = max(0, min(int(end * sr), wav.shape[0]))
            if s1 <= s0:
                s1 = min(wav.shape[0], s0 + int(sr * 0.1))
            chunks.append(wav[s0:s1])
        embs = _encode_batch(encoder, chunks, device)
        emb_list.extend(embs)

    X = np.vstack(emb_list).astype(np.float32, copy=False)
    labels = _cluster_n_speakers(X, 2)
    role_map = _map_to_roles(
        labels.tolist(),
        durations,
        client_label=cfg.client_label,
        therapist_label=cfg.therapist_label,
    )

    result = list(segments)
    for idx, lbl in enumerate(labels.tolist()):
        if idx < len(result):
            result[idx]["speaker"] = role_map.get(lbl, cfg.client_label)

    logger.info("Segment-based diarization: %d segments, 2 clusters", len(result))
    return result


def diarize_audio_fast(
    wav_path_or_audio: Union[str, tuple[Any, int]],
    cfg: DiarizationFastConfig,
    *,
    num_speakers: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Fast diarization: Silero VAD -> ECAPA embeddings -> Mean Shift -> role mapping.

    Returns list of dicts with start, end, speaker.
    """
    import numpy as np  # type: ignore

    device = cfg.device
    if device in ("auto", "mps"):
        device = _resolve_device()
    if device == "mps":
        try:
            import torch  # type: ignore

            if not (getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()):
                device = "cpu"
        except Exception:
            device = "cpu"

    t_total = time.perf_counter()

    wav, sr = _load_wav_float32(wav_path_or_audio)
    if sr != 16000:
        wav = _linear_resample(wav, int(sr), 16000)
        sr = 16000

    vad = _load_silero_vad(device)
    segments_sec = _get_speech_segments(
        wav,
        sr,
        vad,
        threshold=cfg.vad_threshold,
        min_speech_duration_ms=cfg.min_speech_duration_ms,
        min_silence_duration_ms=cfg.min_silence_duration_ms,
    )

    segments_sec = [(s, e) for s, e in segments_sec if e - s >= cfg.min_segment_s]
    logger.info("Silero VAD: %d speech segments", len(segments_sec))
    if not segments_sec:
        return []

    encoder = _get_ecapa_encoder(cfg.embedding_model, device)
    emb_list: list[Any] = []
    durations: list[float] = []

    batch_size = max(1, min(int(cfg.batch_size), 64))
    for i in range(0, len(segments_sec), batch_size):
        batch = segments_sec[i : i + batch_size]
        chunks = []
        for s, e in batch:
            s0 = max(0, min(int(s * sr), wav.shape[0]))
            s1 = max(0, min(int(e * sr), wav.shape[0]))
            chunks.append(wav[s0:s1])
            durations.append(e - s)
        embs = _encode_batch(encoder, chunks, device)
        emb_list.extend(embs)

    X = np.vstack(emb_list).astype(np.float32, copy=False)
    n_speakers_target = 2 if cfg.therapy_mode else max(2, int(num_speakers or 2))
    if cfg.therapy_mode:
        labels = _cluster_n_speakers(X, n_speakers_target)
    else:
        labels = _mean_shift_cosine(X, cfg.mean_shift_bandwidth)
    n_clusters = len(set(labels.tolist()))
    logger.info("Mean Shift: %d clusters", n_clusters)

    if cfg.therapy_mode and n_clusters > 2:
        from collections import Counter
        cnt = Counter(labels.tolist())
        top2 = [c for c, _ in cnt.most_common(2)]
        remap = {lab: (top2[0] if lab == top2[0] else top2[1]) for lab in labels}
        labels = np.array([remap[l] for l in labels], dtype=np.int32)

    role_map = _map_to_roles(
        labels.tolist(),
        durations,
        client_label=cfg.client_label,
        therapist_label=cfg.therapist_label,
    )

    result: list[dict[str, Any]] = []
    for (s, e), lbl in zip(segments_sec, labels.tolist()):
        result.append({
            "start": s,
            "end": e,
            "speaker": role_map.get(lbl, f"SPEAKER_{lbl + 1}"),
        })

    logger.info("Fast diarization done in %.2fs, %d segments", time.perf_counter() - t_total, len(result))
    return result
