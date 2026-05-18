# ADR-0007: Phase 3 runs the repo's own tests inside `SubprocessJail`; Phase 5 wraps the retry envelope, not the inner validate

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** exit-criterion · phase-5-handshake · stage-6 · seam
**Related:** [0001](0001-ship-phase5-contract-surface-by-name.md), [0006](0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md), [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md)

## Context

Roadmap Phase 3 exit criterion (`docs/roadmap.md` Phase 3): "Given a Node.js repo with a known npm CVE, the system writes a working patch diff on a local branch that — when applied — **installs cleanly and passes the repo's own tests**." The "passes the repo's own tests" clause cannot be met without running `npm test`.

The three lens designs disagreed:
- **Performance lens** — implicitly skipped `npm test` (timing budget concern).
- **Security lens** — explicitly deferred test execution to Phase 5 (microVM concern).
- **Best-practices lens** — ran `npm ci` (install only).

The critic correctly flagged this as Issue 2 in `critique.md`: deferring test execution to Phase 5 means Phase 3 ships without meeting its own exit criterion. Phase 5's mandate is the **three-retry envelope** around Stage 6 (production ADR-0014), not the inner test execution itself — those are separable layers.

The architecture spec resolves it: Phase 3 runs both `npm install` and `npm test` inside `SubprocessJail` as part of Stage 6 Validate (`phase-arch-design.md §Component design C1`, §Departures from all three inputs #2, §Exit-criteria checklist). Phase 5 wraps `RemediationOrchestrator._validate_stage6` with `GateRunner` for the three-retry envelope; it does **not** replace the inner validate.

## Options considered

- **Option A — Phase 3 runs `npm install` only; defer `npm test` to Phase 5.** Phase 3 ships without satisfying its own exit criterion; Phase 5's gate envelope subsumes inner validation. **Pattern:** Phase-boundary violation — exit criterion shifts forward without explicit roadmap amendment. Misaligns the layering: gate envelope should wrap test execution, not own it.
- **Option B — Phase 3 runs install + test directly via `run_external_cli` (no jail).** Meets exit criterion but unjailed test execution on the operator's laptop is unsafe (postinstall scripts, network egress). **Pattern:** No isolation — defeats the security threat model.
- **Option C — Phase 3 runs `npm install` AND `npm test` inside `SubprocessJail` as part of Stage 6 Validate. Phase 5's `GateRunner` wraps the *retry envelope* around the orchestrator's `_validate_stage6` method.** **Pattern:** Pipeline + Hexagonal substrate — Phase 5 composes on top; Phase 3 owns the inner validate.

## Decision

Adopt **Option C.** `RemediationOrchestrator._validate_stage6(transform, ctx) -> StageOutcome` is the Phase-3 method that:

1. Applies `transform` to a temp worktree.
2. Calls `SubprocessJail.run(JailedSubprocessSpec(cmd=("npm", "install"), ...))` with `time_budget_s=180`.
3. Calls `SubprocessJail.run(JailedSubprocessSpec(cmd=("npm", "test"), ...))` with `time_budget_s=300`.
4. Collects 5 `TrustSignal`s (`build`, `install`, `tests`, `lockfile_policy`, `cve_delta`).
5. Returns `Validated(passed=True/False, failing=...)` via `TrustScorer.score(signals)`.

Phase 3 alone runs **zero retries** — on `passed=False`, the orchestrator returns the outcome. Phase 5's `GateRunner.run(transition=stage6_validate, ctx=GateContext(...))` is the retry envelope; it re-enters `_validate_stage6` up to 3 times with `ctx.prior_attempts` populated (per Phase 5 ADR-0002).

## Tradeoffs

| Gain | Cost |
|---|---|
| Roadmap exit criterion meetable from Phase 3 alone — `tests/integration/test_end_to_end_express_cve.py` is a true exit gate, not a Phase-5-dependent stub | +6–10 s wall-clock per workflow (npm install + npm test dominate); p50 budget of ≤ 18 s already accounts for this |
| Phase 5's `GateRunner` has a real, working `_validate_stage6` to wrap — no stub-then-replace migration | bwrap/sandbox-exec attack surface accepted; mitigated by `--ignore-scripts` enforcement at CLI + env (per ADR-0006) |
| The retry envelope (Phase 5) and the inner validate (Phase 3) are cleanly separated — production ADR-0014's three-retry policy is composition, not a Phase-3 concern | Phase 3's `_validate_stage6` is intentionally private (underscore-prefixed) yet load-bearing for Phase 5; the naming convention is documented in ADR-0001 |
| Stage-6 trust signals (5 of them) are emitted as `TrustSignal` records in Phase 3; Phase 5 widens via `@register_signal_kind` (05-ADR-0003) — additive | `Stage 6 Validate` becomes a polymorphic concept across phases; reviewers must understand the layering |
| Phase 3's bench `bench_workflow_e2e_warm` includes test execution — the performance envelope is honest about total time-to-PR, not just transform-application time | Test-suite quality of the target repo affects Phase-3 budgets; relative-budget assertions (vs 7-day rolling mean) handle variance |
| Operator gets a definitive verdict from a single Phase-3 invocation — no "install passed but test deferred" partial outcome | A repo with a flaky test suite returns `Validated(passed=False)` on the first run; Phase 5's retry will help, but Phase 3 alone returns the failure — documented behavior |

## Pattern fit

Implements **Pipeline / Chain of responsibility** (toolkit §Behavioral patterns) for the 5-node plugin subgraph + the orchestrator's stage sequence: each stage has a narrow contract, can short-circuit with a typed outcome, and passes to the next. **Hexagonal architecture** via the `SubprocessJail` Port carries the npm install + test commands under isolation. Composes cleanly with Phase 5's gate envelope: Phase 5 wraps the orchestrator's method, not the orchestrator's internals.

## Consequences

- `RemediationOrchestrator._validate_stage6` signature is fixed by ADR-0001 contract snapshot; Phase 5 wraps it via `GateRunner.run(transition=stage6_validate, ctx=...)`.
- Time budgets: `npm install --package-lock-only` 60 s; `npm install` (validate) 180 s; `npm test` 300 s — configurable via env vars, defaults in code.
- `tests/integration/test_end_to_end_express_cve.py` is the headline exit gate; CI-required; runs the full workflow end-to-end against the `express-cve-2024-21501/` fixture.
- `breaking-test-suite/` fixture exercises the `Validated(passed=False)` path explicitly — confirms Phase 3 alone does not retry.
- Phase 5's retry envelope re-enters `_validate_stage6` with `prior_attempts` populated; `ApplyContext.prior_attempts` ships empty in Phase 3 (dead weight) per ADR-0001.
- Adversarial test `tests/adversarial/test_postinstall_canary.py` runs in the same jail — confirms postinstall scripts are sandboxed even during `npm test`.
- `bench_workflow_e2e_warm` (p50 < 20 s, p95 < 35 s) is the SLO; relative-budget regression (> 25% vs 7-day rolling mean) fails CI.

## Reversibility

**Medium-low.** Removing `npm test` from Phase 3 would break the exit criterion and Phase 5 would have to add inner-validate ownership (currently it's only the retry envelope). The layering "Phase 3 owns inner; Phase 5 owns envelope" is hard to undo without re-shifting roadmap scope. Adding more validate steps (e.g., a security scan) is easy via the open `SignalKind` registry; removing test execution is the hard direction.

## Evidence / sources

- `docs/roadmap.md` Phase 3 exit criterion (verbatim: "passes the repo's own tests")
- `../phase-arch-design.md §Goals G1`, §Component design C1, §Departures from all three inputs #2, §Exit-criteria checklist
- `../final-design.md §Synthesis ledger row "npm test in Phase 3"` (score 14/15) and §Departures #2
- `../critique.md §Cross-design observations §Which disagreement matters most for *this* phase?` (Issue 2)
- [production ADR-0014 — three-retry default per gate](../../../production/adrs/0014-three-retry-default-per-gate.md)
- [Phase 5 ADR-0002 — additive `prior_attempts` kwarg](../../05-sandbox-trust-gates/ADRs/0002-additive-prior-attempts-kwarg.md)
