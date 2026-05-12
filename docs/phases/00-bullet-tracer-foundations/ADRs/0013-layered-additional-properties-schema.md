# ADR-0013: Layered `additionalProperties` schema policy — strict envelope, loose `probes.*`, per-probe sub-schemas

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** schema · validation · extension · contract
**Related:** [ADR-0003](0003-two-level-cache-key-schema-versioning.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

The JSON Schema for `repo-context.yaml` is `additionalProperties`-policy-sensitive. The security lens proposed `additionalProperties: false` at every level — strict structural validation that rejects unknown fields as buggy-probe output. The best-practices lens proposed `false` at the root only, leaving `probes.*` loose to allow new probe types to drop in.

`../critique.md §2.1.3` makes the conflict structural: `production/design.md §2.5` requires "extension by addition — adding Java, Python, or a new task type must be new probes + new Skills, never edits to existing probes or the coordinator." If the schema rejects unknown fields under `probes.*`, adding a new probe in Phase 1 requires *editing* the envelope schema — violating the extension-by-addition commitment.

The two policies are incompatible at the seam. A layered solution is needed: structural strictness at the *envelope* (where buggy fields would be ambiguous metadata), looseness under `probes.*` (where new probes drop in), and per-probe sub-schemas constraining their own slice.

## Options considered

- **`additionalProperties: false` everywhere (`[S]`).** Strict validation. Catches every buggy probe field — but violates extension by addition. Phase 1's `NodeBuildSystem` probe requires a schema edit; Phase 7's distroless-migration probes require schema edits. The extension-by-addition seam is broken.
- **`additionalProperties: true` everywhere (lens-design implicit).** Maximum extensibility, zero validation strictness. Buggy probe fields land in the YAML and pollute downstream consumers. Phase 11 commits the pollution to PRs.
- **`additionalProperties: false` at root only (`[B]`).** Envelope strict; under `probes.*` anything goes. New probes drop in. No per-probe validation — a probe's typo in its own slice is silently accepted.
- **Layered: root `false`, `probes.*` `true`, per-probe sub-schemas (synth).** Strict where strictness is structural (envelope), loose where extension matters (probes namespace), per-probe sub-schemas at `src/codegenie/schema/probes/<name>.schema.json` composed via `$ref`. Adding a probe = adding a sub-schema file + one `$ref` line. Strict validation per probe.

## Decision

**The JSON Schema for `repo-context.yaml` uses a layered `additionalProperties` policy:**

- **`additionalProperties: false`** at the **top-level envelope** (`schema_version`, `generated_at`, `repo`, `probes` required keys; no unknown top-level fields).
- **`additionalProperties: true`** under **`probes.*`** (the probes-namespace map; any probe-name key allowed).
- **Each probe owns a sub-schema** at `src/codegenie/schema/probes/<name>.schema.json` composed into the envelope via `$ref`. The sub-schema may itself be strict (`additionalProperties: false`) at the probe-slice level — at the *probe author's* discretion.

Adding a probe in Phase 1+ is one new file under `schema/probes/` plus one `$ref` line in the envelope schema. No edit to existing probe sub-schemas.

## Tradeoffs

| Gain | Cost |
|---|---|
| Extension by addition (`production/design.md §2.5`) holds at the schema level — Phase 1's six probes land as six new sub-schema files; Phase 7's distroless probes likewise | Two levels of strictness to reason about; documented in the probe-authoring guide |
| Structural validation strictness where it matters — envelope is metadata and must be exact; a typo in a top-level key is a real bug | Probe sub-schemas are optional in principle (the probe could ship without one) — the convention is "always ship a sub-schema with your probe" |
| Per-probe versioning works cleanly with [ADR-0003](0003-two-level-cache-key-schema-versioning.md)'s two-level cache key — bumping a probe's sub-schema invalidates only that probe's cache | More schema files to maintain (one per probe); compensated by each being small and probe-author-owned |
| The `$ref` composition pattern is JSON Schema standard — no custom code; `jsonschema` library handles it natively | Schema authoring requires the probe author to understand `$ref` mechanics; mitigated by the Phase 1 probe-authoring guide and the `LanguageDetectionProbe` example |
| Adding a new envelope-level field (e.g., `generated_by` for tooling provenance) is a deliberate edit — `additionalProperties: false` makes the addition visible | Envelope changes are slightly more friction than they would be with `true`; the friction is the point |

## Consequences

- `src/codegenie/schema/repo_context.schema.json` ships in Phase 0 with `additionalProperties: false` at top level and `true` under `probes.*`.
- `src/codegenie/schema/probes/language_detection.schema.json` is the first per-probe sub-schema — establishes the convention and provides Phase 1's authors a working example.
- Phase 1's six new probes add six new sub-schema files. No edit to existing schemas.
- The `Probe.schema_path` convention (or equivalent) lets `cache/keys.py`'s `per_probe_schema_version` ([ADR-0003](0003-two-level-cache-key-schema-versioning.md)) read each probe's own `$id` for cache-key versioning.
- Validation runs in two layers naturally: `jsonschema` traverses the envelope checking root strictness, then descends into `probes.*` per-key into the matching sub-schema via `$ref`.
- The "envelope is metadata, sub-schema is contract" architectural distinction is load-bearing for both schema validation *and* cache invalidation scope ([ADR-0003](0003-two-level-cache-key-schema-versioning.md)).

## Reversibility

**Low.** Tightening `probes.*` to `additionalProperties: false` later would require every probe ship a sub-schema *and* be enumerated as a property of `probes` — breaks extension by addition. Loosening the envelope to `additionalProperties: true` invites the metadata-typo class of bug the strictness exists to catch. The layered policy is the design's structural commitment.

## Evidence / sources

- `../final-design.md §2.9` (Schema validation — layered policy)
- `../final-design.md §L3 row 4` (Layered wins 12 vs `false`-everywhere's 4 vs `false`-at-root's 11)
- `../critique.md §2.1.3` (Critic establishes the incompatibility with extension by addition)
- `../phase-arch-design.md §Component design / Schema validator`
- `../phase-arch-design.md §Data model` (envelope JSON Schema example)
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — `RepoContext` schema is over-the-wire format; layered policy lifts unchanged
- [ADR-0003](0003-two-level-cache-key-schema-versioning.md) — cache invalidation scope depends on this layering
