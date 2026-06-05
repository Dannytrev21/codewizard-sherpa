# Validation report — S5-05 vuln-remediation digests.yaml + green E2E run

Validated: 2026-06-05
Verdict: **HARDENED**
Story file: `docs/phases/06.5-per-task-class-eval-harness/stories/S5-05-vuln-digests-and-e2e-run.md`

## Summary

Twenty-three findings: **8 BLOCK**, **9 HARDEN**, **6 surfaced (5 promoted to AC, 1 to Notes).**

No `NEEDS RESEARCH` items — every pattern is precedented in this repo's HARDENED siblings:
- S5-03 / S5-04 F-DP-1 explicitly named THIS story as the third consumer of `_compute_case_dir_digest` and the rule-of-three trigger to promote it to `codegenie.eval.digests.compute_case_dir_digest`.
- S4-02 HARDENED pins the CLI's flag shape (`--out`, `--bench-root`, `--cache-dir`, no env vars), the `sut_registry` resolution seam, and the JSONL `{kind:"case"} + {kind:"aggregate"}` aggregate shape including `chain_head`/`isolation_class`/`complete`.
- S4-01 HARDENED pins exit code `EXIT_DIGEST_MISMATCH=6` and the `_EXIT_CODE_TABLE` mapping that makes `BenchCaseDigestMismatch → 6` automatic.
- S2-04 HARDENED pins `f"{utc_iso}-{secrets.token_hex(4)}.json"` and the `prev_hash`/`chain_head` invariants.
- S5-02 HARDENED pins the rubric-reads-`harness_output`-only contract — load-bearing for AC-SUT-CONTRACT.

## Conflict-resolution priority (Consistency > Coverage > Test-Quality > Design-Patterns)

Two near-conflicts surfaced; both resolved Consistency-first:

1. **Coverage** suggested adding an AC for the in-vivo subprocess-CLI path; **Consistency** found that S4-02's CLI cannot reach a test-only SUT through a subprocess (the spawned process has an empty `default_sut_registry`). Consistency wins → integration test runs in-process via `CliRunner`; subprocess-shape coverage is deferred to the nightly canary (real SUT) and S6-03 (distroless E2E). The deferred `--sut-module=<dotted>` extension is surfaced in Notes as a Phase-7+ story candidate (F-DP-2).
2. **Coverage** wanted a single-source for `digests.yaml` verification (either script OR test); **Test-Quality** wanted both — the script as the operator gate, the test as the CI gate. Both go through the public `compute_case_dir_digest`; the redundancy is defense-in-depth, not duplication. Both kept.

## Findings

### Consistency critic (7)

- **F-CON-1 (BLOCK) — env-var fixture (`CODEGENIE_EVAL_CACHE_DIR/RUNS_DIR/SUT`) is not an S4-02 contract.** The original TDD plan monkeypatched three environment variables to control cache dir, runs dir, and SUT module. None of these are sanctioned by S4-02 HARDENED — the CLI takes `--out`, `--bench-root`, `--cache-dir`, `--no-cache` flags and resolves the SUT via `codegenie.eval.sut_registry.resolve_sut(name)` against the in-process `default_sut_registry`. The test would have failed at every assertion: `subprocess.run([..., "-m", "codegenie", ...])` ignores `CODEGENIE_EVAL_RUNS_DIR`, the runs would land in `.codegenie/eval/runs/` (the S4-02 default), and there is no `CODEGENIE_EVAL_SUT` import-on-startup mechanism. **Resolution:** replaced the fixture with `tmp_path`-derived flag overrides passed to `CliRunner.invoke(eval_group, ["run", "--out", str(tmp_runs), "--bench-root", str(BENCH_ROOT), "--cache-dir", str(tmp_cache), ...])`. SUT registration happens via the autouse conftest at `tests/fixtures/sut/conftest.py`, which monkeypatches `default_sut_registry` and imports the deterministic stub.

