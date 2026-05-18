# Story S1-05 — Path-scoped pyproject fence amendment

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** Ready
**Effort:** M
**Depends on:** S1-04
**ADRs honored:** ADR-0003 (path-scoped fence amendment — admit `anthropic`/`chromadb`/`fastembed`/`onnxruntime` only outside the gather pipeline), Phase-0 ADR-0002 (production fence preserved; `FORBIDDEN_LLM_SDKS` *narrows* honestly)

## Context

Phase 0 established a closure-scoped fence: `FORBIDDEN_LLM_SDKS = frozenset({"anthropic", "langgraph", "openai", "langchain", "transformers"})` enforced by `tests/unit/test_pyproject_fence.py`. Phase 4 needs `anthropic` (the LLM adapter), `chromadb` (vector store), `fastembed` (embeddings runtime), and `onnxruntime` (ONNX session) — but commitment §2.1 ("no LLM anywhere in the gather pipeline") still must hold for `src/codegenie/{probes,coordinator,cache,output,schema}/`. The critic correctly identified this as "the single most load-bearing change in Phase 4 and none of the three designs writes out the exact set membership change" (Gap 5). The honest framing: the original deny-set **narrows** (anthropic moves out) while a path-scoped fence compensates. This story is mechanically delicate — get it wrong and the next 100 PRs run under a silently-broken invariant.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis → Gap 5: FORBIDDEN_LLM_SDKS path-scope mechanics — exactly where the fence amendment lands` — the exact set-membership change and assertion shape.
  - `../phase-arch-design.md §Goals — G5` — "LLM closure fenced; original deny-list invariant preserved."
  - `../phase-arch-design.md §Development view` — `src/codegenie/fallback/` and `src/codegenie/rag/` are the only admitted homes.
  - `../phase-arch-design.md §Testing strategy → CI gates` — `tests/fence/test_pyproject_fence_phase4.py` is a CI gate.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-path-scoped-fence-amendment.md` — the canonical decision; the exact `GATHER_PIPELINE_PATHS`, `PHASE4_ADMITTED_PACKAGES`, `PHASE4_STILL_FORBIDDEN` set declarations live in this ADR; mirror them verbatim.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — commitment §2.1.
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — probe contract stability.
  - Phase 0 ADR-0002 — production fence (`pyproject.toml` + `import-linter`).
- **Source design:**
  - `../final-design.md §Load-bearing commitments check §2.1` — the exact diff.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `tests/unit/test_pyproject_fence.py` — Phase-0 closure-scoped fence; this story **does not edit** the test logic but **does** update `EXPECTED_FORBIDDEN_SET`.
  - `src/codegenie/_fence.py` — the production-side `FORBIDDEN_LLM_SDKS` constant; narrows in lockstep.
  - `pyproject.toml § [project.dependencies]` — where `anthropic`, `chromadb`, `fastembed`, `onnxruntime`, `keyring` are added (NOT under `[project.optional-dependencies]`).
  - `pyproject.toml § [project.optional-dependencies].agents` — Phase-0 reserved this slot for "Phase 4+ LLM SDKs". The arch + ADR-0003 deliberately depart from this prior plan: the LLM SDK is now `[project.dependencies]` runtime, gated by **path-scope** rather than **extras**. Surface this as a Rule-7 conflict in the attempt log and pick path-scope (the more recent, more strongly-typed choice per ADR-0003); update the `[project.optional-dependencies].agents` comment to reflect the new posture.
  - `pyproject.toml § [tool.importlinter]` — existing import-linter contracts; S1-06 grows this; this story focuses on the pyproject-deps + pytest-fence pair.

## Goal

Land a path-scoped fence: add `anthropic`/`chromadb`/`fastembed`/`onnxruntime`/`keyring` to `[project.dependencies]`; narrow `FORBIDDEN_LLM_SDKS` to remove `anthropic` and add `sentence_transformers`+`torch`; ship `tests/fence/test_pyproject_fence_phase4.py` enforcing path-scope (no gather-pipeline source imports the admitted packages; only `src/codegenie/fallback/leaf/anthropic_adapter.py` imports `anthropic`; only `src/codegenie/rag/` imports `chromadb`/`fastembed`/`onnxruntime`).

