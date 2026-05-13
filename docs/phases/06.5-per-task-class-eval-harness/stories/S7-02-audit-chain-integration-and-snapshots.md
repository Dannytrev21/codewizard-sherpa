# Story S7-02 — End-to-end audit-chain extension integration + golden snapshots

**Step:** Step 7 — Extend fence-CI; lock in end-to-end audit; ship cross-phase amendments
**Status:** Ready
**Effort:** M
**Depends on:** S5-05 (vuln-remediation E2E run produces real `BenchRunReport`s), S2-04 (audit chain primitives)
**ADRs honored:** ADR-0010 (`isolation_class` on chain), ADR-0002 (`lower_bound_95` is the field everyone reads — its byte-shape is frozen), Phase 0 audit-chain reuse (no reinvention)

## Context

Phase 0 establishes the BLAKE3-chained audit log; S2-04 extends it with `BenchRunReport`. Three consecutive `run_eval` calls should produce a chain of length 3 that `audit.verify` walks clean — a single record is not a "chain" worth this name. This story is the end-to-end test of that chain semantic. It also freezes the byte-shape of `BenchRunReport` JSON and `eval_run_audit_record` JSON as golden snapshots, so a downstream phase (Phase 7 consumer, Phase 11 PR provenance reader, Phase 13 ROI dashboard) reads a stable shape. Drift in either snapshot fails the test with a diagnostic pointing at the regen script + the ADR amendment template — the shape is not free to evolve silently.

The genesis-record semantics (`prev_hash == "0"*64`) is the load-bearing detail Phase 0 owns; this story is the *integration* test that those semantics hold across the new Phase 6.5 audit type.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design → src/codegenie/eval/audit.py"` — `write_run_record`, `verify`, genesis semantics.
  - `../phase-arch-design.md §"Testing strategy → Integration → test_audit_chain_extension.py"` — three consecutive runs; chain length 3; verify ok.
  - `../phase-arch-design.md §"Golden snapshots — bench_run_report.v1.json, eval_run_audit_record.v1.json"` — what the snapshots capture + drift diagnostic.
  - `../phase-arch-design.md §"Scenarios → Scenario 4"` — chain-walk after a new run produces the next verdict; this story tests the data substrate that scenario rides on.
- **Phase ADRs:**
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — `isolation_class` field default; snapshots must carry `"subprocess"`.
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — `mean_score`, `score_stddev`, `lower_bound_95` are all on the wire; snapshot covers all three.
- **Production ADRs:**
  - Phase 0 audit-chain ADR (whichever ADR documents `chain_append`/`chain_verify`) — this story reuses, not reinvents.
- **Source design:** `../High-level-impl.md §"Step 7" §"Features delivered"` — names both snapshots and the regen script.

## Goal

Land `tests/integration/test_audit_chain_extension.py` that runs three `run_eval` calls and asserts chain length 3 with `audit.verify().ok is True`; freeze `tests/snapshots/bench_run_report.v1.json` and `tests/snapshots/eval_run_audit_record.v1.json` byte-shapes; ship `scripts/regen_eval_snapshot.py` with a drift-diagnostic pointer.

## Acceptance criteria

