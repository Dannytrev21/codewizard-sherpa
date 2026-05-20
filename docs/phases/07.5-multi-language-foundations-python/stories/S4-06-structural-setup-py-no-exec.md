# Story S4-06 — Structural `setup.py` parsing — never executed (G6)

**Step:** Step 4 — Build the Python Layer A/B probes and the `tree-sitter-python` grammar row
**Status:** Ready
**Effort:** M
**Depends on:** S4-05
**ADRs honored:** ADR-0007

## Context
`setup.py` is arbitrary executable Python — a hostile repo whose only manifest is a `setup.py` calling `os.system(...)` is a real, common shape, and the conventional pip approach (execute it to read metadata) is RCE on the gather process. ADR-0007 forbids execution categorically: `setup.py`/`setup.cfg` are read **as text** and parsed structurally — tree-sitter for `setup.py`, INI for `setup.cfg` — and an AST test proves the Python probe code contains no `exec`/`eval`/`__import__`/`importlib`-of-a-repo-file. This story extends `PythonManifestProbe` with structural `setup.py`/`setup.cfg` parsing and lands the G6 AST fence.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — Python Layer A/B probes` — `setup.py` parsed structurally (tree-sitter), never executed; functional core / imperative shell makes "never executes" a structural property.
- **Architecture:** `../phase-arch-design.md §Edge cases` row 5 — hostile `setup.py` read as text, the dynamic call observed as a `confidence="low"` "not statically analyzable" fact, never executed.
- **Architecture:** `../phase-arch-design.md §Adversarial tests` — "an AST test asserts no `exec`/`eval`/`importlib`-of-repo-file in the Python probe code."
- **Phase ADRs:** `../ADRs/0007-python-probes-hardened-parse-only-no-exec.md` — ADR-0007 — `setup.py` read as text never executed; an AST test forbids `exec`/`eval`/`importlib`-of-repo-file; a parse failure on a hostile `setup.py` is a `confidence="low"` fact, not a fallback execution.
- **Source design:** `../final-design.md §Synthesis ledger CR-4` — the security lens supplied the parse-only / no-exec discipline; the `1.15×` gate was dropped.
- **Existing code:** `src/codegenie/probes/python/manifest.py` (lands S4-05) — `PythonManifestProbe`; this story extends it with the `setup.py`/`setup.cfg` path.
- **Existing code:** `src/codegenie/grammars/lock.py` — `language_for("python")` (lands S4-01) — the tree-sitter parse path for `setup.py`.
- **Existing code:** `configparser` (stdlib) — INI parsing for `setup.cfg`.
- **Existing code:** the `forbidden-patterns` pre-commit hook config — already bans `eval(`/`exec(`/`__import__(`/`os.system` repo-wide; the new AST test is the probe-scoped structural complement.
- **Existing code:** `tests/fence/` — the structural-defense test directory; a probe-scoped AST-walk test belongs alongside the existing fences.

## Goal
Parse `setup.py` structurally (tree-sitter) and `setup.cfg` (INI) as text without executing them, and land the AST test forbidding `exec`/`eval`/`__import__`/`importlib`-of-a-repo-file anywhere in `src/codegenie/probes/python/`.

## Acceptance criteria
- [ ] A red AST-walk test over `src/codegenie/probes/python/` asserts no `exec(`, `eval(`, `__import__(`, or `importlib`-of-a-repo-file call/import appears in any module; it is committed and green (it must already pass if S4-02/S4-04/S4-05 stayed pure — if it fails, that is a real finding to fix).
- [ ] A red test asserts `PythonManifestProbe` extracts `name`/`install_requires` from a *static* `setup.py` (a literal `setup(name="x", install_requires=[...])` call) via tree-sitter structural parsing — `setup.py` is never executed (verified by a monitor / by the absence of any side effect).
- [ ] A hostile `setup.py` (`os.system(...)`, `subprocess`, `__import__`, a dynamically-computed `name`) is read as text and yields a `confidence="low"` "not statically analyzable" fact — the probe never executes it, never crashes.
- [ ] `setup.cfg` is parsed via `configparser` under the byte cap; a malformed `setup.cfg` yields a structured-error / honest-low slice.
- [ ] The structural parse reuses the S4-05 byte/depth caps — `setup.py`/`setup.cfg` are capped before parse; a `python.setup_py_not_static` warning ID is in `_WARNING_IDS`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on touched files; Status set to `Done`.

## Implementation outline
1. Add an AST-walk fence test `tests/fence/test_python_probes_no_exec.py` that walks every module under `src/codegenie/probes/python/` with the `ast` module and asserts no `Call`/`Import` node names `exec`/`eval`/`__import__` or an `importlib` import-of-a-repo-file.
2. Extend `PythonManifestProbe` (S4-05) with a `setup.py` branch: read the file as text under the byte cap, parse with `language_for("python")` (tree-sitter), and walk the tree for a top-level `setup(...)` call with *literal* keyword arguments.
3. Extract `name`/`version`/`install_requires` only from literal arguments; a non-literal (dynamically-computed) argument → record "not statically analyzable" and `confidence="low"`.
4. Add a `setup.cfg` branch: `configparser` parse under the byte cap; extract `[metadata]`/`[options]` keys.
5. On a tree-sitter parse failure of a hostile `setup.py`, return a `confidence="low"` fact with `python.setup_py_not_static` — **never** fall back to importing or `exec`-ing the file.
6. Add `python.setup_py_not_static` to `_WARNING_IDS`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/fence/test_python_probes_no_exec.py`.
Test name: `test_python_probes_contain_no_exec_or_dynamic_import`.
```python
def test_python_probes_contain_no_exec_or_dynamic_import() -> None:
    # arrange: collect every *.py module under src/codegenie/probes/python/.
    # act: ast.parse each and walk the tree.
    # assert: no Call to exec/eval/__import__; no importlib-of-a-repo-file;
    #         (this is the G6 structural proof — RCE on setup.py is impossible).
```
Plus, in `tests/unit/probes/python/test_python_manifest_probe.py`, `test_setup_py_parsed_structurally_never_executed`:
```python
async def test_setup_py_parsed_structurally_never_executed(tmp_path) -> None:
    # arrange: a setup.py that calls setup(name="pkg", install_requires=["requests"])
    #          AND a sentinel side effect (e.g. writes a marker file) at module top level.
    # act: await PythonManifestProbe().run(repo, ctx).
    # assert: name/install_requires extracted; the sentinel marker file was NEVER written
    #         (proving setup.py was read as text, not executed).
```
The fence test must fail if any probe module contains a forbidden node; the structural-parse test fails today because the `setup.py` branch does not exist.

### Green — make it pass
Extend `PythonManifestProbe` with the `setup.py`/`setup.cfg` text-read + structural-parse branches. Tree-sitter walk extracts only literal `setup(...)` kwargs; non-literals → `confidence="low"`. No code path imports or executes the file.

### Refactor — clean up
Extract the tree-sitter `setup(...)`-call walk into a pure helper. Add type hints, a docstring tracing ADR-0007 edge case #5, and confirm a hostile `setup.py` parse failure routes to the `confidence="low"` fact, never to a fallback.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/probes/python/manifest.py` | Add the structural `setup.py` / `setup.cfg` parsing branches to `PythonManifestProbe`. |
| `tests/fence/test_python_probes_no_exec.py` | The G6 AST-walk fence over `probes/python/`. |
| `tests/unit/probes/python/test_python_manifest_probe.py` | The static-`setup.py` extraction + hostile-`setup.py` no-exec tests. |

## Out of scope
- Build-system backend detection from `setup.py` — S4-04 uses `setup.py` *presence* only; this story extracts metadata, still without execution.
- Import-graph parsing — S4-07.
- The Python manifest sub-schema — S4-08.
- A sandboxed `setup.py` execution mode — explicitly never (ADR-0007: reversibility is Low; execution is a vulnerability, not a design option).

## Notes for the implementer
- A tree-sitter parse failure on a hostile `setup.py` must yield a `confidence="low"` "not statically analyzable" fact — **never** a fallback that imports or `exec`s the file (ADR-0007's named drift risk: "a parse failure handled by a fallback that imports or `exec`s the file").
- The AST fence is the structural gate — it makes "never executes `setup.py`" provable, not merely hoped. If S4-02/S4-04/S4-05 wrote any forbidden node, the fence fails and that is a real bug to fix before this story is `Done`.
- Only *literal* `setup(...)` keyword arguments are extractable — a dynamically-computed `name` or a `install_requires` built by a loop is correctly reported as `confidence="low"`; do not try to evaluate it.
- Functional core / imperative shell is what makes no-exec structural: the parsing helpers are pure; `run()` only *reads*. A pure parser cannot execute the file it parses.
- `setup.cfg` is INI — use `configparser`, capped before parse; do not conflate it with the `setup.py` tree-sitter path.