- **F-CON-2 (BLOCK) — `from codegenie.eval.loader import compute_case_digest` doesn't exist.** S2-02 ships `_compute_case_dir_digest` (private; underscore-prefixed). S5-03 HARDENED's F-DP-1 surfaced this as a rule-of-three: this story IS the third consumer (`scripts/sign_bench_digests.py` + `scripts/verify_bench_digests.py` + the integration test all need it). **Resolution:** promote `_compute_case_dir_digest` to public `codegenie.eval.digests.compute_case_dir_digest` (new module). Loader's private name becomes a one-line forwarder so existing imports keep working (Rule 11). New AC-DIG-PROMOTE pins the promotion and asserts `is`-identity between the public and private names.

- **F-CON-3 (BLOCK) — README disclaimer literal text was ambiguous about ADR identity.** Original AC-6 said `**Uncalibrated** — calibration deferred to Phase 13 per ADR-0003 / production ADR-0015.` Phase ADR-0003 in this phase is the **tier-identifiers** ADR (`Literal["bronze","silver","gold"]`), not threshold calibration. The threshold-calibration ADR is **production ADR-0015**. The §Refactor note simultaneously said "ADR-0002, ADR-0003, and (forward) production ADR-0015" — Three ADRs, two of them ambiguous. **Resolution:** pinned the literal text to `**Uncalibrated** — calibration deferred to Phase 13 per ADR-0002 (statistic) and production ADR-0015 (threshold calibration). Phase 7 reads this as candidate input only.` The integration test asserts `EXPECTED_DISCLAIMER in readme_text` against the literal constant (mutation-resistant: any drift in the wording fails).

- **F-CON-4 (HARDEN) — `Depends on:` line incomplete.** Original named only S5-03 and S5-04. The story exercises six other HARDENED stories' contracts at runtime: S4-02 HARDENED (CLI flags + sut_registry seam + JSONL shape), S4-01 HARDENED (exit code 6), S4-03 HARDENED (`eval verify` exit 0), S2-02 HARDENED (loader + canonical digest algorithm), S2-04 HARDENED (chain extension), S1-02 HARDENED (`BenchRunReport` field shapes), S5-01 HARDENED (registration), S5-02 HARDENED (rubric-reads-`harness_output`). Mirror S5-04 F-CON-7's quality bar. **Resolution:** rewrote `Depends on:` to enumerate all ten predecessors with HARDENED contract markers and per-citation rationales naming the specific AC pin.

- **F-CON-5 (HARDEN) — `ADRs honored` line incomplete.** Original named ADR-0002, ADR-0001, ADR-0010. Missing: ADR-0003 (tier identifiers — the literal "bronze→silver" tokens come from this ADR), Phase 0 ADR-0001 (BLAKE3 chokepoint — the new `codegenie.eval.digests` module routes through the policed runtime closure), production ADR-0009 (humans always merge — the rationale for the no-`--with-verdict` scope decision), production ADR-0015 (the calibration-deferred ADR named in the README disclaimer). **Resolution:** expanded with per-ADR rationale.

- **F-CON-6 (HARDEN) — exit-code citation missing from `BenchCaseDigestMismatch` AC.** Original AC said "exit 6 (this is the loader contract from S2-02)" — but exit-code 6 is owned by **S4-01 AC-2** (`EXIT_DIGEST_MISMATCH=6`) and AC-3's `_EXIT_CODE_TABLE` mapping. The loader raises `BenchCaseDigestMismatch`; the *CLI* maps it to exit 6. **Resolution:** AC-7's diagnostic explicitly cites `S4-01 AC-2` and pins `EXIT_DIGEST_MISMATCH=6` by constant name.

