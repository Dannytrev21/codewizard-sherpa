# Story S6-01 — `SandboxRole` additive enum (`GATE` + `PROBE`) exported from `src/codegenie/sandbox/`

**Step:** Step 6 — Phase 5 `SandboxRole` additive enum + `SandboxClient.spawn(role=...)` amendment
**Status:** Ready
**Effort:** S
**Depends on:** S5-01 (byte-edit allowlist fence must be in place to authorize the `__init__.py` + `client.py` edits)
**ADRs honored:** Phase 7 ADR-0003, Phase 7 ADR-0009 (allowlist rows #6 + #7), Phase 7 ADR-0002 (consumer), Phase 7 ADR-0001 (no parallel `probe-control` process), Phase 5 ADR-0001 (two-chokepoint sandbox seam), production ADR-0033 (sum-type discipline)

## Context

Phase 5's `SandboxClient` was built as a single-purpose seam: spawn microVMs (Firecracker on Linux, DinD on macOS, Lima where Phase 5's stack adopts it) for `Gate` ABC subclasses. Phase 7 introduces the first **probe** that needs the same isolation tier — `ShellInvocationTraceProbe` executes target-repo build commands and is the gather pipeline's first target-repo-code-execution event. Phase 7 ADR-0002 binds that probe to `SandboxClient`; Phase 7 ADR-0003 records the minimum-surface mechanism: one additive enum + one additive parameter, not a parallel `probe-control` process.

This story ships **only the enum**. The signature change to `spawn(...)` is S6-02; the integration test that proves microVM topology under `Role.PROBE` is S6-03. The split is deliberate: the byte-edit allowlist fence (S5-01) enumerates rows #6 (`src/codegenie/sandbox/client.py`) and #7 (`src/codegenie/sandbox/__init__.py`) separately, and ADR-0003 says "the change is exactly two lines (one signature, one default)" — landing those two lines in two stories means a regression to either is localized.

`SandboxRole` is a `str, Enum` (not a plain `Enum`) so it round-trips through JSON, audit log payloads, and Pydantic-validated `extra="forbid"` event schemas without `.value` accessors at every consumer. The string values (`"gate"`, `"probe"`) are the **stable wire format** — they appear in `audit.event.role`, in `SandboxRole(role_str)` round-trips, and in any future Phase 8 Planner queries that filter on role. Renaming them is a coordinated multi-phase event per ADR-0003 §Tradeoffs row 4.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §Physical view`](../phase-arch-design.md) — `SandboxRole`-tagged dispatch on the existing chokepoint.
  - [`../phase-arch-design.md §Process view`](../phase-arch-design.md) — sequence diagram lines `spawn(role=Role.PROBE, ...)` and `spawn(role=Role.GATE, ...)` show the two enum values' call sites.
  - [`../phase-arch-design.md §Component design §9 (ShellInvocationTraceProbe)`](../phase-arch-design.md) — the sole `Role.PROBE` caller.
- **Phase ADRs (rules this story honors):**
  - [`../ADRs/0003-sandbox-role-additive-enum-on-spawn.md`](../ADRs/0003-sandbox-role-additive-enum-on-spawn.md) — the canonical decision; the enum values and string wire-format come from here.
  - [`../ADRs/0009-phase-7-byte-edit-allowlist-fence.md`](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — rows 6 + 7 authorize this story's edits and only these.
  - [`../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md`](../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md) — the consumer; explains why `Role.PROBE` exists at all.
  - [`../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md`](../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md) — context for why Phase 7's additive surface is minimum.
- **Source design:**
  - [`../final-design.md §Synthesis ledger departure #3`](../final-design.md) — synthesis position: amend Phase 5 with one parameter, not a parallel process.
  - [`../final-design.md §Risks #1`](../final-design.md) — fallback (`Role.GATE` only) if Phase 5 rejects.
- **Phase 5 context:**
  - [`../../05-sandbox-trust-gates/final-design.md §Components §1 SandboxClient`](../../05-sandbox-trust-gates/final-design.md) — the existing Protocol surface this story extends additively.
  - [`../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md`](../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md) — the seam Phase 7 amends rather than duplicates.
- **High-level impl:**
  - [`../High-level-impl.md §Step 6`](../High-level-impl.md) — Features delivered bullet 1 + bullet 2.

## Goal

