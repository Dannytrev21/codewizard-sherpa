# Story S6-03 — Wire `contributes.adapters` and tuple resolution

**Step:** Step 6 — Build the Python search adapter and the `vulnerability-remediation--python--pip` plugin
**Status:** Ready
**Effort:** S
**Depends on:** S6-02 (the scaffolded plugin + validating `plugin.yaml`)
**ADRs honored:** production ADR-0032, production ADR-0031, ADR-0011

## Context
A plugin does not just *use* the generic query primitives — it *provides* the implementation that makes them work for its language slice (ADR-0032). With the Python adapters (S6-01) and the plugin scaffold (S6-02) in place, this story wires the adapters into the manifest's `contributes.adapters` map and proves the `(vuln, python, pip)` scope tuple resolves to the plugin and its adapters import cleanly — the fast-fail-at-load check ADR-0031 mandates.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — Python search adapter` (line 484) — adapters "registered through the `vulnerability-remediation--python--pip` plugin manifest's `contributes.adapters` map (the existing mechanism, unchanged)."
- **Architecture:** `../phase-arch-design.md §Logical view` (line 89) — `PYPL -.->|"contributes.adapters"| PYA` — the plugin contributes the adapter via the manifest.
- **Phase ADRs:** `../ADRs/0011-python-search-adapter-tree-sitter-first-scip-deferred.md` — ADR-0011 — Python's tree-sitter adapter registered through the existing plugin `contributes.adapters` mechanism, unchanged.
- **Production ADRs:** `../../../production/adrs/0032-language-search-adapters.md §Plugin manifest registration` + `§Dispatch` — `contributes.adapters` maps each primitive (`dep_graph`/`import_graph`/`test_inventory`) to a `module:ClassName` path; the Bundle Builder imports each entry on plugin load and a fast-fail check resolves the import paths.
- **Production ADRs:** `../../../production/adrs/0031-plugin-architecture.md §Resolution` — most-specific match wins; the resolver matches the workflow's `(task, language, build)` tuple against plugin `scope`.
- **Existing code:** `src/codegenie/plugins/manifest.py` — `ManifestContributes.adapters: dict[PrimitiveName, str]` — the `module:Class` value strings (shape-validated by Pydantic; the grammar parse / import is the resolver's concern).
- **Existing code:** `plugins/vulnerability-remediation--python--pip/adapters/python_tree_sitter.py` (S6-01) — the adapter classes whose `module:ClassName` paths the manifest references.
- **Existing code:** `plugins/vulnerability-remediation--python--pip/plugin.yaml` (S6-02) — the manifest this story extends with `contributes.adapters`.

## Goal
Wire the three Python adapters into the plugin manifest's `contributes.adapters` map and prove the `(vuln, python, pip)` tuple resolves to the plugin with all adapter import paths resolving cleanly.

## Acceptance criteria
- [ ] The TDD red test asserting `(vuln, python, pip)` tuple resolution + adapter-import resolution exists, is committed, and starts failing.
- [ ] `plugin.yaml`'s `contributes.adapters` maps `import_graph`, `dep_graph`, and `test_inventory` to the `module:ClassName` paths of the S6-01 adapters.
- [ ] Every `contributes.adapters` `module:ClassName` path imports and the named class exists (the ADR-0031 fast-fail-at-load check passes).
- [ ] Resolving the `(vulnerability-remediation, python, pip)` scope tuple selects the `vulnerability-remediation--python--pip` plugin (most-specific match).
- [ ] An unresolvable-adapter-path negative test confirms a broken `module:Class` entry fails fast with a diagnostic naming the file/field (the resolver has teeth).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on touched files.

## Implementation outline
1. Extend `plugin.yaml`'s `contributes.adapters` with `import_graph`, `dep_graph`, `test_inventory` → the dotted `module:ClassName` paths of the S6-01 adapter classes.
2. Resolve each adapter path (import the module, getattr the class) — confirm they resolve; the manifest's Pydantic shape-check plus the resolver's import-check together gate it.
3. Add the resolution test: build a `(vuln, python, pip)` query and assert the resolver returns the Python pip plugin.
4. Add an `api.py` side-effect import line if the plugin loader needs the adapters imported for registration (mirror Phase 7 `S3-03`/`S8-03` wiring) — keep it one additive line.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/integration/plugins/test_python_pip_adapter_resolution.py`.
Test name: `test_vuln_python_pip_tuple_resolves_plugin_and_adapters_import` — asserts the tuple resolves and every `contributes.adapters` path imports.
```python
# arrange: load plugins/vulnerability-remediation--python--pip via PluginManifest.from_yaml
# act:    resolve the (vulnerability-remediation, python, pip) scope tuple;
#         import each contributes.adapters module:Class entry
# assert: resolved plugin id == "vulnerability-remediation--python--pip"
#         for each (primitive, path): import succeeds and the class exists
#         "import_graph" in manifest.contributes.adapters   # mandatory adapter wired
```
Must fail because `contributes.adapters` is empty/minimal after S6-02.

### Green — make it pass
Populate `contributes.adapters` with the three primitive→path entries; ensure each path resolves to a real class from S6-01. Add the side-effect import line if the loader needs it. The smallest wiring that makes the tuple resolve and the paths import.

### Refactor — clean up
Add the unresolvable-adapter-path negative test (a deliberately broken `module:Class` → fast-fail with a clear diagnostic). Confirm the resolver picks the most-specific plugin over any wildcard base. Docstring the manifest entries against ADR-0032's `contributes.adapters` contract.

## Files to touch
| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--python--pip/plugin.yaml` | Extend `contributes.adapters` with the three primitive→`module:Class` entries. |
| `plugins/vulnerability-remediation--python--pip/api.py` | New (if loader requires) — one additive side-effect import line for adapter registration. |
| `tests/integration/plugins/test_python_pip_adapter_resolution.py` | New — the red test (tuple resolution + adapter import) + the unresolvable-path negative test. |

## Out of scope
- The integration diff test producing a real diff on a vulnerable fixture — S6-04.
- `PYTHON_PACK` construction / `register_language` and the `search_adapter_module` field wiring — S7-01.
- The conformance-tier `test_search_adapter_is_not_a_stub` assertion — S7-02.
- Polyglot-repo dispatch (which adapter answers a query for a Node+Python repo) — ADR-0032 / Phase-8-Planner territory.

## Notes for the implementer
- **`contributes.adapters` keys are primitive names, not adapter class names.** Per ADR-0032 the map is `{import_graph: ..., dep_graph: ..., test_inventory: ...}` — the keys are the generic primitive interfaces.
- **`import_graph` is mandatory.** ADR-0032 §Consequences sets the minimum adapter surface as `ImportGraphAdapter` + `TestInventoryAdapter`; `DepGraphAdapter` is required because the task class (vuln) touches dependencies. Wire all three.
- **Fast-fail-at-load is the contract.** ADR-0031 says a broken adapter import path must surface *at plugin load*, never at workflow time — the negative test must confirm this loud failure.
- **Do not edit the manifest schema.** `ManifestContributes.adapters` already exists. The `module:Class` paths are shape-checked by Pydantic; the import resolution is the resolver's job — both must agree.
- **Keep `api.py` to one import line if needed.** Mirror Phase 7 `S3-03`'s `from .adapters import ...  # noqa: F401` side-effect pattern — additive, no logic.
- **`search_adapter_module` vs `contributes.adapters`.** The `LanguagePack.search_adapter_module` field (a single `module:ClassName` string) is the language-axis pointer; `contributes.adapters` is the plugin-axis map. S7-01 wires the former; this story wires the latter. Keep them consistent — both should point at the S6-01 module.
