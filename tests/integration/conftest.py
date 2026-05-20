"""Phase 7 S3-01 — autouse test isolation for the provenance adapter registry.

`tests/integration/test_provenance_assembly_via_plugins.py` drives a full
plugin load, whose `@register_provenance_adapter` side effects mutate the
module-level `_REGISTRY`. This fixture snapshots `_REGISTRY` at test start,
clears it, yields, and restores the snapshot on teardown so adapter
registrations never bleed between integration tests.

It is the integration-tree mirror of
`tests/unit/primitives/vuln_provenance/conftest.py` (S2-01) and the
property-suite copy under `tests/property/vuln_provenance/conftest.py`
(S2-05) — same snapshot/clear/restore discipline, same `autouse` policy
(Phase 7 ADR-0007 §Consequences). It is harmless for integration tests
that never touch the provenance registry: the snapshot is empty and the
restore is a no-op.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from codegenie.primitives.vuln_provenance import registry as _registry_mod


@pytest.fixture(autouse=True)
def provenance_registry_reset() -> Generator[None, None, None]:
    """Snapshot/clear/restore ``_REGISTRY`` around every integration test."""
    snapshot = _registry_mod._REGISTRY.copy()
    try:
        _registry_mod._REGISTRY.clear()
        yield
    finally:
        _registry_mod._REGISTRY.clear()
        _registry_mod._REGISTRY.update(snapshot)
