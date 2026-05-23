# Story S3-03 — Critical-event synchronous-flush bypass

**Step:** Step 3 — Canonical event log, BlobRef store, and activity-boundary sanitizer
**Status:** Ready
**Effort:** S
**Depends on:** S3-02 (`EventBatchWriter` + flush triggers); S1-03 transitively (`@critical_event` registry + the five marked variants)
**ADRs honored:** ADR-0006 (`@critical_event` synchronous-flush vocabulary — **load-bearing**), ADR-0003 (chain preservation across the sync path), production ADR-0034

## Context

S3-02 ships the batched path; its critical-event awareness fires a flush trigger but does not change the caller's contract — `enqueue` still returns immediately. **This story** ships the **synchronous-flush bypass**: an append whose event is `@critical_event`-marked **bypasses the batcher entirely** and goes through a single-row `INSERT ... RETURNING wf_seq` that the caller awaits. The caller does not return until the row is durably committed to Postgres.

The five `@critical_event` variants (`WorkflowTerminated`, `TrustGateFailed`, `MergeOutcome`, `BudgetExhausted`, `ChainTamperDetected`) cannot afford "batched, durable some-time-later" semantics. A `MergeOutcome` that doesn't reach Postgres means a PR was merged but the audit log has no record (ADR-0006 §Context). A `BudgetExhausted` not durable means the workflow looks under-budget on resume.

The load-bearing risk (ADR-0006 §Tradeoffs row 4, also `phase-arch-design.md §Implementation-level risks #3`) is the **double-write anti-pattern**: an activity emits a critical event, the sync-flush succeeds, and Temporal then retries the activity for some unrelated reason (e.g., heartbeat-timeout) — the retried activity tries to emit the same event again and gets a `UniqueViolation` on `event_id`. This story asserts the activity contract for that path: critical-event emits are idempotent because `event_id` is the PRIMARY KEY, and the second emit must surface a typed error the retry policy handles (not loop forever).

This story also ships the **critical-event vocabulary fence** (`tests/fence/test_critical_event_vocabulary.py`) — asserts the registry contains exactly the five names. ADR-0006 names this as a golden — adding a sixth variant requires updating the golden, forcing a code-review conversation about the cost.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C5 — EventBatchWriter` (the "synchronous-flush bypass" paragraph; "synchronous-flush failure propagates to the activity caller; Temporal retries per the activity's `RetryPolicy`").
  - `../phase-arch-design.md §Data model — `@critical_event` decorator` (the five-variant list).
  - `../phase-arch-design.md §Design patterns applied #8` (Open/Closed via decorator-populated registry).
  - `../phase-arch-design.md §Goals G7` (audit completeness — "the 5 `@critical_event` variants sync-flush, others batched").
