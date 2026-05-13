# ADR-0002: `VulnLedger` is `frozen=False`, with a runtime `id()`-diff after-node hook

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** state · pydantic · langgraph-idiom
**Related:** [ADR-0001](0001-lazy-singleton-build-vuln-loop-factory.md), [ADR-0005](0005-static-schema-version-literal-pin.md), [production ADR-0002](../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md)

## Context

`VulnLedger` is the single Pydantic-typed state contract every node reads from and writes to (`phase-arch-design.md §Component 1`). It must be JSON-serializable end-to-end (the checkpointer round-trips it) and compatible with LangGraph's `model_copy(update=...)` reducer-merging idiom. The synthesizer faced a hard `frozen` fork (`critique.md §cross-design — frozen`):

- **Security's `frozen=True`** is Pydantic-pure: it makes in-place mutation impossible at the type level. But it requires replacing LangGraph's automatic reducer-merging with a custom `@reducer` dispatcher, because LangGraph constructs new instances via `model_copy(update=...)` and every node would need to manually allocate (`critique.md security.3`). This breaks ADR-0002's "use LangGraph's mature tooling for free."
- **Best-practices' `frozen=False`** keeps LangGraph's idiom but leaves the door open to `state.events.append(...)` — an in-place mutation that bypasses `model_copy` and silently breaks replay determinism. Best-practices proposed an AST lint to catch this, but `critique.md best-practices.4` showed the AST lint is hand-waved: `state.events.append(e)` is `getattr` + method call, not assignment, and requires dataflow analysis to detect.

The exit criterion is that the graph survives mid-run kill with byte-identical replay (`final-design.md §Goal 2`). In-place mutation of a mutable field (a list of `AttemptSummary`, a list of `GraphEvent`) silently violates replay determinism — same input state can produce different output if the previous node accidentally mutated `state.prior_attempts` and the checkpoint serialized the post-mutation snapshot. The fail-mode is silent corruption, not a crash, which is exactly what global rule §12 ("Fail loud") forbids.

## Options considered

- **`frozen=True` + custom `@reducer` dispatcher.** Pydantic enforces immutability at the type level; nodes return `ReducerCall("add_attempt", summary)` and an after-node hook applies the reducer. Maximally safe; fights LangGraph's idiom; ~200 LOC of custom dispatch; `langgraph-cli` cannot introspect a non-standard return type.
- **`frozen=False` + AST lint for in-place mutation.** Idiomatic LangGraph; lint claim is hand-waved (`critique.md best-practices.4`); leaves a gap.
- **`frozen=False` + runtime `id()`-diff after-node hook.** Idiomatic LangGraph; replace the lint with a runtime check that, after every node returns, verifies that the `id()` of every mutable list/dict field is either unchanged (true read) or different (clean `model_copy`); an unchanged `id()` with mutated content raises `LedgerMutatedInPlace` and fails the node loudly.

## Decision

`VulnLedger` is declared with `model_config = ConfigDict(extra="forbid", frozen=False)`. After every node returns, a registered after-node hook (`src/codegenie/graph/hooks.py:make_after_node_hook`) iterates `_MUTABLE_FIELDS = ["prior_attempts", "events"]` and any nested mutable sub-collections; if `id(before_field) == id(after_field)` and `before_field != after_field`, the hook raises `LedgerMutatedInPlace(field=..., node=...)`. Every node module exports its function through an `@audited_node` wrapper that applies the hook.

## Tradeoffs

| Gain | Cost |
|---|---|
| LangGraph's `model_copy(update=...)` reducer-merging works idiomatically — no custom dispatcher, no novel return type | Hook is runtime overhead per node return (negligible in practice, ~µs); not a static guarantee |
| In-place mutation is caught loudly at the moment it happens — the node author sees a stack trace pointing at the offending line | The hook only catches list/dict-level mutation; mutating a *nested* Pydantic model's mutable field is missed unless `_MUTABLE_FIELDS` enumerates the nested path |
| `langgraph-cli`, `to_json()`, and standard LangGraph tooling all work without special-casing | Test authors who write per-node tests must invoke `@audited_node`-wrapped functions (or the raw function plus the hook); the project ships a single test helper to avoid divergence |
| `extra="forbid"` still rejects unknown fields at deserialization — schema drift surfaces loudly | `frozen=False` makes `dataclasses.replace`-style allocation cheaper but the discipline of never assigning to a state field directly relies on convention, not the type system |

## Consequences

- The runtime hook **is** the safety net; deleting `@audited_node` from a node module silently re-opens the mutation gap. A static check (`tests/graph/test_audited_node_decorator_applied.py`) asserts every `graph/nodes/*.py` exports an `@audited_node`-wrapped function.
- `_MUTABLE_FIELDS` is a small enumeration in `hooks.py`; adding a new mutable field to `VulnLedger` requires editing both `state.py` and `hooks.py`. This coupling is intentional — adding a mutable field is a load-bearing change and should be visible in PR review.
- The unit test `test_state.py::test_in_place_mutation_raises` is the canary for the hook itself.
- Phase 7's `DistrolessLedger` (ADR-0022 — three-strikes) inherits this convention; the abstraction question is deferred until strike three.
- A future move to `frozen=True` is feasible if LangGraph ever exposes a clean reducer-call return type, but it would require touching every node body. The hook is the durable substitute.

## Reversibility

**Medium.** Going from `frozen=False` + hook to `frozen=True` + custom dispatcher requires rewriting every node body to return a reducer call instead of a state instance, plus replacing LangGraph's standard merge with the dispatcher. That's ~10 nodes plus ~50 test files — a multi-day change but mechanically tractable. Going the other direction (looser discipline, no hook) is trivial but unsafe and was the synthesis's explicit rejection.

## Evidence / sources

- [`../final-design.md` §Component 1 "VulnLedger"](../final-design.md)
- [`../final-design.md` §Synthesis ledger row 1 "frozen on state ledger"](../final-design.md)
- [`../phase-arch-design.md` §Component 7 "Runtime after-node id()-diff hook"](../phase-arch-design.md)
- [`../critique.md` §security.3 + §best-practices.4](../critique.md) — the `@reducer` and AST-lint critiques that forced the synthesis
- [Production ADR-0002](../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md) — "use LangGraph's mature tooling for free"
- CLAUDE.md global rule §12 — "Fail loud" justifies the runtime hook over a hand-waved lint
