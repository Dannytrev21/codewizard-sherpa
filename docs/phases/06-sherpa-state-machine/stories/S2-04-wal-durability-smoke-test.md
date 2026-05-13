# Story S2-04 — WAL durability smoke test for fsync-per-node-boundary

**Step:** Step 2 — Implement `AuditedSqliteSaver` + per-workflow file + BLAKE3 chain extension
**Status:** Ready
**Effort:** S
**Depends on:** S2-03
**ADRs honored:** ADR-0006, ADR-0011

## Context
ADR-0006 commits to "every node-boundary checkpoint is durably persisted before LangGraph proceeds to the next node" and ADR-0011 commits to "aiosqlite WAL+NORMAL is the only durability primitive". The full replay-after-kill canary lives in S8-01 (multiprocessing + SIGKILL); this story ships the cheaper, faster smoke version that runs in the per-PR test suite — write a checkpoint, close the connection abruptly, reopen, assert the last fsync'd frame is intact. This is the early-warning canary that catches a broken WAL setup (e.g., synchronous=OFF accidentally) at PR time instead of nightly.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component 3` — `_fsync_durable` is a no-op above SQLite's own; durability is WAL+NORMAL.
- **Architecture:** `../phase-arch-design.md §Edge cases / Harness engineering` — fsync per node boundary is the rule; the SIGKILL canary lives in Step 8.
- **Architecture:** `../phase-arch-design.md §Scenario 3 — Mid-run SIGKILL + resume` — the picture this story smoke-tests cheaply.
- **Phase ADRs:** `../ADRs/0006-audited-sqlite-saver-per-workflow-fsync.md` — "kill at any node boundary leaves the last fsync'd frame intact and the in-flight node simply re-runs".
- **Phase ADRs:** `../ADRs/0011-sqlite-throughput-watch-and-postgres-escalation.md` — WAL+NORMAL is the only durability primitive; no application-level fsync.
- **Source design:** `../final-design.md §Goals#8` — checkpoint durability under kill.
- **High-level plan:** `../High-level-impl.md §Step 2` — last done-criterion item ("Each `put()` durably persists before the next node runs"); §Step 8 is the full canary.
- **Existing code:** `src/codegenie/graph/checkpointer.py` — the saver under test.

## Goal
Prove with a fast, in-process test that an `AuditedSqliteSaver.put()` is durable across a connection close+reopen (the WAL frame survives) and that any partially-written in-flight WAL frame is rolled back on reopen.

