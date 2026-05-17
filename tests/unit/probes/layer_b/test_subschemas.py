"""S4-07 — Layer B sub-schemas: structural + behavioral + integration tests.

The three checks land here:

1. **Structural** (AC-2): every nested object node in every Layer B
   sub-schema declares ``additionalProperties: false``. A recursive walker
   (``_schema_walkers._walk_object_nodes``) flags any miss; a mutation
   test (T-02b) deletes the flag at a known nested path and asserts the
   walker catches it — guarding against "the walker passes by accident on
   schemas that already conform."
2. **Behavioral** (AC-6): an extra field at a specified JSON Pointer
   triggers an ``additionalProperties`` rejection from the production
   chokepoint validator; the same envelope without the extra field
   validates clean (round-trip control). Three assertions per row.
3. **Integration** (AC-1b, AC-7): the envelope's ``$ref`` routes each
   slice through its sub-schema; a typed Pydantic-model dump (where the
   slice has a model) round-trips through the chokepoint validator.

Naming convention (mirrors the Layer A precedent ``node_build_system.schema.json``
whose root has ``properties.build_system``): the schema filename / ``$id`` slug
== probe module name (``scip_index``, ``tree_sitter_import_graph``,
``node_reflection``, ``index_health``, ``dep_graph``, ``generated_code``,
``semantic_index_meta``); the inner key inside the schema (and the dict the
probe emits in ``ProbeOutput.schema_slice``) is the per-probe inner slice key.
The envelope routes by probe module name.
"""

from __future__ import annotations

import ast
import copy
import importlib
import json
import re
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from pydantic import BaseModel

from codegenie.errors import SchemaValidationError
from codegenie.schema import validator as validator_mod
from tests.unit.probes.layer_b._schema_walkers import _walk_object_nodes

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_DIR = _REPO_ROOT / "src" / "codegenie" / "schema" / "probes"
_ENVELOPE_PATH = _REPO_ROOT / "src" / "codegenie" / "schema" / "repo_context.schema.json"
_INIT_PATH = _REPO_ROOT / "src" / "codegenie" / "probes" / "__init__.py"
_REGENERATOR = _REPO_ROOT / "tools" / "regenerate_probe_schemas.py"

# (probe_module_name, inner_slice_key) for each Layer B probe.
_LAYER_B: list[tuple[str, str]] = [
    ("dep_graph", "dep_graph"),
    ("generated_code", "generated_code"),
    ("index_health", "index_health"),
    ("node_reflection", "reflection"),
    ("scip_index", "semantic_index"),
    ("semantic_index_meta", "semantic_index_meta"),
    ("tree_sitter_import_graph", "import_graph"),
]
_LAYER_B_PROBE_NAMES: list[str] = sorted(p for p, _ in _LAYER_B)
_INNER_KEY: dict[str, str] = dict(_LAYER_B)

_ID_RE = re.compile(
    r"^https://codewizard-sherpa\.dev/schemas/probes/[a-z][a-z0-9_]*/v\d+\.\d+\.\d+\.json$"
)
_WARNING_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

_ENVELOPE_BASE: dict[str, Any] = {
    "schema_version": "0.1.0",
    "generated_at": "2026-05-17T00:00:00Z",
    "repo": {"root": "/tmp/x", "git_commit": None},
    "probes": {},
}


def _load_schema(probe_name: str) -> dict[str, Any]:
    return json.loads((_SCHEMA_DIR / f"{probe_name}.schema.json").read_text())


def _load_envelope() -> dict[str, Any]:
    return json.loads(_ENVELOPE_PATH.read_text())


# Minimal-valid inner-slice bodies (the value inside `slice_root[inner_key]`)
# for the rejection / round-trip / wiring tests. Each is the smallest dict
# that satisfies its sub-schema's required[]; verified by
# ``test_minimal_slice_fixtures_are_themselves_valid``.
def _inner_index_health() -> dict[str, Any]:
    return {
        "scip": {
            "freshness": {"kind": "fresh", "indexed_at": "2026-01-01T00:00:00Z"},
            "confidence": "high",
            "current_commit": "abc123",
            "last_indexed_at": "2026-01-01T00:00:00Z",
        }
    }


