# Phase 05 — Sandbox + Trust-Aware gates: ADRs

Architecture Decision Records for Phase 5, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-two-chokepoint-sandbox-seam.md) | Two-chokepoint sandbox seam — `run_in_sandbox` and `SandboxClient` coexist | architecture · sandbox · gates · phase-boundary |
| [0002](0002-additive-prior-attempts-kwarg.md) | Additive `prior_attempts` kwarg on Phase 3 `ApplyContext` and Phase 4 `FallbackTier.run` | retry · phase-boundary · contract · extension-by-addition |
| [0003](0003-trustscorer-extension-via-signal-kind-registry.md) | Extend Phase 3 `TrustScorer` via open signal-kind registry; do not replace | trust · extension-by-addition · registry · phase-boundary |
| [0004](0004-dind-default-macos-with-gate-isolation-class.md) | DinD is the macOS default; `gate_isolation_class` annotation propagates | sandbox · macos · isolation · downstream-signal |
| [0005](0005-phase4-chain-head-compatibility.md) | `RetryLedger` startup verifies Phase 4 chain-head compatibility | audit-chain · phase-boundary · cross-phase-test |
| [0006](0006-protocol-vs-abc-convention.md) | Protocol for duck-typed contracts; ABC for inherited default behavior | convention · python · contracts |
| [0007](0007-pre-execute-marker-for-resume-safety.md) | `pre_execute` marker written to ledger before `SandboxClient.execute` | resume · idempotency · phase-6-handoff |
| [0008](0008-llm-judge-persona-deferral.md) | LLM Judge persona deferred; surfaced as roadmap gap | roadmap-gap · deferral · persona |
| [0009](0009-firecracker-network-policy-host-side-nftables.md) | Firecracker network policy via host-side TAP + nftables | firecracker · network · isolation |
| [0010](0010-cost-sandbox-run-ledger-schema.md) | `cost.sandbox.run` ledger entry schema is a Phase 5 contract | cost-ledger · phase-13-handoff · contract |
| [0011](0011-no-verdict-cache-in-phase-5.md) | No verdict cache in Phase 5; ship `sandbox_spec_hash` as the forward-compat seam | cache · deferral · phase-9-handoff |
| [0012](0012-static-env-allowlist-no-credentials-in-sandbox.md) | Static env allowlist + CI-enforced denied substrings — no credentials in sandbox | security · credentials · enforcement |
| [0013](0013-digest-pinned-policy-yaml-codegenie-owned.md) | Sandbox policy YAML is codegenie-owned and digest-pinned; not repo-resident | policy · supply-chain · adversarial |
| [0014](0014-objectivesignals-extra-forbid-static-introspection.md) | `ObjectiveSignals` is `extra="forbid", frozen=True`; static-introspection CI test enforces ADR-0008 | trust · enforcement · type-safety |
| [0015](0015-test-inventory-delta-asymmetric-policy.md) | Test-inventory `delta < 0` fails strict-AND; `delta > 0` is informational | signals · adversarial · trust |

## Conventions

- Filenames are `NNNN-kebab-case-title.md` zero-padded, numbered locally per phase starting at 0001.
- Numbers are immutable — a superseded ADR keeps its number; the new one gets the next number and cross-links.
- Cross-references to production ADRs use `../../../production/adrs/NNNN-*.md`.
- Cross-references to other phase ADRs use bare filenames (`[ADR-0003](0003-...md)`).

## Decisions noted but not yet documented

The following decisions were considered for ADR-ification but consolidated, deferred, or judged out of scope. Recorded here so a future architect can revisit:

- **Single-process orchestrator (vs. separate `codegenie-gated` daemon).** Two of three input designs converged on single-process; the critic's daemon attack landed. Captured in [phase-arch-design.md §Tradeoffs (consolidated)](../phase-arch-design.md#tradeoffs-consolidated). Not ADR-ified because all three viable designs except one agreed; this is not a contentious decision.
- **YAML catalog vs hardcoded gate registry.** Best-practices' design proposed YAML; all converged on YAML. Captured in [phase-arch-design.md §Component design — Gate ABC + StrictAndGate](../phase-arch-design.md#gate-abc--strictandgate). Not ADR-ified because the "organizational uniqueness as data" load-bearing commitment from [CLAUDE.md](../../../../CLAUDE.md) already mandates it.
- **`SandboxHealthProbe` as a B2-style probe.** Best-practices' design proposed it; the critic flagged performance's omission. Captured in [phase-arch-design.md §Component design — SandboxHealthProbe](../phase-arch-design.md#sandboxhealthprobe). Not ADR-ified because [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) already mandates the probe shape.
- **`--max-attempts-override` + `--operator-ack` + audit event.** Best-practices' design proposed it; [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md) already says max-attempts is configurable. Captured in [phase-arch-design.md §Component design — CLI surface](../phase-arch-design.md#cli-surface-codegenie-sandbox). Not ADR-ified because the production ADR already governs.
- **strace-in-VM (vs host-side eBPF).** Security-first's design wanted eBPF; macOS does not support it. The synthesis chose strace-in-VM with `coverage_ok` as a soft signal. Captured in [phase-arch-design.md §Edge case 9](../phase-arch-design.md#edge-cases) and [final-design.md §Synthesis ledger — Runtime-trace source row](../final-design.md#synthesis-ledger). Borderline — if Phase 12 introduces deeper validation, this may warrant promotion to an ADR.
- **One YAML catalog or two (`stage6_validate.yaml` + `stage6_validate_loose.yaml`).** Open Q4 — implementation will confirm; [final-design.md §Open questions §4](../final-design.md#open-questions-deferred-to-implementation).
- **No SAST in Phase 5.** Owned by Phase 12; not ADR-ified here because the scope-boundary is already in [phase-arch-design.md §Non-goals §4](../phase-arch-design.md#non-goals).
- **`SignalKind` registry collision policy.** Default: raise `SignalKindAlreadyRegistered` at import; confirmed in implementation. [Open Q10](../phase-arch-design.md#open-questions-deferred-to-implementation).