- **Phase ADRs:**
  - `../ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — **load-bearing for this story.** The five-name vocabulary, the Open/Closed via decorator-registry pattern, the fence-test golden, the anti-double-write tradeoff.
  - `../ADRs/0003-per-workflow-blake3-prev-hash-chain.md` — the sync path must hash against the same per-workflow LRU as the batched path; chain integrity is invariant across paths.
- **Existing code:**
  - `src/codegenie/events/log.py` (S3-01 / S3-02) — `EventLog.append` (sync path already exists), `EventBatchWriter.enqueue` (batched path).
  - `src/codegenie/events/payloads.py` (S1-02 + S1-03) — `_CRITICAL_EVENTS: Final[set[str]]` is populated at import; the five `@critical_event`-marked variants.
  - `src/codegenie/types/identifiers.py` — `WorkflowId`, `EventId`.

## Goal

Ship the `EventBatchWriter.enqueue` dispatch that routes `@critical_event` variants to `EventLog.append` (single-row, synchronous) and non-critical variants to the batched queue, **without changing the caller-side surface** (`enqueue` still returns `EventId`). Ship the fence test that pins the vocabulary to exactly the five known names. Document and test the double-write-on-retry contract: a re-emit of the same critical event raises a typed error the activity's `RetryPolicy.non_retryable` handles.

## Acceptance criteria

- [ ] **AC-1 — `EventBatchWriter.enqueue` dispatch.** When `type(event).__name__ in _CRITICAL_EVENTS`, `enqueue` calls `await self._log.append(event, capability=capability)` (the S3-01 single-row path) and returns its result. The event is NOT added to the buffer; the flush task is not awakened; the caller blocks until durably committed.
- [ ] **AC-2 — Caller-side surface unchanged.** From the caller's perspective, `enqueue(critical_event, capability=cap)` and `enqueue(non_critical_event, capability=cap)` have the same type signature returning `EventId`. The difference is **runtime latency**: the critical variant blocks ~10 ms (one INSERT round-trip); the non-critical returns in < 1 ms.
- [ ] **AC-3 — All five critical variants flow through the sync path.** Five integration tests (one per variant: `WorkflowTerminated`, `TrustGateFailed`, `MergeOutcome`, `BudgetExhausted`, `ChainTamperDetected`) construct an event, `enqueue` it, and assert (a) the row is in `events.events` before `enqueue` returns (verify by a synchronous SELECT immediately after); (b) the batcher's queue is empty (`writer._queue.qsize() == 0`).
- [ ] **AC-4 — Latency budget for sync flush.** Each sync flush commits with p95 ≤ 15 ms (per `High-level-impl.md §Step 3 done-criteria`). Integration test: 100 critical-event emits sequentially against testcontainers PG; assert p95 ≤ 15 ms. This is a sanity-floor assertion, not the formal G6 bench (S3-07).
- [ ] **AC-5 — Chain integrity is preserved across mixed batched + sync emits.** Sequence: enqueue 5 non-critical → 1 critical → 5 non-critical, all for the same workflow. Read the chain back; assert every `wf_seq` is dense (1..11) and `row_hash[n] == BLAKE3(row_hash[n-1] || canonical_payload[n])` for all n. **The critical-emit must not "skip the line" and leave a chain gap.** Implementer note in §3 below.
- [ ] **AC-6 — Sync flush bypasses the queue entirely.** Patch the batcher's flush task to NEVER fire (set `flush_interval_ms = 10_000_000`); enqueue 1 critical event; assert it's in Postgres within 100 ms (no dependence on the flush task). The bypass route does not touch the queue or the flush task; it goes straight to `EventLog.append`.
- [ ] **AC-7 — Double-write-on-retry surfaces a typed error.** Manually emit the same critical event twice (same `event_id`); the second emit raises `psycopg.errors.UniqueViolation` (or a wrapper `EventAlreadyAppended` if implementer prefers a typed surface). Test asserts the second `enqueue` raises this error AND no second row is committed.
- [ ] **AC-8 — Critical-event vocabulary fence.** `tests/fence/test_critical_event_vocabulary.py` asserts `_CRITICAL_EVENTS == frozenset({"WorkflowTerminated", "TrustGateFailed", "MergeOutcome", "BudgetExhausted", "ChainTamperDetected"})` — exact-set equality. Adding a sixth name fails the test; the failure message instructs the contributor to update both the registry and this golden.
- [ ] **AC-9 — Decorator collision raises at import.** Applying `@critical_event` twice to the same variant raises `TypeError` at import time (precedent: `@register_probe`'s duplicate-name check). Test asserts a deliberate double-decoration violates loud.
- [ ] **AC-10 — Empty buffer at sync-flush time is fine.** A sync emit when the batcher's buffer is empty proceeds normally (no batched flush triggered; no race condition). Test: stop the flush task, empty the queue, emit a critical event, assert it lands.
- [ ] **AC-11 — Non-empty buffer at sync-flush time does NOT trigger a batched drain.** A sync emit when the buffer holds 5 non-critical events leaves those 5 in the buffer (the next batched flush picks them up). The sync path does NOT preempt or steal the batch. Test asserts buffer state pre- and post-sync-emit.
- [ ] **AC-12 — `mypy --strict` + lint clean** on the modified `log.py` and the new fence test.

## Implementation outline

1. **Modify `EventBatchWriter.enqueue` (the only structural change).** First line of `enqueue` after the capability check:
    ```python
    if type(event).__name__ in _CRITICAL_EVENTS:
        return await self._log.append(event, capability=capability)
    ```
    The `await` is what makes the caller block until durable. The S3-01 `append` already does INSERT + commit + LRU update; no new logic.
2. **Write the red test for AC-1 first.** A test that patches `EventLog.append` to record its calls and asserts a `MergeOutcome` `enqueue` calls `append` exactly once and the queue is empty.
3. **`@critical_event` collision check (AC-9).** Update `critical_event(cls)` in `codegenie.events.payloads`:
    ```python
    def critical_event(cls: type[T]) -> type[T]:
        if cls.__name__ in _CRITICAL_EVENTS:
            raise TypeError(
                f"@critical_event applied twice to {cls.__name__!r}; "
                f"this class is already in the registry"
            )
        _CRITICAL_EVENTS.add(cls.__name__)
        return cls
    ```
    Note: S1-03 may have already implemented this. If so, this story just verifies the test exists and is wired.
4. **Fence test (AC-8).** `tests/fence/test_critical_event_vocabulary.py`:
    ```python
    EXPECTED = frozenset({"WorkflowTerminated", "TrustGateFailed",
                          "MergeOutcome", "BudgetExhausted", "ChainTamperDetected"})

    def test_critical_event_vocabulary_is_exactly_five() -> None:
        """ADR-0006 — the vocabulary is a closed five-name set in Phase 9.
        Adding a sixth requires (a) updating EXPECTED here, (b) writing an ADR
        amendment justifying the cost, (c) a code-review conversation."""
        from codegenie.events.payloads import _CRITICAL_EVENTS
        assert frozenset(_CRITICAL_EVENTS) == EXPECTED
    ```
5. **AC-5 chain-integrity test (the load-bearing one).** Mixed batched + sync sequence; assert chain verifies. The implementation key: the sync path and the batched path must both consult and update **the same** `_chain_heads` LRU on `EventLog`. The sync path does this via `EventLog.append`; the batched path does this in `flush`. Verify under a `pytest.mark.asyncio` that both update under the same `asyncio.Lock` (the lock S3-02 added).
6. **Double-write contract (AC-7).** Choose one of two paths:
    - **Path A — surface raw `psycopg.errors.UniqueViolation`.** Simplest. The activity's `RetryPolicy.non_retryable` lists `UniqueViolation`. Document in module docstring.
    - **Path B — wrap in `EventAlreadyAppended(EventId)` typed exception.** More auditable. Activity's `RetryPolicy.non_retryable` lists this. Path A is sufficient for Phase 9; Path B can be a follow-up.
    
    Recommend Path A for this story (one fewer error type to maintain). The test asserts `psycopg.errors.UniqueViolation` (or its async-driver equivalent) surfaces.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/integration/events/test_sync_flush_bypass.py`

