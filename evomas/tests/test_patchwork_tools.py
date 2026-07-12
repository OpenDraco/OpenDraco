"""MCP registration + shape assertions for `evomas.tools.patchwork`.

Mirrors the OpenHands-shaped checks in `evomas/tests/test_tools.py`: every
`@tool`-decorated callable in `PATCHWORK_TOOLS` must be a LangChain `BaseTool`
with a non-empty name/description, and MCP must expose each one through
the default registry.
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import BaseTool

from evomas.mcp.server import MCPServer
from evomas.tools.repo.patchwork import PATCHWORK_TOOLS
from evomas.tools.repo.patchwork.workspace_manifest import workspace_manifest as patchwork_tool

_EXPECTED_NAMES = ("code_edit_tools", "csvkit_tool", "git_tool", "grep_tool", "workspace_manifest",)


def test_tools_are_basetool_with_name_and_description() -> None:
    """Each tool exposes the LangChain `BaseTool` contract."""
    for tool in PATCHWORK_TOOLS:
        assert isinstance(tool, BaseTool), tool
        assert tool.name, f"missing name: {tool}"
        assert (tool.description or "").strip(), f"missing description: {tool.name}"


def test_tool_names_match_expected_inventory() -> None:
    """The package exports exactly the names referenced by the variant
    catalog at `evomas/config/agent_types/`."""
    got = {t.name for t in PATCHWORK_TOOLS}
    assert got == set(_EXPECTED_NAMES), got


def test_mcp_default_registry_exposes_every_tool() -> None:
    """MCP's `default_registry()` registers every tool in the bundle."""
    registered = set(MCPServer().registry.tools.keys())
    for name in _EXPECTED_NAMES:
        assert name in registered, f"{name!r} not in MCP registry"


def test_tool_manifest_lists_source_files(buggy_repo: Path) -> None:
    """`patchwork.workspace_manifest` returns a JSON manifest of .py files."""
    out = json.loads(patchwork_tool.invoke({"workspace": str(buggy_repo)}))
    paths = [f["path"] for f in out["files"]]
    assert "calc.py" in paths
    assert "test_calc.py" in paths
    assert out["count"] == len(out["files"])
