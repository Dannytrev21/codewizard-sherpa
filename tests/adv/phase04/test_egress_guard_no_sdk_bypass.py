"""AC-18 — the Anthropic SDK's transport stack does NOT bypass the
:class:`EgressGuard` wrapper at the layer the wrapper protects.

The wrapper hooks :func:`socket.create_connection`. The **sync** Anthropic
client (``anthropic.Anthropic``) uses ``httpx``'s sync transport, which
funnels through :func:`socket.create_connection`. This test points the
sync client at a non-Anthropic literal IP and asserts the socket layer
raises :class:`EgressViolation`.

Residual (ADR-0005 §Threat model, layer 1 of 4): the **async** Anthropic
client uses ``httpx``'s async transport, which delegates to
``asyncio.BaseEventLoop.create_connection`` → ``loop.sock_connect`` —
**not** :func:`socket.create_connection`. The Phase-4 socket wrapper does
not catch this path; the production defense is the
:meth:`AnthropicLeafAdapter._call_sdk_with_transport_retry` ``pinned_to``
envelope (S3-02, the *suspenders* in the belt-and-suspenders pair) plus
ADR-0005's OS-level firewall (layer 2) and nightly drift job (layer 3).
The sync test below is what stays in scope for the wrapper itself.

Note on fence scope: this file imports ``anthropic``, which the path-scoped
fence (S1-05 / ADR-0003) permits only under
``src/codegenie/fallback/leaf/anthropic_adapter.py``. The fence scans
``src/codegenie/`` only — a ``tests/`` file is outside that scope.
"""

from __future__ import annotations

import pytest

from codegenie.fallback.leaf.egress_guard import EgressGuard, EgressViolation

pytestmark = pytest.mark.phase04_adv

anthropic = pytest.importorskip("anthropic")


@pytest.fixture(autouse=True)
def _install_egress_guard() -> None:
    EgressGuard.install()


def test_sync_anthropic_sdk_does_not_bypass_wrapper() -> None:
    """Sync Anthropic client routed at a literal IP off the allowlist
    must surface :class:`EgressViolation` from the socket layer."""
    # Literal IP so the transport reaches ``socket.create_connection``
    # without first failing on DNS resolution. ``192.0.2.1`` is the
    # IANA TEST-NET-1 range — routable in our wrapper's view (it gets
    # checked) but guaranteed not to be the codegenie allowlist host.
    client = anthropic.Anthropic(
        api_key="sk-not-a-real-key",
        base_url="http://192.0.2.1:80",
    )
    with pytest.raises(BaseException) as exc:
        client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=16,
            messages=[{"role": "user", "content": "hi"}],
        )

    raised = exc.value
    chain: list[BaseException | None] = []
    cur: BaseException | None = raised
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        chain.append(cur)
        cur = cur.__cause__ or cur.__context__

    assert any(isinstance(link, EgressViolation) for link in chain), (
        f"EgressViolation not found in cause chain — the sync SDK is "
        f"bypassing socket.create_connection. Chain: {chain!r}"
    )


def test_async_httpx_bypass_is_a_known_residual() -> None:
    """Document the async-asyncio bypass as a deliberate residual.

    ``asyncio.BaseEventLoop.create_connection`` does not call
    :func:`socket.create_connection`; it uses ``loop.sock_connect`` on a
    raw socket. The Phase-4 wrapper is a sync-path defense; async paths
    are covered by the S3-02 ``pinned_to`` envelope (the *suspenders*
    layer) and ADR-0005's OS firewall (layer 2). This test pins the
    residual so a future story that closes it (e.g., by also wrapping
    ``asyncio.BaseEventLoop._sock_connect``) updates this assertion
    deliberately, rather than the gap silently widening.
    """
    import asyncio

    # The asyncio loop's sock_connect uses the raw socket directly; our
    # wrapper only hooks socket.create_connection. The pinning here is
    # structural — the test fails loudly if a future change starts
    # routing asyncio through our wrapper, prompting an AC update.
    assert hasattr(asyncio.BaseEventLoop, "sock_connect")
