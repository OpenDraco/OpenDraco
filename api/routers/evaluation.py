"""Evaluation-page endpoints: scan / inspect prediction JSONLs, run
them through the SWE-bench harness (or `apply_and_test.py` for custom
repos), and stream results back as SSE."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.common import (
    BASE_DIR,
    EVALUATION_DIR,
    INSTANCES_PATH,
    PREDICTIONS_DIR,
    RESULTS_DIR,
    SWEBENCH_VENV_PYTHON,
    safe_under,
)
from evomas.paths import (
    INFERENCE_INTERNAL_LOGS_DIR,
    PREDICTION_TEXT_LOGS_DIR,
)
from evomas.utils.instances import instance_origin_lookup, load_instance_rows
from evomas.utils.paths import to_wsl
from evomas.utils.predictions import derive_run_id_base

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Prediction listing / inspection ─────────────────────────────────────────
_PRED_KEY_RE_LOCAL = re.compile(r"^prediction-(.+)\.jsonl$")


class EvaluationRequest(BaseModel):
    predictions_path: str
    max_workers: int = 4
    # Both auto-detected from the prediction file when omitted.
    split: str | None = None
    run_id: str | None = None
    # Required: filename stem under `scripts/evaluation/` (no `.py`).
    script: str | None = None


@router.get("/api/paths")
def get_paths() -> dict[str, str]:
    """Resolved on-disk paths the frontend renders in user-facing strings
    (empty-state hints, tooltips, error messages). Returned as repo-relative
    POSIX strings so the same payload reads the same on Windows + macOS.
    Falls back to the absolute path when a value lives outside `BASE_DIR`
    (rare: a user passes an absolute `RESULTS_DIR` outside the repo)."""

    def rel(p: Path) -> str:
        try:
            return p.resolve().relative_to(BASE_DIR.resolve()).as_posix()
        except (ValueError, OSError):
            return p.as_posix()

    return {
        "base_dir":              rel(BASE_DIR),
        "results_dir":           rel(RESULTS_DIR),
        "predictions_dir":       rel(PREDICTIONS_DIR),
        "predictions_logs_dir":  rel(PREDICTION_TEXT_LOGS_DIR),
        "evaluations_dir":       rel(EVALUATION_DIR),
        "inference_logs_dir":    rel(INFERENCE_INTERNAL_LOGS_DIR),
    }


@router.get("/api/predictions")
def list_predictions() -> list[str]:
    files = sorted(PREDICTIONS_DIR.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True)
    return [str(p) for p in files]


_DEFAULT_MANIFEST = {"needs_wsl": False}


def _eval_manifest(stem: str) -> dict[str, Any]:
    """Read `EVOMAS_EVALUATOR` from `scripts/evaluation/<stem>.py` (or
    fall back to defaults when missing / unparseable)."""
    script_path = BASE_DIR / "scripts" / "evaluation" / f"{stem}.py"
    if not script_path.is_file():
        raise FileNotFoundError(f"evaluator script not found: {stem}")
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"_eval_{stem}", script_path)
    if spec is None or spec.loader is None:
        return {**_DEFAULT_MANIFEST}
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        logger.warning("evaluator %s import failed: %s; using defaults", stem, exc)
        return {**_DEFAULT_MANIFEST}
    declared = getattr(mod, "EVOMAS_EVALUATOR", None)
    if not isinstance(declared, dict):
        return {**_DEFAULT_MANIFEST}
    return {**_DEFAULT_MANIFEST, **declared}


@router.get("/api/evaluation/scripts")
def list_evaluation_scripts() -> list[dict[str, str]]:
    """Every `scripts/evaluation/*.py` as `{value, label}` for the
    Evaluation-page dropdown. Label = `<stem>.py`."""
    folder = BASE_DIR / "scripts" / "evaluation"
    out: list[dict[str, str]] = []
    if not folder.is_dir():
        return out
    for p in sorted(folder.glob("*.py")):
        stem = p.stem
        if stem.startswith("_"):
            continue
        out.append({"value": stem, "label": p.name})
    return out


@router.get("/api/predictions/inspect")
def inspect_prediction(path: str) -> dict[str, Any]:
    """`{groups: [{subset, split, instance_ids}], total, ...}` for a
    prediction file. Resolution order per line: row's own subset/split,
    then the instances cache, then `("lite", "dev")`."""
    p = safe_under(PREDICTIONS_DIR, path)
    if not p.is_file():
        raise HTTPException(404, "prediction file not found")

    origin = instance_origin_lookup(INSTANCES_PATH)
    text = p.read_text(encoding="utf-8")

    groups: dict[tuple[str, str], list[str]] = {}
    total = 0
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        iid = obj.get("instance_id")
        if not isinstance(iid, str) or not iid:
            continue
        total += 1

        subset = obj.get("subset")
        split = obj.get("split")
        if not subset or not split:
            cached = origin.get(iid)
            if cached:
                subset = subset or cached[0]
                split = split or cached[1]
        subset = subset or "lite"
        split = split or "dev"

        groups.setdefault((subset, split), []).append(iid)

    m = _PRED_KEY_RE_LOCAL.match(p.name)
    run_id_base = m.group(1) if m else p.stem

    return {
        "path": str(p),
        "name": p.name,
        "run_id_base": run_id_base,
        "total": total,
        "groups": [
            {"subset": s, "split": sp, "instance_ids": ids}
            for (s, sp), ids in groups.items()
        ],
    }


# ─── Run / cancel evaluation ──────────────────────────────────────────────────
_eval_procs: dict[str, Any] = {}


@router.post("/api/evaluation/run")
async def run_evaluation(req: EvaluationRequest):
    pred_path = Path(req.predictions_path)
    if not pred_path.is_file():
        raise HTTPException(404, f"Predictions file not found: {req.predictions_path}")

    q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    key = req.predictions_path

    forced = (req.script or "").strip()
    if not forced:
        raise HTTPException(400, "Missing evaluator script.")
    try:
        manifest = _eval_manifest(forced)
    except FileNotFoundError:
        raise HTTPException(400, f"Unknown evaluator script: {forced!r}")

    base = req.run_id or f"evaluation-{derive_run_id_base(pred_path)}"
    all_predictions = [ln for ln in pred_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def put(data: dict) -> None:
        loop.call_soon_threadsafe(q.put_nowait, data)

    def worker() -> None:
        try:
            EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
            tmp_dir = EVALUATION_DIR / "_tmp_predictions"
            tmp_dir.mkdir(parents=True, exist_ok=True)

            if not all_predictions:
                put({"type": "log", "message": f"{pred_path.name} has no prediction rows; nothing to evaluate."})
                put({"type": "done", "returncode": 0})
                return

            iids: list[str] = []
            for raw in all_predictions:
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                iid = obj.get("instance_id")
                if iid:
                    iids.append(iid)
            inst_rows = load_instance_rows(iids, INSTANCES_PATH)

            model_name = "evomas"
            for raw in all_predictions:
                try:
                    cand = json.loads(raw).get("model_name_or_path") or json.loads(raw).get("model")
                    if isinstance(cand, str) and cand.strip():
                        model_name = cand.strip()
                        break
                except json.JSONDecodeError:
                    continue

            shared_pred_path = tmp_dir / f"{pred_path.stem}.jsonl"
            shared_pred_path.write_text("\n".join(all_predictions) + "\n", encoding="utf-8")
            shared_inst_path = tmp_dir / f"{pred_path.stem}__instances.jsonl"
            shared_inst_path.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in inst_rows.values()) + "\n",
                encoding="utf-8",
            )

            put({"type": "log", "message": (
                f"Evaluator {forced!r} over {len(all_predictions)} prediction row(s); "
                f"{len(inst_rows)} instance row(s) resolved for --instances."
            )})
            put({"type": "group_start", "subset": "all", "split": "all",
                 "run_id": base, "count": len(all_predictions)})

            # `needs_wsl: True` wraps in WSL (swebench is POSIX-only).
            script_path = BASE_DIR / "scripts" / "evaluation" / f"{forced}.py"
            if manifest.get("needs_wsl"):
                cmd = [
                    "wsl",
                    to_wsl(str(SWEBENCH_VENV_PYTHON)),
                    to_wsl(str(script_path)),
                    "--predictions", to_wsl(str(shared_pred_path)),
                    "--instances",   to_wsl(str(shared_inst_path)),
                    "--report-dir",  to_wsl(str(EVALUATION_DIR)),
                    "--run-id",      base,
                    "--model",       model_name,
                ]
            else:
                cmd = [
                    sys.executable,
                    str(script_path),
                    "--predictions", str(shared_pred_path),
                    "--instances",   str(shared_inst_path),
                    "--report-dir",  str(EVALUATION_DIR),
                    "--run-id",      base,
                    "--model",       model_name,
                ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(BASE_DIR),
                encoding="utf-8",
                errors="replace",
            )
            _eval_procs[key] = proc
            assert proc.stdout is not None
            for line in iter(proc.stdout.readline, ""):
                put({"type": "log", "message": line.rstrip()})
            proc.wait()
            put({"type": "group_done", "subset": "all", "split": "all",
                 "run_id": base, "returncode": proc.returncode})
            put({"type": "done", "returncode": proc.returncode})
        except Exception as exc:
            put({"type": "error", "message": str(exc)})
        finally:
            loop.call_soon_threadsafe(q.put_nowait, None)

    threading.Thread(target=worker, daemon=True).start()

    async def generate():
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=3600.0)
            except asyncio.TimeoutError:
                yield 'data: {"type":"error","message":"Evaluation timeout"}\n\n'
                break
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/evaluation/cancel")
async def cancel_evaluation(predictions_path: str) -> dict:
    proc = _eval_procs.get(predictions_path)
    if proc:
        proc.terminate()
        return {"ok": True}
    return {"ok": False, "message": "No running evaluation found"}
