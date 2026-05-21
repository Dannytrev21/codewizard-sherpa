# Story S1-05 — Path-scoped pyproject fence amendment

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-04
**ADRs honored:** ADR-0003 (path-scoped fence amendment — admit `anthropic`/`chromadb`/`fastembed`/`onnxruntime` only outside the gather pipeline), Phase-0 ADR-0002 (production fence preserved; `FORBIDDEN_LLM_SDKS` *narrows* honestly)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 13 total — 1 block, 8 hardens, 4 nits

Changes applied:
- AC-1 corrected: `sentence_transformers` → `sentence-transformers` (canonical PyPI *distribution* name) — Consistency F3. The underscore form is the *import* name; `FORBIDDEN_LLM_SDKS` is a distribution-name set, so the underscore spelling left a real fence hole.
- AC-3 strengthened: explicitly requires re-planting a still-forbidden SDK in the extras edge-case test — Test-Quality F4 (after the narrowing, the existing `anthropic`-in-extras test passes vacuously).
- AC-4 strengthened: each new dep must carry the inline `[project.dependencies]` comment the codebase uniformly uses — Design-Patterns/Consistency F2b (Rule 11).
- AC-5 refined: replacement comment no longer over-claims a Phase-6 reservation — nit.
- AC-9 reconciled: rule-specific remediation lives in call-site assert messages; `ImportViolation` is a minimal `(file, package)` value — Test-Quality/Design F10.
- AC-19 added: `_fence._name_of` canonicalizes via `packaging.utils.canonicalize_name` — Consistency F3.
- AC-20 added: the three targeted fence tests consume the shared `walk_imports` kernel (no re-implemented AST walkers) — Design-Patterns F5.
- AC-21 added: negative fixtures exercise the `from X import` branch and prove the AST-not-regex guarantee — Test-Quality F12.
- AC-22 added: the CI `fence` job runs `tests/fence/` so it matches `make fence` and ADR-0003's CI-gate claim — Coverage F8.
- Implementation-outline step 6 reconciled with the TDD-plan scanner signature — Design-Patterns F6 (internal contradiction).
- TDD plan: removed unused `import ast` (would fail `ruff` / AC-16 — F9); targeted-test skeletons rewritten over `walk_imports`; `from X import` + benign-string fixtures added.
- **Block (F1): ADR-0003 §Decision and final-design §2.1 are stale.** Both say "the Phase-0 `FORBIDDEN_LLM_SDKS` set is not edited" — mechanically impossible once `anthropic` becomes a runtime dep (`test_fence_blocks_known_llm_sdks` would fail). The authoritative correction is `phase-arch-design.md §Gap 5`. This story follows Gap 5; see the new reference annotation and Notes-for-implementer entry. The executor must log this and flag the two stale docs for amendment (Rule 7).

Full audit log: `_validation/S1-05-path-scoped-fence-amendment.md`

## Context

Phase 0 established a closure-scoped fence: `FORBIDDEN_LLM_SDKS = frozenset({"anthropic", "langgraph", "openai", "langchain", "transformers"})` enforced by `tests/unit/test_pyproject_fence.py`. Phase 4 needs `anthropic` (the LLM adapter), `chromadb` (vector store), `fastembed` (embeddings runtime), and `onnxruntime` (ONNX session) — but commitment §2.1 ("no LLM anywhere in the gather pipeline") still must hold for `src/codegenie/{probes,coordinator,cache,output,schema}/`. The critic correctly identified this as "the single most load-bearing change in Phase 4 and none of the three designs writes out the exact set membership change" (Gap 5). The honest framing: the original deny-set **narrows** (anthropic moves out) while a path-scoped fence compensates. This story is mechanically delicate — get it wrong and the next 100 PRs run under a silently-broken invariant.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis → Gap 5: FORBIDDEN_LLM_SDKS path-scope mechanics — exactly where the fence amendment lands` — the exact set-membership change and assertion shape.
  - `../phase-arch-design.md §Goals — G5` — "LLM closure fenced; original deny-list invariant preserved."
  - `../phase-arch-design.md §Development view` — `src/codegenie/fallback/` and `src/codegenie/rag/` are the only admitted homes.
  - `../phase-arch-design.md §Testing strategy → CI gates` — `tests/fence/test_pyproject_fence_phase4.py` is a CI gate.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-path-scoped-fence-amendment.md` — the canonical decision; the exact `GATHER_PIPELINE_PATHS`, `PHASE4_ADMITTED_PACKAGES`, `PHASE4_STILL_FORBIDDEN` set declarations live in this ADR; mirror them verbatim. **⚠ STALE DECISION TEXT — do not mirror literally.** ADR-0003 §Decision says "The Phase-0 `FORBIDDEN_LLM_SDKS` set is not edited." That claim is mechanically wrong: once `anthropic` is a `[project.dependencies]` runtime dep, leaving it in `FORBIDDEN_LLM_SDKS` makes `test_fence_blocks_known_llm_sdks` (a live `scan_installed_distribution` check) fail. `phase-arch-design.md §Gap 5` is the authoritative correction — it explicitly says "the synthesis claim 'original set is unchanged' is mechanically incorrect" and prescribes the narrowing this story implements. Honor ADR-0003 for the three path-scope constants; honor §Gap 5 for the `FORBIDDEN_LLM_SDKS` change. Log the ADR-0003/final-design staleness in the attempt log and flag both for amendment (Rule 7).
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — commitment §2.1.
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — probe contract stability.
  - Phase 0 ADR-0002 — production fence (`pyproject.toml` + `import-linter`).
