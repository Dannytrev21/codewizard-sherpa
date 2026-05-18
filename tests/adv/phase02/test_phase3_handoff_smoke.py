"""Phase-2 → Phase-3 adapter-Protocol handoff trip-wire — Gap 1, 02-ADR-0007.

This test is landed **skipped**. The Phase-3 author finds it on first
repo scan via::

    grep -r "enabled when Phase 3 plugin lands" tests/

and unskips it at the Phase-3-entry-gate review (S8-04 files the
follow-up issue that nominates the unskip).

When unskipped, the body asserts that the four ``@runtime_checkable``
``Protocol`` classes from S1-03 still live at their pinned import paths
and that their method signatures match the frozen tuple captured below.
A drift on any signature requires an **ADR amendment to 02-ADR-0006 /
02-ADR-0007**, NOT a silent edit to the Protocol — the failure message
points to the ADR.

Type-system trip-wire (AC-25):

A module-level helper ``_frozen_dep_graph_signature`` (and three
siblings) lives **outside** the skipped body. ``mypy --strict``
type-checks them on every CI run. Any S1-03 signature change makes
mypy fail on **this file** at the next CI run — before unskip, before
Phase 3 lands. The frozen-signature assertion inside the skipped test
catches drift that mypy cannot see (e.g., return-type widening).

DO NOT remove the skip marker without:

1. Filing an ADR amendment to 02-ADR-0006 / 02-ADR-0007.
2. Updating ``_FROZEN_S1_03_SIGNATURES`` below to match Phase-3's
   first plugin's expectations.
3. Adding a row to the appropriate phase ADR table.

The skip exists so a contract change is a deliberate event, not an
incremental drift.
"""

from __future__ import annotations

from typing import Final

import pytest

from codegenie.adapters.confidence import AdapterConfidence, Trusted, Unavailable

# ``TestInventoryAdapter`` is imported under an aliased name so pytest's
# collection heuristic ("classes starting with Test") does not warn about
# the Protocol class. The aliased name preserves the import contract; the
# original name is asserted via getattr at runtime below.
from codegenie.adapters.protocols import (
    DepGraphAdapter,
    ImportGraphAdapter,
    Occurrence,
    ScipAdapter,
    TestId,
)
from codegenie.adapters.protocols import TestInventoryAdapter as _TestInventoryAdapter

# ---------------------------------------------------------------------------
# Frozen signature tuple — capture from src/codegenie/adapters/protocols.py
# at story-write time. Drift on any signature → test fails at unskip.
# ---------------------------------------------------------------------------

_FROZEN_S1_03_SIGNATURES: Final[tuple[tuple[str, str, str], ...]] = (
    ("DepGraphAdapter", "consumers", "(self, pkg: str) -> list[str]"),
    ("DepGraphAdapter", "producers", "(self, pkg: str) -> list[str]"),
    ("DepGraphAdapter", "confidence", "(self) -> AdapterConfidence"),
    ("ImportGraphAdapter", "reverse_lookup", "(self, module: str) -> list[str]"),
    ("ImportGraphAdapter", "confidence", "(self) -> AdapterConfidence"),
    ("ScipAdapter", "refs", "(self, symbol: str) -> list[Occurrence]"),
    ("ScipAdapter", "confidence", "(self) -> AdapterConfidence"),
    ("TestInventoryAdapter", "tests_exercising", "(self, symbol: str) -> list[TestId]"),
    ("TestInventoryAdapter", "confidence", "(self) -> AdapterConfidence"),
)


# ---------------------------------------------------------------------------
# Type-system trip-wires — AC-25.
#
# These helpers live at module level so ``mypy --strict`` type-checks them
# even while the runtime test below is skipped. Any S1-03 Protocol
# signature change makes mypy fail on THIS file at the next CI run — that
# is the contract trip-wire firing through the type system, well before
# Phase 3 unskips the smoke test.
# ---------------------------------------------------------------------------


def _frozen_dep_graph_signature(adapter: DepGraphAdapter) -> None:
    """mypy trip-wire pinning ``DepGraphAdapter``'s S1-03 surface."""
    consumers: list[str] = adapter.consumers("pkg-a")
    producers: list[str] = adapter.producers("pkg-a")
    conf: AdapterConfidence = adapter.confidence()
    # ``len`` so the values are not unused-locals (mypy --strict would warn
    # nothing here, but ruff's F841 might complain on import; using them
    # in a no-op assertion keeps the intent explicit).
    assert isinstance(consumers, list)
    assert isinstance(producers, list)
    assert conf is not None


def _frozen_import_graph_signature(adapter: ImportGraphAdapter) -> None:
    """mypy trip-wire pinning ``ImportGraphAdapter``'s S1-03 surface."""
    files: list[str] = adapter.reverse_lookup("some.module")
    conf: AdapterConfidence = adapter.confidence()
    assert isinstance(files, list)
    assert conf is not None


def _frozen_scip_signature(adapter: ScipAdapter) -> None:
    """mypy trip-wire pinning ``ScipAdapter``'s S1-03 surface."""
    refs: list[Occurrence] = adapter.refs("symbol")
    conf: AdapterConfidence = adapter.confidence()
    assert isinstance(refs, list)
    assert conf is not None


def _frozen_test_inventory_signature(adapter: _TestInventoryAdapter) -> None:
    """mypy trip-wire pinning ``TestInventoryAdapter``'s S1-03 surface."""
    tests: list[TestId] = adapter.tests_exercising("symbol")
    conf: AdapterConfidence = adapter.confidence()
    assert isinstance(tests, list)
    assert conf is not None


