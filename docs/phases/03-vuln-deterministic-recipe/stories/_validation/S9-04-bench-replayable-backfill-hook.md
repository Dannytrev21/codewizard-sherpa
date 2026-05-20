# Validation report: S9-04 — `BenchReplayable` events + Phase 6.5 backfill hook

**Validated:** 2026-05-20
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S9-04 ships the `BenchReplayablePayload` Pydantic schema, the orchestrator emit site, an integration test that mechanically synthesizes ≥10 Phase 6.5 eval cases from the spanning event stream, and a 1-page operator runbook. Its cardinal promise is Goal G9: Phase 6.5's `codegenie eval backfill` lifts cases **mechanically — no human, no LLM**.

Four parallel critics (Coverage, Test-Quality, Consistency, Design-Patterns) found that the story's *goal* is sound and traces to G9, but the *implementation prescription* was underspecified for that goal in three load-bearing ways:

1. **The prescribed `case.toml` shape contradicted the Phase 6.5 `BenchCase` schema it claims (AC-3.5) to satisfy.** The TDD Green step wrote `[case]\ncve_id=…\nexpected_diff_sha256=…`; Phase 6.5's documented `case.toml` schema (`final-design.md` ~line 274) is `case_id, task_class, disposition, difficulty, source, commit_sha, added_at, last_validated_at`, and a case directory also requires `input/` and `expected/` subdirs. Phase 6.5's loader would have rejected every synthesized case.
2. **The payload could not mechanically populate the required `BenchCase` fields.** `commit_sha` (required for non-curated cases) had no source in the payload; `added_at`/`last_validated_at` had no deterministic source. The story's own Notes already state the rule — "if a field cannot be mapped without inference, the payload schema is missing a field" — but never applied it.
3. **The red test never validated a synthesized `case.toml` against the contract** — it asserted only `len(case_dirs) >= 10`. A synthesizer writing empty/garbage files would have shipped GREEN with the goal silently unmet.

All findings have clear in-place fixes; the goal needs no rewrite. Verdict: **HARDENED**. 33 findings across the four critics (9 tagged `block`, ~25 distinct after de-duplication) — all addressed; the story's AC section was restructured (numbered AC-1…AC-11), the TDD plan rewritten with two red tests, the payload expanded with `commit_sha`, and the implementation outline / Notes corrected.

## Findings by critic

### Coverage critic (12 findings)

- **F1 (block)** — AC set verified directory count, not `BenchCase`-schema conformance; the prescribed `case.toml` omitted every required Phase 6.5 field. Fixed: AC-5.6 now loads + validates every `case.toml` against the vendored contract; Green step rewritten.
- **F2 (block)** — `BenchReplayablePayload` could not mechanically populate 5 of 8 required `BenchCase` fields (`commit_sha`, `difficulty`, timestamps, `disposition` for two outcome kinds). Fixed: `commit_sha` added to AC-1; `difficulty` pinned to a documented mechanical default; timestamps sourced from the event; full `outcome_kind → disposition` mapping pinned (AC-7).
- **F3 (block)** — `input/` and `expected/` subdirs required by Phase 6.5's loader but no AC produced them. Fixed: AC-5.5 + AC-5.6 require and assert both subdirs.
- **F4 (harden)** — `_synthesize_bench_case` required deterministic but timestamps/ordering were not. Fixed: timestamps from `event.timestamp`; AC-5.7 asserts byte-identical idempotence across two runs.
- **F5 (harden)** — emit-count edge cases (E10, loader-phase exits, exit-8) could undercount; the `>=10` floor against a zero-margin 10-fixture portfolio was a coin-flip. Fixed: AC-5.3 pins an exact count with a justification that all 10 fixtures reach the orchestrator, plus an inline-comment rule for future non-emitting fixtures.
- **F6 (harden)** — "emit on every exit path" was asserted only for the four named outcomes, not the crash-before-`transform` exception path. Fixed: AC-3 parametrizes over five exit paths including `exception_before_transform`.
- **F7 (harden)** — `transform_diff_bytes_sha256` empty-value contract ambiguous; the empty branch tested only for `not_applicable`. Fixed: typed `BlobDigest | None`; AC-5.4 asserts the `None` branch for all three non-`validated` kinds.
- **F8 (harden)** — `case_id` collision: two empty-diff `not_applicable` payloads would silently overwrite. Fixed: `case_id` derivation folds in `workflow_id`.
- **F9 (harden)** — `workflow_id` named load-bearing in Context but absent from the payload field list and unreachable by `_synthesize_bench_case(payload)`. Fixed: synthesizer signature changed to take the typed `WorkflowSpanningEvent`.
- **F10 (nit)** — no AC verified runbook content correctness (exit codes / paths). Fixed: AC-8 requires exit codes + paths cross-checked against `cli.py` at write time.
- **F11 (harden)** — vendored `_phase65_contract.py` had no mechanism pinning it to the real schema. Fixed: AC-6 pins the vendored shape to `final-design.md`'s documented schema with a cited comment.
- **F12 (nit)** — no AC pinned that `bench_replayable` lands on the *spanning* stream only. Fixed: AC-4.

