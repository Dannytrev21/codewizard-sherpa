# ADR-0010: Phase 3 extends the Phase 2 BLAKE3 audit chain with new event types; cache hits emit `cache.replay` referencing the original chain head

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** audit · chain · cache-replay · phase-2-extension · tamper-evidence
**Related:** [Phase 2 ADR-0012](../../02-context-gather-layers-b-g/ADRs/0012-audit-chain-blake3-rolling-head.md), [Phase 0 ADR-0004](../../00-bullet-tracer-foundations/ADRs/0004-audit-anchor-on-every-gather.md), ADR-0005, ADR-0006, ADR-0007, ADR-0008, ADR-0009

## Context

Phase 0 ADR-0004 established the audit anchor on every gather; Phase 2 ADR-0012 extended it with a rolling BLAKE3 chain head (chain breaks are observability, not gather failure). Phase 3 adds new operations — recipe selection, engine invocation, lockfile scanning, validator runs, branch creation, escalation signals, CVE retraction marking — each of which is integrity-relevant and needs tamper-evidence.

Two questions surfaced:

1. **Which new event types?** Each design had a partial list; the synth consolidates a complete event vocabulary (`final-design.md §"Trust & safety goals"` #15).
2. **What happens on cache hit?** Performance-first's `LockfileResolver` cache (ADR-0006's transient-retry-internal wrapper) serves results from prior runs. The critic flagged that performance-first's design "writes `metadata.json` per attempt with no chained-audit semantics — meaning the cache-hit short-circuit on attempt-id has no audit story for the original attempt's evidence" (`critique.md §"Attacks on performance-first" §"Things this design missed"`). Security-first extends the chain but is silent on cache-hit semantics. The synth answer: cache hits replay the original chain reference (`final-design.md §"Trust & safety goals"` #15: "Cache hits replay the original event chain (the original BLAKE3 hash is included in the cache key; serving from cache re-emits a `cache.replay` event referencing the original chain head)").

## Options considered

- **Per-run unchained `audit.json` [B].** Loses cross-run tamper-evidence; cache hits have no audit story.
- **Extend Phase 2 BLAKE3 chain with new event types; cache hits are silent (no event) [naive].** Cache-hit short-circuit produces no audit trace — operators cannot tell whether a run was fully executed or served from cache.
- **Extend Phase 2 chain; cache hits emit a generic `cache.hit` event with no back-reference [partial].** Operator sees the hit but cannot trace back to the original run's evidence.
- **Extend Phase 2 chain; cache hits emit `cache.replay` event referencing the **original** run's chain head (the BLAKE3 hash that was the chain head when the cache entry was written) [synth].** Operator can navigate from any cache-served result back to the original evidence.

## Decision

**Phase 3 extends the Phase 2 BLAKE3 audit chain (Phase 2 ADR-0012) additively. Two extensions:**

### 1. New Phase-3 event types

Added to the audit event vocabulary; each event is appended to the chain with the rolling BLAKE3 head:

| Event | Trigger | Key payload fields |
|---|---|---|
| `cve.feed.synced` | `codegenie cve sync` per source | `source, snapshot_hash, prior_snapshot_hash, synced_at` |
| `cve.feed.signature_check` | best-effort GPG/commit-signature verify (ADR-0008) | `source, signature_status, key_id` |
| `cve.retraction.detected` | `CveRetractionProbe` finds a withdrawn record (ADR-0009) | `cve_id, source, prior_snapshot_hash, new_snapshot_hash, affected_runs` |
| `evidence_stale.marked` | appended to a prior run's chain when retraction marks it stale (ADR-0009) | `cve_id, reason` |
| `recipe.selected` | selector emits `RecipeSelection` | `recipe_id?, reason, diagnostics` |
| `recipe.engine.invoked` | `RecipeEngine.apply` start/end | `engine, recipe_id, exit_code, duration_ms` |
| `transform.applied` | `Transform.run()` completes | `transform, diff_path, files_changed, confidence` |
| `lockfile.scanned` | `LockfilePolicyScanner.scan` completes (ADR-0007) | `violations, allowed_overrides` |
| `npm.install.run` | `LockfileResolver` subprocess invocation | `attempts, exit_code, duration_ms, transient_retry: bool` |
| `tests.executed` | test validator (ADR-0005) | `exit_code, duration_ms, requires_network: bool` |
| `gate.failed` | any validator emits `passed=False` | `gate, signals` |
| `gate.signal_escalate` | network-required test signature (ADR-0005) | `signal_pattern, suggested_flag` |
| `escalation.policy_violation` | exit 7 path (ADR-0007) | `violation_types, allowed_overrides` |
| `branch.created` | `PatchBranchWriter` finalizes | `branch_name, head_sha` |
| `cache.replay` | cache-served result | `cache_key, original_chain_head_blake3, original_run_id` |

The list is **closed at v0.3.0**; adding a new event type requires an ADR amendment.

### 2. Cache-replay semantics

