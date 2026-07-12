"""Gemini provider for the multi-provider LLM dispatcher.

Builds a `ChatGoogleGenerativeAI` from an `AgentConfig`. Maps the subset
of shared knobs Gemini understands (temperature, top_p, top_k,
num_predict→max_output_tokens, stop) and silently drops Ollama-only knobs
(`num_ctx`, `repeat_penalty`, `repeat_last_n`, `min_p`, `seed`).

Authentication is via the `GOOGLE_API_KEY` env var (langchain auto-detects
it from os.environ; users put it in `evomas/.env`).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from evomas.config.loader import AgentConfig

logger = logging.getLogger(__name__)


def build_chat_gemini(config: AgentConfig, **overrides: Any) -> ChatGoogleGenerativeAI:
    """Construct a Gemini ChatModel from the per-agent config.

    `config.model` is the bare Gemini model id (e.g. `gemini-1.5-pro`); the
    `gemini/` prefix is stripped by `evomas.models.build_chat` before this
    function is called.
    """
    if not os.environ.get("GOOGLE_API_KEY"):
        logger.warning(
            "GOOGLE_API_KEY is not set; Gemini calls will fail at request time. "
            "Add it to evomas/.env."
        )

    num_predict = (
        config.num_predict if config.num_predict and config.num_predict > 0 else None
    )
    stop = config.stop or None

    kwargs: dict[str, Any] = {
        "model": config.model,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "top_k": config.top_k,
        "max_output_tokens": num_predict,
        "stop_sequences": stop,
        # langchain-google-genai inherits streaming behaviour from
        # `streaming=True`; we map the shared `stream` flag through.
        "streaming": bool(config.stream),
    }
    kwargs.update(overrides)
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    logger.debug("ChatGoogleGenerativeAI kwargs: %s", kwargs)
    return ChatGoogleGenerativeAI(**kwargs)
