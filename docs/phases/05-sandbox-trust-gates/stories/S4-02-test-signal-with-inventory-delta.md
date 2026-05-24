# Story S4-02 — `collect_test_signal` with pre-patch test inventory delta

**Step:** Step 4 — Six signal collectors + StrictAndGate adapter
**Status:** Ready (HARDENED 2026-05-24)
**Effort:** M
**Depends on:** S3-07 (real `SandboxRun` against `hello-node`), S1-05 (`@register_signal_kind` registry + delegation to Phase-3 `signal_kind_registry`), S1-03 (`ObjectiveSignals` + `TestSignal` sub-model + `SignalKind` newtype + `AwareDatetime` discipline), **S4-01 (`_common.py` helpers `build_provenance`, `inputs_blake3`, `read_last_log_line`, `utc_now`)** — this story consumes the chokepoint module S4-01 ships.
**ADRs honored:** ADR-0015, ADR-0014, ADR-0003 + production [ADR-0001 hashing chokepoint](../../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md)

## Validation notes (2026-05-24 — phase-story-validator)

Hardened via `phase-story-validator` (verdict: HARDENED). Source-of-truth
contradictions resolved against [`../phase-arch-design.md §Signal
collectors`](../phase-arch-design.md), [`../phase-arch-design.md §Data
model`](../phase-arch-design.md), [`../phase-arch-design.md §Edge cases 6, 7,
17`](../phase-arch-design.md), [ADR-0015](../ADRs/0015-test-inventory-delta-asymmetric-policy.md),
[ADR-0014](../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md),
[ADR-0003](../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md),
the five sibling HARDENED reports (S1-02, S1-03, S1-05, S3-01, S4-01), the
**already-shipped** Phase 0 hashing chokepoint at
[`src/codegenie/hashing.py`](../../../../src/codegenie/hashing.py), and the
Phase 3 [`src/codegenie/transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py)
name-registry (which already pre-registers `"tests"` at module-import). Full
report: [`_validation/S4-02-test-signal-with-inventory-delta.md`](_validation/S4-02-test-signal-with-inventory-delta.md).

Headline edits (every weakness the four critics flagged would have let a
structurally-wrong implementation slip past the executor's validator):

1. **(coverage — block) `SignalProvenance.{signal_kind, collector_module,
   collector_version}` values pinned positively.** Draft constructed a
   `TestSignal` but never asserted the four `provenance` fields. A
   `tests.py` mint that sets `signal_kind="build"` (copy-paste from
   S4-01's `build.py`) passed every draft test. New AC-PROV-KIND-1..-2,
   AC-PROV-MODULE-1..-2, AC-PROV-VERSION-1 + paired tests. Mirrors S4-01
   HARDENED #1..#3.
2. **(coverage — block) `at: AwareDatetime` enforced.** S1-03 AC-6
   rejects naive `datetime` at construction; draft never asserted the
   collector mints a tz-aware `at`. A naive `datetime.utcnow()` would
   `ValidationError` on first run; the test plan didn't catch this.
   New AC-AT-TZ-1 + test case. Mirrors S4-01 HARDENED #4.
3. **(consistency — block) ADR-0001 hashing chokepoint reuse from
   S4-01.** Draft references S4-01's `_common.py` for "shared helpers"
   but never spells out which functions, nor pins delegation. ADR-0001
   forbids any module under `src/codegenie/` from importing `blake3`
   directly — `collect_test_signal` MUST consume
   `_common.build_provenance(...)` (which itself delegates to
   `codegenie.hashing.content_hash_bytes`) rather than minting its own
   `SignalProvenance`. New AC-PROV-FACTORY-1, AC-HASH-CHOKEPOINT-1..-2.
4. **(consistency — block) `@register_signal_kind("tests")` collision
   with Phase 3.** Phase 3's
   [`transforms/signal_kinds.py:156`](../../../../src/codegenie/transforms/signal_kinds.py)
   already executes `TESTS = register_signal_kind("tests")` at import.
   Naive Phase 5 decoration would raise `SignalKindAlreadyRegistered`
   per S1-05 HARDENED #1. The decorator delegates iff the kind is
   absent from the Phase 3 registry. AC-REG-IDEMPOTENT-1 asserts the
   decorator does not raise; explicit Notes paragraph names the
   delegation chain (Rule 7). Mirrors S4-01 HARDENED #8.
5. **(coverage — block) Import-time registration side-effect pinned.**
   Draft never enforces `signals/__init__.py` imports `tests` at
   package-import time. An executor skipping the re-export ships
   `collect_test_signal` that never appears in
   `signal_collector_registry`; `StrictAndGate` (S4-05) silently fails
   to resolve it. New AC-INIT-1..-2. Mirrors S4-01 HARDENED #9.
6. **(coverage — block) `post_count` semantics ambiguous —
   `total`-vs-`passed`.** Draft says "parse jest/vitest output" but
   does not pin which integer in `Tests: 41 failed, 1 passed, 42
   total` is `post_count`. If `post_count = passed`, a patch where all
   42 tests still exist but newly fail gives `delta = -41` (false
   adversarial). The adversarial path ADR-0015 polices is **test
   files removed**, not **tests failing**. Resolution: `post_count =
   total` (jest/vitest/mocha all carry a `total` figure). AC-POSTCOUNT-1
   pins; new test case `test_failures_do_not_falsify_delta` proves
   `delta == 0` when all tests still present but exit nonzero.
7. **(coverage — block) `_PostCountSource` discriminated by parser
   format pinned.** Three formats need explicit `(regex, total_group)`
   discipline. Draft defers entirely to "regex" — implementer might
   pick `passing` (mocha) or `passed` (jest) instead of `total`. New
   `_FORMAT_PARSERS: Final[tuple[_TestFormatParser, ...]]` registry +
   AC-PARSER-1..-3 pin the three formats explicitly.
8. **(coverage — block) Inventory JSON schema pinned via Pydantic.**
   Draft sketches the shape `{"test_count": int, "test_names": list[str],
   "captured_at": ISO8601}` only in prose — implementer is free to
   accept `test_count: -1`, a missing field, a non-int. Schema drift
   when Phase 3 produces the snapshot becomes a silent contract break.
   New `_PrePatchInventory(BaseModel, frozen=True, extra="forbid")` +
   AC-INV-SCHEMA-1..-3 mandate Pydantic validation; AC-INV-CORRUPT-1
   pins corrupt-file behaviour (annotate, do not raise — mirrors the
   missing-file path).
9. **(coverage — block) Banned-substring screening on `details` keys.**
   Story drafted `coverage_evidence_strength is NOT used here` as
   prose, but ADR-0014 polices **four** substrings (`confidence`,
   `llm`, `self_reported`, `model_says`). AC-DETAILS-NOBAN-1 mandates
   the `_TEST_DETAIL_KEYS` catalog contains none of the four; defence
   in depth on `tests/schema/test_objective_signals_static.py`. Mirrors
   S4-01 HARDENED on catalog screening.
10. **(coverage — harden) `_TEST_DETAIL_KEYS: Final[frozenset[str]]`
    catalog landed.** S4-01 set the pattern — a module-level `Final`
    catalog of keys both documents the surface and lets `_common`-style
    fence tests assert no surprise key appeared. The failure path's
    catalog is `{"delta_test_count", "first_failure", "failing_tests",
    "parser_format", "exit_code", "timed_out", "killed_by_oom",
    "pre_patch_inventory_missing"}` (eight keys); the success path is
    `{"delta_test_count", "parser_format"}` (two — `delta` always
    present per ADR-0015; `parser_format` documents which regex hit).
    AC-DETAILS-KEYS-1..-3. Catalog-import discipline mirrors S4-01.
11. **(coverage — harden) `delta_test_count >= 0 and exit_code == 0`
    success path pins `passed=True`.** Draft conflates exit-code and
    delta gating in a single AC; the truth-table needs to be exercised
    over the four (exit_code ∈ {0, ≠0}) × (delta ∈ {<0, ==0, >0}) ×
    (inventory ∈ {present, missing}) = 12 corners. AC-PASSED-TRUTH-1
    + a Hypothesis property AC-PROP-PASSED-1 (sharper than the draft's
    asymmetric-policy property — covers exit-code interaction).
12. **(coverage — harden) `failing_tests` and `first_failure`
    truncation pinned.** Draft says "comma-joined string" without a
    length cap — but `AttemptSummary.prior_failure_summary` per S1-04
    AC is `<= 4 KB`. An adversarial test name 64 KB long would defeat
    the AttemptSummary contract. AC-FAILING-TRUNC-1 pins
    `len(failing_tests.encode("utf-8")) <= 2048` (half of
    AttemptSummary's cap — leaves room for other keys); AC-FIRSTFAIL-TRUNC-1
    pins `len(first_failure.encode("utf-8")) <= 256` (matches S4-01
    `last_log_line` discipline).
13. **(coverage — harden) `first_failure` parsing pinned to test-name
    not log-line.** Draft test asserted `"auth" in sig.details["first_failure"]`
    — an impl that returns the entire `FAIL src/auth.test.ts > jwt-validates`
    line passes. The contract: `first_failure` is the **fully-qualified
    test name** (post-`>`), e.g. `"jwt-validates"` for jest, the `it`
    description for mocha. AC-FIRSTFAIL-SHAPE-1 pins via regex
    `^[^\s].+[^\s]$` AND byte-equality against per-format goldens.
14. **(coverage — harden) `failing_tests` ordering pinned
    deterministic.** Naive impl might emit `set`-ordered output. The
    spec hash chain (S3-01) + AttemptSummary deterministic-replay
    requirement (Phase 9) require byte-stable serialization. AC-FAILING-ORDER-1:
    `failing_tests` is alphabetically sorted, comma-joined (`, ` —
    comma + single space).
15. **(test-quality — block) `SandboxSpec` fixture-hash placeholder
    fixed.** Draft uses `sandbox_spec_hash="d"` (1 char) — S3-01 AC-HASH-FORMAT
    pins 32-char hex; S4-01 HARDENED #13 / AC-FIXTURE-HASH-1 pins
    `"0" * 32`. Fixture chokepoint via `tests/sandbox/conftest.py`
    `_make_run` (the same fixture S4-01 introduces). AC-FIXTURE-HASH-1
    reuses S4-01's chokepoint discipline — this story does NOT
    introduce a parallel fixture.
16. **(test-quality — block) Determinism property over **two distinct
    `SandboxRun` instances**.** Draft Hypothesis property re-calls
    `collect_test_signal` on a different `_make_run`-built instance
    per iteration, but for inventory permutations. The
    `inputs_blake3` determinism (S4-01 HARDENED #5) doesn't transfer
    automatically — added AC-DETERMINISM-1 covering test-signal's own
    `provenance.inputs_blake3` shape (delegated to S4-01's
    `_common.inputs_blake3`).
17. **(test-quality — harden) Parser-format cross-coverage
    parametrized.** Draft has jest-only test bodies. The three formats
    (jest, vitest, mocha) carry the same invariants under the
    `_FORMAT_PARSERS` table — AC-PARSER-PARITY-1 introduces a
    parametrize layer keyed on `(format_name, sample_log, expected_total,
    expected_failing)` so adding pytest in Phase 7.5 is one row.
18. **(test-quality — harden) Negative truth-table cases — exit nonzero
    + delta zero, exit zero + delta negative.** Draft's seven cases
    skip these. AC-PASSED-TRUTH-1 promotes the truth table to an
    exhaustive parametrize layer (12 corners × 3 parser formats = 36
    cases — kept fast since collector is pure).
19. **(consistency — harden) `pre_patch_inventory_path` source
    documented + out-of-scope.** Draft says "supplied via `GateContext`"
    but `GateContext` (per phase-arch §Data model) does NOT carry the
    path field. Resolution: the runner (S4-05 `StrictAndGate` /
    `GateRunner`) constructs the path from `ctx.workflow_id` +
    `ctx.run_id` (path convention pinned by Phase 3 — out of scope
    here). This story takes the path as a kwarg; **does not** reach
    into `GateContext`. Notes paragraph #5 makes the boundary explicit.
20. **(consistency — harden) `_test_parser.py` purity test landed.**
    AST scan asserts no I/O outside `logs_dir`; no top-level mutable
    state; no `subprocess` / `os.system` / network calls. New
    `tests/sandbox/test_signals_purity.py` (extends S4-01's file —
    not a new parallel file).
21. **(patterns — harden) `_TestFormatParser` Protocol + registry
    catalog for parser plug-points.** Three formats today, Phase 7.5
    Python (`pytest`) makes four — rule-of-three cleared. Strategy
    pattern as a Protocol + tuple-catalog: each parser is a frozen
    dataclass `(name: Literal[...], pattern: re.Pattern, total_group:
    str, failing_pattern: re.Pattern | None)`. Phase 7.5 adds a row,
    never edits `_test_parser.py`. AC-PARSER-REGISTRY-1..-3.
22. **(patterns — harden) Sum-type for `_ParsedTests.format`.**
    `format: Literal["jest", "vitest", "mocha", "unknown"]` — typed,
    pattern-matchable, "unknown" is the only path where `post_count == 0`.
    AC-PARSED-FORMAT-1.
23. **(patterns — harden) `_PrePatchInventory` is a frozen Pydantic
    model with strict primitives.** Mirrors S1-03 discipline.
    `model_config = ConfigDict(extra="forbid", frozen=True,
    strict=True)`. AC-INV-SCHEMA-1..-3.
24. **(patterns — harden) `Final` catalog of detail keys (S4-01
    pattern).** `_TEST_DETAIL_KEYS_FAIL` + `_TEST_DETAIL_KEYS_PASS`
    + `_TEST_DETAIL_KEYS_MISSING_INV` (three pinned key-sets — the
    failure path, the success path, the missing-inventory path). The
    full failure-path catalog already pinned via AC-DETAILS-KEYS-1;
    the three-catalog split documents the boundary the impl must
    honour. AC-DETAILS-KEYS-2..-3.
25. **(patterns — harden) Forward-seam Note: Phase 7.5 Python
    parser.** When Phase 7.5 adds `pytest` parsing, the registry takes
    one new `_TestFormatParser(...)` row; `tests.py` does not change.
    Notes paragraph #6 makes the extension contract explicit for the
    Phase 7.5 implementer.
26. **(consistency — harden) Module hygiene mirrored from S4-01.**
    `from __future__ import annotations`, module docstring citing
    ADR-0003/ADR-0014/ADR-0015/ADR-0001 + source story S4-02, `__all__`
    discipline, coverage floor wording (line ≥ 95% AND branch ≥ 90%).
    AC-DOC-1, AC-PURE-1..-3, AC-PG-2.
27. **(consistency — harden) Misleading Notes guidance — durations to
    int ms / lists to comma-joined.** S1-03 + S4-01 set this as a
    *details-shape* discipline. The Notes are corrected to scope only
    to (a) `failing_tests` as a comma-joined string and (b) `parser_format`
    as a `Literal[...]` string — no durations in S4-02's `details`.
28. **(test-quality — harden) Cross-format jest-fallback edge cases.**
    Draft test `JEST_FAIL` regex `"Tests:       41 failed, 1 passed,
    42 total\nFAIL src/auth.test.ts > jwt-validates"` couples the
    test-name to the FAIL banner. Real jest output puts the FAIL
    banner ABOVE the Tests summary line. The fixture is rewritten +
    AC-FIXTURE-LOG-1 mandates fixtures faithfully replicate real
    runner output order.

No `RESCUE`-tier findings — every gap was patchable by adding ACs,
tightening the TDD plan, formalizing the parser-registry, and pinning
the provenance/inventory contracts. No Stage-3 research needed — every
gap was answerable from Phase 5 arch + ADRs + the five prior HARDENED
reports (S1-02, S1-03, S1-05, S3-01, S4-01) + codebase precedents
([`codegenie.hashing`](../../../../src/codegenie/hashing.py),
[`transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py))
+ CLAUDE.md commitments (Extension by addition, Newtype identifiers,
Functional core / imperative shell, Rule 9, Rule 11). Goal (asymmetric
delta-policy collector for `"tests"` signal kind), scope (collector
only — runner-side wiring of inventory path is S4-04/S4-05),
dependencies (S1-03, S1-05, S3-07, **+ S4-01**), out-of-scope discipline,
and ADR mapping (-0003, -0014, -0015, +0001 chokepoint) are unchanged.

## Context

`collect_test_signal` is the load-bearing collector for the most
documented adversarial path in the phase: an LLM-produced patch deletes
a failing test to make `npm test` pass. ADR-0015 establishes asymmetric
inventory policy — `delta_test_count < 0` fails strict-AND;
`delta_test_count > 0` is informational. The collector reads the
post-patch test run from `SandboxRun.logs_dir` and compares against a
pre-patch inventory snapshot path supplied as a kwarg by the runner
(Phase 3 produces and persists the snapshot before Phase 4 runs; the
runner — S4-05 `StrictAndGate` / S5-02 `GateRunner` — owns the path
derivation from `GateContext.workflow_id` / `ctx.run_id`. This story
treats the path as an opaque kwarg input).

This is the **third** signal collector after `collect_build_signal` /
`collect_install_signal` (S4-01) and the **first** with an
extra-kwarg input — S4-01's `_collect_simple` Strategy helper is
intentionally NOT used here (S4-01 Notes #7 pins the trigger at the
Phase-7 third no-extra-input collector). S4-02 instead consumes
S4-01's `_common.py` helpers (`build_provenance`, `inputs_blake3`,
`read_last_log_line`, `utc_now`) as the ADR-0001 hashing chokepoint
mandates — never importing `blake3` directly.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Signal collectors` —
  `collect_test_signal(run, *, pre_patch_inventory_path: Path) -> TestSignal`
  signature; ≤ 60 LOC excluding parser helpers.
- **Architecture:** `../phase-arch-design.md §Edge cases 6, 7, 17` —
  test removal adversarial path, legitimate additions, 3× repeated
  `failed_unrecoverable`.
- **Architecture:** `../phase-arch-design.md §Data model` —
  `TestSignal(_SignalBase)`, `SignalProvenance` shape, `details: dict[str,
  str | int | bool]` constraint (no float, no nested dict, no list as
  value).
- **Phase ADRs:** `../ADRs/0015-test-inventory-delta-asymmetric-policy.md`
  — ADR-0015 — `delta < 0` → `passed=False`; `delta > 0` → annotation
  only; `details["delta_test_count"]` always emitted (zero, positive,
  or negative).
- **Phase ADRs:** `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md`
  — ADR-0014 — `details` typing constraint; four banned substrings in
  field names.
- **Phase ADRs:** `../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md`
  — ADR-0003 — registers via `@register_signal_kind("tests")`.
- **Production ADRs:** [`../../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md`](../../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md)
  — ADR-0001 — `codegenie.hashing` is the single sanctioned hash
  entry point; no other module imports `blake3` directly.
- **High-level impl:** `../High-level-impl.md §Step 4` — done
  criterion: "delta_test_count = -1 when a test file is removed by the
  patch (against `tests/fixtures/repos/test-removes-test/`)".
- **Existing code (S4-01 — DEPENDENCY):**
  [`src/codegenie/sandbox/signals/_common.py`](../../../../src/codegenie/sandbox/signals/_common.py)
  — S4-01 ships `read_last_log_line`, `inputs_blake3`,
  `build_provenance(*, signal_kind, collector_module, run)`, `utc_now`.
  This story REUSES these helpers; does NOT duplicate them.
- **Existing code (S1-03 — DEPENDENCY):**
  `src/codegenie/sandbox/signals/models.py` — `TestSignal`,
  `SignalProvenance`, `_SignalBase`.
- **Existing code (S1-05 — DEPENDENCY):**
  `src/codegenie/sandbox/signals/registry.py` —
  `@register_signal_kind` decorator that delegates to Phase 3's
  `signal_kind_registry`.
- **Existing code (Phase 3 — PRE-REGISTERED):**
  [`src/codegenie/transforms/signal_kinds.py:156`](../../../../src/codegenie/transforms/signal_kinds.py)
  — `TESTS = register_signal_kind("tests")` is already executed at
  Phase-3 module-import time. S1-05's decorator handles the
  idempotent re-registration; no special handling needed in
  `tests.py`.
- **Sibling validation reports (consult before implementing):**
  [`_validation/S1-03-objective-signals-models.md`](_validation/S1-03-objective-signals-models.md),
  [`_validation/S1-05-registries-and-env-allowlist.md`](_validation/S1-05-registries-and-env-allowlist.md),
  [`_validation/S3-01-spec-builder-canonical-hash.md`](_validation/S3-01-spec-builder-canonical-hash.md),
  [`_validation/S4-01-build-install-collectors.md`](_validation/S4-01-build-install-collectors.md)
  — pattern + naming + canonical-JSON precedents this story mirrors.

## Goal

Ship `collect_test_signal(run: SandboxRun, *, pre_patch_inventory_path:
Path) -> TestSignal` that parses jest / vitest / mocha output from
`run.logs_dir`, computes `delta_test_count = parsed.total_count -
pre_inventory.test_count` against a Pydantic-validated snapshot, and
sets `passed = (run.exit_code == 0 and delta_test_count >= 0)`. The
collector mints `TestSignal.provenance` via S4-01's
`_common.build_provenance(...)` chokepoint, mints `at` via
`_common.utc_now()`, and registers via Phase 5's
`@register_signal_kind("tests")` decorator (which delegates
idempotently to Phase 3's pre-registered `"tests"` name).

## Acceptance criteria

### A. Module surface, hygiene, and registration

- [ ] **AC-API-1** `src/codegenie/sandbox/signals/tests.py` defines
  `collect_test_signal(run: SandboxRun, *, pre_patch_inventory_path:
  Path) -> TestSignal`, ≤ 60 LOC excluding imports/`__all__` (parser
  + inventory-reader live in sibling files).
- [ ] **AC-API-2** `src/codegenie/sandbox/signals/_test_parser.py`
  defines `parse_test_results(logs_dir: Path) -> _ParsedTests`, ≤ 80
  LOC; pure modulo I/O on `logs_dir / "stdout.log"`.
- [ ] **AC-API-3** `src/codegenie/sandbox/signals/_test_inventory.py`
  defines `read_pre_inventory(path: Path) -> _PrePatchInventory | None`,
  ≤ 30 LOC; returns `None` on missing-or-corrupt file (never raises).
- [ ] **AC-DOC-1** `tests.py` module docstring's first non-blank
  paragraph references `ADR-0015`, `ADR-0014`, `ADR-0003`, `ADR-0001`
  (hashing chokepoint), and source story `S4-02`. Asserted by AST
  scan over module source. Same discipline for `_test_parser.py` and
  `_test_inventory.py`.
- [ ] **AC-PURE-1** Each of the three modules has `from __future__
  import annotations` as the first non-docstring line.
- [ ] **AC-PURE-2** `set(codegenie.sandbox.signals.tests.__all__) ==
  {"collect_test_signal"}` (byte-exact).
- [ ] **AC-PURE-3** `set(codegenie.sandbox.signals._test_parser.__all__)
  == {"parse_test_results", "_FORMAT_PARSERS", "_ParsedTests",
  "_TestFormatParser"}`. Names starting with `_` are intentionally in
  `__all__` because S4-02's purity-fence + parametrize-layer tests
  import them (mirrors S4-01's `_common.py` `__all__` discipline:
  module-private filename, test-accessible names).
- [ ] **AC-PURE-4** `set(codegenie.sandbox.signals._test_inventory.__all__)
  == {"read_pre_inventory", "_PrePatchInventory"}`.
- [ ] **AC-INIT-1** `src/codegenie/sandbox/signals/__init__.py`
  imports `tests` (in addition to the `build, install` lines from
  S4-01) so that `@register_signal_kind` fires at package import
  time. Asserted by AST scan of `__init__.py` finding `from . import
  ..., tests` (alphabetized).
- [ ] **AC-INIT-2** After `import codegenie.sandbox.signals`, the
  call `signal_collector_registry.get(SignalKind("tests")) is
  collect_test_signal` returns `True`. Verifies registration
  side-effect actually fires.
- [ ] **AC-REG-IDEMPOTENT-1** Importing `tests.py` does NOT raise
  `codegenie.transforms.signal_kinds.SignalKindAlreadyRegistered`
  even though `"tests"` is **already** pre-registered in Phase 3's
  `signal_kind_registry` per
  [`transforms/signal_kinds.py:156`](../../../../src/codegenie/transforms/signal_kinds.py).
  S1-05's decorator delegation makes this idempotent; AC closes the
  regression risk. Tested by a pytest that constructs
  `SignalCollectorRegistry.fresh()`, then re-invokes the decorator
  against the fresh instance — no error.
- [ ] **AC-NEWTYPE-1** `signal_collector_registry.get(SignalKind("tests"))`
  (NewType-keyed lookup, NOT raw `str`) returns `collect_test_signal`.
  Matches S1-05 AC-CR-7.
- [ ] **AC-REG-TEST-1** Registry-resolution assertions appended to
  the **existing** `tests/sandbox/test_signal_collector_registry.py`
  from S1-05 — NOT a new parallel file. Avoids split test ownership
  of the same registry. Mirror of S4-01 AC-REG-TEST-1.

### B. `passed` truth table (ADR-0015 asymmetric policy)

- [ ] **AC-PASSED-TRUTH-1** `collect_test_signal` computes `passed =
  (run.exit_code == 0 and delta_test_count >= 0)`. Asserted via the
  full truth table: `exit_code ∈ {0, ≠0}` × `delta ∈ {<0, ==0, >0}`
  × `inventory ∈ {present, missing}` = **12 corners** — exhaustive
  parametrize layer, mutation-resistant to `and→or`, `>=→>`, `==→!=`.
- [ ] **AC-PROP-PASSED-1** Hypothesis property: `@given(pre=st.integers(0,
  10_000), post=st.integers(0, 10_000), exit_code=st.integers(-1,
  255))` over `collect_test_signal` — `delta = post - pre`; if
  `exit_code == 0 and delta >= 0`: `passed is True`; else `passed
  is False`. AND `details["delta_test_count"] == delta` always.
  Catches the `and→or` mutation that 12 corner-cases miss.
- [ ] **AC-FAILURES-NOT-FALSIFY-DELTA-1** When `run.exit_code != 0`
  AND `parsed.total_count == pre_count` (all tests still present,
  some failing), `delta_test_count == 0` AND `passed is False`. The
  adversarial path ADR-0015 polices is **test files removed**, NOT
  **tests failing**. New test `test_failures_do_not_falsify_delta`.

### C. `details` shape — failure path

- [ ] **AC-DETAILS-KEYS-1** On the failure path where the inventory
  was readable (`passed=False`, exit nonzero OR delta negative), the
  failure-path `details` carries EXACTLY the keys in
  `_TEST_DETAIL_KEYS_FAIL: Final[frozenset[str]] =
  frozenset({"delta_test_count", "first_failure", "failing_tests",
  "parser_format", "exit_code", "timed_out", "killed_by_oom"})`. Module-
  level catalog in `tests.py` (S1-03 Notes pattern, S4-01 precedent).
- [ ] **AC-DETAILS-KEYS-2** On the success path (`passed=True`),
  `details` carries EXACTLY
  `_TEST_DETAIL_KEYS_PASS: Final[frozenset[str]] =
  frozenset({"delta_test_count", "parser_format"})`. (`delta_test_count`
  always present per ADR-0015 invariant; `parser_format` documents
  which regex hit.)
- [ ] **AC-DETAILS-KEYS-3** On the missing-or-corrupt-inventory path,
  `details` carries EXACTLY
  `_TEST_DETAIL_KEYS_MISSING_INV: Final[frozenset[str]] =
  frozenset({"delta_test_count", "parser_format",
  "pre_patch_inventory_missing"})`. The fourth key is the annotation;
  `delta_test_count == 0` per AC-INV-CORRUPT-1.
- [ ] **AC-DETAILS-KEYS-IMPORT-1** Catalogs assert via import:
  `from codegenie.sandbox.signals.tests import (
  _TEST_DETAIL_KEYS_FAIL, _TEST_DETAIL_KEYS_PASS,
  _TEST_DETAIL_KEYS_MISSING_INV)` (single-underscore — module-private
  but test-accessible). Mirrors S4-01 AC-DETAILS-KEYS-2 idiom.
- [ ] **AC-DETAILS-TYPES-1** Value types on each path enforced via
  `type(v) is …` identity (closes the `bool ⊂ int` ambiguity):
  `type(d["delta_test_count"]) is int`,
  `type(d["first_failure"]) is str`, `type(d["failing_tests"]) is str`,
  `type(d["parser_format"]) is str`, `type(d["exit_code"]) is int`,
  `type(d["timed_out"]) is bool`, `type(d["killed_by_oom"]) is bool`,
  `type(d["pre_patch_inventory_missing"]) is bool`.
- [ ] **AC-DETAILS-NOBAN-1** No key in `_TEST_DETAIL_KEYS_FAIL ∪
  _TEST_DETAIL_KEYS_PASS ∪ _TEST_DETAIL_KEYS_MISSING_INV` contains
  any of the substrings `confidence`, `llm`, `self_reported`,
  `model_says` (ADR-0014 — all four, not just one). Asserted via
  iteration over the three frozensets AND via re-running
  `iter_nested_field_names` over `TestSignal`.

### D. `delta_test_count` invariant (ADR-0015)

- [ ] **AC-DELTA-1** `details["delta_test_count"]` is **always** an
  `int` and **always** present — zero, positive, or negative — never
  `None`, never missing, never `float`. Asserted on every of the 12
  truth-table corners + missing-inventory + corrupt-inventory + all
  three parser formats.
- [ ] **AC-DELTA-POSITIVE-INFO-1** When `delta_test_count > 0` AND
  `run.exit_code == 0`, `passed=True` AND
  `sig.details["delta_test_count"] > 0` (informational annotation).
- [ ] **AC-DELTA-NEGATIVE-FAIL-1** When `delta_test_count < 0`,
  `passed=False` REGARDLESS of `run.exit_code` (the adversarial
  signature ADR-0015 catches). Even `exit_code == 0` with negative
  delta is `passed=False`.

### E. `first_failure` / `failing_tests` shape

- [ ] **AC-FIRSTFAIL-SHAPE-1** `details["first_failure"]` is the
  **fully-qualified test name** (the descriptor after the format-
  specific separator: `>` for jest/vitest, `it(…)` text for mocha) —
  NOT the entire `FAIL <path>` banner. For jest's `"FAIL src/auth.test.ts
  > jwt-validates"`, `first_failure == "jwt-validates"`. Asserted via
  regex `^[^\s].+[^\s]$` (no leading/trailing whitespace) AND
  byte-equality against per-format goldens.
- [ ] **AC-FIRSTFAIL-EMPTY-1** When `parsed.failing == []` AND
  `run.exit_code != 0`, `first_failure == ""` (empty string — NOT
  `None`, NOT `"unknown"`). Documents "exit code says failure but
  parser found no failing-test name" (e.g. build failed before test
  start).
- [ ] **AC-FIRSTFAIL-TRUNC-1** `len(first_failure.encode("utf-8")) <=
  256` UTF-8 bytes; truncation is byte-safe (drop trailing partial-
  multibyte sequences). Matches S4-01 `last_log_line` discipline.
- [ ] **AC-FAILING-SHAPE-1** `details["failing_tests"]` is a
  comma-joined string of fully-qualified failing-test names,
  separator `", "` (comma + single space) — NOT `list[str]`
  (S1-03 / ADR-0014 reject list values).
- [ ] **AC-FAILING-ORDER-1** Failing test names within `failing_tests`
  are sorted lexicographically (ASCII order). A naive set-ordered impl
  fails this AC. Required for byte-stable AttemptSummary across runs
  (S1-04 + Phase 9 replay).
- [ ] **AC-FAILING-TRUNC-1** `len(failing_tests.encode("utf-8")) <=
  2048` UTF-8 bytes (half of AttemptSummary's 4 KB
  `prior_failure_summary` cap from S1-04 — leaves room for other
  keys). When truncated, the field ends with `…` (single Unicode
  HORIZONTAL ELLIPSIS, U+2026) to mark truncation; the last name
  before `…` is whole (no mid-name cut).
- [ ] **AC-FAILING-EMPTY-1** When `parsed.failing == []`,
  `failing_tests == ""` (empty string).

### F. `parser_format` discriminator

- [ ] **AC-PARSED-FORMAT-1** `_ParsedTests.format` is a
  `Literal["jest", "vitest", "mocha", "unknown"]` field. AST scan
  asserts the `Literal` type hint is present in
  `_test_parser.py`. Type-safe and pattern-matchable.
- [ ] **AC-PARSEDETAILS-1** `details["parser_format"]` carries
  exactly one of `"jest" | "vitest" | "mocha" | "unknown"` on every
  path (failure / success / missing-inventory).
- [ ] **AC-PARSER-UNKNOWN-1** When the regex set fails to match,
  `_ParsedTests.format == "unknown"` AND
  `_ParsedTests.total_count == 0` AND `_ParsedTests.failing == ()`.
  Collector sets `details["parser_format"] = "unknown"` AND
  `details["delta_test_count"] = -pre_count` (with `pre_count == 0`
  when inventory missing). NOT `delta = 0` — an unparseable log with
  a known pre-inventory IS a regression signal.

### G. `_FORMAT_PARSERS` Strategy registry (extension-by-addition)

- [ ] **AC-PARSER-REGISTRY-1** `_FORMAT_PARSERS: Final[tuple[
  _TestFormatParser, ...]]` is a module-level tuple in
  `_test_parser.py` whose elements are frozen Pydantic models or
  frozen dataclasses, ordered by precedence (jest, vitest, mocha).
  Adding a new format (Phase 7.5 `pytest`) is one row in this tuple
  + a new test row — never an edit to `parse_test_results`.
  AST scan asserts the tuple exists, is `Final`, and contains exactly
  3 entries on the S4-02 PR (4+ when Phase 7.5 lands).
- [ ] **AC-PARSER-REGISTRY-2** `_TestFormatParser` is a frozen
  Pydantic model (or frozen dataclass) with fields `name:
  Literal["jest","vitest","mocha"]`, `pattern: re.Pattern[str]`
  (matches the summary line that yields totals), `total_group: str`
  (regex group name for the total count), `failing_pattern:
  re.Pattern[str] | None` (regex that locates failing test names —
  multi-match). `extra="forbid", frozen=True`.
- [ ] **AC-PARSER-REGISTRY-3** Precedence policy: parsers are tried
  in tuple order; **first match wins**; subsequent parsers are not
  consulted. AC enforces order-stability: a log line matching BOTH
  jest's pattern AND vitest's pattern is parsed as jest (the first
  entry).
- [ ] **AC-PARSER-PARITY-1** Per-format invariants exercised via a
  SINGLE parametrize layer:
  ```python
  @pytest.mark.parametrize("format_name,sample_log,expected_total,expected_failing", [...])
  ```
  Three rows today; Phase 7.5 adds `pytest` row without editing test
  logic.

### H. `_PrePatchInventory` schema (Pydantic strict)

- [ ] **AC-INV-SCHEMA-1** `_PrePatchInventory` is a frozen Pydantic
  model in `_test_inventory.py` with `model_config = ConfigDict(extra=
  "forbid", frozen=True, strict=True)` and fields: `test_count:
  pydantic.NonNegativeInt`, `test_names: tuple[str, ...]` (frozen —
  NOT `list` — mirrors S1-03 immutable-collection discipline),
  `captured_at: pydantic.AwareDatetime`. Constructing with `test_count:
  -1` raises `pydantic.ValidationError`; with `captured_at` naive
  raises `pydantic.ValidationError`.
- [ ] **AC-INV-SCHEMA-2** Unknown field in the JSON file (e.g.
  `{"test_count": 42, "smuggled": "yes", ...}`) raises
  `pydantic.ValidationError` at construction (`extra="forbid"`).
- [ ] **AC-INV-SCHEMA-3** `set(_PrePatchInventory.model_fields.keys())
  == {"test_count", "test_names", "captured_at"}` byte-exact.
- [ ] **AC-INV-MISSING-1** When `pre_patch_inventory_path` does NOT
  exist, `read_pre_inventory(...)` returns `None` (does NOT raise).
  Collector sets `details["pre_patch_inventory_missing"] = True` AND
  `details["delta_test_count"] = 0`.
- [ ] **AC-INV-CORRUPT-1** When `pre_patch_inventory_path` exists but
  the bytes do NOT parse as the schema (truncated JSON, wrong
  field types, banned `extra` field), `read_pre_inventory(...)`
  returns `None` (does NOT raise — corrupt is treated the SAME as
  missing). Phase 3 may not be ready, OR the file was partially
  written under crash — either way, the collector ANNOTATES and
  proceeds with `delta_test_count = 0`. Audit-event logging of the
  corruption is the runner's job (S5-02 — out of scope here).
- [ ] **AC-INV-PERM-1** When `pre_patch_inventory_path` is unreadable
  (PermissionError), `read_pre_inventory(...)` returns `None`. Same
  surface as missing/corrupt.
- [ ] **AC-INV-NEVER-RAISES-1** `read_pre_inventory(...)` raises ONLY
  on programming errors (e.g. `path` is not `Path`). Asserted by
  test parametrize over: missing file, permission denied, truncated
  JSON, wrong field type, extra field, empty file, directory (not
  file), symlink loop — every case returns `None`.

### I. `SignalProvenance` value pinning (S4-01 chokepoint reuse)

- [ ] **AC-PROV-FACTORY-1** `collect_test_signal` builds
  `provenance` by calling S4-01's
  `_common.build_provenance(signal_kind=SignalKind("tests"),
  collector_module=__name__, run=run)` — does NOT instantiate
  `SignalProvenance(...)` directly. AST scan of `tests.py` source
  asserts `from codegenie.sandbox.signals._common import
  build_provenance` is present AND `SignalProvenance(` does NOT
  appear in the source (factory chokepoint discipline).
- [ ] **AC-PROV-KIND-1** `collect_test_signal(_make_run(...),
  pre_patch_inventory_path=...).provenance.signal_kind ==
  SignalKind("tests")`.
- [ ] **AC-PROV-KIND-2** `type(sig.provenance.signal_kind) is str`
  (NewType's runtime identity is `str`; mypy-level `SignalKind`
  distinction is annotation-only — see S1-03 AC-4 / AC-4a).
- [ ] **AC-PROV-MODULE-1** `sig.provenance.collector_module ==
  "codegenie.sandbox.signals.tests"` byte-exact.
- [ ] **AC-PROV-MODULE-2** AST scan of `tests.py` source asserts the
  collector passes `__name__` to `build_provenance` (NOT a hardcoded
  string literal); test asserts `sig.provenance.collector_module ==
  __name__`.
- [ ] **AC-PROV-VERSION-1** `sig.provenance.collector_version == "1"`
  byte-exact (string, NOT int). A bump is an ADR amendment per arch
  §Signal collectors.
- [ ] **AC-HASH-CHOKEPOINT-1** `tests.py`, `_test_parser.py`, AND
  `_test_inventory.py` MUST NOT `import blake3` or `from blake3
  import …` directly. AST scan over `signals/**/*.py` (extends the
  S4-01 chokepoint scan; the AST test from S4-01 already covers this
  scope — no new test file needed, but AC is restated for clarity).
- [ ] **AC-HASH-CHOKEPOINT-2** `tests.py` MUST NOT call
  `codegenie.hashing.content_hash_bytes` directly — the indirection
  is `_common.build_provenance` (which calls
  `_common.inputs_blake3` → `content_hash_bytes`). AST scan of
  `tests.py` asserts `content_hash_bytes` is not imported.
  (Defence in depth: a refactor that bypasses `_common.build_provenance`
  in favour of a direct `content_hash_bytes` call would split the
  chokepoint. Both `tests.py` and `_common.py` calling it is fine —
  this AC pins the **collector's** indirection through `_common`.)
- [ ] **AC-DETERMINISM-1** Two distinct `SandboxRun` instances
  constructed with identical kwargs (different Python `id()`)
  produce byte-equal `sig.provenance.inputs_blake3`. Test uses two
  distinct `_make_run(...)` calls — mirrors S4-01 AC-DETERMINISM-1.

### J. Timezone-aware `at` (S1-03)

- [ ] **AC-AT-TZ-1** `sig.at.tzinfo is not None` AND
  `sig.at.tzinfo.utcoffset(sig.at).total_seconds() == 0` (UTC, not
  just "any tzinfo"). Collector uses S4-01's `_common.utc_now()`
  exclusively — never `datetime.now()` / `datetime.utcnow()` /
  `datetime.now(UTC)`.
- [ ] **AC-AT-TZ-2** AST scan of `tests.py` source asserts
  `datetime.utcnow(` does NOT appear AND `datetime.now()` does NOT
  appear (without a `tzinfo` argument). The single sanctioned path
  is `from codegenie.sandbox.signals._common import utc_now; utc_now()`.

### K. Parser unit tests (table-driven)

- [ ] **AC-PARSER-JEST-1** Jest sample logs parsed correctly:
  `Tests: 42 passed, 42 total` → `total_count=42, failing=()`,
  `format="jest"`. `Tests: 1 failed, 41 passed, 42 total` →
  `total_count=42, failing=("<test-name>",)`, `format="jest"`. Failing-
  test-name extraction follows `FAIL <path>\s*>\s*<name>` precedent.
- [ ] **AC-PARSER-VITEST-1** Vitest sample logs parsed correctly.
  Vitest summary differs from jest in column alignment but uses the
  same `Tests:` / `Test Files:` summary. The `_FORMAT_PARSERS` entry
  for vitest is **distinct** from jest's even if outwardly similar —
  AC enforces an actual vitest sample log triggers the vitest
  parser, not jest's. (Fixture: a real vitest run.)
- [ ] **AC-PARSER-MOCHA-1** Mocha sample logs parsed: `42 passing
  (3s)` / `1 failing\n  AuthService\n    > "jwt-validates"` →
  `total_count=42, failing=("jwt-validates",)`, `format="mocha"`.
  Mocha's `total` is `passing + failing` (no explicit `total` line);
  parser computes it.
- [ ] **AC-FIXTURE-LOG-1** Fixture logs faithfully replicate real
  runner output ORDER: jest emits the `FAIL …` banner BEFORE the
  `Tests:` summary; vitest emits its `❯` icons; mocha emits its
  indented test-name tree. A test parametrized on `(fixture_path,
  expected_format, expected_total, expected_failing)` runs the
  parser over each fixture log; goldens checked into
  `tests/fixtures/test_runner_logs/{jest, vitest, mocha}/*.log`.
- [ ] **AC-POSTCOUNT-1** `_ParsedTests.total_count` is the **total
  test count** (passed + failed + skipped + todo for jest/vitest;
  passing + failing for mocha) — NOT `passed`-only. Documents
  that a patch where all 42 tests still exist but newly fail gives
  `delta = 0` (exit_code says failure; delta doesn't).

### L. Adversarial + informational integration tests

- [ ] **AC-ADVERSARIAL-1** Integration test against
  `tests/fixtures/repos/test-removes-test/`: a `pre_inventory.json`
  with `test_count=42, test_names=[…42 names…]` + a `sandbox_run/logs/
  stdout.log` showing `Tests: 41 passed, 41 total` (post-removal) +
  `exit_code=0` → `collect_test_signal(...)` returns `TestSignal(
  passed=False, ...)` with `details["delta_test_count"] == -1` AND
  `details["parser_format"] == "jest"`. **Load-bearing per ADR-0015.**
- [ ] **AC-INFORMATIONAL-1** Integration test against
  `tests/fixtures/repos/test-adds-regression/`: a `pre_inventory.json`
  with `test_count=42` + a `sandbox_run/logs/stdout.log` showing
  `Tests: 43 passed, 43 total` + `exit_code=0` → `TestSignal(
  passed=True, ...)` with `details["delta_test_count"] == +1` AND
  `details["parser_format"] == "jest"`.
- [ ] **AC-ADVERSARIAL-2** Adversarial extension: same
  `test-removes-test/` fixture but with `exit_code=1` (the patch
  ALSO broke a test on the way out) — still
  `passed=False, delta_test_count=-1`; both signatures trigger
  asymmetric policy.

### M. Fence preservation

- [ ] **AC-FENCE-1** `tests/schema/test_objective_signals_static.py`
  still green — no banned substring entered the `ObjectiveSignals`
  type tree (this story does NOT modify `ObjectiveSignals`;
  `_TEST_DETAIL_KEYS_*` are module-level catalogs not traversed by
  the walker — AC-DETAILS-NOBAN-1 is the defence-in-depth on the
  catalog values themselves).
- [ ] **AC-FENCE-2** `tests/sandbox/test_signals_purity.py` (the
  S4-01 file — extended) still green: `tests.py` /
  `_test_parser.py` / `_test_inventory.py` do NOT import `blake3`
  / `hashlib.sha256` / `subprocess` / `os.system` / `requests` /
  `urllib.request` / any network or process module.
- [ ] **AC-FENCE-3** `tests/sandbox/test_signals_fixture_hash_discipline.py`
  (S4-01) still green: no inline `sandbox_spec_hash=` literal under
  `tests/sandbox/**` deviates from `"0" * 32`.

### N. Quality gates

- [ ] **AC-PG-1** `ruff check`, `ruff format --check`, `mypy --strict`
  pass on `src/codegenie/sandbox/signals/{tests,_test_parser,
  _test_inventory,__init__}.py`.
- [ ] **AC-PG-2** Coverage on touched files: **line ≥ 95% AND branch
  ≥ 90%** (matches phase README definition-of-done; mirrors S4-01
  AC-PG-2).
- [ ] **AC-PG-3** TDD plan's red test exists in commit history
  (separate commit before the green commit), is committed, and is
  green at the end of the story.

## Implementation outline

1. **Reuse S4-01's `_common.py` — do NOT duplicate helpers.** S4-02
   imports `build_provenance`, `utc_now` from
   `codegenie.sandbox.signals._common`. The `inputs_blake3` and
   `read_last_log_line` helpers from S4-01 are NOT consumed by
   `collect_test_signal` directly (the collector hashes a
   structurally different input — runtime by `build_provenance` —
   and uses the parser, not last-log-line). The ADR-0001 chokepoint
   discipline holds regardless: `tests.py` imports nothing from
   `blake3` / `hashlib.sha256`.

2. **Create `src/codegenie/sandbox/signals/_test_parser.py`:**
   - `from __future__ import annotations`; module docstring per
     AC-DOC-1; `from typing import Final, Literal`; `from dataclasses
     import dataclass` (frozen).
   - `@dataclass(frozen=True, slots=True) class _TestFormatParser:
     name: Literal["jest","vitest","mocha"]; pattern: re.Pattern[str];
     total_group: str; failing_pattern: re.Pattern[str] | None`.
   - `@dataclass(frozen=True, slots=True) class _ParsedTests:
     format: Literal["jest","vitest","mocha","unknown"];
     total_count: int; failing: tuple[str, ...]; first_failure: str`.
   - `_FORMAT_PARSERS: Final[tuple[_TestFormatParser, ...]] = (
     _TestFormatParser(name="jest", pattern=..., total_group="total",
     failing_pattern=...), _TestFormatParser(name="vitest", ...),
     _TestFormatParser(name="mocha", ..., failing_pattern=...), )`.
     **Three rows on this PR.** Phase 7.5 adds `pytest` as the
     fourth row.
   - `def parse_test_results(logs_dir: Path) -> _ParsedTests`: reads
     `logs_dir / "stdout.log"` (bytes), decodes UTF-8 errors=replace,
     iterates `_FORMAT_PARSERS` in tuple order, returns the first
     hit; on no match returns `_ParsedTests(format="unknown",
     total_count=0, failing=(), first_failure="")`.
   - `__all__` per AC-PURE-3.

3. **Create `src/codegenie/sandbox/signals/_test_inventory.py`:**
   - `from __future__ import annotations`; module docstring.
   - `class _PrePatchInventory(BaseModel): model_config =
     ConfigDict(extra="forbid", frozen=True, strict=True);
     test_count: NonNegativeInt; test_names: tuple[str, ...];
     captured_at: AwareDatetime`.
   - `def read_pre_inventory(path: Path) -> _PrePatchInventory |
     None`: returns `None` on FileNotFoundError, PermissionError,
     IsADirectoryError, OSError, JSONDecodeError, ValidationError —
     mirrors S4-01 `read_last_log_line` failure-mode discipline.
   - `__all__` per AC-PURE-4.

4. **Create `src/codegenie/sandbox/signals/tests.py`:**
   - `from __future__ import annotations`; module docstring per
     AC-DOC-1; `from typing import Final`.
   - `_TEST_DETAIL_KEYS_FAIL: Final[frozenset[str]] = frozenset({
     "delta_test_count", "first_failure", "failing_tests",
     "parser_format", "exit_code", "timed_out", "killed_by_oom"})`.
   - `_TEST_DETAIL_KEYS_PASS: Final[frozenset[str]] = frozenset({
     "delta_test_count", "parser_format"})`.
   - `_TEST_DETAIL_KEYS_MISSING_INV: Final[frozenset[str]] =
     frozenset({"delta_test_count", "parser_format",
     "pre_patch_inventory_missing"})`.
   - `_MAX_FAILING_TESTS_BYTES: Final[int] = 2048`.
   - `_MAX_FIRST_FAILURE_BYTES: Final[int] = 256`.
   - `@register_signal_kind("tests") def collect_test_signal(run:
     SandboxRun, *, pre_patch_inventory_path: Path) -> TestSignal`:
     - `parsed = parse_test_results(run.logs_dir)`.
     - `inv = read_pre_inventory(pre_patch_inventory_path)`.
     - `delta = (parsed.total_count - inv.test_count) if inv is not
       None else 0`.
     - `passed = (run.exit_code == 0 and delta >= 0)` (NB: when
       `inv is None`, `delta == 0` so `passed` reduces to
       `run.exit_code == 0`).
     - Build `details` per the three catalogs (failure / success /
       missing-inv).
     - Sort + truncate `failing_tests`; truncate `first_failure`.
     - Mint provenance via `_common.build_provenance(signal_kind=
       SignalKind("tests"), collector_module=__name__, run=run)`.
     - `return TestSignal(passed=passed, details=details,
       provenance=provenance, at=utc_now())`.
   - `__all__ = ["collect_test_signal"]`.

5. **Update `src/codegenie/sandbox/signals/__init__.py`** to import
   `tests` (extends the `from . import build, install` line from
   S4-01 → `from . import build, install, tests`; keep alphabetized).

6. **Add `tests/sandbox/test_signals_tests.py`** — the parametrized
   layer (truth table, property test, detail-key catalogs, provenance
   pinning, parser-format parity, adversarial + informational
   integration cases).

7. **EXTEND** `tests/sandbox/test_signal_collector_registry.py`
   (the S1-05 file — already extended by S4-01) with AC-NEWTYPE-1 /
   AC-INIT-2 assertions for `"tests"`.

8. **EXTEND** `tests/sandbox/test_signals_purity.py` (the S4-01 file)
   with AST-scan assertions over `tests.py`, `_test_parser.py`,
   `_test_inventory.py`: no `blake3` / `hashlib.sha256` / `subprocess`
   / network imports.

9. **Add `tests/sandbox/test_pre_inventory_schema.py`** — focused
   Pydantic-validation suite for `_PrePatchInventory` (extra=forbid,
   naive datetime rejection, negative test_count rejection, etc.).

10. **Add fixture directories:**
    - `tests/fixtures/repos/test-removes-test/pre_inventory.json` +
      `sandbox_run/logs/stdout.log` (jest, post-removal).
    - `tests/fixtures/repos/test-adds-regression/pre_inventory.json`
      + `sandbox_run/logs/stdout.log` (jest, post-addition).
    - `tests/fixtures/test_runner_logs/jest/{ok, removed, added,
      failed}.log`.
    - `tests/fixtures/test_runner_logs/vitest/{ok, failed}.log`.
    - `tests/fixtures/test_runner_logs/mocha/{ok, failed}.log`.

11. **Run** `tests/schema/test_objective_signals_static.py` locally
    to confirm AC-FENCE-1.

## TDD plan — red / green / refactor

### Red — write the failing tests first

The test plan exercises the truth table exhaustively via parametrize
layers (mutation-resistant) plus per-format goldens plus structural
fences. Mirroring the S4-01 pattern: a single parametrized file for
collector invariants, separate focused files for Pydantic-validation
and AST-fence concerns.

#### Shared fixture chokepoint — `tests/sandbox/conftest.py` (extend S4-01's)

The `_make_run` fixture from S4-01 is reused. S4-02 ADDS a small
helper `_write_pre_inventory(path, *, test_count, test_names=…)` to
the same conftest:

```python
# tests/sandbox/conftest.py  (extend — single chokepoint)
@pytest.fixture
def _write_pre_inventory(tmp_path: Path):
    """Single helper to materialize a pre_inventory.json.

    Why: tests need to vary test_count / test_names but the schema
    fields (and captured_at format) must stay in lock-step with
    _PrePatchInventory. Single fixture point of update.
    """

    def _factory(
        path: Path,
        *,
        test_count: int,
        test_names: tuple[str, ...] = (),
        captured_at: str = "2026-05-12T00:00:00+00:00",
    ) -> None:
        path.write_text(
            json.dumps(
                {
                    "test_count": test_count,
                    "test_names": list(test_names),
                    "captured_at": captured_at,
                },
                separators=(",", ":"),
            )
        )

    return _factory
```

#### Parametrized collector tests — `tests/sandbox/test_signals_tests.py`

```python
# tests/sandbox/test_signals_tests.py
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from codegenie.sandbox.signals.models import TestSignal
from codegenie.sandbox.signals.registry import signal_collector_registry
from codegenie.sandbox.signals.tests import (
    _TEST_DETAIL_KEYS_FAIL,
    _TEST_DETAIL_KEYS_MISSING_INV,
    _TEST_DETAIL_KEYS_PASS,
    collect_test_signal,
)
from codegenie.types.identifiers import SignalKind


JEST_OK = (
    "PASS  src/auth.test.ts\n"
    "Tests:       42 passed, 42 total\n"
    "Test Suites: 7 passed, 7 total\n"
)
JEST_REMOVED = (
    "PASS  src/auth.test.ts\n"
    "Tests:       41 passed, 41 total\n"
    "Test Suites: 6 passed, 6 total\n"
)
JEST_ADDED = (
    "PASS  src/auth.test.ts\n"
    "Tests:       43 passed, 43 total\n"
    "Test Suites: 8 passed, 8 total\n"
)
JEST_FAIL = (
    "FAIL  src/auth.test.ts > jwt-validates\n"
    "Tests:       1 failed, 41 passed, 42 total\n"
    "Test Suites: 1 failed, 6 passed, 7 total\n"
)
VITEST_OK = (
    "✓ src/util.test.ts (10)\n"
    "Test Files  1 passed (1)\n"
    "     Tests  42 passed (42)\n"
)
MOCHA_OK = (
    "  AuthService\n"
    "    ✓ validates jwt\n\n"
    "  42 passing (3s)\n"
)


# ---- AC-API-1 / AC-INIT-2 / AC-NEWTYPE-1 ---------------------------

def test_registry_resolves_collect_test_signal():
    # WHY: package __init__.py must trigger registration; resolve via SignalKind
    assert (
        signal_collector_registry.get(SignalKind("tests"))
        is collect_test_signal
    )


# ---- AC-PASSED-TRUTH-1 — exhaustive 12-corner truth table ----------

TRUTH = [
    pytest.param(ec, delta, inv, id=f"ec={ec}_delta={delta}_inv={inv}")
    for ec in (0, 1)
    for delta in (-1, 0, 1)
    for inv in ("present", "missing")
]


@pytest.mark.parametrize("exit_code,delta,inv", TRUTH)
def test_passed_truth_table(_make_run, _write_pre_inventory, tmp_path, exit_code, delta, inv):
    # Build a stdout where total = pre + delta (pre=42; post=42+delta) — except
    # when inv=="missing", delta is forced to 0 by the collector (AC-INV-MISSING-1).
    pre_count = 42
    if inv == "present":
        inv_path = tmp_path / "pre.json"
        _write_pre_inventory(inv_path, test_count=pre_count)
        effective_delta = delta
    else:
        inv_path = tmp_path / "missing.json"  # never written
        effective_delta = 0

    post = pre_count + delta
    stdout = (
        f"Tests:       {post} passed, {post} total\n"
        f"Test Suites: 1 passed, 1 total\n"
    )
    run = _make_run(exit_code=exit_code, stdout=stdout)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)

    expected = exit_code == 0 and effective_delta >= 0
    assert sig.passed is expected
    assert sig.details["delta_test_count"] == effective_delta


# ---- AC-PROP-PASSED-1 — Hypothesis property over (pre, post, exit_code)

@given(
    pre=st.integers(min_value=0, max_value=10_000),
    post=st.integers(min_value=0, max_value=10_000),
    exit_code=st.integers(min_value=-1, max_value=255),
)
def test_passed_formula_hypothesis(_make_run, _write_pre_inventory, tmp_path, pre, post, exit_code):
    inv_path = tmp_path / f"pre_{pre}_{post}.json"
    _write_pre_inventory(inv_path, test_count=pre)
    stdout = (
        f"Tests:       {post} passed, {post} total\n"
        f"Test Suites: 1 passed, 1 total\n"
    )
    run = _make_run(exit_code=exit_code, stdout=stdout)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    delta = post - pre
    assert sig.details["delta_test_count"] == delta
    assert sig.passed is (exit_code == 0 and delta >= 0)


# ---- AC-FAILURES-NOT-FALSIFY-DELTA-1 — exit nonzero, all tests present

def test_failures_do_not_falsify_delta(_make_run, _write_pre_inventory, tmp_path):
    # WHY: ADR-0015 polices REMOVED tests, not FAILED tests. A patch where all
    # 42 tests still exist but newly fail must give delta=0 (post-count includes
    # failures), passed=False (exit_code says failure).
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    run = _make_run(exit_code=1, stdout=JEST_FAIL)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    assert sig.details["delta_test_count"] == 0
    assert sig.passed is False


# ---- AC-DELTA-NEGATIVE-FAIL-1 — exit 0 + delta < 0 still fails -----

def test_exit_zero_delta_negative_fails(_make_run, _write_pre_inventory, tmp_path):
    # WHY: adversarial vector ADR-0015 catches — LLM patch deletes test, npm
    # test exits 0 because the deleted test was the failing one.
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    run = _make_run(exit_code=0, stdout=JEST_REMOVED)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    assert sig.details["delta_test_count"] == -1
    assert sig.passed is False


# ---- AC-DELTA-POSITIVE-INFO-1 — exit 0 + delta > 0 passes ----------

def test_exit_zero_delta_positive_passes_informational(_make_run, _write_pre_inventory, tmp_path):
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    run = _make_run(exit_code=0, stdout=JEST_ADDED)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    assert sig.details["delta_test_count"] == 1
    assert sig.passed is True


# ---- AC-DETAILS-KEYS-1..3 — three catalogs match exactly -----------

def test_failure_path_details_keys_equal_fail_catalog(_make_run, _write_pre_inventory, tmp_path):
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    run = _make_run(exit_code=1, stdout=JEST_FAIL)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    assert sig.passed is False
    assert set(sig.details.keys()) == set(_TEST_DETAIL_KEYS_FAIL)


def test_success_path_details_keys_equal_pass_catalog(_make_run, _write_pre_inventory, tmp_path):
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    run = _make_run(exit_code=0, stdout=JEST_OK)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    assert sig.passed is True
    assert set(sig.details.keys()) == set(_TEST_DETAIL_KEYS_PASS)


def test_missing_inventory_details_keys_equal_missing_catalog(_make_run, tmp_path):
    run = _make_run(exit_code=0, stdout=JEST_OK)
    sig = collect_test_signal(run, pre_patch_inventory_path=tmp_path / "missing.json")
    assert set(sig.details.keys()) == set(_TEST_DETAIL_KEYS_MISSING_INV)
    assert sig.details["pre_patch_inventory_missing"] is True
    assert sig.details["delta_test_count"] == 0


# ---- AC-DETAILS-NOBAN-1 — none of the four banned substrings -------

@pytest.mark.parametrize("banned", ["confidence", "llm", "self_reported", "model_says"])
@pytest.mark.parametrize("catalog", [_TEST_DETAIL_KEYS_FAIL, _TEST_DETAIL_KEYS_PASS, _TEST_DETAIL_KEYS_MISSING_INV])
def test_detail_catalog_keys_contain_no_banned_substring(catalog, banned):
    assert not any(banned in k for k in catalog)


# ---- AC-DETAILS-TYPES-1 — bool vs int identity ---------------------

def test_failure_path_value_type_identity(_make_run, _write_pre_inventory, tmp_path):
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    run = _make_run(exit_code=1, stdout=JEST_FAIL)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    assert type(sig.details["delta_test_count"]) is int
    assert type(sig.details["first_failure"]) is str
    assert type(sig.details["failing_tests"]) is str
    assert type(sig.details["parser_format"]) is str
    assert type(sig.details["exit_code"]) is int
    assert type(sig.details["timed_out"]) is bool
    assert type(sig.details["killed_by_oom"]) is bool


def test_missing_inventory_value_type_identity(_make_run, tmp_path):
    run = _make_run(exit_code=0, stdout=JEST_OK)
    sig = collect_test_signal(run, pre_patch_inventory_path=tmp_path / "x.json")
    assert type(sig.details["pre_patch_inventory_missing"]) is bool
    assert type(sig.details["delta_test_count"]) is int


# ---- AC-FIRSTFAIL-SHAPE-1 / AC-FIRSTFAIL-EMPTY-1 / AC-FAILING-ORDER-1

def test_first_failure_is_test_name_not_log_line(_make_run, _write_pre_inventory, tmp_path):
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    run = _make_run(exit_code=1, stdout=JEST_FAIL)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    # Pinned positively: name only, no leading/trailing whitespace, no FAIL banner.
    assert sig.details["first_failure"] == "jwt-validates"


def test_first_failure_empty_when_exit_nonzero_but_no_failing_test_parsed(_make_run, _write_pre_inventory, tmp_path):
    # E.g. build failed before any test ran — exit_code !=0, parsed.failing == ()
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    run = _make_run(exit_code=1, stdout="build broke before tests started\n")
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    assert sig.details["first_failure"] == ""


def test_failing_tests_alphabetically_sorted_comma_space_joined(_make_run, _write_pre_inventory, tmp_path):
    # WHY: byte-stable serialization for AttemptSummary (S1-04 / Phase 9 replay).
    stdout = (
        "FAIL  src/c.test.ts > c-test\n"
        "FAIL  src/a.test.ts > a-test\n"
        "FAIL  src/b.test.ts > b-test\n"
        "Tests:       3 failed, 39 passed, 42 total\n"
        "Test Suites: 3 failed, 4 passed, 7 total\n"
    )
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    run = _make_run(exit_code=1, stdout=stdout)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    assert sig.details["failing_tests"] == "a-test, b-test, c-test"


# ---- AC-FAILING-TRUNC-1 / AC-FIRSTFAIL-TRUNC-1 ---------------------

def test_failing_tests_truncated_to_2048_utf8_bytes(_make_run, _write_pre_inventory, tmp_path):
    long_names = [f"test-name-with-deliberately-long-identifier-{i:06d}" for i in range(200)]
    stdout = "".join(
        f"FAIL  src/x{i}.test.ts > {long_names[i]}\n" for i in range(len(long_names))
    ) + f"Tests:       {len(long_names)} failed, 0 passed, {len(long_names)} total\n"
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=len(long_names))
    run = _make_run(exit_code=1, stdout=stdout)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    assert len(sig.details["failing_tests"].encode("utf-8")) <= 2048
    if len(sig.details["failing_tests"]) > 0:
        # Truncation marker on the tail (AC-FAILING-TRUNC-1).
        assert sig.details["failing_tests"].endswith("…")


def test_first_failure_truncated_to_256_utf8_bytes(_make_run, _write_pre_inventory, tmp_path):
    long = "x" * 1000
    stdout = (
        f"FAIL  src/a.test.ts > {long}\n"
        "Tests:       1 failed, 0 passed, 1 total\n"
    )
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=1)
    run = _make_run(exit_code=1, stdout=stdout)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    assert len(sig.details["first_failure"].encode("utf-8")) <= 256
    # Byte-safe — no partial multibyte at the tail.
    assert sig.details["first_failure"].encode("utf-8").decode("utf-8") == sig.details["first_failure"]


# ---- AC-PROV-* — provenance value pinning --------------------------

def test_provenance_values_pinned(_make_run, _write_pre_inventory, tmp_path):
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    run = _make_run(exit_code=0, stdout=JEST_OK)
    sig = collect_test_signal(run, pre_patch_inventory_path=inv_path)
    assert sig.provenance.signal_kind == SignalKind("tests")
    assert sig.provenance.collector_module == "codegenie.sandbox.signals.tests"
    assert sig.provenance.collector_version == "1"


# ---- AC-DETERMINISM-1 — distinct instances, content-determinism ----

def test_inputs_blake3_content_deterministic_across_distinct_instances(_make_run, _write_pre_inventory, tmp_path):
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    a = collect_test_signal(_make_run(exit_code=0, stdout=JEST_OK), pre_patch_inventory_path=inv_path)
    b = collect_test_signal(_make_run(exit_code=0, stdout=JEST_OK), pre_patch_inventory_path=inv_path)
    assert a.provenance.inputs_blake3 == b.provenance.inputs_blake3
    assert re.fullmatch(r"blake3:[0-9a-f]{64}", a.provenance.inputs_blake3)


# ---- AC-AT-TZ-1 — at is UTC ----------------------------------------

def test_at_is_timezone_aware_utc(_make_run, _write_pre_inventory, tmp_path):
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    sig = collect_test_signal(_make_run(exit_code=0, stdout=JEST_OK), pre_patch_inventory_path=inv_path)
    assert sig.at.tzinfo is not None
    assert sig.at.tzinfo.utcoffset(sig.at).total_seconds() == 0


# ---- AC-PARSER-PARITY-1 — three formats, one parametrize layer -----

PARSER_FIXTURES = [
    pytest.param("jest", JEST_OK, 42, (), "", id="jest-ok"),
    pytest.param("jest", JEST_FAIL, 42, ("jwt-validates",), "jwt-validates", id="jest-fail"),
    pytest.param("vitest", VITEST_OK, 42, (), "", id="vitest-ok"),
    pytest.param("mocha", MOCHA_OK, 42, (), "", id="mocha-ok"),
]


@pytest.mark.parametrize("format_name,sample_log,expected_total,expected_failing,expected_first", PARSER_FIXTURES)
def test_parser_format_parity(_make_run, _write_pre_inventory, tmp_path, format_name, sample_log, expected_total, expected_failing, expected_first):
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=expected_total)
    sig = collect_test_signal(_make_run(exit_code=(0 if not expected_failing else 1), stdout=sample_log), pre_patch_inventory_path=inv_path)
    assert sig.details["parser_format"] == format_name
    expected_failing_str = ", ".join(sorted(expected_failing))
    assert sig.details["failing_tests"] == expected_failing_str
    assert sig.details["first_failure"] == expected_first


# ---- AC-PARSER-UNKNOWN-1 — falls back safely ------------------------

def test_unknown_format_falls_back_safely(_make_run, _write_pre_inventory, tmp_path):
    inv_path = tmp_path / "pre.json"
    _write_pre_inventory(inv_path, test_count=42)
    sig = collect_test_signal(_make_run(exit_code=0, stdout="nothing here\n"), pre_patch_inventory_path=inv_path)
    assert sig.details["parser_format"] == "unknown"
    # AC-PARSER-UNKNOWN-1 — unparseable log + known pre-inventory => delta = -pre
    assert sig.details["delta_test_count"] == -42
    assert sig.passed is False


# ---- AC-INV-CORRUPT-1 / AC-INV-SCHEMA-2 -----------------------------

def test_corrupt_inventory_treated_as_missing(_make_run, tmp_path):
    inv_path = tmp_path / "corrupt.json"
    inv_path.write_text("{not json at all")
    sig = collect_test_signal(_make_run(exit_code=0, stdout=JEST_OK), pre_patch_inventory_path=inv_path)
    assert sig.details["pre_patch_inventory_missing"] is True
    assert sig.details["delta_test_count"] == 0


def test_inventory_with_extra_field_treated_as_missing(_make_run, tmp_path):
    inv_path = tmp_path / "extra.json"
    inv_path.write_text(json.dumps({"test_count": 42, "test_names": [], "captured_at": "2026-05-12T00:00:00+00:00", "smuggled": "yes"}))
    sig = collect_test_signal(_make_run(exit_code=0, stdout=JEST_OK), pre_patch_inventory_path=inv_path)
    # extra=forbid + read returns None on ValidationError => missing-inv path.
    assert sig.details["pre_patch_inventory_missing"] is True


def test_inventory_with_naive_captured_at_treated_as_missing(_make_run, tmp_path):
    inv_path = tmp_path / "naive.json"
    inv_path.write_text(json.dumps({"test_count": 42, "test_names": [], "captured_at": "2026-05-12T00:00:00"}))
    sig = collect_test_signal(_make_run(exit_code=0, stdout=JEST_OK), pre_patch_inventory_path=inv_path)
    assert sig.details["pre_patch_inventory_missing"] is True


# ---- AC-ADVERSARIAL-1 / AC-INFORMATIONAL-1 — integration ------------

def test_adversarial_removed_test_fixture():
    # tests/fixtures/repos/test-removes-test/  must exist & match AC-ADVERSARIAL-1.
    fixture = Path("tests/fixtures/repos/test-removes-test")
    if not fixture.exists():  # pragma: no cover — fixture is part of Files to touch
        pytest.skip("fixture not landed yet")
    # The integration body that loads pre_inventory.json + sandbox_run/logs/stdout.log
    # and asserts passed=False, delta_test_count=-1, parser_format='jest' belongs to
    # tests/integration/sandbox/test_test_signal_adversarial.py — see Files to touch.
```

#### Structural fence + Pydantic-schema tests

`tests/sandbox/test_signals_purity.py` — **extends** the S4-01 file
with AST assertions over `tests.py`, `_test_parser.py`,
`_test_inventory.py`: no `blake3`, no `hashlib.sha256`, no
`subprocess`, no `requests` / `urllib.request`, no `os.system`.
Module docstrings cite the three Phase-5 ADRs + ADR-0001 + S4-02.

`tests/sandbox/test_pre_inventory_schema.py` — focused suite for
`_PrePatchInventory`: `extra="forbid"`, `frozen=True`, `strict=True`;
naive `captured_at` rejected; negative `test_count` rejected;
missing-field rejected; wrong-type rejected; `set(model_fields.keys())
== {"test_count", "test_names", "captured_at"}`.

`tests/sandbox/test_signal_collector_registry.py` — **appends** (do
NOT create new) AC-NEWTYPE-1 / AC-INIT-2 assertions for `"tests"`.

`tests/integration/sandbox/test_test_signal_adversarial.py` — the
two fixture-backed integration tests (AC-ADVERSARIAL-1, AC-ADVERSARIAL-2,
AC-INFORMATIONAL-1).

### Green — make it pass

- Land `_test_parser.py` first (with `_FORMAT_PARSERS`) — unit-test
  parser invariants in isolation against the golden log fixtures.
- Land `_test_inventory.py` next — Pydantic schema unit tests in
  isolation.
- Land `tests.py` + `__init__.py` together (registration side-effect
  must be atomic with the collector).
- Verify the parametrized suite passes on all three formats before
  declaring green.

### Refactor — clean up

- Verify `collect_test_signal` is ≤ 60 LOC excluding parser /
  inventory-reader (AC-API-1).
- Verify `_FORMAT_PARSERS` order is `(jest, vitest, mocha)` —
  precedence is documented in the module docstring.
- Do **NOT** invent a `_collect_with_kwargs(...)` Strategy helper —
  this is the FIRST extra-kwarg collector (S4-03 trace/policy/cve_delta
  also take extra kwargs but each takes a DIFFERENT kwarg). The
  Strategy helper for S4-03 collectors (if any emerges) lives in
  S4-03, not S4-02.

## Files to touch

| Path | Action | Why |
|---|---|---|
| `src/codegenie/sandbox/signals/tests.py` | create | The `collect_test_signal` collector. Mints provenance via S4-01 `_common.build_provenance`. |
| `src/codegenie/sandbox/signals/_test_parser.py` | create | jest / vitest / mocha output parser with `_FORMAT_PARSERS` Strategy registry. |
| `src/codegenie/sandbox/signals/_test_inventory.py` | create | `_PrePatchInventory` Pydantic model + `read_pre_inventory` failure-tolerant reader. |
| `src/codegenie/sandbox/signals/__init__.py` | modify | Append `tests` to the `from . import build, install` line from S4-01. Alphabetized: `from . import build, install, tests`. |
| `tests/sandbox/conftest.py` | modify | Add `_write_pre_inventory` fixture (extends S4-01's `_make_run`). |
| `tests/sandbox/test_signals_tests.py` | create | Truth-table, property, parser-format-parity, details-catalog, provenance-pinning, AT-TZ. |
| `tests/sandbox/test_signals_purity.py` | modify (extend) | AST scans over new `tests.py` / `_test_parser.py` / `_test_inventory.py`. |
| `tests/sandbox/test_signal_collector_registry.py` | modify (append) | AC-NEWTYPE-1 / AC-INIT-2 assertions for `"tests"`. |
| `tests/sandbox/test_pre_inventory_schema.py` | create | Focused `_PrePatchInventory` Pydantic-validation suite. |
| `tests/integration/sandbox/test_test_signal_adversarial.py` | create | Fixture-backed integration: AC-ADVERSARIAL-1, AC-ADVERSARIAL-2, AC-INFORMATIONAL-1. |
| `tests/fixtures/repos/test-removes-test/pre_inventory.json` | create | Adversarial fixture (delta = −1). |
| `tests/fixtures/repos/test-removes-test/sandbox_run/logs/stdout.log` | create | Captured `npm test` output post-removal. |
| `tests/fixtures/repos/test-adds-regression/pre_inventory.json` | create | Informational fixture (delta = +1). |
| `tests/fixtures/repos/test-adds-regression/sandbox_run/logs/stdout.log` | create | Captured `npm test` output post-add. |
| `tests/fixtures/test_runner_logs/jest/{ok,removed,added,failed}.log` | create | Per-format goldens for parser parity tests. |
| `tests/fixtures/test_runner_logs/vitest/{ok,failed}.log` | create | Vitest goldens. |
| `tests/fixtures/test_runner_logs/mocha/{ok,failed}.log` | create | Mocha goldens. |

## Out of scope

- `failed_unrecoverable` 3× detection — `GateRunner`'s job (S5-02),
  not the collector's.
- The `tests/adversarial/test_patch_disables_test.py` E2E test
  driving the full `codegenie remediate` loop — consolidated into
  S7-01; this story only proves the collector's delta math + the
  parser-format coverage + provenance discipline.
- Trace, policy, cve_delta collectors — S4-03.
- `StrictAndGate` adapter (the runner-side consumer) — S4-05.
- `pre_patch_inventory_path` derivation from `GateContext.workflow_id`
  / `ctx.run_id` — S4-05 / S5-02 (runner). This story takes the path
  as a kwarg.
- Phase 3 pre-patch inventory snapshot production — Phase 3's job to
  produce the JSON file at the agreed path. S4-02 only consumes it.
- Phase 7.5 `pytest` parser row in `_FORMAT_PARSERS` — Phase 7.5's
  job (one row added; no edit to `parse_test_results` per AC-PARSER-REGISTRY-1).
- Audit-event emission on `pre_patch_inventory_missing` /
  `pre_patch_inventory_corrupt` — S5-02 `GateRunner` (which has
  access to the structured logger context).

## Notes for the implementer

1. **`details` value-types are strict primitives only.** ADR-0014 +
   S1-03 AC-5 — `dict[str, str | int | bool]`. For S4-02 the values
   are: `delta_test_count: int`, `exit_code: int`, `timed_out: bool`,
   `killed_by_oom: bool`, `parser_format: str`, `first_failure: str`,
   `failing_tests: str`, `pre_patch_inventory_missing: bool`. The
   "convert lists to comma-joined strings" guidance applies to
   `failing_tests` specifically — DO NOT emit `list[str]` (Pydantic
   strict mode rejects).

2. **Hashing chokepoint (ADR-0001) — `tests.py` MUST NOT import
   `blake3` directly.** Provenance is built via S4-01's
   `_common.build_provenance(...)` which itself delegates to
   `codegenie.hashing.content_hash_bytes`. AST scan in
   `tests/sandbox/test_signals_purity.py` enforces this.

3. **Decorator delegation to Phase 3 — `"tests"` is pre-registered.**
   Per S1-05 HARDENED #1 + AC-COL-4, Phase 5's
   `@register_signal_kind("tests")` detects that `"tests"` is already
   in Phase 3's `signal_kind_registry` (registered at module-import
   by `TESTS = register_signal_kind("tests")` per
   [`src/codegenie/transforms/signal_kinds.py:156`](../../../../src/codegenie/transforms/signal_kinds.py))
   and skips the Phase 3 `register_signal_kind` call to avoid
   `SignalKindAlreadyRegistered`. AC-REG-IDEMPOTENT-1 catches a
   regression.

4. **Registration side-effect — `__init__.py` MUST import the
   `tests` module.** The decorator runs at module-import time; if
   the package's `__init__.py` never imports `tests`,
   `signal_collector_registry` lacks the entry when `StrictAndGate`
   (S4-05) tries to resolve it.

5. **`pre_patch_inventory_path` source is the RUNNER's concern.**
   `GateContext` (per phase-arch §Data model) does NOT carry a
   path field. The runner (S4-05 `StrictAndGate` or S5-02
   `GateRunner`) constructs the path from `ctx.workflow_id` /
   `ctx.run_id` per a path convention pinned by Phase 3 — out of
   scope for S4-02. The collector takes the path as an opaque kwarg.

6. **Forward seam — Phase 7.5 `pytest` parser.** When Phase 7.5
   lands the Python parser, the addition is ONE row in
   `_FORMAT_PARSERS` (with `name="pytest"`, the pytest summary regex,
   the failing-test-name pattern) PLUS ONE parametrize row in
   `test_parser_format_parity` PLUS ONE new entry in the
   `parser_format` Literal. `parse_test_results` itself does NOT
   change. The `Literal["jest","vitest","mocha","unknown"]` widens
   to `Literal["jest","vitest","mocha","pytest","unknown"]` —
   per `Open/Closed`, the widening is additive on a closed set; the
   ADR amendment is one line.

7. **Strategy-helper extraction deferred.** S4-02 is the FIRST
   extra-kwarg collector. S4-03 collectors (trace, policy,
   cve_delta) all take DIFFERENT extra kwargs — they do NOT share
   the `(run, pre_patch_inventory_path)` shape. The rule-of-three
   trigger for an `_collect_with_inventory(...)` Strategy helper
   never fires. Two near-identical files for similar collectors are
   cleaner than a premature abstraction (Rule 2; CLAUDE.md "three
   similar lines is better than premature abstraction").

8. **`datetime.now(timezone.utc)` — NOT `datetime.now(UTC)` alias.**
   Codebase convention (Rule 11). Use S4-01's `_common.utc_now()`
   exclusively.

9. **`delta_test_count` is ALWAYS in `details`.** ADR-0015 invariant.
   Zero, positive, or negative — never `None`, never missing. The
   three `_TEST_DETAIL_KEYS_*` catalogs include `delta_test_count`
   in every set; the implementation must too.

10. **The collector NEVER raises on collector-specific failures.**
    Per arch §Failure behavior. Missing-inventory, corrupt-inventory,
    permission-denied, unknown-parser-format — all annotate via
    `details`; never raise. `read_pre_inventory` returns `None`;
    `parse_test_results` returns `_ParsedTests(format="unknown",
    total_count=0, failing=(), first_failure="")`. The collector
    composes the two and returns a `TestSignal`. The only path that
    raises is `TestSignal` Pydantic construction failure — a
    programming error.

11. **Don't try to compute `delta_test_count` from log diff.** Use
    the pre-patch inventory JSON snapshot. Anything else lets the
    LLM influence the count.

12. **Run `tests/schema/test_objective_signals_static.py` locally
    before pushing.** A new banned substring fails the gate CI for
    the whole repo. This story does NOT modify `ObjectiveSignals` so
    the fence should pass trivially — but AC-DETAILS-NOBAN-1 is the
    in-story defence-in-depth on the three catalog values
    themselves.
