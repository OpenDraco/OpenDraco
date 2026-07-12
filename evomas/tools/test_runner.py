"""Run-pytest tool — lets the ReviewerAgent verify a patch actually resolves the bug.

Paired-siblings convention (same as `patch_tools.py`):
  * `run_tests_impl(workspace, test_paths, timeout_s)` — software-callable,
    pure subprocess. Other agent code / scripts can import this directly.
  * `run_tests(...)` — LLM-callable `@tool` wrapper.

Methodology note for the ReviewerAgent's feedback loop: this tool is what
makes the Reviewer's "confirms whether the underlying issue has been
adequately resolved" claim accurate — the LLM agent now actually runs
tests against the patched workspace instead of just lint-checking.

Verdict semantics:
  * `passed` — every test_path returned exit code 0.
  * `failed` — at least one test_path failed.
  * `import_error` — pytest couldn't import the test (workspace deps missing
    in the local venv). No signal — same handling as in
    `evomas/tools/reproducer.py`.
  * `timeout` — pytest hung.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import TypedDict

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


class TestRunResult(TypedDict):
    verdict: str          # passed / failed / import_error / timeout / no_tests
    exit_code: int
    elapsed_s: float
    stdout_tail: str      # last 4 KB of stdout
    stderr_tail: str      # last 4 KB of stderr
    failures: list[str]   # FAILED node-ids extracted from pytest output


_FAILED_RE = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)


def run_tests_impl(
    workspace: str,
    test_paths: list[str] | None = None,
    timeout_s: float = 120.0,
) -> TestRunResult:
    """Run pytest against `workspace`, optionally narrowed to `test_paths`.

    Local subprocess execution: workspace + `<workspace>/src` are prepended
    to PYTHONPATH so the project under test is importable. If a per-instance
    SWE-bench Docker image is available you'd use that instead for accuracy,
    but local is fast and good enough as a feedback signal.
    """
    ws = Path(workspace)
    if not ws.is_dir():
        return TestRunResult(
            verdict="no_tests", exit_code=-1, elapsed_s=0.0,
            stdout_tail="", stderr_tail=f"workspace not found: {ws}",
            failures=[],
        )

    paths = [p for p in (test_paths or []) if p]
    if not paths:
        # Default: discover tests/ at the repo root if it exists.
        if (ws / "tests").is_dir():
            paths = ["tests"]
        elif (ws / "test").is_dir():
            paths = ["test"]
        else:
            return TestRunResult(
                verdict="no_tests", exit_code=-1, elapsed_s=0.0,
                stdout_tail="", stderr_tail="no test path provided and no tests/ dir found",
                failures=[],
            )

    env = os.environ.copy()
    sep = ";" if os.name == "nt" else ":"
    pythonpath_parts = [str(ws)]
    if (ws / "src").is_dir():
        pythonpath_parts.insert(0, str(ws / "src"))
    existing = env.get("PYTHONPATH", "")
    if existing:
        pythonpath_parts.append(existing)
    env["PYTHONPATH"] = sep.join(pythonpath_parts)

    cmd = [sys.executable, "-m", "pytest", "-rA", "--tb=short", *paths]
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=str(ws), env=env,
            capture_output=True, text=True, timeout=timeout_s,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return TestRunResult(
            verdict="timeout", exit_code=-1, elapsed_s=time.time() - t0,
            stdout_tail="", stderr_tail=f"pytest timed out after {timeout_s}s",
            failures=[],
        )
    elapsed = time.time() - t0
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    # Distinguish "tests failed" from "couldn't import workspace".
    combined_lower = (stdout + stderr).lower()
    if "modulenotfounderror" in combined_lower or "no module named" in combined_lower:
        # Heuristic: if pytest couldn't even collect, it's an env issue.
        if "collected 0 items" in combined_lower or "errors during collection" in combined_lower:
            return TestRunResult(
                verdict="import_error", exit_code=proc.returncode, elapsed_s=elapsed,
                stdout_tail=stdout[-4000:], stderr_tail=stderr[-4000:],
                failures=[],
            )

    failures = _FAILED_RE.findall(stdout)
    if proc.returncode == 0:
        verdict = "passed"
    else:
        verdict = "failed"
    return TestRunResult(
        verdict=verdict, exit_code=proc.returncode, elapsed_s=elapsed,
        stdout_tail=stdout[-4000:], stderr_tail=stderr[-4000:],
        failures=failures[:50],
    )


@tool
def run_tests(
    workspace: str,
    test_paths: list[str] | None = None,
    timeout_s: float = 120.0,
) -> dict:
    """Run pytest in `workspace`, optionally narrowed to specific paths, and
    return a verdict.

    USE THIS to confirm the patcher's edits actually resolve the issue.
    Without it, a Reviewer can only judge whether a patch looks correct —
    not whether it makes the tests pass.

    Args:
        workspace:   absolute path to the cloned repo root (the patched workspace).
        test_paths:  optional list of pytest paths/node-ids to focus on.
                     Defaults to the repo's `tests/` or `test/` directory.
        timeout_s:   per-invocation timeout. Default 120s.

    Returns: {`verdict`, `exit_code`, `elapsed_s`, `stdout_tail`, `stderr_tail`, `failures`}
    where `verdict` is one of `passed` / `failed` / `import_error` /
    `timeout` / `no_tests`. Treat `import_error` as "no signal — the
    workspace deps aren't installed locally", not as a true failure.
    """
    return dict(run_tests_impl(workspace, test_paths, timeout_s))
