# Story S7-02 — End-to-end audit-chain extension integration + golden snapshots

**Step:** Step 7 — Extend fence-CI; lock in end-to-end audit; ship cross-phase amendments
**Status:** HARDENED
**Effort:** M
**Depends on:** S2-04 (audit chain primitives — `write_run_record`, `verify`, `VerifyResult`, `GENESIS_PREV_HASH`, `chain_identity`), S3-01 (`Runner().plan(...)` two-call runner contract, `stub_task_class_fixture(tmp_path)` under `tests/helpers/bench.py`), S3-02 (`Runner().execute(...)`, `JitteredStubSUT`, `make_stub_plan(tmp_path)`), S3-06 (`Runner().run_eval(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, ..., out_dir)` composition root that writes the chain), S4-02 (CLI-integration precedent that already had to correct this same runner-API mismatch), S5-05 (real vuln-remediation E2E run — this story uses the *stub* fixture for byte-determinism, S5-05 is only a scheduling dependency).
**ADRs honored:** ADR-0010 (`isolation_class` on `BenchRunReport` — snapshot pins default `"subprocess"`), ADR-0002 (`lower_bound_95` byte-shape is frozen — snapshot carries the field), Phase 0 audit-chain reuse (no reinvention; extends S2-04, does not re-implement `chain_identity` or `write_run_record`).

## Validation notes (added by phase-story-validator on 2026-07-26)

Four block-level Consistency findings and eight harden-level findings were resolved before the executor picks this story up. Summary:

- **F-TQ-1 / F-CON-1 (block) — runner API mismatch.** The original story's TDD plan called `run_eval(task_class_name="stub-task-class", bench_root=STUB_BENCH.parent)` — a 2-arg signature that does not exist. Hardened S3-01/S3-02/S3-06/S4-02 pin `Runner()` as stateless and `run_eval` as a method taking `(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, ..., out_dir) -> BenchRunReport`. **Fix applied:** entire TDD plan rewritten against the hardened two-call contract using `make_stub_plan(tmp_path)` + `JitteredStubSUT.zero()` + a `_default_execute_kwargs(tmp_path)` mirroring S3-02's `_default_kwargs`. `Runner().run_eval(plan, ...)` returns a report with `chain_head` already stamped.
- **F-TQ-2 / F-CON-2 (block) — `frozen_time` kwarg does not exist.** The original snapshot test threaded `frozen_time="1970-01-01T00:00:00Z"` through `run_eval`. S3-01/S3-02 do not accept it; the *only* time-freezing seam is `plan(run_started_iso=...)`. **Fix applied:** snapshot test builds the plan with a frozen `run_started_iso="1970-01-01T00:00:00+00:00"` and passes the resulting plan to `run_eval`.
- **F-TQ-3 (block) — nonexistent fixture path.** `STUB_BENCH = tests/fixtures/bench/stub-task-class` was cited as "from S3-01", but S3-01 ships `stub_task_class_fixture(tmp_path)` as a *runtime helper* under `tests/helpers/bench.py` — there is no persistent tree at `tests/fixtures/bench/`. **Fix applied:** all references replaced with the `stub_task_class_fixture(tmp_path)` + `make_stub_plan(tmp_path)` helpers.
- **F-DP-5 (harden, structural) — canonical serializer as production chokepoint.** The original story canonicalized snapshots via inline `model_dump_json(indent=2)` in a test-local helper. Pydantic's `model_dump_json` does not sort keys — a Pydantic point release would silently drift the snapshot. **Fix applied:** new AC-11a lands `codegenie.eval.snapshots.canonical_json(model) -> str` as the production chokepoint; `tests/helpers/snapshots.py` + `scripts/regen_eval_snapshot.py` consume it; a fence rejects any `model_dump_json` on a wire type outside this chokepoint.
- Other hardenings: `isolation_class` value asserted independently (F-COV-1); runs-dir creation-on-first-write covered (F-COV-2); three consecutive frozen-time runs get three distinct `run_started_iso` values (F-COV-3); tamper target pinned to `prev_hash` per Notes-for-implementer #5 (F-COV-4); pre-tamper baseline asserted (F-COV-5); two-snapshot ambiguity clarified — `bench_run_report.v1.json` = value + shape, `eval_run_audit_record.v1.json` = schema fixture only (F-COV-6); `content_hash` and `chain_head` regex-verified (F-COV-7); chain-link oracle recomputes `chain_identity` independently rather than trusting on-disk `chain_head` (F-TQ-4); canonicalization pinned via `json.dumps(..., sort_keys=True, separators=(",", ": "))` (F-TQ-5); tamper-detection assertion is specific about `VerifyResult.reason` (F-TQ-6); regen script determinism property (F-TQ-7); `--tamper-stub` renamed `dry-run-tamper` subcommand and forbidden from touching `tests/snapshots/` (F-TQ-8); `audit.verify` import corrected (F-CON-3); snapshot versioning rule documented (F-CON-4); `templates/adr-amendment.md` creation-if-missing scoped (F-CON-5); `tests/helpers/snapshots.py` per Rule 11 (F-DP-1); regen script split into two click subcommands (F-DP-2).

