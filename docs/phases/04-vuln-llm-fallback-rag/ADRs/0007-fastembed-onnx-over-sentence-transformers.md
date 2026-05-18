# ADR-0007: `fastembed` ONNX over `sentence-transformers`/torch for local embeddings

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** dependency-discipline · embedded-runtime · contributor-friction · ports-and-adapters
**Related:** ADR-0008 (this phase) · ADR-0003 (this phase)

## Context

Phase 4's RAG tier needs a deterministic local CPU embedder. The choice candidates were `sentence-transformers` (best-practices + security lenses, defaulted to `all-MiniLM-L6-v2`) and `fastembed` (performance lens, defaulted to `BAAI/bge-small-en-v1.5` ONNX). The dimensions to compare are: install footprint, cold-start time, runtime determinism, contributor friction, and supply-chain surface.

`sentence-transformers` pulls in `torch` (~250 MB transitive install on a cold CI run, ~40 s cold-start time). `fastembed` ships its own ONNX runtime (`onnxruntime`, ~130 MB), loads weights from a content-addressed URL, and has no torch dependency. Both run in-process on CPU with no docker-compose requirement.

The critic surfaced an internal inconsistency (`critique.md §"[B] §2"`): the best-practices design used "contributor friction" (no docker-compose) as the *justification* for picking chromadb-local over qdrant, then picked the *heavier* sentence-transformers stack for embeddings — a contradiction in the same design. `fastembed` runs in-process with no docker exactly as chromadb-local does.

There is a residual: ONNX runtime float outputs may differ at the 5th decimal between x86_64 and arm64. Cosine similarity at the retrieval thresholds (0.65 / 0.85) is robust to this; cosine at a tighter floor (e.g., 0.97) is not. ADR-0008 of this phase (two-threshold band, not a single point) compensates.

## Options considered

- **`sentence-transformers` + `torch`** (`all-MiniLM-L6-v2`). Mature ecosystem; PyTorch-native; ~250 MB install, ~40 s cold install on CI. **Pattern:** Vendor SDK as runtime. The heaviest reasonable choice; `torch` brings GPU surface we don't use, telemetry-shaped behaviors, and one of the largest deps in the Python world.
- **`fastembed` ONNX** (`BAAI/bge-small-en-v1.5`). Same in-process shape as sentence-transformers, no torch, ~130 MB install, ~500 ms cold model load. Determinism caveat: ONNX float outputs may drift at 5th decimal across CPU architectures. **Pattern:** Vendor SDK as runtime, lighter footprint.
- **Self-hosted embeddings via a network call** (e.g., OpenAI embeddings API). No runtime weight management; one more network dep. **Pattern:** Remote SaaS. Rejected — adds a second egress allowlist entry (ADR-0005 stays simpler with one host), adds a runtime cost line, and conflicts with the "no network for embeddings" property the design targets.
- **Bring our own ONNX session over BGE without `fastembed`**. Full control; reimplements tokenizer + ONNX session management; significant code surface to maintain. **Pattern:** In-house wrapper. Rejected — `fastembed` is the shape we'd build, but already built and maintained.

## Decision

`FastembedEmbedder` wraps `fastembed.TextEmbedding(model_name="BAAI/bge-small-en-v1.5")` behind the `Embedder` Protocol at `src/codegenie/rag/embedder.py`. Weights are bootstrapped offline by `codegenie embeddings bootstrap` against a content-addressed URL whose sha256 lives in `.codegenie/rag/embeddings_model.lock`; runtime refuses to start on hash mismatch. `EgressGuard` (ADR-0005) catches any runtime download attempt as defense-in-depth. **No `sentence-transformers`, no `torch`** in the runtime; both forbidden in the Phase 4 fence (ADR-0003 — `PHASE4_STILL_FORBIDDEN`). **Pattern:** Adapter (Embedder Protocol) over a vendor SDK, with offline weight bootstrap as the supply-chain control.

## Tradeoffs

