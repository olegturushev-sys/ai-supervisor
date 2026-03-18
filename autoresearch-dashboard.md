# Autoresearch Dashboard: Transcription Speed

**Runs:** 4 | **Kept:** 4 | **Discarded:** 0 | **Crashed:** 0
**Baseline:** transcription_time: 13.098s (#1)
**Best:** transcription_time: 10.518s (#4, -19.7%)

| # | commit | transcription_time | rtf | segments | status | description |
|---|--------|------------------|-----|---------|--------|-------------|
| 1 | e4a848b | 13.098s | 0.2183 | 16 | keep | baseline |
| 2 | 5e669e2 | 12.998s (-0.76%) | 0.2166 | 16 | keep | SEGMENT_CONCURRENCY=16 |
| 3 | 4fb5fa2 | 12.998s (-0.76%) | 0.2166 | 16 | keep | thread optimization |
| 4 | 4fb5fa2 | 10.518s (-19.7%) | 0.1753 | 16 | keep | VAD thresholds (MIN_SPEECH_MS=400, MIN_SILENCE_MS=200) |

## Insights

- **MAJOR WIN**: Increasing VAD thresholds (MIN_SPEECH_MS=400, MIN_SILENCE_MS=200) reduces time by 19.7%
- SEGMENT_CONCURRENCY=16 provides marginal improvement
- Thread settings don't significantly impact performance
- VAD threshold 0.7 makes it worse (more segments)
- DIARIZATION_FIRST=1 is crucial for speed
- Current best RTF: 0.1753 (processes 60s audio in ~10.5s)

## Next Steps

1. Try even larger VAD thresholds (500/250)
2. Adjust mean_shift_bandwidth
3. Consider quality impact of larger thresholds
