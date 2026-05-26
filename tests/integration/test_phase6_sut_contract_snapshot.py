"""Phase 6 S1-01 AC-9 — byte-equal contract snapshot for the SUT public surface.

The snapshot covers:

1. ``VulnRemediationCase.model_json_schema(by_alias=True)``.
2. ``VulnRemediationResult.model_json_schema(by_alias=True)``.
3. A structural snapshot of the ``VulnRemediationSut`` Protocol — for each
   declared method, the ``inspect.signature`` representation plus parameter
   and return annotations as strings.
4. The four-name ``__all__`` allowlist.

Failure modes:

* **Byte diff** — fails the test with a directive that calls out additive vs.
  breaking handling. Set ``PHASE6_CONTRACT_GOLDEN_REWRITE=1`` to regenerate.
* **Additive change** (new optional field with default / new sub-model class)
  — regenerate + amend ADR-0001 §Consequences.
* **Breaking change** (rename, removal, required-without-default,
  ``runtime_checkable`` removal, Literal narrowing) — full ADR-0001
  amendment + downstream Phase-6.5 / Phase-9 review.

The companion meta-test in ``test_phase6_sut_contract_snapshot_meta.py``
exercises the additive/breaking classifier on synthetic snapshots so a
``==``→``!=`` mutation in the classifier dies on CI, not in Phase 6.5.
"""

from __future__ import annotations

import inspect
import json
import os
import typing
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

import codegenie.workflows as workflows_pkg
from codegenie.workflows import (
    TransitionEvent,
    VulnLedgerState,
    VulnRemediationCase,
    VulnRemediationResult,
    VulnRemediationSut,
)
from codegenie.workflows.checkpoints import (
    _MAX_EVENT_BYTES,
    _SEMANTIC_BOUNDARY_KINDS,
    CheckpointStore,
)
from codegenie.workflows.replay import (
    _INTEGRITY_ERROR_ID,
    ChainMismatch,
    EmptyWorkflow,
    Hydrated,
    HydrationResult,
    ReplayVerdict,
    ReplayVerifier,
    TornWrite,
    Verified,
    hydrate_or_fail,
)
from codegenie.workflows.sqlite_checkpoints import _CHECKPOINT_SCHEMA_SQL
from codegenie.workflows.vuln_ledger import _LEGAL_TRANSITIONS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_PATH = _REPO_ROOT / "tests" / "golden" / "phase6-contract" / "snapshot.json"

_REWRITE_FLAG = "PHASE6_CONTRACT_GOLDEN_REWRITE"


def _serialize_protocol_signature() -> dict[str, Any]:
    """Build a deterministic structural snapshot for VulnRemediationSut."""
    methods: dict[str, Any] = {}
    for name in sorted(("run_case", "digest")):
        attr = getattr(VulnRemediationSut, name)
        sig = inspect.signature(attr)
        # Resolve forward references the test owns directly.
        type_hints = typing.get_type_hints(attr)
        methods[name] = {
            "signature": str(sig),
            "is_coroutine_function": inspect.iscoroutinefunction(attr),
            "annotations": {
                k: v.__name__ if hasattr(v, "__name__") else str(v) for k, v in type_hints.items()
            },
        }
    return methods


def _serialize_checkpoint_store_signature() -> dict[str, Any]:
    """Phase 6 S2-01 AC-15 — structural snapshot for the CheckpointStore Protocol."""
    methods: dict[str, Any] = {}
    for name in sorted(("append", "read_all_for_workflow", "tail_chain_head", "lock", "close")):
        attr = getattr(CheckpointStore, name)
        sig = inspect.signature(attr)
        methods[name] = {
            "signature": str(sig),
            "is_coroutine_function": inspect.iscoroutinefunction(attr),
        }
    return methods


def _serialize_replay_verifier_signature() -> dict[str, Any]:
    """Phase 6 S2-02 AC-14 — structural snapshot for the verifier API."""
    methods: dict[str, Any] = {}
    for name in sorted(("__init__", "verify")):
        attr = getattr(ReplayVerifier, name)
        sig = inspect.signature(attr)
        methods[name] = {
            "signature": str(sig),
            "is_coroutine_function": inspect.iscoroutinefunction(attr),
        }
    return methods


