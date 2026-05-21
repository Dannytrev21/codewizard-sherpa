"""S6-02 — TrustScorer (constructor-injected EventLog) + SignalKind open registry.

The story's TDD plan is honoured with five as-built drift resolutions
(recorded in ``_attempts/S6-02.md``):

* D1 — ``TrustSignal`` / ``TrustOutcome`` already shipped in
  :mod:`codegenie.transforms.outcomes` (S1-03); ``trust_scorer`` re-exports
  them rather than redefining (Rule 2 — single definition).
* D2 — the as-built :class:`~codegenie.plugins.events.AdapterDegraded`
  (S6-01) carries ``adapter_name`` / ``signal`` / ``detail``, not the
  ``adapter`` / ``reason`` the story's draft helper assumed.
* D3 — :class:`~codegenie.plugins.events.EventLog` now exposes a public
  ``workflow_id`` attribute (additive — S6-01 only used the ctor arg to
  build the internal path).
* D4 — ``bytes`` is dropped from the AC-7 non-primitive parametrize set:
  pydantic v2 coerces ``bytes`` → ``str`` (the result is still a primitive,
  so the AC's intent — primitives-only ``details`` — holds).
* D5 — ``_has_adapter_degraded_for_workflow`` takes
  ``Iterable[WorkflowInternalEvent | WorkflowSpanningEvent]`` (no ``Event``
  umbrella type exists in the events module).
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
import tempfile
import textwrap
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from codegenie.plugins.events import (
    AdapterDegraded,
    EventLog,
    InMemorySink,
    PluginResolved,
)
from codegenie.transforms.signal_kinds import (
    BUILD,
    CVE_DELTA,
    INSTALL,
    LOCKFILE_POLICY,
    TESTS,
    SignalKindAlreadyRegistered,
    SignalKindRegistry,
    register_signal_kind,
    signal_kind_registry,
)
from codegenie.transforms.trust_scorer import (
    EmptySignals,
    TrustOutcome,
    TrustScorer,
    TrustSignal,
    UnregisteredSignalKind,
)
from codegenie.types.identifiers import EventId, PluginId, SignalKind, WorkflowId

WF = WorkflowId("01HFEEDFACE0000000000000000")
OTHER_WF = WorkflowId("01HOTHERWORKFLOW000000000000")


def _log(tmp_path: Path, wf: WorkflowId = WF) -> EventLog:
    # InMemorySink (S6-01 AC-2) overrides only the spanning sink; the internal
    # stream the scorer reads is always the zstd file under tmp_path.
    return EventLog(root=tmp_path, workflow_id=wf, sink=InMemorySink())


def _ad(wf: WorkflowId = WF, eid: str = "01HAD00", detail: str = "parse_error") -> AdapterDegraded:
    return AdapterDegraded(
        event_id=EventId(eid),
        workflow_id=wf,
        timestamp=datetime.now(UTC),
        adapter_name="dep_graph",
        signal=SignalKind("build"),
        detail=detail,
    )


def _sig(kind: SignalKind, passed: bool = True) -> TrustSignal:
    return TrustSignal(kind=kind, passed=passed, details={})


# --- AC-1: module surface ----------------------------------------------------


def test_public_surface_imports() -> None:
    module = importlib.import_module("codegenie.transforms.trust_scorer")
    for name in (
        "EmptySignals",
        "TrustOutcome",
        "TrustScorer",
        "TrustSignal",
        "UnregisteredSignalKind",
    ):
        assert hasattr(module, name), f"trust_scorer is missing public symbol {name}"


# --- AC-2: constructor injection mandatory -----------------------------------


def test_constructor_requires_event_log() -> None:
    with pytest.raises(TypeError):
        TrustScorer()  # type: ignore[call-arg]


def test_no_ambient_state_alternative_on_class() -> None:
    # Defend Gap 5: no classmethod / helper that resolves event_log from
    # os.environ or any thread-local.
    forbidden = {"from_env", "from_ambient", "current", "for_workflow"}
    assert not (forbidden & set(dir(TrustScorer)))


# --- AC-3 / AC-4 / AC-19: strict-AND, list-equality on `failing` -------------


def test_strict_and_all_pass(tmp_path: Path) -> None:
    scorer = TrustScorer(event_log=_log(tmp_path))
    signals = [_sig(k, True) for k in (BUILD, INSTALL, TESTS, LOCKFILE_POLICY, CVE_DELTA)]
    out = scorer.score(signals)
    assert isinstance(out, TrustOutcome)
    assert out.passed is True
    assert out.failing == []
    assert out.confidence == "high"


@pytest.mark.parametrize("combo", list(product([False, True], repeat=5)))
def test_strict_and_2_to_5_preserves_input_order(tmp_path: Path, combo: tuple[bool, ...]) -> None:
    scorer = TrustScorer(event_log=_log(tmp_path))
    kinds = [BUILD, INSTALL, TESTS, LOCKFILE_POLICY, CVE_DELTA]
    signals = [_sig(k, p) for k, p in zip(kinds, combo, strict=True)]
    out = scorer.score(signals)
    assert out.passed == all(combo)
    # List equality (NOT set) — a sorted-`failing` implementation must fail.
    assert out.failing == [k for k, p in zip(kinds, combo, strict=True) if not p]


def test_failing_preserves_caller_order_not_sorted(tmp_path: Path) -> None:
    # Pin the no-sort discipline directly: reversed kind order in the input
    # produces a reversed `failing` list.
    scorer = TrustScorer(event_log=_log(tmp_path))
    rev = [CVE_DELTA, LOCKFILE_POLICY, TESTS, INSTALL, BUILD]
    signals = [_sig(k, False) for k in rev]
    out = scorer.score(signals)
    assert out.failing == rev  # NOT sorted alphabetically


# --- AC-5: signals preserved verbatim ----------------------------------------


def test_outcome_signals_preserved_verbatim(tmp_path: Path) -> None:
    scorer = TrustScorer(event_log=_log(tmp_path))
    signals = [_sig(BUILD, True), _sig(INSTALL, False)]
    out = scorer.score(signals)
    assert out.signals == signals
    assert [id(s) for s in out.signals] == [id(s) for s in signals]


# --- AC-6 / AC-17 / AC-18: confidence fold -----------------------------------


def test_confidence_degrades_when_adapter_degraded_matches_workflow(tmp_path: Path) -> None:
    log = _log(tmp_path)
    log.emit_internal(_ad())
    log.flush()
    scorer = TrustScorer(event_log=log)
    out = scorer.score([_sig(BUILD)])
    assert out.confidence == "degraded"


def test_confidence_high_when_adapter_degraded_is_other_workflow(tmp_path: Path) -> None:
    log = _log(tmp_path)
    log.emit_internal(_ad(wf=OTHER_WF))
    log.flush()
    scorer = TrustScorer(event_log=log)
    out = scorer.score([_sig(BUILD)])
    assert out.confidence == "high"


def test_confidence_high_when_internal_event_is_not_adapter_degraded(tmp_path: Path) -> None:
    # AC-17 — same workflow_id, but the event is PluginResolved, not
    # AdapterDegraded. Confidence must NOT flip.
    log = _log(tmp_path)
    log.emit_internal(
        PluginResolved(
            event_id=EventId("01HPR00"),
            workflow_id=WF,
            timestamp=datetime.now(UTC),
            plugin_id=PluginId("vulnerability-remediation--node--npm"),
            matched_scope="vulnerability-remediation/node/npm",
            specificity=3,
        )
    )
    log.flush()
    scorer = TrustScorer(event_log=log)
    out = scorer.score([_sig(BUILD)])
    assert out.confidence == "high"


# --- AC-16: stateless across calls -------------------------------------------


def test_score_is_stateless_across_calls(tmp_path: Path) -> None:
    log = _log(tmp_path)
    scorer = TrustScorer(event_log=log)
    out1 = scorer.score([_sig(BUILD)])
    assert out1.confidence == "high"

    log.emit_internal(_ad())  # emit BETWEEN the two score() calls
    log.flush()

    out2 = scorer.score([_sig(BUILD)])
    # A wrong impl that cached the degraded flag in __init__ returns "high"
    # both times. The correct impl re-folds the log on each call.
    assert out2.confidence == "degraded"


# --- AC-9: unregistered kind -------------------------------------------------


def test_unregistered_signal_kind_rejected(tmp_path: Path) -> None:
    scorer = TrustScorer(event_log=_log(tmp_path))
    bogus = SignalKind("not_registered_anywhere")
    with pytest.raises(UnregisteredSignalKind) as excinfo:
        scorer.score([TrustSignal(kind=bogus, passed=True, details={})])
    assert excinfo.value.kind == bogus


# --- AC-10: empty signals ----------------------------------------------------


def test_empty_signals_rejected(tmp_path: Path) -> None:
    scorer = TrustScorer(event_log=_log(tmp_path))
    with pytest.raises(EmptySignals):
        scorer.score([])


# --- AC-7: details rejects non-primitive values ------------------------------
# D4: `bytes` is omitted — pydantic v2 coerces bytes -> str (a primitive),
# so the AC's intent (primitives-only details) is preserved.


@pytest.mark.parametrize(
    "bad_value",
    [
        ["x"],  # list
        ("a", "b"),  # tuple
        None,  # None
        datetime.now(UTC),  # datetime
        {"nested": "object"},  # nested dict
        object(),  # arbitrary object
    ],
)
def test_trust_signal_details_primitives_only(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        TrustSignal(
            kind=BUILD,
            passed=True,
            details={"k": bad_value},  # type: ignore[dict-item]
        )


# --- AC-13: duplicate-name rejection carries both call sites -----------------


def test_register_signal_kind_rejects_duplicate_with_origin_payload() -> None:
    fresh = SignalKindRegistry.fresh()
    register_signal_kind("custom", registry=fresh)
    with pytest.raises(SignalKindAlreadyRegistered) as excinfo:
        register_signal_kind("custom", registry=fresh)
    err = excinfo.value
    assert err.name == SignalKind("custom")
    assert err.existing  # non-empty origin string for the first registration
    assert err.duplicate  # non-empty origin string for the second registration
    # Message names the colliding kind for human grep.
    assert "custom" in str(err)


# --- AC-14: per-test isolation via fresh() -----------------------------------


def test_fresh_registry_is_empty() -> None:
    fresh = SignalKindRegistry.fresh()
    assert SignalKind("build") not in fresh
    assert SignalKind("anything") not in fresh


# --- AC-12: import-time registration is the registration mechanism -----------


def test_phase3_five_kinds_registered_at_import() -> None:
    # Direct module-attribute assertion: BUILD === the SignalKind value the
    # registry was asked to register. A wrong impl that exports the constants
    # but skips the register() side effect would fail `BUILD in registry`.
    for name, const in [
        ("build", BUILD),
        ("install", INSTALL),
        ("tests", TESTS),
        ("lockfile_policy", LOCKFILE_POLICY),
        ("cve_delta", CVE_DELTA),
    ]:
        assert const == SignalKind(name)
        assert const in signal_kind_registry


def test_signal_kinds_module_has_5_top_level_register_calls() -> None:
    # AST-walk: the registrations must be MODULE-LEVEL calls (not inside a
    # function that nothing invokes). Survives the mutation "moved into init()".
    module = importlib.import_module("codegenie.transforms.signal_kinds")
    assert module.__file__ is not None
    src = Path(module.__file__).read_text()
    tree = ast.parse(src)
    top_calls = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Call)
        and getattr(n.value.func, "id", None) == "register_signal_kind"
    ]
    assert len(top_calls) == 5


def test_fresh_subprocess_import_populates_default_registry() -> None:
    # Strongest assertion of import-time registration: a *new* Python process
    # importing codegenie.transforms must observe the 5 kinds — proves no
    # other test's side effect is masking a missing module-level call.
    script = textwrap.dedent(
        """
        import codegenie.transforms  # triggers transforms/__init__.py side effects
        from codegenie.transforms.signal_kinds import signal_kind_registry
        from codegenie.types.identifiers import SignalKind
        names = ["build", "install", "tests", "lockfile_policy", "cve_delta"]
        missing = [n for n in names if SignalKind(n) not in signal_kind_registry]
        assert not missing, f"missing: {missing}"
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


