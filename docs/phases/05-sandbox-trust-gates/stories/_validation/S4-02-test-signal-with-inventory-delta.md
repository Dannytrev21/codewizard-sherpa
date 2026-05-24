# Validation report: S4-02 — `collect_test_signal` with pre-patch test inventory delta

**Validated:** 2026-05-24
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S4-02 ships the load-bearing collector for ADR-0015's adversarial-path
invariant (LLM patch deletes a test to make `npm test` pass). The
draft correctly identified the asymmetric-policy core — `delta < 0
→ fail`, `delta > 0 → informational annotation` — but had **nine
block-tier holes** that an executor following the draft literally
would have either (a) shipped a `TestSignal` without `provenance` or
`at` fields populated (Pydantic `ValidationError` on first real
run), (b) collided with Phase 3's pre-registered `"tests"` signal-kind
on import, (c) silently treated all-failing-but-no-files-removed
runs as adversarial via wrong `post_count` semantics, or (d) accepted
schema-drifted inventory snapshots without complaint.

The dominant failure pattern: the draft was written **before** S1-03,
S1-05, S3-01, AND S4-01's validations landed, so it referenced
surfaces that have since been tightened — most importantly:

- S1-03 mandates `at: AwareDatetime` (naive datetime rejected at
  construction); draft never asserted the collector mints a tz-aware
  `at`.
- S1-05 prescribes `@register_signal_kind` **delegates** the
  name-side to Phase 3's `signal_kind_registry` — and `"tests"` is
  **already** pre-registered there per
  [`transforms/signal_kinds.py:156`](../../../../src/codegenie/transforms/signal_kinds.py).
  Naive decoration would raise `SignalKindAlreadyRegistered`.
- ADR-0001 hashing chokepoint forbids any other module from
  importing `blake3` directly. The draft never spelled out how
  `TestSignal.provenance.inputs_blake3` is computed — risking a
  fresh `_inputs_blake3` helper in `tests.py` that bypasses S4-01's
  `_common.py` chokepoint.
- S4-01 (which validated only days ago) shipped a `_common.py`
  module with `build_provenance`, `inputs_blake3`,
  `read_last_log_line`, `utc_now` — S4-02 must **reuse** these,
  not duplicate them. Draft prose said "shared helpers (S4-01)"
  but never named the four functions.

The pattern findings (4) all fall under CLAUDE.md's "Extension by
addition" and the `_FORMAT_PARSERS` / Pydantic-inventory schema
opportunity the draft missed. Rule-of-three for the parser-format
abstraction IS cleared (jest, vitest, mocha — three formats today;
pytest in Phase 7.5 makes four). The Strategy registry is promoted
to an AC, not just a Note.

No `RESCUE`-tier findings — every gap was patchable by adding ACs,
tightening the TDD plan, formalizing helpers, and documenting the
chokepoint reuse / delegation chain. No Stage-3 research was needed:
every gap was answerable from Phase 5 arch + ADRs + the five prior
HARDENED reports (S1-02, S1-03, S1-05, S3-01, S4-01) + codebase
precedents (`codegenie.hashing`, `transforms/signal_kinds.py`) +
CLAUDE.md load-bearing commitments.

## Findings (severity, lens, fix)

### Block-tier (would-silently-pass / would-crash-on-first-real-input)

1. **(coverage — block) `SignalProvenance.{signal_kind,
   collector_module, collector_version, inputs_blake3}` values
   completely unpinned.** Draft constructs `TestSignal` in tests
   but only asserts `sig.passed` and a handful of `details` keys.
   The `provenance` field is **required** on `_SignalBase` (S1-03)
   — without populating it the collector cannot even construct a
   `TestSignal` (Pydantic `ValidationError`). And even when
   populated, draft never asserts the values are correct. A
   copy-paste from S4-01's `build.py` that mints
   `signal_kind=SignalKind("build")` in `tests.py` passes every
   draft test. **Fix:** AC-PROV-KIND-1..-2, AC-PROV-MODULE-1..-2,
   AC-PROV-VERSION-1 + paired TDD tests; AC-PROV-FACTORY-1 mandates
   delegation to S4-01's `_common.build_provenance`.

