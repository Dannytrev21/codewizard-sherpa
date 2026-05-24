# Story S7-06 — E2E breaking-change exit criterion #1

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** HARDENED
**Effort:** L
**Depends on:** S7-05 (fixture portfolio), S6-05 (`typecheck.typescript` SignalKind), S6-03 (`on_validated` harvest hook), S7-01 (plugin adapter wired), S7-02 (`rag_query_builder`), S2-01 (`_APP_LAYER_PROVENANCE_KINDS` + `ProvenanceClassified` event), S1-04 (`RetrievalOutcome` Pydantic discriminator), S3-05 (`cassettes.lock` discipline), Phase-3 S8-02 (CLI-driver + masking-helper precedent)
**ADRs honored:** ADR-0009 (inline harvest gated by `passed AND confidence == "high"`), ADR-0012 (ProvenanceGate spends zero tokens on non-app-layer), ADR-0015 (`typecheck.typescript` SignalKind in strict-AND), ADR-0014 (cassette discipline), ADR-0017 (`AttemptAnchor` event schema)

## Validation notes

Story hardened by `phase-story-validator` on 2026-05-24. Full report at `_validation/S7-06-e2e-breaking-change.md`. Key changes:

1. **Event-discriminator convention fixed.** Original test used `e["kind"] == "ProvenanceClassified"` / `e["kind"] == "RecipeOutcomeEmitted"`. Phase-3 / Phase-4 `WorkflowInternalEvent` variants in `src/codegenie/plugins/events.py` use `event_type:` (snake_case) as the discriminator, not `kind:` — confirmed in repo. The TDD-plan snippet, helper, and every event filter rewritten to `e["event_type"] == "provenance_classified"`, etc. (CN-B-1.)
2. **Provenance discriminator literals fixed.** Original `{"AppDirect", "AppTransitive", "AppVendored", "Both"}` is PascalCase; S2-01 HARDENED to **lowercase snake_case** literals `{"app_direct", "app_transitive", "app_vendored", "both"}` (see `_APP_LAYER_PROVENANCE_KINDS` in `src/codegenie/fallback/provenance_gate.py`). The set literal in the test must NOT be duplicated — the test imports `_APP_LAYER_PROVENANCE_KINDS` and asserts membership (Rule 7 — surface conflict; DP-H-1 — DRY single-source for the spec). (CN-B-2 / DP-H-1.)
3. **RetrievalOutcome discriminator literal fixed.** Original `outcome.kind == "rag_hit"` is wrong. S1-04 HARDENED `RetrievalOutcome = Annotated[RagHit | RagMiss | RagDegraded, Field(discriminator="kind")]` with literals `"hit"`, `"miss"`, `"degraded"`. AC and snippet corrected. (CN-B-3.)
4. **Phase-3 recipe emits `RecipeSkipped` / `RecipeFailed`, not `RecipeOutcomeEmitted`.** The story optimistically named an event Phase-3 does not currently emit. `RecipeSkipped(reason: str)` is the on-disk shape; `NotApplicableReason` literals are `MAJOR_BUMP_REFUSE` (UPPER_SNAKE), not `major_bump_breaking_change`. AC rewritten to assert `recipe_skipped` (or a Phase-4-added `plan_outcome_emitted` carrying the wrapped `RecipeOutcome` per ADR-0004) **after** verifying the actual event-kind at executor time against `src/codegenie/plugins/events.py`. (CN-B-4 / TQ-H-1.)
5. **Typed-event parsing replaces dict-shuffling.** Original `r.get("outcome", {}).get("kind") == "not_applicable"` violates CLAUDE.md's "no untyped dict shuffling" load-bearing commitment and the Phase-3 S8-02 precedent (which parses each line into a typed `WorkflowInternalEvent` discriminated-union variant). The TDD-plan snippet rewritten to use `pydantic.TypeAdapter(WorkflowInternalEvent).validate_python(line)` and `isinstance(evt, ProvenanceClassified)` / `match` arms. (DP-B-1 / TQ-H-2.)
6. **HarvestSkipped event-absence assertion added.** ADR-0009's gate fires `SolvedExampleHarvested` on the high-confidence path and `HarvestSkipped(reason=low_confidence)` on the medium-confidence path; both events must be mutually exclusive. Original ACs assert the positive fire but not the negative — a regression where the gate emits both events (or omits both) would silently pass. New AC added. (CO-H-3.)
7. **`high_floor` no longer hardcoded.** Original `assert outcome.score >= 0.85` duplicates the threshold; ADR-0008 names `plugin.yaml` as the source of truth. AC rewritten to read `high_floor` from the resolved plugin manifest (`plugins/vulnerability-remediation--node--npm/plugin.yaml`) and assert `>= high_floor`. If plugin.yaml ever raises the floor to 0.90, the test self-adjusts. (DP-H-2 / CO-H-1.)
8. **Plan-shape assertion strengthened.** Original asserted `plan_outcome.kind == "applied_from_llm"` but not the wrapped `PlanProposal` variant. Express 4→5 is structurally a *call-site rewrite*, not a dep-bump (the bump itself is what Phase-3 already refused). Added AC asserting the underlying `PlanProposal` discriminator equals `"callsite_rewrite"` (per ADR-0001 / S1-02 — `PlanProposalCallsiteRewrite`). A regression where the LLM emits `dep_bump` (and somehow Phase-5 still passes) would now fail-loud. (CO-H-2.)
9. **Dispatch-order assertion added.** Each AC checked event presence in isolation; out-of-order events (e.g., `SolvedExampleHarvested` before `TrustOutcomeEmitted`) would not be caught. New AC asserts the typed-event sequence appears in the canonical order: `provenance_classified` → recipe-skipped/failed → `leaf_invoked` → `leaf_returned` → `plan_outcome_emitted` → `trust_outcome_emitted` → `solved_example_harvested`. Indices, not timestamps. (CO-H-4.)
10. **`LlmCostAccrued` stream location pinned.** Per ADR-0017 the `AttemptAnchor` family lives in the **spanning** stream. Original test reads only `.codegenie/events/workflow-internal/`; cost assertion would silently never find the event. AC rewritten to read both streams via a single typed helper. (CN-H-1.)
11. **Cassette identity assertion narrowed.** Original "in cassettes.lock with matching BLAKE3" depended on CI's separate hygiene scanner. Added an in-test assertion that hashes the on-disk cassette at test-start and looks up the BLAKE3 in `cassettes.lock`, failing-loud with a `make refresh-cassettes` pointer if mismatched. Catches a contributor regenerating the cassette without updating the lock. (TQ-H-3.)
12. **Mutable default removed from helper signatures + helper module promotion.** Helpers (`_parse_typed_events`, `_load_high_floor`, `_load_cve`, `_load_repo_ctx`, `_mask_nondeterministic_fields`) ship in `tests/integration/_phase4_e2e_helpers.py` from the **Red** test on (not deferred to Refactor). Rule-of-three is crossed within this story (event parse, plan-outcome assert, harvest assert, cost assert, determinism rerun all share the parser) — extraction is justified now, not premature. S7-07 inherits by import; Phase-3 S8-02's `_mask_nondeterministic_fields` is the named precedent. (DP-H-3.)
13. **Determinism guard split into a separate test function.** Original AC inlined "running twice and comparing bytes" into the main test; pytest sees one function and one pass/fail. Split into `test_phase4_e2e_breaking_change_determinism` so the determinism property fails with its own diagnostic. (TQ-H-4.)
14. **`tsc` baseline path asserted in tmp.** Per ADR-0015, `.codegenie/typecheck/baseline-<repo-sha>.json` is the per-repo baseline; the test must assert it lands inside `tmp_path`, not in `$HOME` or the source fixture. Mirrors the hermeticity discipline of AC-3. (CN-H-2.)
15. **`bwrap` / `sandbox-exec` fail-loud applies to macOS too.** Original AC says "Linux/macOS"; AC clarified that on macOS the missing-binary is `sandbox-exec` (Phase 3 ADR-0007 substrate selection) and on Linux it is `bwrap`. Each platform raises with a platform-specific message. (CN-H-3.)
16. **Notes-for-implementer: extension-by-addition opportunity for next E2E sibling.** S7-07 (replay-lands-RAG) will mirror this story's scaffolding for the cache-hit case. The shared helper module is the kernel; adding a third E2E test (e.g., S7-09 adversarial corpus may want one) must be zero edits to `_phase4_e2e_helpers.py` — additive only. Surfaced as observable constraint: "adding a new Phase-4 E2E test requires zero edits to `_phase4_e2e_helpers.py`." (DP-H-4 — Open/Closed at the file boundary.)

