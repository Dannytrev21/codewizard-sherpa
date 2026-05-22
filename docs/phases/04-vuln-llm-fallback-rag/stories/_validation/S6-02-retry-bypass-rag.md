# Validation report — S6-02 — Retry path bypasses RAG; prompt carries fence-wrapped `prior_failure_summary`

**Validated:** 2026-05-22
**Verdict:** **HARDENED**
**Story:** `docs/phases/04-vuln-llm-fallback-rag/stories/S6-02-retry-bypass-rag.md`

## Context brief

- **Goal under audit (original):** *"Add the retry-bypass branch to `FallbackTier.run`: when `prior_attempts != []`, skip `SolvedExampleRetriever.query` entirely, emit `RagSkippedOnRetry(attempt_count, last_failure_kind)`, and have `PromptBuilder` fence-wrap `prior_attempts[-1].prior_failure_summary` as `source_kind="prior_attempt_summary"` (4 KB cap) in place of the RAG few-shot."*
- **Phase exit criteria touched:** High-level-impl Step 6 (feature item 1, "RAG bypassed when `prior_attempts != []`"); Phase-arch §Control flow Retry path (line 819); §Edge cases row 11.
- **Authoritative ADRs:** ADR-04-0011 (the bypass decision); ADR-04-0002 (chain order *is* the policy — no Strategy/Chain-of-Responsibility); ADR-04-0013 (fence-wrap; scan untruncated then truncate); production ADR-0011 (initial-plan chain order — the deliberate departure target); production ADR-0014 (three-retry cap composes).
- **Sibling-story preconditions:** S6-01 (`FallbackTier` happy-path pipeline, HARDENED) — provides factory `make_fallback_tier_for_fixtures`, event registry pattern (`WorkflowInternalEvent` + `_INTERNAL_CLASSES`), `Sequence[AttemptSummary] = ()` signature, ten-event happy-path tape with `Counter(kinds)` multiplicity discipline. **S6-02 inherits all of S6-01's hardening; mirroring those bars onto the retry path is the main work here.**
- **Shipped contracts (must not contradict):**
  - `src/codegenie/transforms/apply_context.py:72` — `AttemptSummary` actually carries `attempt: AttemptNumber`, `failing_signals: tuple[SignalKind, ...]`, `prior_failure_summary: str`, `evidence_paths: tuple[SandboxedPath, ...]`, `transform_id: TransformId | None`. **There is no `.kind` attribute.** Field validator enforces an 8 KB UTF-8 byte cap (`_SUMMARY_UTF8_BYTES_CAP = 8192`) at construction time — a 16 KB raw payload cannot exist as a valid `AttemptSummary`.
  - `ApplyContext.prior_attempts: tuple[AttemptSummary, ...] = ()` (truly immutable).
  - S2-04 AC-4 + AC-13 — `PromptBuilder.build(..., prior_attempt_summary: str | None = None, ...)`. The kwarg is a **raw string**; `PromptBuilder` is the **sole** fence-call site (AC-13 AST-walking guard rejects any other module that constructs `FencedSegment` directly or calls `self.fence.fence(...)` outside `PromptBuilder`).
  - S2-02 AC-2 — `SourceKind: TypeAlias = Literal["cve_description", "repo_readme", "transitive_dep_meta", "source_snippet", "sandbox_stderr", "rag_retrieved", "prior_attempt_summary"]`. **Not a `StrEnum`.** `SourceKind.prior_attempt_summary` attribute-access spelling is wrong; the literal string `"prior_attempt_summary"` is correct.
