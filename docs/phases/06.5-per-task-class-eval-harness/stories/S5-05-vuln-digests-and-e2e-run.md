# Story S5-05 — vuln-remediation digests.yaml + green E2E run

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** Ready
**Effort:** M
**Depends on:** S5-03 (5 RAG-corpus-derived cases exist) and S5-04 (5 held-out cases exist)
**ADRs honored:** ADR-0002 (`lower_bound_95` is the recorded promotion-evidence candidate, not `mean_score`), ADR-0001 (the rubric subprocess runs the E2E run for all 10 cases), ADR-0010 (`isolation_class="subprocess"` annotated on the emitted `BenchRunReport`)

## Context

The 10 cases exist (5+5), the rubric exists, the harness exists. This story locks the bench by signing every case in `bench/vuln-remediation/cases/digests.yaml` and proves the bench works end-to-end: `codegenie eval run --task-class=vuln-remediation` exits 0 on a CI runner within the cold-cache 12-minute budget, the produced `BenchRunReport` carries a real `lower_bound_95` value, and that value is recorded — with an explicit "uncalibrated" comment — in `bench/vuln-remediation/README.md` as the **candidate** bronze→silver promotion threshold.

ADR-0002 reframes "what gets recorded as evidence" from `mean_score` to `lower_bound_95` (the 1000-resample BCa bootstrap one-sided 95% lower bound). The number is one-sided and conservative; calibration to the actual bronze/silver tier thresholds in `docs/trust-tiers.yaml` is a Phase 13 concern. Phase 6.5 records the *number* and labels it uncalibrated; Phase 7 reads it as input to its own promotion-precondition logic per the roadmap amendment in S7-03.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §`bench/{task-class}/` directory contract` — `cases/digests.yaml` format is `{case-id: blake3:<hex>}`.
  - `../phase-arch-design.md §Control flow` — the full happy-path sequence; `lower_bound_95` is computed at aggregate time with seed `int(run_id[:8], 16)`.
  - `../phase-arch-design.md §Scenarios → Scenario 1: Nightly eval run on vuln-remediation (happy path)` — the contract for what a green E2E run looks like end-to-end.
  - `../phase-arch-design.md §Performance regression tests` — cold-cache ≤ 15 min canary (with headroom), warm ≤ 12 s.
- **Phase ADRs:**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md §Decision` — `lower_bound_95` is the gate's signal; calibration is uncalibrated at Phase 6.5; Phase 13 calibrates.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md §Decision` — every `BenchRunReport` carries `isolation_class="subprocess"`; this story's run records that value.
- **Production ADRs:** `../../../production/adrs/0009-humans-always-merge.md` — the promotion gate is advisory only; this story produces *evidence*, not a decision.
- **Source design:** `../High-level-impl.md §Step 5` "Done criteria" — names the cold/warm budgets and `lower_bound_95` recording.

## Goal

Sign all 10 vuln-remediation cases in `bench/vuln-remediation/cases/digests.yaml`; prove `codegenie eval run --task-class=vuln-remediation` exits 0 on CI within ≤ 12 min cold-cache; record the emitted `lower_bound_95` (with an "uncalibrated" comment) in `bench/vuln-remediation/README.md` as the candidate bronze→silver threshold.

## Acceptance criteria

