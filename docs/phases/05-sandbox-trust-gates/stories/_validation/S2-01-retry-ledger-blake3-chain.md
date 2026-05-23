# Validation report — S2-01 `RetryLedger` BLAKE3-chained JSONL + `Attempt` model

**Story:** [`../S2-01-retry-ledger-blake3-chain.md`](../S2-01-retry-ledger-blake3-chain.md)
**Validated:** 2026-05-23
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S2-01 ships the load-bearing `RetryLedger` — one of Phase 5's three central abstractions per `phase-arch-design.md §Component design`, and the durable checkpoint Phase 6's LangGraph checkpointer will lift unchanged. The draft was directionally correct (right file layout, right BLAKE3 chain idea, right out-of-scope split with S2-02 / S2-03), but it carried **23 findings across all four critic lenses, six of them block-tier** that would have either failed at first import, broken the chain on the second instantiation, or forced S2-02 to edit S1-04's frozen contract in violation of CLAUDE.md "Extension by addition." The most consequential were:

1. **(consistency — block) Hash size contradicts S1-04 HARDENED contract.** Draft uses **32 bytes / 64 hex chars** ("BLAKE3-256 default") throughout — sentinel `"00" * 32` (64 chars), `len(payload["chain_hash"]) == 64`, `prev_chain_head: bytes | None` implicitly 32 bytes, Notes "BLAKE3 default digest is 32 bytes; do not use the `digest_size` parameter". **S1-04 HARDENED ships the `Attempt` model with `prev_hash: str` and `chain_hash: str` validated by `^[0-9a-f]{32}$` — 32 lowercase hex chars = 16 bytes = BLAKE3-128** (per S1-04 AC-J-1 and validation finding #9: "ADR-0005 requires lowercase canonical hex"). The draft's TDD `_make_attempt(prev_hash="00" * 32)` produces a 64-char string and would be **rejected by S1-04's `field_validator` with `ValidationError` on first construction.** The draft's chain math (`blake3(...).hexdigest()` returns 64 chars by default) produces values that cannot be assigned to `Attempt.chain_hash`. Resolution: every "32 bytes / 64 hex" in the story is rewritten to "16 bytes / 32 hex / BLAKE3-128"; implementation must call `.hexdigest(length=16)` (or `.digest(length=16).hex()`); `prev_chain_head` is `bytes | None` of length 16; sentinel is `b"\x00" * 16`. AC-H-1 / AC-H-2 / AC-IMP-1.

2. **(design — block) S2-02 would edit S1-04's frozen `Attempt` contract — violates "Extension by addition".** S2-02's Implementation outline step 2 reads: *"Update `Attempt` (in `gates/contract.py`) to add `type: Literal["attempt"] = "attempt"` as the first field"*. That's an edit to a HARDENED frozen Pydantic model whose shape S1-04 explicitly pins (AC-J + module-purity test). The cleaner forward-compat path lives in S2-01: **write the `"type": "attempt"` discriminator on the JSONL line at serialization time, not on the Attempt model**. The on-disk row shape is `{"type": "attempt", ...attempt fields...}`; replay reads each line, asserts `type == "attempt"`, drops the field, validates as `Attempt`. S2-02 then adds `{"type": "pre_execute", ...}` rows purely additively, no edit to `Attempt` and no regenerated S2-01 golden file. Resolution: AC-T-1..AC-T-3 land the `type` discriminator at the JSONL layer, with `attempts()` filtering by type and `extra=forbid`-style rejection of unknown types. This also lets S2-02's `LedgerEntry` discriminated union land as a pure addition without rewriting history.

3. **(coverage — block) Resume-on-reopen semantics unspecified — the Phase 6 contract this story exists to serve.** Per arch §Concurrency-and-checkpoints (line 236), `attempts.jsonl` "is what Phase 6's checkpointer will lift unchanged." Per ADR-0005, Phase 5 is the chain-extension durability seam. Per ADR-0007, an orphan `pre_execute` row is *expected* on resume. **But the draft's `__init__` only handles first-use: it "writes `manifest.yaml` if absent, stores `prev_chain_head`."** What happens when `RetryLedger(run_dir=tmp, gate_id="g", prev_chain_head=...)` is constructed a *second* time over the same `gate_dir` (e.g., Phase 6 resume from checkpoint, or the in-process retry envelope re-entering the gate)? The draft would default `_next_attempt_id = 1` and `_last_chain_hash = None` — silently restarting the chain over an existing file. The next `record(Attempt(attempt_id=2))` would raise `LedgerAttemptOutOfOrder` (good — fail loud) but a `record(Attempt(attempt_id=1))` would *succeed* and produce a duplicate row (silent corruption). Resolution: AC-RR-1..AC-RR-4 pin re-instantiation semantics — `__init__` reads existing `attempts.jsonl` if present, recovers `_next_attempt_id = max(attempt_id over attempt-rows) + 1`, recovers `_last_chain_hash` from the last row's `chain_hash`, verifies the recovered chain head against `prev_chain_head` (when both present and non-None), and raises `AuditChainCorrupted` on mismatch. The recovery is the load-bearing Phase 6 invariant.

4. **(design — block) Canonical-JSON payload boundary for `chain_hash` computation is undefined.** `chain_hash = blake3(prev_hash + canonical_json(attempt)).hexdigest(length=16)` — but `chain_hash` is itself a field of `Attempt`. If `canonical_json` includes `chain_hash`, you have a chicken-and-egg (the value depends on the value); if it excludes it, that must be specified in the contract because replay must compute the same canonical bytes. Draft step 3 of Implementation outline says `_canonical_json(attempt) -> bytes` using `attempt.model_dump(mode="json")` — which DOES include `chain_hash`. Draft step 5's "rewrites the attempt with the real `chain_hash`" implies the *first* canonicalization uses a placeholder, then a *second* canonicalization with the real hash is written to disk — but then replay's `_compute_chain_hash` over the on-disk bytes computes a *different* hash (because the on-disk payload already contains the real `chain_hash`). The chain is then unverifiable. Resolution: `_canonical_json` MUST exclude `chain_hash` from the dumped payload (`model_dump(mode="json", exclude={"chain_hash"})`); the on-disk JSONL line then has the shape `{**canonical_payload_without_chain_hash, "chain_hash": <computed>}` written in one pass. Replay recomputes `_compute_chain_hash(prev_hash, canonical_json_without_chain_hash)` and compares to the on-disk `chain_hash`. AC-CJ-1..AC-CJ-3 pin this contract.

5. **(consistency — block) `prev_chain_head` byte-length contradiction across sibling stories.** S2-01 draft: 32 bytes. **S2-03 AC-3 (draft, Ready): "wrong size (≠ 32 bytes): raise `AuditChainCorrupted`"**. S1-04 HARDENED: `prev_hash`/`chain_hash` are BLAKE3-128 (16 bytes). With S1-04 winning per Consistency priority, `prev_chain_head` must be **16 bytes** — and S2-03's "≠ 32 bytes" check is wrong and must be flagged for S2-03 validation (filed as a Notes-for-implementer carryforward, since this validator scopes to S2-01 only). The chain-head file `.codegenie/remediation/<run-id>/chain_head.bin` is 16 bytes, not 32. Resolution: AC-H-3 pins `prev_chain_head` byte-length = 16; AC-H-4 pins the `chain_head.bin` sentinel size in the docstring as 16 bytes. The S2-03 mismatch is logged in Notes-for-implementer as a "validator follow-up: S2-03 AC-3 needs amending from 32 to 16 bytes" — this story's executor must not pick up the wrong S2-03 number.

6. **(test-quality — block) Property test is tautological — would pass any deterministic implementation.** Draft AC-6: *"for any N ≤ 5 valid attempts recorded in order under the same `prev_chain_head`, `head()` after the Nth record is deterministic regardless of write timing"*. "Regardless of write timing" is a no-op for a synchronous append-and-fsync loop with no concurrency. The property as written asserts only that `f(x) == f(x)` — every deterministic implementation passes. **Real properties worth pinning:** (a) **prefix-replay invariance** — for any prefix of length M ≤ N, replaying `attempts.jsonl` truncated to that prefix recomputes the same `chain_hash` for record M (catches off-by-one prev_hash threading); (b) **payload-permutation-witness** — recording the same N attempts in a *different attempt_id order* would produce a *different* head (catches a buggy implementation that hashes only the latest payload without prev_hash); (c) **canonical-bytes determinism** — `_canonical_json(attempt)` is byte-identical across two independent calls with the same model fields (catches accidental dict-ordering drift). Resolution: AC-PROP-1 / AC-PROP-2 / AC-PROP-3 replace the tautological AC-6.

The remaining 17 findings were harden- or nit-tier and would not block executor success but each tightens an AC, a test, or a forward-compat seam:

7. **(coverage — harden) Adversarial tamper test owned by AC but missing from Files-to-touch.** AC requires `tests/adversarial/test_audit_chain_tamper.py` but the Files-to-touch table doesn't list it. An executor following the table literally would either skip the file (failing the AC) or invent its location. Added to Files-to-touch with explicit purpose.

8. **(coverage — harden) Tamper test parametrization too narrow.** Draft TDD `test_attempts_replay_verifies_chain_and_detects_tamper` tampers only `sandbox_run_id`. A regression where the walker only validates that field (the `replace("run-0001", ...)` byte-position) passes vacuously. Tightened to a parametrized test across multiple fields: `sandbox_run_id`, `outcome.summary`, `attempt_id`, `prev_hash` — each tampering produces `AuditChainCorrupted` and the exception names the offending `attempt_id`. AC-AT-1 + paired parametrized test.

9. **(coverage — harden) `AuditChainCorrupted` exposes only `str(exc)` substring.** Draft asserts `"attempt_id=1" in str(exc.value)` — fragile (any message-text edit breaks the test), and callers cannot act programmatically without parsing strings. Promote to structured attribute: `AuditChainCorrupted` carries `.attempt_id: int | None` and `.row_index: int` attributes; `str(exc)` is the human-readable summary. AC-AT-2 + S1-01 errors-extension precedent.

10. **(coverage — harden) `manifest.yaml` byte-shape unconstrained.** Draft AC says only "`gate_id`, `created_at` (UTC ISO 8601), `prev_chain_head` (hex)" — no field order, no extra-fields rejection, no idempotency (what if `__init__` is called twice and `manifest.yaml` already exists with different `prev_chain_head`?). Added AC-MF-1..AC-MF-4: alphabetized keys via `yaml.safe_dump(..., sort_keys=True)`; manifest is written exactly once (`open(..., "x")` mode on first construction; idempotent no-op if file exists AND its `prev_chain_head` matches; raise `AuditChainCorrupted` if file exists with mismatched `prev_chain_head`). Mirrors S1-06 schema-stub discipline.

11. **(coverage — harden) `gates/__init__.py` re-export has no AC.** Story Files-to-touch lists it but no AC verifies `from codegenie.gates import RetryLedger, AuditChainCorrupted, LedgerAttemptOutOfOrder` succeeds. Added AC-EX-1 + a one-line import test.

12. **(test-quality — harden) fsync verification conflates structural and timing concerns.** Draft AC bundles "p95 latency ≤ 50 ms on tmpfs" with "verified via `unittest.mock.patch("os.fsync")` call-count test". The mock test verifies *structure* (fsync called on file fd + dir fd); the p95 verifies *timing*. They're different tests with different stability properties. Split: AC-FS-1 (structural — `os.fsync` called twice per `record`, once on file fd, once on dir fd; verified by `unittest.mock.patch("os.fsync")`); AC-FS-2 (timing — p95 ≤ 50 ms over 100 records on tmpfs, marked `pytest.mark.bench` per project markers convention — `bench` is excluded by default per `pyproject.toml`).

13. **(test-quality — harden) `LedgerAttemptOutOfOrder` semantics too strict for resume.** Draft AC says "raises `LedgerAttemptOutOfOrder` if `attempt_id` is not strictly increasing from 1". After resume-on-reopen (block #3), the *next expected* attempt_id may be 2 or 3, not 1. Rephrased AC-OO-1: `record(attempt)` accepts if and only if `attempt.attempt_id == self._next_attempt_id`; raises `LedgerAttemptOutOfOrder` otherwise. The "strictly increasing from 1" property is now a *consequence* of `__init__` initializing `_next_attempt_id = 1` for a brand-new ledger and recovering from the file otherwise.

14. **(design — harden) Pure helpers `_canonical_json` / `_compute_chain_hash` promised in Refactor are AC-worthy.** Draft says "Pull `_canonical_json` and `_compute_chain_hash` into module-level functions so S2-02's `record_pre_execute` reuses them." Refactors are nice-to-have; ACs are testable. Promote to AC-PH-1: both helpers are module-level pure functions (no `self`, no I/O, no logging); a `tests/gates/test_retry_ledger_purity.py` AST-walks `retry_ledger.py` and asserts the two function names are at module top level. This is the seam S2-02 will reuse — pinning it here means S2-02 lands additively. Functional-core/imperative-shell discipline per CLAUDE.md.

15. **(consistency — harden) `Depends on` missing S1-03.** Draft lists `S1-01, S1-04`. But `Attempt.signals: ObjectiveSignals` comes from S1-03 (`sandbox/signals/models.py`); the TDD fixture constructs `ObjectiveSignals()`. Without S1-03 GREEN, the test cannot import. Widen to `S1-01, S1-03, S1-04`.

16. **(consistency — harden) `ADRs honored` missing ADR-0007.** Even though S2-01 defers `record_pre_execute` to S2-02, the story is the chain-substrate that S2-02 extends. The pure-helper extraction (AC-PH-1), the `type` discriminator at the JSONL layer (block #2), and the chain-recovery semantics (block #3) are all S2-01 work in service of ADR-0007. List it.

17. **(test-quality — harden) `_make_attempt` factory uses raw `int` / `str` instead of `AttemptNumber` / `RunId` constructors.** S1-04 HARDENED Notes (#1245 of the validation report): *"NewType is a type-checker shim. `RunId('r1')` returns the bare string at runtime; the NewType wrapper is for `mypy --strict` only. Tests use the constructor form as intent documentation."* Draft uses `attempt_id=attempt_id` (raw int) and `sandbox_run_id=f"run-{attempt_id:04d}"` (raw str). Runtime-equivalent, but loses the intent-documentation discipline S1-04 established. AC-NT-1: TDD plan uses `AttemptNumber(attempt_id)` and `RunId(...)` constructors.

18. **(coverage — harden) Coverage AC wording inconsistency with S1-04 HARDENED.** Draft: "Branch coverage ≥ 90%; line coverage ≥ 95%." S1-04 HARDENED uses the README convention: "95% line / 90% branch." Numbers identical, ordering differs. Pin canonical form for grep-able consistency across `stories/_validation/`.

19. **(test-quality — harden) `extra="forbid"`-style strictness on JSONL row.** S1-04 HARDENED uses `extra=forbid` to reject unknown fields on `Attempt`. Replay should mirror: an unknown JSON field on an `"attempt"` row raises `AuditChainCorrupted` (not a permissive `ignore`). This is the mutation-resistance witness for "tomorrow's `Attempt` adds a field; today's replay must not silently coerce." AC-EF-1 + parametrized test (extra field in JSONL → `AuditChainCorrupted`).

20. **(design — harden) `record(attempt)` ignores caller-supplied `chain_hash` and `prev_hash`.** Today the caller is expected to pass `_make_attempt(prev_hash=ledger.head().hex())` — which is a footgun (caller may pass stale `head()` if there's a race or just forget). The cleaner contract: `record(attempt)` IGNORES whatever `prev_hash`/`chain_hash` the caller supplied and substitutes its own (`prev_hash=self.head().hex()`, `chain_hash=<computed>`). The caller-supplied values are placeholder-only. AC-IG-1 makes this explicit; AC-IG-2 adds a test asserting that two records with intentionally-wrong `prev_hash` from the caller still produce a correctly-chained on-disk pair.

21. **(consistency — harden) Out-of-scope clarity on S2-03's chain-head `.bin` file size mismatch.** S2-03 draft AC-3 says "wrong size (≠ 32 bytes)". Per the BLAKE3-128 decision in block #1, this is 16 bytes. The validator's scope is S2-01; the mismatch is filed in Notes-for-implementer for the S2-03 executor (and a follow-up validator pass on S2-03).

22. **(design — harden) Module purity test missing.** S1-02..S1-07 each ship `tests/gates/test_<module>_purity.py` AST-walking imports against an allowlist. `retry_ledger.py` should follow: allowed imports = `__future__`, `json`, `os`, `errno`, `datetime`, `pathlib`, `typing`, `blake3`, `pydantic`, `yaml`, `structlog`, `codegenie.{errors, types.identifiers, gates.errors, gates.contract, sandbox.signals.models}`. Forbids `subprocess`, `requests`, `urllib`, `langchain`, etc. AC-MP-1 + `tests/gates/test_retry_ledger_purity.py`.

23. **(coverage — nit) `__repr__` AC.** Refactor says "Add `__repr__` exposing only `gate_id` and `_next_attempt_id`." Promote to AC-NT-2 with a one-line assertion (mainly a debugging-hygiene anchor; `__repr__` leaks via logs and structlog).

**No `RESCUE`-tier findings.** The goal traces cleanly to phase exit criteria; every gap was patchable by tightening ACs, switching from BLAKE3-256 to BLAKE3-128, moving the `type` discriminator to the JSONL serialization layer, and adding resume-on-reopen semantics.

**No Stage-3 research needed.** Every gap was answerable from S1-04's HARDENED report (the contract source of truth), ADR-0005 / ADR-0007 / ADR-0011, the phase-arch-design.md `RetryLedger` section, the codebase precedents in `src/codegenie/hashing.py` (BLAKE3 wire format) and `src/codegenie/audit.py` (chained audit anchors, `blake3:` prefix convention), and S2-02 / S2-03 drafts (forward-compat constraints).

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim, hardened):** Implement `RetryLedger` with `record`, `head`, and `attempts` replay verification over a **BLAKE3-128**-chained `attempts.jsonl` file (every line tagged `"type": "attempt"` at serialization), with sibling `manifest.yaml`, fsynced per-record writes (file fd + parent dir fd), pure module-level chain-math helpers reusable by S2-02, and resume-on-reopen recovery of `_next_attempt_id` + `_last_chain_hash` from existing files.
- **Non-goals (Out-of-scope, hardened):** `record_pre_execute(...)` — S2-02 (lands additively because `type` discriminator already exists on disk after S2-01); Phase 4 chain-head startup check — S2-03 (story accepts `prev_chain_head: bytes | None` but does not read `chain_head.bin`); `codegenie sandbox inspect` CLI — S8-01; concurrent-writer locking via `fcntl.flock` — S7-04 (single-writer by `GateRunner` design); `LedgerEntry` discriminated-union read API — S2-02 (this story ships only the `"type": "attempt"` write side and `attempts()` filter; `entries()` is S2-02 surface).

### Phase 5 exit criteria touched

- **Step 2 done-criteria (High-level-impl.md §Step 2):** "`tests/gates/test_retry_ledger.py` ≥ 95% line / 90% branch"; "Property test (hypothesis): … out-of-order `attempt_id` is rejected"; "`tests/adversarial/test_audit_chain_tamper.py` — manually editing `attempts.jsonl` causes `attempts()` to raise `AuditChainCorrupted`"; "Each `record` fsyncs (timing test asserts ≤ 50 ms p95 on a tmpfs, real fsync on physical disk)."
- **§Goal 14 (arch line 29):** "Audit chain extends Phase 4 chain head." S2-01 substrate; S2-03 binds.
- **§Concurrency-and-checkpoints (arch line 236):** "every attempt appends one BLAKE3-chained JSONL line to `.codegenie/remediation/<run-id>/gates/<gate_id>/attempts.jsonl` — that file plus the sandbox-run sub-directories are what Phase 6's checkpointer will lift unchanged." S2-01 is the durable-checkpoint primitive.
- **§Component design — `RetryLedger` (arch line 553):** public surface, file layout, internal structure. The `chain_hash: str` field has comment "blake3-128 hex" — S1-04 HARDENED confirms 32 lowercase hex chars.
- **§Edge case 11 (arch — manual `attempts.jsonl` edit):** triggers `AuditChainCorrupted` on replay — adversarial-tampers AC is the structural defense.

### Load-bearing commitments touched

- **ADR-0005 (Phase 4 chain-head compatibility):** S2-01 ships the chain primitive; `__init__` accepts `prev_chain_head: bytes | None`; S2-03 validates against `chain_head.bin`. BLAKE3 per-line is the wire format.
- **ADR-0007 (pre-execute marker for resume safety):** S2-01 must leave a clean additive seam for S2-02 — the `type` discriminator on every JSONL line, and pure module-level chain-math helpers `record_pre_execute` can reuse. The story title says S2-01 defers the marker, but the seam (discriminator + helpers + recovery) is S2-01 work.
- **ADR-0011 (no verdict cache):** `record` must not double-write on identical `(attempt_id, spec_hash)`; raise `LedgerAttemptOutOfOrder` instead. Per ADR consequences: "the `attempts.jsonl` file is append-only with BLAKE3 per-line chain — second `record(Attempt(attempt_id=1, ...))` raises `LedgerAttemptOutOfOrder`."
- **ADR-0014 (`ObjectiveSignals` extra=forbid):** replay must mirror — unknown JSON field on an `"attempt"` row raises `AuditChainCorrupted`, not silent acceptance. This is mutation-resistance against tomorrow's field-add silently passing today's replay.
- **production ADR-0014 (three-retry default):** `AttemptNumber` upper bound is 1024 (per `types/identifiers.py`), but practical max is 3; the ledger does not enforce 3 — that's `RetryPolicy` (S1-04).
- **CLAUDE.md "Extension by addition":** S2-02 must land additively over S2-01. The `type` discriminator at the JSONL-serialization layer (not on the frozen `Attempt` model) is the seam. S2-02's draft "edit `Attempt` to add `type` field" must be reversed; this story does the discriminator at write time.
- **CLAUDE.md "Newtype identifiers":** S1-04 ships `AttemptNumber` and `RunId` newtypes; tests use constructor form per S1-04 Notes; this story's TDD inherits the discipline.
- **CLAUDE.md "Functional core / imperative shell":** pure module-level `_canonical_json`, `_compute_chain_hash`, `_recover_chain_state` (chain-recovery helper) — class methods orchestrate I/O around them.
- **CLAUDE.md "Fail loud":** chain mismatch, byte-length mismatch, manifest mismatch, out-of-order `attempt_id`, duplicate manifest with different `prev_chain_head` all raise; no silent recovery.

### Sibling-family lineage (Design-Patterns)

- **This story is the 1st concrete consumer of `gates/retry_ledger.py`.** S2-02 (`record_pre_execute`) and S2-03 (`chain_head.bin` check) are siblings that extend the same module. The pure-helper + JSONL-`type`-discriminator design is the rule-of-three pre-emption: it's cheaper to land the kernel here than to refactor in S2-02.
- **Codebase precedent for BLAKE3 hashing:** `src/codegenie/hashing.py` uses `blake3.blake3(b).hexdigest()` returning 64 hex chars (full 256-bit). S1-04 chose 128-bit truncation for `Attempt.{prev,chain}_hash` (smaller JSONL lines); the divergence is documented in S1-04 hardening #9. `retry_ledger.py` must explicitly truncate via `hexdigest(length=16)`.
- **Codebase precedent for audit-chain row shape:** `src/codegenie/audit.py` (`ProbeExecutionRecord`) chains audit anchors with `blake3:` prefix and `additionalProperties: false` schema. `RetryLedger` mirrors the "extra=forbid replay" discipline (block #19) but stays prefix-free in the chain_hash field (S1-04 HARDENED choice — hex only).
- **Codebase precedent for module-purity tests:** every gate/sandbox module from S1-02..S1-07 ships `tests/<package>/test_<module>_purity.py` with an import allowlist (S1-02 AC-9 / 9a / 9b convention). `retry_ledger.py` inherits.

### Prior validation history (if any)

- None for S2-01. This is the first validation pass.

### Open ambiguities (resolved before Stage 2)

- **BLAKE3-256 (draft) vs BLAKE3-128 (S1-04 HARDENED).** Resolution: BLAKE3-128 wins (Consistency priority; S1-04 is the contract holder). Story updated; S2-03 flagged for follow-up.
- **`type` discriminator on `Attempt` model (S2-02 draft) vs at JSONL-serialization layer (this validation).** Resolution: serialization-layer wins (Extension by addition; S1-04 frozen contract preserved). S2-02 must be re-shaped accordingly — flagged in this story's Notes-for-implementer + a follow-up validator pass on S2-02.
- **First-use semantics (draft) vs resume-on-reopen semantics (Phase 6 contract).** Resolution: resume-on-reopen wins (load-bearing for Phase 6 checkpointer per arch §Concurrency-and-checkpoints).

## Critic findings (Stage 2)

### Critic A — Coverage

| Finding | Severity | Resolution |
|---|---|---|
| A-1 | block | Hash size 32 bytes (draft) contradicts S1-04 HARDENED 16 bytes | AC-H-1..AC-H-4 rewrite to BLAKE3-128 |
| A-2 | block | Resume-on-reopen semantics absent | AC-RR-1..AC-RR-4 pin recovery |
| A-3 | block | `prev_chain_head` byte length undefined / wrong | AC-H-3 pins 16 bytes |
| A-4 | harden | Adversarial tamper test owned by AC, missing from Files-to-touch | Add `tests/adversarial/test_audit_chain_tamper.py` |
| A-5 | harden | Tamper test parametrization narrow (only `sandbox_run_id`) | AC-AT-1 parametrize across multiple fields |
| A-6 | harden | `manifest.yaml` byte-shape unconstrained | AC-MF-1..AC-MF-4 |
| A-7 | harden | `gates/__init__.py` re-export AC missing | AC-EX-1 + import test |
| A-8 | harden | Coverage AC wording inconsistent with S1-04 form | Pin "95% line / 90% branch" canonical form |
| A-9 | harden | `Depends on` missing S1-03 | Widen to S1-01, S1-03, S1-04 |
| A-10 | harden | ADR-0007 missing from honored list | Add ADR-0007 |
| A-11 | nit | `__repr__` AC | AC-NT-2 |

### Critic B — Test Quality

| Finding | Severity | Resolution |
|---|---|---|
| B-1 | block | Property test (`AC-6`) is tautological — `f(x) == f(x)` | AC-PROP-1..AC-PROP-3 replace with mutation-witness properties |
| B-2 | harden | `_make_attempt` factory uses raw `int` / `str` | AC-NT-1 use `AttemptNumber` / `RunId` constructors |
| B-3 | harden | `AuditChainCorrupted` substring-only assertion | AC-AT-2 promote to structured attributes |
| B-4 | harden | fsync AC bundles structural + timing | AC-FS-1 (structural) / AC-FS-2 (perf, `bench`-marked) |
| B-5 | harden | `LedgerAttemptOutOfOrder` ("strictly increasing from 1") incompatible with resume-on-reopen | AC-OO-1 rephrase to "equals `_next_attempt_id`" |
| B-6 | harden | Tamper test only mutates one field | AC-AT-1 parametrize |
| B-7 | harden | Replay does not assert `extra=forbid`-style strictness | AC-EF-1 — unknown field → `AuditChainCorrupted` |

### Critic C — Consistency

| Finding | Severity | Resolution |
|---|---|---|
| C-1 | block | S1-04 HARDENED `Attempt.{prev,chain}_hash` validators reject 64-char hex | AC-H-1 conform to 32-char hex |
| C-2 | block | S2-02 draft edits S1-04's frozen `Attempt` model | AC-T-1..AC-T-3 move `type` discriminator to JSONL layer; flag S2-02 for follow-up validation |
| C-3 | block | S2-03 draft "≠ 32 bytes" check contradicts BLAKE3-128 16-byte chain head | Notes-for-implementer flag (S2-03 follow-up) |
| C-4 | harden | `Depends on` missing S1-03 (`ObjectiveSignals` import) | Widen |
| C-5 | harden | `ADRs honored` missing ADR-0007 | Add |
| C-6 | harden | Coverage AC form inconsistent with sibling reports | Pin "95% line / 90% branch" |

### Critic D — Design Patterns

| Finding | Severity | Resolution |
|---|---|---|
| D-1 | block | Canonical-JSON exclusion of `chain_hash` undefined → chicken-and-egg | AC-CJ-1..AC-CJ-3 — `_canonical_json` excludes `chain_hash` |
| D-2 | harden | Pure helpers in Refactor only; would be class methods on first pass | AC-PH-1 promote to module-level pure functions |
| D-3 | harden | `record(attempt)` trusts caller-supplied `prev_hash`/`chain_hash` | AC-IG-1 / AC-IG-2 — ledger overwrites |
| D-4 | harden | Module-purity test missing (S1-02..S1-07 precedent) | AC-MP-1 + `test_retry_ledger_purity.py` |
| D-5 | harden | `LedgerEntry` discriminated-union pattern deferred to S2-02 | Deliberately deferred — S2-01 ships write-side `type` only; S2-02 lands the read-side union purely additively. Documented in Notes-for-implementer. |

## Stage 3 — Research

**Not invoked.** No critic finding tagged `NEEDS RESEARCH`. Every gap was answerable from in-repo sources (S1-04 HARDENED, arch design, ADRs 0005/0007/0011/0014, codebase precedents in `hashing.py` + `audit.py`, and the S2-02 / S2-03 drafts).

## Stage 4 — Edits applied to story

| Section | Change |
|---|---|
| Header | `Depends on: S1-01, S1-03, S1-04`; `ADRs honored: ADR-0005, ADR-0007, ADR-0011`; add `**Validation:** HARDENED 2026-05-23 — see `_validation/S2-01-…md`` |
| Validation notes | New block (after Context) summarizing the 23 changes and why |
| Goal | Refined — explicit BLAKE3-128, `"type": "attempt"` at JSONL layer, resume-on-reopen |
| Acceptance criteria | Rewritten — 11 draft ACs grouped into AC-H (hash), AC-T (type discriminator), AC-CJ (canonical JSON), AC-RR (resume-on-reopen), AC-OO (out-of-order), AC-AT (audit tamper), AC-FS (fsync), AC-MF (manifest), AC-PH (pure helpers), AC-PROP (properties), AC-EF (extra forbid), AC-IG (ignore caller hashes), AC-EX (export), AC-MP (module purity), AC-NT (newtype + repr), AC-QG (quality gates) |
| Implementation outline | Updated: `hexdigest(length=16)`, `_canonical_json` excludes `chain_hash`, `_recover_chain_state` helper, JSONL line shape `{"type": "attempt", **canonical_attempt_minus_chain_hash, "chain_hash": <computed>}` |
| TDD plan | Test code block updated: BLAKE3-128 throughout (`"00" * 16`, `len(...) == 32`), `AttemptNumber` / `RunId` constructors, parametrized tamper, resume-on-reopen test, structural-fsync mock, perf-fsync `bench`, extra-field rejection |
| Files to touch | Added `tests/adversarial/test_audit_chain_tamper.py`, `tests/gates/test_retry_ledger_purity.py`, `tests/gates/test_retry_ledger_resume.py` |
| Out of scope | Tightened to call out S2-02's additive seam, S2-03's chain-head-bin read, `LedgerEntry` discriminated union |
| Notes for implementer | Added: BLAKE3-128 truncation pattern (`hexdigest(length=16)`); `type` discriminator at serialization layer not on `Attempt`; resume-on-reopen recovery; `_canonical_json` excludes `chain_hash`; flag for S2-02 (do not edit `Attempt`) and S2-03 (≠ 32 bytes → ≠ 16 bytes) follow-up validation |

## Final verdict

**HARDENED.** Six block-tier gaps closed (hash size, type-discriminator layer, resume-on-reopen, canonical-JSON boundary, `prev_chain_head` byte-length, property-test tautology); 17 harden/nit gaps tightened. Story is ready for the executor, *if* the executor also receives the S2-02 / S2-03 follow-up flags in the Notes-for-implementer block (so the executor does NOT edit `Attempt` for the `type` field and does NOT match S2-03's 32-byte chain-head sentinel until S2-03 is re-validated).
