"""claude_coder `urlScreenshotTool` — browser-screenshot placeholder.

EvoMas doesn't ship a browser/Playwright runtime, so this returns an
informative error rather than crashing the agent loop. Same pattern as
the OpenHands `BrowserTool` stub.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def urlScreenshotTool(url: str) -> str:
    """Stub: no Playwright / headless-browser runtime is wired in this
    EvoMas install."""
    logger.warning("[claude_coder.urlScreenshotTool] no browser runtime: %s", url[:200])
    return (
        "error: urlScreenshotTool is not configured in this EvoMas install "
        "(no Playwright runtime)."
    )
