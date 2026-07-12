"""Inference-page instance-picker endpoints — manage the local
`swebench_instances.jsonl` cache (count, refresh from HuggingFace, append
custom GitHub repos)."""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.common import INSTANCES_PATH

router = APIRouter()


@router.get("/api/instances/count")
def count_instances() -> dict:
    if not INSTANCES_PATH.exists():
        return {"count": 0}
    count = sum(1 for line in INSTANCES_PATH.open(encoding="utf-8") if line.strip())
    return {"count": count}


@router.post("/api/instances/refresh-all")
def refresh_all_instances(limit: int | None = None) -> dict:
    """Pull every known SWE-bench (subset, split) pair. Heavy — Full
    alone is ~2000 instances per split."""
    from scripts.generate_swebench_instances import build_instances
    combos = [
        ("lite", "dev"), ("lite", "test"),
        ("full", "dev"), ("full", "test"), ("full", "train"),
        ("verified", "test"),
    ]
    results: dict[str, Any] = {}
    total = 0
    for subset, split in combos:
        try:
            count = build_instances(
                split, str(INSTANCES_PATH), limit,
                subset=subset, append=True,
            )
            results[f"{subset}/{split}"] = {"count": count}
            total += count
        except Exception as exc:
            results[f"{subset}/{split}"] = {"error": str(exc)}
    return {"total": total, "results": results}


@router.post("/api/instances/refresh")
def refresh_instances(
    split: str = "dev",
    limit: int | None = None,
    subset: str = "lite",
    append: bool = True,
) -> dict:
    """Regenerate the JSONL for one (subset, split) pair. With `append=True`
    other pairs already in the file are preserved."""
    if split not in {"dev", "test", "train"}:
        raise HTTPException(400, f"split must be 'dev' | 'test' | 'train' (got {split!r})")
    if subset not in {"lite", "full", "verified"}:
        raise HTTPException(400, f"subset must be 'lite' | 'full' | 'verified' (got {subset!r})")
    from scripts.generate_swebench_instances import build_instances
    try:
        count = build_instances(
            split, str(INSTANCES_PATH), limit,
            subset=subset, append=append,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"count": count, "subset": subset, "split": split, "path": str(INSTANCES_PATH)}


class AddCustomInstanceRequest(BaseModel):
    repo: str
    problem_statement: str
    base_commit: str | None = None


_CUSTOM_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@router.post("/api/instances/custom")
def add_custom_instance(req: AddCustomInstanceRequest) -> dict:
    """Append a user-provided GitHub repo to the JSONL. Marked
    `subset=split="custom"` so the SWE-bench harness skips it
    (harness needs test_patch / FAIL_TO_PASS, which a free-form repo
    doesn't carry — `apply_and_test.py` handles these instead)."""
    repo = req.repo.strip()
    # Accept either `owner/name` or a full GitHub URL.
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if repo.startswith(prefix):
            repo = repo[len(prefix):]
    if repo.endswith(".git"):
        repo = repo[:-4]
    repo = repo.rstrip("/")
    if not _CUSTOM_REPO_RE.match(repo):
        raise HTTPException(400, f"repo must be owner/name (got {req.repo!r})")
    problem = (req.problem_statement or "").strip()
    if not problem:
        raise HTTPException(400, "problem_statement is required")

    # Resolve base_commit via ls-remote when the client didn't pin one.
    base_commit = (req.base_commit or "").strip()
    if not base_commit:
        # Force non-interactive: on Windows, hitting a private/missing repo
        # otherwise opens the Git Credential Manager GUI and deadlocks.
        env = {**os.environ,
               "GIT_TERMINAL_PROMPT": "0",
               "GCM_INTERACTIVE": "Never",
               "GIT_ASKPASS": "echo"}
        try:
            out = subprocess.run(
                ["git", "ls-remote", f"https://github.com/{repo}", "HEAD"],
                capture_output=True, text=True, timeout=10, check=True,
                stdin=subprocess.DEVNULL, env=env,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            stderr = getattr(exc, "stderr", "") or str(exc)
            raise HTTPException(502, f"failed to resolve HEAD for {repo}: {stderr[:300]}") from exc
        first = (out.stdout or "").split("\n", 1)[0].strip()
        base_commit = first.split("\t", 1)[0].strip()
        if not re.match(r"^[0-9a-f]{7,40}$", base_commit):
            raise HTTPException(502, f"could not parse HEAD SHA from `git ls-remote` output: {out.stdout[:200]!r}")
    if not re.match(r"^[0-9a-f]{4,40}$", base_commit):
        raise HTTPException(400, f"base_commit doesn't look like a git SHA: {base_commit!r}")

    owner, name = repo.split("/", 1)
    instance_id = f"custom-{owner}-{name}-{base_commit[:7]}"

    # Idempotent on (repo, base_commit) — surface the existing row if any.
    if INSTANCES_PATH.exists():
        with INSTANCES_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("instance_id") == instance_id:
                    return {
                        "instance_id": instance_id,
                        "repo": repo,
                        "base_commit": base_commit,
                        "duplicate": True,
                    }

    # Field order matches SWE-bench JSONL rows so the file stays uniform.
    row = {
        "repo": repo,
        "instance_id": instance_id,
        "base_commit": base_commit,
        "problem_statement": problem,
        "hints_text": "",
        "subset": "custom",
        "split": "custom",
    }
    # Ensure trailing newline so the append lands on a fresh line.
    if INSTANCES_PATH.exists() and INSTANCES_PATH.stat().st_size > 0:
        existing = INSTANCES_PATH.read_bytes()
        if not existing.endswith(b"\n"):
            with INSTANCES_PATH.open("ab") as fh:
                fh.write(b"\n")
    with INSTANCES_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {
        "instance_id": instance_id,
        "repo": repo,
        "base_commit": base_commit,
        "duplicate": False,
    }


@router.get("/api/instances")
def list_instances(skip: int = 0, limit: int = 0) -> list[dict]:
    """List instances. `limit=0` means unlimited."""
    if not INSTANCES_PATH.exists():
        return []
    results: list[dict] = []
    seen = 0
    with INSTANCES_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            seen += 1
            if seen <= skip:
                continue
            if limit > 0 and len(results) >= limit:
                break
            try:
                obj = json.loads(line)
                results.append({
                    "instance_id": obj.get("instance_id", ""),
                    "repo": obj.get("repo", ""),
                    "problem_statement": (obj.get("problem_statement") or "")[:300],
                    # Legacy rows (pre-nested-picker) default to lite/dev.
                    "subset": obj.get("subset", "lite"),
                    "split": obj.get("split", "dev"),
                })
            except json.JSONDecodeError:
                pass
    return results
