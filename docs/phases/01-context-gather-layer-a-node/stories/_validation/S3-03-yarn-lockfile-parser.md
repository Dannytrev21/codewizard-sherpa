# Validation report — S3-03 `_yarn` lockfile parser + ADR-0003 finalization

**Story:** [S3-03-yarn-lockfile-parser.md](../S3-03-yarn-lockfile-parser.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The goal — implement `src/codegenie/probes/_lockfiles/_yarn.py` with `_HAS_PYARN` dispatch (pyarn if available at runtime, else hand-rolled state machine) and finalize ADR-0003's "Implementer's land-time selection" block — is well-formed and traces cleanly to arch §"Component design" #9, ADR-0003, ADR-0007, ADR-0008, ADR-0009, and CLAUDE.md "Extension by addition." The draft, however, inherited the same marker-construction defect S1-02 / S1-03 / S3-01 / S3-02 all carried, *and* introduced a second class of defect that is arguably more severe for this story specifically: it reimplemented the shared `O_NOFOLLOW` + `os.fstat` size-cap kernel in-module instead of calling `parsers/_io.open_capped` (which exists for exactly this case, registry pattern and all).

**Four block-level corrections** applied:

1. **Marker exception construction must be positional.** Draft prescribed `MalformedLockfileError(path=path, cause=e)` (kwargs) and test asserted `exc.value.path == lockfile`. Phase 0 invariant + S1-01's `test_phase1_subclasses_accept_message_arg_and_expose_args0` parametrize **every** Phase 1 marker as positional-only — `hasattr(exc, "path")` is an asserted negative. Construction must be `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause`. Same defect S1-02 / S1-03 / S3-01 / S3-02 hardenings already corrected.

2. **Use the shared `open_capped` kernel.** Draft prescribed an in-module `_open_with_size_check(path, max_bytes)` reimplementing `O_NOFOLLOW` open + `os.fstat` size check from scratch — including raw `e.errno in (40, 62)` instead of `errno.ELOOP`. That kernel **already exists** at `src/codegenie/parsers/_io.open_capped` with the registry-pattern hook (`parser_kind: str` discriminator). Its docstring names exactly this case: "adding a future `safe_toml` is a new caller of this primitive with a new `parser_kind` literal — zero edits here." Reimplementing it (a) duplicates load-bearing security code, (b) defeats the structured `probe.parser.cap_exceeded` event's `parser_kind` discriminator, and (c) violates CLAUDE.md "Extension by addition." Hardened story calls `open_capped(path, max_bytes=YARN_LOCKFILE_MAX_BYTES, parser_kind="yarn_lockfile")` — the third caller of the kernel, validating the registry-pattern claim from `_io.py`'s docstring.

3. **No edit to `_lockfiles/__init__.py`.** Draft Implementation-outline step 8 prescribed "Update `src/codegenie/probes/_lockfiles/__init__.py` with the `YarnLock` re-export (additive)." That contradicts S3-01's settled inert form (`__all__: list[str] = []`) and S3-02's AC-1 + `test_lockfiles_init_remains_inert`. Consumers import siblings directly. S3-03 inherits and adds **two** new files only: `_yarn.py` and the throwaway fuzz script under `tools/`. The hardened story drops the re-export step, pins the non-edit as AC-1, and re-asserts S3-02's architectural test on S3-03's branch.

4. **Rule-of-three resolution — defer extraction with recorded rationale.** S3-01 and S3-02 explicitly punted the shared `_translate(path, *, cause)` helper to S3-03's land time. The draft was silent. Hardened story resolves: **DEFER** with explicit rationale. Yarn's dispatch is structurally different from pnpm/npm — it catches `(SizeCapExceeded, SymlinkRefusedError)` to passthrough plus `Exception` to translate (the hand-rolled scanner raises `ValueError` / `UnicodeDecodeError`; `pyarn` may raise its own classes), and the pre-parse step is `open_capped(...)` rather than `safe_yaml.load(...)` / `safe_json.load(...)`. The trio is two-of-a-kind (pnpm/npm) plus one-of-a-kind (yarn); extracting `_translate` would either (a) widen the helper to swallow `Exception` (loosening pnpm/npm's narrow catches), or (b) require two helpers, defeating the abstraction. CLAUDE.md Rule 2 dominates: "three similar lines is better than premature abstraction." Documented in Notes for the implementer §7; no helper extracted here. Phase 2 may revisit if `bun.lockb` reveals the right shape.

**Fourteen harden-tier additions** mirror S3-01 / S3-02's hardened shape with yarn-specific deltas:

1. Explicit AC for the `__cause__` chain (`exc.value.__cause__ is not None`; `type(cause).__name__` surfaces in `exc.args[0]`).
2. Explicit AC for `str(path) in exc.args[0]` (downstream `WarningId` recovery per ADR-0007).
3. Parametrized markers-only-negative test pinning `not hasattr(exc, "path" | "cap" | "detail" | "cause" | "warning_id")`.
4. Size-cap test rewritten to monkey-patch `os.fstat`, avoiding the 60 MB tmpfs write the draft prescribed (Rule 2 — smallest test that proves the contract; mirrors S3-01/S3-02 precedents).
5. Symlink-passthrough test added (`SymlinkRefusedError` re-raise from `open_capped`).
6. Both dispatch paths (`_HAS_PYARN=True`, `_HAS_PYARN=False`) tested via `monkeypatch.setattr(_yarn, "_HAS_PYARN", ...)`; the malformed-bytes test runs only on the hand-rolled path (forced via monkeypatch) so the assertion is deterministic regardless of `pyarn`'s local install state.
7. `_HAS_PYARN` semantics pinned: `_HAS_PYARN == (importlib.util.find_spec("pyarn") is not None)`; tested with two `find_spec` monkey-patches + `importlib.reload`.
8. `YarnLock` / `YarnLockEntry` declared `total=False`; module exports `__all__ = ["YarnLock", "YarnLockEntry", "parse"]`.
9. Module constants typed `Final[int]`; `_PARSER_KIND: Final[str] = "yarn_lockfile"` declared.
10. Architectural test `test_yarn_module_does_not_reference_sibling_parsers` pinning CLAUDE.md "Extension by addition."
11. Architectural test `test_lockfiles_init_remains_inert` re-asserted at S3-03 land — S3-03 must not touch the family-`__init__`.
12. `parser_kind="yarn_lockfile"` literal pinned at module scope and asserted in a `structlog`-capture test (`probe.parser.cap_exceeded` event surfaces this discriminator — the registry pattern's payoff).
13. `pyarn` API surface verified at land-time (AC-13): the implementer must confirm the actual `pyarn` API call and adjust dispatch accordingly; the Green-code `_pyarn_parse` sketches the most-likely shape (`pyarn.lockfile.Lockfile.from_string(body.decode("utf-8"))`) and the ADR records the verified shape.
14. Local-fuzz AC tightened (AC-16): script lives at `tools/fuzz_yarn_lock.py` (committed throwaway, not pytest-collected); PR body pastes the summary line.

**Test-implementation deltas vs. draft:**

- **Strict UTF-8 decode** (AC-7 + Notes §4). Draft Green code used `errors="replace"`. Hardened version drops the `errors=` kwarg — invalid UTF-8 surfaces as `UnicodeDecodeError`, translated cleanly to `MalformedLockfileError`. Rule 12: fail loud. A new test (`test_parse_invalid_utf8_handrolled_translates_to_malformed_lockfile`) pins this.
- **`re` import banned at module scope.** Draft Implementation-outline step 3 said "No regex over the full body; per-line `str.startswith` / `str.split` are fine." Hardened version sharpens to AC-12 + an architectural test that asserts the module does not import `re` at all — the simplest pin for "no regex over the full file" without false negatives. Per-line `str.partition` / `str.startswith` are sufficient for the format.
- **No fall-back between dispatch paths on parse error** (AC-7 + Notes §11). Draft Implementation-outline step 4 had a confusingly-worded note about pyarn parse-error fall-back ("fall back is a different decision; this story implements either-or dispatch"). Hardened version pins this as AC-7 directly and elaborates in Notes §11.

**No `NEEDS RESEARCH` findings.** The `pyarn` API surface question (could have been a researcher question) is implementation work the story already directs the implementer toward — verify the API at land-time per AC-13, record in ADR-0003. Stage 3 skipped.

Every gap traces to:

- The S3-01 + S3-02 hardened stories + their validation reports (positional-message marker, inert-`__init__` invariant, `os.fstat` monkeypatch pattern, extension-by-addition guard).
- The Phase 0 markers contract pinned by `tests/unit/test_errors.py`.
- The shared `parsers/_io.open_capped` kernel (registry pattern, `parser_kind` discriminator, `errno.ELOOP` translation, `os.fstat` size cap, `O_NOFOLLOW` open).
- The arch §"Component design" #9 cap policy (50 MB) and #4 caller contract.
- CLAUDE.md "Extension by addition" load-bearing commitment.
- ADR-0003's land-time-selection block (lines 69-71 of the ADR) — must be filled.

## Context Brief (Stage 1)

- **Goal as written:** Ship `src/codegenie/probes/_lockfiles/_yarn.py` with `_HAS_PYARN` dispatch + a hand-rolled line-by-line state-machine scanner; finalize ADR-0003 at land-time; conditionally add `pyarn` to `pyproject.toml`.
- **Phase exit criteria touched:**
  - Arch §"Component design" #9 — interface, ~80 ms (pyarn) / ~200 ms (hand-rolled) p50 budget; line-by-line state machine; no regex over full file.
  - Arch §"Component design" #4 — `NodeManifestProbe` (S3-05) is the caller; `yarn.lock` is in `declared_inputs`.
  - Arch §"Edge cases" row 10 — pyarn uninstall path → `_HAS_PYARN=False` → hand-rolled (same correctness; ~50 ms slower).
  - Arch §"Gap analysis" Gap 3 — two-direction parity test (this story enables; S3-04 implements).
  - ADR-0003 — land-time decision rule; "Implementer's land-time selection" block must be filled.
  - ADR-0007 — `WarningId` constructed at catch site from `exc.args[0]`.
  - ADR-0008 — in-process caps via shared kernel.
  - ADR-0009 — `pyarn` is the only Phase 1 dep addition; pure-Python, not a C extension; conditional adoption.
- **Phase 0 contract (load-bearing):**
  - `tests/unit/test_errors.py::test_subclasses_are_markers_only` — `cls.__init__ is e.CodegenieError.__init__`; class-dict allowlist.
  - `tests/unit/test_errors.py::test_phase1_subclasses_accept_message_arg_and_expose_args0` — parametrized over every Phase 1 marker (incl. `MalformedLockfileError`); asserts `not hasattr(exc, "path" | "cap" | "detail" | "warning_id")`.
- **Existing code already on disk:**
  - `src/codegenie/parsers/_io.py` — `open_capped(path, *, max_bytes, parser_kind)`. Returns `bytes`; raises `SizeCapExceeded`, `SymlinkRefusedError`; propagates other `OSError` subclasses unchanged. Emits `probe.parser.cap_exceeded` event with `parser_kind=<literal>`.
  - `src/codegenie/errors.py` — `MalformedLockfileError` is a marker subclass with no `__init__`.
  - `src/codegenie/probes/_lockfiles/_pnpm.py` — S3-01 baseline (S3-01 marked Ready (HARDENED) but `_pnpm.py` is on disk per the earlier story execution).
  - `src/codegenie/probes/_lockfiles/__init__.py` — `__all__: list[str] = []` plus docstring; settled by S3-01 / re-asserted by S3-02. **S3-03 must not edit.**
- **Validation precedents (marker + family discipline already settled):**
  - `_validation/S1-02-safe-json-parser.md` — first kwargs-on-markers correction; `f"{path}: {detail}"` format.
  - `_validation/S1-03-safe-yaml-parser.md` — `from cause` chaining.
  - `_validation/S3-01-pnpm-lockfile-parser.md` — established lockfile-parser shape; inert-`__init__.py` invariant.
  - `_validation/S3-02-npm-lockfile-parser.md` — reinforced inert-`__init__` + deferred `_translate` extraction to S3-03 land-time (this story).
- **Open ambiguities surfaced (resolved in hardened story):**
  1. Draft `MalformedLockfileError(path=path, cause=e)` kwargs construction — **resolved**: positional only, same as S1-02 / S1-03 / S3-01 / S3-02 settled.
  2. Draft `_open_with_size_check` reimplementation — **resolved**: use shared `open_capped` kernel; pass `parser_kind="yarn_lockfile"`.
  3. Draft "Update `_lockfiles/__init__.py` with `YarnLock` re-export" — **resolved**: contradicts S3-01/S3-02; drop and pin non-edit as AC-1.
  4. Draft 60 MB tmpfs write for size-cap test — **resolved**: rewritten as `os.fstat` monkey-patch per S3-01/S3-02.
  5. Draft `errors="replace"` UTF-8 decode — **resolved**: strict decode; `UnicodeDecodeError` surfaces and translates cleanly (Rule 12).
  6. Draft rule-of-three silence — **resolved**: DEFER explicitly with recorded rationale (Notes §7).
  7. Draft pyarn API call shape (`pyarn.parse(...)`) — **resolved**: pinned as land-time verification (AC-13); Green-code sketch is illustrative; actual API recorded in ADR-0003's land-time block.

## Stage 2 — critic reports (synthesized; parallel fan-out omitted per token economy)

Every finding the four critics would surface is cataloged below; the synthesizer pre-resolved conflicts between Coverage/Test-Quality (both wanted more ACs) and Consistency/Design-Patterns (both insisted on the shared-kernel call). Consistency wins; the in-module reimplementation is dropped.

### Coverage (verdict: COVERAGE-BLOCK + harden)

| # | Severity | Finding |
|---|---|---|
| CV1 | **block** | AC-3 prescribes `MalformedLockfileError(path=path, cause=e)` (kwargs) and tests assert `exc.value.path == lockfile`. Phase 0 invariant + S1-01 parametrized tests make this impossible to satisfy. Same defect as S1-02 / S1-03 / S3-01 / S3-02 drafts. |
| CV2 | **block** | Draft Implementation-outline step 2 prescribes in-module `_open_with_size_check` instead of calling the shared `open_capped` kernel. Defeats registry pattern + duplicates load-bearing security code. |
| CV3 | **block** | Implementation-outline step 8 prescribes additive re-export from `_lockfiles/__init__.py`. Contradicts S3-01/S3-02's settled inert form. |
| CV4 | **block** | Rule-of-three resolution missing — S3-01/S3-02 explicitly punted to S3-03 land-time; draft is silent. |
| CV5 | harden | No AC for `__cause__` chain — dropping `from cause` would pass every existing test. |
| CV6 | harden | No AC for `str(path) in exc.args[0]` — `WarningId` reconstruction needs the path recoverable from the message. |
| CV7 | harden | No AC for `SymlinkRefusedError` passthrough on the dispatched-through path. |
| CV8 | harden | No AC for `_HAS_PYARN` semantics being driven by `importlib.util.find_spec`. |
| CV9 | harden | No AC for `total=False` semantics on `YarnLock` / `YarnLockEntry`. |
| CV10 | harden | Module constants not declared `Final[int]`. |
| CV11 | harden | `__all__` not declared on `_yarn.py`. |
| CV12 | harden | No AC for extension-by-addition (CLAUDE.md "Extension by addition") — sibling-import architectural test. |
| CV13 | harden | No AC pinning the non-edit of `_lockfiles/__init__.py` (S3-03 inherits the inert form). |
| CV14 | harden | No AC for `parser_kind="yarn_lockfile"` discriminator surfacing on `probe.parser.cap_exceeded` event. |
| CV15 | harden | No AC pinning the `pyarn` API surface verification at land-time. |
| CV16 | harden | Local-fuzz AC (#9 in draft) phrased only as "note in PR body" — no concrete script form. |

### Test Quality (verdict: TESTS-BLOCK)

Mutation analysis:

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| M1 | `MalformedLockfileError(path=..., cause=...)` (kwargs) | **No** — `TypeError` at construction; test never reaches assertion | **block** |
| M2 | Drop `from cause` — loses `__cause__` chain | **No** — no AC, no test | harden |
| M3 | Reimplement `O_NOFOLLOW` open + size check; forget `errno.ELOOP` portability (use raw `e.errno in (40, 62)`); test on macOS only | **Partially** — symlink test fires on the right platform but skips silently elsewhere | harden |
| M4 | `_HAS_PYARN = True` hardcoded — never falls back | **No** — every other test passes if `pyarn` happens to be installed | harden |
| M5 | `except BaseException as cause` (would absorb KeyboardInterrupt + SystemExit) | **No** | harden |
| M6 | `body.decode("utf-8", errors="replace")` — substitutes U+FFFD; scanner chases garbage | **No** — happy path doesn't trigger; no invalid-UTF-8 test | harden |
| M7 | Fall back from pyarn to hand-rolled on parse error | **No** — draft note is confusing; no AC pins the prohibition | harden |
| M8 | Module-scope `re.compile(...)` with `findall` over full body | **No** — no architectural test for the "no regex over full file" rule | harden |
| M9 | Re-export `YarnLock` from `_lockfiles/__init__.py` | **Not caught** in S3-03 — only S3-02's test (run on its own branch) catches it; need to re-run at S3-03 land | harden |
| M10 | Pass `parser_kind="safe_yaml"` to `open_capped` (sloppy copy-paste from `_pnpm` shape) | **No** — no event-capture test | harden |
| M11 | Marker `__init__` override smuggling instance attributes | Phase 0 test catches at class level; no test guards the construction site in `_yarn.py` | harden |
| M12 | Run the malformed-bytes test against whichever path happens to be active (`_HAS_PYARN=True` or `False`) | **Partially** — test passes but is non-deterministic; force the hand-rolled path | harden |

Test-quality additions:
- Force the hand-rolled path via `monkeypatch.setattr(_yarn, "_HAS_PYARN", False)` for malformed-bytes test.
- Two `_HAS_PYARN` semantics tests with `monkeypatch.setattr(importlib.util, "find_spec", ...)` + `importlib.reload`.
- `structlog`-capture test for `parser_kind="yarn_lockfile"` on the cap-exceeded event.
- Architectural test for no-`re`-import + no-sibling-import.
- Architectural test re-asserting `_lockfiles/__init__.py` inertness.

### Consistency (verdict: CONSISTENCY-BLOCK)

| # | Severity | Finding |
|---|---|---|
| CN1 | **block** | Marker construction (CV1 / M1) — contradicts Phase 0 invariant. |
| CN2 | **block** | `_open_with_size_check` reimplementation (CV2 / M3) — contradicts CLAUDE.md "Extension by addition" load-bearing commitment ("Adding Java, Python, or a new task type must be new probes + new Skills, never edits to existing probes or the coordinator"); applied at the parser-kernel scope, this means new parsers must be new callers of `open_capped`, not new reimplementations of `O_NOFOLLOW`/size-cap. |
| CN3 | **block** | `_lockfiles/__init__.py` re-export (CV3 / M9) — contradicts S3-01 settled form + S3-02 AC-1 + `test_lockfiles_init_remains_inert`. |
| CN4 | harden | Draft "Refactor" note ("The `_open_with_size_check` helper duplicates parts of `safe_json.load` / `safe_yaml.load`. Don't extract unless S3-01 and S3-02 also need it") — wrong on the premise: `safe_json` / `safe_yaml` *already* call `open_capped`; there is no duplication waiting to happen because the kernel exists. Rewritten in the hardened story to note that yarn is the **third** caller of `open_capped`, validating the registry-pattern claim. |
| CN5 | harden | Draft Implementation-outline #4 confusingly says "fall back on error" then immediately says "Don't fall back on parse error; raise. The fallback is on `ImportError`, captured by `_HAS_PYARN`." Hardened version pins this as AC-7 + Notes §11 directly. |
| CN6 | harden | Draft Files-to-touch table is missing the `tools/fuzz_yarn_lock.py` row (since the draft only described "local fuzzing" as a PR-body note). Hardened version adds it. |

### Design Patterns (verdict: PATTERNS-HARDEN)

| # | Finding | Resolution |
|---|---|---|
| DP1 | Rule of three — extract `_translate(path, *, cause)` helper? | **DEFER** with recorded rationale (block-correction #4). The trio is two-of-a-kind plus one-of-a-kind; extraction creates either over-broad or two-helper bloat. Documented in Notes §7. |
| DP2 | Registry pattern at the parser-kernel level (`open_capped` with `parser_kind`) | Already realized in `parsers/_io.py`. Hardened story makes `_yarn.py` the **third** caller, validating the kernel's `parser_kind` registry hook. AC-18 pins the discriminator surfacing on the structured event. |
| DP3 | Strategy pattern (`_HAS_PYARN` two-strategy dispatch) | Kept in simplest form (inline `if _HAS_PYARN:` inside `parse()`). Not refactored to a module-level `_PARSER_FN: Callable` binding — call sites differ subtly and Rule 2 pre-empts the abstraction. Documented in Notes §9. |
| DP4 | Functional core / imperative shell | `_parse_handrolled(body: bytes) -> YarnLock` and `_pyarn_parse(body: bytes) -> YarnLock` are pure; `parse(path)` is the only I/O function. Pays off for the local fuzz harness (AC-16) which targets `_parse_handrolled` directly. Documented in Notes §10. |
| DP5 | Open/Closed at the family level | AC-17 pins the architectural test (no sibling-imports). AC-1 pins the non-edit of `_lockfiles/__init__.py`. |
| DP6 | Sum types (`Literal`) for `current_subblock` state | Not promoted to an AC — `current_subblock: str \| None` with values `"dependencies"` / `"optionalDependencies"` is small enough that `Literal["dependencies", "optionalDependencies"] \| None` would be over-engineering for a private local variable. Documented in the refactor refactor-deferral implicitly. |
| DP7 | Newtype pattern for `parser_kind` | `parser_kind: str` could be `Literal["safe_yaml", "safe_json", "yarn_lockfile", ...]`. Considered; deferred — Phase 2's `IndexHealthProbe` introduces the next parser_kind and is the better moment to extract a `Literal`. Documented as a Phase-2 follow-up; no edit here. |
| DP8 | Marker hierarchy expansion (e.g., `MalformedYarnLockError(MalformedLockfileError)`) | Considered; rejected. Phase 0 invariant freezes the marker hierarchy. The `cause.type.__name__` in `args[0]` (AC-9) preserves the same observability without expanding the type set. |

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. The closest candidate (`pyarn` API surface verification) is implementation work the story directs the implementer to perform at land-time and record in ADR-0003 — that's AC-13, not a researcher question.

## Stage 4 — Synthesizer + Editor

### Conflict resolutions

- **Coverage vs. Design-Patterns on `_translate` extraction.** Coverage wanted an AC pinning the helper's shape; Design-Patterns wanted to defer per Rule 2 + the trio-shape divergence. Design-Patterns wins (priority: Consistency > Coverage > Test-Quality > Design-Patterns; here it's actually Consistency aligning with Design-Patterns — CLAUDE.md "Extension by addition" reads as "new files, not edits", which favors deferring vs. retrofitting a kernel onto two existing files). Resolution: defer with rationale (Notes §7).
- **Test-Quality vs. Coverage on `pyarn` install state.** Test-Quality wanted to force the hand-rolled path on every test (deterministic); Coverage wanted to test both paths (completeness). Resolution: force the hand-rolled path on the deterministic assertions (malformed-bytes, happy-path-shape) AND add `_HAS_PYARN` semantics tests via `importlib.reload`. Both critics' concerns satisfied.
- **Consistency vs. Coverage on `_lockfiles/__init__.py` re-export.** Consistency says "S3-01/S3-02 settled inert; don't touch"; Coverage's instinct was "let downstream import `YarnLock` from the package root." Consistency wins (source-of-truth is the prior validation reports); `from codegenie.probes._lockfiles import _yarn` is the consumer pattern.

### Edits applied (in-place)

The entire story was rewritten — diff is too large to inline, but the structure is:

1. **Header block** — added `(HARDENED)` to Status; added S3-01/S3-02 to `Depends on`; added ADR-0007/0008 to `ADRs honored`; added Phase-0 invariant honored line.
2. **Validation notes section** added — block corrections + harden-tier additions + design-pattern findings.
3. **Context** rewrote — added the trio-shape framing and the rule-of-three resolution upfront.
4. **References** restructured to mirror S3-02's shape — added `parsers/_io.py`, `EVENT_PROBE_PARSER_CAP_EXCEEDED`, validation precedents.
5. **Goal** restated with the shared-kernel call + no-edit-to-`__init__` constraint.
6. **Acceptance criteria** expanded from 11 to 21, each numbered for TDD-plan traceability. Block-defect ACs replaced; harden-tier ACs added.
7. **Implementation outline** rewrote — step 2 now calls `open_capped`; step 8 is the ADR edit (the old step 8 — `__init__.py` re-export — is dropped); a new step for committing `tools/fuzz_yarn_lock.py` is added.
8. **TDD plan / Red** — 12 tests, each docstring-annotated with the AC and the mutation it catches. New tests: invalid-UTF-8 path; `_HAS_PYARN` semantics (two); architectural no-`re`-import; architectural no-sibling-import; `_lockfiles/__init__.py` inertness; `parser_kind` event-capture.
9. **TDD plan / Green** — `open_capped` call; `_HAS_PYARN` via `find_spec`; strict UTF-8 decode; `_pyarn_parse` adapter sketched with land-time-verification note; broad `except Exception as cause` with `(SizeCapExceeded, SymlinkRefusedError)` passthrough.
10. **TDD plan / Refactor** — kept module constants per-file (DP-1 deferral); documented the broader catch (yarn vs. pnpm/npm narrow catches); placeholder `_pyarn_parse` flagged as land-time-fill.
11. **Files to touch** — added `tools/fuzz_yarn_lock.py` row; clarified non-edit list.
12. **Out of scope** — added `_translate` extraction deferral; `_lockfiles/__init__.py` non-edit.
13. **Notes for the implementer** — 16 entries (was 6), aligned with the new ACs.

### Verdict

**HARDENED.** Block-level corrections + 14 harden-tier additions applied in-place. Story is ready for `phase-story-executor` consumption. Marker discipline + shared-kernel call + extension-by-addition + rule-of-three deferral all pinned by ACs with traceability to the TDD plan. The ADR-0003 land-time-selection block + the `pyarn` API surface verification remain implementer responsibilities — the story directs both with concrete ACs (AC-13, AC-15) and PR-template checklist items.

### Follow-up obligations (for future stories / Phase 2)

- **S3-04 parity + oracle tests** — the two-direction validation per arch §"Gap analysis" Gap 3. Lands one story later; reads `YarnLock` shape from `_yarn.parse(...)` on both `_HAS_PYARN=True` and `_HAS_PYARN=False` paths.
- **S5-02 adversarial regex-DoS test** — `tests/adv/test_regex_dos_yarn_lock.py`. The CI gate that the local fuzz (AC-16) precedes.
- **Phase 2 — `_translate` extraction revisit** — if a fourth lockfile (`bun.lockb`) lands, the trio becomes two-of-a-kind plus two-of-a-kind, which may be the right moment to extract.
- **Phase 2 — `parser_kind` Literal extraction** — once `IndexHealthProbe` introduces the next parser_kind, hoist `parser_kind: str` to `Literal["safe_yaml", "safe_json", "yarn_lockfile", "index_health", ...]` in `parsers/_io.py`.
