# Phase 03 — Vuln remediation: deterministic recipe path: ADRs

Architecture Decision Records for Phase 3, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-ship-phase5-contract-surface-by-name.md) | Ship the Phase-5 contract surface in Phase 3 — `RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext`, `RecipeEngine`, `remediation-report.yaml` | phase-boundary · contract · architecture · phase-5-integration |
| [0002](0002-plugin-registry-kernel-instance-with-default-singleton.md) | Plugin / Registry kernel — instance-based with `default_registry` + fixture isolation | plugin-architecture · registry · kernel · open-closed · phase-7-bake-test |
| [0003](0003-plugin-resolution-and-universal-fallback-semantics.md) | Plugin resolution algorithm + universal `(*,*,*)` fallback as a registered plugin | plugin-architecture · resolution · hitl · sum-type · open-closed |
| [0004](0004-plugin-private-capabilities-via-tccm.md) | Plugin-private capabilities live on TCCM `provides`/`requires`, NOT on the kernel `Plugin` Protocol | plugin-architecture · open-closed · kernel-discipline · phase-7-extension |
| [0005](0005-two-stream-event-log-per-adr-0034.md) | Two-stream event log — `workflow_internal` + `workflow_spanning` — per ADR-0034 hybrid model | event-sourcing · audit · phase-9-migration · durability · hybrid-model |
| [0006](0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md) | Hexagonal `SubprocessJail` Port — bwrap + sandbox-exec adapters as the Phase-3 interim sandbox | hexagonal · sandbox · ports-and-adapters · phase-5-substitution · interim-substrate |
| [0007](0007-run-npm-install-and-npm-test-in-phase3-jail.md) | Phase 3 runs the repo's own tests inside `SubprocessJail`; Phase 5 wraps the retry envelope, not the inner validate | exit-criterion · phase-5-handshake · stage-6 · seam |
| [0008](0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md) | `BundleBuilder` uses deterministic serial fallback (NOT hedged-race); `vuln_index.digest` is part of the Bundle cache key | determinism · cache-correctness · commitment-2.4 · veto-strength |
| [0009](0009-recipe-engine-protocol-with-two-implementations-day-1.md) | `RecipeEngine` Protocol ships with TWO implementations on day one — `NpmLockfileRecipeEngine` (production) + `OpenRewriteRecipeEngine` (scaffold) | strategy-pattern · premature-pluggability-avoidance · phase-7-readiness · protocol-rent |
| [0010](0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md) | Domain-modeling discipline — `PluginScope` as `Concrete \| Wildcard` sum type; newtype every domain identifier; tagged-union outcomes everywhere | typing · domain-modeling · sum-type · newtype · illegal-states-unrepresentable |
| [0011](0011-honest-framing-capability-sandboxedpath-pluginslock.md) | Honest framing — `Capability` is audit + lint (NOT runtime-unforgeable); `SandboxedPath` is in-jail-at-construction; `PLUGINS.lock` is integrity check (NOT cryptographic signature) | threat-model · honest-framing · capability · phase-11-precursor |
| [0012](0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md) | Amend `ALLOWED_BINARIES` with `npm`, `bwrap`, `sandbox-exec`, `jq` (amends Phase 2 ADR-0001) | subprocess-discipline · allowed-binaries · amendment · supply-chain |

## Conventions

- Filenames are NNNN-kebab-case-title.md with zero-padded four-digit numbers, numbered locally per phase starting at 0001.
- Numbers are immutable — a superseded ADR keeps its number; the new one gets the next number and cross-links.
- Cross-references to production ADRs use `../../../production/adrs/NNNN-*.md`.
- Cross-references to ADRs in this folder use `NNNN-*.md`.
- Cross-references to ADRs in another phase's folder use `../../{phase}/ADRs/NNNN-*.md`.

## Decisions noted but not yet documented

These are decisions identified in `phase-arch-design.md` (especially under Gap analysis) or in `final-design.md` (Departures + Synthesis ledger) that have not yet been extracted into a standalone ADR. Each is a candidate for a future Phase-3 ADR amendment if/when implementation surfaces enough specificity:

- **Synthetic `example--noop--*` third plugin** (`tests/fixtures/plugins/example--noop--*/`) — locks in the 3-plugin contract bake test before Phase 7. Architecture spec calls this "Phase 3 ADR P3-005"; not extracted here because the decision is `final-design.md §Departures #7` + Goal G3 — bake-test scaffolding rather than a load-bearing structural choice. Surface as a standalone ADR if Phase 7 discovers gaps the bake test missed.

- **`tools/policy/lockfile-policy.yaml` location (codegenie-owned, not repo-owned)** — mirrors Phase 5's `tools/policy/sandbox-policy.yaml`. Architecture spec calls this "ADR P3-009" in Gap 2 / Improvement. Not extracted because the policy schema is one rule (`allowed_registries: list[RegistryUrl]`) and the rule language hasn't been exercised by enough call sites; Phase 7's distroless `BaseImagePolicy` extension will surface the right shape.

- **`SubgraphNode` Protocol with `NodeTransition = Advance | ShortCircuit | Escalate` sum type** — Gap 1 in architecture spec. The transition contract is currently described as "typed step functions Phase 6 wraps 1-to-1." Sharpens to an ADR if/when Phase 6's LangGraph wrap reveals the implicit-ordering smell the gap calls out.

- **`TrustScorer` constructor-injection of `EventLog`** (Gap 5 in architecture spec) — covered inline in ADR-0001's Consequences and ADR-0005's Consequences. A standalone ADR would help if the ambient-state vs constructor-injection question recurs in Phase 4 or 5 for other scorers.

- **`RecipeRegistry` (per-plugin) mirroring `PluginRegistry` shape** — Gap 3 in architecture spec. The registration mechanism is implicitly "iterate over `plugin/recipes/*.py` modules and call `@register_recipe`" but isn't pinned with the same rigor as the plugin registry. A standalone ADR would lock it in before Phase 7's distroless recipes invent a parallel mechanism.

- **`BundleCacheGc` policy** (once-per-day amortization + `codegenie cache prune` alias) — Gap 4 in architecture spec. Currently covered as a Consequence in ADR-0008; surface as a standalone ADR if Phase 10's portfolio scan changes cache-eviction economics.

- **Anti-decision: No LLM in Phase 3** (import-linter contract on `src/codegenie/{plugins,transforms}/` + `plugins/{vulnerability-remediation--node--npm,universal--*--*}/`) — Goal G5. This extends production ADR-0005 ("No LLM in gather pipeline") to the deterministic transform path. Treated as a direct extension of the production ADR; not extracted to avoid duplicating ADR-0005's rationale. If a future phase needs to revisit the boundary (Phase 4 LLM fallback explicitly carves an exception), document the carve-out as a standalone ADR then.

- **Anti-decision: No recipe authoring in Phase 3** (deferred to Phase 15). Roadmap-level decision; not an architecture choice for this phase.

- **Anti-decision: No multi-repo workflow** (deferred to Phase 12). Roadmap-level decision; not an architecture choice for this phase.
