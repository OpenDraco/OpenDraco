"""Convert a `notebooks/notebook-X-raw/` consolidated run dir into the
`experiments/notebook-X-suffix/` layout that `generate_report.py` expects.

Notebook runs write one `prediction-<run>.jsonl` (N lines) and one
`inference.log` per run. The report generator expects per-instance
`predictions/prediction-<run>-<iid_hash>.jsonl` (1 line each) plus
matching `predictions/logs/prediction-<run>-<iid_hash>.log` slices
and one `evaluations/<summary>.json`. This script does the split.

Usage:
    python experiments/split_notebook_run.py <src-notebook-dir> <dst-name>

The dst dir is created under `experiments/` if missing. Existing files
inside the dst are left alone — re-running is a no-op for already-split
runs.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

EXPERIMENTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXPERIMENTS_DIR.parent

_INSTANCE_START_RE = re.compile(r"===\s+running\s+(?P<iid>\S+)\s+with")
_INSTANCE_DONE_RE = re.compile(r"===\s+(?P<iid>\S+)\s+done:")


def _iid_hash(iid: str) -> str:
    # `custom-EvoMas-evomas-instance-trivial-18757fd` -> `18757fd`
    # `marshmallow-code__marshmallow-1359`            -> `1359`
    tail = iid.rsplit("-", 1)[-1]
    return tail


def _split_log(log_path: Path, out_dir: Path, run_stem: str) -> dict[str, int]:
    """Slice inference.log into per-instance segments using the
    `=== running <iid> with` / `=== <iid> done:` markers. Returns
    a count of lines written per instance."""
    if not log_path.is_file():
        return {}
    counts: dict[str, int] = {}
    current: list[str] | None = None
    current_iid: str | None = None
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True):
        m_start = _INSTANCE_START_RE.search(line)
        if m_start:
            if current is not None and current_iid is not None:
                _flush(current, current_iid, out_dir, run_stem, counts)
            current_iid = m_start.group("iid")
            current = [line]
            continue
        if current is not None:
            current.append(line)
        m_done = _INSTANCE_DONE_RE.search(line)
        if m_done and current is not None and current_iid is not None:
            _flush(current, current_iid, out_dir, run_stem, counts)
            current = None
            current_iid = None
    # Tail (no done line)
    if current is not None and current_iid is not None:
        _flush(current, current_iid, out_dir, run_stem, counts)
    return counts


def _flush(lines: list[str], iid: str, out_dir: Path, run_stem: str, counts: dict[str, int]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"prediction-{run_stem}-{_iid_hash(iid)}.log"
    target.write_text("".join(lines), encoding="utf-8", newline="")
    counts[iid] = len(lines)


def split_run(src: Path, dst_name: str) -> None:
    if not src.is_dir():
        print(f"!! src not a dir: {src}")
        sys.exit(2)

    dst = EXPERIMENTS_DIR / dst_name
    if dst.exists():
        print(f"!! dst already exists, skipping: {dst}")
        return

    # Locate the consolidated prediction.jsonl + inference.log + summary json.
    pred_files = list(src.glob("prediction-*.jsonl"))
    log_files = list(src.glob("inference.log"))
    summary_files = list(src.glob("*.json"))
    if not pred_files or not log_files:
        print(f"!! missing prediction-*.jsonl or inference.log in {src}")
        sys.exit(3)
    pred_path = pred_files[0]
    log_path = log_files[0]
    run_stem = pred_path.stem.removeprefix("prediction-")

    dst.mkdir(parents=True)
    preds_dir = dst / "predictions"
    preds_dir.mkdir()
    logs_dir = preds_dir / "logs"
    logs_dir.mkdir()
    evals_dir = dst / "evaluations"
    evals_dir.mkdir()

    # Per-instance predictions
    rows = [json.loads(line) for line in pred_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        iid = row["instance_id"]
        target = preds_dir / f"prediction-{run_stem}-{_iid_hash(iid)}.jsonl"
        target.write_text(json.dumps(row) + "\n", encoding="utf-8", newline="\n")
    print(f"  split {len(rows)} predictions -> {preds_dir}")

    # Per-instance log slices
    counts = _split_log(log_path, logs_dir, run_stem)
    print(f"  split log into {len(counts)} instance slices")

    # Copy eval summary(ies) over
    for sjson in summary_files:
        shutil.copy2(sjson, evals_dir / sjson.name)
    print(f"  copied {len(summary_files)} summary json(s)")

    # Copy the source .ipynb to the top of the experiments dir so the
    # notebook travels with its data (and EXPERIMENT.md readers can jump
    # straight to "how was this run produced"). The matching file is
    # `notebooks/<dst_name without "notebook-" prefix>.ipynb`.
    nb_name = dst_name.removeprefix("notebook-") + ".ipynb"
    nb_src = REPO_ROOT / "notebooks" / nb_name
    if nb_src.is_file():
        shutil.copy2(nb_src, dst / nb_name)
        print(f"  copied {nb_name}")
    else:
        print(f"  (no notebook found at notebooks/{nb_name} — skipped)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python experiments/split_notebook_run.py <src-notebook-dir> <dst-name>")
        sys.exit(1)
    src = Path(sys.argv[1]).resolve()
    dst_name = sys.argv[2]
    split_run(src, dst_name)
