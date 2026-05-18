# Story S1-05 — Phase 3 import-linter contracts + AST fences

**Step:** Step 1 — Scaffold packages, domain primitives, sum types, and structural CI fences
**Status:** Ready
**Effort:** M
**Depends on:** S1-02 (`src/codegenie/plugins/` package exists), S1-03 (`src/codegenie/transforms/outcomes.py` exists), S1-04 (`src/codegenie/transforms/{transform,apply_context}.py` exist)
**ADRs honored:** ADR-0010 (Consequences — `dict[str, Any]` banned under `src/codegenie/{plugins,transforms}/`; fence test enforces), ADR-0001 (`__init__.py` re-exports fence; contract-snapshot test surface), ADR-0011 (lint is the enforcement mechanism for honest-framed primitives — same posture here for the type-discipline fences)

## Context

Phase 3 introduces two new top-level packages (`src/codegenie/plugins/` and `src/codegenie/transforms/`) that will house every plugin-contract, recipe-engine, orchestrator, scorer, and event-log module shipped in Steps 2–6. The deterministic-only commitment ("no LLM in this loop") and the type-discipline commitment (no `Any`, no raw `str` for domain IDs) only hold if **CI hard-blocks regressions** before they land. This story is the CI fence that makes every later Step-1 / Step-2 / … story's typed primitives load-bearing: without these tests, a future story could quietly import `anthropic` under `src/codegenie/plugins/`, smuggle `dict[str, Any]` into a Pydantic model, or edit a Phase 0/1/2 file outside the ADR-permitted allowlist. The Phase 0 `tests/unit/test_pyproject_fence.py` is the precedent; this story extends the fence to the new Phase 3 surface and adds two AST-walk tests for shapes the dep-graph linter cannot see.

