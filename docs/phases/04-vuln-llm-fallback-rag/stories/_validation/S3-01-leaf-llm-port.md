# Validation report: S3-01 — `LeafLlm` Protocol + `LeafResponse` model

**Validated:** 2026-05-21
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S3-01 lands the SDK-free `LeafLlm` Protocol and the `LeafResponse` frozen-extra-forbid model — the single port between Phase 4 and any LLM provider. The goal is correct and traces cleanly to `phase-arch-design.md §Component 4`, ADR-0001, ADR-0010, and production ADR-0020: a typed seam so downstream code programs against a Protocol, not against `anthropic.AsyncAnthropic`. The functional shape (a pure Protocol + a pure data model, no logic) is right, and the story correctly forbids an `Any` SDK escape-hatch.

But the draft carried four substantive defects, all caused by drift against **hardened sibling stories** that were validated *after* S3-01 was first written:

1. **AC-2's `schema: type[PlanProposal]` is type-incoherent.** Hardened S1-02 (AC-2 / F13) establishes that `PlanProposal` is an `Annotated[… , Field(discriminator="kind")]` union *alias* — not a class. `type[PlanProposal]` resolves to a single variant class and has no `.model_json_schema()`/`.json_schema()` method, so the S3-02 adapter built against this Protocol could not produce the SDK `response_format`. The Pydantic-v2 carrier the codebase already uses for this exact union is `TypeAdapter(PlanProposal)` (S1-02 AC-6).
2. **AC-7's negative-`TokenCount` rejection rests on a false premise.** `TokenCount` is a `NewType`; Pydantic v2 resolves a `NewType` to its supertype and applies no validation. The S1-01 smart constructor `parse_token_count` is a separate function Pydantic never invokes. A bare `tokens_in: TokenCount` field silently accepts `-1`.
3. **AC-8 claims `LeafResponse` is hashable — it is not.** `plan` may be a `PlanProposalCallsiteRewrite`, whose `files: list[SandboxedRelativePath]` field (S1-02 AC-3) makes that variant unhashable, so `hash()` on a `LeafResponse` wrapping it raises `TypeError`.
4. **The TDD red tests were not runnable.** Fixtures used `PlanProposalRefuse(reason="UNSAFE_BUMP", …)` — `"UNSAFE_BUMP"` is not a valid `reason` literal (hardened S1-02 AC-3 closes it to `{out_of_scope, insufficient_context, policy_block}`); the negative-tokens test had a `# ... other fields valid` placeholder instead of real code; and the extra-forbid assertion could not isolate `extra="forbid"` from missing-required-field errors.

Plus a stale module path (`codegenie.fallback.prompt` → `codegenie.fallback.fence.prompt_builder`, per hardened S2-04 AC-2) and a brittle exact-frozenset import assertion. All fixable in place — the goal never changes — so the verdict is **HARDENED**.

## Context brief

### Story snapshot
- **Goal:** Land the SDK-free `LeafLlm` Protocol + the `LeafResponse` frozen-extra-forbid Pydantic model so every downstream Phase-4 consumer programs against a typed seam.
- **Non-goals:** concrete adapter (S3-02), `EgressGuard` (S3-03), cassettes (S3-04..06), `BudgetToken` issuer (S2-05), `PlanProposal` union (S1-02).

### Phase / arch constraints
- `phase-arch-design.md §Component 4` — the `LeafLlm` Protocol public-interface block; `LeafResponse` field list. Note: arch line 525 still writes `schema: type[PlanProposal]` — predates S1-02's hardening; stale (see Conflict resolutions).
- ADR-0001 — `PlanProposal` is the closed sum type; §Consequences reserves a per-plugin schema seam (justifies keeping the `schema` parameter).
- ADR-0010 — `BudgetToken` is a required keyword-only arg; calling without one is a `TypeError`.
- ADR-0003 — `port.py` must be SDK-free; `anthropic` is admitted only under `src/codegenie/fallback/leaf/anthropic_adapter.py`.
- production ADR-0020 — deferred multi-vendor seam; the Protocol earns its keep here.

