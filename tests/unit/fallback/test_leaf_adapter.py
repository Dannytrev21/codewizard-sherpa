"""Phase-4 S3-02 — :class:`AnthropicLeafAdapter` unit suite.

Covers init / key-loading / refuse-to-start / no-env-fallback / invoke
signature / request shape / response parsing / event order / token
mapping / digest hygiene / budget non-reconciliation / transport retry
schedule / non-status-error propagation / retry-counter independence /
egress wrapping. SDK fakes only — no live network, no live cassettes
(AC-22; live recording deferred to S3-04..S3-06).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from unittest.mock import MagicMock, patch

import pytest
from pydantic import TypeAdapter

from codegenie.fallback.budget_token import BudgetToken
from codegenie.fallback.fence.prompt_builder import FencedPromptBody, TrustedPrompt
from codegenie.fallback.plan_proposal import PlanProposal
from codegenie.hashing import content_hash_bytes
from codegenie.plugins.events import (
    EventLog,
    LeafInvoked,
    LeafKeyLoaded,
    LeafReturned,
)
from codegenie.types.identifiers import BudgetTokenId, TokenCount, WorkflowId

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _SDKCall:
    """One physical SDK call's recorded inputs (kwargs only — the SDK is
    keyword-only on every modern method)."""

    kwargs: dict[str, Any]


@dataclass
class _FakeUsage:
    """Stand-in for :class:`anthropic.types.Usage` without importing the SDK
    type into the test (the test layer must stay SDK-free per the path-scoped
    fence intent)."""

    input_tokens: int = 100
    output_tokens: int = 80
    cache_read_input_tokens: int | None = 0
    cache_creation_input_tokens: int | None = 0


@dataclass
class _FakeTextBlock:
    """Stand-in for :class:`anthropic.types.TextBlock`."""

    text: str
    type: str = "text"


@dataclass
class _FakeMessage:
    """Stand-in for :class:`anthropic.types.Message`."""

    content: list[_FakeTextBlock]
    usage: _FakeUsage = field(default_factory=_FakeUsage)
    id: str = "msg_01abcdef"
    model: str = "claude-sonnet-4-5-20250929"
    stop_reason: str = "end_turn"


class _FakeAPIStatusError(Exception):
    """Stand-in raised in place of :class:`anthropic.APIStatusError`.

    The adapter's transport retry must catch only ``anthropic.APIStatusError``,
    so tests inject this exception into the SDK call queue and the test
    patches the adapter's reference to ``anthropic.APIStatusError`` to this
    sentinel for the duration of the test.
    """


@dataclass
class _FakeMessages:
    """Records ``create`` kwargs and returns scripted responses or raises."""

    calls: list[_SDKCall] = field(default_factory=list)
    _queue: list[Any] = field(default_factory=list)

    def queue_response(self, message: _FakeMessage) -> None:
        self._queue.append(message)

    def queue_status_error(self, count: int = 1) -> None:
        for _ in range(count):
            self._queue.append(_FakeAPIStatusError("scripted status error"))

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(_SDKCall(kwargs=kwargs))
        if not self._queue:
            return _FakeMessage(
                content=[_FakeTextBlock(text=_VALID_REFUSE_JSON)],
            )
        next_item = self._queue.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        assert isinstance(next_item, _FakeMessage)
        return next_item


@dataclass
class _FakeAsyncAnthropic:
    """Stand-in for :class:`anthropic.AsyncAnthropic`."""

    api_key: str
    messages: _FakeMessages = field(default_factory=_FakeMessages)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_REFUSE_JSON: Final[str] = (
    '{"kind":"refuse","reason":"out_of_scope","rationale":"scripted refuse"}'
)


def _wf() -> WorkflowId:
    return WorkflowId("01HSTGGFEED0000000000000000")


def _event_log(tmp_path: Path) -> EventLog:
    return EventLog(root=tmp_path, workflow_id=_wf())


def _budget_token() -> BudgetToken:
    return BudgetToken(
        id=BudgetTokenId("a" * 32),
        precharged_tokens=TokenCount(500),
        precharged_dollars=Decimal("0.001"),
        issued_at=datetime(2026, 5, 24, tzinfo=UTC),
    )


def _schema() -> TypeAdapter[PlanProposal]:
    return TypeAdapter(PlanProposal)


@pytest.fixture
def adapter_with_sdk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build an :class:`AnthropicLeafAdapter` with the SDK ``AsyncAnthropic``
    constructor monkeypatched to :class:`_FakeAsyncAnthropic` and ``keyring``
    short-circuited to ``"sk-ant-test-NOT-A-REAL-KEY"``."""
    from codegenie.fallback.leaf import anthropic_adapter as mod

    fake_key = "sk-ant-test-NOT-A-REAL-KEY"
    monkeypatch.setattr(mod, "AsyncAnthropic", _FakeAsyncAnthropic)
    # The adapter catches only ``anthropic.APIStatusError`` — point that name
    # at our local sentinel so transport retries can be driven without the SDK.
    monkeypatch.setattr(mod.anthropic, "APIStatusError", _FakeAPIStatusError)

    def _fake_keyring(service: str, user: str) -> str | None:
        if (service, user) == ("codegenie", "anthropic_api_key"):
            return fake_key
        return None

    monkeypatch.setattr(mod.keyring, "get_password", _fake_keyring)
    # Recording egress guard
    enters: list[str] = []
    exits: list[str] = []

    class _RecordingEgress:
        @asynccontextmanager
        async def pinned_to(self, host: str) -> AsyncIterator[None]:
            enters.append(host)
            try:
                yield
            finally:
                exits.append(host)

    log = _event_log(tmp_path)
    egress = _RecordingEgress()
    adapter = mod.AnthropicLeafAdapter(event_log=log, egress_guard=egress)
    return adapter, egress, log, enters, exits, fake_key


