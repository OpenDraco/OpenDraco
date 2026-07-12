import json as _json
import os
import shutil
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Generator

import pytest

def _ollama_alive(host: str = "localhost", port: int = 11434, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _model_loadable(base_url: str, model: str, timeout: float = 60.0) -> tuple[bool, str]:
    """Confirm the model fits in memory by reading the first streaming token.

    Uses stream=True so the connection returns as soon as the first byte
    arrives - CPU-only inference would otherwise exceed a short timeout
    waiting for the full response.
    """
    payload = _json.dumps(
        {"model": model, "prompt": "hi", "stream": True, "num_predict": 1}
    ).encode()
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(1)  # block only until first byte - model is loaded and running
            return True, ""
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        return False, body
    except Exception as exc:
        return False, str(exc)


@pytest.fixture(scope="session")
def ollama_required() -> None:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    parsed = base_url.replace("http://", "").replace("https://", "")
    host, _, port_s = parsed.partition(":")
    port = int(port_s.split("/")[0]) if port_s else 11434
    if not _ollama_alive(host or "localhost", port):
        pytest.skip(f"ollama not reachable at {base_url}")
    # Model tag mirrored by `test_langchain_ollama_model.py` — keep them
    # in sync if you switch off qwen3.5:9b.
    model = "qwen3.5:9b"
    loadable, reason = _model_loadable(base_url, model)
    if not loadable:
        if "memory" in reason.lower():
            pytest.skip(
                f"{model} cannot load - insufficient memory "
                f"(run tests from Windows where Ollama has more RAM): {reason[:200]}"
            )
        pytest.skip(f"{model} not available: {reason[:200]}")


@pytest.fixture
def buggy_repo(tmp_path: Path) -> Generator[Path, None, None]:
    repo = tmp_path / "buggy_repo"
    repo.mkdir()
    (repo / "calc.py").write_text(
        "def add(a, b):\n"
        "    return a - b\n"
        "\n"
        "def multiply(a, b):\n"
        "    return a * b\n"
    )
    (repo / "test_calc.py").write_text(
        "from calc import add, multiply\n"
        "\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
        "\n"
        "def test_multiply():\n"
        "    assert multiply(2, 3) == 6\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@evomas.local"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "evomas-test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial buggy state"],
        cwd=repo, check=True,
    )
    yield repo
    shutil.rmtree(repo, ignore_errors=True)


@pytest.fixture
def buggy_instance(buggy_repo: Path) -> dict:
    base_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=buggy_repo, capture_output=True, text=True
    ).stdout.strip()
    return {
        "instance_id": "evomas__buggy-1",
        "repo": "evomas/buggy",
        "base_commit": base_commit,
        "problem_statement": (
            "The function `add` in calc.py returns the difference instead of the sum. "
            "test_add fails because add(2, 3) returns -1 instead of 5. "
            "Fix add so that it returns a + b."
        ),
        "hints_text": "",
        "FAIL_TO_PASS": "[\"test_calc.py::test_add\"]",
        "PASS_TO_PASS": "[\"test_calc.py::test_multiply\"]",
        "version": "0.0",
    }
