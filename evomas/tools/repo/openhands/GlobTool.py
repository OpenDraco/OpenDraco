"""OpenHands `GlobTool` — recursive glob-pattern file search.

Returns up to 100 matching file paths sorted by mtime (most-recently
modified first). Pattern uses `pathlib.Path.rglob` semantics.
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool


@tool
def GlobTool(pattern: str, path: str | None = None) -> list[str]:
    """Match `pattern` recursively under `path` (default: current
    directory). Returns up to 100 paths, most-recently-modified
    first. Directories are skipped — only file paths are returned."""
    base = Path(path or ".")
    if not base.is_dir():
        return [f"Error: {base} is not a directory"]
    matches: list[tuple[float, str]] = []
    for p in base.rglob(pattern):
        if not p.is_file():
            continue
        matches.append((p.stat().st_mtime, str(p)))
    matches.sort(reverse=True)
    return [m[1] for m in matches[:100]]
