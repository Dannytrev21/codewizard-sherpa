"""S4-07 — regenerate the seven Layer B per-probe JSON Schemas (Phase 1 ADR-0004).

# DECLARED-INPUTS:
#   src/codegenie/indices/freshness.py
#   src/codegenie/depgraph/model.py
#   src/codegenie/probes/layer_b/scip_slice.py

The script is a tuple-registry of builders — Open/Closed at the script body
(Phase 3 Layer C probes extend by one-line tuple insertion, never by
edit-and-rename). The kernel post-processes every builder's output uniformly:

- ``_set_id_and_schema(...)`` writes ``$schema`` (Draft 2020-12) and ``$id``
  (``https://codewizard-sherpa.dev/schemas/probes/<probe_name>/v0.1.0.json``).
- ``_set_additional_props_false_recursively(...)`` walks every nested object
  node (via ``$defs``, ``oneOf``/``anyOf``/``allOf``, ``if``/``then``/``else``,
  ``items``, ``prefixItems``, ``additionalProperties`` when a schema,
  ``properties.*``, ``patternProperties.*``) and sets
  ``additionalProperties: false`` where missing.

Serialization passes through the single ``write_schema_file`` chokepoint so
byte-identical reruns are enforced by one function, not seven copies.

Sub-schemas where Pydantic models exist (``index_health`` — embeds the
``IndexFreshness`` ``$defs`` via ``TypeAdapter.json_schema``; ``dep_graph`` —
``DepGraphProbeOutput.model_json_schema``; ``scip_index`` —
``SemanticIndexSlice.model_json_schema``) are partially generated; the rest are
hand-coded per the per-probe stories' AC fields. Generated portions are reviewed
by re-running this script; hand-edits to those portions break ``T-06`` (the
byte-identical regeneration gate).

Naming convention (mirrors the six Layer A sub-schemas, e.g.
``node_build_system.schema.json`` whose root has ``properties.build_system``):

- Schema filename / ``$id`` slug == **probe module name** (e.g.,
  ``scip_index``, ``tree_sitter_import_graph``, ``node_reflection``,
  ``index_health``, ``dep_graph``, ``generated_code``, ``semantic_index_meta``).
  The envelope wires by probe module name.
- The schema's root ``properties`` declares **the inner slice key** the probe
  emits inside ``ProbeOutput.schema_slice``. Concretely:
    scip_index               -> properties.semantic_index
    tree_sitter_import_graph -> properties.import_graph
    node_reflection          -> properties.reflection
    {index_health, dep_graph, generated_code, semantic_index_meta}
                              -> properties.<probe_name>   (self-wrapping)

The coordinator merges ``probe.schema_slice`` directly under
``envelope.probes.<probe_name>`` (see ``_seam_shallow_merge`` in
``codegenie.cli``), so the schema sees exactly what the probe emits as the
value of the ``probes.<probe_name>`` namespace.

Run:

    python -m tools.regenerate_probe_schemas

Output is written to ``src/codegenie/schema/probes/<probe_name>.schema.json``.
Re-runs are byte-identical (``T-06``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

# Trigger full ``codegenie.probes`` package initialization first so the
# ``codegenie.depgraph`` registry's circular dependency on
# ``codegenie.probes.layer_b.dep_graph`` resolves through normal import order
# (the package __init__ chain is the only consumer that resolves both sides).
import codegenie.probes  # noqa: F401  # see comment above
from codegenie.depgraph.model import DepGraphProbeOutput
from codegenie.indices.freshness import IndexFreshness
from codegenie.probes.layer_b.scip_slice import SemanticIndexSlice

_SchemaDict = dict[str, object]

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_OUT_DIR: Final[Path] = _REPO_ROOT / "src" / "codegenie" / "schema" / "probes"
_ID_STEM: Final[str] = "https://codewizard-sherpa.dev/schemas/probes"
_VERSION: Final[str] = "v0.1.0"

_DRAFT_2020_12: Final[str] = "https://json-schema.org/draft/2020-12/schema"

_ID_PATTERN: Final[str] = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
"""ADR-0007 ID pattern for warnings/errors items."""

_WARNINGS_BLOCK: Final[_SchemaDict] = {
    "type": "array",
    "description": ("Soft-degrade signals. Each item matches the ADR-0007 ID pattern."),
    "items": {"type": "string", "pattern": _ID_PATTERN},
}

_ERRORS_BLOCK: Final[_SchemaDict] = {
    "type": "array",
    "description": (
        "Forward-compatible per-slice error IDs. Each item matches the ADR-0007 ID pattern."
    ),
    "items": {"type": "string", "pattern": _ID_PATTERN},
}


# ---------------------------------------------------------------------------
# Pure inner-body builders (functional core). Each returns the schema for
# the INNER slice value (the value of ``probes.<probe>.<inner_key>``).
# The outer wrapper (``properties.<inner_key>`` + ``required: [<inner_key>]``)
# is composed by ``_wrap_inner`` so the discipline is uniform.
# ---------------------------------------------------------------------------


def _index_health_inner() -> _SchemaDict:
    """Per-source ``IndexFreshness`` records — index source name → freshness."""
    freshness_schema = TypeAdapter(IndexFreshness).json_schema()
    defs = dict(freshness_schema.get("$defs", {}))
    index_freshness_inline = {
        "oneOf": freshness_schema["oneOf"],
        "discriminator": freshness_schema["discriminator"],
    }
    per_source_entry: _SchemaDict = {
        "type": "object",
        "required": ["freshness", "confidence", "current_commit", "last_indexed_at"],
        "properties": {
            "freshness": index_freshness_inline,
            "confidence": {"enum": ["high", "medium", "low"], "type": "string"},
            "current_commit": {"type": "string"},
            "last_indexed_at": {"type": ["string", "null"]},
        },
    }
    return {
        "type": "object",
        "patternProperties": {r"^[a-z][a-z0-9_]*$": per_source_entry},
        "$defs": defs,
    }


def _semantic_index_inner() -> _SchemaDict:
    schema = SemanticIndexSlice.model_json_schema()
    schema.pop("title", None)
    props = schema.setdefault("properties", {})
    props["warnings"] = _WARNINGS_BLOCK
    props["errors"] = _ERRORS_BLOCK
    return schema


def _import_graph_inner() -> _SchemaDict:
    return {
        "type": "object",
        "required": [
            "files_with_imports",
            "total_edges",
            "parsed_files",
            "failed_files",
            "confidence",
            "grammar_versions",
        ],
        "properties": {
            "files_with_imports": {"type": "integer", "minimum": 0},
            "total_edges": {"type": "integer", "minimum": 0},
            "parsed_files": {"type": "integer", "minimum": 0},
            "failed_files": {"type": "integer", "minimum": 0},
            "confidence": {"enum": ["high", "medium", "low"], "type": "string"},
            "grammar_versions": {
                "type": "object",
                "description": (
                    "Per-grammar version string (e.g., 'typescript' -> '0.23.2'). "
                    "Keys are tree-sitter language names."
                ),
                "additionalProperties": {"type": "string"},
            },
            "import_graph_uri": {
                "type": "string",
                "description": (
                    "Relative path to the raw artifact JSON (omitted when "
                    "the probe produced zero edges)."
                ),
            },
            "warnings": _WARNINGS_BLOCK,
            "errors": _ERRORS_BLOCK,
        },
    }


def _dep_graph_inner() -> _SchemaDict:
    schema = DepGraphProbeOutput.model_json_schema()
    schema.pop("title", None)
    # Probe emits extra fields (ecosystem, nodes_count, edges_count) not on
    # the typed model; declare them as optional to match the observed slice.
    props = schema.setdefault("properties", {})
    props.setdefault("ecosystem", {"type": ["string", "null"]})
    props.setdefault("nodes_count", {"type": "integer", "minimum": 0})
    props.setdefault("edges_count", {"type": "integer", "minimum": 0})
    props["warnings"] = _WARNINGS_BLOCK
    props["errors"] = _ERRORS_BLOCK
    return schema


def _generated_code_inner() -> _SchemaDict:
    return {
        "type": "object",
        "required": ["files", "build_outputs", "confidence"],
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["path", "generator"],
                    "properties": {
                        "path": {"type": "string"},
                        "generator": {"type": "string"},
                        "regenerate_command": {"type": "string"},
                    },
                },
            },
            "build_outputs": {"type": "array", "items": {"type": "string"}},
            "confidence": {"enum": ["high", "medium", "low"], "type": "string"},
            "warnings": _WARNINGS_BLOCK,
            "errors": _ERRORS_BLOCK,
        },
    }


def _reflection_inner() -> _SchemaDict:
    return {
        "type": "object",
        "required": [
            "eval_usage",
            "function_constructor_usage",
            "dynamic_require_count",
            "dynamic_import_count",
            "dynamic_property_access_count",
            "prototype_manipulation_count",
            "decorator_usage",
            "env_var_reads",
            "confidence_impact",
            "affected_files",
        ],
        "properties": {
            "eval_usage": {"type": "integer", "minimum": 0},
            "function_constructor_usage": {"type": "integer", "minimum": 0},
            "dynamic_require_count": {"type": "integer", "minimum": 0},
            "dynamic_import_count": {"type": "integer", "minimum": 0},
            "dynamic_property_access_count": {"type": "integer", "minimum": 0},
            "prototype_manipulation_count": {"type": "integer", "minimum": 0},
            "decorator_usage": {
                "type": "object",
                "required": [
                    "nestjs",
                    "typeorm",
                    "class_validator",
                    "custom_decorators_detected",
                ],
                "properties": {
                    "nestjs": {"type": "boolean"},
                    "typeorm": {"type": "boolean"},
                    "class_validator": {"type": "boolean"},
                    "custom_decorators_detected": {"type": "integer", "minimum": 0},
                },
            },
            "env_var_reads": {
                "type": "object",
                "required": ["count", "code_path_affecting"],
                "properties": {
                    "count": {"type": "integer", "minimum": 0},
                    "code_path_affecting": {"type": "integer", "minimum": 0},
                },
            },
            "confidence_impact": {
                "enum": ["high", "medium", "low"],
                "type": "string",
                "description": (
                    "INVERTED semantics: 'high' means observed reflection is "
                    "substantial; 'low' means the slice is structurally clean."
                ),
            },
            "affected_files": {"type": "array", "items": {"type": "string"}},
            "warnings": _WARNINGS_BLOCK,
            "errors": _ERRORS_BLOCK,
        },
    }


def _semantic_index_meta_inner() -> _SchemaDict:
    return {
        "type": "object",
        "required": ["tsconfig_path", "confidence"],
        "properties": {
            "tsconfig_path": {"type": ["string", "null"]},
            "has_extends": {"type": "boolean"},
            "target": {"type": ["string", "null"]},
            "module": {"type": ["string", "null"]},
            "module_resolution": {"type": ["string", "null"]},
            "strict": {"type": "boolean"},
            "include_globs": {"type": "array", "items": {"type": "string"}},
            "exclude_globs": {"type": "array", "items": {"type": "string"}},
            "files_count_estimate": {"type": "integer", "minimum": 0},
            "confidence": {"enum": ["high", "medium", "low"], "type": "string"},
            "warnings": _WARNINGS_BLOCK,
            "errors": _ERRORS_BLOCK,
        },
    }


# Probe module name → (inner slice key, inner-body builder, schema title)
_BUILDERS: list[tuple[str, str, Callable[[], _SchemaDict], str]] = [
    ("index_health", "index_health", _index_health_inner, "IndexHealth probe output"),
    ("scip_index", "semantic_index", _semantic_index_inner, "ScipIndex probe output"),
    (
        "tree_sitter_import_graph",
        "import_graph",
        _import_graph_inner,
        "TreeSitterImportGraph probe output",
    ),
    ("dep_graph", "dep_graph", _dep_graph_inner, "DepGraph probe output"),
    ("generated_code", "generated_code", _generated_code_inner, "GeneratedCode probe output"),
    ("node_reflection", "reflection", _reflection_inner, "NodeReflection probe output"),
    (
        "semantic_index_meta",
        "semantic_index_meta",
        _semantic_index_meta_inner,
        "SemanticIndexMeta probe output",
    ),
]


# ---------------------------------------------------------------------------
# Kernel post-processing (pure helpers).
# ---------------------------------------------------------------------------


def _wrap_inner(
    probe_name: str,
    inner_key: str,
    inner_body: _SchemaDict,
    title: str,
) -> _SchemaDict:
    """Compose the slice-root schema from the inner body.

    Matches the Layer A convention (e.g. ``node_build_system.schema.json``):
    a single required inner-key property whose value is the inner body.
    Any ``$defs`` from the inner body is hoisted to the sub-schema root so
    that ``#/$defs/<Name>`` refs (emitted by Pydantic's
    ``model_json_schema``) resolve against the file root.
    """
    inner_defs: dict[str, object] = {}
    if isinstance(inner_body, dict) and "$defs" in inner_body:
        raw = inner_body.pop("$defs")
        if isinstance(raw, dict):
            inner_defs = dict(raw)
    wrapped: _SchemaDict = {
        "title": title,
        "description": (
            f"Slice produced by the {probe_name} probe (Phase 2 Layer B). "
            f"The slice root carries a single key '{inner_key}' whose value "
            "is the probe's typed output."
        ),
        "type": "object",
        "required": [inner_key],
        "properties": {inner_key: inner_body},
    }
    if inner_defs:
        wrapped["$defs"] = inner_defs
    return wrapped


def _set_id_and_schema(schema: _SchemaDict, probe_name: str) -> _SchemaDict:
    return {
        "$schema": _DRAFT_2020_12,
        "$id": f"{_ID_STEM}/{probe_name}/{_VERSION}.json",
        **schema,
    }


def _is_object_node(node: object) -> bool:
    if not isinstance(node, dict):
        return False
    t = node.get("type")
    if t == "object":
        return True
    if isinstance(t, list) and "object" in t:
        return True
    if t is None and ("properties" in node or "patternProperties" in node):
        return True
    return False


def _set_additional_props_false_recursively(schema: _SchemaDict) -> None:
    """In-place walk; sets ``additionalProperties: false`` on every object
    node missing the keyword, traversing every standard subschema container.
    """

    def _visit(node: object) -> None:
        if not isinstance(node, dict):
            return
        if _is_object_node(node) and "additionalProperties" not in node:
            node["additionalProperties"] = False
        for key in ("properties", "patternProperties", "$defs"):
            sub = node.get(key)
            if isinstance(sub, dict):
                for v in sub.values():
                    _visit(v)
        for key in ("oneOf", "anyOf", "allOf", "prefixItems"):
            sub = node.get(key)
            if isinstance(sub, list):
                for v in sub:
                    _visit(v)
        for key in ("if", "then", "else", "items", "not"):
            _visit(node.get(key))
        ap = node.get("additionalProperties")
        if isinstance(ap, dict):
            _visit(ap)

    _visit(schema)


def write_schema_file(path: Path, schema: _SchemaDict) -> None:
    """Smart-constructor at the serialization boundary — the single chokepoint
    through which every sub-schema is written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")


def build_one(
    probe_name: str,
    inner_key: str,
    inner_builder: Callable[[], _SchemaDict],
    title: str,
) -> _SchemaDict:
    """Compose the final sub-schema for ``probe_name`` from its inner builder."""
    inner_body = inner_builder()
    wrapped = _wrap_inner(probe_name, inner_key, inner_body, title)
    _set_additional_props_false_recursively(wrapped)
    return _set_id_and_schema(wrapped, probe_name)


def main() -> None:
    """Imperative shell — map over ``_BUILDERS`` and write each file."""
    for probe_name, inner_key, inner_builder, title in _BUILDERS:
        schema = build_one(probe_name, inner_key, inner_builder, title)
        out_path = _OUT_DIR / f"{probe_name}.schema.json"
        write_schema_file(out_path, schema)


if __name__ == "__main__":
    main()
