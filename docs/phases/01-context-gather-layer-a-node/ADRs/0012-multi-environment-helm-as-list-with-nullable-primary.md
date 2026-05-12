# ADR-0012: Multi-environment Helm emitted as `environments: list` with nullable primary `image_reference`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** schema · additive-extension · localv2-conformance · contract-shape
**Related:** ADR-0004, ADR-0011

## Context

`localv2.md §5.1 A5` specifies the `deployment` slice with `image_reference` as a **singleton** field (one image reference per deployment). Real Helm repos frequently ship multi-environment value overlays — `values.yaml` + `values-prod.yaml` + `values-staging.yaml` + `values-dev.yaml`, each potentially overriding `image.repository` or `image.tag` to a different value. A singleton field cannot represent this without lying about reality.

The best-practices lens proposed emitting `image_reference` as a list. That violates `localv2.md §5.1 A5`'s explicit singleton example and forces every Phase 2+ consumer to handle a shape change to a previously-singleton field. The critic (`final-design.md` §"Conflict-resolution table") framed this as `[B] Risk #2`: the singleton-vs-list disagreement is real and must be resolved.

The synthesizer's resolution (`final-design.md "Components"` #6): keep `image_reference` as a **nullable singleton** for the single-environment case, and add a **new** `environments: list[EnvironmentEntry]` field for the multi-environment case. Additive at the per-probe sub-schema; honors `localv2.md`'s singleton shape; reflects reality.

## Options considered

- **`image_reference: list` (the best-practices lens proposal).** Reshape the existing field. Violates `localv2.md §5.1 A5`'s singleton example; every downstream consumer breaks; the Phase 0 §2.3 "`localv2.md` is source of truth" rule blocks it.
- **`image_reference: oneOf [string, list[string]]`.** Schema-level type union. Consumers must runtime-type-check every read; nightmare to evolve.
- **Drop multi-env support; emit only the first values file's image.** Hides reality. Phase 3+ recipes get incomplete information.
- **`image_reference: nullable singleton` for single-env case, additive `environments: list[EnvironmentEntry]` for multi-env case.** Honors `localv2.md`; reflects reality additively; downstream consumers handle one shape at a time.

## Decision

**The `deployment` sub-schema declares two fields:**

1. **`image_reference: ImageRefBlock | null`** — the primary/single-environment image reference. Set for `values.yaml`-only repos. `null` for multi-environment repos where there's no canonical primary.
2. **`environments: list[EnvironmentEntry]`** — one entry per detected `values-*.yaml`. Each `EnvironmentEntry`: `{name: str, image_reference: ImageRefBlock, ...}`.