- [ ] `tests/integration/test_audit_chain_extension.py` runs three `run_eval(...)` calls against the stub bench fixture (`tests/fixtures/bench/stub-task-class/` from S3-01); chain length after run 3 is exactly 3; `audit.verify().ok is True`.
- [ ] The genesis record (run 1) has `prev_hash == "0" * 64`; runs 2 and 3 carry the previous record's `chain_head` as their `prev_hash`.
- [ ] Tampering with run-2's JSON on disk (flip one byte in `mean_score`) causes `audit.verify` to return `ok=False` with the offending file path + expected/computed mismatch.
- [ ] `tests/snapshots/bench_run_report.v1.json` exists; matches a deterministic stub-SUT + stub-rubric + stub-bench `BenchRunReport` byte-for-byte; carries `isolation_class: "subprocess"`, `complete: true`, `mean_score`, `score_stddev`, `lower_bound_95`, `per_case` array, `chain_head`, `block_severity_failure_modes`.
- [ ] `tests/snapshots/eval_run_audit_record.v1.json` exists; matches the audit-record byte-shape (record number, prev_hash, content_hash, payload reference, isolation_class).
- [ ] `scripts/regen_eval_snapshot.py` regenerates both snapshots; running the script produces zero diff against committed snapshots on a fresh checkout; running the integration test after `regen_eval_snapshot.py --tamper-stub` produces a diagnostic naming `tests/snapshots/bench_run_report.v1.json` and pointing at `templates/adr-amendment.md`.
- [ ] Drift diagnostic: when the snapshot doesn't match, the test message reads (roughly) `"snapshot drift in tests/snapshots/bench_run_report.v1.json — shape changed; if intentional, regenerate via scripts/regen_eval_snapshot.py and file an ADR amendment using templates/adr-amendment.md"`.
- [ ] The red test from §TDD plan exists, was committed at red, and is now green.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict` clean; the integration test runs in ≤ 10 s wall-clock on the stub fixture.

## Implementation outline

1. **Integration test** — `test_audit_chain_extension.py` uses `tmp_path` for `.codegenie/eval/runs/`; invokes `Runner.run_eval(...)` three times against the stub bench fixture; asserts on chain length, head linkage, and `verify().ok is True`. Also covers the tamper-detection branch with a per-test `monkeypatch` writing a flipped byte and re-running `audit.verify`.
2. **Snapshot files** — generate once via `regen_eval_snapshot.py` against a deterministic stub SUT (no clocks, no IDs from `uuid.uuid4` — use a deterministic `run_id` derivation seeded from input hashes; mirror S3-05's deterministic-seed pattern).
3. **Regen script** — `scripts/regen_eval_snapshot.py` runs the stub bench, captures the `BenchRunReport` and the audit record, writes both to `tests/snapshots/*.v1.json`. Has a `--tamper-stub` mode that intentionally changes the report shape to verify the drift diagnostic fires.
4. **Snapshot comparison helper** — `tests/integration/_snapshot_helpers.py` reads the committed snapshot and the freshly-emitted report; uses `json.loads + ordered dict` for comparison; on mismatch, raises `AssertionError` with the drift diagnostic.
5. **Determinism scaffolding** — the stub SUT must produce identical bytes on every run. `run_id` derived from input hashes (e.g., `blake3(sut_digest+rubric_digest+...)[:8]`), not from time. Timestamps in the report use a frozen "1970-01-01T00:00:00Z" injected via a `--frozen-time` flag the script controls.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/integration/test_audit_chain_extension.py`

```python
# tests/integration/test_audit_chain_extension.py
import json
from pathlib import Path

import pytest

from codegenie.eval.audit import verify as audit_verify
from codegenie.eval.runner import run_eval

STUB_BENCH = Path(__file__).resolve().parents[2] / "tests/fixtures/bench/stub-task-class"


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path / ".codegenie/eval/runs"


def test_three_run_evals_produce_a_chain_of_length_three(runs_dir):
    for _ in range(3):
        run_eval(task_class_name="stub-task-class", bench_root=STUB_BENCH.parent)
    records = sorted(runs_dir.glob("*.json"))
    assert len(records) == 3
    result = audit_verify(runs_dir)
    assert result.ok is True


def test_genesis_record_has_zero_prev_hash(runs_dir):
    run_eval(task_class_name="stub-task-class", bench_root=STUB_BENCH.parent)
    records = sorted(runs_dir.glob("*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record["prev_hash"] == "0" * 64


def test_run_2_prev_hash_equals_run_1_chain_head(runs_dir):
    run_eval(task_class_name="stub-task-class", bench_root=STUB_BENCH.parent)
    run_eval(task_class_name="stub-task-class", bench_root=STUB_BENCH.parent)
    records = sorted(runs_dir.glob("*.json"))
    r1 = json.loads(records[0].read_text())
    r2 = json.loads(records[1].read_text())
    assert r2["prev_hash"] == r1["chain_head"]


def test_tamper_detected_by_audit_verify(runs_dir):
    for _ in range(3):
        run_eval(task_class_name="stub-task-class", bench_root=STUB_BENCH.parent)
    records = sorted(runs_dir.glob("*.json"))
    # Tamper run 2: flip one byte in mean_score.
    bad = json.loads(records[1].read_text())
    bad["mean_score"] = 0.0 if bad["mean_score"] != 0.0 else 0.999
    records[1].write_text(json.dumps(bad))
    result = audit_verify(runs_dir)
    assert result.ok is False


def test_bench_run_report_snapshot_byte_identical_to_v1():
    from tests.integration._snapshot_helpers import assert_snapshot_byte_identical
    snapshot = Path(__file__).resolve().parents[1] / "snapshots/bench_run_report.v1.json"
    fresh = run_eval(task_class_name="stub-task-class", bench_root=STUB_BENCH.parent, frozen_time="1970-01-01T00:00:00Z")
    assert_snapshot_byte_identical(fresh.model_dump_json(indent=2), snapshot)


def test_eval_run_audit_record_snapshot_byte_identical_to_v1():
    from tests.integration._snapshot_helpers import assert_snapshot_byte_identical
    snapshot = Path(__file__).resolve().parents[1] / "snapshots/eval_run_audit_record.v1.json"
    # ... drive run_eval; read the on-disk record; compare.
```

Run; confirm `ModuleNotFoundError: tests.integration._snapshot_helpers` or `FileNotFoundError: tests/snapshots/bench_run_report.v1.json`. Commit as red marker.

### Green

Write `_snapshot_helpers.py`, `scripts/regen_eval_snapshot.py`. Run the regen script. Commit the two snapshot files. The integration test goes green.

### Refactor

- Confirm `run_id` derivation is fully deterministic from inputs — no `time.time()`, no `uuid.uuid4()`. If the runner currently uses time-based IDs, this story has to either add a frozen-time injection point or surface the work as a runner change.
- The drift diagnostic must point at *both* the regen script and the ADR amendment template — a snapshot change without an ADR is a load-bearing failure mode.
- `mypy --strict` clean on `_snapshot_helpers.py` and `regen_eval_snapshot.py` (the latter is a script; annotate `main() -> None`).
- Verify the snapshot files round-trip cleanly: `BenchRunReport.model_validate(json.loads(snapshot.read_text()))` succeeds.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_audit_chain_extension.py` | New — three-run chain integration + tamper detection + snapshot comparison |
| `tests/integration/_snapshot_helpers.py` | New — `assert_snapshot_byte_identical` + drift diagnostic |
| `tests/snapshots/bench_run_report.v1.json` | New — frozen `BenchRunReport` byte-shape |
| `tests/snapshots/eval_run_audit_record.v1.json` | New — frozen audit-record byte-shape |
| `scripts/regen_eval_snapshot.py` | New — regenerate both snapshots from the stub fixture |
| `templates/adr-amendment.md` | Update if it doesn't exist already — drift diagnostic points here |

## Out of scope

- **Fence-CI assertions** — S7-01.
- **Cross-phase ADR amendments** — S7-03.
- **Auditing reports from real benches (vuln-remediation, distroless)** — the integration test uses the stub fixture for byte-determinism; real-bench audit integration is covered by S5-05 and S6-03 individually.
- **Performance regression of audit-chain extension** — Phase 0's own perf canaries cover this.

## Notes for the implementer

- **Determinism is the load-bearing property.** If the stub-bench `run_eval` produces different bytes across two runs in the same checkout, the snapshot test is meaningless. Find every nondeterministic source — `time`, `uuid`, `os.getpid`, dict ordering pre-3.7, set iteration — and pin or remove. The deterministic seed pattern (S3-05) is the precedent; mirror it for `run_id` derivation.
- **`isolation_class` must appear in the snapshot.** It defaults to `"subprocess"`; if it's missing, ADR-0010's Phase 16 detector is silently absent. The snapshot is the *contract* that the field ships, not just exists in the type.
- **Genesis-record handling** is the subtle bit. Phase 0 chain primitives may not have a documented "first record" path; the genesis convention (`prev_hash == "0" * 64`) is set by S2-04. The integration test must work whether `.codegenie/eval/runs/` exists or not — `audit.write_run_record` should create it. Mirror Phase 0's pattern for "first append to an empty chain."
- **The drift diagnostic is operator-facing.** A future contributor whose innocent change to `BenchRunReport` (adding a field) trips this test must read the diagnostic and *immediately know* that they need to (a) regenerate the snapshot, (b) write an ADR amendment naming the new field. Phrase the message so the path forward is obvious — `Rule 12 Fail loud`.
- **Three runs is the minimum to test chain *semantics*.** One run only tests genesis; two runs tests one link; three runs tests that `verify` walks past genesis, past the first link, to the head. Don't be tempted to test with one run "for speed" — the chain semantics aren't exercised.
- **Tamper detection branch** — flipping `mean_score` is a clear test, but flipping `prev_hash` directly is the more honest test (since `mean_score` flipping invalidates the record's own content hash, not the chain link). Pick one; document the choice; do not test both unless cheap.
- **The snapshot file format is JSON, indent=2, sorted keys.** Pydantic's `model_dump_json(indent=2)` does not sort by default — set `model_config = ConfigDict(json_schema_serialization_defaults_required=True)` won't sort keys either; you may need `json.dumps(model.model_dump(), indent=2, sort_keys=True)`. Pin the serialization shape explicitly so it's stable across Pydantic point releases.
