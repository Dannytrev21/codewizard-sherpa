# ADR-0005: `schema_version: Literal["v0.6.0"]` — static, not dynamic `blake3(model_json_schema())`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** state · schema · durability
**Related:** [ADR-0002](0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md), [ADR-0006](0006-audited-sqlite-saver-per-workflow-fsync.md)

## Context

The checkpointer persists `VulnLedger` blobs to disk. On resume, the rehydration path must detect schema drift (a new field, a renamed field, a removed field) and refuse to silently load a stale blob into a current `VulnLedger`. The three lenses disagreed on how to encode the version:

- **Security's `schema_version = blake3(canonical_sorted_json(VulnLedger.model_json_schema()))`** is content-addressed: any field change automatically changes the version, no manual bump needed. `critique.md §security-hidden-2` killed it: Pydantic v2 has changed `model_json_schema()` output between minor versions (`2.5 → 2.6` reorderings, `2.7` adding `$defs` differently). A `pip install --upgrade pydantic` would flip the schema version on every checkpoint and refuse to resume every in-flight workflow on every developer's machine after a routine Pydantic bump.
- **Best-practices' `schema_version: Literal["v0.6.0"]`** is a static string the engineer bumps manually when they change the shape. CI fixture round-trips catch accidental field changes.
- **Performance and the original lenses left it unspecified** — implicitly "v1" with no migration plan.

The exit-criterion-relevant property is that schema drift is *detected loudly* and that the detector itself is not noisy. A detector that flips on every Pydantic minor bump is worse than no detector — it trains operators to `chmod 600` their refusal and move on.

## Options considered

- **Dynamic `blake3(model_json_schema())`.** Auto-detects every field change. Flips spuriously on Pydantic library bumps. Triggers `SchemaDrift` for the wrong reason.
- **Static `Literal["v0.6.0"]`.** Engineer-bumped. Discipline-dependent: a forgotten bump silently passes a drifted blob. CI fixtures under `tests/fixtures/checkpoints/v0.6.0/` guard against unintentional shape changes.
- **Library version string (`pydantic.__version__`).** Wrong granularity; ties schema versioning to library lifecycle.
- **No version, validate-on-read.** Pydantic's `extra="forbid"` catches most adds; renames and removals slip through silently.

## Decision

`VulnLedger.schema_version` is declared as `schema_version: Literal["v0.6.0"]` — a static string literal. On resume, `AuditedSqliteSaver.aget_tuple` reads the persisted `schema_version` from the JSON blob and compares it to the current code's literal; mismatch raises `SchemaDrift` and refuses to resume. The only forward path is `codegenie loop migrate-checkpoint --from <old> --to <new>`. Phase 6 ships **no** registered migrations (only `v0.6.0` exists); the command exists to record the contract.

Two CI gates back the discipline:

1. `tests/fixtures/checkpoints/v0.6.0/*.json` — hand-authored known-good `VulnLedger` blobs that round-trip through `VulnLedger.model_validate`; any field rename or removal breaks them.
2. `tests/graph/test_pydantic_no_any.py` — asserts the model contains no `Any`, `dict[str, Any]`, or untyped `Mapping`; combined with `extra="forbid"`, this means any new field is a typed, intentional addition.

## Tradeoffs

| Gain | Cost |
|---|---|
| Schema-drift detection does not flip on routine library bumps — a Pydantic upgrade is *not* a forced migration | Engineer discipline carries the bump: a missed `v0.6.0 → v0.7.0` literal change silently lets a drifted blob load |
| `codegenie loop migrate-checkpoint` is a one-time deliberate operator step, not an auto-migration that could corrupt state | The migration registry under `graph/migrations/` is empty in v0.6.0 — the first phase that adds a field (likely Phase 7 or 8) writes the first migration; the shape is unspecified by design |
| CI fixtures catch unintentional shape changes at PR time, not at production resume time | Maintaining a small fixture set is one more thing the implementer can forget; the fixture-checkpoint round-trip test is the canary |
| Schema-version semantics are explicit (`Literal["v0.6.0"]`) rather than implicit (a hash that could mean anything) | A future "minor field addition that's safe to load on old readers" cannot be expressed — every schema change requires a version bump and a migration entry, even backward-compatible ones |

## Consequences

- The `v0.6.0` literal is the **public contract version** for Phase 6's persisted state. Phase 7's `DistrolessLedger` ships its own literal (`v0.7.0-distroless` per `phase-arch-design.md §Integration with Phase 7`) — task-class versioning is parallel, not shared.
- The migration command and the empty migration registry are scaffolding Phase 6 ships so that Phase 7+ has a place to add the first real migration without re-designing the seam.
- The exported HITL contract (`docs/contracts/hitl-v0.6.0.json`) uses the same version literal to keep the cross-phase contract aligned with the state-ledger contract.
- `SchemaDrift` is a hard halt — `cli/loop.py` exit code 13 (`phase-arch-design.md §CLI design`); operators see a clear "migrate or abort" prompt.
- A reviewer who adds a field to `VulnLedger` without bumping the literal must update CI fixtures, which breaks the round-trip test loudly — the discipline is enforced indirectly.

## Reversibility

**Medium.** Switching to a dynamic version scheme (e.g., on Pydantic minor bumps' output stabilizing) is mechanical — change the `schema_version` field type, update the checkpointer's check, and re-bake the fixtures. Switching to *no* versioning is easy but unsafe; was the explicit rejection. The migration registry's empty state means there's no historical baggage to carry forward.

## Evidence / sources

- [`../final-design.md` §Goals row 11 "VulnLedger schema-version pin + drift detection"](../final-design.md)
- [`../final-design.md` §Synthesis ledger row 10 "schema_version encoding"](../final-design.md)
- [`../phase-arch-design.md` §Component 1 "VulnLedger" — internal structure](../phase-arch-design.md)
- [`../critique.md` §security-hidden-2](../critique.md) — the Pydantic minor-bump flip that killed dynamic blake3
- Pydantic v2 release notes (2.5, 2.6, 2.7 `model_json_schema()` output changes)
