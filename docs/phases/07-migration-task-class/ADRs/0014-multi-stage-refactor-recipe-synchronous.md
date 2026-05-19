# ADR-0014: `DockerfileMultiStageRefactorTransform` is synchronous; no per-stage `asyncio.gather`

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** honesty · cpu-bound-async · critic · simplicity
**Related:** [0013](0013-dockerfile-recipe-engine-dockerfile-parse.md), [Phase 3 ADR-0008](../../03-vuln-deterministic-recipe/ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md)

## Context

Performance-first's lens design proposed parallelizing per-stage AST manipulation in `DockerfileMultiStageRefactorTransform` via `asyncio.gather`, claiming ~95 ms p99 for a 4-stage Dockerfile (vs. synchronous ~350 ms). The critic landed this as **theatrical** in `critique.md`:

> "`asyncio.gather` over per-stage CPU-bound Dockerfile AST work without `run_in_executor` is theatrical; performance's claim was wrong. […] CPU-bound AST work in async without an executor pool just runs sequentially with overhead, not in parallel."

Python's `asyncio.gather` does not parallelize CPU-bound work without an explicit `loop.run_in_executor(...)` call routing the work to a thread or process pool. Per-stage `dockerfile-parse` AST manipulation is pure CPU work. Wrapping it in `asyncio.gather` without an executor produces a sequential execution with async overhead — slightly slower than the plain synchronous loop.

`final-design.md §Components §10` and `phase-arch-design.md §Component design §11` lock the synchronous shape. The "performance gain" was an illusion; honesty + simplicity win.

## Options considered

- **Option A — Per-stage `asyncio.gather` (no executor).** Performance-first. **Pattern:** Async fan-out. **Rejected** — theatrical; sequential in practice; no parallelism without `run_in_executor`.
- **Option B — `asyncio.gather` with `loop.run_in_executor(thread_pool, ...)`.** **Pattern:** True parallelism. Real ~250 ms savings on a 4-stage Dockerfile; but introduces thread-pool tuning, GIL contention concerns, error-propagation complexity, and a per-workflow thread-pool lifecycle to manage. Cost > benefit at Phase 7's scope (2-3 stage Dockerfiles typical).
- **Option C — Plain synchronous loop.** **Pattern:** Simplicity-first. ≤ 350 ms p99 honest; no async theater; no thread-pool complexity.

## Decision

Adopt **Option C.** `DockerfileMultiStageRefactorTransform.apply(ctx)` is a synchronous function (or `async def` with no `await` points for AST work — same outcome). Per-stage AST manipulation runs in a plain Python `for` loop. No `asyncio.gather` over per-stage work. No `run_in_executor` thread pool. p99 wall-clock for the recipe is ≤ 350 ms on typical 2-3 stage Dockerfiles; the recipe accepts this as the honest cost.

If telemetry from Phase 13 shows multi-stage recipe wall-clock is genuinely the bottleneck on production workloads, a future Phase-13 ADR can revisit with concrete data and ship `loop.run_in_executor` plus thread-pool tuning — but that's a data-driven future decision, not a Phase-7 speculative optimization.

## Tradeoffs

| Gain | Cost |
|---|---|
| Honest about CPU-bound work — no async theater claiming parallelism that doesn't happen | ≤ 350 ms p99 on a 4-stage Dockerfile vs. a theoretical ~95 ms with true parallelism. In practice, 2-3 stage Dockerfiles dominate the corpus; the gap shrinks |
| Simpler shape: one for-loop, no thread-pool lifecycle, no GIL contention concerns, no error-propagation complexity from `asyncio.gather` | If a future workload has 8+ stage Dockerfiles, the synchronous shape costs proportionally more wall-clock. Mitigated: rare in practice; named for Phase 13 telemetry to surface if real |
| Performance-first's `[P-v13]` `asyncio.gather` claim is rejected with the critic's evidence — design closes the speculation honestly | Operators familiar with async-everywhere conventions may expect `asyncio.gather`; this ADR is the explicit refusal |
| Property test idempotence is straightforward (synchronous loop, deterministic output); no async-test fixtures | If Phase 8+ workflows route Dockerfile recipes through async dispatch, the sync recipe still works (it's just one `await` call from the caller's perspective) |
| Aligns with Rule 2 (Simplicity First) and Rule 12 (Fail loud) — the cost is honest; the gain is honest | The "could be faster" line in `critique.md` is preserved as a deferred-improvement note, not as a TODO in code |

## Pattern fit

Implements **Simplicity-first** (Rule 2; toolkit §Architecture / boundaries — the cheapest abstraction): plain synchronous loop. Rejects **Async fan-out without executor** (toolkit §Performance anti-patterns — async theater). Mirrors [Phase 3 ADR-0008](../../03-vuln-deterministic-recipe/ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md)'s rejection of hedged-race parallelism in favor of deterministic serial fallback.

## Consequences

- `plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py` uses a plain `for` loop over stages.
- The recipe's wall-clock target is documented as `≤ 350 ms p99` (`final-design.md §Resource & cost profile`).
- The recipe's docstring includes a forward-reference: "Per-stage parallelism via `loop.run_in_executor` is a deferred optimization; revisit with Phase 13 telemetry if multi-stage wall-clock becomes the workflow bottleneck."
- Property test `test_dockerfile_multi_stage_idempotence.py` asserts the synchronous output is byte-identical across runs and across stage-order permutations.
- No thread-pool lifecycle is introduced in the plugin or the orchestrator.
- Performance-first's `[P-v13]` claim is rejected on the record; the gap between claimed ~95 ms and honest 350 ms is documented in `final-design.md §Components §10`.

## Reversibility

**High.** If Phase 13 telemetry justifies it, swapping the synchronous loop for `loop.run_in_executor(thread_pool, _apply_stage, stage)` is a one-file change inside the recipe, plus thread-pool wiring at the orchestrator level. The recipe's external contract (extends `Transform`, returns `TransformOutcome`) is unaffected.

## Evidence / sources

- `../final-design.md §Components §10` (`DockerfileMultiStageRefactorTransform` — "**No `asyncio.gather`** — the per-stage parallelism performance proposed buys ~250 ms on a 4-stage Dockerfile and adds complexity"), §Patterns considered and deliberately rejected ("`asyncio.gather` over per-stage CPU-bound Dockerfile AST work")
- `../phase-arch-design.md §Component design §11` (`DockerfileBaseImageSwapTransform` + `DockerfileMultiStageRefactorTransform` — synchronous shape)
- `../critique.md §Attacks on the performance-first design "Pattern claims that don't survive scrutiny"` ("Hot path is fully memoizable" / `asyncio.gather` is theatrical)
- [Phase 3 ADR-0008 — Deterministic serial fallback (precedent: reject hedged-race parallelism)](../../03-vuln-deterministic-recipe/ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md)
