# ADR-0007: `warnings[]` entries pattern-constrained to structured IDs

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** schema · facts-not-judgments · structural-defense · pattern-constraint
**Related:** ADR-0004, [Phase 0 ADR-0010](../../00-bullet-tracer-foundations/ADRs/0010-pydantic-probe-output-validator.md), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)

## Context

`production/design.md §2.2` mandates "facts, not judgments" — probes capture evidence, not conclusions. The `_ProbeOutputValidator` (Phase 0 ADR-0010) makes judgment-shaped types structurally unrepresentable via the recursive `JSONValue` recursive type plus the field-name regex.

But the `warnings: list[str]` field on every `ProbeOutput` (per `localv2.md §4`) is a free-form string list. Without a structural constraint, a probe author can write `warnings: ["This Helm chart looks production-ready"]` — a judgment in evidence's clothing. The critic's cross-design observation #4 (`final-design.md "Shared blind spots considered"` #4) flagged this directly: all three lens designs under-specified the `warnings`/`errors` field shape; `production/design.md §2.2` makes the structural defense load-bearing.

The full mitigation is a typed enum, but introducing one in Phase 1 is premature (no consumer is grouping warnings yet; the enum would need to evolve across phases). The minimum structural defense is a **pattern constraint** at the per-probe sub-schema level: every warning ID must follow a discoverable, namespaced shape so downstream consumers (Phase 2's `IndexHealthProbe`) can group by prefix without parsing prose.

## Options considered

- **Free-form `warnings: list[str]`.** No constraint. Probes drift into prose; downstream consumers parse English to group.
- **Closed enum of allowed warning IDs (full typed defense).** Robust. Premature for Phase 1 — every new warning is a cross-phase schema bump; Phase 2's `IndexHealthProbe` is the natural owner once the warning vocabulary stabilizes.
- **Pattern constraint `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`** — namespaced, lowercase, snake-case-with-dots. Allows any new warning ID that fits the shape; rejects prose; enables prefix-based grouping (e.g., all `tsconfig.*` warnings group together).

## Decision

**Every `warnings: list[WarningId]` field in every Phase 1 sub-schema constrains `WarningId` to the JSON Schema pattern:**

```
^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$
```

In Python (per `phase-arch-design.md` "Data model"):

```python
WarningId = Annotated[str, Pattern(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")]
```

Examples that fit:
- `tsconfig.extends_depth_exceeded`
- `tsconfig.extends_cycle`
- `package_manager.multi_lockfile`
- `lockfile.depth_cap_exceeded`
- `kustomization.resource_outside_repo`
- `node.version_declared_resolved_disagree`
- `ci.workflow_parse_error`

The pattern enforces:
- **Lowercase + snake_case** — no `CamelCase`, no spaces, no punctuation other than the single dot.
- **Namespaced** — a prefix before the dot; downstream consumers group by prefix.
- **Non-prose** — "This Helm chart looks production-ready" cannot pass the regex.

Same shape applied to the `errors: list[WarningId]` field where errors carry structured IDs (e.g., `package_json.size_cap_exceeded`). Note: `errors` is the typed-exception-raised-during-probe-run list; `warnings` is the soft-degrade signal.

A future typed `WarningEnum` (Phase 2, owned by `IndexHealthProbe`) tightens the contract from "any string matching the pattern" to "any member of the enum."

## Tradeoffs

| Gain | Cost |
|---|---|
| Prose judgments fail at sub-schema validation — the "facts, not judgments" commitment gets a structural enforcement at the probe boundary, not just at the validator | New warning IDs require following the naming convention; ID collisions across probes are a maintenance concern (prefix discipline) |
| Phase 2's `IndexHealthProbe` can group warnings by prefix deterministically without parsing English | The pattern allows any ID matching the shape — a probe could ship `xx.yy` and pass validation; semantic discipline rests on review |
| The pattern is structural and lives in JSON Schema — no Python runtime check needed; the sub-schema validator carries the load | Adding a new prefix (e.g., `terraform.*`) is a probe-author convention, not a schema-enforced taxonomy |
| Minimum-friction adoption — probe authors don't enumerate every warning up-front; new IDs land naturally | Phase 2's promotion to typed enum is a schema-tightening migration; some Phase 1 IDs may need renaming to fit the enum |
| Composes with ADR-0004 — each sub-schema constrains its own `warnings[]` independently | The pattern itself is a string regex maintained in each sub-schema; a future global regex change is six-file PR |

## Consequences

- Every Phase 1 sub-schema declares the `warnings` (and `errors`, where structured) field as `array` of `string` with the `pattern` constraint applied.
- Probes that emit warnings construct IDs with the naming convention. Failing to do so trips sub-schema validation at envelope merge time; CLI exits 3.
- A canonical-list document under `docs/phases/01-context-gather-layer-a-node/` is not maintained in Phase 1; the IDs surface in `tests/unit/probes/test_*.py` fixture assertions. Phase 2 promotes to enum.
- Downstream consumers (Phase 2's `IndexHealthProbe`) treat warnings as opaque tags that group by their prefix. Phase 3+ recipes and the Trust-Aware gate can branch on specific IDs.
- `tests/unit/test_sub_schemas.py` asserts each sub-schema's `warnings` field carries the pattern constraint.
- The audit anchor (Phase 0 ADR-0004) implicitly records warnings via `raw/<probe>.json` dump — every warning ID is auditable.

## Reversibility

**High.** Removing the pattern constraint is a JSON edit in each sub-schema. Existing `repo-context.yaml` artifacts continue to validate (strings that matched the pattern still match `string`). The semantic loss is the structural defense — prose judgments become representable again. Phase 2's promotion to enum is the forward direction; reverting to free-form is the reverse.

## Evidence / sources

- `../final-design.md "Components"` — warnings field convention
- `../final-design.md "Shared blind spots considered" #4` — the critic-flagged shape
- `../final-design.md "Departures from all three inputs" #3` — the synthesizer departure
- `../final-design.md "Load-bearing commitments check" §2.2` — facts-not-judgments enforcement
- `../phase-arch-design.md "Data model"` — Python type definition
- `../phase-arch-design.md "Agentic best practices" "Typed state contracts at boundaries"` — minimum structural defense framing
- `../phase-arch-design.md "Integration with Phase 2 (next phase)"` — Phase 2's enum promotion path
- ADR-0004 — per-probe sub-schema strictness this rides on
- [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) — the commitment this enforces structurally
