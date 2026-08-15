# Story S6-02 — `SandboxClient.spawn(role=SandboxRole.GATE)` additive parameter

**Step:** Step 6 — Phase 5 `SandboxRole` additive enum + `SandboxClient.spawn(role=...)` amendment
**Status:** HARDENED (phase-story-validator, 2026-08-15 — pre-executor pass; see `_validation/S6-02-sandbox-spawn-role-parameter.md`)
**Effort:** S
**Depends on:** S6-01 (the `SandboxRole` enum must exist), S5-01 (byte-edit allowlist row #6 must be in place); Phase 5 must have shipped `src/codegenie/sandbox/client.py` with the `spawn(...)` (or `execute(...)`) method — see Preconditions §1.
**ADRs honored:** Phase 7 ADR-0003 (primary; see Preconditions §3 for the `capture_trace` amendment gate), Phase 7 ADR-0009 (allowlist row #6 — second half; see Preconditions §4 for the fence file's `# row 6` inline-comment coordination), Phase 7 ADR-0002 (consumer), Phase 7 ADR-0001 (no parallel `probe-control` process), Phase 5 ADR-0001 (two-chokepoint sandbox seam)

## Preconditions

Read before starting:

1. **`src/codegenie/sandbox/client.py` must exist at execution time.** As of 2026-08-15 the directory does not exist on `main` — Phase 5's sandbox module has not shipped yet (mirrors S6-01's Preconditions §1). This story amends Phase 5's method; if `client.py` is still absent when the executor picks up this story, the story is `BLOCKED` on Phase 5's `SandboxClient` module landing. The fallback per ADR-0003 §Reversibility (route `Role.PROBE` through `Role.GATE`) is Phase 7's overall risk, not this story's execution path.
2. **Method name reconciliation (`spawn` vs `execute`) is a Precondition, not just a Note.** Phase 5's canonical [`final-design.md §Components §1 SandboxClient`](../../05-sandbox-trust-gates/final-design.md) shows the method as `SandboxClient.execute(spec: SandboxSpec) -> SandboxRun`. Phase 7 ADR-0003 + arch design speak `spawn(...)`. Rule 7 (surface conflicts, don't average them): read `src/codegenie/sandbox/client.py` first and **use whichever name Phase 5 actually shipped**. If Phase 5 ships `execute`, then ADR-0003's `spawn` wording is architectural intent — extend `execute(...)` additively with the `role` parameter; log the resolution in `_attempts/S6-02.md`. Do NOT silently rename.
3. **`capture_trace: bool` is a SECOND additive parameter beyond `role`. ADR-0003 §Decision says "gains exactly one new parameter."** ADR-0002 §Consequences shows the consumer calling `sandbox.spawn(role=Role.PROBE, workspace=..., command=[...], capture_trace=True)`, and phase-arch-design §Component design §9 (line 813) shows the same shape. Two paths forward, both explicit:
   - **Path A (verify pre-existing):** Grep Phase 5's shipped `SandboxClient` for `capture_trace` — if the parameter already lives on `execute(...)` / `spawn(...)` or on `SandboxSpec`, S6-02 only adds `role` and wires dispatch to the existing `capture_trace`. Preconditions §3 is satisfied.
   - **Path B (Phase 7 amendment):** If `capture_trace` is not pre-existing, S6-02 lands two additive parameters (`role` + `capture_trace`). ADR-0003 §Decision must be amended (either extend the "one new parameter" wording to two, or record `capture_trace` as an ADR-0002 §Consequence — it *does* trace to ADR-0002 §Decision). The executor files the amendment as `ADRs/0003-amendment-capture-trace.md` (Nygard shape) **before** landing the code edit and adds a row-#6 interpretive-comment update to S5-01's fence file. Coordinate; do not silently widen the ADR.
