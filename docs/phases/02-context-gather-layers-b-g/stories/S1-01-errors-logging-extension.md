# Story S1-01 — Errors + logging extension for tools, sandbox, audit, sanitizer

**Step:** Step 1 — Plant sandbox extension, tool wrappers, tool-digest pin manifest, and the four Phase-0/1 in-place edits
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0001, ADR-0003, ADR-0004, ADR-0006, ADR-0012

## Context

Phase 2 introduces seven external tool wrappers, two new sanitizer passes, a rolling BLAKE3 audit chain, the `consumes_peer_outputs` coordinator branch, and the `IndexHealthProbe` advisory budget. Every one of those raise/log sites needs a typed exception and a registered structlog event name *before* the implementations land — otherwise stories S1-02 through S1-11 each introduce ad-hoc error strings and divergent log keys that drift apart in review. This story is the prerequisite for every other Step 1 story; nothing else compiles cleanly until the names exist.

Phase 0 already ships `CodegenieError` with nine subclasses (Phase 0 S2-01) and a `logging.py` module of structlog event constants (Phase 0 S2-04). Phase 1 extended `errors.py` with six more subclasses additively. Phase 2 follows the same pattern — additive extension only, no edits to existing subclasses or constants.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Agentic best practices" → "Error escalation"` — names the nine new Phase 2 subclasses and the rule that `CodegenieError` itself is unchanged.
  - `../phase-arch-design.md §"Component design" #2 (`tools/` wrappers)` — `ToolNotFound`/`ToolTimeout`/`ToolNonZeroExit`/`ToolOutputMalformed`/`ToolInvariantViolation` are the typed exception set every wrapper raises.
  - `../phase-arch-design.md §"4+1 architectural views" "Logical view"` — `audit.chain_break.detected` and `index_health.budget_exceeded` event names with their structured fields.
- **Phase ADRs:**
  - `../ADRs/0001-peer-outputs-binding.md` — ADR-0001 — `probe.peer_outputs.snapshot_built` event fires once per gather when the frozen snapshot is built.
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — ADR-0003 — `probe.sandbox.network_egress_attempted` event + `sandbox_network` structured field; `SandboxLaunchError` raised on `bwrap`/`sandbox-exec` failure.
  - `../ADRs/0006-output-sanitizer-passes-4-5.md` — ADR-0006 — `probe.sanitizer.pass4_fingerprint`, `probe.sanitizer.pass5_marker_detected` events.
  - `../ADRs/0011-index-health-advisory-budget-and-strict-flag.md` — ADR-0011 — `index_health.budget_exceeded` event (advisory; never fails the gather).
  - `../ADRs/0012-audit-chain-blake3-rolling-head.md` — ADR-0012 — `audit.chain_head.advanced` + `audit.chain_break.detected` events; `AuditChainBreakDetected` is **not** raised — it is an observability event, not an exception. The "exception" class with that name (per `High-level-impl.md` Step 1 "Features delivered") is a typed marker only; document this clearly.
- **Source design:**
  - `../final-design.md §"Components" #9 OutputSanitizer — Pass 4 + Pass 5` — sanitizer event names.
  - `../final-design.md §"Failure modes & recovery"` — every Phase 2 failure path maps to one of the nine new typed exceptions.
- **Existing code:**
  - `src/codegenie/errors.py` (Phase 0 S2-01 + Phase 1 S1-01) — extend `__all__` and append nine classes; do not edit existing subclasses.
  - `src/codegenie/logging.py` (Phase 0 S2-04) — extend the event-name `Final[str]` constants block; do not edit existing constants.
  - `tests/unit/test_errors.py` (Phase 0/1) — extend `EXPECTED_SUBCLASSES`.

## Goal

Extend `src/codegenie/errors.py` with nine new `CodegenieError` subclasses and `src/codegenie/logging.py` with eight new structlog event-name constants plus two new structured-field constants, so every Step 1 story has the named primitives it raises and logs into.

## Acceptance criteria

