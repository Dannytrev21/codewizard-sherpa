"""Phase-3 ``TCCM`` + ``ContextQuery`` Pydantic models — plugin-private capability shape.

Phase 3's plugin model needs a richer Task-Class Context Manifest than the
Phase-2 ``codegenie.tccm.model.TCCM`` (probe-set declaration). This module is
the Phase-3 *plugin-private capability* TCCM, ADR-0004 §Consequences' load-
bearing invariant: the kernel ``Plugin`` Protocol stays at four methods, and
task-class-specific knowledge (e.g. ``vuln_index_capabilities``) is declared
here on ``TCCM.provides`` / ``TCCM.requires``.

Two consumers Day 1 — ``BundleBuilder`` (S3-04) iterates ``must_read`` /
``should_read`` / ``may_read`` and the vuln plugin declares
``provides.vuln_index_capabilities``. Neither path crosses into the kernel.

ADRs honored:

- Phase-3 ADR-0004 — plugin-private capabilities live on TCCM ``provides`` /
  ``requires``, NOT on the kernel ``Plugin`` Protocol. Phase 7 distroless
  will declare ``provides.dockerfile_capabilities`` with zero kernel edits.
- Phase-3 ADR-0010 — tagged-union / ``Literal`` discipline for closed state
  sets (``TCCMParseError.reason``).
- Production ADR-0029 — Task-Class Context Manifests: ``must_read`` /
  ``should_read`` / ``may_read`` priority bands.
- Production ADR-0030 — graph-aware context queries: the fixed
  five-primitive set carried by ``_KNOWN_PRIMITIVES``.
- Production ADR-0033 — domain-modeling discipline; smart constructors at
  external boundaries (``ContextQuery.create``).

Module purity (mirrors :mod:`codegenie.result` and :mod:`codegenie.types.errors`):
imports are restricted to ``__future__``, ``re``, ``typing``, ``collections.abc``,
``pydantic``, :mod:`codegenie.types.identifiers`, :mod:`codegenie.result`. No
logger, no I/O, no sibling Phase-3 modules. AST source-scan in
``tests/unit/plugins/test_tccm_module_purity.py`` fences this.

``PrimitiveName`` smart-constructor gap with S1-01 — S1-01's
``parse_primitive_name`` regex (``^[a-z][a-z0-9_]*$``) rejects dotted
primitives like ``scip.refs``. ``ContextQuery.create`` therefore does *not*
call ``parse_primitive_name``; the ``_KNOWN_PRIMITIVES`` membership check IS
the boundary validation and the constructor wraps ``PrimitiveName(s)``
directly after the check (``NewType`` is identity at runtime). A future
amendment to S1-01 may relax the parser; until then the discipline lives
here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from codegenie.result import Err, Ok, Result
from codegenie.types.identifiers import PrimitiveName

__all__ = ("ContextQuery", "TCCM", "TCCMParseError")


# --- Constants ---------------------------------------------------------

_NAMESPACE_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
"""Snake-case grammar for ``provides`` / ``requires`` outer keys, ``provides``
inner keys, and ``requires`` list elements (AC-11 / AC-14)."""

_IMPORT_PATH_RE: Final[re.Pattern[str]] = re.compile(
    r"^[a-zA-Z_][a-zA-Z0-9_.]*:[A-Z][a-zA-Z0-9_]*$"
)
"""``module.path:ClassName`` shape for ``provides`` inner values (AC-11).

Validation is grammatical only — the loader (S2-02 / S2-03) resolves the
``module:Class`` at plugin-load time and surfaces ``PluginRejected(...)``
on import miss (ADR-0004 §Tradeoffs)."""

_PRIMITIVE_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
"""``namespace.name`` dotted-snake shape used by the module-import fence
below (AC-6). Distinct from S1-01's ``parse_primitive_name`` regex which
rejects dots; see module docstring §"PrimitiveName smart-constructor gap"."""

_KNOWN_PRIMITIVES: Final[frozenset[PrimitiveName]] = frozenset(
    {
        PrimitiveName("scip.refs"),
        PrimitiveName("import_graph.reverse_lookup"),
        PrimitiveName("import_graph.transitive_callers"),
        PrimitiveName("dep_graph.consumers"),
        PrimitiveName("test_inventory.tests_exercising"),
    }
)
"""Production ADR-0030 §Initial query primitives — exactly five names. The
set is closed by design: adding a 6th requires an ADR-0030 amendment + an
edit to the AC-5 exact-set pin test (forces a paired review)."""

# Module-import fence (AC-6) — every known primitive must match the grammar.
# A drift (e.g. someone appends ``"scip"`` without the namespace dot) fails
# import. ``raise AssertionError(...)`` per the ``forbidden-patterns`` hook;
# bare ``assert`` is banned repo-wide.
for _p in _KNOWN_PRIMITIVES:
    if not _PRIMITIVE_RE.fullmatch(_p):
        raise AssertionError(f"primitive grammar drift in _KNOWN_PRIMITIVES: {_p!r}")
del _p


# --- Error model -------------------------------------------------------


class TCCMParseError(BaseModel):
    """Boundary-parse failure for :meth:`ContextQuery.create`.

    Frozen Pydantic ``BaseModel`` (mirrors S1-01's
    :class:`codegenie.types.errors.ParseError` precedent), NOT a
    :class:`codegenie.errors.CodegenieError` subclass — the markers-only
    discipline forbids fields on ``CodegenieError`` subclasses, and we need
    the ``reason`` / ``details`` payload at the call site.

    The ``reason`` set is closed by ADR-0010 §Tagged-union / ``Literal``
    discipline; extending it requires an ADR amendment.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: Literal["unknown_primitive", "negative_max_files"]
    details: dict[str, str | int] = {}


