# Story S4-01 — `collect_build_signal` + `collect_install_signal`

**Step:** Step 4 — Six signal collectors + StrictAndGate adapter
**Status:** Ready
**Effort:** S
**Depends on:** S3-07 (DinD integration suite produces real `SandboxRun` artifacts), S1-05 (`@register_signal_kind` registry), S1-03 (`ObjectiveSignals` + `BuildSignal` / `InstallSignal` sub-models)
**ADRs honored:** ADR-0003, ADR-0014

## Context

The two simplest of the six signal collectors. Each translates a `SandboxRun` produced by a real DinD execution of the `build` / `install` phase into a typed Pydantic sub-model. Build and install signals are pure functions over `run.exit_code`, `run.logs_dir`, and `run.timed_out` / `run.killed_by_oom` — no external resources, no diff baselines. This story is the template the remaining four collectors copy from; getting the shape right here pays back four times.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Signal collectors (six functions; open registry)` — function signatures, ≤ 60 LOC budget, "Returns the signal sub-model with `passed=False` and structured `details` reason; never raises".
- **Architecture:** `../phase-arch-design.md §Data model` — `_SignalBase`, `BuildSignal`, `InstallSignal`, `SignalProvenance`, the `details: dict[str, str | int | bool]` constraint (no float, no nested dict).
- **Phase ADRs:** `../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — ADR-0003 — collectors register via `@register_signal_kind`; widens Phase 3's open kind registry.
- **Phase ADRs:** `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — `details` keys are screened by the static introspection test; `confidence`/`llm`/`self_reported`/`model_says` substrings are banned.
- **High-level impl:** `../High-level-impl.md §Step 4` — each collector ≤ 60 LOC, decorated with `@register_signal_kind`.
- **Existing code:** `src/codegenie/sandbox/contract.py` (S1-02) — `SandboxRun` fields the collectors read.
- **Existing code:** `src/codegenie/sandbox/signals/models.py` (S1-03) — `BuildSignal`, `InstallSignal`, `_SignalBase`, `SignalProvenance`.
- **Existing code:** `src/codegenie/sandbox/signals/registry.py` (S1-05) — `@register_signal_kind` decorator and collision policy.

## Goal

Ship two pure-function signal collectors — `collect_build_signal(run: SandboxRun) -> BuildSignal` and `collect_install_signal(run: SandboxRun) -> InstallSignal` — each ≤ 60 LOC, decorated with `@register_signal_kind`, returning frozen sub-models whose `passed` field reflects `run.exit_code == 0 and not run.timed_out and not run.killed_by_oom`.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/signals/build.py` defines `collect_build_signal(run: SandboxRun) -> BuildSignal`, ≤ 60 LOC, decorated `@register_signal_kind("build")`.
- [ ] `src/codegenie/sandbox/signals/install.py` defines `collect_install_signal(run: SandboxRun) -> InstallSignal`, ≤ 60 LOC, decorated `@register_signal_kind("install")`.
- [ ] Both collectors set `passed = (run.exit_code == 0 and not run.timed_out and not run.killed_by_oom)`.
- [ ] On failure, `details` contains structured keys (`exit_code: int`, `timed_out: bool`, `killed_by_oom: bool`, `last_log_line: str` truncated to 256 chars). No banned substrings in any key.
- [ ] Both collectors emit `SignalProvenance` with `signal_kind`, `collector_module`, `collector_version="1"`, and `inputs_blake3` computed from a canonical-JSON of `(run.run_id, run.spec.sandbox_spec_hash, run.exit_code)`.
- [ ] Collectors NEVER raise on collector-specific failure (missing `logs_dir`, unreadable last-log file) — they return `passed=False` with a `details` reason.
- [ ] Pure-function property test: same `SandboxRun` instance → byte-identical sub-model on repeat calls (`provenance.inputs_blake3` deterministic).
- [ ] `tests/schema/test_objective_signals_static.py` still green — no banned substring entered the type tree.
- [ ] Both collectors registered with the registry on import; `tests/sandbox/test_signals_registry.py` asserts `"build"` and `"install"` resolve to the right callables.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/sandbox/signals/build.py`:
   - Import `BuildSignal`, `SignalProvenance` from `.models`; `SandboxRun` from `..contract`; `register_signal_kind` from `.registry`.
   - Function `_read_last_log_line(logs_dir: Path) -> str` returning `""` on any IOError; truncate to 256 chars; strip newlines.
   - Function `_inputs_blake3(run: SandboxRun) -> str` over canonical-JSON `{"run_id": ..., "spec_hash": ..., "exit_code": ...}`.
   - `@register_signal_kind("build")` `collect_build_signal(run)` → builds `details: dict[str, str | int | bool]` and returns frozen `BuildSignal(passed=..., details=..., provenance=..., at=datetime.now(UTC))`.
2. Create `src/codegenie/sandbox/signals/install.py` — same pattern, kind `"install"`. Factor the helpers into `_common.py` if both files duplicate them (Rule 3: only if duplication is real).
3. Add `tests/sandbox/test_signals_build.py` and `tests/sandbox/test_signals_install.py` with fake `SandboxRun` fixtures.
4. Run `tests/schema/test_objective_signals_static.py` to confirm no banned substring.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/sandbox/test_signals_build.py`

