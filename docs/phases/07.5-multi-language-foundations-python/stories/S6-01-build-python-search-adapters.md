# Story S6-01 — Build the tree-sitter Python search adapters

**Step:** Step 6 — Build the Python search adapter and the `vulnerability-remediation--python--pip` plugin
**Status:** Ready
**Effort:** M
**Depends on:** S4-07 (the `PythonImportGraphProbe` whose facts the adapters read)
**ADRs honored:** ADR-0011, production ADR-0032

## Context
ADR-0032 defines language search adapters as the bridge from generic context queries (`import_graph.reverse_lookup`, `dep_graph.consumers`, `test_inventory.tests_exercising`) to language-specific implementations. Phase 7.5 must implement these Protocols for Python so the `vulnerability-remediation--python--pip` plugin can answer real queries. Per ADR-0011 the adapters are **tree-sitter-backed** — always-fresh, in-process, no external binary — with `scip-python` deliberately deferred to a fast-follow that would need its own `ALLOWED_BINARIES` amendment.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — Python search adapter (tree-sitter-first; scip-python deferred)` (lines 481-489) — the public interface (`ImportGraphAdapter` mandatory, `DepGraphAdapter`, `TestInventoryAdapter`), `confidence()` is the ADR-0032-as-written `-> float`, no invented amendment.
- **Architecture:** `../phase-arch-design.md §Logical view` (line 166) — `Probe` and `DepGraphStrategy` reused unchanged; adapters consume probe output, do not change probe contract.
- **Phase ADRs:** `../ADRs/0011-python-search-adapter-tree-sitter-first-scip-deferred.md` — ADR-0011 — tree-sitter-first; `scip-python`/`ScipAdapter` deferred; `confidence() -> float` stays as ADR-0032 specifies; `ALLOWED_BINARIES` untouched.
- **Production ADRs:** `../../../production/adrs/0032-language-search-adapters.md` — the adapter `Protocol`s as written (`ImportGraphAdapter.reverse_lookup`, `.transitive_callers`, `DepGraphAdapter.consumers`, `TestInventoryAdapter.tests_exercising`; `confidence() -> float` mandatory across all).
- **Source design:** `../final-design.md §Synthesis ledger row CR-6` — the tree-sitter-vs-SCIP conflict resolution.
- **Existing code:** `src/codegenie/adapters/protocols.py` — the Phase-2 `@runtime_checkable` adapter Protocols. **Conflict to surface (see Notes):** these declare `confidence() -> AdapterConfidence` (a sum type), but ADR-0011/ADR-0032 mandate `-> float`. Do not edit the Phase-2 file; implement the ADR-0011-as-written `-> float` surface in the new Python adapter module and flag the divergence.
- **Existing code:** `src/codegenie/probes/python/import_graph.py` (S4-07) — the `PythonImportGraphProbe` whose tree-sitter `import`-statement facts the `ImportGraphAdapter` reads.
- **Existing code:** `src/codegenie/grammars/lock.py` — `language_for("python")` lazily loads the `tree-sitter-python` grammar (wired in S4-01).

## Goal
Land a tree-sitter-backed `ImportGraphAdapter`, `DepGraphAdapter`, and `TestInventoryAdapter` for Python, each with a `confidence() -> float` method per ADR-0032-as-written, that translate generic query primitives into Python-specific tree-sitter walks over gathered facts.

## Acceptance criteria
- [ ] The TDD red test for the adapter surface exists, is committed, and starts failing for the right reason (no adapter module yet).
- [ ] An `ImportGraphAdapter` is implemented (mandatory per ADR-0032) — `reverse_lookup(module)` returns every Python file importing `module`; `transitive_callers(file_set, depth)` walks `depth` hops; `confidence() -> float`.
- [ ] A `DepGraphAdapter` (`consumers`/`producers`) and a `TestInventoryAdapter` (`tests_exercising`) are implemented, each with `confidence() -> float`.
- [ ] Every adapter's `confidence()` returns a `float` — **not** a sum type; no "ADR-0033 amendment" is invented (ADR-0011).
- [ ] The adapters are translators not stubs — against a multi-file fixture with ≥ 1 cross-file import, `reverse_lookup` returns a non-empty, non-degenerate result.
- [ ] No new entry is added to `ALLOWED_BINARIES`; the closed-set is untouched (ADR-0011, G8) — assert it in a test.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on the new adapter module and tests; the `fence` job stays green (no `FORBIDDEN_LLM_SDK` rode in).

## Implementation outline
1. Decide the adapter module home: a new `python_tree_sitter.py` that will live under the plugin tree (`plugins/vulnerability-remediation--python--pip/adapters/`, created in S6-02) — for S6-01 land it in a location S6-02 wires; the architecture diagram (line 245) places it at `adapters/python_tree_sitter.py`.
2. Implement `PythonImportGraphAdapter` — backed by tree-sitter `import` / `from ... import` statement walks (reusing `language_for("python")` and the `PythonImportGraphProbe` fact shape). `reverse_lookup` and `transitive_callers` translate module names to file paths.
3. Implement `PythonDepGraphAdapter` over the dep-graph facts and `PythonTestInventoryAdapter` over the test-inventory facts (kept minimal — the phase proves the axis, not Python parity).
4. Give each adapter a `confidence() -> float` reflecting freshness of the underlying gathered facts.
5. Keep the adapter pure-translation: no I/O at construction, no external binary, no subprocess.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/adapters/python/test_python_search_adapters.py`.
Test name: `test_python_import_graph_adapter_reverse_lookup_resolves_cross_file_import` — asserts that against a two-file fixture where `b.py` does `import a`, the `PythonImportGraphAdapter.reverse_lookup("a")` returns a list containing `b.py`.
```python
# arrange: a tree-sitter-parsed fixture with a.py and b.py (b imports a)
# act:    adapter = PythonImportGraphAdapter(...); result = adapter.reverse_lookup("a")
# assert: "b.py" in result            # not a stub: a real cross-file edge resolved
#         isinstance(adapter.confidence(), float)   # ADR-0032-as-written -> float
```
Must fail at import/collection because the adapter module does not exist yet.
A second red test `test_confidence_returns_float_not_sum_type` asserts `type(adapter.confidence()) is float` for all three adapters — the teeth against drifting back to a sum type.

