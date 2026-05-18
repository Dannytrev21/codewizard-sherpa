# Validation report — S8-03 (Eight Phase-2 CI lanes + three advisory bench canaries)

**Story:** [S8-03-ci-jobs-and-benches.md](../S8-03-ci-jobs-and-benches.md)
**Date:** 2026-05-18
**Validator:** phase-story-validator (skill v1.x)
**Verdict:** **HARDENED**

## Summary

The story's *intent* — eight Phase-2-named CI lanes + three bench scripts + the Gap-2 hosted-runner closer — traces cleanly to `phase-arch-design.md §"CI gates"` + §"Gap analysis Gap 2" + ADR-0009 + ADR-0001 + ADR-0004. The *prescriptions*, however, contradicted current master in eleven of twelve ACs. Three preconditions the story assumed were live had not actually landed (`CODEGENIE_FORCE_CPU_COUNT` plumbing, `[[tool.mypy.overrides]]` 5-module block, "Phase 1 bench baseline-comparison pattern"), and one prescribed mechanism (`@requires_tool` decorator, contract-freeze field-allowlist) didn't exist anywhere in the tree. The four-parallel-critic pass identified fourteen findings — twelve `block`, two `harden`. Fourteen ACs rewritten or split; six new ACs added; effort rescoped S → M. Verdict: **HARDENED**.

## Context Brief

**What the story promises (Goal, draft):**
1. `.github/workflows/ci.yml` defines `exactly 8 jobs` named `fence, contract-freeze, unit, integration, portfolio, adv-phase02, mypy, bench`, all on Python 3.11 + 3.12 matrix.
2. Three bench scripts under `tests/bench/` reusing "Phase 1's baseline-comparison + PR-comment pattern verbatim."
3. `bench_portfolio_walltime_hosted_runner.py` consumes `CODEGENIE_FORCE_CPU_COUNT` already plumbed by S1-08.
4. `mypy` lane consumes the `[[tool.mypy.overrides]]` 5-module block per-module `warn_unreachable = true` from S1-11.
5. `contract-freeze` lane already exists from Phase 0/1; this story just extends the regen helper with the `image_digest_resolver` allowlist.

**What the phase's exit criteria demand:**
- G-CI: `adv-phase02` lane fails the build on any adversarial test failure (load-bearing — roadmap exit criterion).
- §"Performance regression tests": three bench scripts with specific thresholds (≥ 50 % comment, ≥ 10 % B2 comment, ≥ 100 % hosted-runner build-fail).
- §"Gap analysis Gap 2": hosted-runner bench closes critic's hidden-assumption #2.

**What the arch + ADRs constrain:**
- ADR-0009: no `pytest-xdist` anywhere; portfolio + adversarial serial.
- ADR-0001: `ALLOWED_BINARIES` Phase-2 extension is the `integration` lane's preflight matrix.
- ADR-0004: `ProbeContext.image_digest_resolver` is the only allowed Phase-2 widening.
- `phase-arch-design.md §"CI gates"`: eight named jobs (the canonical naming).

## Source-of-truth verifications (grep against master)

