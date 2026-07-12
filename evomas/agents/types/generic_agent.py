"""Base agent — catch-all type carrying no prompt and no tool whitelist.

This is the role-less fallback agent: it ships only the canonical Ollama
Modelfile defaults (`temperature=0.8`, `num_ctx=2048`, etc.) and has
empty `DEFAULT_SYSTEM`, `DEFAULT_USER`, `DEFAULT_TOOLS`. JSON config
blocks that select `"class": "Base agent"` MUST supply their own
`prompts` and `tools` (otherwise the agent will run with an empty
system message and the permissive "any registered MCP tool" policy from
`base_agent.BaseAgent.__init__`).

The Python class is still named `GenericAgent` (and lives in
`generic_agent.py`) to avoid clashing with the abstract `BaseAgent` in
`evomas/agents/base_agent.py` — the *type label* is "Base agent" but
the implementation class is a sibling of `LLMToolAgent`, not a
hierarchy root.
"""
from __future__ import annotations

from typing import Any, ClassVar

from evomas.agents.llm_tool_agent import LLMToolAgent


class GenericAgent(LLMToolAgent):
    """Base agent — role-less catch-all type. Carries the canonical Ollama Modelfile defaults; no system/user prompt and no tool whitelist."""

    AGENT_TYPE: ClassVar[str] = "Base agent"
    name = "generic_agent"

    OUTPUT_TYPE: ClassVar[Any] = Any
    OUTPUT_DEFAULT: ClassVar[Any] = None

    # Empty by design -- JSON blocks selecting `"class": "Base agent"`
    # MUST supply their own `prompts` and `tools`.
    DEFAULT_SYSTEM: ClassVar[str] = ""
    DEFAULT_USER: ClassVar[str] = ""
    DEFAULT_TOOLS: ClassVar[tuple[str, ...]] = ()

    # Pure Ollama Modelfile defaults --
    # https://github.com/ollama/ollama/blob/main/docs/modelfile.mdx
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {
        "temperature":    0.8,
        "num_ctx":        2048,
        "top_k":          40,
        "top_p":          0.9,
        "min_p":          0.0,
        "repeat_penalty": 1.1,
        "repeat_last_n":  64,
        "seed":           0,
        "num_predict":    -1,
        "stop":           [],
    }
