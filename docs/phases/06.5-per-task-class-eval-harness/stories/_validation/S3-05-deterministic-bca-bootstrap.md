# Validation report — S3-05 — Deterministic BCa bootstrap for `lower_bound_95`

**Validator run:** 2026-05-27 (scheduled task `story-validation-corrector`)
**Story file:** `../S3-05-deterministic-bca-bootstrap.md`
**Verdict:** **HARDENED** — 22 findings (7 block, 11 harden, 4 nit) applied; story rewritten in place. Concrete contract drifts against HARDENED S3-01 (`RunId` newtype, 16-hex content-addressing) and HARDENED S3-02 (`_aggregate(queue, plan, on_score, started_at)` module-level helper; per-case items are `(case_id, BenchScore)` tuples; canonical `make_stub_plan(tmp_path, *, case_ids=...)` helper) fixed. Two real test-quality bugs closed: `caplog` does not capture `structlog` events in this codebase (`structlog.testing.capture_logs()` is the canonical pattern); `np.percentile`'s `method=` kwarg is load-bearing for cross-version byte-identical determinism. The scipy-or-Acklam ambiguity is collapsed in favor of an Acklam-only implementation so the closure stays minimal. Five pure helpers (`_derive_seed`, `_norm_ppf`, `_bias_correction`, `_acceleration`, `_bca_alpha_lower`) are now AC-mandated with their own Efron §14.3 worked-example unit tests — making the load-bearing BCa math mutation-vulnerable at the unit-test boundary. The future Wilson-switch (ADR-0002 §"Revisit trigger") is surfaced as a Note-for-implementer Strategy-pattern opportunity, not an AC (Rule 2: hold off until the second implementation).

**Skip Stage 3:** no findings tagged `NEEDS RESEARCH` — every weakness resolves against HARDENED S3-01/S3-02 contracts, existing codebase conventions (structlog testing, Final constants, newtype identifiers), and Efron 1993 §14.3 (cited in the story already).

## Context Brief (Stage 1)

S3-05 is the final piece of the runner's aggregator: replace the `lower_bound_95=0.0` placeholder that HARDENED S3-02 emits with a deterministic, seeded BCa-bootstrap 95% one-sided lower confidence bound. This bound is the **sole** input to `PromotionGate.evaluate` (ADR-0002) — `mean_score` and `score_stddev` are reported for human review only. Determinism is load-bearing: identical inputs must produce a byte-identical bound across reruns, host reboots, and Python minor versions, because the bound itself becomes part of the BLAKE3-chained `BenchRunReport`.

Load-bearing constraints:

- **HARDENED S3-01 contracts:**
  - `RunPlan.run_id: RunId` where `RunId = NewType("RunId", str)` and the value is exactly 16 hex chars (`identity_hash(...)[16]` after stripping `sha256:`). The `int(run_id[:8], 16)` seed derivation is therefore well-typed: 8 hex chars → a 32-bit unsigned integer (`numpy.random.default_rng` accepts `int`). The story currently types `run_id: str` — should use `RunId`.
  - `S3-01 AC-12` explicitly states "Empty bench is a legitimate state… the bootstrap seed concern is S3-05's problem, not plan's." S3-05 must handle `len(scores) == 0` gracefully — currently the `N < 5` floor covers it, but no AC pins the `N == 0` case as a tested invariant.
- **HARDENED S3-02 contracts:**
  - The aggregator is `async def _aggregate(queue: asyncio.Queue[tuple[str, BenchScore] | _Sentinel], plan: RunPlan, on_score, started_at) -> BenchRunReport` — a module-level helper, not a method. Story's wording "call from S3-02's aggregator" is vague and risks the executor inlining the call in `Runner.execute` (wrong layer).
  - Per-case items in the report are `tuple[str, BenchScore]`; the story's `[s.score for _, s in per_case]` extraction is correct, but the call site (inside `_aggregate`, after the sentinel-driven loop terminates and `per_case` is sorted by `case_id`) needs to be named.
  - Canonical test helper: `make_stub_plan(tmp_path, *, case_ids=...)` from `tests/helpers/bench.py`. The story's `make_plan_with_varied_scores(stub_bench)` is a fictional helper; widening the canonical helper with an additive `scores=` kwarg is the correct pattern (precedent: S3-04 widened `breakdown_keys=`, `failure_mode_taxonomy=` additively).
  - Story currently uses `caplog` in `test_small_n_returns_zero_and_warns`. The codebase's canonical structlog-event-capture pattern (used in `tests/unit/test_audit_anchors.py` and `tests/smoke/test_cli_end_to_end.py`) is `with structlog.testing.capture_logs() as logs:`. `caplog` will silently miss the event under the project's structlog processor chain.
