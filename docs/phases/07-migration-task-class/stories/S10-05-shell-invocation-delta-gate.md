# Story S10-05 — `ShellInvocationDeltaGate` (re-runs shell-trace probe, `count == 0` requirement)

**Step:** Step 10 — `DockerfileBaseImageSwapTransform` + `DockerfileMultiStageRefactorTransform` + three gates
**Status:** Ready
**Effort:** M
**Depends on:** S7-05 (probe-contract conformance + envelope-validation integration test — confirms `ShellInvocationTraceProbe` is registered and emits the `shell_invocation_trace` slice), S6-02 (`SandboxClient.spawn(role: SandboxRole = SandboxRole.GATE)` additive parameter)
**ADRs honored:** [Phase 7 ADR-0002](../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md) (`ShellInvocationTraceProbe` runs in microVM; this gate re-invokes the same probe shape), [Phase 7 ADR-0003](../ADRs/0003-sandbox-role-additive-enum-on-spawn.md) (`SandboxRole.GATE` vs `SandboxRole.PROBE`), [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md) (open `@register_signal_kind` registry)

## Context

`ShellInvocationDeltaGate` is the third of Phase 7's three gate-catalog contributions. Its job: prove the **migrated** distroless image carries **zero shell invocations**. If `DockerfileBaseImageSwapTransform` (S10-01) swapped to a Chainguard distroless base but a stray `RUN`-induced shell command leaked into the runtime stage, this gate catches it deterministically.

The gate runs `ShellInvocationTraceProbe` (S7-02) against the **migrated** image — not the original. The probe was already built in S7-02 to run inside a microVM with eBPF host-side trace capture; this gate invokes the same probe shape against the post-migration artifact. It passes iff `shell_invocations.count == 0`. Any non-zero count is strict-AND fail.

**Important role choice:** like `DistrolessBuildGate` (S10-04), this gate uses `SandboxClient.spawn(role=SandboxRole.GATE)`, **NOT `Role.PROBE`**. Even though the gate's content is "re-run a probe", the call is happening in **gate context** — it's contributing to the trust score, not gathering probe evidence into `RepoContext`. Phase 5 ADR-P5-001's two-chokepoint shape: `run_in_sandbox` is the probe chokepoint; `SandboxClient` is the gate chokepoint. This gate goes through `SandboxClient` even though it's invoking probe-shaped work — the role is `GATE` because the consumer is `TrustScorer`. The eBPF trace capture that `Role.PROBE` adds (S6-02) is NOT needed here — the gate just needs the shell-invocation count from the probe's output slice; the trace-capture machinery already runs inside the microVM as part of the probe's own implementation.

Per arch §Component design §12: `ShellInvocationDeltaGate` is `isolation_class="microvm"`; perf envelope ≤ 30 s (re-runs the heavy probe in microVM); failure outcome → strict-AND fail.

This story ALSO carries the cross-gate **integration test** (`tests/integration/test_gates_register_phase7.py`) that covers ALL THREE Phase 7 gates registering — the canonical Phase 7 §Testing strategy §Integration tests row for this step.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §12` — `ShellInvocationDeltaGate(Gate)` decorated `@register_signal_kind(name="shell_invocation_delta", isolation_class="microvm")`; re-runs `ShellInvocationTraceProbe` against the migrated image; passes iff `shell_invocations.count == 0`; perf envelope ≤ 30 s.
  - `../phase-arch-design.md §Edge cases #2` — `ShellInvocationTraceProbe` finds shell calls in entrypoint (busybox-isms); plugin's match step returns `Applicability.NotApplicable(reason="shell_invocation_not_rewritable")`; HITL with the invocation list. This gate is the migration-side analogue: if the *migrated* image still has shell calls, the migration didn't succeed.
  - `../phase-arch-design.md §Scenarios §Scenario B` — base-image-only happy path: gate stack `DockerfilePolicyGate → DistrolessBuildGate → ShellInvocationDeltaGate` runs strict-AND.
  - `../phase-arch-design.md §Testing strategy §Integration tests` — `tests/integration/test_gates_register_phase7.py` — all three Phase 7 gates register via `@register_signal_kind` and participate in strict-AND scoring.
