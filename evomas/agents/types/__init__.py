"""Per-type agent base classes for the SWE-bench AGENT_TYPE taxonomy, plus the color palette `/api/agent-types` serves to the frontend (single source of truth for UI palette + node coloring)."""
from __future__ import annotations

from typing import Any

from evomas.agents.base_agent import BaseAgent
from evomas.agents.router import Router
from evomas.agents.types.bug_reproduction import BugReproductionAgent
from evomas.agents.types.environment_setup import EnvironmentSetupAgent
from evomas.agents.types.generic_agent import GenericAgent
from evomas.agents.types.helper_proxy import HelperProxyAgent
from evomas.agents.types.locator import LocatorAgent
from evomas.agents.types.patcher import PatcherAgent
from evomas.agents.types.planner_orchestrator import PlannerOrchestrator
from evomas.agents.types.reviewer import ReviewerAgent

# Ordered as in the SWE-bench AgentType.csv so the frontend palette renders
# them consistently. Each type is registered TWICE so a config block can spell
# `class` as either the AGENT_TYPE label ("Locator") or the Python class name
# ("LocatorAgent") -- both resolve via AGENT_REGISTRY in runner.py.
#
# Router lives at `evomas/agents/router.py` (not under types/) because routing
# is a core control-flow primitive of the graph runtime, not a domain role;
# but it's still part of the AGENT_TYPE taxonomy so it's re-exported here.
_TYPES: tuple[type[BaseAgent], ...] = (
    LocatorAgent,
    PatcherAgent,
    HelperProxyAgent,
    PlannerOrchestrator,
    Router,
    GenericAgent,
    BugReproductionAgent,
    EnvironmentSetupAgent,
    ReviewerAgent,
)
TYPE_REGISTRY: dict[str, type[BaseAgent]] = {}
for _cls in _TYPES:
    TYPE_REGISTRY[_cls.AGENT_TYPE] = _cls
    TYPE_REGISTRY[_cls.__name__] = _cls

# Stable tints used both by the frontend palette and the topology graph.
# 9 visually distinguishable hues spread across the wheel — every
# pair sits at least ~35° apart on the H axis OR differs strongly in
# S/L. Avoids the prior clashes (Router vs Base-agent on purple,
# Helper/Proxy vs Env-setup on teal, Planner vs Bug-repro on orange).
TYPE_COLORS: dict[str, str] = {
    "Bug reproduction":     "#f85149",  # red          ~ 3°
    "Base agent":           "#a4886c",  # taupe/brown  ~30° (desaturated
                                        #              so it doesn't blur
                                        #              with red or amber)
    "Planner/Orchestrator": "#e3b341",  # amber        ~44°
    "Environment setup":    "#bcbd22",  # olive-yellow ~60°
    "Patcher":              "#56d364",  # green        ~129°
    "Helper/Proxy":         "#2dd4bf",  # teal-cyan    ~172°
    "Locator":              "#388bfd",  # royal blue   ~213°
    "Router":               "#a371f7",  # purple       ~263° (matches
                                        #              conditional edges)
    "Reviewer":             "#db61a2",  # magenta-pink ~328°
}
_CONTROL_TYPES: frozenset[str] = frozenset({"Router"})


def list_agent_types() -> list[dict[str, Any]]:
    """Return the agent-type catalog the frontend renders, each entry carrying the type's full default block (prompts + tools + config) so the topology page can seed a dropped node without re-deriving anything client-side."""
    out: list[dict[str, Any]] = []
    # Iterate `_TYPES` (one entry per class), not TYPE_REGISTRY -- the
    # registry double-keys each class so `.values()` would emit duplicates.
    for cls in _TYPES:
        doc = (cls.__doc__ or "").strip().splitlines()
        out.append({
            "type":            cls.AGENT_TYPE,
            "color":           TYPE_COLORS.get(cls.AGENT_TYPE, "#888"),
            "description":     doc[0] if doc else "",
            "class":           cls.__name__,
            "category":        "control" if cls.AGENT_TYPE in _CONTROL_TYPES else "agent",
            "default_system":  cls.DEFAULT_SYSTEM,
            "default_user":    cls.DEFAULT_USER,
            "default_tools":   list(cls.DEFAULT_TOOLS),
            "default_config":  dict(cls.DEFAULT_CONFIG),
        })
    return out


__all__ = [
    "TYPE_REGISTRY",
    "TYPE_COLORS",
    "list_agent_types",
    "BugReproductionAgent",
    "EnvironmentSetupAgent",
    "GenericAgent",
    "HelperProxyAgent",
    "LocatorAgent",
    "PatcherAgent",
    "PlannerOrchestrator",
    "Router",
    "ReviewerAgent",
]
