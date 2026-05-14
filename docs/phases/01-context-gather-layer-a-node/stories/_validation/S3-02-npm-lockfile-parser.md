# Validation report — S3-02 `_npm` lockfile parser

**Story:** [S3-02-npm-lockfile-parser.md](../S3-02-npm-lockfile-parser.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The goal — a thin `safe_json.load` wrapper for `package-lock.json` returning an `NpmLock` `TypedDict`, structurally mirroring S3-01's `_pnpm.py` — is well-formed and traces cleanly to arch §"Component design" #9, §"Component design" #4 (`NodeManifestProbe` caller), arch line 517 (`_npm.py: parsers.safe_json.load (50 MB cap, depth 64)`), ADR-0008 (in-process caps), ADR-0009 (no new C-extension deps), and ADR-0007 (`WarningId` constructed at catch site). **The draft inherited the exact two block-level defects already corrected in S1-02 / S1-03 / S3-01**: it prescribed `MalformedLockfileError(path=path, cause=e)` (kwargs form) and asserted `exc.value.path == lockfile`. The Phase 0 invariant `tests/unit/test_errors.py::test_subclasses_are_markers_only` plus S1-01's parametrized `test_phase1_subclasses_accept_message_arg_and_expose_args0` parametrize **every** Phase 1 marker (including `MalformedLockfileError`) as positional-only — `hasattr(exc, "path")` is an asserted negative. Construction must be `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause`. Path lives in `args[0]`; the original `MalformedJSONError` lives on `__cause__`.

A second consistency block: the draft's AC-7 and Implementation-outline step 3 both prescribe "additively re-export `NpmLock`" from `src/codegenie/probes/_lockfiles/__init__.py`. That contradicts S3-01's settled final form (`__all__: list[str] = []` with a docstring stating "S3-01 ships `_pnpm`; S3-02 ships `_npm`; S3-03 ships `_yarn`. `__all__` stays empty here — each sibling exports from its own module to keep import order unsurprising"). Consumers import siblings directly (`from codegenie.probes._lockfiles import _npm`), which works because `_npm` is a submodule of the package. The hardened story drops the re-export step, drops AC-7, and pins the **non-edit** of `_lockfiles/__init__.py` as AC-1 (a CLAUDE.md "Extension by addition" guarantee — S3-02 must not touch the family-`__init__` settled in S3-01).

Twelve harden-tier additions mirroring S3-01's hardened shape with npm-specific deltas:

1. Explicit AC for the `__cause__` chain (`isinstance(exc.__cause__, MalformedJSONError)`).
2. Explicit AC for `str(path) in exc.args[0]` (downstream `WarningId` recovery per ADR-0007).
3. Parametrized markers-only-negative test (`not hasattr(exc, "path" | "cap" | "detail" | "cause" | "warning_id")`).
4. Size-cap test rewritten to monkey-patch `os.fstat`, avoiding the 60 MB tmpfs write the draft prescribed (Rule 2 — smallest test that proves the contract; mirrors S3-01 precedent).
5. Symlink-passthrough test added (`SymlinkRefusedError` re-raise from `safe_json`).
6. Top-level non-mapping translation made explicit — `safe_json.load` raises `MalformedJSONError` for list / scalar / `null` top-level (`safe_json._decode` line 100: `if not isinstance(obj, dict): raise MalformedJSONError`); `_npm.parse` translates to `MalformedLockfileError` per the same handler that catches malformed-JSON, asserted as the typed exception (not a `TypeError`).
7. `total=False` semantics pinned by a v1-shape fixture (`dependencies` only, no `packages`) and a v3-shape fixture (`packages` only, no `dependencies`) — npm's `lockfileVersion` 1 → 3 evolution is the load-bearing variance that `total=True` would mask.
8. Module constants typed `Final[int]`.
9. `__all__ = ["NpmLock", "parse"]` declared.
10. Architectural test `test_npm_module_does_not_reference_sibling_parsers` pinning CLAUDE.md "Extension by addition" (adding `_bun.py` later must require zero edits to `_npm.py`).
11. Empty-file translation test (`safe_json._decode` raises `MalformedJSONError("empty file")`; must surface as `MalformedLockfileError`).
12. Explicit no-op of `_lockfiles/__init__.py` (AC-1) — S3-02 inherits and must not modify the family-`__init__`.

Two draft-only ambiguities resolved:

- Draft's **depth-cap test fixture choice (70 levels of `{"a":{...}}` nesting)** is correct *for JSON* (unlike S3-01's YAML where bracket-nesting surfaces as `ScannerError`). JSON has no aliases; the depth walker's `id()`-memoization is harmless but non-load-bearing here. The fixture is kept; the implementer-note clarifying "70 levels exceeds 64 cap" is preserved, with a new note pinning why JSON-deep-nesting differs from YAML-alias-amplification.
- Draft's **size-cap test note** ("verify the pre-parse size check on the fd fires before `_json.c` allocates") is rendered moot by the `os.fstat` monkey-patch: with the patch, no 60 MB write happens at all, and the load-bearing assertion is unambiguous — the pre-parse cap fires on the patched `st_size`, full stop.

