# ADR-0006: `BAAI/bge-small-en-v1.5` as default embedding model, SHA-pinned via `huggingface_hub.snapshot_download(revision=<sha>)`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** embedding-model · supply-chain · retrieval-quality · synthesizer-departure
**Related:** [ADR-0005](0005-chromadb-in-process-with-stale-lock-detection.md), [Phase 2 ADR-0005](../../02-context-gather-layers-b-g/ADRs/) (binary digest pin precedent)

## Context

Retrieval quality on CVE advisory text + diff metadata is the second-most-important variable for Phase 4 cost (after prompt caching). Two of the three lens designs picked `sentence-transformers/all-MiniLM-L6-v2` (384-d, general-purpose STS-trained); best-practices picked `BAAI/bge-small-en-v1.5` (384-d, BEIR-leading on technical-text retrieval). The critic (`critique.md §performance.1`) attacked MiniLM specifically: cosine scores compress hard above 0.7 on lexically similar text, and an advisory whose summary repeats the package name twice will trivially clear `τ_hit = 0.86` against unrelated advisories on the same package — silent wrong-bump. The `τ_hit` short-circuits the LLM, so a bad embedding model makes the cache hierarchy a wrong-answer cache.

`final-design.md §"Components"` #8 picks `bge-small-en-v1.5` to resolve the critic's attack. The dimensions stay at 384 (drop-in for the chromadb collection); only retrieval quality differs.

## Options considered

- **`sentence-transformers/all-MiniLM-L6-v2` (384-d).** Performance + security lens default. Mature, widely deployed, easy CI footprint. Critic attack on cosine compression unaddressed.
- **`BAAI/bge-small-en-v1.5` (384-d).** Best-practices pick. Materially better BEIR scores on technical-text retrieval. Same dimensions as MiniLM so swap-in is mechanical for a future re-embed (not a chromadb-collection migration).
- **`BAAI/bge-base-en-v1.5` (768-d).** Larger sibling. Likely better retrieval at 2× memory + storage. Picked as a tunable swap if the labeled benchmark demands.
- **`voyage-code-2` (paid).** Voyage AI's code-tuned model. Best published numbers on code retrieval; requires an API call (Phase 4's local-first commitment violated). Registered as a stub (`VoyageProvider`); opt-in via env var; not the default.

## Decision

Default `EmbeddingProvider` is `SentenceTransformerProvider(model_id="BAAI/bge-small-en-v1.5")`, 384-d, SHA-pinned via `huggingface_hub.snapshot_download(repo_id, revision=<commit_sha>)`. The pinned SHA lives in `tools/digests.yaml`. Model weights cache to `~/.cache/codegenie/models/bge-small-en-v1.5/<digest>/` (~120 MB on disk; ~50 MB resident). Hash mismatch is hard-fail at engine init. Telemetry disabled at import time. `VoyageProvider` is registered but opt-in via `--embed-model=voyage`.

**Operator first-fetch:** `codegenie models fetch` downloads and verifies; airgapped operators pre-stage the model at the cache path and set `HF_HUB_OFFLINE=1`. **First-write protection on `tools/digests.yaml`:** any change to the SHA requires an explicit operator ADR amendment (mechanism: pre-commit hook checks for a `digest-amended` PR label) — closes critic §security.5b (poisoned-first-fetch can't silently certify itself).

## Tradeoffs

| Gain | Cost |
|---|---|
| Retrieval quality on CVE advisory + diff text is materially better than MiniLM — `τ_hit = 0.86` doesn't trivially clear on package-name-collision pairs | ~120 MB model on disk vs MiniLM's ~80 MB; ~50 MB resident; one-time download for new operators |
| 384-d matches MiniLM, so the chromadb collection can swap embedding models with a re-embed (not a schema migration) | A model bump still requires re-embedding the entire corpus before queries match; `codegenie solved-examples reindex --model-digest <new>` is the recovery path (see [ADR-0005](0005-chromadb-in-process-with-stale-lock-detection.md) and Gap 2 fix) |
| SHA-pinning + hard-fail on mismatch closes the supply-chain channel — a compromised HF mirror serving a different `.safetensors` is caught at load | First-fetch path is a separate operator workflow (`codegenie models fetch`); airgapped operators need documentation |
| `tools/digests.yaml` first-write protection closes the "first download from a poisoned mirror certifies itself" attack | Operators changing the model digest must understand the ADR amendment workflow; friction is intentional |
| `VoyageProvider` registered now means the swap to a paid code-tuned model is opt-in, not a refactor | Voyage adds a network egress in production mode + an API key to manage; not enabled until measured quality lift justifies |
| Telemetry-off at import time blocks the silent metrics-phone-home channel | Telemetry-disable must run *before* any `chromadb` or `sentence_transformers` import; ordering bug surface |

## Consequences

- `EmbeddingProvider` lives in `src/codegenie/rag/contract.py` as a Protocol. `SentenceTransformerProvider` is the only concrete implementation in v0.4.0; `VoyageProvider` is a registered stub.
- `model_digest` is in the chromadb collection metadata *and* on every `SolvedExample`. `SolvedExampleStore.read().query` filters by current `EmbeddingProvider.model_digest` so no caller can mix vector spaces (Gap 2 fix).
- Model digest mismatch is graded: at engine init (hard-fail); on every load (re-verify, hard-fail); on writeback (refuses, surfaces via `solved_example_health.confidence = low`).
- `SolvedExampleHealthProbe` reports `mixed_embedding_models: bool` — Phase 4 surfaces; Phase 5 gates.
- Embedding runs in a long-lived UDS sidecar (`embed_worker.py` over `unix:.codegenie/run/embed.sock`) when session ≥ 2 workflows; in-proc fallback for one-shot CLI. Semaphore (max 4 concurrent) bounds contention. Cold boot ≤ 2.5s; warm embed ~28ms for one ~400-token query.

## Reversibility

**Medium.** Swapping the default model means a re-embed across the corpus (linear in example count, ~50ms each via sidecar). The mechanism is `codegenie solved-examples reindex --model-digest <new>`. The *digest pin* is reversible per ADR amendment; the *model family* swap requires the reindex tool to work — covered in Phase 4 as the supported operator workflow.

## Evidence / sources

- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Embedding model"
- `../final-design.md §"Components"` #8 — `EmbeddingProvider` ABC + `SentenceTransformerProvider`
- `../phase-arch-design.md §"Component design"` #7 — `EmbeddingProvider`
- `../phase-arch-design.md §"Gap analysis" §"Gap 2"` — embedding digest filter in queries
- `../critique.md §performance.1` — MiniLM cosine-compression attack
- `../critique.md §security.5` — first-fetch digest poisoning