- [ ] `src/codegenie/errors.py` exports `ToolNotFound`, `ToolTimeout`, `ToolNonZeroExit`, `ToolOutputMalformed`, `ToolInvariantViolation`, `SandboxLaunchError`, `SkillLoadError`, `CatalogLintMismatch`, `AuditChainBreakDetected`; each inherits from `CodegenieError`; each is in `errors.__all__`.
- [ ] Each tool exception's `__init__` is keyword-only and accepts `tool_name: str` plus exception-specific fields (`stderr_excerpt: str` for `ToolNonZeroExit`; `invariant: str` for `ToolInvariantViolation`; `timeout_s: float` for `ToolTimeout`; `detail: str` for `ToolOutputMalformed`; no extras for `ToolNotFound`). Attributes are recoverable from the caught instance.
- [ ] `AuditChainBreakDetected` carries `previous_hash_expected: str` and `previous_hash_actual: str`; its docstring explicitly states it is an observability marker, never raised to fail a gather (ADR-0012).
- [ ] `src/codegenie/logging.py` defines `Final[str]` constants for `PROBE_TOOL_INVOKED = "probe.tool.invoked"`, `PROBE_SANDBOX_NETWORK_EGRESS_ATTEMPTED = "probe.sandbox.network_egress_attempted"`, `PROBE_SANITIZER_PASS4_FINGERPRINT = "probe.sanitizer.pass4_fingerprint"`, `PROBE_SANITIZER_PASS5_MARKER_DETECTED = "probe.sanitizer.pass5_marker_detected"`, `AUDIT_CHAIN_HEAD_ADVANCED = "audit.chain_head.advanced"`, `AUDIT_CHAIN_BREAK_DETECTED = "audit.chain_break.detected"`, `PROBE_PEER_OUTPUTS_SNAPSHOT_BUILT = "probe.peer_outputs.snapshot_built"`, `INDEX_HEALTH_BUDGET_EXCEEDED = "index_health.budget_exceeded"`.
- [ ] `src/codegenie/logging.py` defines the two new structured-field name constants `FIELD_TOOL_NAME = "tool_name"` and `FIELD_SANDBOX_NETWORK = "sandbox_network"`.
- [ ] `tests/unit/test_errors.py` extends `EXPECTED_SUBCLASSES` with the nine new names; asserts each subclass is in `__all__`; asserts attribute round-tripping on a sample instance per class.
- [ ] `tests/unit/test_logging.py` (extend existing) asserts the eight new event constants are present, typed `Final[str]`, and match the documented string values verbatim.
- [ ] No Phase 0 or Phase 1 subclass / constant is edited; the diff is append-only on both files.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Extend `tests/unit/test_errors.py` first (red) — append the nine new names to `EXPECTED_SUBCLASSES`; add an attribute round-trip test per class.
2. Extend `tests/unit/test_logging.py` (red) — assert the eight new event-name constants and two new field constants exist and equal the documented strings.
3. Append the nine subclasses to `src/codegenie/errors.py`. Each subclass:
   - One-line docstring naming its raise site (e.g., `"""Raised by tools.* wrappers when the binary is not on $PATH."""`).
   - Keyword-only `__init__` storing typed attributes, then `super().__init__(f"{tool_name}: ...")` for `str(exc)`.
4. Append the eight event constants + two field constants to `src/codegenie/logging.py` under a `# Phase 2 — additive` block comment.
5. Extend `__all__` on both files.
6. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/errors.py src/codegenie/logging.py tests/unit/test_errors.py tests/unit/test_logging.py`, `pytest tests/unit/test_errors.py tests/unit/test_logging.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_errors.py` (extend) and `tests/unit/test_logging.py` (extend).

```python
# tests/unit/test_errors.py — Phase 2 extension
import codegenie.errors as e

EXPECTED_PHASE2_SUBCLASSES = {
    "ToolNotFound", "ToolTimeout", "ToolNonZeroExit",
    "ToolOutputMalformed", "ToolInvariantViolation",
    "SandboxLaunchError", "SkillLoadError",
    "CatalogLintMismatch", "AuditChainBreakDetected",
}

def test_phase2_subclasses_present_and_in_all():
    # arrange: import the module
    # assert: every Phase 2 subclass is a CodegenieError and exported in __all__
    for name in EXPECTED_PHASE2_SUBCLASSES:
        cls = getattr(e, name)
        assert issubclass(cls, e.CodegenieError)
        assert name in e.__all__

def test_tool_non_zero_exit_carries_stderr_excerpt():
    # arrange/act: construct with documented kwargs
    exc = e.ToolNonZeroExit(tool_name="semgrep", exit_code=2, stderr_excerpt="rule parse error")
    # assert: attributes recoverable; str(exc) informative for structlog
    assert exc.tool_name == "semgrep"
    assert exc.exit_code == 2
    assert "rule parse error" in str(exc)

def test_audit_chain_break_detected_carries_hash_pair():
    exc = e.AuditChainBreakDetected(previous_hash_expected="a" * 64, previous_hash_actual="b" * 64)
    assert exc.previous_hash_expected.startswith("a")
    # docstring documents observability-only contract
    assert "observability" in (e.AuditChainBreakDetected.__doc__ or "").lower()
```

```python
# tests/unit/test_logging.py — Phase 2 extension
import codegenie.logging as L

def test_phase2_event_constants_present_with_documented_strings():
    assert L.PROBE_TOOL_INVOKED == "probe.tool.invoked"
    assert L.PROBE_SANDBOX_NETWORK_EGRESS_ATTEMPTED == "probe.sandbox.network_egress_attempted"
    assert L.PROBE_SANITIZER_PASS4_FINGERPRINT == "probe.sanitizer.pass4_fingerprint"
    assert L.PROBE_SANITIZER_PASS5_MARKER_DETECTED == "probe.sanitizer.pass5_marker_detected"
    assert L.AUDIT_CHAIN_HEAD_ADVANCED == "audit.chain_head.advanced"
    assert L.AUDIT_CHAIN_BREAK_DETECTED == "audit.chain_break.detected"
    assert L.PROBE_PEER_OUTPUTS_SNAPSHOT_BUILT == "probe.peer_outputs.snapshot_built"
    assert L.INDEX_HEALTH_BUDGET_EXCEEDED == "index_health.budget_exceeded"

