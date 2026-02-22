from __future__ import annotations

import sys
from pathlib import Path


def prefer_vendored_whisperx() -> None:
    """
    Prefer the vendored WhisperX fork under vendor/whisperx over any pip-installed whisperx.
    Mirrors the approach used in scripts/test_gigaam_alignment.py.
    """

    project_root = Path(__file__).resolve().parents[2]
    vendor_path = project_root / "vendor" / "whisperx"
    sys.path.insert(0, str(vendor_path))

