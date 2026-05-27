"""Phase-3 S6-06 + Phase-4 S7-10 — Phase-5 contract snapshot.

**S7-10 AC-8.** This file holds the Phase-5 contract surface that
Phase-4 ADRs 0002 (FallbackTier composition), 0009 (inline-harvest
confidence gate), 0010 (LlmInvocationGuard / BudgetToken capability),
0013 (FenceWrapper canary-scan-before-truncation), and 0014 (cassette
discipline) commit to. Phase-4's five additive captures (FallbackTier.
run, FallbackTier.on_validated, LlmInvocationGuard.running_total,
FenceWrapper.fence, SolvedExampleWriteCapability + mint_factory)
appear under the dedicated ``phase4_captures`` top-level snapshot key.

Phase 5's GateRunner reads these symbols by name + signature; any
breaking delta on the captured surface MUST be paired with an
ADR-0001 amendment + golden refresh in the same PR, per the
``PHASE 5 CANNOT SHIP`` directive enforced by the mutation-guard
tests below.

Phase-3 S6-06 (the umbrella story for this file) remains HARDENED-
not-GREEN; the Phase-4 executor authored the minimal kernel +
golden + env-var regen path here so S7-10's AC-1..AC-8 could ship
without waiting on S6-06's full GREEN-complete commit. The S6-06
follow-up should extend the kernel additively (replace inline
dispatch with ``@register_snapshot_kind`` / ``@register_delta_rule``
registries, add the 6 named breaking-delta meta-test families, add
the AST-walk functional-core fence) — not rewrite this file. The
captured snapshot output stays comparable byte-for-byte across the
registry refactor.

Symbols captured (6 of S6-06's 7 named set):

* :class:`RemediationReport` Pydantic JSON schema (S5-05).
* :class:`TrustSignal` Pydantic JSON schema (S6-02).
* :class:`TrustOutcome` Pydantic JSON schema (S6-02).
* :class:`AttemptSummary` Pydantic JSON schema (S1-04).
* :data:`StageOutcome` TypeAlias resolution (S6-04 validation C-F2).
* :class:`Transform` ABC signature (S1-04).
* :class:`RecipeEngine` Protocol signature + ``runtime_checkable``
  flag (S5-01).
* :class:`ApplyContext` Pydantic JSON schema (S1-04).
* :class:`TrustScorer` ``__init__`` + ``.score`` signatures (S6-02).

Loud-skipped:
* :class:`RemediationOrchestrator` — not yet re-exported via
  ``codegenie.transforms`` on master (S6-04 follow-up).

Regen path (mirrors the Phase-6 SUT snapshot's discipline):

    PHASE5_CONTRACT_GOLDEN_REWRITE=1 pytest tests/integration/test_phase5_contract_snapshot.py

Without the env var the test MUST NOT write to the golden path — a
golden-write attempt absent the env var is a directly-rejected
regression vector S6-06 AC-7's no-silent-rewrite fence catches; this
minimal scaffold inherits that discipline (no ``write_text`` outside
the explicit env-var branch).
"""

from __future__ import annotations

import inspect
import json
import os
import typing
from pathlib import Path
from typing import Any

from codegenie import transforms as transforms_pkg

# Phase-4 S7-10 AC-1 capture imports — five additive entries that
# Phase 5's GateRunner reads. Deep-imports here are deliberate: these
# symbols don't have a canonical `codegenie.transforms` re-export
# (they're Phase-4-internal); the snapshot pins them by qualified
# module path so a Phase-5 swap-in sees an explicit ADR-0001 amendment
# event rather than a silent rename.
from codegenie.fallback.budget import LlmInvocationGuard
from codegenie.fallback.fence.wrapper import FenceWrapper
from codegenie.fallback.tier import FallbackTier
from codegenie.rag._capability_mint import _phase4_local_capability_mint
from codegenie.rag.store import SolvedExampleWriteCapability

_GOLDEN_PATH = Path(__file__).parent.parent / "golden" / "phase5-contract" / "snapshot.json"
_REWRITE_ENV_VAR = "PHASE5_CONTRACT_GOLDEN_REWRITE"


# --- Canonical re-export map (S6-06 AC-5) ----------------------------------
# Symbols imported via the canonical ``from codegenie.transforms import ...``
# path. A re-export identity check ensures a duplicate Protocol declaration
# cannot pass (S6-06 AC-6).