Detection rule:
- If only `values.yaml` is present → `image_reference` set; `environments: []`.
- If `values.yaml` AND `values-<env>.yaml` files are present → `image_reference` may be set from `values.yaml` (or `null` if no top-level image reference exists); `environments` lists every `values-<env>.yaml`.
- Single env emitted as `environments` of length 1 is allowed (canonical when there's no `values.yaml` baseline).

The `EnvironmentEntry`'s `name` derives from the filename stem (`values-prod.yaml` → `name: "prod"`, `values-staging.yaml` → `name: "staging"`). Each entry's `image_reference` is captured the same way as the primary.

**Downstream Phase 3+ consumers must handle the list shape from day one** (`phase-arch-design.md "Integration with Phase 2 (next phase)"` — explicit implicit guarantee). The "consumer contract" question — whether some consumers can treat `environments` as authoritative when present and ignore the primary — is recorded as `final-design.md` "Open questions" #6.

## Tradeoffs

| Gain | Cost |
|---|---|
| Honors `localv2.md §5.1 A5`'s singleton shape — Phase 0 §2.3 conformance preserved | Two fields where one might have sufficed; downstream consumers handle both |
| Multi-env repos report all environments accurately; Phase 3+ recipes can pick the right one (e.g., "use prod's image tag for the bump recipe") | The "what's THE image reference?" question has no single answer for multi-env repos; consumers handle it semantically |
| Additive at the per-probe sub-schema — ADR-0004 strictness preserved | The sub-schema declares both fields; a consumer that only reads `image_reference` silently misses environments |
| Composes with ADR-0011 — no Helm template rendering required to capture multi-env evidence; values-file parsing is sufficient | If a deployment's image is computed via `helm template` interpolation, neither the primary nor the `environments` list captures the resolved value — Phase 3+ renders if needed |
| The `name` derivation from filename stem is deterministic and matches Helm-community convention | Repos with non-standard naming (e.g., `values.prod.yaml` instead of `values-prod.yaml`) get `name: "prod.yaml"` — captured as a warning if format unrecognized |
| Empty `environments: []` for single-env repos is unambiguous; nullable `image_reference` distinguishes "no image found" from "no environments listed" | Three states to handle (null primary + empty env / set primary + empty env / null primary + non-empty env) — documented in sub-schema comments |
| Sub-schema declares both shapes upfront — no future-breaking change when a single-env repo adopts multi-env structure | Sub-schema is more complex; `tests/unit/probes/test_deployment.py` covers all four shape permutations |

## Consequences

- `src/codegenie/schema/probes/deployment.schema.json` declares `image_reference` as `nullable` and `environments` as an array of `EnvironmentEntry`-shaped objects. Both at root level; `additionalProperties: false` enforces strictness (ADR-0004).
- `DeploymentProbe` enumerates `values*.yaml` glob-matched paths, parses each with `safe_yaml.load` (10 MB cap, depth 64), and assembles the `environments` list. The primary is read from `values.yaml` if present.
- `tests/unit/probes/test_deployment.py` covers: (a) `values.yaml` only → `image_reference` set, `environments: []`; (b) `values.yaml` + `values-prod.yaml` + `values-staging.yaml` → primary + 2-entry environments; (c) `values-prod.yaml` only (no baseline) → `image_reference: null`, 1-entry environments; (d) `values-prod.yaml` + `values-staging.yaml` + `values-dev.yaml` → 3-entry environments.
- `tests/unit/probes/test_deployment.py` also covers the 12-environment case (Edge case #15) — `additionalProperties: false` continues to bind on each entry.
- Phase 3+ task-class consumers query `environments` first if multi-env is in scope; fall back to `image_reference` for single-env. The convention is documented in the sub-schema's description field.
- Phase 7's distroless migration is largely unaffected — it consumes `manifests.native_modules`, not `deployment.image_reference`. But it inherits the precedent for future multi-shape additive extensions.
- The "open question" #6 (`final-design.md`) — whether consumers can ignore the primary when `environments` is non-empty — remains a Phase-3 consumer-contract decision; this ADR captures the data shape, not the consumer semantics.

## Reversibility

**Low.** Folding `environments` back into `image_reference: list` is a breaking sub-schema change requiring envelope-major-version invalidation. Existing Phase 1 cached outputs continue to validate against the additive shape; reverting requires re-gathering every repo. The forward direction (additional per-environment fields under `EnvironmentEntry`) is symmetric and additive. The shape choice (additive list-alongside-singleton) is deliberately the most future-compatible of the four options.

## Evidence / sources

- `../final-design.md "Components" #6 DeploymentProbe` — multi-env-as-list design
- `../final-design.md "Failure modes & recovery"` row 13 — schema accepts both shapes; consumer contract test verifies handling
- `../final-design.md "Open questions deferred to implementation" #6` — consumer contract open question
- `../phase-arch-design.md "Component design" #6 DeploymentProbe` — interface specifics
- `../phase-arch-design.md "Data model" DeploymentSlice` — Python shape
- `../phase-arch-design.md "Edge cases"` row 15 — 12-environment case
- `../../../localv2.md §5.1 A5` — the singleton example this honors
- ADR-0004 — per-probe sub-schema strictness this rides on
- ADR-0011 — no Helm rendering decision that bounds what this captures
