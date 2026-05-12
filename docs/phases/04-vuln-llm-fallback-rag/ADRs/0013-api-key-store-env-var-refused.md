# ADR-0013: `ApiKeyStore` — `ANTHROPIC_API_KEY` env-var refused at orchestrator start; mode-600 file / OS keyring only; OS-tiered strictness

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** secret-handling · supply-chain · synthesizer-departure
**Related:** [ADR-0004](0004-leaf-llm-agent-protocol-os-tiered.md)

## Context

The Anthropic SDK reads the API key from `ANTHROPIC_API_KEY` env-var by default. Every shell history, every `ps -E`, every crash dump that captures env vars, every CI log that prints env contains the key. The performance lens accepted this default (`import anthropic` picks up the key wherever). The security lens stored the key in an egress-proxy daemon and refused env-var-only setups. Best-practices punted (no key-handling discipline).

The synthesis adopts the security-lens key handling without the egress-proxy process isolation (which is Phase 5's microVM job). The key-handling discipline (no env var on Linux; no plaintext log; no audit body) is cheap to ship in Phase 4 and is load-bearing.

## Options considered

- **Env var (`ANTHROPIC_API_KEY`).** Anthropic SDK default. Easy. Every shell history, crash dump, CI log, `/proc/<pid>/environ` leaks the key.
- **Mode-600 file with hard-refuse on env var.** Operator runs `codegenie auth set-anthropic-key` once. Key never enters env. Linux + macOS both work.
- **OS keystore (macOS Keychain, Linux secret-service).** Higher-trust storage. Adds a platform-specific dep (`security` CLI on Mac; `secretstorage` on Linux).
- **HSM-backed.** Production-grade. Operationally heavy for a local POC.

## Decision

`ApiKeyStore` reads the API key from platform-tiered locations and refuses env-var setups with OS-tiered strictness:

- **macOS:** `security find-generic-password -s codegenie-anthropic`. Bare `ANTHROPIC_API_KEY` env-var emits `audit.warning(api_key.env_present)` but does *not* refuse to start (dev ergonomics — macOS engineers iterate fast and surface in audit, not at startup).
- **Linux:** `secret-service` (preferred); fallback to mode-600 file at `~/.codegenie/secrets/anthropic-api-key` owned by operator, group `codegenie-secrets`. **Bare `ANTHROPIC_API_KEY` in orchestrator env is hard-refuse on Linux** — `codegenie remediate` exits non-zero with a clear error before any work starts.

The key is loaded into the `AnthropicClient` process only ([ADR-0004](0004-leaf-llm-agent-protocol-os-tiered.md)). The key never enters: prompt body, log line (only `blake3(key)[:8]` fingerprint), audit body, cassette, or any cache. Fence-CI forbids the key fingerprint from appearing in test output.

`ApiKeyStore.available() == False` if the key is missing → `RagLlmEngine.available() == False` → selector falls through to `reason="no_engine"` → Phase 3 path exits 4 cleanly. Operator runs `codegenie auth set-anthropic-key`.

## Tradeoffs

| Gain | Cost |
|---|---|
| Linux production-ish runs cannot accidentally leak the key via env (`/proc/<pid>/environ`, crash dumps, CI logs) — the hard-refuse at orchestrator start is conspicuous | Operator must run `codegenie auth set-anthropic-key` once per host; mild UX cost |
| macOS dev cycles stay fast (env var works with audit warning, Keychain works without) — engineers iterate without re-configuring | macOS engineers may have the key in env across reboots; surfaced as warning, not a refusal |
| Key is loaded only into `AnthropicClient` process — orchestrator address space never holds the bytes (Phase 5's microVM tightens this further) | macOS `InProcessLeafLlmAgent` *is* the orchestrator process — the boundary is logical, not enforced (surfaced as known threat-model concession) |
| `blake3(key)[:8]` fingerprint in logs lets operators distinguish keys (e.g., "is my dev key the same as CI's?") without leaking | One fingerprint is one extra observable; documented as not-trust-bearing |
| Fence-CI scan for API key fingerprint patterns in test output catches accidental log emission at build time | The scan is regex-based; novel key shapes (e.g., Anthropic rotates to a new prefix) require a scan update |
| `secret-service` and Keychain are platform-standard, low-friction, well-understood | Two platforms; two implementations; `secretstorage` adds a Linux pip dep |

## Consequences

- `ApiKeyStore` lives in `src/codegenie/llm/secrets/key_store.py`. Read-only API: `available() -> bool`, `read() -> str`. Callable only by `leaf_anthropic.*` and (when running) the `EgressProxy` daemon.
- `codegenie auth set-anthropic-key` is the documented setup path; `codegenie auth fingerprint` returns the `blake3(key)[:8]` for operator key identification.
- macOS env-var warning emits `audit.warning(api_key.env_present)`. Linux env-var presence triggers a hard exit with a specific error message pointing to `codegenie auth set-anthropic-key`.
- `tests/security/test_no_api_key_in_logs.py` scans every captured log fixture and asserts the key fingerprint pattern is absent. Build red on any test that logs the key.
- The egress proxy ([ADR-0004](0004-leaf-llm-agent-protocol-os-tiered.md)) strips agent-supplied `x-api-key` headers before forwarding — closes the smuggle channel from a compromised agent.
- Phase 5's microVM further isolates the key (host-side proxy + microVM agent that never sees the key); Phase 4's `ApiKeyStore` discipline is the prerequisite.

## Reversibility

**High.** Removing the env-var refusal is a one-line config change. Removing the OS-tiered split is a code change but small. The decision is durable on the side of "the key should not be in env"; the mechanism (file vs keystore vs hard refusal) is flexible.

## Evidence / sources

- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "API-key handling"
- `../final-design.md §"Components"` #11 — `ApiKeyStore`
- `../phase-arch-design.md §"Component design"` #10 — `ApiKeyStore`
- `../phase-arch-design.md §"Edge cases"` rows 1, 18
- `../critique.md §performance "Things this design missed"` — API key handling
- `../critique.md §security.4` — SPKI pinning rejected (related; rotation problem documented for Phase 16)