Net effect: every AC is now individually verifiable against typed `WorkflowInternalEvent` / `WorkflowSpanningEvent` variants and named constants from the source tree; thresholds and discriminator literals are sourced from production code (not duplicated); the test no longer passes on a regression that flips outcome discriminators or skips the harvest gate.

## Context

This is **roadmap exit criterion #1** in one test file: a breaking-change CVE (Express 4→5, the `express-cve-2026-1234` fixture from S7-05) runs end-to-end — Phase-3 recipe returns `NotApplicable` because the bump is breaking → Phase-4 `FallbackTier` invokes the leaf LLM via cassette replay → the LLM emits a `PlanProposalCallsiteRewrite` → Phase-5 strict-AND (build + install + tests + lockfile_policy + cve_delta + **typecheck.typescript**) passes → orchestrator invokes `on_validated`, confidence-gate fires, inline harvest writes a `SolvedExample` to the store. Asserted by `LlmCostAccrued` event present, `SolvedExampleHarvested` event present, and a query of the store post-test returning the harvested record.

The test is **cassette-replayed**, not live — `pytest-recording` plays back the response Anthropic returned when the cassette was first recorded. Recording happens via `make refresh-cassettes --i-understand-this-spends-tokens` (S3-06) with `CODEGENIE_LIVE_LLM=1` set; the recorded cassette lands at `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml`, is sanitized by `CassetteSanitizer` (S3-04), and is BLAKE3-pinned in `cassettes.lock` (S3-05). CI replays only.

