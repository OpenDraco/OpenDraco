"""Submit a predictions JSONL to the hosted SWE-bench leaderboards via `sb-cli`, as an alternative to the local Docker harness."""

# No `EVOMAS_EVALUATOR` manifest needed -- defaults (single_shot, no
# WSL) match this script: rows are grouped by (subset, split)
# INTERNALLY so the framework calls us once with the unified evaluator
# contract. See `docs/adding_a_new_problem.md`.

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SB_CLI_VENV = REPO_ROOT / "sb-cli" / "venv"

# Map evomas subset names to sb-cli dataset slugs. `full` is intentionally
# absent: the hosted API doesn't carry it, and we'd rather fail loudly than
# silently pick a different subset.
SUBSET_TO_SB_DATASET: dict[str, str] = {
    "lite":       "swe-bench_lite",
    "verified":   "swe-bench_verified",
    "multimodal": "swe-bench-m",
}


def _sb_cli_executable() -> str:
    """Locate the sb-cli entry-point: PATH, then the in-repo venv; skip the POSIX bin on Windows since CreateProcess can't run a shebang script (WinError 193)."""
    on_path = shutil.which("sb-cli")
    if on_path:
        return on_path
    win_exe = SB_CLI_VENV / "Scripts" / "sb-cli.exe"
    if win_exe.exists():
        return str(win_exe)
    posix_bin = SB_CLI_VENV / "bin" / "sb-cli"
    if posix_bin.exists() and os.name != "nt":
        return str(posix_bin)
    return "sb-cli"


def jsonl_to_json_list(predictions_jsonl: Path, out_json: Path) -> int:
    """Convert one-prediction-per-line JSONL to the JSON-list shape the hosted API accepts."""
    records: list[dict] = []
    with predictions_jsonl.open(encoding="utf-8") as f:
        for ln, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as e:
                raise ValueError(f"{predictions_jsonl}:{ln} is not valid JSON: {e}") from e
            if not isinstance(rec, dict) or "instance_id" not in rec:
                raise ValueError(
                    f"{predictions_jsonl}:{ln} missing required 'instance_id' field"
                )
            records.append(rec)
    out_json.write_text(json.dumps(records), encoding="utf-8")
    return len(records)


def run_remote_evaluation(
    predictions_path: str,
    run_id: str,
    subset: str,
    split: str,
    output_dir: str | None = None,
    overwrite: bool = False,
    gen_report: bool = True,
    instance_ids: str | None = None,
) -> int:
    pred_path = Path(predictions_path)
    if not pred_path.is_file():
        logger.error("predictions file not found: %s", pred_path)
        return 2
    if pred_path.stat().st_size == 0:
        logger.error(
            "predictions file is empty (0 bytes): %s\n"
            "Re-run `evomas run prediction --instances <instances.jsonl> "
            "--output %s --config <name>` to produce predictions before "
            "submitting.",
            pred_path, pred_path.name,
        )
        return 2

    if not os.environ.get("SWEBENCH_API_KEY"):
        logger.error(
            "SWEBENCH_API_KEY is not set. Generate one with "
            "`sb-cli gen-api-key your@email` and export it before running."
        )
        return 2

    dataset = SUBSET_TO_SB_DATASET.get(subset)
    if dataset is None:
        logger.error(
            "subset '%s' has no sb-cli equivalent. Pick one of: %s.",
            subset, sorted(SUBSET_TO_SB_DATASET),
        )
        return 2

    # sb-cli's `submit` reads JSON, not JSONL. `mkstemp` leaves the OS-level
    # fd open: on Windows the later `unlink()` would raise WinError 32
    # (ERROR_SHARING_VIOLATION) because our own process holds the file open.
    # Close the fd immediately; we only need the path.
    fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="evomas-preds-")
    os.close(fd)
    tmp_json = Path(tmp_path)
    try:
        n = jsonl_to_json_list(pred_path, tmp_json)
        if n == 0:
            logger.error(
                "no JSON records in %s (file has %d bytes but every line "
                "stripped to empty). Re-generate predictions and try again.",
                pred_path, pred_path.stat().st_size,
            )
            return 2
        logger.info(
            "Converted %d predictions from %s → %s (sb-cli JSON list).",
            n, pred_path.name, tmp_json.name,
        )

        sb_cli = _sb_cli_executable()
        cmd: list[str] = [
            sb_cli, "submit", dataset, split,
            "--predictions_path", str(tmp_json),
            "--run_id", run_id,
            "--gen_report", "1" if gen_report else "0",
            "--overwrite", "1" if overwrite else "0",
        ]
        if output_dir:
            cmd += ["--output_dir", output_dir]
        if instance_ids:
            cmd += ["--instance_ids", instance_ids]

        logger.info(
            "Submitting to sb-cli: subset=%s split=%s run_id=%s instances=%d "
            "(gen_report=%s, overwrite=%s)",
            dataset, split, run_id, n, gen_report, overwrite,
        )
        try:
            result = subprocess.run(cmd)
        except OSError as e:
            # WinError 193 fires when sb-cli resolved to a POSIX shebang
            # script (sb-cli built under WSL but invoked from Windows-side
            # Python). Install sb-cli into the host-native venv.
            logger.error(
                "Failed to execute sb-cli (%s). Install sb-cli into the "
                "active evomas venv so a native Windows entry-point "
                "exists:\n  pip install sb-cli",
                e,
            )
            return 2
        if result.returncode != 0:
            logger.error("sb-cli submit returned non-zero exit code %d", result.returncode)
        return result.returncode
    finally:
        tmp_json.unlink(missing_ok=True)


