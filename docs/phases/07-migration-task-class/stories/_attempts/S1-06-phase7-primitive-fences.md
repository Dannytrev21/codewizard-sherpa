# Attempt log — S1-06 Phase 7 LLM-SDK + no-`Any` AST fences

Per-story append-only journal. Newest entry at the bottom.

---

## Attempt 1 — 2026-05-19 — GREEN

**Outcome:** GREEN on first attempt. 35 new tests pass. `make lint-imports`,
`make fence`, `pytest tests/fence/`, `mypy --strict` on touched files,
`ruff check`, `ruff format --check` all green. Three-out-of-three planted
violations exercised manually, evidence recorded below.

### What shipped

1. **`pyproject.toml`** — new `[[tool.importlinter.contracts]]` block:
   - name = `phase-7 primitive does not import LLM SDKs`
   - source_modules = `["codegenie.primitives.vuln_provenance"]`
   - forbidden_modules = the canonical `FORBIDDEN_LLM_SDKS` 5-tuple
   - `as_packages = true` (load-bearing — without it submodules leak)
   - `include_external_packages = true` (per-contract; mirrors the global)
2. **`tests/fence/test_phase7_no_llm.py`** — 8 tests:
   - AC-3.a live runtime-closure check + AC-3.d import-success guard (1 test, combined).
   - AC-3.b per-SDK planted-positive (5 parametrized cases — 5 mutation guards).
   - AC-3.c metamorphic complement (1 test).
   - AC-3.e module docstring framing (1 test — pins ADR-0004 + ADR-0005 + audit-+-lint posture).
3. **`tests/fence/test_no_any_in_provenance_surface.py`** — 20 tests:
   - AC-4 floor guard (1 test).
   - AC-4 live scan over the primitive (1 test).
   - AC-5 syft_reader.py exempt-but-clean check (1 test).
   - AC-4 per-shape mutation matrix — 17 parametrized cases (12 positive +
     5 negative), reusing Phase 3's `walk_any_annotations` and `Violation`
     (Rule 7 — do not fork; mutation-resistance preserved).
4. **`tests/fence/test_phase7_importlinter_contracts_shape.py`** — 6 tests:
   - AC-1 contract present.
   - AC-1.a type=forbidden.
   - AC-1.a source_modules pinned.
   - AC-1.b forbidden_modules equals `FORBIDDEN_LLM_SDKS` (drift guard).
   - AC-1.c `as_packages = true`.
   - AC-1.d `include_external_packages = true`.
5. **`tests/fence/test_lint_imports_catches_phase7_planted_leak.py`** — 1 test:
   - AC-2 subprocess-runs `lint-imports`, plants `import anthropic` under
     the primitive, asserts non-zero exit + message names `anthropic` AND
     references `phase-7` or `vuln_provenance`. `try/finally` cleans up.

### Reuse vs. fork — Rule 7 / Rule 11 compliance

- **`FORBIDDEN_LLM_SDKS`**: imported from `codegenie._fence`. No fork.
- **`walk_any_annotations` + `Violation`**: imported from `codegenie._phase3_fence`. No fork. Phase 7 contributes only a new `PHASE7_ROOTS` tuple + a thin walker wrapper (`_scan_phase7_surface`) — both private to the test module, scoped to the new contract surface only.
- The Phase 3 fence module name (`_phase3_fence.py`) is now a slight misnomer because Phase 7 also imports from it. Decision: leave the name alone (surgical change discipline — renaming would touch every Phase 3 import site). A follow-up story can rename to `_any_annotation_fence` if the walker grows additional consumers.

### AC-7 — three-out-of-three planted-violation evidence

Each gate was manually exercised by writing a deliberately-violating file
into the primitive surface, running the gate as a subprocess, observing
the failure with a useful error message, and removing the file.

**Gate 1 — `import-linter` contract.** Planted
`src/codegenie/primitives/vuln_provenance/_planted_check.py` containing
`import anthropic`. Ran `lint-imports --config pyproject.toml --no-cache`.
Observed:

```
phase-7 primitive does not import LLM SDKs BROKEN

Contracts: 4 kept, 1 broken.

phase-7 primitive does not import LLM SDKs
codegenie.primitives.vuln_provenance is not allowed to import anthropic:
-   codegenie.primitives.vuln_provenance._planted_check -> anthropic (l.2)
```

