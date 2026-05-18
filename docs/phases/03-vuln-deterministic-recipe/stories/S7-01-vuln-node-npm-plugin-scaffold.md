# Story S7-01 — `plugins/vulnerability-remediation--node--npm/` scaffold, manifest, TCCM, registration

**Step:** Step 7 — First production plugin, universal HITL fallback plugin, synthetic third plugin
**Status:** Ready
**Effort:** M
**Depends on:** S6-04 (RemediationOrchestrator + the 5-node subgraph + `_validate_stage6` seam must already exist for the plugin's `build_subgraph` to wire into)
**ADRs honored:** [ADR-0002](../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md) (the plugin registers via `@register_plugin(...)` at module import time; no edits to the kernel), [ADR-0003](../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md) (the concrete plugin's specificity-3 scope `(vulnerability-remediation, node, npm)` makes it the resolver head against the `(*, *, *)` universal), [ADR-0004](../ADRs/0004-plugin-private-capabilities-via-tccm.md) (`provides.vuln_index_capabilities` carries the NVD/GHSA/OSV parser entrypoints — the kernel `Plugin` Protocol stays at four methods), [ADR-0011](../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) (`PLUGINS.lock` is the integrity check populated when this plugin's tree first lands)

## Context

This story lands the **first concrete production plugin** under the `plugins/` directory and is the moment the kernel built in Step 2 (`PluginRegistry`, loader, `PLUGINS.lock` integrity check) first proves it can host a real plugin contributed by addition. The directory naming pattern is **`{task}--{language}--{build}`** — verbatim `plugins/vulnerability-remediation--node--npm/` — and the contract surface is *exactly* the four kernel `Plugin` methods (`manifest`, `build_subgraph`, `adapters`, `transforms`) plus a `tccm.yaml` declaring `must_read`/`should_read`/`may_read` queries and the plugin-private `provides.vuln_index_capabilities` namespace (ADR-0004). The four `adapters/` modules and the four `recipes/` classes are S7-02's surface; this story stops at the scaffold + manifest + TCCM + `@register_plugin(...)` call + `PLUGINS.lock` row, so S7-02 can drop adapters and recipes into a tree the resolver is already happy with.

The plugin's manifest must declare the scope `vulnerability-remediation--node--npm` (parsed by `PluginScope.parse(...)` into three `Concrete` dims — specificity 3), `precedence: 100` (higher than the universal's), and an `extends: []` (no inheritance in Phase 3; depth-4 walk exercised only via the synthetic plugin in S7-04). The `tccm.yaml` declares the queries the BundleBuilder will dispatch against the four ADR-0032 adapters S7-02 ships. The `api.py` declaration calls `@register_plugin(...)` against `default_registry` so that, at plugin loader import time, the resolver can return a `ConcreteResolution` for `(vulnerability-remediation, node, npm)` scopes.

The story is intentionally narrow: **scaffold + contract declaration**, not behavior. Recipes and adapters arrive in S7-02; the synthetic third plugin and the three-plugin bake-test arrive in S7-04. The done test is *the resolver resolves the scope to this concrete plugin*, not *the plugin actually remediates a CVE* — that end-to-end claim is S8-02's.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C2` (the `Plugin` Protocol's four methods: `manifest`, `build_subgraph`, `adapters`, `transforms`).
  - `../phase-arch-design.md §Scenarios D` (loader walks `plugins/*/plugin.yaml`, registers each, the resolver composes TCCM left-to-right).
  - `../phase-arch-design.md §Component design C7` (BundleBuilder reads `composed_tccm` to dispatch `must_read` queries).
  - `../phase-arch-design.md §"Open questions deferred to implementation"` — `provides.vuln_index_capabilities` shape.