A surfacing note: the story manifest names `tools/lint/importlinter.cfg` as the contracts home, but the repo currently keeps `import-linter` contracts under `pyproject.toml [tool.importlinter]` (Phase 0 S1-05 / ADR phase-0006). **Honor the existing convention** — extend `pyproject.toml`, not a new `.cfg` file. Surface the manifest drift in `_validation/` follow-up rather than forking a parallel config (Rule 7).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C4 + C5 + C9 + C10` — names every module Phase 3 lands under `src/codegenie/{plugins,transforms}/`; the fence must cover all of them.
  - `../phase-arch-design.md §Testing strategy §CI gates` — the three new fence tests this story creates (`test_no_llm_in_transforms.py`, `test_no_any_in_plugin_surface.py`, `test_kernel_frozen.py`) plus `make lint-imports` extension.
  - `../High-level-impl.md §Step 1 §Features delivered` — `tools/lint/importlinter.cfg amended` (note: actually `pyproject.toml`) + the three fence tests.
- **Phase ADRs:**
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — Consequences clause: `dict[str, Any]` banned under `src/codegenie/{plugins,transforms}/` and `plugins/` by `tests/fence/test_no_any_in_contract_layer.py` (this story's `test_no_any_in_plugin_surface.py` is that file under the manifest name).
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — `src/codegenie/transforms/__init__.py` re-export list is itself a fence target.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — `tests/static/test_capability_fence.py` is the precedent style for ruff-custom-rule fences; this story's AST fences mirror that posture.
- **Existing code:**
  - `pyproject.toml §[tool.importlinter]` lines 294–329 — the existing Phase 0 contract style (`type = "forbidden"`, `source_modules`, `forbidden_modules`, `include_external_packages = true`); the new Phase 3 contracts mirror this.
  - `src/codegenie/_fence.py` + `tests/unit/test_pyproject_fence.py` — Phase 0 fence-test scaffolding (`FORBIDDEN_LLM_SDKS`, `scan_installed_distribution`, `parse_runtime_dep_names_from_toml`). Reuse the scanner; don't reimplement.
  - `tools/regenerate_probe_schemas.py` — Phase 1/2 precedent for an AST-walking helper run from CI (similar pattern to what `test_no_any_in_plugin_surface.py` needs).
  - `Makefile` lines 30–32 — `lint-imports:` target. No edits needed; it already reads `pyproject.toml`.

## Goal

Land three CI-gating fence tests + Phase 3 `import-linter` contracts in `pyproject.toml` so any later PR that imports an LLM SDK under `src/codegenie/{plugins,transforms}/`, introduces `Any` / `dict[str, Any]` annotations on the Phase 3 contract surface, or edits a Phase 0/1/2 file outside the ADR-permitted allowlist fails CI before merge.

## Acceptance criteria

- [ ] `pyproject.toml [tool.importlinter]` extended with two new `forbidden` contracts: one forbidding `FORBIDDEN_LLM_SDKS` (anthropic, langgraph, openai, langchain, transformers) imports under `codegenie.plugins`; one forbidding the same under `codegenie.transforms`. Both use `as_packages = true` so submodules are covered.
- [ ] `make lint-imports` exits 0 with the new contracts (no actual violations because Phase 3 surface is empty of LLM SDKs).
- [ ] `tests/fence/test_no_llm_in_transforms.py` — runtime-closure scan: `import codegenie.transforms; import codegenie.plugins;` followed by `sys.modules`-walk asserting no `FORBIDDEN_LLM_SDKS` member is present. Reuses `codegenie._fence.FORBIDDEN_LLM_SDKS`.
- [ ] `tests/fence/test_no_any_in_plugin_surface.py` — AST-walk over every `.py` file under `src/codegenie/plugins/` and `src/codegenie/transforms/`; fails if any function-arg, return, or class-attribute annotation is `Any`, `typing.Any`, `dict[str, Any]`, or `Dict[str, Any]`. (Allowlist: per-file inline marker `# fence: any-allowed [<adr>]` permits a single line; documented in ADR-0010 §Consequences.)
- [ ] `tests/fence/test_kernel_frozen.py` — git-diff-based fence: against the Phase 2 HEAD (resolved via the latest `feat(phase2/…)` commit on `master`), assert no file outside the ADR-allowlist has been modified by Phase 3 work. Allowlist: `src/codegenie/exec/__init__.py` (ALLOWED_BINARIES amendment, ADR-0012 — lands in S4-05, not this story); `pyproject.toml` (import-linter contract extension — this story); `src/codegenie/types/identifiers.py` (newtype additions — S1-01); `src/codegenie/types/__init__.py` (re-exports — S1-01).
- [ ] One **deliberately-planted violation** is added in a separate branch / commit, the fence catches it, the violation is removed, and the implementation notes record the green-after-removal evidence. (This is the "fail loud" guard — Rule 12. Without this evidence step, a broken fence ships silently.)
- [ ] `tests/fence/__init__.py` exists (test package marker).
- [ ] `make check` includes the new fence tests via existing pytest collection (the `tests/fence/` path is already in scope; verify with `pytest --collect-only tests/fence/`).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on touched files clean.
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. Extend `pyproject.toml [tool.importlinter]` with two new `[[tool.importlinter.contracts]]` blocks:
   - `name = "codegenie.plugins must not import LLM SDKs"`, `type = "forbidden"`, `source_modules = ["codegenie.plugins"]`, `as_packages = true`, `forbidden_modules = ["anthropic", "langgraph", "openai", "langchain", "transformers"]`.
   - Same for `source_modules = ["codegenie.transforms"]`.
2. Add `tests/fence/__init__.py`.
3. Add `tests/fence/test_no_llm_in_transforms.py`:
   - `import codegenie.plugins` + `import codegenie.transforms` (recursive — walk every submodule via `pkgutil.walk_packages`).
   - Assert `sys.modules.keys() & FORBIDDEN_LLM_SDKS == set()`.
   - Parametrized over each `FORBIDDEN_LLM_SDKS` member: a planted-import smoke test that asserts the scanner *would* catch the leak (use a synthetic `FakeModule` injected into `sys.modules` to verify the assertion fails when planted, succeeds when removed — exactly the Phase 0 `test_pyproject_fence.py` pattern).
4. Add `tests/fence/test_no_any_in_plugin_surface.py`:
   - Walk `src/codegenie/plugins/` and `src/codegenie/transforms/` recursively (use `pathlib.Path.rglob("*.py")`).
   - For each file, parse with `ast.parse(src)`, walk the tree, collect every `ast.Subscript` whose `.value.id == "Any"` or whose `.value.attr == "Any"`; collect `ast.Name(id="Any")` in `ast.AnnAssign`, `ast.arg`, `ast.FunctionDef.returns`; collect `ast.Subscript` with shape `dict[str, Any]` / `Dict[str, Any]`.
   - Honor `# fence: any-allowed` inline marker (line-comment scan via `tokenize`).
   - Plant a deliberate violation in a throwaway file under a `_planted_violation_test/` temp fixture (NOT under `src/`), verify the scanner catches it, remove.
