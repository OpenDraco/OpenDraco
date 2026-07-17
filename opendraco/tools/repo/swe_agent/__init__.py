"""swe_agent tool re-implementations.

Mirror of `opendraco.tools.openhands` for the swe_agent repo. Each tool is a
LangChain `@tool`-decorated function exposed via `SWE_AGENT_TOOLS` and registered
with the MCP server in `opendraco.mcp.server.default_registry`.
"""
from opendraco.tools.repo.swe_agent.list_mcp_tools import list_mcp_tools

SWE_AGENT_TOOLS = (list_mcp_tools,)

__all__ = ["SWE_AGENT_TOOLS", "list_mcp_tools"]