4. **S5-01 fence file's `# row 6` inline comment currently reads:** `"src/codegenie/sandbox/client.py — one new role: SandboxRole = Role.GATE parameter on spawn(...) (S6-02)"`. Under Path A (§3) no fence change is needed. Under Path B, the fence file's row-#6 comment must be widened to name **both** `role` AND `capture_trace` as the coordinated pair the row covers (spirit-of-the-rule reading, mirroring S6-01's Preconditions §2 discipline for the enum block). Record the widening in `_attempts/S6-02.md`.
5. **Phase 5's audit-event Pydantic model name is not confirmed.** The story sketches `SpawnDispatchedEvent`; Phase 5 may name it differently (e.g., `SandboxRunEvent`, `ExecuteDispatchedEvent`). Grep `src/codegenie/sandbox/` for the shipped class name and use it verbatim in the tests; the AC-D fields the tests assert on are stable, only the class name is contingent.
6. **Grep-verification pattern for AC-B is object-scoped, not bare-name.** Phase 5's `SandboxClient` is a Protocol; unrelated `.spawn(` calls (e.g., `asyncio.subprocess.Process.spawn`, `multiprocessing.Process.spawn_context`) must not be false-positives. Use `re.compile(r"(?:sandbox|SandboxClient|sandbox_client|self\.sandbox)\.(?:spawn|execute)\(")` or equivalent AST-based check, not `spawn(` naked.

## Validation notes (phase-story-validator, 2026-08-15)

Hardened by the phase-story-validator pipeline; full audit in [`_validation/S6-02-sandbox-spawn-role-parameter.md`](_validation/S6-02-sandbox-spawn-role-parameter.md). Summary of edits:

1. **Preconditions section added** — surfaced (a) `src/codegenie/sandbox/` does not yet exist on `main` (Phase 5 hasn't shipped), (b) the `spawn` vs `execute` method-name reconciliation was buried in Notes-for-implementer and is elevated to a blocking Precondition, (c) **`capture_trace` is a second additive parameter beyond `role`** and ADR-0003 §Decision says "exactly one new parameter" — Path A / Path B decision tree spelled out, (d) S5-01's fence file's `# row 6` inline comment interpretive load spelled out for Path B, (e) `SpawnDispatchedEvent` class-name assumption flagged as contingent, (f) grep-verification pattern for AC-B specified as object-scoped to avoid false positives on `Process.spawn(...)`.
2. **AC-A hardening** — added positional-misuse runtime test (`spawn(spec, Role.GATE)` raises `TypeError`) to pair with the signature-shape check; specified the "signature-snapshot map" more concretely (exact `inspect.Parameter` field-by-field comparison, not just "any other diff fails").
3. **AC-B hardening** — replaced "property-style" nomenclature with "hand-crafted 5-spec matrix" (5 hand-picked variations, not `hypothesis` — the story does not need real property-based testing here); enumerated the exact fields that get sentinel-normalized before byte-equality comparison; changed `e.role == "probe"` sketches to `e.role is SandboxRole.PROBE` (enum-identity idiom); made the grep AC name the object-scoped regex from Preconditions §6; added the redundant-identity check `client.spawn(spec) == client.spawn(spec, role=SandboxRole.GATE)` explicitly.
4. **AC-C hardening** — pinned the exact `ValueError` message text (was `match="capture_trace requires role=SandboxRole.PROBE"` — kept but made exact-match, not substring); added the dispatch-spec assertion (`SandboxSpec` passed to backend dispatcher carries `capture_trace=True` **only** when both `role=PROBE` and `capture_trace=True` — no orthogonality leak).
5. **AC-D hardening** — added the "audit event's only new field is `role`" assertion (`set(model_fields_post) - set(model_fields_pre) == {"role"}`); pinned the round-trip identity as `is SandboxRole.PROBE` (not `==`); added coordinated-golden-refresh AC (fence must detect a golden JSON that was refreshed with `role` field missing).
6. **AC-E hardening** — added the "planted second additive parameter" case (already present) explicitly names `capture_trace` as the planted case under Path A (verifies Path A stayed clean); added a "planted refactor to method body outside the authorized diff" case (verifies fence catches structural drift on the method body, not just the signature).
7. **New AC-G — Concurrency safety** — two concurrent `spawn(...)` calls with different roles emit audit events with correct role tags (no race). Cheap safety net given the story doesn't add new shared state, but pins the invariant.
8. **TDD plan hardening** — added `test_positional_role_raises_type_error`, `test_no_other_signature_changes` (`inspect.Parameter` map diff), `test_capture_trace_dispatch_propagation` (SandboxSpec-carries-capture_trace assertion), `test_capture_trace_not_leaked_when_role_gate`, `test_audit_event_role_is_only_new_field`, `test_role_round_trip_identity_not_equality`, `test_concurrent_spawn_role_tags_correct`, `test_grep_scope_is_object_scoped` (validates the regex from Preconditions §6 itself); added `match=r"^capture_trace requires role=SandboxRole\.PROBE$"` (exact) on all `pytest.raises(ValueError)` calls.
9. **Notes for the implementer** — added "`capture_trace` amendment dance" paragraph explaining Path A vs Path B; added "Method-name Precondition link-back" paragraph; added "Grep false-positive risk" paragraph pointing at Preconditions §6; added "SandboxSpec.model_copy(update=...) subtlety" paragraph noting that Pydantic v2's `model_copy(update=...)` bypasses `extra="forbid"` and silently adds new fields to the model instance — verify the receiving backend dispatcher validates the spec structurally, not just fields-it-knows-about.

**Verdict:** HARDENED — no structural block on the story itself. Story is executable once (a) Phase 5's `sandbox/` module lands, (b) the `capture_trace` Path A / Path B decision is made (Preconditions §3), and (c) S5-01's fence file's row-#6 comment covers whichever Path is chosen.

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

- [ ] `inspect.signature(SandboxClient.spawn)` (or `.execute` per Preconditions §2) returns a `Parameter` named `role` with default `SandboxRole.GATE` and annotation `SandboxRole`. The parameter is keyword-only (declared after a `*` in the signature).
- [ ] **Positional misuse fails at runtime, not only at import.** `client.spawn(spec, SandboxRole.GATE)` (positional `role`) raises `TypeError` naming the parameter as keyword-only. (Signature-shape and runtime-refusal are separate mutation-resistance tests: a `**kwargs` rewrite could pass the signature check while accepting positional `role`.)
- [ ] No other parameters on `spawn(...)` change name, default, kind, or annotation. A unit test snapshots `inspect.signature(spawn).parameters` post-amendment and diffs it against the pre-amendment shape *plus* the one/two additive parameter(s) authorized by Preconditions §3; the diff is asserted field-by-field on each `Parameter` (name, kind, default, annotation), not by set difference. Any other diff fails CI.
- [ ] `mypy --strict src/codegenie/sandbox/` is clean.

### B. Default-path byte-identity (the load-bearing claim)

- [ ] **`client.spawn(...)` without `role=...` produces a `SandboxRun` byte-equal to a synthetic pre-amendment baseline** captured as `tests/golden/sandbox/spawn_default_run.json` (recorded once during this story; the test asserts byte-equality going forward). The **exact** list of sentinel-normalized fields (all others are compared byte-identical) is: `started_at`, `finished_at`, `duration_ms`, `run_id`, `sandbox_spec_hash` (if it embeds a nonce), and any `audit_events[*].timestamp` / `audit_events[*].event_id`. All other fields — `backend`, `gate_isolation_class`, `audit_events[*].kind`, `audit_events[*].role`, `exit_status`, and any `stdout_digest` / `stderr_digest` — must be byte-identical to the baseline. The normalization function is named `_normalize_run_for_byte_identity` and its allow-list of normalized field paths is a `Final[tuple[str, ...]]` at module scope so a stealth addition to the normalization list fails a companion `test_normalized_fields_enumerated` assertion.
- [ ] `client.spawn(role=SandboxRole.GATE)` and `client.spawn()` (default arg) produce byte-equal results (`_normalize_run_for_byte_identity(a) == _normalize_run_for_byte_identity(b)`) across a **hand-crafted 5-spec matrix** — five explicit `SandboxSpec` variations (differing `command`, `workspace`, `env`, `time_budget_seconds`, `network`), enumerated in the test file. This is a fixed-input equivalence check, not `hypothesis` property-based testing; the story does not need real property-based testing here (the amendment is default-arg-equivalence, which is exhaustively characterizable with a handful of specs).
- [ ] **Every Phase 5 production callsite in the codebase is grep-verified to NOT pass `role=` explicitly.** A unit test scans `src/codegenie/` (excluding `src/codegenie/sandbox/`) and `plugins/vulnerability-remediation--node--npm/` using the object-scoped regex from Preconditions §6 (`re.compile(r"(?:sandbox|SandboxClient|sandbox_client|self\.sandbox)\.(?:spawn|execute)\(")`), and asserts no matched call is followed within its argument list by a `role=` kwarg. (Phase 7 plugins under `plugins/distroless-migration--*/` are exempt — those are the only legitimate `role=Role.PROBE` callers, landed in S7-02 + S10-04 + S10-05.) A companion `test_grep_scope_is_object_scoped` seeds a synthetic false-positive (`Process.spawn(role=1)`) and asserts the scanner ignores it; and seeds a synthetic true-positive (`self.sandbox.spawn(role=Role.GATE)` in a non-exempt path) and asserts the scanner catches it.
- [ ] **Phase 5's existing test suite is green with zero new test skips.** `pytest tests/unit/sandbox/ tests/integration/test_sandbox_*.py` exits 0 on the post-story branch. (Test paths are contingent on Phase 5's actual layout — if Phase 5 nested the tests differently, use the actual paths; the invariant is "every pre-existing Phase-5 test still passes without being disabled.")

