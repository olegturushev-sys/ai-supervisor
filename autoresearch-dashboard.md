# Autoresearch Dashboard: Transcription Speed

**Runs:** 3 | **Kept:** 3 | **Discarded:** 0 | **Crashed:** 0
**Baseline:** transcription_time: 13.098s (#1)
**Best:** transcription_time: 12.998s (#2, -0.76%)

| # | commit | transcription_time | rtf | segments | status | description |
|---|--------|------------------|-----|---------|--------|-------------|
| 1 | e4a848b | 13.098s | 0.2183 | 16 | keep | baseline |
| 2 | 5e669e2 | 12.998s (-0.76%) | 0.2166 | 16 | keep | SEGMENT_CONCURRENCY=16 |
| 3 | 4fb5fa2 | 12.998s (-0.76%) | 0.2166 | 16 | keep | thread optimization |

## Insights

- SEGMENT_CONCURRENCY=16 provides marginal improvement
- Thread settings (OMP_NUM_THREADS) don't significantly impact performance
- VAD threshold adjustments make performance worse
- DIARIZATION_FIRST=1 is crucial for speed (21.667s without vs 12.998s with)
- Current RTF: 0.2166 (processes 60s audio in ~13s)

## Next Steps

1. Consider using smaller whisper model (if quality allows)
2. Investigate model caching between runs
3. Profile the VAD/diarization pipeline
