"""claude_coder `devServerTool` — dev-server lifecycle placeholder.

The upstream tool starts / stops / logs from a per-project dev server.
EvoMas runs against a static workspace and doesn't manage long-lived
processes, so this returns an informative error. Wire a real
implementation by managing a `subprocess.Popen` keyed off `port`.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def devServerTool(action: str = "status", port: int = 0, command: str = "") -> str:
    """Stub: no dev-server runtime wired."""
    logger.warning("[claude_coder.devServerTool] no runtime: action=%r port=%d", action, port)
    return (
        "error: devServerTool is not configured in this EvoMas install "
        "(no long-lived dev-server process manager)."
    )
