# Validation report — S7-07 E2E replay-lands-RAG exit criterion #2

**Validator:** `phase-story-validator` skill
**Date:** 2026-05-24
**Story file:** `docs/phases/04-vuln-llm-fallback-rag/stories/S7-07-e2e-replay-lands-rag.md`
**Verdict:** HARDENED

---

## Context brief

S7-07 is the second Phase-4 roadmap exit-criterion test — same-CVE rerun must hit RAG, shape a cheaper LLM call via the seeded few-shot, and the harvest dedup branch must skip writing (since the seed is already in the store). Tests `tests/integration/test_phase4_e2e_replay_lands_rag.py` end-to-end against `tests/fixtures/repos/express-rerun/` (S7-05's pre-seeded fixture) with **no operator step between runs**. Cost-delta baseline is captured hermetically by replaying S7-06's cassette inside the test (option (a)). Two streams matter: workflow-internal for the deterministic dispatch chain; spanning for `LlmCostAccrued` (ADR-04-0017).

ADRs in scope: ADR-04-0008 (two-threshold band; `high_floor` in `plugin.yaml`), ADR-04-0009 (inline harvest with confidence gate; "no operator step between runs" framing), ADR-04-0017 (`AttemptAnchor` family in spanning stream), production ADR-0034 (event sourcing).

Sibling lineage carrying convention forward: **S7-06 (HARDENED 2026-05-24)** ships `_phase4_e2e_helpers.py` as the kernel — typed-event parsing, BLAKE3 cassette/lock integrity check, per-platform jail fail-loud, spanning-stream cost capture, dispatch-order-by-index, determinism in a separate test function, Open/Closed at the file boundary. S7-07 mirrors every one. **S6-03 (HARDENED)** ships the harvest hook with caller-side dedup (`HarvestSkipped(reason="already_harvested")`, closed-set reason literal). **S5-01 (HARDENED)** ships `RagHitEvent`/`RagDegradedEvent`/`RagMissEvent`/`RagCandidateSelectedEvent` with snake_case `event_type` discriminators and payloads (`record_id`, `score`). **S1-04 (HARDENED)** ships `RetrievalOutcome` discriminator `kind: Literal["hit","miss","degraded"]` and `SolvedExample.id: SolvedExampleId`. **S7-05 (HARDENED)** ships `express-rerun/` with AC-11 pinning `embedding_model == codegenie.rag.embeddings.MODEL_DIGEST`.

---

## Stage 2 — Critic findings

### Coverage critic (CO)

| # | Severity | Finding |
|---|---|---|
| CO-1 | harden | `score >= 0.85` hardcodes `high_floor`; ADR-04-0008 names `plugin.yaml` as source. Same as S7-06 CO-H-1. **Fix:** read via `_load_high_floor(PLUGIN_YAML)`. |
| CO-2 | **block** | Event class `RagHitClassified` does not exist. S5-01 HARDENED AC-14 ships `RagHitEvent` / `RagDegradedEvent` / `RagMissEvent` / `RagCandidateSelectedEvent`. Test would silently filter to `[]` and every dependent assertion would no-op. |
| CO-3 | **block** | `RagHitClassified.matched_record.solved_example_id` is not the shape. S5-01 line 220 emits `RagHitEvent(record_id=record.id, score=score, ...)`. The matched record's identity is `record_id` (`SolvedExampleId`). Test would fail at attribute access even after CO-2 is fixed. |
| CO-4 | block | `LeafInvoked` event-class name unverified; placeholder. Verify at executor time. |
| CO-5 | **block** | `TrustOutcome.confidence == "high"` is correct literal but `Literal["high","medium","low"]` is design-doc drift; shipped is `Literal["high","degraded"]` per `src/codegenie/transforms/outcomes.py:403` (S6-03 HARDENED). Goal item (h) accidentally implies the three-value set. |
| CO-6 | **block** | `HarvestSkipped(reason="already_present")` — `"already_present"` is not in S6-03's closed-set `Literal[...]`. Closed set is `{"already_harvested","low_confidence","trust_failed","outcome_not_harvestable"}`. S6-03 ships dedup unconditionally (AC-7 step 3, AC-8); the assertion is single-branch. |
| CO-7 | harden | `LlmCostAccrued` lives in **spanning** stream per ADR-04-0017; test reads workflow-internal only. Same as S7-06 CN-H-1. Cost assertion would silently never find the event. |
| CO-8 | harden | No event-absence companion for the harvest branch — a regression where BOTH `solved_example_harvested` AND `harvest_skipped` fire (or neither) would pass. Mirrors S7-06 CO-H-3. |
| CO-9 | harden | Only `idx_rag < idx_leaf` asserted; full dispatch order across the chain (provenance → rag_hit → rag_candidate_selected → leaf_invoked → leaf_returned → plan_outcome_emitted → trust_outcome_emitted → harvest_skipped) is not pinned. Mirrors S7-06 CO-H-4. |
| CO-10 | harden | No event-absence assertion for `RagDegradedEvent` / `RagMissEvent` on the happy path (the seed is by construction high-confidence). |
| CO-11 | harden | `run_first_run_for_baseline(tmp_path)` does not exist in S7-06's HARDENED helper-module exports. Story must extend `_phase4_e2e_helpers.py` by addition (mirror S7-06 AC-18) without editing kernel helpers. |
| CO-12 | harden | No assertion on `RagCandidateSelectedEvent` (S5-01 AC-14); its presence is the witness that the selected `FencedSegment` reached prompt assembly. |
| CO-13 | harden | No cassette/lock BLAKE3 integrity check inside the test (only "exists + in lock"). Same as S7-06 TQ-H-3. |
| CO-14 | harden | Determinism guard inlined into the main test function. Mirrors S7-06 AC-14 / TQ-H-4 — split into separate test. |
| CO-15 | harden | `system_blocks_count == 3` AND "acceptable alternative `system_blocks_metadata` array of length 3" — parallel implementations. Per Rule 7, pick one; surface as blocker if neither shipped. |

### Test-quality critic (TQ)

| # | Severity | Finding |
|---|---|---|
| TQ-1 | **block** | `parse_events(...)` returns dicts (snippet uses `e["kind"] == "..."`). CLAUDE.md "no untyped `dict` shuffling" load-bearing commitment + Phase-3 S8-02 + S7-06 AC-15 precedent: typed `WorkflowInternalEvent | WorkflowSpanningEvent` parsing via `pydantic.TypeAdapter`. |
| TQ-2 | harden | `_read_seeded_record_id()` uses `yaml.safe_load` to bare dict. S1-04 / S4-04 ship `SolvedExample.from_yaml` — use the typed path. |
| TQ-3 | harden | `assert first_run_dollars > 0` is a tautology (any cassette response has cost). Capture typed `LlmCostAccrued` event and assert `tokens_total > 0` AND `dollars > 0`. |
| TQ-4 | harden | `assert "rag_harvest_cli" not in src` is brittle (a future variable rename evades). Extend to scan substring + import + subprocess invocation (rule-of-three: same defense for S7-09). |
| TQ-5 | harden | Test runs CLI twice (baseline + rerun) but the snippet doesn't pin which cassette `vcr` replays for which invocation. Be explicit in the helper. |
| TQ-6 | harden | `RagHit before LeafInvoked`: assert by INDEX in single-threaded stream (the indices are the spec, not the timestamps). |

### Consistency critic (CN)

| # | Severity | Finding |
|---|---|---|
| CN-1 | **block** | `RagHitClassified` ≠ `RagHitEvent` (S5-01 HARDENED). Same root as CO-2 from a consistency lens. |
| CN-2 | **block** | `matched_record.solved_example_id` ≠ `record_id`. Same root as CO-3. |
| CN-3 | **block** | `"already_present"` ∉ `HarvestSkipped.reason` closed set. Same root as CO-6. |
| CN-4 | harden | `LlmCostAccrued` stream location (spanning). Same as CO-7. |
| CN-5 | harden | Per-platform jail-binary fail-loud language present in narrative but absent from snippet. Mirror S7-06 AC-16 exactly. |
| CN-6 | harden | `0.85` literal duplicated; ADR-04-0008 source of truth. |
| CN-7 | harden | `make refresh-cassettes` incantation should mirror S7-06: `make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1`. |
| CN-8 | harden | `any(seed_dir.glob("*.yaml"))` — S7-05 ships exactly one record; assert `== 1` and load via typed model. |
| CN-9 | harden | No assertion that no `RagDegraded` event fired (low-confidence prompt-tag path); add event-absence companion. |

### Design-patterns critic (DP)

| # | Severity | Finding |
|---|---|---|
| DP-1 | **block** | Dict-shuffling event filter. Same root as TQ-1; tagged-union `match evt:` over typed events is the correct shape per CLAUDE.md + Phase-3 S8-02 + S7-06 precedent. |
| DP-2 | harden | Cost-baseline helper does not exist; extending S7-06's helper module is the right move, but it must be **additive only** — no edits to kernel helpers. Open/Closed at the file boundary. |
| DP-3 | harden | `high_floor` duplicated literal; configuration-as-data + single-source. Same root as CN-6. |
| DP-4 | harden | Goal item (h) presents two parallel implementations ("if S6-03 dedups vs if not"). S6-03 HARDENED ships dedup unconditionally; per Rule 7, collapse to the single branch. |
| DP-5 | harden | AC-7 presents two assertion shapes (`system_blocks_count == 3` vs `system_blocks_metadata: tuple` length-3). Per Rule 7, pick one; surface as blocker if neither shipped. |
| DP-6 | harden | Extension-by-addition rent absent. Future S7-09 (adversarial) must extend the helper module without editing existing function bodies. Surface as observable AC mirroring S7-06 AC-18 / DP-H-4. |
| DP-7 | nit | Module-level constants should be `Final[Path]` (mypy hygiene); mirror S7-06. |
| DP-8 | harden | The static-text guard for "no operator harvest" belongs in a helper (`_assert_no_operator_harvest_invocation`) — rule-of-three: S7-09 will have the same risk. |

### NEEDS RESEARCH

None. Every finding anchored in:
- shipped sibling-story validation reports (S7-06 HARDENED, S6-03 HARDENED, S5-01 HARDENED, S1-04 HARDENED, S7-05 HARDENED)
- referenced ADRs (ADR-04-0008, ADR-04-0009, ADR-04-0017)
- CLAUDE.md load-bearing commitments
- Global Rules (7 — surface conflicts, 9 — tests verify intent, 11 — match conventions, 12 — fail loud)

---

## Stage 4 — Synthesis + edits applied

Edits land in the story file under these headings:

- **Status:** flipped `Ready` → `HARDENED`.
- **Depends on / ADRs honored:** widened with the verified sibling-story HARDENED references and the corrected `Literal[...]` shapes.
- **Validation notes:** new block with 19 numbered items mapping each fix to the critic finding(s) that motivated it.
- **Context:** rewritten to use the correct event-class names (`RagHitEvent`, etc.) and the correct closed-set literal (`"already_harvested"`); replaced "either (a) or (b)" cost-baseline framing with the single-branch (a) per Rule 7; pinned `high_floor` as `plugin.yaml`-sourced; pinned `LlmCostAccrued` as spanning-stream per ADR-04-0017.
- **References — where to look:** added pointers to the HARDENED sibling stories (S7-06, S6-03, S5-01, S1-04, S7-05) plus the source-of-truth files (`src/codegenie/plugins/events.py`, `src/codegenie/transforms/outcomes.py:403`).
- **Goal:** rewritten to a single concrete contract (no parallel "if X / else Y" branches); pinned the cost-baseline mechanism; named the extension-by-addition rent for `_phase4_e2e_helpers.py`.
- **Acceptance criteria:** rewritten and re-numbered as AC-1 through AC-24. The original 12 unnamed bullets collapsed and re-issued with:
  - typed-event parsing across the board (AC-22)
  - typed seeded-record load via `SolvedExample.from_yaml` (AC-2)
  - cassette/lock BLAKE3 integrity check for BOTH cassettes (AC-3)
  - `high_floor` from `plugin.yaml` (AC-5)
  - corrected event-class names (`RagHitEvent`, `RagCandidateSelectedEvent`, `LeafInvoked`, `TrustOutcomeEmitted`, `HarvestSkipped`, `SolvedExampleHarvested`, `LlmCostAccrued`) (AC-6, AC-7, AC-9, AC-12, AC-14, AC-15, AC-16)
  - corrected `HarvestSkipped.reason="already_harvested"` literal (AC-15)
  - event-absence companions for `RagDegradedEvent`/`RagMissEvent` (AC-8) and `SolvedExampleHarvested` (AC-16)
  - dispatch-order by index across full chain (AC-17)
  - cost capture from **spanning** stream (AC-12)
  - first-run baseline strengthened to typed event + non-zero tokens (AC-13)
  - extended no-operator-harvest guard via helper (AC-11; helper added per AC-18)
  - helper-module additive-only extension as observable rent (AC-18)
  - determinism in a separate test function (AC-19)
  - per-platform fail-loud mirroring S7-06 AC-16 (AC-20)
  - cassette regeneration docstring incantation (AC-21)
- **Implementation outline:** rewritten with explicit "read first" preamble naming the HARDENED siblings to consult; clarified that helper extension is appended-only; named the recording precondition (seed must be present during live recording — else cassette captures wrong shape).
- **TDD plan — Red:** rewritten with a Conventions-reminder block citing each load-bearing literal; typed imports; per-platform jail-binary check; in-test cassette/lock hash comparison; two test functions (happy path + determinism); typed event assertions throughout; dispatch-order assertion across the canonical class chain.
- **TDD plan — Green:** clarified that the three new helpers are appended to `_phase4_e2e_helpers.py`; kernel-helper bodies stay frozen; companion tests in `test__phase4_e2e_helpers.py` parametrize new helpers alongside kernel.
- **TDD plan — Refactor:** added the executor-time event-class-name verification step; pytest-repeat flake check.
- **Files to touch:** added `tests/integration/_phase4_e2e_helpers.py` (EXT — append only), `tests/integration/test__phase4_e2e_helpers.py` (EXT), and the baseline-cassette dependency note for `cassettes.lock`.
- **Out of scope:** added "Refactoring or amending S7-06's kernel helpers — additive only (AC-18 Open/Closed rent)".
- **Notes for the implementer:** added six notes — (a) operator-step framing for ADR-04-0009; (b) cost-delta flake envelope; (c) `RagHitEvent before LeafInvoked` witness for named-sequential dispatch; (d) `system_blocks_count` Rule-7 escape path; (e) S6-03 dedup is shipped — no parallel branch; (f) event-class-name verification at executor time; (g) Open/Closed extension contract for S7-09; (h) Phase-3 vs Phase-4 recipe-refusal event ambiguity (carried forward from S7-06 Notes).

No edit to the **Goal**'s intent — same scenario, same exit criterion. Only the *mechanics* (event names, literal values, stream locations, helper module shape, parallel-implementation collapse) were sharpened.

### Conflict resolution

- **DP-4 (collapse parallel-implementation branches in goal (h)) vs Rule 2 (no speculative scope)** — not speculative; S6-03 HARDENED ships dedup unconditionally, so the "if not dedup" branch was never reachable. Goal narrowed to the single shipped contract; surplus removed. Consistency-win.
- **DP-5 (collapse `system_blocks_count` vs `system_blocks_metadata` alternatives) vs Rule 2** — Per Rule 7, picked the canonical shape (`system_blocks_count` — the cheaper observability assertion); the other is preserved in Notes as the documented Rule-7-resolved fallback path the implementer takes only if S3-02 doesn't yet ship the field.
- **CO-11 (extend helper module) vs DP-2 (Open/Closed; do not edit kernel)** — both same root, no conflict. Extension is additive only (append new functions, leave kernel bodies frozen). New AC-18 makes this observable.
- **TQ-4 (extend static guard) vs DP-8 (move to helper)** — both same root; the helper IS the extension. One AC (AC-11) cites both fixes; AC-18 pins the helper-module discipline.

### What was NOT changed

- **Goal section** — same scenario, same roadmap-exit-criterion intent. Only the mechanics tightened (event names, literal values, stream locations, parallel-implementation collapse).
- **Out-of-scope items** — left intact (S7-06 not re-litigated; calibration is S5-04's job; adversarial is S7-09; Phase-11 webhook out).
- **No new ACs for hypothetical futures** (Rule 2). Every new AC traces to an existing ADR, sibling HARDENED story, or load-bearing CLAUDE.md commitment.

---

## Verdict

**HARDENED.** Story now has:

- Correct event-class names (`RagHitEvent`, `RagCandidateSelectedEvent`, `LeafInvoked`, `TrustOutcomeEmitted`, `HarvestSkipped`, `SolvedExampleHarvested`, `LlmCostAccrued`) verified against S5-01 / S6-03 HARDENED + `src/codegenie/plugins/events.py`.
- Correct closed-set literal (`HarvestSkipped.reason="already_harvested"` per S6-03 HARDENED AC-13) — not the phantom `"already_present"`.
- Correct `TrustOutcome.confidence` shape (`Literal["high","degraded"]` per the actual `src/codegenie/transforms/outcomes.py:403` — design-doc `["high","medium","low"]` drift dropped).
- Correct cost-stream location (`LlmCostAccrued` in **spanning** stream per ADR-04-0017) — workflow-internal-only read fixed.
- Typed-event parsing throughout (no `dict.get` shuffling) — CLAUDE.md load-bearing + S7-06 AC-15 precedent.
- `high_floor` from `plugin.yaml` (not duplicated as `0.85` literal) — ADR-04-0008 source of truth.
- BLAKE3 cassette-vs-lock integrity check inside the test for BOTH cassettes (rerun + baseline).
- Per-platform fail-loud on missing jail binary (Linux `bwrap` / macOS `sandbox-exec`).
- Full dispatch-order assertion across the canonical event chain by index (single-threaded stream).
- Event-absence companions for both the happy-path RAG branch (no degraded, no miss) AND the harvest branch (no `SolvedExampleHarvested` on rerun).
- Helper module extended by addition (three new helpers appended to S7-06's kernel) with Open/Closed-at-the-file-boundary as observable rent (AC-18) — S7-09's future adversarial E2E inherits the same contract.
- Extended no-operator-harvest guard via reusable `_assert_no_operator_harvest_invocation` helper (substring + import + subprocess scan).
- Determinism guard as a separate test function (`test_phase4_e2e_replay_lands_rag_determinism`).
- Goal item (h)'s parallel-implementation hedge collapsed to the single shipped contract per Rule 7.
- `system_blocks_count == 3` assertion shape pinned to one canonical observability path with a documented Rule-7-resolved fallback in Notes-for-implementer if S3-02 doesn't ship the field yet.

The story is ready for `phase-story-executor`. The risks remaining at execution time are (a) verifying the exact `event_type: Literal[...] = "..."` literal strings against `src/codegenie/plugins/events.py` once Phase-4 S3-* / S5-* / S6-* land them (these are placeholder snake_case strings until then) and (b) the Rule-7 escape path on AC-10 (S3-02's `system_blocks_count` field) — both are now surfaced loudly in the story rather than hidden in test scaffolding.
