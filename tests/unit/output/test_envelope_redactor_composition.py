"""S3-03 — envelope-level redactor three-pass composition order.

Covers ACs 4, 5, 6, 7: the module docstring documents the three-pass
ladder and references the gating ADRs; the canonical order
``("known_patterns", "entropy", "build")`` is verified by mock-spy
through a shared ``record: list[str]``; a paired reorder mutation
verifies the recording mechanism is order-sensitive (so the canonical
assertion can't pass spuriously); the entry-point's return-type
annotation is :class:`RedactedSlice` (the seam consumes a typed
wrapper, not a tuple).
"""

from __future__ import annotations

import inspect
import typing
from typing import Any
from unittest.mock import Mock

import pytest

from codegenie.output import envelope_redactor as er
from codegenie.output.redacted_slice import RedactedSlice

# ---------------------------------------------------------------------------
# AC-4 — Composition order documented in module docstring (gating ADRs cited)
# ---------------------------------------------------------------------------


def test_ac4_docstring_documents_composition_and_adrs() -> None:
    doc = inspect.getdoc(er) or ""
    normalized = " ".join(doc.split())  # collapse word-wrap (lesson L8)
    for substr in ("02-ADR-0005", "02-ADR-0010", "02-ADR-0008", "Three-pass composition"):
        assert substr in normalized, f"missing {substr!r} in module docstring"


# ---------------------------------------------------------------------------
# AC-5 — Mock-spy verifies canonical order through a shared record list
# ---------------------------------------------------------------------------


_PASS_NAME_BY_REF: dict[Any, str] = {
    er._redact_known_patterns_pass: "known_patterns",
    er._redact_entropy_pass: "entropy",
    er._build_redacted_slice_pass: "build",
}


def _build_recording_spies(record: list[str], passes: tuple[Any, ...]) -> tuple[Any, ...]:
    """Wrap each pass so it appends its name to ``record`` then delegates."""
    spies: list[Any] = []
    for pass_ in passes:
        name = _PASS_NAME_BY_REF[pass_]

        def make_spy(p: Any = pass_, n: str = name) -> Any:
            def _spy(slice_: Any) -> Any:
                record.append(n)
                return p(slice_)

            return Mock(side_effect=_spy, wraps=p)

        spies.append(make_spy())
    return tuple(spies)


def test_ac5_redact_envelope_invokes_passes_in_canonical_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: list[str] = []
    spies = _build_recording_spies(record, er._PASSES)
    monkeypatch.setattr(er, "_PASSES", spies)

    result = er._redact_envelope({"k": "AKIAIOSFODNN7EXAMPLE"})

    assert record == ["known_patterns", "entropy", "build"], record
    for spy in spies:
        assert spy.call_count == 1
    assert isinstance(result, RedactedSlice)


# ---------------------------------------------------------------------------
# AC-6 — Mutation-sensitivity paired tests
# ---------------------------------------------------------------------------


def test_ac6_reorder_mutation_changes_recorded_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: list[str] = []
    mutated_passes = (
        er._redact_entropy_pass,
        er._redact_known_patterns_pass,
        er._build_redacted_slice_pass,
    )
    spies = _build_recording_spies(record, mutated_passes)
    monkeypatch.setattr(er, "_PASSES", spies)

    er._redact_envelope({"k": "AKIAIOSFODNN7EXAMPLE"})

    assert record == ["entropy", "known_patterns", "build"], record


def test_ac6_canonical_order_under_no_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: list[str] = []
    spies = _build_recording_spies(record, er._PASSES)
    monkeypatch.setattr(er, "_PASSES", spies)

    er._redact_envelope({"k": "AKIAIOSFODNN7EXAMPLE"})

    assert record == ["known_patterns", "entropy", "build"], record


# ---------------------------------------------------------------------------
# AC-7 — Entry point return type is RedactedSlice
# ---------------------------------------------------------------------------


def test_ac7_redact_envelope_return_type_is_redacted_slice() -> None:
    hints = typing.get_type_hints(er._redact_envelope)
    assert hints["return"] is RedactedSlice, hints


# ---------------------------------------------------------------------------
# Pass invocation outside _redact_envelope raises (defense-in-depth)
# ---------------------------------------------------------------------------


def test_pass_invoked_outside_redact_envelope_raises() -> None:
    # The ContextVar carries None by default → state lookup raises a clear
    # RuntimeError pointing at the canonical entry point.
    with pytest.raises(RuntimeError, match=r"_redact_envelope"):
        er._redact_known_patterns_pass({"k": "AKIAIOSFODNN7EXAMPLE"})
