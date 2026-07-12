"""Websearch-task tool bundle. Imported for side effects so the
`@tool`-decorated `websearch` + `save_text` register with the MCP
registry that the JSON config's `tools: [{"name": "..."}]` looks up
by name.
"""
from evomas.tools.websearch.save_text import save_text
from evomas.tools.websearch.websearch import websearch

__all__ = ["websearch", "save_text"]
WEBSEARCH_TOOLS = [websearch, save_text]
