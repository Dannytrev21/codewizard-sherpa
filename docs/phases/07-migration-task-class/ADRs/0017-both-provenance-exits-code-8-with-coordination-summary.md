# ADR-0017: `Both` provenance exits the CLI with code 8 and writes `coordination-summary.yaml`

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** exit-codes · operator-ergonomics · phase-boundary · adr-0042
**Related:** [0001](0001-no-multi-plugin-coordinator-in-phase-7.md), [0006](0006-adapter-dispatch-explicit-final-tuple.md), [production ADR-0042](../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md), [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)

## Context

When `assemble_provenance` returns `Both` (CVE present in both app and base layers), Phase 7's contract per [0001](0001-no-multi-plugin-coordinator-in-phase-7.md) is "produce evidence, do not sequence." But operators running `codegenie remediate <repo> --cve <id>` need to know **what just happened**: the workflow didn't fail; it didn't succeed; it produced typed evidence that awaits Phase 8's Planner.

None of the three lens designs proposed a clean operator-facing CLI shape for this terminal state. Performance-first's `MultiPluginCoordinator` ran child workflows (and was rejected). Security-first's `multiplugin/coordinator.py` watchdog ran in the background (and was rejected). Best-practices' "defer to Phase 8" position was correct but silent on operator ergonomics — `final-design.md §Departures from all three inputs #5` introduces the CLI shape: a dedicated exit code and a typed YAML artifact.

`final-design.md §Components §13` and `phase-arch-design.md §Component design §13` lock the contract: CLI exits with code 8, writes `coordination-summary.yaml`, emits `RequiresMultiPluginCoordination` event into the spanning log.

## Options considered

- **Option A — Exit code 0 with a warning log.** Treats `Both` as success. Operators may merge without noticing the pending coordination event. Rejected: violates "honest confidence" + "fail loud" (Rule 12).
- **Option B — Exit code 1 (generic failure).** Treats `Both` as a workflow failure. Operators see "failed" but no signal that this is a different class of failure (evidence is produced; nothing to fix). Rejected: muddles the failure taxonomy.
- **Option C — Reserve a dedicated exit code (8) for "requires multi-plugin coordination — awaiting Phase 8 Planner"; write a typed `coordination-summary.yaml`; emit `RequiresMultiPluginCoordination` event into the spanning log.** **Pattern:** Sum-type exit-code taxonomy + Event sourcing.

## Decision

Adopt **Option C.** When `assemble_provenance(...)` returns `Both`:

1. The migration plugin's subgraph emits exactly one `RequiresMultiPluginCoordination(workflow_id, app_record, base_record, summary_path, emitted_at)` event into the spanning event log (per [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)).
2. A `coordination-summary.yaml` is written to `.codegenie/coordination/<workflow_id>.yaml` with Pydantic-validated shape (`extra="forbid"`). Provisional fields: `workflow_id`, `cve_id`, `app`, `base`, `proposed_plugin_routes`, `awaiting: phase_8_planner`, `schema_version: "phase-7-0"`. Exact schema deferred to first implementation story (Open Question §1 in arch spec).
3. The CLI exits with code **8** — reserved across the project for "requires multi-plugin coordination — awaiting Phase 8 Planner."
4. The orchestrator returns `Applicability.PendingCoordination` to its caller.
5. No PR is opened. No Phase-7-owned coordinator runs. Phase 8's Planner consumes the event when Phase 8 lands.

A complementary CLI subcommand `codegenie list-coordination-candidates` walks `.codegenie/events/spanning/*.jsonl.zst`, filters on `kind == "requires_multi_plugin_coordination"`, and prints a YAML or table view — the pre-Phase-8 operator-visibility surface ([0001](0001-no-multi-plugin-coordinator-in-phase-7.md) §Consequences).

## Tradeoffs

| Gain | Cost |
|---|---|
| Operators see a distinct exit code (8) immediately and know this is "pending coordination," not "failure" — fail-loud + honest-confidence preserved | Exit code 8 becomes a reserved value across the project; future task classes that want their own "pending X" exit code must coordinate with this allocation |
| `coordination-summary.yaml` is the operator-readable handoff: one file, typed Pydantic, `extra="forbid"`, schema-versioned | The exact field shape is provisional (Open Question §1); Phase 8 may need to extend it. Mitigated: `schema_version: "phase-7-0"` field + Phase 8 introduces `"phase-8-0"` if needed; existing reads branch on version |
| The `RequiresMultiPluginCoordination` event in the spanning log is the Phase-8 contract surface — Phase 8 Planner reads it cold, no Phase-7 state to reconcile | The event accumulates unread for ~3 months until Phase 8 lands; mitigation is the `codegenie list-coordination-candidates` CLI + the `_index.tsv` rollup (Gap 5) |
| The `.codegenie/coordination/<workflow_id>.yaml` write is append-style (no overwrite), with `<workflow_id>` ensuring uniqueness per workflow | If a workflow re-runs with the same `<workflow_id>` (unlikely; `WorkflowId` is per-invocation), the write overwrites the previous summary — mitigated by `WorkflowId` newtype + per-invocation uniqueness |
| The CLI's `--help` documents exit code 8 explicitly; operators learn the taxonomy from `codegenie remediate --help` | The CLI surface grows by one exit code + one subcommand (`list-coordination-candidates`); both are small and well-named |