| Reference in draft | Master surface | Verdict |
|---|---|---|
| "8 jobs: `fence, contract-freeze, unit, integration, portfolio, adv-phase02, mypy, bench`" (AC-1 equality) | `.github/workflows/ci.yml` defines 5 jobs: `lint, typecheck, test, security, fence`. NONE of `contract-freeze, unit, integration, portfolio, adv-phase02, mypy, bench` exist as top-level jobs. | **PHANTOM JOB SET** — literal equality would force silent deletion of `lint`/`security` (both load-bearing) |
| "`contract-freeze` job (Phase 0 + ADR-0004 amendment from S1-09)" | No such job in ci.yml. `tests/unit/test_probe_contract.py` exists and runs inside the `test` job. `scripts/regen_probe_contract_snapshot.py` has NO field-allowlist mechanism — just walks the structural signature. | **PHANTOM JOB + PHANTOM MECHANISM** |
| "`@requires_tool` decorator (or extend Phase 0/1's existing one)" | `grep -rn "@requires_tool\|requires_tool" src/ tests/` → zero hits. Existing skip pattern is bare `pytest.mark.skipif` per test. | **PHANTOM DECORATOR** — Phase 0/1 never shipped it |
| "reuses Phase 1's `tests/bench/` baseline-comparison + PR-comment pattern verbatim" | `tests/bench/_helpers.py` writes `bench-results.json` via `merge_bench_result()`. No baseline JSON. No PR-comment automation. | **PHANTOM PATTERN** — pattern doesn't exist to reuse |
| "S1-08 plumbed `CODEGENIE_FORCE_CPU_COUNT` into the coordinator's `Semaphore` sizing" | `src/codegenie/coordinator/coordinator.py:489` — `cpu = os.cpu_count() or 1`. No env-var read anywhere in `src/codegenie/`. | **PHANTOM PRECONDITION** — S1-08 did not ship this; AC-10 has nothing to consume |
| "`[[tool.mypy.overrides]]` block in `pyproject.toml` (S1-11)" with 5-module `warn_unreachable = true` | `pyproject.toml:172` — GLOBAL `[tool.mypy]` `warn_unreachable = true`, repo-wide. The 5-module override block does NOT exist. S8-01's `_attempts` log confirms global is sufficient. | **PHANTOM CONFIG** — `warn_unreachable` is global; per-module unnecessary |
| "all seven adversarial test files" | `tests/adv/phase02/` has **eight** files: `test_adversarial_dockerfile, test_concurrent_gather_race, test_hostile_skills_yaml, test_image_digest_drift, test_no_inmemory_secret_leak, test_phase3_handoff_smoke, test_secret_in_source, test_stale_scip_fixture`. | **MISCOUNT** — `test_phase3_handoff_smoke.py` is the 8th |
| `bench-collection-guard` compatibility | ci.yml:122-130 hardcodes `expected exactly 3 bench tests (S5-01)`. Adding new `-m bench`-marked scripts breaks the guard. | **CONFLICT** — guard count must stay 3 OR be updated; story doesn't address |
| `tests/snapshots/probe_contract.v1.json` | Exists at named path (Phase 0 created it). | **OK** |
| `tests/integration/portfolio/` exists | Exists with `test_portfolio_sweep.py` (S7-01/02). Five fixtures present: `minimal-ts, monorepo-pnpm, distroless-target, native-modules, stale-scip`. | **OK** |
| `ProbeContext.image_digest_resolver` field exists | `src/codegenie/probes/base.py:62` — `image_digest_resolver: Callable[[Path], str | None] | None = None`. ADR-0004 satisfied. | **OK** |
| `tests/bench/test_*.py` (existing) | Three files: `test_cli_cold_start.py, test_coordinator_overhead.py, test_cache_hit_dispatch.py`. All with `@pytest.mark.bench`. | **OK** (story must NOT mark new bench scripts with `-m bench`) |

## Critic reports

### Coverage critic

- [block][AC-1] Equality `== 8 jobs` would force silent deletion of `lint`/`security`. Fix: subset assertion + preserve legacy.
- [block][AC-10/Notes] `CODEGENIE_FORCE_CPU_COUNT` not plumbed; AC depends on un-shipped S1-08 work. Fix: split into 10a (plumbing) + 10b (consumer).
- [block][AC-6] `[[tool.mypy.overrides]]` 5-module block doesn't exist; global `warn_unreachable` satisfies the intent. Fix: rewrite AC-6 to assert global.
- [block][AC-5] 7 vs 8 adversarial files. Fix: enumerate the 8 by name.
- [block][AC-3] `@requires_tool` decorator doesn't exist. Fix: own its creation explicitly.
- [harden][MISSING] Workflow YAML parse-failure mode — typed loader needed.
- [harden][AC-10] Cron timezone unspecified (UTC convention).
- [harden][AC-7/10] Fork PR `GH_TOKEN` degradation — bench comment fails silently on fork PRs.
- [harden][AC-1/2/4] Runner image pinning (`ubuntu-24.04` vs `latest`) — image upgrade alone could trigger ≥ 100 % hosted-runner drift.
- [harden][MISSING] ARM vs x86 runner drift.
- [harden][AC-8/9/10] Network flake / `gh pr comment` failure — silent vs fail-loud.
- [harden][MISSING] Baseline-refresh ritual completeness (metadata header).
- [harden][AC-10 escape valve] Not exercisable today.
- [nit][AC-2] "≤ 90 s on developer machine" unverifiable on CI.
- [nit][AC-11] `tests/snapshots/probe_contract.v1.json` path not verified (it does exist — added reference).
- [nit][Notes/REFACTOR] `tests/bench/baselines/README.md` not in Files-to-touch.

### Test-Quality / Consistency / Design-Patterns critic (combined)

