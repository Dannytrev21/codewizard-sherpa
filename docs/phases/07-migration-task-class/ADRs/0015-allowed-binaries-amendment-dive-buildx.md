# ADR-0015: `ALLOWED_BINARIES` gains `dive` and `docker buildx`; `strace` is explicitly NOT added

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** subprocess-discipline · allowed-binaries · amendment · supply-chain
**Related:** [0002](0002-shell-invocation-trace-probe-runs-in-microvm.md), [0009](0009-phase-7-byte-edit-allowlist-fence.md), [Phase 2 ADR-0001](../../02-phase-2-layer-bg-probes/ADRs/0001-amend-allowed-binaries-omnibus.md), [Phase 3 ADR-0012](../../03-vuln-deterministic-recipe/ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md)

## Context

`codegenie.exec.ALLOWED_BINARIES` is a closed frozenset; adding a binary requires an ADR amendment per Phase 2 ADR-0001's omnibus discipline (subsequently amended by Phase 3 ADR-0012 for `npm`, `bwrap`, `sandbox-exec`, `jq`). Phase 7 introduces two new tools that warrant entries:

- **`dive`** — used in supply-chain validation to inspect image-layer composition. `BaseImageProbe` references it (consulted, not invoked, in the static path); plugin recipe tests use it for assertions.
- **`docker buildx`** — used by `DistrolessBuildGate` inside the microVM to build the migrated image and by `ShellInvocationTraceProbe` (via `SandboxClient.spawn(role=Role.PROBE)`) to run the builder stage.

The best-practices lens design also proposed adding `strace` to `ALLOWED_BINARIES`. The critic flagged this in §"Hidden assumptions §2": `strace` requires `CAP_SYS_PTRACE`, which is non-trivial inside Phase 5's microVM constraints; "the design says 'the last already present on Linux' as if presence implies usability." `final-design.md §Goals` rejects `strace` outright: trace observation happens via Phase 5's existing eBPF host-side view, not via in-VM `strace`.

`final-design.md §Goals` and `phase-arch-design.md §Component design §9` lock the two-binary addition + `strace` rejection. The fence allowlist ([0009](0009-phase-7-byte-edit-allowlist-fence.md) row #8) authorizes the `ALLOWED_BINARIES` edit.

## Options considered

- **Option A — Add `dive`, `docker buildx`, and `strace`.** Best-practices' proposal. Most permissive. `strace`'s `CAP_SYS_PTRACE` requirement and Phase 5 microVM constraints make it operationally fragile.
- **Option B — Add only `dive` and `docker buildx`; observe shell invocations via Phase 5's eBPF host-side view.** **Pattern:** Out-of-VM observation (mirrors Phase 5's host-side gate-trace discipline).
- **Option C — Add `docker buildx` only; defer `dive` until a concrete recipe needs it.** **Rejected** — `BaseImageProbe` tests reference `dive` for portfolio-fixture assertions; deferring forces a Phase-7-amendment-via-amendment path later.

## Decision

Adopt **Option B.** `codegenie.exec.ALLOWED_BINARIES` gains exactly two new rows: **`dive`** and **`docker buildx`**. `strace` is **not** added. Shell-invocation trace observation in `ShellInvocationTraceProbe` ([0002](0002-shell-invocation-trace-probe-runs-in-microvm.md)) happens via Phase 5's existing eBPF host-side view — the in-VM `strace` is informational only and is not invoked by Phase 7 code paths. The fence allowlist ([0009](0009-phase-7-byte-edit-allowlist-fence.md) row #8) authorizes the two-row edit to `src/codegenie/exec/__init__.py`; no other entries change.

## Tradeoffs

