# Story S1-05 — Phase 3 import-linter contracts + AST fences

**Step:** Step 1 — Scaffold packages, domain primitives, sum types, and structural CI fences
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-02 (`src/codegenie/plugins/` package exists), S1-03 (`src/codegenie/transforms/outcomes.py` exists), S1-04 (`src/codegenie/transforms/{transform,apply_context}.py` exist)
**ADRs honored:** ADR-0010 (Consequences — `dict[str, Any]` banned under `src/codegenie/{plugins,transforms}/`; fence test enforces); ADR-0001 — **partial**: this story prevents LLM/`Any` pollution of `transforms/__init__.py`; the explicit re-export snapshot fence is deferred to S6-06; ADR-0011 (audit + lint posture — these fences are CI gates, not runtime guarantees; a PR editing both the fence and the violation defeats it, mitigated by CODEOWNERS on `tests/fence/` and `_phase2_baseline.txt`).

## Validation notes (added 2026-05-18 by phase-story-validator)

Synthesizer applied edits from four critics. The full audit log lives at `_validation/S1-05-phase3-fence-tests.md`. Headline changes:
- **AC tightening (block-severity):** added empty-surface floor guard, per-fence planted-violation evidence (3-of-3, not 1), `make fence` Makefile wiring, structural AST visitor with parametrized mutation cases, regex-grammar inline allowlist marker, `as_packages = true` config-shape assertion, restructured Red step to be red-by-construction every CI run.
- **Coverage hardenings:** known-bypass fixture for type-comments / forward-refs / aliased imports; baseline-SHA shape + ancestor checks; metamorphic complement for the LLM fence; ADR-0011 framing docstrings on every fence file.
- **Consistency fixes:** explicit out-of-scope note for top-level `plugins/` directory coverage (deferred to S7-xx when first plugin Python lands); follow-up amendments to ADR-0010 line 71 and `High-level-impl.md` §Step 1 line 30 so future readers don't trip on stale filenames / config paths; CI `fetch-depth: 0` note for the git-diff fence.
- **Design-pattern shifts:** the AST walker moves to `src/codegenie/_phase3_fence.py` (parity with Phase 0's `_fence.py` mutation-resistance pattern — same function called by live and planted tests). `Violation` becomes a `@dataclass(frozen=True)` (newtype-style, kills primitive obsession). Baseline file structure left flat today but the test reads it via a `_BASELINES` tuple so adding `_phase3_baseline.txt` at Phase-4 time is a one-row append, not a rewrite. Explicit anti-pattern note: **do NOT extract a `FenceRule` ABC** — the 5+ planned fences share category but not input/output shape (Rule 2).

**Verdict:** HARDENED.

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

**Configuration / wiring (AC-1 through AC-3)**
- [ ] **AC-1** `pyproject.toml [tool.importlinter]` extended with two new `forbidden` contracts: one forbidding `FORBIDDEN_LLM_SDKS` (anthropic, langgraph, openai, langchain, transformers) imports under `codegenie.plugins`; one forbidding the same under `codegenie.transforms`. **Both use `as_packages = true`** so submodules are covered. Verified by a unit test `tests/fence/test_phase3_importlinter_contracts_shape.py` that parses `pyproject.toml` and asserts (a) each Phase 3 contract names exactly the five `FORBIDDEN_LLM_SDKS` (no drift), (b) `as_packages is True` on both, (c) `source_modules` is `["codegenie.plugins"]` / `["codegenie.transforms"]` respectively.
- [ ] **AC-2** `make lint-imports` exits 0 with the new contracts. **Coverage-of-the-contract** is independently proved (not just zero violations on an empty surface): a planted-import subprocess test writes `src/codegenie/plugins/_test_planted_leak.py` containing `import anthropic`, runs `lint-imports` as a subprocess, asserts non-zero exit AND that the failure message names the planted module, then removes the file (`tests/fence/test_lint_imports_catches_planted_leak.py`).
- [ ] **AC-3** `Makefile` `fence:` target amended to `pytest -q tests/unit/test_pyproject_fence.py tests/fence/` (per `phase-arch-design.md §Testing strategy §CI gates` line 1042 — `make fence` must run all four fence files). `make fence` exits 0 after this story lands. A meta-test (or shell-snippet assertion in `tests/fence/test_fence_target_wiring.py`) parses the `Makefile`'s `fence:` recipe and asserts each of the four fence test paths is present.

**Runtime-closure fence (AC-4)**
- [ ] **AC-4** `tests/fence/test_no_llm_in_transforms.py` — runtime-closure scan: `pkgutil.walk_packages(codegenie.plugins.__path__); pkgutil.walk_packages(codegenie.transforms.__path__)` followed by `sys.modules`-intersect-with-`FORBIDDEN_LLM_SDKS`. Reuses `codegenie._fence.FORBIDDEN_LLM_SDKS`. **Mutation guards (all parametrized, mirroring Phase 0 precedent):**
  - **AC-4.a** **Live check**: intersection is empty.
  - **AC-4.b** **Per-SDK planted-positive** (`@pytest.mark.parametrize`): for each of the five SDKs, inject a synthetic `sys.modules[<sdk>]` entry imported by a temp submodule `src/codegenie/plugins/_test_planted/<sdk>_leak.py` (created in `tmp_path` and `sys.path`-prepended for the test), assert the same scanner the live check uses catches it, remove. Five cases = five independent mutation guards.
  - **AC-4.c** **Metamorphic complement** (`test_fence_ignores_llm_sdk_present_outside_phase3_closure`): pre-populate `sys.modules["anthropic"]` (or any SDK) directly — NOT via `codegenie.plugins.*` — and assert the fence does NOT fire. Proves the scanner is scoped to the Phase 3 closure, not the test runner's `sys.modules`. Mirrors Phase 0 `test_fence_ignores_llm_sdk_when_planted_in_optional_extras`.
  - **AC-4.d** **Import-success guard**: assert `"codegenie.plugins" in sys.modules` and `"codegenie.transforms" in sys.modules` AFTER the walk — silently-caught `ImportError` must not green the test.
  - **AC-4.e** **Module-level docstring** names ADR-0011 framing (audit + lint, NOT runtime); meta-test scans for the required strings.

**Annotation fence (AC-5)**
- [ ] **AC-5** `tests/fence/test_no_any_in_plugin_surface.py` — structural AST-walk via `ast.NodeVisitor` (NOT shotgun `ast.walk`) restricted to annotation contexts: `ast.AnnAssign.annotation`, `ast.arg.annotation`, `ast.FunctionDef.returns`, `ast.AsyncFunctionDef.returns`, `ast.ClassDef`-body-level `AnnAssign`. Flags any subtree of those annotations containing `ast.Name(id="Any")` or `ast.Attribute(attr="Any")`. Roots: `src/codegenie/plugins/` and `src/codegenie/transforms/`. **The walker is extracted to `src/codegenie/_phase3_fence.py`** (parity with `src/codegenie/_fence.py` precedent — same function called by live + planted tests is the mutation-resistance property). Sub-guards:
  - **AC-5.a** **Floor guard**: each `PHASE3_ROOTS` directory exists AND contains ≥ 1 non-`__init__.py` Python module. A parametrized-by-root assertion fails loudly if a root is missing or empty, so a future deletion of `plugins/` or `transforms/` is not a silent green. Assertion message names the missing-or-empty root.
  - **AC-5.b** **Per-shape planted-violation matrix** (`@pytest.mark.parametrize` over the production walker) covering at minimum:
    | snippet | expected_hit |
    |---|---|
    | `x: Any = 1` | True |
    | `def f(x: Any) -> None: ...` | True |
    | `def f() -> Any: ...` | True |
    | `x: dict[str, Any] = {}` | True |
    | `x: Dict[str, Any] = {}` | True |
    | `x: list[Any] = []` | True |
    | `x: tuple[Any, ...] = ()` | True |
    | `x: typing.Any = 1` | True |
    | `x: Callable[..., Any] = None` | True |
    | `x: dict[str, list[Any]] = {}` | True |
    | `x: int = 1` | False |
    | `isinstance(obj, Any)` (runtime, not annotation) | False |
    | `if TYPE_CHECKING:\n    from typing import Any` (import, not annotation) | False |
    | `x: "Any" = 1` (string forward-ref) | True (must catch) |
    Each row is one mutation guard.
  - **AC-5.c** **Inline allowlist marker grammar**: the marker MUST match `re.compile(r"#\s*fence:\s*any-allowed\s*\[(?P<adr>P3-ADR-\d{4})\]\s*$")`. Bare `# fence: any-allowed`, empty `[]`, or malformed bracket is treated as a violation (with a distinct error message naming the regex). Parametrized test covers: valid `[P3-ADR-0010]` → skipped; bare → violation; `[garbage]` → violation; `[]` → violation; whitespace-tolerant valid → skipped.
  - **AC-5.d** **Zero markers at Step-1 landing**: a meta-test asserts `grep -r "# fence: any-allowed" src/codegenie/{plugins,transforms}/` returns zero matches at S1-05 GREEN time. New markers require an ADR amendment.
  - **AC-5.e** **Known-bypass fixture catalog**: `tests/fence/_fixtures/_known_bypasses.py` (NOT under `src/`) contains shapes the AST walker is known to miss: type-comment annotations (`# type: dict[str, Any]`), `from typing import Any as _Any` aliased, `from typing_extensions import Any`. Each shape is exercised by a test that asserts EITHER the scanner catches it OR it appears in a `KNOWN_BYPASSES: Final[frozenset[str]]` constant in `_phase3_fence.py` with a tracking-issue link in the comment. No floating prose — every bypass is either fenced or registered.
  - **AC-5.f** **Lineno + snippet accuracy**: `test_walker_returns_accurate_lineno_and_snippet` asserts a planted `y: Any = 2` on line 2 returns `Violation(line=2, kind="any-name", snippet="Any")`.

**Kernel-frozen fence (AC-6)**
- [ ] **AC-6** `tests/fence/test_kernel_frozen.py` — git-diff-based fence: against the Phase 2 baseline SHA read from `tests/fence/_phase2_baseline.txt`, assert no file outside the ADR-allowlist has been modified by Phase 3 work. Scope: paths matching `src/codegenie/{,probes/,coordinator/,output/,cache/,grammars/,exec/,indices/,conventions/,types/}/**`. The test reads baselines via `_BASELINES: Final[tuple[tuple[str, Path], ...]] = (("phase-2", Path("tests/fence/_phase2_baseline.txt")),)` so Phase 4 / 5 / … baselines can be appended via ADR amendment without rewriting the walker (Open/Closed at the file boundary).
  - **AC-6.a** **Allowlist** (`Final[frozenset[Path]]` in the test file, each entry tagged via a comment `# adr: <id>`):
    - `pyproject.toml` (this story — import-linter contract extension)
    - `src/codegenie/exec/__init__.py` (S4-05, P3-ADR-0012 — `ALLOWED_BINARIES` amendment; allowed-IF-touched, not required-to-be-touched)
    - `src/codegenie/types/identifiers.py` (S1-01, P3-ADR-0010 — newtype additions)
    - `src/codegenie/types/__init__.py` (S1-01 — re-exports)
  - **AC-6.b** **Baseline integrity**: `test_baseline_is_a_real_commit_sha` asserts `re.fullmatch(r"[0-9a-f]{40}", baseline)`; `test_baseline_resolves_to_ancestor_of_head` asserts `git merge-base --is-ancestor <baseline> HEAD` exits 0 AND `baseline != HEAD_SHA` (an accidental `HEAD` paste is rejected).
  - **AC-6.c** **Helpful-error guard**: a synthetic-diff test (injects a fake non-allowlisted Phase 1 path into the diff via dependency-injection on the diff-source) asserts the failure message contains the literal strings `"_phase2_baseline.txt"` AND `"ADR amendment"` so a future engineer hits a stop sign, not a riddle.
  - **AC-6.d** **Renames + deletions are flagged**: the test uses `git diff --name-status -M` (rename detection) and treats `R` / `D` lines as in-scope changes — a delete-then-recreate that defeats the diff is not silent.
  - **AC-6.e** Module docstring names ADR-0011 framing (CODEOWNERS on `_phase2_baseline.txt` is the social anchor; documented limitation: a PR that edits both the baseline file and the violation defeats the fence).
  - **AC-6.f** Module docstring + Notes-for-implementer surface the **CI `fetch-depth: 0`** requirement (or `git fetch --unshallow` before `make fence`) so shallow clones don't silently break the diff.

**Planted-violation evidence (AC-7) — Rule 12 fail-loud**
- [ ] **AC-7** Each of the three fences proves it actually catches violations via two complementary mechanisms:
  - **AC-7.a** Parametrized planted-positive tests **inside the test suite itself** (AC-4.b, AC-5.b, AC-6.c) — red-by-construction every CI run. These are the load-bearing mutation guards.
  - **AC-7.b** A one-time **out-of-test planted violation** is committed on a throwaway branch / commit per fence (3 of 3): for each fence, plant a real violation in real code, `pytest` shows the test red, remove the violation, `pytest` shows green. The green-after-removal evidence (commit SHAs before/red/after-removal) is recorded in `_attempts/S1-05.md` as three independent 3-line blocks. Missing evidence for any of the three fences fails the executor's validation gate.

**Scaffolding (AC-8 through AC-11)**
- [ ] **AC-8** `tests/fence/__init__.py` exists (test package marker).
- [ ] **AC-9** `pytest tests/fence/ -v` exits 0 with all collected items running (no `skip` / `xfail` markers present — assert via `pytest --collect-only -q tests/fence/ | grep -E "skipped|xfailed"` returns empty).
- [ ] **AC-10** `make check` runs the new fence tests (covered transitively via `make test` because `pyproject.toml [tool.pytest.ini_options] testpaths = ["tests"]` already collects `tests/fence/`; AC-3 additionally wires `make fence` directly).
- [ ] **AC-11** `ruff check`, `ruff format --check`, `mypy --strict` on touched files clean. TDD plan's red test exists in git history (commit SHA recorded in `_attempts/S1-05.md`), green at story landing.

**Follow-up amendments (AC-12)**
- [ ] **AC-12** Two doc amendments land alongside this story (logged in `_attempts/S1-05.md`):
  - `docs/phases/03-vuln-deterministic-recipe/ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` §Consequences renames `tests/fence/test_no_any_in_contract_layer.py` → `tests/fence/test_no_any_in_plugin_surface.py` (single line edit).
  - `docs/phases/03-vuln-deterministic-recipe/High-level-impl.md` §Step 1 line 30 changes `tools/lint/importlinter.cfg amended` → `pyproject.toml [tool.importlinter] amended` so future readers don't replay the Rule-7 conflict this story already resolved.

## Implementation outline

1. **Production walker** — create `src/codegenie/_phase3_fence.py` (private, leading-underscore, mirrors `_fence.py` precedent):
   - `@dataclass(frozen=True) class Violation: file: Path; line: int; kind: Literal["any-name", "any-attribute", "any-subscript-dict", "any-subscript-other"]; snippet: str` — kills primitive-obsession on `tuple[int, str]`.
   - `PHASE3_ROOTS: Final[tuple[Path, ...]] = (Path("src/codegenie/plugins"), Path("src/codegenie/transforms"))`.
   - `ALLOWED_MARKER_RE: Final[re.Pattern[str]] = re.compile(r"#\s*fence:\s*any-allowed\s*\[(?P<adr>P3-ADR-\d{4})\]\s*$")`.
   - `KNOWN_BYPASSES: Final[frozenset[str]] = frozenset({"# type: ... comments", "from typing import Any as <alias>", "from typing_extensions import Any"})` — documented limitations, each with a tracking-issue comment.
   - `class _AnyAnnotationVisitor(ast.NodeVisitor)`: only descends into `AnnAssign.annotation`, `arg.annotation`, `FunctionDef.returns`, `AsyncFunctionDef.returns`. Inside an annotation subtree, flags `ast.Name(id="Any")`, `ast.Attribute(attr="Any")`, `ast.Constant(value=str)` whose value parses (via `ast.parse(value, mode="eval")`) to one of the same shapes (catches string forward-refs).
   - `def walk_any_annotations(src: str, path: Path) -> list[Violation]`: pure function — parses src, runs visitor, applies inline-marker filter via `ALLOWED_MARKER_RE`, returns sorted `Violation` list. Both live + planted tests call THIS function (mutation-resistance parity with `_fence.py`).
   - `def scan_phase3_surface() -> list[Violation]`: orchestrator — iterates `PHASE3_ROOTS`, reads files, calls `walk_any_annotations`. Asserts each root exists + has ≥ 1 non-`__init__.py` file (floor guard, AC-5.a).
2. Extend `pyproject.toml [tool.importlinter]` with two new `[[tool.importlinter.contracts]]` blocks:
   - `name = "codegenie.plugins must not import LLM SDKs"`, `type = "forbidden"`, `source_modules = ["codegenie.plugins"]`, `as_packages = true`, `forbidden_modules = ["anthropic", "langgraph", "openai", "langchain", "transformers"]`.
   - Same for `source_modules = ["codegenie.transforms"]`.
3. Amend `Makefile` `fence:` target to invoke `tests/unit/test_pyproject_fence.py tests/fence/` (covers AC-3).
4. Add `tests/fence/__init__.py`.
5. Add `tests/fence/test_phase3_importlinter_contracts_shape.py` — parses `pyproject.toml`, asserts each Phase 3 contract has the correct shape (AC-1 verifier).
6. Add `tests/fence/test_lint_imports_catches_planted_leak.py` — writes a temp `_test_planted_leak.py` containing `import anthropic` under `src/codegenie/plugins/`, runs `lint-imports` as `subprocess.run([...], check=False)`, asserts non-zero exit + failure message names `anthropic`, removes the file in a `finally` block (AC-2 mutation guard).
7. Add `tests/fence/test_fence_target_wiring.py` — parses `Makefile`, asserts the `fence:` recipe text contains both `tests/unit/test_pyproject_fence.py` and `tests/fence/` (AC-3 verifier).
8. Add `tests/fence/test_no_llm_in_transforms.py`:
   - Reuse `pkgutil.walk_packages` on `codegenie.plugins.__path__` + `codegenie.transforms.__path__`.
   - Live: assert `sys.modules.keys() & FORBIDDEN_LLM_SDKS == set()` AND `"codegenie.plugins" in sys.modules` (import-success guard, AC-4.d).
   - Parametrized per SDK (AC-4.b): plant a synthetic submodule that imports `<sdk>`, run the same walk-and-scan function, assert it catches the leak, clean up. Use a shared `_scan_phase3_runtime_closure()` helper so the live test and planted tests call the SAME function.
   - Metamorphic complement (AC-4.c): pre-populate `sys.modules["anthropic"]` directly (NOT via `codegenie.plugins`), assert fence does NOT fire.
   - Module-level docstring names ADR-0011 framing (audit + lint, NOT runtime).
9. Add `tests/fence/test_no_any_in_plugin_surface.py`:
   - Live scan via `_phase3_fence.scan_phase3_surface()`; assert `== []`.
   - Parametrized over the shape matrix in AC-5.b — each row is one mutation guard, calls `_phase3_fence.walk_any_annotations`.
   - Marker grammar tests (AC-5.c).
   - Zero-markers-at-Step-1 test (AC-5.d): `grep`-equivalent assertion.
   - Known-bypass fixture catalog (AC-5.e): `tests/fence/_fixtures/_known_bypasses.py` exercised against `KNOWN_BYPASSES` constant.
   - Lineno/snippet accuracy test (AC-5.f).
10. Add `tests/fence/test_kernel_frozen.py`:
    - Reads baselines via `_BASELINES` tuple from `tests/fence/_phase2_baseline.txt`.
    - `_run_git_diff(baseline, head) -> list[GitDiffEntry]` uses `git diff --name-status -M` (rename detection per AC-6.d).
    - Allowlist constant `_KERNEL_ALLOWLIST: Final[frozenset[Path]]` with `# adr: <id>` comments per entry.
    - Tests: live (assert intersection empty), baseline-shape (AC-6.b), helpful-error (AC-6.c via injected fake-diff source), renames-and-deletions (AC-6.d), framing docstring (AC-6.e), CI-fetch-depth note in module docstring (AC-6.f).
11. Run `pytest tests/fence/ -v` + `make lint-imports` + `make fence` + `make check`. Record green-after-removal evidence per fence (AC-7.b) in `_attempts/S1-05.md`.
12. Land AC-12 doc amendments (ADR-0010 §Consequences filename rename; High-level-impl.md §Step 1 line 30 config-path correction).

## TDD plan — red / green / refactor

The Phase 0 `_fence.py` precedent is the load-bearing pattern this story replicates: **the live test and the planted-violation tests call the SAME function in `src/`** so any regression in the production walker kills both. Test-local helpers break this property. Therefore: ship `src/codegenie/_phase3_fence.py` FIRST, then write tests against it.

### Red — write tests that are red by construction every CI run

Test file path: `tests/fence/test_no_any_in_plugin_surface.py` — but the Red here is **parametrized planted-violation tests against the walker**, NOT the live "scan the real surface" test (which is trivially green at S1-05 since S1-02/S1-03/S1-04 ship `Any`-clean by construction).

```python
# tests/fence/test_no_any_in_plugin_surface.py — RED phase
import textwrap
import pytest
from codegenie._phase3_fence import walk_any_annotations  # NOT YET EXISTS — drives Red

@pytest.mark.parametrize(
    "snippet,expected_hit",
    [
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
        ('x: "Any" = 1', True),  # string forward-ref
        ("x: int = 1", False),
        ("x: dict[str, int] = {}", False),
        ("isinstance(obj, Any)", False),  # runtime use, not annotation
        ("if TYPE_CHECKING:\n    from typing import Any", False),  # import, not annotation
    ],
)
def test_walker_catches_each_shape(snippet: str, expected_hit: bool) -> None:
    violations = walk_any_annotations(textwrap.dedent(snippet), path=Path("_test"))
    assert bool(violations) is expected_hit, (
        f"Shape `{snippet}` expected hit={expected_hit}, got {violations}"
    )
```

**Why this is red:** `codegenie._phase3_fence` does not exist yet → `ImportError` at collection → every parametrized case is red. Each row in the matrix is one independent mutation guard: if a future implementer drops support for `list[Any]`, that one row goes red while the others stay green.

Add three more red tests immediately:
- `test_floor_guard_fires_on_empty_root` (AC-5.a): parametrize-by-root, point at an empty `tmp_path` clone, assert the scanner raises a descriptive `AssertionError`.
- `test_marker_grammar` (AC-5.c): parametrize valid + invalid marker forms.
- `test_lint_imports_catches_planted_leak` (AC-2): subprocess-runs `lint-imports` against a planted import.

### Green — minimum to pass

1. **Implement `src/codegenie/_phase3_fence.py`** per Implementation outline §1 — the `_AnyAnnotationVisitor`, `walk_any_annotations`, `scan_phase3_surface`, `Violation` dataclass, `ALLOWED_MARKER_RE`, `KNOWN_BYPASSES`. `mypy --strict` clean.
2. **Add `pyproject.toml [tool.importlinter]` contracts** for `codegenie.plugins` + `codegenie.transforms`, both `as_packages = true`. Verify with `make lint-imports` (live + planted-leak subprocess test).
3. **Amend `Makefile` `fence:` target** to `pytest -q tests/unit/test_pyproject_fence.py tests/fence/`. Run `make fence` green.
4. **Write `tests/fence/_phase2_baseline.txt`** containing the current Phase 2 HEAD SHA (40-char hex, lowercase, no newline tolerated → strip on read).
5. **Implement the remaining test files** per Implementation outline §5–§10: importlinter shape, fence-target wiring, runtime-closure scan with all five AC-4 mutation guards, kernel-frozen with synthetic-diff injection point, marker grammar, known-bypass catalog, lineno/snippet accuracy.
6. **Live tests pass** because S1-02/S1-03/S1-04 shipped `Any`-clean and Phase 3 surface has zero LLM imports.
7. **Run `make check` end-to-end** — assert lint + typecheck + test + fence all green.

### Refactor

- Each fence test module: docstring naming the owning ADR + ADR-0011 framing posture (audit + lint, NOT runtime; documented limitations). Verified by a meta-test scanning required strings (AC-4.e, AC-6.e).
- `tests/fence/__init__.py` carries a module docstring catalogue: one line per fence file pointing to the owning ADR. This is the documentation seam in lieu of a `FenceRule` ABC (which would be Procrustean — see Notes-for-implementer).
- The `_BASELINES` tuple lives at module top of `test_kernel_frozen.py` even though only one row exists today — proves forward-compat without adding logic.
- **Edge cases lifted from prose into tests:**
  - **Type-comment annotations** (`# type: dict[str, Any]`): listed in `KNOWN_BYPASSES` with tracking-issue comment, exercised by `tests/fence/_fixtures/_known_bypasses.py` — the bypass is documented, not floating.
  - **Aliased imports** (`from typing import Any as _Any`): same — registered in `KNOWN_BYPASSES`. Step-1 PRs introducing the aliasing fail review by convention (CODEOWNERS + ADR-0011).
  - **`TYPE_CHECKING` block imports**: covered by AC-5.b row `if TYPE_CHECKING:\n    from typing import Any` → `expected_hit=False`. Visitor's annotation-context restriction handles this structurally.
  - **String forward-ref `x: "Any"`**: covered by AC-5.b row `x: "Any" = 1` → `expected_hit=True`. Visitor inspects `ast.Constant(value=str)` inside annotation positions.
- **Confirm the planted-violation evidence** is recorded in `_attempts/S1-05.md` (AC-7.b) — three independent 3-line blocks ("planted X → CI red on test_Y → removed → CI green"), one per fence. Missing any of the three fails the executor's Validator pass.
- **Optional property-based stretch** (deferred to a follow-up; flag in Notes): Hypothesis-fuzz the annotation grammar — generate synthetic annotations from `{int, str, Any, dict[K, V], list[T], Callable[..., T]}`, assert "every snippet whose AST contains `Any` in an annotation position is flagged; substituting `Any → int` makes the snippet clean." Hypothesis is already a dev-dep (`pyproject.toml` line 72) and there's prior art at `tests/unit/probes/test_registry_heaviness.py`. This is mutation-testing-as-property-testing.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/_phase3_fence.py` | **NEW** — production walker (parity with Phase 0 `_fence.py`). Houses `Violation`, `walk_any_annotations`, `scan_phase3_surface`, `ALLOWED_MARKER_RE`, `KNOWN_BYPASSES`. Same function called by live + planted-violation tests = mutation-resistance. |
| `pyproject.toml` | Extend `[tool.importlinter]` with two new Phase 3 LLM-SDK-forbidden contracts (`as_packages = true`). |
| `Makefile` | Amend `fence:` target to invoke `tests/unit/test_pyproject_fence.py tests/fence/` (AC-3; was previously single-file). |
| `tests/fence/__init__.py` | NEW — test package marker + module-docstring catalogue of every fence file with its owning ADR (the documentation seam in lieu of a `FenceRule` ABC). |
| `tests/fence/test_phase3_importlinter_contracts_shape.py` | NEW — parses `pyproject.toml`; asserts each Phase 3 contract has correct `forbidden_modules` set, `as_packages = true`, and correct `source_modules` (AC-1 verifier). |
| `tests/fence/test_lint_imports_catches_planted_leak.py` | NEW — subprocess test: plants `import anthropic` in a temp module under `codegenie.plugins`, runs `lint-imports`, asserts non-zero exit + named module in failure message, removes (AC-2). |
| `tests/fence/test_fence_target_wiring.py` | NEW — parses `Makefile`; asserts `fence:` recipe text contains all four fence-test paths (AC-3 verifier). |
| `tests/fence/test_no_llm_in_transforms.py` | NEW — runtime-closure scan + 5-SDK parametrized planted-positives + metamorphic complement + import-success guard + framing docstring (AC-4). |
| `tests/fence/test_no_any_in_plugin_surface.py` | NEW — calls `_phase3_fence.scan_phase3_surface()`; ships the AC-5.b shape matrix; AC-5.c marker grammar; AC-5.d zero-markers assertion; AC-5.e known-bypass catalog; AC-5.f lineno accuracy; AC-5.a floor guard. |
| `tests/fence/test_kernel_frozen.py` | NEW — git-diff fence (`--name-status -M` for rename detection) against Phase 2 baseline + ADR allowlist (`Final[frozenset[Path]]`); baseline-shape + ancestor checks; helpful-error guard via injected diff source; framing docstring + CI fetch-depth note (AC-6). |
| `tests/fence/_phase2_baseline.txt` | NEW — single line, 40-char hex commit SHA at S1-05 landing time. |
| `tests/fence/_fixtures/_known_bypasses.py` | NEW — fixture file (NOT under `src/`) exercising documented bypass shapes: type-comment annotation, aliased `Any` import, `typing_extensions.Any`. Each is either caught by the walker OR appears in `_phase3_fence.KNOWN_BYPASSES`. |
| `tests/fence/_fixtures/__init__.py` | NEW — fixture package marker. |
| `docs/phases/03-vuln-deterministic-recipe/ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` | EDIT — §Consequences filename `test_no_any_in_contract_layer.py` → `test_no_any_in_plugin_surface.py` (AC-12 — single line). |
| `docs/phases/03-vuln-deterministic-recipe/High-level-impl.md` | EDIT — §Step 1 line 30 `tools/lint/importlinter.cfg amended` → `pyproject.toml [tool.importlinter] amended` (AC-12). |
| `.github/workflows/*.yml` (if `make fence` runs there) | CHECK + edit if needed — assert `fetch-depth: 0` (or `git fetch --unshallow`) before the `make fence` step so `test_kernel_frozen.py`'s git-diff has the baseline SHA in history. If the workflow already runs `make check` with full clones, no edit needed. Surface either way in `_attempts/S1-05.md`. |

## Out of scope

- **`tests/static/test_capability_fence.py`** — handled by S4-05 (custom ruff rule for `*Capability(...)` construction).
- **`test_no_raw_str_for_domain_ids.py`** — ADR-0010 §Consequences names it as a future-state fence; deferred (not blocking Step 1; tracked as a Step-9 cross-cutting concern).
- **`test_event_taxonomy_complete.py`** — handled by S9-02 (event-taxonomy completeness + `$0.00` LLM-spend).
- **`test_phase5_contract_snapshot.py`** — handled by S6-06 (`transforms/__init__.py` re-export snapshot). This story's ADR-0001 honoring is partial: it prevents LLM/`Any` pollution of the contract surface but does NOT pin the re-export list.
- **`test_plugin_protocol_frozen.py`** (ADR-0004 method-count assertion) — handled by S2-01 (lands with the `Plugin` Protocol itself).
- **`tools/lint/importlinter.cfg`** as a separate file — manifest drift surfaced + resolved via AC-12 (amending `High-level-impl.md` §Step 1 line 30 in this story). Honors Rule 7 (surface conflicts, don't fork).
- **Top-level `plugins/` directory AST coverage** (arch G5 lines 22, ADR-0010 line 71): at S1-05 time the directory has no Python (only `PLUGINS.lock` + future YAML / recipe modules). The AST walker is NOT extended to that root in this story. Tracked as a Step-7 / S7-01 follow-up — once `plugins/vulnerability-remediation--node--npm/recipes/*.py` lands, the walker must be re-rooted (one-line edit to `_phase3_fence.PHASE3_ROOTS`). Surface this in `_attempts/S1-05.md` as a forward dependency.
- **Hypothesis property-based grammar fuzzing** (Refactor §optional stretch): deferred to a follow-up; the parametrized shape matrix in AC-5.b is the minimum mutation-resistance bar.
- **`make fence` against `plugins/` lint-imports coverage**: import-linter only sees Python packages under `root_packages` in `pyproject.toml`. The top-level `plugins/` directory isn't a `codegenie.*` package, so import-linter cannot reach it. Coverage of LLM imports in that directory is also a Step-7 follow-up (likely via a separate fence-test mechanism, e.g., AST scan of `plugins/**/*.py` for `import anthropic`-shaped statements). Out of scope here; do not retrofit.

## Notes for the implementer

- **Mirror Phase 0's `_fence.py` precedent.** The reason the live test and planted-violation tests share `parse_runtime_dep_names_from_toml` is that any regression in the production parser kills BOTH the canary and the live check — that's the mutation-resistance docstring at `src/codegenie/_fence.py:5-9`. This story keeps the same property: ship the walker in `src/codegenie/_phase3_fence.py`, have every test call it. Resist the temptation to keep the walker test-local; it breaks the mutation-resistance guarantee.
- **The planted-violation evidence step is load-bearing (Rule 12).** AC-7 now requires THREE independent evidence blocks (one per fence) in `_attempts/S1-05.md`, plus parametrized planted-positive tests **inside the test suite** so red-by-construction holds every CI run — not just at story-landing time.
- **`as_packages = true` in import-linter** matters — without it, only `codegenie.plugins` (the `__init__.py`) is scanned, not submodules. Phase 0's contracts use `as_packages = false` for a deliberate reason (CLI entry only); Phase 3's contracts want submodule coverage. **AC-1 unit test pins this**; do not let it regress.
- **The git-diff fence needs a stable baseline.** Don't try to compute "the Phase 2 ref" dynamically (CI-fragile); commit the SHA into `_phase2_baseline.txt`. The baseline rotates **at Phase-3 phase boundaries**, not per-story — every Phase 3 story can edit `_phase2_baseline.txt` only if its diff would be inside the ADR allowlist (i.e., the same thing the fence already checks). If the allowlist grows, the SHA stays put.
- **CI `fetch-depth: 0`** is a real concern: GitHub Actions defaults to a shallow clone. If `_phase2_baseline.txt`'s SHA isn't in history, `git diff` errors. Either set `fetch-depth: 0` in the checkout step or `git fetch --unshallow` before `make fence`. Surface this in `_attempts/S1-05.md` regardless — the fix is one line in workflow YAML.
- **`pkgutil.walk_packages` triggers eager imports** — that's what makes the runtime-closure scan work, but it also means a syntax error in a Phase 3 module surfaces here, not at `pytest` collection time. Surface that as a clearer error message ("module X failed to import while running fence; fix the import before re-running the fence").
- **Inline allowlist marker `# fence: any-allowed [P3-ADR-XXXX]`** — there should be **zero** of these at S1-05 landing (AC-5.d), and AC-5.c enforces the ADR-bracket grammar at all times. A bare marker, an empty bracket, or a malformed ADR ref is treated as a violation. The marker is the documented escape hatch; a future Phase 3 story that legitimately needs `Any` (e.g., a third-party-library shim) must land an ADR amendment first.
- **`isinstance(x, Any)` is a runtime check, not an annotation.** The `_AnyAnnotationVisitor` only descends into annotation contexts (`AnnAssign.annotation`, `arg.annotation`, `*.returns`), not the full AST. AC-5.b row `isinstance(obj, Any) → expected_hit=False` is the metamorphic complement that pins this. A future "wider" walker that flags runtime uses is over-fence (false positives kill credibility).
- **String forward-refs (`x: "Any"`) ARE annotations.** They evaluate at `typing.get_type_hints()` time. AC-5.b catches them by inspecting `ast.Constant(value=str)` *inside* annotation positions and re-parsing the string in `mode="eval"` — a small but load-bearing detail.
- **`Violation` is a `@dataclass(frozen=True)`**, not a `tuple[int, str]`. Future fences (S4-05 capability, S9-02 event-taxonomy) may aggregate output across walkers; an anaemic tuple makes that harder. The dataclass with `kind: Literal[...]` is the newtype-style typed primitive ADR-0010 mandates everywhere else in Phase 3.
- **ADR-0011 framing posture applies here.** These are *audit + lint* enforcement, not runtime guarantees. A determined contributor who edits the fence file in the same PR as their violation defeats the fence — that's why CODEOWNERS on `tests/fence/` + `tests/fence/_phase2_baseline.txt` is the social anchor (raise this in `_attempts/S1-05.md` as a CODEOWNERS follow-up if not already wired). Don't overclaim the fence's strength; AC-4.e / AC-6.e force docstrings that name the limitation.
- **No `FenceRule` ABC or registry.** The 5+ planned fences (kernel-frozen, any-annotation, llm-runtime, capability, event-taxonomy, contract-snapshot) share *category* but not *input/output shape* — kernel-frozen reads `git diff`, the AST fences walk source, contract-snapshot diffs JSON, capability fence is a ruff custom rule. Forcing one Protocol degrades each. The documentation seam is `tests/fence/__init__.py`'s module docstring catalogue — that's enough. **Rule 2: three similar lines is better than premature abstraction.**
- **The `_BASELINES` tuple is forward-compatible by design.** Only one row today (`("phase-2", Path("tests/fence/_phase2_baseline.txt"))`); Phase 4 / 5 / … append rows via ADR amendment. The test iterates the tuple — no walker rewrite needed when Phase 4 ships its own baseline.
- **`make lint-imports` is already wired into `make check`** per Phase 0 ADR-0006; AC-3 ALSO wires the new `tests/fence/` collection into `make fence` directly (per arch §Testing strategy §CI gates line 1042). Both routes run the tests; the explicit `make fence` route matches the documented gate name.
- **Forward dependency to S7-01**: when `plugins/vulnerability-remediation--node--npm/recipes/*.py` lands, extend `_phase3_fence.PHASE3_ROOTS` with `Path("plugins")` (one-line edit). Surface this in `_attempts/S1-05.md` so the S7-01 author finds it.
