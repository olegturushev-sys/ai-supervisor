#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VENDOR_WHISPERX = _PROJECT_ROOT / "vendor" / "whisperx"
# Prefer the vendored fork (vendor/whisperx) over any pip-installed whisperx.
sys.path.insert(0, str(_VENDOR_WHISPERX))
sys.path.insert(0, str(_PROJECT_ROOT))

import whisperx  # noqa: E402
from backend.app.config import COMPUTE_TYPE, DEVICE  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Smoke test: transcribe RU audio and align with GigaAM (WhisperX fork)."
    )
    p.add_argument("--audio", required=True, help="Path to input audio file.")
    p.add_argument(
        "--whisper-model",
        default="tiny",
        help="Whisper model name for quick transcription (default: tiny).",
    )
    p.add_argument(
        "--language",
        default="ru",
        help="ASR language code (default: ru).",
    )
    p.add_argument(
        "--align-model",
        default=None,
        help='Optional explicit align model override (e.g. "gigaam" or HF wav2vec2). '
        "If omitted and language=ru, GigaAM should be used by default.",
    )
    p.add_argument("--batch-size", type=int, default=8, help="ASR batch size (default: 8).")
    return p.parse_args()


def _has_word_timestamps(aligned: dict) -> bool:
    segments = aligned.get("segments") or []
    for seg in segments:
        for w in (seg.get("words") or []):
            if w.get("start") is not None and w.get("end") is not None:
                return True
    return False


def main() -> int:
    args = parse_args()
    audio_path = Path(args.audio).expanduser().resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    device, compute_type = DEVICE, COMPUTE_TYPE
    print(f"[INFO] device={device} compute_type={compute_type}")
    print(f"[INFO] Loading WhisperX ASR model '{args.whisper_model}'...")
    model = whisperx.load_model(args.whisper_model, device=device, compute_type=compute_type)

    print(f"[INFO] Loading audio: {audio_path}")
    audio = whisperx.load_audio(str(audio_path))

    print("[INFO] Transcribing...")
    result = model.transcribe(audio, batch_size=args.batch_size, language=args.language)
    segments = result.get("segments") or []
    print(f"[INFO] ASR segments: {len(segments)}")
    if not segments:
        print("[ERROR] No ASR segments produced; cannot run alignment.")
        return 2

    lang = (result.get("language") or args.language or "ru").lower()
    print(f"[INFO] Loading align model for language={lang} align_model={args.align_model!r}...")
    align_model, align_metadata = whisperx.load_align_model(
        language_code=lang,
        device=device,
        align_model=args.align_model,
    )
    print(f"[INFO] align_metadata.type={align_metadata.get('type')} language={align_metadata.get('language')}")

    print("[INFO] Aligning...")
    aligned = whisperx.align(
        segments,
        align_model,
        align_metadata,
        audio,
        device,
        return_char_alignments=False,
    )

    ok = _has_word_timestamps(aligned)
    print(f"[INFO] alignment_word_timestamps={ok}")
    if not ok:
        print("[ERROR] Alignment finished but no word timestamps were produced.")
        return 3

    first = (aligned.get("segments") or [None])[0]
    if first is not None:
        preview = (first.get("text") or "").strip()
        print(f"[INFO] first_segment_text={preview!r}")
        words = first.get("words") or []
        if words:
            w0 = words[0]
            print(f"[INFO] first_word={w0.get('word')!r} [{w0.get('start')}, {w0.get('end')}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