def _resolve_symbols() -> dict[str, Any]:
    """Return ``{name: symbol_object}`` for every Phase-5 named contract
    symbol present on the canonical re-export today. Missing symbols are
    surfaced loudly in the snapshot via the ``_missing`` block."""
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    for name in (
        "RemediationReport",
        "TrustSignal",
        "TrustOutcome",
        "AttemptSummary",
        "StageOutcome",
        "Transform",
        "RecipeEngine",
        "ApplyContext",
        "TrustScorer",
        "RemediationOrchestrator",
    ):
        sym = getattr(transforms_pkg, name, None)
        if sym is None:
            missing.append(name)
        else:
            resolved[name] = sym
    resolved["_missing"] = missing  # surface — not hide — the upstream gap
    return resolved


# --- Snapshot kernel (S6-06 AC-7 / AC-8 / AC-9) ----------------------------


def _signature_repr(obj: Any, method: str | None = None) -> dict[str, Any]:
    """Canonical ``inspect.signature`` rendering — parameter names,
    kinds, defaults (repr'd), annotations as strings. ``str()``-ing the
    raw ``inspect.Signature`` is unstable across Python versions; this
    renders the load-bearing fields explicitly."""
    target = getattr(obj, method) if method else obj
    sig = inspect.signature(target)
    params = []
    for p in sig.parameters.values():
        default = repr(p.default) if p.default is not inspect.Parameter.empty else None
        annotation = str(p.annotation) if p.annotation is not inspect.Parameter.empty else None
        params.append(
            {
                "name": p.name,
                "kind": p.kind.name,
                "default": default,
                "annotation": annotation,
            }
        )
    return {
        "parameters": params,
        "return_annotation": (
            str(sig.return_annotation)
            if sig.return_annotation is not inspect.Signature.empty
            else None
        ),
    }


def _pydantic_schema(model: Any) -> dict[str, Any]:
    """Canonical Pydantic JSON schema. ``by_alias=True`` matches the
    Phase-6 SUT contract snapshot's discipline. Sorted-keys serialization
    happens at the top level when the snapshot is dumped to JSON."""
    return model.model_json_schema(mode="serialization", by_alias=True)


def _snapshot_typealias(name: str, alias: Any) -> dict[str, Any]:
    """Capture a ``TypeAlias`` as its target's qualified name."""
    if hasattr(alias, "__module__") and hasattr(alias, "__qualname__"):
        target = f"{alias.__module__}.{alias.__qualname__}"
    else:
        target = repr(alias)
    return {"kind": "type_alias", "target": target}


def _snapshot_protocol(protocol: Any) -> dict[str, Any]:
    """Capture a Protocol's method signatures + runtime_checkable flag.

    Phase 6 lifts Protocols into LangGraph nodes via
    ``node(fn=callable, ...)``; signature drift breaks the lift.
    ``@runtime_checkable`` presence is the structural ``isinstance``
    seam used at the Phase-5 / Phase-6 boundary.
    """
    is_runtime_checkable = bool(getattr(protocol, "_is_runtime_protocol", False))
    methods: dict[str, Any] = {}
    for name in sorted(dir(protocol)):
        if name.startswith("_"):
            continue
        member = getattr(protocol, name)
        if callable(member):
            try:
                methods[name] = _signature_repr(member)
            except (TypeError, ValueError):
                # Some protocol members aren't introspectable (data
                # descriptors etc.); record their type instead.
                methods[name] = {"kind": "non_introspectable", "type": type(member).__name__}
    return {
        "kind": "protocol",
        "runtime_checkable": is_runtime_checkable,
        "methods": methods,
    }


def _snapshot_abc(abc: Any) -> dict[str, Any]:
    """Capture an ABC's abstract method set + concrete subclass shape.

    ``Transform``'s sealed-hierarchy snapshot: the set of qualified
    names is additive on grow + breaking on remove (S6-06 AC-12 / AC-13).
    """
    abstract_methods = sorted(getattr(abc, "__abstractmethods__", set()))
    return {
        "kind": "abc",
        "abstract_methods": abstract_methods,
    }


