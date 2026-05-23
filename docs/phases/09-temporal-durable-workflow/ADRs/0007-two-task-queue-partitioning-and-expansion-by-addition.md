# ADR-0007: Two-task-queue partitioning in Phase 9; expansion by addition

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** isolation · blast-radius · expansion-by-addition · workers
**Related:** [ADR-0008](0008-typed-credential-blocklist-not-regex.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

The activity catalog has nine activities with very different trust and resource profiles: some hold credentials and call GitHub (`github_open_pr`), some run untrusted code in microVMs (`sandbox_build_and_test`), some are pure typed-IO with Postgres (`emit_event`, `write_blob_ref`, `resolve_blob_ref`). Running them on one shared worker pool means a compromise of one worker exposes every credential and every action surface; a resource-heavy activity (`run_vuln_subgraph`'s 1.5 GiB sandbox) competes with cheap ones for the same memory budget.

Temporal partitions work by **task queue**: workers register for specific queues and a workflow dispatches each activity to its declared queue. Task queue identity is also the natural granule for K8s ServiceAccount scoping. The performance-first design [P] proposed four task queues by workload class; the best-practices design [B] proposed two; the security-first design [S] proposed one queue per credential class. The decision must serve both Phase 9's actual needs (two task classes: repo-side activities + system activities) and Phase 10/7.5's growth path (per-language task queues).

## Options considered

- **One queue: `default`.** Every activity runs on every worker. **Pattern:** uniform pool. Blast radius is everything-on-fire.
- **N × M sprawl (N task classes × M language ecosystems × P credential classes).** Maximum isolation. **Pattern:** fine-grained partitioning. Operational overhead grows multiplicatively; YAGNI for Phase 9's actual workload.
- **Two queues, expansion by addition.** Phase 9 ships `vuln-remediation-node-npm` (repo-shaped side-effects) and `system` (event-log + blob-refs). Phase 7.5 adds `vuln-remediation-python-pip` additively. Phase 10 may add `assessment-*` queues additively. **Pattern:** start narrow, expand by addition.

## Decision

Phase 9 ships exactly two task queues: `vuln-remediation-node-npm` (six activities: `resolve_plugin`, `build_bundle`, `route`, `run_vuln_subgraph`, `sandbox_build_and_test`, `github_open_pr`) and `system` (three activities: `emit_event`, `resolve_blob_ref`, `write_blob_ref`). New task classes and languages add new task queues without editing existing ones. **Pattern: start narrow, expansion by addition.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Blast radius of a compromised worker is one queue's allowlist — not everything | Two pools to run, monitor, scale; two K8s ServiceAccounts to maintain |
| `system` queue's narrow event-log+blob writers can scale independently of `vuln-remediation-*` heavy workers | One extra gRPC round-trip when a `vuln-remediation-*` activity needs to write an event (`emit_event` is on the other queue) |
| Per-queue Capability allowlist (see [ADR-0008](0008-typed-credential-blocklist-not-regex.md)) is the trust root — no in-process HMAC ceremony needed | Workers in different K8s pods need their own ServiceAccount mounts |
| Phase 7.5 (Python) and Phase 10 (Assessment) add queues additively — no edit to Phase-9 code | Task-queue catalog grows over time; operational catalog must stay legible |
| `vuln-remediation-node-npm` name encodes both task class and language — Phase 7.5's `vuln-remediation-python-pip` is the obvious additive neighbor | Naming convention is convention, not contract — `tests/fence/test_task_queue_naming.py` enforces the `{task-class}-{language}-{package-manager}` shape (or `system` for the system queue) |

## Pattern fit

Expansion by addition (production ADR-0043) is the codebase-wide stance: new capabilities = new files + new registry rows; never edits to existing entities. Task queues are a registry over which workers run which activities; adding a new task class is a new queue, a new worker process, a new ServiceAccount. The toolkit calls out "start with the minimum set that exercises both the typed seam and the operational seam" — two queues exercise both (the system/repo seam is a real boundary in the activity catalog; one queue would not exercise the multi-queue dispatch code path that Phase 7.5/10 needs working).

## Consequences

- `codegenie.durable.workers.build_worker(kind=WorkerKind.VULN_REMEDIATION_NODE_NPM | WorkerKind.SYSTEM)` is the entry point.
- Each activity declares its task queue via `@register_activity(name=..., task_queue=...)`; lookup is a one-line registry read.
- Capability minting at worker startup reads the K8s ServiceAccount mount `/var/run/secrets/codegenie/queue-identity` to determine which Capability types this worker may mint. See [ADR-0008](0008-typed-credential-blocklist-not-regex.md).
- A worker on `vuln-remediation-node-npm` cannot mint an `EventLogWriteCapability` for kinds outside its allowlist; cannot mint a `PrOpenCapability` for repos outside the active workflow's allowlist. Verified by `tests/adv/test_capability_token_scope.py` and `tests/adv/test_worker_credential_blast_radius.py` (G9 exit criterion).
- Phase 7.5's `vuln-remediation-python-pip` queue is one new `WorkerKind` enum value + one new K8s ServiceAccount + zero edits to existing activities.
- Phase 10 may add `assessment-*` queues by the same shape.
- Operational catalog of task queues lives in `docs/operations/task-queues.md` (created in Phase 9).

## Reversibility

**Medium.** Collapsing queues is easy (run both worker kinds on one pool); expanding to N-by-M sprawl is also easy (additive). The harder reversal is going *back* from N queues to one, which would require K8s ServiceAccount consolidation and Capability allowlist reshaping.

## Evidence / sources

- [`../phase-arch-design.md §C8 — Worker process model`](../phase-arch-design.md#c8--worker-process-model-codegeniedurableworkers)
- [`../phase-arch-design.md §Non-goals — N×M task-queue sprawl`](../phase-arch-design.md#non-goals)
- [`../phase-arch-design.md §Goals G9 — Per-task-queue credential blast radius`](../phase-arch-design.md#goals)
- [`../phase-arch-design.md §Integration with Phase 10 — Per-task-class worker pools`](../phase-arch-design.md#integration-with-phase-10-stage-0-discovery--stage-1-assessment)
- [`../final-design.md §Synthesis ledger — per-task-queue isolation strategy row`](../final-design.md)
- [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)
