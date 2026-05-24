"""Phase-4 S2-05 — the ``BudgetToken`` capability (its own submodule).

Homed in a dedicated submodule so the ``import-linter`` ``forbidden`` contract
can express the scope rule at the module level (the natural granularity
``import-linter`` operates on — see story S2-05 AC-11 / ADR-0010). The only
non-test importers of this module are:

- ``codegenie.fallback.budget`` — the issuer (`LlmInvocationGuard`).
- ``codegenie.fallback.tier`` — Phase-4 S6-01 fallback pipeline.
- ``codegenie.fallback.leaf.anthropic_adapter`` — Phase-4 S3-02 leaf adapter.

The contract in ``pyproject.toml`` is the **structural** guard. Direct
in-process construction of ``BudgetToken`` is forgeable — a hand-built dict
carrying the four fields validates fine. That residual risk is accepted (arch
§Design-patterns row 882 on ``SolvedExampleWriteCapability``: "Pydantic
constructors are public; named as what it is"). S2-05 validation notes pin
this honest framing in place of S1-04's removed ``_marker`` PrivateAttr —
a leading-underscore Pydantic v2 *private* attribute is absent from the JSON
schema and not validated, so it never delivered the guard a draft claimed.

References:
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0010-llm-invocation-guard-budget-token-capability.md``
- ``docs/phases/04-vuln-llm-fallback-rag/phase-arch-design.md §Component 5``
- ``docs/phases/04-vuln-llm-fallback-rag/stories/S2-05-llm-invocation-guard-budget-token.md``
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

from codegenie.types.datetime import TzAwareDatetime
from codegenie.types.identifiers import BudgetTokenId, TokenCount

_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class BudgetToken(BaseModel):
    """Function-signature capability gating LLM spend (ADR-0010).

    Carries its own ``id`` so ``LlmInvocationGuard.reconcile(token, ...)`` is
    a pure ``token.id`` lookup (arch §Component 5 keys ``outstanding_tokens``
    by ``BudgetTokenId``; reconcile is idempotent on ``BudgetTokenId``).

    Minted **only** by ``LlmInvocationGuard.precharge`` — the issuer fills
    ``id`` with ``uuid4().hex`` so the property test
    ``tests/property/test_budget_token_non_reuse.py`` proves no collisions and
    no MAC-leaking ``uuid1`` substitution.

    The token flows through *exactly two frames*: ``FallbackTier →
    LeafLlm.invoke``. The ``import-linter`` contract (pyproject ``[[tool.
    importlinter.contracts]]`` block named after this module) is the
    structural guard — see this module's docstring for the threat model.
    """

    model_config = _FROZEN_FORBID
    id: BudgetTokenId
    precharged_tokens: Annotated[TokenCount, Field(ge=0)]
    precharged_dollars: Decimal
    issued_at: TzAwareDatetime


__all__ = ("BudgetToken",)
