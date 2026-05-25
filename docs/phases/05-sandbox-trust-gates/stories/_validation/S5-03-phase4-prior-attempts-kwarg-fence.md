# Validation report: S5-03 — Cross-phase `prior_attempts` contract conformance (ADR-0002)

**Validated:** 2026-05-25
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S5-03 is the Phase-5-side story for ADR-0002 — the **additive `prior_attempts`
kwarg cross-phase contract** that lets the three-retry loop feed Phase 4's
recipe→RAG→LLM ladder with structured `AttemptSummary` instances instead of
raw sandbox stderr. The story's *goal* (own the Phase-5-side of that ADR) is
intact; ADR-0002 has not been amended and continues to be the authoritative
decision record.

The draft was written **before** every upstream surface this ADR amendment
touches reached HARDENED / GREEN. As a consequence, the draft asserts
implementation work that has already been absorbed by upstream stories,
prescribes a parallel `FenceWrapper.compose_prior_attempts` helper whose
delimiter format and canary scheme directly contradict the shipped Phase-4
fence kernel, names module paths that do not exist in the codebase, and uses
the wrong `AttemptSummary` shape. Every block-tier finding traces to this
"draft predates the dependencies" gap.

| Draft assumption | Reality on `master` (or HARDENED upstream story) |
|---|---|
| `ApplyContext` must *gain* a `prior_attempts: list[AttemptSummary] = []` field (story AC-2) | Phase 3 S1-04 **already shipped** `ApplyContext.prior_attempts: tuple[AttemptSummary, ...] = ()` at [`src/codegenie/transforms/apply_context.py:140`](../../../../src/codegenie/transforms/apply_context.py). The field is `tuple`-typed (not `list`) for true immutability — Pydantic v2 `frozen=True` freezes attribute reassignment, not in-place container mutation. Mutable-default `[]` is the V-D-F2 footgun [`apply_context.py:11-15`](../../../../src/codegenie/transforms/apply_context.py) explicitly closes. AC-2 is **already-satisfied upstream** — Phase 5 owns *no* edit to `ApplyContext`. |
| `FallbackTier.run` lives at `src/codegenie/plan/fallback.py` and the kwarg shape is `prior_attempts: list[AttemptSummary] = []` | (a) Phase 4's `FallbackTier` ships at `src/codegenie/fallback/tier.py` (Phase 4 S6-01 HARDENED — class not yet GREEN). The path `src/codegenie/plan/` **does not exist**. (b) Phase 4 S6-01 HARDENED [`stories/S6-01-fallback-tier-pipeline.md:51`](../../../04-vuln-llm-fallback-rag/stories/S6-01-fallback-tier-pipeline.md) **already locks** the signature to `async def run(advisory, repo_ctx, recipe_selection, *, prior_attempts: Sequence[AttemptSummary] = ()) -> RecipeApplication` — keyword-only, `Sequence` (read-covariant), immutable empty tuple default. AC-1 prescribes a mutable `list`-default footgun and a sync method. |
| `AttemptSummary` is imported from `codegenie.gates.contract` and carries `attempt_id`, `sandbox_run_id`, `failing_signals: list[str]`, `prior_failure_summary`, `evidence_paths: dict` | `AttemptSummary` is shipped at [`codegenie.transforms.apply_context.AttemptSummary`](../../../../src/codegenie/transforms/apply_context.py). Its fields are `attempt: AttemptNumber`, `failing_signals: tuple[SignalKind, ...]`, `prior_failure_summary: str`, `evidence_paths: tuple[SandboxedPath, ...]`, `transform_id: TransformId \| None`. There is **no `attempt_id`** (it's `attempt`); **no `sandbox_run_id`** on the model (`SandboxedPath` carries evidence locality); `failing_signals` is `tuple[SignalKind, ...]` not `list[str]` (newtype consumption per S1-05); `evidence_paths` is a tuple of `SandboxedPath`, not a `dict`. |
| Build a new `FenceWrapper.compose_prior_attempts(attempts) -> str` static helper that emits `<BEGIN_PRIOR_ATTEMPT_{canary}>...<END_PRIOR_ATTEMPT_{canary}>` blocks, with `canary = secrets.token_hex(8).upper()` (16 hex chars uppercase) per attempt | Direct conflict with the shipped Phase-4 fence kernel at [`src/codegenie/fallback/fence/wrapper.py`](../../../../src/codegenie/fallback/fence/wrapper.py): (1) the delimiter format is `<UNTRUSTED_INPUT id={nonce}>...</UNTRUSTED_INPUT id={nonce}>` not `<BEGIN_PRIOR_ATTEMPT_...>`; (2) the canary is `secrets.token_hex(16)` (32 lowercase hex chars) — the `HexNonce` newtype pattern `^[0-9a-f]{32}$`; (3) `FenceWrapper.fence(payload, source_kind)` is the polymorphic dispatch — adding a new "kind" is one `Literal` member + one `_TRUNCATION_CAPS` row, **not a new helper method**; (4) `"prior_attempt_summary"` is **already** in `SourceKind: Literal[...]` and `_TRUNCATION_CAPS["prior_attempt_summary"] = 4 * 1024` is **already** set ([`wrapper.py:53-76`](../../../../src/codegenie/fallback/fence/wrapper.py)); (5) [`src/codegenie/fallback/fence/prompt_builder.py:153,202-203`](../../../../src/codegenie/fallback/fence/prompt_builder.py) `PromptBuilder.build` **already accepts** `prior_attempt_summary: str \| None = None` and fences it via `FenceWrapper.fence(payload, source_kind="prior_attempt_summary")`. Phase 4 S2-04 AC-13 enforces that `PromptBuilder` is the **sole fence-call site**; an AST-walking guard at [`tests/unit/fallback/test_prompt_builder_no_fence_bypass.py`](../../../../tests/) rejects any new helper that re-implements fencing. The prescribed `compose_prior_attempts` would be **rejected by CI** the moment it lands. |
| Phase 4's prompt builder appends the fence block "only when the list is non-empty"; "one call site, no scattered edits" | Phase 4 S6-02 HARDENED [`stories/S6-02-retry-bypass-rag.md:47`](../../../04-vuln-llm-fallback-rag/stories/S6-02-retry-bypass-rag.md) **already specifies** the retry-bypass branch: when `bool(prior_attempts) is True`, `FallbackTier.run` (a) skips RAG retrieval entirely, (b) emits `RagSkippedOnRetry(last_attempt_number, attempt_count, last_failing_signals)`, (c) passes `prior_attempts[-1].prior_failure_summary` (raw `str`) into `PromptBuilder.build(prior_attempt_summary=...)`. `PromptBuilder` (not `FallbackTier.run`) owns the fence call. Phase 5 produces `AttemptSummary` values via the `RetryLedger`; Phase 4's pipeline reduces them. The "compose all attempts into one block" semantics the draft prescribes is **not** what the chain does — Phase 4 takes only the *most recent* attempt. |
| `prior_failure_summary` should be truncated to 4 KB inside the new helper; longer values get `\n…[truncated]` suffix | Two separate caps, two separate layers — the draft conflates them. (a) [`AttemptSummary._summary_bounds`](../../../../src/codegenie/transforms/apply_context.py:98) validates the **stored** `prior_failure_summary` to ≤ **8192 UTF-8 bytes** (`_SUMMARY_UTF8_BYTES_CAP`) at model-validate time, rejecting (not silently truncating) over-cap values. (b) [`_TRUNCATION_CAPS["prior_attempt_summary"] = 4 * 1024`](../../../../src/codegenie/fallback/fence/wrapper.py:75) is the **render-time** UTF-8-byte cap applied by `fence_pure` inside Phase 4's prompt-build path — codepoint-safe (multi-byte sequences are not split), no `…[truncated]` text marker (the `FencedSegment.truncated: bool` field carries the signal). The draft's "one cap, ASCII ellipsis marker" model is wrong on both axes. |
| Mock target `codegenie.llm.fence.canary_matcher.match` | `codegenie.llm.fence` **does not exist**. The actual fence module tree is at `codegenie.fallback.fence` ([`wrapper.py`](../../../../src/codegenie/fallback/fence/wrapper.py), [`canary.py`](../../../../src/codegenie/fallback/fence/canary.py), [`prompt_builder.py`](../../../../src/codegenie/fallback/fence/prompt_builder.py)). There is no `canary_matcher` module; the canary surface is `Scanner` (Protocol) + `CanaryGuard` (production impl per Phase-4 S2-03 GREEN) + `scan_pure`. The `monkeypatch.setattr("codegenie.llm.fence.canary_matcher.match", ...)` would `ModuleNotFoundError` before the test ran. |
| `tests/golden/prompts/fallback_tier_no_prior_attempts.txt` is the byte-identical baseline | (a) Phase 4 S6-01/S6-02 HARDENED do not ship such a golden file. The Phase-4-canonical determinism check is [`tests/unit/fallback/test_prompt_builder_byte_identical.py`](../../../../tests/) via the 50-run property test in S6-07 (which asserts byte-identical assembled prompts under cassette replay). (b) "Byte-identical baseline before/after a default-empty kwarg addition" is trivially true *because the kwarg has no effect when empty* — there is no useful regression a golden captures here that the existing prompt-builder property tests do not already cover. |
| Phase 3 and Phase 4 contract-snapshot tests "regenerate intentionally" in this PR | The contract-snapshot regeneration for `ApplyContext` happened when Phase 3 S1-04 shipped (commit lineage: S1-04 GREEN landed `prior_attempts` proactively per ADR-0001 §Decision C). The contract-snapshot regeneration for `FallbackTier.run` will happen when Phase 4 S6-01 reaches GREEN (it is currently HARDENED). Neither regeneration is owned by S5-03 — both are owned by their respective shipping stories. |
| Mutable default `prior_attempts: list[AttemptSummary] = []` | Python's `def f(x=[])` shares the list across calls — a textbook footgun. Phase 3 ships `tuple[AttemptSummary, ...] = ()` and Phase 4 S6-01 HARDENED ships `Sequence[AttemptSummary] = ()` precisely to close this. The draft's "field(default_factory=list)" is a band-aid; the upstream choice is immutable-default + read-covariant annotation. |

The validator's response: **rescope the story to its non-deferred residual core — Phase-5-side cross-phase conformance fences that pin the shipped contracts so a future renaming surfaces loud — and delete every AC that prescribes work already absorbed by S1-04 (Phase 3 GREEN), S6-01 (Phase 4 HARDENED), or S6-02 (Phase 4 HARDENED). Replace the rejected `compose_prior_attempts` helper with a Notes-for-implementer paragraph documenting the canonical reduction path. Surface the cross-story contradiction (S5-05 asserts `<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>` in the prompt — this is wrong shape; S5-05 needs its own re-validation pass).**

The remaining slice — what S5-03 actually owns:

1. **Cross-phase conformance fence test** at `tests/schema/test_phase5_cross_phase_prior_attempts_contract.py` that pins the byte-stable surface of the ADR-0002 amendment by introspecting upstream symbols:
   - `ApplyContext` has a field named `prior_attempts`, container type `tuple[AttemptSummary, ...]`, default `()`.
   - `AttemptSummary` is importable from `codegenie.transforms.apply_context` (NOT `codegenie.gates.contract`).
   - Phase 4's `SourceKind` Literal union contains `"prior_attempt_summary"`.
   - Phase 4's `_TRUNCATION_CAPS["prior_attempt_summary"]` is exactly `4 * 1024`.
   - Phase 4's `PromptBuilder.build` signature accepts the keyword `prior_attempt_summary: str | None` with default `None`.
   - Phase 4's `FallbackTier.run` signature (when GREEN; until then, asserted *conditionally* — skipped with a clear reason while the class is HARDENED-only) is `async def run(advisory, repo_ctx, recipe_selection, *, prior_attempts: Sequence[AttemptSummary] = ()) -> RecipeApplication`.
2. **A Phase-5-side `ReplanHook`-facing adapter test** that constructs a `ctx: GateContext` with a non-empty `prior_attempts: tuple[AttemptSummary, ...]` (Phase 5's own surface), invokes the orchestrator's `make_orchestrator_replan_hook` closure from S5-01, and asserts the closure forwards `prior_attempts=` to `FallbackTier.run` **by identity** (via `AsyncMock(spec=FallbackTier).run.assert_awaited_once_with(...)`). This is the *Phase-5-side* mirror of S6-01's tape; it pins the kwarg name + identity at the seam.
3. **A documented surfacing of the cross-story contradiction with S5-05** (the `<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>` regex assertion in S5-05 is bound to the rejected helper and must be re-validated to use the actual `<UNTRUSTED_INPUT id=[0-9a-f]{32}>` shape, plus the `prior_attempts[-1]` reduction).

That's enough to land a Phase-5-side conformance gate without duplicating any upstream work, and it leaves a loud breadcrumb for the S5-05 follow-up.

No `RESCUE`-tier escalation: the goal (own the Phase-5-side of ADR-0002) survives the rewrite intact; ADR-0002's text — its decision, tradeoffs, and consequences — does not change; the cross-phase contract is unchanged; only the *prescribed implementation work* in the story is rewritten. Every gap was patchable from in-repo precedents (Phase 4 S2-02/S2-04 GREEN code, S6-01/S6-02 HARDENED stories, Phase 3 S1-04 GREEN code) and the four phase-5 HARDENED sibling stories. **Stage 3 (research) was skipped — every gap was answerable from in-repo precedents and the prior validation reports.**

## Findings by critic

### Coverage critic (12 findings: 6 block, 4 harden, 2 nit)

#### Block-tier

1. **(coverage — block) AC-2 (`ApplyContext` gains a field) is already-satisfied upstream.** Phase 3 S1-04 GREEN shipped the field with `tuple` container + immutable default; the field shape is byte-stable. **Fix:** Delete AC-2 as an "edit to ship"; replace with AC-CONF-1 — a Phase-5-side conformance test that *introspects* `ApplyContext.model_fields["prior_attempts"]` and asserts annotation `tuple[AttemptSummary, ...]` and default `()`.

2. **(coverage — block) AC-1 (`FallbackTier.run` kwarg with mutable default) prescribes the wrong shape.** Phase 4 S6-01 HARDENED pinned `Sequence[AttemptSummary] = ()` keyword-only async. **Fix:** AC-1 replaced with AC-CONF-2 that introspects `inspect.signature(FallbackTier.run)` against the HARDENED-upstream contract (skipped with `pytest.skip("S6-01 not GREEN yet")` until the class lands; converts from skip to fail-loud when GREEN).

3. **(coverage — block) AC-3 (build `FenceWrapper.compose_prior_attempts`) prescribes a CI-rejected helper.** S2-04 AC-13's AST-walking "PromptBuilder is the sole fence-call site" guard would reject the helper on PR. **Fix:** Delete AC-3 entirely; add `Notes for implementer` documenting the canonical reduction path (`prior_attempts[-1].prior_failure_summary` → `PromptBuilder.build(prior_attempt_summary=...)`).

4. **(coverage — block) AC-4 (canary token `secrets.token_hex(8).upper()`, 16 hex chars uppercase) contradicts the shipped fence.** Production uses `secrets.token_hex(16)` → 32 lowercase hex chars as the `HexNonce` newtype. **Fix:** Delete AC-4; add AC-CONF-3 that pins the actual shipped nonce shape (`re.fullmatch(r"^[0-9a-f]{32}$", nonce)`).

5. **(coverage — block) AC-5 (Phase 4 prompt builder appends only when non-empty) prescribes wrong location and wrong reduction.** Phase 4 S6-02 HARDENED specifies the bypass branch lives in `FallbackTier.run` (NOT in `PromptBuilder.build`), and the reduction is `prior_attempts[-1]` (most recent only), not "compose all attempts". **Fix:** Delete AC-5; document the upstream-owned reduction in Notes.

6. **(coverage — block) AC-6 (helper tests at `tests/llm/test_fence_compose_prior_attempts.py`) tests a rejected helper.** Module path `tests/llm/` does not exist; Phase 4 fence tests live under `tests/unit/fallback/`. **Fix:** Delete AC-6 entirely. The fence behavior for `prior_attempt_summary` is owned by Phase 4 S2-02/S2-04 tests; Phase 5 owns *contract conformance* tests, not fence-internal tests.

#### Harden-tier

7. **(coverage — harden) `AttemptSummary` import path wrong throughout (`codegenie.gates.contract` → `codegenie.transforms.apply_context`).** **Fix:** AC-IMP-1 — every TDD test imports from the shipped location; the conformance test asserts the importable path is exactly `codegenie.transforms.apply_context.AttemptSummary`.

8. **(coverage — harden) `AttemptSummary` field shape misstated.** Field names (`attempt_id` → `attempt`; no `sandbox_run_id`), container types (`list[str]` → `tuple[SignalKind, ...]`; `dict` → `tuple[SandboxedPath, ...]`) all wrong. **Fix:** AC-IMP-2 — conformance test introspects `AttemptSummary.model_fields` against the shipped shape, citing the line in `apply_context.py`.

9. **(coverage — harden) 4 KB vs 8 KB conflation.** Two caps, two layers. **Fix:** AC-IMP-3 — conformance test pins both: `AttemptSummary._SUMMARY_UTF8_BYTES_CAP == 8192` (validation cap) AND `_TRUNCATION_CAPS["prior_attempt_summary"] == 4096` (fence render cap).

10. **(coverage — harden) Replan-hook seam test missing.** Phase-5-side identity-preservation test (closure forwards `prior_attempts=` by identity to `FallbackTier.run`) is not specified. **Fix:** AC-SEAM-1 — `AsyncMock(spec=FallbackTier).run.assert_awaited_once_with(..., prior_attempts=ctx.prior_attempts)` (asserts kwarg-name + identity).

#### Nit

11. **(coverage — nit) Files-to-touch list names six non-existent paths.** `src/codegenie/llm/fence.py`, `src/codegenie/plan/fallback.py`, `src/codegenie/orchestrator/apply_context.py`, `tests/llm/`, `tests/plan/`, `tests/golden/prompts/` — none exist. **Fix:** Files-to-touch rewritten to the single new conformance test file + a one-line update to the cross-story note in S5-05 (flagged as a follow-up).

12. **(coverage — nit) "Phase 3 and Phase 4 contract-snapshot tests regenerate" not S5-03's responsibility.** **Fix:** Delete the AC; cite ADR-0002 § Consequences directly in Notes (regen happens at the *shipping* story for each side).

### Test-Quality critic (8 findings: 3 block, 4 harden, 1 nit)

#### Block-tier

T1. **(test-quality — block) `monkeypatch.setattr("codegenie.llm.fence.canary_matcher.match", ...)`** targets a nonexistent module and would raise `ModuleNotFoundError`. **Fix:** Replace with an introspective conformance test against the actual `codegenie.fallback.fence.wrapper.FenceWrapper` surface (no monkeypatch needed — Phase 4 owns the fence-internal tests).

T2. **(test-quality — block) Golden-file baseline test is tautological.** "No kwarg produces byte-identical baseline" is trivially true when the kwarg has no effect when empty (which is the entire point of "additive"). It does not catch any meaningful mutation. **Fix:** Delete the golden test; pin the property via the existing S6-07 byte-identical replay property test (50-run, owned by Phase 4).

T3. **(test-quality — block) `[\"tests\"]` / `\"r1\"` JSON-escaped-quote literals in the TDD plan.** Identical regression to the one S5-02 validation closed. The verbatim Python in the TDD plan would `SyntaxError` if copied. **Fix:** AC-PLAIN-PY-1 asserts `ast.parse(...)` parses the test file; the TDD plan is rewritten with proper Python literals.

#### Harden-tier

T4. **(test-quality — harden) `MagicMock` for `FallbackTier` would not satisfy `async def run`.** Phase 4 S6-01 HARDENED locked `run` to `async`. `MagicMock(spec=FallbackTier).run(...)` returns a `MagicMock`, not a coroutine; `await closure(ctx)` raises `TypeError`. **Fix:** Use `AsyncMock(spec=FallbackTier)`; the test imports `FallbackTier` symbol from `codegenie.fallback.tier` and skips with a clear reason if the symbol is not yet importable (S6-01 not GREEN).

T5. **(test-quality — harden) No identity assertion on the forwarded kwarg.** The seam needs `assert_awaited_once_with(..., prior_attempts=ctx.prior_attempts)` to catch a "rebuild a fresh tuple from the items" regression that mutates audit/identity downstream. **Fix:** AC-SEAM-1 pins identity via `is` (or `assert_awaited_once_with` against the exact tuple object).

T6. **(test-quality — harden) No metamorphic-pair on kwarg-absent vs kwarg-empty equivalence.** Phase 4's `Sequence[AttemptSummary] = ()` default makes `run(...)` and `run(..., prior_attempts=())` semantically identical; a regression that special-cases "kwarg present at all" vs "kwarg empty tuple" would not be caught by the draft's tests. **Fix:** AC-META-1 — parametrize over `("absent", ())` and assert the resulting `FencedPromptBody` is byte-identical (cassette-replayed; reuses S6-07 infrastructure).

T7. **(test-quality — harden) No structural assertion that `prior_attempt_summary` SourceKind is present.** A future ADR amendment could drop it; we need a loud structural test in Phase 5 that depends on the source-kind so any future drop fails Phase 5's CI first. **Fix:** AC-CONF-4 — introspect `get_args(SourceKind)` and assert `"prior_attempt_summary"` is present; the test cites ADR-0002 in its docstring.

#### Nit

T8. **(test-quality — nit) `fallback_tier_stub.last_prompt_text()` invented helper.** Not a Phase-4-canonical pattern. **Fix:** Use the canonical `capturing_event_log` + `PromptAssembled.fenced_body_byte_length` introspection pattern from Phase 4 S6-01 HARDENED instead.

### Consistency critic (9 findings: 5 block, 3 harden, 1 nit)

#### Block-tier

C1. **(consistency — block) Story prescribes `codegenie.llm.fence` — the path does not exist; the actual module is `codegenie.fallback.fence`.** **Fix:** Every reference updated; `codegenie.llm.fence` removed.

C2. **(consistency — block) Story prescribes `<BEGIN_PRIOR_ATTEMPT_{canary}>` delimiter — contradicts the shipped `<UNTRUSTED_INPUT id={nonce}>` delimiter (Phase 4 S2-02 GREEN).** Direct Rule 7 violation (would "average" two delimiter schemes). **Fix:** Delete prescription; cite the shipped delimiter format in Notes.

C3. **(consistency — block) Story prescribes a new `FenceWrapper.compose_prior_attempts` static method — contradicts Phase 4 S2-04 AC-13 "PromptBuilder is the sole fence-call site" (AST-walking guard at `test_prompt_builder_no_fence_bypass.py`).** **Fix:** Delete prescription; the reduction is `prior_attempts[-1].prior_failure_summary` (raw `str`) → `PromptBuilder.build(prior_attempt_summary=...)`.

C4. **(consistency — block) `AttemptSummary` import path `codegenie.gates.contract` is wrong** — shipped at `codegenie.transforms.apply_context`. **Fix:** Every import path corrected throughout the story.

C5. **(consistency — block) Mutable-default `prior_attempts: list[AttemptSummary] = []` contradicts the V-D-F2 closure on shipped `ApplyContext.prior_attempts: tuple[...] = ()` AND Phase 4 S6-01 HARDENED `Sequence[AttemptSummary] = ()`.** Rule 7 (do not average). **Fix:** All references replaced with `Sequence[AttemptSummary] = ()` / `tuple[AttemptSummary, ...] = ()`.

#### Harden-tier

C6. **(consistency — harden) Cross-story contradiction with S5-05.** S5-05 asserts `re.search(r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>", text)` — bound to the rejected helper. Without S5-05's own re-validation, this story's HARDENED rewrite leaves a planted contradiction. **Fix:** Document the follow-up in Notes-for-implementer; recommend S5-05 be re-validated by the validator before execution.

C7. **(consistency — harden) Phase 4 S6-02 HARDENED specifies retry-bypass owns the prompt assembly, NOT the FallbackTier-level "if prior_attempts: prompt += ..." pseudocode in the draft outline.** **Fix:** Replace implementation outline with a description of the existing flow (S6-02-owned), with Phase 5 producing `AttemptSummary` values via `RetryLedger` only.

C8. **(consistency — harden) ADR-0002 § Consequences says "Phase 4's contract-snapshot test regenerates (loud, intentional) as part of the Phase 5 PR" — but Phase 4's `tier.py` is not yet GREEN, so this regeneration cannot happen in the Phase 5 PR that ships S5-03.** **Fix:** ADR-0002 § Consequences is informational about WHEN the regeneration happens — it does not bind it to *this* story. Notes-for-implementer clarifies: regeneration happens at S6-01 GREEN (which lands the class); this story does not regenerate any contract snapshot.

#### Nit

C9. **(consistency — nit) Story uses `attempt_id` throughout — shipped field is `attempt` (newtype `AttemptNumber`).** **Fix:** All AC text + outline references updated to `attempt`.

### Design-Patterns critic (7 findings: 4 block, 2 harden, 1 nit)

#### Block-tier

D1. **(design — block) Prescribed `FenceWrapper.compose_prior_attempts` static helper violates the kernel's polymorphism-by-data strategy.** The shipped kernel dispatches on `source_kind: Literal[...]` via `_TRUNCATION_CAPS[source_kind]` — adding a new "fence purpose" should be **one Literal member + one cap row**, never a new method. The draft's helper would fork the Strategy pattern in place. **Fix:** Story rewrite explicitly *consumes* the shipped kernel; no new helper. The `prior_attempt_summary` SourceKind ALREADY exists (shipped) — Phase 5 owes nothing here.

D2. **(design — block) Prescribed helper violates the functional-core / imperative-shell separation that S2-02 enshrines.** `fence_pure` is the pure core (stdlib + Pydantic, no I/O, no events); `FenceWrapper` is the imperative shell (mints nonces, emits `FenceApplied` / `CanaryCollision` audit events). A `compose_prior_attempts` static method that mints canaries inside the helper would either bypass the shell (no audit events) or re-mint inside the core (impure core). Either is a regression. **Fix:** Helper deleted; reduction flows through `PromptBuilder.build` → `FenceWrapper.fence` → `fence_pure` (audit events preserved automatically).

D3. **(design — block) Prescribed helper violates the sole-mint-site discipline (S2-04 AC-13).** `PromptBuilder` is the only module that may construct `FencedPromptBody` / `TrustedPrompt` newtypes; the AST-walking guard at [`tests/unit/fallback/test_prompt_builder_no_fence_bypass.py`](../../../../tests/) rejects any new `FenceWrapper.fence(...)` call outside `prompt_builder.py`. The helper would be rejected by CI before merge. **Fix:** Helper deleted (already covered by D1/D2).

D4. **(design — block) Primitive obsession on the canary token.** Draft mints raw `str` (`secrets.token_hex(8).upper()`); shipped kernel uses the `HexNonce = NewType("HexNonce", str)` newtype with a documented `^[0-9a-f]{32}$` pattern (the only sanctioned raw cast lives in `_default_nonce_source`). **Fix:** Story Notes-for-implementer cites `HexNonce` as the only correct typed surface.

#### Harden-tier

D5. **(design — harden) Anaemic Notes-for-implementer fail to surface that the entire prescribed surface area is duplicative.** A future implementer reading the draft would write the helper and only learn it's rejected when CI fails. **Fix:** Notes rewritten as a load-bearing "do not build this" paragraph with explicit citations.

D6. **(design — harden) The Phase-5-side conformance fence is the *correct* design pattern here — a CI fence that pins an external (cross-package) contract from the consumer's side.** The story did not name this pattern. **Fix:** Story rewrite explicitly frames the work as a "consumer-side contract fence" (a Phase-3 import-linter-style structural guard that fails loud when an upstream signature drifts).

#### Nit

D7. **(design — nit) `AttemptSummary` belongs in `codegenie.transforms` (which it does); the original arch text framing of "Phase 5 owns the schema" is an aspiration, not the shipped location.** **Fix:** Notes-for-implementer surfaces the ownership clarification (Phase 5 owns the *retry-ledger semantics* and *evidence-paths discipline*; Phase 3 owns the *model* — they coexist).

## Conflict resolution log

- **Coverage AC-2 (Phase 5 edits `ApplyContext`) vs Consistency C5 (`ApplyContext.prior_attempts` is already shipped with the correct immutable shape).** Consistency wins (shipped code is authoritative). AC-2 dropped; replaced with a conformance test.
- **Coverage AC-3/AC-4/AC-5/AC-6 (build new `FenceWrapper.compose_prior_attempts` helper with own delimiter scheme) vs Design D1/D2/D3 (helper violates four shipped patterns and would be CI-rejected).** Design wins on every dimension (kernel polymorphism-by-data, functional-core/imperative-shell, sole-mint-site discipline, primitive-obsession typing). Helper dropped; canonical reduction documented.
- **Coverage AC-7 (Phase 3 + Phase 4 contract snapshots regenerate in this PR) vs Consistency C8 (regeneration is owned by the shipping story for each side, not by S5-03).** Consistency wins. AC-7 dropped; Notes clarify the ADR § Consequences applies at the shipping story for each side.
- **Test-Quality T2 (delete tautological golden) vs Coverage AC-baseline-byte-identical (golden is required).** Test-Quality wins (the golden is provably tautological for an additive default-empty kwarg). The byte-identical property is already covered by S6-07.

## Edits applied (story diff summary)

The story file was rewritten in place to:

1. **Goal** — narrowed to "land the Phase-5-side cross-phase conformance fences for the ADR-0002 amendment, given that the implementation work is owned upstream (Phase 3 S1-04 GREEN; Phase 4 S6-01/S6-02 HARDENED)".
2. **Acceptance criteria** — every AC replaced. New ACs are introspection-driven conformance assertions plus one identity-preserving replan-hook seam test.
3. **Implementation outline** — rewritten to describe the conformance test file structure (no production code change in `src/codegenie/` is owed by this story).
4. **TDD plan** — completely rewritten; no `monkeypatch` on nonexistent modules; AsyncMock-based seam test; `inspect.signature` + `get_args(SourceKind)` + `model_fields` introspection patterns; every TDD test under `tests/schema/` and `tests/unit/orchestrator/` (the canonical conformance-fence directories).
5. **Files to touch** — list rewritten to one new conformance-test file + (optionally) a Notes-for-implementer cross-story breadcrumb pointing to S5-05's regex-assertion that needs re-validation.
6. **Out of scope** — broadened to *explicitly* exclude all the upstream-owned work (the `FenceWrapper` helper, the `FallbackTier.run` signature change, the `ApplyContext` field addition, the Phase 4 prompt-builder edit, the contract-snapshot regenerations, the live cassette recording).
7. **Notes for implementer** — rewritten as load-bearing "do not build the rejected helper; consume the existing kernel; the cross-phase reduction lives in S6-02 HARDENED; here is exactly which symbols to introspect".
8. **Validation notes** — appended after the story header documenting every change.
9. **Status** — promoted `Ready` → `Ready (HARDENED 2026-05-25)` to match the family convention.

The story remains INVEST-shaped: small (S effort, one test file + cross-story breadcrumb), independently testable (introspection-only — no upstream-Green dependency for most ACs), and trace-able to ADR-0002 + the four upstream HARDENED-or-GREEN surfaces.

## Stage 3 (research) — skipped

No `NEEDS RESEARCH` tags. Every gap was answerable from in-repo precedents (Phase 4 S2-02/S2-04 GREEN code; S6-01/S6-02 HARDENED stories; Phase 3 S1-04 GREEN code) and from CLAUDE.md's load-bearing commitments.

## Cross-story follow-ups surfaced

- **S5-05 needs re-validation.** Its load-bearing regex assertion `re.search(r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>", text)` is tied to the helper this validation rejected. The correct assertion is `re.search(r"<UNTRUSTED_INPUT id=[0-9a-f]{32}>.*?(?:</UNTRUSTED_INPUT id=[0-9a-f]{32}>)", text, re.DOTALL)` with the additional check that `PromptAssembled.source_kinds_used` contains `"prior_attempt_summary"` (the canonical structural check from Phase 4 S6-02 HARDENED). The next validator run targeting S5-05 should fold this in.

## Verdict

**HARDENED.** Story rewritten in place. Ready for executor pickup *with the caveat* that the conformance tests targeting `FallbackTier` will skip-with-reason until Phase 4 S6-01 reaches GREEN, at which point the skip flips to a hard assertion. This is the correct shape — Phase 5 does not need Phase 4 to land before Phase 5's own conformance fences can ship, but the cross-package assertions guard the contract once it does.
