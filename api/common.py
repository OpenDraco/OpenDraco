"""Thin api-side wrappers + re-exports.

Path constants live in `evomas.paths`; FastAPI-free helpers live in
`evomas.utils.*`. This module:
- Calls `bootstrap()` once at import time so the api server inherits
  the same sys.path / .env / mkdir setup the CLI does.
- Re-exports the path constants so existing `from api.common import X`
  imports keep working without a wide rename.
- Wraps a couple of evomas-side helpers that raise framework-specific
  exceptions into FastAPI `HTTPException`s.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException

from evomas.paths import (
    BASE_DIR,
    CONFIG_DIR,
    EVALUATION_DIR,
    INFERENCE_INTERNAL_LOGS_DIR,
    INSTANCES_PATH,
    LOADED_CONFIG_DIR,
    PREDEFINED_CONFIG_DIR,
    PREDICTION_CONFIGS_DIR,
    PREDICTION_TEXT_LOGS_DIR,
    PREDICTIONS_DIR,
    RESULTS_DIR,
    SWEBENCH_VENV_PYTHON,
    bootstrap,
)
from evomas.utils.paths import safe_under as _safe_under_pure

bootstrap()

# Re-exported so `from api.common import BASE_DIR …` continues to work.
__all__ = [
    "BASE_DIR",
    "CONFIG_DIR",
    "EVALUATION_DIR",
    "INFERENCE_INTERNAL_LOGS_DIR",
    "INSTANCES_PATH",
    "LOADED_CONFIG_DIR",
    "PREDEFINED_CONFIG_DIR",
    "PREDICTION_CONFIGS_DIR",
    "PREDICTION_TEXT_LOGS_DIR",
    "PREDICTIONS_DIR",
    "RESULTS_DIR",
    "SWEBENCH_VENV_PYTHON",
    "logger",
    "safe_under",
]


# The inference worker attaches a per-run text-log FileHandler to this
# logger so agent code's `logger.info(...)` ends up in the .log transcript.
logger = logging.getLogger("api")


def safe_under(root: Path, candidate: str) -> Path:
    """Path-traversal guard; translates the framework's `PermissionError`
    into FastAPI's `HTTPException(403, …)`."""
    try:
        return _safe_under_pure(root, candidate)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
