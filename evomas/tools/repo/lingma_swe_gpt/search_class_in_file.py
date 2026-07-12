"""lingma_swe_gpt `search_class_in_file` — locate a class inside one file."""
from __future__ import annotations

import json

from langchain_core.tools import tool

from evomas.tools.repo.lingma_swe_gpt._ast_search import find_classes, format_result


@tool
def search_class_in_file(class_name: str, file_name: str, workspace: str) -> str:
    """Search for a class declaration in a specific file.

    Args:
        class_name: exact class name to find.
        file_name: relative path (or trailing path suffix) of the file
            to scan inside the workspace.
        workspace: absolute path to the repo root.

    Returns a JSON `{"result", "summary", "ok"}` payload.
    """
    matches = find_classes(workspace, class_name=class_name, file_filter=file_name)
    result, summary, ok = format_result(
        matches, default_summary=f"search_class_in_file({class_name!r} in {file_name!r})",
    )
    return json.dumps({"result": result, "summary": summary, "ok": ok})
