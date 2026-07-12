"""patchwork `grep_tool` tool.

Upstream reference: https://github.com/patched-codes/patchwork/blob/main/patchwork/common/tools/grep_tool.py
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


from evomas.tools.repo.openhands.GrepTool import GrepTool as _grep


@tool
def grep_tool(pattern: str, path: str = ".", include: str | None = None) -> str:
    """Recursive ripgrep-style content search. Delegates to the openhands
    `grep` implementation."""
    return _grep.invoke({"pattern": pattern, "path": path, "include": include})
