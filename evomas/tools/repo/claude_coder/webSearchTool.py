"""claude_coder `webSearchTool` — web-search placeholder.

EvoMas doesn't ship a web-search backend (no API key wiring, no
crawler), so this returns an informative error. Add a real
implementation by replacing the body with a call to a search API
(Tavily, SerpAPI, …) and threading credentials through env vars.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def webSearchTool(query: str) -> str:
    """Stub: no web-search backend configured in this EvoMas install."""
    logger.warning("[claude_coder.webSearchTool] no backend: %s", query[:200])
    return (
        "error: webSearchTool is not configured in this EvoMas install "
        "(no web-search API key wired)."
    )