### C. `Role.PROBE` topology behavior

- [ ] `client.spawn(role=SandboxRole.PROBE, ..., capture_trace=True)` returns a `SandboxRun` whose `audit_events` contain at least one event `e` with `e.role is SandboxRole.PROBE` (identity check on the enum member, not string `==`; identity guards against a stealth `str` bleed where `e.role` is the raw string `"probe"` instead of the enum).
- [ ] **Dispatch propagation (positive):** when `role == SandboxRole.PROBE` and `capture_trace=True`, a stub backend dispatcher records that the `SandboxSpec` it received had `spec.capture_trace is True` and `spec.role is SandboxRole.PROBE`. (Test double: `class RecordingBackend: def dispatch(self, spec): self.last_spec = spec`.)
- [ ] **Dispatch propagation (orthogonality — negative):** when `role == SandboxRole.GATE` and `capture_trace` is omitted (default `False`), the same stub records `spec.capture_trace is False`. No leak of `capture_trace=True` on the default path.
- [ ] When `role == SandboxRole.PROBE` and `capture_trace=False` (or unset), the call still succeeds; eBPF capture is gated on `capture_trace`, not on `role` alone. ADR-0002 §Decision binds the *combination*; the parameters are orthogonal at the API.
- [ ] When `role == SandboxRole.GATE` and `capture_trace=True` is passed, the call raises `ValueError` whose `str(exc)` **exact-matches** `"capture_trace requires role=SandboxRole.PROBE"`. Pinned with `match=r"^capture_trace requires role=SandboxRole\.PROBE$"` (anchored regex — a substring-only match would let a message like `"capture_trace requires role=SandboxRole.PROBE and network=isolated"` silently pass).

### D. Audit-log `role` field (ADR-0003 §Consequences row 3)

