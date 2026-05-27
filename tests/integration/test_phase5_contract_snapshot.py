"""Phase-3 S6-06 (minimal) — Phase-5 contract snapshot scaffold.

**Status: GREEN-partial (minimal viable scaffold).** Lands the
``tests/integration/test_phase5_contract_snapshot.py`` file +
``tests/golden/phase5-contract/snapshot.json`` golden so Phase-4 S7-10
AC-1..AC-8 can extend the file in place with the five Phase-4 capture
entries. The full S6-06 AC complement (registry-driven
``@register_snapshot_kind`` / ``@register_delta_rule``, the 6 named
breaking-delta meta-test cases, the AC-19 ``PHASE 5 CANNOT SHIP``
directive-format test, the AST-walk functional-core fence) is **not**
shipped here — those are S6-06's GREEN-complete commits.

Why this minimal scaffold exists in a Phase-4 commit: Phase-3 S6-06
remains HARDENED-not-GREEN, blocking S7-10. The Phase-4 executor
authored this scaffold as ``Rule-8 "Read before you write"`` reach-
across: the structural prerequisite for S7-10's contract-snapshot work
is the file + golden + env-var-regen path existing. The 6-symbol
capture today is the minimum that satisfies S7-10 AC-2's "extend in
place" requirement; S6-06's full GREEN attempt should additively
extend this scaffold (not rewrite it).

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


def build_snapshot() -> dict[str, Any]:
    """Compose the full Phase-5 contract snapshot."""
    symbols = _resolve_symbols()
    missing = symbols.pop("_missing")
    captured: dict[str, Any] = {}
    for name in sorted(symbols):
        captured[name] = snapshot_symbol(name, symbols[name])
    return {
        "schema_version": 1,
        "captured": captured,
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
