"""Results-page endpoints: browse past inference + evaluation runs,
fetch their per-file artefacts (prediction JSONL, text log, ATIF
trajectories, config snapshot), generate the reproduce-this-run Jupyter
notebook, publish a run to Graphectory, and reveal paths in the OS
file explorer."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.common import (
    EVALUATION_DIR,
    INFERENCE_INTERNAL_LOGS_DIR,
    INSTANCES_PATH,
    PREDICTION_CONFIGS_DIR,
    PREDICTION_TEXT_LOGS_DIR,
    PREDICTIONS_DIR,
    RESULTS_DIR,
    logger,
    safe_under,
)
from opendraco.utils import graphectory
from opendraco.utils.atif import TRAJECTORY_FILE
from opendraco.utils.instances import instance_memberships
from opendraco.utils.notebook import build_notebook_for_prediction
from opendraco.utils.predictions import (
    expand_hierarchy,
    pair_runs,
    scan_evaluations,
    scan_predictions,
)

router = APIRouter()


@router.get("/api/results/instances")
def list_result_instances() -> list[dict[str, Any]]:
    """List every instance_id with its (prediction, evaluation) runs
    paired up. Each row also carries `memberships` — every (subset,
    split) the instance belongs to, expanded through the dataset
    hierarchy so the Results page can group it under each."""
    preds = scan_predictions(PREDICTIONS_DIR)
    evals = scan_evaluations(EVALUATION_DIR)
    mems = instance_memberships(INSTANCES_PATH)
    ids = sorted(set(preds) | set(evals))

    out: list[dict[str, Any]] = []
    for iid in ids:
        raw_pairs = mems.get(iid) or [("lite", "dev")]
        pairs = expand_hierarchy(raw_pairs)
        out.append({
            "instance_id": iid,
            "subset": pairs[0][0],
            "split":  pairs[0][1],
            "memberships": [{"subset": s, "split": sp} for s, sp in pairs],
            "predictions": preds.get(iid, []),
            "evaluations": evals.get(iid, []),
            "runs": pair_runs(preds.get(iid, []), evals.get(iid, []), iid),
        })
    return out


# ─── Prediction artefacts ────────────────────────────────────────────────────
@router.get("/api/results/prediction")
def get_prediction(path: str, instance_id: str | None = None) -> dict[str, Any]:
    """Parsed JSONL line of a prediction file. With `instance_id` set,
    pick the matching line from a multi-instance file; otherwise return
    the first one."""
    p = safe_under(PREDICTIONS_DIR, path)
    if not p.is_file():
        raise HTTPException(404, "prediction file not found")
    text = p.read_text(encoding="utf-8")
    obj: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if instance_id is None:
            obj = parsed
            break
        if parsed.get("instance_id") == instance_id:
            obj = parsed
            break
    return {"path": str(p), "name": p.name, "raw": text, "data": obj}


@router.get("/api/results/prediction/log")
def get_prediction_log(path: str) -> dict[str, Any]:
    """User-facing Python `logging` transcript for a prediction. Lives at
    `results/predictions/logs/prediction-<run_id>.log`; `path` is the
    sibling prediction `.jsonl`. Returns `exists: false` for runs
    predating the text-log writer."""
    p = safe_under(PREDICTIONS_DIR, path)
    if not p.is_file():
        raise HTTPException(404, "prediction file not found")
    log_path = PREDICTION_TEXT_LOGS_DIR / (p.stem + ".log")
    if not log_path.is_file():
        return {"path": str(log_path), "name": log_path.name, "exists": False, "raw": ""}
    return {
        "path": str(log_path),
        "name": log_path.name,
        "exists": True,
        "raw": log_path.read_text(encoding="utf-8", errors="replace"),
    }


@router.get("/api/results/prediction/trajectory")
def get_prediction_trajectory(path: str, instance_id: str = "") -> dict[str, Any]:
    """One instance's ATIF trajectory of a completed run
    (`<INFERENCE_INTERNAL_LOGS_DIR>/<stem>/<instance_id>/trajectory.json`),
    which the Results modal renders as agent cards + hand-off chips. `path`
    is the sibling prediction `.jsonl`; no `instance_id` means the run's
    first instance."""
    p = safe_under(PREDICTIONS_DIR, path)
    if not p.is_file():
        raise HTTPException(404, "prediction file not found")
    if instance_id in (".", "..") or "/" in instance_id or "\\" in instance_id:
        raise HTTPException(400, f"invalid instance id: {instance_id!r}")
    run_dir = INFERENCE_INTERNAL_LOGS_DIR / p.stem
    if not instance_id:
        files = sorted(run_dir.glob(f"*/{TRAJECTORY_FILE}"))
        docs = [_read_json(f) for f in files]
        ordered = next(
            (d["extra"]["run"].get("instance_ids") for d in docs
             if isinstance(d, dict) and isinstance((d.get("extra") or {}).get("run"), dict)),
            None,
        ) or [f.parent.name for f in files]
        instance_id = ordered[0] if ordered else ""
    target = run_dir / instance_id / TRAJECTORY_FILE
    doc = _read_json(target) if instance_id else None
    return {
        "path": str(target),
        "name": TRAJECTORY_FILE,
        "exists": doc is not None,
        "trajectory": doc,
    }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ─── Graphectory upload ──────────────────────────────────────────────────────
_PREDICTION_STEM_PREFIX = "prediction-"


@router.get("/api/results/graphectory")
def get_graphectory_status() -> dict[str, Any]:
    """Whether Graphectory is enabled: `GRAPHECTORY_URL` (the local Viewer)
    is set. The Results page names it in `missing` before anyone clicks."""
    viewer_url = graphectory.graphectory_base_url()
    return {
        "configured": bool(viewer_url),
        "url": viewer_url,
        "missing": [] if viewer_url else ["GRAPHECTORY_URL"],
    }


def _graphectory_prediction_path(path: str) -> Path:
    """Prediction `.jsonl` (traversal-checked). 404 when it is missing."""
    p = safe_under(PREDICTIONS_DIR, path)
    if not p.is_file():
        raise HTTPException(404, "prediction file not found")
    return p


def _run_log_dir(prediction: Path) -> Path:
    """The run's ATIF folder, `<INFERENCE_INTERNAL_LOGS_DIR>/<stem>/`."""
    return INFERENCE_INTERNAL_LOGS_DIR / prediction.stem