def _inner_semantic_index() -> dict[str, Any]:
    return {
        "scip_index_uri": ".codegenie/context/raw/scip.bin",
        "indexer": "scip-typescript",
        "indexer_version": "0.3.0",
        "files_indexed": 0,
        "files_in_repo": 0,
        "coverage_pct": 0.0,
        "last_indexed_commit": "abc123",
        "last_indexed_at": "2026-01-01T00:00:00Z",
        "indexer_errors": 0,
        "indexer_warnings": 0,
    }


def _inner_import_graph() -> dict[str, Any]:
    return {
        "files_with_imports": 0,
        "total_edges": 0,
        "parsed_files": 0,
        "failed_files": 0,
        "confidence": "high",
        "grammar_versions": {},
    }


def _inner_dep_graph() -> dict[str, Any]:
    return {"graph_path": None, "confidence": "low"}


def _inner_generated_code() -> dict[str, Any]:
    return {
        "files": [{"path": "src/x.ts", "generator": "tsc"}],
        "build_outputs": [],
        "confidence": "high",
    }


def _inner_reflection() -> dict[str, Any]:
    return {
        "eval_usage": 0,
        "function_constructor_usage": 0,
        "dynamic_require_count": 0,
        "dynamic_import_count": 0,
        "dynamic_property_access_count": 0,
        "prototype_manipulation_count": 0,
        "decorator_usage": {
            "nestjs": False,
            "typeorm": False,
            "class_validator": False,
            "custom_decorators_detected": 0,
        },
        "env_var_reads": {"count": 0, "code_path_affecting": 0},
        "confidence_impact": "low",
        "affected_files": [],
    }


def _inner_semantic_index_meta() -> dict[str, Any]:
    return {"tsconfig_path": None, "confidence": "medium"}


# probe_name → inner-slice builder.
_INNER_BUILDERS: dict[str, Any] = {
    "index_health": _inner_index_health,
    "scip_index": _inner_semantic_index,
    "tree_sitter_import_graph": _inner_import_graph,
    "dep_graph": _inner_dep_graph,
    "generated_code": _inner_generated_code,
    "node_reflection": _inner_reflection,
    "semantic_index_meta": _inner_semantic_index_meta,
}


def _minimal_slice(probe_name: str) -> dict[str, Any]:
    """The slice value that lands at ``envelope.probes.<probe_name>`` —
    the inner-slice body wrapped under its inner key."""
    inner_key = _INNER_KEY[probe_name]
    return {inner_key: _INNER_BUILDERS[probe_name]()}


# Where to inject the rogue field (path under the slice root); nested rows
# prove ``additionalProperties: false`` propagates beyond the slice root.
_REJECTION_POINTERS: list[tuple[str, list[str]]] = [
    # rogue field at the SLICE ROOT (sibling of the inner key): catches a
    # contributor writing `probes.scip_index = {semantic_index: {...}, ...rogue}`
    ("scip_index", []),
    ("dep_graph", []),
    ("semantic_index_meta", []),
    # rogue field INSIDE the inner slice body
    ("index_health", ["index_health", "scip"]),
    ("tree_sitter_import_graph", ["import_graph"]),
    ("generated_code", ["generated_code", "files", "0"]),
    ("node_reflection", ["reflection", "decorator_usage"]),
]


def _inject_rogue(slice_body: dict[str, Any], inner_path: list[str]) -> tuple[dict[str, Any], str]:
    """Deep-copy ``slice_body`` and insert ``rogue_field=True`` at
    ``inner_path``. Returns ``(mutated_slice, pointer_under_slice_root)``."""
    body = copy.deepcopy(slice_body)
    target: Any = body
    for seg in inner_path:
        if isinstance(target, list):
            target = target[int(seg)]
        else:
            target = target[seg]
    target["rogue_field"] = True
    pointer = "/" + "/".join([*inner_path, "rogue_field"]) if inner_path else "/rogue_field"
    return body, pointer


