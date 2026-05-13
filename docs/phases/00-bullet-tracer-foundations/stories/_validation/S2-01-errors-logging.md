# Validation report: S2-01 — Error hierarchy + structlog config

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S2-01 plants the two cross-cutting primitives every later Phase-0 story imports: `errors.py` (a `CodegenieError` root + nine marker subclasses) and `logging.py` (`configure_logging(verbose)` + six `EVENT_PROBE_*` string constants). The story was well-structured but its acceptance criteria left ~half of the goal unverified: AC-3 explicitly required *three* behaviors (JSON-on-non-TTY, pretty-on-TTY, `verbose=True`→DEBUG) and the TDD plan only covered the first; AC-1 required each subclass to have a "raise-site docstring" but no test enforced it; the implementer-note "constants are plain `str`, not `enum.StrEnum`" was load-bearing doctrine for Phase 6/13 subscribers but lived only in prose. None of these were structural goal problems — all were patchable in place. Two blocks (missing tests for AC-3 branches) and nine hardens were applied; an AC-7 was added for `configure_logging` re-entrancy/idempotence (structlog mutates process-global state, so double-config without a clean re-apply is a real failure mode for Phase 6/13 CLI startup). One nit deferred: writing an ADR amendment for the StrEnum doctrine — captured in the implementer notes and pinned by AC-5's `type(...) is str` test instead.

## Findings by critic

### Coverage critic

#### F-COV-1: AC-4 does not pin the docstring requirement promised by AC-1
- **Severity:** harden
- **Type:** unverifiable AC
- **Where:** AC-1 / AC-4
- **Why it matters:** AC-1 says each subclass "carries a docstring naming the raise site," but AC-4 only asserts existence + inheritance + `__all__`. A subclass with `pass` and no docstring would pass CI yet violate the contract. Phase 0's "honest provenance" posture depends on these markers actually documenting where they're raised.
- **Proposed fix:** Append to AC-4: "...and asserts `cls.__doc__` is a non-empty string that mentions the raising module name (one of `exec`, `cache`, `sanitizer`, `validator`, `writer`, `coordinator`, `config`, `tool_check`, `schema`)."

#### F-COV-2: No AC pins the event-name constant *closure*
- **Severity:** harden
- **Type:** missing AC
- **Where:** AC-2 / AC-5
- **Why it matters:** AC-2 lists 6 names individually, but unlike `errors.py` (which AC-4 closes via `EXPECTED_SUBCLASSES`), a future PR could silently add `EVENT_PROBE_RETRY` or `EVENT_PROBE_BUDGET`. Phase 6 SHERPA + Phase 13 cost ledger subscribe to *exactly* this set unchanged; expansion is a contract change requiring an ADR.
- **Proposed fix:** Add AC: `tests/unit/test_logging.py` asserts the set `{name for name in dir(cgl) if name.startswith('EVENT_PROBE_')}` equals exactly the six documented names.

#### F-COV-3: No AC protects against StrEnum conversion
- **Severity:** harden
- **Type:** missing AC
- **Where:** missing
- **Why it matters:** The implementer note warns against `enum.StrEnum` but nothing in the ACs enforces it. A `StrEnum` member equals its string value, so AC-2's equality assertions would still pass while `from codegenie.logging import EVENT_PROBE_START` returns an enum member, breaking string-key subscribers in Phase 6/13.
- **Proposed fix:** Add AC: `test_logging.py` asserts `type(cgl.EVENT_PROBE_START) is str` for each constant.

#### F-COV-4: `configure_logging` re-entrancy not specified
- **Severity:** harden
- **Type:** edge case
- **Where:** AC-3 / missing
- **Why it matters:** `structlog.configure()` mutates global state. Phase 6/13 CLI startup may invoke it after test imports already configured it; silently overwriting is a real failure mode. Goal is "configured once in `logging.py` from `cli.py`" (arch §Harness).
- **Proposed fix:** Add AC: `configure_logging` is idempotent — twice with the same `verbose` produces identical final structlog config; with different `verbose` re-applies cleanly.

