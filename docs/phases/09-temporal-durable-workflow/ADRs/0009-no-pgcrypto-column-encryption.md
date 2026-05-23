# ADR-0009: No `pgcrypto` column encryption on `events.payload`; encryption-at-rest delegated to volume layer

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** anti-decision · threat-modeling · defense-in-depth · YAGNI
**Related:** [ADR-0008](0008-typed-credential-blocklist-not-regex.md)

## Context

The security-first design [S] proposed `pgcrypto` column encryption on `events.events.payload` so the JSONB column is opaque at rest in Postgres. The critic's destruction of [S] showed the property does not hold against the actual read path: **every projection holds the decryption key** (otherwise it cannot fold over the payload). If the projection process is compromised, the key is compromised — column encryption is decorative against the only path that consumes payload data. The encryption only protects against an attacker who reads the Postgres data files but does *not* have credentials for any projection process, which is a thin attacker model already covered better by volume-layer encryption (LUKS, AWS RDS TDE).

This is an anti-decision: a tempting defense-in-depth measure that, when costed honestly against the actual read path, buys nothing and adds key-management ceremony.

## Options considered

- **`pgcrypto` symmetric column encryption.** Encrypt `events.payload` with a key held by all writers and projections. **Pattern:** column-level encryption at rest. Adds key-management; offers no protection against the projection compromise path.
- **`pgcrypto` per-row key wrapping.** Each row encrypted with a row-specific key wrapped by a master key. **Pattern:** envelope encryption. Worse key-management; same projection-compromise problem.
- **Volume-layer encryption (LUKS, TDE).** Postgres data volume encrypted at the OS level; no application-level key handling. **Pattern:** transparent disk encryption. Protects the "stolen data files" threat; no application ceremony.
- **No encryption; rely on `seal()` to keep secrets *out* of payloads.** **Pattern:** prevention over remediation. If a secret is never in the payload, no encryption is needed; if a secret slips into the payload, encryption doesn't help (every reader has the key).

## Decision

Phase 9 ships **no `pgcrypto` column encryption** on `events.payload`. Secrets are kept out of payloads by [ADR-0008](0008-typed-credential-blocklist-not-regex.md)'s `seal()` discipline. Encryption-at-rest is delegated to the volume layer (LUKS/TDE), which Phase 16 will land for the production cluster. **Pattern: anti-decision — prevention over decorative remediation.**

## Tradeoffs

| Gain | Cost |
|---|---|
| No key management — no rotation, no compromise drill, no per-environment key splits | If the volume layer encryption is misconfigured in production, payloads are unprotected at rest |
| Projections can be added additively without "do you have the decryption key?" checks | Auditors expecting "PII column-encrypted" will need education on why prevention-via-`seal()` is the better answer |
| No performance cost on reads (encrypted JSONB is slower to query) | Phase 16's volume-layer encryption is a real piece of work that Phase 9 does not pay for; it must land by production |
| Aligns with [ADR-0008](0008-typed-credential-blocklist-not-regex.md) — secrets are never in payloads; encryption would be defending an empty surface | Defense-in-depth advocates will push back; the rationale must be written down (this ADR) |
| Postgres `events.payload` is JSONB queryable by projections without an encryption-key dance | Volume-layer encryption is opaque to the application — no key visibility for `pg_dump` audit reads |

## Pattern fit

The toolkit's `design-patterns-toolkit.md §Anti-decisions` calls this out: an anti-decision ADR exists to document the *tempting* pattern that was *deliberately not applied* and to articulate the pattern-soup or ceremony cost it would have created. Column encryption with a shared key is the canonical case of "encryption that protects against an attacker who does not exist": the actual attackers (compromised projection, compromised application role) have the key by definition; the attackers without the key (raw-disk thieves) are better defended by volume-layer encryption with no application involvement.

## Consequences

- `events.events.payload` is plain JSONB.
- Phase 16 production deployment requires LUKS-encrypted EBS volumes (or equivalent) for the Postgres data; this is on the Phase-16 roadmap.
- `seal()` is the *only* defense against secrets-in-payloads; the discipline is non-negotiable and is fenced at three layers (mypy, fence test, runtime).
- The Phase-13.5 operator portal reads events through `read_role`; no decryption step.
- Phase 11 / 13 projections read payloads directly; no key handling.
- If a future ADR introduces application-managed encryption (e.g., for a multi-tenant scenario where each tenant's projection can decrypt only its tenant's payloads), it lands additively as a new column (`encrypted_payload BYTEA`) with explicit per-tenant key management — not as an edit to this decision.

## Reversibility

**High.** Adding column encryption later is an additive schema migration (`ALTER TABLE events.events ADD COLUMN encrypted_payload BYTEA`) with a backfill — doable; the cost is operational (key management) more than technical.

## Evidence / sources

- [`../phase-arch-design.md §Non-goals — `pgcrypto` column encryption`](../phase-arch-design.md#non-goals)
- [`../phase-arch-design.md §Design patterns applied — Patterns considered and deliberately rejected`](../phase-arch-design.md#patterns-considered-and-deliberately-rejected)
- [`../critique.md §Attacks on the security-first design — pgcrypto column encryption`](../critique.md)
- [`../final-design.md §Synthesis ledger — pgcrypto encryption row`](../final-design.md)
- [production ADR-0040 Data lifecycle, retention, and classification](../../../production/adrs/0040-data-lifecycle-retention-and-classification.md) — volume-layer encryption is the canonical at-rest policy
