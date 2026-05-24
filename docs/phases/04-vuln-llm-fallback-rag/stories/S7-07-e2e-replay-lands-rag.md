# Story S7-07 — E2E replay-lands-RAG exit criterion #2

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** HARDENED
**Effort:** M
**Depends on:** S7-05 (`express-rerun/` fixture with pre-populated `.codegenie/rag/records/`; AC-11 pins `embedding_model == codegenie.rag.embeddings.MODEL_DIGEST`), S6-03 (HARDENED — `on_validated` harvest hook with caller-side idempotence pre-check; closed-set `HarvestSkipped.reason` literals `{"already_harvested", "low_confidence", "trust_failed", "outcome_not_harvestable"}`; `TrustOutcome.confidence: Literal["high", "degraded"]`), S7-06 (HARDENED — sibling E2E test ships `tests/integration/_phase4_e2e_helpers.py` as the kernel; this story **extends by addition** without editing existing helpers), S5-01 HARDENED (event-class names `RagHitEvent`, `RagDegradedEvent`, `RagMissEvent`, `RagCandidateSelectedEvent` in `src/codegenie/plugins/events.py`), S1-04 HARDENED (`RetrievalOutcome` discriminator `kind: Literal["hit","miss","degraded"]`; `RagHit(few_shot: SolvedExample, score: Similarity)` — `SolvedExample.id: SolvedExampleId`)
**ADRs honored:** ADR-04-0009 (inline harvest — the seed comes from a prior validated run; caller-side dedup emits `HarvestSkipped(reason="already_harvested")`), ADR-04-0008 (two-threshold band — `RagHit` only above `high_floor` configured in `plugin.yaml`, not in code), ADR-04-0017 (`AttemptAnchor` family events including `LlmCostAccrued` live in the **spanning** stream, not workflow-internal), production-ADR-0034 (event sourcing for `LlmCostAccrued`)

## Validation notes (validator-added 2026-05-24)

The following corrections and reshapes were applied based on critic findings; each maps to its source by tag. Mirrors the patterns established by sibling S7-06's HARDENED validation report (the helper module, typed-event discipline, spanning-stream cost capture, dispatch-order assertion, and Open/Closed-at-the-file-boundary extension contract all come from S7-06's lineage).

1. **Event-class name corrected.** Original story used `RagHitClassified`; verified non-existent. S5-01 HARDENED §AC-14 ships `RagHitEvent` / `RagDegradedEvent` / `RagMissEvent` / `RagCandidateSelectedEvent` in `src/codegenie/plugins/events.py`, with `event_type:` snake_case discriminator literals. (CO-2 / CN-1.)
2. **Event payload shape corrected.** Original `RagHitClassified.matched_record.solved_example_id` does not exist. S5-01 line 220 emits `RagHitEvent(record_id=record.id, score=score, ...)`; the seed identity is `record_id` (a `SolvedExampleId`), and the matched record is the same `SolvedExample` whose `.id` was read from the fixture YAML. (CO-3 / CN-2.)
3. **`HarvestSkipped.reason` literal corrected to closed-set value.** Original `reason="already_present"` is not in S6-03's closed `Literal[...]`. S6-03 AC-7 / AC-13 ship `{"already_harvested", "low_confidence", "trust_failed", "outcome_not_harvestable"}`. The seeded second run hits the caller-side idempotence pre-check (S6-03 AC-7 step 3) and must emit `HarvestSkipped(reason="already_harvested")`. (CO-6 / CN-3.)
4. **Harvest behavior collapsed from parallel-implementation alternatives to single contract.** Original goal item (h) presented two alternatives ("if S6-03 dedups vs if it doesn't"); per Global Rule 7, surface conflict, don't average. S6-03 HARDENED ships dedup; the assertion is `harvest_skipped(reason="already_harvested")` — no fallback branch. (DP-4.)
5. **Cost-accrual stream pinned to spanning.** Original test reads only `.codegenie/events/workflow-internal/`; per ADR-04-0017 (and S7-06 CN-H-1) `LlmCostAccrued` lives in `.codegenie/events/spanning/append.jsonl.zst`. Cost assertion would silently never find the event in workflow-internal. (CO-7 / CN-4.)
6. **`TrustOutcome.confidence` literal pinned to shipped two-value set.** S6-03 HARDENED corrected `Literal["high", "medium", "low"]` doc drift to the actual `Literal["high", "degraded"]` shipped in `src/codegenie/transforms/outcomes.py:403`. AC asserts `"high"` (the harvest-gate-passing value); `"degraded"` is the only non-pass alternative the seed contract admits. (CO-5.)
7. **Typed-event parsing throughout — no `dict.get` shuffling.** Same as S7-06 TQ-H-2 and CLAUDE.md "no untyped `dict` shuffling" load-bearing commitment. Helpers parse each line into `pydantic.TypeAdapter(WorkflowInternalEvent | WorkflowSpanningEvent).validate_python(...)` typed variants; per-AC assertions use `isinstance(evt, EventClass)` / `match evt` arms. (TQ-1 / DP-1.)
8. **Helper module extended by addition, not edited.** S7-06 HARDENED AC-18 shipped `tests/integration/_phase4_e2e_helpers.py` with kernel helpers `_parse_typed_events`, `_load_high_floor`, `_load_cve`, `_load_repo_ctx`, `_mask_nondeterministic_fields`, `_assert_cassette_lock_matches`. S7-07 extends the module by appending: `_capture_first_run_baseline_dollars(tmp_path: Path, baseline_cassette: Path, baseline_lock: Path, fixture: Path) -> tuple[float, int]`, `_seed_record_id(fixture: Path) -> SolvedExampleId`, `_assert_no_operator_harvest_invocation(test_fn: Callable[..., Any]) -> None`. **Adding S7-09's adversarial E2E test must require zero edits to existing helper-module bodies** (Open/Closed at the file boundary; CO-11 / DP-2 / DP-6). New AC pins this. (Mirrors S7-06 AC-18 + DP-H-4.)
9. **`high_floor` sourced from `plugin.yaml`, not duplicated.** Same as S7-06 CO-H-1 / DP-H-2. Reads via `_load_high_floor(PLUGIN_YAML)` helper. (CO-1 / CN-6 / DP-3.)
10. **Cassette/lock BLAKE3 integrity check inside the test.** Same as S7-06 TQ-H-3. `_assert_cassette_lock_matches(CASSETTE, LOCKFILE)` is called before any CLI invocation; also called for the baseline cassette before the baseline replay. Fail-loud with `make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1` pointer. (CO-13.)
11. **Per-platform fail-loud on missing jail binary.** Same as S7-06 CN-H-3 / AC-16. Linux → `bwrap`; macOS → `sandbox-exec`; raises `pytest.fail` with platform-specific message; `pytest.skip` is forbidden (Rule 12). (CN-5.)
12. **Dispatch-order assertion across full event chain.** Original asserted only `idx_rag < idx_leaf`; a regression that emits `solved_example_harvested` before `trust_outcome_emitted` or fires `leaf_invoked` before `provenance_classified` would pass silently. New AC pins canonical order by index across both streams (workflow-internal for the deterministic dispatch chain; spanning for `llm_cost_accrued`). Mirrors S7-06 AC-13. (CO-9.)
13. **Event-absence companions.** No `RagDegradedEvent` / `RagMissEvent` fires on the happy path (the seed is by construction a high-confidence hit). No `solved_example_harvested` event fires on the rerun (dedup pre-check fires `harvest_skipped` instead). No `degraded` `trust_outcome_emitted`. Asserted as the negative companion to AC-3 / AC-9 / AC-10 (mirrors S7-06 CO-H-3). (CO-8 / CO-10 / CN-9.)
14. **Determinism guard split into a separate test function.** Mirrors S7-06 AC-14 / TQ-H-4. `test_phase4_e2e_replay_lands_rag_determinism` runs the workflow twice against fresh `tmp_path` copies and asserts byte-equality after `_mask_nondeterministic_fields`. (CO-14.)
15. **`system[2]` presence asserted by single canonical shape, not parallel alternatives.** Per Rule 7, picked one: the `LeafInvoked` event's `system_blocks_count` field is the canonical shape S3-02 emits (Phase-4-internal observability event). If S3-02 ships only `system_blocks_metadata: tuple[str, ...]` and not `system_blocks_count`, surface as a Rule-7 blocker at executor time — do NOT silently fall back to cassette-body inspection. The cassette-body-inspection alternative is recorded in Notes for the implementer as the documented Rule-7-resolved fallback path (one ADR amendment away). (CO-15 / DP-5.)
16. **Seeded record loaded via typed `SolvedExample.from_yaml`.** Original `_read_seeded_record_id` used `yaml.safe_load` to bare dict. S1-04 / S4-04 ship `SolvedExample.from_yaml` as the canonical entry. (TQ-2 / CN-8.)
17. **First-run baseline cost captured as typed `LlmCostAccrued` event, not just `> 0`.** Original `assert first_run_dollars > 0` is a tautology (any cassette response has cost). Strengthened to capture the typed event from the baseline cassette's spanning stream and assert the dollars value is positive AND matches the schema (non-zero `tokens_total`). (TQ-3.)
18. **No-operator-harvest static guard extended.** Original asserted only string-substring absence; a regression introducing `subprocess.run(["python", "-m", "codegenie", "rag", "harvest", ...])` or importing `rag_harvest_cli` under a different name would evade. Extended via `_assert_no_operator_harvest_invocation` helper that scans for: (a) any string containing the substring `"rag harvest"` or `"rag_harvest"`; (b) any `from codegenie.cli...rag_harvest` import in `inspect.getsourcefile`'s module-level imports; (c) any `subprocess.*` call whose first arg references "codegenie". (TQ-4 / DP-8.)
19. **`Final[Path]` typing on module-level constants.** Same as S7-06's mypy-hygiene precedent. (DP-7.)

