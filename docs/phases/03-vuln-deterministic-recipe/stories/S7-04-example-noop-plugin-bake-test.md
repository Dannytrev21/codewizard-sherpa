# Story S7-04 — Synthetic `example--noop--*` plugin + 3-plugin contract bake test + `PLUGINS.lock` mismatch test

**Step:** Step 7 — First production plugin, universal HITL fallback plugin, synthetic third plugin
**Status:** Ready
**Effort:** M
**Depends on:** S7-01 (the vuln plugin must be registered), S7-02 (the vuln plugin's recipes + adapters must be wired), S7-03 (the universal fallback must be registered)
**ADRs honored:** [ADR-0002](../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md) (the synthetic plugin registers via the same `@register_plugin(...)` machinery as the production plugins — *bake-testing* the kernel's "extension by addition" claim), [ADR-0003](../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md) (the bake test exercises both `ConcreteResolution` and `UniversalFallbackResolution` paths against the three-plugin universe), [ADR-0004](../ADRs/0004-plugin-private-capabilities-via-tccm.md) (synthetic plugin declares a `provides.example_capabilities` namespace — proves the TCCM-as-extension mechanism is generic, not vuln-specific), [ADR-0009](../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md) (synthetic plugin's `transforms()` exposes a third `RecipeEngine` impl — the Protocol is now bake-tested against 3 engines: `NpmLockfileRecipeEngine` + `OpenRewriteRecipeEngine` + `NoopRecipeEngine`), [ADR-0011](../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) (**the `PLUGINS.lock` mismatch test in this story is the integrity-check ADR's headline regression**)

## Context

The roadmap exit criterion *"plugin contract bake-tested against ≥3 plugins (extension-by-addition test for Phase 7)"* is satisfied here. Phase 7 introduces `migration-chainguard-distroless` as the second real task class under the "zero edits to existing plugins" rule. Bake-testing the kernel contract against three plugins **before** Phase 7 ships proves that:

1. The kernel `Plugin` Protocol's four methods (`manifest`, `build_subgraph`, `adapters`, `transforms`) — locked by ADR-0004 — are sufficient for plugins with wildly different shapes (production vuln-remediation, universal HITL fallback, synthetic noop).
2. The `PluginRegistry` resolver's `(specificity desc, precedence desc, name asc)` ordering produces deterministic results across a non-trivial plugin universe.
3. The per-plugin `RecipeRegistry` from S5-01 generalizes — three plugins each carrying their own recipe registry, no cross-contamination.
4. The four ADR-0032 adapter Protocols (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`) admit at least two implementations each (npm-real + noop-fake), so the BundleBuilder's per-primitive dispatch is not coupled to npm-specific assumptions.
5. **The `PLUGINS.lock` integrity-check actually exits 4 when a plugin file is mutated post-lock** — regression-testing ADR-0011's honest framing.

The synthetic plugin lives under `tests/fixtures/plugins/example--noop--*/` (NOT under `plugins/` — it's test scaffolding, not production), and is loaded only by the bake-test's plugin-root fixture so it doesn't pollute the production registry. Its scope is `example--noop--noop` (three `Concrete` dims, specificity 3, but `task_class == "example"` matches no real workflow scope). It exercises **every** Protocol surface:

- `Plugin` — full four-method surface.
- `Adapter` — one implementation of each ADR-0032 Protocol (`NoopDepGraphAdapter`, `NoopImportGraphAdapter`, `NoopScipAdapter`, `NoopTestInventoryAdapter`), each returning empty results with `AdapterConfidence.High`.
- `RecipeEngine` — `NoopRecipeEngine` that always returns `RecipeOutcome.Skipped(reason=NOOP)`.
- `RecipeProtocol` — `NoopRecipe` whose `applies(...)` always returns `Applies(NoopPlan)`.
- `SubgraphNode` — one node returning `Advance(state)` (proving the orchestrator can drive a non-shortcircuit transition through a plugin's subgraph).

Per `phase-arch-design.md §"Open questions deferred to implementation"`: *"`example--noop--*` exact contract-surface coverage. Synthesis says 'exercises every contract surface.' Implementation may discover gaps."* If this story finds gaps (e.g., a Protocol method no production plugin happens to exercise), extending the synthetic plugin to cover them IS in scope; surfacing them as ADR amendments (e.g., a new method becomes mandatory) is also in scope.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals` G3 ("Plugin contract bake-tested against 3 plugins. Two production + one synthetic. `tests/integration/test_three_plugin_contract.py` resolves all three and exercises every contract surface").
  - `../phase-arch-design.md §Departures from all three inputs #3` ("Synthetic `example--noop--*` plugin under `tests/fixtures/plugins/`").
  - `../phase-arch-design.md §Tradeoffs ledger` row "Synthetic `example--noop--*` plugin in tests" — "~400 LOC of fixture code; Plugin contract bake-tested against 3 plugins; Phase 7's first real consumer doesn't discover Protocol gaps."
  - `../phase-arch-design.md §Component design C2` (the four Protocol methods the bake test must exercise).
  - `../phase-arch-design.md §Edge cases E17` (PLUGINS.lock SHA mismatch — exit 4 with `PluginRejected(integrity_mismatch)`).
  - `../phase-arch-design.md §Scenarios D` (loader walks `plugins/*/plugin.yaml` + verifies `PLUGINS.lock` sha256).
- **Phase ADRs:**
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — the bake test loads against a fresh `PluginRegistry()` instance (NOT `default_registry`), per the test-isolation pattern this ADR established.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — the integrity-check ADR; the mutate-a-file-post-lock test in this story is the ADR's headline consequence.
  - `../ADRs/0004-plugin-private-capabilities-via-tccm.md` (P3-005: synthetic plugin under `tests/fixtures/plugins/` declares `provides.example_capabilities`).
  - `../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md` — the synthetic adds a third `RecipeEngine` impl, deepening the bake.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — the umbrella contract this story is bake-testing.
  - `../../../production/adrs/0032-language-search-adapters.md` — the four adapter Protocols the noop adapters implement.
- **Source dependencies:**
  - The two production plugins from S7-01 + S7-02 + S7-03 must already be on disk.
  - `src/codegenie/plugins/loader.py` from S2-03 — the loader the bake test exercises with a `--plugins-root` (or env var) pointing at the union of production + fixture plugins.
- **High-level impl:** `../High-level-impl.md §Step 7` Done criteria items 1, 4, 5.

## Goal

Land the synthetic `example--noop--noop` plugin under `tests/fixtures/plugins/` exercising every Protocol surface, plus the integration test `tests/integration/test_three_plugin_contract.py` that loads all three plugins and walks every contract surface, plus the regression test `tests/integration/test_plugins_lock_mismatch.py` that proves a post-lock file mutation produces `PluginRejected(integrity_mismatch)` with exit code 4.

## Acceptance criteria

- [ ] `tests/fixtures/plugins/example--noop--noop/` contains: `plugin.yaml`, `tccm.yaml`, `api.py`, `recipes/__init__.py` + `recipes/noop_recipe.py`, `adapters/__init__.py` + four adapter files (one per ADR-0032 Protocol), `subgraph/__init__.py` + `subgraph/noop_node.py`, and a `PLUGINS.lock` file rooted under the fixture dir (NOT the production `plugins/PLUGINS.lock`).
- [ ] The synthetic plugin's `manifest.scope.specificity() == 3` (`example--noop--noop` is three Concrete dims) and its `precedence: 10` (low — never accidentally beats vuln plugin on `(vulnerability-remediation, node, npm)`; this is defense-in-depth — the scope doesn't match anyway).
- [ ] The synthetic plugin declares `provides.example_capabilities: {example_parser: api:NoopParser}` in its TCCM, proving the TCCM-as-extension mechanism (ADR-0004) admits a non-vuln capability namespace.
- [ ] All four `NoopAdapter` classes implement the corresponding ADR-0032 Protocol (`Noop*Adapter` for each of `DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`); each returns empty results and `AdapterConfidence.High` from `confidence()`.
- [ ] `NoopRecipeEngine` implements `RecipeEngine` and returns `RecipeOutcome.Skipped(reason=NOOP)`; `NoopRecipe` implements `RecipeProtocol` and its `applies(plan)` always returns `Applies(NoopPlan)`; the recipe is registered via `@register_recipe(PluginId("example--noop--noop"))` against the plugin's `RecipeRegistry`.
- [ ] `NoopSubgraphNode` implements `SubgraphNode` and returns `Advance(state)` (exercising the non-`ShortCircuit` `NodeTransition` branch the universal plugin can't exercise).
- [ ] `tests/integration/test_three_plugin_contract.py` loads all three plugins via a `PluginRegistry()` instance fixture (NOT `default_registry`), pointing the loader at the production `plugins/` AND `tests/fixtures/plugins/` directories. The test calls every Protocol method on every plugin and asserts contract conformance:
  - `Plugin.manifest` returns a valid `PluginManifest`.
  - `Plugin.build_subgraph(registry)` returns a `PluginSubgraph` whose nodes implement `SubgraphNode`.
  - `Plugin.adapters()` returns `dict[PrimitiveName, Adapter]` with each value structurally conforming to the right ADR-0032 Protocol.
  - `Plugin.transforms()` returns `dict[TransformKind, RecipeEngine]` with each value structurally conforming to `RecipeEngine`.
  - The plugin's `RecipeRegistry.iter(plan)` yields recipes whose `applies(plan)` returns an `Applicability` variant.
  - The universal fallback resolution path is exercised by passing a scope no plugin matches (e.g., `(vulnerability-remediation, rust, cargo)` matches the universal only).
- [ ] **`tests/integration/test_plugins_lock_mismatch.py`** is the regression test for ADR-0011's integrity claim. It:
  1. Sets up a fresh `PluginRegistry()` + a tempdir copy of all three plugins + a freshly-computed `PLUGINS.lock`.
  2. Mutates **one** byte of one file in the npm plugin's tree (e.g., adds a comment to `api.py`) WITHOUT regenerating `PLUGINS.lock`.
  3. Invokes the loader against the mutated tree.
  4. Asserts: the loader raises `PluginRejected(integrity_mismatch)`; the CLI process exit code is 4; the error message includes both the expected and observed SHA so the operator can diff.
- [ ] The bake test executes in well under 5 seconds (Phase 3 budget; bake-tests are not benchmarked but should be cheap).
- [ ] No LLM SDK import added under `tests/fixtures/plugins/example--noop--noop/` (verified via `make fence`).
- [ ] The red test from §TDD plan exists, was committed at red, and is now green.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict` clean on touched files; existing tests (S7-01, S7-02, S7-03) still green.

## Implementation outline

1. **Create the synthetic plugin tree.**
   ```
   tests/fixtures/plugins/example--noop--noop/
     plugin.yaml                 # scope: example--noop--noop; precedence: 10
     tccm.yaml                   # provides.example_capabilities
     api.py                      # _NoopPlugin + register_plugin(plugin, registry=...)
     recipes/
       __init__.py
       noop_recipe.py            # NoopRecipe + NoopRecipeEngine
     adapters/
       __init__.py
       noop_dep_graph.py         # NoopDepGraphAdapter
       noop_import_graph.py      # NoopImportGraphAdapter
       noop_scip.py              # NoopScipAdapter
       noop_test_inventory.py    # NoopTestInventoryAdapter
     subgraph/
       __init__.py
       noop_node.py              # NoopSubgraphNode returning Advance(state)
   tests/fixtures/plugins/example--noop--noop.PLUGINS.lock   # OR placed alongside the dir
   ```
2. **`api.py` uses `register_plugin(plugin, registry=...)` keyword form.** The synthetic plugin is registered against the *test-fixture* `PluginRegistry()` instance, NOT `default_registry`. This is ADR-0002's test-isolation pattern. If the loader's API doesn't admit `registry=` injection at load time, surface as a gap — the test must not pollute the production registry.
3. **Adapters are <10 LOC each.**
   ```python
   class NoopDepGraphAdapter:
       def consumers(self, package): return []
       def confidence(self): return AdapterConfidence.High()
   ```
   Four files; four classes; total ~50 LOC.
4. **`NoopRecipeEngine`** returns `RecipeOutcome.Skipped(reason=NOOP)` from every `apply(...)`. **`NoopRecipe`** is registered via `@register_recipe(PluginId("example--noop--noop"), precedence=100)`; `applies(plan)` is `Applies(NoopPlan())`; `apply(plan, ctx)` returns the engine's `Skipped`.
5. **`NoopSubgraphNode.run(state)`** returns `Advance(state)` — this is the **only** node in Phase 3 that returns `Advance` from a plugin's subgraph (the orchestrator's default 5-node subgraph also returns `Advance` from inter-stage transitions, but inside a *plugin's* `build_subgraph(...)`, the noop is the only `Advance`-returner). This exercises S6-03's `NodeTransition` Advance variant from plugin-supplied code.
6. **`tccm.yaml`** declares `provides.example_capabilities: {example_parser: tests.fixtures.plugins.example__noop__noop.api:NoopParser}` (or whichever module-path the loader's slug-to-module mapping resolves to). The mere act of the loader resolving this import path on plugin load IS the test that ADR-0004's TCCM-as-extension mechanism handles a non-vuln namespace.
7. **`PLUGINS.lock`** — local to the fixture; computed via the same algorithm as the production one. Mismatch test mutates a file under the fixture tree, NOT the production tree.
8. **Bake test (`test_three_plugin_contract.py`)** — see TDD plan; the test fixture creates a fresh `PluginRegistry()`, points the loader at `[production plugins/, tests/fixtures/plugins/]`, walks every Protocol method on every plugin, asserts conformance.
9. **Mismatch test (`test_plugins_lock_mismatch.py`)** — see TDD plan.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/integration/test_three_plugin_contract.py`

```python
# tests/integration/test_three_plugin_contract.py
import pytest

from codegenie.plugins.registry import PluginRegistry
from codegenie.plugins.loader import load_plugins
from codegenie.plugins.resolution import ConcreteResolution, UniversalFallbackResolution
from codegenie.plugins.scope import PluginScope
from codegenie.types.identifiers import PluginId, PrimitiveName


@pytest.fixture
def three_plugin_registry(tmp_path):
    """Fresh registry with the three plugins (vuln + universal + noop) loaded."""
    registry = PluginRegistry()
    load_plugins(
        registry,
        roots=["plugins", "tests/fixtures/plugins/example--noop--noop"],
    )
    return registry


def test_three_plugins_registered(three_plugin_registry):
    names = {p.manifest.name for p in three_plugin_registry.all()}
    assert PluginId("vulnerability-remediation--node--npm") in names
    assert PluginId("universal--*--*") in names
    assert PluginId("example--noop--noop") in names


def test_concrete_resolution_for_npm_scope(three_plugin_registry):
    scope = PluginScope.parse("vulnerability-remediation--node--npm").unwrap()
    r = three_plugin_registry.resolve(scope)
    assert isinstance(r, ConcreteResolution)
    assert r.plugin.manifest.name == PluginId("vulnerability-remediation--node--npm")


def test_universal_resolution_for_unmatched_scope(three_plugin_registry):
    scope = PluginScope.parse("vulnerability-remediation--rust--cargo").unwrap()
    r = three_plugin_registry.resolve(scope)
    assert isinstance(r, UniversalFallbackResolution)


def test_concrete_resolution_for_example_scope(three_plugin_registry):
    scope = PluginScope.parse("example--noop--noop").unwrap()
    r = three_plugin_registry.resolve(scope)
    assert isinstance(r, ConcreteResolution)
    assert r.plugin.manifest.name == PluginId("example--noop--noop")


@pytest.mark.parametrize("plugin_name", [
    "vulnerability-remediation--node--npm",
    "universal--*--*",
    "example--noop--noop",
])
def test_plugin_exposes_four_kernel_methods(three_plugin_registry, plugin_name):
    plugin = three_plugin_registry.get(PluginId(plugin_name))
    # Bake-test the four kernel methods (ADR-0004 locked the contract at these four).
    assert plugin.manifest is not None
    assert plugin.build_subgraph(three_plugin_registry) is not None
    assert isinstance(plugin.adapters(), dict)
    assert isinstance(plugin.transforms(), dict)


def test_noop_plugin_exercises_advance_node_transition(three_plugin_registry):
    """The noop plugin is the only one whose subgraph returns Advance — bake-tests
    the NodeTransition.Advance variant from plugin-supplied code (S6-03)."""
    from codegenie.transforms.subgraph_state import SubgraphState
    from codegenie.transforms.transitions import Advance
    plugin = three_plugin_registry.get(PluginId("example--noop--noop"))
    subgraph = plugin.build_subgraph(three_plugin_registry)
    node = list(subgraph.nodes)[0]
    state = SubgraphState.bootstrap_for_testing()
    transition = asyncio.run(node.run(state))
    assert isinstance(transition, Advance)


def test_noop_plugin_recipe_registry_iter_yields_applies(three_plugin_registry):
    from codegenie.transforms.applicability import Applies
    plugin = three_plugin_registry.get(PluginId("example--noop--noop"))
    plan = ...   # construct NoopPlan
    yielded = list(plugin.recipe_registry.iter(plan))
    assert yielded
    assert isinstance(yielded[0].applicability, Applies)
```

Test file path: `tests/integration/test_plugins_lock_mismatch.py`

```python
# tests/integration/test_plugins_lock_mismatch.py
import shutil
import subprocess
from pathlib import Path

import pytest

from codegenie.plugins.errors import PluginRejected


def test_post_lock_file_mutation_raises_integrity_mismatch_with_exit_4(tmp_path):
    """ADR-0011: PLUGINS.lock is the integrity check. Mutate a file post-lock;
    loader must reject with PluginRejected(integrity_mismatch) and exit 4.
    This is the headline regression for the integrity-check claim."""
    # Stage: copy the three plugins + a fresh PLUGINS.lock to tmp_path.
    plugins_dir = tmp_path / "plugins"
    shutil.copytree("plugins", plugins_dir)
    shutil.copytree("tests/fixtures/plugins/example--noop--noop",
                    plugins_dir / "example--noop--noop")
    # Generate a fresh PLUGINS.lock for this snapshot.
    subprocess.run(
        ["codegenie", "plugins", "lock-update", "--root", str(plugins_dir)],
        check=True,
    )
    # Mutate: append a comment to api.py in the npm plugin (one byte changes the sha).
    api_py = plugins_dir / "vulnerability-remediation--node--npm" / "api.py"
    api_py.write_text(api_py.read_text() + "\n# tampered\n")
    # Act: invoke the loader against the mutated tree.
    result = subprocess.run(
        ["codegenie", "remediate",
         "./tests/fixtures/repos/express-cve-2024-21501",
         "--cve", "CVE-2024-21501",
         "--plugins-root", str(plugins_dir)],
        capture_output=True,
    )
    # Assert: exit 4, error mentions integrity_mismatch + both shas.
    assert result.returncode == 4
    assert b"PluginRejected" in result.stderr
    assert b"integrity_mismatch" in result.stderr.lower()
```

Run; confirm `ModuleNotFoundError` on the noop plugin imports and `KeyError` on `three_plugin_registry.get(PluginId("example--noop--noop"))`; commit the red.

### Green

Land the noop plugin tree + the test infrastructure. Smallest shape:
- Each noop adapter is ~5 LOC.
- `NoopRecipeEngine` is ~10 LOC.
- `NoopSubgraphNode` is ~5 LOC.
- `api.py` is ~15 LOC (the typical plugin shape).
- `tccm.yaml` is ~5 lines.
- `plugin.yaml` is ~10 lines.
Total: ~80 LOC of fixture + ~100 LOC of bake-test infrastructure. (The "400 LOC" estimate in `phase-arch-design.md §Tradeoffs` is the budget ceiling, not the floor.)

### Refactor

- Move the noop adapters to one file (`noop_adapters.py`) if the per-file separation feels artificial; the bake-test loop doesn't care.
- Document each Protocol surface the synthetic plugin exercises in the plugin's `README.md` so the next person reading `tests/fixtures/plugins/example--noop--noop/` knows what this is for.
- Confirm `mypy --strict` clean. All four noop adapter classes are structurally compatible with the corresponding `Protocol`; no `Adapter` ABC inheritance.
- The mismatch test should clean up `tmp_path` automatically via pytest; confirm no `.codegenie/` artifacts leak from the subprocess into the host repo.
- Consider promoting the bake-test plugin walker into a reusable utility (`tests/integration/_plugin_contract_walker.py`) so Phase 7's first real distroless plugin gets bake-test coverage with one new parametrize entry, not a new test file.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/plugins/example--noop--noop/plugin.yaml` | New — manifest with `example--noop--noop` scope, precedence 10 |
| `tests/fixtures/plugins/example--noop--noop/tccm.yaml` | New — declares `provides.example_capabilities` namespace |
| `tests/fixtures/plugins/example--noop--noop/api.py` | New — `_NoopPlugin` + `register_plugin(plugin, registry=...)` (test-injection form) |
| `tests/fixtures/plugins/example--noop--noop/recipes/__init__.py` | New |
| `tests/fixtures/plugins/example--noop--noop/recipes/noop_recipe.py` | New — `NoopRecipe` + `NoopRecipeEngine` |
| `tests/fixtures/plugins/example--noop--noop/adapters/__init__.py` | New |
| `tests/fixtures/plugins/example--noop--noop/adapters/noop_dep_graph.py` | New — `NoopDepGraphAdapter` |
| `tests/fixtures/plugins/example--noop--noop/adapters/noop_import_graph.py` | New — `NoopImportGraphAdapter` |
| `tests/fixtures/plugins/example--noop--noop/adapters/noop_scip.py` | New — `NoopScipAdapter` |
| `tests/fixtures/plugins/example--noop--noop/adapters/noop_test_inventory.py` | New — `NoopTestInventoryAdapter` |
| `tests/fixtures/plugins/example--noop--noop/subgraph/__init__.py` | New |
| `tests/fixtures/plugins/example--noop--noop/subgraph/noop_node.py` | New — `NoopSubgraphNode` returning `Advance(state)` |
| `tests/integration/test_three_plugin_contract.py` | New — the bake test; resolves all three plugins, walks every Protocol method |
| `tests/integration/test_plugins_lock_mismatch.py` | New — **the ADR-0011 regression test**; mutate-a-file-post-lock → exit 4 |
| `tests/fixtures/plugins/example--noop--noop/README.md` | New (refactor pass) — documents the bake-test contract surface coverage |

## Out of scope

- **Adding the synthetic plugin to the production `plugins/PLUGINS.lock`** — the synthetic lives under `tests/fixtures/plugins/`; it does NOT belong in the production lockfile. Mixing them would surface as a noisy CI diff every time the fixture changes; keep them separate.
- **End-to-end remediation against `example--noop--noop`** — the plugin's whole point is exercising the contract surface, not driving a real workflow. A noop recipe returning `Skipped(NOOP)` is the right shape.
- **Bench-testing the bake-test runtime** — bake-tests are not benchmarked. If the test exceeds 5 s, profile and trim; do not add a bench harness for it.
- **Bake-testing the orchestrator's `_validate_stage6` seam against the noop plugin** — that's the orchestrator's surface (S6-04). The noop plugin's `Skipped(NOOP)` doesn't produce a `Transform`, so stage 6 doesn't run; the bake test stops at the recipe-dispatch boundary.
- **Phase 6.5's `TaskClassRegistry` bake-testing** — different registry, different ADR (Phase 6.5's `task_class_registry.py`); not in scope here.
- **Documenting which Protocol methods are bake-tested vs. which are not** in a fence-CI test — that's Phase 7+ territory once the contract surface stabilizes through real Phase 7 consumption.

## Notes for the implementer

- **The synthetic plugin is the bake-test, not a production plugin.** Do not, under any circumstances, put it under `plugins/`. The directory `tests/fixtures/plugins/` IS the contract; the loader respects `--plugins-root` (or `CODEGENIE_PLUGINS_ROOT`) overrides; production loads only `plugins/`.
- **Use a fresh `PluginRegistry()` in the bake test, NOT `default_registry`.** ADR-0002's test-isolation pattern is the precedent: `registry = PluginRegistry(); load_plugins(registry, roots=[...])`. The production `default_registry` is already polluted by the production plugins' `register_plugin(...)` calls; the bake test must work against a clean slate.
- **The PLUGINS.lock mismatch test is the headline regression for ADR-0011.** If you can write a green test where mutating a plugin file does NOT cause exit 4, the loader is broken. Edge case E17 documents the contract; the test enforces it. Make the test fail with an unfixed loader, then fix the loader (most likely S2-03 already shipped this; verify by running the test against the production loader code unmodified).
- **`Advance(state)` is the noop node's signature contribution.** The universal plugin returns `ShortCircuit`; the production npm plugin's subgraph stages return `Advance` between stages (but those are in the *orchestrator's* default subgraph, not the *plugin's* `build_subgraph`). The noop plugin is the first place a *plugin* returns `Advance` from `build_subgraph(...)` — exercising the S6-03 contract end-to-end.
- **The `provides.example_capabilities` namespace is the proof that ADR-0004 generalizes.** If the loader rejects this YAML because "example_capabilities is not a known namespace," that's a regression — the kernel knows about no namespace; the namespace is the plugin's declaration. The vuln plugin happens to declare `vuln_index_capabilities`; the noop plugin declares `example_capabilities`; Phase 7's distroless will declare `dockerfile_capabilities`. The kernel sees opaque strings.
- **Don't pre-emptively bake-test things you can't prove are stable.** The four kernel methods are stable per ADR-0004. The four ADR-0032 adapter Protocols are stable per the production ADR. `RecipeProtocol`/`RecipeEngine`/`SubgraphNode` are stable per S5-01/S6-03. Anything beyond those (e.g., specific event payload shapes, the orchestrator's stage method signatures) is NOT contract surface for the bake test — that's S6-06's Phase-5-contract-snapshot territory.
- **The `~400 LOC` estimate in `phase-arch-design.md §Tradeoffs` is generous.** A minimal noop plugin lands in ~80 LOC of source + ~100 LOC of test. If you're approaching 400 LOC, you're probably re-implementing a recipe engine or adapter beyond noop — pull back.
- **Surface gaps loudly.** Per `§Open questions deferred to implementation`: "Implementation may discover gaps (e.g., a `provides`/`requires` edge case not exercised) and extend." If you find a Protocol method that no production plugin happens to call and the noop plugin would be the only one exercising it, that's a real concern — flag it in the story's commit message and consider whether the method belongs on the kernel.
- **The bake test runs offline.** No `npm install`, no network. Noop adapters return empty results; noop recipe returns `Skipped`; the test asserts contract conformance only. Speed matters: the bake test is the smoke test future contributors run first; keep it under 5 seconds.
- **Phase 7's distroless plugin will be the second real consumer of the bake test.** When Phase 7 ships, adding `migration-chainguard-distroless--node--npm` to the bake-test `parametrize` list should be a one-line change. If it isn't — if Phase 7 forces edits elsewhere in this test — the bake test's "extension by addition" claim is broken and this story did not deliver. Build with that future in mind.