Test intent: A `MergeOutcome` enqueued into a writer with a stopped flush task must reach Postgres before `enqueue` returns. **If the batcher accidentally buffers the critical event**, the test will fail because the row will not be in the table when the post-enqueue SELECT runs.

```python
# Test outline only.
async def test_merge_outcome_lands_synchronously(pg_pool, fresh_events_schema):
    """AC-1, AC-3, AC-6 — critical event bypasses queue entirely.
    Stop the flush task to prove the sync path is independent of it."""
    log = EventLog(pool=pg_pool)
    writer = EventBatchWriter(log=log, flush_interval_ms=10_000_000)  # essentially never
    await writer.start()

    event = MergeOutcome(
        event_id=EventId(uuid4().hex),
        workflow_id=WorkflowId("wf-merge-01"),
        timestamp=datetime.now(UTC),
        correlation_id=None,
        wf_seq=None,
        kind="merge_outcome",
        pr_url=PrUrl("https://github.com/x/y/pull/1"),
        decision="merged",
        reviewer=GitHubUsername("alice"),
    )
    cap = _full_capability_for("system")

    event_id = await writer.enqueue(event, capability=cap)

    # Belt: queue must be empty (sync emit bypasses it).
    assert writer._queue.qsize() == 0

    # And the row is durably committed BEFORE enqueue returned.
    rows = await _fetch(pg_pool, "SELECT * FROM events.events WHERE event_id = %s", event_id)
    assert len(rows) == 1
    assert rows[0].kind == "merge_outcome"

    await writer.stop()
```

Why it fails: As of S3-02 alone, the writer buffers all events including critical — the SELECT returns 0 rows.

### Green — minimal pass

- Add the two-line dispatch to `EventBatchWriter.enqueue`.
- Red test passes.

### Required follow-on tests (one per AC)

