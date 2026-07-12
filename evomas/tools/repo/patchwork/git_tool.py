"""patchwork `git_tool` tool.

Upstream reference: https://github.com/patched-codes/patchwork/blob/main/patchwork/common/tools/git_tool.py
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


import subprocess


@tool
def git_tool(command: str, cwd: str = ".") -> str:
    """Run a `git <command>` invocation in `cwd` and return its output.
    Refuses any command containing destructive flags (`--force`, `push`)."""
    if any(bad in command for bad in ("--force", "push ", " push", "reset --hard")):
        return "error: refused — destructive git command blocked by EvoMas tool wrapper."
    try:
        out = subprocess.run(
            ["git", *command.split()], cwd=cwd, capture_output=True,
            text=True, timeout=60,
        )
        return (out.stdout or "") + (out.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"
