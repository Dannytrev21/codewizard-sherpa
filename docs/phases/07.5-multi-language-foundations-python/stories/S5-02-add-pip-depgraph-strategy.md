# Story S5-02 — Add the pip dep-graph strategy

**Step:** Step 5 — Build the Python dep-graph strategies (pip / poetry / uv)
**Status:** Ready
**Effort:** M
**Depends on:** S5-01, S2-03
**ADRs honored:** ADR-0008, ADR-0009

## Context
The pip dep-graph strategy turns a `requirements.txt` into a `networkx.DiGraph` of dependency edges using *only* the S5-01 classifier — never resolving, never fetching, never spawning a process. ADR-0008 makes determinism a structural property: a function that does not fetch cannot return a different answer because the package index changed. This is the first of the three Step-5 strategies and the precedent S5-03/S5-04 mirror.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Python dep-graph strategies (pip / poetry / uv)` — `DepGraphStrategy` callable alias, `@register_dep_graph_strategy("pip")`, "no package-manager binary invoked; no network touched", near-empty graph with `confidence="low"` for VCS-only repos.
- **Architecture:** `../phase-arch-design.md §Control flow` decision point 6 — pinned dependency → graph edge; `-e`/`git+`/`--index-url`/out-of-tree `-r`/unknown → an `UnresolvedDependency`/`IndexOverride` fact.
- **Architecture:** `../phase-arch-design.md §Edge cases` row 7 — `-r ../../../etc/passwd` recorded `out_of_tree_include`, the include not followed.
- **Phase ADRs:** `../ADRs/0008-python-depgraph-pure-parsing-no-resolution.md` — ADR-0008 — three concrete strategies, zero network/subprocess, no generic abstraction.
- **Phase ADRs:** `../ADRs/0009-requirements-txt-directive-language-parsing-contract.md` — ADR-0009 — directive classification, `-r` repo-root containment.
- **Existing code:** `src/codegenie/depgraph/registry.py` — `DepGraphStrategy = Callable[[ProbeContext, list[Mapping[str, Any]]], networkx.DiGraph]`, `register_dep_graph_strategy`, `DepGraphRegistry` duplicate-loud semantics.
- **Existing code:** `src/codegenie/depgraph/python/requirements.py` (S5-01) — the classifier this strategy consumes.
- **Existing code:** `src/codegenie/probes/layer_b/dep_graph.py` — the Node-side `DepGraphProbe` consumer; mirror how a strategy is registered and dispatched.

## Goal
Land `depgraph/python/pip.py` — a pure-parse `DepGraphStrategy` that resolves a `requirements.txt` to a `networkx.DiGraph`, registered via `@register_dep_graph_strategy("pip")`.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and fails before implementation — then green.
- [ ] The strategy satisfies the `DepGraphStrategy` callable signature exactly and is registered via `@register_dep_graph_strategy("pip")`; `default_dep_graph_registry` dispatches `"pip"` to it.
- [ ] A `requirements.txt` of pinned dependencies resolves to a `networkx.DiGraph` with one node/edge per pinned dependency.
- [ ] A `requirements.txt` containing only `git+`/`-e` directives yields a near-empty graph carrying `confidence="low"` and explicit `UnresolvedDependency` reasons — never a crash, never a fetch.
- [ ] A `-r <path>` is followed *only* when the resolved path is inside the repo root; a `-r ../../../etc/passwd` is recorded as `out_of_tree_include` and the include is NOT read.
- [ ] The strategy performs zero network I/O and zero subprocess spawns — verified directly here (a monitor/patch asserts no socket connect, no `subprocess` spawn) ahead of the broader S5-05 corpus.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on touched files; `pytest` green on touched test files; Status set to `Done`.

## Implementation outline
1. Create `src/codegenie/depgraph/python/pip.py`.
2. Implement `build_pip_dep_graph(ctx, manifests) -> networkx.DiGraph` (or the exact `DepGraphStrategy` shape) — read the `requirements.txt` text from the manifests/ctx, split into lines, classify each via `classify_requirements_directive`.
3. For each `PinnedDependency`: add a node + edge to the `DiGraph`. For each `UnresolvedDependency`/`IndexOverride`: attach as a graph-level attribute / unresolved-facts list — never act on it.
4. For `-r <path>`: resolve relative to the repo root; if `Path.resolve()` escapes the repo root → record `out_of_tree_include` and skip; else recurse into the included file (bounded — guard against include cycles and a depth cap).
5. Decorate the strategy with `@register_dep_graph_strategy("pip")`; export it; add the `+1` import line in `depgraph/python/__init__.py` so registration fires.
6. Set the graph's `confidence` (or the strategy's output) to `"low"` when the graph is near-empty and unresolved facts dominate; `"high"` for a fully-pinned file.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/depgraph/python/test_pip_strategy.py`.
Test name: `test_pinned_requirements_resolve_to_digraph`.
```python
def test_pinned_requirements_resolve_to_digraph(tmp_path: Path) -> None:
    # arrange: a requirements.txt with two pinned dependencies.
    (tmp_path / "requirements.txt").write_text("flask==2.0.1\nrequests==2.28.0\n")
    # act: dispatch via the registered "pip" strategy.
    graph = default_dep_graph_registry.dispatch("pip", _ctx_for(tmp_path), _manifests(tmp_path))
    # assert: a real DiGraph with a node per pinned dependency — the strategy
    #         resolved from the lockfile bytes, not from the index.
    assert isinstance(graph, networkx.DiGraph)
    assert {"flask", "requests"} <= set(graph.nodes)
```
Also red before impl: `test_out_of_tree_include_not_followed` (`-r ../../../etc/passwd` → `out_of_tree_include` fact, the file unread), `test_vcs_only_requirements_yields_low_confidence_near_empty_graph`, `test_pip_strategy_makes_zero_network_calls` (patch `socket.socket.connect` to raise, assert the strategy completes). Each fails with `DepGraphRegistryError`/`KeyError` (no `"pip"` registered) before impl.

