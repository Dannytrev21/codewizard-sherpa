# ADR-0005: No SPKI pin for `api.anthropic.com` — `EgressGuard` + system trust + OS filter + nightly drift job

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** defense-in-depth · operational-resilience · trust-boundary · network-egress
**Related:** ADR-0010 (this phase) · [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md)

## Context

Phase 4 introduces the first egress from the codewizard-sherpa runtime to a third-party API (`api.anthropic.com:443`). The security design lens proposed SPKI-pinning Anthropic's intermediate CA via `ANTHROPIC_SPKI_PINS: Final = frozenset({...})` (with the set membership left unspecified) and treating any cert-pin miss as an `EgressCertPinFailed` workflow halt.

The critic surfaced the operational failure mode (`critique.md §"[S] §1"`): Anthropic uses commercial CAs and rotates intermediates without out-of-band notification; a pin mismatch halts every workflow until we ship a new release with updated pins. The security design itself acknowledged this in §"Resource & cost profile" ("when Anthropic rotates intermediates (~annually) we must ship a release") — meaning the project's release cadence becomes driven by a third-party's CA-rotation schedule. The pin set was admitted as unspecified because Anthropic does not publish stable SPKIs for this purpose.

The threat model the pin was attempting to address is MITM-via-public-CA: an attacker who compromises any CA in the system trust store could intercept the Anthropic API traffic. The threat is real but the probability is low compared to the operational risk of self-DOS on every Anthropic CA rotation.

We still need *some* defense against (a) the leaf adapter being tricked into calling a different host, and (b) transitive deps silently opening sockets to telemetry/CDN endpoints we never approved.

## Options considered

