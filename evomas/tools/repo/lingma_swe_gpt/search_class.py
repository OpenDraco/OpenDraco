"""lingma_swe_gpt `search_class` — locate a class across the workspace.

Behavioral interface matches Lingma-SWE-GPT's `ProjectApiManager.search_class`
(input: `class_name`; output: `(result, summary, ok)`). The body is a
fresh EvoMas implementation that delegates to `ast`-based discovery via
`_ast_search.find_classes`.
"""
from __future__ import annotations

import json

from langchain_core.tools import tool

from evomas.tools.repo.lingma_swe_gpt._ast_search import find_classes, format_result


@tool
def search_class(class_name: str, workspace: str) -> str:
    """Search for a class declaration in the workspace.

    Args:
        class_name: exact class name to find.
        workspace: absolute path to the repo root.

    Returns a JSON string `{"result", "summary", "ok"}` where `result`
    is a newline-joined list of `file:line  ClassName` matches.
    """
    matches = find_classes(workspace, class_name=class_name)
    result, summary, ok = format_result(
        matches, default_summary=f"search_class({class_name!r})",
    )
    return json.dumps({"result": result, "summary": summary, "ok": ok})