### Test-Quality critic (8 findings)

- **F1 (block)** — red test never validated a written `case.toml`; a garbage-writing synthesizer passed. Fixed: AC-5.6 + the rewritten Red 2 test load every `case.toml` through `_phase65_contract.BenchCase`.
- **F2 (block)** — `len(bench_events) >= 10` admits a double-emission bug. Fixed: AC-5.3 asserts exact count `== 10` and one event per distinct `workflow_id`.
- **F3 (block)** — `assert name not in sys.modules` is process-global and session-order-dependent — spuriously fails and falsely passes. Fixed: AC-5.8 rewrites it as a before/after delta scoped to the synthesis loop; Notes cite `test_no_llm_in_transforms.py` discipline.
- **F4 (harden)** — 10 real `npm install` runs: flaky/slow, no skip discipline pinned. Fixed: the story now reuses S8-02's `run_remediate_against_fixture` as-is (inheriting its jail/skip strategy); Notes flag it as a slow integration test and the `--cov-fail-under` interaction.
- **F5 (harden)** — the orchestrator unit-test extension was named but had no red test and no enumerated exit paths. Fixed: TDD plan now has Red 1 — a parametrized orchestrator test over five exit paths.
- **F6 (harden)** — story-named fixtures and `run_remediate_against_fixture` do not exist yet; the red test is not runnable in isolation. Fixed: S8-01/S8-02 added to `Depends on:`; the TDD plan's "why it fails" names the real first failure and the prerequisite.
- **F7 (harden)** — `not_applicable` empty-hash branch claimed in AC but absent from the red test. Fixed: Red 2 asserts the `None`/non-`None` branch per `outcome_kind`.
- **F8 (nit)** — `_synthesize_bench_case` arity inconsistent across AC / red test / Green. Fixed: signature pinned to `_synthesize_bench_case(event, cases_root) -> Path` everywhere.

### Consistency critic (6 findings)

