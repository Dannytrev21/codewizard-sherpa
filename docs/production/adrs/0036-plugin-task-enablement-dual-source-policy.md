# ADR-0036: Plugin/task enablement — dual-source policy (operator Postgres + repo `codegenie.yaml`), OR resolution, fail-closed, stage-aware

**Status:** Accepted
**Date:** 2026-05-15
**Tags:** policy · kill-switch · config-as-code · audit · operator-portal · roadmap · phase-13.5
**Related:** ADR-0009, ADR-0024, ADR-0029, ADR-0031, ADR-0032, ADR-0033, ADR-0034, ADR-0035

## Context

Two stakeholders need the ability to prevent codewizard-sherpa from running work against a particular `(plugin, task, repo)` combination, and they have fundamentally different lifecycles:

- **Operators (platform / ops team).** Need a fast way to disable a plugin globally or scoped to a repo when an upstream tool breaks, a CVE feed misbehaves, a security incident is in flight, or a batch of synthetic-looking PRs need to be paused before they're opened. Lifecycle is **operational** — flips often, urgency varies, must be auditable but also fast.

- **Repo owners.** Need a way to opt their repo out of work without filing an ops ticket: deploy freezes, in-flight migrations, known false-positive patterns specific to their codebase. Lifecycle is **architectural** — changes via PR review, owned by the repo team, slow but durable.

Three properties any solution must preserve:

1. **Auditability.** Every disablement must be attributable to an actor and a reason. The audit trail must distinguish "operator chose this" from "repo team chose this" — these are very different signals when investigating "why didn't codewizard handle CVE-X on repo-Y?"
2. **No silent drops.** A workflow that is skipped because of enablement policy must emit a typed event with the reason and source; an absent log entry must never mean "we silently decided not to run."
3. **Consistency with [ADR-0009](0009-humans-always-merge.md) and the trust-machinery commitments.** Disabling work is allowed; *overriding gate decisions* is not. The disablement happens *before* gates run, not as a post-hoc veto.

The temptation is to pick a single source: either all policy is operational (Postgres-only) and repo teams file tickets, or all policy is config-as-code (YAML-only) and ops files PRs against a config repo. Both single-source options break in production: Postgres-only marginalizes repo team autonomy; YAML-only is too slow for kill-switch semantics.

## Options considered

- **Option A — Postgres-only (operator-owned).** All enablement state in one table; flips happen in the operator portal. Repo teams must request changes via ops. Rejected: marginalizes repo-team autonomy and creates a ticket bottleneck for routine "leave us alone during Q4" requests.

- **Option B — `codegenie.yaml`-only (repo-owned).** All enablement state lives in a per-repo committed file. Ops files PRs against config repos when they need to pause something. Rejected: too slow for kill-switch semantics. When an upstream tool breaks at 3am, "open 50 PRs and wait for review" is the wrong answer.

- **Option C — Portal writes PRs against repo YAMLs.** Operator actions in the portal generate PRs against the affected repos' `codegenie.yaml`. Preserves single-source-of-truth (the YAML). Rejected: defeats the speed property the portal is supposed to deliver, *and* creates the awkward situation where every kill-switch is a multi-repo PR series the operator must shepherd.

- **Option D — Dual-source with logical-OR resolution; fail-closed.** Two sources, neither overrides the other, either can disable. Operator-side = Postgres + event log; repo-side = `codegenie.yaml` loaded as a Layer-A probe. The audit log differentiates the sources. Recommended.

## Decision

**Adopt Option D.** The system carries two enablement policy sources, consulted at three points in the pipeline, resolved by logical OR with fail-closed semantics, and audited via the canonical event log.

### Source 1 — Operator policy (Postgres)

Postgres table `plugin_enablement`:

```sql
plugin_enablement(
  id              uuid primary key,
  org_id          text,                          -- nullable; single-org sentinel v1
  scope_task      text,                          -- task class id or '*'
  scope_plugin    text,                          -- plugin id or '*'
  scope_repo      text,                          -- repo slug or '*'
  enabled         boolean not null,
  updated_by      text not null,                 -- GitHub user id (portal session)
  updated_at      timestamptz not null,
  reason          text not null,                 -- free text; required
  expires         timestamptz                    -- optional; null = indefinite
)
```

- Edited via the [Phase 13.5 operator portal](0035-operator-portal-architecture.md).
- Every change emits a `PluginEnablementChanged(scope, enabled, actor, reason, expires)` event to the canonical event log ([ADR-0034](0034-event-sourcing-canonical-primitive.md)). The table is a projection — if it's wiped, it can be rebuilt from the event log.
- Resolution within this source is **most-specific-wins**: `(task=vuln-remediation, plugin=*, repo=repo-x)` overrides `(task=vuln-remediation, plugin=*, repo=*)`.
- `reason` is required at the API; empty strings are rejected. `expires` is optional but the portal nudges operators toward setting it (most "pause this" cases are temporal).

