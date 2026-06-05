# Story S5-06 — Cache hit-rate + invalidation integration tests

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** HARDENED (phase-story-validator, 2026-06-05)
**Effort:** S
**Depends on:**
- **S5-05 HARDENED** — 10 signed cases land under `bench/vuln-remediation/cases/`; `digests.yaml` is consistent with `compute_case_dir_digest`; the deterministic stub SUT `tests/fixtures/sut/deterministic_vuln_sut.py` is autouse-registered into `default_sut_registry` via `tests/fixtures/sut/conftest.py`; the green E2E run via `CliRunner.invoke(eval_group, ["run", "--task-class=vuln-remediation", ...])` is the substrate this story reruns against; `scripts/sign_bench_digests.py` is parameterized by `--task-class` / `--bench-root` and is the operator-side resign tool (consumed by AC-SINGLE-RESIGN).
- **S4-02 HARDENED** — CLI flags `--task-class`, `--out`, `--bench-root`, `--cache-dir` (added by S5-05 F-CON-1), `--no-cache`; SUT resolution via `codegenie.eval.sut_registry.resolve_sut(name)` against `default_sut_registry`; per-case JSONL **flat** shape `{"kind":"case","case_id":...,"score":float,"passed":bool,"breakdown":{...},"failure_modes":[...],"cost_usd":float,"wall_clock_s":float}` (BenchScore is dumped at the top level — NOT nested under a `"score"` envelope); aggregate JSONL `{"kind":"aggregate", …BenchRunReport fields…}`; `agg["complete"] is True` on happy path; `agg["chain_head"]` equals the on-disk record's `chain_head`.
- **S4-01 HARDENED** — exit code 0 for the happy path; `_EXIT_CODE_TABLE` mapping; `BenchCaseDigestMismatch → EXIT_DIGEST_MISMATCH=6` (the secondary single-case test relies on this mapping when (1) — structural digest defense — fires).
- **S2-03 HARDENED** — `compose_cache_key(CacheKeyInputs) -> CacheKey` with the six-input dataclass; content-addressed `<cache_dir>/<64-hex>.json` filename; `get`/`put` atomicity; per-field uniqueness + positional-swap-resistance ACs already unit-test the cache-key composition. This story is the **integration**-level concretization of those unit-level invariants against the 10-case vuln-remediation bench.
- **S2-02 HARDENED** — loader walk + canonical case-dir digest algorithm; `BenchCaseDigestMismatch` raised when `digests.yaml[case_id]` ≠ recomputed digest; the structural defense the (1)-interpretation of single-case invalidation depends on.
- **S1-02 HARDENED** — `BenchScore` wire type with `frozen=True, extra="forbid"`; AC-2 asserts cardinality of wire types is exactly 5. This story extends `BenchScore` by **one field** (`cache_hit: bool = False`) — additive change; no edit to existing fields; model-cardinality unchanged.
- **S3-02 HARDENED** — runner fan-out + cache probe + cache-write; the seam where the cache-hit stamp lands (AC-RUNNER-STAMP).

**ADRs honored:**
- **ADR-0001** — rubric subprocess invocation contributes to `rubric_digest`; the cache key feels every byte of `bench/<name>/rubric.py`.
- **ADR-0002** — cache hit means the report's `lower_bound_95` is byte-identical across reruns; deterministic statistic is load-bearing for promotion evidence.
- **Phase 0 ADR-0001** — BLAKE3 chokepoint; cache key composition routes through `codegenie.hashing.content_hash_bytes` per S2-03 (no direct `import blake3` in `cache.py`).
- **Production ADR-0009** — humans always merge; the cache-correctness test produces evidence the curator commits to git, but no auto-merge.
- **Production ADR-0015** — calibration-deferred; the `lower_bound_95` stability under warm rerun is a precondition for Phase 13 calibration to be meaningful.

## Validation notes (phase-story-validator, 2026-06-05)

- **Status:** Ready → HARDENED.
- **Depends on:** rewritten from a single-line citation of S5-05 to a seven-story dependency chain with per-citation HARDENED contract markers. (F-CON-5.)
- **ADRs honored:** expanded with Phase 0 ADR-0001 + production ADR-0009 / ADR-0015 and per-ADR rationale. (F-CON-6.)
- **Goal** rewritten to name the wire-type extension (`BenchScore.cache_hit: bool = False`), the in-process `CliRunner` test surface, and the `--out`/`--bench-root`/`--cache-dir` flag-driven fixture.
- **Acceptance criteria** restructured from 6 prose-only bullets to 13 named ACs (AC-1 through AC-LINT-RED-GREEN) with concrete machine-checkable predicates: AC-CACHE-HIT-FIELD pins the wire-type extension and the model-validator that makes `cache_hit=True ⇒ cost_usd == 0.0` unrepresentable; AC-RUNNER-STAMP pins the runner seam; AC-CONFTEST-REUSE forbids redefining the SUT-registration seam shipped by S5-05; AC-PROPERTY-HIT-IMPLIES-ZERO-COST promotes the property test from §Refactor to AC; AC-README-CACHE-BEHAVIOR pins the documentation assertion with a verbatim six-input list; AC-SINGLE-RESIGN adds the secondary re-sign-then-rerun test; AC-1's warm-clock budget split into hard ceiling (≤ 12 s) + regression diagnostic (≤ 8 s).
- **TDD plan rewritten:**
  - Subprocess-spawn replaced with `CliRunner.invoke(eval_group, [...])` (F-CON-2 / F-TQ-2 — identical to S5-05 F-TQ-2).
  - Env-var fixture (`CODEGENIE_EVAL_CACHE_DIR/RUNS_DIR/SUT`) deleted; replaced with `tmp_path`-derived flag overrides `--out=<tmp_runs>` / `--bench-root=<tmp_bench>` / `--cache-dir=<tmp_cache>` (F-CON-1 / F-TQ-1 — identical to S5-05 F-CON-1).
  - Per-case JSONL access flattened from `c["score"]["cost_usd"]` to `c["cost_usd"]` and `c["cache_hit"]` (F-CON-3 — S4-02 AC-10 ships flat).
  - Bench tree mutations `shutil.copytree`-isolated to `tmp_bench` so the real working tree is untouched and the test is parallel-safe (F-TQ-3 — identical to S5-05 F-TQ-3).
  - `wall_clock_ms` field-name corrected to `wall_clock_s` (S4-02 AC-10 ships `wall_clock_s`).
- **Files to touch** expanded with `src/codegenie/eval/models.py` (BenchScore extension), `src/codegenie/eval/runner.py` (cache-hit stamp), `tests/unit/eval/test_cache_hit_property.py` (Hypothesis property test), `bench/vuln-remediation/README.md` (Cache behavior section).
- **Out of scope** expanded with: SUT-digest / cassette-corpus-digest invalidation (S2-03 unit tests own those), the `--sut-module=<dotted>` extension (deferred to Phase 7+), the `_assert_all_cache_hits` helper extraction (deferred to rule-of-three with S6-03).
- **Notes for the implementer** rewritten to document: the wire-field-vs-span-attribute choice, the model-validator approach with fallback, the autouse conftest reuse path inherited from S5-05, the F-COV-4 single-case re-sign secondary test rationale, the F-COV-5 budget split rationale.
- Full audit log: `_validation/S5-06-cache-hit-rate-and-invalidation-tests.md`.

## Context

