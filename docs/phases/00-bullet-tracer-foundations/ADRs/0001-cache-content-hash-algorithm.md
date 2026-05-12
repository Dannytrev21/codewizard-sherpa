# ADR-0001: Cache content-hash algorithm — BLAKE3 for content, SHA-256 for identity

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** cache · hashing · determinism · audit
**Related:** [ADR-0003](0003-two-level-cache-key-schema-versioning.md), [ADR-0004](0004-probe-execution-audit-anchor.md), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md), [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

The cache key is the artifact identity for everything downstream of Phase 0: Phase 11's PR-provenance bundles reference cache keys as evidence anchors; Phase 13's cost ledger deduplicates spend by cache key; Phase 14's continuous-gather model re-hashes inputs on every push webhook across the watched portfolio.

The three lens designs proposed three different hash algorithms — the headline conflict in `../final-design.md §L3 row 1` and the single most consequential disagreement named in `../critique.md §5`. `[P]` proposed `xxh3-128` for a ~100× speedup on lockfile bytes; `[S]` and `[B]` defaulted to SHA-256 per `../../../localv2.md §8`. The critique objected to xxh3 on collision-resistance grounds: under Phase 14 webhook fan-out an attacker who lands a PR in any watched repo can construct colliding inputs and pin the cache to the wrong probe output — silent staleness, which `production/design.md §2.3` (Honest confidence) calls out as the worst failure mode.

A non-cryptographic hash on a path that determines what evidence the Planner sees is incompatible with load-bearing commitment §2.3 at portfolio scale.

## Options considered

- **xxh3-128 everywhere (`[P]`).** Fast (~3 GB/s class). Not collision-resistant. Saves ~3ms per MB on lockfile hashing. Fails the threat model the moment Phase 14's webhook fan-out lands.
- **SHA-256 everywhere (`[S]`+`[B]`).** Cryptographic and `../../../localv2.md §8`-compatible. ~400 MB/s on modern hardware. Slow enough to be noticeable at Phase 14 portfolio scale, fast enough to be irrelevant at Phase 0.
- **BLAKE3 everywhere.** Cryptographic *and* fast (~3 GB/s on modern hardware — matches xxh3's speed argument). Not the algorithm `../../../localv2.md §8` names; would force the spec to follow the implementation.
- **BLAKE3 for content, SHA-256 for the identity tuple (synth compromise).** The critic's proposal from `../critique.md §2.3`. BLAKE3 carries the bulk content-hashing speed; SHA-256 wraps the cache-key tuple and the audit anchor (`../../../localv2.md §8`-compatible, audit-stable).

## Decision

**Bulk content hashing of `declared_inputs` uses BLAKE3. The cache-key identity tuple and the audit anchor (SHA-256 of `repo-context.yaml`) use SHA-256.** Both algorithms live in exactly one module, `src/codegenie/hashing.py`, which exports `content_hash(path) -> "blake3:<hex>"` and `identity_hash(*parts) -> "sha256:<hex>"`. No other file imports `blake3` or `hashlib.sha256`.

## Tradeoffs

| Gain | Cost |
|---|---|
| BLAKE3's ~3 GB/s satisfies `[P]`'s speed argument without giving up collision resistance | Two hash algorithms in the codebase (mitigated: both live in one file behind two clearly-named functions) |
| SHA-256 in the identity tuple keeps the audit anchor `../../../localv2.md §8`-compatible and stable for Phase 11 PR provenance and Phase 13 cost-ledger reconciliation | One extra runtime dependency (`blake3` wheel; pure C extension, no transitive Python deps) |
| Algorithm prefix in the on-disk artifact (`"blake3:..."` / `"sha256:..."`) makes future migrations readable and self-describing | Storage cost of a 6-char prefix per key — negligible |
| Phase 14's continuous-gather story holds at portfolio scale: webhook-driven re-hashing of lockfiles is fast (BLAKE3) and the resulting cache key is cryptographic (SHA-256) | The split must be defended on every PR — the temptation to use BLAKE3 in the identity tuple "for consistency" is real |
| `[P]`'s perf budget and `[S]`'s threat model both close cleanly | Both lenses had to give up their preferred uniform choice |

## Consequences

- `src/codegenie/hashing.py` is a chokepoint: one module, one set of tests (`test_hashing.py`), no second path. Any algorithm change is one file's diff.
- The `key_for(probe, snapshot, task)` derivation is `identity_hash(probe.name, probe.version, schema_version, content_hash_of_inputs)` — `content_hash` is BLAKE3 over the sorted `(path, size)` tuple set, `identity_hash` is SHA-256 over the four-part string tuple.
- Phase 13's cost-ledger attribution per [production ADR-0027](../../../production/adrs/0027-cost-attribution-model.md) gets a stable SHA-256 anchor per probe execution (see [ADR-0004](0004-probe-execution-audit-anchor.md)).
- Phase 14's continuous-gather model (production ADR-0006) inherits the speed of BLAKE3 on the cheapest, most-frequent operation in the system (input hashing).
- The `blake3` Python package becomes a load-bearing runtime dependency in `[project.dependencies]` — included in the `fence` check ([ADR-0002](0002-fence-ci-job-no-llm-in-gather.md)) closure.

## Reversibility

**Medium.** Changing either algorithm post-Phase-0 invalidates every cached blob (all `.codegenie/cache/` contents become orphans) and every prior audit anchor (every `runs/<utc-iso>-<short>.json` references a SHA-256 of a YAML that won't recompute under a new algorithm). Audit-record consumers (Phase 11, Phase 13) have to handle a "before / after" boundary. The cost is borne once and is mostly mechanical because the chokepoint is one file; the audit anchor is the harder migration. Mitigated by the algorithm prefix making the boundary self-describing.

## Evidence / sources

- `../final-design.md §2.7` (Cache layer — explicit resolution of the headline conflict)
- `../final-design.md §L3 row 1` (Conflict-resolution scoring: BLAKE3 wins 12 vs SHA-256's 9; xxh3 vetoed on commitments-fit)
- `../critique.md §5` (Single most consequential disagreement)
- `../critique.md §2.3` (Critic explicitly proposes the BLAKE3 compromise)
- `../phase-arch-design.md §Component design / Hashing` (Single-module chokepoint)
- `../../../localv2.md §8` (SHA-256 specified for cache keys — compatibility surface)
- [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md), [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md): cache integrity is load-bearing for both no-LLM-in-gather and continuous-gather
