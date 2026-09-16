"""debug_gym tool re-implementations.

Mirror of `opendraco.tools.openhands` for the debug_gym repo. Each tool is a
LangChain `@tool`-decorated function exposed via `DEBUG_GYM_TOOLS` and registered
with the MCP server in `opendraco.mcp.server.default_registry`.
"""
from opendraco.tools.repo.debug_gym.EnvironmentTool import EnvironmentTool

DEBUG_GYM_TOOLS = (EnvironmentTool,)

__all__ = ["DEBUG_GYM_TOOLS", "EnvironmentTool"]
