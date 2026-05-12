# ADR-0006: No retry inside the Phase 3 orchestrator; transient-I/O retry only inside `LockfileResolver`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** retry · escalation · linear-orchestrator · phase-5-handoff · scope-discipline
**Related:** [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md), ADR-0007, [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)

## Context

Production ADR-0014 commits to a three-retry default per gate transition. The three competing designs each placed the retry in a different layer:

- **Performance-first** retried inside the orchestrator on transient `npm` errors plus on recipe failure — pulling retry up into Phase 3.
- **Security-first** redefined three-retry as a "deterministic parameter sweep" (Retry 1 widens the version range; Retry 2 tries the next-up patched version) — placing what is functionally Phase-4 planner work into Phase 3.
- **Best-practices** explicitly deferred all retry to Phase 5.

The critic dismantled the first two (`critique.md §"Attacks on performance-first" §"Concrete problems" #2`, `§"Attacks on security-first" §"Concrete problems" #5`): performance-first's retry-in-orchestrator means Phase 5 has to *retire* one of the retry layers (violating extension-by-addition) or live with two policies in series; security-first's parameter sweep does Phase-4-flavored work in Phase 3 and creates the same collision when Phase 4 lands its RAG/LLM fallback (`§"Roadmap-level critiques" #1 "Phase 5"`). Both fail the "Phase 3 is the deterministic floor Phase 4 wraps; Phase 5 wraps Phase 4" promise (`production design.md §3`).

