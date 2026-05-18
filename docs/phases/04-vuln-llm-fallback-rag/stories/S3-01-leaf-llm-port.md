# Story S3-01 — `LeafLlm` Protocol + `LeafResponse` model

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** Ready
**Effort:** S
**Depends on:** S2-04 (`PromptBuilder` mints `TrustedPrompt` + `FencedPromptBody`), S2-05 (`BudgetToken`), S1-02 (`PlanProposal`), S1-01 (`ModelId`, `TokenCount`, `LeafResponseId`)
**ADRs honored:** ADR-0001 (Phase 4 — `PlanProposal` closed sum type — adapter validates via SDK `response_format`), ADR-0010 (Phase 4 — `BudgetToken` required arg), ADR-0020 (production — multi-vendor seam preserved by the Protocol)

## Context

The `LeafLlm` Protocol is the single seam between Phase 4 and any LLM provider. Per `phase-arch-design.md §Component 4`, it is the *only* surface in the codebase that downstream code (`FallbackTier`, plugin adapters, retry logic) sees — concrete adapters (`AnthropicLeafAdapter` in S3-02; eventually a second vendor per production ADR-0020) live behind it. Landing the Protocol + `LeafResponse` first (with no SDK import) decouples the Port from the Adapter and lets every downstream test mock against a typed seam rather than against `anthropic.AsyncAnthropic`.

Critically, the method signature is the load-bearing contract that pins three commitments in the type system simultaneously: (1) the prompt body is a `FencedPromptBody` newtype minted only by `PromptBuilder` (S2-04 AST-walk asserted), so free-prose injection at the leaf is structurally impossible; (2) the schema is `type[PlanProposal]` so the SDK boundary validates before any byte enters Python; (3) `token: BudgetToken` is keyword-only and required — calling without one is a `mypy --strict` `TypeError` (ADR-0010 §Consequences).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 4 — LeafLlm Protocol + AnthropicLeafAdapter` (Public interface block; `LeafResponse` field list).
  - `../phase-arch-design.md §Stable contracts` (the `LeafLlm` Protocol is in the Phase-5-snapshot list).
  - `../phase-arch-design.md §Anti-patterns avoided` ("Capability passed through ten frames" — token flows through exactly two frames).
- **Phase ADRs:**
  - `../ADRs/0001-plan-proposal-closed-sum-type.md` — `response_format = PlanProposal.model_json_schema()` is the boundary validation; the Protocol's `schema: type[PlanProposal]` parameter pins this at the type level.
  - `../ADRs/0010-llm-invocation-guard-budget-token-capability.md` §Decision — keyword-only required `BudgetToken`; §Consequences "calling `LeafLlm.invoke` without a `BudgetToken` is a `TypeError` at call construction."
  - `../ADRs/0003-path-scoped-fence-amendment.md` — `port.py` does **not** import `anthropic`; the Protocol must be SDK-free so consumers outside `src/codegenie/fallback/leaf/anthropic_adapter.py` can import it.
- **Production ADRs:**
  - `../../../production/adrs/0020-leaf-agents-sdk.md` — the deferred multi-vendor seam; Protocol earns its keep here.
- **Source design:** `../final-design.md §Component 4 — LeafLlm`.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/result.py` — frozen Pydantic discriminated union convention; mirror for `LeafResponse`.
  - `src/codegenie/types/identifiers.py` — Phase-4 newtypes from S1-01 (`ModelId`, `TokenCount`, `LeafResponseId`) live here.
  - Any S2-04 module under `src/codegenie/fallback/prompt/` for the `TrustedPrompt` + `FencedPromptBody` import path (the AST-walking test that asserts `PromptBuilder` is the sole minter is the precedent S3-01 will inherit).

## Goal

Land the SDK-free `LeafLlm` Protocol and the `LeafResponse` frozen-extra-forbid Pydantic model so every downstream Phase-4 consumer programs against a typed seam, not against `anthropic.AsyncAnthropic`.

## Acceptance criteria

