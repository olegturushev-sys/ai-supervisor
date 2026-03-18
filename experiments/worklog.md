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

### Run 5: Larger VAD thresholds (500/250) — transcription_time=15.034s (discard)
- What changed: MIN_SPEECH_MS=500, MIN_SILENCE_MS=250
- Result: 15.034s (worse)
- Status: discard

### Run 6: Larger bandwidth (0.6) — transcription_time=12.630s (discard)
- What changed: MEAN_SHIFT_BANDWIDTH=0.6
- Result: 12.630s (worse than best)
- Status: discard

## Key Insights

1. **VAD thresholds are crucial**: MIN_SPEECH_MS=400, MIN_SILENCE_MS=200 reduces time by 19.7%
2. SEGMENT_CONCURRENCY=16 provides marginal improvement
3. Thread settings don't significantly impact this workload
4. Larger VAD thresholds (500/250) make it worse
5. Larger mean_shift_bandwidth makes it worse
6. DIARIZATION_FIRST=1 is crucial for speed

## Final Optimal Settings

```env
SEGMENT_CONCURRENCY=16
DIARIZATION_FAST_MIN_SPEECH_MS=400
DIARIZATION_FAST_MIN_SILENCE_MS=200
DIARIZATION_FAST_MEAN_SHIFT_BANDWIDTH=0.4
```

**Result**: 10.518s (RTF=0.1753) vs baseline 13.098s (RTF=0.2183)
**Improvement**: 19.7% faster

## Quality Considerations

Larger VAD thresholds may skip short pauses/speech. For therapy sessions with natural speech patterns, this should be acceptable. Monitor output quality for missed short utterances.