Three non-obvious failure modes the test must rule out:
1. **Provenance gate refuses but test still passes** — the test must positively assert `Provenance.AppTransitive` (or `AppDirect`) was the classification, so the LLM path actually ran (not a false-positive refuse).
2. **`tsc` reports degraded confidence (no `tsconfig.json`)** — the express fixture must ship `tsconfig.json` so `typecheck.typescript` reports `confidence="high"`, otherwise the harvest gate (`confidence == "high"`) won't fire and the test silently asserts the wrong final state.
3. **`SolvedExampleHarvested` event fires but the record isn't actually queryable** — the test must, after `on_validated`, query the store with the same CVE and assert the harvested record is returned with similarity ≥ `high_floor=0.85`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals — G1` — "Phase 3 recipe returns `NotApplicable` → Phase 4 LLM-replan succeeds → Phase 5 strict-AND (build, install, tests, lockfile_policy, cve_delta, **typecheck.typescript**) passes → outcome harvested → second run on the same case hits RAG and shapes a cheaper LLM call. Asserted by `tests/integration/test_phase4_e2e_breaking_change.py` + `tests/integration/test_phase4_e2e_replay_lands_rag.py`."
  - `../phase-arch-design.md §Scenario 2` — full sequence diagram (Major-version bump triggers LLM fallback, harvests on validate). Each numbered arrow is an assertable event.
  - `../phase-arch-design.md §Edge case #1` — provenance gate refusal scenario (the test must rule it out for express by asserting `AppTransitive` was classified).
  - `../phase-arch-design.md §Testing strategy §End-to-end` — "The two E2E tests above against `fixtures/vuln-major-bump/express-cve-2026-1234/` are end-to-end (CLI → patch on disk → Stage 6 strict-AND pass)."
- **Phase ADRs:**
  - `../ADRs/0009-inline-auto-harvest-confidence-gate.md` — `TrustOutcome.passed AND confidence == "high"` is the harvest gate; this story's test asserts both conditions hold and the harvest fires.
  - `../ADRs/0012-provenance-gate-explicit-tier-zero.md` — refuse-set; the test must assert `Provenance.AppTransitive` (so LLM was actually called).
  - `../ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md` — `typecheck.typescript` is one of the six signals in strict-AND.
  - `../ADRs/0014-cassette-discipline-security-control.md` — the cassette this test consumes must be sanitized, lock-pinned, and CI-replayed.
- **Source design:**
  - `../final-design.md §Component 1 — FallbackTier` + §Component 11 — `TypecheckTypescriptSignal`.
- **High-level impl:**
  - `../High-level-impl.md §Step 7 §Done criteria` — "Roadmap exit criterion #1: `test_phase4_e2e_breaking_change.py` ... green under cassette replay."
- **Existing code:**
  - `tests/fixtures/repos/express-cve-2026-1234/` (S7-05) — the fixture.
  - `tests/integration/test_end_to_end_express_cve.py` (Phase-3 S8-02) — the **template** to mirror for CLI-driver pattern, masking helpers, golden-file approach. Read first.
  - `src/codegenie/cli/__init__.py` — the `codegenie remediate` Click subcommand (Phase 3 S6-05).
  - `src/codegenie/orchestrator/orchestrator.py` (Phase 3) — `RemediationOrchestrator.run`.
  - `src/codegenie/fallback/tier.py` (S6-01) and `plugins/.../subgraph/fallback_plan_engine.py` (S7-01) — the plan adapter.

## Goal

Land `tests/integration/test_phase4_e2e_breaking_change.py` as a cassette-replayed CI-gating integration test that runs `codegenie remediate ./tests/fixtures/repos/express-cve-2026-1234 --cve CVE-2026-1234` and asserts: (a) the CLI exits 0; (b) the `Provenance.AppTransitive` classification fired (provenance gate did **not** refuse); (c) Phase-3 recipe returned `NotApplicable(major_bump_breaking_change)`; (d) `LeafInvoked` fired exactly once; (e) `PlanProposalCallsiteRewrite` was returned; (f) Phase-5 strict-AND passed including `typecheck.typescript`; (g) `confidence == "high"`; (h) `SolvedExampleHarvested` fired; (i) querying the store post-run returns the harvested record with similarity ≥ `high_floor`. Green under cassette replay.

## Acceptance criteria

