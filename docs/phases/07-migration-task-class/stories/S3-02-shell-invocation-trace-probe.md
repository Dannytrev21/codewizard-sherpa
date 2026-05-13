# Story S3-02 — `ShellInvocationTraceProbe` gate-time probe + strace sibling sidecar

**Step:** Step 3 — Land `BaseImageProbe`, `ShellInvocationTraceProbe`, and the four signal collectors
**Status:** Ready
**Effort:** L
**Depends on:** S2-04, S2-07
**ADRs honored:** ADR-P7-001 (`@register_gate_probe` registry), ADR-P7-005 (Phase 2 `RuntimeTraceProbe` stub preserved forever), ADR-P7-006 (`RuntimeTraceProbe` stub kept; this is the sibling new file), ADR-0013 (gate-time strace in Phase 5 chokepoint; 30 s budget; sidecar pattern), ADR-0008 (facts, not judgments)

## Context

This is the single gate-time probe Phase 7 introduces — the empirical validator that the candidate (post-recipe) image's entrypoint does **not** invoke a shell at runtime. It registers via the new `@register_gate_probe` decorator (ADR-P7-001 / S1-01), runs inside Phase 5's `run_in_sandbox` chokepoint, and emits a `ShellInvocationTrace` Pydantic model that the S3-05 `ShellInvocationTraceSignal` collector projects into `ObjectiveSignals.shell_invocation_trace`.

The load-bearing design call (ADR-0013 + arch Gap 4) is that **strace runs in a sibling sidecar container**, not as an ENTRYPOINT wrapper. The sidecar PID-namespace-shares with the candidate via `docker run --pid=container:<candidate> codegenie-strace-sidecar:<pinned-digest>` — this keeps the candidate's PID 1 as its own entrypoint (preserves signal handling) and works on Chainguard distroless images that don't ship strace by construction. The sibling pattern + 30 s budget is the test the Step 3 integration story (S3-03) exercises explicitly.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design ›2. ShellInvocationTraceProbe` — purpose, ABC shape, internal structure (the four-step internal flow), performance envelope, failure behavior.
  - `../phase-arch-design.md §Gap 4` — sidecar PID-share design; why ENTRYPOINT-wrapping is rejected (alters PID 1, signal handling); `--pid=container:<candidate>` pattern.
  - `../phase-arch-design.md §Data model ›Contracts` — `ShellInvocationTrace` Pydantic shape (`candidate_image_digest`, `scenarios_run`, `runtime_shell_count: int | None`, `traced_binaries`, `network_endpoints_touched`, `wall_clock_ms`, `budget_ms: int = 30000`, `confidence`, `confidence_reasons`).
  - `../phase-arch-design.md §Edge cases` — row 5 (budget exhaust → `confidence=medium`, `entrypoint_steady=False`, `runtime_shell_count=None`).
  - `../phase-arch-design.md §Testing strategy ›Unit tests` — second bullet enumerates the ≥10 tests including the intent test and sanitizer Pass 5 check.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-register-gate-probe-new-registry.md` — ADR-P7-001 — register via `@register_gate_probe`, not Phase 2's `@register_probe`. The Phase 2 coordinator must remain unaware.
  - `../ADRs/0013-shell-trace-runs-gate-time-in-phase5-chokepoint.md` — ADR-P7-013 — gate-time only; 30 s budget; sidecar pattern; `--network=none` workload.
  - `../ADRs/0006-runtime-trace-probe-stub-kept-forever.md` — ADR-P7-005 — Phase 2 `RuntimeTraceProbe` stub stays as `applies() = False` no-op; this probe is a *sibling new file*, not a replacement.
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — facts-not-judgments lineage for the intent test.
- **Production ADRs:**
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — `Probe` ABC byte-stable; import verbatim.
  - `../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md` — chokepoint reused; no new sandbox profile.
- **Existing code:**
  - `src/codegenie/probes/base.py` — Phase 2 `Probe` ABC.
  - `src/codegenie/probes/gate_registry.py` — `@register_gate_probe` (S1-01).
  - `src/codegenie/tools/strace.py` — strace subprocess wrapper from S2-04.
  - `src/codegenie/tools/buildkit.py` — `docker buildx build` wrapper from S2-02.
  - `src/codegenie/tools/digests.yaml` — `sandbox.strace`, `sandbox.strace_sidecar`, `gate.shell_trace.budget_s=30` keys landed in S2-07.

## Goal