def _serialize_module_function_signatures() -> dict[str, Any]:
    """Phase 6 S2-02 AC-14 — top-level functions in the verifier module."""
    out: dict[str, Any] = {}
    for fn in (hydrate_or_fail,):
        out[fn.__name__] = {
            "signature": str(inspect.signature(fn)),
            "is_coroutine_function": inspect.iscoroutinefunction(fn),
        }
    return out


def build_snapshot() -> dict[str, Any]:
    """Construct the canonical snapshot dict.

    AC-15 extension: includes the Phase-6 S1-02 ledger contract — the
    discriminated-union schema, the ``TransitionEvent`` schema, and the
    sorted structural snapshot of ``_LEGAL_TRANSITIONS``. The
    additive-vs-breaking classifier inherits S1-01's logic; the meta-test
    exercises it on ledger-shaped deltas (new transition edge = additive;
    removed variant or rename = breaking).

    Phase-6 S2-02 AC-14 extension: includes the four-variant
    :data:`ReplayVerdict` schema, the :data:`HydrationResult` schema, the
    :class:`ReplayVerifier` method signatures, the :func:`hydrate_or_fail`
    function signature, and the ``_INTEGRITY_ERROR_ID`` constant value.
    """
    ledger_adapter = TypeAdapter(VulnLedgerState)
    verdict_adapter = TypeAdapter(ReplayVerdict)
    hydration_adapter = TypeAdapter(HydrationResult)
    return {
        "all": sorted(workflows_pkg.__all__),
        "is_runtime_protocol": bool(getattr(VulnRemediationSut, "_is_runtime_protocol", False)),
        "case_schema": VulnRemediationCase.model_json_schema(by_alias=True),
        "result_schema": VulnRemediationResult.model_json_schema(by_alias=True),
        "protocol": _serialize_protocol_signature(),
        "ledger_state_schema": ledger_adapter.json_schema(by_alias=True),
        "transition_event_schema": TransitionEvent.model_json_schema(by_alias=True),
        "legal_transitions": sorted(f"{p}->{n}" for p, n in _LEGAL_TRANSITIONS),
        # Phase-6 S2-01 AC-15 — checkpoint substrate contract.
        "checkpoint_store_protocol": _serialize_checkpoint_store_signature(),
        "checkpoint_store_is_runtime_protocol": bool(
            getattr(CheckpointStore, "_is_runtime_protocol", False)
        ),
        "semantic_boundary_kinds": sorted(_SEMANTIC_BOUNDARY_KINDS),
        "max_event_bytes": _MAX_EVENT_BYTES,
        "checkpoint_sqlite_schema": _CHECKPOINT_SCHEMA_SQL,
        # Phase-6 S2-02 AC-14 — replay-verifier contract.
        "replay_verdict_schema": verdict_adapter.json_schema(by_alias=True),
        "hydration_result_schema": hydration_adapter.json_schema(by_alias=True),
        "replay_verifier_methods": _serialize_replay_verifier_signature(),
        "replay_module_functions": _serialize_module_function_signatures(),
        "replay_verdict_kinds": sorted(
            v.model_fields["kind"].default
            for v in (Verified, ChainMismatch, TornWrite, EmptyWorkflow)
        ),
        "hydration_result_kinds": sorted(
            [Hydrated.model_fields["kind"].default, "failed_unrecoverable"]
        ),
        "integrity_error_id": str(_INTEGRITY_ERROR_ID),
    }


def _directive() -> str:
    return (
        "Phase-6 contract drift (SUT or ledger). If additive (new optional field "
        "with default / new sub-model class / new transition edge added without "
        "removing or renaming an existing field/variant/edge), regenerate the "
        f"golden under `{_REWRITE_FLAG}=1 pytest "
        "tests/integration/test_phase6_sut_contract_snapshot.py` and amend "
        "ADR-0001 / ADR-0003 §Consequences (also verify the terminal partition "
        "still matches S1-01's TerminalState — AC-6). If breaking (rename, "
        "removal, required-without-default, runtime_checkable removal, Literal "
        "narrowing, removed variant, removed edge), this is an ADR-0001 + "
        "ADR-0003 amendment + downstream Phase-6.5 / Phase-9 review per "
        "ADR-0001 §Consequences."
    )


