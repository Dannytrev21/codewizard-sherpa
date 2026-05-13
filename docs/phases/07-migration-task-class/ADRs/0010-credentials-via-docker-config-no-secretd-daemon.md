# ADR-0010: Credentials live in operator's `~/.docker/config.json` — no `codegenie-secretd` daemon

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** credentials · security · claude-md-veto · simplicity-first
**Related:** [ADR-0003](0003-objective-signals-widening-and-allowlists.md), [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md)

## Context

`docker buildx build` against `cgr.dev/chainguard/*` requires authentication to the Chainguard registry. All three lens designs proposed different credential-handling positions (`critique.md §security.4`, `final-design.md §Conflict-resolution row 4`):

- `[P]` and `[B]` punt to the operator's existing `~/.docker/config.json` — the file every CI pipeline already uses; Phase 7 does not read it, store it, mint tokens against it, or daemonize anything.
- `[S]` proposed `codegenie-secretd` — a per-host credential broker daemon with its own Unix user, AF_UNIX socket, systemd unit, `age`-encrypted credential file, separate audit chain, and tamper-detection on startup. Production-shaped credential infrastructure dropped into a local POC.

The critic landed hard (`§security.4`): `codegenie-secretd` directly violates `CLAUDE.md`'s explicit veto — *"Single Python project, no services, no databases. Filesystem-backed everything."* The synthesizer's conflict-resolution score (`final-design.md` row 4a) records `commitments-fit = 0 (veto)` — a hard rejection, not a tradeoff.

The decision is small in code (Phase 7 does not write a daemon) and large in framing (it pins where production-grade credential handling lives: Phase 16, *as a service*, not as a local-POC daemon).

## Options considered

- **`codegenie-secretd` per-host daemon (`[S]`).** Vetoed by `CLAUDE.md`; commitments-fit = 0.
- **In-process credential cache, encrypted at rest via OS keychain (macOS Keychain / `secret-tool` on Linux).** Cross-platform OS keychain integration is itself non-trivial; operators without a desktop keychain (CI runners) pay the `age` cost; deferred to Phase 16.
- **Operator-side `~/.docker/config.json` only (synthesizer's pick).** Operator manages credentials exactly as they do for every other `docker` invocation; Phase 7's code never touches the file. `cgr.dev` and `docker.io` get added to Phase 5's egress allowlist (ADR-0003) so the Docker daemon's pulls go through.

## Decision

Phase 7 does not read, store, mint, broker, daemonize, or in any way manage credentials. The operator's existing `~/.docker/config.json` is the credential surface; the operator's Docker daemon is the authenticated client. `cgr.dev` and `docker.io` are added to Phase 5's egress allowlist via ADR-0003 (ADR-P7-002). The strace probe's workload runs `--network=none` and so has no network and no credential exposure inside the sandbox. Production-grade credential handling is Phase 16's job (*as a service*, not as a POC daemon).

## Tradeoffs

| Gain | Cost |
|---|---|
| `CLAUDE.md` "Single Python project, no services, no databases" honored verbatim — no daemon, no socket, no systemd unit, no Unix user, no encryption-at-rest infrastructure | No secrets isolation beyond OS posix perms (whatever protects `~/.docker/config.json`) — a single shared credential per operator, not per-workflow |
| Phase 7's code surface area is dramatically smaller — no `~80 LOC age-encrypted on-disk credential file + AF_UNIX broker + tamper-detection + secretd audit chain` to test, version, harden | Operators who want per-workflow credential isolation must wait for Phase 16; Phase 7 cannot serve regulated workloads that require credential broker semantics |
| Operator-side `~/.docker/config.json` is the most familiar credential surface in container ecosystems — zero learning curve, zero new operational discipline | If the operator's `~/.docker/config.json` is missing or unauthenticated for `cgr.dev`, the first `docker buildx build` fails with a registry auth error — caught at `validate_in_sandbox` with a clear CLI exit 11 (edge-cases row 7) |
| The Phase 16 production hardening story stays unforked — one credential-broker design lands as a *service*, not retrofitted from a half-shipped daemon | The synthesizer's veto carries a "production credential broker is Phase 16's job *as a service*" note; if Phase 16 lands later than expected, regulated workloads block on it |

## Consequences

- Phase 7 source code does not import any credential library; fence-CI denies `keyring`, `oauth`, `vault` SDK imports under Phase 7 modules.
- `cgr.dev` and `docker.io` are on Phase 5's egress allowlist (ADR-0003). The Docker daemon authenticates against `cgr.dev` using the operator's `~/.docker/config.json`; the orchestrator never touches the file.
- The workload inside `ShellInvocationTraceProbe`'s sandbox runs `--network=none` — no credential exposure inside the sandbox.
- Operator-facing CLI exit 11 with a clear "Chainguard registry auth failed; check `~/.docker/config.json`" message on `RegistryAuthFailed` (phase-arch-design edge-cases row 7).
- Phase 16's credential-broker design is the documented hand-off — *as a service*, with TEE/SGX/SEV or a per-workflow ephemeral KMS-leased credential.
- The decision is permanent for Phase 7's local-POC era; Phase 8/9 inherit the same posture (still single-process Python until Phase 9's Temporal lift).

## Reversibility

**High for hardening, low for relaxing further.** Re-adding a credential daemon in Phase 16 is the planned path — no Phase 7 code blocks it; the operator-side surface remains a no-op. Relaxing further (e.g., the orchestrator reading `~/.docker/config.json` to mint per-workflow tokens) breaks `CLAUDE.md`'s "no services" and would require this ADR to be amended. The asymmetry is intentional — production credential handling deserves a real design phase.

## Evidence / sources

- `../final-design.md §Goals#14` ("Operator-side `~/.docker/config.json` only")
- `../final-design.md §Conflict-resolution row 4 + row 4a (veto)` (codegenie-secretd vetoed; commitments-fit=0)
- `../final-design.md §"Load-bearing commitments check" "CLAUDE.md"` (no services honored)
- `../phase-arch-design.md §Goals G17` (Credential surface)
- `../phase-arch-design.md §Non-goals #1` (no `codegenie-secretd`)
- `../critique.md §security.4` (the secretd-daemon attack)
- `CLAUDE.md` (project rules: "Single Python project, no services, no databases. Filesystem-backed everything.")
- [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md) — sandbox boundary
