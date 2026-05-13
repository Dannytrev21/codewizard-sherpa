# Story S2-02 — Extend Phase 5's BLAKE3 audit chain on every `put()`

**Step:** Step 2 — Implement `AuditedSqliteSaver` + per-workflow file + BLAKE3 chain extension
**Status:** Ready
**Effort:** M
**Depends on:** S2-01
**ADRs honored:** ADR-0007, ADR-0006

## Context
Phases 2–5 already maintain a single BLAKE3-chained JSONL audit log under `.codegenie/remediation/<run-id>/audit/<run-id>.jsonl`. Phase 6 extends that same chain — one chain across Phases 2–6 — by appending `checkpoint.write` events from `AuditedSqliteSaver.put()` under a shared `threading.Lock` co-owned with Phase 5's `RetryLedger.record`. The chain head from Phase 5 is read at graph entry, written into `VulnLedger.chain_head`, and re-bound on every checkpoint write. This story implements the writer half; tamper-detection on read is S2-03.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component 3` — chain-extension pseudocode (`digest = blake3(json_bytes + self._read_chain_head()).digest()`); `_append_chain_event`, `_lookup_chain_event`, `_verify_chain` private API.
- **Architecture:** `../phase-arch-design.md §Process view` — sequence showing `SAV->>SAV: blake3(json_bytes || prev_chain_head)` inside the per-node put loop, under the shared lock with `RetryLedger.record`.
- **Architecture:** `../phase-arch-design.md §Edge cases / Harness engineering` — single-writer concurrent test rationale.
- **Phase ADRs:** `../ADRs/0007-blake3-chain-extension-and-tamper-evidence.md` — one chain across Phases 2–6, shared `threading.Lock`, event kinds (`checkpoint.write`, `interrupt.raised`, `resume.applied`, `checkpoint.tamper.detected`), `<run-id>`-keyed (not `<workflow-id>`-keyed) chain file.
- **Phase ADRs:** `../ADRs/0006-audited-sqlite-saver-per-workflow-fsync.md` §Consequences — "shared `threading.Lock` because Phase 5's `RetryLedger.record` also appends".
- **Source design:** `../final-design.md §Component 3 — chain extension subsection`, §Failure modes — "Phase 5 chain head mismatch on Phase 6 startup".
- **High-level plan:** `../High-level-impl.md §Step 2` — Risks specific to this step (Gap 2 — Phase 5 `head_from_phase5()` may not exist publicly; options (a) one-line accessor, (b) parse JSONL directly + ADR).
- **Existing code:** `src/codegenie/gates/retry_ledger.py` — **read first**; locate the chain-file writer, the lock (or absence thereof), and the head-read helper (or absence thereof).
- **Existing code:** `src/codegenie/graph/checkpointer.py` — extend the saver shipped in S2-01.

## Goal
On every `AuditedSqliteSaver.put()`, atomically compute `digest = blake3(canonical_json(checkpoint) + prev_chain_head)` and append a `checkpoint.write` event to Phase 5's existing audit chain under a `threading.Lock` shared with `RetryLedger`, so the chain extends in append order across both writers with no interleaving corruption.

