"""augment_swebench_agent `SequentialThinkingTool` — record one step of
multi-step reasoning.

Behavior-faithful interface mirror of the upstream augment-swebench-agent
`SequentialThinkingTool`: distinct from a one-shot `ThinkTool` because
each call carries a step counter the orchestrator can use to reconstruct
the chain. EvoMas-authored body — pure logging, no shared cross-tool
state, each call is self-contained.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def SequentialThinkingTool(
    thought: str,
    step: int = 0,
    total: int = 0,
    agent: str = "augment",
) -> str:
    """Record a thought for `agent` and return JSON
    `{agent, step, total, thought}`. The orchestrator's text log captures
    every call so the trajectory is reconstructable post-run."""
    summary = {"agent": agent, "step": step, "total": total, "thought": thought}
    logger.info("[augment.thinking] %s", summary)
    return json.dumps(summary)
