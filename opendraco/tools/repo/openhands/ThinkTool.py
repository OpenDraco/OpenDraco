"""OpenHands `ThinkTool` — log a chain-of-thought entry without
mutating the workspace.

Matches the upstream OpenHands tool name + parameter shape so prompts
that reference `ThinkTool` continue to make sense. The implementation
is a minimal logger call — it never touches the filesystem or the
network — and always returns a fixed acknowledgement string.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def ThinkTool(thought: str) -> str:
    """Log `thought` to the agent trace without changing any workspace
    state. Use this to externalize reasoning steps before/between
    tool calls. Returns a fixed acknowledgement string."""
    logger.info("[ThinkTool] %s", thought)
    return "Your thought has been logged."
