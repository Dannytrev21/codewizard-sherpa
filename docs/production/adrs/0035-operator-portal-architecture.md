# ADR-0035: Operator portal — read-only-first, event-log-projected, GitHub-OAuth, with visibility/authority separated

**Status:** Accepted
**Date:** 2026-05-15
**Tags:** ui · observability · audit · ops · roadmap · phase-13.5
**Related:** ADR-0003, ADR-0009, ADR-0016, ADR-0024, ADR-0026, ADR-0027, ADR-0031, ADR-0032, ADR-0034, ADR-0036

## Context

Phase 9 ships the Temporal UI (workflow inspection, [ADR-0003](0003-temporal-as-workflow-substrate.md)); Phase 13 ships Grafana ROI dashboards (cost, [ADR-0024](0024-cost-observability-end-to-end.md)). Neither answers the operator's actual question: *"What is the system doing across my org right now, and which plugins / repos / campaigns are healthy, blocked, or worth pausing?"*

Three pressures converge:

- **Cross-cutting observability** — the answers live across Temporal workflow histories, the canonical event log ([ADR-0034](0034-event-sourcing-canonical-primitive.md)), the cost ledger, the plugin registry ([ADR-0031](0031-plugin-architecture.md)), the adapter degradation history ([ADR-0032](0032-language-search-adapters.md)), and GitHub PR state. No single existing surface joins them.
- **Operational kill-switch ergonomics** — when an upstream tool breaks or a repo asks to be left alone during a freeze, ops needs to *flip a switch*, not file a PR against a YAML config. The repo team needs the *opposite* — a YAML they own. (See [ADR-0036](0036-plugin-task-enablement-dual-source-policy.md) for the dual-source policy that consumes this portal.)
- **Roadmap fidelity** — commitment §8 (humans always merge, [ADR-0009](0009-humans-always-merge.md)) and §1 ("no LLM in gather") constrain what a control plane is allowed to do. A surface that lets operators retry workflows, tune trust thresholds, or override gate decisions silently defeats the trust machinery.

The question this ADR answers: *what shape does the operator-facing surface take, and what is it explicitly forbidden from doing?*

## Options considered

- **Option A — Extend Temporal UI.** Add custom views (plugin catalog, repo inventory, kill-switches) into the Temporal UI codebase. Rejected: Temporal UI is a fixed open-source project; forks bit-rot against upstream and lose the workflow-state rendering Temporal UI is genuinely good at. We keep Temporal UI for what it does well (deep workflow drilldowns) and don't try to make it something else.

