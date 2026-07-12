"""Patcher — writes, selects, and applies the patch that fixes the bug."""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from evomas.agents.llm_tool_agent import LLMToolAgent
from evomas.utils.patch import generate_diff_impl

logger = logging.getLogger(__name__)


class PatcherAgent(LLMToolAgent):
    """Handles the actual code modification: writing a patch, **selecting the best
    patch among multiple generated options**, and applying the patch to the file
    system. Writes the workspace `git diff` into `state[self.name]`.

    When the predecessor slot is a `{patches: list[str], validations: list[dict]}`
    bundle (e.g. from a Reviewer in a star/fan-in topology), PatcherAgent runs
    a deterministic ensembler that scores candidates and picks the best — no
    LLM call. Otherwise it falls through to the normal LLM-driven patcher loop.
    """

    AGENT_TYPE: ClassVar[str] = "Patcher"
    name = "patcher"

    OUTPUT_TYPE: ClassVar[Any] = str
    OUTPUT_DEFAULT: ClassVar[str] = ""

    def _producer_value(self) -> str:
        """Surface the workspace `git diff` so the chip and downstream agents get the patch text directly; falls back to the LLM response if no workspace was pinned or the diff was empty."""
        workspace = (self._last_workspace_path or "").strip()
        if workspace:
            diff = generate_diff_impl(workspace) or ""
            if diff.strip():
                return diff
        return self._final_response_text

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Two paths:
          1. Ensembler — predecessor is a `{patches, validations}` bundle.
             Score candidates deterministically and emit the best patch.
          2. Generic LLM loop — call `super().run(state)`. Used by linear
             chains where the predecessor is just a locator's `<files>` block.
        """
        upstream = state.get(self.predecessor_name or "")
        if isinstance(upstream, dict) and (upstream.get("patches") or []):
            return self._ensemble_from_bundle(upstream)
        return super().run(state)

    def _ensemble_from_bundle(self, upstream: dict[str, Any]) -> dict[str, Any]:
        """Deterministic candidate-patch selector. Pure Python — no LLM call.

        Reads `upstream["patches"]` (list[str]) + `upstream["validations"]`
        (list[dict] per patch with `score`, `applies`, `flake8_ok`,
        `review_pass`) and returns the highest-ranked patch.
        """
        candidates: list[str] = list(upstream.get("patches") or [])
        results: list[dict[str, Any]] = list(upstream.get("validations") or [])

        if results and len(results) == len(candidates):
            scored = sorted(
                zip(candidates, results),
                key=lambda pr: (
                    pr[1].get("score", 0),
                    pr[1].get("applies", False),
                    pr[1].get("flake8_ok", False),
                    pr[1].get("review_pass", False),
                ),
                reverse=True,
            )
            best_patch, best_result = scored[0]
            self.logger.info(
                "patcher ensembler: picked candidate %s (score=%s applies=%s)",
                best_result.get("patch_idx"),
                best_result.get("score"),
                best_result.get("applies"),
            )
            if best_result.get("score", 0) > 0 and best_patch.strip():
                return {self.name: best_patch}
            # All zero-score -- only fall back to a candidate that applies,
            # else we'd submit a doomed patch the harness rejects.
            applies_map = {
                r.get("patch_idx", i): r.get("applies", False)
                for i, r in enumerate(results)
            }
            fallback = next(
                (p for i, p in enumerate(candidates) if p.strip() and applies_map.get(i, False)),
                "",
            )
            self.logger.info(
                "patcher ensembler: zero-score fallback applies=%s len=%d",
                bool(fallback), len(fallback),
            )
            return {self.name: fallback}

        # No validation_results -- pick first non-empty candidate so the
        # runner's `final_patch` lookup has something.
        self.logger.warning(
            "patcher ensembler: no/mismatched validation results; using first non-empty"
        )
        return {self.name: next((p for p in candidates if p and p.strip()), "")}

    DEFAULT_SYSTEM: ClassVar[str] = (
        "You are an expert software engineer producing a MINIMAL bug-fix patch.\n"
        "You have a small toolbox of deterministic Python helpers; use them.\n\n"
        "## Step 0: REQUIRED first tool call\n"
        "Call `apply_description_fix(issue_text, workspace)`. It atomically:\n"
        "  1. detects whether the issue is a description / error-message bug,\n"
        "  2. derives the verbatim replacement from the source docstring,\n"
        "  3. builds a unified diff and applies it to the workspace.\n\n"
        "- If the result has `ok: true`: the workspace is ALREADY patched.\n"
        "  Respond with a single line acknowledging the fix and DO NOT call\n"
        "  any further tools. The base agent loop exits as soon as you\n"
        "  respond without a tool call. You are done.\n"
        "- If the result has `ok: false` and `bug_class` is 2 or 3: continue\n"
        "  with the general workflow below. (`bug_class: 2` is a behaviour\n"
        "  bug — wrong output on a specific input. `bug_class: 3` is an API\n"
        "  signature mismatch.)\n\n"
        "## General workflow (class 2 / 3 only)\n"
        "1. Identify the change site:\n"
        "   - If the locator emitted a `<files>` list, start with `read_file`\n"
        "     on the first entry.\n"
        "   - Otherwise use `search_code(query, workspace)` to find candidate\n"
        "     locations, then `read_file` to inspect them.\n"
        "2. Construct a unified diff manually. Wrap it in `<patch>…</patch>`.\n"
        "   Format requirements:\n"
        "     * `diff --git a/<path> b/<path>` header,\n"
        "     * `--- a/<path>` and `+++ b/<path>` file markers,\n"
        "     * `@@ -<old_start>,<old_count> +<new_start>,<new_count> @@`,\n"
        "     * removed lines start with `-`, added with `+`, context with a single space,\n"
        "     * 3 lines of context above and below the hunk,\n"
        "     * repo-relative paths.\n"
        "3. Call `apply_patch(patch_str=<your diff>, repo_path=workspace)`.\n"
        "   - If `ok: false`: call `normalize_patch(patch_str=<your diff>)`\n"
        "     to repair common hunk-header / blank-line mistakes, then\n"
        "     `apply_patch` the normalized result. ONE retry max.\n"
        "4. Optionally call `run_flake8(file_path=<touched.py>)` and fix any\n"
        "   syntax/name errors with a follow-up `apply_patch` call.\n"
        "5. Once a patch has applied successfully, respond with a one-line\n"
        "   summary and stop emitting tool calls.\n\n"
        "## Anti-patterns (always fail the harness)\n"
        "- Paraphrasing the `apply_description_fix` / `derive_description_fix`\n"
        "  output. The harness is character-exact.\n"
        "- Wrapping the buggy code in `try / except`.\n"
        "- Touching test files. The harness scores the very tests you'd be\n"
        "  modifying — never edit them.\n"
        "- Multi-hunk patches when one hunk suffices.\n"
        "- Calling tools NOT in your tool list. The runtime will reject them."
    )
    DEFAULT_USER: ClassVar[str] = (
        "## Issue\n{issue}\n\n"
        "## Workspace\n{workspace}\n\n"
        "## Upstream (locator)\n{predecessor}\n\n"
        "Your FIRST tool call MUST be\n"
        "`apply_description_fix(issue_text=<the Issue above>, repo_path=workspace)`.\n"
        "If it returns `ok: true`, you are done — respond with a one-line\n"
        "acknowledgement and emit NO further tool calls. Otherwise follow the\n"
        "general workflow in the system prompt. Do NOT modify test files."
    )
    DEFAULT_TOOLS: ClassVar[tuple[str, ...]] = (
        # Step-0 deterministic class-1 fixer (detect + derive + apply_patch).
        "apply_description_fix",
        # Lower-level helpers, kept callable for diagnostics.
        "detect_bug_class", "derive_description_fix",
        # General-purpose tools from evomas/tools/ only -- no openhands names.
        "read_file", "list_files", "search_code",
        "apply_patch", "normalize_patch", "generate_diff", "run_flake8",
    )
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {
        "temperature":  0.2,
        "num_ctx":      16384,
        "num_predict":  2048,
        "stop":         ["</patch>"],
    }
