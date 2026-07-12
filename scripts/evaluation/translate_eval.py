"""Translation-task evaluator (parallel to `scripts/evaluation/apply_and_test.py`).

Reads an instances JSONL + a predictions JSONL, applies each prediction
to a clean clone of the instance's repo, then for every file the patch
touches reads the post-patch content and the sidecar `<file>.gold` (the
human reference translation). Computes BLEU per file via sacrebleu
(falls back to a token-overlap score if sacrebleu isn't installed) and
declares the instance resolved when the corpus-BLEU clears
`--threshold` (default 50).

Output mirrors the SWE-bench harness shape used by
`apply_and_test.py` so `experiments/generate_report.py` can pick it up
without changes:

    <report-dir>/<model>.<run-id>.json   ← summary (resolved_ids etc.)
    <report-dir>/logs/run_evaluation/
        <run-id>/<model>/<instance>/
            eval.sh            ← reproducible BLEU re-run
            patch.diff         ← the prediction
            report.json        ← per-instance verdict + BLEU score
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# ────────────────────────────────────────────────────────────────────


def _bleu_sacrebleu(hyp: str, ref: str) -> float | None:
    """Corpus-BLEU via sacrebleu if available; None otherwise."""
    try:
        import sacrebleu  # type: ignore
    except ImportError:
        return None
    bleu = sacrebleu.corpus_bleu([hyp], [[ref]])
    return float(bleu.score)


def _bleu_fallback(hyp: str, ref: str) -> float:
    """Sentence-level BLEU-4 implemented inline so the eval still
    produces a score on hosts that don't have sacrebleu installed.

    Same n-gram precision (n=1..4) and brevity penalty as the
    canonical formula, just without the smoothing flourishes."""
    def _tokenize(s: str) -> list[str]:
        return re.findall(r"\w+|[^\w\s]", s.lower(), flags=re.UNICODE)

    hyp_toks = _tokenize(hyp)
    ref_toks = _tokenize(ref)
    if not hyp_toks or not ref_toks:
        return 0.0

    precisions: list[float] = []
    for n in (1, 2, 3, 4):
        hyp_ngrams = Counter(tuple(hyp_toks[i:i + n]) for i in range(len(hyp_toks) - n + 1))
        ref_ngrams = Counter(tuple(ref_toks[i:i + n]) for i in range(len(ref_toks) - n + 1))
        overlap = sum((hyp_ngrams & ref_ngrams).values())
        total = max(1, sum(hyp_ngrams.values()))
        precisions.append(overlap / total if total else 0.0)

    if any(p == 0 for p in precisions):
        log_p = sum(math.log(max(p, 1e-9)) for p in precisions) / 4
    else:
        log_p = sum(math.log(p) for p in precisions) / 4

    # Brevity penalty.
    bp = 1.0 if len(hyp_toks) > len(ref_toks) else math.exp(1 - len(ref_toks) / max(1, len(hyp_toks)))
    return float(bp * math.exp(log_p) * 100)


def bleu(hyp: str, ref: str) -> tuple[float, str]:
    """Returns `(score, backend)` where backend is `sacrebleu` or
    `fallback` so the caller can record which one ran."""
    score = _bleu_sacrebleu(hyp, ref)
    if score is not None:
        return score, "sacrebleu"
    return _bleu_fallback(hyp, ref), "fallback"


# ────────────────────────────────────────────────────────────────────


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _git(*args: str, cwd: Path) -> str:
    """Run git with the given args; raise on non-zero. Returns stdout."""
    return subprocess.check_output(
        ["git", *args], cwd=str(cwd), encoding="utf-8", errors="replace",
    )


def _clone(repo: str, commit: str, dst: Path) -> None:
    """Clone `repo` into `dst` and reset to `commit`. Supports
    `owner/name` (treated as GitHub) and full URLs."""
    if "://" not in repo and "@" not in repo:
        url = f"https://github.com/{repo}.git"
    else:
        url = repo
    _git("clone", "--quiet", url, str(dst), cwd=dst.parent)
    _git("checkout", "--quiet", commit, cwd=dst)


def _files_touched_by_patch(patch_str: str) -> list[str]:
    """Extract `+++ b/<path>` targets from a unified diff."""
    files: list[str] = []
    for line in patch_str.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[len("+++ b/"):].strip())
    # de-dup while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for f in files:
        if f not in seen and f != "/dev/null":
            seen.add(f)
            out.append(f)
    return out


# ────────────────────────────────────────────────────────────────────


def evaluate_one(
    instance: dict,
    prediction: dict,
    *,
    workdir: Path,
    threshold: float,
) -> dict:
    """Apply the patch, BLEU-score every touched file against its
    `.gold` sidecar, return a per-instance verdict dict."""
    iid = instance["instance_id"]
    repo_dir = workdir / iid
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if repo_dir.exists():
        # Re-use the clone if we already have it (idempotent re-runs).
        # `reset --hard` is the one that actually reverts tracked
        # modifications — `checkout <sha>` on the same sha is a no-op
        # and leaves a previously-applied patch in place, which then
        # makes the next `git apply` fail with "context mismatch"
        # because the file is already in the post-patch state.
        _git("reset", "--hard", instance["base_commit"], cwd=repo_dir)
        _git("clean", "-fdx", cwd=repo_dir)
    else:
        _clone(instance["repo"], instance["base_commit"], repo_dir)

    patch_str = prediction.get("model_patch") or prediction.get("patch") or ""
    per_file_scores: list[dict] = []
    backend_used = "n/a"

    # Catch null-ish placeholders + non-diff text before git apply, so
    # the verdict reads "no patch" instead of a confusing apply error.
    stripped = patch_str.strip()
    if not stripped or stripped.lower() in {"null", "none"} or "diff --git" not in stripped:
        return {
            "instance_id": iid,
            "resolved": False,
            "error": "empty patch" if not stripped else f"no-diff patch ({stripped[:40]!r})",
            "files": [],
            "bleu": 0.0,
            "backend": "n/a",
        }

    patch_path = repo_dir / ".translate_eval_patch.diff"
    patch_path.write_text(patch_str, encoding="utf-8", newline="\n")
    try:
        subprocess.check_call(
            ["git", "apply", "--whitespace=nowarn", str(patch_path)],
            cwd=str(repo_dir),
        )
    except subprocess.CalledProcessError as exc:
        return {
            "instance_id": iid,
            "resolved": False,
            "error": f"git apply failed (exit {exc.returncode})",
            "files": [],
            "bleu": 0.0,
            "backend": "n/a",
        }

    for rel in _files_touched_by_patch(patch_str):
        translated = repo_dir / rel
        gold = repo_dir / (rel + ".gold")
        if not translated.is_file():
            per_file_scores.append({"file": rel, "score": 0.0, "note": "post-patch file missing"})
            continue
        if not gold.is_file():
            per_file_scores.append({"file": rel, "score": 0.0, "note": "no .gold sidecar"})
            continue
        score, backend = bleu(translated.read_text(encoding="utf-8"), gold.read_text(encoding="utf-8"))
        backend_used = backend
        per_file_scores.append({"file": rel, "score": round(score, 2)})

    scored = [r["score"] for r in per_file_scores if "score" in r and r.get("note") is None]
    corpus_bleu = sum(scored) / len(scored) if scored else 0.0
    resolved = corpus_bleu >= threshold and bool(scored)
    return {
        "instance_id": iid,
        "resolved": resolved,
        "bleu": round(corpus_bleu, 2),
        "files": per_file_scores,
        "backend": backend_used,
        "threshold": threshold,
    }


# ────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="Translation-task evaluator (BLEU vs .gold sidecars).")
    ap.add_argument("--instances", required=True, help="Instances JSONL path.")
    ap.add_argument("--predictions", required=True, help="Predictions JSONL path.")
    ap.add_argument("--report-dir", required=True, help="Where to drop the SWE-bench-shaped report tree.")
    ap.add_argument("--run-id", required=True, help="Run identifier (e.g. notebook-translate-custom).")
    ap.add_argument("--model", default="evomas-translate", help="Model label baked into report filenames.")
    ap.add_argument("--threshold", type=float, default=50.0,
                    help="Corpus-BLEU resolved threshold (0-100; sacrebleu scale). Default 50.")
    ap.add_argument("--workdir", default=None,
                    help="Where to clone repos. Default: <report-dir>/_eval_repos.")
    args = ap.parse_args()

    instances = {row["instance_id"]: row for row in _read_jsonl(Path(args.instances))}
    predictions = _read_jsonl(Path(args.predictions))

    report_dir = Path(args.report_dir).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else (report_dir / "_eval_repos")
    workdir.mkdir(parents=True, exist_ok=True)
    log_root = report_dir / "logs" / "run_evaluation" / args.run_id / args.model
    log_root.mkdir(parents=True, exist_ok=True)

    resolved_ids: list[str] = []
    completed_ids: list[str] = []
    error_ids: list[str] = []
    per_instance: list[dict] = []

    for pred in predictions:
        iid = pred.get("instance_id")
        if iid is None or iid not in instances:
            print(f"  skip prediction (missing or unknown instance_id={iid!r})", file=sys.stderr)
            continue
        print(f"  -- {iid} --")
        try:
            verdict = evaluate_one(
                instances[iid], pred,
                workdir=workdir, threshold=args.threshold,
            )
        except Exception as exc:  # noqa: BLE001
            verdict = {"instance_id": iid, "resolved": False, "error": str(exc)}
            error_ids.append(iid)
            print(f"     ERROR: {exc}")

        completed_ids.append(iid)
        if verdict.get("resolved"):
            resolved_ids.append(iid)
            print(f"     RESOLVED  bleu={verdict.get('bleu')}")
        elif "error" not in verdict:
            print(f"     not resolved  bleu={verdict.get('bleu')}  threshold={args.threshold}")

        # Per-instance artefacts (SWE-bench-shape).
        inst_dir = log_root / iid
        inst_dir.mkdir(parents=True, exist_ok=True)
        (inst_dir / "patch.diff").write_text(pred.get("model_patch") or "", encoding="utf-8", newline="\n")
        (inst_dir / "report.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        (inst_dir / "eval.sh").write_text(
            f"#!/usr/bin/env bash\n"
            f"# Reproduce this instance's BLEU score.\n"
            f"python {Path(__file__).name} \\\n"
            f"  --instances {args.instances} \\\n"
            f"  --predictions {args.predictions} \\\n"
            f"  --report-dir {args.report_dir} \\\n"
            f"  --run-id {args.run_id} \\\n"
            f"  --model {args.model} \\\n"
            f"  --threshold {args.threshold}\n",
            encoding="utf-8", newline="\n",
        )
        per_instance.append(verdict)

    # Run-level summary that mirrors apply_and_test.py / SWE-bench harness.
    summary = {
        "run_id": args.run_id,
        "model": args.model,
        "evaluator": "scripts/evaluation/translate_eval.py",
        "threshold": args.threshold,
        "generated_at": datetime.now().isoformat(),
        "resolved_ids": sorted(set(resolved_ids)),
        "completed_ids": sorted(set(completed_ids)),
        "error_ids": sorted(set(error_ids)),
        "instances": per_instance,
    }
    summary_path = report_dir / f"{args.model}.{args.run_id}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nResolved {len(set(resolved_ids))}/{len(set(completed_ids))} instances "
          f"(threshold corpus-BLEU={args.threshold}).")
    print(f"Summary -> {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