Ship `SandboxRole(str, Enum)` with exactly two members — `GATE = "gate"` and `PROBE = "probe"` — defined in `src/codegenie/sandbox/client.py` and re-exported from `src/codegenie/sandbox/__init__.py` as `Role` (the alias the rest of the codebase consumes), such that:

1. `from codegenie.sandbox import Role` and `from codegenie.sandbox.client import SandboxRole` both resolve and refer to the same class object.
2. `Role.GATE.value == "gate"` and `Role.PROBE.value == "probe"` — the string wire format is locked.
3. `Role("gate")` and `Role("probe")` round-trip; `Role("anything-else")` raises `ValueError`.
4. The two file edits (`__init__.py` adds `"Role"` to `__all__` and one import; `client.py` adds the `class SandboxRole` definition) are the only byte-edits this story makes, and both are authorized by S5-01's allowlist rows #6 + #7.

The `spawn(...)` parameter is **out of scope** for this story (S6-02 owns it).

## Acceptance criteria

### A. Enum definition + public export

- [ ] `src/codegenie/sandbox/client.py` defines `class SandboxRole(str, Enum)` with exactly two members: `GATE = "gate"`, `PROBE = "probe"`. No `_value_` overrides, no extra members.
- [ ] `src/codegenie/sandbox/__init__.py` adds `from .client import SandboxRole as Role` (or equivalent re-export) and includes `"Role"` in `__all__`.
- [ ] Both `from codegenie.sandbox import Role` and `from codegenie.sandbox.client import SandboxRole` resolve; `Role is SandboxRole` is `True`.
- [ ] `mypy --strict src/codegenie/sandbox/` is clean.
- [ ] `ruff check src/codegenie/sandbox/` and `ruff format --check src/codegenie/sandbox/` are clean.

### B. String round-trip + value stability

- [ ] `Role.GATE.value == "gate"` and `Role.PROBE.value == "probe"` (exact byte-string match — these are the wire format).
- [ ] `Role("gate") is Role.GATE` and `Role("probe") is Role.PROBE` (round-trip via constructor).
- [ ] `str(Role.GATE)` is stable across the test suite (pin the exact string the codebase chooses — `"SandboxRole.GATE"` vs `"gate"` — and assert it explicitly).
- [ ] `Role.GATE == "gate"` is `True` (the `str, Enum` mixin contract; downstream consumers rely on this).
- [ ] `list(Role)` returns `[Role.GATE, Role.PROBE]` in declaration order; a test pins the cardinality (`len(Role) == 2`) so a future stealth third member fails CI.
- [ ] `Role("PROBE")` (wrong-case) raises `ValueError` — case sensitivity is the contract; a `"Probe"` audit-log payload must round-trip as a parse error, not a silent match.
- [ ] `Role("anything-else")` raises `ValueError` with the canonical Enum message.

### C. JSON serialization (forward-compat for ADR-0003 audit-log additive field)

