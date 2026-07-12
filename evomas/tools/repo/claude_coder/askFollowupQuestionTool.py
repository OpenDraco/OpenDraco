"""claude_coder `askFollowupQuestionTool` — interactive-prompt placeholder.

The upstream tool prompts the user mid-run for clarification. EvoMas
runs autonomously (no interactive user channel during a topology run),
so this returns an informative error rather than blocking the agent
loop. Catalogs that reference the tool still resolve to a callable.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def askFollowupQuestionTool(question: str) -> str:
    """Stub: EvoMas runs autonomously, no interactive user channel.
    Returns an error string the agent can route around."""
    logger.warning("[claude_coder.askFollowupQuestionTool] non-interactive runtime: %s", question[:200])
    return (
        "error: askFollowupQuestionTool is not available in this EvoMas install "
        "(autonomous run, no user-prompt channel). Plan around the missing info."
    )