The synthesis defers all retry to Phase 5 (`final-design.md §"Retry & escalation"` #17), with one narrow exception that the critic specifically accepts: transient I/O retry inside `LockfileResolver`'s `npm install --package-lock-only` wrapper, where the failure mode is genuinely flaky network and the retry is bounded (≤ 3, transient codes only).

## Options considered

- **Three-retry in orchestrator on every gate [P].** Phase 5 has to retire it. Two retry layers collide.
- **Parameter-sweep retry (Retry 1 widens range, Retry 2 next-up patched version) [S].** Phase-4 planning work in Phase 3. Collides with Phase 4 RAG/LLM fallback.
- **Defer all retry to Phase 5, including transient I/O [strict B].** Phase 3's `LockfileResolver` fails fast on any transient `npm` ETIMEDOUT/EAI_AGAIN, even though the same exact subprocess call would succeed on retry. Operational friction; the critic's "transient-I/O retry inside one subprocess wrapper" exemption applies (`§"Attacks on performance-first" #2` accepts this narrow case).
- **Defer all retry to Phase 5; transient-I/O retry only inside `LockfileResolver`'s subprocess wrapper [synth].** Linear orchestrator. One narrow, bounded exception. Phase 4 wraps with planner-driven retry. Phase 5 wraps with gate retry.

## Decision

**Phase 3's orchestrator is six linear function calls in sequence. No retry. No async. No state machine.**

- `transforms/coordinator.remediate(repo_root, cve_id, *, run_id, config) -> RemediationReport` is the only function the orchestrator exposes.
- Stage transitions emit typed audit events; failures preserve the worktree + branch on disk; exit codes are documented (`final-design.md §"Architecture"` exit-code table).
- **The single exception:** `LockfileResolver.run()` wraps `npm install --package-lock-only --ignore-scripts --no-audit --no-fund` with **bounded transient-I/O retry** — up to **3 attempts**, **only** on these exit codes / signature matches:
  - Network errors: `ENOTFOUND`, `EAI_AGAIN`, `ECONNRESET`, `ETIMEDOUT`
  - npm-reported transient codes: `transient_npm_codes` constant in the resolver module
- This is **transient I/O retry inside one subprocess wrapper**, **not policy retry**. The retry is invisible to the orchestrator; from the orchestrator's perspective, `LockfileResolver.run()` either succeeds or fails.
- **No retry on:** recipe engine failures, lockfile policy violations (ADR-0007), validator failures, test failures, build failures, manifest write-back errors, audit chain breaks. All fail-fast in Phase 3.
- **Phase 4 wraps** the linear orchestrator with planner-driven retry (RAG/LLM fallback on `RecipeSelection.reason != "matched"` per ADR-0004; structured-error-driven re-planning).
- **Phase 5 wraps** that with the three-retry gate machinery per production ADR-0014, including `LockfilePolicyScanner` widening (ADR-0007).
- **Phase 6 wraps** as a LangGraph state machine *without changing the orchestrator's signature or `RemediationReport` schema* (`final-design.md §"Roadmap coherence check"`).

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 3 is the deterministic floor it claims to be — Phase 4 wraps it; Phase 5 wraps that; no retry collision | Phase 3 alone fails fast on flaky `npm test` runs (e.g., timing-sensitive integration tests); operator re-runs manually until Phase 5 lands |
| Phase 4's LLM/RAG router doesn't fight an in-orchestrator retry — clean compositional boundary | The critic's "transient-I/O retry inside lockfile resolver" exception is a *real* exception; the implementer must resist the urge to generalize it |
| `LockfileResolver`'s narrow retry is bounded (≤ 3) and signature-gated (specific codes only) — cannot widen accidentally | The transient-code list is a tunable that lives in code; CI test asserts the retry happens on exactly the listed codes, not others |
| Linear orchestrator is six function calls — readable, debuggable, no state machine needed | No graceful recovery from any non-transient-I/O failure in Phase 3; the operator must understand the failure manually until Phase 4/5 land |
| `RemediationReport` schema is the contract Phase 4–9 preserve; defining it now under linear semantics keeps the schema simple | Phase 4's retry-state additions (which attempt won, RAG matches considered) must extend `RemediationReport` additively (`final-design.md §"Roadmap coherence check"` Phase 4) |
| Exit codes 4–8 each correspond to a specific failure layer (no_recipe, transform_fail, validation_fail, policy_violation, signal_escalate) — operators see which stage halted | Granular exit codes are an API surface; renumbering or adding more requires coordination with Phase 5/11 consumers |

## Consequences

- `src/codegenie/transforms/coordinator.py` ships as six linear function calls; the docstring explicitly states "no retry of its own except transient I/O inside `LockfileResolver`."
- `src/codegenie/transforms/validation/install.py` and `test.py` and `build.py` and `lockfile_policy.py` all fail-fast on first failure.
- `src/codegenie/recipes/engine.py`'s `NcuRecipeEngine.apply()` and `OpenRewriteEngineStub.apply()` do **not** retry internally.
- `LockfileResolver.run()` retries with exponential backoff (250 ms × 2 ^ attempt) up to 3 attempts on `transient_npm_codes`; logs each attempt; the audit event `npm.install.run` carries an `attempts: int` field.
- `tests/unit/test_lockfile_resolver_transient_retry.py` asserts retry happens for each listed code and does not happen for others.
- `tests/integration/test_remediate_orchestrator_no_retry.py` asserts non-transient failures exit fast (no second attempt).
- Phase 4's planning coordinator reads `TransformOutput.errors` and `RecipeSelection.reason` (ADR-0004) and decides RAG/LLM routing; it composes by calling `coordinator.remediate(...)` and inspecting the return, never by editing it.
- Phase 5's gate machinery wraps `coordinator.remediate` with `production ADR-0014`'s three-retry policy and `LockfilePolicyScanner` widening (ADR-0007).
- The `--allow-policy-violations`, `--allow-test-network`, `--allow-stale-feeds` flags (ADRs 0007, 0005, 0008) are operator-driven escape valves, **not retries**.

## Reversibility

**Medium.** Adding retry inside the orchestrator later (if Phase 4/5 don't land in time and operators demand it) is mechanically easy — but every existing Phase 3 caller that depends on fail-fast semantics would need re-review. Widening the `LockfileResolver`'s transient-code list is low cost in code, but each addition needs explicit justification (which failure mode is genuinely transient vs. which is a real bug). Removing the narrow exception entirely (strict-defer-everything) is **high cost in operational friction** — flaky `npm install` is a real and frequent failure mode that retry handles cheaply.

## Evidence / sources

- `../final-design.md §"Goals" §"Retry & escalation"` #17, #18
- `../final-design.md §"Components" #5 "LockfileResolver"`
- `../final-design.md §"Components" #10 "Linear sync orchestrator"`
- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Three-retry semantics"
- `../phase-arch-design.md §"Component design" #5 "LockfileResolver"`
- `../phase-arch-design.md §"Component design" #9 "RemediationOrchestrator"`
- `../critique.md §"Attacks on performance-first" #2` — accepts the narrow transient-I/O exception
- `../critique.md §"Attacks on security-first" §"Concrete problems" #5` — parameter sweep is Phase-4 work
- `../critique.md §"Roadmap-level critiques" #1 "Phase 5"` — retry-layer collision
- [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md) — three-retry per gate
- [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — Phase 4's wrap pattern