def test_ac9_contract_snapshot_byte_equal() -> None:
    actual = build_snapshot()
    if os.environ.get(_REWRITE_FLAG) == "1":
        _GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GOLDEN_PATH.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
        return
    assert _GOLDEN_PATH.exists(), _directive()
    expected = json.loads(_GOLDEN_PATH.read_text())
    assert actual == expected, _directive()


# ---------------------------------------------------------------------------
# Additive-vs-breaking classifier (shared with the meta-test).
# ---------------------------------------------------------------------------


def classify_snapshot_diff(old: dict[str, Any], new: dict[str, Any]) -> str:
    """Return one of {'noop', 'additive', 'breaking'} for the given diff.

    Rules (mutation-resistant — the meta-test pins every branch):

    * ``runtime_checkable`` flipped from ``True`` to ``False`` → breaking.
    * Any name in ``old["all"]`` missing from ``new["all"]`` → breaking
      (removal).
    * Any method in ``old["protocol"]`` missing from ``new["protocol"]`` →
      breaking.
    * Any method signature changed → breaking.
    * Any field present in an old schema's ``required`` missing from the new
      schema (or removed entirely) → breaking.
    * Any new field added to ``required`` that was not previously required
      → breaking (required-without-default).
    * Any ``enum`` (Literal) membership narrowed (old member removed) →
      breaking.
    * **AC-15 S1-02 extension** — any edge in ``old["legal_transitions"]``
      missing from ``new["legal_transitions"]`` → breaking (removed legal
      edge); a new edge → additive.
    * **AC-15 S1-02 extension** — the same schema-diff rules apply to
      ``ledger_state_schema`` and ``transition_event_schema``.
    * Anything else with a non-empty diff → additive.
    * No diff → noop.
    """
    if old == new:
        return "noop"

    if old.get("is_runtime_protocol") and not new.get("is_runtime_protocol"):
        return "breaking"

    removed_names = set(old.get("all", [])) - set(new.get("all", []))
    if removed_names:
        return "breaking"

    old_methods = old.get("protocol", {})
    new_methods = new.get("protocol", {})
    if set(old_methods) - set(new_methods):
        return "breaking"
    for name, old_meta in old_methods.items():
        if name not in new_methods:
            return "breaking"
        if old_meta.get("signature") != new_methods[name].get("signature"):
            return "breaking"

    for schema_key in (
        "case_schema",
        "result_schema",
        "ledger_state_schema",
        "transition_event_schema",
    ):
        old_schema = old.get(schema_key, {})
        new_schema = new.get(schema_key, {})
        if _schema_diff_is_breaking(old_schema, new_schema):
            return "breaking"

    old_edges = set(old.get("legal_transitions", []) or [])
    new_edges = set(new.get("legal_transitions", []) or [])
    if old_edges - new_edges:
        return "breaking"

    # Phase-6 S2-01 AC-15 — checkpoint-substrate diff rules.
    if old.get("checkpoint_store_is_runtime_protocol") and not new.get(
        "checkpoint_store_is_runtime_protocol"
    ):
        return "breaking"
    old_cp = old.get("checkpoint_store_protocol", {}) or {}
    new_cp = new.get("checkpoint_store_protocol", {}) or {}
    if set(old_cp) - set(new_cp):
        return "breaking"
    for name, meta in old_cp.items():
        if name not in new_cp:
            return "breaking"
        if meta.get("signature") != new_cp[name].get("signature"):
            return "breaking"
    old_boundaries = set(old.get("semantic_boundary_kinds", []) or [])
    new_boundaries = set(new.get("semantic_boundary_kinds", []) or [])
    if old_boundaries - new_boundaries:
        return "breaking"
    # Narrowing _MAX_EVENT_BYTES downward is breaking (existing valid
    # payloads suddenly reject). Raising is additive.
    old_cap = old.get("max_event_bytes")
    new_cap = new.get("max_event_bytes")
    if isinstance(old_cap, int) and isinstance(new_cap, int) and new_cap < old_cap:
        return "breaking"
    # Schema string change is breaking (column rename, index removal,
    # type change). An additive column would require a new row in the
    # ledger AND the golden file; the executor takes that explicit step.
    if (
        old.get("checkpoint_sqlite_schema") is not None
        and new.get("checkpoint_sqlite_schema") is not None
        and old["checkpoint_sqlite_schema"] != new["checkpoint_sqlite_schema"]
    ):
        return "breaking"

    # Phase-6 S2-02 AC-14 — replay-verifier contract diffs.
    # Removed verdict kind → breaking; added → additive.
    old_verdicts = set(old.get("replay_verdict_kinds", []) or [])
    new_verdicts = set(new.get("replay_verdict_kinds", []) or [])
    if old_verdicts - new_verdicts:
        return "breaking"
    old_hydration = set(old.get("hydration_result_kinds", []) or [])
    new_hydration = set(new.get("hydration_result_kinds", []) or [])
    if old_hydration - new_hydration:
        return "breaking"
    # Verifier method removal / signature change → breaking.
    old_methods = old.get("replay_verifier_methods", {}) or {}
    new_methods = new.get("replay_verifier_methods", {}) or {}
    if set(old_methods) - set(new_methods):
        return "breaking"
    for name, meta in old_methods.items():
        if name not in new_methods or meta.get("signature") != new_methods[name].get("signature"):
            return "breaking"
    # Module-level function removal / signature change → breaking.
    old_fns = old.get("replay_module_functions", {}) or {}
    new_fns = new.get("replay_module_functions", {}) or {}
    if set(old_fns) - set(new_fns):
        return "breaking"
    for name, meta in old_fns.items():
        if name not in new_fns or meta.get("signature") != new_fns[name].get("signature"):
            return "breaking"
    # Verdict / hydration schema breaking-diff rules.
    for schema_key in ("replay_verdict_schema", "hydration_result_schema"):
        if _schema_diff_is_breaking(old.get(schema_key, {}), new.get(schema_key, {})):
            return "breaking"
    # error_id slug change → breaking (downstream consumers may dispatch).
    if (
        old.get("integrity_error_id") is not None
        and new.get("integrity_error_id") is not None
        and old["integrity_error_id"] != new["integrity_error_id"]
    ):
        return "breaking"

    return "additive"


