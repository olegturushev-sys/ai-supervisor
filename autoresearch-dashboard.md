# Autoresearch Dashboard: Transcription Speed

**Runs:** 4 | **Kept:** 4 | **Discarded:** 9 | **Crashed:** 0
**Baseline:** transcription_time: 13.098s (#1)
**Best:** transcription_time: 10.518s (#4, -19.7%)

| # | commit | transcription_time | rtf | segments | status | description |
|---|--------|------------------|-----|---------|--------|-------------|
| 1 | e4a848b | 13.098s | 0.2183 | 16 | keep | baseline |
| 2 | 5e669e2 | 12.998s (-0.76%) | 0.2166 | 16 | keep | SEGMENT_CONCURRENCY=16 |
| 3 | 4fb5fa2 | 12.998s (-0.76%) | 0.2166 | 16 | keep | thread optimization |
| 4 | 4fb5fa2 | 10.518s (-19.7%) | 0.1753 | 16 | keep | **VAD thresholds BEST** |

## Key Finding

**MIN_SPEECH_MS=400, MIN_SILENCE_MS=200** provides 19.7% speed improvement!

## Experiments Tested (All Worse)

| Setting | Result | Status |
|---------|--------|--------|
| MIN_SPEECH_MS=350, MIN_SILENCE_MS=150 | 13.466s | discard |
| MAX_SEGMENT_S=5 | 12.601s | discard |
| MIN_SEGMENT_S=1.5 | 12.992s | discard |
| SUBSEGMENT_S=4 | 13.067s | discard |
| SUBSEGMENT_S=2 | 10.637s | discard |
| SMOOTH_LABELS=0, RMS_NORMALIZE=0 | 13.180s | discard |
| MIN_SPEECH_MS=450 | 12.788s | discard |
| MIN_SPEECH_MS=380 | 11.133s | discard |
| SUBSEGMENT_S=3 | 13.599s | discard |

## Conclusion

The optimal VAD settings are in a narrow range around MIN_SPEECH_MS=400, MIN_SILENCE_MS=200. Further exploration did not find better combinations.
