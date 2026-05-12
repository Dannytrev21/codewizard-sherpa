# ADR-0010: Layer A slices declared optional at the envelope's `probes.*` level

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** schema · multi-language · extension · envelope-shape
**Related:** ADR-0004, [Phase 0 ADR-0013](../../00-bullet-tracer-foundations/ADRs/0013-layered-additional-properties-schema.md)

## Context

The five new Phase 1 probes (`NodeBuildSystem`, `NodeManifest`, and `TestInventory` declare `applies_to_languages = ["javascript", "typescript"]`; `CI` and `Deployment` declare `["*"]`). `LanguageDetectionProbe` runs on every repo. The Phase 0 `Registry.for_task` filter correctly skips probes whose languages don't match the detected stack.

But the envelope's schema has to validate either way. A Go-only repo gathered through `codegenie gather` produces a `repo-context.yaml` with **only** the `language_stack` slice populated (the three Node-only Phase 1 probes are filtered out; `CI` and `Deployment` run but may produce empty slices). If Phase 1 sub-schemas declare any Layer A slice as `required` at the envelope's `probes.*` level, the envelope fails schema validation on every non-Node repo.

The best-practices lens (`design-best-practices.md`) surfaced three options — "nullable variants" / "conditional branches" / "separate envelope" — without picking one. The synthesizer (`final-design.md "Failure modes & recovery"` row 14) picked: declare each Layer A slice as **optional** at the envelope's `probes.*` level. The cleanest of the three options; minimum-friction path forward.

The arch doc (`phase-arch-design.md "Edge cases"` row 11, Scenario 4) reinforces: tested by `tests/integration/probes/test_non_node_repo.py`.

## Options considered

- **Required slices, nullable shape.** Slices are `required` in the envelope; non-applicable slices ship as `null`. Cluttered envelope; every consumer checks `if slice is not None` everywhere; every probe emits a stub slice when filtered out.
- **Conditional branches via `oneOf` (Node-envelope vs. Go-envelope vs. Python-envelope, etc.).** Type-correct but the envelope schema grows combinatorially with language coverage; future Layer B+ probes touching multi-language repos make the schema explode.
- **Separate envelope per language.** Different artifact shapes per language. Consumer complexity multiplies; the `repo-context.yaml` cross-phase contract becomes language-keyed.
- **Optional slices at the envelope's `probes.*` level.** A non-Node repo produces an envelope with the slice key absent. Consumers handle `Optional[Slice]`. Schema validates cleanly. Composes with ADR-0004's per-probe sub-schema strictness (the slice that IS present is strict; the slice that's absent is fine).

## Decision

**Each Phase 1 sub-schema declares its slice as optional at the envelope's `probes.*` level.** The envelope's `properties.probes` does not list any Phase 1 slice in its `required` array. The slice's key is **absent** (not `null`) from the YAML when its probe was filtered out by `Registry.for_task`.

This composes with ADR-0004's per-probe sub-schema strictness: if the slice is present, every key inside it conforms to the sub-schema's `additionalProperties: false` root. If the slice is absent, no validation runs against it. Optional fields *inside* a sub-schema continue to use `null` for not-present rather than field-absence (per ADR-0004).

**Downstream consumers are obligated to treat every Layer A slice as `Optional[Slice]`** — codified as a Phase 1 → Phase 2 implicit guarantee (`phase-arch-design.md "Integration with Phase 2 (next phase)"`).

The `for_task` filter (Phase 0 Registry) is what determines which probes run on a given repo; the schema's optionality just admits the resulting envelope shape.

## Tradeoffs

| Gain | Cost |
|---|---|
| Non-Node repos (Go-only, Python-only, etc.) validate cleanly — no special-casing in the envelope | Every downstream consumer must defensive-check `Optional[Slice]` access |
| Composes with ADR-0004 — per-probe strictness lives at the slice root; absence is not malformedness | "Present-but-empty" vs. "absent" must be distinguishable; the convention is absent-when-filtered, present-but-degraded when ran-but-failed |
| The envelope shape doesn't grow combinatorially with language coverage — Phase 2 adds Layers B–G probes with the same pattern | Reading the YAML requires understanding "what's missing means what didn't apply" — documented in `final-design.md` row 14 |
| `Registry.for_task` (Phase 0) carries the load-bearing filter; schema admits the result | Two layers of optionality — the schema permits absence; the registry decides absence — easier to reason about than `oneOf`-branching schemas |
| Phase 8 hot views (when they land) project from present slices; absence is a natural skip | Hot views must handle slice absence; tested when Phase 8 lands |
| Adds no envelope-edit churn — Phase 0's envelope `probes.*` policy from ADR-0013 (`additionalProperties: true`) is preserved | A future "Node is required for this kind of task" enforcement (e.g., a Phase-3 task class for Node migrations) must enforce at the planner level, not at the schema |

## Consequences

- The envelope's `properties.probes.required` array does NOT list `node_build_system`, `node_manifest`, `ci`, `deployment`, `test_inventory`, or the extended fields of `language_detection`. The slices are admitted but not required.
- `tests/integration/probes/test_non_node_repo.py` is the load-bearing regression — a Go-only fixture under `tests/fixtures/non_node_go/` gathers cleanly; envelope validates with `language_stack` only.
- `tests/unit/test_sub_schemas.py` asserts each Phase 1 sub-schema declares optionality at the envelope level (no `required` reference to its slice key in the envelope).
- Phase 2's Layer B/C/D/G probes follow the same convention. The "all Layer A slices present means a Node repo" inference is a planner-level decision, never schema-enforced.
- Phase 3+ task-class consumers handle `Optional[Slice]` — if `manifests` is absent, the task isn't applicable, full stop.
- The Phase 0 → Phase 1 invariant — "the envelope shape is forward-compatible" — is honored by addition only.

## Reversibility

**Low.** Flipping to `required` retroactively breaks every non-Node repo's cached envelope. Callers (Phase 3+ recipes, the planner, Phase 8 hot views) have come to depend on absence semantics; making slices required mid-stream breaks them. The forward direction (more optional slices in future phases) is symmetric and additive. The reverse direction (tighter language-conditional schemas) requires either a major version bump on the envelope (Phase 0 ADR-0003's schema versioning) or coordinated cache invalidation across all repos.

## Evidence / sources

- `../final-design.md "Failure modes & recovery"` row 14 — non-Node repo path
- `../final-design.md "Risks" #5` — the framing
- `../final-design.md "Tests explicitly not in Phase 1"` — non-Node fixture is in scope
- `../phase-arch-design.md "Component design" #11` — per-probe sub-schemas declare slices as optional
- `../phase-arch-design.md "4+1 architectural views" "Scenarios" "Scenario 4"` — Go-only fixture flow
- `../phase-arch-design.md "Edge cases"` row 11 — non-Node repo edge case
- `../phase-arch-design.md "Integration with Phase 2"` — implicit guarantee
- ADR-0004 — the per-probe sub-schema strictness this composes with
- [Phase 0 ADR-0013](../../00-bullet-tracer-foundations/ADRs/0013-layered-additional-properties-schema.md) — the envelope policy this preserves
