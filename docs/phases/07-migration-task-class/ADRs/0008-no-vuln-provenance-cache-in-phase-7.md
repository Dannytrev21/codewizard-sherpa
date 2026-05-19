# ADR-0008: No `vuln_provenance_cache` in Phase 7 — ADR-0038 §Tradeoffs deferral honored

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** adr-0038 · deferral · kernel-purity · cache · phase-14
**Related:** [0004](0004-vuln-provenance-primitive-home.md), [0007](0007-provenance-adapter-registry-stores-classes.md), [production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md), [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md), [production ADR-0039](../../../production/adrs/0039-bounded-additive-core-primitives.md)

## Context

[Production ADR-0038 §Tradeoffs](../../../production/adrs/0038-vulnerability-provenance-attribution.md) explicitly defers caching: "the provenance join is recomputed every time it's called, with no inter-workflow caching. […] Phase 14 may add a `vuln_provenance_cache` keyed on `(sbom_digest, vuln_index_digest)` if the lookup volume justifies it."

Performance-first's lens design contradicted this on its first page — it proposed a SQLite-backed cross-process LRU cache with a 5-tuple key (`repo_snapshot_sha + cve_id + vuln_index_digest + sbom_digest + image_digest`), 24-hour TTL, WAL mode, BLAKE3 checksums, and a Stage-1-Assessment volume justification. The critic landed Perf-3 hard:

> "Stage 1 Assessment doesn't exist until Phase 10. The cache is built for a load that no phase before 10 can produce. Performance-first contradicts the ADR-0038 deferral on its first page."

Security-first and best-practices both correctly honored the deferral. `final-design.md §Synthesis ledger row 3` (score **15/15**) locks the no-cache position.

There is a second concern beyond the deferral itself: performance's cache lived in `src/codegenie/vuln_provenance/cache.py` and did SQLite I/O at the call site. Critic flagged this as "Hexagonal claim smuggling I/O into the core" — the primitive (positioned as a kernel-bounded primitive per ADR-0039) becomes a module that read/writes a database. Phase 7's primitive must be pure.

## Options considered

- **Option A — Ship the SQLite cache in Phase 7.** Performance-first position. **Pattern:** Memoization with persistent store. Contradicts ADR-0038 deferral; builds for a load no pre-Phase-10 workflow can produce; tangles I/O into the kernel-bounded primitive.
- **Option B — Ship a per-process in-memory LRU only (no SQLite).** Halfway. **Pattern:** Memoization. Cheaper but still contradicts ADR-0038's "recomputed every time it's called"; adds state to a primitive that should be pure.
- **Option C — Ship no cache in Phase 7. Primitive is a pure function. Phase 14 owns the cache when call-volume data justifies it.** **Pattern:** Deferral / Kernel purity.

## Decision

Adopt **Option C.** `src/codegenie/primitives/vuln_provenance/` ships **no cache**. `assemble_provenance(...)` is a pure function over its inputs — no SQLite, no LRU, no `vuln_provenance.sqlite`. The primitive's directory tree contains no `cache.py`. A fence test asserts no `model_construct()` bypass and no `sqlite3` import under `primitives/vuln_provenance/`. Phase 14 owns the cache when call-volume data justifies it; the key shape (`(sbom_digest, vuln_index_digest)` per ADR-0038) is preserved as the future contract.

## Tradeoffs

| Gain | Cost |
|---|---|
| ADR-0038 §Tradeoffs deferral honored without amendment; no ADR contradiction in Phase 7 | Phase 10 portfolio-scale scans pay full cost per `(repo, cve)` pair until Phase 14 ships a cache. Acceptable: Phase 10's design pipeline owns the cost model |
| Primitive is pure: no SQLite I/O at the call site; no hexagonal-claim-smuggling-I/O-into-the-core anti-pattern | The cache must be added later under ADR-0039's discipline (i.e., Phase 14 amends ADR-0038 §Tradeoffs or files a fresh ADR for the cache port). Phase 7 does not pre-shape that ADR — Phase 14 designs it cold |
| `src/codegenie/primitives/vuln_provenance/` ships with no persistent state; the directory tree is small and reviewable; the `__init__.py` re-export surface is the entire public contract | No warm-path optimization for Phase 7 / Phase 8 workloads. Per-call cost is ≤ 50 ms uncached (the bulk being adapter calls); acceptable |
| Phase 14's cache design has the freedom to pick its port (sidecar SQLite vs. Redis vs. an in-process LRU with a periodic flush); Phase 7 does not pre-commit | Operators reading the primitive may expect "what about caching?" — answered explicitly in the primitive's docstring with a forward reference to Phase 14 / ADR-0038 §Tradeoffs |
| Test coverage is straightforward: pure function ⇒ direct call ⇒ assert result. No cache fixtures, no TTL clocks, no flush semantics to test | Performance regressions at Phase 10 scale will manifest only at Phase 10's bench harness; Phase 7's per-call envelope (≤ 50 ms) is honest but small-scale |

