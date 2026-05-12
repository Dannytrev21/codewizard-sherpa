# ADR-0006: Native module catalog versioning — `catalog_version` participates in cache key

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** catalog · data-as-code · cache-invalidation · cross-phase · silent-staleness
**Related:** [Phase 0 ADR-0001](../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md), [Phase 0 ADR-0003](../../00-bullet-tracer-foundations/ADRs/0003-two-level-cache-key-schema-versioning.md), [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md)

## Context

`NodeManifestProbe` ships with `src/codegenie/catalogs/native_modules.yaml` — a hand-curated catalog of well-known native modules (`bcrypt`, `sharp`, `better-sqlite3`, etc.) and the system dependencies / binary artifacts each one requires. The catalog is the load-bearing input for Phase 7's Chainguard distroless migration (`roadmap.md` §"Phase 7"). A missed entry → a Phase 7 distroless build that compiles, passes tests, and crashes at runtime because the native module's runtime library isn't in the distroless image. This is exactly the silent-staleness failure mode `production/design.md §2.3` calls out as the worst failure shape.

The best-practices lens proposed the catalog. The synthesizer (`final-design.md "Risks"` #1) acknowledged the catalog-gap risk explicitly: Phase 1 seeds ~10 entries; gaps surface in Phase 7, five phases out. The mitigation cannot be "be more careful"; it must be a structural cache-invalidation signal so that **any catalog edit** invalidates every cached `NodeManifest` output that was produced under the old catalog.

Phase 0 ADR-0001 + ADR-0003 establish the cache key derivation: `SHA-256(probe_name | probe_version | schema_version | inputs_hash_hex)` where `inputs_hash` is BLAKE3 over `(path, size)` tuples of `declared_inputs`-matching files. The catalog must participate in this key.

## Options considered

- **Auto-derive native modules from `npm` registry metadata.** Removes the hand-curation gap. The metadata is itself attacker-controlled input — exactly the threat model Phase 1 closes. Materially worse.
- **Bump the probe's `version` constant on every catalog edit.** Probe version is in the cache key (Phase 0 ADR-0003); editing it invalidates. Conflates "code change" with "data change" — bad audit trail; reviewers can't distinguish.
- **`catalog_version: int` field at the top of `native_modules.yaml`, AND the catalog YAML file is listed in `NodeManifestProbe.declared_inputs`.** Then the catalog's bytes flow through the same `(path, size)` hash the other inputs do. A bump to `catalog_version` is a semantic signal in the file content (humans can see "this is a deliberate revision"). A change to any catalog entry naturally changes file bytes and invalidates.
- **`catalog_entry_version: int` per entry, additionally.** Per-entry versioning so audits can answer "when was `sharp` last reviewed?" — orthogonal to file-level invalidation.

## Decision

**Two-level catalog versioning, with file-level cache invalidation via `declared_inputs`:**

1. **`catalog_version: int` at the top of `native_modules.yaml`** — bumped by hand whenever a deliberate revision lands. Surfaces in the `manifests` slice as a field; downstream consumers can read it.
2. **`catalog_entry_version: int` per native module entry** — bumped when that specific entry's `system_deps_required` or `binary_artifacts_glob` changes. Surfaces per-entry; the audit trail.
3. **`src/codegenie/catalogs/native_modules.yaml` is listed in `NodeManifestProbe.declared_inputs`.** The Phase 0 cache key derivation includes the catalog YAML's `(path, size)` tuple. Any byte-level edit (including a `catalog_version` bump) invalidates every cached `NodeManifest` output produced under the previous bytes.
4. **The catalog `_schema.json` validates structure at CLI startup.** Duplicate names raise `CatalogLoadError`; missing `catalog_version` raises `CatalogLoadError`. Hard fail.

The same shape applies to `ci_providers.yaml` (its `catalog_version` is in `CIProbe.declared_inputs`).

## Tradeoffs

| Gain | Cost |
|---|---|
| Any catalog edit invalidates cached `node_manifest` outputs cleanly — no silent staleness from cached probes serving old catalog inferences | Cache invalidation blast radius is "every gather that ran on the old catalog" — every consumer re-parses lockfiles when the catalog ships an update |
| `catalog_version` is a semantic signal humans can audit — "what changed in revision 7?" answers from git log | Two version numbers per entry (`catalog_version`, `catalog_entry_version`) — discipline required to bump the right one |
| Phase 7's catalog update at Phase 7 time triggers a fleet-wide `node_manifest` re-gather automatically — the cross-phase invalidation story is concrete | Phase 7's first catalog update produces a cache-miss storm in CI for the integration suite; budget for it |
| The `(path, size)` cache key derivation is unchanged from Phase 0 ADR-0001; no new cache-key shape | Two same-size YAML edits (e.g., swapping two entry orderings) won't invalidate — accepted Phase 1 limitation; documented in `final-design.md` Risk #4 |
| Audits answer "when was `sharp` last reviewed?" by reading `catalog_entry_version` and `git blame` of the YAML | Adds two int fields per native module entry; YAML editor burden |
| Catalog self-schema (`_schema.json`) catches malformed entries at CLI startup — fail-loud per Rule 12 | Catalog YAML PRs must include schema-passing edits; a CI gate enforces |

## Consequences

- `src/codegenie/catalogs/native_modules.yaml` has `catalog_version: int` at file top and `catalog_entry_version: int` per entry. `src/codegenie/catalogs/ci_providers.yaml` follows the same shape.
- `NodeManifestProbe.declared_inputs` includes `"src/codegenie/catalogs/native_modules.yaml"`. The Phase 0 cache key derivation includes the catalog file in `inputs_hash`.
- `src/codegenie/catalogs/_schema.json` validates structure; the catalog loader (`catalogs/__init__.py`) fails the CLI hard if validation fails (Edge case #9).
- `tests/unit/test_catalogs.py` asserts (a) catalog YAML parses; (b) catalog schema validates; (c) duplicate names rejected; (d) `catalog_version` present.
- `tests/unit/probes/test_node_manifest.py` asserts catalog-version bump invalidates cached output (the bump changes file bytes → `inputs_hash` changes → cache miss).
- Phase 7's integration suite is explicitly tasked with exercising the catalog and surfacing gaps (`final-design.md "Risks"` #1).
- The `manifests` slice exposes `catalog_version: int` (the file-level version that produced this slice). Downstream consumers can pin to a minimum version.

## Reversibility

**Medium.** Removing the `catalog_version` field is a YAML edit + a `declared_inputs` edit + a sub-schema field removal. Cached outputs continue to validate (the field becomes absent rather than mis-typed). The semantic loss is the "what changed in revision N?" audit — irreversible only in the sense that history is gone, not the contract. Per-entry `catalog_entry_version` removal is symmetric. The cross-phase invalidation story would survive partial removal (file-level `(path, size)` still in the cache key) but lose the human-readable signal.

## Evidence / sources

- `../final-design.md "Components" #4 NodeManifestProbe` — catalog structure
- `../final-design.md "Risks" #1` — silent-staleness risk register
- `../final-design.md "Open questions deferred to implementation" #7` — catalog versioning was an Open Question
- `../phase-arch-design.md "Component design" #4` — catalog spec
- `../phase-arch-design.md "Component design" #10 Catalog loader` — `MappingProxyType` immutability
- `../phase-arch-design.md "Edge cases" rows 8–9` — catalog gap + malformed catalog
- `../phase-arch-design.md "Path to production end state"` — Phase 7's catalog dependency
- [Phase 0 ADR-0001](../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md), [Phase 0 ADR-0003](../../00-bullet-tracer-foundations/ADRs/0003-two-level-cache-key-schema-versioning.md) — the cache-key derivation this honors
- [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md) — the continuous-gather story that depends on clean invalidation