- **SPKI-pin `api.anthropic.com`** (security design's original choice). Strongest cryptographic binding to a specific certificate chain. **Pattern:** Cryptographic pinning. Self-DOS waiting to happen; pin maintenance is out-of-band; pin rotation is a release event.
- **System trust store + `EgressGuard` only** (the weakest defense). Allow any cert chain the OS trusts; allowlist the host via socket wrapper. **Pattern:** Host allowlist. Operationally simple; doesn't address the MITM-via-compromised-CA threat at all.
- **System trust store + `EgressGuard` + OS-level egress filter + nightly real-API drift job** (synthesis composite). Multi-layer defense without the SPKI-pin operational fragility. The nightly job is the canary that catches certificate/SDK drift in production-shaped form. **Pattern:** Defense-in-depth (named layered controls).
- **CA-pinning instead of SPKI-pinning** (pin Anthropic's CA cert rather than the leaf cert). Less brittle than SPKI on intermediate rotation but still couples release cadence to Anthropic's CA management. **Pattern:** CA pinning. Still has the same rotation-as-release problem in attenuated form.

## Decision

**Reject SPKI pinning.** Phase 4 uses the system trust store for TLS to `api.anthropic.com:443`, with the following defense-in-depth stack: (1) `EgressGuard` is the runtime allowlist (`socket.create_connection` wrapper denying every host other than `api.anthropic.com`); (2) OS-level egress filtering (iptables/nftables on Linux CI; documented for macOS dev); (3) a **nightly CI job** that runs a real Anthropic call with a budget-capped CI key against a representative bench fixture and flags TLS / SDK / API-shape drift; (4) `import-linter` contracts restrict native-extension-using deps (mitigates `EgressGuard`'s C-extension `connect(2)` bypass). **Pattern:** Defense-in-depth — four named complementary controls, none of which is a single point of operational failure. SPKI-pin reintroduction requires a Phase-4 ADR amendment *and* the operational runbook for rotation handling.

## Tradeoffs

| Gain | Cost |
|---|---|
| Anthropic's CA rotations do not trigger codewizard-sherpa releases — operational coupling severed | We accept the residual MITM-via-compromised-public-CA risk (low probability; high impact); documented in `docs/operations/secrets.md` |
| The nightly drift job is the *real* canary — catches TLS, SDK upgrade, API shape, and rate-limit drift in one signal | The drift job spends real Anthropic tokens (budget-capped CI key); operator must maintain the bench fixture and review drift annotations |
| `EgressGuard` + OS-level filter is the same code-time guarantee SPKI pinning bought (the leaf can't talk to an unauthorized host), without the cryptographic-binding fragility | C-extension `connect(2)` bypasses Python's `socket` module — acknowledged residual; mitigated by `import-linter` restrictions on native-extension deps and `codegenie self-check egress` for OS-level posture reporting |
| Adding a second LLM vendor (per [ADR-0020](../../../production/adrs/0020-leaf-agents-sdk.md)) is one fence-amendment ADR + one allowlist entry — not a second pin set to maintain | If the system trust store is compromised at the OS level, our defense collapses to whatever the OS provides — same as every other system on that host |
| The nightly drift job *also* catches cassette-vs-reality drift (a separate concern in ADR-0011 of this phase) — one job, two correctness controls | The nightly job is a *process* control, not a *code* control; the runbook (`docs/operations/cassettes.md`) is load-bearing and must stay current |

## Pattern fit

The toolkit doesn't name "defense-in-depth" explicitly, but the spirit of "Functional core / Imperative shell" applies: the *core* contract is "the leaf may only talk to Anthropic's API" — that contract is enforced at four different layers (process socket wrapper, OS firewall, lint contract, nightly drift verification). Each layer has a different failure mode, none of which is *coupled to a third party's CA rotation schedule*. SPKI pinning would be a stronger single layer at the cost of operational coupling; defense-in-depth trades single-layer strength for layer diversity. The honest pattern name is "layered controls, no single point of operational failure."

## Consequences

- Phase 4 ships with no per-release pin-set maintenance cost.
- The Anthropic API key flows in via `keyring.get_password("codegenie", "anthropic_api_key") → SecretStr` (ADR-0010 of this phase); environment-variable escape paths are explicitly rejected (no `CODEGENIE_ANTHROPIC_KEY_CI`).
- The nightly drift job is in scope for Phase 4's CI surface; its runbook lives in `docs/operations/cassettes.md` and `docs/operations/secrets.md`.
- Phase 9 (Temporal workers) inherits the same posture; each worker installs `EgressGuard` and runs behind the OS egress filter; the nightly drift job continues to be one job per Anthropic key.
- [ADR-0020](../../../production/adrs/0020-leaf-agents-sdk.md)'s eventual un-deferral (second LLM vendor) is *unblocked* — adding a second host to the allowlist is one ADR + one fence-amendment. SPKI pinning would have made this a two-pin-set maintenance problem.
- `EgressGuard.pinned_to(host)` is a context manager whose temporal mutation of process-global socket allowlist is acknowledged by the critic as a boolean-flag-at-scale anti-pattern; mitigated by the host being a single-element typed `HostName` and the context manager being the *only* mutation path (not a configurable boolean).
- Phase 7's distroless container migration plugin will need its own allowlist for the registry endpoints it consults (e.g., `cgr.dev`); the fence amendment is *additive* to `EgressGuard`'s allowlist (no global re-pin).

## Reversibility

**Medium.** Reintroducing SPKI pinning is one Phase-4 ADR amendment plus the operational runbook for rotation handling (which is the actual cost — not the code change). Removing the nightly drift job is trivial (CI workflow deletion) but loses our cassette-vs-reality canary. Removing `EgressGuard` is a code revert but loses the runtime catch of dynamic socket use by transitive deps — a load-bearing control.

## Evidence / sources

- `../final-design.md §Goals` ("api.anthropic.com:443 (TLS, system trust store, no SPKI pin; nightly drift job catches breakage)")
- `../final-design.md §Component 4 — LeafLlm` ("No SPKI pin")
- `../final-design.md §Component 10 — EgressGuard`
- `../final-design.md §Resource & cost profile` ("The operational cost of *no* SPKI pin")
- `../final-design.md §Departures from all three inputs` item 3
- `../phase-arch-design.md §Component design — EgressGuard`
- `../critique.md §"[S] §1"` (SPKI self-DOS)
- `../critique.md §"[S] §2"` (loopback whitelist bypass — ADR-0006 of this phase addresses)
- [production ADR-0020](../../../production/adrs/0020-leaf-agents-sdk.md) (multi-vendor seam preserved)