## Context

Phase 0 establishes the BLAKE3-chained audit log; hardened S2-04 extends it with `BenchRunReport`. Three consecutive `Runner().run_eval(...)` calls should produce a chain of length 3 that `audit.verify` walks clean — a single record is not a "chain" worth this name. This story is the end-to-end test of that chain semantic. It also freezes the byte-shape of a `BenchRunReport` JSON as a golden snapshot, so a downstream phase (Phase 7 consumer, Phase 11 PR provenance reader, Phase 13 ROI dashboard) reads a stable shape. Drift fails the test with a diagnostic pointing at the regen script + the ADR amendment template — the shape is not free to evolve silently.

The report-IS-the-record design (S2-04) means the on-disk `.codegenie/eval/runs/<utc-iso>-<short>.json` file IS the audit record — there is no separate "audit record wrapper" file. The two snapshot files in this story detect drift at different granularities: `bench_run_report.v1.json` byte-freezes the full report for a stub run (value + shape); `eval_run_audit_record.v1.json` is a JSON Schema fixture (property names + types) that can survive a value-only drift and only fails when the record's *shape* changes.

The genesis-record semantics (`prev_hash == GENESIS_PREV_HASH`) is the load-bearing detail Phase 0 / S2-04 own; this story is the *integration* test that those semantics hold across three real `run_eval` invocations.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design → src/codegenie/eval/audit.py"` — `write_run_record`, `verify`, genesis semantics.
  - `../phase-arch-design.md §"Testing strategy → Integration → test_audit_chain_extension.py"` — three consecutive runs; chain length 3; verify ok.
  - `../phase-arch-design.md §"Golden files"` — the two snapshot files + drift diagnostic + regen script.
  - `../phase-arch-design.md §"Scenarios → Scenario 4"` — chain-walk after a new run produces the next verdict; this story tests the data substrate that scenario rides on.
- **Phase ADRs:**
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — `isolation_class` field default; snapshots must carry `"subprocess"`.
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — `mean_score`, `score_stddev`, `lower_bound_95` are all on the wire; snapshot covers all three.
- **Sibling stories (HARDENED, source-of-truth on API shape):**
  - `S2-04-audit-chain-extension.md` — `verify(out_dir: Path, since: str | None = None) -> VerifyResult`, `VerifyResult(ok, verified_complete, verified_incomplete, tampered_path, reason)`, `GENESIS_PREV_HASH`, `chain_identity`.
  - `S3-01-runner-plan-phase.md` — `Runner().plan(task_class_name, *, sut_digest_fn, bench_root, out_dir, run_started_iso, cassette_root, harness_version, registry=None)`; `stub_task_class_fixture(tmp_path)` under `tests/helpers/bench.py`.
  - `S3-02-asyncio-fan-out-and-aggregator.md` — `Runner().execute(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency=None, on_score=None)`; `JitteredStubSUT.zero()`; `make_stub_plan(tmp_path)`.
  - `S3-06-cost-cap-and-partial-reports.md` — `Runner().run_eval(plan, *, ..., out_dir)` composition root; unconditional audit write; report returned with `chain_head` stamped.
  - `S3-05-deterministic-bca-bootstrap.md` — snapshot + `scripts/regen_bootstrap_snapshot.py` precedent for the regen ergonomic + ADR-amendment discipline.
  - `S4-02-eval-run-subcommand.md` F-CON-2 — the *identical* runner-API mismatch that was corrected during S4-02 validation; the pattern is well-established.

## Goal

Land `tests/integration/test_audit_chain_extension.py` that runs three `Runner().run_eval(...)` calls against `stub_task_class_fixture(tmp_path)` and asserts chain length 3 with `audit.verify(...).ok is True`; freeze `tests/snapshots/bench_run_report.v1.json` (full byte snapshot) and `tests/snapshots/eval_run_audit_record.v1.json` (JSON Schema fixture); land `codegenie.eval.snapshots.canonical_json` as the production canonicalizer chokepoint; ship `scripts/regen_eval_snapshot.py` with `regenerate` and `dry-run-tamper` subcommands; write a fence that forbids `model_dump_json` on wire types outside the chokepoint.

## Acceptance criteria

- [ ] **AC-1.** `tests/integration/test_audit_chain_extension.py::test_three_run_evals_produce_a_chain_of_length_three(tmp_path)` uses `stub_task_class_fixture(tmp_path)` + `make_stub_plan(tmp_path)` to build three plans with distinct `run_started_iso` values (`"1970-01-01T00:00:00+00:00"`, `"1970-01-01T00:00:01+00:00"`, `"1970-01-01T00:00:02+00:00"` — F-COV-3), then runs each plan through `asyncio.run(Runner().run_eval(plan, system_under_test=JitteredStubSUT.zero(), out_dir=runs_dir, **_default_execute_kwargs(tmp_path)))` sequentially against the same `runs_dir = tmp_path / ".codegenie/eval/runs"`. After all three calls: `len(tuple(sorted(runs_dir.glob("*.json")))) == 3` AND `audit.verify(runs_dir).ok is True`. Baseline is asserted **before** the tamper test that follows (F-COV-5).