### Source 2 — Repo policy (`codegenie.yaml`)

Committed file at each repo root. Loaded by the existing gather pipeline as a Layer-A probe; cached like any other probe input. Schema:

```yaml
schema_version: 1
enabled: true                          # hard global switch for this repo
watch_branches:                        # optional; defaults to default branch
  - main
  - "release/*"
opt_outs:
  - reason: "Q4 deploy freeze"
    expires: 2027-01-15                # optional ISO date; auto-re-enables
    scope:
      task_classes: ["distroless-migration"]
  - reason: "Owner team migrating off Node"
    scope:
      plugins: ["vulnerability-remediation--node--npm"]
owners:
  primary: "@org/payments-platform"
  escalate_after_days: 7
```

- Edited only via PR review against the repo. Repo CODEOWNERS approve like any other config-as-code change.
- The system reads it; the system does **not** write it (the portal can *display* current opt-outs as a repo-detail badge but cannot edit the YAML).
- Glob support: `paths: ["third_party/**"]` allows path-scoped opt-outs for vendored / generated trees.
- `expires` triggers a "expiring within 7 days" warning in the next gather's CLI summary.

### Resolution rule

For any candidate workflow `(task, plugin, repo)`:

```
disabled := operator_disabled(task, plugin, repo) OR repo_disabled(task, plugin, repo)
```

**Logical OR. Fail-closed.** Either source can disable; neither can re-enable what the other disabled. Rationale: "I forgot to opt out" is a worse failure than "I accidentally opted out and noticed when nothing ran" — the asymmetry of consequences picks OR over AND.

### Consult points

Three stages consult the resolution rule *before* any gate runs:

| Stage | Question asked | Action on `disabled = true` |
|---|---|---|
| Stage 0 — Discovery | `discovery_enabled(repo)` | Skip enrolling this repo into the candidate set |
| Stage 1 — Assessment | `assessment_enabled(repo, task)` | Skip triage; emit `Skipped(reason, source)` |
| Supervisor dispatch (between Stage 1 and Stage 2) | `plugin_enabled(plugin, repo, task)` | Skip the workflow before any subgraph runs |

Every skip emits a `Skipped(stage, workflow_id, reason, source, actor, ts)` event to the canonical event log. The `source` field is one of `"operator-disabled"`, `"repo-opt-out"`, or `"both"` — the audit trail differentiates which stakeholder paused the work.

### Mid-flight semantics

When ops flips an operator-side kill-switch while a workflow is already running, the workflow respects stage boundaries per [ADR-0035](0035-operator-portal-architecture.md):

- **Discovery, Assessment, Deep Scan, Planning, Validation, Learning** — short-circuit at the next stage boundary; emit `Skipped`.
- **Execution** — non-interruptible; finishes (clean candidate diff or clean rollback), then subsequent stages skip.
- **Handoff** — non-interruptible if begun; the PR opens, operator can close manually if desired.

