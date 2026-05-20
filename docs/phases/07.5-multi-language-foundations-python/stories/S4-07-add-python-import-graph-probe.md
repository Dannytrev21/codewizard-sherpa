# Story S4-07 — Add `PythonImportGraphProbe` (Layer B)

**Step:** Step 4 — Build the Python Layer A/B probes and the `tree-sitter-python` grammar row
**Status:** Ready
**Effort:** M
**Depends on:** S4-01
**ADRs honored:** ADR-0004, ADR-0007

## Context
The Python search adapter (S6-01) and the `vulnerability-remediation--python--pip` plugin need an import graph — which modules reference which — to scope a fix and find cross-file impact. `PythonImportGraphProbe` is the single Layer B probe: it walks `import` / `from ... import` statements across `*.py` files via tree-sitter, building a module-to-module edge set. It is parse-only under hard caps (ADR-0007) and `task_specific` so the `language_filter` keeps it off Node-only repos.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — Python Layer A/B probes` — `PythonImportGraphProbe` is Layer B, `tier="task_specific"`; tight `declared_inputs` (`**/*.py`); hard caps before parse.
- **Architecture:** `../phase-arch-design.md §Open questions deferred to implementation` — OQ3: whether the import-graph probe covers `sys.path` / namespace-package resolution or stays minimal is an implementation-time scoping call decided in this story — the phase proves the axis, not Python feature-parity.
- **Phase ADRs:** `../ADRs/0007-python-probes-hardened-parse-only-no-exec.md` — ADR-0007 — parse-only, hard caps before parse, functional core / imperative shell.
- **Phase ADRs:** `../ADRs/0004-python-detection-as-base-tier-probe-not-prepass.md` — ADR-0004 — `task_specific` probes admitted by `language_filter`.
- **Existing code:** `src/codegenie/probes/layer_b/tree_sitter_import_graph.py` — the precedent Node import-graph probe; tree-sitter-driven `import` walk, edge-set slice shape, `declared_inputs` discipline.
- **Existing code:** `src/codegenie/grammars/lock.py` — `language_for("python")` (lands S4-01) — the tree-sitter parse path.
- **Existing code:** `src/codegenie/probes/base.py` — frozen `Probe` ABC; `ProbeContext` (`workspace`, `logger`).
- **Existing code:** `src/codegenie/errors.py` — `SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError` — reused for the per-file caps.
- **External docs:** `tree-sitter-python` grammar node types — `import_statement`, `import_from_statement`, `dotted_name` — the node kinds the walk queries.

## Goal
Land `PythonImportGraphProbe` — a Layer B `task_specific` probe that walks Python `import` statements via tree-sitter under hard caps to produce a module-to-module edge set.

## Acceptance criteria
- [ ] A red test asserts the probe produces import edges from a multi-file fixture where `a.py` does `import b` / `from b import x` — the slice records the `a → b` edge; it fails before the probe exists.
- [ ] `PythonImportGraphProbe` declares `layer="B"`, `tier="task_specific"`, `applies_to_languages=["python"]`, the frozen two-arg `run(self, repo, ctx)`, and tight `declared_inputs` (`**/*.py`).
- [ ] Parsing is via `language_for("python")` (tree-sitter); each file is byte-capped *before* parse; an oversized `*.py` file is skipped with a structured warning and the probe continues, never crashes.
- [ ] A `*.py` file with a syntax error is handled gracefully — the file is dropped from the graph with an honest signal, the probe never crashes on a malformed file.
- [ ] The OQ3 scope is decided and documented in the module docstring: minimal `import`/`from ... import` edge extraction (no `sys.path` / namespace-package resolution); a relative import (`from . import x`) is recorded with the available signal, not silently dropped.
- [ ] The probe is `@register_probe`-decorated and added to `codegenie/probes/__init__.py` with one import line; `_WARNING_IDS` is validated at import; `tests/unit/test_probe_contract.py` + `tests/fence/` stay green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on touched files; Status set to `Done`.

## Implementation outline
1. Create `src/codegenie/probes/python/import_graph.py`.
2. Implement `PythonImportGraphProbe(Probe)` — pure helpers for the tree-sitter `import`-statement walk; `run()` iterates `*.py` files, byte-caps each, parses with `language_for("python")`, and queries `import_statement` / `import_from_statement` nodes.
3. Build a module-to-module edge set keyed by repo-relative module path; emit it as the `schema_slice`.
4. Decide OQ3: minimal extraction — record raw `import` targets and `from ... import` module names, no `sys.path` resolution; document the decision in the docstring.
5. On an oversized or syntax-broken file, skip it with a `_WARNING_IDS` entry and continue — the probe is resilient per-file.
6. Declare `_WARNING_IDS`, `@register_probe`, add the import line.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/probes/python/test_python_import_graph_probe.py`.
Test name: `test_python_import_graph_probe_records_cross_file_edges`.
```python
async def test_python_import_graph_probe_records_cross_file_edges(tmp_path) -> None:
    # arrange: a RepoSnapshot with a.py = "import b\nfrom b import helper" and b.py = "def helper(): ...".
    # act: await PythonImportGraphProbe().run(repo, ctx).
    # assert: the slice's edge set contains an edge from module "a" to module "b";
    #         layer == "B"; the probe did not raise.
```
Also `test_python_import_graph_probe_skips_syntax_broken_file` — a `*.py` with invalid syntax is dropped with a warning, the probe still returns. Both fail today.

### Green — make it pass
Smallest probe: a Layer B `task_specific` `Probe` whose `run` byte-caps and tree-sitter-parses each `*.py`, walks `import_statement`/`import_from_statement` nodes, and emits the edge set. Minimal scope per OQ3 — no path resolution.

### Refactor — clean up
Extract the tree-sitter import-node walk into a pure helper. Add type hints, a docstring tracing ADR-0007 and stating the OQ3 minimal-scope decision, and confirm per-file resilience (one broken file does not abort the probe).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/probes/python/import_graph.py` | `PythonImportGraphProbe` implementation. |
| `src/codegenie/probes/__init__.py` | One additive import line registering the probe. |
| `tests/unit/probes/python/test_python_import_graph_probe.py` | The red test + syntax-broken-file resilience case. |

## Out of scope
- The tree-sitter search *adapters* (`ImportGraphAdapter` etc.) that consume this probe's output — S6-01.
- `sys.path` / namespace-package / dynamic-import resolution — explicitly out (OQ3 decision: minimal scope; the phase proves the axis, not Python parity).
- Dep-graph (package-level) resolution — that is Step 5's `requirements.txt`/lockfile strategies, a different graph.
- The Python import-graph sub-schema — S4-08.

## Notes for the implementer
- OQ3 is decided **here**: keep the probe minimal — `import` / `from ... import` edge extraction only, no `sys.path` or namespace-package resolution. Document the decision in the docstring so a future reader knows it was deliberate, not an omission.
- Each `*.py` file is byte-capped **before** the tree-sitter parse — a single 200 MB generated file must not OOM the probe (ADR-0007 caps-before-parse).
- Per-file resilience matters: one syntax-broken file is dropped with an honest warning, the probe continues over the rest — never abort the whole probe on one bad file.
- This probe's edge-set slice shape is the contract S6-01's `ImportGraphAdapter` consumes and S4-08's sub-schema pins — keep it deliberate and stable.
- A relative import (`from . import x`) carries less resolution signal than an absolute one — record what is available with the honest confidence, do not silently drop it.
- `tier="task_specific"` + `applies_to_languages=["python"]` keeps the probe (and its `language_for("python")` call) off a Node-only gather — load-bearing for the G11 `sys.modules` fence.
