# ADR-0006: Protocol for duck-typed contracts; ABC for inherited default behavior

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** convention · python · contracts
**Related:** [ADR-0001](0001-two-chokepoint-sandbox-seam.md), [ADR-0003](0003-trustscorer-extension-via-signal-kind-registry.md)

## Context

Phase 5 introduces two new shared-shape abstractions in the same PR: `SandboxClient` (declared as `typing.Protocol`) and `Gate` (declared as `abc.ABC`). The critic flagged this as convention drift — two idioms for "shared interface" in one phase, with no rule explaining the choice. Phase 1's `Probe` ABC, Phase 2's `Transform` ABC, and Phase 3's `RecipeEngine` ABC set one precedent; the new Protocol breaks it. Without an explicit rule, Phase 7+ will guess. See [final-design.md §Synthesis ledger — Convention drift](../final-design.md#synthesis-ledger) and [phase-arch-design.md §Logical view](../phase-arch-design.md#logical-view--what-are-the-components-and-how-are-they-related).

## Options considered

- **Everything is an ABC** — One rule, easy to teach. Forces backends to inherit from a base class even when no shared behavior exists. Slightly heavier; mocking is more ceremony.
- **Everything is a Protocol** — Pure structural typing. Backends are plain classes; mocks are trivial. But contracts with shared default behavior (retry policy, gate id, required-signals tuple) lose the inheritance affordance and re-implement defaults per subclass.
- **Rule by purpose** — Protocol when the contract is purely structural (the type system asks "does this object have these methods?"); ABC when subclasses share non-trivial default behavior the contract author wants to provide once.

## Decision

Adopt the purpose-based rule. `SandboxClient` is a `runtime_checkable` Protocol — backends share no default behavior, only a shape (`execute`, `health`). `Gate` is an ABC — subclasses share `gate_id`, `required_signals`, and `retry_policy` defaults and inherit a shared evaluate-time scaffold. The rule is documented in `docs/conventions.md` (added in this phase).

## Tradeoffs

| Gain | Cost |
|---|---|
| Mocking `SandboxClient` for unit tests is one anonymous class with two methods — no inheritance ceremony | Two idioms in the codebase; readers must check which one applies before adding a subclass |
| `Gate` subclasses do not re-implement `gate_id`/`required_signals` boilerplate; ABC carries it | The rule is judgment-based (when does "shared default behavior" warrant ABC?) — borderline cases need ADR amendments |
| Phase 7 distroless follows the same rule when adding new backends (`@register_sandbox_backend`) and new gates | A contributor who guesses wrong forces a refactor on review |
| Documentation cost is one section in `docs/conventions.md` | The rule is enforced socially, not by lint/CI — no automated check |

## Consequences

- `src/codegenie/sandbox/contract.py` declares `SandboxClient` as `@runtime_checkable Protocol`; `src/codegenie/gates/contract.py` declares `Gate` as `ABC`.
- `docs/conventions.md` (new file in this phase) carries the rule and the two examples.
- Future ADRs may add cases (e.g., signal collectors are plain functions, not classes — covered by Phase 1's `@register_probe` precedent).
- New invariant: any cross-component Phase 5+ contract chooses Protocol or ABC by this rule; deviations require an ADR amendment.
- The `auto_detect() -> SandboxClient` factory returns whichever concrete backend satisfies the Protocol — `isinstance(b, SandboxClient)` is the structural check.

## Reversibility

**High.** The rule is documentary; it does not constrain runtime behavior. Reversing means either (a) migrating `SandboxClient` to ABC (small subclass edit on each backend), or (b) migrating `Gate` to Protocol (drop the ABC defaults). Either move is mechanical and confined to ~10 files.

## Evidence / sources

- [final-design.md §Synthesis ledger — Convention drift](../final-design.md#synthesis-ledger)
- [final-design.md §New ADRs implied — ADR-P5-006](../final-design.md#new-adrs-implied-by-this-design)
- [phase-arch-design.md §Logical view](../phase-arch-design.md#logical-view--what-are-the-components-and-how-are-they-related)
- [phase-arch-design.md §Component design — central abstractions vs scaffolding](../phase-arch-design.md#component-design)
- [critique.md best-practices §2](../critique.md)
