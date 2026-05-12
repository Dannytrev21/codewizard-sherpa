# ADR-0003: Two-level cache-key schema versioning — envelope vs per-probe

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** cache · schema · invalidation · scalability
**Related:** [ADR-0001](0001-cache-content-hash-algorithm.md), [ADR-0013](0013-layered-additional-properties-schema.md), [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

`../final-design.md §2.7` defines the cache key tuple as `SHA-256(probe_name | probe_version | schema_version | inputs_hash_hex)`. The synthesis stopped short of saying *what* `schema_version` refers to.

Phase 1 lands per-probe sub-schemas under `src/codegenie/schema/probes/<name>.schema.json`, composed by `$ref` into the envelope ([ADR-0013](0013-layered-additional-properties-schema.md)). Phase 14's continuous-gather model (production ADR-0006) re-hashes incremental probe inputs on every webhook trigger.

`../phase-arch-design.md §Gap analysis Gap 1` identifies the ambiguity: if `schema_version` in the cache key is the **envelope** version, then a single probe's sub-schema bump (e.g., `NodeManifestProbe` gains a `peer_dependencies` field, bumping `node_manifest.schema.json` from `v0.1.0` to `v0.2.0`) invalidates *every* probe's cache entries — not just `NodeManifestProbe`'s. Mass invalidation on every schema change defeats the incremental-gather story at Phase 14 portfolio scale.

The seam is set in Phase 0 by the choice of *which* version string lands in the key. Setting it now or never.

## Options considered

- **Envelope version only.** `schema_version = envelope_schema_version`. One source, simple. Mass-invalidates on every per-probe change.
- **Per-probe version only.** `schema_version = per_probe_schema_version`. Surgical invalidation. Envelope changes (adding a top-level field) don't invalidate anything — correct, because the envelope is metadata not probe output.
- **Both, concatenated.** `schema_version = envelope_version + "|" + per_probe_version`. Belt-and-suspenders; equivalent to "envelope only" in practice since the envelope version moves more often than per-probe versions.

## Decision

**The cache key uses the *per-probe* schema version only.** `cache/keys.py` defines two terms: `envelope_schema_version` (the single envelope `$id` version) and `per_probe_schema_version(probe)` (the `$id` of the probe's own sub-schema, falling back to `envelope_schema_version` if the probe has no sub-schema yet — Phase 0's `LanguageDetectionProbe` ships its sub-schema, so this fallback exists for hypothetical future probes only). The cache key is `identity_hash(probe.name, probe.version, per_probe_schema_version(probe), content_hash_of_inputs)`. A unit test `test_cache_invalidation_scope.py` asserts that bumping `NodeManifestProbe`'s sub-schema does not invalidate `LanguageDetectionProbe`'s cache entry.

## Tradeoffs

| Gain | Cost |
|---|---|
| Surgical invalidation: a per-probe schema bump invalidates only that probe's cache entries, not the portfolio | Two version concepts to maintain (envelope + per-probe); the distinction must be documented for probe authors |
| Phase 14's continuous-gather incremental model holds: schema iteration is cheap | If `envelope_schema_version` ever encodes information that probe outputs depend on, this decoupling silently breaks (mitigated: the envelope is by design metadata-only — see [ADR-0013](0013-layered-additional-properties-schema.md)) |
| Adding a new probe ships a new sub-schema file; only that probe's cache is "cold" — existing probes' caches still hit | Probe authors must remember to bump their sub-schema `$id` when changing output shape (caught by the schema-validation CI gate, but the discipline still has to live somewhere) |
| The two-version model encodes "envelope is metadata, sub-schema is contract" — making the architectural distinction in [ADR-0013](0013-layered-additional-properties-schema.md) load-bearing for cache correctness too | One more thing the Phase 1 probe-authoring guide must explain |

## Consequences

- `cache/keys.py` exports `per_probe_schema_version(probe: type[Probe]) -> str`. The function reads the probe's declared sub-schema path and extracts `$id`.
- `LanguageDetectionProbe`'s sub-schema at `src/codegenie/schema/probes/language_detection.schema.json` ships with `$id: ".../schemas/probes/language_detection/v0.1.0.json"` in Phase 0 — establishing the convention.
- Phase 1's five new probes each get their own sub-schema with their own `$id`. Bumping one bumps that probe's cache, period.
- A probe without a declared sub-schema (e.g., a future experimental probe) falls back to the envelope version — its cache is more brittle, but it works. Acceptable for "experimental" tier; new probes are expected to ship sub-schemas.
- The `envelope_schema_version` is **not** in the cache key. Adding a new top-level envelope field (e.g., `generated_by` for tooling provenance) costs zero cache invalidation.
- Phase 13's cost-ledger reconciliation (per [production ADR-0027](../../../production/adrs/0027-cost-attribution-model.md)) attributes spend to a probe execution by `cache_key` ([ADR-0004](0004-probe-execution-audit-anchor.md)); per-probe versioning means the attribution survives a sibling probe's schema bump.

## Reversibility

**Medium.** Switching to envelope-version-in-key invalidates every cache on the rollout boundary (the first run after the switch is cold for every probe). Reverting from envelope to per-probe again is symmetric. The cost is portfolio-scale cold-start, not data loss; the chokepoint is a single function in `cache/keys.py`.

## Evidence / sources

- `../phase-arch-design.md §Gap analysis Gap 1` (Explicitly identifies the under-specification)
- `../final-design.md §2.7` (Original cache key tuple — under-specified)
- `../final-design.md §2.9` (Layered `additionalProperties` policy — the envelope-vs-per-probe distinction this ADR consumes)
- [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md) — incremental gather depends on surgical invalidation
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — `declared_inputs` is load-bearing for cache correctness
