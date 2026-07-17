"""OpenHands `GrepTool` — recursive regex search across the workspace.

Walks the directory tree, opens each file as text, applies the
compiled regex to its contents. Returns up to 100 matching paths
sorted by mtime (most-recently-modified first).
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from langchain_core.tools import tool


@tool
def GrepTool(pattern: str, path: str | None = None, include: str | None = None) -> list[str]:
    """Search the workspace recursively for files whose contents match
    the regex `pattern`. Optional `include` glob restricts which file
    names are considered. Returns up to 100 paths, most-recently-modified
    first. Files that can't be read are skipped silently."""
    base = Path(path or ".")
    if not base.is_dir():
        return [f"Error: {base} is not a directory"]
    rx = re.compile(pattern)
    matches: list[tuple[float, str]] = []
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if include and not fnmatch.fnmatch(p.name, include):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if rx.search(text):
            matches.append((p.stat().st_mtime, str(p)))
    matches.sort(reverse=True)
    return [m[1] for m in matches[:100]]