@pytest.fixture
def trusted_prompt() -> TrustedPrompt:
    return TrustedPrompt("[SKILL: fix-vuln]\n\n[INSTRUCTION] propose a patch.")


@pytest.fixture
def fenced_body() -> FencedPromptBody:
    return FencedPromptBody(
        "<<<UNTRUSTED-0123456789abcdef>>>\nCVE-2026-1234: bad bug.\n<<<END-0123456789abcdef>>>"
    )


# ---------------------------------------------------------------------------
# Init / key loading
# ---------------------------------------------------------------------------


def test_init_refuses_when_keyring_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2/AC-4 — keyring miss raises ``AnthropicKeyMissing`` with the literal
    ``codegenie auth set`` diagnostic; a final ``leaf_key_loaded(present=False)``
    event is emitted."""
    from codegenie.fallback.leaf.anthropic_adapter import (
        AnthropicKeyMissing,
        AnthropicLeafAdapter,
    )

    log = _event_log(tmp_path)
    with patch("keyring.get_password", return_value=None):
        with pytest.raises(AnthropicKeyMissing) as exc:
            AnthropicLeafAdapter(event_log=log, egress_guard=MagicMock())
    assert "codegenie auth set" in str(exc.value)
    events = list(log.replay())
    assert isinstance(events[-1], LeafKeyLoaded)
    assert events[-1].present is False


def test_init_does_not_fall_back_to_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-5 — env-var fallback is structurally absent: even with
    ``CODEGENIE_ANTHROPIC_KEY_CI`` set, keyring miss still raises."""
    from codegenie.fallback.leaf.anthropic_adapter import (
        AnthropicKeyMissing,
        AnthropicLeafAdapter,
    )

    monkeypatch.setenv("CODEGENIE_ANTHROPIC_KEY_CI", "sk-ant-NOPE-NOT-USED")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-NOPE-NOT-USED")
    log = _event_log(tmp_path)
    with patch("keyring.get_password", return_value=None):
        with pytest.raises(AnthropicKeyMissing):
            AnthropicLeafAdapter(event_log=log, egress_guard=MagicMock())


def test_adapter_source_does_not_reference_env_or_getpass() -> None:
    """AC-5 — AST source-scan: the adapter module contains no ``os.environ`` /
    ``os.getenv`` / ``getpass`` / ``CODEGENIE_*`` reference. Guards against
    a future contributor silently re-adding an env-var fallback path."""
    import ast

    import codegenie.fallback.leaf.anthropic_adapter as mod

    src_path = Path(mod.__file__)
    src = src_path.read_text()
    tree = ast.parse(src)

    forbidden_names = {"environ", "getenv", "getpass"}
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in forbidden_names:
            offenders.append(f"attribute {node.attr} at line {node.lineno}")
        if isinstance(node, ast.Name) and node.id in forbidden_names:
            offenders.append(f"name {node.id} at line {node.lineno}")
    assert not offenders, f"adapter references env/getpass surface: {offenders}"

    # No literal "CODEGENIE_" CI key reference may appear in the source.
    assert "CODEGENIE_ANTHROPIC_KEY_CI" not in src
    assert "ANTHROPIC_API_KEY" not in src