- [CO][block][AC-1] Job-name set contradicts existing 5-job ci.yml.
- [CO][block][AC-1] `contract-freeze` job + scripts/regen allowlist are phantom; story claims they're inherited but neither exists.
- [CO][block][AC-10] `CODEGENIE_FORCE_CPU_COUNT` not plumbed.
- [CO][block][AC-6] mypy overrides phantom; would fail trivially or never.
- [CO][block][AC-3] `@requires_tool` phantom.
- [CO][harden][AC-7] `bench-collection-guard` count==3 hardcode breaks if new scripts marked `-m bench`.
- [CO][harden][AC-8/10] "Phase 1 bench baseline pattern" doesn't exist.
- [TQ][harden][AC-1/2/4] String-grep for xdist is fragile vs typed loader.
- [TQ][harden][AC-10] One-boundary parametrize is mutation-weak; parametrize over `[99, 100, 101]` + `[359, 360, 360.001, 361]`.
- [TQ][harden][AC-5] File-existence test is tautological — also assert ≥ 1 collected `test_…` per file.
- [TQ][harden][AC-11] `test_field_allowlist_excludes_third_field` only one path — parametrize over multiple field names.
- [TQ][nit][AC-9] "fraction between 0.0 and 1.0" vacuous — add metamorphic test with injected sleep.
- [DP][harden] Three bench scripts cross rule-of-three threshold — extract `_bench_kernel.py` with pure `compare_to_baseline` + `Verdict` sum type.
- [DP][harden][AC-1] Job names as bare strings = primitive obsession; use `Literal` / `StrEnum`.
- [DP][harden][AC-10] `>= 100% OR p95 > 360s` is two-rule branching — encode as `Threshold` dataclass + pure `evaluate(...)`.
- [DP][nit] Workflow-YAML tests promote to typed Pydantic loader (`WorkflowFile, Job, Step`).
- [CO][nit][Out-of-scope] `forbidden-patterns` out-of-scope wording could be clearer (pre-commit only, no CI step).

### Researcher report

**Skipped** — no findings tagged `NEEDS RESEARCH`. All hardening targets were codebase-grounded (existing jobs, existing files, existing constants) or convention-rooted (functional core / imperative shell, rule-of-three threshold, parametrize boundaries). No external pattern lookup required.

## Conflict resolution

Priority order per the validator skill: **Consistency > Coverage > Test-Quality > Design-Patterns.**

