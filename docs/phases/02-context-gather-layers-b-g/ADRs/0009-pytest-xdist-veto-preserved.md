# ADR-0009: `pytest-xdist` veto preserved — portfolio CI lane stays serial; no Phase 0 reversal

**Status:** Accepted
**Date:** 2026-05-14
**Tags:** ci · testing · scope · phase-fidelity · veto-preservation · flake-budget
**Related:** [Phase 0 ADR — pytest-xdist veto](../../00-bullet-tracer-foundations/ADRs/), [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md)

## Context

Phase 0's synthesizer recorded a 10/4 vote vetoing `pytest-xdist` for the test lane (Phase 0 synthesizer ledger). The recorded rationale was the shared-fixture race surface — fixtures that exercise `.codegenie/cache/`, temp directories, and external CLI invocations are not safely runnable in parallel by `pytest-xdist`'s worker model — for a zero-parallelism win on a small test count. The veto has held through Phase 1.

Phase 2 introduces the five-fixture portfolio (`tests/fixtures/portfolio/{minimal-ts, native-modules, monorepo-pnpm, distroless-target, stale-scip}/`) and the adversarial `tests/adv/phase02/` lane (≥ 6 tests including the load-bearing `test_stale_scip_fixture.py`, `test_secret_in_source.py`, `test_image_digest_drift.py`). Wall-clock budget grew: cold gather on each fixture is 90–140 s; the portfolio lane plus adversarial lane is the longest single CI job in the system, estimated ≤ 6 min serial.

