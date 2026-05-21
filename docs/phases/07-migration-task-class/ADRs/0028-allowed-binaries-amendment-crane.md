# ADR-0028: `ALLOWED_BINARIES` gains `crane` for daemonless OCI manifest/config/SBOM fetch

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** amendment-a · subprocess-discipline · allowed-binaries · amendment · supply-chain
**Related:** [0009](0009-phase-7-byte-edit-allowlist-fence.md), [0015](0015-allowed-binaries-amendment-dive-buildx.md), [0019](0019-target-image-content-probe.md), [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md), [Phase 2 ADR-0001](../../02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md), [Phase 3 ADR-0012](../../03-vuln-deterministic-recipe/ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md)

## Context

`codegenie.exec.ALLOWED_BINARIES` is a closed frozenset; adding a binary requires an ADR amendment per [Phase 2 ADR-0001](../../02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md)'s omnibus discipline — subsequently amended by [Phase 3 ADR-0012](../../03-vuln-deterministic-recipe/ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md) (`npm`, `bwrap`, `sandbox-exec`, `jq`) and Phase 7 [0015](0015-allowed-binaries-amendment-dive-buildx.md) (`dive`, `docker buildx`).

Amendment A's `TargetImageContentProbe` ([0019](0019-target-image-content-probe.md), Gap G2) needs to fetch the recommended Chainguard image's manifest and config, plus its published SBOM, without standing up a Docker daemon. The probe is a pure read-only inventory — pulling and extracting a full image filesystem would be heavyweight and would couple a gather probe to daemon availability. A daemonless OCI registry client is required. `../final-design.md §Amendment A §A.3 ¶4` names the addition: "`ALLOWED_BINARIES` gains `crane` (target-image manifest + SBOM fetch for G2), in addition to the design-of-record's `dive` + `docker buildx`."

## Options considered

- **Option A — Add `crane` (the go-containerregistry OCI CLI).** **Pattern:** Daemonless, read-only, single-static-binary OCI client. A self-contained Go binary with no daemon dependency; `crane manifest` / `crane config` are stable, non-experimental subcommands.
- **Option B — Use `docker manifest inspect` instead of adding a binary.** **Pattern:** Reuse the Docker CLI already allowlisted via `docker buildx`. **Rejected** — `docker manifest` is an experimental subcommand and `docker manifest inspect` still requires a configured Docker context / daemon for some registry operations; the experimental surface is not a base to build a gather probe on.
- **Option C — Add `skopeo`.** **Pattern:** Daemonless OCI client (alternative to `crane`). **Rejected** — `skopeo` is a heavier dependency with a broader feature surface (copy, sync, signing) than the probe needs; `crane`'s smaller single-static-binary footprint is the lower supply-chain surface for an inventory-only use.

## Decision

Adopt **Option A.** Amend the closed `ALLOWED_BINARIES` frozenset in `src/codegenie/exec/__init__.py` to add exactly one new row: **`crane`**. The edit is authorized by the [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md) byte-edit allowlist amendment to [0009](0009-phase-7-byte-edit-allowlist-fence.md); no other entries change.

`crane` is the go-containerregistry OCI CLI — read-only and daemonless for the subcommands Phase 7 uses (`crane manifest`, `crane config`). It is consumed solely by `TargetImageContentProbe` ([0019](0019-target-image-content-probe.md)). All subprocess use continues to go through `codegenie.exec.run_allowlisted` / `run_external_cli`; the `forbidden-patterns` pre-commit hook still bans `shell=True`, `os.system`, and the rest repo-wide. `plugins/distroless-migration--node--npm/plugin.yaml requirements.external_tools` lists `crane` so the resolver fails fast if the runner image lacks it.

## Tradeoffs

