"""S3-03 — Writer log emission for `secrets_redacted_count` (02-ADR-0008).

Covers ACs 8, 8b, 9, 10, 11, 12, 12b: the constants
:data:`SECRETS_REDACTED_COUNT_FIELD` and :data:`EVENT_ENVELOPE_WRITTEN`
live in :mod:`codegenie.logging`, are exported via ``__all__``, and are
imported by ``Writer.write`` *by name* (no string literals at the call
site); the writer emits exactly one ``envelope.written`` event per
successful ``write`` call carrying the
``secrets_redacted_count=findings_count`` field (zero-count runs emit
the field explicitly so ``grep`` stays useful for auditors); failure
paths are silent on ``envelope.written``; persisted YAML carries
``<REDACTED:fingerprint=…>`` placeholders, not plaintext, and never
leaks :class:`SecretFinding` field names.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any

import pytest
import structlog.testing

import codegenie.logging as cg_log
import codegenie.output.writer as writer_mod
from codegenie.output.envelope_redactor import _redact_envelope
from codegenie.output.sanitizer import redact_secrets
from codegenie.output.writer import Writer
from codegenie.types.identifiers import ProbeId

# ---------------------------------------------------------------------------
# AC-8 / AC-8b — constants, __all__ export, no string-literal drift
# ---------------------------------------------------------------------------


def test_ac8_constants_have_canonical_values() -> None:
    assert cg_log.SECRETS_REDACTED_COUNT_FIELD == "secrets_redacted_count"
    assert cg_log.EVENT_ENVELOPE_WRITTEN == "envelope.written"


def test_ac8b_constants_exported_via_all() -> None:
    assert "SECRETS_REDACTED_COUNT_FIELD" in cg_log.__all__
    assert "EVENT_ENVELOPE_WRITTEN" in cg_log.__all__


def test_ac8_no_string_literals_at_writer_call_site() -> None:
    src = inspect.getsource(Writer.write)
    assert not re.search(r'["\']secrets_redacted_count["\']', src), src
    assert not re.search(r'["\']envelope\.written["\']', src), src


# ---------------------------------------------------------------------------
# AC-9 / AC-10 — count field emitted on zero and non-zero counts
# ---------------------------------------------------------------------------


def _capture_writer_logs(envelope: Any, output_dir: Path) -> list[dict[str, Any]]:
    with structlog.testing.capture_logs() as captured:
        Writer().write(envelope, [], output_dir)
    return list(captured)


def test_ac9_count_field_emitted_on_zero_count(tmp_path: Path) -> None:
    redacted, _ = redact_secrets({}, ProbeId("__envelope__"))
    assert redacted.findings_count == 0

    captured = _capture_writer_logs(redacted, tmp_path / "ctx")
    events = [r for r in captured if r.get("event") == "envelope.written"]
    assert len(events) == 1, events
    assert events[0]["secrets_redacted_count"] == 0


def test_ac10_count_field_emitted_on_nonzero_count(tmp_path: Path) -> None:
    seeded = {
        "p1": {"aws": "AKIAIOSFODNN7EXAMPLE"},
        "p2": {"aws2": "AKIA1234567890ABCDEF"},
        "p3": {"gh": "ghp_" + "a" * 36},
    }
    redacted = _redact_envelope(seeded)
    assert redacted.findings_count == 3

    captured = _capture_writer_logs(redacted, tmp_path / "ctx")
    events = [r for r in captured if r.get("event") == "envelope.written"]
    assert len(events) == 1
    assert events[0]["secrets_redacted_count"] == 3


# ---------------------------------------------------------------------------
# AC-11 — event uniqueness + failure-path silence
# ---------------------------------------------------------------------------


def test_ac11_event_unique_per_write_call(tmp_path: Path) -> None:
    redacted, _ = redact_secrets({}, ProbeId("__envelope__"))
    with structlog.testing.capture_logs() as captured:
        Writer().write(redacted, [], tmp_path / "a")
        Writer().write(redacted, [], tmp_path / "b")
    events = [r for r in captured if r.get("event") == "envelope.written"]
    assert len(events) == 2


def test_ac11_no_event_on_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    redacted, _ = redact_secrets({}, ProbeId("__envelope__"))

    def boom(_dest: Path, _payload: bytes) -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr(writer_mod, "_atomic_write_bytes", boom)
    with structlog.testing.capture_logs() as captured, pytest.raises(OSError):
        Writer().write(redacted, [], tmp_path / "ctx")
    assert [r for r in captured if r.get("event") == "envelope.written"] == []


# ---------------------------------------------------------------------------
# AC-12 / AC-12b — sanitizer → writer → YAML dataflow assertions
# ---------------------------------------------------------------------------


def test_ac12_persisted_yaml_has_no_plaintext_no_finding_fields(tmp_path: Path) -> None:
    aws1 = "AKIAIOSFODNN7EXAMPLE"
    aws2 = "AKIA1234567890ABCDEF"
    high_entropy = "Zk93jH2lP8qX4vR1bN6wM5tY7uA0sC3eF" + "BHnLP9vQz2W4xK"
    envelope_in = {
        "probes": {
            "p1": {"value": aws1},
            "p2": {"value": aws2},
            "p3": {"value": high_entropy},
        }
    }

    redacted = _redact_envelope(envelope_in)
    assert redacted.findings_count >= 3

    out_dir = tmp_path / "ctx"
    Writer().write(redacted, [], out_dir)
    yaml_bytes = (out_dir / "repo-context.yaml").read_bytes()

    # Negative — no plaintext leaked.
    for plaintext in (aws1, aws2, high_entropy):
        assert plaintext.encode("utf-8") not in yaml_bytes, plaintext

    # Negative — no SecretFinding field names persisted.
    assert b"pattern_class" not in yaml_bytes
    assert b"cleartext_len" not in yaml_bytes

    # Positive — the redactor actually ran.
    assert b"<REDACTED:fingerprint=" in yaml_bytes


def test_ac12b_per_probe_placeholder_is_idempotent_under_envelope_pass(
    tmp_path: Path,
) -> None:
    placeholder = "<REDACTED:fingerprint=abcdef12>"
    novel = "ghp_" + "z" * 36
    envelope_in = {
        "p1": {"value": placeholder},  # post-per-probe-scrub shape
        "p2": {"value": novel},
    }
    redacted = _redact_envelope(envelope_in)

    # Only the novel-shape secret should be counted at the envelope layer.
    assert redacted.findings_count == 1
    assert redacted.slice["p1"] == {"value": placeholder}
    novel_slot: Any = redacted.slice["p2"]
    assert novel_slot["value"].startswith("<REDACTED:fingerprint=")
    assert novel not in novel_slot["value"]

    # End-to-end through the writer — placeholder survives, no double count.
    captured = _capture_writer_logs(redacted, tmp_path / "ctx")
    events = [r for r in captured if r.get("event") == "envelope.written"]
    assert events[0]["secrets_redacted_count"] == 1
    yaml_bytes = (tmp_path / "ctx" / "repo-context.yaml").read_bytes()
    assert placeholder.encode("utf-8") in yaml_bytes