- **Source design:**
  - `../final-design.md §Load-bearing commitments check §2.1` — the exact diff. **⚠ Also carries the stale "The original `FORBIDDEN_LLM_SDKS` set is not edited" claim** — same correction as ADR-0003 above; defer to `phase-arch-design.md §Gap 5`.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `tests/unit/test_pyproject_fence.py` — Phase-0 closure-scoped fence; this story **does not edit** the test logic but **does** update `EXPECTED_FORBIDDEN_SET`.
  - `src/codegenie/_fence.py` — the production-side `FORBIDDEN_LLM_SDKS` constant; narrows in lockstep.
  - `pyproject.toml § [project.dependencies]` — where `anthropic`, `chromadb`, `fastembed`, `onnxruntime`, `keyring` are added (NOT under `[project.optional-dependencies]`).
  - `pyproject.toml § [project.optional-dependencies].agents` — Phase-0 reserved this slot for "Phase 4+ LLM SDKs". The arch + ADR-0003 deliberately depart from this prior plan: the LLM SDK is now `[project.dependencies]` runtime, gated by **path-scope** rather than **extras**. Surface this as a Rule-7 conflict in the attempt log and pick path-scope (the more recent, more strongly-typed choice per ADR-0003); update the `[project.optional-dependencies].agents` comment to reflect the new posture.
  - `pyproject.toml § [tool.importlinter]` — existing import-linter contracts; S1-06 grows this; this story focuses on the pyproject-deps + pytest-fence pair.

## Goal

Land a path-scoped fence: add `anthropic`/`chromadb`/`fastembed`/`onnxruntime`/`keyring` to `[project.dependencies]`; narrow `FORBIDDEN_LLM_SDKS` to remove `anthropic` and add `sentence-transformers`+`torch`; ship `tests/fence/test_pyproject_fence_phase4.py` enforcing path-scope (no gather-pipeline source imports the admitted packages; only `src/codegenie/fallback/leaf/anthropic_adapter.py` imports `anthropic`; only `src/codegenie/rag/` imports `chromadb`/`fastembed`/`onnxruntime`).

## Acceptance criteria

### Set-membership change (the honest amendment)