The failure names the contract, the source module, and the forbidden
module. File removed.

**Gate 2 — runtime-closure scan (`tests/fence/test_phase7_no_llm.py`).**
Planted `src/codegenie/primitives/vuln_provenance/_planted_runtime_check.py`
containing `import anthropic` (a real, eager top-level import). Ran
`pytest test_phase7_no_llm.py::test_no_llm_sdk_imported_by_primitive_packages`.
Observed:

```
AssertionError: Phase-7 primitive runtime-closure scan failed to import
codegenie.primitives.vuln_provenance._planted_runtime_check: No module
named 'anthropic'. Fix the underlying import error before re-running the fence.
```

Fail-loud (Rule 12): the scanner names the planted module by its full
dotted path. In this dev environment `anthropic` is not installed, so
the `ImportError → AssertionError` path fires; in a hypothetical
environment where `anthropic` *is* installed the scanner would instead
report the SDK in `sys.modules ∩ FORBIDDEN_LLM_SDKS` — the parametrized
`test_scanner_catches_each_planted_sdk_under_primitive[anthropic]` test
already proves that path using a fake-SDK shim. Both paths surface a
useful, actionable error. File removed.

**Gate 3 — no-`Any` AST fence
(`tests/fence/test_no_any_in_provenance_surface.py`).** Planted
`src/codegenie/primitives/vuln_provenance/_planted_any.py` containing:

```python
from typing import Any
x: dict[str, Any] = {}
```

Ran `pytest test_no_any_in_provenance_surface.py::test_phase7_surface_has_no_any_annotations`.
Observed: `AssertionError` with a `Violation` record naming
`_planted_any.py:3`, `kind=any-name`, `snippet=Any`. The walker correctly
identifies the planted shape — even though it sits inside a
`dict[str, Any]` subscript. File removed.

### Refactor decisions (design-patterns lens)

- **Strategy / Open-Closed for the walker.** Decision: do not introduce
  a `FenceScanner` strategy interface. The walker is already pure
  (`(src, path) -> list[Violation]`) — adding an interface adds zero
  capability and one indirection (Rule 2). When a third surface needs the
  walker, extract `scan_surface(roots: tuple[Path, ...]) -> list[Violation]`
  into the shared `_phase3_fence` (or a renamed module).
- **Newtype for `Violation`.** Already typed as a frozen dataclass with
  closed-`Literal` `kind` (Phase 3 S1-05). No change.
- **Registry for forbidden SDKs.** Already a `frozenset` constant
  (`FORBIDDEN_LLM_SDKS`). Adding indirection (a `@register_forbidden_sdk`
  decorator) would be premature — the SDK list churns slowly and the
  ADR-amendment requirement is the change-management gate.
- **Ports & Adapters.** The fence is structurally `pyproject.toml ↔
  import-linter ↔ test runtime`. The "port" (the `Violation` shape) is
  shared; the "adapters" are the per-gate test modules. This is already
  the pattern; no refactor.

### Gates run

- `make lint-imports` — 5 kept, 0 broken (was 4 + 0 before).
- `.venv/bin/pytest tests/fence/test_phase7_no_llm.py
  tests/fence/test_no_any_in_provenance_surface.py
  tests/fence/test_phase7_importlinter_contracts_shape.py
  tests/fence/test_lint_imports_catches_phase7_planted_leak.py
  --no-cov` → 35 passed.
- `PATH=.venv/bin:$PATH make fence` → 284 passed, 28 skipped, 1 xfailed
  (pre-existing skip set for the known circular-import task; the
  xfail-strict guard fires when that task lands).
- `.venv/bin/ruff check src/codegenie/primitives/vuln_provenance/ tests/fence/` → clean.
- `.venv/bin/ruff format --check src/codegenie/primitives/vuln_provenance/ tests/fence/` → clean.
- `.venv/bin/mypy --strict tests/fence/test_phase7_no_llm.py
  tests/fence/test_no_any_in_provenance_surface.py
  tests/fence/test_phase7_importlinter_contracts_shape.py
  tests/fence/test_lint_imports_catches_phase7_planted_leak.py` → clean.

### AC coverage table

