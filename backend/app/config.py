from __future__ import annotations

import os
from typing import Literal, Optional, Tuple

Device = Literal["cuda", "mps", "cpu"]
ComputeType = Literal["float32", "float16", "int8"]


def choose_device_compute_type() -> Tuple[Device, ComputeType]:
    """
    Defaults for this project:
    - cuda (if present) -> float16
    - mps (Apple Silicon) -> float32
    - cpu -> int8 (stable fallback; faster-whisper/ctranslate2 does not support mps)
    """
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda", "float16"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps", "float32"
        return "cpu", "int8"
    except Exception:
        return "cpu", "int8"


DEVICE, COMPUTE_TYPE = choose_device_compute_type()

# Hugging Face access token (optional) for WhisperX models or GigaAM longform VAD (pyannote/segmentation-3.0).
# Must be provided via environment; never hardcode secrets in code.
HF_TOKEN: Optional[str] = os.getenv("HF_TOKEN")

