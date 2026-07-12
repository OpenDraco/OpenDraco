import os

import pytest
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from evomas.config.loader import AgentConfig
from evomas.models import build_chat, llm_invoke

load_dotenv("evomas/.env")

_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


@pytest.fixture(scope="session")
def gemini_required() -> None:
    if not os.environ.get("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not set; skipping Gemini integration test")
    # Auto-skip when running pytest under a Python that doesn't have the
    # gemini provider package installed (e.g. system Python instead of the
    # evomas venv). The Ollama-only setup is a valid use case -- only fail
    # this test for users who actually intend to exercise the gemini path.
    try:
        import langchain_google_genai  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip(
            "langchain-google-genai not installed in this Python; "
            "run pytest from the evomas venv or `pip install langchain-google-genai`"
        )


@pytest.mark.integration
def test_chat_gemini_basic_call(gemini_required: None) -> None:
    # Build an AgentConfig directly so the test doesn't depend on a
    # predefined JSON having a gemini agent yet.
    config = AgentConfig(
        model=f"gemini/{_GEMINI_MODEL}",
        think=False,
        stream=True,
        temperature=0.0,
        num_predict=64,
    )
    llm = build_chat(config)

    response, _, usage = llm_invoke(llm, [
        SystemMessage(content="Reply with exactly the word OK."),
        HumanMessage(content="Say it."),
    ], agent_name="test-gemini")

    content = getattr(response, "content", "")
    if isinstance(content, list):
        content = "".join(
            c.get("text", "") if isinstance(c, dict) else str(c) for c in content
        )
    assert content, "expected non-empty content from ChatGoogleGenerativeAI"
    # Gemini exposes token counts via `usage_metadata` on the final chunk,
    # which `llm_invoke`'s accumulator picks up through the shared
    # `_extract_token_usage` path.
    assert usage.get("total", 0) > 0, f"expected non-zero token total, got {usage}"
