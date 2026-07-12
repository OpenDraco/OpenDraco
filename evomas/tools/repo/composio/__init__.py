"""composio tool re-implementations.

Mirror of `evomas.tools.openhands` for the composio repo. Each tool is a
LangChain `@tool`-decorated function exposed via `COMPOSIO_TOOLS` and registered
with the MCP server in `evomas.mcp.server.default_registry`.
"""
from evomas.tools.repo.composio.MultiServerMCPClient_langchain_agent import MultiServerMCPClient_langchain_agent
from evomas.tools.repo.composio.MultiServerMCPClient_mcp import MultiServerMCPClient_mcp
from evomas.tools.repo.composio.HostedMCPTool_openai_agents import HostedMCPTool_openai_agents
from evomas.tools.repo.composio.HostedMCPTool_tool_router_mcp import HostedMCPTool_tool_router_mcp

COMPOSIO_TOOLS = (
    MultiServerMCPClient_langchain_agent,
    MultiServerMCPClient_mcp,
    HostedMCPTool_openai_agents,
    HostedMCPTool_tool_router_mcp,
)

__all__ = [
    "COMPOSIO_TOOLS",
    "MultiServerMCPClient_langchain_agent",
    "MultiServerMCPClient_mcp",
    "HostedMCPTool_openai_agents",
    "HostedMCPTool_tool_router_mcp",
]