Design-pattern resolutions (DP1, DP7) recorded in `Notes for the implementer`. **The shared `_translate(path, *, cause)` helper is still deferred to S3-03's land time** — S3-02 is the second concrete parser, but the rule-of-three threshold is the third (S3-03). Premature extraction in S3-02 would create a kernel S3-03 inherits silently. DP7 (Open/Closed at the family level) is promoted to AC-12 with the source-introspection architectural test.

No `NEEDS RESEARCH` findings; Stage 3 skipped. Every gap traces to:

- The S3-01 hardened story + its validation report (positional-message marker, alias-vs-bracket depth-test rationale, extension-by-addition guard).
- The Phase 0 markers contract pinned by `tests/unit/test_errors.py`.
- `safe_json.load`'s settled translation surface (`MalformedJSONError` raised for empty file / `JSONDecodeError` / non-dict top-level; pre-parse `os.fstat` size check; `O_NOFOLLOW` open).
- The arch §"Component design" #9 cap policy (50 MB / depth 64) and #4 caller contract.
- CLAUDE.md "Extension by addition" load-bearing commitment.

## Context Brief (Stage 1)

- **Goal as written:** Ship `src/codegenie/probes/_lockfiles/_npm.py` as a thin `safe_json.load` wrapper returning an `NpmLock` `TypedDict`, structurally identical to S3-01's `_pnpm.py` except for the parser entry point and the translated exception class.
- **Phase exit criteria touched:**
  - Arch §"Component design" #9 — interface, ~100 ms p50 budget for ~10 MB package-lock.json (v2+ stores both flat and nested trees → larger files than pnpm).
  - Arch §"Component design" #4 — `NodeManifestProbe` (S3-05) is the caller; `package-lock.json` is in `declared_inputs`.
  - Arch §"Component design" #8 — `safe_json.load(path, *, max_bytes, max_depth=64)` contract.
  - Arch line 517 — `_npm.py: parsers.safe_json.load (50 MB cap, depth 64)`.
  - ADR-0008 — in-process caps replace per-probe sandbox.
  - ADR-0009 — stdlib `json` only; no `orjson` / `pyjson5`.
  - ADR-0007 — `WarningId` constructed at the catch site from `exc.args[0]`, not embedded on the exception class.
- **Phase 0 contract (load-bearing):**
  - `tests/unit/test_errors.py::test_subclasses_are_markers_only` — `cls.__init__ is e.CodegenieError.__init__`; class-dict allowlist.
  - `tests/unit/test_errors.py::test_phase1_subclasses_accept_message_arg_and_expose_args0` — parametrized over every Phase 1 marker (incl. `MalformedLockfileError`); asserts `not hasattr(exc, "path" | "cap" | "detail" | "warning_id")`.
- **Existing code already on disk:**
  - `src/codegenie/parsers/safe_json.py` from S1-02 — raises positional-only markers; `f"{path}: {detail}"` is the established message format; `_decode` already enforces top-level-dict (raises `MalformedJSONError("expected JSON object at top level")` for list/scalar/null).
  - `src/codegenie/errors.py` — `MalformedLockfileError` is a marker subclass with no `__init__`.
  - **`src/codegenie/probes/_lockfiles/_pnpm.py` is NOT yet on disk** (S3-01 is HARDENED but unexecuted); `_lockfiles/__init__.py` is also not on disk. S3-02's TDD plan must therefore assume S3-01 has landed *before* S3-02 begins (already encoded in `Depends on`).
