# Phase 07 — Add migration task class (Chainguard distroless): ADRs

Architecture Decision Records for Phase 7, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

Phase 7 is the phase that *proves* extension-by-addition for the codewizard-sherpa contract surface. The central decision (ADR-0001) amends production [ADR-0028](../../../production/adrs/0028-task-class-introduction-order.md) to define "extension by addition" as **behavior-preserving additive extension** and enumerates six named additive seams (ADR-0002 through ADR-0007). Two permanent canaries (ADR-0009 contract-surface snapshot, ADR-0014 regression-suite wall-clock) mechanically enforce the discipline across every later phase. The remaining ADRs (0008, 0010–0013) record the load-bearing component-level decisions whose alternatives were viable and whose reasoning future readers will want.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec with 4+1 views, component design, edge cases, testing strategy, harness engineering, gap analysis.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs (performance, security, best-practices) via Graph-of-Thought.
**Devil's-advocate critique:** [critique.md](../critique.md) — the attacks the synthesis had to answer.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with (amends ADR-0028; honors ADR-0007, ADR-0008, ADR-0011, ADR-0012, ADR-0014, ADR-0022).

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-six-named-additive-seams-and-adr-0028-amendment.md) | Six named additive seams across Phase 0–6, plus an amendment to ADR-0028 | extension-by-addition · contract-surface · adr-0028 · load-bearing |
| [0002](0002-register-gate-probe-new-registry.md) | `@register_gate_probe` — a new registry module, not an `applies_to_lifecycle` field on the `Probe` ABC | probes · phase2-contract · gate-lifecycle · new-file-only |
| [0003](0003-objective-signals-widening-and-allowlists.md) | `ObjectiveSignals` widened by four optional fields; `ALLOWED_BINARIES` and egress allowlist extended | phase5-contract · signals · sandbox · allowlist · additive-seam |
| [0004](0004-fallback-tier-task-type-kwarg.md) | `FallbackTier.run` gains `task_type: str \| None = None` kwarg | phase4-contract · planner · task-class-routing · additive-seam |
| [0005](0005-openrewrite-rewrite-docker-deferred.md) | OpenRewrite `rewrite-docker` deferred to Phase 15 — handrolled `dockerfile-parse` engine only | recipes · openrewrite · deferred · simplicity-first |
| [0006](0006-runtime-trace-probe-stub-kept-forever.md) | Phase 2 `RuntimeTraceProbe` stub kept in place forever as a no-op | phase2-contract · probes · backward-compatibility · pure-preservation |
| [0007](0007-recipe-engine-literal-extended-with-dockerfile.md) | `Recipe.engine` `Literal` extended additively with `"dockerfile"` | phase3-contract · recipes · literal-extension · additive-seam |
| [0008](0008-dive-efficiency-advisory-only.md) | `dive_efficiency` ships advisory-only — `passed=True` always; not a strict-AND gate signal | gate-signals · facts-not-judgments · trust-score · phase13-calibration |
| [0009](0009-contract-surface-snapshot-canary.md) | Permanent contract-surface snapshot canary replaces one-shot diff gate and BLAKE3 source freeze | ci · contract-surface · extension-by-addition · permanent-canary · enforcement |
| [0010](0010-credentials-via-docker-config-no-secretd-daemon.md) | Credentials live in operator's `~/.docker/config.json` — no `codegenie-secretd` daemon | credentials · security · claude-md-veto · simplicity-first |
| [0011](0011-distroless-ledger-parallel-to-vuln-ledger.md) | `DistrolessLedger` ships parallel to `VulnLedger` — Phase 8 inherits the merge (ADR-0022 strike two) | state · ledger · three-strikes · phase8-debt |
| [0012](0012-parallel-cli-verbs-no-shared-dispatcher.md) | `codegenie migrate` ships as a parallel CLI verb — no shared dispatcher; Phase 8 unifies | cli · dispatcher · phase8-integration · extension-by-addition |
| [0013](0013-shell-trace-runs-gate-time-in-phase5-chokepoint.md) | `ShellInvocationTraceProbe` runs at gate time inside Phase 5's sandbox chokepoint — 30 s strace budget | probes · gate-time · sandbox · strace · threat-model |
| [0014](0014-regression-suite-wall-clock-canary.md) | Regression-suite wall-clock canary — permanent perf gate, never retired | ci · performance · permanent-canary · enforcement |

## Mapping to the architecture's ADR-P7-NNN identifiers

The architecture spec (`phase-arch-design.md`) refers to the six named additive seams by `ADR-P7-001` through `ADR-P7-006`, plus `ADR-P7-007` for the advisory `dive_efficiency` decision. They land in this phase folder as:

| Architecture id | This phase file | Decision |
|---|---|---|
| ADR-P7-001 | [ADR-0002](0002-register-gate-probe-new-registry.md) | `@register_gate_probe` new registry module |
| ADR-P7-002 | [ADR-0003](0003-objective-signals-widening-and-allowlists.md) | `ObjectiveSignals` widening + `ALLOWED_BINARIES` + egress allowlist |
| ADR-P7-003 | [ADR-0004](0004-fallback-tier-task-type-kwarg.md) | `FallbackTier.run(task_type=)` additive kwarg |
| ADR-P7-004 | [ADR-0005](0005-openrewrite-rewrite-docker-deferred.md) | OpenRewrite `rewrite-docker` deferred |
| ADR-P7-005 | [ADR-0006](0006-runtime-trace-probe-stub-kept-forever.md) | Phase 2 `RuntimeTraceProbe` stub preserved |
| ADR-P7-006 | [ADR-0007](0007-recipe-engine-literal-extended-with-dockerfile.md) | `Recipe.engine` `Literal` += `"dockerfile"` |
| ADR-P7-007 | [ADR-0008](0008-dive-efficiency-advisory-only.md) | `dive_efficiency` advisory-only |

The other ADRs in this phase (0001 = the six-seam discipline + ADR-0028 amendment; 0009 = contract-surface canary; 0010 = `~/.docker/config.json` credentials; 0011 = parallel `DistrolessLedger`; 0012 = parallel CLI verbs; 0013 = gate-time strace; 0014 = regression-suite wall-clock canary) are load-bearing component or harness-engineering decisions that the architecture spec discusses in prose but did not pre-number.

## Conventions

- Filenames `NNNN-kebab-case-title.md`, zero-padded 4-digit, numbered locally per phase from 0001.
- Numbers are immutable — a superseded ADR keeps its number; the new ADR gets the next number with a cross-link.
- Production ADR refs use `../../../production/adrs/NNNN-*.md`.
- Sibling phase ADR refs use `[ADR-NNNN](NNNN-...md)` within this directory.
- Cross-phase refs (e.g., to Phase 6) use `../../06-sherpa-state-machine/ADRs/NNNN-*.md`.
- Status starts at **Accepted** for ADRs written from synthesized designs (the decision is the synthesizer's commitment); future amendments may add **Superseded by ADR-NNNN** entries.

## Decisions noted but not yet documented in arch / final-design

These are decisions the design *implies* or *flags as needing resolution before merge* but does not yet record as a load-bearing ADR. The implementer or the next architect pass should write them or surface them.

- **Workflow-id prefix scheme (`wf:vuln:<sha>` vs `wf:distroless:<sha>`).** Flagged in `phase-arch-design.md §Gap 1`. The prefix is what makes cross-task workflow-id collisions structurally impossible. Implementer should write a Phase-7 ADR (or amend ADR-0011 in this phase) that pins the exact scheme and the `tests/integration/test_chain_no_collision_across_tasks.py` invariant. ADR-worthy because Phase 8's supervisor uses the prefix as the dispatch key.
- **`cache_lock.py` cross-platform `flock(2)` abstraction.** Flagged in `phase-arch-design.md §Gap 2`. Phase 7 documents the buildkit + grype-DB + dockerfile-parse cache concurrency problem; the solution (a `pyfilelock` fallback + macOS BSD flock + Linux fcntl matrix) is sketched but not ADR'd. ADR-worthy if the implementer picks a non-trivial library dependency (`pyfilelock`) or invents a custom abstraction.
- **Strace sidecar pattern (`docker --pid=container:<candidate>`).** Flagged in `phase-arch-design.md §Gap 4`. ADR-0013 in this phase mentions the sidecar pattern but does not deeply justify it; the alternative (ENTRYPOINT-wrapper strace) has subtle PID-1 / signal-handling implications. If the implementer hits resistance from a reviewer who wants ENTRYPOINT-wrapper, the explicit ADR justifying the sidecar choice is the answer.
- **Buildx builder bootstrap (`docker buildx create --name codegenie-distroless`).** Flagged in `phase-arch-design.md §Gap 7`. The auto-create-or-reuse pattern is a small piece of operational discipline; the alternative (require operator to create the builder explicitly) is more conservative but has worse ergonomics. ADR-worthy if the implementer picks a non-obvious default.
- **Phase 8's supervisor verb name (`codegenie sherpa` vs alternative).** Phase 6 named `cli/sherpa.py` as the future supervisor home; Phase 7 did *not* coin the verb (ADR-0012 in this phase). Phase 8 owns this decision but the synthesizer's preference is to keep the `sherpa` namespace. Phase 8's ADR should record the final choice.
- **Phase 8's unification of `VulnLedger` and `DistrolessLedger` (ADR-0022 Three Strikes strike three).** Phase 7 explicitly defers (ADR-0011 in this phase). The third subgraph (Phase 14's continuous gather? Phase 15's recipe authoring?) is the trigger; whichever phase ships it owns the unification ADR.
- **OpenRewrite `rewrite-docker` re-evaluation in Phase 15.** Phase 7 defers (ADR-0005 in this phase). Phase 15's recipe-authoring work should ADR the final decision: return as a `RecipeEngine`, ship as an authoring-target intermediate, or permanently retire.
- **Production ADR-0028 amendment text.** This phase's ADR-0001 states the amendment; the *production* ADR-0028 file should receive the appended paragraph in the same Phase 7 PR. The implementer should ensure the cross-link from production ADR-0028 back to this phase's ADR-0001 is added when the amendment lands.