- **F-CON-7 (BLOCK) — cold-cache budget contradiction (12-min in AC, 90s in test).** AC-3 said "≤ 12 minutes wall-clock" — but the test asserted `elapsed < 90.0`. The Notes section reconciled (stub vs real SUT), but the AC text didn't. A reader would not know which test the 12-min budget binds. **Resolution:** split into AC-3a (stub-SUT CI integration test ≤ 90 s, hard fail) and AC-3b (nightly canary ≤ 15 min real-SUT, baseline-establishment). AC-3b's enforcement is a workflow-file existence test + the comment in the workflow naming Phase 6 as the SUT dependency; the actual budget binds once Phase 6 ships.

### Coverage critic (6)

- **F-COV-1 (HARDEN) — verifier-script-OR-inline-test OR-clause weakens the gate.** AC-2's "(scripts/verify_bench_digests.py OR inline test)" leaves both partially-satisfied as compliant. **Resolution:** Both — the inline test goes through the public `compute_case_dir_digest` and asserts 3-way consistency per case; the script provides the operator-time gate. Different gates at different times.

- **F-COV-2 (HARDEN) — `scripts/sign_bench_digests.py` had no idempotence AC.** Without idempotence, a curator running the script twice could ship inconsistent digests if any non-determinism slipped in (e.g., dict iteration order — though Python 3.7+ guarantees insertion order, the `safe_dump(..., sort_keys=True)` discipline is the actual guarantee). **Resolution:** new AC-SIGN-IDEMP asserts byte-identical output across two consecutive runs.

- **F-COV-3 (HARDEN) — README "Candidate threshold" value-presence test was mutation-thin.** Original test asserted "Candidate bronze" + "Uncalibrated" + "ADR-0002" appear — but a curator hand-writing `Candidate bronze→silver threshold: TBD. Uncalibrated. ADR-0002.` would pass with no actual numeric value recorded. **Resolution:** AC-6 + AC-6a pin (a) the numeric value parseable by `re.search(r"\b(0\.\d{2,4})\b", paragraph)` and (b) the value within ±0.05 of the just-run's aggregate `lower_bound_95`. Drift > 0.05 surfaces a stale README value.

- **F-COV-4 (HARDEN) — `complete is True` invariant missing.** S4-02 AC-10 pins `agg["complete"] is True` on the happy path; the cost-cap path produces `complete=False` and exit 2. The story's AC-4 did not assert `complete`. A regression in the cost-cap accounting could produce a partial report with `complete=False` and exit 0 — wrong on both axes. **Resolution:** folded into AC-4.

- **F-COV-5 (HARDEN) — `codegenie eval verify` exit-0 was English-only in AC-5.** A non-asserted English line in an AC is not a CI gate. **Resolution:** promoted to AC-VERIFY-EXIT0 with a concrete `CliRunner.invoke(eval_group, ["verify", "--out", str(tmp_runs)])` assertion. The verify subcommand's chain-head should match the run's aggregate `chain_head` — a regression where writer + verifier disagree on the chain surfaces here.

- **F-COV-6 (HARDEN) — `tests/fixtures/sut/deterministic_vuln_sut.py`'s output contract was undocumented.** The stub's `harness_output` shape must match what `bench/vuln-remediation/rubric.py`'s `score(case, harness_output)` reads (per S5-02 HARDENED). If the rubric reads a new field that the stub doesn't emit, the integration test surfaces it as a downstream failure with an opaque diagnostic. **Resolution:** AC-SUT-CONTRACT asserts directly that `score(case, stub_sut(case))` returns a valid `BenchScore` for each of the 10 cases — a story-test-boundary diagnostic that names the offending case_id before the integration test fires.

### Test Quality critic (7)

- **F-TQ-1 (BLOCK) — env-var fixture would never green.** See F-CON-1; resolution shared.

