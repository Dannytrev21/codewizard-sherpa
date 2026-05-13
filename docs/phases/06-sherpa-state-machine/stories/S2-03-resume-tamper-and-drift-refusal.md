# Story S2-03 — Refuse resume on tamper / world-readable / schema drift / chain mismatch

**Step:** Step 2 — Implement `AuditedSqliteSaver` + per-workflow file + BLAKE3 chain extension
**Status:** Ready
**Effort:** M
**Depends on:** S2-02
**ADRs honored:** ADR-0007, ADR-0006, ADR-0005

## Context
With S2-01 round-tripping cleanly and S2-02 extending Phase 5's chain on write, this story closes the tamper-evidence loop on read. Four adversarial scenarios must each raise a typed exception and refuse to resume: a mutated SQLite row (`CheckpointTampered`), a world-readable DB file (`CheckpointerInsecure`), a `schema_version` mismatch in the persisted blob (`SchemaDrift`), and a corrupted Phase-5 chain head at constructor time (`AuditChainCorrupted`). On detected tamper, the chain itself gets a `checkpoint.tamper.detected` event so incident response has a clean timeline.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component 3` — pseudocode for `aget_tuple`: `actual = blake3(canonical_json(tup.checkpoint) + self._prev_chain_head_for(tup)).digest()`; if `actual != recorded`, raise `CheckpointTampered`.
- **Architecture:** `../phase-arch-design.md §Failure modes` — schema drift, world-readable, chain head mismatch each map to typed exceptions and CLI exit code 13.
- **Architecture:** `../phase-arch-design.md §CLI design` — exit code 13 = `CheckpointTampered | CheckpointerInsecure | SchemaDrift | AuditChainCorrupted`.
- **Phase ADRs:** `../ADRs/0007-blake3-chain-extension-and-tamper-evidence.md` — recomputes digest on `aget_tuple`; mismatch raises `CheckpointTampered`; the `checkpoint.tamper.detected` event is emitted under the shared chain lock.
- **Phase ADRs:** `../ADRs/0006-audited-sqlite-saver-per-workflow-fsync.md` — `0600` mode is enforceable at startup via `_enforce_file_mode_0600`.
- **Phase ADRs:** `../ADRs/0005-static-schema-version-literal-pin.md` — `schema_version: Literal["v0.6.0"]` mismatch on resume raises `SchemaDrift`; CI fixtures under `tests/fixtures/checkpoints/v0.6.0/` are the canary.
- **Source design:** `../final-design.md §Failure modes` — "Phase 5 chain head mismatch on Phase 6 startup" → `AuditChainCorrupted`.
- **High-level plan:** `../High-level-impl.md §Step 2` — done criteria items 2–5.
- **Existing code:** `src/codegenie/graph/hooks.py` (from S1-04) — the typed exception classes.
- **Existing code:** `src/codegenie/graph/checkpointer.py` (from S2-01/S2-02) — extends `aget_tuple` with verification.

## Goal
Make `AuditedSqliteSaver` refuse to resume on any of the four tamper/drift conditions, each with the typed exception named in ADR-0007 / ADR-0006 / ADR-0005, and emit a `checkpoint.tamper.detected` chain event when SQLite-row tamper is observed.

