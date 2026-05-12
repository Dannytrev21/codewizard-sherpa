# Story S4-02 — `collect_test_signal` with pre-patch test inventory delta

**Step:** Step 4 — Six signal collectors + StrictAndGate adapter
**Status:** Ready
**Effort:** M
**Depends on:** S3-07 (real `SandboxRun` against `hello-node`), S1-05 (registry), S1-03 (`TestSignal` model)
**ADRs honored:** ADR-0015, ADR-0014, ADR-0003

## Context

`collect_test_signal` is the load-bearing collector for the most documented adversarial path in the phase: an LLM-produced patch deletes a failing test to make `npm test` pass. ADR-0015 establishes asymmetric inventory policy — `delta_test_count < 0` fails strict-AND; `delta_test_count > 0` is informational. The collector reads the post-patch test run from `SandboxRun.logs_dir` and compares against a pre-patch inventory snapshot path supplied via `GateContext` (Phase 3 produces and persists the snapshot before Phase 4 runs).

## References — where to look

- **Architecture:** `../phase-arch-design.md §Signal collectors` — `collect_test_signal(run, *, pre_patch_inventory_path: Path) -> TestSignal` signature.
- **Architecture:** `../phase-arch-design.md §Edge cases 6, 7, 17` — test removal adversarial path, legitimate additions, 3× repeated `failed_unrecoverable`.
- **Phase ADRs:** `../ADRs/0015-test-inventory-delta-asymmetric-policy.md` — ADR-0015 — `delta < 0` → `passed=False`; `delta > 0` → annotation only; `details["delta_test_count"]` always emitted (zero, positive, or negative).
- **Phase ADRs:** `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — `details` typing constraint.
- **Phase ADRs:** `../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — ADR-0003 — registers via `@register_signal_kind("tests")`.
- **High-level impl:** `../High-level-impl.md §Step 4` — done criterion: "delta_test_count = -1 when a test file is removed by the patch (against `tests/fixtures/repos/test-removes-test/`)".
- **Existing code:** `src/codegenie/sandbox/signals/_common.py` (S4-01) — shared helpers.
- **Existing code:** `src/codegenie/sandbox/signals/models.py` — `TestSignal`.

## Goal

Ship `collect_test_signal(run: SandboxRun, *, pre_patch_inventory_path: Path) -> TestSignal` that parses jest/vitest output from `run.logs_dir`, computes `delta_test_count = post - pre` against the snapshot, and sets `passed = (run.exit_code == 0 and delta_test_count >= 0)`.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/signals/tests.py` defines `collect_test_signal(run, *, pre_patch_inventory_path)`, decorated `@register_signal_kind("tests")`, ≤ 60 LOC excluding parser helpers (parser may live in `_test_parser.py`).
- [ ] `details["delta_test_count"]` is **always** present as an `int` — zero, positive, or negative. Missing inventory file → `delta_test_count = 0` AND `details["pre_patch_inventory_missing"] = True`.
- [ ] When `delta_test_count < 0`, `passed=False` regardless of exit code (ADR-0015 — adversarial path catch).
- [ ] When `delta_test_count > 0` AND `run.exit_code == 0`, `passed=True` AND `details["delta_test_count"]` is positive (informational annotation).
- [ ] When `run.exit_code != 0`, `passed=False`; `details["first_failure"]` is the first failing test name parsed from the log; `details["failing_tests"]` is a comma-joined string of failing test names (NOT a list — `details` is `dict[str, str | int | bool]`).
- [ ] Parser tolerates jest, vitest, and mocha output formats; unknown format yields `details["parser_format"] = "unknown"` AND `delta_test_count = 0`.
- [ ] Adversarial integration test against `tests/fixtures/repos/test-removes-test/` proves the collector returns `passed=False, delta_test_count=-1` when the patch removes one test file (ADR-0015 — load-bearing).
- [ ] Informational test: a `tests/fixtures/repos/test-adds-regression/` scenario where the patch adds a regression test → `passed=True, delta_test_count=+1`, `failing_signals` does NOT include `"tests"`.
- [ ] Field name `coverage_evidence_strength` is NOT used here (that's trace, S4-03). No banned substrings introduced into `details` keys (`tests/schema/test_objective_signals_static.py` still green).
- [ ] Property test: for any pair `(pre, post)` of non-negative integers, `delta = post - pre`; if `delta < 0`, `passed=False`; if `delta == 0 and exit_code == 0`, `passed=True`.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Define the inventory snapshot format: a JSON file at `pre_patch_inventory_path` with shape `{"test_count": int, "test_names": list[str], "captured_at": ISO8601}`. Document in a module docstring; Phase 3's responsibility to produce.
2. Create `src/codegenie/sandbox/signals/_test_parser.py`:
   - `parse_test_results(logs_dir: Path) -> _ParsedTests`: scans `stdout.log` for jest/vitest summary lines (`Tests:`, `Test Suites:`); falls back to mocha's `passing`/`failing`; populates `_ParsedTests(post_count, failing, first_failure, format)`.
   - Pure function; uses regex; no I/O outside the supplied `logs_dir`.
3. Create `src/codegenie/sandbox/signals/tests.py`:
   - Read pre-patch inventory; tolerate missing file (annotate, don't raise).
   - Call parser; compute `delta_test_count = parsed.post_count - pre_count`.
   - Build `details` dict (str keys → str/int/bool only).
   - Compute `passed = (run.exit_code == 0 and delta_test_count >= 0)`.
   - Construct frozen `TestSignal`.
4. Create fixture repos: `tests/fixtures/repos/test-removes-test/{pre_inventory.json, sandbox_run/logs/stdout.log}` and `tests/fixtures/repos/test-adds-regression/{...}`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/sandbox/test_signals_tests.py`