- **Phase ADRs:**
  - [`../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md`](../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md) — the probe runs in microVM with eBPF trace capture; this gate re-invokes the same shape.
  - [`../ADRs/0003-sandbox-role-additive-enum-on-spawn.md`](../ADRs/0003-sandbox-role-additive-enum-on-spawn.md) — `Role.GATE` is default; this gate uses `Role.GATE` because the consumer is `TrustScorer`, not `RepoContext`.
- **Phase 7 (sibling code):**
  - `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py` (S7-02) — the probe this gate re-invokes; gate consumes the probe's `shell_invocations.count` field.
  - `plugins/distroless-migration--node--npm/recipes/distroless_build_gate.py` (S10-04) — sibling gate; mirror its `@register_signal_kind` shape, its `SandboxClient.spawn(role=Role.GATE)` call, its `BuildFailureReason`-style sum type.
  - `plugins/distroless-migration--node--npm/recipes/dockerfile_policy_gate.py` (S10-03) — sibling gate; mirror its `Passed`/`Failed` Pydantic outcome shape.
- **Existing code:**
  - `plugins/distroless-migration--node--npm/schema/shell_invocation_trace.schema.json` (S7-03) — the probe slice schema this gate validates against.
  - `src/codegenie/sandbox/client.py` — `SandboxClient.spawn(role: SandboxRole = SandboxRole.GATE, ...)`.

## Goal

Land `plugins/distroless-migration--node--npm/recipes/shell_invocation_delta_gate.py`. `ShellInvocationDeltaGate(Gate)` is decorated `@register_signal_kind(name="shell_invocation_delta", isolation_class="microvm")`. It spawns a microVM via `SandboxClient.spawn(role=SandboxRole.GATE, ...)` to re-run `ShellInvocationTraceProbe` against the migrated image (NOT the original). It passes iff the probe's `shell_invocations.count == 0`. Strict-AND `TrustScorer` halts on any non-zero count. p99 ≤ 30 s. ALSO land the cross-gate integration test `tests/integration/test_gates_register_phase7.py` covering all three Phase 7 gates registering.

## Acceptance criteria

### Gate surface + registration

- [ ] **AC-1 — Module + class location.** `plugins/distroless-migration--node--npm/recipes/shell_invocation_delta_gate.py` defines `class ShellInvocationDeltaGate(Gate)`, decorated `@register_signal_kind(name="shell_invocation_delta", isolation_class="microvm")`. After plugin load, `signal_kind_registry["shell_invocation_delta"]` returns this class.
- [ ] **AC-2 — `isolation_class="microvm"`.** Test: `signal_kind_registry["shell_invocation_delta"].isolation_class == "microvm"`.
- [ ] **AC-3 — `Gate` ABC compliance.** `isinstance(g, Gate)` is `True`.

### `SandboxClient.spawn(role=Role.GATE)` — NOT Role.PROBE

- [ ] **AC-4 — Role is `SandboxRole.GATE` (NOT `Role.PROBE`).** Fake-`SandboxClient` test asserts the `role=` kwarg passed to `spawn(...)` is `SandboxRole.GATE`. Document the choice in the gate's docstring: "Even though we re-invoke a probe-shape, the consumer is `TrustScorer`, not `RepoContext`; per ADR-P5-001's two-chokepoint shape, gate context = `Role.GATE`." Rationale: `Role.PROBE` adds host-side eBPF trace capture for context-gathering pipeline; this gate's microVM already runs `strace`-via-eBPF-from-inside as part of the probe's own implementation (S7-02), so no host-side eBPF is needed.

### Re-runs `ShellInvocationTraceProbe` against the **migrated** image

