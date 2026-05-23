# Story S1-07 — Workflow-determinism fences (import-linter + AST + xfail fixture)

**Step:** Step 1 — Domain primitives, typed event contracts, and structural fences
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S1-03, S1-05, S1-06
**ADRs honored:** ADR-0004 (three-layer determinism: import-linter + AST + Replayer; this story lands the first two), production ADR-0005 (precedent: `codegenie-no-llm-sdks` import-linter contract — same shape)

## Context
ADR-0004 names three defense layers; this story lands the first two — `import-linter` at pre-commit and the AST fence at `make test` — so non-determinism is a build break **before any workflow file exists**. The Replayer test (S5-05) catches transitive non-determinism (LangGraph version drift, dict-iteration-order changes between Python minors) but only after a workflow has been written. The architect-stated principle from `High-level-impl.md §Order of operations`: *"Contracts and fences land first because the determinism rules of Temporal workflow code make retrofit expensive — once a `set(` literal or a `datetime.now()` call ships into a workflow body, every later test layer becomes a forensic exercise."* The deliberate-violation xfail fixture proves the fence bites.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C1 — VulnRemediationWorkflow §Dependencies` — exact forbidden-module set: `random`, `time`, `datetime`, `uuid`, `os`, `socket`, `httpx`, `requests`, `redis`, `psycopg`, `asyncpg`, `subprocess`, `codegenie.exec`, `codegenie.transforms`, `codegenie.probes`
  - `../phase-arch-design.md §Scenario 3 — Adversarial: replay-determinism violation caught by CI Replayer` — the three layers in action
  - `../phase-arch-design.md §Edge case 5` — the three-layer defense; build break "with a typed error pointing at the offending line"
  - `../phase-arch-design.md §Harness engineering — Replay` — three layers in order
- **Phase ADRs:**
  - `../ADRs/0004-workflow-determinism-enforcement-three-layers.md` — Decision §"three layers, strictly ordered"; Consequences §`import-linter` config + AST walker + fixture history
- **Production ADRs:**
  - `../../../production/adrs/0005-llm-sdk-firewall.md` *(or equivalent fence-precedent ADR)* — `codegenie-no-llm-sdks` `import-linter` contract is the precedent shape
- **Source design:**
  - `../final-design.md §Test plan — Replay-determinism (CI-gating)`
- **Existing code:**
  - `tools/import-linter.toml` (or the `pyproject.toml § [tool.importlinter]` section) — the existing `codegenie-no-llm-sdks` contract is the canonical reference for contract shape (`type = "forbidden"`, `source_modules`, `forbidden_modules`)
  - `tests/fence/test_pyproject_fence.py` — Phase 0 fence precedent (one Python module reading a config and asserting at test-time); read this for shape
  - `Makefile` §`make lint-imports` target — runs `lint-imports` against the registered contracts
- **External docs:**
  - `https://import-linter.readthedocs.io/en/stable/contract_types.html#forbidden` — "forbidden" contract type used here

## Goal
Land (a) the `codegenie.durable.workflows-must-be-pure` `import-linter` forbidden-contract, (b) the AST fence `tests/fence/test_workflow_determinism.py` walking every file under `src/codegenie/durable/workflows/`, and (c) a deliberate-violation xfail fixture proving both layers catch a forbidden token.

## Acceptance criteria
- [ ] `tools/import-linter.toml` (or `pyproject.toml [tool.importlinter.contracts]`) declares a `type = "forbidden"` contract `codegenie.durable.workflows-must-be-pure` with `source_modules = ["codegenie.durable.workflows"]` and `forbidden_modules = ["random", "time", "datetime", "uuid", "os", "socket", "httpx", "requests", "redis", "psycopg", "asyncpg", "subprocess", "codegenie.exec", "codegenie.transforms", "codegenie.probes"]`.
- [ ] `make lint-imports` passes against the (empty) `src/codegenie/durable/workflows/__init__.py` package — proves the contract is registered and active.
- [ ] `tests/fence/test_workflow_determinism.py` walks every `*.py` file under `src/codegenie/durable/workflows/` with `ast.parse` and rejects: any `ast.Name` matching `set` *as a bare call* (heuristic: `ast.Call` whose `func` is `ast.Name(id="set")`), any attribute access whose dotted path begins with `random.`, `time.`, `os.`, `datetime.now`, `uuid.uuid4`, or reads `os.environ`. The walker reports filename + line + offending token in the failure message.
- [ ] `src/codegenie/durable/workflows/__init__.py` exists (empty package with a docstring naming the determinism fences); the AST fence runs green over it.
- [ ] `tests/fence/test_workflow_determinism_xfail_fixture.py` — copy a deliberately violating file into a tmpdir, point the AST walker at it, assert the walker raises (marked `@pytest.mark.xfail(strict=True)` or asserted via an inverted check; **prefer an inverted positive assertion** over `xfail` because `xfail` hides bugs). The fixture file lives in `tests/fence/fixtures/workflow_determinism/violator.py` and contains `import random; def bad(): return random.random()`.
- [ ] `tests/fence/test_workflow_determinism_xfail_fixture.py` *also* verifies that running `lint-imports` against a deliberately violating module (under `tests/fence/fixtures/workflow_determinism_imports/`) fails with the expected contract violation message (skip if `lint-imports` is not on `PATH` in the test env; do not silently no-op).
- [ ] The forbidden-module list and the AST forbidden-token list are kept as `Final` tuples *at the top* of the AST fence module (`_FORBIDDEN_DOTTED_PREFIXES: Final[tuple[str, ...]]`), so vocabulary drift between the import-linter contract and the AST walker is grep-able. Add a smoke test `test_vocabulary_alignment_between_import_linter_and_ast_walker` that parses the `import-linter` config and asserts every module-name in `forbidden_modules` appears as a dotted-prefix root in the AST walker's list (or surface the intentional difference — `os.environ` is AST-only, e.g.).
- [ ] The AST fence walks files using `ast.walk` (not regex on source text) so a `# random.random()` comment doesn't false-positive.
- [ ] `mypy --strict tests/fence/test_workflow_determinism.py` is clean.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on touched files.

