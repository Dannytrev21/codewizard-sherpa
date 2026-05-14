"""Unit tests for ``apply_raw_artifact_truncation`` — S1-09 Gap 2.

Pins the pure helper that implements the soft per-probe raw-artifact
truncation policy: payloads exceeding ``raw_artifact_truncate_mb * 1 MiB``
are replaced with a ``__truncated_at_budget__`` marker wrapper. Boundary
semantics mirror :meth:`BudgetingContext.report_bytes` — inclusive at the
limit, exclusive above it.
"""

from __future__ import annotations

import json

import pytest

from codegenie.output.raw_truncation import (
    Truncated,
    Untruncated,
    apply_raw_artifact_truncation,
)

ONE_MB = 1_048_576


def test_returns_untruncated_for_under_budget_payload() -> None:
    """AC-7, AC-14 — under-budget payload returns unmodified bytes + Untruncated().

    Kills mutant: always-truncate (returns Truncated() regardless of size).
    """
    payload = b'{"k": "v"}'
    out_bytes, outcome = apply_raw_artifact_truncation(payload, truncate_mb=5)
    assert out_bytes == payload
    assert isinstance(outcome, Untruncated)


def test_empty_payload_untruncated() -> None:
    """AC-14 — zero-byte payload returns (b'', Untruncated()).

    Kills mutant: empty-payload mishandled (e.g., truncates an empty file).
    """
    out_bytes, outcome = apply_raw_artifact_truncation(b"", truncate_mb=5)
    assert out_bytes == b""
    assert isinstance(outcome, Untruncated)


@pytest.mark.parametrize("truncate_mb", [1, 5])
def test_exact_boundary_untruncated(truncate_mb: int) -> None:
    """AC-15 — payload of exactly truncate_mb MiB returns Untruncated (inclusive).

    Mirrors the report_bytes boundary in tests/unit/test_coordinator_budget.py:30-34.
    Kills mutant: off-by-one (using >= instead of >).
    """
    payload = b"a" * (truncate_mb * ONE_MB)
    out_bytes, outcome = apply_raw_artifact_truncation(payload, truncate_mb=truncate_mb)
    assert out_bytes == payload
    assert isinstance(outcome, Untruncated)


def test_one_byte_over_truncated() -> None:
    """AC-16 — payload one byte over the budget triggers Truncated.

    Kills mutant: off-by-one (using >= instead of >).
    Kills mutant: budget computed as truncate_mb * 1_000_000 (decimal) not 1_048_576.
    """
    payload = b"a" * (5 * ONE_MB + 1)
    out_bytes, outcome = apply_raw_artifact_truncation(payload, truncate_mb=5)
    assert isinstance(outcome, Truncated)
    assert outcome.original_bytes == 5 * ONE_MB + 1
    assert outcome.budget_bytes == 5 * ONE_MB
    wrapper = json.loads(out_bytes)
    assert wrapper["__truncated_at_budget__"] is True
    assert wrapper["original_bytes"] == 5 * ONE_MB + 1
    assert wrapper["budget_bytes"] == 5 * ONE_MB


def test_marker_shape_has_exactly_four_keys() -> None:
    """AC-7 — wrapper carries exactly the four contracted keys.

    Kills mutant: extra metadata key leaked into wrapper.
    Kills mutant: key name typo (e.g., missing leading "__").
    """
    payload = b"x" * (6 * ONE_MB)
    out_bytes, _ = apply_raw_artifact_truncation(payload, truncate_mb=5)
    wrapper = json.loads(out_bytes)
    assert set(wrapper.keys()) == {
        "__truncated_at_budget__",
        "original_bytes",
        "budget_bytes",
        "data",
    }


def test_marker_truncated_flag_is_strict_boolean() -> None:
    """AC-7 — the marker flag is the boolean True, not 1, not "True".

    Kills mutant: flag stored as int 1 (truthy but type-mismatched).
    Kills mutant: flag stored as the string "True".
    """
    payload = b"x" * (6 * ONE_MB)
    out_bytes, _ = apply_raw_artifact_truncation(payload, truncate_mb=5)
    wrapper = json.loads(out_bytes)
    assert wrapper["__truncated_at_budget__"] is True
    assert isinstance(wrapper["__truncated_at_budget__"], bool)


def test_prefix_is_parseable_json() -> None:
    """AC-17 — truncation prefix that parses as JSON lands in "data" as parsed value.

    Kills mutant: data field always stored as string, even when parseable.
    """
    # A 5 MiB JSON string literal: "aaaa..." (exactly budget_bytes long).
    body = b'"' + (b"a" * (5 * ONE_MB - 2)) + b'"'
    payload = body + b"\nGARBAGE"
    out_bytes, outcome = apply_raw_artifact_truncation(payload, truncate_mb=5)
    assert isinstance(outcome, Truncated)
    wrapper = json.loads(out_bytes)
    assert isinstance(wrapper["data"], str)
    assert wrapper["data"].startswith("aaaa")
    assert len(wrapper["data"]) == 5 * ONE_MB - 2


def test_prefix_unparseable_falls_back_to_replacement_string() -> None:
    """AC-18 — non-JSON prefix lands in "data" as a UTF-8 string w/ replacement chars.

    Kills mutant: helper raises on unparseable prefix instead of fallback.
    """
    payload = (b"\xff" * (5 * ONE_MB)) + b"X"
    out_bytes, _ = apply_raw_artifact_truncation(payload, truncate_mb=5)
    wrapper = json.loads(out_bytes)
    assert isinstance(wrapper["data"], str)
    assert "�" in wrapper["data"]


def test_utf8_multibyte_at_boundary_uses_replacement() -> None:
    """AC-19 — multi-byte UTF-8 character straddling the boundary does not crash.

    Kills mutant: prefix.decode("utf-8") strict (raises on truncated multi-byte).
    """
    # '€' is U+20AC → E2 82 AC. Pad to 5 MiB - 1, start '€', then trail.
    pad = b"a" * (5 * ONE_MB - 1)
    payload = pad + b"\xe2\x82\xac" + b"more"
    out_bytes, outcome = apply_raw_artifact_truncation(payload, truncate_mb=5)
    assert isinstance(outcome, Truncated)
    wrapper = json.loads(out_bytes)
    assert isinstance(wrapper["data"], str)
    # The last byte of the prefix is 0xE2 (start of '€'); standalone invalid UTF-8
    # → decode(errors="replace") yields '...aaa' + U+FFFD.
    assert wrapper["data"].endswith("�")


def test_truncate_mb_zero_raises() -> None:
    """AC-9 — non-positive truncate_mb fails loud at construction (Rule 12)."""
    with pytest.raises(ValueError):
        apply_raw_artifact_truncation(b"x", truncate_mb=0)


def test_truncate_mb_negative_raises() -> None:
    """AC-9 — negative truncate_mb fails loud."""
    with pytest.raises(ValueError):
        apply_raw_artifact_truncation(b"x", truncate_mb=-1)
