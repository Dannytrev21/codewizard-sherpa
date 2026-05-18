# ADR-0003: Plugin resolution algorithm + universal `(*,*,*)` fallback as a registered plugin

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** plugin-architecture · resolution · hitl · sum-type · open-closed
**Related:** [0002](0002-plugin-registry-kernel-instance-with-default-singleton.md), [0010](0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md), [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md)

## Context

Production ADR-0031 (§"No-match fallback") commits to a universal `(*, *, *)` plugin that handles every "no concrete plugin matches" case via HITL escalation — "no specific plugin matches is never a silent failure." Phase 3 must implement that contract: a concrete `PluginRegistry.resolve(scope) -> PluginResolution` algorithm with deterministic specificity ordering, an `extends`-chain walk for inheritance, and a fallback semantics that **never silently substitutes** a concrete plugin (Goal G7 in `phase-arch-design.md`).

The three lens designs converged on the directory name `plugins/universal--*--*/` (final-design §Synthesis ledger; AGREE edge) but disagreed on (1) how resolution treats the "no match" case and (2) what type the resolver returns. Best-practices proposed `PluginScope.task_class: Literal["*"]` collapsed into `str` at runtime — the critic correctly attacked it as a type smell (`critique.md §Best-practices design — concrete problems`). The architecture spec resolves resolution into a tagged-union return: `PluginResolution = ConcreteResolution | UniversalFallbackResolution`, **with no third "no match" branch** — the universal fallback IS the no-match variant.

## Options considered

- **Option A — Resolver returns `Plugin | None`; orchestrator's outer code checks `None` and dispatches to a hardcoded `_handle_no_match` function.** **Pattern:** Tag-and-dispatch without sum type, plus a hidden no-match branch the kernel knows about. Violates Open/Closed at the kernel level.
- **Option B — Universal fallback is a special case in `resolve()`, returned as a plain `Plugin` indistinguishable from a concrete plugin.** **Pattern:** Stringly-typed enforcement — caller has no static signal that the fallback fired. HITL handoff vs. concrete-applied paths look identical at the type level.
- **Option C — `PluginResolution` is a tagged union (`ConcreteResolution | UniversalFallbackResolution`); the universal plugin is a normal registered plugin (`plugins/universal--*--*/`), but the resolver narrows to the `UniversalFallbackResolution` variant when the head is the universal one.** Resolution order is `(specificity desc, precedence desc, name asc)`; `extends` chain walked with cycle check (max depth 4); composed TCCM merged left-to-right (later wins per ADR-0031). **Pattern:** Tagged union + Registry — the kernel has no `if plugin.is_fallback:` branch; specificity sort puts the universal fallback last by construction; the discriminator lives in the return type.

## Decision

Adopt **Option C.** `PluginRegistry.resolve(scope)` returns a Pydantic `PluginResolution = ConcreteResolution | UniversalFallbackResolution` discriminated on `kind`. Resolution algorithm:

1. Filter registered plugins by `scope.matches(...)`.
2. Sort by `(specificity desc, precedence desc, name asc)` — deterministic on ties.
3. If the head plugin's id is `universal--*--*`, return `UniversalFallbackResolution(reason=NoConcreteMatch, candidates_considered=[...])`.
4. Else walk `extends_chain` (cycle-checked, max depth 4), compose `TCCM` and `adapters` left-to-right, return `ConcreteResolution(plugin, extends_chain, composed_tccm, composed_adapters)`.

The universal fallback is a normal registered plugin under `plugins/universal--*--*/`; its subgraph emits `RequiresHumanReview`, writes sanitized markdown to `.codegenie/handoff/<workflow_id>.md`, and exits 7. The fallback is loaded by the same machinery as every other plugin (no special path).

## Tradeoffs

