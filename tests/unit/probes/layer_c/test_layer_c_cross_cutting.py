"""S5-03 — cross-cutting tests for Layer C marker probes.

Covers AC-V1 (sibling-slice access via read_raw_slices only), AC-V3
(requires-is-metadata-only docstring grep), AC-V12 (LOC budget), and
the sub-schema rejection test per probe.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

_REPO_ROOT = Path(__file__).resolve().parents[4]
_LAYER_C_DIR = _REPO_ROOT / "src" / "codegenie" / "probes" / "layer_c"
_SCHEMA_DIR = _REPO_ROOT / "src" / "codegenie" / "schema" / "probes" / "layer_c"

_SIBLING_READERS = ("entrypoint.py", "shell_usage.py", "certificate.py")
_FOUR_MODULES = ("dockerfile.py", *_SIBLING_READERS)


# ---------------------------------------------------------------------------
# AC-V1 — read_raw_slices is the sole sibling-slice access path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", _SIBLING_READERS)
def test_sibling_slice_reader_uses_read_raw_slices_exactly_once(module_name: str) -> None:
    """AC-V1 — exactly one inbound import of read_raw_slices; no ctx.sibling_slices."""
    src = (_LAYER_C_DIR / module_name).read_text()
    tree = ast.parse(src)
    matching_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "codegenie.probes.layer_b.index_health"
        and any(alias.name == "read_raw_slices" for alias in (node.names or []))
    ]
    assert len(matching_imports) == 1, f"{module_name}: read_raw_slices import count != 1"
    # `ctx.sibling_slices` must not appear — that attribute does not exist on
    # the frozen ProbeContext (Phase 0 ADR-0007).
    assert not re.search(r"ctx\.sibling_slices", src), (
        f"{module_name} references a phantom ctx.sibling_slices attribute"
    )
    # No direct disk reads into .codegenie/context/raw/.
    assert ".codegenie/context/raw" not in src or "read_raw_slices" in src, (
        f"{module_name} appears to read raw artifacts without the helper"
    )


# ---------------------------------------------------------------------------
# AC-V3 — `requires is metadata-only` docstring substring grep
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", _SIBLING_READERS)
def test_requires_metadata_only_docstring_present(module_name: str) -> None:
    """AC-V3 — module docstring records 'requires' is metadata-only."""
    src = (_LAYER_C_DIR / module_name).read_text()
    tree = ast.parse(src)
    doc = ast.get_docstring(tree) or ""
    # Normalize whitespace per L8 (docstrings wrap at col 80).
    normalized = " ".join(doc.split())
    # Tolerate `` ``requires`` is metadata-only `` and `requires is metadata-only`.
    flat = normalized.replace("`", "")
    assert "requires is metadata-only" in flat


# ---------------------------------------------------------------------------
# AC-V12 — LOC budget per module (≤ 100 source lines, no docstrings/comments)
# ---------------------------------------------------------------------------


def _count_source_lines(path: Path) -> int:
    """Return non-blank, non-comment, non-docstring source-line count.

    Strips module-level + class- and function-level docstrings via AST so the
    count matches the Test-Quality discipline ('docstrings count as comments').
    """
    src = path.read_text()
    tree = ast.parse(src)
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            doc_node: ast.AST | None = None
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                doc_node = body[0]
            if doc_node is not None and hasattr(doc_node, "lineno") and hasattr(doc_node, "end_lineno"):
                end = doc_node.end_lineno or doc_node.lineno
                for n in range(doc_node.lineno, end + 1):
                    docstring_lines.add(n)
    count = 0
    for idx, raw in enumerate(src.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if idx in docstring_lines:
            continue
        count += 1
    return count


@pytest.mark.parametrize("module_name", _FOUR_MODULES)
def test_loc_budget_per_module(module_name: str) -> None:
    """AC-V12 — each of the four modules ≤ 100 source lines (no slack)."""
    n = _count_source_lines(_LAYER_C_DIR / module_name)
    assert n <= 100, f"{module_name}: {n} source lines exceeds 100-LOC budget"


# ---------------------------------------------------------------------------
# Sub-schema rejection — every layer_c sub-schema rejects an extra field
# ---------------------------------------------------------------------------


_SUBSCHEMA_FIXTURES = {
    "dockerfile.schema.json": {
        "dockerfile": {"dockerfiles": [], "confidence": "unavailable"},
    },
    "entrypoint.schema.json": {
        "entrypoint": {"entrypoints": [], "confidence": "high"},
    },
    "shell_usage.schema.json": {
        "shell_usage": {
            "static": {
                "final_stage_entrypoint_form": "absent",
                "final_stage_cmd_form": "absent",
                "final_stage_run_commands": [],
            },
            "confidence": "high",
        },
    },
    "certificate.schema.json": {
        "certificate": {
            "cert_paths_read": [],
            "certificate_source": "absent",
            "confidence": "high",
        },
    },
}


@pytest.mark.parametrize("filename, fixture", list(_SUBSCHEMA_FIXTURES.items()))
def test_subschema_validates_clean_then_rejects_extra_field(
    filename: str, fixture: dict[str, object]
) -> None:
    schema = json.loads((_SCHEMA_DIR / filename).read_text())
    Draft202012Validator(schema).validate(fixture)
    # Mutate: drop in an extra root-level field.
    bad = {**fixture, "unknown_field": "x"}
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate(bad)


# ---------------------------------------------------------------------------
# Sub-schema structural — `additionalProperties: false` at every object node
# ---------------------------------------------------------------------------


def _walk_object_nodes_with_properties(node: object) -> list[dict[str, object]]:
    """Yield every JSON-Schema object node that declares `properties` (a closed,
    field-shaped object). Free-form objects without `properties` are excluded
    — they are dict-typed maps and `additionalProperties: <schema>` is the
    correct shape for them.
    """
    out: list[dict[str, object]] = []
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            out.append(node)
        for v in node.values():
            out.extend(_walk_object_nodes_with_properties(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_walk_object_nodes_with_properties(v))
    return out


@pytest.mark.parametrize("filename", list(_SUBSCHEMA_FIXTURES.keys()))
def test_subschema_additional_properties_false_at_every_object_node(filename: str) -> None:
    """Phase 1 ADR-0004 — every closed-object node sets additionalProperties:false."""
    schema = json.loads((_SCHEMA_DIR / filename).read_text())
    for obj in _walk_object_nodes_with_properties(schema):
        assert obj.get("additionalProperties") is False, (
            f"{filename}: closed-object node missing additionalProperties:false: "
            f"{obj.get('title') or list(obj.get('properties', {}).keys())[:3]}"
        )
