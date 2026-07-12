"""suna `filter_mcp_tools` — keyword-filtered listing of MCP tools.

The upstream Suna framework exposes its tools under a `tools` namespace.
The closest useful EvoMas operation is "list the tools I can call
(optionally filtered by keyword)" — implemented against the live MCP
registry. Renamed from `tools` so the catalog name describes what the
function actually does (and parallels `swe_agent.list_mcp_tools`).
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def filter_mcp_tools(category: str = "") -> str:
    """List MCP-registered tool names, optionally filtered to names or
    descriptions containing `category` (case-insensitive substring).
    Returns JSON `{tools: [...], count: N}`."""
    from evomas.mcp.server import MCPServer
    cat = (category or "").strip().lower()
    out: list[str] = []
    for descriptor in MCPServer().registry.tools.values():
        haystack = f"{descriptor.name} {descriptor.description}".lower()
        if not cat or cat in haystack:
            out.append(descriptor.name)
    out.sort()
    logger.info("[suna.filter_mcp_tools] category=%r -> %d tools", category, len(out))
    return json.dumps({"tools": out, "count": len(out)})