```python
# tests/sandbox/test_signals_build.py
from datetime import datetime
from pathlib import Path

import pytest

from codegenie.sandbox.contract import SandboxRun, SandboxSpec
from codegenie.sandbox.signals.build import collect_build_signal
from codegenie.sandbox.signals.models import BuildSignal


def _run(tmp_path: Path, *, exit_code: int, timed_out: bool = False, oom: bool = False) -> SandboxRun:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "stdout.log").write_text("npm WARN deprecated\nbuild output\n")
    spec = SandboxSpec.model_construct(
        base_image="cgr.dev/chainguard/node@sha256:abc",
        copy_in=[], env={}, cmd=["npm", "run", "build"],
        network="none", egress_allowlist=[], enable_trace=False,
        time_budget_seconds=600, memory_limit_mib=2048, pids_limit=1024,
        copy_out=[], label="stage6.build.attempt1", sandbox_spec_hash="deadbeef",
    )
    return SandboxRun(
        run_id="01HXYZ", spec=spec, backend="docker_in_docker",
        gate_isolation_class="shared_kernel",
        started_at=datetime(2026, 5, 12), ended_at=datetime(2026, 5, 12),
        exit_code=exit_code, duration_ms=1000, microvm_seconds=0.0,
        image_pull_bytes=0, build_cache_hit=True, logs_dir=logs,
        trace_path=None, copy_out_root=tmp_path / "out",
        timed_out=timed_out, killed_by_oom=oom,
    )


def test_build_signal_passes_when_exit_zero_no_oom_no_timeout(tmp_path):
    # WHY: BuildSignal.passed is the AND of three observable run conditions —
    #      protects strict-AND from accepting a build that was OOM-killed but
    #      happened to exit zero in a flaky way.
    sig = collect_build_signal(_run(tmp_path, exit_code=0))
    assert sig.passed is True
    assert sig.details["exit_code"] == 0


def test_build_signal_fails_on_nonzero_exit_with_last_log_line(tmp_path):
    sig = collect_build_signal(_run(tmp_path, exit_code=1))
    assert sig.passed is False
    assert sig.details["exit_code"] == 1
    assert sig.details["last_log_line"]  # populated, not empty


def test_build_signal_fails_on_oom_even_if_exit_zero(tmp_path):
    # WHY: docker can report exit_code=0 with OOMKilled=true in race conditions.
    sig = collect_build_signal(_run(tmp_path, exit_code=0, oom=True))
    assert sig.passed is False
    assert sig.details["killed_by_oom"] is True


def test_build_signal_fails_on_timeout(tmp_path):
    sig = collect_build_signal(_run(tmp_path, exit_code=137, timed_out=True))
    assert sig.passed is False
    assert sig.details["timed_out"] is True


def test_build_signal_pure_function_same_inputs_same_blake3(tmp_path):
    # WHY: provenance.inputs_blake3 is the cache key for Phase 9 — must be
    #      deterministic across calls.
    run = _run(tmp_path, exit_code=0)
    a = collect_build_signal(run)
    b = collect_build_signal(run)
    assert a.provenance.inputs_blake3 == b.provenance.inputs_blake3


def test_build_signal_details_only_primitive_value_types(tmp_path):
    # WHY: ADR-0014 — details: dict[str, str | int | bool]; no nested dict, no float.
    sig = collect_build_signal(_run(tmp_path, exit_code=2))
    for k, v in sig.details.items():
        assert isinstance(k, str)
        assert isinstance(v, (str, int, bool))


def test_build_signal_never_raises_on_missing_logs_dir(tmp_path):
    run = _run(tmp_path, exit_code=1)
    # mutate via model_copy with a non-existent path
    run = run.model_copy(update={"logs_dir": tmp_path / "missing"})
    sig = collect_build_signal(run)
    assert sig.passed is False  # collector swallowed the IOError
    assert isinstance(sig, BuildSignal)
```

Mirror this file as `tests/sandbox/test_signals_install.py` with `collect_install_signal` and the `"install"` kind, including the same seven cases.

### Green — make it pass

- Implement helpers in `src/codegenie/sandbox/signals/_common.py` (`_read_last_log_line`, `_inputs_blake3`, `_now`).
- Implement `build.py` and `install.py` each delegating to the helpers; total each ≤ 60 LOC.

### Refactor — clean up

- If the only difference between `build.py` and `install.py` is the signal kind string and the sub-model class, extract a `_collect_simple(run, kind, model_cls)` helper in `_common.py`. Keep public functions short and clearly typed.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/signals/_common.py` | Shared helpers — last-log reader, blake3 of canonical inputs, UTC `now()`. |
| `src/codegenie/sandbox/signals/build.py` | New collector for `"build"` kind. |
| `src/codegenie/sandbox/signals/install.py` | New collector for `"install"` kind. |
| `src/codegenie/sandbox/signals/__init__.py` | Re-export collectors so import-time registration runs. |
| `tests/sandbox/test_signals_build.py` | Red→green tests for build collector. |
| `tests/sandbox/test_signals_install.py` | Red→green tests for install collector. |
| `tests/sandbox/test_signals_registry.py` | Assert `"build"` and `"install"` resolve in the registry. |

## Out of scope

- `collect_test_signal` — S4-02.
- Trace, policy, cve_delta collectors — S4-03.
- The `StrictAndGate` adapter — S4-05.
- `TrustScorer` widening — S4-04.

## Notes for the implementer

1. `details` is `dict[str, str | int | bool]` — Pydantic will reject `float` and nested `dict` at construction. Convert any duration to int milliseconds; convert lists to comma-joined strings if needed.
2. `BuildSignal` and `InstallSignal` are frozen — build a plain dict for `details`, then construct the model once.
3. Both files must execute the `@register_signal_kind` decorator on import. The package `__init__.py` must import them, or first-use of the registry will be empty.
4. Don't peek at logs to infer success — `exit_code`, `timed_out`, `killed_by_oom` are the contract. `last_log_line` is annotation only.
5. `SignalProvenance.collector_version` is a string ("1"), bumped only by an ADR amendment — don't change it casually.
6. Run `tests/schema/test_objective_signals_static.py` locally before pushing; a new banned substring fails the gate CI for the whole repo.