```python
# tests/sandbox/test_signals_tests.py
import json
from datetime import datetime
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from codegenie.sandbox.contract import SandboxRun, SandboxSpec
from codegenie.sandbox.signals.models import TestSignal
from codegenie.sandbox.signals.tests import collect_test_signal


def _write_pre_inventory(path: Path, count: int, names: list[str]) -> None:
    path.write_text(json.dumps({"test_count": count, "test_names": names, "captured_at": "2026-05-12T00:00:00Z"}))


def _make_run(tmp: Path, exit_code: int, stdout: str) -> SandboxRun:
    logs = tmp / "logs"
    logs.mkdir()
    (logs / "stdout.log").write_text(stdout)
    spec = SandboxSpec.model_construct(
        base_image="cgr.dev/chainguard/node@sha256:abc", copy_in=[], env={},
        cmd=["npm", "test"], network="none", egress_allowlist=[], enable_trace=False,
        time_budget_seconds=600, memory_limit_mib=2048, pids_limit=1024,
        copy_out=[], label="stage6.tests.attempt1", sandbox_spec_hash="d",
    )
    return SandboxRun(
        run_id="01HXYZ", spec=spec, backend="docker_in_docker",
        gate_isolation_class="shared_kernel",
        started_at=datetime(2026, 5, 12), ended_at=datetime(2026, 5, 12),
        exit_code=exit_code, duration_ms=1000, microvm_seconds=0.0,
        image_pull_bytes=0, build_cache_hit=True, logs_dir=logs,
        trace_path=None, copy_out_root=tmp / "out",
        timed_out=False, killed_by_oom=False,
    )


JEST_OK = "Tests:       42 passed, 42 total\nTest Suites: 7 passed, 7 total\n"
JEST_REMOVED = "Tests:       41 passed, 41 total\nTest Suites: 6 passed, 6 total\n"
JEST_ADDED = "Tests:       43 passed, 43 total\nTest Suites: 8 passed, 8 total\n"
JEST_FAIL = "Tests:       41 failed, 1 passed, 42 total\nFAIL src/auth.test.ts > jwt-validates\n"


def test_test_removed_sets_passed_false_delta_negative(tmp_path):
    # WHY: ADR-0015 adversarial — LLM deletes a test to make npm test pass.
    inv = tmp_path / "pre.json"
    _write_pre_inventory(inv, count=42, names=[])
    sig = collect_test_signal(_make_run(tmp_path, 0, JEST_REMOVED), pre_patch_inventory_path=inv)
    assert sig.passed is False
    assert sig.details["delta_test_count"] == -1


def test_test_added_is_informational_passed_true(tmp_path):
    # WHY: ADR-0015 — delta > 0 is annotation, not failure.
    inv = tmp_path / "pre.json"
    _write_pre_inventory(inv, count=42, names=[])
    sig = collect_test_signal(_make_run(tmp_path, 0, JEST_ADDED), pre_patch_inventory_path=inv)
    assert sig.passed is True
    assert sig.details["delta_test_count"] == 1


def test_exit_zero_no_delta_passes(tmp_path):
    inv = tmp_path / "pre.json"
    _write_pre_inventory(inv, count=42, names=[])
    sig = collect_test_signal(_make_run(tmp_path, 0, JEST_OK), pre_patch_inventory_path=inv)
    assert sig.passed is True
    assert sig.details["delta_test_count"] == 0


def test_test_failure_populates_first_failure(tmp_path):
    inv = tmp_path / "pre.json"
    _write_pre_inventory(inv, count=42, names=[])
    sig = collect_test_signal(_make_run(tmp_path, 1, JEST_FAIL), pre_patch_inventory_path=inv)
    assert sig.passed is False
    assert "auth" in sig.details["first_failure"]


def test_missing_inventory_annotates_does_not_raise(tmp_path):
    # WHY: Phase 3 may not have run yet during a partial dev loop; collector must not crash.
    sig = collect_test_signal(_make_run(tmp_path, 0, JEST_OK), pre_patch_inventory_path=tmp_path / "missing.json")
    assert sig.details["pre_patch_inventory_missing"] is True
    assert sig.details["delta_test_count"] == 0


def test_unknown_format_falls_back_safely(tmp_path):
    inv = tmp_path / "pre.json"
    _write_pre_inventory(inv, count=42, names=[])
    sig = collect_test_signal(_make_run(tmp_path, 0, "nothing here"), pre_patch_inventory_path=inv)
    assert sig.details["parser_format"] == "unknown"
    assert sig.details["delta_test_count"] == 0


def test_details_only_primitive_value_types(tmp_path):
    # WHY: ADR-0014 — failing_tests is a comma-joined string, not a list.
    inv = tmp_path / "pre.json"
    _write_pre_inventory(inv, count=42, names=[])
    sig = collect_test_signal(_make_run(tmp_path, 1, JEST_FAIL), pre_patch_inventory_path=inv)
    for v in sig.details.values():
        assert isinstance(v, (str, int, bool))


@given(pre=st.integers(min_value=0, max_value=10_000), post=st.integers(min_value=0, max_value=10_000))
def test_asymmetric_delta_policy_property(pre, post, tmp_path):
    inv = tmp_path / f"pre_{pre}_{post}.json"
    _write_pre_inventory(inv, count=pre, names=[])
    stdout = f"Tests:       {post} passed, {post} total\n"
    sig = collect_test_signal(_make_run(tmp_path, 0, stdout), pre_patch_inventory_path=inv)
    delta = post - pre
    if delta < 0:
        assert sig.passed is False
    else:
        assert sig.passed is True
    assert sig.details["delta_test_count"] == delta
```

