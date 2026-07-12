"""Connectivity smoke test for the Ollama path through `build_chat` +
`llm_invoke`. Mirrors `test_langchain_gemini_model.py` exactly — same
flow, same assertions, just a different provider prefix on the model id.

`AgentConfig` is constructed inline so the test doesn't depend on any
JSON config existing on disk (in particular not on `evomas/config/loaded/`,
which is the user-upload directory and may be empty)."""
import pytest
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from evomas.config.loader import AgentConfig
from evomas.models import build_chat, llm_invoke

load_dotenv("evomas/.env")


@pytest.mark.integration
def test_chat_ollama_basic_call(ollama_required: None) -> None:
    # `ollama_required` (in conftest.py) already skips when ollama isn't
    # reachable or the model can't load due to memory pressure. The model
    # tag here mirrors the one in conftest.py — keep them in sync if you
    # switch off qwen3.5:9b.
    config = AgentConfig(
        model="ollama/qwen3.5:9b",
        think=False,
        stream=True,
        temperature=0.0,
        num_predict=64,
    )
    llm = build_chat(config)

    response, _, usage = llm_invoke(llm, [
        SystemMessage(content="Reply with exactly the word OK."),
        HumanMessage(content="Say it."),
    ], agent_name="test-ollama")

    content = getattr(response, "content", "")
    if isinstance(content, list):
        content = "".join(
            c.get("text", "") if isinstance(c, dict) else str(c) for c in content
        )
    assert content, "expected non-empty content from ChatOllama"
    # Token tracking is part of the llm_invoke contract — every Ollama
    # response should carry input/output counters via the streaming
    # finalizer; we mirror the gemini assertion shape exactly.
    assert usage.get("total", 0) > 0, f"expected non-zero token total, got {usage}"
