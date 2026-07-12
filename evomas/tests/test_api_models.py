"""Unit tests for the Ollama-catalog merge helpers.

Specifically covers `pulled_ollama_models_with_catalog` which merges the
locally-pulled list (from Ollama's `/api/tags`) with the curated registry
catalog so the topology dropdown shows every model the user could pick,
marking the unpulled ones with `pulled: False`.
"""
from __future__ import annotations

import pytest

from evomas.models.ollama_catalog import OLLAMA_CATALOG
from evomas.utils import ollama_preflight


def test_pulled_models_come_first_and_unpulled_catalog_fills_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pulled-locally models lead (alphabetical); unpulled catalog
    entries follow in their declared catalog order. Pulled entries
    that ALSO appear in the catalog don't duplicate."""
    # Patch the `/api/tags` probe at its source so the merge sees a
    # controlled "pulled" set.
    catalog_first = OLLAMA_CATALOG[0]
    monkeypatch.setattr(
        ollama_preflight, "_list_pulled",
        lambda: {"ollama/local-only:1b", catalog_first},
    )

    result = ollama_preflight.pulled_ollama_models_with_catalog()

    pulled_section = [m for m in result if m["pulled"]]
    assert len(pulled_section) == 2
    pulled_names = {m["name"] for m in pulled_section}
    assert pulled_names == {"ollama/local-only:1b", catalog_first}

    # Pulled section sorted alphabetically; first two entries cover it.
    assert result[0]["name"] <= result[1]["name"]

    # Unpulled section preserves catalog declaration order, minus the
    # already-pulled entry. The second catalog name is the first unpulled entry.
    unpulled = [m for m in result if not m["pulled"]]
    assert unpulled[0]["name"] == OLLAMA_CATALOG[1]
    assert all(m["name"] != catalog_first for m in unpulled)


def test_unreachable_ollama_still_returns_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """When `/api/tags` can't be reached the catalog still fully populates
    the dropdown so the user can pick something to pull later."""
    monkeypatch.setattr(ollama_preflight, "_list_pulled", lambda: set())

    result = ollama_preflight.pulled_ollama_models_with_catalog()
    assert len(result) == len(OLLAMA_CATALOG)
    assert all(m["pulled"] is False for m in result)
    assert [m["name"] for m in result] == list(OLLAMA_CATALOG)
