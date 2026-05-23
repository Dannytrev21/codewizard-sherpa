# Story S3-01 — `EventLog.append` + per-workflow BLAKE3 chain head

**Step:** Step 3 — Canonical event log, BlobRef store, and activity-boundary sanitizer
**Status:** Ready
**Effort:** M
**Depends on:** S1-02 (`EventPayload` 21-variant union + `EventPayloadAdapter`), S2-03 (alembic `events.events` table + append-only trigger + `application_role` grants)
**ADRs honored:** ADR-0003 (per-workflow BLAKE3 chain — load-bearing), ADR-0012 (event-store topology), ADR-0006 (`@critical_event` decoration is read here — sync vs batched lands in S3-02/S3-03), production ADR-0034

## Context

This story ships the **first writer** against the `events.events` table — `EventLog.append(event, *, capability)` — and the per-workflow BLAKE3 chain semantics ADR-0003 names. The chain is **per `workflow_id`, not global**: each workflow's events form their own hash chain whose head lives in an in-memory LRU (max 200 in-flight workflows per worker process); a cold restart re-reads the chain tail from Postgres on the first append for each workflow. The global-chain alternative was rejected because it serializes every portfolio-wide append through one chain-head — kills G6's ≥3k events/sec target dead.

S3-01 ships the **single-event** path only. Batching, COPY-binary fast path, and the `@critical_event` synchronous-flush bypass land in S3-02 / S3-03. The chain semantics, the LRU, the chain-tail re-read on miss, and the canonical-payload bytes-for-bytes deterministic hash input ship here because S3-02's batcher depends on them.

