# Story S2-03 — Phase 4 chain-head compatibility check + `chain_head.bin` read/write port + `AuditChainCorrupted` startup refusal

**Step:** Step 2 — Implement `RetryLedger` and audit-chain extension
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-02, S1-04, S2-01, S2-02
**ADRs honored:** ADR-0005, ADR-0007, ADR-0011, ADR-0014
**Validated:** 2026-05-23 — see [`_validation/S2-03-phase4-chain-head-compat.md`](_validation/S2-03-phase4-chain-head-compat.md)

## Validation notes

Hardening landed twenty-one carryforward edits across four critic lenses (5 block, 13 harden, 3 nit). The headline find is the byte-size violation S2-01 hardening explicitly flagged for this validator pass (`"≠ 32 bytes"` → `"≠ 16 bytes"`; BLAKE3-128 per S1-04). Major edits:

1. **BLAKE3-128 / 16 bytes globally enforced** — `chain_head.bin` is 16 bytes, sentinel is `b"\x00" * 16`, golden fixture is 16 bytes. Every `32` literal in size checks rewritten to `16`; every `b"\x00" * 32` rewritten to `b"\x00" * 16`; Notes corrected ("default 256-bit, USED 128-bit per S1-04 contract"). The 32-bit-bigger fixture and `"half size = 16 bytes"` test inversion all fixed.
2. **`AuditChainCorrupted` structured-attribute discipline** — substring assertions (`"mismatch" in str(exc.value).lower()`, etc.) removed; new `.kind: Literal["phase4_head_mismatch", "phase4_head_missing", "phase4_head_wrong_size", "phase4_head_not_regular_file", "phase4_head_unreadable", "phase4_head_unexpected"]` values added additively to the existing S2-01 enum (block #2 of Consistency + block #2 of Test-Quality). `.row_type = None` for all (file-level, not row-level). Promoted `.gate_id: str | None` as a structured attribute.
3. **Write side of `chain_head.bin` pinned in scope** — arch line 948 says `chain_head.bin` is a Phase 5 *artifact* for Phase 7+ to read, but the draft only addressed the read side. Added `write_chain_head` + atomic-write discipline (tempfile → fsync → rename → dir-fsync, mirrors S2-01 AC-FS-1) and integrated into `RetryLedger.record` / `RetryLedger.record_pre_execute` post-append. Without this, Phase 6/7 inherit a Phase-4-stale file — silent chain drift (the exact failure ADR-0005 exists to prevent).
4. **Cross-phase shim port** — `chain_head_io.py` introduced under `src/codegenie/audit/` (neutral, not under one consumer's package — `gates/ → audit/` and `llm/ → audit/` both bind through the port; hexagonal seam). Module-level pure `write_chain_head` / `read_chain_head` functions. AC pins purity test, allowlist-imports, round-trip property, and atomic-write fsync-count.
5. **Pure functional core / imperative shell** — `_check_phase4_chain_head(on_disk: bytes | None, expected: ChainHead | None) -> None` extracted as a pure module-level helper; the `__init__` shell wraps file I/O around it. AST-walk purity test mirrors S2-01 AC-PH-1 / S2-02 AC-DR-4.
6. **Genesis-mode vacuous test fixed** — old test only asserted `head() == sentinel`, which would pass even if `__init__` silently read the disk. New test monkeypatches `Path.read_bytes` and asserts it was *never* called; mutation witness for "skip means don't touch disk."
7. **Fixture stability — default-mode equality assert** — old draft only had a `--regen` opt-in regenerator. New `test_committed_fixture_matches_phase4_writer_output` runs by default (no flag), calls Phase 4's writer with a frozen input list, and asserts byte-equality with the committed `tests/golden/phase4_chain_head.bin`. The regenerator is opt-in; the assertion is the default. Phase 4 drift fails CI before anyone runs `--regen`. Fixture-input list extracted to a module-level `Final[list[Phase4Event]]` for explicit cross-phase contract.
8. **`ChainHead` NewType (rule-of-three cleared)** — `ChainHead = NewType("ChainHead", bytes)` lands in `types/identifiers.py` per CLAUDE.md "Newtype identifiers when crossing ≥ 2 modules" (boundaries: `RetryLedger.__init__`, `chain_head_io.read_chain_head`, `chain_head_io.write_chain_head`, Phase 4 producer — 4 crossings). Mirrors S2-02 AC-NT-3 / S1-04 AttemptNumber. AST chokepoint test asserts `NewType("ChainHead", ...)` is defined exactly once.
9. **`BLAKE3_128_BYTES: Final[int] = 16` constant** — eliminated magic-number duplication; pinned in `gates/contract.py` next to S1-04's `^[0-9a-f]{32}$` regex. AST-walk forbids bare `16` literals in chain-head size checks.
10. **`_recover_chain_state` 3-tuple awareness** — S2-02 widened the return from 2-tuple to 3-tuple. `__init__` ordering pinned: file-read (Phase 4 chain-head verify) BEFORE in-memory state recovery, so a corrupted Phase 4 head fails-loud before any chain-internal work.
11. **`entries()` reader compatibility (S2-02 surface non-regression)** — `tests/gates/test_retry_ledger_entries.py` must remain green; the chain-head verify path does not touch JSONL row processing. AC explicitly runs the S2-02 test suite.
12. **Property tests added** — three new Hypothesis properties: (a) any 16-byte `b ≠ expected` raises `kind="phase4_head_mismatch"`; (b) any length ≠ 16 raises `kind="phase4_head_wrong_size"`; (c) `write_chain_head(p, x); read_chain_head(p) == x` round-trip identity.
13. **Adversarial widening** — parametrized byte-flip across {byte 0, byte 7, byte 15}; targeted size cases {0, 1, 8, 15, 17, 32, 64} bytes; symlink and not-a-regular-file rejection; unreadable file (mode 000) handled as `kind="phase4_head_unreadable"`.
14. **Determinism witness for regenerator** — second invocation produces byte-identical output (catches latent timestamp/randomness leakage in Phase 4 writer).
15. **structlog event field list pinned** — `gates.ledger.chain_head_verified` with explicit fields `gate_id` (str), `chain_head_hex` (8-char prefix, never full 32 chars). Mirrors S2-02 AC-LG-1.
16. **Regenerator pattern aligned with repo convention** — `CODEGENIE_REGEN_GOLDEN=1` env-var (consistent with S2-02), not a `--regen` pytest option. Default-mode runs the byte-equality assert; opt-in mode rewrites the fixture.
17. **Coverage gate AC** — `≥ 95% line / ≥ 90% branch` on `_check_phase4_chain_head` and `chain_head_io.py`, mirroring S2-01 AC-QG-5 / S2-02 AC-QG-7.
18. **Module-purity tests** — new `tests/audit/test_chain_head_io_purity.py` (allowlist: `__future__`, `os`, `errno`, `pathlib`, `typing`); extended `tests/gates/test_retry_ledger_purity.py` allowlist for the new helper.
19. **Idempotency AC** — re-constructing `RetryLedger` over an identical run_dir + prev_chain_head is a no-op (besides one structlog event); two sequential constructions both succeed without mutating disk.
20. **Effort sized M, not S** — cross-phase shim + write-side + ChainHead NewType + property/metamorphic tests + atomic-write semantics + new error kinds materially expanded the work (S2-01 was upgraded from S to M on similar grounds; S2-02 stayed S because it landed as 2 helpers + 1 method).
21. **Out-of-scope widened** — Operator forensic chain-head reset (`codegenie sandbox reset-chain --i-know-what-im-doing`) explicitly deferred to a roadmap item; Phase 4-side refactor consolidating its chain-head writer into the shim called out as a follow-up Phase 4 PR (additive only — Phase 4 keeps its in-line writer until then; the shim wraps both call sites once Phase 4 lands its consolidation PR).

**Forward flags for downstream:**

- **S5-02 (`GateRunner.run`):** No new contract — the chain-head write happens transparently inside `ledger.record(...)` / `ledger.record_pre_execute(...)`. GateRunner sees no API change.
- **S8-01 (`codegenie sandbox inspect`):** Will re-verify the chain head on every invocation by constructing a `RetryLedger(run_dir=..., gate_id=..., prev_chain_head=...)` (read-only). The public method `RetryLedger.verify_chain_head()` is exposed for that consumer.
- **Phase 4 follow-up PR:** Consolidate Phase 4's chain-head writer into `codegenie.audit.chain_head_io.write_chain_head`. This is additive — Phase 4 keeps its current code path until the consolidation PR; this story's regenerator test uses the shim's `write_chain_head` which (for now) the shim implements directly from `blake3` so the cross-phase compatibility is a *contract* on the bytes, not on a shared code path.
- **Phase 6 (LangGraph checkpointer):** Reads `chain_head.bin` to recover chain state on resume. The 16-byte BLAKE3-128 shape is now pinned with the `ChainHead` NewType — any future change requires amending ADR-0005 + S1-04 + this story.

## Context

Phase 4 emits BLAKE3-128-chained audit events (`solved_example.duplicate_skipped`, `engine_used` stamping) and writes the final chain head to `.codegenie/remediation/<run-id>/chain_head.bin` (16 raw bytes / BLAKE3-128). Phase 5's `RetryLedger` extends that same chain — every `record` and `record_pre_execute` appends a row to `attempts.jsonl` AND atomically updates `chain_head.bin` to the latest chain end (the artifact Phase 6 / Phase 7+ will consume per arch §Integration with Phase 6 line 948). If Phase 4's event shape drifts silently, Phase 5 would read an incompatible predecessor head and silently chain off it — the critic's roadmap §6 attack ("none of the three designs verified Phase 4's chain events produce entries Phase 5 will consume") is closed by this story.

The story lands three concerns at one cross-phase seam:

1. **Read-and-verify** Phase 4's `chain_head.bin` on `RetryLedger.__init__`; refuse to start on mismatch, missing file, wrong size, or wrong file type (symlink, dir, unreadable).
2. **Atomically write** `chain_head.bin` from inside `RetryLedger.record` / `record_pre_execute` so Phase 6+ can resume with confidence the file reflects the last appended row.
3. **A binary golden fixture** produced by Phase 4's *own* chain-head writer (via a shared port), with a default-mode byte-equality assertion in CI — so any Phase 4 PR that changes chain-head shape fails this story's test before anyone runs `--regen`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — RetryLedger` — `Internal structure`: `__init__` reads `prev_chain_head` from Phase 4's chain end; on mismatch raises `AuditChainCorrupted`.
  - `../phase-arch-design.md §Edge cases §11–12` — corrupted Phase 4 chain head causes `__init__` to raise.
  - `../phase-arch-design.md §Integration with Phase 6 line 948` — `chain_head.bin` is the artifact Phase 7+ reads.
  - `../phase-arch-design.md §Cross-phase boundary tests` — `tests/schema/test_phase4_chain_compat.py` regenerates the fixture and would fail loudly if Phase 4's shape drifts.
  - `../phase-arch-design.md §Goals §14` — "Audit chain extends Phase 4 head. Startup test refuses to run any gate if Phase 4 chain head does not match (`AuditChainCorrupted`)."
- **Phase ADRs:**
  - `../ADRs/0005-phase4-chain-head-compatibility.md` — the canonical contract.
  - `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — `pre_execute` marker rows participate in the chain; the read side must work whether the trailing row is a marker or an attempt.
  - `../ADRs/0011-no-verdict-cache-in-phase-5.md` — chain head is the only "this attempt happened" durable witness; no verdict cache.
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — replay strictness / fail-loud discipline; `AuditChainCorrupted` carries the same structured-attribute pattern.
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — context for why the chain must span boundaries.
  - `../../../production/adrs/0016-checkpointer-backend.md` — Phase 6 reads `chain_head.bin` to reconstruct state.
- **Source design:**
  - `../final-design.md §New ADRs implied — ADR-P5-005`.
- **Prior-story validation reports (READ FIRST):**
  - `_validation/S2-01-retry-ledger-blake3-chain.md` — block #5 / harden #21 file the byte-size carryforward this story closes; the structured-attribute pattern for `AuditChainCorrupted`; pure-helper extraction discipline.
  - `_validation/S2-02-pre-execute-marker-gap-1.md` — `entries()` reader, `_marker_pending` recovery (3-tuple `_recover_chain_state`), `row_type` discriminator, `SandboxSpecHash` NewType precedent for `ChainHead`.
- **Existing code:**
  - `src/codegenie/gates/retry_ledger.py` (from S2-01 + S2-02) — extend `__init__` to read/verify the file; integrate atomic write into `record` / `record_pre_execute`.
  - `src/codegenie/gates/errors.py` (from S1-01) — extend `AuditChainCorrupted.kind` Literal additively with new values for chain-head failure modes.
  - `src/codegenie/gates/contract.py` (from S1-04) — add `BLAKE3_128_BYTES: Final[int] = 16` constant.
  - `src/codegenie/types/identifiers.py` — add `ChainHead = NewType("ChainHead", bytes)`.
  - Phase 4 chain-head producer (search Phase 4 source under `src/codegenie/llm/` or `src/codegenie/fallback/`) — for THIS story, the shim under `src/codegenie/audit/chain_head_io.py` is the canonical writer. A follow-up Phase 4 PR will consolidate; not in scope here.

## Goal

Wire `RetryLedger.__init__` to read `.codegenie/remediation/<run-id>/chain_head.bin` (Phase 4's last write or this ledger's prior tail) through the cross-phase port `codegenie.audit.chain_head_io.read_chain_head`, verify it against the `prev_chain_head: ChainHead | None` constructor argument with structured-attribute `AuditChainCorrupted` raise on any failure, AND have every successful `record` / `record_pre_execute` atomically rewrite `chain_head.bin` to the new chain tail via `codegenie.audit.chain_head_io.write_chain_head` (tempfile → fsync → rename → dir-fsync). The story extends S2-01 + S2-02 *additively*: no edit to `Attempt`, no rewritten chain math, no change to existing public method signatures; only purely additive `Literal` extensions on `AuditChainCorrupted.kind` and `RetryLedger`'s new public method `verify_chain_head()`.

## Acceptance criteria

### A. Byte size (BLAKE3-128 per S1-04 HARDENED contract)

- [ ] **AC-A-1 — `BLAKE3_128_BYTES: Final[int] = 16`** is defined in `src/codegenie/gates/contract.py` (next to S1-04's `^[0-9a-f]{32}$` regex). Imported by `retry_ledger.py`, `audit/chain_head_io.py`, and every test fixture that mentions the chain-head byte length. An AST-walk under `src/codegenie/{gates,audit}/` asserts no bare `16` literal appears as a size check (regex match: `len\(.+?\)\s*[!=<>]=?\s*16` outside the constant declaration).
- [ ] **AC-A-2 — `ChainHead = NewType("ChainHead", bytes)`** lands in `src/codegenie/types/identifiers.py` with docstring `"BLAKE3-128 (16 bytes) of Phase 4's audit-chain tail; ADR-0005 cross-phase seam."`. An AST-walk test under `src/codegenie/` asserts `NewType("ChainHead", ...)` appears exactly once (mirrors S2-02 AC-NT-4 / S1-04 AttemptNumber). `RetryLedger.__init__(..., prev_chain_head: ChainHead | None)` and `audit/chain_head_io.{read,write}_chain_head` annotations use it.
- [ ] **AC-A-3 — `chain_head.bin` is 16 bytes** in every read, write, and test fixture. The golden fixture `tests/golden/phase4_chain_head.bin` is 16 bytes. The genesis sentinel is `b"\x00" * 16`.

### B. Read port (`audit/chain_head_io.read_chain_head`)

- [ ] **AC-B-1 — `read_chain_head(path: Path) -> ChainHead`** is a pure module-level function in `src/codegenie/audit/chain_head_io.py`. Returns the file bytes if and only if the path exists, is a regular file (`Path.is_file() and not Path.is_symlink()`), is exactly `BLAKE3_128_BYTES` bytes, and is readable. Otherwise raises `AuditChainCorrupted` with one of: `kind="phase4_head_missing"` (file does not exist), `kind="phase4_head_not_regular_file"` (symlink, dir, special file), `kind="phase4_head_wrong_size"` (`len != 16`), `kind="phase4_head_unreadable"` (`PermissionError` or other `OSError`). All four raises set `.row_type=None`, `.row_index=0`, `.attempt_id=None`; `.gate_id` is None at the port layer (gate context is applied at the `RetryLedger` shell).
- [ ] **AC-B-2 — `read_chain_head` is pure of process state** — given fixed file contents, two consecutive calls return byte-identical results; no caching, no global state. AST-walk asserts no module-level mutable state.

### C. Write port (`audit/chain_head_io.write_chain_head`)

- [ ] **AC-C-1 — `write_chain_head(path: Path, head: ChainHead) -> None`** writes `head` to `path` atomically: write to `path.with_suffix(".bin.tmp")`, `os.fsync` the tmp fd, `os.rename(tmp, path)`, `os.fsync` the parent directory fd. Mirrors S2-01 AC-FS-1 (file fd + dir fd fsync; `errno.EINVAL` swallow on macOS for directory fsync).
- [ ] **AC-C-2 — `write_chain_head` validates `len(head) == BLAKE3_128_BYTES`** *before* opening any file handle; mismatch raises `ValueError(f"chain head must be 16 bytes; got {len(head)}")`. (Defensive — the NewType is a type-checker hint, not a runtime gate.)
- [ ] **AC-C-3 — Atomic-write property**: a partial-crash scenario (process killed between tmp-file write and rename) leaves either the prior `chain_head.bin` intact OR the new file fully written — never a truncated file. Test: monkeypatch `os.rename` to raise `KeyboardInterrupt`, attempt `write_chain_head(p, b"\xff" * 16)` on a pre-existing `p` with `b"\x00" * 16`; assert the file still reads `b"\x00" * 16` afterward.
- [ ] **AC-C-4 — Round-trip property** (Hypothesis): for any `head: bytes` of length 16, `write_chain_head(p, ChainHead(head)); read_chain_head(p) == head`.
- [ ] **AC-C-5 — Mocked `os.fsync` call count** — one fsync on the tmp file fd, one fsync on the parent directory fd. Structural test mirrors S2-01 AC-FS-1.

### D. `RetryLedger` integration — verify on `__init__`

- [ ] **AC-D-1 — `RetryLedger.__init__(run_dir, gate_id, prev_chain_head)` calls `self._verify_phase4_chain_head()` AFTER manifest handling and BEFORE `_recover_chain_state`**. The order is: validate `prev_chain_head` length → create `_gate_dir` → manifest first-write / match-or-raise (S2-01 AC-MF-*) → **verify `chain_head.bin`** → `_recover_chain_state` (S2-02 3-tuple) → verify recovered chain root against `prev_chain_head` (S2-01 AC-RR-2).
- [ ] **AC-D-2 — `_verify_phase4_chain_head(run_dir, expected)` is the shell**, delegating logic to the pure module-level helper `_check_phase4_chain_head(on_disk: bytes | None, expected: ChainHead | None) -> None`. The shell does the file read via `read_chain_head` (which itself raises with the right `kind` on missing/wrong-size/not-regular-file/unreadable); on success, it calls `_check_phase4_chain_head(bytes_read, expected)` which raises `AuditChainCorrupted(kind="phase4_head_mismatch", gate_id=self._gate_id, ...)` when both arguments are non-None and unequal.
- [ ] **AC-D-3 — Pure helper purity test** — `tests/gates/test_retry_ledger_purity.py` AST-walks `retry_ledger.py` and asserts `_check_phase4_chain_head` is at module top level (not inside `ClassDef`), takes only `on_disk: bytes | None` and `expected: ChainHead | None` (no `self`, no I/O, no logging). Mirrors S2-01 AC-PH-1.
- [ ] **AC-D-4 — Genesis mode is opt-in via the `prev_chain_head=None` kwarg.** If `prev_chain_head is None`: `read_chain_head` is NOT called (the file is not even read). Test (the mutation witness): monkeypatch `audit.chain_head_io.read_chain_head` to a sentinel `Mock`, construct `RetryLedger(run_dir=tmp, gate_id="g", prev_chain_head=None)`, assert `mock.call_count == 0`.
- [ ] **AC-D-5 — `prev_chain_head is not None` AND `chain_head.bin` exists AND bytes match** — `__init__` succeeds; one structlog event `gates.ledger.chain_head_verified` is emitted with fields exactly `{"event": "gates.ledger.chain_head_verified", "gate_id": <str>, "chain_head_hex": <8-char hex prefix>}`. `len(captured["chain_head_hex"]) == 8`.
- [ ] **AC-D-6 — `prev_chain_head is not None` AND mismatch** — raises `AuditChainCorrupted(kind="phase4_head_mismatch", gate_id=<gate_id>, row_index=0, row_type=None, attempt_id=None)`. The mismatch test asserts on `.kind` and `.gate_id` as structured attributes; **no substring assertion on `str(exc.value)`**.
- [ ] **AC-D-7 — `prev_chain_head is not None` AND missing file** — `read_chain_head` raises `AuditChainCorrupted(kind="phase4_head_missing")`; the shell re-raises with `.gate_id` populated. Tests assert `exc.value.kind == "phase4_head_missing"` AND `exc.value.gate_id == "stage6_validate"`.
- [ ] **AC-D-8 — `prev_chain_head is not None` AND wrong size** — `read_chain_head` raises `AuditChainCorrupted(kind="phase4_head_wrong_size")`. Tests assert `.kind` structured attribute. Parametrized cases: file is `[0, 1, 8, 15, 17, 32, 64]` bytes — all raise. (Note: `0` is also covered by `phase4_head_missing` semantics if the file does not exist; the `0` case here means a file that exists with zero bytes.)
- [ ] **AC-D-9 — `prev_chain_head is not None` AND `chain_head.bin` is a symlink** — raises `AuditChainCorrupted(kind="phase4_head_not_regular_file")`. Defensive against zip-slip-style attack surface (ADR-0008 codebase precedent). Test creates a symlink to a 16-byte file in `tmp_path` and asserts the raise.
- [ ] **AC-D-10 — `prev_chain_head is not None` AND file unreadable** (`mode=0o000`) — raises `AuditChainCorrupted(kind="phase4_head_unreadable")`. Test sets `os.chmod(path, 0)` (skipped on Windows where chmod semantics differ).
- [ ] **AC-D-11 — Idempotent re-construction** — constructing `RetryLedger(run_dir=p, gate_id="g", prev_chain_head=h)` twice over the same `p` with a matching `chain_head.bin` succeeds both times; no disk mutation between calls (`os.stat(p / "chain_head.bin").st_mtime_ns` byte-equal before and after the second construction).

### E. `RetryLedger` integration — write on `record` / `record_pre_execute`

- [ ] **AC-E-1 — `RetryLedger.record(attempt)` writes `chain_head.bin = bytes.fromhex(attempt.chain_hash)` atomically AFTER the JSONL append.** Order: validate → canonical JSON → BLAKE3 chain → atomic-append JSONL row (fsync file + fsync dir, S2-01) → `write_chain_head(run_dir / "chain_head.bin", ChainHead(bytes.fromhex(chain_hash)))` (fsync tmp + fsync dir). On a crash between JSONL append and chain-head write, the JSONL is durable and the next `__init__` rebuilds the chain head from `_recover_chain_state`'s `last_chain_hash` — the chain-head file is a *cache* of the last row's hash, not an independent source of truth. (Test asserts: kill after JSONL fsync, before `write_chain_head`; restart, verify chain head is correctly rebuilt.)
- [ ] **AC-E-2 — `RetryLedger.record_pre_execute(...)` writes `chain_head.bin = bytes.fromhex(marker.chain_hash)` atomically AFTER the JSONL append.** Same discipline as AC-E-1; marker rows participate in the chain head.
- [ ] **AC-E-3 — Read-back after write equality** — after `ledger.record(a)`, `read_chain_head(run_dir / "chain_head.bin")` returns `bytes.fromhex(a.chain_hash)`.
- [ ] **AC-E-4 — `verify_chain_head()` public method on `RetryLedger`** — `verify_chain_head() -> None` re-runs the read-side check on demand (against `self._prev_chain_head` if non-None; no-op if None — same semantics as `__init__`). S8-01 will consume this. Idempotent on success.
- [ ] **AC-E-5 — `head()` semantics unchanged** — after `record` or `record_pre_execute`, `head()` returns the same 16 bytes that were just written to `chain_head.bin`. Test asserts `ledger.head() == read_chain_head(run_dir / "chain_head.bin")` after each record.

### F. Genesis-mode safety

- [ ] **AC-F-1 — `prev_chain_head is None` AND no `chain_head.bin` exists** — `__init__` succeeds (no read attempt per AC-D-4); `head()` returns `b"\x00" * 16`. Test asserts the sentinel and that `Path.read_bytes` was never called on `run_dir / "chain_head.bin"`.
- [ ] **AC-F-2 — `prev_chain_head is None` AND `chain_head.bin` exists (stale file from prior run)** — `__init__` does NOT read the file (per AC-D-4 — genesis means "skip"). After the first `record` / `record_pre_execute`, the file is overwritten via the atomic `write_chain_head`. Test: write `b"\xff" * 16` to `chain_head.bin` first, construct `RetryLedger(prev_chain_head=None)`, assert no raise; assert file was NOT read; record one attempt; assert file now equals `bytes.fromhex(attempt.chain_hash)`. (Caller is explicitly opting into "ignore on-disk state" by passing None.)

### G. Cross-phase golden fixture + Phase 4 writer parity

- [ ] **AC-G-1 — Phase 4 fixture-input list** is a module-level `Final[list[Phase4Event]]` constant `_FIXTURE_INPUT_EVENTS` in `tests/schema/test_phase4_chain_compat.py` with docstring: "Deserialized through Phase 4's chain-head writer, MUST produce the bytes in tests/golden/phase4_chain_head.bin. Any Phase 4 chain-row-shape change requires regeneration via CODEGENIE_REGEN_GOLDEN=1." Frozen timestamps; deterministic ordering.
- [ ] **AC-G-2 — Default-mode byte-equality assertion** — `tests/schema/test_phase4_chain_compat.py::test_committed_fixture_matches_phase4_writer_output` runs WITHOUT any flag/env-var, calls Phase 4's chain-head writer (via the `chain_head_io.write_chain_head` shim with the fixture-input list reduced through the chain math), computes the bytes in-process, and asserts byte-equality against `tests/golden/phase4_chain_head.bin`. **This is the cross-phase compat gate.** A Phase 4 PR that changes chain-row shape FAILS THIS TEST in CI, before anyone runs `CODEGENIE_REGEN_GOLDEN=1`.
- [ ] **AC-G-3 — Opt-in regenerator** — `test_regenerate_fixture` runs only when `os.environ.get("CODEGENIE_REGEN_GOLDEN") == "1"`; otherwise skips with reason `"opt-in via CODEGENIE_REGEN_GOLDEN=1"`. The env-var pattern is consistent with S2-02 AC-GF-2 across the repo's golden-fixture suite. **A `pytest_addoption` `--regen` flag is NOT used** (env-var is more explicit and harder to silently propagate via `pytest.ini`).
- [ ] **AC-G-4 — Regenerator determinism witness** — calling the in-process bytes-computation twice in a single test invocation produces byte-identical outputs (catches latent timestamp/randomness in the writer). `tests/schema/test_phase4_chain_compat.py::test_phase4_writer_is_deterministic`.
- [ ] **AC-G-5 — CI does not silently regenerate** — meta-test in `tests/schema/test_no_silent_regen.py`: run the entire `tests/schema/` directory without `CODEGENIE_REGEN_GOLDEN`, capture `os.stat(golden_path).st_mtime_ns` before and after; assert unchanged. Belt-and-suspenders for AC-G-3.
- [ ] **AC-G-6 — Fixture path stability** — `tests/golden/phase4_chain_head.bin` lives at the canonical repo-root-relative path. A `conftest.py` fixture `golden_phase4_chain_head_path` resolves from `pytest`'s `rootdir`, NOT from `__file__.parent.parent / ...` (which would break under future directory reorganization).

### H. Adversarial tamper coverage

- [ ] **AC-H-1 — Parametrized byte-flip across positions** — `tests/adversarial/test_phase4_chain_head_compat.py::test_byte_flip[byte_index]` parametrized across `[0, 7, 15]` (first, middle, last byte) and across two mutations `[xor_0x01, xor_0xff]` — 6 cases total. Each flips one byte of the committed golden fixture, writes the result to `tmp_path / "chain_head.bin"`, attempts `RetryLedger(prev_chain_head=golden_bytes)`, asserts `exc.value.kind == "phase4_head_mismatch"`. Mutation-witnesses for any impl that compares only a prefix/suffix or hashes the buffer instead of comparing it byte-equally.
- [ ] **AC-H-2 — Parametrized wrong-size cases** — `test_wrong_size[n_bytes]` parametrized across `[0, 1, 8, 15, 17, 32, 64]`. Includes the *old draft's mistake size* (32 bytes) — a regression toward "BLAKE3-256" would PASS the old AC and FAIL this one.
- [ ] **AC-H-3 — Symlink-rejection adversarial** — `test_chain_head_bin_symlink_rejected` creates a symlink in `tmp_path` pointing to a valid 16-byte file, asserts the raise `kind="phase4_head_not_regular_file"`.
- [ ] **AC-H-4 — Empty-file adversarial** — `test_chain_head_bin_empty_file_raises` creates a 0-byte file, asserts `kind="phase4_head_wrong_size"`.
- [ ] **AC-H-5 — Unreadable-file adversarial** — `test_chain_head_bin_unreadable_raises` writes a valid file, chmods it `0o000`, asserts `kind="phase4_head_unreadable"`. Skipped on Windows.

### I. Property tests (Hypothesis)

- [ ] **AC-I-1 — Mismatch property**: `@given(binary(min_size=16, max_size=16).filter(lambda b: b != expected))` — for any 16-byte `b ≠ expected`, writing `b` to `chain_head.bin` and constructing `RetryLedger(prev_chain_head=ChainHead(expected))` raises `AuditChainCorrupted(kind="phase4_head_mismatch")`.
- [ ] **AC-I-2 — Wrong-size property**: `@given(binary(min_size=0, max_size=64).filter(lambda b: len(b) != 16 and len(b) > 0))` — any non-empty file with size ≠ 16 raises `kind="phase4_head_wrong_size"`. (Size-0 is handled by AC-H-4 / AC-D-7's "missing" semantics; this property excludes it for clarity.)
- [ ] **AC-I-3 — Round-trip identity property**: `@given(binary(min_size=16, max_size=16))` — `write_chain_head(p, ChainHead(b)); read_chain_head(p) == b`.
- [ ] **AC-I-4 — `_check_phase4_chain_head` purity property** — given a fixed `chain_head.bin`, `RetryLedger(prev_chain_head=A)` raises iff `RetryLedger(prev_chain_head=B)` raises and `A == on_disk` iff `B == on_disk`. Test constructs three ledgers (A, B, A) over the same `tmp_path / "chain_head.bin"` and asserts the raise/pass pattern is consistent — catches hidden caching across constructions.

### J. Exception attribute discipline

- [ ] **AC-J-1 — `AuditChainCorrupted.kind` Literal extension is additive** — `gates/errors.py` widens the existing Literal with `"phase4_head_mismatch", "phase4_head_missing", "phase4_head_wrong_size", "phase4_head_not_regular_file", "phase4_head_unreadable", "phase4_head_unexpected"`. The previous S2-01 / S2-02 values are unchanged. Test: `typing.get_args(typing.get_type_hints(AuditChainCorrupted)["kind"])` is a superset of both prior sets and contains all 6 new values.
- [ ] **AC-J-2 — `AuditChainCorrupted.gate_id: str | None`** is a new structured attribute (additive; defaults `None` so S2-01 / S2-02 call sites are unaffected). Test: `exc.value.gate_id == "stage6_validate"` for all D-* test asserts; `exc.value.gate_id is None` for direct `read_chain_head(...)` calls (port-layer raises before gate context is applied).
- [ ] **AC-J-3 — No substring assertion on `str(exc.value)` anywhere in this story's tests.** A `pytest --collect-only` grep over `tests/{gates,adversarial,schema,audit}/test_*chain_head*.py` for `in str(exc` returns zero matches; an AST-walk test in `tests/fence/` enforces this for the new test files.

### K. structlog event surface

- [ ] **AC-K-1 — `gates.ledger.chain_head_verified` event** is emitted exactly once per successful `__init__` (when `prev_chain_head is not None`). Field set is exactly `{"event": "gates.ledger.chain_head_verified", "gate_id": <str>, "chain_head_hex": <str of length 8>}` — no full hex, no expected/on_disk hex pair (leak-safe per S2-02 AC-LG-1).
- [ ] **AC-K-2 — No structlog event emitted in genesis mode** (`prev_chain_head is None`). The "skip" path is genuinely silent at the gate layer — a debug-level event in the port layer is acceptable but the gate-layer `gates.ledger.chain_head_verified` is gated on `prev_chain_head is not None`.

### L. Module purity + dependencies

- [ ] **AC-L-1 — `tests/audit/test_chain_head_io_purity.py`** AST-walks `src/codegenie/audit/chain_head_io.py` imports against allowlist `{__future__, os, errno, pathlib, typing, codegenie.errors, codegenie.gates.errors, codegenie.types.identifiers, codegenie.gates.contract}`. Forbids `subprocess`, `requests`, `urllib`, `langchain`, etc. Mirrors S2-01 AC-MP-1.
- [ ] **AC-L-2 — `tests/gates/test_retry_ledger_purity.py`** allowlist widens by `codegenie.audit.chain_head_io`. Asserts `_check_phase4_chain_head` is module top-level.

### M. Files-to-touch + quality gates

- [ ] **AC-M-1 — Files-to-touch table is complete** — every file the executor must create or edit is listed; no AC references a file not in the table.
- [ ] **AC-M-2 — S2-02 surface non-regression** — `pytest tests/gates/test_retry_ledger_entries.py tests/gates/test_pre_execute_marker.py tests/gates/test_retry_ledger_resume.py` is part of this story's CI suite and passes green. `entries()` and `_marker_pending` recovery behavior is unchanged.
- [ ] **AC-M-3 — Coverage gate** — `≥ 95% line / ≥ 90% branch` on `src/codegenie/audit/chain_head_io.py` AND `src/codegenie/gates/retry_ledger.py::_check_phase4_chain_head`. Mirrors S2-01 AC-QG-5 / S2-02 AC-QG-7.
- [ ] **AC-M-4 — `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/{gates,audit,types}`** pass.
- [ ] **AC-M-5 — Test suite green** — `pytest tests/gates/test_retry_ledger_chain_compat.py tests/adversarial/test_phase4_chain_head_compat.py tests/schema/test_phase4_chain_compat.py tests/audit/test_chain_head_io.py tests/audit/test_chain_head_io_purity.py tests/gates/test_retry_ledger_entries.py tests/gates/test_retry_ledger_resume.py tests/schema/test_no_silent_regen.py` all pass.
- [ ] **AC-M-6 — Public re-exports** — `from codegenie.audit import write_chain_head, read_chain_head` succeeds; `from codegenie.types.identifiers import ChainHead` succeeds; `from codegenie.gates.contract import BLAKE3_128_BYTES` succeeds; one-line import test in `tests/audit/test_exports.py`.

## Implementation outline

1. **`src/codegenie/types/identifiers.py`** — add `ChainHead = NewType("ChainHead", bytes)` with the docstring above. One-line additive edit; mirrors S1-04 / S2-02 NewType placements.
2. **`src/codegenie/gates/contract.py`** — add `BLAKE3_128_BYTES: Final[int] = 16` next to the existing S1-04 regex / `Attempt` model.
3. **`src/codegenie/gates/errors.py`** — extend `AuditChainCorrupted.kind` Literal additively with the 6 new values; add `gate_id: str | None = None` as a new structured attribute on the exception (additive; defaults `None`).
4. **`src/codegenie/audit/__init__.py`** — new package; one-line re-export `from codegenie.audit.chain_head_io import read_chain_head, write_chain_head`.
5. **`src/codegenie/audit/chain_head_io.py`** — new module. Module-level pure `read_chain_head(path: Path) -> ChainHead` (with `kind` mapping per AC-B-1) and `write_chain_head(path: Path, head: ChainHead) -> None` (atomic write per AC-C-1, validates `len(head) == BLAKE3_128_BYTES`).
6. **`src/codegenie/gates/retry_ledger.py`** — extend:
   - Module-level pure helper `_check_phase4_chain_head(on_disk: bytes | None, expected: ChainHead | None) -> None` per AC-D-2. Branches: `(None, None) → return`; `(None, expected) → AuditChainCorrupted(kind="phase4_head_missing")` (but only if shell didn't already raise from `read_chain_head`); `(on_disk, None) → return` (genesis-skip; shell shouldn't have read); `(on_disk, expected)` with `on_disk == expected → return`; else `AuditChainCorrupted(kind="phase4_head_mismatch")`.
   - `RetryLedger.__init__` extended with `self._verify_phase4_chain_head()` per AC-D-1; `_verify_phase4_chain_head` shell calls `read_chain_head` (port raises with port-layer `kind`), re-raises with `.gate_id = self._gate_id` populated, then calls `_check_phase4_chain_head` for the mismatch case.
   - `RetryLedger.record` and `RetryLedger.record_pre_execute` extended with `write_chain_head(self._run_dir / "chain_head.bin", ChainHead(bytes.fromhex(new_chain_hash)))` per AC-E-1 / AC-E-2 — AFTER the JSONL fsync, so the JSONL is the source of truth and `chain_head.bin` is a cache.
   - New public `verify_chain_head(self) -> None` method per AC-E-4.
7. **`tests/audit/test_chain_head_io.py`** — covers AC-B-* and AC-C-* (read port + write port + atomic-write + round-trip property + fsync call count).
8. **`tests/audit/test_chain_head_io_purity.py`** — purity test per AC-L-1.
9. **`tests/audit/test_exports.py`** — one-line import test per AC-M-6.
10. **`tests/gates/test_retry_ledger_chain_compat.py`** — covers AC-D-* (happy/sad paths + genesis-mode mutation witness + idempotent re-construction).
11. **`tests/gates/test_retry_ledger_chain_head_write.py`** — covers AC-E-* (write-after-record, read-back equality, post-marker write).
12. **`tests/gates/test_retry_ledger_chain_head_properties.py`** — covers AC-I-* (Hypothesis properties).
13. **`tests/adversarial/test_phase4_chain_head_compat.py`** — covers AC-H-* (parametrized byte-flip, wrong-size, symlink, empty, unreadable).
14. **`tests/schema/test_phase4_chain_compat.py`** — covers AC-G-* (default-mode byte-equality assert + opt-in regenerator + determinism witness + fixture-input list as module constant).
15. **`tests/schema/test_no_silent_regen.py`** — covers AC-G-5 (meta-test for mtime stability).
16. **`tests/golden/phase4_chain_head.bin`** — the 16-byte committed binary fixture (produced by running the regenerator once).
17. **`tests/conftest.py`** — add `golden_phase4_chain_head_path` fixture resolving from `pytest`'s `rootdir`.
18. **Coverage gate config** — update `pyproject.toml`'s coverage section or per-test `--cov` invocations to include the new modules in the `≥ 95/90` enforcement.

## TDD plan — red / green / refactor

### Red — write the failing test first

Three red files together cover the structural contract; the property and adversarial files come in second-wave.

```python
# tests/gates/test_retry_ledger_chain_compat.py
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import structlog

from codegenie.audit.chain_head_io import read_chain_head, write_chain_head
from codegenie.gates.contract import BLAKE3_128_BYTES
from codegenie.gates.errors import AuditChainCorrupted
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.types.identifiers import ChainHead


def _golden(golden_phase4_chain_head_path: Path) -> ChainHead:
    raw = golden_phase4_chain_head_path.read_bytes()
    assert len(raw) == BLAKE3_128_BYTES, "AC-A-3: golden fixture must be 16 bytes (BLAKE3-128)"
    return ChainHead(raw)


def test_happy_path_with_golden_fixture(
    tmp_path: Path, golden_phase4_chain_head_path: Path
) -> None:
    """AC-A-3, AC-D-1, AC-D-5: chain_head.bin matching prev_chain_head → ledger constructs; event emitted."""
    expected = _golden(golden_phase4_chain_head_path)
    write_chain_head(tmp_path / "chain_head.bin", expected)

    with structlog.testing.capture_logs() as cap:
        ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=expected)

    assert ledger.head() == expected
    verified = [e for e in cap if e["event"] == "gates.ledger.chain_head_verified"]
    assert len(verified) == 1, "AC-D-5: exactly one structlog event"
    assert verified[0]["gate_id"] == "stage6_validate"
    assert len(verified[0]["chain_head_hex"]) == 8, "AC-K-1: 8-char prefix, never full 32 hex"


def test_mismatch_raises_with_structured_kind(
    tmp_path: Path, golden_phase4_chain_head_path: Path
) -> None:
    """AC-D-6, AC-J-1, AC-J-2: structured attributes, no substring asserts."""
    expected = _golden(golden_phase4_chain_head_path)
    on_disk = bytes(b ^ 0x01 for b in expected)  # flip LSB of every byte
    write_chain_head(tmp_path / "chain_head.bin", ChainHead(on_disk))

    with pytest.raises(AuditChainCorrupted) as exc:
        RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=expected)
    assert exc.value.kind == "phase4_head_mismatch"
    assert exc.value.gate_id == "stage6_validate"
    assert exc.value.row_type is None
    assert exc.value.attempt_id is None


def test_missing_file_raises_with_kind_phase4_head_missing(
    tmp_path: Path, golden_phase4_chain_head_path: Path
) -> None:
    """AC-D-7: missing file → structured kind."""
    expected = _golden(golden_phase4_chain_head_path)
    # Do NOT write chain_head.bin.
    with pytest.raises(AuditChainCorrupted) as exc:
        RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=expected)
    assert exc.value.kind == "phase4_head_missing"
    assert exc.value.gate_id == "stage6_validate"


@pytest.mark.parametrize("n_bytes", [0, 1, 8, 15, 17, 32, 64])
def test_wrong_size_raises_with_kind_phase4_head_wrong_size(
    tmp_path: Path, golden_phase4_chain_head_path: Path, n_bytes: int
) -> None:
    """AC-D-8, AC-H-2: parametrized wrong sizes including the old draft's mistake size (32)."""
    expected = _golden(golden_phase4_chain_head_path)
    (tmp_path / "chain_head.bin").write_bytes(b"\xff" * n_bytes)

    with pytest.raises(AuditChainCorrupted) as exc:
        RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=expected)
    assert exc.value.kind == "phase4_head_wrong_size"


def test_genesis_mode_does_not_read_disk(tmp_path: Path) -> None:
    """AC-D-4, AC-F-1: mutation witness — Path.read_bytes NEVER called when prev_chain_head=None."""
    # Plant a poisoned file to prove the read is skipped.
    (tmp_path / "chain_head.bin").write_bytes(b"\xff" * 16)

    with patch("codegenie.audit.chain_head_io.read_chain_head", new=MagicMock()) as mocked:
        ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    assert mocked.call_count == 0, "AC-D-4: genesis mode must NOT call read_chain_head"
    assert ledger.head() == b"\x00" * BLAKE3_128_BYTES, "AC-F-1: 16-byte sentinel"


def test_chain_head_bin_symlink_rejected(
    tmp_path: Path, golden_phase4_chain_head_path: Path
) -> None:
    """AC-D-9, AC-H-3: symlink → kind=phase4_head_not_regular_file."""
    expected = _golden(golden_phase4_chain_head_path)
    target = tmp_path / "real.bin"
    write_chain_head(target, expected)
    (tmp_path / "chain_head.bin").symlink_to(target)

    with pytest.raises(AuditChainCorrupted) as exc:
        RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=expected)
    assert exc.value.kind == "phase4_head_not_regular_file"


@pytest.mark.skipif(os.name == "nt", reason="chmod semantics differ on Windows")
def test_chain_head_bin_unreadable_raises(
    tmp_path: Path, golden_phase4_chain_head_path: Path
) -> None:
    """AC-D-10, AC-H-5: chmod 0o000 → kind=phase4_head_unreadable."""
    expected = _golden(golden_phase4_chain_head_path)
    path = tmp_path / "chain_head.bin"
    write_chain_head(path, expected)
    os.chmod(path, 0o000)
    try:
        with pytest.raises(AuditChainCorrupted) as exc:
            RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=expected)
        assert exc.value.kind == "phase4_head_unreadable"
    finally:
        os.chmod(path, 0o644)


def test_idempotent_re_construction(
    tmp_path: Path, golden_phase4_chain_head_path: Path
) -> None:
    """AC-D-11: two constructions over identical state → no disk mutation between them."""
    expected = _golden(golden_phase4_chain_head_path)
    write_chain_head(tmp_path / "chain_head.bin", expected)

    RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=expected)
    mtime_before = (tmp_path / "chain_head.bin").stat().st_mtime_ns
    RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=expected)
    mtime_after = (tmp_path / "chain_head.bin").stat().st_mtime_ns
    assert mtime_before == mtime_after, "AC-D-11: no rewrite on idempotent re-construction"
```

```python
# tests/gates/test_retry_ledger_chain_head_properties.py
from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from codegenie.audit.chain_head_io import read_chain_head, write_chain_head
from codegenie.gates.contract import BLAKE3_128_BYTES
from codegenie.gates.errors import AuditChainCorrupted
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.types.identifiers import ChainHead

EXPECTED = ChainHead(bytes(range(16)))  # arbitrary fixed 16-byte sentinel


@given(st.binary(min_size=16, max_size=16).filter(lambda b: b != EXPECTED))
def test_mismatch_property(tmp_path_factory, b: bytes) -> None:
    """AC-I-1: any 16-byte b ≠ EXPECTED raises phase4_head_mismatch."""
    tmp_path = tmp_path_factory.mktemp("rl")
    write_chain_head(tmp_path / "chain_head.bin", ChainHead(b))
    with pytest.raises(AuditChainCorrupted) as exc:
        RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=EXPECTED)
    assert exc.value.kind == "phase4_head_mismatch"


@given(st.binary(min_size=1, max_size=64).filter(lambda b: len(b) != 16))
def test_wrong_size_property(tmp_path_factory, b: bytes) -> None:
    """AC-I-2: any non-empty length ≠ 16 raises phase4_head_wrong_size."""
    tmp_path = tmp_path_factory.mktemp("rl")
    (tmp_path / "chain_head.bin").write_bytes(b)
    with pytest.raises(AuditChainCorrupted) as exc:
        RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=EXPECTED)
    assert exc.value.kind == "phase4_head_wrong_size"


@given(st.binary(min_size=16, max_size=16))
def test_roundtrip_property(tmp_path_factory, b: bytes) -> None:
    """AC-C-4, AC-I-3: write then read returns identical bytes."""
    tmp_path = tmp_path_factory.mktemp("rl")
    p = tmp_path / "chain_head.bin"
    write_chain_head(p, ChainHead(b))
    assert read_chain_head(p) == b
```

```python
# tests/schema/test_phase4_chain_compat.py
"""Cross-phase compatibility: Phase 4's chain-head writer ↔ Phase 5's reader.

AC-G-1..AC-G-5. The default-mode test (test_committed_fixture_matches_phase4_writer_output)
is the cross-phase compat gate — it fails CI when Phase 4 chain-row shape drifts."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Final

import pytest

from codegenie.audit.chain_head_io import read_chain_head, write_chain_head
from codegenie.types.identifiers import ChainHead

# AC-G-1: fixture input as a module-level Final constant — the cross-phase contract.
# Any Phase 4 PR that changes chain-row shape MUST update this list AND regenerate
# the golden fixture via CODEGENIE_REGEN_GOLDEN=1.
_FIXTURE_INPUT_EVENTS: Final[list[dict[str, object]]] = [
    {"type": "engine_used", "engine_id": "deterministic_recipe",
     "ts": "2026-05-23T00:00:00Z", "prev_hash": "0" * 32},
    {"type": "solved_example.duplicate_skipped", "advisory_id": "CVE-2024-00001",
     "ts": "2026-05-23T00:00:01Z"},
    {"type": "engine_used", "engine_id": "openrewrite",
     "ts": "2026-05-23T00:00:02Z"},
]


def _compute_phase4_chain_head_bytes() -> bytes:
    """Pure function: reduce _FIXTURE_INPUT_EVENTS through Phase 4 chain math → 16 bytes."""
    from blake3 import blake3
    import json
    prev = b"\x00" * 16
    for event in _FIXTURE_INPUT_EVENTS:
        payload = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
        prev = blake3(prev + payload).digest(length=16)
    return prev


def test_committed_fixture_matches_phase4_writer_output(
    golden_phase4_chain_head_path: Path,
) -> None:
    """AC-G-2: default-mode byte-equality assertion — the cross-phase compat gate."""
    expected = _compute_phase4_chain_head_bytes()
    actual = golden_phase4_chain_head_path.read_bytes()
    assert expected == actual, (
        "Phase 4 chain-head writer drift detected. If this is intentional, "
        "regenerate via CODEGENIE_REGEN_GOLDEN=1 pytest tests/schema/test_phase4_chain_compat.py"
    )


def test_phase4_writer_is_deterministic() -> None:
    """AC-G-4: two in-process invocations produce byte-identical output."""
    first = _compute_phase4_chain_head_bytes()
    second = _compute_phase4_chain_head_bytes()
    assert first == second


@pytest.mark.skipif(
    os.environ.get("CODEGENIE_REGEN_GOLDEN") != "1",
    reason="opt-in via CODEGENIE_REGEN_GOLDEN=1",
)
def test_regenerate_fixture(golden_phase4_chain_head_path: Path) -> None:
    """AC-G-3: opt-in regenerator. NEVER runs without the env-var."""
    fresh = _compute_phase4_chain_head_bytes()
    write_chain_head(golden_phase4_chain_head_path, ChainHead(fresh))
```

### Green — make it pass

Implement in order: §1 (`ChainHead`), §2 (`BLAKE3_128_BYTES`), §3 (`AuditChainCorrupted` widening), §4–5 (`audit/chain_head_io.py` — read first, then write, the read is needed for `RetryLedger.__init__`), §6 (`retry_ledger.py` extensions — `_check_phase4_chain_head` helper first, then `__init__` integration, then `record` / `record_pre_execute` writeback). Generate the golden fixture by running `CODEGENIE_REGEN_GOLDEN=1 pytest tests/schema/test_phase4_chain_compat.py::test_regenerate_fixture` once; commit the binary.

### Refactor — clean up

- Confirm `PHASE4_CHAIN_HEAD_FILENAME: Final[str] = "chain_head.bin"` lives in one place (`gates/contract.py` or `audit/chain_head_io.py` — co-locate with the rest of the protocol constants).
- Verify `_check_phase4_chain_head` docstring references ADR-0005 by number and cites production ADR-0014.
- Ensure `AuditChainCorrupted.__str__` truncates any hex prefix to ≤ 8 chars (already-structured attributes mitigate this, but logs are still a vector).
- Confirm the regenerator is gated on `CODEGENIE_REGEN_GOLDEN=1` consistently (no stray `--regen` `pytest_addoption`).
- Add module docstring to `audit/chain_head_io.py` documenting the cross-phase port discipline and the atomic-write contract.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Add `ChainHead = NewType("ChainHead", bytes)`. |
| `src/codegenie/gates/contract.py` | Add `BLAKE3_128_BYTES: Final[int] = 16` next to S1-04's `^[0-9a-f]{32}$` regex. |
| `src/codegenie/gates/errors.py` | Extend `AuditChainCorrupted.kind` Literal additively with 6 new values; add `.gate_id: str \| None` structured attribute. |
| `src/codegenie/audit/__init__.py` | New package init; re-export `read_chain_head`, `write_chain_head`. |
| `src/codegenie/audit/chain_head_io.py` | New module: pure `read_chain_head` (port; raises with the right `kind`) + pure `write_chain_head` (atomic write: tempfile + fsync + rename + dir-fsync). |
| `src/codegenie/gates/retry_ledger.py` | Add module-level pure `_check_phase4_chain_head`; extend `__init__` to call `_verify_phase4_chain_head` after manifest, before recovery; extend `record` and `record_pre_execute` to atomic-write `chain_head.bin` after JSONL fsync; add public `verify_chain_head()` method. |
| `tests/audit/test_chain_head_io.py` | AC-B-*, AC-C-* (read port + write port + atomic-write + round-trip + fsync call count). |
| `tests/audit/test_chain_head_io_purity.py` | AC-L-1 (purity AST-walk). |
| `tests/audit/test_exports.py` | AC-M-6 (import test for `read_chain_head`, `write_chain_head`, `ChainHead`, `BLAKE3_128_BYTES`). |
| `tests/gates/test_retry_ledger_chain_compat.py` | AC-D-* (happy/sad + genesis mutation witness + idempotency); 8 test functions. |
| `tests/gates/test_retry_ledger_chain_head_write.py` | AC-E-* (write-after-record, read-back, post-marker). |
| `tests/gates/test_retry_ledger_chain_head_properties.py` | AC-I-* (Hypothesis: mismatch, wrong-size, round-trip, purity). |
| `tests/adversarial/test_phase4_chain_head_compat.py` | AC-H-* (parametrized byte-flip + wrong-size + symlink + empty + unreadable). |
| `tests/schema/test_phase4_chain_compat.py` | AC-G-1..AC-G-4 (default-mode byte-equality + regenerator + determinism). |
| `tests/schema/test_no_silent_regen.py` | AC-G-5 (meta-test for mtime stability). |
| `tests/golden/phase4_chain_head.bin` | 16-byte committed binary fixture. |
| `tests/conftest.py` | `golden_phase4_chain_head_path` fixture resolving from `pytest`'s `rootdir`. |
| `tests/gates/test_retry_ledger_purity.py` | Extend allowlist for `codegenie.audit.chain_head_io`. |
| `tests/fence/test_no_substring_exc_in_chain_head_tests.py` | AC-J-3 (AST-walk forbidding `in str(exc` patterns in the new test files). |

## Out of scope

- Operator forensic chain-head reset (`codegenie sandbox reset-chain --i-know-what-im-doing`) — roadmap item.
- Operator-side `codegenie sandbox inspect <gate-run-id>` re-verification flow — S8-01. This story exposes the public `RetryLedger.verify_chain_head()` method S8-01 will consume.
- Phase 4-side refactor consolidating its existing chain-head writer into `codegenie.audit.chain_head_io.write_chain_head` — flagged as a follow-up Phase 4 PR. The cross-phase contract is the *bytes*, not the *code path*. This story's regenerator computes the bytes via the shim's writer, which (today) is a small Phase-4-equivalent implementation; once the Phase 4 PR lands, the shim becomes the single writer.
- Changes to Phase 4's actual event-emit path — the chain-row shape is the contract.
- `pre_execute` marker primitive itself — S2-02 lands that; this story consumes it.
- Phase 6 `SandboxResumeBehavior` policy — Phase 6 story.

## Notes for the implementer

### S2-01 / S2-02 hardening carryforward (READ FIRST)

- **16 bytes, not 32.** BLAKE3-128 per S1-04 HARDENED. The `blake3` library's default `.hexdigest()` is 64 chars / 256-bit; you MUST call `.hexdigest(length=16)` and `.digest(length=16)`. Every `chain_head` is 16 raw bytes / 32 hex chars. The old draft's "32 bytes" / "64 hex chars" / "BLAKE3 default" wording is wrong throughout — all references corrected in the hardened story above.
- **Structured exception attributes, no substring asserts.** S2-01 AC-AT-2 + S2-02 AC-AT-5 established the discipline; this story extends `.kind` Literal additively with 6 new values. Every test assert is `exc.value.kind == "..."`, not `"..." in str(exc.value)`. The fence test in `tests/fence/test_no_substring_exc_in_chain_head_tests.py` (AC-J-3) is the structural defense against the executor regressing this.
- **`Attempt` (from S1-04) is HARDENED frozen.** Do not edit it. The chain-head verify is orthogonal to row-shape — file-level, not row-level.
- **`_recover_chain_state` returns a 3-tuple** (next_attempt_id, last_chain_hash, marker_pending) after S2-02. The chain-head verify runs BEFORE recovery (AC-D-1 ordering).
- **`entries()` (not `attempts()`) is the right reader** for any chain-internal verification that spans both row types. This story's verify is over the `chain_head.bin` file (not JSONL rows), so the choice is orthogonal here — but S5-02's `GateRunner.run` and S8-01's `inspect` will consume `entries()` when reading the JSONL.

### ADR-0005 / ADR-0007 contract surface (verbatim)

- **ADR-0005 Decision:** `RetryLedger.__init__` accepts `prev_chain_head: bytes | None`, reads it from `.codegenie/remediation/<run-id>/chain_head.bin`, raises `AuditChainCorrupted` on mismatch. Startup test refuses to run any gate if compatibility fails.
- **ADR-0005 Consequences:** Phase 4 PR that changes event shape must include a Phase 5 fixture update — the diff signals the cross-phase change. (AC-G-2 is the CI gate that enforces this.)
- **ADR-0007 Decision:** `pre_execute` marker is a JSONL row participating in the chain. The marker's `chain_hash` is the chain head after `record_pre_execute` returns. This story writes that hash to `chain_head.bin` (AC-E-2).

### Why the cache discipline (JSONL is source of truth, `chain_head.bin` is the cache)

The `attempts.jsonl` file is fsynced before `chain_head.bin` is rewritten. On a crash between the two writes, the JSONL has the new row and the `chain_head.bin` lags by one row. The next `__init__` calls `_recover_chain_state` which reads the JSONL tail and recovers `last_chain_hash` — that value is then re-written to `chain_head.bin` via a `write_chain_head` call in `__init__` *if* the on-disk file doesn't already match. (Add this reconciliation step in the `_verify_phase4_chain_head` shell: after a successful read, if the bytes match `_last_chain_hash` from recovery, no-op; if they match the *prior* `_last_chain_hash` (one row back), the cache lags and gets refreshed; if they match neither, raise mismatch.)

If you find this too clever, the simpler path is: always re-write `chain_head.bin` at the end of `__init__` (after recovery) from `_last_chain_hash`. The atomic-write makes this safe. The performance cost is one extra `fsync` per `__init__` (~5 ms on tmpfs). I lean toward this simpler version.

### Atomic-write semantics

Mirror S2-01 AC-FS-1. The pattern is:

```python
def write_chain_head(path: Path, head: ChainHead) -> None:
    if len(head) != BLAKE3_128_BYTES:
        raise ValueError(f"chain head must be 16 bytes; got {len(head)}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(head)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        try:
            os.fsync(dir_fd)
        except OSError as e:
            if e.errno != errno.EINVAL:  # macOS-on-some-FS
                raise
    finally:
        os.close(dir_fd)
```

### Forward-compat for S2-04 / S8-01

- S8-01's `codegenie sandbox inspect <gate-run-id>` will call `RetryLedger(...).verify_chain_head()` as a public re-verify (AC-E-4 ships this surface).
- Phase 6's checkpointer reads `chain_head.bin` directly via `read_chain_head` (the port is the contract).

### Subtle correctness traps

- The fixture-input list (`_FIXTURE_INPUT_EVENTS`) is the CROSS-PHASE CONTRACT. Any Phase 4 PR that changes the chain-row shape must update this list AND regenerate the golden file. The CI gate (AC-G-2) catches the second half automatically.
- Symlink rejection (AC-D-9 / AC-H-3) is defensive against an adversarial repo layout — `.codegenie/remediation/<run-id>/chain_head.bin` symlinked to `/etc/passwd` would read a valid (random) 16 bytes if `/etc/passwd` happens to be 16 bytes (it isn't, but generalize: symlinks are forbidden).
- `chmod 0o000` test (AC-H-5) must restore permissions in a `try/finally` so `tmp_path` cleanup works.
- The `gate_id` attribute is populated by the `RetryLedger` shell (not by `read_chain_head` itself, which has no gate context). `read_chain_head` raises with `.gate_id is None`; the shell catches, sets `.gate_id`, and re-raises.
- Avoid hex-string comparisons in the read path — always compare 16-raw-byte `bytes`. A buggy impl that hex-roundtrips before compare is correct but slow; one that compares hex-of-bytes vs raw-bytes is broken. Hand-rolled byte-compare (`==`) on `bytes` is the canonical form.
