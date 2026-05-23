# Story S3-02 — `EventBatchWriter` — 20 ms / 256-event flush + `COPY ... BINARY`

**Step:** Step 3 — Canonical event log, BlobRef store, and activity-boundary sanitizer
**Status:** Ready
**Effort:** M
**Depends on:** S3-01 (`EventLog.append` + per-workflow chain semantics; `EventPayloadAdapter`; `EventLogWriteCapability`)
**ADRs honored:** ADR-0003 (chain semantics carried through the batch path), ADR-0006 (critical-event-aware flush trigger; sync dispatch is S3-03), ADR-0012 (Postgres canonical log topology), production ADR-0034

## Context

S3-01 ships single-row `INSERT` for `append`. That path is fine for sync flushes and tests but cannot hit the G6 target of ≥3k events/sec from 5 activity workers — every batched insert pays an RTT. This story ships the **batched COPY-binary path**: `EventBatchWriter` owns an `asyncio.Queue`, accumulates events, flushes on a 20 ms / 256-event boundary, and writes via `COPY events.events FROM STDIN BINARY` (Postgres-native bulk insert).

The batcher does NOT itself dispatch synchronous flushes — S3-03 layers `@critical_event` synchronous-flush dispatch on top. **This story** only ships the **flush-trigger awareness**: if any event in the buffer is `@critical_event`-marked, the batcher flushes immediately (regardless of the 20 ms / 256 threshold). The synchronous return-to-caller semantics that S3-03 needs (caller blocks until the row is durably committed) are NOT shipped here; S3-03 owns the bypass that skips the queue entirely for those variants.

The batched path must preserve the per-workflow BLAKE3 chain S3-01 ships. **This is the hardest part.** A naive batch insert that COPY-streams 256 rows in arbitrary order corrupts the chain (each row's `prev_hash` must equal the prior row's `row_hash` *for that workflow*). The batcher partitions the buffer by `workflow_id` at flush time, hashes each partition serially against the LRU-cached chain head, and emits the COPY stream in a deterministic order. Inter-workflow order does not matter for chain integrity; intra-workflow order is load-bearing.

Back-pressure: when the queue's payload bytes exceed 16 MiB (Postgres unavailable / slow), `append_batch` blocks the caller (`await queue.put(...)`-with-bound). Temporal retries the activity per `RetryPolicy`. This is the design choice ADR-0003's tradeoff table accepts.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C5 — Canonical event log` (the `EventBatchWriter` paragraph; flush triggers; `COPY events.events FROM STDIN BINARY`; back-pressure into Temporal).
  - `../phase-arch-design.md §Goals G6` (≥3k events/sec sustained; p95 ≤15 ms sync / ≤50 ms batched).
  - `../phase-arch-design.md §Implementation-level risks #3` (EventBatchWriter back-pressure interaction with Temporal activity retries).
- **Phase ADRs:**
  - `../ADRs/0003-per-workflow-blake3-prev-hash-chain.md` — chain is per-workflow; the batched path MUST preserve same-workflow serialization at flush time.
  - `../ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — `_CRITICAL_EVENTS` is read here ONLY as a flush trigger; full sync-bypass is S3-03.
- **Existing code:**
  - `src/codegenie/events/log.py` (S3-01) — the single-row `append` path this story sits beside.
  - `src/codegenie/events/payloads.py` (S1-02) — `_CRITICAL_EVENTS: Final[set[str]]` registry populated by `@critical_event`; `EventPayloadAdapter.dump_json` for canonical bytes.
  - `src/codegenie/durable/config.py` (S2-02) — `event_batch_size` (default 256), `event_batch_flush_interval_ms` (default 20).
- **External:**
  - `psycopg` 3.x async COPY: `https://www.psycopg.org/psycopg3/docs/basic/copy.html` — `async with cursor.copy("COPY ... FROM STDIN BINARY") as copy: await copy.write_row(...)`.
  - Postgres binary COPY format: `https://www.postgresql.org/docs/16/sql-copy.html#id-1.9.3.55.9.4` — schema-aware encoding of `UUID`, `BYTEA`, `JSONB`, `TIMESTAMPTZ`, `BIGINT`, `TEXT`.
  - `blake3` Python binding — same dependency as S3-01.

## Goal