- **`test_each_critical_variant_lands_synchronously`** (AC-3) — parametrized over the five variants; each lands in `events.events` before `enqueue` returns.
- **`test_sync_flush_p95_under_15ms`** (AC-4) — 100 sync emits sequentially; p95 wall-clock < 15 ms. Sanity floor; S3-07 owns the formal G6 bench.
- **`test_mixed_batched_sync_chain_integrity`** (AC-5) — 5 batched, 1 sync, 5 batched same-workflow; full chain verifies. **Read this test as the canonical "sync path doesn't corrupt the chain" assertion.**
- **`test_double_emit_raises_unique_violation`** (AC-7) — emit same `event_id` twice; second raises.
- **`test_critical_event_vocabulary_is_exactly_five`** (AC-8) — the fence test.
- **`test_critical_event_double_decoration_raises`** (AC-9) — `TypeError` on double-`@critical_event` (test by dynamically creating a class and applying the decorator).
- **`test_empty_buffer_sync_emit_works`** (AC-10) — sanity.
- **`test_non_empty_buffer_sync_emit_does_not_steal_batch`** (AC-11) — buffer state unchanged after sync emit.

### Refactor

- Module docstring on `log.py` adds a "Critical-event sync bypass" subsection with the dispatch one-liner and ADR-0006 citation.
- Inline comment at the dispatch site references `tests/fence/test_critical_event_vocabulary.py` so a future reader sees the golden.
- The fence test's `EXPECTED` set is the single source of truth; the test failure message includes the diff between `_CRITICAL_EVENTS` and `EXPECTED` for fast remediation.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/events/log.py` | Add the two-line dispatch in `EventBatchWriter.enqueue`. |
| `src/codegenie/events/payloads.py` | Verify (or add) the collision check inside `critical_event(cls)`. |
| `tests/integration/events/test_sync_flush_bypass.py` | All sync-bypass integration tests. |
| `tests/fence/test_critical_event_vocabulary.py` | The five-name fence golden. |
| `tests/unit/events/test_critical_event_decorator.py` | `TypeError` on double-decoration (AC-9). |

## Out of scope

- **`read_workflow`** — S3-04.
- **`BlobRef`** — S3-05.
- **Sanitizer** — S3-06.
- **Formal G6 bench** — S3-07.
- **A "redundant batched write" of critical events** — explicitly out per ADR-0006 §Consequences "current design does not"; an alternative pattern for observability is an open question deferred to implementation.
- **`EventAlreadyAppended` typed wrapper** — not adopted; raw `UniqueViolation` is sufficient. If a future phase finds the raw error too brittle to handle in activity retry policies, the wrapper can land additively without breaking any existing call site.
- **Promoting a sixth event to critical** — requires an ADR amendment and a golden update; out of scope for this story.

## Notes for the implementer

### §1 — The dispatch is two lines

The entire structural change to `EventBatchWriter.enqueue`:

```python
async def enqueue(self, event, *, capability):
    if event.kind not in capability.allowed_kinds:  # AC-3 / S3-01
        raise EventCapabilityViolation(...)
    if type(event).__name__ in _CRITICAL_EVENTS:    # ← THIS STORY
        return await self._log.append(event, capability=capability)
    # ... existing batched path ...
```

Resist adding a `is_critical` boolean field to the event payload — the registry-based check is the ADR-0006 pattern (Open/Closed via decorator-populated registry). A boolean field would force every variant to declare its criticality at the data layer, which is the wrong locality.

### §2 — `_CRITICAL_EVENTS` membership is by `type(event).__name__`, not isinstance

The registry stores class **names**, not classes. This is intentional (ADR-0006 §Consequences) — it survives refactors that move the variant between modules without forcing the registry to track imports. The check is `type(event).__name__ in _CRITICAL_EVENTS`.

`type(event)` (not `event.__class__`) is the canonical Python idiom for "the actual runtime class" (handles `__class__`-overridden descriptors). Both work; pick one and be consistent.

### §3 — Chain integrity across mixed paths

AC-5 is the load-bearing chain-integrity assertion. The mechanism:

1. The sync path goes through `EventLog.append` → INSERT with `wf_seq = (SELECT MAX(wf_seq) + 1 ...)` → updates `_chain_heads[workflow_id]`.
2. The batched path drains the buffer → for each partition, reads chain head from `_chain_heads` (or SELECTs on miss) → COPYs with client-side `wf_seq` increment → updates `_chain_heads`.

