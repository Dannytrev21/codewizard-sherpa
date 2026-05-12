# Story S1-10 — Audit chain head + 100-gather rotation checkpoints

**Step:** Step 1 — Plant sandbox extension, tool wrappers, tool-digest pin manifest, and the four Phase-0/1 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0012

## Context

Phase 0's audit anchor (Phase 0 ADR-0004) writes one append-only `runs/<utc>-<short>.json` per gather. Phase 14's transparency-log integration is the production-grade integrity surface; Phase 2 sits between. ADR-0012 extends `AuditWriter` with a rolling BLAKE3 chain head per gather: each record carries `previous_hash` + `chain_head`; on next gather start, the writer verifies the prior file's chain head. A chain break emits `audit.chain_break.detected` (observability event) and **gather continues** — observability, not enforcement.

Gap 4 from `phase-arch-design.md` adds rotation checkpoints: every 100 gathers a `runs/checkpoints/<rollover_index>.json` checkpoint is written; older records may be archived under `runs/archive/<rollover_index>/`. This keeps the audit folder from growing unbounded over portfolio-scale gathers while preserving cross-rollover tamper-evidence.

This story is one of two stories that touch `audit_writer.py` (the other is implicit — no further Phase 2 stories touch audit). The extension is additive; existing Phase 0 record fields are unchanged.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"4+1 architectural views" "Logical view"` — `AuditWriter` class diagram with `chain_head_blake3` field.
  - `../phase-arch-design.md §"Goals" #14` — audit chain head as a named Phase-0 in-place edit category.
  - `../phase-arch-design.md §"Gap analysis"` Gap 4 — the rollover-checkpoint addition; every 100 gathers.
- **Phase ADRs:**
  - `../ADRs/0012-audit-chain-blake3-rolling-head.md` — ADR-0012 — full decision; `previous_hash` per record; verification at gather start; chain-break is observability only; gather completes normally.
- **Production ADRs:**
  - `../../../production/adrs/` — none directly; Phase 14's transparency-log work supersedes this in production.
- **Source design:**
  - `../final-design.md §"Components" §10 AuditWriter — rolling BLAKE3 chain head` — design statement.
  - `../final-design.md §"Failure modes & recovery"` — audit-chain-break row.