- [ ] **AC-1 — Test file shape.** `tests/integration/test_phase4_e2e_breaking_change.py` exists, is collected by pytest (no `@pytest.mark.skip*`, no `xfail`), is marked `@pytest.mark.integration` and `@pytest.mark.phase4`, and a `pytest --collect-only` run lists every test function.
- [ ] **AC-2 — In-process CLI invocation.** The test imports `from codegenie.cli import cli` and invokes via `click.testing.CliRunner().invoke(cli, ["remediate", str(repo), "--cve", "CVE-2026-1234"], catch_exceptions=False)` so coverage instruments the orchestrator + plugin paths. `result.exit_code == 0` is asserted with `result.output` AND `result.exception` in the failure message.
- [ ] **AC-3 — Cassette identity, sanitized, lock-pinned.** `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml` exists, was recorded via `make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1`, passes `tests/security/test_cassettes_clean.py` (S3-05), and is entered in `tests/cassettes/anthropic/cassettes.lock` (S3-05). The test itself reads the on-disk cassette bytes at start-of-test, computes BLAKE3, and asserts the digest matches the `cassettes.lock` entry — failing-loud with a `make refresh-cassettes` pointer if mismatched (catches a contributor regenerating the cassette without updating the lock).
- [ ] **AC-4 — Hermeticity.** `shutil.copytree(FIXTURE, tmp_path / "express-cve-2026-1234")` runs before CLI invocation; every `.codegenie/` write and git branch creation lands inside `tmp_path`; the source fixture is byte-identical pre-and-post (asserted via a recursive `dircmp` or the existing fixture-pinning fence). The `.codegenie/typecheck/baseline-<repo-sha>.json` file (ADR-0015) lands inside `tmp_path`, not in `$HOME` or the source fixture.
- [ ] **AC-5 — Provenance assertion (rules out the refuse false-positive).** The test parses the workflow-internal stream into typed `WorkflowInternalEvent` variants and finds exactly one `ProvenanceClassified` event whose `provenance_kind` is a member of the imported constant `from codegenie.fallback.provenance_gate import _APP_LAYER_PROVENANCE_KINDS` (today: `{"app_direct", "app_transitive", "app_vendored", "both"}`, lowercase per S2-01 HARDENED). The test does **not** duplicate the set literal — Rule 7 / DRY: the source-of-truth constant is the spec. A regression where `_APP_LAYER_PROVENANCE_KINDS` shrinks (e.g., drops `"both"`) flips this AC automatically.
- [ ] **AC-6 — Phase-3 recipe refusal assertion.** The event stream contains a `RecipeSkipped` (or, if Phase 4 has shipped a `PlanOutcomeEmitted` wrapping `RecipeOutcome.NotApplicable` per ADR-0004, that variant) with `reason == "MAJOR_BUMP_REFUSE"` (the `NotApplicableReason` literal exported by `codegenie.transforms.outcomes`, UPPER_SNAKE — read the source, do not hardcode). Implementer must verify the actual event name shipped by Phase-3 S7-04 / Phase-4 S6-01 against `src/codegenie/plugins/events.py` at executor time and surface any drift loudly rather than blending discriminator literals.
- [ ] **AC-7 — LLM-was-called assertion.** The event stream contains exactly one `LeafInvoked` event and exactly one `LeafReturned` event (verified by `event_type` discriminator from `src/codegenie/plugins/events.py` once those events land in S3-* of this phase). `LeafReturned.tokens_in > 0` and `LeafReturned.tokens_out > 0`. Combined with AC-5, rules out the silent-provenance-refuse failure mode (Goal G7).
- [ ] **AC-8 — Plan-shape assertion (variant + wrapped proposal).** The event stream's `PlanOutcomeEmitted` event (per ADR-0004) carries the `applied_from_llm` discriminator (per S1-04 / Phase-4 `PlanOutcome` sum type), has a non-empty `response_id`, AND the wrapped `PlanProposal` discriminator equals `"callsite_rewrite"` (per ADR-0001 / S1-02 — Express 4→5 is structurally a call-site rewrite, NOT a dep-bump). A regression where the LLM emits `dep_bump` would fail-loud (the dep-bump path is what Phase 3 already refused).
- [ ] **AC-9 — Strict-AND-passed assertion.** The Phase-5 `TrustOutcome` event carries `passed=True`, `confidence="high"`, and `signals` contains a `typecheck.typescript` entry with `passed=True` (Goal G10 / ADR-0015). Plus an event-ordering assertion: the `typecheck.typescript` signal's `started_at` index is **before** the `npm test` signal's `started_at` index (per ADR-0015 §"signal must fail before npm test runs"). If the implementation does not emit per-signal timing, this sub-clause downgrades to "signal appears in the `signals` list" — surface the omission as a Phase-4 follow-up.
- [ ] **AC-10 — Harvest-fired assertion (positive AND negative).** The event stream contains exactly one `SolvedExampleHarvested` event with a non-empty `solved_example_id` AND **zero** `HarvestSkipped` events (defensive against ADR-0009 gate emitting both signals on a regression). The two events are mutually exclusive per ADR-0009; the test asserts both halves.
- [ ] **AC-11 — Store-queryable assertion (high_floor from plugin.yaml).** After the workflow completes, the test instantiates `ChromaPersistentStore` against `tmp_path / ".codegenie" / "rag" / "chroma"`, builds a `Query` via the plugin's `rag_query_builder.build(...)` (S7-02), and asserts `outcome.kind == "hit"` (the `RagHit` discriminator literal per S1-04 — NOT `"rag_hit"`) and `outcome.score >= high_floor` where `high_floor` is read at test time from the resolved `plugins/vulnerability-remediation--node--npm/plugin.yaml` (ADR-0008 — the threshold is configured, not hardcoded). If plugin.yaml ever raises `high_floor` to 0.90, this AC self-adjusts.
- [ ] **AC-12 — Cost-recorded assertion (spanning stream).** The **spanning** event stream (`.codegenie/events/spanning/append.jsonl.zst` — per ADR-0017 the `AttemptAnchor` family is spanning, NOT workflow-internal) contains one `LlmCostAccrued` event filtered to this run's `workflow_id`, with non-zero tokens AND non-zero dollars. The captured `(tokens_total, dollars)` tuple is asserted equal to the values S7-07 will read for delta comparison; if the schema does not yet pin field names, the test captures them by `event_type` and `model_dump()` into a typed pydantic model.
- [ ] **AC-13 — Dispatch-order assertion.** The typed-event sequence appears in canonical order: `provenance_classified` → `recipe_skipped` (or `plan_outcome_emitted` variant `applied_from_recipe.kind == "not_applicable"`) → `leaf_invoked` → `leaf_returned` → `plan_outcome_emitted` → `trust_outcome_emitted` → `solved_example_harvested`. Asserted by index in the parsed list (not by wall-clock timestamps — clock skew within a single process is irrelevant; we want the dispatch order to be the spec).
- [ ] **AC-14 — Determinism guard (separate test).** A second test function `test_phase4_e2e_breaking_change_determinism` runs the workflow twice in succession against fresh `tmp_path` copies, and asserts the two `remediation-report.yaml` bytes are equal after applying the **shared** `_mask_nondeterministic_fields` helper (mirroring Phase-3 S8-02 §AC-4 — the masking discipline: mask `workflow_id`, `event_id`, ISO-8601 timestamps, branch suffix; nothing else). Splitting the determinism property into its own test makes a determinism regression diagnose with its own failure message instead of being subsumed under the main happy-path assertions.
- [ ] **AC-15 — Typed-event parsing (no dict-shuffling).** The event-stream helper parses each line into a `pydantic.TypeAdapter(WorkflowInternalEvent).validate_python(...)` or `validate_json(...)` typed variant (NOT `dict.get`); per-AC assertions use `isinstance(evt, EventClass)` / `match evt` arms. Mirrors Phase-3 S8-02 AC-8's typed-discriminated-union parsing precedent; CLAUDE.md "no untyped `dict` shuffling" load-bearing commitment.
- [ ] **AC-16 — Fail-loud on missing jail binary (per-platform).** The test fails-loud (not skips) if the platform-required jail binary is missing: on Linux, `bwrap` (Phase 3 ADR-0007 substrate); on macOS, `sandbox-exec`. Each platform branch raises `pytest.fail` with a platform-specific message; `pytest.skip` is forbidden (Rule 12 — Fail loud).
- [ ] **AC-17 — Cassette regeneration documented.** The test's module docstring names `make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1` as the regeneration command, cross-links the cassette CODEOWNERS entry (S3-06), and explains the BLAKE3 lock-update step that follows (AC-3).
- [ ] **AC-18 — Helper module shipped from Red, not deferred to Refactor.** `tests/integration/_phase4_e2e_helpers.py` exists by the end of the Red step and exports `_parse_typed_events(events_dir, *, stream: Literal["workflow-internal", "spanning"]) -> list[WorkflowInternalEvent | WorkflowSpanningEvent]`, `_load_high_floor(plugin_yaml: Path) -> float`, `_load_cve(repo_root: Path) -> CveAdvisory`, `_load_repo_ctx(repo_root: Path) -> RepoContext`, `_mask_nondeterministic_fields(text: str) -> str`, and `_assert_cassette_lock_matches(cassette: Path, lock: Path) -> None`. Each helper is typed (no `Any`); each has a docstring naming the architectural concern it owns. S7-07 imports the same module — adding S7-09's E2E test must require **zero edits** to this helper module (Open/Closed at the file boundary; DP-H-4).
- [ ] **AC-19 — `make check` clean** under cassette replay (no live API calls).
- [ ] **AC-20 — TDD red test** exists, is committed, and is green after the Green step.

