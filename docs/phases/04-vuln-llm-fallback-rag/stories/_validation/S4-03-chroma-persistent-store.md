# Validation report: S4-03 — `SolvedExampleStore` Protocol + `ChromaPersistentStore`

**Validated:** 2026-05-22
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S4-03 ships the `SolvedExampleStore` Protocol + the `ChromaPersistentStore` adapter — the RAG substrate's read/write seam (ADR-0016: one Protocol, one in-tree chromadb adapter, Phase-11 pgvector swap behind the same port). The goal traces cleanly to arch §Component 7, final-design §7, HLI Step 4, ADR-0016, and Gap 3. The Ports-and-Adapters shape is correct and the YAGNI discipline (no speculative `update`/`delete`, deferred capability mint) is sound — those aspects are STRONG.

But the story carried one **block**-severity cross-story contradiction and a cluster of executor-confusing defects in its acceptance criteria and TDD plan. All were fixable in place, so the verdict is **HARDENED** — with one caveat the user must action: the block is a missing field on a *dependency* story (S1-04) that this validator cannot edit. S4-03 is hardened to depend on it explicitly and surfaces the required S1-04 amendment loudly.

16 findings — 1 block, 13 harden, 2 nit.

## Findings by critic

### Consistency critic

**C1 (block) — AC-4 reads `example.embedding_vector`, a field `SolvedExample` does not have.** AC-4's `add()` does `collection.add(..., embeddings=[list(example.embedding_vector)], ...)`. S1-04's `SolvedExample` model (already HARDENED) ships `id, task_class, language, build_system, cve_id, advisory_digest, plan_kind, plan_proposal, transform_digest, trust_outcome_digest, provenance, origin, embedding_model, created_at` — **no `embedding_vector`**. ADR-0016 §Consequences is explicit: `codegenie rag rebuild` re-inserts into chromadb "without re-embedding" because "records carry their embedding model digest **+ vector**". chromadb's default embedding function is `all-MiniLM`, not the pinned `fastembed` BGE-small — so the store *cannot* let chromadb embed `documents`; it must receive an explicit pre-computed vector. The only ADR-consistent home for that vector is a field on the canonical record. **Resolution:** S1-04 must be amended to add `embedding_vector: EmbeddingVector` to `SolvedExample` — a one-field extension-by-addition (a sanctioned enforcement mechanism per CLAUDE.md, not a silent edit). This validator hardened S4-03 to depend on that field explicitly and surfaced the amendment in the Validation notes (note B); it did **not** edit S1-04 (out of scope — one story per invocation, surgical edits only).

