"""Frozen probe-contract pinning test (S2-02, ADR-0007).

This module pins both halves of the probe-contract freeze in CI:

* ``doc_fingerprint``      — re-runs the regen script's extractor + hasher
  against the live ``localv2.md`` and compares to the committed snapshot.
* ``structural_signature`` — rebuilds the signature from
  :mod:`codegenie.probes.base` and compares to the committed snapshot.

Either drift fails CI with a message routing the contributor to
``templates/adr-amendment.md`` and ADR-0007. The anchoring tests on their
own are *not* sufficient to lock intent — a regen helper that returned ``""``
or ``{}`` would satisfy them. The fixture-driven extractor / normalizer /
mutation-killer ters in tiers 2–4 are what anchor intent (Rule 9 — tests
verify intent, not just behavior).
"""

from __future__ import annotations

import ast
import hashlib
import json
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import codegenie.probes.base as base
from scripts.regen_probe_contract_snapshot import (
    extract_section_4_body,
    normalize_and_hash,
    structural_signature,
)

# --- Anchors ----------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "probe_contract.v1.json"
LOCALV2_PATH = REPO_ROOT / "docs" / "localv2.md"
BASE_PY_PATH = REPO_ROOT / "src" / "codegenie" / "probes" / "base.py"

FINGERPRINT_DRIFT_MESSAGE = (
    "localv2.md §4 has drifted from the frozen contract. "
    "Resolution is ALWAYS 'change code to match doc, never the inverse'. "
    "See templates/adr-amendment.md and ADR-0007."
)
STRUCTURAL_DRIFT_MESSAGE = (
    "src/codegenie/probes/base.py has drifted from localv2.md §4. "
    "See templates/adr-amendment.md and ADR-0007."
)
ALLOWED_BASE_PY_IMPORTS = {"abc", "collections", "dataclasses", "logging", "pathlib", "typing"}


def _load_snapshot() -> dict[str, Any]:
    if not SNAPSHOT_PATH.exists():
        pytest.fail(
            f"{SNAPSHOT_PATH} is missing. Regenerate with "
            f"`python scripts/regen_probe_contract_snapshot.py`."
        )
    try:
        snap: dict[str, Any] = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"{SNAPSHOT_PATH} is corrupt ({exc}). Regenerate with "
            f"`python scripts/regen_probe_contract_snapshot.py`."
        )
    assert set(snap.keys()) == {
        "snapshot_schema_version",
        "doc_fingerprint",
        "structural_signature",
    }, f"snapshot has unexpected top-level keys: {set(snap.keys())}"
    assert snap["snapshot_schema_version"] == 1, snap["snapshot_schema_version"]
    return snap


def _synthetic_module(
    field_name: str = "x",
    field_type: type = int,
    default: Any | None = None,
) -> types.ModuleType:
    """Build a tiny synthetic module containing a controllable dataclass.

    Reused across mutation-killer tests (Tier 4) so each test exercises one
    independent dimension of the signature (field name, type, default).
    Constructed via ``types.ModuleType`` so it has no source file — the
    regen script's source-walk falls back to including all classes in
    ``vars(module)``.
    """
    m = types.ModuleType("synthetic")
    ns: dict[str, Any] = {"__annotations__": {field_name: field_type}}
    if default is not None:
        ns[field_name] = default
    inner = dataclass(type("Inner", (), ns))
    m.Inner = inner  # type: ignore[attr-defined]
    return m


# --- Tier 1 — anchoring tests (pin the committed snapshot) ------------------


def test_probe_contract_doc_fingerprint_matches_snapshot() -> None:
    snap = _load_snapshot()
    body = extract_section_4_body(LOCALV2_PATH.read_text(encoding="utf-8"))
    current = normalize_and_hash(body)
    assert current == snap["doc_fingerprint"], FINGERPRINT_DRIFT_MESSAGE


def test_probe_class_structural_signature_matches_snapshot() -> None:
    snap = _load_snapshot()
    current = structural_signature(base)
    assert current == snap["structural_signature"], STRUCTURAL_DRIFT_MESSAGE


# --- Tier 2 — extractor tests against hand-authored fixtures ----------------


def test_extract_section_4_body_extracts_only_section_4_from_fixture() -> None:
    md = "## 3. Prelude\nbefore\n\n## 4. The probe contract\nBODY-OF-4\n\n## 5. After\nafter\n"
    body = extract_section_4_body(md)
    assert body.strip() == "BODY-OF-4", body


