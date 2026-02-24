from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from .jobs import InMemoryJobStore
from .whisperx_service import TranscriptionService
from .debug_log import dlog
from .config import OPENROUTER_API_KEY
from .openrouter_service import analyze_transcript

logger = logging.getLogger(__name__)


_SEMAPHORE = asyncio.Semaphore(int(os.getenv("JOBS_CONCURRENCY", "1")))

_ASR_MODEL_NAME = os.getenv("WHISPERX_MODEL", "tiny")
_LANGUAGE = os.getenv("WHISPERX_LANGUAGE", "ru")
_BATCH_SIZE = int(os.getenv("WHISPERX_BATCH_SIZE", "8"))
_DIARIZE_NUM_SPEAKERS = os.getenv("DIARIZE_NUM_SPEAKERS")
_DIARIZE_MIN_SPEAKERS = os.getenv("DIARIZE_MIN_SPEAKERS")
_DIARIZE_MAX_SPEAKERS = os.getenv("DIARIZE_MAX_SPEAKERS")

_service: TranscriptionService | None = None
_service_lock = asyncio.Lock()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_markdown(output_path: Path, audio_path: Path, result: dict) -> None:
    segments = result.get("segments", []) or []
    segments = sorted(segments, key=lambda s: float(s.get("start") or 0.0))

    max_gap_s = 2.0
    blocks: list[dict] = []
    for seg in segments:
        spk = (seg.get("speaker") or "").strip() or "Без метки"
        text = str(seg.get("text") or "").strip()
        if not text or text == "[...]":
            continue
        start = float(seg.get("start") or 0.0)
        end = float(seg.get("end") or start)

        if blocks:
            last = blocks[-1]
            gap = start - last["end"]
            if last["speaker"] == spk and gap <= max_gap_s:
                last["text"] += " " + text
                last["end"] = end
                continue

        blocks.append({"speaker": spk, "text": text, "start": start, "end": end})

    lines: list[str] = []
    lines.append("# Транскрипция")
    lines.append("")
    lines.append(f"- Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    lines.append(f"- Аудио: `{audio_path.name}`")
    lines.append(f"- Модель: `{result.get('asr_model') or _ASR_MODEL_NAME}`")
    lines.append(f"- Язык: `{result.get('language') or _LANGUAGE}`")
    lines.append("")

    for block in blocks:
        lines.append(f"**{block['speaker']}:** {block['text']}")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_json(output_path: Path, result: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_analysis_markdown(
    output_path: Path,
    transcript: str,
    analysis: str,
) -> None:
    """
    Write final analysis markdown with AI analysis FIRST, then transcript.
    """
    lines = [
        "# Анализ психотерапевтической сессии",
        "",
        "## Анализ сессии (AI)",
        "",
        analysis,
        "",
        "---",
        "",
        "## Исходная транскрипция",
        "",
        transcript,
        "",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


async def _ffmpeg_convert_to_wav(input_path: Path, wav_path: Path) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(wav_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed (code={proc.returncode}): {err.decode('utf-8', 'ignore')}")


def _parse_int_or_none(v: str | None) -> int | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


async def _get_service() -> TranscriptionService:
    global _service
    async with _service_lock:
        if _service is None:
            _service = TranscriptionService(
                model_name=_ASR_MODEL_NAME,
                batch_size=_BATCH_SIZE,
            )
        return _service


async def run_job(job_id: str, input_path: Path, store: InMemoryJobStore) -> None:
    async with _SEMAPHORE:
        try:
            # region agent log
            dlog(
                run_id="pre-fix",
                hypothesis_id="H3",
                location="backend/app/worker.py:run_job",
                message="run_job start",
                data={"job_id": job_id, "input_suffix": input_path.suffix},
            )
            # endregion
            store.update(job_id, state="running", stage="convert", progress=0.15)

            job_dir = Path(input_path).parent
            wav_path = job_dir / "audio.wav"
            try:
                await _ffmpeg_convert_to_wav(input_path, wav_path)
                audio_path: Path = wav_path
            except (FileNotFoundError, RuntimeError):
                # ffmpeg isn't installed or input isn't decodable; continue with original input
                audio_path = input_path

            store.update(job_id, stage="transcribe", progress=0.55)
            # region agent log
            dlog(
                run_id="pre-fix",
                hypothesis_id="H3",
                location="backend/app/worker.py:run_job",
                message="after_convert_stage_transcribe",
                data={
                    "job_id": job_id,
                    "used_wav": (audio_path == wav_path),
                    "audio_suffix": audio_path.suffix,
                },
            )
            # endregion

            result: dict
            if os.getenv("WHISPERX_DISABLE", "").strip() in {"1", "true", "yes"}:
                result = {
                    "segments": [
                        {
                            "start": 0.0,
                            "end": 0.0,
                            "text": "[backend] Transcription pipeline disabled (WHISPERX_DISABLE=1).",
                        }
                    ]
                }
            else:
                try:
                    store.update(job_id, stage="align", progress=0.85)
                    # region agent log
                    dlog(
                        run_id="pre-fix",
                        hypothesis_id="H3",
                        location="backend/app/worker.py:run_job",
                        message="before_service_transcribe",
                        data={
                            "job_id": job_id,
                            "language": _LANGUAGE,
                            "num_speakers": _parse_int_or_none(_DIARIZE_NUM_SPEAKERS),
                            "min_speakers": _parse_int_or_none(_DIARIZE_MIN_SPEAKERS),
                            "max_speakers": _parse_int_or_none(_DIARIZE_MAX_SPEAKERS),
                        },
                    )
                    # endregion
                    service = await _get_service()
                    aligned = await service.transcribe(
                        audio_path,
                        language=_LANGUAGE,
                        num_speakers=_parse_int_or_none(_DIARIZE_NUM_SPEAKERS),
                        min_speakers=_parse_int_or_none(_DIARIZE_MIN_SPEAKERS),
                        max_speakers=_parse_int_or_none(_DIARIZE_MAX_SPEAKERS),
                        progress_cb=lambda stage, progress=None: store.update(job_id, stage=stage, progress=progress),
                    )
                    result = aligned
                except Exception as e:
                    # region agent log
                    dlog(
                        run_id="pre-fix",
                        hypothesis_id="H2",
                        location="backend/app/worker.py:run_job",
                        message="service.transcribe failed",
                        data={
                            "job_id": job_id,
                            "err_type": type(e).__name__,
                            "err": str(e)[:500],
                        },
                    )
                    # endregion
                    # Minimal "working" backend even without WhisperX installed/configured.
                    result = {
                        "segments": [
                            {
                                "start": 0.0,
                                "end": 0.0,
                                "text": f"[backend] Transcription pipeline unavailable: {e}",
                            }
                        ]
                    }

            store.update(job_id, stage="write", progress=0.95)
            md_path = _project_root() / "output" / f"{job_id}.md"
            json_path = _project_root() / "output" / f"{job_id}.json"
            await asyncio.to_thread(_write_markdown, md_path, audio_path, result)
            await asyncio.to_thread(_write_json, json_path, result)

            store.set_markdown_path(job_id, md_path)
            store.set_json_path(job_id, json_path)

            store.update(job_id, state="done", stage="done", progress=1.0)
            # region agent log
            dlog(
                run_id="pre-fix",
                hypothesis_id="H3",
                location="backend/app/worker.py:run_job",
                message="run_job done",
                data={
                    "job_id": job_id,
                    "md_exists": md_path.exists(),
                    "json_exists": json_path.exists(),
                    "segments": len((result.get("segments") or [])),
                },
            )
            # endregion
        except Exception as e:
            # region agent log
            dlog(
                run_id="pre-fix",
                hypothesis_id="H4",
                location="backend/app/worker.py:run_job",
                message="run_job error",
                data={"job_id": job_id, "error": str(e)[:500]},
            )
            # endregion
            store.update(job_id, state="error", progress=1.0, error=str(e))

