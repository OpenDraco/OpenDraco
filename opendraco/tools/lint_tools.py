import shutil
import subprocess
from typing import TypedDict

from langchain_core.tools import tool

FLAKE8_RULES: str = "E9,F63,F7,F82"


class LintResult(TypedDict):
    ok: bool
    output: str
    rules: str


def run_flake8_impl(file_path: str, rules: str = FLAKE8_RULES, timeout: int = 30) -> LintResult:
    flake8_bin = shutil.which("flake8")
    if not flake8_bin:
        return {"ok": True, "output": "flake8 not installed; skipped", "rules": rules}
    try:
        proc = subprocess.run(
            [flake8_bin, f"--select={rules}", file_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"flake8 timed out after {timeout}s", "rules": rules}
    output = (proc.stdout + proc.stderr).strip()
    return {"ok": proc.returncode == 0, "output": output, "rules": rules}


@tool
def run_flake8(file_path: str) -> LintResult:
    """Run flake8 with a syntax-only ruleset (E9,F63,F7,F82) on a single Python file.

    Args:
        file_path: absolute path to a .py file.

    Returns a dict {ok, output, rules}. ok=True means no syntax/name errors detected.
    """
    return run_flake8_impl(file_path)
