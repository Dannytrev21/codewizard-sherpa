# Story S5-05 — vuln-remediation digests.yaml + green E2E run

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** HARDENED (phase-story-validator, 2026-06-05)
**Effort:** M
**Depends on:** S5-03 HARDENED (`bench/vuln-remediation/cases/digests.yaml` exists with 5 RAG-corpus-derived entries; `_compute_case_dir_digest` from `codegenie.eval.loader` is the canonical S2-02 §AC-3 algorithm — S5-05 is the third consumer and the rule-of-three trigger to promote it to public `codegenie.eval.digests.compute_case_dir_digest`), S5-04 HARDENED (5 held-out entries appended to `digests.yaml`; `bench/vuln-remediation/cases/held-out-cve-exclusion-manifest.yaml` exists as a sibling under `cases/`; the loader's case walk must succeed past it), S4-02 HARDENED (`codegenie eval run --task-class=<name>` ships with flags `--out`, `--bench-root`, `--cases`, `--concurrency`, `--max-cost-usd`, `--no-cache`, `--with-verdict`, `--target-tier`; SUT is resolved via `codegenie.eval.sut_registry.resolve_sut(name)` against the `default_sut_registry`; per-case JSONL `kind="case"` + aggregate `kind="aggregate"` shape; `agg["chain_head"]` equals the on-disk record's `chain_head`; happy-path `agg["complete"] is True` AND `agg["isolation_class"] == "subprocess"`), S4-01 HARDENED (exit-code partition `{0,1,2,3,4,5,6}`; `BenchCaseDigestMismatch` → `EXIT_DIGEST_MISMATCH=6`; `ChainTamperDetected` → `EXIT_CHAIN_TAMPER=5`; `TaskClassNotFound` / unregistered SUT → 3; `BenchCaseLoadError` reason="bench-dir-missing" → 4; cost-cap → 2; generic → 1; `_EXIT_CODE_TABLE` is the table-driven mapper), S4-03 HARDENED (`codegenie eval verify` exit 0 when the chain at `--out`/default verifies; this story exercises it after the run), S4-05 HARDENED (`PromotionGate.evaluate` + `write_recommendation` reachable via `--with-verdict` — Out of scope here but the contract is the why we don't invoke), S2-02 HARDENED (loader walk + canonical case-dir digest algorithm at §AC-3; `BenchCaseDigestMismatch` raised when `digests.yaml[case_id]` ≠ recomputed digest — exit 6 by S4-01's table; `digests.yaml` schema regex `re.fullmatch(r"^blake3:[0-9a-f]{64}$", v)` per entry), S2-04 HARDENED (`audit.write_run_record` writes `f"{utc_iso}-{secrets.token_hex(4)}.json"` under `out_dir`; `prev_hash` of the new record equals the prior tip; `chain_head` field on the persisted record equals the returned head), S1-02 HARDENED (`BenchRunReport.isolation_class: Literal["subprocess","microvm"] = "subprocess"`; `lower_bound_95: float ∈ [0, 1]`; `mean_score: float ∈ [0, 1]`; `score_stddev: float ≥ 0`; `chain_head: str`; `prev_hash: str | None`; `complete: bool`; `block_severity_failure_modes: tuple[str, ...]`), S5-01 HARDENED (`bench/vuln-remediation/registration.py` resolves `load_task_class("vuln-remediation")`), S5-02 HARDENED (subprocess rubric reads `harness_output` only — the deterministic stub SUT's emitted `harness_output` shape is the contract surface between SUT and rubric).
**ADRs honored:** ADR-0001 (subprocess rubric isolation is the run-level mechanism; this story exercises it in vivo for the first time), ADR-0002 (`lower_bound_95` — not `mean_score` — is the recorded promotion-evidence candidate; aggregate-time bootstrap with deterministic seed `int(run_id[:8], 16)` over 1000 resamples; conservative one-sided lower bound at 95%), ADR-0003 (phase-6.5 tier-identifiers — `Literal["bronze","silver","gold"]` validated at startup; this story does NOT invoke promotion logic, but the README's "Candidate bronze→silver threshold" wording uses these identifiers verbatim), ADR-0010 (`isolation_class="subprocess"` annotated on every emitted `BenchRunReport`; the promotion gate refuses to mix `isolation_class` populations once Phase 16 flips the value — surfaced as an AC because the field is structural even though its value is monotone at Phase 6.5), Phase 0 ADR-0001 (BLAKE3 hashing chokepoint — for `src/codegenie/`; the new `codegenie.eval.digests` module + `bench/`-curation scripts under `scripts/` route through the chokepoint), production ADR-0009 (humans always merge — the promotion gate is advisory; this story produces *evidence*, not a verdict; no auto-promotion logic invoked), production ADR-0015 (forward-looking — threshold calibration is deferred to Phase 13; this story records the candidate `lower_bound_95` value as **uncalibrated**, naming production ADR-0015 in the README disclaimer alongside ADR-0002).

## Validation notes

**Hardened 2026-06-05** by phase-story-validator skill (`_validation/S5-05-vuln-digests-and-e2e-run.md`).
- **F-CON-1 / F-TQ-1 (BLOCK):** original fixture relied on `monkeypatch.setenv("CODEGENIE_EVAL_CACHE_DIR", …)`, `CODEGENIE_EVAL_RUNS_DIR`, and `CODEGENIE_EVAL_SUT` — none of which are S4-02 contracts. Replaced with CLI flags: `--out=<tmp>`, `--bench-root=<tmp_bench>`, `--cache-dir=<tmp>` (added in this story as a one-flag extension of S4-02's existing `--no-cache`/`--out` set — see Notes §SUT-injection seam); SUT injected via `CliRunner.invoke(eval_group, [...])` in-process (S4-02's `default_sut_registry` registration happens at module import time inside the test process). Subprocess-shape coverage is preserved by the nightly canary against the real `VulnRemediationSut` (Phase 6).
- **F-CON-2 / F-DP-1 (BLOCK):** original Implementation outline §2 said `from codegenie.eval.loader import compute_case_digest` — that public symbol does not exist. S2-02 ships `_compute_case_dir_digest` (private); S5-03 / S5-04 surfaced the F-DP-1 trigger (third consumer promotes). S5-05 IS the third consumer (`scripts/sign_bench_digests.py` + `scripts/verify_bench_digests.py` + the integration test) — this story ships the promotion: new module `src/codegenie/eval/digests.py` re-exports `compute_case_dir_digest` (and `_compute_case_dir_digest` becomes a one-line forwarder for backwards compatibility per Rule 11). All three new consumers import from the public module; the loader uses the same implementation. AC-DIG-PROMOTE pins this.
- **F-TQ-2 (BLOCK):** the subprocess-spawn pattern (`subprocess.run([sys.executable, "-m", "codegenie", ...])`) cannot reach a test-only stub SUT because the spawned process imports `default_sut_registry` empty. Resolution: use `click.testing.CliRunner.invoke(eval_group, [...])` in-process; the test's autouse conftest fixture imports `tests.fixtures.sut.deterministic_vuln_sut`, whose module-level `@register_sut("vuln-remediation", ...)` populates the in-process default registry. The S4-02 subprocess pathway is exercised by S6-03 (with a stub distroless SUT) and by the nightly canary; this story's CI-friendly integration test does not need a fresh process boundary.
- **F-TQ-3 (BLOCK):** the whitespace-edit invalidation test mutated `bench/vuln-remediation/cases/<case_id>/input/…` on the real working tree, restored on a `try/finally` — fragile under pytest-xdist + parallel CI + test crashes. Replaced with: copy `bench/vuln-remediation/` to `tmp_path / "bench" / "vuln-remediation"`, mutate the copy, invoke the CLI with `--bench-root=<tmp_bench>`. The real working tree is untouched.
- **F-CON-3 (BLOCK):** the literal-text variant in AC-6 said `ADR-0002 / ADR-0003 / production ADR-0015` but story §Refactor §1 said `ADR-0002, ADR-0003, and (forward) production ADR-0015` — phase ADR-0003 is the tier-identifiers ADR (`Literal["bronze","silver","gold"]`), not threshold calibration. The calibration-deferred ADR is production ADR-0015. Pinned the README literal text to `**Uncalibrated** — calibration deferred to Phase 13 per ADR-0002 (statistic) and production ADR-0015 (threshold calibration). Phase 7 reads this as candidate input only.`
- **F-CON-7 (BLOCK):** AC-3 said "≤ 12 minutes wall-clock" but the test asserted `elapsed < 90.0`. Split into AC-3a (stub-SUT CI integration test: ≤ 90 s, hard fail on regression) and AC-3b (nightly canary: ≤ 15 min real-SUT cold cache per `phase-arch-design.md §Performance regression tests`, 20% headroom over the 12-min target; first run establishes baseline; failing it is a flag, not a CI block).
- **F-CON-4 (HARDEN):** `Depends on` rewritten from S5-03 + S5-04 to the full 10-story dependency chain (S5-03, S5-04, S4-02, S4-01, S4-03, S4-05, S2-02, S2-04, S1-02, S5-01, S5-02). Mirror S5-04 F-CON-7's quality bar.
- **F-CON-5 (HARDEN):** `ADRs honored` rewritten to add ADR-0001 (subprocess rubric exercised in vivo), ADR-0003 (tier identifiers — README uses verbatim), Phase 0 ADR-0001 (BLAKE3 chokepoint — the new `codegenie.eval.digests` module), production ADR-0009 (humans always merge — gate not auto-invoked), production ADR-0015 (forward-looking calibration deferral named in the README disclaimer).
- **F-COV-1 (HARDEN):** `verifier-script-OR-inline-test` OR-clause in AC-2 replaced with both: (a) the integration test asserts byte-equality between `digests.yaml[case_id]` and `compute_case_dir_digest(case_dir)` per case; (b) `scripts/verify_bench_digests.py` exists, is invoked as a fence-CI assertion, and exits 0 in the happy state. The script is the operator-time gate; the test is the CI-time gate. Both go through the public `codegenie.eval.digests.compute_case_dir_digest`.
- **F-COV-2 (HARDEN):** `scripts/sign_bench_digests.py` had no idempotence AC. Added AC-SIGN-IDEMP: running the script twice in succession produces byte-identical `digests.yaml`.
- **F-COV-3 (HARDEN):** README "Candidate threshold" presence test was loose. AC-6 now requires the recorded `lower_bound_95` value to be parseable as a `float ∈ [0, 1]` matching `re.compile(r"\\b(0\\.\\d{2,4})\\b")` somewhere in the threshold paragraph (a curator-pinned numeric value, not "X.XX placeholder"). Mutation tweak: a curator hand-writing `0.00` passes the format, but the same-run aggregate-line numeric is asserted within 0.05 of the README value (median-of-3 jitter allowance per Notes).
- **F-COV-4 (HARDEN):** No AC asserted `complete is True` on the happy path. Folded into AC-4.
- **F-COV-5 (HARDEN):** `codegenie eval verify` exit-0 was English-only in AC-5. Promoted to AC-VERIFY-EXIT0 with a `CliRunner.invoke(eval_group, ["verify", "--out", str(tmp_out)])` assertion (exit 0; chain_head matches the just-emitted run's chain_head).
- **F-COV-6 (HARDEN):** No AC for `tests/fixtures/sut/deterministic_vuln_sut.py` documenting the `harness_output` shape contract. Added AC-SUT-CONTRACT: the stub SUT's emitted `harness_output` matches what `bench/vuln-remediation/rubric.py`'s `score(case, harness_output)` reads (per S5-02 HARDENED contract); a unit test invokes `score(case, stub_sut(case))` for each of the 10 cases and asserts it returns a valid `BenchScore` without raising.
- **F-TQ-4 (HARDEN):** Original `digest.startswith("blake3:") and len(digest) == 71` is mutation-weak. Tightened to `re.fullmatch(r"^blake3:[0-9a-f]{64}$", digest)` + byte-equality to recomputed `compute_case_dir_digest(case_dir)`. Mirror S5-03 AC-3 / S5-04 AC-3.
- **F-TQ-5 (HARDEN):** `block_severity_failure_modes` JSON-form (list-after-round-trip vs tuple-in-Python) was unspecified. Pinned: the JSONL aggregate's value is a JSON list; each element is one of the codes declared `severity: block` in `bench/vuln-remediation/failure_modes.yaml`; the test loads the YAML and filters by severity to derive the allowed set.
- **F-TQ-6 (HARDEN):** Stub SUT output distribution was unconstrained — a stub returning all-passing `harness_output` collapses `lower_bound_95` to 1.0 and the recorded candidate threshold is uninformative. Added AC-STUB-DIST: the stub SUT's deterministic outputs produce `0 < mean_score < 1` AND `0 < score_stddev` AND `lower_bound_95 < mean_score` strictly — i.e., a non-trivial mix that exercises the BCa bootstrap meaningfully. The mix is hand-curated to the 10 cases' difficulty/disposition diversity per S5-03 AC-7 / S5-04 AC-7.
- **F-TQ-7 (HARDEN):** Audit-chain extension's `prev_hash == prior_tip` invariant was not asserted at the story-test boundary. Added AC-CHAIN-EXTEND: read the prior chain tip before the run, run, then assert the new record's `prev_hash` equals the captured prior tip.
- **F-DP-1 (PROMOTED to AC):** `compute_case_dir_digest` promotion at the rule-of-three (S5-05 IS the third consumer per S5-03 / S5-04 F-DP-1). Public surface lives at `src/codegenie/eval/digests.py`; the loader's `_compute_case_dir_digest` becomes a one-line alias. AC-DIG-PROMOTE pins the public name and forbids inline reimplementation in any consumer (scripts or tests).
- **F-DP-2 (PROMOTED to AC):** Open/Closed for `scripts/sign_bench_digests.py` and `scripts/verify_bench_digests.py` — both take a `--bench-root` and a `--task-class` and walk; adding a new task class requires zero edits to either script. AC-SCRIPT-OPENCLOSED pins this with a test that registers a second stub task class and runs both scripts against `bench/<stub>/cases/`.
- **F-DP-3 (surfaced):** `SystemUnderTest` Protocol — the deterministic stub satisfies the protocol pinned by S4-02 AC-3 (`Callable[[BenchCase], Awaitable[Mapping[str, Any]]]`); mypy --strict over the test confirms structural conformance. Surfaced in Notes; not promoted.
- **F-DP-4 (surfaced):** README candidate-threshold paragraph is a per-task-class Strategy pattern; S6-03 (distroless) will copy it verbatim. When S7's third bench (`migration-chainguard-distroless` post-graduation OR Phase 8 reuse) lands, extract a `bench/_threshold_disclaimer.md.tmpl` partial and source it. NOT this story's job. Surfaced in Notes.

## Context

The 10 cases exist (5+5), the rubric exists, the harness exists, the CLI exists. This story locks the bench by signing every case in `bench/vuln-remediation/cases/digests.yaml` and proves the bench works end-to-end: the eval CLI exits 0 on a CI runner within the cold-cache **stub-SUT** budget (≤ 90 s) AND the nightly canary against the real SUT runs within the cold-cache **real-SUT** budget (≤ 15 min per `phase-arch-design.md §Performance regression tests`), the produced `BenchRunReport` carries a real `lower_bound_95` value, and that value is recorded — with an explicit "uncalibrated" comment — in `bench/vuln-remediation/README.md` as the **candidate** bronze→silver promotion threshold.

ADR-0002 reframes "what gets recorded as evidence" from `mean_score` to `lower_bound_95` (the 1000-resample BCa bootstrap one-sided 95% lower bound, deterministic seed `int(run_id[:8], 16)`). The number is one-sided and conservative; calibration to the actual bronze/silver tier thresholds in `docs/trust-tiers.yaml` is a Phase 13 concern (production ADR-0015). Phase 6.5 records the *number* and labels it uncalibrated; Phase 7 reads it as input to its own promotion-precondition logic per the roadmap amendment in S7-03.

This story also ships the F-DP-1 rule-of-three promotion: `_compute_case_dir_digest` → public `codegenie.eval.digests.compute_case_dir_digest`. The new module is consumed by `scripts/sign_bench_digests.py`, `scripts/verify_bench_digests.py`, and the integration test; the loader's private helper becomes a one-line forwarder. Adding the next task-class's `digests.yaml` (S6-03 for distroless) requires zero edits to either operator script or the public helper — the scripts walk `bench/<task-class>/cases/` parameterically.

The integration test runs **in-process** via `click.testing.CliRunner.invoke(eval_group, [...])` — not via `subprocess.run([sys.executable, "-m", "codegenie", ...])` — so that the test's autouse conftest can register the deterministic stub SUT into the in-process `default_sut_registry`. Subprocess-shape coverage is preserved by the nightly canary against the real `VulnRemediationSut` (Phase 6) and by S6-03's distroless E2E. This is a deliberate test-scope decision per F-TQ-2.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §`bench/{task-class}/` directory contract` — `cases/digests.yaml` format is `{case-id: blake3:<hex>}`.
  - `../phase-arch-design.md §Control flow` — the full happy-path sequence; `lower_bound_95` is computed at aggregate time with seed `int(run_id[:8], 16)`.
  - `../phase-arch-design.md §Scenarios → Scenario 1: Nightly eval run on vuln-remediation (happy path)` — the contract for what a green E2E run looks like end-to-end.
  - `../phase-arch-design.md §Performance regression tests` — nightly canary cold-cache ≤ 15 min (20% headroom over 12-min target); warm ≤ 12 s.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md §Decision` — every rubric call is a fresh subprocess + SCRUBBED env; this story exercises the contract under load.
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md §Decision §Consequences` — `lower_bound_95` is the gate's signal; calibration is uncalibrated at Phase 6.5; Phase 13 calibrates; deterministic seed `int(run_id[:8], 16)`.
  - `../ADRs/0003-tier-identifiers-as-str-validated-at-startup.md §Decision` — `Literal["bronze","silver","gold"]` are the verbatim identifiers used in the README's "Candidate bronze→silver threshold" wording.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md §Decision §Consequences` — every `BenchRunReport` carries `isolation_class="subprocess"`; this story's run records that value; the gate's same-population precondition is in force from this run forward.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — the promotion gate is advisory only; this story produces *evidence*, not a decision. `--with-verdict` is intentionally out of scope.
  - `../../../production/adrs/0015-trust-score-threshold-calibration.md` — the per-task-class threshold calibration ADR; named in the README disclaimer as the deferral target.
- **Source design:** `../High-level-impl.md §Step 5` "Done criteria" — names the cold/warm budgets and `lower_bound_95` recording.
- **Sibling story contracts (HARDENED — load-bearing for this story):**
  - `S5-03-vuln-rag-corpus-derived-cases.md §AC-3 §AC-6 §AC-6a` — canonical `_compute_case_dir_digest` consumption; 3-way digest consistency (`case.toml#case_digest == digests.yaml[case_id] == compute_case_dir_digest(case_dir)`).
  - `S5-03 §"Digests algorithm extraction surfaced (F-DP-1)"` + `S5-04 §F-DP-1` — the rule-of-three trigger condition; **S5-05 is the third consumer** and ships the promotion.
  - `S5-04-vuln-held-out-cases.md §AC-6` — `digests.yaml` 10-entry shape (5 RAG + 5 held-out, sorted alphabetically); `held-out-cve-exclusion-manifest.yaml` sibling under `cases/` that the loader walk must pass over.
  - `S5-02-vuln-rubric-and-unit-tests.md §AC-1 §AC-2` — the rubric reads `harness_output` only (never `expected/`); the deterministic stub SUT's contract surface is `harness_output`.
  - `S4-02-eval-run-subcommand.md §AC-1 §AC-3 §AC-9 §AC-10 §AC-14` — CLI flags + `sut_registry` seam + exit-code mapping via `main()` + JSONL aggregate shape (including `chain_head` equality and `isolation_class="subprocess"`) + `--out` override.
  - `S4-01-cli-scaffold-exit-codes.md §AC-2 §AC-3` — `EXIT_DIGEST_MISMATCH=6` and the `_EXIT_CODE_TABLE` mapping; `BenchCaseDigestMismatch` → 6; `ChainTamperDetected` → 5.
  - `S4-03-eval-verify-subcommand.md §AC` — `codegenie eval verify --out=<dir>` exit 0 on chain integrity.
  - `S2-02-loader-cases-and-digests.md §AC-3 §AC-6a §AC-6b` — canonical digest algorithm; `digests.yaml` schema; `digests.yaml` ↔ filesystem completeness.
  - `S2-04-audit-chain-extension.md §AC-2 §AC-3a` — `write_run_record` filename derivation (`f"{utc_iso}-{secrets.token_hex(4)}.json"`); persisted `chain_head` equals returned head; `prev_hash` equals prior tip.
  - `S1-02-wire-models-frozen-extra-forbid.md §AC` — `BenchRunReport` field shapes (including the `isolation_class` and `lower_bound_95` fields S5-05 asserts).

## Goal

Sign all 10 vuln-remediation cases in `bench/vuln-remediation/cases/digests.yaml` via a CI-runnable signing path that consumes the public `compute_case_dir_digest` (promoted in this story per the S5-03/S5-04 F-DP-1 rule-of-three trigger); prove `codegenie eval run --task-class=vuln-remediation` exits 0 against a deterministic stub SUT within the CI-integration budget (≤ 90 s) AND establishes the nightly real-SUT canary budget baseline (≤ 15 min, 20% headroom over 12-min target); record the emitted `lower_bound_95` value (with the uncalibrated disclaimer naming ADR-0002 + production ADR-0015) in `bench/vuln-remediation/README.md` as the candidate bronze→silver threshold; ship `scripts/sign_bench_digests.py` and `scripts/verify_bench_digests.py` as task-class-parameterized operator tools (Open/Closed — adding the next task class is zero edits).

## Acceptance criteria

- [ ] **AC-1 (digests.yaml shape — exactly 10 sorted entries; canonical regex per entry).** `bench/vuln-remediation/cases/digests.yaml` exists; `yaml.safe_load(text)` returns a `dict[str, str]`; `len(d) == 10`; the set of keys equals `{p.name for p in (BENCH_ROOT/"vuln-remediation"/"cases").iterdir() if p.is_dir() and (p / "case.toml").is_file()}` (filters out `held-out-cve-exclusion-manifest.yaml` and any sibling files); each value satisfies `re.fullmatch(r"^blake3:[0-9a-f]{64}$", value)`; the file's serialized form equals `yaml.safe_dump(d, sort_keys=True)` byte-for-byte (catches a curator hand-editing without sort).

- [ ] **AC-2 (3-way digest consistency — story-test boundary + script gate).** For each of the 10 cases: `case.toml#case_digest == digests.yaml[case_id] == compute_case_dir_digest(case_dir)` (all three byte-equal). The integration test asserts this triple-equality per case; `scripts/verify_bench_digests.py --bench-root=bench --task-class=vuln-remediation` exits 0 in the happy state and exits 1 with a diagnostic naming the offending case_id when any of the three pairs diverge. Both consumers go through `codegenie.eval.digests.compute_case_dir_digest` — no inline reimplementation of the algorithm anywhere in `scripts/` or `tests/`.

- [ ] **AC-DIG-PROMOTE (F-DP-1 rule-of-three — public helper promotion).** New module `src/codegenie/eval/digests.py` exposes `def compute_case_dir_digest(case_dir: Path) -> str` and is re-exported from `codegenie.eval.__init__` as `compute_case_dir_digest`. The loader's `_compute_case_dir_digest` becomes a one-line `compute_case_dir_digest = _eval_digests.compute_case_dir_digest` alias (no behavior change; loader's existing call sites keep their import paths working — Rule 11). A unit test asserts `from codegenie.eval.digests import compute_case_dir_digest` succeeds AND `from codegenie.eval.loader import _compute_case_dir_digest` still resolves AND both names refer to the same function object (`is`-identity). An AST/import lint asserts no module under `src/codegenie/`, `tests/`, or `scripts/` re-implements the algorithm (sentinel string match: the canonical algorithm's `b"\x1f"` and `b"\x1e"` separator literals appear only inside `src/codegenie/eval/digests.py`).

- [ ] **AC-3a (CI integration test budget — stub SUT, ≤ 90 s wall-clock; hard fail on regression).** `tests/integration/eval/test_eval_end_to_end_vuln.py::test_e2e_run_exits_zero_within_stub_budget` runs the eval via `CliRunner.invoke(eval_group, ["run", "--task-class=vuln-remediation", "--out", str(tmp_runs), "--bench-root", str(tmp_bench), "--cache-dir", str(tmp_cache)])` with the deterministic stub SUT (autouse-registered via `tests/fixtures/sut/deterministic_vuln_sut.py`'s `@register_sut("vuln-remediation", ...)`); `result.exit_code == 0`; `elapsed < 90.0` (wall-clock measured around the `CliRunner.invoke` call); the on-disk record under `tmp_runs` round-trips to a valid `BenchRunReport`.

- [ ] **AC-3b (nightly canary budget — real SUT, ≤ 15 min cold cache).** A separate CI workflow `nightly-eval-vuln.yml` (out-of-scope: per Phase 7 / Phase 13 scheduling — this story merely names the contract) is required to invoke `codegenie eval run --task-class=vuln-remediation --no-cache` against the real `VulnRemediationSut` and assert `wall_clock < 15 * 60` seconds. First run establishes baseline; this story commits the workflow stub and a `tests/integration/eval/test_real_sut_canary_workflow_exists.py` AST assertion (`.github/workflows/nightly-eval-vuln.yml` exists; contains `runs-on:` and the eval-run command literal). The real-SUT pass/fail is a flag, not a CI block, until Phase 6 ships and the SUT exists.

- [ ] **AC-4 (`BenchRunReport` field invariants — complete happy path).** The aggregate `BenchRunReport` (both the JSONL `kind="aggregate"` line and the on-disk record at `tmp_runs/*.json`) has: `task_class == "vuln-remediation"`, `len(per_case) == 10`, `mean_score ∈ [0, 1]`, `0 ≤ score_stddev < 1`, `0 ≤ lower_bound_95 ≤ mean_score`, `0 ≤ passed_count ≤ 10`, `total_cost_usd ≥ 0`, `block_severity_failure_modes` is a JSON list whose every element is one of the codes declared with `severity: block` in `bench/vuln-remediation/failure_modes.yaml` (the test loads the YAML and derives the allowed set), `prev_hash` is a 64-hex string (the prior tip captured pre-run) or `None` (only if `tmp_runs` was empty before this run), `chain_head` is a 64-hex string, `complete is True`, **and** `isolation_class == "subprocess"` (ADR-0010). The JSONL aggregate's field set is a superset of these.

- [ ] **AC-CHAIN-EXTEND (prior tip ↔ new record `prev_hash` invariant — story-test boundary).** Before the integration-test run: capture `prior_tip = read_chain_head(tmp_runs)` (returns `None` if no prior records). After the run: `len(list(tmp_runs.glob("*.json"))) == prior_count + 1`; the newest record's `prev_hash == prior_tip` (byte-equal); the newest record's `chain_head == aggregate["chain_head"]`. Defense-in-depth on S2-04 §AC-3a.

- [ ] **AC-VERIFY-EXIT0 (`codegenie eval verify` exits 0 after the run).** After AC-3a's run, invoke `CliRunner.invoke(eval_group, ["verify", "--out", str(tmp_runs)])`; `result.exit_code == 0`; the verify subcommand emits a `VerifyResult` whose `chain_head == aggregate["chain_head"]` (parsed from stdout via the `--format=jsonl` shape per S4-03). Catches a regression where the writer and the verifier disagree on the chain.

- [ ] **AC-6 (README "Candidate bronze→silver threshold" section — value + disclaimer literal text).** `bench/vuln-remediation/README.md` contains a section whose markdown header is `## Candidate bronze→silver threshold` (or equivalent unambiguous header containing `Candidate`, `bronze`, `silver`, `threshold` tokens). Under it: (a) a paragraph stating the captured `lower_bound_95` value rendered to **at least 3 significant figures**, parseable by `re.search(r"\\b(0\\.\\d{2,4})\\b", paragraph)` — a curator hand-writing `0.00` passes the format but AC-6a's same-run cross-check catches it; (b) the literal text `**Uncalibrated** — calibration deferred to Phase 13 per ADR-0002 (statistic) and production ADR-0015 (threshold calibration). Phase 7 reads this as candidate input only.` (case-sensitive; the integration test asserts `EXPECTED_DISCLAIMER in readme_text`). The integration test parses the section, extracts the numeric value, asserts it's a `float ∈ [0, 1]`.

- [ ] **AC-6a (same-run README value cross-check — median-of-3 jitter allowance).** The extracted README threshold value MUST be within ±0.05 of the aggregate's `lower_bound_95` from the AC-3a run (allowing the median-of-3 noise the Notes describe). The test does `abs(readme_value - aggregate["lower_bound_95"]) ≤ 0.05`. Mutation-tightening: a curator hand-writing a stale value from a prior run (drift > 0.05) fails this.

- [ ] **AC-7 (digest invalidation → exit 6 via isolated tmp bench-root).** The integration test copies `bench/vuln-remediation/` to `tmp_path / "bench" / "vuln-remediation"`, mutates one signed file under `tmp_bench/cases/<case_id>/input/` (e.g., appends `b"\n"`), invokes `CliRunner.invoke(eval_group, ["run", "--task-class=vuln-remediation", "--bench-root", str(tmp_bench), "--out", str(tmp_runs2)])`, and asserts `result.exit_code == 6` (`EXIT_DIGEST_MISMATCH` per S4-01 AC-2). The real working tree is NEVER mutated. S5-06 owns the focused invalidation test suite; this AC asserts the end-to-end path here.

- [ ] **AC-SIGN-IDEMP (`scripts/sign_bench_digests.py` is idempotent).** `scripts/sign_bench_digests.py --bench-root=<tmp_bench> --task-class=vuln-remediation` writes `<tmp_bench>/cases/digests.yaml`. Running it a second time against the same `<tmp_bench>` produces a byte-identical file (`hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()`). A unit test asserts this.

- [ ] **AC-SCRIPT-OPENCLOSED (`sign_bench_digests` + `verify_bench_digests` are task-class-parameterized — Open/Closed).** Both scripts accept `--task-class=<name>` and `--bench-root=<path>` and walk `<bench-root>/<task-class>/cases/*/` for case directories; neither script contains the literal `vuln-remediation` (or any task-class name). A test registers a synthetic stub task class (a fresh `bench/_test_stub/cases/` tree under `tmp_path`) and invokes both scripts against it — `sign` produces a valid `digests.yaml`; `verify` exits 0. Adding `migration-chainguard-distroless` (S6-03) is a directory creation, not a script edit.

- [ ] **AC-STUB-DIST (deterministic stub SUT produces non-trivial score distribution).** `tests/fixtures/sut/deterministic_vuln_sut.py` returns hand-curated `harness_output` for each of the 10 cases such that the rubric produces: `0 < mean_score < 1.0`, `0 < score_stddev < 0.5`, `lower_bound_95 < mean_score` (strict — the BCa bootstrap is meaningfully exercised), and at least one case scores 0.0 (block-severity failure mode triggered) AND at least one case scores 1.0 (clean pass). A unit test asserts these invariants on the stub-SUT-driven aggregate.

- [ ] **AC-SUT-CONTRACT (stub SUT's `harness_output` matches rubric's reader contract).** For each of the 10 cases, `from bench.vuln_remediation.rubric import score; score(case, stub_sut(case))` returns a valid `BenchScore` without raising. The test parameterizes over the 10 cases and asserts `isinstance(result, BenchScore)`. Catches a stub-SUT/rubric contract drift before the integration test surfaces the same problem behind exit-code 1.

- [ ] **AC-CONFTEST-REGISTRATION (autouse conftest registers the stub SUT into `default_sut_registry`).** `tests/fixtures/sut/conftest.py` (autouse for `tests/integration/eval/`) executes `import tests.fixtures.sut.deterministic_vuln_sut` whose module-level `@register_sut("vuln-remediation", registry=default_sut_registry, sut_digest_fn=…)` populates the in-process registry. The integration test asserts `from codegenie.eval.sut_registry import resolve_sut; resolve_sut("vuln-remediation").sut is deterministic_vuln_sut.stub_sut`. A teardown clears the registration to avoid cross-test pollution (use `pytest.fixture(autouse=True)` yield + `default_sut_registry._unregister("vuln-remediation")` — name reserved by S4-02 AC-3 for test isolation; if not present, the conftest creates a fresh `SutRegistry()` per test and monkeypatches `default_sut_registry`).

- [ ] **AC-LINT-RED-GREEN (red→green; lint + typecheck + fence green).** Red test from §TDD plan (`tests/integration/eval/test_eval_end_to_end_vuln.py`) exists, was committed at red, now green. `ruff check tests/integration/eval/test_eval_end_to_end_vuln.py tests/fixtures/sut/ scripts/ src/codegenie/eval/digests.py`, `ruff format --check` on same paths, `mypy --strict src/codegenie/eval/digests.py tests/integration/eval/test_eval_end_to_end_vuln.py tests/fixtures/sut/deterministic_vuln_sut.py`, `pytest tests/integration/eval/test_eval_end_to_end_vuln.py -v`, `pytest tests/unit/eval/test_digests_module.py -v` all pass. `make fence` continues to pass — `codegenie.eval.digests` is closure-internal; no LLM SDK imports introduced; `scripts/` and `bench/` remain outside the policed runtime closure.

## Implementation outline

1. **Write the red test first** under `tests/integration/eval/test_eval_end_to_end_vuln.py` — see §TDD plan. Confirm it fails with one of: `digests.yaml` missing, `compute_case_dir_digest` not importable from `codegenie.eval.digests`, `default_sut_registry` not populated for `"vuln-remediation"`, or the README disclaimer absent. Commit as the red marker.

2. **Promote the canonical digest helper** (F-DP-1 rule-of-three trigger):
   - Create `src/codegenie/eval/digests.py`:
     ```python
     """Canonical case-directory BLAKE3 digest helper.

     Promoted from private codegenie.eval.loader._compute_case_dir_digest
     at the rule-of-three trigger surfaced by S5-03/S5-04 F-DP-1: this
     story's three consumers (sign_bench_digests, verify_bench_digests,
     integration test) plus the loader.
     """
     from pathlib import Path
     import blake3

     _RECORD_SEP = b"\x1f"   # ASCII Unit Separator — between relpath and content-hash
     _GROUP_SEP = b"\x1e"    # ASCII Record Separator — between records

     def compute_case_dir_digest(case_dir: Path) -> str:
         """BLAKE3 over the canonical case-directory serialization.

         Algorithm pinned by S2-02 §AC-3:
           1. Walk case_dir.rglob("*") ONCE.
           2. Filter to regular non-symlink files (S2-02 §AC-9 rejects symlinks).
           3. Exclude case.toml (per ADR-0005 §Consequences).
           4. Sort by p.relative_to(case_dir).as_posix() ascending.
           5. Per file: f"{rel_posix}\x1f{content_hash(p)}".encode("utf-8").
           6. Join records with \x1e.
           7. BLAKE3 once, hexdigest, prefix with "blake3:".
         """
         ...
     ```
   - Edit `src/codegenie/eval/loader.py`: replace the body of `_compute_case_dir_digest` with `from codegenie.eval.digests import compute_case_dir_digest as _compute_case_dir_digest` (so existing import sites stay green — Rule 11). The loader still exposes the private name; the public name is the new path.
   - Re-export from `src/codegenie/eval/__init__.py`: add `from codegenie.eval.digests import compute_case_dir_digest as compute_case_dir_digest` (the `as` form keeps mypy --strict's `--no-implicit-reexport` happy).

3. **Sign all 10 case digests via the new operator script** `scripts/sign_bench_digests.py`:
   ```python
   #!/usr/bin/env python3
   """Sign every bench/<task-class>/cases/<case-id>/ directory; write digests.yaml.

   Open/Closed: --task-class and --bench-root parameterize; no task-class name
   appears as a literal in this script (AC-SCRIPT-OPENCLOSED).
   """
   import argparse, sys
   from pathlib import Path
   import yaml
   from codegenie.eval.digests import compute_case_dir_digest

   def main() -> int:
       parser = argparse.ArgumentParser()
       parser.add_argument("--task-class", required=True)
       parser.add_argument("--bench-root", type=Path, default=Path("bench"))
       args = parser.parse_args()

       cases_root = args.bench_root / args.task_class / "cases"
       digests = {
           p.name: compute_case_dir_digest(p)
           for p in sorted(cases_root.iterdir())
           if p.is_dir() and (p / "case.toml").is_file()
       }
       (cases_root / "digests.yaml").write_text(
           yaml.safe_dump(digests, sort_keys=True, default_flow_style=False)
       )
       return 0

   if __name__ == "__main__":
       sys.exit(main())
   ```
   Filter on `(p / "case.toml").is_file()` so that sibling files (e.g., S5-04's `held-out-cve-exclusion-manifest.yaml`) are skipped. Idempotence (AC-SIGN-IDEMP) follows from `sort_keys=True` + `default_flow_style=False` + the deterministic algorithm.

4. **Verify parity via** `scripts/verify_bench_digests.py`:
   ```python
   """Verify digests.yaml ↔ filesystem ↔ case.toml#case_digest 3-way consistency.

   Exit 0 on parity; exit 1 with a diagnostic naming the offending case_id otherwise.
   """
   # ...parse --task-class, --bench-root; load digests.yaml; loop cases; for each:
   #   recomputed = compute_case_dir_digest(case_dir)
   #   in_yaml = digests[case_id]
   #   in_toml = tomllib.loads((case_dir/"case.toml").read_text())["case_digest"]
   #   assert recomputed == in_yaml == in_toml, f"divergence at {case_id}: ..."
   # Operator-readable diagnostic on failure.
   ```

5. **Build the deterministic stub SUT** at `tests/fixtures/sut/deterministic_vuln_sut.py`:
   - Module-level `@register_sut("vuln-remediation", sut_digest_fn=_stub_sut_digest, registry=default_sut_registry)` decorates an async `stub_sut(case: BenchCase) -> Mapping[str, Any]` function.
   - The stub returns hand-curated `harness_output` per `case.case_id`, hitting AC-STUB-DIST's distribution invariants: at least one case scoring 0.0 (block-severity failure mode), at least one scoring 1.0 (clean pass), the remaining 8 producing the score mix that yields `0 < mean_score < 1` and a meaningful BCa lower bound.
   - The output shape (`harness_output["validator"]["cve_dropped"]`, etc.) matches what `bench/vuln-remediation/rubric.py`'s `score(case, harness_output)` reads (S5-02 contract).
   - `_stub_sut_digest()` returns a stable BLAKE3 over the stub's source file (so the cache key is deterministic across reruns of the same stub).
   - Document the `harness_output` shape contract in `tests/fixtures/sut/README.md` (the same patterns next task classes copy — F-DP-4).

6. **Autouse conftest** at `tests/fixtures/sut/conftest.py`:
   ```python
   import pytest
   from codegenie.eval.sut_registry import SutRegistry, default_sut_registry

   @pytest.fixture(autouse=True)
   def _isolate_sut_registry(monkeypatch):
       """Each test gets a fresh SutRegistry; stub SUTs register into it."""
       fresh = SutRegistry()
       monkeypatch.setattr("codegenie.eval.sut_registry.default_sut_registry", fresh)
       # Import side effect populates the fresh registry:
       from tests.fixtures.sut import deterministic_vuln_sut  # noqa: F401
       # The module-level @register_sut(...) call uses default_sut_registry,
       # which we've just swapped to `fresh`. Re-execute the decorator via
       # importlib.reload if the module was previously cached:
       import importlib
       importlib.reload(deterministic_vuln_sut)
       yield
       # monkeypatch tears down; original default_sut_registry restored.
   ```
   The reload-on-each-test pattern avoids cross-test SUT pollution. If `importlib.reload` proves brittle, an alternative is to wire the stub's registration through an explicit `register_in(registry: SutRegistry)` helper that the conftest calls directly, bypassing the module-level decorator (the conftest, not the test, owns registration).

7. **Run the harness once locally**: `pytest tests/integration/eval/test_eval_end_to_end_vuln.py -v -k test_e2e_run`. Capture the printed `lower_bound_95` value (the AC-3a test logs it before the AC-4 assertions). Iterate the stub's `harness_output` shapes until AC-STUB-DIST is satisfied with a stable median across 3 manual runs.

8. **Update** `bench/vuln-remediation/README.md`:
   - Add a `## Candidate bronze→silver threshold` section.
   - Record the median-of-3 `lower_bound_95` value to 3 sig figs.
   - Include the literal disclaimer:
     ```markdown
     **Uncalibrated** — calibration deferred to Phase 13 per ADR-0002 (statistic)
     and production ADR-0015 (threshold calibration). Phase 7 reads this as
     candidate input only.
     ```
   - Add a brief operator note: "Re-sign via `python scripts/sign_bench_digests.py --task-class=vuln-remediation`; verify via `python scripts/verify_bench_digests.py --task-class=vuln-remediation`."

9. **Establish the nightly canary stub** (AC-3b):
   - Add `.github/workflows/nightly-eval-vuln.yml` with `runs-on: ubuntu-24.04`, scheduled at 07:00 UTC, invoking `python -m codegenie eval run --task-class=vuln-remediation --no-cache --out=.codegenie/eval/runs/canary`. The workflow does NOT register the real `VulnRemediationSut` (it does not exist yet — Phase 6 ships it); the first nightly run will exit 3 (`TaskClassNotFound` / unregistered SUT) until Phase 6 ships. That is the documented baseline: the canary is plumbed but the SUT is the missing dependency. Commit a comment in the workflow file naming Phase 6 as the dependency.
   - Add `tests/integration/eval/test_real_sut_canary_workflow_exists.py` asserting the workflow file exists and contains the expected `runs-on:` + command literal.

10. **Lint, typecheck, fence, full test suite** per AC-LINT-RED-GREEN.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/eval/test_eval_end_to_end_vuln.py` (under the existing Phase 6.5 eval integration tests' directory — siblings: `test_cli_run.py`, `test_audit_chain.py`).

```python
# tests/integration/eval/test_eval_end_to_end_vuln.py
"""End-to-end run of bench/vuln-remediation/ via CliRunner against a
deterministic stub SUT. Runs IN-PROCESS so the autouse conftest can
populate default_sut_registry with the stub. Subprocess-shape coverage
is the nightly canary's job (Phase 6's real VulnRemediationSut).

ADRs: 0001 (subprocess rubric exercised in vivo), 0002 (lower_bound_95
recorded), 0010 (isolation_class annotated)."""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from codegenie.eval.cli import eval_group
from codegenie.eval.digests import compute_case_dir_digest

REPO_ROOT = Path(__file__).parents[3]  # tests/integration/eval/ -> tests/integration/ -> tests/ -> REPO_ROOT
BENCH_ROOT = REPO_ROOT / "bench"
VULN_BENCH = BENCH_ROOT / "vuln-remediation"

EXPECTED_DISCLAIMER = (
    "**Uncalibrated** — calibration deferred to Phase 13 per "
    "ADR-0002 (statistic) and production ADR-0015 (threshold calibration). "
    "Phase 7 reads this as candidate input only."
)


# ----- AC-1 digests.yaml shape -----------------------------------------------

def test_digests_yaml_signs_exactly_ten_sorted_canonical_entries() -> None:
    """AC-1: 10 entries, regex per value, byte-equal to sort_keys=True dump."""
    digests_path = VULN_BENCH / "cases" / "digests.yaml"
    assert digests_path.exists(), "digests.yaml missing"
    raw = digests_path.read_text()
    sig = yaml.safe_load(raw)
    assert isinstance(sig, dict)
    expected_keys = {
        p.name
        for p in (VULN_BENCH / "cases").iterdir()
        if p.is_dir() and (p / "case.toml").is_file()
    }
    assert set(sig.keys()) == expected_keys, f"keys differ: {set(sig.keys())} vs {expected_keys}"
    assert len(sig) == 10, f"want 10 cases, got {len(sig)}"
    for case_id, digest in sig.items():
        assert re.fullmatch(r"^blake3:[0-9a-f]{64}$", digest), f"{case_id}: bad digest {digest!r}"
    canonical = yaml.safe_dump(sig, sort_keys=True, default_flow_style=False)
    assert raw == canonical, "digests.yaml is not in canonical sort_keys=True form"


# ----- AC-2 3-way digest consistency -----------------------------------------

import tomllib

@pytest.mark.parametrize("case_dir", sorted(
    p for p in (VULN_BENCH / "cases").iterdir()
    if p.is_dir() and (p / "case.toml").is_file()
))
def test_three_way_digest_consistency(case_dir: Path) -> None:
    """AC-2: case.toml#case_digest == digests.yaml[case_id] == compute_case_dir_digest(case_dir)."""
    digests_yaml = yaml.safe_load((VULN_BENCH / "cases" / "digests.yaml").read_text())
    case_toml = tomllib.loads((case_dir / "case.toml").read_text())
    in_toml = case_toml["case_digest"]
    in_yaml = digests_yaml[case_dir.name]
    recomputed = compute_case_dir_digest(case_dir)
    assert in_toml == in_yaml == recomputed, (
        f"{case_dir.name}: toml={in_toml} yaml={in_yaml} recomputed={recomputed}"
    )


# ----- AC-DIG-PROMOTE public helper promotion --------------------------------

def test_compute_case_dir_digest_public_and_private_alias_to_same_function() -> None:
    """AC-DIG-PROMOTE: loader's private name forwards to the public module."""
    from codegenie.eval.digests import compute_case_dir_digest as public_fn
    from codegenie.eval.loader import _compute_case_dir_digest as private_fn
    from codegenie.eval import compute_case_dir_digest as reexported_fn
    assert public_fn is private_fn, "loader's private name must forward to digests module"
    assert public_fn is reexported_fn, "codegenie.eval.__init__ must re-export"


def test_no_inline_reimplementation_of_digest_algorithm() -> None:
    """AC-DIG-PROMOTE: the canonical separator literals appear only in digests.py."""
    SENTINELS = (b"\\x1f", b"\\x1e", "\\x1f", "\\x1e")
    found_in: list[Path] = []
    for sentinel in (rb"\\x1f", rb"\\x1e"):  # literal-bytes form curators might use
        for path in REPO_ROOT.rglob("*.py"):
            if "/.venv/" in str(path) or "/tests/cassettes/" in str(path):
                continue
            text = path.read_bytes()
            if sentinel in text and path.name != "digests.py":
                found_in.append(path)
    assert not found_in, f"digest separator literals found outside digests.py: {found_in}"


# ----- AC-3a / AC-4 / AC-CHAIN-EXTEND / AC-VERIFY-EXIT0 happy path -----------

@pytest.fixture
def isolated_run(tmp_path: Path) -> dict[str, Path]:
    return {
        "tmp_runs": tmp_path / "runs",
        "tmp_cache": tmp_path / "cache",
    }


def _read_chain_head(runs_dir: Path) -> str | None:
    if not runs_dir.exists():
        return None
    records = sorted(runs_dir.glob("*.json"))
    if not records:
        return None
    return json.loads(records[-1].read_text())["chain_head"]


def test_e2e_happy_path_within_stub_budget_and_all_field_invariants(
    isolated_run: dict[str, Path],
) -> None:
    """AC-3a + AC-4 + AC-CHAIN-EXTEND + AC-VERIFY-EXIT0 + AC-CONFTEST-REGISTRATION."""
    tmp_runs = isolated_run["tmp_runs"]
    tmp_cache = isolated_run["tmp_cache"]
    prior_tip = _read_chain_head(tmp_runs)

    runner = CliRunner()
    start = time.monotonic()
    result = runner.invoke(
        eval_group,
        [
            "run",
            "--task-class=vuln-remediation",
            "--out", str(tmp_runs),
            "--bench-root", str(BENCH_ROOT),
            "--cache-dir", str(tmp_cache),
        ],
    )
    elapsed = time.monotonic() - start

    assert result.exit_code == 0, f"exit={result.exit_code}; stderr={result.stderr_bytes!r}; out={result.output[-2000:]}"
    assert elapsed < 90.0, f"stub-SUT E2E took {elapsed:.1f}s; budget 90s"

    lines = [json.loads(l) for l in result.output.splitlines() if l.strip()]
    per_case = [l for l in lines if l.get("kind") == "case"]
    aggregate_lines = [l for l in lines if l.get("kind") == "aggregate"]
    assert len(per_case) == 10
    assert len(aggregate_lines) == 1
    agg = aggregate_lines[0]

    # AC-4 BenchRunReport invariants
    assert agg["task_class"] == "vuln-remediation"
    assert len(agg["per_case"]) == 10
    assert 0.0 <= agg["mean_score"] <= 1.0
    assert 0.0 <= agg["score_stddev"] < 1.0
    assert 0.0 <= agg["lower_bound_95"] <= agg["mean_score"]
    assert 0 <= agg["passed_count"] <= 10
    assert agg["total_cost_usd"] >= 0.0
    assert agg["complete"] is True
    assert agg["isolation_class"] == "subprocess"
    assert re.fullmatch(r"^[0-9a-f]{64}$", agg["chain_head"])

    # AC-4 block_severity_failure_modes — allowed set from failure_modes.yaml
    fm_yaml = yaml.safe_load((VULN_BENCH / "failure_modes.yaml").read_text())
    block_codes = {row["code"] for row in fm_yaml if row.get("severity") == "block"}
    assert isinstance(agg["block_severity_failure_modes"], list)
    for code in agg["block_severity_failure_modes"]:
        assert code in block_codes, f"unknown block-severity code: {code}"

    # AC-CHAIN-EXTEND prev_hash ↔ prior tip
    records = sorted(tmp_runs.glob("*.json"))
    assert len(records) == 1  # tmp_runs was empty at start
    on_disk = json.loads(records[0].read_text())
    assert on_disk["prev_hash"] == prior_tip  # both None on a fresh tmp_runs
    assert on_disk["chain_head"] == agg["chain_head"]

    # AC-VERIFY-EXIT0 — eval verify finds the chain intact
    verify_result = runner.invoke(eval_group, ["verify", "--out", str(tmp_runs)])
    assert verify_result.exit_code == 0, f"verify failed: {verify_result.output}"


# ----- AC-6 / AC-6a README disclaimer + value cross-check --------------------

def test_readme_records_candidate_threshold_with_literal_disclaimer(
    isolated_run: dict[str, Path],
) -> None:
    """AC-6 + AC-6a: literal disclaimer text + value matches just-run aggregate within ±0.05."""
    readme = (VULN_BENCH / "README.md").read_text()
    assert "Candidate bronze→silver threshold" in readme or "## Candidate bronze" in readme, (
        "README missing the 'Candidate bronze→silver threshold' section header"
    )
    assert EXPECTED_DISCLAIMER in readme, "README disclaimer literal text missing or drifted"

    # Extract numeric value
    threshold_section = readme.split("Candidate bronze", 1)[1].split("##", 1)[0]
    match = re.search(r"\b(0\.\d{2,4})\b", threshold_section)
    assert match, f"no parseable threshold value in README section: {threshold_section!r}"
    readme_value = float(match.group(1))
    assert 0.0 <= readme_value <= 1.0

    # Cross-check against a fresh stub-SUT run
    runner = CliRunner()
    result = runner.invoke(
        eval_group,
        [
            "run",
            "--task-class=vuln-remediation",
            "--out", str(isolated_run["tmp_runs"]),
            "--bench-root", str(BENCH_ROOT),
            "--cache-dir", str(isolated_run["tmp_cache"]),
        ],
    )
    assert result.exit_code == 0
    agg = json.loads([l for l in result.output.splitlines() if '"kind":"aggregate"' in l or '"kind": "aggregate"' in l][0])
    assert abs(readme_value - agg["lower_bound_95"]) <= 0.05, (
        f"README threshold {readme_value} drifts from current run {agg['lower_bound_95']}"
    )


# ----- AC-7 digest invalidation → exit 6 via isolated bench-root -------------

def test_whitespace_edit_invalidates_digest_returns_exit_6(tmp_path: Path) -> None:
    """AC-7: copy bench to tmp_path, mutate the copy, assert exit 6. Real tree untouched."""
    tmp_bench = tmp_path / "bench"
    shutil.copytree(BENCH_ROOT, tmp_bench)
    tmp_vuln_cases = tmp_bench / "vuln-remediation" / "cases"

    # Pick the first case directory and mutate one input file
    case_dir = sorted(
        p for p in tmp_vuln_cases.iterdir()
        if p.is_dir() and (p / "case.toml").is_file()
    )[0]
    input_files = list((case_dir / "input").rglob("*"))
    target = next(p for p in input_files if p.is_file())
    target.write_bytes(target.read_bytes() + b"\n")

    runner = CliRunner()
    result = runner.invoke(
        eval_group,
        [
            "run",
            "--task-class=vuln-remediation",
            "--out", str(tmp_path / "runs"),
            "--bench-root", str(tmp_bench),
            "--cache-dir", str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 6, (
        f"want EXIT_DIGEST_MISMATCH=6, got {result.exit_code}; output={result.output[-2000:]}"
    )


# ----- AC-SIGN-IDEMP / AC-SCRIPT-OPENCLOSED ----------------------------------

def test_sign_bench_digests_is_idempotent(tmp_path: Path) -> None:
    """AC-SIGN-IDEMP: running the script twice yields a byte-identical digests.yaml."""
    import subprocess as sp
    tmp_bench = tmp_path / "bench"
    shutil.copytree(BENCH_ROOT, tmp_bench)
    digests_path = tmp_bench / "vuln-remediation" / "cases" / "digests.yaml"
    # First run
    sp.run(
        ["python", "scripts/sign_bench_digests.py", "--task-class=vuln-remediation",
         f"--bench-root={tmp_bench}"],
        cwd=REPO_ROOT, check=True,
    )
    first = digests_path.read_bytes()
    # Second run
    sp.run(
        ["python", "scripts/sign_bench_digests.py", "--task-class=vuln-remediation",
         f"--bench-root={tmp_bench}"],
        cwd=REPO_ROOT, check=True,
    )
    second = digests_path.read_bytes()
    assert first == second, "sign_bench_digests.py is not idempotent"


def test_sign_and_verify_scripts_are_task_class_parameterized(tmp_path: Path) -> None:
    """AC-SCRIPT-OPENCLOSED: scripts work for a synthetic task class without edits."""
    import subprocess as sp
    # Build a synthetic stub bench tree
    stub_bench = tmp_path / "bench"
    stub_case_dir = stub_bench / "_test_stub" / "cases" / "001-stub-case"
    (stub_case_dir / "input").mkdir(parents=True)
    (stub_case_dir / "expected").mkdir()
    (stub_case_dir / "input" / "hello.txt").write_text("hi\n")
    (stub_case_dir / "expected" / "out.txt").write_text("ok\n")
    # case.toml — minimal but case_digest unset; sign script computes
    (stub_case_dir / "case.toml").write_text(
        '# stub\ncase_id = "001-stub-case"\ncase_digest = "blake3:"\n'
        '# remaining fields elided for the script-shape test\n'
    )
    sp.run(
        ["python", "scripts/sign_bench_digests.py", "--task-class=_test_stub",
         f"--bench-root={stub_bench}"],
        cwd=REPO_ROOT, check=True,
    )
    assert (stub_bench / "_test_stub" / "cases" / "digests.yaml").is_file()
    # verify exits 0 — but only if case.toml#case_digest was updated to match.
    # For this story the verify-script consumes digests.yaml and recomputes; if
    # case.toml's case_digest is the stub "blake3:" placeholder, verify exits 1
    # with a useful diagnostic — that's the expected codepath for a not-yet-signed
    # case.toml. The test asserts the script exited with a non-crash code.
    verify_result = sp.run(
        ["python", "scripts/verify_bench_digests.py", "--task-class=_test_stub",
         f"--bench-root={stub_bench}"],
        cwd=REPO_ROOT, capture_output=True,
    )
    assert verify_result.returncode in {0, 1}, "verify script crashed"
    # Open/Closed: assert "vuln-remediation" does not appear in either script source.
    for script in ("sign_bench_digests.py", "verify_bench_digests.py"):
        src = (REPO_ROOT / "scripts" / script).read_text()
        assert "vuln-remediation" not in src
        assert "migration-chainguard-distroless" not in src


# ----- AC-STUB-DIST / AC-SUT-CONTRACT ----------------------------------------

def test_stub_sut_produces_nontrivial_score_distribution(isolated_run: dict[str, Path]) -> None:
    """AC-STUB-DIST: 0 < mean < 1, 0 < stddev, lower_bound_95 < mean, ≥1 zero, ≥1 one."""
    runner = CliRunner()
    result = runner.invoke(
        eval_group,
        [
            "run",
            "--task-class=vuln-remediation",
            "--out", str(isolated_run["tmp_runs"]),
            "--bench-root", str(BENCH_ROOT),
            "--cache-dir", str(isolated_run["tmp_cache"]),
        ],
    )
    assert result.exit_code == 0
    agg = next(json.loads(l) for l in result.output.splitlines() if '"aggregate"' in l)
    assert 0.0 < agg["mean_score"] < 1.0
    assert agg["score_stddev"] > 0.0
    assert agg["lower_bound_95"] < agg["mean_score"]
    per_case_scores = [c["score"] for c in agg["per_case"]]
    assert any(s == 0.0 for s in per_case_scores), "stub-SUT should produce ≥1 zero-score case"
    assert any(s == 1.0 for s in per_case_scores), "stub-SUT should produce ≥1 perfect-score case"


def test_stub_sut_harness_output_matches_rubric_reader_contract() -> None:
    """AC-SUT-CONTRACT: rubric.score(case, stub_sut(case)) returns valid BenchScore."""
    import asyncio
    from codegenie.eval.loader import load_task_class, load_cases
    from codegenie.eval.models import BenchScore
    from tests.fixtures.sut.deterministic_vuln_sut import stub_sut

    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    cases = load_cases(tc)
    from bench.vuln_remediation.rubric import score as rubric_score  # type: ignore[import-not-found]

    for case in cases:
        harness_output = asyncio.run(stub_sut(case))
        result = rubric_score(case, harness_output)
        assert isinstance(result, BenchScore), f"{case.case_id}: rubric returned {type(result)}"


# ----- AC-3b nightly canary workflow stub ------------------------------------

def test_nightly_canary_workflow_file_exists() -> None:
    """AC-3b: .github/workflows/nightly-eval-vuln.yml is committed."""
    workflow = REPO_ROOT / ".github" / "workflows" / "nightly-eval-vuln.yml"
    assert workflow.is_file()
    text = workflow.read_text()
    assert "runs-on:" in text
    assert "codegenie eval run --task-class=vuln-remediation" in text
    assert "--no-cache" in text
```

Run it; confirm one of: `digests.yaml` missing, `codegenie.eval.digests` import fails, `default_sut_registry` doesn't resolve `"vuln-remediation"`, `EXPECTED_DISCLAIMER` not in README, `nightly-eval-vuln.yml` missing, or 10-case count not reached. Commit as the red marker.

### Green — smallest impl shape

1. Ship `src/codegenie/eval/digests.py` (Step 2 of §Implementation outline). Verify `from codegenie.eval.digests import compute_case_dir_digest` works and `from codegenie.eval.loader import _compute_case_dir_digest` still resolves to the same object.
2. Ship `scripts/sign_bench_digests.py` and run `python scripts/sign_bench_digests.py --task-class=vuln-remediation`. Commit `bench/vuln-remediation/cases/digests.yaml`.
3. Ship `tests/fixtures/sut/deterministic_vuln_sut.py` + `conftest.py` + `README.md`. Iterate the stub's `harness_output` shapes until AC-STUB-DIST is satisfied (≥1 zero, ≥1 one, non-trivial mean/stddev).
4. Run the integration tests locally; iterate the stub until all ACs green.
5. Capture `lower_bound_95` from the AC-3a run (median of 3 manual runs); update `bench/vuln-remediation/README.md` with the threshold paragraph + literal disclaimer text.
6. Add `.github/workflows/nightly-eval-vuln.yml`. Commit.

### Refactor — clean up

- `bench/vuln-remediation/cases/digests.yaml` carries a header comment: `# Generated by scripts/sign_bench_digests.py --task-class=vuln-remediation. Do not edit by hand.`
- `scripts/sign_bench_digests.py` exits non-zero if the bench tree is missing `case.toml` in any case directory (operator-friendly diagnostic).
- `scripts/verify_bench_digests.py` is a thin CLI wrapper around a `verify_parity(bench_root: Path, task_class: str) -> list[str]` function (returns list of human-readable divergences; empty list = parity); the script prints them and exits `1 if divergences else 0`. The function is unit-testable.
- The "uncalibrated" wording in README is verbatim consistent across task classes — the same disclaimer should appear in `bench/migration-chainguard-distroless/README.md` after S6-03 (mechanical copy; not abstracted yet — Rule 2; F-DP-4 trigger fires when the third bench needs it).
- `tests/fixtures/sut/README.md` documents the `harness_output` shape contract so S6-03 (and any future task class's deterministic-stub SUT) copies the pattern.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/digests.py` | **New** — public `compute_case_dir_digest` (F-DP-1 rule-of-three promotion). |
| `src/codegenie/eval/__init__.py` | Extend — re-export `compute_case_dir_digest`. |
| `src/codegenie/eval/loader.py` | Edit — replace `_compute_case_dir_digest` body with one-line forward to `codegenie.eval.digests.compute_case_dir_digest` (Rule 11 — preserves existing import sites byte-for-byte). |
| `bench/vuln-remediation/cases/digests.yaml` | New — signs all 10 case directories; written by `scripts/sign_bench_digests.py`; sorted alphabetically. |
| `bench/vuln-remediation/README.md` | Extend — "Candidate bronze→silver threshold" section + literal `**Uncalibrated** … ADR-0002 (statistic) and production ADR-0015 (threshold calibration). Phase 7 reads this as candidate input only.` disclaimer + operator-runbook line for re-signing. |
| `tests/integration/eval/test_eval_end_to_end_vuln.py` | New — full TDD plan above; runs in-process via `CliRunner`. |
| `tests/fixtures/sut/deterministic_vuln_sut.py` | New — stub SUT decorated `@register_sut("vuln-remediation", ...)`; satisfies AC-STUB-DIST + AC-SUT-CONTRACT. |
| `tests/fixtures/sut/conftest.py` | New — autouse `_isolate_sut_registry` fixture that monkeypatches `default_sut_registry` and imports the stub module each test (or per-module). |
| `tests/fixtures/sut/README.md` | New — documents the `harness_output` shape contract; F-DP-4 lays the seed for S6-03 to copy. |
| `tests/unit/eval/test_digests_module.py` | New — unit tests for `compute_case_dir_digest` (deterministic, sort-invariant, excludes `case.toml`, rejects symlinks delegated to caller). |
| `scripts/sign_bench_digests.py` | New — task-class-parameterized signing operator script; idempotent. |
| `scripts/verify_bench_digests.py` | New — task-class-parameterized parity-verification operator script. |
| `.github/workflows/nightly-eval-vuln.yml` | New — nightly canary workflow stub; first runs return exit 3 until Phase 6 registers `VulnRemediationSut`; commit a comment naming Phase 6 as the dependency. |

## Out of scope

- **Cache hit-rate + invalidation deep tests.** S5-06 owns those — this story has a one-line invalidation sanity check (AC-7); S5-06 covers warm reruns, partial invalidation, distinct cache-key collision boundaries, etc.
- **Real-SUT nightly canary tuning.** The CI test uses a stub SUT. The real-SUT 12-min cold-cache budget is the nightly canary; first run establishes baseline; if it regresses, that is a separate flag and a separate fix. The workflow file lands; the SUT registration lands in Phase 6.
- **Tier calibration.** The `lower_bound_95` value is recorded as **uncalibrated**; Phase 13 (production ADR-0015) calibrates against historical PR outcomes. The wording is locked literal.
- **`PromotionGate.evaluate(...)` invocation.** S4-04 wired the gate; this story does NOT invoke it (it can; the `--with-verdict` flag triggers it via S4-02 AC-8). The evaluation is a separate story-level concern; the *evidence* is what this story records.
- **Audit chain integration test (3 consecutive runs).** S7-02 owns that. This story only asserts one run extends the chain by 1 record AND `prev_hash == prior_tip` at the story-test boundary.
- **Subprocess-CLI shape coverage.** Deliberately deferred to the nightly canary (real SUT) + S6-03 (distroless E2E). In-process `CliRunner` covers the same code paths minus the `sys.argv` parse + fresh-`sys.modules` boundary. Adding `--sut-module=<dotted>` to S4-02's `eval run` would re-enable subprocess testing; that is a candidate Phase-7 extension if `phase-arch-design.md §Performance regression tests` adds a "cold-start under subprocess" budget.
- **`held-out-cve-exclusion-manifest.yaml` schema validation.** Owned by S5-04 / a future Phase-4 amendment. This story's `digests.yaml`-shape AC filters cases by `(p / "case.toml").is_file()` so the manifest is naturally skipped.
- **Cross-task-class `digests.yaml` extraction.** The pattern this story makes Open/Closed for the *scripts* (AC-SCRIPT-OPENCLOSED). The `digests.yaml` file itself is per-bench; no cross-bench manifest exists.

## Notes for the implementer

- **Two cold-cache budgets, two contracts.**
  - **AC-3a CI integration test** (stub SUT, in-process `CliRunner`): ≤ 90 s. Hard fail on regression — a harness regression.
  - **AC-3b nightly canary** (real SUT, subprocess): ≤ 15 min cold-cache (20% headroom over the `phase-arch-design.md §Performance regression tests` 12-min target). First nightly run establishes baseline. Failing the canary is a flag — surfacing a flame-graph artifact — not a CI block, until Phase 6 ships the SUT and we have a stable baseline to defend.
- **Order of operations matters.** Sign `digests.yaml` **after** S5-03 + S5-04 have stabilized case content. If a case's `input/` is edited after signing, the loader raises `BenchCaseDigestMismatch` (exit 6). Coordinate; re-run `scripts/sign_bench_digests.py --task-class=vuln-remediation` after any case-content edit.
- **`lower_bound_95` will drift across stub-SUT runs** because the BCa bootstrap has small-sample noise (N=10) even with a deterministic seed (the `int(run_id[:8], 16)` derivation depends on `run_id`, which differs per run). Pick the **median of 3** manual runs as the README value; AC-6a allows ±0.05 jitter against any single subsequent run. Do not refresh the README every PR — refresh only after a substantive stub-SUT change.
- **`isolation_class="subprocess"`** is the structural value Phase 6.5 ships. The promotion gate (S4-04) refuses to mix `isolation_class` populations once Phase 16 flips the field. ADR-0010 §Decision makes this load-bearing; AC-4 asserts it on every emitted report.
- **Stub-SUT contract surface (F-DP-3).** `tests/fixtures/sut/deterministic_vuln_sut.py` is the second concrete `SystemUnderTest` after Phase 4's stub (Phase 6's real `VulnRemediationSut` will be the third). The Protocol is pinned by S4-02 AC-3 — `Callable[[BenchCase], Awaitable[Mapping[str, Any]]]`. mypy --strict over the test confirms structural conformance; no Protocol class is extracted yet (Rule 2 — two consumers).
- **`compute_case_dir_digest` promotion is THIS story's job (F-DP-1).** The third consumer (this story's integration test) is the trigger. The loader's private name forwards via a one-line alias so all prior import sites keep working (Rule 11). Mypy --strict's `--no-implicit-reexport` requires the `from … import x as x` form in `codegenie.eval.__init__`.
- **README literal disclaimer is verbatim** — see AC-6's exact string. S6-03 (distroless) copies it byte-for-byte under its own README. When the third bench needs the same disclaimer (Phase 8 or beyond), extract `bench/_threshold_disclaimer.md.tmpl` (F-DP-4). Not now.
- **The integration test does NOT use a subprocess.** This is a deliberate scope decision (per F-TQ-2): the spawned `python -m codegenie` cannot reach a test-only stub SUT because the spawned process's `default_sut_registry` is empty. `CliRunner.invoke` covers the same code paths — CLI parsing, `sut_registry.resolve_sut`, `Runner.plan`, `Runner.run_eval` (which still spawns the rubric subprocess internally — ADR-0001 is exercised in vivo), `audit.write_run_record`, JSONL emission, exit-code mapping. The subprocess boundary is exercised by the nightly canary (real SUT) and by S6-03's distroless E2E.
- **`tests/fixtures/sut/conftest.py` isolation** uses a monkeypatch-replacement of `default_sut_registry` with a fresh `SutRegistry()` per test; the stub module is imported (or reimported) after the swap so its module-level `@register_sut(...)` decorates into the fresh registry. If `importlib.reload` proves fragile under pytest-xdist, the alternative is to expose `tests.fixtures.sut.deterministic_vuln_sut.register_in(registry)` and have the conftest call it directly — this gives strict control over which registry the stub registers into, at the cost of moving the registration call out of module-level. Either pattern is acceptable; pick whichever survives a `pytest -n auto` run cleanly.
- **`scripts/verify_bench_digests.py`'s `verify_parity()` function** is the testable unit — the script is a thin CLI shim. Keep the function pure (takes paths, returns a list of human-readable divergence strings, no I/O beyond reading the bench tree) so that S5-06's invalidation suite can call it directly without subprocess overhead.
- **AC-DIG-PROMOTE's separator-sentinel scan** uses the literal escape sequences `b"\x1f"`/`b"\x1e"` — be careful that the AST/import lint doesn't false-positive on string literals in tests that document the algorithm. The check should exclude `tests/cassettes/`, `.venv/`, and any documentation files; if false positives surface, scope the scan to `src/codegenie/`, `scripts/`, and `tests/integration/`/`tests/unit/` only.
- **F-DP-2 deferred extension: `--sut-module=<dotted>` flag.** If a later story needs subprocess-shape E2E coverage against a test SUT, extend `eval run` to accept `--sut-module=<dotted_path>` and `importlib.import_module()` it before `resolve_sut(...)`. The Click option is additive; the import has the same side effect as the conftest reimport pattern. Defer the ADR/story until S7-02 or a Phase-7 entry-point story needs it. Surface in the architect's deferred-decisions list.