The repo-side source (`codegenie.yaml`) only takes effect on the *next* gather (it's loaded as a Layer-A probe); a freshly-committed opt-out does not retroactively halt a workflow already in flight. This is the right default: the repo team committed the opt-out via PR, which by definition involves at least one review cycle, which is more than enough time for any in-flight workflow to complete.

## Tradeoffs

| Gain | Cost |
|---|---|
| Operator gets fast kill-switch ergonomics (Postgres flip + event emission, sub-second) | Two sources of truth — but the OR rule makes resolution unambiguous and the audit log differentiates them |
| Repo teams get autonomy without an ops ticket bottleneck (PR against their own `codegenie.yaml`) | Repo-side opt-outs only apply to the *next* gather; a freshly-committed opt-out doesn't halt in-flight work (this is intentional but must be documented) |
| OR + fail-closed picks the asymmetry of consequences: missed opt-out is worse than missed enable | Neither source can override the other — sometimes ops wants to *force-enable* a repo's opt-out (e.g., for a critical security patch). That escalation requires the repo team to amend `codegenie.yaml`; we do not provide an operator override. This is by design — preserves repo-team authority over their own opt-outs |
| Every disablement is auditable via two paths: Postgres history + canonical event log (operator side); git history (repo side); both surfaced in the portal's audit log | Operators must understand that flipping a switch only prevents *new* work — Execution and Handoff already in flight complete. The `Skipped` event docs and the portal UI must make this legible |
| `expires` field on both sides; opt-outs auto-re-enable when stale (no zombie opt-outs that outlive their reason) | Repo teams must remember to set `expires` for genuinely-temporary opt-outs; indefinite opt-outs are still possible by omitting it |
| Path-scoped repo opt-outs (`paths: ["third_party/**"]`) handle the "scanner false-positive in vendored code" case without disabling the whole repo | Path globs are matched against `RepoContext.affected_paths` (when the task class declares affected paths); task classes that don't have a notion of "this workflow targets these paths" can't honor `paths:` and fall back to repo-level scope |
| The portal *displays* repo-side opt-outs but does not edit them — preserves config-as-code on the repo side while still giving operators visibility | Operators occasionally want to "fix a typo" in someone's `codegenie.yaml`; they file a PR like everyone else |

## Pattern fit

Pattern: **Dual-source policy with OR resolution and fail-closed semantics** + **CQRS** (Postgres table is a projection of the event log on the operator side; the YAML file is its own source on the repo side; both feed into a single resolution function) + **policy-as-data** (both sources are auditable structured data, not code; the resolution function is pure and deterministic) + **fail-closed asymmetry** (the *consequence* shape, not just the *behavior* shape, drives the rule).

This composes with: [ADR-0034](0034-event-sourcing-canonical-primitive.md) (event log is the canonical audit source); [ADR-0031](0031-plugin-architecture.md) (scope tuples map onto plugin scope tuples — `(task, plugin, repo)` is the same shape the plugin registry already speaks); [ADR-0029](0029-task-class-context-manifests.md) (TCCMs define what a task class *needs*; this ADR defines whether a task class *runs at all*); [ADR-0035](0035-operator-portal-architecture.md) (the portal is the operator-side UX for this policy).

It avoids: **silent drops** (every skip emits a typed event); **single-source authoritarianism** (neither stakeholder can override the other; the OR rule plus separate source tags preserves attribution); **stringly-typed scopes** (the table uses `scope_task`, `scope_plugin`, `scope_repo` as typed columns with `*` as the wildcard sentinel — no JSON blob shenanigans).

## Consequences

- A new Postgres table `plugin_enablement` lands in Phase 13.5. `org_id` column nullable for single-org v1.
- The canonical event log gains two typed event kinds: `PluginEnablementChanged` (operator action) and `Skipped` (workflow short-circuited by enablement policy, with `source` discriminator).
- A new repo-side artifact `codegenie.yaml` becomes part of the gather pipeline's Layer-A probe set. Schema-versioned. Loaded under the same chokepoint discipline as every other YAML (Phase 1 `safe_yaml.load`).
- The Supervisor dispatch logic gains a pre-routing consult against the resolution function. The consult is pure: it reads the table + the loaded `codegenie.yaml` from `RepoContext` and returns a boolean + source. No side effects beyond emitting `Skipped` if the answer is "skip."
- Phase 13.5's operator portal ([ADR-0035](0035-operator-portal-architecture.md)) ships with views for: "all current operator-side kill-switches" (with bulk filter), "this repo's current opt-outs" (read-only display of the YAML), and "audit log of every flip" (event-log replay).
- The roadmap's Phase 14 (continuous gather) inherits this policy unchanged — webhook-driven re-gathers consult the same resolution function before enqueueing workflows. No changes to Phase 14's design.
- Existing phases (0–13) do not change. The policy lands in Phase 13.5 and is consumed by Phase 13.5 onward.

## Reversibility

**Medium.** Backing out the operator side is cheap: the portal stops writing, the table is dropped, the consult returns "enabled" always. Backing out the repo side is harder: any `codegenie.yaml` files committed in production repos must be either honored, deprecated with notice, or migrated to a replacement policy mechanism. The compromise that makes this reversible: the schema is versioned (`schema_version: 1`), so a v2 schema can supersede v1 cleanly; and the event log records every operator action, so reconstructing operator state from history is always possible. The OR rule itself is the most reversible part — if a future operational study finds the OR/AND asymmetry was wrong, it's a one-line change in the resolution function and a clear amendment to this ADR.

## Evidence / sources

- [`docs/roadmap.md`](../../roadmap.md) §"Phase 13.5 — Operator portal" — the phase this policy lands in
- [`docs/production/design.md`](../design.md) §4.8 "Runtime enablement (kill-switches)" — how the policy slots into the plugin model
- [ADR-0035](0035-operator-portal-architecture.md) — the operator-side UX; this ADR defines the policy that ADR-0035's mutation surface edits
- [ADR-0034](0034-event-sourcing-canonical-primitive.md) — the canonical event log this policy emits to
- [ADR-0031](0031-plugin-architecture.md) — plugin scope tuples; this ADR's scope columns mirror that shape
- [ADR-0033](0033-domain-modeling-discipline.md) — typed events for `PluginEnablementChanged` and `Skipped`
- [ADR-0009](0009-humans-always-merge.md) — the commitment that explains why enablement is "prevent new work" not "override decisions"
