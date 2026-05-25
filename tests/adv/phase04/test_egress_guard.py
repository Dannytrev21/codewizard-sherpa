"""Phase-4 S3-03 — :class:`EgressGuard` adversarial suite.

Covers the install/wrap semantics, the forbidden-host parametrization
(driven through real HTTP-client code paths to ``socket.create_connection``),
the loopback policy (ADR-0006), the ``pinned_to`` async context manager,
the ``self-check egress`` CLI side-effect-free check, and the
:func:`_is_admitted` functional core (AC-27).

The ``sitecustomize.py`` auto-discovery proof (AC-26) lives in
:mod:`test_egress_guard_sitecustomize`.
"""

from __future__ import annotations

import socket
import sys

import pytest

from codegenie.fallback.leaf.egress_guard import (
    EgressGuard,
    EgressViolation,
    _is_admitted,
    _test_only_loopback_enabled,
)

pytestmark = pytest.mark.phase04_adv


@pytest.fixture(autouse=True)
def _install_egress_guard() -> None:
    """Ensure the wrapper is installed (idempotent) and the loopback
    flag is reset between tests."""
    EgressGuard.install()
    EgressGuard.reset_for_test()


# --- AC-2 — idempotent install ---------------------------------------------


def test_install_is_idempotent() -> None:
    """Calling :meth:`EgressGuard.install` twice in the same process does
    not double-wrap. The wrapper exposes ``__wrapped__`` pointing at the
    captured original, and the wrapper identity is stable across calls."""
    first = socket.create_connection
    EgressGuard.install()  # second call
    second = socket.create_connection
    assert first is second
    assert hasattr(second, "__wrapped__")
    # __wrapped__ must NOT be the wrapper itself — that would be a double-wrap.
    assert second.__wrapped__ is not second  # type: ignore[attr-defined]


# --- AC-3 + AC-6 + AC-16 — forbidden hosts via real socket path ------------


_FORBIDDEN_HOSTS = [
    ("evil.example.com", 443),
    ("10.0.0.1", 443),
    ("127.0.0.1", 8080),
    ("::1", 8080),
    ("localhost", 8080),
    ("1.1.1.1", 443),
    ("xn--api-1ub.anthropic.com", 443),
]


@pytest.mark.parametrize(("host", "port"), _FORBIDDEN_HOSTS)
def test_forbidden_hosts_raise_via_socket(host: str, port: int) -> None:
    """Direct :func:`socket.create_connection` to a forbidden host raises
    :class:`EgressViolation` with the exact host/port populated."""
    with pytest.raises(EgressViolation) as exc:
        socket.create_connection((host, port))
    assert exc.value.host == host
    assert exc.value.port == port


@pytest.mark.parametrize("host", ["evil.example.com", "10.0.0.1", "1.1.1.1"])
def test_forbidden_hosts_via_urllib(host: str) -> None:
    """The forbidden-host block reaches code paths that go through
    :func:`socket.create_connection`. :mod:`urllib` is stdlib and ships
    with every interpreter — no third-party dep needed to prove the
    socket layer is what stops the connection."""
    import urllib.error
    import urllib.request

    with pytest.raises((EgressViolation, urllib.error.URLError)) as exc:
        urllib.request.urlopen(f"http://{host}:80", timeout=1)  # noqa: S310
    # urllib wraps the socket failure in URLError(reason=...) — assert
    # EgressViolation is somewhere in the cause chain (direct, __cause__,
    # __context__, or .reason).
    raised = exc.value
    chain: list[BaseException | None] = [raised, raised.__cause__, raised.__context__]
    if isinstance(raised, urllib.error.URLError):
        chain.append(raised.reason if isinstance(raised.reason, BaseException) else None)
    assert any(isinstance(link, EgressViolation) for link in chain), (
        f"EgressViolation not found in cause chain of {raised!r}: {chain!r}"
    )


# --- AC-4 — base allowlist contents ----------------------------------------


def test_base_allowlist_admits_anthropic_only() -> None:
    """The pure :func:`_is_admitted` admits ``api.anthropic.com:443`` and
    rejects everything else (loopback excluded by ``loopback_enabled``)."""
    assert _is_admitted("api.anthropic.com", 443, loopback_enabled=False) is True
    # different port → rejected
    assert _is_admitted("api.anthropic.com", 80, loopback_enabled=False) is False
    # different host → rejected even on canonical port
    assert _is_admitted("evil.example.com", 443, loopback_enabled=False) is False


# --- AC-7 — loopback admitted under fixture, real fall-through -------------


