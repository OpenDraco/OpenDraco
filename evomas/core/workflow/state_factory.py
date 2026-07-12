"""Build the workflow `TypedDict` state class dynamically from a unified config.

Each agent owns the slot keyed by its node id (`state[self.name]`), typed by
the class's `OUTPUT_TYPE` ClassVar.

`errors` and `thinking` are tagged with `Annotated[..., operator.add]` so
fan-out super-steps with concurrent writes merge instead of failing the
default `LastValue` channel with `INVALID_CONCURRENT_GRAPH_UPDATE`. Producer
slots stay `LastValue` since each agent uniquely owns its own slot."""
from __future__ import annotations

import operator
from copy import deepcopy
from typing import Annotated, Any, TypedDict

from evomas.agents.base_agent import BaseAgent

# Runtime-seeded keys present in every workflow state. `errors` and
# `thinking` use `operator.add` for fan-in concatenation.
RUNTIME_INPUTS: list[dict[str, Any]] = [
    {"name": "instance",       "type": dict[str, Any]},
    {"name": "workspace_path", "type": str},
    {"name": "issue_text",     "type": str},
    {"name": "errors",         "type": Annotated[list[str], operator.add], "default": []},
    {"name": "thinking",       "type": Annotated[str,       operator.add], "default": ""},
]


def build_state_class(
    config: dict[str, Any],
    agents: dict[str, BaseAgent],
) -> type:
    """Return a `TypedDict` whose slots are `RUNTIME_INPUTS` plus one per
    agent node, named by node id and typed by the class's `OUTPUT_TYPE`."""
    fields: dict[str, Any] = {}
    for entry in RUNTIME_INPUTS:
        fields[entry["name"]] = entry["type"]
    for node_name, agent in agents.items():
        fields[node_name] = type(agent).OUTPUT_TYPE
    return TypedDict("EvomasState", fields, total=False)  # type: ignore[operator]


def build_initial_state(
    config: dict[str, Any],
    agents: dict[str, BaseAgent],
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    """RUNTIME_INPUTS defaults → per-agent `OUTPUT_DEFAULT` (deep-copied to
    avoid shared-ref bugs) → caller's runtime inputs."""
    state: dict[str, Any] = {}
    for entry in RUNTIME_INPUTS:
        if "default" in entry:
            state[entry["name"]] = deepcopy(entry["default"])
    for node_name, agent in agents.items():
        default = getattr(type(agent), "OUTPUT_DEFAULT", None)
        if default is not None:
            state[node_name] = deepcopy(default)
    state.update(runtime_inputs)
    return state