## Context

This is **roadmap exit criterion #2**: "re-running the same case hits RAG, not LLM, and produces an equivalent fix at lower cost." The test runs the express CVE workflow *twice* against the `express-rerun/` fixture (S7-05 ships it pre-seeded with one `SolvedExample` covering the same CVE), with **no operator step between runs** — and asserts on the second run that:

- A `RagHitEvent` was observed in the workflow-internal event stream (the retriever scored ≥ `high_floor` against the seeded record; `high_floor` is read from `plugin.yaml` per ADR-04-0008, NOT duplicated as `0.85` in the test).
- A `RagCandidateSelectedEvent` was observed for that record (S5-01 AC-14 — pins the selected `FencedSegment` reaches prompt assembly).
- The leaf LLM was still called, but the call's `system[2]` block carried the few-shot record. The Phase-4 contract is intra-workflow cache only — `cache_creation > 0` on system[2] first time and `cache_read > 0` on subsequent intra-batch runs.
- The second-run `LlmCostAccrued.dollars` (from the **spanning** stream, per ADR-04-0017 — NOT workflow-internal) is strictly less than first-run × 0.5.
- The seeded record is already present in the store, so S6-03's caller-side idempotence pre-check fires `HarvestSkipped(reason="already_harvested")` (NOT `"already_present"` — that literal is not in S6-03's closed reason set).
- No operator-invoked harvest CLI call occurs between runs (static guard via `inspect.getsource` of the test function, extended to scan for subprocess invocations and CLI imports — not just substring matches).