## Acceptance criteria
- [ ] `AuditedSqliteSaver.put()` reads the current chain head, computes `blake3(canonical_json(checkpoint) || prev_head).digest()`, and appends one JSONL event of kind `"checkpoint.write"` with fields `{kind, thread_id, checkpoint_id, prev, digest, at}` to `.codegenie/remediation/<run-id>/audit/<run-id>.jsonl`.
- [ ] The chain append happens **under the same `threading.Lock` object** Phase 5's `RetryLedger.record` uses; verified by `id(checkpointer._chain_lock) == id(retry_ledger.CHAIN_LOCK)` (or whatever symbol the team lands on). The lock is exposed as a process-global so both writers import the same instance.
- [ ] The chain head Phase 6 starts from is seeded via either (a) a public Phase-5 accessor like `RetryLedger.head_from_phase5(run_id)` (preferred, requires a one-line addition to `gates/retry_ledger.py`) or (b) direct JSONL parsing of the last chain event (fallback). The choice taken is documented in a code comment with the rationale.
- [ ] A concurrent-writer test launches one `asyncio.Task` driving `AuditedSqliteSaver.put` 100× and one thread driving `RetryLedger.record` 100× against the same chain file; afterward the JSONL parses cleanly in append order, every event's `prev` field matches the previous event's `digest`, and total event count is exactly 200.
- [ ] On startup, `AuditedSqliteSaver.__init__` reads the persisted Phase 5 chain head; if the head does not match the `prev` of the first `checkpoint.write` event already present for this `(thread_id)` (i.e., the chain seed is inconsistent), it raises `AuditChainCorrupted`. (Tamper of an existing row is S2-03; this AC covers the seed/startup case from ADR-0007.)
- [ ] No LLM, no clock-based randomness, and no app-level `os.fsync` are introduced — chain append is `O_APPEND` under the shared lock; durability of the JSONL is the OS's append-write semantics + WAL on the SQLite side.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Open `src/codegenie/gates/retry_ledger.py` and locate (a) where the chain file is written, (b) whether a `threading.Lock` already exists, (c) whether a `head(run_id)`-like accessor is exposed. Record findings in a short PR-description note.
2. Decide:
   - If a lock exists but is module-private, **promote it to module-public** as `CHAIN_LOCK: Final[threading.Lock]` (or similar). Add one line, nothing else.
   - If no lock exists, surface a one-line `CHAIN_LOCK` and wrap the existing `record` writer in `with CHAIN_LOCK:` — minimal-surgical-change rule.
   - If a head accessor exists, import it. If not, add `def head_from_phase5(run_id: str) -> bytes: ...` returning the digest bytes of the last chain event (a one-line read accessor; per ADR-0007 Consequences).
3. In `src/codegenie/graph/checkpointer.py`, store the imported `CHAIN_LOCK` and the chain-file path on the saver instance.
4. Implement `_read_chain_head() -> bytes` that returns the last event's `digest` (or `VulnLedger.chain_head` if you carry it forward), and `_append_chain_event(kind, **fields) -> None` that takes `CHAIN_LOCK`, opens the JSONL in `"ab"` mode, writes one canonical-JSON line + `b"\n"`, and returns.
5. Override `put()`: compute `json_bytes = canonical_json(checkpoint)`, `digest = blake3(json_bytes + self._read_chain_head()).digest()`, call `super().aput(...)`, then `await asyncio.to_thread(self._append_chain_event, "checkpoint.write", thread_id=..., checkpoint_id=..., digest=digest.hex())`.
6. On `__init__`, after the SQLite connection is up, verify that the Phase 5 chain head, if any prior `checkpoint.write` events exist for this `thread_id`, matches the expected previous; otherwise raise `AuditChainCorrupted` (imported from `graph/hooks.py`).
7. Write `tests/integration/test_chain_single_writer.py` exercising the concurrent-writer AC.
8. Write `tests/integration/test_chain_seed_mismatch.py` covering the constructor-time `AuditChainCorrupted` case.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/integration/test_chain_single_writer.py`

```python
import asyncio
import json
import threading
from pathlib import Path

import pytest

from codegenie.gates.retry_ledger import CHAIN_LOCK, RetryLedger
from codegenie.graph.checkpointer import make_checkpointer
from tests.graph.fixtures.ledgers import build_minimal_ledger


@pytest.mark.asyncio
async def test_concurrent_chain_writers_produce_well_formed_chain(tmp_path: Path) -> None:
    """Phase 5's RetryLedger.record and Phase 6's AuditedSqliteSaver.put both
    extend the same BLAKE3 chain file. They MUST acquire the same threading.Lock
    instance (ADR-0007). Verify by driving 100 events from each writer against the
    same chain file and asserting (1) total count == 200, (2) prev->digest forms
    an unbroken hash chain, (3) no interleaving corruption.

    Why this matters: a forgotten lock surfaces here, not in production.
    """
    run_id = "run-xyz"
    chain_dir = tmp_path / "remediation" / run_id / "audit"
    chain_dir.mkdir(parents=True)
    chain_file = chain_dir / f"{run_id}.jsonl"

    saver = make_checkpointer("workflow_a", base=tmp_path / "loop" / "checkpoints", chain_file=chain_file)
    retry_ledger = RetryLedger(run_id=run_id, audit_root=tmp_path / "remediation")
    config = {"configurable": {"thread_id": "workflow_a"}}

    # Both writers must observe the SAME lock object.
    assert saver._chain_lock is CHAIN_LOCK, "shared chain lock not co-owned (ADR-0007)"

    async def hammer_saver() -> None:
        for i in range(100):
            checkpoint = {"v": 1, "ts": f"2026-05-12T00:00:{i:02d}Z",
                          "channel_values": {"__root__": build_minimal_ledger().model_dump(mode="json")}}
            await saver.aput(config, checkpoint, {}, {})

    def hammer_retry_ledger() -> None:
        for i in range(100):
            retry_ledger.record_test_event(i)  # synthetic event for parity

    thread = threading.Thread(target=hammer_retry_ledger)
    thread.start()
    await hammer_saver()
    thread.join()

    events = [json.loads(line) for line in chain_file.read_text().splitlines() if line.strip()]
    assert len(events) == 200

    # Hash chain integrity: each event's prev MUST equal the previous event's digest.
    for prev, curr in zip(events, events[1:]):
        assert curr["prev"] == prev["digest"], (
            f"chain break at index {events.index(curr)}: prev={curr['prev']!r} vs prior digest={prev['digest']!r}"
        )