- [ ] **AC-5 — Re-invokes probe shape against migrated image.** The gate's `evaluate(ctx)` reads the migrated image's digest from `ctx` (set by S10-04 `DistrolessBuildGate.Passed.image_digest` propagating through the gate-stack), then spawns the microVM with the migrated image as the target — NOT the original repo's Dockerfile. Test: fake-`SandboxClient` test asserts the `spawn(...)` kwargs include the migrated image's digest (not the source-repo path).
- [ ] **AC-6 — Probe-slice extraction.** The gate parses the probe's output slice (matching the `shell_invocation_trace.schema.json` schema from S7-03), extracts the `shell_invocations.count` integer field. Test: against a fixture probe output with `count == 0` → `Passed`; with `count == 5` → `Failed(shell_invocation_count=5, locations=...)`.

### Pass / fail semantics

- [ ] **AC-7 — `Passed` iff `count == 0`.** Module-level `class ShellInvocationDeltaGatePassed(BaseModel)` (frozen, `extra="forbid"`) with field `image_digest: ImageDigest`, `verified_shell_count: Literal[0]` (the literal-zero is load-bearing — pin the invariant in the type).
- [ ] **AC-8 — `Failed` carries count + locations.** `class ShellInvocationDeltaGateFailed(BaseModel)` (frozen, `extra="forbid"`) with fields: `image_digest: ImageDigest`, `shell_invocation_count: int` (asserted `> 0` by `field_validator`), `locations: tuple[ShellInvocationLocation, ...]` (where `ShellInvocationLocation` is the typed sub-model from S7-02's probe slice — re-imported, not re-defined). Test: a probe output with `count == 3` and three locations → `Failed.locations` carries those three.
- [ ] **AC-9 — Sandbox failure as separate outcome.** If `client.spawn(...)` itself fails (microVM boot failure, network error, probe crash inside VM), return `ShellInvocationDeltaGateFailed(...)` with a typed reason variant — e.g., extend `Failed` with `reason: Literal["non_zero_shell_count", "probe_execution_failed", "sandbox_timeout"]` and a `stderr_tail: str` (≤ 8 KB UTF-8 bytes, NUL/control/bidi rejected, mirrors S10-04). Non-zero shell count is non-retryable (the migration is wrong); probe-execution and timeout are retryable per Phase 5 retry envelope.

### Strict-AND integration

- [ ] **AC-10 — Integration test: all three Phase 7 gates register.** `tests/integration/test_gates_register_phase7.py` is the canonical cross-step integration test:
  - Plugin loads via `loader.load_plugin("distroless-migration--node--npm")`.
  - After load, `signal_kind_registry` has exactly these three new keys: `"dockerfile_policy"`, `"distroless_build"`, `"shell_invocation_delta"`.
  - Each gate's `isolation_class` is correct (`"none"`, `"microvm"`, `"microvm"`).
  - The `TrustScorer` is queried with `required_signals=("dockerfile_policy", "distroless_build", "shell_invocation_delta")` and a scripted-pass scenario produces overall `Pass`; a scripted-fail (any one gate fails) produces overall `Fail`.
  - The test exercises the strict-AND conjunction explicitly: 3-way pass → overall pass; 1-fail-2-pass → overall fail; assertion covers all 2³=8 combinations is overkill — parametrize over the 4 minimal cases (all-pass, each-individual-fail).
- [ ] **AC-11 — No `--allow-policy-violations` flag also covers this gate.** Shared fence `tests/fence/test_no_policy_override_flag.py` (S10-03 AC-10) already enforces this; verify it remains green.

### Audit + diagnostic

- [ ] **AC-12 — `_WARNING_IDS`** `Final[frozenset[str]]` validated at import via `raise AssertionError(...)`. IDs include `shell_invocation_delta.non_zero_count`, `shell_invocation_delta.probe_execution_failed`, `shell_invocation_delta.sandbox_timeout`.
- [ ] **AC-13 — Failing gate emits typed event with locations.** `tests/integration/test_shell_delta_gate_audit_trail.py`: against a fixture migrated image with stray shell invocations (e.g., a misconfigured Dockerfile with `RUN /bin/sh -c "..."` in runtime stage), the spanning log carries `ShellInvocationDeltaGateFailed(image_digest=..., shell_invocation_count=N, locations=(...))`. Operator gets a concrete diagnostic of WHERE the shell calls happen.

### Perf + gates

- [ ] **AC-14 — p99 ≤ 30 s.** `tests/perf/test_shell_invocation_delta_gate.py::test_delta_p99_under_30s` runs the gate 50 times (heavy; small sample). Marked `@pytest.mark.bench` + `@pytest.mark.phase07_e2e`.
- [ ] **AC-15** — `mypy --strict plugins/distroless-migration--node--npm/recipes/` clean.
- [ ] **AC-16** — `ruff check ... && ruff format --check` clean.
- [ ] **AC-17** — `make lint-imports` green.
- [ ] **AC-18** — Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay byte-equal.

## Implementation outline

1. **`plugins/distroless-migration--node--npm/recipes/shell_invocation_delta_gate.py`** — define `ShellInvocationDeltaGatePassed` / `ShellInvocationDeltaGateFailed` Pydantic models; define `ShellInvocationDeltaGate(Gate)` decorated `@register_signal_kind(name="shell_invocation_delta", isolation_class="microvm")`.
2. **`evaluate(ctx)` implementation** —
   - Read migrated image digest from `ctx` (propagated by the gate-stack from `DistrolessBuildGatePassed`).
   - Build sandbox spec: `role=SandboxRole.GATE`, `command=` (the probe's invocation shape — re-use the helper from S7-02 if available; otherwise replicate the command list locally).
   - Call `client.spawn(...)`.
   - On success: parse the probe slice from the spawn result's stdout (or output file — depends on Phase 5/Phase 7 contract); extract `shell_invocations.count` and `locations`.
   - `count == 0` → `Passed`. `count > 0` → `Failed(reason="non_zero_shell_count", ...)`. Spawn failure → `Failed(reason="probe_execution_failed" | "sandbox_timeout", ...)`.
3. **Re-import `ShellInvocationLocation` from S7-02's probe module** (or from the probe-slice Pydantic models) — DO NOT re-define. Single source of truth.
4. **`tests/unit/gates/test_shell_invocation_delta_gate.py`** — fake-`SandboxClient` covering AC-4..AC-9.
5. **`tests/integration/test_gates_register_phase7.py`** — the canonical cross-step integration test (AC-10). Three signal kinds registered; strict-AND conjunction across them.
6. **`tests/integration/test_shell_delta_gate_audit_trail.py`** — typed event flows to spanning log (AC-13).
7. **`tests/perf/test_shell_invocation_delta_gate.py`** — bench (AC-14).

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/integration/test_gates_register_phase7.py`

```python
"""Canonical Phase 7 integration test: all three gates register and participate in strict-AND."""

import pytest

from codegenie.plugins.loader import load_plugin
from codegenie.sandbox.gates.registry import signal_kind_registry


@pytest.fixture(autouse=True)
def _reset_registry(monkeypatch):
    # Fresh registry per test — mirrors S2-05 provenance_registry_reset pattern
    snapshot = dict(signal_kind_registry)
    yield
    signal_kind_registry.clear()
    signal_kind_registry.update(snapshot)


def test_all_three_phase7_gates_register_after_plugin_load() -> None:
    load_plugin("distroless-migration--node--npm")
    assert "dockerfile_policy" in signal_kind_registry
    assert "distroless_build" in signal_kind_registry
    assert "shell_invocation_delta" in signal_kind_registry


def test_isolation_classes_are_correct() -> None:
    load_plugin("distroless-migration--node--npm")
    assert signal_kind_registry["dockerfile_policy"].isolation_class == "none"
    assert signal_kind_registry["distroless_build"].isolation_class == "microvm"
    assert signal_kind_registry["shell_invocation_delta"].isolation_class == "microvm"


@pytest.mark.parametrize(
    "scenario,expected_overall",
    [
        # (dockerfile_policy_pass, distroless_build_pass, shell_delta_pass), expected
        ((True, True, True), "pass"),
        ((False, True, True), "fail"),
        ((True, False, True), "fail"),
        ((True, True, False), "fail"),
    ],
)
def test_strict_and_conjunction_across_phase7_gates(scenario, expected_overall) -> None:
    """ADR-0012 + Phase 5 ADR-0003: any failing gate fails the conjunction."""
    from codegenie.sandbox.trust_scorer import TrustScorer
    load_plugin("distroless-migration--node--npm")
    scorer = TrustScorer.with_scripted_signals({
        "dockerfile_policy": scenario[0],
        "distroless_build": scenario[1],
        "shell_invocation_delta": scenario[2],
    })
    result = scorer.score(required_signals=("dockerfile_policy", "distroless_build", "shell_invocation_delta"))
    assert result.kind == expected_overall
```

Test file path: `tests/unit/gates/test_shell_invocation_delta_gate.py`

```python
from dataclasses import dataclass, field
from typing import Any
import pytest

from codegenie.sandbox import SandboxRole

from plugins.distroless_migration__node__npm.recipes.shell_invocation_delta_gate import (
    ShellInvocationDeltaGate,
    ShellInvocationDeltaGateFailed,
    ShellInvocationDeltaGatePassed,
)


@dataclass
class _FakeSandboxRun:
    exit_code: int
    probe_slice_json: str = '{"shell_invocations": {"count": 0, "locations": []}}'


@dataclass
class _FakeSandboxClient:
    scripted: list[_FakeSandboxRun]
    received: list[dict[str, Any]] = field(default_factory=list)

    def spawn(self, **kwargs: Any) -> _FakeSandboxRun:
        self.received.append(kwargs)
        return self.scripted.pop(0)


def test_uses_role_gate_not_probe() -> None:
    client = _FakeSandboxClient(scripted=[_FakeSandboxRun(exit_code=0)])
    gate = ShellInvocationDeltaGate(client=client)
    gate.evaluate(image_digest="sha256:" + "a" * 64)
    assert client.received[0]["role"] == SandboxRole.GATE


def test_count_zero_is_passed() -> None:
    client = _FakeSandboxClient(scripted=[_FakeSandboxRun(exit_code=0)])
    gate = ShellInvocationDeltaGate(client=client)
    result = gate.evaluate(image_digest="sha256:" + "a" * 64)
    assert isinstance(result, ShellInvocationDeltaGatePassed)
    assert result.verified_shell_count == 0


def test_count_nonzero_is_failed_with_locations() -> None:
    probe_out = (
        '{"shell_invocations": {"count": 3, '
        '"locations": [{"layer": "sha256:abc", "command": "sh"}, '
        '{"layer": "sha256:def", "command": "bash"}, '
        '{"layer": "sha256:ghi", "command": "/bin/sh"}]}}'
    )
    client = _FakeSandboxClient(scripted=[_FakeSandboxRun(exit_code=0, probe_slice_json=probe_out)])
    gate = ShellInvocationDeltaGate(client=client)
    result = gate.evaluate(image_digest="sha256:" + "a" * 64)
    assert isinstance(result, ShellInvocationDeltaGateFailed)
    assert result.shell_invocation_count == 3
    assert len(result.locations) == 3


def test_sandbox_timeout_is_retryable_failure() -> None:
    client = _FakeSandboxClient(scripted=[_FakeSandboxRun(exit_code=124)])  # timeout convention
    gate = ShellInvocationDeltaGate(client=client)
    result = gate.evaluate(image_digest="sha256:" + "a" * 64)
    assert isinstance(result, ShellInvocationDeltaGateFailed)
    assert result.reason == "sandbox_timeout"


def test_passed_pins_count_zero_literal() -> None:
    from typing import get_type_hints, Literal
    hints = get_type_hints(ShellInvocationDeltaGatePassed)
    assert hints["verified_shell_count"] == Literal[0]
```

State why it fails: `ModuleNotFoundError` — neither the gate module nor the integration-test fixtures exist yet.

### Green — minimal pass

- Land `shell_invocation_delta_gate.py` with the two Pydantic outcome models (`Passed` has `verified_shell_count: Literal[0]`), `ShellInvocationDeltaGate(Gate)` decorated `@register_signal_kind(...)`.
- Implement `evaluate(image_digest)` that builds the spawn-spec, calls `client.spawn(role=SandboxRole.GATE, ...)`, parses the JSON probe slice from stdout, and routes to `Passed`/`Failed`.
- Land `tests/integration/test_gates_register_phase7.py` covering all three gates (depends on S10-03 + S10-04 being shipped; this story is the integration-stitch).

### Refactor

- Hoist `_parse_probe_slice(json_str: str) -> tuple[int, tuple[ShellInvocationLocation, ...]]` as a pure helper; test in isolation over malformed JSON, missing fields, count-but-no-locations etc.
- Pin `_REASON_CLASSIFIER: Final[tuple[tuple[Pattern[str], str], ...]]` for stderr-to-reason mapping (mirror S10-04's `_FAILURE_PATTERNS`).
- Re-import `ShellInvocationLocation` from S7-02's probe module — confirm single-source via the AST-walk fence (`tests/fence/test_shell_delta_gate_reimports_location.py` asserts the import path).
- Add `_WARNING_IDS` import-time validation.
- Confirm `mypy --strict` clean — the `Literal[0]` on `verified_shell_count` should be inferred correctly.

## Files to touch

| Path | Why |
|---|---|
| `plugins/distroless-migration--node--npm/recipes/shell_invocation_delta_gate.py` | NEW — `ShellInvocationDeltaGate(Gate)` + Pydantic outcome models; `@register_signal_kind(name="shell_invocation_delta", isolation_class="microvm")`; uses `SandboxClient.spawn(role=Role.GATE)`. |
| `plugins/distroless-migration--node--npm/recipes/__init__.py` | Extend — additive import line for side-effect registration. |
| `tests/unit/gates/test_shell_invocation_delta_gate.py` | NEW — fake-`SandboxClient` covering AC-4..AC-9. |
| `tests/integration/test_gates_register_phase7.py` | NEW — canonical cross-step integration: all three gates register and participate in strict-AND (AC-10). |
| `tests/integration/test_shell_delta_gate_audit_trail.py` | NEW — typed event flows to spanning log (AC-13); `@pytest.mark.phase07_e2e`. |
| `tests/fence/test_shell_delta_gate_reimports_location.py` | NEW — AST-walk asserts `ShellInvocationLocation` is imported (not re-defined). |
| `tests/perf/test_shell_invocation_delta_gate.py` | NEW — p99 ≤ 30 s bench (AC-14); `@pytest.mark.bench` + `@pytest.mark.phase07_e2e`. |

## Out of scope

- **`ShellInvocationTraceProbe` itself** — S7-02. This story re-invokes it from gate context; the probe module is unchanged.
- **`DockerfilePolicyGate`** — S10-03. Co-equal sibling gate.
- **`DistrolessBuildGate`** — S10-04. Co-equal sibling gate; this gate runs AFTER it (the migrated image digest comes from `DistrolessBuildGatePassed`).
- **`SandboxClient.spawn` role parameter wiring** — S6-02.
- **Phase 8 `MultiPluginCoordinator`** — Phase 7 ADR-0001 defers this; Phase 7 just emits evidence.

## Notes for the implementer

- **`Role.GATE` — NOT `Role.PROBE`.** Despite re-invoking probe-shaped work, this is gate context. The consumer is `TrustScorer`, not `RepoContext`. ADR-P5-001's two-chokepoint shape: `run_in_sandbox` is the probe chokepoint (`Role.PROBE` adds host-side eBPF for that chokepoint); `SandboxClient.spawn` is the gate chokepoint (`Role.GATE` is the default). The probe itself already runs its in-VM trace capture when invoked — we don't need host-side eBPF on top. AC-4 is the mechanical enforcement; document the choice with an ADR-0003 + ADR-P5-001 citation in the gate's docstring.
- **`verified_shell_count: Literal[0]` is load-bearing.** Pinning the count to the literal `0` in the `Passed` type makes "passed but count was 5" type-illegal — the strict-AND invariant lives in the type, not in runtime checks. `mypy --strict` would catch a regression where someone tries to construct `Passed(verified_shell_count=5)`. Production ADR-0033 (Domain modeling discipline): make illegal states unrepresentable.
- **Re-invoke `ShellInvocationTraceProbe`'s shape; do NOT re-define it.** S7-02 already ships the probe with its sandbox-spawn shape, its probe-slice schema, its `ShellInvocationLocation` Pydantic. Import-and-call, don't fork. If the probe's invocation shape is parametric on "what image to trace", expose that via a helper in S7-02's module that this gate calls. Otherwise the trace logic drifts between probe-context (S7-02) and gate-context (this story), which is exactly the kind of duplication that bites later.
- **The migrated image digest comes from `DistrolessBuildGatePassed.image_digest`** — S10-04. Phase 5's gate-stack contract is that gate outputs propagate to subsequent gates via a typed bag (ctx). Read the digest from there; do NOT re-build the image (`DistrolessBuildGate` already did). If the digest is missing from ctx (because `DistrolessBuildGate` was skipped), return `Failed(reason="missing_migrated_image_digest")` honestly — don't paper over with a sentinel.
- **JSON-from-stdout vs JSON-from-file** — Phase 5/Phase 7 contract for "how a probe slice gets out of the sandbox" may be: (a) stdout, (b) a mounted output file, (c) an event-log entry. Pick whichever S7-02 ships; mirror its shape. If S7-02 uses output file, mount the same path; if stdout, parse stdout. Don't invent a third shape.
- **`tests/integration/test_gates_register_phase7.py` is the canonical fence for ALL THREE Phase 7 gates.** Even though it's filed under this story (S10-05), it asserts S10-03's `dockerfile_policy`, S10-04's `distroless_build`, AND this story's `shell_invocation_delta`. If S10-03 or S10-04 hasn't shipped yet, this test fails — that's the cross-step integration check. The story should NOT be marked GREEN until all three gates pass the test.
- **Strict-AND conjunction is 4 parametrized cases, not 8.** AC-10's parametrization covers the minimal cases: all-pass, each individual fail. The 4 remaining 2-fail / 3-fail cases are degenerate (already implied by 1-fail-fails-overall). Don't over-parametrize.
- **Locations matter for operator diagnostic.** Edge case #2 names the operator experience: when a migration leaves shell calls, the operator needs to see WHERE (which layer, which command). The `locations` tuple on `Failed` is the answer. Make sure the audit-trail integration test (AC-13) asserts not just the count but the locations list.
- **Mirror S10-04's shape.** Sibling gate; same role choice; same `isolation_class`; same Pydantic outcome model pattern; same `_WARNING_IDS` validation; same stderr-tail truncation discipline (8 KB UTF-8 bytes). Convention > taste (global Rule 11).
- **`isinstance(result, ShellInvocationDeltaGateFailed)` then `result.reason == "..."` is the dispatch shape** — not a separate sum-type-discriminated union (the `Passed` and `Failed` classes are themselves the discrimination). Don't introduce a `class Reason(StrEnum)` if a `Literal[...]` field on `Failed` does the job. S10-04 went with a `StrEnum` for `BuildFailureReason` (4 reasons); this gate has 3 reasons — `Literal["non_zero_shell_count", "probe_execution_failed", "sandbox_timeout"]` is fine, but pick one shape consistent with S10-04 if cross-gate uniformity matters.
- **Performance — ≤ 30 s.** This is the heaviest gate (re-runs the heavy probe in microVM). Don't try to optimize by caching probe results across gate invocations — the migrated image is what we're trusting; re-trace it fresh each time. If the bench fails, the issue is likely microVM boot time (Phase 5's territory) or probe runtime (S7-02's territory), not this gate.
