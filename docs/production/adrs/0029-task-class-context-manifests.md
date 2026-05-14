# ADR-0029: Task-Class Context Manifests — context selection as data

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** context · task-class · extension-by-addition · skills
**Related:** ADR-0005, ADR-0006, ADR-0007, ADR-0011, ADR-0013, ADR-0028

## Context

The `RepoContext` artifact (per [`../../localv2.md` §3](../../localv2.md) and [`../design.md` §3.2](../design.md)) is a comprehensive, deterministic snapshot of a repo: language inventory, build system, runtime traces, dependency graph, vulnerabilities, container layout, conventions, skills. By design it captures everything any future task class might need.

But no single task class needs everything. A vulnerability-remediation worker cares about lockfiles, package manifests, vulnerability records, the call sites of the affected module, and the tests exercising those call sites. It does not need the deployment manifests or runtime container trace. A distroless-migration worker is the inverse — it cares deeply about Dockerfile shape, base-image references, and shell-invocation evidence; lockfiles are incidental.

If every leaf agent receives the full `RepoContext`, two failures emerge:

1. **Token bloat.** The LLM's context window fills with information irrelevant to the task, crowding out the parts that matter and inflating per-workflow cost — directly against ADR-0024 / ADR-0025.
2. **Silent omissions.** If the agent is left to filter for itself, it can miss something that mattered, and the Trust-Aware gate has no way to flag the gap because there is no declared expectation of what should have been in scope.

Stage 7 Learning ([`../design.md` §3](../design.md)) and ADR-0028 (task-class introduction order) both commit to *extension by addition* — adding a new task class must not edit the gather pipeline, the Planner, or existing subgraphs. So per-task-class context selection cannot live in code. It must live as data.

The probe side of this contract already exists: every probe declares `applies_to_tasks` ([`../../localv2.md` §4](../../localv2.md)). The missing piece is the consumer-side counterpart — a declarative mapping, per task class, of which `RepoContext` slices and which filesystem globs matter, with priority bands and a budget cap.

## Options considered

- **Option A — per-subgraph hardcoded context selection.** Each LangGraph subgraph (Vulnerability Subgraph, Migration Subgraph) names the `RepoContext` keys it consumes. Fast to implement; tightly coupled. Adding a new task class means editing a new subgraph file, but the *pattern* of what-to-read is duplicated across subgraphs and drifts over time. Fails the spirit of ADR-0028.
- **Option B — let the leaf LLM filter the full `RepoContext`.** Hand the LLM everything and steer with prompt instructions ("focus on the lockfile"). Cheapest to design; most expensive at runtime; least auditable. Fails on token bloat and silent omissions.
- **Option C — Task-Class Context Manifests (TCCMs).** One YAML per task class declaring (i) which `RepoContext` keys to query, in priority bands (`must_read` / `should_read` / `may_read`), (ii) which filesystem globs to expand when `RepoContext` is not yet available, (iii) a hard token-budget cap. The Planner reads the TCCM for the dispatched task class and builds a **Context Bundle** that becomes the worker subgraph's context window. Adding a new task class is one new YAML file — no code edit anywhere.

## Decision

**Adopt Task-Class Context Manifests as the context-selection layer between `RepoContext` and the Hierarchical Planner / worker subgraphs.**

A TCCM is a YAML file at `task-class-contexts/{task-class}.yaml` declaring, for one task class:

- `must_read` — `RepoContext` keys + filesystem globs that always load. Sized to always fit the budget.
- `should_read` — second-priority items, loaded if budget allows. Last entries may be deferred with a provenance note.
- `may_read` — third-priority items, loaded only on explicit request from a worker node mid-execution (the escape hatch for SHERPA nodes that discover they need more).
- `bootstrap_globs` — fallback when no `RepoContext` exists yet (Phase 0–2 of the roadmap, or first-ever gather on a new repo).
- `budget` — `max_files`, `max_tokens`, `per_file_max_tokens`. Hard caps; a misconfigured TCCM cannot blow the workflow budget.

The Hierarchical Planner ([`../design.md` §4.1](../design.md)) consults the dispatched task class's TCCM and builds the Context Bundle that becomes the subgraph's initial state. The Bundle's provenance — which TCCM, which keys included, which deferred, which `may_read` items were later requested — is logged alongside the cost ledger for audit.

