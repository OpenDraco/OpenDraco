"""LocAgent tools — lightweight reimplementations.

Upstream LocAgent walks a pre-built code graph (entities = directory/file/class/
function, edges = contains/imports/invokes/inherits). Building such a graph is
non-trivial; here we provide grep/AST-style approximations that respect the
same input/output shapes so prompts and routing logic remain compatible.
"""
from __future__ import annotations

import ast
import fnmatch
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


def _resolve_entity(entity: str, root: Path) -> str:
    """Resolve `file:Qualified.name` into the source slice for that entity.

    Falls back to "(not found)" when the qualified name cannot be located via AST.
    """
    if ":" not in entity:
        p = root / entity
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
        return f"(file not found: {entity})"
    file_part, qual = entity.split(":", 1)
    p = root / file_part
    if not p.is_file():
        return f"(file not found: {file_part})"
    try:
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return f"(could not parse {file_part})"
    parts = qual.split(".")
    nodes: list[ast.AST] = list(ast.iter_child_nodes(tree))
    target: ast.AST | None = None
    for name in parts:
        match = next(
            (
                n
                for n in nodes
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and n.name == name
            ),
            None,
        )
        if match is None:
            return f"(entity not found: {entity})"
        target = match
        nodes = list(ast.iter_child_nodes(match))
    if target is None:
        return f"(entity not found: {entity})"
    src = p.read_text(encoding="utf-8", errors="replace").splitlines()
    start = getattr(target, "lineno", 1) - 1
    end = getattr(target, "end_lineno", start + 1)
    return "\n".join(src[start:end])


@tool
def get_entity_contents(entity_names: list[str], workspace_path: str = ".") -> dict[str, str]:
    """Searches the codebase to retrieve the complete implementations of specified entities based on the provided entity names. The tool can handle specific entity queries such as function names, class names, or file paths."""
    root = Path(workspace_path)
    return {name: _resolve_entity(name, root) for name in entity_names}


@tool
def search_code_snippets(
    search_terms: list[str] | None = None,
    line_nums: list[int] | None = None,
    file_path_or_pattern: str = "**/*.py",
    workspace_path: str = ".",
) -> list[dict[str, Any]]:
    """Searches the codebase to retrieve relevant code snippets based on given queries (terms or line numbers).

    Either `search_terms` or `line_nums` must be provided.
    - With `search_terms`: returns surrounding 10-line snippets around each hit.
    - With `line_nums`: returns the surrounding 10-line snippet at each requested line in `file_path_or_pattern`.
    """
    root = Path(workspace_path)
    out: list[dict[str, Any]] = []

    if line_nums:
        target = root / file_path_or_pattern
        if not target.is_file():
            return [{"error": f"file not found: {file_path_or_pattern}"}]
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        for ln in line_nums:
            lo, hi = max(0, ln - 5), min(len(lines), ln + 5)
            out.append(
                {
                    "path": str(target.relative_to(root)),
                    "line": ln,
                    "snippet": "\n".join(lines[lo:hi]),
                }
            )
        return out

    if not search_terms:
        return []

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        if not fnmatch.fnmatch(rel, file_path_or_pattern):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = content.splitlines()
        for term in search_terms:
            for i, line in enumerate(lines):
                if term in line:
                    lo, hi = max(0, i - 5), min(len(lines), i + 5)
                    out.append(
                        {
                            "path": rel,
                            "line": i + 1,
                            "term": term,
                            "snippet": "\n".join(lines[lo:hi]),
                        }
                    )
                    if len(out) >= 50:
                        return out
                    break
    return out


@tool
def explore_tree_structure(
    start_entities: list[str],
    direction: str = "downstream",
    traversal_depth: int = 2,
    entity_type_filter: list[str] | None = None,
    dependency_type_filter: list[str] | None = None,
    workspace_path: str = ".",
) -> str:
    """Unified repository exploring tool that traverses the code structure to retrieve the surroundings of specified entities. In this lightweight implementation only `contains` traversal (directory/file tree) is supported, regardless of `direction` and the dependency filters."""
    root = Path(workspace_path)
    lines: list[str] = []

    def walk(p: Path, depth: int) -> None:
        if traversal_depth != -1 and depth > traversal_depth:
            return
        indent = "  " * depth
        if p.is_dir():
            lines.append(f"{indent}{p.name}/")
            for c in sorted(p.iterdir()):
                if c.name.startswith("."):
                    continue
                walk(c, depth + 1)
        else:
            lines.append(f"{indent}{p.name}")

    for ent in start_entities:
        target = root if ent == "/" else (root / ent)
        if target.exists():
            walk(target, 0)
        else:
            lines.append(f"(not found: {ent})")
    return "\n".join(lines)[:8000]


LOC_TOOLS: list[Any] = [get_entity_contents, search_code_snippets, explore_tree_structure]
