"""AC-8 / AC-17 — thread isolation of the loopback opt-in.

A freshly-started :class:`threading.Thread` runs in an empty
``contextvars.Context``. So a value ``.set()`` in the main thread by the
:func:`egress_test_loopback` fixture is invisible to the worker — the
worker sees ``default=False`` and raises :class:`EgressViolation` when it
attempts loopback. This is the AC-8 isolation guarantee, for free, with
no extra plumbing.

The test must **not** copy or propagate the context across the thread
boundary; doing so would defeat the isolation.
"""

from __future__ import annotations

import socket
import threading

import pytest

from codegenie.fallback.leaf.egress_guard import EgressGuard, EgressViolation

pytestmark = pytest.mark.phase04_adv


@pytest.fixture(autouse=True)
def _install_egress_guard() -> None:
    EgressGuard.install()


def test_loopback_flag_is_invisible_to_worker_thread(
    egress_test_loopback: None,  # noqa: ARG001 — fixture sets flag in main thread
) -> None:
    results: list[str] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            socket.create_connection(("127.0.0.1", 8080), timeout=1)
            results.append("admitted")
        except EgressViolation:
            results.append("blocked")
        except BaseException as exc:  # noqa: BLE001 — surface anything unexpected
            errors.append(exc)

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=5)  # join BEFORE the fixture resets so the assertion is meaningful

    assert not errors, f"worker raised unexpected error: {errors!r}"
    assert results == ["blocked"], (
        f"worker thread must see EgressViolation; got {results!r}. "
        "If 'admitted', the ContextVar leaked across the thread boundary — "
        "isolation is broken."
    )
