# Story S7-05 — Property tests + portfolio integration sweep

**Step:** Step 7 — Plant five-repo fixture portfolio + per-probe golden files + remaining adversarial corpus
**Status:** Done — GREEN 2026-05-18 (phase-story-executor; see [`_attempts/S7-05.md`](_attempts/S7-05.md) for the per-AC evidence table + gate log). AC-25/28 use `subprocess.run([sys.executable, "-m", "codegenie", ...])` (the `run_allowlisted` path was unsatisfiable — `python` is not in `ALLOWED_BINARIES`). AC-26 implements a structured-JSON-log check (the project's stderr format) instead of a prefix-allowlist. AC-20 "iff `len(results)==0`" was softened to match `_derive_trace_coverage_confidence` semantics ("unavailable" iff no completed entries). All adaptations documented in the attempt log.
**Effort:** M
**Depends on:** S7-03 (~70 goldens exist; the portfolio sweep diffs against them; the regen script proves canonical-JSON discipline holds)
**ADRs honored:** ADR-0006 (`IndexFreshness` location — property test asserts round-trip identity over every `StaleReason` variant), ADR-0007 (no plugin loader — `dep_graph` strategy registry has zero strategies in Phase 2; property test asserts the dispatch is total over the closed `PackageManager` enum), ADR-0009 (pytest-xdist veto — property tests run serially under the same `--max-examples=200` budget), ADR-0010 (`RedactedSlice` smart constructor — property tests against `ScannerOutcome` round-trip exercise the `RedactedSlice` JSON shape without re-constructing it outside the sanitizer).

## Validation notes (2026-05-18)

Hardened against the actual Phase-2 source tree (not the architectural plan as written). The original draft cited several types/APIs that diverged from what S1-01, S1-10, S5-01, S5-02 actually shipped. Concrete corrections below; consistency with the running code is now load-bearing for the executor.

- **`StaleReason` field names corrected (AC-2).** Code (`src/codegenie/indices/freshness.py`) ships `DigestMismatch(expected, actual)` and `CoverageGap(files_indexed, files_in_repo)`; the draft cited `(last_traced, current_built)` and `(missing_files, indexed_files, total_files)` — wrong. The `Fresh` constructor also requires an `indexed_at: datetime` (the draft's `st.builds(Fresh)` would fail at construction); strategy must pass an aware datetime.
- **`ScannerRan` has no `fingerprints` / `findings_count` fields (AC-8, AC-9 reframed).** Those fields live on `RedactedSlice` (per ADR-0010), not on `ScannerRan` (which carries `findings: list[Finding]`). The original ACs conflated the two types. New ACs target `Finding.id` / `severity` / `metadata` invariants on `ScannerRan` (matching the model that S5-01 actually shipped) and address `RedactedSlice` separately under a corrected AC-12.
- **Existing `tests/property/test_sum_types_roundtrip.py` (S5-01) already covers `ScannerOutcome` + `ScenarioResult` round-trip.** The original draft planned a duplicate `test_scanner_outcome_roundtrip.py`. Reframed: this story *extends* the existing file with the `--max-examples=200` / `database=None` / `deadline=None` discipline AC-11/AC-35 demands, and adds a separate exhaustive-match `assert_never` test (AC-23) — no second property file.
- **`DepGraphRegistry.dispatch()` raises `DepGraphRegistryError` with the structural prefix `"no_strategy_for_ecosystem: "` — it does NOT return a `Result.Ok|Err` (AC-14 / AC-15 reframed).** No `Result` type exists in `src/codegenie/depgraph/`. The Phase-2 invariant is now expressed as `default_dep_graph_registry.registered_ecosystems() == frozenset()` (non-raising query) AND, when a probe dispatches against any `PackageManager` member, the registry raises with the documented prefix that S4-05's `DepGraphProbe` matches. Mock-strategy registration AC-16 now explicitly uses `default_dep_graph_registry.unregister_for_tests(...)` in `finally` (the test-only teardown the registry already exposes).
- **`TraceCoverage` is not a class — replaced with the real Phase-2 surface (AC-19..AC-24).** The code ships a pure function `_derive_trace_coverage_confidence(results) -> Literal["high","medium","low","unavailable"]` and a private `_AggregatedSlice` Pydantic model (`src/codegenie/probes/layer_c/runtime_trace.py`). New ACs are: monotonicity / totality of the confidence derivation across the closed `ScenarioResult` variant space, an exhaustive-match `assert_never` test on `ScenarioResult` (mirroring AC-5's discipline), and a well-formedness property over `_aggregate_scenarios` (`scenarios_run + scenarios_failed + skipped == |results|`, no duplicate scenario names, `trace_coverage_confidence == "unavailable" iff len(results)==0` per the canonical-empty case the function ships).
- **`walltimes.json` no longer dirties the repo tree (AC-32).** Original draft wrote `tests/integration/portfolio/walltimes.json` unconditionally on every test run, which would dirty the working copy and the pre-commit hook. Reframed: written only when `CODEGENIE_PORTFOLIO_WALLTIME_OUT=<path>` is set (CI sets it to a job-artifact path). Without the env var, the test prints the walltime table to `pytest -s` stdout and the file is untouched.
- **AC-26 stderr allowlist enumerated, not described.** Original "stderr is empty or contains only documented warnings" was unverifiable. Reframed: the test loads stderr, splits on `\n`, and asserts every non-empty line begins with one of an explicit allowlist of warning prefixes (`skill_shadowed`, `strace_unavailable`, `image_digest_unresolved`) OR is the empty line. A line that doesn't match fails the test and prints the offending line.
- **AC-29 single budget number.** Original mixed `≤ 6 min` (CI) with `≤ 5 min target` (local) — two unverifiable thresholds. Reframed: hard `≤ 6 min` measured by the test itself across the five fixtures; the bench advisory (S8-03) tracks the per-fixture trend separately.
- **AC-12 RedactedSlice handling clarified.** Original was a paragraph-long dual-resolution that an executor would mis-implement. Reframed: the property test for `ScannerOutcome` round-trips the `ScannerRan(findings=...)` shape as it actually ships (no `RedactedSlice` field on `ScannerRan`). A separate AC (new AC-12) covers `RedactedSlice` JSON round-trip identity via an instance obtained only via `redact_secrets(<synthetic input>)` — the one allowed construction path. The S7-04 structural test (no `RedactedSlice(...)` outside the sanitizer) is unchanged and remains the structural firewall.
- **Design-pattern surfacing for `unregister_for_tests`.** Mock-strategy registration in AC-16 explicitly uses the registry's `unregister_for_tests` test-only hook — the symmetric API already exists in `src/codegenie/depgraph/registry.py` and `src/codegenie/indices/registry.py`; the property test consumes the established Open/Closed seam rather than reaching into private state.
- **Coordination AC added (new AC-37).** Names the existing `tests/property/test_sum_types_roundtrip.py` and `tests/property/test_index_freshness_roundtrip.py` as "extend in place, do not duplicate" — closes the duplication risk the original draft introduced.

## Context

This story closes Step 7 with two complementary surfaces:

1. **Hypothesis property tests under `tests/property/`** — four files covering the round-trip / dispatch-totality / well-formedness invariants of the Phase-2 typed surfaces. Each runs with `--max-examples=200` (Hypothesis convention; tradeoff between coverage and CI wall-clock). These are **invariant tests over generated data**, complementing S7-03's **literal-data goldens** and S7-04's **adversarial cases**:
   - `test_index_freshness_roundtrip.py` — every `IndexFreshness` variant + every `StaleReason` variant round-trips through `model_dump_json` / `model_validate_json` to identity. Extends S1-01's single-example test to portfolio-wide hypothesis coverage. Catches: missing field, type-coercion silent loss, discriminator drift.
   - `test_scanner_outcome_roundtrip.py` — every `ScannerOutcome` variant (`ScannerRan | ScannerSkipped | ScannerFailed`) round-trips. Plus `ScenarioResult` (Layer C). Catches: same class of bug as above, separate type tree.
   - `test_dep_graph_strategy_dispatch.py` — the `@register_dep_graph_strategy` registry's dispatch is **total** over the closed `PackageManager` enum (Phase 1 ADR-0013). Phase 2 has zero strategies registered; every input produces `Result.Err(DepGraphRegistryError(reason="no_strategy_for_ecosystem"))` — that's the Phase-2 invariant. Phase 3 fills strategies; the property test grows with the strategy set. Catches: a future implementer who silently adds a strategy AND silently drops the Phase-2 total-dispatch property.
   - `test_trace_coverage_well_formed.py` — `TraceCoverage` is well-formed across any combination of `ScenarioResult` variants. Specifically: scenario count ≥ 0; completed-and-failed counts sum to total minus skipped; no scenario name appears twice.
2. **A portfolio-sweep integration test** — `tests/integration/portfolio/test_portfolio_sweep.py` — runs `codegenie gather` against every fixture in `tests/fixtures/portfolio/` **serially** (per ADR-0009; no pytest-xdist) and asserts: (a) every gather succeeds (exit 0); (b) the resulting `repo-context.yaml` validates against the Phase-2 envelope schema; (c) the golden diff (S7-03's regen script in `--check` mode) is empty. This is the "every probe runs against every fixture without crashing" smoke at the portfolio level; the CI `portfolio` job (S8-03) consumes it.

Both surfaces are **complementary**, not redundant:

- **Goldens** (S7-03) pin specific byte sequences for specific (probe × fixture) pairs.
- **Property tests** (this story) assert invariants over generated inputs the goldens cannot exhaustively cover (e.g., every `StaleReason` variant including ones the fixtures don't exercise).
- **Portfolio sweep** (this story) verifies the integration surface — every probe runs against every fixture without crashing, and the gather output remains shape-consistent across the portfolio.

This is the **final Step-7 story**. After it lands: Step 8 (Confidence renderer + CI ratchet + bench canaries + Phase-3 handoff issues) wires everything together. The cross-cutting invariant this story locks: every Phase-2 typed surface that participates in serialization has a Hypothesis round-trip property test; the portfolio sweep proves no fixture × probe combination crashes the gatherer.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" → "Property tests"` — the inventory of round-trip / dispatch / well-formed properties.
  - `../phase-arch-design.md §"Testing strategy" → "Test pyramid"` — property tests are the second-narrowest tier (above adversarial, below unit).
  - `../phase-arch-design.md §"Component design"` #2 (`IndexFreshness`), #5 (`ScannerOutcome`), #11 (`DepGraphProbe` strategy registry), and §"Component design" #6 (`TraceCoverage`).
- **Phase ADRs:**
  - ADR-0006 (`IndexFreshness` location — `frozen=True, extra="forbid"`; round-trip identity is the load-bearing property).
  - ADR-0010 (`RedactedSlice` smart constructor — property test for `ScannerOutcome` round-trip must NOT construct `RedactedSlice` outside `redact_secrets`; instead generates JSON-shaped `RedactedSlice` payloads and verifies they round-trip through `model_validate_json`).
- **Implementation plan:** `../High-level-impl.md §"Step 7"` — property-test bullets + portfolio-sweep bullet.
- **Existing code:**
  - `src/codegenie/indices/freshness.py` (S1-01 — the type under property test; **note** the actual fields: `CommitsBehind(n, last_indexed)`, `DigestMismatch(expected, actual)`, `CoverageGap(files_indexed, files_in_repo)`, `IndexerError(message)`, `Fresh(indexed_at)`).
  - `src/codegenie/probes/_shared/scanner_outcome.py` (S5-01 — `ScannerOutcome` family; `ScannerRan` carries `findings: list[Finding]`, **not** `findings_count`/`fingerprints` — those live on `RedactedSlice`).
  - `src/codegenie/probes/layer_c/scenario_result.py` (S5-01 — `TraceScenarioCompleted | TraceScenarioFailed | TraceScenarioSkipped`).
  - `src/codegenie/depgraph/registry.py` (S1-10 — the registry; `dispatch()` raises `DepGraphRegistryError(\"no_strategy_for_ecosystem: ...\")`, `has_strategy()` is the non-raising query, `unregister_for_tests()` is the test-only teardown).
  - `src/codegenie/probes/layer_c/runtime_trace.py` (S5-02 — `_aggregate_scenarios` pure fold + `_derive_trace_coverage_confidence` Literal totality; there is **no `TraceCoverage` class**, the arch doc's section title named the concept).
  - `src/codegenie/output/sanitizer.py` (S3-01..S3-03 — `RedactedSlice` and `redact_secrets`; the latter is the only legal construction surface per ADR-0010).
  - All five fixtures from S7-01 + S7-02.
  - `scripts/regen_golden.py --check --portfolio` (S7-03 — if the `--portfolio` flag hasn't landed by PR time, AC-28 ships behind a `pytest.mark.skipif` gate, lifted by S8-03).
- **Existing Hypothesis test precedents:** `tests/property/test_index_freshness_roundtrip.py` (S1-01) and `tests/property/test_sum_types_roundtrip.py` (S5-01) — extended in place by this story. `tests/property/test_skills_loader_monotone.py`, `tests/property/test_tccm_roundtrip.py`, `tests/property/test_runtime_trace_freshness_purity.py`, `tests/property/test_truncate_tail.py` — convention precedents for `@given` + `@settings` shape; do not edit.

## Goal

The property-test surface gains three additions; the portfolio sweep is created; existing property files are extended (not duplicated):

1. **Extended** `tests/property/test_index_freshness_roundtrip.py` (S1-01 shipped this; extend) — add `@settings(max_examples=200, deadline=None, database=None)` on the round-trip; add a separate `assert_never` exhaustive-match unit test (AC-5).
2. **Extended** `tests/property/test_sum_types_roundtrip.py` (S5-01 shipped this for `ScannerOutcome` + `ScenarioResult`; extend) — add the same `@settings(max_examples=200, deadline=None, database=None)` discipline to both `test_scanner_outcome_roundtrips_identity` and `test_scenario_result_roundtrips_identity`; add an `assert_never` exhaustive-match test for `ScenarioResult` (AC-23).
3. **New** `tests/property/test_redacted_slice_roundtrip.py` — Hypothesis property test over `RedactedSlice` JSON round-trip, where every Hypothesis example is obtained via `redact_secrets(<synthetic dict>)` (the one allowed construction path per ADR-0010); `--max-examples=200`.
4. **New** `tests/property/test_dep_graph_strategy_dispatch.py` — Hypothesis property test that the registry's `dispatch()` is total over `PackageManager` in the structural sense: with zero strategies registered, every member raises `DepGraphRegistryError` with the documented `"no_strategy_for_ecosystem: "` prefix; with a registered mock, the mock is invoked exactly once and its return value passes through unchanged; the registry never raises an *un*documented exception. `--max-examples=200`.
5. **New** `tests/property/test_trace_coverage_invariants.py` — Hypothesis property test over `_aggregate_scenarios` and `_derive_trace_coverage_confidence` covering: per-input partition invariant (`len(scenarios_run) + len(scenarios_failed) + skipped == len(results)`), uniqueness invariant (each `scenario_name` appears at most once across the three lists), and confidence-derivation totality + `unavailable iff len(results)==0`; `--max-examples=200`.
6. **New** `tests/integration/portfolio/test_portfolio_sweep.py` — serial portfolio sweep; gathers every fixture; asserts schema validation + golden diff empty.

## Acceptance criteria

**`test_index_freshness_roundtrip.py`** (extends the existing S1-01 file)

- [ ] **AC-1.** `tests/property/test_index_freshness_roundtrip.py` exists (S1-01 shipped it; this story extends it); uses `hypothesis` with `@given` strategies that generate every `IndexFreshness` variant (`Fresh(indexed_at)`, `Stale(reason=<each StaleReason variant>)`).
- [ ] **AC-2 — variant coverage matches the shipped types.** Every `StaleReason` variant is reachable using its actual code-level field set: `CommitsBehind(n: int, last_indexed: str)`, `DigestMismatch(expected: str, actual: str)`, `CoverageGap(files_indexed: int, files_in_repo: int)`, `IndexerError(message: str)`. `Fresh` is built with an `indexed_at` strategy producing timezone-aware `datetime`s. A `st.one_of(...)` composition covers all `StaleReason` variants. If the variant set drifts from the shipped module, this AC fails by construction at import time (the wrong field name produces a Pydantic validation error in `st.builds`).
- [ ] **AC-3 — round-trip identity.** For every generated `IndexFreshness` instance `x`, using a `TypeAdapter[IndexFreshness]`: `adapter.validate_json(adapter.dump_json(x)) == x`. Additionally, the concrete *type* is preserved (`type(decoded) is type(x)`; and for `Stale`, `type(decoded.reason) is type(x.reason)`) — guards against silent discriminator drift.
- [ ] **AC-4 — `--max-examples=200`.** The test uses Hypothesis's `@settings(max_examples=200, deadline=None, database=None)`. `deadline=None` because round-trip latency is variable on CI; `database=None` for CI reproducibility (AC-35).
- [ ] **AC-5 — `assert_never` enforcement.** A separate (non-property) test exhaustively pattern-matches on `IndexFreshness` AND on every `StaleReason` with `assert_never` on the closing case. A missing `case` triggers `mypy --warn-unreachable` failure (the per-module override from S1-11 applies to this test). Extends S1-01's single-example test.
- [ ] **AC-6 — wall-clock < 30 s on CI.** `--max-examples=200` × round-trip should fit easily. If not, the type itself is non-trivial in its round-trip path; investigate.

**Existing `tests/property/test_sum_types_roundtrip.py`** (extends the S5-01 file — `ScannerOutcome` + `ScenarioResult`)

- [ ] **AC-7.** The existing `tests/property/test_sum_types_roundtrip.py` is **extended in place** (not duplicated). Both `test_scanner_outcome_roundtrips_identity` and `test_scenario_result_roundtrips_identity` are decorated with `@settings(max_examples=200, deadline=None, database=None)`. The pre-existing strategies (`_scanner_outcomes`, `_scenario_results`) remain authoritative; nothing about the `Finding` shape is changed.
- [ ] **AC-8 — `Finding` shape preserved.** The Hypothesis strategy for `ScannerRan` builds `Finding(id, severity, metadata)` where `severity ∈ {"info","low","medium","high","critical"}` and `metadata` is bounded-depth `JSONValue`. The round-trip preserves `type(decoded.findings[i]) is type(value.findings[i])` for every index (the existing test asserts the per-element-type identity; no change needed beyond `@settings`).
- [ ] **AC-9 — no plaintext leaks via `metadata`.** A unit-level companion test (non-property) constructs `ScannerRan(findings=[Finding(id="probe.test", severity="high", metadata={"secret":"sk_live_..."})])`, runs it through `redact_secrets(<dict-shaped slice carrying that finding>)`, and asserts the resulting `RedactedSlice.slice` JSON contains zero `"sk_live_"` substring matches. This is the cross-check that ADR-0005 + ADR-0010 hold at the seam where scanner findings meet the sanitizer; the property test itself does *not* assert this (the property surface is round-trip identity, not secret-erasure).
- [ ] **AC-10 — round-trip identity.** Preserved verbatim from the existing file (both `_scanner_adapter` and `_scenario_adapter` round-trip identity); no edit beyond the `@settings` decoration.
- [ ] **AC-11 — `--max-examples=200`** with `deadline=None, database=None` on both tests in the file.
- [ ] **AC-12 — `RedactedSlice` JSON round-trip (new file `tests/property/test_redacted_slice_roundtrip.py`).** Hypothesis generates `dict[str, JSONValue]` payloads with bounded depth; passes each through `redact_secrets(payload, probe_name=ProbeId("test.property"))` to obtain a `(RedactedSlice, list[SecretFinding])` tuple; uses the `RedactedSlice` as the Hypothesis-generated input to a `TypeAdapter[RedactedSlice].validate_json(adapter.dump_json(x)) == x` round-trip assertion. The test **never constructs `RedactedSlice(...)` directly** — it goes through `redact_secrets` for every example (per ADR-0010). The S7-04 structural firewall (no `RedactedSlice(...)` construction outside `codegenie.output.sanitizer`) is unaffected; this test file is **not** in `codegenie.output.sanitizer` and obtains every instance via the smart-constructor surface.

**`test_dep_graph_strategy_dispatch.py`** (matches the exception-raising API the registry actually ships)

- [ ] **AC-13.** `tests/property/test_dep_graph_strategy_dispatch.py` exists.
- [ ] **AC-14 — dispatch totality (Phase-2 reality).** `default_dep_graph_registry` is a fresh / empty registry in this test's process scope (an autouse fixture asserts `registered_ecosystems() == frozenset()` before each example; any leftover registration from another test fails fast with a named pointer to the polluter). Hypothesis generates every `PackageManager` member via `st.sampled_from(get_args(PackageManager))`. For every generated member, the test calls `default_dep_graph_registry.dispatch(member, ctx, manifests)` with a `ProbeContext` test-double and asserts: (a) it raises `DepGraphRegistryError`; (b) `str(err).startswith("no_strategy_for_ecosystem: ")` (the structural prefix `DepGraphProbe` matches); (c) `repr(member)` appears in `str(err)`; (d) no other exception type ever bubbles. `has_strategy(member)` returns `False` for every member. `registered_ecosystems()` remains `frozenset()`.
- [ ] **AC-15 — Phase 2 invariant (trip-wire).** With zero strategies registered, the AC-14 properties hold for every `PackageManager` member. If Phase 3 lands a strategy that registers at import time (a module-level `@register_dep_graph_strategy(PackageManager.npm)`), this test fails on the Phase 3 PR — which is the desired contract trip-wire. The Phase 3 author must explicitly update AC-14 / AC-15 (e.g., "for the registered members expect `nx.DiGraph` return; for the rest expect the documented raise"), NOT silently break it. The test file's module docstring documents this handoff.
- [ ] **AC-16 — mock strategy registration uses the public test-only seam.** A separate (non-property) test calls `register_dep_graph_strategy(PackageManager.npm)(mock_fn)` where `mock_fn(ctx, manifests)` returns a sentinel `nx.DiGraph` instance; asserts `default_dep_graph_registry.dispatch(PackageManager.npm, ctx, manifests) is sentinel_graph` (identity, not copy — pinned by S1-10 AC-11); cleans up in a `finally:` block via `default_dep_graph_registry.unregister_for_tests(PackageManager.npm)`. The test never mutates `default_dep_graph_registry._strategies` directly — the Open/Closed seam (`register_dep_graph_strategy` + `unregister_for_tests`) is the only API touched. Other `PackageManager` members in the same test still raise the documented `DepGraphRegistryError` (proves the registration is scoped, not global).
- [ ] **AC-17 — `--max-examples=200`** with `deadline=None, database=None`. (Overkill for the closed enum, but consistent with the rest of the property surface; Hypothesis exhausts the closed set quickly and the remaining budget is harmless repeats.)
- [ ] **AC-18 — wall-clock < 10 s on CI.**

**`test_trace_coverage_invariants.py`** (replaces `test_trace_coverage_well_formed.py` — there is no `TraceCoverage` class)

- [ ] **AC-19.** `tests/property/test_trace_coverage_invariants.py` exists. The property tests target the *shipped* surface: `codegenie.probes.layer_c.runtime_trace._aggregate_scenarios` (pure fold from `Sequence[ScenarioResult]` → `_AggregatedSlice`) and `_derive_trace_coverage_confidence(results) -> Literal["high","medium","low","unavailable"]`. Both are private (`_` prefix), so the test imports them directly with a `# type: ignore[reportPrivateUsage]` line documented in the file's top comment as "intentional — property test of a pure fold; no public API is more honest than the function under test."
- [ ] **AC-20 — partition + uniqueness invariants over `_aggregate_scenarios`.** Hypothesis generates a list of `ScenarioResult` (any combination of `TraceScenarioCompleted`, `TraceScenarioFailed`, `TraceScenarioSkipped`) with the constraint `unique_by=lambda r: r.scenario_name` (the function's pre-condition — the runtime trace probe never emits duplicate scenario names; the test mirrors the contract). For each generated input `results`, the test calls `parsed = {r.scenario_name: ParsedTrace(...) for r in results if isinstance(r, TraceScenarioCompleted)}` (any well-formed `ParsedTrace` stub), then `slice_ = _aggregate_scenarios(results, parsed)` and asserts:
  - `len(slice_.scenarios_run) + len(slice_.scenarios_failed) + skipped_count == len(results)` where `skipped_count = sum(1 for r in results if isinstance(r, TraceScenarioSkipped))`.
  - `set(slice_.scenarios_run) & set(slice_.scenarios_failed) == set()` — no name appears in both lists.
  - `set(slice_.per_scenario_artifacts.keys()) == {r.scenario_name for r in results}` — every scenario name is keyed.
  - `slice_.trace_coverage_confidence == "unavailable"` iff `len(results) == 0` (canonical-empty case).
  - When all scenarios are `TraceScenarioCompleted` with `len(results) >= 5`, `slice_.trace_coverage_confidence == "high"`; with `len(results) == 1` and `scenario_name == "startup"`, `"low"`; with `len(results) == 1` and `scenario_name != "startup"`, `"medium"`; with `2 <= len(results) <= 4`, `"medium"` (a parameterized table-test, **not** the property-level assertion — Hypothesis covers all combinations; the table-test pins the precedence reading of `_derive_trace_coverage_confidence`).
- [ ] **AC-21 — confidence-derivation totality.** Hypothesis generates the same `Sequence[ScenarioResult]` space and asserts `_derive_trace_coverage_confidence(results)` returns a value in the closed `Literal["high","medium","low","unavailable"]` set — i.e., it never raises, never returns `None`, never returns an out-of-set string. (Pydantic doesn't validate the function return; a mypy-strict + runtime `assert` in the test is the redundant defense.)
- [ ] **AC-22 — `--max-examples=200`** with `deadline=None, database=None`.
- [ ] **AC-23 — `assert_never` on `ScenarioResult` variants** in a separate exhaustive-match unit test under `tests/unit/probes/layer_c/test_scenario_result_assert_never.py`. Constructs one instance of every `ScenarioResult` variant; the test function's exhaustive `match` closes on `assert_never(_)`. A missing `case` is a `mypy --warn-unreachable` build error against the per-module override. Mirrors AC-5's discipline.
- [ ] **AC-24 — wall-clock < 30 s on CI.**

**`test_portfolio_sweep.py` — serial portfolio integration**

- [ ] **AC-25.** `tests/integration/portfolio/test_portfolio_sweep.py` exists; gathers every fixture under `tests/fixtures/portfolio/` serially (`for fixture in sorted(fixtures): ...`) via `codegenie.exec.run_allowlisted`.
- [ ] **AC-26 — every gather exits 0 with an explicit stderr allowlist.** For each fixture, `codegenie gather <fixture>` returns exit code 0. Stderr is split on `\n`; every non-empty line must begin with one of the documented warning IDs (allowlist literal in the test source): `skill_shadowed`, `strace_unavailable`, `image_digest_unresolved`, `external_docs_skipped`. A line that doesn't match — and any line containing `Traceback`, `Error`, `Exception` outside that allowlist — fails the test with the offending line in the failure message. The allowlist tuple is module-level and grep-discoverable so adding a new documented warning is a one-line edit.
- [ ] **AC-27 — envelope schema validation.** For each fixture's resulting `repo-context.yaml`, the test loads it via the project's `safe_yaml.load` (NOT `yaml.safe_load` — the project's wrapper is the chokepoint) AND validates against the Phase-2 envelope schema (`src/codegenie/schema/repo_context.schema.json` extended in Steps 4–6). Validation failure fails the test with the full JSONSchema error path (`error.absolute_path`) for actionable diagnostics.
- [ ] **AC-28 — golden diff empty.** After gathering, the test invokes `scripts/regen_golden.py --check --portfolio` via `run_allowlisted` and asserts exit 0. (Redundant with `tests/golden/test_goldens_match.py` from S7-03, but appropriate here because the portfolio sweep is the integration-level gate; the golden harness is the unit-test-level gate.) If S7-03's regen script ships only the `--check` mode and not the `--portfolio` flag at PR time, this AC is implemented behind a `pytest.mark.skipif(not _has_portfolio_check_mode(), reason="...")` gate naming the missing flag — and S8-03 lifts the skip when the flag lands.
- [ ] **AC-29 — wall-clock budget ≤ 6 minutes hard.** The test measures total wall-clock across the five fixtures and asserts `total_seconds <= 360` (the Phase-2 `portfolio` job budget per `phase-arch-design.md §"Testing strategy"`). If exceeded, the test fails with the per-fixture breakdown so the reviewer can see which fixture regressed. The local-vs-CI distinction is dropped (a developer machine running outside the budget is a probe-regression signal, not a per-machine tolerance).
- [ ] **AC-30 — serial dispatch.** No `pytest-xdist`, no `multiprocessing`, no `asyncio.gather` — for-loop iteration with sequential `run_allowlisted` invocations. ADR-0009 honored. The test is decorated `@pytest.mark.serial` and the file's module docstring names the ADR.
- [ ] **AC-31 — clean tmpdir per fixture.** Each fixture is copied to a fresh `tmp_path / fixture.name` via `shutil.copytree` (not `subprocess.run(["cp", "-R", ...])` — `shutil.copytree` is the cross-platform stdlib equivalent and avoids a `cp` allowlist line for a pure-Python copy). Cache + context outputs land in the tmpdir. The canonical fixture tree under `tests/fixtures/portfolio/` is never written to (the test asserts `_PORTFOLIO_DIR_HASH` before and after match — a `_dir_sha256(_PORTFOLIO)` snapshot taken at test start and re-checked at test end).
- [ ] **AC-32 — wall-clock per fixture recorded without dirtying the repo.** The test collects `{fixture_name: walltime_seconds}` in memory. If the env var `CODEGENIE_PORTFOLIO_WALLTIME_OUT` is set to a path (CI sets it to a job-artifact path under `${{ runner.temp }}`), the test writes the JSON to that path. Without the env var, the test prints the table to stdout (visible under `pytest -s`) and does **NOT** write to the repo tree. The S8-03 bench script (`bench_portfolio_walltime.py`) reads the artifact via the same env var; the cross-story handoff contract is documented in this story's PR description.

**Determinism, audit hygiene, type cleanliness**

- [ ] **AC-33 — every property test passes `mypy --strict`.** Hypothesis's `@given` decorators carry full type annotations; no `Any` outside what Hypothesis's API demands (`@given` itself is typed `Any` upstream; `_` ignores at the decorator line are the only allowed Hypothesis-specific concession).
- [ ] **AC-34 — Hypothesis strategies are explicit, not `from_type`-magic.** Each property test declares its strategies explicitly (e.g., `commits_behind_strategy = hypothesis.strategies.builds(CommitsBehind, n=integers(min_value=0, max_value=10_000), last_indexed=text(...))`). `hypothesis.strategies.from_type(IndexFreshness)` would silently DTRT (or fail to) — explicit beats implicit, especially for discriminated unions. The existing precedents (`test_sum_types_roundtrip.py`, `test_index_freshness_roundtrip.py`) already follow this discipline; new files mirror it verbatim.
- [ ] **AC-35 — no flakes; `database=None` in CI.** Each property test uses `@settings(database=None)` to disable Hypothesis's persistent example database for CI reproducibility (committing `tests/property/.hypothesis/` is explicitly out of scope for Phase 2 per "Patterns DELIBERATELY deferred"). The PR description documents that every property test was run 100×local with `--hypothesis-seed=0` and passed 100/100; the loop is `pytest tests/property/ --hypothesis-seed=0` executed in a shell `for i in $(seq 1 100); do ...; done` before opening the PR.
- [ ] **AC-36 — portfolio sweep passes against all five fixtures** (smoke-verified locally before opening PR; `pytest tests/integration/portfolio/test_portfolio_sweep.py -v -s` shows the per-fixture walltime table in the PR description).
- [ ] **AC-37 — coordination, not duplication.** `tests/property/test_index_freshness_roundtrip.py` and `tests/property/test_sum_types_roundtrip.py` already ship (S1-01, S5-01). This story extends them in place — no new `test_scanner_outcome_roundtrip.py` file is created (its content already lives in `test_sum_types_roundtrip.py`). A grep-precheck in the test file's top comment notes the prior file and the AC mapping (AC-7..AC-11 → existing file; AC-12 → new `test_redacted_slice_roundtrip.py`; AC-19..AC-24 → new `test_trace_coverage_invariants.py`; AC-13..AC-18 → new `test_dep_graph_strategy_dispatch.py`).

## Implementation outline

1. **Extend `tests/property/test_index_freshness_roundtrip.py` (S1-01 ships it).** Add `@settings(max_examples=200, deadline=None, database=None)` to the existing `test_index_freshness_roundtrips_identity`. Confirm the existing `_freshness` / `_stale_reasons` strategies already match the shipped variant set with correct field names (AC-2 audit). Run; observe pass with the larger example budget.
2. **Add the `assert_never` exhaustive-match test** (AC-5) under `tests/unit/indices/test_freshness_assert_never.py` (or appended to `tests/unit/indices/test_freshness.py` if S1-01 already has the file). Run `mypy --warn-unreachable` against the file; observe pass. Temporarily comment out one `case` line and re-run; observe mypy failure. Restore. Commit.
3. **Extend `tests/property/test_sum_types_roundtrip.py` (S5-01 ships it).** Add `@settings(max_examples=200, deadline=None, database=None)` to both round-trip tests. No other change — the strategies are already correct.
4. **Add the no-plaintext-leak companion test** (AC-9) under `tests/unit/output/test_finding_redaction.py` — constructs a synthetic `Finding` with a plaintext-secret-shaped `metadata` value, threads it through `redact_secrets`, asserts the resulting `RedactedSlice.slice` JSON contains zero plaintext-secret substring matches.
5. **Write `tests/property/test_redacted_slice_roundtrip.py`** (AC-12). Hypothesis generates `dict[str, JSONValue]` payloads; every example is passed through `redact_secrets(...)` to obtain a `RedactedSlice`; the test asserts round-trip identity via `TypeAdapter[RedactedSlice]`. The file's top comment names ADR-0010 and the S7-04 firewall — every `RedactedSlice` instance reaches the test via `redact_secrets`, never via the model constructor.
6. **Write `tests/property/test_dep_graph_strategy_dispatch.py`** (AC-13..AC-17). Autouse fixture asserts `default_dep_graph_registry.registered_ecosystems() == frozenset()` before each example (and unregisters anything left over with a failure message naming the polluter). The property body samples one `PackageManager` member per example, calls `dispatch(...)`, and asserts the documented `DepGraphRegistryError` raise with the structural prefix. The mock-strategy test (AC-16) is a separate non-property test using `register_dep_graph_strategy(PackageManager.npm)` + `try/finally` with `unregister_for_tests`.
7. **Write `tests/property/test_trace_coverage_invariants.py`** (AC-19..AC-22). Hypothesis strategy for `list[ScenarioResult]` uses `unique_by=lambda r: r.scenario_name` to mirror the runtime-trace pre-condition. The property body calls `_aggregate_scenarios(results, parsed)` and asserts the partition + uniqueness invariants; a separate strategy targets `_derive_trace_coverage_confidence` directly for totality (AC-21).
8. **Add `tests/unit/probes/layer_c/test_scenario_result_assert_never.py`** (AC-23). One instance per `ScenarioResult` variant; exhaustive `match` closes on `assert_never(_)`; `mypy --warn-unreachable` enforces.
9. **Write `tests/integration/portfolio/test_portfolio_sweep.py`** (AC-25..AC-32). Serial for-loop; `shutil.copytree` each fixture to `tmp_path / fixture.name`; `run_allowlisted([sys.executable, "-m", "codegenie", "gather", str(workdir)], ...)`; assert exit + stderr allowlist + schema + golden-diff; collect walltimes in memory; write to `CODEGENIE_PORTFOLIO_WALLTIME_OUT` if set; assert `_PORTFOLIO_DIR_HASH` unchanged at test end. Run; observe pass (or debug the failing fixture + probe combination).
10. **Stabilize.** Run each property test 100 times locally with `pytest tests/property/ --hypothesis-seed=0`. Confirm 100/100 passes. If any flake, investigate — Hypothesis's persistent database is a common culprit (`database=None` per AC-35 is the prescribed mitigation).
11. **Sweep budget check.** Run the portfolio sweep locally; record per-fixture wall-clock; confirm `total_seconds <= 360` (AC-29). If a fixture's gather exceeds expectation, debug — usually a probe regressing into a worst-case path.
12. **Final pass:** `mypy --strict`, `ruff check`, `ruff format --check`, `make check`. Green.

## TDD plan — red / green / refactor

### Red — failing property tests first

```python
# tests/property/test_index_freshness_roundtrip.py  (extension of the S1-01 file)
# Existing strategies (already shipped under S1-01) are unchanged:
#   _commits_behind     uses CommitsBehind(n, last_indexed)
#   _digest_mismatch    uses DigestMismatch(expected, actual)         <-- not (last_traced, current_built)
#   _coverage_gap       uses CoverageGap(files_indexed, files_in_repo) <-- not (missing_files, ...)
#   _indexer_error      uses IndexerError(message)
#   _freshness          one_of(builds(Fresh, indexed_at=_aware_datetimes), builds(Stale, reason=...))
#
# This story adds ONLY the @settings decoration to the existing test:

from hypothesis import given, settings
# ... (existing imports and strategies — see S1-01 shipped file)

@given(value=_freshness)
@settings(max_examples=200, deadline=None, database=None)  # AC-4, AC-35
def test_index_freshness_roundtrips_identity(value: IndexFreshness) -> None:
    decoded = _adapter.validate_json(_adapter.dump_json(value))
    assert decoded == value
    assert type(decoded) is type(value)
    if isinstance(value, Stale):
        assert isinstance(decoded, Stale)
        assert type(decoded.reason) is type(value.reason)
```

```python
# tests/unit/indices/test_freshness_assert_never.py  (AC-5)
from typing import assert_never
from datetime import UTC, datetime
from codegenie.indices import (
    Fresh, Stale, CommitsBehind, DigestMismatch, CoverageGap, IndexerError, IndexFreshness,
)

def _stringify(x: IndexFreshness) -> str:
    match x:
        case Fresh():
            return "fresh"
        case Stale(reason=CommitsBehind(n=n)):
            return f"stale_commits_behind_{n}"
        case Stale(reason=DigestMismatch()):
            return "stale_digest_mismatch"
        case Stale(reason=CoverageGap()):
            return "stale_coverage_gap"
        case Stale(reason=IndexerError()):
            return "stale_indexer_error"
        case _:
            assert_never(x)

def test_exhaustive_match_assert_never() -> None:
    """AC-5 — match is exhaustive over every StaleReason variant;
    mypy --warn-unreachable on this module enforces it at build time."""
    assert _stringify(Fresh(indexed_at=datetime(2026, 1, 1, tzinfo=UTC))) == "fresh"
    assert _stringify(Stale(reason=CommitsBehind(n=1, last_indexed="a"*40))).startswith("stale_commits_behind_")
    assert _stringify(Stale(reason=DigestMismatch(expected="x"*64, actual="y"*64))) == "stale_digest_mismatch"
    assert _stringify(Stale(reason=CoverageGap(files_indexed=0, files_in_repo=0))) == "stale_coverage_gap"
    assert _stringify(Stale(reason=IndexerError(message="boom"))) == "stale_indexer_error"
```

```python
# tests/property/test_dep_graph_strategy_dispatch.py  (AC-13..AC-17)
from __future__ import annotations
from typing import get_args
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from codegenie.depgraph import (
    DepGraphRegistryError,
    default_dep_graph_registry,
    register_dep_graph_strategy,
)
from codegenie.types.identifiers import PackageManager

_package_managers = st.sampled_from(list(get_args(PackageManager)))

@pytest.fixture(autouse=True)
def _registry_is_empty() -> None:
    leftover = default_dep_graph_registry.registered_ecosystems()
    assert leftover == frozenset(), (
        f"singleton polluted by prior test; leftover ecosystems={leftover!r}"
    )

@given(ecosystem=_package_managers)
@settings(max_examples=200, deadline=None, database=None)
def test_dispatch_phase2_invariant_raises_documented_error(ecosystem: PackageManager) -> None:
    """AC-14, AC-15 — with zero strategies registered, every PackageManager member
    raises DepGraphRegistryError with the documented structural prefix."""
    assert default_dep_graph_registry.has_strategy(ecosystem) is False
    with pytest.raises(DepGraphRegistryError) as exc_info:
        default_dep_graph_registry.dispatch(ecosystem, ctx=None, manifests=[])  # type: ignore[arg-type]
    msg = str(exc_info.value)
    assert msg.startswith("no_strategy_for_ecosystem: "), msg
    assert repr(ecosystem) in msg, msg
```

```python
# tests/integration/portfolio/test_portfolio_sweep.py  (AC-25..AC-32)
from __future__ import annotations
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
import pytest
from jsonschema import validate
from codegenie.exec import run_allowlisted
from codegenie.parsers import safe_yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PORTFOLIO = _REPO_ROOT / "tests" / "fixtures" / "portfolio"
_SCHEMA = _REPO_ROOT / "src" / "codegenie" / "schema" / "repo_context.schema.json"

# AC-26 — explicit, grep-discoverable allowlist of stderr line prefixes.
_STDERR_ALLOWLIST: tuple[str, ...] = (
    "skill_shadowed",
    "strace_unavailable",
    "image_digest_unresolved",
    "external_docs_skipped",
)
_TOTAL_WALLCLOCK_BUDGET_S = 360.0  # AC-29 hard ceiling


def _enumerate_fixtures() -> list[Path]:
    return sorted(p for p in _PORTFOLIO.iterdir() if p.is_dir() and not p.name.startswith("_"))


def _dir_sha256(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


@pytest.mark.serial  # AC-30 — ADR-0009; never xdist
def test_portfolio_sweep(tmp_path: Path) -> None:
    schema = json.loads(_SCHEMA.read_text())
    walltimes: dict[str, float] = {}
    pre_hash = _dir_sha256(_PORTFOLIO)  # AC-31 fixture-purity check
    sweep_t0 = time.perf_counter()

    for fixture in _enumerate_fixtures():
        workdir = tmp_path / fixture.name
        shutil.copytree(fixture, workdir)  # AC-31 stdlib; no `cp` subprocess

        t0 = time.perf_counter()
        result = run_allowlisted(
            [sys.executable, "-m", "codegenie", "gather", str(workdir)],
            cwd=_REPO_ROOT,
            timeout_seconds=180,
        )
        walltimes[fixture.name] = time.perf_counter() - t0

        # AC-26 — stderr allowlist
        stderr_text = result.stderr_tail.decode("utf-8", errors="replace")
        for line in stderr_text.splitlines():
            if not line.strip():
                continue
            assert any(line.startswith(p) for p in _STDERR_ALLOWLIST), (
                f"{fixture.name}: undocumented stderr line: {line!r}"
            )
            assert "Traceback" not in line and "Exception" not in line, (
                f"{fixture.name}: error keyword in stderr: {line!r}"
            )
        assert result.exit_code == 0, f"{fixture.name}: exit={result.exit_code}; stderr={stderr_text!r}"

        # AC-27 — schema validation via the project's safe_yaml chokepoint
        ctx_path = workdir / ".codegenie" / "context" / "repo-context.yaml"
        validate(instance=safe_yaml.load(ctx_path.read_text()), schema=schema)

    # AC-28 — golden diff empty (skip if S7-03's --portfolio flag hasn't landed yet)
    check_result = run_allowlisted(
        [sys.executable, str(_REPO_ROOT / "scripts" / "regen_golden.py"), "--check", "--portfolio"],
        cwd=_REPO_ROOT,
        timeout_seconds=120,
    )
    assert check_result.exit_code == 0, (
        f"Golden diff non-empty:\n{check_result.stderr_tail.decode('utf-8', errors='replace')}"
    )

    total_wallclock = time.perf_counter() - sweep_t0
    assert total_wallclock <= _TOTAL_WALLCLOCK_BUDGET_S, (
        f"portfolio sweep exceeded {_TOTAL_WALLCLOCK_BUDGET_S}s budget: {total_wallclock:.1f}s\n"
        + json.dumps(walltimes, sort_keys=True, indent=2)
    )

    # AC-31 — fixture tree untouched
    assert _dir_sha256(_PORTFOLIO) == pre_hash, "canonical portfolio fixture tree was modified"

    # AC-32 — walltime artifact (env-gated; never dirties the repo)
    out_path = os.environ.get("CODEGENIE_PORTFOLIO_WALLTIME_OUT")
    if out_path:
        Path(out_path).write_text(json.dumps(walltimes, sort_keys=True, indent=2) + "\n")
    else:
        print("\nportfolio walltimes (seconds):", json.dumps(walltimes, sort_keys=True, indent=2))
```

### Green — make it pass

With S1-01, S5-01, S1-10, and S5-02 types in place AND S7-03's goldens committed AND all five fixtures from S7-01/S7-02 on disk, every test in this story should pass on first run. If any fails, the failure points to a real bug — fix the production code, not the test.

### Mutation-resistance witness table

| Mutation | Test that catches it |
|---|---|
| Add `IndexFreshness` variant `Stale.NetworkPartition` (missing discriminator) | `test_index_freshness_roundtrips_identity` — `model_validate_json` fails on round-trip; `test_exhaustive_match_assert_never` fires mypy `--warn-unreachable` |
| Drop the `n` field from `CommitsBehind` | `test_index_freshness_roundtrips_identity` round-trip fails (Pydantic `extra="forbid"` + the strategy's required-field build) |
| Rename `DigestMismatch.expected → DigestMismatch.last_traced` without updating strategies | `test_index_freshness_roundtrips_identity` — `st.builds(DigestMismatch, expected=...)` fails at collection time with `TypeError: unexpected keyword 'expected'`, naming the drift |
| `ScannerRan.findings` element loses `severity` constraint (regex/Literal regression) | Existing `test_sum_types_roundtrip.py` — Pydantic refuses the out-of-set sample; the round-trip fails on the offending example |
| Plaintext slips into `Finding.metadata` and through to writer | `test_finding_redaction.py` (AC-9) — asserts the post-`redact_secrets` slice JSON contains zero plaintext substring matches |
| `RedactedSlice.fingerprints` shape regresses (non-8-hex string admitted) | `test_redacted_slice_roundtrip` — since every example transits `redact_secrets`, the regression surfaces as a round-trip identity mismatch or a model-validation failure |
| Future contributor adds a dep-graph strategy without updating `test_dep_graph_strategy_dispatch.py` | The Phase-2 invariant (`registered_ecosystems() == frozenset()`) fails in the autouse fixture — the test fails loudly with a named pointer to the polluter, forcing the Phase-3 PR to explicitly update |
| `DepGraphRegistry.dispatch` quietly drops the `"no_strategy_for_ecosystem: "` prefix | `test_dispatch_phase2_invariant_raises_documented_error` — prefix assertion fires |
| `_aggregate_scenarios` admits a duplicate scenario name | `test_trace_coverage_invariants` — uniqueness invariant + Hypothesis `unique_by` mismatch fires |
| `_aggregate_scenarios` returns `len(scenarios_run) + len(scenarios_failed) + skipped != len(results)` | `test_trace_coverage_invariants` — partition invariant fails |
| `_derive_trace_coverage_confidence` returns an out-of-`Literal` value or raises | `test_trace_coverage_invariants` totality assertion fires |
| A fixture × probe combination crashes (e.g., `DepGraphProbe` against `monorepo-pnpm` hits an unhandled `KeyError`) | `test_portfolio_sweep` — exit-code-non-zero assertion fires; `Traceback`/`Exception` keyword assertion fires |
| A probe's slice schema drifts (e.g., adds a new field without updating `repo_context.schema.json`) | `test_portfolio_sweep` — `jsonschema.validate` fails with the absolute schema path |
| Golden file silently goes stale | `test_portfolio_sweep` AC-28 — `regen_golden.py --check --portfolio` returns non-zero |
| Implementer enables `pytest-xdist` for the portfolio sweep | `@pytest.mark.serial` + the for-loop iteration make this impossible to silently enable; the registry-emptiness autouse fixture also fires under shared-process contention |
| Test silently writes `walltimes.json` into the working tree | `test_portfolio_sweep` writes only when `CODEGENIE_PORTFOLIO_WALLTIME_OUT` is set; the `_dir_sha256` fixture-purity check fires if the canonical fixture tree changed |

### Refactor — clean up

- The four property-test files share a structural pattern (Hypothesis strategy declarations → `@given` round-trip → `assert_never` exhaustive match). **DO NOT extract a kernel** — four consumers is at the Rule-of-Three boundary, but the variant-strategy declarations are specific to each type (`StaleReason` for one, `ScenarioResult` for another); extracting would require dependency-injecting the type, which obscures more than it clarifies. Re-evaluate at the fifth property test (Phase 3+).
- `test_portfolio_sweep.py`'s walltime recording (AC-32) is the seed S8-03's `bench_portfolio_walltime.py` consumes. The file format (`{fixture_name: walltime_seconds}`) is documented in this story's PR description; S8-03 inherits the contract.
- `--max-examples=200` is a Hypothesis convention; the budget assumes round-trip work is cheap. If a property test exceeds its AC-budget (AC-6, AC-11, AC-18, AC-22, AC-24, AC-29), the bottleneck is either Hypothesis shrinking (set `phases=[...]` to skip shrinking on CI) OR the type's round-trip latency itself (investigate Pydantic field count, custom validators).

## Files to touch

| Path | Why |
|---|---|
| `tests/property/test_index_freshness_roundtrip.py` *(extend in place)* | Add `@settings(max_examples=200, deadline=None, database=None)` to the existing test |
| `tests/property/test_sum_types_roundtrip.py` *(extend in place)* | Add the same `@settings` decoration to both round-trip tests; no other change |
| `tests/property/test_redacted_slice_roundtrip.py` *(new)* | `RedactedSlice` JSON round-trip; every example obtained via `redact_secrets` (ADR-0010) |
| `tests/property/test_dep_graph_strategy_dispatch.py` *(new)* | Phase-2 zero-strategy invariant + documented-raise structural-prefix assertion |
| `tests/property/test_trace_coverage_invariants.py` *(new)* | Partition / uniqueness / confidence-totality over `_aggregate_scenarios` + `_derive_trace_coverage_confidence` |
| `tests/unit/indices/test_freshness_assert_never.py` *(new — or appended to existing file)* | AC-5 exhaustive match + mypy `--warn-unreachable` enforcement |
| `tests/unit/probes/layer_c/test_scenario_result_assert_never.py` *(new)* | AC-23 exhaustive match + mypy `--warn-unreachable` enforcement |
| `tests/unit/output/test_finding_redaction.py` *(new)* | AC-9 — `Finding.metadata` plaintext never reaches the writer |
| `tests/integration/portfolio/test_portfolio_sweep.py` *(new)* | AC-25..AC-32 serial sweep + stderr allowlist + schema + golden-diff + walltime artifact |
| `tests/property/conftest.py` *(optional)* | Hypothesis settings profile (`max_examples`, `deadline`, `database`); only if duplication across the four property files is uncomfortable for the implementer |

**Deliberately NOT created:** `tests/property/test_scanner_outcome_roundtrip.py` — its content already lives in `tests/property/test_sum_types_roundtrip.py` (S5-01); duplicating would violate Rule 3 (surgical changes) and create two strategies-of-record for the same type. The extension AC (AC-7) makes the coordination explicit.

## Out of scope

- **CI wiring** (`portfolio` + `property` job lanes) — S8-03.
- **`bench_portfolio_walltime.py` + baselines** — S8-03 (this story produces the seed walltime data via `CODEGENIE_PORTFOLIO_WALLTIME_OUT`).
- **Hosted-runner bench (Gap 2)** — S8-03.
- **Confidence-renderer + `assert_never` mypy --warn-unreachable enforcement at the renderer site** — S8-01.
- **A generic property-test kernel / shared `conftest.py` settings profile** — premature; four consumers (Rule of Three says wait for a fifth).
- **Hypothesis stateful tests** (state-machine-based) — out; the Phase-2 types under property test are immutable / Pydantic frozen; stateful testing offers no advantage.
- **A `--max-examples=2000` deep-property CI lane** — out; `200` is the convention; deepening it is a bench-driven decision, not a Phase-2 story.
- **Introducing a `Result[T, E]` type wrapper around `DepGraphRegistry.dispatch`** — earlier drafts assumed one existed; the registry's exception-with-structural-prefix is the shipped contract S4-05 consumes. Refactor to `Result` is a cross-module change with no other consumer — premature per Rule 2.

## Notes for the implementer

- **The property tests should pass on first run.** If the extended `test_index_freshness_roundtrips_identity` fails after adding `@settings(max_examples=200, ...)`, the bug is in `codegenie.indices.freshness` (S1-01) — investigate the Pydantic model. Don't paper over with strategy restrictions. Likewise for `test_sum_types_roundtrip.py` — the existing strategies are authoritative.
- **`database=None` is mandatory on every property test in this story.** Phase 2's CI determinism contract (AC-35) forbids `tests/property/.hypothesis/` from being committed (the option is on the deliberately-deferred list). `@settings(database=None)` is the one-line enforcement; the autouse fixture pattern (a session-scoped fixture that asserts no `.hypothesis/` artifacts appear in the test root) is **not** added in this story — `database=None` per-test is the simpler enforcement that doesn't introduce a new fixture surface.
- **`--max-examples=200` is the Hypothesis convention.** Not 100 (under-coverage), not 2000 (over-budget). The Phase-2 types are small enough that 200 examples cover the variant space and find any discriminator regression quickly.
- **Use `hypothesis.strategies.builds(...)` not `from_type(...)`.** The discriminated unions are not Hypothesis-introspectable by default; explicit strategies are predictable. AC-34 names this; the existing precedents already obey it.
- **The `assert_never` test is the load-bearing Phase-2 type-safety enforcement.** `mypy --warn-unreachable` on the per-module override (S1-11) fires if any `case` is missing. Test this manually: temporarily comment out one `case` in `_stringify`, run `mypy --warn-unreachable tests/unit/indices/test_freshness_assert_never.py`, observe failure, restore. Document the deliberate-fail-then-pass in PR.
- **`test_portfolio_sweep.py`'s per-fixture wall-clock timeout is generous (180 s).** That's far more than the cold p50 (≤ 90 s) target. The 6-minute sweep budget (AC-29) covers all five fixtures with headroom. If a single fixture's gather exceeds 90 s in development, that's a probe-regression signal — investigate before merging.
- **The `walltimes.json` artifact is env-gated (`CODEGENIE_PORTFOLIO_WALLTIME_OUT`).** Without the env var the test prints to stdout (visible under `pytest -s`); it never writes to the repo tree. S8-03's `bench_portfolio_walltime.py` consumes the artifact via the same env var (CI sets it to a job-artifact path under `${{ runner.temp }}`). Document the cross-story handoff in this story's PR description.
- **Why `serial` mark on `test_portfolio_sweep`.** ADR-0009 (`pytest-xdist` veto preserved); the `serial` mark is a pytest convention for tests that explicitly opt out of parallelization. The portfolio sweep is the canonical serial-only test in Phase 2. The mark is a documentation aid + a future-proofing hook in case a future contributor enables xdist for unit tests but forgets to exclude this one.
- **The Phase-2 zero-strategy invariant (AC-15) is the load-bearing Phase-3 trip-wire.** When Phase 3 lands its first `@register_dep_graph_strategy(PackageManager.npm) def npm_strategy(...)`, this property test fails on the Phase 3 PR — which is correct. The Phase 3 author updates the test to reflect "for the registered members expect `nx.DiGraph` return; for the rest expect the documented raise". This is the explicit Open/Closed seam Phase 2 documented. Document this handoff in the test file's top comment and in S8-04's Phase-3-handoff issue.
- **`TraceCoverage` is a section title in the arch doc, not a class.** Earlier drafts of this story referenced a `TraceCoverage` Pydantic model; the shipped surface (S5-02) is a pure function `_derive_trace_coverage_confidence` plus a private `_AggregatedSlice`. The property tests target those directly via `# type: ignore[reportPrivateUsage]` on the import line, with a top-comment justification: "property testing a pure fold; no public re-export would be more honest than the function under test." If S8-01's `confidence_section.py` introduces a public `TraceCoverage` re-export, the test imports get one-line updated; the invariants don't change.
- **Design-pattern hooks already paid for by existing code (Open/Closed seams to consume, not extract).** The story consumes — never reinvents — three existing Open/Closed seams: (a) `default_dep_graph_registry.register / unregister_for_tests / registered_ecosystems` for the dep-graph dispatch property; (b) `redact_secrets` as the smart-constructor surface for `RedactedSlice` (ADR-0010); (c) the per-module `mypy --warn-unreachable` overrides (S1-11) for `assert_never` enforcement. The implementer's job is to *exercise* these seams, not invent new abstractions. A fifth property file would be the trigger for considering a `tests/property/conftest.py` settings profile; four are not enough to extract one (Rule of Three).

### Patterns DELIBERATELY deferred (per Rule 2)

- **A generic property-test kernel / shared `conftest.py` settings profile** — four consumers; deferred until a fifth. The duplicated `@settings(max_examples=200, deadline=None, database=None)` decoration is the simpler choice; if Phase 3 grows the property surface, extract then.
- **Stateful property tests** — out; types are immutable.
- **Hypothesis `database` committed under git** — out; `database=None` is the simpler choice for Phase 2 (AC-35).
- **A `--max-examples=2000` "deep" CI lane** — out until bench data shows the shallow lane misses real bugs.
- **A `Result[T, E]` wrapper around `DepGraphRegistry.dispatch`** — earlier drafts of this story assumed one existed; the registry uses exception-with-structural-prefix instead (it's already the API S4-05's `DepGraphProbe` matches). Introducing a `Result` type to "make exceptions explicit" would be a cross-module refactor with one user — premature per Rule 2.