`@register_gate_probe class ShellInvocationTraceProbe(Probe)` lives at `src/codegenie/probes/shell_invocation_trace.py`, registers on the **gate** registry (not Phase 2's), launches strace in a sibling sidecar via `docker run --pid=container:<candidate>` with a configurable 30 s budget, and emits a Pydantic `ShellInvocationTrace` that contains **facts only** — no field name expresses a judgment.

## Acceptance criteria

- [ ] `src/codegenie/probes/shell_invocation_trace.py` exists; `ShellInvocationTraceProbe` decorated with `@register_gate_probe` from `codegenie.probes.gate_registry`; **not** `@register_probe`.
- [ ] `name = "shell_invocation_trace"`, `applies_to_tasks = ["distroless_migration"]`, `applies_to_languages = ["*"]`, `declared_inputs = ["__image_digest__:<candidate>", "**/test/scenarios/*.yaml"]`, `timeout_seconds = 30`.
- [ ] `all_gate_probes()` returns a tuple containing exactly this probe (after S3-01 + S3-02 import); Phase 2 `all_probes()` does **not** contain it — both asserted by unit test.
- [ ] `ShellInvocationTrace` Pydantic model with `extra="forbid"`, `frozen=True`, `schema_version: Literal["v0.7.0"]` and the field set from `phase-arch-design.md §Data model ›Contracts`.
- [ ] **Intent test** `test_shell_trace_emits_facts_not_judgments` asserts no field name on `ShellInvocationTrace` matches `^(is_|safe_|recommended_).*`.
- [ ] ≥10 unit tests in `tests/unit/probes/test_shell_invocation_trace.py`: mocked strace `execve` event stream → `runtime_shell_count`; budget-exhaust path → `confidence="medium"`, `entrypoint_steady=False`, `runtime_shell_count=None`; observed shell (`/bin/sh` in `execve`) → `runtime_shell_count > 0`; sidecar invocation uses `--pid=container:<candidate>` (asserted via mocked subprocess args); workload `docker run` includes `--network=none`, `--cap-drop=ALL`, `--read-only`, `--pids-limit=64`, `--memory=512m`; sanitizer Pass 5 strips prompt-injection markers from raw trace bytes; `applies_to_tasks` matrix; budget config read from `tools/digests.yaml#gate.shell_trace.budget_s` (env override > digests.yaml > default-30); registration on gate registry only; the intent test.
- [ ] `mypy --strict src/codegenie/probes/shell_invocation_trace.py` and `ruff check`/`ruff format --check` clean.
- [ ] Fence-CI denies LLM-SDK imports under `probes/` — exercised in S1-08; this file imports none.
- [ ] Phase 2 `RuntimeTraceProbe.applies() == False` still holds (ADR-P7-005 — unit-asserted via existing Phase 2 test imported here as a regression guard).

## Implementation outline

1. Scaffold `src/codegenie/probes/shell_invocation_trace.py`. Import `Probe` from `.base`, `register_gate_probe` from `.gate_registry`.
2. Define `ShellInvocationTrace` Pydantic model with the contract shape — `runtime_shell_count: int | None` (None when `confidence != "high"`), `budget_ms: int = 30000`, `confidence_reasons: list[str]`.
3. Implement `applies(view) -> bool` — `True` iff `view.task_type == "distroless_migration"` AND the candidate image digest is present in `view` (gate-time inputs).
4. Implement `run(view) -> ShellInvocationTrace`:
   - Read budget from `tools.digests.get("gate.shell_trace.budget_s", default=30)`.
   - Resolve candidate digest from the view.
   - Launch sibling sidecar via `tools.strace.run_in_sidecar(candidate_digest=..., scenarios=..., budget_s=..., sidecar_image=tools.digests.get("sandbox.strace_sidecar"))` — wrapper from S2-04.
   - Parse `execve` events into `runtime_shell_count`, `traced_binaries`, `network_endpoints_touched` (always empty given `--network=none`; field kept for forward compat per ADR-0013).
   - On `subprocess.TimeoutExpired`: return `ShellInvocationTrace(confidence="medium", runtime_shell_count=None, entrypoint_steady=False, confidence_reasons=["budget_exhausted"])`.
   - Confidence: `"high"` if entrypoint reached steady-state under budget; else `"medium"`.
5. Sanitizer Pass 5 hook: when reading raw trace bytes, route through `tools.strace.sanitize_pass5(raw_bytes)` (S2-04) — strips prompt-injection markers from `LABEL`/`RUN`-derived strings before storing in `traced_binaries`.
6. Register via `@register_gate_probe` decorator.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/test_shell_invocation_trace.py`

The load-bearing red test is registration + intent:

```python
# tests/unit/probes/test_shell_invocation_trace.py
import re
from codegenie.probes.gate_registry import all_gate_probes
from codegenie.probes import all_probes as phase2_all_probes
from codegenie.probes.shell_invocation_trace import ShellInvocationTrace, ShellInvocationTraceProbe

JUDGMENT_RE = re.compile(r"^(is_|safe_|recommended_).*")

def test_registers_on_gate_registry_only():
    # arrange: imports above have triggered registration
    # act
    gate_names = {p.name for p in all_gate_probes()}
    phase2_names = {p.name for p in phase2_all_probes()}
    # assert
    assert "shell_invocation_trace" in gate_names
    assert "shell_invocation_trace" not in phase2_names, (
        "ShellInvocationTraceProbe must NOT appear on Phase 2 registry (ADR-P7-001)."
    )

def test_shell_trace_emits_facts_not_judgments():
    # arrange + act
    field_names = list(ShellInvocationTrace.model_fields.keys())
    offenders = [f for f in field_names if JUDGMENT_RE.match(f)]
    # assert
    assert offenders == [], (
        f"ShellInvocationTraceProbe outputs must be facts, not judgments "
        f"(ADR-0008 / Rule 9); offenders: {offenders}"
    )
```

This fails at import (`ImportError`) until the module exists. Commit red.

Additional ≥8 tests (one per behavior):

```python
def test_budget_exhaust_returns_confidence_medium(monkeypatch): ...
def test_runtime_shell_count_zero_when_entrypoint_clean(monkeypatch): ...
def test_runtime_shell_count_positive_when_bin_sh_observed(monkeypatch): ...
def test_sidecar_invocation_uses_pid_container_share(monkeypatch): ...  # asserts --pid=container:<digest>
def test_workload_runs_with_network_none_and_cap_drop_all(monkeypatch): ...
def test_sanitizer_pass5_strips_injection_markers(monkeypatch): ...
def test_applies_to_tasks_only_distroless(): ...
def test_budget_config_precedence(monkeypatch, tmp_path): ...   # env > digests.yaml > 30
def test_runtime_trace_probe_stub_still_applies_false(): ...    # ADR-P7-005
```

### Green — make it pass

Smallest implementation: define the Pydantic model with the contract field set (no judgment-named fields), then implement `applies` + `run` over `tools.strace.run_in_sidecar` (mocked in unit tests). Use `monkeypatch.setattr` on the strace wrapper to drive the four event-stream paths.

### Refactor — clean up

- Type hints (`mypy --strict`).
- Docstrings on `ShellInvocationTraceProbe.run` linking ADR-0013.
- Lift the sidecar argument construction (`--pid=container:...`, `--network=none`, `--cap-drop=ALL`, `--read-only`, `--pids-limit=64`, `--memory=512m`) into a small helper so the sidecar-args unit test is one-line.
- Structured-log entry: `sandbox.spawn` on sidecar launch, `sandbox.exit` on completion (per `phase-arch-design.md §Harness engineering`); never log raw trace bytes — they go to `raw/scenarios/*.trace.log` only.
- Confirm `RuntimeTraceProbe.applies() is False` in a guard test imported from Phase 2 (ADR-P7-005).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/shell_invocation_trace.py` | New — implements `ShellInvocationTraceProbe` + `ShellInvocationTrace` per Component 2 + ADR-0013. |
| `tests/unit/probes/test_shell_invocation_trace.py` | New — ≥10 unit tests incl. registration, intent, sidecar-args, budget-exhaust, sanitizer, RuntimeTraceProbe guard. |
| `src/codegenie/probes/__init__.py` | Additive import line so registration fires at package import time. |

## Out of scope

- **`tools/strace.py` itself** — S2-04. This story consumes the wrapper.
- **`tools/digests.yaml` keys** — added in S2-07; this story reads them.
- **Sidecar PID-share integration test on real Docker** — S3-03 (`test_strace_sidecar_pid_share.py` + `test_strace_idempotent.py`).
- **`ShellInvocationTraceSignal` collector** — S3-05; this story produces the probe output; the gate-time strict-AND projection is a separate file.
- **`ObjectiveSignals` widening** — S1-02.
- **Empirical 30 s budget calibration under real workloads** — S7-04 (`test_strace_budget_distribution.py`).
- **Phase 5 chokepoint integration** — composed in S5-03/S5-04 (`validate_in_sandbox` node).
- **Chainguard-distroless strace sidecar image migration** — Phase 16; this story uses the Alpine sidecar pinned in `digests.yaml#sandbox.strace_sidecar`.

## Notes for the implementer

- The single most-easily-missed property is `--pid=container:<candidate>`. If you ENTRYPOINT-wrap the candidate (run `strace candidate-entrypoint`), PID 1 becomes strace, signal handling changes, and the integration test S3-03 fails. The sibling sidecar pattern is non-negotiable (ADR-0013 + Gap 4).
- Budget configuration precedence (per `phase-arch-design.md §Harness engineering ›Configuration`): CLI flag > env var > `tools/digests.yaml` > hardcoded default (30). The unit test must cover at least env > digests > default; CLI-flag plumbing is composed in S5-05.
- `network_endpoints_touched` is always `[]` because the workload runs `--network=none`. Keep the field anyway (ADR-0013 — forward compatibility for future non-isolated probes).
- `runtime_shell_count: int | None` — `None` is *only* valid when `confidence != "high"`. The strict-AND collector in S3-05 collapses `confidence != "high" OR runtime_shell_count != 0` to `passed=False`; this probe must never set `count=None` with `confidence="high"` (assert that invariant in the model `@model_validator` or in `run`).
- Sanitizer Pass 5 is shared with Phase 4 (`final-design.md §Component-2`). Import from `tools.strace.sanitize_pass5` — do not re-implement.
- Phase 2's `RuntimeTraceProbe` (`src/codegenie/probes/runtime_trace.py`) stays in the registry forever as `applies() = False` (ADR-P7-005). Do not import it, do not delete it, do not rename your probe to collide with its name.
- The intent test is the load-bearing facts-vs-judgments check. Anything that smells like `is_distroless_safe` or `recommended_action` should live in the planner (S5-x), not here.