- [ ] Every `spawn(...)` call emits an audit-log event whose Pydantic schema includes a `role: SandboxRole` field. The field is **additive** to the existing schema; existing fields are unchanged.
- [ ] **Role is the *only* new field on the audit event.** A test captures the pre-amendment `SpawnDispatchedEvent.model_fields` field-set (recorded as a `Final[frozenset[str]]` in the test file) and asserts `set(post.model_fields) - PRE_FIELDS == {"role"}` — no accidental extra field slipped in during the amendment.
- [ ] `extra="forbid"` is preserved: an audit event with a typo (`{"role_": "gate"}`) fails Pydantic validation; a payload with no `role` field at all also fails (the field is required post-amendment).
- [ ] The audit-log JSON round-trips **with enum identity**: `SpawnDispatchedEvent.model_validate_json(dumps({"kind": "spawn.dispatched", "role": SandboxRole.PROBE.value, ...})).role is SandboxRole.PROBE` (identity, not `==`; a `str` bleed would silently pass equality).
- [ ] **Coordinated golden refresh.** Every audit event in the Phase 5 regression suite under `tests/golden/sandbox/audit/*.json` is updated additively (one new `role: "gate"` field per record) and the golden-diff fence accepts the change as a single coordinated edit. **A companion test seeds a synthetic golden file missing the `role` field and asserts the fence flags it** (proves the refresh discipline, not just that the refresh happened this once). No other field changes.

### E. Byte-edit allowlist fence

- [ ] S5-01's `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` passes after this story's edits. The fence verifies that `src/codegenie/sandbox/client.py` carries exactly: S6-01's enum block + S6-02's parameter addition(s) (`role`, and `capture_trace` if Path B under Preconditions §3) + S6-02's dispatch wire-up + the additive `role` field on the audit-event model. Any *other* byte-edit to `client.py` (formatting, docstring rewrites, unrelated refactors) is rejected.
- [ ] A deliberately-planted third additive parameter on `spawn(...)` (e.g., `extra_flag: bool = False` — distinct from the authorized `role` and `capture_trace`) fails the fence; the error message names `client.py` and the unauthorized additive diff. **Under Path A (Preconditions §3), a planted `capture_trace` addition is the failing case here** (Path A says `capture_trace` is pre-existing, so adding it is an unauthorized edit).
- [ ] A deliberately-planted unrelated method-body refactor inside `spawn(...)` (e.g., renaming an internal local from `spec_with_role` to `enriched_spec`) fails the fence — proves the fence catches structural drift on the method body, not just signature diffs.

### F. Type-check + style + import-linter

- [ ] `mypy --strict src/codegenie/sandbox/` clean.
- [ ] `ruff check src/codegenie/sandbox/` + `ruff format --check src/codegenie/sandbox/` clean.
- [ ] `make lint-imports` green (no LLM SDK reachable from the sandbox module).
- [ ] `make check` green end-to-end.

### G. Concurrency safety

- [ ] Two concurrent `spawn(...)` calls with **different** roles — one `role=SandboxRole.GATE` and one `role=SandboxRole.PROBE` — emit audit events with correct, un-swapped role tags. Test runs the two calls via `asyncio.gather(...)` against the recording stub backend and asserts each captured event's `role` matches the role its own caller passed. Guards against a stealth shared-mutable-state introduction (e.g., a module-level `_current_role` variable) that would swap the tags under contention. Cheap; single test.

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

import asyncio
import inspect
import re
from typing import Final

import pytest
from pydantic import ValidationError

from codegenie.sandbox import Role
from codegenie.sandbox.client import SandboxClient, SandboxRole, SpawnDispatchedEvent

# Pre-amendment audit-event field-set. Frozen so a stealth extra field slipping
# in with `role` fails test_audit_event_role_is_only_new_field.
_PRE_AMENDMENT_EVENT_FIELDS: Final[frozenset[str]] = frozenset({
    # ... enumerate every Phase-5 field on the audit event; grep
    # `src/codegenie/sandbox/` for the shipped model to fill in.
})


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

    def test_positional_role_raises_type_error(self, stub_client, gate_spec) -> None:
        # Signature-shape test above proves declaration; this test proves
        # runtime enforcement. A `**kwargs` rewrite could pass the shape check
        # while silently accepting positional role.
        with pytest.raises(TypeError, match=r"role"):
            stub_client.spawn(gate_spec, SandboxRole.GATE)  # type: ignore[misc]

    def test_no_other_signature_changes(self) -> None:
        # Field-by-field diff against pre-amendment shape + authorized additive params.
        # PRE_SHAPE captured from a git worktree of pre-amendment main.
        params = inspect.signature(SandboxClient.spawn).parameters
        additive = {"role", "capture_trace"}  # narrow to {"role"} under Path A
        for name, p in params.items():
            if name in additive:
                continue
            pre = PRE_SHAPE[name]  # from a fixture-captured baseline
            assert p.name == pre.name
            assert p.kind == pre.kind
            assert p.default == pre.default
            assert p.annotation == pre.annotation