## Implementation outline
1. Add the `codegenie.durable.workflows-must-be-pure` contract to `tools/import-linter.toml` (or `pyproject.toml` if that's where contracts live in this codebase — read the file first; do not duplicate).
2. Create `src/codegenie/durable/workflows/__init__.py` with a docstring naming the three-layer fence (import-linter at pre-commit, AST at `make test`, Replayer at CI) and citing ADR-0004.
3. Create `tests/fence/test_workflow_determinism.py`:
   - Module-level `_FORBIDDEN_DOTTED_PREFIXES: Final[tuple[str, ...]] = ("random.", "time.", "uuid.uuid4", "datetime.now", "os.environ")` and `_FORBIDDEN_BARE_CALLS: Final[tuple[str, ...]] = ("set",)`.
   - `_iter_workflow_files() -> Iterator[Path]` yields all `*.py` under `src/codegenie/durable/workflows/`.
   - `_walk_module(tree: ast.AST) -> list[Violation]` collects every `Call` / `Attribute` whose dotted path matches a forbidden prefix.
   - One test per file invoking the walker and asserting empty violations.
4. Create the xfail fixture + companion test asserting the walker raises against the violating fixture (don't use `pytest.xfail` — use an explicit `pytest.raises`/return-violations assertion so the test is positive evidence the fence bites).
5. Create the vocabulary-alignment smoke test that parses the `import-linter` config and cross-checks the AST walker's list.
6. Run `make lint-imports` + `pytest tests/fence/test_workflow_determinism.py` until green.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/fence/test_workflow_determinism.py`
```python
import ast
from pathlib import Path
from typing import Final

_FORBIDDEN_DOTTED_PREFIXES: Final[tuple[str, ...]] = (
    "random.", "time.", "uuid.uuid4", "datetime.now", "os.environ",
)
_FORBIDDEN_BARE_CALLS: Final[tuple[str, ...]] = ("set",)

def _walk(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_BARE_CALLS:
                violations.append(f"{path}:{node.lineno} bare {node.func.id}(")
        if isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            for forbidden in _FORBIDDEN_DOTTED_PREFIXES:
                if dotted.startswith(forbidden):
                    violations.append(f"{path}:{node.lineno} {dotted}")
    return violations

def test_workflow_files_have_no_nondeterminism():
    root = Path("src/codegenie/durable/workflows")
    assert root.is_dir(), "workflows package must exist (empty __init__.py is fine)"
    for py in root.rglob("*.py"):
        violations = _walk(py)
        assert not violations, "non-determinism in workflow body:\n" + "\n".join(violations)
```

Test file path: `tests/fence/test_workflow_determinism_xfail_fixture.py`
```python
def test_walker_catches_random_import_in_fixture():
    from tests.fence.test_workflow_determinism import _walk
    from pathlib import Path
    fixture = Path("tests/fence/fixtures/workflow_determinism/violator.py")
    violations = _walk(fixture)
    assert any("random" in v for v in violations), (
        "AST fence failed to flag 'random.random()' in fixture — "
        "the determinism layer is asleep."
    )

def test_walker_catches_bare_set_literal_in_fixture():
    from tests.fence.test_workflow_determinism import _walk
    from pathlib import Path
    fixture = Path("tests/fence/fixtures/workflow_determinism/set_violator.py")
    violations = _walk(fixture)
    assert any("set" in v for v in violations)

def test_import_linter_contract_rejects_violator_module(tmp_path):
    # Skip if lint-imports is not on PATH (some unit-only environments)
    import shutil, subprocess, pytest
    if shutil.which("lint-imports") is None:
        pytest.skip("lint-imports not available in this environment")
    # invoke against the fixtures dir; assert non-zero exit + expected
    # contract violation message in stdout/stderr
    # (exact invocation depends on tools/import-linter.toml layout)
```

Test file path: `tests/fence/test_workflow_determinism_vocabulary_alignment.py`
```python
def test_import_linter_and_ast_walker_share_vocabulary_roots():
    # Parse tools/import-linter.toml (or pyproject.toml) and extract the
    # workflows-must-be-pure forbidden_modules list.
    # Assert every root (split('.')[0]) is either in _FORBIDDEN_DOTTED_PREFIXES
    # roots OR is documented as "import-linter only" in a Final[set[str]].
    ...
```

### Green — make it pass
Empty `src/codegenie/durable/workflows/__init__.py`. The contract added to `import-linter` config. The walker reads files, parses ASTs, returns violations; one test per file (a single parametrized test is fine).

### Refactor — clean up
- Pull `_dotted(node: ast.Attribute) -> str` into a helper that walks `Attribute` chains correctly (`os.environ.get` -> `"os.environ.get"`).
- The fence module's `Final` vocabulary tables are the contract — comment each forbidden prefix with *why* (e.g., `# datetime.now() is wall-clock; use workflow.now() instead`).
- The xfail-fixture violating file (`tests/fence/fixtures/workflow_determinism/violator.py`) must be **excluded** from the production workflows package so the regular AST sweep doesn't fail on it — that's automatic because it lives under `tests/`, not under `src/`.
- The vocabulary-alignment test should print a clear diff if drift is detected (`forbidden_modules - ast_roots = {...}`).

## Files to touch
| Path | Why |
|---|---|
| `tools/import-linter.toml` *(or `pyproject.toml`)* | Register `codegenie.durable.workflows-must-be-pure` forbidden contract |
| `src/codegenie/durable/workflows/__init__.py` | Empty package with docstring citing ADR-0004 three layers |
| `tests/fence/test_workflow_determinism.py` | AST walker + sweep over `src/codegenie/durable/workflows/` |
| `tests/fence/test_workflow_determinism_xfail_fixture.py` | Walker flags the deliberate violator; `lint-imports` rejects too |
| `tests/fence/test_workflow_determinism_vocabulary_alignment.py` | Cross-check import-linter contract ↔ AST walker vocabulary |
| `tests/fence/fixtures/workflow_determinism/violator.py` | Deliberately violating file (`import random`) |
| `tests/fence/fixtures/workflow_determinism/set_violator.py` | Deliberately violating file (bare `set(...)` call) |
| `tests/fence/fixtures/workflow_determinism_imports/__init__.py` | A module the `lint-imports` xfail test points at |
| `tests/fence/fixtures/workflow_determinism_imports/violator.py` | `import psycopg` to exercise the import-linter contract |

## Out of scope
- **Replayer test** (`tests/workflows/test_replay_determinism.py`) — Step 5 (S5-05). The third determinism layer.
- **`forbidden-patterns` pre-commit hook regex** — repo-wide already; this story does not add new global patterns. If a workflow-body-specific regex is needed, surface in S8-05 (the `while ... retry` fence).
- **No-retry-loop fence over workflow bodies** — Step 8 (S8-05).
- **Per-Python-minor matrix** for the Replayer — Step 5.

## Notes for the implementer
- **`set(` is a Python builtin** with non-deterministic iteration order in unbenchmarked code paths — Temporal docs explicitly call it out. The AST walker catches the literal `set(...)` call form; the `import-linter` contract cannot help here (no module to forbid). That's exactly why ADR-0004 is layered.
- **Prefer positive assertions over `@pytest.mark.xfail`.** `xfail` swallows the failure and reports green — terrible at communicating that the fence is working. The fixture test invokes the walker directly and `assert` it produces violations.
- The forbidden-modules list mirrors arch §C1 exactly — **copy it verbatim**, do not paraphrase. Drift is what the vocabulary-alignment test catches.
- `import-linter` config syntax: `type = "forbidden"`, `name = "..."`, `source_modules = [...]`, `forbidden_modules = [...]`. Read the existing `codegenie-no-llm-sdks` contract for the exact shape used by this repo.
- The "empty `src/codegenie/durable/workflows/__init__.py`" is intentional — Step 5 lands the workflow bodies; this story lands the *walls* before the rooms. The AST walker exits green over an empty directory, which proves the walker runs.
- The `lint-imports` CLI sub-step of the xfail-fixture test may not run in all test environments (CI yes, hermetic-pytest-only no). Skip-not-no-op with a clear `pytest.skip` message; surface in the implementer notes that the import-linter side of the xfail is covered by `make lint-imports` in CI.
- The `_dotted` helper is subtle: `ast.Attribute(value=ast.Attribute(value=ast.Name(id="os"), attr="environ"), attr="get")` → `"os.environ.get"`. Walk the `value` chain until you hit an `ast.Name`. If the base is not a `Name` (e.g., a subscript or call), bail out and return `""` — the walker is heuristic, not a type-checker.
- A deliberate trade-off: the AST walker is **string-based after parsing**, so it does not resolve aliasing (`import time as t; t.time()` would slip past). That's OK — `import-linter` catches the `import time` half. The two layers complement.
