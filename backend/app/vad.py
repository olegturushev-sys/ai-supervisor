from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class VadSegment:
    start_s: float
    end_s: float


def segment_wav_energy_vad(
    wav_path: str,
    *,
    sample_rate: int = 16000,
    frame_ms: int = 30,
    padding_ms: int = 300,
    min_segment_ms: int = 250,
    max_segment_s: float = 30.0,
    threshold: float | None = None,
    threshold_scale: float = 1.0,
    boundary_padding_s: float = 0.0,
) -> List[VadSegment]:
    """
    Simple local VAD segmentation based on frame energy (RMS).
    Requires 16kHz mono WAV (we rely on the backend ffmpeg step to produce this).
    """
    import numpy as np  # type: ignore
    import soundfile as sf  # type: ignore

    audio, sr = sf.read(wav_path, dtype="int16", always_2d=True)
    if sr != sample_rate:
        raise RuntimeError(f"VAD expects {sample_rate}Hz wav, got {sr}Hz")
    mono = audio.mean(axis=1).astype(np.int16)
    padding_frames = max(1, int(padding_ms / frame_ms))
    min_frames = max(1, int(min_segment_ms / frame_ms))

    frame_len_samples = int(sample_rate * frame_ms / 1000)

    def frame_time_s(frame_index: int) -> float:
        return (frame_index * frame_len_samples) / float(sample_rate)

    # Frame RMS (0..1 roughly)
    x = (mono.astype(np.float32) / 32768.0).clip(-1.0, 1.0)
    total_frames = max(1, len(x) // frame_len_samples)
    rms = []
    for i in range(total_frames):
        a = i * frame_len_samples
        b = a + frame_len_samples
        frame = x[a:b]
        if frame.size == 0:
            continue
        rms.append(float(np.sqrt(np.mean(frame * frame) + 1e-12)))

    if not rms:
        return []

    if threshold is None:
        med = float(np.median(rms))
        p90 = float(np.percentile(rms, 90))
        threshold = max(0.0035, med + 0.4 * max(0.0, p90 - med))
    threshold = float(threshold) * max(0.3, min(1.5, float(threshold_scale)))

    decisions: List[bool] = [v > float(threshold) for v in rms]

    if not decisions:
        # empty/too short audio
        return []

    segments: List[Tuple[int, int]] = []
    triggered = False
    start_idx = 0
    ring: List[bool] = []

    for i, is_voiced in enumerate(decisions):
        ring.append(is_voiced)
        if len(ring) > padding_frames:
            ring.pop(0)

        if not triggered:
            voiced_count = sum(1 for x in ring if x)
            if voiced_count > 0.9 * len(ring):
                triggered = True
                start_idx = max(0, i - len(ring))
                ring.clear()
        else:
            unvoiced_count = sum(1 for x in ring if not x)
            if unvoiced_count > 0.9 * len(ring):
                end_idx = i
                segments.append((start_idx, end_idx))
                triggered = False
                ring.clear()

    if triggered:
        segments.append((start_idx, len(decisions)))

    total_dur_s = frame_time_s(len(decisions)) - frame_time_s(0)
    pad_s = max(0.0, min(2.0, float(boundary_padding_s)))

    out: List[VadSegment] = []
    for s_idx, e_idx in segments:
        if (e_idx - s_idx) < min_frames:
            continue
        start_s = max(0.0, frame_time_s(s_idx) - pad_s)
        end_s = min(total_dur_s, frame_time_s(e_idx) + pad_s)
        if end_s <= start_s:
            continue

        dur = end_s - start_s
        if dur <= max_segment_s:
            out.append(VadSegment(start_s=start_s, end_s=end_s))
        else:
            parts = max(1, int(math.ceil(dur / max_segment_s)))
            step = dur / parts
            for p in range(parts):
                ps = start_s + p * step
                pe = min(end_s, ps + step)
                if (pe - ps) >= (min_segment_ms / 1000.0):
                    out.append(VadSegment(start_s=ps, end_s=pe))

    return out