- **F-TQ-2 (BLOCK) — subprocess-spawn cannot reach a test-only stub SUT.** The original test did `subprocess.run([sys.executable, "-m", "codegenie", "eval", "run", ...])`. The spawned process imports `default_sut_registry` empty (no autouse conftest in the spawned process); `resolve_sut("vuln-remediation")` raises `TaskClassNotFound` → exit 3. Two repair paths: (a) add `--sut-module=<dotted>` to S4-02 (extends S4-02; needs ADR amendment); (b) replace `subprocess.run` with `CliRunner.invoke` (in-process; the autouse conftest populates the registry). Option (b) is less invasive and covers the same code paths minus the `sys.argv` parse + fresh-`sys.modules` boundary. **Resolution:** Option (b). Subprocess-shape coverage is the nightly canary's job (real SUT) and S6-03's job (distroless E2E). Option (a) is surfaced in Notes as a Phase-7+ extension candidate.

- **F-TQ-3 (BLOCK) — whitespace-mutation test mutated the real working tree.** The original `test_whitespace_edit_to_case_invalidates_digest` did `target.write_bytes(original + b"\n")` against `bench/vuln-remediation/cases/<case>/input/...`. Under pytest-xdist, parallel test workers would race on the same file; if the test crashes between the mutation and the `finally` restore, the tree is dirty; CI bisection over a dirty tree is undefined. **Resolution:** the test now copies `bench/` to `tmp_path / "bench"` via `shutil.copytree`, mutates the copy, invokes `CliRunner.invoke(eval_group, ["run", ..., "--bench-root", str(tmp_bench)])`. The real tree is untouched; the test is parallel-safe.

- **F-TQ-4 (HARDEN) — digest format-only check was mutation-weak.** Original `digest.startswith("blake3:") and len(digest) == 71` accepts `"blake3:" + "0" * 64` as valid format — but the digest is a hand-fabricated lie. Mirror S5-03 AC-3 / S5-04 AC-3's HARDENED pattern: regex full-match + byte-equality to recomputed canonical. **Resolution:** AC-1 + AC-2 use `re.fullmatch(r"^blake3:[0-9a-f]{64}$", v)` AND `compute_case_dir_digest(case_dir) == digests.yaml[case_id]`. Mutation-resistant.

- **F-TQ-5 (HARDEN) — `block_severity_failure_modes` JSON-form vs Python-tuple form unclear.** AC-4 said "(possibly empty) tuple of declared codes" — but after JSON round-trip, Python tuples become lists. The aggregate-line read via `json.loads(...)` returns a list, not a tuple. The story's test would pass either way (Python `for code in agg["block_severity_failure_modes"]` works on both), but the post-load type assertion would surprise. Also: "declared codes" was unspecified — declared where, with what severity filter? **Resolution:** AC-4 pins the JSONL form as `list`, derives the allowed set from `failure_modes.yaml` filtered by `severity == "block"`, and asserts every element is in that set.

- **F-TQ-6 (HARDEN) — stub-SUT distribution unconstrained.** A stub returning all-`harness_output={"validator": {...passing...}}` collapses `mean_score` to 1.0, `score_stddev` to 0.0, and `lower_bound_95` to 1.0 (BCa bootstrap with zero variance has degenerate CI). The recorded candidate threshold would be "1.0 — uncalibrated", which is uninformative; worse, it would mask any rubric regression that should have triggered a per-case failure mode. **Resolution:** AC-STUB-DIST pins `0 < mean_score < 1`, `score_stddev > 0`, `lower_bound_95 < mean_score` (strict), ≥1 case scoring 0.0 (block-severity triggered), ≥1 case scoring 1.0 (clean pass). The BCa bootstrap is meaningfully exercised.

- **F-TQ-7 (HARDEN) — `prev_hash == prior_tip` invariant unasserted.** S2-04 AC-3a is the contract; defense-in-depth at the story-test boundary surfaces a regression where the writer stamps the wrong prior tip. **Resolution:** AC-CHAIN-EXTEND captures the prior tip pre-run and asserts equality post-run.

### Design Patterns critic (4 promoted to AC + 2 surfaced)

