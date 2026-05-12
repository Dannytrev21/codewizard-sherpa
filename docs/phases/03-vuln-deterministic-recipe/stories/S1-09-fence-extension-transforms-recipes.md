# Story S1-09 — Phase-0 `fence` CI extension to `transforms/` + `recipes/`

**Step:** Step 1 — Plant the two ABCs, the four Phase 0/1/2 additive edits, and the foundations every Phase 3 component consumes
**Status:** Ready
**Effort:** S
**Depends on:** S1-02 (the `src/codegenie/transforms/` package must exist for the fence to scan it), S1-03 (the `src/codegenie/recipes/` package must exist for the fence to scan it)
**ADRs honored:** ADR-0002 (two new top-level packages — the fence extension is the load-bearing CI guarantee that the package-layout decision actually keeps LLMs out of `transforms/` and `recipes/`), ADR-0013 (Phase-3 confidence is strict-AND of binary signals; no LLM in this loop — the fence is the mechanical enforcement of this), Phase 0's no-LLM-in-gather fence precedent (the same pattern, extended)

## Context

Phase 3 commits — across `final-design.md §Goals`, ADR-0013, and the `stories/README.md` cross-cutting "No-LLM fence extension" — that the deterministic recipe path contains **no LLM call**. Tokens per run = 0. The mechanical enforcement is the Phase-0 `fence` CI job: an AST/import-closure scan that fails CI red if any module under a fenced package imports a known LLM SDK. Phase 0 fenced the gather packages; Phase 3 extends the fence to its two new top-level packages — `src/codegenie/transforms/` and `src/codegenie/recipes/`.

The forbidden import set is the same one Phase 0 pinned: `anthropic`, `langgraph`, `chromadb`, `qdrant`, `qdrant-client`, `sentence-transformers`, `voyageai`, `openai`. Phase 4 (LLM-fallback planning) is allowed to import these — but only from `src/codegenie/planning/` or wherever Phase 4 lands; never from `transforms/` or `recipes/`. This story plants the fence in the Phase-3 packages. S7-07 finalizes the CI wiring as merge-blocking; this story makes the fence enforceable and green on the seed code S1-02/S1-03 just landed.

The fence is **not the only no-LLM signal** — `requirements.txt` / `pyproject.toml` do not declare the LLM SDKs as runtime dependencies in Phase 3, and `mypy --strict` would fail if they were referenced. But the fence is the *durable* signal: a future engineer who casually adds `anthropic` to `pyproject.toml` (perhaps for a Phase 4 prototype) does not silently expose Phase 3 code to LLM imports. The fence catches the regression at PR time.

A sibling adversarial test pins the no-direct-subprocess discipline: under `src/codegenie/transforms/` + `src/codegenie/recipes/`, **no module may call `subprocess.run` / `subprocess.Popen` directly** — every subprocess call must route through `src/codegenie/exec.py` (the chokepoint that owns the sandbox) or `src/codegenie/tools/*` wrappers (which in turn route through `exec.py`). This is the Phase 2 chokepoint-preservation discipline carried forward; without the AST scan, a future implementer could bypass the sandbox by importing `subprocess` from a recipe engine module. The scan lives in this story because it is the second mechanical no-LLM-spirit invariant the fence-class CI gates own.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Harness engineering" §"CI gates"` — `fence` listed as one of the new CI jobs; `transforms/` + `recipes/` named.
  - `../phase-arch-design.md §"Goals"` — `tokens_per_run_p99 == 0` exit criterion (the contract this story enforces mechanically).
  - `../phase-arch-design.md §"Cross-cutting concerns" §"No-LLM fence extension"` — the load-bearing rationale.
- **Phase ADRs:**
  - `../ADRs/0002-two-new-top-level-packages-transforms-recipes.md` — the package boundary the fence enforces.
  - `../ADRs/0013-confidence-strict-and-of-binary-signals-no-llm.md` — the no-LLM-in-this-loop invariant the fence makes mechanical.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — Phase 0's fence precedent; this story extends the same pattern.
- **Source design:**
  - `../final-design.md §"Goals" §"Trust & safety goals"` #15 — "no LLM in this loop" exit criterion.
  - `../final-design.md §"Synthesis ledger"` row "Fence extension" — Phase 3 fence extends to the two new packages.
