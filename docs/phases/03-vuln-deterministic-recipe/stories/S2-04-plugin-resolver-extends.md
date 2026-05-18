# Story S2-04 — Plugin resolver: `(specificity, precedence, name)` ordering + `extends` walker + `UniversalFallbackResolution`

**Step:** Step 2 — Plugin Registry kernel, manifest schema, loader, resolver
**Status:** Ready
**Effort:** M
**Depends on:** S2-02, S2-03
**ADRs honored:** ADR-0002, ADR-0003, ADR-0010, production ADR-0031, production ADR-0009

## Context

This is Step 2's payoff story: with the kernel (S2-01), the manifest model (S2-02), and the loader (S2-03) in place, the resolver implements the **ADR-0003 algorithm** that maps a `PluginScope` to a typed `PluginResolution`. Two structural commitments are load-bearing:

1. **Universal fallback is a registered plugin, not a code path.** When no concrete plugin matches a scope, the resolver returns `UniversalFallbackResolution`, narrowed from the head of the sorted candidate list. The universal plugin (`universal--*--*`) is loaded by the same machinery as any other plugin (ADR-0031 §No-match fallback). The kernel has **no** `if plugin.id == "universal--*--*":` branch.
2. **The return type is a tagged union, not `Plugin | None`.** `PluginResolution = ConcreteResolution | UniversalFallbackResolution`; every dispatch site `match`es with `assert_never`. This is the structural enforcement of production ADR-0009 (humans always merge): the "no concrete match" path is type-impossible to silently drop.

The `extends` walker composes TCCM and adapter maps left-to-right (later wins per ADR-0031 §Inheritance and override). Cycle detection caps at depth 4 with a visited-set check; `PluginExtendsCycle(chain)` is raised on cycle and `PluginRejected(reason="extends_depth_exceeded", chain=...)` on over-depth.

A Hypothesis property test is non-optional here: for any randomly-generated set of `PluginScope`s registered alongside a `universal--*--*` fallback, `resolver.resolve(scope)` is total — it returns `ConcreteResolution` whose `plugin.scope.matches(scope)` is True, OR returns `UniversalFallbackResolution`. It never raises (cycle is a startup-time concern, not a per-resolve concern), never returns `None`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C2` — `resolve()` algorithm; `(specificity desc, precedence desc, name asc)` ordering; cycle check; max depth 4.
  - `../phase-arch-design.md §Component design C3` — `PluginScope` + `Concrete | Wildcard` sum type from S1-02; `specificity() = count of Concrete dims`.
  - `../phase-arch-design.md §Scenarios D` — concrete walkthrough: vuln-remediation--node--yarn-berry resolved against a `(vuln, javascript, yarn-berry)` workflow walks `extends: [vulnerability-remediation--node--*]`, composes TCCM left-to-right.
  - `../phase-arch-design.md §Edge case E2, E9, E10` — fallback path; ambiguous ties; deep `extends` chains.
  - `../phase-arch-design.md §Testing strategy — Property tests` — the determinism + totality property.
- **Phase ADRs:**
  - `../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md` — ADR-0003 — Option C is the decision; algorithm steps 1–4 are mandatory; universal fallback is a registered plugin under `plugins/universal--*--*/`, **never** a hardcoded code path.
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — ADR-0002 — `resolve` is on the registry instance; exit code 4 on cycle.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — ADR-0010 — `PluginScope` is a sum type, not `Literal["*"]`; `PluginId` newtype.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` §Discovery and resolution + §Inheritance and override — the canonical algorithm; later-wins-on-collision for `extends`.
  - `../../../production/adrs/0009-humans-always-merge.md` — the invariant the typed `UniversalFallbackResolution` enforces statically.
- **Existing code:**
  - `src/codegenie/plugins/registry.py` (S2-01) — `PluginRegistry.resolve(scope)` is the method this story implements; replace the `NotImplementedError`.
  - `src/codegenie/plugins/scope.py` (S1-02) — `PluginScope`, `Concrete`, `Wildcard`, `matches`, `specificity`.
  - `src/codegenie/plugins/manifest.py` (S2-02) — `PluginManifest.extends`, `PluginManifest.precedence`.
  - `src/codegenie/plugins/errors.py` — `PluginExtendsCycle` (S2-01 placeholder; populated here).
  - `src/codegenie/result.py` — `Result` is **not** used on `resolve` (resolve is total; no `Result` needed). `Result` is used by the cycle pre-check helper if implemented (optional).

