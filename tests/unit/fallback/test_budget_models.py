"""Phase-4 — happy/sad-path tests for ``BudgetSnapshot`` + ``BudgetToken``.

S1-04 shipped the original model shapes; **S2-05 reshaped them** to
match the issuer's needs (``LlmInvocationGuard(max_tokens=, max_dollars=)``
plus ``outstanding_tokens: dict[BudgetTokenId, TokenCount]`` plus the
projection fields). Per Global Rule 7 (surface conflicts) the rename
``cap_tokens`` → ``max_tokens`` is documented in the S2-05 attempt log; the
old ``_marker`` ``PrivateAttr`` was dropped per S2-05 AC-2 Note (it never
delivered the schema guard a draft claimed).

The RAG-side models stay under ``tests/unit/rag/test_models.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from codegenie.fallback.budget import BudgetSnapshot, BudgetToken
from codegenie.types.identifiers import BudgetTokenId

_UTC_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_TOKEN = {
    "id": "a" * 32,
    "precharged_tokens": 5_000,
    "precharged_dollars": Decimal("0.03"),
    "issued_at": _UTC_NOW,
}
_SNAPSHOT = {
    "consumed_tokens": 100,
    "consumed_dollars": Decimal("0.5"),
    "max_tokens": 1_000,
    "max_dollars": Decimal("1.5"),
    "outstanding_tokens": {},
    "outstanding_dollars": Decimal("0"),
}


# --- extra="forbid" / frozen, parametrized over both budget models ----------


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


# --- BudgetSnapshot invariants ----------------------------------------------


def test_budget_snapshot_happy() -> None:
    assert BudgetSnapshot.model_validate(_SNAPSHOT).consumed_tokens == 100


def test_budget_snapshot_keyset_pinned() -> None:
    """The five stored fields plus two computed projection fields."""
    expected = {
        "consumed_tokens",
        "consumed_dollars",
        "max_tokens",
        "max_dollars",
        "outstanding_tokens",
        "outstanding_dollars",
        "remaining_tokens",
        "remaining_dollars",
    }
    assert set(BudgetSnapshot.model_validate(_SNAPSHOT).model_dump()) == expected


def test_budget_snapshot_remaining_tokens_projection() -> None:
    """``remaining_tokens == max - consumed - sum(outstanding)``."""
    snap = BudgetSnapshot.model_validate(
        {
            **_SNAPSHOT,
            "consumed_tokens": 100,
            "outstanding_tokens": {BudgetTokenId("b" * 32): 200},
        }
    )
    assert snap.remaining_tokens == 1_000 - 100 - 200


def test_budget_snapshot_remaining_dollars_projection() -> None:
    """``remaining_dollars`` debits both consumed and outstanding."""
    snap = BudgetSnapshot.model_validate(
        {
            **_SNAPSHOT,
            "consumed_dollars": Decimal("0.5"),
            "outstanding_dollars": Decimal("0.2"),
        }
    )
    assert snap.remaining_dollars == Decimal("1.5") - Decimal("0.5") - Decimal("0.2")


def test_budget_snapshot_consumed_plus_outstanding_exceeds_max_rejected() -> None:
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate(
            {
                **_SNAPSHOT,
                "consumed_tokens": 800,
                "outstanding_tokens": {BudgetTokenId("c" * 32): 300},
            }
        )


def test_budget_snapshot_consumed_dollars_exceeds_max_rejected() -> None:
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate({**_SNAPSHOT, "consumed_dollars": Decimal("2.0")})


def test_budget_snapshot_negative_dollars_rejected() -> None:
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate({**_SNAPSHOT, "consumed_dollars": Decimal("-0.5")})


def test_budget_snapshot_negative_tokens_rejected() -> None:
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate({**_SNAPSHOT, "consumed_tokens": -1})


# --- BudgetToken -------------------------------------------------------------


def test_budget_token_happy() -> None:
    bt = BudgetToken.model_validate(_TOKEN)
    assert bt.precharged_tokens == 5_000
    assert bt.precharged_dollars == Decimal("0.03")
    assert bt.id == "a" * 32


def test_budget_token_keyset_pinned() -> None:
    """Four stored fields; S2-05 added ``id`` and dropped ``_marker``."""
    expected = {"id", "precharged_tokens", "precharged_dollars", "issued_at"}
    assert set(BudgetToken.model_validate(_TOKEN).model_dump()) == expected


def test_budget_token_negative_precharged_tokens_rejected() -> None:
    with pytest.raises(ValidationError):
        BudgetToken.model_validate({**_TOKEN, "precharged_tokens": -1})


def test_budget_token_issued_at_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError):
        BudgetToken.model_validate({**_TOKEN, "issued_at": datetime(2026, 1, 1)})
