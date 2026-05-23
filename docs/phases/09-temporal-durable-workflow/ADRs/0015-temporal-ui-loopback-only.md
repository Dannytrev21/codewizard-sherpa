# ADR-0015: `temporal-ui` bound to `127.0.0.1:8233` only

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** dev-surface · attack-surface · fence
**Related:** [ADR-0008](0008-typed-credential-blocklist-not-regex.md)

## Context

`temporal-ui` (Temporal's web UI) is one of the highest-value dev affordances Phase 9 ships: an engineer can browse live and past workflows, see activity dispatches and signals, inspect payloads, terminate stuck workflows, replay histories. It also exposes the same control plane to anyone who can reach the bind address — `temporal-ui` does not ship with authentication suitable for an exposed port.

The choice is between exposing the UI on `0.0.0.0:8233` (convenient for sharing with teammates, accessible from VMs, reachable across the local network) and binding to `127.0.0.1:8233` only (loopback, accessible only from the host running Docker). The security-first design [S] was emphatic that any non-loopback bind is a footgun the team will eventually regret. The performance-first design [P] silently bound to `0.0.0.0` ("for convenience"). The critic's destruction of [P] showed this is the canonical case where convenience defaults erode against the attacker model: an engineer working from a coffee-shop wifi exposes their dev cluster to the local subnet.

Production exposure of any workflow control surface is a Phase-13.5/Phase-16 question — the operator portal authenticates against the canonical event log via `read_role`, not against Temporal directly. Phase-9's `temporal-ui` is dev-only.

## Options considered

- **Bind `0.0.0.0:8233` by default.** "Just works" from VMs and team browsers. **Pattern:** convenience default. Attack surface = whatever subnet the dev box is on.
- **Bind `127.0.0.1:8233` by default; document an SSH-tunnel pattern for remote access.** Loopback-only; remote inspection via `ssh -L 8233:127.0.0.1:8233 dev-box`. **Pattern:** secure default + documented escape. Attack surface = the dev box's loopback only.
- **Bind `127.0.0.1:8233` and add a fence test that grep-rejects `0.0.0.0` patterns across `scripts/`, `infra/`, `Makefile`.** **Pattern:** secure default + structural enforcement.

## Decision

`temporal-ui` binds `127.0.0.1:8233`. `scripts/temporal-dev.sh` rejects `--ip 0.0.0.0` (and any non-loopback wildcard pattern) at argument-parse time. `tests/fence/test_temporal_ui_loopback.py` grep-rejects `0.0.0.0` across `scripts/`, `infra/`, `Makefile`. The G2 exit criterion encodes this. **Pattern: secure default + structural enforcement.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Dev cluster control plane is loopback-only; not reachable from the local subnet | Sharing the UI with a teammate requires an SSH tunnel — one extra step |
| The fence test makes future "let me just expose this for a demo" PRs into build breaks — forces the discussion | Every script/yml that *legitimately* binds `0.0.0.0` for an unrelated service (e.g., docs preview) must add a comment explaining why — a small grep-noise cost |
| The G2 exit criterion is verifiable mechanically | If `temporal-ui` itself ever changes its default bind to something other than `127.0.0.1`, the docker-compose override must keep pace |
| Production exposure question is properly deferred to Phase 13.5 / 16 — no premature "let's add OAuth to dev-mode `temporal-ui`" | Engineers expecting "the UI is shared at our team's dev URL" have to learn the SSH-tunnel pattern |
| Convention is documented; future contributors can read this ADR before trying to relax the bind | The fence test must be updated if a *legitimate* `0.0.0.0` use lands elsewhere — small ongoing maintenance cost |

## Pattern fit

Secure default + structural enforcement is the toolkit's `design-patterns-toolkit.md §Fail-secure defaults` shape: the default is the safe choice; deviating from it requires explicit code (which the fence catches). The Phase-2 `_GENERATOR_HEADER_MARKERS` and `forbidden-patterns` pre-commit hooks are precedent — the codebase prefers structural defenses (grep-able patterns, fence tests) over runtime checks for footgun avoidance.

## Consequences

- `infra/docker-compose.dev.yml` binds `temporal-ui` to `127.0.0.1:8233`.
- `scripts/temporal-dev.sh` parses `--ip` and rejects `0.0.0.0` patterns at argparse time.
- `tests/fence/test_temporal_ui_loopback.py` is a new fence test — greps `scripts/`, `infra/`, `Makefile` for `0.0.0.0`; any match must have an inline `# fence-allowlist: <reason>` comment or fail.
- `docs/development.md` documents the SSH-tunnel pattern for sharing the UI: `ssh -L 8233:127.0.0.1:8233 <dev-host>`.
- Production exposure of any workflow control surface is *not* this ADR's scope — Phase 13.5 lands the operator portal, which reads `events.events` via `read_role` (not Temporal cluster auth).
- G2 exit criterion (`tests/fence/test_temporal_ui_loopback.py` greps every checked-in script for `0.0.0.0`; `scripts/temporal-dev.sh` rejects `--ip 0.0.0.0`) is verifiable.

## Reversibility

**High.** Reverting to `0.0.0.0` is one config change + one fence-test deletion. The decision is conservatism; relaxation is cheap. The cost of having relaxed it once and being attacked is unbounded.

## Evidence / sources

- [`../phase-arch-design.md §Goals G2 — temporal-ui on 127.0.0.1:8233`](../phase-arch-design.md#goals)
- [`../phase-arch-design.md §C9 — Local dev surface`](../phase-arch-design.md#c9--local-dev-surface-infradocker-composedevyml-scriptstemporal-devsh)
- [`../phase-arch-design.md §Physical view`](../phase-arch-design.md#physical-view--where-does-this-code-run)
- [`../critique.md §Attacks on the performance-first design — temporal-ui exposure`](../critique.md)
- [`../final-design.md §Synthesis ledger — temporal-ui exposure row`](../final-design.md)
- Precedent: Phase-2 `forbidden-patterns` pre-commit hook