## Goal

Implement `PluginRegistry.resolve(scope: PluginScope) -> PluginResolution` and the `extends` walker that composes TCCM and adapters left-to-right with cycle detection (max depth 4). Ship the discriminated `PluginResolution` Pydantic union and a Hypothesis property test that proves the totality invariant.

## Acceptance criteria

- [ ] `src/codegenie/plugins/resolver.py` exists with: `PluginResolution` Pydantic discriminated union (`ConcreteResolution | UniversalFallbackResolution`); `compose_extends_chain(plugin, registry, *, max_depth=4) -> ConcreteResolution`; `resolve(registry, scope) -> PluginResolution`. `PluginRegistry.resolve(scope)` delegates here (no `NotImplementedError`).
- [ ] `ConcreteResolution`: `kind: Literal["concrete"] = "concrete"`, `plugin: Plugin`, `extends_chain: list[Plugin]` (root → leaf, leaf is `plugin` itself), `composed_tccm: ComposedTccm`, `composed_adapters: dict[PrimitiveName, Adapter]`. Composition is **left-to-right merge with later-wins-on-collision** (production ADR-0031). For Step 2 `composed_tccm` may be a minimal placeholder until Step 3's TCCM model lands — see Out of scope.
- [ ] `UniversalFallbackResolution`: `kind: Literal["universal_fallback"] = "universal_fallback"`, `reason: Literal["no_concrete_match"]`, `candidates_considered: list[PluginId]` (the filtered-but-not-chosen concrete plugins, sanitized — no repo paths).
- [ ] Resolution algorithm (per ADR-0003):
  1. Filter `registry.all()` by `plugin.scope.matches(scope)` (the S1-02 `matches` method).
  2. Sort by `(plugin.scope.specificity() desc, plugin.manifest.precedence desc, plugin.manifest.name asc)`. Sort is deterministic on ties.
  3. If the head plugin's name is `universal--*--*`, return `UniversalFallbackResolution(reason="no_concrete_match", candidates_considered=[p.manifest.name for p in tail])`.
  4. Else `compose_extends_chain(head, registry)` → `ConcreteResolution`.
- [ ] `compose_extends_chain` walks `plugin.manifest.extends` left-to-right, recursing depth-first; visited-set tracks the in-progress chain; cycle → `raise PluginExtendsCycle(chain=[...])`; depth > 4 → `raise PluginRejected(reason="extends_depth_exceeded", chain=[...])`. Composition merges later-wins-on-collision per ADR-0031.
- [ ] If `registry.all()` is empty OR no plugin (concrete or universal) matches, the resolver raises `PluginRegistryCorrupted` (the universal fallback MUST be registered; missing universal is a startup-corruption case, not a per-resolve concern — emit a `PluginRegistryCorrupted` spanning event at the call site too, but the *exception type* is what this story commits to).
- [ ] `tests/unit/plugins/test_resolver.py` covers: exact match beats wildcard match (specificity ordering); equal-specificity plugins broken by `precedence`; equal-precedence broken by name (alphabetical); `extends` chain of depth 4 composes correctly; depth 5 raises `PluginRejected(extends_depth_exceeded)`; `A extends B extends A` cycle raises `PluginExtendsCycle(chain=["A","B","A"])`; no-concrete-match with universal registered returns `UniversalFallbackResolution`; no universal registered raises `PluginRegistryCorrupted`.
- [ ] `tests/unit/plugins/test_resolver_property.py` is a Hypothesis property test: for any randomly-generated registry containing a `universal--*--*` plugin plus 0..5 concrete plugins, for any randomly-generated `PluginScope`, `resolve(scope)` is total — returns `ConcreteResolution` (whose `plugin.scope.matches(scope)` is True) OR `UniversalFallbackResolution`. Never raises; never returns `None`. ≥100 examples.
- [ ] TDD red test (`test_no_match_returns_universal_fallback`) committed and green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/plugins/resolver.py` and the new tests. Exhaustiveness `match` (with `assert_never`) demonstrated at one dispatch site in tests.

## Implementation outline

1. Define `ConcreteResolution`, `UniversalFallbackResolution`, `PluginResolution` Pydantic models in `resolver.py`. Use `Annotated[..., Field(discriminator="kind")]`.
2. Define `compose_extends_chain(plugin, registry, *, max_depth=4, _visited=None) -> ConcreteResolution` — recursive walker; visited-set is a `set[PluginId]` threaded through the recursion; `_visited is None` → fresh; depth is `len(_visited)`.
3. Define `resolve(registry, scope) -> PluginResolution` — the four-step algorithm above. Module-private helper.
4. Wire `PluginRegistry.resolve(self, scope)` to `resolver.resolve(self, scope)`. Replace the `NotImplementedError` from S2-01.
5. Populate `PluginExtendsCycle(chain: list[PluginId])` in `errors.py` if S2-01 left it as a placeholder.
6. Tests in dependency order: unit cases first; property test last (uses Hypothesis strategies for `PluginScope` and synthetic plugin sets).
7. Add `tests/fixtures/plugins/universal_fallback_fixture.py` — a minimal universal plugin with `manifest.name = "universal--*--*"`, scope `(*, *, *)`, lowest precedence. Reused by S7-03's HITL implementation.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/plugins/test_resolver.py`

