# Story S7-04 — Synthetic `example--noop--*` plugin + 3-plugin contract bake test + `PLUGINS.lock` mismatch test

**Step:** Step 7 — First production plugin, universal HITL fallback plugin, synthetic third plugin
**Status:** HARDENED
**Effort:** M
**Depends on:** S2-03 (the `load_plugins` loader + `PLUGINS.lock` integrity check the bake test and mismatch test both drive), S5-01 (`RecipeEngine` / `RecipeProtocol` / `RecipeRegistry` / `@register_recipe` + the `match_recipes` walker the noop recipe is exercised through), S6-03 (the `SubgraphNode` Protocol + `SubgraphState` the noop node implements — **not yet built**, see Residual risks), S7-01 (the vuln plugin must be registered), S7-02 (the vuln plugin's recipes + adapters must be wired), S7-03 (the universal fallback must be registered). The subprocess/exit-4 arm of the mismatch test additionally depends on S6-05 (`codegenie remediate` CLI) — see AC-18 and Out of scope.
**ADRs honored:** [ADR-0002](../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md) (the synthetic plugin registers via the same `register_plugin(plugin, registry=...)` *function call* as the production plugins — *bake-testing* the kernel's "extension by addition" claim — and the bake test runs against a fresh `PluginRegistry()` instance, never `default_registry`), [ADR-0003](../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md) (the bake test exercises both `ConcreteResolution` and `UniversalFallbackResolution` paths against the three-plugin universe), [ADR-0004](../ADRs/0004-plugin-private-capabilities-via-tccm.md) (synthetic plugin declares a `provides.example_capabilities` namespace — proves the TCCM-as-extension mechanism is generic, not vuln-specific), [ADR-0009](../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md) (synthetic plugin's `transforms()` exposes a third `RecipeEngine` impl — the Protocol is now bake-tested against 3 engines: `NpmLockfileRecipeEngine` + `OpenRewriteRecipeEngine` + `NoopRecipeEngine`), [ADR-0011](../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) (**the `PLUGINS.lock` mismatch test in this story is the integrity-check ADR's headline regression**).

## Validation notes

Validated: 2026-05-19
Verdict: HARDENED
Findings addressed: 23 total — 7 block, 12 harden, 4 nit (consolidated across the four critics).

This story carried the **same pervasive API-drift defect class** every S7 sibling carried (see `_validation/S7-01..S7-03`): it was written against an imagined API surface, not the as-built `src/codegenie/`. The *goal* (bake-test the plugin contract against 3 plugins + the `PLUGINS.lock` mismatch regression) is sound and traces cleanly to High-level-impl §Step 7 done-criteria 1, 4, 5 and the roadmap exit criterion — hence HARDENED, not RESCUE. The mechanism was rewritten against verified source.

Block-tier closures:

1. **Loader API.** The story prescribed `load_plugins(registry, roots=[prod, fixture])`. The as-built signature (`loader.py:191`) is `load_plugins(plugin_root: Path, lock_path: Path, *, registry: PluginRegistry | None = None, verifier: PluginVerifier | None = None) -> Result[LoadReport, PluginRejected]` — a **single** root, a **single** lock path, returns a `Result` (never raises). No multi-root form exists. Every AC / TDD snippet rewritten.
2. **Loader import-prefix collision.** `loader.py:291` hardcodes `importlib.import_module(f"plugins.{slug}.api")`. A plugin directory under `tests/fixtures/plugins/` is therefore **not importable** by `load_plugins` — the discovery + integrity gate accept any `plugin_root`, but the import step is pinned to the `plugins.` package. Reconciliation (AC-7, AC-9, Notes): the **two production plugins** are directory-loaded via `load_plugins(<repo>/plugins, <repo>/plugins/PLUGINS.lock, registry=fresh)`; the **synthetic plugin** is registered directly into the *same* fresh registry via `register_plugin(noop_plugin, registry=fresh)` — the established `universal_fallback_fixture.make_universal_fallback()` precedent. This still bake-tests the *contract surface* against 3 plugins (the goal); it does not require the loader to import a non-`plugins`-rooted directory.
3. **`plugin.recipe_registry` does not exist.** The `Plugin` Protocol has **exactly four** members (`manifest`, `build_subgraph`, `adapters`, `transforms` — `protocols.py:69`, arch §C2 "What is NOT on `Plugin`"). The recipe surface is reached via `transforms() -> dict[TransformKind, RecipeEngine]` and via a fixture-owned `RecipeRegistry` exercised through `match_recipes(...)` (`recipe_engine.py:156`). `RecipeRegistry` has no `.iter()` — its surface is `register / get / all / _reset_for_tests`.
4. **The four ADR-0032 adapter Protocols + `confidence()` + `AdapterConfidence.High` do not exist.** The as-built kernel `Adapter` Protocol (`protocols.py:56`) has **one** member: `primitive: PrimitiveName`. `DepGraphAdapter`/`ImportGraphAdapter`/`ScipAdapter`/`TestInventoryAdapter` are production-ADR-0032 *prose*, not shipped Protocol classes. `AdapterConfidence` (`outcomes.py:408`) is `Trusted | Degraded | Unavailable` — there is **no `High`**, and it is a union TypeAlias (`AdapterConfidence.High()` is invalid). The noop adapters conform to the **single-member `Adapter` Protocol**, one per `PrimitiveName`. The deferred concrete adapter method surface is surfaced as a gap (Notes).
5. **Pseudo-OO union construction + invented members.** `RecipeOutcome.Skipped(reason=NOOP)` → `RecipeOutcome` is a discriminated-union TypeAlias; construct `Skipped(...)` directly. `Skipped` fields are `kind` / `reason: SkipReason` / `plugin_id: PluginId`; `SkipReason = Literal["plugin_disabled", "registry_skipped"]` — `NOOP` is not a member. `Applies(NoopPlan)` → `Applies(plan: ApplicationPlan)`; `NoopPlan` does not exist. `register_recipe(..., precedence=100)` → no `precedence` kwarg; precedence is a recipe **class attribute**.
6. **Wrong import paths.** `codegenie.transforms.transitions`, `codegenie.transforms.applicability`, `codegenie.transforms.subgraph_state` do not exist. `Advance` / `NodeTransition` / `Applies` / `Skipped` all live in `codegenie.transforms.outcomes` (re-exported from `codegenie.transforms`). `SubgraphState` + the `SubgraphNode` Protocol ship in S6-03 (un-built) — see Residual risks.
7. **Dependency cliff + bake-test mutation-blindness.** `Depends on:` widened to the full transitive spine. Bake-test assertions rewritten from `is not None` / `isinstance(_, dict)` (which a `{}`-returning broken plugin passes) to structural `isinstance` against the `@runtime_checkable` Protocols + non-emptiness + exact-set-equality.

Harden/nit: positive control added to the mismatch test (AC-17); pure `load_plugins` boundary made the primary integrity assertion with the subprocess/exit-4 path a thin gated arm (AC-16/AC-18); anti-pollution ACs added (AC-12, AC-13); the extension-by-addition property promoted to an observable AC (AC-11); four ~5-LOC adapter files collapsed to one `noop_adapters.py`; the fixture `README.md` dropped in favour of a module docstring (sibling convention); newtype discipline pinned. `@register_recipe` as a *decorator* was confirmed **correct** and left intact (distinct from `register_plugin`, a function call).

Full audit log: `docs/phases/03-vuln-deterministic-recipe/stories/_validation/S7-04-example-noop-plugin-bake-test.md`.

## Context

The roadmap exit criterion *"plugin contract bake-tested against ≥3 plugins (extension-by-addition test for Phase 7)"* is satisfied here. Phase 7 introduces `migration-chainguard-distroless` as the second real task class under the "zero edits to existing plugins" rule. Bake-testing the kernel contract against three plugins **before** Phase 7 ships proves that:

1. The kernel `Plugin` Protocol's four members (`manifest`, `build_subgraph`, `adapters`, `transforms` — locked by ADR-0004 / arch §C2) are sufficient for plugins with wildly different shapes (production vuln-remediation, universal HITL fallback, synthetic noop).
2. The `PluginRegistry` resolver's `(specificity desc, precedence desc, name asc)` ordering produces deterministic results across a non-trivial plugin universe, and both `ConcreteResolution` and `UniversalFallbackResolution` are reachable.
3. The per-plugin `RecipeRegistry` from S5-01 generalizes — three plugins each carrying their own recipes, no cross-contamination — and the `RecipeEngine` Protocol admits a third implementation (`NoopRecipeEngine`).
4. The kernel `Adapter` Protocol admits ≥2 implementations (npm-real from S7-02 + noop-fake), so `Plugin.adapters()` dispatch is not coupled to npm-specific assumptions.
5. **The `PLUGINS.lock` integrity check actually rejects with `IntegrityMismatch` when a plugin file is mutated post-lock** — regression-testing ADR-0011's honest framing.

The synthetic plugin lives under `tests/fixtures/plugins/example--noop--noop/` (NOT under `plugins/` — it is test scaffolding, not production). Because the as-built loader (`loader.py:291`) imports plugin `api.py` modules via the hardcoded `plugins.{slug}.api` package prefix, the synthetic plugin is **not** directory-discoverable by `load_plugins` from a non-`plugins`-rooted location. The bake test therefore registers it directly into the shared test registry via `register_plugin(noop_plugin, registry=...)` — the same fixture-module pattern `tests/fixtures/plugins/universal_fallback_fixture.py` already uses. The two production plugins ARE directory-loaded via `load_plugins`. All three land in one fresh `PluginRegistry()`; the bake test then walks every contract surface on all three.

Its scope is `example--noop--noop` (three `Concrete` dims, specificity 3, but `task_class == "example"` matches no real workflow scope). It exercises **every** kernel contract surface:

- `Plugin` — full four-member surface (`manifest`, `build_subgraph`, `adapters`, `transforms`).
- `Adapter` — implementations keyed by the four `PrimitiveName` values (`dep_graph`, `import_graph`, `scip`, `test_inventory`), each structurally conforming to the as-built single-member `Adapter` Protocol.
- `RecipeEngine` — `NoopRecipeEngine` whose `apply(...)` returns a `Skipped` outcome.
- `RecipeProtocol` — `NoopRecipe` whose `applies(cve, bundle)` returns `Applies(plan=...)`.
- `SubgraphNode` — one node returning `Advance(...)` (proving the orchestrator can drive a non-short-circuit transition through a plugin's subgraph).

Per `phase-arch-design.md §"Open questions deferred to implementation"`: *"`example--noop--*` exact contract-surface coverage. Synthesis says 'exercises every contract surface.' Implementation may discover gaps."* If this story finds gaps (e.g., a Protocol method no production plugin happens to exercise, or — as this validation surfaced — the loader's `plugins.`-prefixed import precluding a fixture-rooted plugin), extending the synthetic plugin to cover them IS in scope; surfacing them as ADR amendments is also in scope.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals` G3 ("Plugin contract bake-tested against 3 plugins. Two production + one synthetic. `tests/integration/test_three_plugin_contract.py` resolves all three and exercises every contract surface").
  - `../phase-arch-design.md §Departures from all three inputs #3` ("Synthetic `example--noop--*` plugin under `tests/fixtures/plugins/`").
  - `../phase-arch-design.md §Component design C2` — the **four** Protocol members the bake test must exercise; the "What is NOT on `Plugin`" note; `adapters() -> dict[PrimitiveName, Adapter]`; `transforms() -> dict[TransformKind, RecipeEngine]`.
  - `../phase-arch-design.md §Edge cases E17` (PLUGINS.lock SHA mismatch — `PluginRejected(integrity_mismatch)`, exit 4 with the diff).
  - `../phase-arch-design.md §Scenarios D` (loader walks `plugins/*/plugin.yaml` + verifies `PLUGINS.lock` sha256).
- **Phase ADRs:** `../ADRs/0002-*.md` (fresh `PluginRegistry()` for tests; `register_plugin` is a **function call**), `../ADRs/0011-*.md` (the integrity-check ADR — the mutate-a-file-post-lock test is its headline consequence), `../ADRs/0004-*.md` (P3-005: synthetic plugin under `tests/fixtures/plugins/` declares `provides.example_capabilities`), `../ADRs/0009-*.md` (the synthetic adds a third `RecipeEngine` impl).
- **Production ADRs:** `../../../production/adrs/0031-plugin-architecture.md` (the umbrella contract this story bake-tests), `../../../production/adrs/0032-language-search-adapters.md` (the *primitives* the noop adapters key on — note ADR-0032 defines per-primitive adapters, NOT four distinct shipped Protocol *types*; the as-built kernel `Adapter` Protocol is one type keyed by `PrimitiveName`).
- **As-built source (verify every prescribed API against these — the story was hardened against them, but S7-01/02/03 are not yet executed, so re-confirm before red):**
  - `src/codegenie/plugins/protocols.py` — the `Plugin` + `Adapter` Protocols (`@runtime_checkable`).
  - `src/codegenie/plugins/loader.py` — `load_plugins`, `compute_plugin_tree_digest`, the `plugins.{slug}.api` import.
  - `src/codegenie/plugins/registry.py` — `PluginRegistry`, `register_plugin`, `default_registry`.
  - `src/codegenie/plugins/resolver.py` / `resolution.py` — `ConcreteResolution`, `UniversalFallbackResolution`.
  - `src/codegenie/plugins/recipe_registry.py` — `RecipeRegistry`, `@register_recipe`.
  - `src/codegenie/transforms/recipe_engine.py` — `RecipeEngine`, `RecipeProtocol`, `match_recipes`.
  - `src/codegenie/transforms/outcomes.py` — `Skipped`, `Applies`, `ApplicationPlan`, `SkipReason`, `Advance`, `NodeTransition`, `AdapterConfidence`.
  - `src/codegenie/plugins/errors.py` — the `PluginRejected` tagged union; `IntegrityMismatch`; `exit_code_for_rejection`.
  - `tests/fixtures/plugins/universal_fallback_fixture.py` + `fake_plugin.py` — the established fixture-plugin shape (module docstring, `@dataclass`, boundary newtype-lift, direct `register_plugin`).
- **High-level impl:** `../High-level-impl.md §Step 7` Done criteria items 1, 4, 5.

## Goal

Land the synthetic `example--noop--noop` plugin under `tests/fixtures/plugins/` exercising every kernel contract surface, plus the integration test `tests/integration/test_three_plugin_contract.py` that loads all three plugins into one fresh `PluginRegistry()` and walks every contract surface on every plugin via a single reusable contract-walker, plus the regression test `tests/integration/test_plugins_lock_mismatch.py` that proves a post-lock file mutation makes `load_plugins(...)` return `Err(IntegrityMismatch)` (and, when the `codegenie remediate` CLI exists, surfaces as process exit code 4).

## Acceptance criteria

### The synthetic plugin

- [ ] **AC-1** — `tests/fixtures/plugins/example--noop--noop/` contains: `plugin.yaml`, `tccm.yaml`, `api.py`, `recipes/__init__.py` + `recipes/noop_recipe.py`, `adapters/__init__.py` + `adapters/noop_adapters.py` (one file, four adapter classes), `subgraph/__init__.py` + `subgraph/noop_node.py`. No `PLUGINS.lock` ships inside this fixture dir (the mismatch test computes its own lock for a staged tmp tree — AC-15). (validator: collapsed four adapter files → one; dropped the standalone `PLUGINS.lock` artifact and the `README.md`.)
- [ ] **AC-2** — `plugin.yaml` declares scope `example--noop--noop` as a nested `ManifestScope` (three `Concrete` dims) and `precedence: 10` (low — defense-in-depth; the scope matches no real workflow anyway). A test lifts the manifest scope via the as-built path (e.g. `lift_manifest_scope(...)` per the S7-01/S7-03 precedent) to a `PluginScope` and asserts `.specificity() == 3`. (validator: `manifest.scope` is a `ManifestScope`, not a `PluginScope`; `specificity()` is a `PluginScope` method — same fix as S7-01 CN-7 / S7-03 CN-6.)
- [ ] **AC-3** — The synthetic plugin instance is a `@dataclass(frozen=True)` mirroring `universal_fallback_fixture._UniversalFallbackPlugin`, structurally satisfying the `Plugin` Protocol; `api.py` registers it with the function call `register_plugin(noop_plugin, registry=...)` (ADR-0002 — a function call, NOT a decorator). All `PluginId` / `PrimitiveName` / `TransformKind` / `RecipeId` values in the fixture are constructed via their newtype constructors at the boundary, never raw `str`.
- [ ] **AC-4** — `tccm.yaml` declares `provides.example_capabilities: {example_parser: <module-path>:NoopParser}`, proving the TCCM-as-extension mechanism (ADR-0004) admits a non-vuln capability namespace. The kernel must treat `example_capabilities` as an opaque namespace string; if the loader/TCCM resolver rejects it because the namespace is "unknown", that is a regression to flag.
- [ ] **AC-5** — The four noop adapter classes (`NoopDepGraphAdapter`, `NoopImportGraphAdapter`, `NoopScipAdapter`, `NoopTestInventoryAdapter`) each structurally conform to the as-built single-member `Adapter` Protocol (`protocols.py`): each carries a `primitive: PrimitiveName` attribute set to `dep_graph` / `import_graph` / `scip` / `test_inventory` respectively. `Plugin.adapters()` returns a `dict[PrimitiveName, Adapter]` with exactly those four keys. (validator: the four ADR-0032 method-bearing Protocols + `confidence()` + `AdapterConfidence.High` do not exist — see Validation notes block 4 and Notes.)
- [ ] **AC-6** — `NoopRecipeEngine` structurally conforms to the `RecipeEngine` Protocol; its `async def apply(self, plan, ...)` returns a directly-constructed `Skipped(reason="registry_skipped", plugin_id=PluginId("example--noop--noop"))` (a `RecipeOutcome` variant — confirm the exact `Skipped` field set against `outcomes.py` at implementation time). `NoopRecipe` structurally conforms to `RecipeProtocol` with class attributes `recipe_id` / `name` / `kind` / `precedence`; its `applies(self, cve, bundle)` (two-arg, the real signature) returns `Applies(plan=ApplicationPlan(...))`. The recipe is registered against a fixture-owned `RecipeRegistry` via `@register_recipe(PluginId("example--noop--noop"))` (a decorator — no `precedence` kwarg; `precedence` is the class attribute).
- [ ] **AC-7** — `NoopSubgraphNode` structurally conforms to the S6-03 `SubgraphNode` Protocol and its `run(...)` returns an `Advance(...)` (`NodeTransition` variant from `codegenie.transforms.outcomes`) — exercising the non-`ShortCircuit` branch the universal plugin cannot. (validator: gated on S6-03; if S6-03's as-built `SubgraphNode` / `SubgraphState` shape differs from this story's assumption, the executor reconciles against the shipped code — see Residual risks.)

### The 3-plugin contract bake test (`tests/integration/test_three_plugin_contract.py`)

- [ ] **AC-8** — The test builds **one fresh `PluginRegistry()`** instance (NOT `default_registry` — ADR-0002 test-isolation). It directory-loads the two production plugins via `load_plugins(<repo>/plugins, <repo>/plugins/PLUGINS.lock, registry=fresh)` and asserts the returned `Result` is `Ok`; it registers the synthetic plugin into the *same* registry via `register_plugin(noop_plugin, registry=fresh)`. After setup, `{p.manifest.name for p in registry.all()}` **equals exactly** `{PluginId("vulnerability-remediation--node--npm"), PluginId("universal--*--*"), PluginId("example--noop--noop")}` (exact set equality + cardinality 3 — catches a dropped, deduped, or stray plugin).
- [ ] **AC-9** — A single reusable contract-walker (`tests/integration/_plugin_contract_walker.py`, or an equivalent helper) takes a `Plugin` and asserts, **for every one of the three plugins**: `isinstance(plugin, Plugin)` (the `@runtime_checkable` kernel Protocol); `isinstance(plugin.manifest, PluginManifest)`; `plugin.build_subgraph(registry)` returns a subgraph with ≥1 node, each node structurally conforming to `SubgraphNode`; `plugin.adapters()` is a non-empty `dict` whose every value structurally conforms to `Adapter` and whose keys are `PrimitiveName`s; `plugin.transforms()` is a non-empty `dict` whose every value structurally conforms to `RecipeEngine`. Shallow `is not None` / `isinstance(_, dict)` checks are **not** sufficient. (validator: the bake test must fail against a plugin returning `{}` or a bare object.)
- [ ] **AC-10** — Resolution is asserted both ways against the three-plugin registry: `registry.resolve(PluginScope.parse("vulnerability-remediation--node--npm").unwrap())` is a `ConcreteResolution` whose plugin is the vuln plugin; `registry.resolve(PluginScope.parse("vulnerability-remediation--rust--cargo").unwrap())` is a `UniversalFallbackResolution` (no concrete match); `registry.resolve(PluginScope.parse("example--noop--noop").unwrap())` is a `ConcreteResolution` whose plugin is the noop plugin. An additional assertion proves the noop plugin (specificity 3, precedence 10) never *shadows* the vuln plugin on the vuln scope.
- [ ] **AC-11** — The plugin universe under test is a single module-level `Final` tuple in `test_three_plugin_contract.py`; every `@pytest.mark.parametrize` over plugins derives from that tuple, and the contract-walking logic lives entirely in the AC-9 helper. The test includes a docstring (or comment) stating the observable extension-by-addition contract: **adding Phase 7's distroless plugin to the bake test is exactly one new tuple entry — zero edits to `_plugin_contract_walker.py`**. (validator: rule-of-three is crossed — vuln + universal + noop; Phase 7 is the 4th consumer — so the "extension by addition" property this story exists to prove is itself made observable.)
- [ ] **AC-12** — A test asserts the production `plugins/PLUGINS.lock` does **not** reference `example--noop--noop` (the synthetic must never enter the production lockfile).
- [ ] **AC-13** — After `test_three_plugin_contract.py` runs, `default_registry` does **not** contain `PluginId("example--noop--noop")` — the synthetic plugin's registration never leaks into the production singleton.
- [ ] **AC-14** — The noop plugin's recipe surface is exercised: the fixture-owned `RecipeRegistry` is asserted to contain the noop recipe; calling the recipe's `applies(cve, bundle)` against fixture inputs returns an `Applies`, and `NoopRecipeEngine.apply(...)` returns a `Skipped` (`RecipeOutcome` variant). Reached via `plugin.transforms()` and/or the fixture registry — **never** via a `plugin.recipe_registry` attribute (no such member exists on `Plugin`).
- [ ] **AC-15** — The bake test (`test_three_plugin_contract.py`) executes offline (no `npm`, no network) in well under 5 seconds.

### The `PLUGINS.lock` mismatch regression test (`tests/integration/test_plugins_lock_mismatch.py`)

- [ ] **AC-16** — **Primary, in-process assertion (the ADR-0011 headline regression).** The test: (1) `copytree`s the two production plugins into a `tmp_path` root and computes a fresh `PLUGINS.lock` for that snapshot via the as-built helper (`compute_plugin_tree_digest` + the lockfile writer); (2) **positive control** — calls `load_plugins(tmp_root, tmp_lock, registry=PluginRegistry())` against the un-mutated tree and asserts the `Result` is `Ok` (proving the test fails for *tampering*, not setup noise); (3) mutates one byte of one file in a plugin tree WITHOUT regenerating the lock; (4) calls `load_plugins` again and asserts the `Result` is `Err`, the error is the `IntegrityMismatch` variant (`kind == "integrity_mismatch"`), and the error carries both the expected and observed digest so an operator can diff. (validator: the integrity check is reachable at the pure `load_plugins` boundary — fast, deterministic, no subprocess; the positive control was missing.)
- [ ] **AC-17** — `exit_code_for_rejection(IntegrityMismatch(...))` returns `4` (a direct, in-process assertion of the ADR-0011 / E17 exit-code contract — no subprocess needed).
- [ ] **AC-18** — **Conditional subprocess arm.** *If and only if* the `codegenie remediate` CLI subcommand exists (S6-05), one additional subprocess test invokes it against the mutated tree and asserts process exit code `4` and that stderr contains the `kind` literal `integrity_mismatch` (assert on the typed `kind` string — **not** the substring `PluginRejected`, which is a union alias and need not appear in rendered output). If `codegenie remediate` does not yet exist, this AC is satisfied by AC-16 + AC-17 and the subprocess assertion is deferred to the S6-05 story (note it there). (validator: the story must not depend on un-built CLI subcommands for its core regression.)

### Hygiene

- [ ] **AC-19** — No LLM SDK import added anywhere under `tests/fixtures/plugins/example--noop--noop/` (verified via `make fence`).
- [ ] **AC-20** — The red tests from §TDD plan exist, were committed at red (failing for the *intended* reason — see TDD plan), and are now green.
- [ ] **AC-21** — `ruff format --check`, `ruff check`, `mypy --strict` clean on touched files; existing tests (S7-01, S7-02, S7-03) still green.

## Implementation outline

1. **Confirm preconditions before red.** Verify `plugins/vulnerability-remediation--node--npm/` and `plugins/universal--*--*/` exist on disk and `load_plugins` loads them clean; verify the S6-03 `SubgraphNode` Protocol + `SubgraphState` are shipped. If any precondition is unmet, set the story `BLOCKED` (or `BLOCKED-PARTIAL`) and record the gap in `_attempts/S7-04.md` — do **not** stub fake production plugins to force the bake test green.
2. **Create the synthetic plugin tree.**
   ```
   tests/fixtures/plugins/example--noop--noop/
     plugin.yaml                 # nested ManifestScope: example--noop--noop; precedence: 10
     tccm.yaml                   # provides.example_capabilities
     api.py                      # _NoopPlugin @dataclass(frozen=True) + register_plugin(plugin, registry=...)
     recipes/__init__.py
     recipes/noop_recipe.py      # NoopRecipe + NoopRecipeEngine + the fixture RecipeRegistry
     adapters/__init__.py
     adapters/noop_adapters.py   # NoopDepGraphAdapter, NoopImportGraphAdapter, NoopScipAdapter, NoopTestInventoryAdapter
     subgraph/__init__.py
     subgraph/noop_node.py       # NoopSubgraphNode returning Advance(...)
   ```
3. **`api.py`** — module docstring documents which contract surface each piece exercises (sibling convention — `universal_fallback_fixture.py` / `fake_plugin.py` do this; no `README.md`). The `_NoopPlugin` `@dataclass(frozen=True)` exposes `manifest`, `build_subgraph`, `adapters`, `transforms`. A `make_noop_plugin()` factory + a `register_noop_plugin(registry)` helper let the bake test inject a fresh registry (the `make_universal_fallback` precedent).
4. **Adapters** — one file, four classes, each ≈3 LOC, each carrying `primitive = PrimitiveName("dep_graph")` etc. They conform to the as-built one-member `Adapter` Protocol. Do **not** add `confidence()` / `consumers()` unless the as-built `Adapter` Protocol has grown those members by implementation time — if it has, match it; if not, surface the deferred-method-surface gap in the attempt log.
5. **`NoopRecipeEngine`** — `async def apply(self, plan, ...)` returns `Skipped(...)` constructed directly. **`NoopRecipe`** — class attributes `recipe_id` / `name` / `kind` / `precedence`; `applies(self, cve, bundle)` returns `Applies(plan=ApplicationPlan(...))`. Registered via `@register_recipe(PluginId("example--noop--noop"))` against a fixture-local `RecipeRegistry` instance (not `default_recipe_registry`).
6. **`NoopSubgraphNode`** — `run(...)` returns `Advance(...)`. Confirm the S6-03 `SubgraphNode.run` signature + `SubgraphState` shape against the shipped code; do not invent a `bootstrap_for_testing` constructor — use whatever S6-03 ships, or annotate the input `Any` under `if TYPE_CHECKING:` if the type is fenced out of plugin folders (the S7-03 DP-2 precedent).
7. **`tccm.yaml`** — `provides.example_capabilities` with a module path the loader's slug-to-module mapping resolves. Confirm the path convention against S2-03 — do not invent one.
8. **Bake test** — see TDD plan. One fresh `PluginRegistry()`; two production plugins via `load_plugins`; the synthetic via `register_plugin`; the AC-9 contract-walker walks all three.
9. **Mismatch test** — see TDD plan. Primary path is the in-process `load_plugins` boundary; the subprocess/exit-4 arm is conditional on S6-05.

## TDD plan — red / green / refactor

### Red

Test file: `tests/integration/test_three_plugin_contract.py`

```python
import asyncio
from typing import Final

import pytest

from codegenie.plugins.registry import PluginRegistry, register_plugin
from codegenie.plugins.loader import load_plugins
from codegenie.plugins.protocols import Plugin, Adapter, RecipeEngine
from codegenie.plugins.resolution import ConcreteResolution, UniversalFallbackResolution
from codegenie.plugins.scope import PluginScope
from codegenie.types.identifiers import PluginId
# Real homes — confirm at green time:
#   Advance, NodeTransition  -> codegenie.transforms (re-export of .outcomes)
#   SubgraphState            -> S6-03 module (NOT codegenie.transforms.subgraph_state)

_VULN = PluginId("vulnerability-remediation--node--npm")
_UNIVERSAL = PluginId("universal--*--*")
_NOOP = PluginId("example--noop--noop")
_PLUGIN_UNIVERSE: Final[tuple[PluginId, ...]] = (_VULN, _UNIVERSAL, _NOOP)


@pytest.fixture
def three_plugin_registry(repo_root):
    """Fresh registry: 2 production plugins directory-loaded, 1 synthetic registered directly."""
    registry = PluginRegistry()
    result = load_plugins(
        repo_root / "plugins",
        repo_root / "plugins" / "PLUGINS.lock",
        registry=registry,
    )
    assert result.is_ok(), result          # fail loud on a load error
    from tests.fixtures.plugins... import register_noop_plugin   # exact path TBD at green
    register_noop_plugin(registry)
    return registry


def test_exactly_three_plugins_registered(three_plugin_registry):
    assert {p.manifest.name for p in three_plugin_registry.all()} == set(_PLUGIN_UNIVERSE)


@pytest.mark.parametrize("plugin_id", _PLUGIN_UNIVERSE)
def test_plugin_satisfies_full_kernel_contract(three_plugin_registry, plugin_id):
    from tests.integration._plugin_contract_walker import assert_plugin_contract
    assert_plugin_contract(three_plugin_registry.get(plugin_id), three_plugin_registry)


def test_concrete_resolution_for_npm_scope(three_plugin_registry):
    r = three_plugin_registry.resolve(PluginScope.parse("vulnerability-remediation--node--npm").unwrap())
    assert isinstance(r, ConcreteResolution)
    assert r.plugin.manifest.name == _VULN


def test_universal_resolution_for_unmatched_scope(three_plugin_registry):
    r = three_plugin_registry.resolve(PluginScope.parse("vulnerability-remediation--rust--cargo").unwrap())
    assert isinstance(r, UniversalFallbackResolution)


def test_noop_never_shadows_concrete(three_plugin_registry):
    r = three_plugin_registry.resolve(PluginScope.parse("vulnerability-remediation--node--npm").unwrap())
    assert r.plugin.manifest.name == _VULN   # specificity 3 + precedence beats noop's precedence 10
```

`_plugin_contract_walker.py` (the AC-9 helper) does the structural walk: `isinstance(plugin, Plugin)`; a `PluginManifest` check; `build_subgraph` → ≥1 node, each `isinstance(node, SubgraphNode)`; `adapters()` non-empty, every value `isinstance(_, Adapter)`; `transforms()` non-empty, every value `isinstance(_, RecipeEngine)`. The noop-specific assertions (`Advance` from the noop node via `asyncio.run`; the recipe `Applies` / engine `Skipped`) live in dedicated tests so the parametrized walk stays plugin-agnostic.

Test file: `tests/integration/test_plugins_lock_mismatch.py`

```python
import shutil

from codegenie.plugins.registry import PluginRegistry
from codegenie.plugins.loader import load_plugins
from codegenie.plugins.errors import IntegrityMismatch, exit_code_for_rejection


def test_post_lock_mutation_returns_integrity_mismatch(tmp_path, repo_root):
    """ADR-0011 headline regression — at the pure load_plugins boundary."""
    root = tmp_path / "plugins"
    shutil.copytree(repo_root / "plugins", root)
    lock = root / "PLUGINS.lock"
    # (re)compute a fresh lock for this snapshot via the as-built helper — exact API TBD at green.
    _write_fresh_lock(root, lock)

    # Positive control: the un-mutated tree must load clean.
    ok = load_plugins(root, lock, registry=PluginRegistry())
    assert ok.is_ok(), ok

    # Mutate one byte; do NOT regenerate the lock.
    victim = next((root).glob("*/api.py"))
    victim.write_text(victim.read_text() + "\n# tampered\n")

    err = load_plugins(root, lock, registry=PluginRegistry())
    assert err.is_err()
    rejection = err.unwrap_err()
    assert isinstance(rejection, IntegrityMismatch)
    assert rejection.kind == "integrity_mismatch"
    # error carries expected + observed digest (field names TBD at green)


def test_integrity_mismatch_maps_to_exit_4():
    # construct a minimal IntegrityMismatch and assert the exit-code contract
    assert exit_code_for_rejection(_some_integrity_mismatch()) == 4
```

Run; confirm the bake-test imports fail (`ModuleNotFoundError` on the not-yet-created noop fixture + `_plugin_contract_walker`) and the mismatch test fails because the noop fixture / lock helper don't exist — the **intended** red. Commit the red.

### Green

Land the noop plugin tree + `_plugin_contract_walker.py` + the lock helper. Smallest shape: adapters ≈3 LOC each (one file); `NoopRecipeEngine` ≈10 LOC; `NoopRecipe` ≈8 LOC; `NoopSubgraphNode` ≈5 LOC; `api.py` ≈20 LOC; `tccm.yaml` ≈6 lines; `plugin.yaml` ≈12 lines. Total ≈80 LOC of fixture + ≈80 LOC of bake-test infrastructure. The "~400 LOC" estimate in `phase-arch-design.md §Tradeoffs` is the ceiling, not the floor.

### Refactor

- Confirm `mypy --strict` clean — all noop adapter / engine / recipe / node classes are *structurally* compatible with the corresponding `@runtime_checkable` Protocol; no ABC inheritance.
- Confirm no `.codegenie/` artifacts leak from the mismatch test into the host repo; `tmp_path` cleans up automatically.
- The `_plugin_contract_walker.py` helper is the load-bearing extension seam — keep its public function (`assert_plugin_contract`) intent-revealing and free of `Any` in its signature.
- Document in `api.py`'s module docstring which contract surface each fixture piece exercises.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/plugins/example--noop--noop/plugin.yaml` | New — nested `ManifestScope` (`example--noop--noop`), precedence 10 |
| `tests/fixtures/plugins/example--noop--noop/tccm.yaml` | New — declares `provides.example_capabilities` namespace |
| `tests/fixtures/plugins/example--noop--noop/api.py` | New — `_NoopPlugin` `@dataclass(frozen=True)` + `make_noop_plugin()` + `register_noop_plugin(registry)` (test-injection form) |
| `tests/fixtures/plugins/example--noop--noop/recipes/__init__.py` | New |
| `tests/fixtures/plugins/example--noop--noop/recipes/noop_recipe.py` | New — `NoopRecipe` + `NoopRecipeEngine` + fixture `RecipeRegistry` |
| `tests/fixtures/plugins/example--noop--noop/adapters/__init__.py` | New |
| `tests/fixtures/plugins/example--noop--noop/adapters/noop_adapters.py` | New — four `Noop*Adapter` classes, one file |
| `tests/fixtures/plugins/example--noop--noop/subgraph/__init__.py` | New |
| `tests/fixtures/plugins/example--noop--noop/subgraph/noop_node.py` | New — `NoopSubgraphNode` returning `Advance(...)` |
| `tests/integration/_plugin_contract_walker.py` | New — the reusable contract-walker; the extension-by-addition seam (AC-9, AC-11) |
| `tests/integration/test_three_plugin_contract.py` | New — the 3-plugin bake test |
| `tests/integration/test_plugins_lock_mismatch.py` | New — **the ADR-0011 regression test** |

## Out of scope

- **Adding the synthetic plugin to the production `plugins/PLUGINS.lock`** — it lives under `tests/fixtures/plugins/`; AC-12 enforces it never enters the production lockfile.
- **Directory-loading the synthetic plugin via `load_plugins`** — the loader's `plugins.{slug}.api` import prefix (`loader.py:291`) precludes importing a `tests/fixtures/`-rooted directory; the synthetic is registered directly via `register_plugin` (Validation notes block 2). Making the loader support arbitrary import roots is a loader concern (S2-03 / a future ADR amendment), not this story.
- **The `codegenie remediate` subprocess exit-4 assertion** — deferred to the S6-05 story unless that CLI already exists when this story runs (AC-18).
- **Shipping `codegenie plugins lock-update`** — the mismatch test computes its own lock in-process via `compute_plugin_tree_digest`; the `lock-update` CLI helper is named in arch E17 + High-level-impl risk #3 but is **not assigned to any story's Features-delivered list** — surfaced as an orphan deliverable (see Notes).
- **End-to-end remediation against `example--noop--noop`** — the plugin's point is the contract surface, not a real workflow.
- **Bench-testing the bake-test runtime** — bake-tests are not benchmarked; AC-15 caps it at 5 s by inspection.
- **Phase 6.5's `TaskClassRegistry` bake-testing** — different registry, different ADR.

## Notes for the implementer

- **The synthetic plugin is the bake-test, not a production plugin.** Never put it under `plugins/`. It is registered into the test registry directly via `register_plugin(plugin, registry=...)` — the `tests/fixtures/plugins/universal_fallback_fixture.py::make_universal_fallback` precedent. Read that fixture first; mirror its shape (module docstring, `@dataclass`, `model_construct` if a validator rejects the slug, boundary newtype-lift).
- **Use a fresh `PluginRegistry()`, never `default_registry`** (ADR-0002). AC-13 enforces no leak into the production singleton.
- **The loader is single-root, single-lock, and returns a `Result`.** `load_plugins(plugin_root: Path, lock_path: Path, *, registry=None, verifier=None) -> Result[LoadReport, PluginRejected]`. There is no `roots=` plural form. Always assert `.is_ok()` — fail loud (Rule 12).
- **The recipe surface is NOT on the `Plugin` Protocol.** The kernel `Plugin` has exactly four members (`manifest`, `build_subgraph`, `adapters`, `transforms`). There is no `plugin.recipe_registry`. Reach the noop recipes via `plugin.transforms()` (the `RecipeEngine` map) and via the fixture-owned `RecipeRegistry`. This is by design (ADR-0004 — task-specific knowledge off the kernel).
- **The four ADR-0032 adapter Protocols are not shipped.** The as-built kernel `Adapter` Protocol has one member, `primitive: PrimitiveName`. `DepGraphAdapter` / `ImportGraphAdapter` / `ScipAdapter` / `TestInventoryAdapter` exist only as ADR-0032 prose; `confidence()` per ADR-0032 is a `float`, not a sum type; `AdapterConfidence` is `Trusted | Degraded | Unavailable` with **no `High`**. The noop adapters conform to the single-member `Adapter` Protocol. If S7-02 (which ships the npm adapters) has by implementation time grown the `Adapter` Protocol with a richer method surface, **match the as-built `Adapter` Protocol and S7-02's npm-adapter file organization** (Rule 11) — and record the contract-surface decision in the attempt log.
- **Tagged unions are constructed by their variant classes, directly.** `Skipped(...)`, `Applies(...)`, `Advance(...)` — never `RecipeOutcome.Skipped(...)` / `NodeTransition.Advance(...)`. This is the exact defect S7-01, S7-02 (CN-4), and S7-03 (CN-7) were all corrected for. `Skipped.reason` is a `SkipReason = Literal["plugin_disabled", "registry_skipped"]` — there is no `NOOP`. `Applies.plan` is an `ApplicationPlan` — there is no `NoopPlan`. Confirm every variant's field set against `codegenie/transforms/outcomes.py` before writing the fixture.
- **`@register_recipe` IS a decorator; `register_plugin` is a function call.** Do not collapse the two. `register_recipe(plugin_id, *, registry=None)` has no `precedence` kwarg — `precedence` is a class attribute on the recipe class.
- **S6-03 is not yet built.** `NoopSubgraphNode` implements the S6-03 `SubgraphNode` Protocol and `run(...)` consumes a `SubgraphState`. Neither is on disk yet. Run this story *after* S6-03 ships and reconcile `noop_node.py` against the as-built `SubgraphNode.run` signature; if `SubgraphState` is fenced out of plugin folders (the S7-03 CN-3 precedent), annotate it `Any` under `if TYPE_CHECKING:`. Import `Advance` from `codegenie.transforms` — NOT `codegenie.transforms.transitions` (no such module).
- **The mismatch test's primary assertion is in-process.** The integrity check is reachable at the pure `load_plugins` boundary returning `Err(IntegrityMismatch)` — fast, deterministic, no subprocess, no fixture repo, no `npm`. A positive control (the un-mutated tree loads `Ok`) is mandatory: without it the test cannot distinguish "rejected because of the mutation" from "rejected for setup noise". The exit-4 mapping is a separate, in-process `exit_code_for_rejection` assertion. The subprocess arm is conditional (AC-18).
- **`codegenie plugins lock-update` is an orphan deliverable.** It is named in arch E17 and High-level-impl risk #3 as a regen helper but assigned to no story. This story does not need it (the mismatch test computes the lock in-process). Flag it to the architect / story-writer so a story owns it before Phase 7.
- **The bake test runs offline and fast** (AC-15, <5 s). Keep `test_three_plugin_contract.py` 100% in-process. Speed matters: it is the smoke test future contributors run first.
- **Phase 7's distroless plugin is the 4th consumer of the bake test.** AC-11 makes "adding it is one tuple entry, zero edits to the walker" an observable contract. If Phase 7 forces edits to `_plugin_contract_walker.py`, the extension-by-addition claim is broken and this story did not deliver. Build the walker with that future in mind.
- **Surface gaps loudly** (per `§Open questions deferred to implementation`). The loader import-prefix collision was one such gap surfaced during validation. If implementation finds another (a Protocol method no production plugin exercises; a TCCM namespace the resolver rejects), record it in the commit message + attempt log and consider whether it warrants an ADR amendment.
