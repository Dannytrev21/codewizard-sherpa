# ADR-0012: Static env allowlist + CI-enforced denied substrings — no credentials in sandbox

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** security · credentials · enforcement
**Related:** [ADR-0014](0014-objectivesignals-extra-forbid-static-introspection.md), [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)

## Context

The orchestrator process holds every credential the system uses — `ANTHROPIC_API_KEY` (Phase 4), grype DB tokens (cve_delta), registry creds (cgr.dev pulls). The sandbox executes LLM-influenced code; an LLM patch that exfiltrates an env var via `npm postinstall` is a documented adversarial path ([phase-arch-design.md §Edge case 5](../phase-arch-design.md#edge-cases)). Best-practices' design left env-allowlist documentation in a comment; the critic flagged "comment-only enforcement" as no enforcement. Security-first wanted "no env inheritance" — too strict (NPM_CONFIG_* is needed for `npm ci`). The synthesis: explicit allowlist + CI test on denied substrings. See [final-design.md §Synthesis ledger row: Env into sandbox](../final-design.md#synthesis-ledger).

## Options considered

- **No env inheritance** — Sandbox starts with empty env. `npm ci` fails (needs PATH, NPM_CONFIG_*, HTTPS_PROXY). Forces every variable to be configured per-gate; high friction.
- **Comment-only allowlist** — Document the allowlist in code comments; trust contributors not to add credentials. Critic: not enforcement.
- **Static allowlist module + CI test** — `env_allowlist.py` declares the allowlist; `env_allowlist.filter(env)` is the only path from orchestrator env to `SandboxSpec.env`; CI test asserts denied substrings (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`) cannot pass even if added to the allowlist.

## Decision

`src/codegenie/sandbox/env_allowlist.py` declares the allowlist (`PATH`, `NODE_ENV`, `NPM_CONFIG_*`, `HTTPS_PROXY`). `SandboxSpecBuilder` calls `env_allowlist.filter(env)` to populate `SandboxSpec.env`. `tests/schema/test_env_allowlist_no_credentials.py` asserts that an env dict containing `*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*` substrings returns an env without those keys, even if those keys are accidentally added to the allowlist.

## Tradeoffs

| Gain | Cost |
|---|---|
| Credentials cannot leak via env into the sandbox — enforced by code + CI, not by comment | Adding a legitimately-needed env var requires editing `env_allowlist.py` + ADR amendment if it touches new namespaces |
| The denied-substring check is *belt and suspenders* — even an operator who adds `MY_API_KEY` to the allowlist fails CI | Operators learn the allowlist; new envs require explicit additions; friction is real |
| Static module is one source of truth — Phase 7+ inherits with zero edits | Substring matching has false positives (a var named `KEYBOARD_LAYOUT` would be filtered) — acceptable; not a real-world env var name in our stack |
| `SandboxSpecForbidden` is raised loudly on a denied substring; fails fast at build time | Per-gate env customization (e.g., a specific gate needing `CI=true`) requires touching the allowlist instead of inline |

## Consequences

- `src/codegenie/sandbox/env_allowlist.py` is the only module that translates host env → sandbox env.
- `SandboxSpecBuilder` consumes the filter; no other path exists.
- `tests/schema/test_env_allowlist_no_credentials.py` runs every CI build.
- `SandboxSpec.env: Mapping[str, str]` is the post-filter view; the pre-filter env never enters a Pydantic model.
- New invariant: any new credential the orchestrator handles inherits this allowlist policy by default (no opt-out).
- Phase 4's `ANTHROPIC_API_KEY` cannot reach the sandbox — verified by adversarial test in `tests/adversarial/test_postinstall_exfil.py`.

## Reversibility

**Low.** Loosening the allowlist (allowing more inheritance) re-opens the credential-leak vector with no compensating defense. Tightening further (no inheritance) breaks `npm ci`. The denied-substring CI test could be relaxed but its bytes-on-disk cost is near zero; there is no reason to.

## Evidence / sources

- [final-design.md §Synthesis ledger — Env into sandbox row](../final-design.md#synthesis-ledger) (winner score 11)
- [phase-arch-design.md §Goals 7](../phase-arch-design.md#goals)
- [phase-arch-design.md §Component design — SandboxSpecBuilder](../phase-arch-design.md#sandboxspecbuilder)
- [phase-arch-design.md §Testing strategy — CI gates](../phase-arch-design.md#ci-gates)
- [phase-arch-design.md §Adversarial tests — test_postinstall_exfil](../phase-arch-design.md#adversarial-tests)
