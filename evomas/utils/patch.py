"""Software-callable patch primitives — git apply, git diff, unified-diff repair.

# ---------------------------------------------------------------------------
# SOFTWARE-CALLED SURFACE for the patch-handling primitives. The
# `@tool`-decorated LLM-facing wrappers (`apply_patch`, `generate_diff`,
# `normalize_patch`) live in `evomas/tools/patch_tools.py` and delegate
# straight into the `_impl` functions here. Code that doesn't need a
# LangChain tool round-trip (api router, agent runtime, runner,
# scripts/evaluation/apply_and_test.py) imports from this module directly.
#
# This split keeps the LLM-facing tool definitions thin and parks the real
# implementation alongside the rest of evomas's pure-Python utilities in
# `evomas/utils/`.
# ---------------------------------------------------------------------------
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)


def _patch_env() -> dict[str, str] | None:
    """Environment for invoking GNU `patch` on Windows.

    Windows' installer-detection heuristic flags any executable named
    `patch.exe` as an installer and demands UAC elevation, so a plain
    `subprocess.run(["patch", ...])` dies with `WinError 740` before patch
    ever runs. Setting `__COMPAT_LAYER=RunAsInvoker` tells the compatibility
    layer to launch the process as the invoking (non-elevated) user, which
    suppresses the false-positive elevation request. No-op off Windows.
    """
    if sys.platform != "win32":
        return None
    env = os.environ.copy()
    env["__COMPAT_LAYER"] = "RunAsInvoker"
    return env


class PatchResult(TypedDict):
    ok: bool
    output: str
    applied: bool


def _git(args: list[str], cwd: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    # Force UTF-8: git emits UTF-8 but `text=True` decodes via the
    # system locale (cp1252 on Windows), which double-encodes non-ASCII
    # bytes and breaks downstream `git apply`.
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _patch_cmd(args: list[str], cwd: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["patch", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=_patch_env(),
    )


def apply_patch_impl(patch_str: str, repo_path: str, dry_run: bool = False) -> PatchResult:
    if not patch_str.strip():
        return {"ok": False, "output": "empty patch", "applied": False}

    content = patch_str if patch_str.endswith("\n") else patch_str + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".diff", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(content)
        patch_path = tf.name

    try:
        # Method 1: git apply --check (strict)
        check = _git(["apply", "--check", patch_path], cwd=repo_path)
        if check.returncode == 0:
            if dry_run:
                return {"ok": True, "output": "patch applies cleanly (dry run)", "applied": False}
            apply = _git(["apply", patch_path], cwd=repo_path)
            return {
                "ok": apply.returncode == 0,
                "output": (apply.stdout + apply.stderr).strip() or "patch applied",
                "applied": apply.returncode == 0,
            }

        git_err = (check.stdout + check.stderr).strip()

        # Method 2: patch --fuzz=5 (more lenient context matching)
        fuzz_args = ["--batch", "--fuzz=5", "-p1", "-i", patch_path]
        if dry_run:
            fuzz_args = ["--dry-run"] + fuzz_args
        fuzz = _patch_cmd(fuzz_args, cwd=repo_path)
        if fuzz.returncode == 0:
            output = (fuzz.stdout + fuzz.stderr).strip() or "patch applied (fuzz)"
            return {"ok": True, "output": output, "applied": not dry_run}

        return {
            "ok": False,
            "output": f"{git_err}\n{(fuzz.stdout + fuzz.stderr).strip()}".strip(),
            "applied": False,
        }
    finally:
        try:
            Path(patch_path).unlink()
        except OSError:
            pass


def generate_diff_impl(repo_path: str, base_commit: str | None = None) -> str:
    args = ["diff", "--no-color"]
    if base_commit:
        args.append(base_commit)
    proc = _git(args, cwd=repo_path)
    if proc.returncode != 0:
        logger.warning("git diff failed: %s", proc.stderr)
        return ""
    return proc.stdout


# ─── Unified-diff repair helpers (used by `normalize_patch_impl` and by any
# PatcherAgent that wants to normalize before applying). Pure string
# functions, no filesystem side-effects. ────────────────────────────────
def _add_git_header_if_missing(patch: str) -> str:
    """Prepend `diff --git a/<path> b/<path>` when the LLM omitted it.
    `git apply` requires the header; GNU `patch` doesn't. Adding it makes
    the diff compatible with both backends used inside apply_patch."""
    if patch.startswith("diff --git"):
        return patch
    lines = patch.splitlines()
    old_path = new_path = None
    for line in lines[:10]:
        if line.startswith("--- a/") and old_path is None:
            old_path = line[6:].split("\t")[0].strip()
        elif line.startswith("+++ b/") and new_path is None:
            new_path = line[6:].split("\t")[0].strip()
    if old_path and new_path:
        return f"diff --git a/{old_path} b/{new_path}\n{patch}"
    return patch


def _fix_blank_context_lines(patch: str) -> str:
    """Ensure blank context lines inside hunks have a leading space.
    `git apply` rejects patches where context lines inside a hunk are
    completely empty — the unified-diff standard requires a single-space
    prefix for unchanged lines."""
    lines = patch.splitlines(keepends=True)
    result: list[str] = []
    in_hunk = False
    for line in lines:
        if line.startswith("@@"):
            in_hunk = True
        elif line.startswith("diff --git"):
            in_hunk = False
        if in_hunk and line in ("\n", "\r\n", ""):
            line = " \n"
        result.append(line)
    return "".join(result)


_HUNK_HEADER_RE_INNER: re.Pattern[str] = re.compile(
    r"^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@", re.MULTILINE,
)


def _fix_hunk_headers(patch: str) -> str:
    """Recalculate `@@` hunk headers to match the actual content line counts.
    LLMs frequently write wrong `old_count` / `new_count`; `git apply --check`
    flags this as a corrupt patch even when the content would apply fine."""
    lines = patch.splitlines(keepends=True)
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _HUNK_HEADER_RE_INNER.match(line)
        if m:
            old_start = int(m.group(1))
            new_start = int(m.group(2))
            i += 1
            body: list[str] = []
            while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("diff --git"):
                body.append(lines[i])
                i += 1
            old_count = sum(1 for l in body if l and (l[0] in (" ", "-")))
            new_count = sum(1 for l in body if l and (l[0] in (" ", "+")))
            suffix_m = re.match(r"@@[^@]*@@(.*)", line.rstrip("\r\n"))
            suffix = suffix_m.group(1) if suffix_m else ""
            new_header = f"@@ -{old_start},{old_count} +{new_start},{new_count} @@{suffix}\n"
            result.append(new_header)
            result.extend(body)
        else:
            result.append(line)
            i += 1
    return "".join(result)


def _filter_noop_hunks(patch: str) -> str:
    """Remove hunks where every removed line equals the corresponding added
    line (whitespace-only flips, trailing-comment churn). Such hunks fail
    `git apply` with context-mismatch and carry no useful fix anyway."""
    lines = patch.splitlines(keepends=True)
    file_header: list[str] = []
    current_hunk: list[str] = []
    meaningful_hunks: list[list[str]] = []

    def _is_meaningful(hunk: list[str]) -> bool:
        removed = [l[1:].rstrip("\r\n") for l in hunk if l.startswith("-")]
        added = [l[1:].rstrip("\r\n") for l in hunk if l.startswith("+")]
        return removed != added

    def _flush_hunk() -> None:
        if current_hunk and _is_meaningful(current_hunk):
            meaningful_hunks.append(list(current_hunk))
        current_hunk.clear()

    in_file = False
    for line in lines:
        if line.startswith("diff --git") or line.startswith("--- ") or line.startswith("+++ "):
            _flush_hunk()
            if line.startswith("diff --git"):
                in_file = True
            file_header.append(line)
        elif line.startswith("@@") and in_file:
            _flush_hunk()
            current_hunk.append(line)
        elif in_file and current_hunk:
            current_hunk.append(line)
    _flush_hunk()

    if not meaningful_hunks:
        if not file_header:
            return patch
        return ""

    return "".join(file_header + [l for h in meaningful_hunks for l in h])


def normalize_patch_impl(patch_str: str) -> str:
    """Run every diff-repair pass on a (possibly malformed) unified diff and
    return a `git apply`-compatible string. Empty input → empty output."""
    patch = (patch_str or "").strip("\n\r ")
    if not patch:
        return ""
    patch = _add_git_header_if_missing(patch)
    patch = _fix_blank_context_lines(patch)
    patch = _fix_hunk_headers(patch)
    patch = _filter_noop_hunks(patch)
    if patch and not patch.endswith("\n"):
        patch += "\n"
    return patch
