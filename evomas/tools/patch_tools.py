"""LLM-facing patch tools: thin `@tool` wrappers around the software-callable
`_impl` functions in `evomas/utils/patch.py`, plus the deterministic class-1
description-bug fixer (`apply_description_fix`) that composes
`detect_bug_class` + `derive_description_fix` + `apply_patch` into a single
call the patcher chain runs first.

The real `git apply` / `git diff` / unified-diff-normaliser code lives in
`evomas/utils/patch.py`. This module just wraps each `_impl` in an `@tool`
so a LangChain-driven agent can call it as a tool. Code that doesn't need
the tool layer (api router, agent runtime, runner, scripts) should import
the `_impl` versions from `evomas/utils/patch` directly.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.tools import tool

from evomas.tools.repo_tools import derive_description_fix_impl
from evomas.tools.search_tools import detect_bug_class_impl
from evomas.utils.patch import (
    PatchResult,
    _git,
    apply_patch_impl,
    generate_diff_impl,
    normalize_patch_impl,
)

# Re-export for callers that previously imported these names from this
# module. They still resolve to the canonical implementations in
# `evomas/utils/patch.py`.
__all__ = [
    "PatchResult",
    "apply_patch_impl",
    "generate_diff_impl",
    "normalize_patch_impl",
    "reset_repo_impl",
    "apply_description_fix_impl",
    "DescriptionFixApplied",
    "apply_patch",
    "generate_diff",
    "normalize_patch",
    "reset_repo",
    "apply_description_fix",
]

logger = logging.getLogger(__name__)


def reset_repo_impl(repo_path: str, base_commit: str) -> None:
    """Hard-reset `repo_path` to `base_commit` and wipe untracked files.
    Software-callable; the `@tool` wrapper below is what an LLM agent uses."""
    _git(["reset", "--hard", base_commit], cwd=repo_path)
    _git(["clean", "-fdx"], cwd=repo_path)


@tool
def apply_patch(patch_str: str, repo_path: str, dry_run: bool = False) -> PatchResult:
    """Apply a unified diff patch to a git repository using `git apply`.

    Args:
        patch_str: unified diff content.
        repo_path: absolute path to the git repo root.
        dry_run: if True, only run `git apply --check` without applying.

    Returns {ok, output, applied}.
    """
    return apply_patch_impl(patch_str, repo_path, dry_run)


@tool
def generate_diff(repo_path: str, base_commit: str | None = None) -> str:
    """Run `git diff` in the given repo against the working tree (or a base commit)."""
    return generate_diff_impl(repo_path, base_commit)


@tool
def reset_repo(repo_path: str, base_commit: str) -> None:
    """Hard-reset the repository to base_commit and remove untracked files."""
    reset_repo_impl(repo_path, base_commit)


@tool
def normalize_patch(patch_str: str) -> str:
    """Repair common LLM-generated unified-diff malformations and return a
    `git apply`-compatible patch string. Idempotent: a well-formed patch is
    returned unchanged. Specifically:
      * adds a `diff --git a/<path> b/<path>` header when missing,
      * recomputes `@@ -old,oldc +new,newc @@` hunk counts from body lines,
      * gives blank context lines inside hunks a leading space,
      * drops hunks where every `-` line equals the matching `+` line.
    Call this right after generating a `<patch>...</patch>` block and before
    `apply_patch`.

    Args:
        patch_str: raw unified diff content (possibly malformed).
    Returns: a normalized diff string, or "" if the input has no diff content.
    """
    return normalize_patch_impl(patch_str)


# ─── End-to-end class-1 description fixer ────────────────────────────────────
# Composes `detect_bug_class` (search_tools) + `derive_description_fix`
# (repo_tools) + `apply_patch` (utils.patch) into a single deterministic call
# the patcher chain invokes first. Lives in patch_tools because the
# downstream operation — building a minimal unified diff and applying it — is
# fundamentally a patch op.

class DescriptionFixApplied(TypedDict, total=False):
    ok: bool                          # True when the patch was applied
    bug_class: int                    # 1 / 2 / 3 from detect_bug_class
    evidence: str                     # detect_bug_class evidence (always)
    file: str                         # repo-relative, class 1 only
    line: int                         # 1-indexed, class 1 only
    old_string: str                   # the literal removed
    new_string: str                   # the literal inserted
    patch: str                        # the unified diff applied
    error: str                        # set when a class-1 path can't complete


def _build_single_line_diff(
    relative_path: str,
    lines: list[str],
    line_index: int,
    old_string: str,
    new_string: str,
    context: int = 3,
) -> str:
    """Build a minimal unified diff that replaces `old_string` with
    `new_string` on `lines[line_index]`. Reads no filesystem; pure string
    construction. The 3-line context above/below matches `git diff` defaults
    so `git apply --check` doesn't reject for fuzzy context."""
    original_line = lines[line_index]
    if old_string not in original_line:
        raise ValueError(f"old_string not found on line {line_index + 1}")
    new_line = original_line.replace(old_string, new_string, 1)
    if new_line == original_line:
        raise ValueError("replacement produced an identical line")

    start = max(0, line_index - context)
    end = min(len(lines), line_index + context + 1)
    pre = lines[start:line_index]
    post = lines[line_index + 1:end]

    hunk_old_count = len(pre) + 1 + len(post)
    hunk_new_count = hunk_old_count  # single-line replacement → counts match
    hunk_start = start + 1  # 1-indexed

    body: list[str] = []
    body.extend(" " + l for l in pre)
    body.append("-" + original_line)
    body.append("+" + new_line)
    body.extend(" " + l for l in post)

    header = (
        f"diff --git a/{relative_path} b/{relative_path}\n"
        f"--- a/{relative_path}\n"
        f"+++ b/{relative_path}\n"
        f"@@ -{hunk_start},{hunk_old_count} +{hunk_start},{hunk_new_count} @@\n"
    )
    return header + "\n".join(body) + "\n"


