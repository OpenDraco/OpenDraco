"""claude_coder `exitAgentTool` — stop the current agent loop.

Delegates to the canonical OpenHands `FinishTool` so EvoMas has one
end-of-loop signal across repos. The catalog name (`exitAgentTool`)
stays upstream-aligned.
"""
from __future__ import annotations

from langchain_core.tools import tool

from evomas.tools.repo.openhands.FinishTool import FinishTool as _finish


@tool
def exitAgentTool(message: str = "") -> str:
    """Stop the agent loop. Returns a string starting with `FINISH:`
    that the controller observes to halt the run."""
    return _finish.invoke({"message": message})