class TestDefaultPathByteIdentity:
    @pytest.fixture
    def stub_client(self) -> SandboxClient:
        # Construct a Phase-5-canonical SandboxClient stub. Exact shape
        # depends on Phase 5's shipped constructor (Preconditions §1).
        ...

    def test_default_arg_run_byte_equals_role_gate_run(self, stub_client: SandboxClient, gate_spec) -> None:
        default = stub_client.spawn(gate_spec)
        explicit = stub_client.spawn(gate_spec, role=Role.GATE)
        assert _normalize_run_for_byte_identity(default) == _normalize_run_for_byte_identity(explicit)

    @pytest.mark.parametrize("spec", HAND_CRAFTED_5_SPEC_MATRIX)
    def test_default_arg_byte_equivalence_across_spec_matrix(self, stub_client, spec) -> None:
        # Hand-crafted 5 SandboxSpec variations (differing command, workspace,
        # env, time_budget_seconds, network). NOT hypothesis — fixed inputs.
        default = stub_client.spawn(spec)
        explicit = stub_client.spawn(spec, role=Role.GATE)
        assert _normalize_run_for_byte_identity(default) == _normalize_run_for_byte_identity(explicit)

    def test_normalized_fields_enumerated(self) -> None:
        # Guards against a stealth addition to the sentinel-normalized list —
        # if someone silently normalizes a new field, this test surfaces it.
        from tests.unit.sandbox.test_spawn_role_parameter import (
            _NORMALIZED_FIELD_PATHS,
        )
        assert _NORMALIZED_FIELD_PATHS == (
            "started_at",
            "finished_at",
            "duration_ms",
            "run_id",
            "sandbox_spec_hash",
            "audit_events[*].timestamp",
            "audit_events[*].event_id",
        )

    def test_no_phase5_production_callsite_passes_role(self) -> None:
        # Object-scoped regex per Preconditions §6.
        pattern = re.compile(
            r"(?:sandbox|SandboxClient|sandbox_client|self\.sandbox)\.(?:spawn|execute)\("
        )
        # ... walk src/codegenie/ (excluding sandbox/) and
        # plugins/vulnerability-remediation--node--npm/; for each match,
        # assert the argument list does NOT contain role=.
        ...

    def test_grep_scope_is_object_scoped(self) -> None:
        # Meta-test the regex itself. Prevents a naive `spawn(` scan from
        # false-positive on Process.spawn and false-negative on obj.spawn.
        pattern = re.compile(
            r"(?:sandbox|SandboxClient|sandbox_client|self\.sandbox)\.(?:spawn|execute)\("
        )
        assert not pattern.search("Process.spawn(role=1)")
        assert not pattern.search("multiprocessing.Process.spawn_context()")
        assert pattern.search("self.sandbox.spawn(spec, role=Role.GATE)")