- [ ] `bench/vuln-remediation/cases/digests.yaml` exists and signs **exactly 10** case directories — keys are case_ids (matching directory names); values are `"blake3:<64-hex>"` strings.
- [ ] Each signed digest equals the BLAKE3 over the case directory contents (same algorithm S5-03/S5-04 used in `case.toml`); a verifier script (`scripts/verify_bench_digests.py` or inline test) confirms parity.
- [ ] `codegenie eval run --task-class=vuln-remediation` on a CI runner with **cold** cache exits 0 in ≤ 12 minutes wall-clock; the integration test `tests/integration/test_eval_end_to_end_vuln.py` exercises this with a stub-deterministic SUT (the real SUT cold-cache budget is the nightly canary; the integration test runs against a deterministic stub for CI-friendliness).
- [ ] The emitted `BenchRunReport` has: `task_class="vuln-remediation"`, `len(per_case)==10`, `mean_score ∈ [0, 1]`, `score_stddev >= 0`, `lower_bound_95 ∈ [0, mean_score]`, `passed_count <= 10`, `total_cost_usd >= 0`, `block_severity_failure_modes` is a (possibly empty) tuple of declared codes, `prev_hash`/`chain_head` populated by the audit chain, **and** `isolation_class="subprocess"` (ADR-0010).
- [ ] The audit chain has one additional record after the run; `codegenie eval verify` returns exit 0; the new chain head matches the run's `chain_head`.
- [ ] `bench/vuln-remediation/README.md` contains a "Candidate bronze→silver threshold" section recording the run's `lower_bound_95` value, with the literal text `**Uncalibrated** — calibration deferred to Phase 13 per ADR-0003 / production ADR-0015. Phase 7 reads this as candidate input only.` (or equivalent wording naming the ADRs).
- [ ] Whitespace-only edit to any signed `case.toml`/`input/`/`expected/` file makes the next `codegenie eval run` raise `BenchCaseDigestMismatch` with exit 6 (this is the loader contract from S2-02; S5-06 has the focused invalidation test, but this AC asserts it works end-to-end here too — a 1-line sanity check).
- [ ] Red test from §TDD plan (`tests/integration/test_eval_end_to_end_vuln.py`) exists, was committed at red, now green; `ruff check`, `ruff format --check`, `pytest tests/integration/test_eval_end_to_end_vuln.py -v` all pass; CI nightly canary green (or annotated "first run, baseline established").

## Implementation outline

1. Write the red test `tests/integration/test_eval_end_to_end_vuln.py` first — see §TDD plan.
2. Compute BLAKE3 digests for all 10 case directories:
   ```python
   from codegenie.eval.loader import compute_case_digest  # or whatever S2-02 named it
   import yaml, pathlib
   cases_root = pathlib.Path("bench/vuln-remediation/cases")
   digests = {p.name: compute_case_digest(p) for p in sorted(cases_root.iterdir()) if p.is_dir()}
   (cases_root / "digests.yaml").write_text(yaml.safe_dump(digests, sort_keys=True))
   ```
3. Verify parity: each `case.toml`'s `case_digest` field equals `digests.yaml[case_id]`. If they diverge, freeze case content and re-sign (do not edit `case.toml` digest by hand).
4. Run `codegenie eval run --task-class=vuln-remediation` against a stub-deterministic SUT under `tests/fixtures/sut/deterministic_vuln_sut.py`. Capture the `BenchRunReport`'s `lower_bound_95`.
5. Update `bench/vuln-remediation/README.md`:
   - Add the "Candidate bronze→silver threshold" section.
   - Record the captured `lower_bound_95` value (~3 sig figs).
   - Include the uncalibrated disclaimer naming ADR-0002 / ADR-0003.
6. Add nightly CI canary: `tests/integration/test_eval_end_to_end_vuln.py` runs as part of the standard test suite; the *full* real-SUT cold-cache run is the nightly canary referenced in `phase-arch-design.md §Performance regression tests`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_eval_end_to_end_vuln.py`

```python
# tests/integration/test_eval_end_to_end_vuln.py
"""End-to-end run of bench/vuln-remediation/ against a deterministic stub SUT.
ADR-0002: lower_bound_95 is the recorded candidate. ADR-0010: isolation_class
is annotated. Cold-cache wall-clock budget enforced (relaxed for CI stub)."""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
RUNS_DIR = REPO_ROOT / ".codegenie" / "eval" / "runs"


@pytest.fixture(autouse=True)
def clean_cache_and_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEGENIE_EVAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("CODEGENIE_EVAL_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("CODEGENIE_EVAL_SUT", "tests.fixtures.sut.deterministic_vuln_sut")
    yield


def _run_eval():
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "codegenie", "eval", "run",
         "--task-class=vuln-remediation", "--format=jsonl"],
        capture_output=True, text=True, cwd=REPO_ROOT, check=False,
    )
    elapsed = time.monotonic() - start
    return result, elapsed


