"""Phase-4 S3-02 — in-call malformed-output retry (AC-12 / AC-13 / AC-14)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from codegenie.fallback.budget_token import BudgetToken
from codegenie.fallback.fence.prompt_builder import FencedPromptBody, TrustedPrompt
from codegenie.fallback.plan_proposal import PlanProposal, PlanProposalRefuse
from codegenie.plugins.events import (
    EventLog,
    LeafProtocolViolationEvent,
    LeafReturned,
)
from codegenie.types.identifiers import BudgetTokenId, TokenCount, WorkflowId
from tests.unit.fallback.test_leaf_adapter import (  # type: ignore[import-not-found]
    _VALID_REFUSE_JSON,
    _FakeAPIStatusError,
    _FakeAsyncAnthropic,
    _FakeMessage,
    _FakeTextBlock,
)


def _wf() -> WorkflowId:
    return WorkflowId("01HSTGMALFEED000000000000000")


def _token() -> BudgetToken:
    return BudgetToken(
        id=BudgetTokenId("b" * 32),
        precharged_tokens=TokenCount(500),
        precharged_dollars=Decimal("0.001"),
        issued_at=datetime(2026, 5, 24, tzinfo=UTC),
    )


def _schema() -> TypeAdapter[PlanProposal]:
    return TypeAdapter(PlanProposal)


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, EventLog]:
    from codegenie.fallback.leaf import anthropic_adapter as mod

    monkeypatch.setattr(mod, "AsyncAnthropic", _FakeAsyncAnthropic)
    monkeypatch.setattr(mod.anthropic, "APIStatusError", _FakeAPIStatusError)
    monkeypatch.setattr(mod.keyring, "get_password", lambda *_a, **_k: "sk-ant-fake")

    class _Egress:
        @asynccontextmanager
        async def pinned_to(self, _host: str) -> AsyncIterator[None]:
            yield

    log = EventLog(root=tmp_path, workflow_id=_wf())
    return mod.AnthropicLeafAdapter(event_log=log, egress_guard=_Egress()), log


async def test_in_call_schema_failure_retries_exactly_once(adapter: tuple[Any, EventLog]) -> None:
    """AC-13 — one malformed 200 then one valid 200: exactly two physical SDK
    calls, retry user content gets the trusted suffix appended, response is
    the valid refuse, and no ``LeafProtocolViolationEvent`` is emitted."""
    adp, log = adapter
    adp._client.messages.queue_response(_FakeMessage(content=[_FakeTextBlock(text="not json")]))
    adp._client.messages.queue_response(
        _FakeMessage(content=[_FakeTextBlock(text=_VALID_REFUSE_JSON)])
    )
    sys = TrustedPrompt("[SKILL]\n\n[INSTR]")
    body = FencedPromptBody("<<<UNTRUSTED-abcdef0123456789>>>data<<<END-abcdef0123456789>>>")
    response = await adp.invoke(sys, body, schema=_schema(), token=_token())
    assert adp._client.messages.call_count == 2
    retry_content = adp._client.messages.calls[1].kwargs["messages"][0]["content"]
    assert retry_content.endswith(
        "\n\n[SYSTEM] your previous response was malformed; emit valid PlanProposal."
    )
    # Initial user bytes intact at the *start*; suffix appended only.
    assert retry_content.startswith(str(body))
    assert isinstance(response.plan, PlanProposalRefuse)
    assert response.plan.kind == "refuse"
    # No protocol-violation event was emitted (recovery succeeded).
    violations = [e for e in log.replay() if isinstance(e, LeafProtocolViolationEvent)]
    assert violations == []


async def test_double_malformed_raises_protocol_violation_and_emits_event(
    adapter: tuple[Any, EventLog],
) -> None:
    """AC-14 — two malformed responses raise ``LeafProtocolViolation`` and
    emit exactly one ``LeafProtocolViolationEvent``; no ``LeafReturned``."""
    from codegenie.fallback.leaf.anthropic_adapter import LeafProtocolViolation

    adp, log = adapter
    adp._client.messages.queue_response(_FakeMessage(content=[_FakeTextBlock(text="not json")]))
    adp._client.messages.queue_response(
        _FakeMessage(content=[_FakeTextBlock(text='{"missing":"kind"}')])
    )
    sys = TrustedPrompt("[SKILL]\n\n[INSTR]")
    body = FencedPromptBody("<<<UNTRUSTED-0badf00dcafebeef>>>x<<<END-0badf00dcafebeef>>>")
    with pytest.raises(LeafProtocolViolation):
        await adp.invoke(sys, body, schema=_schema(), token=_token())
    violations = [e for e in log.replay() if isinstance(e, LeafProtocolViolationEvent)]
    assert len(violations) == 1
    returns = [e for e in log.replay() if isinstance(e, LeafReturned)]
    assert returns == []
