"""Pure helpers over prediction JSONLs + evaluation report dirs.

Used by the api Results page aggregation and the Evaluation router's
partitioning logic. No FastAPI dependency — every function takes the
directory paths it needs explicitly, so the CLI / tests / notebook
generator can reuse them.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from evomas.utils.instances import instance_origin_lookup


_TS_RE = re.compile(r"-(\d{14})(?:\.|$)")
_PRED_KEY_RE = re.compile(r"^prediction-(.+)\.jsonl$")
_EVAL_KEY_RE = re.compile(r"^evaluation-(.+)$")


# ─── (subset, split) partitioning for the eval worker ───────────────────────
def partition_predictions(
    path: Path,
    instances_path: Path,
) -> dict[tuple[str, str], list[str]]:
    """Group JSONL lines by (subset, split). Resolution per line: row's
    own subset/split fields, then the instances cache (looked up by
    instance_id), then `("lite", "dev")`."""
    origin = instance_origin_lookup(instances_path)
    out: dict[tuple[str, str], list[str]] = {}
    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        subset = obj.get("subset")
        split = obj.get("split")
        if not subset or not split:
            cached = origin.get(obj.get("instance_id") or "")
            if cached:
                subset = subset or cached[0]
                split = split or cached[1]
        subset = subset or "lite"
        split = split or "dev"
        out.setdefault((subset, split), []).append(raw)
    return out


def derive_run_id_base(pred_path: Path) -> str:
    """`<config>-<UID>` from a prediction filename, else a timestamp."""
    m = re.match(r"^prediction-(.+)\.jsonl$", pred_path.name)
    if m:
        return m.group(1)
    return f"adhoc-{datetime.now().strftime('%Y%m%d%H%M%S')}"


# ─── Per-instance scan + pair (Results-page aggregation) ────────────────────
def scan_predictions(predictions_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Group every prediction JSONL line by `instance_id` so multi-instance
    files surface as one entry per instance. Returns
    `{instance_id: [{path, name, instance_id, run_id, mtime}, …]}`."""
    out: dict[str, list[dict[str, Any]]] = {}
    for p in predictions_dir.glob("*.jsonl"):
        try:
            text = p.read_text(encoding="utf-8")
            mtime = p.stat().st_mtime
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            iid = obj.get("instance_id")
            if not isinstance(iid, str) or not iid:
                continue
            out.setdefault(iid, []).append({
                "path": str(p),
                "name": p.name,
                "instance_id": iid,
                "run_id": obj.get("run_id"),
                "mtime": mtime,
            })
    for files in out.values():
        files.sort(key=lambda f: f["mtime"], reverse=True)
    return out


def scan_evaluations(evaluation_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Group per-instance evaluation dirs by instance_id.
    Layout: `<evaluation_dir>/logs/run_evaluation/<run_id>/<model>/<instance_id>/`."""
    out: dict[str, list[dict[str, Any]]] = {}
    base = evaluation_dir / "logs" / "run_evaluation"
    if not base.is_dir():
        return out
    for run_dir in base.iterdir():
        if not run_dir.is_dir():
            continue
        for model_dir in run_dir.iterdir():
            if not model_dir.is_dir():
                continue
            for inst_dir in model_dir.iterdir():
                if not inst_dir.is_dir():
                    continue
                iid = inst_dir.name
                out.setdefault(iid, []).append({
                    "run_id": run_dir.name,
                    "model": model_dir.name,
                    "dir": str(inst_dir),
                    "mtime": inst_dir.stat().st_mtime,
                })
    for entries in out.values():
        entries.sort(key=lambda e: e["mtime"], reverse=True)
    return out


def key_of_pred(pred: dict[str, Any]) -> str | None:
    """Pairing key from a prediction's `run_id` (preferred) or filename
    (`prediction-<config>-<UID>.jsonl` → `<config>-<UID>`; legacy
    `<id>-<TS>.jsonl` → `<TS>`)."""
    rid = pred.get("run_id")
    if isinstance(rid, str) and rid:
        return rid
    name = pred.get("name", "")
    m = _PRED_KEY_RE.match(name)
    if m:
        return m.group(1)
    m = _TS_RE.search(name)
    return m.group(1) if m else None


def key_of_eval(ev: dict[str, Any]) -> str | None:
    """Pairing key from an evaluation's run_id
    (`evaluation-<config>-<UID>` → `<config>-<UID>`; legacy
    `evomas-<split>-<TS>` → `<TS>`)."""
    run_id = ev.get("run_id", "")
    m = _EVAL_KEY_RE.match(run_id)
    if m:
        return m.group(1)
    m = _TS_RE.search(run_id)
    return m.group(1) if m else None


def pair_runs(
    preds: list[dict[str, Any]],
    evals: list[dict[str, Any]],
    instance_id: str,
) -> list[dict[str, Any]]:
    """Pair predictions + evaluations on a shared `<config>-<UID>` key.
    Orphan evaluations come through as run entries with `prediction=None`
    so the UI dropdown still surfaces them."""
    runs: list[dict[str, Any]] = []
    used_eval_dirs: set[str] = set()

    for pred in preds:
        key = key_of_pred(pred)
        match = next(
            (e for e in evals if key is not None and key_of_eval(e) == key),
            None,
        )
        if match:
            used_eval_dirs.add(match["dir"])
        runs.append({
            "run_id": key or pred.get("name", ""),
            "key": key,
            "prediction": pred,
            "evaluation": match,
            "mtime": pred.get("mtime", 0),
        })

    for ev in evals:
        if ev["dir"] in used_eval_dirs:
            continue
        key = key_of_eval(ev)
        runs.append({
            "run_id": ev.get("run_id") or "",
            "key": key,
            "prediction": None,
            "evaluation": ev,
            "mtime": ev.get("mtime", 0),
        })

    runs.sort(key=lambda r: r.get("mtime", 0), reverse=True)
    return runs


def expand_hierarchy(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Add the implied Full membership for each Lite/Verified row
    (`lite/X` ⊆ `full/X`, `verified/test` ⊆ `full/test`). One-way:
    a `full/X` row doesn't imply Lite — the cache can't tell."""
    expanded = list(pairs)
    seen = set(pairs)
    for subset, split in pairs:
        if subset in ("lite", "verified"):
            parent = ("full", split)
            if parent not in seen:
                expanded.append(parent)
                seen.add(parent)
    return expanded