- **Option B — Grafana dashboards only.** Build everything as Grafana panels over Prometheus + the cost ledger + event-log materialized views. Rejected: Grafana is excellent for metrics, weak for entity inventories (plugin catalogs, repo timelines) and structured drilldowns (a single workflow's full event stream). Forcing those into Grafana yields awkward UX and brittle templating.

- **Option C — Bespoke portal projected off the canonical event log; read-only-first with one narrow mutation surface (plugin/task enablement); GitHub OAuth + portal-side admin allowlist.** Recommended. The event log is already the canonical primitive ([ADR-0034](0034-event-sourcing-canonical-primitive.md)); the portal is one more projection alongside the cost ledger and KG. Read-only-first keeps the trust machinery intact; the explicit mutation surface (kill-switches) is scoped, audited, and forbidden from overriding gate decisions.

- **Option D — Full control plane.** A portal with buttons to pause/resume workflows, retry from a node, tune trust thresholds, and override gate decisions. Rejected for v1: every editable knob is one that could defeat a gate that exists for a reason; operator overrides of gates are exactly the failure mode the Trust-Aware layer ([§4.1, §4.6](../design.md)) was built to prevent. The kill-switch model in [ADR-0036](0036-plugin-task-enablement-dual-source-policy.md) is the narrow exception — it prevents work from *starting*, never overrides decisions that have *run*.

## Decision

**Adopt Option C.** Phase 13.5 ships a bespoke operator portal with the following properties:

1. **Read-mostly.** The only mutation surface is plugin/task enablement kill-switches, defined in [ADR-0036](0036-plugin-task-enablement-dual-source-policy.md). All other state changes happen through existing surfaces (PR review, ADR amendments, eval-harness calibration, config-as-code).

2. **Event-log-projected.** Every view materializes from the canonical event log ([ADR-0034](0034-event-sourcing-canonical-primitive.md)) and the cost ledger ([ADR-0024](0024-cost-observability-end-to-end.md)). The portal is a downstream consumer, not a source of truth — it cannot lie about what happened because the event log is what happened.

3. **GitHub OAuth identity; portal-side admin allowlist.** Authentication is GitHub OAuth. Repo visibility is resolved by querying the GitHub API at session establishment — a viewer sees the repos they have GitHub access to. **Admin** is a portal-side allowlist (`portal_admins(github_user_id, granted_by, granted_at, reason)`), *not* a GitHub-org-admin reflection. The security property: admins get *visibility elevation* (global read across workflows / campaigns / metrics) without *authority elevation* (their write-action scope remains the repos they own, just like any other user).

4. **Event-driven refresh.** Live views update via SSE or WebSocket subscriptions to the canonical event log; no polling. The specific transport (SSE vs WebSocket) is deferred to phase design.

5. **Stage-aware kill semantics.** When a kill-switch fires against an in-flight workflow:
   - **Discovery, Assessment, Deep Scan, Planning, Validation, Learning** — short-circuit at the next stage boundary. These stages don't mutate the candidate; aborting is safe.
   - **Execution** — non-interruptible. The stage completes (clean candidate diff or clean rollback), then subsequent stages skip.
   - **Handoff** — non-interruptible if already begun. The PR opens; the operator can close it manually.
   - A `Skipped(stage, reason, source, actor)` event writes to the canonical event log at the point of skip.

6. **Forbidden mutations.** The portal **cannot**:
   - Override gate decisions or retry workflows from a specific node (the gate is the authority; retry policy is [ADR-0014](0014-three-retry-default-per-gate.md)).
   - Tune trust thresholds (calibrated by the [Phase 6.5 eval harness](../../phases/06.5-per-task-class-eval-harness/), not by hand).
   - Install, upgrade, or remove plugins (display-only catalog v1; lifecycle is a separate concern with its own deployment auth + rollback ADR when it lands).
   - Cancel in-flight Execution or Handoff (the kill respects safe boundaries; the audit story is "we chose to stop new work, not undo work in flight").

7. **`org_id` column from day one.** All new Postgres tables (`plugin_enablement`, `portal_admins`) carry a nullable `org_id` column. Single-org v1 uses a sentinel default; multi-tenant Phase 14+ promotes it to a populated tenant key. Cheap forward-compatibility insurance.

## Roles and visibility

| Role | Read scope | Write/action scope |
|---|---|---|
| **Repo owner** | Repos the viewer has GitHub access to (resolved via GitHub API at session) | Same as read |
| **Admin** | All repos / workflows / campaigns / metrics — globally | Repos they own (same rule as repo-owner) |

Admin is a portal-side concept, not a GitHub-org-admin elevation. The asymmetry is deliberate: a platform engineer needs *visibility* across the entire org to run reports, investigate stalls, and answer questions; they don't need *authority* to mutate state in repos they don't own. Authority follows ownership; visibility follows role.

## Views (v1, ops first)

| View | Source | Notes |
|---|---|---|
| Pipeline ribbon | Temporal SDK + event log | Every active workflow as a 7-stage swimlane; color-coded by gate verdict |
| Repo detail | Continuous Gather Dispatcher emissions + event log + GitHub API | Last gather, `RepoContext` digest, active workflows, opt-outs, recent PRs, cost-to-date |
| Plugin catalog | `plugins/` directory + plugin-resolution events | TCCM preview, recipes, last-used / last-failed; kill-switch toggle |
| Campaign rollup | Event log (correlation by trigger ID) | When one trigger fans out to N repos: succeeded / blocked / awaiting review counts |
| Cost view | Phase 13 Grafana panels embedded | Per-task-class, per-plugin, per-repo breakdowns |
| Audit log | Event log (`PluginEnablementChanged`, `Skipped`, gate verdicts) | Searchable by actor, repo, plugin, reason, time |

Repo-owner views (v1.5) reuse the same backend with role-scoped filters; nothing new is built, just rendered differently.

## Tradeoffs

| Gain | Cost |
|---|---|
| Single unified operator surface; eliminates the "where do I look?" problem across Temporal UI + Grafana + GitHub + logs | One more service to operate (SPA + thin gateway + Postgres) |
| Visibility-without-authority security property: an admin can debug org-wide without being able to mutate anything they don't own | The admin allowlist must be maintained; a stale admin list is its own governance problem |
| Read-only-first preserves trust-machinery invariants (commitments §3 honest confidence, §8 humans always merge) | Operators sometimes want to override; "no" must be a stable answer or pressure will accumulate to widen the mutation surface |
| Event-log projection means the portal can never disagree with reality; it cannot drift from what actually happened | Event-log retention policy and replay performance now matter to UX (a slow replay is a slow portal) |
| Stage-aware kill semantics — operators get fast kill ergonomics without risking half-applied state | Operators must understand that flipping a switch doesn't undo work already in flight; documentation + the `Skipped` event must make this legible |
| GitHub OAuth + portal-side admin allowlist is the simplest workable auth — no new IdP to integrate, but admin elevation is still controlled | When multi-tenant lands, the admin allowlist needs scoping per tenant; the `org_id` column is the hook but the policy itself isn't yet specified |
| Plugin install / upgrade explicitly deferred — keeps v1 small and defers the deployment-auth + rollback ADR until there's a real install workflow to design against | Operators will eventually want this; the deferral creates a known follow-up |

## Pattern fit

Pattern: **CQRS-style projection** (the canonical event log is the write side; the portal is one of several read-side projections — cost ledger, KG, ROI dashboard, and now the portal are all peers) + **role-scoped visibility with separated authority** (the admin role elevates *read* without elevating *write*) + **read-mostly UI with narrow auditable mutation** (every mutation flows through an event-emitting API and lands in the canonical event log).

This composes with: [ADR-0031](0031-plugin-architecture.md) (the plugin catalog view reads the registry); [ADR-0032](0032-language-search-adapters.md) (adapter-degradation history surfaces in repo detail); [ADR-0034](0034-event-sourcing-canonical-primitive.md) (every projection is by definition a downstream consumer of the canonical log); [ADR-0036](0036-plugin-task-enablement-dual-source-policy.md) (the one mutation surface this portal exposes).

It avoids: **control-plane creep** (the flag-on-sight failure mode of operator UIs that grow override buttons until they defeat their own gates); **dual sources of truth** (settings would normally live in YAML for config-as-code consistency, but enablement is *operational state* with a different lifecycle — see ADR-0036 for that nuance); **GitHub-org-admin reflection** (treating GitHub org-admin as portal admin would conflate visibility with authority and propagate every GitHub permission churn into our security model).

## Consequences

- A new top-level service ships: a SPA (framework TBD) + thin FastAPI/Starlette gateway + Postgres (`plugin_enablement`, `portal_admins`) + SSE/WebSocket subscriber to the event log. Runs as a Kubernetes deployment alongside Phase 14's MCP servers.
- Two new Postgres tables; both carry `org_id` from day one (nullable default for single-org v1).
- The canonical event log gains two typed event kinds: `PluginEnablementChanged` (operator action) and `Skipped` (workflow short-circuited by kill-switch). Both consumed by the portal's audit log view; both also available to any other projection.
- The roadmap gains a new Phase 13.5 between AgentOps (Phase 13) and Continuous Gather + MCP servers (Phase 14). Phase 13.5 depends on Phase 9 (event log) and Phase 13 (cost ledger); it does not depend on Phase 14 and composes naturally with it.
- A follow-up ADR (TBD when needed) will design plugin install / upgrade / removal lifecycle with deployment auth + rollback semantics.
- The Phase 6.5 eval harness, Phase 13 Grafana dashboards, and Temporal UI all stay. The portal does not replace any of them — it sits alongside as the human-operator-first surface that links across them.

## Reversibility

**High.** The portal is read-mostly and projects off existing stores. If the design proves wrong, the projection can be rebuilt; the underlying event log, cost ledger, and Postgres tables are not portal-specific. The one mutation surface (kill-switches) lives in tables with full event-log audit; reverting the portal does not erase any operational state. The GitHub OAuth integration is the standard pattern and is decoupled from the portal's data model. The riskiest commitment in this ADR is the *read-only-first* discipline — once operators get used to read-mostly, widening the mutation surface later is a deliberate choice with its own ADR, not a slippery slope. That's the property we're paying for.

## Evidence / sources

- [`docs/roadmap.md`](../../roadmap.md) §"Phase 13.5 — Operator portal" — the phase definition this ADR records
- [`docs/production/design.md`](../design.md) §3.1 Personas (Operator portal row), §4.8 Plugins (Runtime enablement paragraph), §5 Observability (portal mention) — how the portal slots into the broader design
- [ADR-0034](0034-event-sourcing-canonical-primitive.md) — the canonical event log the portal projects from
- [ADR-0024](0024-cost-observability-end-to-end.md) + [ADR-0026](0026-roi-kpi-model.md) — the cost ledger and Grafana ROI dashboard the portal embeds
- [ADR-0009](0009-humans-always-merge.md) — the commitment that explains why "no override gate decisions" is non-negotiable
- [ADR-0036](0036-plugin-task-enablement-dual-source-policy.md) — the kill-switch policy this portal surfaces
