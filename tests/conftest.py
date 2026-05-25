"""Root test-suite conftest.

Phase-4 S3-03: exposes the :func:`egress_test_loopback` fixture — the **only**
sanctioned opt-in to loopback admission under :class:`EgressGuard`. The
production code path never sets the flag; the fixture is the structural
gate (ADR-0006).

When to request the fixture: a test that needs to dial ``127.0.0.1`` /
``::1`` / ``localhost`` (e.g., binds a throwaway listener and connects to
it). Do NOT request it for tests that mock or monkeypatch the socket
layer; mocked tests never reach :func:`socket.create_connection`.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture
def egress_test_loopback() -> Iterator[None]:
    """Set the thread-scoped loopback opt-in for the duration of the test.

    The ``ContextVar`` is reset on teardown via
    :meth:`EgressGuard.reset_for_test`. Other threads spawned during the
    test run in an empty ``Context`` so the flag is invisible to them
    (the AC-8 isolation guarantee).
    """
    # Lazy import — keeps the root conftest cheap to collect when no test
    # in the run actually requests this fixture.
    from codegenie.fallback.leaf.egress_guard import (
        EgressGuard,
        _test_only_loopback_enabled,
    )

    _test_only_loopback_enabled.set(True)
    try:
        yield
    finally:
        EgressGuard.reset_for_test()
