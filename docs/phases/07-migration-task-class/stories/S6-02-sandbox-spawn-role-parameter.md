# Story S6-02 — `SandboxClient.spawn(role=SandboxRole.GATE)` additive parameter

**Step:** Step 6 — Phase 5 `SandboxRole` additive enum + `SandboxClient.spawn(role=...)` amendment
**Status:** Ready
**Effort:** S
**Depends on:** S6-01 (the `SandboxRole` enum must exist), S5-01 (byte-edit allowlist row #6 must be in place)
**ADRs honored:** Phase 7 ADR-0003 (primary), Phase 7 ADR-0009 (allowlist row #6 — second half), Phase 7 ADR-0002 (consumer), Phase 7 ADR-0001 (no parallel `probe-control` process), Phase 5 ADR-0001 (two-chokepoint sandbox seam)

## Context

S6-01 ships `SandboxRole(str, Enum)` with `GATE` and `PROBE` members. This story is the second half of the Phase 5 amendment: `SandboxClient.spawn(...)` gains exactly one new keyword parameter — `role: SandboxRole = SandboxRole.GATE` — and the role drives a small, well-defined behavior diff:

- `Role.GATE` (the default) preserves **byte-identical** existing Phase 5 behavior: same microVM topology, same audit-log fields the prior version emitted, no additional capture overhead.
- `Role.PROBE` boots the **same microVM topology** plus (a) eBPF host-side trace capture and (b) a short container boot (so `ShellInvocationTraceProbe`'s `docker buildx build` has a runtime container to observe, not just an idle VM). This is the topology ADR-0002 §Decision binds.

The load-bearing claim is **byte-identity on the default path**: every existing Phase 5 callsite (`Gate.evaluate(...)` consumers, the test suite, integration tests) must continue to work without source-code changes. The default-arg value is what makes this safe — but it also means a careless edit (e.g., changing the default to `Role.PROBE`, or removing the default) would silently shift every existing caller's behavior. The fence in S5-01 catches *structural* drift (the file content); this story's tests catch *behavioral* drift (the default path's audit-log fields and topology).

ADR-0003 §Consequences row 1 says "the change is exactly two lines (one signature, one default)." This story honors that: the `class SandboxRole` block from S6-01 plus this story's parameter addition together exhaust S5-01's allowlist row #6 for `src/codegenie/sandbox/client.py`. No other byte-edit is permitted.

This story does **not** include the microVM-boot-and-eBPF-trace integration proof (`tests/integration/test_sandbox_client_role_probe.py`); that's S6-03. This story covers the signature, the default-arg semantics, the dispatch logic that routes `role` to topology, and the audit-log `role` field.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §Component design §9 (ShellInvocationTraceProbe)`](../phase-arch-design.md) — the consumer's exact call shape: `spawn(role=Role.PROBE, workspace=..., command=[...], capture_trace=True)`.
  - [`../phase-arch-design.md §Process view`](../phase-arch-design.md) — sequence diagram lines `spawn(role=Role.GATE)` (Gate path) and `spawn(role=Role.PROBE)` (probe path).
  - [`../phase-arch-design.md §Tradeoffs (consolidated)`](../phase-arch-design.md) — row "Phase 5 `SandboxClient.spawn(...)` gains one `role: SandboxRole` parameter".
- **Phase ADRs:**
  - [`../ADRs/0003-sandbox-role-additive-enum-on-spawn.md`](../ADRs/0003-sandbox-role-additive-enum-on-spawn.md) — primary; §Decision, §Tradeoffs, §Consequences (the two-line rule), §Reversibility (fallback semantics).
  - [`../ADRs/0009-phase-7-byte-edit-allowlist-fence.md`](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — row #6: "`src/codegenie/sandbox/client.py` — exactly one new `role: SandboxRole = Role.GATE` parameter on `spawn(...)`." S6-01 + S6-02 together exhaust this row.
  - [`../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md`](../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md) — the consumer; explains what `Role.PROBE` *means* operationally.
  - [`../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md`](../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md) — context for why we resist parallel control-plane processes.
- **Source design:**
  - [`../final-design.md §Lens summary §2`](../final-design.md) + [`§Synthesis ledger departure #3`](../final-design.md) — the synthesis position.
  - [`../final-design.md §Risks #1`](../final-design.md) — the fallback if Phase 5 rejects (route `Role.PROBE` through `Role.GATE` semantics; emit a warning).
- **Phase 5 context:**
  - [`../../05-sandbox-trust-gates/final-design.md §Components §1 SandboxClient`](../../05-sandbox-trust-gates/final-design.md) — the existing `SandboxClient` surface that grows by exactly one parameter.
  - [`../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md`](../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md) — the seam.
- **High-level impl:**
  - [`../High-level-impl.md §Step 6`](../High-level-impl.md) — Features delivered bullet 2 + done criterion "every existing Phase 5 callsite byte-unchanged."

## Goal

Amend `SandboxClient.spawn(...)` with exactly one additive keyword parameter — `role: SandboxRole = SandboxRole.GATE` — wired so that:

1. **Every existing Phase 5 callsite is byte-unchanged.** The default-arg path produces identical observable behavior (same microVM topology, same audit-log fields, same exit codes, same `SandboxRun` shape) as the pre-amendment version.
2. **`spawn(role=SandboxRole.PROBE, ..., capture_trace=True)`** boots the same microVM topology *plus* enables eBPF host-side trace capture *plus* the short container boot ADR-0002 §Decision requires.
3. The audit-log event for every `spawn(...)` call carries an additive `role: "gate" | "probe"` field; existing audit-log consumers tolerate the new field per Phase 5's `extra="forbid"` discipline being expanded by ADR-0003 §Consequences row 3.
4. The signature is the **only** byte-edit beyond S6-01's enum block. The byte-edit allowlist fence (S5-01 row #6) shows `client.py` carrying exactly: (a) the `class SandboxRole` block from S6-01, (b) this story's `role: SandboxRole = SandboxRole.GATE` parameter addition, (c) the dispatch wire-up that interprets the parameter. Nothing else.

## Acceptance criteria

### A. Signature surface

- [ ] `inspect.signature(SandboxClient.spawn)` returns a `Parameter` named `role` with default `SandboxRole.GATE` and annotation `SandboxRole`. The parameter is keyword-only (declared after a `*` in the signature) so a positional misuse is a `TypeError`.
- [ ] No other parameters on `spawn(...)` change name, default, kind, or annotation. A unit test snapshots the full `inspect.signature(spawn).parameters` map post-amendment against the pre-amendment shape *plus* the one new `role` parameter; any other diff fails CI.
- [ ] `mypy --strict src/codegenie/sandbox/` is clean.

### B. Default-path byte-identity (the load-bearing claim)

- [ ] **`client.spawn(...)` without `role=...` produces a `SandboxRun` byte-equal to a synthetic pre-amendment baseline** captured as `tests/golden/sandbox/spawn_default_run.json` (recorded once during this story; the test asserts byte-equality going forward). Fields snapshotted: `backend`, `gate_isolation_class`, `duration_ms is None or >= 0`, `audit_events[*].kind`, `audit_events[*].role`, exit status. (Time-dependent fields like `started_at` are normalized to a sentinel before comparison.)
- [ ] `client.spawn(role=SandboxRole.GATE)` produces a result byte-equal to `client.spawn()` (default arg). A property-style test asserts the equivalence across a 5-spec parameter sweep (different `command`, `workspace`, `env`, `time_budget_seconds`, `network` values).
- [ ] **Every Phase 5 production callsite in the codebase is grep-verified to NOT pass `role=` explicitly.** A unit test scans `src/codegenie/` (excluding `src/codegenie/sandbox/`) and `plugins/vulnerability-remediation--node--npm/` for the string `spawn(` and asserts no occurrence is followed by a `role=` kwarg. (Phase 7 plugins under `plugins/distroless-migration--*/` are exempt — those are the only legitimate `role=Role.PROBE` callers, landed in S7-02 + S10-04 + S10-05.)
- [ ] **Phase 5's existing test suite is green with zero new test skips.** `pytest tests/unit/sandbox/ tests/integration/test_sandbox_*.py` exits 0 on the post-story branch.

### C. `Role.PROBE` topology behavior

- [ ] `client.spawn(role=SandboxRole.PROBE, ..., capture_trace=True)` returns a `SandboxRun` whose `audit_events` contain at least one event with `role == "probe"`.
- [ ] When `role == SandboxRole.PROBE` and `capture_trace=True`, the underlying backend dispatcher is invoked with eBPF-host-capture-enabled in its `SandboxSpec` (verified with a stub `SandboxClient` test double — the *real* integration boot is S6-03's job).
- [ ] When `role == SandboxRole.PROBE` and `capture_trace=False` (or unset), the call still succeeds; eBPF capture is gated on `capture_trace`, not on `role` alone. ADR-0002 §Decision binds the *combination*; the parameters are orthogonal at the API.
- [ ] When `role == SandboxRole.GATE` and `capture_trace=True` is passed, the call raises `ValueError("capture_trace requires role=SandboxRole.PROBE")` — `capture_trace` is a `Role.PROBE`-only capability per ADR-0002 §Decision (the trace capture is meaningful only for the probe topology).

### D. Audit-log `role` field (ADR-0003 §Consequences row 3)

- [ ] Every `spawn(...)` call emits an audit-log event whose Pydantic schema includes a `role: SandboxRole` field. The field is **additive** to the existing schema; existing fields are unchanged.
- [ ] `extra="forbid"` is preserved: an audit event with a typo (`{"role_": "gate"}`) fails Pydantic validation; a payload with no `role` field at all also fails (the field is required post-amendment).
- [ ] The audit-log JSON round-trips: `dumps({"kind": "spawn.dispatched", "role": Role.PROBE.value, ...})` parses back to a model whose `role` is `SandboxRole.PROBE`.
- [ ] Sanity: every audit event in the Phase 5 regression suite under `tests/golden/sandbox/audit/*.json` is updated additively (one new `role: "gate"` field per record) and the golden-diff fence accepts the change as a single coordinated edit. (No other field changes.)

### E. Byte-edit allowlist fence

- [ ] S5-01's `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` passes after this story's edits. The fence verifies that `src/codegenie/sandbox/client.py` carries exactly: S6-01's enum block + S6-02's parameter + S6-02's dispatch wire-up. Any *other* byte-edit to `client.py` (formatting, docstring rewrites, unrelated refactors) is rejected.
- [ ] A deliberately-planted second `spawn(...)` parameter (e.g., `extra_flag: bool = False`) fails the fence; the error message names `client.py` and the unauthorized additive diff.

### F. Type-check + style + import-linter

- [ ] `mypy --strict src/codegenie/sandbox/` clean.
- [ ] `ruff check src/codegenie/sandbox/` + `ruff format --check src/codegenie/sandbox/` clean.
- [ ] `make lint-imports` green (no LLM SDK reachable from the sandbox module).
- [ ] `make check` green end-to-end.

## Implementation outline

1. **Read [`src/codegenie/sandbox/client.py`](../../../src/codegenie/sandbox/client.py) end-to-end** — every existing `spawn(...)` (or `execute(...)` per Phase 5's actual naming; reconcile against the file content) caller in the file, every backend dispatcher, every audit-log emission site. Rule 8 — Read before you write. (Note: if the Phase 5 file names the method `execute` rather than `spawn`, surface the convention conflict per Rule 7 — ADR-0003 and the Phase 7 arch design speak `spawn`; use that name for new code and document the resolution in the Notes section. **Do not silently rename**.)
2. **Add the keyword-only parameter** to `spawn(...)`:
   ```python
   def spawn(
       self,
       spec: SandboxSpec,
       *,
       role: SandboxRole = SandboxRole.GATE,
       capture_trace: bool = False,
   ) -> SandboxRun:
       ...
   ```
   The `*` is load-bearing: it forces `role` to be keyword-only so a positional misuse fails fast. `capture_trace` is the orthogonal flag ADR-0002 §Decision pairs with `role=Role.PROBE`.
3. **Wire the dispatch logic**:
   ```python
   if capture_trace and role is not SandboxRole.PROBE:
       raise ValueError("capture_trace requires role=SandboxRole.PROBE")
   spec_with_role = spec.model_copy(update={"role": role, "capture_trace": capture_trace})
   ```
   The backend dispatcher (Firecracker / DinD / Lima) receives `spec_with_role`; the spec's `role` field drives the audit-log tag; the spec's `capture_trace` flag enables eBPF host-side capture and the short container boot.
4. **Emit the audit event** with the new `role` field. The existing Phase 5 audit event Pydantic model gains the additive `role: SandboxRole` field. Existing golden files under `tests/golden/sandbox/audit/` are updated additively per AC-D bullet 4.
5. **Write tests** under `tests/unit/sandbox/test_spawn_role_parameter.py` covering ACs A + B + C + D. The Phase 5 regression suite stays untouched except for the additive `role` field in golden audit events.
6. **Run S5-01's byte-edit allowlist fence** locally. Verify `client.py` carries exactly the authorized additive content.
7. **Run `make check`** — confirm Phase 5's full test suite + Phase 7's new tests are green.

## TDD plan (red → green → refactor)

### Red — write `tests/unit/sandbox/test_spawn_role_parameter.py` first

```python
"""Pins the SandboxClient.spawn(role=...) parameter amendment (Phase 7 ADR-0003)."""

from __future__ import annotations

import inspect

import pytest

from codegenie.sandbox import Role
from codegenie.sandbox.client import SandboxClient, SandboxRole


class TestSignature:
    def test_role_parameter_present_with_default_gate(self) -> None:
        params = inspect.signature(SandboxClient.spawn).parameters
        assert "role" in params
        assert params["role"].default is SandboxRole.GATE

    def test_role_is_keyword_only(self) -> None:
        # ADR-0003: explicit-keyword-arg-only convention guards the default.
        params = inspect.signature(SandboxClient.spawn).parameters
        assert params["role"].kind is inspect.Parameter.KEYWORD_ONLY

    def test_role_annotation_is_sandbox_role(self) -> None:
        params = inspect.signature(SandboxClient.spawn).parameters
        assert params["role"].annotation is SandboxRole


class TestDefaultPathByteIdentity:
    @pytest.fixture
    def stub_client(self) -> SandboxClient:
        # ... construct a Phase-5-canonical SandboxClient stub
        ...

    def test_default_arg_run_byte_equals_role_gate_run(self, stub_client: SandboxClient, gate_spec) -> None:
        default = stub_client.spawn(gate_spec)
        explicit = stub_client.spawn(gate_spec, role=Role.GATE)
        assert _normalize(default) == _normalize(explicit)

    def test_no_phase5_production_callsite_passes_role(self) -> None:
        # Grep-verify: src/codegenie/ (excluding sandbox/) + Phase 3 plugin must NOT
        # pass role= explicitly. Phase 7 plugins under plugins/distroless-migration--*/
        # are exempt.
        ...


class TestProbePath:
    def test_capture_trace_with_gate_raises(self, stub_client, gate_spec) -> None:
        with pytest.raises(ValueError, match="capture_trace requires role=SandboxRole.PROBE"):
            stub_client.spawn(gate_spec, role=Role.GATE, capture_trace=True)

    def test_probe_role_audit_event_carries_role_field(self, stub_client, probe_spec) -> None:
        run = stub_client.spawn(probe_spec, role=Role.PROBE)
        assert any(e.role == "probe" for e in run.audit_events)

    def test_probe_role_without_capture_trace_succeeds(self, stub_client, probe_spec) -> None:
        # role and capture_trace are orthogonal at the API.
        run = stub_client.spawn(probe_spec, role=Role.PROBE, capture_trace=False)
        assert run.exit_status.success or run.exit_status.failed_for_known_reason


class TestAuditEventSchema:
    def test_audit_event_includes_role_field(self) -> None:
        from codegenie.sandbox.client import SpawnDispatchedEvent
        assert "role" in SpawnDispatchedEvent.model_fields

    def test_audit_event_extra_forbid_preserved(self) -> None:
        from codegenie.sandbox.client import SpawnDispatchedEvent
        with pytest.raises(ValidationError):
            SpawnDispatchedEvent(kind="spawn.dispatched", role="gate", typo=1)

    def test_audit_event_role_is_required(self) -> None:
        from codegenie.sandbox.client import SpawnDispatchedEvent
        with pytest.raises(ValidationError):
            SpawnDispatchedEvent(kind="spawn.dispatched")  # no role
```

Run — the imports / signature checks fail because `spawn(...)` doesn't yet accept `role`. Red.

### Green — minimum implementation

Add the keyword-only `role: SandboxRole = SandboxRole.GATE` and `capture_trace: bool = False` parameters; wire the dispatch + audit-event emission; update the Phase 5 audit Pydantic model with the additive `role: SandboxRole` field; refresh golden audit JSON files additively.

### Refactor

Verify no behavioral drift in default-path tests; verify the byte-edit allowlist fence shows only the authorized diff on `client.py`; run `mypy --strict` + `ruff` + `make check`.

## Files to touch

- `src/codegenie/sandbox/client.py` — add the keyword-only `role` and `capture_trace` parameters to `spawn(...)`; wire dispatch + audit-log emission. S5-01 allowlist row #6 (second half; S6-01 used the first half).
- (Existing) `src/codegenie/sandbox/client.py` (or equivalent) audit-event Pydantic model — add additive `role: SandboxRole` field. Same row #6 edit budget; no separate allowlist row needed.
- `tests/unit/sandbox/test_spawn_role_parameter.py` — new file with the AC tests.
- `tests/golden/sandbox/audit/*.json` — additive `role: "gate"` field per record; coordinated golden refresh.
- `tests/golden/sandbox/spawn_default_run.json` — new baseline for byte-identity comparison.

## Out of scope

- The integration test booting a real microVM under `Role.PROBE` and capturing an eBPF trace — owned by **S6-03**.
- `ShellInvocationTraceProbe`'s implementation (the sole `Role.PROBE` caller in Phase 7's probe layer) — owned by **S7-02**.
- `DistrolessBuildGate` / `ShellInvocationDeltaGate` calling `spawn(role=Role.GATE)` — owned by **S10-04** and **S10-05** (those are existing-callsite-shaped uses; the default arg covers them, but those stories make the call explicit for audit-log clarity).
- The Phase 8 Planner's reading of `role` for scheduling decisions — explicit non-goal per ADR-0003 §Tradeoffs row 2.
- A `Role.RECIPE` / `Role.AUDIT` / `Role.WARM_PROBE` extension — future phases.

## Notes for the implementer

- **Method name reconciliation (Rule 7 — Surface conflicts, don't average them):** Phase 5's `final-design.md` shows the method as `SandboxClient.execute(spec) -> SandboxRun`; Phase 7's ADR-0003 + arch design speak `SandboxClient.spawn(...)`. Read `src/codegenie/sandbox/client.py` to determine the actual name in the shipped code, and **use that name**. If Phase 5 ships `execute`, then ADR-0003's text "`spawn`" is the architectural intent and the implementation extends `execute(...)` additively with the same `role` parameter — surface the resolution in the story's attempt log under `_attempts/S6-02.md`. Do **not** silently rename.
- **Default-arg byte-identity is the load-bearing claim.** The single largest risk in this story is a stealth behavioral change on the default path. AC-B's golden file (`tests/golden/sandbox/spawn_default_run.json`) is the canonical check; the property-style sweep across 5 spec variations is the secondary check. If you cannot reproduce byte-identity on a clean Phase 5 fixture, **stop and ask** — do not lower the bar.
- **Why `capture_trace` is orthogonal to `role`:** ADR-0002 §Decision binds `Role.PROBE + capture_trace=True` as the canonical shell-trace probe shape. But `Role.PROBE` alone (without trace capture) is reserved as the audit-log distinction even when no trace is needed — a future Phase 8 Planner may schedule a probe-tagged microVM for a different purpose that doesn't need eBPF. Keep the parameters orthogonal at the API; raise only on the impossible combination (`capture_trace + Role.GATE`).
- **`SpawnDispatchedEvent` (or whatever Phase 5 names its audit-event Pydantic model) gains a `role` field additively.** Phase 5's `extra="forbid"` discipline (Phase 5 ADR-0001 / final-design §6) prevents silent field smuggling; the additive `role` field is the *one* explicit Phase 7 extension. Update Phase 5's golden audit JSON files in lockstep.
- **The byte-edit allowlist fence (S5-01) will fail if you touch anything else in `client.py`.** Resist "while I'm here" formatting changes (Rule 3 — Surgical Changes). If the file needs a docstring update or a refactor to accommodate the parameter, surface it in the Notes section and propose an ADR amendment to row #6 — do not silently widen.
- **The fallback ADR-0003 §Reversibility names** (route `Role.PROBE` through `Role.GATE` semantics if Phase 5 rejects the amendment) is **not in scope for this story.** This story assumes Phase 5 ratifies. If the fallback is invoked, AC-C bullet 2 changes — log that in the attempt log and reopen.
- **No `cost_band`, no `applies_when` on `spawn(...)` either.** ADR-0003's minimum-surface principle extends to the parameter list: one new parameter (`role`), one related orthogonal flag (`capture_trace`), no other additions.
- **Read [Phase 5 final-design §Components §1](../../05-sandbox-trust-gates/final-design.md)** before touching the method body — it documents which backends register and how the spec flows. The amendment must compose with `DockerInDockerClient`, `FirecrackerClient`, and whatever Lima-based backend Phase 5 ends up shipping for macOS.
