"""Unit tests for the hand-off summarizer / preview helpers used by
graph_builder's per-edge log line and the inference page's chip rendering."""
from __future__ import annotations

import pytest

from evomas.utils.handoff import preview_payload, summarize_payload


def test_summarize_none() -> None:
    assert summarize_payload(None) == "None"


def test_summarize_bool_before_int() -> None:
    # Python bool subclasses int — the helper must check bool first or the
    # output reads as `int(True)` which is misleading.
    assert summarize_payload(True) == "bool(True)"
    assert summarize_payload(False) == "bool(False)"


def test_summarize_int() -> None:
    assert summarize_payload(42) == "int(42)"
    assert summarize_payload(-7) == "int(-7)"


def test_summarize_float() -> None:
    assert summarize_payload(3.14) == "float(3.14)"


def test_summarize_str_uses_byte_units() -> None:
    assert summarize_payload("hello") == "str(5 B)"
    big = "x" * 2048
    out = summarize_payload(big)
    assert out.startswith("str(") and "KB" in out


def test_summarize_bytes() -> None:
    assert summarize_payload(b"hi") == "bytes(2 B)"


def test_summarize_list_reports_item_count_and_size() -> None:
    out = summarize_payload(["alpha", "beta"])
    assert out.startswith("list(2 items, ~")
    assert "B" in out  # bytes/KB suffix


def test_summarize_tuple_distinct_from_list() -> None:
    assert summarize_payload(("a", "b")).startswith("tuple(2 items, ~")


def test_summarize_dict_reports_key_count() -> None:
    out = summarize_payload({"k": "v", "k2": "v2"})
    assert out.startswith("dict(2 keys, ~")


def test_summarize_set() -> None:
    out = summarize_payload({"a", "b", "c"})
    assert out.startswith("set(3 items, ~")


def test_summarize_unknown_type_fallback() -> None:
    class Custom:
        def __str__(self) -> str: return "custom-repr"
    out = summarize_payload(Custom())
    # type name + size, no crash
    assert out.startswith("Custom(~")


def test_summarize_unrenderable_falls_back_cleanly() -> None:
    class Boom:
        def __str__(self) -> str: raise RuntimeError("nope")
    # str() of the object fails; helper returns a fallback rather than
    # propagating the exception out of the log path.
    assert summarize_payload(Boom()) == "Boom(?)"


def test_preview_short_payload_unchanged() -> None:
    assert preview_payload("hello") == "hello"


def test_preview_long_payload_truncates_with_suffix() -> None:
    long = "x" * 20000
    out = preview_payload(long, max_chars=16384)
    assert out.endswith(" more chars)")
    assert "..." in out
    assert len(out) < len(long)


def test_preview_unrenderable_yields_placeholder() -> None:
    class Boom:
        def __str__(self) -> str: raise RuntimeError("nope")
    out = preview_payload(Boom())
    assert out.startswith("<unrenderable: Boom:")


@pytest.mark.parametrize("value,expected_prefix", [
    (None,            "None"),
    (0,               "int(0)"),
    ("",              "str(0 B)"),
    ([],              "list(0 items, ~"),
    ({},              "dict(0 keys, ~"),
])
def test_summarize_empty_values(value, expected_prefix) -> None:
    assert summarize_payload(value).startswith(expected_prefix)
