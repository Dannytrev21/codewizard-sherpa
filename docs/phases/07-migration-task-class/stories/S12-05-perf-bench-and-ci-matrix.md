# Story S12-05 — Perf regression tests + `bench/migration-chainguard-distroless/` expansion + CI matrix split + regression-gate enforcement

**Step:** Step 12 — End-to-end test suite + property tests + adversarial tests + regression-gate enforcement
**Status:** Ready
**Effort:** M
**Depends on:** S12-01 (fixture portfolio)
**ADRs honored:** ADR-0006 (`_ADAPTER_DISPATCH_ORDER` `Final` tuple — perf test exercises the deterministic dispatch path), ADR-0008 (no `vuln.provenance` cache — the uncached p99 ≤ 50 ms target is the contract), ADR-0009 (byte-edit allowlist + Phase 3–6.5 regression hard gate — **this story pins the hard-gate as a CI invariant**), ADR-0015 (`docker buildx` + `dive` allowlist + `@pytest.mark.phase07_e2e` matrix-split — open question §6 is pinned here), `phase-arch-design.md §Performance regression tests` + `§CI gates`.

## Context

S12-05 is the **CI-and-bench convergence story**. It pins four things that the rest of Phase 7 has been deferring to "Step 12":

1. **Performance regression tests** for the two load-bearing primitives + probes:
   - `assemble_provenance(...)` uncached, p99 ≤ 50 ms across 1000 trials (ADR-0008's tradeoff contract).
   - `BaseImageProbe`, p99 ≤ 60 ms cold / ≤ 2 ms warm.
   - `DockerfileBaseImageSwapTransform` p99 ≤ 80 ms; `DockerfileMultiStageRefactorTransform` p99 ≤ 350 ms (already named in arch but explicitly pinned here as the third perf-test artifact).

2. **Bench tier expansion: `bench/migration-chainguard-distroless/` from 3 seeds to 10 cases.** Per `High-level-impl.md §Risks` item 7 + open question §5: the case distribution is pinned in this story. Proposed: **4 single-plugin / 3 `Both` / 2 `Unknown` / 1 already-distroless** = 10 cases total. The bench tier is the cassette-replay tier (analogous to `bench/vuln-remediation/`) — cost-ledger byte-equality (ε ≤ $0.01) enforced.

3. **CI matrix split for `@pytest.mark.phase07_e2e`.** Per `High-level-impl.md §Risks` item 6 + open question §6: pin the policy. **Opt-in per-PR via `phase07-e2e` label; mandatory on `main`-merge.** GitHub Actions workflow YAML lands in this story.

4. **Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay confirmed as hard pre-merge gate in CI config.** Per `High-level-impl.md §Done criteria` AC + Definition of Done for every Phase 7 story. This story ensures the GitHub Actions workflow has the explicit `required: true` setting on these two jobs. **This is the final invariant check.**

S12-05 does NOT introduce new product behavior. It pins the contracts: perf budgets, cassette coverage, CI gating policies. Each is read-once, set-once; the cost of changing them later is high enough that they get their own story.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy §Performance regression tests` (lines 1313–1318) — the perf targets verbatim.
  - `../phase-arch-design.md §Testing strategy §CI gates` (lines 1304–1311) — the hard pre-merge gate enumeration.
  - `../phase-arch-design.md §Gap analysis §Gap 5` — `_index.tsv` rollup; bench expansion is the operational mitigation for portfolio-scale coordination-event accumulation.
- **Phase ADRs:**
  - `../ADRs/0008-no-vuln-provenance-cache-in-phase-7.md` — explains WHY the uncached p99 ≤ 50 ms target exists.
  - `../ADRs/0015-allowed-binaries-amendment-dive-buildx.md` — the `@pytest.mark.phase07_e2e` marker's runner requirements.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — the regression-suite hard-gate IS the load-bearing operational invariant.
- **Existing infrastructure:**
  - `bench/vuln-remediation/cases/` — Phase 3/6.5 precedent for cassette-replay layout. Mirror exactly.
  - `tests/bench/` — Phase 1/2 precedent for `@pytest.mark.bench` test shape; reuse the perf-measurement helpers (e.g., `bench_p99()`, `bench_warm_cold()` if they exist).
  - `.github/workflows/*.yml` — existing CI config; this story adds matrix-split + label-gated job, does NOT modify the base `make check` job (per ADR-0009).

## Goal

Land three perf regression tests under `tests/perf/`, expand `bench/migration-chainguard-distroless/` to 10 curated cases with pinned distribution, and add a `.github/workflows/phase07-e2e.yml` (or amend the existing CI config) so `@pytest.mark.phase07_e2e` runs opt-in per PR via label + mandatory on `main`-merge. Confirm the Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay are wired as hard pre-merge gates with `required: true` semantics.

## Acceptance criteria

### Part A — Performance regression tests

**`assemble_provenance` uncached perf (AC-1, AC-2)**
- [ ] **AC-1** `tests/perf/test_assemble_provenance_uncached.py::test_p99_under_50ms_over_1000_trials` — runs `assemble_provenance(...)` against the `node-vulnerable-alpine/` fixture from S12-01 (the `Both` fixture — the heaviest path) 1000 times, sorts trial times, asserts `p99 <= 50ms`. Uses `time.perf_counter()` with sub-microsecond resolution. Decorated `@pytest.mark.bench` (advisory, excluded from default `pytest -q` per CLAUDE.md).
- [ ] **AC-2** Warmup discipline: first 50 trials are discarded (JIT + import cache + sqlite warmup); only trials 50–1049 are measured. Hardcoded; documented in the test docstring. Verified by a meta-assertion that `len(measured_trials) == 1000` AND the first 50 are not in the measured set.

**`BaseImageProbe` cold/warm perf (AC-3, AC-4)**
- [ ] **AC-3** `tests/perf/test_base_image_probe.py::test_p99_cold_under_60ms` — cold (cache-miss) p99 ≤ 60 ms over 100 trials against the `multi-stage-dockerfile/` fixture. Each trial clears the cache directory before invocation. Decorated `@pytest.mark.bench`.
- [ ] **AC-4** `tests/perf/test_base_image_probe.py::test_p99_warm_under_2ms` — warm (cache-hit) p99 ≤ 2 ms over 1000 trials. Cache is populated once before the loop. Verifies `cache_strategy="content"` is doing its job per Phase 2 ADR-0006.

**Dockerfile recipe perf (AC-5)**
- [ ] **AC-5** `tests/perf/test_dockerfile_recipes.py::test_swap_p99_under_80ms_and_multistage_p99_under_350ms` — measures `DockerfileBaseImageSwapTransform.apply(...)` against `node-vulnerable-base-only/` and `DockerfileMultiStageRefactorTransform.apply(...)` against `multi-stage-dockerfile/`. 100 trials each; p99 assertions. Decorated `@pytest.mark.bench`.

**Perf-test hygiene (AC-6)**
- [ ] **AC-6** All three perf files share a `tests/perf/_bench_helpers.py` module with `measure_p99(callable_, *, trials: int, warmup: int) -> float` and `assert_p99_under(p99_ms: float, budget_ms: float, *, context: str) -> None`. The latter prints a structured failure message `f"p99={p99_ms:.2f}ms exceeded budget={budget_ms}ms ({context})"` on failure (Rule 12). If `tests/bench/` already has helpers, REUSE them (Rule 11) and skip this AC; surface the reuse in this story's notes.

### Part B — Bench tier expansion

**Case distribution (AC-7, AC-8)**
- [ ] **AC-7** `bench/migration-chainguard-distroless/cases/` contains exactly **10 curated cases** with this distribution (pinned per open question §5):
  - **4 single-plugin cases:** 2 base-only (Alpine → Chainguard), 2 app-only (transitive remediation only, distroless base already in place).
  - **3 `Both` cases:** Alpine base + transitive app vuln; Debian-slim base + npm package vuln; ARG-driven multi-stage base + yarn-berry transitive.
  - **2 `Unknown` cases:** poisoned SBOM (mismatched layerID); Dockerfile heredoc / ARG-driven FROM that `dockerfile-parse` cannot resolve.
  - **1 already-distroless case:** `cgr.dev/chainguard/node`, clean app; `applicability()` returns `NotApplicable`.
  Each case is a directory with `input/` (fixture-shaped repo, can reference `tests/fixtures/portfolio/*` via symlinks OR be standalone copies — pin one convention here, mirror `bench/vuln-remediation/cases/` precedent), `expected/` (the recorded outputs: `assemble_provenance` result, recipe diff if applicable, gate outcomes, `coordination-summary.yaml` if applicable), `cassette.json` (the recorded cost ledger), `README.md`.
- [ ] **AC-8** `bench/migration-chainguard-distroless/test_cassette_replay.py` — runs each case, asserts byte-equality of `assemble_provenance` output + recipe diff + cost-ledger entries vs the recorded `cassette.json`, ε ≤ $0.01 on cost-ledger floats. Decorated `@pytest.mark.bench`.

**Cassette discipline (AC-9, AC-10)**
- [ ] **AC-9** Each case's `cassette.json` records the deterministic outputs **only** — never time-varying fields like `emitted_at` or `workflow_id`. Verified by a meta-test `bench/migration-chainguard-distroless/test_cassette_shape.py` that parses each cassette and asserts the forbidden field list (`{"emitted_at", "workflow_id", "wall_time", "pid"}`) is absent.
- [ ] **AC-10** Cassette regeneration is a documented operator workflow, NOT a per-test side effect. `bench/migration-chainguard-distroless/REGENERATE.md` documents: when to regenerate (only when an intentional behavior change is shipped), how (`python -m bench.migration_chainguard_distroless.regenerate --case <name>`), CODEOWNERS review required. Mirrors `bench/vuln-remediation/REGENERATE.md` if present (Rule 11).

### Part C — CI matrix split

**`phase07_e2e` workflow YAML (AC-11, AC-12, AC-13)**
- [ ] **AC-11** `.github/workflows/phase07-e2e.yml` (NEW) — GitHub Actions workflow that runs `pytest -m phase07_e2e` on a Linux runner with `--privileged` Docker access. Triggers:
  - On PR: only if the `phase07-e2e` label is present (label-gated; `if: contains(github.event.pull_request.labels.*.name, 'phase07-e2e')`).
  - On `push` to `main`: always (mandatory).
  Per open question §6 pinned here.
- [ ] **AC-12** The workflow YAML matrix-splits across at minimum: Python 3.11 + Python 3.12 (mirroring the existing `make check` matrix per CLAUDE.md). Single-OS (Linux only; macOS / Windows runners can't do `--privileged`).
- [ ] **AC-13** The workflow YAML's job `name` is `phase07-e2e (py-{matrix.python-version})` so a `main`-branch protection rule can require it by exact name (operators set this in repo settings; this story documents the required exact name in the workflow file's top comment).

**Hard pre-merge gate confirmation (AC-14, AC-15, AC-16)**
- [ ] **AC-14** Existing CI workflow (the one that runs `make check`) is verified to include the `bench/vuln-remediation/` cassette replay job AND fail the workflow on cost-ledger drift > $0.01. If currently missing the cassette-replay step, add it. (Surface as a follow-up if S6-05 already shipped this — Rule 7.)
- [ ] **AC-15** Phase 3–6.5 regression suite (`make check`) is `required: true` on `main`-branch protection. Documented in `.github/workflows/phase07-e2e.yml`'s top comment + `docs/phases/07-migration-task-class/CI-gates.md` (NEW). The `CI-gates.md` doc enumerates the four required jobs (`make check` + `bench/vuln-remediation/ replay` + `bench/migration-chainguard-distroless/ replay` + `phase07-e2e (main-merge only)`).
- [ ] **AC-16** Phase 3–6.5 regression-confirmation test — `tests/integration/test_phase7_regression_gate.py` (NEW) — runs as part of `make check`; invokes `pytest tests/unit/probes/ tests/unit/plugins/ tests/integration/test_vuln_remediation_*` (the Phase 3–6.5 subsurface) and asserts all green. This is a meta-test asserting the regression gate fires within the same suite. Pinned to a runtime budget of < 60s (subset of Phase 3 unit tests; not full Phase 3 suite).

### Part D — Docs + observability

**`make docs` green (AC-17, AC-18)**
- [ ] **AC-17** `make docs` green: `mkdocs build --strict` succeeds with the new `docs/phases/07-migration-task-class/CI-gates.md` page added to the nav. `mkdocs.yml` nav additively amended (this is a Phase 0 surface meant for incremental additions; verify with S5-01's allowlist).
- [ ] **AC-18** Phase 7 docs page (`docs/phases/07-migration-task-class/index.md` if present, or the README) links to the four required jobs by name + to `CI-gates.md`.

### Cross-cutting gates (AC-19 through AC-22)
- [ ] **AC-19** Byte-edit allowlist fence S5-01 green. New files under `tests/perf/`, `bench/migration-chainguard-distroless/`, `.github/workflows/phase07-e2e.yml`, `docs/phases/07-migration-task-class/CI-gates.md`. The `.github/workflows/` directory is NOT a Phase 0–6.5-locked file (CI config is meant for incremental amendment); confirm with S5-01.
- [ ] **AC-20** `mypy --strict tests/perf/` clean.
- [ ] **AC-21** `make check` green end-to-end including the new perf tests' import (the `@pytest.mark.bench` decoration excludes them from default runs).
- [ ] **AC-22** **The four required jobs all pass on a sanity-check PR:** (1) `make check`, (2) `bench/vuln-remediation/` cassette replay, (3) `bench/migration-chainguard-distroless/` cassette replay, (4) `phase07-e2e (py-3.12)` after applying the `phase07-e2e` label. Verified manually on a draft PR; evidence linked in this story's `_attempts/` log.

## Implementation outline

1. **Read `bench/vuln-remediation/` first.** Layout, cassette format, replay test shape, regeneration docs — all should be mirrored exactly per Rule 11. If `bench/vuln-remediation/` doesn't actually exist yet (it's referenced in CLAUDE.md as Phase 6.5 work — confirm), then this story is the first cassette tier; document the chosen conventions explicitly.
2. **Author the perf helpers** (`tests/perf/_bench_helpers.py` or reuse from `tests/bench/`); author the three perf test files.
3. **Curate the 10 bench cases.** Each case:
   - Pick a CVE + base image + app deps shape matching the slot (single-plugin / `Both` / `Unknown` / already-distroless).
   - Run `codegenie remediate` once against the case input; capture `assemble_provenance` result + recipe diff + cost-ledger entries.
   - Pin into `cassette.json`.
   - Write the README.
4. **Author the bench-replay test** + meta-test for cassette shape.
5. **Author `.github/workflows/phase07-e2e.yml`** with label-gated PR trigger + always-on-`main` trigger.
6. **Confirm hard pre-merge gates.** Inspect the existing `make check` workflow; add the `bench/vuln-remediation/` cassette-replay step if missing; add the `bench/migration-chainguard-distroless/` cassette-replay step. Add the `tests/integration/test_phase7_regression_gate.py` meta-test.
7. **Document everything** in `docs/phases/07-migration-task-class/CI-gates.md`; amend `mkdocs.yml` nav.
8. Run `make check` + `make docs` locally; both green.
9. Open a draft PR against `main`; apply `phase07-e2e` label; verify the workflow fires + completes. Capture the evidence (workflow run URL) in `_attempts/S12-05.md`.

## TDD plan (red-green-refactor)

### Red
1. Write `tests/perf/test_assemble_provenance_uncached.py` with the `@pytest.mark.bench` decorator + the AC-1 assertion. Run: skipped (bench marker excluded by default) → run with `-m bench` → fails on missing fixture OR fails on `assemble_provenance` not yet importable. Initial red is "fixture not found" or "module not found."
2. Write `tests/perf/test_base_image_probe.py` + `tests/perf/test_dockerfile_recipes.py` similarly.
3. Write `bench/migration-chainguard-distroless/test_cassette_replay.py` parametrized over the 10 case names; initial red is "case directory does not exist."
4. Write `.github/workflows/phase07-e2e.yml` and open a draft PR; the workflow YAML is parsed by GitHub Actions; check for syntax errors via `actionlint` (or the GitHub-side validation) before merge.

### Green
1. Implement perf helpers; perf tests pass with `pytest -m bench`.
2. Curate 10 cases; cassette-replay tests pass.
3. Push the workflow YAML; verify it runs end-to-end on a draft PR.
4. Confirm the four-job gate by inspecting CI summary.

### Refactor
1. Extract any duplicated trial-measurement logic into `_bench_helpers.py`.
2. **Mutation guard for AC-1:** temporarily change the perf budget to 1ms. The test must fail. Revert.
3. **Mutation guard for AC-8:** temporarily mutate one case's `cassette.json` (drift the cost ledger by $0.05 — above the ε). The replay test must fail. Revert.
4. **Mutation guard for AC-15:** temporarily delete a Phase 3 test file. The `tests/integration/test_phase7_regression_gate.py` meta-test must fail loudly (Rule 12 — "skipped due to missing file" is NOT acceptable; the test must FAIL). Revert.

## Files to touch

**New files:**
- `tests/perf/__init__.py`.
- `tests/perf/_bench_helpers.py` (or reuse from `tests/bench/`).
- `tests/perf/test_assemble_provenance_uncached.py`.
- `tests/perf/test_base_image_probe.py`.
- `tests/perf/test_dockerfile_recipes.py`.
- `bench/migration-chainguard-distroless/cases/<10 directories>/` (each with `input/`, `expected/`, `cassette.json`, `README.md`).
- `bench/migration-chainguard-distroless/test_cassette_replay.py`.
- `bench/migration-chainguard-distroless/test_cassette_shape.py`.
- `bench/migration-chainguard-distroless/REGENERATE.md`.
- `tests/integration/test_phase7_regression_gate.py`.
- `.github/workflows/phase07-e2e.yml`.
- `docs/phases/07-migration-task-class/CI-gates.md`.

**Modified files:**
- `mkdocs.yml` (nav entry for `CI-gates.md`).
- Possibly the existing CI workflow YAML if the cassette-replay step is missing for `bench/vuln-remediation/` (surface as follow-up if S6-05 is meant to own this).

## Out of scope

- The headline e2e tests — S12-02, S12-03.
- The adversarial suite — S12-04.
- The fixture portfolio — S12-01 (this story consumes it).
- New product behavior — this story pins contracts, doesn't introduce code paths.
- Cross-phase CI changes (e.g., Phase 8 gates) — out of Phase 7 scope.

## Notes for the implementer

- **The perf budgets are contract-level commitments, not aspirational.** Per ADR-0008's Tradeoff table, p99 ≤ 50 ms uncached is THE reason there's no cache in Phase 7. If perf regresses past the budget, the story is BLOCKED until the regression is fixed OR ADR-0008 is amended.
- **Cassette regeneration is a CODEOWNERS-gated operation.** Mirroring Phase 3/6.5: any cassette drift in CI = either (a) a real behavior change (which requires the cassette to be regenerated + the ADR to record the change) or (b) a regression. Never just regenerate "to make CI green" — that defeats the gate.
- **The 10-case distribution (4/3/2/1) is the proposed pin for open question §5.** If the implementer finds during curation that 3 `Both` cases are insufficient (e.g., the heuristic edge cases require more), surface it in `_validation/S12-05.md` rather than silently adding cases — the distribution is operator-readable governance, not test-author judgment.
- **`phase07-e2e` workflow label name is operator-readable.** Don't shorten to `e2e` (collides with future phases) or `p7e2e` (cryptic). Document the label in `CI-gates.md` so future operators know it exists.
- **Required-status-check name strings are LOAD-BEARING.** GitHub branch protection rules reference workflow job names by exact string. If you rename the matrix job, branch protection silently stops requiring it. AC-13 pins the exact name (`phase07-e2e (py-{matrix.python-version})`); don't drift.
- **AC-14 may surface a missing cassette-replay step in the existing CI workflow.** If `bench/vuln-remediation/` was meant to land in Phase 6.5 (S6-05) and the cassette-replay job already exists, this story just confirms + documents. If it doesn't exist yet, file a follow-up against Phase 6.5 (NOT inline edit — Rule 7 + ADR-0009). Either way, document the resolution in `_attempts/S12-05.md`.
- **Rule 10 — checkpoint after every significant step.** This story has four parts (perf, bench, CI, docs) and each is independently complex. After each part, run `make check` + the relevant subset; do NOT push all four parts in one commit. Per-part commits give CI signal at each stage.
- **The "regression-suite as hard gate" is the FINAL invariant check of Phase 7.** S12-05 is where Phase 7 closes the loop on "extension by addition." If a Phase 7 PR can merge while regressing a Phase 3 test, the entire phase's premise has failed. AC-15 + AC-16 are the structural firewall for that failure mode.
- **Rule 12 — fail loud.** If perf regresses by 5% (still under budget), DO NOT silently let it through. Per-trial p99 logging on test runs (visible in `pytest -v -m bench`) gives operators trend visibility. The budget assertion is the hard gate; the logging is the early-warning system.
