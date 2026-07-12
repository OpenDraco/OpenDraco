"""Generic config-driven agent that runs a LangChain function-calling loop from the unified-config block, with an optional single-shot diff fallback when the run produced no workspace changes."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from evomas.agents.base_agent import BaseAgent
from evomas.utils.patch import generate_diff_impl
from evomas.utils.handoff import preview_payload

# Must match `graph_builder._wrap`'s offered-line cap. Log-only inline
# preview; the full value lives in `state[<predecessor>]` and on the SSE
# `agent_input` event for the chip modal.
_HANDOFF_LOG_PREVIEW_CHARS: int = 1000

_PATCH_RE = re.compile(r"<patch>(.*?)</patch>", re.DOTALL | re.IGNORECASE)
_FINISH_NAMES = {"finish"}


def _coerce_slot_for_prompt(value: Any, max_chars: int = 8000) -> str:
    """Render a state-slot value as a string for `{name}` substitution.

    Empty OUTPUT_DEFAULTs (`""`, `[]`, `{}`, `None`) collapse to "" so hub
    prompts with "if X is empty" rules see them as truly empty (rendering
    `[]` as literal `"[]"` would misread as non-empty content). Lists of
    strings join on newlines so the model sees a readable list, not `repr`.
    """
    if value is None or value == "" or value == [] or value == {}:
        return ""
    if isinstance(value, str):
        return value[:max_chars]
    if isinstance(value, list) and all(isinstance(x, str) for x in value):
        return "\n".join(value)[:max_chars]
    return str(value)[:max_chars]


class LLMToolAgent(BaseAgent):
    name = "llm_tool_agent"

    def __init__(
        self,
        config_block: dict[str, Any] | None = None,
        node_name: str | None = None,
    ) -> None:
        super().__init__(config_block, node_name=node_name)
        block = config_block or {}
        # Layer type DEFAULT_CONFIG under the JSON block for `max_iters` the
        # same way BaseAgent.__init__ already does for the other hyperparams.
        merged = {**type(self).DEFAULT_CONFIG, **block}
        self.max_iters: int = int(merged.get("max_iters") or 10)

        fb = block.get("fallback") or {}
        self.fallback_enabled: bool = bool(fb.get("enabled"))
        self.guarantee_change: bool = bool(fb.get("guarantee_change"))
        self.fallback_system: str = fb.get("system") or _DEFAULT_FALLBACK_SYSTEM

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._run_llm_loop(state)

    def _run_llm_loop(self, state: dict[str, Any]) -> dict[str, Any]:
        workspace: str = state.get("workspace_path") or ""
        issue: str = state.get("issue_text") or ""
        instance: dict[str, Any] = state.get("instance") or {}
        self._last_workspace_path = workspace

        # Capped at 8000 chars so a runaway thinking buffer can't blow the
        # context window; the full value still lives in state for programmatic
        # readers (e.g. HelperProxyAgent's score-and-pick branch).
        predecessor_value = ""
        if self.predecessor_name:
            raw = state.get(self.predecessor_name)
            predecessor_value = str(raw or "")[:8000]
        self._last_predecessor_value = predecessor_value

        # Receiver-side mirror of `graph_builder._wrap`'s "[X] offered to [Y]"
        # line so the .log captures both halves of every hand-off in order.
        if self.predecessor_name and predecessor_value.strip():
            received_preview = preview_payload(
                predecessor_value, max_chars=_HANDOFF_LOG_PREVIEW_CHARS,
            ).replace("\n", "\\n")
            self.logger.info(
                "[%s] received from [%s]: %s",
                self.name, self.predecessor_name, received_preview,
            )

        system = self.prompts.get("system") or ""
        user_template = (self.prompts.get("user") or "").strip() or _DEFAULT_USER_PROMPT
        # Include every state slot so prompts can reference upstream producers
        # by name (e.g. `{locator}`, `{patcher}`) -- needed for hubs in
        # bidirectional / cyclic topologies where `{predecessor}` only resolves
        # to the first incoming edge's slot and goes stale on later iterations.
        fmt_kwargs: dict[str, str] = {
            k: _coerce_slot_for_prompt(v) for k, v in state.items()
        }
        # Explicit args win over state-slot collisions (a node literally named
        # `issue` would otherwise shadow the issue text).
        fmt_kwargs.update(
            issue=issue[:8000],
            workspace=workspace,
            instance_id=instance.get("instance_id", ""),
            predecessor=predecessor_value,
        )
        # `format_map` with a missing-key fallback so a typo renders one
        # `{name}` as empty rather than nuking ALL substitutions (the previous
        # KeyError fallback kept the literal template, hiding `{issue}` etc).
        warned_keys: list[str] = []

        class _FmtKwargs(dict[str, str]):
            def __missing__(self, key: str) -> str:
                warned_keys.append(key)
                return ""

        user_msg = user_template.format_map(_FmtKwargs(fmt_kwargs))
        if warned_keys:
            self.logger.warning(
                "user prompt references unknown placeholder(s) %s; rendered as empty",
                sorted(set(warned_keys)),
            )

        tools = self._bound_tools()
        llm = self.make_llm()
        if tools:
            llm = llm.bind_tools(tools)

        messages: list[Any] = [SystemMessage(content=system), HumanMessage(content=user_msg)]
        for step in range(self.max_iters):
            self.logger.info("[%s] iter %d/%d", self.name, step + 1, self.max_iters)
            response = self._invoke(llm, messages)  # pyright: ignore[reportArgumentType]
            messages.append(response)
            # Overwrite each iteration so the LAST non-empty content wins;
            # tool-call-only iterations keep the previously-captured text.
            self._capture_response_text(response)

            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                self.logger.info("[%s] no tool calls — stopping loop", self.name)
                break

            finished = False
            for call in tool_calls:
                tname = call.get("name") or ""
                args = call.get("args") or {}
                call_id = call.get("id") or f"call_{step}_{tname}"
                self.logger.info("[%s] tool %s args=%s", self.name, tname, str(args)[:200])
                try:
                    result = self._call_tool(tname, args)
                except Exception as exc:
                    result = f"Error: {exc}"
                messages.append(
                    ToolMessage(
                        content=self._stringify(result),
                        tool_call_id=call_id,
                        name=tname,
                    )
                )
                if tname in _FINISH_NAMES:
                    finished = True

            if finished:
                self.logger.info("[%s] finish() called — exiting loop", self.name)
                break

        # If max_iters exhausted without any final assistant message,
        # `_final_response_text` is still empty and the producer slot would
        # hand off "0 B". Fire one no-tools summarization so the agent emits
        # its canonical output (e.g. locator's `<files>...</files>`).
        if not self._final_response_text.strip():
            self.logger.info("[%s] max_iters reached without response — running summary fallback", self.name)
            try:
                summary_messages = list(messages) + [HumanMessage(content=(
                    "You have used all available iterations. Based on what "
                    "you have found so far, emit your FINAL response now in "
                    "the format your system prompt requires. Do NOT call any "
                    "more tools."
                ))]
                response = self._invoke(self.make_llm(), summary_messages)
                self._capture_response_text(response)
            except Exception as exc:
                self.logger.info("[%s] summary fallback failed: %s", self.name, exc)

        if self.fallback_enabled and workspace:
            if not (generate_diff_impl(workspace) or "").strip():
                self.logger.info("[%s] no workspace changes — running diff fallback", self.name)
                self._fallback_singleshot_patch(issue, workspace)

        return {
            "thinking": self._thinking,
            self.name: self._producer_value(),
        }

    def _capture_response_text(self, response: Any) -> None:
        """Extract final assistant text from a LangChain response onto `self._final_response_text`, handling both plain-string and list-of-content-parts shapes (Claude tool-calls, Gemini structured output)."""
        content = getattr(response, "content", None)
        if isinstance(content, str):
            text = content.strip()
            if text:
                self._final_response_text = content
            return
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    parts.append(str(part.get("text", "") or ""))
                else:
                    parts.append(str(part))
            joined = "".join(parts).strip()
            if joined:
                self._final_response_text = "".join(parts)

    def _fallback_singleshot_patch(self, issue: str, workspace: str) -> None:
        prompt = (
            "Produce a unified diff that fixes the issue. Wrap it in <patch>...</patch>.\n\n"
            f"## Repository\n{workspace}\n\n## Issue\n{issue[:6000]}\n"
        )
        try:
            response = self._invoke(
                self.make_llm(),
                [
                    SystemMessage(content=self.fallback_system),
                    HumanMessage(content=prompt),
                ],
            )
        except Exception as exc:
            self.logger.warning("[%s] fallback LLM call failed: %s", self.name, exc)
            return

        raw = self._extract_text(response)
        match = _PATCH_RE.search(raw)
        if match:
            patch_str = match.group(1).strip()
        else:
            i = raw.lower().find("<patch>")
            patch_str = raw[i + len("<patch>") :].strip() if i >= 0 else ""
        if patch_str:
            try:
                result = self.mcp.call("apply_patch", {
                    "patch_str": patch_str,
                    "repo_path": workspace,
                    "dry_run": False,
                })
                self.logger.info("[%s] fallback apply_patch: %s", self.name, str(result)[:200])
            except Exception as exc:
                self.logger.warning("[%s] fallback apply_patch failed: %s", self.name, exc)
        else:
            self.logger.warning("[%s] fallback: no <patch> content in response", self.name)

        if self.guarantee_change and not (generate_diff_impl(workspace) or "").strip():
            self._touch_tracked_file(workspace)

    def _touch_tracked_file(self, workspace: str) -> None:
        try:
            ls = subprocess.run(
                ["git", "ls-files"], cwd=workspace,
                capture_output=True, text=True, timeout=10,
            )
        except Exception as exc:
            self.logger.warning("[%s] last-resort: git ls-files failed: %s", self.name, exc)
            return
        if ls.returncode != 0:
            return
        candidates = [c.strip() for c in ls.stdout.splitlines() if c.strip()]
        if not candidates:
            return
        target_name = next(
            (c for c in candidates if c.lower() in {"readme.md", "readme.rst", "readme"}),
            candidates[0],
        )
        target = Path(workspace) / target_name
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
            text = text.rstrip("\n") + "\n\n<!-- EvoMas marker -->\n"
            target.write_text(text, encoding="utf-8")
            self.logger.warning("[%s] last-resort: appended marker to %s", self.name, target_name)
        except Exception as exc:
            self.logger.warning("[%s] last-resort: could not modify %s: %s",
                                self.name, target_name, exc)

    def _bound_tools(self) -> list[Any]:
        """Resolve the BaseTool objects to bind to the LLM straight from
        the MCP registry. Whatever `default_registry()` auto-discovered
        under `evomas/tools/` (top-level `@tool` fns + every bundle's
        `*_TOOLS` list) is what this agent can call."""
        registry = self.mcp.registry.tools
        names = (
            list(self.tool_policy.keys())
            if self.tool_policy is not None
            else list(registry.keys())
        )
        return [registry[n].tool for n in names if n in registry and registry[n].tool is not None]

    @staticmethod
    def _extract_tool_calls(response: Any) -> list[dict[str, Any]]:
        if isinstance(response, AIMessage) and getattr(response, "tool_calls", None):
            return [dict(c) for c in response.tool_calls]
        kw = getattr(response, "additional_kwargs", None) or {}
        raw = kw.get("tool_calls") or []
        out: list[dict[str, Any]] = []
        for c in raw:
            fn = (c or {}).get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            out.append({"name": fn.get("name", ""), "args": args or {}, "id": c.get("id")})
        return out

    @staticmethod
    def _stringify(result: Any) -> str:
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, indent=2, default=str)
        except (TypeError, ValueError):
            return str(result)

    @staticmethod
    def _extract_text(response: Any) -> str:
        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for c in content:
                if isinstance(c, dict):
                    if c.get("type") in ("text", "", None):
                        parts.append(c.get("text", "") or "")
                    elif c.get("type") == "thinking":
                        continue
                    else:
                        parts.append(str(c.get("text", "") or ""))
                else:
                    parts.append(str(c))
            return "".join(parts)
        return str(content)


_DEFAULT_USER_PROMPT = (
    "You are working inside a git repository at `{workspace}`. "
    "Use your tools to make the minimal source changes that resolve the issue below, "
    "then call `finish` with a one-sentence summary.\n\n"
    "## Issue\n{issue}\n"
)

_DEFAULT_FALLBACK_SYSTEM = (
    "You are an expert Python software engineer writing a minimal bug-fix patch.\n"
    "Output a single unified git diff that, when applied with `git apply`, fixes the "
    "issue.\n\n"
    "STRICT FORMAT:\n"
    "1. Wrap the entire patch in <patch>...</patch>.\n"
    "2. Start with `diff --git a/<path> b/<path>` followed by `--- a/...` and `+++ b/...`.\n"
    "3. Use as few hunks as possible.\n"
    "4. Use repo-relative paths.\n"
    "5. No prose outside the <patch> tags.\n"
)
