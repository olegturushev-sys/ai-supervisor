# Autoresearch: Transcription Speed Optimization

## Objective
Optimize transcription speed on M2 Mac while maintaining quality. Current setup uses CPU with SEGMENT_CONCURRENCY=8.

## Metrics
- **Primary**: transcription_time (seconds, lower is better)
- **Secondary**: transcription_speed (RTF - Real-Time Factor, lower is better), memory_mb

## How to Run
`./autoresearch.sh` — outputs `METRIC name=number` lines.

## Files in Scope
- `backend/app/config.py` — device selection, compute type
- `backend/app/whisperx_service.py` — transcription pipeline
- `backend/app/worker.py` — job orchestration
- `backend/app/services/diarization_fast.py` — fast diarization
- `backend/app/embedding_cache.py` — ECAPA encoder caching
- `.env` — configuration parameters

## Off Limits
- Do not commit secrets (API keys)
- Do not change the audio processing pipeline fundamentally

## Constraints
- Must work on macOS with Apple Silicon (M2)
- Must maintain transcription quality
- Tests must complete without errors

## What's Been Tried

### Baseline (Run 1)
- CPU + int8, SEGMENT_CONCURRENCY=8
- Device: cpu, Compute: int8
- GigaAM model: v3_e2e_rnnt
- Result: baseline measurement needed

### Ideas
1. Increase SEGMENT_CONCURRENCY (8 → 16)
2. Adjust VAD_THRESHOLD_SCALE (0.9 → 0.5) to reduce segments
3. Skip diarization for short audio
4. Use batch_size optimization for ECAPA
5. Preload models on startup
6. Cache VAD model
