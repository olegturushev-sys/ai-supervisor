from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_ENCODER_CACHE: dict[tuple[str, str], Any] = {}
_CACHE_LOCK = threading.Lock()


def get_ecapa_encoder(embedding_model: str, device: str) -> Any:
    key = (embedding_model, device)
    with _CACHE_LOCK:
        if key not in _ENCODER_CACHE:
            t0 = time.perf_counter()
            from speechbrain.inference.speaker import EncoderClassifier
            _ENCODER_CACHE[key] = EncoderClassifier.from_hparams(
                source=embedding_model,
                run_opts={"device": device},
            )
            logger.info("ECAPA encoder %s loaded in %.2fs", embedding_model, time.perf_counter() - t0)
        return _ENCODER_CACHE[key]
