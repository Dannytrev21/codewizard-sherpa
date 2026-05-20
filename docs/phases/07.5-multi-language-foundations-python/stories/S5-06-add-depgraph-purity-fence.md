# Story S5-06 — Add `tests/fence/test_depgraph_purity.py` AST fence (G5)

**Step:** Step 5 — Build the Python dep-graph strategies (pip / poetry / uv)
**Status:** Ready
**Effort:** S
**Depends on:** S5-02
**ADRs honored:** ADR-0008

## Context
ADR-0008 makes Python dep-graph extraction structurally incapable of network egress — but a structural claim needs a structural test. This story lands the `tests/fence/test_depgraph_purity.py` AST fence: an AST-walk over `src/codegenie/depgraph/python/` that fails if any module imports or calls `urllib`/`requests`/`http`/`socket`/`subprocess`. It is the standing CI-blocking proof that the dep-graph strategies cannot fetch — a planted `import requests` in that sub-package turns it red.

## References — where to look
- **Architecture:** `../phase-arch-design.md §LanguagePack contract-snapshot fence` and `§CI gates` — "`tests/fence/test_depgraph_purity.py` — AST-walk over `src/codegenie/depgraph/python/` asserting no `urllib`/`requests`/`http`/`socket`/`subprocess` import and no network/exec call".
- **Architecture:** `../phase-arch-design.md §Agentic best practices — Tool-use safety` — "`tests/fence/test_depgraph_purity.py` is an AST proof that `src/codegenie/depgraph/python/` imports no `urllib`/`requests`/`http`/`socket`/`subprocess`".
- **Phase ADRs:** `../ADRs/0008-python-depgraph-pure-parsing-no-resolution.md` — ADR-0008 — "A new `tests/fence/test_depgraph_purity.py` AST fence proves `src/codegenie/depgraph/python/` imports no `urllib`/`requests`/`http`/`socket`/`subprocess`"; consequences: "a planted `import requests` in that subpackage turns it red".
- **Existing code:** `tests/fence/test_transforms_module_purity.py` — the precedent AST-walk module-purity fence (allowlist as `frozenset`, `ast.walk`, planted-positive tests).
- **Existing code:** `tests/fence/test_no_llm_in_transforms.py` — the planted-positive / mutation-resistance pattern (one shared scanner, both live + planted tests call it).
- **Existing code:** `src/codegenie/depgraph/python/` (S5-01..S5-04) — the package this fence walks.

## Goal
Add `tests/fence/test_depgraph_purity.py` — an AST-walk fence over `src/codegenie/depgraph/python/` that fails on any `urllib`/`requests`/`http`/`socket`/`subprocess` import or call.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and fails before the fence module exists — then green.
- [ ] The fence AST-walks *every* `.py` file under `src/codegenie/depgraph/python/` and asserts none imports (`import` or `from ... import`) `urllib`, `requests`, `http`, `socket`, or `subprocess`.
- [ ] The fence also asserts no *call* to those modules' surfaces appears (e.g. an attribute call on an aliased import) — the import check alone is not sufficient.
- [ ] A planted-positive test: a temporary module under `depgraph/python/` containing `import requests` (one forbidden module per parametrized case) turns the fence red — proving the scanner has teeth.
- [ ] A metamorphic negative: the live (clean) package passes; a module importing an *allowed* dependency (`tomllib`, `networkx`, `pathlib`) does NOT trip the fence.
- [ ] The fence is collected by `make fence` / `pytest tests/fence/` and is CI-blocking.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on the new test file; `pytest tests/fence/test_depgraph_purity.py` green; Status set to `Done`.

