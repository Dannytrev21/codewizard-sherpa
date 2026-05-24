# Validation report — S7-06 E2E breaking-change exit criterion #1

**Validator:** `phase-story-validator` skill
**Date:** 2026-05-24
**Story file:** `docs/phases/04-vuln-llm-fallback-rag/stories/S7-06-e2e-breaking-change.md`
**Verdict:** HARDENED

---

## Context brief

S7-06 is the headline Phase-4 roadmap exit-criterion test — a breaking-change CVE (Express 4→5 on the `express-cve-2026-1234` fixture from S7-05) running end-to-end through the dispatch: provenance gate → Phase-3 recipe (refuses with `MAJOR_BUMP_REFUSE`) → Phase-4 FallbackTier → LLM via cassette replay → strict-AND with `typecheck.typescript` → inline harvest (confidence gate per ADR-0009). The story file lands a single integration test plus its cassette + lock entry. Test is cassette-replayed in CI; live recording is operator-gated.

ADRs in scope: ADR-0001 (PlanProposal sum type), ADR-0004 (PlanOutcome wraps RecipeOutcome), ADR-0008 (two-threshold band), ADR-0009 (inline harvest confidence gate), ADR-0012 (provenance gate as tier-0), ADR-0014 (cassette discipline), ADR-0015 (`typecheck.typescript` SignalKind), ADR-0017 (AttemptAnchor event schema).

Phase-3 precedent: `tests/integration/test_end_to_end_express_cve.py` from Phase-3 S8-02 (HARDENED) — the masking-helper, CliRunner-not-subprocess, typed-event-parsing, fail-loud-on-missing-jail conventions.

---

## Stage 2 — Critic findings

### Coverage critic (CO)

| # | Severity | Finding |
|---|---|---|
| CO-H-1 | harden | `assert outcome.score >= 0.85` hardcodes the threshold; ADR-0008 names `plugin.yaml` as source of truth (`high_floor` default 0.85). A floor change in plugin.yaml would silently drift from the test. **Fix:** load `high_floor` from `plugins/.../plugin.yaml` at test time. |
| CO-H-2 | harden | Plan-shape assertion checks the wrapping `applied_from_llm` discriminator but not the wrapped `PlanProposal` variant. Express 4→5 is structurally a `callsite_rewrite`; a regression where the LLM emits `dep_bump` (and somehow validation passes) would not be caught. **Fix:** assert `PlanProposal.kind == "callsite_rewrite"` per ADR-0001. |
| CO-H-3 | harden | ADR-0009 fires `SolvedExampleHarvested` on the high-confidence path and `HarvestSkipped(reason=low_confidence)` on medium-confidence; both events are mutually exclusive. Story asserts the positive fire but not the negative. A regression where both fire (or neither does) would pass silently. **Fix:** add an event-absence assertion for `HarvestSkipped`. |
| CO-H-4 | harden | Per-AC event presence checks ignore order. A regression where `solved_example_harvested` fires before `trust_outcome_emitted` (an obviously wrong dispatch) would still pass. **Fix:** assert canonical dispatch order by index. |

### Test-quality critic (TQ)

| # | Severity | Finding |
|---|---|---|
| TQ-H-1 | harden | `r.get("outcome", {}).get("kind") == "not_applicable" and "major" in r.get("outcome", {}).get("reason", "").lower()` is substring matching — would pass on `"this is not a major refuse"` or any string containing "major". Need exact literal match against `NotApplicableReason` (`"MAJOR_BUMP_REFUSE"`). |
| TQ-H-2 | harden | Test parses events as raw `dict` and uses `.get(...).get(...)` shuffling. CLAUDE.md (load-bearing): "no untyped `dict` shuffling." Phase-3 S8-02 precedent: parse each line into typed `WorkflowInternalEvent` discriminated-union variant. **Fix:** use `pydantic.TypeAdapter(WorkflowInternalEvent).validate_json(line)`. |
| TQ-H-3 | harden | "Cassette in `cassettes.lock` with BLAKE3" is policed by a separate CI scanner; nothing in *this* test would catch a contributor regenerating without updating the lock. **Fix:** assert `BLAKE3(cassette_bytes) == lock_entry` at test start, fail-loud with `make refresh-cassettes` pointer. |
| TQ-H-4 | harden | "Run twice and compare bytes" inlined into the main test function — a determinism regression would surface mixed in with happy-path assertions. **Fix:** split into `test_phase4_e2e_breaking_change_determinism` with its own AC + diagnostic. |
| TQ-N-5 | nit | The 10× flake-check is described as Refactor-step manual; `pytest-repeat` (`--count=10`) is the idiomatic automation — noted. |

