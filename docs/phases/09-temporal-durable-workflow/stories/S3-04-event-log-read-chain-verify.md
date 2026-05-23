# Story S3-04 — `EventLog.read_workflow` + chain-verify on read

**Step:** Step 3 — Canonical event log, BlobRef store, and activity-boundary sanitizer
**Status:** Ready
**Effort:** S
**Depends on:** S3-01 (chain semantics on the write side), S3-02 (batched chain — read must verify both write paths)
**ADRs honored:** ADR-0003 (per-workflow BLAKE3 chain — chain-verify is the read-side companion to S3-01's write-side hash), ADR-0006 (`ChainTamperDetected` is `@critical_event`; emission goes through S3-03's sync-flush path), production ADR-0034

## Context

S3-01 and S3-02 ship the **write side** of the per-workflow BLAKE3 chain. This story ships the **read side**: `EventLog.read_workflow(workflow_id) -> AsyncIterator[EventPayload]` that streams a workflow's events in `wf_seq` order **and verifies the chain as it reads**. Verification is per-row: for each row n > 1, assert `row_hash[n] == BLAKE3(row_hash[n-1] || canonical_payload[n])` exactly.

A chain break — either a gap in `wf_seq` (missing row) or a hash mismatch (tampered row) — triggers emission of a `ChainTamperDetected` event (the load-bearing `@critical_event` variant) via the sync-flush path from S3-03, then **halts the iterator** for that workflow. Downstream projections (audit_trail, retry_histogram, plugin_telemetry — all in Step 7) call `read_workflow` to fold; they observe the halt and stop folding for that workflow. The intent: silent corruption MUST NOT survive across a fold.