def test_digests_yaml_signs_exactly_ten_cases():
    digests_path = BENCH_ROOT / "vuln-remediation" / "cases" / "digests.yaml"
    assert digests_path.exists()
    sig = yaml.safe_load(digests_path.read_text())
    assert isinstance(sig, dict) and len(sig) == 10
    for case_id, digest in sig.items():
        assert digest.startswith("blake3:") and len(digest) == 71


def test_e2e_run_exits_zero_within_cold_cache_budget():
    result, elapsed = _run_eval()
    assert result.returncode == 0, (
        f"exit={result.returncode}; stderr={result.stderr[-2000:]}"
    )
    # CI integration: 90 s for the stub SUT; the real cold cold-cache budget
    # (≤ 12 min) is the nightly canary, not this synchronous test.
    assert elapsed < 90.0, f"E2E took {elapsed:.1f}s; budget 90s (stub SUT)"


def test_run_emits_ten_per_case_jsonl_lines_plus_aggregate():
    result, _ = _run_eval()
    lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
    per_case = [l for l in lines if l.get("kind") == "case"]
    aggregate = [l for l in lines if l.get("kind") == "aggregate"]
    assert len(per_case) == 10
    assert len(aggregate) == 1


def test_audit_record_carries_lower_bound_95_and_isolation_class_subprocess():
    _run_eval()
    runs = sorted(Path("/tmp").glob("*/runs/*.json"))  # use the tmp_path-set RUNS_DIR
    # Simpler: pick the freshest file in CODEGENIE_EVAL_RUNS_DIR by env contract.
    import os
    runs_dir = Path(os.environ["CODEGENIE_EVAL_RUNS_DIR"])
    audit_files = sorted(runs_dir.glob("*.json"))
    assert audit_files, "no audit record emitted"
    report = json.loads(audit_files[-1].read_text())
    assert report["task_class"] == "vuln-remediation"
    assert len(report["per_case"]) == 10
    assert 0.0 <= report["lower_bound_95"] <= report["mean_score"]
    assert report["isolation_class"] == "subprocess"  # ADR-0010
    assert report["chain_head"]  # populated by audit.write_run_record


def test_readme_records_candidate_threshold_with_uncalibrated_disclaimer():
    readme = (BENCH_ROOT / "vuln-remediation" / "README.md").read_text()
    assert "Candidate bronze" in readme or "candidate bronze" in readme.lower()
    assert "Uncalibrated" in readme or "uncalibrated" in readme.lower()
    assert "ADR-0002" in readme  # names the lower_bound_95 ADR


def test_whitespace_edit_to_case_invalidates_digest(tmp_path):
    # Touch one signed file; next run must raise BenchCaseDigestMismatch (exit 6).
    from codegenie.eval.loader import load_task_class, load_cases
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    cases = load_cases(tc)
    one = cases[0]
    target = one.input_path / next(iter(p for p in one.input_path.rglob("*") if p.is_file()))
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n")
        result, _ = _run_eval()
        assert result.returncode == 6, f"expected exit 6 (digest mismatch); got {result.returncode}"
    finally:
        target.write_bytes(original)