## Acceptance criteria

### Set-membership change (the honest amendment)

- [ ] AC-1 — `src/codegenie/_fence.py` `FORBIDDEN_LLM_SDKS` is updated to `frozenset({"langgraph", "openai", "langchain", "transformers", "sentence_transformers", "torch"})` — exactly six members. `anthropic` is removed; `sentence_transformers` + `torch` are added (so the path-scoped fence amendment narrows the LLM set honestly without leaving a hole for the alternative-embeddings backends).
- [ ] AC-2 — `tests/unit/test_pyproject_fence.py` `EXPECTED_FORBIDDEN_SET` updated to match AC-1's six members; **all five existing Phase-0 tests still pass against the new set**. The parametrized `test_fence_catches_each_planted_llm_sdk` covers all six SDKs.
- [ ] AC-3 — The Phase-0 test's comment / docstring is updated **only** to note the narrowing (`anthropic` moved to path-scope, `sentence_transformers`+`torch` added) — no behavior change to the closure-scoped scan logic.

### pyproject deps

- [ ] AC-4 — `pyproject.toml § [project.dependencies]` adds `anthropic`, `chromadb`, `fastembed`, `onnxruntime`, `keyring`, all with strict version constraints (lower-and-upper bound like `anthropic>=0.40.0,<1.0.0`; exact lower/upper to be picked at implementation time and surfaced in the attempt log).
- [ ] AC-5 — `pyproject.toml § [project.optional-dependencies].agents` comment updated — the previous "LLM SDKs land here" comment is now stale; replace with `# Reserved for Phase 6 (langgraph); the Phase-0 ADR-0006 plan to gate `anthropic` via extras was superseded by Phase-4 ADR-0003 path-scoping.`
- [ ] AC-6 — Phase-0 fence `make fence` runs green after dependency addition (the Phase-0 test scans the *installed distribution*; it now finds zero match against the narrowed `FORBIDDEN_LLM_SDKS`).

### Path-scoped fence — new test

- [ ] AC-7 — `tests/fence/test_pyproject_fence_phase4.py` lands with these module-level `Final` constants verbatim from ADR-0003:
  ```python
  GATHER_PIPELINE_PATHS: Final[frozenset[str]] = frozenset({
      "src/codegenie/probes/", "src/codegenie/coordinator/",
      "src/codegenie/cache/", "src/codegenie/output/", "src/codegenie/schema/",
  })
  PHASE4_ADMITTED_PACKAGES: Final[frozenset[str]] = frozenset(
      {"anthropic", "chromadb", "fastembed", "onnxruntime"}
  )
  PHASE4_STILL_FORBIDDEN: Final[frozenset[str]] = frozenset(
      {"langgraph", "openai", "langchain", "transformers",
       "sentence_transformers", "torch"}
  )
  ```
- [ ] AC-8 — The Phase-4 fence test ships four assertions:
  1. **No source under `GATHER_PIPELINE_PATHS` imports any package in `PHASE4_ADMITTED_PACKAGES ∪ PHASE4_STILL_FORBIDDEN`** (AST-walk every `.py`; collect top-level `import X` and `from X.* import ...` against the package roots).
  2. **No source anywhere imports any package in `PHASE4_STILL_FORBIDDEN`** (closure-wide).
  3. **`anthropic` is imported only by `src/codegenie/fallback/leaf/anthropic_adapter.py`** (single permitted callsite).
  4. **`chromadb`/`fastembed`/`onnxruntime` are imported only by modules under `src/codegenie/rag/`** (rag-package scope).
