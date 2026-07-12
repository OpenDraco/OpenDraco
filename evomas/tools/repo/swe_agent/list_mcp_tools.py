"""swe_agent `list_mcp_tools` — manifest of every registered MCP tool.

The upstream SWE-agent has a `ToolHandler` class that's tightly coupled
to its own runtime (`ToolConfig`, `SWEEnv`, command-bundle install,
action-protocol parsing) — none of those concepts exist in EvoMas, where
tool dispatch is handled by MCP. So instead of porting a class that
wouldn't fit, this EvoMas-specific tool exposes the same kind of
introspection: a JSON manifest of every callable tool currently in the
MCP registry. The catalog name is `list_mcp_tools` rather than the
generic `tools` it used to carry, so its purpose is obvious from the
file/JSON name alone.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def list_mcp_tools() -> str:
    """Return a JSON manifest of every MCP-registered tool: a list of
    `{name, description, inputSchema}` objects. Use this to discover
    available capabilities mid-run."""
    from evomas.mcp.server import MCPServer
    manifest = MCPServer().registry.list()
    logger.info("[swe_agent.list_mcp_tools] manifest size=%d", len(manifest))
    return json.dumps(manifest)
