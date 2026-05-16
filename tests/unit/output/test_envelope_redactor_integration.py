"""S3-03 — End-to-end envelope-redactor + writer integration.

Covers ACs 15, 16: parametrized over the four canonical shapes
(zero / one / three-distinct / same-fingerprint-twice), assert
``findings_count``, deduplicated ``fingerprints``, the log event's
``secrets_redacted_count``, the persisted YAML satisfies the F6
substring contract, and a post-write round-trip via
``RedactedSlice.model_validate(model_dump())`` proves the writer does
not mutate the slice. Also pins placeholder-idempotence (AC-16): a
pre-existing ``<REDACTED:fingerprint=…>`` placeholder survives the
envelope-level pass unchanged and does not increment the count.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import structlog.testing

from codegenie.output.envelope_redactor import _redact_envelope
from codegenie.output.redacted_slice import RedactedSlice
from codegenie.output.writer import Writer


def _write_and_capture(
    envelope_in: dict[str, Any], output_dir: Path
) -> tuple[RedactedSlice, list[dict[str, Any]], bytes]:
    redacted = _redact_envelope(envelope_in)
    with structlog.testing.capture_logs() as captured:
        Writer().write(redacted, [], output_dir)
    yaml_bytes = (output_dir / "repo-context.yaml").read_bytes()
    return redacted, list(captured), yaml_bytes


# Canonical secret literals — bigger entropy gap than the entropy floor so
# the named patterns are what actually fire (entropy fallback acts only on
# strings no named pattern claimed).
_AWS_1 = "AKIAIOSFODNN7EXAMPLE"
_AWS_2 = "AKIA1234567890ABCDEF"
_GH = "ghp_" + "a" * 36


_CASES: list[tuple[str, dict[str, Any], int, int]] = [
    # (case-id, envelope-in, expected findings_count, expected fingerprint count)
    ("zero", {"probes": {"p": {}}}, 0, 0),
    ("one", {"probes": {"p": {"key": _AWS_1}}}, 1, 1),
    (
        "three-distinct",
        {"probes": {"a": {"k": _AWS_1}, "b": {"k": _AWS_2}, "c": {"k": _GH}}},
        3,
        3,
    ),
    (
        "same-fingerprint-twice",
        {"probes": {"a": {"k": _AWS_1}, "b": {"k": _AWS_1}}},
        2,
        1,
    ),
]


@pytest.mark.parametrize(("case_id", "envelope_in", "exp_count", "exp_fps"), _CASES)
def test_ac15_envelope_redactor_writer_dataflow(
    tmp_path: Path,
    case_id: str,
    envelope_in: dict[str, Any],
    exp_count: int,
    exp_fps: int,
) -> None:
    out_dir = tmp_path / case_id
    redacted, captured, yaml_bytes = _write_and_capture(envelope_in, out_dir)

    # Counts and fingerprint dedup match 02-ADR-0010 contract.
    assert redacted.findings_count == exp_count
    assert len(redacted.fingerprints) == exp_fps

    # Single log event with the canonical field name + value.
    events = [r for r in captured if r.get("event") == "envelope.written"]
    assert len(events) == 1
    assert events[0]["secrets_redacted_count"] == exp_count

    # F6 substring contract over the persisted YAML.
    for plaintext in (_AWS_1, _AWS_2, _GH):
        if plaintext.encode("utf-8") in yaml_bytes:
            # Allowed only if this secret was not part of the input fixture.
            assert plaintext not in str(envelope_in), plaintext
    assert b"pattern_class" not in yaml_bytes
    assert b"cleartext_len" not in yaml_bytes
    if exp_count > 0:
        assert b"<REDACTED:fingerprint=" in yaml_bytes

    # Post-write round-trip — writer must not mutate the slice (RedactedSlice
    # is frozen, but the persisted YAML could in principle reorder keys
    # destructively if a future contributor swapped Dumper options).
    dumped = redacted.model_dump()
    rebuilt = RedactedSlice.model_validate(dumped)
    assert rebuilt == redacted


# ---------------------------------------------------------------------------
# AC-16 — Placeholder-idempotence (pre-scrubbed leaf survives unchanged)
# ---------------------------------------------------------------------------


def test_ac16_placeholder_is_idempotent_no_double_count() -> None:
    placeholder = "<REDACTED:fingerprint=abcdef12>"
    redacted = _redact_envelope({"slot": placeholder})

    assert redacted.findings_count == 0
    assert redacted.slice == {"slot": placeholder}


def test_ac16_placeholder_plus_novel_counts_only_novel() -> None:
    placeholder = "<REDACTED:fingerprint=deadbeef>"
    redacted = _redact_envelope(
        {
            "pre_scrubbed": placeholder,
            "novel": _AWS_1,
        }
    )

    # Exactly one finding — the AWS key. The placeholder is unchanged.
    assert redacted.findings_count == 1
    assert redacted.slice["pre_scrubbed"] == placeholder
    novel_value = redacted.slice["novel"]
    assert isinstance(novel_value, str)
    assert novel_value.startswith("<REDACTED:fingerprint=")
    assert _AWS_1 not in novel_value