- [ ] AC-9 — Each assertion failure raises a diagnostic naming **the offending file path AND the offending package** (e.g., `"src/codegenie/probes/foo.py imports forbidden package 'anthropic' (PHASE4_ADMITTED_PACKAGES are admitted only under src/codegenie/fallback/leaf/)"`). The diagnostic is the mutation guard: a regression that silently widens the scope produces a high-signal failure.
- [ ] AC-10 — **Deliberate-violation fixtures (negative tests).** Four small fixture files committed under `tests/fence/_fixtures_phase4/` exercise each assertion:
  - `_fixtures_phase4/violator_probe_imports_anthropic.py.txt` (file extension `.py.txt` so it doesn't run as a test; the fence test loads it as text + AST-walks it as if under `src/codegenie/probes/`).
  - `_fixtures_phase4/violator_random_file_imports_torch.py.txt` (PHASE4_STILL_FORBIDDEN check).
  - `_fixtures_phase4/violator_non_leaf_imports_anthropic.py.txt` (anthropic outside `leaf/`).
  - `_fixtures_phase4/violator_non_rag_imports_chromadb.py.txt` (chromadb outside `rag/`).
- [ ] AC-11 — Each fixture has a paired `tests/fence/test_pyproject_fence_phase4_negatives.py` test that synthetically routes the fixture through the same scanner the production fence uses (refactor the scanner into a function `_walk_imports(paths: Sequence[Path], gathered_paths: frozenset[str]) -> set[ImportViolation]`) and asserts the violation is detected. **Critical:** the negative test uses the SAME scanner — mutating the production scanner kills both. (Mirror the Phase-0 fence pattern at `tests/unit/test_pyproject_fence.py` where the deliberate-negative tests invoke the same production code path.)

### Targeted fence assertions

- [ ] AC-12 — `tests/fence/test_only_leaf_imports_anthropic.py` — AST source-scan asserts `import anthropic` (or `from anthropic import *`) appears in **exactly one** file: `src/codegenie/fallback/leaf/anthropic_adapter.py`. (Skeleton: until S3-02 lands the adapter, the test asserts the count is *at most* one and names the only-permitted path. Test asserts the exact filename match if any imports exist.)
- [ ] AC-13 — `tests/fence/test_rag_no_anthropic.py` — AST source-scan asserts no module under `src/codegenie/rag/` imports `anthropic` (forward-defensive even though no rag module would have a reason to).
- [ ] AC-14 — `tests/fence/test_no_langgraph_in_phase4.py` — closure-wide AST scan for `import langgraph` / `from langgraph` — must be zero. (Phase 6 owns the langgraph admission ADR.)

### Verification + hygiene

- [ ] AC-15 — `make check` green after the dependency addition. `make fence` (the Phase-0 test) green. The new `tests/fence/test_pyproject_fence_phase4.py` and its negative tests green.
- [ ] AC-16 — `mypy --strict`, `ruff check`, `ruff format --check` clean on touched files.
- [ ] AC-17 — `pyproject.toml` lockfile (`uv.lock`) re-locked with the new deps; CI matrix re-runs against the regenerated closure.
- [ ] AC-18 — The TDD plan's red tests exist, are committed, and are green.

## Implementation outline

1. **Add the deps to `pyproject.toml`.** Pick strict-pinned lower+upper bounds for `anthropic`, `chromadb`, `fastembed`, `onnxruntime`, `keyring`. Surface the picked versions in the attempt log.
2. **Re-lock `uv.lock`.** Run `uv lock` (or the project's lock command per `Makefile`) and commit the result.
3. **Narrow `FORBIDDEN_LLM_SDKS`** in `src/codegenie/_fence.py` to the AC-1 six-member set. Update the module docstring to reflect the narrowing (mention ADR-0003 explicitly).
4. **Update `EXPECTED_FORBIDDEN_SET`** in `tests/unit/test_pyproject_fence.py` and update the supporting comment.
5. **Update the `[project.optional-dependencies].agents` comment** in `pyproject.toml` per AC-5.
6. **Land the scanner helper.** Add `tests/fence/_phase4_scanner.py` (test-package-private) containing the AST-walking function `walk_imports(roots: Sequence[Path]) -> set[ImportViolation]`. Define `ImportViolation = NamedTuple("ImportViolation", [("file", str), ("package", str), ("reason", str)])`. The scanner returns the empty set on clean trees; violations carry the file + package + reason (mutation guard for the diagnostic).
7. **Land `tests/fence/test_pyproject_fence_phase4.py`** with the four AC-8 assertions consuming the scanner.
8. **Land the fixture files** under `tests/fence/_fixtures_phase4/` and the paired `test_pyproject_fence_phase4_negatives.py`.
9. **Land the three targeted fence tests** (`test_only_leaf_imports_anthropic.py`, `test_rag_no_anthropic.py`, `test_no_langgraph_in_phase4.py`).
10. Run `make check` locally; verify all fences green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/fence/test_pyproject_fence_phase4.py`

```python
"""Phase-4 path-scoped fence (ADR-0003).

This complements (does not replace) the Phase-0 closure-scoped fence at
``tests/unit/test_pyproject_fence.py``. The original ``FORBIDDEN_LLM_SDKS``
*narrows* honestly — anthropic moves to path-scope here, and
sentence_transformers/torch are added (so we don't leave a hole for an
alternative embeddings backend).
"""
from __future__ import annotations

import ast
import pathlib
from typing import Final

from tests.fence._phase4_scanner import ImportViolation, walk_imports

REPO_ROOT: Final = pathlib.Path(__file__).resolve().parents[2]

GATHER_PIPELINE_PATHS: Final[frozenset[str]] = frozenset({
    "src/codegenie/probes/", "src/codegenie/coordinator/",
    "src/codegenie/cache/", "src/codegenie/output/", "src/codegenie/schema/",
})
PHASE4_ADMITTED_PACKAGES: Final[frozenset[str]] = frozenset(
    {"anthropic", "chromadb", "fastembed", "onnxruntime"}
)
PHASE4_STILL_FORBIDDEN: Final[frozenset[str]] = frozenset(
    {"langgraph", "openai", "langchain", "transformers",
     "sentence_transformers", "torch"}
)
ONLY_LEAF_ANTHROPIC: Final[pathlib.Path] = (
    REPO_ROOT / "src/codegenie/fallback/leaf/anthropic_adapter.py"
)
RAG_PACKAGE: Final[pathlib.Path] = REPO_ROOT / "src/codegenie/rag"


def _src_files_under(rel_root: str) -> list[pathlib.Path]:
    root = REPO_ROOT / rel_root.rstrip("/")
    if not root.exists():
        return []
    return [p for p in root.rglob("*.py")]


def test_gather_pipeline_has_no_phase4_admitted_or_forbidden_imports() -> None:
    """AC-8 (1) — the gather pipeline closure stays LLM-free."""
    forbidden = PHASE4_ADMITTED_PACKAGES | PHASE4_STILL_FORBIDDEN
    offenders: list[ImportViolation] = []
    for rel in GATHER_PIPELINE_PATHS:
        violations = walk_imports(_src_files_under(rel), forbidden=forbidden)
        offenders.extend(violations)
    assert not offenders, (
        f"Gather-pipeline source imports forbidden package(s); ADR-0003 broken: "
        f"{offenders}"
    )


def test_closure_wide_phase4_still_forbidden() -> None:
    """AC-8 (2) — no source anywhere imports PHASE4_STILL_FORBIDDEN packages."""
    all_src = _src_files_under("src/")
    offenders = walk_imports(all_src, forbidden=PHASE4_STILL_FORBIDDEN)
    assert not offenders, (
        f"Source imports PHASE4_STILL_FORBIDDEN package(s) (langgraph is "
        f"Phase 6's job; torch / sentence_transformers are not admitted): "
        f"{offenders}"
    )


def test_anthropic_imported_only_by_leaf_adapter() -> None:
    """AC-8 (3) — anthropic is single-callsite (the leaf adapter)."""
    all_src = _src_files_under("src/")
    offenders = [
        v for v in walk_imports(all_src, forbidden={"anthropic"})
        if pathlib.Path(v.file).resolve() != ONLY_LEAF_ANTHROPIC.resolve()
    ]
    assert not offenders, (
        f"`anthropic` may be imported only by {ONLY_LEAF_ANTHROPIC}; offenders: "
        f"{offenders}"
    )


def test_chromadb_fastembed_onnxruntime_only_under_rag() -> None:
    """AC-8 (4) — rag-substrate deps may live only under src/codegenie/rag/."""
    all_src = _src_files_under("src/")
    rag_resolved = RAG_PACKAGE.resolve()
    offenders = [
        v for v in walk_imports(
            all_src, forbidden={"chromadb", "fastembed", "onnxruntime"}
        )
        if rag_resolved not in pathlib.Path(v.file).resolve().parents
    ]
    assert not offenders, (
        f"`chromadb`/`fastembed`/`onnxruntime` may be imported only under "
        f"{RAG_PACKAGE}; offenders: {offenders}"
    )
```

The scanner helper:

```python
# tests/fence/_phase4_scanner.py
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ImportViolation:
    file: str
    package: str
    reason: str


def _top_level_packages(tree: ast.AST) -> set[str]:
    """Return the set of top-level package names imported by `tree`."""
    pkgs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                pkgs.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            pkgs.add(node.module.split(".", 1)[0])
    return pkgs


def walk_imports(
    files: Sequence[Path], *, forbidden: Iterable[str]
) -> list[ImportViolation]:
    """Return one ImportViolation per (file, forbidden-package) pair found."""
    forbidden_set = set(forbidden)
    out: list[ImportViolation] = []
    for f in files:
        try:
            tree = ast.parse(f.read_text())
        except (UnicodeDecodeError, SyntaxError):
            continue
        for pkg in _top_level_packages(tree):
            if pkg in forbidden_set:
                out.append(ImportViolation(
                    file=str(f), package=pkg,
                    reason=f"{pkg} imported by {f}; ADR-0003 path-scope violated",
                ))
    return out
```

The negative tests (mirrors the Phase-0 deliberate-negative pattern):

```python
# tests/fence/test_pyproject_fence_phase4_negatives.py
"""Mutation-guard negative tests: same scanner the live fence uses."""
from __future__ import annotations

import pathlib
import pytest

from tests.fence._phase4_scanner import walk_imports

FIXTURES = pathlib.Path(__file__).parent / "_fixtures_phase4"


@pytest.mark.parametrize(
    "fixture_name,forbidden_pkg",
    [
        ("violator_probe_imports_anthropic.py.txt", "anthropic"),
        ("violator_random_file_imports_torch.py.txt", "torch"),
        ("violator_non_leaf_imports_anthropic.py.txt", "anthropic"),
        ("violator_non_rag_imports_chromadb.py.txt", "chromadb"),
    ],
)
def test_scanner_catches_each_planted_violation(
    tmp_path: pathlib.Path, fixture_name: str, forbidden_pkg: str
) -> None:
    fixture = FIXTURES / fixture_name
    target = tmp_path / "violator.py"
    target.write_text(fixture.read_text())
    out = walk_imports([target], forbidden={forbidden_pkg})
    assert len(out) == 1, f"Scanner missed planted {forbidden_pkg} in {fixture_name}: {out}"
    assert out[0].package == forbidden_pkg
```

Fixture contents (`tests/fence/_fixtures_phase4/violator_probe_imports_anthropic.py.txt`):
```python
"""DELIBERATE VIOLATION FIXTURE — paired with test_pyproject_fence_phase4_negatives.py.
Mutation guard: removing `anthropic` from the scanner's forbidden set kills this test.
"""
import anthropic  # type: ignore[import-untyped]
```

(The other three fixtures are similar one-line `import` lines for `torch`, `anthropic`, `chromadb`.)

The targeted skeletons:

```python
# tests/fence/test_only_leaf_imports_anthropic.py
import ast, pathlib
import codegenie
_LEAF = pathlib.Path(codegenie.__file__).parent / "fallback/leaf/anthropic_adapter.py"
_SRC_ROOT = pathlib.Path(codegenie.__file__).parent

def test_only_leaf_imports_anthropic():
    offenders = []
    for py in _SRC_ROOT.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            is_import = (
                (isinstance(node, ast.Import) and any(a.name.split(".",1)[0] == "anthropic" for a in node.names))
                or (isinstance(node, ast.ImportFrom) and node.module and node.module.split(".",1)[0] == "anthropic")
            )
            if is_import and py.resolve() != _LEAF.resolve():
                offenders.append((str(py), node.lineno))
    assert not offenders, f"Only {_LEAF} may `import anthropic`; offenders: {offenders}"
```

```python
# tests/fence/test_rag_no_anthropic.py
import ast, pathlib
import codegenie
_RAG = pathlib.Path(codegenie.__file__).parent / "rag"

def test_rag_does_not_import_anthropic():
    if not _RAG.exists(): return
    offenders = []
    for py in _RAG.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Import) and any(a.name.split(".",1)[0] == "anthropic" for a in node.names)):
                offenders.append((str(py), node.lineno))
    assert not offenders, f"rag/ must not import anthropic: {offenders}"
