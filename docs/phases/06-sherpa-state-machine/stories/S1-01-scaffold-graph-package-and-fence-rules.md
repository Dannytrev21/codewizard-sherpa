# Story S1-01 — Scaffold `graph/` package skeleton + fence-CI rules

**Step:** Step 1 — Scaffold `graph/` package, ship `VulnLedger` + HITL contracts + structural CI gates
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0002, ADR-0012

## Context
This is the foundation story for Phase 6: create the empty Python package tree that every later Step 1–10 story will populate, and extend the existing `tools/fence_ci.yaml` policy with the four banned-import rules that protect the `graph/` boundary. Nothing here ships behavior — but every fence rule landed here catches an ADR-0002 / ADR-0012 violation at PR time instead of runtime, so this story is the structural floor for the rest of the phase.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Development view — code organization` — the full directory tree the package must match (lines 251–310).
  - `../phase-arch-design.md §Development view — Fence-CI updates` (lines 304–309) — the four exact fence rules to add.
  - `../phase-arch-design.md §Testing strategy — CI gates` (lines 1196–1207) — what static gates this story underwrites.
- **Phase ADRs:**
  - `../ADRs/0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md` — ADR-0002 — the package is the home of the runtime hook the ADR requires.
  - `../ADRs/0012-pure-edge-discipline-tests-over-acl-machinery.md` — ADR-0012 — fence rule on `graph/edges.py` (no `random|time|os|datetime` imports) is structurally required by this ADR.
- **High-level-impl:**
  - `../High-level-impl.md §Step 1 — Features delivered` — first three bullets enumerate every file that must exist.
- **Existing code:**
  - `tools/fence_ci.yaml` — extend it; do not rewrite. Phase 0's fence loader is the existing mechanism.
  - `src/codegenie/` — discover the actual package root layout; place `graph/` as a sibling of `cli/`, `gates/`, `planner/`.

## Goal
Create the empty `src/codegenie/graph/` package tree (nine files plus two empty subpackages) and extend `tools/fence_ci.yaml` with the four banned-import rules so every subsequent commit in Phase 6 imports cleanly and lints loudly.

## Acceptance criteria
- [ ] `src/codegenie/graph/__init__.py`, `state.py`, `hitl.py`, `events.py`, `hooks.py`, `edges.py`, `vuln_loop.py`, `checkpointer.py` exist as stubs (each with a module docstring naming its Phase 6 owner-story); `nodes/__init__.py` and `migrations/__init__.py` exist as empty files.
- [ ] `tools/fence_ci.yaml` contains four new rules: (1) `graph/**` cannot import `anthropic|chromadb|sentence-transformers`; (2) `graph/edges.py` cannot import `random|time|os|datetime` except the literal `from datetime import fromisoformat`; (3) `graph/nodes/*.py` cannot import any sibling `codegenie.graph.nodes.*`; (4) `graph/**` cannot import `langgraph.types.interrupt` except from `graph/nodes/await_human.py`.
- [ ] `python -c "import codegenie.graph"` succeeds.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `tests/graph/test_fence_graph_no_anthropic.py` proves a synthesized `import anthropic` in a `graph/*.py` fixture file is rejected by the fence runner.
- [ ] `ruff check src/codegenie/graph/`, `ruff format --check src/codegenie/graph/`, `mypy --strict src/codegenie/graph/`, and `pytest tests/graph/ -k "scaffold or fence"` all pass.

## Implementation outline
1. Read `tools/fence_ci.yaml` to learn the existing rule schema and the loader's selector syntax.
2. Create the directory tree under `src/codegenie/graph/` per arch §Development view; each stub file gets only a module docstring and `from __future__ import annotations` if the project uses it.
3. Extend `tools/fence_ci.yaml` with the four rules; group them under a `phase: 6` comment block so future readers see the provenance.
4. Add `tests/graph/__init__.py`, then `tests/graph/test_fence_graph_no_anthropic.py` — invoke the existing fence runner against a synthesized offending file, assert it raises.
5. Run `mypy --strict src/codegenie/graph/` — should be vacuously clean against empty stubs.
6. Add a CI-job stub (if Phase 0's CI matrix requires per-package opt-in) so `graph/` is scanned.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/graph/test_fence_graph_no_anthropic.py`

```python
def test_graph_package_cannot_import_anthropic(tmp_path: Path) -> None:
    # arrange: create a fake graph submodule that violates the fence
    offender = tmp_path / "codegenie" / "graph" / "rogue.py"
    offender.parent.mkdir(parents=True)
    offender.write_text("import anthropic\n")
    # act + assert: the existing fence runner must reject it
    with pytest.raises(FenceViolation) as exc:
        run_fence(rule_set="phase6_graph", roots=[tmp_path])
    assert "anthropic" in str(exc.value)
    assert "graph/rogue.py" in str(exc.value)


def test_graph_edges_cannot_import_time_module() -> None:
    # arrange: real edges.py stub is empty — fence must still parse the rule
    # act + assert: synthesize a violating import via a tmp_path fixture and
    # assert FenceViolation; whitelist `from datetime import fromisoformat`
    # passes.
    ...


def test_graph_nodes_cannot_import_sibling_nodes() -> None:
    # arrange: synthesize graph/nodes/foo.py with `from codegenie.graph.nodes import bar`
    # act + assert: FenceViolation raised with rule id "graph_no_sibling_node_imports"
    ...
```

### Green — make it pass
Create the package stubs and the four fence-yaml entries. The smallest implementation is: directories + nine module-docstring-only files + four YAML rule blocks. No behavior, no imports beyond `__future__`.

### Refactor — clean up
Add module docstrings that name (a) the owning Phase 6 story slug and (b) the ADR(s) the file implements. Confirm `mypy --strict` is silent (no `Any`, no `cast`). Document the fence-rule additions in `tools/fence_ci.yaml` with an inline comment block referencing this story.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/graph/__init__.py` | Package marker; placeholder docstring noting future exports (`build_vuln_loop`, `VulnLedger`, `HumanRequest`, `HumanDecision`). |
| `src/codegenie/graph/state.py` | Stub — owner story S1-02. |
| `src/codegenie/graph/hitl.py` | Stub — owner story S1-03. |
| `src/codegenie/graph/events.py` | Stub — owner story S1-04. |
| `src/codegenie/graph/hooks.py` | Stub — owner story S1-04. |
| `src/codegenie/graph/edges.py` | Stub — owner story S3-01. |
| `src/codegenie/graph/vuln_loop.py` | Stub — owner story S5-01. |
| `src/codegenie/graph/checkpointer.py` | Stub — owner story S2-01. |
| `src/codegenie/graph/nodes/__init__.py` | Empty subpackage marker. |
| `src/codegenie/graph/migrations/__init__.py` | Empty subpackage marker (ADR-0005). |
| `tools/fence_ci.yaml` | Extend with four `phase6_graph` rules. |
| `tests/graph/__init__.py` | Test package marker. |
| `tests/graph/test_fence_graph_no_anthropic.py` | Red test for fence rule (1). |

## Out of scope
- **`VulnLedger` body** — S1-02 fills `state.py`.
- **`HumanRequest`/`HumanDecision` bodies** — S1-03 fills `hitl.py`.
- **`GraphEvent`, exception classes, after-node hook** — S1-04 fills `events.py` + `hooks.py`.
- **Layer-0 introspection tests beyond the fence smoke** — S1-05 lands `test_no_self_confidence_in_loopstate.py`, `test_schema_version_pin.py`, `test_pep_no_O_optimizations.py`.
- **`@pure_edge` decorator** — S3-01.
- **CI workflow file edits** beyond opt-in for the new package path; the perf nightly cron is Step 9.

## Notes for the implementer
- The fence runner's selector syntax must support **path negation** (rule 4 excludes one file from a `graph/**` ban). If it doesn't, surface this loudly — do not silently downgrade the rule. Phase 0's fence loader is the authority; read it before assuming.
- Resist the urge to add real exports to `__init__.py` now. Every premature export creates an import cycle when the owner story lands; leave it as a docstring-only stub.
- The `datetime.fromisoformat` whitelist in rule (2) is **only** for the literal `from datetime import fromisoformat` form. Forbid `import datetime` and `from datetime import datetime`. The arch design at line 307 is the authority — match its wording exactly.
- Run `mypy --strict` on the empty package to flush out any latent project-config issue (e.g., missing `py.typed` marker, missing `mypy.ini` stanza for the new package). Catching this now saves S1-02 from debugging it.
- ADR-0012 is the rationale for fence rule (2) — cite it in the YAML comment block.
- If the project uses `from __future__ import annotations` everywhere else, do the same here for forward-compat with the Pydantic types S1-02 will land.
