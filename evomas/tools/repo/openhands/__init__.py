"""OpenHands tool re-implementations — one per file under the
upstream-aligned tool names.

Each module exposes a single `@tool`-decorated function whose name
matches the upstream OpenHands tool identifier (e.g. `BrowserTool`,
`CmdRunTool`, …) so prompts referencing those names continue to
resolve. Implementations are EvoMas-authored Python wrappers — they
share a small `_helpers` module for output truncation, file viewing,
edit-undo, and bash dispatch.
"""

from evomas.tools.repo.openhands.BrowserTool import BrowserTool
from evomas.tools.repo.openhands.CmdRunTool import CmdRunTool
from evomas.tools.repo.openhands.CondensationRequestTool import CondensationRequestTool
from evomas.tools.repo.openhands.FinishTool import FinishTool
from evomas.tools.repo.openhands.GlobTool import GlobTool
from evomas.tools.repo.openhands.GrepTool import GrepTool
from evomas.tools.repo.openhands.IPythonTool import IPythonTool
from evomas.tools.repo.openhands.LLMBasedFileEditTool import LLMBasedFileEditTool
from evomas.tools.repo.openhands.StrReplaceEditorTool import StrReplaceEditorTool
from evomas.tools.repo.openhands.ThinkTool import ThinkTool
from evomas.tools.repo.openhands.ViewTool import ViewTool

from evomas.tools.repo.openhands.loc_tools import (
    LOC_TOOLS,
    explore_tree_structure,
    get_entity_contents,
    search_code_snippets,
)

OPENHANDS_TOOLS = (
    BrowserTool,
    CmdRunTool,
    CondensationRequestTool,
    FinishTool,
    GlobTool,
    GrepTool,
    IPythonTool,
    LLMBasedFileEditTool,
    StrReplaceEditorTool,
    ThinkTool,
    ViewTool,
)

__all__ = [
    "OPENHANDS_TOOLS",
    "LOC_TOOLS",
    "BrowserTool",
    "CmdRunTool",
    "CondensationRequestTool",
    "FinishTool",
    "GlobTool",
    "GrepTool",
    "IPythonTool",
    "LLMBasedFileEditTool",
    "StrReplaceEditorTool",
    "ThinkTool",
    "ViewTool",
    "explore_tree_structure",
    "get_entity_contents",
    "search_code_snippets",
]