### Green — make it pass
Implement `pip.py` consuming the S5-01 classifier; build the `DiGraph`; register via the decorator. Smallest shape — line-by-line classify, `graph.add_edge` per pinned dep, unresolved facts onto `graph.graph[...]`. `-r` containment via `Path.resolve()` prefix check against the repo root.

### Refactor — clean up
Extract a pure `requirements_to_graph(lines, repo_root) -> ...` helper (functional core) so `run()`-style I/O is the thin shell; add docstrings citing ADR-0008/0009; guard `-r` recursion against cycles; ensure the only `import`s are stdlib + `networkx` + the S5-01 classifier — no `urllib.request`, `requests`, `http`, `socket`, `subprocess`.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/depgraph/python/pip.py` | The pip `DepGraphStrategy`, registered for `"pip"`. |
| `src/codegenie/depgraph/python/__init__.py` | `+1` import line so the `@register_dep_graph_strategy("pip")` decorator fires. |
| `tests/unit/depgraph/python/test_pip_strategy.py` | The pip-strategy unit tests. |

## Out of scope
- The poetry / uv strategies — S5-03 / S5-04.
- The full adversarial `requirements.txt` corpus + system-wide egress monitors — S5-05.
- The `tests/fence/test_depgraph_purity.py` AST fence — S5-06.
- Surfacing the `DiGraph` into `RepoContext` slices / the dep-graph sub-schema — owned by the Python probe sub-schema work (S4-08) and the plugin path (Step 6).

## Notes for the implementer
- ADR-0008 forbids resolution outright — never call `pip`, never fetch from an index, never spawn a process. If you find yourself wanting transitive deps you cannot get from the file, that absence is the *honest* answer (`confidence="low"`), not a bug to fix with a resolver.
- The `-r` containment check must use `Path.resolve()` (which collapses `..`) and compare against the *resolved* repo root — a string-prefix check on the raw path is bypassable.
- `confidence="low"` for a near-empty VCS-only graph is honest under-confidence, not a failure (Edge case / ADR-0008 consequences) — do not treat it as an error path.
- Keep the pure core (`requirements_to_graph`) separate from the file-reading shell — S5-06's purity fence and the functional-core/imperative-shell convention both depend on this split.
- Guard `-r` include recursion against cycles and apply a depth cap — a `requirements.txt` that `-r`s itself must not hang.
- The `DepGraphStrategy` alias is `Callable[[ProbeContext, list[Mapping[str, Any]]], networkx.DiGraph]` — match it exactly; a signature drift is a `mypy` error at the `register` call site.
