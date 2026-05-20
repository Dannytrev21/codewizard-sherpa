"""Phase 7 S2-05 — autouse registry isolation for the property-test package.

`assemble_provenance` dispatches over the module-level `_REGISTRY` in
`codegenie.primitives.vuln_provenance.registry`. The property tests in this
directory register adapters into that dict; this fixture snapshots / clears /
restores it around every test function so a registration never leaks to a
sibling test.

This is a deliberate duplicate of the fixture in
`tests/unit/primitives/vuln_provenance/conftest.py` (S2-01). The two test
trees — `tests/unit/...` and `tests/property/...` — have no common ancestor
`conftest.py` (the repo ships no top-level `tests/conftest.py`), and a pytest
fixture cannot be shared across sibling packages without one. Per S2-05's
implementer note, the localized duplicate is preferred over introducing a
suite-wide top-level conftest — that would make this autouse fixture run for
every test in the ~5500-test suite, a non-surgical change for a 10-line
fixture. The localized conftest also mirrors S2-01's own package-scoped
placement.

Hypothesis note: this fixture is function-scoped, so it runs ONCE per `@given`
test function — NOT once per generated example. Isolating one example from the
next is the responsibility of each property-test body (each clears `_REGISTRY`
in a `finally:` block and asserts it empty at the start). This fixture's job
is isolation from *sibling tests*, not from *sibling examples*.
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
