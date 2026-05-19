# Story S1-06 — Phase 7 LLM-SDK import-linter contract + no-`Any` AST fence

**Step:** Step 1 — Scaffold `vuln.provenance` primitive — newtypes, Provenance union, Protocol, errors, SyftSbom reader, fences
**Status:** GREEN

> **GREEN (2026-05-19):** Three CI gates landed and exercised against
> planted violations (3-of-3 evidence in
> `_attempts/S1-06-phase7-primitive-fences.md`). New files:
> `pyproject.toml` (one `[[tool.importlinter.contracts]]` block),
> `tests/fence/test_phase7_no_llm.py` (8 tests),
> `tests/fence/test_no_any_in_provenance_surface.py` (20 tests),
> `tests/fence/test_phase7_importlinter_contracts_shape.py` (6 tests),
> `tests/fence/test_lint_imports_catches_phase7_planted_leak.py` (1 test).
> Reuses `walk_any_annotations` + `Violation` + `FORBIDDEN_LLM_SDKS` from
> existing Phase 0 / Phase 3 fence helpers (no fork, Rule 7).
> `make lint-imports` → 5 kept / 0 broken; `make fence` → 284 passed;
> `mypy --strict` + `ruff check` + `ruff format --check` clean on touched files.
**Effort:** S
**Depends on:** S1-03, S1-04, S1-05

## Validation notes (2026-05-19, `phase-story-validator` first pass)

Edits applied in place (see [`_validation/S1-06-phase7-primitive-fences.md`](_validation/S1-06-phase7-primitive-fences.md) for the full audit):

- **F1 — Canonical walker pinned.** The TDD plan and Implementation outline now name `walk_any_annotations(src: str, path: Path) -> list[Violation]` from `codegenie._phase3_fence` — not `has_any_annotation(tree)`. The walker already exists; the executor imports, does not fork (Rule 7).
- **F2 — `PHASE7_ROOTS` Open/Closed mirror is now an explicit AC.** Mirrors Phase 3's `PHASE3_ROOTS: Final[tuple[Path, ...]]` convention; floor guard parametrizes over it.
- **F4/F5 — `sys.modules` isolation + metamorphic invariants made concrete.** AC-3.b spells out snapshot/restore discipline; AC-3.c spells out the plant-outside-primitive-then-walk-then-pop-then-intersect invariant. No more hand-wavy "implementer wires this."
- **F6 — `as_packages = true` rationale captured load-bearing** so a future "cleanup" cannot silently drop it.
- **F7 — `make fence` wiring concretised to `tests/fence/test_fence_target_wiring.py`** (which exists). AC-6 names the file to extend.
- **F8 — AC-7's three planted-violation scenarios enumerated** with exact failure-message expectations each must produce; evidence shape uniform.
- **F9 — `__init__.py` is INCLUDED in the AST walk** (deliberate divergence from Phase 3 — re-exports are public surface). Floor guard counts non-init modules only.
- **F3 / F10 / F11 — surfaced as Notes-for-implementer** (marker-grammar Open/Closed grandfathering, S5-01 byte-edit allowlist forward-coupling, `lint-imports` invocation discipline).

