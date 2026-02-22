#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.config import COMPUTE_TYPE, DEVICE  # noqa: E402
import whisperx


def format_ts(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    total_ms = int(seconds * 1000)
    sec, ms = divmod(total_ms, 1000)
    mins, sec = divmod(sec, 60)
    hrs, mins = divmod(mins, 60)
    return f"{hrs:02d}:{mins:02d}:{sec:02d}.{ms:03d}"


def write_markdown(
    output_path: Path,
    audio_path: Path,
    model_name: str,
    device: str,
    result: dict,
) -> None:
    lines: list[str] = []
    lines.append("# Transcript")
    lines.append("")
    lines.append(f"- Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- Audio: `{audio_path}`")
    lines.append(f"- Model: `{model_name}`")
    lines.append(f"- Device: `{device}`")
    lines.append("")
    lines.append("## Segments")
    lines.append("")

    segments = result.get("segments", []) or []
    for seg in segments:
        start = format_ts(seg.get("start", 0.0))
        end = format_ts(seg.get("end", 0.0))
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        lines.append(f"- [{start} - {end}] {text}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="First-run CLI transcription using WhisperX (Markdown output)."
    )
    parser.add_argument(
        "--audio",
        required=True,
        help="Path to input audio file.",
    )
    parser.add_argument(
        "--model",
        default="large-v3",
        help="Whisper model name (default: large-v3).",
    )
    parser.add_argument(
        "--language",
        default="ru",
        help="Language code for ASR (default: ru).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="ASR batch size (default: 8).",
    )
    parser.add_argument(
        "--output",
        default="output/transcript.md",
        help="Markdown output path (default: output/transcript.md).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    audio_path = Path(args.audio).expanduser().resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    output_path = Path(args.output).expanduser().resolve()
    device, compute_type = DEVICE, COMPUTE_TYPE

    print(f"[INFO] Loading WhisperX model '{args.model}' on {device}...")
    model = whisperx.load_model(args.model, device=device, compute_type=compute_type)

    print(f"[INFO] Loading audio: {audio_path}")
    audio = whisperx.load_audio(str(audio_path))

    print("[INFO] Running transcription...")
    result = model.transcribe(audio, batch_size=args.batch_size, language=args.language)

    print(f"[INFO] Writing Markdown: {output_path}")
    write_markdown(output_path, audio_path, args.model, device, result)
    print("[INFO] Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
