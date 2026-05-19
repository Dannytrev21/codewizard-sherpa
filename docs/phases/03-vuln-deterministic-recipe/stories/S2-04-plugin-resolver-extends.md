# Story S2-04 — Plugin resolver: `(specificity, precedence, name)` ordering + `extends` walker + `UniversalFallbackResolution`

**Step:** Step 2 — Plugin Registry kernel, manifest schema, loader, resolver
**Status:** Done — GREEN 2026-05-19 (phase-story-executor; see [`_attempts/S2-04.md`](_attempts/S2-04.md) for the per-AC evidence table + gate log)
**Effort:** M
**Depends on:** S1-02 (`PluginScope`), S1-03 (tagged-union discipline), S2-01 (kernel + `resolve` `NotImplementedError` stub), S2-02 (`ManifestScope` shape — pre-lift), S2-03 (loader + `PluginRejected`)
**ADRs honored:** ADR-0002, ADR-0003, ADR-0010, production ADR-0031, production ADR-0009

## Validation notes (2026-05-18)

Hardened by the `phase-story-validator` skill (autonomous run via the story-validation-corrector scheduled task). Full audit at [`_validation/S2-04-plugin-resolver-extends.md`](_validation/S2-04-plugin-resolver-extends.md). Substantive changes:

- **`ManifestScope → PluginScope` lift added as a load-bearing first step.** The original story called `plugin.scope.matches(scope)` directly. Per S2-02's hardened output (and the arch follow-up logged in `_validation/S2-02-plugin-manifest-pydantic.md §Arch amendments`), the *load-time* `PluginManifest.scope` is a `ManifestScope` whose dims are `str | list[str]`. The resolver is the lift point: a new `lift_manifest_scope(manifest_scope) -> tuple[PluginScope, ...]` fans out lists into the cross-product of single-dim `PluginScope` instances. The sort and filter operate on a typed `ScopedCandidate` (plugin + one lifted `PluginScope`), not on raw `Plugin`.
- **`matches` signature aligned with S1-02.** S1-02 ships `PluginScope.matches(*, task: str, language: str, build: str) -> bool` (keyword-only). The resolver receives a `PluginScope` (from the orchestrator's repo-context-derived scope) and queries each lifted candidate via `candidate.lifted_scope.matches(task=..., language=..., build=...)` after unpacking the incoming scope's Concrete dims. Wildcards on the *incoming* scope are treated as "operator did not specify" — see Notes §"Incoming scope discipline".
- **`UNIVERSAL_FALLBACK_ID: Final[PluginId]` sentinel.** ADR-0003 §Decision step 3 says "if the head plugin's id is `universal--*--*`". Story originally inlined the literal; hardened to a module-level `Final[PluginId]` so adding `S7-03`'s real fallback plugin, the `make_universal_fallback` fixture, and the loader's startup check all reference one symbol. (Notes §"Why not parameterize" preserves the no-config-knob discipline.)
- **`ConcreteResolution.matched_scope: PluginScope` added.** Arch line 779 names this field; original AC omitted it. The matched scope is the single lifted `PluginScope` that filtered through — useful for audit / event payloads and for the property test's "concrete resolution's matched_scope.matches(...)" totality check.
- **`candidates_considered` semantics pinned.** ADR-0003 §Consequences row 5: "concrete plugins were filtered out". Story originally said "filtered-but-not-chosen concrete plugins" with ambiguous semantics. Hardened: `candidates_considered` is the alphabetized `tuple[PluginId, ...]` of every concrete `plugin.manifest.name` that was in `registry.all()` but whose **no** lifted scope matched the incoming scope. Excludes the universal plugin itself; tuple (not list) so the field is hashable + immutable.
- **TDD plan parametrized.** Original story had one red test. Hardened: parametrized table with **eleven** named tests covering specificity ordering, precedence tie-break, name tie-break, fan-out, extends composition (TCCM + adapters left-to-right merge), cycle detection, depth-cap, universal fallback (no concrete match), universal-only registry, missing-universal corruption, and missing-extends-target error. Mutation kill-list enumerated.
- **Property test pinned.** Strategy must NOT generate `UNIVERSAL_FALLBACK_ID` as a concrete plugin name; ≥200 examples; `deadline=None` to avoid CI flakes; `assert_never` exhaustive `match` over `PluginResolution` at the assertion site (mutation-resistance for "added a third variant" refactor).
- **Functional core / imperative shell split.** `resolve` is decomposed into pure helpers: `_lift_candidates(plugins) -> tuple[ScopedCandidate, ...]`, `_filter_matches(candidates, scope) -> tuple[ScopedCandidate, ...]`, `_sort_by_keys(matches) -> tuple[ScopedCandidate, ...]`, `_compose_extends_chain(head, registry) -> ConcreteResolution`. Public `resolve(registry, scope)` composes them; the only I/O is whatever the registry holds (in-memory, deterministic).
- **`PluginRegistryCorrupted` clarified.** ADR-0003 §Consequences line 50 names a *spanning event*; phase-arch §C2 line 483 lists the *exit code 4* family. This story raises a typed exception `PluginRegistryCorrupted(reason: Literal["missing_universal", "empty_registry"])`; the event emission is S6-01's concern (Out-of-scope expanded).
- **Magic-number removal.** `max_depth=4` becomes `_MAX_EXTENDS_DEPTH: Final[int] = 4` at module level, with an ADR-0003 §Tradeoffs comment naming the empirical basis.

The original story's substance (algorithm, totality property, cycle detection, universal-fallback-as-plugin discipline) is preserved. The validator only **tightened ACs into individually verifiable assertions**, **pinned the `ManifestScope → PluginScope` lift seam** that the rest of Phase 3 already implicitly committed to, **added missing-edge-case ACs** (universal-only, missing-extends-target, fan-out, no-incoming-wildcard), **rewrote the TDD plan into a parametrized table with eleven concrete tests**, and **refactored the implementation outline into a functional-core / imperative-shell split**. No scope change.

## Context

This is Step 2's payoff story: with the kernel (S2-01), the manifest model (S2-02), and the loader (S2-03) in place, the resolver implements the **ADR-0003 algorithm** that maps a `PluginScope` (the orchestrator's intent — derived from `repo-context.yaml`) to a typed `PluginResolution`. Four structural commitments are load-bearing:

