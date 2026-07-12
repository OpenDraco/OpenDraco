"""joycode_agent tool re-exports.

joycode-agent's three upstream tools (`CompleteTool`,
`SequentialThinkingTool`, `StrReplaceEditorTool`) are functionally
identical to augment-swebench-agent + OpenHands counterparts (verified
diff: same body modulo docstrings and a default agent-string). Rather
than duplicate-register them with MCP (and clobber each other under
last-write-wins), we re-export the canonical symbols. The joycode
catalog's `tools[].name` resolves to the canonical at runtime.
"""
from evomas.tools.repo.augment_swebench_agent.SequentialThinkingTool import SequentialThinkingTool
from evomas.tools.repo.augment_swebench_agent.CompleteTool import CompleteTool
from evomas.tools.repo.openhands.StrReplaceEditorTool import StrReplaceEditorTool

# Empty aggregate — every tool is already registered with MCP via its
# canonical owning bundle (augment_swebench_agent or openhands).
JOYCODE_AGENT_TOOLS: tuple = ()

__all__ = [
    "JOYCODE_AGENT_TOOLS",
    "SequentialThinkingTool",
    "CompleteTool",
    "StrReplaceEditorTool",
]