- **F1 (block)** — AC-2's `payload=payload.model_dump()` produces a `None` value (`recipe_id`) that `WorkflowSpanningEvent.payload: dict[str, str|int|bool|float|list[str]]` (arch §C9) forbids. Fixed: emit site pinned to `model_dump(mode="json", exclude_none=True)`; optional fields carry `= None` defaults so the round-trip still reconstructs.
- **F2 (block)** — Green-step `case.toml` shape contradicts the Phase 6.5 `BenchCase` schema. Fixed: Green step + AC-5/AC-6 rewritten to the documented schema.
- **F3 (block)** — `BenchReplayablePayload` missing fields Phase 6.5 requires (`commit_sha`, timestamps, `difficulty`). Fixed: `commit_sha` added; timestamps from the event; `difficulty` a documented default — surfaced per the story's own ADR-0005 rule.
- **F4 (harden)** — `Depends on:` omitted S6-01 (the union) and S6-04 (the emit site this story edits). Fixed: `Depends on:` now `S6-01, S6-04, S8-01, S8-02, S9-02, S9-03`.
- **F5 (harden)** — Refactor note mischaracterized E10 ("universal fallback substitution refused" vs the arch's "concrete plugin fails to load → exit 4 before resolution"). Fixed: Refactor note reworded to the arch's framing; the conclusion (no event) was already correct.
- **F6 (nit)** — runbook honest-framing verified correct; one minor cross-reference cleanup (ADR-0011 assigns `PLUGINS.lock` Sigstore to Phase 11; event-stream anchoring is a separate Phase 16 item — do not conflate). Fixed: AC-8 wording disambiguates the two artifacts.

### Design-Patterns critic (7 findings)

- **F1 (harden)** — primitive obsession: `transform_diff_bytes_sha256: BlobDigest` admits an illegal empty `BlobDigest`. Fixed: typed `BlobDigest | None`; a `@model_validator` ties `not None` to `outcome_kind == "validated"` — illegal states unrepresentable. `recipe_id` consistent.
- **F2 (harden)** — `extra="forbid"` round-trip fragility under `exclude_none`. Fixed: `= None` defaults pinned; AC-5 implicitly exercises the round-trip via `model_validate(e.payload)`.
- **F3 (nit)** — `outcome_kind → disposition` should be a module-level `Final` dict, not a `match` ladder. Surfaced in Notes.
- **F4 (harden)** — `_synthesize_bench_case` tangles the pure mapping with the disk write. Fixed: outline + Notes now prescribe a pure `_bench_case_from_event(event) -> BenchCaseContract` + thin write shell (functional core / imperative shell).
- **F5 (nit, counter-finding)** — do **not** add a `CommitSha` newtype; the repo convention (`index_health.schema.json`) carries commit SHAs as raw `str`. Surfaced in Notes; `commit_sha: str` chosen in AC-1.
- **F6 (nit, counter-finding)** — `_synthesize_bench_case` is correctly test-local; do not promote to `src/`. Surfaced in Notes.
- **F7 (nit)** — raw-`dict` event reads in the test leak untyped-dict shuffling. Fixed: Red 2 reads events as typed `WorkflowSpanningEvent`; Notes reinforce.

## Research briefs

None — no finding was tagged `NEEDS RESEARCH`. Every defect had a concrete in-codebase precedent or a documented schema to align to.

## Conflict resolutions

- **Design-Patterns F2 ("no `exclude_none`, total wire shape") vs Consistency F1 ("`payload` dict forbids `None`").** Consistency wins (source-of-truth: arch §C9 types the dict without `None`). Resolution: emit site uses `model_dump(mode="json", exclude_none=True)`; Design-Patterns F2's legitimate concern (clean round-trip) is preserved by adding `= None` defaults to the optional fields, so the dropped keys reconstruct on `model_validate`.
- **`""`-sentinel (Consistency F1 option a) vs `None` (Design-Patterns F1).** Design-Patterns wins on the field *type*: `BlobDigest`/`RecipeId` are typed identifiers and `""` is an illegal value of each (Rule 7 — do not average two sentinels). Both optional fields are `… | None`.
- **`commit_sha` newtype (implied by primitive-obsession lens) vs raw `str` (Design-Patterns F5).** F5 wins — the repo has an explicit documented convention that commit SHAs are boundary data, not kernel identifiers. No `identifiers.py` change.
- **Effort bump.** Coverage/Consistency findings genuinely expand the surface (`input/`+`expected/` dirs, contract validation, `commit_sha`, the parametrized orchestrator test). Effort raised S → M with a note. This is a scope *clarification*, not scope creep — the goal is unchanged; the original "S" estimate was based on the under-specified version.

## Edits applied

1. **Header** — `Status: Ready → HARDENED`; `Effort: S → M` (with rationale); `Depends on:` expanded to `S6-01, S6-04, S8-01, S8-02, S9-02, S9-03`; `Validation notes` block appended.
2. **Context** — added a `case.toml`-field-to-source mapping table; rewrote the payload field list to include `commit_sha` and clarify `workflow_id`/`timestamp` ride on the event envelope.
3. **References** — Phase 6.5 reference now points at the explicit `case.toml` schema + case-directory contract.
4. **AC-1** — added `commit_sha: str`; `transform_diff_bytes_sha256` → `BlobDigest | None = None`; `recipe_id` → `= None` default; added a cross-field `@model_validator`.
5. **AC-2** — emit pinned to `model_dump(mode="json", exclude_none=True)`.
6. **AC-3 (new)** — exactly-once emission across five exit paths, parametrized orchestrator unit test.
7. **AC-4 (new)** — `bench_replayable` is spanning-stream-only.
8. **AC-5** — integration-test AC rewritten: exact count + distinct-workflow assertion, payload field assertions, `input/`+`expected/` subdirs, contract conformance against the vendored `BenchCase`, determinism/idempotence, scoped before/after `sys.modules` delta.
9. **AC-6 (new)** — vendored `_phase65_contract.py` pinned to `final-design.md`'s documented schema.
10. **AC-7 (new)** — exhaustive pinned `outcome_kind → disposition` mapping.
11. **AC-8** — runbook exit codes/paths cross-checked against `cli.py`; Phase 11 vs Phase 16 Sigstore artifacts disambiguated.
12. **TDD plan** — two red tests (orchestrator parametrized + integration); red-test code rewritten with typed event reads, contract validation, determinism check, scoped LLM check; Green/Refactor rewritten; E10 mischaracterization corrected.
13. **Implementation outline + Files to touch** — updated to the hardened shape.
14. **Notes for the implementer** — added: functional-core/imperative-shell split, `Final`-dict catalog, typed event reads, no-`CommitSha`-newtype, `difficulty` mechanical default, test-local-helper guidance, slow-integration-test caveat; corrected the stale `""`-sentinel note.

## Verdict rationale

HARDENED. The story had nine `block`-severity findings, but every one has a clear in-place fix — none required rewriting the story's *goal*, which traces cleanly to Goal G9 and the High-level-impl Step 9 done-criterion. The defects were concentrated in the implementation prescription (a `case.toml` shape that contradicted the consumer schema, a payload missing fields, a TDD plan that didn't verify its own cardinal AC). That is exactly what the validator's edit pass is for. RESCUE was considered (nine blocks) and rejected: the goal is correct, all ACs trace, no non-goal is implemented.

## Recommended next step

`phase-story-executor` to implement. The executor should start at the Depends-on chain check — S8-01 (10-fixture portfolio) and S8-02 (`run_remediate_against_fixture`) must be on disk before Red 2 is runnable, and S6-01/S6-04 before Red 1. The cardinal AC to keep honest during implementation is **AC-5.6** — every synthesized `case.toml` must `model_validate` against the vendored Phase 6.5 `BenchCase`; a green test without that assertion means the goal is unmet.