Out-of-scope (recorded; not folded into ACs): shared `codegenie._fence_roots` registry (rule-of-three not yet reached — defer to Phase 8+); phase-prefix-agnostic `ALLOWED_MARKER_RE` (defer until a real Phase 7+ marker is needed); `model_construct()` bypass fence (already deferred per the story's Out-of-scope section).
**ADRs honored:** ADR-0004 (Consequences clause: "an `import_linter` contract extends the cold-start defense to `src/codegenie/primitives/vuln_provenance/` — no LLM SDK imports" and "a fence test extends the runtime closure assertion to the new tree"), production ADR-0005 (no LLM in gather pipeline — this story extends that fence to the new primitive), Phase 3 ADR-0010 (`dict[str, Any]` banned under contract-surface trees — this story extends that to `primitives/vuln_provenance/`), Phase 0/Phase 3 fence precedent (`tests/fence/test_pyproject_fence.py`, `tests/fence/test_no_any_in_plugin_surface.py`)

## Context

The `vuln.provenance` primitive is becoming kernel-surface (ADR-0039 bounded additive primitive home). Without CI fences, a future story could quietly:
- import `anthropic` / `openai` / `langchain` / `langgraph` / `transformers` from `src/codegenie/primitives/vuln_provenance/` (the deterministic-pipeline guarantee dies silently);
- annotate the primitive's public surface with `dict[str, Any]` or bare `Any` (every typed-boundary discipline Step 1 just shipped dies silently — the `SyftSbom` `extra="allow"` is the one tolerated exception, but `Any` annotations elsewhere are unbounded primitive obsession).

The Phase 0 `tests/unit/test_pyproject_fence.py` + Phase 3 `tests/fence/test_no_any_in_plugin_surface.py` are the precedent shapes. This story extends both posture types to the new primitive tree: one `import-linter` contract (cold-start defense) + two fence tests (runtime-closure scan + AST-walk for `Any`). Per Phase 7 ADR-0009, this is preparation for the larger byte-edit allowlist fence in S5-01; the contracts and tests land now so Step 2+ stories cannot regress them before the allowlist arrives.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy §CI gates` — names "extend `import-linter` to `primitives/vuln_provenance/`" + "no-`Any` AST fence on the primitive surface".
  - `../phase-arch-design.md §Harness engineering §Determinism vs probabilism` — "Fence-enforced by `tests/fence/test_phase7_no_llm.py` (`import_linter` contract)."
  - `../phase-arch-design.md §Anti-patterns avoided` — "Untyped `dict[str, Any]`: `SyftSbom` carries `extra='allow'` deliberately; every other typed boundary is `extra='forbid'`" — this fence enforces that everywhere except `syft_reader.py`.
- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` Consequences clause (last two bullets) — names exactly the two fence shapes this story lands.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — the parent rule this story extends.
  - `../../../production/adrs/0039-bounded-additive-core-primitives.md` — names `primitives/` as kernel surface; admits additional fences without an ADR amendment.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `pyproject.toml §[tool.importlinter]` (existing Phase 0 + Phase 3 contracts) — mirror the `type = "forbidden"`, `source_modules = [...]`, `forbidden_modules = [...]`, `as_packages = true`, `include_external_packages = true` shape. Read the existing rows; do NOT redefine `FORBIDDEN_LLM_SDKS`.
  - `src/codegenie/_fence.py` — Phase 0 `FORBIDDEN_LLM_SDKS` + `scan_installed_distribution` + `parse_runtime_dep_names_from_toml`. **Reuse**; do NOT reimplement.
  - `tests/unit/test_pyproject_fence.py` — Phase 0 fence-test scaffolding. Mirror the planted-positive + metamorphic-complement pattern.
  - `src/codegenie/_phase3_fence.py` + `tests/fence/test_no_any_in_plugin_surface.py` — Phase 3 `Any`-AST-walker. **Canonical helper:** `walk_any_annotations(src: str, path: Path) -> list[Violation]`. **Canonical roots constant:** `PHASE3_ROOTS: Final[tuple[Path, ...]]`. **Canonical hit type:** the frozen `Violation` dataclass with `kind: ViolationKind` (closed `Literal`). Phase 7 imports all three verbatim and mirrors `PHASE3_ROOTS` with a parallel `PHASE7_ROOTS` (extension by addition — Phase 3's tuple is NOT mutated; Phase 7 ADR-0009 byte-edit allowlist forbids it).
  - `tests/fence/test_phase3_importlinter_contracts_shape.py` — Phase 3 contract-shape parsing test; mirror.
  - `src/codegenie/primitives/vuln_provenance/syft_reader.py` (from S1-05) — has `extra="allow"` deliberately; the `Any`-fence must **exempt** this file (or specifically not flag `__pydantic_extra__` shapes).
- **Phase 3 story precedent:**
  - `../../../03-vuln-deterministic-recipe/stories/S1-05-phase3-fence-tests.md` — the structural fence story this one mirrors. Identical AC shapes (planted-positive, metamorphic complement, floor guard).

## Goal

Land three CI gates that protect the `src/codegenie/primitives/vuln_provenance/` surface:
1. An `import-linter` contract forbidding `FORBIDDEN_LLM_SDKS` under the new primitive (cold-start defense).
2. `tests/fence/test_phase7_no_llm.py` — runtime-closure scan asserting no LLM SDK imports through the primitive (`pkgutil.walk_packages` + `sys.modules` intersection).
3. `tests/fence/test_no_any_in_provenance_surface.py` — AST-walk asserting no `Any` / `dict[str, Any]` annotations on the primitive surface (with one explicit exemption: `syft_reader.py` is allowed to admit `__pydantic_extra__` via `extra="allow"`, but its declared annotations stay typed).

## Acceptance criteria

- [ ] **AC-1 — Import-linter contract (cold-start defense).** `pyproject.toml [tool.importlinter]` gains one new `type = "forbidden"` contract:
  ```toml
  [[tool.importlinter.contracts]]
  name = "phase-7 primitive does not import LLM SDKs"
  type = "forbidden"
  source_modules = ["codegenie.primitives.vuln_provenance"]
  forbidden_modules = ["anthropic", "openai", "langchain", "langgraph", "transformers"]
  as_packages = true
  include_external_packages = true
  ```
  A unit test parses `pyproject.toml`, locates the contract by name, asserts:
  - **(a)** `source_modules == ["codegenie.primitives.vuln_provenance"]` (retargeting to `codegenie.primitives` would over-fence; retargeting to a subpath would under-fence — pin exactly).
  - **(b)** `set(forbidden_modules) == codegenie._fence.FORBIDDEN_LLM_SDKS` — coupled to the canonical constant so drift is impossible. Drift here = the fence is silently incomplete.
  - **(c)** `as_packages is True` — **load-bearing**: without it `import-linter` scans only `vuln_provenance/__init__.py` and every submodule (`types`, `protocols`, `errors`, `syft_reader`, `registry`, `assembly`, `events`, `sbom_verifier`) silently leaks. The shape-pin test's failure message MUST name the submodule-leakage failure mode so a future "cleanup" cannot drop the flag silently.
  - **(d)** `include_external_packages is True` — required for `import-linter` to traverse third-party packages (the LLM SDKs) in transitive-import reasoning.
- [ ] **AC-2 — `make lint-imports` green with the new contract.** Verified by a planted-positive subprocess test: a temp file `src/codegenie/primitives/vuln_provenance/_test_planted_leak.py` containing `import anthropic` is written, `make lint-imports` runs as a subprocess, exits non-zero, the failure message names the planted file. File removed after assertion (test uses `try/finally`).
- [ ] **AC-3 — `tests/fence/test_phase7_no_llm.py` — runtime-closure scan.** Reuses `codegenie._fence.FORBIDDEN_LLM_SDKS`. Mutation guards:
  - **AC-3.a** **Live check:** `pkgutil.walk_packages(codegenie.primitives.vuln_provenance.__path__)` followed by `set(sys.modules) & FORBIDDEN_LLM_SDKS == set()`.
  - **AC-3.b** **Per-SDK planted-positive** (`@pytest.mark.parametrize` over the five SDKs): for each SDK, (1) write a fake `<sdk>.py` to a `tmp_path/fake_sdk_root` and `monkeypatch.syspath_prepend` it; (2) write a temp primitive submodule `src/codegenie/primitives/vuln_provenance/_test_planted_<sdk>.py` containing `import <sdk>`; (3) **snapshot AND pop** every `codegenie.primitives.vuln_provenance` and `codegenie.primitives.vuln_provenance.*` entry from `sys.modules` (so the walker re-imports them fresh and observes the planted file); (4) run the SAME scanner the live check uses; (5) assert `sdk in scanner_result`; (6) in `finally`, delete the planted file, pop the SDK from `sys.modules`, pop the freshly-imported primitive modules, restore the snapshot. The isolation discipline is **load-bearing** — without it, subsequent tests see a different `vuln_provenance.*` class identity than they did at pytest collection time (breaks the future S2-01 adapter registry's class-identity contract).
  - **AC-3.c** **Metamorphic complement:** plant a fake `anthropic.py` at `tmp_path/fake_outside/anthropic.py` and `monkeypatch.syspath_prepend` it (NOT under the primitive's path); `importlib.import_module("anthropic")` to populate `sys.modules["anthropic"]`; walk the primitive packages; assert `"anthropic" in sys.modules` (we put it there); pop ALL `FORBIDDEN_LLM_SDKS` entries from `sys.modules`; intersect post-pop `sys.modules` with `FORBIDDEN_LLM_SDKS`; assert the result is `frozenset()`. **The invariant proven is:** the primitive's walk does NOT re-import a globally-present SDK; scoping is the primitive's closure, not the test runner's `sys.modules`. (Concrete invariant — no hand-wavy "implementer wires this.")
  - **AC-3.d** **Import-success guard:** assert `"codegenie.primitives.vuln_provenance" in sys.modules` after the walk — silently-caught `ImportError` must not green the test.
  - **AC-3.e** **ADR framing in docstring:** module-level docstring names ADR-0004 + production ADR-0005; meta-test scans for the required strings.
- [ ] **AC-4 — `tests/fence/test_no_any_in_provenance_surface.py` — AST-walk fence.** Mirrors Phase 3's structural visitor (NOT shotgun `ast.walk`):
  - **`PHASE7_ROOTS` Open/Closed mirror:** module-level `PHASE7_ROOTS: Final[tuple[Path, ...]] = (Path("src/codegenie/primitives/vuln_provenance"),)`. Mirrors `codegenie._phase3_fence.PHASE3_ROOTS`. Phase 3's `PHASE3_ROOTS` is NOT mutated (Phase 7 ADR-0009 byte-edit allowlist forbids editing `_phase3_fence.py`). A future ADR-0039 primitive landing in Phase 8+ becomes the third consumer; at that point the per-phase tuples may be lifted into a shared `codegenie._fence_roots` registry (rule-of-three) — out of scope here.
  - **AST scan scope:** every `*.py` file under each `PHASE7_ROOTS` entry, **including `__init__.py`** — re-exports from `vuln_provenance/__init__.py` are part of the public surface; an `Any` annotation there is just as harmful as one in a submodule. This is a deliberate divergence from Phase 3's `scan_phase3_surface()` (which excludes `__init__.py`); rationale recorded in the module docstring.
  - **Walker:** import `walk_any_annotations(src: str, path: Path) -> list[Violation]` from `codegenie._phase3_fence` verbatim. **This is the SAME function Phase 3 uses.** Do NOT extract, re-implement, fork, or rename — Rule 7. (The walker was extracted into `_phase3_fence` by Phase 3 S1-05; the visitor handles `ast.AnnAssign.annotation`, `ast.arg.annotation`, `ast.FunctionDef.returns`, `ast.AsyncFunctionDef.returns`, plus forward-ref re-parse of string `Constant` values.) Import `Violation` (frozen dataclass) and `ViolationKind` (closed `Literal`) for hit aggregation.
  - **Floor guard:** parametrized over `PHASE7_ROOTS`; each root directory exists AND contains ≥ 1 non-`__init__.py` Python module (`__init__.py` is included in the AST scan but EXCLUDED from the floor-guard count, to avoid silently-greening an empty package whose init re-exports nothing).
  - **Per-shape planted-violation matrix:** reuse Phase 3's exact matrix verbatim (`x: Any`, `def f(x: Any) -> None`, `def f() -> Any`, `x: dict[str, Any]`, `x: Dict[str, Any]`, `x: list[Any]`, `x: tuple[Any, ...]`, `x: typing.Any`, `x: Callable[..., Any]`, `x: dict[str, list[Any]]`, `x: "Any"` forward-ref, `x: "dict[str, Any]"` forward-ref) — each row is one mutation guard against a regression that drops a shape from the visitor.
  - **Negative cases:** `x: int = 1`, `x: dict[str, int] = {}`, `isinstance(obj, Any)` (runtime), `if TYPE_CHECKING: from typing import Any` (import), `from typing import Any` (import) → NOT flagged.
- [ ] **AC-5 — `syft_reader.py` is exempt from the `Any` fence.** The deliberate `extra="allow"` admits a `__pydantic_extra__: dict[str, Any]` shape internally to Pydantic, but the file's *declared annotations* must stay typed. The fence walks `syft_reader.py` and flags any **declared** `Any` annotation; the Pydantic-internal `__pydantic_extra__` field is generated, not declared, so it does not appear in the AST. A test asserts: `_has_any("syft_reader.py source")` returns no findings today (i.e., the S1-05 implementation must not have introduced any `Any` annotations).
- [ ] **AC-6 — `make fence` wiring.** Extend `tests/fence/test_fence_target_wiring.py` (which exists, Phase 3 precedent) with assertions that the `Makefile`'s `fence:` recipe covers **all four** new Phase 7 fence files: `tests/fence/test_phase7_no_llm.py`, `tests/fence/test_no_any_in_provenance_surface.py`, `tests/fence/test_phase7_importlinter_contracts_shape.py`, `tests/fence/test_lint_imports_catches_phase7_planted_leak.py`. Coverage is asserted either by explicit-path enumeration in the recipe OR by a directory glob (e.g. `tests/fence/`) that the meta-test recognises. Do NOT invent a new wiring test — extend the existing one.
- [ ] **AC-7 — Three-out-of-three planted-violation evidence** (mirrors Phase 3 S1-05's discipline). `_attempts/S1-06.md` records evidence for **each** of the three enumerated scenarios — uniform shape so the validation precedent stays mechanical:
  1. **Gate 1 — `import-linter` contract:** plant `import anthropic` at `src/codegenie/primitives/vuln_provenance/_test_planted_phase7_leak.py`; run `make lint-imports` (or the `lint-imports` console script directly — see Notes); capture stdout/stderr; assert non-zero exit AND the combined output names BOTH `anthropic` AND (`phase-7` OR `vuln_provenance`) so an operator can locate the offending contract; remove the planted file in `finally`.
  2. **Gate 2 — runtime-closure fence (`tests/fence/test_phase7_no_llm.py`):** same planted file as above; run `pytest tests/fence/test_phase7_no_llm.py`; capture failure output; assert it names the planted module path (`_test_planted_phase7_leak`); remove planted file.
  3. **Gate 3 — no-`Any` AST fence (`tests/fence/test_no_any_in_provenance_surface.py`):** plant `x: Any = 1` at `src/codegenie/primitives/vuln_provenance/_test_planted_any.py`; run `pytest tests/fence/test_no_any_in_provenance_surface.py`; capture failure output; assert it reports `Violation(file=…_test_planted_any.py, line=1, kind="any-name", snippet="Any")`; remove planted file.

  Plus a `## Forward-coupling to S5-01` section in the same `_attempts/S1-06.md` listing every byte-edit this story made to Phase 0–6.5-locked files (`pyproject.toml`'s one `[[tool.importlinter.contracts]]` block) and every new file added under `tests/fence/` (four new files) — S5-01's executor mechanically picks these up when writing the byte-edit allowlist.
- [ ] **AC-8 — Gates.** `make lint-imports` green; `pytest tests/fence/` green; `mypy --strict` clean on touched files; `ruff check`, `ruff format --check` clean; Phase 0/1/2/3 + Phase 5/6.5 regression suite green.
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline

1. Add the new `[[tool.importlinter.contracts]]` block to `pyproject.toml`. Match the existing Phase 3 contract style verbatim — `as_packages = true`, `include_external_packages = true`.
2. Land `tests/fence/test_phase7_no_llm.py`:
   - Import `FORBIDDEN_LLM_SDKS`, `scan_installed_distribution` from `codegenie._fence`. **Reuse, do not redefine.**
   - Walk `codegenie.primitives.vuln_provenance.__path__` via `pkgutil.walk_packages`.
   - Intersect `set(sys.modules)` with `FORBIDDEN_LLM_SDKS`; assert empty.
   - Add the per-SDK planted-positive parametrized test (five cases).
   - Add the metamorphic complement.
   - Add the import-success guard.
   - Module-level docstring naming ADR-0004 + production ADR-0005.
3. Land `tests/fence/test_no_any_in_provenance_surface.py`:
   - Import `walk_any_annotations` (canonical helper, signature `(src: str, path: Path) -> list[Violation]`) and `Violation` from `codegenie._phase3_fence`. **The walker already exists.** Do NOT extract, fork, or rename — Rule 7.
   - Module-level `PHASE7_ROOTS: Final[tuple[Path, ...]] = (Path("src/codegenie/primitives/vuln_provenance"),)`. Mirror, do not edit, `codegenie._phase3_fence.PHASE3_ROOTS`.
   - Module-level helper `_scan_phase7_surface() -> list[Violation]` that iterates `PHASE7_ROOTS`, asserts each root is a directory and contains ≥ 1 non-`__init__.py` module (floor guard), then runs `walk_any_annotations` over every `*.py` file (including `__init__.py` — see AC-4 rationale).
   - Floor-guard test: parametrize over `PHASE7_ROOTS`; assert directory exists + non-init module count ≥ 1.
   - Live check: call `_scan_phase7_surface()`; assert returned `Violation` list is empty.
   - `syft_reader.py` exempt-but-clean test (AC-5): read `PHASE7_ROOTS[0] / "syft_reader.py"`; run the walker; assert empty list.
   - Per-shape planted-violation parametrized matrix (verbatim Phase 3 table — paste, don't paraphrase).
   - Negative-case parametrized matrix.
4. Land `tests/fence/test_phase7_importlinter_contracts_shape.py`:
   - Parse `pyproject.toml`; locate the Phase 7 contract by name; assert the four invariants (AC-1.a-d).
5. Land `tests/fence/test_lint_imports_catches_phase7_planted_leak.py`:
   - Write a temp `_test_planted_leak.py` under the primitive containing `import anthropic`.
   - Subprocess-run `make lint-imports`; assert non-zero exit + planted module name in stderr.
   - Remove the planted file in `finally`.
6. Wire `make fence` target (verify the existing `Makefile` recipe already covers the new files via the `tests/fence/` glob; if not, add explicit paths).

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/fence/test_phase7_no_llm.py`

```python
"""Phase 7 LLM-SDK runtime-closure fence — ADR-0004 + production ADR-0005.

This fence is audit + lint, NOT a runtime guarantee. A PR that edits both this
file and a violation defeats it; mitigated by CODEOWNERS on `tests/fence/`.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

from codegenie._fence import FORBIDDEN_LLM_SDKS

PRIMITIVE_PKG = "codegenie.primitives.vuln_provenance"


def _walk_primitive() -> None:
    pkg = importlib.import_module(PRIMITIVE_PKG)
    for _ in pkgutil.walk_packages(pkg.__path__, prefix=f"{PRIMITIVE_PKG}."):
        importlib.import_module(_.name)


# --- AC-3.a Live check -------------------------------------------------------

def test_no_llm_sdk_in_primitive_runtime_closure():
    _walk_primitive()
    leaked = set(sys.modules) & FORBIDDEN_LLM_SDKS
    assert leaked == set(), f"LLM SDKs leaked through primitive closure: {leaked}"


# --- AC-3.d Import-success guard --------------------------------------------

def test_primitive_imports_succeed():
    _walk_primitive()
    assert PRIMITIVE_PKG in sys.modules


# --- AC-3.b Per-SDK planted-positive (sketch — implementer fills in details) ---

@pytest.mark.parametrize("sdk", sorted(FORBIDDEN_LLM_SDKS))
def test_fence_catches_planted_leak(sdk: str, tmp_path: Path, monkeypatch):
    """Mirror Phase 0 / Phase 3 planted-positive: create a temp submodule
    under the primitive's path that imports the SDK; assert the scanner
    catches it; restore.
    """
    # Implementation detail mirrors tests/unit/test_pyproject_fence.py and
    # tests/fence/test_no_llm_in_transforms.py. The test fails today because
    # the live check (above) hasn't run yet; once the implementer lands the
    # full planted-positive scaffolding, the test is structurally guarded.
    pass  # implementer: fill in per the Phase 0/3 precedent


# --- AC-3.c Metamorphic complement -----------------------------------------

def test_fence_ignores_llm_sdk_outside_primitive_closure(monkeypatch):
    """If anthropic is in sys.modules but NOT via the primitive's closure,
    the fence must NOT fire. Proves scoping."""
    import types
    fake = types.ModuleType("anthropic")
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    # Live check still walks the primitive — and the primitive does NOT
    # import anthropic — so the intersection should be empty *for the
    # primitive's closure*, even though anthropic is globally present.
    # The fence here checks the post-walk intersection; the structural
    # property is that we don't add anthropic to the primitive's reachable
    # set just because it's globally present.
    _walk_primitive()
    # Anthropic is in sys.modules (we put it there), so the simple
    # intersection would fire — but the live check above already ran and
    # passed. To test the metamorphic property, the implementer wires this
    # test to use a closure-scoped scanner (per Phase 0 precedent) rather
    # than the raw sys.modules intersection.
    # …implementer mirrors test_fence_ignores_llm_sdk_when_planted_in_optional_extras.
```

`tests/fence/test_no_any_in_provenance_surface.py`:

```python
"""Phase 7 no-Any AST fence — Phase 7 ADR-0004 + Phase 3 ADR-0010 / ADR-0011.

AST-walks src/codegenie/primitives/vuln_provenance/ and rejects any
declared `Any` / `dict[str, Any]` annotation. The deliberate `extra='allow'`
on SyftSbom is NOT a declared `Any` — it surfaces internally via
`__pydantic_extra__` which Pydantic generates at runtime and which is not
in the AST. This fence remains green after S1-05.

Audit + lint posture (ADR-0011), not a runtime guarantee.
"""
from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from codegenie._phase3_fence import Violation, walk_any_annotations

PHASE7_ROOTS: Final[tuple[Path, ...]] = (
    Path("src/codegenie/primitives/vuln_provenance"),
)
"""Mirror of `codegenie._phase3_fence.PHASE3_ROOTS`. Do NOT mutate PHASE3_ROOTS
from this file — Phase 7 ADR-0009 byte-edit allowlist forbids editing
`_phase3_fence.py`. Future Phase 8+ primitive surfaces extend by adding a
parallel `PHASE8_ROOTS` constant in a new fence file."""


def _scan_phase7_surface() -> list[Violation]:
    """Live scan using the canonical Phase 3 walker."""
    out: list[Violation] = []
    for root in PHASE7_ROOTS:
        if not root.is_dir():
            raise AssertionError(
                f"Phase-7 fence root {root} does not exist — fence cannot run"
            )
        non_init = [p for p in root.rglob("*.py") if p.name != "__init__.py"]
        if not non_init:
            raise AssertionError(
                f"Phase-7 fence root {root} has only __init__.py — would silently green"
            )
        # NB: scan ALL *.py files (including __init__.py) — re-exports are
        # public surface. Floor guard above counts non-init modules only.
        for file in sorted(root.rglob("*.py")):
            out.extend(walk_any_annotations(file.read_text(), file))
    return out


# --- AC-4 floor guard --------------------------------------------------------

@pytest.mark.parametrize("root", PHASE7_ROOTS, ids=lambda p: str(p))
def test_each_phase7_root_exists_and_is_non_empty(root: Path) -> None:
    assert root.is_dir()
    assert [p for p in root.rglob("*.py") if p.name != "__init__.py"]


# --- AC-4 live check ---------------------------------------------------------

def test_no_any_in_primitive_surface() -> None:
    violations = _scan_phase7_surface()
    assert violations == [], f"Any annotations found in primitive: {violations}"


# --- AC-5 syft_reader.py exempt-but-clean ------------------------------------

def test_syft_reader_has_no_declared_any_annotations() -> None:
    path = PHASE7_ROOTS[0] / "syft_reader.py"
    assert path.is_file()
    violations = walk_any_annotations(path.read_text(), path)
    assert violations == []


# --- AC-4 per-shape planted-violation matrix (verbatim Phase 3 table) -------

_SHAPE_MATRIX: Final[tuple[tuple[str, bool], ...]] = (
    ("x: Any = 1", True),
    ("def f(x: Any) -> None: ...", True),
    ("def f() -> Any: ...", True),
    ("x: dict[str, Any] = {}", True),
    ("x: Dict[str, Any] = {}", True),
    ("x: list[Any] = []", True),
    ("x: tuple[Any, ...] = ()", True),
    ("x: typing.Any = 1", True),
    ("x: Callable[..., Any] = None", True),
    ("x: dict[str, list[Any]] = {}", True),
    ('x: "Any" = 1', True),
    ('x: "dict[str, Any]" = {}', True),
    ("x: int = 1", False),
    ("x: dict[str, int] = {}", False),
    ("isinstance(obj, Any)", False),
    ("if TYPE_CHECKING:\n    from typing import Any", False),
    ("from typing import Any", False),
)


@pytest.mark.parametrize("snippet,expected_hit", _SHAPE_MATRIX)
def test_walker_per_shape(snippet: str, expected_hit: bool) -> None:
    import textwrap
    violations = walk_any_annotations(
        textwrap.dedent(snippet), path=Path("_test.py")
    )
    assert (len(violations) > 0) is expected_hit
```

State why it fails today: (a) the `import-linter` contract for `codegenie.primitives.vuln_provenance` does not exist; (b) `tests/fence/test_phase7_no_llm.py` does not exist; (c) `tests/fence/test_no_any_in_provenance_surface.py` does not exist; (d) `tests/fence/test_phase7_importlinter_contracts_shape.py` does not exist; (e) `tests/fence/test_lint_imports_catches_phase7_planted_leak.py` does not exist. Note: `walk_any_annotations` and `Violation` already exist in `codegenie._phase3_fence` — no extraction work needed.

### Green — make it pass
- Add the `[[tool.importlinter.contracts]]` block to `pyproject.toml`.
- Land the three new fence files; reuse `codegenie._fence.FORBIDDEN_LLM_SDKS` + `codegenie._phase3_fence.has_any_annotation` (or extract the latter into a shared helper if needed).
- Wire `make fence` (verify `tests/fence/` glob covers the new files).
- Plant + remove each violation to gather AC-7 evidence.

### Refactor — clean up
- Each fence file's module docstring names ADR-0004 + production ADR-0005 + ADR-0011 ("audit + lint posture, not runtime").
- No walker extraction needed — `walk_any_annotations` already lives in `codegenie._phase3_fence` (Phase 3 S1-05). Verify by import.
- Confirm `make fence` runs all four new Phase 7 fence files alongside Phase 0 + Phase 3's fences. The Phase 3 `tests/fence/test_no_any_in_plugin_surface.py` MUST still pass — the shared walker is unchanged, no Phase 3 imports moved.

## Files to touch
| Path | Why |
|---|---|
| `pyproject.toml` | Add one `[[tool.importlinter.contracts]]` block for the primitive (Phase 7 byte-edit allowlist row to be recorded for S5-01). |
| `tests/fence/test_phase7_no_llm.py` | NEW — runtime-closure scan; planted-positive + metamorphic complement. |
| `tests/fence/test_no_any_in_provenance_surface.py` | NEW — AST-walk fence; floor guard + planted-violation matrix; consumes `walk_any_annotations` from `codegenie._phase3_fence`. |
| `tests/fence/test_phase7_importlinter_contracts_shape.py` | NEW — parse `pyproject.toml`; assert the new contract's shape (AC-1). |
| `tests/fence/test_lint_imports_catches_phase7_planted_leak.py` | NEW — subprocess `lint-imports` planted-positive (AC-2). |
| `tests/fence/test_fence_target_wiring.py` | EXTEND — assert the `Makefile`'s `fence:` recipe covers the four new files (AC-6). |
| `Makefile` | NO EDIT IF the existing `fence:` target's glob (`tests/fence/`) already covers the new files; verify via the wiring test first. |
| `src/codegenie/_phase3_fence.py` | **DO NOT TOUCH** — Phase 7 ADR-0009 byte-edit allowlist forbids editing this file. `walk_any_annotations`, `Violation`, `PHASE3_ROOTS` are imported as-is. |
| `_attempts/S1-06.md` | NEW — three planted-violation evidence entries (AC-7) + forward-coupling section listing the byte-edits for S5-01. |

## Out of scope

- **The 10-row byte-edit allowlist fence** — landed by S5-01 (this story is the LLM + `Any` fence; the byte-edit fence is a separate enumeration).
- **The `model_construct()` bypass fence** — named in ADR-0004 Consequences as a future fence; deferred to the implementer's discretion or a follow-up story.
- **Cross-direction import-linter contracts** (primitive cannot import from `plugins/`) — landed by S5-03 (Step 5).
- **The plugin-directory probe-placement fence** — landed by S5-02 (Step 5).
- **`PLUGINS.lock` entry for the new plugin tree** — landed by S5-04 (Step 5; the new Phase 7 plugin doesn't exist yet at this story's time).
- **Wider `Any`-fence coverage to `plugins/distroless-migration--*/`** — landed by S5-03 once the new plugin tree exists.

## Notes for the implementer

- **Reuse, don't redefine `FORBIDDEN_LLM_SDKS`.** It lives at `src/codegenie/_fence.py`. Importing the constant + the scanner is the entire dependency surface. Forking it (in a copy-paste, or via a "Phase 7 SDKs" list) is a Rule 7 violation — the canonical home is Phase 0.
- **The `has_any_annotation` walker should be the same function** that Phase 3's `tests/fence/test_no_any_in_plugin_surface.py` uses. Read that file first; if the walker is already in a shared helper (`src/codegenie/_phase3_fence.py` or similar), import it; if it's inline, extract it (additive: move the function, update Phase 3's test's import line — that's the single byte-edit). Forking the walker is the same Rule 7 violation as forking `FORBIDDEN_LLM_SDKS`.
- **`SyftSbom`'s `extra="allow"` is NOT an `Any` annotation.** The Pydantic-internal `__pydantic_extra__: dict[str, Any]` is *generated* by Pydantic when `extra="allow"` is set; it does not appear in the AST of `syft_reader.py`. The fence walks the AST, so it does not see `__pydantic_extra__`. If S1-05 was implemented correctly (no declared `Any` annotations), `syft_reader.py` passes the fence today. If a future Phase-7 developer adds `metadata: dict[str, Any]` to `SyftSbom`, the fence fires — that's the intended discipline.
- **Three-out-of-three planted violations are required** (AC-7). Mirror Phase 3 S1-05's validation discipline: insert a violation, watch CI fail with a useful error message, remove. Record evidence in `_attempts/S1-06.md` during execution. One-out-of-three is not enough — the validation precedent flagged that as a block-tier weakness.
- **`make fence` discoverability.** The `Makefile`'s `fence:` target should run *all* fence files. Read the current recipe (Phase 3 S1-05 landed `pytest -q tests/unit/test_pyproject_fence.py tests/fence/`); if the glob `tests/fence/` already covers the new files, no `Makefile` edit needed. Verify with a meta-test (the existing `tests/fence/test_fence_target_wiring.py` from Phase 3, if present — extend it).
- **`import-linter` `as_packages = true` is load-bearing.** Without it, only the top-level `codegenie.primitives.vuln_provenance` is covered; submodules (`types`, `protocols`, `errors`, `syft_reader`) leak. Phase 3's contract has this; mirror.
- **Phase 3 + Phase 0/1/2 regression suite stays green.** This story adds contracts + fence files but does NOT touch any existing production code. The risk is if extracting `has_any_annotation` into a shared module breaks Phase 3's test; verify Phase 3's `tests/fence/test_no_any_in_plugin_surface.py` still imports + runs after the extraction.
- **The `import-linter` runs in a separate CI job** (`make lint-imports`); the runtime-closure fence runs in `pytest tests/fence/`; the no-`Any` fence runs in `pytest tests/fence/`. All three must be green before merge. The story's done-criteria are AND across all three.
- **Pin the `Makefile` recipe shape if you edit it.** Use `tests/fence/` as a glob if it covers everything; otherwise enumerate the paths. Do not regress to `pytest -q tests/` (which would run the whole suite — way too slow for the `fence` target).
- **Forward to S5-01.** The byte-edit allowlist fence (Step 5) will assert that this story's edits to Phase 0–6.5 files are within its allowlist row reservations. This story makes ONE byte-edit to a Phase 0–6.5 file: a single `[[tool.importlinter.contracts]]` block append in `pyproject.toml`. It also adds FOUR new files under `tests/fence/` (additive new files under that directory are implicitly admitted; see ADR-0009 Decision text). Record both in `_attempts/S1-06.md` under a `## Forward-coupling to S5-01` section so S5-01's executor mechanically consumes them when writing the allowlist.
- **Marker-grammar Open/Closed (forward note).** `codegenie._phase3_fence.ALLOWED_MARKER_RE` is regex-hardcoded to `P3-ADR-\d{4}`. If a future Phase 7+ file ever needs an inline `# fence: any-allowed` exemption, do NOT widen this regex from Phase 7 — that's a byte-edit to `_phase3_fence.py`, which ADR-0009 forbids. The mechanically-additive path is a separate Phase-3-ADR-amendment story that lifts the grammar to phase-prefix-agnostic (`P\d-ADR-\d{4}`). Today's posture is "zero markers under Phase 7 surface" (mirrors Phase 3 S1-05 AC-5.d), so no marker is needed yet.
- **`lint-imports` invocation discipline (AC-2 + AC-7 Gate 1).** Invoke the `lint-imports` console script directly (resolved via `Path(sys.executable).parent / "lint-imports"` with a `shutil.which` fallback), not `make lint-imports`. The `make` indirection (a) requires a working `make` on every test host, (b) re-invokes pytest in some configs, (c) loses pytest's `capture_output` discipline. Mirror Phase 3's precedent at `tests/fence/test_lint_imports_catches_planted_leak.py`.
- **`PHASE7_ROOTS` extension, not `PHASE3_ROOTS` mutation.** Phase 7's `PHASE7_ROOTS: Final[tuple[Path, ...]]` lives in `tests/fence/test_no_any_in_provenance_surface.py`. Do NOT add a row to Phase 3's `PHASE3_ROOTS` in `_phase3_fence.py`. The per-phase pattern is intentional — rule-of-three for a shared `codegenie._fence_roots` registry has not been crossed; Phase 8+ becomes the 3rd consumer.
