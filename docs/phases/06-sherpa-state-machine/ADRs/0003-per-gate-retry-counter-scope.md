# ADR-0003: `retry_count` is scoped per gate transition, with same-signature flake short-circuit

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** retry · semantics · phase5-parity
**Related:** [ADR-0004](0004-retry-re-enters-phase4-fallback-tier.md), [ADR-0013](0013-same-signature-flake-detection-in-route-after-attempt.md), [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md)

## Context

`final-design.md §Synthesis ledger row 2` and `critique.md §cross-design` flagged the retry-counter-scope conflict as the single most load-bearing disagreement in Phase 6. The three lenses landed in three different places:

- **Performance:** `retry_count` per-gate, reset on engine switch.
- **Security:** `len(attempts) >= 3` per workflow, with same-signature flake detection.
- **Best-practices:** `retry_count` **monotonic per workflow lifetime**, reset only on HITL "continue."

Best-practices' interpretation **silently breaks** [ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md), whose title is *"Three-retry default per gate transition."* Under best-practices' shape, a recipe-fail + RAG-fail + LLM-fail run escalates after 3 total attempts across engines — not after 3 attempts at the same gate. Worse, the Phase 5 parity test (`tests/integration/test_retry_semantics_parity.py`) **cannot pass byte-for-byte**, because Phase 5's `GateRunner.run` uses `for attempt in range(1, max_attempts + 1)` *per gate* and produces a 5-entry `attempts.jsonl` for that scenario; best-practices' graph would produce a 3-entry ledger and escalate.

Global rule §7 forbids averaging conflicting patterns; the synthesizer must pick the per-gate interpretation and reject best-practices' per-workflow shape, which it did (`final-design.md §Conflict-resolution row 2`).

## Options considered

- **Per-workflow lifetime counter (best-practices' pick).** `retry_count` monotonically increases across every failure regardless of which gate transition it was at. Reset only on HITL "continue." Cheap to compute; breaks ADR-0014; breaks Phase 5 parity.
- **Per-gate counter, no flake detection (performance's literal pick).** Reset on `current_gate_id` change. Honors ADR-0014; doesn't catch the case where a deterministic failure (`same_signature(prior_attempts[-1], prior_attempts[-2])`) burns the retry budget on a flake-shaped non-flake.
- **Per-gate counter + same-signature flake detection (security's idea, ported).** Reset on `current_gate_id` change; if the last two attempts have the same failing signals + same `prior_failure_summary`, route directly to `non_retryable` and don't burn another retry.

## Decision

`VulnLedger.retry_count` is **scoped per gate transition.** `record_attempt` resets `retry_count = 0` whenever `current_gate_id` changes; otherwise it increments. `await_human` resets `retry_count = 0` when `HumanDecision.action == "continue"`. `route_after_attempt` additionally returns `"non_retryable"` when `len(prior_attempts) >= 2 and same_signature(prior_attempts[-1], prior_attempts[-2])`, where `same_signature` compares `sorted(failing_signals)` and `prior_failure_summary` (`phase-arch-design.md §Component 4`).

## Tradeoffs

| Gain | Cost |
|---|---|
| Honors [ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md) literally — "three retries per gate transition" | Reset-on-gate-change adds a small piece of state-coupling between `record_attempt` and `current_gate_id` that future authors must preserve |
| Phase 5 sync `for`-loop ledger and Phase 6 LangGraph cycle produce byte-identical `attempts.jsonl` (G4 parity test passes) | Same-signature flake detection adds one branch to `route_after_attempt` — the unit test must enumerate it |
| Flake detection prevents burning the retry budget on a deterministic recurring failure — operator sees HITL faster | If the test signals are noisy (timestamps, run IDs, transient stderr), false-positive same-signature matches escalate prematurely — Phase 5's `AttemptSummary.failing_signals` field design must hold |
| HITL "continue" semantics are explicit: the human's approval grants a fresh retry budget — matches operator intuition | `HumanDecision.action="continue"` after a same-signature flake routes to `non_retryable` again (see Phase 6 design Gap 4); the doc must say so |

## Consequences

- The parity test `tests/integration/test_retry_semantics_parity.py` is the **canonical canary** for this decision; the day it drifts, one of the two implementations is wrong.
- `route_after_attempt` is the single predicate that reads this state — keeping the retry policy in one function instead of scattered across nodes. The function is exhaustively unit-tested over the cartesian of `(passed, retryable, retry_count, same_signature)`.
- Phase 7's `DistrolessLedger` inherits the per-gate counter shape — its gates are different but the scoping rule is the same. Adding a new task class in Phase 7 does not require re-deriving retry semantics.
- The `max_attempts` field on `VulnLedger` is **frozen at graph-build time** (see Phase 6's design tradeoff on `--max-attempts-override` mid-run): an operator running `codegenie loop resume` cannot raise the cap. Phase 5's `--max-attempts-override` flag binds at graph-build, not mid-resume. Risk #4 records this scope cut.
- A future ADR amendment (the design notes ADR-P6-008) may reconcile the literal roadmap wording "twice in a row" with the production default `max_attempts=3`; until then the exit-criterion test parametrizes `max_attempts=2` (`phase-arch-design.md §Two-consecutive vs three-strikes`).

## Reversibility

**Low.** Going back to a per-workflow counter would silently break Phase 5 parity, ADR-0014, and the exit-criterion semantics; the parity test is byte-identical, so reversion is detected immediately but the downstream cleanup is broad. Reversing the same-signature short-circuit alone is cheap (a one-line predicate change) and would only affect the flake-detection edge case.

## Evidence / sources

- [`../final-design.md` §Synthesis ledger row 2 "Retry-counter scope"](../final-design.md)
- [`../final-design.md` §Component 4 "@pure_edge — route_after_attempt"](../final-design.md)
- [`../phase-arch-design.md` §Component 4 "@pure_edge predicates"](../phase-arch-design.md)
- [`../critique.md` §best-practices.1](../critique.md) — the per-workflow vs per-gate conflict that forced the decision
- [Production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md) — title is per-gate; this ADR honors it