```

Run it; confirm `digests.yaml` missing or `--task-class=vuln-remediation` not registered or 10-cases-not-present. Commit as red marker.

### Green — smallest impl shape

1. Generate `digests.yaml` via the snippet in §Implementation outline. Commit.
2. Ensure `tests/fixtures/sut/deterministic_vuln_sut.py` exists (a hand-coded stub that returns plausible `harness_output` for each case, allowing the rubric to score deterministically). If S3-* didn't ship this, add it under the bench-author's umbrella with a clear comment.
3. Run the test suite locally; iterate.
4. Capture `lower_bound_95` from the run output, record in README.

### Refactor — clean up

- The candidate threshold section in README.md cites ADR-0002, ADR-0003, and (forward) production ADR-0015 for calibration.
- `scripts/verify_bench_digests.py` (small helper): walks `cases/`, recomputes BLAKE3, diffs against `digests.yaml`; exits 0 on parity, 1 on drift. Documented in the README.
- `bench/vuln-remediation/cases/digests.yaml` header comment: "Generated by `scripts/sign_bench_digests.py`. Do not edit by hand. Re-sign after any case edit."
- The "uncalibrated" wording in README is verbatim consistent across task classes — the same disclaimer should appear in `bench/migration-chainguard-distroless/README.md` after S6-03.
- The integration test's `tests/fixtures/sut/deterministic_vuln_sut.py` is documented in `tests/fixtures/sut/README.md` so the next task class can copy the pattern.

## Files to touch

| Path | Why |
|---|---|
| `bench/vuln-remediation/cases/digests.yaml` | New — signs all 10 case directories |
| `bench/vuln-remediation/README.md` | Extend — "Candidate bronze→silver threshold" section with uncalibrated disclaimer |
| `tests/integration/test_eval_end_to_end_vuln.py` | New — E2E + digest signing + readme assertion + invalidation sanity check |
| `tests/fixtures/sut/deterministic_vuln_sut.py` | New (if not extant) — stub SUT that emits per-case `harness_output` for the rubric |
| `tests/fixtures/sut/README.md` | New (if not extant) — documents the stub-SUT pattern |
| `scripts/sign_bench_digests.py` | New — operator helper to compute + write `digests.yaml` |
| `scripts/verify_bench_digests.py` | New — operator helper to verify digest parity |

## Out of scope

- **Cache hit-rate + invalidation deep tests.** S5-06 owns those — this story has a one-line invalidation sanity check; S5-06 covers warm reruns, partial invalidation, etc.
- **Real-SUT nightly canary tuning.** The CI test uses a stub SUT. The real-SUT 12-min cold-cache budget is the nightly canary; if it regresses, that is a separate flag and a separate fix.
- **Tier calibration.** The `lower_bound_95` value is recorded as uncalibrated; Phase 13 (production ADR-0015) calibrates against historical PR outcomes.
- **`PromotionGate.evaluate(...)` invocation.** S4-04 wired the gate; this story does not invoke it (it can; the `--with-verdict` flag triggers it). The evaluation is a separate story-level concern; the *evidence* is what this story records.
- **Audit chain integration test (3 consecutive runs).** S7-02 owns that integration test; this story only asserts one run extends the chain by 1 record.

## Notes for the implementer

- The cold-cache budget in the AC is ≤ 90 s for the stub SUT, not the ≤ 12 min real-SUT target. Two separate budgets:
  - **CI integration test** (this story's AC): ≤ 90 s, stub SUT. Hard fail on regression — that is a harness regression.
  - **Nightly canary** (separate CI job): ≤ 15 min real-SUT cold-cache (20% headroom over 12 min). Slower regression signal; first run *establishes* the baseline.
- Order of operations matters. Sign `digests.yaml` **after** S5-03 + S5-04 have stabilized case content; if a case's `input/` is edited after signing, the loader will refuse to load it (exit 6). Coordinate.
- The README's `lower_bound_95` value will move slightly across runs because `score_stddev` and `passed_count` shift with stub-SUT noise. Pick the median of 3 runs and label it as such — do not refresh every PR.
- ADR-0010 §Decision: `isolation_class` must be present on the report. If S1-02's `BenchRunReport` doesn't include the field, surface it now — every report from Phase 6.5 forward carries `isolation_class="subprocess"`. Phase 16 microVM upgrade flips the field; the promotion gate (S4-04) refuses to mix populations.
- The stub SUT (`tests/fixtures/sut/deterministic_vuln_sut.py`) is the *contract surface* between the bench and the SUT layer. Its return shape must match what `bench/vuln-remediation/rubric.py`'s `score(case, harness_output)` expects (per S5-02). If the contract isn't documented, document it here in `tests/fixtures/sut/README.md`.
- The E2E test exercises the *real* `codegenie eval run` CLI as a subprocess (`subprocess.run([sys.executable, "-m", "codegenie", "eval", "run", ...])`). This is intentional — it covers the CLI wiring, the loader, the runner, the subprocess rubric, the audit chain, and the JSONL emission in a single test. Yes, it is slow; yes, it is the right test.
- If the `lower_bound_95` value comes back near 0 because the stub SUT returns a mix of passing/failing per-case outputs that produce wide CI, tune the stub to produce plausible-but-deterministic outputs. Do **not** tune the rubric or the bootstrap to make the number look nicer — those are downstream artifacts.
