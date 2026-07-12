"""OpenHands `CmdRunTool` — run a shell command inside the workspace.

Subsumes the previous `bash` + `execute_bash` aliases — both pointed at
the same `_execute_bash_impl` helper. Output (stdout + stderr) is
truncated to the shared output cap and the exit code is appended.
"""
from __future__ import annotations

from langchain_core.tools import tool

from evomas.tools.repo.openhands._helpers import _execute_bash_impl


@tool
def CmdRunTool(command: str, cwd: str | None = None, timeout: int = 30) -> str:
    """Run `command` via the shell. Returns combined stdout + stderr
    plus a trailing `[exit code: N]` line. Default timeout 30 s."""
    return _execute_bash_impl(command, cwd, timeout)
