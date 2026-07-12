"""trae_agent tool re-implementations.

Three trae-specific tools (`CKGTool`, `JSONEditTool`, `TaskDoneTool`)
are registered locally. The other three upstream trae tools are
functionally identical to canonicals owned by other bundles, so we
re-export instead of duplicate-registering:

- `BashTool` (trae) === `CmdRunTool` (OpenHands) — same shell-subprocess
- `EditTool` / `TextEditorTool` (trae) === `StrReplaceEditorTool` (OpenHands)
- `SequentialThinkingTool` (trae) === `SequentialThinkingTool` (augment)

`TaskDoneTool` is byte-equivalent to `CompleteTool` but kept as a
separate MCP registration because trae's upstream uses this distinct
name (per the project's "upstream-aligned names" policy).
"""
from evomas.tools.repo.trae_agent.CKGTool import CKGTool
from evomas.tools.repo.trae_agent.JSONEditTool import JSONEditTool
from evomas.tools.repo.trae_agent.TaskDoneTool import TaskDoneTool

# Re-exports from canonical bundles (no duplicate MCP registration).
from evomas.tools.repo.openhands.CmdRunTool import CmdRunTool
from evomas.tools.repo.openhands.StrReplaceEditorTool import StrReplaceEditorTool
from evomas.tools.repo.augment_swebench_agent.SequentialThinkingTool import SequentialThinkingTool

TRAE_AGENT_TOOLS = (
    CKGTool,
    JSONEditTool,
    TaskDoneTool,
    # The re-exported canonicals are already in MCP via their owning
    # bundles — listing them here would double-register.
)

__all__ = [
    "TRAE_AGENT_TOOLS",
    "CKGTool",
    "JSONEditTool",
    "TaskDoneTool",
    "CmdRunTool",
    "StrReplaceEditorTool",
    "SequentialThinkingTool",
]
