# ADR-0003: Hot-view integrity by gather-id content-addressing, not HMAC/KMS

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** content-addressed cache · fail-closed · make-illegal-states-unrepresentable
**Related:** ADR-0004, ADR-0006, [production ADR-0013](../../../production/adrs/0013-pre-rendered-redis-hot-views.md)

## Context

The four Redis hot-view slices ([production ADR-0013](../../../production/adrs/0013-pre-rendered-redis-hot-views.md)) feed the planner's routing context. Redis is a separate process; a writable-Redis compromise is a write primitive into every planner's context — the trust boundary the security lens labels TB-4. The phase therefore must decide a *trust posture* for reading Redis: is a value the planner reads trusted, or verified?

[critique.md §Cross-design observations](../critique.md#where-do-the-three-disagree) shows the three lenses split three ways: performance trusts Redis on read (it has a degraded path for Redis *unavailable* but **no path for Redis lying**); best-practices likewise trusts on read; security verifies every value with an HMAC tag whose key is held in a KMS and minted through a secrets broker. The security mechanism is correct in *property* (fail-closed) but undeployable in *substrate*: per [critique.md §hidden assumptions](../critique.md#hidden-assumptions-1), no KMS, no secrets broker, and no mTLS PKI exists in any phase 0–8, and the Phase 8 roadmap tooling list is three lines (`redis`, `redis-py`, `mcp`). The synthesis [departs from all three](../final-design.md#departures-from-all-three-inputs) — it takes security's fail-closed *property* via a substrate-honest *mechanism*.

## Options considered

- **Option A — Trusted-on-read.** Parse whatever Redis returns; degrade only when Redis is *unreachable*. **Pattern:** none — leaves TB-4 wide open. A Redis writer silently poisons every planner's routing context with zero detection.
- **Option B — HMAC-tagged values, KMS-held key, secrets-broker mint.** Every slice carries a cryptographic MAC; the planner verifies it before use. **Pattern:** Capability / cryptographic integrity — but the enabling infrastructure (KMS, secrets broker) does not exist before Phase 9. Undeployable this phase; *architecture by threat enumeration* (toolkit "speculative subsystem").
- **Option C — Content-addressed integrity by `gather_id`.** Every slice the renderer writes is stamped with the `gather_id` (a content hash of the source `RepoContext`) and its `slice_schema_version`. On read, the planner verifies the `(repo, slice, gather_id, slice_schema_version)` binding; any mismatch discards the Redis value and falls through to cold storage. **Pattern:** Content-addressed cache + make-illegal-states-unrepresentable — uses the gather/cache layer's existing content-identity discipline (`cache/keys.py`); zero new infrastructure.

## Decision

Every hot-view slice is stamped with the source `gather_id` and its `slice_schema_version`. On read, `HotViewStore` verifies the `(repo, slice_name, gather_id, slice_schema_version)` binding against the gather identity the planner knows; **any mismatch — stale, tampered, or version-drift — discards the Redis value and falls through to a cold-storage read**. Redis is therefore **untrusted on read, fail-closed to cold storage**, with no KMS, no HMAC, and no secrets broker. This is the **content-addressed cache** pattern: data integrity by content identity, the same discipline the cache layer already uses.

## Tradeoffs

| Gain | Cost |
|---|---|
| Fail-closed property — a tampered or stale Redis value cannot reach a planner's context — with zero new infrastructure on the actual substrate | No *cryptographic* tamper-evidence: an attacker who can both write Redis *and* read the source artifact could forge a value with a matching `gather_id` |
| `gather_id` is already a first-class identity in the gather/audit layer — the integrity check is a microsecond string compare, not a crypto operation | The defense covers a Redis *writer* (a latency attacker, fully defended) but not a Redis *reader-plus-artifact* attacker (deferred to Phase 9 identity work) |
| A writable-Redis compromise is downgraded from a context-poisoning attack to a latency cost — the attacker can only force a slower cold read | A sustained tamper attack flips every read to the cold path — a portfolio-wide latency multiplier; mitigated by alerting on the integrity-miss signal, not by a circuit breaker this phase |
| Deployable on the macOS dev substrate today — no Phase-9 identity prerequisite | The cryptographic story is explicitly deferred; this ADR must be revisited when KMS/secrets infrastructure lands in Phase 9+ |

## Pattern fit

The toolkit's anti-pattern list flags the "speculative subsystem" — "infrastructure for zero-current-use threats whose enabling phase has not arrived." Option B's KMS+broker apparatus is exactly that: a credential-management subsystem in a phase whose only LLM call is a leaf node. The chosen mechanism is the **content-addressed cache** discipline already proven in `cache/keys.py` — a cache key derived from content identity. The `(repo, slice, gather_id, slice_schema_version)` binding makes a stale-or-tampered value structurally a *cache miss*, so the planner never branches on it; the fail-closed property falls out of the cache semantics rather than being a bolted-on security control.

## Consequences

- `HotViewStore.get` always returns a valid `HotViewSlice` (never `None`) — a miss resolves transparently through cold storage, so the planner's warm path is branchless.
- An integrity miss is logged as a security/ops signal (`structlog`, a `_WARNING_IDS`-registered ID) — never silent (Rule 12).
- A property test must hold: a hot-view-served read and a cold-storage read produce *byte-identical* planner context. The cache changes latency, never the answer.
- The cold-storage path (`ColdStoreReader`) must read the *same* `RepoContext` artifact the renderer rendered from — see [ADR-0006](0006-cold-storage-fallback-reads-the-rendered-repocontext.md).
- A genuine cryptographic tamper-evidence story for Redis is Phase 9+ work; this ADR is the record that it is deferred, not forgotten.
- Adversarial tests must cover: a wrong-`gather_id` value (discarded → cold read), and attacker-controlled bytes for `risk_flags` (planner context byte-identical to the no-tamper run).
- A portfolio-wide cold-path storm (Redis flush, or a sustained tamper attack) is bounded and self-healing — see [phase-arch-design.md §Edge case 13](../phase-arch-design.md#edge-cases); Phase 9 owns a warm-up-on-start story.

## Reversibility

**Medium.** The `gather_id` + `slice_schema_version` stamping is baked into the `HotViewSlice` model and the renderer/store contract — changing the *integrity mechanism* later (e.g. adding an HMAC field in Phase 9) is an additive `HotViewSlice` field plus a renderer/store edit, compiler-policed. The *trust posture itself* — untrusted-on-read, fail-closed — is load-bearing and is the part Phase 9's cryptographic story builds *on*, not replaces. Phase 9 adds crypto evidence; it does not undo content-addressing.

## Evidence / sources

- ../final-design.md §Departures from all three inputs, item 2 — gather-id content-addressed integrity
- ../final-design.md §Synthesis ledger — Conflict-resolution row "Redis trust posture"
- ../phase-arch-design.md §C4 — HotViewStore; §Scenario 2 — fail-closed to cold storage
- ../phase-arch-design.md §G5 — "Redis is untrusted on read"
- ../critique.md §Attacks on the security-first design, problem 5 — fail-closed as a DoS amplifier
- ../critique.md §hidden assumptions — no KMS/secrets-broker in Phase 8
- ../../../production/adrs/0013-pre-rendered-redis-hot-views.md
- `design-patterns-toolkit.md` §Anti-patterns — "Speculative subsystem"
