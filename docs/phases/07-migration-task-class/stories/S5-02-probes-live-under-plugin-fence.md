# Story S5-02 — Plugin-directory probe-placement fence

**Step:** Step 5 — Phase 7 byte-edit allowlist fence + import-linter contracts + `PLUGINS.lock`
**Status:** HARDENED (phase-story-validator, 2026-08-14)
**Effort:** S
**Depends on:** S5-01 (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py` is in place — this fence is a sibling under `tests/fence/` and inherits the same Phase 3 ADR-0011 honest-framing posture).
**ADRs honored:** Phase 7 ADR-0005 (probes live under `plugins/distroless-migration--node--npm/probes/`, not `src/codegenie/probes/` — verbatim source); Phase 7 ADR-0009 (this fence file is itself under `tests/fence/` and is out of scope for the byte-edit allowlist); Phase 3 ADR-0011 (`0011-honest-framing-capability-sandboxedpath-pluginslock.md` — this fence is audit + lint, not runtime; the docstring must embed the framing); production ADR-0031 (plugin architecture — every plugin contributes its own `probes/`, `adapters/`, `recipes/`, `subgraph/`); production ADR-0007 (probe contract frozen — the placement does not affect the ABC, which lives at `src/codegenie/probes/base.py`).

## Validation notes

**Validator:** `phase-story-validator` (four-critic parallel pipeline + synthesizer).
**Report:** [`_validation/S5-02-probes-live-under-plugin-fence.md`](_validation/S5-02-probes-live-under-plugin-fence.md).
**Verdict:** HARDENED — critics surfaced eight block-severity findings (three consistency, two coverage, two test-quality collapsing into one, and two design-patterns). All were reconciled and edited in place. The story is now ready for `phase-story-executor`.

Load-bearing edits (see full report for the complete list):

1. **`default_registry.all_probes()` replaces `_REGISTRY`** (consistency-1). The module-level `_REGISTRY` symbol does not exist in `src/codegenie/probes/registry.py`; the public API is `default_registry.all_probes()`, and every other test in the codebase that reads the probe registry uses it (see `tests/bench/test_cache_hit_dispatch.py`, `tests/fixtures/_shape_test_kernel.py`). AC-4 and Implementation outline §5 rewritten.
2. **`Path.resolve().is_relative_to(...)` replaces `str.startswith("src/codegenie/probes/")`** (coverage-1 + test-3 + design-6, unanimous). The original comparison against a relative-path string is a guaranteed silent no-op because `inspect.getsourcefile` returns an absolute path — the walker would always return "OK" even after a real Phase 7 violation shipped. Python ≥ 3.11 (`pyproject.toml § requires-python = ">=3.11"`) makes `is_relative_to` available.
3. **`Violation` frozen dataclass replaces `list[tuple[Path, int, str]]`** (design-2). Matches the sibling family (`_capability_fence.Violation`, `_phase3_fence.Violation`) — Rule 11 (match convention) and Rule 9 (typed intent).
4. **`ExpectedProbe` frozen dataclass replaces `tuple[tuple[str, Path], ...]`** (design-3). Original shape permitted cross-contaminated rows a typo would slip through (`("BaseImageProbe", Path(".../shell_trace_probe.py"))`); dataclass wrapping makes the illegal state unrepresentable.
5. **`_FORBIDDEN_PHASE7_PROBE_NAMES` derives from `_EXPECTED_PHASE7_PROBE_LOCATIONS`** (design-4). Single source of truth; adding a third probe to the tuple auto-extends the negative fence.
6. **Import re-exports and alias assignments in the core tree are covered by AC-3** (coverage-2). The original AC-3 walked `ast.ClassDef` only, so a `from plugins... import BaseImageProbe` in `src/codegenie/probes/__init__.py`, or a module-level `BaseImageProbe = _RealClass`, would reintroduce the forbidden name and slip past. AC-3 extended to reject `ast.ImportFrom`/`ast.Import`/`ast.Assign`/`ast.AnnAssign` that bind a forbidden name in the core tree; AC-5.f and AC-5.g plant both shapes.
7. **`_CORE_PROBE_ROOT` floor guard** (test-1). Mirrors `test_capability_fence.py::test_floor_guard_every_root_exists_and_non_empty` — a mutation that renames `_CORE_PROBE_ROOT` to a typo, or a future deletion of `src/codegenie/probes/`, currently silent-greens the fence. New AC-1.b closes it.
8. **Nested-subdirectory planted case + `NodeVisitor.generic_visit` discipline** (test-2 + coverage-5). Original AC-5.a planted a file at `tmp_path` root; a non-recursive walker (`os.listdir` mutation) would still pass. New AC-5.c plants under `tmp_path/probes/layer_c/planted.py` to prove recursion; Implementation outline §2 mandates `generic_visit` inside `visit_ClassDef` so nested class defs are traversed.
9. **`pytest.mark.xfail(condition=..., strict=True)` with a computed predicate** (design-8 + test-4 + coverage-4). Replaces the manual "S7-01 implementer removes the marker" prose hand-off with a runtime-computed condition that flips automatically when Phase-7 probes register. The skip-when-empty alternative is dropped (mixing `pytest.skip()` with strict-xfail is a footgun).
10. **`inspect.getsourcefile(cls) is None` FAILS loudly** (coverage-8). Original Notes said "treat as a soft warning (skip with a loud reason)"; that lets a `types.new_class`-generated or `type()`-built probe slip through — exactly the malicious shape the fence must reject. AC-4 now fails on unresolvable source.
11. **Bidirectional plugin-directory invariant** (coverage-3). Original AC-4 filtered `applies_to_tasks != ["*"]`. A task-class-specific probe that *forgets* to set the field defaults to `["*"]` and slips past. AC-4.b + AC-4.c add the bidirectional check: task-class-specific ⇒ under a `plugins/*/probes/` subtree; wildcard ⇒ under `src/codegenie/probes/`.
12. **Monotonicity property test** (test-7). AC-11 — walker returns exactly N+1 violations after planting one file and exactly N after removing it; kills off-by-one and dedup-swallowing mutants. Rule 2 satisfied because the plant/unplant machinery is already in AC-5.
13. **`_attempts/S5-02.md` evidence schema formalized** (test-9). Mirrors S5-01's `AC-5.i evidence-check test` — an in-suite parser verifies the required headings and SHA rows exist, so the block cannot be omitted under time pressure.

Findings deferred (recorded in the report; not edited into the story):
- **`TaskId` newtype** (design-5) — does not yet exist in `src/codegenie/types/identifiers.py`; Rule 2 says defer. Notes bullet added.
- **`iter_probes()` public API** (design-7) — coupling smell recorded as a Notes bullet for a follow-up story; refactoring the registry surface is out of scope here.
- **Vestigial filename `test_provenance_primitive_in_plugin_directory.py`** (consistency-2) — ADR-0005 §Consequences uses the name verbatim (a Phase-3 copy-paste artifact). Rule 11 says match the source; renaming requires an ADR amendment. Notes bullet added.
- **`# xfail-until: story-S7-01` mechanical marker** (design-9) — Rule 2 over-engineering with N=1; rejected.
- **Refactor to shared AST-walker ABC** (design-1) — refused for the same Rule 2 reason S5-01 refused `Fence` ABC. A `# duplicate-of:` comment is added instead.

## Context

Phase 7 ADR-0005 §Decision is unambiguous: `BaseImageProbe` lives at `plugins/distroless-migration--node--npm/probes/base_image_probe.py` and `ShellInvocationTraceProbe` lives at `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py`. Neither belongs under `src/codegenie/probes/`. The best-practices lens originally proposed `src/codegenie/probes/layer_c/base_image_probe.py` + `src/codegenie/probes/layer_d/shell_trace_probe.py`; the critic landed BP-5 against this ("entrenches a precedent that future task classes' probes go in core"); the synthesis (`final-design.md §Lens summary §5`, score 15/15) locked plugin-internal placement.

The byte-edit allowlist fence (S5-01) protects against unauthorized byte-edits to *existing* Phase 0–6.5 files. It does NOT protect against *new* probe files being added to `src/codegenie/probes/` — because adding a net-new file under `src/codegenie/probes/layer_c/` is technically additive (the file grows the directory rather than mutating an existing file). Without a structural fence that asserts the placement policy, a future PR could quietly land a task-class-specific probe under the core probe tree and re-open the precedent BP-5 closed.

This story plants a small AST-walk + filesystem-walk fence that:
1. Asserts `BaseImageProbe` and `ShellInvocationTraceProbe` Python classes are defined under `plugins/distroless-migration--node--npm/probes/`, NOT under `src/codegenie/probes/`.
2. Asserts no Python file under `src/codegenie/probes/` defines, imports, or aliases a class named `BaseImageProbe` or `ShellInvocationTraceProbe` — so re-exports (`from plugins... import BaseImageProbe`) and alias assignments (`BaseImageProbe = _Real`) cannot smuggle the name back into the core namespace.
3. Generalizes (slightly): a meta-test enumerates every class in `default_registry.all_probes()` and asserts the bidirectional invariant — task-class-specific probes (`applies_to_tasks != ["*"]`) live under a `plugins/*/probes/` subtree; wildcard probes (`applies_to_tasks == ["*"]`) live under `src/codegenie/probes/`. This is the load-bearing assertion that future task-class plugins follow the same shape *and* that a "forgot to set `applies_to_tasks`" bug is caught loudly (the plugin-authored probe defaults to `["*"]` and would otherwise slip past).

The fence is small and mechanical; it complements (does not replace) S5-01's byte-edit fence and S5-03's import-linter contracts.

**Honest framing (Phase 3 ADR-0011 carry-forward):** like every other fence, this is audit + lint. CODEOWNERS on `tests/fence/` is the social anchor; a determined PR editing both the fence and the violation defeats it. Acceptable.

## References — where to look

- **Phase ADR — primary source of truth:**
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` §Decision + §Consequences — names the file `tests/fence/test_provenance_primitive_in_plugin_directory.py` (name is vestigial — see Notes) and AST-asserts the two new probes live under `plugins/distroless-migration--node--npm/probes/`, not under `src/codegenie/probes/`.
- **Cross-cutting ADRs:**
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — this fence file is under `tests/fence/` and falls outside the byte-edit allowlist scope. Adding it is additive (new test file).
  - `../../03-vuln-deterministic-recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — the "audit + lint, not runtime" framing this fence inherits.
  - `production ADR-0031` (plugin architecture) — every plugin contributes its own `probes/`.
  - `production ADR-0007` (probe contract frozen) — the ABC lives at `src/codegenie/probes/base.py`; this fence does NOT enforce ABC-conformance (that's `tests/unit/test_probe_contract.py`'s job), only *placement*.
- **Architecture:**
  - `../phase-arch-design.md §Component design §8 (BaseImageProbe), §9 (ShellInvocationTraceProbe)` — names the file paths.
  - `../phase-arch-design.md §Testing strategy §Fence / structural` — names this fence file.
- **Precedent fence files (style):**
  - `tests/fence/test_capability_fence.py` — live-scan + planted-positive using the SAME `find_violations(roots=[...])` function; frozen `Violation` dataclass; floor-guard-every-root; per-class parametrized planted-positive. **This is the closest sibling; mirror its shape closely.**
  - `tests/fence/test_no_any_in_plugin_surface.py` — `walk_any_annotations` + `Violation` frozen dataclass + per-shape parametrize matrix.
  - `tests/fence/test_plugin_protocol_frozen.py` — AST-walks plugin contract surfaces; mirror the structural-AST visitor pattern.
- **Existing code:**
  - `src/codegenie/probes/registry.py` — `@register_probe` decorator + `default_registry: Registry` process-wide instance + `default_registry.all_probes() -> tuple[type[Probe], ...]` public iteration API (used by `tests/bench/test_cache_hit_dispatch.py:32` and `tests/fixtures/_shape_test_kernel.py:273-275`).
  - `src/codegenie/probes/base.py:78` — `applies_to_tasks: list[str]` with `["*"]` = "match any" sentinel.
  - `src/codegenie/probes/__init__.py` — explicit-import collection point. A new line for the Phase 7 plugin probes would land here under S8-03's row 10 of the byte-edit allowlist; this fence does NOT depend on that wiring (it works on filesystem paths + AST, not on import discovery).
- **Sibling stories (verbatim filenames must match):**
  - `S7-01-base-image-probe.md §Goal / AC-1` — `plugins/distroless-migration--node--npm/probes/base_image_probe.py`.
  - `S7-02-shell-invocation-trace-probe.md §Goal / AC-1` — `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py`.

## Goal

Land `tests/fence/test_provenance_primitive_in_plugin_directory.py` (the name comes from ADR-0005 §Consequences verbatim — see Notes for why the vestigial name is preserved) so any PR that places a Phase-7 (or any task-class-specific) probe under `src/codegenie/probes/` — whether by defining a `class`, re-exporting an `import`, or aliasing an assignment — fails CI.

## Acceptance criteria

**Filesystem assertion + meta-liveness (AC-1)**
- [ ] **AC-1** `tests/fence/test_provenance_primitive_in_plugin_directory.py` exists; module docstring (a) cites Phase 7 ADR-0005, (b) embeds Phase 3 ADR-0011 honest-framing language, (c) names the two probes by name (`BaseImageProbe`, `ShellInvocationTraceProbe`) and their expected locations (`plugins/distroless-migration--node--npm/probes/base_image_probe.py` and `.../shell_trace_probe.py`). A meta-test scans for these strings.
- [ ] **AC-1.b** **Walker-liveness meta-check** (kills "empty walker body" and "removed asserts" mutations): a sibling meta-test asserts the fence file's source contains the identifiers `_CORE_PROBE_ROOT`, `_EXPECTED_PHASE7_PROBE_LOCATIONS`, `find_forbidden_class_definitions`, `find_forbidden_name_bindings`, and the class-name strings `"BaseImageProbe"` + `"ShellInvocationTraceProbe"`. A future PR that guts the fence body (comments out asserts, renames helpers, deletes the constants) fails loudly.
- [ ] **AC-1.c** **Floor guard** (mirrors `test_capability_fence.py::test_floor_guard_every_root_exists_and_non_empty`): a test asserts `_CORE_PROBE_ROOT.is_dir()` is True AND that the directory contains at least one non-`__init__.py` `*.py` file. A future deletion of `src/codegenie/probes/` or a typo in `_CORE_PROBE_ROOT` currently silent-greens the fence; this guard refuses to proceed.

**Positive placement assertions (AC-2)**
- [ ] **AC-2** Parametrized test `test_probe_class_lives_at_expected_path` over `_EXPECTED_PHASE7_PROBE_LOCATIONS` (a `tuple[ExpectedProbe, ...]` of frozen dataclasses):
  - Reads the file at `expected.expected_path`.
  - AST-parses it.
  - Walks `ast.ClassDef` nodes (via `NodeVisitor` with explicit `generic_visit` to reach nested defs) and asserts at least one node has `name == expected.class_name`.
  - Fails loudly if the file does not exist (message names the expected path AND Phase 7 ADR-0005).
  - **Xfail transition is data-driven, not manual**: the parametrized test is decorated with `@pytest.mark.xfail(condition=_no_phase7_probes_registered(), strict=True, reason="Phase 7 probes land in S7-01 / S7-02")`. `_no_phase7_probes_registered()` inspects `default_registry.all_probes()` at collection time and returns `True` iff none of the entries has `applies_to_tasks == ["distroless-migration"]`. When S7-01 / S7-02 register their probes, the condition flips to `False`, the xfail marker becomes inactive, and the test asserts positively. No manual marker-removal hand-off; a wrong-location landing by S7-01 (probe at `src/codegenie/probes/base_image_probe.py`) still fails AC-3.

**Negative core-tree assertions (AC-3) — the load-bearing fence**
- [ ] **AC-3** `test_no_phase7_class_definitions_under_core_tree`:
  - Walks every `*.py` under `_CORE_PROBE_ROOT` recursively (excluding `__pycache__/`), following the same DI shape as `test_capability_fence.py::find_violations(roots=[...])`.
  - AST-parses each file; runs `find_forbidden_class_definitions(roots=[_CORE_PROBE_ROOT], forbidden_names=_FORBIDDEN_PHASE7_PROBE_NAMES)`.
  - Asserts the returned `list[Violation]` is empty.
  - On hit: failure message names the offending `(file, line, class_name)` tuples AND Phase 7 ADR-0005.
- [ ] **AC-3.a** Per-probe parametrized variant (so failures attribute to a specific probe): two parameter rows, one per Phase 7 probe class name.
- [ ] **AC-3.b** **Import/alias re-export defense** — `test_no_phase7_names_rebound_under_core_tree`: same walk, but with `find_forbidden_name_bindings(roots=[_CORE_PROBE_ROOT], forbidden_names=_FORBIDDEN_PHASE7_PROBE_NAMES)`. Rejects any `ast.ImportFrom` importing a forbidden name, any `ast.Import` with a bare or aliased forbidden name, any `ast.Assign` / `ast.AnnAssign` whose target `Name.id` is in the forbidden set. Empty list = pass.
- [ ] **AC-3.c** **Symlink normalization** — every `*.py` under `_CORE_PROBE_ROOT` is walked with `rglob("*.py")` and each hit is asserted to satisfy `path.resolve().is_relative_to(_CORE_PROBE_ROOT.resolve())` — a symlink `src/codegenie/probes/base_image_probe.py -> ../../../plugins/.../probes/base_image_probe.py` (which would satisfy `import codegenie.probes.base_image_probe` while pointing the class definition at the plugin) fails.

**Registry-coverage assertion (AC-4) — generalizes the fence**
- [ ] **AC-4** `test_task_class_specific_probes_live_under_plugin_tree`:
  - Imports `from codegenie.probes.registry import default_registry` and iterates `default_registry.all_probes()`.
  - Filters to entries whose `applies_to_tasks != ["*"]` (task-class-specific).
  - For each, derives the source file via `inspect.getsourcefile(probe_cls)`.
  - **AC-4.a** If `inspect.getsourcefile(cls) is None` for any probe, the fence FAILS with a message citing "unresolvable source is treated as a hostile shape per ADR-0005 §Consequences" — NOT skip.
  - Asserts `Path(source).resolve().is_relative_to(_CORE_PROBE_ROOT.resolve())` is `False` (source is NOT under the core probe tree).
  - On hit: failure message names the probe class + the offending source path + Phase 7 ADR-0005 + production ADR-0031.
  - **AC-4.b** **Bidirectional invariant** — `test_wildcard_probes_live_under_core_tree`: for every entry whose `applies_to_tasks == ["*"]`, asserts the source IS under `_CORE_PROBE_ROOT.resolve()`. Catches the "forgot to set `applies_to_tasks`" bug in a plugin-authored probe (which defaults to `["*"]` and would otherwise slip past AC-4).
  - **AC-4.c** **Xfail transition is data-driven** — `@pytest.mark.xfail(condition=_no_phase7_probes_registered(), strict=True, reason="No task-class-specific probes registered pre-S7")`. `_no_phase7_probes_registered()` is the SAME predicate used by AC-2, so the flip is atomic when S7-01/S7-02 land. If the plugin loader is not yet wired at S5-02 landing time (S8-03 wires it), the condition returns `True` and the test xfails cleanly; when the wiring lands, the condition flips and the assertion runs positively.

**Planted-violation evidence (AC-5) — Rule 12 fail-loud**
Parametrized in-test planted-violation cases (use `tmp_path` + `roots=[...]` kwarg on the walker so the working tree is never mutated):
- [ ] **AC-5.a** Plant `class BaseImageProbe: pass` at `tmp_path / "planted.py"` → `find_forbidden_class_definitions(roots=[tmp_path], forbidden_names={"BaseImageProbe"})` returns exactly one `Violation`.
- [ ] **AC-5.b** Plant the same class under `tmp_path_for_plugins / "distroless-migration--node--npm/probes/decoy.py"` → the walker rooted at `_CORE_PROBE_ROOT` does NOT flag it (proves the walker is scoped to the root passed in — the plugin path is out of scope by construction).
- [ ] **AC-5.c** **Recursion proof** — plant `class ShellInvocationTraceProbe: pass` at `tmp_path / "sub" / "deeper" / "planted.py"` → the walker rooted at `tmp_path` still catches it (proves `rglob` recursion, kills any `os.listdir`-non-recursive mutation).
- [ ] **AC-5.d** **Nested-class proof** — plant `class Outer:\n    class BaseImageProbe: pass` → walker catches the nested class (proves `NodeVisitor.visit_ClassDef` calls `generic_visit`).
- [ ] **AC-5.e** **Multi-class-per-file proof** — plant `class Foo: pass\nclass BaseImageProbe: pass\nclass Bar: pass` in one file → walker returns exactly one violation with `class_name == "BaseImageProbe"` (not three; not zero; kills first-class-only and dedup-by-file mutations).
- [ ] **AC-5.f** **Import re-export proof** — plant `from x import BaseImageProbe` OR `from x import BaseImageProbe as BaseImageProbe` at `tmp_path / "reexport.py"` → `find_forbidden_name_bindings` returns exactly one violation. Also plant `import BaseImageProbe as BaseImageProbe` (bare) — same expectation.
- [ ] **AC-5.g** **Alias-assignment proof** — plant `BaseImageProbe = object` and `BaseImageProbe: type = object` at `tmp_path / "alias.py"` → `find_forbidden_name_bindings` returns two violations (one per binding shape).
- [ ] **AC-5.h** **Docstring-not-code proof** — plant a file whose docstring contains `class BaseImageProbe:` as free text (no actual `ClassDef`) → walker returns zero violations (proves AST-based, not regex — kills a mutant that swaps AST for `re.search`).
- [ ] **AC-5.i** **Symlink escape proof** — synthesize `tmp_path / "core_probes"` as a directory with a symlink `linked.py -> tmp_path / "elsewhere" / "planted.py"` whose target contains `class BaseImageProbe: pass`. AC-3.c's `resolve().is_relative_to(...)` check surfaces the symlink as a violation. (Skipped with a loud reason on filesystems that reject symlink creation.)
- [ ] **AC-5.j** **Out-of-test evidence** — on a throwaway branch, plant `class BaseImageProbe: pass` in `src/codegenie/probes/_test_planted.py`, run the fence, capture red output + SHA; remove; capture green + SHA. Recorded in `_attempts/S5-02.md` under a `### AC-5.j evidence` heading with three rows: `Before SHA:`, `Red output (excerpt):`, `After SHA + Green output (excerpt):`. A meta-test (`test_ac5j_evidence_block_present`) parses `_attempts/S5-02.md`, asserts the heading exists, and asserts each row is non-empty (mirrors S5-01's `AC-5.i evidence-check test`).

**Cross-fence integration (AC-6)**
- [ ] **AC-6** This fence does not regress S5-01 or any other Phase-7 fence: `make fence` and `make check` exit 0 after this story lands. (Passive check — S5-01's own path filter excludes `tests/`, so a new file at `tests/fence/test_provenance_primitive_in_plugin_directory.py` is out of scope for `_LOCKED_SURFACE_GLOBS` by construction. Verified by the `make check` gate in CI, not by a bespoke in-test subprocess call.)

**Wiring (AC-7 through AC-9)**
- [ ] **AC-7** `pytest tests/fence/test_provenance_primitive_in_plugin_directory.py -v` exits 0 at story landing (with AC-2 / AC-4.c xfail-conditional inactive-flipping-to-xfailed once S7-01/S7-02 register the probes).
- [ ] **AC-8** `make fence` and `make check` exit 0; no other fence regresses.
- [ ] **AC-9** `ruff check`, `ruff format --check`, `mypy --strict tests/fence/test_provenance_primitive_in_plugin_directory.py` clean. (`pyproject.toml [tool.mypy]` overrides `tests.*` with `disallow_untyped_defs = false` but keeps `strict = true` — the assertion is meaningful, not vacuous.)

**Property invariants (AC-10 + AC-11)**
- [ ] **AC-10** **Monotonicity** — `test_walker_monotonicity`: given a `tmp_path` containing N forbidden-class files, `find_forbidden_class_definitions(roots=[tmp_path], forbidden_names=...)` returns exactly N `Violation`s; after planting one additional file, exactly N+1; after removing it, exactly N. Kills off-by-one and dedup-by-file mutations for one small block of code — the plant/unplant machinery already exists in AC-5.
- [ ] **AC-11** **Idempotency** — two consecutive calls to `find_forbidden_class_definitions(...)` with the same inputs return equal `Violation` lists (in the same order). Kills hidden state / non-deterministic-glob mutants.

## Implementation outline

1. **Author the fence file** `tests/fence/test_provenance_primitive_in_plugin_directory.py`:
   - Module docstring (AC-1 strings embedded — Phase 7 ADR-0005 citation; Phase 3 ADR-0011 honest framing; the two probe names; expected paths).
   - `# duplicate-of: src/codegenie/_capability_fence.py::find_violations` header comment at the walker's home — records the Rule-2-honoring intentional copy-paste of the AST-walker shape (no shared `Fence` ABC; three walkers, three predicates).
   - `_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]` — anchor all paths off the repo root, not CWD.
   - `_CORE_PROBE_ROOT: Final[Path] = _REPO_ROOT / "src" / "codegenie" / "probes"`.

2. **Data model — illegal states unrepresentable, primitive obsession eliminated:**
   ```python
   @dataclass(frozen=True)
   class ExpectedProbe:
       class_name: str
       expected_path: Path  # relative to _REPO_ROOT

   @dataclass(frozen=True)
   class Violation:
       file: Path
       line: int
       kind: Literal["class_def", "import_from", "import_as", "assign", "ann_assign"]
       name: str

   _EXPECTED_PHASE7_PROBE_LOCATIONS: Final[tuple[ExpectedProbe, ...]] = (
       ExpectedProbe("BaseImageProbe",
                     _REPO_ROOT / "plugins/distroless-migration--node--npm/probes/base_image_probe.py"),
       ExpectedProbe("ShellInvocationTraceProbe",
                     _REPO_ROOT / "plugins/distroless-migration--node--npm/probes/shell_trace_probe.py"),
   )

   # Single source of truth — derive the forbidden-name set from the tuple.
   _FORBIDDEN_PHASE7_PROBE_NAMES: Final[frozenset[str]] = frozenset(
       p.class_name for p in _EXPECTED_PHASE7_PROBE_LOCATIONS
   )
   ```

3. **AST walker (pure functions, single-root-per-call so tests can DI `roots=[tmp_path]`):**
   - `def find_forbidden_class_definitions(*, roots: Iterable[Path], forbidden_names: frozenset[str]) -> list[Violation]` — walks each root recursively via `Path.rglob("*.py")`, AST-parses each file, walks `ast.ClassDef` via a `NodeVisitor` subclass whose `visit_ClassDef` calls `generic_visit(node)` so nested defs are reached. Returns `Violation(kind="class_def", ...)` per hit.
   - `def find_forbidden_name_bindings(*, roots: Iterable[Path], forbidden_names: frozenset[str]) -> list[Violation]` — same walk shape, different visitor: `visit_ImportFrom`, `visit_Import`, `visit_Assign`, `visit_AnnAssign`. Returns `Violation` with the appropriate `kind`.

4. **Wire AC-2** — parametrized test over `_EXPECTED_PHASE7_PROBE_LOCATIONS`. Reads each expected location, AST-parses, asserts the `ClassDef` is present. Xfail marker:
   ```python
   def _no_phase7_probes_registered() -> bool:
       from codegenie.probes.registry import default_registry
       return not any(
           list(cls.applies_to_tasks) == ["distroless-migration"]
           for cls in default_registry.all_probes()
       )

   @pytest.mark.xfail(
       condition=_no_phase7_probes_registered(),
       strict=True,
       reason="Phase 7 probes land in S7-01 / S7-02; xfail flips to pass automatically on landing.",
   )
   ```

5. **Wire AC-3 / AC-3.a / AC-3.b / AC-3.c** — `find_forbidden_class_definitions(roots=[_CORE_PROBE_ROOT], forbidden_names=_FORBIDDEN_PHASE7_PROBE_NAMES)` + `find_forbidden_name_bindings(roots=[_CORE_PROBE_ROOT], forbidden_names=_FORBIDDEN_PHASE7_PROBE_NAMES)` + symlink-safety check on every walked file (`path.resolve().is_relative_to(_CORE_PROBE_ROOT.resolve())`).

6. **Wire AC-4** — replace the story's original `_REGISTRY` import with the confirmed-public API:
   ```python
   from codegenie.probes.registry import default_registry
   ...
   for probe_cls in default_registry.all_probes():
       if list(probe_cls.applies_to_tasks) == ["*"]:
           continue  # wildcard probes handled by AC-4.b
       source = inspect.getsourcefile(probe_cls)
       if source is None:
           pytest.fail(
               f"{probe_cls.__name__}: inspect.getsourcefile returned None; "
               f"unresolvable source is a hostile shape per ADR-0005."
           )
       source_path = Path(source).resolve()
       assert not source_path.is_relative_to(_CORE_PROBE_ROOT.resolve()), (
           f"{probe_cls.__name__} (task-class-specific) lives under core probe tree at "
           f"{source_path} — Phase 7 ADR-0005 + production ADR-0031 forbid this."
       )
   ```
   Bidirectional check (AC-4.b) mirrors the shape with the inverted predicate for `applies_to_tasks == ["*"]`. Both wrapped in the shared strict-xfail-conditional decorator (AC-4.c).

7. **Plant the AC-5 violations** — in `tmp_path` for AC-5.a–i via the `roots=[...]` kwarg; on a throwaway branch for AC-5.j. Record `_attempts/S5-02.md` evidence block per the AC-5.j schema.

8. **Wire AC-10 / AC-11 property tests** — reuse the plant/unplant machinery; small in-line loops, no `hypothesis` dependency (Rule 2 — the state space is bounded and enumerable).

9. **Run `make check`** — green.

## TDD plan (red → green → refactor)

**Red:**
1. Author the fence file with AC-2 / AC-3 / AC-3.b / AC-3.c / AC-4 / AC-4.b wired but no `xfail` markers. Run `pytest tests/fence/test_provenance_primitive_in_plugin_directory.py` — expect AC-2 red (the expected probe files do not exist yet) and AC-4 red-on-emptiness (no Phase 7 probes registered yet).
2. Verify the failure messages contain Phase 7 ADR-0005 and the offending paths.
3. Plant a synthetic violation as in AC-5.a (in `tmp_path`); run the parametrized AC-5 tests directly — they catch every plant shape independently.

**Green:**
1. Add `@pytest.mark.xfail(condition=_no_phase7_probes_registered(), strict=True, reason="...")` decorator to AC-2 + AC-4 + AC-4.b — the tests pass-as-xfail while Phase 7 probes haven't registered.
2. Run `pytest tests/fence/test_provenance_primitive_in_plugin_directory.py -v` — all green.
3. Run `make check` — green.

**Refactor:**
1. Confirm `find_forbidden_class_definitions` and `find_forbidden_name_bindings` are pure module-level functions (no hidden state — AC-11 idempotency test enforces).
2. Confirm the `Violation` dataclass is frozen and hashable; confirm `ExpectedProbe` likewise.
3. Sort `_EXPECTED_PHASE7_PROBE_LOCATIONS` deterministically (alphabetical by `class_name`).
4. Confirm `ruff` / `mypy --strict` clean.

## Files to touch

- `tests/fence/test_provenance_primitive_in_plugin_directory.py` — new test file.
- `docs/phases/07-migration-task-class/stories/_attempts/S5-02-probes-live-under-plugin-fence.md` — append-only attempt log. MUST contain a `### AC-5.j evidence` heading with three non-empty rows: `Before SHA:`, `Red output (excerpt):`, `After SHA + Green output (excerpt):`. The in-suite `test_ac5j_evidence_block_present` meta-test parses this file at test time.

## Out of scope

- **ABC conformance for the new probes** — that's `tests/unit/test_probe_contract.py`'s job and is exercised by S7-05.
- **Sub-schema location** — Phase 7 ADR-0005 also says sub-schemas live under `plugins/distroless-migration--node--npm/schema/`; that's S7-03's territory.
- **`@register_probe` registration coverage** — S7-05 verifies the loader picks up the new probes; this fence only asserts file placement + name bindings.
- **Positive-shape assertion (task-class-specific probes MUST live under `plugins/<slug>/probes/`)** — deferred to Phase 8's first plugin. When the plugin tuple grows to two plugins, the shape becomes learnable and the fence gains the positive check. Today AC-4 asserts only "not core"; a probe at `/tmp/random.py` would pass.
- **Generalizing the fence to ALL future task-class plugins** — the parametrized expected-locations tuple only contains Phase 7's two probes. Phase 8+ extends this tuple via ADR amendment.
- **Cryptographic attestation** — Phase 3 ADR-0011 framing; this is lint, not signature. Deferred to Phase 11 Sigstore migration.
- **Public `iter_probes()` API on the registry** — the story uses the existing `default_registry.all_probes()`; if a future story wants to formalize an `iter_probes()` iterator (Interface Segregation), it lands as a follow-up refactor with all registry consumers migrating together.
- **`TaskId` newtype for `applies_to_tasks` sentinel** — `src/codegenie/types/identifiers.py` does not currently define one, and Rule 2 says defer. When Phase 8+ introduces `TaskId`, this fence updates in the same PR that lands the newtype.

## Notes for the implementer

- **Xfail transition is data-driven, not manual.** The xfail predicate `_no_phase7_probes_registered()` inspects `default_registry.all_probes()` at collection time and flips automatically when S7-01 / S7-02 register their probes. No manual marker-removal handshake. If S7-01 lands the probe at the wrong location (`src/codegenie/probes/base_image_probe.py`), AC-2's xfail stays xfailed (file at expected plugin path still doesn't exist) but AC-3 fires with a clear "class defined in core" message — the fence catches the wrong-location landing loudly. The predicate is intentionally narrow: it looks for `applies_to_tasks == ["distroless-migration"]`, not a generic "any task-class-specific probe" check, so Phase-8+ plugins don't accidentally silence the xfail before their own fences are wired.
- **The registry-walk in AC-4 is the future-protection.** Today it covers Phase 7's two probes; tomorrow it covers every task-class-specific probe added to the registry. The shape is data-driven: no Phase 7-specific magic, just "all probes whose `applies_to_tasks != ['*']`". If Phase 8 adds an `opentelemetry-migration` probe under `src/codegenie/probes/`, this fence catches it without any edit.
- **Bidirectional invariant (AC-4.b) catches the "forgot the field" bug.** A plugin-authored probe that forgets to set `applies_to_tasks = ["distroless-migration"]` inherits the ABC default `["*"]` — the wildcard-check then fires: "wildcard probe living outside `src/codegenie/probes/`". This is the fence's most important extension over the naïve "just check task-class-specific probes" design.
- **Anti-pattern explicitly avoided:** do NOT make this fence *also* enforce ABC conformance, registration, or sub-schema placement. Rule 2 — single-purpose, single-shape. Those are different fences with different shapes.
- **`inspect.getsourcefile` returning `None` FAILS loudly.** A probe class whose source cannot be resolved is exactly the shape a `types.new_class`- or `type()`-generated probe would take. Skipping is the wrong default; the fence rejects unresolvable sources as hostile per ADR-0005 §Consequences enforcement.
- **Path portability.** `_REPO_ROOT` is anchored on `Path(__file__).resolve().parents[2]` (not CWD). Every filesystem check uses `Path.resolve().is_relative_to(...)`, never `str.startswith("relative/path")`. This is the difference between a fence that works and a fence that silently green-flags forever — string-prefix comparison against a relative path against an absolute `inspect.getsourcefile` return value would ALWAYS return `False` and the assertion would ALWAYS pass.
- **Rule-of-three refused, not extracted.** `find_forbidden_class_definitions` / `find_forbidden_name_bindings` are the third structurally-similar AST walker (after `_phase3_fence.walk_any_annotations` and `_capability_fence.find_violations`). The three walkers differ in predicate shape, result kind, and exclusion set; a shared `Fence` ABC would compress at the wrong layer. S5-01's validation report refused `Fence` ABC on Rule 2 grounds; the same refusal applies here. The `# duplicate-of:` comment makes the discipline visible to the next reader.
- **Registry access via `default_registry.all_probes()`, not `_REGISTRY`.** The module has no `_REGISTRY` symbol; the public API is a bound method on the process-wide `default_registry` instance. Follow-up thought: if a future story wants to formalize an `iter_probes()` iterator (Interface Segregation on the Registry surface), it lands as a separate refactor with all registry consumers migrating together — not in this fence.
- **Surface conflicts (Rule 7):** if at implementation time `BaseImageProbe`'s file path in S7-01's story drifts from `base_image_probe.py` to e.g., `base_image.py`, surface the drift. The fix is an ADR amendment to ADR-0005's §Decision text + a one-row edit to `_EXPECTED_PHASE7_PROBE_LOCATIONS`. Do not silently rename.
- **Vestigial filename.** `test_provenance_primitive_in_plugin_directory.py` reads as vestigial — the content is probe placement, not vuln-provenance. It is preserved verbatim from ADR-0005 §Consequences per Rule 11 (a likely Phase-3 copy-paste artifact in the ADR itself); renaming requires an ADR-0005 amendment. Do NOT quietly rename.
- **CODEOWNERS is the social anchor.** `tests/fence/` should already be CODEOWNERS-covered transitively; verify and add if not.