**C2 (harden) — `query`/`add` are `async` in the story but synchronous in arch §Component 7 + final-design §7.** Both design docs print `def query` / `def add`. The story (AC-1, AC-9) makes them `async def`. The async form is *correct* — arch §Concurrency (line 269) and HLI Step 4 mandate a process-local `asyncio.Lock` around `add()`; `asyncio.Lock.acquire()` must be `await`ed; `asyncio.to_thread` wrapping requires an async caller; AC-8's contention test `await`s `add`. The arch's code snippet is illustrative drift (the sibling `Embedder` Protocol in S4-01 is genuinely sync — it has no lock). The story silently resolved the conflict without acknowledgment. Per Global Rule 7 (surface conflicts, don't average), the validator added Notes §10 documenting the deviation and a forward-pointer in AC-1, so the executor does not "fix" it back to sync.

**C3 (harden) — missing dependency on S4-01.** The story says "*Extend* `src/codegenie/rag/errors.py`" and imports `from codegenie.rag.errors import ...`. S4-01 is the story that *creates* `rag/errors.py` (with `EmbeddingModelMismatch`, `EmbeddingsBootstrapRequired`); S1-05 creates the empty `rag/__init__.py`. The `Depends on` line listed only S1-04 and S1-05. Added S4-01.

**C4 (nit) — `StoreCorrupted` is declared but never exercised in S4-03.** Implementation Outline §2 adds `StoreCorrupted` "referenced by arch §Component 7 §Failure behavior" but no AC/test exercises it (corruption recovery is rebuild-from-YAML work, S4-04/S4-07). Left declared (it is part of the error family) but Outline §2 now says so explicitly, so the executor does not invent a corruption test.

**C5 (harden) — AC-4's `<doc_text>` construction referenced fields not on `SolvedExample`.** AC-4 said `<doc_text>` is "`Query`-shaped key text (`failure_mode`, `cve_id`, `affected_package`)". `affected_package` and `failure_mode` are `Query` fields, not `SolvedExample` fields. And once the explicit `embedding_vector` is the search key (C1), `documents` is non-searchable stored text anyway. Rewrote AC-4: the search key is `embeddings=[list(example.embedding_vector)]`; `documents=` is optional human-readable text only.

### Coverage critic

**V1 (harden) — `digest()` order-sensitivity had no test that adds records in a different order.** AC-6 states "different order returns a different digest. Order is the contract" and Notes §5 forbids sorting `_record_ids` — but the TDD plan's only digest test checked empty-≠-after-one-add. A sorting implementation would pass everything. Added `test_digest_is_insertion_order_sensitive`: two stores receive the same two records in opposite order → different digests; a third in the same order as store-1 → equal. Kills the sort mutant.

**V2 (harden) — partition isolation was tested but not an AC.** The TDD plan listed `test_partition_collections_are_independent`, but no AC made cross-partition isolation a checklist item. Added **AC-5b** — a record in partition P1 is never returned by a query against partition P2.

**V3 (harden) — `close()` idempotency unspecified.** AC-7 said query/add raise `StoreClosed` after `close()` but said nothing about a second `close()`. A lifecycle method that raises on double-close is a `try/finally`-teardown footgun. AC-7 now pins `close()` idempotent.

**V4 (harden) — `digest()`-after-`close()` undefined.** `digest()` is the third method; AC-7 covered only query/add. `digest()` is a pure projection over in-memory `_record_ids` and does not touch the client — it *can* and *should* still work. AC-7 now pins it: `digest()` survives `close()`, does not raise `StoreClosed`.

**V5 (harden) — AC-8 named two incompatible timeout-test mechanisms.** AC-8 prose said "patch `asyncio.wait_for` … or `freezegun` … or `monkeypatch` … to 0.1s" while the Red test `monkeypatch`es `_ADD_LOCK_TIMEOUT_SECONDS` to `0.05`. Settled on the single clean knob — `monkeypatch` the module constant — and reconciled the 0.1/0.05 drift.

### Test-Quality critic

**T1 (harden) — `test_add_then_query_returns_rag_hit` never queried.** The Red test named "…then query returns rag hit" only did `add` then a `digest()` check — it never called `query`. Worse, the public `query` returns `RagMiss` by contract (no vector), so a genuine `add → query → RagHit` round-trip is only reachable through the private `_query_with_embedding`. Split into two honest tests: `test_add_appends_record_and_changes_digest` (the digest-moves check, plus a positive empty-digest assert) and `test_add_then_query_with_embedding_returns_rag_hit` (the load-bearing round-trip via `_query_with_embedding`, asserting `RagHit` with score ≥ 0.99 when querying with the record's own vector). ADR-0016 §Consequences explicitly expects `test_store.py` to cover the "open/add/query round-trip" — now it does.

**T2 (harden) — empty-digest had no positive test.** The Red test asserted `digest() != empty_constant` after an add, but nothing asserted a *fresh* store's `digest()` *equals* the empty BLAKE3 constant. A `digest()` that hashes something unexpected on an empty store would pass. Added `test_empty_store_digest_is_blake3_of_empty` and pinned the constant as a module-level `_EMPTY_BLAKE3`.

**T3 (harden) — AC-9 fence pinned method *names* but not *signatures*.** A mutant that drops the `capability` parameter from `add` (defeating the capability gate — a load-bearing Context §4 property) would pass the name-set check. AC-9 now pins each method's `inspect.signature` — `add` is exactly `(self, example, capability)`, `query` exactly `(self, q, *, top_k, similarity_floor)`.

**T6 (harden) — AC-8's explanation of the `locked()` assertion was wrong.** AC-8 said "assert `locked()` is `False` after the raise (the `finally` released the never-acquired lock)". This contradicts the (correct) Implementation Outline §7 pattern: on timeout, `acquired` is `False`, so the `finally` does **not** release. After the raise the lock is still held by the *test's* manual `acquire()`; it returns to `False` only when the test releases it. The misleading parenthetical risked the executor implementing an *unguarded* `release()` — which would `RuntimeError` or desync the lock. Reworded AC-8 to describe the mechanics correctly and to state that the `locked()` assertion (after the test's own release) is what catches an unguarded-release mutant.

### Design-Patterns critic

**D1 (harden) — AC-5 contradicted Notes §4 on where the query vector enters.** AC-5 said the *public* `query` accepts an optional `query_embedding: EmbeddingVector | None` kwarg; Notes §4 picked option (B) — a *private* `_query_with_embedding`, public `query` returns `RagMiss`; AC-1's Protocol signature for `query` has no such kwarg. Three sources, three shapes. Resolved to option (B) consistently: rewrote AC-5 so the public `query` is exactly the AC-1 four-arg signature and returns `RagMiss`, and the private `_query_with_embedding(q, query_embedding, *, top_k, similarity_floor)` is the real read path S5-01 calls. AC-1 = AC-5 now, and AC-9's four-method fence stays intact. Updated Notes §4 to record the decision and Implementation Outline §6 to list both methods.

**D2 (harden) — `_load_existing_record_ids()` cannot reconstruct insertion order; `digest()` reopen-determinism is unbacked.** AC-3 said `_record_ids` is populated "in insertion order, populated by reading existing collections on init." chromadb's `collection.get()` does not guarantee insertion order, and there is one collection per partition — concatenating them gives an order driven by collection-iteration, not insertion. AC-6's order-sensitive `digest()` and S4-07's `rag rebuild` golden test (byte-identical digest after rebuild) would silently break across a close/reopen. The canonical insertion-order source is S4-04's `manifest.yaml` (an ordered `records` list per ADR-0016). Hardened: AC-3 now carries the caveat, AC-6 scopes its determinism contract to *within-process*, and Notes §11 records that cross-process determinism arrives with S4-04 — surfaced loudly per Rule 12 rather than claiming reopen-stability the implementation cannot deliver.

**D3 (harden) — AC-1's `close()` description was incorrect.** AC-1 said `close()` "closes the asyncio lock state." An `asyncio.Lock` has no teardown — there is nothing to close. Reworded: `close()` drops the chromadb client reference; the lock needs nothing.

**D4 (nit) — chromadb metadata flatness.** AC-4's `metadatas=[<metadata>]` was an unspecified placeholder. chromadb metadata must be a flat `str/int/float/bool` dict and cannot hold a nested `RecordProvenance`. Per the Out-of-scope section, `provenance` *is* persisted as metadata here (only its chain verification is deferred to S4-05) — so AC-4 now says metadata is a flat dict and `provenance` must be serialized to a flat field.

**STRONG aspects (recorded, no edit needed).** Ports-and-Adapters is correctly applied — one Protocol, one adapter, the Phase-11 pgvector swap is the *announced* second adapter (ADR-0017), so the Protocol earns its keep. The per-`(task_class, language, build_system)` collection partition is a clean data-driven seam — future task classes slot in without touching existing collections (Open/Closed). Notes §8 correctly resists speculative `update()`/`delete()` (Rule 2 / YAGNI). The capability-as-argument is correctly *declared here, minted later* (S4-06). The functional-core/imperative-shell split (`digest()` pure; `add`/`query` impure) is sound.

## Research briefs

No `NEEDS RESEARCH` findings. Every issue resolved from in-repo sources: S1-04 (`SolvedExample`/`Query`/`RetrievalOutcome` shapes), S4-01 (`rag/errors.py` ownership, sibling `Embedder` Protocol sync-ness, `EmbeddingVector` tuple newtype), ADR-0016 (records-carry-the-vector, single-writer, rebuild path), arch §Component 7/9/Concurrency/Gap 3, HLI Step 4, and the repo's extension-by-addition + fail-loud commitments.

## Conflict resolutions

- **Consistency vs. the arch code snippet (C2).** The arch §Component 7 snippet shows sync `def`; arch §Concurrency + HLI Step 4 mandate `asyncio.Lock`, which forces async. The two arch sections contradict each other. Resolved in favor of the *behavioral* requirement (the lock) over the *illustrative* snippet — the story's async choice stands, documented in Notes §10. Not averaged.
- **`digest()` determinism scope (D2).** Coverage wanted a strong order-sensitivity guarantee; Design-Patterns showed cross-process order is unrecoverable in S4-03. Resolved by *scoping* the contract (within-process, deterministic; cross-process deferred to S4-04's manifest) rather than weakening or over-claiming it.

## Edits applied

1. Header `Status: Ready → HARDENED`; `Depends on` adds S4-01 and the explicit `embedding_vector` requirement on S1-04; `Validation notes` block inserted with the surfaced cross-story blocker (note B).
2. AC-1 — `close()` description corrected; async-vs-sync deviation forward-referenced to Notes §10.
3. AC-3 — insertion-order caveat for `_load_existing_record_ids()`.
4. AC-4 — `embedding_vector` dependency made explicit; `documents`-as-search-key removed; metadata flatness + provenance-serialization pinned.
5. AC-5 — rewritten as public `query` (Protocol surface, returns `RagMiss`) + private `_query_with_embedding` (real read path); **AC-5b** added for partition isolation.
6. AC-6 — positive empty-digest assertion, explicit opposite-order requirement, within-process determinism scope.
7. AC-7 — `close()` idempotency + `digest()`-survives-close.
8. AC-8 — single timeout mechanism (`monkeypatch` the constant); corrected `locked()`-assertion mechanics.
9. AC-9 — `inspect.signature` pinning for all four methods.
10. Implementation Outline §2 (`StoreCorrupted` declared-not-exercised), §6 (both read methods + `_check_open`), §7 (constant, not literal `30.0`).
11. TDD plan — Red tests rewritten/split; imports updated (`RagHit`, `make_query_matching`); follow-on test list expanded to nine sharp tests.
12. Green section — four public methods + private `_query_with_embedding`.
13. Files to touch — `fake_solved_example.py` row notes `embedding_vector` + `make_query_matching`.
14. Notes — §4 rewritten (option B decided), §10 (async deviation) + §11 (digest cross-process scope) added.

## Verdict rationale

HARDENED. The story's goal, scope, and architectural shape are correct — Ports-and-Adapters with a properly announced second adapter, clean partition seam, sound YAGNI discipline. No scope rewrite was needed, so this is not a RESCUE. The defects were real but local: one cross-story field contradiction (C1), three internal contradictions among AC-1/AC-5/Notes-§4 and within AC-8, and a cluster of under-specified lifecycle/coverage gaps. All were patchable in place.

**One caveat the user must action:** finding C1 requires a one-field amendment to story **S1-04** (`add embedding_vector: EmbeddingVector to SolvedExample`). This validator does not edit sibling stories. S4-03 is hardened to depend on the field explicitly and stays `HARDENED`, but **it must not be executed until S1-04 carries `embedding_vector`** — otherwise the executor will stall on AC-4.

## Recommended next step

1. Amend story **S1-04** (`S1-04-rag-pydantic-models.md`) to add `embedding_vector: EmbeddingVector` to the `SolvedExample` model (and its `extra="forbid"`/round-trip tests). This is the precondition for S4-03.
2. Then run `phase-story-executor` on S4-03.