def _required(schema: dict[str, Any]) -> set[str]:
    return set(schema.get("required", []) or [])


def _properties(schema: dict[str, Any]) -> dict[str, Any]:
    return schema.get("properties", {}) or {}


def _schema_diff_is_breaking(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """Return True iff the schema diff is breaking under the AC-9 rules."""
    old_req, new_req = _required(old), _required(new)
    # Old required field removed entirely → breaking.
    if old_req - new_req - set(_properties(new)):
        return True
    # New required field that wasn't previously declared at all → breaking.
    new_required_unseen = new_req - old_req
    if new_required_unseen and not new_required_unseen.issubset(_properties(old)):
        return True
    # Field removed from properties → breaking.
    removed_props = set(_properties(old)) - set(_properties(new))
    if removed_props:
        return True
    # Literal/enum narrowing → breaking.
    for name, old_prop in _properties(old).items():
        new_prop = _properties(new).get(name, {})
        if not new_prop:
            continue
        old_enum = old_prop.get("enum")
        new_enum = new_prop.get("enum")
        if (
            isinstance(old_enum, list)
            and isinstance(new_enum, list)
            and set(old_enum) - set(new_enum)
        ):
            return True
    # Walk $defs for the same enum-narrowing rule.
    for def_name, old_def in (old.get("$defs", {}) or {}).items():
        new_def = (new.get("$defs", {}) or {}).get(def_name, {})
        if _schema_diff_is_breaking(old_def, new_def):
            return True
    return False
