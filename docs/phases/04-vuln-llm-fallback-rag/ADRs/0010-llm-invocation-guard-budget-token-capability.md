# ADR-0010: `LlmInvocationGuard` + `BudgetToken` — per-workflow budget cap as a function-signature capability

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** capability-pattern · circuit-breaker · type-driven-safety · cost-discipline
**Related:** [production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md) · [production ADR-0025](../../../production/adrs/0025-per-workflow-cost-cap.md) · ADR-0001 (this phase)

## Context

Phase 4 introduces the first place codewizard-sherpa spends money per-request (LLM tokens). [Production ADR-0025](../../../production/adrs/0025-per-workflow-cost-cap.md) commits the project to "hard per-workflow cost cap with explicit override" as a Temporal-middleware-enforced pattern in the production service. Phase 4 (the local POC) needs the same control at its scale: a *bug* in `LeafLlm.invoke` that retries a never-resolving prompt should not silently burn tokens until a human notices.

The three design lenses split: performance emitted cost events and deferred enforcement to Phase 13 (the production ledger); best-practices shipped no per-workflow cap at all; security shipped `LlmInvocationGuard` as a hard cap exposed as a *required function-signature argument* — calling `LeafLlm.invoke(...)` without a `BudgetToken` is a type error.

The critic acknowledged the security shape as load-bearing-correct, with one caveat: "capability passed through ten frames" anti-pattern risk (`critique.md §"Anti-patterns from the toolkit's flag on sight list"`). The mitigation must be that the token flows through *few* frames, not many.

## Options considered

- **No cap; events only** (performance lens). `LlmInvocationGuard` emits `cost.llm.call` events; no enforcement. Phase 13's production ledger eventually enforces. **Pattern:** Observability without control. A bug that retries forever spends tokens until alerts fire.
- **No cap at all** (best-practices lens). Defer entirely to Phase 13. **Pattern:** Defer-to-platform. Phase 4 ships a system that can silently runaway in spend.
- **Hard cap via a global counter the adapter checks** (alternative). `LlmInvocationGuard.check_and_decrement()` called at top of `invoke`. **Pattern:** Procedural check. A missed-check bug (or a new code path that forgets) silently bypasses the cap.
- **Hard cap as a function-signature capability** (security lens). `LeafLlm.invoke(..., token: BudgetToken)` — calling without one is a `TypeError` at call construction. **Pattern:** Capability pattern (financial) + Circuit breaker.

## Decision

`LlmInvocationGuard` is a per-workflow object initialized with `max_tokens`, `max_dollars`, `per_call_max_tokens`, and an `event_log`. `LeafLlm.invoke(...)` declares `token: BudgetToken` as a required keyword arg; the adapter cannot be called without one. The `BudgetToken` is a `frozen=True, extra="forbid"` Pydantic model with `precharged_tokens`, `precharged_dollars`, `issued_at`, and a private `_marker: Literal["budget_token"]` discriminator. The token flows through exactly two frames: `FallbackTier → LeafLlm.invoke`. **Defaults:** `max_tokens_per_workflow=250_000`, `max_dollars_per_workflow=$1.50`, `per_call_max_tokens=32_000`. **Pattern:** Capability pattern (financial) + Circuit breaker — token is a function-signature property, not a runtime check.

## Tradeoffs