Hot views (ADR-0013) become the rendered cache of the most frequent `must_read` slices across active TCCMs; pre-rendering is now TCCM-driven, not hard-coded.

## Tradeoffs

| Gain | Cost |
|---|---|
| Adding a new task class = one new YAML file; no edits to the Planner, subgraphs, probes, or gather pipeline (preserves ADR-0028 and the extension-by-addition commitment) | TCCMs themselves must be authored carefully; mistakes show up as wrong context in the leaf agent — surfaced as Stage 7 Learning telemetry |
| Token economy is enforced as a hard per-task-class budget, auditable from the Bundle's provenance | One more layer in the call chain — Bundle building adds tens of milliseconds at portfolio scale |
| Context selection becomes diff-friendly — git history shows when a task class's context shape changed and why | TCCMs duplicate some content available from probe `applies_to_tasks` declarations; the duplication is intentional (producer-side vs. consumer-side) but must stay in sync |
| Skills ([`../../localv2.md` §10](../../localv2.md)) and TCCMs use the same loader pattern — same indexing, same versioning, same testing | TCCM evolution requires discipline: Stage 7 must write back which entries actually helped vs. were noise, so TCCMs improve from data rather than guesswork |

## Consequences

- **New task class = one new TCCM + one new subgraph.** Phase 7 of the roadmap (Chainguard distroless migration) is the first proof of this — adding it adds `distroless-migration.yaml`, not edits to `vulnerability-remediation.yaml`. ADR-0028's extension-by-addition test depends on this mechanism existing.
- **The Planner's `recipe_match` → `solved_example_rag` → `llm_fallback` chain (ADR-0011) operates on the Bundle, not the full `RepoContext`.** Each stage receives only what the TCCM scoped in. Recipe matching becomes cheaper; RAG retrieval becomes more precise; LLM fallback gets a smaller, more relevant prompt.
- **Pre-rendered Redis hot views (ADR-0013) auto-derive from TCCM aggregation.** The list of pre-rendered slices is no longer maintained by hand; it's computed from the `must_read` sections of the TCCMs currently in service.
- **The Skills server ([`../design.md` §8.1](../design.md)) gains a TCCM index alongside its Skills index.** Same MCP-served pattern; same authoring conventions; same forward-compatibility from POC to service.
- **Stage 7 Learning writes back per-entry usefulness telemetry.** Each `should_read` entry the worker actually consulted, vs. each `may_read` item that had to be requested, vs. each `must_read` item that turned out to be unused — these become inputs that tune TCCMs over time.
- **The POC's `RepoContext` schema does not change.** TCCMs consume the existing schema; the producer side ([`../../localv2.md` §4](../../localv2.md)) is unaffected. Probes do not need to know about TCCMs.

## Reversibility

**Medium-low.** TCCMs are pure data — removing them and reverting to "Planner passes full `RepoContext` to leaf" is a one-commit change to the Planner. But the cost-economy gains and the audit trail evaporate immediately, and ADR-0028's extension-by-addition guarantee weakens (each new task class would need to either pass full context or duplicate selection logic in its subgraph). A reverse-direction migration (re-introducing TCCMs after they were removed) would need to re-derive each task class's context shape from production traces — feasible but lossy.

## Evidence / sources

- [`../../localv2.md` §4](../../localv2.md) — probe contract with `applies_to_tasks` declarations (producer side; the consumer side is what this ADR adds)
- [`../../localv2.md` §10](../../localv2.md) — Skills as YAML-frontmatter data: same pattern TCCMs follow
- [`../design.md` §2](../design.md) — load-bearing commitments: "Organizational uniqueness as data, not prompts", "Extension by addition", "Progressive disclosure for context"
- [`../design.md` §3.2](../design.md) — continuous gather + pre-rendered hot views (TCCMs slot in here)
- [`../design.md` §4.1](../design.md) — Hierarchical Planner Supervisor (TCCMs feed it)
- ADR-0007 — probe contract preserved POC→service (TCCMs consume the contract unchanged)
- ADR-0011 — recipe-first → RAG → LLM-fallback planning order (TCCM feeds each step of the chain)
- ADR-0013 — pre-rendered Redis hot views (now derived from TCCM aggregation rather than hand-curated)
- ADR-0028 — task class introduction order (TCCMs are the mechanism that makes the ordering enforceable as extension-by-addition)
