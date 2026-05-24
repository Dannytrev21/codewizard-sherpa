"""Phase-4 S2-05 — ``LlmInvocationGuard`` + ``BudgetSnapshot`` (financial
circuit breaker for the LLM-fallback tier).

The :class:`~codegenie.fallback.budget_token.BudgetToken` capability lives in
its own submodule so the ``import-linter`` ``forbidden`` contract can pin
its three non-test importers structurally (``codegenie.fallback.budget``,
``codegenie.fallback.tier``, ``codegenie.fallback.leaf.anthropic_adapter``).

This module ships:

- :class:`BudgetSnapshot` — name-stable projection Phase 5's ``GateRunner``
  reads across retries (forward-compat surface; arch §Forward-compat row
  ``LlmInvocationGuard.running_total``). Field set is fixed by S2-05 AC-3
  and pinned by ``tests/integration/test_phase5_contract_snapshot.py`` in
  the eventual S7-10 contract snapshot.
- :class:`BudgetExceeded` — structured typed exception with a three-member
  ``reason`` literal and per-reason numeric context (token-cap reasons carry
  ``int``, the dollar-cap reason carries ``Decimal`` — no ``int | Decimal``
  sloppiness; S2-05 AC-17).
- :class:`BudgetReconcileUnknownToken` — raised for a token the guard never
  minted (forged or cross-workflow-leaked id; AC-6 third branch).
- :class:`LlmInvocationGuard` — the issuer / circuit breaker. ``precharge``
  mints a :class:`~codegenie.fallback.budget_token.BudgetToken` after every
  cap check passes; ``reconcile`` is idempotent on ``token.id``;
  ``running_total`` is a pure projection.

ADR-0010 §Decision sets the defaults this module hard-codes:
``max_tokens_per_workflow=250_000``, ``max_dollars_per_workflow=$1.50``,
``per_call_max_tokens=32_000``. S7-04's ``plugin.yaml`` overrides these as
configuration knobs; this module exposes them as constructor parameters.

References:
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0010-llm-invocation-guard-budget-token-capability.md``
- ``docs/phases/04-vuln-llm-fallback-rag/phase-arch-design.md §Component 5``
- ``docs/phases/04-vuln-llm-fallback-rag/stories/S2-05-llm-invocation-guard-budget-token.md``
- ``docs/production/adrs/0024-cost-observability-end-to-end.md``
- ``docs/production/adrs/0025-per-workflow-cost-cap.md``
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from codegenie.fallback.budget_token import BudgetToken
from codegenie.plugins.events import (
    BudgetCapExceeded,
    BudgetPrecharged,
    BudgetReconciled,
    BudgetReconciledDuplicate,
    BudgetUnknownTokenReconcile,
    EventLog,
)
from codegenie.types.identifiers import BudgetTokenId, EventId, TokenCount

_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

# --- Defaults (ADR-0010 §Decision) ------------------------------------------

_DEFAULT_MAX_TOKENS: Final[int] = 250_000
_DEFAULT_MAX_DOLLARS: Final[Decimal] = Decimal("1.50")
_DEFAULT_PER_CALL_MAX_TOKENS: Final[int] = 32_000

# ADR-0010 §Tradeoffs row 1 — uncalibrated Q1-2026 estimate. Anthropic
# Sonnet-class input is ~$0.003 / 1K tokens; ``precharge`` runs *before*
# the call so only the input cost is known. S7-04 ``plugin.yaml``
# overrides this constant per ADR-0010 §Consequences.
_DEFAULT_DOLLARS_PER_TOKEN: Final[Decimal] = Decimal("0.000003")

_BudgetCapReason = Literal[
    "per_call_max_exceeded",
    "workflow_max_tokens_exceeded",
    "workflow_max_dollars_exceeded",
]

_EVENT_ID_PREFIX: Final[str] = "01HBDG"


# --- BudgetSnapshot ---------------------------------------------------------


class BudgetSnapshot(BaseModel):
    """Name-stable projection of one ``LlmInvocationGuard``'s current state.

    Phase 5's ``GateRunner`` reads this across retries; S7-10 pins the
    field set in ``tests/integration/test_phase5_contract_snapshot.py``.
    Adding a field is allowed (additive); removing or renaming requires a
    phase-amendment ADR — see ADR-0010 §Reversibility.

    Invariants:

    * Token conservation — ``consumed_tokens + sum(outstanding_tokens) +
      remaining_tokens == max_tokens``.
    * Dollar conservation — ``consumed_dollars + outstanding_dollars +
      remaining_dollars == max_dollars`` (where ``outstanding_dollars`` is
      the dollar sum of the precharged-but-not-reconciled tokens).
    """

    model_config = _FROZEN_FORBID
    consumed_tokens: Annotated[TokenCount, Field(ge=0)]
    consumed_dollars: Decimal
    max_tokens: Annotated[TokenCount, Field(ge=0)]
    max_dollars: Decimal
    outstanding_tokens: dict[BudgetTokenId, TokenCount]
    outstanding_dollars: Decimal

    @computed_field  # type: ignore[prop-decorator]
    @property
    def remaining_tokens(self) -> TokenCount:
        """``max_tokens − consumed_tokens − sum(outstanding_tokens)``.

        Computed so the snapshot cannot encode an inconsistent
        ``remaining`` versus ``consumed + outstanding``.
        """
        outstanding_sum = sum(self.outstanding_tokens.values(), 0)
        return TokenCount(self.max_tokens - self.consumed_tokens - outstanding_sum)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def remaining_dollars(self) -> Decimal:
        """``max_dollars − consumed_dollars − outstanding_dollars``.

        Debits precharged-but-not-reconciled dollars rather than
        ``max_dollars − consumed_dollars`` — which would over-report
        available budget by the still-outstanding precharge.
        """
        return self.max_dollars - self.consumed_dollars - self.outstanding_dollars

    @model_validator(mode="after")
    def _invariants(self) -> Self:
        if self.consumed_dollars < 0:
            raise ValueError(f"consumed_dollars ({self.consumed_dollars}) must be non-negative")
        if self.outstanding_dollars < 0:
            raise ValueError(
                f"outstanding_dollars ({self.outstanding_dollars}) must be non-negative"
            )
        outstanding_token_sum = sum(self.outstanding_tokens.values(), 0)
        if self.consumed_tokens + outstanding_token_sum > self.max_tokens:
            raise ValueError(
                f"consumed_tokens ({self.consumed_tokens}) + outstanding "
                f"({outstanding_token_sum}) exceeds max_tokens ({self.max_tokens})"
            )
        if self.consumed_dollars + self.outstanding_dollars > self.max_dollars:
            raise ValueError(
                f"consumed_dollars ({self.consumed_dollars}) + outstanding "
                f"({self.outstanding_dollars}) exceeds max_dollars ({self.max_dollars})"
            )
        return self


# --- Exceptions -------------------------------------------------------------


class BudgetExceeded(Exception):
    """A ``precharge`` cap check refused the call.

    Per ADR-0010 §Decision the cap is a *hard* per-workflow ceiling — token
    or dollar. The exception carries a structured ``reason: Literal`` and
    per-reason numeric context so callers (notably ``FallbackTier.run`` in
    S6-01) can project to ``RecipeApplication.Refused(reason=
    BUDGET_EXCEEDED, details={...})`` without parsing strings.

    Per-reason numeric typing (S2-05 AC-17): the two token-cap reasons
    carry ``int`` ``projected``/``max``; ``workflow_max_dollars_exceeded``
    carries ``Decimal`` ``projected``/``max``. No ``int | Decimal``
    primitive-union sloppiness.
    """

    def __init__(
        self,
        *,
        reason: _BudgetCapReason,
        projected: int | Decimal,
        max: int | Decimal,
    ) -> None:
        self.reason: _BudgetCapReason = reason
        self.projected: int | Decimal = projected
        self.max: int | Decimal = max
        super().__init__(f"budget cap exceeded ({reason}): projected={projected}, max={max}")


class BudgetReconcileUnknownToken(Exception):
    """``reconcile`` was called with a token the guard never minted.

    The guard only mints tokens through ``precharge``, so an unknown
    ``token.id`` is always either a hand-built fixture (test) or a
    cross-workflow leak. Either way the reconcile attempt is refused —
    silently absorbing it would let forged tokens credit / debit the
    budget. ADR-0010 §Decision treats this as a guard violation, not a
    duplicate-call edge.
    """

    def __init__(self, token_id: BudgetTokenId) -> None:
        self.token_id: BudgetTokenId = token_id
        super().__init__(f"reconcile called with unknown token id {token_id!r}")


# --- Helpers ----------------------------------------------------------------


def _new_event_id() -> EventId:
    """Mint a deterministic-shape event id for one budget-event emission.

    Test assertions only check that *some* event exists for a given
    ``event_type``; the exact id is intentionally unpinned so the helper
    stays a private implementation detail (the ULID-like ``01HBDG`` prefix
    is operator-friendly ``grep`` bait — mirrors S2-01's ``_new_event_id``
    pattern in ``provenance_gate.py``).
    """
    return EventId(_EVENT_ID_PREFIX + uuid.uuid4().hex[:20].upper())


def _now() -> datetime:
    """Placeholder timestamp; :meth:`EventLog._stamp` overwrites with the
    log's injected clock before the bytes hit disk."""
    return datetime.now(UTC)


