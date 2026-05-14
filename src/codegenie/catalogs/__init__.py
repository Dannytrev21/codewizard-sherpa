"""Catalog loader — organizational uniqueness as data, not prompts.

Two YAML catalogs ship in Phase 1: ``native_modules.yaml`` (10 seed entries
— the load-bearing input for Phase 7's distroless migration) and
``ci_providers.yaml`` (markers + parser kinds for the five CI providers
Phase 1 supports). Both are validated against a self-schema at first
import and exposed as ``MappingProxyType``-wrapped immutable mappings.

The four module-level constants — :data:`NATIVE_MODULES`,
:data:`CI_PROVIDERS`, :data:`NATIVE_MODULES_CATALOG_VERSION`,
:data:`CI_PROVIDERS_CATALOG_VERSION` — are populated as a side effect of
importing this module. Any failure (``SymlinkRefusedError``,
``SizeCapExceeded``, ``DepthCapExceeded``, ``MalformedYAMLError`` from
``parsers.safe_yaml.load``; schema mismatch from ``jsonschema``; duplicate
entry name) is translated to :class:`codegenie.errors.CatalogLoadError`
and **propagates uncaught** out of the import. The CLI's top-level catch
turns this into exit-code 2 — a load-bearing-invariant violation per arch
§"Edge cases" row 9. There is no soft-degrade to an empty catalog (Rule 12
— Fail Loud).

The loader is a small stable kernel with a registry-via-discriminator: a
single :func:`_load_catalog` body and a ``schema_subkey: Literal[...]``
parameter. Adding a third (or fourth) catalog is a new YAML file + new
``NamedTuple`` + new schema ``$def`` + one new module-scope call —
**zero edits to** :func:`_load_catalog`. Widening the ``Literal`` arms is
the only deliberate edit a new catalog requires inside this module; it is
the type-level review signal that the kernel is being extended (the same
plugin-shape framing as ``parsers/_io.py`` and the parsers' ``_depth``
walker).

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #10 — interface, hard-fail-at-startup,
  ``MappingProxyType`` immutability.
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Data model" — exact ``NativeModuleEntry`` / ``CIProviderEntry``
  shapes (sequence fields ``tuple[str, ...]``; ``parser`` is the
  five-arm ``Literal``).
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0006-native-module-catalog-versioning.md`` (ADR-0006) pins
  ``catalog_version`` + per-entry ``catalog_entry_version`` and the
  catalog YAMLs in ``NodeManifestProbe.declared_inputs`` for cache
  invalidation; ``0008-in-process-parse-caps-not-per-probe-sandbox.md``
  (ADR-0008) requires every YAML read to route through
  ``parsers.safe_yaml.load`` (O_NOFOLLOW + size cap + depth walker);
  ``0004-per-probe-subschema-additional-properties-false.md`` (ADR-0004)
  pins ``additionalProperties: false`` discipline at sub-schema roots.
- ``docs/production/design.md`` §2.6 — organizational uniqueness as
  data, not prompts.

Every typed exception this module raises is a **marker** — a single
positional formatted-message string with no instance state — preserving
the Phase 0 ``test_subclasses_are_markers_only`` invariant.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Literal, NamedTuple, TypeVar, get_type_hints

import structlog
from jsonschema import Draft202012Validator

from codegenie.errors import CatalogLoadError, CodegenieError
from codegenie.parsers import safe_yaml

__all__ = [
    "CIProviderEntry",
    "CI_PROVIDERS",
    "CI_PROVIDERS_CATALOG_VERSION",
    "NATIVE_MODULES",
    "NATIVE_MODULES_CATALOG_VERSION",
    "NativeModuleEntry",
]

_logger = structlog.get_logger(__name__)
_EVENT_CATALOG_LOAD: Final[str] = "probe.catalog.load"
_MAX_CATALOG_BYTES: Final[int] = 1_000_000


class NativeModuleEntry(NamedTuple):
    """One native-module catalog entry; arch §"Data model"."""

    name: str
    requires_node_gyp: bool
    system_deps_required: tuple[str, ...]
    binary_artifacts_glob: tuple[str, ...]
    notes: str
    catalog_entry_version: int


class CIProviderEntry(NamedTuple):
    """One CI-provider catalog entry; arch §"Data model"."""

    name: str
    marker_paths: tuple[str, ...]
    parser: Literal[
        "github_actions",
        "gitlab_ci",
        "jenkins",
        "circleci",
        "azure_pipelines",
    ]


_CATALOG_DIR: Final[Path] = Path(__file__).parent
_LOAD_SCHEMA: dict[str, Any] = json.loads(
    (_CATALOG_DIR / "_schema.json").read_text(encoding="utf-8")
)

_T = TypeVar("_T", bound=NamedTuple)


def _coerce_sequences(raw: Mapping[str, Any], entry_cls: type[_T]) -> dict[str, Any]:
    """Convert ``list[...]`` YAML values to ``tuple[...]`` per ``entry_cls``.

    The NamedTuple's structural immutability depends on sequence fields
    actually being ``tuple`` at runtime. PyYAML decodes a YAML sequence
    to ``list``; this function inspects the target annotation and
    coerces in place.
    """
    hints = get_type_hints(entry_cls)
    out: dict[str, Any] = {}
    for field, value in raw.items():
        target = hints.get(field)
        if target == tuple[str, ...] and isinstance(value, list):
            out[field] = tuple(value)
        else:
            out[field] = value
    return out


def _load_catalog(
    path: Path,
    entry_cls: type[_T],
    schema_subkey: Literal["native_modules", "ci_providers"],
) -> tuple[Mapping[str, _T], int]:
    """Load one catalog file; the kernel — closed for modification.

    Args:
        path: Catalog YAML on disk.
        entry_cls: ``NamedTuple`` subclass to construct per entry.
        schema_subkey: Discriminator selecting a ``$def`` in
            ``_schema.json``. Widening this ``Literal`` is the only
            deliberate edit a new catalog requires inside this module.

    Returns:
        Tuple of the immutable mapping (``MappingProxyType`` over
        ``{entry.name: entry_cls(**...)}``) and the file's
        ``catalog_version``.

    Raises:
        CatalogLoadError: any failure (parser caps, schema mismatch,
            duplicate name) — translated to a marker exception with the
            failing path embedded in ``args[0]``.
    """
    try:
        loaded = safe_yaml.load(path, max_bytes=_MAX_CATALOG_BYTES)
    except CodegenieError as exc:
        raise CatalogLoadError(f"{path}: {exc.args[0]}") from exc

    # Schema validation is the gate; after it passes we trust the shape and
    # widen to ``Any`` so the loop below doesn't fight ``JSONValue``'s union.
    data: dict[str, Any] = dict(loaded)
    schema = _LOAD_SCHEMA["$defs"][schema_subkey]
    errors = list(Draft202012Validator(schema).iter_errors(data))
    if errors:
        first = errors[0]
        raise CatalogLoadError(f"{path}: {first.json_path}: {first.message}") from first

    entries: list[dict[str, Any]] = data["entries"]
    seen: set[str] = set()
    for entry in entries:
        name: str = entry["name"]
        if name in seen:
            raise CatalogLoadError(f"{path}: duplicate name: {name}")
        seen.add(name)

    built: dict[str, _T] = {}
    for raw in entries:
        coerced = _coerce_sequences(raw, entry_cls)
        # ``entry_cls`` is a concrete ``NamedTuple`` subclass (e.g.,
        # ``NativeModuleEntry``) but mypy reads ``type[_T]`` as the
        # ``typing.NamedTuple`` factory and rejects ``**kwargs``.
        built[raw["name"]] = entry_cls(**coerced)  # type: ignore[call-overload]

    catalog_version = int(data["catalog_version"])
    _logger.info(
        _EVENT_CATALOG_LOAD,
        catalog_name=schema_subkey,
        entries=len(built),
        catalog_version=catalog_version,
    )
    return MappingProxyType(built), catalog_version


NATIVE_MODULES, NATIVE_MODULES_CATALOG_VERSION = _load_catalog(
    _CATALOG_DIR / "native_modules.yaml",
    NativeModuleEntry,
    schema_subkey="native_modules",
)
CI_PROVIDERS, CI_PROVIDERS_CATALOG_VERSION = _load_catalog(
    _CATALOG_DIR / "ci_providers.yaml",
    CIProviderEntry,
    schema_subkey="ci_providers",
)
