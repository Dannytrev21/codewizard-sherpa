"""``codegenie.adapters.protocols`` — typed surfaces Phase 3 plugins implement.

This module declares the four ``@runtime_checkable`` ``Protocol`` classes
that Phase 3's first plugin (``plugins/vulnerability-remediation--node--npm/``)
implements:

- :class:`DepGraphAdapter` —
  ``plugins/.../adapters/dep_graph_npm.py``
- :class:`ImportGraphAdapter` —
  ``plugins/.../adapters/import_graph_node.py``
- :class:`ScipAdapter` —
  ``plugins/.../adapters/scip_node.py``
- :class:`TestInventoryAdapter` —
  ``plugins/.../adapters/test_inventory_node.py``

Phase 2 ships **only** the typed surface (02-ADR-0007). No implementations,
no factories, no plugin loader. The structural insurance against drift is
``tests/integration/adapters/test_phase3_handoff_smoke.py`` — landed
skipped in S7-04 and unskipped at Phase 3 entry (S8-04).

PEP 544 §runtime_checkable note: ``isinstance(stub, Protocol)`` checks
attribute *presence*, never *signatures*. Signature drift is a
``mypy --strict`` concern at type-check time, never a runtime concern.

Module purity invariant (S1-03 AC-15): this module imports only stdlib
typing / dataclasses and the sibling ``confidence`` module. No I/O, no
logger, no sibling Phase-2 modules under ``parsers``/``probes``/``exec``.

The four-Protocol set is closed; adding a fifth requires an ADR
amendment to 02-ADR-0007. Production ADR-0032 places the actual adapter
implementations in Phase 3 plugin source trees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NewType, Protocol, runtime_checkable

from codegenie.adapters.confidence import AdapterConfidence

TestId = NewType("TestId", str)
"""``TestId`` — adapter-tier newtype.

Declared here rather than in S1-05's ``identifiers`` module because its
only consumer family is :class:`TestInventoryAdapter`; the architect's
rule is that a newtype belongs where its consumer family lives.
"""


@dataclass(frozen=True, slots=True)
class Occurrence:
    """Raw SCIP-decoded position — mmap-friendly.

    Frozen + ``slots=True`` so Phase 3's ``ScipAdapter`` can construct
    millions of these when walking a SCIP blob without paying the
    per-instance ``__dict__`` overhead. The field set is fixed:
    ``file`` (relative path), ``line`` (1-based), ``col`` (1-based).
    Phase 3 may extend with ``kind: Literal[...]`` via ADR amendment
    if the first real adapter needs it (02-ADR-0007 §Reversibility).
    """

    file: str
    line: int
    col: int


@runtime_checkable
class DepGraphAdapter(Protocol):
    """Cross-package dependency reachability.

    ``consumers(pkg)`` — all internal packages that depend on ``pkg``.
    ``producers(pkg)`` — all internal packages ``pkg`` depends on.
    Both directions are required so the Phase-3 planner can reason
    about blast radius and upstream dependency changes.
    """

    def consumers(self, pkg: str) -> list[str]: ...
    def producers(self, pkg: str) -> list[str]: ...
    def confidence(self) -> AdapterConfidence: ...


@runtime_checkable
class ImportGraphAdapter(Protocol):
    """File-level reverse-import lookup.

    ``reverse_lookup(module)`` — every file that imports ``module``.
    Complements :class:`DepGraphAdapter` (which answers at the *package*
    level) — the Phase-3 planner often needs the finer-grained answer
    to decide if a refactor is safe.
    """

    def reverse_lookup(self, module: str) -> list[str]: ...
    def confidence(self) -> AdapterConfidence: ...


@runtime_checkable
class ScipAdapter(Protocol):
    """Symbol-level SCIP-backed reference lookup.

    ``refs(symbol)`` — every occurrence of ``symbol`` across the
    repository. The SCIP index is the authoritative source for
    "where is this used?" — the Phase-3 planner uses it to estimate
    the cost of a rename or signature change.
    """

    def refs(self, symbol: str) -> list[Occurrence]: ...
    def confidence(self) -> AdapterConfidence: ...


@runtime_checkable
class TestInventoryAdapter(Protocol):
    """Test-discovery: which tests exercise a given symbol.

    ``tests_exercising(symbol)`` — the set of :class:`TestId` values
    that, if they fail, indicate the symbol's behavior changed. The
    Phase-3 validator uses this to scope the regression suite for a
    PR.
    """

    def tests_exercising(self, symbol: str) -> list[TestId]: ...
    def confidence(self) -> AdapterConfidence: ...
