"""claude_coder `spawnAgentTool` — sub-agent spawn placeholder.

EvoMas spawns agents via the **topology graph** (LangGraph edges,
super-step scheduling) rather than through an in-tool runtime call.
A tool that requests "spawn a sub-agent" is conceptually a no-op here:
the orchestrator decides routing, not the tool layer. Returns a
structured signal the orchestrator/Helper agent can pick up if it
wants to honor the request.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def spawnAgentTool(agent_type: str = "", task: str = "") -> str:
    """Record a spawn intent for the orchestrator. The actual routing
    happens via the topology graph — this tool just emits the JSON
    envelope. Returns `{request, agent_type, task, ok}`."""
    payload = {
        "request": "spawn_agent",
        "agent_type": agent_type,
        "task": task,
        "ok": True,
        "note": "EvoMas spawns sub-agents via topology edges, not via tool call; this is an advisory signal.",
    }
    logger.info("[claude_coder.spawnAgentTool] %s", payload)
    return json.dumps(payload)
