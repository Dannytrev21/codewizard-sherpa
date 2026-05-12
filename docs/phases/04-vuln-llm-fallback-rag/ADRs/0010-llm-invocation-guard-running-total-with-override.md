# ADR-0010: `LlmInvocationGuard` with per-invocation + per-workflow running-total ceiling and explicit `--allow-cost-overrun` override

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** cost-cap · budget-enforcer · phase-13-handoff · synthesizer-departure
**Related:** [production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md), [production ADR-0025](../../../production/adrs/0025-per-workflow-cost-cap.md), [production ADR-0027](../../../production/adrs/0027-cost-attribution-model.md)

## Context

Phase 4 is the first phase that spends money. The cost-cap primitive's shape determines how Phase 13's Budget Enforcer middleware composes. The three lens designs picked three incompatible primitives:

- Performance: per-call cap (`--max-llm-cost-usd=0.50`) with token-prediction enforcement; budgeted retries.
- Security: hard per-workflow token cap + egress byte cap in the proxy; no override (operationally painful).
- Best-practices: per-invocation $5.00 hard wall, no running-total interface.

The critic (`critique.md §best-practices hidden assumption #3`) attacked best-practices' missing running-total interface as the integration shape Phase 13 will need. The synthesizer ships *both* layers in one Guard API: per-invocation ceiling + per-workflow running-total kwarg, so Phase 13's middleware is a swap, not a rewrite. The `--allow-cost-overrun=<usd>` override flag emits a loud audit event so blanket-use is policed via dashboard alerts.

## Options considered

- **Per-invocation only.** Best-practices position. Simple. No running-total hook means Phase 13's Budget Enforcer either rewrites the guard or wraps it; either way Phase 4's API is the wrong shape.
- **Per-workflow only.** Performance position. Misses the per-call disaster-prevention case (a single Anthropic prompt that estimates at $50 should refuse pre-call, not after the workflow ledger ticks past $50).
- **Per-workflow with no override.** Security position. Honest about wanting to cap; brittle on rare-but-real expensive cases (breaking-change CVEs that genuinely need more headroom).
- **Per-invocation + per-workflow running-total in one API, with explicit override.** Synth. Both layers; running-total as a kwarg so Phase 13's middleware swaps in cleanly; `--allow-cost-overrun=<usd>` raises the per-invocation ceiling with a loud audit event.

## Decision

`LlmInvocationGuard` exposes one method:

```python
class LlmInvocationGuard:
    def __init__(self, *, per_invocation_ceiling_usd: Decimal,
                 per_workflow_ceiling_usd: Decimal,
                 rates: RateTable) -> None: ...
    def precheck(self, request: LlmRequest, *,
                 running_total_usd: Decimal) -> None:
        """Raises CostCeilingBreached if either ceiling would be breached."""
```

Defaults: per-invocation $5.00; per-workflow $0.50 ([production ADR-0025](../../../production/adrs/0025-per-workflow-cost-cap.md) aligned). Estimation is `chars/4 × $/token + max_tokens × $/output_token` — conservative ~20% high; documented as disaster-prevention, not micro-budgeting. `--allow-cost-overrun=<usd>` opt-in flag raises the per-invocation ceiling and emits `budget.overrun.allowed` audit event.

`CostEmitter` writes `cost-ledger.jsonl` entries under `.codegenie/remediation/<run-id>/` in the shape Phase 13's tiered roll-up consumes verbatim ([production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md) aggregation key `(workflow_id, stage, node, model)`).

**Three-layer enforcement** (defense-in-depth):
1. **L1 preflight** — `LlmInvocationGuard.precheck` refuses before the API call.
2. **L2 `max_tokens`** — Anthropic-side enforcement on the request body.
3. **L3 egress byte cap (Linux jailed only)** — 128 KB hard truncate at the `EgressProxy`; truncated response → reject as adversarial; no retry.

## Tradeoffs

| Gain | Cost |
|---|---|
| Per-invocation ceiling catches single-prompt disasters; per-workflow ceiling catches multi-call workflows | Two ceilings to configure; defaults differ; operators must understand both |
| Running-total kwarg is the integration shape Phase 13's middleware swaps into — no Phase 13 rewrite | Phase 4 carries the running total in the caller (`FallbackTier`); not a global; explicit-is-better-than-implicit |
| Explicit override (`--allow-cost-overrun=<usd>`) with a loud audit event provides an escape valve without normalizing overruns | Operators who blanket-enable the flag at portfolio scale silently overrun; mitigated by dashboard alert on `budget.overrun.allowed` event volume |
| Three-layer defense (preflight + max_tokens + egress byte cap) means no single layer must be trustworthy | Egress byte cap is Linux-only (the EgressProxy doesn't run on macOS); macOS dev mode relies on L1+L2 only — surfaced as known platform asymmetry |
| `CostLedgerEntry` schema matches [production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md) verbatim — Phase 13 reads it without migration | Schema must include `cache_creation_input_tokens` and `cache_read_input_tokens` for cache-hit-rate accounting; Anthropic SDK shape changes have broken this twice in 2025–2026 (mitigated by `sdk_minor` pin per [ADR-0007](0007-anthropic-model-pin-via-versioned-alias.md)) |
| Estimation is ~20% high (chars/4 conservative); refusals are loud, not silent | Real CVE remediations near the $5.00 ceiling will sometimes refuse legitimately; operators bump per-call with `--allow-cost-overrun` |

## Consequences

- `LlmInvocationGuard` lives in `src/codegenie/llm/guard.py`. Stateless; reads `rates.yaml` on construction.
- `CostEmitter` writes JSONL entries to `.codegenie/remediation/<run-id>/cost-ledger.jsonl`. Phase 13 consumes this verbatim; Phase 4 ships the writer.
- `cost.llm.invoked` audit event fields: `(workflow_id, stage="planning", node="rag_llm_engine", model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_usd, latency_ms)`.
- Phase 13's Budget Enforcer middleware replaces `LlmInvocationGuard.precheck` with a richer running-total + per-task-class + tiered direct/amortized/overhead implementation ([production ADR-0027](../../../production/adrs/0027-cost-attribution-model.md)). The kwarg signature is preserved.
- Phase 5's three-retry default (per [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md)) calls `precheck` between retries with the updated running total.
- `--allow-cost-overrun=<usd>` is the only escape valve; surfaced via dashboard alerts when usage exceeds threshold.

## Reversibility

**Medium.** Replacing the running-total kwarg with a different shape (e.g., a context manager that auto-tracks the workflow total) is a Phase 13 rewrite. Removing the override flag tightens security at the cost of breaking-change-CVE remediations. The *layered enforcement* is durable; the *threshold defaults* are configuration.

## Evidence / sources

- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Cost ceiling enforcement"
- `../final-design.md §"Components"` #6 — `LlmInvocationGuard` + `CostEmitter`
- `../final-design.md §"Departures from all three inputs"` #5 — running-total Guard
- `../phase-arch-design.md §"Component design"` #9 — three-layer enforcement
- `../critique.md §best-practices hidden assumption #3` — running-total interface gap
- Production [ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md) — cost observability
- Production [ADR-0025](../../../production/adrs/0025-per-workflow-cost-cap.md) — per-workflow cap
- Production [ADR-0027](../../../production/adrs/0027-cost-attribution-model.md) — three-tier attribution