def test_extract_section_4_body_handles_section_4_as_final_section() -> None:
    md = "## 3. earlier\nprev\n\n## 4. The probe contract\nFINAL-BODY\n"
    body = extract_section_4_body(md)
    assert "FINAL-BODY" in body and "## " not in body


def test_extract_section_4_body_raises_on_missing_section_4() -> None:
    with pytest.raises(ValueError, match=r"## 4\. The probe contract"):
        extract_section_4_body("## 1. only\nnothing here\n")


def test_extract_section_4_body_raises_on_multiple_section_4_anchors() -> None:
    md = "## 4. The probe contract\nfirst\n\n## 4. The probe contract\nsecond\n"
    with pytest.raises(ValueError, match=r"multiple|>1|duplicate"):
        extract_section_4_body(md)


def test_extract_section_4_body_does_not_terminate_on_subheadings() -> None:
    md = "## 4. The probe contract\nbody-line\n\n### 4.1 nested\nsubbody\n\n## 5. after\nafter\n"
    body = extract_section_4_body(md)
    assert "subbody" in body and "after" not in body


# --- Tier 3 — normalizer tests (algorithm pinned) ---------------------------


@pytest.mark.parametrize(
    "body",
    [
        "a   b\tc\nd",
        "a   b\tc\r\nd",
        "  a   b   ",
        "a\n\n\n\nb",
    ],
)
def test_normalize_and_hash_collapses_whitespace_and_is_idempotent(body: str) -> None:
    h1 = normalize_and_hash(body)
    h2 = normalize_and_hash(" " + body + " \n")
    h3 = normalize_and_hash(body.replace("\n", "\r\n"))
    assert h1 == h2 == h3


def test_normalize_and_hash_is_utf8_sha256_of_collapsed_body() -> None:
    body = "  foo\t bar  "
    expected = hashlib.sha256(b"foo bar").hexdigest()
    assert normalize_and_hash(body) == expected


def test_normalize_and_hash_is_deterministic_across_invocations() -> None:
    md = LOCALV2_PATH.read_text(encoding="utf-8")
    assert normalize_and_hash(extract_section_4_body(md)) == normalize_and_hash(
        extract_section_4_body(md)
    )


# --- Tier 4 — structural-signature mutation killers -------------------------


def test_structural_signature_of_synthetic_module_includes_field_name_type_and_default() -> None:
    sig = structural_signature(_synthetic_module(field_name="x", field_type=int, default=7))
    assert sig["Inner"]["fields"][0]["name"] == "x"
    assert "int" in sig["Inner"]["fields"][0]["type"]
    assert sig["Inner"]["fields"][0]["default"] == "7"


def test_structural_signature_changes_when_field_name_changes() -> None:
    a = structural_signature(_synthetic_module(field_name="x"))
    b = structural_signature(_synthetic_module(field_name="y"))
    assert a != b


def test_structural_signature_changes_when_field_type_changes() -> None:
    a = structural_signature(_synthetic_module(field_type=int))
    b = structural_signature(_synthetic_module(field_type=str))
    assert a != b


def test_structural_signature_changes_when_default_changes() -> None:
    a = structural_signature(_synthetic_module(default=1))
    b = structural_signature(_synthetic_module(default=2))
    assert a != b


def test_structural_signature_is_deterministic_across_invocations() -> None:
    assert structural_signature(base) == structural_signature(base)


def test_structural_signature_captures_required_probe_class_attributes() -> None:
    sig = structural_signature(base)
    attrs = {a["name"] for a in sig["Probe"]["class_attributes"]}
    required = {
        "name",
        "layer",
        "tier",
        "applies_to_tasks",
        "applies_to_languages",
        "requires",
        "declared_inputs",
        "timeout_seconds",
        "cache_strategy",
    }
    assert required <= attrs, attrs


def test_structural_signature_captures_required_probe_methods() -> None:
    sig = structural_signature(base)
    methods = set(sig["Probe"]["methods"])
    assert {"applies", "cache_key", "run"} <= methods, methods


def test_probe_class_has_no_version_attribute() -> None:
    # Phase 0 explicitly excludes `version` per `phase-arch-design.md §Open
    # questions Q2` — pin against the misleading hint in earlier docs.
    sig = structural_signature(base)
    names = {a["name"] for a in sig["Probe"]["class_attributes"]}
    assert "version" not in names


def test_structural_signature_preserves_probe_class_attribute_order() -> None:
    # Insertion order is part of the contract: the snapshot is sensitive to
    # field-list reordering. AC-3 requires Python 3.11+ insertion order.
    sig = structural_signature(base)
    names = [a["name"] for a in sig["Probe"]["class_attributes"]]
    assert names == [
        "name",
        "layer",
        "tier",
        "applies_to_tasks",
        "applies_to_languages",
        "requires",
        "declared_inputs",
        "timeout_seconds",
        "cache_strategy",
    ], names


