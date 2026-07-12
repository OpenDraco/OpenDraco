"""Router — thin LLM-driven dispatcher that picks the next worker agent(s) to run.

Lives at `evomas/agents/router.py` (not under `types/`) because routing is a
core control-flow primitive of the graph runtime, not a domain agent role.
The graph builder's conditional-edge wiring keys on `isinstance(agent, Router)`
to decide which nodes get an LLM-driven router vs static fan-out.

This class was previously named `Orchestrator` and lived in
`evomas/agents/types/orchestrator.py`. It was renamed to `Router` because its
actual job is routing (one-line dispatch), not planning. The new
`PlannerOrchestrator` agent type under `evomas/agents/types/` describes the
necessary code changes BEFORE handing off, matching the thesis's
"Planner/Orchestrator" definition.
"""
from __future__ import annotations

from typing import Any, ClassVar

from evomas.agents.llm_tool_agent import LLMToolAgent


class Router(LLMToolAgent):
    """Thin LLM gateway with no tools that emits a one-line dispatch ack; the graph builder does the actual routing."""

    AGENT_TYPE: ClassVar[str] = "Router"
    name = "router"

    OUTPUT_TYPE: ClassVar[Any] = str
    OUTPUT_DEFAULT: ClassVar[str] = ""

    DEFAULT_SYSTEM: ClassVar[str] = (
        "You are the Router of a multi-agent automated "
        "software-repair pipeline. You do not edit code yourself; you "
        "decide which worker agent(s) should run next.\n\n"
        "Respond with a SINGLE line containing the names of the next "
        "agent(s) to dispatch, separated by spaces or commas. The exact "
        "agent names are listed in the user prompt. The graph runtime "
        "parses your reply for whole-word matches of those names and "
        "routes the run accordingly. Emit NO tool calls — the base agent "
        "loop exits as soon as you respond without one."
    )
    DEFAULT_USER: ClassVar[str] = (
        "## Issue\n{issue}\n\n## Workspace\n{workspace}\n\n"
        "Decide the next step and respond with a one-line dispatch."
    )
    DEFAULT_TOOLS: ClassVar[tuple[str, ...]] = ()
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {
        "temperature":  0.0,
        "num_ctx":      2048,
        "num_predict":  512,
    }