| Gain | Cost |
|---|---|
| Honors [Phase 2 ADR-0001](../../02-phase-2-layer-bg-probes/ADRs/0001-amend-allowed-binaries-omnibus.md)'s amendment discipline: each new binary is ratified by ADR, not by quiet edit | Two ADR-amendment rows in Phase 7; mirrors Phase 3 ADR-0012's amendment pattern |
| `docker buildx` is the canonical Docker build CLI for multi-stage and buildx-cache scenarios; using it (vs. legacy `docker build`) is forward-compatible with Phase 8's warm-pool work | `docker buildx` requires Docker 20.10+; Phase 5's runner-image baseline must satisfy this. Documented in plugin's `plugin.yaml requirements.external_tools` |
| `dive` is consumed by tests/fixtures and (optionally) by future portfolio-validation checks; having it allowlisted up-front avoids the "we needed it for a test, ship a hotfix" pattern | One more binary in the supply-chain surface; mitigated by `dive`'s small footprint and the closed `ALLOWED_BINARIES` set |
| Rejecting `strace` keeps Phase 5's microVM constraints honest — no `CAP_SYS_PTRACE` expansion, no in-VM privileged tool | If a future probe genuinely requires `strace` (rather than eBPF host-side), it must file its own ADR amendment; that's the discipline |
| The eBPF host-side view is the canonical shell-trace surface — one observation mechanism, not two (one in-VM, one out-of-VM) | Operators inspecting the probe's behavior must learn to read eBPF traces, not `strace` output. Mitigated by the probe's audit-event schema (`ShellInvocationObserved(count, locations)`) |

## Pattern fit

Implements **Subprocess discipline via closed allowlist** ([Phase 2 ADR-0001](../../02-phase-2-layer-bg-probes/ADRs/0001-amend-allowed-binaries-omnibus.md), [Phase 3 ADR-0012](../../03-vuln-deterministic-recipe/ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md)): every external binary is ratified by ADR amendment; the frozenset is closed; the `forbidden-patterns` pre-commit hook bans `shell=True` etc. across the repo. Also instantiates **Honest tool selection** — refuses to add tools whose isolation costs are not paid (`strace` + `CAP_SYS_PTRACE` in a shared-kernel context).

## Consequences

- `src/codegenie/exec/__init__.py` `ALLOWED_BINARIES` frozenset gains exactly two rows: `"dive"` and `"docker buildx"`. The edit is authorized by fence allowlist row #8 ([0009](0009-phase-7-byte-edit-allowlist-fence.md)).
- `strace` is **not** added; a fence test (`tests/fence/test_phase7_no_strace.py` or extension of the existing `ALLOWED_BINARIES` fence) asserts `"strace" not in ALLOWED_BINARIES`.
- `plugins/distroless-migration--node--npm/plugin.yaml` lists `requirements.external_tools: [docker, dive, docker-buildx]` so the resolver fails fast if the runner image lacks them.
- Phase 5's microVM constraints are unchanged — no `CAP_SYS_PTRACE` is requested for any role (`Role.GATE` or `Role.PROBE`).
- The eBPF host-side trace view (Phase 5's existing capability) is the canonical shell-invocation observation surface for `ShellInvocationTraceProbe`.
- If a future probe genuinely requires `strace` (or another `CAP_*`-elevated tool), a fresh ADR amendment is required; it must include the threat-model analysis Phase 5 wants.
- Phase 5's runner-image baseline is updated to ensure `docker buildx` is present; CI runner provisioning is out of Phase 7's surface but is named in `final-design.md §Resource & cost profile`.

## Reversibility

**High.** Adding or removing rows in `ALLOWED_BINARIES` is one-line changes plus the corresponding ADR amendment. Removing `dive` if a future redesign no longer uses it is straightforward; adding `strace` later if a strong threat-model justification emerges is straightforward (with the corresponding ADR work).

## Evidence / sources

- `../final-design.md §Goals` ("Net-new runtime Python deps: 1 (`dockerfile-parse`). Two new CLI binaries in `ALLOWED_BINARIES`: `dive`, `docker buildx`. […] `strace` is NOT added"), §Resource & cost profile
- `../phase-arch-design.md §Component design §9` (`ShellInvocationTraceProbe` — "The in-VM `strace` is informational only and is NOT added to `ALLOWED_BINARIES`"), §Testing strategy §Adversarial tests
- `../critique.md §Attacks on the best-practices design "Hidden assumptions §2"` (`strace` requires `CAP_SYS_PTRACE`, "the last already present on Linux" — presence ≠ usability)
- [Phase 2 ADR-0001 — Allowed binaries omnibus](../../02-phase-2-layer-bg-probes/ADRs/0001-amend-allowed-binaries-omnibus.md)
- [Phase 3 ADR-0012 — Amend ALLOWED_BINARIES with npm, bwrap, sandbox-exec, jq](../../03-vuln-deterministic-recipe/ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md)