- **F-DP-1 (PROMOTED to AC) — `compute_case_dir_digest` rule-of-three promotion.** S5-03 / S5-04 F-DP-1 explicitly named this story as the trigger condition. S5-05 ships **three new consumers** of the helper (`scripts/sign_bench_digests.py`, `scripts/verify_bench_digests.py`, the integration test). Promoting the helper here is structural; deferring it would force four call sites to import a private name through `loader.py`, which (Rule 11 + Rule 7) the codebase's discipline doesn't allow. **Resolution:** AC-DIG-PROMOTE pins (a) the new module `src/codegenie/eval/digests.py`, (b) re-export from `codegenie.eval.__init__`, (c) loader's private name forwards via one-line alias (so all existing imports stay green — Rule 11), (d) `is`-identity test between public and private names, (e) AST/import lint asserts no other file under `src/codegenie/`, `scripts/`, or `tests/` re-implements the canonical algorithm.

- **F-DP-2 (PROMOTED to AC) — Open/Closed for `sign_bench_digests` + `verify_bench_digests`.** Both scripts must accept `--task-class=<name>` and `--bench-root=<path>`; neither may hard-code `"vuln-remediation"` or any task-class name. S6-03 (distroless) will add the second consumer; Phase 8+ benches add the third onwards. **Resolution:** AC-SCRIPT-OPENCLOSED pins parameterization + asserts (via a synthetic stub task class under `tmp_path`) that adding a new task class requires zero edits to either script.

- **F-DP-3 (PROMOTED to AC) — autouse conftest as the SUT-registration seam.** The deterministic stub registers into `default_sut_registry` at module import time; the conftest monkeypatches the default registry to a fresh `SutRegistry()` and imports/reimports the stub module each test. This is the **only** clean way to run end-to-end through `CliRunner` without leaking SUT registrations across tests (and across stories — S6-03 will register its own stub for distroless). **Resolution:** AC-CONFTEST-REGISTRATION pins the conftest's location, the autouse fixture's monkeypatch shape, and the post-run `resolve_sut(...)` assertion.

- **F-DP-4 (PROMOTED to AC) — `tests/fixtures/sut/README.md` documents the stub-SUT contract surface.** Once the README exists, S6-03 copies the pattern verbatim for `tests/fixtures/sut/deterministic_distroless_sut.py`. The pattern then naturally extracts at the third consumer (Phase 8 or beyond) into a shared `tests/fixtures/sut/_base.py` if Rule 2's threshold is crossed. **Resolution:** AC-SUT-CONTRACT requires the README to document the `harness_output` shape contract between the stub SUT and the rubric (per S5-02 HARDENED — rubric reads `harness_output` only).

- **F-DP-5 (surfaced) — `SystemUnderTest` Protocol structural conformance.** mypy --strict over the test confirms the stub satisfies S4-02 AC-3's `Callable[[BenchCase], Awaitable[Mapping[str, Any]]]` shape. Not promoted; mypy is the gate.

- **F-DP-6 (surfaced) — README candidate-threshold paragraph is a per-task-class Strategy template.** S6-03 will copy it verbatim. When the third bench needs the same shape (Phase 8+), extract `bench/_threshold_disclaimer.md.tmpl` and source it. NOT this story's job (Rule 2 — two consumers). Surfaced in Notes.

### Surfaced — endorsements (no edit)

- **Functional-core / imperative-shell.** `compute_case_dir_digest` is pure; the operator scripts are imperative shell; the integration test orchestrates both. The pattern is sound. Endorsed.
- **CliRunner.invoke for in-process integration.** Click's testing harness covers the same exit-code path, JSONL emission, and `ctx.obj["format"]` propagation as a real subprocess; the only differences are `sys.argv` parsing (Click does it either way) and a fresh `sys.modules` (which would defeat SUT registration here). Endorsed as the right test surface for this story.
- **`isolation_class="subprocess"` as a structural field even when monotone.** Phase 6.5 emits a field with only one valid value today, but ADR-0010 makes the field load-bearing for the Phase 16 transition. Asserting it on every report is structural foresight at near-zero cost. Endorsed.

