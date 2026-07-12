"""composio `MultiServerMCPClient_mcp` — emit an MCP catalog payload in
the shape `MultiServerMCPClient` from `langchain-mcp-adapters` expects.

Behavior-faithful re-implementation of the upstream composio
`python/examples/mcp.py` example script: returns the live EvoMas MCP
registry as a JSON list of `{name, description}` entries, ready to be
fed into a `MultiServerMCPClient` config. Renamed from the bare `mcp`
so the catalog name reveals the consumer (the upstream class the data
is shaped for).
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def MultiServerMCPClient_mcp() -> str:
    """List MCP-registered tools as JSON `[{name, description}]`."""
    from evomas.mcp.server import MCPServer
    catalog = [
        {"name": d.name, "description": d.description}
        for d in MCPServer().registry.tools.values()
    ]
    catalog.sort(key=lambda x: x["name"])
    logger.info("[composio.MultiServerMCPClient_mcp] catalog size=%d", len(catalog))
    return json.dumps(catalog)