## Acceptance criteria
- [ ] `aget_tuple()` recomputes `actual_digest = blake3(canonical_json(persisted_checkpoint) + prev_chain_head_for_this_checkpoint).digest()` and compares it to the chain's recorded `digest` for this `(thread_id, checkpoint_id)`; on mismatch raises `CheckpointTampered` **and** appends one `checkpoint.tamper.detected` event to the chain (same shared lock from S2-02) before raising.
- [ ] On construction, if the DB file's mode is anything other than `0o600`, `_enforce_file_mode_0600` raises `CheckpointerInsecure` with a message containing the offending octal mode and a remediation hint (`chmod 600 <path>`). Tested by `chmod 0o644` on a freshly-created DB.
- [ ] On `aget_tuple()`, if the persisted blob's `schema_version` field does not equal the current code's `VulnLedger` literal (`"v0.6.0"`), raise `SchemaDrift` carrying both the persisted and expected version strings. Tested by mutating the row's JSON payload.
- [ ] On construction, if the Phase-5 chain head read at startup does not match the `prev` of the first `checkpoint.write` event for this `thread_id` (when any exist), raise `AuditChainCorrupted`. Tested by corrupting the Phase-5 chain file's last digest before constructing the saver.
- [ ] All four exceptions inherit from a common base (e.g., `CheckpointerError`) and are importable from `codegenie.graph.hooks`; CLI exit code 13 is the test contract for "any of these four".
- [ ] The `checkpoint.tamper.detected` event includes `{thread_id, checkpoint_id, expected_digest, observed_digest, at}` and extends the chain (its own `prev → digest` link is well-formed; verified by re-running the S2-02 chain-walk).
- [ ] Recompute uses the **same** `canonical_json` from S2-01 — the serializer is single-sourced; a separate serializer would silently break tamper detection.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Confirm `CheckpointTampered`, `CheckpointerInsecure`, `SchemaDrift`, `AuditChainCorrupted` all exist in `src/codegenie/graph/hooks.py` (delivered by S1-04). If any are missing, surface as a story-precondition failure — do not add them here.
2. Add a private base `class CheckpointerError(Exception): ...` if not already present, and re-parent the four. The CLI maps any `CheckpointerError` to exit code 13.
3. Override `aget_tuple()` in `src/codegenie/graph/checkpointer.py`:
   - Call the parent to get the raw `(config, checkpoint, metadata, pending_writes)` tuple.
   - Read the persisted `schema_version` from `checkpoint["channel_values"]["__root__"]["schema_version"]`; if not `"v0.6.0"`, raise `SchemaDrift` *before* attempting BLAKE3 verification (drift wins over tamper).
   - Look up the recorded `digest` for `(thread_id, checkpoint_id)` via `_lookup_chain_event`.
   - Compute `actual = blake3(canonical_json(checkpoint) + prev_for_that_event).digest()`.
   - If `actual != recorded`: append `checkpoint.tamper.detected` event via `_append_chain_event` (under `CHAIN_LOCK`), then `raise CheckpointTampered(thread_id, checkpoint_id, expected=recorded.hex(), observed=actual.hex())`.
4. Extend `__init__` to check Phase-5 chain head consistency against the first `checkpoint.write` event for this `thread_id`; raise `AuditChainCorrupted` on mismatch.
5. Add four adversarial tests, one per failure mode. Each must construct a clean DB + chain, mutate exactly the relevant byte/field, then assert the right exception.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/adversarial/test_checkpoint_refusals.py`

```python
import json
import sqlite3
import stat
from pathlib import Path

import pytest

from codegenie.graph.checkpointer import make_checkpointer
from codegenie.graph.hooks import (
    AuditChainCorrupted,
    CheckpointTampered,
    CheckpointerError,
    CheckpointerInsecure,
    SchemaDrift,
)
from tests.graph.fixtures.ledgers import build_minimal_ledger