### Existing-code reality (verified 2026-05-21)
- `src/codegenie/fallback/` is not implemented yet — all Phase-4 stories are docs-only. Phase-4 newtypes (`ModelId`/`TokenCount`/`LeafResponseId`) are not yet in `identifiers.py` (S1-01 unexecuted). This is normal for a design-phase story; the dependencies are correctly declared in the header.
- **Sibling module paths (from hardened story ACs):** `PlanProposal` → `src/codegenie/fallback/plan_proposal.py` (S1-02 AC-1); `TrustedPrompt`/`FencedPromptBody` → `src/codegenie/fallback/fence/prompt_builder.py` (S2-04 AC-2); `BudgetToken` → `src/codegenie/fallback/budget.py` (S2-05 AC-1).
- `PlanProposalRefuse.reason` is `Literal["out_of_scope", "insufficient_context", "policy_block"]` (S1-02 AC-3); `PlanProposalCallsiteRewrite.files` is `list[SandboxedRelativePath]` with `Field(min_length=1)`.

### Sibling lineage
S3-01 is the first Step-3 story. Its dependencies (S1-01, S1-02, S2-04, S2-05) are all HARDENED. The recurring Phase-4 hardening theme — drift against newer sibling decisions — recurs here: S3-01 was drafted before S1-02 hardened away `PlanProposal.model_json_schema()` and before S2-04 pinned the prompt-builder module path.

### Open ambiguities
None requiring user input. The one design call (`type[PlanProposal]` vs `TypeAdapter[PlanProposal]`) was resolved against hardened S1-02 — see Conflict resolutions.

## Findings by critic

### Consistency critic

- **C1 (block)** — AC-2's `schema: type[PlanProposal]` and Notes for the implementer ("the adapter passes `schema.model_json_schema()`") contradict hardened S1-02 AC-2/AC-6 (F13): `PlanProposal` is an `Annotated` union alias, not a class, with no `.model_json_schema()`/`.json_schema()` method. Fixed: signature → `schema: TypeAdapter[PlanProposal]`; AC-2 prose, Notes, Implementation outline, Green section all reconciled. The `schema` seam itself is kept — ADR-0001 §Consequences reserves it for a Phase-7 plugin with its own variants.
- **C2 (block)** — AC-4's import set named `codegenie.fallback.prompt`; the real module per hardened S2-04 AC-2 is `codegenie.fallback.fence.prompt_builder`. Fixed.
- **C3 (harden)** — the stale `schema.model_json_schema()` claim removed from Notes for the implementer; a cross-story note added flagging that sibling S3-02 still carries the same stale assumption (S3-02 is not yet validated — it must be reconciled when its turn comes).

### Coverage critic

- **Cov1 (block)** — AC-7 promised negative-`TokenCount` rejection "by the smart constructor S1-01 ships", but a `NewType` field carries no Pydantic validation and `parse_token_count` is never invoked by model construction. The AC was unsatisfiable. Fixed: AC-3's four token fields are now `Annotated[TokenCount, Field(ge=0)]`; AC-7 rewritten to verify the real `Field(ge=0)` mechanism, parametrized over all four fields.
- **Cov2 (block)** — AC-8 claimed `LeafResponse` is hashable. False: a `PlanProposalCallsiteRewrite` `plan` carries a `list` field, so `hash()` raises `TypeError`. Fixed: AC-8 reframed around structural `==` + immutability (which frozen Pydantic models support regardless of field hashability — and which is what the S6-07 determinism test actually needs).
- **Cov3 (harden)** — AC-6's subprocess-mypy meta-test was negative-only. A `Protocol` mangled into an un-satisfiable shape would still make all five reject cases "pass" with a non-zero exit. Added AC-6a — a conforming-stub positive control that must type-check clean.

### Test-Quality critic