### Consistency critic (CN)

| # | Severity | Finding |
|---|---|---|
| CN-B-1 | **block** | Test code uses `e["kind"] == "ProvenanceClassified"` etc. Repo convention (verified in `src/codegenie/plugins/events.py`): discriminator key is `event_type:` and literals are snake_case (`"provenance_classified"`, `"recipe_skipped"`, etc.). Original `e["kind"]` would find nothing — every assertion silently passes on an empty `[]`. |
| CN-B-2 | **block** | Provenance literals listed as `{"AppDirect", "AppTransitive", "AppVendored", "Both"}` (PascalCase). S2-01 HARDENED to lowercase snake_case `{"app_direct", "app_transitive", "app_vendored", "both"}`. Test would never match. **Fix:** import `_APP_LAYER_PROVENANCE_KINDS` from `codegenie.fallback.provenance_gate`; do not duplicate. |
| CN-B-3 | **block** | `outcome.kind == "rag_hit"` — S1-04 HARDENED `RetrievalOutcome` to discriminator literals `"hit"`, `"miss"`, `"degraded"` per `Field(discriminator="kind")`. Test would always fail. |
| CN-B-4 | **block** | Story references `RecipeOutcomeEmitted` event with `kind="not_applicable"` and `reason="major_bump_breaking_change"`. Verified: (a) no `RecipeOutcomeEmitted` event class in `src/codegenie/plugins/events.py` — Phase 3 emits `RecipeSkipped(reason: str)`; (b) `NotApplicableReason` literal is `MAJOR_BUMP_REFUSE` (UPPER_SNAKE), not `major_bump_breaking_change`. Either fix to the Phase-3 shape, OR have Phase 4 ship a wrapping `plan_outcome_emitted` event per ADR-0004 and document that here. |
| CN-H-1 | harden | ADR-0017 puts `AttemptAnchor` family events (including `LlmCostAccrued`) in the **spanning** stream. Story reads only `.codegenie/events/workflow-internal/`. Cost assertion would never find the event. **Fix:** read both streams via the typed helper. |
| CN-H-2 | harden | ADR-0015 places `tsc` baseline at `.codegenie/typecheck/baseline-<repo-sha>.json`; not asserted that it lands inside `tmp_path` (hermeticity gap). |
| CN-H-3 | harden | "Linux/macOS" jail-binary fail-loud is generic. On Linux the missing binary is `bwrap`; on macOS it is `sandbox-exec` (per Phase 3 ADR-0007). Each platform should raise with a platform-specific message. |

### Design-patterns critic (DP)

| # | Severity | Finding |
|---|---|---|
| DP-B-1 | **block** | Dict-shuffling event filter (`r.get("outcome", {}).get("kind")`) violates CLAUDE.md load-bearing commitment and Phase-3 S8-02 typed-discriminated-union precedent. Same finding as TQ-H-2 from a design-pattern lens: tagged-union dispatch over a `match evt:` is the correct shape; untyped dict lookup is anti-pattern. |
| DP-H-1 | harden | Provenance kind set duplicated as a string literal in the test instead of importing `_APP_LAYER_PROVENANCE_KINDS` (the named Specification per ADR-0012). Same root cause as CN-B-2 (DRY / single-source). |
| DP-H-2 | harden | `high_floor` duplicated as `0.85` in test; ADR-0008 names plugin.yaml as the source. Configuration-as-data + single-source-of-truth violation. |
| DP-H-3 | harden | Helper module deferred to Refactor, but rule-of-three is crossed within this story (event parsing, plan-outcome assert, harvest assert, cost assert, determinism rerun all share the typed parser) plus S7-07 immediately consuming. **Fix:** ship helper module in Red; surface as observable AC-18. |
| DP-H-4 | harden | No extension-by-addition rent specified. Future Phase-4 E2E siblings (S7-07, S7-09) must extend by adding test files, not by editing the helper module. Surface as observable constraint in Notes (Open/Closed at the file boundary). |
| DP-N-5 | nit | Module-level `FIXTURE` / `CASSETTE` should be `Final[Path]` for mypy hygiene (minor). |

### NEEDS RESEARCH

None. Every finding is anchored in existing source-tree constants, repo-convention precedents (Phase-3 S8-02 hardened story), or already-HARDENED Phase-4 sibling stories (S2-01, S1-04). No external canonical-pattern lookup needed.

---

