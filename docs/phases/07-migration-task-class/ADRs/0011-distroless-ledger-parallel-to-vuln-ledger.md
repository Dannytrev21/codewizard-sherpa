# ADR-0011: `DistrolessLedger` ships parallel to `VulnLedger` — Phase 8 inherits the merge (ADR-0022 strike two)

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** state · ledger · three-strikes · phase8-debt
**Related:** [ADR-0012](0012-parallel-cli-verbs-no-shared-dispatcher.md), [production ADR-0022](../../../production/adrs/0022-per-subgraph-topology.md), Phase 6 [ADR-0002](../../06-sherpa-state-machine/ADRs/0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md), Phase 6 [ADR-0005](../../06-sherpa-state-machine/ADRs/0005-static-schema-version-literal-pin.md)

## Context

Phase 6 shipped `VulnLedger` as the single Pydantic-typed state contract for the vuln loop (`schema_version: Literal["v0.6.0"]`, `extra="forbid"`, `frozen=False` with a runtime `id()`-diff hook). Phase 7's distroless loop needs an analogous state contract with the same discipline (`phase-arch-design.md §Component 6`). The three lens designs took three positions on ledger architecture (`final-design.md §Conflict-resolution row 15`):

- `[P]` — new `MigrationLedger` parallel to `VulnLedger` with own closed `Literal`s.
- `[S]` — new `MigrationLoopState` *composed into* a unifying `LoopState`. The composition requires editing Phase 6's `state.py`.
- `[B]` — new `DistrolessLedger` parallel to `VulnLedger`; ADR-0022 (Three Strikes) deferred.

Production ADR-0022 ("Per-subgraph topology — when to extract shared structure") is explicit: build the first two subgraphs as pure duplication; extract shared structure when a third subgraph reveals the pattern. **Three Strikes And You Refactor.** Vuln is strike one; distroless is strike two; the abstraction is deferred to Phase 8 or Phase 15 when the third subgraph (Language-Upgrade or similar) lands.

The critic acknowledged this is a real debt (`§performance.3`): two ledgers mean Phase 8's supervisor reads two schemas, and bumping either ledger's `Literal` is a two-place edit. The synthesizer accepts the debt explicitly (`final-design.md §Component-5 "Tradeoffs accepted"`, `§"Acknowledged debt Phase 8 inherits"`).

## Options considered

- **Unified `LoopState` composed from `VulnLoopState | MigrationLoopState` (`[S]`).** Requires editing Phase 6's `state.py` to add the discriminator + the union — a Phase 6 source edit not on the six-seam list (ADR-0001). Rejected.
- **Generic `BaseLedger` base class with subclasses.** Production ADR-0022 explicitly defers premature abstraction; the abstraction shape is wrong until a third subgraph proves it. Rejected at this phase.
- **Parallel `DistrolessLedger`, no shared base, Phase 8 unifies.** Production ADR-0022 honored verbatim; Phase 7 ships with explicit debt acknowledgement; the synthesizer's pick.

## Decision

`DistrolessLedger` ships as a sibling Pydantic `BaseModel` at `src/codegenie/graph/state_distroless.py`, structurally similar to `VulnLedger` (field-by-field mirror where shapes coincide), with its own `schema_version: Literal["v0.7.0"]` pin, its own `extra="forbid"` discipline, its own `frozen=False` + runtime `id()`-diff hook. No shared base class with `VulnLedger`. The `last_engine` `Literal` value sets differ deliberately: vuln has `"recipe"|"rag"|"phase4_llm"`; distroless has `"dockerfile_recipe"|"rag"|"phase4_llm"`. Phase 8's supervisor (or Phase 15, whichever lands first) owns the unification under production ADR-0022's "Three Strikes" rule.

## Tradeoffs

| Gain | Cost |
|---|---|
| Production ADR-0022 honored verbatim — premature abstraction avoided; the third subgraph will reveal the right shape | Phase 8 inherits the merge — supervisor must `model_validate_json` both schemas to determine `task_type` and dispatch |
| Each ledger is independently evolvable — bumping `VulnLedger.schema_version` to `v0.6.1` does not require a `DistrolessLedger` bump in lockstep | Two checkpoint-migration paths the moment either ledger's `Literal` bumps; cross-task ROI scoring requires Phase 8 to know both `last_engine` value sets |
| `DistrolessLedger` fields can deliberately differ where shapes diverge (e.g., `target_image_recommendation` is distroless-specific) — no forced commonality where the structures genuinely differ | Field-by-field mirror is a copy-paste-prone discipline; drift between the two ledgers must be caught by reviewer attention (no mechanical check) |
| Phase 8 will see *two* concrete subgraphs side-by-side and *can* pattern-match the shared vs distinct fields — the abstraction it ships will be informed, not guessed | If Phase 8 ships under time pressure, the unification may be skipped and the debt grows; Phase 15's "Three Strikes" prevents this from becoming permanent |

## Consequences

- `src/codegenie/graph/state_distroless.py` defines `DistrolessLedger` and `TargetImageRecommendation` as the two new Pydantic contracts; both `extra="forbid"`, `schema_version` literal-pinned.
- `tests/unit/graph/test_distroless_state.py` mirrors Phase 6's `tests/unit/graph/test_vuln_state.py` test pattern — `extra="forbid"` rejection, `id()`-diff hook fires on in-place mutation, `schema_version` pin asserted.
- The `wf:distroless:<sha>` workflow-id prefix differs from `wf:vuln:<sha>` (`phase-arch-design.md §Gap 1`) — Phase 8's supervisor uses the prefix as the dispatch key.
- `.codegenie/migration/checkpoints/<workflow_id>.sqlite3` lives in a different directory from vuln checkpoints — same `AuditedSqliteSaver` class, structurally impossible to collide on workflow_id.
- Phase 8's supervisor is the unification owner. If Phase 8 unifies, this ADR is superseded by a Phase 8 ADR; if Phase 8 punts further, Phase 15 owns the unification (ADR-0022 Three Strikes "fires" on the third subgraph).
- The two `last_engine` value sets (`"recipe"` vs `"dockerfile_recipe"`) are a *named* artifact of the deferred unification — Phase 8 sees the divergence and unifies.

## Reversibility

**Medium.** Unifying the ledgers post-hoc requires migrating persisted checkpoints (vuln-workflow SQLite files on operator machines) to a unified schema. Phase 9's Temporal lift is the natural point — checkpoints are recreated under the new substrate. Reversing earlier costs operator-side schema migrations; reversing later costs nothing (Phase 8/15 will pick the shape based on the third subgraph). The asymmetry favors letting Three Strikes fire naturally.

## Evidence / sources

- `../final-design.md §Conflict-resolution row 15` (parallel `DistrolessLedger`; Three Strikes deferred)
- `../final-design.md §Component 5 "Tradeoffs accepted"` ("Two ledgers (Phase 8 inherits the merge)")
- `../final-design.md §"Acknowledged debt Phase 8 inherits"`
- `../phase-arch-design.md §Component 6` (DistrolessLedger fields)
- `../phase-arch-design.md §Gap 1` (workflow_id prefix scheme)
- `../critique.md §performance.3` (the two-ledger debt)
- [production ADR-0022](../../../production/adrs/0022-per-subgraph-topology.md) — Per-subgraph topology / Three Strikes
- [Phase 6 ADR-0005](../../06-sherpa-state-machine/ADRs/0005-static-schema-version-literal-pin.md) — schema_version Literal pin