def test_loopback_admitted_when_fixture_set_real_fallthrough(
    egress_test_loopback: None,  # noqa: ARG001 — fixture sets the flag
) -> None:
    """With the fixture active, ``create_connection`` falls through to
    the real socket call — proven by binding a throwaway listener on an
    ephemeral port and asserting a genuine TCP connection succeeds."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        conn = socket.create_connection(("127.0.0.1", port), timeout=1)
        try:
            assert conn.fileno() >= 0
        finally:
            conn.close()
    finally:
        listener.close()


def test_loopback_rejected_without_fixture() -> None:
    """Without the fixture, loopback is rejected — proves the fixture is
    the discriminator, not an unrelated success state."""
    with pytest.raises(EgressViolation):
        socket.create_connection(("127.0.0.1", 8080), timeout=1)


# --- AC-9 — no env-var escape ----------------------------------------------


def test_no_env_var_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting any plausible ``CODEGENIE_*`` env var does NOT widen the
    allowlist. The flag is fixture-set only."""
    monkeypatch.setenv("CODEGENIE_TEST_ALLOW_LOOPBACK", "1")
    monkeypatch.setenv("CODEGENIE_EGRESS_BYPASS", "true")
    with pytest.raises(EgressViolation):
        socket.create_connection(("127.0.0.1", 8080), timeout=1)


def test_egress_guard_source_has_no_environ_reference() -> None:
    """AC-9 — AST-level proof: the module source contains no
    ``os.environ`` / ``os.getenv`` / ``CODEGENIE_*`` reference."""
    import codegenie.fallback.leaf.egress_guard as mod

    src = open(mod.__file__).read()  # noqa: SIM115, PTH123
    assert "os.environ" not in src
    assert "os.getenv" not in src
    assert "CODEGENIE_" not in src


# --- AC-10 — no boolean parameter ------------------------------------------


def test_install_signature_is_zero_arg() -> None:
    import inspect

    sig = inspect.signature(EgressGuard.install)
    # classmethod signature drops ``cls`` — should be empty.
    assert list(sig.parameters) == []


def test_pinned_to_signature_is_one_arg() -> None:
    import inspect

    sig = inspect.signature(EgressGuard.pinned_to)
    params = list(sig.parameters)
    assert params == ["host"]


# --- AC-11 + AC-12 — pinned_to ---------------------------------------------


async def test_pinned_to_anthropic_admits_inside_block() -> None:
    """A well-formed allowlisted host enters cleanly; we don't actually
    dial Anthropic, but inside the block the same host is admitted
    because it's in the base allowlist."""
    async with EgressGuard.pinned_to("api.anthropic.com:443"):
        # _is_admitted is the same check the wrapper makes; if the base
        # allowlist were silently stripped on enter the assertion would fail.
        assert _is_admitted("api.anthropic.com", 443, loopback_enabled=False) is True


async def test_pinned_to_other_host_raises_at_enter() -> None:
    with pytest.raises(EgressViolation):
        async with EgressGuard.pinned_to("other.example.com:443"):
            pytest.fail("body must not run when host is not allowlisted")


# --- AC-28 — malformed pinned_to argument ----------------------------------


@pytest.mark.parametrize("bad", ["no-colon", "host:notaport", ":443"])
async def test_pinned_to_malformed_raises_value_error(bad: str) -> None:
    with pytest.raises(ValueError):
        async with EgressGuard.pinned_to(bad):
            pytest.fail("body must not run for malformed host:port")


# --- AC-19 + AC-20 — CLI self-check ----------------------------------------


def test_self_check_egress_prints_allowlist_and_state(capsys: pytest.CaptureFixture[str]) -> None:
    from codegenie.__main__ import main

    rc = main(["self-check", "egress"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "api.anthropic.com:443" in out
    assert "installed=" in out


def test_self_check_egress_does_not_set_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """AC-20 — the reporting command must not mutate the test-only flag."""
    from codegenie.__main__ import main

    # Confirm the flag starts False (autouse fixture reset it).
    assert _test_only_loopback_enabled.get() is False
    rc = main(["self-check", "egress"])
    assert rc == 0
    capsys.readouterr()  # drain
    assert _test_only_loopback_enabled.get() is False


# --- AC-27 — pure-helper table-driven --------------------------------------


@pytest.mark.parametrize(
    ("host", "port", "loopback_enabled", "expected"),
    [
        ("api.anthropic.com", 443, False, True),
        ("api.anthropic.com", 443, True, True),
        ("api.anthropic.com", 80, False, False),
        ("evil.example.com", 443, False, False),
        ("127.0.0.1", 8080, False, False),
        ("127.0.0.1", 8080, True, True),
        ("::1", 8080, False, False),
        ("::1", 8080, True, True),
        ("localhost", 8080, False, False),
        ("localhost", 8080, True, True),
        ("10.0.0.1", 443, True, False),  # private IP not a loopback form
        ("xn--api-1ub.anthropic.com", 443, False, False),  # IDN literal compared as-is
    ],
)
def test_is_admitted_table(host: str, port: int, *, loopback_enabled: bool, expected: bool) -> None:
    assert _is_admitted(host, port, loopback_enabled=loopback_enabled) is expected


# --- Python-version sanity (avoid surprising stdlib regressions) -----------


def test_running_on_python_311_or_newer() -> None:
    """``contextvars`` propagation across ``await`` requires 3.7+; this
    project targets 3.11+."""
    assert sys.version_info >= (3, 11)
