from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional, Tuple

os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.8"

# Load .env file if exists (for local development)
_env_file = Path(__file__).resolve().parents[2] / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value

Device = Literal["cuda", "mps", "cpu"]
ComputeType = Literal["float32", "float16", "int8"]


def choose_device_compute_type() -> Tuple[Device, ComputeType]:
    """
    Defaults for this project:
    - cuda (if present) -> float16
    - mps (Apple Silicon) -> int8 (with memory limit)
    - cpu -> int8
    
    Note: MPS memory limited via PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.8 to prevent crashes.
    """
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda", "float16"
        # MPS with memory limit for Apple Silicon
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps", "int8"
        return "cpu", "int8"
    except Exception:
        return "cpu", "int8"


DEVICE, COMPUTE_TYPE = choose_device_compute_type()

# Hugging Face access token (optional) for WhisperX models or GigaAM longform VAD (pyannote/segmentation-3.0).
# Must be provided via environment; never hardcode secrets in code.
HF_TOKEN: Optional[str] = os.getenv("HF_TOKEN")

# OpenRouter API key for therapy session analysis (https://openrouter.ai/keys)
OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")

# QWEN CLI path for local therapy session analysis
# Full path to qwen CLI executable (e.g. /usr/local/bin/qwen or ~/.local/bin/qwen)
QWEN_CLI_PATH: Optional[str] = os.getenv("QWEN_CLI_PATH")