- **ADR-0002 §Decision:** Seed is `int(run_id[:8], 16)`; bootstrap is 1000 BCa resamples; `lower_bound_95` is the 2.5th percentile of bootstrapped means. §"Revisit trigger" defers a future Wilson switch — observable from `BenchRunReport` (per-case `score ∈ {0.0, 1.0}` rate > 80% over 50+ cases). The trigger does **not** require any S3-05 infrastructure beyond what `BenchRunReport` already carries.
- **CLAUDE.md load-bearing commitments:**
  - "Determinism over probabilism" — the bootstrap is "the **single** probabilistic surface" (arch §Determinism vs probabilism); leafed and seeded.
  - "Honest confidence" — `lower_bound_95` IS the operationalization (ADR-0002).
  - Newtype identifiers — domain IDs are typed (`RunId`, `ProbeId`, etc.); raw `str` for `run_id` crosses ≥2 module boundaries (bootstrap reads it, runner produces it).
  - Functional core / imperative shell — the BCa math is naturally pure; only the `N < 5` `structlog.warning` is impure. Extract the math into pure module-level helpers.
  - Final tuples / module-level constants for catalogs (`_GENERATOR_HEADER_MARKERS`, `_LOCKFILE_PRECEDENCE`) — `_N_RESAMPLES_DEFAULT`, `_SMALL_N_FLOOR` are the natural analogs.
  - Forbidden-pattern hook bans bare `assert` — module-level invariant assertions use `raise AssertionError(...)`.
- **Closure hygiene:** numpy is acceptable (not on the LLM-fence deny-list `{langgraph, openai, langchain, transformers, sentence-transformers, torch}`); scipy is bigger and brings transitive BLAS-stack pressure. The Acklam algorithm for `_norm_ppf` keeps the closure to numpy-only — preferred over scipy on Rule 2 grounds.
- **numpy version pin:** `np.percentile`'s `method=` kwarg defaults to `"linear"` since numpy 1.22 (the rename from `interpolation=`); pinning `method="linear"` explicitly removes a silent-drift surface across numpy versions. `numpy.random.Generator.choice` is byte-stable across numpy versions per the NEP 19 RNG stability policy — pin `numpy>=1.22` in pyproject.toml so both guarantees hold.

## Stage 2 — Critic findings

Four critics ran in parallel.

### Coverage (C-01 … C-08) — 8 findings

- **C-01 (block).** `run_id: str` parameter type drifts from HARDENED S3-01's `RunId` newtype. Cross-module call (`_aggregate` → `compute_lower_bound_95`) is exactly where the newtype discipline matters.
- **C-02 (block).** "Call from S3-02's aggregator" is vague. HARDENED S3-02 has a named module-level `_aggregate(queue, plan, on_score, started_at)` — the call site must be named (post-sentinel loop, after per-case sort).
- **C-03 (block).** `N == 0` (empty bench) not explicitly tested. S3-01 AC-12 explicitly hands this case to S3-05; the `N < 5` floor covers it semantically, but the test must cover it because empty list is a different code-path shape (no resampling, no jackknife, no `arr.std`).
- **C-04 (harden).** `np.percentile`'s `method=` kwarg is load-bearing for cross-version byte-identical determinism. Story does not pin it.
- **C-05 (harden).** `np.random.default_rng(seed).choice(...)` byte-stability across numpy versions is governed by NEP 19; pin `numpy>=1.22` and document the stability commitment.
- **C-06 (harden).** Helpers `_bias_correction`, `_acceleration`, `_bca_alpha_lower`, `_norm_ppf` mentioned in refactor but not AC-mandated. The Efron §14.3 worked-example unit tests are listed in refactor — should be ACs, since they're what makes the BCa math mutation-vulnerable.
- **C-07 (nit).** `_derive_seed(run_id: RunId) -> int` smart constructor opportunity — collapses `int(run_id[:8], 16)` into a named, unit-tested helper. Mirrors S3-01's `_compose_run_id` precedent.
- **C-08 (nit).** Story does not name the precondition that `run_id[:8]` is valid hex — implicit from HARDENED S3-01 (`run_id` is 16-hex), but worth a sentence.

