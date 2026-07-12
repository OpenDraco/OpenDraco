"""Evaluator for websearch / ad-hoc question-answer tasks.

Unlike `apply_and_test.py`, this evaluator doesn't try to clone a repo or
run pytest — the agent's deliverable is a saved answer file (via
`save_text`), not a code patch. The schema is the same SWE-bench-shaped
shell so `experiments/generate_report.py` picks it up, but the verdict
fields are filled in from "did the agent actually run + write something"
signals rather than test outcomes.

Resolved criterion (per instance):
   The agent must have written an `answer*.md` file (or any
   `*<instance_id>*.md`) somewhere reachable from the run's output
   dir. This is the deliverable websearch tasks specify in their
   problem statement (e.g. "Write the answer to ./answer-py.md"); a
   model_patch alone is no longer enough — the file must actually
   exist on disk after the agent runs.

The CLI surface matches the unified evaluator contract used by
`api/routers/evaluation.py` and the notebook generator's section 5 —
`--predictions / --instances / --report-dir / --run-id / --model`.
"""
from __future__ import annotations

# OPTIONAL manifest — defaults (no WSL, single_shot) match this script.
EVOMAS_EVALUATOR = {"needs_wsl": False}

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _find_answer_file(report_dir: Path, instance_id: str) -> Path | None:
    """Search likely locations for an `answer-*.md` (or any *.md) that the
    websearch agent saved via `save_text`. Walks the report-dir, the
    project CWD, the user's home dir, and `C:\\Users\\Public`."""
    candidates: list[Path] = []
    haystacks = [report_dir, Path.cwd(), Path.home()]
    pub = Path("C:/Users/Public")
    if pub.is_dir():
        haystacks.append(pub)
    for root in haystacks:
        try:
            candidates.extend(root.glob("answer*.md"))
            candidates.extend(root.glob(f"*{instance_id}*.md"))
        except OSError:
            continue
    candidates = [p for p in candidates if p.is_file()]
    return max(candidates, key=lambda p: p.stat().st_mtime, default=None)


def evaluate_one(
    instance: dict[str, Any],
    prediction: dict[str, Any],
    *,
    report_dir: Path,
) -> dict[str, Any]:
    iid = instance["instance_id"]
    patch = prediction.get("model_patch")
    has_patch = bool(patch and patch.strip())
    answer = _find_answer_file(report_dir, iid)
    has_answer = answer is not None

    resolved = has_answer
    return {
        "instance_id": iid,
        "resolved": resolved,
        "patch_present": has_patch,
        "patch_chars": len(patch or ""),
        "answer_file": str(answer) if answer else None,
        "answer_chars": answer.stat().st_size if answer else 0,
        "criterion": "answer_file_found",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Websearch / ad-hoc QA evaluator.")
    ap.add_argument("--instances", required=True, help="Instances JSONL.")
    ap.add_argument("--predictions", required=True, help="Predictions JSONL.")
    ap.add_argument("--report-dir", required=True, help="Where to drop the report tree.")
    ap.add_argument("--run-id", required=True, help="Run identifier baked into report filenames.")
    ap.add_argument("--model", default="evomas-websearch", help="Model label baked into report filenames.")
    args = ap.parse_args()

    instances = {row["instance_id"]: row for row in _read_jsonl(Path(args.instances))}
    predictions = _read_jsonl(Path(args.predictions))

    report_dir = Path(args.report_dir).resolve()
    log_root = report_dir / "logs" / "run_evaluation" / args.run_id / args.model
    log_root.mkdir(parents=True, exist_ok=True)

    resolved_ids: list[str] = []
    completed_ids: list[str] = []
    error_ids: list[str] = []
    per_instance: list[dict[str, Any]] = []

    for pred in predictions:
        iid = pred.get("instance_id")
        if iid is None or iid not in instances:
            print(f"  skip prediction (unknown instance_id={iid!r})", file=sys.stderr)
            continue
        print(f"  -- {iid} --")
        try:
            verdict = evaluate_one(instances[iid], pred, report_dir=report_dir)
        except Exception as exc:  # noqa: BLE001
            verdict = {"instance_id": iid, "resolved": False, "error": str(exc)}
            error_ids.append(iid)
            print(f"     ERROR: {exc}")
            per_instance.append(verdict)
            continue

        completed_ids.append(iid)
        if verdict["resolved"]:
            resolved_ids.append(iid)
            ans = verdict.get("answer_file") or f"patch={verdict['patch_chars']}B"
            print(f"     RESOLVED  {ans}")
        else:
            print(f"     not resolved  (no patch, no answer file found)")

        inst_dir = log_root / iid
        inst_dir.mkdir(parents=True, exist_ok=True)
        (inst_dir / "patch.diff").write_text(pred.get("model_patch") or "", encoding="utf-8", newline="\n")
        (inst_dir / "report.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        per_instance.append(verdict)

    summary = {
        "run_id": args.run_id,
        "model": args.model,
        "evaluator": "scripts/evaluation/websearch_eval.py",
        "generated_at": datetime.now().isoformat(),
        "resolved_ids": sorted(set(resolved_ids)),
        "completed_ids": sorted(set(completed_ids)),
        "error_ids": sorted(set(error_ids)),
        "instances": per_instance,
    }
    summary_path = report_dir / f"{args.model}.{args.run_id}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nResolved {len(set(resolved_ids))}/{len(set(completed_ids))} instances "
          f"(criterion: patch_present OR answer_file_found).")
    print(f"Summary -> {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