2. **(coverage — block) `at: AwareDatetime` enforcement missing.**
   S1-03 AC-6 / AC-6a rejects naive `datetime` at construction. A
   naive `datetime.utcnow()` would `ValidationError` on first real
   run. Draft test plan never builds a real signal end-to-end with
   a timezone check. **Fix:** AC-AT-TZ-1 + paired test case;
   AC-AT-TZ-2 AST scan asserts `tests.py` never imports
   `datetime.utcnow`.

3. **(consistency — block) ADR-0001 hashing chokepoint reuse from
   S4-01 unspecified.** Draft says "Existing code:
   `src/codegenie/sandbox/signals/_common.py` (S4-01) — shared
   helpers" but does NOT name `build_provenance`,
   `inputs_blake3`, `utc_now`, NOR pin delegation. A naive impl
   minting its own `_inputs_blake3` helper directly importing
   `blake3` would pass every draft test but violate ADR-0001's
   single-chokepoint discipline. **Fix:** AC-PROV-FACTORY-1
   mandates `tests.py` calls `_common.build_provenance` (which
   delegates to `codegenie.hashing.content_hash_bytes`);
   AC-HASH-CHOKEPOINT-1..-2 AST scan asserts no direct `blake3`
   import under `signals/**/*.py`.

4. **(consistency — block) Phase 3 pre-registered `"tests"`
   collision unaddressed.** Phase 3's
   [`transforms/signal_kinds.py:156`](../../../../src/codegenie/transforms/signal_kinds.py)
   executes `TESTS = register_signal_kind("tests")` at module
   import time. Phase 5's `@register_signal_kind("tests")` on
   `collect_test_signal` would raise
   `SignalKindAlreadyRegistered` unless S1-05's decorator handles
   idempotent re-registration — which it does, but the draft
   never references this. **Fix:** AC-REG-IDEMPOTENT-1 asserts
   the decorator does not raise; explicit Notes paragraph #3
   documents the delegation. Mirrors S4-01 HARDENED #8.

5. **(coverage — block) Import-time registration side-effect
   unpinned.** Draft never asserts `signals/__init__.py` imports
   `tests` at package-import. Without the re-export,
   `signal_collector_registry` lacks `"tests"` when `StrictAndGate`
   (S4-05) tries to resolve. **Fix:** AC-INIT-1 (AST scan
   asserts `from . import …, tests` is present) + AC-INIT-2
   (`signal_collector_registry.get(SignalKind("tests")) is
   collect_test_signal`). Mirrors S4-01 HARDENED #9.

6. **(coverage — block) `post_count` semantics ambiguous —
   `total`-vs-`passed`.** Draft says "parse jest/vitest output"
   without specifying which integer is `post_count`. If
   `post_count = passed` (not `total`), then a patch where all 42
   tests still exist but newly fail gives `delta = passed - pre =
   1 - 42 = -41` — falsely triggering the adversarial-path policy
   ADR-0015 polices ONLY for files-removed scenarios. **Fix:**
   AC-POSTCOUNT-1 pins `post_count = total` (jest/vitest/mocha
   total: passed + failed + skipped + todo); new test
   `test_failures_do_not_falsify_delta` proves `delta == 0` when
   all tests still present but exit nonzero.

7. **(coverage — block) `_PostCountSource` discriminated by
   parser format pinned.** The three formats need an explicit
   `(regex, total_group)` discipline. Draft defers entirely to
   "regex" — implementer might pick `passing` (mocha) or `passed`
   (jest) instead of `total`. **Fix:** `_FORMAT_PARSERS:
   Final[tuple[_TestFormatParser, ...]]` registry +
   AC-PARSER-1..-3 + AC-PARSER-REGISTRY-1..-3 pin the three
   formats explicitly, including precedence policy (first match
   wins).