- **Out-of-scope:** The cassette fixture for the integration test (recorded via `make refresh-cassettes` from S3-06); "exclude prior-attempt's RAG hit and re-query" (rejected in ADR-04-0011 §Options considered); Phase-6 LangGraph lift of the bypass branch (Phase 6's concern).

## Critic reports

### Coverage critic — verdict: block (then fixed)

1. **[block]** No retry-path event-tape AC with list-equality + `Counter(kinds)` multiplicity (S6-01 ships this discipline for happy + four refuse paths; retry path was unenforced). A mutation that emits *both* `RagSkippedOnRetry` and `RagMiss` would slip through.
2. **[block]** No AC requires `RagSkippedOnRetry` registration in `src/codegenie/plugins/events.py` `WorkflowInternalEvent` + `_INTERNAL_CLASSES` round-tripped via `_INTERNAL_ADAPTER`. Implementation outline §3 hedged ("if not already added") — without registration, first emission raises a Pydantic discriminator error at runtime.
3. **[block]** `last_failure_kind: str` is primitive obsession. Closed-set domain identifier should be typed (`SignalKind` newtype or `Literal[...]`).
4. **[harden]** `prior_attempts` with `len > 1`: goal says "most recent" (`[-1]`) but no AC parametrizes on N≥2 — a `prior_attempts[0]` regression mutation passes every AC.
5. **[harden]** No AC pins `attempt_count == len(prior_attempts)` — a hard-coded `attempt_count=1` passes with N=1.
6. **[harden]** Edge values uncovered: empty string, whitespace-only, exactly-at-cap, UTF-8 multibyte at byte boundary.
7. **[harden]** Integration test does not assert `retriever.query.assert_not_awaited()` AND `retriever.query.call_count == 0` (the "construct but never await" mutation slips past the cassette grep).
8. **[harden]** No retry-path refuse-path event-tape ACs (what if leaf refuses on retry? budget exhausted on retry? — prefix-ordering invariant from S6-01 doesn't compose).
9. **[harden]** No AC pins `PlanOutcomeEmitted.outcome` variant on retry — likely `AppliedFromLlm` (same as initial since retry also reaches the leaf), but unpinned.
10. **[nit]** Cassette-substring assertions are fragile to fence-tag format changes that no ADR pins.

### Test-Quality critic — verdict: block (then fixed)

1. **[block]** TDD plan literal `tier = FallbackTier(retriever=retriever, ..., prompt_builder=...)` uses `...` (Ellipsis) as a syntactic shortcut; that compiles but breaks the constructor. S6-01 ships `make_fallback_tier_for_fixtures(...)` precisely to avoid this. Use the factory.
2. **[block]** TDD plan imports — `AttemptSummary` is constructed but never imported in the imports block; `FENCE_TAG_OVERHEAD` is referenced but never imported (no such symbol exists in the codebase). NameError risk for the executor.
3. **[block]** No assertion that `prior_attempts[-1]` (not `[0]`) is used — with N=1, both indices return the same element. Add N=2,3 parametrize with distinguishable `prior_failure_summary` and `failing_signals`.
4. **[block]** No `attempt_count == len(prior_attempts)` assertion for N≥2 — hard-coded `attempt_count=1` slips through.
5. **[block]** Mocks not spec'd against Protocol. `retriever` is plain `AsyncMock()`; if the impl calls a renamed attribute (`self._rag.query` instead of `self._retriever.query`), the silent second mock absorbs it and the test passes vacuously. Mirror S6-01's `MagicMock(spec=EventLog)` discipline: `AsyncMock(spec=SolvedExampleRetriever)`.
6. **[block]** Canary scan-before-truncate (ADR-0013) asserted by *consequence* (redacted marker appears in fenced bytes) rather than *position*. A re-ordering refactor that happens to leave the redaction in-bounds passes. Add: (a) marker appears within `[:4096 + FENCE_TAG_OVERHEAD]` of the truncated content; (b) `CanaryCollision` event fires (ADR-0013 §Consequences).
7. **[harden]** Cross-event payload identity not enforced on retry path (S6-01 pins `PromptBuilt.digest == LeafInvoked.digest` on happy path; retry path needs the same).
8. **[harden]** Cassette-grep assertions are fragile and vacuous on format drift — replace with structured assertions over the `PromptAssembled.source_kinds_used` event tuple emitted by `PromptBuilder` per S2-04 AC-10.
9. **[harden]** Metamorphic property missing: bypassed-path output depends ONLY on `prior_attempts[-1]`. Varying `prior_attempts[:-1]` arbitrarily must produce identical prompt body + identical `RagSkippedOnRetry.last_failing_signals`.
10. **[nit]** Test names encode WHAT, not WHY (Rule 9). Mirror S6-01's docstring discipline — make the same-wrong-RAG-hit-twice motivation visible.

### Consistency critic — verdict: block (then fixed)

1. **[block]** Stale ADR cross-reference in the inherited arch document — `phase-arch-design.md` lines 819 and 938 both cite `ADR-04-0003` for the RAG bypass; the actual ADR file is `0011-rag-bypass-on-retry.md`. The story's body uses `ADR-04-0011` consistently, but a reader following the arch's pointer hits a 404. **Resolution:** add to Notes-for-implementer that this story should patch the two stale references in `phase-arch-design.md` as part of its surgical change.
2. **[block]** `prior_attempts` type drift: S6-01 hardened to `Sequence[AttemptSummary] = ()` (immutable, read-covariant). S6-02's Goal says `prior_attempts != []` — which (a) re-asserts a list-shape assumption S6-01 deliberately departed from, and (b) is semantically wrong: `() != []` evaluates to `True`, so the literal predicate misclassifies the default empty tuple as a retry. Implementation outline correctly uses `bool(prior_attempts)`. **Resolution:** rewrite Goal + AC to `bool(prior_attempts)`; add a parametrized AC that both `()` and `[]` are treated as initial-plan.
3. **[harden]** No AC forbids the `is_retry: bool` regression in `PromptBuilder.build`. Arch §Anti-patterns avoided (line 912) names this exact decision as the *precedent* for the "no boolean flags on public methods" rule. Currently advisory in Refactor §2; needs an `inspect.signature` AC to lock it.
4. **[harden]** `FENCE_TAG_OVERHEAD` is a forward-reference; the symbol does not exist in the codebase or in any phase doc. **Resolution:** either rewrite the assertion to use a structural assertion (`len(fenced.content_bytes) <= 4 KB * 2` is loose but doesn't depend on a phantom constant) or require S2-02 to export it explicitly.
5. **[harden]** `RagSkippedOnRetry` registration AC is hedged ("if not already added"); replace with explicit S6-01-style AC pinning location to `src/codegenie/plugins/events.py`.
6. **[harden]** No AC forbids pre-fence truncation inside `tier.py`. AC #5 covers "canary fires past 4 KB cap" but the implementer could truncate raw summary in `tier.py` before passing to `PromptBuilder` (a fence-bypass that defeats ADR-0013's "scan untruncated then truncate"). Need an AST-walking fence test.
7. **[harden]** Cross-link docstring duplication: ADR-04-0011 string appears twice (unit-test inline + integration-test top). Stale-ADR risk surfaces (see #1). Add a single source of truth or a fence test that walks `ADR-04-NNNN` references and resolves them.
8. **[nit]** Files-to-touch row for events: hedged location replaced with `src/codegenie/plugins/events.py` per S6-01.

### Design-Patterns critic — verdict: block (then fixed)

1. **[block]** `prior_attempts[-1].kind` is a phantom field. Shipped `AttemptSummary` (`src/codegenie/transforms/apply_context.py:72`) carries `failing_signals: tuple[SignalKind, ...]`, NOT `.kind`. The TDD-plan literal `AttemptSummary(kind="LEAF_REFUSED", ...)` and outline step 1 (`prior_attempts[-1].kind`) will not compile. **Resolution:** rewrite to use `failing_signals: tuple[SignalKind, ...]` as shipped; `RagSkippedOnRetry` field becomes `last_failing_signals: tuple[SignalKind, ...]`.
2. **[block]** `PromptBuilder.build` signature contradicts S2-04. S6-02 says "thread `Optional[FencedSegment]`"; S2-04 AC-4 ships `prior_attempt_summary: str | None = None` (raw string) and AC-13 makes `PromptBuilder` the **sole** fence-call site. Threading a `FencedSegment` from `tier.py` violates the AST-walking no-fence-bypass guard. **Resolution:** pass `prior_attempts[-1].prior_failure_summary` (raw `str`) into the existing `prior_attempt_summary` kwarg; `PromptBuilder` already owns the fence call internally per S2-04.
3. **[block]** `SourceKind.prior_attempt_summary` attribute-access spelling is wrong. S2-02 AC-2 ships `SourceKind: TypeAlias = Literal[...]` — a literal, not a `StrEnum`. The correct spelling is the bare string `"prior_attempt_summary"` (also resolves itself once `PromptBuilder` owns the fence call per #2 — `tier.py` no longer references `SourceKind` directly at all).
4. **[harden]** With #2 resolved, the "`Optional[RetrievalOutcome]` xor `Optional[FencedSegment]`" smell collapses: `PromptBuilder.build`'s shipped signature already has separate optional kwargs (`rag_few_shots: tuple[str, ...] = ()` and `prior_attempt_summary: str | None = None`); the xor invariant is enforced by *whichever* `tier.py` populates. Document the invariant in Notes-for-implementer rather than introducing a new tagged union.
5. **[harden]** No pure functional-core extraction. S6-01 extracted `transform_from_plan(plan: PlanProposal) -> Transform` for testability. Symmetric candidate: `def select_retry_summary(prior_attempts: Sequence[AttemptSummary]) -> AttemptSummary` (picks `[-1]`; asserts non-empty as defense-in-depth against future guard refactors). Lets a unit test prove `[-1]`-selection + non-empty invariant in isolation.
6. **[harden]** `RagSkippedOnRetry.last_failing_signals: tuple[SignalKind, ...]` is the typed shape (replacing primitive-obsession `last_failure_kind: str`). `SignalKind = NewType("SignalKind", str)` already exists at `src/codegenie/types/identifiers.py:96`.
7. **[harden]** `PromptBuilder.build` signature lock should be a fence test (`inspect.signature` no-bool-params); the Refactor §2 reminder is advisory only.
8. **[harden]** Files-to-touch hedge ("`src/codegenie/fallback/events.py` (or wherever event kinds live)") replaced with authoritative `src/codegenie/plugins/events.py`.
9. **[strong/keep]** `if/else` shape correctly preserved (ADR-04-0002 forbids Strategy / Chain-of-Responsibility for tier order).
10. **[strong/keep]** `FallbackTier` state-free invariant honored (retry branch uses local variables only).
11. **[nit]** `RagSkippedOnRetry.last_attempt_number: AttemptNumber = prior_attempts[-1].attempt` is more canonical (and typed) than deriving `attempt_count` from container length. Keep both: `attempt_count` is the policy-relevant counter Phase 5 reads; `last_attempt_number` correlates back to Phase-5 audit traces.
12. **[nit]** Rule-of-three reminder for Notes-for-implementer: don't pattern-soup a `RetryStrategy` Protocol; ADR-04-0011 §Reversibility commits to an additive ADR amendment if a third retry-shape ever lands (Phase 13 cost-aware re-rank is the next candidate).

## Conflict resolutions (priority: Consistency > Coverage > Test-Quality > Design-Patterns)

- **Design-Patterns #2 (`FencedSegment` threading) vs Coverage AC #3 (FencedSegment passed through):** S2-04 AC-13 is the source of truth — `PromptBuilder` is the sole fence-call site. `tier.py` passes `prior_attempts[-1].prior_failure_summary` (raw `str`) into the existing `prior_attempt_summary: str | None` kwarg. ACs rewritten accordingly. The "structural-presence of fenced segment in prompt body" assertion shifts from inspecting a `FencedSegment` kwarg to inspecting the `PromptAssembled` event's `source_kinds_used: tuple[SourceKind, ...]` (S2-04 AC-10).
- **Design-Patterns #1 (`.kind` is phantom) vs Goal text:** shipped `AttemptSummary` is the source of truth; Goal + ACs + event-field rewritten to `failing_signals: tuple[SignalKind, ...]`. ADR-04-0011 §Consequences phrasing (`prior_failure_summary: str ≤ 8 KB raw`) is consistent with shipped code; only the story's invented `.kind` was wrong. Note: ADR-04-0011 itself still uses `prior_attempts: list[AttemptSummary]` in code snippets — same Global-Rule-7 conflict S6-01 flagged. Surfaced to executor.
- **Consistency #2 (`!= []` truthiness) vs Goal phrasing:** Goal rewritten to `bool(prior_attempts)`. Parametrized AC pins that `()` and `[]` are both initial-plan (no `RagSkippedOnRetry` emitted, retriever invoked).
- **Coverage #1 (event-tape multiplicity) vs Test-Quality #7 (cross-event identity):** both adopted — list-equality + `Counter(kinds)` + cross-event identity (`PromptBuilt.digest == LeafInvoked.digest`).
- **Consistency #4 (`FENCE_TAG_OVERHEAD` phantom symbol):** rewritten to bound the fenced byte length against a loose-but-self-contained ceiling: `len(fenced_segment_recorded.content) <= 4 * 1024 + 256` (the 256-byte slack accommodates fence-tag overhead; if S2-02 ships an exact constant, the AC accepts substituting it).

## Edits applied

See the story file's `Validation notes` block for the full change list. Summary:

- **Goal rewritten:** replaced `prior_attempts != []` with `bool(prior_attempts)`; replaced phantom `.kind` field with shipped `failing_signals: tuple[SignalKind, ...]`; replaced `FencedSegment` threading with raw-string passthrough into S2-04's existing `prior_attempt_summary: str | None` kwarg.
- **15 ACs rewritten / added** — explicit retry-path event tape (list-equality + `Counter(kinds)` multiplicity); parametrized N ∈ {1, 2, 3} for `attempt_count` + `[-1]` selection; typed `RagSkippedOnRetry` fields (`last_failing_signals: tuple[SignalKind, ...]` + `last_attempt_number: AttemptNumber`); event registration in `src/codegenie/plugins/events.py` `WorkflowInternalEvent` + `_INTERNAL_CLASSES`; PromptBuilder signature lock fence test; pre-fence-truncation fence test; structural cassette assertion via `PromptAssembled.source_kinds_used`; metamorphic property (varying `prior_attempts[:-1]`); retry-path refuse-path tapes; `bool(prior_attempts)` semantics with `()` and `[]` parametrize; canary-position assertion + `CanaryCollision` event check; cross-event payload identity (`PromptBuilt.digest == LeafInvoked.digest`); edge-value coverage (empty/whitespace/at-cap/multibyte).
- **Implementation outline rewritten:** uses `make_fallback_tier_for_fixtures` factory; explicit `select_retry_summary(prior_attempts) -> AttemptSummary` pure helper; passes raw `prior_failure_summary` into `PromptBuilder.build`'s existing `prior_attempt_summary` kwarg (not `FencedSegment`); registers `RagSkippedOnRetry` in `src/codegenie/plugins/events.py`.
- **TDD plan rewritten:** factory replaces `...`-Ellipsis constructor; explicit imports (`AttemptSummary`, `SignalKind`); `AsyncMock(spec=SolvedExampleRetriever)`; parametrized N ∈ {1, 2, 3}; structural assertions over events rather than cassette greps; metamorphic property test added; tests use 8 KB cap (the shipped `_SUMMARY_UTF8_BYTES_CAP`) rather than the un-constructible 16 KB.
- **Files-to-touch:** events location authoritative (`src/codegenie/plugins/events.py`); `PromptBuilder` no signature change required (S2-04 already accepts the kwarg).
- **Notes-for-implementer expanded:** shipped `AttemptSummary` shape; ADR-04-0011 text-vs-shipped `list`/`tuple` Global-Rule-7 conflict (same one S6-01 surfaced); stale `ADR-04-0003` references in `phase-arch-design.md` lines 819 + 938 — patch as part of this surgical change; `is_retry: bool` regression guard; rule-of-three reminder for `RetryStrategy`; `select_retry_summary` non-empty invariant is defense-in-depth.

## Final verdict

**HARDENED.** Story now matches shipped contracts (no phantom `.kind`; no fence-bypass; correct `SourceKind` spelling; constructible `AttemptSummary`); inherits S6-01's tape/multiplicity/event-registry rigor; pins `[-1]` selection and `attempt_count` with parametrize; closes the canary scan-before-truncate position invariant; replaces fragile cassette greps with structural event assertions. Two cross-phase conflicts (`AttemptSummary` shape vs `.kind` text; ADR text `list` vs shipped `tuple`) surfaced to the implementer rather than silently averaged. One out-of-scope surgical sweep (stale `ADR-04-0003` references) added to scope so the implementer doesn't leave broken in-doc links.
