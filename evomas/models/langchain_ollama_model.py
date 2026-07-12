import logging
import os
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_ollama import ChatOllama

from evomas.config.loader import AgentConfig
from evomas.exceptions.errors import OllamaMemoryError


from dotenv import load_dotenv

load_dotenv()


logger = logging.getLogger(__name__)


def _resolve_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def build_chat_ollama(config: AgentConfig, **overrides: Any) -> ChatOllama:
    seed = config.seed if config.seed != 0 else None
    num_predict = (
        config.num_predict if config.num_predict and config.num_predict > 0 else None
    )
    stop = config.stop or None
    reasoning = bool(config.think) if config.think is not None else None

    kwargs: dict[str, Any] = {
        "model": config.model,
        "base_url": _resolve_base_url(),
        "temperature": config.temperature,
        "num_ctx": config.num_ctx,
        "num_predict": num_predict,
        "top_k": config.top_k,
        "top_p": config.top_p,
        "repeat_penalty": config.repeat_penalty,
        "repeat_last_n": config.repeat_last_n,
        "seed": seed,
        "stop": stop,
        "reasoning": reasoning,
    }
    kwargs.update(overrides)
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    logger.debug("ChatOllama kwargs: %s", kwargs)
    return ChatOllama(**kwargs)


def _flush_lines(buf: str, prefix: str) -> str:
    """Log complete lines from buf, return leftover partial line."""
    while "\n" in buf:
        line, _, buf = buf.partition("\n")
        if line.strip():
            logger.info("%s %s", prefix, line)
    return buf


class TokenUsage(dict):
    """Lightweight `{input, output, total}` token counter -- dict so it
    serializes cleanly to the prediction JSONL and the frontend payload."""
    @classmethod
    def empty(cls) -> "TokenUsage":
        return cls(input=0, output=0, total=0)

    def add(self, other: "TokenUsage | dict[str, int]") -> "TokenUsage":
        if not other:
            return self
        self["input"]  = int(self.get("input", 0))  + int(other.get("input", 0))
        self["output"] = int(self.get("output", 0)) + int(other.get("output", 0))
        self["total"]  = int(self.get("total", 0))  + int(other.get("total", 0))
        return self


def _extract_token_usage(message: Any) -> TokenUsage:
    """Extract token counts from a langchain-ollama response. Tries the
    standard `usage_metadata` (langchain v0.2+) first, then falls back to
    Ollama's per-response `response_metadata` (`prompt_eval_count` /
    `eval_count`). Returns zero counters when the model didn't report any
    (some streaming paths only attach usage to the final chunk)."""
    if message is None:
        return TokenUsage.empty()
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict) and usage:
        return TokenUsage(
            input=int(usage.get("input_tokens", 0) or 0),
            output=int(usage.get("output_tokens", 0) or 0),
            total=int(usage.get("total_tokens", 0) or 0),
        )
    meta = getattr(message, "response_metadata", None) or {}
    if isinstance(meta, dict) and meta:
        inp = int(meta.get("prompt_eval_count", 0) or 0)
        out = int(meta.get("eval_count", 0) or 0)
        if inp or out:
            return TokenUsage(input=inp, output=out, total=inp + out)
    return TokenUsage.empty()


