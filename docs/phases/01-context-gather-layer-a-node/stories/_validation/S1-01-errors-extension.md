# Validation report — S1-01 Errors extension

**Story:** [S1-01-errors-extension.md](../S1-01-errors-extension.md)
**Validated:** 2026-05-13
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story's goal — six new typed exception subclasses for Phase 1's parsers and catalog loader — is sound and traces cleanly to arch design (§"Agentic best practices" → "Error escalation", §"Edge cases" rows 1/2/3/9) and ADR-0007. The implementation pattern proposed in the draft, however, violated three independent load-bearing Phase 0 test contracts. Three parallel critics found seven block-tier and seven harden-tier issues; the synthesizer reconciled them by switching the design pattern from custom-`__init__` to bare markers (consistent with the existing 11 Phase 0 subclasses) and tightened every AC and TDD test to mutation-resistance.

No `NEEDS RESEARCH` findings; Stage 3 was skipped (token economy).

## Context Brief (Stage 1)

- **Goal as written:** Extend `errors.py` with six new `CodegenieError` subclasses carrying `path` + violated cap or `detail` as instance attributes.
- **Phase exit criteria touched:** Arch §Goals #6 (hard caps in every parser → typed exception → `ProbeOutput(confidence="low", errors=[...])`), Arch §Goals #4 (probe-contract conformance — Phase 0 §2.3 snapshot unchanged), Arch §Edge cases rows 1/2/3/9.
- **Phase 0 contract (load-bearing):** `src/codegenie/errors.py` module docstring asserts *"Subclasses carry no `__init__`, no `__str__`, no class attributes — they are markers only."* Pinned by `tests/unit/test_errors.py::test_subclasses_are_markers_only` (`cls.__init__ is e.CodegenieError.__init__`).
- **Phase 0 inventory observed:** `errors.__all__` contains **eleven** subclasses (the story's draft Context section claimed nine — stale by `ProbeBudgetExceeded` and `AllProbesFailedError`).
- **ADR-0007 contract:** WarningId pattern lives at the **catch site** (the probe), not on the exception class.

## Stage 2 — critic reports

### Coverage (verdict: COVERAGE-HARDEN)

- **F1 (harden)** — Raise-site contract is not pinned by any AC; story doesn't capture which exception maps to which failure (arch §Edge cases #1, #2, #3, #9).
- **F2 (block)** — `MalformedYAMLError` and `MalformedLockfileError` have no attribute-shape assertion; a `pass`-bodied class would pass all draft ACs.
- **F3 (harden)** — `str(exc)` message format (`f"{path}: cap={cap}"`) prescribed in implementation outline but unlocked in any AC.
- **F4 (harden)** — AC-3 (SymlinkRefusedError) asserts behavior the story cannot observe from its scope alone.
- **F5 (harden)** — Edge case #9 (`CatalogLoadError` hard-fail at CLI startup) is not distinguished from soft-fail siblings.
- **F6 (nit)** — ADR-0007 says exceptions don't embed WarningIds; no negative assertion guards against accidental addition.
- **F7 (nit)** — EXPECTED_SUBCLASSES set doesn't prove `issubclass(_, CodegenieError)`.

### Test quality (verdict: TESTS-BLOCK)

Mutation analysis (8 plausible wrong implementations):

| # | Wrong implementation | Caught by draft TDD plan? | Severity |
|---|---|---|---|
| 1 | Aliasing collapse `SizeCapExceeded = CodegenieError` | No (incidentally caught only if CodegenieError rejects kwargs) | harden |
| 2 | `cap` stored as `float` (e.g., `64.0`) | No (`==` is true for float-vs-int) | harden |
| 3 | Non-keyword-only `__init__(self, path, cap)` | No (story's Red test calls keyword-only) | block |
| 4 | Missing `self.path` on `DepthCapExceeded` | No (only `dc.cap` asserted) | block |
| 5 | `MalformedYAMLError`/`MalformedLockfileError` as `pass` | No (never constructed) | block |
| 6 | `MalformedJSONError.detail = None` | No (only path checked) | harden |
| 7 | Drop `path` substring from `str(exc)` for malformed types | No (asserted only for SizeCapExceeded) | harden |
| 8 | EXPECTED_SUBCLASSES desync (9 vs 11) | N/A — itself a stale baseline | block |

Plus: `test_symlink_refused_is_phase0_type_unchanged` is a tautology; AC-5 has no test; intent-vs-behavior gap (test claims to verify "recoverable from caught exception" but never `pytest.raises`).

### Consistency (verdict: CONSISTENCY-BLOCK)

- **F1 (block)** — Custom `__init__` violates Phase 0 `test_subclasses_are_markers_only` (`cls.__init__ is e.CodegenieError.__init__` + `cls.__dict__` allowlist).
- **F2 (block)** — `EXPECTED_SUBCLASSES` cardinality wrong: 9 in story vs 11 in Phase 0 `__all__`.
- **F3 (block)** — New docstrings won't satisfy `test_every_subclass_has_raise_site_docstring` (slug allowlist excludes `parsers`, `catalogs`).
- **F4 (harden)** — ADR-0008 citation misattributed (that ADR governs the sanitizer, not `errors.py`).
- **F5 (harden)** — Collapses into F1.
- **F6 (nit)** — `SymlinkRefusedError` docstring scope extension is an S1-02 concern.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap is answerable from arch + ADR-0007 + the existing Phase 0 test contract.

## Stage 4 — Synthesizer resolution

### Conflict resolution

Coverage F1/F2/F3 demanded richer attribute coverage (path, cap, detail accessible via instance). Consistency F1 said this directly violates Phase 0's marker-only invariant. **Consistency wins** (per skill rule: arch + Phase 0 contract is source of truth). The synthesizer chose:

- Keep new subclasses as **markers** (no `__init__`, no class attrs) — preserves Phase 0 invariant for all 17 subclasses uniformly.
- Encode path / cap / detail in the **formatted message string** the raise site passes positionally to `CodegenieError.__init__` (inherits `Exception.__init__` → `.args[0]`).
- Document that `WarningId` semantics are recovered at the **catch site** by the calling probe (matches arch §Error escalation: *"each is caught by the calling probe into `ProbeOutput.errors` with a structured WarningId"*).

This satisfies the goal ("not ad-hoc string exceptions") by providing six **typed** marker classes the raise sites can use, and avoids the Phase 0 contract collision.

### Edits applied to the story

| Section | Before | After |
|---|---|---|
| Header — ADRs honored | `ADR-0007, ADR-0008 (Phase 0 chokepoint preservation)` | `ADR-0007` (ADR-0008 misattribution dropped per Consistency F4) |
| Status | `Ready` | `Ready (hardened by phase-story-validator)` |
| New "Validation notes" block | absent | added — summarizes the four structural changes |
| Context — Phase 0 count | "nine subclasses" | "**eleven** subclasses" (Consistency F2) |
| Goal | "subclasses that carry a violated-cap path and a typed-id" via `__init__` | "six new **marker** subclasses … raise sites construct with formatted message …; subclasses inherit `CodegenieError.__init__` (markers-only invariant preserved)" |
| Acceptance criteria | 7 ACs, several vague | 10 ACs (AC-1…AC-10) — each individually verifiable; explicitly pins markers-only invariant (AC-2), 17-name closure (AC-3), DOCUMENTED_MODULE_SLUGS additive extension (AC-4), raise-site docstrings (AC-5), `args[0]` round-trip + negative attribute checks (AC-6), root unchanged (AC-7), class-identity preservation (AC-8), red-commit evidence (AC-9), toolchain (AC-10) |
| Implementation outline | Each subclass with keyword-only `__init__` storing typed attrs + `super().__init__(formatted_message)` | Each subclass is a bare marker — one-line docstring only; raise sites format the message; module docstring gets a one-line note about Phase 1 markers |
| TDD plan — Red | Constructed 4 of 6 types; asserted custom-attr roundtrip | Parametrized over **all six** new types; asserts `args[0]` round-trip + `hasattr(exc, X) is False` for `{path, cap, detail, warning_id}` (negative-state mutation guard); caught-recovery test via `pytest.raises`; class-identity preservation test; CatalogLoadError hard-fail docstring test; root-unchanged test |
| TDD plan — Green | Custom `__init__` per subclass | Bare marker bodies (docstring only); each docstring names its slug (`parsers` / `catalogs`) and the raise site |
| TDD plan — Refactor | Custom message formatting in `super().__init__` | Confirm `cls.__dict__` keys stay inside `MARKER_ALLOWED_DICT_KEYS`; module-docstring note |
| Out of scope | (existing four items) | + "Carrying machine-readable path/cap/detail as instance attributes" + "Verifying the safe_json.load / safe_yaml.load raise behavior" (S1-02/S1-03 owns it) |
| Notes for implementer | "Keyword-only `__init__`…" | "Markers only. No `__init__`. Path/cap/detail in the message string …" + DOCUMENTED_MODULE_SLUGS guidance + WarningId-at-catch-site reminder |

### Mutation-resistance crosswalk

After edits, the eight mutations from the test-quality critic are now caught:

| # | Wrong implementation | Caught by hardened TDD? |
|---|---|---|
| 1 | Aliasing collapse | Yes — `test_phase1_subclasses_inherit_codegenie_error_directly` asserts `cls.__mro__[1] is e.CodegenieError` (Phase 0 test already in place, now applied to all 17). |
| 2 | `cap` as float — n/a — no longer stored | Mutation no longer applicable (markers). |
| 3 | Non-keyword-only `__init__` — n/a — no `__init__` | Mutation no longer applicable. |
| 4 | Missing `self.path` — n/a — no instance attrs | Mutation no longer applicable; `hasattr(exc, "path") is False` is asserted. |
| 5 | `MalformedYAMLError`/`MalformedLockfileError` as bare `pass` | **Yes** — every Phase-1 marker is parametrized; even bare-`pass` would fail `test_phase1_subclasses_accept_message_arg_and_expose_args0` if `__doc__` is missing (caught by `test_every_subclass_has_raise_site_docstring`); slug requirement also enforces docstring content. |
| 6 | `MalformedJSONError.detail = None` — n/a — no `.detail` | Mutation no longer applicable. |
| 7 | `str(exc)` drops path — n/a — `str()` delegates to `args[0]` | Mutation no longer applicable; AC-6 asserts `str(exc) == msg` for the round-tripped message. |
| 8 | EXPECTED_SUBCLASSES desync | Yes — set explicitly enumerates all **17** names; `test_all_closure_pins_public_surface` catches any drift. |

Additional positive-attribute coverage:

- `test_caught_phase1_exception_recovers_via_args0` — catches via `pytest.raises(CodegenieError)`; asserts message round-trips through the actual catch path (Rule 9: intent encoded — "the message is recoverable from the caught instance").
- `test_symlink_refused_class_identity_preserved` — asserts `errors.SymlinkRefusedError is errors.__dict__["SymlinkRefusedError"]` (guards against accidental re-import shadow).
- `test_catalog_load_error_doc_marks_hard_fail` — pins arch §Edge cases row 9 invariant in the docstring (load-bearing distinguishment from soft-fail siblings).

### Edge-case coverage crosswalk

| Arch edge case | Hardened story AC |
|---|---|
| #1 — billion-laughs in pnpm-lock.yaml → `DepthCapExceeded` | AC-1 (type exists) + AC-5 (docstring names parsers + depth walker) |
| #2 — 600 MB string in package.json → `SizeCapExceeded` | AC-1 + AC-5 |
| #3 — symlink package.json → `SymlinkRefusedError` (Phase 0) | AC-8 (class identity preserved); raise-site validation deferred to S1-02 |
| #9 — catalog YAML malformed → `CatalogLoadError` hard-fail | AC-5 + dedicated `test_catalog_load_error_doc_marks_hard_fail` |

## Verdict & rationale

**HARDENED.** Story now ready for the executor. Goal preserved; ACs individually verifiable; TDD plan mutation-resistant against eight named mutations; full consistency with Phase 0's markers-only invariant, the 11-name closure, and the docstring slug contract. No structural goal-vs-arch conflict requiring `phase-story-writer` re-run.

## Open questions / follow-ups for downstream stories

- **S1-02 / S1-03 / S1-04** must extend the `SymlinkRefusedError` docstring (Phase 0) to mention the parser walker if the raise site broadens. The validator flagged this as an S1-02 concern (Consistency F6 → out of scope here, must be carried forward).
- **Future structured-state need:** If any later phase needs introspectable `path` / `cap` attributes on these exceptions (e.g., for retry logic that branches on cap-vs-detail), it must amend the Phase 0 markers-only invariant via a dedicated ADR that re-shapes **all 17** subclasses uniformly — not an asymmetric Phase 1 carve-out.

## Sources cited by critics

- `tests/unit/test_errors.py` (Phase 0 S2-01)
- `src/codegenie/errors.py` (Phase 0 source)
- `docs/phases/01-context-gather-layer-a-node/phase-arch-design.md` §"Agentic best practices" line ~825, §"Edge cases" line ~830
- `docs/phases/01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md`
- `docs/phases/01-context-gather-layer-a-node/final-design.md` §"Failure modes & recovery" line ~340
- `docs/phases/00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md` (cited by story; misattribution flagged)
- `CLAUDE.md` "Extension by addition" commitment