The harness's cache key per case is `BLAKE3(case_digest || sut_digest || rubric_digest || cassette_corpus_digest || harness_version || cassette_canary_pin)` (S2-03). If any input changes, the key changes. If none changes, every case is a cache hit, every `cost_usd` is `0.0`, and a warm rerun is bounded by the cache I/O rather than by SUT invocation. The harness's cost discipline (CI budget, contributor dev-loop latency) hinges on this being true.

Two failure modes the integration test must catch:
- **False misses** — a warm rerun re-invokes the SUT. Cache key derivation is wrong; cost regression silent.
- **False hits** — a case is edited but the cache serves the stale score. Cache key is missing an input. Promotion evidence becomes lies.

ADR-0002 + ADR-0001 don't *say* "cache must be correct" explicitly, but the promotion gate's `lower_bound_95` is only meaningful if the score producing it is reproducible **and** invalidated when any input shifts. The 10-case vuln-remediation bench is the first concrete corpus to test this on.

**Detection signal — `BenchScore.cache_hit: bool`.** Cost-based detection (`cost_usd == 0.0`) is insufficient for the stub SUT (which emits `cost_usd=0.0` always per S5-05 design). The integration test detects cache hits via an explicit `cache_hit: bool` field on `BenchScore`, set to `False` by default and stamped `True` by the runner (S3-02) when serving from cache. A Pydantic `model_validator` makes the illegal combination `cache_hit=True and cost_usd > 0` unrepresentable. This is an extension-by-addition of S1-02's `BenchScore` (one field added; no edits to existing fields; model-cardinality unchanged; structural walk in S1-02 AC-2 stays green).

**Test surface — in-process via `CliRunner.invoke`.** Subprocess-spawn (`subprocess.run([sys.executable, "-m", "codegenie", ...])`) cannot reach the deterministic stub SUT because the spawned process imports `default_sut_registry` empty. The integration test runs in-process via `click.testing.CliRunner.invoke(eval_group, ["run", "--task-class=vuln-remediation", "--out", str(tmp_runs), "--bench-root", str(tmp_bench), "--cache-dir", str(tmp_cache)])`; the autouse conftest at `tests/fixtures/sut/conftest.py` (shipped by S5-05) populates the in-process `default_sut_registry`. Subprocess-shape coverage is the nightly canary's job (real SUT). Identical scope decision to S5-05 F-TQ-2.