@pytest.mark.asyncio
async def test_row_tamper_raises_checkpoint_tampered_and_emits_chain_event(tmp_path: Path) -> None:
    """A mutated SQLite row MUST be detected on aget_tuple; the chain MUST grow a
    checkpoint.tamper.detected event with the observed-vs-expected digests.

    Why this matters: ADR-0007's whole point — offline DB tamper is the threat
    model that motivates the chain. If we don't both raise and record, incident
    response has neither a halt nor a timeline.
    """
    saver = make_checkpointer("wf_t", base=tmp_path)
    config = {"configurable": {"thread_id": "wf_t"}}
    ledger = build_minimal_ledger()
    checkpoint = {"v": 1, "ts": "2026-05-12T00:00:00Z",
                  "channel_values": {"__root__": ledger.model_dump(mode="json")}}
    await saver.aput(config, checkpoint, {}, {})
    await saver.aclose()

    # Tamper: open the DB, mutate one byte of the serialized checkpoint blob.
    db_path = tmp_path / "wf_t.sqlite3"
    conn = sqlite3.connect(str(db_path))
    try:
        # Locate the checkpoints row (table name comes from AsyncSqliteSaver schema).
        row = conn.execute("SELECT rowid, checkpoint FROM checkpoints LIMIT 1").fetchone()
        rowid, blob = row[0], row[1]
        # Flip exactly one byte in the middle of the blob.
        idx = len(blob) // 2
        mutated = blob[:idx] + bytes([blob[idx] ^ 0x01]) + blob[idx + 1:]
        conn.execute("UPDATE checkpoints SET checkpoint = ? WHERE rowid = ?", (mutated, rowid))
        conn.commit()
    finally:
        conn.close()

    saver2 = make_checkpointer("wf_t", base=tmp_path)
    with pytest.raises(CheckpointTampered):
        await saver2.aget_tuple(config)

    # Chain must contain a checkpoint.tamper.detected event.
    chain_events = saver2._read_chain_events()
    kinds = [e["kind"] for e in chain_events]
    assert "checkpoint.tamper.detected" in kinds


@pytest.mark.asyncio
async def test_world_readable_db_refuses_construction(tmp_path: Path) -> None:
    """ADR-0006: a 0644 DB is insecure; constructor MUST raise."""
    saver = make_checkpointer("wf_w", base=tmp_path)
    await saver.aput({"configurable": {"thread_id": "wf_w"}},
                     {"v": 1, "ts": "z", "channel_values": {"__root__": build_minimal_ledger().model_dump(mode="json")}},
                     {}, {})
    await saver.aclose()
    db = tmp_path / "wf_w.sqlite3"
    db.chmod(0o644)
    with pytest.raises(CheckpointerInsecure) as exc:
        make_checkpointer("wf_w", base=tmp_path)
    assert "chmod 600" in str(exc.value).lower() or "0o600" in str(exc.value)


@pytest.mark.asyncio
async def test_schema_version_mutation_raises_schema_drift(tmp_path: Path) -> None:
    """ADR-0005: persisted schema_version != current literal MUST refuse to resume."""
    saver = make_checkpointer("wf_s", base=tmp_path)
    config = {"configurable": {"thread_id": "wf_s"}}
    await saver.aput(config,
                     {"v": 1, "ts": "z", "channel_values": {"__root__": build_minimal_ledger().model_dump(mode="json")}},
                     {}, {})
    await saver.aclose()

    # Mutate persisted blob to claim it's v0.5.9.
    db_path = tmp_path / "wf_s.sqlite3"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT rowid, checkpoint FROM checkpoints LIMIT 1").fetchone()
        rowid, blob = row[0], row[1]
        # Implementations may store JSON-as-bytes or msgpack; here we assume JSON.
        as_text = blob.decode("utf-8")
        mutated = as_text.replace('"schema_version":"v0.6.0"', '"schema_version":"v0.5.9"').encode("utf-8")
        # NB: also need to repair length headers if the saver's encoder added any.
        conn.execute("UPDATE checkpoints SET checkpoint = ? WHERE rowid = ?", (mutated, rowid))
        conn.commit()
    finally:
        conn.close()

    saver2 = make_checkpointer("wf_s", base=tmp_path)
    with pytest.raises(SchemaDrift) as exc:
        await saver2.aget_tuple(config)
    assert "v0.5.9" in str(exc.value) and "v0.6.0" in str(exc.value)


