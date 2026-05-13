# ADR-0010: Promote Phase 5's `GateRunner._run_one_attempt` to a public `run_one` — the single surgical Phase 5 touch

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** phase5-contract · surgical-change · parity-test
**Related:** [ADR-0003](0003-per-gate-retry-counter-scope.md), [ADR-0004](0004-retry-re-enters-phase4-fallback-tier.md)

## Context

Phase 6 must invoke Phase 5's gate-evaluation logic *one attempt at a time* (the LangGraph cycle unrolls Phase 5's `for attempt in range(1, max_attempts + 1)` loop into a graph cycle of `validate_in_sandbox → record_attempt → route_after_attempt → replan_with_phase4 → apply_recipe → validate_in_sandbox`). Phase 5 ships `GateRunner.run` (the looped version) as its public API. Phase 6 needs a *single-attempt* entry point.

The three lenses handled this dependency differently (`critique.md §best-practices.cross-design.3`, Phase 6 design's Gap 2):

- **Performance** decomposed Phase 5's `GateRunner.run` into 5 nodes (`build_spec → execute_sandbox → collect_signals → evaluate_gate → branch`). Phase 5 does not expose those internal steps; this is a Phase-5 refactor masquerading as a Phase-6 design.
- **Best-practices** assumed Phase 5's `GateRunner` exposes a `.run-one` method without checking whether Phase 5's shipped code actually does.
- **Security** ignored the contract entirely and ran `GateRunner.run` (the looped version) at every node call, which would produce duplicate ledger entries.

The synthesis (`final-design.md §Component 5`) decided: **one and only one Phase-5 source touch — promote the existing private helper to a public name.** The renaming-only change is documented as ADR-P6-001 in the design. This ADR formalizes it.

There is a real risk the helper isn't factored as cleanly as the synthesis assumed (Phase 6 design's Gap 2). The implementer must read `src/codegenie/gates/runner.py` first; if Phase 5 ships a monolithic `run()` with the per-attempt body inline, the promotion becomes a small refactor of `GateRunner.run` to extract `run_one` as a top-level method, plus an update to Phase 5's contract-snapshot tests. Either way, the change is bounded, surgical, and recorded.

## Options considered

- **Phase 6 re-implements Phase 5's per-attempt body inline.** Avoids the Phase-5 touch but introduces a second implementation of the gate logic that can drift from Phase 5's — exactly the drift `critique.md` flagged.
- **Phase 6 calls `GateRunner.run` (the looped version) once per node and relies on `max_attempts=1`.** Phase 5's internal `RetryLedger.record` would still fire from inside the loop, producing duplicate ledger entries that the parity test would catch as drift.
- **Phase 6 promotes `_run_one_attempt` to public `run_one`.** One additive rename in Phase 5's source; Phase 5's `run` is unchanged and still callable; Phase 6 calls `run_one(transition, ctx)` once per node attempt.

## Decision

The implementer of Phase 6 will inspect `src/codegenie/gates/runner.py` and promote the single-attempt entry point to a **public `run_one(transition, ctx) -> GateOutcome` method** on `GateRunner`. The original `GateRunner.run` is unchanged. If Phase 5's existing shape factors the per-attempt body cleanly (a private `_run_one_attempt` or equivalent), the change is renaming-only and Phase 5's contract-snapshot tests need no update. If Phase 5's shape is monolithic, the implementer performs the minimum refactor needed to expose `run_one` as a top-level method on `GateRunner`, updates the Phase 5 contract-snapshot tests in lockstep, and amends this ADR's "Decision" section to describe what shipped. **This is the only Phase 0–5 source touch Phase 6 makes.**

The parity test (`tests/integration/test_retry_semantics_parity.py`) is the canary: it runs the same fixture scenario through Phase 5's sync `GateRunner.run` and through Phase 6's LangGraph cycle and asserts byte-identical `attempts.jsonl`. The day this drifts, one of the two implementations is wrong.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 6 calls a typed, public Phase 5 API — no private-member access, no implementation copy | One Phase-5 source touch in an otherwise additive-only phase; the surgical-changes discipline (CLAUDE.md Rule 3) makes it inspectable but is still a touch |
| Phase 5's `GateRunner.run` continues to work for sync callers (smoke tests, the CLI baseline) — no behavior change for existing consumers | If Phase 5's body is monolithic, the implementer must perform a small refactor under Phase 6's budget; the ADR is amended to record what actually shipped |
| Parity test catches drift between the two implementations on every CI run — single source of truth | The parity test only fires on the curated fixture (`tests/fixtures/golden_attempts/cve_fixture_3retries.jsonl`); a divergence on uncommon paths is not caught until the next exit-criterion test runs |
| The cross-phase contract is small (one method signature) and documented in the contract-snapshot test that Phase 5 already ships | A future Phase 5 refactor that changes `run_one`'s signature is a Phase-5-and-6 change; the ADR must be amended |

## Consequences

- `src/codegenie/graph/nodes/validate_in_sandbox.py` imports `from codegenie.gates.runner import GateRunner` and calls `GateRunner(...).run_one(transition, ctx)`. No private-attribute access; no `_run_one_attempt` reference.
- `src/codegenie/graph/nodes/record_attempt.py` imports Phase 5's `RetryLedger` for the actual chain extension. The `run_one` method returns a `GateOutcome` but does *not* write to the ledger — that's the Phase 6 node's job. The split is what allows the cycle to retry without double-writing.
- A CI lint (`tests/graph/test_runner_run_one_public.py`) asserts `codegenie.gates.runner.GateRunner.run_one` is importable and callable — Build fails if Phase 5 reverts the promotion (closes `final-design.md §Failure modes — "Phase 5 _run_one_attempt not promoted"`).
- Phase 5's `final-design.md §6 GateRunner` should be amended in lockstep to document the public `run_one` method; if the engineer working Phase 6 cannot make that amendment, they flag it as a follow-up.
- Phase 7's distroless loop calls `GateRunner.run_one` the same way for its own gate transitions — the public API is task-class-agnostic.

## Reversibility

**High.** Reverting `run_one` to a private `_run_one_attempt` is a one-rename change; the Phase 6 import breaks loudly. The only durable cost is the Phase 5 contract-snapshot test, which would need a small revert in lockstep. Adding *more* Phase 5 public methods (e.g., for distroless gate signals in Phase 7) is a parallel additive change that doesn't affect this decision.

## Evidence / sources

- [`../final-design.md` §Component 5 "validate_in_sandbox + record_attempt"](../final-design.md)
- [`../final-design.md` §Risk 1](../final-design.md)
- [`../phase-arch-design.md` §Component 5 "Nodes" — `validate_in_sandbox` row](../phase-arch-design.md)
- [`../phase-arch-design.md` §Gap analysis Gap 2](../phase-arch-design.md) — the "is the helper really factored cleanly?" risk
- [`../critique.md` §cross-design — best-practices.cross-design.3](../critique.md)
- Phase 5's `final-design.md §6 GateRunner` — the contract this ADR amends additively
