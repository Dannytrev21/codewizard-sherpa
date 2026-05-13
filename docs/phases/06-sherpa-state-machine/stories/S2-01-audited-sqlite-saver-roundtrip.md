# Story S2-01 — Implement `AuditedSqliteSaver` round-trip + per-workflow file mode

**Step:** Step 2 — Implement `AuditedSqliteSaver` + per-workflow file + BLAKE3 chain extension
**Status:** Ready
**Effort:** M
**Depends on:** S1-05
**ADRs honored:** ADR-0006, ADR-0005, ADR-0011

## Context
Step 2 introduces durability and tamper-evidence for the LangGraph state machine. This first story lands the bare bones: an `AsyncSqliteSaver` subclass that opens a per-workflow `.sqlite3` file at `0600`, configures WAL + `synchronous=NORMAL`, serializes checkpoints with a canonical-JSON encoder, and round-trips a `VulnLedger` byte-identical. Chain extension and tamper detection are deliberately deferred to S2-02 / S2-03 so this story stays mechanical and well-bounded.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component 3 "AuditedSqliteSaver"` — `__init__`, `_enforce_file_mode_0600`, `_fsync_durable`, `canonical_json`, factory shape.
- **Architecture:** `../phase-arch-design.md §Development view` — the `graph/checkpointer.py` location, the `make_checkpointer` factory.
- **Architecture:** `../phase-arch-design.md §Persistence view` — file-system layout under `.codegenie/loop/checkpoints/<workflow_id>.sqlite3`.
- **Phase ADRs:** `../ADRs/0006-audited-sqlite-saver-per-workflow-fsync.md` — fsync per node boundary; WAL=on, synchronous=NORMAL; per-workflow file; 0600 mode; the `make_checkpointer` factory as the Phase-9 swap seam.
- **Phase ADRs:** `../ADRs/0005-static-schema-version-literal-pin.md` — `schema_version: Literal["v0.6.0"]` is the contract this round-trip must preserve.
- **Phase ADRs:** `../ADRs/0011-sqlite-throughput-watch-and-postgres-escalation.md` — durability/throughput tradeoff context; this story does not measure throughput but must not introduce extra fsync calls.
- **Source design:** `../final-design.md §Synthesis ledger rows 4 + 5` (per-workflow file + fsync-per-boundary picks).
- **High-level plan:** `../High-level-impl.md §Step 2` — features delivered + done criteria.
- **Existing code:** `src/codegenie/graph/state.py` — `VulnLedger` is what round-trips. `src/codegenie/gates/retry_ledger.py` — read before writing the factory so Phase-5 chain-file seams aren't broken (chain logic itself is S2-02).

## Goal
Ship `AuditedSqliteSaver(AsyncSqliteSaver)` plus `make_checkpointer()` such that a known `VulnLedger` written via `put()` and read via `aget_tuple()` is byte-identical, and the on-disk file is `0600` with WAL + `synchronous=NORMAL` configured.

## Acceptance criteria
- [ ] `AuditedSqliteSaver` is defined in `src/codegenie/graph/checkpointer.py` as a subclass of LangGraph's `AsyncSqliteSaver`; opening the saver creates the parent directory and the `<workflow_id>.sqlite3` file with file mode exactly `0o600` (verified by `(stat.st_mode & 0o777) == 0o600`).
- [ ] On connect, `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` are set (verified by querying each PRAGMA back and asserting `"wal"` and `1` respectively).
- [ ] `make_checkpointer(workflow_id: str, *, base: Path = Path(".codegenie/loop/checkpoints")) -> AuditedSqliteSaver` factory exists and is the only public construction path; it derives the file path as `base / f"{workflow_id}.sqlite3"`.
- [ ] A round-trip test writes a known `VulnLedger` via `put()` and reads it back via `aget_tuple()`; the reconstructed `model_dump_json(by_alias=True, exclude_none=False)` is byte-identical to the original, and `schema_version` survives as the literal `"v0.6.0"`.
- [ ] A `canonical_json(obj)` helper exists, sorts dict keys recursively, uses `separators=(",", ":")`, and is the only serializer used inside the checkpointer for both persistence and (future) digest computation.
- [ ] Calling `put()` twice in the same session produces two distinct `checkpoint_id` rows readable back via `aget_tuple` with the most-recent state.
- [ ] No application-level `os.fsync()` call exists in `src/codegenie/graph/checkpointer.py` — durability is delegated to SQLite's WAL+NORMAL discipline (grep gate; documented in the file header).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Read `src/codegenie/gates/retry_ledger.py` first to confirm what (if any) `head_from_phase5()` accessor exists. If absent, **do not** add it here — surface as a note for S2-02 (Gap 2 in the arch design).
2. Add `src/codegenie/graph/checkpointer.py` with module docstring quoting ADR-0006's "fsync at every node boundary" commitment and ADR-0011's "WAL+NORMAL is the only durability primitive" rule.
3. Implement `canonical_json(obj) -> bytes` — recursive key sort, `json.dumps(..., separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")`. Keep it small.
4. Implement `AuditedSqliteSaver.__init__(self, db_path: Path)` that: ensures parent dir exists, opens with `umask` set so the file lands at `0600` (or `os.chmod(db_path, 0o600)` after first open), calls `super().__init__(conn_string=str(db_path))`.
5. Override `setup()` (or use post-connect hook) to issue `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`. Verify both via read-back.
6. Implement `_enforce_file_mode_0600(self) -> None`: `st = path.stat(); if (st.st_mode & 0o777) != 0o600: raise CheckpointerInsecure(...)`. Call from `__init__` after the connection is opened.
7. Override `put()` to serialize the LangGraph checkpoint via `canonical_json` and delegate to the parent's `put()` with that canonical serializer plugged in. Do NOT add chain logic yet — leave a clearly named TODO with `# S2-02:` comment.
8. Implement `make_checkpointer(workflow_id, *, base=...)` factory at module level — single-line constructor invocation.
9. Write `tests/graph/test_checkpointer.py` exercising the AC above. Use `tmp_path` fixture for the DB location.
10. Confirm `mypy --strict` clean; no `Any`, no `cast`, no `# type: ignore`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/graph/test_checkpointer.py`

```python
import json
import stat
from pathlib import Path

import pytest

from codegenie.graph.checkpointer import (
    AuditedSqliteSaver,
    canonical_json,
    make_checkpointer,
)
from codegenie.graph.state import VulnLedger
# Fixture for a known-good VulnLedger; lives under tests/graph/fixtures/.
from tests.graph.fixtures.ledgers import build_minimal_ledger


@pytest.mark.asyncio
async def test_audited_saver_roundtrips_vuln_ledger_byte_identical(tmp_path: Path) -> None:
    """A VulnLedger written via put() and read via aget_tuple() must be byte-identical.

    Why this matters: ADR-0005 commits to schema_version="v0.6.0" surviving the
    round-trip; ADR-0006 commits to the checkpointer being the single durable
    side-effect boundary. If serialization is lossy here, replay-byte-identity
    (S8-01) can never hold downstream.
    """
    saver = make_checkpointer("workflow_abc123def4567890", base=tmp_path)
    ledger = build_minimal_ledger(schema_version="v0.6.0")
    config = {"configurable": {"thread_id": "workflow_abc123def4567890"}}

    # Put through the LangGraph checkpoint protocol.
    checkpoint = {"v": 1, "ts": "2026-05-12T00:00:00Z", "channel_values": {"__root__": ledger.model_dump(mode="json")}}
    await saver.aput(config, checkpoint, {}, {})

    tup = await saver.aget_tuple(config)
    assert tup is not None
    restored = VulnLedger.model_validate(tup.checkpoint["channel_values"]["__root__"])

    # Byte-identical canonical form
    assert restored.model_dump_json(by_alias=True, exclude_none=False) == ledger.model_dump_json(
        by_alias=True, exclude_none=False
    )
    assert restored.schema_version == "v0.6.0"


@pytest.mark.asyncio
async def test_db_file_mode_is_0600_after_init(tmp_path: Path) -> None:
    """ADR-0006: per-workflow file at 0600. Any laxer mode is a security regression."""
    saver = make_checkpointer("workflow_zzz", base=tmp_path)
    # Force first write so the file actually exists.
    await saver.aput(
        {"configurable": {"thread_id": "workflow_zzz"}},
        {"v": 1, "ts": "2026-05-12T00:00:00Z", "channel_values": {"__root__": build_minimal_ledger().model_dump(mode="json")}},
        {},
        {},
    )
    db_path = tmp_path / "workflow_zzz.sqlite3"
    assert db_path.exists()
    mode = stat.S_IMODE(db_path.stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


@pytest.mark.asyncio
async def test_wal_and_synchronous_normal_pragmas_configured(tmp_path: Path) -> None:
    """ADR-0011: WAL + synchronous=NORMAL is the only durability primitive."""
    saver = make_checkpointer("workflow_yyy", base=tmp_path)
    # Read PRAGMAs back via the saver's internal connection.
    journal_mode = await saver.read_pragma("journal_mode")
    synchronous = await saver.read_pragma("synchronous")
    assert journal_mode.lower() == "wal"
    assert int(synchronous) == 1  # NORMAL


def test_canonical_json_is_deterministic_and_sorted() -> None:
    """canonical_json must produce byte-identical output regardless of input dict order."""
    a = {"b": 2, "a": [3, {"y": 1, "x": 2}]}
    b = {"a": [3, {"x": 2, "y": 1}], "b": 2}
    assert canonical_json(a) == canonical_json(b)
    # No whitespace
    assert b" " not in canonical_json(a)
```

### Green — make it pass
Smallest shape: subclass `AsyncSqliteSaver`, post-connect issue the two PRAGMAs, chmod the file to `0o600` after the parent's `__init__`, ship `canonical_json` and `make_checkpointer`. Plug `canonical_json` into the checkpoint serializer LangGraph uses.

### Refactor — clean up
- Document every PRAGMA in a module-level docstring with the ADR reference.
- Add a `read_pragma(name) -> str` helper (used by tests and a future `audit` subcommand).
- Add type hints everywhere; no `Any`.
- Confirm grep `os.fsync` against `src/codegenie/graph/` returns empty (ADR-0011 rule).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/graph/checkpointer.py` | New — class, factory, canonical_json, PRAGMA setup. |
| `src/codegenie/graph/__init__.py` | Re-export `AuditedSqliteSaver`, `make_checkpointer` (small additive change). |
| `tests/graph/test_checkpointer.py` | New — round-trip + file-mode + PRAGMA tests. |
| `tests/graph/fixtures/__init__.py` | New if absent. |
| `tests/graph/fixtures/ledgers.py` | New — `build_minimal_ledger()` helper used across S2-* stories. |

## Out of scope
- BLAKE3 chain extension (S2-02).
- Tamper / schema-drift / world-readable refusal tests (S2-03).
- Replay-after-kill canary (S2-04 smoke, S8-01 full).
- Throughput measurement (S9-02).
- Adding `head_from_phase5()` to Phase 5 — surface as a note, do not edit Phase 5 here.

## Notes for the implementer
- LangGraph's `AsyncSqliteSaver` may expose the underlying connection through a non-public attribute; if so, document the specific attribute name in a comment and add a focused test so a LangGraph minor bump fails loudly rather than silently.
- `umask` is process-global and unreliable in test runners; prefer an explicit `os.chmod(db_path, 0o600)` immediately after the file is first created.
- `canonical_json` must be the **single** serializer used both for persistence and for future digest computation in S2-02 — keep it pure and side-effect-free.
- Do not call `os.fsync` from Python — SQLite handles durability inside its WAL machinery; adding application-level fsync would silently double-fsync and skew S9-02's throughput baseline.
- If `tests/graph/fixtures/ledgers.py` already exists from S1 work, extend it; do not fork it.
- Keep the parent directory creation (`mkdir(parents=True, exist_ok=True)`) at `0o700` — the file is what `_enforce_file_mode_0600` asserts on, but the directory should not be world-readable either.
