# Story S7-01 — `plugins/vulnerability-remediation--node--npm/` scaffold, manifest, TCCM, registration

**Step:** Step 7 — First production plugin, universal HITL fallback plugin, synthetic third plugin
**Status:** HARDENED (validated 2026-05-19; see `_validation/S7-01-vuln-node-npm-plugin-scaffold.md`)
**Effort:** M
**Depends on:** S6-04 (RemediationOrchestrator + the 5-node subgraph + `_validate_stage6` seam must already exist for the plugin's `build_subgraph` to wire into), S7-03 (the universal-fallback plugin must be registrable for the negative-resolution assertion to be meaningful — until S7-03, tests register `tests/fixtures/plugins/universal_fallback_fixture.make_universal_fallback()`)
**ADRs honored:** [ADR-0002](../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md) (the plugin registers via the `register_plugin(plugin)` **function call** at module import time — NOT a decorator; the kernel is closed for modification), [ADR-0003](../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md) (the concrete plugin's specificity-3 scope `(vulnerability-remediation, node, npm)` makes it the resolver head against the `(*, *, *)` universal), [ADR-0004](../ADRs/0004-plugin-private-capabilities-via-tccm.md) (`provides.vuln_index_capabilities` carries the NVD/GHSA/OSV feed entrypoints — the kernel `Plugin` Protocol stays at four methods; the TCCM is observed via `ConcreteResolution.composed_tccm.provides`, NOT via `plugin.manifest.tccm.provides`), [ADR-0011](../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) (`PLUGINS.lock` is the integrity check populated when this plugin's tree first lands)

## Validation notes (2026-05-19)

This story was hardened by the `phase-story-validator` pass on 2026-05-19. Summary of the changes:

- **Block fixes (correctness).** The original story prescribed a `plugin.yaml` and tests that contradicted the actual code surfaces shipped by S2-02 (`PluginManifest`), S2-03 (`load_plugins`), S2-04 (`resolver`), and S3-03 (vuln-index feeds). Specifically:
  - `scope:` is a *nested submodel* (`task_class | languages | build_systems`), not a slug string.
  - The `tccm:` reference is `contributes.tccm`, not a top-level field — and `./tccm.yaml` is the schema default, so it may be omitted entirely.
  - Vuln-feed classes are `NvdFeed` / `GhsaFeed` / `OsvFeed` under `codegenie.vuln_index.feeds.{nvd,ghsa,osv}` — NOT `NvdParser` etc. under `codegenie.vuln_index.{nvd,ghsa,osv}`.
  - The loader API is `compute_plugin_tree_digest` + `LockFile.from_path` (both `Result`-returning), not `compute_plugin_tree_sha256` + `read_plugins_lock`.
  - `PluginSubgraph` is a TYPE_CHECKING-only forward-ref stub in `codegenie.plugins.protocols`; it is NOT in `__all__` and cannot be runtime-imported.
  - `manifest.tccm` is a *path string* (per `ManifestContributes`); the parsed TCCM is observable on `ConcreteResolution.composed_tccm` (via the resolver), not on the manifest.
- **Mutation-resistance hardening.** Tests as originally drafted would pass for `scope: (*,*,*)`, `precedence: 0`, `must_read: []`, four entries in `vuln_index_capabilities`, and a no-fallback-registered registry. ACs and tests were rewritten to assert field-level invariants (`Concrete` value of each scope dim; exact `precedence`; exact key-set of `vuln_index_capabilities`; resolver runs against a registry where the universal fallback fixture is also registered).
- **Architectural gap surfaced (DEFERRED).** The current resolver uses a placeholder `ComposedTccm` with only `provides` + `requires` (see `src/codegenie/plugins/resolver.py:120-134`). The real `TCCM` with `must_read`/`should_read`/`may_read` lives in `codegenie.plugins.tccm.TCCM` but the resolver has not been wired to load it from disk yet (`_plugin_tccm` reads `getattr(plugin, "_composed_tccm", None)`). The TCCM-loading upgrade is a precondition for this story's `must_read` ACs; until that upgrade lands, the plugin must expose `_composed_tccm` directly. The story's ACs were split accordingly — the `provides` assertion is observable today; the `must_read`/`should_read` assertions are gated on the resolver upgrade (called out as AC-13 below).
- **Anti-pattern removed.** The original Implementation Outline shipped `__file__.replace("api.py", "plugin.yaml")` then "fixed" it in Refactor — Rule-3 violation. The hardened outline writes `pathlib.Path(__file__).parent / "plugin.yaml"` upfront and uses a `@dataclass(frozen=True)` instance shape (mirroring `universal_fallback_fixture.py`) instead of an ad-hoc class with manifest as a class-body attribute.
- **Slug-to-module mapping clarified.** The note that "Python module name will need underscoring per the loader's slug-to-module mapping" was incorrect — `loader.py:289-293` does `importlib.import_module(f"plugins.{slug}.api")` with the literal hyphenated slug, and `tests/unit/plugins/test_loader.py:176-188` confirms hyphenated dirs work when `sys.path` includes the parent of `plugins/` (the production tree adds `plugins/__init__.py`; per-plugin dirs need their own `__init__.py` because the slug contains hyphens).

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

- [ ] **AC-1 (manifest shape).** `plugins/vulnerability-remediation--node--npm/plugin.yaml` parses cleanly through `PluginManifest.from_yaml(...)` (`extra="forbid"` Pydantic-validated) into a `PluginManifest` with:
  - `name == PluginId("vulnerability-remediation--node--npm")`
  - `version` non-empty (`"0.1.0"`)
  - `scope` is a `ManifestScope` with **exactly** `task_class="vulnerability-remediation"`, `languages="javascript"`, `build_systems="npm"` (per the existing fixture precedent at `tests/fixtures/plugins/loader_fixtures.py:36-42`; do NOT use `node` — Layer A's `LanguageDetection` emits `javascript`/`typescript`. The plugin's **directory** name uses `--node--` for human readability per production-ADR-0031 §dir convention, but the inner `languages:` token must match Layer A. See validation note.)
  - `extends == ()` (empty tuple — no inheritance in Phase 3)
  - `precedence == 100` (overridden from the schema default of 50; the explicit value is the audit anchor for "concrete plugins use higher precedence than the universal fallback's 0")
  - `contributes.adapters` is a non-empty `dict[PrimitiveName, str]` whose values are `module:Class` strings (shape `^[a-zA-Z_][a-zA-Z0-9_.]*:[A-Z][a-zA-Z0-9_]*$`) pointing at the four ADR-0032 import paths S7-02 will land — keys `dep_graph`, `import_graph`, `scip`, `test_inventory` (one each)
  - `contributes.tccm` either omitted (relies on schema default `"./tccm.yaml"`) or present with that value. **No top-level `tccm:` field** (forbidden by `extra="forbid"`).
- [ ] **AC-2 (api.py shape).** `plugins/vulnerability-remediation--node--npm/api.py` defines a `Plugin`-Protocol-conforming `@dataclass(frozen=True)` (mirroring `tests/fixtures/plugins/universal_fallback_fixture._UniversalFallbackPlugin`), binds it as `plugin: Final = _VulnNodeNpmPlugin(manifest=_load_manifest())`, and calls `register_plugin(plugin)` exactly once at module-import time against `default_registry`. The manifest-loading path uses `pathlib.Path(__file__).parent / "plugin.yaml"` (NOT `__file__.replace`); see Notes-for-implementer for the load-failure routing.
- [ ] **AC-3 (tccm.yaml shape).** `plugins/vulnerability-remediation--node--npm/tccm.yaml` parses cleanly through `codegenie.plugins.tccm.TCCM.model_validate(yaml.safe_load(...))` and exposes:
  - `must_read` is a list of `ContextQuery` of length ≥ 1, where at least one entry has `primitive == "dep_graph.consumers"` (one of the five closed `_KNOWN_PRIMITIVES` from `tccm.py:78-87`); the `args` dict contains a `package` key (the affected-package template variable BundleBuilder will substitute)
  - `should_read` is a list of `ContextQuery` of length ≥ 1, with at least one `primitive == "import_graph.transitive_callers"` OR `primitive == "scip.refs"` (the index-health-freshness substitute; pin one and add a Notes line citing the choice)
  - `may_read` may be empty
  - `provides` contains the key `"vuln_index_capabilities"`, and `provides["vuln_index_capabilities"]` is a `dict[str, str]` whose **key-set is exactly** `{"nvd_parser", "ghsa_parser", "osv_parser"}` (three; not two, not four) and whose values are the literal import paths `codegenie.vuln_index.feeds.nvd:NvdFeed`, `codegenie.vuln_index.feeds.ghsa:GhsaFeed`, `codegenie.vuln_index.feeds.osv:OsvFeed` (the actual S3-03 class names — NOT `NvdParser`/`GhsaParser`/`OsvParser`)
  - Each value resolves at plugin-load time: `importlib.import_module(module)` + `getattr(mod, class_name)` returns a non-None class — verified by a targeted unit test in §TDD that loops over the three entries.
- [ ] **AC-4 (`PLUGINS.lock` row).** `plugins/PLUGINS.lock`, parsed via `LockFile.from_path(Path("plugins/PLUGINS.lock")).unwrap()`, contains an entry whose key is `PluginId("vulnerability-remediation--node--npm")` and whose value is a `BlobDigest` (64-lowercase-hex matching `^[0-9a-f]{64}$`) equal to `compute_plugin_tree_digest(Path("plugins/vulnerability-remediation--node--npm")).unwrap()`. Re-derived via either `codegenie plugins lock-update` (if S2-03 shipped that helper) or by-hand from `compute_plugin_tree_digest`; the commit message names which method was used.
- [ ] **AC-5 (loader registration witness).** Running `load_plugins(Path("plugins"), Path("plugins/PLUGINS.lock"), registry=PluginRegistry())` against a **fresh** `PluginRegistry` instance (not `default_registry`) returns `Ok(LoadReport(loaded=tuple_containing_our_plugin_id, total_walked=N))`, and the registry passed in has the plugin registered (`registry.get(PluginId("vulnerability-remediation--node--npm")) is plugin`). The test must NOT rely on `default_registry` mutation — that path is reserved for production CLI use; tests use fresh registries (ADR-0002 §Consequences row 7).
- [ ] **AC-6 (resolution to ConcreteResolution).** With a **fresh** `PluginRegistry` populated with **both** this plugin AND the universal fallback fixture (`make_universal_fallback()`), calling `registry.resolve(PluginScope.parse("vulnerability-remediation--node--npm").unwrap())` returns a `ConcreteResolution` where:
  - `resolution.kind == "concrete"`
  - `resolution.plugin.manifest.name == PluginId("vulnerability-remediation--node--npm")`
  - `resolution.matched_scope` has all three dims as `Concrete` (not `Wildcard`) with values `"vulnerability-remediation"`, `"javascript"` (or whatever language token AC-1 settled on), `"npm"`
  - `resolution.extends_chain == (resolution.plugin,)` (length-1 chain, head is self — empty `extends` means the only entry in the chain is the plugin itself)
  - `isinstance(resolution, UniversalFallbackResolution)` is **False** — this assertion is meaningful BECAUSE the universal fallback IS registered in the test setup. Without the fallback registered, the negative would be vacuous.
- [ ] **AC-7 (`composed_tccm.provides` flows through).** The same `ConcreteResolution` from AC-6 exposes `resolution.composed_tccm.provides["vuln_index_capabilities"]` with the same three-entry key-set described in AC-3. (Note: this validates the resolver actually composed the plugin's TCCM and surfaced `provides` correctly — the resolver loads each plugin's `_composed_tccm` via `_plugin_tccm`; this story's plugin exposes it via the dataclass field, see Notes-for-implementer.)
- [ ] **AC-8 (no LLM SDKs).** `make fence` and `make lint-imports` stay green; no module under `plugins/vulnerability-remediation--node--npm/` imports `anthropic`, `langgraph`, `openai`, `langchain`, or `transformers` (Phase 3 fence contracts from S1-05).
- [ ] **AC-9 (CODEOWNERS for lockfile).** `grep -F 'PLUGINS.lock' CODEOWNERS` returns a non-empty match assigning the platform team (per ADR-0011 §Consequences row 4). If S2-03 already landed it, this story verifies and leaves untouched.
- [ ] **AC-10 (idempotency / single-registration).** Importing `plugins.vulnerability_remediation__node__npm.api` (Python-module form per `loader.py:289-293`) twice into the same registry raises `PluginAlreadyRegistered`; the test exercises this by calling `register_plugin(plugin, registry=fresh_registry)` twice and asserts the second call raises with both colliding-origin strings in the error message.
- [ ] **AC-11 (TCCM rejection coverage).** A mutated-fixture `tccm.yaml` whose `must_read` entry has `primitive: "dep_graph.consumer"` (typo — missing terminal `s`) is rejected at plugin-load time as a `PluginRejected` variant (likely surfaced via the resolver's `_plugin_tccm`/the manifest's TCCM loader); the test pins the typed variant rather than `Exception`.
- [ ] **AC-12 (precedence is honored, not defaulted).** With a second fixture plugin registered at the *same* scope `(vulnerability-remediation, javascript, npm)` but `precedence=50` (the schema default), `registry.resolve(...)` returns this story's plugin (the `precedence=100` one) at the head. (Mutation guard: prevents an implementer from silently relying on the schema default.)
- [ ] **AC-13 (DEFERRED — TCCM `must_read`/`should_read` end-to-end flow).** As of 2026-05-19 the resolver's `ComposedTccm` placeholder exposes only `provides` and `requires` (not `must_read`/`should_read`/`may_read`). This AC is *blocked* on a separate story that wires the resolver to use the real `codegenie.plugins.tccm.TCCM`. When that lands, this AC fires: `resolution.composed_tccm.must_read` is non-empty AND every entry's `.primitive` is a member of `_KNOWN_PRIMITIVES`. Until the resolver upgrade ships, S7-01's AC-7 (`provides` only) is the sufficient observable.
- [ ] **AC-14 (red test landed and now green).** The red tests from §TDD plan exist on a commit annotated "red" and are green on the final commit; the attempt log under `_attempts/S7-01-vuln-node-npm-plugin-scaffold.md` names the red-commit SHA.
- [ ] **AC-15 (toolchain clean).** `ruff format --check`, `ruff check`, `mypy --strict` clean on touched files; the new unit + integration tests pass; existing `pytest tests/unit/plugins/test_loader.py` still green (the new plugin tree must not break any sibling test).

## Implementation outline

1. **Create the directory tree:**
   ```
   plugins/vulnerability-remediation--node--npm/
     __init__.py                # empty; required because the slug contains hyphens (see `tests/unit/plugins/test_loader.py:182-188`)
     plugin.yaml
     tccm.yaml
     api.py
     recipes/__init__.py        # empty; S7-02 fills
     adapters/__init__.py       # empty; S7-02 fills
   ```
   `subgraph/__init__.py` is **omitted** until a real subgraph override is needed (Rule 2 / Simplicity First — the manifest default `contributes.subgraph: str = "./subgraph/"` is a path-pointer that does not require an existing directory for the loader; if a future story needs an override, the directory can be added then). The plugin's `build_subgraph(registry)` returns the orchestrator's default subgraph imported from S6-04 (see step 4 — call out the exact import once S6-04 finalises the export). The loader does `importlib.import_module(f"plugins.{slug}.api")` with the literal hyphenated slug; `plugins/__init__.py` (top-level) and the per-plugin `__init__.py` both must exist so Python's filesystem-based finder accepts the dotted-name lookup.
2. **`plugin.yaml`** — minimal valid `PluginManifest`. Hand-compose; do NOT use `model_dump_yaml` from a constructed instance (that would couple this file to Pydantic field order). Canonical shape:
   ```yaml
   name: vulnerability-remediation--node--npm
   version: "0.1.0"
   scope:
     task_class: vulnerability-remediation
     languages: javascript
     build_systems: npm
   extends: []
   precedence: 100
   contributes:
     adapters:
       dep_graph: plugins.vulnerability_remediation__node__npm.adapters.dep_graph:NpmDepGraphAdapter
       import_graph: plugins.vulnerability_remediation__node__npm.adapters.import_graph:NpmImportGraphAdapter
       scip: plugins.vulnerability_remediation__node__npm.adapters.scip:NpmScipAdapter
       test_inventory: plugins.vulnerability_remediation__node__npm.adapters.test_inventory:NpmTestInventoryAdapter
   ```
   - `extends: []` Pydantic-validates as the empty tuple `()`.
   - `contributes.tccm` is omitted; the schema default `"./tccm.yaml"` applies.
   - `requirements` is omitted; the schema default `ManifestRequirements()` applies.
   - No top-level `tccm:` key — that would trip `extra="forbid"` → `SchemaViolation`.
   - The adapter import-path strings target modules S7-02 will create; YAML parse only validates *shape* (`module:Class` grammar via `tccm.py:_IMPORT_PATH_RE`); the actual import resolution fires at S7-02's runtime when the BundleBuilder dispatches. Confirm `Concrete` class-name suffixes (e.g., `NpmDepGraphAdapter`) match what S7-02 will land — if S7-02's names differ at story-execution time, this story's `contributes.adapters` value strings must be updated as part of S7-02, not retroactively.
3. **`tccm.yaml`** — canonical shape:
   ```yaml
   must_read:
     - primitive: dep_graph.consumers
       args:
         package: "{vulnerability.affected_package}"
   should_read:
     - primitive: scip.refs
       args:
         symbol: "{vulnerability.affected_symbol}"
       max_files: 50
   may_read: []
   provides:
     vuln_index_capabilities:
       nvd_parser: codegenie.vuln_index.feeds.nvd:NvdFeed
       ghsa_parser: codegenie.vuln_index.feeds.ghsa:GhsaFeed
       osv_parser: codegenie.vuln_index.feeds.osv:OsvFeed
   requires: {}
   ```
   - Every `primitive` must be a member of the closed set `_KNOWN_PRIMITIVES` (see `src/codegenie/plugins/tccm.py:78-87`). The two used here are `dep_graph.consumers` and `scip.refs`.
   - `provides.vuln_index_capabilities` import-path values point at the **real** S3-03 classes — `NvdFeed`, `GhsaFeed`, `OsvFeed` under `codegenie.vuln_index.feeds.*`. AC-3 verifies these resolve at load time.
   - `args` value types restricted to `str | int | bool | list[str]` (per `ContextQuery.args` annotation).
4. **`api.py`** — module body, frozen-dataclass shape mirroring `tests/fixtures/plugins/universal_fallback_fixture.py`:
   ```python
   """Vulnerability-remediation Node/npm plugin — first concrete production plugin.

   Per ADR-0002 the registration is a function call, not a decorator.
   Per ADR-0004 task-class-specific capabilities live on TCCM provides,
   not on the kernel Plugin Protocol.
   """
   from __future__ import annotations

   from dataclasses import dataclass, field
   from pathlib import Path
   from typing import Any, Final

   from codegenie.plugins.manifest import PluginManifest
   from codegenie.plugins.protocols import Adapter, Plugin, RecipeEngine
   from codegenie.plugins.registry import register_plugin
   from codegenie.plugins.tccm import TCCM  # only if the TCCM is exposed via _composed_tccm; see Notes
   from codegenie.types.identifiers import PluginId, PrimitiveName, TransformKind

   _MANIFEST_PATH: Final[Path] = Path(__file__).parent / "plugin.yaml"
   _TCCM_PATH: Final[Path] = Path(__file__).parent / "tccm.yaml"


   def _load_manifest() -> PluginManifest:
       """Load and validate the plugin's manifest at module-import time.

       Failure routing: `from_yaml` returns Result; on `Err` the unwrap
       raises and surfaces through `loader.py:289-293` as a typed
       `PluginImportError`. Note that this is a *defence-in-depth*
       reload: the loader already validated the manifest in Gate 2
       before importing this module. Re-loading here keeps the plugin
       self-contained for ad-hoc Python imports outside the loader.
       """
       result = PluginManifest.from_yaml(_MANIFEST_PATH)
       if result.is_err():
           raise RuntimeError(f"plugin manifest invalid: {result.unwrap_err()!r}")
       return result.unwrap()


   @dataclass(frozen=True)
   class _VulnNodeNpmPlugin:
       """Plugin-Protocol-conforming instance for the vuln node/npm plugin."""

       manifest: PluginManifest
       _adapters: dict[PrimitiveName, Adapter] = field(default_factory=dict)
       _transforms: dict[TransformKind, RecipeEngine] = field(default_factory=dict)

       def build_subgraph(self, registry: Any) -> Any:
           # Returns the orchestrator's default 5-node subgraph; S6-04 owns
           # the exact import. Until that lands, raise NotImplementedError —
           # the resolver does not call build_subgraph during S7-01's tests.
           raise NotImplementedError("subgraph wiring is S6-04 / S7-02's surface")

       def adapters(self) -> dict[PrimitiveName, Adapter]:
           return dict(self._adapters)

       def transforms(self) -> dict[TransformKind, RecipeEngine]:
           return dict(self._transforms)


   plugin: Final[_VulnNodeNpmPlugin] = _VulnNodeNpmPlugin(manifest=_load_manifest())
   register_plugin(plugin)
   ```
   - **Do NOT** import `PluginSubgraph` from `codegenie.plugins.protocols` — it is only a `TYPE_CHECKING` forward-ref stub and is not in `__all__`. The `build_subgraph` return annotation is `Any` until S6-04 lands the real type.
   - **Do NOT** call `register_plugin` inside `if __name__ == "__main__":` or any conditional — the loader's Gate 4 relies on the unconditional import side-effect (ADR-0002).
   - The `_adapters` and `_transforms` dicts are empty in this story; S7-02 lands the values. The dataclass-field default uses `field(default_factory=dict)` so the empty-state is typed correctly.
   - **TCCM exposure (interim).** Because the resolver currently reads `getattr(plugin, "_composed_tccm", None)` (placeholder `ComposedTccm` with only `provides`/`requires`), this story's plugin must additionally expose a `_composed_tccm: ComposedTccm` field built from the plugin's `tccm.yaml`'s `provides`/`requires` map. The `must_read`/`should_read` fields land via the resolver upgrade tracked by AC-13.
5. **`PLUGINS.lock` row** — compute the SHA-256 tree digest via `compute_plugin_tree_digest(Path("plugins/vulnerability-remediation--node--npm"))` (from `src/codegenie/plugins/loader.py`). Append the JSON-shaped entry to `plugins/PLUGINS.lock` (the file is a JSON object `dict[PluginId, BlobDigest]` per `LockFile`'s schema). Document the operator workflow in the commit message (`codegenie plugins lock-update` if the helper exists; otherwise the hand-computation Python one-liner using `compute_plugin_tree_digest`).
6. **CODEOWNERS** — `grep -F 'PLUGINS.lock' CODEOWNERS` to verify S2-03 already landed the entry; if absent, add the entry per ADR-0011 §Consequences row 4.
7. **Tests** — see TDD plan.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/plugins/test_vuln_node_npm_plugin_scaffold.py` (unit) and `tests/integration/plugins/test_vuln_node_npm_plugin_load.py` (integration).

Tests use **fresh** `PluginRegistry()` instances populated by `load_plugins(...)` — they do NOT depend on `default_registry` mutation (ADR-0002 §Consequences row 7). Tests that need the universal fallback also register `make_universal_fallback()` so the negative assertions are meaningful.

```python
# tests/unit/plugins/test_vuln_node_npm_plugin_scaffold.py
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from codegenie.plugins.errors import PluginAlreadyRegistered
from codegenie.plugins.loader import compute_plugin_tree_digest, load_plugins
from codegenie.plugins.lockfile import LockFile
from codegenie.plugins.manifest import PluginManifest
from codegenie.plugins.registry import PluginRegistry, register_plugin
from codegenie.plugins.resolver import (
    ConcreteResolution,
    UniversalFallbackResolution,
)
from codegenie.plugins.scope import Concrete, PluginScope
from codegenie.plugins.tccm import TCCM
from codegenie.types.identifiers import BlobDigest, PluginId, PrimitiveName
from tests.fixtures.plugins.universal_fallback_fixture import make_universal_fallback

_PLUGIN_ROOT = Path("plugins")
_PLUGIN_DIR = _PLUGIN_ROOT / "vulnerability-remediation--node--npm"
_PLUGIN_ID = PluginId("vulnerability-remediation--node--npm")


@pytest.fixture
def loaded_registry() -> PluginRegistry:
    """Fresh registry, populated by running the real loader against `plugins/`."""
    registry = PluginRegistry()
    result = load_plugins(_PLUGIN_ROOT, _PLUGIN_ROOT / "PLUGINS.lock", registry=registry)
    assert result.is_ok(), f"loader returned {result.unwrap_err()!r}"
    return registry


# --- AC-1: manifest shape (field-level pins) ---


def test_manifest_loads_and_has_exact_field_values() -> None:
    manifest = PluginManifest.from_yaml(_PLUGIN_DIR / "plugin.yaml").unwrap()
    assert manifest.name == _PLUGIN_ID
    assert manifest.version == "0.1.0"
    assert manifest.scope.task_class == "vulnerability-remediation"
    assert manifest.scope.languages == "javascript"
    assert manifest.scope.build_systems == "npm"
    assert manifest.extends == ()
    assert manifest.precedence == 100   # NOT default 50
    # Adapter map keys are exactly the four ADR-0032 primitives.
    assert set(manifest.contributes.adapters.keys()) == {
        PrimitiveName("dep_graph"),
        PrimitiveName("import_graph"),
        PrimitiveName("scip"),
        PrimitiveName("test_inventory"),
    }


# --- AC-3: TCCM shape + import-path resolution ---


def test_tccm_declares_vuln_index_capabilities_with_exact_keyset() -> None:
    import yaml
    data = yaml.safe_load((_PLUGIN_DIR / "tccm.yaml").read_text(encoding="utf-8"))
    tccm = TCCM.model_validate(data)
    # must_read non-empty AND uses known primitive.
    assert len(tccm.must_read) >= 1
    assert tccm.must_read[0].primitive == PrimitiveName("dep_graph.consumers")
    # provides has exactly the three expected feed entries.
    vic = tccm.provides["vuln_index_capabilities"]
    assert set(vic.keys()) == {"nvd_parser", "ghsa_parser", "osv_parser"}
    # Each import path resolves to a real class object at load time.
    for key in ("nvd_parser", "ghsa_parser", "osv_parser"):
        module_path, _, class_name = vic[key].partition(":")
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        assert isinstance(cls, type), f"{vic[key]} did not resolve to a class"


# --- AC-4: lockfile row ---


def test_plugins_lock_row_matches_recomputed_tree_digest() -> None:
    lockfile = LockFile.from_path(_PLUGIN_ROOT / "PLUGINS.lock").unwrap()
    recomputed: BlobDigest = compute_plugin_tree_digest(_PLUGIN_DIR).unwrap()
    assert lockfile.root[_PLUGIN_ID] == recomputed


# --- AC-5: loader registers via fresh registry ---


def test_loader_registers_plugin_in_fresh_registry(loaded_registry: PluginRegistry) -> None:
    plugin = loaded_registry.get(_PLUGIN_ID)
    assert plugin.manifest.name == _PLUGIN_ID


# --- AC-6: resolution to ConcreteResolution against a registry that also has the fallback ---


def test_resolution_returns_concrete_and_not_fallback_when_fallback_is_registered(
    loaded_registry: PluginRegistry,
) -> None:
    # Register the universal fallback so the negative is meaningful.
    loaded_registry.register(make_universal_fallback())
    scope = PluginScope.parse("vulnerability-remediation--javascript--npm").unwrap()
    resolution = loaded_registry.resolve(scope)
    assert isinstance(resolution, ConcreteResolution)
    assert not isinstance(resolution, UniversalFallbackResolution)
    assert resolution.plugin.manifest.name == _PLUGIN_ID
    # Field-level assertions on matched_scope — all Concrete, NOT wildcard.
    assert isinstance(resolution.matched_scope.task_class, Concrete)
    assert resolution.matched_scope.task_class.value == "vulnerability-remediation"
    assert isinstance(resolution.matched_scope.language, Concrete)
    assert resolution.matched_scope.language.value == "javascript"
    assert isinstance(resolution.matched_scope.build_system, Concrete)
    assert resolution.matched_scope.build_system.value == "npm"
    # extends_chain is length-1 (self only) when extends == ().
    assert len(resolution.extends_chain) == 1
    assert resolution.extends_chain[0] is resolution.plugin


# --- AC-7: composed_tccm.provides flows through ---


def test_composed_tccm_provides_vuln_index_capabilities_after_resolution(
    loaded_registry: PluginRegistry,
) -> None:
    loaded_registry.register(make_universal_fallback())
    scope = PluginScope.parse("vulnerability-remediation--javascript--npm").unwrap()
    resolution = loaded_registry.resolve(scope)
    assert isinstance(resolution, ConcreteResolution)
    vic = resolution.composed_tccm.provides["vuln_index_capabilities"]
    assert set(vic.keys()) == {"nvd_parser", "ghsa_parser", "osv_parser"}


# --- AC-10: double-registration raises PluginAlreadyRegistered ---


def test_double_register_raises_typed_collision(loaded_registry: PluginRegistry) -> None:
    existing = loaded_registry.get(_PLUGIN_ID)
    with pytest.raises(PluginAlreadyRegistered):
        register_plugin(existing, registry=loaded_registry)


# --- AC-12: precedence is honored against a peer at the same scope ---


def test_precedence_100_beats_peer_at_default_50(loaded_registry: PluginRegistry) -> None:
    # Construct a peer plugin at the same scope but with the schema default.
    # Use model_construct to bypass `name` collision against the loaded plugin
    # — the peer has a distinct id but a colliding scope.
    from dataclasses import dataclass, field
    from typing import Any
    from codegenie.plugins.manifest import (
        ManifestContributes,
        ManifestRequirements,
        ManifestScope,
        PluginManifest,
    )

    peer_manifest = PluginManifest.model_construct(
        name=PluginId("vulnerability-remediation--javascript--npm-peer-fixture"),
        version="0.0.0",
        scope=ManifestScope(
            task_class="vulnerability-remediation",
            languages="javascript",
            build_systems="npm",
        ),
        extends=(),
        precedence=50,    # the schema default — the mutation surface.
        contributes=ManifestContributes(),
        requirements=ManifestRequirements(),
    )

    @dataclass(frozen=True)
    class _Peer:
        manifest: PluginManifest
        def build_subgraph(self, registry: Any) -> Any: raise NotImplementedError
        def adapters(self) -> dict[Any, Any]: return {}
        def transforms(self) -> dict[Any, Any]: return {}

    loaded_registry.register(_Peer(manifest=peer_manifest))  # type: ignore[arg-type]
    scope = PluginScope.parse("vulnerability-remediation--javascript--npm").unwrap()
    resolution = loaded_registry.resolve(scope)
    assert isinstance(resolution, ConcreteResolution)
    assert resolution.plugin.manifest.name == _PLUGIN_ID   # NOT the peer.
```

A second TCCM-rejection test exercises AC-11:

```python
# tests/unit/plugins/test_vuln_node_npm_plugin_tccm_rejection.py
import pytest
from pydantic import ValidationError

from codegenie.plugins.tccm import TCCM


def test_tccm_rejects_unknown_primitive_typo() -> None:
    """A typo in the primitive name (`consumer` vs `consumers`) must
    raise at parse time, not silently pass through."""
    payload = {
        "must_read": [{"primitive": "dep_graph.consumer", "args": {"package": "p"}}],
        "should_read": [],
        "may_read": [],
        "provides": {},
        "requires": {},
    }
    with pytest.raises(ValidationError):
        TCCM.model_validate(payload)
```

Property test for tree-digest invariance (mirrors the existing `tests/unit/plugins/test_loader_digest_property.py` precedent):

```python
# tests/unit/plugins/test_vuln_node_npm_tree_digest_property.py
from pathlib import Path
import hypothesis
from hypothesis import strategies as st

from codegenie.plugins.loader import compute_plugin_tree_digest

# Property: re-running compute_plugin_tree_digest against the same plugin
# tree returns byte-identical digests across N invocations. Catches any
# accidental non-determinism (sort key drift, locale-dependent encoding,
# walk-order leak).
@hypothesis.given(_n=st.integers(min_value=2, max_value=8))
def test_tree_digest_is_idempotent(_n: int) -> None:
    plugin_dir = Path("plugins/vulnerability-remediation--node--npm")
    first = compute_plugin_tree_digest(plugin_dir).unwrap()
    for _ in range(_n - 1):
        again = compute_plugin_tree_digest(plugin_dir).unwrap()
        assert again == first
```

Run all four test files; confirm each one fails for the expected reason (the plugin directory does not yet exist → `IoError` / `FileNotFoundError`); commit at red with the SHA recorded in `_attempts/S7-01-vuln-node-npm-plugin-scaffold.md`.

### Green

Land the directory tree per §Implementation outline step 1, the `plugin.yaml` per step 2, the `tccm.yaml` per step 3, the `api.py` per step 4, and the `PLUGINS.lock` row per step 5. Verify each AC's named test passes; the property test should be deterministic.

### Refactor

- Confirm `mypy --strict` clean across `plugins/vulnerability-remediation--node--npm/api.py` and all new test files. `Plugin` is a Protocol; structural conformance is enough; no `class _VulnNodeNpmPlugin(Plugin):` inheritance.
- Re-read `api.py` for any forgotten `print` / debug-log statements; the plugin module body is import-time-only — anything printed leaks into the loader's startup output.
- Confirm the `forbidden-patterns` pre-commit hook does not flag any pattern in the new files (it shouldn't — but the `plugins/` subtree is new ground for the hook).
- Verify CODEOWNERS for `plugins/PLUGINS.lock` (AC-9) is in place.
- Note in `_attempts/S7-01-vuln-node-npm-plugin-scaffold.md`: the `must_read`/`should_read` end-to-end assertions (AC-13) are blocked on the resolver upgrade story — add that story as a follow-up dependency for whichever story integrates with the BundleBuilder (likely S7-02 or S8-02).

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/__init__.py` | New — empty; required for Python's filesystem-based finder to admit the hyphenated dir (see `tests/unit/plugins/test_loader.py:182-188`) |
| `plugins/vulnerability-remediation--node--npm/plugin.yaml` | New — `PluginManifest` YAML (nested `scope`, `precedence: 100`, `extends: []`, `contributes.adapters` map; NO top-level `tccm:`) |
| `plugins/vulnerability-remediation--node--npm/tccm.yaml` | New — `must_read` referencing `dep_graph.consumers`, `should_read` referencing `scip.refs`, `provides.vuln_index_capabilities` with exact three-entry key-set pointing at the real `codegenie.vuln_index.feeds.*:*Feed` classes |
| `plugins/vulnerability-remediation--node--npm/api.py` | New — `@dataclass(frozen=True)` plugin instance + `register_plugin(plugin)` call at module-import time; uses `pathlib.Path(__file__).parent / "plugin.yaml"` (NOT `__file__.replace`); imports do NOT pull `PluginSubgraph` (TYPE_CHECKING-only) |
| `plugins/vulnerability-remediation--node--npm/recipes/__init__.py` | New — empty; S7-02 populates |
| `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` | New — empty; S7-02 populates |
| `plugins/PLUGINS.lock` | Modified — add the row keyed by `PluginId("vulnerability-remediation--node--npm")` with value `BlobDigest` from `compute_plugin_tree_digest(...)` |
| `CODEOWNERS` | Modified IFF S2-03 did not already add `plugins/PLUGINS.lock` ownership (verify via `grep -F 'PLUGINS.lock' CODEOWNERS` first) |
| `tests/unit/plugins/test_vuln_node_npm_plugin_scaffold.py` | New — unit tests covering AC-1, AC-3, AC-4, AC-5, AC-6, AC-7, AC-10, AC-12 |
| `tests/unit/plugins/test_vuln_node_npm_plugin_tccm_rejection.py` | New — AC-11 typed-rejection test for malformed `tccm.yaml` |
| `tests/unit/plugins/test_vuln_node_npm_tree_digest_property.py` | New — Hypothesis property test for AC-4's tree-digest determinism |

## Out of scope

- **Recipe implementations** (`NpmLockfileSemverBumpRecipe`, etc.) — S7-02.
- **Adapter implementations** (the four ADR-0032 npm adapters) — S7-02.
- **NVD/GHSA/OSV parser code** — S3-03 ships those; this story only references them by import path.
- **End-to-end Express CVE test** — S8-02. This story stops at "the resolver returns this plugin for the scope," not "the plugin successfully remediates."
- **Plugin signing (Sigstore)** — Phase 11; ADR-0011 explicitly defers.
- **OpenRewriteRecipeEngine wiring** — S5-03 ships the scaffold; this plugin's `transforms()` does not list it in Phase 3 (Dockerfile fixture is Phase-7-tagged).

## Notes for the implementer

- **Scope parsing.** `PluginScope.parse("vulnerability-remediation--javascript--npm")` succeeds — each dim matches `^[a-z0-9_-]+$` and the hyphen in `vulnerability-remediation` is in-grammar (`Concrete.value` carries the full string verbatim). The same is true for `vulnerability-remediation--node--npm`; we pick `javascript` (not `node`) for the inner `languages:` field because Layer A's `LanguageDetection` emits `javascript`/`typescript` — the BundleBuilder's matching against probe outputs needs an exact string match. The plugin *directory* uses `--node--` for operator readability (every `node` plugin is npm-family); the *manifest scope's `languages:` field* uses `javascript`. This split is intentional and documented here so the next plugin's author sees the precedent.
- **Hyphenated module imports work.** `loader.py:289-293` does `importlib.import_module(f"plugins.{slug}.api")` with the literal hyphenated slug. Python's filesystem-based finder happily resolves the dotted name to a directory even when the name parts contain hyphens (proof: `tests/unit/plugins/test_loader.py:176-188`). The per-plugin `__init__.py` is required because Python needs the directory marked as a package; the top-level `plugins/__init__.py` already exists.
- **The `adapters()` returning `{}` is correct in this story.** The BundleBuilder will surface a missing adapter as `AdapterConfidence.Unavailable` and either fall back to a TCCM-declared substitute or log `LowConfidenceAnswerUsed`. The contract is satisfied; behavior arrives in S7-02.
- **`PLUGINS.lock` row computation.** Use `compute_plugin_tree_digest` directly (see `src/codegenie/plugins/loader.py:158-185`). The algorithm: `_collect_plugin_files` walks the tree, skips `__pycache__/` and `*.pyc`, refuses symlink-escapes, returns sorted `(relpath, bytes)` pairs; `tree_digest_of_files` (in `codegenie.hashing`) is the chokepoint that produces the 64-hex SHA-256. The lockfile's value is then lifted through `parse_blob_digest` into a `BlobDigest`.
- **The `recipes/__init__.py` + `adapters/__init__.py` MUST exist** even when empty — without them, the Python import system won't treat the directories as packages and S7-02 will trip on `ModuleNotFoundError: plugins.vulnerability_remediation__node__npm.recipes`.
- **Do NOT register two plugins in one file.** `register_plugin(plugin)` is called exactly once in `api.py`; the registry raises `PluginAlreadyRegistered` on collision.
- **`forbidden-patterns` hook surface.** The Phase 0 pre-commit hook bans `subprocess.run(..., shell=True)`, `os.system`, `os.popen`, `eval(`, `exec(`, `__import__(`, `pickle.loads`. The plugin directory inherits the same coverage; the loader (S2-03) does its own `importlib.import_module(...)` which is allowed. Do not add an `__import__` call here.
- **No probe import.** This plugin does NOT import from `codegenie.probes`. The TCCM's `must_read` query references probe outputs at runtime via the BundleBuilder; the YAML is the seam. Importing `codegenie.probes.layer_d.foo` directly would break the layering and trip Phase 3's import-linter contract from S1-05.
- **`PluginSubgraph` is unimportable at runtime.** It lives under `if TYPE_CHECKING:` in `codegenie/plugins/protocols.py:35-41` and is intentionally not in `__all__`. Use `Any` for the `build_subgraph` return annotation until S6-04 lands the real type, and rely on `from __future__ import annotations` to defer evaluation.
- **TCCM placeholder ↔ real TCCM gap.** The resolver currently uses a placeholder `ComposedTccm` with only `provides`/`requires` (see `src/codegenie/plugins/resolver.py:120-134`); the real `TCCM` with `must_read`/`should_read`/`may_read` lives in `codegenie.plugins.tccm`. The resolver loads each plugin's TCCM via `_plugin_tccm` which does `getattr(plugin, "_composed_tccm", None)` — so this plugin's `_VulnNodeNpmPlugin` dataclass must expose a `_composed_tccm: ComposedTccm` field built from the YAML's `provides`/`requires`. Until a follow-up story upgrades the resolver to use the real `TCCM` (covered by AC-13), the `must_read`/`should_read` assertions cannot be tested end-to-end through the resolver — they are tested by directly parsing `tccm.yaml` via `TCCM.model_validate(...)` (see AC-3).
- **Rule-of-three observation.** S7-01 is the *first* concrete production plugin; S7-04 will make 3 (with the synthetic third plugin). Do **not** extract a `PluginScaffold` helper now (Rule 2 — three similar lines is better than premature abstraction). When S7-04 lands, audit the copy-paste overlap with `api.py`; if >60% is duplicated, lift a `make_plugin(manifest_path) -> Plugin` factory at that point. Document this rule-of-three trigger in `api.py`'s module docstring so the next author sees the precedent.
- **Class-body manifest load: defence-in-depth re-read.** The loader's Gate 2 already parses `plugin.yaml` and surfaces `SchemaViolation`/`MalformedYaml` cleanly *before* Gate 4 imports `api.py`. The `_load_manifest()` call in `api.py` re-parses the same YAML at module-import time, redundant with Gate 2. The redundancy is intentional: it keeps the plugin self-contained for ad-hoc Python imports outside the loader (e.g., a future REPL session) and ensures the plugin's `manifest` field always reflects the on-disk YAML. The redundancy cost is one file read per process startup, which is negligible. *Failure routing:* if the YAML is malformed at this point, `_load_manifest()` raises `RuntimeError`, which the loader's Gate 4 catches and surfaces as `PluginImportError` — operator sees the typed variant, but with a less-precise reason than Gate 2's `SchemaViolation`. This is acceptable because Gate 2 would have caught the same condition first in normal operation.
- **Resist gold-plating.** Rule 2 (Simplicity First) — do not pre-emptively add `should_read` queries you can't justify; do not pre-emptively wire `extends` even to the universal plugin (Phase 3's `extends_chain` empty is the documented happy path); do not pre-emptively add a `subgraph/` directory (the orchestrator's default subgraph applies until a real reason to override arrives).
