"""Phase-4 S3-03 — :class:`EgressGuard`, the process-wide
``socket.create_connection`` wrapper that admits only
``api.anthropic.com:443`` and rejects every other host (including loopback)
unless an explicit test-only opt-in is set via a thread-scoped
``contextvars.ContextVar``.

This is the **belt** to :class:`AnthropicLeafAdapter`'s suspenders: every
physical SDK attempt is also wrapped in ``egress_guard.pinned_to(...)``,
but ``EgressGuard`` is what catches a transitive dep that opens a socket
*outside* the adapter's ``pinned_to`` envelope. ADR-0005 §Defense in depth.

Two ADR-locked decisions shape the surface:

* **No SPKI pin** (ADR-0005). ``api.anthropic.com:443`` is the host-level
  allowlist; TLS uses the system trust store. SPKI pinning was rejected as
  self-DOS on Anthropic CA rotation.
* **No production loopback carve-out** (ADR-0006). ``127.0.0.1`` / ``::1`` /
  ``localhost`` are rejected by default. The only opt-in is the pytest
  fixture :func:`egress_test_loopback` (``tests/conftest.py``), which sets
  the module-level :data:`_test_only_loopback_enabled` ``ContextVar`` to
  ``True``. There is no env-var escape, no boolean parameter, no module
  constant. The ``ContextVar`` propagates across ``await`` boundaries
  within one thread *and* is invisible to freshly-started
  :class:`threading.Thread` workers (the worker runs in an empty
  ``Context``) — which is exactly the AC-8 isolation guarantee, for free.

The module-level :data:`_BASE_ALLOWLIST` is the extension seam: Phase 7's
``cgr.dev`` is one added row under an additive ADR amendment, not a new
mechanism.

We wrap ``socket.create_connection`` only — :meth:`socket.socket.connect`
called by a C extension bypasses us. That residual is documented in
ADR-0005 §Threat model and mitigated structurally by the
``import-linter`` restriction on native-extension deps (S1-06).
"""

from __future__ import annotations

import contextlib
import contextvars
import socket
from collections.abc import AsyncIterator
from typing import Any, Final

__all__ = (
    "EgressGuard",
    "EgressViolation",
    "_test_only_loopback_enabled",
)

# --- Module state -----------------------------------------------------------

_test_only_loopback_enabled: Final[contextvars.ContextVar[bool]] = contextvars.ContextVar(
    "_test_only_loopback_enabled", default=False
)
"""The pytest-fixture-set opt-in to loopback admission (ADR-0006).

Production code paths never touch this. The :class:`ContextVar` shape is
load-bearing for two properties:

* Propagates across ``await`` boundaries — Phase-4 adapter calls are
  ``async``.
* A freshly-started :class:`threading.Thread` runs in an *empty*
  ``Context`` — so a value ``.set()`` in thread A is invisible to thread
  B without any extra plumbing (the AC-8 isolation guarantee).
"""

_BASE_ALLOWLIST: Final[frozenset[tuple[str, int]]] = frozenset({("api.anthropic.com", 443)})
"""The base ``(host, port)`` allowlist. Phase 7's ``cgr.dev`` is one added
row under an additive ADR amendment (production ADR-0020); it is not a new
mechanism. Read by the pure helper :func:`_is_admitted`."""

_LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "::1", "localhost"})
"""The three host forms that the :func:`egress_test_loopback` fixture
admits. Any other host (e.g. a private-RFC1918 address like ``10.0.0.1``)
remains rejected even when the flag is set — the fixture is a loopback
escape, not a generic "tests can dial anything" escape."""

_installed: bool = False
"""Idempotency flag for :meth:`EgressGuard.install`."""

_ORIGINAL_CREATE_CONNECTION: Any = None
"""Captured once at first :meth:`EgressGuard.install`. The wrapper always
delegates here, even if ``socket.create_connection`` is re-bound later;
:attr:`socket.create_connection.__wrapped__` also points here so AC-2's
idempotency assertion has a stable target."""


# --- Exception --------------------------------------------------------------