| Gain | Cost |
|---|---|
| Honors [Phase 2 ADR-0001](../../02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md)'s amendment discipline — every new binary is ratified by ADR, not by quiet edit; mirrors [0015](0015-allowed-binaries-amendment-dive-buildx.md) and [Phase 3 ADR-0012](../../03-vuln-deterministic-recipe/ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md) | One ADR-amendment row in Amendment A; the cost of the closed-allowlist discipline, paid willingly |
| `crane` is daemonless — `TargetImageContentProbe` introspects registry metadata with no Docker daemon, keeping a read-only gather probe free of daemon coupling | One more binary in the supply-chain surface; mitigated by `crane`'s small single-static-binary footprint and the closed `ALLOWED_BINARIES` set |
| `crane manifest` / `crane config` are stable subcommands — no experimental-feature dependency, unlike `docker manifest` | `crane` must be provisioned into the Phase 5 runner image; documented in `plugin.yaml requirements.external_tools` so the resolver fails fast rather than the probe failing mid-run |
| Choosing `crane` over `skopeo` keeps the footprint to an inventory-only client — no copy/sync/signing surface the probe never uses | If a future probe needs `skopeo`-only capability, that is a fresh ADR amendment; the discipline holds |

## Pattern fit

Implements **Subprocess discipline via closed allowlist** ([Phase 2 ADR-0001](../../02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md), [Phase 3 ADR-0012](../../03-vuln-deterministic-recipe/ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md), Phase 7 [0015](0015-allowed-binaries-amendment-dive-buildx.md)): every external binary is ratified by ADR amendment; the frozenset is closed; all invocation flows through `run_allowlisted` / `run_external_cli`. Instantiates **Honest tool selection** — pick the lightest tool that does the job (`crane` over `skopeo`) and refuse the experimental subcommand path (`docker manifest`).

## Consequences

- `src/codegenie/exec/__init__.py` `ALLOWED_BINARIES` frozenset gains exactly one row: `"crane"`. The edit is authorized by the [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md) byte-edit allowlist amendment.
- `crane` is consumed only by `TargetImageContentProbe` ([0019](0019-target-image-content-probe.md)) via `codegenie.exec.run_external_cli`.
- `plugins/distroless-migration--node--npm/plugin.yaml` `requirements.external_tools` adds `crane`, joining `docker`, `dive`, and `docker-buildx` ([0015](0015-allowed-binaries-amendment-dive-buildx.md)); the resolver fails fast if the runner image lacks any of them.
- Phase 5's runner-image baseline is updated to provision `crane`; CI runner provisioning is out of Phase 7's surface but is named in `../final-design.md §Resource & cost profile`.
- The existing `ALLOWED_BINARIES` fence test enumerates the frozenset; its expected-membership assertion gains `"crane"`.
- If a future probe genuinely requires `skopeo` or another OCI tool, a fresh ADR amendment is required.
- Implemented in Amendment A Step 13 (`../final-design.md §A.2`, Gap G2; `High-level-impl.md` Step 13).

## Reversibility

**High.** Adding or removing a row in `ALLOWED_BINARIES` is a one-line change plus the corresponding ADR amendment. Removing `crane` if a future redesign no longer fetches target-image manifests is straightforward — the only consumer is `TargetImageContentProbe`, whose own removal would naturally retire the entry.

## Evidence / sources

- `../final-design.md §Amendment A §A.3 ¶4` ("`ALLOWED_BINARIES` gains `crane`"), §Resource & cost profile
- `../phase-arch-design.md §Component design — Amendment A §16` (`TargetImageContentProbe` — "Requires `crane` in `ALLOWED_BINARIES`")
- [0015 — `ALLOWED_BINARIES` gains `dive` and `docker buildx`](0015-allowed-binaries-amendment-dive-buildx.md)
- [0019 — `TargetImageContentProbe`](0019-target-image-content-probe.md)
- [Phase 2 ADR-0001 — Allowed binaries omnibus](../../02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md)
- [Phase 3 ADR-0012 — Amend ALLOWED_BINARIES with npm, bwrap, sandbox-exec, jq](../../03-vuln-deterministic-recipe/ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md)
