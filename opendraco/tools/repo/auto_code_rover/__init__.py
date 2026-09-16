"""auto_code_rover tool re-implementations.

Mirror of `opendraco.tools.openhands` for the auto-code-rover repo. Each tool
is a LangChain `@tool`-decorated function exposed via `AUTO_CODE_ROVER_TOOLS`
and registered with the MCP server in `opendraco.mcp.server.default_registry`.
"""
from opendraco.tools.repo.auto_code_rover.agent_write_patch import agent_write_patch

AUTO_CODE_ROVER_TOOLS = (agent_write_patch,)

__all__ = ["AUTO_CODE_ROVER_TOOLS", "agent_write_patch"]
