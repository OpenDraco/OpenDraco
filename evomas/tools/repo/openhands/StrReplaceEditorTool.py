"""OpenHands `StrReplaceEditorTool` — multi-command file editor.

Supports five subcommands selected via the `command` argument:
- `view`     — print the file (or list a directory) with line numbers.
- `create`   — write a new file (fails if it already exists).
- `str_replace` — unique-substring replacement (errors if `old_str`
  matches zero or more-than-one occurrences).
- `insert`   — splice `new_str` after `insert_line`.
- `undo_edit` — revert the most recent edit at `path` from the
  in-memory undo stack.

Every mutating subcommand pushes the previous file contents onto the
shared `_UNDO_STACK` so `undo_edit` can restore them.
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from evomas.tools.repo.openhands._helpers import _UNDO_STACK, _file_view, _push_undo


@tool
def StrReplaceEditorTool(
    command: str,
    path: str,
    file_text: str | None = None,
    old_str: str | None = None,
    new_str: str | None = None,
    insert_line: int | None = None,
    view_range: list[int] | None = None,
) -> str:
    """Multi-command file editor. Dispatches on `command` (`view`,
    `create`, `str_replace`, `insert`, `undo_edit`). Returns a short
    status string on success or a `Error: ...` description on
    failure."""
    p = Path(path)
    if command == "view":
        if not p.exists():
            return f"Error: path {path} does not exist."
        return _file_view(p, view_range)

    if command == "create":
        if p.exists():
            return f"Error: file already exists at: {path}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(file_text or "", encoding="utf-8")
        return f"File created successfully at: {path}"

    if command == "str_replace":
        if not p.is_file():
            return f"Error: file does not exist: {path}"
        if old_str is None:
            return "Error: `old_str` is required for str_replace."
        text = p.read_text(encoding="utf-8", errors="replace")
        count = text.count(old_str)
        if count == 0:
            return "Error: `old_str` not found in file."
        if count > 1:
            return f"Error: `old_str` matched {count} times — make it unique."
        _push_undo(p)
        p.write_text(text.replace(old_str, new_str or "", 1), encoding="utf-8")
        return "The file has been edited."

    if command == "insert":
        if not p.is_file():
            return f"Error: file does not exist: {path}"
        if insert_line is None:
            return "Error: `insert_line` is required for insert."
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if not 0 <= insert_line <= len(lines):
            return f"Error: insert_line {insert_line} out of range [0, {len(lines)}]."
        _push_undo(p)
        lines = lines[:insert_line] + [(new_str or "")] + lines[insert_line:]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return "The file has been edited."

    if command == "undo_edit":
        key = str(p.resolve())
        stack = _UNDO_STACK.get(key) or []
        if not stack:
            return "Error: no edits to undo for this file."
        prev = stack.pop()
        p.write_text(prev, encoding="utf-8")
        return "Last edit reverted."

    return f"Error: unknown command {command!r}."
