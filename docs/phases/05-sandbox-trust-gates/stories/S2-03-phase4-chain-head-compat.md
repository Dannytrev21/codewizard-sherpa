# Story S2-03 — Phase 4 chain-head compatibility check + `AuditChainCorrupted` startup refusal

**Step:** Step 2 — Implement `RetryLedger` and audit-chain extension
**Status:** Ready
**Effort:** S
**Depends on:** S2-01
**ADRs honored:** ADR-0005, ADR-0007

## Context

Phase 4 emits BLAKE3-chained audit events (`solved_example.duplicate_skipped`, `engine_used` stamping) and writes the final chain head to `.codegenie/remediation/<run-id>/chain_head.bin`. Phase 5's `RetryLedger` extends that same chain — if Phase 4's event shape drifts silently, Phase 5 would read an incompatible predecessor entry and never notice. The critic's roadmap §6 attack ("none of the three designs verified Phase 4's chain events produce entries Phase 5 will consume") is closed by this story: a binary golden fixture produced by Phase 4's *own* chain-head writer, and a `RetryLedger.__init__` startup refusal if the on-disk file doesn't match the in-memory `prev_chain_head` argument (or is missing/truncated).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — RetryLedger` — `Internal structure`: `__init__` reads `prev_chain_head` from Phase 4's chain end (path: `.codegenie/remediation/<run-id>/chain_head.bin`); on mismatch raises `AuditChainCorrupted`.
  - `../phase-arch-design.md §Edge cases §12` — corrupted Phase 4 chain head causes `__init__` to raise.
  - `../phase-arch-design.md §Cross-phase boundary tests` — `tests/schema/test_phase4_chain_compat.py` regenerates the fixture and would fail loudly if Phase 4's shape drifts.
  - `../phase-arch-design.md §Goals §14` — "Audit chain extends Phase 4 head. Startup test refuses to run any gate if Phase 4 chain head does not match (`AuditChainCorrupted`)."
- **Phase ADRs:**
  - `../ADRs/0005-phase4-chain-head-compatibility.md` — the canonical contract; pay attention to the "Consequences" section about Phase 4 PRs that change event shape needing a fixture update.
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — context for why the chain needs to span boundaries.
- **Source design:**
  - `../final-design.md §New ADRs implied — ADR-P5-005`.
- **Existing code:**
  - `src/codegenie/gates/retry_ledger.py` (from S2-01) — extend `__init__` to read and validate the file.
  - Phase 4 chain-head producer (search Phase 4 source under `src/codegenie/llm/` or `src/codegenie/fallback/`) — call its writer in the fixture generator. The fixture's byte-stability is part of this story's contract.

## Goal

