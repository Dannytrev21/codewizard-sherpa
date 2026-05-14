# Validation report — S3-01 `_pnpm` lockfile parser

**Story:** [S3-01-pnpm-lockfile-parser.md](../S3-01-pnpm-lockfile-parser.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The goal — a thin `safe_yaml.load` wrapper for `pnpm-lock.yaml` returning a `PnpmLock` `TypedDict` — traces cleanly to arch §"Component design" #9, §"Component design" #4 (`NodeManifestProbe` caller), §"Edge cases" row 1 (billion-laughs), §"Scenarios" #3 (alias-amplification flow), ADR-0008 (in-process caps) and ADR-0009 (no new C-extension parsers). **The draft inherited the same kwargs-on-markers defect that S1-02 and S1-03 hardenings already corrected**: it prescribed `MalformedLockfileError(path=path, cause=e)` (kwargs) and asserted `exc.value.path == lockfile`. Phase 0's `tests/unit/test_errors.py::test_subclasses_are_markers_only` and S1-01's `test_phase1_subclasses_accept_message_arg_and_expose_args0` parametrize `MalformedLockfileError` as positional-only and assert `not hasattr(exc, "path")`. The implementer-notes hedge ("if `__init__` doesn't accept `path` + `cause`, surface as a blocker") was wrong on both counts — it doesn't, and adding one would break the Phase 0 invariant.

Additionally, the draft's depth-cap test used **straight bracket-nesting** (`"a: " + "[" * 70 + "1" + "]" * 70`), which CSafeLoader's tokenizer rejects with `ScannerError` *before* the post-parse depth walker runs — that surfaces as `MalformedYAMLError`, not `DepthCapExceeded`. The canonical billion-laughs vector for `pnpm-lock.yaml` (per arch §"Edge cases" row 1 and §"Scenarios" #3) is **YAML alias amplification** — an anchor chain that the `id()`-memoized walker in `safe_yaml.load` catches as a logical-depth violation. The hardened test uses the anchor-chain shape so it exercises the load-bearing defense from S1-03, not pyyaml's tokenizer.

Twelve harden-tier additions: explicit AC for the `__cause__` chain (`isinstance(exc.__cause__, MalformedYAMLError)`), explicit AC for `str(path) in exc.args[0]` (downstream `WarningId` recovery per ADR-0007), parametrized markers-only-negative test (no `.path`, no `.cap`, no `.cause`, no `.detail`, no `.warning_id`), size-cap test moved to `os.fstat` monkey-patching (avoids the 60 MB tmpfs write — Rule 2), symlink-passthrough test added, top-level-non-mapping translation made explicit (`MalformedYAMLError` → `MalformedLockfileError`), multi-document YAML treated as malformed, `total=False` semantics pinned by a v6-shape fixture (omits `snapshots`) and a v9-shape fixture (includes it), module constants typed `Final[int]`, `__all__ = ["PnpmLock", "parse"]` declared, dead `FIXTURE_DIR` reference removed, and an architectural test `test_pnpm_module_does_not_reference_sibling_parsers` that pins CLAUDE.md "Extension by addition" — adding `_bun.py` later requires zero edits to `_pnpm.py`.

Design-pattern resolutions (DP1, DP7) recorded in `Notes for the implementer` rather than as ACs, because the rule of three is not yet crossed in S3-01: only the first of three sibling parsers exists. The shared `_translate(path, *, cause)` helper is deferred to S3-03's land time (third concrete consumer = rule-of-three threshold per Rule 2). Premature extraction in S3-01 would create a kernel S3-02 inherits silently and bias the trio toward an abstraction the third consumer might disprefer.

No `NEEDS RESEARCH` findings; Stage 3 skipped. Every gap is answerable from S1-02 and S1-03 hardened stories, the Phase 0 markers contract pinned by `tests/unit/test_errors.py`, the arch design, and ADR-0007/0008/0009.

## Context Brief (Stage 1)

- **Goal as written:** Ship `src/codegenie/probes/_lockfiles/_pnpm.py` as a thin `safe_yaml.load` wrapper returning a `PnpmLock` `TypedDict`.
- **Phase exit criteria touched:**
  - Arch §"Component design" #9 — interface, ~250 ms p50 budget for ~5 MB pnpm-lock.yaml.
  - Arch §"Component design" #4 — `NodeManifestProbe` (S3-05) is the caller; lockfile is in `declared_inputs`.
  - Arch §"Component design" #8 — `safe_yaml.load(path, *, max_bytes, max_depth=64)` contract.
  - Arch §"Edge cases" row 1 — billion-laughs `pnpm-lock.yaml` → `DepthCapExceeded`.
  - Arch §"Scenarios" #3 — billion-laughs end-to-end flow via the `id()`-memoized walker.
  - ADR-0008 — in-process caps replace per-probe sandbox.
  - ADR-0009 — `CSafeLoader` only; no `ruamel.yaml`/new C-extension.
  - ADR-0007 — `WarningId` constructed at the catch site from `exc.args[0]`, not embedded on the exception class.
- **Phase 0 contract (load-bearing):**
  - `tests/unit/test_errors.py::test_subclasses_are_markers_only` — `cls.__init__ is e.CodegenieError.__init__`; class-dict allowlist.
  - `tests/unit/test_errors.py::test_phase1_subclasses_accept_message_arg_and_expose_args0` — parametrized over every Phase 1 marker (incl. `MalformedLockfileError`); asserts `not hasattr(exc, "path" | "cap" | "detail" | "warning_id")`.
- **Existing code already on disk:**
  - `src/codegenie/parsers/safe_yaml.py` from S1-03 — raises positional-only markers; `f"{path}: {type(exc).__name__}: {exc}"` is the established message format.
  - `src/codegenie/errors.py` — `MalformedLockfileError` is a marker subclass with no `__init__`.
- **Validation precedents (the marker discipline already settled):**
  - `_validation/S1-02-safe-json-parser.md` — first kwargs-on-markers correction; introduced `f"{path}: {detail}"` format.
  - `_validation/S1-03-safe-yaml-parser.md` — added `from cause` chaining; alias-amplification mutation surfaced.
- **Open ambiguities surfaced (resolved in hardened story):**
  1. Implementation-outline step 4's "if `MalformedLockfileError` doesn't accept `path` + `cause` kwargs, surface as a blocker" — **resolved**: the contract is settled, the hardened story prescribes the positional-message form unconditionally and deletes the step.
  2. `_lockfiles/__init__.py` "may be empty or re-export" — **resolved**: docstring + `__all__: list[str] = []`. Re-exports added incrementally by S3-02 / S3-03.
  3. Whether the depth-cap test should use the canonical alias-bomb fixture from S1-03 or invent a new shape — **resolved**: use the alias-chain pattern (matches arch §"Edge cases" + arch §"Scenarios" #3).

## Stage 2 — critic reports (synthesized; parallel fan-out omitted per token economy)

The S1-02/S1-03 mutation tables already establish the standard set of failure modes for thin chokepoint parsers; only the S3-01-specific deltas (TypedDict variance, three-sibling family shape, single-vs-multi-document scope) required first-principles analysis. All four critics' findings are below.

### Coverage (verdict: COVERAGE-HARDEN)

| # | Severity | Finding |
|---|---|---|
| CV1 | **block** | AC prescribes `MalformedLockfileError(path=path, cause=e)` (kwargs) and test asserts `exc.value.path == lockfile`. Phase 0 invariant + S1-01 parametrized tests make this impossible to satisfy. |
| CV2 | **block** | Implementation outline step 4 ("surface in PR body if `MalformedLockfileError` doesn't accept `path + cause`") frames a settled question as open. The hardened story must prescribe positional-message form unconditionally. |
| CV3 | harden | No AC for `__cause__` chain — dropping `from cause` would pass every existing test. |
| CV4 | harden | No AC for `str(path) in exc.args[0]` — `WarningId` reconstruction in `NodeManifestProbe` (per ADR-0007) needs the path recoverable from the message. |
| CV5 | harden | No AC for `SymlinkRefusedError` passthrough. The story claims it re-raises unchanged but no test asserts it. |
| CV6 | harden | No AC for `SizeCapExceeded` / `DepthCapExceeded` passthrough as distinct exception types (could be caught and swallowed). |
| CV7 | harden | No AC for top-level non-mapping translation (a YAML list at top level surfaces as `MalformedYAMLError` from `safe_yaml.load`; the story doesn't make the translation explicit). |
| CV8 | harden | No AC for multi-document YAML behavior (`safe_yaml.load` rejects multi-doc input; the story chooses `load` over `load_all` but doesn't pin the multi-doc-malformed behavior). |
| CV9 | harden | `_lockfiles/__init__.py` "may be empty or re-export" — needs concrete content for the red/green commit boundary. |
| CV10 | harden | Module constants not declared `Final[int]` — mypy --strict would not flag a future mutation. |
| CV11 | harden | `__all__` not declared on `_pnpm.py` — leaks `cast`, `Any`, `TypedDict`, `safe_yaml`, `MalformedYAMLError` as public-looking names. |
| CV12 | harden | No AC for extension-by-addition (CLAUDE.md load-bearing commitment) — adding `_bun.py` could silently introduce a sibling-import. |

### Test Quality (verdict: TESTS-BLOCK)

Mutation analysis (twelve plausible wrong implementations):

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| 1 | `MalformedLockfileError(path=..., cause=...)` (kwargs) | **No** — TypeError at construction; test never reaches assertion | **block** |
| 2 | Drop `from cause` — loses `__cause__` chain | **No** — no AC, no test | harden |
| 3 | `except Exception as cause: raise MalformedLockfileError(...)` — swallows typed exceptions | **No** — would translate `SizeCapExceeded` to `MalformedLockfileError`; draft's size-cap test expects `SizeCapExceeded`, so it would catch this mutation; ✓ caught | OK |
| 4 | Build message as `str(cause)` without path | **No** — no path-in-message AC | harden |
| 5 | Drop `O_NOFOLLOW` (inherited from `safe_yaml`) — symlink follows | **No** — draft has no symlink test | harden |
| 6 | Use `safe_yaml.load_all` (multi-doc) and return `next()` | **No** — happy-path content is single-doc; would pass silently | harden |
| 7 | `total=True` on `PnpmLock` — v6 (no `snapshots`) callers would need to default | **No** at runtime; mypy --strict in CI would surface — but only the v9 fixture is tested | harden |
| 8 | Use bracket-nesting in depth-cap test (the draft's actual approach) | **N/A** — the test itself is broken (surfaces as `MalformedYAMLError` from `ScannerError`, not `DepthCapExceeded`); the canonical alias-bomb is needed | **block** (test bug) |
| 9 | Walker has no `id()` memoization (alias amplification hangs) | **No** — without the alias-bomb test, this is invisible at S3-01; relies on S1-03's hardening, but the test must exercise it from the lockfile path | harden |
| 10 | Schema-validate the lockfile inside `parse` (out-of-scope behavior added) | **No** — Notes say don't, but no negative test | nit |
| 11 | Add `MalformedLockfileError.__init__(self, *, path, cause)` "for convenience" | **No** — no test of the marker discipline at construction site | harden |
| 12 | Sibling-import `_npm` from `_pnpm.py` | **No** — no test pinning extension-by-addition | harden |

### Consistency (verdict: CONSISTENCY-BLOCK)

| # | Severity | Finding |
|---|---|---|
| CN1 | **block** | `MalformedLockfileError(path=path, cause=e)` violates `test_subclasses_are_markers_only` (Phase 0) and `test_phase1_subclasses_accept_message_arg_and_expose_args0` (S1-01). Same defect S1-02 and S1-03 hardenings already corrected. |
| CN2 | **block** | `assert exc.value.path == lockfile` (lines 89, 103) — markers expose no `.path`. Must assert via `str(exc.value)` / `args[0]`. |
| CN3 | harden | Implementation-outline step 4 frames the kwarg question as a "blocker to surface". The contract is settled; the hardened story prescribes positional unconditionally. |
| CN4 | harden | Depth-cap test uses bracket-nesting (`"a: " + "[" * 70 + "1" + "]" * 70`). CSafeLoader's tokenizer raises `ScannerError` (= `MalformedYAMLError` from `safe_yaml.load`) before the post-parse walker runs — depth cap never fires. Test as written would fail because `pytest.raises(DepthCapExceeded)` never sees the exception. Use the alias-chain shape from arch §"Scenarios" #3 / S1-03's canonical billion-laughs fixture. |
| CN5 | harden | Test file references `FIXTURE_DIR = Path(__file__).parent / "fixtures" / "_pnpm"` but never uses it (all four tests use `tmp_path`). Dead reference; delete. |
| CN6 | nit | Module constants `PNPM_LOCKFILE_MAX_BYTES` not declared `Final` — S1-03 precedent uses `Final[str]` for `_PARSER_KIND`. |
| CN7 | nit | `_lockfiles/__init__.py` is described as "may be empty or re-export" — needs concrete content for the red/green commit boundary. |
| CN8 | harden | The two notes — "If `MalformedLockfileError.__init__` doesn't accept `path + cause` kwargs ... surface as a blocker" + "MalformedLockfileError carries `path` per S1-01's error-extension contract; add the constructor argument if missing" — both invert the actual contract. S1-01 froze markers as positional-only; the hardened story corrects both. |

### Design Patterns (verdict: DESIGN-HARDEN)

| # | Severity | Finding |
|---|---|---|
| DP1 | nit (resolved as deferral) | Shared `_translate(path, *, cause)` helper across pnpm/npm/yarn — opportunity exists but **the rule of three is not yet crossed in S3-01**. Recommendation recorded in Notes for the implementer; extraction deferred to S3-03's land time. Rule 2 governs: three similar lines is better than premature abstraction. |
| DP2 | harden | `total=False` on `PnpmLock` is load-bearing for pnpm v6 vs v9 variance. Hardened story makes this explicit + pins via v6-fixture test (`snapshots` not in result) AND v9-fixture test. |
| DP3 | nit | A `Literal["pnpm"]` discriminator could surface at module level for downstream `WarningId` construction. Deferred — consumer constructs the ID per ADR-0007; YAGNI. |
| DP4 | harden | Module constants need `Final[int]` typing. |
| DP5 | harden | Functional-core / imperative-shell split is mostly clean (parse is I/O, cast is pure). Surface in Notes so future maintainers don't smuggle validation into the parser layer. |
| DP6 | nit | Tagged-union `Result[PnpmLock, LockfileParseError]` opportunity — deferred (exceptions are the established pattern; adopting Result here would require `NodeManifestProbe` and all three siblings to adopt it). |
| DP7 | **harden** | Open/Closed at the family level — adding `_bun.py` must require zero edits to `_pnpm.py`. **Promoted to AC-12** with an architectural test (source introspection) because it's a load-bearing CLAUDE.md commitment and the test cost is one `inspect.getsource()` call. |
| DP8 | nit | `__all__` declaration provides a clean public-API surface for the module; promoted to AC-2. |

### Story-smells scan

- ✗ "May be empty or re-export" (under-specified) — corrected to concrete `__all__: list[str] = []`.
- ✗ "Surface as a blocker if X" where X is already settled (false ambiguity) — implementation-outline step 4 deleted.
- ✗ Dead reference (`FIXTURE_DIR` declared, never used) — deleted.
- ✓ TDD plan distinguishes intent from behavior via per-test docstring naming the mutation caught (Rule 9 supported).
- ✗ Test prescribes 60 MB byte-write — replaced with `os.fstat` monkey-patch (Rule 2).
- ✗ Test prescribes wrong vector for the named edge case (bracket-nesting vs alias amplification) — corrected.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap traces to:

- Phase 0 `errors.py` contract (frozen, tested by parametrized markers-only tests).
- S1-02 + S1-03 hardened stories (established positional-message + `from cause` precedent).
- Arch §"Edge cases" row 1 + §"Scenarios" #3 (canonical billion-laughs vector for YAML — alias amplification, not bracket-nesting).
- CLAUDE.md "Extension by addition" load-bearing commitment.
- Standard CSafeLoader documentation (tokenizer raises `ScannerError` before the post-parse depth walker runs).

## Stage 4 — Synthesizer resolution

### Conflict resolution

No conflicts among the four critics — every finding compounds in the same direction (positional-message marker, alias-bomb depth test, extension-by-addition guard, fast size-cap monkey-patch). Consistency dominates (CN1/CN2/CN4 are blocks); Coverage and Test-Quality findings layer onto the corrected base. Design-Patterns DP7 promoted to AC-12; DP1 deferred to S3-03 per Rule 2.

### Edits applied (before / after)

**Status field:**
- Before: `**Status:** Ready`
- After: `**Status:** Ready (HARDENED)` + new `Validation notes` block summarizing the corrections.

**Depends on:**
- Before: `S1-05 (catalogs + safe_yaml already loaded by it transitively)` — S1-05 is the catalogs story, which is unrelated to lockfile parsing.
- After: `S1-03 (safe_yaml.load), S1-01 (Phase 1 marker exceptions)` — direct dependencies named.

**ADRs honored:**
- Before: ADR-0008, ADR-0009.
- After: ADR-0008, ADR-0009, ADR-0007 (`WarningId` construction at catch site — the marker contract this story honors).

**Acceptance criteria:**
- Before: 7 unnumbered checkboxes; one kwargs-on-markers block; one missing-cause-chain gap; one bracket-nesting depth-cap defect; no extension-by-addition AC.
- After: 15 numbered ACs, each traceable to one or more TDD-plan tests. AC-1 / AC-2 pin module shape; AC-3 pins cap constants; AC-4 pins three passthrough markers; AC-5 / AC-7 / AC-8 pin malformed-YAML translation + `__cause__` chain + path-in-args[0]; AC-6 / AC-15 pin marker discipline; AC-9 pins `total=False`; AC-10 / AC-11 pin non-mapping / multi-doc translation; AC-12 pins extension-by-addition (architectural test); AC-13 pins toolchain green; AC-14 pins TDD discipline.

**TDD plan:**
- Before: 4 tests (happy path + 3 typed failures) with kwargs-on-markers assertions and the bracket-nesting depth-cap defect.
- After: 8 named tests, each with a docstring keying it to its AC(s) and naming the mutation it catches:
  1. `test_parse_happy_path_v9_returns_typed_dict_shape` (AC-3/9/14)
  2. `test_parse_happy_path_v6_missing_snapshots_still_parses` (AC-9 — pins `total=False`)
  3. `test_parse_oversized_file_reraises_size_cap` (AC-4; `os.fstat` monkey-patch — no 60 MB write)
  4. `test_parse_yaml_alias_amplification_reraises_depth_cap` (AC-4; canonical billion-laughs)
  5. `test_parse_symlink_at_final_component_reraises_symlink_refused` (AC-4)
  6. `test_parse_malformed_yaml_raises_malformed_lockfile_with_cause_chain` (AC-5/7)
  7. `test_parse_malformed_yaml_message_contains_path` (AC-8)
  8. `test_parse_top_level_non_mapping_raises_malformed_lockfile` (AC-10)
  9. `test_raised_marker_has_no_instance_attributes` (AC-6/15; parametrized markers-only-negative)
  10. `test_parse_multi_document_yaml_translates_to_malformed_lockfile` (AC-11)
  11. `test_pnpm_module_does_not_reference_sibling_parsers` (AC-12; CLAUDE.md "Extension by addition")

**Implementation outline:**
- Before: step 4 said "Confirm `MalformedLockfileError` carries `path` per S1-01's error-extension contract; add the constructor argument if missing (surface in PR body if so)" — wrong on both counts; deleted. New step 4 names the test-module package marker + TDD plan.
- Now prescribes `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause` directly; module constants typed `Final[int]`; `__all__ = ["PnpmLock", "parse"]`.

**Notes for the implementer:**
- Before: 6 bullets, one of which ("If `MalformedLockfileError.__init__` doesn't accept `path` + `cause` keyword args per S1-01's contract, surface that as a blocker") inverts the contract.
- After: 10 bullets — corrects the marker discipline note (Note 3), adds the alias-amplification rationale (Note 5), adds the rule-of-three deferral for the shared `_translate` helper (Note 7), adds the Open/Closed-at-family-level commitment (Note 8), adds the functional-core / imperative-shell rationale for `cast(PnpmLock, raw)` (Note 9), explains `__all__` (Note 10).

## Verdict: **HARDENED**

The story is now ready for `phase-story-executor`. All ACs are individually verifiable; the TDD plan's eight named tests collectively cover the goal under mutation; the marker discipline is settled and matches S1-01/S1-02/S1-03 precedents; the extension-by-addition commitment is pinned via an architectural test; and the design-pattern opportunity (shared `_translate` helper) is correctly deferred to S3-03 per Rule 2.

## Follow-up obligations carried forward

- **S3-02** (npm-lockfile-parser): inherits the same marker-construction discipline + cap constants + `__all__` + `_lockfiles/__init__.py` stays inert. **Do NOT extract a shared `_translate` helper yet** — wait for S3-03.
- **S3-03** (yarn-lockfile-parser): rule-of-three threshold. Evaluate extracting `_translate(path, *, cause)` to `_lockfiles/__init__.py` or `parsers/_lockfile_io.py` once all three are visible. If extracted, AC-12's "no sibling import" guard in S3-01 stays satisfied because the helper lives in the package `__init__`, not in a sibling module.
- **S3-05** (`NodeManifestProbe`): caller; constructs `WarningId` per ADR-0007 from `exc.args[0]` for each typed exception. The path-in-message contract (AC-8) is the load-bearing handoff.
