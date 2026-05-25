# Story S3-01 — `LeafLlm` Protocol + `LeafResponse` model

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** Done — GREEN 2026-05-24 (phase-story-executor; see [`_attempts/S3-01.md`](_attempts/S3-01.md) for the per-AC evidence table + gate log — SDK-free `LeafLlm` Protocol + `LeafResponse` frozen-extra-forbid Pydantic model land at `src/codegenie/fallback/leaf/port.py` (~120 lines, zero runtime logic) with `__init__.py` re-exporting the two public names. 19 story-scoped tests pass: 11 in `tests/unit/fallback/test_leaf_port.py` (AC-1/3/5/7/8), 2 in `test_port_module_purity.py` (AC-4 named-forbidden set + namespace rule), 6 in `test_leaf_protocol_typecheck.py` (AC-6 five mypy negatives + AC-6a conforming-stub positive control). Cross-story reconciliation per Rule 7: (a) added `codegenie.fallback.leaf` to the ADR-0010 BudgetToken-scope contract `source_modules` (shape test required it); (b) added `codegenie.fallback.leaf.port -> codegenie.fallback.budget_token` to `ignore_imports` (the Protocol's `token: BudgetToken` is the load-bearing seam); (c) reconciled S2-05's stale `codegenie.fallback.leaf.protocol` import path in `tests/fence/test_budget_token_typecheck.py` + `tests/fixtures/typecheck/budget_token_missing.py` to the S3-01-canonical `port.py` name, **and removed a `# type: ignore[call-arg]` on the very call site whose missing-arg diagnostic the gate asserts on** — without that fix the S2-05 AC-15 gate would have silently green-passed on S3-01 landing (lesson L-7). Gates green: 6565 unit+integration, 433 fence (the previously-skipped `test_budget_token_typecheck.py` AC-15 gate now runs live), `mypy --strict src/` (221 files), `ruff check` + `ruff format --check`, `lint-imports` (11 contracts kept / 0 broken). Two pre-existing local-env failures (`tsconfig_pathological` timing flake; `lint_imports_canary` PATH issue) deselected per the L-2 / L-4 convention — recurring from S2-01/02/03/04/05; CI Linux runners are clean.)
**Effort:** S
**Depends on:** S2-04 (`PromptBuilder` mints `TrustedPrompt` + `FencedPromptBody`), S2-05 (`BudgetToken`), S1-02 (`PlanProposal`), S1-01 (`ModelId`, `TokenCount`, `LeafResponseId`)
**ADRs honored:** ADR-0001 (Phase 4 — `PlanProposal` closed sum type — adapter validates via SDK `response_format`), ADR-0010 (Phase 4 — `BudgetToken` required arg), ADR-0020 (production — multi-vendor seam preserved by the Protocol)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 12 — 6 blocks, 5 hardens, 1 nit

Changes applied:
- **C1 (block)** — AC-2 signature: `schema: type[PlanProposal]` → `schema: TypeAdapter[PlanProposal]`. `PlanProposal` is an `Annotated` discriminated-union *alias* (hardened S1-02 AC-2), not a class — `type[PlanProposal]` resolves to a single variant class and has no `.model_json_schema()`. `TypeAdapter` is the Pydantic-v2 carrier S1-02 AC-6 already uses. Notes for the implementer corrected; cross-story note added that sibling S3-02 carries the same stale `model_json_schema()` assumption.
- **C2 (block)** — AC-4 import set named `codegenie.fallback.prompt`; the real module (hardened S2-04 AC-2) is `codegenie.fallback.fence.prompt_builder`.
- **Cov1 (block)** — AC-7 negative-`TokenCount` rejection rested on a false premise — a `NewType` performs no Pydantic validation. AC-3's four token fields are now `Annotated[TokenCount, Field(ge=0)]`; AC-7 rewritten to verify the real mechanism.
- **Cov2 (block)** — AC-8 claimed `LeafResponse` is hashable; it is not — `plan` may be a `PlanProposalCallsiteRewrite` whose `files: list[...]` field makes `hash()` raise. AC-8 reframed around structural `==` + immutability.
- **TQ1 (block)** — red test `test_leaf_response_negative_tokens_rejected` was malformed (`# ... other fields valid` placeholder) and rested on Cov1's false premise. Rewritten parametrized over all four token fields off a valid baseline.
- **TQ3 (block)** — red test fixtures used `PlanProposalRefuse(reason="UNSAFE_BUMP", ...)`; `"UNSAFE_BUMP"` is not a valid `reason` literal (hardened S1-02 AC-3). Fixed to `"out_of_scope"`.
- **Cov3 (harden)** — AC-6a added: a positive control proving the Protocol is actually implementable (a negative-only meta-test is not mutation-resistant).
- **TQ2 (harden)** — `test_leaf_response_is_frozen_and_forbids_extra` split; the extra-forbid test now mutates one key off a fully-valid baseline so the `ValidationError` isolates `extra="forbid"`.
- **TQ4 (harden)** — AC-6 now names the expected mypy diagnostic substrings (mirrors S1-01 / hardened S1-02 AC-7) instead of "a substring match".
- **DP3 (harden)** — AC-4 reframed from a brittle exact-frozenset to a robust forbidden-set + `pydantic`-only-namespace rule.
- **C3 (harden)** — stale `schema.model_json_schema()` claim removed from Notes for the implementer.
- **AC-10 (nit)** — reframed: it pointed at a not-yet-existent S3-02 test; restated as subsumed by AC-4.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S3-01-leaf-llm-port.md

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

- [x] AC-1 — `src/codegenie/fallback/leaf/__init__.py` and `src/codegenie/fallback/leaf/port.py` exist; `port.py` exports `LeafLlm` (`typing.Protocol`) and `LeafResponse` (Pydantic frozen-extra-forbid `BaseModel`) and nothing else; module-level `__all__ = ("LeafLlm", "LeafResponse")` is exact.
- [x] AC-2 — `LeafLlm.invoke` signature is exactly:
  ```python
  async def invoke(
      self,
      system_prompt: TrustedPrompt,
      user_message: FencedPromptBody,
      *,
      schema: TypeAdapter[PlanProposal],
      token: BudgetToken,
  ) -> LeafResponse: ...
  ```
  The `*` keyword-only separator is mandatory; `schema` and `token` are keyword-only; both are required (no defaults). `schema` is a `pydantic.TypeAdapter[PlanProposal]`, **not** `type[PlanProposal]` (validator: corrected — C1). `PlanProposal` is `Annotated[PlanProposalDepBump | … | PlanProposalRefuse, Field(discriminator="kind")]` (hardened S1-02 AC-2) — an annotated union *alias*, not a class: `type[PlanProposal]` resolves to `type[A] | type[B] | …` (one variant class, not the union) and exposes no `.model_json_schema()` / `.json_schema()` method. `TypeAdapter(PlanProposal)` is the Pydantic-v2 carrier the codebase already uses for this exact union (S1-02 AC-6: `TypeAdapter(PlanProposal).json_schema()`); the caller (`FallbackTier`) constructs one `TypeAdapter(PlanProposal)` and passes it, and the S3-02 adapter calls `schema.json_schema()` for the SDK `response_format` and `schema.validate_json(...)` at the boundary. The seam is kept (rather than hardcoding the union in the adapter) because ADR-0001 §Consequences reserves it for a Phase-7 plugin shipping its own `PlanProposal` variants.
- [x] AC-3 — `LeafResponse` fields, in exact order, with these types: `plan: PlanProposal`, `tokens_in: Annotated[TokenCount, Field(ge=0)]`, `cache_read_tokens: Annotated[TokenCount, Field(ge=0)]`, `cache_creation_tokens: Annotated[TokenCount, Field(ge=0)]`, `tokens_out: Annotated[TokenCount, Field(ge=0)]`, `model: ModelId`, `stop_reason: Literal["end_turn", "max_tokens", "stop_sequence", "tool_use"]`, `response_id: LeafResponseId`. `model_config = ConfigDict(frozen=True, extra="forbid")`. The four token-count fields are `Annotated[TokenCount, Field(ge=0)]` — **not bare `TokenCount`** (validator: corrected — Cov1). `TokenCount` is `NewType("TokenCount", int)` (S1-01 AC-2); Pydantic v2 resolves a `NewType` to its supertype `int` and applies **no** validation, so a bare `tokens_in: TokenCount` silently accepts `-1`. The `Field(ge=0)` constraint is what makes AC-7's negative-rejection real. To `mypy --strict` the field type is still `TokenCount` (`Annotated[X, …]` is transparent to the type checker), so the typed-seam guarantee holds.
- [x] AC-4 — `port.py` is SDK-free. The AST source-scan test (`tests/unit/fallback/test_port_module_purity.py`) asserts **both**: (a) `port.py` imports **none** of `anthropic`, `httpx`, `requests`, `urllib3`, `aiohttp`, `socket`, `ssl` (named-forbidden set — yields a precise diagnostic); (b) every `import` / `from … import` statement in `port.py` resolves to either the stdlib, `pydantic`, or a `codegenie.*` module — i.e. **no third-party package other than `pydantic`**. Framing (b) as a namespace rule rather than an exact frozenset keeps the test robust when sibling Step-1/Step-2 modules are relocated (validator: reframed — DP3/C2). For reference, the expected `codegenie.*` imports as of validation are: `codegenie.types.identifiers` (`ModelId`, `TokenCount`, `LeafResponseId`), `codegenie.fallback.plan_proposal` (`PlanProposal` — S1-02 AC-1), `codegenie.fallback.fence.prompt_builder` (`TrustedPrompt`, `FencedPromptBody` — S2-04 AC-2; **not** `codegenie.fallback.prompt`, which does not exist — validator: corrected stale path), and `codegenie.fallback.budget` (`BudgetToken` — S2-05 AC-1). The test must import these names from their **actual** shipped modules; confirm each path before pinning.
- [x] AC-5 — `LeafLlm` is `runtime_checkable=False` (default for `Protocol`). A negative test asserts that calling `isinstance(obj, LeafLlm)` raises `TypeError` (matches the existing newtype-isinstance pin convention from Phase-2 S1-05).
- [x] AC-6 — `mypy --strict` rejects every one of these call shapes (subprocess-mypy meta-test, `tests/unit/fallback/test_leaf_protocol_typecheck.py`). Each temp file binds a correctly-typed `sch: TypeAdapter[PlanProposal] = TypeAdapter(PlanProposal)` and a `tok: BudgetToken` so that every negative case isolates **exactly one** violation (validator: hardened — passing the bare `PlanProposal` alias as `schema` would itself be a type error and would muddy the "missing token" / keyword-only cases — TQ4):
  - `leaf.invoke(sp, body, schema=sch)` — missing required `token`.
  - `leaf.invoke(sp, body, token=tok)` — missing required `schema`.
  - `leaf.invoke(sp, body, sch, tok)` — positional `schema`/`token` (keyword-only violation).
  - `leaf.invoke("raw str", body, schema=sch, token=tok)` — raw `str` instead of `TrustedPrompt`.
  - `leaf.invoke(sp, "raw str", schema=sch, token=tok)` — raw `str` instead of `FencedPromptBody`.
  Test parametrizes over the 5 cases; each case must produce a **non-zero exit** AND a diagnostic substring match — at minimum one of `"incompatible type"`, `"argument"`, `"missing"`, `"positional"` in lowercased stdout (mirrors S1-01 `test_phase4_identifiers_mypy_negative.py` and hardened S1-02 AC-7 — asserting only `returncode != 0` green-washes a file that fails mypy for an unrelated reason such as an import-resolution error). The test `pytest.importorskip("mypy")` so a missing mypy install surfaces as a skip, not a confusing pass/fail.
- [x] AC-6a — **Positive control** (same meta-test file): a temp file defining a minimal class whose `invoke` matches the AC-2 signature exactly, assigned to a `LeafLlm`-typed variable (`_l: LeafLlm = _ConformingStub()`), type-checks **clean** — `mypy --strict` exits 0 with no error on stdout. (validator: added — Cov3; a negative-only meta-test is not mutation-resistant — a `Protocol` mangled into an un-satisfiable shape would still make all five AC-6 cases "pass" with a non-zero exit. The positive control proves the Protocol is actually implementable, which is the story's whole point.)
- [x] AC-7 — A `LeafResponse` constructed with **all eight fields otherwise valid** but any one of the four token-count fields set to a negative value (`tokens_in=TokenCount(-1)`, then independently `cache_read_tokens`, `cache_creation_tokens`, `tokens_out`) raises `pydantic.ValidationError`. The rejection comes from the `Field(ge=0)` constraint in AC-3 — **not** from `TokenCount` itself (a `NewType` carries no runtime validation; `parse_token_count`, the S1-01 smart constructor, is a separate function Pydantic never invokes). The test parametrizes over all four token fields so a `Field(ge=0)` missing from any single field is caught. (validator: corrected — Cov1/TQ1; the original AC's "rejected by the smart constructor S1-01 ships" premise was false.)
- [x] AC-8 — `LeafResponse` is immutable and supports structural equality. Two `LeafResponse` instances built from byte-identical field values compare `==`; two that differ in any single field compare `!=`; assigning to any field raises `pydantic.ValidationError` (`frozen=True`). The determinism property test in S6-07 consumes this **equality** invariant. (validator: corrected — Cov2; the original AC claimed `LeafResponse` is *hashable*, which is false — `plan` may be a `PlanProposalCallsiteRewrite`, whose `files: list[SandboxedRelativePath]` field (S1-02 AC-3) makes that variant unhashable, so `hash(LeafResponse(plan=<callsite_rewrite>, …))` raises `TypeError`. Frozen Pydantic models support `==` regardless of field hashability, and `==` is what a determinism test needs. Do **not** add `unsafe_hash` or coerce `files` to a `tuple` — that would silently edit S1-02's hardened contract.)
- [x] AC-9 — `mypy --strict src/codegenie/fallback/leaf/port.py` clean. `ruff check`, `ruff format --check` clean on touched files.
- [x] AC-10 — `port.py` contains zero `import anthropic` statements (subsumed by AC-4's named-forbidden set; restated here because it is the precondition that makes the S3-02 fence test `tests/fence/test_only_leaf_imports_anthropic.py` pass once that test lands). No new test is written for AC-10 in this story — AC-4's purity test is the verifying check. (validator: reframed — the original AC pointed at a test that does not exist until S3-02, so it was not independently verifiable within S3-01's scope.)
- [x] AC-11 — The TDD red test exists, is committed, was demonstrably failing before implementation, and is now green.

## Implementation outline

1. Create `src/codegenie/fallback/leaf/__init__.py` (empty re-export from `port`).
2. Create `src/codegenie/fallback/leaf/port.py` with the `Protocol` class (`invoke` typed per AC-2 — `schema: TypeAdapter[PlanProposal]`) and the `LeafResponse` model.
3. Wire `LeafResponse` to the Phase-4 newtypes (`ModelId`, `LeafResponseId`) and to `PlanProposal` (Step 1); the four token-count fields are `Annotated[TokenCount, Field(ge=0)]` (AC-3). `TypeAdapter` and `Field` come from `pydantic`.
4. Add the AST source-scan purity test under `tests/unit/fallback/test_port_module_purity.py` (AC-4 — named-forbidden set + `pydantic`-only-namespace rule).
5. Add the subprocess-mypy meta-test under `tests/unit/fallback/test_leaf_protocol_typecheck.py` — the 5 reject cases (AC-6) plus the conforming-stub positive control (AC-6a).

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/fallback/test_leaf_port.py
import pytest
from pydantic import ValidationError

from codegenie.fallback.leaf.port import LeafLlm, LeafResponse
from codegenie.fallback.plan_proposal import PlanProposalRefuse
from codegenie.types.identifiers import LeafResponseId, ModelId, TokenCount


def _valid_kwargs() -> dict[str, object]:
    """A fully-populated, valid LeafResponse kwargs dict. Every negative test
    mutates exactly one key off this baseline so each assertion isolates one
    rule (and `test_leaf_response_baseline_is_valid` guards the baseline)."""
    return {
        # reason MUST be one of S1-02 AC-3's literals:
        # {out_of_scope, insufficient_context, policy_block}. "UNSAFE_BUMP"
        # (the original draft's value) is not valid and would raise for the
        # WRONG reason.
        "plan": PlanProposalRefuse(reason="out_of_scope", rationale="test"),
        "tokens_in": TokenCount(100),
        "cache_read_tokens": TokenCount(0),
        "cache_creation_tokens": TokenCount(50),
        "tokens_out": TokenCount(200),
        "model": ModelId("claude-sonnet-4-5-20250929"),
        "stop_reason": "end_turn",
        "response_id": LeafResponseId("msg_01abc"),
    }


def test_leaf_response_baseline_is_valid() -> None:
    # Positive control: if the baseline itself were invalid, every negative
    # test below would pass for the wrong reason.
    resp = LeafResponse(**_valid_kwargs())
    assert resp.tokens_in == 100


def test_leaf_response_is_frozen() -> None:
    resp = LeafResponse(**_valid_kwargs())
    with pytest.raises(ValidationError):
        resp.tokens_in = TokenCount(0)  # type: ignore[misc]  # frozen


def test_leaf_response_forbids_extra() -> None:
    # Baseline is fully valid → the ONLY violation is the extra key, so the
    # ValidationError can ONLY be the extra="forbid" rule (the original test
    # called LeafResponse(plan=plan, extra=...) which also failed on the
    # seven missing required fields — it could not isolate extra-forbid).
    with pytest.raises(ValidationError, match="[Ee]xtra"):
        LeafResponse(**_valid_kwargs(), surprise="not-allowed")  # type: ignore[call-arg]


def test_leaf_llm_protocol_is_not_runtime_checkable() -> None:
    with pytest.raises(TypeError):
        isinstance(object(), LeafLlm)  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    ["tokens_in", "cache_read_tokens", "cache_creation_tokens", "tokens_out"],
)
def test_leaf_response_negative_tokens_rejected(field: str) -> None:
    # Field(ge=0) on each token field — NOT the TokenCount NewType — is what
    # rejects a negative count. Parametrized so a ge=0 missing from any one
    # field is caught.
    kwargs = _valid_kwargs()
    kwargs[field] = TokenCount(-1)
    with pytest.raises(ValidationError):
        LeafResponse(**kwargs)
```

### Green — make it pass

Author `port.py` minimally: `Protocol` class with the `invoke` method signature (`schema: TypeAdapter[PlanProposal]`); `LeafResponse` model with the 8 fields — the four token-count fields `Annotated[TokenCount, Field(ge=0)]` — and `frozen=True, extra="forbid"` config. No SDK imports; no logic — pure shape.

### Refactor — clean up

Sort `__all__`. Add docstrings naming ADR-0001 + ADR-0010 (the two ADRs the Protocol's signature directly encodes). Verify `mypy --strict` on the whole `src/codegenie/fallback/leaf/` subtree.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/leaf/__init__.py` | Package marker; re-export `LeafLlm` + `LeafResponse`. |
| `src/codegenie/fallback/leaf/port.py` | The Protocol + `LeafResponse` model (this story's deliverable). |
| `tests/unit/fallback/test_leaf_port.py` | Red test for frozen+extra-forbid; runtime-checkable rejection; negative-`TokenCount`. |
| `tests/unit/fallback/test_port_module_purity.py` | AST source-scan asserting `port.py` does not import any HTTP/SDK module. |
| `tests/unit/fallback/test_leaf_protocol_typecheck.py` | Subprocess-mypy meta-test: the 5 reject cases (AC-6) + the conforming-stub positive control (AC-6a). |

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
- The Protocol's `schema` parameter is a `pydantic.TypeAdapter[PlanProposal]`, **not** `type[PlanProposal]`. `PlanProposal` is an `Annotated` discriminated-union alias (hardened S1-02 AC-2), not a class — it exposes no `.model_json_schema()` / `.json_schema()` method, and `type[PlanProposal]` resolves to a single variant class, not the union. The S3-02 adapter calls `schema.json_schema()` (for the SDK `response_format`) and `schema.validate_json(...)` (boundary validation). Test the schema *usage* in S3-02, not here; S3-01 only pins the Protocol's parameter type.
- **Cross-story note (not S3-01's to fix):** sibling story `S3-02-anthropic-leaf-adapter.md` still references `PlanProposal.model_json_schema()` in its ACs and `Depends on` line — the same stale assumption hardened S1-02 (F13) removed. When S3-02 is validated it must be reconciled to `TypeAdapter(PlanProposal).json_schema()`.
- `TokenCount` is a `NewType` — it performs **no** runtime validation. A Pydantic field typed bare `TokenCount` accepts negative ints silently. The `Annotated[TokenCount, Field(ge=0)]` in AC-3 is load-bearing for AC-7; do not drop the `Field(ge=0)`.
- `LeafResponse` is **not hashable** — `plan` may be a `PlanProposalCallsiteRewrite` carrying a `list` field (S1-02 AC-3). Rely on structural `==` (which frozen Pydantic models always support), never `hash()`. Do not "fix" this by coercing `files` to a tuple — that is S1-02's contract, out of scope here.
