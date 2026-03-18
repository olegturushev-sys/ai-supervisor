#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

# Optimize thread settings for CPU
export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8
export NUMEXPR_NUM_THREADS=8

echo "=== Autoresearch: Transcription Speed Benchmark ===" >&2

# Create test audio if not exists (60 seconds of silence with beeps)
TEST_AUDIO="experiments/test_audio.wav"

if [[ ! -f "$TEST_AUDIO" ]]; then
    echo "Creating test audio file..." >&2
    
    # Generate 60 second audio with some speech-like patterns using Python
    python3 << 'PYEOF'
import struct
import wave
import math
import random

# Create 60 second audio at 16kHz
sample_rate = 16000
duration = 60
num_samples = sample_rate * duration

with wave.open("experiments/test_audio.wav", "w") as f:
    f.setnchannels(1)
    f.setsampwidth(2)  # 2 bytes = 16 bit
    f.setframerate(sample_rate)
    
    import numpy as np
    
    # Generate speech-like audio with pauses
    audio = np.zeros(num_samples, dtype=np.int16)
    
    # Add segments of "speech" (noise + tones)
    segment_positions = [0, 8, 15, 22, 30, 38, 45, 52]
    segment_duration = 3  # seconds
    
    for pos in segment_positions:
        start = pos * sample_rate
        end = min(start + segment_duration * sample_rate, num_samples)
        
        # Generate speech-like signal (modulated noise)
        t = np.linspace(0, segment_duration, end - start)
        speech = np.sin(2 * np.pi * 200 * t) * 0.3
        speech += np.sin(2 * np.pi * 400 * t) * 0.2
        speech += np.random.normal(0, 0.15, len(t))
        
        # Apply envelope
        envelope = np.ones_like(t)
        attack = int(0.1 * sample_rate)
        release = int(0.2 * sample_rate)
        envelope[:attack] = np.linspace(0, 1, attack)
        envelope[-release:] = np.linspace(1, 0, release)
        speech *= envelope
        
        audio[start:end] = (speech * 16000).astype(np.int16)
    
    f.writeframes(audio.tobytes())

print("Test audio created: 60 seconds, 16kHz, mono")
PYEOF
fi

echo "Test audio: $TEST_AUDIO" >&2

# Load config
source <(grep -E '^[A-Z_]+=' .env | sed 's/^/export /')

# Record start time
START_TIME=$(date +%s%N)

# Run transcription
cd backend
export PYTHONPATH="${PWD}:${PYTHONPATH:-}"

# Get the project root
PROJECT_ROOT="$(cd .. && pwd)"
export PROJECT_ROOT

# Capture output
OUTPUT=$(python3 << PYEOF
import asyncio
import sys
import time
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.whisperx_service import TranscriptionService

project_root = os.environ.get('PROJECT_ROOT', '/Users/olegturushev/Note Therapy/whisperx-gigaam-mac')

async def transcribe():
    service = TranscriptionService(
        model_name="tiny",
        batch_size=8,
    )
    
    audio_path = Path(project_root) / "experiments" / "test_audio.wav"
    start = time.time()
    
    result = await service.transcribe(
        str(audio_path),
        language="ru",
        num_speakers=None,
        progress_cb=None,
    )
    
    end = time.time()
    duration = end - start
    audio_duration = 60.0  # seconds
    
    print(f"TRANSCRIPTION_TIME={duration:.3f}")
    print(f"RTF={duration/audio_duration:.4f}")
    print(f"SEGMENTS={len(result.get('segments', []))}")

asyncio.run(transcribe())
PYEOF
)

END_TIME=$(date +%s%N)
DURATION=$(echo "scale=3; ($END_TIME - $START_TIME) / 1000000000" | bc)
EXIT_CODE=$?
echo "$OUTPUT"
echo "" >&2
echo "Total script duration: ${DURATION}s, Exit code: $EXIT_CODE" >&2

# Parse metrics from output
TRANSCRIPTION_TIME=$(echo "$OUTPUT" | grep "^TRANSCRIPTION_TIME=" | cut -d= -f2)
RTF=$(echo "$OUTPUT" | grep "^RTF=" | cut -d= -f2)
SEGMENTS=$(echo "$OUTPUT" | grep "^SEGMENTS=" | cut -d= -f2)

echo "METRIC transcription_time=${TRANSCRIPTION_TIME:-0}"
echo "METRIC rtf=${RTF:-0}"
echo "METRIC segments=${SEGMENTS:-0}"

exit $EXIT_CODE
