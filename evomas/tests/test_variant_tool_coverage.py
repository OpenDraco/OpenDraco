"""MCP-registry coverage check for every agent variant.

Each variant emitted by `evomas.agents.types.variants.list_variants()` carries a
`default_tools` list -- the tool names the agent's whitelist references at
runtime. The MCP server (`evomas.mcp.server.MCPServer`) needs to have a
registered tool with each of those names for the LLM to actually be able to
call it; otherwise the agent ends up with zero callable tools at inference
time and silently can't act.

Today's state:
* **Built-in EvoMas variants** (`repo == "evomas"`) reference tool names that
  are wired into `default_registry()` in `evomas/mcp/server.py`. We hard-assert
  full coverage -- if a built-in variant lists a tool MCP doesn't know about,
  something has rotted and we want the test to fail loud.
* **Repo variants** (CSV-derived) reference upstream tool names whose
  implementations live as `NotImplementedError` stubs under
  `evomas/tools/<repo>/`. Those stubs are NOT registered with MCP yet, so
  every repo variant has gaps. We collect the per-repo / per-variant missing
  list and `pytest.xfail` with the report attached as the message -- this
  keeps `pytest -q` green while still surfacing the gap when the report is
  needed (run with `pytest -rx ./evomas/tests/test_variant_tool_coverage.py`
  to see the message).

If you want the suite to FAIL when repo variants have gaps (e.g. to gate a
"wire up the per-repo stubs" cleanup), swap the final `pytest.xfail(...)`
call for `pytest.fail(...)`.
"""
from __future__ import annotations

import pytest

from evomas.agents.types.variants import list_variants
from evomas.mcp.server import MCPServer


def _registered_tool_names() -> set[str]:
    """Tool names the MCP server's default registry exposes."""
    return set(MCPServer().registry.tools.keys())


def test_builtin_variants_are_fully_covered_by_mcp_registry() -> None:
    """Hard floor: every built-in (`repo='evomas'`) variant's `default_tools`
    list must be reachable through MCP. A miss here means the canonical
    agent-type defaults rotted out of sync with `default_registry()`."""
    registered = _registered_tool_names()
    failures: list[str] = []
    for agent_type, variants in list_variants().items():
        for v in variants:
            if v.get("repo") != "evomas":
                continue
            missing = set(v.get("default_tools") or []) - registered
            if missing:
                failures.append(
                    f"  {agent_type:24} {v['key']:30} missing: {sorted(missing)}"
                )
    if failures:
        msg = "Built-in variants reference tool names MCP doesn't expose:\n" + "\n".join(failures)
        msg += (
            f"\n\nMCP registered ({len(registered)}): "
            f"{', '.join(sorted(registered))}"
        )
        pytest.fail(msg)


def test_repo_variants_mcp_coverage_report() -> None:
    """Diagnostic: report per-repo / per-variant missing tools. xfails when
    there's anything to report so the suite stays green but the message
    captures the exact list of names that need to be wired into MCP.

    To turn this into a hard gate (block merges until the registry catches
    up with the variant catalog), swap `pytest.xfail(...)` for `pytest.fail(...)`.
    """
    registered = _registered_tool_names()
    # repo_id -> variant_key -> sorted list of missing tool names
    report: dict[str, dict[str, list[str]]] = {}
    for variants in list_variants().values():
        for v in variants:
            repo = v.get("repo") or ""
            if not repo or repo == "evomas":
                continue
            missing = sorted(set(v.get("default_tools") or []) - registered)
            if missing:
                report.setdefault(repo, {})[v["key"]] = missing

    if not report:
        # Every repo variant is reachable -- the gap has been closed.
        return

    lines: list[str] = [
        f"{len(report)} repo(s) have variants with tool names MCP doesn't expose:",
    ]
    for repo, variants in sorted(report.items()):
        lines.append(f"\n  [{repo}]")
        for key, missing in sorted(variants.items()):
            lines.append(f"    {key:48} missing: {missing}")
    lines.append("")
    lines.append(
        f"MCP registered ({len(registered)}): {', '.join(sorted(registered))}"
    )
    pytest.xfail("\n".join(lines))


def test_unused_mcp_tools_report() -> None:
    """Informational: list MCP-registered tools that no variant references.
    Always passes -- helps spot tools that could be retired or aliased."""
    registered = _registered_tool_names()
    referenced: set[str] = set()
    for variants in list_variants().values():
        for v in variants:
            referenced.update(v.get("default_tools") or [])
    unused = sorted(registered - referenced)
    if unused:
        # Not a failure -- just a print-through visible with `pytest -s`.
        print(f"\n[info] MCP tools no variant references: {unused}")