The performance lens proposed reversing the Phase 0 veto for the portfolio lane: "the portfolio fixtures live in their own directories; they can't race each other; let xdist parallelize them." Its own Open Question §4 admitted "the synthesizer should confirm whether this is a reversal of Phase 1 §2.2." The critic ([critique.md §"Attacks on the performance-first design" #3](../critique.md), critic finding #8) attacked this as a unilateral reversal of a recorded Phase 0 commitment without an ADR — the kind of decision Rule 7 (surface conflicts, don't average them) names: when a recent commitment contradicts a current preference, the recent commitment wins until explicitly amended.

The synthesis (`final-design.md §"Conflict-resolution table" row 5`, §"Goals"`) chose to preserve the Phase 0 veto and to **measure** the assumption that serial portfolio CI fits within budget. This ADR records the decision and the failure mode that would trigger reconsideration.

## Options considered

- **Option A — Reverse the Phase 0 veto for the portfolio lane.** **Pattern:** Parallel/xdist for IO-bound tests. Performance lens's pick. Unilateral reversal of a recorded 10/4 veto; critic finding #8. The portfolio fixtures' isolation is real per directory but the shared invocation surface (`.codegenie/cache/` regeneration scripts, tool-cache lookups, external CLI subprocess pools, port collisions on `docker` daemons) re-introduces the exact race surface Phase 0 rejected.
- **Option B — Reverse the veto repo-wide.** Maximum parallelism. Same problems as Option A at greater scope.
- **Option C — Preserve the veto; portfolio + adversarial lanes run serial; advisory bench canary asserts wall-clock fits the budget; named escape valve if budget regresses.** **Pattern:** Phase boundary discipline + measurement over assertion. Synthesis pick.

## Decision

Adopt **Option C — preserve the Phase 0 `pytest-xdist` veto for Phase 2.** The portfolio lane (`tests/integration/portfolio/`, `tests/golden/probes/<probe>/<fixture>.json`) and the adversarial lane (`tests/adv/phase02/`) run **serial**. The advisory bench canary `tests/bench/bench_portfolio_walltime.py` measures cold + warm p50 per fixture and flags ≥ 50 % regression as a PR comment (not a build gate). The hosted-runner emulation bench `tests/bench/bench_portfolio_walltime_hosted_runner.py` (Gap 2 improvement) runs nightly with `CODEGENIE_FORCE_CPU_COUNT=2` and uses build-fail threshold ≥ 100 % (i.e., > 360 s p95). The named escape valve — committing per-fixture `.codegenie/cache/` blobs to flip the regenerate-each-run policy — is documented as the alternative if walltime regresses past 8 minutes. **Pattern: Veto preserved; measurement over assertion; named escape valve if budget regresses.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 0's recorded 10/4 veto is honored — Rule 7 (surface conflicts, don't average them; the more recent / more tested decision wins) applied verbatim | Portfolio lane CI walltime is a hard ~6-minute serial spend; PR feedback is ~6 min slower than a parallel-portfolio reality where every fixture runs in its own slot |
| Zero shared-fixture race surface — `.codegenie/cache/` regeneration scripts, tool-cache lookups, `docker` daemon port allocation, external CLI subprocess pools all run one-at-a-time; flake budget stays low | Theoretical parallel speedup (5 fixtures × 90 s ≈ 450 s serial vs. ~90 s parallel max) is not captured; for the portfolio specifically, the synthesis estimates we lose 4–5 min/PR |
| Bench canaries are **advisory** (PR comment, not block) on every PR; the hosted-runner emulation bench is build-gating only at ≥ 100 % regression (> 360 s p95) — the measurement infrastructure tells us when the assumption is wrong | A PR that incidentally regresses portfolio walltime by 40 % doesn't fail CI; the comment is the loud signal, and a reviewer must act on it |
| Named escape valve — commit per-fixture `.codegenie/cache/` blobs to flip the regenerate-each-run policy — is documented (open question §6 in the synthesis) and is the operator's lever if the assumption breaks | Committing cache blobs makes fixture diffs opaque (binary diff in `tests/fixtures/portfolio/*/.codegenie/cache/`); the trade is reviewability vs. CI speed; the synthesis picks reviewability now |
| The `cpu_count()=2` hosted-runner case is **measured** by `bench_portfolio_walltime_hosted_runner.py` — the critic [P] §"hidden assumption" #2 ("per-tier semaphores degenerate to starvation on small runners") generalizes to "any concurrency story degrades on small runners"; preserving the veto means we don't need a parallel-vs-serial branch for runner size | macOS dev hosts and `cpu_count()=8` developer laptops experience the same serial walltime as `cpu_count()=2` CI — dev feedback is slow on the portfolio lane regardless of hardware |
| If Phase 3+ proves the portfolio walltime is genuinely binding (CI feedback loops slow material PR velocity), the ADR can be amended with measurement evidence — the reversal path is open and explicit | Future engineers may experience friction wanting to enable xdist for "obvious" speedups; the friction is the point; recorded ADR amendments are how Phase 0 commitments evolve |

## Pattern fit

Pattern: **Veto preservation under Rule 7 + Measurement over assertion** (`design-patterns-toolkit.md §"Anti-patterns to flag explicitly"` — pattern soup / ceremony avoidance; combined with toolkit's broader "don't average commitments" discipline encoded in user's global rules). The decision is not a technical pattern — it is a phase-boundary discipline pattern. The named escape valve makes the commitment **revisable but not rewritable**: a future amendment is an ADR, not a silent flag flip. Composes with [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md)'s deterministic-gather commitment — `pytest-xdist` doesn't compromise gather determinism directly, but the shared-fixture race surface compromises **test determinism**, which is what Phase 0's veto actually defended.

## Consequences

- `pyproject.toml` does NOT list `pytest-xdist` in `dev` extras. The `pytest` invocation in CI (`.github/workflows/ci.yml` or equivalent) runs without `-n auto` / `-n N` flags.
- `tests/bench/bench_portfolio_walltime.py` (advisory) — five-fixture cold + warm p50 captured per run; baseline JSON committed under `tests/bench/baselines/`. ≥ 50 % delta = PR comment, no block.
- `tests/bench/bench_portfolio_walltime_hosted_runner.py` (Gap 2 improvement; nightly, not per-PR) emulates `cpu_count()=2` via `CODEGENIE_FORCE_CPU_COUNT=2`. ≥ 50 % delta = comment-on-PR (advisory); ≥ 100 % delta (> 360 s p95 on the hosted runner) = build-fail.
- The named escape valve — committing per-fixture `.codegenie/cache/` blobs — is documented in `tests/fixtures/portfolio/README.md` (synthesis open question §6). The trade is named: faster CI vs. opaque fixture diffs.
- A future ADR amendment that re-enables `pytest-xdist` for any test lane requires (1) measurement evidence that serial CI is materially binding (e.g., 95th-percentile PR feedback delay > N minutes for ≥ K weeks), (2) explicit identification of the shared-fixture surface and how the test setup eliminates races (file-system isolation per worker, port allocation, etc.), (3) a `tests/adv/test_xdist_isolation.py` adversarial test demonstrating no race under contention.
- Other forms of parallelism stay on the rejected list for the same reasons: no internal `ThreadPoolExecutor` inside any probe (final-design §12, critic [P] hidden-assumption #3); no per-tier coordinator semaphores (final-design §13, critic [P] hidden-assumption #2). The single `Semaphore(min(cpu_count(), 8))` from Phase 0 is preserved.

## Reversibility

**High.** Re-enabling `pytest-xdist` later is a `pyproject.toml` edit + a `pytest` invocation change + an ADR amendment to this one with the measurement evidence. The test bodies don't need to change unless they have hidden race surfaces (which the amendment process forces to surface). The harder reversal is **un-doing the xdist if races later prove real** — flaky tests in CI are a familiar trap; preserving the veto until measurement justifies reversal keeps that door closed.

## Evidence / sources

- `../final-design.md §"Goals"` — wall-clock targets; no `pytest-xdist`
- `../final-design.md §"Conflict-resolution table" row 5` — Phase 0 veto holds
- `../final-design.md §"Patterns considered and deliberately rejected" #6` — explicit refusal
- `../final-design.md §"Resource & cost profile" §"CI walltime delta vs. Phase 1"` — serial CI walltime budget
- `../phase-arch-design.md §"Non-goals"` (`pytest-xdist` veto)
- `../phase-arch-design.md §"Gap analysis & improvements" Gap 2` — `bench_portfolio_walltime_hosted_runner.py` hidden-assumption measurement
- `../phase-arch-design.md §"Open questions deferred to implementation" §6` — named escape valve (commit cache blobs)
- `../critique.md §"Attacks on the performance-first design" #3` — unilateral reversal framing
- [Phase 0 ADRs](../../00-bullet-tracer-foundations/ADRs/) — recorded 10/4 veto
- [Production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md) — deterministic-gather commitment (test determinism is its sibling)
- User global Rule 7 (`/Users/dannytrevino/.claude/CLAUDE.md`) — "Surface conflicts, don't average them; the more recent / more tested decision wins"
