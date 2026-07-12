"""MCP registration + behavior checks for `evomas.tools.trae_agent`.

The trae-agent bundle contains 3 trae-specific tools (`CKGTool`,
`JSONEditTool`, `TaskDoneTool`) and re-exports 3 canonicals
(`CmdRunTool`, `StrReplaceEditorTool`, `SequentialThinkingTool`) from
the OpenHands / augment bundles. The catalog's `tools[].name` strings
for the canonicals resolve via those bundles in MCP — the trae
aggregate avoids duplicate registration.
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import BaseTool

from evomas.mcp.server import MCPServer
from evomas.tools.repo.trae_agent import TRAE_AGENT_TOOLS
from evomas.tools.repo.trae_agent import (
    CKGTool,
    JSONEditTool,
    TaskDoneTool,
)

# The 3 trae-specific names registered locally via this bundle.
_LOCAL_NAMES = ("CKGTool", "JSONEditTool", "TaskDoneTool")

# All 6 names the trae catalog references — locals + re-exported
# canonicals. Each must resolve in MCP regardless of which bundle
# actually owns the registration.
_CATALOG_NAMES = (
    "CKGTool",
    "JSONEditTool",
    "TaskDoneTool",
    "CmdRunTool",            # re-exported from openhands
    "StrReplaceEditorTool",  # re-exported from openhands
    "SequentialThinkingTool",  # re-exported from augment_swebench_agent
)


def test_local_aggregate_holds_only_trae_specific_tools() -> None:
    """Re-exported canonicals are NOT in TRAE_AGENT_TOOLS to avoid the
    last-write-wins MCP clobber. Their registration happens via the
    owning bundles in `evomas/mcp/server.py:default_registry`."""
    assert {t.name for t in TRAE_AGENT_TOOLS} == set(_LOCAL_NAMES)


def test_local_tools_are_basetool_with_name_and_description() -> None:
    for tool in TRAE_AGENT_TOOLS:
        assert isinstance(tool, BaseTool), tool
        assert tool.name, f"missing name: {tool}"
        assert (tool.description or "").strip(), f"missing description: {tool.name}"


def test_mcp_default_registry_exposes_every_catalog_tool() -> None:
    """MCP exposes every name the trae catalog references — locals via
    this bundle, canonicals via openhands / augment bundles."""
    registered = set(MCPServer().registry.tools.keys())
    for name in _CATALOG_NAMES:
        assert name in registered, f"{name!r} not in MCP registry"


def test_task_done_tool_writes_workspace_marker(buggy_repo: Path) -> None:
    record = json.loads(TaskDoneTool.invoke({
        "result": "done", "workspace": str(buggy_repo), "agent": "trae-test",
    }))
    assert record["completed"] is True
    assert (buggy_repo / ".evomas" / "state.json").is_file()


def test_ckg_tool_lists_top_level_symbols(buggy_repo: Path) -> None:
    out = CKGTool.invoke({"path": str(buggy_repo / "calc.py")})
    assert "def add" in out
    assert "def multiply" in out


def test_json_edit_tool_round_trips(buggy_repo: Path) -> None:
    target = buggy_repo / "data.json"
    target.write_text('{"a": 1}', encoding="utf-8")
    out = JSONEditTool.invoke({"path": str(target), "key": "b", "value": "2"})
    assert out == "ok"
    data = json.loads(target.read_text())
    assert data == {"a": 1, "b": 2}
