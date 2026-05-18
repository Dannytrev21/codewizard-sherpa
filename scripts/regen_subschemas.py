"""S6-08 — regenerate Layer D + E + G per-probe sub-schemas.

Lands the 16 Step-6 sub-schemas under
``src/codegenie/schema/probes/layer_{d,e,g}/`` from the existing Pydantic
slice models — the model is the source of truth, the JSON Schema tracks
it.

The script is the Layer D/E/G analogue of ``tools/regenerate_probe_schemas.py``
(the Layer B/A regenerator); both share the same post-processing
discipline:

- ``$id`` URI: ``https://codewizard-sherpa.dev/schemas/probes/layer_<d|e|g>/<name>/v0.1.0.json``
- ``$schema``: Draft 2020-12.
- ``additionalProperties: false`` injected at every object node missing
  it (Phase 1 ADR-0004 convention) — walked recursively through
  ``properties`` / ``patternProperties`` / ``$defs`` / ``oneOf`` /
  ``anyOf`` / ``allOf`` / ``items`` / ``prefixItems`` / ``if`` /
  ``then`` / ``else`` / ``not``.

Re-runs are byte-identical (sorted JSON keys); two consecutive
invocations produce no diff.

Run:

    python -m scripts.regen_subschemas

(Or, equivalently, ``python scripts/regen_subschemas.py`` after
``uv pip install -e .[dev]``.)
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

from pydantic import BaseModel

# Add repo root to sys.path so the script can be invoked as a flat file
# from CI without `python -m` (matches sibling tooling).
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))


def _import_all() -> dict[str, tuple[str, type[BaseModel]]]:
    """Lazy-import to avoid module-load side effects at script import time."""
    from codegenie.probes.layer_d.adrs import AdrsSlice
    from codegenie.probes.layer_d.conventions import ConventionsSlice
    from codegenie.probes.layer_d.exceptions import ExceptionsSlice
    from codegenie.probes.layer_d.external_docs import NotOptedInExternalDocsSlice
    from codegenie.probes.layer_d.policy import PolicySlice
    from codegenie.probes.layer_d.repo_config import RepoConfigSlice
    from codegenie.probes.layer_d.repo_notes import RepoNotesSlice
    from codegenie.probes.layer_d.skills_index import SkillsIndexSlice
    from codegenie.probes.layer_e.ownership import OwnershipSlice
    from codegenie.probes.layer_e.service_topology_stub import (
        NotOptedInServiceTopologySlice,
    )
    from codegenie.probes.layer_e.slo_stub import NotOptedInSloSlice
    from codegenie.probes.layer_g.ast_grep import AstGrepSlice
    from codegenie.probes.layer_g.gitleaks import GitleaksSlice
    from codegenie.probes.layer_g.ripgrep_curated import RipgrepCuratedSlice
    from codegenie.probes.layer_g.semgrep import SemgrepSlice
    from codegenie.probes.layer_g.test_coverage_mapping import TestCoverageSlice

    return {
        # name -> (layer, model)
        "skills_index": ("d", SkillsIndexSlice),
        "conventions": ("d", ConventionsSlice),
        "adrs": ("d", AdrsSlice),
        "repo_notes": ("d", RepoNotesSlice),
        "repo_config": ("d", RepoConfigSlice),
        "policy": ("d", PolicySlice),
        "exceptions": ("d", ExceptionsSlice),
        "external_docs": ("d", NotOptedInExternalDocsSlice),
        "ownership": ("e", OwnershipSlice),
        "service_topology_stub": ("e", NotOptedInServiceTopologySlice),
        "slo_stub": ("e", NotOptedInSloSlice),
        "semgrep": ("g", SemgrepSlice),
        "ast_grep": ("g", AstGrepSlice),
        "ripgrep_curated": ("g", RipgrepCuratedSlice),
        "gitleaks": ("g", GitleaksSlice),
        "test_coverage_mapping": ("g", TestCoverageSlice),
    }


_OUT_DIR: Final[Path] = _REPO_ROOT / "src" / "codegenie" / "schema" / "probes"
_ID_STEM: Final[str] = "https://codewizard-sherpa.dev/schemas/probes"
_VERSION: Final[str] = "v0.1.0"
_DRAFT: Final[str] = "https://json-schema.org/draft/2020-12/schema"


def _walk_force_additional_props_false(node: object) -> None:
    """In-place: ensure every object node carries ``additionalProperties: false``."""
    if isinstance(node, dict):
        is_object = (
            node.get("type") == "object"
            or (isinstance(node.get("type"), list) and "object" in node["type"])
            or (node.get("type") is None and ("properties" in node or "patternProperties" in node))
        )
        if is_object and "additionalProperties" not in node:
            node["additionalProperties"] = False
        for key in ("properties", "patternProperties", "$defs"):
            sub = node.get(key)
            if isinstance(sub, dict):
                for v in sub.values():
                    _walk_force_additional_props_false(v)
        for key in ("oneOf", "anyOf", "allOf", "prefixItems"):
            sub = node.get(key)
            if isinstance(sub, list):
                for v in sub:
                    _walk_force_additional_props_false(v)
        for key in ("if", "then", "else", "items", "not"):
            _walk_force_additional_props_false(node.get(key))
        ap = node.get("additionalProperties")
        if isinstance(ap, dict):
            _walk_force_additional_props_false(ap)


def _build_subschema(name: str, layer: str, model: type[BaseModel]) -> dict[str, object]:
    inner: dict[str, object] = dict(model.model_json_schema())
    inner.pop("title", None)
    schema_id = f"{_ID_STEM}/layer_{layer}/{name}/{_VERSION}.json"
    # Layer G probes wrap their slice as ``{<name>: <slice_dict>}`` at the
    # ``schema_slice`` boundary (sibling-pattern reuse — semgrep / gitleaks
    # / ast_grep / ripgrep_curated / test_coverage_mapping). Their
    # sub-schemas must mirror that wrap to validate cleanly. Layer D/E
    # probes emit the slice dict unwrapped; their sub-schemas are the
    # slice shape directly.
    if layer == "g":
        defs: dict[str, object] = {}
        raw_defs = inner.pop("$defs", None)
        if isinstance(raw_defs, dict):
            defs = dict(raw_defs)
        wrapped: dict[str, object] = {
            "type": "object",
            "required": [name],
            "properties": {name: inner},
            "title": f"{model.__name__} ({name}) — Layer G envelope wrap",
            "description": (
                f"Phase-2 Layer G slice produced by the {name} probe. "
                f"The slice carries a single required key '{name}' whose "
                f"value is the typed {model.__name__}; generated from "
                f"{model.__module__}.{model.__name__} by "
                "scripts/regen_subschemas.py."
            ),
        }
        if defs:
            wrapped["$defs"] = defs
        _walk_force_additional_props_false(wrapped)
        return {"$schema": _DRAFT, "$id": schema_id, **wrapped}

    inner["title"] = f"{model.__name__} ({name})"
    inner["description"] = (
        f"Phase-2 Layer {layer.upper()} slice produced by the {name} probe. "
        f"Generated from {model.__module__}.{model.__name__} by "
        f"scripts/regen_subschemas.py; the Pydantic model is the source of truth."
    )
    _walk_force_additional_props_false(inner)
    return {"$schema": _DRAFT, "$id": schema_id, **inner}


def _write(path: Path, schema: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")


def main() -> int:
    builders = _import_all()
    for name, (layer, model) in builders.items():
        schema = _build_subschema(name, layer, model)
        out_path = _OUT_DIR / f"layer_{layer}" / f"{name}.schema.json"
        _write(out_path, schema)
    return 0


def envelope_ref_map() -> dict[str, str]:
    """Public helper: probe name → expected ``$ref`` URI for envelope wiring."""
    builders = _import_all()
    return {
        name: f"{_ID_STEM}/layer_{layer}/{name}/{_VERSION}.json"
        for name, (layer, _model) in builders.items()
    }


_BUILDERS: Callable[[], dict[str, tuple[str, type[BaseModel]]]] = _import_all


if __name__ == "__main__":
    raise SystemExit(main())