- **Existing code:**
  - `scripts/fence_imports.py` (or equivalent — Phase 0's fence script; verify exact path on disk before editing) — the AST/import-closure scanner this story extends.
  - `tests/adv/test_fence_no_llm_imports.py` (Phase 0's) — the adversarial test pattern this story mirrors.
  - `src/codegenie/transforms/` (S1-02 — package seed) — the package the fence extends to scan.
  - `src/codegenie/recipes/` (S1-03 — package seed) — the package the fence extends to scan.
- **Style reference:**
  - Phase 0's fence story (under `docs/phases/00-bullet-tracer-foundations/stories/`) — the original pattern this story extends.

## Goal

Extend the Phase-0 `fence_imports.py` scanner so its scan set includes `src/codegenie/transforms/` and `src/codegenie/recipes/`; ship two adversarial tests pinning (a) the LLM-SDK-import-forbidden invariant under both new packages, and (b) the no-direct-`subprocess.run`/`Popen` invariant under both new packages (every subprocess call routes through `exec.py` or `tools/*`).

## Acceptance criteria

- [ ] `scripts/fence_imports.py` (or whatever Phase 0 named the scanner) is extended so its package scan list includes `src/codegenie/transforms/` and `src/codegenie/recipes/`. The forbidden-import set is unchanged from Phase 0: `anthropic`, `langgraph`, `chromadb`, `qdrant`, `qdrant-client`, `sentence-transformers`, `voyageai`, `openai`.
- [ ] Running the scanner against `main` after S1-02 + S1-03 land produces zero violations (the new packages are green from day one).
- [ ] `tests/adv/test_phase3_fence_no_llm_imports.py` exists. It (a) synthesizes a minimal module under `src/codegenie/transforms/` or a tmp-mirror of the scan tree containing `import anthropic`, (b) invokes the scanner as a subprocess, and (c) asserts non-zero exit and that the violation message names `anthropic` and the offending module path.
- [ ] `tests/adv/test_phase3_fence_no_llm_imports.py` also has a "negative" test that runs the scanner against the real (clean) tree and asserts exit 0 + zero violations — pins the "green on main" invariant.
- [ ] `tests/adv/test_phase3_no_subprocess_direct.py` exists. It AST-scans every `.py` file under `src/codegenie/transforms/` and `src/codegenie/recipes/` (excluding `__pycache__`) and asserts that **none** import `subprocess` and **none** reference `subprocess.run` or `subprocess.Popen`. Test fails red if any direct `subprocess` usage is found. The allowed chokepoints (`src/codegenie/exec.py` and `src/codegenie/tools/*`) are explicitly out of the scan tree.
- [ ] The same `tests/adv/test_phase3_no_subprocess_direct.py` synthesizes a fake file containing `subprocess.run(["echo"])` (written to a tmp tree mirroring `src/codegenie/transforms/`) and asserts the scan flags it — pins the test's mechanics, not just the current-tree state.
- [ ] Both adversarial tests are registered under `pytest.mark.fence` (or whatever Phase 0's marker is); S7-07 wires the merge-blocking CI gate.
- [ ] The fence scanner's CLI output on violation is grep-able and stable: one line per violation, formatted `<file>:<line>: forbidden import '<sdk>'`. The format is asserted by the synthesized-violation test so a future scanner-refactor cannot silently drop the file/line context.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict scripts/fence_imports.py tests/adv/` pass.
- [ ] A one-line entry is added to `phase-arch-design.md`'s CI-gates table (or wherever the gate list lives) noting that `fence` now covers `transforms/` + `recipes/`. (If the table already names the gates, this is a no-op.)

## Implementation outline

1. **Read `scripts/fence_imports.py` end-to-end** — Rule 8. Identify the package list (it is likely a constant near the top, e.g., `FENCED_PACKAGES = ["src/codegenie/probes", ...]`). Identify how the scan is invoked (likely an AST visitor or `ast.parse` walk that flags `ImportFrom` / `Import` nodes whose names are in the forbidden set).
2. **Extend the package list** with two entries: `"src/codegenie/transforms"` and `"src/codegenie/recipes"`. Preserve the existing entries; this is additive.
3. **Run the scanner manually** against `main` after S1-02 + S1-03. Confirm zero violations. (The seed packages contain only the ABC + Pydantic + registry boilerplate — no LLM imports possible.)
4. **Write `tests/adv/test_phase3_fence_no_llm_imports.py`** — three tests:
   - **Synthesized violation** — write a tmp `.py` file containing `import anthropic` into a tmp dir mirroring `src/codegenie/transforms/`, point the scanner at the tmp tree, assert non-zero exit + message.
   - **Clean tree** — invoke the scanner against the real tree, assert exit 0.
   - **Format stability** — the synthesized-violation test asserts the output line matches `r":\d+: forbidden import 'anthropic'"`.
5. **Write `tests/adv/test_phase3_no_subprocess_direct.py`** — two tests:
   - **AST scan over real tree** — walk every `.py` file under the two packages, parse each, walk the AST for `Import` / `ImportFrom` of `subprocess` and `Attribute` access patterns like `subprocess.run`. Assert empty findings on the real tree.
   - **Synthesized violation** — write a tmp `.py` file containing `import subprocess; subprocess.run([...])` under a tmp `transforms/` tree, run the scanner against that tree, assert non-empty findings.
6. **Register the pytest marker** (if not already present in `pyproject.toml`'s `[tool.pytest.ini_options]` `markers` list).
7. **Wire the CI job** — Phase 0's `fence` workflow already exists; verify it picks up the new package entries automatically (most scanner implementations enumerate the constant). If the workflow file hardcodes per-package invocations, extend it. (If the workflow extension is non-trivial, defer to S7-07; this story owns the scanner + tests.)

## TDD plan — red / green / refactor

### Red — write the failing tests first

Path: `tests/adv/test_phase3_fence_no_llm_imports.py`

```python
"""ADR-0002 + ADR-0013 | Invariant: src/codegenie/transforms/ and src/codegenie/recipes/ may not import LLM SDKs.

Forbidden set: anthropic, langgraph, chromadb, qdrant, qdrant-client, sentence-transformers, voyageai, openai.
Mechanical enforcement via scripts/fence_imports.py. CI gate (S7-07) blocks merge on any violation.
"""
import pytest
from pathlib import Path

@pytest.mark.fence
def test_fence_scanner_flags_synthesized_anthropic_import(tmp_path: Path) -> None:
    # Write tmp tree mirroring src/codegenie/transforms/; drop in a file with `import anthropic`.
    # Invoke scripts/fence_imports.py against the tmp tree; assert non-zero exit + message contains 'anthropic'.
    ...

@pytest.mark.fence
def test_fence_scanner_green_on_real_tree() -> None:
    # Invoke the scanner against the real src/codegenie/transforms/ + recipes/; assert exit 0.
    ...

@pytest.mark.fence
def test_fence_violation_message_is_grep_stable(tmp_path: Path) -> None:
    # Pin the violation-message format: '<file>:<line>: forbidden import <sdk>'.
    ...
```

Path: `tests/adv/test_phase3_no_subprocess_direct.py`

```python
"""ADR-0002 + Phase 2 chokepoint-preservation | Invariant: no module under transforms/ or recipes/ may
call subprocess.run / subprocess.Popen directly; every subprocess call routes through exec.py or tools/*.

The chokepoint is what owns the sandbox; bypassing it is a load-bearing regression.
"""
import ast
import pytest
from pathlib import Path

@pytest.mark.fence
def test_no_subprocess_imports_under_transforms() -> None:
    # Walk src/codegenie/transforms/**/*.py; parse each; assert no `import subprocess` / `from subprocess import ...`.
    ...

@pytest.mark.fence
def test_no_subprocess_imports_under_recipes() -> None:
    ...

@pytest.mark.fence
def test_synthesized_subprocess_violation_caught(tmp_path: Path) -> None:
    # Write a fake module containing subprocess.run([...]); assert the AST scanner flags it.
    ...
```

Run both; commit red. (The clean-tree tests pass immediately because the seed packages from S1-02/S1-03 have no violations. The synthesized-violation tests fail until the scanner extension is in.)

### Green — make it pass

- Extend `FENCED_PACKAGES` (or the equivalent) in `scripts/fence_imports.py` with the two new entries.
- Implement the synthesized-violation test scaffolding: a `tmp_path`-rooted tree, a single file with `import anthropic`, an invocation via `subprocess.run([sys.executable, "scripts/fence_imports.py", "--root", str(tmp_path)])` or similar.
- Implement the AST scanner in `test_phase3_no_subprocess_direct.py` inline (no new production code — the test owns the discipline). Use `ast.parse` + `ast.walk` to find `Import` and `ImportFrom` nodes for `subprocess`, plus `Attribute` chains rooted at `subprocess`. Keep the implementation small enough to fit in the test file (≤ 30 lines).
- Confirm both real-tree negative tests pass against the actual `transforms/` and `recipes/` packages.

### Refactor — clean up

- **One responsibility per test file.** `test_phase3_fence_no_llm_imports.py` owns the LLM-SDK gate; `test_phase3_no_subprocess_direct.py` owns the chokepoint-preservation gate. Resist the urge to combine.
- **The AST scanner in `test_phase3_no_subprocess_direct.py`** is test-only — do not promote it to `scripts/` until a second consumer arises (Rule 2 — no speculative abstractions).
- **Confirm the synthesized-violation tests do not pollute the real tree.** Use `tmp_path` exclusively; never write into `src/codegenie/`.
- **Run the fence scanner manually** one more time against `main`; confirm zero violations and capture the output in the PR body as evidence the gate is green.

## Files to touch

| Path | Why |
|---|---|
| `scripts/fence_imports.py` | Extend `FENCED_PACKAGES` (or equivalent) with `src/codegenie/transforms` + `src/codegenie/recipes`. |
| `tests/adv/test_phase3_fence_no_llm_imports.py` | New — synthesized violation + clean tree + message-format stability. |
| `tests/adv/test_phase3_no_subprocess_direct.py` | New — AST scan for direct `subprocess` usage under the two new packages. |
| `pyproject.toml` (extend if needed) | Register `pytest.mark.fence` if not already in the markers list. |
| `phase-arch-design.md` (one-line note, optional) | Confirm the CI-gates table mentions `fence` covers `transforms/` + `recipes/`. |

## Out of scope

- **CI workflow wiring** — S7-07 finalizes `fence` as merge-blocking. This story makes the scanner and tests work; the CI YAML change is in S7-07 unless Phase 0's workflow already enumerates packages from the scanner's constant.
- **Adding a new forbidden import** — the set is closed at the Phase 0 list. Phase 4 may need to add `langgraph` to its own fence (in the opposite sense — restrict it *out* of `transforms/` but *into* `planning/`); that is a Phase 4 ADR.
- **Fencing other Phase-3 packages** — `transforms/cve/` and `transforms/validation/` are sub-packages of `transforms/` and are scanned automatically by the recursive walk. No separate entries needed.
- **Replacing Phase 0's scanner with a more sophisticated tool** (e.g., `import-linter`, `deptry`) — Rule 3 (surgical changes). The existing scanner is adequate; replacement is a Phase 4+ refactor with its own ADR.
- **A `tests/adv/` fixture for Phase 4's planner package** — Phase 4 owns its own fence story.
- **AST scan for other forbidden patterns** (e.g., `eval`, `exec`, `pickle.loads`) — narrower invariants belong in their own stories. This story owns only the LLM-SDK and direct-`subprocess` invariants.

## Notes for the implementer

- **The scanner is the durable signal, not the import surface.** A future engineer who removes `anthropic` from `pyproject.toml` and adds it back later does not break the fence — the fence is keyed on the *import statement* in source, not the dependency manifest. This is intentional: the dependency manifest is necessary but not sufficient. Code can import a package that is not declared (CI breaks, but later); the fence catches the regression at AST-scan time before the test runner ever loads the module.
- **Synthesized-violation tests are load-bearing.** Without them, a future refactor that silently breaks the scanner (e.g., a typo in the forbidden-set constant) goes undetected because the clean-tree test would still pass. Pin the *mechanics* of the gate, not just the current state.
- **Do not import `subprocess` from the test file itself.** Use `pathlib` for tree manipulation and `subprocess.run` only at the top of the test (the test file is not under `transforms/` or `recipes/`; the discipline applies to production code, not test code). If the test file itself triggers the scanner, exclude `tests/` from the scan root.
- **The AST scanner in `test_phase3_no_subprocess_direct.py` should accept import-aliases.** A naive scan misses `from subprocess import run as r; r([...])`. Walk the AST for both `Import` (name `subprocess`) and `ImportFrom` (module `subprocess`) — both forms are forbidden. The synthesized-violation test should include the `from subprocess import run` form to pin this.
- **Phase 4's allowed-LLM-imports boundary is `src/codegenie/planning/`** — when Phase 4 lands, its package is *not* in `FENCED_PACKAGES`. Phase 4's own ADR captures the boundary. This story does not pre-judge Phase 4's package name.
- **Performance.** The scanner walks the AST of every `.py` file under the two packages — at Phase 3's seed size this is ≤ 30 files and runs in well under a second. As the packages grow, the scan stays linear; no perf concern.
- **Failure mode if the scanner is broken.** Phase 0's CI gate prevents merging a broken scanner; this story's clean-tree test additionally pins "the scanner is functional and exit-0 on a clean tree." A scanner that silently always-passes (the worst failure mode) is caught by the synthesized-violation test.
- **Regression risk: very low.** This is the most mechanical Step 1 edit besides S1-05. The main risk is the scanner's package-list constant living in a non-obvious file (e.g., a YAML config rather than the script source); read Phase 0's `fence`-gate story first to be sure.