`EventLogWriteCapability` ships in this story (it lives at `src/codegenie/durable/capabilities.py` — declared in S1-06's Protocol-only file; this story adds the concrete Pydantic record + `allowed_kinds` enforcement). Tests assert an `append` call whose `event.kind` is outside `capability.allowed_kinds` raises a typed error before any Postgres write.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C5 — Canonical event log` (the public interface block; the per-workflow chain-head LRU; the `events_wf_seq_uniq` index that detects double-recording).
  - `../phase-arch-design.md §Data model — Postgres schema` (`events.events` columns + index list; `prev_hash BYTEA NULL`, `row_hash BYTEA NOT NULL`, `wf_seq BIGINT NULL`).
  - `../phase-arch-design.md §Data model — Capability types` (`EventLogWriteCapability` shape).
  - `../phase-arch-design.md §Edge case 8` (chain-tamper detection path — emitted in S3-04 on read; this story writes the chain that S3-04 verifies).
- **Phase ADRs:**
  - `../ADRs/0003-per-workflow-blake3-prev-hash-chain.md` — **load-bearing for this story.** Partitioned hash chain; chain-head per `workflow_id`; cold-restart re-reads tail; portfolio events (`workflow_id = NULL`) are NOT chained.
  - `../ADRs/0012-event-store-topology-temporal-history-plus-postgres-events.md` — canonical log is Postgres; Temporal history is operational ledger.
  - `../ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — `_CRITICAL_EVENTS` is read here only to keep the append signature flexible enough for S3-02/S3-03; sync-flush dispatch is deferred.
- **Existing code (precedent + dependency):**
  - `src/codegenie/events/payloads.py` (S1-02 output) — `EventPayloadAdapter.dump_json(event)` produces the **canonical payload bytes**; the hash input is `prev_row_hash || canonical_payload` exactly as ADR-0003 specifies.
  - `src/codegenie/events/alembic/versions/0001_create_events_schema.py` (S2-03) — the schema this writer targets.
  - `src/codegenie/durable/config.py` (S2-02) — `DurableSettings` + `AsyncConnectionPool` factory.
  - `src/codegenie/types/identifiers.py` (S1-01) — `WorkflowId`, `EventId`, `WorkflowSeq`, `BlobDigest`.
- **External:**
  - `blake3` Python binding — `https://github.com/oconnor663/blake3-py`.
  - `psycopg` 3.x async — `await conn.execute("INSERT ... RETURNING wf_seq", ...)`.
  - BLAKE3 spec — `https://github.com/BLAKE3-team/BLAKE3-specs`.

## Goal

Ship `EventLog.append(event, *, capability) -> EventId` that (a) rejects events whose `kind` is outside `capability.allowed_kinds` before touching Postgres, (b) computes `row_hash = BLAKE3(prev_row_hash || canonical_payload)` using a per-workflow chain-head LRU (max 200), (c) re-reads the chain tail from Postgres on LRU miss, (d) inserts via `INSERT ... RETURNING wf_seq` so the server allocates the per-workflow monotonic counter, (e) updates the LRU with the new `row_hash`, (f) leaves portfolio events (`workflow_id IS NULL`) unchained (`prev_hash = NULL`, `wf_seq = NULL`, `row_hash = BLAKE3(canonical_payload)`).

## Acceptance criteria

- [ ] **AC-1 — `EventLog` public surface.** `src/codegenie/events/log.py` exports a class `EventLog` whose constructor signature is `__init__(self, *, pool: AsyncConnectionPool, chain_lru_max: int = 200) -> None` and which exposes `async def append(self, event: EventPayload, *, capability: EventLogWriteCapability) -> EventId`. No other public methods in this story (`append_batch` and `read_workflow` ship in S3-02 / S3-04). Type annotations resolve under `mypy --strict`.
- [ ] **AC-2 — `EventLogWriteCapability` concrete Pydantic record.** `src/codegenie/durable/capabilities.py` exports `EventLogWriteCapability(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")`, fields `task_queue: TaskQueueName`, `allowed_kinds: frozenset[str]`, `minted_at: datetime`. Construction with a non-`frozenset` `allowed_kinds` is a Pydantic validation error (test asserts this).
- [ ] **AC-3 — Capability allowlist enforced before Postgres.** A call to `EventLog.append(event, capability=cap)` where `event.kind not in cap.allowed_kinds` raises `EventCapabilityViolation` (typed exception under `codegenie.events.errors`) carrying `.kind: str` and `.allowed: frozenset[str]` attributes — **before any connection is acquired from the pool**. Test patches the pool's `connection()` to raise on entry and asserts the violation surfaces without the patch firing.
- [ ] **AC-4 — First event in a workflow has `prev_hash = NULL`.** An append for a workflow not in the LRU and not present in `events.events` writes a row with `prev_hash IS NULL` and `wf_seq = 1`. Integration test against fresh testcontainer Postgres asserts the row reads back with `prev_hash IS NULL`.
- [ ] **AC-5 — `row_hash = BLAKE3(prev_row_hash || canonical_payload)`.** The canonical payload is `EventPayloadAdapter.dump_json(event)` (bytes). For the first event, `row_hash = BLAKE3(b"" || canonical_payload)` — i.e., the empty-bytes prefix is the convention (NOT `prev_row_hash` as some sentinel string). Subsequent events in the same workflow concatenate the prior `row_hash` (BYTEA, 32 bytes) with the canonical payload. Test computes the hash off-line via `blake3` and compares byte-for-byte against the stored `row_hash`.
- [ ] **AC-6 — Per-workflow chain-head LRU with bounded size.** The LRU is bounded to `chain_lru_max=200` workflows. Filling it past 200 evicts the least-recently-appended workflow; the next append for the evicted workflow re-reads the chain tail from Postgres (`SELECT row_hash, wf_seq FROM events.events WHERE workflow_id = $1 ORDER BY wf_seq DESC LIMIT 1`). Test fills the LRU to 201 and asserts the 201st workflow's first append issues exactly one chain-tail SELECT before its INSERT.
- [ ] **AC-7 — `wf_seq` allocated server-side via `RETURNING`.** The INSERT statement reads `INSERT INTO events.events (...) VALUES (...) RETURNING wf_seq`; the client never computes `wf_seq` itself. Test inserts 5 events for one workflow and asserts the returned sequence is `(1, 2, 3, 4, 5)`. (S2-03 owns the index that makes this unique; this story owns the writer that uses it.)
- [ ] **AC-8 — Concurrent workflows append in parallel; same-workflow appends serialize.** Integration test launches 3 concurrent `asyncio.gather`-d workflows, each issuing 100 appends; asserts (a) every workflow's chain is internally consistent (`prev_hash[n].row_hash == prev_hash[n-1].row_hash`-equivalent — `row_hash[n] = BLAKE3(row_hash[n-1] || payload[n])`), (b) `wf_seq` within each workflow is `1..100` with no gaps, (c) cross-workflow wall-clock parallelism is observed (total time < 3× single-workflow time — sanity guard, not a perf assertion).
- [ ] **AC-9 — Portfolio events (`workflow_id = None`) skip the chain.** An append whose `event.workflow_id is None` writes `wf_seq = NULL`, `prev_hash = NULL`, `row_hash = BLAKE3(canonical_payload)` (no prior-hash prefix). Test inserts a `WorkflowStarted` with `workflow_id=None` (portfolio-scoped variants like a future config event); asserts the row has `wf_seq IS NULL` and the row_hash matches a pure `BLAKE3(payload)`.
- [ ] **AC-10 — Cold-restart chain-tail re-read is correct.** Construct a fresh `EventLog` instance (simulating a worker restart), append 3 events to workflow `wf1`; throw away the instance; construct a new `EventLog` with the same pool; append the 4th event; assert `row_hash[4] = BLAKE3(row_hash[3] || payload[4])` exactly (where `row_hash[3]` is read fresh from Postgres). The test commits each event individually so the chain-tail SELECT sees committed data.
- [ ] **AC-11 — Append is atomic per event.** A simulated `psycopg.OperationalError` mid-INSERT (patch `cursor.execute` to raise) leaves no partial row, does NOT update the LRU, and propagates the error to the caller. Test asserts `events.events` row count is unchanged AND the LRU entry for that workflow is unchanged after the failed call.
- [ ] **AC-12 — `EventId` allocation.** `event_id` is a `UUID` hex string (matching the schema's `UUID PRIMARY KEY`); construction lives in `EventPayload._Base.event_id`'s default factory (S1-02 owns the factory). This story asserts the returned `EventId` equals the inserted `event_id` column. (No new UUID logic here — just the round-trip.)
- [ ] **AC-13 — Lint / type clean + cold-start fence.** `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/events/{log,errors,capabilities}.py` (capabilities file lives at `codegenie.durable.capabilities` per arch); `make lint-imports` green; per-submodule cold-start fence stays green (importing `codegenie.events.log` does NOT eagerly touch Postgres).

## Implementation outline

1. **Capability + error types first (smallest leaves).** Create `src/codegenie/durable/capabilities.py` per AC-2 (frozen Pydantic with `extra="forbid"`). Create `src/codegenie/events/errors.py` with `EventCapabilityViolation(Exception)` carrying typed `.kind` + `.allowed`.
2. **Write the red test for AC-3 (capability rejection) — it's the cheapest unit test, no Postgres needed.** Patch `pool.connection` to raise `RuntimeError("must not be called")`; construct `EventLog(pool=patched_pool)`; call `append(event, capability=cap_with_disjoint_allowed_kinds)`; assert `EventCapabilityViolation` surfaces with the right `.kind` and `.allowed`.
3. **`EventLog.__init__` skeleton.** Store `pool`, construct an OrderedDict-based LRU bounded by `chain_lru_max`. The LRU key is `WorkflowId`; the value is a tuple `(row_hash: bytes, wf_seq: int)`. Use `collections.OrderedDict` + `move_to_end` for the eviction order (precedent: `codegenie.probes.registry`'s LRU-of-200; mirror that idiom).
4. **`append` flow (read this carefully):**
   - **(a)** Check `event.kind in capability.allowed_kinds`; if not, raise `EventCapabilityViolation(kind=event.kind, allowed=capability.allowed_kinds)`.
   - **(b)** Compute `canonical_payload: bytes = EventPayloadAdapter.dump_json(event)`.
   - **(c)** If `event.workflow_id is None`: `prev_hash = None`, `wf_seq_param = None`, `row_hash = blake3(canonical_payload).digest()`. Insert and return `EventId`.
   - **(d)** Else: look up `event.workflow_id` in the LRU. On hit, take the cached `(row_hash, _)` tuple. On miss, acquire a connection and `SELECT row_hash FROM events.events WHERE workflow_id = $1 ORDER BY wf_seq DESC LIMIT 1` (returns `None` for first-ever event). Compute `row_hash = blake3((prev_row_hash or b"") + canonical_payload).digest()`.
   - **(e)** Issue `INSERT INTO events.events (event_id, workflow_id, kind, timestamp, correlation_id, payload, prev_hash, row_hash, wf_seq) VALUES (...) RETURNING wf_seq`. `wf_seq` is allocated by a sub-select: `(SELECT COALESCE(MAX(wf_seq), 0) + 1 FROM events.events WHERE workflow_id = $2)`. The `events_wf_seq_uniq` UNIQUE INDEX (S2-03) is the integrity backstop.
   - **(f)** Update the LRU: `self._chain_heads[workflow_id] = (new_row_hash, new_wf_seq)`; `move_to_end(workflow_id)`. Evict the oldest if over `chain_lru_max`.
   - **(g)** Return `event.event_id` as `EventId`.
5. **Spike the chain-tail SELECT path before wiring the LRU.** Write a tiny standalone test (real testcontainer Postgres if available; else `pytest-postgresql` ephemeral): insert 3 rows manually via `application_role`, instantiate a fresh `EventLog`, append a 4th, read all 4 back, verify chain. This is AC-10's test.
6. **Use a transaction per append** (Postgres default isolation `READ COMMITTED` is fine — the wf_seq UNIQUE INDEX is the serial-write integrity check for one workflow's stream).
7. **Atomic-failure test (AC-11)** — monkeypatch `psycopg.AsyncCursor.execute` to raise on the INSERT; assert no row, no LRU update.
8. **Per-submodule cold-start fence.** Add an entry to `tests/fence/test_module_cold_start.py` (or its phase-9 equivalent) asserting `import codegenie.events.log` does NOT call `pool.connection()`. The constructor must be IO-free.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/events/test_event_log_capability.py`

Test intent: A capability whose `allowed_kinds` is disjoint from `event.kind` MUST cause `append` to raise **before** any Postgres connection is acquired. The pool's `connection()` is monkeypatched to raise `RuntimeError("must not be called")`; the test passes only if `EventCapabilityViolation` is what surfaces (not the `RuntimeError`).

```python
# Test outline only; full body is the implementer's job.
async def test_append_rejects_event_kind_outside_capability_before_postgres(
    fake_pool_that_raises_on_connection,
):
    """AC-3 — capability check fires BEFORE any pool acquisition.
    If this test ever passes by accident (RuntimeError leaks), we have
    leaked credentials into a connection-acquisition retry storm."""
    log = EventLog(pool=fake_pool_that_raises_on_connection)
    cap = EventLogWriteCapability(
        task_queue=TaskQueueName("system"),
        allowed_kinds=frozenset({"workflow_started"}),  # disjoint
        minted_at=datetime.now(UTC),
    )
    bad_event = MergeOutcome(...)  # kind="merge_outcome", outside allowed
    with pytest.raises(EventCapabilityViolation) as exc_info:
        await log.append(bad_event, capability=cap)
    assert exc_info.value.kind == "merge_outcome"
    assert "workflow_started" in exc_info.value.allowed
    # Belt: the pool was never touched.
    fake_pool_that_raises_on_connection.connection.assert_not_called()
```

Why it fails: `codegenie.events.log` doesn't exist yet — `ImportError`.

### Green — minimal pass

- Create `errors.py` with `EventCapabilityViolation`.
- Create `log.py` with `EventLog.__init__` (no IO) and `append` that performs the capability check first, then `NotImplementedError` for the rest. The red test goes green.

### Required follow-on tests (integration; testcontainers Postgres)

Each test corresponds to one AC; intent stated, not bodies.

- **`test_first_event_writes_null_prev_hash`** (AC-4) — fresh workflow, fresh LRU, assert the row reads back with `prev_hash IS NULL` and `wf_seq = 1`.
- **`test_row_hash_matches_offline_blake3`** (AC-5) — compute the expected hash with `blake3` directly in the test, assert byte-equality with the stored `row_hash`. **This test is the canonical "the chain formula is what ADR-0003 says" assertion** — must catch a refactor that accidentally swaps the concat order or hashes UTF-8-decoded JSON instead of bytes.
- **`test_lru_evicts_at_201_workflows`** (AC-6) — fill the LRU to 200, then 201; spy on the chain-tail SELECT counter; the 201st workflow's first append issues exactly one tail-SELECT.
- **`test_wf_seq_is_dense_within_a_workflow`** (AC-7) — 5 appends to one workflow return `(1,2,3,4,5)` exactly; no gaps under serial-write conditions.
- **`test_concurrent_workflows_chain_independently`** (AC-8) — 3 concurrent workflows × 100 events each; each chain verifies internally; cross-workflow parallelism observed (`wall_clock < 3 * single_workflow_time` — a sanity heuristic).
- **`test_portfolio_event_skips_chain`** (AC-9) — `workflow_id=None`; row has `wf_seq IS NULL`, `prev_hash IS NULL`, `row_hash = BLAKE3(canonical_payload)`.
- **`test_cold_restart_chain_tail_reread`** (AC-10) — construct, append 3, discard, construct fresh, append 4th; verify the new row's `prev_hash` matches the 3rd row's `row_hash` read fresh from Postgres.
- **`test_failed_append_leaves_no_partial_state`** (AC-11) — monkeypatch INSERT to raise; assert `SELECT COUNT(*) FROM events.events` unchanged AND LRU entry for that workflow unchanged.

### Property test (Hypothesis)

`tests/property/test_event_log_chain_invariant.py` — generate sequences of 2–20 events for one workflow (Hypothesis strategy over the 21-variant union, drawn from S1-02's strategies); insert them via `EventLog.append`; read them back; assert the chain verifies (`row_hash[n] == BLAKE3(row_hash[n-1] || dump_json(events[n]))`). This is the bytes-level invariant ADR-0003 names; a single example test can be mutated past with a wrong concat order; the property test cannot.

### Refactor

- Extract the canonical-payload-bytes computation into a tiny pure helper `_canonical_payload_bytes(event: EventPayload) -> bytes` and unit-test it independently (`EventPayloadAdapter.dump_json(event)` round-trip). Functional core / imperative shell.
- Module docstring on `log.py` cites ADR-0003, names the LRU eviction policy, and points at the cold-restart re-read path as the load-bearing recovery mechanism.
- `EventCapabilityViolation`'s `__init__` takes `kind: str, allowed: frozenset[str]`; message: `f"event kind {kind!r} not in capability.allowed_kinds={sorted(allowed)!r}"`. Sorted for deterministic test assertions.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/events/log.py` | `EventLog` class, `append` method, LRU, chain-tail re-read. |
| `src/codegenie/events/errors.py` | `EventCapabilityViolation` typed exception. |
| `src/codegenie/durable/capabilities.py` | `EventLogWriteCapability` concrete Pydantic record (S1-06 declared Protocols; this story lands the record). |
| `tests/unit/events/__init__.py` | Test package marker (may already exist from S1-02). |
| `tests/unit/events/test_event_log_capability.py` | Red test + capability-check tests (no Postgres). |
| `tests/integration/events/__init__.py` | Test package marker. |
| `tests/integration/events/test_event_log_append.py` | All Postgres-backed integration tests (AC-4 through AC-11). |
| `tests/property/test_event_log_chain_invariant.py` | Hypothesis property: chain verifies for generated event sequences. |
| `tests/fixtures/events/__init__.py` | If not already present from S1-02. |
| `tests/fixtures/events/postgres.py` | Testcontainer fixture for fresh `events` schema (alembic-up + truncate-between-tests). |

## Out of scope

- **`append_batch`** — handled by S3-02. The batched COPY-binary path is a different write strategy; `append` here is single-row INSERT.
- **`@critical_event` synchronous-flush dispatch** — handled by S3-03. This story's `append` is already synchronous (one INSERT, one commit); S3-03's job is to make S3-02's batched path bypass back to synchronous for critical variants.
- **`read_workflow` + chain-verify-on-read** — handled by S3-04. This story writes; S3-04 reads + verifies.
- **`ChainTamperDetected` emission** — handled by S3-04. The write side has no tamper to detect; tamper is a read-time discovery.
- **`BlobRef`** — handled by S3-05. Events here are inlined; payloads > 8 KiB will use BlobRef once S3-05 lands and S4-03 wires `build_bundle` to call `write_blob_ref`.
- **Sanitizer / `RedactedActivityResult.seal`** — handled by S3-06. Sanitization is an activity-boundary concern; this story is the event-log substrate, one layer down.
- **Throughput bench** — handled by S3-07. This story's perf budget is "doesn't pathologically regress"; the formal ≥3k events/sec assertion ships in S3-07.
- **Worker-process EventBatchWriter lifecycle** — handled by S3-02. This story instantiates `EventLog` directly in tests; production-path wiring is the worker bootstrap (S6-01).
- **Adversarial chain-tamper forge test** — handled by S3-04's `tests/adv/test_event_chain_tamper_detection.py` (requires `migrations_role` forge access, which is the read-side discovery path).

## Notes for the implementer

### §1 — The hash formula is load-bearing

ADR-0003's formula is `row_hash = BLAKE3(prev_row.row_hash || canonical_payload)`. **`canonical_payload` is bytes**, not a Python string. The bytes come from `EventPayloadAdapter.dump_json(event)`. **Do not** hash a `.model_dump()` dict — Python dict insertion order is deterministic in 3.11+ but the `json.dumps` defaults are not byte-stable across Python versions. The Pydantic `TypeAdapter.dump_json` path IS byte-stable because Pydantic owns the serializer.

The first-event convention is `prev_row_hash = b""` (empty bytes), NOT `b"\x00" * 32` and NOT `None`-prefixed. The chain-verifier in S3-04 must use the same convention; the AC-5 test is the canonical assertion.

### §2 — LRU eviction with `OrderedDict`

The 200-entry LRU is bounded *per-worker-process*. `collections.OrderedDict` + `move_to_end(key, last=True)` is the canonical Python idiom. Eviction: `self._chain_heads.popitem(last=False)` removes the least-recently-touched. AC-6's test is the integrity check.

Avoid `functools.lru_cache` — it's a decorator on a callable, not a data structure you can mutate. We need explicit mutation (insert, update, evict).

### §3 — `wf_seq` allocation in the INSERT

Two approaches; the implementer should pick one and document the choice in the module docstring:

- **Sub-select in the INSERT** (recommended): `INSERT ... VALUES (..., (SELECT COALESCE(MAX(wf_seq), 0) + 1 FROM events.events WHERE workflow_id = $1), ...) RETURNING wf_seq`. The UNIQUE INDEX is the integrity backstop; under serial-write to one workflow's stream, there is no race.
- **Application-side increment from LRU**: read the cached `wf_seq`, increment, INSERT with the explicit value. Faster (no sub-select) but requires the LRU to be authoritative; a stale LRU (post-eviction + concurrent insert from another worker for the same workflow) corrupts the count. Reject — same-workflow concurrent writes across workers are out of scope for Phase 9 but the cross-worker contention case is a hidden landmine.

Sub-select wins on robustness. The 5-µs overhead is invisible against the 1-15ms RTT.

### §4 — Capability check is the first line of `append`

AC-3's red test is the canonical "the check fires before any IO" assertion. Resist any refactor that moves the check inside a `try`/`finally` that opens a connection — the test will go red but the bug will be silent in production (a compromised activity will leak a connection-acquisition retry loop before its violation surfaces).

### §5 — `EventLogWriteCapability.allowed_kinds` is a `frozenset[str]`

Pydantic v2's `frozenset` validation is strict — passing a `set` or `list` is a validation error. AC-2's test asserts this. The strict typing is what makes the capability auditable: a misconfigured worker that mints a capability allowing too many kinds fails at construction, not at first abusive append.

### §6 — Per-submodule cold-start fence

Importing `codegenie.events.log` MUST NOT acquire a Postgres connection. The constructor takes a pool but does not touch it. Add an entry to the per-submodule cold-start fence (`tests/fence/test_phase09_cold_start.py` or sibling) asserting `import codegenie.events.log` is IO-free. This is the load-bearing assertion that the module is safe to import in any test context.

### §7 — Chain-tail re-read on miss is a SINGLE SELECT

The cold-restart path issues exactly ONE query per evicted workflow's first append: `SELECT row_hash, wf_seq FROM events.events WHERE workflow_id = $1 ORDER BY wf_seq DESC LIMIT 1`. The `events_wf_seq_idx` (partial index where `workflow_id IS NOT NULL`) makes this an index scan, not a table scan.

Do NOT cache a "previously known empty" sentinel — a workflow that has zero events legitimately wants `prev_hash = NULL` on the next append, and the SELECT returning empty is the correct signal.

### §8 — Not adopted (YAGNI)

- **Async-cache (`asyncache.LRUCache`)** — not adopted. The LRU is mutated only inside `append` which is already serial-per-`asyncio`-loop; we don't need an async-safe primitive. `OrderedDict` is fine.
- **Distributed chain-head cache (Redis)** — not adopted. ADR-0003's "200 in-flight per worker" budget is per-process; cross-worker coordination of the same workflow's chain head is out of scope (a workflow's activity executions are partitioned by task queue, and within a queue the worker pool routes per `workflow_id` via Temporal sticky tasking).
- **Chain-verify-on-write** — not adopted. Verification is the read path's job (S3-04). Writers cannot detect tamper that happens after their own write.
- **A `flush()` method** — not adopted. Single-row INSERT in this story is auto-committed by `psycopg`'s default. The batched path (S3-02) introduces `flush()` semantics.