- [ ] **AC-2.** Genesis + chain-link discipline. In the same test file's `test_chain_links_verify_via_oracle(tmp_path)`: after three writes, walk the three sorted records; assert `r1["prev_hash"] == GENESIS_PREV_HASH`; then independently recompute `expected_r2_prev = chain_identity(r1["prev_hash"], content_hash_bytes(canonical_json(BenchRunReport.model_validate(r1).model_copy(update={"chain_head": ""}))))` via `codegenie.hashing.chain_identity` and `codegenie.eval.snapshots.canonical_json` (the oracle path). Assert `r2["prev_hash"] == expected_r2_prev` AND `r3["prev_hash"] == expected_r3_prev` (recomputed the same way). **Do not trust the on-disk `chain_head`** — recompute (F-TQ-4). Mirrors S2-04 AC-6's oracle discipline.

- [ ] **AC-3.** Tamper-detection with specific `VerifyResult` assertions. `test_tamper_on_prev_hash_detected(tmp_path)`: after the three-run baseline (AC-1), flip one byte in run-2's `prev_hash` field on disk (`hex_char = "a" if orig[-1] != "a" else "b"`), re-`json.dumps`, rewrite atomically. Call `result = audit.verify(runs_dir)`. Assert `result.ok is False` AND `result.tampered_path == records[1]` AND `result.reason` starts with either `"prev_hash mismatch"` or `"content_hash mismatch"` (per S2-04 AC-4's `VerifyResult` shape — the exact reason depends on walk order, both are correct detections; the test pins the failure mode is *one of the chain-integrity reasons*, not a parse error or a missing file). (F-COV-4 / F-TQ-6 — target `prev_hash` per Notes-for-implementer #5, not `mean_score`.)

- [ ] **AC-4.** `tests/snapshots/bench_run_report.v1.json` exists; matches the report produced by a **single** `run_eval` on `stub_task_class_fixture(tmp_path)` with `run_started_iso="1970-01-01T00:00:00+00:00"` and `JitteredStubSUT.zero()` — byte-for-byte after `codegenie.eval.snapshots.canonical_json(report)`. Independent oracle assertions (do NOT trust `model_dump`):
  - `parsed = json.loads(snapshot.read_text())`
  - `parsed["isolation_class"] == "subprocess"` (ADR-0010 — F-COV-1)
  - `parsed["complete"] is True`
  - all of `mean_score`, `score_stddev`, `lower_bound_95` are present and `0.0 <= value <= 1.0` (ADR-0002 — F-COV-1)
  - `parsed["per_case"]` is a non-empty list
  - `parsed["chain_head"]` matches `^sha256:[0-9a-f]{64}$` (F-COV-7)
  - `parsed["block_severity_failure_modes"]` is a list (may be empty for the stub)

- [ ] **AC-5.** `tests/snapshots/eval_run_audit_record.v1.json` exists; is a **JSON Schema** (not a byte-value snapshot) capturing the on-disk record's *shape*: `type: object`, `additionalProperties: false`, and `required` naming every field expected on the wire (`isolation_class`, `complete`, `mean_score`, `score_stddev`, `lower_bound_95`, `per_case`, `chain_head`, `prev_hash`, `block_severity_failure_modes`, plus any other fields S1-02 pins on `BenchRunReport`). The integration test loads this schema via `jsonschema` (already in `dev` deps) and validates the on-disk record against it — drift in *shape* fails here, drift in *values* fails on AC-4. This dual-check catches "field added" vs "value distribution shifted" independently. (F-COV-6 — if the executor decides schema fixture is over-specified, they may collapse AC-4 + AC-5 into one full-value snapshot with an ADR amendment naming the collapse; the tradeoff is called out in Notes.)

- [ ] **AC-6.** `scripts/regen_eval_snapshot.py` exposes two subcommands (click or argparse — match the repo's convention):
  - `regenerate` — writes to `tests/snapshots/bench_run_report.v1.json` + `tests/snapshots/eval_run_audit_record.v1.json`; running it twice in a row from a fresh checkout produces byte-identical files (F-TQ-7 determinism property).
  - `dry-run-tamper --out=<tmp_path>` — writes intentionally-drifted copies to `<tmp_path>` (NOT `tests/snapshots/`); prints the drift diagnostic to stdout; used by a manual smoke test to verify the diagnostic wording is honest. **Forbidden from touching `tests/snapshots/`** (F-TQ-8) — fence-tested: the subcommand refuses if `--out` resolves under `tests/snapshots/`.

- [ ] **AC-7.** Drift diagnostic wording (produced by `assert_snapshot_byte_identical` in `tests/helpers/snapshots.py`): when the snapshot doesn't match, the raised `AssertionError` contains (a) the absolute path of the snapshot file, (b) the substring `scripts/regen_eval_snapshot.py regenerate`, and (c) the substring `templates/adr-amendment.md`. Independently asserted by a helper unit test (`tests/unit/test_snapshot_diagnostic.py`) that mocks a mismatch and inspects the exception message.

- [ ] **AC-8.** `templates/adr-amendment.md` exists (create it if it doesn't) with a minimal Nygard-format stub: `# Amends: ADR-XXXX`, `## Change`, `## Justification`, `## Consequences` sections. The story does NOT gate on any specific content beyond these headers existing.

- [ ] **AC-9.** Runs-dir creation-on-first-write: `runs_dir` does not exist before `run_eval` is called; the first `run_eval` invocation creates it via S2-04's `write_run_record` (S2-04 AC-4 handles the missing-dir case). The test asserts `runs_dir.exists() is False` immediately after the fixture setup and `runs_dir.is_dir()` after the first call, with mode `0o700` on directories under `.codegenie/eval/` (S2-04 AC-2a establishes the mode; this AC verifies the *end-to-end* preservation). (F-COV-2.)

- [ ] **AC-10.** Three distinct `run_started_iso` values feed the three `plan()` calls so on-disk filenames are guaranteed distinct even when everything else about the plan is deterministic. Asserted by: `assert len(set(records)) == 3` on the sorted paths — no filename collision. (F-COV-3.)

- [ ] **AC-11.** Snapshot serialization canonicalizer. `tests/helpers/snapshots.py::assert_snapshot_byte_identical(actual: BaseModel | str, snapshot: Path)` uses `codegenie.eval.snapshots.canonical_json` for the canonicalization; the committed snapshot bytes are the output of that same canonicalizer. Round-trip fence: `tests/fence/test_snapshot_canonicalization_chokepoint.py` reads each committed snapshot under `tests/snapshots/`, round-trips it through `canonical_json(BenchRunReport.model_validate(...))` (for the report snapshot; JSON Schema for the schema snapshot), and asserts byte-equality. (F-TQ-5.)

- [ ] **AC-11a.** `codegenie.eval.snapshots.canonical_json(model: BaseModel) -> str` is a new public helper — pure function, no I/O — that returns `json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True, separators=(",", ": "))`. Add to `__all__`. Fence test in `tests/fence/test_snapshot_canonicalization_chokepoint.py` also AST-walks `src/codegenie/eval/`, `tests/helpers/`, and `scripts/regen_eval_snapshot.py`, and rejects any `.model_dump_json(...)` call on `BenchRunReport | BenchScore | PromotionVerdict` (S1-02's wire types) outside `canonical_json`. (F-DP-5 — Phase 11 / Phase 13 consumers must read the *same* canonicalization as the writer.)

- [ ] **AC-12.** Regen determinism property. A fresh-tmp `scripts/regen_eval_snapshot.py regenerate --out=<tmp_path>` invocation followed immediately by a second invocation to the same `<tmp_path>` produces byte-identical output. Verified by a unit test that shells out via `subprocess.run` (or imports and calls the click entry directly). (F-TQ-7.)

- [ ] **AC-13.** Snapshot versioning rule documented. Module docstring at the top of `codegenie/eval/snapshots.py` and a top comment in `scripts/regen_eval_snapshot.py` both name the rule: **wire-shape changes require (a) `dry-run-tamper` diagnostic fires first, (b) new file `.v2.json` lands alongside `.v1.json` for one release cycle, (c) ADR amendment in `docs/phases/06.5-per-task-class-eval-harness/ADRs/` names the removed / added fields, (d) `.v1.json` is deleted only after Phase 11's consumer catches up.** Textual assertion — no runtime enforcement in this story (Phase 11's consumer will pin the versioning rule structurally when it lands). (F-CON-4.)

- [ ] **AC-14.** The red test from §TDD plan exists, was committed at red, and is now green.

- [ ] **AC-15.** `ruff format --check`, `ruff check`, `mypy --strict src/codegenie/eval/snapshots.py tests/helpers/snapshots.py scripts/regen_eval_snapshot.py tests/integration/test_audit_chain_extension.py tests/fence/test_snapshot_canonicalization_chokepoint.py` clean on touched files. The integration test suite (`tests/integration/test_audit_chain_extension.py`) runs in ≤ 10 s wall-clock on the stub fixture.

## Implementation outline

1. **`src/codegenie/eval/snapshots.py`** — new public module.
   - `canonical_json(model: BaseModel) -> str`: `return json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True, separators=(",", ": "))`. Pure function, `mypy --strict` clean.
   - Module docstring names the snapshot versioning rule (AC-13).
   - Export from `src/codegenie/eval/__init__.py` if surface budget allows (max 9 exports per Phase 6.5 goal — check with `_PUBLIC_SURFACE_CARDINALITY`; if at cap, keep `canonical_json` as an internal-but-import-linter-permitted symbol).

2. **`tests/helpers/snapshots.py`** — new shared test helper (per Rule 11 — matches `tests/helpers/bench.py` and `tests/helpers/chain.py`).
   - `assert_snapshot_byte_identical(actual: BaseModel | str, snapshot: Path) -> None`. If `actual` is a `BaseModel`, canonicalize via `canonical_json`; if `str`, use as-is. Read `snapshot.read_text()`; compare. On mismatch raise `AssertionError` with the diagnostic containing snapshot path + regen command + ADR-amendment template path (AC-7).
   - No I/O beyond reading the snapshot file; no logging.

3. **`scripts/regen_eval_snapshot.py`** — click subcommand group.
   - `regenerate` subcommand: builds a `plan` via `make_stub_plan(tmp_path)` with `run_started_iso="1970-01-01T00:00:00+00:00"`, runs `Runner().run_eval(plan, system_under_test=JitteredStubSUT.zero(), out_dir=tmp_out, **_default_execute_kwargs(tmp_path))`, canonicalizes the returned report, writes to `tests/snapshots/bench_run_report.v1.json`. Also generates the JSON Schema for `eval_run_audit_record.v1.json` via `BenchRunReport.model_json_schema()` (post-processed to `additionalProperties: false` where S1-02 requires it).
   - `dry-run-tamper --out=<tmp_path>` subcommand: same regen, but injects an extra field (`_dry_run_marker: "tamper"`) before canonicalization; writes to `--out`; refuses if `--out` resolves under `tests/snapshots/` (fence — AC-6). Prints the drift diagnostic to stdout.
   - `main() -> None` annotated; `mypy --strict` clean.

4. **`tests/integration/test_audit_chain_extension.py`** — the integration test file. Tests:
   - `test_three_run_evals_produce_a_chain_of_length_three` (AC-1, AC-9, AC-10)
   - `test_chain_links_verify_via_oracle` (AC-2)
   - `test_tamper_on_prev_hash_detected` (AC-3, F-COV-5)
   - `test_bench_run_report_snapshot_byte_identical_to_v1` (AC-4, AC-11)
   - `test_eval_run_audit_record_matches_json_schema` (AC-5)

5. **`tests/fence/test_snapshot_canonicalization_chokepoint.py`** — AST walk over `src/codegenie/eval/`, `tests/helpers/`, `scripts/regen_eval_snapshot.py`; rejects any `.model_dump_json(...)` call on `BenchRunReport | BenchScore | PromotionVerdict` outside `canonical_json`; asserts round-trip byte-equality on every `tests/snapshots/*.v1.json` file.

6. **`templates/adr-amendment.md`** — create if missing per AC-8. Four sections: `# Amends: ADR-XXXX`, `## Change`, `## Justification`, `## Consequences`. Short.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/integration/test_audit_chain_extension.py`

```python
# tests/integration/test_audit_chain_extension.py
"""End-to-end: three consecutive Runner().run_eval calls extend the S2-04
audit chain to length 3 with verify().ok is True; snapshot the report shape.

Runner API (hardened S3-01/S3-02/S3-06/S4-02): stateless Runner(); two-call
flow: plan = Runner().plan(...); report = asyncio.run(Runner().run_eval(plan, ...)).
Time-freezing via plan(run_started_iso=...), NOT a run_eval kwarg.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import jsonschema
import pytest

from codegenie.eval.audit import verify as audit_verify
from codegenie.eval.models import BenchRunReport
from codegenie.eval.runner import Runner
from codegenie.eval.snapshots import canonical_json
from codegenie.hashing import GENESIS_PREV_HASH, chain_identity, content_hash_bytes
from tests.helpers.bench import (
    JitteredStubSUT,
    make_stub_plan,
    stub_task_class_fixture,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_REPORT = REPO_ROOT / "tests/snapshots/bench_run_report.v1.json"
SNAPSHOT_SCHEMA = REPO_ROOT / "tests/snapshots/eval_run_audit_record.v1.json"


def _default_execute_kwargs(tmp_path: Path) -> dict:
    # Mirrors S3-02's _default_kwargs — cache_dir + timeout_per_case_seconds
    # + a deterministic rubric_runner stub.
    from tests.helpers.bench import make_deterministic_rubric_runner
    return {
        "rubric_runner": make_deterministic_rubric_runner(),
        "cache_dir": tmp_path / ".codegenie/eval/cache",
        "timeout_per_case_seconds": 5.0,
    }


def _run_once(tmp_path: Path, runs_dir: Path, run_started_iso: str) -> BenchRunReport:
    """Build a plan with a frozen run_started_iso, execute run_eval once,
    return the report. runs_dir is passed to plan() (for chain verify) AND
    to run_eval() (for chain append) — same directory."""
    plan = make_stub_plan(
        tmp_path,
        run_started_iso=run_started_iso,
        out_dir=runs_dir,
    )
    return asyncio.run(
        Runner().run_eval(
            plan,
            system_under_test=JitteredStubSUT.zero(),
            out_dir=runs_dir,
            **_default_execute_kwargs(tmp_path),
        )
    )


# ------------------------------------------------------------- AC-1 / AC-9 / AC-10

def test_three_run_evals_produce_a_chain_of_length_three(tmp_path):
    runs_dir = tmp_path / ".codegenie/eval/runs"
    assert not runs_dir.exists()  # AC-9 preamble

    for iso in (
        "1970-01-01T00:00:00+00:00",
        "1970-01-01T00:00:01+00:00",
        "1970-01-01T00:00:02+00:00",
    ):
        _run_once(tmp_path, runs_dir, iso)

    assert runs_dir.is_dir()  # AC-9
    records = tuple(sorted(runs_dir.glob("*.json")))
    assert len(records) == 3  # AC-1
    assert len(set(records)) == 3  # AC-10 — no filename collision
    result = audit_verify(runs_dir)
    assert result.ok is True  # AC-1 baseline


# --------------------------------------------------------------------- AC-2

def test_chain_links_verify_via_oracle(tmp_path):
    runs_dir = tmp_path / ".codegenie/eval/runs"
    for iso in (
        "1970-01-01T00:00:00+00:00",
        "1970-01-01T00:00:01+00:00",
        "1970-01-01T00:00:02+00:00",
    ):
        _run_once(tmp_path, runs_dir, iso)

    records = tuple(sorted(runs_dir.glob("*.json")))
    r1, r2, r3 = (json.loads(p.read_text()) for p in records)

    assert r1["prev_hash"] == GENESIS_PREV_HASH

    # Independent oracle: recompute r2's expected prev_hash from r1.
    r1_model = BenchRunReport.model_validate(r1)
    r1_canon = canonical_json(r1_model.model_copy(update={"chain_head": ""}))
    expected_r2_prev = chain_identity(
        r1["prev_hash"], content_hash_bytes(r1_canon.encode("utf-8"))
    )
    assert r2["prev_hash"] == expected_r2_prev

    r2_model = BenchRunReport.model_validate(r2)
    r2_canon = canonical_json(r2_model.model_copy(update={"chain_head": ""}))
    expected_r3_prev = chain_identity(
        r2["prev_hash"], content_hash_bytes(r2_canon.encode("utf-8"))
    )
    assert r3["prev_hash"] == expected_r3_prev


# --------------------------------------------------------------------- AC-3

def test_tamper_on_prev_hash_detected(tmp_path):
    runs_dir = tmp_path / ".codegenie/eval/runs"
    for iso in (
        "1970-01-01T00:00:00+00:00",
        "1970-01-01T00:00:01+00:00",
        "1970-01-01T00:00:02+00:00",
    ):
        _run_once(tmp_path, runs_dir, iso)
    records = tuple(sorted(runs_dir.glob("*.json")))

    # Pre-tamper baseline (F-COV-5).
    assert audit_verify(runs_dir).ok is True

    # Flip one byte in run-2's prev_hash — target the chain-link semantic
    # (Notes-for-implementer #5). Same-length replacement preserves JSON shape.
    parsed = json.loads(records[1].read_text())
    orig = parsed["prev_hash"]
    swap = "a" if orig[-1] != "a" else "b"
    parsed["prev_hash"] = orig[:-1] + swap
    records[1].write_text(json.dumps(parsed))

    result = audit_verify(runs_dir)
    assert result.ok is False
    assert result.tampered_path == records[1]
    assert result.reason is not None
    assert result.reason.startswith(("prev_hash mismatch", "content_hash mismatch"))


# ------------------------------------------------------------- AC-4 / AC-11

def test_bench_run_report_snapshot_byte_identical_to_v1(tmp_path):
    from tests.helpers.snapshots import assert_snapshot_byte_identical

    runs_dir = tmp_path / ".codegenie/eval/runs"
    report = _run_once(tmp_path, runs_dir, "1970-01-01T00:00:00+00:00")

    # F-DP-5: canonicalize via the production chokepoint, not model_dump_json.
    assert_snapshot_byte_identical(report, SNAPSHOT_REPORT)

    # Independent oracle assertions on the committed snapshot (F-COV-1, F-COV-7).
    parsed = json.loads(SNAPSHOT_REPORT.read_text())
    assert parsed["isolation_class"] == "subprocess"
    assert parsed["complete"] is True
    for field in ("mean_score", "score_stddev", "lower_bound_95"):
        assert isinstance(parsed[field], (int, float))
        assert 0.0 <= float(parsed[field]) <= 1.0
    assert isinstance(parsed["per_case"], list) and parsed["per_case"]
    import re
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", parsed["chain_head"])
    assert isinstance(parsed["block_severity_failure_modes"], list)


# --------------------------------------------------------------------- AC-5

def test_eval_run_audit_record_matches_json_schema(tmp_path):
    runs_dir = tmp_path / ".codegenie/eval/runs"
    _run_once(tmp_path, runs_dir, "1970-01-01T00:00:00+00:00")
    records = tuple(sorted(runs_dir.glob("*.json")))
    on_disk = json.loads(records[0].read_text())

    schema = json.loads(SNAPSHOT_SCHEMA.read_text())
    assert schema["type"] == "object"
    assert schema.get("additionalProperties") is False
    # Sanity: required fields include the audit-chain identity fields.
    for field in ("prev_hash", "chain_head", "isolation_class"):
        assert field in schema["required"]

    # Validate — raises jsonschema.ValidationError on drift.
    jsonschema.validate(on_disk, schema)
```

Run; confirm `ModuleNotFoundError: codegenie.eval.snapshots` and `ModuleNotFoundError: tests.helpers.snapshots` and `FileNotFoundError: tests/snapshots/bench_run_report.v1.json`. Commit as the red marker.

### Green

Land in this order (each step should push the red closer to green):

1. `src/codegenie/eval/snapshots.py` — `canonical_json` helper + module docstring (AC-11a, AC-13).
2. `tests/helpers/snapshots.py` — `assert_snapshot_byte_identical` (AC-7).
3. `scripts/regen_eval_snapshot.py` — click group with `regenerate` + `dry-run-tamper` subcommands (AC-6).
4. `python scripts/regen_eval_snapshot.py regenerate` — produces `tests/snapshots/bench_run_report.v1.json` + `tests/snapshots/eval_run_audit_record.v1.json` for the first time. Commit those two files (they are the golden shape from this point on).
5. `templates/adr-amendment.md` — create if missing (AC-8).
6. `tests/fence/test_snapshot_canonicalization_chokepoint.py` — the fence (AC-11).
7. `tests/unit/test_snapshot_diagnostic.py` — AC-7's diagnostic-text unit test.
8. Re-run the integration suite — all five tests should now be green.

### Refactor

- Confirm `run_id` derivation in `Runner().plan(...)` is fully deterministic from inputs (S3-01 AC-2 already pins this) — no `time.time()`, no `uuid.uuid4()`. If the runner leaked wall-clock into the plan, this story surfaces the leak as a `regen determinism` failure (AC-12); fix it in S3-01, not here.
- The drift diagnostic must point at *both* the regen command AND the ADR amendment template (AC-7) — a snapshot change without an ADR is a load-bearing failure mode.
- `mypy --strict` clean on all touched files (AC-15).
- Verify the snapshot files round-trip cleanly: `BenchRunReport.model_validate(json.loads(SNAPSHOT_REPORT.read_text()))` succeeds; `jsonschema.Draft202012Validator.check_schema(json.loads(SNAPSHOT_SCHEMA.read_text()))` succeeds. Both are already exercised by the tests above but worth confirming in a REPL.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_audit_chain_extension.py` | New — five tests: three-run chain integration + oracle chain-link + tamper detection + report snapshot + schema fixture validation |
| `tests/helpers/snapshots.py` | New — `assert_snapshot_byte_identical` (moved from the original story's `tests/integration/_snapshot_helpers.py` per Rule 11 / F-DP-1) |
| `src/codegenie/eval/snapshots.py` | New — `canonical_json` production chokepoint (F-DP-5) + versioning-rule docstring |
| `tests/snapshots/bench_run_report.v1.json` | New — frozen `BenchRunReport` byte-shape from a stub run at `run_started_iso="1970-01-01T00:00:00+00:00"` |
| `tests/snapshots/eval_run_audit_record.v1.json` | New — JSON Schema fixture (not byte snapshot) capturing on-disk record shape |
| `scripts/regen_eval_snapshot.py` | New — click subcommand group: `regenerate` + `dry-run-tamper --out=<tmp_path>` |
| `tests/fence/test_snapshot_canonicalization_chokepoint.py` | New — AST fence + round-trip byte-equality (AC-11) |
| `tests/unit/test_snapshot_diagnostic.py` | New — AC-7 diagnostic-text unit test |
| `templates/adr-amendment.md` | Create if missing — minimal Nygard-format stub |
| `src/codegenie/eval/__init__.py` | Edit — add `canonical_json` to `__all__` if surface budget allows (check `_PUBLIC_SURFACE_CARDINALITY`) |
| `tests/helpers/bench.py` | Edit — extend `make_stub_plan` to accept a `run_started_iso` kwarg if it doesn't already (additive; check hardened S3-02) and add `make_deterministic_rubric_runner` if it doesn't exist |

## Out of scope

- **Fence-CI assertions** — S7-01.
- **Cross-phase ADR amendments** — S7-03.
- **Auditing reports from real benches (vuln-remediation, distroless)** — the integration test uses the stub fixture for byte-determinism; real-bench audit integration is covered by S5-05 and S6-03 individually.
- **Performance regression of audit-chain extension** — Phase 0's own perf canaries cover this.
- **Phase 11 / Phase 13 consumer readers** — this story ships the *canonicalizer chokepoint*, but Phase 11's PR provenance reader and Phase 13's ROI dashboard consume it later. Nothing in this story stubs those.
- **`--allow-isolation-mix` operator override** — ADR-0010 defers the transition contract to Phase 16.

## Notes for the implementer

- **The runner contract changed after this story was first written — follow the hardened APIs, not the original prose.** `Runner()` is stateless. `Runner().plan(name, *, sut_digest_fn, bench_root, out_dir, run_started_iso, cassette_root, harness_version)` loads the task class + cases and verifies the chain *internally*, raising `ChainTamperDetected` / `BenchCaseDigestMismatch` / `TaskClassNotFound` before any SUT call. `Runner().run_eval(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency=None, max_cost_usd=5.0, out_dir)` is the audit-writing composition root. Do **not** call `load_task_class` / `load_cases` / `audit.verify` directly on this path — `plan()` owns them. This is the same mistake S4-02 caught in its own validation (F-CON-2); the pattern is well-established.

- **Determinism is the load-bearing property.** If a stub `run_eval` produces different bytes across two runs with identical inputs (same `run_started_iso`, same `sut_digest`, same `rubric_digest`, same cassette corpus), the snapshot test is meaningless. S3-01 pins `run_id` derivation off input hashes (no wall-clock, no uuid); if the executor observes non-determinism at snapshot time, fix it in the runner (S3-01 / S3-02 / S3-06), not here — this story just consumes the determinism.

- **`isolation_class` must appear in the snapshot.** It defaults to `"subprocess"` (ADR-0010); if it's missing, Phase 16's microVM upgrade detector is silently absent. AC-4 verifies the field is present AND equals `"subprocess"` — do NOT trust `model_dump` to serialize defaults; the assertion is against the on-disk bytes.

- **Tamper target is `prev_hash`, not `mean_score`.** Notes-for-implementer #5 in the original story acknowledged this — `mean_score` invalidates the record's *own* content hash (interesting but semantic-ambiguous); `prev_hash` invalidates the *chain link* (the invariant this whole story is here to protect). AC-3 pins the target and pins the specific `VerifyResult.reason` shape.

- **Three runs is the minimum to test chain *semantics*.** One run only tests genesis; two runs tests one link; three runs tests that `verify` walks past genesis, past the first link, to the head. Don't be tempted to test with one run "for speed" — the chain semantics aren't exercised.

- **Three distinct `run_started_iso` values are the correct threading** for the three-run test. A single frozen ISO would collide on filename (S3-01's basename derivation includes `run_id` which is content-addressed off `run_started_iso`); three distinct ISOs give three distinct filenames without sacrificing single-run determinism (each snapshot test uses only *one* frozen ISO).

- **The two snapshot files detect drift at different granularities.** `bench_run_report.v1.json` is a full byte snapshot — catches value drift (a stub SUT that regressed to emit `mean_score=0.5` when it was `0.0` before). `eval_run_audit_record.v1.json` is a JSON Schema — catches shape drift (a field added to `BenchRunReport` that nobody remembered to bump a version for). If the executor decides the schema fixture is over-specified for Phase 6.5 needs (e.g., because S1-02's `_FROZEN_WIRE_TYPES` cardinality test + `additionalProperties: false` on `BenchRunReport` already catches shape drift), they may collapse AC-4 + AC-5 into one full-value snapshot — but they must land an ADR amendment in `docs/phases/06.5-per-task-class-eval-harness/ADRs/` naming the collapse and record why.

- **The drift diagnostic is operator-facing.** A future contributor whose innocent change to `BenchRunReport` (adding a field) trips this test must read the diagnostic and *immediately know* the path forward: (a) regenerate the snapshot via `python scripts/regen_eval_snapshot.py regenerate`, (b) write an ADR amendment using `templates/adr-amendment.md`, (c) if the field addition breaks downstream Phase 11 / Phase 13 consumers, bump `v1` → `v2` per AC-13's rule. Rule 12 — Fail loud.

- **Canonicalization lives in production code, not test code.** `codegenie.eval.snapshots.canonical_json` is the single chokepoint that Phase 11 / Phase 13 consumers will also use to compute checksums or compare shapes. Inline `model_dump_json(indent=2)` in a test helper would drift the moment Pydantic changes its default serialization — and Phase 11 would then read a different shape than the writer produced. The fence at AC-11a prevents this silently.

- **`--dry-run-tamper` must never touch `tests/snapshots/`.** The subcommand's `--out` argument is validated to reject any path resolving under `tests/snapshots/` (AC-6). A future contributor running `python scripts/regen_eval_snapshot.py dry-run-tamper --out=tests/snapshots/` (typo or copy-paste from the docs) must NOT land tampered committed snapshots.

- **Snapshot versioning is a *documented convention*, not a runtime enforcement in this story.** AC-13 puts the rule in module docstrings so operators know what to do; Phase 11's consumer will pin it structurally when it lands. The path forward is well-understood; over-engineering the enforcement in Phase 6.5 is YAGNI (Rule 2).
