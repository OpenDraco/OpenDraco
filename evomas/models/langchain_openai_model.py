"""OpenAI provider for the multi-provider LLM dispatcher.

Builds a `ChatOpenAI` from an `AgentConfig`. Maps the subset of shared
knobs OpenAI understands (temperature, top_p, num_predict→max_tokens,
seed, stop) and silently drops Ollama-only knobs (`num_ctx`, `top_k`,
`repeat_penalty`, `repeat_last_n`, `min_p`).

Authentication is via the `OPENAI_API_KEY` env var. `OPENAI_BASE_URL` is
honored if set (useful for Azure OpenAI or local proxies like LiteLLM).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from langchain_openai import ChatOpenAI

from evomas.config.loader import AgentConfig

logger = logging.getLogger(__name__)


def build_chat_openai(config: AgentConfig, **overrides: Any) -> ChatOpenAI:
    """Construct an OpenAI ChatModel from the per-agent config.

    `config.model` is the bare OpenAI model id (e.g. `gpt-4o-mini`); the
    `openai/` prefix is stripped by `evomas.models.build_chat` before this
    function is called.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        logger.warning(
            "OPENAI_API_KEY is not set; OpenAI calls will fail at request time. "
            "Add it to evomas/.env."
        )

    num_predict = (
        config.num_predict if config.num_predict and config.num_predict > 0 else None
    )
    seed = config.seed if config.seed != 0 else None
    stop = config.stop or None
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None

    kwargs: dict[str, Any] = {
        "model": config.model,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "max_tokens": num_predict,
        "seed": seed,
        "stop": stop,
        "streaming": bool(config.stream),
        "base_url": base_url,
    }
    kwargs.update(overrides)
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    logger.debug("ChatOpenAI kwargs: %s", kwargs)
    return ChatOpenAI(**kwargs)