8. **(coverage — block) Inventory JSON schema unpinned via
   Pydantic.** Draft prose sketches `{"test_count": int,
   "test_names": list[str], "captured_at": ISO8601}` but
   implementer is free to accept `test_count: -1`, a missing
   field, a non-int. Schema drift when Phase 3 produces the
   snapshot becomes a silent contract break. **Fix:**
   `_PrePatchInventory(BaseModel, frozen=True, strict=True,
   extra="forbid")` + AC-INV-SCHEMA-1..-3 mandate Pydantic
   validation; AC-INV-CORRUPT-1 pins corrupt-file behaviour
   (annotate, do not raise — mirrors missing-file path);
   AC-INV-PERM-1 / AC-INV-NEVER-RAISES-1 cover the failure-mode
   matrix.

9. **(coverage — block) Banned-substring screening on
   `details` keys.** Draft prose says `coverage_evidence_strength`
   "is NOT used here" — but ADR-0014 polices **four** banned
   substrings (`confidence`, `llm`, `self_reported`,
   `model_says`). A defence-in-depth catalog scan is missing.
   **Fix:** AC-DETAILS-NOBAN-1 mandates none of the four appear
   in any of the three `_TEST_DETAIL_KEYS_*` catalogs; mirrors
   S4-01 catalog-screening pattern.

### Harden-tier (would-pass-but-leave-trap-for-next-sibling)

10. **(coverage — harden) `_TEST_DETAIL_KEYS_*: Final[frozenset[str]]`
    three-catalog split.** S4-01 set the pattern of a module-level
    `Final` catalog of `details` keys. S4-02 has THREE distinct
    key-sets: failure path, success path, missing-inventory path.
    Pinning all three as `Final` catalogs documents the surface
    and lets parametrize tests assert exact key-set equality.
    **Fix:** AC-DETAILS-KEYS-1..-3 + AC-DETAILS-KEYS-IMPORT-1.

11. **(coverage — harden) Truth-table not exhaustive.** Draft has
    seven cases; the truth table is `exit_code ∈ {0, ≠0}` × `delta
    ∈ {<0, ==0, >0}` × `inventory ∈ {present, missing}` = **12
    corners**. Draft cases skip e.g. (`exit_code=0, delta>0`,
    inventory=missing). The `and→or` mutation slips past seven
    cases. **Fix:** AC-PASSED-TRUTH-1 promotes the truth table to
    a parametrize layer over all 12 corners; AC-PROP-PASSED-1
    adds a Hypothesis property over `(pre, post, exit_code)`.

12. **(coverage — harden) `failing_tests` / `first_failure`
    truncation pinned.** Draft has no length cap.
    `AttemptSummary.prior_failure_summary` (S1-04) is ≤ 4 KB. An
    adversarial 64 KB test name would defeat the AttemptSummary
    contract. **Fix:** AC-FAILING-TRUNC-1 (2048 UTF-8 bytes; ends
    with `…` on truncation; last name whole) + AC-FIRSTFAIL-TRUNC-1
    (256 UTF-8 bytes; byte-safe — matches S4-01 `last_log_line`).

13. **(coverage — harden) `first_failure` parsing pinned to
    test-name not log-line.** Draft test asserted `"auth" in
    sig.details["first_failure"]` — vague; an impl that returns
    the entire `FAIL src/auth.test.ts > jwt-validates` line
    passes. **Fix:** AC-FIRSTFAIL-SHAPE-1 pins the
    fully-qualified test name post-`>`; regex `^[^\s].+[^\s]$` +
    per-format goldens.

14. **(coverage — harden) `failing_tests` ordering pinned
    deterministic.** Naive impl might emit `set`-ordered output.
    Spec hash chain (S3-01) + AttemptSummary deterministic-replay
    (Phase 9) require byte-stable serialization. **Fix:**
    AC-FAILING-ORDER-1: alphabetically sorted, joined with `, `
    (comma + single space).

15. **(test-quality — block) `SandboxSpec` fixture-hash
    placeholder bug.** Draft uses `sandbox_spec_hash="d"` (1 char)
    — S3-01 AC-HASH-FORMAT pins 32-char hex; S4-01 HARDENED #13 /
    AC-FIXTURE-HASH-1 pins `"0" * 32` and a `conftest.py`
    chokepoint. **Fix:** S4-02 reuses S4-01's `_make_run` fixture
    chokepoint (no parallel fixture); AC-FIXTURE-LOG-1 governs
    log fixtures.

