"""AST-based class / method lookup helpers shared by the lingma_swe_gpt
search tools. Pure-EvoMas implementation; uses Python's `ast` to locate
declarations across a workspace.

The tools (`search_class`, `search_class_in_file`, `search_method_in_file`,
`search_method_in_class`, `search_method`) mirror the behavioral interface
of Lingma-SWE-GPT's `ProjectApiManager` search methods — same function
names and parameter shape — but the implementation here is fresh code
built on top of `ast` + the EvoMas `repo_tools.list_files_impl` helper.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

from evomas.tools.repo_tools import list_files_impl


def _iter_py_files(workspace: str) -> Iterable[tuple[Path, str]]:
    """Yield (absolute_path, source_text) for every .py file under workspace.
    Files that fail to read are silently skipped."""
    base = Path(workspace)
    for rel in list_files_impl(workspace, "*.py"):
        path = base / rel
        try:
            yield path, path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue


def _parse(source: str) -> ast.Module | None:
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def find_classes(
    workspace: str,
    class_name: str | None = None,
    file_filter: str | None = None,
) -> list[dict]:
    """Locate `class <X>` declarations in the workspace.

    Args:
        workspace: absolute path to the repo root.
        class_name: if set, only return classes whose name equals this.
        file_filter: if set, only scan the file whose relative path
            ends with this string (lets callers narrow to a single file).

    Returns a list of `{"file", "line", "class"}` dicts, sorted by file
    then line.
    """
    out: list[dict] = []
    base = Path(workspace)
    for path, source in _iter_py_files(workspace):
        rel = str(path.relative_to(base))
        if file_filter and not rel.endswith(file_filter):
            continue
        tree = _parse(source)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if class_name and node.name != class_name:
                    continue
                out.append({"file": rel, "line": node.lineno, "class": node.name})
    out.sort(key=lambda d: (d["file"], d["line"]))
    return out


def find_methods(
    workspace: str,
    method_name: str | None = None,
    class_name: str | None = None,
    file_filter: str | None = None,
) -> list[dict]:
    """Locate `def <X>` declarations (including methods inside classes).

    Args:
        workspace: repo root.
        method_name: filter by exact function/method name.
        class_name: if set, only return methods nested inside `class <class_name>`.
        file_filter: if set, only scan a single file (by relative-path suffix).

    Returns `{"file", "line", "class" or None, "method"}` dicts.
    """
    out: list[dict] = []
    base = Path(workspace)
    for path, source in _iter_py_files(workspace):
        rel = str(path.relative_to(base))
        if file_filter and not rel.endswith(file_filter):
            continue
        tree = _parse(source)
        if tree is None:
            continue
        # Walk classes first to know each function's enclosing class.
        for klass in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            if class_name and klass.name != class_name:
                continue
            for body_node in klass.body:
                if isinstance(body_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if method_name and body_node.name != method_name:
                        continue
                    out.append({"file": rel, "line": body_node.lineno,
                                "class": klass.name, "method": body_node.name})
        # Then free functions at module scope (only if no class_name filter).
        if class_name is None:
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if method_name and node.name != method_name:
                        continue
                    out.append({"file": rel, "line": node.lineno,
                                "class": None, "method": node.name})
    out.sort(key=lambda d: (d["file"], d["line"]))
    return out


def format_result(matches: list[dict], default_summary: str) -> tuple[str, str, bool]:
    """Build the `(result, summary, ok)` triple Lingma's upstream tools
    return. `result` is a newline-joined `file:line` listing; `summary`
    is a short status line; `ok` is True iff at least one match was found.
    """
    if not matches:
        return ("", default_summary + " (no matches)", False)
    lines: list[str] = []
    for m in matches:
        klass = m.get("class")
        sym = m.get("method") or m.get("class") or "?"
        prefix = f"{klass}.{sym}" if klass and "method" in m else sym
        lines.append(f"{m['file']}:{m['line']}  {prefix}")
    summary = f"{default_summary} ({len(matches)} match{'es' if len(matches) != 1 else ''})"
    return ("\n".join(lines), summary, True)