## Pattern fit

Implements **Sum-type exit-code taxonomy** (toolkit §Operability — exit codes are a typed surface, not a free-for-all): `Code.SUCCESS=0`, `Code.GENERIC_FAILURE=1`, ..., `Code.REQUIRES_MULTI_PLUGIN_COORDINATION=8` (the value 8 picked deliberately for memorability and to leave 2–7 for future generic-failure-subkinds). Also instantiates **Event sourcing** ([production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)) — the spanning log is the source of truth; the YAML summary is a projection consumers can read. Mirrors [0001](0001-no-multi-plugin-coordinator-in-phase-7.md)'s overall "produce evidence, do not sequence" position.

## Consequences

- The CLI's exit-code constants module (e.g., `src/codegenie/cli/exit_codes.py`) gains `Code.REQUIRES_MULTI_PLUGIN_COORDINATION = 8`. Documented in `--help`.
- `RequiresMultiPluginCoordination` event variant lives at `src/codegenie/primitives/vuln_provenance/events.py` (typed Pydantic per ADR-0034).
- `coordination-summary.yaml` schema is provisional, `schema_version: "phase-7-0"`, Pydantic-validated, `extra="forbid"`. Exact fields nailed down in first implementation story (Open Question §1).
- A goldens fixture `tests/golden/coordination-summary/both-app-direct-plus-base-image.yaml` locks the operator-readable shape across changes.
- `codegenie list-coordination-candidates [--since DATE] [--format yaml|table]` subcommand walks the spanning log and prints pending events. Default `--format=yaml` for parseability; `--format=table` for at-a-glance.
- A complementary writer appends one row to `.codegenie/coordination/_index.tsv` per `Both` event (Gap 5 mitigation in arch spec) — the operator's portfolio-friendly index until Phase 13.5's operator portal lands.
- Property test `test_both_always_emits_coordination.py` asserts: for every workflow where `assemble_provenance` returns `Both`, the spanning log contains exactly one `RequiresMultiPluginCoordination` event AND the process exits code 8 AND `coordination-summary.yaml` is written.
- E2E test `tests/e2e/test_both_provenance_emits_coordination_event_e2e.py` (`@pytest.mark.phase07_e2e`) exercises the full path on a fixture with CVEs in both layers — **no PR is opened**, asserting the Phase-7-stops-here behavior.
- Phase 8's Planner inherits the contract: read `.codegenie/events/spanning/*.jsonl.zst`, filter on `kind=="requires_multi_plugin_coordination"`, project. The `app_record` and `base_record` fields are typed `AppKind` + `BaseKind` discriminated unions — Phase 8 routes without re-parsing SBOMs.

## Reversibility

**Low.** Once Phase 8's Planner is built against the exit-code-8 / event / YAML contract, changing any of these would force Phase 8 (and Phase 11 merge-gate) to migrate. The `schema_version` field gives forward-compatibility within the YAML; the exit-code value is harder to change (operators' scripts depend on it). The contract-style golden fixture makes drift visible at every PR.

## Evidence / sources

- `../final-design.md §Goals` ("`Both` provenance variant produces evidence, not coordination"), §Synthesis ledger departure #5 (exit code 8) + departure #6 (list-coordination-candidates CLI), §Data flow "One `Both`-variant slice"
- `../phase-arch-design.md §Component design §13` (`RequiresMultiPluginCoordination` event + `coordination-summary.yaml` writer), §Component design §14 (`codegenie list-coordination-candidates` CLI), §Scenarios C (Both variant — exit code 8), §Gap 2 (`coordination-summary.yaml` schema provisional), §Gap 5 (events accumulate unread)
- `../critique.md §Cross-design observations` (`Both` ownership disagreement)
- [Phase 7 ADR-0001 — No `MultiPluginCoordinator` in Phase 7](0001-no-multi-plugin-coordinator-in-phase-7.md)
- [production ADR-0042 — Multi-plugin coordination for `Both` workflows](../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md)
- [production ADR-0034 — Event sourcing canonical primitive](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)
