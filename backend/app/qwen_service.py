"""
QWEN CLI integration for therapy session analysis.
Calls QWEN CLI locally to analyze therapy transcripts.
"""
from __future__ import annotations

import asyncio
import logging
import shlex
from typing import Optional

from .config import QWEN_CLI_PATH

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """Ты врач психиатр, психотерапевт, придерживающийся гуманистического подхода, с психоаналитическим анализом. Перед тобой расшифровка сессии с клиентом. Составь резюме сессии, включи в него структурированные жалобы, особенности анамнеза, предположительный диагноз, прогнозируемые подходы к терапии. Опиши ключевые моменты сессии.
Ты можешь ставить диагнозы не совпадающие с диагнозом, звучащим на сессии и выдвигать несовпадающие с терапевтом концепции.
Проведи полноценную супервизию сессии
Результат представь в виде готового к скачиванию файла txt

---

Расшифровка сессии:

{transcript}
"""


async def analyze_with_qwen_cli(
    transcript: str,
) -> Optional[str]:
    """
    Send transcript to QWEN CLI for analysis.
    Returns the analysis text or None on failure.
    """
    if not QWEN_CLI_PATH:
        logger.warning("QWEN_CLI_PATH not set, skipping QWEN analysis")
        return None

    prompt = ANALYSIS_PROMPT.format(transcript=transcript)

    # Build command: qwen <prompt>
    # Using shell=False for security, pass args as list
    cmd = [QWEN_CLI_PATH, prompt]

    try:
        logger.info("Calling QWEN CLI: %s", shlex.join(cmd))
        
        # Create subprocess with timeout
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # Wait for completion with timeout (5 minutes max)
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=300.0
            )
        except asyncio.TimeoutError:
            logger.error("QWEN CLI timed out after 300 seconds")
            proc.kill()
            await proc.wait()
            return None

        if proc.returncode != 0:
            logger.error(
                "QWEN CLI failed with code %s: %s",
                proc.returncode,
                stderr.decode("utf-8", "ignore")[:500]
            )
            return None

        output = stdout.decode("utf-8").strip()
        
        if not output:
            logger.warning("QWEN CLI returned empty output")
            return None

        logger.info("QWEN CLI analysis completed (%d chars)", len(output))
        return output

    except FileNotFoundError:
        logger.error("QWEN CLI not found at %s", QWEN_CLI_PATH)
        return None
    except Exception as e:
        logger.exception("QWEN CLI call failed: %s", e)
        return None