class EgressViolation(Exception):
    """A socket attempt to a non-allowlisted ``(host, port)`` was blocked.

    Reserved for **well-formed but not-allowlisted** hosts (AC-12). Malformed
    inputs (e.g. a bad ``host:port`` string passed to
    :meth:`EgressGuard.pinned_to`) raise :class:`ValueError` instead
    (AC-28).
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        super().__init__(
            f"egress denied: {host}:{port} is not in the codegenie allowlist "
            f"(api.anthropic.com:443 is the only Phase-4 host)"
        )


# --- Pure helpers (functional core, AC-27) ----------------------------------


def _is_admitted(host: str, port: int, *, loopback_enabled: bool) -> bool:
    """Decide whether ``(host, port)`` is admitted.

    Pure: no I/O, no ``ContextVar`` read. ``loopback_enabled`` is passed
    in by the imperative shell (:func:`_wrap_create_connection`). The
    base allowlist is consulted first so a Phase-7 amendment that adds a
    ``(loopback-looking host, port)`` row would still admit it without
    needing the flag.
    """
    if (host, port) in _BASE_ALLOWLIST:
        return True
    if loopback_enabled and host in _LOOPBACK_HOSTS:
        return True
    return False


def _parse_host_port(spec: str) -> tuple[str, int]:
    """Split a ``"host:port"`` string into a ``(host, int)`` tuple.

    AC-28 — malformed inputs raise :class:`ValueError` at parse time, not
    :class:`EgressViolation`. The exception class is the discriminator
    between "the caller passed garbage" and "well-formed host is not in
    the allowlist".
    """
    if ":" not in spec:
        raise ValueError(f"pinned_to expects 'host:port'; got {spec!r} (no colon)")
    # rsplit so IPv6 literals like ``[::1]:443`` could land later without
    # an API change (Phase 4 has none in the allowlist; AC-1 future-proofs).
    host, _, port_str = spec.rpartition(":")
    if not host:
        raise ValueError(f"pinned_to expects 'host:port'; got {spec!r} (empty host)")
    try:
        port = int(port_str)
    except ValueError as exc:
        raise ValueError(f"pinned_to expects 'host:port' with integer port; got {spec!r}") from exc
    return host, port


# --- Wrapper (imperative shell) ---------------------------------------------


def _wrap_create_connection(original: Any) -> Any:
    """Build the ``socket.create_connection`` wrapper around ``original``.

    The wrapper is the imperative shell: it reads the
    :data:`_test_only_loopback_enabled` ``ContextVar`` once, delegates the
    allow/deny decision to the pure :func:`_is_admitted`, and either
    raises :class:`EgressViolation` or calls ``original``. The original
    is captured by closure so monkeypatching ``socket.create_connection``
    later cannot fool the wrapper into delegating to itself.
    """

    def wrapped_create_connection(
        address: tuple[str | bytes, int],
        *args: Any,
        **kwargs: Any,
    ) -> socket.socket:
        host_raw, port = address
        if isinstance(host_raw, bytes):
            host = host_raw.decode("ascii", errors="replace")
        else:
            host = host_raw
        loopback_enabled = _test_only_loopback_enabled.get()
        if not _is_admitted(host, port, loopback_enabled=loopback_enabled):
            raise EgressViolation(host=host, port=port)
        result: socket.socket = original(address, *args, **kwargs)
        return result

    wrapped_create_connection.__wrapped__ = original  # type: ignore[attr-defined]
    return wrapped_create_connection


# --- Public class -----------------------------------------------------------


class EgressGuard:
    """Process-wide socket guard installed via ``sitecustomize.py``.

    All methods are :class:`classmethod` — :class:`EgressGuard` is never
    instantiated; the class object itself is the
    :class:`~codegenie.fallback.leaf.anthropic_adapter.EgressGuardPort`
    that :class:`AnthropicLeafAdapter` expects (AC-24).
    """

    @classmethod
    def install(cls) -> None:
        """Wrap :func:`socket.create_connection` exactly once per process.

        Idempotent (AC-2): the second call is a no-op. Must run before any
        module imports a network library at module-import time;
        ``sitecustomize.py`` at interpreter start is the earliest hook
        short of the C startup.
        """
        global _installed, _ORIGINAL_CREATE_CONNECTION  # noqa: PLW0603
        if _installed:
            return
        _ORIGINAL_CREATE_CONNECTION = socket.create_connection
        socket.create_connection = _wrap_create_connection(_ORIGINAL_CREATE_CONNECTION)
        _installed = True

    @classmethod
    @contextlib.asynccontextmanager
    async def pinned_to(cls, host: str) -> AsyncIterator[None]:
        """Async context manager that pins the SDK egress to ``host``.

        AC-11 / AC-12 / AC-13. ``host`` is a ``"host:port"`` string so the
        adapter callsite reads like the URL it protects
        (``pinned_to("api.anthropic.com:443")``).

        The Phase-4 allowlist is a single host, so ``pinned_to`` is a
        re-affirmation rather than a dynamic widening — the body runs only
        if ``(host, port)`` is already in :data:`_BASE_ALLOWLIST`.
        Well-formed but non-allowlisted hosts raise :class:`EgressViolation`
        at enter (the body never runs). Malformed inputs raise
        :class:`ValueError` (AC-28).

        Phase 7's distroless plugin adds ``cgr.dev`` via an additive ADR
        amendment to :data:`_BASE_ALLOWLIST`; ``pinned_to`` then admits it
        with no signature change.
        """
        parsed_host, parsed_port = _parse_host_port(host)
        if (parsed_host, parsed_port) not in _BASE_ALLOWLIST:
            raise EgressViolation(host=parsed_host, port=parsed_port)
        yield

    @classmethod
    def reset_for_test(cls) -> None:
        """Reset the loopback opt-in flag in the current context (AC-14).

        Does **not** un-install the wrapper. Tests that touch the flag
        MUST call this in teardown (or use the :func:`egress_test_loopback`
        fixture, which calls it on ``yield`` exit).
        """
        _test_only_loopback_enabled.set(False)