- [ ] `json.dumps({"role": Role.GATE})` produces `'{"role": "gate"}'` (the mixin makes this work without a custom encoder; assert it explicitly so a future encoder regression fails CI).
- [ ] Round-trip: `Role(json.loads(json.dumps({"role": Role.PROBE.value}))["role"]) is Role.PROBE`.
- [ ] A Pydantic `BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=True)` and a `role: Role` field validates `{"role": "gate"}` and rejects `{"role": "gate", "extra": 1}` (smoke test that Phase 5's `extra="forbid"` discipline holds when the enum participates).

### D. Allowlist fence interaction

- [ ] `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (from S5-01) passes after this story's edits — `src/codegenie/sandbox/__init__.py` has exactly the one-line `Role` export change (allowlist row #7) and `src/codegenie/sandbox/client.py` has exactly the `class SandboxRole` block (allowlist row #6's first half; S6-02 lands the rest of row #6).
- [ ] A deliberately-planted second edit to `src/codegenie/sandbox/__init__.py` (e.g., adding an unrelated re-export) fails the fence; the fence error message names the file.

### E. No Phase 5 regression

- [ ] **Phase 5's existing test suite is green with zero new test skips.** Specifically `pytest tests/unit/sandbox/ tests/integration/test_sandbox_*.py` exits 0 (the suite Phase 5 ships with) on the post-story branch.
- [ ] `make check` is green.
- [ ] No existing test is deleted, disabled, or marked `xfail` to accommodate this story. (If one needs to change, surface it in the Notes section — bare contradictions are blocking.)

## Implementation outline

1. **Open `src/codegenie/sandbox/client.py`.** Read the file end-to-end first (Rule 8 — Read before you write). Locate the imports block; add `from enum import Enum` if not already present. Locate a stable insertion point near the top of the module (after imports, before the existing `SandboxClient` Protocol / class). This is the only edit row #6 of S5-01's allowlist authorizes for this story.
2. **Add the enum:**
   ```python
   class SandboxRole(str, Enum):
       """Sandbox spawn role.

       GATE: the default — used by every Phase 5 Gate caller (unchanged behavior).
       PROBE: introduced in Phase 7 for ``ShellInvocationTraceProbe``; same
           microVM topology as GATE plus eBPF host-side trace capture and a
           short container boot. See Phase 7 ADR-0003.

       The string values are the wire format (audit logs, Pydantic event
       payloads). Renaming a member is a coordinated multi-phase event.
       """

       GATE = "gate"
       PROBE = "probe"
   ```
   No methods. No `_value_` override. No docstrings on individual members (the class docstring is the source of truth).
3. **Open `src/codegenie/sandbox/__init__.py`.** Add `from .client import SandboxRole as Role` to the imports; add `"Role"` to `__all__` alphabetically. This is allowlist row #7 of S5-01.
4. **Write the unit tests** under `tests/unit/sandbox/test_role_enum.py` covering ACs B + C exhaustively. Tests must be byte-equal-runnable copy/paste — see TDD plan below.
5. **Run `make check`.** Confirm Phase 5's test suite is byte-clean.
6. **Run S5-01's byte-edit allowlist fence.** Verify exactly the two file changes show up; the fence's row-#6 + row-#7 counters increment as expected.

## TDD plan (red → green → refactor)

### Red — write `tests/unit/sandbox/test_role_enum.py` first

```python
"""Pins the SandboxRole enum's wire format and module surface (Phase 7 ADR-0003)."""

from __future__ import annotations

import json
from enum import Enum

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from codegenie.sandbox import Role
from codegenie.sandbox.client import SandboxRole


class TestEnumDefinition:
    def test_role_is_sandbox_role(self) -> None:
        assert Role is SandboxRole

    def test_inherits_from_str_and_enum(self) -> None:
        assert issubclass(SandboxRole, str)
        assert issubclass(SandboxRole, Enum)

    def test_exactly_two_members(self) -> None:
        # Cardinality is load-bearing: a stealth third member must fail CI.
        assert len(list(SandboxRole)) == 2

    def test_member_declaration_order(self) -> None:
        assert list(SandboxRole) == [SandboxRole.GATE, SandboxRole.PROBE]


class TestStringWireFormat:
    def test_gate_value(self) -> None:
        # The string is the wire format; renaming is a multi-phase event.
        assert SandboxRole.GATE.value == "gate"

    def test_probe_value(self) -> None:
        assert SandboxRole.PROBE.value == "probe"

    def test_str_enum_mixin_string_equality(self) -> None:
        # Phase 5 audit-log consumers rely on the str mixin contract.
        assert SandboxRole.GATE == "gate"
        assert SandboxRole.PROBE == "probe"


class TestRoundTrip:
    def test_gate_constructor_round_trip(self) -> None:
        assert SandboxRole("gate") is SandboxRole.GATE

    def test_probe_constructor_round_trip(self) -> None:
        assert SandboxRole("probe") is SandboxRole.PROBE

    def test_unknown_value_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            SandboxRole("audit")  # Future Role.AUDIT does not exist yet.

    def test_case_sensitivity(self) -> None:
        # An audit-log payload with "PROBE" must fail parse, not silently match.
        with pytest.raises(ValueError):
            SandboxRole("PROBE")


class TestJsonSerialization:
    def test_dumps_uses_string_value(self) -> None:
        # No custom encoder needed; the str mixin makes this work.
        assert json.dumps({"role": SandboxRole.GATE}) == '{"role": "gate"}'

    def test_round_trip_through_json(self) -> None:
        payload = json.dumps({"role": SandboxRole.PROBE.value})
        assert SandboxRole(json.loads(payload)["role"]) is SandboxRole.PROBE


class TestPydanticIntegration:
    """Phase 5's audit-log Pydantic models use extra='forbid'; pin the contract."""

    class _RoleEvent(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        role: SandboxRole

    def test_validates_string_input(self) -> None:
        event = self._RoleEvent(role="gate")  # type: ignore[arg-type]
        assert event.role is SandboxRole.GATE

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            self._RoleEvent(role="gate", extra=1)  # type: ignore[call-arg]

    def test_rejects_unknown_role(self) -> None:
        with pytest.raises(ValidationError):
            self._RoleEvent(role="audit")  # type: ignore[arg-type]
```

Run the test file — it fails because `Role` and `SandboxRole` don't exist yet (the import fails). That's red.

### Green — minimum implementation

Add the `class SandboxRole(str, Enum)` block to `src/codegenie/sandbox/client.py` and the re-export to `src/codegenie/sandbox/__init__.py`. Re-run; all tests pass.

### Refactor

Nothing to refactor — the enum is two lines plus a docstring. Verify no `# noqa` was added; verify `mypy --strict` clean; verify `ruff check` + `ruff format --check` clean.

## Files to touch

- `src/codegenie/sandbox/client.py` — add `class SandboxRole(str, Enum)` block (S5-01 allowlist row #6; the `role=` parameter portion of row #6 is S6-02's responsibility).
- `src/codegenie/sandbox/__init__.py` — add `from .client import SandboxRole as Role`; add `"Role"` to `__all__` (S5-01 allowlist row #7).
- `tests/unit/sandbox/test_role_enum.py` — new file with the test cases above.

## Out of scope

- The `role: SandboxRole = SandboxRole.GATE` parameter on `SandboxClient.spawn(...)` — owned by **S6-02**. This story ships only the enum.
- The integration test proving `spawn(role=Role.PROBE)` boots a microVM with eBPF trace capture — owned by **S6-03**.
- Phase 5's audit-log `role` field schema extension (additive per ADR-0003 §Consequences) — Phase 5 owns the audit-log surface; Phase 7 only consumes via the parameter (S6-02).
- A future `Role.RECIPE` / `Role.AUDIT` for later task classes — ADR-0003 §Reversibility notes this is the same additive shape; not in Phase 7 scope.

## Notes for the implementer

- **Why `str, Enum` and not plain `Enum`:** Phase 5's audit-log Pydantic models serialize role to JSON without a custom encoder; consumers like `coordination-summary.yaml` (S11-02) and `RequiresMultiPluginCoordination` events (S11-01) inherit `extra="forbid"`. A plain `Enum` requires `.value` accessors at every boundary and breaks round-trip semantics. ADR-0003 explicitly chose the mixin shape.
- **Why ship the enum in a separate story from the parameter:** S5-01's byte-edit allowlist enumerates `client.py` (row #6) and `__init__.py` (row #7) as *two* allowed edits; landing the enum block in S6-01 and the `spawn(...)` parameter in S6-02 keeps each story's diff minimal and lets a regression to either be localized in `git bisect`. ADR-0003 §Consequences row 1 names this two-line split.
- **Why `Role` is the public alias, not `SandboxRole` directly:** consumer code reads `from codegenie.sandbox import Role; client.spawn(role=Role.PROBE, ...)`. The `Role` alias is what the rest of the codebase imports; `SandboxRole` is the canonical class name. Both must work — assert the identity in AC-A.
- **Phase 5 ratification:** ADR-0003 §Risks names the precondition. If Phase 5 rejects (unlikely; the synthesis-departure architecture's load-bearing piece), the fallback per ADR-0003 §Reversibility is to ship `Role.PROBE` semantically but route via `Role.GATE` — that's S6-02's concern, not this story's. This story ships the enum either way.
- **`raise AssertionError` discipline:** if any production-code invariant assertion is needed here, use `raise AssertionError(...)`, not bare `assert` (the `forbidden-patterns` pre-commit hook bans bare `assert` in `src/`). Test files use plain `assert`; that's fine.
- **No `cost_band`, no `applies_when` on the enum** — ADR-0003 deliberately keeps the enum dumb. Routing-via-role policy (e.g., Phase 8 scheduling probes on cheaper runners) is a Planner concern that *reads* the role; the enum itself carries no metadata.
- **Read [Phase 5 ADR-0001](../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md) before editing `client.py`.** The two-chokepoint seam (`SandboxClient.spawn(...)` + `run_in_sandbox`) is the load-bearing convention; this story extends `spawn(...)`'s caller-facing API additively without touching `run_in_sandbox`.