## Implementation outline
1. Create `tests/fence/test_depgraph_purity.py`.
2. Define a module-level `_FORBIDDEN_ROOTS: frozenset[str]` = `{"urllib", "requests", "http", "socket", "subprocess"}`.
3. Write a single shared scanner — `_scan_depgraph_python_forbidden() -> dict[str, set[str]]` (file → forbidden roots found) — that `ast.parse`s each `.py` under `src/codegenie/depgraph/python/` and walks for `ast.Import` / `ast.ImportFrom` nodes whose root module is forbidden, plus `ast.Call`/`ast.Attribute` nodes resolving to a forbidden alias.
4. The live test calls the shared scanner and asserts the result is empty.
5. The planted-positive tests (parametrized over the five forbidden roots) write a temp module under `depgraph/python/`, call the *same* scanner, assert the planted import is caught, then clean up — mirroring `test_no_llm_in_transforms.py`'s mutation-resistance pattern.
6. Add a module docstring framing the fence: a static AST proof, the complement to S5-05's dynamic monitors.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/fence/test_depgraph_purity.py`.
Test name: `test_depgraph_python_imports_no_network_or_subprocess`.
```python
def test_depgraph_python_imports_no_network_or_subprocess() -> None:
    # arrange + act: AST-walk every module under src/codegenie/depgraph/python/.
    offenders = _scan_depgraph_python_forbidden()
    # assert: the live package imports zero network/subprocess surface
    #         (ADR-0008 — dep-graph extraction cannot fetch).
    assert offenders == {}, (
        f"depgraph/python/ imported a forbidden network/subprocess module: {offenders}"
    )
```
This fails with `ImportError`/`NameError` until the scanner exists. Then add the parametrized planted-positive `test_fence_catches_each_planted_forbidden_import` (plants `import requests`, `import socket`, ... one at a time, asserts the scanner catches it) — these must fail until the scanner correctly detects planted imports.

### Green — make it pass
Implement the shared `_scan_depgraph_python_forbidden` scanner with `ast.parse` + `ast.walk`; the live `depgraph/python/` package should already pass it if S5-01..S5-02 stayed pure. Wire the planted-positive parametrized tests calling the same scanner.

### Refactor — clean up
Add docstrings citing ADR-0008 G5; ensure the scanner handles `from urllib.parse import ...` correctly — `urllib.parse` is import-safe so the fence should target the *request* surfaces; decide explicitly whether `urllib` as a root is forbidden wholesale (the arch-design says `urllib`) — if so, S5-01's host extraction must avoid `import urllib.parse` at module scope or the fence is over-broad. **Resolve this:** match the arch-design's `urllib` literal — forbid the `urllib` root, and have S5-01 extract the host without an `import urllib` (e.g. a small pure string split) OR scope the fence to `urllib.request`/`urllib.error` and note the deviation. Pick one, document why, keep the fence and S5-01 consistent.

## Files to touch
| Path | Why |
|---|---|
| `tests/fence/test_depgraph_purity.py` | The new AST-walk purity fence over `depgraph/python/`. |

## Out of scope
- The dynamic zero-egress monitors — S5-05 (this is the static complement).
- Walking `depgraph/` outside the `python/` sub-package — the fence is scoped to `depgraph/python/` per ADR-0008.
- The `import-linter` contract for `codegenie.depgraph.python` — finalized in S8-02 (this AST fence is the narrower Python-scoped proof ADR-0008 calls for; `import-linter` is the structural complement).

## Notes for the implementer
- **Watch the `urllib` ambiguity.** The arch-design forbids `urllib` wholesale, but S5-01 may use `urllib.parse.urlsplit` to extract an index host (no network). Resolve the conflict in the refactor step — either S5-01 avoids `import urllib` entirely (a pure string split for the host) and the fence forbids `urllib` as written, or the fence is scoped to `urllib.request`/`urllib.error` with a documented deviation. Do not leave the fence and S5-01 contradicting each other (Rule 7 — surface the conflict, do not average).
- Mirror `test_no_llm_in_transforms.py`'s mutation-resistance: the live check and the planted-positive tests must call the *same* scanner so a regression in the scanner kills both.
- Use `importlib.invalidate_caches()` before re-scanning in planted-positive tests so a freshly-written temp module is discovered (the `test_no_llm_in_transforms.py` precedent documents this stale-`FileFinder` trap).
- Clean up planted temp modules in a `finally` block — a leftover `_test_planted_*.py` under `depgraph/python/` would break every later run.
- The call-check (not just the import-check) matters: `import socket as s; s.socket()` would slip past a pure import-name scan — walk for forbidden attribute-call chains too.
- This fence is CI-blocking (G5) — it must be fast (it is, one AST parse per small file) and live under `tests/fence/` so `make fence` collects it.
