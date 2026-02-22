#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Force lightweight path for smoke tests.
os.environ["WHISPERX_DISABLE"] = "1"

from backend.app.main import app  # noqa: E402


def main() -> int:
    c = TestClient(app)

    r = c.get("/health")
    assert r.status_code == 200, r.text

    files = {"file": ("audio.wav", b"RIFF0000WAVEfmt ", "audio/wav")}
    r = c.post("/transcribe", files=files)
    assert r.status_code == 200, r.text
    payload = r.json()
    task_id = payload["task_id"]

    state = None
    status_payload = None
    for _ in range(200):
        s = c.get(f"/status/{task_id}")
        assert s.status_code == 200, s.text
        status_payload = s.json()
        state = status_payload["state"]
        if state in ("done", "error"):
            break
        time.sleep(0.05)

    assert status_payload is not None
    assert state == "done", status_payload

    dl = c.get(f"/download/{task_id}.md")
    assert dl.status_code == 200, dl.text
    assert dl.headers.get("content-type", "").startswith("text/markdown")
    assert len(dl.text) > 0

    print("OK", task_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

