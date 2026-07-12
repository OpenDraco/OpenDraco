"""claude_coder `executeCommandTool` — run a shell command.

Behavior-faithful re-implementation of the upstream tool name only;
no upstream code is referenced. Delegates to the canonical OpenHands
`CmdRunTool` so EvoMas has one shell-execution path, not two.
"""
from __future__ import annotations

from langchain_core.tools import tool

from evomas.tools.repo.openhands.CmdRunTool import CmdRunTool as _exec


@tool
def executeCommandTool(command: str, cwd: str | None = None, timeout: int = 30) -> str:
    """Run `command` in `cwd` with a `timeout`-second cap. Returns
    combined stdout + stderr plus the `[exit code: N]` line that the
    canonical OpenHands `CmdRunTool` produces."""
    return _exec.invoke({"command": command, "cwd": cwd, "timeout": timeout})
