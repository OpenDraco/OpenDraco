"""MCP registration + shape assertions for `evomas.tools.composio`.

Mirrors the OpenHands-shaped checks in `evomas/tests/test_tools.py`: every
`@tool`-decorated callable in `COMPOSIO_TOOLS` must be a LangChain `BaseTool`
with a non-empty name/description, and MCP must expose each one through
the default registry.
"""
from __future__ import annotations

import json

from langchain_core.tools import BaseTool

from evomas.mcp.server import MCPServer
from evomas.tools.repo.composio import (
    MultiServerMCPClient_langchain_agent as langchain_agent,
    MultiServerMCPClient_mcp as composio_mcp,
    HostedMCPTool_openai_agents as openai_agents,
    HostedMCPTool_tool_router_mcp as tool_router_mcp,
)
from evomas.tools.repo.composio import COMPOSIO_TOOLS

_EXPECTED_NAMES = (
    "MultiServerMCPClient_langchain_agent",
    "MultiServerMCPClient_mcp",
    "HostedMCPTool_openai_agents",
    "HostedMCPTool_tool_router_mcp",
)


def test_tools_are_basetool_with_name_and_description() -> None:
    """Each tool exposes the LangChain `BaseTool` contract."""
    for tool in COMPOSIO_TOOLS:
        assert isinstance(tool, BaseTool), tool
        assert tool.name, f"missing name: {tool}"
        assert (tool.description or "").strip(), f"missing description: {tool.name}"


def test_tool_names_match_expected_inventory() -> None:
    """The package exports exactly the names referenced by the variant
    catalog at `evomas/config/agent_types/`."""
    got = {t.name for t in COMPOSIO_TOOLS}
    assert got == set(_EXPECTED_NAMES), got


def test_mcp_default_registry_exposes_every_tool() -> None:
    """MCP's `default_registry()` registers every tool in the bundle."""
    registered = set(MCPServer().registry.tools.keys())
    for name in _EXPECTED_NAMES:
        assert name in registered, f"{name!r} not in MCP registry"


def test_mcp_returns_catalog() -> None:
    catalog = json.loads(composio_mcp.invoke({}))
    assert isinstance(catalog, list) and catalog
    names = {entry["name"] for entry in catalog}
    assert "apply_patch" in names


def test_tool_router_mcp_finds_patch_tools() -> None:
    hits = json.loads(tool_router_mcp.invoke({"query": "apply unified diff patch"}))
    assert isinstance(hits, list)
    assert any("patch" in h["name"].lower() for h in hits)


def test_langchain_agent_lists_chain_agents() -> None:
    agents = json.loads(langchain_agent.invoke({"config": "chain"}))
    names = {a["name"] for a in agents}
    assert {"locator", "patcher", "reviewer", "finalizer"}.issubset(names)
    for a in agents:
        assert a["model"].startswith("ollama/")


def test_openai_agents_reshapes_for_oai_sdk() -> None:
    agents = json.loads(openai_agents.invoke({"config": "chain"}))
    assert {"name", "instructions", "model"}.issubset(agents[0].keys())