**Bench tree mutations are tmp_path-isolated.** Both invalidation tests `shutil.copytree(REPO_ROOT / "bench" / "vuln-remediation", tmp_bench / "vuln-remediation")` and mutate the copy; `--bench-root` points the CLI at `tmp_bench`. The real working tree is never touched, so the tests are parallel-safe under pytest-xdist. Identical pattern to S5-05 F-TQ-3.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/cache.py` — `get/put/gc`; corrupt-file-on-read treated as miss; `fcntl.flock` on sentinel.
  - `../phase-arch-design.md §Testing strategy → Integration → test_cache_hit_rate.py / test_cache_invalidation.py` (lines 991-992) — names this story's tests; specifies "second run ≤ 8 s" and "all 10 `cost_usd == 0.0`"; whitespace edits to `rubric.py` invalidate all; whitespace edits to one `case.toml` invalidate only that case.
  - `../phase-arch-design.md §Process view` line 856 — `attributes: case_id, cache_hit: bool, curation_class` — names `cache_hit` as a span attribute; this story promotes it to a wire-type field (extension-by-addition).
  - `../phase-arch-design.md §Property tests → Cache-key determinism` — the Hypothesis-property substrate; this story's AC-PROPERTY-HIT-IMPLIES-ZERO-COST is the sibling property test pinning the model-validator invariant.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md §Consequences` — the rubric file is bytewise part of `rubric_digest`; any edit (whitespace included) bumps it.
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md §Consequences` — deterministic `lower_bound_95` requires deterministic cache; this test enforces both.
- **Sibling-story HARDENED contracts (load-bearing for this story's TDD plan):**
  - `S5-05-vuln-digests-and-e2e-run.md §AC-3a §AC-CONFTEST-REGISTRATION §AC-SUT-CONTRACT` — `CliRunner.invoke(eval_group, ["run", "--task-class=vuln-remediation", "--out", str(tmp_runs), "--bench-root", str(tmp_bench), "--cache-dir", str(tmp_cache)])` is the sanctioned invocation shape; `tests/fixtures/sut/conftest.py` autouse-registers `deterministic_vuln_sut`. **Reuse, do not duplicate.**
  - `S4-02-eval-run-subcommand.md §AC-3 §AC-7 §AC-10 §AC-14` — `sut_registry` resolution; `--no-cache` semantics (this story does NOT use `--no-cache` — it needs the cache to actually be used); **flat** per-case JSONL shape (`c["cost_usd"]`, NOT `c["score"]["cost_usd"]`); `--out` override.
  - `S4-01-cli-scaffold-exit-codes.md §AC-2 §AC-3` — `_EXIT_CODE_TABLE` mapping; `BenchCaseDigestMismatch → EXIT_DIGEST_MISMATCH=6` (consumed by the secondary single-case structural-defense test).
  - `S2-03-content-addressed-cache.md §"Composer (`compose_cache_key`) semantics"` — six-input `CacheKeyInputs` dataclass; per-field uniqueness + positional-swap-resistance unit tests; the cache-key composition this story integration-tests on real bench inputs.
  - `S2-02-loader-cases-and-digests.md §AC-3` — canonical case-dir digest algorithm; `BenchCaseDigestMismatch` on stale digest.
  - `S1-02-wire-models-frozen-extra-forbid.md §AC-2 §AC-3 §AC-11` — `BenchScore.score: Field(ge=0.0, le=1.0)`, `cost_usd: Field(ge=0.0)`, etc.; the structural walk asserts model cardinality (5) — adding `cache_hit` to `BenchScore` does NOT change cardinality.
  - `S3-02-asyncio-fan-out-and-aggregator.md` — runner fan-out; the cache-probe branch is the seam for AC-RUNNER-STAMP.
- **Source design:** `../High-level-impl.md §Step 5` "Done criteria" — "Re-running the same task class with no source changes is a 100% cache hit (10/10 cases `cost_usd == 0.0`, wall-clock ≤ 8 s)"; "whitespace edit to `rubric.py` invalidates all 10 cache entries; whitespace edit to one `case.toml` invalidates exactly that case".

## Goal

Land two integration tests that exercise the full cache contract on the 10-case vuln-remediation bench, executed in-process via `CliRunner.invoke` against a `shutil.copytree`-isolated `tmp_bench`. Concretely:

1. Extend `BenchScore` by **one** additive field: `cache_hit: bool = False`, with a model-validator that makes `cache_hit=True and cost_usd > 0` unrepresentable. The runner (S3-02) stamps `cache_hit=True` when serving from cache; the CLI's flat per-case JSONL surfaces it as a top-level `c["cache_hit"]` key.
2. Land `tests/integration/eval/test_cache_hit_rate.py`: warm rerun across the 10-case vuln-remediation bench produces all 10 per-case lines with `cache_hit=True` and `cost_usd=0.0`; aggregate `complete=True`, `isolation_class="subprocess"`, `chain_head` matches the on-disk record; wall-clock ≤ 12 s hard-fail / ≤ 8 s regression diagnostic.
3. Land `tests/integration/eval/test_cache_invalidation.py` with two scenarios: (a) whitespace edit to `tmp_bench/vuln-remediation/rubric.py` produces all 10 cases with `cache_hit=False` on the warm rerun (rubric_digest invalidation propagates); (b) whitespace edit to one case's `input/<file>` triggers `BenchCaseDigestMismatch` → exit 6 (the structural-defense interpretation per S2-02). A secondary AC-SINGLE-RESIGN test re-signs `digests.yaml` after the case edit and asserts 9 cache hits + 1 miss (the cache-key composition interpretation).
4. Document the cache contract in `bench/vuln-remediation/README.md` "Cache behavior" section (verbatim six-input list, signed-content-addressed semantics).

The story exists to enforce the cost-discipline that ADR-0002's `lower_bound_95` reproducibility depends on — false misses silently regress CI cost; false hits silently lie in promotion evidence. Two tests cover both sides.

## Acceptance criteria

- [ ] **AC-CACHE-HIT-FIELD (wire-type extension — extension by addition).** `src/codegenie/eval/models.py` extends `BenchScore` with exactly one additive field: `cache_hit: bool = Field(default=False, description="True when the score was served from the cache; False on fresh SUT+rubric execution.")`. Existing fields and their constraints are unchanged. The model's `model_config` keeps `frozen=True, extra="forbid"`. A `@model_validator(mode="after")` raises `pydantic.ValidationError` on the illegal combination `cache_hit is True and cost_usd > 0.0` (making it unrepresentable). Verified by: (a) a unit test under `tests/unit/eval/test_cache_hit_property.py` constructing `BenchScore(passed=True, score=0.5, breakdown={}, failure_modes=(), cost_usd=0.0, wall_clock_ms=10, cache_hit=True)` succeeds; (b) `BenchScore(..., cost_usd=0.01, cache_hit=True)` raises `pydantic.ValidationError` with a diagnostic naming both fields; (c) the S1-02 structural-walk test (`tests/unit/eval/test_models.py::test_every_wire_type_frozen_and_forbid`) stays green — model cardinality remains 5; (d) the BenchScore model_fields dict gains exactly one new key (`cache_hit`); existing keys are unchanged.

- [ ] **AC-RUNNER-STAMP (runner sets `cache_hit=True` on serve-from-cache).** `src/codegenie/eval/runner.py` — in the cache-probe branch where `cache.get(cache_key, cache_dir)` returns non-`None`, the worker constructs the per-case `BenchScore` with `cache_hit=True` (or `cached_score.model_copy(update={"cache_hit": True})` if returning the cached score directly). The fresh-execution branch leaves `cache_hit=False` (the default). Verified by: a unit test that primes the cache with a `BenchScore` whose `cache_hit=False`, then runs the runner against the same cache_key, and asserts the returned per-case `BenchScore.cache_hit is True`. Mutation-resistant: a missed seam (runner forgets to stamp) surfaces as the warm-rerun integration test failing with `cache_hit=False`.

- [ ] **AC-CONFTEST-REUSE (no duplication of the SUT-registration seam).** Neither integration test in this story defines a `fresh_eval_env` fixture, redefines `tests/fixtures/sut/conftest.py`, redefines `_isolate_sut_registry`, or re-imports `tests.fixtures.sut.deterministic_vuln_sut` directly. The autouse conftest at `tests/fixtures/sut/conftest.py` (shipped by S5-05 AC-CONFTEST-REGISTRATION) is the canonical seam; this story's tests live under `tests/integration/eval/` (the same scope the conftest covers). Verified by a grep-style assertion in the validation: `grep -rE 'monkeypatch\.setenv\("CODEGENIE_EVAL_' tests/integration/eval/test_cache_*.py` returns zero matches; `grep -rE 'subprocess\.run\(\[.*"-m", "codegenie"' tests/integration/eval/test_cache_*.py` returns zero matches.

- [ ] **AC-1 (warm rerun — 100% cache hit, in-process).** `tests/integration/eval/test_cache_hit_rate.py::test_warm_rerun_is_100_percent_cache_hit` executes:
  1. `shutil.copytree(REPO_ROOT / "bench" / "vuln-remediation", tmp_bench / "vuln-remediation")` (the real tree is never mutated).
  2. Cold run: `CliRunner().invoke(eval_group, ["run", "--task-class=vuln-remediation", "--out", str(tmp_runs), "--bench-root", str(tmp_bench), "--cache-dir", str(tmp_cache), "--format=jsonl"])` — assert `result.exit_code == 0`.
  3. Warm run: identical invocation; measure `elapsed = time.monotonic() - start` around the `CliRunner.invoke` call.
  4. Parse the warm run's stdout JSONL; collect per-case lines (`o["kind"] == "case"`) and the aggregate line (`o["kind"] == "aggregate"`).
  5. Assert: `len(cases) == 10`; `all(c["cache_hit"] is True for c in cases)`; `all(c["cost_usd"] == 0.0 for c in cases)`; `agg["complete"] is True`; `agg["isolation_class"] == "subprocess"`; `agg["chain_head"]` is truthy and equals the on-disk record's `chain_head` (load the file at `tmp_runs / <utc_iso>-<token>.json` and compare).
  6. Wall-clock: **hard fail** if `elapsed > 12.0` (50% headroom over the §Step 5 target — flake-safe); **regression diagnostic** via `pytest.warns` or `structlog.warn` if `elapsed > 8.0` but `≤ 12.0` (surfaces drift without flaking).

- [ ] **AC-2 (rubric-edit invalidates all 10).** `tests/integration/eval/test_cache_invalidation.py::test_whitespace_edit_to_rubric_invalidates_all_ten` executes:
  1. `shutil.copytree(...)` to `tmp_bench`.
  2. Cold run via `CliRunner.invoke(eval_group, [...])` to warm the cache (cache lives under `tmp_cache`).
  3. Append `b"\n# cache-bust\n"` to `tmp_bench / "vuln-remediation" / "rubric.py"` (byte-content change, not just `mtime`).
  4. Rerun: `CliRunner.invoke(eval_group, [...])` against the same `tmp_cache`.
  5. Assert: `result.exit_code == 0`; `len(cases) == 10`; `sum(1 for c in cases if c["cache_hit"] is True) == 0` (zero cache hits — all 10 re-invoked the SUT through fresh rubric_digest).
  6. The `try`/`finally` defense-in-depth restoration is **not required** because `tmp_bench` is auto-cleaned by pytest's `tmp_path` fixture; keeping it would still be acceptable belt-and-suspenders but is not load-bearing once the bench tree is isolated.

- [ ] **AC-3 (single-case edit triggers structural digest defense — exit 6).** `tests/integration/eval/test_cache_invalidation.py::test_whitespace_edit_to_one_case_input_raises_digest_mismatch` executes:
  1. `shutil.copytree(...)` to `tmp_bench`.
  2. Cold run to warm the cache.
  3. Pick `target_dir = next(d for d in (tmp_bench / "vuln-remediation" / "cases").iterdir() if d.is_dir() and (d / "case.toml").exists())`; `target_id = target_dir.name`; pick `input_file = next(p for p in (target_dir / "input").rglob("*") if p.is_file())`.
  4. Append `b"\n"` to `input_file` (changes the case-dir digest; `digests.yaml` stays at the original digest).
  5. Rerun via `CliRunner.invoke`.
  6. Assert: `result.exit_code == 6` (per S4-01 `EXIT_DIGEST_MISMATCH`); the loader's `BenchCaseDigestMismatch` raise propagates through `main()`'s `_EXIT_CODE_TABLE`; `target_id in result.stderr` (the diagnostic names the offending case_id — defense-in-depth check; the stderr is captured by `CliRunner` automatically when `mix_stderr=False`).

- [ ] **AC-SINGLE-RESIGN (secondary — re-sign-then-rerun yields 9 hits + 1 miss).** `tests/integration/eval/test_cache_invalidation.py::test_resigned_single_case_invalidates_only_that_case` executes:
  1. `shutil.copytree(...)` to `tmp_bench`.
  2. Cold run to warm the cache.
  3. Pick `target_dir` and `input_file` as in AC-3.
  4. Append `b"\n"` to `input_file`.
  5. Run `scripts/sign_bench_digests.py --task-class=vuln-remediation --bench-root=<tmp_bench>` (S5-05 F-DP-2 — Open/Closed-parameterized) via `subprocess.run` (this is an operator-script invocation, NOT a CLI invocation — orthogonal to F-CON-2). The script regenerates `digests.yaml` from the recomputed `compute_case_dir_digest(target_dir)`.
  6. Rerun the eval via `CliRunner.invoke`.
  7. Assert: `result.exit_code == 0`; `sum(1 for c in cases if c["cache_hit"] is True) == 9`; `sum(1 for c in cases if c["cache_hit"] is False) == 1`; `next(c for c in cases if c["cache_hit"] is False)["case_id"] == target_id` (the right case is the one that missed). This test exercises the cache-key composition (the `case_digest` input flows into the per-case cache_key and changes propagate to exactly one entry). AC-3 tests the loader's structural defense; AC-SINGLE-RESIGN tests the cache-key composition. Both are load-bearing.

- [ ] **AC-PROPERTY-HIT-IMPLIES-ZERO-COST (Hypothesis property test pinning the model-validator).** `tests/unit/eval/test_cache_hit_property.py::test_cache_hit_true_implies_zero_cost` uses Hypothesis to draw arbitrary `BenchScore` shapes (score ∈ [0,1], cost_usd ≥ 0, wall_clock_ms ≥ 0, breakdown dict, failure_modes tuple, passed bool, cache_hit bool) and asserts: for every drawn `BenchScore`, either `cache_hit is False` OR `cost_usd == 0.0` (the model-validator from AC-CACHE-HIT-FIELD rejects the illegal combination at construction time, so this draws shapes that *survived* construction). A second property: any construction with `cache_hit=True and cost_usd > 0` raises `pydantic.ValidationError`. Mutation-resistant: removing the model-validator surfaces immediately.

- [ ] **AC-README-CACHE-BEHAVIOR (documentation pin — verbatim six-input list).** `bench/vuln-remediation/README.md` contains a `## Cache behavior` section that (a) names both integration test files by path (`tests/integration/eval/test_cache_hit_rate.py` and `tests/integration/eval/test_cache_invalidation.py`), (b) lists the six cache-key inputs **verbatim** as a bulleted list — `case_digest`, `sut_digest`, `rubric_digest`, `cassette_corpus_digest`, `harness_version`, `cassette_canary_pin` (any drift fails the test), (c) documents the signed-content-addressed semantics with the literal phrase `"signed-content-addressed"` and the sentence `"You cannot edit one case and let the cache invalidate — you must re-sign in digests.yaml."`. The integration test asserts: `(BENCH_ROOT / "README.md").read_text()` contains the section heading, the six verbatim input names (each as `\bname\b` regex match), and both literal phrases. Mutation-resistant: any drop or rename of an input surfaces.