### Green — make it pass
Land the adapter module with the three adapter classes. `PythonImportGraphAdapter` parses Python files via `language_for("python")`, collects `import`/`import-from` nodes, and builds the module→files index `reverse_lookup` reads. `DepGraphAdapter`/`TestInventoryAdapter` translate the corresponding gathered facts. Each `confidence()` returns a plain `float`. Minimum surface — no SCIP, no extra Protocols.

### Refactor — clean up
Extract a pure tree-sitter import-extraction helper (functional core); keep `__init__`/query methods the only stateful surface. Add docstrings citing ADR-0032 primitive names and ADR-0011's tree-sitter-first decision. Add the `ALLOWED_BINARIES` closed-set regression assertion. Confirm `mypy --strict` sees `confidence` typed `-> float`.

## Files to touch
| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--python--pip/adapters/python_tree_sitter.py` | New — the three tree-sitter-backed Python adapters (`ImportGraph`/`DepGraph`/`TestInventory`). |
| `plugins/vulnerability-remediation--python--pip/adapters/__init__.py` | New — package marker for the adapters sub-package. |
| `tests/unit/adapters/python/test_python_search_adapters.py` | New — the red tests + the `confidence -> float` teeth + the `ALLOWED_BINARIES` closed-set assertion. |

## Out of scope
- The `scip-python` `ScipAdapter` and any `ALLOWED_BINARIES` amendment — deferred fast-follow (ADR-0011; sequencing is OQ4, left to a later closeout/Phase-8 story).
- The `plugin.yaml` manifest and `contributes.adapters` wiring — S6-02 / S6-03.
- The integration diff test against a vulnerable fixture — S6-04.
- Polyglot-repo adapter dispatch (which adapter answers which query for a Node+Python repo) — ADR-0032 / Phase-8-Planner territory.

## Notes for the implementer
- **`confidence()` return-type conflict (surface it, do not blend).** `src/codegenie/adapters/protocols.py` declares `confidence() -> AdapterConfidence` (a Phase-2 sum type); ADR-0011 and ADR-0032-as-written mandate `-> float`. Per Rule 7, do not average: implement the Python adapters to ADR-0011's `-> float` (the governing phase ADR for this work) and flag the Phase-2 sum-type Protocol as a separate cleanup. Do not silently edit the Phase-2 file.
- **The stub trap.** A stub adapter passes `mypy` and a naive test. The red test must use a fixture with a real cross-file import so a stub returning `[]` fails — this carries into S7-04's fixture-shape meta-test (≥ 1 cross-file ref).
- **`ALLOWED_BINARIES` untouched is a hard goal (G8).** No `scip-python`, no `pip`/`poetry`/`uv` — the adapter is tree-sitter-in-process only. Land the closed-set regression assertion here so the goal has teeth.
- **Adapter = translator, not forwarder.** Per ADR-0032 §Pattern fit, the adapter *translates* generic primitives into Python tree-sitter walks; it is not a thin pass-through to a probe.
- **No I/O at construction.** The adapter consumes already-gathered facts; do not parse the repo in `__init__`.
- **Keep the import-graph depth a scoping call (OQ3).** Whether `transitive_callers` covers `sys.path`/namespace-package resolution is an implementation-time decision — minimal is acceptable; the phase proves the axis, not Python feature-parity.