#### F-COV-5: `verbose=False` default not pinned
- **Severity:** nit
- **Type:** vague AC
- **Where:** AC-2
- **Why it matters:** AC-2 declares the signature `configure_logging(verbose: bool) -> None` — note no default. The goal calls `configure_logging(verbose=False)` as a default-elided invocation. Ambiguous.
- **Proposed fix:** Change signature to `configure_logging(verbose: bool = False) -> None`; add `inspect.signature` default check.

#### F-COV-6: JSON-on-non-TTY assertion is permissive
- **Severity:** nit
- **Type:** weak trace
- **Where:** AC-5 / TDD red sample
- **Why it matters:** The sample test parses `splitlines()[-1]` — any non-JSON noise on earlier lines passes. The goal is JSON output, not "the last line happens to be JSON."
- **Proposed fix:** Strengthen to "every non-empty line of captured stderr parses as JSON."

#### F-COV-7: Sensitive-value-redaction commitment unowned
- **Severity:** nit
- **Type:** missing AC (scope check)
- **Where:** missing
- **Why it matters:** Arch §Harness line 755 commits "env vars, /Users/ paths never logged at INFO." This story ships `configure_logging` but no AC encodes redaction. The Out-of-scope section doesn't claim or deflect it.
- **Proposed fix:** Add explicit non-goal deferring redaction to first caller (option (b) — honest deferral rather than duplicating ADR-0008's chokepoint).

#### F-COV-8: `__all__` not required for `logging.py`
- **Severity:** nit
- **Type:** missing AC
- **Where:** AC-2 / AC-5
- **Why it matters:** Errors module pins `__all__` but logging module doesn't, despite exporting seven public names that Phase 6/13 import.
- **Proposed fix:** Add `__all__` requirement + closure test.

### Test-Quality critic

#### F-TQ-1: AC-3 `verbose=True`/DEBUG level has zero test coverage
- **Severity:** block
- **Type:** missing test for stated AC
- **Mutation that slips:** `wrapper_class=structlog.make_filtering_bound_logger(logging.INFO)` — hardcoded INFO regardless of `verbose`. AC-3 explicitly mandates the verbose→DEBUG behavior; the TDD plan body shows no test.
- **Proposed fix:** Add `test_verbose_true_enables_debug` and `test_verbose_false_silences_debug`.

#### F-TQ-2: AC-3 pretty-on-TTY branch has zero test coverage
- **Severity:** block
- **Type:** missing test for stated AC
- **Mutation that slips:** `processors=[structlog.processors.JSONRenderer()]` unconditionally. Non-TTY test passes; TTY branch never exercised.
- **Proposed fix:** Add `test_configure_logging_pretty_on_tty_is_not_json`.

#### F-TQ-3: `structlog.configure` mutates process-global state with no teardown
- **Severity:** harden
- **Mutation that slips:** Test order coupling — a prior test's config leaks in; the new test's config leaks downstream.
- **Proposed fix:** Autouse `_reset_structlog` fixture calling `structlog.reset_defaults()`.

#### F-TQ-4: Subclass test does not pin the hierarchy *closure*
- **Severity:** harden
- **Mutation that slips:** A typo-named `ProbErrror(CodegenieError)` added alongside the correct nine. Iterating `EXPECTED_SUBCLASSES` only pins the floor, not the ceiling.
- **Proposed fix:** `assert set(e.__all__) == EXPECTED_SUBCLASSES | {"CodegenieError"}`.

#### F-TQ-5: `CodegenieError = Exception` aliasing passes every check
- **Severity:** harden
- **Mutation that slips:** Collapsing alias; whole typed hierarchy becomes vacuous.
- **Proposed fix:** `assert e.CodegenieError is not Exception` and `assert e.CodegenieError.__mro__[1] is Exception`.

#### F-TQ-6: Constants test allows `StrEnum` aliasing despite implementer-note ban
- **Severity:** harden
- **Mutation that slips:** `StrEnum`-based constants still satisfy `==`; the ban is doctrine-only.
- **Proposed fix:** `type(cgl.EVENT_PROBE_START) is str` (not `isinstance`).

#### F-TQ-7: Subclasses-are-markers invariant is unenforced
- **Severity:** nit
- **Mutation that slips:** Future contributor adds `def __init__(...)` to `ProbeTimeoutError`.
- **Proposed fix:** `cls.__init__ is e.CodegenieError.__init__` + `cls.__dict__.keys() <= {"__module__", "__qualname__", "__doc__"}`. Applied (worth doing — implementer note explicitly bans behavior on subclasses).

### Consistency critic

#### F-CON-1: Step header conflicts with `High-level-impl.md §Step 1`
- **Severity:** harden
- **Type:** step mis-assignment
- **Where:** story header
- **Source of truth:** `High-level-impl.md §Step 1` lines 32–33 list `errors.py` and `logging.py` as Step 1 deliverables; the story re-labels them as Step 2.
- **Resolution:** Story-writer's reclassification is defensible (ADR-0008/0012 typed-failure carriers live in Step 2), but should be explicit. Also `Depends on: S1-01` should be `S1-01..S1-05` to match the contracts-first ordering principle now that those stories have shipped.

#### F-CON-2: AC-1 requires docstring naming raise-site, but AC-4 test does not enforce it
- **Severity:** harden
- **Type:** AC-internal contradiction
- **Resolution:** AC-4 extended with docstring assertions. Folded with F-COV-1.

#### F-CON-3: Sensitive-value scrubbing commitment has no AC
- **Severity:** harden
- **Type:** AC contradicts arch
- **Source of truth:** `phase-arch-design.md §Harness engineering` line 755
- **Resolution:** Picked option (b) — honest deferral. Added explicit non-goal to Out-of-scope. Reasoning: ADR-0008's `OutputSanitizer` is the path-redaction chokepoint for ProbeOutput→YAML; duplicating it in the structlog pipeline would violate single-chokepoint discipline. Phase 0 has no INFO-level `/Users/`-bearing caller; deferral is honest.

#### F-CON-4: "Don't switch to enum.StrEnum" doctrine lives only in implementer notes
- **Severity:** nit
- **Resolution:** Folded with F-COV-3 / F-TQ-6 — the `type(...) is str` test makes the doctrine load-bearing. ADR amendment deferred.

### Items verified consistent (no finding)
- Subclass names (9): story AC-1, `EXPECTED_SUBCLASSES`, arch line 770, High-level-impl line 32 — all match.
- Event-name strings (6): story AC-2, TDD test, arch line 755 — all match.
- `final-design.md §2.14` exists (Logging section).
- `configure_logging(verbose: bool) -> None` signature matches High-level-impl line 33.
- ADR-0008 and ADR-0012 citations correct.
- CLAUDE.md load-bearing commitments — none violated.

## Research briefs

None. No critic finding required outside-pattern lookup; `type(...) is str` for StrEnum-guard and `structlog.reset_defaults()` for test isolation are idiomatic patterns already implied by the libraries' documented behavior.

## Conflict resolutions

- **F-COV-7 (defer redaction) vs F-CON-3 (add AC or non-goal):** Both converge on option (b) — honest deferral via Out-of-scope. Adding a redacting processor would duplicate ADR-0008's chokepoint; the Consistency critic's option (a) was rejected on single-chokepoint grounds.
- **F-COV-2 / F-COV-3 / F-COV-8 / F-TQ-4 / F-TQ-6 / F-CON-4 all converge on closure + StrEnum + `__all__` assertions:** consolidated into AC-5's test block.

## Edits applied

### Edit 1 — Header: Step-assignment note + `Depends on` expanded
- **Source:** Consistency F-CON-1
- **Rationale:** Surface the Step-1→Step-2 reclassification explicitly so readers don't read it as a contradiction; update `Depends on` to match the actually-shipped predecessor chain.

### Edit 2 — AC-1 hardened
- **Source:** Coverage F-COV-1 + Consistency F-CON-2
- **Before:** "each subclass inherits from `CodegenieError`, each carries a docstring naming the raise site"
- **After:** Direct inheritance + docstring ≥ 10 chars naming one of nine documented module slugs.

### Edit 3 — AC-2 hardened
- **Source:** Coverage F-COV-5, F-COV-8
- **Changes:** Signature now `verbose: bool = False`; `__all__` required listing all seven public names.

### Edit 4 — AC-4 hardened
- **Source:** Coverage F-COV-1, Test-Quality F-TQ-4, F-TQ-5, F-TQ-7
- **Changes:** Added (a) `__all__` closure equality, (b) `CodegenieError is not Exception` + direct-MRO check, (c) docstring length + slug check, (d) markers-only invariant (`__init__` inheritance + `__dict__` keys subset).

### Edit 5 — AC-5 hardened
- **Source:** Coverage F-COV-2, F-COV-3, F-COV-5, F-COV-6, F-COV-8; Test-Quality F-TQ-1, F-TQ-2, F-TQ-3, F-TQ-6
- **Changes:** Added autouse `_reset_structlog` fixture; pretty-on-TTY test; `verbose=True`/DEBUG + `verbose=False`/silenced tests; `type(...) is str` constant-type test; `EVENT_PROBE_*` closure test; `__all__` closure test; `inspect.signature` default check; all-non-empty-lines-JSON tightening.

### Edit 6 — AC-7 added (idempotence/re-entrancy)
- **Source:** Coverage F-COV-4
- **Rationale:** `structlog.configure` mutates process-global state; Phase 6/13 may double-configure; silent overwrite was an unowned failure mode.

### Edit 7 — Out of scope expanded
- **Source:** Coverage F-COV-7 + Consistency F-CON-3
- **Rationale:** Explicit non-goal for INFO-level sensitive-value scrubbing; defers to first caller (Phase 1 `NodeManifestProbe`) via ADR amendment rather than duplicating ADR-0008's chokepoint here.

### Edit 8 — Implementer notes: StrEnum doctrine expanded
- **Source:** Consistency F-CON-4 + Test-Quality F-TQ-6
- **Rationale:** Doctrine is now backed by a test (AC-5's `type(...) is str`), not prose alone.

### Edit 9 — Implementation outline + TDD plan rewritten
- **Source:** Test-Quality F-TQ-1/F-TQ-2/F-TQ-3/F-TQ-4/F-TQ-5/F-TQ-6/F-TQ-7; Coverage F-COV-1/F-COV-2/F-COV-3/F-COV-6/F-COV-8
- **Changes:** Replaced thin TDD samples with full red-phase test code covering closure, alias-collapse, marker-only, StrEnum-guard, all-lines-JSON, pretty-on-TTY, verbose branches, idempotence, and signature checks. Added `_reset_structlog` fixture.

## Verdict rationale

**HARDENED.** Two `block`-level findings (F-TQ-1 missing verbose-True/DEBUG test, F-TQ-2 missing pretty-on-TTY test) — both reflect *stated* AC-3 behaviors that the TDD plan simply forgot to test. These are not goal problems; they are gaps in coverage of an already-correct goal. Nine `harden` findings strengthened the closure, alias-collapse, StrEnum-guard, docstring, and re-entrancy invariants. One `nit` (F-TQ-7 markers-only) was applied because the implementer-note explicitly bans behavior on subclasses; testing it makes the doctrine load-bearing. One `nit` (F-CON-4 ADR amendment for StrEnum doctrine) deferred — the `type(...) is str` test provides the runtime guard the ADR would have. Goal-to-AC trace is now complete; every AC is individually verifiable and mutation-resistant under the proposed TDD plan.

## Recommended next step

`phase-story-executor` to implement.
