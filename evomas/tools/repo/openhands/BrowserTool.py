"""OpenHands `BrowserTool` — placeholder for browser-driving capability.

The upstream OpenHands `BrowserTool` drives a Playwright session; EvoMas
doesn't ship a browser runtime here, so this returns an informative
error rather than crashing the agent loop. Keeps the tool catalog
complete so prompts referencing `BrowserTool` resolve to a callable
that explains why it can't run.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def BrowserTool(action: str = "", url: str = "") -> str:
    """Stub: this EvoMas install has no Playwright/Browser runtime.
    Returns an explanatory error so the agent can route around it."""
    logger.warning("[BrowserTool] no runtime configured: action=%r url=%r", action, url[:120])
    return (
        "error: BrowserTool is not configured in this EvoMas install "
        "(no Playwright/Browser runtime available)."
    )