- [ ] AC-1 — `src/codegenie/fallback/leaf/__init__.py` and `src/codegenie/fallback/leaf/port.py` exist; `port.py` exports `LeafLlm` (`typing.Protocol`) and `LeafResponse` (Pydantic frozen-extra-forbid `BaseModel`) and nothing else; module-level `__all__ = ("LeafLlm", "LeafResponse")` is exact.
- [ ] AC-2 — `LeafLlm.invoke` signature is exactly:
  ```python
  async def invoke(
      self,
      system_prompt: TrustedPrompt,
      user_message: FencedPromptBody,
      *,
      schema: type[PlanProposal],
      token: BudgetToken,
  ) -> LeafResponse: ...
  ```
  The `*` keyword-only separator is mandatory; `schema` and `token` are keyword-only; both are required (no defaults).
- [ ] AC-3 — `LeafResponse` fields, in exact order, with these types: `plan: PlanProposal`, `tokens_in: TokenCount`, `cache_read_tokens: TokenCount`, `cache_creation_tokens: TokenCount`, `tokens_out: TokenCount`, `model: ModelId`, `stop_reason: Literal["end_turn", "max_tokens", "stop_sequence", "tool_use"]`, `response_id: LeafResponseId`. `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] AC-4 — `port.py` **does not** import `anthropic`, `httpx`, `requests`, or `urllib3`. AST source-scan test asserts the import set is exactly `{__future__, typing, pydantic, codegenie.types.identifiers, codegenie.fallback.plan_proposal, codegenie.fallback.prompt, codegenie.fallback.budget}` (names subject to Step-1/Step-2 modules' final locations — mirror the established paths).
- [ ] AC-5 — `LeafLlm` is `runtime_checkable=False` (default for `Protocol`). A negative test asserts that calling `isinstance(obj, LeafLlm)` raises `TypeError` (matches the existing newtype-isinstance pin convention from Phase-2 S1-05).
- [ ] AC-6 — `mypy --strict` rejects every one of these call shapes (subprocess-mypy meta-test):
  - `leaf.invoke(sp, body, schema=PlanProposal)` — missing required `token`.
  - `leaf.invoke(sp, body, token=tok)` — missing required `schema`.
  - `leaf.invoke(sp, body, PlanProposal, tok)` — positional `schema`/`token` (keyword-only violation).
  - `leaf.invoke("raw str", body, schema=PlanProposal, token=tok)` — raw `str` instead of `TrustedPrompt`.
  - `leaf.invoke(sp, "raw str", schema=PlanProposal, token=tok)` — raw `str` instead of `FencedPromptBody`.
  Test parametrizes over the 5 cases; each case must produce non-zero exit and a substring match in stderr/stdout.
- [ ] AC-7 — `LeafResponse(plan=..., tokens_in=TokenCount(-1), ...)` raises `pydantic.ValidationError` (negative `TokenCount` is rejected by the smart constructor S1-01 ships).
- [ ] AC-8 — `LeafResponse` is hashable (`frozen=True` Pydantic models hash by field tuple) — `hash(leaf_response)` returns an `int`; two equal responses hash equal. The hash invariant is consumed by the determinism property test in S6-07.
- [ ] AC-9 — `mypy --strict src/codegenie/fallback/leaf/port.py` clean. `ruff check`, `ruff format --check` clean on touched files.
- [ ] AC-10 — `tests/fence/test_only_leaf_imports_anthropic.py` (landed in S3-02) **passes vacuously** after this story — i.e., `port.py` does not import `anthropic`, and at this point no module in the repo does.
- [ ] AC-11 — The TDD red test exists, is committed, was demonstrably failing before implementation, and is now green.

## Implementation outline

1. Create `src/codegenie/fallback/leaf/__init__.py` (empty re-export from `port`).
2. Create `src/codegenie/fallback/leaf/port.py` with the `Protocol` class and `LeafResponse` model.
3. Wire `LeafResponse` to the Phase-4 newtypes (`TokenCount`, `ModelId`, `LeafResponseId`) and to `PlanProposal` (Step 1).
4. Add the import-set AST source-scan test under `tests/unit/fallback/test_port_module_purity.py`.
5. Add the subprocess-mypy meta-test under `tests/unit/fallback/test_leaf_protocol_typecheck.py` parametrizing the 5 reject cases.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/fallback/test_leaf_port.py
import pytest
from pydantic import ValidationError

from codegenie.fallback.leaf.port import LeafLlm, LeafResponse
from codegenie.fallback.plan_proposal import PlanProposalRefuse
from codegenie.types.identifiers import LeafResponseId, ModelId, TokenCount


def test_leaf_response_is_frozen_and_forbids_extra() -> None:
    plan = PlanProposalRefuse(reason="UNSAFE_BUMP", rationale="test")
    resp = LeafResponse(
        plan=plan,
        tokens_in=TokenCount(100),
        cache_read_tokens=TokenCount(0),
        cache_creation_tokens=TokenCount(50),
        tokens_out=TokenCount(200),
        model=ModelId("claude-sonnet-4-5-20250929"),
        stop_reason="end_turn",
        response_id=LeafResponseId("msg_01abc"),
    )
    with pytest.raises(ValidationError):
        resp.tokens_in = TokenCount(0)  # type: ignore[misc]  # frozen
    with pytest.raises(ValidationError):
        LeafResponse(plan=plan, extra="not-allowed")  # type: ignore[call-arg]


def test_leaf_llm_protocol_is_not_runtime_checkable() -> None:
    with pytest.raises(TypeError):
        isinstance(object(), LeafLlm)  # type: ignore[misc]


def test_leaf_response_negative_tokens_rejected() -> None:
    plan = PlanProposalRefuse(reason="UNSAFE_BUMP", rationale="test")
    with pytest.raises(ValidationError):
        LeafResponse(
            plan=plan,
            tokens_in=TokenCount(-1),
            # ... other fields valid
        )
```