- **Phase ADRs:**
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — `@register_plugin(plugin, *, registry=None)` is the only registration mechanism; production code uses `default_registry`.
  - `../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md` — specificity ordering puts this plugin (3-Concrete-dim) above the universal `(*,*,*)` (0-Concrete-dim).
  - `../ADRs/0004-plugin-private-capabilities-via-tccm.md` — task-class-specific NVD/GHSA/OSV parsers live in TCCM `provides`, NOT on a `cve_feed_parsers()` method on the kernel `Plugin`.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — `PLUGINS.lock` is the integrity check; CODEOWNERS gates edits.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — the umbrella manifest shape this story instantiates.
  - `../../../production/adrs/0029-task-class-context-manifests.md` — TCCM `must_read`/`should_read`/`may_read` semantics this story declares against.
  - `../../../production/adrs/0032-language-search-adapters.md` — the four adapter Protocols the `contributes.adapters` map points at (S7-02 implements them).
- **High-level impl:** `../High-level-impl.md §"Step 7"` — features delivered list.
- **Source precedent for the registration shape:** `src/codegenie/plugins/registry.py` (the `default_registry` + `@register_plugin` decorator from S2-01).
- **Source precedent for a probe-shaped explicit-import collection point:** `src/codegenie/probes/__init__.py` — the same explicit-import discipline applies to plugin loader (no entry-point scan).

## Goal

Land `plugins/vulnerability-remediation--node--npm/{plugin.yaml,api.py,tccm.yaml}` plus an empty `recipes/__init__.py` and `adapters/__init__.py` (so S7-02 can drop files in), wire `@register_plugin(...)` into `api.py`, populate `plugins/PLUGINS.lock` with this plugin's tree sha256, and prove that `default_registry.resolve(PluginScope.parse("vulnerability-remediation--node--npm"))` returns a `ConcreteResolution` whose `plugin.manifest.name == PluginId("vulnerability-remediation--node--npm")` and whose `composed_tccm.must_read` is non-empty.

## Acceptance criteria