class TestProbePath:
    def test_capture_trace_with_gate_raises(self, stub_client, gate_spec) -> None:
        with pytest.raises(
            ValueError,
            match=r"^capture_trace requires role=SandboxRole\.PROBE$",  # anchored, exact
        ):
            stub_client.spawn(gate_spec, role=Role.GATE, capture_trace=True)

    def test_probe_role_audit_event_carries_role_enum(self, stub_client, probe_spec) -> None:
        run = stub_client.spawn(probe_spec, role=Role.PROBE)
        # Identity, not equality — guards against a str bleed into audit events.
        assert any(e.role is SandboxRole.PROBE for e in run.audit_events)

    def test_probe_role_without_capture_trace_succeeds(self, stub_client, probe_spec) -> None:
        # role and capture_trace are orthogonal at the API.
        run = stub_client.spawn(probe_spec, role=Role.PROBE, capture_trace=False)
        assert run.exit_status.success or run.exit_status.failed_for_known_reason

    def test_capture_trace_dispatch_propagation(self, recording_backend_client, probe_spec) -> None:
        # Positive: role=PROBE + capture_trace=True → dispatcher spec carries both.
        recording_backend_client.spawn(probe_spec, role=Role.PROBE, capture_trace=True)
        last_spec = recording_backend_client.backend.last_spec
        assert last_spec.role is SandboxRole.PROBE
        assert last_spec.capture_trace is True

    def test_capture_trace_not_leaked_when_role_gate(self, recording_backend_client, gate_spec) -> None:
        # Negative orthogonality: default GATE path never leaks capture_trace=True.
        recording_backend_client.spawn(gate_spec)  # default role, default capture_trace
        last_spec = recording_backend_client.backend.last_spec
        assert last_spec.role is SandboxRole.GATE
        assert last_spec.capture_trace is False


class TestAuditEventSchema:
    def test_audit_event_includes_role_field(self) -> None:
        assert "role" in SpawnDispatchedEvent.model_fields

    def test_audit_event_role_is_only_new_field(self) -> None:
        # No accidental extra field snuck in with role.
        new_fields = set(SpawnDispatchedEvent.model_fields) - _PRE_AMENDMENT_EVENT_FIELDS
        assert new_fields == {"role"}

    def test_audit_event_extra_forbid_preserved(self) -> None:
        with pytest.raises(ValidationError):
            SpawnDispatchedEvent(kind="spawn.dispatched", role="gate", typo=1)  # type: ignore[call-arg]

    def test_audit_event_role_is_required(self) -> None:
        with pytest.raises(ValidationError):
            SpawnDispatchedEvent(kind="spawn.dispatched")  # type: ignore[call-arg]  # no role

    def test_round_trip_identity_not_equality(self) -> None:
        import json
        payload = json.dumps({"kind": "spawn.dispatched", "role": SandboxRole.PROBE.value})
        event = SpawnDispatchedEvent.model_validate_json(payload)
        # Identity, not equality — guards against a str bleed.
        assert event.role is SandboxRole.PROBE


class TestConcurrencySafety:
    async def test_concurrent_spawn_role_tags_correct(self, recording_backend_client, gate_spec, probe_spec) -> None:
        # No shared-mutable-state introduction can silently swap the tags.
        gate_call = recording_backend_client.spawn(gate_spec, role=Role.GATE)
        probe_call = recording_backend_client.spawn(probe_spec, role=Role.PROBE, capture_trace=True)
        gate_run, probe_run = await asyncio.gather(gate_call, probe_call)
        assert all(e.role is SandboxRole.GATE for e in gate_run.audit_events)
        assert any(e.role is SandboxRole.PROBE for e in probe_run.audit_events)
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

