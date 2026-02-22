"""
Diarization factory: returns the appropriate diarization function by engine name.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _assign_speaker_to_segment(
    seg_start: float,
    seg_end: float,
    diar_segments: list[dict[str, Any]],
) -> Optional[str]:
    """Assign speaker to segment by maximal overlap with diarization segments."""
    best_speaker: Optional[str] = None
    best_overlap = 0.0
    seg_mid = (seg_start + seg_end) / 2
    for d in diar_segments:
        ds, de = d.get("start", 0), d.get("end", 0)
        overlap = max(0, min(seg_end, de) - max(seg_start, ds))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = d.get("speaker")
        if overlap > 0 and best_speaker and best_overlap >= (seg_end - seg_start) * 0.5:
            break
    if best_overlap <= 0 and diar_segments:
        for d in diar_segments:
            ds, de = d.get("start", 0), d.get("end", 0)
            if ds <= seg_mid <= de:
                return d.get("speaker")
        nearest = min(diar_segments, key=lambda d: min(abs(d["start"] - seg_end), abs(d["end"] - seg_start)))
        return nearest.get("speaker")
    return best_speaker


def diarize_audio_fast_wrapper(
    wav_path: str,
    segments: list[dict[str, Any]],
    *,
    cfg: Any,
    num_speakers: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Wrapper: runs fast diarization (Silero VAD + ECAPA + Mean Shift) and maps
    results to transcript segments by temporal overlap.
    """
    from .diarization_fast import DiarizationFastConfig, diarize_audio_fast, diarize_segments_by_embedding

    if not isinstance(cfg, DiarizationFastConfig):
        fast_cfg = DiarizationFastConfig(
            device=getattr(cfg, "device", "auto"),
            embedding_model=str(getattr(cfg, "embedding_model", "speechbrain/spkrec-ecapa-voxceleb")),
            vad_threshold=float(getattr(cfg, "vad_threshold", 0.5)),
            min_speech_duration_ms=int(getattr(cfg, "min_speech_duration_ms", 250)),
            min_silence_duration_ms=int(getattr(cfg, "min_silence_duration_ms", 100)),
            mean_shift_bandwidth=float(getattr(cfg, "mean_shift_bandwidth", 0.4)),
            min_segment_s=float(getattr(cfg, "min_segment_s", 0.5)),
            batch_size=int(getattr(cfg, "batch_size", 8)),
            therapy_mode=bool(getattr(cfg, "therapy_mode", True)),
            client_label=str(getattr(cfg, "client_label", "Клиент") or "Клиент"),
            therapist_label=str(getattr(cfg, "therapist_label", "Терапевт") or "Терапевт"),
        )
    else:
        fast_cfg = cfg

    if fast_cfg.therapy_mode and len(segments) >= 2:
        result = diarize_segments_by_embedding(wav_path, list(segments), fast_cfg)
    else:
        diar_segments = diarize_audio_fast(wav_path, fast_cfg, num_speakers=num_speakers)
        if not diar_segments:
            logger.warning("Fast diarization produced no segments")
            return segments
        result = list(segments)
        for seg in result:
            start = float(seg.get("start") or 0)
            end = float(seg.get("end") or start)
            spk = _assign_speaker_to_segment(start, end, diar_segments)
            if spk:
                seg["speaker"] = spk

    logger.info(
        "Fast diarization wrapper: %d/%d segments labeled",
        sum(1 for s in result if s.get("speaker")),
        len(result),
    )
    return result


def get_diarization_function(engine: str) -> Callable[..., list[dict[str, Any]]]:
    """
    Return diarization function for the given engine.

    - local: diarize_segments_speechbrain (uses transcript segments + ECAPA + clustering)
    - fast: diarize_audio_fast_wrapper (Silero VAD + ECAPA + Mean Shift, maps to segments)
    """
    if engine == "local":
        from ..diarization_local import diarize_segments_speechbrain

        return diarize_segments_speechbrain
    if engine == "fast":
        return diarize_audio_fast_wrapper
    raise ValueError(f"Unknown diarization engine: {engine}")
