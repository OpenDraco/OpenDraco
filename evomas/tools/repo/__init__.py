"""Repo-variant tool bundles borrowed from external SWE-bench agents
(openhands, swe_agent, patchwork, ...). Each subpackage exports its
tools via a `*_TOOLS` list; `evomas.mcp.server._discover_tools` walks
them recursively.

This file exists so the parent `evomas.tools` package picks `repo` up
via `pkgutil.iter_modules` — namespace packages (no `__init__.py`)
are skipped by iter_modules at the parent level.
"""
