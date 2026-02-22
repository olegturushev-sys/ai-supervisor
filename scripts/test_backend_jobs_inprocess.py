#!/usr/bin/env python3
from __future__ import annotations

import sys
import time
from pathlib import Path
import os

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["WHISPERX_DISABLE"] = "1"

from backend.app.main import app


def main() -> int:
    c = TestClient(app)

    r = c.get("/health")
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ok"}

    files = {"file": ("audio.wav", b"RIFF0000WAVEfmt ", "audio/wav")}
    r = c.post("/jobs", files=files)
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    state = None
    for _ in range(50):
        jr = c.get(f"/jobs/{job_id}")
        assert jr.status_code == 200, jr.text
        payload = jr.json()
        state = payload["state"]
        if state in ("done", "error"):
            break
        time.sleep(0.1)

    assert state == "done", payload

    rr = c.get(f"/jobs/{job_id}/result")
    assert rr.status_code == 200, rr.text
    assert rr.headers.get("content-type", "").startswith("text/markdown")
    assert len(rr.text) > 0

    print("OK", job_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