- **Method-name Precondition link-back (Rule 7 — Surface conflicts, don't average them):** the `spawn` vs `execute` reconciliation is elevated to a blocking Precondition (§2), not a Note. Before writing code, resolve the name by reading the shipped `src/codegenie/sandbox/client.py`. If Phase 5 ships `execute`, extend `execute(...)` additively with the same `role` parameter — log the resolution in `_attempts/S6-02.md`. Do **not** silently rename.
- **`capture_trace` amendment dance (Preconditions §3).** The story adds two additive parameters: `role` AND `capture_trace`. ADR-0003 §Decision says "gains exactly one new parameter." Two paths: **Path A** — `capture_trace` was pre-existing on Phase 5's `SandboxClient` / `SandboxSpec`; grep confirms; no ADR amendment needed. **Path B** — `capture_trace` is new here; file `ADRs/0003-amendment-capture-trace.md` (Nygard shape) **before** landing the code edit and widen S5-01's fence file's `# row 6` inline comment. Both paths preserve the arch design (line 813 shows the consumer calling with `capture_trace=True`); the choice is which artifact carries the audit trail. Do not silently widen ADR-0003.
- **Default-arg byte-identity is the load-bearing claim.** The single largest risk in this story is a stealth behavioral change on the default path. AC-B's golden file (`tests/golden/sandbox/spawn_default_run.json`) is the canonical check; the property-style sweep across 5 spec variations is the secondary check. If you cannot reproduce byte-identity on a clean Phase 5 fixture, **stop and ask** — do not lower the bar.
- **Why `capture_trace` is orthogonal to `role`:** ADR-0002 §Decision binds `Role.PROBE + capture_trace=True` as the canonical shell-trace probe shape. But `Role.PROBE` alone (without trace capture) is reserved as the audit-log distinction even when no trace is needed — a future Phase 8 Planner may schedule a probe-tagged microVM for a different purpose that doesn't need eBPF. Keep the parameters orthogonal at the API; raise only on the impossible combination (`capture_trace + Role.GATE`).
- **`SpawnDispatchedEvent` (or whatever Phase 5 names its audit-event Pydantic model) gains a `role` field additively.** Phase 5's `extra="forbid"` discipline (Phase 5 ADR-0001 / final-design §6) prevents silent field smuggling; the additive `role` field is the *one* explicit Phase 7 extension. Update Phase 5's golden audit JSON files in lockstep.
- **The byte-edit allowlist fence (S5-01) will fail if you touch anything else in `client.py`.** Resist "while I'm here" formatting changes (Rule 3 — Surgical Changes). If the file needs a docstring update or a refactor to accommodate the parameter, surface it in the Notes section and propose an ADR amendment to row #6 — do not silently widen.
- **The fallback ADR-0003 §Reversibility names** (route `Role.PROBE` through `Role.GATE` semantics if Phase 5 rejects the amendment) is **not in scope for this story.** This story assumes Phase 5 ratifies. If the fallback is invoked, AC-C bullet 2 changes — log that in the attempt log and reopen.
- **No `cost_band`, no `applies_when` on `spawn(...)` either.** ADR-0003's minimum-surface principle extends to the parameter list: one new parameter (`role`), one related orthogonal flag (`capture_trace`), no other additions.
- **Read [Phase 5 final-design §Components §1](../../05-sandbox-trust-gates/final-design.md)** before touching the method body — it documents which backends register and how the spec flows. The amendment must compose with `DockerInDockerClient`, `FirecrackerClient`, and whatever Lima-based backend Phase 5 ends up shipping for macOS.
- **Grep false-positive risk (Preconditions §6).** Naive `spawn(` scans hit `asyncio.subprocess.Process.spawn`, `multiprocessing.Process.spawn_context`, `subprocess.Popen(...).spawn_...` — false positives that would spuriously fail AC-B's grep test. Use the object-scoped regex from Preconditions §6 (or an AST-based check) and pin the regex itself with the meta-test `test_grep_scope_is_object_scoped`. If Phase 5 uses a different attribute name for the injected `SandboxClient` (e.g., `self._sandbox` with the leading underscore), extend the regex — do not accept false negatives.
- **`SandboxSpec.model_copy(update=...)` subtlety.** Pydantic v2's `model_copy(update={"role": role, "capture_trace": capture_trace})` **bypasses `extra="forbid"` at copy time** — it silently adds the new keys to the model instance even if the model class does not declare them. If the receiving backend dispatcher validates the spec structurally (via `model_dump()` → re-parse) it will catch the drift; if it inspects `spec.role` and `spec.capture_trace` by attribute access it will succeed silently. Either (a) extend `SandboxSpec`'s class definition to declare `role: SandboxRole = SandboxRole.GATE` and `capture_trace: bool = False` as first-class fields (respecting Phase 5's `extra="forbid"` invariant), or (b) file a matching amendment in the same PR that adds these fields to `SandboxSpec`. Do not rely on `model_copy(update=...)` alone as the schema-extension mechanism.