- **TQ1 (block)** — the red test `test_leaf_response_negative_tokens_rejected` had a `# ... other fields valid` placeholder instead of code (not runnable) and rested on Cov1's false premise. Rewritten: parametrized over all four token fields, mutating one key off a fully-valid baseline.
- **TQ2 (harden)** — `test_leaf_response_is_frozen_and_forbids_extra` called `LeafResponse(plan=plan, extra="not-allowed")`, which raises for the seven *missing required fields* as much as for the extra key — it could not isolate `extra="forbid"`. Split into `test_leaf_response_is_frozen` and `test_leaf_response_forbids_extra`; the latter mutates one key off a valid baseline and `match=`es the extra-inputs message.
- **TQ3 (block)** — red-test fixtures used `PlanProposalRefuse(reason="UNSAFE_BUMP", …)`; `"UNSAFE_BUMP"` is not in S1-02's closed `reason` literal set, so the fixture would itself raise `ValidationError` — every negative test would pass for the wrong reason. Fixed to `reason="out_of_scope"` via a shared `_valid_kwargs()` helper, with a `test_leaf_response_baseline_is_valid` positive control guarding the baseline.
- **TQ4 (harden)** — AC-6 said only "a substring match in stderr/stdout" without naming the substring. Hardened to require one of `incompatible type` / `argument` / `missing` / `positional` in lowercased stdout (mirrors S1-01 `test_phase4_identifiers_mypy_negative.py` and hardened S1-02 AC-7) plus a `pytest.importorskip("mypy")`.

### Design-Patterns critic

- **DP1 (note — STRONG aspect)** — the LLM trust boundary modelled as a Protocol port with the SDK contained in the adapter is the correct hexagonal/adapter application (arch §Design-patterns row 878). `LeafResponse` is a pure frozen data model with no behavior and no `Any` escape-hatch — no premature abstraction, Rule 2 respected. Left unchanged.
- **DP2 (harden — folds into C1)** — `TypeAdapter[PlanProposal]` is the type-correct, codebase-consistent carrier for the discriminated union (Rule 11 — S1-02 AC-6 set the precedent). Applied as part of the C1 fix.
- **DP3 (harden)** — AC-4's exact-frozenset import assertion is brittle: it breaks whenever a sibling Step-1/Step-2 module is relocated, and the story already had to hedge "names subject to … final locations" — a hedge a hardcoded `assert ==` cannot honor. Reframed to a robust forbidden-set (named HTTP/SDK packages) + a `pydantic`-only-third-party-namespace rule. This directly encodes the SDK-free intent and never needs editing when siblings move — easier to maintain, the explicit ask of this validation pass.

## Research briefs

None. Every finding was resolved from in-repo docs and hardened sibling stories (S1-01, S1-02, S2-04, S2-05) plus their validation reports. No finding was tagged `NEEDS RESEARCH`; Stage 3 skipped.

## Conflict resolutions

- **Arch line 525 (`schema: type[PlanProposal]`) vs hardened S1-02.** The arch one-liner predates S1-02's hardening, which established (F13) that `PlanProposal` is an `Annotated` alias with no `.model_json_schema()`. The validator's priority chain puts Consistency first, but here the "source of truth" is itself split: a stale arch line vs a *hardened, validated* sibling story. Resolved in favour of the hardened sibling — identical to S2-05's resolution of "arch §Testing-strategy line 963 is stale; the ADR + component spec win." The Protocol contract must be implementable by S3-02; `type[PlanProposal]` is not. `TypeAdapter[PlanProposal]` chosen.
- **Keep vs drop the `schema` parameter.** Coverage might argue the adapter could hardcode `PlanProposal` and drop the parameter entirely (simpler — Rule 2). Consistency wins: ADR-0001 §Consequences explicitly reserves a per-plugin schema seam ("Phase 7's distroless plugin … with its own `PlanProposal` schema variants"). The seam is kept and typed correctly, not removed.

## Edits applied

