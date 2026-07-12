"""Translate-task tool bundle. Imported for side effects so the
`@tool`-decorated `write_file` registers with the MCP registry that
the JSON config's `tools: [{"name": "write_file"}]` looks up by name.
"""
from evomas.tools.translate.write_file import write_file

__all__ = ["write_file"]
TRANSLATE_TOOLS = [write_file]