The arch is firm: "no operator step between runs" is the production-behavior guarantee that distinguishes this from a test-scaffolding shortcut. The seed in S7-05's `express-rerun/` fixture represents what S7-06's run *would have harvested* (i.e., the fixture mirrors S7-06's post-run state); this story tests the **second** run only — the first run is the seed.

Three non-obvious points:

1. **The fixture's seed must match the embedder's `model_digest()`**. S7-05 AC-11 pins `seed_record.embedding_model == codegenie.rag.embeddings.MODEL_DIGEST`. If S5-03's model-mismatch exclusion drops the record, the retriever returns bare `RagMiss(reason="all_candidates_model_mismatch")` and the test silently fails the wrong way (degenerates to S7-06's path). The S7-05 fixture acceptance criteria pin this; this story trusts the fixture and asserts at test-setup time that the seed loads via typed `SolvedExample.from_yaml` (S4-04) without raising.
2. **"Lower cost" is asserted via the spanning-stream `llm_cost_accrued` event**, not by re-running S7-06 inside this test. The constant against which the second-run cost is compared is captured during a baseline replay of S7-06's cassette via the `_capture_first_run_baseline_dollars` helper (option (a) — fully hermetic). Both invocations are cassette-replayed; total wall-clock ≤ 60s.
3. **`RagHitEvent` must appear *before* `LeafInvoked`** — order matters. The retriever fires first; the leaf call uses the hit as few-shot. The dispatch-order AC pins the full chain by index (workflow-internal stream is single-threaded; the indices are the spec, not the timestamps).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals — G1` (line 18) — "second run on the same case hits RAG and shapes a cheaper LLM call. Asserted by `tests/integration/test_phase4_e2e_replay_lands_rag.py` (no operator step between runs)."
  - `../phase-arch-design.md §Scenario 1` (lines 341–373) — full sequence diagram of the RAG-hit-reshapes-LLM path. Each numbered arrow is an assertable event order: `Tier→Prov` → `Prov→Retr` → `Retr→Emb→Store→Retr→Tier RagHit` → `Tier→Bud precharge` → `Tier→Leaf invoke` → `Tier→Bud reconcile` → `Tier→CLI`.
  - `../phase-arch-design.md §Prompt template structure` — "Three cached system blocks per call: `system[0]` skill ... `system[1]` instruction template ... `system[2]` per-workflow RAG few-shot."
  - `../phase-arch-design.md §Component 9 — SolvedExampleRetriever` and §Component 11 — `confidence.py` (two-threshold band).
  - `../phase-arch-design.md §Harness engineering` (line 825) — `INFO` audit-anchored events include `RagHit/Miss/Degraded`, `LeafInvoked`, `BudgetReconciled`, `SolvedExampleHarvested`. The actual event-class names per `src/codegenie/plugins/events.py` (verified against S5-01 / S6-03) are `RagHitEvent`, `RagDegradedEvent`, `RagMissEvent`, `RagCandidateSelectedEvent`, `LeafInvoked`/`LeafReturned`, `PlanOutcomeEmitted`, `TrustOutcomeEmitted`, `SolvedExampleHarvested`, `HarvestSkipped`, `LlmCostAccrued`.
- **Phase ADRs:**
  - `../ADRs/0009-inline-auto-harvest-confidence-gate.md` — "The integration test `tests/integration/test_phase4_e2e_replay_lands_rag.py` runs the same CVE case twice with *no operator step between runs* — the second run must hit RAG with the inline-harvested record."
  - `../ADRs/0008-two-threshold-calibration-band.md` — `RagHit` requires score ≥ `high_floor` (config; default `0.85`).
  - `../ADRs/0017-attempt-anchor-event-schema.md` — the `AttemptAnchor` family (including `LlmCostAccrued`) lives in the **spanning** stream, not workflow-internal.
- **Source design:**
  - `../final-design.md §Component 9` and §"Goal: Inline auto-harvest gate."
- **High-level impl:**
  - `../High-level-impl.md §Step 7` — "Roadmap exit criterion #2 ... second run on same case hits RAG (`rag_hit_event` present in workflow-internal stream); leaf call shaped by few-shot; `llm_cost_accrued` (spanning) second-run delta < first-run × 0.5; no operator step between runs."
- **Sibling stories (HARDENED; the source of every convention this story mirrors):**
  - **`S7-06-e2e-breaking-change.md` (HARDENED)** — ships `tests/integration/_phase4_e2e_helpers.py` with the kernel helpers `_parse_typed_events`, `_load_high_floor`, `_load_cve`, `_load_repo_ctx`, `_mask_nondeterministic_fields`, `_assert_cassette_lock_matches`. This story extends the module by addition only.
  - **`S6-03-on-validated-harvest-hook.md` (HARDENED)** — `HarvestSkipped` event registered with `event_type: Literal["harvest_skipped"]` and `reason: Literal["already_harvested","low_confidence","trust_failed","outcome_not_harvestable"]`. `TrustOutcome.confidence: Literal["high","degraded"]`.
  - **`S5-01-retriever-query-composition.md` (HARDENED)** — `RagHitEvent`, `RagDegradedEvent`, `RagMissEvent`, `RagCandidateSelectedEvent`, `QueryBuiltEvent`, etc., live in `src/codegenie/plugins/events.py`. `RagHitEvent` carries `record_id` (`SolvedExampleId`) and `score`.
  - **`S1-04-rag-pydantic-models.md` (HARDENED)** — `RetrievalOutcome` discriminator `kind: Literal["hit","miss","degraded"]`; `RagHit(few_shot: SolvedExample, score: Similarity)`; **bare** `RagMiss`; `SolvedExample.id: SolvedExampleId`.
  - **`S7-05-phase4-fixture-portfolio.md` (HARDENED)** — AC-11 pins `express-rerun/.codegenie/rag/records/<id>.yaml` `embedding_model == codegenie.rag.embeddings.MODEL_DIGEST`.
- **Existing code:**
  - `tests/fixtures/repos/express-rerun/` (S7-05) — the fixture with `.codegenie/rag/records/<id>.yaml` already pre-populated.
  - `tests/integration/test_phase4_e2e_breaking_change.py` (S7-06) — sibling test; reuses `_phase4_e2e_helpers.py`.
  - `tests/integration/_phase4_e2e_helpers.py` (S7-06 HARDENED AC-18) — the kernel.
  - `src/codegenie/rag/retriever.py` (S5-01) — emits `RagHitEvent | RagDegradedEvent | RagMissEvent`.
  - `src/codegenie/fallback/tier.py` (S6-01 / S6-03) — RAG-hit-shapes-LLM path; `on_validated` hook with dedup.
  - `src/codegenie/plugins/events.py` — the canonical `WorkflowInternalEvent` / `WorkflowSpanningEvent` discriminated unions.
  - `src/codegenie/transforms/outcomes.py:403` — `TrustOutcome.confidence: Literal["high","degraded"]`.
  - `plugins/vulnerability-remediation--node--npm/plugin.yaml` — `high_floor` and `degraded_floor`.

## Goal

Land `tests/integration/test_phase4_e2e_replay_lands_rag.py` as a cassette-replayed integration test that runs `codegenie remediate ./tests/fixtures/repos/express-rerun --cve CVE-2026-1234` (after first replaying the S7-06 baseline cassette in the same test to capture `first_run_dollars`) and asserts the canonical RAG-hit-shapes-LLM dispatch fires end-to-end, the harvest dedup pre-check skips writing, and the second-run cost is strictly less than half of the first-run baseline — all under cassette replay, hermetically. The test extends `_phase4_e2e_helpers.py` **by addition only** (zero edits to S7-06's kernel helpers); adding S7-09's adversarial E2E next must continue that pattern.

## Acceptance criteria

- [ ] **AC-1 — File location + pytest collection.** `tests/integration/test_phase4_e2e_replay_lands_rag.py` exists, is collected by pytest, marked `@pytest.mark.integration` + `@pytest.mark.phase4`.
- [ ] **AC-2 — Hermetic fixture copy.** The test runs via `click.testing.CliRunner` and hermetically copies `tests/fixtures/repos/express-rerun/` to `tmp_path` before invocation. The `.codegenie/rag/records/<id>.yaml` seed is preserved in the copy; the copy is asserted to contain **exactly one** seeded record (`len(list((target / ".codegenie/rag/records").glob("*.yaml"))) == 1`), and the seed is loaded via typed `SolvedExample.from_yaml(...)` at test-setup time (no `yaml.safe_load` of a bare dict).
- [ ] **AC-3 — Cassette + lock identity check (BLAKE3) inside the test.** `_assert_cassette_lock_matches(CASSETTE, LOCKFILE)` is called for the S7-07 cassette before the rerun invocation, AND for the S7-06 baseline cassette before the baseline replay. Failure message points to `make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1`. Mirrors S7-06 AC-3.
- [ ] **AC-4 — Cassette files exist + entered in `cassettes.lock`.** Both `tests/cassettes/anthropic/test_phase4_e2e_replay_lands_rag.yaml` (the rerun cassette) and `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml` (the baseline cassette from S7-06) exist, are sanitized (S3-04), and have entries in `cassettes.lock` (S3-05) with BLAKE3.
- [ ] **AC-5 — `high_floor` sourced from plugin.yaml.** `high_floor = _load_high_floor(PLUGIN_YAML)` — no `0.85` literal duplicated in the test. Mirrors S7-06 CO-H-1.
- [ ] **AC-6 — `RagHitEvent` assertion (typed).** The workflow-internal event stream contains exactly one `RagHitEvent` (parsed via `_parse_typed_events(..., stream="workflow-internal")`). Assertion uses `isinstance(evt, RagHitEvent)` over the typed list, NOT dict `[e["kind"] == "..."]`. The event's `record_id` field equals the `SolvedExampleId` read from the seeded YAML via `_seed_record_id(FIXTURE_RERUN)`. The event's `score` field is `>= high_floor`.
- [ ] **AC-7 — `RagCandidateSelectedEvent` assertion.** Exactly one `RagCandidateSelectedEvent` (S5-01 AC-14) follows the `RagHitEvent` — pins that the selected `FencedSegment` reached prompt assembly. Asserted by `isinstance` filter; presence is the witness that S5-01's retriever did not drop the fenced segment after classification.
- [ ] **AC-8 — Event-absence companions (happy-path).** No `RagDegradedEvent`. No `RagMissEvent`. The seed is by construction high-confidence; a regression where the retriever degrades or misses must fail-loud here, not silently swallow into a different code path.
- [ ] **AC-9 — `LeafInvoked` after `RagHitEvent` (typed indices).** `idx_rag = next(i for i, e in enumerate(internal) if isinstance(e, RagHitEvent))`; `idx_leaf = next(i for i, e in enumerate(internal) if isinstance(e, LeafInvoked))`; `assert idx_rag < idx_leaf`. The dispatch is single-threaded; the indices are the spec.
- [ ] **AC-10 — `system[2]` few-shot in prompt (typed event field).** The `LeafInvoked` event carries `system_blocks_count == 3` (the canonical shape S3-02 emits). If S3-02 ships only `system_blocks_metadata: tuple[str, ...]` and not `system_blocks_count`, the implementer **surfaces as a Rule-7 blocker** and resolves by either adding the field to S3-02 (preferred — small surgical edit) or amending this AC to inspect the cassette body directly via the cassette-reading helper (recorded in Notes-for-implementer as the documented fallback). Do NOT silently average the two shapes.
- [ ] **AC-11 — No-operator-harvest static + import + subprocess guard.** `_assert_no_operator_harvest_invocation(test_phase4_e2e_replay_lands_rag)` is called inside the test; the helper scans the test function's source for: (a) any string containing the substring `"rag harvest"` or `"rag_harvest"`; (b) any `import` of a name matching `rag_harvest*` from `codegenie.cli` or any submodule of `codegenie`; (c) any `subprocess.*` call whose first arg literal contains `"codegenie"`. The helper is added to `_phase4_e2e_helpers.py` so S7-09 and any future "no-scaffolding-between-runs" E2E sibling reuses it (rule-of-three threshold; CO-3 / DP-8).
- [ ] **AC-12 — Cost-delta assertion against typed `LlmCostAccrued` from the spanning stream.** The **spanning** event stream (`.codegenie/events/spanning/append.jsonl.zst` — per ADR-04-0017 the `AttemptAnchor` family is spanning, not workflow-internal) contains exactly one `LlmCostAccrued` event filtered to this run's `workflow_id`. The captured `dollars` value is strictly less than `first_run_dollars * 0.5`, where `first_run_dollars` was captured by `_capture_first_run_baseline_dollars(tmp_path, BASELINE_CASSETTE, BASELINE_LOCKFILE, BASELINE_FIXTURE) -> tuple[float, int]`. Failure message names ADR-04-0017 and the spanning-stream path. Mirrors S7-06 AC-12.
- [ ] **AC-13 — First-run baseline is typed and non-zero (not a tautology).** `_capture_first_run_baseline_dollars` returns `(dollars, tokens_total)` from the typed `LlmCostAccrued` event captured during the baseline replay. The test asserts `dollars > 0.0` AND `tokens_total > 0` — strengthens the original `assert first_run_dollars > 0` which is satisfied by any cassette response. (TQ-3.)
- [ ] **AC-14 — `TrustOutcomeEmitted` `passed=True, confidence="high"` (typed; closed-set literal).** `trust = [e for e in internal if isinstance(e, TrustOutcomeEmitted)][0]`; `assert trust.passed is True and trust.confidence == "high"`. `confidence` is `Literal["high","degraded"]` per `src/codegenie/transforms/outcomes.py:403` — the only non-pass alternative is `"degraded"`, and asserting equality to `"high"` rules it out. (S6-03 HARDENED corrected `Literal["high","medium","low"]` doc drift.)
- [ ] **AC-15 — Harvest dedup branch asserted (closed-set literal).** Exactly one `HarvestSkipped` event with `reason == "already_harvested"` (NOT `"already_present"` — that string is not in S6-03's closed `Literal`). Asserted by `isinstance(evt, HarvestSkipped) and evt.reason == "already_harvested"`.
- [ ] **AC-16 — Event-absence companions for the harvest gate.** No `SolvedExampleHarvested` event on the rerun. Combined with AC-15, asserts mutual exclusion of the two terminal harvest events (matches S6-03 AC-15 invariant — exactly one terminal event per `on_validated` call). Mirrors S7-06 CO-H-3.
- [ ] **AC-17 — Dispatch-order assertion across both streams.** The typed-event sequence on the workflow-internal stream appears in canonical order by index: `provenance_classified` → `rag_hit_event` → `rag_candidate_selected` → `leaf_invoked` → `leaf_returned` → `plan_outcome_emitted` → `trust_outcome_emitted` → `harvest_skipped`. The spanning stream contains `llm_cost_accrued` for this workflow_id at any position after `leaf_returned`'s wall-clock (the two streams are independent files; we assert the spanning event's workflow_id matches and its presence, not a cross-stream index). Mirrors S7-06 AC-13.
- [ ] **AC-18 — Helper-module extension is additive only (Open/Closed at the file boundary).** `_phase4_e2e_helpers.py` gains three new functions appended to the end: `_capture_first_run_baseline_dollars`, `_seed_record_id`, `_assert_no_operator_harvest_invocation`. **Zero edits to the bodies of S7-06's kernel helpers** (`_parse_typed_events`, `_load_high_floor`, `_load_cve`, `_load_repo_ctx`, `_mask_nondeterministic_fields`, `_assert_cassette_lock_matches`). A unit test in `tests/integration/test__phase4_e2e_helpers.py` (created by S7-06; extended here) parametrizes over both the existing kernel symbols and the three new ones, asserting each is typed (no `Any`) and importable. Adding S7-09's adversarial E2E test must continue this pattern — surfaced as observable rent. Mirrors S7-06 AC-18 + DP-H-4.
- [ ] **AC-19 — Determinism guard (separate test function).** `test_phase4_e2e_replay_lands_rag_determinism` runs the workflow twice in succession against fresh `tmp_path` copies of `express-rerun/`, and asserts the two `remediation-report.yaml` bytes are equal after `_mask_nondeterministic_fields` (mirrors S7-06 AC-14 / TQ-H-4). Both runs replay the same cassette; the determinism regression diagnoses with its own failure message.
- [ ] **AC-20 — Fail-loud on missing jail binary (per-platform).** Linux → `bwrap`; macOS → `sandbox-exec`; raises `pytest.fail` with a platform-specific message; `pytest.skip` is forbidden (Rule 12). Mirrors S7-06 AC-16.
- [ ] **AC-21 — Cassette regeneration documented.** The test module docstring names `make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1` as the regeneration command, cross-links the cassette CODEOWNERS entry (S3-06), explains the BLAKE3 lock-update step, and explicitly warns: regenerate the rerun cassette only with the seed record present in the live run's `.codegenie/rag/records/` — otherwise the cassette captures the post-RAG-miss shape and the test silently passes the wrong way.
- [ ] **AC-22 — Typed-event parsing throughout (no `dict.get` shuffling).** Every event assertion uses `_parse_typed_events` returning `list[WorkflowInternalEvent]` / `list[WorkflowSpanningEvent]` plus `isinstance(...)` / `match ...` discrimination. No `e["kind"]`, no `r.get("outcome", {}).get(...)`. CLAUDE.md "no untyped `dict` shuffling" load-bearing commitment + S7-06 AC-15.
- [ ] **AC-23 — `make check` clean** under cassette replay (no live API calls).
- [ ] **AC-24 — TDD red test** exists, is committed, and is green after the Green step.

## Implementation outline

1. **Read first.** Open S6-03 HARDENED to confirm dedup behavior (S6-03 AC-7 step 3, `_solved_example_id_for` + `store.contains`, `HarvestSkipped(reason="already_harvested")`). Open S5-01 HARDENED to confirm event-class names (`RagHitEvent`, `RagCandidateSelectedEvent`) and their payloads (`record_id`, `score`). Open S7-06 HARDENED's `_phase4_e2e_helpers.py` to read the kernel helpers — your extensions must be additive, never edit existing bodies. Open S7-05 HARDENED to confirm the seed record's `solved_example_id` and embedding-model digest pinning.
2. **Build the test skeleton.** Hermetic fixture copy via `shutil.copytree`. Cassette + lock identity checks for both the S7-06 baseline cassette and the S7-07 rerun cassette. CLI invocation via `CliRunner`. Per-platform jail-binary fail-loud (mirror S7-06 AC-16 exactly).
3. **Record the rerun cassette** via `make refresh-cassettes`. **Recording precondition:** the seed record must be present in the live run's `.codegenie/rag/records/` — otherwise the live API sees no few-shot and the cassette's response shape will be the post-RAG-miss shape, silently producing a cassette that makes the test pass the wrong way. Document this in the test docstring as AC-21 requires.
4. **Add both cassettes (rerun + baseline) to `cassettes.lock`** (S3-05).
5. **Extend `_phase4_e2e_helpers.py` by addition.** Append `_capture_first_run_baseline_dollars`, `_seed_record_id`, `_assert_no_operator_harvest_invocation`. Add tests in `tests/integration/test__phase4_e2e_helpers.py` (already created by S7-06) parametrized over both kernel and new helpers. Do NOT edit kernel-helper bodies.
6. **Write the assertions in the order they appear in the event stream** (chronological by index) so a regression's failure point is unambiguous. For the cost-delta assertion, capture `first_run_dollars` BEFORE the rerun invocation by replaying S7-06's cassette via `_capture_first_run_baseline_dollars`.
7. **Add the `_assert_no_operator_harvest_invocation` guard** against substring, import, and subprocess regressions.
8. **Ship the determinism test** as a separate function (AC-19) — masking helper from S7-06.
9. **Flake-check** by running 10× in a row (or via `pytest-repeat --count=10`).

## TDD plan — red / green / refactor

### Red — write the failing test first

> **Convention reminders before reading the snippet (validator-added):**
>
> - Discriminator key on every event is `event_type:` (snake_case literal). Do NOT use `kind:`. Source of truth: `src/codegenie/plugins/events.py`.
> - `RetrievalOutcome` model discriminator is `kind: Literal["hit","miss","degraded"]` (S1-04). The retriever EVENT class is `RagHitEvent` with `event_type:` snake_case (S5-01). These are two different things — the model `kind` lives on `RagHit.kind == "hit"`; the event `event_type` lives on `RagHitEvent.event_type == "rag_hit"` (or whatever S5-01's executor pins it as — verify at executor time).
> - Provenance literals are lowercase snake_case: `app_direct`, `app_transitive`, `app_vendored`, `both` (S2-01 HARDENED). Source: `_APP_LAYER_PROVENANCE_KINDS`.
> - `HarvestSkipped.reason` closed-set literal is `{"already_harvested", "low_confidence", "trust_failed", "outcome_not_harvestable"}` (S6-03 AC-13). The dedup branch uses `"already_harvested"`, NOT `"already_present"`.
> - `TrustOutcome.confidence` is `Literal["high","degraded"]` (S6-03 line 17; `src/codegenie/transforms/outcomes.py:403`), NOT `["high","medium","low"]`.
> - `LlmCostAccrued` lives in the **spanning** stream (ADR-04-0017), not workflow-internal. Read both streams.
> - Event-class names for Phase-4-shipped events (`LeafInvoked`, `LeafReturned`, `PlanOutcomeEmitted`, `TrustOutcomeEmitted`, `LlmCostAccrued`, `SolvedExampleHarvested`, `HarvestSkipped`) must be **verified at executor time** against `src/codegenie/plugins/events.py`.
> - **Helper-module extension is additive only.** Append your three new helpers; never edit S7-06's kernel-helper bodies. Open/Closed at the file boundary.

```python
# tests/integration/test_phase4_e2e_replay_lands_rag.py
"""
Phase 4 roadmap exit criterion #2 — replay lands RAG; second run is cheaper.

Critically: **no operator step between runs.** The seed under
tests/fixtures/repos/express-rerun/.codegenie/rag/records/ stands in for
what S7-06's first run would have harvested. This test runs only the
second workflow; the seed is the production-behavior precondition.

Cost baseline: option (a) — fully hermetic. Inside the test, before
invoking the CLI on the rerun fixture, replay S7-06's cassette against
the express-cve-2026-1234 fixture via _capture_first_run_baseline_dollars
and capture the typed LlmCostAccrued event's dollars. Use that value as
the baseline for the cost-delta assertion.

Regenerating cassettes:
    make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1

WARNING: regenerate the rerun cassette ONLY with the seed record present
in the live run's .codegenie/rag/records/. Without the seed, the live API
sees no few-shot, the cassette captures the post-RAG-miss shape, and the
test silently passes the wrong way (degenerates to S7-06's path).

After regenerating, recompute the BLAKE3 of each cassette's bytes and
update tests/cassettes/anthropic/cassettes.lock (S3-05). AC-3 fails-loud
if the on-disk cassette and the lock entry disagree.

The cassette tests/cassettes/anthropic/test_phase4_e2e_replay_lands_rag.yaml
is owned by the rotating cassette-steward (CODEOWNERS); regeneration
requires that owner's approval.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Final

import pytest
from click.testing import CliRunner

from codegenie.cli import cli
from codegenie.plugins.events import (
    HarvestSkipped,
    LeafInvoked,
    PlanOutcomeEmitted,
    ProvenanceClassified,
    RagCandidateSelectedEvent,
    RagDegradedEvent,
    RagHitEvent,
    RagMissEvent,
    SolvedExampleHarvested,
    TrustOutcomeEmitted,
    # Spanning-stream variant:
    # LlmCostAccrued (verify import name at executor time against src/codegenie/plugins/events.py)
)
from codegenie.rag.models import SolvedExample

from tests.integration._phase4_e2e_helpers import (
    # Kernel from S7-06 — DO NOT EDIT THESE BODIES:
    _assert_cassette_lock_matches,
    _load_high_floor,
    _mask_nondeterministic_fields,
    _parse_typed_events,
    # New helpers appended by this story:
    _assert_no_operator_harvest_invocation,
    _capture_first_run_baseline_dollars,
    _seed_record_id,
)

FIXTURE_RERUN: Final[Path] = Path("tests/fixtures/repos/express-rerun")
FIXTURE_BASELINE: Final[Path] = Path("tests/fixtures/repos/express-cve-2026-1234")
CASSETTE: Final[Path] = Path("tests/cassettes/anthropic/test_phase4_e2e_replay_lands_rag.yaml")
CASSETTE_BASELINE: Final[Path] = Path("tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml")
LOCKFILE: Final[Path] = Path("tests/cassettes/anthropic/cassettes.lock")
PLUGIN_YAML: Final[Path] = Path("plugins/vulnerability-remediation--node--npm/plugin.yaml")
JAIL_BINARY: Final[str] = "bwrap" if sys.platform == "linux" else "sandbox-exec"


@pytest.fixture
def vcr_cassette_dir() -> str:
    return str(CASSETTE.parent)


@pytest.fixture
def hermetic_rerun(tmp_path: Path) -> Path:
    import shutil as _shutil_which
    if _shutil_which.which(JAIL_BINARY) is None:
        pytest.fail(
            f"jail binary {JAIL_BINARY!r} missing on {sys.platform}; "
            f"cannot run jailed npm install (AC-20; Rule 12 — Fail loud)"
        )
    target = tmp_path / "express-rerun"
    shutil.copytree(FIXTURE_RERUN, target)

    # AC-2 — fixture invariant: exactly one seeded record; typed load round-trips.
    seed_dir = target / ".codegenie" / "rag" / "records"
    seed_files = list(seed_dir.glob("*.yaml"))
    assert len(seed_files) == 1, (
        f"fixture must contain exactly one seeded record (S7-05 AC-11); "
        f"found {len(seed_files)} under {seed_dir}"
    )
    # Round-trip via typed model; fail-loud if S4-04's from_yaml rejects.
    SolvedExample.from_yaml(seed_files[0].read_text())
    return target


@pytest.mark.integration
@pytest.mark.phase4
@pytest.mark.vcr(CASSETTE.name, record_mode="none")
def test_phase4_e2e_replay_lands_rag(
    hermetic_rerun: Path, vcr_cassette_dir: str, tmp_path: Path
) -> None:
    # AC-3 — cassette identity checks for BOTH cassettes (rerun + baseline).
    _assert_cassette_lock_matches(CASSETTE, LOCKFILE)
    _assert_cassette_lock_matches(CASSETTE_BASELINE, LOCKFILE)

    # AC-11 — no operator-invoked harvest in this test (static + import + subprocess).
    _assert_no_operator_harvest_invocation(test_phase4_e2e_replay_lands_rag)

    # AC-12 / AC-13 — capture first-run baseline cost from S7-06's cassette
    # (option (a) — fully hermetic). Returns (dollars, tokens_total) typed.
    first_run_dollars, first_run_tokens = _capture_first_run_baseline_dollars(
        tmp_path=tmp_path,
        baseline_cassette=CASSETTE_BASELINE,
        baseline_lock=LOCKFILE,
        fixture=FIXTURE_BASELINE,
    )
    assert first_run_dollars > 0.0, (
        f"baseline LlmCostAccrued.dollars must be > 0 "
        f"(captured {first_run_dollars}); cassette regression?"
    )
    assert first_run_tokens > 0, (
        f"baseline LlmCostAccrued.tokens_total must be > 0 "
        f"(captured {first_run_tokens}); cassette regression?"
    )

    # AC-5 — high_floor from plugin.yaml (no 0.85 literal).
    high_floor = _load_high_floor(PLUGIN_YAML)

    # Drive the rerun invocation.
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["remediate", str(hermetic_rerun), "--cve", "CVE-2026-1234"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, (
        f"CLI failed: exit={result.exit_code}\n"
        f"output:\n{result.output}\n"
        f"exception: {result.exception!r}"
    )

    # Parse both streams as typed events. NEVER e["kind"].
    internal = _parse_typed_events(
        hermetic_rerun / ".codegenie" / "events", stream="workflow-internal"
    )
    spanning = _parse_typed_events(
        hermetic_rerun / ".codegenie" / "events", stream="spanning"
    )

    # AC-6 — RagHitEvent typed; record_id == seed; score >= high_floor.
    rag_hits = [e for e in internal if isinstance(e, RagHitEvent)]
    assert len(rag_hits) == 1, (
        f"expected exactly one RagHitEvent (seed is high-confidence); got {len(rag_hits)}"
    )
    seed_id = _seed_record_id(FIXTURE_RERUN)
    assert rag_hits[0].record_id == seed_id, (
        f"RagHitEvent.record_id ({rag_hits[0].record_id}) "
        f"!= seed solved_example_id ({seed_id}); model-mismatch silently degraded?"
    )
    assert rag_hits[0].score >= high_floor, (
        f"RagHitEvent.score ({rag_hits[0].score}) < high_floor ({high_floor}); "
        f"calibration drift?"
    )

    # AC-7 — RagCandidateSelectedEvent follows the hit.
    selected = [e for e in internal if isinstance(e, RagCandidateSelectedEvent)]
    assert len(selected) == 1, (
        f"S5-01 AC-14: RagCandidateSelectedEvent must fire for hit; "
        f"got {len(selected)} — selected FencedSegment likely dropped"
    )

    # AC-8 — event-absence companions: no degraded, no miss.
    assert not [e for e in internal if isinstance(e, RagDegradedEvent)], (
        "RagDegradedEvent fired; seed should be high-confidence hit"
    )
    assert not [e for e in internal if isinstance(e, RagMissEvent)], (
        "RagMissEvent fired; model-mismatch or chain-orphan silently excluded the seed"
    )

    # AC-9 — RagHitEvent before LeafInvoked (by index, single-threaded stream).
    idx_rag = next(i for i, e in enumerate(internal) if isinstance(e, RagHitEvent))
    idx_leaf = next(i for i, e in enumerate(internal) if isinstance(e, LeafInvoked))
    assert idx_rag < idx_leaf, (
        f"RagHitEvent (idx={idx_rag}) must precede LeafInvoked (idx={idx_leaf}) — "
        f"FallbackTier named-sequential dispatch (S6-01) regression"
    )

    # AC-10 — system[2] few-shot present on LeafInvoked.
    [leaf_evt] = [e for e in internal if isinstance(e, LeafInvoked)]
    # Pick ONE shape per Rule 7. system_blocks_count is the canonical S3-02 shape;
    # if S3-02 ships only system_blocks_metadata: tuple[str, ...], the implementer
    # surfaces as Rule-7 blocker and resolves additively (see Notes).
    assert leaf_evt.system_blocks_count == 3, (
        f"LeafInvoked.system_blocks_count == {leaf_evt.system_blocks_count}; "
        f"expected 3 (skill, instruction, rag_few_shot per arch §Prompt template structure)"
    )

    # AC-12 — LlmCostAccrued lives in SPANNING stream per ADR-04-0017.
    # cost = [e for e in spanning if isinstance(e, LlmCostAccrued)]
    # (verify import name at executor time)
    cost_events = [
        e
        for e in spanning
        if type(e).__name__ == "LlmCostAccrued"
    ]
    assert len(cost_events) == 1, (
        f"expected exactly one LlmCostAccrued in spanning stream; got {len(cost_events)} — "
        f"ADR-04-0017 family in {hermetic_rerun}/.codegenie/events/spanning/"
    )
    second_run_dollars = float(cost_events[0].dollars)
    assert second_run_dollars < first_run_dollars * 0.5, (
        f"replay cost {second_run_dollars} not < 0.5 * first-run baseline {first_run_dollars}; "
        f"system[2] cache regression? RAG-shapes-LLM path failure?"
    )

    # AC-14 — TrustOutcomeEmitted typed; passed=True, confidence='high' (closed-set).
    [trust] = [e for e in internal if isinstance(e, TrustOutcomeEmitted)]
    assert trust.passed is True, "strict-AND did not pass on the rerun"
    assert trust.confidence == "high", (
        f"TrustOutcome.confidence == {trust.confidence!r}; expected 'high' "
        f"(Literal['high','degraded'] per src/codegenie/transforms/outcomes.py:403)"
    )

    # AC-15 / AC-16 — Harvest dedup branch (closed-set literal) AND mutual exclusion.
    skipped = [e for e in internal if isinstance(e, HarvestSkipped)]
    harvested = [e for e in internal if isinstance(e, SolvedExampleHarvested)]
    assert len(harvested) == 0, (
        f"SolvedExampleHarvested fired on rerun (got {len(harvested)}); "
        f"S6-03 dedup pre-check (AC-7 step 3) should have skipped writing"
    )
    assert len(skipped) == 1 and skipped[0].reason == "already_harvested", (
        f"expected exactly one HarvestSkipped(reason='already_harvested'); "
        f"got {[(type(e).__name__, getattr(e, 'reason', None)) for e in skipped]}"
    )

    # AC-17 — Dispatch order across workflow-internal stream by index.
    # (Spanning stream is independent; we already asserted its single LlmCostAccrued above.)
    def _idx(cls: type) -> int:
        for i, e in enumerate(internal):
            if isinstance(e, cls):
                return i
        raise AssertionError(f"event class {cls.__name__} not present in stream")

    canonical_order = [
        ProvenanceClassified,
        RagHitEvent,
        RagCandidateSelectedEvent,
        LeafInvoked,
        # LeafReturned,  # add when S3-02 ships
        PlanOutcomeEmitted,
        TrustOutcomeEmitted,
        HarvestSkipped,
    ]
    indices = [_idx(cls) for cls in canonical_order]
    assert indices == sorted(indices), (
        f"dispatch out of canonical order; classes={[c.__name__ for c in canonical_order]}; "
        f"indices={indices} (expected strictly increasing)"
    )


@pytest.mark.integration
@pytest.mark.phase4
@pytest.mark.vcr(CASSETTE.name, record_mode="none")
def test_phase4_e2e_replay_lands_rag_determinism(tmp_path: Path) -> None:
    """AC-19 — running the rerun twice yields byte-identical
    remediation-report.yaml after masking workflow_id/timestamps/event_id.
    Mirrors S7-06 AC-14 / TQ-H-4; uses S7-06's _mask_nondeterministic_fields."""
    if shutil.which(JAIL_BINARY) is None:
        pytest.fail(
            f"jail binary {JAIL_BINARY!r} missing on {sys.platform}; "
            f"cannot run jailed npm install (Rule 12 — Fail loud)"
        )

    runner = CliRunner()

    def _one_run(label: str) -> str:
        target = tmp_path / label
        shutil.copytree(FIXTURE_RERUN, target)
        result = runner.invoke(
            cli,
            ["remediate", str(target), "--cve", "CVE-2026-1234"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        return (target / "remediation-report.yaml").read_text()

    a = _mask_nondeterministic_fields(_one_run("run-a"))
    b = _mask_nondeterministic_fields(_one_run("run-b"))
    assert a == b, "determinism regression: two replays produced different reports"
```

Run: `pytest tests/integration/test_phase4_e2e_replay_lands_rag.py -v` — all assertions fail before the chain is wired (Red).

### Green — make it pass

1. **Extend `_phase4_e2e_helpers.py` by addition only.** Append three new functions:
   - `_capture_first_run_baseline_dollars(*, tmp_path: Path, baseline_cassette: Path, baseline_lock: Path, fixture: Path) -> tuple[float, int]` — copies `fixture` to `tmp_path / "baseline"`, calls `_assert_cassette_lock_matches(baseline_cassette, baseline_lock)`, invokes the CLI under `vcr` replay of `baseline_cassette`, parses the spanning stream, returns `(dollars, tokens_total)` from the single `LlmCostAccrued` event filtered by workflow_id.
   - `_seed_record_id(fixture: Path) -> SolvedExampleId` — reads the single YAML under `fixture / ".codegenie/rag/records"`, parses via typed `SolvedExample.from_yaml`, returns `.id`.
   - `_assert_no_operator_harvest_invocation(test_fn: Callable[..., Any]) -> None` — uses `inspect.getsource(test_fn)` for substring checks AND `inspect.getmodule(test_fn)` for import-name scan AND AST-walks for `subprocess.*` calls whose first arg literal contains `"codegenie"`.
   - **Do NOT edit the bodies of kernel helpers** (`_parse_typed_events`, `_load_high_floor`, `_load_cve`, `_load_repo_ctx`, `_mask_nondeterministic_fields`, `_assert_cassette_lock_matches`). Open/Closed at the file boundary (AC-18).
2. **Extend `tests/integration/test__phase4_e2e_helpers.py`** (created by S7-06) with parametrized rows for the three new helpers — each `isinstance(...)`-style typing assertion + an end-to-end smoke (the cost-baseline helper smoked against a tiny stub cassette in tests/cassettes/).
3. **Record the rerun cassette** via `make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1` *with the seed record present in the live run's `.codegenie/rag/records/`*. Recording without the seed will silently produce a wrong-shape cassette (AC-21 warning).
4. **Add cassette + lock entry** for the rerun cassette.
5. **Iterate** until each assertion is green. The `RagHitEvent` → `LeafInvoked` ordering (a regression in `FallbackTier`'s named-sequential dispatch) is the most likely failure mode; the dispatch-order assertion (AC-17) names the culprit.

### Refactor — clean up

- Verify every event-class import name matches `src/codegenie/plugins/events.py` at executor time; if `LlmCostAccrued` is exported under a different name, fix the typed import and the `type(e).__name__ == "LlmCostAccrued"` fallback together — surface per Rule 12, do not weaken the assertion.
- Confirm the three new helpers each have a docstring naming the architectural concern they own (mirrors S7-06 AC-18 discipline).
- Flake-check 10× in a row: `pytest --count=10 tests/integration/test_phase4_e2e_replay_lands_rag.py -q` (requires `pytest-repeat`).

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase4_e2e_replay_lands_rag.py` | NEW — the exit-criterion #2 test (happy-path + determinism). |
| `tests/integration/_phase4_e2e_helpers.py` | EXT — append `_capture_first_run_baseline_dollars`, `_seed_record_id`, `_assert_no_operator_harvest_invocation`; **zero edits to S7-06's kernel helpers**. |
| `tests/integration/test__phase4_e2e_helpers.py` | EXT — parametrize new helpers (created by S7-06; extended here). |
| `tests/cassettes/anthropic/test_phase4_e2e_replay_lands_rag.yaml` | NEW — second-run cassette (recorded with seed record present). |
| `tests/cassettes/anthropic/cassettes.lock` | EXT — new entry with BLAKE3 for the rerun cassette. |

## Out of scope

- The first-run E2E itself (S7-06).
- Calibration of `high_floor` (S5-04 owns the smoke test; this story trusts the configured value and reads it from plugin.yaml).
- Adversarial RAG-poisoning tests (S7-09).
- Phase-11 post-merge webhook harvest path — Phase-4 ships only the inline path.
- Refactoring or amending S7-06's kernel helpers — additive only (AC-18 Open/Closed rent).

## Notes for the implementer

- **The "no operator step between runs" framing is load-bearing for ADR-04-0009.** The `_assert_no_operator_harvest_invocation` guard catches the most obvious regression (a future maintainer adding `runner.invoke(rag_harvest, ...)` between the fixture copy and the CLI invocation as a "convenience"); but the real defense is the seeded fixture standing in for the prior production-behavior harvest.
- **The cost delta is the most likely-to-flake assertion**: token counts depend on Anthropic's tokenizer, which changes silently across SDK versions. If the cassette is re-recorded under a new SDK pin, the delta-vs-baseline ratio may shift. The `< 0.5x` threshold is generous to absorb this; if it tightens over time, surface per Global Rule 12 and bump it explicitly in this story's acceptance criteria, not silently in the threshold constant.
- **The `RagHitEvent before LeafInvoked` assertion (AC-9) is the witness that `FallbackTier`'s named-sequential pipeline (S6-01) is preserved** — if a future refactor parallelizes the retriever and the leaf call, this test fails immediately and that's the right outcome.
- **The `system_blocks_count == 3` assertion (AC-10) depends on S3-02's `AnthropicLeafAdapter` emitting that metadata on `LeafInvoked`.** Rule 7: if S3-02 does not yet emit `system_blocks_count`, surface as a blocker and either (a) add the field to S3-02 (preferred — small surgical, supports future cache-warmth assertions), or (b) amend this AC to inspect the cassette body directly via a new `_assert_cassette_body_has_three_system_blocks(cassette: Path) -> None` helper appended to `_phase4_e2e_helpers.py`. Do NOT silently average the two shapes.
- **The cost-baseline via option (a) means this test invokes the CLI twice** — once on `express-cve-2026-1234` for the baseline, once on `express-rerun` for the assertion. Both invocations are cassette-replayed; total wall-clock should still be ≤ 60s.
- **S6-03 ships dedup.** Per S6-03 AC-7 step 3 + AC-8 + AC-13, the caller-side idempotence pre-check uses `_solved_example_id_for(outcome=..., embedding_model=embedder.model_digest())` + `store.contains(sid)` and emits `HarvestSkipped(reason="already_harvested")`. There is no parallel "if not dedup" branch. The original story's hedge ("if S6-03 dedups vs if it doesn't") was design-doc drift; the shipped contract is unambiguous.
- **Event-class names verified at executor time.** Before commit, grep `src/codegenie/plugins/events.py` for the actual `event_type: Literal[...] = "..."` lines shipped by Phase-4 stories S5-* / S6-* (the executor for S5-01 / S6-03 / S7-06 lands them), and adjust the test imports + literals. The `type(e).__name__ == "LlmCostAccrued"` line in the snippet is a fallback that the implementer should replace with a typed import once the class name is confirmed.
- **Open/Closed at the file boundary (AC-18) is the extension contract S7-09 inherits.** Future "no-scaffolding-between-runs" E2E siblings will add their own assertions to `_assert_no_operator_harvest_invocation`'s pattern set — those additions live in the helper, not in the per-test source. If the helper-module body grows beyond ~400 LOC, surface as a kernel-extract opportunity (rule-of-three), not as a "rewrite the kernel" move.
- **Phase-3 / Phase-4 recipe-refusal event ambiguity** (carried forward from S7-06 Notes): on this story's happy path, `RecipeSkipped` (Phase 3) and `PlanOutcomeEmitted{applied_from_recipe.kind == "not_applicable"}` (Phase 4 wrapping) may both fire. Do not blend them; pick the shape the executor for S6-03 actually ships and assert on that one. Surface per Rule 7 if ambiguous.