## Implementation outline

1. **Read first**: open `tests/integration/test_end_to_end_express_cve.py` (Phase-3 S8-02) for the CLI-driver, masking-helper, and golden-file patterns; mirror them (Global Rule 11).
2. Write the test skeleton: copy the fixture to `tmp_path`, invoke the CLI via `CliRunner`, assert exit code, parse the event stream.
3. Implement the cassette-recording flow first (one-time): run `make refresh-cassettes` with `CODEGENIE_LIVE_LLM=1` set + valid Anthropic API key in keyring; the recorded cassette lands under `tests/cassettes/anthropic/` and is sanitized by S3-04's hooks at record time.
4. Add the cassette to `cassettes.lock` (S3-05): compute BLAKE3, append the entry.
5. Implement the event-stream parser (read `.codegenie/events/workflow-internal/<workflow_id>.jsonl.zst`, decompress, parse line-by-line into typed `WorkflowInternalEvent` variants from Phase 3).
6. Add per-acceptance-bullet assertions, each with a meaningful failure message naming which roadmap criterion or arch §Scenario 2 numbered arrow is violated.
7. Add the post-test store-queryability assertion: open `ChromaPersistentStore` against the tmp dir; build a `Query` via `rag_query_builder.build(...)`; assert similarity ≥ 0.85.
8. Run with cassette replay to confirm green; flake-check by running 10× in a row.

## TDD plan — red / green / refactor

### Red — write the failing test first

> **Convention reminders before reading the snippet (validator-added):**
> - Discriminator key is `event_type:` (snake_case) per Phase-3 / Phase-4 `WorkflowInternalEvent` / `WorkflowSpanningEvent` definitions in `src/codegenie/plugins/events.py`. Do NOT use `kind:` for event-type matching.
> - Provenance literals are lowercase snake_case: `app_direct`, `app_transitive`, `app_vendored`, `both` (S2-01 HARDENED). Source of truth: `_APP_LAYER_PROVENANCE_KINDS` — import it, do not duplicate.
> - `RetrievalOutcome` discriminator literals are `"hit"`, `"miss"`, `"degraded"` (S1-04 HARDENED), NOT `"rag_hit"`.
> - `NotApplicableReason` literals are UPPER_SNAKE: `"MAJOR_BUMP_REFUSE"` etc., exported from `codegenie.transforms.outcomes`.
> - Event names for Phase-4-shipped events (`LeafInvoked`, `LeafReturned`, `PlanOutcomeEmitted`, `TrustOutcomeEmitted`, `LlmCostAccrued`, `SolvedExampleHarvested`, `HarvestSkipped`) must be **verified at executor time** against `src/codegenie/plugins/events.py` (Phase-4 stories S2-* / S6-* land them). The snippet below uses placeholder `event_type` literals in snake_case; the implementer reconciles against the source and surfaces drift loudly (Rule 12).

