# Story S5-02 — Plugin-directory probe-placement fence

**Step:** Step 5 — Phase 7 byte-edit allowlist fence + import-linter contracts + `PLUGINS.lock`
**Status:** Ready
**Effort:** S
**Depends on:** S5-01 (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py` is in place — this fence is a sibling under `tests/fence/` and inherits the same Phase 3 ADR-0011 honest-framing posture).
**ADRs honored:** Phase 7 ADR-0005 (probes live under `plugins/distroless-migration--node--npm/probes/`, not `src/codegenie/probes/` — verbatim source); Phase 7 ADR-0009 (this fence file is itself under `tests/fence/` and is out of scope for the byte-edit allowlist); production ADR-0031 (plugin architecture — every plugin contributes its own `probes/`, `adapters/`, `recipes/`, `subgraph/`); production ADR-0007 (probe contract frozen — the placement does not affect the ABC, which lives at `src/codegenie/probes/base.py`).

## Context

Phase 7 ADR-0005 §Decision is unambiguous: `BaseImageProbe` lives at `plugins/distroless-migration--node--npm/probes/base_image_probe.py` and `ShellInvocationTraceProbe` lives at `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py`. Neither belongs under `src/codegenie/probes/`. The best-practices lens originally proposed `src/codegenie/probes/layer_c/base_image_probe.py` + `src/codegenie/probes/layer_d/shell_trace_probe.py`; the critic landed BP-5 against this ("entrenches a precedent that future task classes' probes go in core"); the synthesis (`final-design.md §Lens summary §5`, score 15/15) locked plugin-internal placement.

The byte-edit allowlist fence (S5-01) protects against unauthorized byte-edits to *existing* Phase 0–6.5 files. It does NOT protect against *new* probe files being added to `src/codegenie/probes/` — because adding a net-new file under `src/codegenie/probes/layer_c/` is technically additive (the file grows the directory rather than mutating an existing file). Without a structural fence that asserts the placement policy, a future PR could quietly land a task-class-specific probe under the core probe tree and re-open the precedent BP-5 closed.

This story plants a small AST-walk + filesystem-walk fence that:
1. Asserts `BaseImageProbe` and `ShellInvocationTraceProbe` Python classes are defined under `plugins/distroless-migration--node--npm/probes/`, NOT under `src/codegenie/probes/`.
2. Asserts no Python file under `src/codegenie/probes/` defines a class named `BaseImageProbe` or `ShellInvocationTraceProbe`.
3. Generalizes (slightly): a meta-test enumerates every class decorated with `@register_probe` in the loaded registry and asserts none of them whose `applies_to_tasks` is task-class-specific (i.e., not `["*"]`) lives under `src/codegenie/probes/` — this is the load-bearing assertion that future task-class plugins follow the same shape.

The fence is small and mechanical; it complements (does not replace) S5-01's byte-edit fence and S5-03's import-linter contracts.

**Honest framing (Phase 3 ADR-0011 carry-forward):** like every other fence, this is audit + lint. CODEOWNERS on `tests/fence/` is the social anchor; a determined PR editing both the fence and the violation defeats it. Acceptable.

## References — where to look

- **Phase ADR — primary source of truth:**
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` §Decision + §Consequences — names the file `tests/fence/test_provenance_primitive_in_plugin_directory.py` and AST-asserts the two new probes live under `plugins/distroless-migration--node--npm/probes/`, not under `src/codegenie/probes/`.
- **Cross-cutting ADRs:**
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — this fence file is under `tests/fence/` and falls outside the byte-edit allowlist scope. Adding it is additive (new test file).
  - `production ADR-0031` (plugin architecture) — every plugin contributes its own `probes/`.
  - `production ADR-0007` (probe contract frozen) — the ABC lives at `src/codegenie/probes/base.py`; this fence does NOT enforce ABC-conformance (that's `tests/unit/test_probe_contract.py`'s job), only *placement*.
- **Architecture:**
  - `../phase-arch-design.md §Component design §8 (BaseImageProbe), §9 (ShellInvocationTraceProbe)` — names the file paths.
  - `../phase-arch-design.md §Testing strategy §Fence / structural` — names this fence file.
- **Precedent fence files (style):**
  - `tests/fence/test_plugin_protocol_frozen.py` — AST-walks plugin contract surfaces; mirror the structural-AST visitor pattern.
  - `tests/fence/test_no_any_in_plugin_surface.py` — `ast.NodeVisitor` (not shotgun `ast.walk`) discipline; reuse.
  - `tests/fence/test_capability_fence.py` — Phase 3 capability-construction AST fence; same shape (walk Python files, report `ast.ClassDef` matches).
- **Existing code:**
  - `src/codegenie/probes/registry.py` — `@register_probe` decorator + `_REGISTRY` access for the meta-test.
  - `src/codegenie/probes/__init__.py` — explicit-import collection point. A new line for the Phase 7 plugin probes would land here under S8-03's row 10 of the byte-edit allowlist; this fence does NOT depend on that wiring (it works on filesystem paths + AST, not on import discovery).

## Goal

Land `tests/fence/test_provenance_primitive_in_plugin_directory.py` (the name comes from ADR-0005 §Consequences verbatim) so any PR that places a Phase-7 (or any task-class-specific) probe under `src/codegenie/probes/` instead of under `plugins/<plugin-slug>/probes/` fails CI.

## Acceptance criteria

**Filesystem assertion (AC-1)**
- [ ] **AC-1** `tests/fence/test_provenance_primitive_in_plugin_directory.py` exists; module docstring (a) cites Phase 7 ADR-0005, (b) embeds Phase 3 ADR-0011 honest-framing language, (c) names the two probes by name (`BaseImageProbe`, `ShellInvocationTraceProbe`) and their expected locations (`plugins/distroless-migration--node--npm/probes/base_image_probe.py` and `.../shell_trace_probe.py`). A meta-test scans for these strings.

**Positive placement assertions (AC-2)**
- [ ] **AC-2** Parametrized test `test_probe_class_lives_at_expected_path` over the tuple `(("BaseImageProbe", "plugins/distroless-migration--node--npm/probes/base_image_probe.py"), ("ShellInvocationTraceProbe", "plugins/distroless-migration--node--npm/probes/shell_trace_probe.py"))`:
  - Reads the file at the expected path.
  - AST-parses it.
  - Walks `ast.ClassDef` nodes and asserts at least one node has `name == <probe_name>`.
  - Fails loudly if the file does not exist (with a message naming the expected path AND Phase 7 ADR-0005).

**Negative core-tree assertions (AC-3) — the load-bearing fence**
- [ ] **AC-3** `test_no_phase7_probe_class_under_core_tree`:
  - Walks every `*.py` under `src/codegenie/probes/` (recursively; exclude `__pycache__/`).
  - AST-parses each file.
  - Asserts no `ast.ClassDef` in any of those files has `name in {"BaseImageProbe", "ShellInvocationTraceProbe"}`.
  - On hit: failure message names the offending file path AND the disallowed class name AND Phase 7 ADR-0005.
- [ ] **AC-3.a** Per-probe parametrized variant (so failures attribute to a specific probe): two parameter rows, one per Phase 7 probe class name.

**Registry-coverage assertion (AC-4) — generalizes the fence**
- [ ] **AC-4** `test_task_class_specific_probes_never_live_under_core_tree`:
  - Imports `codegenie.probes.registry._REGISTRY` (or the public `get_all_probes()` API if exposed) after standard test bootstrap.
  - Filters to probe entries whose `applies_to_tasks` is task-class-specific (i.e., `applies_to_tasks != ["*"]`).
  - For each, derives the source file via `inspect.getsourcefile(probe_cls)`.
  - Asserts the resolved file path does NOT start with `src/codegenie/probes/`.
  - On hit: failure message names the probe class + the offending source path + Phase 7 ADR-0005 + production ADR-0031.
  - Empty pre-S7 (no Phase 7 probes registered yet): the test is `xfail(strict=True, reason="No task-class-specific probes loaded yet; will become required after S7-01 / S7-02")`. **Strict xfail flips to pass once Phase 7 probes register**, then to fail-on-unxpected-pass if a future probe ships under the core tree. This is the load-bearing future-protection.
  - Alternatively, if `xfail strict=True` complicates the suite: skip-when-empty with a `pytest.skip(...)` that *names* the precondition (no Phase 7 probes registered) so the skip is loud, not silent.

**Planted-violation evidence (AC-5) — Rule 12 fail-loud**
- [ ] **AC-5** Parametrized in-test planted-violation cases (use `tmp_path` + dependency-injection on the file-walker so the working tree is not mutated):
  - **AC-5.a** Plant a synthetic file `src/codegenie/probes/planted/base_image_probe_planted.py` containing `class BaseImageProbe: pass` (a class with the forbidden name in the forbidden directory) → AC-3's walker (parametrized over a `_walker_roots: tuple[Path, ...]` kwarg) flags it.
  - **AC-5.b** Plant the same class under `plugins/distroless-migration--node--npm/probes/decoy.py` → AC-3's walker does NOT flag it (proves the walker is scoped to the core tree).
  - **AC-5.c** Plant `class ShellInvocationTraceProbe: pass` under `src/codegenie/probes/layer_d/planted.py` → flagged.
  - **AC-5.d** Out-of-test evidence: on a throwaway branch, plant `class BaseImageProbe: pass` in `src/codegenie/probes/_test_planted.py`, run the fence, capture red output + SHA; remove; capture green + SHA. 3-line evidence block in `_attempts/S5-02.md`.

**Cross-fence integration (AC-6)**
- [ ] **AC-6** This fence does not regress S5-01: the new `tests/fence/test_provenance_primitive_in_plugin_directory.py` file is under `tests/fence/`, which is NOT in `_LOCKED_SURFACE_GLOBS` (S5-01's path filter excludes `tests/`). Verified by running `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py` after this story lands; exit code 0.

**Wiring (AC-7 through AC-9)**
- [ ] **AC-7** `pytest tests/fence/test_provenance_primitive_in_plugin_directory.py -v` exits 0 at story landing (with AC-4's strict-xfail if Phase 7 probes haven't registered yet).
- [ ] **AC-8** `make fence` and `make check` exit 0; no other fence regresses.
- [ ] **AC-9** `ruff check`, `ruff format --check`, `mypy --strict tests/fence/test_provenance_primitive_in_plugin_directory.py` clean.

## Implementation outline

1. **Author the fence file** `tests/fence/test_provenance_primitive_in_plugin_directory.py`:
   - Module docstring (AC-1 strings embedded).
   - `_EXPECTED_PHASE7_PROBE_LOCATIONS: Final[tuple[tuple[str, Path], ...]] = (("BaseImageProbe", Path("plugins/distroless-migration--node--npm/probes/base_image_probe.py")), ("ShellInvocationTraceProbe", Path("plugins/distroless-migration--node--npm/probes/shell_trace_probe.py")))`.
   - `_FORBIDDEN_PHASE7_PROBE_NAMES: Final[frozenset[str]] = frozenset({"BaseImageProbe", "ShellInvocationTraceProbe"})`.
   - `_CORE_PROBE_ROOT: Final[Path] = Path("src/codegenie/probes")`.
2. **Implement the AST walker as a pure function** so AC-5's planted-violation tests share the same code path as the live check:
   - `def find_classes_named(root: Path, forbidden_names: frozenset[str]) -> list[tuple[Path, int, str]]` — returns `(file_path, lineno, class_name)` for every `ast.ClassDef` in the root subtree whose name is in `forbidden_names`. Uses `ast.NodeVisitor` (NOT `ast.walk` shotgun).
3. **Wire AC-2** — parametrized test reads each expected probe location, AST-parses it, asserts the class is defined there. At story-landing time, S7-01 and S7-02 have not landed yet; this AC is therefore `xfail(strict=True)` until those stories ship. The dependency-DAG places this story before S7-01 / S7-02, so the xfail-then-pass transition is the load-bearing landing event.
4. **Wire AC-3 / AC-3.a** — the live `find_classes_named(_CORE_PROBE_ROOT, _FORBIDDEN_PHASE7_PROBE_NAMES)` call; empty list = pass; non-empty = fail with the helpful error.
5. **Wire AC-4** — registry-coverage assertion. Use `from codegenie.probes.registry import _REGISTRY` (private import is OK in tests; document the coupling). Filter by `applies_to_tasks != ["*"]`. Resolve via `inspect.getsourcefile`. Strict-xfail before Phase 7 probes register.
6. **Plant the AC-5 violations** (in `tmp_path` for AC-5.a–c via the `_walker_roots` kwarg; on a throwaway branch for AC-5.d). Record evidence.
7. **Run `make check`** — green.

## TDD plan (red → green → refactor)

**Red:**
1. Author the fence file with AC-2 / AC-3 / AC-4 wired but no `xfail` markers. Run `pytest tests/fence/test_provenance_primitive_in_plugin_directory.py` — expect AC-2 red (the expected probe files do not exist yet) and AC-4 either green-on-empty (no Phase 7 probes registered) or red-on-emptiness (depending on whether the test skips or asserts non-empty).
2. Verify the failure messages contain Phase 7 ADR-0005 and the offending paths.

**Green:**
1. Add `xfail(strict=True, reason="Phase 7 probes land in S7-01 / S7-02")` to AC-2 + AC-4 — the tests pass-as-xfail.
2. Run `pytest tests/fence/test_provenance_primitive_in_plugin_directory.py -v` — all green.
3. Plant a synthetic violation as in AC-5.a (in `tmp_path`); run the parametrized AC-5 test directly — it catches the violation.

**Refactor:**
1. Extract `find_classes_named` and the registry-walk helper as module-level pure functions with `Final` constants for the roots — same code path for live + planted tests (mutation-resistance).
2. Confirm `ruff` / `mypy --strict` clean.
3. Sort the `_EXPECTED_PHASE7_PROBE_LOCATIONS` tuple deterministically (alphabetical by class name).

## Files to touch

- `tests/fence/test_provenance_primitive_in_plugin_directory.py` — new test file.
- `_attempts/S5-02.md` — append-only attempt log with the 3-line out-of-test planted-violation evidence block.

## Out of scope

- **ABC conformance for the new probes** — that's `tests/unit/test_probe_contract.py`'s job and is exercised by S7-05.
- **Sub-schema location** — Phase 7 ADR-0005 also says sub-schemas live under `plugins/distroless-migration--node--npm/schema/`; that's S7-03's territory.
- **`@register_probe` registration coverage** — S7-05 verifies the loader picks up the new probes; this fence only asserts file placement.
- **Generalizing the fence to ALL future task-class plugins** — the parametrized expected-locations tuple only contains Phase 7's two probes. Phase 8+ extends this tuple via ADR amendment.
- **Cryptographic attestation** — Phase 3 ADR-0011 framing; this is lint, not signature. Deferred to Phase 11 Sigstore migration.

## Notes for the implementer

- **The xfail-strict transition is the load-bearing landing event.** At S5-02 landing time, S7-01 / S7-02 have not shipped, so AC-2's parametrized test is `xfail(strict=True)`. When S7-01 lands `BaseImageProbe` at the expected location, AC-2's `BaseImageProbe` row transitions to pass; the strict-xfail then *fails-on-unexpected-pass* until the xfail marker is removed. **The S7-01 implementer removes the xfail marker as part of S7-01 GREEN; document this hand-off in `_attempts/S5-02.md`.** Without this hand-off, the fence becomes a silent no-op once S7-01 lands.
- **The registry-walk in AC-4 is the future-protection.** Today it covers Phase 7's two probes; tomorrow it covers every task-class-specific probe added to the registry. The shape is data-driven: no Phase 7-specific magic, just "all probes whose `applies_to_tasks != ['*']`". If Phase 8 adds an `opentelemetry-migration` probe under `src/codegenie/probes/`, this fence catches it without any edit.
- **Anti-pattern explicitly avoided:** do NOT make this fence *also* enforce ABC conformance, registration, or sub-schema placement. Rule 2 — single-purpose, single-shape. Those are different fences with different shapes.
- **`inspect.getsourcefile` returns a string OR `None`.** Handle `None` defensively — a probe class whose source cannot be resolved is itself suspicious; treat it as a soft warning (skip with a loud reason), not a silent pass.
- **Surface conflicts (Rule 7):** if at implementation time `BaseImageProbe`'s file path in S7-01's story drifts from `base_image_probe.py` to e.g., `base_image.py`, surface the drift. The fix is an ADR amendment to ADR-0005's §Decision text + a one-row edit to `_EXPECTED_PHASE7_PROBE_LOCATIONS`. Do not silently rename.
- **CODEOWNERS is the social anchor.** `tests/fence/` should already be CODEOWNERS-covered transitively; verify and add if not.
