# ADR-0015: The orchestrator self-loads the repo dependency set and resolves `CveId → VulnerabilityRecord` — `run` / `__init__` stay frozen

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** phase-boundary · contract · data-ingress · functional-core-imperative-shell · sum-type · open-closed
**Related:** [0001](0001-ship-phase5-contract-surface-by-name.md), [0003](0003-plugin-resolution-and-universal-fallback-semantics.md), [0008](0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md), [0010](0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md), [0014](0014-recipe-engine-surfaces-transform-via-transform-registry.md)

## Context

Story `S6-04` (`RemediationOrchestrator` + the 5-node subgraph) was re-validated on 2026-05-21 with verdict **RESCUE** (see [`stories/_validation/S6-04-remediation-orchestrator.md` §Re-validation](../stories/_validation/S6-04-remediation-orchestrator.md)). The re-validation found two data-flow preconditions that a story-hardening edit cannot close — they are architectural decisions, and one of them is an internal contradiction in `phase-arch-design.md` itself. This ADR resolves them.

### Gap G1 — `RepoContext` has no ingress, and the arch contradicts itself

`phase-arch-design.md §Control flow` **step 1** says the **CLI** loads `.codegenie/context/repo-context.yaml`. **Step 2** then calls `RemediationOrchestrator.run(repo, cve, ApplyContext())` — a signature with **no parameter** to receive what step 1 loaded. `RemediationOrchestrator.__init__(registry, vuln_index, event_log, *, sandbox=None)` has no slot either. The arch's own control-flow narrative is structurally impossible against the arch's own component contract. Plugin resolution (`step 3 — scope_from_repo_context`), CVE resolution (G2 below), and the `BundleBuilder.build(resolution, repo_ctx, vuln, vuln_index)` call (`step 6` / `§C7`) all need that context.

A complicating fact discovered while grounding this ADR: **`RepoContext` is not a Python type.** There is no `class RepoContext` anywhere in `src/codegenie/`. "`RepoContext`" names the *on-disk YAML artifact* `repo-context.yaml` plus its JSON Schema (`src/codegenie/schema/repo_context.schema.json`). There is **no in-memory model and no loader**. `src/codegenie/output/paths.py` ships only a pure path helper (`<repo_root>/.codegenie/context/repo-context.yaml`, no IO). The arch's `repo_ctx: RepoContext` annotation in `§C7` describes an intent, not a shipped type — the as-built `BundleBuilder.build` (S3-04) takes `repo_ctx: object` / `vuln: object` as deliberately-unused plumbed-through placeholders.

### Gap G2 — no shipped path from `CveId` to `VulnerabilityRecord`

`RemediationOrchestrator.run` accepts `cve: CveId`. Every downstream consumer needs a full `VulnerabilityRecord` (`match_recipes(registry, plugin_id, cve: VulnerabilityRecord, bundle)`; the recipe engines reason over `affected_range`). The shipped `VulnIndex` (S3-02, `vuln_index/index.py`) exposes `lookup(name: PackageName, ecosystem: Ecosystem) -> list[VulnerabilityRecord]`, `affecting_range(cve: CveId) -> AffectedRange`, and `digest()` — **none maps `CveId → VulnerabilityRecord`**. A `VulnerabilityRecord` is keyed `(cve_id, ecosystem, package)`, so a single CVE can produce *several* records; selecting the one(s) relevant to the target repo requires the repo's actual dependency set — i.e. the same context as G1. G2 collapses into G1.

### Why this needs an ADR, not a story edit

The frozen-contract promise of [ADR-0001](0001-ship-phase5-contract-surface-by-name.md) is the whole reason `run` / `__init__` exist in their named shape. Picking how the context enters, whether `VulnIndex` grows a method, and where the (arch-mandated, story-omitted) bundle build lives are load-bearing structural choices. A `phase-story-validator` pass is explicitly not authorised to invent them.