```python
from codegenie.plugins.registry import PluginRegistry, register_plugin
from codegenie.plugins.resolver import UniversalFallbackResolution
from codegenie.plugins.scope import PluginScope
from tests.fixtures.plugins.fake_plugin import make_fake_plugin
from tests.fixtures.plugins.universal_fallback_fixture import make_universal_fallback


def test_no_match_returns_universal_fallback():
    """ADR-0003 §Decision step 3: when no concrete plugin matches a scope and
    the universal fallback is registered, `resolve` returns
    `UniversalFallbackResolution`. The fallback is a registered plugin, not a
    hardcoded code path; this is the type-level enforcement of
    production ADR-0009 (humans always merge)."""
    registry = PluginRegistry()
    register_plugin(make_universal_fallback(), registry=registry)
    register_plugin(
        make_fake_plugin(
            name="vulnerability-remediation--python--pip",
            scope_yaml={"task_class": "vulnerability-remediation",
                        "languages": ["python"], "build_systems": ["pip"]},
        ),
        registry=registry,
    )

    scope = PluginScope.parse("distroless-migration--node--npm").unwrap()
    resolution = registry.resolve(scope)

    assert isinstance(resolution, UniversalFallbackResolution)
    assert resolution.reason == "no_concrete_match"
    # the python-pip plugin was filtered out (didn't match), so it isn't in candidates
    assert "vulnerability-remediation--python--pip" not in resolution.candidates_considered
```

Why it fails: `codegenie.plugins.resolver` doesn't exist; `PluginRegistry.resolve` still raises `NotImplementedError` from S2-01.

### Green — minimal pass

- Implement `resolve` with the four steps.
- Implement `compose_extends_chain` with cycle + depth checks.
- Wire `PluginRegistry.resolve` to delegate.
- Universal-fallback narrowing: head-of-sorted-list inspection by `manifest.name == "universal--*--*"`.

### Refactor

