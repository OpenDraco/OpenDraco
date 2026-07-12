"""MCP registration + shape assertions for `evomas.tools.debug_gym`.

Mirrors the OpenHands-shaped checks in `evomas/tests/test_tools.py`: every
`@tool`-decorated callable in `DEBUG_GYM_TOOLS` must be a LangChain `BaseTool`
with a non-empty name/description, and MCP must expose each one through
the default registry.
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import BaseTool

from evomas.mcp.server import MCPServer
from evomas.tools.repo.debug_gym import DEBUG_GYM_TOOLS
from evomas.tools.repo.debug_gym.EnvironmentTool import EnvironmentTool as debug_gym_tool

_EXPECTED_NAMES = ("EnvironmentTool",)


def test_tools_are_basetool_with_name_and_description() -> None:
    """Each tool exposes the LangChain `BaseTool` contract."""
    for tool in DEBUG_GYM_TOOLS:
        assert isinstance(tool, BaseTool), tool
        assert tool.name, f"missing name: {tool}"
        assert (tool.description or "").strip(), f"missing description: {tool.name}"


def test_tool_names_match_expected_inventory() -> None:
    """The package exports exactly the names referenced by the variant
    catalog at `evomas/config/agent_types/`."""
    got = {t.name for t in DEBUG_GYM_TOOLS}
    assert got == set(_EXPECTED_NAMES), got


def test_mcp_default_registry_exposes_every_tool() -> None:
    """MCP's `default_registry()` registers every tool in the bundle."""
    registered = set(MCPServer().registry.tools.keys())
    for name in _EXPECTED_NAMES:
        assert name in registered, f"{name!r} not in MCP registry"


def test_tool_lists_test_files(buggy_repo: Path) -> None:
    """`debug_gym.EnvironmentTool` enumerates pytest-discoverable test files."""
    out = json.loads(debug_gym_tool.invoke({"workspace": str(buggy_repo)}))
    assert "test_calc.py" in out["tests"]
    assert out["count"] == len(out["tests"]) >= 1
