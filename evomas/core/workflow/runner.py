import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from evomas.agents.base_agent import BaseAgent
from evomas.agents.llm_tool_agent import LLMToolAgent
from evomas.agents.types import TYPE_REGISTRY
from evomas.config.loader import load_config, resolve_variant_block
from evomas.core.workflow.graph_builder import build_graph
from evomas.core.workflow.state_factory import build_initial_state, build_state_class
from evomas.exceptions.errors import ConfigError, EvomasError, OllamaMemoryError
from evomas.utils.patch import generate_diff_impl
from evomas.utils.ollama_preflight import preflight_models
from evomas.utils.workspace import Workspace, clone_workspace

logger = logging.getLogger(__name__)

# Per-node revisit budget. Total super-step budget =
# DEFAULT_MAX_REVISITS * len(agents). Override via EVOMAS_GRAPH_MAX_REVISITS.
DEFAULT_MAX_REVISITS: int = 2


def _max_revisits() -> int:
    raw = os.getenv("EVOMAS_GRAPH_MAX_REVISITS", "").strip()
    if not raw:
        return DEFAULT_MAX_REVISITS
    try:
        v = int(raw)
    except ValueError:
        logger.warning(
            "EVOMAS_GRAPH_MAX_REVISITS=%r is not an int; using default %d",
            raw, DEFAULT_MAX_REVISITS,
        )
        return DEFAULT_MAX_REVISITS
    return max(1, v)

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    # Generic config-driven agent; openhands.json uses it for every node.
    "LLMToolAgent": LLMToolAgent,
    # Type aliases so JSON blocks can write `"class": "Locator"` etc.
    **TYPE_REGISTRY,
}


def _build_agents(config: dict[str, Any]) -> dict[str, BaseAgent]:
    agents: dict[str, BaseAgent] = {}
    for name, block in (config.get("agents") or {}).items():
        # Fill prompts/tools from the variant catalog when not inlined.
        block = resolve_variant_block(block)
        cls_name = block.get("class")
        if not cls_name:
            raise ConfigError(f"agent '{name}' missing required 'class' field")
        cls = AGENT_REGISTRY.get(cls_name)
        if cls is None:
            raise ConfigError(
                f"agent '{name}': unknown class '{cls_name}' "
                f"(known: {sorted(AGENT_REGISTRY)})"
            )
        agents[name] = cls(block, node_name=name)
    return agents


def _compose_issue(instance: dict[str, Any]) -> str:
    parts: list[str] = []
    if instance.get("problem_statement"):
        parts.append(str(instance["problem_statement"]))
    hints = instance.get("hints_text")
    if hints:
        parts.append("\n## Hints\n" + str(hints))
    return "\n".join(parts).strip()


def _maybe_weave_op(fn):
    try:
        import weave  # type: ignore

        return weave.op()(fn)
    except Exception:
        return fn


def _run_impl(instance: dict[str, Any], config: str | dict[str, Any] = "") -> str:
    """Run the EvoMas workflow for a single SWE-bench instance. `config` is
    a name, path, in-memory unified config dict, or empty for the default.

    `instance.repo` + `instance.base_commit` are optional — when both are
    absent (or empty), the runner skips the GitHub clone and uses a
    throwaway tmpdir as the workspace. That's the path the websearch /
    chat-style configs take: agents that don't need source files just
    want SOMETHING the tool sandbox can resolve `EVOMAS_WORKSPACE_PATH`
    against."""
    instance_id: str = instance["instance_id"]
    repo: str | None = instance.get("repo") or None
    base_commit: str | None = instance.get("base_commit") or None

    if isinstance(config, dict):
        cfg_label = config.get("id") or "<inline>"
        logger.info("=== running %s with inline config (id=%s) ===", instance_id, cfg_label)
        cfg = config
    else:
        logger.info("=== running %s with config=%s ===", instance_id, config)
        cfg = load_config(config)

    # Fail fast on missing Ollama models — preferable to a cryptic 404
    # from LangChain 30s into the agent loop.
    preflight_models(cfg)

    if repo and base_commit:
        workspace = clone_workspace(instance_id, repo, base_commit)
    else:
        # No repo to clone -- give the chain an empty scratch dir so
        # workspace-aware tools (write_file, list_files) still have a
        # valid root, and so `generate_diff_impl` later returns "" via
        # its existing git-failure path.
        ws_path = Path(tempfile.gettempdir()) / "evomas_workspace" / f"adhoc-{instance_id}"
        ws_path.mkdir(parents=True, exist_ok=True)
        workspace = Workspace(instance_id, repo or "", base_commit or "", ws_path)
        logger.info("ad-hoc workspace at %s (no repo/base_commit on instance)", ws_path)
    issue_text = _compose_issue(instance)
    # Sandboxed tools (write_file, ...) read this env var.
    os.environ["EVOMAS_WORKSPACE_PATH"] = str(workspace.path)

    # Order matters: state_factory reads each agent class's
    # OUTPUT_TYPE / OUTPUT_DEFAULT ClassVars.
    agents = _build_agents(cfg)
    state_cls = build_state_class(cfg, agents)
    graph = build_graph(cfg, agents, state_cls)

    initial_state = build_initial_state(
        cfg,
        agents,
        {
            "instance": instance,
            "workspace_path": str(workspace.path),
            "issue_text": issue_text,
        },
    )

    max_revisits = _max_revisits()
    recursion_limit = max_revisits * max(1, len(agents))
    invoke_config: dict[str, Any] = {"recursion_limit": recursion_limit}
    logger.info(
        "graph runtime: %d agents x %d max revisits => recursion_limit=%d",
        len(agents), max_revisits, recursion_limit,
    )
    try:
        final_state = graph.invoke(initial_state, config=invoke_config)
    except OllamaMemoryError:
        raise
    except Exception as exc:
        logger.exception("graph execution failed for %s: %s", instance_id, exc)
        raise EvomasError(f"graph failure for {instance_id}: {exc}") from exc

    # `final_patch` is a unified diff or empty -- the end-node slot is
    # only used when it actually contains `diff --git ` (virtual-patcher
    # pattern), so LLM phrases like "null" / "OK" can't leak through.
    workspace_diff = generate_diff_impl(str(workspace.path)) or ""
    if workspace_diff.strip():
        final_patch: str = workspace_diff
    else:
        end_field: Any = cfg.get("end")
        end_key: str = (
            end_field if isinstance(end_field, str)
            else (end_field[-1] if end_field else "")
        )
        slot_value = str(final_state.get(end_key) or "")
        if "diff --git " in slot_value:
            logger.info(
                "%s: workspace clean; using diff from end-node state[%r]",
                instance_id, end_key,
            )
            final_patch = slot_value
        else:
            logger.warning(
                "%s produced empty patch (workspace clean AND state[%r] not a diff)",
                instance_id, end_key,
            )
            final_patch = ""

    # Sum each agent's `BaseAgent.tokens` so the CLI line matches the API.
    tokens_in    = sum(int(a.tokens.get("input", 0))  for a in agents.values())
    tokens_out   = sum(int(a.tokens.get("output", 0)) for a in agents.values())
    tokens_total = sum(int(a.tokens.get("total", 0))  for a in agents.values())
    logger.info(
        "=== %s done: %d-char patch | tokens in=%d out=%d total=%d ===",
        instance_id, len(final_patch), tokens_in, tokens_out, tokens_total,
    )
    return final_patch


run = _maybe_weave_op(_run_impl)
