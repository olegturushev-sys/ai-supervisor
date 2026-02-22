from __future__ import annotations

import sys
from pathlib import Path


def prefer_vendored_gigaam() -> None:
    """
    Prefer vendored GigaAM under vendor/gigaam.
    """
    project_root = Path(__file__).resolve().parents[2]
    vendor_path = project_root / "vendor" / "gigaam"
    sys.path.insert(0, str(vendor_path))

