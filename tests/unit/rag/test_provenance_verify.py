"""Phase-4 S4-05 — unit tests for ``codegenie.rag.provenance.verify``.

Pure-predicate ACs (AC-1, AC-2, AC-4, AC-5, AC-6, AC-7, AC-12). The
membership Hypothesis property (AC-8) lives in
``tests/property/test_provenance_verify_membership_property.py`` and the
caller-emission smoke (AC-9) lives in
``tests/integration/test_phase4_provenance_orphan_emit.py`` — both close
the final-design §Component 11 contract this story ships.
"""

from __future__ import annotations

import ast
import inspect
from unittest.mock import Mock

import pytest

from codegenie.rag.provenance import SpanningChainLog, verify
from codegenie.types.identifiers import ChainHead
from tests.fixtures.rag.fake_solved_example import make_solved_example

_KNOWN = ChainHead("a" * 64)
_FORGED = ChainHead("b" * 64)


# --- AC-4 --------------------------------------------------------------------


def test_verify_returns_true_when_chain_head_in_spanning_log() -> None:
    """Edge case #14 + final-design Component 11: appearance-in-log is the
    chain-verification contract. Catches always-True and always-False mutants."""
    record = make_solved_example(id_="a" * 64, event_chain_head=str(_KNOWN))
    log = Mock(spec=SpanningChainLog)
    log.contains_chain_head.side_effect = lambda h: h == _KNOWN

    assert verify(record, log) is True
    log.contains_chain_head.assert_called_once_with(_KNOWN)


# --- AC-5 --------------------------------------------------------------------


def test_verify_returns_false_when_chain_head_absent() -> None:
    """Forged or chain-orphan record case — the load-bearing security property."""
    record = make_solved_example(id_="b" * 64, event_chain_head=str(_FORGED))
    log = Mock(spec=SpanningChainLog)
    log.contains_chain_head.return_value = False

    assert verify(record, log) is False
    log.contains_chain_head.assert_called_once_with(_FORGED)


# --- AC-7 --------------------------------------------------------------------


def test_verify_empty_chain_head_returns_false_without_log_call() -> None:
    """Defense in depth: a direct ``ChainHead("")`` cast can forge an empty
    head even though S1-01's smart constructor rejects it at the boundary."""
    record = make_solved_example(id_="c" * 64, event_chain_head=str(_KNOWN))
    forged_provenance = record.provenance.model_copy(update={"event_chain_head": ChainHead("")})
    forged_record = record.model_copy(update={"provenance": forged_provenance})
    log = Mock(spec=SpanningChainLog)

    assert verify(forged_record, log) is False
    log.contains_chain_head.assert_not_called()


# --- AC-6 (mock side) --------------------------------------------------------


def test_verify_calls_only_contains_chain_head_on_spanning_log() -> None:
    """Mock(spec=...) lets us assert no other Protocol method is touched
    even if a future implementer added one."""
    record = make_solved_example(id_="d" * 64, event_chain_head=str(_KNOWN))
    log = Mock(spec=SpanningChainLog)
    log.contains_chain_head.return_value = True

    verify(record, log)

    # ``contains_chain_head`` is the only method that should have been called.
    assert log.method_calls == [("contains_chain_head", (_KNOWN,), {})]


def test_verify_does_not_mutate_record() -> None:
    """Records are frozen Pydantic models; verify reads only, never writes."""
    record = make_solved_example(id_="e" * 64, event_chain_head=str(_KNOWN))
    log = Mock(spec=SpanningChainLog)
    log.contains_chain_head.return_value = True

    snapshot = record.model_dump_json()
    verify(record, log)
    assert record.model_dump_json() == snapshot


# --- AC-6 (AST side) ---------------------------------------------------------

_FORBIDDEN_CALL_TOKENS = (
    "EventLog",
    "emit_internal",
    "emit_spanning",
    "open(",
    "Path(",
    "os.",
    "subprocess.",
    "socket.",
    "requests.",
    "logging.",
)


def test_verify_source_has_no_io_or_event_dependency() -> None:
    """The verifier is the functional core; caller owns EventLog emission."""
    src = inspect.getsource(verify)
    for token in _FORBIDDEN_CALL_TOKENS:
        assert token not in src, f"verify must not reference {token!r}: pure-predicate contract"