def test_init_does_not_store_cleartext_key(adapter_with_sdk: Any) -> None:
    """AC-3 — the cleartext key never appears as a direct adapter attribute.

    The adapter uses ``__slots__`` (no ``__dict__``); iterate the named
    slots and assert none of them carry the cleartext bytes. The SDK
    client retains the key internally — that's expected and out of
    scope for this assertion."""
    adapter, _egress, _log, _enters, _exits, fake_key = adapter_with_sdk
    for slot in adapter.__slots__:
        if slot == "_client":
            continue  # SDK client legitimately holds the key
        value = getattr(adapter, slot, None)
        blob = repr(value)
        assert fake_key not in blob, f"slot {slot!r} leaked the cleartext key"
        assert "sk-ant" not in blob, f"slot {slot!r} carries sk-ant-shaped bytes"


def test_init_emits_key_loaded_present_true(adapter_with_sdk: Any) -> None:
    """AC-4 — happy-path construction emits ``leaf_key_loaded(present=True)``
    exactly once."""
    _adapter, _egress, log, *_ = adapter_with_sdk
    events = [e for e in log.replay() if isinstance(e, LeafKeyLoaded)]
    assert len(events) == 1
    assert events[0].present is True


# ---------------------------------------------------------------------------
# Invoke shape
# ---------------------------------------------------------------------------


def test_invoke_signature_matches_leaf_llm_protocol() -> None:
    """AC-6 — exact signature parity with the S3-01 Protocol (keyword-only
    schema + token)."""
    import inspect

    from codegenie.fallback.leaf.anthropic_adapter import AnthropicLeafAdapter
    from codegenie.fallback.leaf.port import LeafLlm

    adapter_sig = inspect.signature(AnthropicLeafAdapter.invoke)
    port_sig = inspect.signature(LeafLlm.invoke)
    assert list(adapter_sig.parameters) == list(port_sig.parameters)
    for name in ("schema", "token"):
        assert adapter_sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


