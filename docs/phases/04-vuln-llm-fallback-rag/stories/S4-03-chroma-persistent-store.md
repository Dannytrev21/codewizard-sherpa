# Story S4-03 — `SolvedExampleStore` Protocol + `ChromaPersistentStore` + asyncio.Lock with 30s timeout

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** Ready
**Effort:** L
**Depends on:** S1-04 (`SolvedExample`, `Query`, `RetrievalOutcome`, `RecordProvenance` Pydantic models; `SolvedExampleId`, `StoreDigest`, `Similarity` Newtypes), S1-05 (path-scoped fence admits `chromadb` only under `src/codegenie/rag/`)
**ADRs honored:** ADR-0016 (chromadb PersistentClient embedded; YAML canonical; sqlite derived; single-writer constraint declared in Protocol + enforced by `asyncio.Lock`; per-(task_class, language, build_system) collection), Gap 3 (lock-contention contract: 30s `await`, then raise `StoreWriteContention`)

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
    - `def close(self) -> None` — synchronous; releases the chromadb client + closes the asyncio lock state.
    Module docstring states the **single-writer constraint** verbatim per ADR-0016 §Decision (and AC-9's fence test grep-anchors on the phrase "single-writer constraint").
- [ ] **AC-2 — `SolvedExampleWriteCapability` marker shape.** `src/codegenie/rag/store.py` exports `SolvedExampleWriteCapability` as a `@final` frozen dataclass with one field: `workflow_id: WorkflowId`. The class has no public constructor in user-visible surface — S4-06 ships the `_phase4_local_capability_mint` factory; this story only declares the type. Tests in this story construct it via direct call inside the test module (boundary lift acknowledged with `# AC-2-test-only-direct-construction` comment near the construction site).
- [ ] **AC-3 — `ChromaPersistentStore.__init__` opens chromadb embedded mode.** `ChromaPersistentStore(root_dir: Path)`:
    - Calls `chromadb.PersistentClient(path=str(root_dir / "chroma"))` exactly once; caches the client on `self._client`.
    - Resolves collection-per-partition lazily: `_get_collection(task_class, language, build_system) -> chromadb.Collection` uses `client.get_or_create_collection(name=f"{task_class}__{language}__{build_system}")`.
    - Creates a single asyncio lock on `self._add_lock = asyncio.Lock()`.
    - Initializes `self._record_ids: list[SolvedExampleId] = []` in insertion order, populated by reading existing collections on init (call `_load_existing_record_ids()`; if no collections exist yet, list is empty).
- [ ] **AC-4 — `add()` writes to the partition collection and appends to record_ids.** `await store.add(example, capability)`:
    - Acquires `self._add_lock` with a `30.0` second timeout via `asyncio.wait_for(self._add_lock.acquire(), timeout=30.0)`. Timeout → raise `StoreWriteContention(workflow_id=capability.workflow_id)`. Lock released in `finally`.
    - Resolves `collection = self._get_collection(example.task_class, example.language, example.build_system)`.
    - Calls `collection.add(ids=[example.id], embeddings=[list(example.embedding_vector)], metadatas=[<metadata>], documents=[<doc_text>])` where `<doc_text>` is `Query`-shaped key text (`failure_mode`, `cve_id`, `affected_package`) — the same text the retriever embeds at query time.
    - chromadb `add` is **sync** (verify in practice); to honor "don't block the event loop", wrap in `await asyncio.to_thread(collection.add, ...)` per Risks section of `High-level-impl.md §Step 4`.
    - Appends `example.id` to `self._record_ids`.
    - Returns `example.id`.
- [ ] **AC-5 — `query()` returns `RetrievalOutcome` over the matching partition only.** `await store.query(q, top_k=5)`:
    - Resolves the partition collection from `q.task_class, q.language, q.build_system`. If the collection doesn't exist (no records ever added for that partition) → returns `RagMiss` immediately (per arch §Component 9 "Returns `RagMiss` rather than raising when the store is empty").
    - Embeds NOTHING — chromadb queries take a pre-embedded `query_embeddings` array; the retriever (S5-01) does the embedding and passes the vector. This story's Protocol takes a **`Query`** but the chromadb-specific embedding is the retriever's responsibility; in S4-03 we *temporarily* internally embed by accepting an optional `query_embedding: EmbeddingVector | None` kwarg with the documented contract: "if `None`, the retriever has not yet been wired — `RagMiss` is returned." (See Notes §4 for the cleanup path.)
    - Returns `RagHit(few_shot=record, score=Similarity(top_score))` if top result above `similarity_floor` (when provided); else `RagMiss`. **NO band classification here** — the two-threshold band is S5-02; this story's `query` returns the raw scored top-k record and a `RagHit/RagMiss` projection wired to `similarity_floor` only.
- [ ] **AC-6 — `digest()` is BLAKE3-rolled over the current record-id list.** `digest()`:
    - `h = blake3.blake3()`; for each `id in self._record_ids` (in insertion order): `h.update(id.encode("utf-8"))`.
    - Returns `StoreDigest(h.hexdigest())`.
    - Empty store → returns `StoreDigest(blake3.blake3().hexdigest())` (the BLAKE3 of empty bytes — deterministic).
    - Two stores that received the **same records in the same order** return identical digests; one store receiving records in a different order returns a different digest. Order is the contract.
- [ ] **AC-7 — `close()` releases the client + lock state.** After `store.close()`:
    - `self._client = None`.
    - Subsequent `query` / `add` calls raise `StoreClosed` (typed exception in `codegenie.rag.errors`).
- [ ] **AC-8 — `StoreWriteContention` integration test (the load-bearing pin).** `tests/integration/test_phase4_store_contention_30s.py` (the SHORT version of S4-08's `harvest_contention` test — the full multi-coroutine `asyncio.gather` version lives in S4-08):
    - Acquire `store._add_lock` manually in the test (`await store._add_lock.acquire()`), then call `await store.add(example, capability)` with a **patched** `asyncio.wait_for` that fast-forwards (mock the timeout to ~0.1s for test speed — or use `freezegun` / a `monkeypatch` of the timeout constant to 0.1).
    - Assert `StoreWriteContention` raised with `exc.workflow_id == capability.workflow_id`.
    - Assert `self._add_lock.locked()` is `False` after the raise (the `finally` released the never-acquired lock — verify the try/except guards the `wait_for(acquire())` correctly; this is a known subtle pattern).
- [ ] **AC-9 — `SolvedExampleStore` Protocol fence test.** `tests/fence/test_solved_example_store_protocol_frozen.py` asserts:
    - `{n for n in dir(SolvedExampleStore) if not n.startswith("_")} == {"query", "add", "digest", "close"}`.
    - `inspect.iscoroutinefunction(SolvedExampleStore.query)` is `True`; same for `add`.
    - `inspect.isfunction(SolvedExampleStore.digest)` AND not coroutine; same for `close`.
    - Module docstring of `store.py` contains the literal substring `"single-writer constraint"` (the load-bearing ADR-0016 framing).
- [ ] **AC-10 — Path-scoped fence still green.** `tests/fence/test_pyproject_fence_phase4.py` passes; `chromadb` imported only inside `src/codegenie/rag/store.py`.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean.

## Implementation outline

1. **Spike first** (Risks line 140 of High-level-impl.md): a one-page script that creates a `chromadb.PersistentClient`, opens a collection, calls `add` from two `asyncio.gather`-launched coroutines under `asyncio.to_thread`, confirms no deadlock and the asyncio.Lock works correctly. **If chromadb itself blocks the loop** (it's CPython sync code under the hood), the `asyncio.to_thread` wrapping is the correct shape — confirm via the spike before proceeding. **Throw the spike away** before opening the PR; it lives as a comment in the module docstring naming the verified posture.
2. **`errors.py` additions** — `StoreWriteContention(Exception)` with `workflow_id: WorkflowId` typed attribute; `StoreCorrupted(Exception)`; `StoreClosed(Exception)`. All three referenced by arch §Component 7 §Failure behavior.
3. **`store.py` skeleton** — `from __future__ import annotations`; module docstring naming ADR-0016, the single-writer constraint, the Phase-11 pgvector swap precondition.
4. **`SolvedExampleWriteCapability`** — `@final` frozen dataclass with `workflow_id: WorkflowId`. No constructor magic. Docstring says "minted by `_phase4_local_capability_mint` in S4-06; do not construct directly outside the mint module."
5. **`SolvedExampleStore` Protocol** — `@runtime_checkable`; four-method surface per AC-1. Method docstrings encode the contract (idempotency, error shapes, return invariants).
6. **`ChromaPersistentStore` class**:
   - `__init__(self, root_dir: Path)`.
   - `_get_collection(task_class, language, build_system) -> chromadb.Collection`.
   - `_load_existing_record_ids()`.
   - `add(self, example, capability)`: lock + `asyncio.to_thread(collection.add, ...)` + record_ids append.
   - `query(self, q, *, top_k, similarity_floor, query_embedding=None)`: partition lookup + `asyncio.to_thread(collection.query, ...)` if `query_embedding` provided; else `RagMiss`.
   - `digest()`: rolled BLAKE3.
   - `close()`.
7. **30s timeout pattern (subtle):**
   ```python
   acquired = False
   try:
       await asyncio.wait_for(self._add_lock.acquire(), timeout=30.0)
       acquired = True
       # ... do work
   except asyncio.TimeoutError as e:
       raise StoreWriteContention(workflow_id=capability.workflow_id) from e
   finally:
       if acquired:
           self._add_lock.release()
   ```
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
from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleStore,
    SolvedExampleWriteCapability,
)
from codegenie.types.identifiers import (
    SolvedExampleId,
    StoreDigest,
    WorkflowId,
)
# Test fixture for SolvedExample construction (S1-04 ships the model):
from tests.fixtures.rag.fake_solved_example import make_solved_example


@pytest.mark.asyncio
async def test_add_then_query_returns_rag_hit(tmp_path: Path) -> None:
    """ADR-0016 §Decision: chromadb is the queryable derived index.
    Catches "add never writes" and "query always returns RagMiss" mutants."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-001"))
    example = make_solved_example(
        id_="ex-001",
        task_class="vuln_remediation",
        language="typescript",
        build_system="npm",
        cve_id="CVE-2026-1234",
    )
    sid = await store.add(example, cap)
    assert sid == SolvedExampleId("ex-001")

    # Empty digest is BLAKE3 of nothing; after one add it must differ.
    assert store.digest() != StoreDigest(
        "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
        # ^ BLAKE3 of empty input
    )
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

Land the minimum: `_ADD_LOCK_TIMEOUT_SECONDS: Final[float] = 30.0` module constant, the Protocol declaration, `ChromaPersistentStore` with the three methods, the timeout pattern from Implementation Outline §7. Use `asyncio.to_thread(collection.add, ...)` to keep the event loop responsive.

### Refactor

- Hoist `_get_collection` + `_load_existing_record_ids` into clean helpers.
- Module docstring with the single-writer phrase verbatim.
- Add structured-log emissions (`store.add.acquired`, `store.add.completed`, `store.add.timeout`).

### Required follow-on tests

- `test_protocol_surface_frozen` (AC-9) — fence test.
- `test_digest_changes_on_add` (AC-6) — empty digest != after-add digest; same records added in different order produce different digests.
- `test_query_empty_partition_returns_rag_miss` (AC-5).
- `test_close_disables_subsequent_operations` (AC-7) — `pytest.raises(StoreClosed)` after `close()`.
- `test_partition_collections_are_independent` — adding an example with `(task_class="vuln_remediation", language="ts", build_system="npm")` doesn't appear when querying `(task_class="distroless_migration", ...)`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/store.py` | `SolvedExampleStore` Protocol + `ChromaPersistentStore` + `SolvedExampleWriteCapability` marker. |
| `src/codegenie/rag/errors.py` | Extend with `StoreWriteContention`, `StoreCorrupted`, `StoreClosed`. |
| `tests/fixtures/rag/__init__.py` | New test-fixture package. |
| `tests/fixtures/rag/fake_solved_example.py` | `make_solved_example(...)` helper — builds a valid `SolvedExample` with sensible defaults; single boundary lift of raw `str` → `SolvedExampleId` etc. |
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

### §4 — The temporary `query_embedding=None` kwarg

The Protocol declares `query(q: Query, *, top_k, similarity_floor) -> RetrievalOutcome` but the `ChromaPersistentStore.query` impl needs the **pre-embedded** vector that the retriever (S5-01) will compute. Two clean options:

- **(A)** Carry an internal embedder reference inside the store. Pollutes the store/retriever boundary and means the store secretly does embedding work.
- **(B)** Add a private `_query_with_embedding(q, vec, top_k, similarity_floor)` method that the retriever calls; the public `query(q, ...)` method either raises (the retriever's job) or returns `RagMiss`.

Option (B) is the cleaner shape; the public `query` is the Protocol commitment, and the private `_query_with_embedding` is the in-house bypass. The story's AC-5 keeps the public method's behavior on the `query_embedding=None` path (return `RagMiss`) so the Protocol surface is honest about what it does without a vector. S5-01 will call the private method explicitly.

**Surface the trade-off in the module docstring.** A reviewer who reads the Protocol and wonders "where does the embedding happen?" deserves an inline answer.

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