@router.post("/api/results/prediction/graphectory")
def upload_prediction_to_graphectory(payload: dict[str, str]) -> dict[str, Any]:
    """Publish a run's ATIF trajectories into the local Graphectory Viewer
    (`opendraco.utils.graphectory.publish_run`) and return one Viewer link
    per instance. `path` is the sibling prediction `.jsonl`. The links are
    also saved as `graphectory-links.json` in the run's folder.

    Waits until the Viewer lists every instance. Errors always carry a
    message in `detail`: 400 bad input, 404 no run folder / trajectories,
    500 the data folder is not writable, 502 the Viewer did not reload or
    list the run, 503 `GRAPHECTORY_URL` unset or invalid, 504 the Viewer is
    unreachable."""
    viewer_url = graphectory.graphectory_base_url()
    if not viewer_url:
        raise HTTPException(
            503, "Graphectory is not configured: set GRAPHECTORY_URL (e.g. "
                 "\"http://localhost:9610\") in opendraco/.env and restart the API",
        )
    path = payload.get("path") or ""
    if not path:
        raise HTTPException(400, "path is required")
    prediction = _graphectory_prediction_path(path)
    run_dir = _run_log_dir(prediction)
    if not run_dir.is_dir():
        raise HTTPException(
            404, f"run log folder {run_dir.name} not found - re-run inference to record one",
        )
    try:
        links = graphectory.publish_run(viewer_url, run_dir)
    except graphectory.GraphectoryError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    run_id = graphectory.safe_run_id(prediction.stem.removeprefix(_PREDICTION_STEM_PREFIX))
    return {"links": links, "run_id": run_id}


@router.get("/api/results/prediction/graphectory")
def get_saved_graphectory_link(path: str, instance_id: str = "") -> dict[str, Any]:
    """The link a past publish of this run saved for `instance_id`, or
    `{"graph": null}` when there is none, the file is unusable, Graphectory
    is not configured, or the link is on another Viewer than the current
    `GRAPHECTORY_URL` (saved before the setting changed: the run is treated
    as not published there yet). `path` is the prediction `.jsonl`."""
    prediction = _graphectory_prediction_path(path)
    viewer_url = graphectory.graphectory_base_url()
    if not viewer_url:
        return {"graph": None}
    try:
        saved = json.loads(
            (_run_log_dir(prediction) / graphectory.LINKS_FILE).read_text(encoding="utf-8"),
        )
    except (OSError, ValueError):
        return {"graph": None}
    links = saved.get("links") if isinstance(saved, dict) else None
    graph = links.get(instance_id) if isinstance(links, dict) else None
    if not isinstance(graph, str) or not graph:
        return {"graph": None}
    if not graphectory.is_on_viewer(graph, viewer_url):
        return {"graph": None}
    return {"graph": graph}


@router.get("/api/results/prediction/config")
def get_prediction_config(path: str) -> dict[str, Any]:
    """Snapshot of the unified-config JSON used to produce a prediction.
    Snapshots at `results/predictions/configs/<stem>.json` survive
    edits/renames of the source config."""
    p = safe_under(PREDICTIONS_DIR, path)
    if not p.is_file():
        raise HTTPException(404, "prediction file not found")
    cfg_path = PREDICTION_CONFIGS_DIR / (p.stem + ".json")
    if not cfg_path.is_file():
        return {"path": str(cfg_path), "name": cfg_path.name, "exists": False, "raw": ""}
    return {
        "path": str(cfg_path),
        "name": cfg_path.name,
        "exists": True,
        "raw": cfg_path.read_text(encoding="utf-8", errors="replace"),
    }