1. **Universal fallback is a registered plugin, not a code path.** When no concrete plugin matches a scope, the resolver returns `UniversalFallbackResolution`. The universal plugin (`universal--*--*`) is loaded by the same machinery as any other plugin (ADR-0031 §No-match fallback). The kernel has **no** `if plugin.id == UNIVERSAL_FALLBACK_ID:` branch outside the resolver itself.
2. **The return type is a tagged union, not `Plugin | None`.** `PluginResolution = ConcreteResolution | UniversalFallbackResolution`; every dispatch site `match`es with `assert_never`. This is the structural enforcement of production ADR-0009 (humans always merge): the "no concrete match" path is type-impossible to silently drop.
3. **The resolver is the `ManifestScope → PluginScope` lift point.** S2-02 ships `PluginManifest.scope: ManifestScope` with raw `str | list[str]` per dim (per production ADR-0031's canonical YAML). This story is the first place those raw scopes are *lifted* into S1-02's typed `PluginScope` sum. A plugin whose `manifest.scope.languages == ["node", "python"]` fans out into two lifted `PluginScope` candidates; the resolver scores each candidate independently.
4. **The `extends` walker composes TCCM and adapter maps left-to-right.** Later wins per ADR-0031 §Inheritance and override. Cycle detection caps at depth 4 with a visited-set check; `PluginExtendsCycle(chain)` is raised on cycle and `PluginRejected(reason="extends_depth_exceeded", chain=...)` on over-depth.

A Hypothesis property test is non-optional here: for any randomly-generated set of `PluginScope`s registered alongside a `universal--*--*` fallback, `resolver.resolve(scope)` is total — it returns `ConcreteResolution` whose `matched_scope.matches(...)` is True, OR returns `UniversalFallbackResolution`. It never raises (cycle is a startup-time concern, not a per-resolve concern), never returns `None`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C2 (line 479)` — `resolve()` algorithm; `(specificity desc, precedence desc, name asc)` ordering; cycle check; max depth 4.
  - `../phase-arch-design.md §Component design C3 (lines 486–514)` — `PluginScope` + `Concrete | Wildcard` sum type from S1-02; `specificity() = count of Concrete dims`; `matches(*, task, language, build) -> bool` keyword-only signature.
  - `../phase-arch-design.md §Scenarios D (lines 392–411)` — concrete walkthrough: vuln-remediation--node--npm resolved against a `(vuln, node, npm)` workflow; sort by (specificity desc, precedence desc, name asc); walk `extends_chain` (max depth 4); compose TCCM left-to-right.
  - `../phase-arch-design.md §Data model (lines 775–791)` — `ConcreteResolution.matched_scope: PluginScope` field (load-bearing for property test); `UniversalFallbackResolution.candidates_considered: list[PluginId]`; `Annotated[..., Discriminator("kind")]`.
  - `../phase-arch-design.md §Edge cases E2, E9, E10` — fallback path; ambiguous ties; deep `extends` chains.
- **Phase ADRs:**
  - `../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md` — Option C is the decision; algorithm steps 1–4 are mandatory; universal fallback is a registered plugin under `plugins/universal--*--*/`, **never** a hardcoded code path. §Consequences row 5 specifies `candidates_considered = filtered-out concrete plugins`.
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — ADR-0002 — `resolve` is on the registry instance; exit code 4 on cycle.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — ADR-0010 — `PluginScope` is a sum type, not `Literal["*"]`; `PluginId` newtype.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` §Discovery and resolution + §Inheritance and override — the canonical algorithm; later-wins-on-collision for `extends`.
  - `../../../production/adrs/0009-humans-always-merge.md` — the invariant the typed `UniversalFallbackResolution` enforces statically.
- **Sibling validations (recent precedent):**
  - `_validation/S2-02-plugin-manifest-pydantic.md §Arch amendments` — flags that `PluginManifest.scope` is `ManifestScope` (raw form), not `PluginScope`. This story is the lift point.
  - `_validation/S2-01-plugin-registry-kernel.md` — autouse `restore_default_registry` fixture; tagged-union exception payload pattern; parametrized per-variant tests.
  - `_validation/S2-03-plugin-loader-integrity.md` — Strategy-seam-by-Protocol precedent (`PluginVerifier`); tagged-union sum-type for errors (`PluginRejected` variants); AST-source-scan fences.
  - `_validation/S1-02-plugin-scope-sum-type.md` — `matches(*, task, language, build) -> bool` keyword-only signature; round-trip via `PluginScope.parse(str(scope)).unwrap()`; AC-21 module-purity AST scan precedent.
  - `_validation/S1-03-tagged-union-outcomes.md` — discriminator-on-`kind` pattern; `assert_never` exhaustiveness AST scan precedent.
- **Existing code:**
  - `src/codegenie/plugins/registry.py` (S2-01) — `PluginRegistry.resolve(scope)` raises `NotImplementedError("S2-04 …")`; replace.
  - `src/codegenie/plugins/scope.py` (S1-02) — `PluginScope`, `Concrete`, `Wildcard`, `matches`, `specificity`.
  - `src/codegenie/plugins/manifest.py` (S2-02) — `PluginManifest.extends: tuple[PluginId, ...]`, `PluginManifest.precedence: int = 50` (note: 50, not 0 — fixed in S2-02 validation), `PluginManifest.scope: ManifestScope`.
  - `src/codegenie/plugins/errors.py` (S2-01 placeholders) — populate `PluginExtendsCycle(chain)` and `PluginRegistryCorrupted(reason)`.
  - `src/codegenie/plugins/resolution.py` (S2-01 placeholder) — expand `class PluginResolution: ...` to the real discriminated union OR move into `resolver.py`. Pick one location and pin it.
  - `src/codegenie/result.py` — `Result` is **not** used on `resolve` (resolve is total; no `Result` needed). The cycle pre-check could be a startup helper if implemented (deferred to S2-03 + S6-04).

## Goal

Implement `PluginRegistry.resolve(scope: PluginScope) -> PluginResolution` and the supporting machinery: the `ManifestScope → PluginScope` lift (with list fan-out), the `(specificity desc, precedence desc, name asc)` sort, the `extends`-chain walker that composes TCCM and adapter maps left-to-right (with cycle detection + max depth 4), the typed `PluginResolution` discriminated union, and the Hypothesis property test that proves the totality invariant. The universal fallback fires by *type narrowing on the sorted head*, not by branching on a string.

## Acceptance criteria

- [ ] **AC-1 — Module surface.** `src/codegenie/plugins/resolver.py` exports exactly: `UNIVERSAL_FALLBACK_ID` (`Final[PluginId]`), `ScopedCandidate` (frozen dataclass), `ConcreteResolution`, `UniversalFallbackResolution`, `PluginResolution` (type alias), `lift_manifest_scope`, `compose_extends_chain`, `resolve`. Declared via `__all__: Final[tuple[str, ...]] = (...)` alphabetically sorted. `set(resolver.__all__)` equality is asserted in a test — stowaway exports fail CI (S1-02 AC-2 precedent).
- [ ] **AC-2 — `UNIVERSAL_FALLBACK_ID` sentinel.** Module-level `UNIVERSAL_FALLBACK_ID: Final[PluginId] = PluginId("universal--*--*")`. The string literal MUST appear in exactly one place in `src/codegenie/`; an AST-source-scan test (`tests/static/test_universal_fallback_id_single_source.py`) parses every `.py` file under `src/codegenie/` and `tests/fixtures/plugins/` and asserts the literal `"universal--*--*"` appears at most once outside of `resolver.py` and `tests/fixtures/plugins/universal_fallback_fixture.py`. (Mutation: a future contributor inlines the literal in a comparison → test fails.)
- [ ] **AC-3 — `ScopedCandidate` dataclass.** `@dataclass(frozen=True, slots=True) class ScopedCandidate: plugin: Plugin; lifted_scope: PluginScope`. Carries the *single* lifted PluginScope a candidate plugin was scored against (so multi-scope manifests fan out into multiple candidates pre-sort).
- [ ] **AC-4 — `ConcreteResolution` Pydantic model.** `model_config = ConfigDict(frozen=True, extra="forbid")`. Fields exactly:
  - `kind: Literal["concrete"] = "concrete"`
  - `plugin: Plugin`
  - `extends_chain: tuple[Plugin, ...]` (root → leaf; **leaf is `plugin` itself**)
  - `matched_scope: PluginScope` — the lifted scope that filtered through (per arch §Data model line 779)
  - `composed_tccm: ComposedTccm` — minimal placeholder Pydantic model for Step 2 (`class ComposedTccm(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid"); provides: dict[str, dict[str, str]] = {}; requires: dict[str, tuple[str, ...]] = {}`). Step 3 (S3-01) replaces with the real `TCCM` model from `../ADRs/0004-plugin-private-capabilities-via-tccm.md`; this story documents the substitution point.
  - `composed_adapters: dict[PrimitiveName, Adapter]`
- [ ] **AC-5 — `UniversalFallbackResolution` Pydantic model.** `model_config = ConfigDict(frozen=True, extra="forbid")`. Fields exactly:
  - `kind: Literal["universal_fallback"] = "universal_fallback"`
  - `reason: Literal["no_concrete_match"]`
  - `candidates_considered: tuple[PluginId, ...]` (alphabetized; excludes `UNIVERSAL_FALLBACK_ID`)
- [ ] **AC-6 — Discriminated union.** `PluginResolution: TypeAlias = Annotated[ConcreteResolution | UniversalFallbackResolution, Field(discriminator="kind")]`. The `PluginRegistry.resolve` return annotation uses this alias (not the raw union); mypy narrowing flows through the alias.
- [ ] **AC-7 — `lift_manifest_scope`.** `lift_manifest_scope(manifest_scope: ManifestScope) -> tuple[PluginScope, ...]` lifts the raw `str | list[str]` dims into the **cross-product** of single-dim `PluginScope` instances. Examples (parametrized table in `test_resolver.py`):
  - `(task_class="vulnerability-remediation", languages="node", build_systems="npm")` → 1 PluginScope.
  - `(task_class="vulnerability-remediation", languages=["node", "python"], build_systems="*")` → 2 PluginScopes (one with Concrete("node"), one with Concrete("python")).
  - `(task_class=["vulnerability-remediation", "distroless-migration"], languages="*", build_systems=["npm", "pip"])` → 4 PluginScopes.
  - `(task_class="*", languages="*", build_systems="*")` → 1 PluginScope (universal).
  The function delegates per-dim string-to-`ScopeDim` lift to a helper `_lift_dim(raw: str) -> ScopeDim` (returns `Wildcard()` for `"*"`, else `Concrete(value=raw)`). Each output `PluginScope` is constructed directly (NOT via `PluginScope.parse(...)`) because the manifest YAML loader already validated the inputs.
- [ ] **AC-8 — `_lift_candidates` pure helper.** `_lift_candidates(plugins: Sequence[Plugin]) -> tuple[ScopedCandidate, ...]` flat-maps each plugin into its `lift_manifest_scope(plugin.manifest.scope)`-produced tuple. Output is a flat tuple of `(plugin, lifted_scope)` pairs; the same `plugin` may appear in multiple `ScopedCandidate`s.
- [ ] **AC-9 — Resolution algorithm.** `resolve(registry: PluginRegistry, scope: PluginScope) -> PluginResolution` executes exactly these steps:
  1. `candidates = _lift_candidates(registry.all())`.
  2. `matches = tuple(c for c in candidates if c.lifted_scope.matches(task=_unpack(scope.task_class), language=_unpack(scope.language), build=_unpack(scope.build_system)))` where `_unpack(dim: ScopeDim) -> str` returns `dim.value` for `Concrete` and `"*"` for `Wildcard` (incoming wildcards mean "operator did not specify" — they always match per S1-02's `matches` semantics applied with `"*"` interpreted as the wildcard string-form; see Notes §"Incoming scope discipline").
  3. If `matches` is empty AND the registry contains the universal plugin, return `UniversalFallbackResolution(reason="no_concrete_match", candidates_considered=())`.
  4. If `matches` is empty AND the registry does NOT contain the universal plugin, raise `PluginRegistryCorrupted(reason="missing_universal")`.
  5. Sort `matches` by `_sort_key`: `(-lifted_scope.specificity(), -plugin.manifest.precedence, plugin.manifest.name)`. (Negation for descending; the tuple is naturally ascending.)
  6. If sorted head's `plugin.manifest.name == UNIVERSAL_FALLBACK_ID`, return `UniversalFallbackResolution(reason="no_concrete_match", candidates_considered=_candidates_considered(registry))`.
  7. Else: walk the head's `extends` chain via `compose_extends_chain(head.plugin, registry)`; return the resulting `ConcreteResolution` with `matched_scope=head.lifted_scope`.
- [ ] **AC-10 — `_candidates_considered` semantics.** `_candidates_considered(registry: PluginRegistry) -> tuple[PluginId, ...]` returns the alphabetized `tuple[PluginId, ...]` of every `plugin.manifest.name` in `registry.all()` whose name != `UNIVERSAL_FALLBACK_ID`. (The "concrete plugins were filtered out" semantics per ADR-0003 §Consequences row 5.) When invoked from step 6, this is the operator-visible debug surface; the universal plugin is intentionally excluded since the resolver already narrowed *to* it.
- [ ] **AC-11 — `compose_extends_chain`.** `compose_extends_chain(plugin: Plugin, registry: PluginRegistry, *, max_depth: int = _MAX_EXTENDS_DEPTH) -> ConcreteResolution`:
  - Walks `plugin.manifest.extends: tuple[PluginId, ...]` depth-first, left-to-right.
  - Threads a `visited: frozenset[PluginId]` through the recursion (initial: `frozenset()`); on entry, if `plugin.manifest.name in visited`, raise `PluginExtendsCycle(chain=tuple([*visited_path, plugin.manifest.name]))` where `visited_path` records the insertion order (use a `tuple[PluginId, ...]` accumulator alongside `visited`).
  - On `len(visited) >= max_depth`, raise `PluginRejected(reason="extends_depth_exceeded", chain=tuple([*visited_path, plugin.manifest.name]))`.
  - Resolves each `extends_id: PluginId` via `registry.get(extends_id)`; if not registered, `registry.get` already raises `PluginNotRegistered(name)` (S2-01); the resolver does NOT catch this — it propagates (the loader's startup integrity check is the right place to fail-fast for missing extends targets; see Notes §"Why `PluginNotRegistered` propagates").
  - Composes `composed_tccm` and `composed_adapters` left-to-right (extends[0] applied first, then extends[1], …, then `plugin` itself applied last). For dict merges, later wins on collision (`a | b` Python 3.9+ dict merge semantics OR `{**a, **b}`); for `provides` (nested `dict[str, dict[str, str]]`), the inner dicts are also merged later-wins per-key (one-level deep).
  - Returns `ConcreteResolution(plugin=plugin, extends_chain=(*resolved_extends_in_order, plugin), matched_scope=<filled by caller>, composed_tccm=..., composed_adapters=...)`.
- [ ] **AC-12 — `PluginRegistry.resolve` delegation.** `PluginRegistry.resolve(self, scope: PluginScope) -> PluginResolution` delegates to `resolver.resolve(self, scope)`. The `NotImplementedError("S2-04 …")` stub from S2-01 is removed; AST-source-scan test (`tests/static/test_no_notimplemented_in_registry.py`) asserts the substring `"NotImplementedError"` does not appear in `src/codegenie/plugins/registry.py`.
- [ ] **AC-13 — Module purity (functional core).** AST scan (`tests/unit/plugins/test_resolver_purity.py`) parses `src/codegenie/plugins/resolver.py` and asserts the `Import`/`ImportFrom` set is a subset of `{__future__, dataclasses, typing, pydantic, codegenie.plugins.scope, codegenie.plugins.manifest, codegenie.plugins.protocols, codegenie.plugins.registry, codegenie.plugins.errors, codegenie.types.identifiers}`. No `os`, `pathlib`, `logging`, or any I/O module. (S1-02 AC-21 precedent; ADR-0001 chokepoint hygiene generalized.)
- [ ] **AC-14 — Exhaustiveness `match` AST scan.** AST scan (`tests/unit/plugins/test_resolver_exhaustiveness.py`) parses `resolver.py` and asserts: every `match` block whose subject is a `PluginResolution`-typed expression contains a final `case _: assert_never(...)` arm. The test also includes a `_dispatch_example(resolution: PluginResolution) -> str` helper *in the test file* that does an exhaustive `match` and is type-checked via mypy's `assert_never`; adding a future variant without updating dispatch sites breaks `mypy --strict` (S1-02 AC-14 precedent).
- [ ] **AC-15 — Tests in `tests/unit/plugins/test_resolver.py`.** Parametrized + per-AC tests enumerated below (eleven concrete cases). Each MUST be individually runnable as `pytest -k "<name>"` (no shared mutable state):
  1. `test_no_match_returns_universal_fallback` (red — see TDD plan).
  2. `test_exact_match_beats_wildcard` — specificity-3 plugin AND specificity-1 plugin both match an incoming `(vuln, node, npm)` scope; assert the specificity-3 wins (mutation: sort key reversed → fails).
  3. `test_precedence_breaks_specificity_tie` — two plugins with equal specificity; one has `precedence=100`, the other `precedence=50` (the default per S2-02 AC-2); assert the precedence-100 wins.
  4. `test_name_breaks_precedence_tie` — two plugins with equal specificity, equal precedence, names `"a-plugin"` and `"b-plugin"`; assert `"a-plugin"` wins (alphabetical ascending).
  5. `test_lift_manifest_scope_fans_out` — parametrized table with the four examples from AC-7; each input → exact-tuple-of-`PluginScope` output.
  6. `test_extends_chain_composes_tccm_and_adapters_left_to_right` — plugin `A` extends plugin `B`; `B.transforms()` returns `{Foo: AdapterB}`; `A.transforms()` returns `{Foo: AdapterA, Bar: AdapterC}`; assert `resolution.composed_adapters == {Foo: AdapterA, Bar: AdapterC}` (later-wins on `Foo`; `Bar` added). Mirror with `composed_tccm.provides`: `B.provides = {"vuln": {"x": "vB"}}`; `A.provides = {"vuln": {"x": "vA", "y": "vA2"}}`; assert composed `{"vuln": {"x": "vA", "y": "vA2"}}` (inner dict also later-wins per-key).
  7. `test_extends_depth_4_composes_correctly` — chain `A → B → C → D` (depth 4 = `len(visited) == 4` at leaf); assert no raise; assert `extends_chain` tuple length is 4 (root→leaf order: `(D, C, B, A)` — extends walked first applies first; chain `extends_chain[-1] is A` is `plugin` itself).
  8. `test_extends_depth_5_raises_extends_depth_exceeded` — chain `A → B → C → D → E`; assert raises `PluginRejected` with `reason == "extends_depth_exceeded"` and `chain == (PluginId("A"), PluginId("B"), PluginId("C"), PluginId("D"), PluginId("E"))`.
  9. `test_extends_cycle_raises_plugin_extends_cycle` — `A extends B`, `B extends A`; resolve(A); assert raises `PluginExtendsCycle` with `chain == (PluginId("A"), PluginId("B"), PluginId("A"))` (entry-point repeated at tail per Notes §"Cycle chain shape").
  10. `test_only_universal_registered_returns_universal_fallback` — registry contains *only* the universal plugin; resolve any scope; assert `UniversalFallbackResolution(reason="no_concrete_match", candidates_considered=())`. (Mutation: AC-9 step 3 missing → falls through to step 4 → raises `PluginRegistryCorrupted` → test fails.)
  11. `test_missing_universal_raises_plugin_registry_corrupted` — registry contains only concrete plugins; resolve a scope none match; assert raises `PluginRegistryCorrupted(reason="missing_universal")`.
  12. `test_extends_missing_target_raises_plugin_not_registered` — `A extends B`, `B` is not registered; resolve(A); assert raises `PluginNotRegistered(name=PluginId("B"))` (the S2-01 exception propagates).
  13. `test_candidates_considered_alphabetized_and_excludes_universal` — registry contains `c-plugin`, `a-plugin`, `b-plugin` (all concrete, none match the incoming scope) plus universal; resolve(non-matching-scope); assert `resolution.candidates_considered == (PluginId("a-plugin"), PluginId("b-plugin"), PluginId("c-plugin"))` (no universal).
- [ ] **AC-16 — Property test in `tests/unit/plugins/test_resolver_property.py`.** Hypothesis property test:
  - Strategy `concrete_plugin_name()` draws from `text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=32).filter(lambda s: s != "universal--*--*" and not s.startswith("-") and not s.endswith("-"))`. The negative filter is mandatory — generating `universal--*--*` as a concrete name would corrupt the test invariant (asserted as a meta-property in the strategy via `assume(name != UNIVERSAL_FALLBACK_ID)`).
  - Strategy `concrete_plugins()` draws 0..5 fake plugins with random `ManifestScope` (each dim independently `Wildcard | Concrete(<random word>)`) and random `precedence ∈ [0, 100]`.
  - Strategy `incoming_scope()` draws a random `PluginScope` (each dim independently `Wildcard | Concrete(<random word>)`).
  - For each (registry-with-universal + 0..5 concretes, incoming scope) pair: `resolution = resolve(registry, scope)`. Assert (via exhaustive `match` over `PluginResolution` with `assert_never`): if `ConcreteResolution`, `resolution.matched_scope.matches(task=_unpack(scope.task_class), language=_unpack(scope.language), build=_unpack(scope.build_system))` is True AND `resolution.plugin in registry.all()`; if `UniversalFallbackResolution`, `resolution.plugin_id == UNIVERSAL_FALLBACK_ID` (via `registry.get(UNIVERSAL_FALLBACK_ID)`). Never raises (assume Hypothesis-generated plugins are well-formed — no cycles, depth ≤ 4); never returns `None`.
  - Decorate `@settings(max_examples=200, deadline=None)` — deadline disabled to avoid CI flakes on cold-cache machines; 200 examples to exercise the cross-product without slowing CI excessively.
- [ ] **AC-17 — `_MAX_EXTENDS_DEPTH` constant.** `_MAX_EXTENDS_DEPTH: Final[int] = 4` at module level with a comment naming ADR-0003 §Tradeoffs as the empirical basis. The literal `4` MUST NOT appear inline in any `if depth > 4` / `max_depth=4` site (AST scan asserts at most one occurrence of the integer literal `4` in `resolver.py`; the named constant is the single source of truth). (Mutation-resistance for "raised the cap to 10 without an ADR amendment".)
- [ ] **AC-18 — Fixtures.** `tests/fixtures/plugins/universal_fallback_fixture.py` exports `make_universal_fallback() -> Plugin` returning a minimal universal plugin with `manifest.name == UNIVERSAL_FALLBACK_ID`, `manifest.scope == ManifestScope(task_class="*", languages="*", build_systems="*")`, `manifest.precedence == 0` (lowest, below the S2-02 default of 50), `manifest.extends == ()`, `build_subgraph()` returns a stub, `adapters()`/`transforms()` return `{}`. `tests/fixtures/plugins/fake_plugin.py` (extended from S2-01) accepts new kwargs `extends: tuple[PluginId, ...] = ()`, `precedence: int = 50`, `manifest_scope: ManifestScope | None = None` (so resolver tests compose chains and fan-outs).
- [ ] **AC-19 — `ruff check`, `ruff format --check`, `mypy --strict` clean** on `src/codegenie/plugins/resolver.py`, `tests/unit/plugins/test_resolver.py`, `tests/unit/plugins/test_resolver_property.py`, `tests/unit/plugins/test_resolver_purity.py`, `tests/unit/plugins/test_resolver_exhaustiveness.py`, `tests/static/test_universal_fallback_id_single_source.py`, `tests/static/test_no_notimplemented_in_registry.py`, `tests/fixtures/plugins/universal_fallback_fixture.py`. Exhaustiveness `match` with `assert_never` demonstrated at the `_dispatch_example` site in `test_resolver_exhaustiveness.py`.

## Implementation outline

1. **Errors first.** Populate `src/codegenie/plugins/errors.py` placeholders (if S2-01 left them as such):
   - `class PluginExtendsCycle(Exception): chain: tuple[PluginId, ...]; exit_code: ClassVar[int] = 4`.
   - `class PluginRejected(Exception): reason: Literal["extends_depth_exceeded", ...]; chain: tuple[PluginId, ...]; exit_code: ClassVar[int] = 4`. (S2-03 may have already added the seven-variant tagged union; if so, extend with the new `extends_depth_exceeded` variant additively per its hardened tagged-union shape.)
   - `class PluginRegistryCorrupted(Exception): reason: Literal["missing_universal", "empty_registry"]; exit_code: ClassVar[int] = 4`.
2. **Sum-type return.** In `src/codegenie/plugins/resolver.py` (NEW), define `ConcreteResolution`, `UniversalFallbackResolution`, the `PluginResolution` `Annotated[..., Field(discriminator="kind")]` alias, the `ComposedTccm` minimal placeholder Pydantic, and the `ScopedCandidate` frozen dataclass. Remove the `PluginResolution` placeholder from `src/codegenie/plugins/resolution.py` (or leave the file as a one-line `from codegenie.plugins.resolver import PluginResolution as PluginResolution` re-export — pick one and document in Notes §"Module placement").
3. **Sentinel + constants.** `UNIVERSAL_FALLBACK_ID: Final[PluginId] = PluginId("universal--*--*")`. `_MAX_EXTENDS_DEPTH: Final[int] = 4`.
4. **Pure helpers.** Define in this order (each is pure-given-inputs):
   - `_lift_dim(raw: str) -> ScopeDim` — `"*"` → `Wildcard()`; else `Concrete(value=raw)`.
   - `lift_manifest_scope(ms: ManifestScope) -> tuple[PluginScope, ...]` — cross-product over the three dims.
   - `_lift_candidates(plugins: Sequence[Plugin]) -> tuple[ScopedCandidate, ...]` — flat-map.
   - `_unpack(dim: ScopeDim) -> str` — `dim.value` for `Concrete`, `"*"` for `Wildcard`; total via `match` + `assert_never`.
   - `_filter_matches(candidates: tuple[ScopedCandidate, ...], scope: PluginScope) -> tuple[ScopedCandidate, ...]`.
   - `_sort_key(c: ScopedCandidate) -> tuple[int, int, str]` — returns `(-c.lifted_scope.specificity(), -c.plugin.manifest.precedence, c.plugin.manifest.name)`. Named for clarity; tested directly in a small unit test.
   - `_candidates_considered(registry: PluginRegistry) -> tuple[PluginId, ...]` — alphabetized concrete-only names.
5. **`compose_extends_chain`.** Recursive walker with `visited: frozenset[PluginId]` + `visited_path: tuple[PluginId, ...]` threaded through; raises `PluginExtendsCycle` on cycle, `PluginRejected(extends_depth_exceeded)` on over-depth; composes `composed_tccm` (one-level-deep later-wins per `provides` key) and `composed_adapters` (single-level later-wins).
6. **`resolve`.** Compose helpers in the AC-9 order. Raise `PluginRegistryCorrupted(reason="empty_registry")` if `registry.all()` is empty (defensive — should already be caught at loader startup, but fail-loud here too).
7. **Wire delegation.** Edit `src/codegenie/plugins/registry.py`: replace `NotImplementedError("S2-04 …")` body with `return resolver.resolve(self, scope)`. Add the `from codegenie.plugins import resolver` import locally inside the method (avoid module-level circular import — `resolver` imports `PluginRegistry` type for annotation only via `TYPE_CHECKING`).
8. **Fixtures.** Land `tests/fixtures/plugins/universal_fallback_fixture.py` + extend `tests/fixtures/plugins/fake_plugin.py` with the new kwargs.
9. **Tests in dependency order.** Unit cases first (AC-15 enumeration); module-purity / exhaustiveness AST scans; property test last (AC-16).

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/plugins/test_resolver.py`

```python
from codegenie.plugins.registry import PluginRegistry, register_plugin
from codegenie.plugins.resolver import UNIVERSAL_FALLBACK_ID, UniversalFallbackResolution
from codegenie.plugins.scope import PluginScope
from codegenie.types.identifiers import PluginId
from tests.fixtures.plugins.fake_plugin import make_fake_plugin
from tests.fixtures.plugins.universal_fallback_fixture import make_universal_fallback


def test_no_match_returns_universal_fallback() -> None:
    """ADR-0003 §Decision step 3 + §Consequences row 5: when no concrete
    plugin matches a scope and the universal fallback is registered, `resolve`
    returns `UniversalFallbackResolution` with `candidates_considered`
    listing every non-universal plugin in the registry (alphabetized). The
    fallback is a registered plugin, not a hardcoded code path; this is the
    type-level enforcement of production ADR-0009 (humans always merge).
    """
    registry = PluginRegistry()
    register_plugin(make_universal_fallback(), registry=registry)
    register_plugin(
        make_fake_plugin(
            name=PluginId("vulnerability-remediation--python--pip"),
            manifest_scope_kwargs={
                "task_class": "vulnerability-remediation",
                "languages": "python",
                "build_systems": "pip",
            },
        ),
        registry=registry,
    )

    scope = PluginScope.parse("distroless-migration--node--npm").unwrap()
    resolution = registry.resolve(scope)

    assert isinstance(resolution, UniversalFallbackResolution)
    assert resolution.kind == "universal_fallback"
    assert resolution.reason == "no_concrete_match"
    # python-pip plugin is in the registry, didn't match, so IS in candidates_considered
    assert resolution.candidates_considered == (
        PluginId("vulnerability-remediation--python--pip"),
    )
    # universal is excluded from candidates_considered (we resolved TO it)
    assert UNIVERSAL_FALLBACK_ID not in resolution.candidates_considered
```

Why it fails: `codegenie.plugins.resolver` doesn't exist; `PluginRegistry.resolve` still raises `NotImplementedError` from S2-01; `UNIVERSAL_FALLBACK_ID` symbol absent; `make_universal_fallback` fixture absent.

### Green follow-on — every AC-15 test name landed

After the red test goes green, land each of the following one at a time (verify each individually fails BEFORE the implementation lands, then passes AFTER):

- `test_exact_match_beats_wildcard` — AC-15 #2.
- `test_precedence_breaks_specificity_tie` — AC-15 #3.
- `test_name_breaks_precedence_tie` — AC-15 #4.
- `test_lift_manifest_scope_fans_out` (parametrized, 4 cases) — AC-15 #5.
- `test_extends_chain_composes_tccm_and_adapters_left_to_right` — AC-15 #6.
- `test_extends_depth_4_composes_correctly` — AC-15 #7.
- `test_extends_depth_5_raises_extends_depth_exceeded` — AC-15 #8.
- `test_extends_cycle_raises_plugin_extends_cycle` — AC-15 #9.
- `test_only_universal_registered_returns_universal_fallback` — AC-15 #10.
- `test_missing_universal_raises_plugin_registry_corrupted` — AC-15 #11.
- `test_extends_missing_target_raises_plugin_not_registered` — AC-15 #12.
- `test_candidates_considered_alphabetized_and_excludes_universal` — AC-15 #13.
- AST-scan tests (purity + exhaustiveness + single-source sentinel + no-NotImplementedError) — AC-13/14/2/12.
- Hypothesis property test `tests/unit/plugins/test_resolver_property.py:test_resolve_is_total` — AC-16.

### Refactor

- Pull `_sort_key`, `_unpack`, `_lift_dim` into named functions; small unit tests for each (each is independently mutation-target-rich).
- Move the `_dispatch_example(resolution: PluginResolution) -> str` helper into `test_resolver_exhaustiveness.py` and have mypy verify it (the `assert_never` in the `case _:` arm is the type-level proof).
- The Hypothesis property test uses three strategies: `concrete_plugin_name()` (forbids `UNIVERSAL_FALLBACK_ID`), `concrete_plugins()` (0..5 fake plugins), `incoming_scope()` (random PluginScope). Assertion uses an exhaustive `match` over `PluginResolution`.
- `candidates_considered` is computed via a helper; mutation: returning unsorted list → `test_candidates_considered_alphabetized_and_excludes_universal` fails.
- The literal `4` cap: pin via `_MAX_EXTENDS_DEPTH`; AST scan asserts the literal `4` appears at most once in `resolver.py`.

### Mutation kill-list (selection)

| # | Mutation | Catching test |
|---|---|---|
| M1 | Sort key reversed (`(specificity asc, ...)`) | `test_exact_match_beats_wildcard` |
| M2 | Precedence ignored in sort | `test_precedence_breaks_specificity_tie` |
| M3 | Name tie-break uses `desc` instead of `asc` | `test_name_breaks_precedence_tie` |
| M4 | `lift_manifest_scope` returns first element only (no cross-product) | `test_lift_manifest_scope_fans_out` (4 cases) |
| M5 | `extends` merge is right-to-left (later loses on collision) | `test_extends_chain_composes_tccm_and_adapters_left_to_right` |
| M6 | Cycle detection uses depth-check only (no visited-set) | `test_extends_cycle_raises_plugin_extends_cycle` (A→B→A at depth 2 is NOT depth-cap) |
| M7 | Depth-cap uses `>` instead of `>=` (off-by-one allows depth 5) | `test_extends_depth_5_raises_extends_depth_exceeded` |
| M8 | Universal-only registry raises `PluginRegistryCorrupted` instead of fallback | `test_only_universal_registered_returns_universal_fallback` |
| M9 | Missing universal silently returns first concrete | `test_missing_universal_raises_plugin_registry_corrupted` |
| M10 | `candidates_considered` includes universal | `test_candidates_considered_alphabetized_and_excludes_universal` |
| M11 | `candidates_considered` not alphabetized | same |
| M12 | `lift_manifest_scope` constructs `Concrete(value="*")` instead of `Wildcard()` | `test_lift_manifest_scope_fans_out[universal]` |
| M13 | `_unpack(Wildcard())` returns empty string | `test_resolve_is_total` property fails on incoming-wildcard cases |
| M14 | `manifest.name == "universal--*--*"` inlined; literal updated in one place only | `test_universal_fallback_id_single_source` AST scan |
| M15 | `match` block over `PluginResolution` missing `case _: assert_never` | `test_resolver_exhaustiveness` AST scan |
| M16 | `resolver.py` imports `pathlib` (impurity creep) | `test_resolver_purity` AST scan |
| M17 | `extends_chain` order reversed (leaf→root instead of root→leaf) | `test_extends_depth_4_composes_correctly` asserts `extends_chain[-1] is plugin` |
| M18 | `_MAX_EXTENDS_DEPTH` literal inlined at one site, refactor changes the constant only | AST scan asserts literal `4` appears at most once in `resolver.py` |

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/resolver.py` | NEW — `UNIVERSAL_FALLBACK_ID`, `ScopedCandidate`, `ComposedTccm` placeholder, `ConcreteResolution`, `UniversalFallbackResolution`, `PluginResolution` alias, `lift_manifest_scope`, `compose_extends_chain`, `resolve`, pure helpers. |
| `src/codegenie/plugins/registry.py` | Replace `NotImplementedError` in `resolve` with local-import delegation to `resolver.resolve`. |
| `src/codegenie/plugins/resolution.py` | Either deleted OR collapsed to a one-line re-export (`from codegenie.plugins.resolver import PluginResolution as PluginResolution`). Pick one; document in Notes §"Module placement". |
| `src/codegenie/plugins/errors.py` | Populate `PluginExtendsCycle(chain)`, `PluginRegistryCorrupted(reason)`, extend `PluginRejected` taxonomy with `extends_depth_exceeded` (additively, per S2-03's hardened tagged-union shape). |
| `tests/unit/plugins/test_resolver.py` | Unit + parametrized tests (AC-15 enumeration, 13 named tests). |
| `tests/unit/plugins/test_resolver_property.py` | Hypothesis property test (≥200 examples; deadline=None). |
| `tests/unit/plugins/test_resolver_purity.py` | Module-purity AST scan. |
| `tests/unit/plugins/test_resolver_exhaustiveness.py` | `match` + `assert_never` AST scan + mypy `_dispatch_example` helper. |
| `tests/static/test_universal_fallback_id_single_source.py` | AST scan asserting `"universal--*--*"` literal appears in at most two files. |
| `tests/static/test_no_notimplemented_in_registry.py` | AST scan asserting `NotImplementedError` is absent from `registry.py`. |
| `tests/fixtures/plugins/universal_fallback_fixture.py` | `make_universal_fallback()` — reused by S7-03's HITL plugin. |
| `tests/fixtures/plugins/fake_plugin.py` | Extend with `extends=`, `precedence=`, `manifest_scope_kwargs=` kwargs. |

## Out of scope

- **Concrete universal HITL subgraph behavior** — handled by S7-03 (writes sanitized handoff markdown, emits `RequiresHumanReview`). This story only needs a fixture plugin that registers as `universal--*--*`; its `build_subgraph` returns a stub.
- **`ComposedTccm` real shape + `provides`/`requires` merge semantics beyond the one-level-deep later-wins** — Step 3 (S3-01) lands the real `TCCM` Pydantic per ADR-0004. The placeholder defined here is intentional; the substitution point is documented in Notes §"TCCM substitution".
- **`composed_adapters` real `Adapter` implementations** — Step 7 / S7-02 lands npm-specific adapters. Resolver tests use stub `Adapter` instances; the composition logic (later-wins-on-collision) is what's exercised.
- **`PluginRegistryCorrupted` spanning-event emission** — that's the event log's concern (S6-01). This story raises the typed exception; the orchestrator (S6-04) maps it to event + exit code 4.
- **Plugin loader integration** — S2-03 already loads plugins; this story consumes whatever the loader registered. No loader changes here.
- **Per-plugin `RecipeRegistry`** — Step 5 / S5-01 (Gap 3 fix per phase-arch §Gap analysis line 1166).
- **Loader-time `extends` cycle / depth pre-check** — Notes §3 of the original story called this optional. The resolver's per-resolve cycle check is the contract; a startup pre-check is an additive safety net deferred to S2-03's hardened loader (already adopts verify-all-then-import-all per its validation).
- **Pre-loader integrity check that `extends` references resolve at startup time** — the resolver propagates `PluginNotRegistered` (a clean S2-01 exception); a loader-time pre-check is additive and deferred (see Notes §"Why `PluginNotRegistered` propagates").
- **`registry.all()` empty** — defensive `PluginRegistryCorrupted(reason="empty_registry")` is raised, but the loader's startup check (S2-03) is the canonical place to fail-fast on an empty registry; this story's raise is belt-and-braces.

## Notes for the implementer

### Why a `Final[PluginId]` sentinel, not a config knob

ADR-0003 §Decision step 3 reads literally "If the head plugin's id is `universal--*--*`". The string is the load-bearing convention. The hardening introduces `UNIVERSAL_FALLBACK_ID` as a typed `Final` constant so the literal lives in **one** place — adding S7-03's real fallback plugin, the `make_universal_fallback` fixture, and the loader's startup check all reference one symbol. **Do not parameterize the name.** Adding an alternate fallback (e.g., a team-specific HITL handler) is an ADR amendment, not a code-time decision. The AST single-source-of-truth scan catches a future contributor inlining the literal.

### Incoming scope discipline

The resolver receives a `PluginScope` from the orchestrator (S6-04). That `PluginScope` is constructed from `repo-context.yaml` evidence — the task class is always concrete; the language is determined by Phase 1's `LanguageDetection` (concrete OR ambiguous, but never `*` from a deterministic detector); the build system is similarly concrete. So in production, the *incoming* scope is fully Concrete on all three dims. Still, the resolver must handle wildcards in the incoming scope (for tests, for Phase 4's LLM-fallback experiments where intent is intentionally broader, and for `codegenie remediate --any-language`-style operator overrides). `_unpack(Wildcard()) -> "*"` and `PluginScope.matches(task="*", language=..., build=...)` returns True iff every plugin dim either is `Wildcard()` or its `Concrete.value == "*"` — but no plugin should declare `Concrete("*")` per S1-02's parser (which would lift `"*"` to `Wildcard()`). The result: incoming-scope wildcards match **every** plugin candidate on that dim, which is what an operator means by "I don't care about the language."

### `assert_never` discipline on `match resolution`

`assert_never` on `match resolution: case ConcreteResolution() | UniversalFallbackResolution(): ...` is the type-level enforcement that production ADR-0009 lives or dies on. mypy will catch a missed variant when Phase 4 adds (hypothetically) a `LlmFallbackResolution`; a reviewer will reject a `Plugin | None` regression. The `_dispatch_example` helper in `test_resolver_exhaustiveness.py` is **the** test asset that proves exhaustiveness today; do not delete it during refactor.

### Depth-cap empirical basis

`_MAX_EXTENDS_DEPTH = 4` is empirical (per ADR-0003 §Tradeoffs). The depth-5 test should construct a chain `A → B → C → D → E` and assert `PluginRejected(reason="extends_depth_exceeded", chain=(A, B, C, D, E))`. The chain length is 5; the *visited-set size at the point of the check* is what crosses the threshold (i.e., check fires when `len(visited) >= _MAX_EXTENDS_DEPTH` AND we are about to descend further — equivalently, when `len(visited) == 4` and we try to walk into the 5th level).

### Cycle chain shape

`A extends B extends A`. The cycle exception's `chain` field carries `(PluginId("A"), PluginId("B"), PluginId("A"))` — repeat the entry-point at the tail so an operator reading the stack can immediately see "we came back to where we started." This is more useful than `(A, B)`. Pin in the test: full-tuple equality.

### Left-to-right `extends` merge with later-wins-on-collision

When merging two adapter maps, `{**a, **b}` style suffices (Python dict update is "later wins"). But the *chain order* is `extends[0] applied first → extends[1] applied second → ... → plugin itself applied last`. The "leaf wins" property emerges from putting the plugin at the *end* of the chain (production ADR-0031 §Inheritance and override is explicit). Read it twice; this is the most common bug class in this story. The test `test_extends_chain_composes_tccm_and_adapters_left_to_right` pins it.

For `composed_tccm.provides` (a `dict[str, dict[str, str]]`), the inner dicts are also merged later-wins per-key (one-level deep). Beyond one level deep is out of scope — `TCCM` real shape lands in S3-01.

### Why `PluginNotRegistered` propagates

If `A extends B` and `B` is not in the registry, `registry.get(PluginId("B"))` raises `PluginNotRegistered(name=PluginId("B"))` per S2-01. The resolver does NOT catch this — three reasons:

1. The loader's startup integrity check (S2-03 hardened) should refuse to start when an `extends` target is missing; if this happens at resolve-time it's a real corruption case.
2. Catching here would force the resolver to re-emit a different typed error (e.g., `PluginRejected(reason="extends_target_missing")`), bloating the resolver's error surface.
3. `PluginNotRegistered` already carries `exit_code: ClassVar[int] = 4` per S2-01, so the orchestrator's outer handler maps it correctly.

The AC pins this propagation behavior so a future contributor doesn't "improve" it.

### TCCM substitution

`ComposedTccm` here is a minimal Pydantic placeholder (`provides: dict[str, dict[str, str]] = {}`, `requires: dict[str, tuple[str, ...]] = {}`). Step 3 / S3-01 lands the real `TCCM` per ADR-0004 §Decision. The substitution will be: change `ConcreteResolution.composed_tccm: ComposedTccm` → `composed_tccm: TCCM`. The resolver's left-to-right merge logic stays the same (the dict shapes line up); the property test grows new assertions about `must_read` / `should_read` / `may_read` query composition.

### Module placement (`resolver.py` vs `resolution.py`)

S2-01 shipped a placeholder `class PluginResolution: ...` in `src/codegenie/plugins/resolution.py`. This story can:

- (a) Move the real definitions into `resolver.py` and reduce `resolution.py` to a one-line re-export (`from codegenie.plugins.resolver import PluginResolution as PluginResolution`).
- (b) Move the real definitions into `resolution.py` and have `resolver.py` import from there.

Pick (a). Reason: callers already import `PluginResolution` from `resolution.py` (the S2-01 contract); the re-export preserves the import path. New consumers should import from `resolver.py`. Document in this story; the executor's `Files to touch` row for `resolution.py` is the one-line shim.

### Hypothesis strategy discipline

The strategy must NOT generate `UNIVERSAL_FALLBACK_ID` as a *concrete* plugin name — reserve that string for the fallback fixture. The `.filter(lambda s: s != "universal--*--*")` plus an `assume(name != UNIVERSAL_FALLBACK_ID)` is belt-and-braces. The property is non-negotiable; if the test gets flaky, debug the strategy (likely `max_examples` exhaustion against an over-tight filter), not the assertion.

### Mypy strictness

`PluginResolution` is `Annotated[ConcreteResolution | UniversalFallbackResolution, Field(discriminator="kind")]` — the discriminated `kind` is what Pydantic uses for narrowing at runtime; mypy uses the structural union for static narrowing. Annotate `resolve`'s return as `PluginResolution` (the typed alias). Do NOT annotate as `ConcreteResolution | UniversalFallbackResolution` — that bypasses the alias and produces a less-readable error message when a future variant is added.

### Sanitization of `candidates_considered`

`candidates_considered` carries `PluginId`s only, not paths or adapter import strings. The `PluginId` newtype (S1-01) is `str` at runtime but constrained at the smart-constructor boundary. Stating this in the docstring prevents a future contributor from "enriching" the list with file paths the operator never asked for. ADR-0003 §Consequences row 5 names the constraint.

### Property test is the headline assertion

`resolve` is total — never raises (modulo well-formedness assumptions on the registry), never returns `None`. The Hypothesis property test is the proof. If the test grows flaky or times out, debug the strategy and the `deadline=None` setting, NOT the assertion. The property is the contract.
