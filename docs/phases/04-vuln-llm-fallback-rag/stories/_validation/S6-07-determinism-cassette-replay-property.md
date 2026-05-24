# Validation report — S6-07 Determinism-under-cassette-replay property test

**Validated:** 2026-05-23
**Validator:** phase-story-validator (scheduled story-validation-corrector run)
**Verdict:** **HARDENED**
**Findings:** 4 block · 14 harden · 4 nit — all resolved in place

---

## Stage 1 — Context Brief

### Story snapshot
- **Goal (verbatim original):** Land `tests/property/test_determinism_under_cassette_replay.py` running `FallbackTier.run` 50 times under cassette replay with a constant four-tuple, asserting byte-identical `Transform.diff_bytes` AND byte-identical event-kind sequence across runs.
- **Phase exit criteria touched:** Phase-arch §Goals G6 (replay); High-level-impl Step 6 Done criterion "Determinism property tests/property/test_determinism_under_cassette_replay.py"; final-design.md line 37 (determinism property at 50 runs); Phase 6.5 bench replay reads this contract; Phase 7 E2E exit criterion #2 (replay-lands-RAG) depends on this property holding.

### Authoritative ADRs
- **ADR-04-0002** — Pipeline; "the chain order *is* the policy"; deterministic when cassette is fixed; every step one audit event — debuggability is a sequence (`Tradeoffs` row 3).
- **ADR-04-0014** — Cassette discipline + `cassettes.lock` BLAKE3 manifest; nightly drift job is the cassette-vs-reality canary; **the determinism property assumes cassette identity is content-addressed.**
- **ADR-04-0008** — Two-threshold band (`RagHit | RagDegraded | RagMiss`); ONNX cross-arch 5th-decimal drift acknowledged; band absorbs it; **the determinism test must skip on cross-arch playback.**
- **ADR-04-0011** — Retry path bypasses RAG; **must be just as deterministic as initial-plan path** (per S6-02 carry-forward).

### Sibling-story lineage (Design-Patterns + Test-Quality carry-forward)
- **S6-01 (HARDENED)** — Ten-event happy-path tape; `make_fallback_tier_for_fixtures(...)` factory; `Sequence[AttemptSummary] = ()`; event registry in `src/codegenie/plugins/events.py` `WorkflowInternalEvent` + `_INTERNAL_CLASSES`; `Counter(kinds)` multiplicity discipline; cross-event payload identity (`PromptBuilt.digest == LeafInvoked.digest`; `BudgetPrecharged.token_id == BudgetReconciled.token_id`).
- **S6-02 (HARDENED)** — Retry-bypass tape with `RagSkippedOnRetry`; `Sequence[AttemptSummary] = ()` truthiness predicate (`bool(prior_attempts)`, not `!= []`); `PromptBuilder` sole-mint discipline; pre-fence-truncation fence test.
- **S4-08 (HARDENED)** — Set the precedent for "1st use, do not extract" rule-of-three discipline applied to test-side helpers.
- **S3-06 (HARDENED — Phase 5)** — `digest_for(name)` kernel pattern (extract on third consumer); **S6-07 is the 1st deterministic-projection consumer** — kernel extract deferred per Rule 2.

### Shipped/declared contracts the story must not contradict
- `make_fallback_tier_for_fixtures(store=..., embedder=...)` factory signature (S6-01 hardened).
- `Sequence[AttemptSummary] = ()` signature on `FallbackTier.run(..., prior_attempts=())` (S6-01/S6-02 hardened — list-literal mutable-default forbidden).
- `EXPECTED_EVENT_COUNT_PER_BRANCH` = 10 for all four branches per S6-01/S6-02 ten-event-tape contract.
- `pyproject.toml` markers: `bench`, `adv`, `phase02_adv` are registered; `determinism` + `platform_recorded` are NEW (this story registers them).
- `tests/cassettes/anthropic/cassettes.lock` is the BLAKE3 manifest (ADR-04-0014) — every cassette this story creates must add an entry.
- `_INTERNAL_CLASSES: Final[tuple[type[BaseModel], ...]]` in `codegenie.plugins.events` — the exhaustiveness fence walks it.