# --- ContextQuery ------------------------------------------------------


class ContextQuery(BaseModel):
    """A single graph-aware context-query primitive (ADR-0030).

    Fields:

    - ``primitive`` — one of the five ADR-0030 names; carries the closed-set
      invariant. ``@field_validator`` enforces membership.
    - ``args`` — primitive arguments, restricted to JSON primitives + list-of-str
      (no ``Any``, no nested dicts — see AC-9 rationale).
    - ``fallback`` — ADR-0008 declared-fallback seam; fires only on
      ``AdapterConfidence.Degraded | Unavailable`` at dispatch time. Phase 3
      defines the type; the dispatch policy lives in BundleBuilder (S3-04).
    - ``max_files`` — ADR-0030 bound; ``None`` means uncapped.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    primitive: PrimitiveName
    args: dict[str, str | int | bool | list[str]]
    fallback: ContextQuery | None = None
    max_files: int | None = None

    @field_validator("primitive")
    @classmethod
    def _primitive_in_known_set(cls, v: str) -> PrimitiveName:
        if v not in _KNOWN_PRIMITIVES:
            raise ValueError(f"unknown primitive: {v!r}")
        return PrimitiveName(v)

    @field_validator("max_files")
    @classmethod
    def _max_files_positive_or_none(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError(f"max_files must be positive or None: {v!r}")
        return v

    @classmethod
    def create(
        cls,
        primitive: str,
        args: dict[str, str | int | bool | list[str]],
        *,
        fallback: ContextQuery | None = None,
        max_files: int | None = None,
    ) -> Result[ContextQuery, TCCMParseError]:
        """Smart-constructor surface for the two enumerated parse failures.

        Returns ``Err(TCCMParseError(...))`` for the two cases the schema
        cannot express ergonomically (unknown primitive + non-positive
        ``max_files``). Pydantic ``ValidationError`` from any other source
        (malformed ``args`` value, ``extra='forbid'`` rejection, …)
        propagates to the caller — ``create`` is NOT a catch-all.
        """

        if primitive not in _KNOWN_PRIMITIVES:
            return Err(
                error=TCCMParseError(
                    reason="unknown_primitive",
                    details={"primitive": primitive},
                )
            )
        if max_files is not None and max_files <= 0:
            return Err(
                error=TCCMParseError(
                    reason="negative_max_files",
                    details={"max_files": max_files},
                )
            )
        # PrimitiveName is identity at runtime; direct wrap is intentional
        # (see module docstring §"PrimitiveName smart-constructor gap" + AC-7).
        return Ok(
            value=cls(
                primitive=PrimitiveName(primitive),
                args=args,
                fallback=fallback,
                max_files=max_files,
            )
        )


# --- TCCM --------------------------------------------------------------


def _validate_namespace_keys(value: Mapping[str, object], *, where: str) -> None:
    """Raise ``ValueError`` if any outer key fails the namespace grammar.

    AC-17 — single owner of ``_NAMESPACE_RE.fullmatch``. Both ``provides``
    and ``requires`` route through this helper. The loop walks ALL keys so
    the second-position offender is also surfaced (AC-12 — mutation pin
    against an early ``return`` after the first failure).
    """

    bad: list[str] = []
    for key in value:
        if not _NAMESPACE_RE.fullmatch(key):
            bad.append(key)
    if bad:
        raise ValueError(f"{where}: invalid namespace keys: {bad!r}")


class TCCM(BaseModel):
    """Phase-3 Task-Class Context Manifest (plugin-private capability shape).

    Read together with the Phase-2 ``codegenie.tccm.model.TCCM`` — different
    namespace, different shape, different consumer. Per ADR-0004 the two
    are intentionally distinct; do NOT unify.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    must_read: list[ContextQuery]
    should_read: list[ContextQuery] = []
    may_read: list[ContextQuery] = []
    provides: dict[str, dict[str, str]] = {}
    requires: dict[str, list[str]] = {}

    @field_validator("provides")
    @classmethod
    def _validate_provides(cls, v: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        _validate_namespace_keys(v, where="provides")
        for ns, inner in v.items():
            # Capability-name grammar — route through the same helper so
            # ``_NAMESPACE_RE`` has exactly one call site (AC-17).
            _validate_namespace_keys(inner, where=f"provides[{ns!r}]")
            for cap_name, import_path in inner.items():
                if not _IMPORT_PATH_RE.fullmatch(import_path):
                    raise ValueError(
                        f"provides[{ns!r}][{cap_name!r}]: invalid import path {import_path!r}"
                    )
        return v

    @field_validator("requires")
    @classmethod
    def _validate_requires(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        _validate_namespace_keys(v, where="requires")
        for ns, names in v.items():
            # List-element grammar — wrap as an ad-hoc mapping so the
            # namespace helper remains the SOLE owner of ``_NAMESPACE_RE``
            # use (AC-17). Duplicate names in the list collapse, but the
            # grammar check is per-name and order-independent.
            as_map: dict[str, None] = {n: None for n in names}
            _validate_namespace_keys(as_map, where=f"requires[{ns!r}]")
        return v


# Resolve the recursive forward-ref ``fallback: ContextQuery | None``.
ContextQuery.model_rebuild()
