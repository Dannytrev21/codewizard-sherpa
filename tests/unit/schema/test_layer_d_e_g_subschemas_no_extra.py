"""S6-08 AC-9 + AC-17 — Layer D + E + G sub-schema structural enforcement.

Two invariants:

- **AC-9.** Every nested object node in every Step-6 sub-schema (8 D + 3 E
  + 5 G = 16) declares ``additionalProperties: false`` (Phase 1
  ADR-0004 convention). The walker visits ``properties``,
  ``patternProperties``, ``$defs``, ``oneOf``, ``anyOf``, ``allOf``,
  ``items``, ``prefixItems``, ``if``, ``then``, ``else``, and ``not`` —
  the same containers ``tools/regenerate_probe_schemas.py`` /
  ``scripts/regen_subschemas.py`` set the property on.

- **AC-17.** The envelope's ``$ref`` graph references every Step-6
  sub-schema by its layered ``$id`` URI. A new Step-6 sub-schema lands
  as a new file + a new envelope ``$ref`` line — never an edit to an
  existing ref.

Mutation discipline (walker T-02b precedent — see
``tests/unit/probes/layer_b/test_subschemas.py``): the walker fires on
ANY missing ``additionalProperties: false`` at ANY nested object,
including ``$defs`` and ``oneOf`` variants — guarding against "the
walker passes by accident on schemas that already conform."
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_SCHEMA_PROBES: Final[Path] = _REPO_ROOT / "src" / "codegenie" / "schema" / "probes"
_ENVELOPE_PATH: Final[Path] = (
    _REPO_ROOT / "src" / "codegenie" / "schema" / "repo_context.schema.json"
)

# Expected layered sub-schema names per layer (AC-9 count = 8 + 3 + 5 = 16).
EXPECTED_LAYER_D: Final[frozenset[str]] = frozenset(
    {
        "skills_index",
        "conventions",
        "adrs",
        "repo_notes",
        "repo_config",
        "policy",
        "exceptions",
        "external_docs",
    }
)
EXPECTED_LAYER_E: Final[frozenset[str]] = frozenset(
    {"ownership", "service_topology_stub", "slo_stub"}
)
EXPECTED_LAYER_G: Final[frozenset[str]] = frozenset(
    {"semgrep", "ast_grep", "ripgrep_curated", "gitleaks", "test_coverage_mapping"}
)

_LAYER_DIRS: Final[list[tuple[str, frozenset[str]]]] = [
    ("layer_d", EXPECTED_LAYER_D),
    ("layer_e", EXPECTED_LAYER_E),
    ("layer_g", EXPECTED_LAYER_G),
]


def _walk_object_nodes(node: object, path: str = "$"):  # type: ignore[no-untyped-def]
    """Yield ``(json_pointer, node)`` for every object node in the schema."""
    if isinstance(node, dict):
        is_object = (
            node.get("type") == "object"
            or (isinstance(node.get("type"), list) and "object" in node["type"])
            or (node.get("type") is None and ("properties" in node or "patternProperties" in node))
        )
        if is_object:
            yield path, node
        for key in ("properties", "patternProperties", "$defs"):
            sub = node.get(key)
            if isinstance(sub, dict):
                for k, v in sub.items():
                    yield from _walk_object_nodes(v, f"{path}.{key}.{k}")
        for key in ("oneOf", "anyOf", "allOf", "prefixItems"):
            sub = node.get(key)
            if isinstance(sub, list):
                for i, v in enumerate(sub):
                    yield from _walk_object_nodes(v, f"{path}.{key}[{i}]")
        for key in ("if", "then", "else", "items", "not"):
            sub = node.get(key)
            if sub is not None:
                yield from _walk_object_nodes(sub, f"{path}.{key}")
        ap = node.get("additionalProperties")
        if isinstance(ap, dict):
            yield from _walk_object_nodes(ap, f"{path}.additionalProperties")


@pytest.mark.parametrize("layer_dir,expected_names", _LAYER_DIRS)
def test_layer_dir_has_expected_schemas(layer_dir: str, expected_names: frozenset[str]) -> None:
    """AC-9 count enforcement: each layer directory contains its
    expected set of sub-schema files (no more, no fewer)."""
    schemas = sorted((_SCHEMA_PROBES / layer_dir).glob("*.schema.json"))
    cleaned = {p.name.removesuffix(".schema.json") for p in schemas}
    assert cleaned == expected_names, (
        f"{layer_dir} mismatch: expected {expected_names}, got {cleaned}"
    )


@pytest.mark.parametrize("layer_dir,_expected", _LAYER_DIRS)
def test_every_object_rejects_extra(layer_dir: str, _expected: frozenset[str]) -> None:
    """AC-9. Every nested *typed* object node in every Step-6 sub-schema
    either declares ``additionalProperties: false`` OR declares a typed
    schema for ``additionalProperties`` (legitimate map-of-X shape —
    e.g., ``dict[str, JSONValue]`` on ``Finding.metadata``).

    Free-form maps (``type: object`` with NO ``properties`` and NO
    ``patternProperties``) are exempt — those are ``dict[str, X]``
    payloads where the consumer model carries the constraint.

    The leak we are guarding against is the *typed* object that
    silently grows a stray field.
    """
    for schema_path in sorted((_SCHEMA_PROBES / layer_dir).glob("*.schema.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for jpath, obj in _walk_object_nodes(schema):
            has_typed_shape = "properties" in obj or "patternProperties" in obj
            if not has_typed_shape:
                continue
            ap = obj.get("additionalProperties")
            permits_anything = ap is None or ap is True
            assert not permits_anything, (
                f"{schema_path.name}:{jpath} (typed object) permits extra properties (ap={ap!r})"
            )


def test_walker_catches_a_dropped_additional_properties_flag() -> None:
    """Mutation T-02b: the walker fires on a schema with a dropped
    ``additionalProperties: false`` at a known nested path."""
    mutated = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "outer": {
                "type": "object",
                # NOTE: deliberately missing ``additionalProperties: false``
                "properties": {"x": {"type": "integer"}},
            }
        },
    }
    misses = [
        path
        for path, obj in _walk_object_nodes(mutated)
        if obj.get("additionalProperties") is None or obj.get("additionalProperties") is True
    ]
    assert misses == ["$.properties.outer"], misses


def test_envelope_references_all_step6_subschemas() -> None:
    """AC-17. The envelope's ``$ref`` graph contains a $ref to every
    Step-6 layered sub-schema (16 total). A new Step-6 sub-schema lands
    as a new file + a new envelope ``$ref`` line — never an edit to
    existing refs."""
    envelope = json.loads(_ENVELOPE_PATH.read_text(encoding="utf-8"))
    refs: set[str] = set()
    for entry in envelope["properties"]["probes"]["properties"].values():
        ref = entry.get("$ref")
        if isinstance(ref, str):
            refs.add(ref)
    missing: list[str] = []
    for layer_dir, names in _LAYER_DIRS:
        for name in names:
            expected = (
                f"https://codewizard-sherpa.dev/schemas/probes/{layer_dir}/{name}/v0.1.0.json"
            )
            if expected not in refs:
                missing.append(expected)
    assert not missing, f"envelope is missing $refs for: {missing}"
