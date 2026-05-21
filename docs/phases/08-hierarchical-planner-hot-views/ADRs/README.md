# Phase 08 — Hierarchical Planner + pre-rendered hot views: ADRs

Architecture Decision Records for Phase 8, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-supervisor-graph-engine.md) | Supervisor graph engine — plain async pipeline, not LangGraph | Functional core / imperative shell · orchestration · dependency management |
| [0002](0002-supervisor-decision-three-variant-sum-type.md) | SupervisorDecision is a three-variant sum type including MultiPluginDispatch | Tagged union / sum type · make-illegal-states-unrepresentable · multi-plugin coordination |
| [0003](0003-hot-view-integrity-by-gather-id-content-addressing.md) | Hot-view integrity by gather-id content-addressing, not HMAC/KMS | content-addressed cache · fail-closed · make-illegal-states-unrepresentable |
| [0004](0004-per-slice-hot-view-schema-versioning.md) | Per-slice hot-view schema versioning | content-addressed cache · make-illegal-states-unrepresentable · schema evolution |
| [0005](0005-50ms-p95-exit-criterion-scoped-to-hot-view-read.md) | The <50ms p95 exit criterion is scoped to the hot-view read | Functional core / imperative shell · performance SLO · testability |
| [0006](0006-cold-storage-fallback-reads-the-rendered-repocontext.md) | Cold-storage fallback reads the same RepoContext the renderer rendered from | Hexagonal / ports & adapters · content-addressed cache · fail-closed |
| [0007](0007-routing-events-into-existing-event-log.md) | Routing decisions emit into the existing event log — no standalone event store | Open/Closed at the file boundary · event emission · roadmap phasing |
| [0008](0008-route-events-in-the-workflow-internal-stream.md) | RouteDecided/RouteDescended belong in the workflow-internal event stream | Tagged union / sum type · event modeling · stream placement |
| [0009](0009-concrete-resolution-to-bundle-resolution-adapter.md) | A ConcreteResolution → BundleResolution adapter bridges the resolver and the Bundle builder | Adapter pattern · fail-loud · type-system bridging |
| [0010](0010-repoid-newtype-in-the-identifiers-module.md) | RepoId is a newtype added to the identifiers module | Newtype pattern · Open/Closed at the file boundary · domain modeling |
| [0011](0011-fixed-three-step-routing-pipeline.md) | The recipe→RAG→LLM router is a fixed three-step pipeline, not a registry | Pipeline (fixed steps) · Hexagonal / ports & adapters · anti-decision: no premature pluggability |
| [0012](0012-mcp-skills-server-security-posture.md) | MCP Skills server — read-only tools and contract-snapshot, no OS-level confinement | Smart constructor / contract snapshot · Newtype pattern · anti-decision: no speculative subsystem |

## How these ADRs relate

The twelve ADRs fall into four clusters:

- **The Supervisor layer** — [0001](0001-supervisor-graph-engine.md) (graph engine), [0002](0002-supervisor-decision-three-variant-sum-type.md) (the `SupervisorDecision` sum type), [0009](0009-concrete-resolution-to-bundle-resolution-adapter.md) (the resolver→builder adapter).
- **The hot-view cache** — [0003](0003-hot-view-integrity-by-gather-id-content-addressing.md) (integrity), [0004](0004-per-slice-hot-view-schema-versioning.md) (versioning), [0005](0005-50ms-p95-exit-criterion-scoped-to-hot-view-read.md) (the SLO scope), [0006](0006-cold-storage-fallback-reads-the-rendered-repocontext.md) (the fail-closed cold path).
- **The routing decision + its audit trail** — [0007](0007-routing-events-into-existing-event-log.md) (no standalone store), [0008](0008-route-events-in-the-workflow-internal-stream.md) (stream placement), [0011](0011-fixed-three-step-routing-pipeline.md) (the fixed pipeline).
- **Cross-cutting** — [0010](0010-repoid-newtype-in-the-identifiers-module.md) (the `RepoId` newtype, used by every package) and [0012](0012-mcp-skills-server-security-posture.md) (the MCP Skills server posture).

Five ADRs ([0001](0001-supervisor-graph-engine.md), [0008](0008-route-events-in-the-workflow-internal-stream.md), [0009](0009-concrete-resolution-to-bundle-resolution-adapter.md), [0010](0010-repoid-newtype-in-the-identifiers-module.md), and the corrected framing in [0003](0003-hot-view-integrity-by-gather-id-content-addressing.md)/[0007](0007-routing-events-into-existing-event-log.md)) exist because the synthesized `final-design.md` made claims that are false against the shipped codebase — the four gaps the phase architect surfaced. [0011](0011-fixed-three-step-routing-pipeline.md) and [0012](0012-mcp-skills-server-security-posture.md) carry **anti-decisions**: a Strategy registry / Chain-of-Responsibility router and OS-level MCP confinement were both deliberately *not* built, and the ADRs record why.

## Decisions noted but not yet documented

These are real Phase-8 choices the design surfaces but that are not yet load-bearing enough — or not yet *resolved* enough — to be ADRs. They are open questions, tuning parameters, or implementer verifications, tracked in [phase-arch-design.md §Open questions](../phase-arch-design.md#open-questions-deferred-to-implementation):

- **`MultiPluginDispatch` sequencing depth** — how much cross-PR sequencing (ordering, shared evidence, status rollup) Phase 8 implements vs. defers to Phase 10. A scoping call for the story plan, not a settled decision. ADR-0002 freezes the *shape* (`work_items` + `parent_workflow_id`); the *depth* is open.
- **Hot-view debounce under churn** — whether `render_hot_views` needs a per-`RepoId` debounce (performance proposed 250 ms) to cap render amplification under a hot monorepo's push burst. A tuning parameter to validate against real push-frequency data.
- **`mcp` SDK version pin** — the specific version pinned in `pyproject.toml`. A deliberate choice the implementer makes; the `MCP_SKILLS_CONTRACT` snapshot guards drift but the initial pin is not yet decided.
- **`RepoId` grammar** — whether `RepoId` carries an `owner/name` grammar and a smart-constructor lift, or stays a free `NewType` until Phase 10 Discovery pins the GitHub repo-identity shape. ADR-0010 records the newtype; the grammar is deferred to Phase 10.
- **`NullRagPort` vs a two-step chain** — if the executor finds the null RAG branch creates dead-test maintenance burden, a two-step chain growing the RAG step in Phase 11 is the fallback. ADR-0011 commits to the three-step shape; this is its named escape hatch.

## Conventions

- **Filenames** are `NNNN-kebab-case-title.md` with zero-padded four-digit numbers, numbered locally per phase starting at 0001.
- **Numbers are immutable** — a superseded ADR keeps its number; the new one gets the next number and cross-links.
- **Cross-references** to production ADRs use `../../../production/adrs/NNNN-*.md`; to sibling phase ADRs use `NNNN-*.md`.
- **`Status`** follows the production convention: Proposed · Accepted · Provisional Accepted · Deferred · Superseded. All twelve Phase-8 ADRs are `Accepted` — each freeze is either narrow and earned, or (where a contract is frozen early) justified by a named downstream consumer one phase away.
