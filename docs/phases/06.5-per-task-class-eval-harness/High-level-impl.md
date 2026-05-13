# Phase 6.5 — Per-task-class eval harness + first benches: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-12
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 6.5"
**Anchor ADR:** [Phase 5 ADR-0016](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)

## Executive summary

The engineer is building `src/codegenie/eval/` — a deterministic, offline harness package — plus two `bench/` corpora (`vuln-remediation` ≥10 cases, `migration-chainguard-distroless` ≥3 seed) and one fence-CI extension. The central work shape is **contracts first, then runtime, then content**: the Pydantic wire types and the `@register_task_class` registry must land before any consumer can compile against them; the asyncio runner + subprocess rubric model must work end-to-end against a stub bench before the real benches get hand-curated; fence-CI is the last gate so it asserts against a working harness, not a partial one. Two upstream ADR amendments (Phase 4 `Canary.mint(seed=...)`, Phase 5 ADR-0010 `bench_invocation` flag) ride along with the work that depends on them.

## Order of operations

Sequencing follows three constraints. **Contracts before consumers** — `BenchScore`, `BenchCase`, `BenchRunReport`, `PromotionVerdict`, `TaskClass`, and the `Rubric` Protocol are referenced by every other module, so they ship in Step 1 with `extra="forbid"`, `frozen=True`, and the static smuggling-ban tests. **Harness internals before user-visible surface** — the audit-chain extension, cost-tag shim, canary shim, and cache are all infrastructure the runner depends on; they land in Step 2 so Step 3 (the runner) and Step 4 (the CLI + promotion gate) can be built on a verified substrate. **Backfill vuln-remediation before seeding migration-chainguard-distroless** — Step 5 produces the worked example a Phase 7 implementer will pattern-match against; Step 6 seeds the new-task-class corpus using exactly that pattern. **Fence-CI last** (Step 7) so it gates on a working harness end-to-end, including the audit chain integration test, rather than a partial one.

## Step 1 — Establish contracts: package scaffold, wire models, registry, Protocol

**Goal:** `src/codegenie/eval/` exports the 9 stable names with `frozen=True, extra="forbid"` wire types, the `@register_task_class` decorator, and the `Rubric` Protocol — all unit-tested and statically smuggling-resistant.