## Pattern fit

Implements **Deferral with named owner** (toolkit §Architecture / boundaries — Deferral as an explicit anti-decision): Phase 14 is the named owner; ADR-0038 §Tradeoffs is the existing precedent; no Phase 7 work is done speculatively. Also instantiates **Kernel purity** ([production ADR-0039](../../../production/adrs/0039-bounded-additive-core-primitives.md) — bounded core primitives must be pure): no I/O in the kernel-bounded primitive's body. Rejects **Memoization at the kernel layer** (toolkit §Performance — Memoization belongs at the adapter layer, not in the port).

## Consequences

- `src/codegenie/primitives/vuln_provenance/` contains no `cache.py`, no `sqlite3` import, no LRU decorator on `assemble_provenance`.
- `assemble_provenance(...)` is a pure function — same inputs, same outputs. Property test `test_idempotence.py` asserts this.
- A fence (`tests/fence/test_phase7_no_llm.py` and a related `tests/fence/test_provenance_primitive_purity.py` if added per implementation discretion) asserts no `sqlite3`, `aiofiles`, or other I/O modules imported under `primitives/vuln_provenance/`.
- The deferral is documented in `primitives/vuln_provenance/__init__.py`'s module docstring with an explicit forward reference: "Caching is deferred to Phase 14 per ADR-0038 §Tradeoffs; do not add a cache module without amending ADR-0038."
- Phase 10's design pipeline must explicitly engage the portfolio-scale cost model — Phase 7 ships telemetry (`ProvenanceQueried` event carries the per-call timing) so Phase 10 has data.
- Phase 14's future cache lands as an **adapter** the primitive composes (port + adapter discipline), not as a module that does I/O at the call site. The cache key shape `(sbom_digest, vuln_index_digest)` per ADR-0038 is preserved as the future contract.
- Performance-first's `[P-v5]` (SQLite cache) plus `[P-v6]` (5-tuple key) plus `[P-v7]` (24h TTL) plus `[P-v34]` (WAL + batch-flush) plus `[P-v36]` (BLAKE3 checksum) — **all rejected in Phase 7**.

## Reversibility

**High.** Adding a cache in Phase 14 (or earlier if data justifies) is a forward-additive change: the primitive's `__init__.py` surface gains a new optional `cache: ProvenanceCache | None = None` parameter; existing callers pass `None` (default behavior unchanged). The cache itself is an adapter, not a kernel concern. The cost of reversal is zero from Phase 7's perspective.

## Evidence / sources

- `../final-design.md §Lens summary §3`, §Goals, §Synthesis ledger row 3 (score 15/15)
- `../phase-arch-design.md §Component design §1` (`VulnProvenancePrimitive` — "No SQLite, no LRU. **No cache in Phase 7**"), §Path to production end state "Still missing — No portfolio-scale `vuln.provenance` caching until Phase 14"
- `../critique.md §Attacks on the performance-first design §3` (Perf-3 — cache contradicts ADR-0038 deferral), §Anti-patterns "Hexagonal claim smuggling I/O into the core"
- [production ADR-0038 — Vulnerability provenance attribution](../../../production/adrs/0038-vulnerability-provenance-attribution.md) §Tradeoffs (caching deferral to Phase 14)
- [production ADR-0039 — Bounded additive core primitives](../../../production/adrs/0039-bounded-additive-core-primitives.md)
