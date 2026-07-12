"""augment_swebench_agent tool re-implementations.

Two augment-specific tools (`CompleteTool`, `SequentialThinkingTool`)
plus a re-export of the canonical OpenHands `StrReplaceEditorTool` —
augment's upstream `str_replace_tool` is the same exact-match editor;
re-exporting avoids a duplicate MCP registration.
"""
from evomas.tools.repo.augment_swebench_agent.SequentialThinkingTool import SequentialThinkingTool
from evomas.tools.repo.augment_swebench_agent.CompleteTool import CompleteTool
# `StrReplaceEditorTool` is the canonical OpenHands editor — augment's
# upstream `str_replace_tool` is the same tool under a different name.
# Re-exporting (not duplicating) avoids the last-write-wins clobber the
# lingma `search_code` collision exposed earlier.
from evomas.tools.repo.openhands.StrReplaceEditorTool import StrReplaceEditorTool

AUGMENT_SWEBENCH_AGENT_TOOLS = (
    SequentialThinkingTool,
    CompleteTool,
    # StrReplaceEditorTool is NOT included here — already registered with
    # MCP via the OpenHands bundle; the augment catalog's tool whitelist
    # references it by name and MCP resolves to the canonical.
)

__all__ = [
    "AUGMENT_SWEBENCH_AGENT_TOOLS",
    "SequentialThinkingTool",
    "CompleteTool",
    "StrReplaceEditorTool",
]