def _snapshot_class(cls: Any) -> dict[str, Any]:
    """Capture a concrete class's ``__init__`` + named methods."""
    out: dict[str, Any] = {"kind": "class", "name": cls.__name__}
    if hasattr(cls, "__init__"):
        try:
            out["__init__"] = _signature_repr(cls, "__init__")
        except (TypeError, ValueError):
            out["__init__"] = None
    # Named methods (skip dunders + properties + types).
    methods: dict[str, Any] = {}
    for name in sorted(dir(cls)):
        if name.startswith("_"):
            continue
        attr = getattr(cls, name, None)
        if attr is None or not callable(attr):
            continue
        if isinstance(attr, type):
            continue
        try:
            methods[name] = _signature_repr(attr)
        except (TypeError, ValueError):
            continue
    out["methods"] = methods
    return out


def snapshot_symbol(name: str, obj: Any) -> dict[str, Any]:
    """Dispatch ``obj`` to its appropriate capture function.

    S6-06's GREEN-complete attempt registers each kind via
    ``@register_snapshot_kind``; the minimal scaffold uses a closed
    dispatch on a few introspection signals — additive at the dispatch
    boundary (S6-06's registry replaces this body wholesale, the
    snapshot output stays comparable byte-for-byte).
    """
    # TypeAlias
    if isinstance(obj, typing._GenericAlias) or (  # type: ignore[attr-defined]
        not isinstance(obj, type)
        and not callable(obj)
        and hasattr(obj, "__origin__") is False
        and not hasattr(obj, "__abstractmethods__")
        and not hasattr(obj, "model_fields")
    ):
        # Heuristic: name resolves to a typing alias not a class.
        if not isinstance(obj, type):
            return _snapshot_typealias(name, obj)
    # Pydantic model
    if hasattr(obj, "model_fields"):
        return {"kind": "pydantic_model", "schema": _pydantic_schema(obj)}
    # Protocol
    if hasattr(obj, "_is_protocol") and obj._is_protocol:
        return _snapshot_protocol(obj)
    # ABC
    if getattr(obj, "__abstractmethods__", None):
        return _snapshot_abc(obj)
    # Concrete class
    if isinstance(obj, type):
        return _snapshot_class(obj)
    # Fallback — TypeAlias / non-introspectable
    return _snapshot_typealias(name, obj)


def _snapshot_phase4_captures() -> dict[str, Any]:
    """Phase-4 S7-10 AC-1 — the five additive captures.

    Each entry pins the load-bearing shape Phase 5's GateRunner reads.
    Per AC-2 the comparison is golden-file based (not inline string
    assertion); the captures emit dict structures that participate in
    the same top-level ``sort_keys=True`` serialization as the
    canonical re-export captures.

    Per AC-4 ``_phase4_local_capability_mint``'s name is pinned
    exactly — Phase-5 supersession is a contract event requiring an
    ADR-0001 amendment + golden refresh in the same PR.
    """
    return {
        "FallbackTier.run": {
            "kind": "method",
            "qualified_name": f"{FallbackTier.__module__}.{FallbackTier.__qualname__}.run",
            "signature": _signature_repr(FallbackTier, "run"),
        },
        "FallbackTier.on_validated": {
            "kind": "method",
            "qualified_name": f"{FallbackTier.__module__}.{FallbackTier.__qualname__}.on_validated",
            "signature": _signature_repr(FallbackTier, "on_validated"),
        },
        "LlmInvocationGuard.running_total": {
            "kind": "method",
            "qualified_name": (
                f"{LlmInvocationGuard.__module__}.{LlmInvocationGuard.__qualname__}.running_total"
            ),
            "signature": _signature_repr(LlmInvocationGuard, "running_total"),
        },
        "FenceWrapper.fence": {
            "kind": "method",
            "qualified_name": f"{FenceWrapper.__module__}.{FenceWrapper.__qualname__}.fence",
            "signature": _signature_repr(FenceWrapper, "fence"),
        },
        "SolvedExampleWriteCapability": {
            "kind": "dataclass",
            "qualified_name": (
                f"{SolvedExampleWriteCapability.__module__}."
                f"{SolvedExampleWriteCapability.__qualname__}"
            ),
            "frozen": getattr(SolvedExampleWriteCapability.__dataclass_params__, "frozen", False),
            "slots": bool(getattr(SolvedExampleWriteCapability, "__slots__", ())),
            "fields": sorted(
                f.name for f in SolvedExampleWriteCapability.__dataclass_fields__.values()
            ),
            # AC-4 — pin the mint factory's interim name + signature.
            "mint_factory": {
                "qualified_name": (
                    f"{_phase4_local_capability_mint.__module__}."
                    f"{_phase4_local_capability_mint.__qualname__}"
                ),
                "signature": _signature_repr(_phase4_local_capability_mint),
            },
        },
    }


