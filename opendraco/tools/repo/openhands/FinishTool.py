"""OpenHands `FinishTool` — signal end of the agent's turn.

The controller observes the `FINISH:` prefix in the returned string
and stops the agent loop. Matches the upstream tool name + parameter
shape so prompts referencing `FinishTool` continue to make sense.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def FinishTool(message: str) -> str:
    """Mark the agent's task complete and stop the loop. The returned
    string starts with `FINISH:` so the controller can detect it
    without inspecting the LLM's text output."""
    logger.info("[FinishTool] %s", message)
    return f"FINISH: {message}"
