"""debug_gym tool re-implementations.

Mirror of `evomas.tools.openhands` for the debug_gym repo. Each tool is a
LangChain `@tool`-decorated function exposed via `DEBUG_GYM_TOOLS` and registered
with the MCP server in `evomas.mcp.server.default_registry`.
"""
from evomas.tools.repo.debug_gym.EnvironmentTool import EnvironmentTool

DEBUG_GYM_TOOLS = (EnvironmentTool,)

__all__ = ["DEBUG_GYM_TOOLS", "EnvironmentTool"]