- [ ] **AC-JSONL-FLAT-SHAPE (per-case JSONL is flat — not nested under "score").** Both integration tests parse per-case JSONL via `o = json.loads(line); assert o["kind"] == "case"` and access `o["cost_usd"]`, `o["cache_hit"]`, `o["case_id"]`, `o["score"]` (the scalar, not a nested dict), `o["passed"]`, `o["wall_clock_s"]` — all at the top level. Tests MUST NOT access `o["score"]["cost_usd"]` or any other nested form. This pins the S4-02 AC-10 contract from the consumer side; a regression where the CLI starts nesting (e.g., emitting `BenchRunReport.per_case` as `[(case_id, BenchScore)]` tuples without unwrapping) surfaces here.

- [ ] **AC-CI-NOT-NIGHTLY (tests run in the standard suite, not nightly-canary-only).** `tests/integration/eval/test_cache_hit_rate.py` and `tests/integration/eval/test_cache_invalidation.py` carry no `@pytest.mark.canary` or `@pytest.mark.nightly` marker; `make test` (which runs `pytest -q` per CLAUDE.md "Important pytest config") executes them. The PR CI workflow run includes them.

- [ ] **AC-PARALLEL-SAFE (tests are parallel-safe under pytest-xdist).** The bench-tree mutations (rubric.py edit, case input file edit) happen exclusively against `tmp_bench` (`shutil.copytree`-copied from the real `bench/vuln-remediation/`). The real working tree is never modified. Verified by: (a) running `pytest tests/integration/eval/test_cache_*.py -n 2 -v` (xdist 2 workers) green; (b) `git diff --quiet bench/vuln-remediation/` is true after the test run.

- [ ] **AC-LINT-RED-GREEN (red→green; lint + typecheck green).** Red versions of `tests/integration/eval/test_cache_hit_rate.py` and `tests/integration/eval/test_cache_invalidation.py` and `tests/unit/eval/test_cache_hit_property.py` exist, were committed at red, are now green. `ruff check tests/integration/eval/test_cache_*.py tests/unit/eval/test_cache_hit_property.py src/codegenie/eval/models.py src/codegenie/eval/runner.py`, `ruff format --check` on same paths, `mypy --strict src/codegenie/eval/models.py src/codegenie/eval/runner.py`, `pytest tests/integration/eval/test_cache_hit_rate.py tests/integration/eval/test_cache_invalidation.py tests/unit/eval/test_cache_hit_property.py -v` all pass. `make fence` continues to pass — no LLM SDK imports introduced. `make check` is green.

## Implementation outline

1. **Write the red tests first** under `tests/integration/eval/test_cache_hit_rate.py`, `tests/integration/eval/test_cache_invalidation.py`, and `tests/unit/eval/test_cache_hit_property.py` — see §TDD plan. Confirm failures (`AttributeError: BenchScore has no field 'cache_hit'`, or assertion failures on `c["cache_hit"]` not being present in JSONL). Commit as the red marker.

2. **Extend `BenchScore` by one additive field (AC-CACHE-HIT-FIELD).** Edit `src/codegenie/eval/models.py`:
   ```python
   class BenchScore(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       passed: bool
       score: float = Field(ge=0.0, le=1.0)
       breakdown: dict[str, float]
       failure_modes: tuple[FailureMode, ...]
       cost_usd: float = Field(ge=0.0)
       wall_clock_ms: int = Field(ge=0)
       cache_hit: bool = Field(
           default=False,
           description="True when the score was served from the cache; False on fresh SUT+rubric execution.",
       )

       @model_validator(mode="after")
       def _cache_hit_implies_zero_cost(self) -> "BenchScore":
           if self.cache_hit and self.cost_usd > 0.0:
               raise ValueError(
                   f"cache_hit=True is incompatible with cost_usd={self.cost_usd!r}; "
                   "a cached score is by definition zero-cost (no SUT invocation)."
               )
           return self
   ```
   This is extension-by-addition: no existing field is edited; `extra="forbid"` and `frozen=True` are preserved; model cardinality (5 wire types) is unchanged. S1-02's structural walk stays green.

