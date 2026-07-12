"""Environment setup — installs deps and configures the workspace before fix attempts."""
from __future__ import annotations

from typing import Any, ClassVar

from evomas.agents.llm_tool_agent import LLMToolAgent


class EnvironmentSetupAgent(LLMToolAgent):
    """Set up the dev environment for testing / building (requirements, bootstrap scripts, venv); writes `environment_ready: bool` and optionally `setup_log: str`."""

    AGENT_TYPE: ClassVar[str] = "Environment setup"
    name = "environment_setup"

    OUTPUT_TYPE: ClassVar[Any] = dict[str, Any]
    OUTPUT_DEFAULT: ClassVar[dict[str, Any]] = {}

    DEFAULT_SYSTEM: ClassVar[str] = (
        "You are an environment-setup agent. Inspect the repository for dependency files "
        "(`requirements.txt`, `pyproject.toml`, `package.json`, `Gemfile`, `Dockerfile`, …) "
        "and run the minimal commands needed to make the project's tests runnable.\n\n"
        "Be conservative: prefer the project's existing scripts over ad-hoc package installs. "
        "If something would require root or hit the network, mention it in your final summary "
        "and stop instead of attempting it. Report `{environment_ready: bool, setup_log: str}` "
        "and call `finish`."
    )
    DEFAULT_USER: ClassVar[str] = (
        "## Workspace\n{workspace}\n\n"
        "Bootstrap the environment so tests can run."
    )
    DEFAULT_TOOLS: ClassVar[tuple[str, ...]] = (
        "read_file", "list_files", "search_code",
    )
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {
        "temperature":  0.2,
        "num_ctx":      4096,
        "num_predict":  1024,
    }
