"""claude_coder `searchFilesTool` — glob-pattern file search.

Delegates to the canonical OpenHands `GlobTool` so EvoMas has one
glob-based file-search path, not two.
"""
from __future__ import annotations

from langchain_core.tools import tool

from evomas.tools.repo.openhands.GlobTool import GlobTool as _glob


@tool
def searchFilesTool(pattern: str, path: str | None = None) -> list[str]:
    """Match `pattern` recursively under `path` (default: current
    directory). Returns up to 100 file paths, most-recently-modified
    first."""
    return _glob.invoke({"pattern": pattern, "path": path})