Ship `EventBatchWriter` (private, owned by the worker bootstrap) and `EventLog.append_batch(events, *, capability) -> tuple[EventId, ...]` such that (a) appends ride an `asyncio.Queue`-backed buffer flushed on 20 ms OR 256 events OR `@critical_event` membership; (b) flush partitions by `workflow_id`, hashes each partition serially against the LRU chain head, COPY-streams the entire flush as one Postgres transaction; (c) back-pressure into the caller when the queue exceeds 16 MiB payload bytes; (d) the resulting chain is byte-identical to what S3-01's single-row path would have produced.

## Acceptance criteria

- [ ] **AC-1 — `EventBatchWriter` public surface.** `src/codegenie/events/log.py` (same module as S3-01) exports `class EventBatchWriter` with constructor `__init__(self, *, log: EventLog, batch_size: int = 256, flush_interval_ms: int = 20, max_buffer_bytes: int = 16 * 1024 * 1024) -> None`. Methods: `async def enqueue(self, event: EventPayload, *, capability: EventLogWriteCapability) -> EventId` (returns the pre-computed `event_id` immediately; flush is deferred); `async def flush(self) -> None` (drain & commit synchronously); `async def start(self) -> None` + `async def stop(self) -> None` (lifecycle for the background flush task).
- [ ] **AC-2 — `EventLog.append_batch` surface.** `EventLog` (extended from S3-01) gains `async def append_batch(self, events: Sequence[EventPayload], *, capability: EventLogWriteCapability) -> tuple[EventId, ...]`. Implementation: for each event, capability-check, compute canonical payload, then issue ONE `COPY events.events FROM STDIN BINARY` for the whole batch. The chain is computed serially per `workflow_id` against the LRU.
- [ ] **AC-3 — Flush triggers (three).** A flush happens when ANY of: (a) `len(buffer) >= batch_size`, (b) `time_since_last_flush_ms >= flush_interval_ms`, (c) `any(type(ev).__name__ in _CRITICAL_EVENTS for ev in buffer)`. Tests construct each trigger in isolation and assert the flush fires within ≤5 ms of the trigger condition.
- [ ] **AC-4 — Chain preservation across the batch.** Insert a sequence of 50 events for the same workflow via `append_batch`; read them back via direct SELECT; assert (a) `wf_seq = 1..50` dense, (b) for every `n > 1`, `row_hash[n] == BLAKE3(row_hash[n-1] || canonical_payload[n])`. This is the **canonical chain-preservation assertion**; if it ever drifts, the batcher is broken.
- [ ] **AC-5 — Cross-workflow parallelism, intra-workflow serialization.** A batch containing events from 3 workflows interleaved `(w1, w2, w1, w3, w2, w1, ...)` flushes correctly: each workflow's chain is independently consistent; the COPY stream order is "all w1's events in original arrival order, then all w2's in arrival order, then all w3's" (or any partition order — the point is intra-workflow order is preserved). Test asserts each workflow's `wf_seq` is dense + chain verifies; cross-workflow `wf_seq` interleavings are irrelevant.
- [ ] **AC-6 — `COPY ... BINARY` is the flush path.** Profile / inspect: a 256-event flush issues exactly ONE Postgres statement, of kind `COPY` (not `INSERT`). Test uses `pg_stat_statements` or `psycopg` connection logging to assert the executed statement begins with `COPY events.events`.
- [ ] **AC-7 — Pre-computed `event_id` returned to caller.** `enqueue` returns the `event_id` **before** the flush. The contract: `event.event_id` is set by the Pydantic factory at construction time (S1-02 owns this); the writer trusts it and returns it. Test asserts `enqueue(event, ...) == event.event_id` even when flush is deferred.
- [ ] **AC-8 — Back-pressure on > 16 MiB buffer.** Patch the pool to make COPY block indefinitely; enqueue events totalling > 16 MiB; assert the (16-MiB+1)-th enqueue call **blocks** (the `asyncio.Queue.put` is bounded and `await`s); release the COPY block; the queued events drain. Use `asyncio.wait_for(..., timeout=...)` to assert the block is real, not a busy spin.
- [ ] **AC-9 — Critical-event flush trigger does NOT bypass the queue.** A `MergeOutcome` event enqueued via `enqueue` rides the queue and causes immediate flush (AC-3); but `enqueue` returns immediately (not awaiting the flush). **S3-03** layers the sync-bypass that makes `MergeOutcome`-emitting activities block until durable. Test asserts: enqueue 1 batched event, then 1 critical event, then 1 batched event; the next flush includes ALL THREE (queue order preserved); no events are dropped or reordered.
- [ ] **AC-10 — Lifecycle: `start()` / `stop()`.** `start()` launches an internal `asyncio.Task` that wakes every `flush_interval_ms` and calls `flush()` if the buffer is non-empty. `stop()` cancels the task, drains the remaining buffer (synchronous final flush), and returns when committed. Test asserts post-`stop()`, the buffer is empty and all enqueued events landed in Postgres.
- [ ] **AC-11 — Atomic batch: failure aborts the whole batch.** A simulated `psycopg.OperationalError` mid-COPY (patch `copy.write_row` to raise on the 100th row of a 200-row flush) leaves ZERO rows in `events.events` (the COPY transaction rolls back) AND leaves the LRU chain-head **unchanged** (no partial chain progress). Failed-batch events are re-queued and the next flush succeeds with `wf_seq` starting where the failed batch would have started.
- [ ] **AC-12 — Throughput sanity (NOT G6 — that's S3-07).** Integration test: 10 concurrent workflows × 100 events each (1000 events total) via `append_batch` commits in < 50 ms p95 wall-clock (per the High-level-impl Step 3 done-criterion). This is a sanity floor, not the formal G6 assertion (S3-07 owns ≥3k events/sec).
- [ ] **AC-13 — `mypy --strict` + cold-start fence.** `mypy --strict` clean on the extended `log.py`; `import codegenie.events.log` does not start the background flush task (start is explicit); per-submodule cold-start fence stays green.

## Implementation outline

1. **Write the red test for AC-4 first** (chain preservation across batch). This is the load-bearing invariant; if you implement everything else and this fails, the batcher is structurally wrong.
2. **`EventBatchWriter` skeleton.**
    - `self._queue: asyncio.Queue[tuple[EventPayload, EventLogWriteCapability]]` (bounded by `max_buffer_bytes` via a custom `Queue` subclass that tracks payload bytes — `asyncio.Queue` is item-count-bounded, not byte-bounded, so wrap it).
    - `self._buffer_bytes: int = 0` counter.
    - `self._flush_task: asyncio.Task | None = None`.
    - `self._last_flush_at: float = 0.0` (use `loop.time()`, which is monotonic; `workflow.now()` is not relevant here — this is activity-side code).
3. **`enqueue` flow:**
    - Capability-check (raise `EventCapabilityViolation` immediately, do not buffer).
    - Compute `payload_bytes = EventPayloadAdapter.dump_json(event)` (do it once; cache on a tuple).
    - If `self._buffer_bytes + len(payload_bytes) > max_buffer_bytes`: `await self._queue.put_with_backpressure(...)` blocks until capacity.
    - Otherwise enqueue; check the three flush triggers (size, age, critical-event); if any fire, call `self._maybe_flush()` (non-blocking — it schedules the flush task to run).
    - Return `event.event_id`.
4. **`flush` flow:**
    - Drain the queue under `asyncio.Lock` (one flush at a time per writer).
    - Partition by `workflow_id`: `partitions: dict[WorkflowId | None, list[tuple[EventPayload, bytes]]] = ...`.
    - For each partition with non-None `workflow_id`: look up the chain head in `self._log._chain_heads` (LRU shared with S3-01); on miss, SELECT chain tail. Hash each event serially: `row_hash[n] = BLAKE3((prev_row_hash or b"") + canonical_payload[n])`.
    - For the portfolio partition (`workflow_id is None`): each event hashed independently (`row_hash = BLAKE3(canonical_payload)`).
    - Open one transaction; `cursor.copy("COPY events.events (event_id, workflow_id, kind, timestamp, correlation_id, payload, prev_hash, row_hash, wf_seq) FROM STDIN BINARY") as copy`.
    - **`wf_seq` allocation**: read `MAX(wf_seq)` per workflow_id **once** at flush start (within the transaction); increment in Python for each event in the partition; write to the COPY stream. The `events_wf_seq_uniq` UNIQUE INDEX is the integrity backstop if two workers race for the same workflow (unlikely under Temporal sticky-task affinity but the fence is real).
    - Commit. Update `self._log._chain_heads` with the new `(row_hash, wf_seq)` for each touched workflow.
    - On any exception, **roll back the transaction AND do not update the LRU** (AC-11). Re-queue the failed-batch events for the next flush (in original order).
5. **`start` / `stop`:**
    - `start`: spawn `self._flush_task = asyncio.create_task(self._flush_loop())`.
    - `_flush_loop`: `while not cancelled: await asyncio.sleep(flush_interval_ms / 1000); if buffer non-empty: await self.flush()`.
    - `stop`: `self._flush_task.cancel()`; `await asyncio.shield(self.flush())` (final drain); await task completion.
6. **COPY-binary encoding.** psycopg's `copy.write_row((event_id_uuid, workflow_id_or_None, kind_str, ts_dt, corr_or_None, payload_jsonb_bytes, prev_hash_bytes_or_None, row_hash_bytes, wf_seq_int_or_None))` handles the binary format. **Use `Jsonb` adapter** for the `payload` column — psycopg's `Jsonb(json_str_or_bytes)` wraps a JSON value for COPY.
7. **Bounded `Queue` wrapper** for byte-budget back-pressure — write a small `_ByteBoundedQueue` subclass that tracks `bytes_in_flight` and exposes `await put_with_backpressure(item, item_bytes)`. Test it in isolation (AC-8 covers integration).

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/integration/events/test_event_batch_writer_chain.py`

Test intent: A 50-event batch for one workflow, flushed in one COPY, must produce a chain byte-identical to what 50 single-row `append` calls would have produced (S3-01's chain semantics).

```python
# Test outline only.
async def test_batch_preserves_per_workflow_chain(pg_pool, fresh_events_schema):
    """AC-4 — the batched COPY path produces the same chain S3-01's
    single-row INSERT path produces. If this fails, the batcher is
    structurally wrong — every other AC is moot."""
    log = EventLog(pool=pg_pool)
    writer = EventBatchWriter(log=log)
    await writer.start()

    wf = WorkflowId("wf-test-01")
    cap = _full_capability_for("system")
    events = [_make_event(workflow_id=wf, kind="route_decided") for _ in range(50)]

    for ev in events:
        await writer.enqueue(ev, capability=cap)
    await writer.flush()
    await writer.stop()

    rows = await _fetch_workflow_rows(pg_pool, wf)
    assert [r.wf_seq for r in rows] == list(range(1, 51))

    prev = b""
    for n, row in enumerate(rows):
        expected = blake3(prev + EventPayloadAdapter.dump_json(events[n])).digest()
        assert row.row_hash == expected, f"chain break at wf_seq={row.wf_seq}"
        prev = row.row_hash
```

Why it fails: `EventBatchWriter` doesn't exist yet — `ImportError`.

### Green — minimal pass

- Add `EventBatchWriter` with `enqueue` / `flush` / `start` / `stop`.
- `flush` partitions by `workflow_id`, hashes serially, COPY-streams.
- The red test passes; the chain matches S3-01's formula.

### Required follow-on tests (one per AC)

- **`test_flush_triggers_on_size`** (AC-3a) — enqueue 256 events; assert flush fires.
- **`test_flush_triggers_on_age`** (AC-3b) — enqueue 1 event; sleep 25 ms; assert flush fires.
- **`test_flush_triggers_on_critical_event`** (AC-3c) — enqueue 1 non-critical, then 1 `MergeOutcome`; assert flush fires immediately on the second.
- **`test_cross_workflow_interleaving`** (AC-5) — interleave 3 workflows × 10 events; assert each workflow's chain is consistent.
- **`test_flush_uses_copy_binary`** (AC-6) — patch the psycopg cursor to record statement kinds; assert exactly one `COPY` per flush.
- **`test_enqueue_returns_event_id_pre_flush`** (AC-7) — `assert (await writer.enqueue(ev, ...)) == ev.event_id` without explicit flush.
- **`test_backpressure_blocks_at_16mib`** (AC-8) — patch COPY to block; enqueue 17 MiB worth; assert the next enqueue `await` blocks (use `asyncio.wait_for(..., timeout=0.1)` and expect `TimeoutError`).
- **`test_critical_event_does_not_bypass_queue`** (AC-9) — three enqueues (batched, critical, batched); next flush contains all three in original order. **NOTE for implementer:** S3-03 will add a true sync-bypass; this test asserts S3-02's *queue* behavior, not S3-03's bypass.
- **`test_stop_drains_remaining_buffer`** (AC-10) — enqueue 5; stop; assert all 5 landed.
- **`test_failed_batch_rolls_back_and_keeps_lru_unchanged`** (AC-11) — patch `copy.write_row` to raise on the 100th of 200; assert table row count = 0 AND chain-head LRU unchanged (compare before/after via direct inspection of `log._chain_heads`).
- **`test_1k_events_under_50ms_p95`** (AC-12) — 10 workflows × 100 events; 5 runs; assert p95 wall-clock < 50 ms. NOT the formal G6 bench (S3-07).

### Property test (Hypothesis)

`tests/property/test_batch_writer_chain_invariance.py` — Hypothesis strategy generates a sequence of `(workflow_id, event)` pairs of length 10-100 across 1-5 distinct workflows; the test enqueues + flushes via `EventBatchWriter`, reads back, and asserts every workflow's chain verifies. This is the canonical "batching doesn't corrupt chains" property; a single example test can be mutated past by a wrong partition order, but the property test cannot.

### Refactor

- Extract `_ByteBoundedQueue` into a private class with its own focused unit tests; do not subclass `asyncio.Queue` (composition over inheritance — psycopg's async patterns prefer composition).
- Module docstring on `log.py` adds a "Batched path" section citing ADR-0006 (flush triggers) and ADR-0003 (chain preservation).
- The chain-computation helper extracted in S3-01 (`_canonical_payload_bytes`) is reused; this story does NOT redefine it.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/events/log.py` | Extend with `EventBatchWriter`, `append_batch`, internal `_ByteBoundedQueue`. |
| `src/codegenie/events/errors.py` | Add `BatchFlushFailed` if a typed exception is useful for back-pressure surfacing. |
| `tests/integration/events/test_event_batch_writer_chain.py` | Red test + chain-preservation integration tests. |
| `tests/integration/events/test_event_batch_writer_lifecycle.py` | `start` / `stop` / drain / back-pressure tests. |
| `tests/integration/events/test_event_batch_writer_triggers.py` | Three flush-trigger tests. |
| `tests/property/test_batch_writer_chain_invariance.py` | Hypothesis property. |
| `tests/unit/events/test_byte_bounded_queue.py` | Focused unit tests for the private bounded queue. |

## Out of scope

- **Synchronous-flush bypass for `@critical_event`** — handled by S3-03. This story uses `_CRITICAL_EVENTS` membership as a flush *trigger* only; the caller-blocks-until-durable semantics ship in S3-03.
- **`read_workflow` + chain-verify** — handled by S3-04.
- **`BlobRef`** — handled by S3-05.
- **Sanitizer** — handled by S3-06.
- **Formal G6 throughput bench** — handled by S3-07. AC-12 here is a sanity floor.
- **Cross-worker contention on the same workflow's stream** — out of scope for Phase 9. Temporal sticky-task affinity routes a workflow's activities to one worker; cross-worker writes for the same workflow happen only under failover, where the chain-tail re-read (S3-01) is the correctness mechanism.
- **OTel tracing of flush latency** — Phase 13 lands OTel; here, structured logs at flush-start/end with `len(buffer)`, `bytes`, `wall_clock_ms` are sufficient observability.
- **Adaptive batch sizing** — not adopted. The `(batch_size=256, flush_interval_ms=20)` defaults are a guess validated by S3-07's bench; adjustment is a phase-3 config tune, not a Phase-9 feature.

## Notes for the implementer

### §1 — Chain integrity is the load-bearing invariant

Every refactor here must preserve the per-workflow chain. The AC-4 test + the Hypothesis property test are the canonical "the batcher didn't corrupt the chain" assertions. If either fails, stop and re-derive the partitioning + serial-hash logic — do not paper over with a special case.

### §2 — `wf_seq` allocation under COPY

Unlike S3-01's single-row INSERT (which uses a sub-select `RETURNING wf_seq`), COPY cannot embed sub-selects. The batcher must allocate `wf_seq` client-side. The approach:

1. At flush start, for each partition, issue one `SELECT COALESCE(MAX(wf_seq), 0) FROM events.events WHERE workflow_id = $1` **inside the same transaction as the COPY**.
2. Increment client-side; write to the COPY stream.
3. The `events_wf_seq_uniq` UNIQUE INDEX is the integrity backstop — if two workers race for the same workflow's stream (rare; Temporal sticky-task affinity prevents this nominally), one transaction commits and the other rolls back; the loser re-queues its events.

The transaction isolation level (READ COMMITTED, the Postgres default) is sufficient: within the transaction, the SELECT + COPY see a consistent snapshot of `events.events`; commit either succeeds or fails atomically.

### §3 — Back-pressure surfaces as Temporal activity retry

When the queue blocks (AC-8), the activity caller's `await emit_event(...)` blocks. After Temporal's activity heartbeat timeout (30 s for activity workers per `phase-arch-design.md §C8`), Temporal marks the activity as failed and retries per the `RetryPolicy`. The bench in Step 8 (S8-04) includes a fault-injection scenario for this; this story does NOT need to simulate the Temporal retry — just the bounded `await put`.

### §4 — `psycopg` COPY-binary is a foot-gun

The binary COPY format is schema-position-sensitive — the columns in the `COPY events.events (event_id, workflow_id, kind, timestamp, correlation_id, payload, prev_hash, row_hash, wf_seq)` clause MUST match the order of the tuple passed to `copy.write_row`. **Pin the column list explicitly** in the COPY statement; do not rely on the table's column-definition order (S2-04's snapshot fence would catch a schema-change drift, but better to be loud).

