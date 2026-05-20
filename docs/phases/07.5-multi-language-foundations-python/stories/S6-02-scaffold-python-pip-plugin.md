# Story S6-02 — Scaffold the `vulnerability-remediation--python--pip` plugin

**Step:** Step 6 — Build the Python search adapter and the `vulnerability-remediation--python--pip` plugin
**Status:** Ready
**Effort:** S
**Depends on:** S6-01 (the Python adapters the plugin will wire)
**ADRs honored:** production ADR-0031, production ADR-0032, ADR-0011

## Context
ADR-0031 makes a plugin the bundle for a `(task × language × build-tool)` slice — here `(vulnerability-remediation, python, pip)`. The plugin lives at `plugins/vulnerability-remediation--python--pip/` and `extends` the universal `vulnerability-remediation--*--*` base, inheriting the orchestration shell so Python only contributes what is genuinely language-specific. This story lands the plugin directory skeleton and a `plugin.yaml` that validates against the existing `PluginManifest` Pydantic schema.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Goals — G10` (line 29) — the plugin lives at `plugins/vulnerability-remediation--python--pip/`, `extends` the universal base.
- **Architecture:** `../phase-arch-design.md §Development view` (lines 242-245) — `PYPLUG → plugin.yaml (contributes.adapters)` + `adapters/python_tree_sitter.py`.
- **Phase ADRs:** `../ADRs/0011-python-search-adapter-tree-sitter-first-scip-deferred.md` — ADR-0011 — adapters registered through the plugin `contributes.adapters` mechanism, unchanged.
- **Production ADRs:** `../../../production/adrs/0031-plugin-architecture.md` — ADR-0031 — plugin directory layout (`plugin.yaml`, `tccm.yaml`, `subgraph/`, `adapters/`, `recipes/`), `extends` list semantics (later-in-list wins), `plugin.yaml` validated against Pydantic at load.
- **Production ADRs:** `../../../production/adrs/0032-language-search-adapters.md` — ADR-0032 — `contributes.adapters` maps each primitive to a `module:ClassName` import path.
- **Existing code:** `src/codegenie/plugins/manifest.py` — `PluginManifest` / `ManifestScope` / `ManifestContributes` / `ManifestRequirements` Pydantic models + `PluginManifest.from_yaml(path) -> Result[...]`; the manifest schema the new `plugin.yaml` must validate against unchanged.
- **Existing code:** `plugins/` — the repo plugin root (currently `PLUGINS.lock`, `__init__.py`); Phase 7's `distroless-migration--node--npm` story `S8-01` is the manifest precedent to mirror.

## Goal
Land the `plugins/vulnerability-remediation--python--pip/` directory with a `plugin.yaml` that `extends` the universal vulnerability-remediation base and validates clean through `PluginManifest.from_yaml`.

## Acceptance criteria
- [ ] The TDD red test loading `plugins/vulnerability-remediation--python--pip/plugin.yaml` via `PluginManifest.from_yaml` exists, is committed, and starts failing (no manifest yet).
- [ ] `plugin.yaml` declares `name: vulnerability-remediation--python--pip`, `scope: {task: vulnerability-remediation, language: python, build: pip}`, and `extends` the universal `vulnerability-remediation--*--*` base.
- [ ] `PluginManifest.from_yaml` returns an `Ok` — the manifest validates (no unknown fields, all types correct, `extends` entries lift through `parse_plugin_id`).
- [ ] The `extends` chain resolves to the universal base (the parent plugin id is a real, resolvable entry).
- [ ] A malformed-manifest negative test confirms `from_yaml` returns an `Err` naming the offending field (the schema has teeth).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on touched files; the plugin directory follows the ADR-0031 layout.

## Implementation outline
1. Create the plugin directory `plugins/vulnerability-remediation--python--pip/` with the ADR-0031 layout (`plugin.yaml`, `adapters/` — already seeded by S6-01).
2. Author `plugin.yaml`: `name`, `version`, `scope` (the `(vuln, python, pip)` tuple), `extends: [vulnerability-remediation--*--*]`, `contributes` (left minimal here — `adapters` wiring is S6-03), `requirements` (`external_tools: []` — tree-sitter-first, no binary per ADR-0011).
3. Verify `PluginManifest.from_yaml` accepts it; verify the `extends` parent id is the resolvable universal base.
4. Keep `contributes.adapters` empty/minimal at this step — S6-03 fills it.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/plugins/test_python_pip_plugin_manifest.py`.
Test name: `test_python_pip_plugin_yaml_validates_and_extends_universal_base` — asserts the manifest loads to `Ok` and `extends` includes the universal base.
```python
# arrange: path to plugins/vulnerability-remediation--python--pip/plugin.yaml
# act:    result = PluginManifest.from_yaml(path)
# assert: isinstance(result, Ok)
#         manifest = result.value
#         manifest.scope == ...vulnerability-remediation/python/pip...
#         any base id in manifest.extends matches vulnerability-remediation--*--*
```
Must fail because `plugin.yaml` does not exist (`from_yaml` returns an `IoError` `Err`).