```

### Green — make it pass
- Promote (or create) `CHAIN_LOCK` in `src/codegenie/gates/retry_ledger.py` as a module-public `Final[threading.Lock]`.
- Wire `AuditedSqliteSaver._chain_lock = CHAIN_LOCK` in `__init__`.
- Override `aput` to take the lock around the JSONL append (run in `asyncio.to_thread` to keep the async signature pure).
- Optionally accept `chain_file` kwarg in `make_checkpointer` so tests can isolate per-`tmp_path` (production path derives from `run_id`).

### Refactor — clean up
- Make `_append_chain_event(kind, **fields)` generic so S2-03 (tamper.detected) and S4-08 (interrupt.raised / resume.applied) reuse it.
- Add a `_verify_chain()` method that walks the JSONL and re-checks `prev → digest` continuity; expose it as a private API the verify CLI can call later.
- Add a unit test confirming `blake3(canonical_json(checkpoint) + prev)` matches a hand-computed digest for one known checkpoint.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/graph/checkpointer.py` | Override `aput` with chain extension; expose `_chain_lock`, `_append_chain_event`, `_read_chain_head`, `_verify_chain`. |
| `src/codegenie/gates/retry_ledger.py` | Promote `CHAIN_LOCK` to module-public; add `head_from_phase5(run_id)` if absent. **Surgical, one-or-two-line change.** |
| `tests/integration/test_chain_single_writer.py` | New — concurrent-writer canary. |
| `tests/integration/test_chain_seed_mismatch.py` | New — startup `AuditChainCorrupted` when seed disagrees. |
| `tests/graph/fixtures/ledgers.py` | Extend if needed for synthetic chain events. |

## Out of scope
- Tamper-detection on `aget_tuple` for a mutated SQLite row (S2-03).
- World-readable / schema-drift refusals (S2-03).
- Chain events `interrupt.raised`, `resume.applied` from `await_human` (S4-08).
- Replay-byte-identical canary (S2-04 smoke; S8-01 full).
- Authentication of who appended an event (deferred to Phase 11 — ADR-0008).

## Notes for the implementer
- **Read Phase 5 first.** If `_run_one_attempt`'s seam is interleaved with the chain writer, surface that loudly here — do not paper over with a private import. Per Gap 2 in the arch design, the fallback (option b) is JSONL-parsing the head directly, paired with a short Phase-6 ADR documenting the choice.
- The lock must be the same Python `threading.Lock` instance. A common mistake: each writer constructs its own `threading.Lock()`. The `is` check in the test (`saver._chain_lock is CHAIN_LOCK`) catches it.
- Run the JSONL append inside `asyncio.to_thread(...)` — the lock is sync but `aput` is async; mixing them naively can deadlock the event loop.
- `O_APPEND` writes on POSIX are atomic only up to `PIPE_BUF`; canonical chain events are small (well under 4 KiB) so single-line atomicity holds. Add a comment to that effect; do not rely on flock.
- The digest computation order is `prev_head || canonical_json(checkpoint)` — match the ADR pseudocode exactly; reversing the operands silently breaks tamper detection (S2-03).
- Per the arch design, do not stash `prev_chain_head` redundantly in two places. The truth is the last chain event's `digest`; `VulnLedger.chain_head` is a convenience cache.
