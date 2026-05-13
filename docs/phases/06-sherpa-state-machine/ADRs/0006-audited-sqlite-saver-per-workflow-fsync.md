# ADR-0006: Per-workflow SQLite checkpointer with fsync at every node boundary

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** durability · checkpointer · concurrency
**Related:** [ADR-0007](0007-blake3-chain-extension-and-tamper-evidence.md), [ADR-0011](0011-sqlite-throughput-watch-and-postgres-escalation.md), [production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md)

## Context

The exit criterion for Phase 6 is *"Mid-run kill + resume works without state loss"* (`roadmap.md §Phase 6 Exit criteria`). The three lenses landed in three different places on what "without state loss" means and how to ship it:

- **Performance** shipped a queued / background-flush checkpointer that "returns when queued, not when persisted," buying ~6× throughput headroom. `critique.md performance.2` killed it: a 50 ms durability gap is state loss the moment the in-flight node has visible side effects — and the Phase 5 audit chain has *already* been extended in that window, so the next resume sees a `prev_chain_head` mismatch and aborts. The exit criterion forbids state loss, full stop.
- **Performance** also shipped a **single shared SQLite DB** (`.codegenie/loop/checkpoints.sqlite`); best-practices the same; **security** picked a **per-workflow file** (`.codegenie/checkpointer/<workflow-id>.db`). Single-shared-DB creates write contention across concurrent workflows under SQLite's single-writer model; per-workflow files eliminate the contention but multiply the file count.
- All three lenses **defer Postgres** to Phase 9 (`final-design.md §Shared blind spots #1`) — without any of them measuring whether SQLite is even adequate.

`final-design.md §Synthesis ledger rows 4 and 5` resolved the conflict: fsync at every node boundary (no background queue), per-workflow file (security's pick). The measurement deferral is separately addressed by ADR-0011's throughput-watch gate.

## Options considered

- **Single shared SQLite DB + queued flush.** Performance's original. Highest throughput; loses state on kill; contends across concurrent workflows. Rejected on correctness grounds.
- **Single shared SQLite DB + fsync per boundary.** Durable; contends across concurrent workflows because SQLite is single-writer per file.
- **Per-workflow SQLite file + queued flush.** No contention; loses state on kill. Rejected on correctness grounds.
- **Per-workflow SQLite file + fsync per boundary.** No contention; durable; throughput is whatever WAL + NORMAL fsync delivers (measured by ADR-0011).

## Decision

The checkpointer is `AuditedSqliteSaver` (subclass of LangGraph's `AsyncSqliteSaver`) at path `.codegenie/loop/checkpoints/<workflow_id>.sqlite3`. Configuration: `WAL=on, synchronous=NORMAL, file mode 0600`. **Every node-boundary checkpoint is durably persisted (WAL frame + `wal_checkpoint(PASSIVE)`) before LangGraph proceeds to the next node.** No background queue. No delta-encoded writes. `workflow_id` is the 16-char BLAKE3 digest of `repo_root_blake3 || advisory_canonical_id`, so the same advisory + same repo HEAD content-addresses to the same checkpoint file and the resume path is deterministic.

## Tradeoffs

| Gain | Cost |
|---|---|
| Exit-criterion durability is preserved — kill at any node boundary leaves the last fsync'd frame intact and the in-flight node simply re-runs | Throughput is whatever SQLite delivers with WAL+NORMAL; we do not promise 800 writes/s — ADR-0011 measures it |
| No write contention between concurrent workflows — Phase 9's Temporal worker can run N workflows in parallel against N separate `.sqlite3` files | One file per workflow grows the file count on disk; cleanup tooling becomes Phase 7+'s concern |
| The BLAKE3 audit chain never extends ahead of a fsync'd checkpoint — `prev_chain_head` is always consistent on resume | aiosqlite's per-process event-loop overhead may dominate at high concurrency — flagged by the design's Gap 3, addressed by a future concurrent-throughput test |
| The `0600` file mode lock at startup catches world-readable checkpoints loudly — local trust posture is enforceable | Operators on shared dev hosts who `chmod` for convenience get a `CheckpointerInsecure` raise — recovery is a one-line `chmod 600`, but it's friction |
| `<workflow_id>` content-addressing means re-invoking with the same inputs always resumes the same workflow — no manual `--thread-id` flag | If an operator wants two independent runs of the same `(repo, cve)` pair, they must override the workflow ID; the design does not yet expose a clean override |

## Consequences

- The checkpointer is exposed via a factory `make_checkpointer(workflow_id, *, base) -> AuditedSqliteSaver` so Phase 9 can swap to `AuditedPostgresSaver` in one place (`phase-arch-design.md §Integration with Phases 8–9`).
- The fsync-per-boundary policy directly drives ADR-0011's throughput watch — if SQLite can't hit ≥ 100 writes/s on CI hardware with this configuration, the Postgres migration pulls forward.
- `tests/integration/test_replay_after_kill.py` SIGKILLs during `validate_in_sandbox` (the longest node) and asserts byte-identical final state; `tests/adversarial/test_world_readable_checkpoint_refused.py` enforces the `0600` posture.
- The `<workflow_id>`-keyed file means `codegenie loop inspect` and `codegenie loop replay` take a `thread_id` and find the right DB without a global registry.
- `langgraph-cli` is documented as point-at-a-specific-file (one workflow at a time) — `final-design.md §Goal 10`.
- The same-process write to the audit chain file (`AuditedSqliteSaver.put` → audit chain append) requires a shared `threading.Lock` because Phase 5's `RetryLedger.record` also appends to the same chain file (Phase 6 design's Open Question #4); `test_chain_single_writer.py` is the canary.

## Reversibility

**Medium.** Switching to a shared DB is mechanical (change the path scheme) but the contention argument rises immediately and the per-workflow audit-chain alignment breaks down — non-trivial cleanup. Switching to a queued flush is also mechanical but reintroduces the exit-criterion violation; would force amending the roadmap. Switching to Postgres (via `make_checkpointer`) is the explicit forward path; ADR-0011's gate is what triggers it.

## Evidence / sources

- [`../final-design.md` §Synthesis ledger rows 4 + 5](../final-design.md)
- [`../final-design.md` §Component 3 "AuditedSqliteSaver"](../final-design.md)
- [`../phase-arch-design.md` §Component 3 "AuditedSqliteSaver"](../phase-arch-design.md)
- [`../phase-arch-design.md` §Process view](../phase-arch-design.md)
- [`../critique.md` §performance.2](../critique.md) — the 50 ms durability-gap argument
- [Production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md) — Postgres-vs-Redis deferral