def test_structural_signature_captures_required_dataclasses() -> None:
    # The four dataclasses required by §4 must all be present, in
    # alphabetical key order (AC-3 specifies sorted key order).
    sig = structural_signature(base)
    assert list(sig.keys()) == [
        "InputFingerprint",
        "Probe",
        "ProbeContext",
        "ProbeOutput",
        "RepoSnapshot",
        "Task",
    ], list(sig.keys())


# --- Tier 5 — failure-message contract is exercised -------------------------


def test_doc_fingerprint_failure_message_routes_to_amendment_template() -> None:
    tampered = LOCALV2_PATH.read_text(encoding="utf-8").replace(
        "class Probe(ABC):",
        "class Probe(ABCMeta):",
        1,
    )
    snap = _load_snapshot()
    tampered_hash = normalize_and_hash(extract_section_4_body(tampered))
    assert tampered_hash != snap["doc_fingerprint"], (
        "synthetic tamper failed to alter the doc fingerprint — the test "
        "would no longer guarantee the failure-message contract is exercised."
    )
    with pytest.raises(AssertionError, match=r"templates/adr-amendment\.md"):
        assert tampered_hash == snap["doc_fingerprint"], FINGERPRINT_DRIFT_MESSAGE


def test_structural_signature_failure_message_routes_to_amendment_template() -> None:
    snap = _load_snapshot()
    drifted = structural_signature(_synthetic_module())
    assert drifted != snap["structural_signature"], (
        "synthetic module signature unexpectedly matches the snapshot — "
        "mutation-killer test cannot exercise the failure-message contract."
    )
    with pytest.raises(AssertionError, match=r"templates/adr-amendment\.md"):
        assert drifted == snap["structural_signature"], STRUCTURAL_DRIFT_MESSAGE


# --- Tier 6 — base.py is stdlib-only (AC-7) ---------------------------------


