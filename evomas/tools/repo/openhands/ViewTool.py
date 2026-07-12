"""OpenHands `ViewTool` — print a file (or directory listing) with line
numbers, optionally restricted to a line range.

Delegates rendering to the shared `_file_view` helper so the output
format stays consistent with the `view` subcommand of
`StrReplaceEditorTool`.
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from evomas.tools.repo.openhands._helpers import _file_view


@tool
def ViewTool(path: str, view_range: list[int] | None = None) -> str:
    """Show `path` as numbered text (for a file) or as a recursive
    listing capped at depth 2 (for a directory). `view_range` is a
    `[start, end]` 1-indexed inclusive slice; pass `[10, -1]` to view
    line 10 through end of file."""
    p = Path(path)
    if not p.exists():
        return f"Error: path {path} does not exist."
    return _file_view(p, view_range)
