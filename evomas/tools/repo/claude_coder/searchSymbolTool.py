"""claude_coder `searchSymbolTool` — locate a Python symbol declaration.

Delegates to the lingma `find_methods` / `find_classes` helpers
(EvoMas's existing `ast`-based symbol locators) so we don't reinvent
the wheel.
"""
from __future__ import annotations

import json

from langchain_core.tools import tool

from evomas.tools.repo.lingma_swe_gpt._ast_search import find_classes, find_methods


@tool
def searchSymbolTool(symbol: str, workspace: str) -> str:
    """Find a class or function declaration named `symbol` anywhere in
    `workspace`. Returns JSON with the matches (file + line + kind).
    Checks both class and method declarations; multiple hits per
    workspace are returned together."""
    classes = find_classes(workspace, class_name=symbol)
    methods = find_methods(workspace, method_name=symbol)
    hits = [{"kind": "class", **c} for c in classes] + [{"kind": "method", **m} for m in methods]
    return json.dumps({
        "symbol": symbol,
        "matches": hits,
        "count": len(hits),
        "ok": bool(hits),
    })