def test_base_py_imports_are_stdlib_only() -> None:
    tree = ast.parse(BASE_PY_PATH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_roots.add(node.module.split(".")[0])
    extras = imported_roots - ALLOWED_BASE_PY_IMPORTS
    assert not extras, (
        f"src/codegenie/probes/base.py imports outside the allowed stdlib set: "
        f"{extras}. The frozen probe contract surface must remain stdlib-only "
        "(ADR-0007 + ADR-0010)."
    )


def test_base_py_carries_codeowners_todo_for_s5_02() -> None:
    # AC-9: a grep-able TODO so the CODEOWNERS linkage to S5-02 is auditable.
    source = BASE_PY_PATH.read_text(encoding="utf-8")
    assert "TODO(S5-02): CODEOWNERS entry required" in source, (
        "src/codegenie/probes/base.py must carry the S5-02 CODEOWNERS TODO "
        "per S2-02 AC-9; Phase 0 exit is conditional on the linkage."
    )


# --- Tier 7 — ADR-0002 sentinel + Phase-1 mutation killers (S1-06) ---------

_ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS: tuple[str, ...] = (
    "cache_dir",
    "output_dir",
    "workspace",
    "logger",
    "config",
    "parsed_manifest",
    "input_snapshot",
)
_ADR_0002_PATH = (
    REPO_ROOT
    / "docs"
    / "phases"
    / "01-context-gather-layer-a-node"
    / "ADRs"
    / "0002-parsed-manifest-memo-on-probe-context.md"
)


def test_probe_context_field_list_matches_adr_0002_amendment() -> None:
    # AC-5: explicit ADR-0002 sentinel. A third future field fails CI here
    # with a self-documenting message that names the ADR.
    import dataclasses

    actual = tuple(f.name for f in dataclasses.fields(base.ProbeContext))
    assert actual == _ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS, (
        f"ProbeContext field list {actual} does not match ADR-0002. "
        f"Adding fields to ProbeContext is gated by ADR-0002 amendment. "
        f"See docs/phases/01-context-gather-layer-a-node/ADRs/"
        f"0002-parsed-manifest-memo-on-probe-context.md."
    )


def test_probe_context_new_field_annotations_pinned() -> None:
    # AC-4: catches `set` ↔ `frozenset` swap and `Mapping` → `dict` swap
    # independently of the structural-signature snapshot.
    import inspect as _inspect

    ann = _inspect.get_annotations(base.ProbeContext)
    assert "Callable" in repr(ann["parsed_manifest"])
    assert "Mapping" in repr(ann["parsed_manifest"])
    assert "frozenset" in repr(ann["input_snapshot"])
    assert "InputFingerprint" in repr(ann["input_snapshot"])


def test_probe_context_phase0_construction_keeps_working(tmp_path: Path) -> None:
    # AC-7: a mutation that removed the `= None` default on either new field
    # breaks this test; the Phase 0 construction sites all use kwargs.
    import logging

    ctx = base.ProbeContext(
        cache_dir=tmp_path / "c",
        output_dir=tmp_path / "o",
        workspace=tmp_path / "w",
        logger=logging.getLogger("test"),
        config={},
    )
    assert ctx.parsed_manifest is None
    assert ctx.input_snapshot is None


def test_input_fingerprint_is_tuple_subclass() -> None:
    fp = base.InputFingerprint(path="/r/package.json", mtime_ns=1, size=100, content_hash="abc")
    assert isinstance(fp, tuple)  # NamedTuple inherits tuple


def test_input_fingerprint_is_hashable_and_frozenset_member() -> None:
    fp = base.InputFingerprint(path="/x", mtime_ns=0, size=0, content_hash="0")
    hash(fp)  # raises if not hashable
    assert {fp} == {fp}
    assert frozenset({fp, fp}) == frozenset({fp})


def test_input_fingerprint_equality_is_value_based() -> None:
    a = base.InputFingerprint(path="/x", mtime_ns=0, size=0, content_hash="0")
    b = base.InputFingerprint(path="/x", mtime_ns=0, size=0, content_hash="0")
    c = base.InputFingerprint(path="/y", mtime_ns=0, size=0, content_hash="0")
    assert a == b
    assert a != c


def test_input_fingerprint_is_immutable() -> None:
    fp = base.InputFingerprint(path="/x", mtime_ns=0, size=0, content_hash="0")
    with pytest.raises(AttributeError):
        fp.path = "y"  # type: ignore[misc]


def test_input_fingerprint_field_types_pinned() -> None:
    # AC-2: a mutation that retyped `mtime_ns: float` (silent precision loss)
    # is caught here.
    ann = base.InputFingerprint.__annotations__
    assert ann["path"] is str
    assert ann["mtime_ns"] is int
    assert ann["size"] is int
    assert ann["content_hash"] is str


def test_allowed_base_py_imports_includes_collections() -> None:
    # AC-8: widening of the stdlib-only fence is itself part of the amendment;
    # this test pins the new entry so a future revert is a loud regression.
    assert "collections" in ALLOWED_BASE_PY_IMPORTS


def test_localv2_section_4_shows_phase1_probe_context_fields() -> None:
    # AC-10: code matches doc, never the inverse (ADR-0007). Without this
    # check the doc_fingerprint test catches drift but the source of drift
    # is opaque; this test names what was missed.
    body = extract_section_4_body(LOCALV2_PATH.read_text(encoding="utf-8"))
    assert "parsed_manifest:" in body, "localv2.md §4 ProbeContext missing parsed_manifest"
    assert "input_snapshot:" in body, "localv2.md §4 ProbeContext missing input_snapshot"
    assert "class InputFingerprint(NamedTuple):" in body, (
        "localv2.md §4 missing InputFingerprint NamedTuple block"
    )


def test_adr_0002_names_input_snapshot_and_input_fingerprint() -> None:
    # AC-11: the ADR text is the human-facing record; an ADR that doesn't
    # name input_snapshot is rot the moment Phase 2 reads it for context.
    text = _ADR_0002_PATH.read_text(encoding="utf-8")
    assert "input_snapshot" in text
    assert "InputFingerprint" in text


def test_probe_context_sentinel_fires_on_synthetic_third_field() -> None:
    # AC-18: exercise the sentinel's failure-message contract. A throwaway
    # dataclass with a third field stands in for the future amendment.
    import dataclasses as _dc

    @_dc.dataclass
    class _SyntheticThreeField:
        cache_dir: Path
        output_dir: Path
        workspace: Path
        logger: Any
        config: dict[str, Any]
        parsed_manifest: Any = None
        input_snapshot: Any = None
        future_third_field: Any = None  # the offending addition

    actual = tuple(f.name for f in _dc.fields(_SyntheticThreeField))
    with pytest.raises(AssertionError, match=r"ADR-0002"):
        assert actual == _ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS, (
            f"ProbeContext field list {actual} does not match ADR-0002. "
            f"Adding fields to ProbeContext is gated by ADR-0002 amendment. "
            f"See docs/phases/01-context-gather-layer-a-node/ADRs/"
            f"0002-parsed-manifest-memo-on-probe-context.md."
        )
