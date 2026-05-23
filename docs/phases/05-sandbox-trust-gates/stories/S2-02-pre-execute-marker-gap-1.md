# Story S2-02 — Pre-execute marker `record_pre_execute` + JSONL ordering (Gap 1)

**Step:** Step 2 — Implement `RetryLedger` and audit-chain extension
**Status:** HARDENED
**Validation:** 2026-05-23 — see [`_validation/S2-02-pre-execute-marker-gap-1.md`](_validation/S2-02-pre-execute-marker-gap-1.md)
**Effort:** S
**Depends on:** S2-01
**ADRs honored:** ADR-0007, ADR-0005, ADR-0011, ADR-0014

## Context

`SandboxClient.execute` is **not** idempotent (image pulls, live grype, new `sandbox_run_id` on every call). If Phase 6's worker dies between `execute` returning and `RetryLedger.record` writing the attempt, a resume has no record an execute happened — and would re-run, paying full sandbox + LLM-token cost. ADR-0007 closes Gap 1 by introducing a two-phase write: a `"pre_execute"` JSONL marker chained into the BLAKE3 chain *before* `client.execute`, followed by the normal `"attempt"` line after. Phase 5 ships the marker; Phase 6 ships the resume policy (`SandboxResumeBehavior`). This story implements the marker surface, the ordering invariant, and the recovery semantics that make a process-restart between marker and attempt safe; the `GateRunner` call-site that uses it lands in S5-02.

## Validation notes — what changed during hardening (2026-05-23)

