# ADR-0008: `BundleBuilder` uses deterministic serial fallback (NOT hedged-race); `vuln_index.digest` is part of the Bundle cache key

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** determinism · cache-correctness · commitment-2.4 · veto-strength
**Related:** [0005](0005-two-stream-event-log-per-adr-0034.md), [0010](0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md), [production ADR-0030](../../../production/adrs/0030-graph-aware-context-queries.md)

## Context

Production `design.md §2.4` ("Determinism over probabilism for structural changes") is a **veto-strength** commitment: "same inputs → same Transform bytes; replay produces identical outputs." Phase 3's `BundleBuilder` (`src/codegenie/plugins/bundle.py`) executes TCCM `must_read` / `should_read` / `may_read` queries via language adapters; the question is what happens when an adapter reports `AdapterConfidence.Degraded` or `Unavailable` (e.g., stale SCIP index).

The **performance lens** proposed **hedged-race**: fire the primary query AND the declared fallback in parallel; return the first-to-complete with confidence weighting. This minimizes p99 latency.

The **security** and **best-practices lenses** both proposed **declarative serial fallback**: invoke the fallback *only* when the primary returns `Degraded` or `Unavailable`. Slightly slower (~+100 ms on degraded paths), but the result is a deterministic function of inputs.

The critic correctly attacked hedged-race in `critique.md §Attacks on the performance-first design`: hedged-race violates commitment §2.4 by definition — two runs against the same inputs can return *different* Bundle bytes if the primary wins on run 1 and the fallback wins on run 2 (due to scheduler noise). Different Bundle bytes → different `recipe.applies(cve, bundle)` decisions → different `Transform.diff_bytes` → determinism property fails.

Additionally, the critic flagged Hidden Assumption #3: the lens designs' Bundle cache keys did **not** include `vuln_index.digest`. A CVE-feed refresh that re-classifies a CVE (e.g., severity rises, affected range widens) must not return a stale cache hit; the cache key must include the vulnerability index's content digest.

## Options considered

- **Option A — Hedged-race in `BundleBuilder` (performance lens).** Fire primary + fallback in parallel; return first-to-complete weighted by confidence. **Pattern:** Race-based composition. Violates commitment §2.4.
- **Option B — Declarative serial fallback; `vuln_index.digest` omitted from cache key.** Deterministic queries, but stale cache hits on CVE-feed refresh. **Pattern:** Smart constructor under-specified — cache key doesn't reflect a real input.
- **Option C — Declarative serial fallback (fire fallback only when primary returns `Degraded`/`Unavailable`), AND `vuln_index.digest` included in the Bundle cache key.** Deterministic + correct under CVE-feed updates. **Pattern:** Pure Functional core / imperative shell — the Bundle is a fold over typed inputs.

## Decision

Adopt **Option C.** `BundleBuilder` (`src/codegenie/plugins/bundle.py`) executes TCCM queries under `asyncio.Semaphore(min(4, os.cpu_count()))` (overridable via `CODEGENIE_BUNDLE_CONCURRENCY` env var); each query's TCCM-declared `fallback` runs **only** when the primary returns `AdapterConfidence ∈ {Degraded, Unavailable}`. Bundle cache key:

```
blake3(
  plugin_id || plugin_version || primitive || canonicalize(args)
  || repo_ctx.digest || scip.digest || dep_graph.digest
  || vuln_index.digest
)
```

A property test asserts byte-identical Bundle output across 100 Hypothesis runs on the same inputs.

## Tradeoffs