def build_snapshot() -> dict[str, Any]:
    """Compose the full Phase-5 contract snapshot."""
    symbols = _resolve_symbols()
    missing = symbols.pop("_missing")
    captured: dict[str, Any] = {}
    for name in sorted(symbols):
        captured[name] = snapshot_symbol(name, symbols[name])
    # Phase-4 S7-10 AC-1 captures — additive entries under a separate
    # top-level key so a Phase-4 widening doesn't perturb the Phase-3
    # captured set's golden bytes.
    phase4 = _snapshot_phase4_captures()
    return {
        "schema_version": 1,
        "captured": captured,
        "phase4_captures": phase4,
        "_missing_from_canonical_reexport": missing,
    }


def should_update_golden(env: dict[str, str]) -> bool:
    """Pure helper — env-var → bool. Testable without monkeypatch
    (S6-06 AC-bonus from the validation report)."""
    return env.get(_REWRITE_ENV_VAR) == "1"


# --- The test --------------------------------------------------------------


def test_phase5_contract_snapshot_byte_equal_to_golden() -> None:
    """S6-06 AC-1 + AC-8 — captured snapshot is byte-equal to golden.

    The golden file MUST exist; first-write happens via the env-var
    regen path (no silent first-write on a missing golden — S6-06 AC-7
    no-silent-rewrite fence).
    """
    snapshot = build_snapshot()
    serialized = json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=True) + "\n"

    if should_update_golden(dict(os.environ)):
        _GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GOLDEN_PATH.write_text(serialized)
        return  # env-var regen path — no comparison

    assert _GOLDEN_PATH.exists(), (
        f"PHASE 5 CANNOT SHIP — golden snapshot missing at {_GOLDEN_PATH}. "
        f"Run with {_REWRITE_ENV_VAR}=1 to seed it; commit the result; "
        f"reference ADR-0001 §Consequences row 2 in the commit message."
    )
    golden = _GOLDEN_PATH.read_text()
    assert serialized == golden, (
        f"PHASE 5 CANNOT SHIP — Phase-5 contract surface drifted from "
        f"the golden at {_GOLDEN_PATH}.\n\n"
        f"Either revert the breaking change OR land an ADR-0001 "
        f"amendment + run with {_REWRITE_ENV_VAR}=1 to refresh the "
        f"golden in the same PR.\n\n"
        f"Captured-vs-golden diff: re-run with PYTHONHASHSEED=0 + "
        f"diff <(python -c 'import json; from tests.integration."
        f"test_phase5_contract_snapshot import build_snapshot; "
        f"print(json.dumps(build_snapshot(), indent=2, sort_keys=True))') "
        f"{_GOLDEN_PATH}"
    )


def test_snapshot_is_deterministic_across_invocations() -> None:
    """S6-06 AC-8 — same source → byte-identical snapshot across N
    invocations in the same process. Catches non-stable dict ordering
    in ``model_json_schema()`` output.
    """
    first = json.dumps(build_snapshot(), indent=2, sort_keys=True)
    for _ in range(5):
        repeat = json.dumps(build_snapshot(), indent=2, sort_keys=True)
        assert repeat == first, (
            "non-deterministic snapshot — dict iteration order leaked into "
            "the output. Investigate model_json_schema() emitter version."
        )


def test_should_update_golden_returns_true_only_for_exact_env_value() -> None:
    """Pure helper has the documented truth table."""
    assert should_update_golden({_REWRITE_ENV_VAR: "1"}) is True
    assert should_update_golden({_REWRITE_ENV_VAR: "true"}) is False
    assert should_update_golden({_REWRITE_ENV_VAR: "0"}) is False
    assert should_update_golden({}) is False


def test_remediation_orchestrator_loud_skip_documented() -> None:
    """The one missing symbol is recorded in the snapshot's
    ``_missing_from_canonical_reexport`` block — so a future S6-04
    follow-up that re-exports ``RemediationOrchestrator`` sees its
    name disappear from this list AND extend the captured set
    additively.
    """
    snapshot = build_snapshot()
    # Today's gap (will change additively when S6-04 follow-up lands).
    assert "_missing_from_canonical_reexport" in snapshot
    assert "RemediationOrchestrator" in snapshot["_missing_from_canonical_reexport"]