1. Header `Status: Ready → HARDENED`; `Validation notes` block inserted under the header.
2. **AC-2** — signature `schema: type[PlanProposal]` → `schema: TypeAdapter[PlanProposal]`; prose explains why `type[PlanProposal]` is incoherent and why `TypeAdapter` is the codebase-consistent carrier (C1).
3. **AC-3** — the four token-count fields → `Annotated[TokenCount, Field(ge=0)]`; prose explains a `NewType` carries no Pydantic validation (Cov1).
4. **AC-4** — reframed from an exact frozenset (with the wrong `codegenie.fallback.prompt` path) to a named-forbidden-set + `pydantic`-only-namespace rule; correct sibling paths listed for reference (C2/DP3).
5. **AC-6** — meta-test cases now bind a correctly-typed `sch: TypeAdapter[PlanProposal]`; named diagnostic substrings required; `pytest.importorskip("mypy")` (TQ4).
6. **AC-6a** — added: conforming-stub positive control (Cov3).
7. **AC-7** — rewritten to verify the `Field(ge=0)` mechanism, parametrized over all four token fields; false "smart constructor" premise removed (Cov1/TQ1).
8. **AC-8** — hash claim replaced with structural `==` + immutability; explains why `LeafResponse` is not hashable and forbids the silent-edit "fix" (Cov2).
9. **AC-10** — reframed: no longer points at a not-yet-existent S3-02 test; restated as subsumed by AC-4 (nit).
10. **Implementation outline** — steps 2–5 updated for `TypeAdapter`, `Field(ge=0)`, and the AC-6a positive control.
11. **TDD plan — Red** — the three test functions rewritten: shared `_valid_kwargs()` helper with a valid `reason`, a `test_leaf_response_baseline_is_valid` positive control, frozen/extra-forbid split into isolating tests, negative-tokens parametrized over all four fields.
12. **TDD plan — Green** — notes `schema: TypeAdapter[PlanProposal]` and the `Annotated[TokenCount, Field(ge=0)]` fields.
13. **Notes for the implementer** — stale `schema.model_json_schema()` bullet replaced; cross-story note about S3-02; two new bullets on `NewType` non-validation and `LeafResponse` non-hashability.
14. **Files to touch** — `test_leaf_protocol_typecheck.py` row updated to mention AC-6a.

## Verdict rationale

HARDENED. The story's goal — an SDK-free `LeafLlm` Protocol plus a frozen `LeafResponse` model — is correct, traces cleanly to arch Component 4 and ADR-0001/0010/0020, and is untouched by this pass. Six findings were `block`-severity, but every one is an AC- or test-mechanism defect with a clear in-place fix; none required rewriting the goal or scope (the RESCUE trigger). The blockers were all drift against sibling stories that hardened *after* S3-01 was drafted — `PlanProposal` becoming an `Annotated` alias, the prompt-builder module path, the `reason` literal set — plus two type-system misconceptions (`NewType` validates; a frozen model is always hashable). After the edits, AC-2's signature is implementable by S3-02, AC-7 verifies a real constraint, AC-8 asserts a property `LeafResponse` actually has, the TDD red tests are runnable and each isolates one rule, and the meta-test has a positive control. Ready for `phase-story-executor`.

## Recommended next step

`phase-story-executor` to implement S3-01. Sequence: (1) `port.py` — `Protocol` + `LeafResponse` with `Annotated[TokenCount, Field(ge=0)]` fields; (2) the red tests (`_valid_kwargs` baseline first); (3) `test_port_module_purity.py`; (4) `test_leaf_protocol_typecheck.py` — AC-6 negatives + AC-6a positive control last, as the proof the Protocol is both un-bypassable and implementable.

**Cross-story flag for the validator queue:** `S3-02-anthropic-leaf-adapter.md` still references `PlanProposal.model_json_schema()` (ACs + `Depends on` line). When S3-02 is validated, reconcile it to `TypeAdapter(PlanProposal).json_schema()` and to the `schema: TypeAdapter[PlanProposal]` parameter type S3-01 now pins.
