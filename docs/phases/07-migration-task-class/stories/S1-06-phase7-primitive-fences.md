# Story S1-06 — Phase 7 LLM-SDK import-linter contract + no-`Any` AST fence

**Step:** Step 1 — Scaffold `vuln.provenance` primitive — newtypes, Provenance union, Protocol, errors, SyftSbom reader, fences
**Status:** Ready
**Effort:** S
**Depends on:** S1-03, S1-04, S1-05
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
  - `src/codegenie/_phase3_fence.py` + `tests/fence/test_no_any_in_plugin_surface.py` — Phase 3 `Any`-AST-walker (the `_phase3_fence._has_any` visitor function); reuse the walker, retarget the roots.
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
  A unit test parses `pyproject.toml`, locates the contract, asserts (a) `source_modules == ["codegenie.primitives.vuln_provenance"]`, (b) `forbidden_modules` is exactly the five SDKs (no drift), (c) `as_packages is True`, (d) `include_external_packages is True`.
- [ ] **AC-2 — `make lint-imports` green with the new contract.** Verified by a planted-positive subprocess test: a temp file `src/codegenie/primitives/vuln_provenance/_test_planted_leak.py` containing `import anthropic` is written, `make lint-imports` runs as a subprocess, exits non-zero, the failure message names the planted file. File removed after assertion (test uses `try/finally`).
- [ ] **AC-3 — `tests/fence/test_phase7_no_llm.py` — runtime-closure scan.** Reuses `codegenie._fence.FORBIDDEN_LLM_SDKS`. Mutation guards:
  - **AC-3.a** **Live check:** `pkgutil.walk_packages(codegenie.primitives.vuln_provenance.__path__)` followed by `set(sys.modules) & FORBIDDEN_LLM_SDKS == set()`.
  - **AC-3.b** **Per-SDK planted-positive** (`@pytest.mark.parametrize` over the five SDKs): inject a synthetic `sys.modules[<sdk>]` via a temp submodule under the primitive's path (`tmp_path` + `sys.path` prepend); assert the same scanner the live check uses catches it; remove the temp submodule.
  - **AC-3.c** **Metamorphic complement:** pre-populate `sys.modules["anthropic"]` directly (NOT via the primitive's closure); assert the fence does NOT fire. Proves scope is the primitive's closure, not the test runner's `sys.modules`.
  - **AC-3.d** **Import-success guard:** assert `"codegenie.primitives.vuln_provenance" in sys.modules` after the walk — silently-caught `ImportError` must not green the test.
  - **AC-3.e** **ADR framing in docstring:** module-level docstring names ADR-0004 + production ADR-0005; meta-test scans for the required strings.
- [ ] **AC-4 — `tests/fence/test_no_any_in_provenance_surface.py` — AST-walk fence.** Mirrors Phase 3's structural visitor (NOT shotgun `ast.walk`):
  - Roots: every `.py` file under `src/codegenie/primitives/vuln_provenance/`.
  - Walker: `ast.NodeVisitor` restricted to `ast.AnnAssign.annotation`, `ast.arg.annotation`, `ast.FunctionDef.returns`, `ast.AsyncFunctionDef.returns`, `ast.ClassDef`-body-level `AnnAssign`.
  - Flags: any subtree of those annotations containing `ast.Name(id="Any")` or `ast.Attribute(attr="Any")`.
  - **The walker is the SAME function** as Phase 3's `src/codegenie/_phase3_fence.py::_has_any` (or equivalent name) — **reuse, do not fork**. If Phase 3's walker can be retargeted by passing roots, do that; if not, extract the visitor into a shared helper module.
  - **Floor guard:** each root directory exists AND contains ≥ 1 non-`__init__.py` Python module (parametrized assertion fails loudly if the primitive directory is deleted).
  - **Per-shape planted-violation matrix:** parametrized over the existing Phase 3 mutation matrix (`x: Any`, `def f(x: Any) -> None`, `def f() -> Any`, `x: dict[str, Any]`, `x: list[Any]`, `x: typing.Any`, `x: "Any"` forward-ref, etc.) — each row is one mutation guard.
  - **Negative cases:** `x: int = 1`, `isinstance(obj, Any)` (runtime, not annotation), `if TYPE_CHECKING: from typing import Any` (import, not annotation) → NOT flagged.
- [ ] **AC-5 — `syft_reader.py` is exempt from the `Any` fence.** The deliberate `extra="allow"` admits a `__pydantic_extra__: dict[str, Any]` shape internally to Pydantic, but the file's *declared annotations* must stay typed. The fence walks `syft_reader.py` and flags any **declared** `Any` annotation; the Pydantic-internal `__pydantic_extra__` field is generated, not declared, so it does not appear in the AST. A test asserts: `_has_any("syft_reader.py source")` returns no findings today (i.e., the S1-05 implementation must not have introduced any `Any` annotations).
- [ ] **AC-6 — `make fence` wiring.** The `Makefile` `fence:` target's recipe includes `tests/fence/test_phase7_no_llm.py` and `tests/fence/test_no_any_in_provenance_surface.py` (or, equivalently, a directory glob that covers them). A meta-test parses the `Makefile`'s `fence:` recipe and asserts both fence test paths are present (or that the glob covers them).
- [ ] **AC-7 — Three-out-of-three planted-violation evidence** (mirrors Phase 3 S1-05's discipline): for each of the three CI gates (import-linter contract, no-LLM runtime fence, no-`Any` AST fence), the story's `_attempts/` log records evidence that a deliberately-planted violation (a) was inserted, (b) caused CI to fail with a useful error message, (c) was removed before merge. The evidence lives in `_attempts/S1-06.md` (created during execution).
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
   - If `codegenie._phase3_fence` has an extractable `_has_any` (or `AnyAnnotationVisitor`) helper, reuse it. Otherwise, refactor into a shared `codegenie._fence` helper and update Phase 3's import (additive, surgical — read Phase 3's fence file first to confirm shape).
   - Root: `src/codegenie/primitives/vuln_provenance/`.
   - Floor-guard test: assert the root exists + has ≥ 1 non-`__init__.py` module.
   - Live check: walk every `.py`, run the visitor, assert no findings.
   - Planted-violation parametrized matrix (mirror Phase 3's table).
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
"""Phase 7 no-Any AST fence — ADR-0004 + Phase 3 ADR-0010.

AST-walks src/codegenie/primitives/vuln_provenance/ and rejects any
declared `Any` / `dict[str, Any]` annotation. The deliberate `extra='allow'`
on SyftSbom is NOT a declared `Any` — it surfaces internally via
`__pydantic_extra__` which is not in the AST. This fence remains green
after S1-05.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from codegenie._phase3_fence import (  # or wherever the shared helper lives
    has_any_annotation,
)

PRIMITIVE_ROOT = Path("src/codegenie/primitives/vuln_provenance")


# --- AC-4 Floor guard --------------------------------------------------------

def test_primitive_root_exists_and_nonempty():
    assert PRIMITIVE_ROOT.is_dir()
    python_files = [
        p for p in PRIMITIVE_ROOT.rglob("*.py") if p.name != "__init__.py"
    ]
    assert python_files, f"{PRIMITIVE_ROOT} has no non-__init__.py modules"


# --- AC-4 Live check ---------------------------------------------------------

def test_no_any_in_primitive_surface():
    findings = []
    for py in PRIMITIVE_ROOT.rglob("*.py"):
        tree = ast.parse(py.read_text())
        hits = has_any_annotation(tree)
        if hits:
            findings.append((py, hits))
    assert findings == [], f"Any annotations found in primitive: {findings}"


# --- AC-4 Per-shape planted-violation matrix --------------------------------

@pytest.mark.parametrize("snippet,expected_hit", [
    ("x: Any = 1", True),
    ("def f(x: Any) -> None: ...", True),
    ("def f() -> Any: ...", True),
    ("x: dict[str, Any] = {}", True),
    ("x: list[Any] = []", True),
    ("x: typing.Any = 1", True),
    ('x: "Any" = 1', True),
    ("x: int = 1", False),
    ("isinstance(obj, Any)", False),
])
def test_walker_per_shape(snippet, expected_hit):
    tree = ast.parse(snippet)
    hits = has_any_annotation(tree)
    assert bool(hits) is expected_hit
```

State why it fails today: (a) the `import-linter` contract for `codegenie.primitives.vuln_provenance` does not exist; (b) `tests/fence/test_phase7_no_llm.py` does not exist; (c) `tests/fence/test_no_any_in_provenance_surface.py` does not exist; (d) the shared `has_any_annotation` helper may need extraction.

### Green — make it pass
- Add the `[[tool.importlinter.contracts]]` block to `pyproject.toml`.
- Land the three new fence files; reuse `codegenie._fence.FORBIDDEN_LLM_SDKS` + `codegenie._phase3_fence.has_any_annotation` (or extract the latter into a shared helper if needed).
- Wire `make fence` (verify `tests/fence/` glob covers the new files).
- Plant + remove each violation to gather AC-7 evidence.

### Refactor — clean up
- Each fence file's module docstring names ADR-0004 + production ADR-0005 + ADR-0011 ("audit + lint posture, not runtime").
- If `has_any_annotation` was extracted, update Phase 3's existing test to import from the new home (surgical, additive).
- Confirm `make fence` runs all four fence tests (Phase 0, Phase 3 transforms, Phase 3 plugins, Phase 7).

## Files to touch
| Path | Why |
|---|---|
| `pyproject.toml` | Add one `[[tool.importlinter.contracts]]` block for the primitive. |
| `tests/fence/test_phase7_no_llm.py` | NEW — runtime-closure scan; planted-positive + metamorphic complement. |
| `tests/fence/test_no_any_in_provenance_surface.py` | NEW — AST-walk fence; floor guard + planted-violation matrix. |
| `tests/fence/test_phase7_importlinter_contracts_shape.py` | NEW — parse `pyproject.toml`; assert the new contract's shape (AC-1). |
| `tests/fence/test_lint_imports_catches_phase7_planted_leak.py` | NEW — subprocess `make lint-imports` planted-positive (AC-2). |
| `Makefile` (verify, possibly amend) | Ensure `fence:` target's recipe runs the new fence files. |
| `src/codegenie/_phase3_fence.py` or equivalent (read first) | Possibly extract `has_any_annotation` into a shared helper if not already. |

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
- **Forward to S5-01.** The byte-edit allowlist fence (Step 5) will assert that this story's changes to `pyproject.toml` (one contract block) and `tests/fence/` (three new files) are within its allowlist row reservations. Coordinate file paths with the S5-01 implementer; if S5-01 has not yet been written, leave a `# TODO(S5-01)` marker in this story's `_attempts/` log noting "this story's `pyproject.toml` edit must be on the S5-01 byte-edit allowlist."