| Gain | Cost |
|---|---|
| Commitment §2.4 honored at the Bundle layer — `Transform` determinism property (Goal G4) inherits cleanly | +~100 ms on degraded paths vs hedged-race max(); acceptable in the 18-s p50 envelope |
| `vuln_index.digest` in cache key means a CVE-feed refresh that re-classifies a CVE invalidates the Bundle cache entry — no stale-cache surprise | Cache hit rate drops slightly after every `codegenie vuln-index refresh`; acceptable cost for correctness |
| Hypothesis property test (100 runs, byte-identical output) is feasible because the function IS pure modulo timestamps | The property test is brittle to any non-determinism (set iteration order, dict ordering pre-3.7, hash seed) — strict discipline required |
| `AdapterDegraded` event emission on fallback paths gives clean confidence propagation into `TrustOutcome.confidence` (Goal G8) | The fallback path is taken less often in steady state; less-tested code path needs explicit fixture coverage |
| `CODEGENIE_BUNDLE_CONCURRENCY` env var escape hatch addresses the critic's "unbenchmarked SSD-knee" Hidden Assumption #4 — CI tuning without code edits | Env var sprawl risk; we limit to two env vars total in Phase 3 (this + `CODEGENIE_VULN_INDEX_PATH`) |
| Cache key includes content digests of every input, not file paths or mtimes — content-addressed cache survives repo moves and clock skew | Cache key computation requires reading all inputs to digest them; amortized by caching the digests themselves |

## Pattern fit

Implements **Functional core / imperative shell** (toolkit §Architecture-scale patterns) — the Bundle is a pure fold over typed inputs (`plugin_id`, `repo_ctx.digest`, `vuln_index.digest`, primitive queries' canonicalized args), with side effects (adapter dispatch, disk reads) at the edges. The cache key IS the content-hash of the inputs; identical inputs guarantee identical outputs. Rejects hedged-race composition because it introduces scheduler-dependent non-determinism into a function that must be pure.

## Consequences

- `src/codegenie/plugins/bundle.py` ships `BundleBuilder` with `asyncio.Semaphore(min(4, os.cpu_count()))` and serial fallback dispatch.
- `tests/unit/plugins/test_bundle.py` asserts (a) Bundle cache hit on identical inputs, (b) cache miss after `vuln_index.digest` change, (c) fallback fires deterministically (not raced) on `Degraded`.
- Property test: 100 Hypothesis runs of `BundleBuilder.build(...)` against the same inputs → byte-identical Bundle.
- `AdapterDegraded` events on the workflow-internal stream carry `(primitive, adapter_name, reason)` payload; `TrustScorer` folds them into `TrustOutcome.confidence`.
- `CODEGENIE_BUNDLE_CONCURRENCY` env var is the single tuning knob; documented in operator runbook.
- Cache-key collision is impossible by construction (blake3 hash of all inputs); a key mismatch indicates a real input change.
- `BundleCacheGc` helper (per architecture-spec Gap 4) runs at orchestrator init if `time.time() - last_gc > 86400`; operator alias `codegenie cache prune` invokes unconditionally.
- Phase 8's Redis hot views replace this cache; the cache-key shape (blake3 over content) ports unchanged.

## Reversibility

**Low (for hedged-race).** Switching to hedged-race violates commitment §2.4 directly — the determinism property test would fail by construction. The only reversible direction is *more* determinism (e.g., synchronous serial without the semaphore), not less.

**High (for cache-key shape).** Adding additional digest inputs (e.g., a future ADR ships `policy.digest`) is mechanical; removing an input would invalidate every existing cache entry but is a one-line change.

## Evidence / sources

- `../phase-arch-design.md §Component design C7`, §Patterns considered and deliberately rejected ("No hedged-race in `BundleBuilder`"), §Goals G4 + G8
- `../final-design.md §Synthesis ledger rows "BundleBuilder fallback semantics"` (score 15/15) and "`vuln_index.digest` in Bundle cache key" (score 15/15)
- `../critique.md §Attacks on the performance-first design — hedged-race violates §2.4`, §Hidden assumptions #3 (`vuln_index.digest`), Hidden assumptions #4 (unbenchmarked SSD-knee)
- `docs/production/design.md §2.4` — determinism over probabilism (veto-strength commitment)
- [production ADR-0005 — no LLM in gather pipeline](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)
- [production ADR-0030 — graph-aware context queries](../../../production/adrs/0030-graph-aware-context-queries.md)
- design-patterns-toolkit.md §Functional core, imperative shell