## Edits applied

- **Status** updated to `HARDENED (phase-story-validator, 2026-06-05)`.
- **Depends on** rewritten from S5-03 + S5-04 to a ten-story dependency chain (S5-03, S5-04, S4-02, S4-01, S4-03, S4-05, S2-02, S2-04, S1-02, S5-01, S5-02) with HARDENED contract markers and per-citation rationales (F-CON-4).
- **ADRs honored** expanded with ADR-0001, ADR-0003, Phase 0 ADR-0001, production ADR-0009, production ADR-0015 + per-ADR rationale (F-CON-5).
- **Validation notes** block appended under the header documenting every change.
- **Context** rewritten to surface the two-budget contract (stub vs canary), the F-DP-1 promotion, the CliRunner-vs-subprocess scope decision.
- **References — where to look** expanded with: full S5-03 / S5-04 / S5-02 / S5-01 / S4-02 / S4-01 / S4-03 / S2-02 / S2-04 / S1-02 citations naming the specific AC pins this story consumes, plus phase ADR-0001 and ADR-0003, plus production ADR-0009 and ADR-0015.
- **Goal** rewritten to name the two budgets, the F-DP-1 promotion, the operator scripts' Open/Closed contract.
- **Acceptance criteria** restructured from 8 prose-only bullets to 14 named ACs (AC-1 through AC-LINT-RED-GREEN) with concrete machine-checkable predicates. Mirrors S5-03 HARDENED / S5-04 HARDENED structure.
- **Implementation outline** rewritten from a 6-step sketch to a 10-step plan with concrete code skeletons for `src/codegenie/eval/digests.py`, `scripts/sign_bench_digests.py`, `scripts/verify_bench_digests.py`, and the autouse conftest fixture.
- **TDD plan** rewritten — old 6-test sketch replaced with 13 named tests under `tests/integration/eval/test_eval_end_to_end_vuln.py`. Every test cites its AC; every test runs in-process via `CliRunner`; no subprocess invocations except for the operator-script idempotence + Open/Closed tests (which exercise the scripts as standalone processes — orthogonal to the CLI subprocess concern).
- **Files to touch** expanded from 7 to 13 paths covering the F-DP-1 promotion, the autouse conftest, the unit test for the digests module, the nightly canary workflow stub.
- **Out of scope** expanded with: subprocess-CLI shape (deferred to canary + S6-03), `held-out-cve-exclusion-manifest.yaml` schema validation (owned by S5-04), cross-task-class `digests.yaml` extraction (no current trigger).
- **Notes for the implementer** rewritten to surface: the two-budget contract, the median-of-3 jitter rationale, the F-DP-1 promotion mechanics, the CliRunner-vs-subprocess scope decision with its deferred `--sut-module=<dotted>` extension, the conftest isolation pattern and its `importlib.reload`-vs-`register_in(...)` alternatives, the AC-DIG-PROMOTE separator-sentinel scan scope, the F-DP-4 future-extraction trigger condition.

## Verdict

**HARDENED.** The story now (a) traces every acceptance criterion to a HARDENED sibling-story contract or phase ADR, (b) ships the F-DP-1 rule-of-three promotion the sibling stories explicitly named it for, (c) replaces the unimplementable env-var fixture with the S4-02-sanctioned flag-and-`CliRunner` mechanism, (d) replaces the parallel-unsafe real-tree mutation test with a tmp_path-isolated copy, (e) splits the cold-cache budget into stub-SUT (CI integration test) and real-SUT (nightly canary) contracts, and (f) surfaces the deferred subprocess-CLI-with-test-SUT extension as a Phase-7+ candidate without blocking this story's red-green window.
