"""claude_coder `readFileTool` — read a file's contents.

Delegates to the canonical OpenDraco `read_file` from
`opendraco.tools.repo_tools`.
"""
from __future__ import annotations

from langchain_core.tools import tool

from opendraco.tools.repo_tools import read_file_impl


@tool
def readFileTool(path: str, with_line_numbers: bool = True, max_chars: int | None = None) -> str:
    """Read `path` and return its contents. When `with_line_numbers` is
    True (default) prepend `<n>\\t` to each line; when `max_chars` is
    set, truncate."""
    return read_file_impl(path, with_line_numbers=with_line_numbers, max_chars=max_chars)
