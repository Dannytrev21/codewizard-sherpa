# Validation report — S2-02 Pre-execute marker `record_pre_execute` + JSONL ordering (Gap 1)

**Story:** [`../S2-02-pre-execute-marker-gap-1.md`](../S2-02-pre-execute-marker-gap-1.md)
**Validated:** 2026-05-23
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S2-02 extends S2-01's `RetryLedger` with the pre-execute marker that closes ADR-0007's Gap 1 (worker dies between `SandboxClient.execute` returning and `RetryLedger.record` writing, leaving Phase 6's resume policy with no record an execute happened). The story's goal is correct and traces cleanly to ADR-0007. **But the draft was constructed before S2-01's hardening landed**, and it directly contradicts S2-01 HARDENED's load-bearing carryforward flags — six block-tier findings plus thirteen harden-tier and one nit-tier finding, twenty in total.

The block-tier issues, all of which would have made the executor either fail at first import or break the chain on first marker write:

1. **(consistency — block) Story directly violates S2-01 HARDENED carryforward flag #18.** Draft Implementation outline step 2: *"Update `Attempt` (in `gates/contract.py`) to add `type: Literal['attempt'] = 'attempt'` as the first field so canonical JSON always serializes `type` first."* S2-01 hardening (validation report blocks #2 and notes #18) **explicitly forbids this** — the `"type"` discriminator already lives at the JSONL serialization layer (S2-01 AC-T-1..AC-T-3 with the discriminator injected by `_canonical_json`), and `Attempt` is HARDENED frozen. Editing `Attempt` would silently violate CLAUDE.md "Extension by addition," would force a regeneration of S1-04's golden fixtures (which S2-01 hardening explicitly says is unnecessary), and would propagate to any downstream consumer of `Attempt` that asserts on `get_type_hints` or `model_fields`. Resolution: implementation outline rewritten; `PreExecuteMarker` carries its own `type: Literal["pre_execute"]` field; `Attempt` is untouched; **new AC-PM-3 is a structural defense** — an AST-walk asserts `Attempt`'s field list is byte-identical between S2-01's HARDENED head and S2-02's GREEN head. This is the kind of guard that catches a future executor (or a sloppy refactor) that ignores the Note and edits `Attempt` anyway. `tests/gates/test_s2_02_no_attempt_edit.py` added.

2. **(consistency — block) Hash sizes throughout TDD plan are 64-char (BLAKE3-256), but S1-04 HARDENED requires 32-char (BLAKE3-128).** Draft TDD: `record_pre_execute(attempt_id=1, sandbox_spec_hash="ab" * 32)` — 64 chars. S2-01 hardening block #1 pinned BLAKE3-128: `chain_hash`/`prev_hash` validated by `^[0-9a-f]{32}$`. The draft's `"ab" * 32` would be rejected at marker construction by Pydantic field_validators. `sandbox_spec_hash` *also* needs to be 32 hex chars: arch line 654 explicitly says `SandboxSpec.sandbox_spec_hash: str` is "blake3-128 over canonical-JSON" — ADR-0011's forward-compat seam. The draft's chain math (`blake3(...).hexdigest()` returning 64 chars by default) would never produce a hash that fits the field. Resolution: every `"ab" * 32` / `"cd" * 32` / `"ef" * 32` rewritten to `"ab" * 16` / `"cd" * 16` / `"ef" * 16`; `sandbox_spec_hash` validated by `^[0-9a-f]{32}$` in `PreExecuteMarker`; AC-PM-1 pins the hash-size constraint explicitly.

3. **(consistency — block) `record_pre_execute` signature contradicts ADR-0007 Decision.** Draft: `record_pre_execute(attempt_id: int, sandbox_spec_hash: str) -> None` — 2 args, `now_utc()` called inside. ADR-0007 Decision section: *"`RetryLedger` exposes `record_pre_execute(attempt_id, sandbox_spec_hash, started_at) -> None`"* — 3 args, caller supplies the clock. ADR wins per Consistency priority (Source-of-truth > Coverage). Also a design improvement: the ledger has no business owning the wall clock (mixes pure logic with hidden I/O — violates CLAUDE.md "Functional core / imperative shell"). The caller, `GateRunner` in S5-02, has access to the precise pre-execute timestamp and can inject it. Tests get free determinism — no `freezegun` dependency, no monkeypatch. Resolution: AC-RPE-1 pins the 3-arg signature; AC-GF-1 constructs the golden file with a fixed `started_at = datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC)` injected at the call site, no time-mocking required.

4. **(design — block) `LedgerEntry = Annotated[PreExecuteMarker | Attempt, Field(discriminator="type")]` would raise `PydanticSchemaGenerationError`.** Draft Implementation outline step 3 prescribes Pydantic v2's discriminated-union form. But this form requires the `type` field to be present and `Literal`-typed on *every* union member. Per block #1, `Attempt` has NO `type` field — the discriminator for `"attempt"` rows is at the JSONL serialization layer, not on the model. Pydantic v2 would reject the `Annotated[..., Field(discriminator="type")]` at schema construction with `PydanticSchemaGenerationError("Model Attempt does not have a field 'type' to use as a discriminator")`. The story would not even import. Resolution: AC-PM-2 pins `LedgerEntry` as a plain `TypeAlias = PreExecuteMarker | Attempt` union; AC-DR-1 introduces a pure module-level helper `_parse_ledger_row(payload: dict, row_index: int) -> LedgerEntry` that hand-rolls the dispatch via a `match` statement on `payload["type"]`. This also opens the seam for a future `_ROW_TYPE_REGISTRY` registry pattern (deferred per Rule 2 — see harden #14).

5. **(coverage — block) `_marker_pending` recovery on process restart is in a Note, not in any AC.** Draft Notes line: *"On a fresh process start, set it by replaying the file once in `__init__` and looking for a trailing `pre_execute` line."* Notes don't gate execution. Without an AC, the executor will skip this recovery, and the *exact* failure mode Gap 1 was filed to close — Phase 6 worker dies between marker and attempt, restarts, writes a second marker for the same `attempt_id` — proceeds silently. The ledger's `_next_attempt_id == 1` (per S2-01 AC-RR-1 if the file ends on an orphan marker, the last `"attempt"` row's `attempt_id + 1` is still `1`, *or* the file has only the marker and there is no last attempt, so `_next_attempt_id = 1` again), `_marker_pending == False`, second `record_pre_execute(1, ...)` succeeds — silent corruption of the chain semantics. Resolution: AC-RR-5 / AC-RR-6 / AC-RR-7 pin `_marker_pending` recovery on three explicit cases: (i) trailing orphan marker → `_marker_pending = True`, `_next_attempt_id = marker.attempt_id` (NOT `+ 1`); (ii) marker-attempt-marker tail → `_marker_pending = True`, `_next_attempt_id = second_marker.attempt_id`; (iii) marker-attempt → `_marker_pending = False`, `_next_attempt_id = attempt.attempt_id + 1`. `_recover_chain_state` widens its return tuple from 2 to 3 elements (purely additive — S2-01 callers get a one-line unpack edit covered by S2-01's existing resume tests).

6. **(test-quality — block) Tamper test relies on substring assertion that the S2-01 hardening explicitly removed.** Draft: `assert 'entry_type="pre_execute"' in str(exc.value) or "pre_execute" in str(exc.value)`. S2-01 hardening (validation report block #9 and AC-AT-2) explicitly removed substring assertions in favor of structured attributes (`.attempt_id: int | None`, `.row_index: int`, `.kind: Literal[...]`). The draft's test would either (a) fail because the executor moves to structured attributes and removes the substring, or (b) succeed for the wrong reason because the substring happens to appear via the exception's default `__str__`. Either way, the test is mutation-fragile. Resolution: `AuditChainCorrupted` gains `.row_type: Literal["attempt", "pre_execute"] | None` as a structured attribute (AC-AT-5); the tamper test asserts on `.row_type` and `.kind`, not on string-containment (AC-AT-3); the test is also parametrized across {sandbox_spec_hash, started_at, attempt_id, prev_hash, type} (5 cases) rather than the single tamper the draft had.

The remaining 14 findings were harden- or nit-tier and would not block execution but each tightens an AC, a test, or a forward-compat seam:

7. **(coverage — harden) Missing AC: `record_pre_execute` validates `sandbox_spec_hash` format.** Draft has no format check on the hash parameter; a caller passing `"not-a-hash"` would write a corrupted marker that fails *later* during replay. Per "fail loud" (CLAUDE.md Rule 12), validation should happen at the boundary. Added AC-OO-3: `re.fullmatch(r"[0-9a-f]{32}", sandbox_spec_hash)` BEFORE any disk write. Mirrors S2-01 AC-OO-1's validate-before-write pattern.

8. **(coverage — harden) Missing AC: validation order — checks BEFORE disk write.** Draft doesn't pin that `_marker_pending`, `attempt_id`, and `sandbox_spec_hash` checks happen before any append. A buggy implementation that does `validate → append → set _marker_pending` could leave the file in a state where `_marker_pending` is stale on disk. AC-OO-3 makes the ordering explicit: validate three conditions, raise `LedgerAttemptOutOfOrder` (or a new `ValueError` for hash-format), only then append.

9. **(test-quality — harden) Missing property test: chain-participation witness.** The draft has one ordering test and one chain test but no property test asserting that *changing a marker payload changes the next attempt's prev_hash*. This is the load-bearing invariant of the two-phase write — if the marker's `sandbox_spec_hash` is altered, the chain breaks at the next row. AC-PROP-M-2 added: payload-permutation witness across mixed sequences (`marker(A); attempt; marker(B); attempt` vs swapped A/B → different heads).

10. **(test-quality — harden) Missing property test: prefix-replay invariance over mixed rows.** S2-01 AC-PROP-1 pinned this for attempts; the marker should inherit the same property. Otherwise a buggy implementation that hashes only one row type into the chain could pass S2-01's property and fail on resume from a marker-only prefix. AC-PROP-M-1 added.

11. **(test-quality — harden) Missing property test: `_canonical_json_marker` determinism.** Same property as S2-01 AC-PROP-3 for `Attempt`, but for the new helper. Catches accidental dict-ordering drift in the new model. AC-PROP-M-3 added.

12. **(coverage — harden) Missing AC: structlog event `gates.ledger.pre_execute_recorded`.** Draft says "Emit structlog ... event" in Refactor. Refactors are nice-to-have; ACs are testable. Promoted to AC-LG-1 with leak-safe field list (`gate_id`, `attempt_id`, `sandbox_spec_hash[:8]`) — full hash on disk, not in logs.

13. **(coverage — harden) Missing AC: coverage gate.** Draft has no coverage AC. S2-01 has AC-QG-5 (≥ 95% line / ≥ 90% branch on `retry_ledger.py`). Added AC-QG-7 with the same threshold; S2-01's threshold doesn't grandfather S2-02 additions automatically.

14. **(design — harden) Primitive obsession on `sandbox_spec_hash: str`.** CLAUDE.md: "Newtype identifiers when they cross ≥ 2 module boundaries." `sandbox_spec_hash` crosses (a) `SandboxSpec` (sandbox/contract), (b) `SandboxRun` (sandbox/contract), (c) `PreExecuteMarker` (gates/contract) — 3 modules, rule-of-three cleared. Promoted to `SandboxSpecHash = NewType("SandboxSpecHash", str)` in `types/identifiers.py` with the standard docstring + AST-chokepoint pattern (AC-NT-4 mirrors S1-04 AC-A / AC-R / AC-S). `SandboxSpec`/`SandboxRun` annotations widen one-line.

15. **(design — harden) `PreExecuteMarker` placement: `retry_ledger.py` (draft) vs `contract.py` (correct).** `Attempt` lives in `contract.py` (S1-04); `PreExecuteMarker` is its sibling domain model and the same module is the import target for `codegenie sandbox inspect` (S8-01) and any external Phase 6 reader. Moved to `contract.py`. The `_canonical_json_marker` helper stays in `retry_ledger.py` because it's a chain-math concern.

16. **(design — harden) Registry seam vs. rule-of-three resolution.** A Design-Patterns critic carryforward would suggest `@register_ledger_row_type("pre_execute", PreExecuteMarker)` for future row types. Today there are only 2 row types — `match` statement is right. Per CLAUDE.md Rule 2 ("three similar lines is better than premature abstraction") + Synthesizer priority (Consistency > Design-Patterns), the registry is *deferred* and surfaced as a tracked seam in Notes-for-implementer. The 3rd row type's story will promote `_parse_ledger_row` to a `Final[dict[str, type[BaseModel]]]` registry as pure addition.

17. **(coverage — harden) Missing AC: `record(attempt)` without preceding marker still works.** The marker is *optional* per ADR-0007 — only `GateRunner` in S5-02 will call it; until then, any caller using `record(attempt)` directly must continue to work. Without this AC, the executor could "tighten" `record(attempt)` to *require* a marker, breaking S2-01 tests. Added AC-OO-6 with explicit "fresh ledger, no marker, `record(_make_attempt(1))` succeeds" test.

18. **(coverage — harden) Missing AC: `LedgerAttemptOutOfOrder.context` discriminator.** S2-01 ships `.expected` / `.got`. Without a third attribute, callers cannot distinguish double-marker from out-of-order-attempt. Added `.context: Literal["record", "record_pre_execute"]` as a pure addition; S2-01 tests still pass because callers that don't read `.context` are unaffected (AC-OO-5).

19. **(consistency — harden) Missing structural defense for "S2-02 must not edit `Attempt`."** Block #1 said "the executor must not edit `Attempt`." Notes alone are insufficient — a future executor running this story cold could ignore the Note. AC-PM-3 adds `tests/gates/test_s2_02_no_attempt_edit.py`, an AST-walk that asserts `Attempt`'s field list is byte-identical between S2-01 HARDENED head and S2-02 GREEN head. Failure mode: PR fails CI before review.

20. **(coverage — nit) Missing AC: module-purity test for added code.** S2-01 ships `test_retry_ledger_purity.py`; S1-04 ships `test_contract_purity.py`. Both should stay green with the new code. Added AC-MP-1 and AC-MP-2 — they're really "no new test file, just keep the existing ones green" but the explicit AC reminds the executor to re-run them and adds `_canonical_json_marker` / `_parse_ledger_row` to the expected-top-level-functions list.

**No `RESCUE`-tier findings.** The story's goal, scope, and ADR alignment are correct; the contradictions are all surface-level (signatures, hash sizes, where the discriminator lives) and patchable in place.

**No Stage-3 research needed.** Every gap was answerable from S2-01's HARDENED report (the contract source of truth for the chain primitive), ADR-0007 / ADR-0005 / ADR-0011 / ADR-0014, the phase-arch-design.md `RetryLedger` and Gap 1 sections, the codebase precedents in S1-04's NewType + AST-chokepoint pattern, and S2-01's full validation report. No external pattern lookup was needed.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim, hardened):** Extend `RetryLedger` with `record_pre_execute(attempt_id, sandbox_spec_hash, started_at)` writing a BLAKE3-128-chained `{"type": "pre_execute", ...}` JSONL line before the matching `"attempt"` line, with: parametrized tamper test, property tests for chain participation, `_marker_pending` recovery, `entries()` reader that dispatches on `"type"` via a pure module-level helper, structured-attribute exceptions. The story extends S2-01 *additively*: no edit to `Attempt`, no regenerated S2-01 golden file, no rewritten chain math.
- **Non-goals (Out-of-scope, hardened):** `GateRunner.run` call-site — S5-02; `SandboxResumeBehavior` enum — Phase 6; resume policy (re-execute vs skip) — Phase 6; `codegenie sandbox inspect` CLI — S8-01; `_ROW_TYPE_REGISTRY` lift — deferred to 3rd-row-type story.

### Phase 5 exit criteria touched

- **§Goal 1 (Phase 5 exits Stage 6 with audit-chain extension).** ADR-0007's marker is what makes Phase 6 able to *detect* "execute happened, result lost" — without it, Phase 6's checkpointer has no observability into mid-attempt crashes and either always re-executes (cost) or always skips (silent verdict change).
- **§Component design — `RetryLedger` Internal structure (arch line 553+).** The widening from `{record, head, attempts}` to `{record, head, attempts, record_pre_execute, entries}` is what this story lands. `entries()` is the durable read-side that Phase 6 will use.
- **§Gap 1 (arch line 1003).** The full gap statement and improvement spec. The story IS the closure of this gap.
- **§Process view — Retry-recovers sequence.** The marker write happens *before* `client.execute`. This story ships the ledger surface; the sequence diagram's call-order is owned by S5-02 (`GateRunner.run` loop body).
- **§Edge case 11 (arch — `attempts.jsonl` manual edit).** The parametrized tamper test extends this defense to marker rows.

### Load-bearing commitments touched

- **ADR-0007 (this story's canonical ADR):** signature `(attempt_id, sandbox_spec_hash, started_at)`, BLAKE3-chained, JSONL row type `"pre_execute"`, orphan marker is *expected* state on resume.
- **ADR-0005 (Phase 4 chain-head compatibility):** the marker row is part of the chain — changing its shape triggers chain-compat regeneration. AC-CH-1..AC-CH-4 pin the row shape; future shape changes require an ADR amendment.
- **ADR-0011 (no verdict cache; sandbox_spec_hash is the seam):** `sandbox_spec_hash` is BLAKE3-128 — same format constraint applied to the marker field via the new `SandboxSpecHash` NewType.
- **ADR-0014 (`ObjectiveSignals` extra=forbid):** replay must mirror — `PreExecuteMarker` `extra=forbid`, AC-AT-6 pins the unknown-field rejection.
- **CLAUDE.md "Extension by addition":** S2-02 must land additively over S2-01. The story's `Attempt`-edit (draft step 2) violated this; AC-PM-3 added as the structural defense. `_recover_chain_state`'s widening from 2-tuple to 3-tuple is the *allowed* form of extension — purely additive at the type level.
- **CLAUDE.md "Newtype identifiers when crossing ≥ 2 module boundaries":** `SandboxSpecHash` lands per rule-of-three (3 modules — `SandboxSpec`, `SandboxRun`, `PreExecuteMarker`).
- **CLAUDE.md "Functional core / imperative shell":** caller injects `started_at`; ledger does no clock-fetch. `_canonical_json_marker` and `_parse_ledger_row` are pure module-level helpers (AC-DR-4, AC-MP-1).
- **CLAUDE.md "Fail loud":** validation BEFORE write (AC-OO-3); chain-tamper raises with structured attributes (AC-AT-3..AC-AT-5); orphan marker is *visible* via `entries()` (AC-DR-1).
- **CLAUDE.md "Data-driven registries over branching code":** today `match` (only 2 row types); registry promotion deferred per Rule 2 — surfaced as tracked seam in Notes.

### Sibling-family lineage (Design-Patterns)

- **This story is the 2nd consumer of `gates/retry_ledger.py`.** S2-01 (first; chain primitive) and S2-03 (third; chain-head startup verify) flank it. Per S2-01's prior validation, the kernel was deliberately structured for S2-02 to land additively — pure module-level helpers (`_canonical_json`, `_compute_chain_hash`, `_recover_chain_state`) are the reuse points; `_canonical_json_marker` and `_parse_ledger_row` extend without editing any of them.
- **Codebase precedent for NewType + AST chokepoint:** S1-03 (`SignalKind`), S1-04 (`AttemptNumber`, `RunId`). The S1-03 AC-4c pattern (AST-walk under `src/codegenie/gates/` forbidding `NewType("Name", ...)` redefinition) is mirrored by AC-NT-4 for `SandboxSpecHash`.
- **Codebase precedent for "discriminated union without `Annotated[Field(discriminator=...)]`":** S1-04 has tagged-union models for `GateOutcome.state: Literal["passed", "failed_retryable", "failed_terminal"]` — same hand-rolled dispatch shape. The pattern (load via `match` on a `Literal` field, no Pydantic discriminated-union magic) is established.

### Prior validation history

- None for S2-02 — this is the first pass.
- S2-01's HARDENED report extensively shapes this story (see references throughout).
- S2-03 carries a known follow-up flag from S2-01: `len != 32` check on `chain_head.bin` should be `len != 16` (BLAKE3-128 byte length). Not in scope for this story; flagged for S2-03 validator.

## Critic findings (Stage 2 — verbatim)

### Coverage critic findings

| Severity | Finding | Resolution |
|---|---|---|
| **block** | `_marker_pending` recovery on `__init__` is in Notes, not in any AC. Phase 6 contract failure. | AC-RR-5..AC-RR-7 added. |
| **harden** | `sandbox_spec_hash` format unvalidated at boundary. | AC-OO-3 + format check. |
| **harden** | Validation-before-write ordering unpinned. | AC-OO-3 pins the order. |
| **harden** | `record(attempt)` without prior marker not pinned (S2-01 callers regress risk). | AC-OO-6. |
| **harden** | structlog event in Refactor, not AC. | AC-LG-1. |
| **harden** | Coverage gate AC missing. | AC-QG-7. |
| **nit** | Module-purity test re-run AC missing. | AC-MP-1, AC-MP-2. |

### Test-Quality critic findings

| Severity | Finding | Resolution |
|---|---|---|
| **block** | Tamper test uses fragile substring assertion (`'entry_type="pre_execute"' in str(exc.value)`) — directly contradicts S2-01 AC-AT-2 hardening. | Removed; `.row_type` + `.kind` structured-attribute asserts. |
| **harden** | Tamper test parametrization too narrow (single field). | AC-AT-3 parametrizes across 5 fields. |
| **harden** | Missing chain-participation witness — marker tamper invalidates *following* attempt? | AC-AT-4 + dedicated test. |
| **harden** | Missing prefix-replay invariance property over mixed rows. | AC-PROP-M-1. |
| **harden** | Missing payload-permutation witness for markers. | AC-PROP-M-2. |
| **harden** | Missing canonical-bytes determinism for `_canonical_json_marker`. | AC-PROP-M-3. |
| **harden** | Golden file uses `freezegun` (new dep) where caller-injection is cleaner. | AC-GF-1 / AC-GF-2 — caller injects `started_at`, no `freezegun`. |

### Consistency critic findings

| Severity | Finding | Resolution |
|---|---|---|
| **block** | Implementation step 2 violates S2-01 HARDENED carryforward #18 (edits `Attempt`). | Removed; AC-PM-3 adds AST structural defense. |
| **block** | Hash sizes are 64 chars (BLAKE3-256), contradicting S1-04 HARDENED BLAKE3-128. | Every `"ab" * 32` → `"ab" * 16`; `sandbox_spec_hash` constrained to `^[0-9a-f]{32}$`. |
| **block** | `record_pre_execute` signature drops `started_at`, contradicting ADR-0007 Decision verbatim. | AC-RPE-1 pins 3-arg signature. |
| **harden** | `Depends on` missing S1-02 (sandbox contract — `SandboxSpec.sandbox_spec_hash` lives there). | Widened. |
| **harden** | `LedgerEntry` discriminated-union form unworkable without `type` on `Attempt`. | AC-DR-1 — hand-rolled dispatch. |

### Design-Patterns critic findings

| Severity | Finding | Resolution |
|---|---|---|
| **block** | `LedgerEntry = Annotated[PreExecuteMarker \| Attempt, Field(discriminator="type")]` raises `PydanticSchemaGenerationError` because `Attempt` has no `type` field. | AC-PM-2 + AC-DR-1 — plain `TypeAlias` union with hand-rolled `_parse_ledger_row` dispatch. |
| **harden** | Primitive obsession on `sandbox_spec_hash: str` (3-module boundary). | AC-NT-3 + AC-NT-4 — `SandboxSpecHash` NewType. |
| **harden** | `PreExecuteMarker` placement: `retry_ledger.py` (draft) vs `contract.py` (sibling to `Attempt`). | Moved to `contract.py`. |
| **harden** | `LedgerAttemptOutOfOrder.context` discriminator missing. | AC-OO-5 — additive `.context` attribute. |
| **harden** | `AuditChainCorrupted.row_type` discriminator missing. | AC-AT-5 — additive `.row_type` attribute. |
| **harden** | Registry seam vs rule-of-three: today `match`, future `_ROW_TYPE_REGISTRY`. | Deferred per Rule 2; surfaced in Notes as a tracked seam. |
| **harden** | `_parse_ledger_row` purity must be AC, not implicit. | AC-DR-4 — AST-walk asserts module-level. |

## Edits applied (Stage 4)

Story rewritten end-to-end. Major sections:

- **Status / Validation lines updated:** `Ready` → `HARDENED` with 2026-05-23 link to this report.
- **`Validation notes` block added** under the header (20 bullets, mirroring the S2-01 report's structure — each numbered carryforward is referenceable from future stories).
- **References section expanded** — adds ADR-0011, ADR-0014, arch line 654 (`sandbox_spec_hash` format), and a "Prior-story validation (read first)" pointer to S2-01's report.
- **Goal section rewritten** to specify BLAKE3-128, `_marker_pending` recovery, `entries()` shape, structured exceptions, and the "additive over S2-01" commitment.
- **Acceptance criteria restructured** into 14 lettered sections (A–N) with 36 individually-verifiable ACs. Compared to the draft's 9 unstructured bullets, every AC now (a) has an explicit ID, (b) is third-party-verifiable, and (c) traces to a critic finding or S2-01 carryforward.
- **Implementation outline rewritten** — 10 ordered steps; the offending "edit `Attempt` to add `type` field" step is gone; `_recover_chain_state` widening to 3-tuple is explicit.
- **TDD plan rewritten** — 8 distinct test functions covering: ordering + golden, orphan-marker, double-marker, no-marker-still-works, mismatched-attempt-after-marker, parametrized tamper (5 cases), chain-participation witness, extra-field. Property tests + resume tests called out in additional-files list.
- **Files-to-touch expanded** — `test_s2_02_no_attempt_edit.py` added; `test_retry_ledger_entries.py` added; existing S2-01 tests called out as extension targets.
- **Out-of-scope widened** to explicitly defer the `_ROW_TYPE_REGISTRY` per rule-of-three.
- **Notes for the implementer** rewritten with 4 sections: (a) S2-01 hardening carryforward (READ FIRST), (b) ADR-0007 contract verbatim, (c) `_marker_pending` recovery semantics, (d) `LedgerEntry` discriminated-union shape, (e) Registry seam vs rule-of-three, (f) Forward-compat for S2-03, (g) Subtle correctness traps.

## Verdict

**HARDENED.** Story now consumes S2-01's `RetryLedger` kernel additively, ships the marker primitive that closes ADR-0007 Gap 1, and leaves no editable surface for the executor to silently violate "Extension by addition." Every AC is individually verifiable; every critical edge case (process restart between marker and attempt, marker tamper invalidating the following attempt, orphan marker on a fresh ledger, mismatched attempt_id after marker, `record(attempt)` without prior marker) has at least one test in the TDD plan that would fail if a wrong implementation were swapped in.

### Forward flags for downstream stories

- **S2-03 (next):** This story's `entries()` reader is the API S2-03's chain-head startup verify will consume. S2-03's TDD plan must be re-validated to (a) use `entries()` (not S2-01's `attempts()`) where chain-head verification spans both row types, and (b) amend its `len != 32` check on `chain_head.bin` to `len != 16` (BLAKE3-128 byte length — S2-01 hardening carryforward #18, also flagged in this story's Notes).
- **S5-02 (`GateRunner.run`):** Will call `record_pre_execute(attempt_id, sandbox_spec_hash, started_at)` immediately before `client.execute(spec)`. The 3-arg signature is final per ADR-0007.
- **S8-01 (`codegenie sandbox inspect`):** Will read `entries()` to surface orphan markers as "execute started, result missing." The `LedgerEntry: TypeAlias = PreExecuteMarker | Attempt` is the importable surface S8-01 will consume.
- **3rd-row-type story (TBD, likely S6+ or S7+):** Will promote `_parse_ledger_row`'s `match` statement to a `_ROW_TYPE_REGISTRY: Final[dict[str, type[BaseModel]]]` per CLAUDE.md "data-driven registries over branching code." Deferred today per Rule 2 / rule-of-three.
