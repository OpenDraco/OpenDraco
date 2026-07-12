"""Read a SWE-bench-style instances JSONL into a list of dicts. Lives under
`evomas.utils` so reproduce-this-run notebooks can import it from anywhere."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_instances(
    instances_path: str | Path,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """JSONL → list of dicts."""
    path = Path(instances_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Instances file not found: {instances_path}\n"
            f"Generate it first with: evomas run instances --output {instances_path}"
        )
    instances: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                instances.append(json.loads(line))
    if limit is not None and limit > 0:
        instances = instances[:limit]
    return instances


def instance_memberships(instances_path: Path) -> dict[str, list[tuple[str, str]]]:
    """`instance_id -> [(subset, split), …]`. An id can appear under
    multiple pairs (lite/dev AND full/dev after both subsets refresh)."""
    out: dict[str, list[tuple[str, str]]] = {}
    if not instances_path.exists():
        return out
    for raw in instances_path.read_text(encoding="utf-8").splitlines():
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
        pair = (obj.get("subset") or "lite", obj.get("split") or "dev")
        memberships = out.setdefault(iid, [])
        if pair not in memberships:
            memberships.append(pair)
    return out


def instance_origin_lookup(instances_path: Path) -> dict[str, tuple[str, str]]:
    """First (subset, split) per id — for callers that need one canonical pair."""
    mems = instance_memberships(instances_path)
    return {iid: pairs[0] for iid, pairs in mems.items()}


def load_instance_rows(
    instance_ids: set[str] | list[str],
    instances_path: Path,
) -> dict[str, dict[str, Any]]:
    """`instance_id -> full row` for every match (eval worker sidecar)."""
    wanted = set(instance_ids)
    out: dict[str, dict[str, Any]] = {}
    if not wanted or not instances_path.exists():
        return out
    with instances_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            iid = obj.get("instance_id")
            if iid in wanted:
                out[iid] = obj
                if len(out) == len(wanted):
                    break
    return out


SUBSET_DATASETS: dict[str, str] = {
    "lite":     "SWE-bench/SWE-bench_Lite",
    "full":     "SWE-bench/SWE-bench",
    "verified": "SWE-bench/SWE-bench_Verified",
}


def fetch_swebench_instances(
    subset: str,
    split: str,
    instance_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Pull a SWE-bench (subset, split) fresh from HuggingFace. With
    `instance_ids` set, filter to just those — keeps a single-instance
    notebook from materialising the whole ~2000-row split.

    Rows come annotated with `subset` + `split` so the runner / eval
    worker can partition them the same way the local cache would.

    `datasets` is imported lazily so a CLI that never calls this
    function (e.g. the custom-repo branch) doesn't pay the HF startup
    cost or require the package to be installed."""
    if subset not in SUBSET_DATASETS:
        raise ValueError(
            f"unknown subset {subset!r}; expected one of {sorted(SUBSET_DATASETS)}"
        )
    from datasets import load_dataset  # type: ignore[import-untyped]
    ds = load_dataset(SUBSET_DATASETS[subset])
    if split not in ds:
        raise ValueError(f"split {split!r} not in dataset {SUBSET_DATASETS[subset]!r}")
    wanted = set(instance_ids) if instance_ids else None
    rows: list[dict[str, Any]] = []
    for item in ds[split]:
        obj = dict(item)
        if wanted is not None and obj.get("instance_id") not in wanted:
            continue
        obj["subset"] = subset
        obj["split"] = split
        rows.append(obj)
        if wanted is not None and len(rows) == len(wanted):
            break
    return rows