- [ ] `plugins/vulnerability-remediation--node--npm/plugin.yaml` is a valid `PluginManifest` (`extra="forbid"` Pydantic-validated) with: `name: vulnerability-remediation--node--npm`, `version: 0.1.0`, `scope: vulnerability-remediation--node--npm`, `precedence: 100`, `extends: []`, `tccm: tccm.yaml`, and a `contributes.adapters` map pointing at the four ADR-0032 import paths S7-02 will fill (`dep_graph`, `import_graph`, `scip`, `test_inventory`).
- [ ] `plugins/vulnerability-remediation--node--npm/api.py` defines `plugin: Final = _Plugin(...)` (a `Plugin`-Protocol-conforming dataclass or class) and immediately calls `register_plugin(plugin)` at module-import time against `default_registry` — no eager subgraph build, no I/O, no LLM SDK imports.
- [ ] `plugins/vulnerability-remediation--node--npm/tccm.yaml` declares **at least** one `must_read` query (e.g., the `package.json` + `package-lock.json` slice), one `should_read` (e.g., `IndexHealthProbe` freshness), zero or more `may_read`, and `provides.vuln_index_capabilities: {nvd_parser: codegenie.vuln_index.nvd:NvdParser, ghsa_parser: ..., osv_parser: ...}` (three entries, even though the parsers themselves are S3-03's surface — the YAML can reference them by import path that resolves at plugin load time).
- [ ] `plugins/PLUGINS.lock` contains a row for `vulnerability-remediation--node--npm` whose value is the SHA-256 of the deterministic per-file digest of the plugin's tree (per ADR-0011); regenerated by `codegenie plugins lock-update` if such a helper exists, otherwise hand-computed and noted in the commit message.
- [ ] Plugin loader (from S2-03) discovers this plugin at startup, calls `importlib.import_module("plugins.vulnerability_remediation__node__npm.api")` (or whichever module-name mapping is in use; mirror the directory→module convention already established), and the registration is observable via `default_registry.get(PluginId("vulnerability-remediation--node--npm"))`.
- [ ] `default_registry.resolve(PluginScope.parse("vulnerability-remediation--node--npm").unwrap())` returns `ConcreteResolution` whose `plugin.manifest.name` is this plugin and whose `composed_tccm.must_read` is non-empty. The same scope must NOT return `UniversalFallbackResolution`.
- [ ] No LLM SDK import is added under `plugins/vulnerability-remediation--node--npm/` (verified via `make fence` + `make lint-imports` Phase 3 contracts from S1-05).
- [ ] `CODEOWNERS` entry for `plugins/PLUGINS.lock` exists (per ADR-0011); if S2-03 already landed it, this story does not re-add — verify and note.
- [ ] The red test from §TDD plan exists, was committed at red, and is now green.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict` clean on touched files; the new unit + integration tests pass; `pytest tests/integration/test_plugin_loader.py` (if it exists from S2-03) still green.

## Implementation outline

1. **Create the directory tree:**
   ```
   plugins/vulnerability-remediation--node--npm/
     plugin.yaml
     tccm.yaml
     api.py
     recipes/__init__.py        # empty; S7-02 fills
     adapters/__init__.py       # empty; S7-02 fills
     subgraph/__init__.py       # empty; the plugin returns the orchestrator's 5-node default subgraph in Phase 3
   ```
   Note: the directory uses double-hyphens; the Python module name will need underscoring per the loader's slug-to-module mapping established in S2-03. Mirror exactly whatever convention S2-03 set; do not invent a new one.
2. **`plugin.yaml`** — minimal valid `PluginManifest`. Hand-compose; do NOT use `model_dump_yaml` from a constructed instance (that would couple this file to Pydantic field order). YAML keys: `name`, `version`, `scope`, `precedence`, `extends`, `tccm`, `contributes.adapters`. The adapter import paths point at `plugins.vulnerability_remediation__node__npm.adapters.<module>:<Class>` — S7-02 lands those classes; the YAML can reference them by string ahead of time (import resolution happens at plugin load, not YAML parse).
3. **`tccm.yaml`** — declare the queries:
   - `must_read.derived`: one query computing `dep_graph.consumers(vulnerability.affected_package)` for the affected package (the BundleBuilder will dispatch through the npm `dep_graph` adapter once S7-02 lands it).
   - `should_read.derived`: one query checking `IndexHealthProbe` freshness (Phase 2 B2 output) — non-fatal but informs `AdapterConfidence`.
   - `provides.vuln_index_capabilities` map with three import-path entries pointing at the NVD/GHSA/OSV parsers shipped by S3-03.
4. **`api.py`** — module body:
   ```python
   from typing import Final
   from codegenie.plugins.protocols import Plugin, PluginSubgraph, Adapter, RecipeEngine
   from codegenie.plugins.manifest import PluginManifest
   from codegenie.plugins.registry import register_plugin
   from codegenie.types.identifiers import PluginId, PrimitiveName, TransformKind

   _MANIFEST_PATH = __file__.replace("api.py", "plugin.yaml")

   class _VulnNodeNpmPlugin:
       manifest: PluginManifest = PluginManifest.from_yaml(_MANIFEST_PATH).unwrap()
       def build_subgraph(self, registry): ...    # returns the orchestrator's default 5-node subgraph; no override in Phase 3
       def adapters(self) -> dict[PrimitiveName, Adapter]: ...  # imported from .adapters in S7-02; empty dict in this story
       def transforms(self) -> dict[TransformKind, RecipeEngine]: ...  # empty in this story; S7-02 fills

   plugin: Final = _VulnNodeNpmPlugin()
   register_plugin(plugin)
   ```
   The `adapters()` and `transforms()` methods may return empty dicts in this story — S7-02 fills them. The Protocol is satisfied; the BundleBuilder will surface adapter-missing as `AdapterConfidence.Unavailable`, which is the correct typed signal until S7-02 lands.
5. **`PLUGINS.lock` row** — compute the SHA-256 tree digest of the plugin directory per the algorithm established by S2-03 (sorted-relative-path → file-sha256, hashed together). Add the row. Note the operator workflow in the commit message (`codegenie plugins lock-update` if the helper exists; otherwise the hand-computation script).
6. **CODEOWNERS** — verify S2-03 already landed `plugins/PLUGINS.lock` ownership; if not, add the entry per ADR-0011.
7. **Tests** — see TDD plan.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/plugins/test_vuln_node_npm_plugin_scaffold.py`

```python
# tests/unit/plugins/test_vuln_node_npm_plugin_scaffold.py
import pytest

from codegenie.plugins.registry import default_registry
from codegenie.plugins.resolution import ConcreteResolution, UniversalFallbackResolution
from codegenie.plugins.scope import PluginScope
from codegenie.types.identifiers import PluginId


def test_vuln_node_npm_plugin_registers_with_default_registry():
    # The mere act of plugin loader having run at session start must have
    # registered our plugin. If this is failing, either api.py did not
    # call register_plugin, or the loader did not pick the directory up.
    plugin = default_registry.get(PluginId("vulnerability-remediation--node--npm"))
    assert plugin is not None
    assert plugin.manifest.name == PluginId("vulnerability-remediation--node--npm")
    assert plugin.manifest.scope.specificity() == 3   # Concrete on all three dims


def test_vuln_node_npm_plugin_is_concrete_resolution_head_against_its_scope():
    scope = PluginScope.parse("vulnerability-remediation--node--npm").unwrap()
    resolution = default_registry.resolve(scope)
    # Specificity-3 plugin must beat the universal (*,*,*) at specificity 0.
    assert isinstance(resolution, ConcreteResolution)
    assert resolution.plugin.manifest.name == PluginId("vulnerability-remediation--node--npm")
    assert resolution.composed_tccm.must_read   # non-empty


def test_vuln_node_npm_plugin_tccm_declares_provides_vuln_index_capabilities():
    plugin = default_registry.get(PluginId("vulnerability-remediation--node--npm"))
    # ADR-0004: task-class-specific capabilities live in TCCM provides, NOT on the kernel Plugin.
    provides = plugin.manifest.tccm.provides
    assert "vuln_index_capabilities" in provides
    vic = provides["vuln_index_capabilities"]
    # Three feed parsers (NVD / GHSA / OSV) per S3-03.
    for key in ("nvd_parser", "ghsa_parser", "osv_parser"):
        assert key in vic
        assert ":" in vic[key]   # "module:Class" import path shape
```

A second integration test asserts the loader actually walks the directory and `PLUGINS.lock` matches:

```python
# tests/integration/test_vuln_node_npm_plugin_lockfile_match.py
def test_vuln_node_npm_plugin_lockfile_row_present_and_matches_tree_sha():
    from codegenie.plugins.loader import compute_plugin_tree_sha256, read_plugins_lock
    expected = compute_plugin_tree_sha256("plugins/vulnerability-remediation--node--npm")
    lock = read_plugins_lock("plugins/PLUGINS.lock")
    assert lock["vulnerability-remediation--node--npm"] == expected
```

Run; confirm `default_registry.get(...)` raises `KeyError` or `PluginRejected`; commit the red.

### Green

Land the four files (`plugin.yaml`, `tccm.yaml`, `api.py`, empty `__init__.py`s under `recipes/`/`adapters/`/`subgraph/`) and the `PLUGINS.lock` row. Smallest shape: `api.py` has the `register_plugin(plugin)` call at module top level; `adapters()`/`transforms()` return `{}`; `build_subgraph(registry)` returns the orchestrator's default 5-node subgraph (no override).

### Refactor

- Move the `_MANIFEST_PATH` derivation to a module-level `pathlib.Path(__file__).parent / "plugin.yaml"` — cleaner than string replace.
- Confirm `mypy --strict` clean. `Plugin` is a Protocol; structural conformance is enough; no `class _VulnNodeNpmPlugin(Plugin):` inheritance.
- Add a docstring to `api.py` citing ADR-0002 and ADR-0004.
- Confirm the `forbidden-patterns` pre-commit hook does not catch `__import__` or `eval` in `api.py` — it shouldn't, but the plugin directory is new ground for the hook.

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/plugin.yaml` | New — `PluginManifest` YAML (scope, precedence, extends, contributes.adapters map) |
| `plugins/vulnerability-remediation--node--npm/tccm.yaml` | New — `must_read`/`should_read`/`may_read` + `provides.vuln_index_capabilities` |
| `plugins/vulnerability-remediation--node--npm/api.py` | New — plugin class + `register_plugin(plugin)` call at module-import time |
| `plugins/vulnerability-remediation--node--npm/recipes/__init__.py` | New — empty; S7-02 populates |
| `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` | New — empty; S7-02 populates |
| `plugins/vulnerability-remediation--node--npm/subgraph/__init__.py` | New — empty; orchestrator's default 5-node subgraph is used in Phase 3 |
| `plugins/PLUGINS.lock` | Modified — add the row for `vulnerability-remediation--node--npm` (tree sha256) |
| `CODEOWNERS` | Modified IFF S2-03 did not already add `plugins/PLUGINS.lock` ownership |
| `tests/unit/plugins/test_vuln_node_npm_plugin_scaffold.py` | New — registration + resolution + TCCM-provides red-then-green tests |
| `tests/integration/test_vuln_node_npm_plugin_lockfile_match.py` | New — recomputed tree sha matches the lockfile row |

## Out of scope

- **Recipe implementations** (`NpmLockfileSemverBumpRecipe`, etc.) — S7-02.
- **Adapter implementations** (the four ADR-0032 npm adapters) — S7-02.
- **NVD/GHSA/OSV parser code** — S3-03 ships those; this story only references them by import path.
- **End-to-end Express CVE test** — S8-02. This story stops at "the resolver returns this plugin for the scope," not "the plugin successfully remediates."
- **Plugin signing (Sigstore)** — Phase 11; ADR-0011 explicitly defers.
- **OpenRewriteRecipeEngine wiring** — S5-03 ships the scaffold; this plugin's `transforms()` does not list it in Phase 3 (Dockerfile fixture is Phase-7-tagged).

## Notes for the implementer

- **Scope parsing precedent.** `PluginScope.parse(s)` must already return `Result[PluginScope, ParseError]` from S1-02. If the parser does NOT accept `vulnerability-remediation--node--npm` (because `vulnerability-remediation` is a hyphenated `Concrete` value), that's a real S1-02 gap — surface it; do not silently mutate to single-word task class names. The `ScopeDim = Concrete | Wildcard` algebra holds regardless of whether the inner string has hyphens.
- **The `adapters()` returning `{}` is correct in this story.** The BundleBuilder will surface a missing adapter as `AdapterConfidence.Unavailable` and either fall back to a TCCM-declared substitute or log `LowConfidenceAnswerUsed`. The contract is satisfied; behavior arrives in S7-02.
- **`PLUGINS.lock` row computation.** Mirror the algorithm S2-03 settled on. Most likely shape: sorted relative-paths → per-file sha256 → outer sha256 of the concatenated rows. Do not invent a new algorithm; if S2-03's algorithm has edge cases (symlinks, executable bits), check those first.
- **The `recipes/__init__.py` + `adapters/__init__.py` MUST exist** even when empty — without them, the Python import system won't treat the directories as packages and S7-02 will trip on `ModuleNotFoundError: plugins.vulnerability_remediation__node__npm.recipes`.
- **Do NOT register two plugins in one file.** The decorator's contract is one plugin per `@register_plugin(...)` call; `api.py` calls it exactly once.
- **`forbidden-patterns` hook surface.** The Phase 0 pre-commit hook bans `subprocess.run(..., shell=True)`, `os.system`, `os.popen`, `eval(`, `exec(`, `__import__(`, `pickle.loads`. The plugin directory inherits the same coverage; the loader (S2-03) does its own `importlib.import_module(...)` which is allowed. Do not add an `__import__` call here.
- **No probe import.** This plugin does NOT import from `codegenie.probes`. The TCCM's `must_read` query references probe outputs at runtime via the BundleBuilder; the YAML is the seam. Importing `codegenie.probes.layer_d.foo` directly would break the layering and trip Phase 3's import-linter contract from S1-05.
- **Resist gold-plating.** Rule 2 (Simplicity First) — do not pre-emptively add `should_read` queries you can't justify; do not pre-emptively wire `extends` even to the universal plugin (Phase 3's `extends_chain` empty is the documented happy path); do not pre-emptively add a `subgraph/` override (the orchestrator's default 5-node subgraph is the right shape until a real reason to override arrives).