3. **Stamp `cache_hit=True` in the runner (AC-RUNNER-STAMP).** Edit `src/codegenie/eval/runner.py` at the cache-probe branch:
   ```python
   cached = cache.get(cache_key, cache_dir)
   if cached is not None:
       # Defense-in-depth: cached scores were written with cache_hit=False (the
       # write path is the first execution); flip the bit for the consumer.
       return cached.model_copy(update={"cache_hit": True})
   # ... fresh execution path; resulting BenchScore has cache_hit=False (default)
   ```
   Document the seam with a one-line comment naming AC-RUNNER-STAMP.

4. **Reuse the S5-05 autouse conftest (AC-CONFTEST-REUSE).** Do NOT redefine `tests/fixtures/sut/conftest.py`, `_isolate_sut_registry`, or any SUT-registration fixture. Confirm the autouse conftest at `tests/fixtures/sut/conftest.py` covers `tests/integration/eval/` (it does, by virtue of pytest's conftest scope walking up the directory tree); if it does not, expand its `pytest_collection_modifyitems` scope or move the conftest one directory up. Do NOT add a new conftest.

5. **Write the integration tests (AC-1, AC-2, AC-3, AC-SINGLE-RESIGN, AC-JSONL-FLAT-SHAPE, AC-PARALLEL-SAFE).** Use `CliRunner.invoke(eval_group, ["run", "--task-class=vuln-remediation", "--out", str(tmp_runs), "--bench-root", str(tmp_bench), "--cache-dir", str(tmp_cache), "--format=jsonl"])`. Bench tree mutations target `tmp_bench` only.

6. **Write the Hypothesis property test (AC-PROPERTY-HIT-IMPLIES-ZERO-COST).** Use `hypothesis.strategies.builds(BenchScore, ...)` with composite strategies that draw arbitrary `BenchScore` shapes; the model-validator rejects the illegal combination at construction time. A second test directly constructs `BenchScore(..., cache_hit=True, cost_usd=0.01)` and asserts `pytest.raises(pydantic.ValidationError)`.

7. **Document the cache behavior (AC-README-CACHE-BEHAVIOR).** Append to `bench/vuln-remediation/README.md`:
   ```markdown
   ## Cache behavior

   The eval harness caches per-case `BenchScore`s under `.codegenie/eval/cache/<64-hex>.json`,
   keyed by `compose_cache_key(CacheKeyInputs(...))` where the inputs are (verbatim):

   - `case_digest`
   - `sut_digest`
   - `rubric_digest`
   - `cassette_corpus_digest`
   - `harness_version`
   - `cassette_canary_pin`

   The cache is **signed-content-addressed**. You cannot edit one case and let the cache
   invalidate — you must re-sign in `digests.yaml`. The structural defense:
   any edit to `cases/<id>/{case.toml,input/*,expected/*}` not reflected in `digests.yaml`
   raises `BenchCaseDigestMismatch` at load time (exit 6).

   Integration tests: `tests/integration/eval/test_cache_hit_rate.py` (warm-rerun 100% hit)
   and `tests/integration/eval/test_cache_invalidation.py` (rubric-edit invalidates all;
   re-signed case-edit invalidates exactly one).
   ```

8. **Iterate to green.** Run `ruff check`, `ruff format --check`, `mypy --strict`, `pytest -v` per AC-LINT-RED-GREEN. Confirm `make check` is green and `make fence` continues to pass (no LLM SDK introduced).

9. **(Optional housekeeping) Regenerate S7-02 snapshots.** If `tests/snapshots/bench_run_report.v1.json` already exists (S7-02 may ship before this story), the new `cache_hit` field surfaces as a JSON-byte drift. Run `python scripts/regen_eval_snapshot.py` and commit the regen with a one-line note that S5-06 added `BenchScore.cache_hit`. If S7-02 has not yet shipped, this step is a no-op.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/integration/eval/test_cache_hit_rate.py`

```python
# tests/integration/eval/test_cache_hit_rate.py
"""Cache contract on the 10-case vuln-remediation bench.
S2-03 + High-level-impl.md §Step 5 "Done criteria" + S4-02 HARDENED AC-10.
In-process via CliRunner (S5-05 F-TQ-2 pattern). Bench tree is tmp_path-isolated."""

from __future__ import annotations

import json
import shutil
import time
import warnings
from pathlib import Path

from click.testing import CliRunner

from codegenie.eval.cli import eval_group

# tests/fixtures/sut/conftest.py (autouse — S5-05 AC-CONFTEST-REGISTRATION)
# populates default_sut_registry with deterministic_vuln_sut.

REPO_ROOT = Path(__file__).parents[3]
REAL_BENCH = REPO_ROOT / "bench" / "vuln-remediation"


def _invoke(tmp_runs: Path, tmp_bench: Path, tmp_cache: Path) -> tuple[object, float]:
    runner = CliRunner(mix_stderr=False)
    start = time.monotonic()
    result = runner.invoke(
        eval_group,
        [
            "run",
            "--task-class=vuln-remediation",
            "--out", str(tmp_runs),
            "--bench-root", str(tmp_bench),
            "--cache-dir", str(tmp_cache),
            "--format=jsonl",
        ],
        catch_exceptions=False,
    )
    return result, time.monotonic() - start


def _parse_jsonl(stdout: str) -> tuple[list[dict], dict]:
    objs = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    cases = [o for o in objs if o["kind"] == "case"]
    aggs = [o for o in objs if o["kind"] == "aggregate"]
    assert len(aggs) == 1, f"expected exactly one aggregate line; got {len(aggs)}"
    return cases, aggs[0]


def test_warm_rerun_is_100_percent_cache_hit(tmp_path: Path) -> None:
    tmp_bench = tmp_path / "bench"
    tmp_bench.mkdir()
    shutil.copytree(REAL_BENCH, tmp_bench / "vuln-remediation")
    tmp_runs = tmp_path / "runs"
    tmp_cache = tmp_path / "cache"

    # Cold run: warm the cache.
    cold_result, _ = _invoke(tmp_runs, tmp_bench, tmp_cache)
    assert cold_result.exit_code == 0, (
        f"cold run failed: exit={cold_result.exit_code}\nstderr={cold_result.stderr}"
    )

    # Warm run: 100% cache hit, ≤ 12 s hard / ≤ 8 s diagnostic.
    warm_result, elapsed = _invoke(tmp_runs, tmp_bench, tmp_cache)
    assert warm_result.exit_code == 0, (
        f"warm run failed: exit={warm_result.exit_code}\nstderr={warm_result.stderr}"
    )

    cases, agg = _parse_jsonl(warm_result.stdout)
    assert len(cases) == 10
    # AC-JSONL-FLAT-SHAPE: per-case lines are flat (NOT nested under "score").
    assert all(c["cache_hit"] is True for c in cases), (
        f"expected cache_hit=True everywhere; "
        f"got {[(c['case_id'], c['cache_hit']) for c in cases]}"
    )
    assert all(c["cost_usd"] == 0.0 for c in cases), (
        f"expected all cost_usd=0.0; got {[c['cost_usd'] for c in cases]}"
    )

    # AC-COV-3: aggregate invariants on the warm rerun.
    assert agg["complete"] is True
    assert agg["isolation_class"] == "subprocess"
    assert agg["chain_head"], "chain_head must be truthy on a complete warm rerun"

    # Chain head equals the on-disk record.
    records = sorted(tmp_runs.glob("*.json"))
    assert len(records) == 2, f"expected exactly 2 records (cold + warm); got {len(records)}"
    on_disk = json.loads(records[-1].read_text())
    assert on_disk["chain_head"] == agg["chain_head"], (
        "stdout chain_head must equal on-disk record's chain_head (S4-02 AC-10)"
    )

    # AC-1 wall-clock — split budget (F-COV-5).
    assert elapsed <= 12.0, (
        f"warm rerun took {elapsed:.2f}s; hard ceiling 12.0s (50% headroom over §Step 5 target)"
    )
    if elapsed > 8.0:
        warnings.warn(
            f"warm rerun took {elapsed:.2f}s; §Step 5 target is ≤ 8.0s — regression diagnostic",
            stacklevel=2,
        )
```

Test file path: `tests/integration/eval/test_cache_invalidation.py`

```python
# tests/integration/eval/test_cache_invalidation.py
"""Cache invalidation contract: rubric edit invalidates all; case edit triggers
the structural digest defense (exit 6); re-signed case edit invalidates exactly one.
ADR-0002 §Consequences + S2-02 HARDENED + S4-01 HARDENED EXIT_DIGEST_MISMATCH=6."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from codegenie.eval.cli import eval_group


REPO_ROOT = Path(__file__).parents[3]
REAL_BENCH = REPO_ROOT / "bench" / "vuln-remediation"
SIGN_SCRIPT = REPO_ROOT / "scripts" / "sign_bench_digests.py"


def _isolate_bench(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Return (tmp_runs, tmp_bench, tmp_cache, tmp_bench / 'vuln-remediation')."""
    tmp_bench = tmp_path / "bench"
    tmp_bench.mkdir()
    bench_root = shutil.copytree(REAL_BENCH, tmp_bench / "vuln-remediation")
    return tmp_path / "runs", tmp_bench, tmp_path / "cache", bench_root


def _invoke(tmp_runs: Path, tmp_bench: Path, tmp_cache: Path) -> object:
    return CliRunner(mix_stderr=False).invoke(
        eval_group,
        [
            "run",
            "--task-class=vuln-remediation",
            "--out", str(tmp_runs),
            "--bench-root", str(tmp_bench),
            "--cache-dir", str(tmp_cache),
            "--format=jsonl",
        ],
        catch_exceptions=False,
    )


def _per_case(result) -> list[dict]:
    return [
        json.loads(line)
        for line in result.stdout.splitlines()
        if line.strip() and json.loads(line)["kind"] == "case"
    ]


def test_whitespace_edit_to_rubric_invalidates_all_ten(tmp_path: Path) -> None:
    tmp_runs, tmp_bench, tmp_cache, bench_root = _isolate_bench(tmp_path)

    # Cold: warm the cache.
    cold = _invoke(tmp_runs, tmp_bench, tmp_cache)
    assert cold.exit_code == 0, f"cold failed: {cold.stderr}"

    # Mutate rubric.py inside the isolated tree.
    rubric = bench_root / "rubric.py"
    rubric.write_bytes(rubric.read_bytes() + b"\n# cache-bust\n")

    # Rerun: rubric_digest changed → all 10 cache_keys differ → 0 cache hits.
    warm = _invoke(tmp_runs, tmp_bench, tmp_cache)
    assert warm.exit_code == 0, f"warm-after-rubric-edit failed: {warm.stderr}"
    cases = _per_case(warm)
    assert len(cases) == 10
    cache_hits = sum(1 for c in cases if c["cache_hit"] is True)
    assert cache_hits == 0, (
        f"expected 0 cache hits after rubric edit; got {cache_hits}/10; "
        f"cache_hit per case: {[(c['case_id'], c['cache_hit']) for c in cases]}"
    )


def test_whitespace_edit_to_one_case_input_raises_digest_mismatch(tmp_path: Path) -> None:
    tmp_runs, tmp_bench, tmp_cache, bench_root = _isolate_bench(tmp_path)

    # Cold: warm the cache.
    cold = _invoke(tmp_runs, tmp_bench, tmp_cache)
    assert cold.exit_code == 0, f"cold failed: {cold.stderr}"

    # Pick one case to mutate.
    target_dir = next(
        d for d in (bench_root / "cases").iterdir()
        if d.is_dir() and (d / "case.toml").exists()
    )
    target_id = target_dir.name
    input_file = next(p for p in (target_dir / "input").rglob("*") if p.is_file())
    input_file.write_bytes(input_file.read_bytes() + b"\n")

    # Rerun: case_digest now mismatches digests.yaml → loader raises
    # BenchCaseDigestMismatch → main() maps to exit 6.
    result = _invoke(tmp_runs, tmp_bench, tmp_cache)
    assert result.exit_code == 6, (
        f"expected exit 6 (EXIT_DIGEST_MISMATCH); got {result.exit_code}; "
        f"stderr={result.stderr[-1000:]}"
    )
    assert target_id in result.stderr, (
        f"diagnostic must name the offending case_id {target_id!r}; "
        f"stderr={result.stderr[-1000:]}"
    )


def test_resigned_single_case_invalidates_only_that_case(tmp_path: Path) -> None:
    """AC-SINGLE-RESIGN — the cache-key composition gate.

    After re-signing digests.yaml, the cache miss should fall on exactly one case
    (the edited one). Nine cache hits, one cache miss. This exercises the
    case_digest input to compose_cache_key (S2-03 per-field uniqueness AC, but
    against a real bench)."""
    tmp_runs, tmp_bench, tmp_cache, bench_root = _isolate_bench(tmp_path)

    # Cold: warm the cache.
    cold = _invoke(tmp_runs, tmp_bench, tmp_cache)
    assert cold.exit_code == 0, f"cold failed: {cold.stderr}"

    # Mutate one case.
    target_dir = next(
        d for d in (bench_root / "cases").iterdir()
        if d.is_dir() and (d / "case.toml").exists()
    )
    target_id = target_dir.name
    input_file = next(p for p in (target_dir / "input").rglob("*") if p.is_file())
    input_file.write_bytes(input_file.read_bytes() + b"\n")

    # Re-sign digests.yaml via the operator-side script (S5-05 F-DP-2 — Open/Closed
    # parameterized; this subprocess invocation is orthogonal to F-CON-2 because
    # the script does not require any in-process SUT registry).
    sign_result = subprocess.run(
        [
            sys.executable, str(SIGN_SCRIPT),
            "--task-class=vuln-remediation",
            "--bench-root", str(tmp_bench),
        ],
        capture_output=True, text=True, check=False,
    )
    assert sign_result.returncode == 0, (
        f"sign_bench_digests.py failed: stderr={sign_result.stderr}"
    )

    # Rerun: case_digest matches digests.yaml again; the cache key for THIS
    # case changed; the other 9 keys are unchanged.
    result = _invoke(tmp_runs, tmp_bench, tmp_cache)
    assert result.exit_code == 0, f"resigned rerun failed: {result.stderr}"

    cases = _per_case(result)
    assert len(cases) == 10
    hits = [c for c in cases if c["cache_hit"] is True]
    misses = [c for c in cases if c["cache_hit"] is False]
    assert len(hits) == 9 and len(misses) == 1, (
        f"expected exactly 9 hits + 1 miss; got {len(hits)} hits, {len(misses)} misses"
    )
    assert misses[0]["case_id"] == target_id, (
        f"the missed case must be the edited one; "
        f"expected={target_id!r}, missed={misses[0]['case_id']!r}"
    )
```

Test file path: `tests/unit/eval/test_cache_hit_property.py`

```python
# tests/unit/eval/test_cache_hit_property.py
"""AC-PROPERTY-HIT-IMPLIES-ZERO-COST — Pydantic model-validator pin.
Any construction with cache_hit=True and cost_usd > 0 raises ValidationError.
Hypothesis sweeps the BenchScore shape; survivors all satisfy the invariant."""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from codegenie.eval.models import BenchScore


@st.composite
def _benchscores(draw) -> BenchScore:
    cache_hit = draw(st.booleans())
    # If cache_hit, force cost_usd=0.0 so construction succeeds; the property
    # test then verifies the invariant. The "constructed shape" branch is the
    # one we care about — we want to draw lawful BenchScores and observe the
    # invariant holds. The opposite-direction test (illegal raises) is below.
    cost_usd = 0.0 if cache_hit else draw(st.floats(min_value=0.0, max_value=1000.0, allow_nan=False))
    return BenchScore(
        passed=draw(st.booleans()),
        score=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
        breakdown={},
        failure_modes=(),
        cost_usd=cost_usd,
        wall_clock_ms=draw(st.integers(min_value=0, max_value=10_000)),
        cache_hit=cache_hit,
    )


@given(score=_benchscores())
def test_cache_hit_true_implies_zero_cost(score: BenchScore) -> None:
    assert (not score.cache_hit) or score.cost_usd == 0.0


def test_cache_hit_true_with_nonzero_cost_raises() -> None:
    with pytest.raises(ValidationError, match="cache_hit"):
        BenchScore(
            passed=True, score=0.5, breakdown={}, failure_modes=(),
            cost_usd=0.01, wall_clock_ms=10, cache_hit=True,
        )


def test_cache_hit_false_with_nonzero_cost_is_lawful() -> None:
    """Fresh execution: cache_hit=False, cost_usd>0 is the normal case."""
    score = BenchScore(
        passed=True, score=0.5, breakdown={}, failure_modes=(),
        cost_usd=0.01, wall_clock_ms=10, cache_hit=False,
    )
    assert score.cache_hit is False
    assert score.cost_usd == 0.01
```

Run all three; confirm failures (expected: `AttributeError: BenchScore has no field 'cache_hit'`, or `c["cache_hit"]` KeyError on the parse). Commit as red marker.

### Green — smallest impl shape

1. Land `BenchScore.cache_hit: bool = Field(default=False, ...)` and the `model_validator` in `src/codegenie/eval/models.py` per §Implementation outline step 2.
2. Stamp `cache_hit=True` in the runner's cache-probe branch per §Implementation outline step 3.
3. Confirm the CLI's flat per-case JSONL automatically surfaces the new field (because `BenchScore.model_dump()` now includes it; S4-02's `_emit_jsonl` dumps each per-case `BenchScore` flat).
4. Run the three test files; confirm green.
5. Confirm cache invalidation works as designed: a `rubric.py` edit in `tmp_bench` changes `rubric_digest`, which is one input to every per-case cache key — all 10 keys differ → all 10 are cache misses. The structural defense (S2-02 loader) catches a `case.toml`/`input/` edit not reflected in `digests.yaml` and raises `BenchCaseDigestMismatch`.
6. Run `scripts/sign_bench_digests.py` in the AC-SINGLE-RESIGN test to re-sign `digests.yaml`; the cache-key for that one case changes; the other 9 stay unchanged — 9 hits + 1 miss.

### Refactor — clean up

- Update `bench/vuln-remediation/README.md` "Cache behavior" section per AC-README-CACHE-BEHAVIOR.
- The `cache_hit` field is now part of the wire contract; document it on `BenchScore`'s docstring + the README.
- The 8 s warm-budget is the §Step 5 floor; the 12 s hard ceiling absorbs CI flake (F-COV-5). The diagnostic `warnings.warn(...)` between 8 and 12 surfaces drift without flaking.
- Cross-reference S7-02's "audit chain extension integration" test — both consume the autouse conftest from `tests/fixtures/sut/conftest.py`; do **not** define a parallel `fresh_eval_env` fixture (AC-CONFTEST-REUSE). The `tmp_path`-based bench/runs/cache trio is short enough to inline at the top of each test; extraction is rule-of-three-deferred (see §Notes for the implementer §F-DP-4).

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/eval/test_cache_hit_rate.py` | **New** — AC-1 warm-rerun 100% cache hit + split wall-clock budget + AC-COV-3 aggregate invariants + AC-JSONL-FLAT-SHAPE |
| `tests/integration/eval/test_cache_invalidation.py` | **New** — AC-2 (rubric edit invalidates all), AC-3 (case input edit → exit 6 structural defense), AC-SINGLE-RESIGN (re-signed case edit → 9 hits + 1 miss) |
| `tests/unit/eval/test_cache_hit_property.py` | **New** — AC-PROPERTY-HIT-IMPLIES-ZERO-COST Hypothesis property + direct constructor checks |
| `src/codegenie/eval/models.py` | **Extend** — add `BenchScore.cache_hit: bool = False` + `model_validator` (AC-CACHE-HIT-FIELD); extension-by-addition only |
| `src/codegenie/eval/runner.py` | **Extend** — stamp `cache_hit=True` in the cache-probe branch (AC-RUNNER-STAMP) |
| `bench/vuln-remediation/README.md` | **Extend** — `## Cache behavior` section per AC-README-CACHE-BEHAVIOR (verbatim six-input list + signed-content-addressed phrasing) |
| `tests/snapshots/bench_run_report.v1.json` (if extant) | **Regen** — `cache_hit` field surfaces in JSON; if S7-02 already shipped, run `python scripts/regen_eval_snapshot.py` |

Files **NOT** touched (extension-by-addition discipline):
- `tests/fixtures/sut/conftest.py` — S5-05 AC-CONFTEST-REGISTRATION is reused (AC-CONFTEST-REUSE).
- `tests/fixtures/sut/deterministic_vuln_sut.py` — S5-05 fixture is reused.
- `src/codegenie/eval/cli.py` — flat JSONL shape already dumps every `BenchScore.model_dump()` field at the top level; the new `cache_hit` surfaces automatically.
- `src/codegenie/eval/cache.py` — `compose_cache_key` already routes through `rubric_digest`; no change to the composer is needed for AC-2 / AC-SINGLE-RESIGN. If the test reveals the key is missing an input, that's a bug for S2-03 to fix (do NOT kludge the test — surface to S2-03's executor).

## Out of scope

- **SUT-digest / cassette-corpus-digest / harness-version invalidation.** S2-03 HARDENED's per-field uniqueness + positional-swap-resistance unit tests already cover these inputs at the cache-key composer boundary. Integration-level coverage is deferred to Phase 7+ when the real SUT lands and `sut_digest` changes meaningfully (the stub SUT's `sut_digest` is a hand-coded constant).
- **Hypothesis property tests for cache-key determinism over arbitrary inputs.** Listed in `phase-arch-design.md §Property tests`; lives under S2-03 (`tests/unit/eval/test_cache.py`); this story is the *integration*-level concretization on real bench inputs.
- **Cache GC behavior.** S2-03's `gc(retain_days=90)` is unit-tested there; not in scope.
- **Cross-host cache sharing.** Gap #5 (parallel-eval across hosts) is deferred to Phase 13; the cache is per-host in Phase 6.5.
- **Concurrent eval-run race.** Edge case #17 is fence-CI / runner-level; `fcntl.flock` serializes writers but the integration test does not exercise concurrency here.
- **`--sut-module=<dotted>` CLI extension.** Surfaced by S5-05 F-TQ-2 as a Phase-7+ candidate so subprocess-spawn integration tests could reach a test SUT through a fresh `sys.modules`. NOT this story's job.
- **`_assert_all_cache_hits` / `_assert_zero_cache_hits` helper extraction.** Rule-of-three deferred to S6-03 (distroless cache-hit test would be the third consumer); see §Notes §F-DP-4.

## Notes for the implementer

- **Wire-field vs span-attribute decision (F-DP-1).** The arch's §Process view line 856 names `cache_hit: bool` as a span/log attribute. This story promotes it to a `BenchScore` wire field for three reasons: (a) the per-case JSONL is the integration test's only observable surface (logs/spans are not asserted in CI), (b) the audit chain's `BenchRunReport.per_case` already carries `tuple[(case_id, BenchScore), ...]` — making `cache_hit` a `BenchScore` field places it on the existing wire contract by addition rather than introducing a parallel sidecar dict, (c) the Pydantic `model_validator` makes the illegal combination `cache_hit=True and cost_usd > 0` unrepresentable at construction time. Span attribute coverage is orthogonal and can land in a future observability story.

- **Model-validator fallback.** If `phase-architect` review finds the `@model_validator(mode="after")` raises on a legitimate edge case (e.g., a cost-cap partial report where `complete=False` ships a `cache_hit=False, cost_usd > 0` mix and the validator should allow it — currently lawful), the validator stays as-is. If the validator is rejected outright (e.g., a future SUT charges sub-cent invocations even on warm cache for telemetry reasons), fallback path: drop the validator, keep the field, and pin the invariant via the Hypothesis property test only. Document the gap with a one-line comment.

- **F-COV-4: the two single-case interpretations.**
  1. **Structural digest defense (AC-3, primary).** Edit `input/`/`expected/` of one case → `case_digest` recomputation by loader → mismatch with `digests.yaml` → `BenchCaseDigestMismatch` (exit 6). The cache never gets a chance to serve a stale entry because the loader refuses the case. This is the load-bearing test — the signed-content-addressed contract.
  2. **Cache-key composition (AC-SINGLE-RESIGN, secondary).** Re-sign `digests.yaml` after the case edit → `case_digest` matches → cache key includes the new `case_digest` → cache miss for *this* case only → 1 SUT re-invocation, 9 cache hits. Exercises the per-case input to `compose_cache_key`.

  Both are load-bearing; (1) tests the loader's structural defense, (2) tests the cache-key composer. The story's High-level-impl.md §Step 5 phrasing ("whitespace edit to one case.toml invalidates exactly that case") is ambiguous between them — this story tests both.

- **F-COV-5: wall-clock budget split.** §Step 5's 8 s target is the *aspirational* warm-rerun budget. Hard-failing at 8 s would flake on contended CI runners (SSD I/O variance + interpreter cold-start + Click's import cascade). The split (`≤ 12.0` hard / `≤ 8.0` regression diagnostic) gives 50% headroom while still surfacing drift. If the diagnostic fires on three consecutive CI runs, profile cold-imports per S4-01's "deferred heavy imports" discipline.

- **F-DP-4 rule-of-three trigger (helper extraction).** This story has two integration tests; the cache-state assertions inline are ≤ 5 lines each. If S6-03 (distroless E2E cache-hit test) ships a third consumer, extract `tests/integration/eval/_cache_helpers.py::assert_all_cache_hits(cases)` and `assert_zero_cache_hits(cases)`. Until then, inline.

- **AC-CONFTEST-REUSE: no parallel `fresh_eval_env` fixture.** S5-05 AC-CONFTEST-REGISTRATION already ships the autouse SUT-registration seam at `tests/fixtures/sut/conftest.py`. Confirm the conftest's scope covers `tests/integration/eval/`. If it does not (e.g., the conftest currently scopes to `tests/integration/eval/` but a future move broke it), move the conftest up to `tests/fixtures/sut/conftest.py` or `tests/integration/conftest.py` and re-test all S5-05 tests. **Do not** duplicate the registration logic in this story's tests.

- **AC-JSONL-FLAT-SHAPE: per-case JSONL is flat.** S4-02 AC-10 ships per-case lines as `{"kind":"case", "case_id":..., "score":float, "passed":bool, "breakdown":{...}, "failure_modes":[...], "cost_usd":float, "wall_clock_s":float}`. The new `cache_hit` field surfaces at the top level the same way (`c["cache_hit"]`). Tests MUST NOT access `c["score"]["cost_usd"]` or any nested form — `c["score"]` is the scalar (`BenchScore.score: Field(ge=0, le=1)`).

- **Field name correctness — `wall_clock_s` (not `wall_clock_ms`).** S4-02 AC-10 ships the JSONL field as `wall_clock_s` (seconds, float). The `BenchScore` model has `wall_clock_ms: int` internally; the JSONL emission converts to seconds. Tests asserting `wall_clock_*` must use the JSONL name.

- **`shutil.copytree` cost.** Copying `bench/vuln-remediation/` (10 cases, each with `input/`, `expected/`, `case.toml`) is small (< 1 MB total). Each integration test does this once; pytest's `tmp_path` cleans up automatically. Total per-test fixture cost ≈ 50 ms — well inside the wall-clock budget.

- **`cache-bust` edit must change byte content, not `mtime`.** The cache is content-addressed (BLAKE3 over inputs); `touch rubric.py` would NOT invalidate. The test appends `b"\n# cache-bust\n"` — actual byte change. Document this in the test comment.

- **Stub-SUT determinism.** `tests/fixtures/sut/deterministic_vuln_sut.py` (from S5-05) must produce byte-stable `harness_output` for each case across runs, else the integration test appears to pass spuriously (the cache might serve stale entries that happen to match). S5-05 AC-STUB-DIST asserts this via the aggregate-distribution invariants; if a regression surfaces here as flaky AC-1, suspect stub-SUT determinism first.

- **If a rubric edit doesn't invalidate.** That is a bug in S2-03 — `compose_cache_key` is missing `rubric_digest` as an input. Surface to S2-03's executor; do NOT kludge this story's test. AC-2's failure mode (`cache_hits != 0` after rubric edit) names S2-03 explicitly in the diagnostic message.

- **Snapshot regen (housekeeping).** If S7-02's `tests/snapshots/bench_run_report.v1.json` has already shipped, the new `cache_hit` field surfaces as a JSON-byte drift in the snapshot comparison. Run `python scripts/regen_eval_snapshot.py` and commit the regen alongside this story's changes with a one-line note. If S7-02 has not yet shipped (likely — S7-02 is the same Step 7 fence-CI step that depends on S5-06), this step is a no-op.
