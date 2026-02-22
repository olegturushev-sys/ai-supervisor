from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class DiarizationConfig:
    device: str = "cpu"
    default_speakers: int = 2
    min_segment_s: float = 0.8
    max_segment_s: float = 8.0  # 0 = no split; >0 = split segments longer than this into subsegments
    subsegment_duration_s: float = 2.5  # used when splitting long segments
    min_rms: float = 0.0  # 0 = disabled; >0 = filter segments with RMS below this
    embedding_model: str = "speechbrain/spkrec-ecapa-voxceleb"
    batch_size: int = 8
    clustering: str = "agglomerative"  # agglomerative|spectral|refined
    smooth_labels: bool = True  # post-process: merge adjacent same-speaker, fix short islands
    rms_normalize: bool = True  # normalize per-segment RMS before encoding
    therapy_mode: bool = True  # always 2 speakers: client (more utterances) and therapist (fewer)
    client_label: str = "Клиент"
    therapist_label: str = "Терапевт"


_ENCODER_CACHE: dict[tuple[str, str], Any] = {}
_ENCODER_CACHE_LOCK = None  # lazy-created to avoid importing threading unless needed


def _rms_normalize(chunk: Any, *, target_rms: float = 0.05) -> Any:
    import numpy as np  # type: ignore

    x = np.asarray(chunk, dtype=np.float32)
    if x.size == 0:
        return x
    rms = float(np.sqrt(np.mean(x * x)) + 1e-12)
    if rms < 1e-12:
        return x
    return (x * (target_rms / rms)).astype(np.float32, copy=False)


def _linear_resample(x, sr_in: int, sr_out: int):
    import numpy as np  # type: ignore

    if sr_in == sr_out:
        return x
    if x.size == 0:
        return x
    ratio = float(sr_out) / float(sr_in)
    n_out = max(1, int(round(x.shape[0] * ratio)))
    t_in = np.linspace(0.0, 1.0, num=x.shape[0], endpoint=False, dtype=np.float64)
    t_out = np.linspace(0.0, 1.0, num=n_out, endpoint=False, dtype=np.float64)
    return np.interp(t_out, t_in, x).astype(x.dtype, copy=False)


def _get_encoder(*, embedding_model: str, device: str):
    global _ENCODER_CACHE_LOCK
    if _ENCODER_CACHE_LOCK is None:
        import threading

        _ENCODER_CACHE_LOCK = threading.Lock()

    key = (embedding_model, device)
    with _ENCODER_CACHE_LOCK:
        enc = _ENCODER_CACHE.get(key)
        if enc is not None:
            return enc

        from speechbrain.inference.speaker import EncoderClassifier  # type: ignore

        enc = EncoderClassifier.from_hparams(
            source=embedding_model,
            run_opts={"device": device},
        )
        _ENCODER_CACHE[key] = enc
        return enc


def _encode_embeddings(encoder: Any, chunks: list[Any], *, device: str) -> list[Any]:
    import numpy as np  # type: ignore
    import torch  # type: ignore

    if not chunks:
        return []

    lens = [int(c.shape[0]) for c in chunks]
    max_len = max(lens) if lens else 0
    if max_len <= 0:
        return []

    batch = torch.zeros((len(chunks), max_len), dtype=torch.float32, device=device)
    for i, c in enumerate(chunks):
        n = int(c.shape[0])
        if n <= 0:
            continue
        batch[i, :n] = torch.from_numpy(np.asarray(c, dtype=np.float32)).to(device)

    wav_lens = torch.tensor(lens, dtype=torch.float32, device=device) / float(max_len)
    with torch.no_grad():
        emb_t = encoder.encode_batch(batch, wav_lens)

    # SpeechBrain often returns [B, 1, D]
    if hasattr(emb_t, "ndim") and emb_t.ndim == 3:
        emb_t = emb_t[:, 0, :]
    emb = emb_t.detach().cpu().numpy()
    return [emb[i] for i in range(emb.shape[0])]


