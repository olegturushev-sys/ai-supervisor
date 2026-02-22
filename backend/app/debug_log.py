from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional


_LOG_PATH = Path("/Users/olegturushev/Note Therapy/.cursor/debug-8957bd.log")
_SESSION_ID = "8957bd"


def dlog(
    *,
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: Optional[dict[str, Any]] = None,
) -> None:
    """
    NDJSON debug logger for runtime evidence. Never log secrets.
    """
    try:
        payload = {
            "sessionId": _SESSION_ID,
            "id": f"log_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}",
            "timestamp": int(time.time() * 1000),
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
        }
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Never crash the app due to debug logging
        pass

