# Story S7-10 — Phase-5 contract snapshot + ops runbooks

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** GREEN-partial — 2026-05-26 (phase-story-executor; ops-docs slice; see [`_attempts/S7-10.md`](_attempts/S7-10.md)). Shipped `docs/operations/secrets.md` (NEW) + canonical S7-10 section headings appended to `cassettes.md` + `embeddings.md` (preserving existing S3-06 + S4-01 prose) + `tests/integration/test_ops_docs_exist.py` with pure `parse_section_body` helper + 7 tests covering AC-11/12/13/14/16. **Contract-snapshot portion (AC-1..AC-10, AC-17, AC-18) BLOCKED** on Phase-3 S6-06 not shipping on master: `tests/integration/test_phase5_contract_snapshot.py` + `tests/golden/phase5-contract/` + `scripts/regen_probe_contract_snapshot.py` are all absent on master. AC-15 (`make docs --strict`) is a follow-up to run before merge.
**Effort:** M
**Depends on:** Phase-3 `S6-06` **GREEN** (the canonical `tests/integration/test_phase5_contract_snapshot.py` file + its registry-driven classifier + golden-file format MUST exist before this story extends them — at validation time S6-06 was HARDENED-not-GREEN and the test file did not yet exist on disk); S7-06 (full E2E green — the snapshot is honest only if the contract surface actually works); S6-01 (`FallbackTier.run` signature stable); S3-05 (`cassettes.lock` format stable); S3-02 (`AnthropicLeafAdapter` + `keyring` flow stable); S2-05 (`LlmInvocationGuard.running_total`); S4-06 (`SolvedExampleWriteCapability` mint surface); S4-01 (embeddings bootstrap); S3-06 (`docs/operations/cassettes.md` stub — this story finalizes it)
**ADRs honored:** Phase-4 ADR-0002 (FallbackTier signature stability), Phase-4 ADR-0005 (no env-var fallback for Anthropic key — `secrets.md` cross-link), Phase-4 ADR-0006 (egress-guard cross-link from `secrets.md`), Phase-4 ADR-0007 (fastembed-onnx; embeddings bootstrap discipline), Phase-4 ADR-0008 (two-threshold calibration band; embeddings doc footnote), Phase-4 ADR-0009 (`_phase4_local_capability_mint` is interim — Phase 5 supersedes; the snapshot pins the **interim name** explicitly and a Phase-5 rename is a contract event requiring an ADR amendment per Phase-3 ADR-0001 §Consequences row 2), Phase-4 ADR-0010 (`LlmInvocationGuard` budget-token capability — `running_total` shape pinned), Phase-4 ADR-0013 (FenceWrapper canary scan — `fence` signature pinned), Phase-4 ADR-0014 (cassette discipline — `cassettes.md` runbook anchor + `cassettes.lock` format pin), Phase-3 ADR-0001 (Phase-5 contract surface; §Consequences row 1 mandates re-export from `codegenie.transforms`; row 2 mandates the snapshot test + the `PHASE 5 CANNOT SHIP` directive-message format), production-ADR-0031 (extension by addition; Phase 5 hands-off contract)

## Validation notes (2026-05-24)

This story was hardened against shipped reality at HEAD `9f3ec45`. At validation time, neither `tests/integration/test_phase5_contract_snapshot.py` (Phase-3 S6-06 deliverable; HARDENED, not GREEN) nor `src/codegenie/fallback/*` (Phase-4 implementation; not started) existed on disk. The story is therefore correctly forward-looking; the edits below pin the discipline it must inherit from S6-06 and resolve internal contradictions.

Edits applied:

1. **Status** flipped to `HARDENED` with link to validation report.
2. **Depends on** expanded: Phase-3 `S6-06` **GREEN** is now an explicit hard precondition (the snapshot file must exist before this story extends it); S3-06 (cassettes.md stub) added.
3. **ADRs honored** expanded from 3 to 11 entries: Phase-4 ADR-0010 (LlmInvocationGuard), ADR-0013 (FenceWrapper canary), ADR-0014 (cassette discipline), ADR-0005 + ADR-0006 + ADR-0007 + ADR-0008 (cited inside the story body but missing from the header line), and Phase-3 ADR-0001 (the upstream contract-surface ADR whose §Consequences row 2 the directive-message format inherits from). production-ADR-0031 retained.
4. **AC-1 reframed** to inherit S6-06's golden-file approach + classifier registry. The TDD plan's `inspect.signature(...)` string comparison contradicted both the story's own Notes ("if cross-version stability is hard, dump the signature to a golden file") and S6-06's hardened discipline (golden file under `tests/golden/phase5-contract/`, registry-driven classifier with 6 breaking-delta families, deterministic property test, no-silent-rewrite fence, directive-message format, functional-core helpers `snapshot_symbol`/`diff_snapshots`/`format_breaking_delta_message`, Pydantic-version pin). The five Phase-4 captures now plumb through `snapshot_symbol(...)` + the existing `@register_snapshot_kind`/`@register_delta_rule` registries — no new helpers, no new classifier rules (else explicit ADR amendment).
5. **AC for directive-message format** added: a breaking delta in any of the five Phase-4 captures emits the same `PHASE 5 CANNOT SHIP` diagnostic format established by S6-06 (cite Phase-3 ADR-0001 §Consequences row 2). Future-implementer cannot regress operator UX without a red test.
6. **Meta-tests for breaking-delta detection** added (mirrors S6-06's six meta-test cases) — one per Phase-4 capture: `prior_attempts` becoming required, `running_total()` returning `dict` instead of `BudgetSnapshot`, `FenceWrapper.fence` losing the `source_kind` kwarg, `SolvedExampleWriteCapability` losing `frozen=True`, `cassettes.lock` line-format regex changing. Without these, the classifier could silently accept a breaking delta on a Phase-4 entry.
7. **Determinism property** extended to Phase-4 entries: 10× same-source → byte-identical snapshot.
8. **Pydantic-version pin** AC added: the golden encodes Pydantic's exact JSON-schema-emitter output; `pyproject.toml` carries `pydantic == X.Y.*`; a Pydantic minor bump is a contract event.
9. **Interim-name pinning** AC added for `_phase4_local_capability_mint`: the snapshot pins the **exact interim name**; Phase-5 supersession (ADR-0009) requires an ADR-0001-amendment + golden refresh in the same PR (matches S6-06's discipline).
10. **TDD plan's separate file** changed to extension-in-place. The v1 plan created `tests/integration/test_phase5_contract_snapshot_phase4_additions.py` — bifurcating the canonical surface and contradicting AC-1's "extended (not rewritten)". The plan now extends `tests/integration/test_phase5_contract_snapshot.py` directly (or invokes S6-06's regen script `scripts/regen_probe_contract_snapshot.py` against the additive entries — confirm naming at execution).
11. **`_sig(obj)` ad-hoc helper removed** from TDD plan. The hardened story consumes S6-06's pure functional-core helpers (`snapshot_symbol`, `diff_snapshots`) — no parallel helper invention (Open/Closed; Rule 11 match existing convention).
12. **Ops-doc smoke test strengthened**: `test_ops_doc_exists_with_sections` was a substring check (passable by putting the section name inside a comment with no body). New AC requires each section be a level-2 Markdown heading (`## `) followed by non-empty content (≥3 lines or a fenced code block); pin via a `parse_section_body(...)` helper test.
13. **`fallback_tier_callable` fixture pinned by Protocol**: v1 said "structurally matches `FallbackTier.run`" — unverifiable. New AC requires the fixture module to export a `FallbackTierCallable` Protocol *and* the `fallback_tier_callable` instance; Phase 6's lift can `isinstance(fallback_tier_callable, FallbackTierCallable)`. Fixture is wired with mock collaborators that observe at least one call (the mock asserts it ran end-to-end; not a pure-pass-through impl).
14. **Behavior test for the fixture** added: calling `fallback_tier_callable` with a minimal valid input (advisory, repo_ctx, recipe_selection, prior_attempts=[]) returns a `RecipeApplication` (does not raise; mocks observe the expected call sequence). v1's `test_fallback_tier_callable_fixture_published` only checked `iscoroutinefunction`.
15. **Missing-lock-file edge case** added for `embeddings.md`: refuse-to-start applies to both **lock drift** *and* **lock missing entirely** (the v1 doc only mentioned drift).
16. **No-silent-rewrite fence** AC extended to Phase-4 entries: without `UPDATE_GOLDEN=1`, the test MUST NOT write to the golden path even for the additive Phase-4 captures.
17. **Refuse-to-start cross-link**: `secrets.md`'s "Refuse-to-start" section must cite the executable test (`tests/integration/test_anthropic_leaf_refuse_on_missing_key.py` or successor from S3-02) — not a free-floating prose claim.
18. **ADR-citation accuracy fixed**: v1 attributed "no env-var fallback" to ADR-0006 — that ADR is the egress-guard loopback-carveout decision. The no-env-var-fallback discipline lives in Phase-4 ADR-0005 (`no-spki-pin-egress-defense-in-depth` §"Anthropic key in keyring; refuse-to-start on missing key"). Cite both, primary = ADR-0005.
19. **`Notes for the implementer`** extended with: (a) the story bundles three deliverables on purpose (shared Step-7 deadline + handoff owner); single-responsibility concern noted but kept — Rule 2 (Simplicity First) wins over story-splitting for ≤3 cohesive deliverables; (b) `REQUIRED_DOCS` dict in the smoke test stays as-is for three docs; if a 4th ops doc is ever added, extract `OpsDocSpec` Pydantic model + a `@register_ops_doc` registry (rule-of-three threshold); (c) functional-core / imperative-shell discipline carries forward — `parse_section_body(...)` and the fixture's `assert_callable_runs(...)` helper are pure, the fixture module's top-level wiring is the imperative shell.

Three critics ran (coverage, test-quality, consistency); design-patterns ran a fourth pass. No Stage-3 research was needed — every finding had a local resolution traceable to S6-06's hardened state.

## Context

Two related deliverables in one story because they share an owner (Phase-4 → Phase-5 handoff) and a deadline (Step-7 merge gate):

1. **Phase-5 contract snapshot refresh.** `tests/integration/test_phase5_contract_snapshot.py` is the canonical surface that Phase 5 (Sandbox + Trust-Aware Gates) reads against. It pinned Phase 3's surface at the end of Phase 3; this story adds the **additive** Phase-4 entries: `FallbackTier.run(advisory, repo_ctx, recipe_selection, *, prior_attempts=[]) -> RecipeApplication`, `LlmInvocationGuard.running_total() -> BudgetSnapshot`, `FenceWrapper.fence(payload, source_kind) -> FencedSegment`, `SolvedExampleWriteCapability` mint signature, `cassettes.lock` line format. The snapshot test is **byte-equal** — if any of these signatures drift after Step 7 merges, the snapshot diff is the alarm.

2. **Operations runbooks.** Phase 4 introduces three new operator-facing concerns: Anthropic API key (`keyring`) management (S3-02), cassette refresh + steward rotation (S3-06), and embeddings model bootstrap + rebuild (S4-01 + S4-07). The arch §"What's next" calls these out as Phase-9 (Temporal worker) preconditions: the operator needs documented procedures for each before deployment. The three docs land under `docs/operations/`:
   - `docs/operations/secrets.md` — Anthropic key storage, rotation, refuse-to-start on missing key, no env-var fallback (ADR-0006).
   - `docs/operations/cassettes.md` — already started in S3-06; this story finalizes it with the steward rotation cadence, the `make refresh-cassettes` invocation, the CODEOWNERS approval flow, and the BLAKE3 lock refresh.
   - `docs/operations/embeddings.md` — `codegenie embeddings bootstrap`, `codegenie rag rebuild [--reembed]`, the `embeddings_model.lock` sha256 contract, refuse-to-start behavior on drift.

Plus a third deliverable mentioned in the High-level-impl: **publish `tests/fixtures/fallback_tier_callable.py`** as the contract Phase 6 (LangGraph runtime) reads when it lifts `FallbackTier.run` into a graph node — no code change to Phase 4 at that lift.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Stable contracts` — "Stable contracts (versioned by `tests/integration/test_phase5_contract_snapshot.py`): `FallbackTier.run` signature, `LeafLlm` Protocol, `PlanProposal` union members + field names, `LlmInvocationGuard.running_total()` return shape, `RetrievalOutcome` variants, `SolvedExampleWriteCapability` mint surface, `FenceWrapper.fence` signature, `cassettes.lock` line format."
  - `../phase-arch-design.md §What's next — handoff to Phase 5` — the seven hand-off interfaces Phase 5 consumes.
  - `../phase-arch-design.md §Configuration` — the operator-facing concerns this story documents.
  - `../phase-arch-design.md §Component 8 — Embedder` — `codegenie embeddings bootstrap` CLI; `embeddings_model.lock` discipline.
  - `../phase-arch-design.md §Component 12 — CassetteSanitizer` + discipline.
- **Phase ADRs:**
  - `../ADRs/0009-inline-auto-harvest-confidence-gate.md` — Consequences section: "`tests/fixtures/fallback_tier_callable.py` is published as the contract Phase 6 reads."
  - `../ADRs/0005-no-spki-pin-egress-defense-in-depth.md` — key in keyring; no env-var fallback (operator docs cite this).
  - `../ADRs/0006-egress-guard-no-production-loopback-carveout.md` — operator docs cross-link.
  - `../ADRs/0014-cassette-discipline-security-control.md` — cassette ops runbook anchor.
  - `../ADRs/0007-fastembed-onnx-over-sentence-transformers.md` — embeddings bootstrap ops anchor.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — Phase 5 hand-off contract framing.
- **Source design:**
  - `../final-design.md §"What's next"` — the seven Phase-5 hand-off items.
- **High-level impl:**
  - `../High-level-impl.md §Step 7 §Done criteria` — "`tests/integration/test_phase5_contract_snapshot.py` updated to capture additive interface lines from Phase 4 ...; `tests/fixtures/fallback_tier_callable.py` published as the contract Phase 6 reads ...; Documentation: `docs/operations/{secrets.md, cassettes.md, embeddings.md}` runbooks landed."
  - `../High-level-impl.md §"What's next — handoff to Phase 5"` — duplicated; the same seven items.
- **Existing code:**
  - `tests/integration/test_phase5_contract_snapshot.py` (Phase 3 S6-06) — the snapshot test scaffolding; read its inspection pattern carefully. **Add to it; do not rewrite.**
  - `tests/fixtures/fallback_tier_callable.py` — does not yet exist; this story creates it.
  - `src/codegenie/fallback/tier.py` (S6-01) — `FallbackTier.run` signature.
  - `src/codegenie/fallback/budget.py` (S2-05) — `LlmInvocationGuard.running_total`.
  - `src/codegenie/fallback/fence/wrapper.py` (S2-02) — `FenceWrapper.fence`.
  - `src/codegenie/rag/ingest.py` (S4-06) — `_phase4_local_capability_mint`.
  - `tests/cassettes/anthropic/cassettes.lock` (S3-05) — format.
  - `docs/operations/cassettes.md` (S3-06 stub) — extend to final form.

## Goal

Extend `tests/integration/test_phase5_contract_snapshot.py` to capture the five Phase-4 additive interface lines as byte-equal snapshot entries; publish `tests/fixtures/fallback_tier_callable.py` as the Phase-6-LangGraph-lift contract; land `docs/operations/{secrets,cassettes,embeddings}.md` as final runbooks each cross-linking their source ADRs.

## Acceptance criteria

- [ ] AC-1 — `tests/integration/test_phase5_contract_snapshot.py` (the Phase-3 S6-06 file; **must already exist and be GREEN**) is **extended in place** (not rewritten, not bifurcated into a sibling file) with five additive captures, each plumbed through S6-06's existing helpers `snapshot_symbol(...)` + the `@register_snapshot_kind`/`@register_delta_rule` registries — **no new helpers, no new classifier rules** (else explicit Phase-3 ADR-0001 amendment in the same PR):
  - `FallbackTier.run` — full signature including `prior_attempts: list[AttemptSummary] = []` keyword-only.
  - `FallbackTier.on_validated` — `(outcome: PlanOutcome, trust: TrustOutcome) -> None`.
  - `LlmInvocationGuard.running_total` — `() -> BudgetSnapshot`.
  - `FenceWrapper.fence` — `(payload: str, source_kind: SourceKind) -> FencedSegment`.
  - `SolvedExampleWriteCapability` — Pydantic model schema (frozen + extra=forbid + the mint factory signature `_phase4_local_capability_mint(workflow_id, chain_head) -> SolvedExampleWriteCapability`).
  - `cassettes.lock` line format — pinned via a golden file under `tests/golden/phase5-contract/` (mirroring the S6-06 layout); one example line + a frozen regex of the format. (validator: hardened — original AC allowed ad-hoc helper; now inherits S6-06's golden + registry discipline)
- [ ] AC-2 — The capture comparison is **golden-file based** (not inline `inspect.signature(...)` string assertion). Python-version drift is absorbed by the golden's stable serialization (the same approach S6-06 hardened). `pyproject.toml` carries an exact-minor Pydantic version pin (`pydantic == X.Y.*`); a Pydantic minor bump that changes the JSON-schema-emitter output is a contract event requiring an ADR amendment + golden refresh in the same PR. (validator: added — resolves the contradiction between v1 TDD plan and v1 Notes; pattern: Phase-3 S6-06 §AC-14)
- [ ] AC-3 — **Directive-message format**: a breaking delta in any of the five Phase-4 captures produces the diagnostic format established by S6-06 — failure message contains the literal `PHASE 5 CANNOT SHIP`, the symbol name, the before/after signature, and a reference to Phase-3 ADR-0001 §Consequences row 2. (validator: added — operator UX cannot regress silently; pattern: S6-06 directive-message AC)
- [ ] AC-4 — **Interim-name pinning**: the `_phase4_local_capability_mint` capture pins the **exact interim name**. Phase-5 supersession (ADR-0009) is a contract event: any rename or signature change at swap-in requires an ADR-0001 amendment + golden refresh in the same PR. The snapshot is the source of truth for the interim name; do NOT make the capture tolerant of renames. (validator: added — resolves ambiguity in Notes)
- [ ] AC-5 — **Breaking-delta meta-tests** (mirrors S6-06's six meta-test families). Add one assertion per Phase-4 capture proving a deliberate breaking delta is rejected by the existing classifier:
  - `prior_attempts` flipped from `= []` to required (no default) → rejected.
  - `LlmInvocationGuard.running_total` return annotation changed from `BudgetSnapshot` to `dict[str, int]` → rejected.
  - `FenceWrapper.fence` losing the `source_kind` kwarg → rejected.
  - `SolvedExampleWriteCapability` model_config flipping from `frozen=True` to `frozen=False` (or `extra="forbid"` → `extra="allow"`) → rejected.
  - `cassettes.lock` line-format regex tightened-or-loosened beyond byte-equality → rejected.
  - `FallbackTier.on_validated` losing its `trust` parameter → rejected.
  (validator: added — without these, the classifier could silently accept a breaking delta on a Phase-4 entry)
- [ ] AC-6 — **Determinism property test** extended to Phase-4 captures: running the snapshot 10× in the same process produces byte-identical output for each Phase-4 capture (catches non-stable dict ordering in `model_json_schema()`). (validator: added — inherits S6-06's discipline)
- [ ] AC-7 — **No-silent-rewrite fence** extended to Phase-4 captures: without `UPDATE_GOLDEN=1`, the test MUST NOT write to the golden path even for the additive Phase-4 entries. Asserted by patching `Path.write_text` on the golden path during the meta-test (same pattern as S6-06). (validator: added)
- [ ] AC-8 — The snapshot test's module docstring is updated to name Phase 4 as the source of the additive entries and cite every relevant Phase-4 ADR (0002, 0009, 0010, 0013, 0014).
- [ ] AC-9 — `tests/fixtures/fallback_tier_callable.py` exists and exports BOTH:
  - A `FallbackTierCallable` Protocol describing the awaited shape (`async def __call__(advisory, repo_ctx, recipe_selection, *, prior_attempts=[]) -> RecipeApplication`); decorated `@runtime_checkable`.
  - A module-level `fallback_tier_callable` instance such that `isinstance(fallback_tier_callable, FallbackTierCallable)` is True at import time.
  Phase 6 lifts the callable into a LangGraph node by `node(fn=fallback_tier_callable, ...)`. Module docstring documents the wiring + cites the Phase-6 lift path. (validator: hardened — v1 used unverifiable "structurally matches"; now pinned by Protocol)
- [ ] AC-10 — **Fixture behavior test**: `tests/fixtures/test_fallback_tier_callable_runs.py` invokes `fallback_tier_callable(...)` with a minimal valid input (well-formed `CveAdvisory`, `RepoContext`, `RecipeSelection`, `prior_attempts=[]`) under `asyncio.run`; asserts a non-None `RecipeApplication` is returned, the mocked `LeafLlm` was invoked at least once (`mock.assert_called()`), and the mocked `BudgetGuard.running_total()` was checked. (validator: added — v1 only tested `iscoroutinefunction`, which a pure-pass-through stub could pass)
- [ ] AC-11 — `docs/operations/secrets.md` exists with these **level-2 Markdown sections**, each followed by non-empty body content (≥3 lines or a fenced code block):
  - `## Anthropic key storage` — `keyring set codegenie anthropic_api_key` (one-liner; cite OS keychains for macOS Keychain / Linux SecretService).
  - `## Refuse-to-start behavior` — `AnthropicLeafAdapter.__init__` raises on missing key; **no env-var fallback** (cite Phase-4 **ADR-0005** primary; ADR-0006 secondary cross-link). Section must link the executable test that asserts this (`tests/integration/test_anthropic_leaf_refuse_on_missing_key.py` or successor named by S3-02).
  - `## Rotation cadence` — quarterly; cite the steward rotation in cassettes.md.
  - `## codegenie auth set` — the operator command (cross-link to S3-02's CLI; if S3-02 hasn't shipped a CLI yet, document `keyring set ...` as the primary path).
  (validator: hardened — sections must be observable headings + body, not arbitrary substrings; ADR-0005 fixed as the primary no-env-var citation)
- [ ] AC-12 — `docs/operations/cassettes.md` is **finalized** (S3-06 may have shipped a stub) with these level-2 sections, each followed by non-empty body content:
  - `## Refresh trigger matrix` — (a) nightly drift job flagging any cassette, (b) Anthropic SDK upgrade, (c) prompt template change in `plugins/.../skills/`; each row names the responsible owner.
  - `## make refresh-cassettes invocation` — full one-liner with `--i-understand-this-spends-tokens` + `CODEGENIE_LIVE_LLM=1`.
  - `## CODEOWNERS approval flow` — the cassette-steward role; rotation cadence; how a new steward is named.
  - `## BLAKE3 lock refresh` — `cassettes.lock` discipline; CI scanner naming; how to recompute on cassette change.
  - `## Sanitizer guarantees` — what `CassetteSanitizer` strips (cite ADR-0014).
- [ ] AC-13 — `docs/operations/embeddings.md` exists with these level-2 sections, each followed by non-empty body content:
  - `## codegenie embeddings bootstrap` — what it downloads (BGE-small-en-v1.5); content-addressed sha256; the `embeddings_model.lock` file's role.
  - `## codegenie rag rebuild` — when to run (model drift, corpus restore, sqlite corruption per arch edge case #13); document the `[--reembed]` flag.
  - `## Refuse-to-start on lock state` — **`FastembedEmbedder.__init__` raises on (a) lock drift AND (b) lock file missing entirely** (cite ADR-0007); operator runs `bootstrap` to recover. Section must link the executable test asserting this. (validator: hardened — v1 only addressed drift, not absence)
  - `## Cross-architecture float drift` — acknowledged; the two-threshold band absorbs it (cite ADR-0008).
- [ ] AC-14 — Each ops docs page has a `## See also` section cross-linking the relevant ADRs by file path (e.g., `../phases/04-vuln-llm-fallback-rag/ADRs/0005-...md`).
- [ ] AC-15 — All three docs are valid Markdown and pass `make docs` (mkdocs --strict). Run captured in `_attempts/`.
- [ ] AC-16 — `tests/integration/test_ops_docs_exist.py` smoke test enforces the section-and-body shape (not just substring presence). Implementation: a pure `parse_section_body(text: str, heading: str) -> str | None` helper returns the body for a level-2 heading; the test asserts (a) the heading exists exactly once, (b) `parse_section_body(...)` returns a non-empty body (≥3 lines or a fenced code block). The helper is functional-core (no I/O); the test is the imperative shell. (validator: hardened — v1 substring check was bypassable by putting the section name in a comment)
- [ ] AC-17 — Running the extended snapshot test under a deliberate violation (rename `running_total` → `total`, or remove `source_kind` kwarg, etc.) fails loud with a diagnostic in the `PHASE 5 CANNOT SHIP` format from AC-3 — named in the test's failure output, not just in a logfile.
- [ ] AC-18 — Extension-by-addition fence: the five Phase-4 captures are added by **new dispatch rows** (one `@register_snapshot_kind(...)` decorator per shape if a new shape is needed; none are needed today — all five are existing `pydantic_model` / `protocol_method` / `class_method` / `regex_lock` kinds covered by S6-06's five registered kinds). Acceptance test asserts the registry has the same number of registered kinds before and after this story (no kernel edits). (validator: added — extension-by-addition AC; pattern: registry / Open/Closed; CLAUDE.md "Extension by addition")
- [ ] AC-19 — `make check` clean.
- [ ] AC-20 — TDD red test exists, committed, green.

## Implementation outline

1. **Pre-flight (Read before you write — Rule 8):** open `tests/integration/test_phase5_contract_snapshot.py` (Phase 3 S6-06) and the `tests/golden/phase5-contract/` directory. Confirm the helpers (`snapshot_symbol`, `diff_snapshots`, `format_breaking_delta_message`), the registries (`@register_snapshot_kind`, `@register_delta_rule`), the regen script (`scripts/regen_probe_contract_snapshot.py`), and the directive-message format are GREEN. If any of these are absent, mark this story `BLOCKED-PARTIAL` and stop.
2. **Extend the snapshot test in place** (not a sibling file — AC-1). Add one capture row per Phase-4 entry. Each row calls `snapshot_symbol(...)` from S6-06; no new helpers.
3. **Add the six breaking-delta meta-tests** (AC-5). One per Phase-4 capture; each constructs a deliberately broken double and asserts the existing classifier rejects it with the `PHASE 5 CANNOT SHIP` directive.
4. **Add the determinism + no-silent-rewrite + extension-by-addition fences** (AC-6, AC-7, AC-18). These mirror S6-06's hardened fences — copy the pattern, don't reinvent.
5. **Regen the golden** with `UPDATE_GOLDEN=1 python scripts/regen_probe_contract_snapshot.py` (or the S6-06-named equivalent). Commit the golden alongside the test edits in the same PR.
6. **Build `tests/fixtures/fallback_tier_callable.py`** with:
   - `FallbackTierCallable` Protocol (`@runtime_checkable`) describing the awaited shape.
   - The wired `fallback_tier_callable` instance built from `FallbackTier` + observable mock collaborators (`MockLeafLlm`, `MockBudgetGuard`, etc. — each records its invocations on the instance).
   - Module docstring documenting the Phase-6 lift contract.
7. **Build the behavior test** `tests/fixtures/test_fallback_tier_callable_runs.py` (AC-10) — runs the callable end-to-end, asserts mocks were exercised.
8. **Write `docs/operations/secrets.md`** with the four level-2 sections (AC-11); ADR-0005 primary cite, ADR-0006 secondary.
9. **Finalize `docs/operations/cassettes.md`** with the five level-2 sections (AC-12). If the S3-06 stub exists, extend; else write from scratch.
10. **Write `docs/operations/embeddings.md`** with the four level-2 sections (AC-13); include the missing-lock-file behavior alongside drift.
11. **Add `## See also` sections** to all three ops docs with ADR file-path cross-links (AC-14).
12. **Add `tests/integration/test_ops_docs_exist.py`** with the `parse_section_body` pure helper + the parametrized + the `## See also` + the pure-helper unit tests (AC-16).
13. **Add an `Operations` section** to `docs/index.md` / `mkdocs.yml` nav.
14. **Run `make docs` and `make check`** to confirm everything is green (AC-15, AC-19).

## TDD plan — red / green / refactor

> **Pre-flight check (Read before you write — Rule 8):** open `tests/integration/test_phase5_contract_snapshot.py` (Phase-3 S6-06 deliverable) and confirm GREEN. If it does not yet exist on disk, this story is **blocked** until S6-06 ships its GREEN drop (`snapshot_symbol`, `diff_snapshots`, `format_breaking_delta_message` helpers; `@register_snapshot_kind` + `@register_delta_rule` registries; the `tests/golden/phase5-contract/` golden directory; the regen script `scripts/regen_probe_contract_snapshot.py`). Record the dep state in the attempt log before proceeding.

### Red — write the failing tests first

Two test files; both **extend** existing files (do not create parallel sibling files):

1. **`tests/integration/test_phase5_contract_snapshot.py`** (extend in place; do NOT create a `_phase4_additions.py` sibling):
   - For each of the five Phase-4 captures (`FallbackTier.run`, `FallbackTier.on_validated`, `LlmInvocationGuard.running_total`, `FenceWrapper.fence`, `SolvedExampleWriteCapability` + `_phase4_local_capability_mint`, `cassettes.lock` line-format regex), add one row that calls `snapshot_symbol(name, obj)` and asserts the result equals the corresponding entry in `tests/golden/phase5-contract/phase4.yaml` (or whatever file name S6-06's regen script produces — confirm at execution time).
   - Add six **breaking-delta meta-tests** (AC-5): each constructs a deliberately-broken copy of the symbol (e.g., `class _BrokenFallbackTier: async def run(self, advisory, repo_ctx, recipe_selection, prior_attempts): ...` — `prior_attempts` made required) and asserts `diff_snapshots(...)` flags it via `@register_delta_rule(...)`'s output with the `PHASE 5 CANNOT SHIP` directive (AC-3).
   - Add the **determinism property test** (AC-6): call `snapshot_symbol(FallbackTier.run)` 10× in a tight loop; assert all 10 outputs are byte-identical.
   - Add the **no-silent-rewrite fence** test (AC-7): monkeypatch `Path.write_text` on the golden path; run the test without `UPDATE_GOLDEN=1`; assert `write_text` was never invoked.
   - Add the **extension-by-addition fence** test (AC-18): assert `len(SNAPSHOT_KIND_REGISTRY)` and `len(DELTA_RULE_REGISTRY)` are unchanged between S6-06's GREEN state and this story's HEAD.

2. **`tests/integration/test_ops_docs_exist.py`** (new file; functional-core helper + imperative-shell test):
   ```python
   from __future__ import annotations
   from pathlib import Path
   import pytest

   def parse_section_body(text: str, heading: str) -> str | None:
       """Pure: return the body following a level-2 `## heading` until the next `## ` or EOF, or None if absent."""
       marker = f"\n## {heading}\n"
       if marker not in text:
           return None
       after = text.split(marker, 1)[1]
       end = after.find("\n## ")
       return after[:end] if end != -1 else after

   REQUIRED_DOCS: dict[str, list[str]] = {
       "docs/operations/secrets.md":     ["Anthropic key storage", "Refuse-to-start behavior", "Rotation cadence", "codegenie auth set"],
       "docs/operations/cassettes.md":   ["Refresh trigger matrix", "make refresh-cassettes invocation", "CODEOWNERS approval flow", "BLAKE3 lock refresh", "Sanitizer guarantees"],
       "docs/operations/embeddings.md":  ["codegenie embeddings bootstrap", "codegenie rag rebuild", "Refuse-to-start on lock state", "Cross-architecture float drift"],
   }

   @pytest.mark.parametrize("path,sections", list(REQUIRED_DOCS.items()))
   def test_ops_doc_has_sections_with_body(path: str, sections: list[str]) -> None:
       p = Path(path)
       assert p.is_file(), f"missing ops doc: {p}"
       text = p.read_text()
       for s in sections:
           body = parse_section_body(text, s)
           assert body is not None, f"{p} missing level-2 heading '## {s}'"
           # body must be ≥3 non-blank lines OR contain a fenced code block
           non_blank = [ln for ln in body.splitlines() if ln.strip()]
           has_fence = "```" in body
           assert len(non_blank) >= 3 or has_fence, f"{p} section '{s}' has empty/trivial body"

   def test_each_ops_doc_has_see_also_section() -> None:
       for path in REQUIRED_DOCS:
           assert parse_section_body(Path(path).read_text(), "See also") is not None, \
               f"{path} missing '## See also' cross-link section"

   # Pure-helper test (functional-core discipline)
   def test_parse_section_body_handles_eof() -> None:
       assert parse_section_body("\n## A\nline1\nline2\nline3\n", "A").strip() == "line1\nline2\nline3"

   def test_parse_section_body_handles_next_section() -> None:
       assert parse_section_body("\n## A\nbody-a\n## B\nbody-b\n", "A").strip() == "body-a"

   def test_parse_section_body_returns_none_when_missing() -> None:
       assert parse_section_body("# top\n## Other\nx\n", "Missing") is None
   ```

3. **`tests/fixtures/test_fallback_tier_callable_runs.py`** (AC-10 — behavior test for the fixture; lives next to the fixture file):
   ```python
   import asyncio
   import inspect
   from typing import runtime_checkable
   from tests.fixtures.fallback_tier_callable import FallbackTierCallable, fallback_tier_callable

   def test_fixture_satisfies_protocol() -> None:
       assert isinstance(fallback_tier_callable, FallbackTierCallable)
       assert inspect.iscoroutinefunction(fallback_tier_callable.__call__) or asyncio.iscoroutinefunction(fallback_tier_callable)

   def test_fixture_runs_end_to_end_with_minimal_input() -> None:
       # Build minimal valid CveAdvisory / RepoContext / RecipeSelection fixtures
       advisory, repo_ctx, recipe_selection = _build_minimal_inputs()
       result = asyncio.run(fallback_tier_callable(advisory, repo_ctx, recipe_selection, prior_attempts=[]))
       assert result is not None
       # The fixture's mocked LeafLlm + BudgetGuard must have been exercised
       assert fallback_tier_callable.mock_leaf_llm.call_count >= 1
       assert fallback_tier_callable.mock_budget_guard.running_total_calls >= 1
   ```

Run the three test files; every new assertion must fail before any new artifact lands.

### Green — make it pass

1. Extend `tests/integration/test_phase5_contract_snapshot.py` (in place) with the five additive captures + six meta-tests + determinism + no-silent-rewrite + extension-by-addition fences. Consume S6-06's `snapshot_symbol(...)` / `diff_snapshots(...)` / `format_breaking_delta_message(...)` helpers; do NOT invent a parallel `_sig()` helper.
2. Run `python scripts/regen_probe_contract_snapshot.py --phase 4` (or the S6-06-named equivalent) under `UPDATE_GOLDEN=1` to materialize the Phase-4 golden entries; commit the golden alongside.
3. Build `tests/fixtures/fallback_tier_callable.py` with `FallbackTierCallable` Protocol + the wired instance + observable mocks.
4. Write the three ops docs (secrets / cassettes-finalize / embeddings).
5. Add the `## See also` section to each doc with ADR file-path cross-links.
6. Run `make docs` to confirm mkdocs --strict accepts the new pages.
7. Iterate until `pytest -q tests/integration/test_phase5_contract_snapshot.py tests/integration/test_ops_docs_exist.py tests/fixtures/test_fallback_tier_callable_runs.py` is GREEN and `make check` is clean.

### Refactor — clean up

- Confirm zero new helpers were introduced in the snapshot test (consume S6-06's helpers only); zero new classifier rules (consume S6-06's `@register_delta_rule` outputs); zero changes to `len(SNAPSHOT_KIND_REGISTRY)` / `len(DELTA_RULE_REGISTRY)` — these are AC-18's invariants.
- Cross-link each ops doc from `docs/index.md` (the mkdocs nav) — add an "Operations" section if it doesn't exist.
- Confirm `make docs` clean.
- If a Pydantic version bump is required mid-implementation, treat it as a contract event: amend Phase-3 ADR-0001 + refresh the golden in the same PR (AC-2).

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase5_contract_snapshot.py` | Extend in place with Phase-4 additive captures + meta-tests + determinism + no-silent-rewrite + extension-by-addition fences. **Do NOT create a `_phase4_additions.py` sibling** (AC-1). |
| `tests/golden/phase5-contract/phase4.yaml` (name TBD per S6-06) | Phase-4 captures' golden entries. Materialized by regen script under `UPDATE_GOLDEN=1`. |
| `tests/integration/test_ops_docs_exist.py` | Smoke test enforcing level-2 heading + non-empty body shape (not substring presence). Exports the pure `parse_section_body` helper. |
| `tests/fixtures/fallback_tier_callable.py` | Phase-6 LangGraph lift contract. Exports `FallbackTierCallable` Protocol + the wired `fallback_tier_callable` instance with observable mocks. |
| `tests/fixtures/test_fallback_tier_callable_runs.py` | Behavior test (AC-10) — runs the callable end-to-end with minimal valid input. |
| `docs/operations/secrets.md` | Anthropic key + keyring + refuse-to-start runbook. ADR-0005 primary citation. |
| `docs/operations/cassettes.md` | Cassette refresh + CODEOWNERS + BLAKE3 runbook (finalize the S3-06 stub). |
| `docs/operations/embeddings.md` | Bootstrap + rebuild + refuse-on-(drift OR missing-lock) runbook. |
| `docs/index.md` (or `mkdocs.yml` nav) | Add "Operations" section. |
| `scripts/regen_probe_contract_snapshot.py` (if name differs in S6-06) | If a CLI flag is needed to scope to Phase-4 entries, extend; do not invent a parallel regen script. |

## Out of scope

- Phase 6 LangGraph lift itself (Phase 6 owns it; this story only publishes the contract fixture).
- Adversarial corpus (S7-09).
- E2E tests (S7-06 / S7-07).
- Cassette steward initial assignment (S3-06); this story documents the rotation cadence only.

## Notes for the implementer

- **Inherit, don't invent.** The Phase-3 S6-06 hardening built the substrate: golden-file capture format, `snapshot_symbol`/`diff_snapshots`/`format_breaking_delta_message` pure helpers, `@register_snapshot_kind` + `@register_delta_rule` registries with six breaking-delta families, determinism property, no-silent-rewrite fence, directive-message format with `PHASE 5 CANNOT SHIP`, Pydantic version pin, `should_update_golden(env)` factored out for testability. Consume all of them. AC-18 explicitly forbids new kernel rows.
- **Cross-version signature drift is handled by the golden, not by the test.** A Python-version bump that changes `inspect.signature`'s string formatting is a contract event: regen the golden under `UPDATE_GOLDEN=1`, commit the diff alongside an ADR-0001 amendment, and call it out in the PR. **Do not** write Python-version-conditional assertions in the test.
- **Interim-name pinning is intentional.** The `_phase4_local_capability_mint` capture pins the exact name; Phase 5's supersession (ADR-0009) requires an ADR-0001 amendment + golden refresh. The snapshot's job is to make the rename a contract event, not to tolerate it.
- **The fixture has three deliverables in one file**: the `FallbackTierCallable` Protocol, the wired callable instance, and the observable mocks. The mocks must record their invocations so the behavior test (AC-10) can assert end-to-end exercise — a pure-pass-through impl that returns a hardcoded `RecipeApplication` without invoking the mocked `LeafLlm` is a wrong implementation and AC-10 must reject it.
- **Refuse-to-start cross-links must point to executable tests**, not free-floating prose. `secrets.md`'s and `embeddings.md`'s refuse-to-start sections cite (and link to) the integration test that asserts the behavior — if S3-02 / S4-01 haven't shipped that test yet, write a `pytest.mark.skip(reason="awaiting S3-02 / S4-01 GREEN")` shell so the cross-link's target exists and the missing implementation is visible.
- **`docs/operations/` may not exist yet.** Create the directory; add an `## Operations` section to `docs/index.md` (or `mkdocs.yml` nav) so mkdocs --strict picks the pages up.
- **The three ops docs are operator-readable plain language**, not engineer-internal. Cross-link ADRs but don't quote them verbatim — the docs are *how to operate*, not *why the design is this shape*.
- **`make docs --strict`** will fail on broken links and missing referenced files — run early and fix iteratively.
- **`_phase4_local_capability_mint` will be renamed by Phase 5** (ADR-0009). Land a TODO comment in `src/codegenie/rag/ingest.py`'s module docstring pointing to ADR-0009 + the snapshot test as the rename's contract gate.
- **The three-deliverables bundling is intentional.** Snapshot + fixture + ops docs share the Step-7 deadline and the Phase-4 → Phase-5 handoff owner. Single-responsibility purists could split this into S7-10a/b/c, but Rule 2 (Simplicity First) says three cohesive deliverables that ship together is better than three siblings with synchronization rules. Note: if a fourth ops doc is ever added (e.g., `docs/operations/sandbox.md` in Phase 5), the `REQUIRED_DOCS` dict crosses the rule-of-three threshold — extract an `OpsDocSpec` Pydantic model + `@register_ops_doc(...)` registry at that point. Until then, the dict is fine (CLAUDE.md "Extension by addition" + Rule 2).
- **Functional core / imperative shell**: `parse_section_body(...)` is pure (no I/O); the test functions are the imperative shell. `snapshot_symbol`, `diff_snapshots`, `format_breaking_delta_message` (S6-06) are also pure. Keep it that way — AST-walk fences from S6-06 will catch a regression.
- **Scope hygiene**: this story does NOT add `LeafLlm` Protocol or `RetrievalOutcome` to the snapshot — they were already captured by Phase 3's infrastructure consuming their imports. If implementation reveals they're missing (Global Rule 12 — fail loud), add them and note in the attempt log; do not add them to the primary AC list silently.
- **Read the dep state first** (Pre-flight check in TDD plan). If S6-06 is HARDENED-not-GREEN at execution time, mark this story `BLOCKED-PARTIAL` in the attempt log and surface to the human before proceeding — extending a test file that doesn't exist yet is the worst kind of phantom work.
