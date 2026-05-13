# ADR-0011: SQLite throughput is **measured** in CI — < 100 writes/s pulls Phase 9 Postgres forward

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** performance · durability · phase9-trigger
**Related:** [ADR-0006](0006-audited-sqlite-saver-per-workflow-fsync.md), [production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md)

## Context

`final-design.md §Synthesis ledger §Shared blind spots #1` flagged that all three lens designs *defer Postgres without measuring SQLite throughput*:

- Performance budgets 800 writes/s/worker without measurement.
- Security defers throughput to Phase 9 entirely.
- Best-practices documents `database is locked` as a known limitation.

Phase 6's exit criterion ("Mid-run kill + resume works without state loss") forces fsync-per-node-boundary (ADR-0006). That choice trades throughput for durability — the question is *how much.* If SQLite under WAL + NORMAL fsync on CI hardware delivers, say, 30 writes/s, the Phase 9 Postgres migration is no longer "deferred until later" but "Phase 7-or-8 blocker." Deferring a load-bearing operational property to a future phase *without a measurement* is exactly the global-rule-§12 ("Fail loud") violation the synthesizer rejected.

The synthesis (`final-design.md §Goal 9`) commits to a measured throughput gate. This ADR formalizes the escalation path and the threshold.

## Options considered

- **Defer until Phase 9, no measurement.** Status quo across all three lenses. Risk that Phase 9's Postgres migration is forced under time pressure; no early warning.
- **Measure once in development, hard-code a "yes we're fine" assertion.** Passes the buck to whoever runs it next.
- **Measure in CI on every run, with a hard threshold that triggers an ADR amendment.** Catches the regression at PR-merge time, not at Phase-9 design time.

## Decision

`tests/perf/test_checkpoint_throughput.py` (nightly CI; `@pytest.mark.slow`) issues 1,000 serial checkpoints through a real `AuditedSqliteSaver(WAL=on, synchronous=NORMAL)` and records achieved throughput in `tests/perf/baseline.json`. **If achieved throughput is < 100 writes/s on CI hardware**, the test fails and ADR-P6-006 (recorded as Risk #3 in the design; same as this ADR's amendment trigger) fires: an ADR amendment story is opened to *pull Phase 9's Postgres migration forward to Phase 7 or 8*. The merge of any work that depends on Phase 6 ops at scale is blocked until the amendment lands. The 100 writes/s threshold is the floor below which fsync-per-boundary stops being viable for the projected Phase 9 workload (single workflow at ≥ 10 node transitions/s × 3 transitions per second of orchestration time × headroom).

A complementary multi-workflow concurrent test (`tests/perf/test_checkpoint_concurrent_throughput.py`, per the design's Gap 3) spawns N=10 `asyncio.Task`s, each driving a separate `AuditedSqliteSaver(<workflow_N>.sqlite3)` through 100 serial checkpoints, and measures aggregate throughput. Its threshold is set after the first CI run records the baseline — at least 10× the single-workflow throughput (per-workflow files should scale).

## Tradeoffs

| Gain | Cost |
|---|---|
| The Postgres-deferral assumption is **measured, not assumed** — Phase 9's plan has a concrete data point | The threshold (100 writes/s) is a synthesizer-picked floor; calibrating it requires the first CI run to establish reality |
| If SQLite is inadequate, the team knows at Phase 6 merge time, not Phase 9 design time — Phase 9's Postgres work pulls forward cleanly | CI runtime grows by the nightly perf test (~30 s); the test is marked `@pytest.mark.slow` to keep PR feedback fast |
| The concurrent-throughput test catches per-process aiosqlite event-loop overhead before Phase 9 hits it at production scale | Tuning the multi-workflow threshold is post-baseline work; the first run only records, doesn't assert |
| ADR-P6-006 (the amendment story) is named and ready — operators see a clear escalation path, not a "we'll figure it out" hand-wave | If the threshold fires *and* Postgres isn't ready, the team has to choose between weakening the durability commitment and slipping the phase — Phase 6 does not pre-resolve that conflict |

## Consequences

- `tests/perf/baseline.json` is the committed source of truth for measured throughput; PRs that re-tune the configuration (WAL settings, fsync mode) update the baseline as a deliberate step (`phase-arch-design.md §Performance regression tests`).
- The 100 writes/s floor is justified by Phase 9's projected workload of one workflow doing ~10 node transitions over ~100 s = 0.1 writes/s per workflow, scaled to N=100 concurrent workflows = 10 writes/s, with 10× headroom for spikes = 100 writes/s.
- A failing throughput test triggers the explicit ADR amendment story (`ADR-P6-006: SQLite throughput insufficient — escalate Postgres earlier`), which the Phase 9 design must consume.
- This ADR's threshold can be retuned with measurement evidence; the *mechanism* (CI-gated measurement → amendment trigger) is what's load-bearing.
- The concurrent-throughput test additionally guards against the silent failure mode where per-workflow files appear fine in isolation but contend at scale (Gap 3 in the design).

## Reversibility

**High.** The threshold is configuration. Removing the gate entirely is a one-line test deletion; doing so would reintroduce the shared blind spot the synthesizer explicitly rejected. Raising or lowering the floor is mechanical and should be evidence-driven. The escalation path (ADR amendment) is the durable commitment; the specific number is not.

## Evidence / sources

- [`../final-design.md` §Goals row 9 "SQLite throughput is measured"](../final-design.md)
- [`../final-design.md` §Synthesis ledger §Shared blind spots #1](../final-design.md)
- [`../final-design.md` §Risk 3](../final-design.md)
- [`../phase-arch-design.md` §Gap analysis Gap 3](../phase-arch-design.md) — concurrent-throughput addendum
- [`../phase-arch-design.md` §Performance regression tests](../phase-arch-design.md)
- [Production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md) — the deferred decision this ADR makes resolvable
- CLAUDE.md global rule §12 — "Fail loud" justifies measurement over assumption