@pytest.mark.asyncio
async def test_phase5_chain_seed_corruption_raises_audit_chain_corrupted(tmp_path: Path) -> None:
    """ADR-0007: a corrupted Phase-5 chain head at constructor time is fatal."""
    # Pre-seed the Phase-5 chain file with an inconsistent prev->digest pair, then
    # try to construct a saver that references it.
    run_id = "run-corrupt"
    chain_dir = tmp_path / "remediation" / run_id / "audit"
    chain_dir.mkdir(parents=True)
    chain_file = chain_dir / f"{run_id}.jsonl"
    chain_file.write_text(
        json.dumps({"kind": "attempt.recorded", "prev": "00" * 32, "digest": "aa" * 32, "at": "z"}) + "\n" +
        json.dumps({"kind": "checkpoint.write", "thread_id": "wf_c", "checkpoint_id": "cp1",
                    "prev": "bb" * 32, "digest": "cc" * 32, "at": "z"}) + "\n"  # prev != prior digest
    )

    with pytest.raises(AuditChainCorrupted):
        make_checkpointer("wf_c", base=tmp_path / "loop" / "checkpoints", chain_file=chain_file)


def test_all_refusals_inherit_from_common_base() -> None:
    """CLI exit code 13 maps to CheckpointerError; the four refusals MUST share that base."""
    for cls in (CheckpointTampered, CheckpointerInsecure, SchemaDrift, AuditChainCorrupted):
        assert issubclass(cls, CheckpointerError)
```

### Green — make it pass
- Add `class CheckpointerError(Exception): ...` to `graph/hooks.py` and re-parent the four typed exceptions.
- Override `aget_tuple`: schema check → chain lookup → digest recompute → emit-tamper-then-raise.
- Extend `__init__` with the chain-head consistency check and the `_enforce_file_mode_0600` call (already from S2-01) — confirm both raise correctly.
- Add `_read_chain_events()` helper (testing only) that parses the JSONL into a list of dicts.

### Refactor — clean up
- Centralize the "lookup recorded digest for `(thread_id, checkpoint_id)`" path in one private method so future event kinds reuse it.
- Make the `checkpoint.tamper.detected` event's payload schema explicit in a typed Pydantic model under `graph/events.py` (additive; do not modify the model from S1-04).
- Add a docstring on `aget_tuple` mapping each `raise` site to its ADR.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/graph/checkpointer.py` | Override `aget_tuple`; add chain-seed consistency check in `__init__`. |
| `src/codegenie/graph/hooks.py` | Add `CheckpointerError` base; reparent four refusals. |
| `src/codegenie/graph/events.py` | Optional: typed `CheckpointTamperDetectedEvent` (additive). |
| `tests/adversarial/test_checkpoint_refusals.py` | New — four refusal tests + the inheritance test. |
| `tests/adversarial/__init__.py` | New if absent. |

## Out of scope
- WAL durability under simulated process kill (S2-04).
- Replay-after-kill multiprocessing canary (S8-01).
- Operator-key signing of the `human_decision` (Phase 11 — ADR-0008).
- CLI exit-code wiring (S6-02 handles the click side).
- Tamper-after-resume (i.e., online tampering during a paused workflow) — explicitly deferred to Phase 11.

## Notes for the implementer
- Order matters in `aget_tuple`: check **schema drift first**, then digest. Reversing the order can raise `CheckpointTampered` for a benignly-drifted blob and mislead operators.
- The tamper-detected chain event must be written **before** the `raise`, so a failed resume still leaves an audit trail. Use a `try/finally` if needed, but keep it under the shared lock.
- The mutation tests rely on the underlying schema of `AsyncSqliteSaver`. If LangGraph changes the table or column names between versions, the tests fail loudly — that's intentional; pin LangGraph in `pyproject.toml`.
- The `schema_version` mutation test may need to handle whatever encoding LangGraph uses for `checkpoint` (JSON vs msgpack). Probe the saver's serializer first; if non-JSON, mutate via a serialize/mutate/re-serialize round-trip rather than text replace.
- Do **not** swallow `CheckpointTampered` to attempt recovery; the refusal is the contract.
- `_enforce_file_mode_0600` must run on every construction, not just first-time — an operator who `chmod 644`s between runs gets caught on the next open.
- Keep the test that asserts the common base; it's the contract the CLI's exit-code mapper relies on (S6-02).
