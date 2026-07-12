"""Canonical filesystem paths for the EvoMas tree.

Single source of truth for every "where on disk does X live" question
the framework asks (config roots, results layout, instance cache, the
SWE-bench venv shim). `api/common.py` re-exports these; the CLI and
tests import them directly.

Constants are pure (no side effects). Call `bootstrap()` once at process
start when you need the side-effect bundle: mkdir of the writable
folders, sys.path push of the repo root, .env load, and the one-time
migrations of legacy folder names. The api server and `evomas` CLI both
do that before any router/handler runs.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


# ─── Pure constants ─────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent.parent

CONFIG_DIR: Path = BASE_DIR / "evomas" / "config"
PREDEFINED_CONFIG_DIR: Path = CONFIG_DIR / "predefined"
LOADED_CONFIG_DIR: Path = CONFIG_DIR / "loaded"
INSTANCES_PATH: Path = BASE_DIR / "swebench_instances.jsonl"

# Load `.env` BEFORE resolving env-driven constants. `bootstrap()` also
# loads them later for the side-effect bundle, but that fires AFTER
# `RESULTS_DIR` is bound — without this eager call, a `RESULTS_DIR=…`
# set in `api/.env` is silently ignored because os.getenv() returns
# empty at module-import time. `override=False` keeps shell-set values
# winning over .env values, matching the bootstrap() contract.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(BASE_DIR / "evomas" / ".env", override=False)
    _load_dotenv(BASE_DIR / "api" / ".env", override=False)
except ImportError:
    # python-dotenv not installed — paths fall back to defaults; the
    # CLI/API will fail loud elsewhere if dotenv is genuinely missing.
    pass


# Results root is overridable via RESULTS_DIR in evomas/.env or
# api/.env (relative values resolved against BASE_DIR). Resolved at
# module-import time so every caller sees the same path even if env
# vars mutate later.
def _resolve_results_dir() -> Path:
    raw = os.getenv("RESULTS_DIR", "").strip()
    if not raw:
        return BASE_DIR / "results"
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (BASE_DIR / p)


RESULTS_DIR: Path = _resolve_results_dir()
PREDICTIONS_DIR: Path = RESULTS_DIR / "predictions"
# Per-run user-facing text log surfaced by the Results page.
PREDICTION_TEXT_LOGS_DIR: Path = PREDICTIONS_DIR / "logs"
# Snapshot of the config used for each run; survives source-config edits.
PREDICTION_CONFIGS_DIR: Path = PREDICTIONS_DIR / "configs"
# Internal NDJSON SSE-event log per run; powers Inference-page reload-resume.
INFERENCE_INTERNAL_LOGS_DIR: Path = BASE_DIR / "evomas" / "logs" / "inference_logs"
EVALUATION_DIR: Path = RESULTS_DIR / "evaluations"

# Linux/macOS interpreter inside the bundled SWE-bench checkout — the
# evaluation harness needs this specific Python so its docker-build
# context picks up the right dependency tree.
SWEBENCH_VENV_PYTHON: Path = BASE_DIR / "SWE-bench" / "venv" / "bin" / "python"


# ─── Side effects (call once at process start) ──────────────────────────────
_BOOTSTRAPPED = False


def bootstrap() -> None:
    """Idempotent process-start setup:

    1. Push BASE_DIR onto sys.path so `import api` / `import evomas` work
       under the api server without an editable install hitting them.
    2. Load `evomas/.env` (then `api/.env` for overrides).
    3. mkdir every writable result/log folder.
    4. Migrate legacy folder names (singular `evaluation/` → plural
       `evaluations/`; NDJSON logs alongside text → dedicated dir).

    Safe to call multiple times; subsequent calls are no-ops.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True

    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    # Lazy import so a bare `import evomas.paths` doesn't drag in dotenv.
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / "evomas" / ".env", override=False)
    load_dotenv(BASE_DIR / "api" / ".env", override=False)

    # mkdir the directories the framework writes into. Config roots have
    # to exist before the topology page tries to list them; results
    # folders before the first run writes its artefacts.
    PREDEFINED_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOADED_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Migrate the singular `evaluation/` folder name; the rename has to
    # happen BEFORE we mkdir EVALUATION_DIR (otherwise the rename target
    # exists and the migration silently no-ops).
    _legacy_eval = RESULTS_DIR / "evaluation"
    if _legacy_eval.exists() and not EVALUATION_DIR.exists():
        _legacy_eval.rename(EVALUATION_DIR)

    # Migrate the previous NDJSON-log location (was alongside text logs).
    _legacy_internal_logs = PREDICTIONS_DIR / "logs"
    if _legacy_internal_logs.is_dir() and not INFERENCE_INTERNAL_LOGS_DIR.exists():
        INFERENCE_INTERNAL_LOGS_DIR.parent.mkdir(parents=True, exist_ok=True)
        _legacy_internal_logs.rename(INFERENCE_INTERNAL_LOGS_DIR)

    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    PREDICTION_TEXT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PREDICTION_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    INFERENCE_INTERNAL_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
