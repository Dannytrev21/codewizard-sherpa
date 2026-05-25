"""Phase-4 S3-01 — ``LeafLlm`` Protocol + ``LeafResponse`` Pydantic model.

The single seam between Phase 4 and any LLM provider. Concrete adapters
(``AnthropicLeafAdapter`` lands in S3-02; a second vendor per
[production ADR-0020](../../../../../docs/production/adrs/0020-leaf-agents-sdk.md))
live behind it; downstream code (``FallbackTier``, plugin adapters, retry
logic) sees only this typed surface.

The :meth:`LeafLlm.invoke` signature is the load-bearing contract that pins
three commitments in the type system simultaneously:

1. The prompt body is a :class:`~codegenie.fallback.fence.prompt_builder.FencedPromptBody`
   newtype minted only by :class:`~codegenie.fallback.fence.prompt_builder.PromptBuilder`
   (S2-04 AST-walk asserted): free-prose injection at the leaf is structurally
   impossible.
2. The schema is a :class:`pydantic.TypeAdapter` of
   :data:`~codegenie.fallback.plan_proposal.PlanProposal` so the SDK boundary
   validates before any byte enters Python (`response_format` semantics —
   ADR-0001).
3. ``token: BudgetToken`` is keyword-only and required — calling without one
   is a ``TypeError`` at call construction (ADR-0010 §Consequences). The
   ``import-linter`` ``forbidden`` contract scopes
   :mod:`codegenie.fallback.budget_token` to the two-frame
   ``FallbackTier → LeafLlm.invoke`` flow.

Module purity (AC-4 / ADR-0003 path-scoped fence): only stdlib + ``pydantic``
+ ``codegenie.*`` imports. No HTTP / SDK / socket / ssl modules. Enforced by
``tests/unit/fallback/test_port_module_purity.py``.

References:
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0001-plan-proposal-closed-sum-type.md``
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0003-path-scoped-fence-amendment.md``
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0010-llm-invocation-guard-budget-token-capability.md``
- ``docs/phases/04-vuln-llm-fallback-rag/phase-arch-design.md §Component 4``
- ``docs/production/adrs/0020-leaf-agents-sdk.md`` (multi-vendor seam)
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from codegenie.fallback.budget_token import BudgetToken
from codegenie.fallback.fence.prompt_builder import FencedPromptBody, TrustedPrompt
from codegenie.fallback.plan_proposal import PlanProposal
from codegenie.types.identifiers import LeafResponseId, ModelId, TokenCount

__all__ = ("LeafLlm", "LeafResponse")

_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")
"""Mirror the codebase-wide ``frozen=True, extra="forbid"`` convention used by
``PlanProposal*`` variants and ``BudgetSnapshot`` — immutable instances,
strict extra-key rejection."""


class LeafResponse(BaseModel):
    """One leaf-LLM invocation's typed result.

    The four token-count fields carry ``Annotated[TokenCount, Field(ge=0)]``
    — **not** bare ``TokenCount``. ``TokenCount`` is a ``NewType``; Pydantic
    v2 resolves a ``NewType`` to its supertype (``int``) and applies **no**
    runtime validation. The ``Field(ge=0)`` constraint is what makes the
    negative-token rejection real. To ``mypy --strict`` the field type is
    still ``TokenCount`` (``Annotated`` is transparent to the type checker).

    ``stop_reason`` is a closed ``Literal[...]`` of exactly the four values
    Anthropic's SDK returns; adding a fifth value is an ADR amendment.

    Equality is structural and matters for S6-07's determinism property test:
    byte-identical-field instances compare ``==``. ``LeafResponse`` is **not**
    hashable — ``plan`` may be a
    :class:`~codegenie.fallback.plan_proposal.PlanProposalCallsiteRewrite`
    whose ``files: list[...]`` field makes ``hash()`` raise. Frozen Pydantic
    models support ``==`` regardless of field hashability, and ``==`` is what
    a determinism test needs.

    Do **not** expose a ``raw_sdk_response: Any`` escape hatch: the whole
    point of the Protocol is that the SDK stays contained in the adapter.
    """

    model_config = _FROZEN_FORBID
    plan: PlanProposal
    tokens_in: Annotated[TokenCount, Field(ge=0)]
    cache_read_tokens: Annotated[TokenCount, Field(ge=0)]
    cache_creation_tokens: Annotated[TokenCount, Field(ge=0)]
    tokens_out: Annotated[TokenCount, Field(ge=0)]
    model: ModelId
    stop_reason: Literal["end_turn", "max_tokens", "stop_sequence", "tool_use"]
    response_id: LeafResponseId


class LeafLlm(Protocol):
    """The single SDK-free seam between Phase 4 and any LLM provider.

    Default ``Protocol`` (i.e. **not** ``@runtime_checkable``). Calling
    ``isinstance(x, LeafLlm)`` raises ``TypeError`` — the load-bearing pin is
    structural type-checking, not runtime introspection.

    Signature pins three contracts simultaneously (see module docstring):

    * ``user_message: FencedPromptBody`` — only
      :class:`~codegenie.fallback.fence.prompt_builder.PromptBuilder` mints
      this newtype (S2-04 AST-walk asserted), so free-prose injection at the
      leaf is structurally impossible.
    * ``schema: TypeAdapter[PlanProposal]`` — passes
      ``schema.json_schema()`` to the SDK as ``response_format`` and
      ``schema.validate_json(...)`` at the boundary (ADR-0001). ``PlanProposal``
      is an ``Annotated`` union *alias* (not a class) so ``type[PlanProposal]``
      resolves to a single variant class with no ``.model_json_schema()`` —
      ``TypeAdapter`` is the Pydantic-v2 carrier.
    * ``token: BudgetToken`` — keyword-only and required. Omitting it is a
      ``TypeError`` at call construction (ADR-0010 §Consequences). The
      ``import-linter`` ``forbidden`` contract pins the two-frame scope.
    """

    async def invoke(
        self,
        system_prompt: TrustedPrompt,
        user_message: FencedPromptBody,
        *,
        schema: TypeAdapter[PlanProposal],
        token: BudgetToken,
    ) -> LeafResponse: ...