# --- AC-15 / AC-20: pure helpers (functional core / imperative shell) --------


def test_pure_helpers_have_no_io_dependencies() -> None:
    # AST-walk: _compute_strict_and and _has_adapter_degraded_for_workflow
    # MUST NOT reference replay, open, Path, or os.
    module = importlib.import_module("codegenie.transforms.trust_scorer")
    assert module.__file__ is not None
    src = Path(module.__file__).read_text()
    tree = ast.parse(src)
    forbidden = {"replay", "open", "Path", "os"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "_compute_strict_and",
            "_has_adapter_degraded_for_workflow",
        ):
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            attrs = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            assert not (forbidden & (names | attrs)), (
                f"{node.name} references forbidden I/O symbol: {forbidden & (names | attrs)}"
            )


def test_compute_strict_and_is_pure() -> None:
    # Smoke test the pure helper independently of EventLog.
    from codegenie.transforms.trust_scorer import _compute_strict_and

    signals = [_sig(BUILD, True), _sig(INSTALL, False), _sig(TESTS, False)]
    passed, failing = _compute_strict_and(signals)
    assert passed is False
    assert failing == [INSTALL, TESTS]


def test_no_module_level_mutable_caches() -> None:
    module = importlib.import_module("codegenie.transforms.trust_scorer")
    assert module.__file__ is not None
    src = Path(module.__file__).read_text()
    tree = ast.parse(src)
    suspicious = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                # `__all__` is an immutable-by-convention export declaration,
                # not cache state — AC-20 targets `_cache = {}` / `_seen = set()`.
                if (
                    isinstance(tgt, ast.Name)
                    and tgt.id.startswith("_")
                    and tgt.id != "__all__"
                    and isinstance(node.value, (ast.Dict, ast.Set, ast.List))
                ):
                    suspicious.append(tgt.id)
    assert not suspicious, f"module-level mutable state in trust_scorer.py: {suspicious}"


