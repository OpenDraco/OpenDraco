"""composio `HostedMCPTool_openai_agents` — emit the agent registry
from an EvoMas config in the shape an OpenAI-Agents `HostedMCPTool`
caller expects.

Behavior-faithful re-implementation of the data shape that the
upstream composio `tool_router/openai_agents.py` example builds when
constructing a `HostedMCPTool` (from `openai-agents`). Renamed from
`openai_agents` so the consumer class is visible in the catalog name.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def HostedMCPTool_openai_agents(config: str = "chain") -> str:
    """List the agents in `config` (default: the `chain` predefined
    topology) reshaped as `[{name, instructions, model}]` — the schema
    OpenAI's Agents SDK consumes."""
    from evomas.config.loader import load_config
    try:
        cfg = load_config(config)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc), "config": config})
    out = []
    for name, block in (cfg.get("agents") or {}).items():
        prompts = block.get("prompts") or {}
        out.append({
            "name": name,
            "instructions": prompts.get("system", "") or block.get("class", ""),
            "model": block.get("model", ""),
        })
    logger.info("[composio.HostedMCPTool_openai_agents] config=%s -> %d agents", config, len(out))
    return json.dumps(out)
