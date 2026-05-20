"""Phase 7 S2-01 — autouse test isolation for the provenance adapter registry.

Every test in ``tests/unit/primitives/vuln_provenance/`` runs against a fresh
``_REGISTRY``. The fixture snapshots whatever is in the dict at test start
(typically empty, but production plugin imports could populate it), clears it,
yields, and restores the snapshot on teardown. Mirrors Phase 2's
``freshness`` registry isolation pattern (per Phase 7 ADR-0007 §Consequences).

The fixture is function-scoped + autouse — every test in the package sees a
fresh registry without naming the fixture explicitly. This is the policy
documented in S2-01 AC-9.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from codegenie.primitives.vuln_provenance import registry as _registry_mod


@pytest.fixture(autouse=True)
def provenance_registry_reset() -> Generator[None, None, None]:
    """Snapshot/clear/restore ``_REGISTRY`` around every test in this package."""
    snapshot = _registry_mod._REGISTRY.copy()
    try:
        _registry_mod._REGISTRY.clear()
        yield
    finally:
        _registry_mod._REGISTRY.clear()
        _registry_mod._REGISTRY.update(snapshot)