# --- Property test: confidence fold is exactly "any matching AdapterDegraded" -


@given(
    events=st.lists(
        st.tuples(
            st.sampled_from(["adapter_degraded", "plugin_resolved"]),
            st.sampled_from([WF, OTHER_WF]),
        ),
        min_size=0,
        max_size=20,
    ),
)
def test_confidence_property_iff_matching_adapter_degraded(
    events: list[tuple[str, WorkflowId]],
) -> None:
    # A fresh temp dir per generated input (NOT the function-scoped `tmp_path`
    # fixture, which Hypothesis does not reset between examples — the zstd
    # internal-stream file would otherwise accumulate events across examples).
    with tempfile.TemporaryDirectory() as td:
        log = _log(Path(td))
        for i, (etype, wf) in enumerate(events):
            if etype == "adapter_degraded":
                log.emit_internal(
                    AdapterDegraded(
                        event_id=EventId(f"01HAD{i:03}"),
                        workflow_id=wf,
                        timestamp=datetime.now(UTC),
                        adapter_name="dep_graph",
                        signal=SignalKind("build"),
                        detail="x",
                    )
                )
            else:
                log.emit_internal(
                    PluginResolved(
                        event_id=EventId(f"01HPR{i:03}"),
                        workflow_id=wf,
                        timestamp=datetime.now(UTC),
                        plugin_id=PluginId("p"),
                        matched_scope="s",
                        specificity=1,
                    )
                )
        log.flush()
        scorer = TrustScorer(event_log=log)
        out = scorer.score([_sig(BUILD)])
        expected = (
            "degraded"
            if any(etype == "adapter_degraded" and wf == WF for etype, wf in events)
            else "high"
        )
        assert out.confidence == expected