- **Existing code:**
  - `src/codegenie/audit_writer.py` (Phase 0 S2-XX) — extend the existing module; do not rewrite. (If the module name differs in Phase 0's actual layout, e.g., `audit/writer.py`, adapt the path accordingly.)
  - `src/codegenie/errors.py` — `AuditChainBreakDetected` (added in S1-01; observability marker, not raised).
  - `src/codegenie/logging.py` — `AUDIT_CHAIN_HEAD_ADVANCED`, `AUDIT_CHAIN_BREAK_DETECTED` (added in S1-01).

## Goal

Extend `src/codegenie/audit_writer.py` with a rolling BLAKE3 chain head — each `runs/<utc>-<short>.json` record carries `previous_hash` + `chain_head` fields; `verify_previous_chain_head()` runs at next gather start emitting `audit.chain_break.detected` on mismatch without failing the gather; every 100 gathers a `runs/checkpoints/<rollover_index>.json` is written and older records may be archived.

## Acceptance criteria

- [ ] `src/codegenie/audit_writer.py` adds two fields to the record schema: `previous_hash: str` (64-char hex BLAKE3 of the prior record's canonical byte serialization; `"genesis"` for the first record) and `chain_head: str` (BLAKE3 of this record's canonical byte serialization).
- [ ] `AuditWriter` exposes `verify_previous_chain_head() -> bool` which: reads the most recent `runs/<utc>-<short>.json`, recomputes its expected `previous_hash` (the BLAKE3 of *its* predecessor — read transitively), compares to the stored value, returns `True` on match.
- [ ] On `verify_previous_chain_head()` mismatch, the writer emits a structlog event with key `audit.chain_break.detected` carrying `previous_hash_expected`, `previous_hash_actual`, `chain_head_of_prior_record` fields; the gather **continues** (function returns `False`, never raises).
- [ ] `verify_previous_chain_head()` is called from the coordinator at gather start; on `False`, the coordinator emits the structured event and proceeds (no exception, no exit code change).
- [ ] On successful chain advance, the writer emits `audit.chain_head.advanced` with `chain_head: str`, `gather_id: str` fields.
- [ ] Every 100th successful gather writes `runs/checkpoints/<rollover_index>.json` containing `{first_gather_id, last_gather_id, chain_head_at_rollover, rollover_index, written_at_utc}`. `rollover_index` is the integer count of completed rollover rollovers; starts at 0; increments after each 100-gather window closes.
- [ ] Older records under `runs/<utc>-<short>.json` covered by a checkpoint **may** be archived to `runs/archive/<rollover_index>/<utc>-<short>.json` (a CLI flag `--audit-archive-on-rollover` opts in; default is to leave records in place — archival is operator opt-in per the documented audit-GC procedure).
- [ ] `tests/unit/audit/test_chain_head.py` ships ≥ 6 tests — chain head advances one per gather; `verify_previous_chain_head` returns `True` on intact chain; returns `False` on tampered prior record; emits `audit.chain_break.detected` on mismatch; gather completes (no exception); rollover checkpoint written at 100-gather boundary.
- [ ] `tests/adv/test_audit_chain_break_observability.py` ships — corrupts a prior `runs/*.json` file; asserts next gather emits `audit.chain_break.detected` and **exits 0** (per ADR-0012).
- [ ] Genesis record handling: the first-ever gather emits `previous_hash: "genesis"`; `verify_previous_chain_head()` on an empty `runs/` directory returns `True` without emitting the chain-break event.
- [ ] Existing Phase 0 audit record fields (`tool_digest`, per-probe metadata, cache decisions, sanitizer pass count) are unchanged; the diff is purely additive on the record schema.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write `tests/unit/audit/test_chain_head.py` first (red).
2. Write `tests/adv/test_audit_chain_break_observability.py` (red).
3. Extend `src/codegenie/audit_writer.py`:
   - Add `previous_hash: str` and `chain_head: str` fields to the Pydantic record model (`extra="forbid"` per Phase 0 discipline).
   - Add `_canonical_bytes(record: AuditRecord) -> bytes` that serializes deterministically (sorted keys, no whitespace, UTF-8) — this is the input to BLAKE3.
   - Add `verify_previous_chain_head() -> bool`:
     1. List `runs/*.json` sorted by mtime.
     2. If empty, return `True`.
     3. Read the most recent file.
     4. Read its `previous_hash` and locate the previous file.
     5. Recompute BLAKE3 over the previous file's canonical bytes.
     6. Compare; on mismatch, emit `audit.chain_break.detected` event; return `False`.
   - Extend the existing `write_record(...)` method to populate `previous_hash` from the prior record's `chain_head` (or `"genesis"` if none) and set `chain_head` for this record.
   - Add `_maybe_write_rollover_checkpoint(rollover_index, ...)` that triggers on every 100th successful write.
4. Add a `--audit-archive-on-rollover` CLI flag (extends `src/codegenie/cli.py`); when set and a rollover happens, move covered records under `runs/<utc>-<short>.json` into `runs/archive/<rollover_index>/`.
5. Coordinator (or CLI startup, depending on the existing call site) invokes `verify_previous_chain_head()` *before* dispatching probes; on `False`, log the structured event and continue (no abort).
6. Run pytest, ruff, mypy.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/audit/test_chain_head.py`.

```python
import json
from pathlib import Path

import pytest

from codegenie.audit_writer import AuditWriter


def test_genesis_record_has_previous_hash_genesis(tmp_path: Path):
    writer = AuditWriter(runs_dir=tmp_path)
    writer.write_record(gather_id="g0", payload={})
    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == 1
    rec = json.loads(files[0].read_text())
    assert rec["previous_hash"] == "genesis"
    assert len(rec["chain_head"]) == 64  # BLAKE3 hex


def test_chain_advances_one_per_gather(tmp_path: Path):
    writer = AuditWriter(runs_dir=tmp_path)
    writer.write_record(gather_id="g0", payload={})
    writer.write_record(gather_id="g1", payload={})
    files = sorted(tmp_path.glob("*.json"))
    recs = [json.loads(f.read_text()) for f in files]
    assert recs[1]["previous_hash"] == recs[0]["chain_head"]


def test_verify_returns_true_on_intact_chain(tmp_path: Path):
    writer = AuditWriter(runs_dir=tmp_path)
    writer.write_record(gather_id="g0", payload={})
    writer.write_record(gather_id="g1", payload={})
    assert writer.verify_previous_chain_head() is True


def test_verify_returns_false_on_tampered_prior(tmp_path: Path, caplog):
    writer = AuditWriter(runs_dir=tmp_path)
    writer.write_record(gather_id="g0", payload={"key": "original"})
    writer.write_record(gather_id="g1", payload={})
    # corrupt g0 after the fact
    g0_file = sorted(tmp_path.glob("*.json"))[0]
    rec = json.loads(g0_file.read_text())
    rec["payload"] = {"key": "tampered"}
    g0_file.write_text(json.dumps(rec))
    assert writer.verify_previous_chain_head() is False
    # event surfaced in logs
    assert any("audit.chain_break.detected" in r.getMessage() for r in caplog.records)


def test_verify_does_not_raise_on_break(tmp_path: Path):
    writer = AuditWriter(runs_dir=tmp_path)
    writer.write_record(gather_id="g0", payload={})
    # corrupt
    f = sorted(tmp_path.glob("*.json"))[0]
    rec = json.loads(f.read_text())
    rec["chain_head"] = "f" * 64  # bogus
    f.write_text(json.dumps(rec))
    # next gather verification must not raise
    writer.verify_previous_chain_head()  # returns False; no exception


def test_rollover_checkpoint_written_every_100_gathers(tmp_path: Path):
    writer = AuditWriter(runs_dir=tmp_path)
    for i in range(100):
        writer.write_record(gather_id=f"g{i}", payload={})
    cp_dir = tmp_path / "checkpoints"
    assert cp_dir.exists()
    cps = sorted(cp_dir.glob("*.json"))
    assert len(cps) == 1
    cp = json.loads(cps[0].read_text())
    assert cp["rollover_index"] == 0
    assert cp["first_gather_id"] == "g0"
    assert cp["last_gather_id"] == "g99"
```

```python
# tests/adv/test_audit_chain_break_observability.py
import json
import subprocess
import sys
from pathlib import Path


def test_chain_break_exits_zero_with_event(tmp_path: Path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    # seed a "prior gather" record with bogus chain head
    prior = runs / "20260101-aaaaaa.json"
    prior.write_text(json.dumps({
        "gather_id": "old", "previous_hash": "genesis", "chain_head": "f" * 64,
        "payload": {},
    }))
    # then corrupt it
    rec = json.loads(prior.read_text())
    rec["payload"] = {"k": "tampered"}
    prior.write_text(json.dumps(rec))
    # run codegenie gather (or invoke the coordinator startup directly)
    monkeypatch.setenv("CODEGENIE_RUNS_DIR", str(runs))
    res = subprocess.run(
        [sys.executable, "-m", "codegenie", "gather", "--dry-run"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0  # observability, not enforcement
    assert "audit.chain_break.detected" in (res.stdout + res.stderr)
```

Run; confirm failures (missing fields, methods). Commit as red marker.

### Green — make it pass

Extend `audit_writer.py` per the implementation outline. Use `blake3` (already in deps from Phase 0).

### Refactor — clean up

- `_canonical_bytes` must be **byte-deterministic**: sorted keys, no whitespace, UTF-8 encoding, no floats with platform-dependent representation. Use `json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("utf-8")`.
- The rollover-checkpoint shape is small and stable; document its schema in a leading comment.
- Module docstring extended with one paragraph naming ADR-0012, Gap 4, and the observability-only contract.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/audit_writer.py` | Extend record schema; add `verify_previous_chain_head`; add rollover-checkpoint logic |
| `src/codegenie/cli.py` | Add `--audit-archive-on-rollover` flag |
| `tests/unit/audit/test_chain_head.py` | New — ≥ 6 tests |
| `tests/adv/test_audit_chain_break_observability.py` | New — adversarial pin |

## Out of scope

- **Phase 14 transparency-log integration** — ADR-0012 names Phase 14 as the production-grade replacement; this story ships the lightweight in-tree mechanism.
- **`--strict-audit` flag** that would fail-gather on chain break — ADR-0012 names this as a future amendment; not in Phase 2.
- **Audit GC / pruning beyond the rollover archive** — operator concern, documented in the audit-module README; not a Phase 2 deliverable.
- **Cross-rollover tamper-evidence** (linking checkpoint N to checkpoint N-1) — Phase 14's transparency log handles this; the per-gather chain is one-deep by design.

## Notes for the implementer

- The observability-only contract is the load-bearing piece. Per Rule 12 (Fail loud), an operator who silently deletes a `runs/*.json` (legitimate housekeeping) gets a `chain_break.detected` event they must dismiss — but their gather **completes**. If you find yourself adding `raise AuditChainBreakDetected(...)` somewhere, you've drifted from ADR-0012. The `AuditChainBreakDetected` class is the **typed marker** for the event payload, never raised to the caller.
- BLAKE3 over canonical bytes — *not* over the file as-written. Reasoning: pretty-printing whitespace or key reordering should not invalidate the chain. `_canonical_bytes` strips that variability.
- Genesis record handling has a subtle edge case: an `.empty/` `runs/` directory should be indistinguishable from "never gathered before." Both produce `previous_hash: "genesis"`. If an operator deletes the most recent `runs/*.json` but leaves earlier ones, the chain is broken — that's the case `verify_previous_chain_head` catches.
- Rollover index increments **after** the 100-gather window closes — not per-gather. Off-by-one bugs here are easy. Tested explicitly by the `test_rollover_checkpoint_written_every_100_gathers` test; the assertion that the first checkpoint covers `g0`–`g99` pins the boundary.
- Archival is opt-in (`--audit-archive-on-rollover`). Default behavior: leave records in `runs/` even after rollover. The CLI flag flips the behavior. Reason: operators differ in their disk-budget tolerance; some want unbounded audit-trail retention.
- `verify_previous_chain_head()` is called at coordinator startup, *before* probe dispatch. The early call is intentional: it ensures the chain-break event lands in the gather's structlog stream rather than being orphaned in an audit-only log. Wire the call into `Coordinator.__aenter__` (or whatever the Phase 0 entry point is called).
- The runs-dir layout extends to `runs/checkpoints/` and (opt-in) `runs/archive/<rollover_index>/`. Document the layout in the audit-module README so future Phases (14, transparency log) inherit the same on-disk shape.
- `previous_hash` for the second record is the first record's `chain_head` (not the BLAKE3 of the first record computed at read time — they should be equal, but cache the stored value rather than recomputing per-read). The verifier *recomputes* to check, but the writer *stores* the prior's `chain_head` directly.
- This story is one of the four ADR-gated in-place edits Phase 2 makes to Phase 0/1 code. The PR description must cite ADR-0012 and confirm Phase 0's existing audit-record fields are unchanged (only the two new fields are appended).
- If the existing Phase 0 audit module name is `src/codegenie/audit/writer.py` rather than `src/codegenie/audit_writer.py`, adapt path; the surface is `AuditWriter` class. Do not refactor Phase 0's package layout to match this story's preferred name (Rule 3 — Surgical Changes).
