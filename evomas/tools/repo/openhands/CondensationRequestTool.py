"""OpenHands `CondensationRequestTool` — request a summary/condensation
of the conversation so the controller can compact memory before
continuing.

EvoMas's runtime doesn't yet act on the signal (the controller doesn't
shorten conversation history), so this is a no-op acknowledgement —
present so the upstream-shaped tool catalog stays complete and prompts
that reference `CondensationRequestTool` resolve.
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def CondensationRequestTool() -> str:
    """Signal that the conversation history should be condensed.
    Returns a fixed acknowledgement string. No mutation happens."""
    return "Condensation requested."