def llm_invoke(
    llm: BaseChatModel,
    messages: list[BaseMessage],
    *,
    agent_name: str = "llm",
    on_think: Callable[[str], None] | None = None,
) -> tuple[Any, str, TokenUsage]:
    """Stream LLM response. Returns (response, thinking_text, token_usage).

    The `token_usage` dict carries {input, output, total} counts pulled
    from the response's `usage_metadata` / `response_metadata` and is also
    logged at INFO so it shows up in the per-prediction text log."""
    think_prefix = f"[{agent_name}|think]"
    resp_prefix = f"[{agent_name}|resp ]"

    try:
        accumulated: Any = None
        native_think_buf: str = ""  # from additional_kwargs["thinking"] - for line logging
        native_think_full: str = ""  # full accumulated native thinking
        native_thinking: bool = False
        native_think_total: int = 0

        content_buf: str = ""  # content stream (may embed <think> tags)
        in_think_tag: bool = False
        tag_think_buf: str = ""
        tag_think_full: str = ""  # full accumulated tag-based thinking
        tag_think_total: int = 0

        logger.info(
            "[%s] --> %s  messages=%d  prompt_chars=%d",
            agent_name,
            getattr(llm, "model", llm.__class__.__name__),
            len(messages),
            sum(len(str(getattr(m, "content", ""))) for m in messages),
        )

        for chunk in llm.stream(messages):
            # --- Path 1: native Ollama thinking field ---
            # langchain_ollama uses "reasoning_content" (not "thinking") for this key
            _kw = chunk.additional_kwargs or {}
            think_piece: str = (
                _kw.get("reasoning_content") or _kw.get("thinking") or ""
            ) or ""

            # --- Also extract thinking / text from list-typed content ---
            text: str = ""
            if isinstance(chunk.content, str):
                text = chunk.content
            elif isinstance(chunk.content, list):
                for item in chunk.content:
                    if not isinstance(item, dict):
                        text += str(item)
                        continue
                    item_type = item.get("type", "")
                    if item_type == "thinking":
                        think_piece += item.get("thinking", "") or item.get("text", "")
                    elif item_type in ("text", ""):
                        text += item.get("text", "")

            if think_piece:
                if not native_thinking:
                    logger.info("[%s] --- thinking start ---", agent_name)
                    native_thinking = True
                native_think_total += len(think_piece)
                native_think_full += think_piece
                native_think_buf += think_piece
                native_think_buf = _flush_lines(native_think_buf, think_prefix)
                if on_think:
                    on_think(think_piece)

            if text:
                content_buf += text

                # Parse the buffer for <think> / </think> boundaries
                while content_buf:
                    if in_think_tag:
                        end = content_buf.find("</think>")
                        if end >= 0:
                            tag_part = content_buf[:end]
                            tag_think_total += len(tag_part)
                            tag_think_full += tag_part
                            tag_think_buf += tag_part
                            tag_think_buf = _flush_lines(tag_think_buf, think_prefix)
                            if on_think and tag_part:
                                on_think(tag_part)
                            if tag_think_buf.strip():
                                logger.info("%s %s", think_prefix, tag_think_buf)
                                tag_think_buf = ""
                            logger.info(
                                "[%s] --- thinking end (%d chars) ---",
                                agent_name,
                                tag_think_total,
                            )
                            in_think_tag = False
                            content_buf = content_buf[end + len("</think>") :]
                        else:
                            tag_think_full += content_buf
                            tag_think_total += len(content_buf)
                            tag_think_buf += content_buf
                            tag_think_buf = _flush_lines(tag_think_buf, think_prefix)
                            if on_think and content_buf:
                                on_think(content_buf)
                            content_buf = ""
                    else:
                        start = content_buf.find("<think>")
                        if start == 0:
                            if not native_thinking:
                                logger.info("[%s] --- thinking start ---", agent_name)
                            in_think_tag = True
                            content_buf = content_buf[len("<think>") :]
                        elif start > 0:
                            # flush response text before the tag
                            before = content_buf[:start]
                            content_buf = _flush_lines(
                                before + "\n", resp_prefix
                            ).rstrip("\n")
                            content_buf += content_buf[start:]  # will be re-processed
                            content_buf = content_buf[start:]
                        else:
                            content_buf = _flush_lines(content_buf, resp_prefix)
                            break

            accumulated = chunk if accumulated is None else accumulated + chunk

        # Final flushes
        if native_think_buf.strip():
            logger.info("%s %s", think_prefix, native_think_buf)
        if native_thinking:
            logger.info(
                "[%s] --- thinking end (%d chars) ---", agent_name, native_think_total
            )
        if content_buf.strip() and not in_think_tag:
            logger.info("%s %s", resp_prefix, content_buf.strip())

        thinking = (native_think_full or tag_think_full).strip()
        token_usage = _extract_token_usage(accumulated)
        if token_usage.get("total", 0) > 0:
            logger.info(
                "[%s] tokens in=%d out=%d total=%d",
                agent_name,
                token_usage["input"],
                token_usage["output"],
                token_usage["total"],
            )
        return accumulated, thinking, token_usage

    except Exception as exc:
        msg = str(exc)
        if "memory" in msg.lower() and (
            "ResponseError" in type(exc).__name__ or "status code" in msg
        ):
            raise OllamaMemoryError(msg) from exc
        raise
