"""claude_coder `fileEditorTool` — multi-command file editor.

Delegates to the canonical OpenHands `StrReplaceEditorTool`, which
already supports view / create / str_replace / insert / undo_edit.
The catalog name (`fileEditorTool`) stays upstream-aligned; the
implementation reuses the proven canonical so behavior is consistent
across repos.
"""
from __future__ import annotations

from langchain_core.tools import tool

from evomas.tools.repo.openhands.StrReplaceEditorTool import StrReplaceEditorTool as _editor


@tool
def fileEditorTool(
    command: str,
    path: str,
    file_text: str | None = None,
    old_str: str | None = None,
    new_str: str | None = None,
    insert_line: int | None = None,
    view_range: list[int] | None = None,
) -> str:
    """Run an editor command against `path`. `command` is one of
    `view`, `create`, `str_replace`, `insert`, `undo_edit` — see the
    OpenHands `StrReplaceEditorTool` docstring for the per-command
    contract."""
    return _editor.invoke({
        "command": command,
        "path": path,
        "file_text": file_text,
        "old_str": old_str,
        "new_str": new_str,
        "insert_line": insert_line,
        "view_range": view_range,
    })