### Green — make it pass

- Implement `_test_parser.py` with jest/vitest/mocha regexes. Order: try jest summary, then vitest summary, then mocha; on no match return `format="unknown"`, `post_count=0`.
- Implement `tests.py` orchestrating inventory read + parse + delta + frozen `TestSignal` construction.

### Refactor — clean up

- If parsing branches get long, extract per-format parsers into private functions returning `Optional[_ParsedTests]`.
- Pull JSON inventory schema into a tiny Pydantic model in the same file (no separate file — Rule 3).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/signals/tests.py` | The collector. |
| `src/codegenie/sandbox/signals/_test_parser.py` | jest/vitest/mocha output parser. |
| `src/codegenie/sandbox/signals/__init__.py` | Re-export so registration fires. |
| `tests/sandbox/test_signals_tests.py` | All seven cases + property test. |
| `tests/fixtures/repos/test-removes-test/pre_inventory.json` | Adversarial fixture (delta = -1). |
| `tests/fixtures/repos/test-removes-test/sandbox_run/logs/stdout.log` | Captured `npm test` output post-removal. |
| `tests/fixtures/repos/test-adds-regression/pre_inventory.json` | Informational fixture (delta = +1). |
| `tests/fixtures/repos/test-adds-regression/sandbox_run/logs/stdout.log` | Captured `npm test` output post-add. |

## Out of scope

- `failed_unrecoverable` 3× detection — that's the `GateRunner` (S5-02), not the collector.
- The `tests/adversarial/test_patch_disables_test.py` end-to-end test — consolidated into S7-01; this story only proves the collector's delta math.
- Trace, policy, cve_delta collectors — S4-03.

## Notes for the implementer

1. `details` is `dict[str, str | int | bool]`. `failing_tests` must be a comma-joined string, not `list[str]`. Pydantic rejects nested dicts and floats — convert durations to int.
2. `delta_test_count` is **always** an int and **always** in `details`. Zero, positive, or negative — never `None`, never missing. ADR-0015 invariant.
3. `passed` logic: `run.exit_code == 0 and delta_test_count >= 0`. The exit code is checked **first** — a failing test run is `passed=False` even with `delta_test_count=0`.
4. No banned substring in `details` keys. Don't name anything `*_confidence`, `*_llm`, `*_self_reported`, `*_model_says`. The static introspection test runs at every CI build.
5. The pre-patch inventory file is produced by Phase 3 — for now your tests synthesize it; Phase 3's wiring is out of scope for this story.
6. Don't try to compute `delta_test_count` from log diff. Use the pre-patch JSON snapshot. Anything else lets the LLM influence the count.