```

```python
# tests/fence/test_no_langgraph_in_phase4.py
import ast, pathlib
import codegenie
_ROOT = pathlib.Path(codegenie.__file__).parent

def test_no_langgraph_anywhere():
    offenders = []
    for py in _ROOT.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            is_import = (
                (isinstance(node, ast.Import) and any(a.name.split(".",1)[0] == "langgraph" for a in node.names))
                or (isinstance(node, ast.ImportFrom) and node.module and node.module.split(".",1)[0] == "langgraph")
            )
            if is_import:
                offenders.append((str(py), node.lineno))
    assert not offenders, f"langgraph is Phase 6's admission, not Phase 4: {offenders}"
```

State why it fails: `ImportError` — the `tests/fence/_phase4_scanner` module + the fixtures + the updated `FORBIDDEN_LLM_SDKS` don't exist yet.

### Green — make it pass

1. Update `src/codegenie/_fence.py` `FORBIDDEN_LLM_SDKS` to the six-member set.
2. Update `tests/unit/test_pyproject_fence.py` `EXPECTED_FORBIDDEN_SET` to match.
3. Add deps to `pyproject.toml § [project.dependencies]`; re-lock `uv.lock`.
4. Land `tests/fence/_phase4_scanner.py`, the fence test file, the four fixtures, the negative tests, and the three targeted tests.

### Refactor — clean up

- Lift `GATHER_PIPELINE_PATHS`, `PHASE4_ADMITTED_PACKAGES`, `PHASE4_STILL_FORBIDDEN` to module-level `Final` constants (already in the AC-7 shape).
- Ensure the scanner's `_top_level_packages` covers both `import X` and `from X.* import ...` forms (including relative imports — `node.level > 0` is intra-package; those are NOT third-party, so the scanner ignores them, which is correct).
- Document in the fence-file module docstring the **narrowing** framing: "The Phase-0 set narrows honestly; admission moves to path-scope per ADR-0003."
- Edge cases enumerated in arch §Edge cases that touch this code: #15 (planted-in-extras still ignored — Phase-0 invariant preserved).

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Add `anthropic`/`chromadb`/`fastembed`/`onnxruntime`/`keyring` to `[project.dependencies]`; update `[project.optional-dependencies].agents` comment. |
| `uv.lock` | Re-locked. |
| `src/codegenie/_fence.py` | Narrow `FORBIDDEN_LLM_SDKS` to the AC-1 six members; update module docstring. |
| `tests/unit/test_pyproject_fence.py` | Update `EXPECTED_FORBIDDEN_SET`; update comment naming ADR-0003. |
| `tests/fence/_phase4_scanner.py` | NEW — AST-walking scanner used by both the live fence and the negative tests. |
| `tests/fence/test_pyproject_fence_phase4.py` | NEW — four AC-8 path-scope assertions. |
| `tests/fence/test_pyproject_fence_phase4_negatives.py` | NEW — four deliberate-violation fixture tests (mutation guard). |
| `tests/fence/_fixtures_phase4/violator_probe_imports_anthropic.py.txt` | NEW — fixture; not auto-discovered as a test. |
| `tests/fence/_fixtures_phase4/violator_random_file_imports_torch.py.txt` | NEW — fixture. |
| `tests/fence/_fixtures_phase4/violator_non_leaf_imports_anthropic.py.txt` | NEW — fixture. |
| `tests/fence/_fixtures_phase4/violator_non_rag_imports_chromadb.py.txt` | NEW — fixture. |
| `tests/fence/test_only_leaf_imports_anthropic.py` | NEW — single-callsite assertion for `anthropic`. |
| `tests/fence/test_rag_no_anthropic.py` | NEW — `rag/` may not import `anthropic`. |
| `tests/fence/test_no_langgraph_in_phase4.py` | NEW — closure-wide langgraph rejection. |

## Out of scope

- **`import-linter` contracts mirroring the fence** — S1-06 (mirror at lint-time).
- **`tests/fence/test_kernel_frozen.py`** — S1-07 (zero edits to Phase 0/1/2/3 kernel files).
- **Actually adding `import anthropic` somewhere** — S3-02 (the leaf adapter).
- **Actually adding `import chromadb` / `fastembed` / `onnxruntime` somewhere** — S4-03, S4-01.
- **`./node_modules/.bin/tsc` `ALLOWED_BINARIES` amendment** — S6-04.
- **Re-running `make check` to verify post-amendment greenness** — performed locally; CI gates verify on merge.

## Notes for the implementer

- **Surface the Phase-0 ADR-0006 plan-departure per Rule 7.** Phase 0 ADR-0006 reserved `[project.optional-dependencies].agents` for "Phase 4+ LLM SDKs"; this story departs by putting `anthropic` in `[project.dependencies]` runtime under path-scope. Cross-link Phase-0 ADR-0006 from the attempt log; update the `pyproject.toml` comment so the next reader sees the supersedure.
- **The `FORBIDDEN_LLM_SDKS` narrowing is honest, not a relaxation.** Two new SDKs (`sentence_transformers`, `torch`) join the deny-set so the closure-scoped fence is *stricter*, not weaker. ADR-0003's "honestly narrows" framing is load-bearing — the test diagnostic and the ADR text must use that word.
- **Strict version pinning is non-optional for the new deps.** Pick a lower bound that matches the SDK feature set the Phase-4 ADRs assume (Anthropic SDK supporting `response_format=` per ADR-0001; chromadb supporting embedded mode per ADR-0016). Pick an upper bound that's open enough to admit patch releases but closed enough to prevent a major bump silently invalidating cassettes (README §Open implementation questions §7).
- **`keyring` is admitted closure-wide** — it's a lightweight key-loader Phase 4 uses at `AnthropicLeafAdapter.__init__`. It's not LLM-shaped, so it doesn't need path-scope (any module that wants to load a secret may do so). Phase-0 ADR-0002 is unaffected — `keyring` was never on the deny-list.
- **The scanner uses AST, not regex.** A `# noqa` or string-literal `"import anthropic"` should not trigger; only an actual `Import` / `ImportFrom` node does. Mutation guard: the scanner's `_top_level_packages` is the load-bearing function; a regression that returns `set()` early kills the negative tests immediately.
- **The deliberate-violation fixtures are committed (in `_fixtures_phase4/`) but NOT executed as `.py` files.** The `.py.txt` extension keeps pytest from discovering them as modules. The negative test reads them as text and runs the scanner against them in a `tmp_path`.
- **`tests/fence/__init__.py`** is the package marker (likely already added by S1-01); ensure it exists so `from tests.fence._phase4_scanner import ...` resolves.
- **CI fail-loud expectation (Rule 12).** When a future PR adds `import anthropic` to a probe, the diagnostic names the file, the package, and ADR-0003 — the next reader knows exactly where to go. Verify the diagnostic shape is preserved when refactoring the scanner.
- **The negative tests are the mutation guards** for the production scanner. If a contributor "simplifies" the scanner and breaks closure-wide scanning, four parametrized cases fail immediately. Mirror the Phase-0 pattern at `tests/unit/test_pyproject_fence.py` exactly.
- **Phase-0 invariant preserved (Rule 12 / honest framing).** The narrowed `FORBIDDEN_LLM_SDKS` is **strictly larger** in commitment terms — six SDKs are now denied closure-wide where only five were before. ADR-0003's "the synthesis claim 'original set unchanged' is wrong" is the honest framing; the story file echoes that wording in the attempt log so the next reader sees the dishonesty was caught and corrected.
