# Story S4-03 — `SolvedExampleStore` Protocol + `ChromaPersistentStore` + asyncio.Lock with 30s timeout

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** HARDENED
**Effort:** L
**Depends on:** S1-04 (`SolvedExample`, `Query`, `RetrievalOutcome`, `RecordProvenance` Pydantic models; `SolvedExampleId`, `StoreDigest`, `Similarity` Newtypes — **plus the `embedding_vector` field on `SolvedExample`; see Validation note B — S1-04 as currently specified omits it and must be amended before this story executes**), S1-05 (path-scoped fence admits `chromadb` only under `src/codegenie/rag/`; creates the empty `src/codegenie/rag/__init__.py` namespace marker), S4-01 (creates `src/codegenie/rag/errors.py` and the `rag` package's first error types — **this story *extends* that module**)
**ADRs honored:** ADR-0016 (chromadb PersistentClient embedded; YAML canonical; sqlite derived; single-writer constraint declared in Protocol + enforced by `asyncio.Lock`; per-(task_class, language, build_system) collection), Gap 3 (lock-contention contract: 30s `await`, then raise `StoreWriteContention`)

## Validation notes

Validated: 2026-05-22
Verdict: HARDENED
Findings addressed: 16 — 1 block, 13 harden, 2 nit

**Surfaced cross-story blocker (note B) — requires an S1-04 amendment before this story can execute.** AC-4 reads `example.embedding_vector` and `add()` passes it to chromadb as `embeddings=[...]`. ADR-0016 §Consequences mandates that canonical records carry "embedding model digest **+ vector**" so `codegenie rag rebuild` can re-insert into chromadb *without re-embedding*. But S1-04's `SolvedExample` model (already HARDENED) ships fields `id … embedding_model, created_at` with **no `embedding_vector`**. The chromadb default embedding function is `all-MiniLM`, not the pinned `fastembed` BGE-small, so the store *must* receive an explicit pre-computed vector — it cannot fall back to letting chromadb embed `documents`. Resolution: S1-04 must be amended to add `embedding_vector: EmbeddingVector` to `SolvedExample` (a one-field extension-by-addition — adding a struct field is a sanctioned enforcement mechanism per CLAUDE.md, not a silent edit). This story is hardened to depend on that field explicitly; it stays `HARDENED` (the goal/shape are sound) but **must not be executed until S1-04 carries `embedding_vector`**.

Changes applied:
- **AC-4 fixed (block, note B)** — made the `example.embedding_vector` dependency explicit; the search key is `embeddings=[list(example.embedding_vector)]`, not `documents`. The `<doc_text>` requirement was removed: it referenced `affected_package`/`failure_mode`, which are `Query` fields, not `SolvedExample` fields, and `documents` is non-searchable stored text once an explicit vector is supplied.
- **AC-1 / AC-9 (harden)** — the Protocol's `query`/`add` are `async def`; arch §Component 7 and final-design §7 show them as sync `def`. The async form is correct (`asyncio.Lock` + `asyncio.to_thread` both require `await`; arch §Concurrency + HLI Step 4 mandate the lock). Added Notes §10 acknowledging the deviation so the executor does not "fix" it back to sync. AC-9 now also pins each method's signature, not just its name.
- **AC-5 / Notes §4 (harden)** — removed the contradiction: AC-5 previously said the *public* `query` accepts a `query_embedding` kwarg, while Notes §4 picked option (B) (a *private* `_query_with_embedding`). AC-5 now matches AC-1's four-arg Protocol signature; the private `_query_with_embedding` is the real read path S5-01 calls.
- **AC-3 / Notes §11 (harden)** — `_load_existing_record_ids()` cannot reconstruct true insertion order across multiple chromadb collections; the canonical insertion-order source is S4-04's `manifest.yaml`. `digest()` cross-process determinism is therefore deferred to S4-04; S4-03's `digest()` contract is within-process (order of `add()` calls in the live store).
- **AC-7 (harden)** — pinned `close()` idempotency (a second `close()` is a no-op) and `digest()`-after-`close()` behavior (still works — pure in-memory projection).
- **AC-8 (harden)** — fixed the misleading parenthetical: on timeout the `add()` `finally` does **not** release (the `acquired` guard is `False`); the lock returns to unlocked only when the test releases its own manual hold. The `locked()` assertion catches an unguarded `release()` mutant. Settled on one timeout mechanism — `monkeypatch` of `_ADD_LOCK_TIMEOUT_SECONDS` — and reconciled the 0.1s/0.05s drift.
- **TDD plan (harden)** — `test_add_then_query_returns_rag_hit` never queried; renamed and split. Added: a real `add → _query_with_embedding → RagHit` round-trip; a positive empty-store-digest test; an explicit insertion-order-sensitivity test (two stores, same records, opposite order → different digests).
- Nits: `StoreCorrupted` is declared-but-not-exercised here (corruption recovery is later work); chromadb metadata must be a flat `str/int/float/bool` dict.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S4-03-chroma-persistent-store.md

## Context

The RAG substrate's read/write seam. ADR-0016 commits Phase 4 to **one Protocol** (`SolvedExampleStore`) with **one in-tree adapter** (`ChromaPersistentStore` over `chromadb.PersistentClient` in embedded mode); a Phase-11 pgvector adapter swap happens behind the same Protocol. The load-bearing constraints — captured by the critic and documented in Gap 3 + edge case #5:

1. **Single-writer.** chromadb's HNSW writer is single-threaded; concurrent ingest from 24 portfolio workers (Phase 11) needs **declared** serialization, not silent racing. Phase 4 declares this in the Protocol's docstring and enforces it inside `ChromaPersistentStore` via a process-local `asyncio.Lock`.
2. **30 s lock-contention contract.** `add()` `await`s the lock with a 30 s timeout; on timeout raises `StoreWriteContention(workflow_id)`. S4-08 pins the behavior with an integration test under `asyncio.gather`; Phase 11's pgvector swap must conform.
3. **Per-`(task_class, language, build_system)` collection partition.** Smaller HNSW indexes; O(1) collection lookup at query time; future task classes (Phase 7 distroless, Phase 15 recipe authoring) land in their own collections without touching existing ones.
4. **`add()` is capability-gated.** The `SolvedExampleWriteCapability` argument is required; the type is **declared here** (a frozen, opaque marker class) and **minted** in S4-06's `_phase4_local_capability_mint`. Read paths (`query`) require no capability.

This story ships the Protocol shape + the chromadb-backed adapter's read/add/digest/close lifecycle **without** wiring the YAML-canonical layer yet — S4-04 lands the YAML canonical write + manifest. The `add()` implementation here writes to chromadb only; S4-04 layers the atomic YAML write on top. (Surface this carefully — Notes §1.)

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 7 — SolvedExampleStore + ChromaPersistentStore` — public Protocol (`query`, `add`, `digest`, `close`); chromadb embedded mode; per-collection partition.
  - `../phase-arch-design.md §"Concurrency"` (line 269) — `SolvedExampleStore.add` is single-writer; `asyncio.Lock` guards it.
  - `../phase-arch-design.md §Edge case #5` — chromadb writer contention under concurrent harvest → `asyncio.Lock` serializes; both records land deterministically.
  - `../phase-arch-design.md §"Gap 3"` (line 1106) — lock-contention contract: 30 s `await`, then `StoreWriteContention`; `tests/integration/test_phase4_harvest_contention.py` pins behavior.
- **Phase ADRs:**
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` — full decision; capability-gated write; per-collection partition; rebuild path.
  - `../ADRs/0007-fastembed-onnx-over-sentence-transformers.md` — `chromadb` admitted only under `src/codegenie/rag/`.
- **Production ADRs:**
  - `../../../production/adrs/0017-knowledge-graph-backend.md` — Phase-11 backend deferral; pgvector / qdrant / Neo4j candidates; this Protocol is the seam.
- **Source design:**
  - `../final-design.md §Component 7` — Protocol + chromadb single-writer.
- **Existing code (precedent to mirror):**
  - `src/codegenie/cache/` — Phase-0 content-addressed storage layout (file naming conventions, BLAKE3 keying).
  - `src/codegenie/probes/registry.py` — `@runtime_checkable` Protocol idiom.

## Goal

Ship `SolvedExampleStore` Protocol + `ChromaPersistentStore` adapter at `src/codegenie/rag/store.py` with the four-method surface (`query`, `add`, `digest`, `close`), capability-gated `add()` under a process-local `asyncio.Lock` with a 30 s timeout raising `StoreWriteContention`, per-`(task_class, language, build_system)` chromadb collection partitioning, and a `digest() -> StoreDigest` projection returning the BLAKE3-rolled head over the current record-id list — queryable in isolation before S5-01's retriever composes it.

## Acceptance criteria

- [ ] **AC-1 — `SolvedExampleStore` Protocol declaration.** `src/codegenie/rag/store.py` exports `SolvedExampleStore` as a `@runtime_checkable` `Protocol` with **exactly four** non-dunder member names:
    - `async def query(self, q: Query, *, top_k: int = 5, similarity_floor: float | None = None) -> RetrievalOutcome`.
    - `async def add(self, example: SolvedExample, capability: SolvedExampleWriteCapability) -> SolvedExampleId`.
    - `def digest(self) -> StoreDigest` — synchronous; pure projection over current record IDs.
    - `def close(self) -> None` — synchronous; releases the chromadb client. (An `asyncio.Lock` needs no teardown — do **not** write "close the lock"; there is nothing to close. `close()` only drops the chromadb client reference.)
    `query`/`add` are `async def`; arch §Component 7 and final-design §7 show them as sync `def`, but the `asyncio.Lock` (arch §Concurrency, HLI Step 4) and `asyncio.to_thread` wrapping both require `await`. The async form is the resolved contract — see Notes §10.
    Module docstring states the **single-writer constraint** verbatim per ADR-0016 §Decision (and AC-9's fence test grep-anchors on the phrase "single-writer constraint").
- [ ] **AC-2 — `SolvedExampleWriteCapability` marker shape.** `src/codegenie/rag/store.py` exports `SolvedExampleWriteCapability` as a `@final` frozen dataclass with one field: `workflow_id: WorkflowId`. The class has no public constructor in user-visible surface — S4-06 ships the `_phase4_local_capability_mint` factory; this story only declares the type. Tests in this story construct it via direct call inside the test module (boundary lift acknowledged with `# AC-2-test-only-direct-construction` comment near the construction site).
- [ ] **AC-3 — `ChromaPersistentStore.__init__` opens chromadb embedded mode.** `ChromaPersistentStore(root_dir: Path)`:
    - Calls `chromadb.PersistentClient(path=str(root_dir / "chroma"))` exactly once; caches the client on `self._client`.
    - Resolves collection-per-partition lazily: `_get_collection(task_class, language, build_system) -> chromadb.Collection` uses `client.get_or_create_collection(name=f"{task_class}__{language}__{build_system}")`.
    - Creates a single asyncio lock on `self._add_lock = asyncio.Lock()`.
    - Initializes `self._record_ids: list[SolvedExampleId] = []`, populated by reading existing collections on init (call `_load_existing_record_ids()`; if no collections exist yet, list is empty). **Insertion-order caveat:** chromadb's `collection.get()` does not guarantee insertion order, and there is one collection per partition — so `_load_existing_record_ids()` cannot reconstruct the true cross-process insertion order in S4-03. It loads in chromadb's returned order; the canonical insertion-order source is S4-04's `manifest.yaml`. See AC-6 and Notes §11 — `digest()` cross-process (close/reopen) determinism is deferred to S4-04; S4-03's `digest()` contract is within-process only.
- [ ] **AC-4 — `add()` writes to the partition collection and appends to record_ids.** `await store.add(example, capability)`:
    - Acquires `self._add_lock` with a `_ADD_LOCK_TIMEOUT_SECONDS` (default `30.0`) timeout via `asyncio.wait_for(self._add_lock.acquire(), timeout=_ADD_LOCK_TIMEOUT_SECONDS)`. Timeout → raise `StoreWriteContention(workflow_id=capability.workflow_id)`. The lock is released in a `finally` **guarded by an `acquired` flag** (Implementation Outline §7) — never call `release()` on a lock this coroutine did not acquire.
    - Resolves `collection = self._get_collection(example.task_class, example.language, example.build_system)`.
    - Calls `collection.add(ids=[example.id], embeddings=[list(example.embedding_vector)], metadatas=[<metadata>])` — the **search key is the explicit pre-computed `example.embedding_vector`** (a 384-tuple per S1-01's `EmbeddingVector = NewType("EmbeddingVector", tuple)`). **Do not** pass `documents=` as a search-driving field: chromadb's default embedding function is `all-MiniLM`, not the pinned `fastembed` BGE-small, so letting chromadb embed `documents` would produce vectors incompatible with the retriever's query vectors. `documents=` may be passed as optional human-readable stored text, but it is **not** the query key. (See Validation note B: `example.embedding_vector` requires the S1-04 amendment.)
    - `<metadata>` is a **flat `dict[str, str | int | float | bool]`** — chromadb metadata cannot hold nested models. Carry the partition triple, `embedding_model`, and the `provenance` **serialized to a flat field** (e.g. `provenance.event_chain_head` as a string, or the whole `RecordProvenance` as a JSON string) — Out of scope confirms `provenance` *is persisted as metadata here*; only its chain *verification* is deferred to S4-05. Do not attempt to store the nested `RecordProvenance` object directly — chromadb will reject it.
    - chromadb `collection.add` is **sync** (confirm via the spike, Implementation Outline §1); to honor "don't block the event loop", wrap in `await asyncio.to_thread(collection.add, ...)` per Risks section of `High-level-impl.md §Step 4`.
    - Appends `example.id` to `self._record_ids`.
    - Returns `example.id`.
- [ ] **AC-5 — public `query()` honors the Protocol surface; the real read path is private `_query_with_embedding()`.** This story implements **two** read methods (resolving the AC-1 ↔ Notes §4 design choice — option B):
    - **Public `query(q: Query, *, top_k=5, similarity_floor=None) -> RetrievalOutcome`** — exactly the AC-1 Protocol signature (**no `query_embedding` parameter** — adding one would break the four-method Protocol surface and AC-9's fence). chromadb similarity search needs a *pre-embedded* vector; a `Query` carries typed fields, not a vector, and this story ships no embedder inside the store. The public `query` therefore **resolves the partition collection** from `q.task_class, q.language, q.build_system` and **returns `RagMiss`** — it cannot produce a `RagHit` without a vector. Its docstring states: "the embedding-bearing read path is `_query_with_embedding`, called by `SolvedExampleRetriever` (S5-01); the public `query` returns `RagMiss` until the retriever is wired." This keeps the Protocol surface honest about what it does without a vector.
    - **Private `_query_with_embedding(q: Query, query_embedding: EmbeddingVector, *, top_k=5, similarity_floor=None) -> RetrievalOutcome`** — the in-house read path S5-01 calls. Resolves the partition collection from `q`; if the collection doesn't exist (no records ever added for that partition) → returns `RagMiss` (per arch §Component 9 "Returns `RagMiss` rather than raising when the store is empty"). Otherwise runs `await asyncio.to_thread(collection.query, query_embeddings=[list(query_embedding)], n_results=top_k)`, takes the top result, and returns `RagHit(few_shot=record, score=Similarity(top_score))` if `similarity_floor is None or top_score >= similarity_floor`; else `RagMiss`.
    - **NO band classification here** — the two-threshold band is S5-02; both methods return only `RagHit | RagMiss` (never `RagDegraded`), wired to `similarity_floor` alone.
- [ ] **AC-5b — partition collections are isolated.** A record added under partition `(task_class=A, language=L, build_system=B)` is **never** returned by a `_query_with_embedding` against a different partition triple. The query routes to exactly one collection (O(1) lookup); cross-partition leakage is a correctness failure. (Pinned by `test_partition_collections_are_independent`.)
- [ ] **AC-6 — `digest()` is BLAKE3-rolled over the current record-id list.** `digest()`:
    - `h = blake3.blake3()`; for each `id in self._record_ids` (in insertion order): `h.update(id.encode("utf-8"))`.
    - Returns `StoreDigest(h.hexdigest())`.
    - Empty store → returns `StoreDigest(blake3.blake3().hexdigest())` (the BLAKE3 of empty bytes — deterministic; the literal hex is `af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262`). A fresh store's `digest()` **equals** this constant — pinned by a positive test, not only by the `!=`-after-add direction.
    - Two stores that received the **same records in the same order** return identical digests; one store receiving the same records in a **different order** returns a **different** digest. Order is the contract — pinned by an explicit two-store opposite-order test (TDD plan). **Do not sort** `_record_ids` before rolling (Notes §5).
    - **Within-process scope.** This insertion-order contract holds for the order of `add()` calls in the *live* store. Cross-process determinism (close → reopen → `digest()` byte-identical) is **not** guaranteed in S4-03 because `_load_existing_record_ids()` cannot reconstruct chromadb insertion order (AC-3 caveat); S4-04's `manifest.yaml` is the canonical insertion-order source that makes the rebuild golden test (S4-07) deterministic. See Notes §11.
- [ ] **AC-7 — `close()` releases the client; is idempotent; `digest()` survives it.** After `store.close()`:
    - `self._client = None`.
    - Subsequent `query` / `_query_with_embedding` / `add` calls raise `StoreClosed` (typed exception in `codegenie.rag.errors`).
    - **`close()` is idempotent** — a second `close()` on an already-closed store is a no-op (returns `None`, raises nothing). A lifecycle method that raises on double-close is a footgun for `try/finally` teardown.
    - **`digest()` still works after `close()`** — it is a pure projection over the in-memory `self._record_ids`, which `close()` does not clear; it does not touch `self._client`. `digest()` does **not** raise `StoreClosed`. (Pinned by a follow-on test.)
- [ ] **AC-8 — `StoreWriteContention` integration test (the load-bearing pin).** `tests/integration/test_phase4_store_contention_30s.py` (the SHORT version of S4-08's `harvest_contention` test — the full multi-coroutine `asyncio.gather` version lives in S4-08):
    - **One** timeout mechanism: `monkeypatch.setattr("codegenie.rag.store._ADD_LOCK_TIMEOUT_SECONDS", 0.05)`. Do not patch `asyncio.wait_for` and do not use `freezegun` — patching the module constant is the clean, single-knob approach and matches the Red test below.
    - Acquire `store._add_lock` manually in the test (`await store._add_lock.acquire()`), then call `await store.add(example, capability)`; with the lock held, the `add()` must time out.
    - Assert `StoreWriteContention` raised with `exc.workflow_id == capability.workflow_id`.
    - **Then the test releases its own manual hold** (`store._add_lock.release()` in a `finally`) and asserts `store._add_lock.locked() is False`. Note the mechanics precisely: on timeout, `add()`'s `acquired` flag is `False`, so its `finally` does **not** call `release()` — the lock stays held by the *test* until the test releases it. This assertion catches a buggy `add()` that calls `release()` **unguarded** (without the `acquired` flag): an unguarded release on a lock `add()` never acquired would either raise `RuntimeError` or desync the lock so the test's own `release()` fails. Verify the `try/except/finally` from Implementation Outline §7 — the `acquired` guard is the load-bearing detail.
- [ ] **AC-9 — `SolvedExampleStore` Protocol fence test.** `tests/fence/test_solved_example_store_protocol_frozen.py` asserts:
    - `{n for n in dir(SolvedExampleStore) if not n.startswith("_")} == {"query", "add", "digest", "close"}` (exactly four; no fifth method, no speculative `update`/`delete` — Notes §8).
    - `inspect.iscoroutinefunction(SolvedExampleStore.query)` is `True`; same for `add`.
    - `inspect.isfunction(SolvedExampleStore.digest)` AND not coroutine; same for `close`.
    - **Signatures are pinned, not just names** — via `inspect.signature`: `add`'s parameter list is exactly `(self, example, capability)` (the `capability` gate is load-bearing — a mutant that drops it must fail the fence); `query`'s is exactly `(self, q, *, top_k, similarity_floor)`; `digest`/`close` take only `(self)`. This catches a "rename a name back, keep the signature wrong" mutant that the name-set check alone misses.
    - Module docstring of `store.py` contains the literal substring `"single-writer constraint"` (the load-bearing ADR-0016 framing).
- [ ] **AC-10 — Path-scoped fence still green.** `tests/fence/test_pyproject_fence_phase4.py` passes; `chromadb` imported only inside `src/codegenie/rag/store.py`.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean.

## Implementation outline

1. **Spike first** (Risks line 140 of High-level-impl.md): a one-page script that creates a `chromadb.PersistentClient`, opens a collection, calls `add` from two `asyncio.gather`-launched coroutines under `asyncio.to_thread`, confirms no deadlock and the asyncio.Lock works correctly. **If chromadb itself blocks the loop** (it's CPython sync code under the hood), the `asyncio.to_thread` wrapping is the correct shape — confirm via the spike before proceeding. **Throw the spike away** before opening the PR; it lives as a comment in the module docstring naming the verified posture.
2. **`errors.py` additions** — *extend* the `src/codegenie/rag/errors.py` module S4-01 creates. Add `StoreWriteContention(Exception)` with a `workflow_id: WorkflowId` typed attribute; `StoreClosed(Exception)`; `StoreCorrupted(Exception)`. All three are named by arch §Component 7 §Failure behavior. `StoreWriteContention` and `StoreClosed` are *exercised* by this story's tests (AC-8, AC-7); `StoreCorrupted` is **declared here for the family but not raised in S4-03** — corruption-recovery is later work (rebuild-from-YAML, S4-04/S4-07). Do not write a test that forces `StoreCorrupted` in this story.
3. **`store.py` skeleton** — `from __future__ import annotations`; module docstring naming ADR-0016, the single-writer constraint, the Phase-11 pgvector swap precondition.
4. **`SolvedExampleWriteCapability`** — `@final` frozen dataclass with `workflow_id: WorkflowId`. No constructor magic. Docstring says "minted by `_phase4_local_capability_mint` in S4-06; do not construct directly outside the mint module."
5. **`SolvedExampleStore` Protocol** — `@runtime_checkable`; four-method surface per AC-1. Method docstrings encode the contract (idempotency, error shapes, return invariants).
6. **`ChromaPersistentStore` class**:
   - `__init__(self, root_dir: Path)` — no embedder injected (the store does not embed; see Notes §4).
   - `_get_collection(task_class, language, build_system) -> chromadb.Collection`.
   - `_load_existing_record_ids()` — see AC-3 caveat + Notes §11.
   - `add(self, example, capability)`: lock + `asyncio.to_thread(collection.add, ...)` (`embeddings=[list(example.embedding_vector)]`) + record_ids append.
   - `query(self, q, *, top_k=5, similarity_floor=None)` — the AC-1 Protocol surface; resolves the partition and returns `RagMiss` (no vector available; AC-5).
   - `_query_with_embedding(self, q, query_embedding, *, top_k=5, similarity_floor=None)` — the real read path: partition lookup + `asyncio.to_thread(collection.query, ...)` → `RagHit | RagMiss`. Called by S5-01's retriever.
   - `digest()`: rolled BLAKE3 over `_record_ids`.
   - `close()`: idempotent; drops the client; `digest()` still works after.
   - `_check_open()` helper: raises `StoreClosed` when `self._client is None` — called at the top of `add` / `query` / `_query_with_embedding` (not `digest`).
7. **30s timeout pattern (subtle):**
   ```python
   acquired = False
   try:
       await asyncio.wait_for(
           self._add_lock.acquire(), timeout=_ADD_LOCK_TIMEOUT_SECONDS
       )
       acquired = True
       # ... do work
   except asyncio.TimeoutError as e:
       raise StoreWriteContention(workflow_id=capability.workflow_id) from e
   finally:
       if acquired:
           self._add_lock.release()
   ```
   Use the module constant `_ADD_LOCK_TIMEOUT_SECONDS` (default `30.0`), never a literal — AC-8's test monkeypatches the constant.
8. **Tests:**
   - `tests/unit/rag/test_store.py` covers AC-3 through AC-7; AC-9 fence test in `tests/fence/`.
   - `tests/integration/test_phase4_store_contention_30s.py` covers AC-8 (the SHORT contention test; S4-08 lands the full `asyncio.gather` version with two coroutines + monotonic chain head).
   - Tests use an in-process `tmp_path / "rag"` chromadb dir; teardown calls `store.close()`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/rag/test_store.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.rag.errors import StoreWriteContention
from codegenie.rag.models import RagHit
from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleWriteCapability,
)
from codegenie.types.identifiers import (
    SolvedExampleId,
    StoreDigest,
    WorkflowId,
)
# Test fixtures (S1-04 ships SolvedExample/Query; this story ships the builders):
from tests.fixtures.rag.fake_solved_example import (
    make_query_matching,
    make_solved_example,
)


_EMPTY_BLAKE3 = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
# ^ BLAKE3 hexdigest of empty input — AC-6.


@pytest.mark.asyncio
async def test_add_appends_record_and_changes_digest(tmp_path: Path) -> None:
    """ADR-0016 §Decision: chromadb is the queryable derived index.
    Catches the "add never writes" mutant: a no-op add leaves digest at
    the empty-BLAKE3 constant."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-001"))
    example = make_solved_example(
        id_="ex-001",
        task_class="vuln_remediation",
        language="typescript",
        build_system="npm",
        cve_id="CVE-2026-1234",
    )
    assert store.digest() == StoreDigest(_EMPTY_BLAKE3)  # fresh store (AC-6)

    sid = await store.add(example, cap)
    assert sid == SolvedExampleId("ex-001")
    # After one add, digest must have moved off the empty constant.
    assert store.digest() != StoreDigest(_EMPTY_BLAKE3)
    store.close()


@pytest.mark.asyncio
async def test_add_then_query_with_embedding_returns_rag_hit(tmp_path: Path) -> None:
    """The load-bearing round-trip: a record added to the store is
    retrievable. Catches the "query always returns RagMiss" mutant and a
    "store.add silently drops the vector" mutant. Uses the private
    _query_with_embedding (AC-5) — the public query() has no vector and
    returns RagMiss by contract."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-001"))
    example = make_solved_example(id_="ex-001")  # carries embedding_vector
    await store.add(example, cap)

    q = make_query_matching(example)  # same partition triple as `example`
    outcome = await store._query_with_embedding(
        q, example.embedding_vector, top_k=5
    )
    assert isinstance(outcome, RagHit)
    assert outcome.few_shot.id == SolvedExampleId("ex-001")
    # Querying with the record's own vector → top similarity ~1.0.
    assert outcome.score >= 0.99
    store.close()


@pytest.mark.asyncio
async def test_add_under_contention_raises_store_write_contention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gap 3 + edge case #5: declared 30s timeout becomes StoreWriteContention,
    not a silent hang. If this test fails, the Phase 11 pgvector conformance
    bar is unverified — surface per Rule 12."""
    # Squeeze the timeout to 0.05s for fast tests:
    monkeypatch.setattr("codegenie.rag.store._ADD_LOCK_TIMEOUT_SECONDS", 0.05)
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-block"))
    example = make_solved_example(id_="ex-002")

    # Manually take the lock — the next add() must time out:
    await store._add_lock.acquire()
    try:
        with pytest.raises(StoreWriteContention) as exc_info:
            await store.add(example, cap)
        assert exc_info.value.workflow_id == WorkflowId("wf-block")
    finally:
        store._add_lock.release()
    # Lock must be releasable — the timed-out add must not leak ownership:
    assert store._add_lock.locked() is False
    store.close()
```

Why it fails: `codegenie.rag.store` doesn't exist.

### Green — make it pass

Land the minimum: `_ADD_LOCK_TIMEOUT_SECONDS: Final[float] = 30.0` module constant, the Protocol declaration, `ChromaPersistentStore` with the four public methods (`query`, `add`, `digest`, `close`) **plus** the private `_query_with_embedding`, the timeout pattern from Implementation Outline §7. Use `asyncio.to_thread(collection.add, ...)` / `asyncio.to_thread(collection.query, ...)` to keep the event loop responsive.

### Refactor

- Hoist `_get_collection` + `_load_existing_record_ids` into clean helpers.
- Module docstring with the single-writer phrase verbatim.
- Add structured-log emissions (`store.add.acquired`, `store.add.completed`, `store.add.timeout`).

### Required follow-on tests

- `test_protocol_surface_frozen` (AC-9) — fence test; the exact four-name set, coroutine-ness, **and** `inspect.signature` of every method (the `capability` param on `add` is load-bearing).
- `test_empty_store_digest_is_blake3_of_empty` (AC-6) — a fresh store's `digest()` **equals** `_EMPTY_BLAKE3` (positive direction — catches a `digest()` that hashes something other than the empty roll).
- `test_digest_is_insertion_order_sensitive` (AC-6) — **two** stores; add the *same* two records `ex-A`, `ex-B` to store-1 and `ex-B`, `ex-A` to store-2; assert `store1.digest() != store2.digest()`. Then a third store with `ex-A`, `ex-B` (same order as store-1): `store3.digest() == store1.digest()`. Kills the "sort `_record_ids` before rolling" mutant (Notes §5) — a sorting impl makes all three digests equal.
- `test_query_empty_partition_returns_rag_miss` (AC-5) — `_query_with_embedding` against a never-populated partition → `RagMiss`, not a raise.
- `test_public_query_returns_rag_miss_without_vector` (AC-5) — the public `query(q)` returns `RagMiss` even after a matching record was added (it has no vector — by contract).
- `test_close_disables_subsequent_operations` (AC-7) — `pytest.raises(StoreClosed)` from `add` / `query` / `_query_with_embedding` after `close()`.
- `test_close_is_idempotent` (AC-7) — a second `close()` raises nothing.
- `test_digest_survives_close` (AC-7) — `digest()` after `close()` returns the same value it returned before `close()`; no `StoreClosed`.
- `test_partition_collections_are_independent` (AC-5b) — add a record under `(task_class="vuln_remediation", language="typescript", build_system="npm")`; a `_query_with_embedding` against `(task_class="distroless_migration", language="typescript", build_system="npm")` returns `RagMiss` (the record never leaks across the partition boundary).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/store.py` | `SolvedExampleStore` Protocol + `ChromaPersistentStore` + `SolvedExampleWriteCapability` marker. |
| `src/codegenie/rag/errors.py` | Extend with `StoreWriteContention`, `StoreCorrupted`, `StoreClosed`. |
| `tests/fixtures/rag/__init__.py` | New test-fixture package. |
| `tests/fixtures/rag/fake_solved_example.py` | `make_solved_example(...)` — builds a valid `SolvedExample` with sensible defaults, **including a valid `embedding_vector`** (a 384-element tuple of floats — see Validation note B; depends on the S1-04 amendment); single boundary lift of raw `str` → `SolvedExampleId` etc. `make_query_matching(example)` — builds a `Query` whose partition triple (`task_class`, `language`, `build_system`) matches a given `SolvedExample`, for the round-trip test. |
| `tests/unit/rag/test_store.py` | AC red test + follow-ons. |
| `tests/integration/test_phase4_store_contention_30s.py` | AC-8 (short contention test; S4-08 lands the full multi-coroutine test). |
| `tests/fence/test_solved_example_store_protocol_frozen.py` | AC-9. |

## Out of scope

- **YAML canonical write + manifest** — S4-04. This story writes to chromadb only; the YAML canonical+manifest layer composes on top of `add()`.
- **`RecordProvenance.verify` chain check** — S4-05. The `provenance` field on `SolvedExample` is persisted as metadata but not verified at query time here.
- **Two-threshold band classifier** — S5-02. This story's `query` returns `RagHit | RagMiss` only (no `RagDegraded`); the band classification composes on top.
- **`_phase4_local_capability_mint`** — S4-06. This story declares the capability type; S4-06 ships the mint + the import-linter contract pinning the mint surface.
- **`codegenie rag rebuild`** — S4-07.
- **The `asyncio.gather` two-coroutine test pinning monotonic chain-head** — S4-08 (depends on S4-04's chain head landing).
- **pgvector adapter** — Phase 11; the Protocol is the seam.

## Notes for the implementer

### §1 — Why YAML-canonical is NOT in this story

ADR-0016 commits to YAML as canonical and chromadb sqlite as derived. The atomic-write contract (write YAML first, then chromadb; if chromadb fails, the YAML record is still on disk for `rag rebuild`) lives in S4-04. **This story writes chromadb directly inside `add()` without the YAML side.** That is intentional: it lets the chromadb adapter ship + test in isolation; S4-04 then wraps `add()` to take the YAML-canonical path. Surface this clearly in the module docstring: `add()` will be **extended** by S4-04 to write YAML first; do not "improve" by anticipating S4-04 here.

### §2 — `chromadb` is sync; wrap in `asyncio.to_thread`

`chromadb`'s API is synchronous CPython code. Awaiting `collection.add(...)` directly would block the event loop. Wrap in `await asyncio.to_thread(collection.add, ...)` so the asyncio.Lock around the call is meaningful (the lock is async-aware; the wrapped call yields control while waiting on the thread pool). The Risks section of `High-level-impl.md §Step 4` calls this out explicitly — confirm via the spike (Implementation Outline §1).

### §3 — Single-writer is **declared** in the Protocol docstring, not just enforced

The phrase "single-writer constraint" must appear verbatim in `SolvedExampleStore`'s docstring (AC-9 grep-anchors on it). The reason: a future contributor who writes a second adapter (pgvector in Phase 11) must read the Protocol's contract and discover that **concurrent writes serialize at the adapter level**. If pgvector's adapter doesn't serialize, the contract is violated even though it could trivially support concurrent writes. The serialization is the Phase-4 conformance bar — the Protocol carries it forward.

### §4 — Two read methods: public `query` + private `_query_with_embedding` (resolved — option B)

The Protocol declares `query(q: Query, *, top_k, similarity_floor) -> RetrievalOutcome` but chromadb similarity search needs a **pre-embedded** vector, which a `Query` does not carry and which this store does not compute (no embedder is injected). Two options were considered:

- **(A)** Carry an internal embedder reference inside the store. Rejected — it pollutes the store/retriever boundary, means the store secretly does embedding work, and would force `add()` to embed too (contradicting ADR-0016's "records carry their vector; rebuild does not re-embed").
- **(B) — chosen.** A private `_query_with_embedding(q, query_embedding, *, top_k, similarity_floor)` method is the real read path; the public `query(q, ...)` keeps exactly the four-arg Protocol signature and returns `RagMiss` (it has no vector). S5-01's retriever embeds the `Query` and calls `_query_with_embedding` explicitly.

**Do not** add a `query_embedding` parameter to the *public* `query` — that would change the Protocol surface and break AC-9's four-method fence and signature pin. The vector flows through the *private* method only. AC-5 is the contract; AC-1 is the Protocol shape; they now agree.

**Surface the split in the module docstring.** A reviewer who reads the Protocol and wonders "where does the embedding happen?" deserves an inline answer: the retriever embeds; the store stores pre-computed vectors (`add`) and searches with a passed-in vector (`_query_with_embedding`).

### §5 — `digest()` is order-sensitive on purpose

The BLAKE3 roll over record IDs is order-sensitive (different insertion order → different digest). This is the **right contract** for S4-07's `rag rebuild` golden test — rebuilding from canonical YAML in the same insertion order produces the byte-identical digest. **Do not** sort the record IDs before rolling; sorting would hide insertion-order bugs that the rebuild test is designed to catch.

### §6 — `StoreWriteContention` is a Phase-4 event the orchestrator handles, not a workflow halt

When `add()` times out, the workflow does **not** fail outright (the patch shipped — that's the user-visible win). The harvester loses the compounding opportunity; emit `SolvedExampleIngestFailed(reason=write_contention)` from the caller (S4-06's writer surface) and continue. The exception is the in-process signal; the event log is the cross-process audit anchor.

### §7 — Per-collection partition naming

`task_class__language__build_system` (double-underscore separator) — chromadb collection names must be valid identifiers; underscores are safe. Avoid `:` or `/` (chromadb may reject; varies by version). Document the convention; future task classes (e.g., `"distroless_migration"`) just slot in.

### §8 — Don't speculatively add `update()` or `delete()`

The Protocol has four methods. A future story might want `delete()` for retraction; that's a Phase-11 ADR amendment when the merge-webhook ingest path lands. Adding it now is YAGNI and would break the four-method fence test (AC-9).

### §9 — Test posture for the contention test

S4-08 owns the full `asyncio.gather`-two-coroutines + monotonic-chain-head integration test. This story ships the **shorter** integration test that pins just the timeout behavior (manual lock acquisition + timeout assertion) — sufficient to catch a regression where someone changes `30.0` to `30` (still works) or removes the `try/finally` (lock leaks; the test catches via `locked()` assertion).

### §10 — `query`/`add` are `async`, deviating from the arch's illustrative code snippet (acknowledged)

Arch §Component 7 and final-design §7 print the `SolvedExampleStore` Protocol with **synchronous** `def query` / `def add`. This story ships them as **`async def`** and AC-9 pins them as coroutines. The async form is correct and is the resolved contract — arch §Concurrency (line 269) and HLI Step 4 both mandate a process-local `asyncio.Lock` around `add()`, `asyncio.Lock.acquire()` must be `await`ed, and the `asyncio.to_thread` wrapping of the sync chromadb calls requires an async caller. The arch's code snippet is illustrative drift (the sibling `Embedder` Protocol in S4-01 is genuinely sync because it has no lock). **Do not "fix" `query`/`add` back to sync `def`** — that would make the 30 s lock-contention contract (Gap 3, AC-8) unimplementable. This is a deliberate, surfaced deviation per Global Rule 7 (surface conflicts, don't average them).

### §11 — `digest()` cross-process determinism is deferred to S4-04's manifest

`digest()` rolls BLAKE3 over `self._record_ids` in insertion order (AC-6). Within a single live store, insertion order is the order of `add()` calls — deterministic. **Across a close/reopen it is not**, because `_load_existing_record_ids()` rebuilds `_record_ids` from chromadb, and `collection.get()` does not promise insertion order — and there is one collection per partition, so even a stable per-collection order would not give a global insertion order. The canonical insertion-order record is S4-04's `.codegenie/rag/manifest.yaml` (`{records: [...]}`, an ordered list per ADR-0016 §Consequences). S4-07's `rag rebuild` golden test — which needs a byte-identical `digest()` after a rebuild — depends on that manifest, not on chromadb's `get()` order. So in S4-03: state plainly in the `digest()` docstring that cross-process determinism arrives with S4-04; do **not** claim reopen-stability the implementation cannot deliver (Rule 12 — fail loud). `_load_existing_record_ids()` loads in chromadb's returned order as a best effort for the live `_record_ids` list.
