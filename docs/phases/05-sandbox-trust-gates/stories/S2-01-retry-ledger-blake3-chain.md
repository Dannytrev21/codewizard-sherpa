# Story S2-01 — `RetryLedger` BLAKE3-chained JSONL + `Attempt` model

**Step:** Step 2 — Implement `RetryLedger` and audit-chain extension
**Status:** Ready
**Effort:** M
**Depends on:** S1-01, S1-04
**ADRs honored:** ADR-0005, ADR-0007, ADR-0011

## Context

The `RetryLedger` is one of Phase 5's three load-bearing abstractions (per `phase-arch-design.md §Component design`) and is the only durable checkpoint the retry loop produces. Every attempt appends one BLAKE3-chained JSONL line to `.codegenie/remediation/<run-id>/gates/<gate_id>/attempts.jsonl`, and that file plus the sandbox-run sub-directories are what Phase 6's checkpointer will lift unchanged. This story lands the core `record`, `head`, and `attempts` replay surface; pre-execute marker (S2-02) and Phase 4 chain-head startup check (S2-03) extend it.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — RetryLedger` — purpose, file layout, internal structure, failure behavior.
  - `../phase-arch-design.md §Logical view` — `RetryLedger` class diagram with `prev_chain_head` and `Attempt` shape.
  - `../phase-arch-design.md §Process view` — sequence diagram showing `record` write ordering with `GateRunner`.
  - `../phase-arch-design.md §Edge cases §11` — manual `attempts.jsonl` edit triggers `AuditChainCorrupted` on replay.
  - `../phase-arch-design.md §Code contracts and APIs` — the `Attempt` Pydantic model (`attempt_id`, `sandbox_run_id`, `signals`, `outcome`, `started_at`, `ended_at`, `prev_hash`, `chain_hash`).
- **Phase ADRs:**
  - `../ADRs/0005-phase4-chain-head-compatibility.md` — `record` extends a chain that began in Phase 4; `attempts.jsonl` is append-only with BLAKE3 per-line.
  - `../ADRs/0011-no-verdict-cache-in-phase-5.md` — `record` must not double-write on identical `(attempt_id, spec_hash)`; raise `LedgerAttemptOutOfOrder` instead.
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — three attempts is the upper-bound `attempt_id`.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "BLAKE3-chained RetryLedger"`.
- **Existing code:**
  - `src/codegenie/gates/contract.py` (from S1-04) — imports `Attempt`, `TransitionId`, `GateOutcome`.
  - `src/codegenie/gates/errors.py` (from S1-01) — extend with `AuditChainCorrupted` and `LedgerAttemptOutOfOrder`.

## Goal

Implement `RetryLedger` with `record`, `head`, and `attempts` replay verification over a BLAKE3-chained `attempts.jsonl` file with sibling `manifest.yaml` and fsynced per-record writes.

## Acceptance criteria

