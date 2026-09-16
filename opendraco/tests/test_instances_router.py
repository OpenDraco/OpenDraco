"""Guards on the (subset, split) matrix the instance-picker endpoints drive.

`refresh-all` must only ask HuggingFace for pairs that actually ship —
a phantom pair turns into a permanent `error` entry in the response.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import scripts.generate_swebench_instances as gen
from api.routers import instances as router


# Splits published by each SWE-bench repo on HuggingFace, verified against
# https://datasets-server.huggingface.co/splits. Note `full` has NO train
# split — the legacy `princeton-nlp/SWE-bench` mirror carries that, not
# `SWE-bench/SWE-bench`.
SHIPPED = {
    "lite/dev", "lite/test",
    "full/dev", "full/test",
    "verified/test",
}


@pytest.fixture
def stub_build(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Replace the HuggingFace pull with a recorder — no network, no disk."""
    calls: list[tuple[str, str]] = []

    def _fake(split_name, output_path, limit=None, subset="lite", append=False):
        calls.append((subset, split_name))
        if split_name not in gen.SUBSET_SPLITS[subset]:
            raise ValueError(
                f"split {split_name!r} not in dataset {gen.SUBSET_DATASETS[subset]!r}"
            )
        return 1

    monkeypatch.setattr(gen, "build_instances", _fake)
    return calls


def test_subset_splits_matches_huggingface() -> None:
    pairs = {f"{subset}/{split}"
             for subset, splits in gen.SUBSET_SPLITS.items()
             for split in splits}
    assert pairs == SHIPPED


def test_subset_splits_covers_every_dataset() -> None:
    assert set(gen.SUBSET_SPLITS) == set(gen.SUBSET_DATASETS)


def test_refresh_all_requests_only_shipped_pairs(stub_build: list) -> None:
    body = router.refresh_all_instances()
    assert {f"{s}/{sp}" for s, sp in stub_build} == SHIPPED
    errors = {k: v["error"] for k, v in body["results"].items() if "error" in v}
    assert errors == {}
    assert body["total"] == len(SHIPPED)


def test_refresh_rejects_split_the_subset_does_not_ship(stub_build: list) -> None:
    with pytest.raises(HTTPException) as exc:
        router.refresh_instances(split="train", subset="full")
    assert exc.value.status_code == 400
    assert "train" in str(exc.value.detail)
    # Rejected before any HuggingFace download is attempted.
    assert stub_build == []


def test_refresh_accepts_a_shipped_pair(stub_build: list) -> None:
    body = router.refresh_instances(split="dev", subset="full")
    assert body == {"count": 1, "subset": "full", "split": "dev",
                    "path": str(router.INSTANCES_PATH)}
    assert stub_build == [("full", "dev")]