| Gain | Cost |
|---|---|
| A missed-check bug is structurally impossible — `invoke()` without a token is `TypeError` at call construction, caught by `mypy --strict` | The cap defaults (250K / $1.50) are uncalibrated Q1-2026 estimates; Phase 13's cost ledger will calibrate; until then conservative numbers |
| Blast radius on runaway spend is bounded *per workflow* (not per process); concurrent workflows have independent guards | The cap is per-workflow; a portfolio of N workflows can still burn N × cap; Phase 13's per-portfolio cap is the next layer |
| `running_total()` is a typed surface Phase 5's `GateRunner` consumes across retries — the budget composes naturally with Phase 5's retry envelope | Reconcile is idempotent on `BudgetTokenId` — duplicate reconcile calls must be safe; tested in `tests/unit/fallback/test_budget_guard.py` |
| `BudgetToken` flows through exactly two frames (`FallbackTier → LeafLlm.invoke`) — the toolkit's "capability passed through ten frames" anti-pattern is avoided by design (token does NOT flow through `PromptBuilder` or `FenceWrapper`) | Three frames would already feel like a context object trying to escape — discipline must hold as Phase 6's LangGraph migration lifts `FallbackTier` into a node |
| `cost.llm.call` event entries compose with Phase 5's `cost.sandbox.run` entries for Phase 13's eventual unified ledger | Decimal arithmetic for dollars must be exact (`Decimal`, not `float`); tested via Hypothesis property `tests/property/test_budget_decimal_exactness.py` |
| Override paths for known-expensive cases (per `roadmap.md`'s "operator-mode batch with elevated cap") arrive in Phase 4 as a configuration knob in `plugin.yaml`, not as a runtime flag | Operator override audit trail is load-bearing — every override emits an event and the override is operator-acknowledged |

## Pattern fit

The toolkit's Capability pattern fit is exact: "A token (object) that grants permission to perform an action. Holding the token = having the capability. No capability = no operation." `BudgetToken` is the financial capability; `LeafLlm.invoke` is the action. The toolkit names "cost ledger access (`SpendCapability(budget_usd=…)`)" as the canonical example.

The toolkit's anti-pattern flag "Capability passed through ten frames" is the load-bearing constraint: the token flows *only* through `FallbackTier → LeafLlm.invoke`. Two frames. It does *not* flow through `PromptBuilder`, `FenceWrapper`, `EgressGuard`, or `SolvedExampleRetriever`. The capability is local to the leaf-call site, not a global ambient permission.

Circuit Breaker is the second pattern at play: cap-exceeded `BudgetExceeded` raises before any leaf call, halting the spend (the "open" state of the breaker). The breaker resets per-workflow (no half-open / probing state — Phase 4 doesn't need that complexity).

## Consequences

- `LeafLlm.invoke` cannot be called without a `BudgetToken` — `mypy --strict` enforces; test `tests/unit/fallback/test_budget_guard.py::test_invoke_requires_token_typecheck` asserts at type-check time.
- `LlmInvocationGuard.precharge(requested_tokens)` is the only mint path; `precharge` raises `BudgetExceeded` if `running_total + requested > max`.
- `LlmInvocationGuard.reconcile(token, actual_in, actual_out, actual_dollars)` updates running totals; idempotent on `BudgetTokenId`.
- `BudgetExceeded` raises return as `RecipeApplication.Refused(reason=BUDGET_EXCEEDED)` from `FallbackTier.run` — typed; consumed by Phase 5's HITL escalation.
- Phase 5's `GateRunner` consumes `running_total()` across retries — `BudgetSnapshot` is the projection shape.
- Phase 13's eventual cost ledger composes `cost.llm.call` (Phase 4) + `cost.sandbox.run` (Phase 5) + others — the event vocabulary is forward-compatible.
- Audit events: `LeafKeyLoaded`, `LeafInvoked(prompt_digest_blake3)`, `LeafReturned(response_digest_blake3, tokens_in, tokens_out, cache_read, cache_creation)`, `BudgetReconciled`, `BudgetExceeded`.
- The 250K / $1.50 cap is recorded as Phase 4's initial calibration in `plugin.yaml`; Phase 13 cost-ledger evidence drives subsequent tuning.
- No environment-variable escape (`CODEGENIE_ANTHROPIC_KEY_CI` rejected per critic [S] hidden assumption #2); the API key flows via `keyring.get_password("codegenie", "anthropic_api_key") → SecretStr` only.

## Reversibility

**Low.** Removing the cap (defaulting `max_tokens=∞`) is a one-line config change but loses the runaway-spend guarantee. Changing `LeafLlm.invoke` to *not* require `BudgetToken` is a Protocol signature change consumed by every leaf adapter and Phase 5's retry envelope — high friction, requires phase amendment. Adjusting cap *values* is config (`plugin.yaml`); high reversibility there.

## Evidence / sources

- `../final-design.md §Component 5 — LlmInvocationGuard`
- `../final-design.md §Goal "Per-workflow hard budget cap"`
- `../phase-arch-design.md §Component 5 — LlmInvocationGuard + BudgetToken`
- `../phase-arch-design.md §Design patterns applied` row 4 (Capability + Circuit Breaker)
- `../phase-arch-design.md §Anti-patterns avoided` ("Capability passed through ten frames")
- `../critique.md §"Anti-patterns from the toolkit's flag on sight list"`
- [production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md) (cost observability)
- [production ADR-0025](../../../production/adrs/0025-per-workflow-cost-cap.md) (per-workflow cost cap pattern; this ADR is the Phase 4 instance)