## Stage 4 — Synthesis + edits applied

Edits land in the story file under headings:

- **Validation notes** (appended after the metadata block): 16 numbered items mapping each fix to the critic finding and severity that motivated it.
- **Acceptance criteria**: rewritten and re-numbered as AC-1 through AC-20. The original 16 unnamed bullets collapsed and re-issued with: imported constants instead of duplicated literals (AC-5, AC-11); typed-event parsing AC (AC-15); per-platform fail-loud (AC-16); event-absence companions (AC-10); spanning-stream cost lookup (AC-12); dispatch-order assertion (AC-13); separate determinism test (AC-14); helper-module-from-Red AC (AC-18).
- **TDD plan — Red**: rewritten to use typed pydantic `WorkflowInternalEvent` imports, `_APP_LAYER_PROVENANCE_KINDS` import-and-membership, `high_floor` read from plugin.yaml, snake_case event-type literals, two test functions (happy path + determinism), platform-specific jail-binary check, in-test cassette/lock hash comparison. Conventions-reminder block prepended above the snippet citing each load-bearing literal.
- **TDD plan — Refactor**: clarified that the helper module is shipped in Red (not Refactor); added the per-helper unit-test step (mirroring S8-02 AC-13); added pytest-repeat flake check guidance.
- **Files to touch**: added `tests/integration/_phase4_e2e_helpers.py` (NEW) and `tests/integration/test__phase4_e2e_helpers.py` (NEW); noted these are the kernel that S7-07 and future siblings extend by addition.
- **Notes for the implementer**: appended four notes — (a) verify event-type literals against source at executor time; (b) Phase-3 vs Phase-4 recipe-refusal event ambiguity (do not blend, pick one); (c) plugin import-path ambiguity; (d) extension-by-addition rent for future siblings.

No edit to the **Goal** section. Goal (a)–(i) is intact; we only sharpened the verifications.

### Conflict resolution

- DP-H-1 (DRY, import the constant) vs. CN-B-2 (literals are wrong as written) — both same root, Consistency-win takes precedence: use the imported constant; that fixes both findings simultaneously.
- TQ-H-2 / DP-B-1 (typed events vs dict-shuffle) — agreed; CLAUDE.md commitment + Phase-3 precedent both say typed-event parsing. Applied.
- CO-H-2 (assert `callsite_rewrite`) vs Rule 2 (no speculative checks) — not speculative: ADR-0009 + ADR-0001 + Phase-arch §Scenario 2 all name the callsite-rewrite shape as the *whole point* of the breaking-change path. Coverage-win.

### What was NOT changed

- **Goal section** — unchanged. Intent is correct.
- **Scope** — out-of-scope items left intact (S7-07 cache-hit, S7-09 adversarial, golden-file masking).
- **No new ACs for hypothetical futures** (Rule 2). Every new AC traces to an existing ADR or load-bearing commitment.

---

## Verdict

**HARDENED.** Story now has: typed event parsing throughout; every discriminator literal sourced from production code (not duplicated); cassette-vs-lock integrity check inside the test; per-platform fail-loud; spanning-stream cost capture; event-presence-AND-absence assertions for the harvest gate; dispatch-order assertion; explicit `callsite_rewrite` plan-shape; helper module promoted to Red with Open/Closed extension-by-addition rent; separate determinism test function.

A regression that:
- Skips the provenance gate → AC-5 fails (no `ProvenanceClassified` event with app-layer kind).
- Inverts the recipe refusal logic → AC-6 fails (`MAJOR_BUMP_REFUSE` literal absent).
- Calls the LLM twice on a retry path → AC-7's `len == 1` fails.
- Emits `dep_bump` instead of `callsite_rewrite` → AC-8 fails.
- Flips the confidence gate (low-confidence yet harvests) → AC-10's `HarvestSkipped == 0` may fail depending on regression shape; combined positive+negative assertions catch the gate.
- Reads `high_floor` from a stale hardcoded constant → AC-11 self-adjusts to plugin.yaml.
- Reorders the dispatch (harvest before validate) → AC-13 fails.
- Mutates state between two runs (nondeterminism in lockfile/branch ID) → AC-14 fails with its own diagnostic.
- Regenerates the cassette without updating the lock → AC-3 fails-loud at test start.
- Shuffles fields in raw dicts when the schema changes → AC-15 fails at `validate_json`.
- Duplicates `_APP_LAYER_PROVENANCE_KINDS` and the test forgets to update → AC-5 import fails.

The story is ready for `phase-story-executor`.
