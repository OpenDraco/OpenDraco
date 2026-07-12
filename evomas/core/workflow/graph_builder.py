"""Generic LangGraph builder driven by a unified config dict.

Wiring rules:
- `end` nodes with no outgoing edges get a static edge to END.
- Router nodes with ≥2 outgoing edges get an LLM-driven conditional
  router. Routers cannot route to END directly (the candidate set
  is exactly the declared targets) — terminal logic must run in a worker
  node whose static `→ END` wire ends the graph.
- All other multi-edge sources get static fan-out (every successor runs
  in parallel on the same super-step).

Pre-flight validation lives on the frontend's Topology page; any
structural problem reaching here surfaces as a `TopologyError`."""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from evomas.agents.base_agent import BaseAgent
from evomas.agents.router import Router
from evomas.exceptions.errors import OllamaMemoryError, TopologyError
from evomas.utils.handoff import preview_payload, summarize_payload

# Tighter cap than the SSE `handoff.preview` (16 KB) so `.log` stays
# scannable on runs with multi-KB diffs.
_HANDOFF_LOG_PREVIEW_CHARS: int = 1000

logger = logging.getLogger(__name__)


def _wrap(
    agent: BaseAgent, targets: list[str], *, conditional: bool = False,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Wrap an agent's `run()` so the node emits per-handoff log lines.

    `conditional=True` suppresses per-target logging here for orchestrator
    sources — the router emits its own log lines for the targets actually
    picked, otherwise we'd over-count every potential successor."""
    def node(state: dict[str, Any]) -> dict[str, Any]:
        try:
            delta = agent.run(dict(state))
        except OllamaMemoryError:
            raise
        except Exception as exc:
            logger.error("agent %s failed: %s", agent.name, exc)
            errors: list[str] = list(state.get("errors") or [])
            errors.append(f"{agent.name}: {exc}")
            return {"errors": errors}

        # Canonical producer slot is `delta[agent.name]` (edge-driven IO);
        # fall back to the whole delta when the agent wrote to other keys.
        if targets and not conditional and isinstance(delta, dict):
            primary = delta.get(agent.name, delta)
            _emit_handoff_log(agent.name, targets, primary)
        return delta

    return node


def _emit_handoff_log(source: str, picked: list[str], primary: Any) -> None:
    """Per-target log emitter shared by static fan-out (`_wrap`) and the
    conditional router so the log format stays identical."""
    payload_summary = summarize_payload(primary)
    offered_preview = preview_payload(
        primary, max_chars=_HANDOFF_LOG_PREVIEW_CHARS,
    ).replace("\n", "\\n")
    for target in picked:
        logger.info("[%s] -> [%s] payload=%s", source, target, payload_summary)
        if offered_preview.strip():
            logger.info(
                "[%s] offered to [%s]: %s",
                source, target, offered_preview,
            )


def _make_router(
    source: str, targets: list[str],
) -> Callable[[dict[str, Any]], list[str]]:
    """Conditional-edge router for a Router hub. Reads
    `state[source]` and returns target names mentioned as whole words.
    Falls back to all targets on parser miss (over-dispatch beats stall)."""
    patterns: dict[str, re.Pattern[str]] = {
        t: re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in targets
    }

    def route(state: dict[str, Any]) -> list[str]:
        text = state.get(source) or ""
        if not isinstance(text, str):
            text = str(text)
        picked = [t for t in targets if patterns[t].search(text)]
        if picked:
            logger.info("[%s] LLM routed to %s (out of %s)", source, picked, targets)
        else:
            logger.warning(
                "[%s] LLM emitted no parseable target in %r; falling back to all %s",
                source, text[:200], targets,
            )
            picked = list(targets)
        # Emit handoff lines only for the targets actually dispatched.
        primary = state.get(source)
        if primary is not None and picked:
            _emit_handoff_log(source, picked, primary)
        return picked

    return route


def _normalize_end(raw_end: Any) -> set[str]:
    """Coerce the JSON `end` field (string or list) into a set of names."""
    if isinstance(raw_end, str):
        return {raw_end} if raw_end else set()
    if isinstance(raw_end, list):
        return {s for s in raw_end if isinstance(s, str) and s}
    raise TopologyError(
        f"'end' must be a string or list of strings; got {type(raw_end).__name__}"
    )


def build_graph(
    config: dict[str, Any],
    agents: dict[str, BaseAgent],
    state_cls: type,
) -> Any:
    """Compile a graph from a unified config dict. Any LangGraph/wiring
    failure surfaces as a `TopologyError` for consistent error rendering."""
    try:
        entry = config.get("entry")
        end_set = _normalize_end(config.get("end", []))

        edges = config.get("edges") or []
        out_edges: dict[str, list[str]] = {}
        in_edges: dict[str, list[str]] = {}
        for e in edges:
            src, tgt = e["from"], e["to"]
            out_edges.setdefault(src, []).append(tgt)
            in_edges.setdefault(tgt, []).append(src)

        # Edge-driven IO: agents read `state[self.predecessor_name]` to
        # avoid hardcoding upstream node ids. Multi-upstream nodes see
        # the first incoming edge.
        for node_name, agent in agents.items():
            upstream = in_edges.get(node_name) or []
            agent.predecessor_name = upstream[0] if upstream else None

        # Sources that will use conditional routing — must match the
        # `add_conditional_edges` condition below so `_wrap` skips its
        # static-fan-out log to avoid double-emission.
        conditional_sources: set[str] = {
            source for source, declared in out_edges.items()
            if isinstance(agents.get(source), Router) and len(declared) >= 2
        }

        graph = StateGraph(state_cls)
        for name, agent in agents.items():
            graph.add_node(name, _wrap(  # pyright: ignore[reportArgumentType]
                agent,
                list(out_edges.get(name, [])),
                conditional=name in conditional_sources,
            ))

        graph.add_edge(START, entry)  # pyright: ignore[reportArgumentType]

        # Static fan-out by default; Routers with ≥2 outgoing
        # edges get an LLM-driven conditional router instead.
        for source, targets in out_edges.items():
            agent = agents.get(source)
            if isinstance(agent, Router) and len(targets) >= 2:
                graph.add_conditional_edges(
                    source,
                    _make_router(source, list(targets)),
                    {t: t for t in targets},
                )
            else:
                for target in targets:
                    graph.add_edge(source, target)

        # END wires for terminal nodes (those with no outgoing edges).
        for name in end_set:
            if name not in out_edges:
                graph.add_edge(name, END)

        return graph.compile()
    except TopologyError:
        raise
    except Exception as exc:
        raise TopologyError(
            f"failed to compile graph from config: {type(exc).__name__}: {exc}"
        ) from exc
