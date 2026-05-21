# ADR-0024: `BaseImageProbe` is extended (not duplicated) for architecture-coverage delta and non-public-registry detection

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** amendment-a · extension-by-addition · open-closed · honest-confidence · gather-or-refuse
**Related:** [0005](0005-probes-live-under-plugin-not-core-tree.md), [0008](0008-no-vuln-provenance-cache-in-phase-7.md), [0009](0009-phase-7-byte-edit-allowlist-fence.md), [0025](0025-migration-refusal-taxonomy.md), [0026](0026-migration-confidence-aggregation.md), [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

Amendment A's gap inventory (`../final-design.md §Amendment A §A.2`) names two image-resolution hazards a naive `FROM` swap silently introduces:

- **G11 — multi-architecture coverage delta.** The source image may publish a manifest list covering architectures the Chainguard target does not. `node:18-alpine` ships `armv7`; `cgr.dev/chainguard/node` ships `amd64`/`arm64` only. A `FROM` swap that drops `armv7` produces an image that builds clean and passes the gate, then fails to schedule on an `armv7` node in production — a silently dropped platform.
- **G13 — non-public mirror base image.** A `FROM` referencing an internal mirror (e.g. `acmecorp/node:18-alpine-patched`) may already carry the CVE patched *differently* than the public upstream. A migration that assumes the public-registry patch state can regress or duplicate a fix.

Both hazards are answered by facts the **existing** `BaseImageProbe` (`../phase-arch-design.md §Component design §8`) is already 90% of the way to producing: it reads every `FROM`, resolves it to an immutable digest via `ctx.image_digest_resolver`, and classifies the image kind. The architecture set is in the resolved manifest list; the registry host is in the `ImageRef` string. The design question is whether to add a second probe or grow the one that already holds the digest. `../phase-arch-design.md §Component design — Amendment A` resolves G11/G13 as a `BaseImageProbe` *extension*, and `../final-design.md §Amendment A §A.2` (G11, G13 rows) names the component as `BaseImageProbe extension`.

## Options considered

- **Option A — A separate `ArchitectureProbe`** (Layer C, plugin-internal) that resolves the `FROM` digest a second time to read the manifest list. **Pattern:** One probe per concern. **Rejected** — `BaseImageProbe` already calls `ctx.image_digest_resolver` for every `FROM`; a second probe re-does the identical resolution (a duplicate `crane manifest` / `docker manifest inspect` round-trip per unique `FROM`), doubling the cold-path cost the §8 performance envelope budgets, and splitting one image's facts across two slices that consumers must then re-join.
- **Option B — Extend the existing `BaseImageProbe`** with additive slice fields: `supported_architectures` on each `BaseImageStage`, and a `non_public_registry: bool` flag derived from the `ImageRef` host. **Pattern:** Open/Closed by additive fields on an existing slice — the schema grows, nothing existing changes.
- **Option C — Ignore architecture entirely; resolve only the digest and image kind.** **Pattern:** Minimal probe. **Rejected** — silently drops a production platform (G11). "Builds clean, fails to schedule" is exactly the broken-image outcome §A.1 forbids.

## Decision

Adopt **Option B.** Extend the existing `BaseImageProbe` — no new probe. `BaseImageSlice`'s per-stage record (`BaseImageStage`) gains:

- `supported_architectures: tuple[str, ...]` — the architecture set of the **source** image, read from the already-resolved manifest list.
- `non_public_registry: bool` — `True` when the `FROM` `ImageRef` host is not a recognised public registry (`docker.io`, `ghcr.io`, `cgr.dev`, ...).

Behavioural consequences:

- **G11.** When a source stage's `supported_architectures` is a strict superset of the Chainguard target's (the target set comes from `TargetImageContentProbe`'s `supported_architectures`, ADR-0019), the migration would drop a platform. The recipe **refuses** with `RefusedArchitectureLoss` ([0025](0025-migration-refusal-taxonomy.md)), naming the dropped architecture(s) — a typed refusal, not a silent drop.
- **G13.** When `non_public_registry` is `True`, the resolving adapter reports `AdapterConfidence.Degraded` and the probe emits a **WARN** requiring HITL acknowledgement — the operator confirms the mirror's patch state before the migration proceeds. The migration is not refused (the mirror may be fine); it is degraded and surfaced.

This amends the still-`Ready` story **S7-01** — its acceptance criteria gain the two new fields and the `RefusedArchitectureLoss` / `Degraded`-on-mirror behaviour, per `../phase-arch-design.md §Amendment A gaps §Sequencing`.

## Tradeoffs

| Gain | Cost |
|---|---|
| Zero duplicate digest resolution — the two new facts ride the `crane`/`docker manifest` round-trip `BaseImageProbe` already makes; the §8 performance envelope (p99 ≤ 60 ms cold) holds | `BaseImageProbe` now carries two concerns (kind classification + arch/registry delta). Accepted: both derive from the same resolved manifest; cohesion is high, not a grab-bag |
| Open/Closed by additive fields — `base_image.schema.json` grows two properties; no existing field, consumer, or `$ref` changes; existing slice readers keep parsing | The slice schema is a Phase-8+ contract; growing it is a one-way additive commitment (cannot later remove `supported_architectures` without a breaking change). Worth it; additivity is the project's standing rule (production ADR-0043) |
| `RefusedArchitectureLoss` makes a dropped platform a **typed, evidenced** outcome — HITL sees exactly which arch is lost, not a runtime scheduling failure weeks later | The target arch set is a cross-probe dependency (`TargetImageContentProbe`); if that probe is `Unavailable` the comparison cannot be made. Handled: a missing target arch set degrades `MigrationConfidence` ([0026](0026-migration-confidence-aggregation.md)) rather than producing a false "no loss" |
| `non_public_registry` → `AdapterConfidence.Degraded` reuses the existing adapter-confidence channel — no new confidence vocabulary, the [0026](0026-migration-confidence-aggregation.md) rollup already consumes `Degraded` | Registry-host classification is a heuristic over a host allowlist; a private registry with a public-looking host is misclassified. Accepted: false-negative degrades to "treated as public", caught by the build gate; the allowlist is data, extensible without an ADR |
| One probe, one slice — consumers read all of an image's facts (kind, digest, arch, registry) from one place; no cross-slice join | — |

## Pattern fit

Instantiates **Open/Closed by extension, not duplication** ([0005](0005-probes-live-under-plugin-not-core-tree.md)'s "extension by addition"; production ADR-0007's frozen-contract-extended-by-addition) — the *probe* is extended by additive *fields*, the schema grows, the Probe ABC and existing consumers are untouched. Honours **Honest confidence** (production design §2.3) — a mirror base image is not silently trusted; it surfaces as `AdapterConfidence.Degraded`. Honours **Gather-or-refuse, never ship broken** (`../final-design.md §Amendment A §A.1`) — architecture loss is a deterministic, detectable condition, so it gets a typed *refusal* ([0025](0025-migration-refusal-taxonomy.md)), not a WARN.

## Consequences

- No new probe file. `plugins/distroless-migration--node--npm/probes/base_image_probe.py` is edited to populate the two new fields — this is an Amendment-A byte-edit allowlisted by [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md).
- `plugins/distroless-migration--node--npm/schema/base_image.schema.json` gains `supported_architectures` and `non_public_registry` (additive; allowlisted by [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md)). No envelope `$ref` change — the slice already has one.
- `BaseImageStage` gains `supported_architectures: tuple[str, ...]` and `non_public_registry: bool`.
- `RefusedArchitectureLoss` is a new variant of the closed refusal taxonomy ([0025](0025-migration-refusal-taxonomy.md)); its payload names the dropped architecture(s) and the source stage.
- The recipe (`DockerfileBaseImageSwapTransform`) consumes `supported_architectures` and compares against `TargetImageContentProbe`'s set; a strict superset → `RefusedArchitectureLoss`.
- `non_public_registry == True` → resolving adapter reports `AdapterConfidence.Degraded` → `RuntimeCompatProbe`-style WARN requiring HITL acknowledgement; `MigrationConfidence` rolls up `Degraded` ([0026](0026-migration-confidence-aggregation.md)).
- Story **S7-01** acceptance criteria are amended to cover both fields and both behaviours.
- The public-registry host allowlist is module-level data; extending it is not an ADR amendment.

## Reversibility

**Medium.** The two new slice fields are an additive, one-way contract — once Phase 8+ consumers read `supported_architectures`, removing it is a breaking change requiring coordination. The *implementation* (which CLI resolves the manifest list — `crane` per ADR-0028) is internal and freely swappable. Reversing the **policy** — moving architecture detection back into a separate probe — would re-introduce the duplicate digest resolution Option A was rejected for, and would split one image's facts across two slices, forcing every consumer and the TCCM `must_read` list to migrate.

## Evidence / sources

- `../final-design.md §Amendment A §A.2` (G11, G13 rows — component named `BaseImageProbe extension`), `§A.1` (governing principle)
- `../phase-arch-design.md §Component design §8` (`BaseImageProbe` — existing digest resolution + performance envelope), `§Component design — Amendment A`, `§Amendment A gaps §Sequencing` (S7-01 amended)
- [ADR-0005 — Probes live under the plugin; extension by addition](0005-probes-live-under-plugin-not-core-tree.md)
- [ADR-0009 — Phase 7 byte-edit allowlist fence](0009-phase-7-byte-edit-allowlist-fence.md)
- [ADR-0025 — Migration refusal taxonomy (`RefusedArchitectureLoss`)](0025-migration-refusal-taxonomy.md)
- [ADR-0026 — `MigrationConfidence` aggregation (`AdapterConfidence.Degraded` rollup)](0026-migration-confidence-aggregation.md)
- [production ADR-0007 — Probe contract preserved POC→service](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)