### Green — make it pass
Create the directory and author a minimal valid `plugin.yaml` matching the `PluginManifest` schema fields (`name`, `version`, `scope`, `extends`, `precedence` default, `contributes`, `requirements`). The smallest manifest that validates and carries the correct scope + `extends`.

### Refactor — clean up
Add a malformed-manifest negative test (e.g. unknown field → `SchemaViolation` `Err` naming the field). Confirm the directory layout matches ADR-0031. Keep `contributes` minimal — note in a comment that adapter wiring lands in S6-03.

## Files to touch
| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--python--pip/plugin.yaml` | New — the plugin manifest (`scope`, `extends`, `contributes`, `requirements`). |
| `tests/unit/plugins/test_python_pip_plugin_manifest.py` | New — the red test (`from_yaml` → `Ok`, `extends` resolves) + the malformed-manifest negative test. |

## Out of scope
- Wiring `contributes.adapters` to the Python adapters and proving tuple resolution — S6-03.
- The integration diff test on a vulnerable fixture — S6-04.
- The `tccm.yaml`, `subgraph/`, `recipes/`, `skills/` plugin contents — bundled per ADR-0031 but only the parts needed for the `(vuln, python, pip)` diff are in 7.5 scope; flesh them out as S6-03/S6-04 demand.
- `PLUGINS.lock` entry + CODEOWNERS gating — follow the Phase 7 `S5-04` mechanism if required by `make check`; otherwise defer to S8-02 phase-gate close.

## Notes for the implementer
- **Reuse the manifest schema unchanged.** `PluginManifest` already supports `extends`, `scope`, `contributes.adapters` — do not edit `src/codegenie/plugins/manifest.py`. If a field genuinely does not fit, that is an ADR-0031 amendment, not a silent extension.
- **`extends` is a list and entries lift through `parse_plugin_id`.** A typo in the universal-base id surfaces as a `SchemaViolation` `Err` naming `extends[i]` — let the schema catch it; do not pre-validate by hand.
- **`requirements.external_tools` stays empty.** Tree-sitter-first (ADR-0011) means no binary requirement — declaring one would imply an `ALLOWED_BINARIES` need that does not exist.
- **The universal base must exist.** ADR-0031 puts the universal `vulnerability-remediation--*--*` base in-tree. If it is absent, this story is blocked the way Phase 7 `S3-02` was blocked on the npm plugin directory — surface that loudly in the attempt log rather than papering over with a stub parent.
- **Mirror the Phase 7 precedent.** `docs/phases/07-migration-task-class/stories/S8-01-distroless-migration-plugin-manifest.md` is the closest manifest story — same `from_yaml`-validates discipline, no schema edits.
