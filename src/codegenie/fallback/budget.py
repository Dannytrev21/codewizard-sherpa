"""Phase-4 S1-04 — ``BudgetSnapshot`` + ``BudgetToken`` shapes.

The *issuer* (``LlmInvocationGuard.precharge`` / ``.reconcile``) lands in
S2-05; this story ships the data shapes alone. Keeping them in the
``fallback/`` package (rather than under ``rag/``) reflects the arch
boundary: ``LlmInvocationGuard`` is the LLM-fallback choke point, not a
RAG-side primitive.

``BudgetToken`` is the function-signature **capability** gating LLM spend
(ADR-0010): every leaf-LLM-port entry function carries a ``BudgetToken``
argument so the import-linter contract + S2-05 AST-walk can prove no
unguarded call site exists. The ``_marker`` is a Pydantic v2 ``PrivateAttr``
(ADR-0010 §Decision calls it "private"): absent from ``model_dump()``,
not constructor-settable, and not protected by ``frozen=True``. AC-18's
tests pin this contract.

References:
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0010-llm-invocation-guard-budget-token-capability.md``
- ``docs/phases/04-vuln-llm-fallback-rag/phase-arch-design.md §Component 5``
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    model_validator,
)

from codegenie.types.datetime import TzAwareDatetime
from codegenie.types.identifiers import TokenCount

_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class BudgetSnapshot(BaseModel):
    """Name-stable projection Phase 5 consumes from ``LlmInvocationGuard``.

    The invariant ``consumed_tokens + outstanding_tokens <= cap_tokens`` is
    the load-bearing relation Phase 5's running-total projection depends
    on; rejecting illegal snapshots at construction makes silent overspend
    impossible. ``TokenCount`` non-negativity is enforced both by
    ``parse_token_count`` at the boundary AND ``Field(ge=0)`` here —
    ``NewType`` is opaque to Pydantic v2 (it sees the base ``int``).
    """

    model_config = _FROZEN_FORBID
    consumed_tokens: Annotated[TokenCount, Field(ge=0)]
    consumed_dollars: Decimal
    outstanding_tokens: Annotated[TokenCount, Field(ge=0)]
    cap_tokens: Annotated[TokenCount, Field(ge=0)]
    cap_dollars: Decimal

    @model_validator(mode="after")
    def _invariants(self) -> Self:
        if self.consumed_tokens + self.outstanding_tokens > self.cap_tokens:
            raise ValueError(
                f"consumed_tokens ({self.consumed_tokens}) + outstanding_tokens "
                f"({self.outstanding_tokens}) exceeds cap_tokens ({self.cap_tokens})"
            )
        if self.consumed_dollars > self.cap_dollars:
            raise ValueError(
                f"consumed_dollars ({self.consumed_dollars}) exceeds cap_dollars "
                f"({self.cap_dollars})"
            )
        if self.consumed_dollars < 0:
            raise ValueError(f"consumed_dollars ({self.consumed_dollars}) must be non-negative")
        return self


class BudgetToken(BaseModel):
    """Function-signature capability gating LLM spend (ADR-0010).

    No ``id`` field — ADR-0010 keeps tokens id-less; ``LlmInvocationGuard``
    keys ``outstanding_tokens: dict[BudgetTokenId, TokenCount]`` by an
    *external* ``BudgetTokenId`` (arch §Component 5 State). If S2-05 finds
    the token genuinely needs to carry its own id, that is an ADR-0010
    amendment surfaced in S2-05 — not this story.

    ``_marker`` is a ``PrivateAttr``: ADR-0010 §Decision explicitly calls
    it a "private" marker. A leading-underscore annotation in Pydantic v2
    is *not* a validated field — it is absent from ``model_dump()``, not
    constructor-settable, and is the identity tag S2-05's import-linter
    contract + AST-walk use to recognise a capability flow.
    """

    model_config = _FROZEN_FORBID
    precharged_tokens: Annotated[TokenCount, Field(ge=0)]
    precharged_dollars: Decimal
    issued_at: TzAwareDatetime
    _marker: Literal["budget_token"] = PrivateAttr(default="budget_token")


__all__ = ("BudgetSnapshot", "BudgetToken")