### Test-Quality (F-TQ-1 … F-TQ-7) — 7 findings

- **F-TQ-1 (block).** `caplog` does not capture `structlog` events under the project's processor chain. `test_small_n_returns_zero_and_warns(caplog)` is a silent false-pass — `caplog.records` will be empty regardless of whether the warning fired. Codebase canonical: `structlog.testing.capture_logs()` (precedent: `tests/unit/test_audit_anchors.py:172` and 5 other call sites; `tests/smoke/test_cli_end_to_end.py:39`).
- **F-TQ-2 (block).** `test_bound_lands_on_report(stub_bench)` references fictional helpers (`stub_bench`, `make_plan_with_varied_scores`, `stub_sut`, `stub_rubric`). HARDENED S3-02 introduced `make_stub_plan(tmp_path, *, case_ids=...)`. Aggregator regression test must use the canonical helper, widened additively with a `scores=` kwarg.
- **F-TQ-3 (harden).** Helpers `_bias_correction`, `_acceleration`, `_bca_alpha_lower`, `_norm_ppf` have no AC-mandated unit tests. Without unit tests against Efron §14.3 worked examples (or against scipy as an oracle, executed once at story-prep time), an executor can ship a wrong implementation that passes the Hypothesis sanity property by accident.
- **F-TQ-4 (harden).** **Missing property: order-invariance.** The BCa bound is symmetric under permutation of the input scores. A test that asserts `compute_lower_bound_95(list(reversed(scores)), ...) == compute_lower_bound_95(scores, ...)` would catch any implementation that accidentally consumed scores in their input order (e.g., a naive Welford-style streaming bootstrap that doesn't recompute on the full sample).
- **F-TQ-5 (harden).** Snapshot test's placeholder hex (`"0x1.5cc4..."`) is honest but the AC needs to spell out the regen flow: executor runs the test once to compute the value, pins it as the literal, AND records the numpy version pin in `pyproject.toml` so the snapshot remains stable until an intentional numpy bump triggers an ADR amendment.
- **F-TQ-6 (harden).** Hypothesis property `test_bca_bound_within_mean_minus_two_stddev_window` filters out `stddev == 0` via early return — but the filter happens inside the test body. With `hypothesis.assume(arr.std(ddof=1) > 0)` the property's intent is clearer and Hypothesis discards rather than passes-vacuously.
- **F-TQ-7 (nit).** `test_uniform_score_shift_is_non_decreasing` uses `[s + 0.05 for s in scores]` with `max_value=0.9` to avoid clamp. Add `assume(all(s + 0.05 <= 1.0 for s in scores))` so the property remains valid if the strategy is widened later.

### Consistency (F-CON-1 … F-CON-5) — 5 findings

- **F-CON-1 (block).** `run_id: str` vs HARDENED S3-01's `RunId` newtype. Same as C-01 — surfaced from the consistency lens to confirm both critics flag it independently.
- **F-CON-2 (block).** "S3-02's aggregator" vs HARDENED S3-02's `_aggregate(queue, plan, on_score, started_at)`. Same as C-02.
- **F-CON-3 (harden).** The scipy-or-Acklam ambiguity ("`scipy.stats.norm.ppf` if scipy is available; else Acklam's algorithm") violates Rule 7: surface conflicts, don't average. The story must pin one. **Pick Acklam-only:** keeps the closure to numpy-only (no transitive BLAS-stack pressure); cross-version byte-stability is easier to certify (the algorithm is fixed); the story already cites Acklam as the fallback. scipy can be revisited in a future ADR amendment if its determinism guarantees ever exceed Acklam's.
- **F-CON-4 (harden).** numpy version pin missing. NEP 19 governs `np.random.Generator.choice` stability across numpy minor versions; pin `numpy>=1.22,<3.0` (or similar) in pyproject.toml so the snapshot test's byte-identical commitment is testable.
- **F-CON-5 (nit).** ADR-0002's "Revisit trigger" (Wilson switch when `score ∈ {0.0, 1.0}` rate > 80%) is observable from `BenchRunReport` — no S3-05 infrastructure needed. The story has this in Out-of-scope; that placement is correct. A one-sentence Note-for-implementer that the Strategy-pattern path is the Wilson-switch on-ramp would close the design-pattern thread without creating premature abstraction.

### Design-Patterns (F-DP-1 … F-DP-6) — 6 findings (none block; 3 harden, 3 nit)

- **F-DP-1 (harden).** Pure functional core / imperative shell discipline. `compute_lower_bound_95` is naturally pure except for the `N < 5` `structlog.warning`. Extract the math into pure helpers (`_bias_correction`, `_acceleration`, `_bca_alpha_lower`, `_norm_ppf`, `_derive_seed`) — each unit-testable in isolation; the impure surface is exactly the warning. Mirrors S3-01's pattern (three pure helpers extracted: `_compose_rubric_digest`, `_compose_cassette_corpus_digest`, `_compose_run_id`).
- **F-DP-2 (harden).** Module-level `Final` constants for magic numbers: `_N_RESAMPLES_DEFAULT: Final[int] = 1000`, `_SMALL_N_FLOOR: Final[int] = 5`, `_ALPHA_LOWER: Final[float] = 0.025`. Codebase precedent: `_GENERATOR_HEADER_MARKERS`, `_LOCKFILE_PRECEDENCE` (both iterated, never branched on). Promotes intent and makes the small-N floor a single source of truth.
- **F-DP-3 (harden).** Smart constructor `_derive_seed(run_id: RunId) -> int` — collapses `int(run_id[:8], 16)` into a named helper with its own unit test. Surfaces the precondition (`run_id` is 16-hex) and the invariant (`0 ≤ seed < 2**32`) at a unit-test boundary. Mirrors S3-01's `_compose_run_id` smart-constructor pattern.
- **F-DP-4 (nit).** **Strategy/registry for the future Wilson switch (Note only, NOT AC).** ADR-0002's revisit trigger names a future bootstrap-method swap. A `ConfidenceBoundStrategy` Protocol with `BCaBootstrapStrategy` as the day-1 implementation would make Wilson a zero-edit additive change. **Reject as AC** (Rule 2: "three similar lines is better than premature abstraction" — we have ONE implementation today). **Accept as Note-for-implementer** so the Wilson PR author knows the extension shape.
- **F-DP-5 (nit).** Anaemic `Sequence[float]` for `per_case_scores`. A `BenchScores = NewType("BenchScores", tuple[float, ...])` would type the input precisely (a tuple of `BenchScore.score` values), but this is over-typing for a leaf helper. Defer.
- **F-DP-6 (nit).** Vectorized resample (`rng.choice(arr, size=(n_resamples, arr.size), replace=True).mean(axis=1)`) — already mentioned in Notes but currently presented as optional. Make it the canonical implementation; keep the slow loop in the docstring as the readable spec. Performance matters because the test suite runs the bootstrap dozens of times per CI run.

## Stage 3 — Researcher

Skipped — no findings tagged `NEEDS RESEARCH`. Every weakness resolves against:

- HARDENED S3-01 / S3-02 contracts (newtype, helper signatures, aggregator name)
- Existing codebase conventions (`structlog.testing.capture_logs`, `Final` constants, smart constructors)
- Efron 1993 §14.3 (already cited in the story)
- numpy stability policies (NEP 19 for RNG, `method=` kwarg stability for `np.percentile`)
- ADR-0002 §"Revisit trigger" (already authored by the phase architect)

## Stage 4 — Synthesizer

**Conflict resolution (Consistency > Coverage > Test-Quality > Design-Patterns):**

| Conflict | Resolution | Wins because |
|---|---|---|
| Story's `run_id: str` vs HARDENED S3-01's `RunId` newtype | Use `RunId` | Consistency: upstream HARDENED contract is source of truth |
| Story's "S3-02's aggregator" vs HARDENED `_aggregate(queue, plan, on_score, started_at)` | Name `_aggregate` explicitly; pin call site (post-sentinel loop, after `per_case` sort) | Consistency: upstream HARDENED contract is source of truth |
| Story's scipy-or-Acklam ambiguity | Pin Acklam-only (numpy-only closure) | Consistency (Rule 7: surface conflict, don't average) + closure hygiene (Rule 2: smaller closure beats optional dep) |
| Story's `caplog` vs codebase's `structlog.testing.capture_logs` | Use `structlog.testing.capture_logs` | Test-Quality: `caplog` is a silent false-pass under the project's processor chain |
| Story's fictional `make_plan_with_varied_scores(stub_bench)` vs HARDENED `make_stub_plan(tmp_path, *, case_ids=...)` | Use HARDENED helper; widen additively with `scores=` kwarg | Consistency: upstream HARDENED helper is canonical |
| Design-Patterns suggests Strategy/registry for Wilson switch; Rule 2 says hold off | Defer to Note-for-implementer (not AC) | Rule 2: "three similar lines is better than premature abstraction" — we have ONE implementation |
| Coverage wants Efron worked-example unit tests as ACs; story has them in refactor | Promote to ACs (renumbered) | Coverage: they're load-bearing mutation defense |