This story also ships the **adversarial chain-tamper test** (`tests/adv/test_event_chain_tamper_detection.py`) — uses the `migrations_role` connection (DDL on `events` schema only, per S2-03's grants) to forge a row's `payload` column, then asserts the next `read_workflow` emits `ChainTamperDetected` and halts. `migrations_role` is the role with the privilege to mutate the table — the test simulates a compromise of that role; the chain is the structural defense.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C5 — EventLog.read_workflow` (the public signature; chain-verify-as-you-read; emit `ChainTamperDetected` on break).
  - `../phase-arch-design.md §C10 — Projections` (projections call `read_workflow`; `audit_trail` is the canonical consumer).
  - `../phase-arch-design.md §Edge cases §8` (chain-tamper detection path).
  - `../phase-arch-design.md §Scenarios §3` (adversarial: replay-determinism — sibling adversarial pattern; this story's adv test follows the same scaffolding).
- **Phase ADRs:**
  - `../ADRs/0003-per-workflow-blake3-prev-hash-chain.md` — **load-bearing.** "Projections verify the chain as they fold. A break emits `ChainTamperDetected` and halts the projection for that workflow."
  - `../ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — `ChainTamperDetected` is one of the five `@critical_event` variants; emission rides the sync-flush bypass S3-03 provides.
- **Existing code:**
  - `src/codegenie/events/log.py` (S3-01 / S3-02 / S3-03) — `EventLog.append`, `EventBatchWriter`, the chain-head LRU.
  - `src/codegenie/events/payloads.py` (S1-02 + S1-03) — `EventPayloadAdapter.validate_python` for re-hydration from `JSONB`, `ChainTamperDetected` variant.
- **External:**
  - psycopg async cursor streaming: `async for row in cursor.stream("SELECT ...")` — Postgres-side cursor avoids loading the whole result set into memory.

## Goal

Ship `EventLog.read_workflow(workflow_id) -> AsyncIterator[EventPayload]` that streams events in `wf_seq` ascending order, verifies the per-row BLAKE3 chain, and on any break (gap or mismatch) (a) emits a `ChainTamperDetected` via the sync-flush path with `expected_hash` / `actual_hash` / `at_seq` populated, (b) raises `ChainBrokenError` from the iterator so the caller's fold halts. Ship the adversarial test that forges a row via `migrations_role` and asserts detection.

## Acceptance criteria

- [ ] **AC-1 — Public surface.** `EventLog.read_workflow(workflow_id: WorkflowId) -> AsyncIterator[EventPayload]`. The return type is an async iterator (e.g., `async def read_workflow(...) -> AsyncIterator[EventPayload]: yield ...`). The iterator is consumed via `async for event in log.read_workflow(wf): ...`. Type-checks under `mypy --strict`.
- [ ] **AC-2 — `wf_seq` ascending order.** Events are yielded in strictly ascending `wf_seq` order. SQL: `SELECT ... FROM events.events WHERE workflow_id = $1 ORDER BY wf_seq ASC`. Test inserts 50 events with shuffled COPY order (S3-02 path); read returns them in `wf_seq = 1..50` order.
- [ ] **AC-3 — Chain-verify per row.** For each row n > 1, the iterator asserts `row.row_hash == BLAKE3(prev_row.row_hash || EventPayloadAdapter.dump_json(event)).digest()` exactly. For row 1, asserts `row.row_hash == BLAKE3(b"" || canonical_payload).digest()` AND `row.prev_hash IS NULL`. **The canonical chain-verify assertion.**
- [ ] **AC-4 — Hash mismatch emits `ChainTamperDetected` and halts.** Insert 3 rows via the writer; forge row 2's `payload` column via direct `application_role` UPDATE (which the trigger blocks — use `migrations_role` instead per S2-03 grants); `read_workflow(wf)` iterates row 1 fine, then on row 2 (a) emits a `ChainTamperDetected(expected_hash=..., actual_hash=..., at_seq=2)` event via `EventLog.append` (sync), (b) raises `ChainBrokenError` from the iterator. Row 3 is NOT yielded.
- [ ] **AC-5 — `wf_seq` gap emits `ChainTamperDetected` and halts.** Insert rows with `wf_seq = 1, 2, 4` (skip 3) by using `migrations_role` to bypass `events_wf_seq_uniq`. `read_workflow` yields rows 1, 2, then on attempting to read row 3 detects `wf_seq` jumps to 4 (expected = `prev.wf_seq + 1 = 3`), emits `ChainTamperDetected(at_seq=3)`, raises `ChainBrokenError`. Row 4 not yielded.
- [ ] **AC-6 — `ChainTamperDetected` rides sync-flush.** The emission of `ChainTamperDetected` from inside `read_workflow` is itself a `@critical_event` (per ADR-0006); the emit MUST go through `EventLog.append` (sync path) not the batched path. Test patches `EventBatchWriter.enqueue` to assert it is NOT called during chain-tamper handling; only `EventLog.append` is.
- [ ] **AC-7 — Adversarial: forged payload via `migrations_role`.** `tests/adv/test_event_chain_tamper_detection.py` — uses a `migrations_role` connection (testcontainers PG with the role configured per S2-03's grants) to issue `UPDATE events.events SET payload = $1 WHERE event_id = $2`. Then `application_role` calls `read_workflow(wf)`; the iterator emits `ChainTamperDetected` and raises. The test asserts: (a) the emission row exists in `events.events`; (b) the typed `ChainTamperDetected.expected_hash` matches what S3-01's chain would have produced; (c) `actual_hash` matches the forged row's recomputed hash; (d) `at_seq` matches the forged row's `wf_seq`.
- [ ] **AC-8 — Streaming with server-side cursor.** `read_workflow` uses a server-side cursor (`async with conn.cursor(name="ev_stream") as cur: async for row in cur.stream("SELECT ... WHERE workflow_id = $1 ORDER BY wf_seq ASC", (wf,)): yield ...`) — does NOT load the whole result set into memory. Test inserts 10,000 events for one workflow, asserts `read_workflow` yields them without holding more than ~1 MiB resident.
- [ ] **AC-9 — `ChainBrokenError` is typed.** `codegenie.events.errors.ChainBrokenError(Exception)` carries `.workflow_id: WorkflowId`, `.at_seq: WorkflowSeq`, `.reason: Literal["hash_mismatch", "wf_seq_gap"]`. Tests assert all three attributes are populated correctly for each failure mode.
- [ ] **AC-10 — Re-reading after a halt re-detects.** After a halt, calling `read_workflow(wf)` again re-emits `ChainTamperDetected` (the chain is still broken; no idempotence on `ChainTamperDetected` event_id because each emit gets a fresh `EventId`). This is intentional: forensic operators want every read attempt to surface the tamper. Test asserts two consecutive `read_workflow` calls each emit a `ChainTamperDetected` (two distinct rows).
- [ ] **AC-11 — Read on a healthy chain yields all events without emitting anything.** Insert 100 events for one workflow; `read_workflow` yields all 100 with no `ChainTamperDetected` emission. Test asserts post-read event count for that workflow is exactly 100 (no extra rows).
- [ ] **AC-12 — Empty workflow yields zero events without error.** `read_workflow` of an unknown `workflow_id` returns an empty iterator. No error, no `ChainTamperDetected`.
- [ ] **AC-13 — `mypy --strict` + lint clean.**

## Implementation outline

1. **`ChainBrokenError`** in `src/codegenie/events/errors.py` per AC-9.
2. **`read_workflow` skeleton** in `src/codegenie/events/log.py`:
    ```python
    async def read_workflow(self, workflow_id: WorkflowId) -> AsyncIterator[EventPayload]:
        async with self._pool.connection() as conn:
            async with conn.cursor(name=f"ev_stream_{uuid.uuid4().hex}") as cur:
                await cur.execute(
                    "SELECT event_id, workflow_id, kind, timestamp, correlation_id, "
                    "payload, prev_hash, row_hash, wf_seq "
                    "FROM events.events WHERE workflow_id = %s ORDER BY wf_seq ASC",
                    (workflow_id,),
                )
                prev_row_hash: bytes = b""
                prev_wf_seq: int = 0
                async for raw_row in cur:
                    event = _hydrate_event(raw_row.payload)  # EventPayloadAdapter
                    # AC-3 chain check
                    expected_hash = blake3(prev_row_hash + EventPayloadAdapter.dump_json(event)).digest()
                    if raw_row.row_hash != expected_hash:
                        await self._emit_tamper(workflow_id, expected_hash, raw_row.row_hash, raw_row.wf_seq)
                        raise ChainBrokenError(workflow_id, raw_row.wf_seq, "hash_mismatch")
                    # AC-5 gap check
                    if raw_row.wf_seq != prev_wf_seq + 1:
                        await self._emit_tamper(workflow_id, ..., ..., prev_wf_seq + 1)
                        raise ChainBrokenError(workflow_id, WorkflowSeq(prev_wf_seq + 1), "wf_seq_gap")
                    yield event
                    prev_row_hash = raw_row.row_hash
                    prev_wf_seq = raw_row.wf_seq
    ```
3. **`_emit_tamper`** — private method on `EventLog`. Constructs the `ChainTamperDetected` event and calls `self.append(event, capability=_internal_tamper_capability)`. The `_internal_tamper_capability` is a static `EventLogWriteCapability` minted at `EventLog.__init__` time with `allowed_kinds={"chain_tamper_detected"}` — narrow, single-purpose. **NOT minted from the K8s ServiceAccount** because tamper-detection is an internal correctness mechanism, not a user-facing emission.
4. **Adversarial test (AC-7) scaffolding.** The testcontainers fixture needs to expose a `migrations_role`-connected pool alongside the default `application_role` pool. Document in the fixture file. The test:
    ```python
    async def test_forged_row_emits_chain_tamper_detected(
        application_pool, migrations_pool, fresh_events_schema,
    ):
        log = EventLog(pool=application_pool)
        wf = WorkflowId("wf-tamper-01")
        # 1. Write 3 legitimate events.
        await log.append(_make_event(wf, kind="route_decided"), capability=cap)
        e2 = _make_event(wf, kind="recipe_applied")
        await log.append(e2, capability=cap)
        await log.append(_make_event(wf, kind="patch_applied"), capability=cap)
        # 2. Forge row 2.
        async with migrations_pool.connection() as conn:
            await conn.execute(
                "UPDATE events.events SET payload = %s WHERE event_id = %s",
                (Jsonb({"kind": "recipe_applied", "tampered": True, ...}), e2.event_id),
            )
        # 3. Read and assert detection.
        with pytest.raises(ChainBrokenError) as exc_info:
            events = [ev async for ev in log.read_workflow(wf)]  # noqa: F841
        assert exc_info.value.reason == "hash_mismatch"
        assert exc_info.value.at_seq == WorkflowSeq(2)
        # 4. Assert ChainTamperDetected row exists.
        tamper_rows = await _fetch_events_by_kind(application_pool, wf, "chain_tamper_detected")
        assert len(tamper_rows) == 1
        assert tamper_rows[0].payload["at_seq"] == 2
    ```
5. **Wait for one of two adversarial scenarios for AC-5 (`wf_seq` gap):** Insert rows with `wf_seq = 1, 2, 4` directly via `migrations_role` (raw INSERT, bypassing the writer). The test verifies the iterator detects the gap.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/integration/events/test_read_workflow_chain_verify.py`

Test intent: A healthy 5-event workflow streams without emitting anything; a 5-event workflow with row 3's `row_hash` flipped raises `ChainBrokenError` and emits a `ChainTamperDetected`.

```python
# Test outline only.
async def test_healthy_chain_streams_without_tamper_event(pg_pool, fresh_events_schema):
    """AC-2, AC-3, AC-11 — happy path; chain-verify is silent when intact."""
    log = EventLog(pool=pg_pool)
    wf = WorkflowId("wf-healthy-01")
    cap = _full_capability_for("system")
    for _ in range(5):
        await log.append(_make_event(workflow_id=wf, kind="route_decided"), capability=cap)
    yielded = [ev async for ev in log.read_workflow(wf)]
    assert len(yielded) == 5
    assert [ev.wf_seq for ev in yielded] == [1, 2, 3, 4, 5]
    tamper = await _count_events_by_kind(pg_pool, wf, "chain_tamper_detected")
    assert tamper == 0
```

Why it fails: `read_workflow` doesn't exist yet.

### Green — minimal pass

- Add `read_workflow` per the outline.
- Add `_emit_tamper` private method.
- Add `ChainBrokenError`.
- Healthy-chain test passes.

### Required follow-on tests

- **`test_hash_mismatch_detected`** (AC-3, AC-4) — flip a row's `row_hash` directly via `migrations_role`; assert `ChainBrokenError("hash_mismatch", at_seq=N)`.
- **`test_wf_seq_gap_detected`** (AC-5) — insert rows with a gap; assert `ChainBrokenError("wf_seq_gap")`.
- **`test_tamper_event_rides_sync_path`** (AC-6) — patch `EventBatchWriter.enqueue` to fail loudly if called during `read_workflow` failure; tamper still emits.
- **`test_forged_payload_adversarial`** (AC-7) — the load-bearing adversarial test; lives under `tests/adv/`.
- **`test_streaming_does_not_load_all_into_memory`** (AC-8) — 10k events; check `tracemalloc` or peak RSS during iteration; assert < 5 MiB increase.
- **`test_chain_broken_error_carries_typed_attributes`** (AC-9) — exhaustive check of `.workflow_id`, `.at_seq`, `.reason` for both reasons.
- **`test_re_read_after_halt_emits_tamper_again`** (AC-10) — two consecutive failing reads, two tamper rows.
- **`test_empty_workflow_yields_nothing`** (AC-12) — `read_workflow(WorkflowId("never-existed"))` returns empty.

### Property test (Hypothesis)

`tests/property/test_chain_verify_invariance.py` — Hypothesis generates a healthy chain via `EventLog.append` for 2-30 events; reads it back via `read_workflow`; asserts the iterator yields the same events in the same order with no `ChainTamperDetected` emitted. This is the canonical "happy-path chain-verify is silent" invariant.

### Refactor

- Extract the per-row chain-check into a small pure helper `_verify_row(prev_row_hash, prev_wf_seq, raw_row, hydrated_event) -> tuple[bytes, int] | ChainBrokenError`. Returns the new `prev_row_hash`/`prev_wf_seq` on success; returns the typed error otherwise. Pure / testable in isolation.
- Module docstring on `log.py` adds a "Read path / chain-verify" subsection citing ADR-0003 and ADR-0006.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/events/log.py` | Add `read_workflow` async iterator + `_emit_tamper` + `_internal_tamper_capability`. |
| `src/codegenie/events/errors.py` | Add `ChainBrokenError` typed exception. |
| `tests/integration/events/test_read_workflow_chain_verify.py` | Healthy + tampered chain integration tests. |
| `tests/adv/test_event_chain_tamper_detection.py` | The load-bearing adversarial test (forged payload via `migrations_role`). |
| `tests/property/test_chain_verify_invariance.py` | Hypothesis property: healthy chains round-trip silently. |
| `tests/fixtures/events/postgres.py` | Extend with the `migrations_pool` fixture (alongside the existing `application_pool`). |

## Out of scope

- **`BlobRef`** — S3-05.
- **Sanitizer** — S3-06.
- **Throughput bench** — S3-07.
- **Projections (`audit_trail`, etc.)** — Step 7. This story ships `read_workflow`; projections consume it.
- **A `read_kind` / `read_correlation_id` API** — out of scope per `stories/README.md §Open implementation questions §7`. May land additively if projection ergonomics drift.
- **Cross-workflow chain verify** — out of scope by design (ADR-0003: portfolio events are NOT chained; cross-workflow re-ordering attacks are not in the threat model).
- **Recovery from chain break** — out of scope. Operators must manually inspect the tamper event, identify the corruption source, and quarantine the workflow. Phase 9 surfaces the break; remediation is a runbook concern, not code.
- **Halting a partial fold mid-projection** — Step 7 (S7-01 specifically) owns the projection-side response to `ChainBrokenError`.

## Notes for the implementer

### §1 — The chain-verify formula is symmetric with the write

Write side (S3-01): `row_hash = BLAKE3(prev_row_hash || canonical_payload)`.
Read side (this story): `expected = BLAKE3(prev_row_hash || canonical_payload)`; assert `actual == expected`.

The **canonical payload bytes** must be computed the same way on both sides: `EventPayloadAdapter.dump_json(event)`. If S3-01 used a different serializer, the chain-verify will fail spuriously on every healthy row. The `_canonical_payload_bytes` helper extracted in S3-01 / S3-02 is shared with this story.

### §2 — Server-side cursor matters

The 10k-event test (AC-8) is the canary that "streaming" is actually streaming. A naive `await conn.execute("SELECT ...")` followed by `for row in cur.fetchall()` loads everything into RAM. The named-cursor `cur.stream(...)` form (psycopg 3.x) streams from Postgres. The `tracemalloc` assertion is the proof.

### §3 — `_internal_tamper_capability` is NOT minted from the SA mount

The tamper-detection emission is **internal** — it's the chain-verify mechanism reporting on itself. It doesn't have an external caller's capability to use; constructing one in-process at `EventLog.__init__` time is correct. The `allowed_kinds={"chain_tamper_detected"}` narrows the capability so it can't be abused as a general-purpose write key.

`tests/adv/test_capability_token_scope.py` (S6-02 / S8-03 land it) does NOT need to test this internal capability — it's not user-faced.

### §4 — `ChainTamperDetected` emission can itself fail

What if the sync emit of `ChainTamperDetected` *itself* fails (Postgres down)? Two paths:

1. **Propagate the error to the read caller** — replace the `ChainBrokenError` with the underlying Postgres error. Loud, surfaces the infrastructure issue.
2. **Swallow the emission error and still raise `ChainBrokenError`** — the caller knows the chain is broken; the missing tamper row is recoverable on the next read (AC-10's "re-reading re-detects" semantics).

Path 2 is correct: the chain-break detection is the primary signal; the audit-trail emission is a secondary record. Path 1 risks the caller hiding the chain break under a Postgres error. Document this in the module docstring; AC-10 (re-detection on retry) IS the recovery mechanism.

### §5 — Adversarial test needs the `migrations_role` fixture

S2-03 ships the `migrations_role` with DDL on `events` only — it can `UPDATE events.events` because the trigger blocks `application_role`'s UPDATE, but the trigger is BEFORE-UPDATE and `migrations_role` has the privilege to disable triggers via `ALTER TABLE events.events DISABLE TRIGGER events_immutable_trg` followed by the UPDATE.

The test fixture must:
1. Construct a separate `psycopg_pool.AsyncConnectionPool` whose DSN uses `migrations_role` credentials.
2. Provide it as the `migrations_pool` fixture alongside `application_pool`.
3. Document that `migrations_role` is the **only** legitimate write path for the adversarial test; production code MUST use `application_role`.

`tests/fixtures/events/postgres.py` is the place to add it.

### §6 — `wf_seq` gap detection is a separate path from hash detection

A `wf_seq` gap is structurally different from a hash mismatch:

- A **hash mismatch** means the row's bytes were modified post-insert.
- A **`wf_seq` gap** means a row was DELETED or never inserted but a later row exists.

Both deserve `ChainTamperDetected`, but the `at_seq` differs:
- For a hash mismatch at row n: `at_seq = n` (the corrupted row).
- For a `wf_seq` gap (rows 1, 2, 4 — row 3 missing): `at_seq = prev_wf_seq + 1 = 3` (the missing row).

AC-9's `reason` attribute (`"hash_mismatch"` vs `"wf_seq_gap"`) lets operators triage the failure mode.

### §7 — Not adopted (YAGNI)

- **Resumable iteration after a halt** — not adopted. The chain is broken; resuming past the break would silently skip corrupt data. Halting is the correct response.
- **Background chain-verifier** — not adopted. Phase 9's chain-verify is **at read time only** (per ADR-0003). A background sweeper is a Phase-13 observability concern.
- **`read_workflow_with_paging`** — not adopted. The server-side cursor IS the paging mechanism. Adding offset/limit would risk the operator missing the chain-verify because they paged past the break.
- **Soft-halt that yields events post-break with a flag** — not adopted. Loud halt is the contract; downstream projections rely on iteration termination as the halt signal.