def _group_predictions(
    predictions_path: str,
    instances_path: str | None,
    subset_override: str | None,
    split_override: str | None,
) -> dict[tuple[str, str], list[str]]:
    """Group prediction rows by (subset, split). Per-row resolution:
    CLI override → row field → instances-cache lookup → ('lite','dev')."""
    inst_cache: dict[str, tuple[str, str]] = {}
    if instances_path:
        try:
            text = Path(instances_path).read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("could not open instances cache %s: %s", instances_path, exc)
            text = ""
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            iid = obj.get("instance_id")
            if iid:
                inst_cache[iid] = (
                    obj.get("subset") or "lite",
                    obj.get("split") or "dev",
                )

    buckets: dict[tuple[str, str], list[str]] = {}
    for raw in Path(predictions_path).read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        iid = obj.get("instance_id") or ""
        subset = subset_override or obj.get("subset") or inst_cache.get(iid, ("lite", "dev"))[0]
        split  = split_override  or obj.get("split")  or inst_cache.get(iid, ("lite", "dev"))[1]
        buckets.setdefault((subset, split), []).append(raw)
    return buckets


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Submit EvoMas predictions to the hosted SWE-bench leaderboards "
            "via sb-cli. Rows are grouped by (subset, split) internally -- "
            "one submission per bucket -- so the framework can call this "
            "script once with the unified evaluator contract."
        )
    )
    parser.add_argument(
        "--predictions",
        default="evomas_predictions.jsonl",
        help="Path to the JSONL predictions file.",
    )
    parser.add_argument(
        "--instances", default=None,
        help="Instances JSONL used to resolve subset/split for rows that "
             "don't carry them. Optional -- omit if every row already "
             "declares those fields or you pass --subset/--split overrides.",
    )
    parser.add_argument(
        "--model", default=None,
        help="Accepted for the unified evaluator contract; unused here.",
    )
    parser.add_argument(
        "--subset", choices=list(SUBSET_TO_SB_DATASET), default=None,
        help="Override per-row subset (forces every row into this bucket). "
             "lite | verified | multimodal -- 'full' has no hosted API split.",
    )
    parser.add_argument(
        "--split", choices=["dev", "test"], default=None,
        help="Override per-row split. 'test' is only available on lite / "
             "verified / multimodal subsets.",
    )
    parser.add_argument(
        "--run-id", default=None,
        help="Submission run-id base. Multi-bucket runs append "
             "-<subset>-<split>. Must be unique per bucket unless "
             "--overwrite is set.",
    )
    # Both flag spellings accepted: `--output-dir` (sb-cli native) and
    # `--report-dir` (unified evaluator contract). They resolve to the
    # same destination; whichever the caller passes wins.
    parser.add_argument(
        "--output-dir", "--report-dir", dest="output_dir", default=None,
        help="Where sb-cli writes the downloaded report. Accepts both "
             "--output-dir and --report-dir spellings.",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite an existing run-id's report on the server.",
    )
    parser.add_argument(
        "--no-gen-report", dest="gen_report", action="store_false",
        help="Skip the report-fetch step after submission - useful when "
             "submitting in batches and downloading reports later.",
    )
    parser.add_argument(
        "--instance-ids", default=None,
        help="Comma-separated subset of instance_ids to submit (default: all).",
    )
    parser.set_defaults(gen_report=True)
    args = parser.parse_args()

    buckets = _group_predictions(args.predictions, args.instances, args.subset, args.split)
    if not buckets:
        logger.error("No predictions found in %s", args.predictions)
        return 1

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_run_id = args.run_id or f"evomas-{ts}"
    output_dir = args.output_dir or "."
    tmp_dir = Path(output_dir) / "_tmp_predictions"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    return_codes: list[int] = []
    for (subset, split), lines in buckets.items():
        bucket_path = tmp_dir / f"_bucket_{subset}_{split}.jsonl"
        bucket_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        bucket_run_id = (
            f"{base_run_id}-{subset}-{split}" if len(buckets) > 1 else base_run_id
        )
        logger.info(
            "Remote bucket %s/%s -> %d row(s), run_id=%s",
            subset, split, len(lines), bucket_run_id,
        )
        rc = run_remote_evaluation(
            str(bucket_path), bucket_run_id, subset, split,
            args.output_dir, args.overwrite, args.gen_report, args.instance_ids,
        )
        return_codes.append(rc)
    return max(return_codes) if return_codes else 0


if __name__ == "__main__":
    sys.exit(main())
