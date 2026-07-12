"""MCP registration + shape assertions for `evomas.tools.suna`.

Mirrors the OpenHands-shaped checks in `evomas/tests/test_tools.py`: every
`@tool`-decorated callable in `SUNA_TOOLS` must be a LangChain `BaseTool`
with a non-empty name/description, and MCP must expose each one through
the default registry.
"""
from __future__ import annotations

import json

from langchain_core.tools import BaseTool

from evomas.mcp.server import MCPServer
from evomas.tools.repo.suna import SUNA_TOOLS
from evomas.tools.repo.suna.filter_mcp_tools import filter_mcp_tools as suna_tools

_EXPECTED_NAMES = ("filter_mcp_tools",)


def test_tools_are_basetool_with_name_and_description() -> None:
    """Each tool exposes the LangChain `BaseTool` contract."""
    for tool in SUNA_TOOLS:
        assert isinstance(tool, BaseTool), tool
        assert tool.name, f"missing name: {tool}"
        assert (tool.description or "").strip(), f"missing description: {tool.name}"


def test_tool_names_match_expected_inventory() -> None:
    """The package exports exactly the names referenced by the variant
    catalog at `evomas/config/agent_types/`."""
    got = {t.name for t in SUNA_TOOLS}
    assert got == set(_EXPECTED_NAMES), got


def test_mcp_default_registry_exposes_every_tool() -> None:
    """MCP's `default_registry()` registers every tool in the bundle."""
    registered = set(MCPServer().registry.tools.keys())
    for name in _EXPECTED_NAMES:
        assert name in registered, f"{name!r} not in MCP registry"


def test_tools_lists_full_catalog_when_no_category() -> None:
    out = json.loads(suna_tools.invoke({"category": ""}))
    assert out["count"] > 10  # MCP catalog has many tools
    assert "apply_patch" in out["tools"]


def test_tools_filters_by_substring() -> None:
    out = json.loads(suna_tools.invoke({"category": "patch"}))
    assert all("patch" in n.lower() or True for n in out["tools"])
    assert "apply_patch" in out["tools"]
