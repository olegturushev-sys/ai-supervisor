"""
OpenRouter API integration for therapy session analysis.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from .config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "deepseek/deepseek-chat"

ANALYSIS_PROMPT = """Ты врач психиатр, психотерапевт, придерживающийся гуманистического подхода, с психоаналитическим анализом. Перед тобой расшифровка сессии с клиентом. Составь резюме сессии, включи в него структурированные жалобы, особенности анамнеза, предположительный диагноз, прогнозируемые подходы к терапии. Опиши ключевые моменты сессии. Ты можешь ставить диагнозы, не совпадающие с диагнозом, звучащим на сессии, и выдвигать несовпадающие с терапевтом концепции.

---

Ниже приведена расшифровка сессии:

{transcript}
"""


async def analyze_transcript(
    transcript: str,
    *,
    model: str = DEFAULT_MODEL,
) -> Optional[str]:
    """
    Send transcript to OpenRouter API for analysis.
    Returns the analysis text or None on failure.
    """
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY not set, skipping analysis")
        return None

    prompt = ANALYSIS_PROMPT.format(transcript=transcript)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/note-therapy/whisperx-gigaam-mac",
        "X-Title": "Note Therapy Transcription",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            logger.info("Calling OpenRouter API with model %s", model)
            response = await client.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
            )
            logger.info("OpenRouter response status: %s", response.status_code)
            response.raise_for_status()
            data = response.json()
            logger.info("OpenRouter response data: %s", str(data)[:500])
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip() if content else None
    except httpx.HTTPStatusError as e:
        logger.error("OpenRouter HTTP error: %s %s", e.response.status_code, e.response.text)
        return None
    except Exception as e:
        logger.exception("OpenRouter API call failed: %s", e)
        return None
