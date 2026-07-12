"""patchwork `code_edit_tools` tool.

Upstream reference: https://github.com/patched-codes/patchwork/blob/main/patchwork/steps/ModifyCode/ModifyCode.py
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


from evomas.tools.repo.openhands.StrReplaceEditorTool import StrReplaceEditorTool as _editor


@tool
def code_edit_tools(
    path: str,
    old_str: str | None = None,
    new_str: str | None = None,
    file_text: str | None = None,
    insert_line: int | None = None,
    view_range: list[int] | None = None,
    command: str = "str_replace",
) -> str:
    """Exact-match string replacement in a file (openhands str_replace_editor
    semantics). `command` accepts view/create/str_replace/insert/undo_edit."""
    return _editor.invoke({
        "command": command,
        "path": path,
        "old_str": old_str,
        "new_str": new_str,
        "file_text": file_text,
        "insert_line": insert_line,
        "view_range": view_range,
    })