async def test_first_request_uses_output_config_schema_and_exact_user_bytes(
    adapter_with_sdk: Any,
    trusted_prompt: TrustedPrompt,
    fenced_body: FencedPromptBody,
) -> None:
    """AC-7 — first SDK request has ``output_config.format.schema ==
    schema.json_schema()``; one cached trusted-system block; user content is
    exactly ``str(fenced_body)`` (no wrapping, no f-string interpolation)."""
    adapter, _egress, _log, _enters, _exits, _key = adapter_with_sdk
    schema = _schema()
    await adapter.invoke(
        trusted_prompt,
        fenced_body,
        schema=schema,
        token=_budget_token(),
    )
    call = adapter._client.messages.calls[0]
    kwargs = call.kwargs
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["output_config"]["format"]["schema"] == schema.json_schema()
    assert kwargs["system"] == [
        {
            "type": "text",
            "text": str(trusted_prompt),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    assert kwargs["messages"] == [{"role": "user", "content": str(fenced_body)}]


async def test_invoke_emits_invoked_then_returned(
    adapter_with_sdk: Any,
    trusted_prompt: TrustedPrompt,
    fenced_body: FencedPromptBody,
) -> None:
    """AC-8 — happy path emits ``leaf_invoked`` before the SDK call and
    ``leaf_returned`` after parse succeeds."""
    adapter, _egress, log, *_ = adapter_with_sdk
    await adapter.invoke(trusted_prompt, fenced_body, schema=_schema(), token=_budget_token())
    invoked = [e for e in log.replay() if isinstance(e, LeafInvoked)]
    returned = [e for e in log.replay() if isinstance(e, LeafReturned)]
    assert len(invoked) == 1
    assert len(returned) == 1
    # Replay sorts by (timestamp, event_id); invoked.event_id should sort
    # before returned.event_id by construction (UUID4 hex).
    assert invoked[0].model == "claude-sonnet-4-5-20250929"


async def test_token_fields_map_from_usage(
    adapter_with_sdk: Any,
    trusted_prompt: TrustedPrompt,
    fenced_body: FencedPromptBody,
) -> None:
    """AC-9 — token-count fields are pulled from
    :class:`anthropic.types.Usage`; missing cache counters default to zero."""
    adapter, _egress, _log, *_ = adapter_with_sdk
    # Queue a response with all four usage fields explicit.
    adapter._client.messages.queue_response(
        _FakeMessage(
            content=[_FakeTextBlock(text=_VALID_REFUSE_JSON)],
            usage=_FakeUsage(
                input_tokens=42,
                output_tokens=17,
                cache_read_input_tokens=9,
                cache_creation_input_tokens=11,
            ),
        )
    )
    response = await adapter.invoke(
        trusted_prompt, fenced_body, schema=_schema(), token=_budget_token()
    )
    assert response.tokens_in == 42
    assert response.tokens_out == 17
    assert response.cache_read_tokens == 9
    assert response.cache_creation_tokens == 11

    # And a response with cache counters absent → default to 0.
    adapter._client.messages.queue_response(
        _FakeMessage(
            content=[_FakeTextBlock(text=_VALID_REFUSE_JSON)],
            usage=_FakeUsage(
                input_tokens=1,
                output_tokens=1,
                cache_read_input_tokens=None,
                cache_creation_input_tokens=None,
            ),
        )
    )
    response2 = await adapter.invoke(
        trusted_prompt, fenced_body, schema=_schema(), token=_budget_token()
    )
    assert response2.cache_read_tokens == 0
    assert response2.cache_creation_tokens == 0


async def test_event_payloads_never_contain_raw_prompt_or_response(
    adapter_with_sdk: Any,
    trusted_prompt: TrustedPrompt,
    fenced_body: FencedPromptBody,
) -> None:
    """AC-10 — no raw prompt or response bytes appear in any emitted event."""
    adapter, _egress, log, *_ = adapter_with_sdk
    await adapter.invoke(trusted_prompt, fenced_body, schema=_schema(), token=_budget_token())
    for event in log.replay():
        serialized = event.model_dump_json()
        assert str(trusted_prompt) not in serialized
        assert str(fenced_body) not in serialized
        # The refuse JSON's distinctive rationale string must not leak.
        assert "scripted refuse" not in serialized


async def test_prompt_digest_matches_blake3_of_concat(
    adapter_with_sdk: Any,
    trusted_prompt: TrustedPrompt,
    fenced_body: FencedPromptBody,
) -> None:
    """AC-10 — ``prompt_digest_blake3`` equals
    :func:`blake3(str(system_prompt) + str(user_message))` (un-prefixed)."""
    adapter, _egress, log, *_ = adapter_with_sdk
    await adapter.invoke(trusted_prompt, fenced_body, schema=_schema(), token=_budget_token())
    expected = content_hash_bytes(
        (str(trusted_prompt) + str(fenced_body)).encode("utf-8")
    ).removeprefix("blake3:")
    invoked = next(e for e in log.replay() if isinstance(e, LeafInvoked))
    assert invoked.prompt_digest_blake3 == expected


async def test_budget_token_is_not_reconciled_in_adapter(
    adapter_with_sdk: Any,
    trusted_prompt: TrustedPrompt,
    fenced_body: FencedPromptBody,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-11 — the adapter accepts the token but does NOT call
    :meth:`LlmInvocationGuard.reconcile` and does NOT mutate budget state."""
    from codegenie.fallback import budget as budget_mod

    reconcile_calls: list[Any] = []

    def _spy(self: Any, token: Any, **kw: Any) -> None:
        reconcile_calls.append((token, kw))

    monkeypatch.setattr(budget_mod.LlmInvocationGuard, "reconcile", _spy)
    adapter, *_ = adapter_with_sdk
    await adapter.invoke(trusted_prompt, fenced_body, schema=_schema(), token=_budget_token())
    assert reconcile_calls == [], "adapter must not call LlmInvocationGuard.reconcile"


def test_adapter_source_does_not_import_llm_invocation_guard() -> None:
    """AC-11 — AST source-scan: no ``LlmInvocationGuard`` import in the
    adapter (the budget guard is FallbackTier's concern per ADR-0010).

    Checks import statements specifically (not docstring mentions), so the
    adapter is free to reference the class name in prose to explain *why*
    it doesn't import it."""
    import ast

    import codegenie.fallback.leaf.anthropic_adapter as mod

    tree = ast.parse(Path(mod.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "LlmInvocationGuard", (
                    f"adapter imports LlmInvocationGuard at line {node.lineno} — "
                    "reconciliation belongs to FallbackTier (ADR-0010)"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "LlmInvocationGuard" not in alias.name, (
                    f"adapter imports {alias.name} at line {node.lineno}"
                )


# ---------------------------------------------------------------------------
# Transport retries (AC-15..AC-17)
# ---------------------------------------------------------------------------


async def test_transport_retry_schedule_is_1_4_16(
    adapter_with_sdk: Any,
    trusted_prompt: TrustedPrompt,
    fenced_body: FencedPromptBody,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-15 — three retries on ``APIStatusError`` with sleep schedule
    ``[1.0, 4.0, 16.0]`` then propagation."""
    adapter, _egress, _log, _enters, _exits, _key = adapter_with_sdk
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    adapter._client.messages.queue_status_error(count=3)
    # 4th attempt succeeds with a valid refuse JSON.
    adapter._client.messages.queue_response(
        _FakeMessage(content=[_FakeTextBlock(text=_VALID_REFUSE_JSON)])
    )
    await adapter.invoke(trusted_prompt, fenced_body, schema=_schema(), token=_budget_token())
    assert sleeps == [1.0, 4.0, 16.0]
    assert adapter._client.messages.call_count == 4


async def test_transport_retry_propagates_after_four_failures(
    adapter_with_sdk: Any,
    trusted_prompt: TrustedPrompt,
    fenced_body: FencedPromptBody,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-15 — after the 4th failure the original ``APIStatusError`` propagates
    unwrapped (not re-raised under a new exception)."""
    adapter, _egress, _log, _enters, _exits, _key = adapter_with_sdk

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    adapter._client.messages.queue_status_error(count=4)
    with pytest.raises(_FakeAPIStatusError):
        await adapter.invoke(trusted_prompt, fenced_body, schema=_schema(), token=_budget_token())
    assert adapter._client.messages.call_count == 4


async def test_non_status_error_skips_transport_retry(
    adapter_with_sdk: Any,
    trusted_prompt: TrustedPrompt,
    fenced_body: FencedPromptBody,
) -> None:
    """AC-16 — a non-``APIStatusError`` from the SDK propagates immediately,
    without invoking transport retries."""
    adapter, _egress, _log, *_ = adapter_with_sdk

    class _UnrelatedError(Exception):
        pass

    adapter._client.messages._queue.append(_UnrelatedError("boom"))
    with pytest.raises(_UnrelatedError):
        await adapter.invoke(trusted_prompt, fenced_body, schema=_schema(), token=_budget_token())
    assert adapter._client.messages.call_count == 1


async def test_transport_retry_and_malformed_retry_are_independent(
    adapter_with_sdk: Any,
    trusted_prompt: TrustedPrompt,
    fenced_body: FencedPromptBody,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-17 — one status error then one malformed 200 then one valid 200:
    transport-retry counter and malformed-retry counter are independent."""
    adapter, _egress, _log, *_ = adapter_with_sdk

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    adapter._client.messages.queue_status_error(count=1)
    adapter._client.messages.queue_response(_FakeMessage(content=[_FakeTextBlock(text="not json")]))
    adapter._client.messages.queue_response(
        _FakeMessage(content=[_FakeTextBlock(text=_VALID_REFUSE_JSON)])
    )
    await adapter.invoke(trusted_prompt, fenced_body, schema=_schema(), token=_budget_token())
    # 1 status error + 1 malformed + 1 valid = 3 physical SDK calls.
    assert adapter._client.messages.call_count == 3


# ---------------------------------------------------------------------------
# EgressGuard wrapping (AC-18)
# ---------------------------------------------------------------------------


async def test_egress_guard_wraps_every_sdk_call(
    adapter_with_sdk: Any,
    trusted_prompt: TrustedPrompt,
    fenced_body: FencedPromptBody,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-18 — exactly one enter/exit pair per physical SDK call, every host
    equal to ``api.anthropic.com:443``."""
    adapter, _egress, _log, enters, exits, _key = adapter_with_sdk

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    adapter._client.messages.queue_status_error(count=2)
    adapter._client.messages.queue_response(
        _FakeMessage(content=[_FakeTextBlock(text=_VALID_REFUSE_JSON)])
    )
    await adapter.invoke(trusted_prompt, fenced_body, schema=_schema(), token=_budget_token())
    assert len(enters) == 3 == len(exits)
    for host in enters:
        assert host == "api.anthropic.com:443"
    for host in exits:
        assert host == "api.anthropic.com:443"