**Features delivered:**
- `src/codegenie/eval/__init__.py` re-exporting exactly: `register_task_class`, `TaskClassRegistry`, `default_registry`, `TaskClass`, `BenchCase`, `BenchScore`, `BenchRunReport`, `PromotionVerdict`, `Rubric`.
- `models.py` — Pydantic v2 wire types (`BenchScore`, `FailureMode`, `BenchCase`, `BenchRunReport`, `PromotionVerdict`) plus `@dataclass(frozen=True, slots=True) TaskClass`. Includes `complete: bool = True` on `BenchRunReport` (Gap #4) and `isolation_class: Literal["subprocess", "microvm"] = "subprocess"` (Gap #1).
- `registry.py` — `default_registry`, `TaskClassRegistry`, `@register_task_class` decorator; collision raises `TaskClassAlreadyRegistered`.
- `rubric.py` — `@runtime_checkable Rubric` Protocol with single `score(case, harness_output) -> BenchScore` method.
- `errors.py` — typed errors (`TaskClassNotFound`, `TaskClassAlreadyRegistered`, `BenchCaseLoadError`, `BenchCaseDigestMismatch`, `BenchCaseIDCollision`, `ChainTamperDetected`, `IncompleteReportForPromotion`, `PromotionMustBeHumanAuthorized`, `TierConfigInvalid`).
- `tests/unit/test_eval_models.py`, `test_eval_registry.py`, `test_rubric_protocol.py`, `test_bench_score_static.py`, `test_breakdown_keys_static.py`, `test_eval_package_imports_no_llm_sdk.py`.

**Done criteria:**
- [ ] `from codegenie.eval import *` imports without errors and exposes ≤ 9 names.
- [ ] `pytest tests/unit/test_eval_models.py` passes; every wire model rejects `extra` fields and rejects mutation.
- [ ] `test_bench_score_static.py` field-graph-walks `BenchScore` recursively and fails on any `confidence|llm|self_reported|model_says` substring.
- [ ] `test_eval_package_imports_no_llm_sdk.py` AST-walks `src/codegenie/eval/**/*.py` and fails on any `import anthropic|openai|langchain|langgraph|transformers`.
- [ ] Registry collision raises `TaskClassAlreadyRegistered(name, existing_qualname, incoming_qualname)`.
- [ ] mypy `--strict` clean on `src/codegenie/eval/{models,registry,rubric,errors}.py`.

**Depends on:** Phase 0 (`codegenie.audit`, `codegenie.hashing`, import-linter contract, pydantic pin); Phase 5 ADR-0014 pattern for static-introspection tests.

**Effort:** M — small surface but the static-introspection tests and ban-list discipline are load-bearing.

## Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims

**Goal:** The runner has working dependencies — bench cases can be loaded with digest verification, scores can be cached content-addressedly, `BenchRunReport`s can extend the Phase 0 audit chain, the Phase 4 canary seed can be pinned per case, and bench-driven sandbox runs are tagged for Phase 13.

**Features delivered:**
- `loader.py` — `load_task_class(name, bench_root)` and `load_cases(task_class)`. Resolves `bench.{name}.registration` via `sys.path` prep (Gap #2 Option A); BLAKE3-verifies each case directory against `cases/digests.yaml`; sorts by `case_id`; raises `BenchCaseIDCollision` on duplicate `case_id` field across directories.
- `cache.py` — content-addressed `get/put/gc` with `fcntl.flock` on a sentinel file; atomic rename on write; corrupt-on-read treated as miss with `structlog.warn`.
- `audit.py` — `write_run_record(report, out_dir) -> (Path, chain_head)` and `verify(out_dir, since)` over Phase 0's BLAKE3 chain; `prev_hash` mismatch raises `ChainTamperDetected`.
- `canary.py` — `with_pinned_canary(case)` context manager; thread-local injection into Phase 4's `Canary.mint(seed=...)` (additive kwarg amendment to Phase 4 final-design lands here).
- `cost_tag.py` — `tag_invocation(task_class, case_id, run_started_iso)` context manager that sets `CODEGENIE_BENCH_INVOCATION_TAG`. Phase 5 ADR-0010 amendment (additive `bench_invocation: bool` on `SandboxCostEntry`) lands here.
- `tests/unit/test_loader.py`, `test_cache.py`, `test_audit_chain.py`, `test_canary_seed.py`, `test_cost_ledger_tagging.py`.

**Done criteria:**
- [ ] `load_cases` over a 3-case fixture returns `BenchCase`s sorted by `case_id`; flipped byte in one case raises `BenchCaseDigestMismatch(case_id, expected, computed)`.
- [ ] Two `case.toml`s declaring `case_id="X"` in different directories raise `BenchCaseIDCollision`.
- [ ] `cache.put` followed by `cache.get` round-trips; mid-write process kill leaves the previous value intact (atomic rename); corrupt file is treated as miss.
- [ ] `audit.write_run_record` appended to a clean chain → `audit.verify().ok is True`; rewriting any prior record → `verify().ok is False`.
- [ ] Two `Canary.mint(seed=bytes.fromhex(pin))` calls in the same case produce byte-identical tokens.
- [ ] When `CODEGENIE_BENCH_INVOCATION_TAG` is set, a recorded `SandboxCostEntry` has `bench_invocation=True` and `workflow_id` equal to the tag value.
- [ ] Phase 4 final-design.md and Phase 5 ADR-0010 are amended in the same commit(s) as the shim code that depends on them.

**Depends on:** Step 1 (wire models, errors). Phase 0 `codegenie.audit` + `codegenie.hashing`. Phase 4 `Canary.mint`. Phase 5 `CostEmitter`.

**Effort:** L — five shims plus the audit-chain integration; each is small but the cross-phase amendments add review surface.

## Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap

**Goal:** `Runner.run_eval(...)` executes a full eval pipeline over a stub bench, with subprocess-isolated rubric scoring, deterministic aggregation, audit append, and six typed per-case failure paths.

**Features delivered:**
- `runner.py` — six-phase pipeline (plan → cache probe → execute → aggregate → cost-cap → audit append) with `asyncio.Semaphore(N=min(cpu_count(), 4))`; `--concurrency` override; `--max-cost-usd` default 5.0; `--no-cache`; deterministic BCa bootstrap (1000 resamples, seed `int(run_id[:8], 16)`).
- Subprocess rubric invocation: `asyncio.create_subprocess_exec("python", str(rubric_path), env=SCRUBBED_ENV, cwd=TemporaryDirectory(), stdin=PIPE, stdout=PIPE, stderr=PIPE, timeout=case.rubric_wall_clock_seconds or 60)`.
- Six typed per-case failure paths: `sut.exception`, `sut.timeout`, `rubric.malformed_output`, `rubric.timeout`, `rubric.unknown_breakdown_key`, `rubric.unknown_failure_mode` — each yielding a `FailureMode(severity="block")` and letting the run continue.
- Runtime validation: `BenchScore.breakdown` keys checked against `task_class.breakdown_keys: frozenset[str]`; rubric-emitted `failure_mode.code` resolved against `failure_modes.yaml` taxonomy.
- `tests/fixtures/bench/stub-task-class/` — 3-case cassette-free stub bench used by `test_runner.py` and the integration tests.
- `tests/unit/test_runner.py` (six failure paths + happy path), `test_bootstrap.py` (deterministic seed, `mean - 2*stddev ≤ lower_bound_95 ≤ mean`), Hypothesis property tests for cache-key determinism + aggregate correctness.

**Done criteria:**
- [ ] `run_eval` over the 3-case stub bench with a deterministic stub SUT exits 0, produces a `BenchRunReport` with `complete=True`, `isolation_class="subprocess"`, and extends the audit chain by one record.
- [ ] Each of the six failure paths is exercised by `test_runner.py` and produces the documented `FailureMode.code`; the run does not abort.
- [ ] Bootstrap is deterministic: two runs with identical inputs produce byte-identical `lower_bound_95`.
- [ ] Cost-cap path: when `total_cost_usd > max_cost_usd`, outstanding tasks are cancelled, the report's `run_id` is `partial:<...>`, and `complete=False`.
- [ ] Rubric subprocess cannot read `ANTHROPIC_API_KEY`, `AWS_*`, `HOME`, or `USER` (verified by `tests/adv/test_rubric_subprocess_env_scrubbed.py`).
- [ ] `tests/fixtures/bench/adversarial-task-class/` covers: env-read attempt, timeout, banned breakdown key, poisoned case, malformed `failure_modes.yaml`.

**Depends on:** Step 1 (wire models + Protocol), Step 2 (loader, cache, audit, canary, cost_tag).

**Effort:** L — the runner is the biggest single module; the adversarial-test fixture portfolio is non-trivial.

## Step 4 — Wire the CLI and the read-only promotion gate

**Goal:** `codegenie eval run | verify | promote-verdict` subcommands work end-to-end against the stub bench; `PromotionGate.evaluate(...)` emits typed verdicts; `PromotionGate.apply()` raises unconditionally.

**Features delivered:**
- `cli.py` — Click subcommand group with deferred heavy imports; partitioned exit codes (0 success, 1 generic, 2 cost-cap, 3 task-class not registered, 4 bench dir missing, 5 chain tamper, 6 digest mismatch); `--format=human|jsonl` (default jsonl).
- `promotion.py` — `PromotionGate(tier_config)`; `evaluate(...)` checks ALL of: `lower_bound_95 ≥ thresholds[target_tier]`, `passed_count ≥ min_cases_for_promotion[target_tier]`, `block_severity_failure_modes == ()`, `audit.verify().ok is True`, `report.complete is True` (Gap #4 reject path), and (Gap #1) all reports in evidence window share `isolation_class`. `reasons` enumerates every failing condition. `apply()` always raises `PromotionMustBeHumanAuthorized` with the operator's escalation path in the message.
- `docs/trust-tiers.yaml` — minimal schema: `thresholds: Mapping[str, float]`, `current_tiers: Mapping[str, str]`. Candidate numbers only; CODEOWNERS-gated.
- Recommendation writer: when `--with-verdict` is set or `evaluate` flips to `evidence_sufficient=True`, write `.codegenie/eval/recommendations/<utc-iso>.json`.
- `tests/unit/test_promotion.py`, `tests/integration/test_eval_promotion_verdict.py`, `tests/adv/test_promotion_apply_raises.py`.

**Done criteria:**
- [ ] `codegenie eval run --task-class=<stub>` against the stub fixture exits 0 with one JSONL line per case + one aggregate line on stdout, and writes a `BenchRunReport` JSON to `.codegenie/eval/runs/`.
- [ ] `codegenie eval verify --strict` over a clean chain exits 0; over a tampered chain exits 5.
- [ ] `PromotionGate.apply(...)` raises `PromotionMustBeHumanAuthorized` from every call site, including direct test invocation (`tests/adv/test_promotion_apply_raises.py`).
- [ ] `evaluate(...)` returns `evidence_sufficient=True` only when every condition passes; the `reasons` tuple lists every failed condition individually when it returns `False`.
- [ ] `evaluate(...)` with `report.complete=False` raises `IncompleteReportForPromotion`.
- [ ] `docs/trust-tiers.yaml` exists with bronze candidate numbers as data and a README header stating the values are not calibrated.
- [ ] Cold-start CLI ≤ 600 ms (mirrors Phase 0 `codegenie gather`).

**Depends on:** Step 1, Step 2, Step 3.

**Effort:** M — CLI is mechanical; promotion gate's all-conditions logic and the apply()-always-raises asymmetry need careful tests.

## Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies

**Goal:** `bench/vuln-remediation/` is a complete worked example: ≥10 cases (5 RAG-corpus-derived + 5 held-out), a working subprocess rubric, `breakdown_keys.py`, `failure_modes.yaml`, signed digests, and a green end-to-end run via `codegenie eval run --task-class=vuln-remediation`.

**Features delivered:**
- `bench/vuln-remediation/registration.py` — exactly one `@register_task_class("vuln-remediation", bench_path=..., min_cases_for_promotion={"bronze": 10, "silver": 25})`.
- `bench/vuln-remediation/rubric.py` — subprocess entrypoint (`if __name__ == "__main__"`); reads JSON from stdin, writes `BenchScore` JSON to stdout; deterministic; ≤ 60 s per case.
- `bench/vuln-remediation/breakdown_keys.py` — `StrEnum BreakdownKey` with values that pass the substring ban (no `confidence|llm|self_reported|model_says`).
- `bench/vuln-remediation/failure_modes.yaml` — full taxonomy with `severity: block|warn|info` per code.
- `bench/vuln-remediation/cases/` — 5 cases mechanically derived from `tests/cassettes/phase4/` solved-example corpus (`curation_class="rag-corpus-derived"`) + 5 hand-curated held-out cases (`curation_class="held-out"`); each with `case.toml`, `input/`, `expected/`, `cassette_canary_pin`, `case_digest`; `cases/digests.yaml` signs all 10.
- `bench/vuln-remediation/tests/test_rubric_unit.py` — bench-author unit tests for the rubric (in-process; trusted boundary).
- `tests/integration/test_eval_end_to_end_vuln.py`, `test_phase4_cassette_replay_canary.py`, `test_cache_hit_rate.py`, `test_cache_invalidation.py`.
- `scripts/scaffold_bench_case.py` (Open Q #8) — operator tooling for `--task-class` + `--cve` → scaffolded case directory.

**Done criteria:**
- [ ] `codegenie eval run --task-class=vuln-remediation` exits 0 on a CI runner with the cassette corpus warm; ≤ 12 min cold cache; ≤ 8 s warm cache.
- [ ] The aggregate `BenchRunReport` carries `mean_score`, `score_stddev`, `lower_bound_95`, `passed_count`, `block_severity_failure_modes=()`, and is appended to the audit chain.
- [ ] `lower_bound_95` is the recorded bronze→silver candidate (per the architecture-doc departure from `mean`); a comment in `bench/vuln-remediation/README.md` documents the candidate value (uncalibrated).
- [ ] Curation-class split is 5/5; fence-CI's held-out-count assertion (≥ 5) passes once silver appears in `min_cases_for_promotion`.
- [ ] Re-running the same task class with no source changes is a 100% cache hit (10/10 cases `cost_usd == 0.0`, wall-clock ≤ 8 s).
- [ ] Whitespace edit to `rubric.py` invalidates all 10 cache entries; whitespace edit to one `case.toml` invalidates exactly that case.

**Depends on:** Step 1–4 (the harness must run end-to-end). Phase 6's `build_vuln_loop` (the SUT) and Phase 4's cassette tree.

**Effort:** L — 10 curated cases with cassette pins + ground-truth `expected/` artifacts is the longest-tail work in the phase; the held-out 5 require hand curation.

## Step 6 — Seed `bench/migration-chainguard-distroless/` with ≥3 cases + rubric stub + taxonomies

**Goal:** Phase 7 has a complete directory skeleton to grow into: registration, stub rubric, breakdown keys, failure-mode taxonomy, ≥3 held-out seed cases, signed digests. The promotion gate emits `evidence_sufficient=False` because `lower_bound_95` is wide at N=3 — this is the correct conservative output and is documented.

**Features delivered:**
- `bench/migration-chainguard-distroless/registration.py` — one `@register_task_class("migration-chainguard-distroless", bench_path=..., min_cases_for_promotion={"bronze": 10})`. Note: only `bronze` declared — Phase 7 raises silver/gold.
- `bench/migration-chainguard-distroless/rubric.py` — subprocess entrypoint scoring on Dockerfile-derived signals (base image swapped to a Chainguard image, no shell invocations in trace, multi-stage build preserved). Stub-quality acceptable; Phase 7 will harden.
- `bench/migration-chainguard-distroless/breakdown_keys.py` — `StrEnum` (e.g., `BASE_IMAGE_SWAPPED`, `SHELL_FREE`, `BUILD_PASSES`).
- `bench/migration-chainguard-distroless/failure_modes.yaml` — initial taxonomy (`migration.base_image_not_chainguard`, `migration.shell_invocation_present`, `migration.build_failed`).
- `bench/migration-chainguard-distroless/cases/` — 3 Chainguard-publicly-documented seed cases (`curation_class="held-out"`), each with `case.toml`, `input/Dockerfile`, `expected/Dockerfile` + `expected/build.log`, `cassette_canary_pin`, `case_digest`; `cases/digests.yaml` signs all 3.
- `bench/migration-chainguard-distroless/tests/test_rubric_unit.py`.

**Done criteria:**
- [ ] `codegenie eval run --task-class=migration-chainguard-distroless` exits 0; produces a `BenchRunReport` with N=3 per_case entries.
- [ ] The emitted `PromotionVerdict` for `target_tier="bronze"` is `evidence_sufficient=False` with `reasons` including "case count below floor" (3 < 10) — this is the intended conservative output.
- [ ] `bench/migration-chainguard-distroless/README.md` documents what Phase 7 must add (≥7 more cases, ≥5 of which `held-out`).
- [ ] All 3 cases reference real Chainguard-documented migration examples; no synthetic Dockerfiles.

**Depends on:** Step 5 (the pattern to mirror). Phase 6.5 is the first time someone follows the directory contract from scratch — bugs in the contract surface here, not in Phase 7.

**Effort:** M — fewer cases, but Step 5's pattern must already exist for this to be a fast follow.

## Step 7 — Extend fence-CI; lock in end-to-end audit; ship cross-phase amendments

**Goal:** A PR that adds a task class without the full directory contract fails CI with a path-specific diagnostic in ≤ 2 s. The audit chain integrates end-to-end. All ADR amendments land before this phase merges.

**Features delivered:**
- `tests/unit/test_eval_fence.py` — seven structural assertions (six from architecture + Gap #3 case-id collision):
  1. Directory contract: AST-walk `bench/*/registration.py` for `@register_task_class("<literal>")` calls; assert all required paths exist for each literal.
  2. Minimum case count: 10 for vuln-remediation, 3 for migration-chainguard-distroless.
  3. Curation-class split: if any tier ≥ silver in `min_cases_for_promotion`, count `held-out` cases ≥ 5.
  4. Literal-name-only: first positional arg to `@register_task_class` is `ast.Constant[str]`.
  5. Breakdown-key static ban: walk `bench/{name}/breakdown_keys.py` `StrEnum` member values; reject `confidence|llm|self_reported|model_says` substring.
  6. Failure-mode taxonomy validity: each `failure_modes.yaml` entry has `severity ∈ {block, warn, info}` and non-empty `description`.
  7. (Gap #3) Case-id uniqueness: parse every `case.toml`; `case_id` set has no duplicates; each `case_id` matches its containing directory name.
- `tests/integration/test_eval_end_to_end_vuln.py` end-to-end run wired into nightly CI.
- `tests/integration/test_audit_chain_extension.py` — three consecutive `run_eval` calls produce a chain of length 3 that `audit.verify` walks clean.
- `tests/snapshots/bench_run_report.v1.json` + `eval_run_audit_record.v1.json` — golden file snapshots.
- ADR amendments landed in the same PR or immediately prior:
  - Phase 4 final-design: `Canary.mint(seed: bytes | None = None)` additive kwarg.
  - Phase 5 ADR-0010: `bench_invocation: bool` field on `SandboxCostEntry`.
  - Phase 5 ADR-0016: "automatic demotion = recommendation-shift, not side-effect" clarification.
- Roadmap §Phase 7 exit-criterion shift: `bench_score.mean ≥ tier_threshold[bronze]` → `bench_score.lower_bound_95 ≥ tier_threshold[bronze]`.

**Done criteria:**
- [ ] All seven fence-CI assertions run in ≤ 2 s combined wall-clock.
- [ ] A synthetic PR that adds `@register_task_class("foo")` without `bench/foo/cases/digests.yaml` fails the fence test with a diagnostic naming the missing path; the PR cannot merge.
- [ ] A synthetic PR that defines a `BreakdownKey` member with value `"llm_confidence"` fails fence assertion #5.
- [ ] A synthetic PR with duplicate `case_id` across two case directories fails fence assertion #7.
- [ ] Coverage on `src/codegenie/eval/` ≥ 90% line, ≥ 80% branch; mypy `--strict` clean on `src/codegenie/eval/` + `bench/**/rubric.py` + `bench/**/registration.py`.
- [ ] Performance regression canaries (vuln cold ≤ 15 min, warm ≤ 12 s, fence ≤ 2 s) are wired and green.
- [ ] All three ADR amendments are merged before or with this phase; roadmap §Phase 7 exit criterion is updated in the same merge train.

**Depends on:** Step 1–6 (every artifact the fence asserts against must exist).

**Risks specific to this step:** Cross-phase amendments may require separate review cycles (Phase 4/5 CODEOWNERS); start the amendment PRs early in Step 2/3 so they don't block the phase-merge train here.

**Effort:** M — fence assertions are mostly AST + filesystem walks; the coordination cost on the ADR amendments is the long pole.

## Exit-criteria mapping

| Exit criterion (paraphrased) | Step(s) |
|---|---|
| #1 `src/codegenie/eval/` package with unit-tested registry, model, runner, promotion gate | Step 1, Step 3, Step 4 |
| #2 `bench/vuln-remediation/cases/` ≥10 cases + rubric.py + aggregate (lower_bound_95 as candidate) | Step 5 |
| #3 `bench/migration-chainguard-distroless/cases/` ≥3 seed cases + rubric.py | Step 6 |
| #4 fence-CI rejects PR adding task class without bench/ | Step 7 |
| #5 trust-tier promotion gate wired but does NOT auto-promote | Step 4 |
| #6 `codegenie eval run --task-class=vuln-remediation` exits 0 + JSON + audit record | Step 4, Step 5, Step 7 |
| #7 Phase 7 can reference ≥10 cases + bench_score.lower_bound_95 ≥ tier_threshold[bronze] as hard precondition | Step 5 + Step 7 handoff (roadmap amendment) |

## Implementation-level risks

1. **The 5 held-out vuln-remediation cases are the long-pole curation work.** Hand-curating CVE-fix ground truth (input repo snapshot + expected diff + ground-truth `expected/` artifacts) is slow and easy to underestimate. Signal it's going sideways: Step 5 stretches past one week with < 5 held-out cases written. Mitigation: start case scaffolding in parallel with Step 3 (Open Q #8 `scripts/scaffold_bench_case.py` can be written by the harness implementer while the curator drafts cases against the contract).

2. **Cross-phase ADR amendments can stall the merge.** Phase 4 `Canary.mint(seed=...)` and Phase 5 ADR-0010 `bench_invocation` both need separate CODEOWNERS review. Signal: an amendment PR sits > 3 days in review with no concerns surfaced. Mitigation: open both amendment PRs at the start of Step 2 (when the dependent code is written), not at Step 7. The amendments are additive and uncontroversial; the risk is calendar-driven, not technical.

3. **Subprocess rubric isolation may surface OS-level surprises on macOS dev loops.** `asyncio.create_subprocess_exec` + `TemporaryDirectory` + scrubbed env interacts with macOS's SIP and `tmpwatch` differently from Linux CI. Signal: `test_rubric_subprocess_env_scrubbed.py` is green on Linux but flaky on macOS. Mitigation: run the adversarial test suite on both substrates in CI from Step 3 onward, not at Step 7.

4. **Bootstrap small-sample behavior at N=3 may produce surprising verdicts during Step 6.** `lower_bound_95` is one-sided and conservative; curators may misread the `evidence_sufficient=False` output as a bug. Signal: Step 6 stalls with curators believing the rubric is wrong when the bound is just wide. Mitigation: document the N=3 conservative-by-design behavior in `bench/migration-chainguard-distroless/README.md` and in the verdict's `reasons` tuple itself ("case count below floor").

5. **Audit chain integration with Phase 0 may need a one-time bootstrap.** If Phase 0's chain root is currently empty, the first `BenchRunReport` becomes the genesis record. Signal: `audit.verify` returns ambiguous results on the very first run because there is no `prev_hash` to compare against. Mitigation: in Step 2, define the genesis-record semantics explicitly (`prev_hash == "0" * 64`) and snapshot-test it in `test_audit_chain.py`.

## What's next — handoff to Phase 7

- **New artifacts on disk:** `src/codegenie/eval/`, `bench/vuln-remediation/` (≥10 cases), `bench/migration-chainguard-distroless/` (3 seed cases), `.codegenie/eval/runs/<utc-iso>-<short>.json` audit chain, `.codegenie/eval/cache/` content-addressed score cache, `.codegenie/eval/recommendations/` advisory verdicts, `docs/trust-tiers.yaml`, `scripts/scaffold_bench_case.py`.
- **New contracts ready for consumers:** `@register_task_class`, `BenchScore`, `BenchCase`, `TaskClass`, `BenchRunReport`, `FailureMode`, `BreakdownKey` StrEnum convention, `PromotionVerdict`, `Rubric` Protocol, and the `bench/{name}/{registration.py, rubric.py, breakdown_keys.py, failure_modes.yaml, cases/{digests.yaml,*}, tests/}` directory shape.
- **New CI gates in place:** `tests/unit/test_eval_fence.py` asserting (a) bench-dir exists per registered task class, (b) ≥5 held-out cases for any task class declaring tier ≥ silver, (c) case-id collision detection, (d) `BreakdownKey` smuggling-ban, (e) literal-name-only registration, (f) failure-mode taxonomy validity, (g) minimum case count per task class.
- **Amended upstream phases:** Phase 4 final-design (`Canary.mint(seed=...)` kwarg); Phase 5 ADR-0010 (`bench_invocation: bool` on `SandboxCostEntry`); Phase 5 ADR-0016 (automatic-demotion clarification); roadmap §Phase 7 exit criterion shifted from `mean` to `lower_bound_95`.
- **Implicit assumptions Phase 7 can now make:** rubric runs in subprocess + scrubbed env (never in-process from the runner's perspective); bootstrap `lower_bound_95` is the promotion gate's signal; tier names live in `docs/trust-tiers.yaml` (not as Python `Literal`); bench-invocations are tagged so Phase 13's cost ledger excludes them from production-cost aggregations; `BenchRunReport.complete=False` is rejected by the promotion gate; `isolation_class` field will discriminate subprocess-era from microvm-era records when Phase 16 lands.
- **What Phase 7 must do, structurally:** expand `bench/migration-chainguard-distroless/cases/` from 3 → ≥10 with ≥5 `curation_class="held-out"`; add `silver` (and optionally `gold`) entries to `min_cases_for_promotion` in its `registration.py`; never edit `src/codegenie/eval/`, Phase 0–6 source, or any pre-existing `bench/vuln-remediation/` file (the extension-by-addition invariant from CLAUDE.md is the test).