@router.get("/api/results/prediction/notebook")
def get_prediction_notebook(path: str, evaluator: str = "") -> Response:
    """Reproduce-this-run Jupyter notebook (.ipynb) for a prediction JSONL.
    Thin HTTP wrapper around `opendraco.utils.notebook.build_notebook_for_prediction`;
    passes the api-side config/instances paths so the env-overrideable
    `RESULTS_DIR` is honored. `evaluator` is the filename stem under
    `scripts/evaluation/` to bake into section 5 — required."""
    evaluator_stem = (evaluator or "").strip()
    if not evaluator_stem:
        raise HTTPException(400, "evaluator stem is required")
    p = safe_under(PREDICTIONS_DIR, path)
    try:
        run_id, notebook = build_notebook_for_prediction(
            p,
            configs_dir=PREDICTION_CONFIGS_DIR,
            instances_path=INSTANCES_PATH,
            evaluator=evaluator_stem,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, f"failed to read prediction file: {exc}") from exc
    body = json.dumps(notebook, indent=1)
    return Response(
        content=body,
        media_type="application/x-ipynb+json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="prediction-{run_id}.ipynb"'
            ),
        },
    )


# ─── Evaluation artefacts ────────────────────────────────────────────────────
@router.get("/api/results/evaluation")
def get_evaluation(dir: str) -> dict[str, Any]:
    """Return the parsed report.json + patch.diff for a per-instance evaluation dir."""
    base = (EVALUATION_DIR / "logs" / "run_evaluation").resolve()
    d = safe_under(base, dir)
    if not d.is_dir():
        raise HTTPException(404, "evaluation directory not found")
    report: dict[str, Any] = {}
    report_path = d / "report.json"
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
    patch = ""
    patch_path = d / "patch.diff"
    if patch_path.is_file():
        patch = patch_path.read_text(encoding="utf-8", errors="replace")
    # dir = .../logs/run_evaluation/<run_id>/<model>/<instance_id>
    run_dir = d.parent.parent
    model = d.parent.name
    run_id = run_dir.name
    summary_path = EVALUATION_DIR / f"{model}.{run_id}.json"
    return {
        "dir": str(d),
        "report": report,
        "patch": patch,
        "files": sorted(p.name for p in d.iterdir() if p.is_file()),
        "run_dir": str(run_dir),
        "summary_path": str(summary_path) if summary_path.is_file() else "",
    }


@router.post("/api/results/reveal")
def reveal_in_explorer(payload: dict[str, str]) -> dict[str, Any]:
    """Open the OS file explorer at a path. Files are highlighted in
    their parent folder; directories open in place. Restricted to
    `results/` to prevent revealing arbitrary system paths."""
    path = payload.get("path") or ""
    if not path:
        raise HTTPException(400, "path is required")
    p = safe_under(RESULTS_DIR, path)
    if not p.exists():
        raise HTTPException(404, f"path not found: {path}")
    if sys.platform.startswith("win"):
        if p.is_dir():
            subprocess.Popen(["explorer", str(p)])
        else:
            subprocess.Popen(["explorer", f"/select,{p}"])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(p)] if p.is_file() else ["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p) if p.is_dir() else str(p.parent)])
    return {"ok": True, "path": str(p)}


@router.get("/api/results/evaluation/zip")
def get_evaluation_zip(dir: str) -> Response:
    """Bundle a per-instance evaluation into a zip.
    Archive layout: `logs/<files…>` + `<model>.<run_id>.json` summary."""
    base = (EVALUATION_DIR / "logs" / "run_evaluation").resolve()
    d = safe_under(base, dir)
    if not d.is_dir():
        raise HTTPException(404, "evaluation directory not found")

    # dir = .../run_evaluation/<run_id>/<model>/<instance_id>
    run_id = d.parent.parent.name
    model = d.parent.name
    instance_id = d.name

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(d.iterdir()):
            if f.is_file():
                zf.write(f, arcname=f"logs/{f.name}")
        summary = EVALUATION_DIR / f"{model}.{run_id}.json"
        if summary.is_file():
            zf.write(summary, arcname=summary.name)
    buf.seek(0)

    archive_name = f"{instance_id}-{run_id}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{archive_name}"'},
    )


@router.get("/api/results/evaluation/log")
def get_evaluation_log(dir: str, name: str = "run_instance.log") -> dict[str, Any]:
    """Contents of a log file inside the evaluation dir. `name` defaults
    to `run_instance.log`; pass `test_output.txt` for the test log."""
    if name not in {"run_instance.log", "test_output.txt", "eval.sh", "patch.diff", "report.json"}:
        raise HTTPException(400, f"log '{name}' not allowed")
    base = (EVALUATION_DIR / "logs" / "run_evaluation").resolve()
    d = safe_under(base, dir)
    f = d / name
    if not f.is_file():
        raise HTTPException(404, f"log not found: {name}")
    return {"name": name, "content": f.read_text(encoding="utf-8", errors="replace")}