def apply_description_fix_impl(issue_text: str, repo_path: str) -> DescriptionFixApplied:
    """End-to-end class-1 description-bug fixer.

    Combines `detect_bug_class` + `derive_description_fix` and applies the
    resulting single-line replacement via `apply_patch`. Pure deterministic
    Python — safe to call as the very first step in any patcher chain.

    Returns:
      * On class-1 success: `{ok: True, bug_class: 1, file, line, old_string,
        new_string, patch, evidence}`. The workspace has been modified.
      * On non-class-1 detection: `{ok: False, bug_class: <2|3>, evidence}`.
        The caller (LLM agent) should fall through to a general workflow.
      * On class-1 detection but derivation/apply failure: `{ok: False,
        bug_class: 1, error, evidence}`.
    """
    detection = detect_bug_class_impl(issue_text, repo_path)
    bug_class = int(detection.get("bug_class", 0) or 0)
    evidence = str(detection.get("evidence", ""))
    if bug_class != 1:
        return {"ok": False, "bug_class": bug_class, "evidence": evidence}

    matched_file = str(detection.get("matched_file", ""))
    matched_quoted = str(detection.get("matched_quoted_string", ""))
    if not matched_file or not matched_quoted:
        return {
            "ok": False, "bug_class": 1, "evidence": evidence,
            "error": "class-1 detection missing matched_file or matched_quoted_string",
        }

    fix = derive_description_fix_impl(repo_path, matched_file, matched_quoted)
    if fix.get("error"):
        return {
            "ok": False, "bug_class": 1, "evidence": evidence,
            "error": f"derive_description_fix failed: {fix.get('error')}",
        }

    new_string = str(fix.get("new_string", ""))
    line_no = int(fix.get("line", 0) or 0)
    if not new_string or line_no < 1:
        return {
            "ok": False, "bug_class": 1, "evidence": evidence,
            "error": "derive_description_fix returned an unusable result",
        }

    abs_file = Path(repo_path) / matched_file
    if not abs_file.is_file():
        return {
            "ok": False, "bug_class": 1, "evidence": evidence,
            "error": f"matched_file not found at expected path: {abs_file}",
        }
    try:
        text = abs_file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "ok": False, "bug_class": 1, "evidence": evidence,
            "error": f"read failed: {exc}",
        }
    lines = text.splitlines()
    line_index = line_no - 1
    if not (0 <= line_index < len(lines)):
        return {
            "ok": False, "bug_class": 1, "evidence": evidence,
            "error": f"derived line {line_no} out of range (file has {len(lines)} lines)",
        }

    try:
        patch_str = _build_single_line_diff(
            relative_path=matched_file,
            lines=lines,
            line_index=line_index,
            old_string=matched_quoted,
            new_string=new_string,
        )
    except ValueError as exc:
        return {
            "ok": False, "bug_class": 1, "evidence": evidence,
            "error": f"diff construction failed: {exc}",
        }

    apply = apply_patch_impl(patch_str, repo_path)
    if not apply.get("ok"):
        return {
            "ok": False, "bug_class": 1, "evidence": evidence,
            "error": f"apply_patch failed: {apply.get('output', '')[:300]}",
            "patch": patch_str,
        }

    logger.info("[apply_description_fix] applied %s:%d %r -> %r",
                matched_file, line_no, matched_quoted, new_string)
    return {
        "ok": True,
        "bug_class": 1,
        "evidence": evidence,
        "file": matched_file,
        "line": line_no,
        "old_string": matched_quoted,
        "new_string": new_string,
        "patch": patch_str,
    }


@tool
def apply_description_fix(issue_text: str, repo_path: str) -> dict[str, Any]:
    """Deterministic end-to-end fixer for class-1 description / error-message
    bugs. Detects the bug class, derives the verbatim replacement from the
    source docstring, builds a minimal unified diff, and applies it to the
    workspace via `apply_patch` — all without LLM judgment.

    Use this as the FIRST tool call on every SWE-bench-style task:
      * If it returns `ok=True`: the fix is already applied. Stop emitting
        further tool calls — your job is done.
      * If it returns `ok=False`: this is a class-2 behaviour bug or a
        class-3 API mismatch. Fall through to the general repair workflow:
        read the relevant file with `read_file`, write a unified diff
        manually, and apply it via `apply_patch`.

    Args:
        issue_text: the SWE-bench issue / problem statement.
        repo_path:  absolute path to the cloned workspace root.

    Returns: `{ok, bug_class, evidence, ...}` — see `apply_description_fix_impl`
        for the full shape.
    """
    return dict(apply_description_fix_impl(issue_text, repo_path))
