# ADR-0014: Three-retry default per gate transition

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** policy · escalation
**Related:** ADR-0008, ADR-0009

## Context

When a Trust-Aware gate fails (sandbox build broke, tests failed, SAST found a new issue), the worker subgraph can either give up or retry. Retrying is sometimes successful — the LLM, given the error log as additional state, often produces a better next attempt. But unlimited retries are catastrophic: they burn tokens, mask deeper issues, and create false confidence when the system "eventually got there" after 50 attempts.

The retry cap is a load-bearing knob. Too low and the system gives up on solvable problems. Too high and the system masks real bugs and pays unbounded LLM cost.

## Options considered

- **No retries — fail fast.** Any gate failure immediately escalates to human. Conservative; underutilizes the LLM's ability to learn from sandbox feedback.
- **N=3 retries.** After 3 failed attempts, `interrupt()` and escalate.
- **N=5 retries.** More chances, more cost.
- **N=10+ retries.** Most chances, highest cost, highest risk of "agent eventually stumbled into something that passes the gate but is semantically wrong."
- **Dynamic retry policy** — adjust per task class, per error type, per historical success rate.

## Decision

**Default per-node retry cap is 3.** On the 3rd consecutive gate failure at the same node, the worker subgraph halts gracefully:

1. Failure is logged to the knowledge graph as a "negative example" — future plans can avoid the same path.
2. The Supervisor is notified; sibling workers continue unaffected.
3. The worker invokes LangGraph's `interrupt()` to checkpoint state and escalate to a human reviewer.

The retry cap is configurable per subgraph and per node — defaults to 3 but can be tuned per ADR amendment as evidence accumulates.

## Tradeoffs

| Gain | Cost |
|---|---|
| LLM gets 2 chances to learn from sandbox error logs — captures the common "minor fix" case | Some genuinely solvable problems escalate to human after 3 tries when 4 would have worked |
| Cost ceiling per node is bounded — worst case 3× LLM spend at that node | Aggressive cap may mask emerging capability — as models improve, 3 may be too low |
| Failed paths produce knowledge-graph entries that prevent repeat failures across the portfolio | Negative-example logging adds storage and write throughput requirements |
| Escalation is loud — humans see a clear "stuck after 3" signal rather than silent retry spirals | False positives where the system gives up on solvable problems consume reviewer attention |

## Consequences

- The retry counter is part of the Pydantic state ledger; LangGraph's conditional edges read it to decide route-back vs. escalate.
- Error logs from each failed attempt are concatenated into state — the agent sees "you tried X (failed because Y), then Z (failed because W)" as context for the third attempt.
- Workers that exhaust retries do not crash the Supervisor or sibling workers (Temporal's failure isolation).
- The "3" can be revisited in an ADR amendment once production data exists; default until then is conservative.
- Per-task-class tuning is allowed but the default applies unless explicitly overridden.

## Reversibility

**Low cost.** The retry cap is a configuration value, not a structural choice. Bumping to 5 or down to 2 is one ADR amendment plus a config change.

## Evidence / sources

- `../design.md §4.1` (Layer 3 — retry-back-with-context behavior)
- `../design.md §4.5` Scenario A — vulnerability scenario explicitly references "After 3 failed attempts"
- `../design.md §5` (Retry limits subsection)
- `../design.md §8.9` (Trust-Aware gate decision flow — explicit `Retry count < 3?` branch)
- Konveyor Kai's retry-and-adjust pattern (`../../auto-agent-design.md §2.1`)