- **Validation precedents (the marker discipline already settled):**
  - `_validation/S1-02-safe-json-parser.md` — first kwargs-on-markers correction; introduced `f"{path}: {detail}"` format.
  - `_validation/S1-03-safe-yaml-parser.md` — added `from cause` chaining; alias-amplification mutation surfaced.
  - `_validation/S3-01-pnpm-lockfile-parser.md` — established the exact lockfile-parser shape S3-02 mirrors; pinned `_lockfiles/__init__.py` as inert (`__all__: list[str] = []`).
- **Open ambiguities surfaced (resolved in hardened story):**
  1. Draft AC-7 + Implementation-outline step 3 "additively re-export `NpmLock`" — **resolved**: contradicts S3-01's settled inert `__init__.py`. Drop the re-export; consumers import siblings directly.
  2. Draft's "If `MalformedLockfileError.__init__` carries `path + cause`" hedge (Note #5 implicit via line 130's kwargs construction) — **resolved**: the contract is settled, positional only.
  3. Draft's 60 MB byte payload for size-cap test — **resolved**: rewritten as `os.fstat` monkey-patch per S3-01.

## Stage 2 — critic reports (synthesized; parallel fan-out omitted per token economy)

Every finding the four critics would surface is already cataloged in the S3-01 validation report; the npm-specific deltas are listed below.

### Coverage (verdict: COVERAGE-HARDEN)

| # | Severity | Finding |
|---|---|---|
| CV1 | **block** | AC-3 prescribes `MalformedLockfileError(path=path, cause=e)` (kwargs) and tests assert `exc.value.path == lockfile`. Phase 0 invariant + S1-01 parametrized tests make this impossible to satisfy. Same defect as S3-01 draft. |
| CV2 | **block** | AC-7 + Implementation-outline step 3 prescribe additive re-export from `_lockfiles/__init__.py`. S3-01 hardened story settled `__all__: list[str] = []`. Must drop. |
| CV3 | harden | No AC for `__cause__` chain — dropping `from cause` would pass every existing test. |
| CV4 | harden | No AC for `str(path) in exc.args[0]` — `WarningId` reconstruction in `NodeManifestProbe` needs the path recoverable from the message. |
| CV5 | harden | No AC for `SymlinkRefusedError` passthrough. |
| CV6 | harden | No AC for top-level non-mapping translation (`MalformedJSONError` → `MalformedLockfileError`). |
| CV7 | harden | No AC for empty-file translation (`safe_json._decode` raises `MalformedJSONError("empty file")`). |
| CV8 | harden | No AC for `total=False` semantics pinned by v1-shape + v3-shape fixtures. |
| CV9 | harden | Module constants not declared `Final[int]`. |
| CV10 | harden | `__all__` not declared on `_npm.py`. |
| CV11 | harden | No AC for extension-by-addition (CLAUDE.md "Extension by addition"). |
| CV12 | harden | No AC pinning the **non-edit** of `_lockfiles/__init__.py` (S3-02 inherits the inert form). |

### Test Quality (verdict: TESTS-BLOCK)