### Phase / arch constraints
- **CLAUDE.md** load-bearing commitments: "Facts, not judgments" (the test reports verdicts, not pass/fail booleans); "Newtype identifiers" (`DeterminismKey` is a Pydantic model, not a tuple); "Functional core / imperative shell" (pure helpers in `tests/_determinism/`); "AST-walking tests enforce" (multiple fence guards).
- **Global Rule 7** — surface conflicts; do not blend. Four-tuple vs eight-tuple constancy: resolved by choosing the broader (eight) and surfacing in Notes-for-implementer.
- **Global Rule 9** — Tests verify intent, not behavior. Diagnostic message must name run-index + event-index + field; sum-type verdict makes failure machine-readable.
- **Global Rule 12** — Fail loud. `ITERATIONS < 20` raises at module import; reduced-iteration runs log via `structlog`; cassette-miss diagnostic names `make refresh-cassettes`.

### Pre-existing state on disk (gap analysis at validation time)
- `src/codegenie/fallback/` does NOT exist yet (S1-01..S6-06 are HARDENED but not GREEN).
- `src/codegenie/rag/` does NOT exist yet.
- `tests/cassettes/anthropic/` does NOT exist yet (S3-03..S3-06 prerequisite).
- `tests/fixtures/fallback_tier_callable.py` does NOT exist yet (S6-01 prerequisite).
- `pytest-recording` is NOT in `pyproject.toml` (S3-01..S3-06 lands it).
- `_INTERNAL_CLASSES` exists in `codegenie.plugins.events` but with Phase-3 entries; S6-01 adds the ten new Phase-4 entries.

**Implication:** S6-07 sits at the end of Step-6 dependency chain. The story is correctly positioned (its `Depends on` line has been updated to include S3-05 + S3-06).

### Open ambiguities (Stage 1 exit gate)
None blocking; all surfaced as Global-Rule-7 Notes-for-implementer:
1. Eight-tuple vs four-tuple — adopted eight; documented in Notes.
2. `RecipeApplication` discriminated-union vs single-attribute shape — carry-forward from S6-01; documented in Notes.
3. `pytest-recording` global vs per-test `record_mode="none"` — depends on S3-04's conftest; documented in Notes.

→ Proceeded to Stage 2.

---

## Stage 2 — Critic findings

### Critic — Coverage (verdict: harden)

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | block | AC4's allowlist is exhaustive against the *original* event shape but not the hardened S6-01 ten-event tape (which carries `token_id`, `prompt_digest_blake3`, `payload_digest_blake3`-shaped fields). | Group B (AC-ENUM-1..-3) replaces allowlist with closed-set `StrEnum`; AC-ENUM-2 fence walks `_INTERNAL_CLASSES` for exhaustiveness. |
| 2 | block | AC3 references `payload_digest_blake3` as an event attribute but no S6-01 event carries it — silently passes if attribute access returns `None`. | Group C (AC-DIGEST-1..-3) clarifies: `_deterministic_digest(event)` is an in-test computed BLAKE3 over `_strip_nondet(event)` canonical bytes. |
| 3 | block | Cross-arch ONNX drift (ADR-04-0008) ignored; the test would pass on the recording arch and fail spuriously on another. | Group G (AC-PLATFORM-1..-2) — `recording_arch.json` sidecar + `_assert_recording_arch_compatible` + `pytest.mark.platform_recorded`. |
| 4 | block | No state-leak detection across iterations; `asyncio.run()` per iteration is necessary but not sufficient — module-level dicts can mutate deterministically. | Group F (AC-FRESH-3) — `_capture_module_state` before/after the loop. |
| 5 | harden | `RagDegraded` and `RagMiss` branches uncovered — determinism is exercised on only the happy `RagHit` path. | Group D (AC-BRANCH-1..-5) — four branches; verdict shape branch-invariant. |
| 6 | harden | Constancy tuple values are not logged or asserted-on at test start; drift mid-test is invisible. | Group A (AC-TUPLE-2) — `key_now == key_initial` per iteration; logged via `structlog`. |
| 7 | harden | Performance dropdown is hand-wavy — arbitrary value silently accepted. | Group M (AC-PERF-1..-3) — closed-set `Literal[20,25,30,40,50]`; warn loud; ≥ 20 hard floor. |
| 8 | harden | No AST property test for `set()`/`dict()` iteration in source modules. | Group J (AC-AST-1) — `tests/fence/test_no_set_iter_in_fallback.py`. |
| 9 | harden | `_first_divergence` signature ambiguous. | Group N (AC-HELPER-1) pins. |
| 10 | harden | Cassette-miss diagnostic unspecified. | AC-LOCK-3 pins exact `make refresh-cassettes` message. |
| 11 | harden | `embedding_model_digest` constancy across iterations not asserted (could be lazy-cached and silently differ). | AC-TUPLE-2 covers; key recomputed per iteration. |