| Gain | Cost |
|---|---|
| The "no match" path is a typed return variant, not an exception or a `None` check — `match` + `assert_never` enforces exhaustive handling at every dispatch site | Two ways to lose: forget to register the universal plugin (`PluginRegistryCorrupted` event at startup) vs. forget to handle the fallback variant in dispatch (mypy catches it) |
| Universal fallback discovered by the same `plugins/*/plugin.yaml` walk as every other plugin — zero special-casing in the loader (ADR-0031's "loaded by the same mechanism") | The directory name `universal--*--*/` involves shell-globbing-unfriendly characters; ops must quote paths in scripts |
| Specificity ordering is data-driven (`scope.specificity() = count of Concrete dims`); precedence ties broken explicitly by manifest field; name ties broken alphabetically — fully deterministic | Adding a fourth scope dimension later (e.g., runtime target) would change `specificity()` semantics across every existing plugin |
| `extends`-chain walk with cycle check (max depth 4) means inheritance composes safely; `composed_tccm` is built by left-to-right merge with later-wins-on-collision per ADR-0031 | Cycle detection adds startup cost; depth-4 cap is empirical (no production plugin chain expected to exceed it) |
| `UniversalFallbackResolution.candidates_considered` carries debug info — operator can see which concrete plugins were filtered out and why | Audit log volume grows with plugin count; sanitization must scrub repo-specific paths from the candidate list |

## Pattern fit

Implements **Tagged union / sum type for state** (toolkit §Structural / typing patterns) — `PluginResolution` distinguishes ConcreteResolution from UniversalFallbackResolution at the type level, eliminating the "did the fallback fire?" boolean smell. Implements **Open/Closed Principle** (toolkit §Composition / coupling patterns) — adding new plugin types or new fallback reasons is additive; the kernel's `resolve()` has no `match plugin.id:` block that grows. The universal fallback being a registered plugin (not a hardcoded code path) is the textbook ADR-0031 promise: "the fallback plugin is itself added by addition."

## Consequences

- `src/codegenie/plugins/resolver.py` ships the algorithm; `src/codegenie/plugins/scope.py` ships `PluginScope.matches` and `specificity()`.
- `tests/unit/plugins/test_resolver.py` covers: exact match > wildcard; precedence ties; `extends` chain walk; no concrete match → `UniversalFallbackResolution`; cycle detection raises `PluginExtendsCycle(chain)`.
- Property test: `Resolver.resolve` invariant — returns `ConcreteResolution` whose `plugin.scope.matches(...)` is True, OR returns `UniversalFallbackResolution` (never raises, never returns `None`).
- Loader startup check: `default_registry.get(PluginId("universal--*--*"))` must succeed; missing → `PluginRegistryCorrupted` spanning event + hard exit.
- Universal fallback subgraph writes sanitized handoff: NFKC normalize + ANSI escape + bidi + zero-width strip (security lens contribution, retained per `phase-arch-design.md §Agentic best practices`).
- Phase 5 inherits this resolution shape — no edits.
- New invariant: any change to specificity/precedence/name ordering requires an ADR amendment (it's a global determinism property).

## Reversibility

**Medium.** The discriminated-union return is easy to relax to `Plugin | None` (mechanical), but every consumer site would need to re-introduce a `None` check, and the `humans always merge` invariant (production ADR-0009) would lose its static guarantee. The chosen shape is hard to make less safe; that's intentional. Switching the resolution algorithm itself (e.g., to `precedence first, specificity second`) is also mechanical but would change behavior across every existing plugin — a behavioral break, not a structural one.

## Evidence / sources

- `../phase-arch-design.md §Component design C2 + C3`, §Scenarios B + D, §Edge case E2 + E9 + E10
- `../final-design.md §Synthesis ledger row "Universal fallback directory name"` (convergent across lenses) and §Departures #4
- `../critique.md §Best-practices design — concrete problems` (`Literal["*"]` collapse to `str` at runtime)
- [production ADR-0031 — plugin architecture §No-match fallback](../../../production/adrs/0031-plugin-architecture.md)
- [production ADR-0009 — humans always merge](../../../production/adrs/0009-humans-always-merge.md)
- design-patterns-toolkit.md §Tagged union, §Open/Closed Principle
