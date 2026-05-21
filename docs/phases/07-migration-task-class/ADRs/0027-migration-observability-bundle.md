# ADR-0027: Migration observability — a typed `transformations_applied` list plus enrichment events make the change legible to the human merger

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** observability · humans-always-merge · enrichment · content-cache · amendment-a · §23 · G14-G17 · M3
**Related:** [0002](0002-shell-invocation-trace-probe-runs-in-microvm.md), [0008](0008-no-vuln-provenance-cache-in-phase-7.md), [0024](0024-multi-arch-and-external-registry-checks.md), [0025](0025-migration-refusal-taxonomy.md), [0026](0026-migration-confidence-aggregation.md), [0028](0028-allowed-binaries-amendment-crane.md), [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md), [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)

## Context

[production ADR-0009](../../../production/adrs/0009-humans-always-merge.md) makes autonomy end at PR creation — a human always merges. A distroless migration is a non-trivial structural change: it swaps the `FROM`, drops `RUN` lines the target image makes redundant, may rewrite a `HEALTHCHECK`, may add `--chown` to `COPY` lines, and a multi-stage refactor can quietly *balloon* the compressed image. If the human merger cannot see *what the recipe did* and *what risk it carries*, the "humans always merge" gate is a rubber stamp.

`final-design.md §Amendment A §A.2` gaps G14–G17 and M3, and `phase-arch-design.md §Component design — Amendment A §23`, require the migration's effect to be legible in the PR. None of this is a *decision* the system makes — it is *enrichment*: the migration already happened (or refused, [ADR-0025](0025-migration-refusal-taxonomy.md)); observability tells the human about it. The amendment is explicit (`final-design.md §A.1`) that every gap resolves to GATHER, REFUSE, or **WARN** — and G14–G17/M3 are all WARN: none of them blocks.

Gap G17 additionally asks for cross-CVE *performance* reuse: the `ShellInvocationTraceProbe` ([ADR-0002](0002-shell-invocation-trace-probe-runs-in-microvm.md)) boots a microVM and runs a build — expensive — so two CVEs filed against the same repo on the same day should not re-run it twice.

## Options considered

- **Option A — Hand-assemble a free-text PR description from whatever the recipe knows.** **Pattern:** Prose-as-interface. **Rejected** — a free-text description is not machine-readable (Phase 11's merge-gate and Phase 13.5's portal cannot consume it), drifts as the recipe changes, and an engineer editing the recipe can silently forget to update the prose.
- **Option B — A typed `transformations_applied` list plus typed enrichment events; the PR description is *rendered* from the typed data.** **Pattern:** Typed projection — the data is the source of truth, the prose is a view. The migration record carries a `tuple[TransformationKind, ...]`; the spanning event log carries the size/rollback/attestation enrichments.
- **Option C — Defer all migration observability to the Phase 13.5 operator portal.** **Pattern:** Deferral. **Rejected** — the PR reviewer needs this *now*, at merge time; Phase 13.5 is many phases away, and the portal is for portfolio-level operators, not the per-PR human merger. Deferring leaves the "humans always merge" gate blind in the interim.

## Decision

Adopt **Option B.** Ship a migration observability bundle (`phase-arch-design.md §23`), all of it WARN/enrichment — none of it blocks:

1. **Typed `transformations_applied: tuple[TransformationKind, ...]`** on the migration record. `TransformationKind` is a closed sum type (`FromSwapped`, `RedundantRunDropped`, `HealthcheckRewritten`, `ChownAdded`, `EntrypointRewrittenToExecForm`, …) — each variant carries the affected instruction index. The PR-description renderer turns it into operator prose: *"swapped FROM, dropped 3 redundant RUN lines, rewrote 1 HEALTHCHECK, added --chown to 2 COPY lines."* This is gap **M3**.
2. **Typed enrichment events** into the spanning log ([production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)):
   - `MigrationSizeRegression` — pre/post compressed image size; a multi-stage refactor can balloon the image (gap **G14**).
   - `pre_migration_image_ref` capture so the PR can carry a rollback runbook — *"to roll back, redeploy `<digest>`"* (gap **G15**).
   - an **attestation diff** — Chainguard ships a signed SBOM + SLSA provenance the source image lacks; the PR surfaces the gained attestations (gap **G16**).
3. **Cross-CVE content-cache reuse** of the heavy `ShellInvocationTraceProbe` output, keyed on `(Dockerfile-digest, package.json-digest, image-digest)` (gap **G17**). Two CVEs filed against the same repo on the same day hit the cache; the microVM build runs once, not twice.

The PR description is *rendered* from the typed data; the typed `transformations_applied` list and the events are the source of truth. A goldens fixture locks the rendered shape.

## Tradeoffs

