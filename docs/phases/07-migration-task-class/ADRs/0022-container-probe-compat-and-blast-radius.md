# ADR-0022: The migration blast radius includes deployment manifests; `ContainerProbeCompatProbe` analyses K8s/Compose/helm probes

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** amendment-a · g6 · blast-radius · deployment-manifests · static-analysis
**Related:** [0005](0005-probes-live-under-plugin-not-core-tree.md), [0009](0009-phase-7-byte-edit-allowlist-fence.md), [0021](0021-runtime-shell-invocation-probe.md), [0027](0027-migration-observability-bundle.md), [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

`final-design.md §Amendment A §A.2` gap G6, and §A.3 departure #1: **the migration's blast radius is not just the `Dockerfile`.** A distroless image has no shell and a reduced binary set. Any container health or liveness/readiness probe that depends on a shell or an absent binary silently breaks when the image is swapped:

- Dockerfile `HEALTHCHECK CMD curl -f http://localhost/health` — `curl` is not in a distroless runtime.
- Kubernetes `livenessProbe.exec.command: ["sh", "-c", "..."]` — no `/bin/sh`.
- Compose `healthcheck.test: ["CMD-SHELL", "..."]` — same.
- helm chart probe templates that render to either of the above.

The orchestrator sees a green build, a passing Dockerfile policy gate, a merged PR — and a deployment that fails its readiness gate, or worse, passes a now-no-op `exec` probe and routes traffic to an unhealthy pod. The design-of-record's gather pipeline never inspects deployment manifests. The Phase 2 `DeploymentProbe` **locates** `docker-compose.yml`, Kubernetes manifests, and helm charts — but only locates them; it performs no probe-compatibility analysis. `phase-arch-design.md §Component design — Amendment A §19` resolves G6 to a new plugin-internal probe that *analyses* the file set `DeploymentProbe` already finds.

## Options considered

- **Option A — Keep the migration `Dockerfile`-only.** The PR changes the `Dockerfile` and nothing else; deployment-manifest probes are out of scope. **Pattern:** Narrow blast radius. **Rejected** — it knowingly ships an image whose Kubernetes `exec` probes silently fail; the migration is "correct" only by a definition that ignores the runtime contract the manifests encode.
- **Option B — Widen the gather scope to deployment manifests via a new compat probe.** Ship `ContainerProbeCompatProbe`, analysing the file set Phase 2's `DeploymentProbe` already locates, and let the migration PR include a deployment-manifest change. **Pattern:** Blast-radius-aware gather; static manifest analysis.
- **Option C — Defer probe-compat to a separate, later phase.** Acknowledge the gap, file it, ship the Dockerfile-only migration now. **Pattern:** Scope deferral. **Rejected** — the probe breakage is *caused by this migration*. Deferring the analysis means knowingly shipping a change that breaks deployment probes and calling the breakage someone else's phase. Amendment A §A.1's governing principle — gather enough to transform correctly, or refuse — forbids it.

## Decision

Adopt **Option B.** Ship `ContainerProbeCompatProbe` at `plugins/distroless-migration--node--npm/probes/container_probe_compat_probe.py` — Layer B/C, `tier="task_specific"`, static, plugin-internal per [ADR-0005](0005-probes-live-under-plugin-not-core-tree.md), registered via `@register_probe`, obeying the frozen Probe ABC ([production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)).

The probe **consumes the file set the Phase 2 `DeploymentProbe` already locates** — `docker-compose.yml`, Kubernetes manifests, helm charts — and statically analyses each for shell-dependent or absent-binary-dependent probes:

- Dockerfile `HEALTHCHECK` using `curl`/`wget` or shell form,
- Kubernetes `livenessProbe`/`readinessProbe`/`startupProbe` with an `exec.command` that invokes `sh`/`bash` or a non-distroless binary,
- Compose `healthcheck.test` in `CMD-SHELL` form or with a shell-dependent command,
- helm chart probe templates rendering to either.

It emits `ContainerProbeCompatSlice`: one typed record per probe, carrying the manifest path, the probe kind, and the specific shell/binary dependency. A module-level `Final` catalog enumerates the probe-shape patterns per manifest family — data-driven, no branching.

**The migration PR's blast radius is explicitly wider than the `Dockerfile`.** Where a shell-dependent `exec` probe has a deterministic HTTP-probe equivalent (the app already exposes the health endpoint the `curl` probe targets), the recipe rewrites it and the PR includes the deployment-manifest change. Where the rewrite is non-deterministic, the finding is a WARN in the PR description ([ADR-0027](0027-migration-observability-bundle.md)) — surfaced for the human reviewer, never silently dropped.

`DeploymentProbe` is **not edited** — it still only locates the files. The analysis is entirely new and entirely plugin-internal.

## Tradeoffs

| Gain | Cost |
|---|---|
| The migration no longer ships an image whose K8s/Compose probes silently fail — the runtime contract the manifests encode is honored | The migration PR's diff is larger and crosses files an operator may not expect a "distroless migration" to touch; mitigated — the PR description's `transformations_applied` list names every manifest change |
| Reuses Phase 2 `DeploymentProbe`'s file-location output — no duplicate manifest discovery, no edit to `DeploymentProbe` | A coupling: the probe depends on `DeploymentProbe`'s located file set being accurate; if `DeploymentProbe` misses a manifest, the compat analysis misses it too — declared as a `requires` dependency so the coordinator orders them |
| Deterministic HTTP-probe rewrites are applied automatically; non-deterministic ones WARN — the human sees every probe the migration touched | Distinguishing deterministic from non-deterministic rewrites is a judgment the recipe must encode; an over-cautious WARN is acceptable, an over-confident rewrite is not |
| Static manifest analysis covers every probe declared, not just exercised paths — completeness, the property "ships broken" demands | helm charts must be analysed as templates (pre-render) or rendered; the probe analyses templates conservatively and reports `low` confidence where templating obscures the probe shape |
| Plugin-internal placement keeps the probe off the core tree ([ADR-0005](0005-probes-live-under-plugin-not-core-tree.md)) | One more probe in the plugin tree; `make check`'s registry test enumerates it regardless |

## Pattern fit

Implements **static analysis with a data-driven pattern catalog** — the per-manifest-family probe-shape patterns are a module-level `Final` catalog iterated at one call site, never an `if/elif` on manifest kind. Instantiates **Plugin / Registry** ([ADR-0005](0005-probes-live-under-plugin-not-core-tree.md)) and the frozen Probe ABC ([production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)). The `ContainerProbeCompatSlice` records are sum-typed by probe kind and manifest family — no stringly-typed dispatch. The probe declares a `requires` dependency on `DeploymentProbe`, using the coordinator's existing dependency-ordering seam rather than re-discovering files.

## Consequences

- `plugins/distroless-migration--node--npm/probes/container_probe_compat_probe.py` is a net-new file; its sub-schema `plugins/distroless-migration--node--npm/schema/container_probe_compat.schema.json` is net-new (`additionalProperties: false` at every node).
- The envelope schema gains one `$ref`; the plugin loader gains one additive import line — both enumerated in [ADR-0029](0029-amend-byte-edit-allowlist-for-amendment-a.md).
- `DeploymentProbe` (Phase 2) is **unchanged** — it still only locates manifests; the new probe declares `requires` on it.
- The migration recipe may now emit a deployment-manifest diff (HTTP-probe rewrite) in addition to the `Dockerfile` diff; non-deterministic cases WARN via [ADR-0027](0027-migration-observability-bundle.md)'s `transformations_applied` bundle.
- `MigrationConfidence` (M1) consumes the slice; a manifest with an unrewritable shell probe degrades migration confidence.
- Golden fixtures cover: a `HEALTHCHECK curl` Dockerfile, a K8s `exec: ["sh","-c",...]` liveness probe, a Compose `CMD-SHELL` healthcheck, a helm probe template, and a repo with no deployment manifests (empty slice).

## Reversibility

**Medium.** The probe `name` and `ContainerProbeCompatSlice` shape are the contract downstream consumers bind to; relocating the source file preserves it, and the pattern catalog is data. What is genuinely hard to reverse is the **policy** — once the migration PR is allowed to touch deployment manifests, narrowing the blast radius back to `Dockerfile`-only re-opens G6 and would require re-auditing every migration that rewrote a probe. The widened blast radius is a deliberate, ADR-recorded scope expansion, not an implementation detail.

## Evidence / sources

- `../final-design.md §Amendment A §A.2` (gap G6), §A.3 departure #1 (blast radius widens beyond the `Dockerfile`)
- `../phase-arch-design.md §Component design — Amendment A §19`
- [ADR-0005 — Probes live under the plugin, not the core tree](0005-probes-live-under-plugin-not-core-tree.md)
- [ADR-0021 — RuntimeShellInvocationProbe](0021-runtime-shell-invocation-probe.md) (sibling Amendment A shell-detection probe)
- [ADR-0027 — Migration observability bundle](0027-migration-observability-bundle.md) (`transformations_applied` / WARN surface)
- [production ADR-0007 — Probe contract preserved POC→service](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)
