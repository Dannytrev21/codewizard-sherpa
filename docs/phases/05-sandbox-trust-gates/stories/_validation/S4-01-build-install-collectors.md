# Validation report: S4-01 — `collect_build_signal` + `collect_install_signal`

**Validated:** 2026-05-24
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S4-01 ships the two simplest of the six Step-4 signal collectors and is *the
template* the remaining four (S4-02 / S4-03) and Phase 7 (`baseimage`,
`shell_presence`) copy verbatim. The draft correctly identified the trivial
shape — `passed = exit_code == 0 ∧ ¬timed_out ∧ ¬killed_by_oom`, pure helpers
in `_common.py`, `@register_signal_kind` decoration — but had **nine
block-tier holes** that an executor following the draft literally would have
either (a) silently passed CI with the wrong provenance, (b) invented a
parallel `blake3` import in violation of the [ADR-0001 hashing
chokepoint](../../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md),
or (c) shipped collectors whose registration never fires at import time.

The dominant failure pattern: the draft was written before S1-03 and S1-05's
validations landed, so it referenced surfaces that were tightened during
sibling hardening — most importantly:

- S1-03 mandates `at: AwareDatetime` (naive datetime rejected at
  construction). The draft has no AC asserting collectors produce a
  tz-aware `at`; a naive `datetime.utcnow()` would `ValidationError` at the
  first run — but the test plan never builds a real signal end-to-end with
  the timezone check.
- S1-05 prescribes `@register_signal_kind` **delegates** the name-side to
  Phase-3's `signal_kind_registry` (already pre-registered for `"build"` /
  `"install"` per `transforms/signal_kinds.py`). The draft does not document
  the delegation, risking a double-registration `SignalKindAlreadyRegistered`.
- ADR-0001 hashing chokepoint forbids any other module from importing
  `blake3` directly. The draft's `_inputs_blake3` helper specification
  implies a direct `blake3` import; the canonical path is
  `codegenie.hashing.content_hash_bytes(canonical_json)`.
- The pure-function determinism test re-calls the collector on the *same
  Python instance* twice. This passes even for a wrong impl that derives
  the hash from `id(run)`; the property the AC actually wants is "two
  equivalently-constructed but distinct instances produce the same hash."