- **Coverage** wanted AC-6 to assert per-module `warn_unreachable` block. **Consistency** found this contradicts `Out-of-scope: editing pyproject.toml mypy overrides` AND the global setting already covers it (per S8-01's `_attempts` log). **Consistency wins.** AC-6 rewritten to assert the global flag + add a smoke ritual; out-of-scope wording strengthened.
- **Coverage** wanted AC-10 to assume CPU-count plumbing exists. **Consistency** found the plumbing doesn't exist. **Consistency wins.** AC-10 split into 10a (plumbing, this story ships it) and 10b (consumer).
- **Design-Patterns** proposed a `JobName` `StrEnum`. **Rule 2** (don't over-abstract) was considered; with 8 job names crossing two test files, an enum is justified. Adopted but kept in `_workflow_model.py` (the typed loader) rather than as a free-standing module.
- **Design-Patterns** proposed extracting `_bench_kernel.py`. Three bench scripts hit the rule-of-three threshold; the kernel is justified. Adopted as AC-8 / AC-9 / AC-10b dependency.
- **Coverage** wanted AC-1 to delete `lint`/`security`. **Consistency** refused — both are load-bearing Phase-0/1 contracts. Resolved with the subset-assertion reframing.
- **Coverage** wanted runner-arch / runner-version pinning ACs. **Consistency** flagged this as adjacent to ADR-0009's intent. Resolved by adding AC-10c (pinning `ubuntu-24.04` on bench-nightly) and surfacing the broader "runner-image upgrade alone could drift the bench" risk in `Notes for the implementer`.
- **Test-Quality** wanted typed workflow loader. **Design-Patterns** agreed (DRY across 3+ CI tests). Adopted as `tests/unit/ci/_workflow_model.py`.

## Edits applied to story (before → after)

| Section | Before | After |
|---|---|---|
| Title | "Eight CI jobs YAML…" | "Eight Phase-2 CI lanes + three advisory bench canaries (hosted-runner closes Gap 2)" — clarifies "lanes" not whole-workflow-replace |
| Status | `Ready` | `HARDENED` |
| Effort | `S` | `M` (rescoped to honor the precondition + helper-extraction work the draft hand-waved) |
| Depends on | "S8-02" only | "S8-02 + precondition: plumb `CODEGENIE_FORCE_CPU_COUNT` — folded into this story as AC-10a since no separate story exists" |
| ADRs honored | 4 ADRs | unchanged (all still apply) |
| Validation notes | absent | 14-item block documenting every change and why |
| Context | "five inherited or extended" | rewritten to acknowledge current 5-job ci.yml shape; reframe Phase-2 8 names as an additive subset |
| AC-1 | "exactly 8 jobs" equality | "8 names are a required *subset*" + AC-1b: legacy `lint`/`security` preserved |
| AC-2 | "≤ 90 s pytest serial" loose target | adds `--no-cov` discipline (avoid double-counting global 85 % floor); `timeout-minutes: 5` is the only CI-enforced ceiling |
| AC-3 | `@requires_tool` decorator (phantom) | creates `tests/_ci_support/requires_tool.py` + decorator contract test (signature, skip-reason format, warning emission, composability with parametrize) |
| AC-4 | five-fixture sweep | adds explicit pytest --collect-only verification that all 5 fixtures appear |
| AC-5 | "all seven adversarial test files" | enumerates 8 named files; asserts each has ≥ 1 collected `test_…` (catches empty stubs) |
| AC-6 | "per-module overrides" (phantom block) | asserts GLOBAL `warn_unreachable = true` + smoke ritual + asserts no override disables it; CLI does NOT pass `--warn-unreachable` (config-driven) |
| AC-7 | basic `continue-on-error: true` | adds AC-7b (`bench-collection-guard` count stays at 3, new scripts NOT marked `-m bench`) + AC-7c (fork-PR degradation) |
| AC-8 | "5-fixture cold + warm p50" | adds: ≥ 5 runs per (fixture, mode), consumes `_bench_kernel.compare_to_baseline`, baseline metadata header (`refreshed_at`/`refreshed_by`/`reason`) |
| AC-9 | "≥ 10 % comments" | adds metamorphic test: injected sleep in `IndexHealthProbe.run` → strictly larger fraction; vacuous "between 0.0 and 1.0" called out as such |
| AC-10 (split) | one AC for whole bench | **AC-10a** (plumb env-var into coordinator), **AC-10b** (bench script consumes it; parametrized boundary tests at 99/100/101/359/360/361), **AC-10c** (workflow file with cron UTC + runner pinning + permissions) |
| AC-11 | "regen helper extended with allowlist" (phantom) | promotes `contract-freeze` to its own lane; creates the field-allowlist in `regen_probe_contract_snapshot.py`; parametrize-tests over multiple field names; ADR-0004 substring assertion |
| AC-12 | basic fence guard | adds `make lint-imports` + `mypy --strict` on all new modules |
| AC-13 (new) | absent | metamorphic test: monkeypatch-inject `-n 4` into a parsed workflow → expect AssertionError |
| Out of scope | 6 items | adds: deleting/renaming `lint`/`security`; changing `bench-collection-guard` count; running hosted-runner bench per-PR |
| Files to touch | 14 files | 30+ files: `_cpu_budget.py`, `_bench_kernel.py`, `requires_tool.py`, `_workflow_model.py`, 3 baseline JSONs, `baselines/README.md`, parametrized boundary test, etc. |
| TDD plan | 11 RED tests | 16 RED tests + 8 GREEN steps + refactor + ritual capture |
| Notes for implementer | 11 bullets | 18 bullets: CPU-count plumbing ordering, baseline-metadata audit trail, fork-PR detection, cron timezone documentation, threshold inclusivity rules, rule-of-three justification for `_bench_kernel`, pure/impure split |

## Final verdict

**HARDENED.** The goal is sound — phase-arch-design.md §"CI gates" + Gap 2 closer — but the original draft assumed a CI shape and three preconditions that did not match master. The rewritten story is implementable by the executor: every prescribed mechanism (typed workflow loader, bench kernel, CPU-count wrapper, `@requires_tool` decorator, field-allowlist) is concretely scoped with its own file path, line count, and ACs. The eight Phase-2 named lanes are added without silently deleting the legacy `lint`/`security` jobs. The `bench-collection-guard` count==3 invariant is preserved by NOT marking the new bench scripts with `@pytest.mark.bench`. The `CODEGENIE_FORCE_CPU_COUNT` plumbing is owned by AC-10a (no longer a hand-wave precondition). The `pyproject.toml` mypy overrides AC is anchored to the global flag that's already in place (no phantom block).

This is a substantial-scope story (M, not S as originally claimed) and a future contributor reading it alongside master will find: (a) eight new top-level CI lanes plus a new nightly workflow; (b) the existing five jobs preserved unchanged; (c) the `bench-collection-guard` count==3 unchanged; (d) three bench scripts composing a shared kernel; (e) one new src/ module (`_cpu_budget.py`); (f) one coordinator.py line edited; (g) no edits to `pyproject.toml` mypy config; (h) no edits to any adversarial test; (i) explicit fork-PR degradation; (j) explicit cron UTC convention; (k) parametrized threshold-boundary tests with explicit inclusivity rules. No phantom surfaces, no contradictions with ADR-0009 / ADR-0004 / ADR-0008, no self-inconsistent test/code prescriptions.
