# ADR-0003: `ObjectiveSignals` widened by four optional fields; `ALLOWED_BINARIES` and egress allowlist extended

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** phase5-contract · signals · sandbox · allowlist · additive-seam
**Related:** [ADR-0001](0001-six-named-additive-seams-and-adr-0028-amendment.md), [ADR-0008](0008-dive-efficiency-advisory-only.md), [ADR-0009](0009-contract-surface-snapshot-canary.md), [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md), [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)

## Context

Phase 7 introduces four new gate-time signals: `dive` (advisory size/efficiency), `shell_presence` (strict-AND: no `/bin/sh` in the runtime layer), `shell_invocation_trace` (strict-AND: no runtime shell invocation), and `base_image` (informational: pre-image manifest digest). All four are read by Phase 5's `StrictAndGate.evaluate` and feed Phase 3's `TrustScorer.score` — both of which iterate the `ObjectiveSignals` Pydantic model (`phase-arch-design.md §Component 8`, `§Data model §Contracts`).

The signals also require two host-side allowlist extensions: the `docker` and `dive` binaries must be on Phase 0's `ALLOWED_BINARIES` list to subprocess-launch from Phase 5's sandbox chokepoint; `cgr.dev` and `docker.io` must be on Phase 5's egress allowlist for the Docker daemon's image pulls.

`[S]`'s alternative — Phase 5 rootfs bump of +350–600 MB to include buildx, dive, dockerfile-parse, cosign, image-runner — was rejected by the critic (`critique.md §security.4`) and the synthesizer (`final-design.md §Conflict-resolution row 6`) on commitments-fit grounds (`CLAUDE.md` "Single Python project, no services") and Phase 5's chokepoint design. The remaining surface is the four-field widening plus two allowlist extensions, bundled into a single ADR because they all derive from Phase 5's seam.

The widening is *additive*: each new field defaults to `None`. Phase 5's `StrictAndGate.evaluate` iterates populated optional fields; Phase 3's `TrustScorer.score` reads only the fields it knows about. The contract-surface snapshot (ADR-0009) captures the Pydantic schema diff in the same PR.

## Options considered

- **Fork `ObjectiveSignals` into `DistrolessObjectiveSignals` parallel to the vuln one.** Zero edit to Phase 5; doubled gate-evaluation logic; Phase 8 inherits two signal models to merge. Rejected on the strict-zero-edit-alternative argument (`final-design.md §"Departures #5"`).
- **Use a generic `extras: dict[str, Any]` escape hatch on `ObjectiveSignals`.** Phase 5's existing model would not need new typed fields. Breaks the `extra="forbid"` typed-contract discipline (production ADR-0008 + `CLAUDE.md` rule "Typed state contracts at every boundary").
- **Rootfs bump (`[S]`).** +350–600 MB; new daemon dependencies; vetoed on `CLAUDE.md`.
- **Four optional-`None` fields + two allowlist additions (the synthesizer's pick).** One additive Pydantic widening; `extra="forbid"` discipline preserved; default-`None` keeps existing serialized payloads + existing `StrictAndGate.evaluate` invocations byte-identical when the new signals aren't populated.

## Decision

Edit three Phase 0–6 files additively, all in the Phase 7 PR alongside the regenerated contract-surface snapshot:

1. `src/codegenie/sandbox/signals/models.py` — add `dive | shell_presence | shell_invocation_trace | base_image: ... | None = None` as four optional fields on `ObjectiveSignals`. Defaults are `None`; existing callsites are byte-identical when the fields are unpopulated.
2. `src/codegenie/sandbox/host/allowed_binaries.py` — append `"docker"`, `"dive"` to the sorted list.
3. `src/codegenie/sandbox/host/egress_allowlist.py` — append `"cgr.dev"`, `"docker.io"` to the sorted list.

All three additions are captured in this single ADR (called ADR-P7-002 in the architecture spec) and bundled in the same PR as the contract-surface snapshot regeneration.

## Tradeoffs

| Gain | Cost |
|---|---|
| One typed `ObjectiveSignals` shared by both task classes — Phase 8's supervisor reads one model, not two | Three Phase 5 source files receive additive edits; the literal "only new files" reading of the roadmap is qualified (this is the cost ADR-0001 pays for) |
| `extra="forbid"` discipline preserved; `dive --json` schema upstream-break still fails loudly via Pydantic `ValidationError` on the `DiveSignal` model | The `ObjectiveSignals.model_json_schema()` byte string changes — contract-surface snapshot (ADR-0009) drifts and must be regenerated in the same PR |
| Allowlist additions are sorted-list appends — diff is one-line per file, trivially auditable | Future signal additions (Phase 8/13/15) follow this exact pattern — each one is another ADR; the discipline holds only if each future author writes one |
| Existing Phase 3/4/5/6 consumers of `ObjectiveSignals` are byte-identical when called against vuln workflows (where the new fields are `None`) — verified by `tests/integration/test_objective_signals_widening_compat.py` (Gap 3 mitigation) | The widening is "additive" only if every existing consumer handles `None` for the new fields — never automatically true; requires the explicit compat test |

## Consequences

- The contract-surface snapshot (ADR-0009) diff for this PR includes `ObjectiveSignals.model_json_schema()`, `ALLOWED_BINARIES` sorted list, egress allowlist sorted list — three diffs, one ADR.
- `tests/integration/test_objective_signals_widening_compat.py` (phase-arch-design §Gap 3) is the *mechanical* enforcement of "additive" — runs Phase 3's `TrustScorer.score` and Phase 5's `StrictAndGate.evaluate` against fixtures with all four new fields populated and against fixtures with all four `None`. Both must succeed.
- Phase 5's `StrictAndGate.evaluate` skip-when-`None` behavior remains intact; gate verdicts for vuln workflows are byte-identical pre- and post-Phase 7.
- Phase 8's supervisor reads `ObjectiveSignals` from the gate audit chain for ROI scoring — one model covers both task classes.
- Phase 13 (calibration) decides whether to harden `dive` to strict-AND or any of the new signals to a different policy (ADR-0008 in this phase records the advisory-only stance).
- Phase 9's Temporal worker imports the widened `ObjectiveSignals` — schema-version pin (Phase 5's existing `Literal`) covers checkpoint migration.

## Reversibility

**Medium.** Reverting the four-field widening requires Phase 8 to ship a parallel `DistrolessObjectiveSignals` or merge in retrospect — both Phase 8 + Phase 13 inherit churn. Reverting the allowlist additions is one-line per file but breaks every fixture that uses the `docker buildx` toolchain. Possible but not free; the asymmetry is the point of the named-seam discipline.

## Evidence / sources

- `../final-design.md §Goals#15` (public surface enumeration)
- `../final-design.md §Conflict-resolution row 5–6` (rootfs bump rejected)
- `../final-design.md §"Departures #3 ADR-P7-002"` (bundle scope)
- `../phase-arch-design.md §Component 8` (signal collectors)
- `../phase-arch-design.md §Component 13 ADR-P7-002` (file-by-file diffs)
- `../phase-arch-design.md §Gap 3` (widening compat test)
- `../critique.md §security.4` (the rootfs-bump rejection)
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) — Trust score uses objective signals only
- [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md) — microVM sandbox isolation
