# ADR-0011: No `ChainguardPullToken` or STS apparatus in Phase 7

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** threat-model · simplicity-first · critic-sec4 · supply-chain
**Related:** [0010](0010-chainguard-cve-image-lookup-frozen-yaml.md), [0009](0009-phase-7-byte-edit-allowlist-fence.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)

## Context

The security-first lens design proposed shipping a multi-component Chainguard authentication subsystem in Phase 7:

- `ChainguardPullToken` as a `SecretStr`-wrapped newtype with `__str__` raising on coercion
- Process-boot logger filter to scrub the token from logs
- STS/OIDC mint flow with ≤ 10-minute TTL
- Egress pull-proxy that injects the token at the outer egress
- IP allowlist for the egress proxy
- Audit events per mint and per use
- Automated rotation via Chainguard's STS-style OIDC flow
- Packaged under `src/codegenie/registry/chainguard/{sts_client.py,pull_proxy.py,token.py}`

The critic landed Sec-4 hard in `critique.md`:

> "None of this is required to ship the migration task class. Chainguard's `cgr.dev/chainguard/*` distroless images are **public** and pullable without authentication (that's the entire pitch of the catalog). The security design invents an auth requirement that doesn't exist, then builds a multi-component subsystem around it. […] This is **threat-model-driven over-engineering** — a defense against a credential that needn't exist."

The pattern claim — "capability tokens" — also fails. Capability tokens are unforgeable references to specific actions on specific resources; `ChainguardPullToken` as proposed is a bearer credential with a TTL and a scope string. "Bearer token mislabeled as capability token" was the critic's verdict.

`final-design.md §Synthesis ledger row 7` (score **13/15**) and §"No Chainguard credential class" lock the rejection.

## Options considered

- **Option A — Ship the full STS/OIDC/pull-proxy apparatus.** Security-first. **Pattern (claimed):** Capability token + Hexagonal port. **Pattern (actual per critic):** Bearer token + pull-proxy sidecar. Defends against a credential that doesn't need to exist.
- **Option B — Ship a minimal `ChainguardPullToken` newtype only (no STS, no proxy, no rotation), reserved for future use.** **Pattern:** Speculative-newtype. Premature primitive for a problem that doesn't exist.
- **Option C — No credential class. Pulls go through Phase 2's existing registry-pull capability against public `cgr.dev/chainguard/*` images. Future ADR if private-registry support arrives.** **Pattern:** Anti-decision / deferral.

## Decision

Adopt **Option C.** Phase 7 ships **no Chainguard credential class**. No `ChainguardPullToken`, no `SecretStr` newtype for it, no `src/codegenie/registry/chainguard/` package, no STS client, no OIDC mint flow, no pull-proxy sidecar, no per-mint audit events, no IP allowlist. Pulls of `cgr.dev/chainguard/*` images use Phase 2's existing registry-pull capability against unauthenticated registry endpoints. The threat surface defended by the security-first apparatus does not exist in Phase 7. If/when Chainguard introduces private-registry support relevant to the project, a future ADR opens the question with a concrete threat model.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 7 adds zero new packages for credential management; supply-chain surface stays tight | If Chainguard's pull behavior changes (private images, rate-limited tokens, IP-allowlisted endpoints), Phase 7 must amend or a follow-up ADR must add the credential class. Acceptable: the change is forward-additive when it arrives |
| The seven-component apparatus security proposed (under multiple `src/codegenie/registry/chainguard/*.py` files) is structurally closed off by the fence allowlist ([0009](0009-phase-7-byte-edit-allowlist-fence.md)) | The fence forbids quiet credential-class additions; a future legitimate addition requires an ADR amendment + fence amendment together. That's the discipline, not a bug |
| Operators reading the threat model see one line ("public images, no auth") instead of debating bearer-vs-capability framing | If a security reviewer expects defense-in-depth on registry pulls, the project must point to the Phase 2 registry-pull capability + microVM isolation as the existing defenses, not to a Chainguard-specific subsystem |
| No `SecretStr` newtype with `__str__` raising — Phase 7 does not extend the "secrets discipline" surface with a credential that has no production justification | If a future Phase has both public and private registries to mix-and-match, the unifying newtype must be designed cold — but that's a future ADR's job |
| Rule 2 (Simplicity First) honored: minimum code that solves the problem | Some defense-in-depth purists may argue every external service deserves a typed credential class on principle. Counter-argued: principle alone doesn't justify code |

## Pattern fit

Implements **Anti-decision / Deferral** (toolkit §Architecture / boundaries — Anti-decisions are first-class; Rule 2 Simplicity First): the cheapest abstraction is the one not shipped. Also instantiates **Honest threat-model framing** (toolkit §Adversarial review — defenses are scoped to documented threats, not speculative ones). Rejects **Capability tokens** (security-first's claim) on the grounds that the implementation as proposed is bearer-token-with-TTL, not capability-as-unforgeable-reference. Mirrors [Phase 3 ADR-0011](../../03-vuln-deterministic-recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md)'s discipline of refusing to over-claim cryptographic properties an implementation doesn't have.

## Consequences

- `src/codegenie/registry/chainguard/` does **not exist** in Phase 7. Fence allowlist ([0009](0009-phase-7-byte-edit-allowlist-fence.md)) does not authorize it.
- `ChainguardPullToken`, `ChainguardScope`, `STSClient`, `PullProxy`, `egress_token_injection` — none of these are defined in Phase 7.
- `DistrolessBuildGate` (the microVM that pulls Chainguard images) uses Phase 2's existing registry-pull capability. Pulls go to `cgr.dev/chainguard/*` unauthenticated.
- A future ADR (e.g., "Phase N ADR-NNNN — Chainguard private-registry credential class") is the path if Chainguard offers private registry endpoints the project consumes. That ADR must include the concrete threat model and would amend this one.
- If a future Phase 7 hotfix discovers that `cgr.dev/chainguard/*` rate-limits unauthenticated pulls beyond what the project can tolerate, the response is: (a) named ADR to introduce auth, (b) fence allowlist amendment to authorize the new package, (c) implementation.
- `tests/fence/test_phase7_no_chainguard_credential_class.py` (or an extension of `test_phase7_no_byte_edits_to_locked_files.py`) asserts the negative: no `ChainguardPullToken` or `STSClient` symbol exists under `src/codegenie/`.
- Risk #1 of `final-design.md` does **not** name this as a risk — Chainguard's public-image policy is well-documented and stable.

## Reversibility

**High.** Adding a credential class later is a forward-additive change: a new module under `src/codegenie/registry/chainguard/` or `src/codegenie/primitives/registry_credentials/` (depending on the future ADR's framing), plus the fence amendment, plus the consumer wire-up at the registry-pull capability. Phase 7's "no credential class" decision creates no debt that compounds; it simply doesn't ship infrastructure that future work may need.

## Evidence / sources

- `../final-design.md §Goals` ("No Chainguard credential class"), §Synthesis ledger row 7 (score 13/15), §Patterns considered and deliberately rejected
- `../phase-arch-design.md §Component design §10` (`DistrolessMigrationPlugin` — no chainguard credential surface), §Tradeoffs (consolidated) row "No Chainguard credential class"
- `../critique.md §Attacks on the security-first design §4` (Sec-4 — threat-model-driven over-engineering), §Design-pattern critiques ("Capability tokens claim — Bearer token mislabeled as capability token")
- [Phase 3 ADR-0011 — Honest framing — Capability is audit + lint](../../03-vuln-deterministic-recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) (precedent: refusing to over-claim cryptographic properties)
- Rule 2 — Simplicity First (CLAUDE.md global rules)
