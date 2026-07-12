"""MCP registration + re-export checks for `evomas.tools.joycode_agent`.

joycode-agent's three upstream tools are functionally identical to
augment-swebench-agent + OpenHands counterparts, so the joycode bundle
re-exports the canonical symbols rather than duplicate-registering. The
bundle's aggregate is therefore intentionally empty; the catalog's
`tools[].name` strings resolve to the canonical tools at MCP runtime.
"""
from __future__ import annotations

from evomas.mcp.server import MCPServer
from evomas.tools.repo.joycode_agent import (
    JOYCODE_AGENT_TOOLS,
    CompleteTool,
    SequentialThinkingTool,
    StrReplaceEditorTool,
)

# The names the catalog references. Each must resolve in MCP via its
# canonical bundle (augment_swebench_agent or openhands).
_EXPECTED_NAMES = ("CompleteTool", "SequentialThinkingTool", "StrReplaceEditorTool")


def test_aggregate_is_intentionally_empty() -> None:
    """Joycode-agent re-exports canonical symbols, so the bundle's own
    tuple is empty. Document the intent so a future contributor doesn't
    'fix' it by re-adding duplicates."""
    assert JOYCODE_AGENT_TOOLS == ()


def test_reexports_resolve() -> None:
    """The 3 symbols re-exported via `evomas.tools.joycode_agent` are
    the canonical LangChain BaseTool callables."""
    from langchain_core.tools import BaseTool
    for t in (CompleteTool, SequentialThinkingTool, StrReplaceEditorTool):
        assert isinstance(t, BaseTool), t
        assert t.name and (t.description or "").strip()


def test_mcp_default_registry_exposes_every_tool() -> None:
    """MCP's `default_registry()` registers every catalog-referenced
    tool via the canonical bundle."""
    registered = set(MCPServer().registry.tools.keys())
    for name in _EXPECTED_NAMES:
        assert name in registered, f"{name!r} not in MCP registry"