- [ ] `RetryLedger(run_dir: Path, gate_id: str, prev_chain_head: bytes | None)` creates `.codegenie/remediation/<run-id>/gates/<gate_id>/{attempts.jsonl,manifest.yaml}` on first use and writes `manifest.yaml` with `gate_id`, `created_at` (UTC ISO 8601), `prev_chain_head` (hex).
- [ ] `RetryLedger.record(attempt: Attempt) -> None` serializes `Attempt` to canonical JSON (`json.dumps(..., sort_keys=True, separators=(",", ":"))`), computes `chain_hash = blake3(prev_hash_bytes + payload_bytes).hexdigest()`, appends one JSONL line, fsyncs the file *and* the directory file-descriptor.
- [ ] `RetryLedger.head() -> bytes` returns the most recent line's `chain_hash` decoded from hex (or `prev_chain_head` if no lines yet, or 32 zero bytes if both absent).
- [ ] `RetryLedger.attempts() -> list[Attempt]` replays the file, recomputes each `chain_hash`, raises `AuditChainCorrupted` on the first mismatch, and raises `LedgerAttemptOutOfOrder` if `attempt_id` is not strictly increasing from 1.
- [ ] Out-of-order or duplicate `record` (e.g., a second call with `attempt_id == 1` after `attempt_id == 1` was already recorded) raises `LedgerAttemptOutOfOrder` **before** any write hits disk.
- [ ] Hypothesis property test: for any N ≤ 5 valid attempts recorded in order under the same `prev_chain_head`, `head()` after the Nth record is deterministic regardless of write timing; recomputing `chain_hash` from re-parsed canonical JSON matches the stored value.
- [ ] `tests/adversarial/test_audit_chain_tamper.py` — manually editing one byte of any payload (other than the final line's `chain_hash`) causes `attempts()` to raise `AuditChainCorrupted` with a message identifying the offending `attempt_id`.
- [ ] Per-`record` p95 latency ≤ 50 ms on tmpfs (`/tmp` in CI), with actual `os.fsync` on the JSONL fd and the parent directory fd (verified via `unittest.mock.patch("os.fsync")` call-count test, not a timing test).
- [ ] Branch coverage on `src/codegenie/gates/retry_ledger.py` ≥ 90%; line coverage ≥ 95%.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/gates`, `pytest tests/gates/test_retry_ledger.py` all pass.

## Implementation outline

1. Add `blake3>=0.4` to `pyproject.toml` dependencies and lock.
2. Extend `src/codegenie/gates/errors.py` with `AuditChainCorrupted(GatesError)` and `LedgerAttemptOutOfOrder(GatesError)`.
3. Create `src/codegenie/gates/retry_ledger.py` with:
   - `class RetryLedger:` accepting `run_dir`, `gate_id`, `prev_chain_head: bytes | None` in `__init__`. (Chain-head *check* lands in S2-03; this story just stores `prev_chain_head` as the initial `head()` value.)
   - Private `_gate_dir: Path` property `= run_dir / "gates" / gate_id`.
   - `_canonical_json(attempt: Attempt) -> bytes` using `attempt.model_dump(mode="json")` then `json.dumps(..., sort_keys=True, separators=(",", ":")).encode()`.
   - `_compute_chain_hash(prev_hex: str, payload: bytes) -> str` — `blake3(bytes.fromhex(prev_hex) + payload).hexdigest()` (32 bytes → 64 hex chars).
   - `record(attempt: Attempt)` — open `attempts.jsonl` in append-binary mode, write one line, `os.fsync(f.fileno())`, then open the parent dir and `os.fsync(dirfd)` for crash-safety.
   - `head() -> bytes` — read the last `chain_hash` (cached; invalidate on `record`); decode hex to 32 raw bytes; return `prev_chain_head or b"\x00" * 32` if no lines exist.
   - `attempts() -> list[Attempt]` — line-by-line replay, recompute `chain_hash`, validate `attempt_id` monotonicity from 1; structlog `gates.ledger.replay_failed` on mismatch.
4. Emit a structlog event `gates.ledger.attempt_recorded` with `gate_id`, `attempt_id`, `chain_hash` (first 8 hex chars only) on each successful `record`.
5. Write the manifest on first use only; do not rewrite on subsequent records.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/gates/test_retry_ledger.py`

```python
# tests/gates/test_retry_ledger.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codegenie.gates.contract import Attempt, GateOutcome
from codegenie.gates.errors import AuditChainCorrupted, LedgerAttemptOutOfOrder
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.sandbox.signals.models import ObjectiveSignals


def _make_attempt(attempt_id: int, prev_hash: str = "00" * 32) -> Attempt:
    now = datetime.now(timezone.utc)
    return Attempt(
        attempt_id=attempt_id,
        sandbox_run_id=f"run-{attempt_id:04d}",
        signals=ObjectiveSignals(),
        outcome=GateOutcome(
            passed=False, attempt=attempt_id, failing_signals=[],
            retryable=True, state="failed_retryable", summary="",
            signals=ObjectiveSignals(),
        ),
        started_at=now,
        ended_at=now,
        prev_hash=prev_hash,
        chain_hash="00" * 32,  # placeholder; ledger fills in
    )


def test_record_appends_chained_line_and_fsyncs(tmp_path: Path) -> None:
    ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=None)
    attempt = _make_attempt(1)

    ledger.record(attempt)

    jsonl = tmp_path / "gates" / "stage6_validate" / "attempts.jsonl"
    assert jsonl.exists(), "attempts.jsonl must be created"
    lines = jsonl.read_text().splitlines()
    assert len(lines) == 1, "exactly one line written per record call"
    payload = json.loads(lines[0])
    assert payload["attempt_id"] == 1
    assert len(payload["chain_hash"]) == 64, "blake3-256 hex is 64 chars"
    assert payload["prev_hash"] == "00" * 32, "first record uses zero prev"
    # Chain is derived: changing one payload byte must change chain_hash.
    assert payload["chain_hash"] != payload["prev_hash"]


def test_attempts_replay_verifies_chain_and_detects_tamper(tmp_path: Path) -> None:
    ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=None)
    ledger.record(_make_attempt(1))
    ledger.record(_make_attempt(2, prev_hash=ledger.head().hex()))

    # Clean replay round-trips.
    assert [a.attempt_id for a in ledger.attempts()] == [1, 2]

    # Tamper: flip a byte in the first line's sandbox_run_id.
    jsonl = tmp_path / "gates" / "stage6_validate" / "attempts.jsonl"
    text = jsonl.read_text()
    tampered = text.replace("run-0001", "run-XXXX", 1)
    jsonl.write_text(tampered)

    with pytest.raises(AuditChainCorrupted) as exc:
        ledger.attempts()
    assert "attempt_id=1" in str(exc.value), "error must identify offending row"


def test_record_rejects_out_of_order_attempt_id_before_writing(tmp_path: Path) -> None:
    ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=None)
    ledger.record(_make_attempt(1))

    with pytest.raises(LedgerAttemptOutOfOrder):
        ledger.record(_make_attempt(1))  # duplicate id

    jsonl = tmp_path / "gates" / "stage6_validate" / "attempts.jsonl"
    assert len(jsonl.read_text().splitlines()) == 1, "rejected record must not append"
```

### Green — make it pass

Smallest implementation: `RetryLedger.__init__` creates `_gate_dir`, writes `manifest.yaml` if absent, stores `prev_chain_head` (bytes or `None`). `record` validates `attempt.attempt_id == self._next_attempt_id`, computes canonical JSON, computes `chain_hash`, rewrites the `attempt` with the real `chain_hash`, appends, fsyncs file + parent dir, increments `_next_attempt_id`. `head` returns `bytes.fromhex(self._last_chain_hash)` or `prev_chain_head` or zero bytes. `attempts` reads, parses each line via `Attempt.model_validate_json`, replays `chain_hash` computation, raises on mismatch.

### Refactor — clean up

- Add type hints for every method; `from __future__ import annotations`.
- Docstrings citing ADR-0005 and ADR-0007.
- Pull `_canonical_json` and `_compute_chain_hash` into module-level functions so S2-02's `record_pre_execute` reuses them.
- Replace `print` (if any) with structlog `gates.ledger.*` event names from S1-01's event-constants module.
- Edge cases: missing `_gate_dir`, empty `attempts.jsonl` (treat as no records, not error), trailing newline tolerance, UTF-8 decode error → `AuditChainCorrupted`.
- Add `__repr__` exposing only `gate_id` and `_next_attempt_id`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/retry_ledger.py` | New module — `RetryLedger` class. |
| `src/codegenie/gates/errors.py` | Add `AuditChainCorrupted`, `LedgerAttemptOutOfOrder`. |
| `src/codegenie/gates/__init__.py` | Re-export `RetryLedger` at package surface. |
| `tests/gates/test_retry_ledger.py` | The red test plus property + tamper tests. |
| `tests/gates/conftest.py` | (If needed) shared `_make_attempt` factory. |
| `pyproject.toml` | Add `blake3` dependency. |

## Out of scope

- `record_pre_execute(...)` — S2-02.
- Phase 4 chain-head compatibility startup check — S2-03 (this story accepts `prev_chain_head` but does not validate it against an on-disk Phase 4 file).
- `codegenie sandbox inspect` CLI surface — S8-01.
- Concurrent-writer locking via `fcntl.flock` — S7-04 (the ledger is single-writer by `GateRunner` design).

## Notes for the implementer

- BLAKE3 default digest is 32 bytes; do not use the `digest_size` parameter unless you have a reason — the chain compat test in S2-03 depends on the default.
- `Attempt.model_dump(mode="json")` is **required** (not `model_dump()`) so `datetime` becomes ISO-8601 string — otherwise canonical JSON varies.
- `os.fsync` on the directory fd matters on Linux (ext4) but is a no-op on macOS; do not guard it, just call and ignore `OSError` with `errno.EINVAL` from non-POSIX FS.
- Resist the urge to cache the entire attempts list in memory — replay reads the file. The only cached state is `_last_chain_hash` and `_next_attempt_id`.
- The 32-byte zero `prev_chain_head` is a *sentinel for the first ledger ever*; in real runs it comes from Phase 4 (S2-03).
- Do not import anything from `sandbox/` — `gates/` and `sandbox/` are sibling packages; circular imports here will surface later.
- `LedgerAttemptOutOfOrder` must raise *before* any disk write to preserve the file-is-truth invariant.