16. **(test-quality — block) Determinism property over **two
    distinct `SandboxRun` instances**.** Draft Hypothesis property
    iterates over `(pre, post)` but doesn't exercise content-
    determinism on `provenance.inputs_blake3`. S4-01 HARDENED #5
    set the pattern. **Fix:** AC-DETERMINISM-1 uses two distinct
    `_make_run(...)` calls with identical kwargs to assert
    byte-equal `inputs_blake3`.

17. **(test-quality — harden) Parser-format cross-coverage
    parametrized.** Draft has jest-only test bodies. Three
    formats today, Phase 7.5 pytest makes four — single
    parametrize layer is the right shape. **Fix:**
    AC-PARSER-PARITY-1 introduces `@pytest.mark.parametrize(
    "format_name,sample_log,expected_total,expected_failing,
    expected_first", PARSER_FIXTURES)`; adding pytest is one row.

18. **(test-quality — harden) Negative truth-table corners — exit
    nonzero + delta zero, exit zero + delta negative.** Draft
    cases skip these. AC-PASSED-TRUTH-1 promotes the truth table
    to exhaustive (12 corners × 3 parser formats = 36 cases —
    kept fast since collector is pure).

19. **(consistency — harden) `pre_patch_inventory_path` source
    out-of-scope documented.** Draft says "supplied via
    `GateContext`" but `GateContext` (per phase-arch §Data
    model) does NOT carry the path field. **Fix:** Notes
    paragraph #5 makes the runner-side wiring out of scope; S4-05
    / S5-02 owns the derivation from `ctx.workflow_id` /
    `ctx.run_id`. Story takes the path as an opaque kwarg.

20. **(consistency — harden) `_test_parser.py` purity test
    landed.** AST scan asserts no I/O outside `logs_dir`; no
    `subprocess` / `os.system` / network calls. **Fix:** AC-FENCE-2
    extends the S4-01 `tests/sandbox/test_signals_purity.py`
    file (no parallel file).

21. **(patterns — harden) `_TestFormatParser` Protocol +
    `_FORMAT_PARSERS` registry catalog promoted from Notes to
    ACs.** Three formats today; Phase 7.5 pytest makes four —
    rule-of-three CLEARED. Strategy pattern as a Protocol +
    tuple-catalog: each parser is a frozen dataclass `(name,
    pattern, total_group, failing_pattern)`. Phase 7.5 adds a
    row; never edits `_test_parser.py`. **Fix:**
    AC-PARSER-REGISTRY-1..-3.

22. **(patterns — harden) Sum-type for `_ParsedTests.format`.**
    `format: Literal["jest", "vitest", "mocha", "unknown"]` —
    typed, pattern-matchable. "unknown" is the only path where
    `post_count == 0`. **Fix:** AC-PARSED-FORMAT-1 +
    AC-PARSER-UNKNOWN-1.

23. **(patterns — harden) `_PrePatchInventory` is a frozen
    Pydantic model with strict primitives + immutable tuple.**
    Mirrors S1-03 discipline. `test_names: tuple[str, ...]` (NOT
    `list[str]`) for immutability. **Fix:** AC-INV-SCHEMA-1.

24. **(patterns — harden) Three `Final` catalogs of detail keys
    (S4-01 pattern extended).** Three pinned key-sets document the
    boundary the implementation must honour — and let parametrize
    tests scan all three for banned substrings in one pass.
    **Fix:** AC-DETAILS-KEYS-1..-3.

25. **(patterns — harden) Forward-seam Note: Phase 7.5 Python
    parser.** Phase 7.5 adds `pytest` parsing as one new
    `_TestFormatParser` row; `tests.py` does not change. **Fix:**
    Notes paragraph #6 documents the extension contract.

26. **(consistency — harden) Module hygiene mirrored from S4-01.**
    `from __future__ import annotations`, module docstring citing
    ADR-0003/ADR-0014/ADR-0015/ADR-0001 + source story S4-02,
    `__all__` discipline, coverage floor (line ≥ 95% AND branch
    ≥ 90%). **Fix:** AC-DOC-1, AC-PURE-1..-4, AC-PG-2.

