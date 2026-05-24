"""Phase-4 S1-04 — happy/sad-path tests for ``BudgetSnapshot`` + ``BudgetToken``.

The RAG-side models are exercised in ``tests/unit/rag/test_models.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from codegenie.fallback.budget import BudgetSnapshot, BudgetToken

_UTC_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_TOKEN = {
    "precharged_tokens": 5_000,
    "precharged_dollars": Decimal("0.03"),
    "issued_at": _UTC_NOW,
}
_SNAPSHOT = {
    "consumed_tokens": 100,
    "consumed_dollars": Decimal("0.5"),
    "outstanding_tokens": 0,
    "cap_tokens": 1_000,
    "cap_dollars": Decimal("1.5"),
}


# --- extra="forbid" / frozen, parametrized over both budget models (AC-10) ---


@pytest.mark.parametrize(
    "model_cls,payload",
    [(BudgetSnapshot, _SNAPSHOT), (BudgetToken, _TOKEN)],
)
def test_extra_keys_rejected(model_cls, payload) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        model_cls.model_validate({**payload, "shell": "rm"})


@pytest.mark.parametrize(
    "model_cls,payload,field",
    [
        (BudgetSnapshot, _SNAPSHOT, "consumed_tokens"),
        (BudgetToken, _TOKEN, "precharged_tokens"),
    ],
)
def test_frozen_rejects_assignment(model_cls, payload, field) -> None:  # type: ignore[no-untyped-def]
    instance = model_cls.model_validate(payload)
    with pytest.raises(ValidationError):
        setattr(instance, field, getattr(instance, field))


# --- BudgetSnapshot invariants (AC-6 + AC-17) ---


def test_budget_snapshot_happy() -> None:
    assert BudgetSnapshot.model_validate(_SNAPSHOT).consumed_tokens == 100


def test_budget_snapshot_keyset_pinned() -> None:
    expected = {
        "consumed_tokens",
        "consumed_dollars",
        "outstanding_tokens",
        "cap_tokens",
        "cap_dollars",
    }
    assert set(BudgetSnapshot.model_validate(_SNAPSHOT).model_dump()) == expected


def test_budget_snapshot_consumed_plus_outstanding_exceeds_cap_rejected() -> None:
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate(
            {**_SNAPSHOT, "consumed_tokens": 800, "outstanding_tokens": 300}
        )


def test_budget_snapshot_consumed_dollars_exceeds_cap_rejected() -> None:
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate({**_SNAPSHOT, "consumed_dollars": Decimal("2.0")})


def test_budget_snapshot_negative_dollars_rejected() -> None:
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate({**_SNAPSHOT, "consumed_dollars": Decimal("-0.5")})


def test_budget_snapshot_negative_tokens_rejected() -> None:  # AC-17
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate({**_SNAPSHOT, "consumed_tokens": -1})


# --- BudgetToken (AC-7 + AC-13 + AC-17 + AC-18) ---


def test_budget_token_happy() -> None:
    bt = BudgetToken.model_validate(_TOKEN)
    assert bt.precharged_tokens == 5_000
    assert bt.precharged_dollars == Decimal("0.03")


def test_budget_token_keyset_pinned() -> None:
    # _marker is a PrivateAttr — must NOT appear in model_dump().
    expected = {"precharged_tokens", "precharged_dollars", "issued_at"}
    assert set(BudgetToken.model_validate(_TOKEN).model_dump()) == expected


def test_budget_token_negative_precharged_tokens_rejected() -> None:  # AC-17
    with pytest.raises(ValidationError):
        BudgetToken.model_validate({**_TOKEN, "precharged_tokens": -1})


def test_budget_token_issued_at_naive_datetime_rejected() -> None:  # AC-13
    with pytest.raises(ValidationError):
        BudgetToken.model_validate({**_TOKEN, "issued_at": datetime(2026, 1, 1)})


def test_budget_token_marker_default() -> None:  # AC-18
    assert BudgetToken.model_validate(_TOKEN)._marker == "budget_token"


def test_budget_token_marker_not_serialized() -> None:  # AC-18 — PrivateAttr ⇒ excluded
    assert "_marker" not in BudgetToken.model_validate(_TOKEN).model_dump()


def test_budget_token_forged_marker_rejected() -> None:  # AC-18 — capability cannot be injected
    with pytest.raises(ValidationError):
        BudgetToken.model_validate({**_TOKEN, "_marker": "forged"})
