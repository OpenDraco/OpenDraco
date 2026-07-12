"""MCP registration + shape assertions for `evomas.tools.auto_code_rover`.

After the `common.py` removal, the bundle exposes a single tool —
`agent_write_patch`. This file mirrors the OpenHands-shaped checks in
`evomas/tests/test_tools.py`: every `@tool`-decorated callable in
`AUTO_CODE_ROVER_TOOLS` must be a LangChain `BaseTool` with a non-empty
name/description, and MCP must expose each one through the default
registry.
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import BaseTool

from evomas.mcp.server import MCPServer
from evomas.tools.repo.auto_code_rover import agent_write_patch
from evomas.tools.repo.auto_code_rover import AUTO_CODE_ROVER_TOOLS

_EXPECTED_NAMES = ("agent_write_patch",)


def test_tools_are_basetool_with_name_and_description() -> None:
    """Each tool exposes the LangChain `BaseTool` contract."""
    for tool in AUTO_CODE_ROVER_TOOLS:
        assert isinstance(tool, BaseTool), tool
        assert tool.name, f"missing name: {tool}"
        assert (tool.description or "").strip(), f"missing description: {tool.name}"


def test_tool_names_match_expected_inventory() -> None:
    """The package exports exactly the names referenced by the variant
    catalog at `evomas/config/agent_types/`."""
    got = {t.name for t in AUTO_CODE_ROVER_TOOLS}
    assert got == set(_EXPECTED_NAMES), got


def test_mcp_default_registry_exposes_every_tool() -> None:
    """MCP's `default_registry()` registers every tool in the bundle."""
    registered = set(MCPServer().registry.tools.keys())
    for name in _EXPECTED_NAMES:
        assert name in registered, f"{name!r} not in MCP registry"


def test_agent_write_patch_applies_diff(buggy_repo: Path) -> None:
    patch = (
        "diff --git a/calc.py b/calc.py\n"
        "--- a/calc.py\n"
        "+++ b/calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )
    result = agent_write_patch.invoke({"patch": patch, "repo_path": str(buggy_repo)})
    assert result == "ok"
    assert "return a + b" in (buggy_repo / "calc.py").read_text()