The pattern findings (4) all fall under CLAUDE.md's "Extension by addition"
and S1-03's note-only `_BUILD_DETAIL_KEYS: Final[frozenset[str]]` pattern.
The third-collector threshold for the no-extra-input collector shape is **not
yet met** here (S4-03 collectors all take extra kwargs, so the shape doesn't
recur until Phase 7's `baseimage`/`shell_presence`). The Strategy helper is
documented as a Notes-for-implementer signpost, not promoted to AC.

No `RESCUE`-tier findings — every gap was patchable by adding ACs, tightening
the TDD plan, formalizing helpers, and documenting collisions / delegations.
No Stage-3 research was needed: every gap was answerable from Phase 5 arch +
ADRs + the four prior HARDENED reports (S1-02, S1-03, S1-05, S3-01) +
codebase precedents (`codegenie.hashing`, `transforms/signal_kinds.py`,
`probes/language_detection.py` Final-catalog pattern) + CLAUDE.md commitments.

## Findings (severity, lens, fix)

### Block-tier (would-silently-pass / would-crash-on-first-real-input)

1. **(coverage — block) `SignalProvenance.signal_kind` value is unpinned.**
   Draft says the collector returns a `BuildSignal` with `provenance:
   SignalProvenance` but never asserts `provenance.signal_kind ==
   SignalKind("build")`. A wrong impl that mints `SignalKind("install")` in
   `build.py` (copy-paste bug between the two files) passes every existing
   draft test. **Fix:** AC-PROV-KIND-1..-2 pin both collectors; assertions
   added in TDD plan.

2. **(coverage — block) `SignalProvenance.collector_module` value is unpinned.**
   `collector_module` carries `"codegenie.sandbox.signals.build"` —
   downstream provenance verification relies on this being the actual
   module that produced the signal. A wrong impl that hardcodes
   `"sandbox.signals.collector"` or `__name__.rsplit(".", 1)[0]` fails
   silently. **Fix:** AC-PROV-MODULE-1..-2.

3. **(coverage — block) `SignalProvenance.collector_version == "1"` is
   unpinned.** Notes say "don't change it casually" but no test verifies
   the literal "1". **Fix:** AC-PROV-VERSION-1.

4. **(coverage — block) `at` is timezone-aware (S1-03 AwareDatetime).**
   S1-03 AC-6 / AC-6a mandates naive datetime is rejected at
   construction. A naive `datetime.utcnow()` would `ValidationError` on
   the first real run, but the test plan never asserts `sig.at.tzinfo is
   not None` after construction. **Fix:** AC-AT-TZ-1 + paired test case.

5. **(test-quality — block) Pure-function determinism test uses the same
   `SandboxRun` instance twice.** `test_build_signal_pure_function_same_inputs_same_blake3`
   re-calls `collect_build_signal(run)` with the same instance — passes
   even for an impl that returns `f"blake3:{id(run):x}"`. The property
   the AC wants is *content* determinism: two equivalently-constructed
   but distinct instances produce byte-equal `inputs_blake3`. **Fix:**
   AC-DETERMINISM-1 + rewritten TDD test using two distinct
   `_run(...)` calls with identical kwargs.

6. **(consistency — block) Hash chokepoint violated.** ADR-0001 (Phase 0)
   pins `codegenie.hashing` as the **single source of truth** for hashing —
   "no other file under `src/codegenie/` imports `blake3` or
   `hashlib.sha256`." Draft's `_inputs_blake3` helper implies a direct
   `blake3` import; the canonical path is
   `codegenie.hashing.content_hash_bytes(canonical_json_bytes)`. **Fix:**
   AC-HASH-CHOKEPOINT-1..-3 mandate delegation + AST scan asserting no
   `blake3` import under `sandbox/signals/`.

7. **(consistency — block) Canonical-JSON serialization is unspecified.**
   `_inputs_blake3` over `(run.run_id, run.spec.sandbox_spec_hash,
   run.exit_code)` has no specified encoding. Naive `json.dumps(...)` is
   Python-minor-unstable (S3-01 hardening flagged this). **Fix:**
   AC-HASH-INPUTS-1 pins canonical JSON: `json.dumps({"run_id": ...,
   "spec_hash": ..., "exit_code": ...}, sort_keys=True,
   separators=(",", ":")).encode("utf-8")`.

8. **(consistency — block) Decorator-delegation to Phase 3 unpinned.**
   S1-05 HARDENED #1 establishes Phase 5's `@register_signal_kind`
   **delegates** the name-side to Phase 3's `signal_kind_registry`
   (already pre-registered with `BUILD = register_signal_kind("build")`
   per `src/codegenie/transforms/signal_kinds.py`). A naive impl that
   double-registers `"build"` would raise Phase 3's
   `SignalKindAlreadyRegistered`. S1-05 AC-COL-4 makes the delegation
   idempotent for pre-existing names, but S4-01 doesn't reference this.
   **Fix:** AC-REG-IDEMPOTENT-1 asserts both collectors register
   without raising even though `"build"` and `"install"` are already in
   Phase 3's registry; explicit Notes paragraph names the delegation.

9. **(coverage — block) Import-time registration side-effect unpinned.**
   Notes #3 says "package `__init__.py` must import them, or first-use of
   the registry will be empty" — but no AC asserts this. An executor
   skipping the re-export ships collectors that never appear in
   `signal_collector_registry`, and the `StrictAndGate` (S4-05)
   silently fails to find them. **Fix:** AC-INIT-1..-2 pin the
   `signals/__init__.py` re-export AND the registry-resolution test
   (`signal_collector_registry.get(SignalKind("build")) is
   collect_build_signal`).

### Harden-tier (would-pass-but-leave-trap-for-next-sibling)

10. **(coverage — harden) `details` value-set is unpinned for the
    failure case.** Draft AC-4 says "structured keys (`exit_code: int`,
    `timed_out: bool`, `killed_by_oom: bool`, `last_log_line: str` truncated
    to 256 chars)" but no AC asserts `set(sig.details.keys()) ==
    {"exit_code", "timed_out", "killed_by_oom", "last_log_line"}` on the
    failure path. **Fix:** AC-DETAILS-KEYS-1..-2 + a module-level
    `_BUILD_DETAIL_KEYS: Final[frozenset[str]]` catalog (S1-03 Notes
    pattern, S2's `_WARNING_IDS` precedent).

11. **(coverage — harden) `last_log_line` byte-vs-char truncation is
    ambiguous.** "Truncated to 256 chars" — code points, bytes, after
    decode-error replacement? An adversarial 256-emoji line is 1024
    UTF-8 bytes. **Fix:** AC-LASTLOG-TRUNC-1 pins **256 UTF-8 bytes** post
    `.decode("utf-8", errors="replace")` (matches `codegenie.hashing` UTF-8
    discipline); AC-LASTLOG-EMPTY-1 pins empty-string return on missing /
    unreadable / zero-length file.

12. **(coverage — harden) `passed=True` `details` contract is
    unpinned.** Should the success path emit a non-empty `details`? Draft
    is silent. **Fix:** AC-DETAILS-PASS-1 pins `details = {"exit_code": 0}`
    on the success path (a minimum non-empty signal of "we observed
    success" — empty `{}` would be ambiguous with "no information").

13. **(test-quality — harden) Mutation-resistance on `passed` formula
    missing.** Draft has four passed/failed cases but doesn't cover the
    AND-formula exhaustively — e.g., `(exit_code=0, timed_out=True,
    oom=True)` should still be `passed=False`, and the mutation that
    swapped `and` for `or` slips past four out of seven cases. **Fix:**
    Hypothesis property test AC-PROP-PASSED-1: for all `(exit_code,
    timed_out, oom)` in `int × bool × bool`, `passed ==
    (exit_code == 0 and not timed_out and not oom)`.

14. **(test-quality — harden) Cross-collector parity not parametrized.**
    Draft says "mirror this file" for `test_signals_install.py` — duplicated
    tests rot at different rates. **Fix:** AC-PARITY-1 introduces a
    parametrize layer: `@pytest.mark.parametrize("collect,kind,model_cls",
    [(collect_build_signal, "build", BuildSignal),
    (collect_install_signal, "install", InstallSignal)])` exercises the
    same seven invariants over both. Sets the template for S4-02..S4-06
    and Phase 7 (`baseimage`, `shell_presence`).

15. **(test-quality — harden) `SandboxSpec` test-fixture drift risk.**
    Draft uses `SandboxSpec.model_construct(...)` to bypass validation
    AND sets `sandbox_spec_hash="deadbeef"` (8 chars). S3-01 AC-HASH-FORMAT
    pins 32-char hex. A fixture that diverges from the contract risks
    masking a bug where the collector inspects `len(spec.sandbox_spec_hash)`
    downstream. **Fix:** AC-FIXTURE-HASH-1 mandates fixtures use a
    32-char-hex placeholder (`"0" * 32`); a `conftest.py` helper
    `_make_run(...)` is the single fixture chokepoint.

16. **(consistency — harden) Notes #1 conversion guidance is
    misleading.** "Convert any duration to int milliseconds; convert lists
    to comma-joined strings if needed" — but build / install `details`
    carry no durations and no lists. Implementer might invent
    `details["duration_ms"]` to follow the note. **Fix:** Notes paragraph
    rewritten to scope guidance to S4-02..S4-06.

17. **(patterns — harden) Strategy helper deferral is correct but should
    be a documented signpost.** Build + install share the no-extra-input
    shape. S4-03 (trace, policy, cve_delta) all take extra kwargs — does
    NOT extend the same Strategy. Phase 7's `baseimage`/`shell_presence`
    will (per arch §Goal 9). Rule-of-three for the Strategy helper hits at
    Phase 7, not here (only two instances now). **Fix:** Notes
    paragraph #7 signposts the extraction trigger — third no-extra-input
    collector — so the Phase-7 implementer knows when to widen `_common.py`
    to a `_collect_simple(run, kind, model_cls)` helper.

18. **(patterns — harden) `SignalKind` newtype usage in the registry
    boundary.** S1-03 promotes `SignalKind = NewType("SignalKind", str)` to
    `types/identifiers.py`. Draft uses raw strings `"build"`/`"install"` in
    the decorator. S1-05 AC-CR-7 mandates the registry's internal store
    keys on `SignalKind`. **Fix:** AC-NEWTYPE-1 pins that the
    `signal_collector_registry` resolves the registered functions via
    `SignalKind("build")` / `SignalKind("install")` lookup (not raw `str`),
    matching S1-05 contract.

19. **(consistency — harden) `datetime.now(timezone.utc)` vs
    `datetime.now(UTC)` convention.** Story prose says "`datetime.now(UTC)`"
    — codebase convention is `datetime.now(timezone.utc)` (used in S1-03's
    ACs and elsewhere). Rule 11: match codebase convention. **Fix:** Notes
    + AC test imports `from datetime import datetime, timezone`.

20. **(consistency — harden) Test file naming for registry resolution.**
    Draft prescribes `tests/sandbox/test_signals_registry.py`. S1-05 AC-PG-2
    already pins `tests/sandbox/test_signal_collector_registry.py` as the
    registry test file. **Fix:** AC-REG-TEST-1 mandates this story
    **appends** to the existing S1-05 test file (no new parallel file);
    avoids split test ownership for the same registry.

### Nit-tier (cosmetic / readability)

21. **(nit) Module docstrings should cite ADR-0003, ADR-0014, ADR-0015 + S4-01.**
    Mirrors S1-02 / S1-03 / S1-05 hardened pattern. Captured in AC-DOC-1.

22. **(nit) `from __future__ import annotations` as line 1 post-docstring.**
    Already established codebase convention. Captured in AC-PURE-1.

23. **(nit) `__all__` discipline — alphabetized, set-equal to the
    documented public surface.** Mirror of S1-02 / S1-03 / S1-05. Captured
    in AC-PURE-2.

## Edits applied to the story

The Validation notes block at the top of the story is the authoritative
list. The patches translate every Block/Harden finding above into a paired
AC + TDD-plan code change. The TDD plan is now parametrized across both
collectors (finding #14), uses two distinct `_run(...)` instances for
determinism (finding #5), invokes `codegenie.hashing.content_hash_bytes`
for hashing (finding #6), pins canonical-JSON shape (finding #7), and adds
a Hypothesis property test for the AND-formula (finding #13). Notes for
the implementer are tightened to remove the misleading conversion guidance
(finding #16) and to signpost the Strategy-helper extraction trigger at
Phase 7's third no-extra-input collector (finding #17).

## Verdict

**HARDENED.** Edits applied in place. Story ready for `phase-story-executor`.