**Edits applied to the story** (full delta-list in the story's new `## Validation notes` block at the top):

1. **Header** — `Status: Ready` → `Status: Ready (HARDENED 2026-05-27)`; `Depends on` widened to S3-02 HARDENED (`_aggregate` helper) + S3-01 HARDENED (`RunId` newtype, 16-hex content-addressing); `ADRs honored` clarified.
2. **`## Validation notes` block** appended after the title — records every change with rationale.
3. **Context** — clarified that `run_id` is 16-hex (HARDENED S3-01), so `run_id[:8]` is always valid hex (no precondition-failure path needed in the bootstrap); pinned the numpy-only-no-scipy choice; named the `_aggregate` call site.
4. **Goal** — rewritten to (a) type `run_id: RunId`, (b) name the call site as `_aggregate` (S3-02 HARDENED's module-level helper), (c) pin numpy + Acklam as the canonical implementation, (d) commit to the pure-helper extraction.
5. **Acceptance criteria** — renumbered AC-1…AC-17. 9 new/strengthened ACs:
   - AC-1 `compute_lower_bound_95(scores, *, run_id: RunId, n_resamples=_N_RESAMPLES_DEFAULT) -> float`.
   - AC-2 `_derive_seed(run_id: RunId) -> int` smart constructor with own unit test.
   - AC-3 numpy-only: no scipy in `pyproject.toml`; `_norm_ppf` implemented via Acklam's algorithm.
   - AC-6 `np.percentile(..., method="linear")` pinned.
   - AC-7 N=0 (empty list) → 0.0 + warn (explicit AC, distinct test from N=4).
   - AC-8 Pure helpers `_bias_correction`, `_acceleration`, `_bca_alpha_lower`, `_norm_ppf` each have unit tests against Efron §14.3 worked examples (or scipy-computed oracle values pinned as literals at story-prep time).
   - AC-9 Module-level `Final` constants: `_N_RESAMPLES_DEFAULT`, `_SMALL_N_FLOOR`, `_ALPHA_LOWER`.
   - AC-12 structlog testing via `structlog.testing.capture_logs()` (not `caplog`).
   - AC-13 Order-invariance Hypothesis property (`compute_lower_bound_95(reversed(scores), ...) == compute_lower_bound_95(scores, ...)`).
   - AC-14 Aggregator wiring: `_aggregate` (S3-02 HARDENED helper) calls `compute_lower_bound_95([s.score for _, s in per_case], run_id=plan.run_id)` after the sentinel-driven loop terminates and `per_case` is sorted by `case_id`. Regression test uses `make_stub_plan(tmp_path, *, case_ids=..., scores=[...])` (additively widened).
   - AC-16 `numpy>=1.22,<3.0` pinned in `pyproject.toml`; snapshot test depends on this pin.
   - AC-17 Snapshot regen flow documented: executor runs the test, pins the literal hex, records the numpy pin; future regen requires an ADR amendment (rare).
6. **Implementation outline** — rewritten:
   - Step 1: `compute_lower_bound_95(scores: Sequence[float], *, run_id: RunId, n_resamples: int = _N_RESAMPLES_DEFAULT) -> float`.
   - Step 2: `_derive_seed(run_id: RunId) -> int` smart constructor.
   - Step 3: pure helpers `_bias_correction`, `_acceleration`, `_bca_alpha_lower`, `_norm_ppf` (Acklam's algorithm — stdlib only, no scipy).
   - Step 4: vectorized resample as canonical: `rng.choice(arr, size=(n_resamples, arr.size), replace=True).mean(axis=1)`; slow loop kept in docstring as the readable spec.
   - Step 5: `_aggregate(queue, plan, on_score, started_at)` (S3-02 HARDENED's module-level helper) — after `per_case` sort, set `lower_bound_95 = compute_lower_bound_95([s.score for _, s in per_case], run_id=plan.run_id)`.
7. **TDD plan** — rewritten:
   - Fix `caplog` → `with structlog.testing.capture_logs() as logs:`.
   - Replace fictional `make_plan_with_varied_scores(stub_bench)` with HARDENED `make_stub_plan(tmp_path, *, case_ids=..., scores=...)`.
   - Add order-invariance Hypothesis property.
   - Add N=0 test.
   - Add Efron §14.3 worked-example unit tests for `_bias_correction`, `_acceleration`, `_bca_alpha_lower`, `_norm_ppf` (in `tests/unit/test_bootstrap_helpers.py`).
   - Replace snapshot placeholder hex with a clear "regen by running once at green-step" comment + the numpy version assertion.
   - Use `hypothesis.assume(...)` instead of in-body early returns for stddev=0 and clamp-avoidance.
8. **Files to touch** — additions:
   - `tests/unit/test_bootstrap_helpers.py` (Efron worked-example unit tests for pure helpers).
   - `tests/helpers/bench.py` widening: additive `scores=None` kwarg on `make_stub_plan` — when provided, threads through to the stub SUT/rubric so the aggregator regression test can vary scores per case.
   - `pyproject.toml` pin: `numpy>=1.22,<3.0` (numpy version pin is part of the byte-identical determinism contract).
   - **Removed:** scipy from optional-dependency list (Acklam-only).
9. **Out of scope** — explicit additions:
   - `ConfidenceBoundStrategy` Protocol / Strategy pattern (Wilson-switch on-ramp): Note-for-implementer only — Rule 2 (one implementation today).
   - scipy as alternative `norm.ppf` source: deferred to future ADR amendment.
   - `BenchScores` newtype for the input: over-typing for a leaf helper.
10. **Notes for the implementer** — substantially extended:
    - Strategy-pattern Note for the future Wilson switch: when adding `WilsonBoundStrategy`, extract a `ConfidenceBoundStrategy` Protocol from `compute_lower_bound_95`'s shape; the registry-of-strategies pattern is the Open/Closed seam. **Do not introduce now.**
    - Acklam's algorithm citation: Peter John Acklam, "An algorithm for computing the inverse normal cumulative distribution function" (2003); maximum relative error ~1.15 × 10⁻⁹ on the central region — adequate for BCa.
    - `np.percentile(..., method="linear")` is pinned because numpy's default `method=` has been stable since 1.22 but pinning makes the dependency on numpy's API explicit.
    - `structlog.testing.capture_logs` is the canonical structlog-event-capture pattern; `caplog` silently misses events under the project's processor chain.
    - The `N < 5` floor is the only impure surface in an otherwise functional-core module — keep it that way.

## Verdict

**HARDENED.** The story is now compatible with HARDENED S3-01 (`RunId` newtype) and HARDENED S3-02 (`_aggregate` helper, `(case_id, BenchScore)` queue items, canonical `make_stub_plan` helper). Five pure helpers carry the load-bearing BCa math under unit-test scrutiny (Efron §14.3 worked examples + order-invariance + monotone-shift + mean-stddev-window properties = mutation-resistant defense). The closure hygiene constraint (numpy-only, no scipy) is now explicit. The future Wilson-switch is preserved as a documented Strategy-pattern extension point without forcing premature abstraction. Two silent-false-pass bugs (`caplog` vs structlog; unpinned `np.percentile` method) are closed.
