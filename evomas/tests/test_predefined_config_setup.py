"""Setup smoke test for every predefined config.

For each file in `evomas/config/predefined/*.json`, verify the full
inference pipeline starts cleanly:

  1. `load_config` parses the JSON.
  2. `_build_agents` resolves every `class` field against the
     `AGENT_REGISTRY` and instantiates each agent block.
  3. `build_state_class` builds a TypedDict that covers every node.
  4. `build_graph` compiles a LangGraph from the wiring rules.
  5. `clone_workspace` is invoked (mocked → returns a local tmp git
     repo, so no SWE-bench-scale network clone happens during tests).
  6. `graph.invoke(initial_state)` runs at least the entry node.

LLM calls are stubbed at `LLMToolAgent._run_llm_loop` so the test
doesn't need Ollama running — every agent immediately returns a
minimal delta and the graph walks every node deterministically.

The test only checks that the setup *kicks off* without raising; it
does NOT assert anything about the final patch or per-agent
behaviour. That's the contract the user asked for: "no need to wait
until it finishes, but does the git clone, etc and starts running
the entry agent". A config that compiles + clones + dispatches the
entry node without an exception is considered structurally healthy.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from evomas.agents.llm_tool_agent import LLMToolAgent
from evomas.core.workflow import runner as runner_mod
from evomas.utils.workspace import Workspace


PREDEFINED_DIR = Path(__file__).resolve().parents[1] / "config" / "predefined"
PREDEFINED_NAMES: list[str] = sorted(p.stem for p in PREDEFINED_DIR.glob("*.json"))


@pytest.fixture
def fake_workspace(tmp_path: Path) -> Path:
    """Tiny git repo at `tmp_path / "repo"`. Stands in for the real
    SWE-bench-scale clone — `clone_workspace` would normally pull a
    multi-megabyte repo over the network, which is too slow + flaky
    for a non-integration test."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# stub repo\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


# Per-node successor map populated by the test body before each run.
# The stub LLM loop reads this so `_make_router` can pick a deterministic
# parseable target instead of falling back to "dispatch all" — which on
# cyclic configs (cycle, hybrid, star_centralized) would walk every
# spoke endlessly until hitting LangGraph's recursion limit.
_NODE_TARGETS: dict[str, list[str]] = {}


@pytest.fixture
def stubbed_llm_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub every agent's LLM loop so no Ollama / Gemini / OpenAI call
    fires during the test. Returns the minimal delta shape the runner
    expects: `thinking` (accumulator) + the agent's producer slot
    keyed by its node name.

    The producer-slot payload deliberately contains the LAST candidate
    name from the agent's outgoing-edge list (populated by the test
    body from `cfg.edges`). For orchestrator hubs that's the conditional
    router's preferred terminal target: configs typically order their
    edges so the terminal / finalizer node is last (e.g. cycle's
    router has `{router→patcher_final, router→finalizer}` — picking
    `finalizer` short-circuits the retry loop). For non-orchestrator
    agents the output is ignored by the wiring anyway."""

    def stub_run(self: LLMToolAgent, state: dict[str, Any]) -> dict[str, Any]:
        # Pin the workspace path the way the real loop does so subclass
        # `_producer_value` overrides (PatcherAgent reads
        # `_last_workspace_path` for its `git diff`) don't crash.
        self._last_workspace_path = state.get("workspace_path") or ""
        targets = _NODE_TARGETS.get(self.name, [])
        payload = targets[-1] if targets else f"[{self.name}] stub-output"
        return {
            "thinking": f"[{self.name}] stub-thought",
            self.name: payload,
        }

    monkeypatch.setattr(LLMToolAgent, "_run_llm_loop", stub_run)


@pytest.fixture
def stubbed_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """No-op the Ollama preflight. The real one shells out to
    `ollama pull` for any missing models, which requires the binary on
    PATH + a reachable daemon — neither is available in CI sandboxes."""
    monkeypatch.setattr(runner_mod, "preflight_models", lambda *_a, **_kw: None)


@pytest.fixture
def stubbed_clone(
    fake_workspace: Path, monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Make `clone_workspace` (and any callable that imported it
    elsewhere in the runner) return our local fake repo. Records each
    call so the test can assert the clone step was actually invoked
    — i.e., the setup pipeline did reach the workspace-clone stage
    before kicking off the graph."""
    calls: list[tuple[str, str, str]] = []

    def fake_clone(instance_id: str, repo: str, base_commit: str) -> Workspace:
        calls.append((instance_id, repo, base_commit))
        return Workspace(
            instance_id=instance_id,
            repo=repo,
            base_commit=base_commit,
            path=fake_workspace,
        )

    # `runner._run_impl` does `from evomas.utils.workspace import clone_workspace`
    # at module load, so the bound name lives on the `runner` module.
    monkeypatch.setattr(runner_mod, "clone_workspace", fake_clone)
    return {"calls": calls}


def _populate_targets_from_config(config_name: str) -> None:
    """Build `_NODE_TARGETS` from the config so the stub LLM loop has
    parseable router targets to emit. The router's candidate set is
    exactly the declared outgoing edges — Routers cannot route
    to END, so no synthetic candidate is appended."""
    from evomas.config.loader import load_config
    cfg = load_config(config_name)
    _NODE_TARGETS.clear()
    for edge in cfg.get("edges") or []:
        _NODE_TARGETS.setdefault(edge["from"], []).append(edge["to"])


@pytest.mark.parametrize("config_name", PREDEFINED_NAMES)
def test_predefined_config_setup_starts(
    config_name: str,
    buggy_instance: dict[str, Any],
    stubbed_llm_loop: None,
    stubbed_preflight: None,
    stubbed_clone: dict[str, Any],
) -> None:
    """Drive the full setup → entry-agent-dispatch path for one
    predefined config. Skipping LLM calls means every agent returns
    immediately, so this completes in <1s per config.

    Assertions:
      - `_run_impl` returns without raising.
      - `clone_workspace` was called exactly once with the instance's
        repo and base_commit (proves the setup reached step 5).
      - The returned final-patch string is well-formed (any string,
        possibly empty — we stubbed the agents, so an empty patch is
        the expected steady state, not a bug)."""
    _populate_targets_from_config(config_name)
    final_patch = runner_mod._run_impl(buggy_instance, config_name)
    assert isinstance(final_patch, str)
    assert len(stubbed_clone["calls"]) == 1, (
        f"clone_workspace should have fired exactly once for {config_name}, "
        f"got {stubbed_clone['calls']}"
    )
    instance_id, repo, base_commit = stubbed_clone["calls"][0]
    assert instance_id == buggy_instance["instance_id"]
    assert repo == buggy_instance["repo"]
    assert base_commit == buggy_instance["base_commit"]