27. **(consistency — harden) Misleading Notes guidance corrected.**
    "Convert durations to int ms / lists to comma-joined strings"
    — S1-03 + S4-01 set this as a *details-shape* discipline;
    S4-02 has no durations in `details`, only `failing_tests` as
    comma-joined string and `parser_format` as Literal string.
    **Fix:** Notes paragraph #1 scoped to the two cases that
    apply.

28. **(test-quality — harden) Fixture log faithfulness.** Draft
    `JEST_FAIL` regex couples test-name to FAIL banner on the
    SAME line as the Tests summary. Real jest puts the FAIL
    banner ABOVE the summary. **Fix:** Rewritten golden logs;
    AC-FIXTURE-LOG-1 mandates fixtures replicate real runner
    output ORDER.

### Nit-tier (cosmetic / readability)

29. **(nit) Module docstrings cite ADR-0003 / ADR-0014 / ADR-0015 +
    ADR-0001 + S4-02.** Mirrors S4-01 hardened pattern. Captured in
    AC-DOC-1.

30. **(nit) `from __future__ import annotations` as line 1
    post-docstring.** Codebase convention. Captured in AC-PURE-1.

31. **(nit) `__all__` discipline (alphabetized, set-equal).**
    Captured in AC-PURE-2..-4.

## Edits applied to the story

The Validation notes block at the top of the story is the authoritative
edit log. Headline summary:

- **Status:** `Ready` → `Ready (HARDENED 2026-05-24)`.
- **Depends on:** added explicit `+ S4-01 (_common.py helpers)` row.
- **ADRs honored:** added `+ ADR-0001 hashing chokepoint`.
- **Context:** rewritten to mention three-formats parser, S4-01
  chokepoint reuse, runner-side path-derivation out of scope.
- **References:** added S4-01 `_common.py` dependency, Phase 3
  `transforms/signal_kinds.py` pre-registration, five sibling
  validation reports.
- **Goal:** rewritten to specify `total_count` (not `passed_count`),
  Pydantic-validated snapshot, `_common.build_provenance` chokepoint
  reuse.
- **Acceptance criteria:** restructured into 14 sections (A–N) with
  ~70 ACs (up from ~10 in the draft). Every block-tier and
  harden-tier finding has at least one paired AC; many have
  paired AST scans plus runtime checks.
- **Implementation outline:** expanded from 4 steps to 11 steps;
  every file action paired with a "why".
- **TDD plan:** rewritten as a single parametrize layer over the 12
  truth-table corners + property test + parser-format parity +
  detail-catalog assertions + provenance pinning + integration
  fixture-backed tests. Mirrors S4-01's parametrize pattern.
- **Files to touch:** expanded from 8 to 17 entries (three modules,
  three test files extended, one test file appended, six fixture
  log files, one Pydantic schema test, one integration test).
- **Out of scope:** added six items (failed_unrecoverable 3×, E2E
  consolidated to S7-01, trace/policy/cve_delta, StrictAndGate,
  `pre_patch_inventory_path` derivation, Phase 3 snapshot
  production, Phase 7.5 pytest row, audit-event emission).
- **Notes for the implementer:** rewritten to 12 paragraphs
  (S4-01-quality discipline); explicit decorator-delegation note,
  forward-seam note for Phase 7.5, Strategy-helper non-extraction
  rationale, never-raises contract.

## Stage-3 research

Not needed. Every gap was answerable from the Phase 5 architecture
docs, ADR-0003/0014/0015, ADR-0001 (hashing chokepoint), the five
prior HARDENED reports (S1-02, S1-03, S1-05, S3-01, S4-01),
codebase precedents
([`codegenie.hashing`](../../../../src/codegenie/hashing.py),
[`transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py)),
and CLAUDE.md load-bearing commitments (Extension by addition,
Newtype identifiers, Functional core / imperative shell, Rule 9,
Rule 11).

## Verdict

**HARDENED.** Story restructured in place; ready for
`phase-story-executor` invocation. Goal, scope, dependencies (S1-03,
S1-05, S3-07, S4-01), out-of-scope discipline, and ADR mapping
(-0003, -0014, -0015, +ADR-0001 chokepoint) unchanged. No
`RESCUE`-tier findings; no Stage-3 research.
