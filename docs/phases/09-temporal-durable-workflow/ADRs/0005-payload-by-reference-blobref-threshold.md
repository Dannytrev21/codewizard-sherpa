# ADR-0005: Payload-by-reference via `BlobRef` for activity payloads > 8 KiB

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** smart-constructor · content-addressing · history-compactness
**Related:** [ADR-0008](0008-typed-credential-blocklist-not-regex.md), [ADR-0012](0012-event-store-topology-temporal-history-plus-postgres-events.md)

## Context

Temporal workflow history records every activity input and return value byte-by-byte. The Phase-8 `ContextBundle` is 50–150 KiB; a Phase-3 `patch_diff` can be larger; a sandbox log is bigger still. If those crossed the activity boundary as inline payloads, per-workflow history would inflate from ~14 records to many thousands of kilobytes; `temporal-ui` would become illegible; replay would re-read megabytes; and storage costs would scale with payload size rather than event count. The G8 exit criterion is "≤ 30 events nominally / ≤ 200 worst-case per workflow", which inline-payload growth would silently violate.

A reference-by-digest discipline keeps history compact, deduplicates content-addressable bytes (identical bundles share one blob row), and creates a single audit point for "what was that exact payload?" without bloating workflow history.

## Options considered

- **Inline everything.** All activity inputs/outputs are full Pydantic models with their bytes. **Pattern:** none — naive simplicity. Wastes history; loses content-addressing dedup.
- **Reference-everything via S3/MinIO.** Every payload over 1 KiB goes to object storage; activity inputs are presigned URLs. **Pattern:** external blob store. Adds an infrastructure dependency; complicates dev-up.
- **Postgres `events.blob_refs` table, content-addressed by BLAKE3 digest, 8 KiB threshold, smart constructor.** Payloads > 8 KiB are written to `events.blob_refs` (`digest BYTEA PRIMARY KEY, content BYTEA, content_kind TEXT, byte_len BIGINT`) via the `write_blob_ref` Activity; the resulting `BlobRef(digest, content_kind, byte_len)` crosses the workflow boundary. `BlobRef` is constructed *only* by `write_blob_ref` (smart-constructor pattern). **Pattern:** content-addressed blob store, smart constructor.

## Decision

Activity payloads > 8 KiB ride `BlobRef(digest, content_kind, byte_len)`; bytes live in `events.blob_refs` keyed by BLAKE3 digest with `ON CONFLICT DO NOTHING` (content-addressed dedup); the `BlobRef` smart constructor lives in `write_blob_ref` and is the only legal path to producing one. **Pattern: smart constructor + content-addressed blob store, no separate infrastructure.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Workflow history stays ~2 KiB per activity invocation (just the `BlobRef` envelope) | Two extra activities per workflow on average (`write_blob_ref`, `resolve_blob_ref`) — ~10 ms wall-clock |
| Content-addressed dedup — identical bundles share one blob row across all workflows | Postgres carries blob bytes (not S3) — ~150 MiB/day storage at 1k workflows/day |
| `BlobRef` smart constructor makes "did you remember to put bytes in the store?" a compile-time check (the only way to get a `BlobRef` is from `write_blob_ref`) | Threshold (8 KiB) is a magic number; some payloads at 7.9 KiB would benefit from refs and won't get them |
| `temporal-ui` shows compact history; engineers can inspect a workflow run at a glance | Looking at the actual payload requires a separate `resolve_blob_ref` call (`make blob-show DIGEST=...` ergonomic) |
| No new infrastructure component — Postgres is already there | Postgres becomes the de-facto blob store for Phase 9; if blob growth exceeds expectations, must migrate to S3 in Phase 16 |
| Digest mismatch on read is detectable (`BlobDigestMismatchError`) — tamper-evident at the bytes level | Per-worker LRU cache adds memory pressure (~16 MiB at typical fill) |

## Pattern fit

Smart-constructor pattern (toolkit `design-patterns-toolkit.md §Construction-as-validation`) makes "this value cannot exist unless it's been validated" a type-level guarantee. `BlobRef` cannot be constructed except by `write_blob_ref`, which means a `BlobRef` in workflow history is by construction a reference to bytes that exist in `events.blob_refs`. Content-addressing (Git, Nix, IPFS) is the canonical pattern when "the data is the name": identical bytes produce identical digests produce identical primary keys produce automatic dedup. The 8 KiB threshold matches Temporal's own recommendation (`https://docs.temporal.io/workflows#payload-size`) for staying well under the per-activity 2 MiB hard cap.

## Consequences

- `events.blob_refs` schema lives in `src/codegenie/events/alembic/versions/0001_create_events_schema.py`.
- `BlobRef` is a frozen Pydantic model with `extra="forbid"`; the smart constructor lives only in `write_blob_ref`.
- `BlobKind` is a sum type (`ContextBundle | RepoSnapshotDelta | SandboxLog | PatchDiff | EvidenceBundle`) — additive, additions live in [`codegenie.events.blob_refs.payloads`](../phase-arch-design.md#c6--payload-by-reference-codegenievntsblob_refs).
- Activities choosing to inline a < 8 KiB payload do so by *not* calling `write_blob_ref` — no enforcement at the boundary.
- Cache: per-worker `BlobRef` LRU avoids round-tripping bytes when one activity reads what a prior activity in the same worker process wrote.
- Phase 11 / Phase 13 projections fold `BlobRef` references without re-reading bytes; only the audit-trail projection optionally resolves them.
- Storage growth: ~220 MiB/day at 1k workflows/day per [`../final-design.md §Resource & cost profile`](../final-design.md). Annual: ~80 GiB. Within Postgres comfort range.
- If blob storage outgrows Postgres comfort (~Phase 16), a new `BlobStoreAdapter` Protocol can swap to S3 additively — `BlobRef` shape is stable.

## Reversibility

**Medium.** Lowering the threshold is a one-line config change; raising it requires migrating existing references (impractical — they live in workflow history). Swapping the blob substrate to S3 requires an Adapter swap but `BlobRef` shape is unchanged, so workflow histories remain valid.

## Evidence / sources

- [`../phase-arch-design.md §C6 — Payload-by-reference`](../phase-arch-design.md#c6--payload-by-reference-codegenievntsblob_refs)
- [`../phase-arch-design.md §Data model — Postgres schema`](../phase-arch-design.md#postgres-schema-internal)
- [`../phase-arch-design.md §Goals G8 — Workflow-history compactness`](../phase-arch-design.md#goals)
- [`../final-design.md §7 Payload-by-reference`](../final-design.md)
- Temporal docs: *Workflow Payload Size* — `https://docs.temporal.io/workflows#payload-size`
