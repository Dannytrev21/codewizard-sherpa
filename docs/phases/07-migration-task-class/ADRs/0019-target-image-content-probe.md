# ADR-0019: `TargetImageContentProbe` inventories the Chainguard target image via `crane` + published SBOM so the recipe drops redundant layers

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** amendment-a · probe · target-image · content-cache · daemonless
**Related:** [0009](0009-phase-7-byte-edit-allowlist-fence.md), [0015](0015-allowed-binaries-amendment-dive-buildx.md), [0028](0028-allowed-binaries-amendment-crane.md), [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md), [production ADR-0001](../../../production/adrs/0001-layered-hybrid-orchestration.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

Amendment A (`../final-design.md §Amendment A §A.2`, Gap G2) found the gather pipeline inventories what the *source* repo does but never inventories what the *recommended Chainguard target image already provides*. Without that inventory the recipe re-imports the present: it keeps a `RUN apk add ca-certificates` the target already ships, keeps a `RUN adduser` when the target already has `nonroot` (uid 65532), or assumes a `/bin/sh` the distroless target does not have. The result is a larger image, redundant layers, or a build that depends on a shell that is not there.

The recipe needs a typed inventory of the target: preinstalled packages, preinstalled users, CA-certificate presence, whether a shell is present (`shell_present: bool` is load-bearing — it drives whether shell-form `ENTRYPOINT` can survive), supported architectures, and the exact-text source `RUN` lines the target makes redundant. Chainguard publishes a signed SBOM with every image; the `SbomProbe` machinery already exists to read SBOMs. The open question is *how* to fetch the target image's manifest and config.

## Options considered

- **Option A — Hardcode a static table of Chainguard image contents in a frozen YAML.** **Pattern:** Frozen lookup catalog. **Rejected** — Chainguard rebuilds and updates its images continuously; a static table drifts silently and the recipe acts on stale truth. The image digest is the only honest key.
- **Option B — Live `crane manifest` + `crane config` for the resolved digest, plus the Chainguard-published SBOM read through the existing `SbomProbe` machinery pointed at the target image.** **Pattern:** Daemonless OCI introspection, content-cached on the immutable digest.
- **Option C — `docker pull` the target image and inspect its filesystem.** **Pattern:** Filesystem inspection via the Docker daemon. **Rejected** — requires a running Docker daemon, is heavier (full layer download + extraction), and couples a read-only inventory probe to daemon availability for no gain over `crane`.

## Decision

Adopt **Option B.** Ship `TargetImageContentProbe` at `plugins/distroless-migration--node--npm/probes/target_image_content_probe.py` — Layer E, `tier="task_specific"`, static, `cache_strategy="content"`, `declared_inputs=["image-digest:<target-resolved>"]`. It obeys the frozen Probe ABC ([production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)), registers via `@register_probe`, and lives under the plugin per [0005](0005-probes-live-under-plugin-not-core-tree.md).

The probe fetches the recommended Chainguard image's manifest and config via `crane manifest` + `crane config` for the resolved digest, and reads the Chainguard-published SBOM through the existing `SbomProbe` machinery pointed at the *target* image. It is a pure parse — no build, no daemon. It emits `TargetImageContentSlice`: `preinstalled_packages`, `preinstalled_users` (including `nonroot` uid 65532), a `ca_certificates` flag, `shell_present: bool` (load-bearing), `default_workdir`, `default_entrypoint`, `supported_architectures`, and `already_satisfied_run_lines` — the exact-text source `RUN` lines the target image makes redundant.

Because the target image digest is immutable, `cache_strategy="content"` keyed on `image-digest:<target-resolved>` makes the fetch a one-time cost per digest across the portfolio. `crane` is read-only and daemonless; its addition to `ALLOWED_BINARIES` is ratified by [0028](0028-allowed-binaries-amendment-crane.md). All invocation goes through `codegenie.exec.run_external_cli`.

## Tradeoffs

| Gain | Cost |
|---|---|
| The recipe drops `RUN` lines the target already satisfies — smaller image, fewer layers, no re-import of the present | The probe makes a network fetch to a registry; mitigated by content-caching on the immutable digest — one fetch per digest, reused across every CVE and repo |
| `crane` is daemonless and read-only — no Docker daemon dependency for a read-only inventory | One new binary in `ALLOWED_BINARIES` ([0028](0028-allowed-binaries-amendment-crane.md)); ratified by ADR amendment per the closed-allowlist discipline |
| Keying on the digest, not an image tag, means the inventory never drifts — a re-tagged image is a new digest is a new cache key | A registry outage degrades the probe; it reports `confidence: "low"` and `MigrationConfidence` ([0026](0026-migration-confidence-aggregation.md)) rolls up `Degraded`, escalating to HITL rather than guessing |
| Reuses the existing `SbomProbe` machinery rather than a second SBOM reader — one SBOM-parsing surface | The `SbomProbe` machinery must accept being pointed at a target image, not only the source repo; a small additive parameter, no contract break |

## Pattern fit

Instantiates **Daemonless OCI introspection** — `crane` reads registry metadata without a Docker daemon, mirroring the read-only posture Phase 7 already takes for image lookups. Instantiates **Content-addressed caching** (CLAUDE.md §Registry-dispatched coordinator — `cache/` is content-addressed off `declared_inputs`): the immutable digest is the perfect cache key. Instantiates **Reuse over reinvention** (production ADR-0001 layered-hybrid composition): the existing `SbomProbe` machinery is pointed at a new target rather than duplicated.

## Consequences

- `plugins/distroless-migration--node--npm/probes/target_image_content_probe.py` is a net-new file; its sub-schema `.../schema/target_image_content.schema.json` (`additionalProperties: false` at every node) is net-new.
- The envelope `src/codegenie/schema/repo_context.schema.json` gains one `$ref`; `src/codegenie/plugins/loader.py` gains one additive import line — authorized by the [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md) byte-edit allowlist amendment to [0009](0009-phase-7-byte-edit-allowlist-fence.md).
- `src/codegenie/exec/__init__.py` `ALLOWED_BINARIES` gains `crane` — ratified by [0028](0028-allowed-binaries-amendment-crane.md). `plugin.yaml requirements.external_tools` lists `crane` so the resolver fails fast.
- The `DockerfileBaseImageSwapTransform` and `DockerfileMultiStageRefactorTransform` recipes gain a typed `TargetImageContents` input and consult `already_satisfied_run_lines` to drop redundant lines (`../final-design.md §A.3 ¶2`).
- Golden fixtures land under `tests/golden/probes/target_image_content/` with recorded `crane` manifest/config + SBOM responses so tests are hermetic.
- Implemented in Amendment A Step 13 (`../final-design.md §A.2`, Gap G2; `High-level-impl.md` Step 13).

## Reversibility

**Medium.** The probe `name` and `TargetImageContentSlice` shape are the load-bearing contract the recipe consumes; relocating or rewriting the internals is cheap. Reversing the **policy** — replacing live `crane` introspection with a static table — would reintroduce the silent-drift failure G2 exists to close and is not a path back worth taking. Removing `crane` from `ALLOWED_BINARIES` is a one-line change plus an ADR amendment.

## Evidence / sources

- `../final-design.md §Amendment A §A.2` (Gap G2), `§A.3 ¶4` (`ALLOWED_BINARIES` gains `crane`)
- `../phase-arch-design.md §Component design — Amendment A §16` (`TargetImageContentProbe`)
- [0028 — `ALLOWED_BINARIES` gains `crane`](0028-allowed-binaries-amendment-crane.md)
- [0015 — `ALLOWED_BINARIES` gains `dive` and `docker buildx`](0015-allowed-binaries-amendment-dive-buildx.md)
- [production ADR-0001 — Layered hybrid orchestration](../../../production/adrs/0001-layered-hybrid-orchestration.md)
- [production ADR-0007 — Probe contract preserved POC to service](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)