## Options considered

The re-validation enumerated three ingress options for G1:

- **Option 1 — Orchestrator self-loads.** `run()` derives the repo root from the `repo: SandboxedPath` it *already receives* and loads the context off `<repo>/.codegenie/context/repo-context.yaml` itself. `run` / `__init__` signatures unchanged. **Pattern:** Functional core / imperative shell + make-illegal-states-unrepresentable.
- **Option 2 — `RepoContext` enters via `__init__`.** Requires an ADR-0001 *amendment* (the `__init__` surface is contract-frozen and S6-06-snapshotted) — a loud, gated contract change for no functional gain.
- **Option 3 — CVE→record resolution is a pre-orchestrator (CLI) step.** The CLI resolves `CveId + context → VulnerabilityRecord` and `run`'s signature is amended to take `vuln: VulnerabilityRecord` instead of `cve: CveId` — again an ADR-0001 amendment + S6-06 re-snapshot, and it pushes index-query logic into the thin CLI shell.

For G2, two sub-options: **(2a)** add an additive `VulnIndex.find_by_cve(cve) -> list[VulnerabilityRecord]`; **(2b)** compose the existing `lookup` over every repo dependency and filter by `cve_id`.

## Decision

### D1 — Adopt **Option 1**: the orchestrator self-loads. `run` / `__init__` stay frozen.

`RemediationOrchestrator.run(self, repo: SandboxedPath, cve: CveId, context: ApplyContext | None = None)` and `__init__(self, registry, vuln_index, event_log, *, sandbox=None)` are **unchanged** — no ADR-0001 amendment, no S6-06 re-snapshot.

This is not merely the smallest change; it is the *correct* coupling. The `repo` path and the context artifact that describes that repo are intrinsically one thing — `repo-context.yaml` is a fixed sub-path of `repo`. Passing them as two independent parameters (Options 2/3) admits an illegal state: a `RepoContext` handed in for the *wrong* `repo`. Deriving the context from `repo` makes that mismatch **unrepresentable**. Phase 5 wraps `_validate_stage6`, *not* `run()` (ADR-0001 §Context) — so `run()`'s shape is Phase-3-internal + CLI-facing, and self-loading changes nothing Phase 5 observes.

### D2 — Introduce a narrow loader, not a `RepoContext` model.

S6-04 needs exactly one fact out of `repo-context.yaml`: the repo's dependency set. A full `RepoContext` deserializer is unwarranted scope (Rule 2). Add a new module `src/codegenie/transforms/repo_context.py` — functional core / imperative shell:

- `InstalledDependency` — frozen Pydantic model, `package: PackageName`, `ecosystem: Ecosystem`. (Installed *versions* are deliberately out of scope: name + ecosystem is sufficient to resolve `CveId → VulnerabilityRecord`; version-range applicability is already the recipe engines' job.)
- `load_installed_dependencies(repo_root: Path) -> Result[tuple[InstalledDependency, ...], RepoContextLoadError]` — the imperative shell does one file read; a pure helper parses bytes → tuple. The dependency set is extracted from the `node_manifest` probe slice of the envelope; the exact slice keys are pinned by the post-ADR story re-harden against the shipped schema.
- `RepoContextLoadError` — a tagged union (ADR-0010 discipline): `RepoContextMissing` · `RepoContextUnreadable` · `RepoContextSchemaInvalid` · `RepoContextNoDependencies`.

### D3 — Adopt **Option 2a** for G2: additive `VulnIndex.find_by_cve` + a pure resolver.

Add `VulnIndex.find_by_cve(self, cve: CveId) -> list[VulnerabilityRecord]` — one additive method, a `WHERE cve_id = ?` query. CVE-keyed access is already a sanctioned `VulnIndex` capability (`affecting_range(cve)` exists), so this is consistent, not a new shape. Composition (2b) was rejected: O(deps) queries and a resolver that reads worse.

A **pure** resolver `resolve_cve(records, deps) -> CveResolution` intersects `find_by_cve(cve)` with the loaded dependency set (a record matches a dep iff `package` *and* `ecosystem` are equal). `CveResolution` is a tagged union: `CveAffectsRepo(record)` · `CveNotInRepo` · `CveAffectsMultiple(records)`. The orchestrator maps it deterministically:

| `CveResolution` | Orchestrator outcome |
|---|---|
| `CveAffectsRepo(record)` | proceed with `record` |
| `CveNotInRepo` (or `RepoContextNoDependencies`) | `RemediationNotApplicable` |
| `CveAffectsMultiple(records)` | `RequiresHumanReview` |

`CveAffectsMultiple → RequiresHumanReview` keeps Phase 3 honestly scoped to day-1 single-dependency npm-lockfile remediation; multi-package CVEs escalate to a human rather than guessing. `RepoContextMissing` / `Unreadable` / `SchemaInvalid` → `RemediationFailed` (operator error — `codegenie gather` must run first, or the artifact is corrupt; fail loud per Rule 12).

### D4 — The bundle build is orchestrator-owned, in the `run()` preamble.

`phase-arch-design.md §Control flow step 6` mandates a `BundleBuilder.build` between resolution and the subgraph, yet the 5-node subgraph has no bundle node and `SubgraphState.bundle` has no populating node. **Decision:** the orchestrator builds the bundle inside `run()` — after dependency-set load, CVE resolution, and plugin resolution, before the subgraph loop — and seeds the initial `SubgraphState.bundle`. The bundle build depends on `vuln_index` (an `__init__` dependency) and `resolution`; keeping it in `run()` leaves the 5-node subgraph a pure linear transform pipeline that Phase 6's LangGraph wrap maps 1-to-1, with no conditional sixth node. `IngestCveNode` remains node 1 and performs the D3 CVE resolution (constructor-injected `VulnIndex`, may `ShortCircuit`); the dependency set is loaded once by the `run()` shell and seeded onto `SubgraphState`.

## Tradeoffs

| Gain | Cost |
|---|---|
| `run` / `__init__` stay frozen — no ADR-0001 amendment, no S6-06 re-snapshot | The orchestrator gains a disk-read dependency the frozen signature does not advertise — mitigated: it already does repo IO (npm, git, branch writes) |
| A repo/context mismatch is unrepresentable (context is derived from `repo`) | Self-loading couples the orchestrator to the `repo-context.yaml` location; a path change is now a two-site edit (`output/paths.py` + the loader) |
| Narrow loader (D2) ships ~3 small types, not a full `RepoContext` model | A later phase that needs more of the envelope must widen the loader or finally introduce the model |
| `find_by_cve` is one additive `VulnIndex` method, mirroring `affecting_range` | A small S3-02 surface amendment; the S6-06 contract snapshot (not yet baked) records the wider `VulnIndex` |
| Bundle build in `run()` keeps the subgraph a clean 5-node 1-to-1 Phase-6 wrap | `run()`'s preamble grows; the orchestrator owns four resolution steps before the loop |

## Pattern fit

- **Functional core / imperative shell** (CLAUDE.md; toolkit §FC-IS) — `load_installed_dependencies` and `resolve_cve` are pure given bytes/inputs; only `run()` touches disk.
- **Make illegal states unrepresentable** (ADR-0010; toolkit §domain modeling) — deriving the context from `repo` eliminates the wrong-repo-context bug class by construction.
- **Tagged union / sum type** (ADR-0010) — `RepoContextLoadError` and `CveResolution` are discriminated unions; every dispatch site uses `match` + `assert_never`. No booleans, no `None`-means-three-things.
- **Open/Closed** — `find_by_cve` is an *addition* to `VulnIndex`, not an edit to an existing query.

## Consequences

- **New module** `src/codegenie/transforms/repo_context.py` — `InstalledDependency`, `load_installed_dependencies`, `RepoContextLoadError` (+ its variants), `resolve_cve`, `CveResolution` (+ its variants). It is a new "Files to touch" entry for the S6-04 re-harden and a new per-submodule cold-start fence subject.
- **Additive `VulnIndex.find_by_cve`** (S3-02 surface amendment). The eventual S6-06 Phase-5 contract snapshot bakes the wider `VulnIndex`.
- **`SubgraphState` gains additive slots** — `installed_dependencies: tuple[InstalledDependency, ...]` and `vulnerability_record: VulnerabilityRecord | None = None` (seeded/threaded between `IngestCveNode` and `MatchRecipeNode`). This routes to an **additive S6-03 amendment** of `plugins/subgraph.py` (`extra="forbid"` stays; new fields default-valued).
- **`NotApplicableReason` / `HumanReviewReason` widen additively** with `CVE_NOT_IN_DEPENDENCY_SET` and `MULTI_PACKAGE_CVE` respectively — additive Literal widening, mirroring [ADR-0001](0001-ship-phase5-contract-surface-by-name.md)'s 2026-05-19 amendment precedent.
- **The orchestrator mints a real `CapabilityBundle`** (npm-install + git capabilities — a remediation workflow's capability set is not empty) for the internally-constructed `ApplyContext`. This supersedes the re-validation's B7 note: do **not** rely on a nonexistent `CapabilityBundle.empty()`.
- **`phase-arch-design.md §Control flow` step 1 is superseded** by D1 — the CLI does **not** load or pass `repo-context.yaml`; the orchestrator self-loads. An amendment note is added to the arch doc pointing here.
- **`BundleBuilder.build`'s `repo_ctx` / `vuln` parameters stay `object`-typed and unused** for S6-04 (the orchestrator passes the resolved values through); tightening those annotations is a future story's additive change, when `build` actually consumes them.
- **Post-ADR re-harden.** `S6-04` stays `BLOCKED` until a `phase-story-validator` pass folds this ADR plus the patchable dependency-drift list (B1–B9 in the re-validation report) into the story's ACs. Only then may `phase-story-executor` run it. No later Step-6/7/8/9 story may execute before that.

## Reversibility

**Medium.** The loader and `repo_context.py` types are Phase-3-internal — replaceable without cross-phase coordination. `VulnIndex.find_by_cve` is additive and safe to keep even if unused. The one sticky commitment is D1: once S6-05's CLI and any Phase-4/5 caller assume the orchestrator self-loads, moving ingress back into a parameter is an ADR-0001 amendment. That cost is intentional — it is the same frozen-contract discipline ADR-0001 exists to enforce.

## Evidence / sources

- [`stories/_validation/S6-04-remediation-orchestrator.md` §Re-validation — 2026-05-21](../stories/_validation/S6-04-remediation-orchestrator.md) — gaps G1, G2, dependency-drift B1–B9
- `phase-arch-design.md §Control flow` steps 1–6 (the internal contradiction) + `§C7. BundleBuilder`
- `src/codegenie/vuln_index/index.py` — shipped `VulnIndex` surface (`lookup`, `affecting_range`, `digest`); `vuln_index/models.py` — `VulnerabilityRecord(cve_id, ecosystem, package, affected_range, …)`
- `src/codegenie/plugins/bundle.py:437` — as-built `BundleBuilder.build(resolution, repo_ctx: object, vuln: object, vuln_index)`
- `src/codegenie/plugins/sandbox_path.py` — `SandboxedPath.absolute: Path`; `src/codegenie/output/paths.py` — `repo-context.yaml` path helper (no IO; no loader)
- [ADR-0001](0001-ship-phase5-contract-surface-by-name.md) — frozen Phase-5 contract surface; Phase 5 wraps `_validate_stage6`, not `run()`
- [ADR-0010](0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md) — sum-type + newtype discipline