def test_phase2_field_constants_present():
    assert L.FIELD_TOOL_NAME == "tool_name"
    assert L.FIELD_SANDBOX_NETWORK == "sandbox_network"
```

Run; confirm `AttributeError` on every new name. Commit as red marker.

### Green — make it pass

Append nine classes to `src/codegenie/errors.py`:

- `class ToolNotFound(CodegenieError)` — `__init__(self, *, tool_name: str)`.
- `class ToolTimeout(CodegenieError)` — `__init__(self, *, tool_name: str, timeout_s: float)`.
- `class ToolNonZeroExit(CodegenieError)` — `__init__(self, *, tool_name: str, exit_code: int, stderr_excerpt: str)`.
- `class ToolOutputMalformed(CodegenieError)` — `__init__(self, *, tool_name: str, detail: str)`.
- `class ToolInvariantViolation(CodegenieError)` — `__init__(self, *, tool_name: str, invariant: str)`.
- `class SandboxLaunchError(CodegenieError)` — `__init__(self, *, detail: str)`.
- `class SkillLoadError(CodegenieError)` — `__init__(self, *, path: Path, detail: str)`.
- `class CatalogLintMismatch(CodegenieError)` — `__init__(self, *, lint: str, detail: str)`.
- `class AuditChainBreakDetected(CodegenieError)` — `__init__(self, *, previous_hash_expected: str, previous_hash_actual: str)`; docstring explicitly: `"""Marker for the audit.chain_break.detected observability event. Never raised to fail a gather (ADR-0012)."""`.

Append eight `Final[str]` event constants and two field constants to `src/codegenie/logging.py`.

### Refactor — clean up

- Module-level docstrings on both files extended with a one-line "Phase 2 additive extension per ADR-0001/0003/0004/0006/0011/0012" note.
- `__all__` re-sorted (alphabetical) on both files — touching `__all__` is permitted by Rule 3 because the file's purpose includes maintaining `__all__`.
- Confirm `mypy --strict` is clean — each `__init__` is keyword-only (`*`); attributes typed; `super().__init__(...)` carries the formatted message for `str(exc)` rendering in logs.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/errors.py` | Append nine subclasses; extend `__all__` |
| `src/codegenie/logging.py` | Append eight event constants + two field constants; extend `__all__` |
| `tests/unit/test_errors.py` | Extend `EXPECTED_SUBCLASSES`; add attribute round-trip tests |
| `tests/unit/test_logging.py` | Add presence + value assertions for new constants |

## Out of scope

- **Raising the new exceptions from wrappers / coordinator / sanitizer / audit** — those raise sites land in S1-02 (`exec.py`), S1-05/06/07 (wrappers), S1-09 (sanitizer), S1-10 (audit), S1-11 (coordinator). This story is the type definitions only.
- **Emitting the new event constants in production code** — emissions land in the consuming stories (e.g., `probe.tool.invoked` in S1-05/06/07; `audit.chain_head.advanced` in S1-10).
- **A `WarningId` enum extension** — Phase 1 deferred this; Phase 2 carries the deferral forward.
- **Re-exporting from `codegenie/__init__.py`** — Phase 0 does not re-export `errors` or `logging`; do not start.

## Notes for the implementer

- `AuditChainBreakDetected` is named like an exception class but is *never raised* — it is the typed marker for the `audit.chain_break.detected` observability event payload. Per ADR-0012 and Rule 12 (Fail loud), the audit writer logs and *continues*; the typed class exists so tests can assert "this event family fired" via the typed shape rather than a string match. Document this in the class docstring.
- Keyword-only `__init__` (`def __init__(self, *, tool_name, ...)`) is mandatory across all nine. The Phase 0 subclasses did not enforce keyword-only; Phase 1 did. Phase 2 follows Phase 1's precedent (Rule 11 — match the most recent convention).
- Do **not** subclass `subprocess.CalledProcessError` for `ToolNonZeroExit`; everything is `CodegenieError` so the CLI's top-level catch (Phase 0 S4-02) treats them uniformly.
- `SkillLoadError` accepts `path: Path` — this is the SKILL.md path the loader was trying to read. Storing it makes the structlog rendering include the offending file (load-bearing for triage in S2-01).
- The `stderr_excerpt` stored on `ToolNonZeroExit` is the *first 4 KiB* of stderr — wrappers (S1-05/06/07) truncate before raising. Do not store unbounded stderr; the cap belongs to the raise site, not the exception type.
- This file is not in `CODEOWNERS`-routed paths; `errors.py` and `logging.py` are allowed to grow by addition. The frozen contract is `Probe` (S1-11), not `CodegenieError`.
- `ToolDigestMismatch` is **not** in this story's set — ADR-0005 references it, but it is added in S1-08 alongside the digest verifier (one of the four new typed exceptions there is `ToolDigestMismatch`). Keep this story's nine names verbatim from `High-level-impl.md` Step 1; resist the urge to pre-add a tenth.