| Gain | Cost |
|---|---|
| ~120 MB less install; ~40 s faster cold CI per run; ~180 MB RSS vs ~400+ MB with torch | `fastembed` is a younger library than `sentence-transformers`; smaller community; less search-engine help when things break |
| No `torch` in the runtime closure — eliminates a large supply-chain surface (telemetry, GPU drivers, CUDA assumptions on dev machines) | Cross-architecture float drift at 5th decimal — mitigated by the two-threshold band ([ADR-0008](0008-two-threshold-calibration-band.md)) and Phase-4 CI running x86_64 only |
| Same in-process / no-docker shape as `chromadb` local — contributor-friction argument applies consistently | Phase 6.5's bench harness must include the `arm64-cross-host-determinism` test (deferred to Phase 6.5; recorded as a known gap) |
| Offline bootstrap + sha256-locked weights + `EgressGuard` catch any runtime weight download — supply-chain control is explicit | Operator must run `codegenie embeddings bootstrap` once per host before workflows can run; the bootstrap step is documented in `docs/operations/bootstrap.md` |
| `Embedder` Protocol earns its keep — Voyage / Cohere / future ONNX models slot in behind the same `model_digest()` cache-key contract | The Protocol is acknowledged borderline-premature pluggability (one adapter today); kept because `model_digest()` is the cache-key contract — not because of imminent multi-vendor pressure |

## Pattern fit

The toolkit's "Ports and Adapters" pattern applies cleanly: `Embedder` is the port; `FastembedEmbedder` is the only adapter today; future Voyage/Cohere adapters land behind the same port. The toolkit's anti-pattern flag for premature pluggability is acknowledged — but the `model_digest() -> BlobDigest` method is the load-bearing reason the Protocol exists (the embedding cache key includes the model digest; without the Protocol method, every cache lookup hardcodes "fastembed" — the wrong coupling).

The contributor-friction argument is the toolkit's "developer experience" cross-cut: the same justification that picks chromadb-local (no docker-compose) must pick fastembed-ONNX (no torch). Picking the heavier dep where the same argument applied would be the inconsistency the critic flagged.

## Consequences

- Phase 4 fence (ADR-0003) keeps `sentence_transformers` and `torch` in `PHASE4_STILL_FORBIDDEN` — these are now banned project-wide, not just in the gather pipeline. `tests/fence/test_no_sentence_transformers.py` asserts.
- `onnxruntime` is admitted in the Phase 4 fence (`PHASE4_ADMITTED_PACKAGES`), restricted to `src/codegenie/rag/`.
- Worker memory ceiling (Phase 4 addition): ~180 MB RSS for fastembed; ~100 MB for chromadb @ 10K examples; ~30 MB for the Anthropic client; total ~310 MB on top of Phase 3's ~400 MB.
- Phase-4 CI runs x86_64 (ubuntu-24.04) only. arm64 cross-host determinism test is a known Phase-6.5 follow-up; recorded as Open Question 8 in `final-design.md`.
- The embeddings cache (`.codegenie/rag/embeddings.cache.sqlite`) keys on BLAKE3 of input text and includes the `model_digest()` as a column — model upgrades automatically invalidate cached vectors.
- `.codegenie/rag/embeddings_model.lock` (sha256 + model name) is a refuse-start signal; a contributor who fat-fingers a model upgrade halts the worker rather than silently embedding into a different vector space.
- Phase 6.5's bench harness owns calibration (threshold band tuning) and includes the cross-arch determinism test; Phase 4 ships the bench fixtures.
- Phase 11's pgvector adapter swap is orthogonal — embeddings model is the same; only the store changes.

## Reversibility

**Medium.** Swapping to a different embeddings runtime (Voyage API, Cohere, a different ONNX model) is one adapter behind the existing `Embedder` Protocol — additive, no kernel change. Reverting to `sentence-transformers`+`torch` would require removing the Phase 4 fence's `PHASE4_STILL_FORBIDDEN` entries and adding ~250 MB to the install footprint, plus a re-embedding pass for the existing solved-example corpus (since cosine similarity is not preserved across embedding models). Reversal is feasible but expensive once the corpus has any size.

## Evidence / sources

- `../final-design.md §Component 8 — FastembedEmbedder`
- `../final-design.md §Patterns considered and deliberately rejected` (sentence-transformers + torch)
- `../final-design.md §Conflict-resolution table` row "Embedding model"
- `../phase-arch-design.md §Component 8 — Embedder + FastembedEmbedder`
- `../critique.md §"[B] §2"` (contributor-friction argument applied inconsistently in best-practices)
- `../critique.md §"[P] §3"` hidden assumption (cross-architecture float drift)