5. Add `tests/fence/test_kernel_frozen.py`:
   - Run `git diff --name-only <phase2-baseline-ref>..HEAD` in the test, intersect with the path set under `src/codegenie/{,probes/,coordinator/,output/,cache/,grammars/,exec/,indices/,conventions/,types/}/` (Phase 0/1/2 surface) **minus the ADR-allowlist**. Assert the intersection is empty.
   - Baseline ref: read from a small `tests/fence/_phase2_baseline.txt` file checked into the repo (one line — the commit SHA at the time of S1-05 landing). Updating the file is an ADR amendment.
   - The allowlist itself is a `Final[frozenset[str]]` constant in the test, each entry commented with the owning ADR.
6. Run `pytest tests/fence/ -v` + `make lint-imports` + `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/fence/test_no_any_in_plugin_surface.py` (simplest of the three to land first)

```python
import ast
import pathlib

import pytest

PHASE3_ROOTS = [
    pathlib.Path("src/codegenie/plugins"),
    pathlib.Path("src/codegenie/transforms"),
]


def _walk_any_annotations(src: str) -> list[tuple[int, str]]:
    """Return (line, snippet) tuples for every Any / dict[str, Any] annotation."""
    tree = ast.parse(src)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # Direct `Any` reference
        if isinstance(node, ast.Name) and node.id == "Any":
            hits.append((node.lineno, ast.unparse(node)))
        # `dict[str, Any]` / `Dict[str, Any]`
        if isinstance(node, ast.Subscript):
            unparsed = ast.unparse(node)
            if "Any" in unparsed and ("dict[" in unparsed or "Dict[" in unparsed):
                hits.append((node.lineno, unparsed))
    return hits


def test_no_any_under_phase3_surface():
    violations: list[str] = []
    for root in PHASE3_ROOTS:
        for py in root.rglob("*.py"):
            src = py.read_text()
            hits = _walk_any_annotations(src)
            for lineno, snippet in hits:
                # Honor inline allowlist marker
                line_text = src.splitlines()[lineno - 1] if lineno <= len(src.splitlines()) else ""
                if "# fence: any-allowed" in line_text:
                    continue
                violations.append(f"{py}:{lineno}: {snippet}")
    assert violations == [], (
        "ADR-0010 §Consequences forbids Any / dict[str, Any] under Phase 3 "
        "contract surface. Violations:\n" + "\n".join(violations)
    )


def test_planted_violation_is_caught(tmp_path):
    # Planted-violation smoke test — proves the scanner actually checks.
    fake = tmp_path / "fake.py"
    fake.write_text("from typing import Any\nx: Any = 1\n")
    hits = _walk_any_annotations(fake.read_text())
    assert hits, "Scanner failed to catch a planted Any annotation"
```

State why it fails: until S1-02/S1-03/S1-04 land, `src/codegenie/plugins/` and `src/codegenie/transforms/` either don't exist (test errors on missing path) or are empty (test trivially passes — surface that with an explicit "≥ 1 file expected" guard so empty-dir doesn't silently green).

### Green — minimal pass
- The fence test passes because S1-02/S1-03/S1-04 already shipped no `Any` annotations.
- Add the two `import-linter` contracts in `pyproject.toml`; `make lint-imports` exits 0.
- Add `tests/fence/test_no_llm_in_transforms.py` mirroring the Phase 0 scanner pattern + planted-violation parametrize.
- Add `tests/fence/test_kernel_frozen.py` reading the baseline SHA from `_phase2_baseline.txt` (committed alongside).

