# ADR-0001: `consumes_peer_outputs` class attribute + frozen-snapshot positional arg

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** coordinator · probe-contract · chokepoint-preservation · peer-data · synthesizer-departure
**Related:** [Phase 0 ADR-0005](../../00-bullet-tracer-foundations/ADRs/0005-coordinator-async-from-day-one.md), [Phase 0 ADR-0007](../../00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-snapshot.md), [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md), [production ADR-0006](../../../production/adrs/0006-deterministic-gather-no-llm.md), ADR-0011

## Context

`IndexHealthProbe` (B2) is the load-bearing freshness oracle in Phase 2: per `final-design.md §"Components" #2 (IndexHealthProbe)`, it rolls up six per-domain views (SCIP, SBOM, CVE, semgrep, gitleaks, runtime_trace) from the actual outputs of upstream probes — not from a side cache, not from disk. To do that it must, *at run time*, read the post-sanitizer outputs of every probe it depends on.

The best-practices lens proposed adding `peer_outputs: Mapping[str, ProbeOutput]` to `ProbeContext` as the one Phase-0 dataclass extension Phase 2 makes (`design-best-practices.md "Components" §2.2`). The critic dismantled that proposal (`critique.md "Attacks on the best-practices design"` #3): `ProbeContext`'s shape was deliberately frozen by Phase 0 ADR-0007 and Phase 1 made one ADR-gated extension (`parsed_manifest`); mutating the dataclass again — and exposing *other probes' outputs* through it — changes the coordinator's contract with every probe, not just B2. The CLAUDE.md "extension by addition" invariant ("never edits to existing probes or the coordinator") is structurally violated for 99% of probes that don't need the field. A second Phase-0 mutation also normalizes ADR-gated coordinator edits as routine — the precedent matters more than the diff.

None of the three lenses proposed an opt-in mechanism keyed off the probe itself. It surfaced as a synthesizer departure (`final-design.md "Departures from all three inputs"` #2).

## Options considered

- **`ProbeContext.peer_outputs: Mapping` [B].** One new optional field on the Phase-0 dataclass. Every probe sees the type even if 26 of 27 never touch it. Sets the precedent that ADR-gated coordinator surface mutations are routine.
- **Internal coordinator state, no contract surface.** B2 reaches back into coordinator internals to read the peer-output table. Easiest diff; couples B2 to the coordinator's private fields; defeats the structural-symmetry-with-other-probes goal that made B2 a `Probe` in the first place.
- **`consumes_peer_outputs: bool = False` class attribute + frozen-snapshot third positional arg [synth].** B2 declares the opt-in on the class; coordinator inspects the attribute at registration time; only probes that declare `True` receive the third positional argument. `ProbeContext`'s public field set is unchanged. 99% of probes see the original two-arg signature. One ADR-gated branch in `Coordinator.dispatch`.

## Decision

**Add an optional class attribute `consumes_peer_outputs: ClassVar[bool] = False` to `Probe` (`src/codegenie/probes/base.py`).** The default leaves the existing two-arg `run(snapshot, ctx)` signature untouched for every Phase 0 and Phase 1 probe. `IndexHealthProbe` declares `consumes_peer_outputs = True`. At dispatch time the coordinator inspects the attribute via `inspect.signature` once per registration and selects the call shape: probes opting in receive a **third positional argument `peer_outputs: FrozenMapping[str, ProbeOutput]`** containing the post-sanitizer outputs of every peer probe that has completed in this gather.

- **Snapshot is frozen.** Constructed once per gather, after every Wave 1–4 peer probe has emitted a sanitized `ProbeOutput`; passed by reference to `IndexHealthProbe.run()`; never mutated after construction. Built via `types.MappingProxyType` wrapping `dict[str, ProbeOutput]` and the contained `ProbeOutput` is already a Pydantic model with frozen-config.
- **Post-sanitizer.** The snapshot reflects the bytes that will be written to YAML, not pre-sanitizer drafts. Passes 1–5 of `OutputSanitizer` run before snapshot construction.
- **Coordinator-private.** The snapshot is built in `Coordinator.dispatch`; it does not appear on `ProbeContext`. Probes that don't declare `consumes_peer_outputs = True` cannot accidentally depend on peer outputs.
- **One branch in dispatch.** The Coordinator branch reads `getattr(probe, "consumes_peer_outputs", False)` and chooses the two- or three-arg call. No new IPC, no new threading, no new lifecycle.

## Tradeoffs

| Gain | Cost |
|---|---|
| `ProbeContext`'s public field set is unchanged in Phase 2 — Phase 0 ADR-0007's frozen-snapshot contract holds | A class-attribute opt-in is one more thing probe authors must remember when they need peer data; documentation lives in the Probe ABC docstring |
| 99% of probes see the original two-arg signature — no defensive `if peer_outputs is None` branch in every probe | The Coordinator gains one signature-dispatch branch; tested by `tests/unit/coordinator/test_peer_output_binding.py` |
| Snapshot is frozen, post-sanitizer — B2 sees the bytes that hit disk, not transient drafts | Snapshot construction is per-gather O(N) over peer outputs; immaterial at Phase 2 budgets but bench-tracked |
| The Skill-author / probe-author mental model stays simple — `consumes_peer_outputs` is opt-in, not opt-out | A probe that should opt in but forgets gets `TypeError` at first call — fail-loud, but the signal is at the wrong layer |
| `inspect.signature` is called once at registration, not per call — no hot-path reflection | Adds a startup-time check that grows linearly with probe count; insignificant at 27 probes, watch at 100+ |
| Future probes needing peer data (e.g., Phase 5's RuntimeTrace orchestrator) reuse the same seam without further ABC changes | Establishes "peer-output binding" as an enduring coordinator capability; future-proofing this is Phase 14's concern |

## Consequences

- `src/codegenie/probes/base.py` gains `consumes_peer_outputs: ClassVar[bool] = False`. No other field change.
- `src/codegenie/coordinator.py` gains one branch: `if getattr(probe, "consumes_peer_outputs", False): peer_outputs_snapshot = _freeze_peer_outputs(self._completed); await probe.run(snapshot, ctx, peer_outputs_snapshot)` (sketch).
- `IndexHealthProbe.run()` has the three-arg signature; no other Phase 2 probe declares `consumes_peer_outputs = True`.
- `tests/unit/coordinator/test_peer_output_binding.py` asserts: probes without the attribute see two-arg call; B2 receives the frozen snapshot; the snapshot is immutable at the Python type-system level (`MappingProxyType` raises on mutation); `ProbeContext` is unchanged.
- The `_freeze_peer_outputs` helper lives in `coordinator/` next to `parsed_manifest_memo.py` (`Phase 1 ADR-0002`). Same shape — per-gather, in-process, never serialized.
- Phase 5's RuntimeTraceProbe (C4) lands as a probe that may itself declare `consumes_peer_outputs = True` if it needs to bind against the SBOM/CVE snapshots; the seam is ready.
- The Phase-0 audit anchor event family is preserved unchanged; no new audit event is required for peer-output binding (B2's own audit record captures its peer-output dependency set via `requires`).

## Reversibility

**Medium.** The class attribute and dispatch branch are mechanically removable: delete `consumes_peer_outputs` from `Probe`, delete the branch in `Coordinator.dispatch`, change `IndexHealthProbe.run()` to a two-arg signature and refactor it to read peer outputs from a different source. The hard part is the *different source* — B2 needs the data, so something must replace the seam. Replacing with `ProbeContext.peer_outputs` (the rejected option) is the most likely path; replacing with internal coordinator coupling is structurally worse. Reversal cost is owning the consequence: another seam must be designed.

## Evidence / sources

- `../final-design.md "Goals (concrete, measurable)"` Probe-contract-preserved bullet — the binding spec
- `../final-design.md "Components" #12 Coordinator — peer-output binding` — interface
- `../final-design.md "Conflict-resolution table" D6` — the resolution
- `../final-design.md "Departures from all three inputs" #2` — synthesizer call-out
- `../phase-arch-design.md "Executive summary"` move #2 — the framing
- `../phase-arch-design.md "4+1 architectural views" "Logical view"` — the class-diagram annotation
- `../critique.md "Attacks on the best-practices design"` #3 — the dismantling
- [Phase 0 ADR-0007](../../00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-snapshot.md) — the frozen-contract this preserves
- [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md) — the prior pattern for an ADR-gated coordinator extension that this one is consciously narrower than
