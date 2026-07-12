import argparse
import json
import logging
import re
import subprocess
from pathlib import Path

# `datasets` (HuggingFace) is imported lazily inside `build_instances` so the
# custom-repo branch can run on environments missing pandas/dateutil/etc.

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SUBSET_DATASETS: dict[str, str] = {
    "lite":     "SWE-bench/SWE-bench_Lite",
    "full":     "SWE-bench/SWE-bench",
    "verified": "SWE-bench/SWE-bench_Verified",
}


def build_instances(
    split_name: str,
    output_path: str,
    limit: int | None = None,
    subset: str = "lite",
    append: bool = False,
) -> int:
    """Pull instances from HuggingFace and write one JSONL line per item, annotated with `subset` and `split` so the UI can group them; with `append=True`, other (subset, split) pairs are preserved."""
    if subset not in SUBSET_DATASETS:
        raise ValueError(
            f"unknown subset {subset!r}; expected one of {sorted(SUBSET_DATASETS)}"
        )
    from datasets import load_dataset  # lazy: HF deps not needed on --custom-repo
    ds = load_dataset(SUBSET_DATASETS[subset])
    if split_name not in ds:
        raise ValueError(f"split {split_name!r} not in dataset {SUBSET_DATASETS[subset]!r}")
    instances = ds[split_name]
    if limit is not None and limit > 0:
        instances = instances.select(range(min(limit, len(instances))))

    out = Path(output_path)
    surviving: list[str] = []
    if append and out.exists():
        # Drop pre-existing lines for the same (subset, split); we're about to re-fetch them.
        for raw in out.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                surviving.append(raw)
                continue
            same_subset = (obj.get("subset", "lite") == subset)
            same_split = (obj.get("split", "dev") == split_name)
            if same_subset and same_split:
                continue
            surviving.append(raw)

    with out.open("w", encoding="utf-8") as f:
        for raw in surviving:
            f.write(raw + "\n")
        for item in instances:
            obj = dict(item)
            obj["subset"] = subset
            obj["split"] = split_name
            f.write(json.dumps(obj) + "\n")

    return len(instances)


# ─── Custom-repo branch ───────────────────────────────────────────────────────
# Mirrors the row shape produced by api/server.py:/api/instances/custom so a
# CLI-added instance is interchangeable with an API-added one.
_GITHUB_URL_RE = re.compile(r"^(?:https?://github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def _parse_github_repo(repo: str) -> tuple[str, str]:
    """Accept 'owner/name' or a full GitHub URL; return (owner, name)."""
    m = _GITHUB_URL_RE.match(repo.strip())
    if not m:
        raise ValueError(f"--custom-repo must be 'owner/name' or a GitHub URL, got {repo!r}")
    return m.group(1), m.group(2)


def _resolve_head(owner: str, name: str) -> str:
    """Look up the remote HEAD SHA via `git ls-remote`."""
    url = f"https://github.com/{owner}/{name}.git"
    proc = subprocess.run(
        ["git", "ls-remote", url, "HEAD"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git ls-remote failed for {url} (rc={proc.returncode}): "
            f"{(proc.stderr or proc.stdout or '').strip()}"
        )
    line = (proc.stdout or "").strip().splitlines()[0] if proc.stdout else ""
    sha = line.split()[0] if line else ""
    if not sha:
        raise RuntimeError(f"git ls-remote {url} HEAD returned no SHA")
    return sha


def _append_custom_row(
    output_path: str,
    repo: str,
    base_commit: str | None,
    problem_statement: str,
    instance_id: str | None,
) -> dict:
    """Build and append one custom-repo row to the JSONL (idempotent on instance_id)."""
    owner, name = _parse_github_repo(repo)
    sha = base_commit.strip() if base_commit else _resolve_head(owner, name)
    iid = instance_id or f"custom-{owner}-{name}-{sha[:7]}"
    row = {
        "repo": f"{owner}/{name}",
        "instance_id": iid,
        "base_commit": sha,
        "problem_statement": problem_statement,
        "hints_text": "",
        "subset": "custom",
        "split": "custom",
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    surviving: list[str] = []
    if out.exists():
        for raw in out.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                surviving.append(raw)
                continue
            if obj.get("instance_id") == iid:
                continue
            surviving.append(raw)
    with out.open("w", encoding="utf-8") as f:
        for raw in surviving:
            f.write(raw + "\n")
        f.write(json.dumps(row) + "\n")
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", choices=list(SUBSET_DATASETS), default="lite",
                        help="SWE-bench subset to pull (default: lite)")
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--output", default="swebench_instances.jsonl")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N instances (smoke test)")
    parser.add_argument("--append", action="store_true",
                        help="Keep existing lines for other (subset, split) pairs.")
    # --custom-repo skips the HuggingFace pull and appends one synthetic
    # 'custom' row matching the /api/instances/custom schema.
    parser.add_argument("--custom-repo", default="",
                        help="GitHub 'owner/name' or URL. Switches to custom-repo mode "
                             "(skips the HuggingFace pull; appends one row).")
    parser.add_argument("--custom-problem", default="",
                        help="Problem statement for the custom row. Required when "
                             "--custom-repo is set.")
    parser.add_argument("--custom-base-commit", default="",
                        help="Base commit SHA for the custom row. Defaults to the remote "
                             "HEAD via `git ls-remote` when omitted.")
    parser.add_argument("--custom-instance-id", default="",
                        help="Instance id for the custom row. Defaults to "
                             "'custom-<owner>-<name>-<sha[:7]>' when omitted.")
    args = parser.parse_args()

    if args.custom_repo:
        if not args.custom_problem:
            parser.error("--custom-problem is required when --custom-repo is set.")
        logger.info("Appending custom-repo instance for %s -> %s",
                    args.custom_repo, args.output)
        row = _append_custom_row(
            args.output,
            args.custom_repo,
            args.custom_base_commit or None,
            args.custom_problem,
            args.custom_instance_id or None,
        )
        logger.info(
            "Wrote custom row instance_id=%s base_commit=%s -> %s",
            row["instance_id"], row["base_commit"][:8], args.output,
        )
        return

    logger.info(
        "Generating instances subset=%s split=%s limit=%s append=%s",
        args.subset, args.split, args.limit, args.append,
    )
    total = build_instances(args.split, args.output, args.limit,
                            subset=args.subset, append=args.append)
    logger.info("Generated %d instances → %s", total, args.output)


if __name__ == "__main__":
    main()
