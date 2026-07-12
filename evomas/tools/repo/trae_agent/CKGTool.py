"""trae_agent `CKGTool` — top-level Python symbol listing.

Lightweight stand-in for upstream trae-agent's code-knowledge-graph
tool. Parses a single Python file with `ast` and returns the
declarations at module scope. Python-only coverage; the upstream
CKGTool indexes multiple languages but this EvoMas version keeps it
to .py.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def CKGTool(path: str) -> str:
    """List top-level classes and functions in a Python file via ast.parse.
    Returns a newline-separated "<kind> <name> (line=<n>)" listing — a
    lightweight stand-in for upstream trae-agent's code-knowledge-graph
    that ships only Python coverage."""
    p = Path(path)
    if not p.is_file():
        return f"error: {path} is not a file."
    try:
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return f"error: cannot parse {path}: {exc}"
    out = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out.append(f"class {node.name} (line={node.lineno})")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(f"def {node.name} (line={node.lineno})")
    return "\n".join(out) or "(no top-level symbols)"
