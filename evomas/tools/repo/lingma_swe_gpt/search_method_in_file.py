"""lingma_swe_gpt `search_method_in_file` — locate a method/function in one file."""
from __future__ import annotations

import json

from langchain_core.tools import tool

from evomas.tools.repo.lingma_swe_gpt._ast_search import find_methods, format_result


@tool
def search_method_in_file(method_name: str, file_name: str, workspace: str) -> str:
    """Search for a method or function declaration in a specific file.

    Args:
        method_name: exact function/method name to find.
        file_name: relative path (or trailing path suffix) of the file
            to scan inside the workspace.
        workspace: absolute path to the repo root.

    Returns a JSON `{"result", "summary", "ok"}` payload listing
    `file:line  Class.method` matches (or just `file:line  method` for
    module-level functions).
    """
    matches = find_methods(workspace, method_name=method_name, file_filter=file_name)
    result, summary, ok = format_result(
        matches, default_summary=f"search_method_in_file({method_name!r} in {file_name!r})",
    )
    return json.dumps({"result": result, "summary": summary, "ok": ok})