- [ ] AC-1 — `src/codegenie/_fence.py` `FORBIDDEN_LLM_SDKS` is updated to `frozenset({"langgraph", "openai", "langchain", "transformers", "sentence-transformers", "torch"})` — exactly six members. `anthropic` is removed; `sentence-transformers` + `torch` are added (so the path-scoped fence amendment narrows the LLM set honestly without leaving a hole for the alternative-embeddings backends). (validator: hardened — was `sentence_transformers` with an underscore; Consistency F3. `FORBIDDEN_LLM_SDKS` is consumed by `_fence.py` against PyPI **distribution** names, and the distribution is `sentence-transformers` with a hyphen. The underscore form is the *import* name and belongs only in `PHASE4_STILL_FORBIDDEN` — see AC-7. Robust matching across separator/case variants is AC-19's job.)
- [ ] AC-2 — `tests/unit/test_pyproject_fence.py` `EXPECTED_FORBIDDEN_SET` updated to match AC-1's six members; **all five existing Phase-0 tests still pass against the new set**. The parametrized `test_fence_catches_each_planted_llm_sdk` covers all six SDKs.
- [ ] AC-3 — The Phase-0 test's comment / docstring is updated to note the narrowing (`anthropic` moved to path-scope, `sentence-transformers`+`torch` added) — no behavior change to the closure-scoped *scan logic*. **One test-data change is required (not a scan-logic change, so it is in scope):** `test_fence_ignores_llm_sdk_when_planted_in_optional_extras` currently plants `anthropic` in `[project.optional-dependencies]`. After the narrowing `anthropic ∉ FORBIDDEN_LLM_SDKS`, so that test passes vacuously — its stated mutation guard ("a regression that widens the fence to extras re-includes anthropic and dies") is dead. Re-plant a **still-forbidden** SDK (`torch`) so the metamorphic edge-case test keeps teeth; update its inline comment accordingly. (validator: hardened — Test-Quality F4. The other four Phase-0 tests are unchanged.)

### pyproject deps

- [ ] AC-4 — `pyproject.toml § [project.dependencies]` adds `anthropic`, `chromadb`, `fastembed`, `onnxruntime`, `keyring`, all with strict version constraints (lower-and-upper bound like `anthropic>=0.40.0,<1.0.0`; exact lower/upper to be picked at implementation time and surfaced in the attempt log). **Each new dep carries an inline comment** matching the established `[project.dependencies]` convention — every existing dep there (`networkx`, `alembic`, `orjson`, `zstandard`, …) has one explaining why it is in the closure and its fence relationship (Rule 11). The `anthropic`/`chromadb`/`fastembed`/`onnxruntime` comments must state that each is **admitted closure-wide but path-scoped per ADR-0003** and fenced out of the gather pipeline by `tests/fence/test_pyproject_fence_phase4.py`; the `keyring` comment states it is not LLM-shaped and needs no path-scope. (validator: hardened — Consistency/Design F2b.)
- [ ] AC-5 — `pyproject.toml § [project.optional-dependencies].agents` comment updated. The current 3-line comment ("Phase 4+ slot — LLM SDKs (anthropic, langgraph, ...) land here, NOT in `[project.dependencies]`. This is the load-bearing structural separation the fence (ADR-0002) enforces.") is now stale. Replace it with a comment recording the supersedure honestly, e.g.: `# Phase-0 ADR-0006 reserved this slot for LLM SDKs via extras; superseded by Phase-4 ADR-0003, which admits anthropic/chromadb/fastembed/onnxruntime into [project.dependencies] under a path-scoped fence (tests/fence/test_pyproject_fence_phase4.py). Phase 6's langgraph admission is expected to path-scope likewise — see ADR-0003 §Consequences.` The slot stays declared (empty) as a semantic marker; do not delete it. (validator: refined — nit; original replacement over-claimed a firm Phase-6 reservation.)
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
- [ ] AC-9 — Each assertion failure produces a diagnostic naming **the offending file path(s) AND the offending package(s)** AND the rule-specific remedy (e.g., `"src/codegenie/probes/foo.py imports forbidden package 'anthropic' — PHASE4_ADMITTED_PACKAGES are admitted only under src/codegenie/fallback/leaf/"`). The diagnostic is the mutation guard: a regression that silently widens the scope produces a high-signal failure. **Division of labour:** `ImportViolation` is a minimal `(file, package)` value object — it does NOT carry a `reason` string. The rule-specific remedy text lives in each *call site's* assertion message (the four AC-8 omnibus asserts, plus the AC-12/13/14 targeted asserts), because only the call site knows which of the four rules was violated. (validator: hardened — Test-Quality/Design F10; the original implied a generic `reason` field baked into the scanner, which cannot know the rule context.)
- [ ] AC-10 — **Deliberate-violation fixtures (negative tests).** Five small fixture files committed under `tests/fence/_fixtures_phase4/` (file extension `.py.txt` so they don't run as tests; the fence test loads each as text + AST-walks it):
  - `_fixtures_phase4/violator_probe_imports_anthropic.py.txt` — `import anthropic` (plain `Import` form).
  - `_fixtures_phase4/violator_random_file_imports_torch.py.txt` — **must use the `from torch import ...` form**, so the `ast.ImportFrom` branch of `_top_level_packages` has negative coverage. (validator: hardened — Test-Quality F12; without this, the entire `ImportFrom` branch could be deleted and every fixture still pass.)
  - `_fixtures_phase4/violator_non_leaf_imports_anthropic.py.txt` — anthropic outside `leaf/`.
  - `_fixtures_phase4/violator_non_rag_imports_chromadb.py.txt` — chromadb outside `rag/`.
  - `_fixtures_phase4/benign_string_literal_mentions_anthropic.py.txt` — **NOT a violation**: contains only a comment `# import anthropic` and a string literal `s = "import anthropic"`. The scanner must report **zero** violations for it. (validator: added — Test-Quality F12; this is the metamorphic complement that proves the "AST, not regex" guarantee in Notes-for-implementer is actually tested.)
- [ ] AC-11 — Each fixture has a paired `tests/fence/test_pyproject_fence_phase4_negatives.py` test that synthetically routes the fixture through **the same `walk_imports` scanner the live fence uses** (the canonical signature is `walk_imports(files: Sequence[Path], *, forbidden: Iterable[str]) -> list[ImportViolation]` from `tests/fence/_phase4_scanner.py` — see AC-7/Impl step 6). The four violator fixtures assert exactly one violation is detected with the expected `package`; the `benign_string_literal_mentions_anthropic` fixture asserts **zero** violations. **Critical:** the negative tests use the SAME scanner — mutating it kills both the live fence and these. (Mirror the Phase-0 fence pattern at `tests/unit/test_pyproject_fence.py` where the deliberate-negative tests invoke the same production code path.) (validator: hardened — the original named a non-existent `_walk_imports(paths, gathered_paths) -> set` signature; reconciled to the TDD-plan scanner — Design F6.)

### Targeted fence assertions

- [ ] AC-12 — `tests/fence/test_only_leaf_imports_anthropic.py` — asserts `anthropic` is imported by **exactly one** file: `src/codegenie/fallback/leaf/anthropic_adapter.py`. The test **consumes the shared `walk_imports` scanner** (`from tests.fence._phase4_scanner import walk_imports`) — it does NOT re-implement an AST walk (see AC-20). (Skeleton: until S3-02 lands the adapter, no file imports `anthropic`, so the test passes vacuously — that is expected; the test still names the only-permitted path. Once any import exists, it asserts the exact filename match.)
- [ ] AC-13 — `tests/fence/test_rag_no_anthropic.py` — asserts no module under `src/codegenie/rag/` imports `anthropic` (forward-defensive even though no rag module would have a reason to). **Consumes `walk_imports`** (AC-20). Vacuously green until `src/codegenie/rag/` exists (S4-xx) — expected.
- [ ] AC-14 — `tests/fence/test_no_langgraph_in_phase4.py` — closure-wide assertion that no `src/` source imports `langgraph` — must be zero. (Phase 6 owns the langgraph admission ADR.) **Consumes `walk_imports`** (AC-20). This is a deliberate per-rule echo of the langgraph subset of AC-8(2)'s omnibus closure-wide check — keep both per ADR-0003 §Consequences ("per-fence-rule unit tests" + "the omnibus ... cross-cutting assertion"); do not "dedupe" it away. (validator: hardened — F5/F7: now a thin wrapper over the shared scanner, and the intentional redundancy is documented.)

### Verification + hygiene

- [ ] AC-15 — `make check` green after the dependency addition. `make fence` (the Phase-0 test) green. The new `tests/fence/test_pyproject_fence_phase4.py` and its negative tests green.
- [ ] AC-16 — `mypy --strict`, `ruff check`, `ruff format --check` clean on touched files.
- [ ] AC-17 — `pyproject.toml` lockfile (`uv.lock`) re-locked with the new deps; CI matrix re-runs against the regenerated closure.
- [ ] AC-18 — The TDD plan's red tests exist, are committed, and are green.

### Validator-added criteria

- [ ] AC-19 — `src/codegenie/_fence.py` `_name_of` canonicalizes the parsed distribution name via `packaging.utils.canonicalize_name` (PEP 503), so `sentence-transformers`, `sentence_transformers`, `Sentence.Transformers` and any case/separator variant all resolve to the one canonical name `sentence-transformers` and are caught by `FORBIDDEN_LLM_SDKS`. A test in `tests/unit/test_pyproject_fence.py` plants `sentence_transformers>=0.1` (underscore form) in synthetic `[project.dependencies]` and asserts it is still caught — proving the canonicalization closes the hole. Canonicalization is a no-op for the five single-token members, so no existing behavior changes. (validator: added — Consistency F3; `packaging` is already a runtime dep — `_fence.py` imports `packaging.requirements`.)
- [ ] AC-20 — There is exactly **one** AST-import-walking implementation in `tests/fence/`: `_phase4_scanner.walk_imports`. The omnibus fence (AC-8), the negative tests (AC-11), AND the three targeted tests (AC-12/13/14) all import and call it. No Phase-4 fence test re-implements `ast.walk` / `ast.Import` / `ast.ImportFrom` handling inline. Observable check: a mutation that breaks `walk_imports` fails *every* Phase-4 fence test, not a subset. (validator: added — Design-Patterns F5; the original spec had four hand-rolled AST walkers in one directory, defeating the "same scanner" mutation-guard principle the story itself states in AC-11.)
- [ ] AC-21 — Negative-fixture coverage exercises both import forms and the AST-not-regex guarantee: at least one violator fixture uses `from X import Y` (the `ast.ImportFrom` branch) and the `benign_string_literal_mentions_anthropic` fixture proves a comment/string-literal mention is **not** flagged (see AC-10). (validator: added — Test-Quality F12.)
- [ ] AC-22 — The CI `fence` job (`.github/workflows/ci.yml`) runs `tests/fence/` alongside `tests/unit/test_pyproject_fence.py`, so the dedicated CI gate matches `make fence` (which already runs both — `Makefile §fence`) and the new path-scoped fence is a first-class CI gate per ADR-0003 §Testing strategy. Without this, a path-scope regression fails `make fence` locally and the CI `test` job, but the dedicated CI `fence` gate stays green — a confusing local/CI divergence. (validator: added — Coverage F8.)

## Implementation outline

1. **Add the deps to `pyproject.toml`.** Pick strict-pinned lower+upper bounds for `anthropic`, `chromadb`, `fastembed`, `onnxruntime`, `keyring`. Surface the picked versions in the attempt log.
2. **Re-lock `uv.lock`.** Run `uv lock` (or the project's lock command per `Makefile`) and commit the result.
3. **Narrow `FORBIDDEN_LLM_SDKS`** in `src/codegenie/_fence.py` to the AC-1 six-member set. Update the module docstring to reflect the narrowing (mention ADR-0003 explicitly).
4. **Update `EXPECTED_FORBIDDEN_SET`** in `tests/unit/test_pyproject_fence.py` and update the supporting comment.
5. **Update the `[project.optional-dependencies].agents` comment** in `pyproject.toml` per AC-5.
6. **Land the scanner helper — the single AST-walking kernel (AC-20).** Add `tests/fence/_phase4_scanner.py` (test-package-private) containing the AST-walking function `walk_imports(files: Sequence[Path], *, forbidden: Iterable[str]) -> list[ImportViolation]` and `@dataclass(frozen=True) class ImportViolation` with exactly two fields — `file: str`, `package: str` (no `reason` field — AC-9). The scanner returns an empty list on clean trees. Every Phase-4 fence test (omnibus, negatives, the three targeted) consumes this one function — no test re-implements `ast.walk`.
7. **Land `tests/fence/test_pyproject_fence_phase4.py`** with the four AC-8 assertions consuming the scanner; each assert message carries the rule-specific remedy (AC-9).
8. **Land the fixture files** under `tests/fence/_fixtures_phase4/` (five files — four violators incl. one `from X import` form, plus one benign string-literal fixture — AC-10/AC-21) and the paired `test_pyproject_fence_phase4_negatives.py`.
9. **Land the three targeted fence tests** (`test_only_leaf_imports_anthropic.py`, `test_rag_no_anthropic.py`, `test_no_langgraph_in_phase4.py`) — each a thin consumer of `walk_imports` (AC-20).
10. **Wire the CI `fence` job** (`.github/workflows/ci.yml`) to run `tests/fence/` alongside `tests/unit/test_pyproject_fence.py` (AC-22).
11. Run `make check` locally; verify all fences green.

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

import pathlib
from typing import Final

from tests.fence._phase4_scanner import ImportViolation, walk_imports

# validator note (F9): no `import ast` here — this file delegates all AST work
# to `walk_imports`; an unused `import ast` would fail `ruff` (AC-16).

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
    # Minimal value object (AC-9): file + package only. The rule-specific
    # remedy text lives in each call site's assertion message, because only
    # the call site knows which of the four path-scope rules was violated.
    file: str
    package: str


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
                out.append(ImportViolation(file=str(f), package=pkg))
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


def test_scanner_ignores_string_and_comment_mentions(tmp_path: pathlib.Path) -> None:
    """AC-21 — the AST-not-regex guarantee. A forbidden name appearing only in a
    comment or string literal is NOT a violation. Mutation guard: a regex-based
    regression of the scanner false-positives here and dies."""
    benign = FIXTURES / "benign_string_literal_mentions_anthropic.py.txt"
    target = tmp_path / "benign.py"
    target.write_text(benign.read_text())
    out = walk_imports([target], forbidden={"anthropic"})
    assert out == [], f"Scanner false-positived on a non-import mention: {out}"
```

Fixture contents (`tests/fence/_fixtures_phase4/violator_probe_imports_anthropic.py.txt`):
```python
"""DELIBERATE VIOLATION FIXTURE — paired with test_pyproject_fence_phase4_negatives.py.
Mutation guard: removing `anthropic` from the scanner's forbidden set kills this test.
"""
import anthropic  # type: ignore[import-untyped]
```

The `torch` fixture must use the `from X import` form so the `ast.ImportFrom`
branch of `_top_level_packages` has negative coverage (AC-10/AC-21):
```python
# tests/fence/_fixtures_phase4/violator_random_file_imports_torch.py.txt
"""DELIBERATE VIOLATION FIXTURE — exercises the ImportFrom branch."""
from torch import nn  # type: ignore[import-untyped]
```

The benign fixture proves the scanner is AST-based, not regex-based (AC-21):
```python
# tests/fence/_fixtures_phase4/benign_string_literal_mentions_anthropic.py.txt
"""NOT A VIOLATION — anthropic appears only in a comment and a string literal."""
# import anthropic
s = "import anthropic"
```

(`violator_non_leaf_imports_anthropic.py.txt` and `violator_non_rag_imports_chromadb.py.txt`
are one-line `import anthropic` / `import chromadb` files.)

The targeted skeletons — **all three consume the shared `walk_imports` scanner** (AC-20); none re-implements `ast.walk`:

```python
# tests/fence/test_only_leaf_imports_anthropic.py
import pathlib

import codegenie

from tests.fence._phase4_scanner import walk_imports

_SRC_ROOT = pathlib.Path(codegenie.__file__).parent
_LEAF = _SRC_ROOT / "fallback/leaf/anthropic_adapter.py"


def test_only_leaf_imports_anthropic() -> None:
    offenders = [
        v
        for v in walk_imports(list(_SRC_ROOT.rglob("*.py")), forbidden={"anthropic"})
        if pathlib.Path(v.file).resolve() != _LEAF.resolve()
    ]
    assert not offenders, (
        f"Only {_LEAF} may import `anthropic` (ADR-0003 single-callsite rule); "
        f"offenders: {offenders}"
    )
```

```python
# tests/fence/test_rag_no_anthropic.py
import pathlib

import codegenie

from tests.fence._phase4_scanner import walk_imports

_RAG = pathlib.Path(codegenie.__file__).parent / "rag"


def test_rag_does_not_import_anthropic() -> None:
    # Vacuously green until src/codegenie/rag/ exists (S4-xx) — expected.
    files = list(_RAG.rglob("*.py")) if _RAG.exists() else []
    offenders = walk_imports(files, forbidden={"anthropic"})
    assert not offenders, f"rag/ must not import anthropic: {offenders}"
```

```python
# tests/fence/test_no_langgraph_in_phase4.py
import pathlib

import codegenie

from tests.fence._phase4_scanner import walk_imports

_SRC_ROOT = pathlib.Path(codegenie.__file__).parent


def test_no_langgraph_anywhere() -> None:
    # Deliberate per-rule echo of the langgraph subset of AC-8(2) — keep both
    # per ADR-0003 §Consequences (per-rule unit tests + omnibus assertion).
    offenders = walk_imports(list(_SRC_ROOT.rglob("*.py")), forbidden={"langgraph"})
    assert not offenders, f"langgraph is Phase 6's admission, not Phase 4: {offenders}"
```

State why it fails: `ImportError` — the `tests/fence/_phase4_scanner` module + the fixtures + the updated `FORBIDDEN_LLM_SDKS` don't exist yet.

### Green — make it pass

1. Update `src/codegenie/_fence.py` `FORBIDDEN_LLM_SDKS` to the six-member set (canonical distribution names — `sentence-transformers` with a hyphen); make `_name_of` canonicalize via `packaging.utils.canonicalize_name` (AC-1/AC-19).
2. Update `tests/unit/test_pyproject_fence.py` `EXPECTED_FORBIDDEN_SET` to match; re-plant the extras edge-case test with a still-forbidden SDK (AC-3); add the underscore-spelling metamorphic case (AC-19).
3. Add deps to `pyproject.toml § [project.dependencies]` with inline comments (AC-4); update the `agents` extras comment (AC-5); re-lock `uv.lock`.
4. Land `tests/fence/_phase4_scanner.py`, the fence test file, the five fixtures, the negative tests, and the three targeted tests.
5. Wire the CI `fence` job to include `tests/fence/` (AC-22).

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
| `src/codegenie/_fence.py` | Narrow `FORBIDDEN_LLM_SDKS` to the AC-1 six members (canonical distribution names); make `_name_of` canonicalize via `packaging.utils.canonicalize_name` (AC-19); update module docstring. |
| `tests/unit/test_pyproject_fence.py` | Update `EXPECTED_FORBIDDEN_SET`; re-plant the extras edge-case test with a still-forbidden SDK (AC-3); add the underscore-spelling metamorphic case (AC-19); update comment naming ADR-0003. |
| `.github/workflows/ci.yml` | Extend the CI `fence` job to run `tests/fence/` alongside `tests/unit/test_pyproject_fence.py` (AC-22). |
| `tests/fence/_phase4_scanner.py` | NEW — the single AST-walking scanner consumed by the omnibus fence, the negatives, AND the three targeted tests (AC-20). |
| `tests/fence/test_pyproject_fence_phase4.py` | NEW — four AC-8 path-scope assertions. |
| `tests/fence/test_pyproject_fence_phase4_negatives.py` | NEW — five fixture tests: four planted-violation + one benign string-literal (mutation guard; AC-21). |
| `tests/fence/_fixtures_phase4/violator_probe_imports_anthropic.py.txt` | NEW — fixture; not auto-discovered as a test. |
| `tests/fence/_fixtures_phase4/violator_random_file_imports_torch.py.txt` | NEW — fixture; uses the `from torch import ...` form (ImportFrom branch coverage). |
| `tests/fence/_fixtures_phase4/violator_non_leaf_imports_anthropic.py.txt` | NEW — fixture. |
| `tests/fence/_fixtures_phase4/violator_non_rag_imports_chromadb.py.txt` | NEW — fixture. |
| `tests/fence/_fixtures_phase4/benign_string_literal_mentions_anthropic.py.txt` | NEW — benign fixture; proves the scanner is AST-based not regex (AC-21). |
| `tests/fence/test_only_leaf_imports_anthropic.py` | NEW — single-callsite assertion for `anthropic`; consumes `walk_imports`. |
| `tests/fence/test_rag_no_anthropic.py` | NEW — `rag/` may not import `anthropic`; consumes `walk_imports`. |
| `tests/fence/test_no_langgraph_in_phase4.py` | NEW — closure-wide langgraph rejection; consumes `walk_imports`. |

## Out of scope

- **`import-linter` contracts mirroring the fence** — S1-06 (mirror at lint-time).
- **`tests/fence/test_kernel_frozen.py`** — S1-07 (zero edits to Phase 0/1/2/3 kernel files).
- **Actually adding `import anthropic` somewhere** — S3-02 (the leaf adapter).
- **Actually adding `import chromadb` / `fastembed` / `onnxruntime` somewhere** — S4-03, S4-01.
- **`./node_modules/.bin/tsc` `ALLOWED_BINARIES` amendment** — S6-04.
- **Re-running `make check` to verify post-amendment greenness** — performed locally; CI gates verify on merge.

## Notes for the implementer

- **⚠ ADR-0003 §Decision and final-design §2.1 carry a stale, mechanically-wrong claim (Rule 7 — surface, don't average).** Both say "the Phase-0 `FORBIDDEN_LLM_SDKS` set is not edited." That is impossible: `tests/unit/test_pyproject_fence.py::test_fence_blocks_known_llm_sdks` runs a live `scan_installed_distribution()` = `requires_names_from_distribution() & FORBIDDEN_LLM_SDKS`. The moment `anthropic` is added to `[project.dependencies]` (AC-4), keeping `anthropic` in `FORBIDDEN_LLM_SDKS` makes that intersection non-empty and the Phase-0 fence **fails**. `anthropic` MUST come out of the set. `phase-arch-design.md §Gap 5` is the authoritative correction and explicitly says so ("the synthesis claim 'original set is unchanged' is mechanically incorrect"). **This story follows §Gap 5.** In the attempt log: record the contradiction, note that ADR-0003 §Decision + §Consequences and final-design §2.1 need an amendment to drop the "set is not edited" wording, and do not silently average the two framings.
- **Distribution names vs import names — two different namespaces (Consistency F3).** `FORBIDDEN_LLM_SDKS` (in `_fence.py`) is checked against PyPI **distribution** names — it is consumed by `parse_runtime_dep_names_from_toml` (reads `[project].dependencies`) and `requires_names_from_distribution` (reads `importlib.metadata`). The PyPI distribution is `sentence-transformers` (hyphen). `PHASE4_STILL_FORBIDDEN` (in the Phase-4 fence) is checked against **import** names by AST walking — the import name is `sentence_transformers` (underscore). The two sets legitimately differ on that one member; that is correct, not a typo. `_name_of` must `canonicalize_name` so a contributor writing `sentence_transformers` (underscore) or `Sentence-Transformers` in `[project.dependencies]` is still caught (AC-19). Verified: `packaging.requirements.Requirement` does **not** canonicalize `.name`; `packaging.utils.canonicalize_name` does.
- **Surface the Phase-0 ADR-0006 plan-departure per Rule 7.** Phase 0 ADR-0006 reserved `[project.optional-dependencies].agents` for "Phase 4+ LLM SDKs"; this story departs by putting `anthropic` in `[project.dependencies]` runtime under path-scope. Cross-link Phase-0 ADR-0006 from the attempt log; update the `pyproject.toml` comment so the next reader sees the supersedure.
- **The `FORBIDDEN_LLM_SDKS` narrowing is honest, not a relaxation.** Two new SDKs (`sentence-transformers`, `torch`) join the deny-set so the closure-scoped fence is *stricter*, not weaker. The "honestly narrows" framing is load-bearing — the test diagnostic and the docstring must use that word.
- **Strict version pinning is non-optional for the new deps.** Pick a lower bound that matches the SDK feature set the Phase-4 ADRs assume (Anthropic SDK supporting `response_format=` per ADR-0001; chromadb supporting embedded mode per ADR-0016). Pick an upper bound that's open enough to admit patch releases but closed enough to prevent a major bump silently invalidating cassettes (README §Open implementation questions §7).
- **`keyring` is admitted closure-wide** — it's a lightweight key-loader Phase 4 uses at `AnthropicLeafAdapter.__init__`. It's not LLM-shaped, so it doesn't need path-scope (any module that wants to load a secret may do so). Phase-0 ADR-0002 is unaffected — `keyring` was never on the deny-list.
- **The scanner uses AST, not regex.** A `# noqa` or string-literal `"import anthropic"` should not trigger; only an actual `Import` / `ImportFrom` node does. Mutation guard: the scanner's `_top_level_packages` is the load-bearing function; a regression that returns `set()` early kills the negative tests immediately.
- **The deliberate-violation fixtures are committed (in `_fixtures_phase4/`) but NOT executed as `.py` files.** The `.py.txt` extension keeps pytest from discovering them as modules. The negative test reads them as text and runs the scanner against them in a `tmp_path`.
- **`tests/fence/__init__.py`** is the package marker (likely already added by S1-01); ensure it exists so `from tests.fence._phase4_scanner import ...` resolves.
- **CI fail-loud expectation (Rule 12).** When a future PR adds `import anthropic` to a probe, the diagnostic names the file, the package, and ADR-0003 — the next reader knows exactly where to go. Verify the diagnostic shape is preserved when refactoring the scanner.
- **The negative tests are the mutation guards** for the production scanner. If a contributor "simplifies" the scanner and breaks closure-wide scanning, four parametrized cases fail immediately. Mirror the Phase-0 pattern at `tests/unit/test_pyproject_fence.py` exactly.
- **Phase-0 invariant preserved (Rule 12 / honest framing).** The narrowed `FORBIDDEN_LLM_SDKS` is **strictly larger** in commitment terms — six SDKs are now denied closure-wide where only five were before. `phase-arch-design.md §Gap 5`'s "the synthesis claim 'original set is unchanged' is mechanically incorrect" is the honest framing (note: this correction lives in §Gap 5, NOT in ADR-0003 §Decision — see the block-finding note at the top of these Notes); the attempt log echoes that wording so the next reader sees the contradiction was caught and corrected.