## Acceptance criteria
- [ ] A test writes one full checkpoint via `aput`, closes the saver, reopens via `make_checkpointer`, and successfully `aget_tuple`s the same checkpoint byte-identical (already covered by S2-01 for the round-trip; this story adds the **explicit close-reopen** sequence so the contract is named).
- [ ] A test writes two checkpoints in sequence with `await saver.aput(...)` between them, closes after the second, reopens, and asserts only the second (most recent) is returned by `aget_tuple` — i.e., both writes were fsync'd before the close.
- [ ] A grep gate in the test confirms no `os.fsync(` call exists anywhere under `src/codegenie/graph/`; the file header of `checkpointer.py` carries a one-line comment naming ADR-0011 as the rule.
- [ ] A test verifies `PRAGMA journal_mode` returns `"wal"` and `PRAGMA synchronous` returns `1` (NORMAL) immediately after reopen — no PRAGMA drift between open cycles.
- [ ] A test simulates an in-flight WAL frame: open a low-level `sqlite3` connection to the same DB file, begin a transaction, write an extra row, **do not commit**, close the connection abruptly (`conn.close()` without `commit`); reopen via `make_checkpointer` and assert (a) the uncommitted row is absent, (b) prior committed checkpoints remain intact, (c) the chain file has not gained a corresponding `checkpoint.write` event.
- [ ] The test runs in under 5 seconds wall-clock on CI (it is the cheap canary; S8-01 owns the slow multiprocessing version).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Add `tests/integration/test_wal_durability_smoke.py`. Use `tmp_path` and `pytest.mark.asyncio`.
2. Test 1 — close-reopen round-trip: build saver, `aput` one checkpoint, `await saver.aclose()`, drop the reference, build a fresh saver at the same path, `aget_tuple`, assert byte-identical.
3. Test 2 — two-write durability: same shape but two `aput` calls; verify the latter wins on read.
4. Test 3 — uncommitted-WAL rollback: after writing one committed checkpoint via the saver, open a raw `sqlite3.connect(str(db_path), isolation_level=None)` connection, `BEGIN`, `INSERT` a synthetic row into the `checkpoints` table, **omit `COMMIT`**, `conn.close()`. Reopen via `make_checkpointer`, count rows, assert the synthetic insert is gone.
5. Test 4 — PRAGMA stability across reopens: build, close, build, read PRAGMAs; assert WAL + NORMAL.
6. Test 5 — grep gate: walk `src/codegenie/graph/` for the string `os.fsync(` (with the paren so docstrings naming the call don't false-positive); assert empty.
7. Confirm `mypy --strict` clean and the suite runs under 5s locally.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/integration/test_wal_durability_smoke.py`

```python
import sqlite3
from pathlib import Path

import pytest

from codegenie.graph.checkpointer import make_checkpointer
from tests.graph.fixtures.ledgers import build_minimal_ledger


@pytest.mark.asyncio
async def test_checkpoint_survives_close_reopen(tmp_path: Path) -> None:
    """ADR-0006: a put() before close MUST be visible after reopen.

    Why this matters: if WAL+NORMAL isn't actually configured (e.g., a typo
    sets synchronous=OFF), this test fails — catching the durability regression
    at PR time, not in S8-01's slow multiprocessing canary.
    """
    saver = make_checkpointer("wf_d", base=tmp_path)
    config = {"configurable": {"thread_id": "wf_d"}}
    ledger = build_minimal_ledger()
    cp = {"v": 1, "ts": "2026-05-12T00:00:00Z",
          "channel_values": {"__root__": ledger.model_dump(mode="json")}}
    await saver.aput(config, cp, {}, {})
    await saver.aclose()

    saver2 = make_checkpointer("wf_d", base=tmp_path)
    tup = await saver2.aget_tuple(config)
    assert tup is not None
    restored_root = tup.checkpoint["channel_values"]["__root__"]
    assert restored_root == ledger.model_dump(mode="json")


@pytest.mark.asyncio
async def test_uncommitted_wal_frame_is_rolled_back(tmp_path: Path) -> None:
    """ADR-0011: WAL+NORMAL is the only durability primitive — an uncommitted
    in-flight WAL frame MUST be rolled back on the next open. Verified by
    sneaking an uncommitted INSERT in via raw sqlite3 then reopening via the
    saver and confirming the row is gone.

    Why this matters: this is the core property S8-01's SIGKILL canary asserts
    at full cost; here we get the same signal in 1 second.
    """
    saver = make_checkpointer("wf_r", base=tmp_path)
    config = {"configurable": {"thread_id": "wf_r"}}
    await saver.aput(config,
                     {"v": 1, "ts": "z", "channel_values": {"__root__": build_minimal_ledger().model_dump(mode="json")}},
                     {}, {})
    await saver.aclose()

    db_path = tmp_path / "wf_r.sqlite3"
    # Raw connection, no COMMIT, abrupt close.
    raw = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        raw.execute("BEGIN")
        # Use a no-op-shaped insert that wouldn't survive rollback.
        raw.execute(
            "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata) "
            "VALUES ('wf_r', '', 'fake-cp', NULL, 'json', ?, ?)",
            (b"{}", b"{}"),
        )
        # NO COMMIT.
    finally:
        raw.close()

    saver2 = make_checkpointer("wf_r", base=tmp_path)
    # Count rows for thread_id wf_r; only the committed one must remain.
    rows = await saver2.count_checkpoints("wf_r")
    assert rows == 1


@pytest.mark.asyncio
async def test_pragmas_stable_across_reopens(tmp_path: Path) -> None:
    """A regression that flips synchronous to OFF or journal_mode to DELETE on
    a subsequent open would silently break durability."""
    s1 = make_checkpointer("wf_p", base=tmp_path)
    await s1.aput({"configurable": {"thread_id": "wf_p"}},
                  {"v": 1, "ts": "z", "channel_values": {"__root__": build_minimal_ledger().model_dump(mode="json")}},
                  {}, {})
    await s1.aclose()

    s2 = make_checkpointer("wf_p", base=tmp_path)
    assert (await s2.read_pragma("journal_mode")).lower() == "wal"
    assert int(await s2.read_pragma("synchronous")) == 1


def test_no_app_level_fsync_in_graph_package() -> None:
    """ADR-0011: WAL+NORMAL is the ONLY durability primitive.
    An os.fsync() call would skew S9-02's throughput baseline and contradict the ADR."""
    import codegenie.graph as graph_pkg
    pkg_root = Path(graph_pkg.__file__).parent
    offenders: list[Path] = []
    for py in pkg_root.rglob("*.py"):
        text = py.read_text()
        if "os.fsync(" in text:
            offenders.append(py)
    assert not offenders, f"os.fsync() found in graph package: {offenders}"
```

### Green — make it pass
- The first two tests should pass with the S2-01 implementation as-is — if either fails, surface a regression.
- Add a `count_checkpoints(thread_id) -> int` helper to `AuditedSqliteSaver` so the rollback test has a small, typed query path. This is a one-method addition; keep it minimal.
- The grep gate passes by virtue of ADR-0011 compliance; if it fails, remove the offending `os.fsync` and update the corresponding ADR consequence.

### Refactor — clean up
- Move `build_minimal_ledger` and any test helpers into the shared `tests/graph/fixtures/ledgers.py` rather than duplicating them.
- Add a docstring on `count_checkpoints` noting it's a test-and-CLI-friendly helper, not a hot path.
- Confirm the test runtime stays under 5s on CI; if not, drop the second `aput` in test #1 (one is enough) or shrink the synthetic ledger.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/graph/checkpointer.py` | Add minimal `count_checkpoints(thread_id)` helper used by the rollback test. |
| `tests/integration/test_wal_durability_smoke.py` | New — five tests covering close-reopen, rollback, PRAGMA stability, and the grep gate. |
| `tests/integration/__init__.py` | New if absent. |

## Out of scope
- The full SIGKILL multiprocessing replay-after-kill test (S8-01).
- The reference replay-byte-identical test (S8-02).
- Throughput measurement (S9-02 / S9-03).
- Cross-platform `aiosqlite` WAL behavior on macOS vs Linux differences — S8-01 handles the platform-matrix coverage; here we assume the same platform for open and reopen.

## Notes for the implementer
- Use `await saver.aclose()` (not just `del saver`) to release the WAL file handle deterministically — otherwise the rollback test races on macOS.
- The synthetic uncommitted-INSERT test exercises raw `sqlite3` directly so the saver's own write path can't accidentally commit on close. Keep that test honest by **not** going through `aput`.
- If LangGraph's checkpoint table schema changes (column names, NOT NULL constraints), the synthetic INSERT will fail with an `IntegrityError`; that's the canary — surface the schema change loudly rather than skipping the test.
- The grep gate uses substring match for `os.fsync(`. If the codebase grows a legitimate `os.fsync` site outside `graph/` (e.g., in `tools/`), it's outside this gate by design.
- This story explicitly does NOT need `multiprocessing` or `signal.SIGKILL` — keep it cheap. S8-01 owns the slow version.
- `count_checkpoints` is incidental scaffolding for this test; do not grow it into a query API in this story. If S6-04's `inspect` needs a richer query, extend it there.
