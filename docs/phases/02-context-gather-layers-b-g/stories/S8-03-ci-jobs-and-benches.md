# Story S8-03 — Eight CI jobs YAML + three advisory bench canaries (hosted-runner closes Gap 2)

**Step:** Step 8 — Confidence section renderer + CI ratchet + advisory benches + Phase-3 handoff
**Status:** Ready
**Effort:** M
**Depends on:** S8-02 (CLI summary line ships; integration tests under `tests/integration/cli/` exist for the `integration` job's matrix)
**ADRs honored:** 02-ADR-0009 (`pytest-xdist` veto preserved — `portfolio` job is **serial**, no xdist anywhere); 02-ADR-0001 (`ALLOWED_BINARIES` Phase 2 extension is the union the `integration` job depends on); production ADR-0005 (no LLM in gather — the `fence` job stays green); 02-ADR-0004 (`ProbeContext.image_digest_resolver` is the one allowed widening — the `contract-freeze` snapshot regen permits exactly this field)

## Context

Phase 2 ships eight CI jobs (phase-arch-design.md §"CI gates") — five inherited or extended from Phase 0/1 (`fence`, `contract-freeze`, `unit`, `integration`, `portfolio`), three new (`adv-phase02`, `mypy`, `bench`). Of these, **`adv-phase02` is load-bearing** — it gates every adversarial test from S4-02 (`stale_scip`), S5-05 (`image_digest_drift`), S5-06 (`adversarial_dockerfile`), S6-07 (`secret_in_source`), and S7-04 (`hostile_skills_yaml`, `concurrent_gather_race`, `no_inmemory_secret_leak`). A failing `test_stale_scip_fixture.py` turns the build red; that is the roadmap exit criterion for Phase 2 ("`IndexHealthProbe` surfaces a real staleness case in CI against a deliberately-seeded fixture").

Three **advisory** bench canaries also land here. They never block merge — they comment on PRs (Phase 0 §3.2 advisory discipline). The third bench (`bench_portfolio_walltime_hosted_runner.py`) is the closer for Gap 2 from phase-arch-design.md §"Gap analysis": the developer-laptop bench (`bench_portfolio_walltime.py`) measures wall-clock on a beefy machine; the hosted-runner bench emulates the actual GitHub Actions `cpu_count()=2` runner via `CODEGENIE_FORCE_CPU_COUNT=2` and **does** have a build-fail threshold (≥ 100 % regression or > 360 s p95). That single bench is the one place in Phase 2 where bench failure is build-failure — because by then we're not advising, we've crossed the operational red line.

The `mypy` job is the runtime enforcer of S8-01's exhaustiveness ritual: `mypy --strict` repo-wide plus `--warn-unreachable` per-module overrides on the five named modules (`codegenie.{indices, probes.layer_b.index_health, report, adapters, tccm}`) configured in S1-11's `pyproject.toml`. A removed `case` in `confidence_section.py` produces a CI build error — verified by the Step 8 PR-review checklist ritual recorded in S8-01.

This story is the **YAML** + the **bench scripts**. It does not change semantics of the underlying tests; it wires them to lanes and thresholds.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"CI gates"` — the eight numbered jobs with their gating/advisory status.
  - `../phase-arch-design.md §"Performance regression tests"` — `bench_portfolio_walltime.py` and `bench_index_health_overhead.py` thresholds (≥ 50 % and ≥ 10 % comment-on-PR).
  - `../phase-arch-design.md §"Gap analysis"` Gap 2 — *"hosted-runner bench closes the hidden-assumption #2"*; the **Improvement** subsection names `bench_portfolio_walltime_hosted_runner.py`, `CODEGENIE_FORCE_CPU_COUNT=2`, nightly cron, comment-on-PR ≥ 50 %, build-fail ≥ 100 % (> 360 s p95), and the escape valve (commit per-fixture `.codegenie/cache/` blobs — operator decision, not Phase 2's).
  - `../phase-arch-design.md §"Adversarial tests"` — the table of seven adversarial tests the `adv-phase02` job aggregates.
- **Phase ADRs:**
  - `../ADRs/0009-pytest-xdist-veto-preserved.md` — *no xdist anywhere*. The `portfolio` lane stays serial inside 6 min.
  - `../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` — the eleven additions; the `integration` lane's tool-presence matrix.
  - `../ADRs/0004-image-digest-as-declared-input-token.md` — the `contract-freeze` snapshot regen permits exactly the `image_digest_resolver` field on `ProbeContext`; nothing else widens.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather.md` — `fence` job invariant.
  - `../../../production/adrs/0033-domain-modeling-discipline.md` §3 — `mypy --strict` + `--warn-unreachable` per-module is the runtime enforcement.
- **Source design:**
  - `../final-design.md §"CI lane"` — *"Serial (no `pytest-xdist`). Estimated CI walltime growth ≤ 6 minutes; the bench canary ... is advisory."*
  - `../final-design.md §"Open questions deferred to implementation"` #5 — full-repo `mypy --warn-unreachable` is a backlog item (filed in S8-04).
- **Existing code (DO NOT WEAKEN):**
  - `.github/workflows/ci.yml` (Phase 0 + Phase 1) — existing `fence`, `contract-freeze`, `unit` jobs. Phase 2 **adds lanes**; existing job semantics are preserved.
  - `tests/bench/` (Phase 1) — Phase 1's bench pattern (baseline JSON committed; ≥ 50 % comment-on-PR). Phase 2 reuses the pattern verbatim; do not introduce a different harness.
  - `pyproject.toml` (S1-11) — `[[tool.mypy.overrides]]` block listing the five Phase 2 modules with `warn_unreachable = true`. The `mypy` CI job invokes the standard `mypy` CLI; overrides come from this config.
  - All adversarial test files from S4-02 / S5-05 / S5-06 / S6-07 / S7-04 — landed before this story; `adv-phase02` collects them by `pytest tests/adv/phase02/`.

## Goal

Land `.github/workflows/ci.yml` extensions adding three new jobs (`adv-phase02`, `mypy`, `bench`) and refactoring the existing `unit` job to add the `integration` and `portfolio` sister lanes — total **eight jobs**. The job matrix runs on Python 3.11 *and* 3.12 (High-level-impl.md Step 8 done criterion #3). All jobs are **serial** (no `pytest-xdist` invocation anywhere; ADR-0009).

Land three new bench scripts under `tests/bench/`:

1. `bench_portfolio_walltime.py` — five-fixture cold + warm p50 captured per run; baseline JSON committed in `tests/bench/baselines/portfolio_walltime.json`; ≥ 50 % delta posts a PR comment (no block).
2. `bench_index_health_overhead.py` — measures `IndexHealthProbe` walltime as a fraction of total cold gather walltime on `minimal-ts`; ≥ 10 % posts a PR comment. Phase 2's invariant is "< 5 % is the target; 5–10 % is acceptable; ≥ 10 % is a comment."
3. `bench_portfolio_walltime_hosted_runner.py` — nightly cron (not per-PR); sets `CODEGENIE_FORCE_CPU_COUNT=2` so the `Semaphore(min(cpu_count(), 8))` resolves to `Semaphore(2)`; ≥ 50 % regression vs baseline posts a PR comment; **≥ 100 % regression OR p95 > 360 s = build failure**. This is the only Phase-2 bench whose failure fails the build (Gap 2 closer).

`adv-phase02` is **load-bearing** — the job runs every test under `tests/adv/phase02/` serially and fails the build on any failure. A `test_stale_scip_fixture.py` failure (B2 not catching seeded staleness) turns `main` red.

## Acceptance criteria

- [ ] **AC-1 (eight CI jobs in `.github/workflows/ci.yml`, all on Python 3.11 + 3.12 matrix).** The workflow file defines exactly eight jobs named `fence`, `contract-freeze`, `unit`, `integration`, `portfolio`, `adv-phase02`, `mypy`, `bench`. Each runs on `python-version: ["3.11", "3.12"]` matrix. `tests/unit/ci/test_workflow_yaml.py` parses the workflow and asserts (a) the set of job names; (b) the Python matrix; (c) no `--numprocesses`/`-n`/`pytest-xdist` invocation anywhere in any step (ADR-0009 guard).
- [ ] **AC-2 (`unit` job ≤ 90 s pytest serial).** The `unit` job runs `pytest tests/unit/ -q --tb=short` with NO `-n`/`-x` parallel flags. Local wall-clock on a developer machine ≤ 90 s (loose target — CI runner is the actual constraint). The job's `timeout-minutes: 5` step-level cap enforces the ceiling. `test_workflow_yaml.py::test_unit_serial` asserts the absence of xdist flags.
- [ ] **AC-3 (`integration` job — real tool invocations, CI-gated on tool presence, skip-with-loud-warning).** The job pre-flights each `ALLOWED_BINARIES` Phase 2 addition (`semgrep`, `syft`, `grype`, `gitleaks`, `tree-sitter`, `docker`, `strace`, `scip-typescript`); when a tool is missing, the relevant test marks itself `pytest.skip("<tool> not on PATH — SKIPPED LOUD")` with the warning surfaced in CI stdout via a custom `@requires_tool(name)` decorator. The job runs `pytest tests/integration/ -q` serially. `tests/unit/ci/test_tool_skip_is_loud.py` asserts that the skip reason string contains the literal substring `SKIPPED LOUD` and the tool name — silent skips are forbidden (Rule 12 — fail loud).
- [ ] **AC-4 (`portfolio` job — five-fixture sweep + golden diff, serial, ≤ 6 min, no xdist).** The job runs `pytest tests/integration/portfolio/ -q --tb=short` against the five-fixture portfolio (S7-01/S7-02: `minimal-ts`, `native-modules`, `monorepo-pnpm`, `distroless-target`, `stale-scip`). `timeout-minutes: 7` (one-minute headroom over the 6-min budget). Golden-diff failure is a hard fail. AC asserts: (a) no `-n`/`pytest-xdist`; (b) `timeout-minutes <= 7`. `test_workflow_yaml.py::test_portfolio_serial_budget` verifies.
- [ ] **AC-5 (`adv-phase02` job — LOAD-BEARING — fails build on any adversarial failure).** The job runs `pytest tests/adv/phase02/ -q --tb=long`. Every adversarial test from S4-02/S5-05/S5-06/S6-07/S7-04 is collected; the job's `continue-on-error: false` (default) means any failure fails the build. `tests/unit/ci/test_adv_phase02_load_bearing.py` asserts: (a) the workflow's `adv-phase02` step does NOT have `continue-on-error: true`; (b) all seven adversarial test files exist under `tests/adv/phase02/` (file-presence test; per-file test surface lives in the original story). The story documents in "Notes for the implementer" the verification ritual: deliberately introduce a bug in `IndexHealthProbe` (e.g., always emit `Fresh`) and confirm the CI build fails red on `test_stale_scip_fixture.py`; revert.
- [ ] **AC-6 (`mypy` job — `--strict` repo-wide + `--warn-unreachable` per-module from `pyproject.toml`).** The job runs `mypy --strict src/codegenie/ tests/`. The per-module `[[tool.mypy.overrides]]` block in `pyproject.toml` (S1-11) is consumed automatically; the job does NOT pass `--warn-unreachable` on the command line (config-driven). `tests/unit/ci/test_mypy_per_module_overrides.py` parses `pyproject.toml` and asserts the five named modules each appear in an `overrides` entry with `warn_unreachable = true`. **AC-6b — exhaustiveness smoke ritual:** the Step 8 PR-review checklist includes "deliberately remove a `case` from `confidence_section.py`, confirm `mypy` job fails with `[unreachable]`, revert"; the ritual's mypy stderr is captured in `_attempts/S8-03.md`.
- [ ] **AC-7 (`bench` job — advisory; never blocks PR).** The job runs `pytest tests/bench/bench_portfolio_walltime.py tests/bench/bench_index_health_overhead.py -q`. The job's `continue-on-error: true` ensures merge is never blocked by bench regression. ≥ 50 % regression vs `tests/bench/baselines/portfolio_walltime.json` posts a PR comment via `gh pr comment` (uses `GH_TOKEN`/`secrets.GITHUB_TOKEN`); ≥ 10 % regression for `bench_index_health_overhead.py` posts a comment. `tests/unit/ci/test_bench_advisory.py` asserts `continue-on-error: true` on the `bench` step (Phase 0 §3.2 discipline).
- [ ] **AC-8 (`bench_portfolio_walltime.py` — five-fixture cold + warm p50, baseline JSON committed).** The script runs each of the five fixtures (`minimal-ts`, `native-modules`, `monorepo-pnpm`, `distroless-target`, `stale-scip`) cold (cache cleared) and warm (cache populated), capturing p50 across 3 runs. Compares against `tests/bench/baselines/portfolio_walltime.json` (committed baseline). On ≥ 50 % regression vs any baseline entry, posts a PR comment listing the regressed fixture(s); never raises a non-zero exit. `tests/bench/test_bench_portfolio_walltime_smoke.py` asserts the script runs end-to-end against `minimal-ts` only (smoke; full sweep is in CI).
- [ ] **AC-9 (`bench_index_health_overhead.py` — B2 walltime < 5 % of total cold gather on `minimal-ts`; ≥ 10 % comments).** The script captures `IndexHealthProbe` walltime as fraction-of-total during a cold gather of `minimal-ts`. Reports the fraction; on ≥ 10 % posts a PR comment naming the regression (does NOT fail). The 5 % target is documented; 5–10 % is an acceptable middle band. `tests/bench/test_bench_index_health_smoke.py` smokes the harness.
- [ ] **AC-10 (`bench_portfolio_walltime_hosted_runner.py` — nightly, `CODEGENIE_FORCE_CPU_COUNT=2`, comment ≥ 50 %, build-fail ≥ 100 % or p95 > 360 s — Gap 2 closer).** The script reads `CODEGENIE_FORCE_CPU_COUNT` (already plumbed into the coordinator's `Semaphore` sizing from Step 1) and forces `Semaphore(2)` regardless of `os.cpu_count()`. Runs the five-fixture portfolio. ≥ 50 % regression vs `tests/bench/baselines/portfolio_walltime_hosted_runner.json` → PR comment. **≥ 100 % regression OR p95 > 360 s → script exits non-zero, failing the build**. A new workflow file `.github/workflows/bench-nightly.yml` runs the script on a `cron: "0 4 * * *"` schedule; results posted as a GH commit-status check on `main`. AC asserts: (a) the workflow exists; (b) the cron schedule is nightly; (c) the script exits non-zero on the threshold; (d) `CODEGENIE_FORCE_CPU_COUNT=2` is set in the workflow env. `tests/unit/ci/test_hosted_runner_bench_thresholds.py` covers (c) via a stub-injected timing.
- [ ] **AC-11 (`contract-freeze` regen permits `image_digest_resolver` and nothing else).** The Phase 2 amendment of `ProbeContext` (S1-09) is the only widening allowed. `tests/snapshots/probe_contract.v1.json` contains the post-S1-09 snapshot. The `contract-freeze` job's regen helper (Phase 0) is extended with an explicit field-allowlist that includes `image_digest_resolver`; any third field fails CI with the ADR-0004 pointer. `tests/unit/ci/test_contract_freeze_allowlist.py` asserts: (a) the snapshot contains `image_digest_resolver`; (b) the regen helper's field-allowlist names exactly `{...Phase 0 fields, "image_digest_resolver"}` — adding another fails.
- [ ] **AC-12 (Phase 0 `fence` continues green; no new LLM/network imports).** The `fence` job asserts no `anthropic`/`openai`/`langgraph`/`httpx`/`requests`/`socket` imports under `src/codegenie/`. This story introduces no new such import. CI run against `main` post-merge passes `fence` on both Python 3.11 and 3.12.

## Out of scope

- Editing the contents of any adversarial test under `tests/adv/phase02/` (those land in S4-02/S5-05/S5-06/S6-07/S7-04).
- Editing `pyproject.toml`'s `mypy` overrides (S1-11 owns this); the `mypy` job here just consumes them.
- Splitting the `portfolio` job into per-fixture parallel lanes via xdist. ADR-0009. If walltime regresses past 6 min, the operator's escape valve (final-design.md §"Open Q 6", phase-arch-design.md §"Gap 2 §Escape valve") is committing per-fixture `.codegenie/cache/` blobs — not a CI shape change.
- Making `bench` gating. ADR-0009 + final-design.md §"CI lane" — `bench` is advisory. Only `bench_portfolio_walltime_hosted_runner.py`'s ≥ 100 % / p95 > 360 s threshold is gating, and that's the nightly cron job, not per-PR.
- Adding a `coverage-ratchet` job (Phase 1 already owns this; Phase 2 inherits unchanged).
- Adding a `forbidden-patterns` job (Phase 0 pre-commit owns this; Phase 2's extension to ban `model_construct` is enforced by the existing pre-commit hook — S1-11).

## Files to touch

**New:**

- `.github/workflows/bench-nightly.yml` — nightly cron for the hosted-runner bench.
- `tests/bench/bench_portfolio_walltime.py` — AC-8.
- `tests/bench/bench_index_health_overhead.py` — AC-9.
- `tests/bench/bench_portfolio_walltime_hosted_runner.py` — AC-10.
- `tests/bench/baselines/portfolio_walltime.json` — committed baseline (initial values from the first run; refreshed via a separate ritual PR when intentional).
- `tests/bench/baselines/portfolio_walltime_hosted_runner.json` — committed baseline for the hosted-runner bench.
- `tests/bench/test_bench_portfolio_walltime_smoke.py`, `test_bench_index_health_smoke.py` — smoke tests for the harnesses.
- `tests/unit/ci/__init__.py` — empty.
- `tests/unit/ci/test_workflow_yaml.py` — AC-1, AC-2, AC-4, AC-7.
- `tests/unit/ci/test_tool_skip_is_loud.py` — AC-3.
- `tests/unit/ci/test_adv_phase02_load_bearing.py` — AC-5.
- `tests/unit/ci/test_mypy_per_module_overrides.py` — AC-6.
- `tests/unit/ci/test_bench_advisory.py` — AC-7 secondary.
- `tests/unit/ci/test_hosted_runner_bench_thresholds.py` — AC-10.
- `tests/unit/ci/test_contract_freeze_allowlist.py` — AC-11.

**Modified:**

- `.github/workflows/ci.yml` — add five new job blocks (`integration`, `portfolio`, `adv-phase02`, `mypy`, `bench`); extend matrix to `["3.11", "3.12"]` if not already; keep `fence` + `contract-freeze` + `unit` unchanged in semantics.
- `scripts/regen_probe_contract_snapshot.py` (or wherever Phase 0/Phase 1's snapshot regen lives) — field-allowlist now includes `image_digest_resolver`; explicit assertion fails on a third field.

**Untouched (DO NOT EDIT):**

- Phase 0 `fence.py` / fence-equivalent logic.
- `pyproject.toml`'s `mypy` block (S1-11 owns).
- Any adversarial test under `tests/adv/phase02/`.
- Phase 1's existing bench harness pattern under `tests/bench/`.

## TDD plan — red / green / refactor

**RED (failing tests committed first):**

1. `test_workflow_yaml.py::test_eight_jobs_named` — parses `.github/workflows/ci.yml`, asserts `{"fence","contract-freeze","unit","integration","portfolio","adv-phase02","mypy","bench"} == set(jobs)`. Fails red (current workflow has only Phase 0/1 jobs).
2. `test_workflow_yaml.py::test_no_xdist_anywhere` — recursive scan of every workflow step's `run` string for `pytest-xdist`/`-n auto`/`--numprocesses`. Fails red if any introduce.
3. `test_workflow_yaml.py::test_python_matrix_311_312` — both Python versions present on every job's `strategy.matrix`. Fails red.
4. `test_adv_phase02_load_bearing.py::test_no_continue_on_error` — adversarial job has no `continue-on-error: true`. Fails red.
5. `test_bench_advisory.py::test_bench_continue_on_error_true` — `bench` job step has `continue-on-error: true`. Fails red.
6. `test_mypy_per_module_overrides.py::test_five_modules_have_warn_unreachable` — parses `pyproject.toml`'s `[[tool.mypy.overrides]]` and asserts the five Phase 2 modules each have `warn_unreachable = true`. Fails red until the override block lands (or, if S1-11 already landed it, this asserts the wiring stays correct under S8-03's job addition).
7. `test_contract_freeze_allowlist.py::test_field_allowlist_excludes_third_field` — exercises the regen helper with a synthetic third field; asserts it raises with a message naming ADR-0004. Fails red.
8. `test_hosted_runner_bench_thresholds.py::test_exits_nonzero_on_100pct_regression` — stub-inject a fake "200 % regression" timing into the script's threshold-check function; asserts `SystemExit` with non-zero code. Fails red — the script doesn't exist yet.
9. `test_bench_portfolio_walltime_smoke.py` — invokes the bench script against `minimal-ts`, asserts it produces a result dict with `cold_p50_s` and `warm_p50_s` keys. Fails red.
10. `test_bench_index_health_smoke.py` — invokes the harness, asserts it returns a `fraction_of_total` float between 0.0 and 1.0. Fails red.
11. `test_tool_skip_is_loud.py` — induces `semgrep` missing on PATH (monkeypatch); asserts the `pytest.skip` reason contains `SKIPPED LOUD` and `semgrep`. Fails red.

**GREEN (minimum code to pass):**

1. Add the five new job blocks to `.github/workflows/ci.yml` with `serial pytest` invocations, matrix on Python 3.11 + 3.12, correct `continue-on-error` settings, `timeout-minutes`.
2. Write the three bench scripts. `bench_portfolio_walltime.py` and `bench_index_health_overhead.py` reuse Phase 1's `tests/bench/` baseline-comparison + PR-comment pattern verbatim. `bench_portfolio_walltime_hosted_runner.py` adds the env-var force + the build-fail threshold.
3. Create `.github/workflows/bench-nightly.yml` with `cron: "0 4 * * *"` triggering the hosted-runner bench.
4. Commit initial baseline JSON files (use first-run measurements; document the "intentional baseline-refresh PR" ritual in the README of `tests/bench/baselines/`).
5. Extend `scripts/regen_probe_contract_snapshot.py` (or Phase 0/1's equivalent) with the explicit field-allowlist `{...phase0_fields, "image_digest_resolver"}`; raise with ADR-0004 pointer on any extra field.
6. Write the `@requires_tool` decorator (or extend Phase 0/1's existing one) so skip reasons contain `SKIPPED LOUD` literally.

**REFACTOR:**

- DRY the bench-script comment-on-PR helper into `tests/bench/_pr_comment.py` if the three scripts duplicate the same `gh pr comment` invocation.
- Confirm `mypy --strict tests/bench/` is clean.
- Run the AC-5 ritual locally (introduce a B2 bug → CI fails → revert); capture proof in `_attempts/S8-03.md`.
- Run the AC-6 ritual (delete a `case` in `confidence_section.py` → `mypy` fails → revert); capture mypy stderr in `_attempts/S8-03.md`.
- `ruff format`, `ruff check`, `mypy --strict` green on touched modules.

## Notes for the implementer

- **The `adv-phase02` job is the load-bearing gate.** It is the only Phase 2 lane whose green-on-`main` is the public contract that the roadmap exit criterion is met. Treat any flake here as a P0 — the discipline phase-arch-design.md §"Adversarial corpus" calls out. If a test is flaky, fix the test or the fixture, never `continue-on-error: true`.
- **Bench advisory vs gating — DON'T blur the line.** Of the three benches, only `bench_portfolio_walltime_hosted_runner.py` gates the build, and only on the ≥ 100 % / p95 > 360 s thresholds, and only on the nightly cron — not per-PR. The other two benches comment-only. Mixing these up either (a) makes PRs blocked by infra noise (kills the velocity bench is supposed to protect) or (b) lets a 100 % regression sail through (kills the operator-visibility bench is supposed to provide).
- **`CODEGENIE_FORCE_CPU_COUNT` wiring.** S1-08 plumbed this env-var into the coordinator's `Semaphore` sizing (`Semaphore(min(int(os.environ.get("CODEGENIE_FORCE_CPU_COUNT", os.cpu_count() or 1)), 8))`). If you find S1-08 did NOT thread this all the way through, surface the gap loudly and file a follow-up — do not paper over by reading the env-var inside the bench script alone. The point is reproducing real CI behavior, which requires the coordinator to honor the override.
- **Baseline-refresh ritual.** Baselines are committed JSON; a contributor who intentionally regresses the bench (e.g., a heavier B2 algorithm) MUST refresh the baseline in a separate PR with reviewer approval. Document this in `tests/bench/baselines/README.md` so the discipline is discoverable.
- **PR-comment helper auth.** Use `${{ secrets.GITHUB_TOKEN }}` — the default GH Actions token has `pull-requests: write` when `permissions:` is set explicitly. Set `permissions: { pull-requests: write, contents: read }` on bench jobs only; do NOT grant broader scopes to `unit`/`portfolio`/etc.
- **Tool-presence pre-flight.** If `docker` is missing on a CI runner, the `integration` job's docker-using tests should `SKIPPED LOUD` (visible in CI output); the job exit is still 0. Surface the missing tools at the start of the job's stdout so a human scanning logs sees the list at a glance.
- **`portfolio` job's 6-min budget vs Gap 2 hosted-runner reality.** The 6-min budget assumes the dev-laptop bench's measurements. The nightly hosted-runner bench is what verifies the assumption against actual CI hardware. If the nightly fails the ≥ 100 % threshold, the operator's choice is the escape valve (committed cache blobs); do not edit the 6-min budget unilaterally — that requires an ADR amendment.
- **Phase 0 fence runs first.** Order the `needs:` graph so `fence` runs first; everything else depends on `fence` passing. If a future contributor accidentally imports `httpx`, no other job wastes minutes.
- **`mypy` job is fast (< 30 s) — no caching beyond what mypy provides natively.** Adding action-level mypy caching is a separate optimization; out of scope.
- **Adversarial-test files presence — file-existence test only.** AC-5 only checks the seven adversarial files exist at predictable paths; per-test semantics live in their original stories. This story does NOT re-validate adversarial logic.
- **Don't run benches in `unit`/`portfolio` lanes.** Bench scripts live in `tests/bench/` and are invoked only by the `bench` and `bench-nightly.yml` workflows. The `unit` lane's pytest discovery should exclude `tests/bench/` (configure via `[tool.pytest.ini_options]` `testpaths`/`norecursedirs` — verify S1-11 or this story sets it).
