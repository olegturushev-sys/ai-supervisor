# Autoresearch Worklog

## Session: Transcription Speed Optimization (2026-03-18)

### Run 1: Baseline — transcription_time=13.098s
- What changed: Initial baseline measurement
- Result: 13.098s, RTF=0.2183, 16 segments
- Status: keep

### Run 2: SEGMENT_CONCURRENCY=16 — transcription_time=12.998s (-0.76%)
- What changed: SEGMENT_CONCURRENCY from 8 to 16
- Result: 12.998s, RTF=0.2166
- Status: keep

### Run 3: Thread optimization — transcription_time=12.998s (no change)
- What changed: Added OMP_NUM_THREADS=8, MKL_NUM_THREADS=8
- Result: 12.998s (no improvement)
- Status: keep

### Run 4: VAD thresholds — transcription_time=10.518s (-19.7%) **BEST**
- What changed: MIN_SPEECH_MS=400, MIN_SILENCE_MS=200
- Result: 10.518s, RTF=0.1753
- Status: **keep (BEST)**

### Run 5-13: Additional experiments (all worse than Run 4)
- MIN_SPEECH_MS=350/150: 13.466s (worse)
- MAX_SEGMENT_S=5: 12.601s (worse)
- MIN_SEGMENT_S=1.5: 12.992s (worse)
- SUBSEGMENT_S=4: 13.067s (worse)
- SUBSEGMENT_S=2: 10.637s (close, but worse)
- SMOOTH_LABELS=0, RMS_NORMALIZE=0: 13.180s (worse)
- MIN_SPEECH_MS=450/180: 12.788s (worse)
- MIN_SPEECH_MS=380/180: 11.133s (worse)
- SUBSEGMENT_S=3: 13.599s (worse)

## Key Insights

1. **VAD thresholds are crucial**: MIN_SPEECH_MS=400, MIN_SILENCE_MS=200 reduces time by 19.7%
2. SEGMENT_CONCURRENCY=16 provides marginal improvement
3. Thread settings don't significantly impact this workload
4. The optimal settings are in a narrow range around MIN_SPEECH_MS=400, MIN_SILENCE_MS=200
5. Smoothing and RMS normalization are important (disable makes it worse)

## Final Optimal Settings

```env
SEGMENT_CONCURRENCY=16
DIARIZATION_FAST_MIN_SPEECH_MS=400
DIARIZATION_FAST_MIN_SILENCE_MS=200
DIARIZATION_FAST_MEAN_SHIFT_BANDWIDTH=0.4
DIARIZATION_SMOOTH_LABELS=1
DIARIZATION_RMS_NORMALIZE=1
```

**Result**: 10.518s (RTF=0.1753) vs baseline 13.098s (RTF=0.2183)
**Improvement**: 19.7% faster