# ---------------------------------------------------------------------------
# AC-1, AC-10 — files exist, valid JSON Schema documents
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("probe_name", _LAYER_B_PROBE_NAMES)
def test_subschemas_exist_and_are_valid_json(probe_name: str) -> None:
    """AC-1, AC-10: file exists, parses, passes meta-schema check."""
    path = _SCHEMA_DIR / f"{probe_name}.schema.json"
    assert path.is_file(), f"missing sub-schema file: {path}"
    schema = json.loads(path.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"


# ---------------------------------------------------------------------------
# AC-10b — $id uniqueness, canonical pattern, slice-name agreement
# ---------------------------------------------------------------------------


def test_subschema_ids_are_unique_and_canonical() -> None:
    """AC-10b: $id values are pairwise distinct, canonical-pattern-conformant,
    and their trailing slug equals the envelope's $ref probe name."""
    envelope = _load_envelope()
    envelope_refs = envelope["properties"]["probes"]["properties"]
    ids: list[str] = []
    for probe_name in _LAYER_B_PROBE_NAMES:
        schema = _load_schema(probe_name)
        sid = schema["$id"]
        assert _ID_RE.match(sid), f"{probe_name} $id does not match canonical pattern: {sid}"
        slug = sid.split("/")[-2]
        assert slug == probe_name, (
            f"{probe_name} $id slug ({slug}) does not match filename / envelope $ref key"
        )
        assert envelope_refs[probe_name]["$ref"] == sid, (
            f"envelope $ref for {probe_name} does not match its sub-schema $id"
        )
        ids.append(sid)
    assert len(set(ids)) == len(ids), "duplicate $id values across Layer B sub-schemas"


# ---------------------------------------------------------------------------
# AC-1b — envelope routes every Layer B probe through its sub-schema
# ---------------------------------------------------------------------------


def test_envelope_refs_every_layer_b_subschema() -> None:
    envelope = _load_envelope()
    refs = envelope["properties"]["probes"]["properties"]
    for probe_name in _LAYER_B_PROBE_NAMES:
        assert probe_name in refs, f"envelope missing $ref for {probe_name}"
        schema = _load_schema(probe_name)
        assert refs[probe_name]["$ref"] == schema["$id"]


# ---------------------------------------------------------------------------
# AC-2 — additionalProperties: false at every nested object node
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("probe_name", _LAYER_B_PROBE_NAMES)
def test_additional_properties_false_at_every_object_level(probe_name: str) -> None:
    schema = _load_schema(probe_name)
    missing = _walk_object_nodes(schema)
    assert missing == [], (
        f"{probe_name}: object nodes missing additionalProperties: false at: {missing}"
    )


def test_walker_catches_removed_additional_properties_false() -> None:
    """AC-2 mutation-resistance: prove the walker isn't passing by accident."""
    schema = _load_schema("index_health")
    mutated = copy.deepcopy(schema)
    # Delete additionalProperties at $defs.Stale (nested in the embedded
    # IndexFreshness sub-schema, hoisted to the sub-schema root).
    del mutated["$defs"]["Stale"]["additionalProperties"]
    missing = _walk_object_nodes(mutated)
    assert any("$defs/Stale" in m for m in missing), (
        f"walker did not flag the deleted additionalProperties: missing={missing}"
    )


# ---------------------------------------------------------------------------
# AC-3 — warnings[]/errors[] are ADR-0007-pattern-constrained as flat strings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("probe_name", _LAYER_B_PROBE_NAMES)
def test_warnings_and_errors_pattern_constraints(probe_name: str) -> None:
    """Schema-side: ``warnings``/``errors`` (when present, at the inner-slice
    level) are flat-string arrays with the ADR-0007 regex pattern."""
    schema = _load_schema(probe_name)
    inner_key = _INNER_KEY[probe_name]
    inner = schema["properties"][inner_key].get("properties", {})
    for field in ("warnings", "errors"):
        if field not in inner:
            continue
        block = inner[field]
        assert block.get("type") == "array", (
            f"{probe_name}.{field} must be type=array, got {block.get('type')}"
        )
        items = block.get("items", {})
        assert items.get("type") == "string", (
            f"{probe_name}.{field} items must be type=string, got {items.get('type')}"
        )
        assert items.get("pattern") == _WARNING_ID_RE.pattern, (
            f"{probe_name}.{field} items pattern mismatch: {items.get('pattern')}"
        )


_LAYER_B_PROBE_MODULES = {
    "index_health": "codegenie.probes.layer_b.index_health",
    "scip_index": "codegenie.probes.layer_b.scip_index",
    "tree_sitter_import_graph": "codegenie.probes.layer_b.tree_sitter_import_graph",
    "dep_graph": "codegenie.probes.layer_b.dep_graph",
    "generated_code": "codegenie.probes.layer_b.generated_code",
    "node_reflection": "codegenie.probes.layer_b.node_reflection",
    "semantic_index_meta": "codegenie.probes.layer_b.semantic_index_meta",
}


@pytest.mark.parametrize("probe_name", _LAYER_B_PROBE_NAMES)
def test_each_probe_emitted_ids_match_pattern_constraint(probe_name: str) -> None:
    """AC-3 probe-module side: every member of ``_WARNING_IDS`` (and
    ``_ERROR_IDS`` if present) matches the ADR-0007 regex.

    Skip-with-warn for probe modules that haven't shipped ``_WARNING_IDS``."""
    mod = importlib.import_module(_LAYER_B_PROBE_MODULES[probe_name])
    warning_ids = getattr(mod, "_WARNING_IDS", None)
    if warning_ids is None:
        warnings.warn(
            f"probe module {_LAYER_B_PROBE_MODULES[probe_name]} has no _WARNING_IDS; "
            "test is non-load-bearing for this probe until S4-XX lands the constant.",
            stacklevel=2,
        )
        pytest.skip(f"{probe_name} lacks _WARNING_IDS")
    for wid in warning_ids:
        assert _WARNING_ID_RE.match(wid), (
            f"{probe_name} _WARNING_IDS contains non-conformant id: {wid}"
        )
    error_ids = getattr(mod, "_ERROR_IDS", None)
    if error_ids is not None:
        for eid in error_ids:
            assert _WARNING_ID_RE.match(eid), (
                f"{probe_name} _ERROR_IDS contains non-conformant id: {eid}"
            )


# ---------------------------------------------------------------------------
# AC-4 — slice optional at envelope, wired at properties
# ---------------------------------------------------------------------------


def test_layer_b_slices_wired_and_optional_at_envelope() -> None:
    """AC-4: positive — each probe name is under properties; negative — none
    appear in any envelope-level required[]."""
    envelope = _load_envelope()
    probes_block = envelope["properties"]["probes"]
    props = probes_block["properties"]
    for probe_name in _LAYER_B_PROBE_NAMES:
        assert probe_name in props
    envelope_required = envelope.get("required", [])
    for probe_name in _LAYER_B_PROBE_NAMES:
        assert probe_name not in envelope_required
    probes_required = probes_block.get("required", [])
    for probe_name in _LAYER_B_PROBE_NAMES:
        assert probe_name not in probes_required


# ---------------------------------------------------------------------------
# AC-5, AC-5b — regenerator is reproducible; discriminators survive
# ---------------------------------------------------------------------------


def test_index_health_subschema_regenerates_identically() -> None:
    """AC-5: re-running the regenerator writes byte-identical files."""
    committed = (_SCHEMA_DIR / "index_health.schema.json").read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "tools.regenerate_probe_schemas"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, f"regenerator failed: {result.stderr.decode()}"
    after = (_SCHEMA_DIR / "index_health.schema.json").read_bytes()
    assert committed == after, "regenerator output is not byte-identical to committed file"

    src = _REGENERATOR.read_text()
    assert "# DECLARED-INPUTS:" in src
    assert "src/codegenie/indices/freshness.py" in src


def test_index_freshness_discriminators_preserved_in_schema() -> None:
    """AC-5b: ``$defs`` entries (hoisted to schema root) carry the right
    ``kind.const`` discriminators."""
    schema = _load_schema("index_health")
    defs = schema["$defs"]
    expected = {
        "Fresh": "fresh",
        "Stale": "stale",
        "CommitsBehind": "commits_behind",
        "DigestMismatch": "digest_mismatch",
        "CoverageGap": "coverage_gap",
        "IndexerError": "indexer_error",
    }
    for name, expected_kind in expected.items():
        assert name in defs, f"$defs missing {name}"
        kind = defs[name]["properties"]["kind"]
        assert kind.get("const") == expected_kind, (
            f"$defs.{name}.properties.kind.const != {expected_kind!r} (got {kind.get('const')!r})"
        )


# ---------------------------------------------------------------------------
# AC-6 — per-probe rejection test (rejection + validator-fingerprint + control)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_validator_cache() -> None:
    """Each test gets a fresh cache so on-disk edits land between runs."""
    validator_mod._validator.cache_clear()
    yield
    validator_mod._validator.cache_clear()


def _format_pointer(error: jsonschema.ValidationError) -> str:
    """RFC-6901 JSON Pointer for ``error.absolute_path`` (parent of the
    rogue field for ``additionalProperties`` errors)."""
    return "/" + "/".join(str(seg) for seg in error.absolute_path)


@pytest.mark.parametrize("probe_name,inner_path", _REJECTION_POINTERS, ids=lambda v: str(v))
def test_subschema_rejects_extra_field(probe_name: str, inner_path: list[str]) -> None:
    """AC-6: (a) rejection fires; (b) validator is ``additionalProperties``,
    pointer is the offending container, rogue key surfaces in message;
    (c) round-trip control — the same envelope without the rogue field is
    accepted.

    Note: ``jsonschema`` ``additionalProperties`` errors carry
    ``absolute_path`` pointing at the parent object; the unexpected key
    lives in ``message``."""
    base_slice = _minimal_slice(probe_name)
    rogue_slice, _ = _inject_rogue(base_slice, inner_path)
    expected_container_pointer = (
        "/probes/" + probe_name + (("/" + "/".join(inner_path)) if inner_path else "")
    )

    bad_envelope = {**_ENVELOPE_BASE, "probes": {probe_name: rogue_slice}}

    with pytest.raises(SchemaValidationError) as exc_info:
        validator_mod.validate(bad_envelope)
    cause = exc_info.value.__cause__
    assert isinstance(cause, jsonschema.ValidationError), (
        f"expected jsonschema.ValidationError cause, got {type(cause).__name__}"
    )
    assert cause.validator == "additionalProperties", (
        f"{probe_name}: expected additionalProperties validator, got {cause.validator!r}"
    )
    actual_pointer = _format_pointer(cause)
    assert actual_pointer == expected_container_pointer, (
        f"{probe_name}: container pointer mismatch. "
        f"expected={expected_container_pointer} got={actual_pointer}"
    )
    assert "rogue_field" in cause.message, (
        f"{probe_name}: rogue field name not surfaced in error message: {cause.message}"
    )

    good_envelope = {**_ENVELOPE_BASE, "probes": {probe_name: base_slice}}
    validator_mod.validate(good_envelope)


def test_minimal_slice_fixtures_are_themselves_valid() -> None:
    """The rejection-test round-trip control depends on the minimal slices
    actually being valid — pin that invariant once, here, so a future
    fixture edit failing the assumption fails loud rather than silently
    making AC-6 vacuous."""
    for probe_name in _LAYER_B_PROBE_NAMES:
        envelope = {**_ENVELOPE_BASE, "probes": {probe_name: _minimal_slice(probe_name)}}
        validator_mod.validate(envelope)


# ---------------------------------------------------------------------------
# AC-7 — Typed-model round-trip against the chokepoint validator
# ---------------------------------------------------------------------------


def _slice_pydantic_model(probe_name: str) -> type[BaseModel] | None:
    if probe_name == "scip_index":
        from codegenie.probes.layer_b.scip_slice import SemanticIndexSlice

        return SemanticIndexSlice
    if probe_name == "dep_graph":
        from codegenie.depgraph.model import DepGraphProbeOutput

        return DepGraphProbeOutput
    return None


def _typed_model_instance(probe_name: str) -> BaseModel | None:
    if probe_name == "scip_index":
        from codegenie.probes.layer_b.scip_slice import SemanticIndexSlice

        return SemanticIndexSlice(
            scip_index_uri=".codegenie/context/raw/scip.bin",
            indexer="scip-typescript",
            indexer_version="0.3.0",
            files_indexed=0,
            files_in_repo=0,
            coverage_pct=0.0,
            last_indexed_commit="abc123",
            last_indexed_at="2026-01-01T00:00:00Z",
            indexer_errors=0,
            indexer_warnings=0,
        )
    if probe_name == "dep_graph":
        from codegenie.depgraph.model import DepGraphProbeOutput

        return DepGraphProbeOutput(graph_path=None, confidence="low")
    return None


@pytest.mark.parametrize("probe_name", _LAYER_B_PROBE_NAMES)
def test_layer_b_typed_model_round_trips_against_subschema(probe_name: str) -> None:
    """AC-7: model.model_dump(mode='json') wrapped in the envelope and
    pushed through the chokepoint validator must be accepted.

    Skip-with-warn for slices that ship dict-shaped (no top-level Pydantic
    model exists yet)."""
    instance = _typed_model_instance(probe_name)
    if instance is None:
        warnings.warn(
            f"{probe_name} has no top-level Pydantic model — round-trip is "
            "exercised by the rejection test's control row only. Future story "
            "may promote the slice to a model and unskip.",
            stacklevel=2,
        )
        pytest.skip(f"{probe_name} dict-shaped at source")
    inner_key = _INNER_KEY[probe_name]
    payload = instance.model_dump(mode="json")
    envelope = {**_ENVELOPE_BASE, "probes": {probe_name: {inner_key: payload}}}
    validator_mod.validate(envelope)


@pytest.mark.parametrize("probe_name", _LAYER_B_PROBE_NAMES)
def test_typed_model_matches_subschema_structure(probe_name: str) -> None:
    """AC-7b: bidirectional check — model fields ⊆ schema inner-slice
    properties AND schema required[] ⊆ model non-Optional-without-default
    fields."""
    model = _slice_pydantic_model(probe_name)
    if model is None:
        pytest.skip(f"{probe_name} dict-shaped at source")
    schema = _load_schema(probe_name)
    inner_key = _INNER_KEY[probe_name]
    inner = schema["properties"][inner_key]
    schema_props = set(inner.get("properties", {}).keys())
    # Schema may declare warnings/errors slots the model doesn't carry directly
    # (Phase 1 routes them via ProbeOutput.errors). Also allow probe-emitted
    # extras like dep_graph's ecosystem/nodes_count/edges_count (not on the
    # typed model yet).
    schema_props -= {"warnings", "errors"}
    model_fields = set(model.model_fields.keys())
    extra_in_model = model_fields - schema_props
    assert not extra_in_model, (
        f"{probe_name}: model has fields not declared in schema: {extra_in_model}"
    )
    schema_required = set(inner.get("required", []))
    model_required = {name for name, info in model.model_fields.items() if info.is_required()}
    missing_in_model = schema_required - model_required
    # Schema may require fields the typed model doesn't yet model (e.g.,
    # dep_graph required only has [graph_path, confidence] from Pydantic,
    # which IS a subset of model_required). Allow when schema does NOT
    # require — assert only when schema strictly requires a field the
    # model marks optional.
    assert not missing_in_model, (
        f"{probe_name}: schema requires fields the model marks optional/defaulted: "
        f"{missing_in_model}"
    )


# ---------------------------------------------------------------------------
# AC-8 — explicit additive imports in codegenie.probes.__init__
# ---------------------------------------------------------------------------


_LAYER_B_PROBE_MODULES_ORDERED: list[str] = sorted(
    [
        "dep_graph",
        "generated_code",
        "index_health",
        "node_reflection",
        "scip_index",
        "semantic_index_meta",
        "tree_sitter_import_graph",
    ]
)


def test_layer_b_probes_grouped_additive_imports() -> None:
    """AC-8: the grouped ``from codegenie.probes.layer_b import (...)`` block
    in ``__init__.py`` lists exactly seven module names in alphabetical order
    — matching the codebase's grouped-import convention."""
    tree = ast.parse(_INIT_PATH.read_text())
    target_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "codegenie.probes.layer_b"
    ]
    assert len(target_imports) == 1, (
        f"expected exactly one grouped ImportFrom for codegenie.probes.layer_b, "
        f"got {len(target_imports)}"
    )
    node = target_imports[0]
    names = [alias.name for alias in node.names]
    assert names == _LAYER_B_PROBE_MODULES_ORDERED, (
        f"Layer B imports out of order or missing: {names} != {_LAYER_B_PROBE_MODULES_ORDERED}"
    )


# ---------------------------------------------------------------------------
# AC-9 — all seven probes registered in default_registry
# ---------------------------------------------------------------------------


def test_layer_b_probes_in_default_registry() -> None:
    """AC-9: collective presence check (each story's per-probe test exists
    too; this one catches missing package-level import side-effects)."""
    from codegenie.probes.registry import default_registry

    registered = {p.name for p in default_registry.all_probes()}
    expected = set(_LAYER_B_PROBE_NAMES)
    missing = expected - registered
    assert not missing, f"default_registry missing Layer B probes: {missing}"