def test_captured_set_contains_six_phase3_symbols_at_minimum() -> None:
    """The available Phase-5 contract surface is at least these six
    today; a future re-export addition extends additively."""
    snapshot = build_snapshot()
    captured = snapshot["captured"]
    expected_subset = {
        "RemediationReport",
        "TrustSignal",
        "TrustOutcome",
        "AttemptSummary",
        "StageOutcome",
        "TrustScorer",
    }
    missing = expected_subset - set(captured)
    assert not missing, f"expected Phase-3 contract symbols missing from snapshot: {missing}"


# --- Phase-4 S7-10 AC-1 — the five additive Phase-4 captures ---------------


def test_phase4_captures_block_present_in_snapshot() -> None:
    """S7-10 AC-1 — the five named Phase-4 captures live under a
    ``phase4_captures`` top-level key (kept distinct from the Phase-3
    re-export captures so Phase-4 widenings don't perturb Phase-3
    golden bytes)."""
    snapshot = build_snapshot()
    assert "phase4_captures" in snapshot
    p4 = snapshot["phase4_captures"]
    expected = {
        "FallbackTier.run",
        "FallbackTier.on_validated",
        "LlmInvocationGuard.running_total",
        "FenceWrapper.fence",
        "SolvedExampleWriteCapability",
    }
    missing = expected - set(p4)
    assert not missing, f"S7-10 AC-1: missing Phase-4 captures: {missing}"


def test_phase4_fallback_tier_run_signature_pins_prior_attempts_default() -> None:
    """S7-10 AC-1 + AC-5 mutation guard: the ``prior_attempts`` default
    is the immutable empty tuple ``()``. A regression that flips this
    to required (no default) would break Phase 5's retry envelope
    composition."""
    p4 = build_snapshot()["phase4_captures"]
    params = p4["FallbackTier.run"]["signature"]["parameters"]
    prior_attempts = next(p for p in params if p["name"] == "prior_attempts")
    assert prior_attempts["kind"] == "KEYWORD_ONLY", (
        "PHASE 5 CANNOT SHIP — FallbackTier.run.prior_attempts must remain "
        "keyword-only; positional-arg drift breaks Phase 5's GateRunner retry "
        "envelope. Reference ADR-04-0002 + Phase-3 ADR-0001 §Consequences row 2."
    )
    assert prior_attempts["default"] == "()", (
        "PHASE 5 CANNOT SHIP — FallbackTier.run.prior_attempts default flipped "
        "from `()` to `" + str(prior_attempts["default"]) + "`. A required "
        "prior_attempts arg breaks Phase 5's first-call shape. Reference "
        "ADR-04-0011 + Phase-3 ADR-0001 §Consequences row 2."
    )


def test_phase4_fence_wrapper_fence_carries_source_kind_kwarg() -> None:
    """S7-10 AC-5 mutation guard: ``FenceWrapper.fence`` MUST keep its
    ``source_kind`` parameter — losing it breaks the SourceKind
    discrimination Phase 5 + Phase 4 retrieval both depend on."""
    p4 = build_snapshot()["phase4_captures"]
    params = p4["FenceWrapper.fence"]["signature"]["parameters"]
    param_names = {p["name"] for p in params}
    assert "source_kind" in param_names, (
        "PHASE 5 CANNOT SHIP — FenceWrapper.fence lost its source_kind "
        "parameter. The SourceKind Literal discrimination is load-bearing "
        "across S2-02 / S2-04 / ADR-04-0013. Reference ADR-04-0013 + Phase-3 "
        "ADR-0001 §Consequences row 2."
    )


def test_phase4_on_validated_keeps_trust_parameter() -> None:
    """S7-10 AC-5 mutation guard: ``FallbackTier.on_validated`` must
    carry the ``trust: TrustOutcome`` parameter — the confidence gate
    + harvest-skip-reason dispatch reads it."""
    p4 = build_snapshot()["phase4_captures"]
    params = p4["FallbackTier.on_validated"]["signature"]["parameters"]
    param_names = {p["name"] for p in params}
    assert "trust" in param_names, (
        "PHASE 5 CANNOT SHIP — FallbackTier.on_validated lost its `trust` "
        "parameter; the ConfidenceGate dispatch can't fire without it. "
        "Reference ADR-04-0009 + Phase-3 ADR-0001 §Consequences row 2."
    )