# --- LlmInvocationGuard -----------------------------------------------------


class LlmInvocationGuard:
    """Per-workflow financial circuit breaker (ADR-0010 Capability +
    Circuit Breaker patterns).

    Constructor parameters are keyword-only — the default values are the
    ADR-0010 §Decision numbers and are intentionally *not* readable from
    environment variables (ADR-0010 §Consequences row 11 — config flows
    via ``plugin.yaml`` in S7-04 only; no ``CODEGENIE_BUDGET_*`` escape).

    Internal state is per-instance and not threadsafe across event loops:
    Phase 4 is single-event-loop and ``precharge`` / ``reconcile`` are
    *synchronous* with no suspension point, so the operations are atomic
    by construction. Phase 9 (Temporal workers) is when multi-loop
    locking becomes a real concern — surfaced in S2-05 AC-14 and ADR-0010
    §Internal structure.

    The token capability flows through exactly two frames:
    ``FallbackTier → LeafLlm.invoke`` (S6-01 + S3-02). The
    ``[[tool.importlinter.contracts]]`` ``"phase-4 BudgetToken scope is
    two-frame"`` in ``pyproject.toml`` is the structural guard — see
    :mod:`codegenie.fallback.budget_token`.
    """

    __slots__ = (
        "_consumed_dollars",
        "_consumed_tokens",
        "_dollars_per_token",
        "_event_log",
        "_max_dollars",
        "_max_tokens",
        "_outstanding",
        "_per_call_max_tokens",
        "_reconciled_ids",
    )

    def __init__(
        self,
        *,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        max_dollars: Decimal = _DEFAULT_MAX_DOLLARS,
        per_call_max_tokens: int = _DEFAULT_PER_CALL_MAX_TOKENS,
        event_log: EventLog,
        dollars_per_token: Decimal = _DEFAULT_DOLLARS_PER_TOKEN,
    ) -> None:
        if max_tokens < 0:
            raise ValueError(f"max_tokens ({max_tokens}) must be non-negative")
        if max_dollars < Decimal("0"):
            raise ValueError(f"max_dollars ({max_dollars}) must be non-negative")
        if per_call_max_tokens <= 0:
            raise ValueError(f"per_call_max_tokens ({per_call_max_tokens}) must be positive")
        if dollars_per_token < Decimal("0"):
            raise ValueError(f"dollars_per_token ({dollars_per_token}) must be non-negative")
        self._max_tokens: int = max_tokens
        self._max_dollars: Decimal = max_dollars
        self._per_call_max_tokens: int = per_call_max_tokens
        self._dollars_per_token: Decimal = dollars_per_token
        self._event_log: EventLog = event_log
        self._consumed_tokens: int = 0
        self._consumed_dollars: Decimal = Decimal("0")
        # Store the *whole* BudgetToken (one source of truth — parallel
        # id→count + id→dollars dicts can desync; S2-05 §"Store the whole
        # BudgetToken"). Both ``precharged_tokens`` and
        # ``precharged_dollars`` are needed for the dollar projection and
        # the dollar cap.
        self._outstanding: dict[BudgetTokenId, BudgetToken] = {}
        self._reconciled_ids: set[BudgetTokenId] = set()

    # --- Public surface -----------------------------------------------------

    def precharge(self, requested_tokens: int) -> BudgetToken:
        """Mint a :class:`BudgetToken` if every cap check passes.

        Cap-check order (fixed and tested — S2-05 AC-5): ``requested > 0``
        → ``per_call_max`` → ``workflow_max_tokens`` →
        ``workflow_max_dollars``. A call violating two caps surfaces the
        *first* in this order so ``BudgetExceeded.reason`` is
        deterministic.

        On any cap failure: emit :class:`BudgetCapExceeded` first, then
        raise :class:`BudgetExceeded`. ``_outstanding`` is **not** mutated
        — the precharge is a no-op on failure (S2-05 AC-14 (iii) pins this
        as ``running_total()`` byte-identical before and after).
        """
        if requested_tokens <= 0:
            raise ValueError(f"requested_tokens ({requested_tokens}) must be positive")

        if requested_tokens > self._per_call_max_tokens:
            self._emit_cap_exceeded("per_call_max_exceeded")
            raise BudgetExceeded(
                reason="per_call_max_exceeded",
                projected=requested_tokens,
                max=self._per_call_max_tokens,
            )

        outstanding_tokens_sum = sum(t.precharged_tokens for t in self._outstanding.values())
        projected_tokens = self._consumed_tokens + outstanding_tokens_sum + requested_tokens
        if projected_tokens > self._max_tokens:
            self._emit_cap_exceeded("workflow_max_tokens_exceeded")
            raise BudgetExceeded(
                reason="workflow_max_tokens_exceeded",
                projected=projected_tokens,
                max=self._max_tokens,
            )

        precharged_dollars = self._dollars_per_token * requested_tokens
        outstanding_dollars_sum = sum(
            (t.precharged_dollars for t in self._outstanding.values()),
            Decimal("0"),
        )
        projected_dollars = self._consumed_dollars + outstanding_dollars_sum + precharged_dollars
        if projected_dollars > self._max_dollars:
            self._emit_cap_exceeded("workflow_max_dollars_exceeded")
            raise BudgetExceeded(
                reason="workflow_max_dollars_exceeded",
                projected=projected_dollars,
                max=self._max_dollars,
            )

        token_id = BudgetTokenId(uuid.uuid4().hex)
        token = BudgetToken(
            id=token_id,
            precharged_tokens=TokenCount(requested_tokens),
            precharged_dollars=precharged_dollars,
            issued_at=_now(),
        )
        self._outstanding[token_id] = token
        self._event_log.emit_internal(
            BudgetPrecharged(
                event_id=_new_event_id(),
                workflow_id=self._event_log.workflow_id,
                timestamp=_now(),
                token_id=token_id,
                precharged_tokens=TokenCount(requested_tokens),
                precharged_dollars=precharged_dollars,
            )
        )
        return token

    def reconcile(
        self,
        token: BudgetToken,
        *,
        actual_in: int,
        actual_out: int,
        actual_dollars: Decimal,
    ) -> None:
        """Settle a previously-minted token against actual usage.

        Three branches (S2-05 AC-6):

        * First call (``token.id`` in ``_outstanding``) — remove the token,
          fold actuals into consumption totals, mark id as reconciled,
          emit :class:`BudgetReconciled`.
        * Duplicate (``token.id`` in ``_reconciled_ids``) — no-op, emit
          :class:`BudgetReconciledDuplicate`. ADR-0010 §Tradeoffs row 3 —
          Phase-5 retry envelopes may legitimately replay.
        * Unknown (neither) — emit :class:`BudgetUnknownTokenReconcile`,
          then raise :class:`BudgetReconcileUnknownToken`. A guard against
          forged tokens.
        """
        if actual_in < 0:
            raise ValueError(f"actual_in ({actual_in}) must be non-negative")
        if actual_out < 0:
            raise ValueError(f"actual_out ({actual_out}) must be non-negative")
        if actual_dollars < Decimal("0"):
            raise ValueError(f"actual_dollars ({actual_dollars}) must be non-negative")

        token_id = token.id
        if token_id in self._outstanding:
            del self._outstanding[token_id]
            self._consumed_tokens += actual_in + actual_out
            self._consumed_dollars += actual_dollars
            self._reconciled_ids.add(token_id)
            self._event_log.emit_internal(
                BudgetReconciled(
                    event_id=_new_event_id(),
                    workflow_id=self._event_log.workflow_id,
                    timestamp=_now(),
                    token_id=token_id,
                    actual_in=TokenCount(actual_in),
                    actual_out=TokenCount(actual_out),
                    actual_dollars=actual_dollars,
                )
            )
            return

        if token_id in self._reconciled_ids:
            self._event_log.emit_internal(
                BudgetReconciledDuplicate(
                    event_id=_new_event_id(),
                    workflow_id=self._event_log.workflow_id,
                    timestamp=_now(),
                    token_id=token_id,
                )
            )
            return

        # Unknown — emit before raise so the audit trail catches forged
        # ids even if the caller swallows the exception.
        self._event_log.emit_internal(
            BudgetUnknownTokenReconcile(
                event_id=_new_event_id(),
                workflow_id=self._event_log.workflow_id,
                timestamp=_now(),
                token_id=token_id,
            )
        )
        raise BudgetReconcileUnknownToken(token_id)

    def running_total(self) -> BudgetSnapshot:
        """Pure projection over the current internal state.

        No side effects; can be called arbitrarily many times (S2-05 AC-7
        (iv)). The ``outstanding_tokens`` projection materialises a fresh
        ``dict`` each call — callers that mutate the returned dict do not
        affect the guard.
        """
        outstanding_token_view: dict[BudgetTokenId, TokenCount] = {
            tid: tok.precharged_tokens for tid, tok in self._outstanding.items()
        }
        outstanding_dollars_sum = sum(
            (t.precharged_dollars for t in self._outstanding.values()),
            Decimal("0"),
        )
        return BudgetSnapshot(
            consumed_tokens=TokenCount(self._consumed_tokens),
            consumed_dollars=self._consumed_dollars,
            max_tokens=TokenCount(self._max_tokens),
            max_dollars=self._max_dollars,
            outstanding_tokens=outstanding_token_view,
            outstanding_dollars=outstanding_dollars_sum,
        )

    # --- Private helpers ----------------------------------------------------

    def _emit_cap_exceeded(self, reason: _BudgetCapReason) -> None:
        self._event_log.emit_internal(
            BudgetCapExceeded(
                event_id=_new_event_id(),
                workflow_id=self._event_log.workflow_id,
                timestamp=_now(),
                reason=reason,
            )
        )


__all__ = (
    "BudgetExceeded",
    "BudgetReconcileUnknownToken",
    "BudgetSnapshot",
    "BudgetToken",
    "LlmInvocationGuard",
)