1. **Implementation step "edit `Attempt` to add `type: Literal['attempt']`" REMOVED.** S2-01 HARDENED carryforward flag #18 explicitly forbids this — the `"type"` discriminator already lives at the JSONL serialization layer (S2-01 AC-T-1..AC-T-3). The draft would have edited S1-04's frozen Pydantic contract in violation of CLAUDE.md "Extension by addition." Resolution: `PreExecuteMarker` carries its own `type: Literal["pre_execute"]` field; `Attempt` is untouched; the discriminator for `"attempt"` rows continues to be injected at write-time by S2-01's `_canonical_json` helper.
2. **Hash sizes aligned with S1-04 HARDENED contract.** Every `"ab" * 32` / `"cd" * 32` (64-char / 256-bit) in the TDD plan rewritten to `"ab" * 16` / `"cd" * 16` (32-char / BLAKE3-128). S1-04 validates `prev_hash`/`chain_hash` against `^[0-9a-f]{32}$`; the draft would have produced strings rejected at marker construction. `sandbox_spec_hash` is also 32 hex chars (BLAKE3-128 per arch line 654 — `SandboxSpec.sandbox_spec_hash` is "blake3-128 over canonical-JSON").
3. **`record_pre_execute` signature aligned with ADR-0007.** Draft: `record_pre_execute(attempt_id, sandbox_spec_hash) -> None` and `now_utc()` inside. ADR-0007 Decision: `record_pre_execute(attempt_id, sandbox_spec_hash, started_at) -> None`. ADR wins per Consistency priority. Caller injects `started_at`; ledger does no time-fetch (functional core / imperative shell — pure helpers stay pure; golden-file determinism is trivial because the caller controls the clock).
4. **`LedgerEntry` discriminated-union pattern reshaped.** Draft used `Annotated[PreExecuteMarker | Attempt, Field(discriminator="type")]` — but `Attempt` has no `type` field (S2-01 hardening kept it at the JSONL layer). The Pydantic v2 discriminator requires the field on every union member, so the draft would have raised `PydanticSchemaGenerationError`. Resolution: `entries()` reads each row, dispatches on the JSONL `"type"` value via a pure module-level `_parse_ledger_row(payload: dict) -> LedgerEntry` helper. `LedgerEntry: TypeAlias = PreExecuteMarker | Attempt` is a plain union; dispatch is one `match` statement.
5. **`PreExecuteMarker` model moved to `gates/contract.py`.** Draft put it in `retry_ledger.py`. `Attempt` lives in `contract.py`; the marker is a sibling domain model that S8-01's `codegenie sandbox inspect` and any future external reader will import. Co-locating with `Attempt` mirrors S1-04's module discipline.
6. **`SandboxSpecHash` NewType promoted to `types/identifiers.py`.** Primitive obsession on `sandbox_spec_hash: str` — the value crosses ≥ 3 module boundaries (`SandboxSpec`, `SandboxRun`, `PreExecuteMarker`) so it clears CLAUDE.md's rule-of-three threshold. Constructor form in tests per S1-04 Notes ("intent documentation"). The `SandboxSpec`/`SandboxRun` annotations in `sandbox/contract.py` widen in this story as a one-line edit (S1-02's `RunId` precedent — same widening shape).
7. **`_marker_pending` recovery promoted from Note to AC-RR-5.** Draft Note said "on process restart, replay the file once in `__init__`" but no AC pinned it. Without recovery, a crash between marker and attempt would let a second `record_pre_execute(1, ...)` succeed on restart — silent corruption Phase 6 cannot detect. New AC-RR-5 pins: `__init__` scans the file's tail; if the last row is a `"pre_execute"` with no matching `"attempt"` at the same `attempt_id`, set `_marker_pending = True` and `_next_attempt_id = marker.attempt_id` (NOT `+ 1` — that's the attempt's job). Otherwise `_marker_pending = False` and `_next_attempt_id` follows S2-01 AC-RR-1 semantics.
8. **Parametrized tamper test for marker fields.** Draft had a single substring-asserting tamper test. Replaced with the S2-01 AC-AT-1 pattern: parametrize across `{sandbox_spec_hash, started_at, attempt_id, prev_hash, type}`, each tamper raises `AuditChainCorrupted` with structured `.kind` / `.row_index` / `.row_type` attributes.
9. **Structured exception attributes — substring assertions removed.** Draft: `assert 'entry_type="pre_execute"' in str(exc.value)`. Replaced with `assert exc.row_type == "pre_execute"` and `assert exc.kind == "chain_mismatch"`. Mirrors S2-01 AC-AT-2 (`.attempt_id`, `.row_index`, `.kind`). New attribute `.row_type: Literal["attempt", "pre_execute"] | None` added to `AuditChainCorrupted` (extends S2-01 — purely additive).
10. **`LedgerAttemptOutOfOrder` widened with `.context: Literal["record", "record_pre_execute"]`.** Without it, callers can't distinguish "double marker" from "out-of-order attempt." Pure addition; S2-01's `.expected`/`.got` semantics unchanged.
11. **`record_pre_execute` validation-before-write pinned.** Mirrors S2-01 AC-OO-1: validate `attempt_id == self._next_attempt_id` AND `_marker_pending is False` AND `sandbox_spec_hash` matches `^[0-9a-f]{32}$` BEFORE any disk write. New AC-OO-3.
12. **`record_pre_execute` ignores caller-supplied chain fields.** Marker `prev_hash` is `self.head().hex()`; `chain_hash` is `_compute_chain_hash(prev_hex, _canonical_json_marker(marker))`. Caller never controls chain fields — S2-01 AC-IG-1 precedent. New AC-IG-3.
13. **Module-purity + import allowlist for added code.** S2-02 extends `retry_ledger.py` and `contract.py`; both already have purity tests from S2-01 / S1-04. Re-running them against the new code IS the test (no new file). Pin as AC-MP-1 so the executor's coverage gate catches drift.
14. **Coverage gate AC-QG-7 added** — ≥ 95% line / ≥ 90% branch on `src/codegenie/gates/retry_ledger.py` (canonical form, mirrors S2-01 AC-QG-5).
15. **Property tests added (mutation-witness, not tautology).** AC-PROP-M-1 (prefix-replay invariance over mixed rows), AC-PROP-M-2 (marker tamper invalidates the *following* attempt's chain — chain-participation witness), AC-PROP-M-3 (canonical-bytes determinism for `PreExecuteMarker`).
16. **structlog event promoted to AC-LG-1.** Draft put `gates.ledger.pre_execute_recorded` in Refactor; promoted to AC with leak-safe field list (`gate_id`, `attempt_id`, `sandbox_spec_hash[:8]`).
17. **Golden file uses injected clock, not freezegun.** Draft suggested "use `freezegun` or a fixed `datetime` injection." `freezegun` is a new dependency for one test. Cleaner: caller supplies `started_at`, golden file constructs `PreExecuteMarker(started_at=datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC))` directly. No new dependencies; matches change #3 above.
18. **Registry seam for future row types noted (not promoted).** Today: 2 row types (`attempt`, `pre_execute`). Rule of three not yet cleared. `_parse_ledger_row` uses a plain `match` statement; a `_ROW_TYPE_REGISTRY: Final[dict[str, type[BaseModel]]]` lift is deferred to the *third* row type's story (most likely S6+ sandbox-health snapshot or S7+ cost-ledger row). Surfaced in Notes-for-implementer as a tracked seam.
19. **`Depends on` widened to include S1-02 (sandbox contract).** The marker's `sandbox_spec_hash` field implicitly couples to `SandboxSpec.sandbox_spec_hash` byte-stability; without S1-02's contract shipped the type alias has no home.
20. **Carryforward flag for S2-03.** S2-03's TDD will need to read both `"attempt"` and `"pre_execute"` rows for chain-head startup verification. Surfaced in Notes so the S2-03 validator pass knows.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 1` (line 1003) — full gap statement and the `record_pre_execute` improvement spec.
  - `../phase-arch-design.md §Component design — RetryLedger` (line 553) — `Internal structure` and surface; the public interface widens additively.
  - `../phase-arch-design.md §Process view — Retry-recovers sequence` — order of operations between `RetryLedger`, `GateRunner`, and `SandboxClient`.
  - `../phase-arch-design.md §Open questions §8` (line 1063) — re-execute is the Phase 5 default; `SandboxResumeBehavior` is Phase 6's call.
  - `../phase-arch-design.md §Code contracts` (line 654) — `SandboxSpec.sandbox_spec_hash: str` is "blake3-128 over canonical-JSON" (the format constraint the marker validates).
- **Phase ADRs:**
  - `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — the canonical contract; pay attention to the 3-arg signature `(attempt_id, sandbox_spec_hash, started_at)`, the row-type discrimination, and the BLAKE3-chained requirement.
  - `../ADRs/0005-phase4-chain-head-compatibility.md` — the marker shape becomes part of the chain; chain-compat regen applies if the row shape changes.
  - `../ADRs/0011-no-verdict-cache-in-phase-5.md` — `sandbox_spec_hash` is the forward-compat seam Phase 9 will lift; pin its byte-stability discipline here.
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — replay-strictness precedent (unknown field on a marker row → `AuditChainCorrupted`).
- **Production ADRs:**
  - `../../../production/adrs/0016-checkpointer-backend.md` — the Phase 6 surface this contract serves.
- **Source design:**
  - `../final-design.md §New ADRs implied — ADR-P5-007`.
- **Existing code (from S2-01 HARDENED):**
  - `src/codegenie/gates/retry_ledger.py` — extend with `record_pre_execute`, `entries`, and the recovery branch in `__init__`. Reuse `_canonical_json`, `_compute_chain_hash`, `_recover_chain_state` (all module-level pure helpers per S2-01 AC-PH-1).
  - `src/codegenie/gates/contract.py` — add `PreExecuteMarker` alongside `Attempt`. Do NOT add a `type` field to `Attempt` — S2-01 hardening flag #18.
  - `src/codegenie/gates/errors.py` — extend `AuditChainCorrupted` with `.row_type` and `LedgerAttemptOutOfOrder` with `.context`. Both additive.
  - `src/codegenie/types/identifiers.py` — add `SandboxSpecHash = NewType("SandboxSpecHash", str)`; widen `sandbox/contract.py` annotations in a one-line additive edit.
- **Prior-story validation (read first):**
  - `_validation/S2-01-retry-ledger-blake3-chain.md` — block findings #1, #2, #5 and harden findings #14, #19, #22 directly shape S2-02 and are referenced in this story's ACs.

## Goal

Extend `RetryLedger` with `record_pre_execute(attempt_id: AttemptNumber, sandbox_spec_hash: SandboxSpecHash, started_at: datetime) -> None` that writes one BLAKE3-128-chained `{"type": "pre_execute", ...}` JSONL line immediately before the matching `"attempt"` line, with: golden-file ordering test, parametrized marker-tamper test, property tests for chain participation, `_marker_pending` recovery semantics on `__init__`, an `entries() -> list[LedgerEntry]` reader that dispatches on `"type"` via a pure module-level helper, and full structured-attribute exceptions (no substring assertions). The story extends S2-01 *additively*: no edit to `Attempt`, no regenerated S2-01 golden file, no rewritten chain math.

## Acceptance criteria

### A. `PreExecuteMarker` model

- [ ] **AC-PM-1 — `PreExecuteMarker` lives in `src/codegenie/gates/contract.py`** alongside `Attempt`, configured `model_config = ConfigDict(extra="forbid", frozen=True)`. Field order: `type: Literal["pre_execute"] = "pre_execute"`, `attempt_id: AttemptNumber`, `sandbox_spec_hash: SandboxSpecHash`, `started_at: datetime`, `prev_hash: str`, `chain_hash: str`. Field validators: `prev_hash` and `chain_hash` match `^[0-9a-f]{32}$` (BLAKE3-128); `sandbox_spec_hash` matches `^[0-9a-f]{32}$` (also BLAKE3-128 per arch line 654 / ADR-0011); `started_at.tzinfo is not None` (UTC-aware required).
- [ ] **AC-PM-2 — `PreExecuteMarker` is NOT exported under a `LedgerEntry` `Field(discriminator=...)` Pydantic v2 union.** Replay dispatch is hand-rolled in a pure module-level helper (AC-DR-1) because `Attempt` carries no `type` field (S2-01 hardening). A unit test asserts `TypeAlias` shape: `LedgerEntry` is `typing.Union[PreExecuteMarker, Attempt]` (or `PreExecuteMarker | Attempt`), not a Pydantic `RootModel`.
- [ ] **AC-PM-3 — `Attempt` is NOT edited in this story.** AST-walk on `git diff src/codegenie/gates/contract.py` between S2-01 HARDENED head and S2-02 GREEN head asserts the existing `Attempt` `ClassDef`'s field list is byte-identical (only `PreExecuteMarker` and any imports are added). Enforced by `tests/gates/test_s2_02_no_attempt_edit.py` — load both module ASTs, compare `Attempt.body` field nodes. (This is the "extension by addition" structural defense.)

### B. `SandboxSpecHash` NewType

- [ ] **AC-NT-3 — `SandboxSpecHash = NewType("SandboxSpecHash", str)`** in `src/codegenie/types/identifiers.py`. Docstring: `"BLAKE3-128 hex (32 chars) over canonical-JSON of SandboxSpec; ADR-0011 forward-compat seam."`. `sandbox/contract.py` is widened additively: `SandboxSpec.sandbox_spec_hash: SandboxSpecHash` and `SandboxRun.sandbox_spec_hash: SandboxSpecHash` (one-line edits — runtime-equivalent, type-checker-visible).
- [ ] **AC-NT-4 — `SandboxSpecHash` is IMPORTED, not redefined.** AST-walk on `src/codegenie/gates/` asserts no `NewType("SandboxSpecHash", ...)` call anywhere — same chokepoint pattern as S1-04 AC-A / AC-R / AC-S.

### C. `record_pre_execute` surface

- [ ] **AC-RPE-1 — Signature: `record_pre_execute(self, attempt_id: AttemptNumber, sandbox_spec_hash: SandboxSpecHash, started_at: datetime) -> None`.** Three positional args, no defaults, no `now_utc()` call inside. Matches ADR-0007 Decision verbatim.
- [ ] **AC-RPE-2 — Writes a single JSONL line of canonical shape `{"attempt_id": <int>, "chain_hash": <hex32>, "prev_hash": <hex32>, "sandbox_spec_hash": <hex32>, "started_at": <ISO-8601 UTC>, "type": "pre_execute"}`** (canonical = sorted-keys, separators `(",", ":")`, no trailing whitespace, terminated by `\n`). Exact JSON-key set asserted via `set(json.loads(line).keys()) == {"attempt_id", "chain_hash", "prev_hash", "sandbox_spec_hash", "started_at", "type"}`.
- [ ] **AC-RPE-3 — fsync discipline mirrors `record(attempt)`.** Two `os.fsync` calls per `record_pre_execute`: one on the JSONL file fd, one on the parent dir fd. Verified by `unittest.mock.patch("codegenie.gates.retry_ledger.os.fsync")` — call count = 2; ordering = file fd then dir fd.

### D. Chain participation (the load-bearing invariant)

- [ ] **AC-CH-1 — Marker `prev_hash` chains from `head()` *at marker-write time*.** Implementation: `prev_hex = self.head().hex(); marker.prev_hash = prev_hex`. Test: `record_pre_execute(1, "ab"*16, t)` then read line 0; assert `json.loads(line)["prev_hash"] == ledger_head_before_marker.hex()`.
- [ ] **AC-CH-2 — Following `record(attempt)` chains from the marker's `chain_hash`, not the marker's `prev_hash`.** This is the test the draft already had — kept verbatim except hash-size fix. After `record_pre_execute(1, ...); record(_make_attempt(1, ...))`, the on-disk attempt row's `prev_hash` equals the marker row's `chain_hash`.
- [ ] **AC-CH-3 — Marker `chain_hash` is computed over the canonical bytes of the marker payload excluding `chain_hash`** (mirrors S2-01 AC-CJ-1 for `Attempt`). Implementation: a new pure helper `_canonical_json_marker(marker: PreExecuteMarker) -> bytes` returns `json.dumps(marker.model_dump(mode="json", exclude={"chain_hash"}), sort_keys=True, separators=(",", ":")).encode()`. The chain_hash is then `_compute_chain_hash(prev_hex, _canonical_json_marker(marker_with_placeholder))`. Replay does the same.
- [ ] **AC-CH-4 — `record_pre_execute` ignores caller-supplied `prev_hash` / `chain_hash`.** This is impossible by signature (those are not parameters) — but the *internal builder* must use `self.head().hex()` for `prev_hash` and `"0" * 32` as the placeholder for `chain_hash` before computation. Mirrors S2-01 AC-IG-1 in spirit. New AC tightens: AST-walk on `record_pre_execute` body asserts no reference to a caller-provided hash variable.

### E. Out-of-order / duplicate guards (validation BEFORE write)

- [ ] **AC-OO-3 — `record_pre_execute(attempt_id, ...)` accepts iff `attempt_id == self._next_attempt_id` AND `self._marker_pending is False`.** Any other state raises `LedgerAttemptOutOfOrder(expected=self._next_attempt_id, got=attempt_id, context="record_pre_execute")` *before* any disk write. Test: `record_pre_execute(1, h, t); record_pre_execute(1, h, t)` raises (`.context == "record_pre_execute"`, `.expected == 1`, `.got == 1` — same `attempt_id` because `_next_attempt_id` does NOT advance on marker — but `_marker_pending` is the discriminator).
- [ ] **AC-OO-4 — `record(attempt)` after `record_pre_execute(attempt.attempt_id, ...)` succeeds and clears `_marker_pending`.** Mismatched `attempt.attempt_id` (e.g., marker for 1, then `record(attempt_id=2)`) raises `LedgerAttemptOutOfOrder(expected=1, got=2, context="record")`.
- [ ] **AC-OO-5 — `LedgerAttemptOutOfOrder` carries `.context: Literal["record", "record_pre_execute"]`.** Pure addition over S2-01's `.expected`/`.got`. Callers (and reviewers) can distinguish double-marker from out-of-order attempt without parsing strings.
- [ ] **AC-OO-6 — `record(attempt)` without a preceding marker is still legal** (the marker is *optional* per ADR-0007 — only `GateRunner` in S5-02 will start calling it). Test: fresh ledger, `record(_make_attempt(1, ...))` succeeds, no `LedgerAttemptOutOfOrder` raised, `entries()` returns `[Attempt(...)]`.

### F. Recovery semantics (`_marker_pending` on reopen)

- [ ] **AC-RR-5 — `__init__` recovers `_marker_pending` from the file tail.** If the file's *last row* parses as `"type": "pre_execute"` AND there is no subsequent `"type": "attempt"` row with the same `attempt_id`, set `self._marker_pending = True` and `self._next_attempt_id = marker.attempt_id` (NOT `+ 1` — the attempt slot is still open). Otherwise `_marker_pending = False` and `_next_attempt_id` follows S2-01 AC-RR-1. Pure addition to `_recover_chain_state` — extend its return tuple from `(next_attempt_id, last_chain_hash)` to `(next_attempt_id, last_chain_hash, marker_pending)` (S2-01 callers will need to unpack the third element — that's a one-line edit covered by S2-01's existing tests staying green).
- [ ] **AC-RR-6 — Reopen with a trailing orphan marker preserves the marker's `chain_hash` as `head()`.** Test: construct ledger, `record_pre_execute(1, "ab"*16, t)`, discard instance, construct second `RetryLedger(...)` over same gate-dir; assert `ledger.head() == bytes.fromhex(marker.chain_hash)`; assert `ledger._marker_pending is True`; assert next `record(_make_attempt(1, prev_hash=ledger.head().hex()))` succeeds and chains from the marker.
- [ ] **AC-RR-7 — Reopen with a marker-attempt-marker tail (marker for `n`, attempt for `n`, marker for `n+1`) sets `_marker_pending = True` and `_next_attempt_id = n+1`.** This is the "Phase 6 worker crashed after the second marker, before the second attempt" scenario.

### G. `entries()` reader (the discriminated-union seam)

- [ ] **AC-DR-1 — `entries() -> list[LedgerEntry]` returns both row types in file order.** `LedgerEntry: TypeAlias = PreExecuteMarker | Attempt`. Dispatch via a pure module-level helper `_parse_ledger_row(payload: dict, row_index: int) -> LedgerEntry` that reads `payload["type"]` and routes to `PreExecuteMarker.model_validate(payload)` or `Attempt.model_validate(payload)` (after popping `"type"` for the `Attempt` branch — S2-01 AC-T-2 precedent). Unknown `type` raises `AuditChainCorrupted(kind="unknown_type", row_index=row_index, row_type=None)`.
- [ ] **AC-DR-2 — `entries()` verifies the chain across mixed rows.** Each row's `prev_hash` must equal the previous row's `chain_hash` (or `prev_chain_head.hex()` for the first row, or `"0" * 32` if both are None). Mismatch raises `AuditChainCorrupted(kind="chain_mismatch", row_index=i, row_type=<row's type>)`. Test parametrizes the mismatch on row 0 (marker only), row 1 (marker→attempt), row 2 (marker→attempt→marker).
- [ ] **AC-DR-3 — `attempts()` still returns only `"attempt"` rows in file order** (S2-01 AC-T-2 preserved). Implementation: `return [e for e in self.entries() if isinstance(e, Attempt)]`. Test: orphan marker → `attempts() == []`; marker + attempt → `attempts() == [Attempt(...)]`.
- [ ] **AC-DR-4 — `_parse_ledger_row` is a module-level pure function.** Same module-purity test as S2-01 AC-PH-1 — AST-walks `retry_ledger.py` and asserts `_parse_ledger_row` is at `ast.Module` top level, not nested in a `ClassDef`.

### H. Tamper detection (parametrized adversarial)

- [ ] **AC-AT-3 — Parametrized tamper across marker fields.** `tests/adversarial/test_audit_chain_tamper.py` adds parametrize cases for `{sandbox_spec_hash, started_at, attempt_id, prev_hash, type}` on a `"pre_execute"` row. Each tamper raises `AuditChainCorrupted`. Assertions: `exc.row_index == 1` (1-based), `exc.row_type == "pre_execute"`, `exc.kind in {"chain_mismatch", "unknown_type", "extra_field", "schema_error"}`.
- [ ] **AC-AT-4 — Marker tamper invalidates the *following* attempt's chain.** The witness that the marker participates in the chain: after `record_pre_execute(1, ...); record(_make_attempt(1, ...))`, tamper one byte in the marker's `sandbox_spec_hash`. Replay raises `AuditChainCorrupted` on the *marker* row (row 1) with `kind="chain_mismatch"` — even though the *attempt* row is byte-perfect, the chain breaks at row 1 because the marker's recomputed `chain_hash` no longer matches the on-disk value, AND the attempt's `prev_hash` no longer matches the marker's recomputed `chain_hash`. The test asserts the *first* raise is on row 1 (defensive walker stops at first break).
- [ ] **AC-AT-5 — `AuditChainCorrupted.row_type: Literal["attempt", "pre_execute"] | None`.** Additive over S2-01 AC-AT-2. `None` when `kind == "unknown_type"` (the row had no parseable type discriminator). Tests assert on the attribute, not on `str(exc)`.
- [ ] **AC-AT-6 — Extra unknown JSON field on a `"pre_execute"` row raises `AuditChainCorrupted`.** Mirrors S2-01 AC-EF-1 for the new row type — `PreExecuteMarker.model_config = ConfigDict(extra="forbid")` catches unknowns; replay re-raises as `AuditChainCorrupted(kind="extra_field", row_type="pre_execute", row_index=...)`. Mutation-resistance against silent field drift.

### I. Property tests (mutation-witness, not tautology)

- [ ] **AC-PROP-M-1 — Prefix-replay invariance across mixed rows (hypothesis).** For any sequence of `[marker(i), attempt(i)]` pairs of length N ∈ [1, 4], replaying `attempts.jsonl` truncated to any prefix M ≤ 2N reproduces the same chain hashes for rows 1..M as the full-file replay. Catches off-by-one prev_hash threading across row types.
- [ ] **AC-PROP-M-2 — Marker-payload-permutation witness (hypothesis).** For any two markers A and B with different `sandbox_spec_hash` values at positions (1, 2), the head after `record_pre_execute(A); record_pre_execute(B)` (impossible due to AC-OO-3 — so this property is recast: after `record_pre_execute(A); record(attempt_A); record_pre_execute(B); record(attempt_B)`, the head differs from the head after the same sequence with A and B swapped). Catches a buggy implementation that hashes only the attempt payload without rolling the marker's `chain_hash` into the chain.
- [ ] **AC-PROP-M-3 — Canonical-bytes determinism for `PreExecuteMarker` (hypothesis).** `_canonical_json_marker(marker)` is byte-identical across 100 independent calls. Same property as S2-01 AC-PROP-3 for `Attempt`.

### J. Golden-file ordering (without `freezegun`)

- [ ] **AC-GF-1 — `tests/gates/test_pre_execute_marker.py::test_jsonl_ordering` writes the golden pair.** The test constructs `started_at = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)`, `_make_attempt(1, ...)` with deterministic `RunId("run-0001")` and `started_at`/`ended_at` set to the same fixed datetime. Calls `record_pre_execute(AttemptNumber(1), SandboxSpecHash("ab"*16), started_at)` then `record(attempt)`. Reads `attempts.jsonl`, splits lines, asserts: (a) exactly 2 lines; (b) `json.loads(lines[0])["type"] == "pre_execute"`; (c) `json.loads(lines[1])["type"] == "attempt"`; (d) `lines[1]_parsed["prev_hash"] == lines[0]_parsed["chain_hash"]` (the chain link).
- [ ] **AC-GF-2 — Golden file `tests/golden/attempts_jsonl_pre_execute_then_attempt.jsonl` is byte-equal** to the produced output (no substitutions because the test injects deterministic timestamps + hashes directly). The test reads the golden file and asserts byte-equality with the live output. To regenerate after a deliberate chain-shape change: delete the file and re-run the test (it self-heals iff `CODEGENIE_REGEN_GOLDEN=1`, mirroring the repo's existing pattern — see `tests/golden/README.md`).

### K. Logging + observability

- [ ] **AC-LG-1 — structlog event `gates.ledger.pre_execute_recorded` emitted on every successful marker write,** with fields `gate_id`, `attempt_id`, `sandbox_spec_hash[:8]` (8-char prefix only; full hash is on disk — leak-safe). Verified via `structlog.testing.capture_logs()`. The event name is added to S1-01's event-constants module.

### L. Schema-fence & banned-substring tests stay green

- [ ] **AC-SF-1 — `tests/schema/test_objective_signals_static.py` continues to pass** — no `confidence` / `llm` / `self_reported` / `model_says` substring introduced in `PreExecuteMarker` or any new test code (ADR-0014).
- [ ] **AC-SF-2 — `tests/schema/test_audit_chain_tamper.py` continues to pass** with the new `row_type` attribute available; if that test asserts on `kind`/`row_index` only (S2-01 AC-AT-2), no edit is needed. If it currently has any code path that imports `PreExecuteMarker` or `entries()`, those paths land here.

### M. Module purity + import allowlist (no new file; re-runs S2-01's purity test)

- [ ] **AC-MP-1 — `tests/gates/test_retry_ledger_purity.py` stays green with the additions.** New module-level functions `_canonical_json_marker` and `_parse_ledger_row` are at `ast.Module` top level (not nested in `ClassDef`). Import allowlist gains nothing new (all needed names — `Literal`, `TypeAlias`, etc. — were already in S2-01's allowlist). If `Union`/`TypeAlias` need to be added, the AC asserts the additive widening is intentional (one extra row in the S2-01 test's allowlist set).
- [ ] **AC-MP-2 — `tests/gates/test_contract_purity.py` (from S1-04) stays green with `PreExecuteMarker` added.** Same discipline.

### N. Quality gates (canonical form, mirrors S2-01)

- [ ] **AC-QG-7 — Coverage on `src/codegenie/gates/retry_ledger.py` ≥ 95% line / ≥ 90% branch** after S2-02 additions.
- [ ] **AC-QG-8 — `ruff check src/codegenie/gates src/codegenie/types/identifiers.py tests/gates tests/adversarial`** clean.
- [ ] **AC-QG-9 — `ruff format --check src/codegenie/gates src/codegenie/types/identifiers.py tests/gates`** clean.
- [ ] **AC-QG-10 — `mypy --strict src/codegenie/gates src/codegenie/types`** clean.
- [ ] **AC-QG-11 — `pytest tests/gates/test_pre_execute_marker.py tests/gates/test_retry_ledger_entries.py tests/gates/test_retry_ledger_resume.py tests/adversarial/test_audit_chain_tamper.py tests/gates/test_retry_ledger_properties.py`** all pass. (The S2-01 resume test gets an additional case parametrized in for AC-RR-5..AC-RR-7.)
- [ ] **AC-QG-12 — TDD plan's red test exists, is committed, and is green.**

## Implementation outline

1. **`src/codegenie/types/identifiers.py`** — add `SandboxSpecHash = NewType("SandboxSpecHash", str)` with docstring per AC-NT-3.
2. **`src/codegenie/sandbox/contract.py`** — widen `SandboxSpec.sandbox_spec_hash` and `SandboxRun.sandbox_spec_hash` annotations from `str` to `SandboxSpecHash`. Pure type-checker edit; runtime behavior unchanged (S1-02's `RunId` precedent — same widening shape).
3. **`src/codegenie/gates/contract.py`** — add `PreExecuteMarker` frozen Pydantic model per AC-PM-1. Do NOT touch `Attempt`.
4. **`src/codegenie/gates/errors.py`** — widen `AuditChainCorrupted` with `.row_type: Literal["attempt", "pre_execute"] | None = None`. Widen `LedgerAttemptOutOfOrder` with `.context: Literal["record", "record_pre_execute"]`. Both purely additive — S2-01 tests still pass because the new attributes default to safe values when constructed S2-01-style.
5. **`src/codegenie/gates/retry_ledger.py`** — module-level helpers first:
   - `_canonical_json_marker(marker: PreExecuteMarker) -> bytes` — `marker.model_dump(mode="json", exclude={"chain_hash"})` → canonical-JSON bytes. Pure.
   - `LedgerEntry: TypeAlias = PreExecuteMarker | Attempt` at module top level.
   - `_parse_ledger_row(payload: dict, row_index: int) -> LedgerEntry` — reads `payload["type"]`; `match` on the value:
     - `"attempt"` → drop `"type"`, return `Attempt.model_validate(payload)` (catch `ValidationError`, re-raise as `AuditChainCorrupted(kind="extra_field" or "schema_error", row_index, row_type="attempt")`).
     - `"pre_execute"` → return `PreExecuteMarker.model_validate(payload)` (similar error wrapping; row_type="pre_execute").
     - anything else → raise `AuditChainCorrupted(kind="unknown_type", row_index, row_type=None, message=f"unknown row type: {payload['type']!r}")`.
   - Extend `_recover_chain_state(jsonl_path: Path) -> tuple[int, str | None, bool]` — third tuple element is `marker_pending`. Algorithm: stream-parse the file; if the last row is a `"pre_execute"` AND there is no later `"attempt"` row with the same `attempt_id`, return `(marker.attempt_id, marker.chain_hash, True)`. Otherwise, return the S2-01 semantics with `False` appended.
6. **`RetryLedger.__init__`** — destructure the 3-tuple from `_recover_chain_state`. Store `self._marker_pending: bool`. S2-01's chain-root-verify branch (AC-RR-2) is unchanged because the first row's `prev_hash` check applies whether the first row is a marker or an attempt.
7. **`RetryLedger.record_pre_execute(attempt_id, sandbox_spec_hash, started_at)`** — per AC-OO-3 / AC-CH-1..AC-CH-4:
   - Validate `attempt_id == self._next_attempt_id` AND `self._marker_pending is False` AND `re.fullmatch(r"[0-9a-f]{32}", sandbox_spec_hash)`. Mismatch raises `LedgerAttemptOutOfOrder(context="record_pre_execute", ...)` BEFORE any disk write.
   - Build marker with placeholder `chain_hash="0" * 32`, `prev_hash=self.head().hex()`.
   - Compute `chain_hash = _compute_chain_hash(prev_hex, _canonical_json_marker(marker))`.
   - `record = marker.model_copy(update={"chain_hash": chain_hash}).model_dump(mode="json")`.
   - `line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"`.
   - Append to JSONL fd; `flush()`; `os.fsync(file_fd)`; close. `os.fsync(dir_fd)` with `EINVAL` swallowing (S2-01 K precedent).
   - `self._last_chain_hash = chain_hash`; `self._marker_pending = True`. NOTE: `_next_attempt_id` does NOT advance — the attempt slot is still open.
   - structlog `gates.ledger.pre_execute_recorded` with `gate_id`, `attempt_id`, `sandbox_spec_hash[:8]`.
8. **Extend `RetryLedger.record(attempt)`** — minimal change per AC-OO-4:
   - When validating `attempt.attempt_id`, allow it to equal `_next_attempt_id` whether or not `_marker_pending` is true (S2-01 semantics unchanged).
   - After successful append, set `self._marker_pending = False` AND increment `_next_attempt_id` (S2-01 already did the increment — no change).
   - The `prev_hex = self.head().hex()` substitution in S2-01 already pulls from the marker's `chain_hash` once `_last_chain_hash` is set in step 7 — *zero edit* to the chain-math line.
9. **Add `RetryLedger.entries() -> list[LedgerEntry]`** per AC-DR-1..AC-DR-2:
   - If file absent or empty: return `[]`.
   - For each line (1-based `row_index`): parse JSON; call `_parse_ledger_row(payload, row_index)`; recompute the chain via `_compute_chain_hash` (using `_canonical_json` for `Attempt`, `_canonical_json_marker` for `PreExecuteMarker`); byte-compare to the on-disk `chain_hash`; mismatch → `AuditChainCorrupted(kind="chain_mismatch", row_index, row_type=<entry's type>)`.
   - Return the list.
10. **Update `RetryLedger.attempts()`** per AC-DR-3 — one-liner: `return [e for e in self.entries() if isinstance(e, Attempt)]`. The S2-01 implementation that did `attempts()` directly via inline replay is replaced by this delegation; behavior is unchanged because `entries()` does the same chain verification + extra-field strictness S2-01 implemented.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/gates/test_pre_execute_marker.py`

```python
# tests/gates/test_pre_execute_marker.py
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codegenie.gates.contract import Attempt, GateOutcome, PreExecuteMarker
from codegenie.gates.errors import AuditChainCorrupted, LedgerAttemptOutOfOrder
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.sandbox.signals.models import ObjectiveSignals
from codegenie.types.identifiers import AttemptNumber, RunId, SandboxSpecHash


ZERO_16 = "0" * 32  # BLAKE3-128 sentinel as hex (16 bytes -> 32 hex chars)
FIXED_TS = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)
SPEC_HASH_AB = SandboxSpecHash("ab" * 16)
SPEC_HASH_CD = SandboxSpecHash("cd" * 16)


def _make_attempt(attempt_id: int) -> Attempt:
    """Deterministic attempt factory using newtype constructors (S1-04 Notes #1245)."""
    return Attempt(
        attempt_id=AttemptNumber(attempt_id),
        sandbox_run_id=RunId(f"run-{attempt_id:04d}"),
        signals=ObjectiveSignals(),
        outcome=GateOutcome(
            passed=False, attempt=AttemptNumber(attempt_id), failing_signals=[],
            retryable=True, state="failed_retryable", summary="",
            signals=ObjectiveSignals(),
        ),
        started_at=FIXED_TS, ended_at=FIXED_TS,
        prev_hash=ZERO_16, chain_hash=ZERO_16,  # placeholders; ledger overrides per AC-IG-1.
    )


def test_marker_precedes_attempt_and_chains(tmp_path: Path) -> None:
    """AC-CH-1, AC-CH-2, AC-GF-1, AC-RPE-1, AC-RPE-2."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=None)
    head_before = ledger.head().hex()

    ledger.record_pre_execute(AttemptNumber(1), SPEC_HASH_AB, FIXED_TS)
    ledger.record(_make_attempt(1))

    lines = (tmp_path / "gates" / "stage6_validate" / "attempts.jsonl").read_text().splitlines()
    assert len(lines) == 2
    marker, attempt = json.loads(lines[0]), json.loads(lines[1])

    assert marker["type"] == "pre_execute" and attempt["type"] == "attempt"
    assert marker["attempt_id"] == attempt["attempt_id"] == 1
    assert marker["prev_hash"] == head_before, "AC-CH-1: marker chains from head() at write time"
    assert attempt["prev_hash"] == marker["chain_hash"], "AC-CH-2: attempt chains FROM marker, not marker's prev_hash"
    assert re.fullmatch(r"[0-9a-f]{32}", marker["chain_hash"]), "BLAKE3-128 hex"
    assert set(marker.keys()) == {"attempt_id", "chain_hash", "prev_hash", "sandbox_spec_hash", "started_at", "type"}


def test_orphan_marker_visible_via_entries_not_attempts(tmp_path: Path) -> None:
    """AC-DR-1, AC-DR-3."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    ledger.record_pre_execute(AttemptNumber(1), SPEC_HASH_CD, FIXED_TS)

    assert ledger.attempts() == []
    entries = ledger.entries()
    assert len(entries) == 1
    assert isinstance(entries[0], PreExecuteMarker)
    assert entries[0].sandbox_spec_hash == SPEC_HASH_CD


def test_double_marker_without_intervening_attempt_raises(tmp_path: Path) -> None:
    """AC-OO-3, AC-OO-5."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    ledger.record_pre_execute(AttemptNumber(1), SPEC_HASH_AB, FIXED_TS)

    with pytest.raises(LedgerAttemptOutOfOrder) as exc:
        ledger.record_pre_execute(AttemptNumber(1), SPEC_HASH_AB, FIXED_TS)
    assert exc.value.context == "record_pre_execute"
    assert exc.value.expected == 1 and exc.value.got == 1


def test_record_without_marker_still_succeeds(tmp_path: Path) -> None:
    """AC-OO-6: the marker is optional; S2-01 callers (no GateRunner yet) must still work."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    ledger.record(_make_attempt(1))
    assert len(ledger.attempts()) == 1
    assert len(ledger.entries()) == 1


def test_mismatched_attempt_after_marker_raises(tmp_path: Path) -> None:
    """AC-OO-4: marker for n; record(m) with m != n raises."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    ledger.record_pre_execute(AttemptNumber(1), SPEC_HASH_AB, FIXED_TS)

    with pytest.raises(LedgerAttemptOutOfOrder) as exc:
        ledger.record(_make_attempt(2))
    assert exc.value.context == "record"
    assert exc.value.expected == 1 and exc.value.got == 2


@pytest.mark.parametrize(
    "field, new_value",
    [
        ("sandbox_spec_hash", "ff" * 16),
        ("started_at", "2030-01-01T00:00:00+00:00"),
        ("attempt_id", 99),
        ("prev_hash", "ff" * 16),
        ("type", "pre_execute_v2"),
    ],
)
def test_marker_tamper_parametrized(tmp_path: Path, field: str, new_value: object) -> None:
    """AC-AT-3, AC-AT-5: structured-attribute assertion, no substring matches."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    ledger.record_pre_execute(AttemptNumber(1), SPEC_HASH_AB, FIXED_TS)

    jsonl = tmp_path / "gates" / "g" / "attempts.jsonl"
    row = json.loads(jsonl.read_text().strip())
    row[field] = new_value
    jsonl.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    with pytest.raises(AuditChainCorrupted) as exc:
        ledger.entries()
    assert exc.value.row_index == 1
    if field == "type":
        assert exc.value.row_type is None  # unknown_type — couldn't classify
        assert exc.value.kind == "unknown_type"
    else:
        assert exc.value.row_type == "pre_execute"
        assert exc.value.kind in {"chain_mismatch", "schema_error", "extra_field"}


def test_marker_tamper_invalidates_following_attempt_chain(tmp_path: Path) -> None:
    """AC-AT-4: chain-participation witness."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    ledger.record_pre_execute(AttemptNumber(1), SPEC_HASH_AB, FIXED_TS)
    ledger.record(_make_attempt(1))

    jsonl = tmp_path / "gates" / "g" / "attempts.jsonl"
    lines = jsonl.read_text().splitlines()
    marker_row = json.loads(lines[0])
    marker_row["sandbox_spec_hash"] = "ff" * 16  # tamper marker payload
    lines[0] = json.dumps(marker_row, sort_keys=True, separators=(",", ":"))
    jsonl.write_text("\n".join(lines) + "\n")

    with pytest.raises(AuditChainCorrupted) as exc:
        ledger.entries()
    # First failure is on the marker row — walker stops there.
    assert exc.value.row_index == 1 and exc.value.row_type == "pre_execute"
    assert exc.value.kind == "chain_mismatch"


def test_extra_field_on_marker_row_raises(tmp_path: Path) -> None:
    """AC-AT-6."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="g", prev_chain_head=None)
    ledger.record_pre_execute(AttemptNumber(1), SPEC_HASH_AB, FIXED_TS)

    jsonl = tmp_path / "gates" / "g" / "attempts.jsonl"
    row = json.loads(jsonl.read_text().strip())
    row["rogue_field"] = "x"
    jsonl.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    with pytest.raises(AuditChainCorrupted) as exc:
        ledger.entries()
    assert exc.value.row_type == "pre_execute"
    assert exc.value.kind in {"extra_field", "schema_error"}


def test_jsonl_ordering_byte_equal_to_golden(tmp_path: Path) -> None:
    """AC-GF-1, AC-GF-2."""
    ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=None)
    ledger.record_pre_execute(AttemptNumber(1), SPEC_HASH_AB, FIXED_TS)
    ledger.record(_make_attempt(1))

    produced = (tmp_path / "gates" / "stage6_validate" / "attempts.jsonl").read_bytes()
    golden = Path(__file__).parent.parent / "golden" / "attempts_jsonl_pre_execute_then_attempt.jsonl"
    assert produced == golden.read_bytes(), "AC-GF-2: byte-equal golden"
```

Additional test files (per Files-to-touch):

- `tests/gates/test_retry_ledger_resume.py` — extended with AC-RR-5..AC-RR-7. New cases: trailing orphan marker recovery (assert `head() == marker.chain_hash`, `_marker_pending is True`); marker-attempt-marker tail recovery; second `RetryLedger(...)` over orphan-marker file followed by `record(_make_attempt(marker.attempt_id))` succeeds; followed by a second `record_pre_execute(marker.attempt_id, ...)` raises (already-completed slot).
- `tests/gates/test_retry_ledger_entries.py` — AC-DR-1..AC-DR-4: pure dispatch on `"type"`; `attempts()` filters; chain verification across mixed rows; unknown type raises `kind="unknown_type"` `row_type=None`; `_parse_ledger_row` is module-level (AST-walk).
- `tests/gates/test_retry_ledger_properties.py` — extended with AC-PROP-M-1..AC-PROP-M-3 (hypothesis strategies for `PreExecuteMarker` + mixed sequences).
- `tests/gates/test_retry_ledger_fsync.py` — extended with `record_pre_execute` mock case (AC-RPE-3).
- `tests/adversarial/test_audit_chain_tamper.py` — extended with marker-field parametrize cases (AC-AT-3..AC-AT-6).
- `tests/gates/test_s2_02_no_attempt_edit.py` — AST-walk asserting `Attempt`'s field list is byte-identical to S2-01's HARDENED head (AC-PM-3).
- `tests/gates/test_pre_execute_marker.py` — the core test file shown above.

### Green — make it pass

Smallest implementation per Implementation outline §1–§10. Module-level pure helpers first (`_canonical_json_marker`, `_parse_ledger_row`, extended `_recover_chain_state`); then `PreExecuteMarker` on `contract.py`; then `record_pre_execute` and `entries()` on `RetryLedger`. The shared `_compute_chain_hash` helper from S2-01 is reused unchanged.

### Refactor — clean up

- Module docstring on `retry_ledger.py` updated to cite ADR-0007 verbatim about the two-phase write.
- `PreExecuteMarker` carries a docstring naming ADR-0007 and explaining that the model is the *durable* record of "we are about to execute" — not a verdict.
- `_parse_ledger_row`'s `match` statement structured for easy registry-promotion later (Note #18 — when a 3rd row type lands, promote to a `Final[dict[str, Callable]]` registry).
- Confirm `tests/schema/test_objective_signals_static.py` still passes — no banned substrings in the new code.
- Verify `mypy --strict` on the `LedgerEntry: TypeAlias = PreExecuteMarker | Attempt` declaration (PEP 604 union must work; if not, fall back to `Union[PreExecuteMarker, Attempt]` from `typing`).
- `__repr__` on `RetryLedger` unchanged — already exposes only `gate_id` and `_next_attempt_id` per S2-01 AC-NT-2; `_marker_pending` is intentionally NOT exposed (debug-leak hygiene).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Add `SandboxSpecHash = NewType(...)` (AC-NT-3). |
| `src/codegenie/sandbox/contract.py` | Widen `SandboxSpec.sandbox_spec_hash` and `SandboxRun.sandbox_spec_hash` annotations to `SandboxSpecHash` (one-line additive). |
| `src/codegenie/gates/contract.py` | Add `PreExecuteMarker` frozen Pydantic model (AC-PM-1). Do NOT touch `Attempt`. |
| `src/codegenie/gates/errors.py` | Widen `AuditChainCorrupted` with `.row_type`; widen `LedgerAttemptOutOfOrder` with `.context`. Both purely additive (AC-AT-5, AC-OO-5). |
| `src/codegenie/gates/retry_ledger.py` | Add `_canonical_json_marker`, `LedgerEntry` TypeAlias, `_parse_ledger_row`; extend `_recover_chain_state` return tuple; add `record_pre_execute`, `entries`; simplify `attempts()` to delegate to `entries()`. |
| `tests/gates/test_pre_execute_marker.py` | Core marker tests (red + chain + tamper + ordering + golden — shown above). |
| `tests/gates/test_retry_ledger_entries.py` | `entries()` dispatch + chain verification (AC-DR-1..AC-DR-4). |
| `tests/gates/test_retry_ledger_resume.py` | Extended with AC-RR-5..AC-RR-7 (`_marker_pending` recovery). |
| `tests/gates/test_retry_ledger_properties.py` | Extended with AC-PROP-M-1..AC-PROP-M-3 (hypothesis). |
| `tests/gates/test_retry_ledger_fsync.py` | Extended with `record_pre_execute` mock (AC-RPE-3). |
| `tests/adversarial/test_audit_chain_tamper.py` | Extended with parametrized marker-tamper cases (AC-AT-3..AC-AT-6). |
| `tests/gates/test_s2_02_no_attempt_edit.py` | AST-walk asserting `Attempt` field list is byte-identical to S2-01 HARDENED head (AC-PM-3 — the extension-by-addition structural defense). |
| `tests/golden/attempts_jsonl_pre_execute_then_attempt.jsonl` | Byte-equal golden file with deterministic timestamps (AC-GF-2). |
| `tests/gates/conftest.py` | Optionally export `FIXED_TS` and the deterministic `_make_attempt` factory if multiple tests need it. |

## Out of scope

- `GateRunner` call-site that invokes `record_pre_execute` before `client.execute` — S5-02.
- `SandboxResumeBehavior` enum on `GateContext` — Phase 6.
- Resume semantics ("re-execute" vs "skip") — Phase 6; this story's invariant is "the marker is *visible* on resume" and stops there.
- CLI surfacing of orphan markers in `codegenie sandbox inspect` — S8-01 (it just reads `entries()`).
- A `_ROW_TYPE_REGISTRY` lift for `_parse_ledger_row` — deferred to the 3rd row type's story per rule-of-three (CLAUDE.md Rule 2). Today: `match` statement.

## Notes for the implementer

### S2-01 hardening carryforward (READ FIRST)

- **DO NOT add a `type` field to `Attempt`.** S2-01 hardening flag #18 and AC-T-1..AC-T-3 keep the `"attempt"` discriminator at the JSONL serialization layer. `PreExecuteMarker` carries its own `type: Literal["pre_execute"]` because the marker is a fresh model — but `Attempt` is HARDENED frozen, and editing it would re-trigger S1-04 / S2-01's chain of dependencies. AC-PM-3 has a structural defense (AST diff) that will fail your PR if you touch `Attempt`.
- **Hash sizes are 32 hex chars (BLAKE3-128), not 64.** Every test fixture in this story uses `"ab" * 16`, NOT `"ab" * 32`. S1-04's `Attempt` validators (`^[0-9a-f]{32}$`) will reject anything longer. `blake3(...).hexdigest(length=16)` — never the default 64-char.
- **`_recover_chain_state` return tuple widens from 2 to 3 elements.** Existing S2-01 callers (the S2-01 `__init__` line) need a one-line edit to unpack the new `marker_pending` element. This is fine — the S2-01 test suite covers the call site and will catch the breakage if the unpacking is missed. The S2-01 *contract* (recovery of `_next_attempt_id` and `_last_chain_hash`) is preserved; the new field is purely additive.

### ADR-0007 contract verbatim

- `record_pre_execute(attempt_id, sandbox_spec_hash, started_at) -> None` — 3 args, caller supplies the clock. Do NOT introduce `now_utc()` inside the ledger; that mixes pure logic with I/O (CLAUDE.md "Functional core / imperative shell" — the ledger is the imperative shell for the file, the caller is the imperative shell for the wall clock).
- The marker payload is minimal — no signals, no outcome — it is a "we're about to execute" lightweight record, not a verdict. Per AC-PM-1, the field set is exactly `{type, attempt_id, sandbox_spec_hash, started_at, prev_hash, chain_hash}`.

### `_marker_pending` recovery semantics

- This is the load-bearing Phase 6 invariant the story exists to ship. A second `RetryLedger(...)` over the same gate-dir on process restart MUST recover `_marker_pending = True` if the file's tail is an orphan marker. Otherwise a worker that crashes between `record_pre_execute` and `record(attempt)` could let a *second* `record_pre_execute(same_attempt_id)` succeed on restart — exactly the silent corruption Gap 1 was filed to close.
- `_recover_chain_state` is the single point of recovery — extending its return tuple keeps the recovery logic pure and unit-testable in isolation. Do not duplicate the file-tail scan inside `__init__`.

### `LedgerEntry` discriminated-union shape

- `LedgerEntry: TypeAlias = PreExecuteMarker | Attempt`. This is **not** a Pydantic discriminated union (which would require `type` on both models — S2-01 hardening keeps `Attempt` clean). Dispatch is hand-rolled in `_parse_ledger_row` via a `match` statement.
- When a 3rd row type lands (likely S6+ `sandbox_health_snapshot` or S7+ `cost_ledger_entry`), promote the `match` to a `_ROW_TYPE_REGISTRY: Final[dict[str, type[BaseModel]]]` per CLAUDE.md "data-driven registries over branching code." Today is **not** that day — Rule 2 caps premature abstraction. Surface the seam in the module docstring so the next story author finds it.

### Registry seam vs. rule-of-three (Design-Patterns critic carryforward)

- The Design-Patterns critic flagged this as a place to introduce `@register_ledger_row_type(...)`. The Coverage critic's "registry over branching" recommendation conflicts with Consistency's "today there are only 2 row types — Rule 2 caps premature abstraction." Consistency wins; the registry is deferred. Document the seam in `retry_ledger.py`'s module docstring as a tracked extension point so the 3rd-row-type executor lands the registry as pure addition.

### Forward-compat for S2-03

- S2-03 will need `entries()` to read both `"attempt"` and `"pre_execute"` rows for chain-head startup verification. This story ships `entries()` ready for that. S2-03's validator pass needs to confirm its TDD plan uses `entries()` (or the underlying helpers), not S2-01's `attempts()`.

### Subtle correctness traps

- The `started_at` field on `PreExecuteMarker` is the *pre-execute* timestamp; `Attempt.started_at` is when execute *returned*. Two distinct timestamps; do NOT alias them. Both have separate semantic meaning for cost/audit analysis (e.g., `attempt.started_at - marker.started_at` ≈ sandbox boot + setup time).
- Pydantic v2 preserves field declaration order; declare `type` first in `PreExecuteMarker` so canonical-JSON output puts `"type"` first after `sort_keys=True` (alphabetical: `attempt_id` < `chain_hash` < `prev_hash` < `sandbox_spec_hash` < `started_at` < `type` — the field order in the *class* doesn't actually matter for canonical JSON because keys are sorted; but declaring `type` first is the intent-documentation discipline matching `Attempt`).
- The chain-tamper detection in `entries()` must surface *which row type* failed in the structured attribute, not just the message. Reviewers need to distinguish marker tamper (rare; the marker is short-lived in-process) from attempt tamper (common adversarial target).
- Keep the marker payload minimal — no signals, no outcome — it is a "we're about to execute" lightweight record, not a verdict.
