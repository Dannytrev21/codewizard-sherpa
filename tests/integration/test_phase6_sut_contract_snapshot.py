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

import codegenie.workflows as workflows_pkg
from codegenie.workflows import (
    VulnRemediationCase,
    VulnRemediationResult,
    VulnRemediationSut,
)

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


def build_snapshot() -> dict[str, Any]:
    """Construct the canonical snapshot dict."""
    return {
        "all": sorted(workflows_pkg.__all__),
        "is_runtime_protocol": bool(getattr(VulnRemediationSut, "_is_runtime_protocol", False)),
        "case_schema": VulnRemediationCase.model_json_schema(by_alias=True),
        "result_schema": VulnRemediationResult.model_json_schema(by_alias=True),
        "protocol": _serialize_protocol_signature(),
    }


def _directive() -> str:
    return (
        "Phase-6 SUT contract drift. If additive (new optional field with "
        "default / new sub-model class added without removing or renaming an "
        "existing field), regenerate the golden under "
        f"`{_REWRITE_FLAG}=1 pytest "
        "tests/integration/test_phase6_sut_contract_snapshot.py` and amend "
        "ADR-0001 §Consequences. If breaking (rename, removal, "
        "required-without-default, runtime_checkable removal, Literal "
        "narrowing), this is an ADR-0001 amendment + downstream Phase-6.5 / "
        "Phase-9 review per ADR-0001 §Consequences."
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

    for schema_key in ("case_schema", "result_schema"):
        old_schema = old.get(schema_key, {})
        new_schema = new.get(schema_key, {})
        if _schema_diff_is_breaking(old_schema, new_schema):
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