### Critic — Test Quality (verdict: harden)

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | block | Thin assertion `set(diff_bytes for _ in range(50))` reports cardinality, not positional divergence — failure is undiagnosable. | Group H (AC-PARAM-1) + sum-type `CompareReport` with `format_diagnostic()`. |
| 2 | block | `_strip_nondet` is destructive + non-recursive; nested Pydantic models slip through. | Group C (AC-DIGEST-1) — `_to_dict_recursive` handles nesting. |
| 3 | block | No Hypothesis property over input-shape variation — determinism tested on one fixture per branch. | Group K (AC-HYP-1) — `test_determinism_under_cassette_replay_hypothesis.py`. |
| 4 | block | Memoized-`Transform` cheat trivially passes (`return self._cached_transform`). | Group F (AC-FRESH-1..-3) — id-disparity + factory-call-inside-loop AST guard + module-state guard. |
| 5 | harden | `pytest --record-mode=none` configuration not pinned (per-test vs global). | Notes-for-implementer surfaces S3-04 dependency; AC-CLOSE-2 pins lint-imports. |
| 6 | harden | Random sources not seeded. | Group L (AC-SEED-1..-2) — autouse fixture. |
| 7 | harden | Bulk assertion makes pytest reporter useless; per-iteration parametrize is missing. | Group H (AC-PARAM-1) — `@pytest.mark.parametrize("iteration", range(ITERATIONS))`. |
| 8 | harden | No BLAKE3 digest per run captured (catches len-equal-bytes-different mutations). | Group C (AC-DIGEST-3 round-trip identity). |
| 9 | harden | `_diff_runs(...)` ambiguous arity. | Group N (AC-HELPER-2) — `_diff_two_tapes(a, b)` pinned. |
| 10 | nit | Cassette-substring assertions fragile. | Not exercised in this story; surfaced in S6-02 lineage. |

### Critic — Consistency (verdict: harden)

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | block | Four-tuple (phase-arch §Idempetence line 827) vs eight-tuple (final-design.md line 37) — story uses four. | Group A — adopted eight per validator priority (Consistency > Coverage); Notes-for-implementer surfaces with Global Rule 7. |
| 2 | block | Phase-arch §Concurrency (line 269) "single-async-event-loop per workflow" — but AC7 runs `asyncio.run` 50 times. | Resolved by docstring + Notes: concurrency = within-workflow invariant; determinism = across-replay invariant. Two distinct invariants; the test exercises the second. |
| 3 | block | ADR-04-0014 `cassettes.lock` BLAKE3 manifest integration missing. | Group E (AC-LOCK-1..-3). |
| 4 | block | "Event-kind sequence" implied by ADR-04-0002 "every step one audit event — debuggability is a sequence" — original ACs only check digest set, not order. | Group H + Group N + sum-type `EventTapeDiverged(event_index, ...)` — positional order is the contract. |
| 5 | harden | `tests/fixtures/fallback_tier_callable.py` factory signature lock — must match S6-01 hardened `make_fallback_tier_for_fixtures(store=..., embedder=...)`. | Pinned in TDD plan + implementation outline. |
| 6 | harden | Phase 4 merge-gate workflow not named; "in default suite" insufficient. | Group P (AC-MARKER-1..-2) + Notes — `make test-fast` exclusion is the operator boundary; CI matrix routing is out-of-scope. |
| 7 | harden | "≥ 20 floor" not enforced at module import. | AC-CLOSE-3 — `RuntimeError` at module import. |
| 8 | harden | `pprint.pformat` insufficient for big-dict diff per CLAUDE.md fail-loud commitment. | Replaced with `unittest.TestCase.assertDictEqual`-style via `CompareReport.format_diagnostic()`. |
| 9 | nit | "Make refresh-cassettes" workflow ownership ambiguous. | Notes — cassette-steward CODEOWNERS from S3-06; cassette-recording is operator-touch. |

### Critic — Design Patterns (verdict: harden)