`psycopg.types.json.Jsonb(payload_bytes)` is the canonical wrapper for the `payload JSONB` column. Do NOT pass raw `bytes` — psycopg would try to encode as `BYTEA`.

### §5 — Critical-event flush trigger is one `set` lookup

`type(event).__name__ in _CRITICAL_EVENTS` (the registry from S1-03 / ADR-0006) is O(1). Check at enqueue time, not at flush time, to ensure the flush *trigger* fires immediately. The set is `Final` after import — no race conditions to worry about.

### §6 — `_chain_heads` is shared with `EventLog` from S3-01

The LRU lives on `EventLog`, not `EventBatchWriter`. The batcher mutates `log._chain_heads` after a successful flush. Wrap the mutation in a brief `asyncio.Lock` to prevent a concurrent single-row `append` from S3-01 reading a stale head mid-flush. The lock is per-`EventLog`-instance; contention is minimal because most appends go through the batcher anyway.

### §7 — Failed-batch re-queue is in original order

AC-11 specifies that a failed batch re-queues its events for the next flush. Preserve original enqueue order — the chain hash relies on it. The simplest implementation: collect the drained batch into a list before COPY; on exception, re-enqueue the list to the front of the buffer (use a deque-backed buffer if you go this route, or maintain a `_pending_retry: list` that prepends to the next `flush()`'s drain).

### §8 — Not adopted (YAGNI)

- **A separate writer per task queue** — not adopted. One `EventBatchWriter` per worker process is sufficient at G6 throughput. If a future phase shows queue contention, a per-task-queue writer is an additive refactor (the writer is owned by the worker bootstrap, S6-01).
- **Compression of the COPY stream** — not adopted. Postgres's wire protocol does compression; the COPY payload is bytes the server inflates. Premature optimization.
- **Async-queue persistence (event durability before flush)** — not adopted. The contract is "Temporal at-least-once + idempotent activities means a flush failure causes a retry that re-emits the same events with the same `event_id` (S1-02's UUID factory is deterministic per attempt? — no, it's random; idempotence at the *write* layer relies on `event_id` being the PRIMARY KEY and `ON CONFLICT DO NOTHING` on re-emit. **Check this with the schema: S2-03's `events.events` does NOT include `ON CONFLICT DO NOTHING` in its INSERT — re-emitting the same `event_id` would raise a unique-violation.** Resolution path: the batcher's INSERT/COPY does NOT include `ON CONFLICT`; if Temporal retries an activity and the activity re-emits the same event, the duplicate insert fails loud — and the activity's `RetryPolicy.non_retryable` catches `UniqueViolation` so the workflow does not loop. Document this in the module docstring. **If S4-02 / S4-05 deem this brittle, an `ON CONFLICT DO NOTHING` clause can be added additively to the COPY's INSERT-from-staging-table fallback path — but the staging fallback is not in scope here.**).
