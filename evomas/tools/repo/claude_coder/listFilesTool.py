"""claude_coder `listFilesTool` — list files under a directory.

Behavior-faithful re-implementation; delegates to the canonical EvoMas
`list_files` from `evomas.tools.repo_tools`.
"""
from __future__ import annotations

from langchain_core.tools import tool

from evomas.tools.repo_tools import list_files_impl


@tool
def listFilesTool(directory: str = ".", extension: str = "*") -> list[str]:
    """List files under `directory` matching the optional glob
    `extension` (default `*` = all). Returns relative paths."""
    return list_files_impl(directory, extension)