**Correct restraint confirmed:** No Capability pattern (test runs in test process; no auth boundary). No Plugin/Strategy abstraction over branches (rule-of-three not reached; four-branch parametrize is fine).

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | block | `Final[tuple[str, ...]]` allowlist — primitive obsession on field names; typos pass mypy. | Group B (AC-ENUM-1..-3) — `StrEnum`. |
| 2 | block | `_strip_nondet` defined in test module — hidden coupling to test-local allowlist. | Extracted to `tests/_determinism/digest.py`; pure; tested in isolation. |
| 3 | block | Pure-impure tangle: ad-hoc assertions mix I/O, async, and verdict — failure is brittle. | Sum-type `CompareReport = AllRunsIdentical \| DiffBytesDiverged \| EventTapeDiverged \| StateLeakDetected` (Pydantic frozen) — make-illegal-states-unrepresentable. |
| 4 | block | `_diff_runs(run_a, run_b) -> str` signature inconsistent with call site (50 tapes vs 2). | Group N (AC-HELPER-1..-3) — `_first_divergence`, `_diff_two_tapes`, `_compare_runs` separated; functional core. |
| 5 | harden | `DeterminismKey` as a Pydantic frozen-extra-forbid model, not a raw tuple — newtype pattern. | Group A (AC-TUPLE-1..-3). |
| 6 | harden | `EventDeterministicProjection.project(event) -> dict` design opportunity — but rule-of-three NOT reached (first deterministic-projection consumer). | Surfaced in Notes-for-implementer as deferred refactor; AC-LATER not introduced (premature abstraction per Rule 2). |
| 7 | harden | Test-side helper coupling — extract to `tests/_determinism/` package. | Done — 6 modules under `tests/_determinism/`. |
| 8 | nit | `pytest-recording` global `record_mode="none"` vs per-test marker. | Surfaced in Notes; depends on S3-04. |

---

## Stage 3 — Researcher

**No `NEEDS RESEARCH` findings were tagged.** Critics had sufficient framing from:
- Hypothesis property-test idioms (already in repo, e.g., `tests/property/test_runtime_trace_freshness_purity.py`).
- Sum-type verdict pattern (S3-06 sibling — `DigestPresent | DigestPlaceholder | DigestKeyMissing | DigestFileMissing`).
- AST-walking fence pattern (multiple precedents in `tests/fence/`).
- `StrEnum` allowlist pattern (S3-06 — `SandboxHealthReason`).
- BLAKE3 content-addressed manifest (`cassettes.lock` per ADR-04-0014; `digests.yaml` per Phase 5 S3-05).

Stage 3 skipped per skill spec ("research without a question is token-burn").

---

## Stage 4 — Synthesizer / Editor — edits applied

**Story header:**
- Status: `Ready` → `HARDENED`
- `Depends on`: added S3-05 (cassettes.lock) + S3-06 (refresh-cassettes operator workflow)
- `ADRs honored`: added ADR-04-0011 (retry-bypass determinism); added phrasing from ADR-04-0002 §Tradeoffs ("every step one audit event")
- Inserted `## Validation notes (phase-story-validator v1, 2026-05-23)` block with 18 numbered changes.

**Acceptance criteria:** Replaced the 9 loose ACs with 17 grouped ACs across 17 groups (A through Q) totalling ~40 individually-verifiable predicates. Every AC names the file/symbol/observable it constrains; every AC traces back to the goal "byte-identical outputs across 50 cassette replays" via at least one of: constancy contract (A), allowlist exhaustiveness (B), digest correctness (C), branch coverage (D), cassette integrity (E), fresh-tier (F), platform compatibility (G), per-iteration isolation (H), cross-event identity (I), source-module hygiene (J), input-variation robustness (K), seed discipline (L), perf budget (M), helper signatures (N), event count (O), suite routing (P), closing invariants (Q).

**Implementation outline:** Restructured around the new `tests/_determinism/` package; six pure modules (`nondet_fields`, `digest`, `compare`, `key`, `module_state`, `recording_arch`); the test file is composition only.

**TDD plan:** Six new test files + nine sub-tests showing each AC's failing-test shape:
1. `tests/unit/test_determinism_compare.py` — `CompareReport` variants in isolation (pure unit tests).
2. `tests/property/test_determinism_under_cassette_replay.py` — the main per-branch parametrized property.
3. `tests/property/test_determinism_verdict_shape.py` — branch-invariant verdict.
4. `tests/property/test_determinism_under_cassette_replay_hypothesis.py` — input-shape variation.
5. `tests/property/test_determinism_identity_invariants.py` — cross-event payload identity.
6. `tests/fence/test_determinism_allowlist_exhaustive.py` — `_INTERNAL_CLASSES` walker.
7. `tests/fence/test_no_set_iter_in_fallback.py` — AST source-module guard.
8. `tests/fence/test_tier_constructed_per_iteration.py` — AST factory-in-loop guard.
9. `tests/fence/test_determinism_helpers_pure.py` — AST purity of helpers.

**Files-to-touch:** Expanded from 5 entries to 22 — covers the new helper package, four cassette directories with recording-arch sidecars, `cassettes.lock` update, `pyproject.toml` marker registration, `Makefile` `test-fast` target.

