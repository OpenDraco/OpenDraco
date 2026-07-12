"""composio `HostedMCPTool_tool_router_mcp` — pick the top-N MCP tools
most relevant to a query, shaped for an OpenAI-Agents `HostedMCPTool`
tool-router payload.

Behavior-faithful re-implementation of the data shape that the
upstream composio `tool_router/tool_router_mcp.py` example builds when
constructing a `HostedMCPTool` inside `def main()`. Renamed so the
consumer class is visible in the catalog name. Implementation uses
Jaccard token overlap with a substring fallback — fresh EvoMas code,
no upstream lines reused.
"""
from __future__ import annotations

import json
import logging
import re

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-z_]+")


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text or "") if len(w) > 2}


@tool
def HostedMCPTool_tool_router_mcp(query: str, top_k: int = 3) -> str:
    """Return the top-`top_k` MCP tools most relevant to `query` as
    JSON `[{name, description, score}]`. Score is jaccard token
    similarity; ties broken by name alpha order."""
    from evomas.mcp.server import MCPServer
    q = _tokens(query)
    scored: list[tuple[float, str, str]] = []
    for d in MCPServer().registry.tools.values():
        t = _tokens(f"{d.name} {d.description}")
        if not q or not t:
            score = 0.0
        else:
            score = len(q & t) / len(q | t)
        if score == 0 and query and query.lower() in (d.name + " " + d.description).lower():
            score = 0.01  # substring fallback
        if score > 0:
            scored.append((score, d.name, d.description))
    scored.sort(key=lambda r: (-r[0], r[1]))
    top = [{"name": n, "description": desc, "score": round(s, 3)} for s, n, desc in scored[:top_k]]
    logger.info("[composio.HostedMCPTool_tool_router_mcp] query=%r -> %d hits", query, len(top))
    return json.dumps(top)
