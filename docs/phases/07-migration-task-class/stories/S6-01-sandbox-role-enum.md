# Story S6-01 — `SandboxRole` additive enum (`GATE` + `PROBE`) exported from `src/codegenie/sandbox/`

**Step:** Step 6 — Phase 5 `SandboxRole` additive enum + `SandboxClient.spawn(role=...)` amendment
**Status:** HARDENED (phase-story-validator, 2026-08-15 — pre-executor pass; see `_validation/S6-01-sandbox-role-enum.md`)
**Effort:** S
**Depends on:** S5-01 (byte-edit allowlist fence must be in place to authorize the `__init__.py` + `client.py` edits); Phase 5 must have shipped `src/codegenie/sandbox/client.py` and `src/codegenie/sandbox/__init__.py` — see Preconditions.
**ADRs honored:** Phase 7 ADR-0003, Phase 7 ADR-0009 (allowlist rows #6 + #7 — see Preconditions §2 for the row-#6 spirit-of-the-rule reading), Phase 7 ADR-0002 (consumer), Phase 7 ADR-0001 (no parallel `probe-control` process), Phase 5 ADR-0001 (two-chokepoint sandbox seam), production ADR-0033 (sum-type discipline)

## Preconditions

Read before starting:

1. **`src/codegenie/sandbox/` must exist at execution time.** As of 2026-08-15 the directory does not exist on `main` — Phase 5's sandbox module has not shipped yet (see the roadmap). This story targets Phase 5's `client.py` + `__init__.py`; if those files are still absent when the executor picks up this story, the story is `BLOCKED` on Phase 5's `SandboxClient` module landing. The fallback per ADR-0003 §Reversibility (route `Role.PROBE` through `Role.GATE`) is Phase 7's overall risk, not this story's execution path — this story's job is to ship the enum against a real `client.py`, or block until one exists.
2. **ADR-0009 row #6 covers the enum block *and* the parameter as one coordinated edit.** Row #6's literal wording is `"exactly one new role: SandboxRole = Role.GATE parameter on spawn(...)"`; a strict reading covers only the parameter. The spirit-of-the-rule reading — the one this story and S6-02 execute against — is that the row authorizes every byte-edit to `client.py` required by the sandbox-role amendment (Phase 7 ADR-0003), of which the `class SandboxRole` block is a necessary half. Anchor for the broad reading: [`../High-level-impl.md §Step 6`](../High-level-impl.md) explicitly lists both the enum block and the parameter under one "Features delivered" bullet, and Phase 7 ADR-0003 §Consequences row 1 counts the change as "exactly two lines (one signature, one default)" *in addition to* the enum itself. If S5-01's fence file (as landed) enforces the strict reading (row #6 blocks the enum-block byte-edit), the fence file's `# row 6` inline comment must be widened before this story can pass — coordinate with the S5-01 executor, do NOT amend ADR-0009 (row #6's ADR text remains unchanged; only the fence file's interpretive comment shifts). Document the widening in this story's attempt log if it occurs.
3. **Python version.** The codebase's floor is 3.11 (see `pyproject.toml`). `enum.StrEnum` is available at that floor; the story deliberately uses `class SandboxRole(str, Enum)` per ADR-0003's example, not `StrEnum` — see Notes-for-implementer §"StrEnum alternative" for the rationale. Any Python-3.11-specific `Enum.__str__` semantics are pinned in AC-B (`repr` and `str` explicitly asserted so a future minor-version drift is a loud test failure).

## Validation notes (phase-story-validator, 2026-08-15)

Hardened by the phase-story-validator pipeline; full audit in [`_validation/S6-01-sandbox-role-enum.md`](_validation/S6-01-sandbox-role-enum.md). Summary of edits:

1. **Preconditions added** — surfaced that `src/codegenie/sandbox/` does not yet exist on `main` (Phase 5 hasn't shipped), that ADR-0009 row #6's *literal* wording covers only the parameter (spirit-of-the-rule reading extended to the enum block is documented and anchored to HL-impl Step 6), and that Python 3.11's `StrEnum` alternative was rejected per ADR-0003.
2. **AC-A hardening** — added the alias-rejection check `len(SandboxRole.__members__) == 2` (the existing `len(list(SandboxRole)) == 2` silently skips aliases; a stealth `LEGACY = "gate"` would have passed).
3. **AC-B hardening** — pinned `str(Role.GATE) == "SandboxRole.GATE"` and `repr(Role.GATE) == "<SandboxRole.GATE: 'gate'>"` explicitly (removes the "codebase chooses" ambiguity — the choice is made now); added value-uniqueness (`SandboxRole.GATE.value != SandboxRole.PROBE.value`), symbol-name stability (`.name == "GATE" | "PROBE"`), and `.value` type check (`isinstance(SandboxRole.GATE.value, str)`).
4. **AC-C hardening** — added hash-equality with underlying `str` (`hash(SandboxRole.GATE) == hash("gate")`) so downstream audit-log consumers can mix enum values and raw strings as dict keys without silently different bucketing.
5. **AC-D clarification** — extended AC-D with the "spirit-of-the-rule" language from Preconditions §2; added AC-D.b naming the S5-01 fence file's `# row 6` inline comment as the interpretive load-bearing artifact.
6. **TDD plan hardening** — added `test_no_aliases`, `test_value_uniqueness`, `test_name_stability`, `test_value_is_str`, `test_str_repr_stability`, `test_hash_equality_with_str` corresponding to the new/tightened ACs.
7. **Notes for the implementer** — added a "StrEnum alternative" paragraph explaining why `class SandboxRole(str, Enum)` was picked (ADR-0003 explicit example + `str(instance)` divergence between the two shapes) and a "Preconditions link-back" reminder for the row-#6 spirit-of-the-rule dance.

**Verdict:** HARDENED — no structural block. Story is executable the moment Phase 5's `sandbox/` module lands and the S5-01 fence's row-#6 comment covers the enum block.

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

- [ ] `src/codegenie/sandbox/client.py` defines `class SandboxRole(str, Enum)` with exactly two members: `GATE = "gate"`, `PROBE = "probe"`. No `_value_` overrides, no extra members, no aliases.
- [ ] **Alias-rejection guard:** `len(SandboxRole.__members__) == 2` (in addition to `len(list(SandboxRole)) == 2` in AC-B — `list()` skips aliases; `__members__` counts them, so both are required to catch a stealth `LEGACY = "gate"` that would otherwise appear as a silent alias for `GATE`).
- [ ] `src/codegenie/sandbox/__init__.py` adds `from .client import SandboxRole as Role` (or equivalent re-export) and includes `"Role"` in `__all__` alphabetically.
- [ ] Both `from codegenie.sandbox import Role` and `from codegenie.sandbox.client import SandboxRole` resolve; `Role is SandboxRole` is `True` (identity, not equality — pinned by `assert Role is SandboxRole`).
- [ ] `mypy --strict src/codegenie/sandbox/` is clean.
- [ ] `ruff check src/codegenie/sandbox/` and `ruff format --check src/codegenie/sandbox/` are clean.

### B. String round-trip + value stability

- [ ] `Role.GATE.value == "gate"` and `Role.PROBE.value == "probe"` (exact byte-string match — these are the wire format).
- [ ] **Value type is `str`, not a subclass or `bytes`:** `type(Role.GATE.value) is str` and `type(Role.PROBE.value) is str`. The "wire format is `str`" claim depends on the values being plain `str` — a `bytes` value or a `str` subclass would silently break Pydantic v2's discriminator machinery.
- [ ] **Value uniqueness:** `Role.GATE.value != Role.PROBE.value` (guards against a typo like `PROBE = "gate"` that would silently alias `Role.PROBE` to `Role.GATE`).
- [ ] **Symbol-name stability:** `Role.GATE.name == "GATE"` and `Role.PROBE.name == "PROBE"`. A rename like `GATE` → `Gate` leaves `.value` unchanged and would slip past every other assertion here; `.name` is what error messages and `repr()` use, so a rename is a wire-visible event.
- [ ] `Role("gate") is Role.GATE` and `Role("probe") is Role.PROBE` (round-trip via constructor; identity, not equality).
- [ ] **`str(Role.GATE) == "SandboxRole.GATE"` and `str(Role.PROBE) == "SandboxRole.PROBE"`.** The `str, Enum` mixin (per ADR-0003) inherits `Enum.__str__`, which returns `f"{ClassName}.{MemberName}"` on Python 3.11+; the wire format `"gate"`/`"probe"` is on `.value`, not `str(...)`. Pinning this explicitly locks the divergence (a future refactor to `enum.StrEnum` would flip `str(...)` to the wire value and this test would fail loudly — the intended blast radius).
- [ ] **`repr(Role.GATE) == "<SandboxRole.GATE: 'gate'>"` and `repr(Role.PROBE) == "<SandboxRole.PROBE: 'probe'>"`.** `repr` is what appears in stack traces and error messages; pinning it locks operator-facing surface stability.
- [ ] `Role.GATE == "gate"` is `True` (the `str, Enum` mixin contract; downstream consumers rely on this).
- [ ] `list(Role)` returns `[Role.GATE, Role.PROBE]` in declaration order; a test pins the cardinality (`len(list(Role)) == 2`) so a future stealth third *member* (not alias — aliases are guarded in AC-A) fails CI.
- [ ] `Role("PROBE")` (wrong-case) raises `ValueError` — case sensitivity is the contract; a `"Probe"` audit-log payload must round-trip as a parse error, not a silent match.
- [ ] `Role("anything-else")` raises `ValueError` with the canonical Enum message (`is not a valid SandboxRole` substring).

### C. JSON serialization (forward-compat for ADR-0003 audit-log additive field)

- [ ] `json.dumps({"role": Role.GATE})` produces `'{"role": "gate"}'` (the mixin makes this work without a custom encoder; assert it explicitly so a future encoder regression fails CI).
- [ ] Round-trip: `Role(json.loads(json.dumps({"role": Role.PROBE.value}))["role"]) is Role.PROBE`.
- [ ] **Hash equality with the underlying `str`:** `hash(Role.GATE) == hash("gate")` and `hash(Role.PROBE) == hash("probe")`. The `str, Enum` mixin makes this true; pinning it locks the invariant so downstream audit-log correlators can safely use enum values and raw strings as dict keys / set members interchangeably (a lens shift to `StrEnum` preserves this; a lens shift to plain `Enum` would silently break it).
- [ ] A Pydantic `BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=True)` and a `role: Role` field validates `{"role": "gate"}` and rejects `{"role": "gate", "extra": 1}` (smoke test that Phase 5's `extra="forbid"` discipline holds when the enum participates).

### D. Allowlist fence interaction

- [ ] `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (from S5-01) passes after this story's edits — `src/codegenie/sandbox/__init__.py` has exactly the one-line `Role` export change (allowlist row #7) and `src/codegenie/sandbox/client.py` has exactly the `class SandboxRole` block (spirit-of-the-rule reading of allowlist row #6 — see Preconditions §2; S6-02 lands the `spawn(role=...)` parameter portion of the same row).
- [ ] **Row-#6 interpretive comment:** the fence file's `# row 6` inline block-comment must name both the enum block and the `spawn(...)` parameter as the coordinated pair row #6 covers (spirit-of-the-rule per Preconditions §2). If the S5-01 executor landed the strict reading, coordinate the widening with them; do not amend ADR-0009 §Decision — only the fence file's interpretive comment shifts. Record the widening (or its absence) in this story's attempt log.
- [ ] A deliberately-planted second edit to `src/codegenie/sandbox/__init__.py` (e.g., adding an unrelated re-export) fails the fence; the fence error message names the file.
- [ ] A deliberately-planted unrelated edit to `src/codegenie/sandbox/client.py` (e.g., a doc-comment tweak elsewhere in the file) fails the fence; the fence error message names the file. (Row #6's spirit-of-the-rule reading authorizes exactly the enum block + the parameter addition — no incidental edits.)

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

    def test_no_aliases(self) -> None:
        # list() and iteration skip aliases; __members__ counts them.
        # A stealth `LEGACY = "gate"` would pass test_exactly_two_members
        # (list() skips it as an alias of GATE) but this assertion catches it.
        assert len(SandboxRole.__members__) == 2

    def test_member_declaration_order(self) -> None:
        assert list(SandboxRole) == [SandboxRole.GATE, SandboxRole.PROBE]

    def test_name_stability(self) -> None:
        # Symbol names are the operator-facing surface (repr, error messages).
        # A rename like GATE -> Gate would leave .value untouched and slip
        # past every other assertion here.
        assert SandboxRole.GATE.name == "GATE"
        assert SandboxRole.PROBE.name == "PROBE"


class TestStringWireFormat:
    def test_gate_value(self) -> None:
        # The string is the wire format; renaming is a multi-phase event.
        assert SandboxRole.GATE.value == "gate"

    def test_probe_value(self) -> None:
        assert SandboxRole.PROBE.value == "probe"

    def test_value_is_plain_str(self) -> None:
        # A str subclass or bytes value would silently break Pydantic v2's
        # discriminator machinery on downstream audit-log models.
        assert type(SandboxRole.GATE.value) is str
        assert type(SandboxRole.PROBE.value) is str

    def test_value_uniqueness(self) -> None:
        # Guards against a typo like PROBE = "gate" that would silently
        # alias PROBE to GATE.
        assert SandboxRole.GATE.value != SandboxRole.PROBE.value

    def test_str_enum_mixin_string_equality(self) -> None:
        # Phase 5 audit-log consumers rely on the str mixin contract.
        assert SandboxRole.GATE == "gate"
        assert SandboxRole.PROBE == "probe"

    def test_str_and_repr_stability(self) -> None:
        # `str, Enum` inherits Enum.__str__ on Python 3.11+: "ClassName.MEMBER".
        # The wire value is on .value, NOT str(...). Pinning both locks the
        # divergence — a future refactor to enum.StrEnum would flip str(...)
        # to the wire value, and this test would fail loudly (intended blast).
        assert str(SandboxRole.GATE) == "SandboxRole.GATE"
        assert str(SandboxRole.PROBE) == "SandboxRole.PROBE"
        assert repr(SandboxRole.GATE) == "<SandboxRole.GATE: 'gate'>"
        assert repr(SandboxRole.PROBE) == "<SandboxRole.PROBE: 'probe'>"

    def test_hash_equality_with_underlying_str(self) -> None:
        # The str mixin makes an enum member hash the same as its wire value.
        # Downstream audit-log correlators may key dicts / sets on a mix of
        # enum members and raw strings; a lens shift to plain Enum would
        # silently break this. StrEnum preserves it.
        assert hash(SandboxRole.GATE) == hash("gate")
        assert hash(SandboxRole.PROBE) == hash("probe")


class TestRoundTrip:
    def test_gate_constructor_round_trip(self) -> None:
        assert SandboxRole("gate") is SandboxRole.GATE

    def test_probe_constructor_round_trip(self) -> None:
        assert SandboxRole("probe") is SandboxRole.PROBE

    def test_unknown_value_raises_value_error(self) -> None:
        # Future Role.AUDIT does not exist yet.
        with pytest.raises(ValueError, match="is not a valid SandboxRole"):
            SandboxRole("audit")

    def test_case_sensitivity(self) -> None:
        # An audit-log payload with "PROBE" must fail parse, not silently match.
        with pytest.raises(ValueError, match="is not a valid SandboxRole"):
            SandboxRole("PROBE")


class TestJsonSerialization:
    def test_dumps_uses_string_value(self) -> None:
        # No custom encoder needed; the str mixin makes this work.
        assert json.dumps({"role": SandboxRole.GATE}) == '{"role": "gate"}'

    def test_round_trip_through_json(self) -> None:
        payload = json.dumps({"role": SandboxRole.PROBE.value})
        assert SandboxRole(json.loads(payload)["role"]) is SandboxRole.PROBE

    def test_membership_in_str_keyed_dict(self) -> None:
        # Downstream audit-log correlators may build dicts keyed on the wire
        # value and later look them up with an enum member (or vice versa).
        # The str-mixin hash-equality contract (see TestStringWireFormat) makes
        # this work; pinning it here catches a regression to plain Enum.
        by_wire = {"gate": 1, "probe": 2}
        assert by_wire[SandboxRole.GATE] == 1
        assert by_wire[SandboxRole.PROBE] == 2

        by_enum = {SandboxRole.GATE: "g", SandboxRole.PROBE: "p"}
        assert by_enum["gate"] == "g"
        assert by_enum["probe"] == "p"


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
- **StrEnum alternative — why we did NOT use `enum.StrEnum`.** Python 3.11+ (the codebase's floor) ships `enum.StrEnum`, which is designed exactly for the "str-mixin enum with wire-value semantics" pattern. It would give one behavior difference from `class SandboxRole(str, Enum)`: `str(SandboxRole.GATE)` returns `"gate"` (the wire value) under `StrEnum`, and `"SandboxRole.GATE"` under the `str, Enum` mixin. ADR-0003's Consequences row 1 shows the enum defined as `class SandboxRole(str, Enum)`; that is the authoritative shape. This story pins `str(...)` semantics accordingly (AC-B), so if a future refactor switches to `StrEnum` the test fails loudly and the change gets an ADR amendment — the blast radius is intentional. Do **not** silently switch to `StrEnum` during implementation.
- **Preconditions link-back.** Before starting, re-read `## Preconditions` — the `src/codegenie/sandbox/` module must exist (Phase 5 dependency) and S5-01's fence file's `# row 6` inline comment must cover the enum block under the spirit-of-the-rule reading (Preconditions §2). If either is not true at pick-up time, the story is `BLOCKED`; append to the attempt log rather than pushing an incomplete implementation.
