# Autoresearch Worklog

## Session: Transcription Speed Optimization

### Run 1: Baseline — transcription_time=13.098s
- Timestamp: 2026-03-18
- What changed: Initial baseline measurement
- Result: 13.098s, RTF=0.2183, 16 segments
- Insight: Baseline established
- Next: Try increasing SEGMENT_CONCURRENCY

### Run 2: SEGMENT_CONCURRENCY=16 — transcription_time=12.998s (keep)
- Timestamp: 2026-03-18
- What changed: SEGMENT_CONCURRENCY from 8 to 16
- Result: 12.998s (-0.1s, -0.76%), RTF=0.2166
- Insight: Higher concurrency provides marginal improvement
- Next: Try adjusting VAD parameters

### Run 3: Thread optimization — transcription_time=12.998s (keep)
- Timestamp: 2026-03-18
- What changed: Added OMP_NUM_THREADS=8, MKL_NUM_THREADS=8
- Result: 12.998s (no change)
- Insight: Thread settings don't significantly impact this workload
- Next: Try different optimizations

## Key Insights
- SEGMENT_CONCURRENCY=16 is slightly better than 8
- VAD threshold 0.7 made it worse (more segments to process)
- WHISPERX_BATCH_SIZE=16 made it worse (memory pressure)
- DIARIZATION_FIRST=0 is much slower (21.667s vs 12.998s)
- Thread settings have minimal impact
- Current best: 12.998s (RTF=0.2166) with SEGMENT_CONCURRENCY=16

## Next Ideas
1. Try disabling diarization entirely (just transcription)
2. Cache model loading between runs
3. Optimize audio preprocessing (resampling, etc.)
4. Try different whisper models (small vs tiny)