def _smooth_speaker_labels(segments: list[dict[str, Any]], *, min_island_s: float = 0.5) -> None:
    """
    Post-process: fix short speaker "islands" by reassigning to neighbor majority.
    Segments must be sorted by start.
    """
    if not segments or min_island_s <= 0:
        return
    n = len(segments)
    for i in range(n):
        seg = segments[i]
        dur = float(seg.get("end") or 0) - float(seg.get("start") or 0)
        if dur >= min_island_s:
            continue
        spk = seg.get("speaker")
        if not spk:
            continue
        # Collect neighbors' speakers
        neighbors: list[str] = []
        if i > 0 and segments[i - 1].get("speaker"):
            neighbors.append(segments[i - 1]["speaker"])
        if i < n - 1 and segments[i + 1].get("speaker"):
            neighbors.append(segments[i + 1]["speaker"])
        if not neighbors:
            continue
        best = Counter(neighbors).most_common(1)[0][0]
        if best != spk:
            seg["speaker"] = best


def diarize_segments_speechbrain(
    wav_path: str,
    segments: list[dict[str, Any]],
    *,
    cfg: DiarizationConfig,
    num_speakers: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Local diarization using SpeechBrain ECAPA-TDNN:
    - Energy/VAD-provided transcript segments
    - SpeechBrain speaker embeddings
    - sklearn clustering

    Returns the same segments with `speaker` labels added when possible.
    """
    # Lazy imports (optional dependency).
    import numpy as np  # type: ignore
    import soundfile as sf  # type: ignore
    import torch  # type: ignore

    try:
        # speechbrain v1+ typically exposes this path
        from speechbrain.inference.speaker import EncoderClassifier  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Local diarization requires 'speechbrain'. Install it and retry."
        ) from e

    try:
        from sklearn.cluster import AgglomerativeClustering  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Local diarization requires 'scikit-learn'. Install it and retry."
        ) from e

    wav, sr = sf.read(wav_path, dtype="float32", always_2d=False)
    if hasattr(wav, "ndim") and wav.ndim == 2:
        wav = wav.mean(axis=1)
    wav = np.asarray(wav, dtype=np.float32)
    if sr != 16000:
        wav = _linear_resample(wav, int(sr), 16000)
        sr = 16000

    if not segments:
        return segments

    # Build embeddings per transcript segment (cached encoder + micro-batching).
    encoder = _get_encoder(embedding_model=cfg.embedding_model, device=cfg.device)

    emb_list: list[np.ndarray] = []
    seg_map: list[int] = []

    pending_chunks: list[np.ndarray] = []
    pending_seg_idx: list[int] = []

    def _flush_pending() -> None:
        nonlocal pending_chunks, pending_seg_idx, emb_list, seg_map
        if not pending_chunks:
            return
        embs = _encode_embeddings(encoder, pending_chunks, device=cfg.device)
        for e, si in zip(embs, pending_seg_idx):
            if e is None:
                continue
            e = np.asarray(e, dtype=np.float32)
            if e.ndim != 1 or e.size == 0:
                continue
            emb_list.append(e)
            seg_map.append(si)
        pending_chunks = []
        pending_seg_idx = []

    bs = max(1, int(getattr(cfg, "batch_size", 8) or 8))
    max_seg = float(getattr(cfg, "max_segment_s", 0) or 0)
    sub_dur = float(getattr(cfg, "subsegment_duration_s", 2.5) or 2.5)
    min_rms = float(getattr(cfg, "min_rms", 0) or 0)
    rms_norm = bool(getattr(cfg, "rms_normalize", True))

    def _add_chunk(chunk: np.ndarray, seg_idx: int) -> None:
        if chunk.size == 0:
            return
        if min_rms > 0:
            rms = float(np.sqrt(np.mean(chunk * chunk)) + 1e-12)
            if rms < min_rms:
                return
        if rms_norm:
            chunk = _rms_normalize(chunk)
        pending_chunks.append(np.asarray(chunk, dtype=np.float32))
        pending_seg_idx.append(seg_idx)
        if len(pending_chunks) >= bs:
            _flush_pending()

    for idx, seg in enumerate(segments):
        try:
            start = float(seg.get("start") or 0.0)
            end = float(seg.get("end") or start)
        except Exception:
            continue
        if end <= start:
            continue
        dur = end - start
        if dur < cfg.min_segment_s:
            continue

        if max_seg > 0 and dur > max_seg:
            # Split long segment into subsegments
            t = start
            while t < end:
                t_end = min(t + sub_dur, end)
                s0 = int(t * sr)
                s1 = int(t_end * sr)
                s0 = max(0, min(s0, wav.shape[0]))
                s1 = max(0, min(s1, wav.shape[0]))
                chunk = wav[s0:s1]
                _add_chunk(chunk, idx)
                t = t_end
        else:
            s0 = int(start * sr)
            s1 = int(end * sr)
            s0 = max(0, min(s0, wav.shape[0]))
            s1 = max(0, min(s1, wav.shape[0]))
            chunk = wav[s0:s1]
            _add_chunk(chunk, idx)

    _flush_pending()

    if not emb_list:
        return segments

    X = np.vstack(emb_list).astype(np.float32, copy=False)
    n = np.linalg.norm(X, axis=1, keepdims=True) + 1e-12
    Xn = X / n

    therapy_mode = bool(getattr(cfg, "therapy_mode", False))
    k = num_speakers
    if therapy_mode:
        k = 2
    elif k is None:
        k = int(cfg.default_speakers)
    k = max(1, min(int(k), Xn.shape[0]))

    clustering_mode = (getattr(cfg, "clustering", "agglomerative") or "agglomerative").strip().lower()

    if k == 1:
        labels = np.zeros((Xn.shape[0],), dtype=np.int32)
    elif clustering_mode == "spectral":
        from sklearn.cluster import SpectralClustering  # type: ignore

        clusterer = SpectralClustering(
            n_clusters=k,
            affinity="nearest_neighbors",
            n_neighbors=min(10, Xn.shape[0] - 1) if Xn.shape[0] > 1 else 1,
            random_state=42,
        )
        labels = clusterer.fit_predict(Xn).astype(np.int32, copy=False)
    elif clustering_mode == "refined":
        try:
            clusterer = AgglomerativeClustering(
                n_clusters=k,
                metric="cosine",
                linkage="average",
            )
        except TypeError:
            clusterer = AgglomerativeClustering(
                n_clusters=k,
                affinity="cosine",  # type: ignore[call-arg]
                linkage="average",
            )
        labels = clusterer.fit_predict(Xn).astype(np.int32, copy=False)
        # Refinement: recompute centroids, reassign by nearest
        for _ in range(2):
            centroids = np.zeros((k, Xn.shape[1]), dtype=np.float32)
            counts = np.zeros(k, dtype=np.int32)
            for i, lbl in enumerate(labels):
                centroids[lbl] += Xn[i]
                counts[lbl] += 1
            for j in range(k):
                if counts[j] > 0:
                    centroids[j] /= counts[j]
                    nrm = np.linalg.norm(centroids[j]) + 1e-12
                    centroids[j] /= nrm
            for i in range(Xn.shape[0]):
                best_j = 0
                best_sim = -2.0
                for j in range(k):
                    if counts[j] == 0:
                        continue
                    sim = float(np.dot(Xn[i], centroids[j]))
                    if sim > best_sim:
                        best_sim = sim
                        best_j = j
                labels[i] = best_j
    else:
        try:
            clusterer = AgglomerativeClustering(
                n_clusters=k,
                metric="cosine",
                linkage="average",
            )
        except TypeError:
            clusterer = AgglomerativeClustering(
                n_clusters=k,
                affinity="cosine",  # type: ignore[call-arg]
                linkage="average",
            )
        labels = clusterer.fit_predict(Xn).astype(np.int32, copy=False)

    # Majority vote for segments that were split into multiple embeddings
    seg_labels: dict[int, list[int]] = defaultdict(list)
    for i, seg_idx in enumerate(seg_map):
        seg_labels[seg_idx].append(int(labels[i]))

    for seg_idx, lbls in seg_labels.items():
        best = Counter(lbls).most_common(1)[0][0]
        segments[seg_idx]["speaker"] = f"SPEAKER_{best + 1}"

    # Therapy mode: relabel to client (more utterances) / therapist (fewer)
    if therapy_mode:
        counts = Counter(seg.get("speaker") for seg in segments if seg.get("speaker"))
        if len(counts) >= 2:
            sorted_spk = sorted(counts.keys(), key=lambda s: -counts[s])
            more_spk, less_spk = sorted_spk[0], sorted_spk[1]
            client_lbl = str(getattr(cfg, "client_label", "Клиент") or "Клиент")
            therapist_lbl = str(getattr(cfg, "therapist_label", "Терапевт") or "Терапевт")
            mapping = {more_spk: client_lbl, less_spk: therapist_lbl}
            for seg in segments:
                if seg.get("speaker") in mapping:
                    seg["speaker"] = mapping[seg["speaker"]]

    if getattr(cfg, "smooth_labels", True):
        _smooth_speaker_labels(segments, min_island_s=0.5)

    return segments

