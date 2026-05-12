# ADR-0004: Per-probe sub-schema `additionalProperties: false` at its own root

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** schema · validation · extension · contract · chokepoint
**Related:** [Phase 0 ADR-0013](../../00-bullet-tracer-foundations/ADRs/0013-layered-additional-properties-schema.md), [Phase 0 ADR-0008](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md), ADR-0007

## Context

Phase 0 ADR-0013 specified the **envelope** layering: `additionalProperties: false` at the root of `repo_context.schema.json`, **but** `probes.*: additionalProperties: true` — so a new probe in any future phase can land its slice without rewriting the envelope. The strictness has to live somewhere, otherwise a typo'd field on a probe slice (e.g., `image_referenece` instead of `image_reference`) passes envelope validation and propagates to downstream consumers as a silent miss.

The critic's cross-design observation #1 (`final-design.md "Shared blind spots considered"` #1): all three lens designs *implicitly* wanted `additionalProperties: false` per probe — none cited Phase 0 §2.9 / ADR-0013 explicitly, and none documented where the strictness should live. The security lens proposed a third sanitizer pass (`OutputSanitizer.scrub` adds a size/depth cap on `schema_slice`) but that edits Phase 0 ADR-0008's frozen chokepoint without amendment (`critique.md "Attacks on the security-first design"` #5).

The synthesizer position: the strictness lives **per-probe**, at each sub-schema's own root — not globally, not in the sanitizer, not at the envelope's `probes.*` boundary.

## Options considered

- **`additionalProperties: false` at envelope's `probes.*` (global).** Forbids any probe ever to ship an extra field anywhere in its slice. Future-hostile; reverses Phase 0 ADR-0013 explicitly.
- **Third sanitizer pass that caps slice size/depth ([S]).** Adds capacity defense at the chokepoint. Edits the frozen `OutputSanitizer.scrub` without ADR amendment (Phase 0 ADR-0008); doesn't solve typo'd-field problem.
- **Per-probe sub-schemas, each declaring `additionalProperties: false` at its own root, composed into the envelope via `$ref`.** Strictness is local. Adding a field is a probe-code change + sub-schema change in the same PR — the friction is the point.

## Decision

**Each Phase 1 probe owns one JSON Schema Draft 2020-12 file at `src/codegenie/schema/probes/<probe_name>.schema.json`:**

- `language_detection.schema.json` (extended in Phase 1)
- `node_build_system.schema.json`
- `node_manifest.schema.json`
- `ci.schema.json`
- `deployment.schema.json`
- `test_inventory.schema.json`

**Each sub-schema declares `additionalProperties: false` at its own root.** The Phase 0 envelope's `additionalProperties: false` at top and `probes.*: additionalProperties: true` are **preserved unchanged** (Phase 0 ADR-0013).

Sub-schemas are referenced from the envelope via relative `$ref`. Optional fields use `null` for not-present rather than field-absence (so `additionalProperties: false` means what it says — every present key is declared). Each Phase 1 sub-schema declares its slice **optional** at the `probes.*` level so non-Node repos produce a valid envelope (see ADR-0010).

Adding a field to any Phase 1 probe slice requires editing both the probe code and the sub-schema in the same PR. **No release-versioning policy** for sub-schemas is introduced in Phase 1 — `localv2.md` doesn't have one; Phase 2 introduces it when the first cross-phase sub-schema change is anticipated.

## Tradeoffs

| Gain | Cost |
|---|---|
| Typo'd or undeclared fields fail at land-time validation (CI exit 3) — not at downstream-consumer parse time | Each new field is a two-file PR (code + sub-schema); friction by design |
| Phase 0 ADR-0008's two-pass `OutputSanitizer` stays frozen — no chokepoint edit | A future global cross-cutting field (e.g., per-probe `cost_attribution`) requires editing every sub-schema; convention is the load-bearer |
| Phase 0 ADR-0013's layered policy is preserved — `probes.*: true` keeps future probes additive at the envelope level | Per-probe sub-schemas drift in shape conventions unless documented (deferred to Phase 2's versioning policy) |
| Optional-by-default at envelope level means non-Node repos validate cleanly (ADR-0010) — Layer A slices are absent on Go-only fixtures, not invalid | Downstream consumers must treat all Phase 1 slices as `Optional[Slice]` — codified as a Phase 2 implicit guarantee |
| Sub-schemas are `$ref`-composed; validator compile cost bumps from ~30 ms to ~50 ms — within envelope of cold-start budget | Six sub-schema files (one per probe + the LanguageDetection extension) instead of one giant envelope — more files to navigate |
| The pattern is reusable: Phase 2 adds Layers B–G sub-schemas with the same shape without revisiting this decision | A future probe wanting forward-compat field (e.g., `[S] Goal #6`'s `prompt_injection_marker_count`) must amend its sub-schema in the same PR — adoption friction |

## Consequences

- `src/codegenie/schema/probes/` is a new directory. Phase 0's envelope `$ref`s into it. The envelope shape (top-level keys) does not change in Phase 1.
- `tests/unit/test_sub_schemas.py` asserts (a) each sub-schema is valid Draft 2020-12; (b) each `$ref` resolves; (c) each sub-schema has `additionalProperties: false` at its own root.
- The schema validator chain at envelope merge time becomes: envelope-root strict → `probes.*` loose → per-sub-schema strict. The validator's `SchemaValidationError` carries the failing JSON Pointer so the operator can find the offending field.
- Phase 2 inherits the convention. Layer B/C/D/G sub-schemas land in the same directory with the same root-strict rule.
- The `warnings: list[WarningId]` field in every sub-schema is pattern-constrained per ADR-0007 — the structural defense against prose-judgment smuggling lives in each sub-schema.
- The "per-probe sub-schema versioning policy" open question (final-design "Open questions" #2) is deferred to Phase 2.

## Reversibility

**Medium.** Flipping any one sub-schema to `additionalProperties: true` is a one-line JSON edit; the validator continues to function. Doing so reverses the structural defense for that probe and silently re-opens the typo'd-field failure mode. The reverse direction (making `probes.*: false` at the envelope) is a Phase 0 ADR-0013 amendment, not a Phase 1 ADR concern. Removing the sub-schema directory entirely would require re-inlining six slice shapes into the envelope — mechanically expensive but doable, and cached outputs continue to validate against the inlined shapes.

## Evidence / sources

- `../final-design.md "Components" #9 Per-probe sub-schemas` — the design statement
- `../final-design.md "Shared blind spots considered" #1` — the critic-flagged agreement
- `../final-design.md "Conflict-resolution table" row 4` — the resolution
- `../phase-arch-design.md "Component design" #11` — interface
- `../phase-arch-design.md "Data model"` — `model_config = ConfigDict(extra="forbid")` mirror in Python
- `../critique.md "Attacks on the security-first design"` #5 — the rejected sanitizer-third-pass alternative
- [Phase 0 ADR-0013](../../00-bullet-tracer-foundations/ADRs/0013-layered-additional-properties-schema.md) — the layered policy this extends
- [Phase 0 ADR-0008](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md) — the chokepoint this avoids editing