### Refactor
- Lift the AST-walk helper into `tests/fence/_helpers.py` if it has > 1 consumer (`test_no_any_in_plugin_surface.py` is the only one in Step 1; defer until Step 2 has a second).
- Add docstrings to each fence test naming the owning ADR (mirror `tests/unit/test_pyproject_fence.py`'s docstring style).
- Edge cases:
  - **E10** (universal-fallback hidden by import error): not directly fenced here, but `test_kernel_frozen.py` will catch a Phase 3 PR that "fixes" the issue by editing Phase 1 loader code.
  - **Type-comment annotations** (`# type: dict[str, Any]`) bypass `ast`-walk — add a regex scan as a second pass; comment with the limitation.
  - **`TYPE_CHECKING` block imports** of `Any` are not annotations per se — the AST walk correctly ignores `ast.ImportFrom` nodes; double-check by inspecting an `if TYPE_CHECKING:` block in `apply_context.py` (S1-04).
- Confirm the planted-violation evidence is recorded in the attempt log (a 3-line "planted X → fence caught → removed → green" note).

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Extend `[tool.importlinter]` with two new Phase 3 LLM-SDK-forbidden contracts. |
| `tests/fence/__init__.py` | NEW — test package marker. |
| `tests/fence/test_no_llm_in_transforms.py` | NEW — runtime-closure scan + planted-violation parametrize. |
| `tests/fence/test_no_any_in_plugin_surface.py` | NEW — AST-walk for `Any` / `dict[str, Any]` under Phase 3 surface. |
| `tests/fence/test_kernel_frozen.py` | NEW — git-diff fence against Phase 2 baseline + ADR allowlist. |
| `tests/fence/_phase2_baseline.txt` | NEW — single line, commit SHA at S1-05 landing time. |

## Out of scope

- **`tests/static/test_capability_fence.py`** — handled by S4-05 (custom ruff rule for `*Capability(...)` construction).
- **`test_no_raw_str_for_domain_ids.py`** — ADR-0010 §Consequences names it as a future-state fence; deferred (not blocking Step 1; tracked as a Step-9 cross-cutting concern).
- **`test_event_taxonomy_complete.py`** — handled by S9-02 (event-taxonomy completeness + `$0.00` LLM-spend).
- **`test_phase5_contract_snapshot.py`** — handled by S6-06.
- **`test_plugin_protocol_frozen.py`** (ADR-0004 method-count assertion) — handled by S2-01 (lands with the `Plugin` Protocol itself).
- **`tools/lint/importlinter.cfg`** as a separate file — surface manifest drift in `_validation/` follow-up; this story honors the existing `pyproject.toml [tool.importlinter]` convention per Rule 7.

## Notes for the implementer

- **The planted-violation evidence step is load-bearing (Rule 12).** Without it, a broken fence test ships green by virtue of finding nothing to flag. The Phase 0 `test_pyproject_fence.py` does this via the parametrized `test_fence_catches_each_planted_llm_sdk` — mirror that pattern; don't shortcut. Record the green-after-removal evidence in `_attempts/S1-05.md`.
- **`as_packages = true` in import-linter** matters — without it, only `codegenie.plugins` (the `__init__.py`) is scanned, not submodules. Phase 0's contracts use `as_packages = false` for a deliberate reason (CLI entry only); Phase 3's contracts want submodule coverage.
- **The git-diff fence needs a stable baseline.** Don't try to compute "the Phase 2 ref" dynamically (CI-fragile); commit the SHA into `_phase2_baseline.txt` and update it via ADR amendment. Read it with `pathlib.Path("tests/fence/_phase2_baseline.txt").read_text().strip()`.
- **`pkgutil.walk_packages` triggers eager imports** — that's what makes the runtime-closure scan work, but it also means a syntax error in a Phase 3 module surfaces here, not at `pytest` collection time. Surface that as a clearer error message ("module X failed to import while running fence; fix the import before re-running the fence").
- **Inline allowlist marker `# fence: any-allowed [<adr>]`** — there should be zero of these in Step 1 (S1-02/S1-03/S1-04 are `Any`-clean by construction). Reserve the marker for *future* documented exceptions; a Step-1 PR introducing the marker fails review by convention.
- **ADR-0011 framing posture applies here.** These are *audit + lint* enforcement, not runtime guarantees. A determined plugin author who edits the test file in the same PR as their violation defeats the fence — that's an open Phase-11-grade problem (CODEOWNERS + PR review is the social anchor; Sigstore plugin signing is the eventual seam). Don't overclaim the fence's strength.
- **`make lint-imports` is already wired into `make check`** per Phase 0 ADR-0006; verify the new contracts run by inspecting `make check` output, not by adding a second invocation.