# ---------------------------------------------------------------------------
# Minimal in-test stubs used in the runtime-conformance assertion.
# These stubs structurally implement each Protocol; ``isinstance(stub,
# Protocol)`` is the Phase-3-author's smoke confirmation that the
# Protocols are still ``@runtime_checkable``.
# ---------------------------------------------------------------------------


class _DepGraphStub:
    def consumers(self, pkg: str) -> list[str]:
        return [pkg]

    def producers(self, pkg: str) -> list[str]:
        return [pkg]

    def confidence(self) -> AdapterConfidence:
        return Trusted(rationale="phase3-handoff-smoke")


class _ImportGraphStub:
    def reverse_lookup(self, module: str) -> list[str]:
        return [module]

    def confidence(self) -> AdapterConfidence:
        return Trusted(rationale="phase3-handoff-smoke")


class _ScipStub:
    def refs(self, symbol: str) -> list[Occurrence]:
        return [Occurrence(file="x.py", line=1, col=1)]

    def confidence(self) -> AdapterConfidence:
        return Unavailable(rationale="phase3-handoff-smoke")


class _TestInventoryStub:
    def tests_exercising(self, symbol: str) -> list[TestId]:
        return [TestId(f"test::{symbol}")]

    def confidence(self) -> AdapterConfidence:
        return Trusted(rationale="phase3-handoff-smoke")


def _normalize_signature(sig: str) -> str:
    """Normalize a signature string for frozen-tuple comparison.

    Collapses whitespace and strips the single-quote markers
    ``inspect.signature`` introduces when the source module uses
    ``from __future__ import annotations`` (PEP 563 string-form
    annotations are surfaced as quoted strings).
    """
    return " ".join(sig.replace("'", "").split())


@pytest.mark.skip(
    reason=(
        "enabled when Phase 3 plugin lands — see "
        "docs/phases/02-context-gather-layers-b-g/ADRs/"
        "0007-no-plugin-loader-in-phase-2.md and "
        "docs/phases/02-context-gather-layers-b-g/High-level-impl.md "
        "§Step 7 Phase-3-handoff bullet"
    )
)
def test_phase3_adapter_handoff_smoke() -> None:
    """AC-21 / AC-22 / AC-23 / AC-24 — Phase-3 adapter handoff smoke.

    Unskip this test when Phase 3's first plugin
    (``plugins/vulnerability-remediation--node--npm/``) lands. If the
    first plugin's adapters do not satisfy the four frozen Protocol
    signatures below, **DO NOT silently change the Protocols** — file
    an ADR amendment to 02-ADR-0006 / 02-ADR-0007 first, update
    ``_FROZEN_S1_03_SIGNATURES`` accordingly, then unskip and re-run.
    """
    import inspect

    # 1. The four Protocols are importable at their pinned paths
    #    (the module-level imports above will have ImportError'd if not).
    assert DepGraphAdapter is not None
    assert ImportGraphAdapter is not None
    assert ScipAdapter is not None
    assert _TestInventoryAdapter is not None
    assert _TestInventoryAdapter.__name__ == "TestInventoryAdapter"

    # 2. ``AdapterConfidence`` discriminated-union has its three documented
    #    variants. We import two here; ``Degraded`` is imported defensively
    #    inside the test to keep the module-level surface small.
    from codegenie.adapters.confidence import Degraded

    assert Trusted is not None
    assert Degraded is not None
    assert Unavailable is not None

    # 3. Runtime structural conformance via ``isinstance(stub, Protocol)``.
    assert isinstance(_DepGraphStub(), DepGraphAdapter)
    assert isinstance(_ImportGraphStub(), ImportGraphAdapter)
    assert isinstance(_ScipStub(), ScipAdapter)
    assert isinstance(_TestInventoryStub(), _TestInventoryAdapter)

    # 4. Frozen-signature drift detection (AC-23). Any S1-03 signature
    #    change will surface here as a string-mismatch with the named
    #    Protocol + method.
    protocol_by_name: dict[str, type] = {
        "DepGraphAdapter": DepGraphAdapter,
        "ImportGraphAdapter": ImportGraphAdapter,
        "ScipAdapter": ScipAdapter,
        "TestInventoryAdapter": _TestInventoryAdapter,
    }
    for proto_name, method_name, frozen_sig in _FROZEN_S1_03_SIGNATURES:
        proto = protocol_by_name[proto_name]
        method = getattr(proto, method_name)
        live_sig = _normalize_signature(str(inspect.signature(method)))
        # ``inspect.signature`` does not include ``self`` for unbound
        # Protocol methods retrieved via attribute access in some Python
        # versions; normalize both sides for the comparison.
        live_norm = live_sig if live_sig.startswith("(self") else f"(self, {live_sig[1:]}"
        frozen_norm = _normalize_signature(frozen_sig)
        # Compare the method-name + signature; mismatch points at the ADR.
        assert live_norm == frozen_norm or live_sig == frozen_norm, (
            f"S1-03 Protocol drift detected on {proto_name}.{method_name}: "
            f"live signature {live_norm!r} does not match frozen "
            f"{frozen_norm!r}. DO NOT silently change the Protocol — file "
            f"an ADR amendment to 02-ADR-0006 / 02-ADR-0007 and update "
            f"_FROZEN_S1_03_SIGNATURES in this test file before unskipping."
        )