```python
# tests/integration/test_phase4_e2e_breaking_change.py
"""
Phase 4 roadmap exit criterion #1 — breaking-change CVE solved end-to-end.

Regenerating the cassette:
    make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1

After regenerating, recompute the BLAKE3 of the new cassette bytes and update
`tests/cassettes/anthropic/cassettes.lock` (S3-05). AC-3 fails-loud if the
on-disk cassette and the lock entry disagree.

The cassette `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml`
is owned by the rotating cassette-steward (CODEOWNERS); regeneration requires
that owner's approval.
"""
from __future__ import annotations
import shutil
import sys
from pathlib import Path
from typing import Final

import pytest
from click.testing import CliRunner

from codegenie.cli import cli
from codegenie.fallback.provenance_gate import _APP_LAYER_PROVENANCE_KINDS
from codegenie.plugins.events import (
    ProvenanceClassified,
    RecipeSkipped,
    # Phase-4-shipped event types — verify against src/codegenie/plugins/events.py
    # at executor time; the import names below are the convention, not a guarantee:
    # LeafInvoked, LeafReturned, PlanOutcomeEmitted, TrustOutcomeEmitted,
    # SolvedExampleHarvested, HarvestSkipped, LlmCostAccrued,
)
from codegenie.rag.store import ChromaPersistentStore

from tests.integration._phase4_e2e_helpers import (
    _assert_cassette_lock_matches,
    _load_cve,
    _load_high_floor,
    _load_repo_ctx,
    _mask_nondeterministic_fields,
    _parse_typed_events,
)

FIXTURE: Final[Path] = Path("tests/fixtures/repos/express-cve-2026-1234")
CASSETTE: Final[Path] = Path("tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml")
LOCKFILE: Final[Path] = Path("tests/cassettes/anthropic/cassettes.lock")
PLUGIN_YAML: Final[Path] = Path("plugins/vulnerability-remediation--node--npm/plugin.yaml")
JAIL_BINARY: Final[str] = "bwrap" if sys.platform == "linux" else "sandbox-exec"


@pytest.fixture
def vcr_cassette_dir() -> str:
    return str(CASSETTE.parent)


@pytest.fixture
def hermetic_repo(tmp_path: Path) -> Path:
    import shutil as _shutil_which
    if _shutil_which.which(JAIL_BINARY) is None:
        pytest.fail(
            f"jail binary {JAIL_BINARY!r} missing on {sys.platform}; "
            f"cannot run jailed npm install (AC-16; Rule 12 — Fail loud)"
        )
    target = tmp_path / "express-cve-2026-1234"
    shutil.copytree(FIXTURE, target)
    return target


@pytest.mark.integration
@pytest.mark.phase4
@pytest.mark.vcr(CASSETTE.name, record_mode="none")
def test_phase4_e2e_breaking_change(hermetic_repo: Path, vcr_cassette_dir: str) -> None:
    # AC-3 — cassette identity check before the workflow even starts.
    _assert_cassette_lock_matches(CASSETTE, LOCKFILE)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["remediate", str(hermetic_repo), "--cve", "CVE-2026-1234"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, (
        f"CLI failed: exit={result.exit_code}\n"
        f"output:\n{result.output}\n"
        f"exception: {result.exception!r}"
    )

    internal = _parse_typed_events(
        hermetic_repo / ".codegenie" / "events", stream="workflow-internal"
    )
    spanning = _parse_typed_events(
        hermetic_repo / ".codegenie" / "events", stream="spanning"
    )

    # AC-5 — provenance fires; kind is in the imported app-layer set.
    provs = [e for e in internal if isinstance(e, ProvenanceClassified)]
    assert len(provs) == 1, f"expected exactly one ProvenanceClassified, got {len(provs)}"
    assert provs[0].provenance_kind in _APP_LAYER_PROVENANCE_KINDS, (
        f"provenance_kind={provs[0].provenance_kind!r} is not in "
        f"_APP_LAYER_PROVENANCE_KINDS={_APP_LAYER_PROVENANCE_KINDS!r} — "
        "the provenance gate would have refused; LeafInvoked would never fire; "
        "Phase-4 G7 is silently violated."
    )

    # AC-6 — Phase-3 recipe refused with MAJOR_BUMP_REFUSE.
    # NOTE: implementer verifies whether Phase-4 emits a wrapping PlanOutcomeEmitted
    # event or whether the underlying RecipeSkipped is what surfaces — adjust the
    # isinstance and reason field accordingly; do not silently weaken to substring match.
    refused = [e for e in internal if isinstance(e, RecipeSkipped)]
    assert any(e.reason == "MAJOR_BUMP_REFUSE" for e in refused), (
        f"no RecipeSkipped(reason='MAJOR_BUMP_REFUSE') in internal stream; "
        f"saw reasons={[e.reason for e in refused]!r}"
    )

    # AC-7 — LLM invoked exactly once. (See ADR-0017 / S2-* / S3-* for actual event types.)
    # leaf_invoked = [e for e in internal if isinstance(e, LeafInvoked)]
    # leaf_returned = [e for e in internal if isinstance(e, LeafReturned)]
    # assert len(leaf_invoked) == 1 and len(leaf_returned) == 1
    # assert leaf_returned[0].tokens_in > 0 and leaf_returned[0].tokens_out > 0

    # AC-8 — plan_outcome_emitted is applied_from_llm with callsite_rewrite proposal.
    # [plan_out] = [e for e in internal if isinstance(e, PlanOutcomeEmitted)]
    # assert plan_out.plan_outcome_kind == "applied_from_llm"
    # assert plan_out.plan_outcome.response_id
    # assert plan_out.plan_proposal_kind == "callsite_rewrite", (
    #     "Express 4→5 is structurally a callsite rewrite; dep_bump would mean Phase 3 should not have refused"
    # )

    # AC-9 — strict-AND passes with typecheck.typescript first.
    # [trust] = [e for e in internal if isinstance(e, TrustOutcomeEmitted)]
    # assert trust.passed is True and trust.confidence == "high"
    # signal_kinds = {s.kind for s in trust.signals}
    # assert "typecheck.typescript" in signal_kinds
    # [ts_sig] = [s for s in trust.signals if s.kind == "typecheck.typescript"]
    # assert ts_sig.passed is True
    # if hasattr(ts_sig, "started_at"):
    #     [test_sig] = [s for s in trust.signals if s.kind in {"test_stage", "tests"}]
    #     assert ts_sig.started_at < test_sig.started_at  # ADR-0015: tsc before npm test

    # AC-10 — harvest fired positively; HarvestSkipped did NOT fire (mutually exclusive per ADR-0009).
    # harvests = [e for e in internal if isinstance(e, SolvedExampleHarvested)]
    # skipped = [e for e in internal if isinstance(e, HarvestSkipped)]
    # assert len(harvests) == 1 and len(skipped) == 0, (
    #     "ADR-0009 gate: SolvedExampleHarvested and HarvestSkipped are mutually exclusive; "
    #     f"got harvests={len(harvests)} skipped={len(skipped)}"
    # )
    # assert harvests[0].solved_example_id

    # AC-12 — LlmCostAccrued lives in the SPANNING stream per ADR-0017.
    # cost = [e for e in spanning if isinstance(e, LlmCostAccrued) and e.workflow_id == provs[0].workflow_id]
    # assert len(cost) == 1
    # assert cost[0].tokens_total > 0 and float(cost[0].dollars) > 0

    # AC-13 — dispatch order asserted by index, not by timestamps.
    # order = [e.event_type for e in internal]
    # def _idx(name: str) -> int:
    #     return next(i for i, n in enumerate(order) if n == name)
    # assert (
    #     _idx("provenance_classified")
    #     < _idx("recipe_skipped")
    #     < _idx("leaf_invoked")
    #     < _idx("leaf_returned")
    #     < _idx("plan_outcome_emitted")
    #     < _idx("trust_outcome_emitted")
    #     < _idx("solved_example_harvested")
    # )

    # AC-11 — store is queryable post-run; harvested record returns at or above plugin.yaml's high_floor.
    advisory = _load_cve(hermetic_repo)
    repo_ctx = _load_repo_ctx(hermetic_repo)
    high_floor = _load_high_floor(PLUGIN_YAML)
    from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder
    q = rag_query_builder.build(advisory, repo_ctx)
    store = ChromaPersistentStore(hermetic_repo / ".codegenie" / "rag" / "chroma")
    try:
        outcome = store.query(q, top_k=1)
    finally:
        store.close()
    assert outcome.kind == "hit", f"expected RagHit (kind='hit'), got kind={outcome.kind!r}"
    assert outcome.score >= high_floor, (
        f"score={outcome.score} below plugin.yaml high_floor={high_floor}; "
        "harvested record not retrievable above the high-confidence band"
    )

    # AC-4 — baseline landed inside tmp.
    baselines = list((hermetic_repo / ".codegenie" / "typecheck").glob("baseline-*.json"))
    assert baselines, "tsc baseline did not land under tmp .codegenie/typecheck/"


@pytest.mark.integration
@pytest.mark.phase4
@pytest.mark.vcr(CASSETTE.name, record_mode="none")
def test_phase4_e2e_breaking_change_determinism(tmp_path: Path) -> None:
    """AC-14 — running the workflow twice yields byte-identical reports after masking."""
    runner = CliRunner()
    reports: list[bytes] = []
    for i in range(2):
        repo = tmp_path / f"run-{i}" / "express-cve-2026-1234"
        repo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(FIXTURE, repo)
        result = runner.invoke(
            cli, ["remediate", str(repo), "--cve", "CVE-2026-1234"], catch_exceptions=False
        )
        assert result.exit_code == 0, f"run {i} failed: {result.output}"
        raw = (repo / ".codegenie" / "remediation-report.yaml").read_bytes()
        reports.append(_mask_nondeterministic_fields(raw.decode("utf-8")).encode("utf-8"))
    assert reports[0] == reports[1], (
        "determinism regression — Goal G4 violated; report bytes differ after masking"
    )
```