Wire `RetryLedger.__init__` to read `.codegenie/remediation/<run-id>/chain_head.bin` (Phase 4's last write), compare against the passed `prev_chain_head`, and raise `AuditChainCorrupted` on mismatch, missing file, or wrong byte length — with a Phase-4-produced golden fixture proving cross-phase compatibility.

## Acceptance criteria

- [ ] `RetryLedger.__init__(run_dir: Path, gate_id: str, prev_chain_head: bytes | None)` resolves `chain_head_path = run_dir / "chain_head.bin"`.
- [ ] If `prev_chain_head is not None` and the file exists: contents must equal `prev_chain_head` bytes exactly; mismatch raises `AuditChainCorrupted(f"phase4 chain-head mismatch: expected={...}, on_disk={...}")`.
- [ ] If `prev_chain_head is not None` and the file is missing: raise `AuditChainCorrupted("phase4 chain-head missing")`.
- [ ] If `prev_chain_head is not None` and the file is wrong size (≠ 32 bytes): raise `AuditChainCorrupted("phase4 chain-head wrong size: got={n}")`.
- [ ] If `prev_chain_head is None`: skip the check (genesis ledger; used only in test fixtures and the very first phase-4-less run).
- [ ] After a successful pass, `__init__` records a structlog event `gates.ledger.chain_head_verified` with `chain_head_hex[:8]`.
- [ ] `tests/golden/phase4_chain_head.bin` is produced by Phase 4's *own* chain-head writer via `tests/schema/test_phase4_chain_compat.py::test_regenerate_fixture` (runnable via `pytest -k regenerate_fixture --regen`), so the byte format is the contract and the fixture cannot drift unilaterally.
- [ ] `tests/adversarial/test_phase4_chain_head_mismatch.py` — flipping any byte in `chain_head.bin` causes `RetryLedger(...)` to raise `AuditChainCorrupted`; the error message includes the gate_id.
- [ ] `tests/adversarial/test_phase4_chain_head_missing.py` — deleting `chain_head.bin` while `prev_chain_head` is non-None raises `AuditChainCorrupted`.
- [ ] `tests/gates/test_retry_ledger_chain_compat.py::test_happy_path_with_golden_fixture` — reading the committed `tests/golden/phase4_chain_head.bin`, passing `prev_chain_head=Path(...).read_bytes()`, constructs a `RetryLedger` without raising AND records one attempt whose `prev_hash` equals the golden bytes (hex).
- [ ] `codegenie sandbox inspect <gate-run-id>` (placeholder if S8-01 not landed: just `RetryLedger(...).head()` after construction) re-verifies the chain head against the on-disk file on every invocation.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/gates`, `pytest tests/gates/test_retry_ledger_chain_compat.py tests/adversarial/test_phase4_chain_head_mismatch.py tests/adversarial/test_phase4_chain_head_missing.py` pass.

## Implementation outline

1. Extend `src/codegenie/gates/retry_ledger.py`:
   - In `__init__`, after computing `_gate_dir`, add `self._verify_phase4_chain_head(run_dir, prev_chain_head)`.
   - `_verify_phase4_chain_head(run_dir, expected)` — early-return on `expected is None`; read `run_dir / "chain_head.bin"`; check existence, size (must be 32 bytes), equality. Raise `AuditChainCorrupted` with structured message on any failure.
2. Identify Phase 4's chain-head writer. If a public function (e.g., `codegenie.llm.audit.write_chain_head(path, head_bytes)`) exists, import it. If not (likely — this is cross-phase scaffolding), write a thin shim `src/codegenie/llm/audit/chain_head_io.py` that exposes `write_chain_head` and `read_chain_head` and call those from Phase 4 too (additive, no behavior change in Phase 4 — flag for follow-up Phase 4 PR if Phase 4's existing implementation is inlined and not yet refactored).
3. Add `tests/golden/phase4_chain_head.bin` — a 32-byte file. The companion regenerator `tests/schema/test_phase4_chain_compat.py::test_regenerate_fixture(regen_flag)` reproducibly produces it by calling Phase 4's writer with a fixed deterministic input (e.g., a hardcoded list of three `engine_used` events with frozen timestamps). The test asserts the bytes match the committed fixture; with `--regen`, it rewrites.
4. Add the three adversarial / happy-path tests.
5. Wire structlog `gates.ledger.chain_head_verified` event into S1-01's event-constants module.
6. Update `RetryLedger.head()` docstring noting that the initial `head()` return value equals `prev_chain_head` exactly when the on-disk file has been verified.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/gates/test_retry_ledger_chain_compat.py`

```python
# tests/gates/test_retry_ledger_chain_compat.py
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.gates.errors import AuditChainCorrupted
from codegenie.gates.retry_ledger import RetryLedger

GOLDEN = Path(__file__).parent.parent / "golden" / "phase4_chain_head.bin"


def test_happy_path_with_golden_fixture(tmp_path: Path) -> None:
    """RetryLedger accepts a Phase-4-produced chain head and chains the next attempt from it."""
    expected_head = GOLDEN.read_bytes()
    assert len(expected_head) == 32, "golden fixture must be 32 bytes — Phase 4 chain-head size"

    # Place the same bytes at the location RetryLedger reads.
    (tmp_path / "chain_head.bin").write_bytes(expected_head)

    ledger = RetryLedger(
        run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=expected_head,
    )

    # head() before any record returns the Phase 4 head exactly.
    assert ledger.head() == expected_head


def test_mismatch_raises_audit_chain_corrupted(tmp_path: Path) -> None:
    expected = GOLDEN.read_bytes()
    on_disk = bytes(b ^ 0x01 for b in expected)  # flip the LSB of every byte
    (tmp_path / "chain_head.bin").write_bytes(on_disk)

    with pytest.raises(AuditChainCorrupted) as exc:
        RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=expected)
    assert "mismatch" in str(exc.value).lower()


def test_missing_file_with_expected_head_raises(tmp_path: Path) -> None:
    expected = GOLDEN.read_bytes()
    # Do NOT write chain_head.bin.
    with pytest.raises(AuditChainCorrupted) as exc:
        RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=expected)
    assert "missing" in str(exc.value).lower()


def test_wrong_size_file_raises(tmp_path: Path) -> None:
    (tmp_path / "chain_head.bin").write_bytes(b"\x00" * 16)  # half size
    with pytest.raises(AuditChainCorrupted) as exc:
        RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=b"\x00" * 32)
    assert "size" in str(exc.value).lower()


def test_genesis_mode_skips_check_when_prev_chain_head_is_none(tmp_path: Path) -> None:
    """No file, no expected head — used by tests and the very first ever run."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=None)
    assert ledger.head() == b"\x00" * 32
```

### Green — make it pass

Implement `_verify_phase4_chain_head` exactly as described. The four branches (`None → skip`, `missing file → raise`, `wrong size → raise`, `mismatch → raise`, `equal → pass`) are mechanical. Generate the golden fixture by calling Phase 4's chain-head writer with a fixed input; commit the binary.

### Refactor — clean up

- Move the path resolution (`run_dir / "chain_head.bin"`) into a module constant `PHASE4_CHAIN_HEAD_FILENAME = "chain_head.bin"` to keep S5-02 and S8-01 (`inspect`) in sync.
- Add a docstring on `_verify_phase4_chain_head` referencing ADR-0005 by number and citing the production ADR-0014 link from the ADR.
- Make the `AuditChainCorrupted` messages structured (include `gate_id`, expected/actual hex prefixes truncated to 8 chars — never log full 64 hex chars because that's the chain secret-ish identifier).
- Ensure the regenerator test (`test_regenerate_fixture`) is *not* part of the default `pytest` run — gate it on a `--regen` flag (via `pytest_addoption`) so CI doesn't silently regenerate.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/retry_ledger.py` | Add `_verify_phase4_chain_head` and the `PHASE4_CHAIN_HEAD_FILENAME` constant. |
| `src/codegenie/llm/audit/chain_head_io.py` | (If absent) shim exposing Phase 4's `write_chain_head`/`read_chain_head` so the fixture generator and Phase 4 share one writer. |
| `tests/gates/test_retry_ledger_chain_compat.py` | Five branches: happy, mismatch, missing, wrong size, genesis. |
| `tests/adversarial/test_phase4_chain_head_mismatch.py` | Edge case 12 dedicated adversarial test. |
| `tests/adversarial/test_phase4_chain_head_missing.py` | Missing-file adversarial test. |
| `tests/schema/test_phase4_chain_compat.py` | Regenerator + assert-byte-equal test (with `--regen` flag). |
| `tests/golden/phase4_chain_head.bin` | The 32-byte golden fixture (binary). |
| `tests/conftest.py` | `--regen` `pytest_addoption` hook. |

## Out of scope

- Operator-side `codegenie sandbox inspect` re-verification flow — S8-01 (this story just makes `__init__` re-verify on every construction).
- Changes to Phase 4's actual event-emit path — the shim makes the writer importable, but Phase 4's existing events keep their shape. A future Phase 4 PR may consolidate; that's tracked, not done here.
- Recovery flow when an operator legitimately needs to reset the chain head (forensic edit) — that's a roadmap item (manual `codegenie sandbox reset-chain --i-know-what-im-doing`); not in scope.
- `pre_execute` marker (S2-02 lands that surface).

## Notes for the implementer

- 32 bytes is the BLAKE3 default digest size — keep it that way. ADR-0005 implicitly pins this via "shape of the chain head" — a digest_size change is an ADR amendment.
- The fixture generator MUST call Phase 4's writer, not synthesize bytes by hand. If you hand-write the 32 bytes, this story's whole premise (cross-phase compatibility) is undermined.
- The error message should NOT echo full hex strings — truncate to 8-char prefix (`abc12345…`). Full hex in logs leaks chain state unnecessarily.
- A *missing* `chain_head.bin` with `prev_chain_head=None` is the "genesis" mode used by tests; this is intentional and not a security hole because the genesis mode is opt-in via the constructor argument, not file-state.
- Watch for path-separator bugs on Windows — the test should use `Path`, never raw strings.
- If Phase 4 source has no public writer function today, this story is *additive scaffolding* — flag it in the PR description as a Phase 4 surface refactor that ADR-0005 anticipated; do not redesign Phase 4's audit emission.
- The `--regen` flag and `test_regenerate_fixture` must not auto-run in CI; double-check your `pytest_addoption` defaults the flag to `False`.
- The fixture's byte-stability is part of the test contract — any Phase 4 PR that changes chain-head shape must regenerate AND surface the diff for ADR review.
