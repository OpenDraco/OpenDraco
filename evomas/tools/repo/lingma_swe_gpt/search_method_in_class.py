"""lingma_swe_gpt `search_method_in_class` — locate a method inside a class."""
from __future__ import annotations

import json

from langchain_core.tools import tool

from evomas.tools.repo.lingma_swe_gpt._ast_search import find_methods, format_result


@tool
def search_method_in_class(method_name: str, class_name: str, workspace: str) -> str:
    """Search for a method declared inside a specific class.

    Args:
        method_name: exact method name to find.
        class_name: enclosing class name.
        workspace: absolute path to the repo root.

    Returns a JSON `{"result", "summary", "ok"}` payload.
    """
    matches = find_methods(workspace, method_name=method_name, class_name=class_name)
    result, summary, ok = format_result(
        matches, default_summary=f"search_method_in_class({method_name!r} in class {class_name!r})",
    )
    return json.dumps({"result": result, "summary": summary, "ok": ok})
