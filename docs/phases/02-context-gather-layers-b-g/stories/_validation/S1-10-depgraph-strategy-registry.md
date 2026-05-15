# Validation report — S1-10 `codegenie.depgraph` + `@register_dep_graph_strategy` registry

**Story:** [`../S1-10-depgraph-strategy-registry.md`](../S1-10-depgraph-strategy-registry.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story stands up the 3rd registry of the decorator-registry family in this codebase: `codegenie.depgraph.registry` joins `codegenie.probes.registry` (Phase 0) and `codegenie.indices.registry` (S1-02) under the same `register / dedup-by-named-origins / registered_X / unregister_for_tests / module-level singleton + decorator` shape. Phase 2 ships **zero strategies**; Phase 3 plugin packages (e.g., `plugins/vulnerability-remediation--node--npm/strategies/dep_graph_pnpm.py`) register the first `build_pnpm` strategy by **new file + new decorator** — `DepGraphProbe` (S4-05) is never edited.

The draft was structurally sound (no RESCUE-tier findings; the decorator-registry shape correctly mirrors S1-02's precedent). Eight harden-tier gaps were closed:

1. **`PackageManager` is a `Literal[...]`, not an Enum** — the draft tests' `PackageManager.PNPM if hasattr(PackageManager, "PNPM") else "pnpm"` defensive ternary collapsed to bare strings at runtime (the `hasattr` branch is dead code). Verified at `src/codegenie/probes/node_build_system.py:115`. Tests rewritten to use `cast(PackageManager, "pnpm")` and an `ALL_PACKAGE_MANAGERS` tuple over the five Phase 1 Literal members.
2. **Decorator return-identity untested** (`reg.register(eco)(fn) is fn`) — a `register` that returned `None` would have passed the draft. New AC-10 + dedicated test.
3. **Strategy argument-order + return-identity untested** — the draft's tests passed `_make_ctx, []` and asserted `isinstance(g, networkx.DiGraph)`, but never that the strategy received `ctx` and `manifests` in the documented positional order, and never that `dispatch` returned the strategy's exact graph (not a copy/wrapper). New AC-11 + dedicated sentinel-identity test. (Same class of silent mutation S1-02's hardening caught for `slice`/`head`.)
4. **Duplicate-error message format untested for "both call sites named as `module.qualname`"** — AC-2 said "raises DepGraphRegistryError" but no test pinned the message shape; a regression that stripped origins to bare `__qualname__` would have passed. AC-2 strengthened, dedicated test added (mirrors S1-02 validation finding #4).
5. **`registered_ecosystems()` had no AC** — implementation outline named it but its return type, ordering, and empty-registry behavior were not pinned. New AC-12 + dedicated test.
6. **`DepGraphRegistryError` in `errors.__all__` was not pinned** — outline §4 said "append" but `__all__` was silent. A regression that omits the export from `__all__` would pass linting. New AC-13.
7. **Module-level decorator singleton test used a non-`PackageManager` string** (`"__test_singleton_eco__"` with `# type: ignore[arg-type]`) — bypassed both the type contract and the singleton's pre-condition assertion. Rewritten to use `BUN` (a real Phase 1 Literal member), with `assert default_dep_graph_registry.has_strategy(BUN) is False` pre- and post-conditions to prove no test leak.
8. **AC-4 dispatch-error reason format under-specified** — "in `args[0]`" was vague; tightened to `args[0]` begins with the literal prefix `no_strategy_for_ecosystem: ` followed by `repr(ecosystem)`. S4-05's downstream translation logic matches on this prefix.

The Acceptance criteria block expanded from 12 ACs to 16 ACs (numbering shifted for the new pins). The TDD plan grew from 7 tests to 13 tests. Implementation outline + Notes for the implementer rewritten to lock in:

- `Mapping[str, Any]` manifest shape as **final** (verified by source scan — no `Manifest` Pydantic model in `src/codegenie/`).
- Rule-of-three kernel-extract opportunity **deferred** to a post-Phase-2 cleanup story (3 sites diverge on dispatch shape; mid-phase extract is scope-creep). The deferral mirrors S1-02's explicit deferral note; the opportunity is recorded so it survives.
- Dispatch contract: **identity, not equality** — no defensive copy/wrap.

No `NEEDS RESEARCH` findings (Stage 3 skipped — every gap was answerable from the arch, ADR-0006, the S1-02 hardening precedent, and a direct source scan against `src/codegenie/`).

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim):** Implement `src/codegenie/depgraph/{__init__.py, model.py, registry.py}` — `@register_dep_graph_strategy(ecosystem: PackageManager)` decorator-registry returning `Callable[[ProbeContext, list[Manifest]], networkx.DiGraph]` strategies, **zero strategies registered in Phase 2**, with typed `DepGraphRegistryError` on unknown ecosystem dispatch.
- **Non-goals:** any actual ecosystem strategy implementation (Phase 3); `DepGraphProbe` itself (S4-05); `Manifest` Pydantic model; Maven/Cargo/Gradle (Phase 8+); multi-ecosystem cross-resolution.

### Phase 2 exit criteria touched

- G9 (kernel scaffolding ships before Phase 3).
- The Open/Closed seam for `DepGraphProbe` (B5) — adding a new ecosystem strategy is a new file + new decorator + ADR-amend on `PackageManager`, never an edit to `DepGraphProbe`.
- 02-ADR-0007 ("No plugin loader in Phase 2") — the registry IS the explicit-imports collection point Phase 3 fills, but Phase 2 ships zero.

### Load-bearing commitments touched

- **CLAUDE.md §"Extension by addition"** — the registry is the addition seam; Phase 3 adds strategies as new files.
- **Production ADR-0033 §3 (no primitive obsession on domain identifiers)** — `PackageManager` is the typed registry key; raw `str` is a review-blocker (enforced by `mypy --strict` over the `dict[PackageManager, …]` typing).
- **02-ADR-0006 §Decisions noted (registry symmetry)** — `register / dispatch / has_strategy / registered_X / unregister_for_tests` shape symmetric with `@register_index_freshness_check` and `@register_probe`.

### Sibling-family lineage

- **This story is the 3rd concrete consumer of the decorator-registry family.**
  - 1st: `codegenie.probes.registry` (Phase 0) — `Registry.register / for_task` + module-level `register_probe` decorator.
  - 2nd: `codegenie.indices.registry` (S1-02) — `FreshnessRegistry.register / dispatch_all / registered_names / unregister_for_tests`.
  - 3rd: `codegenie.depgraph.registry` (this story) — `DepGraphRegistry.register / dispatch / has_strategy / registered_ecosystems / unregister_for_tests`.
- **Rule-of-three threshold:** **REACHED** for a shared `KernelRegistry[K, V]` base. However, dispatch-shape divergence (filter+LRU / total-dispatch / single-dispatch+query) keeps the shared lines below the cost-of-introducing-a-generic threshold mid-phase. **Decision: defer to a post-Phase-2 cleanup story** (mirrors S1-02 validator's explicit deferral; recorded in Notes for the implementer).
- **Prior validation framings carried forward:**
  - S1-02: `module.qualname` in duplicate-error message; `unregister_for_tests` test-only convenience; registration-time (not dispatch-time) duplicate detection; module-level singleton + thin decorator-factory wrapper.

### Phase / arch constraints

- **`phase-arch-design.md §"Component design" #11 (DepGraphProbe + strategy registry)`** — public interface, `@register_dep_graph_strategy(ecosystem=PackageManager.PNPM)` shape (the arch uses Enum-style syntax loosely; `PackageManager` is actually a `Literal`), "zero strategies in Phase 2" rule, low-confidence fallback contract.
- **`phase-arch-design.md §"Design patterns applied"` row 5** — "Adding Maven (Phase 8+) is a new file + decorator, never an edit to `DepGraphProbe`. String-keyed dict — Phase 3 deferral was the exact ADR-0033 violation the critic flagged."
- **02-ADR-0006 §Consequences last bullet** — names `@register_dep_graph_strategy` symmetric with `@register_index_freshness_check` and `@register_probe`.

### Goal-to-AC trace

| AC | Goal coverage |
|---|---|
| AC-1 | Public surface — package exports |
| AC-2 | Decorator behavior + duplicate detection at register-time (NOT dispatch-time) |
| AC-3 | Strategy-signature shape (key contract for Phase 3 plugin authors) |
| AC-4 | Dispatch contract + unknown-ecosystem error format (S4-05 translation token) |
| AC-5 | Non-raising query API (lets `DepGraphProbe` short-circuit without exception flow) |
| AC-6 | Phase 2 ships ZERO strategies (load-bearing — 02-ADR-0007) |
| AC-7 | `PackageManager` re-export discipline (production ADR-0033, S1-05 contract) |
| AC-8 | Round-trip register/dispatch/has_strategy with identity assertion |
| AC-9 | Unknown-ecosystem error format precision |
| AC-10 | Decorator return-identity (NEW — non-invasive registration mutation pin) |
| AC-11 | Strategy invocation contract (NEW — argument-swap + return-wrap mutation pin) |
| AC-12 | `registered_ecosystems()` contract (NEW — was in outline only, no AC) |
| AC-13 | `DepGraphRegistryError` in `errors.__all__` (NEW — was silent in outline) |
| AC-14 | `forbidden-patterns` discipline (model_construct ban — S1-11 target) |
| AC-15 | Red-test exists and is green |
| AC-16 | Static-check + test commands all pass |

### Open ambiguities

None. The story's only mid-flight ambiguity was the `Manifest` Pydantic model: source scan confirmed it does not exist, so `Mapping[str, Any]` is final (AC-3 strengthened to lock this in; ADR amendment if changed).

## Stage 2 — critic reports

### Coverage critic (verdict: COVERAGE-HARDEN)

Mutation analysis vs. draft TDD plan:

| # | Wrong implementation | Caught by draft? | Severity |
|---|---|---|---|
| 1 | Silently overwrite on duplicate registration | Yes — `test_duplicate_ecosystem_rejected_at_registration_time` | — |
| 2 | Raise on duplicate at *dispatch* time, not registration time | Yes — the `with pytest.raises(...)` wraps the `@reg.register(...)` call, so a dispatch-time raise would let the second `@reg.register(...)` succeed and fail the `pytest.raises` block | — |
| 3 | `register` returns `None` (decorator strips the function) | **No** — no `is fn` identity assertion in the draft | **harden → AC-10** |
| 4 | `dispatch` calls `fn(manifests, ctx)` (swapped positional args) | **No** — the draft's stub ignores both args; `isinstance(g, DiGraph)` doesn't observe what was passed | **harden → AC-11** |
| 5 | `dispatch` wraps/copies the strategy's graph (e.g., `nx.DiGraph(g)`) | **No** — `isinstance` check doesn't observe identity | **harden → AC-4 + AC-11 identity assertion** |
| 6 | Duplicate-error message uses bare `__qualname__`, drops `module.` | **No** — original test only checked `pytest.raises(DepGraphRegistryError)` with no message inspection | **harden → AC-2** (mirror S1-02 hardening #4) |
| 7 | `registered_ecosystems()` returns an ordered list instead of frozenset | **No** — no test invoked the method | **harden → AC-12** |
| 8 | `has_strategy(BUN)` raises (instead of returning False) on unregistered Literal | Partial — draft's `test_has_strategy_query_does_not_raise` tested PNPM/NPM only; other Literal members untested | **harden → AC-5 totality clause** |
| 9 | Unknown-ecosystem error `args[0]` does NOT include the ecosystem repr | Partial — draft only checked `"no_strategy_for_ecosystem" in args[0]` (substring) | **harden → AC-4 exact-prefix + AC-9 startswith** |
| 10 | `register_dep_graph_strategy` creates a fresh registry per call (vs. targeting default singleton) | Partial — draft's singleton test was structurally fragile (used a non-Literal string) | **harden → singleton test rewrite** |
| 11 | `DepGraphRegistryError` is defined inside `registry.py` (not in `errors.py`) | **No** — no test inspected `errors.__all__` or class location | **harden → AC-13** |
| 12 | `DepGraphProbeOutput` is not frozen / accepts extra fields | **No** — model existed but only as an import; no test exercised `frozen` or `extra="forbid"` | **harden → AC-1 + dedicated test** |

### Test-quality critic (verdict: TEST-QUALITY-HARDEN)

- **`hasattr(PackageManager, "PNPM")` defensive ternary** is dead code (`hasattr` is always False for a `Literal` type alias). Tests appear to use the typed identifier but actually use bare strings on every invocation. **Removed**; replaced with `cast(PackageManager, "pnpm")` and an `ALL_PACKAGE_MANAGERS` tuple.
- **`test_register_and_dispatch_pnpm_strategy`** asserted `isinstance(g, networkx.DiGraph)` and a single edge presence — both can be satisfied by a `dispatch` impl that constructs a new graph and copies the edges over. Rewritten to assert `out is graph_returned_by_strategy` (identity).
- **No test for argument-passing contract** — added `test_dispatch_passes_ctx_and_manifests_positionally` with sentinel objects and `is`-identity assertions on both.
- **No test for decorator return-identity** — added `test_decorator_returns_function_unchanged` (`reg.register(eco)(fn) is fn`).
- **No test for `registered_ecosystems()`** — added with empty/single/multi-member coverage and a non-mutation check.
- **`test_duplicate_ecosystem_rejected_at_registration_time`** asserted only `DepGraphRegistryError` was raised; did not pin message format. Strengthened to require both module.qualname strings to appear in `args[0]` (mirror S1-02 #4 hardening).
- **Singleton test** used a non-Literal string (`"__test_singleton_eco__"` with `# type: ignore`). Rewritten to use `BUN` with pre/post-condition assertions on the singleton's emptiness.
- **No tests for `DepGraphProbeOutput`'s frozen / extra="forbid" discipline** — added `test_dep_graph_probe_output_shape`.
- **No tests for `__all__` exactness** — added `test_public_surface_is_exact`.
- **No tests for `DepGraphRegistryError` location in `errors.__all__`** — added `test_dep_graph_registry_error_is_a_marker_in_errors_module`.

No property-based test added: the registry's semantics are exhaustively expressible over the 5-element `PackageManager` Literal — a single Hypothesis strategy over `sampled_from(ALL_PACKAGE_MANAGERS)` would be slower than the explicit member enumeration in `test_has_strategy_is_total_over_package_manager_literal`. (See `references/techniques.md §"Property-based testing"`: "when the input domain is small and enumerable, prefer explicit enumeration.")

### Consistency critic (verdict: CONSISTENCY-CLEAN with one harden)

- ✓ **02-ADR-0007** ("No plugin loader in Phase 2"): story aligns; AC-6 enforces structurally.
- ✓ **02-ADR-0006 §Decisions noted (registry symmetry)**: shape matches S1-02 + Phase 0.
- ✓ **Production ADR-0033 §3** (typed identifiers): `dict[PackageManager, …]` carries the contract.
- ✓ **S1-05's `PackageManager` re-export** at `codegenie.types.identifiers`: story imports from there, not directly from `node_build_system`.
- ✓ **CLAUDE.md §"Extension by addition"**: the registry IS the extension mechanism.
- **HARDEN — arch wording ambiguity**: `phase-arch-design.md §"Component design" #11` says `@register_dep_graph_strategy(ecosystem=PackageManager.PNPM)` (Enum-style syntax) and "Phase 1 ADR-0013 `PackageManager` enum" — but the actual code is `Literal[...]`, not an Enum. This is not a contradiction (the arch uses "enum" colloquially for a discriminated-string sum), but the draft tests were misled into a defensive `hasattr` ternary. Story Notes now explicitly call out the Literal-not-Enum reality and the correct test idiom (`cast(...)`).
- ✓ **`Manifest` shape**: source scan against `src/codegenie/` confirms no `Manifest` / `NodeManifest` Pydantic model exists. `Mapping[str, Any]` is final. AC-3 strengthened to pin this; future change is ADR-amendment-gated.

### Design-patterns critic (verdict: DESIGN-CLEAN with deferred-kernel-extract note)

- **Plugin / strategy fit** ✓ — the decorator-registry IS the right shape; mirrors S1-02 + Phase 0.
- **Open/Closed at the file boundary** ✓ — adding a new ecosystem is a new file under `plugins/*/` with `@register_dep_graph_strategy(...)`. Zero edits to `depgraph/registry.py` or `DepGraphProbe`.
- **Dependency direction (DIP)** ✓ — `depgraph/registry.py` depends on `ProbeContext` (Phase 0 contract) and `PackageManager` (Phase 1 contract); no Phase 3 dependencies. `DepGraphProbe` (S4-05) will depend on `depgraph/`, never the reverse.
- **Hexagonal / pure-impure split** — N/A here; the registry is a pure data structure. Side effects live in the strategies themselves (Phase 3).
- **Primitive obsession** ✓ — `PackageManager` carries the contract; `dict[PackageManager, …]` typing is correct under `--strict`.
- **Make illegal states unrepresentable** ✓ — `DepGraphProbeOutput` is frozen + extra=forbid + typed confidence Literal; the typed slice shape is locked.
- **Composition over inheritance** ✓ — no inheritance; flat `DepGraphRegistry` class.
- **Strict typing** ✓ — story prescribes `mypy --strict`; no `Any` in public signatures except inside the `Mapping[str, Any]` strategy parameter (acceptable until Phase 1 ships a typed `Manifest`).
- **Small modules with deep interfaces (Ousterhout)** ✓ — single class, five methods, rich public surface.
- **Rule-of-three kernel-extract** — **REACHED** but **deferred** (see Notes for the implementer for full reasoning). The three registries diverge on dispatch shape (`for_task` filter + LRU / `dispatch_all` total / single `dispatch` + `has_strategy`); the shared 15–25 LOC × 3 is below the cost-of-introducing-a-generic threshold mid-phase. Rule 2 + Rule 3 + S1-02 precedent (which also deferred). Recorded as a future-cleanup opportunity; not mandated.
- **YAGNI guard** ✓ — story does NOT pre-extract a generic kernel, does NOT introduce a `Protocol` where `Callable` suffices, does NOT mandate a `DepGraphSliceModel` Pydantic wrapper around the `DiGraph`.

## Stage 3 — researcher

**Skipped.** No `NEEDS RESEARCH` findings. All hardening was answerable from:

- The arch design + 02-ADR-0006 + 02-ADR-0007 + production ADR-0033.
- The S1-02 validation report (sibling-precedent for the same registry shape).
- Direct source scan against `src/codegenie/` (confirmed `PackageManager` is `Literal`, confirmed no `Manifest` Pydantic model, confirmed `errors.py`'s `__all__` discipline).

## Stage 4 — synthesizer / edits applied

### Edits to the story file

| # | Section | Edit |
|---|---|---|
| 1 | Header | Added `(HARDENED by phase-story-validator 2026-05-15)` to Status |
| 2 | After header | Added a `## Validation notes (2026-05-15, phase-story-validator)` block with the 8-point hardening summary |
| 3 | AC-1 | Added "Public surface symmetry" clause requiring exact `__all__` set equality |
| 4 | AC-2 | Strengthened to require "both registration sites named as dotted `module.qualname` strings in `args[0]`" + "at decoration time" precision |
| 5 | AC-3 | Locked `Mapping[str, Any]` as **final** (verified by source scan); changed "adapt at impl time" to "ADR amendment if changed" |
| 6 | AC-4 | Pinned identity return + exact prefix `no_strategy_for_ecosystem: ` + `repr(ecosystem)` |
| 7 | AC-5 | Added totality clause over `PackageManager` Literal members |
| 8 | AC-6 | Pinned scan to `rglob("*.py")` recursive; explicit skip = "`depgraph/registry.py`" |
| 9 | AC-7 | Tightened to "no `class PackageManager` AND no top-level `PackageManager = ...` reassignment" |
| 10 | AC-8 | Added identity-equal-to-closure assertion + explicit five-member Literal enumeration |
| 11 | AC-9 | Pinned `startswith("no_strategy_for_ecosystem: ")` (exact-prefix per AC-4) |
| 12 | **NEW AC-10** | Decorator return-identity (`reg.register(eco)(fn) is fn`) |
| 13 | **NEW AC-11** | Strategy invocation contract (sentinel args, identity-equal received, no copy) |
| 14 | **NEW AC-12** | `registered_ecosystems()` contract (return type, empty-registry, non-mutating) |
| 15 | **NEW AC-13** | `DepGraphRegistryError` in `errors.__all__` + marker shape |
| 16 | AC-14 (was AC-10) | Renumbered; content unchanged |
| 17 | AC-15 (was AC-11) | Renumbered; content unchanged |
| 18 | AC-16 (was AC-12) | Renumbered; scoped `mypy --strict` to the touched directories |
| 19 | TDD plan | Rewrote test file: removed `hasattr` ternary; added 6 new tests; strengthened 4 existing tests |
| 20 | Implementation outline | Added §1 fields-per-AC-1 pointer; §2 added `_origins` rationale + `unregister_for_tests`; §3 added explicit `__all__` declaration; §4 added "extend `__all__`" requirement |
| 21 | Green / registry.py | Added inline comments for AC-10 / AC-11 / AC-4 identity contracts; added docstring on `unregister_for_tests` |
| 22 | Files to touch | Strengthened `errors.py` row to "AND extend `__all__`" |
| 23 | Notes for the implementer | Replaced Enum-bullet with `Literal`-truth bullet + `cast` test idiom; added Manifest-source-scan note; added rule-of-three deferral with full reasoning; tightened dispatch-contract note ("identity, not equality") |

### Before/after spot-checks

**Before — AC-2:**
> `@register_dep_graph_strategy(ecosystem: PackageManager)` is a decorator-factory; registers the function in `default_dep_graph_registry`; duplicate-ecosystem registration raises `DepGraphRegistryError` at import time.

**After — AC-2:**
> `@register_dep_graph_strategy(ecosystem: PackageManager)` is a decorator-factory; registers the function in `default_dep_graph_registry`; duplicate-ecosystem registration raises `DepGraphRegistryError` at decoration time (i.e., module import) with **both registration sites named as dotted `module.qualname` strings in `args[0]`** (mirror S1-02 hardening; an operator grepping a multi-file plugin tree can locate both registrations from the message alone).

**Before — TDD plan, dispatch test:**
```python
g = reg.dispatch(PackageManager.PNPM if hasattr(...) else "pnpm", _make_ctx(tmp_path), [])
assert isinstance(g, networkx.DiGraph)
```

**After — TDD plan, dispatch test:**
```python
PNPM = cast(PackageManager, "pnpm")
# ...
graph_returned_by_strategy = networkx.DiGraph()
@reg.register(PNPM)
def build_pnpm(ctx, manifests): return graph_returned_by_strategy
out = reg.dispatch(PNPM, ctx, [])
assert out is graph_returned_by_strategy   # identity — wrap/copy mutation would fail
```

## Verdict

**HARDENED.** Story is ready for `phase-story-executor`. The 16-AC contract is mutation-resistant; the executor's Validator pass can binary-pass/fail each AC against runtime evidence.

## Audit trail

- Validation invocation: scheduled task `story-validation-corrector` (2026-05-15)
- Story commits prior to validation: at HEAD (no prior `_validation/S1-10-*.md` report)
- Files modified by this validation:
  - `docs/phases/02-context-gather-layers-b-g/stories/S1-10-depgraph-strategy-registry.md` (in-place hardening)
  - `docs/phases/02-context-gather-layers-b-g/stories/_validation/S1-10-depgraph-strategy-registry.md` (this report — new file)
