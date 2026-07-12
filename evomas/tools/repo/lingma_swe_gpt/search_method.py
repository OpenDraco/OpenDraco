"""lingma_swe_gpt `search_method` — locate a method/function anywhere in the workspace."""
from __future__ import annotations

import json

from langchain_core.tools import tool

from evomas.tools.repo.lingma_swe_gpt._ast_search import find_methods, format_result


@tool
def search_method(method_name: str, workspace: str) -> str:
    """Search for a method or function declaration across the workspace.

    Args:
        method_name: exact function/method name to find.
        workspace: absolute path to the repo root.

    Returns a JSON `{"result", "summary", "ok"}` payload listing every
    declaration (`file:line  Class.method` for methods,
    `file:line  function` for module-level functions).
    """
    matches = find_methods(workspace, method_name=method_name)
    result, summary, ok = format_result(
        matches, default_summary=f"search_method({method_name!r})",
    )
    return json.dumps({"result": result, "summary": summary, "ok": ok})
