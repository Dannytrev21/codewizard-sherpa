"""Phase-4 S3-02 — schema-at-SDK-boundary (AC-7 / ADR-0001).

The adapter passes :meth:`TypeAdapter.json_schema` to ``output_config.format``
and validates the response with :meth:`TypeAdapter.validate_json` before
constructing the :class:`LeafResponse`. This pair is the load-bearing seam
the LLM never gets to bypass.
"""

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
from codegenie.fallback.plan_proposal import PlanProposal
from codegenie.plugins.events import EventLog
from codegenie.types.identifiers import BudgetTokenId, TokenCount, WorkflowId
from tests.unit.fallback.test_leaf_adapter import (  # type: ignore[import-not-found]
    _FakeAPIStatusError,
    _FakeAsyncAnthropic,
    _FakeMessage,
    _FakeTextBlock,
)


def _wf() -> WorkflowId:
    return WorkflowId("01HSTGSCHFEED000000000000000")


@pytest.fixture
def adp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from codegenie.fallback.leaf import anthropic_adapter as mod

    monkeypatch.setattr(mod, "AsyncAnthropic", _FakeAsyncAnthropic)
    monkeypatch.setattr(mod.anthropic, "APIStatusError", _FakeAPIStatusError)
    monkeypatch.setattr(mod.keyring, "get_password", lambda *_a, **_k: "sk-ant-fake")

    class _Egress:
        @asynccontextmanager
        async def pinned_to(self, _host: str) -> AsyncIterator[None]:
            yield

    log = EventLog(root=tmp_path, workflow_id=_wf())
    return mod.AnthropicLeafAdapter(event_log=log, egress_guard=_Egress())


async def test_output_config_format_equals_schema_json_schema(adp: Any) -> None:
    """AC-7 — ``output_config.format.schema`` is byte-identical to
    :meth:`TypeAdapter.json_schema()` for ``PlanProposal``."""
    schema = TypeAdapter(PlanProposal)
    await adp.invoke(
        TrustedPrompt("[SKILL]\n\n[INSTR]"),
        FencedPromptBody("<<<UNTRUSTED-deadbeefcafe1234>>>x<<<END-deadbeefcafe1234>>>"),
        schema=schema,
        token=BudgetToken(
            id=BudgetTokenId("c" * 32),
            precharged_tokens=TokenCount(1),
            precharged_dollars=Decimal("0.0001"),
            issued_at=datetime(2026, 5, 24, tzinfo=UTC),
        ),
    )
    call_kwargs = adp._client.messages.calls[0].kwargs
    assert call_kwargs["output_config"]["format"]["schema"] == schema.json_schema()


async def test_response_text_is_parsed_through_schema_validate_json(
    adp: Any,
) -> None:
    """AC-7/AC-8 — the adapter parses the SDK response text via
    :meth:`TypeAdapter.validate_json`. We prove this by checking the
    returned :class:`LeafResponse.plan` is the exact discriminated-union
    variant the JSON encoded."""
    adp._client.messages.queue_response(
        _FakeMessage(
            content=[
                _FakeTextBlock(text='{"kind":"refuse","reason":"policy_block","rationale":"r"}')
            ]
        )
    )
    schema = TypeAdapter(PlanProposal)
    response = await adp.invoke(
        TrustedPrompt("[SKILL]\n\n[INSTR]"),
        FencedPromptBody("<<<UNTRUSTED-9999888877776666>>>x<<<END-9999888877776666>>>"),
        schema=schema,
        token=BudgetToken(
            id=BudgetTokenId("d" * 32),
            precharged_tokens=TokenCount(1),
            precharged_dollars=Decimal("0.0001"),
            issued_at=datetime(2026, 5, 24, tzinfo=UTC),
        ),
    )
    assert response.plan.kind == "refuse"
    assert response.plan.reason == "policy_block"