### Green — make it pass

Author `port.py` minimally: `Protocol` class with the `invoke` method signature; `LeafResponse` model with the 8 fields and `frozen=True, extra="forbid"` config. No SDK imports; no logic — pure shape.

### Refactor — clean up

Sort `__all__`. Add docstrings naming ADR-0001 + ADR-0010 (the two ADRs the Protocol's signature directly encodes). Verify `mypy --strict` on the whole `src/codegenie/fallback/leaf/` subtree.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/leaf/__init__.py` | Package marker; re-export `LeafLlm` + `LeafResponse`. |
| `src/codegenie/fallback/leaf/port.py` | The Protocol + `LeafResponse` model (this story's deliverable). |
| `tests/unit/fallback/test_leaf_port.py` | Red test for frozen+extra-forbid; runtime-checkable rejection; negative-`TokenCount`. |
| `tests/unit/fallback/test_port_module_purity.py` | AST source-scan asserting `port.py` does not import any HTTP/SDK module. |
| `tests/unit/fallback/test_leaf_protocol_typecheck.py` | Subprocess-mypy meta-test for the 5 reject cases (AC-6). |

## Out of scope

- Any concrete adapter (S3-02 lands `AnthropicLeafAdapter`).
- `EgressGuard` (S3-03).
- Cassette discipline (S3-04..S3-06).
- The `LlmInvocationGuard` / `BudgetToken` issuer (S2-05).
- The `PlanProposal` union itself (S1-02).

## Notes for the implementer

- The Protocol must remain SDK-free; if you accidentally import `anthropic` here, the path-scoped fence amendment (ADR-0003 / S1-05) admits it only under `src/codegenie/fallback/leaf/anthropic_adapter.py`, so the fence test will fail loudly.
- `LeafResponse.stop_reason` uses a closed `Literal[...]` not a free `str` — the four values are exactly what Anthropic's SDK returns. Adding a fifth value is an ADR amendment.
- Do *not* expose `LeafResponse.raw_sdk_response: Any` or any escape hatch. The point of the Protocol is that the SDK is contained in the adapter.
- AC-6's subprocess-mypy meta-test is the load-bearing assurance that the `TypeError`-on-missing-token claim in ADR-0010 §Consequences is verified at CI, not just on hope.
- The Protocol's `schema: type[PlanProposal]` parameter is `type[T]` not `T` — callers pass the *class*, not an instance; the adapter passes `schema.model_json_schema()` to the SDK's `response_format`. Test this in S3-02, not here.