The lockfile-resolver cache (ADR-0006's transient-I/O internal wrapper; cache key per `final-design.md §"Components" #5`) includes the **original chain head BLAKE3 hash** in the cached entry alongside the lockfile bytes:

```yaml
cache_entry:
  cache_key: "<blake3>"
  lockfile_bytes: <bytes>
  original_chain_head_blake3: "<blake3>"   # chain head at time of original write
  original_run_id: "<run_id>"
```

When a subsequent run gets a cache hit, the orchestrator:

1. Reads the cached `original_chain_head_blake3` and `original_run_id`.
2. Emits `cache.replay` event with both fields plus the current run's `cache_key`.
3. The current run's chain advances per Phase 2 ADR-0012 (the new event is hashed into the rolling head).
4. Forensic readers can navigate from a `cache.replay` event back to the original run's full chain (the audit log directory contains the original `runs/<utc>-<short>.json`).

This gives every cache-served result a back-reference to the evidence that produced it, **without** re-emitting the original probe / engine events in the new run's chain.

## Tradeoffs

| Gain | Cost |
|---|---|
| Closed event vocabulary at v0.3.0 — readers (Phase 5 gates, Phase 11 PR notifier, future audit dashboards) can decode any event type with a single schema | Adding a new event type requires an ADR amendment; the closed-enum discipline is a coordination tax |
| Cache hits emit `cache.replay` with back-reference — forensic readers can trace any cache-served result to its origin run | Cache entries grow by 32 bytes (`original_chain_head_blake3`) + `run_id` (~36 bytes) per entry; immaterial |
| `evidence_stale.marked` writes into *prior* runs' chains (ADR-0009) — the BLAKE3 chain head of an old run legitimately advances; tamper-evidence is preserved on the marker itself | Prior-run chain mutation is a structural feature of the design; documented loudly; the chain-verification helper must understand the advance |
| Phase 2 ADR-0012's "chain breaks are observability, not failure" stance carries forward — Phase 3 doesn't tighten enforcement | A malicious actor with write access to `.codegenie/remediation/*/audit/` can still tamper; Phase 14 transparency-log is the load-bearing fix |
| `gate.signal_escalate`, `escalation.policy_violation` events make operator decisions structurally visible to Phase 5/11 routers | Phase 5/11 must consume the events; consumer contracts are flagged for their phase ADRs |
| The cache-key already includes content hashes (lockfile, package.json, npm digest, registry mirror digest) per ADR-0006; chain-head field is additive | Cache invalidation on `npm` minor bump produces a portfolio-wide cache rebuild; pre-warmed on the bump PR; documented in ADR-0006 |

## Consequences

- `src/codegenie/audit/writer.py` extends with the Phase 3 event types (Pydantic discriminated union or schema).
- `src/codegenie/audit/schema.json` (or equivalent) defines the new event types as a closed enum.
- `src/codegenie/cache/` (extended) — lockfile cache entries include `original_chain_head_blake3` and `original_run_id`.
- `src/codegenie/transforms/coordinator.py` emits the events at each stage transition; `LockfileResolver.run()` emits `cache.replay` on cache hit.
- `src/codegenie/audit/chain_verify.py` (Phase 2 helper) extended to recognize cross-run `evidence_stale.marked` events as legitimate chain advances.
- `tests/adv/test_audit_chain_break_observability_phase3.py` (Phase 2 carry-over plus Phase 3 events).
- `tests/unit/test_cache_replay_back_reference.py` asserts cache hits emit the event and the original chain head is preserved.
- `tests/unit/test_audit_event_schema_validates_or_drops.py` property test asserts all 15 event types validate.
- Phase 14's transparency log replaces the rolling-BLAKE3 mechanism without changing the event vocabulary.
- Phase 5/11 ADRs document how they consume `gate.signal_escalate`, `escalation.policy_violation`, `gate.failed`.

## Reversibility

**Medium for event types; Low for cache-replay shape.** Adding new event types is mechanically additive but requires an ADR amendment per the closed-enum discipline. Removing event types breaks downstream consumers (Phase 5 gate retry logic; Phase 11 notifier). The cache-replay back-reference shape is high-value forensic context — removing it would compromise post-incident investigation; high cost to reverse. The `evidence_stale.marked`-on-prior-runs pattern is the most structurally novel piece; reversing it (e.g., marking on the *current* run instead) would break the back-reference property and require Phase 4 RAG to re-derive staleness — high cost.

## Evidence / sources

- `../final-design.md §"Goals" §"Trust & safety goals"` #15 — event vocabulary and cache-replay
- `../final-design.md §"Components" #5 "LockfileResolver"` (cache-hit replay)
- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Audit chain on cache hit"
- `../phase-arch-design.md §"Component design" #14 "Audit chain — Phase-3 event extensions"`
- `../phase-arch-design.md §"Data model" §"Audit event payload extensions (Phase 3)"`
- `../critique.md §"Attacks on performance-first" §"Things this design missed"` — audit chain extension
- `../critique.md §"Attacks on best-practices" §"Things this design missed"` — audit/chain semantics
- [Phase 2 ADR-0012](../../02-context-gather-layers-b-g/ADRs/0012-audit-chain-blake3-rolling-head.md) — rolling BLAKE3 chain head
- [Phase 0 ADR-0004](../../00-bullet-tracer-foundations/ADRs/0004-audit-anchor-on-every-gather.md) — audit anchor