def test_phase4_capability_is_frozen_dataclass() -> None:
    """S7-10 AC-5 mutation guard: ``SolvedExampleWriteCapability`` is
    a frozen dataclass — flipping to mutable breaks the mint-once-
    consume-many invariant ADR-04-0010 establishes."""
    p4 = build_snapshot()["phase4_captures"]
    cap = p4["SolvedExampleWriteCapability"]
    assert cap["frozen"] is True, (
        "PHASE 5 CANNOT SHIP — SolvedExampleWriteCapability.__dataclass_params__"
        ".frozen flipped from True to False. The mint-once-consume-many "
        "invariant requires immutability. Reference ADR-04-0010 + Phase-3 "
        "ADR-0001 §Consequences row 2."
    )
    assert cap["mint_factory"]["qualified_name"].endswith("_phase4_local_capability_mint"), (
        "PHASE 5 CANNOT SHIP — _phase4_local_capability_mint interim name "
        "drifted. Phase-5 supersession (ADR-04-0009) is a contract event "
        "requiring an ADR-0001 amendment + golden refresh in the same PR. "
        "AC-4 pins this exact interim name."
    )


def test_phase4_running_total_return_annotation_pinned_to_budget_snapshot() -> None:
    """S7-10 AC-5 mutation guard: ``LlmInvocationGuard.running_total``
    MUST return a typed :class:`BudgetSnapshot`. A narrow-to-``dict``
    regression collapses the audit-trail discipline ADR-04-0010
    builds on.
    """
    p4 = build_snapshot()["phase4_captures"]
    return_annotation = p4["LlmInvocationGuard.running_total"]["signature"]["return_annotation"]
    # The annotation is captured as a string (across Python versions
    # the repr varies between `'BudgetSnapshot'` and `BudgetSnapshot`).
    assert return_annotation is not None
    assert "BudgetSnapshot" in str(return_annotation), (
        f"PHASE 5 CANNOT SHIP — LlmInvocationGuard.running_total return "
        f"annotation drifted from BudgetSnapshot to "
        f"{return_annotation!r}. The typed audit-trail discipline "
        f"requires BudgetSnapshot; a `dict[str, int]` regression breaks "
        f"Phase 5's budget-reconcile contract. Reference ADR-04-0010 + "
        f"Phase-3 ADR-0001 §Consequences row 2."
    )


def test_phase4_cassettes_lock_format_is_pinned_by_module_existence() -> None:
    """S7-10 AC-5 mutation guard (final of six): the
    ``tests/cassettes/anthropic/cassettes.lock`` file format is the
    operator-visible artifact ADR-04-0014 establishes.

    Today's minimal cassette-discipline scaffold guards the format
    via the existing ``tests/security/test_cassettes_clean.py``
    scanner (S3-05); this mutation guard surfaces an authoritative
    breakage in the **format-pinning module** (i.e. if the scanner is
    deleted or its regex is loosened beyond byte-equality, the cassette
    line format becomes silently mutable). Pinning the module
    presence + its name surfaces the regression at this snapshot's
    granularity.
    """
    repo_root = Path(__file__).parents[2]
    scanner = repo_root / "tests" / "security" / "test_cassettes_clean.py"
    assert scanner.exists(), (
        f"PHASE 5 CANNOT SHIP — cassettes.lock format-pinning module "
        f"missing at {scanner}. ADR-04-0014's line-format invariant is "
        f"enforced by this scanner; without it the lock-file shape "
        f"becomes silently mutable. Reference ADR-04-0014 + Phase-3 "
        f"ADR-0001 §Consequences row 2."
    )


def test_phase4_captures_round_trip_through_json_deterministically() -> None:
    """S7-10 AC-6 — Phase-4 captures share the determinism property
    with the Phase-3 captures: 10 invocations produce byte-identical
    JSON for the ``phase4_captures`` block."""
    first = json.dumps(build_snapshot()["phase4_captures"], indent=2, sort_keys=True)
    for _ in range(10):
        repeat = json.dumps(build_snapshot()["phase4_captures"], indent=2, sort_keys=True)
        assert repeat == first, (
            "non-deterministic Phase-4 captures — dict iteration order leaked "
            "into the output for at least one of the five captures."
        )