Both paths read and update **the same** LRU under the same async lock. The sync path's INSERT commits before its `_chain_heads` update; the batched path's COPY commits before its `_chain_heads` update. So if a batched flush starts WHILE a sync emit is in-flight, the batched flush sees the post-sync chain head (correct) OR the pre-sync chain head (incorrect — the batched chain would skip the sync event's `row_hash`).

**Resolution:** the async lock on `_chain_heads` access is held across the whole `(read-head → write-rows → update-head)` cycle for both paths. The batched flush's transaction holds the lock from its `MAX(wf_seq)` read through its COPY through its `_chain_heads` update. The sync `append` does the same. Contention is brief (10-50 ms) and bounded.

If contention becomes a perf issue, partition the lock by `workflow_id` (one lock per workflow's chain-head entry). Not in scope here; the single global lock is fine at G6 throughput.

### §4 — Double-write on retry: explain the `RetryPolicy` interaction

The S4-01 `_POLICIES` table will list `psycopg.errors.UniqueViolation` (or a wrapper) in `non_retryable` for activities that emit critical events. The contract chain:

1. Activity emits `MergeOutcome` → sync flush → COMMIT.
2. Activity returns successfully.
3. Temporal records the activity result.
4. (Hypothetical) some upstream Temporal-level retry fires (heartbeat-timeout from a stuck worker, say) → activity re-runs.
5. Re-running activity emits the same `MergeOutcome` with the same `event_id` (idempotent factory).
6. INSERT raises `UniqueViolation`.
7. Activity's `RetryPolicy.non_retryable` catches; activity fails with a typed error visible in `temporal-ui`.

In practice, the `(repo, attempt_id)` idempotency at the activity layer (S4-04) means the activity sees the prior PR exists and short-circuits before emitting a duplicate `MergeOutcome` at all. But the chain-level defense (`UniqueViolation`) is the belt against the suspenders.

### §5 — Latency budget — keep an eye on the LRU

The 15 ms p95 budget is for the synchronous INSERT round-trip. The LRU update is microseconds; the dominant cost is the `INSERT ... RETURNING wf_seq` itself (network RTT + Postgres commit fsync). On localhost testcontainers, expect 5-8 ms; under CI's shared infra, expect 10-15 ms. If S3-07's bench surfaces > 15 ms, two levers:

1. Reduce the sub-select cost: cache `MAX(wf_seq)` in the LRU and trust it; rely on the `events_wf_seq_uniq` UNIQUE INDEX for integrity (a stale LRU under cross-worker contention would raise `UniqueViolation`, which is the retry signal).
2. Disable Postgres `synchronous_commit = on` for the test (NOT for production) — but this hides a real latency.

Lever 1 is the additive optimization; do not pre-pay it here.

### §6 — The fence test is a culture artifact

`tests/fence/test_critical_event_vocabulary.py` is **the** way the system communicates "promoting an event to critical is a decision, not an accident". When the test fails because a contributor added `@critical_event`, the failure message must say so loudly:

```
AssertionError: _CRITICAL_EVENTS has {NewEventName} not in EXPECTED golden.
This decoration promotes an event to synchronous-flush, which costs ~10 ms per emit.
If this is intentional:
  1. Update EXPECTED in this test file to include {NewEventName}.
  2. Write an ADR amendment to ADR-0006 explaining why this event cannot afford batched semantics.
  3. Mention the throughput cost in the PR description.
If this is unintentional, remove the @critical_event decoration.
```

The message itself is part of the contract.

### §7 — Not adopted (YAGNI)

- **A `force_sync=True` kwarg on `enqueue`** — not adopted. The decision of "sync vs batched" is encoded in the *event type*, not the call site. A kwarg would invite contributors to upgrade non-critical events to sync ad-hoc without going through the ADR amendment process.
- **Distributed lock for cross-worker chain-head coordination** — not adopted. Temporal sticky-task affinity makes cross-worker writes for one workflow rare; the `events_wf_seq_uniq` UNIQUE INDEX is the integrity backstop for the rare case.
- **Telemetry on sync-flush latency** — Phase 13 lands OTel; for now, the structured-log entry at the end of `EventLog.append` (with `wall_clock_ms`) is sufficient.
