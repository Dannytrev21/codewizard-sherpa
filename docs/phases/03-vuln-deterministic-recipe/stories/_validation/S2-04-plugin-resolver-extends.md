# Validation report — S2-04 — Plugin resolver: `(specificity, precedence, name)` ordering + `extends` walker + `UniversalFallbackResolution`

**Validated:** 2026-05-18
**Validator:** phase-story-validator skill (autonomous run via story-validation-corrector scheduled task)
**Verdict:** **HARDENED**
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S2-04-plugin-resolver-extends.md`

---

## Context brief

S2-04 is Step 2's payoff: it lands the **ADR-0003 resolution algorithm** that maps a `PluginScope` (orchestrator intent from `repo-context.yaml`) to a typed `PluginResolution = ConcreteResolution | UniversalFallbackResolution`. The story replaces the `NotImplementedError("S2-04 …")` stub S2-01 shipped on `PluginRegistry.resolve`, walks `extends` chains with cycle + depth-4 caps, composes TCCM and adapters left-to-right (later-wins), and proves totality via Hypothesis.

**Critical context surfaced during validation:**

- **The `ManifestScope → PluginScope` lift is THIS story's responsibility.** Per `_validation/S2-02-plugin-manifest-pydantic.md §Arch amendments`, S2-02 ships `PluginManifest.scope: ManifestScope` (raw `str | list[str]` per dim — the production-ADR-0031 canonical YAML shape), NOT the post-lift `PluginScope`. Phase-arch §Data model line 755 incorrectly typed it as `PluginScope`; that's the arch follow-up still pending. S2-04 is the load-bearing lift point, and the lift is **fan-out via cross-product** (a manifest with `languages: [node, python]` produces two `PluginScope` candidates). The original story called `plugin.scope.matches(scope)` directly — wrong on three counts: (a) `plugin.scope` doesn't exist (`plugin.manifest.scope` does), (b) it's a `ManifestScope`, not a `PluginScope`, (c) the call ignores list fan-out entirely.
- **S1-02's `PluginScope.matches` signature is keyword-only `(*, task, language, build)` with `str` params**, NOT `matches(other: PluginScope)`. Per `_validation/S1-02-plugin-scope-sum-type.md §K-F3`, the kernel stays task-class-agnostic and `matches` takes raw strings. Story originally used the wrong signature.
- **Arch §Data model line 779 names `ConcreteResolution.matched_scope: PluginScope`** — the lifted scope that filtered through. Original story omitted this field from the AC; the property test invariant `resolution.matched_scope.matches(...)` depends on it.
- **`UNIVERSAL_FALLBACK_ID` sentinel discipline.** ADR-0003 §Decision step 3: "if the head plugin's id is `universal--*--*`". The string `"universal--*--*"` will appear in: (1) the resolver's narrowing check, (2) `S7-03`'s real fallback plugin manifest, (3) `make_universal_fallback()` test fixture, (4) the loader's startup `default_registry.get(...)` check (ADR-0003 §Consequences). The original story inlined the literal; hardened to a module-level `Final[PluginId]` constant with an AST single-source-of-truth scan.
- **`candidates_considered` semantics.** ADR-0003 §Consequences row 5: "concrete plugins were filtered out — operator can see which concrete plugins were filtered out and why." Original story said "filtered-but-not-chosen concrete plugins" with two contradictory interpretations: (a) tail of the sorted matches list, (b) all concrete plugins in the registry whose lifted scopes did NOT match the incoming scope. Per ADR-0003 §Consequences row 5 and the intended debug surface, interpretation (b) is correct — and is now pinned in AC-10.

**Load-bearing siblings + precedents:**
- `_validation/S2-02-plugin-manifest-pydantic.md` — `ManifestScope` shape; arch follow-up that `S2-04 produces a ResolvedManifest whose scope: PluginScope is the lifted form`.
- `_validation/S2-03-plugin-loader-integrity.md` — tagged-union sum-type for errors (`PluginRejected` seven-variant); AST-source-scan fences for chokepoint discipline; Strategy seam via Protocol (`PluginVerifier`). This story's hardening reuses the AST-scan pattern (single-source-of-truth for `UNIVERSAL_FALLBACK_ID`; absence of `NotImplementedError`).
- `_validation/S2-01-plugin-registry-kernel.md` — `register -> Plugin` return type; `_visited` discipline foreshadowed; fresh-instance fixture for test isolation.
- `_validation/S1-02-plugin-scope-sum-type.md` — `matches(*, task, language, build) -> bool` signature; `__str__` round-trip; AST module-purity scan precedent; Hypothesis strategies for `scope_dims()` (reuse for resolver property strategy).
- `_validation/S1-03-tagged-union-outcomes.md` — discriminator-on-`kind`; `assert_never` AST exhaustiveness scan precedent; `EscalationReason` literals including `"plugin_extends_cycle"`.
- ADR-0003 line 18 (Option C): "the kernel has no `if plugin.id == 'universal--*--*':` branch outside the resolver" — informs the `UNIVERSAL_FALLBACK_ID` single-source-of-truth scan.
- ADR-0031 (production) §Inheritance and override: "later wins on collision" for `extends` chain composition — the test pin in AC-15 #6.

**Original story strengths (preserved):**

- Correctly cited ADR-0003 / ADR-0002 / ADR-0010 / production ADR-0031 / production ADR-0009 across References, Notes, and the Implementation outline.
- Goal correctly identified the four load-bearing commitments: tagged-union return, universal-as-registered-plugin, `extends` walker with cycle+depth check, Hypothesis totality property.
- Out-of-scope cleanly separated S3-01 (real TCCM), S7-02 (real adapters), S7-03 (universal HITL subgraph), S6-01 (event emission), S5-01 (per-plugin RecipeRegistry).
- Honest framing: cycle is a startup-time concern, not a per-resolve concern (preserved in Notes §"Property test is the headline assertion").
- Notes correctly warned "do not parameterize the universal name" (now elevated to a typed Final constant + AST scan).
- Implementation outline §2's `_visited=None → fresh; depth is len(_visited)` was conceptually right but the mutable-default antipattern made it brittle (hardened to `frozenset[PluginId] | tuple[PluginId, ...]` thread-through).

**Original story weaknesses (resolved):**

- **`plugin.scope` shape wrong (Consistency C-F1, `block`).** Per S2-02 hardened, `plugin.manifest.scope` is a `ManifestScope` (raw `str | list[str]`), not a `PluginScope`. Story bypassed the lift entirely.
- **`matches` signature wrong (Consistency C-F2, `block`).** S1-02 ships `matches(*, task: str, language: str, build: str) -> bool` (keyword-only, `str` params); story used `plugin.scope.matches(scope)` passing a `PluginScope`.
- **List fan-out missing (Consistency C-F3 / Coverage Cov-F1, `block`).** `ManifestScope.languages: str | list[str]` allows multi-value; story silently ignored. A plugin with `languages: [node, python]` must produce two `PluginScope` candidates.
- **`matched_scope: PluginScope` missing from `ConcreteResolution` AC (Coverage Cov-F2 / Consistency C-F4, `block`).** Arch §Data model line 779 names it; property test invariant depends on it.
- **`candidates_considered` semantics ambiguous (Coverage Cov-F3 / Consistency C-F5, `block`).** Original "filtered-but-not-chosen concrete plugins" admits two readings; ADR-0003 §Consequences row 5 disambiguates to "in registry but didn't match the incoming scope".
- **Magic-string `"universal--*--*"` (Design-Patterns DP-F1, `block`).** Inlined in the algorithm; should be a typed `Final[PluginId]` sentinel. Compounds with the `make_universal_fallback` fixture (also references the same string) and with S7-03 (real plugin manifest).
- **Only one red test for ten distinct AC paths (Test-Quality TQ-F1, `block`).** S2-03 precedent (AC-7 parametrized) was clearly the right pattern; story had one test.
- **No mutation-resistance for left-to-right `extends` merge (Test-Quality TQ-F2, `block`).** Refactor §3 mentioned "later wins on collision" but no concrete test would catch a right-to-left mutant.
- **No "only universal registered" test (Coverage Cov-F4, `block`).** Edge case: empty concrete set, universal alone. Per the algorithm, sort produces a length-1 list with universal as head → narrows to `UniversalFallbackResolution`. Original story did not pin this.
- **No "extends target not registered" test (Coverage Cov-F5, `harden`).** `A extends B` where `B` is not registered; what raises? Hardened: `PluginNotRegistered` propagates from `registry.get`; AC pins the propagation.
- **`_visited=None` mutable-default antipattern (Design-Patterns DP-F2, `harden`).** Recursion threads a private parameter; better to use `frozenset` + `tuple` accumulator for the path.
- **`PluginResolution` placeholder module location ambiguous (Consistency C-F6, `harden`).** S2-01 shipped `src/codegenie/plugins/resolution.py` with `class PluginResolution: ...` placeholder. Story did not pin where the real definitions land. Hardened: `resolver.py` is the source-of-truth; `resolution.py` becomes a one-line re-export.
- **`PluginRegistryCorrupted` confusion (Consistency C-F7, `harden`).** ADR-0003 §Consequences line 50 names a *spanning event*; phase-arch §C2 line 483 lists the *exception family*. Story conflated them; hardened to: this story raises the *typed exception*; S6-01 maps to the event.
- **Sort key as a free function or method? (Design-Patterns DP-F3, `harden`).** Story's `_sort_key(plugin) -> tuple[int, int, str]` ignored the lifted scope (which carries the relevant `specificity`). Hardened: `_sort_key(c: ScopedCandidate)` — scope-on-the-candidate is the right shape.
- **Magic-number `4` cap (Design-Patterns DP-F5, `harden`).** Hardcoded depth cap; mutation-target. Hardened to `_MAX_EXTENDS_DEPTH: Final[int] = 4` with AST scan asserting the literal `4` appears at most once.
- **`assert_never` exhaustiveness AST scan not pinned (Test-Quality TQ-F3, `harden`).** S1-02 / S1-03 precedent uses AST AC; story only mentioned in Refactor.
- **Module purity AST scan not pinned (Test-Quality TQ-F4, `harden`).** S1-02 AC-21 / S2-03 precedent. Resolver is kernel code; hardened to AC-13 with explicit allowlist.
- **`extends_chain` ordering ambiguity (Coverage Cov-F6, `harden`).** Original AC said "leaf is `plugin` itself" but didn't pin the ordering of the rest (root→leaf or extends-order). Hardened: extends walked first applies first; `extends_chain[-1] is plugin`; test pins via tuple equality.
- **Hypothesis strategy underspecified (Test-Quality TQ-F5, `harden`).** Original Notes warned "strategy must not generate `universal--*--*` as concrete" but no AC pinned it. Hardened: AC-16 explicitly names the `.filter()` + `assume()` and the `max_examples=200; deadline=None` settings.

---

## Stage 2 — Four critic reports (single-agent synthesis)

Following Rule 6 (token-budget discipline), the four critics were synthesized into a single analysis pass rather than spawning four parallel agents. The framing remained four-lens. Severity tags: `block` (story must change), `harden` (story improved by change), `nit` (cosmetic).

### Coverage critic — 6 findings

| ID | Severity | Title | Resolution |
|---|---|---|---|
| Cov-F1 | block | `ManifestScope → PluginScope` lift missing — story calls `plugin.scope.matches(...)` against a type that doesn't exist | Applied — AC-7 (`lift_manifest_scope` with 4-case parametrized fan-out) + AC-8 (`_lift_candidates` flat-map) + Notes §"Why a `Final[PluginId]` sentinel". List fan-out is the cross-product. |
| Cov-F2 | block | `ConcreteResolution.matched_scope: PluginScope` missing from AC | Applied — AC-4 lists `matched_scope: PluginScope` explicitly; AC-16 property invariant depends on it. |
| Cov-F3 | block | `candidates_considered` semantics ambiguous | Applied — AC-10 pins to "alphabetized tuple of concrete plugin names in registry that did NOT match the incoming scope, excluding `UNIVERSAL_FALLBACK_ID`". AC-15 #13 test exercises ordering + exclusion. |
| Cov-F4 | block | "Only universal registered" edge not tested | Applied — AC-15 #10 `test_only_universal_registered_returns_universal_fallback`; AC-9 step 3 explicitly returns fallback when matches is empty AND universal is in registry. |
| Cov-F5 | harden | "Extends target not registered" behavior not pinned | Applied — AC-15 #12 `test_extends_missing_target_raises_plugin_not_registered`; Notes §"Why `PluginNotRegistered` propagates" documents the rationale (loader pre-check is the right place; resolver propagates). |
| Cov-F6 | harden | `extends_chain` ordering ambiguous (root→leaf vs extends-order vs leaf→root) | Applied — AC-15 #7 asserts `extends_chain[-1] is plugin`; Notes §"Left-to-right `extends` merge" articulates the chain order (`extends[0] first, ..., plugin last`); mutation kill-list M17 catches reversal. |

### Test-Quality critic — 5 findings

| ID | Severity | Title | Resolution |
|---|---|---|---|
| TQ-F1 | block | One red test for ten distinct AC paths | Applied — AC-15 enumerates 13 concrete named tests; TDD plan "Green follow-on" lists each by name (mirrors S2-03 hardened precedent). |
| TQ-F2 | block | No mutation-resistance for left-to-right `extends` merge | Applied — AC-15 #6 `test_extends_chain_composes_tccm_and_adapters_left_to_right` pins both `composed_adapters` (single-level later-wins on `Foo`; `Bar` added) AND `composed_tccm.provides` (one-level-deep per-key later-wins). Mutation M5 catches right-to-left. |
| TQ-F3 | harden | `assert_never` exhaustiveness AST scan not pinned | Applied — AC-14 introduces `tests/unit/plugins/test_resolver_exhaustiveness.py` with AST scan + a `_dispatch_example` mypy-typechecked helper. S1-02 AC-14 precedent. |
| TQ-F4 | harden | Module purity AST scan not pinned | Applied — AC-13 introduces `tests/unit/plugins/test_resolver_purity.py` with an explicit allowlist (no `os` / `pathlib` / `logging`). S1-02 AC-21 precedent. |
| TQ-F5 | harden | Hypothesis strategy underspecified | Applied — AC-16 names `concrete_plugin_name()` strategy with `.filter()` + `assume()` to forbid `UNIVERSAL_FALLBACK_ID`; `@settings(max_examples=200, deadline=None)`; exhaustive `match` over `PluginResolution` at the assertion site (so adding a future variant breaks the property's `assert_never`). |

### Consistency critic — 7 findings

| ID | Severity | Title | Resolution |
|---|---|---|---|
| C-F1 | block | `plugin.scope` doesn't exist; `plugin.manifest.scope: ManifestScope` does (S2-02 hardened) | Applied — AC-7 + AC-8 + AC-9 step 2 reference `plugin.manifest.scope` and route through `lift_manifest_scope`. Validation notes header documents the lift seam. |
| C-F2 | block | `matches(*, task, language, build) -> bool` keyword-only (S1-02 hardened) | Applied — AC-9 step 2 + Notes §"Incoming scope discipline" pin the keyword call form; `_unpack(ScopeDim) -> str` converts the incoming `PluginScope` dims for the call. |
| C-F3 | block | `ManifestScope` list fan-out (S2-02 AC-3) | Applied — AC-7 fan-out is the cross-product over the three dims; AC-15 #5 parametrized table pins 4 specific cases. |
| C-F4 | block | `ConcreteResolution.matched_scope: PluginScope` (arch §Data model line 779) | Applied — see Coverage Cov-F2. |
| C-F5 | block | `candidates_considered` semantics (ADR-0003 §Consequences row 5) | Applied — see Coverage Cov-F3. |
| C-F6 | harden | `PluginResolution` module location undeclared | Applied — Notes §"Module placement" pins `resolver.py` as source-of-truth; `resolution.py` becomes a one-line re-export to preserve the S2-01-shipped import path. |
| C-F7 | harden | `PluginRegistryCorrupted` exception vs event conflated | Applied — AC-9 step 4 raises the typed exception; Out-of-scope expanded with "spanning-event emission deferred to S6-01"; Notes §"Module placement" cross-references. |

### Design-Patterns critic — 6 findings

| ID | Severity | Title | Resolution |
|---|---|---|---|
| DP-F1 | block | Magic-string `"universal--*--*"` inlined | Applied — AC-2 introduces `UNIVERSAL_FALLBACK_ID: Final[PluginId]`; AST single-source-of-truth scan (`tests/static/test_universal_fallback_id_single_source.py`) asserts at most two occurrences in the codebase (resolver + fixture). Compounds with S7-03's future real-plugin manifest reference. Notes §"Why a `Final[PluginId]` sentinel, not a config knob" preserves the no-config-knob discipline. |
| DP-F2 | harden | `_visited=None` mutable-default antipattern | Applied — `compose_extends_chain` threads `visited: frozenset[PluginId]` (immutable) + `visited_path: tuple[PluginId, ...]` (immutable accumulator for cycle-chain reporting). AC-11 + Implementation outline §5 pin the shape. |
| DP-F3 | harden | `_sort_key(plugin)` shape ignored lifted scope | Applied — `_sort_key(c: ScopedCandidate) -> tuple[int, int, str]` returns `(-c.lifted_scope.specificity(), -c.plugin.manifest.precedence, c.plugin.manifest.name)`. Negation for descending; tuple naturally ascending. |
| DP-F4 | harden | Functional-core / imperative-shell tangle in `resolve` | Applied — Implementation outline §4 splits pure helpers (`_lift_dim`, `lift_manifest_scope`, `_lift_candidates`, `_unpack`, `_filter_matches`, `_sort_key`, `_candidates_considered`) from the orchestrating `resolve`. Each pure helper independently mutation-target-rich. AC-13 module-purity scan enforces. |
| DP-F5 | harden | Magic-number `4` cap | Applied — AC-17 introduces `_MAX_EXTENDS_DEPTH: Final[int] = 4`; AST scan asserts literal `4` appears at most once in `resolver.py`. Mutation kill-list M18. |
| DP-F6 | nit | `ScopedCandidate` typed dataclass vs raw tuple | Applied — AC-3 introduces `@dataclass(frozen=True, slots=True) class ScopedCandidate: plugin: Plugin; lifted_scope: PluginScope` for naming clarity. |

---

## Stage 3 — Researcher

**Not invoked.** No critic finding was tagged `NEEDS RESEARCH`. All resolutions reuse this codebase's established precedents:

- `_validation/S1-02-plugin-scope-sum-type.md` — `matches(*, task, language, build)` keyword-only signature; AST module-purity AC-21; Hypothesis `scope_dims()` strategy form.
- `_validation/S1-03-tagged-union-outcomes.md` — `Annotated[..., Field(discriminator="kind")]` discipline; `assert_never` AST exhaustiveness; `EscalationReason` literal taxonomy that includes `"plugin_extends_cycle"`.
- `_validation/S2-01-plugin-registry-kernel.md` — fresh-`PluginRegistry()` test isolation; autouse `restore_default_registry` fixture; `register -> Plugin` return.
- `_validation/S2-02-plugin-manifest-pydantic.md §Arch amendments` — `PluginManifest.scope: ManifestScope`; precedence default 50; arch follow-up logged ("S2-04 produces a ResolvedManifest").
- `_validation/S2-03-plugin-loader-integrity.md` — Strategy seam via Protocol (`PluginVerifier`); AST source-scan fences (chokepoint discipline); tagged-union sum type for errors; parametrized per-variant tests; verify-all-then-import-all order pinned via AC.
- ADR-0003 §Decision (steps 1–4) and §Consequences (row 5 — `candidates_considered` semantics; line 50 — `PluginRegistryCorrupted` spanning event vs exception distinction).
- Production ADR-0031 §Inheritance and override — left-to-right merge with later-wins on collision.
- `src/codegenie/types/identifiers.py` (Phase 0 / S1-01) — `PluginId` newtype + smart constructor.

---

## Stage 4 — Edits applied to story

The story file was rewritten in place. Substantive changes:

1. **Status** raised from `Ready` to `HARDENED`. Validation notes block appended under header.
2. **Depends on** list corrected to include S1-02 (`PluginScope`), S1-03 (tagged-union discipline), S2-02 (`ManifestScope` shape — pre-lift), S2-03 (loader + `PluginRejected` taxonomy). Original story listed only S2-02 / S2-03.
3. **Context** rewritten to enumerate four load-bearing commitments instead of two — adds the `ManifestScope → PluginScope` lift seam and the `extends` walker as separate commitments.
4. **References** expanded to include the four sibling `_validation/` reports (S1-02, S1-03, S2-01, S2-02, S2-03) and the arch line-numbers (lines 479, 486–514, 392–411, 775–791, 779).
5. **Acceptance criteria** restructured (19 ACs, each individually verifiable):
   - AC-1: module surface + `__all__` (alphabetized) + stowaway-export test.
   - AC-2: `UNIVERSAL_FALLBACK_ID: Final[PluginId]` sentinel + AST single-source-of-truth scan.
   - AC-3: `ScopedCandidate` frozen dataclass.
   - AC-4: `ConcreteResolution` Pydantic with `matched_scope: PluginScope` (per arch §Data model line 779).
   - AC-5: `UniversalFallbackResolution` Pydantic with `candidates_considered: tuple[PluginId, ...]` (immutable).
   - AC-6: `PluginResolution` discriminated alias (`Annotated[..., Field(discriminator="kind")]`).
   - AC-7: `lift_manifest_scope` cross-product fan-out with 4 parametrized examples.
   - AC-8: `_lift_candidates` flat-map.
   - AC-9: 7-step resolution algorithm pinned with `_unpack` discipline.
   - AC-10: `candidates_considered` semantics pinned (alphabetized; excludes universal).
   - AC-11: `compose_extends_chain` with `frozenset[PluginId]` + `tuple[PluginId, ...]` accumulator; `PluginNotRegistered` propagation; left-to-right merge.
   - AC-12: `PluginRegistry.resolve` delegation; AST scan for `NotImplementedError` absence.
   - AC-13: module-purity AST scan with explicit allowlist.
   - AC-14: exhaustiveness `match` + `assert_never` AST scan + mypy `_dispatch_example` helper.
   - AC-15: 13 named tests in dependency order.
   - AC-16: Hypothesis property test with strategy specifications + `max_examples=200; deadline=None`.
   - AC-17: `_MAX_EXTENDS_DEPTH: Final[int] = 4` with AST literal-uniqueness scan.
   - AC-18: fixtures (`make_universal_fallback`, extended `make_fake_plugin`).
   - AC-19: lint + mypy clean on all new files.
6. **Implementation outline** restructured into 9 numbered steps with explicit pure-helper ordering (Implementation outline §4 lists 7 pure helpers in dependency order).
7. **TDD plan** expanded:
   - Red test rewritten to use `make_universal_fallback`, `PluginId`, `manifest_scope_kwargs`, exact-tuple-equality assertion on `candidates_considered`, and `UNIVERSAL_FALLBACK_ID` symbol import.
   - Green follow-on lists every AC-15 test name + AST-scan tests + Hypothesis property.
   - Refactor section preserved + extended (named helpers, `_dispatch_example` helper, `_MAX_EXTENDS_DEPTH` constant).
   - Mutation kill-list table (18 mutations) added — every mutation has a named catching test.
8. **Files to touch** expanded from 7 to 12 paths:
   - `src/codegenie/plugins/resolution.py` — collapsed to one-line re-export.
   - `tests/unit/plugins/test_resolver_purity.py` — module-purity AST scan.
   - `tests/unit/plugins/test_resolver_exhaustiveness.py` — exhaustiveness AST scan.
   - `tests/static/test_universal_fallback_id_single_source.py` — AST scan.
   - `tests/static/test_no_notimplemented_in_registry.py` — AST scan.
9. **Out of scope** expanded:
   - Loader-time `extends` cycle / depth pre-check (deferred to S2-03's hardened loader).
   - Loader-time integrity check for `extends` target presence.
   - `registry.all()` empty case is defensive belt-and-braces (canonical fail-loud is in S2-03 loader).
10. **Notes for the implementer** restructured into 11 subsections covering: sentinel discipline, incoming scope semantics, `assert_never` discipline, depth-cap basis, cycle chain shape, left-to-right merge gotcha, `PluginNotRegistered` propagation rationale, TCCM substitution point, module placement decision, Hypothesis strategy discipline, mypy strictness, `candidates_considered` sanitization, property-test-is-the-contract.

The original story's substance (the algorithm, the totality property, cycle detection, the universal-fallback-as-plugin discipline) is preserved. The validator only **tightened ACs into individually verifiable assertions**, **introduced the `ManifestScope → PluginScope` lift seam** that the rest of Phase 3 implicitly assumes, **refactored the resolver into a functional-core / imperative-shell split with 7 pure helpers**, **promoted the magic string + magic number to typed `Final` constants with AST single-source-of-truth scans**, **parametrized the TDD plan into 13 named tests + a Hypothesis property + 18-row mutation kill-list**, and **pinned `candidates_considered` semantics + `_unpack` incoming-scope discipline**. No scope change.

---

## Arch follow-up (carried forward; not a story edit)

The arch follow-up logged in `_validation/S2-02-plugin-manifest-pydantic.md` remains pending:

- **`phase-arch-design.md` line 755**: `scope: PluginScope` → `scope: ManifestScope` on the load-time `PluginManifest`. Document the post-lift `ResolvedManifest.scope: PluginScope` (or `ConcreteResolution.matched_scope: PluginScope`) as the form S2-04 produces.

This story's hardening makes the lift seam visible in the AC surface, which partially addresses the arch gap. A clean fix is still a one-line arch edit + a `ResolvedManifest` model OR keeping the lift inside the resolver (current direction). No action required for this story; logged for the phase-architect skill's next pass.

---

## Verdict — HARDENED

The story now passes the four critics:

- **Coverage:** every AC is individually verifiable; the four list-fan-out cases are parametrized; both universal-only-registry and missing-universal edges are tested; `extends_chain` ordering pinned via tuple equality; `candidates_considered` semantics + ordering + exclusion are tested; `PluginNotRegistered` propagation is tested.
- **Test-Quality:** every AC has at least one concrete test that would fail under an obvious mutation (18-row mutation kill-list). The left-to-right merge gets dedicated tests for both `composed_adapters` and `composed_tccm.provides`. AST source-scan fences guard the literal `"universal--*--*"`, the literal `4`, `NotImplementedError` removal, exhaustiveness `match` arms, and module purity. The Hypothesis property test catches the wide class of "resolver became partial" mutations.
- **Consistency:** every chokepoint (S1-02 `matches` keyword signature, S2-02 `ManifestScope` shape, S2-01 `register -> Plugin` return) is routed correctly; the `ManifestScope → PluginScope` lift seam is explicit; `candidates_considered` semantics match ADR-0003 §Consequences row 5; `PluginResolution` module placement is pinned; `PluginRegistryCorrupted` is the typed exception, the spanning event is S6-01.
- **Design-Patterns:** Tagged union (`PluginResolution`) makes "no concrete match" type-impossible to silently drop; Open/Closed at the kernel (`UNIVERSAL_FALLBACK_ID` sentinel + AST single-source-of-truth scan keeps the kernel free of `if plugin.id == X` branches outside the resolver itself); functional core / imperative shell (7 named pure helpers); Strategy pattern preserved via the `ScopedCandidate` lift seam (Phase 4's `LlmFallbackResolution` could land additively as a new union variant + a new strategy in the same flow); make-illegal-states-unrepresentable via the discriminated `kind: Literal[...]` discipline; primitive obsession on universal-ID and depth-cap is removed.

Ready for `phase-story-executor`.
