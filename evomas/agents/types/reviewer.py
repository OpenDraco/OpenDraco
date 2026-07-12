"""Reviewer — verifies that a candidate patch actually resolves the issue.

In addition to the lint + semantic-match checks the reviewer already runs,
it now calls `run_tests` (registered MCP tool, see `evomas/tools/test_runner.py`)
against the patched workspace. The Reviewer's verdict is therefore grounded in
real pytest outcomes — not just "looks correct" judgement — matching the thesis
Reviewer definition: *confirms whether the underlying issue has been adequately
resolved*.
"""
from __future__ import annotations

from typing import Any, ClassVar

from evomas.agents.llm_tool_agent import LLMToolAgent


class ReviewerAgent(LLMToolAgent):
    """Reviews the patcher's workspace edits (apply / lint / **run tests** / semantic match) via MCP tools, since the diff isn't a template placeholder."""

    AGENT_TYPE: ClassVar[str] = "Reviewer"
    name = "reviewer"

    # Output bundles `{patches, validations}` so the downstream ensembler
    # can read both via a single predecessor slot -- no multi-upstream lookup.
    OUTPUT_TYPE: ClassVar[Any] = dict[str, Any]
    OUTPUT_DEFAULT: ClassVar[dict[str, Any]] = {}

    DEFAULT_SYSTEM: ClassVar[str] = (
        "You are a strict code-review agent. The upstream patcher has\n"
        "already applied its edits to the workspace; you do NOT receive\n"
        "the patch text inline. Call `generate_diff` to retrieve the\n"
        "current diff against the base commit -- THAT is the patch you\n"
        "are reviewing.\n\n"
        "## Required checks (call ALL the tools, in order)\n"
        "1. `generate_diff(repo_path=workspace)` — see the candidate patch.\n"
        "2. `run_tests(workspace=workspace)` — execute the project's test\n"
        "   suite against the patched workspace. **This is the primary**\n"
        "   **resolution signal.** The result's `verdict` field is one of:\n"
        "     * `passed`   → tests pass → STRONG signal the patch works.\n"
        "     * `failed`   → tests fail → patch did not resolve the bug.\n"
        "     * `import_error` → workspace deps missing locally; treat as\n"
        "       NO-SIGNAL (do not fail on this alone, fall back to lint /\n"
        "       semantic checks).\n"
        "     * `timeout` / `no_tests` → NO-SIGNAL.\n"
        "3. `run_flake8(file_path=<modified .py>)` on every changed file.\n"
        "   New lint errors = FAIL.\n"
        "4. Semantic check: is the change minimal and targeted? Does it\n"
        "   match the bug class the issue describes? An early-return\n"
        "   guard or try/except wrap for a class-1 description bug is a\n"
        "   FAIL. Test-file edits are a FAIL.\n\n"
        "## Important: do NOT reset the workspace\n"
        "Even on FAIL, leave the patcher's edits on disk. The downstream\n"
        "ensembler reads the workspace diff as the final patch, so wiping\n"
        "the tree would erase the only candidate we have. Report FAIL as a\n"
        "signal only.\n\n"
        "## Output\n"
        "Wrap your verdict in <review>...</review>. First line PASS or\n"
        "FAIL, second line a one-sentence reason that cites the\n"
        "`run_tests` verdict explicitly (e.g. `FAIL: run_tests=failed,\n"
        "test_physical_n1_L0 still fails`). Once the verdict is written,\n"
        "emit no further tool calls — the loop exits as soon as you\n"
        "respond without one."
    )
    DEFAULT_USER: ClassVar[str] = (
        "## Issue\n{issue}\n\n"
        "## Workspace\n{workspace}\n\n"
        "## Upstream (patcher summary)\n{predecessor}\n\n"
        "Call `generate_diff` then `run_tests` to verify the candidate\n"
        "patch, then respond with <review>PASS|FAIL</review>."
    )
    DEFAULT_TOOLS: ClassVar[tuple[str, ...]] = (
        "generate_diff", "apply_patch", "run_flake8",
        "normalize_patch", "reset_repo",
        "read_file",
        # NEW: test execution -- grounds the verdict in real pytest outcomes.
        "run_tests",
    )
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {
        "temperature":  0.2,
        "num_ctx":      8192,
        "num_predict":  768,
        "stop":         ["</review>"],
    }