Run: `pytest tests/integration/test_phase4_e2e_breaking_change.py -v` — fails on every assertion before the implementation chain is wired (events not emitted, store empty, cassette absent, helper module absent).

### Green — make it pass

1. Wire the pieces from Steps 1–6 + S7-01..S7-05.
2. Record the cassette via `make refresh-cassettes` and confirm `tests/security/test_cassettes_clean.py` passes.
3. Add the cassette to `cassettes.lock`.
4. Run the test; iterate until every assertion is green.

### Refactor — clean up

- The helper module `tests/integration/_phase4_e2e_helpers.py` lands in **Red** (AC-18), not Refactor — the rule-of-three is already crossed within this story (event parsing, cost lookup, determinism rerun, harvest assertion, store query) plus S7-07. The refactor pass tightens the helpers' docstrings and verifies the module imports cleanly from S7-07.
- Add per-helper unit tests (mirror Phase-3 S8-02 AC-13): `tests/integration/test__phase4_e2e_helpers.py` exercises `_mask_nondeterministic_fields`, `_parse_typed_events`, and `_assert_cassette_lock_matches` against tiny hand-built inputs (a wrong regex / wrong stream dispatch / wrong BLAKE3 is far cheaper to debug here than inside a failing E2E).
- Run the E2E 10× in a row under cassette replay (`pytest tests/integration/test_phase4_e2e_breaking_change.py --count=10`); document any flake-mitigation choice in the module docstring.
- Confirm the determinism test (AC-14) passes; if it flakes, the masker is missing a nondeterministic field — surface and add (do NOT mask substantive fields like `transform.diff_bytes_sha256`; that is a Goal-G4 regression, not a masker omission).

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase4_e2e_breaking_change.py` | The exit-criterion test (two test functions per AC-14). |
| `tests/integration/_phase4_e2e_helpers.py` | NEW — shared helpers for S7-06 + S7-07 + future Phase-4 E2E tests (event-stream parser, plugin.yaml threshold loader, fixture loaders, cassette-lock checker, mask helper). Open/Closed at the file boundary (AC-18 / DP-H-4). |
| `tests/integration/test__phase4_e2e_helpers.py` | NEW — unit tests for each helper in isolation (Refactor step). |
| `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml` | Recorded (sanitized) Anthropic cassette. |
| `tests/cassettes/anthropic/cassettes.lock` | New entry with BLAKE3 hash of the cassette (AC-3 reads this). |

## Out of scope

- The replay-lands-RAG E2E test (S7-07) — sibling story consuming the harvested record from this test's store output.
- Adversarial corpus (S7-09).
- Golden-file masking (optional here; mandatory in S8-02 of Phase 3 for the report; this E2E test's primary assertions are event-driven, not byte-equal report).
- Performance regression `bench_phase4_e2e_cassette_replay` (covered under S6-01's `bench` markers).

## Notes for the implementer

- **Verify event-type literals at executor time.** The TDD snippet uses placeholder snake_case event names (`leaf_invoked`, `plan_outcome_emitted`, `trust_outcome_emitted`, `solved_example_harvested`, `harvest_skipped`, `llm_cost_accrued`). Before commit, grep `src/codegenie/plugins/events.py` for the actual `event_type: Literal[...] = "..."` lines shipped by Phase-4 stories S2-* / S3-* / S6-* and adjust the test imports + literals. If a story is HARDENED-but-not-GREEN and the events have not yet landed, the AC-7/8/10/12/13 tests fail in Red as expected; surface the dependency loudly per Rule 12, do not weaken the AC.
- **Phase-3 vs Phase-4 recipe-refusal event.** Phase 3 today emits `RecipeSkipped(reason: str)` (per `src/codegenie/plugins/events.py`). ADR-0004 introduces a Phase-4-local `PlanOutcome` wrapping `RecipeOutcome`, and may emit a `plan_outcome_emitted` event whose payload's `applied_from_recipe` arm carries the `NotApplicable("MAJOR_BUMP_REFUSE")` projection. AC-6 accepts either shape, but the implementer must pick the one Phase-4 actually emits and remove the other branch — do not assert against both (Rule 7 — surface conflict, do not blend).
- **Plugin-package import path.** The story's snippet uses `plugins.vulnerability_remediation_node_npm` (Python-import style). Plugin packages live under `plugins/<plugin-id>/` and the plugin loader (S2-03) registers them by manifest. Confirm the actual import path the loader exposes at executor time; the import in the snippet may need to be deferred behind the plugin resolver rather than a direct module import.
- **Cassette recording is gated by `make refresh-cassettes --i-understand-this-spends-tokens` (S3-06) + valid keyring entry.** Do not run live API calls inside the test loop; one-time recording is the discipline.
- The `Provenance.AppTransitive` (or similar app-layer) assertion is the most-likely-to-be-skipped guard — without it, a regression in the provenance adapter (S7-03) could turn this test into a silent provenance-refuse passing case where the LLM is never called and the test still "passes" in the wrong way. **Fail loud per Global Rule 12.**
- The "harvested record queryable post-run" assertion is the proof of the Phase-4 exit criterion #1 plus the precondition for exit criterion #2 (S7-07). If the record isn't queryable above `high_floor`, S7-07 cannot succeed — surface loudly.
- The fixture's `tsconfig.json` must produce `tsc --noEmit` exit-code 0 on Express-4 (pre-patch). If `tsc` reports errors on the *baseline*, the `typecheck.typescript` signal's strict-AND will incorrectly flag the post-patch state. Validate this during S7-05 fixture construction, not at E2E time.
- The cassette body has been sanitized by S3-04; even so, do not log `cassette.serialize()` anywhere — keep the response BLAKE3-digested in audit events only (arch §Logging strategy).
- The `LeafInvoked == 1` assertion is the witness that the LLM was actually called — combine with `Provenance.AppTransitive` to rule out the refuse-false-positive failure mode.
- If the test passes on first replay but fails on second replay, the cassette is being mutated mid-test (a bug in S3-04 or `pytest-recording`); surface immediately per Global Rule 12.
- **Extension-by-addition rent (DP-H-4).** S7-07 will mirror this story's scaffolding for the cache-hit case; S7-09 may add a third E2E for the adversarial-corpus path. The discipline: adding any future Phase-4 E2E test must require **zero edits** to `tests/integration/_phase4_e2e_helpers.py` (Open/Closed at the file boundary). If a third sibling needs a new helper, add a new function — do not generalize an existing one until a *fourth* consumer crosses the rule-of-three again.