**Out-of-scope:** Added "per-event `nondet_fields` migration" (rule-of-three deferred); "CI matrix configuration" (operator concern); kept S7-06/S7-07 + Phase 6.5 dependencies as before.

**Notes-for-implementer:** Expanded from 7 bullets to 11 — adds the Global-Rule-7 surfacing for the four-vs-eight-tuple, the `RecipeApplication`-shape carry-forward from S6-01, the rule-of-three deferred refactor reasoning, and the `pytest-recording` configuration dependency on S3-04.

---

## Conflict resolutions (priority: Consistency > Coverage > Test-Quality > Design-Patterns)

| Conflict | Resolution | Rationale |
|---|---|---|
| **Four-tuple vs eight-tuple constancy** (arch §Idempotence vs final-design.md line 37) | Adopted eight-tuple. | Consistency > Coverage; final-design is the broader source-of-truth for determinism property scope. Notes-for-implementer surfaces per Rule 7. |
| **Default-suite (AC9 original) vs `-m bench` exclusion + dev iteration friction** (Consistency #6) | Split: `rag_hit` in default suite; `rag_degraded`/`rag_miss`/`retry_bypass` under new `@pytest.mark.determinism` marker. | Consistency > Test-Quality; `make test-fast` exists for dev iteration; CI runs both lanes. |
| **`pytest-recording` per-test vs global** (Consistency #5) | Depends on S3-04 conftest; surfaced in Notes. | Test-Quality < Consistency; do not silently pick. |
| **`EventDeterministicProjection` design opportunity vs YAGNI** (Design-Patterns #6) | Deferred — first consumer; rule-of-three not reached. | Rule 2 wins over premature abstraction. Pattern surfaced in Notes; AC-LATER not introduced. |
| **`pprint.pformat` (TDD plan) vs CLAUDE.md fail-loud** | Replaced with `unittest.TestCase.assertDictEqual`-style structured diff via `CompareReport.format_diagnostic()`. | Consistency > Test-Quality. |
| **`asyncio.run` per iteration vs §Concurrency single-loop invariant** | Documented as intentional in the test docstring: two different invariants. | Surfaced in Notes; AC docstring pins. |

---

## Final verdict

**HARDENED.** Story now constrains a correct implementation:

- Every AC is individually verifiable: 40 predicates across 17 groups, each naming the file/symbol/observable it pins.
- The AC set collectively guarantees the goal: byte-identical outputs across 50 cassette replays under all four control-flow branches, with no escape hatches for memoized-cheat, module-state-leak, dict-iteration-leak, or cross-arch drift.
- Every AC has at least one test in the TDD plan that would fail if a wrong implementation were swapped in: sum-type verdict catches "right object, wrong bytes"; AST guards catch "right output, wrong source-module discipline"; module-state guard catches "right output, accumulating side effects"; identity invariants catch "right pipeline, wrong cross-event reference".
- No AC is a tautology, a "no exception thrown" check, or a vague qualitative statement.
- TDD plan distinguishes intent-verifying tests (Hypothesis property over input shape; identity invariants) from regression tests (per-iteration parametrized byte-equality).
- Story does not contradict phase arch, any ADR, or CLAUDE.md.
- Critical edge cases listed: cross-arch float drift; dict iteration order; set iteration; cassette-miss; module-state leak; memoized-Transform cheat; constancy-tuple drift; reduced-iteration count; recording arch mismatch.
- The prescribed implementation: (a) consumes the S6-01 `make_fallback_tier_for_fixtures` factory + Phase 5 `cassettes.lock` kernel; (b) introduces a new `tests/_determinism/` test-side helper package with six pure modules; (c) does NOT extract a `nondet_fields` projection onto event classes (rule-of-three; deferred to next consumer); (d) leaves an explicit extension-by-addition path for Phase 6.5 bench-replay determinism + Phase 9 Temporal-replay determinism (they will be the rule-of-three triggers).
- Domain identifiers typed: `DeterminismKey` (Pydantic frozen-extra-forbid), `NonDeterministicField` (StrEnum), `CompareReport` / `EventTapeDiff` (tagged unions); pure logic separated from I/O (`tests/_determinism/` is functional core; the test file is imperative shell).

Three cross-doc conflicts surfaced to the implementer rather than silently averaged: (1) four-vs-eight-tuple constancy; (2) `RecipeApplication.diff_bytes` access shape from S6-01; (3) `pytest-recording` config dependency on S3-04.
