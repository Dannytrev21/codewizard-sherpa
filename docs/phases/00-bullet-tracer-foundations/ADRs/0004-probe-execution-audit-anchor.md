# ADR-0004: Per-probe audit anchor — `cache_key` + `blob_sha256` in `ProbeExecutionRecord`

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** audit · provenance · cross-phase · cost-attribution
**Related:** [ADR-0001](0001-cache-content-hash-algorithm.md), [ADR-0003](0003-two-level-cache-key-schema-versioning.md), [production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md), [production ADR-0027](../../../production/adrs/0027-cost-attribution-model.md)

## Context

`../final-design.md §2.12` defines a `RunRecord` audit artifact at `.codegenie/runs/<utc-iso>-<short>.json` with a `yaml_sha256` field — the SHA-256 of the final `repo-context.yaml` — as the audit anchor.

`../phase-arch-design.md §Gap analysis Gap 2` flags the problem: the `yaml_sha256` is a *whole-gather* anchor. Phase 11's PR provenance bundle references *individual* probe evidence (a `NodeManifestProbe` output cited in a vuln-remediation PR), and Phase 13's cost-ledger attribution per [production ADR-0027](../../../production/adrs/0027-cost-attribution-model.md) attributes spend to *a probe execution*, not the whole YAML. Neither consumer is served by the whole-artifact anchor alone.

The synthesis names two downstream consumers (Phase 11, Phase 13) and provides a third party's anchor. The seam needs to land in Phase 0 — both phases inherit the record format and changing it later is a coordinated migration across the audit-writer, cost ledger, and PR provenance layers.

## Options considered

- **Whole-YAML anchor only (the synthesis as written).** `yaml_sha256` on `RunRecord` and nothing per-probe. Phase 11 and Phase 13 reconstruct per-probe anchors from the cache layer separately. Two consumers, two re-derivations, two opportunities for drift.
- **Per-probe `cache_key` only.** Add `cache_key: str` to `ProbeExecutionRecord`. Phase 13 attributes spend correctly; Phase 11 still has to verify evidence-blob integrity by some other means.
- **Per-probe `cache_key` + `blob_sha256` (synth gap-fix).** Both fields on `ProbeExecutionRecord`. `cache_key` is the SHA-256 identity tuple (over inputs); `blob_sha256` is SHA-256 of the sanitized output blob bytes. Phase 13 has its attribution anchor; Phase 11 has its evidence-integrity anchor; both come for free from the same write.
- **Per-probe `blob_blake3` (consistent with BLAKE3 elsewhere).** Use BLAKE3 for the blob hash too. Saves one algorithm in the audit record. Breaks `../../../localv2.md §8`-compatibility for the audit anchor and complicates cross-tool verification — many audit tools speak SHA-256 by default.

## Decision

**`ProbeExecutionRecord` includes both `cache_key: str` (the SHA-256 identity tuple from [ADR-0001](0001-cache-content-hash-algorithm.md)) and `blob_sha256: str` (SHA-256 of the sanitized blob bytes, distinct from the BLAKE3 input-content hash).** The `codegenie audit verify` subcommand walks every run-record, re-reads every claimed `cache_key`'s blob, recomputes `blob_sha256`, and reports mismatches. A unit test `test_audit_anchors.py` asserts both fields are populated and `blob_sha256` matches a recomputation.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 13's cost ledger attributes spend to `cache_key` directly — no re-derivation, no drift between audit and ledger | Two anchors per probe instead of one; ~ 130 extra bytes per probe execution record |
| Phase 11's PR-provenance bundle uses `blob_sha256` to verify cited evidence — integrity guarantee without recomputing input hashes | Two SHA-256 computes per probe per run (cheap; sub-millisecond at Phase 0 scale) |
| The whole-YAML `yaml_sha256` anchor is preserved for envelope-level verification — three layers of integrity (envelope / per-probe / cache key) | The audit record schema grows; Phase 1+ probes must ship both fields |
| `codegenie audit verify` becomes a structural verification of the entire gather lineage, not just the YAML manifest | Verification cost grows linearly with probe count (still under 100ms for Phase 2's expected ~30 probes) |
| Cross-phase consumers (Phase 11, Phase 13, Phase 14) inherit the anchor structure for free — no Phase-N migration | Once consumers depend on these field names, they're frozen for the project lifetime (mitigated: `ProbeExecutionRecord` is a Pydantic model with clear semantics) |

## Consequences

- `src/codegenie/audit.py` ships `ProbeExecutionRecord` with `name`, `version`, `cache_hit`, `wall_clock_ms`, `exit_status`, **`cache_key`**, **`blob_sha256`**. The two new fields are not "nice to have"; they are the cross-phase contract anchors.
- The `AuditWriter` reads `cache_key` from the Coordinator's `ProbeExecution = Ran(output) | CacheHit(output, key) | Skipped(reason)` shape — `Ran` carries the key implicitly via the cache write path; `CacheHit` carries it explicitly.
- `blob_sha256` is computed over the **sanitized** blob (post `OutputSanitizer.scrub`). The path-scrubbed, field-name-filtered representation is what's hashable — anything else makes audit recomputation depend on the original probe output, which the system has by design discarded.
- The `codegenie audit verify` subcommand becomes a Phase 0 deliverable (exit criterion #12) and a permanent operational tool — Phase 11's PR-provenance verification and Phase 13's cost-ledger reconciliation are both layered on top of this command.
- The fields are populated for **both** `Ran` and `CacheHit` executions. A `CacheHit` audit entry still records `cache_key` (the same one the cached blob is keyed by) and `blob_sha256` (which must match the recomputation — the cache verifies its own contents).
- `Skipped` executions populate `cache_key` as the would-be key plus `blob_sha256` as the empty-string sentinel; `exit_status="skipped"` distinguishes.

## Reversibility

**Medium.** Removing the fields is mechanically cheap (delete from the dataclass; update `AuditWriter`) but breaks every downstream consumer that depends on them. By the time Phase 13 ships, both fields are load-bearing for cost attribution — removal would require re-deriving the anchors from cache state, which only works for cache entries that haven't been GC'd. The longer the system runs, the harder removal gets. Plan to live with the fields.

## Evidence / sources

- `../phase-arch-design.md §Gap analysis Gap 2` (Identifies the under-specification and the two-anchor fix)
- `../phase-arch-design.md §Component design / Audit writer` (`ProbeExecutionRecord` shape)
- `../final-design.md §2.12` (Original audit record — anchored only at YAML level)
- `../final-design.md §11 exit criterion #12` (`codegenie audit verify` smoke run)
- [production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md) — cost-observability commitment this anchor serves
- [production ADR-0027](../../../production/adrs/0027-cost-attribution-model.md) — cost attribution model the cache_key feeds into
