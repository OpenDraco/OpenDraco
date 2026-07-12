"""Planner/Orchestrator — separates plan-then-execute by describing the necessary
code changes BEFORE handing off to a coder agent.

Distinguished from `Router` (in `evomas/agents/router.py`): the Router is a
*thin* one-line dispatcher with no domain knowledge. The PlannerOrchestrator
does a real planning pass — it reads the issue, sketches the change in
3-5 bullet points, and dispatches to the worker(s) with that plan attached.

Downstream agents receive the plan via `state["planner_orchestrator"]` (the
predecessor slot). The graph builder still uses the LLM-emitted dispatch
line for conditional routing, identically to how it treats a `Router` node
with ≥2 outgoing edges — so a PlannerOrchestrator in a hub position behaves
as both planner AND router.
"""
from __future__ import annotations

from typing import Any, ClassVar

from evomas.agents.llm_tool_agent import LLMToolAgent


class PlannerOrchestrator(LLMToolAgent):
    """Architectural decision-maker: describes the necessary code changes and delegates the actual editing to a designated coder agent."""

    AGENT_TYPE: ClassVar[str] = "Planner/Orchestrator"
    name = "planner_orchestrator"

    OUTPUT_TYPE: ClassVar[Any] = str
    OUTPUT_DEFAULT: ClassVar[str] = ""

    DEFAULT_SYSTEM: ClassVar[str] = (
        "You are the Planner/Orchestrator of a multi-agent automated "
        "software-repair pipeline. You do NOT edit code yourself; you "
        "separate planning from execution.\n\n"
        "## Output shape (one block, no tool calls)\n"
        "1. `## Plan` — a 3-5-bullet description of the minimal code\n"
        "   changes needed to fix the issue. Reference files / functions\n"
        "   when you can.\n"
        "2. `## Dispatch` — a SINGLE final line containing the names of\n"
        "   the next worker agent(s) to run, separated by spaces or\n"
        "   commas. The graph runtime parses this line for whole-word\n"
        "   matches against the agent names listed in the user prompt.\n\n"
        "## Anti-patterns\n"
        "- Calling any tool (you have none).\n"
        "- Emitting code or unified-diff text in the plan — that's the\n"
        "  coder agent's job.\n"
        "- Skipping the `## Dispatch` line — the run stalls without it."
    )
    DEFAULT_USER: ClassVar[str] = (
        "## Issue\n{issue}\n\n## Workspace\n{workspace}\n\n"
        "Produce the `## Plan` section, then a `## Dispatch` line naming\n"
        "the next worker agent(s) to run."
    )
    DEFAULT_TOOLS: ClassVar[tuple[str, ...]] = ()
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {
        "temperature":  0.2,
        "num_ctx":      4096,
        "num_predict":  768,
    }
