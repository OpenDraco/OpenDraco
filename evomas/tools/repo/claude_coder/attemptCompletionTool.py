"""claude_coder `attemptCompletionTool` — task-completion marker.

Functionally aligned with augment's `CompleteTool` — both signal the
end of an agent's turn and record the outcome. Delegates to the
augment canonical so EvoMas has one consistent completion-marker code
path; the catalog name (`attemptCompletionTool`) stays upstream-aligned.
"""
from __future__ import annotations

from langchain_core.tools import tool

from evomas.tools.repo.augment_swebench_agent.CompleteTool import CompleteTool as _complete


@tool
def attemptCompletionTool(result: str = "", workspace: str = "", agent: str = "claude_coder") -> str:
    """Mark the run done. Returns the JSON record
    `{agent, completed, result, ts}`; when `workspace` is set drops
    a `.evomas/state.json` marker for out-of-process callers."""
    return _complete.invoke({"result": result, "workspace": workspace, "agent": agent})