def test_verify_module_calls_only_allowed_callables() -> None:
    """AST guarantee: the only call inside ``verify`` is
    ``spanning_log.contains_chain_head(head)`` — no hidden side effects.
    """
    from codegenie.rag import provenance as provenance_module

    src = inspect.getsource(provenance_module)
    tree = ast.parse(src)

    verify_func: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "verify":
            verify_func = node
            break
    assert verify_func is not None, "expected to find function `verify` in provenance.py"

    calls: list[str] = []
    for sub in ast.walk(verify_func):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Attribute):
                calls.append(func.attr)
            elif isinstance(func, ast.Name):
                calls.append(func.id)
    # Only one Call should be made — ``spanning_log.contains_chain_head(head)``.
    # ``bool(...)`` truthiness check on ``head`` is via ``if not head``, not a Call.
    assert calls == ["contains_chain_head"], f"unexpected calls in verify: {calls!r}"


# --- AC-1 / AC-2 -------------------------------------------------------------


def test_verify_signature_module_level_function() -> None:
    """No staticmethod alias on RecordProvenance; ``verify`` is a module-level
    function consumed by the retriever (S5-01)."""
    sig = inspect.signature(verify)
    params = list(sig.parameters)
    assert params == ["record", "spanning_log"]
    assert sig.return_annotation in (bool, "bool")


def test_spanning_chain_log_protocol_has_exactly_two_methods() -> None:
    """S4-05 AC-2 + Phase-4 S5-01 ``head()`` extension: the surface stays
    bounded to two methods. ``contains_chain_head`` (S4-05) +
    ``head()`` (S5-01 — the RagRecordChainOrphan needs the current
    spanning-log head for triage). Do **not** extend to
    ``get_chain_segment`` / ``iter_events`` / ``record_id_for_head``."""
    members = {
        name
        for name in dir(SpanningChainLog)
        if not name.startswith("_") and callable(getattr(SpanningChainLog, name))
    }
    assert members == {"contains_chain_head", "head"}, members


def test_spanning_chain_log_is_runtime_checkable() -> None:
    """S4-05 AC-2: a duck-typed fake satisfies isinstance() at runtime.

    With the Phase-4 S5-01 extension, the fake now needs both
    ``contains_chain_head`` AND ``head``."""

    class _FakeLog:
        def contains_chain_head(self, head: ChainHead) -> bool:
            del head
            return False

        def head(self) -> ChainHead:
            return ChainHead("0" * 64)

    assert isinstance(_FakeLog(), SpanningChainLog)


def test_recordprovenance_has_no_verify_staticmethod() -> None:
    """AC-1: ``RecordProvenance.verify`` would invite a circular import; the
    arch-prose contract is met by the module-level function instead."""
    from codegenie.rag.models import RecordProvenance

    assert not hasattr(RecordProvenance, "verify"), (
        "RecordProvenance.verify staticmethod alias is forbidden by S4-05 §1"
    )


# --- AC-12 -------------------------------------------------------------------


_STALE_FIELD_NAMES = (
    "record_chain_head",
    "model_id",
    "embedding_dim",
    "trust_outcome_passed",
)


def test_provenance_module_does_not_reference_stale_fields() -> None:
    """AC-12: the validator hardened RecordProvenance to four fields; ensure
    drafts referring to removed names never sneak back in."""
    from codegenie.rag import provenance as provenance_module

    src = inspect.getsource(provenance_module)
    for stale in _STALE_FIELD_NAMES:
        assert stale not in src, f"stale RecordProvenance field name leaked: {stale!r}"


# --- AC-1 — sanity: the verifier reads exactly ``event_chain_head`` ---------


def test_verify_reads_event_chain_head_field() -> None:
    """Catches a wrong-attribute mutant where someone reads
    ``record.provenance.workflow_id`` or another field by mistake.
    """
    record = make_solved_example(id_="f" * 64, event_chain_head=str(_KNOWN))
    seen: list[ChainHead] = []
    log = Mock(spec=SpanningChainLog)
    log.contains_chain_head.side_effect = lambda h: seen.append(h) or True

    verify(record, log)

    assert seen == [record.provenance.event_chain_head]


# --- AC-1 — sanity: pure-predicate boundary (no env / sleep / time) ---------


def test_verify_does_not_sleep_or_read_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A defensive smoke test — verify must not touch process state."""
    import os as _os
    import time as _time

    called: list[str] = []
    monkeypatch.setattr(_time, "sleep", lambda *_a, **_k: called.append("sleep"))
    monkeypatch.setattr(_os, "getenv", lambda *_a, **_k: called.append("getenv") or "")

    record = make_solved_example(id_="g" * 64, event_chain_head=str(_KNOWN))
    log = Mock(spec=SpanningChainLog)
    log.contains_chain_head.return_value = True

    verify(record, log)
    assert called == []