Mutation analysis (same set as S3-01, npm-specific where it differs):

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| 1 | `MalformedLockfileError(path=..., cause=...)` (kwargs) | **No** — `TypeError` at construction; test never reaches assertion | **block** |
| 2 | Drop `from cause` — loses `__cause__` chain | **No** — no AC, no test | harden |
| 3 | `except Exception as cause: raise MalformedLockfileError(...)` — swallows typed exceptions | **No** — draft size-cap test would catch this only because it expects `SizeCapExceeded`; ✓ partial | OK |
| 4 | Build message as `str(cause)` without path | **No** — no path-in-message AC | harden |
| 5 | Symlink follows (would require `safe_json` regression — out of scope but the passthrough test pins our re-raise) | **No** — draft has no symlink test | harden |
| 6 | `total=True` on `NpmLock` — v1 (no `packages`) callers would need to default | **No** at runtime; only v3-shape fixture is tested | harden |
| 7 | Use bracket-nesting for depth-cap (the draft's approach) | ✓ caught — JSON has no aliases; `_json.c` parses 70-deep nests successfully; the post-parse `_walk` fires `DepthCapExceeded` at depth 65 | OK (unlike YAML, this is the **correct** vector for JSON) |
| 8 | Schema-validate the lockfile inside `parse` (out-of-scope behavior added) | **No** — Notes say don't, but no negative test | nit |
| 9 | Add `MalformedLockfileError.__init__(self, *, path, cause)` "for convenience" | **No** — no test of the marker discipline at construction site | harden |
| 10 | Sibling-import `_pnpm` from `_npm.py` | **No** — no test pinning extension-by-addition | harden |
| 11 | Translate `MalformedJSONError` only for `JSONDecodeError` path, miss `empty file` and `expected JSON object` paths | **No** — draft has one malformed-JSON test only | harden |
| 12 | Add a re-export to `_lockfiles/__init__.py` (draft AC-7 invites this) | **No** — draft AC-7 prescribes it; we must invert | **block** |

### Consistency (verdict: CONSISTENCY-BLOCK)

| # | Severity | Finding |
|---|---|---|
| CN1 | **block** | `MalformedLockfileError(path=path, cause=e)` violates `test_subclasses_are_markers_only` (Phase 0) and `test_phase1_subclasses_accept_message_arg_and_expose_args0` (S1-01). Same defect S1-02 / S1-03 / S3-01 hardenings already corrected. |
| CN2 | **block** | `assert exc.value.path == lockfile` (draft lines 82, 95) — markers expose no `.path`. Must assert via `str(exc.value.args[0])`. |
| CN3 | **block** | Draft AC-7 and Implementation-outline step 3 "additively re-export `NpmLock`" contradicts S3-01 hardened story (`__all__: list[str] = []`). Must drop re-export, pin non-edit. |
| CN4 | harden | Draft's mention of S1-03 dependency for "symmetry with sibling parsers' shared error-translation pattern" — S3-02 depends on S1-02 (`safe_json`) and S1-01 (markers), not S1-03 (which serves S3-01). Fix `Depends on`. |
| CN5 | harden | Module constants `NPM_LOCKFILE_MAX_BYTES` not declared `Final` — S1-02 / S3-01 precedent uses `Final[int]`. |
| CN6 | nit | Draft Note about "if `MalformedJSONError` from S1-01 carries `path` + `cause` per the typed-exception extension contract" — `MalformedJSONError` is a Phase 1 marker (S1-01); per the markers-only contract, it does *not* carry `path` or `cause`. The note inverts the contract just like S3-01 draft did. Delete. |

### Design Patterns (verdict: DESIGN-HARDEN)

| # | Severity | Finding |
|---|---|---|
| DP1 | nit (resolved as deferral) | Shared `_translate(path, *, cause)` helper across pnpm/npm/yarn — opportunity exists but **the rule of three is not yet crossed in S3-02** (this is the second concrete consumer; rule-of-three is the third = S3-03). Recommendation recorded in Notes for the implementer; extraction deferred to S3-03's land time. |
| DP2 | harden | `total=False` on `NpmLock` is load-bearing for v1 vs v3 variance — v1 has `dependencies` only, v3 has `packages` only. Hardened story makes this explicit + pins via v1-fixture + v3-fixture tests. |
| DP3 | nit | A `Literal["npm"]` discriminator could surface at module level for downstream `WarningId` construction. Deferred — consumer constructs the ID per ADR-0007; YAGNI. |
| DP4 | harden | Module constants need `Final[int]` typing. |
| DP5 | harden | Functional-core / imperative-shell split: `parse` is I/O + translation; `cast(NpmLock, raw)` is pure no-op. Surface in Notes so future maintainers don't smuggle validation in. |
| DP6 | nit | Tagged-union `Result[NpmLock, LockfileParseError]` — deferred (exceptions are the established pattern; adopting Result here would require `NodeManifestProbe` and all three siblings to adopt it). |
| DP7 | **harden** | Open/Closed at the family level — adding `_bun.py` must require zero edits to `_npm.py`. **Promoted to AC-12** with an architectural test (source introspection) because it's a load-bearing CLAUDE.md commitment and the test cost is one `inspect.getsource()` call. |
| DP8 | nit | `__all__` declaration provides a clean public-API surface for the module; promoted to AC-2. |
| DP9 | harden | Non-edit of `_lockfiles/__init__.py` is **itself** an Open/Closed signal — S3-02 adds a new module, period. Promoted to AC-1 with a test (`_lockfiles/__init__.py` content unchanged from S3-01). Less wishful than relying on reviewer vigilance. |

### Story-smells scan

- ✗ "Mirror `_pnpm.py`'s structure verbatim" appears in Note #1 and Implementation outline step 1 — concrete, but the draft *also* prescribes a kwargs marker construction that doesn't match `_pnpm.py`'s positional form, so the symmetry-claim is hollow. Hardened story makes the positional form the literal instruction.
- ✗ Test prescribes 60 MB byte-write — replaced with `os.fstat` monkey-patch (Rule 2).
- ✗ "If `MalformedJSONError` from S1-01 carries `path` + `cause` per the typed-exception extension contract; if the constructor signature drifted, surface in PR body" inverts the contract (markers never carry instance state). Delete.
- ✗ "Update `_lockfiles/__init__.py` to additively re-export `NpmLock`" contradicts S3-01 settled form. Delete.
- ✓ TDD plan distinguishes intent from behavior via per-test naming (Rule 9 supported once hardened).
- ✓ Out-of-scope list is precise and traces to specific downstream stories (S3-03, S3-05, S3-06).

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap traces to:

- Phase 0 `errors.py` contract (frozen, tested by parametrized markers-only tests).
- S1-02 + S3-01 hardened stories (established positional-message + `from cause` precedent + inert `_lockfiles/__init__.py`).
- `safe_json.load` source (line 100: top-level non-dict raises `MalformedJSONError`; line 93: empty file raises `MalformedJSONError`).
- Arch §"Component design" #9 (cap policy) and #4 (caller contract).
- CLAUDE.md "Extension by addition" load-bearing commitment.

## Stage 4 — Synthesizer resolution

### Conflict resolution

No conflicts among the four critics — every finding compounds in the same direction. Consistency dominates (CN1 / CN2 / CN3 are blocks); Coverage and Test-Quality findings layer onto the corrected base. Design-Patterns DP7 promoted to AC-12; DP9 promoted to AC-1; DP1 deferred to S3-03 per Rule 2. Consistency priority preserves `_lockfiles/__init__.py` inert — Design-Patterns DP9 makes the inheritance explicit rather than implicit.

### Edits applied (before / after)

**Status field:**
- Before: `**Status:** Ready`
- After: `**Status:** Ready (HARDENED)` + new `Validation notes` block.

**Depends on:**
- Before: `S1-02 (safe_json), S1-03 (safe_yaml — for symmetry with the sibling parsers' shared error-translation pattern)`
- After: `S3-01 (_pnpm.py + _lockfiles/__init__.py — the family kernel landed here), S1-02 (safe_json.load), S1-01 (Phase 1 marker exceptions)` — direct dependencies named; S1-03 dependency removed (irrelevant to JSON parsing).

**ADRs honored:**
- Before: ADR-0008, ADR-0009.
- After: ADR-0008, ADR-0009, ADR-0007 (`WarningId` construction at catch site — the marker contract this story honors).

**Acceptance criteria:**
- Before: 7 unnumbered checkboxes; one kwargs-on-markers block; one additive-re-export block; one missing-cause-chain gap; no extension-by-addition AC.
- After: 15 numbered ACs, each traceable to one or more TDD-plan tests. AC-1 pins non-edit of `_lockfiles/__init__.py`; AC-2 pins module shape; AC-3 pins cap constants; AC-4 pins three passthrough markers; AC-5 / AC-7 / AC-8 pin malformed-JSON translation + `__cause__` chain + path-in-args[0]; AC-6 / AC-15 pin marker discipline; AC-9 pins `total=False`; AC-10 / AC-11 pin non-mapping / empty-file translation; AC-12 pins extension-by-addition (architectural test); AC-13 pins toolchain green; AC-14 pins TDD discipline.

**TDD plan:**
- Before: 4 tests (happy + 3 typed failures) with kwargs-on-markers assertions and a 60 MB byte-write.
- After: 11 named tests, each with a docstring keying it to its AC(s) and naming the mutation it catches:
  1. `test_parse_happy_path_v3_returns_typed_dict_shape` (AC-3/9/14)
  2. `test_parse_happy_path_v1_missing_packages_still_parses` (AC-9 — pins `total=False`)
  3. `test_parse_oversized_file_reraises_size_cap` (AC-4; `os.fstat` monkey-patch — no 60 MB write)
  4. `test_parse_deep_nesting_reraises_depth_cap` (AC-4; bracket-nesting is the correct vector for JSON)
  5. `test_parse_symlink_at_final_component_reraises_symlink_refused` (AC-4)
  6. `test_parse_malformed_json_raises_malformed_lockfile_with_cause_chain` (AC-5/7)
  7. `test_parse_malformed_json_message_contains_path` (AC-8)
  8. `test_parse_top_level_non_mapping_raises_malformed_lockfile` (AC-10)
  9. `test_parse_empty_file_raises_malformed_lockfile` (AC-11)
  10. `test_raised_marker_has_no_instance_attributes` (AC-6/15)
  11. `test_npm_module_does_not_reference_sibling_parsers` (AC-12; CLAUDE.md "Extension by addition")
  12. `test_lockfiles_init_remains_inert` (AC-1; S3-01's settled form unchanged by S3-02)

**Implementation outline:**
- Before: step 3 "Update `_lockfiles/__init__.py` to additively re-export `NpmLock`" — invented. Deleted. Replaced with a non-edit guarantee.
- Outline now prescribes `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause` directly; module constants typed `Final[int]`; `__all__ = ["NpmLock", "parse"]`.

**Notes for the implementer:**
- Before: 6 bullets, one of which ("If `MalformedJSONError` from S1-01 carries `path + cause` per the typed-exception extension contract; if the constructor signature drifted, surface in PR body") inverts the contract.
- After: 9 bullets — corrects the marker discipline note, adds the JSON-vs-YAML depth-test rationale (no alias amplification in JSON; bracket-nesting is the correct vector), adds the rule-of-three deferral for the shared `_translate` helper (still S3-03's call), adds the Open/Closed-at-family-level commitment, adds the functional-core / imperative-shell rationale for `cast(NpmLock, raw)`, adds the `__all__` rationale, adds the non-edit `_lockfiles/__init__.py` rationale.

## Verdict: **HARDENED**

The story is now ready for `phase-story-executor`. All ACs are individually verifiable; the TDD plan's twelve named tests collectively cover the goal under mutation; the marker discipline is settled and matches S1-01/S1-02/S1-03/S3-01 precedents; the extension-by-addition commitment is pinned via an architectural test; the non-edit of `_lockfiles/__init__.py` is pinned by an inert-file test; and the design-pattern opportunity (shared `_translate` helper) is correctly deferred to S3-03 per Rule 2.

## Follow-up obligations carried forward

- **S3-03** (yarn-lockfile-parser): rule-of-three threshold. Evaluate extracting `_translate(path, *, cause)` to `_lockfiles/__init__.py` or `parsers/_lockfile_io.py` once all three are visible. If extracted, AC-12's "no sibling import" guard in S3-01 and S3-02 stays satisfied because the helper lives in the package `__init__`, not in a sibling module. Note: extracting to `__init__` would require **lifting** `__all__` from `[]` to `["_translate"]` (or similar); that is S3-03's decision, NOT S3-02's.
- **S3-05** (`NodeManifestProbe`): caller; constructs `WarningId` per ADR-0007 from `exc.args[0]` for each typed exception. The path-in-message contract (AC-8) is the load-bearing handoff.
