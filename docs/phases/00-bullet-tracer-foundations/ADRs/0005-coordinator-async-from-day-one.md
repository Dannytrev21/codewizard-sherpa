# ADR-0005: Coordinator is async from day one, one probe in Phase 0

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** coordinator · concurrency · interface · phase-evolution
**Related:** [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

`production/design.md §3.1` describes the Probe Coordinator as dispatching probes in parallel with a bounded worker pool. `../../../localv2.md §12` Week 1 lists "Coordinator (asyncio, bounded worker pool, per-probe timeout, failure isolation)" as Phase 0 scope.

The best-practices lens proposed shipping a **serial** coordinator in Phase 0 — citing Rule 2 (Simplicity First) — and adding async in Phase 1. `../critique.md §3.1.1` rejected this as a contract-breaking decision dressed as scoping: the coordinator's *interface* (`asyncio.Semaphore`, per-probe `asyncio.Task`, `asyncio.wait_for`) is itself a load-bearing convention the rest of the system inherits. Shipping serial-only means Phase 1 doesn't *add* concurrency; it *replaces* the coordinator. That's "scaffolding becomes the project" — exactly what Rule 2 is trying to avoid in the other direction.

Phase 14's continuous-gather model (production ADR-0006) needs the same dispatch interface. The interface lands in Phase 0 or it lands as a rewrite later.

## Options considered

- **Serial coordinator in Phase 0, async in Phase 1 (`[B]`).** Shortest Phase 0 path; defers concurrency until there's parallelism to win. Replaces, not extends, the interface in Phase 1.
- **Async with unbounded concurrency.** `asyncio.gather` over every probe. Fast at one probe; tail-latency blowup at 30. Doesn't model `production/design.md §3.1`'s "bounded worker pool."
- **Async from day one, `Semaphore(min(cpu_count, 8))`, one probe in Phase 0 (`[P]`+`[S]`, adopted by synth).** Same code path Phase 0 dispatches one probe through, Phase 1 dispatches six, Phase 2 dispatches ~30. The interface freezes at Phase 0 close; only the probe set grows.
- **Thread pool.** `concurrent.futures.ThreadPoolExecutor`. Equivalent semantics for I/O-bound work; doesn't compose with `asyncio.create_subprocess_exec` (the subprocess allowlist's primitive — see [ADR-0012](0012-subprocess-allowlist-chokepoint.md)).

## Decision

**The Coordinator is async from day one. Bound by `asyncio.Semaphore(min(os.cpu_count() or 1, config.max_concurrent_probes, 8))`. One `asyncio.Task` per probe via `asyncio.create_task` + `asyncio.wait_for(probe.timeout_seconds)`. Hard kill at `1.5 × timeout_seconds` via `cancel()` + 100ms grace + SIGKILL on tracked subprocesses.** Phase 0 dispatches exactly one probe (`LanguageDetectionProbe`) through this path; Phase 1 dispatches six; Phase 2 dispatches ~30; Phase 14 dispatches incrementally. The interface — semaphore, per-probe task, per-probe timeout, failure isolation, `ProbeExecution = Ran | CacheHit | Skipped` output — is frozen at Phase 0 close.

## Tradeoffs

| Gain | Cost |
|---|---|
| The Phase 0 interface = the Phase 1 interface = the Phase 14 interface; later phases extend by adding probes, not by replacing the dispatcher | The Phase 0 implementation carries machinery (semaphore, task tracking, timeout cancellation) that is not exercised by 1 probe |
| `production/design.md §3.1`'s "bounded worker pool" is honored from day one — no rewrite when load arrives | Async code is harder to reason about than sync code; new contributors pay an entry cost |
| Phase 14's incremental-gather model inherits the coordinator unchanged; `ProbeExecution = Ran \| CacheHit \| Skipped` is the cache-hit pass-through it needs ([ADR-0009](0009-cache-hit-pass-through-coordinator-output.md)) | Failure-isolation tests must cover the `cancel + grace + SIGKILL` path even though Phase 0 has no probe that exercises it |
| Subprocess cancellation composes correctly via `asyncio.create_subprocess_exec` — the same primitive `exec.run_allowlisted` uses ([ADR-0012](0012-subprocess-allowlist-chokepoint.md)) | The 1.5× timeout grace window is a magic constant; calibration belongs to Phase 5 sandbox work |
| No "Phase 1 replaces the coordinator" diff — extension-by-addition (`production/design.md §2.5`) holds | The interface is frozen with one probe of evidence — open questions about resource budgets are punted to [Gap 3](../phase-arch-design.md) (per-probe RSS / artifact size, deferred to Phase 1+) |

## Consequences

- The Coordinator's public surface is `async def gather(snapshot, task, probes, config, cache, sanitizer) -> GatherResult`. `GatherResult` is the frozen dataclass `(outputs: dict[str, ProbeOutput], executions: dict[str, ProbeExecution])`. Phase 1 adds probes; the function signature does not change.
- Probe exceptions are caught into `ProbeOutput(errors=[...], confidence="low")`; the coordinator never re-raises. CLI exit policy lives in `cli.py` consuming the `GatherResult`: 0 if ≥1 probe succeeded; 2 if all failed.
- The `Semaphore(min(cpu_count(), 8))` cap is the same one in `production/design.md §3.1`. The `8` ceiling exists because beyond it, `os.scandir` contention dominates and IO scheduling falls over.
- The `_ProbeOutputValidator → OutputSanitizer.scrub` pipeline lives **inside** the coordinator, post-probe-run, pre-cache-put. The coordinator is where the trust boundary is enforced ([ADR-0008](0008-output-sanitizer-two-pass-chokepoint.md), [ADR-0009](0009-cache-hit-pass-through-coordinator-output.md)).
- `tests/unit/test_coordinator_*.py` cover the dispatch path, the timeout-cancel path, and the failure-isolation path — even though Phase 0 has one probe, the tests pin the interface.

## Reversibility

**High.** Reverting to a serial coordinator requires reverting the async signatures across the call graph (CLI → coordinator → cache → probes), the test surface, and every consumer that depends on `asyncio` semantics (Phase 1's six probes, Phase 14's incremental gather). Phase 0 is the only window where the cost is small; after Phase 1 ships six probes against this interface, the cost compounds.

## Evidence / sources

- `../final-design.md §1` (Architecture diagram — "Coordinator (asyncio)")
- `../final-design.md §2.6` (Coordinator component design)
- `../final-design.md §L3 row 5` (Conflict resolution: async-day-one wins 11 vs serial's 3)
- `../critique.md §3.1.1` (Critic's rejection of serial-as-scoping)
- `../phase-arch-design.md §Component design / Coordinator`
- `../../../localv2.md §12` Week 1 ("asyncio, bounded worker pool")
- [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md) — continuous-gather depends on this interface unchanged
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — the contract lift relies on dispatcher stability