- Pull the sort key into a named function (`_sort_key(plugin) -> tuple[int, int, str]`) for clarity.
- `assert_never` in a small `_dispatch_example(resolution: PluginResolution) -> str` test helper to *prove* the `match` is exhaustive; mypy will catch missed variants.
- The Hypothesis property test uses two strategies: `scopes()` produces random `(Concrete | Wildcard, ...)` tuples; `plugin_sets()` produces 0..5 synthetic plugins with random scopes + a guaranteed universal fallback. Assertion: `isinstance(resolution, (ConcreteResolution, UniversalFallbackResolution))` AND if concrete, `resolution.plugin.scope.matches(scope)` is True.
- `candidates_considered` sanitization: drop any plugin name that contains a path component (defensive — universe-of-discourse is `PluginId`, but a future plugin name might leak; sanitize defensively per ADR-0003 §Consequences).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/resolver.py` | New: `PluginResolution` union, `resolve`, `compose_extends_chain`. |
| `src/codegenie/plugins/registry.py` | Replace `NotImplementedError` in `resolve` with delegation to `resolver.resolve`. |
| `src/codegenie/plugins/errors.py` | Populate `PluginExtendsCycle(chain)` and `PluginRegistryCorrupted` if S2-01 left them as placeholders. |
| `tests/unit/plugins/test_resolver.py` | Unit cases: specificity, precedence, name ordering, extends depth, cycle, fallback. |
| `tests/unit/plugins/test_resolver_property.py` | Hypothesis property test (≥100 examples). |
| `tests/fixtures/plugins/universal_fallback_fixture.py` | `make_universal_fallback()` helper — reused by S7-03. |
| `tests/fixtures/plugins/fake_plugin.py` | Extend the S2-01 helper to accept `extends=[...]` and `precedence=N` so resolver tests can compose chains. |

## Out of scope

- **Concrete universal HITL subgraph behavior** — handled by S7-03 (writes sanitized handoff markdown, emits `RequiresHumanReview`). This story only needs a fixture plugin that *registers* as `universal--*--*`; its `build_subgraph` can return a stub.
- **`ComposedTccm` real shape + provides/requires merge** — Step 3 (S3-01) lands `TCCM` Pydantic. For Step 2's resolver tests, treat `composed_tccm` as a minimal placeholder (`dict[str, str]` or a `TccmPlaceholder` shim) and document the substitution point.
- **`composed_adapters` real Adapter implementations** — Step 7 / S7-02 lands npm-specific adapters. Resolver tests use stub `Adapter` instances; the composition logic (later-wins-on-collision) is what's exercised.
- **`PluginRegistryCorrupted` spanning event emission** — that's the event log's concern (S6-01). This story raises the typed exception; the orchestrator (S6-04) maps it to event + exit.
- **Plugin loader integration** — S2-03 already loads plugins; this story consumes whatever the loader registered. No loader changes here.
- **Per-plugin `RecipeRegistry`** — Step 5 / S5-01 (Gap 3 fix).

## Notes for the implementer

- ADR-0003 §Decision step 3 reads "If the head plugin's id is `universal--*--*`". The literal string is the load-bearing convention; resist parameterizing it. A future "what if the universal name changes" question is an ADR amendment, not a code-time decision.
- The `assert_never` discipline on `match resolution: case ConcreteResolution() | UniversalFallbackResolution(): ...` is the type-level enforcement that production ADR-0009 lives or dies on. mypy will catch a missed variant; a reviewer will reject a `Plugin | None` regression.
- Depth-4 cap is empirical (per ADR-0003 §Tradeoffs). The depth-5 test should construct a chain `A → B → C → D → E` and assert `PluginRejected(reason="extends_depth_exceeded", chain=["A","B","C","D","E"])`. The chain length is len-5 (≥ 5 distinct nodes); the *visited-set size* is what crosses the threshold.
- Cycle detection: `A extends B extends A`. The cycle exception's `chain` field carries `["A","B","A"]` — repeat the entry-point at the tail so an operator reading the stack can immediately see "we came back to where we started." This is more useful than `["A","B"]`.
- Left-to-right `extends` merge with later-wins-on-collision: when merging two adapter maps, `{**a, **b}` style suffices (Python dict update is "later wins"). But the chain order is `extends[0] → extends[1] → ... → plugin itself last`. The "leaf wins" property emerges from putting the plugin at the *end* of the chain conceptually (production ADR-0031 §Inheritance and override is explicit). Read it twice; this is the most common bug class in this story.
- Hypothesis: derive the `PluginScope` strategy from S1-02's strategies if S1-02 ships them; otherwise compose ad-hoc strategies from `Concrete(value=...)` and `Wildcard()`. The strategy must not generate `universal--*--*` as a *concrete* plugin name — reserve that string for the fallback fixture.
- `candidates_considered` carries `PluginId`s only, not paths or adapter import strings. Sanitization is one line (filter on type), but stating it explicitly in the docstring prevents a future contributor from "enriching" the list with file paths the operator never asked for. ADR-0003 §Consequences calls this out.
- The property test is the headline assertion of ADR-0003 — totality (`resolve` never raises, never returns `None`). If the test gets flaky or times out, debug the strategy, not the assertion; the property is non-negotiable.
- Mypy strictness: `PluginResolution` is `ConcreteResolution | UniversalFallbackResolution` — the discriminated `kind` is what mypy uses for narrowing. Annotate the `resolve` return as `PluginResolution`, not `ConcreteResolution | UniversalFallbackResolution` (the alias is the typed surface).
