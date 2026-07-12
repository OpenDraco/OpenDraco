"""composio `MultiServerMCPClient_langchain_agent` — emit the agent
registry from an EvoMas config in the shape a LangChain agent backed
by `MultiServerMCPClient` consumes.

Behavior-faithful re-implementation of the data shape that the
upstream composio `tool_router/langchain_agent.py` example builds
inside `async def main()` when wiring a `MultiServerMCPClient` into a
LangChain runnable. Renamed from `langchain_agent` to make the
consumer-class context explicit.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def MultiServerMCPClient_langchain_agent(config: str = "chain") -> str:
    """List the agents in `config` (default: the `chain` predefined
    topology) as JSON `[{name, class, model, tools}]`."""
    from evomas.config.loader import load_config
    try:
        cfg = load_config(config)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc), "config": config})
    agents = []
    for name, block in (cfg.get("agents") or {}).items():
        agents.append({
            "name": name,
            "class": block.get("class", ""),
            "model": block.get("model", ""),
            "tools": [t.get("name") for t in (block.get("tools") or []) if isinstance(t, dict)],
        })
    logger.info("[composio.MultiServerMCPClient_langchain_agent] config=%s -> %d agents", config, len(agents))
    return json.dumps(agents)