| AC | Evidence |
|---|---|
| AC-1 | `pyproject.toml:391-396` (new contract block); 6 shape-pin tests in `test_phase7_importlinter_contracts_shape.py`. |
| AC-2 | `test_lint_imports_catches_phase7_planted_leak.py::test_lint_imports_catches_planted_anthropic_under_primitive` — subprocess + planted-positive + try/finally cleanup. |
| AC-3.a | `test_phase7_no_llm.py::test_no_llm_sdk_imported_by_primitive_packages`. |
| AC-3.b | `test_phase7_no_llm.py::test_scanner_catches_each_planted_sdk_under_primitive` × 5 SDKs. |
| AC-3.c | `test_phase7_no_llm.py::test_scanner_ignores_llm_sdk_present_outside_primitive_closure`. |
| AC-3.d | Combined into `test_no_llm_sdk_imported_by_primitive_packages` (import-success guard `assert pkg in sys.modules`). |
| AC-3.e | `test_phase7_no_llm.py::test_module_docstring_names_adr_framing`. |
| AC-4 | `test_no_any_in_provenance_surface.py::test_phase7_surface_has_no_any_annotations` + 17 shape mutation guards + floor guard. |
| AC-5 | `test_no_any_in_provenance_surface.py::test_syft_reader_has_no_declared_any_annotations`. |
| AC-6 | `tests/fence/test_fence_target_wiring.py::test_fence_recipe_invokes_phase3_fence_directory` already pins `tests/fence/` glob; new fence files sit under that glob and were observed running under `make fence`. |
| AC-7 | This log section "Three-out-of-three planted-violation evidence" — all three gates exercised, observed firing, cleaned up. |
| AC-8 | All gates run above. |

### Out of scope (deferred to later stories)

- **10-row byte-edit allowlist fence** — S5-01 (reserves the `pyproject.toml`
  + `tests/fence/` paths this story edited; coordinate with S5-01 writer).
- **`model_construct()` bypass fence** — already landed by S1-05 (story
  notes deferred to a follow-up but `test_vuln_provenance_no_model_construct.py`
  is already present in `tests/fence/`).
- **Cross-direction import-linter contracts** (primitive ↛ plugins) — S5-03.
- **Plugin-directory probe-placement fence** — S5-02.
- **`PLUGINS.lock` entry for the Phase 7 plugin tree** — S5-04.
- **Walker extraction into a non-Phase-3-named helper** — explicit decision
  to defer; rename when a third surface appears.

### TODO carried forward

- `# TODO(S5-01)`: this story's `pyproject.toml` edit (one
  `[[tool.importlinter.contracts]]` block) and the four new
  `tests/fence/*.py` files must be on the S5-01 byte-edit allowlist
  when that story is written.

### Lessons (also appended to `_lessons.md`)

- **Reusing Phase 3's `walk_any_annotations` was the right call.** The
  walker already takes `(src, path)` and is root-agnostic; "extending"
  the fence to Phase 7 was a new test module with `PHASE7_ROOTS = (...)`
  and a thin wrapper. A walker whose API admits new surfaces without
  edits is a walker that gets reused — the canonical mutation-resistance
  property of the Phase 0 fence precedent.
- **`include_external_packages = true` is a per-contract knob too.** The
  global setting at `[tool.importlinter]` works, but pinning it on the
  per-contract block (a) makes the contract self-describing for
  shape-pin tests, and (b) is exactly what the story spec literally
  encoded. When the spec encodes a knob, mirror the spec — the
  shape-pin test author and the contract author share one source of
  truth.
- **Three-out-of-three planted evidence is cheap when the gates are
  fast.** Each plant + observe + remove was sub-second. The validation
  cost of "all three gates fire on real planted violations" is
  negligible against the cost of a silently-degraded fence; this is the
  Phase 3 S1-05 lesson applied verbatim.
- **The fail-loud-on-ImportError path matters as much as the
  sys.modules-intersection path.** In a dev environment without the
  forbidden SDK installed, planted `import anthropic` surfaces as
  `ImportError → AssertionError` (because the scanner wraps the import).
  This is *also* a useful gate fire — the operator sees the planted
  module by name and can act. Both paths are surfaced via the same
  scanner function; one fence test, two failure modes, one source of
  truth.