| Gain | Cost |
|---|---|
| The human merger sees exactly what the recipe did and what risk it carries — "humans always merge" is an informed gate, not a rubber stamp | A typed `TransformationKind` sum type plus three event variants grow the schema; the migration-record edit is ADR-gated ([0029](0029-amend-byte-edit-allowlist-for-amendment-a.md)) |
| `transformations_applied` is machine-readable — Phase 11's merge-gate and Phase 13.5's portal consume the same typed data the PR renders | The renderer is one more thing to keep in sync, but it is a pure projection; a goldens fixture catches drift at every PR |
| Cross-CVE cache reuse (G17) skips a redundant microVM build — measurable cost saving when a repo gets multiple CVEs in a window | The cache key `(Dockerfile, package.json, image-digest)` must be exact; a stale hit would re-use a wrong trace — mitigated by content-addressing on all three digests |
| All of the bundle is WARN — it never blocks a migration; a missing size number or attestation diff degrades the PR description, not the merge | Enrichment that silently fails (e.g. `crane` cannot fetch the attestation) must WARN visibly, not vanish — handled by a warning ID, not a swallowed exception |

## Pattern fit

Implements **typed projection** (toolkit §Observability — the typed `transformations_applied` list and the spanning events are the source of truth; the PR prose is a view rendered from them, never hand-authored). The enrichment events instantiate **event sourcing** ([production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)) — the spanning log is canonical, the PR description is a projection. `TransformationKind` is a closed sum type, mirroring [ADR-0025](0025-migration-refusal-taxonomy.md)'s refusal taxonomy and the `MigrationConfidence` rollup ([ADR-0026](0026-migration-confidence-aggregation.md)) — Phase 7's consistent "make the outcome a typed value, not a string." The content-cache reuse mirrors the established `cache_strategy="content"` seam — keys derive from `declared_inputs`-style digests.

**Cache scope — explicitly distinct from [ADR-0008](0008-no-vuln-provenance-cache-in-phase-7.md).** ADR-0008 keeps `vuln.provenance` **uncached** (it is a derived query over moving facts). This ADR caches **only** the `ShellInvocationTraceProbe` output — a different cache, the probe's own `cache_strategy="content"` entry, and only for that one heavy probe. The two decisions do not conflict: ADR-0008 forbids a *provenance* cache; this ADR reuses a *probe-output* cache.

## Consequences

- The migration record gains a typed `transformations_applied: tuple[TransformationKind, ...]` field; `TransformationKind` is a new closed sum type under the plugin's schema. The additive edit is enumerated in [ADR-0029](0029-amend-byte-edit-allowlist-for-amendment-a.md).
- Three event variants — `MigrationSizeRegression`, the `pre_migration_image_ref` capture, the attestation diff — land as typed Pydantic events in the spanning log ([production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)).
- The PR-description renderer reads `transformations_applied` + the events and emits operator prose plus a rollback runbook (`redeploy <pre_migration_image_ref digest>`); a goldens fixture locks the rendered shape.
- The attestation diff (G16) reads the Chainguard-published signed SBOM + SLSA provenance via `crane` ([ADR-0028](0028-allowed-binaries-amendment-crane.md)).
- `ShellInvocationTraceProbe` reuses its content-cache entry keyed on `(Dockerfile-digest, package.json-digest, image-digest)`; a property test asserts two CVEs against the same repo on the same day boot the microVM once.
- Every bundle item is WARN: a migration with a ballooned image, a missing attestation diff, or an absent rollback ref still produces a PR — the PR description carries the warning, the merge is not blocked.
- A warning ID (`migration_observability.*`) is emitted when an enrichment cannot be computed — failure is loud, not swallowed.

## Reversibility

**High.** The entire bundle is enrichment — removing any item degrades the PR description but breaks no contract and blocks no migration. The `transformations_applied` list and the events are additive; dropping them is a localized revert. The content-cache reuse is a pure performance optimization — disabling it costs a redundant microVM build but changes no behavior.

## Evidence / sources

- `../final-design.md §Amendment A §A.2` gaps G14 (image-size delta), G15 (rollback runbook), G16 (attestation diff), G17 (cross-CVE cache), M3 (`transformations_applied`); §A.1 (every gap is GATHER / REFUSE / **WARN**)
- `../phase-arch-design.md §Component design — Amendment A §23` (migration observability bundle), §Harness engineering §Idempotence (`ShellInvocationTraceProbe` content-cached on `(image-digest, Dockerfile-digest, package.json-digest)`)
- [Phase 7 ADR-0008 — no `vuln_provenance_cache` in Phase 7](0008-no-vuln-provenance-cache-in-phase-7.md) (the distinct, uncached `vuln.provenance` derived query)
- [Phase 7 ADR-0002 — `ShellInvocationTraceProbe` runs in a microVM](0002-shell-invocation-trace-probe-runs-in-microvm.md) (the heavy probe whose output this ADR caches)
- [Phase 7 ADR-0028 — `ALLOWED_BINARIES` amendment for `crane`](0028-allowed-binaries-amendment-crane.md) (attestation/SBOM fetch)
- [production ADR-0009 — humans always merge](../../../production/adrs/0009-humans-always-merge.md), [production ADR-0034 — event sourcing canonical primitive](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)
