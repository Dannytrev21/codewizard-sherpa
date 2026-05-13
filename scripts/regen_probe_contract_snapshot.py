"""Regenerate ``tests/snapshots/probe_contract.v1.json`` (ADR-0007 / S2-02).

Two artefacts are written:

* ``doc_fingerprint``       — SHA-256 of a whitespace-normalized copy of
  ``docs/localv2.md §4``'s body. Any edit to §4 changes this hash.
* ``structural_signature``  — deterministic dict of class shapes from
  ``codegenie.probes.base``. Any edit to a dataclass field, the ``Probe``
  ABC's class attributes, or its declared methods changes this signature.

``tests/unit/test_probe_contract.py`` imports the three helpers below
(``extract_section_4_body``, ``normalize_and_hash``, ``structural_signature``)
and re-runs them against the live doc + module, comparing both to the
committed snapshot. Either drift fails CI with a message routing the
contributor to ``templates/adr-amendment.md``.

Run with::

    python scripts/regen_probe_contract_snapshot.py

Per ADR-0007 the source of truth is ``localv2.md``; any drift between the
implementation and the doc is *always* resolved by changing code to match
the doc, never the inverse.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import json
import re
import sys
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCALV2_PATH = REPO_ROOT / "docs" / "localv2.md"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "probe_contract.v1.json"
SNAPSHOT_SCHEMA_VERSION = 1

_SECTION_4_HEADING = re.compile(r"^## 4\. The probe contract\s*$", re.MULTILINE)
_NEXT_H2 = re.compile(r"^## ", re.MULTILINE)


def extract_section_4_body(md_text: str) -> str:
    """Return the body of ``## 4. The probe contract`` from ``md_text``.

    The body starts immediately after the heading line and ends at the next
    H2 (``^## ``) line, or at EOF if §4 is the final section.

    Raises ``ValueError`` if §4 is missing or appears more than once.
    Subheadings (``### 4.1 ...``) do NOT terminate the body — only top-level
    ``## `` headings do.
    """
    starts = list(_SECTION_4_HEADING.finditer(md_text))
    if not starts:
        raise ValueError("anchor '## 4. The probe contract' not found in document")
    if len(starts) > 1:
        raise ValueError(
            "multiple '## 4. The probe contract' anchors found "
            f"(found {len(starts)}, expected 1 — duplicate heading)"
        )
    body_start = starts[0].end()
    next_match = _NEXT_H2.search(md_text, pos=body_start)
    body_end = next_match.start() if next_match else len(md_text)
    return md_text[body_start:body_end]


def normalize_and_hash(body: str) -> str:
    """Whitespace-collapse ``body`` and return its SHA-256 hex digest.

    Algorithm is fixed by ``phase-arch-design.md §Open questions Q3``::

        hashlib.sha256(
            re.sub(r"\\s+", " ", body).strip().encode("utf-8")
        ).hexdigest()
    """
    collapsed = re.sub(r"\s+", " ", body).strip()
    return hashlib.sha256(collapsed.encode("utf-8")).hexdigest()


# Map private stdlib submodules introduced by Python's internal reorganizations
# (e.g. Python 3.13 split pathlib into `pathlib._local.Path`) back to their
# public-API location. AC-3 requires the structural signature to be stable
# across the CI matrix (3.11 and 3.12); ``str | None`` was added with PEP 604
# in 3.10 so the project's floor (3.11) is safely past that one. The pathlib
# rename is the load-bearing case today; later entries are added here if a
# future Python release renames another stdlib class in a way the contract
# touches.
_PRIVATE_TO_PUBLIC_MODULE = {
    "pathlib._local.": "pathlib.",
}


def _stable_type_repr(annot: Any) -> str:
    if isinstance(annot, str):
        return annot
    rendered = repr(annot)
    for private_prefix, public_prefix in _PRIVATE_TO_PUBLIC_MODULE.items():
        rendered = rendered.replace(private_prefix, public_prefix)
    return rendered


def _serialize_dataclass_fields(cls: type) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in dataclasses.fields(cls):
        if f.default is not dataclasses.MISSING:
            default: str | None = repr(f.default)
        elif f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
            default = f"<factory:{f.default_factory.__name__}>"
        else:
            default = None
        out.append(
            {
                "name": f.name,
                "type": _stable_type_repr(f.type),
                "default": default,
            }
        )
    return out


def _serialize_class_attributes(cls: type) -> list[dict[str, Any]]:
    annotations = inspect.get_annotations(cls)
    out: list[dict[str, Any]] = []
    for name, annot in annotations.items():
        if name in cls.__dict__:
            default: str | None = repr(cls.__dict__[name])
        else:
            default = None
        out.append(
            {
                "name": name,
                "type": _stable_type_repr(annot),
                "default": default,
            }
        )
    return out


def _serialize_methods(cls: type) -> list[str]:
    return [name for name, val in vars(cls).items() if not name.startswith("_") and callable(val)]


def _ast_decorator_map(module: types.ModuleType) -> dict[str, list[str]]:
    try:
        src_file = inspect.getsourcefile(module)
    except TypeError:
        # `types.ModuleType("foo")` constructed at runtime is "built-in" to
        # `inspect.getfile` — fall back to including every class in
        # `vars(module)` (the synthetic-module path used by the mutation-killer
        # tests in S2-02).
        src_file = None
    if not src_file:
        return {}
    tree = ast.parse(Path(src_file).read_text(encoding="utf-8"))
    return {
        node.name: [ast.unparse(d) for d in node.decorator_list]
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }


def _module_class_names_from_source(module: types.ModuleType) -> set[str] | None:
    try:
        src_file = inspect.getsourcefile(module)
    except TypeError:
        # `types.ModuleType("foo")` constructed at runtime is "built-in" to
        # `inspect.getfile` — fall back to including every class in
        # `vars(module)` (the synthetic-module path used by the mutation-killer
        # tests in S2-02).
        src_file = None
    if not src_file:
        return None
    tree = ast.parse(Path(src_file).read_text(encoding="utf-8"))
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}


def structural_signature(module: types.ModuleType) -> dict[str, Any]:
    """Return a deterministic dict signature of ``module``'s classes.

    Schema (per S2-02 AC-3): keyed by class name in alphabetical order;
    each entry has ``bases``, ``decorators``, ``fields``, ``methods``,
    ``class_attributes``. ``fields`` is populated for ``@dataclass``
    classes (Python 3.11+ insertion order); ``class_attributes`` is
    populated from PEP-526 annotations on non-dataclass classes.

    Classes imported into ``module`` (e.g. ``ABC`` in ``codegenie.probes.base``)
    are filtered out via AST inspection of the module's source. Modules
    constructed at runtime via ``types.ModuleType()`` have no source file
    and fall back to including every class in ``vars(module)``.
    """
    declared = _module_class_names_from_source(module)
    decorator_map = _ast_decorator_map(module)
    members: list[tuple[str, type]] = [
        (n, c)
        for n, c in inspect.getmembers(module, inspect.isclass)
        if declared is None or n in declared
    ]

    signature: dict[str, Any] = {}
    for name, cls in sorted(members, key=lambda kv: kv[0]):
        if dataclasses.is_dataclass(cls):
            fields = _serialize_dataclass_fields(cls)
            class_attributes: list[dict[str, Any]] = []
        else:
            fields = []
            class_attributes = _serialize_class_attributes(cls)
        signature[name] = {
            "bases": [b.__name__ for b in cls.__bases__],
            "decorators": decorator_map.get(name, []),
            "fields": fields,
            "methods": _serialize_methods(cls),
            "class_attributes": class_attributes,
        }
    return signature


def main() -> int:
    """Regenerate the on-disk snapshot. Returns POSIX exit code."""
    src_root = REPO_ROOT / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    import codegenie.probes.base as base  # noqa: PLC0415

    md_text = LOCALV2_PATH.read_text(encoding="utf-8")
    body = extract_section_4_body(md_text)
    snapshot: dict[str, Any] = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "doc_fingerprint": normalize_and_hash(body),
        "structural_signature": structural_signature(base),
    }
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    sys.stdout.write(f"wrote {SNAPSHOT_PATH.relative_to(REPO_ROOT)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
