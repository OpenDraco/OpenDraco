import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from evomas.config.loader import AgentConfig, agent_config_from_block
from evomas.models import build_chat, llm_invoke

if TYPE_CHECKING:
    from evomas.mcp.server import MCPServer


class BaseAgent(ABC):
    name: ClassVar[str] = "base_agent"

    AGENT_TYPE: ClassVar[str] = ""

    # Per-type defaults consulted when the JSON block omits the matching
    # field, so `class: <type>` alone is enough to get a working agent.
    DEFAULT_SYSTEM: ClassVar[str] = ""
    DEFAULT_USER: ClassVar[str] = ""
    DEFAULT_TOOLS: ClassVar[tuple[str, ...]] = ()
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {}

    # Edge-driven state contract: every agent writes into `state[self.name]`
    # and reads its upstream via `state[self.predecessor_name]`.
    # `state_factory.build_state_class` uses OUTPUT_TYPE to generate a typed
    # TypedDict slot; OUTPUT_DEFAULT (optional) seeds the slot in
    # `build_initial_state` so consumers never trip on a missing key.
    OUTPUT_TYPE: ClassVar[Any] = Any
    OUTPUT_DEFAULT: ClassVar[Any] = None

    # Injected by `graph_builder` once the topology is wired: the upstream
    # node that feeds this one (None for the entry node).
    predecessor_name: str | None = None

    def __init__(
        self,
        config_block: dict[str, Any] | None = None,
        node_name: str | None = None,
    ) -> None:
        from evomas.mcp.server import get_server

        block: dict[str, Any] = config_block or {}
        self.config_block: dict[str, Any] = block
        # Layer the type's hyperparameter defaults under the JSON block so
        # `class: "Patcher"` inherits patcher-tuned knobs without re-declaring
        # them, while still letting the JSON override any individual knob.
        merged_for_config = {**type(self).DEFAULT_CONFIG, **block}
        self.config: AgentConfig = agent_config_from_block(merged_for_config)
        block_prompts: dict[str, str] = block.get("prompts") or {}
        self.prompts: dict[str, str] = {
            "system": block_prompts.get("system") or type(self).DEFAULT_SYSTEM,
            "user":   block_prompts.get("user")   or type(self).DEFAULT_USER,
            **{k: v for k, v in block_prompts.items() if k not in {"system", "user"}},
        }
        # node_name override lets one config-driven class back multiple
        # graph nodes that differ only in prompts/tools.
        if node_name:
            self.name = node_name  # type: ignore[misc]
        self.logger: logging.Logger = logging.getLogger(f"evomas.agents.{self.name}")
        self.mcp: MCPServer = get_server()
        # `tools` absent -> permissive (any registered MCP tool callable);
        # present (even as []) -> whitelist, with per-entry `params` supplying
        # defaults the call site can still override.
        self.tool_policy: dict[str, dict[str, Any]] | None = None
        if "tools" in block:
            policy: dict[str, dict[str, Any]] = {}
            for entry in block.get("tools") or []:
                tname = entry.get("name") if isinstance(entry, dict) else None
                if not tname:
                    continue
                params = entry.get("params") if isinstance(entry, dict) else None
                policy[tname] = dict(params) if isinstance(params, dict) else {}
            self.tool_policy = policy
        elif type(self).DEFAULT_TOOLS:
            self.tool_policy = {name: {} for name in type(self).DEFAULT_TOOLS}
        self._thinking: str = ""
        # Final assistant text from the most recent `_invoke()` that produced
        # content; overwritten per iteration so the LAST response sticks.
        # Surfaced into the producer slot at end-of-run by `_producer_value()`.
        self._final_response_text: str = ""
        # Pinned by `run()` so subclasses (e.g. PatcherAgent's
        # `_producer_value`) can snapshot the diff without re-plumbing it.
        self._last_workspace_path: str = ""
        # Upstream slot value substituted into the user prompt as
        # `{predecessor}`; read by inference-page tooling to show what the
        # receiver actually consumed on a hand-off chip.
        self._last_predecessor_value: str = ""
        # Observation hooks read externally by the API worker / CLI runner.
        # `on_response` fires once per `_invoke()`; per-chunk streaming is
        # intentional only for thinking tokens.
        self.on_think: Callable[[str], None] | None = None
        self.on_response: Callable[[str], None] | None = None
        self.on_tool: Callable[[str, dict[str, Any], Any], None] | None = None
        self.tokens: dict[str, int] = {"input": 0, "output": 0, "total": 0}

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if self.tool_policy is not None and name not in self.tool_policy:
            allowed = sorted(self.tool_policy)
            raise PermissionError(
                f"agent '{self.name}' is not allowed to call tool '{name}' "
                f"(allowed: {allowed or '<none>'})"
            )
        merged: dict[str, Any] = {}
        if self.tool_policy is not None:
            merged.update(self.tool_policy.get(name) or {})
        merged.update(arguments or {})
        result = self.mcp.call(name, merged)
        if self.on_tool:
            self.on_tool(name, merged, result)
        return result

    def make_llm(self, **overrides: Any) -> BaseChatModel:
        """Construct the LangChain ChatModel for this agent's configured provider (selected from the `<provider>/<model>` prefix on `self.config.model`)."""
        return build_chat(self.config, **overrides)

    def _invoke(self, llm: BaseChatModel, messages: list[BaseMessage]) -> Any:
        response, self._thinking, usage = llm_invoke(
            llm, messages, agent_name=self.name,
            on_think=self.on_think,
        )
        self.tokens["input"]  += int(usage.get("input", 0))
        self.tokens["output"] += int(usage.get("output", 0))
        self.tokens["total"]  += int(usage.get("total", 0))
        # `content` may be a string or list of content-blocks; coerce to text.
        if self.on_response is not None:
            raw = getattr(response, "content", "")
            if isinstance(raw, list):
                text = "".join(
                    c.get("text", "") if isinstance(c, dict) else str(c)
                    for c in raw
                )
            else:
                text = str(raw or "")
            if text:
                self.on_response(text)
        return response

    def _producer_value(self) -> Any:
        """Value to write into `state[self.name]` at end-of-run; subclasses override when the canonical artifact isn't the final response text (e.g. PatcherAgent returns the workspace `git diff`)."""
        return self._final_response_text

    @abstractmethod
    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Process state and return a state delta dict (LangGraph node convention)."""
