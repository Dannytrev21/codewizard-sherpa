# Validation report — S2-03 Phase 4 chain-head compatibility check + `chain_head.bin` read/write port + `AuditChainCorrupted` startup refusal

**Story:** [`../S2-03-phase4-chain-head-compat.md`](../S2-03-phase4-chain-head-compat.md)
**Validated:** 2026-05-23
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S2-03 closes ADR-0005's cross-phase chain-compatibility seam — `RetryLedger.__init__` reads `.codegenie/remediation/<run-id>/chain_head.bin` (Phase 4's tail), refuses startup on mismatch, and the BLAKE3-chained extension downstream stays tamper-evident. The story's goal traces cleanly to arch §Goals item 14, §Edge cases #11–12, and the canonical ADR. **But the draft was written before S2-01 and S2-02 hardening landed**, and it carries the byte-size carryforward S2-01 hardening explicitly filed for this validator pass — twenty-one findings total: 5 block-tier, 13 harden-tier, 3 nit-tier across four critic lenses.

The block-tier issues, each of which would have made the executor either fail at first construction, pass tests for the wrong reason, or leave a silent cross-phase chain-drift gap:

1. **(consistency + test-quality + coverage — block) BLAKE3-128 byte-size violation throughout the draft.** The draft uses 32 bytes / 64 hex chars everywhere — `len(expected_head) == 32`, `b"\x00" * 32`, `b"\x00" * 16  # half size`, AC-3 `"≠ 32 bytes"`, Notes line 161 `"32 bytes is the BLAKE3 default digest size — keep it that way"`. S1-04 HARDENED + S2-01 HARDENED pin BLAKE3-128 / 16 bytes (validator `^[0-9a-f]{32}$` over `Attempt.{prev,chain}_hash`); S2-01 AC-H-3 explicitly raises `ValueError("prev_chain_head must be 16 bytes; got {n}")` for any other length. The S2-01 hardening report (block #5, harden #21, Notes #18) *explicitly* filed this against S2-03: *"S2-03's '≠ 32 bytes' check is wrong and must be flagged for S2-03 validation."* The draft's happy-path test would fail at the `Attempt`-construction layer (the recovered chain root would be 64 hex chars, rejected by the field validator) — the test would never even reach the chain-head comparison. Resolution: every "32 bytes" → "16 bytes" in 12 locations; sentinel `b"\x00" * 16`; `BLAKE3_128_BYTES: Final[int] = 16` introduced as a named constant in `gates/contract.py` so the magic number lives once. AC-A-1..AC-A-3 + AST-walk forbidding bare `16` literals in size checks.

2. **(consistency + test-quality + design — block) `AuditChainCorrupted` constructed via string-only, asserted via substring — exactly the antipattern S2-01 / S2-02 hardening removed.** Draft writes `AuditChainCorrupted(f"phase4 chain-head mismatch: expected={...}, on_disk={...}")` and asserts `"mismatch" in str(exc.value).lower()`, `"missing" in str(exc.value).lower()`, `"size" in str(exc.value).lower()`. S2-01 AC-AT-2 ships `AuditChainCorrupted` with `.kind: Literal[...]`, `.row_index: int`, `.attempt_id: int | None`; S2-02 AC-AT-5 added `.row_type`. The substring assertion would either (a) fail because the executor moves to structured attributes and removes the substring, or (b) succeed for the wrong reason because the substring appears via the default `__str__`. Worse, the existing S2-01 `.kind` enum has no semantically-right value for "Phase 4 chain-head file failures" — neither `chain_mismatch` (replay-of-JSONL), nor `wrong_chain_root` (recovered-root-vs-kwarg), nor `manifest_mismatch` (manifest.yaml). The draft is silent on what to do. Resolution: AC-J-1 widens `.kind` Literal additively with 6 new values (`phase4_head_mismatch`, `phase4_head_missing`, `phase4_head_wrong_size`, `phase4_head_not_regular_file`, `phase4_head_unreadable`, `phase4_head_unexpected`). AC-J-2 adds `.gate_id: str | None` as an additive structured attribute (the draft's AC-8 `"error message includes the gate_id"` becomes a runtime-witnessable obligation, not a fragile substring grep). AC-J-3 is the structural defense: a fence test AST-walks the new test files and forbids `in str(exc` patterns. All 8 D-* / H-* tests rewritten to assert on `exc.value.kind` and `exc.value.gate_id`.

3. **(consistency — block) Goal contradicts arch §Integration with Phase 6 — the WRITE side of `chain_head.bin` is unaccounted for.** Arch line 948 lists `.codegenie/remediation/<run-id>/chain_head.bin` as a "new artifact *produced*" by Phase 5 for "Phase 7+ to read" (the "extended chain"). The draft only addresses Phase 5 READING what Phase 4 wrote; it never specifies when Phase 5 rewrites the file (after each `record`? after each `record_pre_execute`? never?). Without an answer, Phase 6 inherits a Phase-4-stale `chain_head.bin` that no longer reflects Phase 5's appended chain — silent staleness, the exact failure ADR-0005 ("silent chain drift is impossible") exists to prevent. The Out-of-scope section doesn't enumerate "write side deferred"; it's just missing. Resolution: AC-E-1..AC-E-5 land the write side — `RetryLedger.record` and `record_pre_execute` atomically update `chain_head.bin` via `write_chain_head` after the JSONL fsync. The discipline is "JSONL is source of truth, `chain_head.bin` is the cache" — on a crash between the two writes, recovery rebuilds from the JSONL tail. Atomic write semantics mirror S2-01 AC-FS-1 (tempfile → fsync → rename → dir-fsync). New public `RetryLedger.verify_chain_head()` is the S8-01 consumption point.

4. **(coverage + design — block) Cross-phase byte-stable fixture contingency lives only in Notes, not in ACs — executor cannot gate on it.** Draft Implementation outline §2 prescribes a shim "If a public [Phase 4 writer] function … exists, import it. If not (likely — this is cross-phase scaffolding), write a thin shim …" — but the shim location, exports, and "Phase 4 also imports from this shim" requirement are all in Notes. An executor following ACs-only would either (a) hand-synthesize the 32-byte fixture (the exact failure mode Notes warn against), or (b) skip the cross-phase wiring entirely. The story's whole reason to exist (the cross-phase compatibility test) becomes unenforced. Resolution: `src/codegenie/audit/chain_head_io.py` is introduced as a neutral hexagonal port — neither under `gates/` nor under `llm/`. AC-B-* pins the read port; AC-C-* pins the write port (atomic-write + fsync count). The fixture-input list `_FIXTURE_INPUT_EVENTS` is a module-level `Final[list[...]]` constant in the schema test (AC-G-1) so it's a versioned cross-phase contract, not hidden inside a test function. AC-G-2 is the cross-phase compat gate: a *default-mode* (no flag/env-var) byte-equality assertion between the in-process Phase 4-equivalent writer reduction and the committed golden fixture — Phase 4 drift FAILS CI before anyone runs the regenerator. AC-G-3 inverts the draft's "only regenerator gated" pattern: the assertion runs by default; the regenerator is opt-in via `CODEGENIE_REGEN_GOLDEN=1` (env-var consistent with S2-02 AC-GF-2, not a `pytest_addoption --regen` which silently propagates via `pytest.ini`). AC-G-5 is the meta-defense: a `tests/schema/test_no_silent_regen.py` records `os.stat(golden).st_mtime_ns` before and after running the schema test suite, asserts unchanged.

5. **(test-quality — block) Genesis-mode test is vacuous — asserts the sentinel but does NOT verify the file-read was SKIPPED.** Draft `test_genesis_mode_skips_check_when_prev_chain_head_is_none` only asserts `ledger.head() == b"\x00" * 32` (also wrong byte size). If the implementation silently calls `Path.read_bytes()` on a non-existent file and catches `FileNotFoundError`, the test passes — but the AC's intent ("genesis ledger; skip the check") is violated because the impl DID touch the disk. A regression where the impl always reads the file and only skips comparison-when-`expected-is-None` would pass this test. This is the kind of test Rule 9 ("Tests verify intent, not just behavior") explicitly targets. Resolution: AC-D-4 is the mutation witness — monkeypatch `codegenie.audit.chain_head_io.read_chain_head` with a `MagicMock`, plant a deliberately-poisoned `chain_head.bin` in `tmp_path` containing 16 garbage bytes, construct `RetryLedger(prev_chain_head=None)`, assert `mock.call_count == 0`. The test now distinguishes "skipped" from "happens to not raise."

The remaining 16 findings were harden- or nit-tier and would not block executor success but each tightens an AC, a test, or a forward-compat seam:

6. **(test-quality — harden) Property tests missing for the load-bearing invariants.** Three Hypothesis properties added: AC-I-1 (any 16-byte `b ≠ expected` raises `phase4_head_mismatch`), AC-I-2 (any length ≠ 16 raises `phase4_head_wrong_size`), AC-I-3 (`write_chain_head` + `read_chain_head` round-trip identity). AC-I-4 is the purity witness — given a fixed `chain_head.bin`, the raise/pass decision depends only on the `expected` kwarg (no hidden state across constructions). Catches "buggy impl that compares only the first 8 bytes" or "compares hex-of-bytes vs raw-bytes" — mutations the original single-tampered-byte test would never catch.

7. **(test-quality — harden) Adversarial test widening — parametrize byte-flip position, parametrize wrong-size cases.** Draft only flipped the LSB of EVERY byte (a "tampered file" but any prefix-compare bug would still catch it). AC-H-1 parametrizes across `[0, 7, 15]` (first, middle, last byte) and `[xor_0x01, xor_0xff]` mutations — 6 cases. AC-H-2 parametrizes wrong-size cases across `[0, 1, 8, 15, 17, 32, 64]` bytes — **explicitly including the old draft's mistake size (32 bytes)**: a regression toward "BLAKE3-256" would PASS the old AC and FAIL this one. AC-H-3 (symlink rejection — defensive against zip-slip-shaped attack surface, ADR-0008 precedent). AC-H-4 (empty file). AC-H-5 (chmod 0o000 → `kind="phase4_head_unreadable"` — handles the `OSError` path that would otherwise leak a raw `PermissionError`).

8. **(design — harden) Primitive obsession on chain-head `bytes` — rule-of-three cleared, `ChainHead` NewType missing.** Per CLAUDE.md "Newtype identifiers when crossing ≥ 2 module boundaries," `chain_head` bytes flow through ≥ 4 module boundaries: `RetryLedger.__init__`, `audit/chain_head_io.read_chain_head`, `audit/chain_head_io.write_chain_head`, and Phase 4's producer call-site. S2-02 hardening landed `SandboxSpecHash` per the same rule (3 modules cleared); this story clears 4. AC-A-2 lands `ChainHead = NewType("ChainHead", bytes)` in `types/identifiers.py` with AST-walk chokepoint (mirrors S2-02 AC-NT-4).

9. **(design — harden) Pure functional core / imperative shell — `_check_phase4_chain_head` helper extracted.** S2-01 AC-PH-1 / S2-02 AC-DR-4 established the discipline: chain math lives in pure module-level helpers, AST-walk asserted via `tests/gates/test_retry_ledger_purity.py`. Draft's `_verify_phase4_chain_head` mixes file I/O (read) with logic (4-way decision over two `bytes | None` inputs). The pure piece is trivially extractable. AC-D-2 / AC-D-3 promote the helper to module-level; the class method is the impure shell. Logic gets unit-tested without `tmp_path`; integration tests cover the shell.

10. **(consistency — harden) `_recover_chain_state` 3-tuple awareness.** S2-02 widened the return from 2-tuple to 3-tuple (adding `marker_pending`). Draft is silent on ordering. AC-D-1 pins the order explicitly: validate `prev_chain_head` length → manifest first-write/match-or-raise → **verify `chain_head.bin`** → `_recover_chain_state` (3-tuple) → verify recovered chain root against `prev_chain_head` (S2-01 AC-RR-2). The chain-head file check happens BEFORE in-memory recovery so a corrupted Phase 4 head fails-loud before any chain-internal work.

11. **(consistency — harden) `entries()` (S2-02) vs `attempts()` (S2-01) reader awareness.** S2-02 hardening's forward-flag explicitly tagged this for S2-03 validation. The chain-head file check (AC-D-*) operates on raw bytes — not on JSONL rows — so the choice is orthogonal here. AC-M-2 makes the S2-02 surface non-regression explicit: `test_retry_ledger_entries.py` and `test_pre_execute_marker.py` and `test_retry_ledger_resume.py` are part of this story's CI suite and must stay green.

12. **(coverage — harden) Coverage gate AC missing.** S2-01 AC-QG-5 (≥ 95/90% on `retry_ledger.py`) and S2-02 AC-QG-7 (same for `record_pre_execute`-touched paths) set the bar. AC-M-3 mirrors: ≥ 95% line / ≥ 90% branch on `audit/chain_head_io.py` AND on `retry_ledger.py::_check_phase4_chain_head`.

13. **(consistency — harden) `Depends on` too narrow.** Draft says `S2-01`. The story now consumes S2-02's 3-tuple `_recover_chain_state`, the extended `AuditChainCorrupted.row_type`, the `entries()` reader (for non-regression). Widened to `S1-02, S1-04, S2-01, S2-02`.

14. **(consistency — harden) `ADRs honored` widened.** Draft lists `ADR-0005, ADR-0007`. Added `ADR-0011` (no verdict cache; the chain head is the only "this attempt happened" durable witness) and `ADR-0014` (`extra=forbid` / fail-loud replay discipline — `AuditChainCorrupted` structured-attribute pattern inherits this). Matches S2-01 / S2-02 hardened ADR sets.

15. **(coverage + harden) Quality-gates AC widening.** Draft's `pytest` invocation lists three files. AC-M-5 widens to seven, including the new property and adversarial files; AC-M-6 adds an import test for the new public exports (`read_chain_head`, `write_chain_head`, `ChainHead`, `BLAKE3_128_BYTES`).

16. **(test-quality — harden) structlog event field list pinned.** Draft AC says "records a structlog event `gates.ledger.chain_head_verified` with `chain_head_hex[:8]`" — field list incomplete. AC-K-1 pins the exact field set: `{"event": "...", "gate_id": <str>, "chain_head_hex": <str of length 8>}`. AC-K-2 pins NO event in genesis mode (silence is the right signal there; emitting "verified" for the skip case would be misleading).

17. **(design — harden) Atomic-write contract (S2-01 fsync pattern reused).** AC-C-1 pins tempfile + fsync(tmp) + rename + fsync(dir). AC-C-3 is the partial-crash witness: monkeypatch `os.rename` to raise `KeyboardInterrupt`, assert the file still reads the prior contents. AC-C-5 is the structural witness: mock `os.fsync`, assert it's called exactly twice (file fd + dir fd) — same shape as S2-01 AC-FS-1.

18. **(design — harden) Module-purity tests.** S1-02..S2-02 each ship `tests/gates/test_<module>_purity.py` AST-walking imports against an allowlist. AC-L-1 adds `tests/audit/test_chain_head_io_purity.py`; AC-L-2 widens `test_retry_ledger_purity.py` allowlist for the new helper. Forbidden imports: `subprocess`, `requests`, `urllib`, `langchain`, anything LLM-shaped.

19. **(coverage — harden) Effort upgraded S → M.** The cross-phase shim + write-side + ChainHead NewType + property/metamorphic tests + atomic-write semantics + 6 new error kinds materially expanded the work. S2-01 underwent the same S → M upgrade under similar validation; S2-02 stayed S because it was purely 2 new helpers + 1 new method.

20. **(consistency — harden) Notes-line corrections.** Two internal contradictions: line 161 "32 bytes is the BLAKE3 default digest size — keep it that way" — the 256-bit default is wrong for Phase 5's use; the contract is BLAKE3-128. Line 136 "never log full 64 hex chars" — 32 hex chars under BLAKE3-128. Both fixed; the leak-safe truncation prefix (8 chars) is unchanged.

21. **(nit) Regenerator pattern aligned with S2-02 (env-var, not `pytest_addoption`).** AC-G-3 uses `CODEGENIE_REGEN_GOLDEN=1` consistent with S2-02 AC-GF-2, not `--regen`. Env-var is more explicit, harder to silently propagate via `pytest.ini`, and matches the repo's existing golden-fixture regeneration pattern across phases.

**No `RESCUE`-tier findings.** The story's goal, scope, and ADR alignment are correct; every issue is patchable in place. The byte-size violation was explicitly anticipated by S2-01 hardening — the validator did exactly what the carryforward asked.

**No Stage-3 research needed.** Every finding was answerable from S2-01 / S2-02 HARDENED reports, ADRs 0005 / 0007 / 0011 / 0014, the phase-arch-design.md `RetryLedger` and Integration-with-Phase-6 sections, and CLAUDE.md load-bearing commitments. The two soft "NEEDS RESEARCH" flags (symlink behavior, Phase 4 source location) were resolved by the validator's own judgment: symlinks are categorically rejected (`phase4_head_not_regular_file` per ADR-0008 codebase precedent); Phase 4 source location is deferred to a follow-up Phase 4 PR (the cross-phase contract is the bytes, not a shared code path).

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim, hardened):** Wire `RetryLedger.__init__` to read `.codegenie/remediation/<run-id>/chain_head.bin` through the cross-phase port `codegenie.audit.chain_head_io.read_chain_head`, verify it against `prev_chain_head: ChainHead | None` with structured-attribute `AuditChainCorrupted` raises on any failure, AND have every `record` / `record_pre_execute` atomically rewrite `chain_head.bin` to the new tail. Extends S2-01 + S2-02 *additively*: no edit to `Attempt`, no rewritten chain math, no change to existing public method signatures.
- **Non-goals (Out-of-scope, hardened):** Operator forensic chain-head reset (roadmap); `codegenie sandbox inspect <gate-run-id>` (S8-01); Phase 4-side consolidation refactor (follow-up Phase 4 PR — additive); changes to Phase 4 event-emit path; pre-execute marker primitive (S2-02); Phase 6 `SandboxResumeBehavior` policy.

### Phase 5 exit criteria touched

- **§Goals item 14 (audit chain extends Phase 4 head, startup test refuses on mismatch).** The story IS the closure of this goal.
- **§Component design — `RetryLedger` Internal structure (arch line 553+).** The widening from S2-01/S2-02 (`{record, head, attempts, record_pre_execute, entries}`) to add `verify_chain_head()` (new public method for S8-01) plus the `_verify_phase4_chain_head` shell + `_check_phase4_chain_head` pure helper internally.
- **§Edge cases #11–12 (audit chain tamper, Phase 4 chain-head mismatch).** Both are pinned to `AuditChainCorrupted` raises with structured `.kind`.
- **§Integration with Phase 6 line 948 (`chain_head.bin` is a Phase 5 artifact for Phase 7+ to read).** The previously-unaccounted-for write side is now AC-E-1..AC-E-5.
- **§Cross-phase boundary tests (tests/schema/test_phase4_chain_compat.py).** AC-G-2 is the default-mode byte-equality assert; AC-G-3 / AC-G-5 are the regenerator opt-in + silent-regen meta-defense.

### Load-bearing commitments touched

- **ADR-0005 (this story's canonical ADR):** signature `RetryLedger.__init__(..., prev_chain_head: ChainHead | None)`, file path `.codegenie/remediation/<run-id>/chain_head.bin`, raise `AuditChainCorrupted` on mismatch.
- **ADR-0007 (`pre_execute` marker):** marker rows participate in the chain — `record_pre_execute` updates `chain_head.bin` (AC-E-2).
- **ADR-0011 (no verdict cache; sandbox_spec_hash is the seam):** chain head is the only durable witness that "this exact attempt happened"; no verdict cache means no shortcut around chain extension.
- **ADR-0014 (`ObjectiveSignals` extra=forbid + replay strictness):** `AuditChainCorrupted` carries the same structured-attribute pattern (`.kind`, `.row_index`, `.row_type`, `.gate_id`); fail-loud applies to chain-head file failures.
- **CLAUDE.md "Extension by addition":** the new `.kind` values are additive Literal extension; `.gate_id` is an additive attribute (defaults None); `verify_chain_head()` is a new public method, not an edit; no existing signature changes.
- **CLAUDE.md "Newtype identifiers when crossing ≥ 2 module boundaries":** `ChainHead = NewType("ChainHead", bytes)` lands per rule-of-three (4 modules — `RetryLedger`, `chain_head_io.read`, `chain_head_io.write`, Phase 4 producer).
- **CLAUDE.md "Functional core / imperative shell":** `_check_phase4_chain_head` is a pure module-level helper; the `__init__` shell wraps file I/O around it. AST-walk asserts at module top level (AC-D-3).
- **CLAUDE.md "Fail loud":** every chain-head failure raises with a structured `.kind`; the structlog event `gates.ledger.chain_head_verified` is a positive observability signal; silent skip is gated on `prev_chain_head is None` (an explicit, type-checker-visible opt-in).
- **CLAUDE.md "Data-driven registries over branching code":** `_check_phase4_chain_head`'s 5-way decision is small (None/None, None/expected, on_disk/None, equal, unequal) and asymmetric — `match` is right; registry promotion deferred per Rule 2.

### Sibling-family lineage (Design-Patterns)

- **This story is the 3rd consumer of `gates/retry_ledger.py`.** S2-01 (first; chain primitive + resume-on-reopen) and S2-02 (second; pre-execute marker + `entries()` + `_marker_pending`) lay the kernel. S2-03 extends additively — no method signature changes; only purely additive `.kind` Literal values, a new `.gate_id` attribute, and a new public `verify_chain_head()` method.
- **Codebase precedent for NewType + AST chokepoint:** S1-03 (`SignalKind`), S1-04 (`AttemptNumber`, `RunId`), S2-02 (`SandboxSpecHash`). The S1-03 AC-4c pattern (AST-walk forbidding `NewType("Name", ...)` redefinition) is mirrored by AC-A-2 for `ChainHead`.
- **Codebase precedent for atomic-write + fsync(file) + fsync(dir):** S2-01 AC-FS-1 (the `attempts.jsonl` append discipline). AC-C-1 reuses the pattern for `chain_head.bin` writes; AC-C-5 mirrors the mocked-fsync call-count structural test.
- **Codebase precedent for `extra=forbid`-style strictness on JSONL row:** S2-01 AC-EF-1. The same strictness applies to the new error `.kind` Literal — any unknown kind in tests fails.

### Prior validation history

- None for S2-03 — this is the first pass.
- S2-01 HARDENED report extensively shapes this story (carryforward block #5, harden #21, Notes #18: BLAKE3-128 byte size + structured `AuditChainCorrupted`; carryforward harden #14: pure module-level helpers; AC-FS-1: atomic-write fsync discipline).
- S2-02 HARDENED report shapes this story (carryforward forward-flag #1: `entries()` not `attempts()`; AC-AT-5: `.row_type`; AC-NT-3: `SandboxSpecHash` NewType precedent for `ChainHead`; AC-GF-2: `CODEGENIE_REGEN_GOLDEN=1` env-var regenerator pattern).

## Critic findings (Stage 2 — verbatim)

### Coverage critic findings (6 block, 11 harden, 5 nit)

| Severity | Finding | Resolution |
|---|---|---|
| **block** | BLAKE3-128 byte-size contradiction throughout (12 sites: AC-3/4/5, TDD literals, Notes line 161). | AC-A-1..AC-A-3 + globally rewritten 32→16. |
| **block** | Goal vs. AC drift — behavior unspecified for `prev_chain_head is None` AND file exists. | AC-F-2 pins behavior (skip read; first record overwrites). |
| **block** | `AuditChainCorrupted` raised as string-only — substring assertions contradict S2-01/S2-02 hardening. | AC-J-1 widens `.kind` Literal additively; AC-J-2 adds `.gate_id`; AC-J-3 fence test. |
| **block** | Cross-phase fixture contingency lives only in Notes — executor can hand-synthesize bytes. | AC-B-* / AC-C-* / AC-G-1..AC-G-5 promote the shim + default-mode equality assertion to ACs. |
| **block** | Missing AC for "16-byte file exists but bytes don't equal `prev_chain_head`" — conflated kind. | Separate `.kind` values per failure mode. |
| **block** | Story misses S2-01 hardening's already-implemented recovered-root check; ordering unclear. | AC-D-1 pins ordering: chain-head verify BEFORE recovery + S2-01 AC-RR-2 check. |
| **harden** | Missing edge case AC: `run_dir` doesn't exist. | AC-D-7 + behavior pinned. |
| **harden** | Missing edge case: chain_head.bin is a symlink / directory. | AC-D-9 + AC-H-3. |
| **harden** | Missing edge case: truncated/partial write race. | AC-C-3 atomic-write property test. |
| **harden** | `codegenie sandbox inspect` AC unverifiable + unpinned in TDD. | AC-E-4: public `verify_chain_head()` method for S8-01. |
| **harden** | Failure message must include `gate_id` (structured attribute). | AC-J-2 promotes `gate_id` to structured attribute. |
| **harden** | Coverage-gate AC missing. | AC-M-3 (≥ 95/90%). |
| **harden** | S2-02 surface non-regression (`entries()`) unpinned. | AC-M-2 (S2-02 tests in CI). |
| **harden** | Fixture regenerable AND byte-identical between two runs. | AC-G-4 determinism witness. |
| **harden** | `--regen` flag default unpinned. | AC-G-3 (env-var, not flag) + AC-G-5 meta-defense. |
| **harden** | Genesis mode allows silent skip in production code. | AC-F-1 / AC-F-2 + AC-D-4 mutation witness. |
| **harden** | Idempotent `__init__` unpinned. | AC-D-11. |
| **nit** | Hex truncation message-safety in Refactor — promote to AC. | AC-K-1 leak-safe field list. |
| **nit** | structlog field list incomplete. | AC-K-1 explicit field list. |
| **nit** | `tests/conftest.py` `pytest_addoption` AC missing — replaced by env-var pattern. | AC-G-3 env-var, no conftest hook. |
| **nit** | `PHASE4_CHAIN_HEAD_FILENAME` constant in Refactor — promote to AC. | Surfaced in Refactor §clean-up; co-located with port constants. |
| **nit** | `Depends on` too narrow. | Widened to S1-02, S1-04, S2-01, S2-02. |
| **nit** | `ADRs honored` missing 0011 and 0014. | Widened to 0005, 0007, 0011, 0014. |

### Test-Quality critic findings (4 block, 13 harden, 4 nit)

| Severity | Finding | Resolution |
|---|---|---|
| **block** | All test-code uses 32 bytes / 64 hex (would fail at `Attempt` field validator). | Globally rewritten. |
| **block** | Three substring `"…" in str(exc.value)` assertions — exact pattern S2-01/S2-02 removed. | AC-J-1..AC-J-3 + AST fence test. |
| **block** | Genesis-mode test is vacuous (asserts `head()`, doesn't verify read was SKIPPED). | AC-D-4 mutation witness — monkeypatch `read_chain_head`, assert call count = 0. |
| **block** | "Golden fixture must be 32 bytes" assertion is intent-void; no test asserts bytes came from Phase 4's writer. | AC-G-2 default-mode byte-equality between in-process Phase-4-equivalent reduction and committed fixture. |
| **harden** | Byte-flip test only flips ALL bytes (LSB of every byte). | AC-H-1 parametrize across `[0, 7, 15]` byte positions × `[xor_0x01, xor_0xff]`. |
| **harden** | Missing Hypothesis property: any 16-byte `b ≠ expected` raises. | AC-I-1. |
| **harden** | Missing Hypothesis property: any size ≠ 16 raises. | AC-I-2 + parametrized cases `[0, 1, 8, 15, 17, 32, 64]`. |
| **harden** | Missing metamorphic: `write_chain_head` + `read_chain_head` round-trip identity. | AC-C-4 / AC-I-3. |
| **harden** | Missing metamorphic: `test_regenerate_fixture` twice produces identical bytes. | AC-G-4. |
| **harden** | Missing purity property: `_check_phase4_chain_head` is pure of process state across constructions. | AC-I-4 — three sequential constructions (A, B, A) test. |
| **harden** | Test names too generic (`test_happy_path_with_golden_fixture`). | Renamed. |
| **harden** | structlog event not verified at runtime in happy-path test. | AC-D-5 uses `structlog.testing.capture_logs()`. |
| **harden** | "Error message includes gate_id" not asserted as structured attribute. | AC-J-2 `.gate_id` + tests assert. |
| **harden** | Fixture-file location stability not pinned. | AC-G-6 + `tests/conftest.py` fixture resolving from `pytest`'s `rootdir`. |
| **harden** | No test that default `pytest` run leaves the fixture mtime unchanged. | AC-G-5 (meta-test). |
| **harden** | Symlink behavior undefined. | AC-D-9 + AC-H-3 — reject as `phase4_head_not_regular_file`. |
| **harden** | Unreadable file leaks raw `PermissionError`. | AC-D-10 + AC-H-5 — wrap as `phase4_head_unreadable`. |
| **nit** | `bytes(b ^ 0x01 for b in expected)` visually confusing. | Renamed variable for clarity. |
| **nit** | After 32→16 fix, "half size" cases stale. | AC-H-2 parametrized `[0, 1, 8, 15, 17, 32, 64]` covers all reasonable sizes. |
| **nit** | Adversarial test name overlaps in-`tests/gates/` test. | Consolidated under `tests/adversarial/test_phase4_chain_head_compat.py` parametrized. |
| **nit** | Refactor item "structured messages" — 32 hex chars under BLAKE3-128 (not 64). | Notes-line correction. |

### Consistency critic findings (3 block, 11 harden, 3 nit)

| Severity | Finding | Resolution |
|---|---|---|
| **block** | Headline BLAKE3-128 contradiction (S2-01 hardening explicitly filed this). | AC-A-1..AC-A-3 + global rewrite. |
| **block** | `AuditChainCorrupted` string-only construction contradicts S2-01 AC-AT-2 + S2-02 AC-AT-5. | AC-J-1..AC-J-3. |
| **block** | Write side of `chain_head.bin` unaccounted for (arch line 948). | AC-E-1..AC-E-5 + atomic-write integration into `record`/`record_pre_execute`. |
| **harden** | Genesis-mode test asserts wrong-size sentinel. | Test rewritten with `b"\x00" * 16`. |
| **harden** | `_recover_chain_state` 3-tuple ordering unmentioned. | AC-D-1 + Implementation outline §6. |
| **harden** | `head()` re-verify uses `attempts()` implicitly; must work for marker-tail per S2-02. | Surfaced in Notes; AC-E-5 covers `head()` post-record equality. |
| **harden** | `Depends on` too narrow. | Widened. |
| **harden** | `ADRs honored` missing 0011 + 0014. | Widened. |
| **harden** | Notes line 161 / line 136 internal contradiction with BLAKE3-128. | Both corrected. |
| **harden** | Module-purity test missing for new module. | AC-L-1 + AC-L-2. |
| **harden** | Functional-core/imperative-shell discipline not pinned. | AC-D-2 + AC-D-3 pure helper. |
| **harden** | Effort S → M (work materially expanded). | Updated. |
| **harden** | Out-of-scope incomplete (write side, Phase 4-side refactor). | Out-of-scope widened. |
| **harden** | `--regen` structural defense missing. | AC-G-3 + AC-G-5. |
| **nit** | Adversarial-file split (mismatch.py / missing.py) vs consolidated parametrized. | Consolidated under one file. |
| **nit** | Phase 4 source path guessed in Notes. | Notes acknowledges; the bytes are the contract, not the code path. |
| **nit** | structlog event field list not S2-02-aligned. | AC-K-1 explicit field list. |

### Design-Patterns critic findings (0 block, 7 harden, 3 nit)

| Severity | Finding | Resolution |
|---|---|---|
| **harden** | Primitive obsession on `chain_head` bytes — `ChainHead` NewType missing (rule-of-three cleared). | AC-A-2. |
| **harden** | Pure-impure tangle — `_check_phase4_chain_head` helper not extracted. | AC-D-2 + AC-D-3. |
| **harden** | `AuditChainCorrupted.kind` Literal not pinned for new failure-shapes. | AC-J-1 (6 new Literal values). |
| **harden** | Shim placement `llm/audit/` puts shared port under one consumer. | Moved to neutral `codegenie/audit/`. |
| **harden** | Atomic-write semantics unspecified. | AC-C-1..AC-C-5. |
| **harden** | Fixture-input hidden state inside test function. | AC-G-1 `_FIXTURE_INPUT_EVENTS: Final[list[...]]` module-level constant. |
| **harden** | Magic-number `16` duplicated. | AC-A-1 `BLAKE3_128_BYTES: Final[int] = 16`. |
| **nit** | `prev_chain_head: bytes \| None` two-valued — sum-type opportunity deferred. | Per Rule 2; surfaced in Notes for future rule-of-three. |
| **nit** | `kind` Literal additive pattern as the canonical extension surface. | Documentation-rent; module docstring guidance. |
| **nit** | `--regen` env-var vs option flag — pick repo-consistent pattern. | AC-G-3 `CODEGENIE_REGEN_GOLDEN=1` per S2-02 AC-GF-2. |

## Edits applied (Stage 4)

Story rewritten end-to-end. Major sections:

- **Header lines updated:** `Status: Ready` → `HARDENED`; `Effort: S` → `M`; `Depends on: S2-01` → `S1-02, S1-04, S2-01, S2-02`; `ADRs honored: ADR-0005, ADR-0007` → `ADR-0005, ADR-0007, ADR-0011, ADR-0014`; `Validated: 2026-05-23` line added.
- **`Validation notes` block added** under the header — 21 numbered carryforwards mirroring the S2-02 report structure (each item referenceable from future stories).
- **References section expanded** — adds ADR-0011, ADR-0014, production ADR-0016, the two prior validation reports, and explicit "READ FIRST" pointers.
- **Goal section rewritten** — pins BLAKE3-128, `ChainHead` NewType, atomic-write discipline, hexagonal port placement, additive-only extension surface.
- **Acceptance criteria restructured** into 13 lettered sections (A–M) with 36 individually-verifiable ACs (up from 9 unstructured bullets). Every AC has (a) an explicit ID, (b) third-party-verifiability, (c) trace to a critic finding or S2-01/S2-02 carryforward.
- **Implementation outline rewritten** — 18 ordered steps; the chain-head write side, pure helper extraction, and hexagonal port placement are explicit.
- **TDD plan rewritten** — three red files in the body (chain-compat: 8 tests; properties: 3 Hypothesis tests; schema: 3 default-mode + opt-in tests). Adversarial and additional files called out separately.
- **Files-to-touch expanded** — 19 files (up from 8); each maps to specific ACs.
- **Out-of-scope widened** to explicitly defer operator forensic reset, S8-01 CLI, Phase 4-side refactor.
- **Notes for the implementer** rewritten with 5 sections: (a) S2-01/S2-02 hardening carryforward (READ FIRST), (b) ADR-0005/ADR-0007 contract surface verbatim, (c) cache discipline (JSONL = source of truth, chain_head.bin = cache), (d) atomic-write semantics with full code snippet, (e) forward-compat for S8-01 + Phase 6, (f) subtle correctness traps (symlink, chmod cleanup, gate_id population layer, byte-vs-hex compare).

## Verdict

**HARDENED.** Story now closes ADR-0005's cross-phase chain-compatibility seam end-to-end (read + write + atomic + property-tested + cross-phase fixture stability) with full structured-attribute discipline. The byte-size carryforward S2-01 hardening filed for this validator pass is closed. Every AC is individually verifiable; every critical edge case (mismatch, missing, wrong-size, symlink, unreadable, partial-write crash, genesis-mode silent-skip, idempotent re-construction, marker-tail chain head, Phase 4 byte-drift) has at least one test that would fail if a wrong implementation were swapped in. The cross-phase contract (the bytes, not the code path) is enforced by a *default-mode* CI gate — Phase 4 drift fails the assertion before anyone touches the regenerator.

### Forward flags for downstream stories

- **S5-02 (`GateRunner.run`):** No new contract — `chain_head.bin` write happens transparently inside `ledger.record(...)` / `ledger.record_pre_execute(...)`. GateRunner sees no API change.
- **S8-01 (`codegenie sandbox inspect`):** Will re-verify the chain head on every invocation by constructing a `RetryLedger` and calling its new public `verify_chain_head()` (AC-E-4). The `ChainHead` NewType is the importable type S8-01 will consume.
- **Phase 4 follow-up PR:** Consolidate Phase 4's existing in-line chain-head writer into `codegenie.audit.chain_head_io.write_chain_head`. Additive only — Phase 4 keeps its code path until the consolidation PR. This story's regenerator computes the cross-phase bytes via the shim's writer (which is small enough to be Phase-4-equivalent today). Tracked in Out-of-scope; not in this story's scope.
- **Phase 6 (LangGraph checkpointer):** Reads `chain_head.bin` via `read_chain_head` to recover chain state on resume. The 16-byte BLAKE3-128 shape is pinned with the `ChainHead` NewType — any future change requires amending ADR-0005 + S1-04 + this story.
- **Future "3rd row type" story (TBD, likely S6+ or S7+):** `AuditChainCorrupted.kind` Literal is now at 13+ values across S2-01/S2-02/S2-03. The rule-of-three for promoting `.kind` from a Literal union to a registry-backed enum is cleared; deferred today per Rule 2 (the Literal works fine and Pydantic v2's discriminator support is mature). Surfaced in Notes for future trigger.
