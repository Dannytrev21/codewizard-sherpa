# Validation report: S2-02 — FenceWrapper pure core + audit shell

**Validated:** 2026-05-21 16:05 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S2-02's goal is sound and traces cleanly to ADR-0013: ship `fence_pure` (a stdlib-only pure core) plus `FenceWrapper.fence` (the imperative shell), the per-source truncation-cap dict, and a Hypothesis property that the per-invocation nonce can never escape the fence. The core design — module path, the byte-exact cap table, the scan-untruncated-then-truncate ordering, the functional-core/imperative-shell split — is fully consistent with the ADR and the phase arch.

The draft was not executor-ready for two reasons. First, like its already-hardened sibling S2-01, it named a non-existent event surface: it pointed `EventLog` registration at `src/codegenie/audit.py` (the Phase-0 *gather* audit writer — no `EventLog`), referenced a non-existent "event-kind allowlist" and a non-existent `tests/fence/test_event_kinds_complete.py`. Second, the three behaviours the story itself names as load-bearing — the scan-untruncated-**first** ordering, the close-delimiter-in-body backstop, and byte-exact truncation — had **no acceptance criteria and no TDD-plan tests**; they lived only in "Notes for the implementer", and the laziest correct-looking `fence_pure` passed all 13 original ACs while defeating ADR-0013's purpose or crashing on multi-byte input.

All four blockers have clear in-place fixes — none requires rewriting the goal. The story is HARDENED: the event surface is reconciled to `codegenie.plugins.events.EventLog` / `emit_internal` / `WorkflowInternalEvent` exactly as S2-01 was; five new ACs (AC-14..AC-18) promote the unpinned load-bearing behaviours; and AC-4/AC-5/AC-7 are hardened to carry the scanner verdict as a sum type instead of an "implementer chooses" `_pattern_id: str | None` escape-hatch.

## Context brief

- **Story snapshot:** `fence_pure(payload, nonce, source_kind, scanner) -> FencedSegment` (pure core) + `FenceWrapper.fence` (imperative shell — mints nonce, emits events, delegates). `_TRUNCATION_CAPS: Final[dict[SourceKind, int]]`. Hypothesis nonce-no-escape property. Step 2 of Phase 4.
- **ADRs:** ADR-0013 (scan-untruncated-first; per-source caps; functional-core/imperative-shell), ADR-0003 (path-scoped fence — `src/codegenie/fallback/fence/`), production ADR-0033 (newtype/smart-constructor/sum-type discipline).
- **Codebase reality (verified 2026-05-21):** `src/codegenie/audit.py` has no `EventLog`. The real event log is `codegenie.plugins.events.EventLog` (`emit_internal`/`emit_spanning`); events are Pydantic variants in a `WorkflowInternalEvent`/`WorkflowSpanningEvent` discriminated union plus parallel `_INTERNAL_CLASSES`/`_SPANNING_CLASSES` tuples. `HexNonce` (`NewType(str)`, `^[0-9a-f]{32}$`) + `parse_hex_nonce` shipped by S1-01 (HARDENED); S1-01 does **not** ship `FencedSegment`/`SourceKind`/`CanaryResult`. `tests/fence/test_pyproject_fence_phase4.py` is the correct name (S1-05, HARDENED) — does not exist yet only because S1-05 is unexecuted. `src/codegenie/fallback/` does not exist yet.
- **Sibling lineage:** S2-01 (`ProvenanceGate`, HARDENED) was hardened against the *identical* event-log mistake (its blockers C1/C2). S2-02 had not been reconciled.
- **Open ambiguities at Stage 1:** none requiring user input.

## Findings by critic

### Coverage critic

- **F1 (block)** — The scan-untruncated-first ordering — the story's load-bearing goal — has no AC. AC-6 prose lists the steps but only the outcomes are asserted; a scan-after-truncate impl passes every AC. The `_RecordingScanner` test lived only in Notes.
- **F2 (block)** — Close-delimiter-collision-in-body has no AC. The Notes discuss it heavily; AC-8 only asserts the property *holds* and cannot reach the case randomly.
- **F3 (block)** — Multi-byte UTF-8 truncation at the cap boundary unspecified; a `payload[:cap]` char-slice passes the (all-ASCII) AC-9.
- **F4 (harden)** — `original_byte_length` semantics under redaction undefined (original input length vs 30-byte redaction string).
- **F5 (harden)** — AC-7's `pattern_id` flow from `fence_pure` to the shell left "implementer chooses" — unverifiable.
- **F6 (harden)** — Empty-payload behaviour unspecified.
- **F7 (harden)** — AC-9 tests `cap+1000` and `cap-1` but not exactly `cap`; `>` vs `>=` unconstrained.
- **F8 (nit)** — `truncated`/`canary_fired` interaction on a collision not pinned.
- **F9 (nit)** — Out-of-scope omits `scan_pure`.

### Test-Quality critic

- **F1 (block)** — AC-8's `st.text()` strategy cannot reach the close-delimiter case (2⁻¹²⁸ per example); the property passes for an implementation that does no in-body delimiter check at all.
- **F2 (block)** — AC-9 cannot fail a char-vs-byte truncation mistake (no multi-byte payload, no exact-boundary case).
- **F3 (block)** — The scan-untruncated-first ordering has no AC and no TDD-plan test; reordering the steps passes all 13 ACs.
- **F4 (harden)** — AC-10's redaction test cannot exercise redact-then-truncate (30-byte redaction string < 1 KB min cap); the "sanity-checks the post-truncation length" claim is vacuous.
- **F5 (harden)** — AC-11 pure/shell parity unparametrized — blind to the collision and truncation branches.
- **F6 (harden)** — AC-6 AST-walk forbidden-call list incomplete (misses `pathlib`/`datetime`/`sys.stdout`/`logging`); uses the stale `.emit(` name; mechanism unspecified.
- **F7 (nit)** — AC-3's value-equality test is hard-coded-matching-hard-coded; reframe as a snapshot.
- **F8 (harden)** — No test pins the `FenceApplied` event payload (the event emitted on every call).
- **F9 (nit)** — The production default `nonce_source` factory has no positive test.
- **F10 (nit)** — `CanaryResult` has no discriminated-union decode test.

### Consistency critic

- **F1 (block)** — References, Files-to-touch, AC-6, AC-7 name a non-existent `EventLog` in `src/codegenie/audit.py`. The real log is `codegenie.plugins.events.EventLog`. Exact mistake S2-01 was hardened against (C2).
- **F2 (block)** — AC-12 says "event-kind allowlist" and references a non-existent `tests/fence/test_event_kinds_complete.py`. The mechanism is the `WorkflowInternalEvent` union + `_INTERNAL_CLASSES` tuple.
- **F3 (harden)** — `WorkflowInternalEvent` vs `WorkflowSpanningEvent` choice for the fence events is correct (internal — within a workflow run) but the story never states it; a wrong guess ships a `prev_hash`-bearing class that won't validate.
- **F4 (harden)** — Depends-on line claims S1-01 supplies `FencedSegment` "model home" and `SourceKind` — it does not; S2-02 is the first definer.
- **F5 (harden)** — AC-7's default nonce factory `HexNonce(secrets.token_hex(16))` is a raw cast, but AC-7 step 1 calls the result "smart-constructed, asserts length and hex shape" — internally contradictory.
- **F6 (nit, confirmation)** — AC-1's `tests/fence/test_pyproject_fence_phase4.py` reference is **correct** (S1-05 AC-7); do not flag.
- **F7 (nit, confirmation)** — Module path, cap table, scan-before-truncate ordering all trace cleanly to ADR-0013/ADR-0003/arch; no conflict in the core design.

### Design-Patterns critic

- **F1 (harden)** — Audit events pointed at the wrong module; `FenceApplied`/`CanaryCollision` should be event-sourced `WorkflowInternalEvent` variants in `plugins/events.py` (cross-links Consistency F1; sibling S2-01 D2).
- **F2 (harden)** — AC-7's `_pattern_id: str | None` escape-hatch bakes in an anaemic/illegal-state model and silently breaks the AC-11 `model_dump()` parity check (a leading-underscore field is not a Pydantic field). `FencedSegment` should carry `canary: CanaryResult`; `canary_fired` becomes a derived property.
- **F3 (harden)** — `CanaryResult` discriminator under-specified vs the codebase's `Annotated[A | B, Field(discriminator="kind")]` sum-type convention; variant `kind` literal values unnamed.
- **F4 (harden, medium confidence)** — `pattern_id` is a raw `str` crossing ≥4 module boundaries — newtype (`CanaryPatternId`) opportunity.
- **F5 (nit)** — `SourceKind`/`_TRUNCATION_CAPS` seam is sound; add a Note steering away from a `match`/`assert_never` ladder.
- **F6 (nit, confirmation)** — The `Scanner` Protocol port and the injected `nonce_source` factory are correctly scoped — not over-engineering; keep them.
- **F7 (nit)** — AST-walk forbidden-call list should use the real `emit_internal`/`emit_spanning` names (cross-links Test-Quality F6).

## Research briefs

None. Every finding was resolved by reading in-repo source, ADRs, and the sibling S2-01 validation report. No `NEEDS RESEARCH` findings — Stage 3 skipped.

## Conflict resolutions

- **Coverage F5 vs Design-Patterns F2 (the `pattern_id` plumbing).** Both flag AC-7's "implementer chooses" ambiguity. Design-Patterns supplies the cleaner fix (sum type on `FencedSegment`, illegal states unrepresentable) and Coverage supplies the verifiability requirement. Merged: AC-4 now carries `canary: CanaryResult`; AC-7 step 3 `match`es on it. Design-Patterns priority is lowest, but here it does not *add* an AC — it picks the shape for an AC Coverage already required — so no priority conflict.
- **Design-Patterns F4 (`CanaryPatternId` newtype) vs Rule 2.** Per the synthesis priority chain, Rule 2 (Simplicity First) wins over Design-Patterns when a finding asks for scaffolding ahead of the threshold. Promoting `pattern_id` to a newtype *here* would load the full `identifiers.py` `__all__` / `_NEWTYPE_REGISTRY` / `test_identifiers_phase3.py` cross-file fence reconciliation (the S1-01 pattern) onto S2-02 for a single field whose minting site (the injection-pattern catalog) is S2-03's. Demoted from `harden` to a `Notes for the implementer` paragraph addressed to S2-03's executor. No new AC.
- **Test-Quality F4 (redact-then-truncate).** Option (b) chosen: the redaction string (30 bytes) is below the smallest cap (1 KB), so redact-and-return vs redact-then-truncate are byte-identical — the ordering is genuinely unobservable. AC-10 reworded to state this and drop the vacuous "post-truncation length" sanity check, rather than inventing a tiny-cap injection seam the production code does not need.

## Edits applied

### Edit 1 — Header: Status + Validation notes
- `Status: Ready` → `Status: HARDENED`; added the `Validation notes` block.

### Edit 2 — Depends-on line corrected (Consistency F4)
- Removed the false "S1-01 supplies `FencedSegment` model home / `SourceKind` literal alias" claim; states S1-01 ships newtypes only and S2-02 is the first definer of `FencedSegment`/`SourceKind`/`CanaryResult`; added S1-05 as a dependency (lands the fence test + admits the path).

### Edit 3 — References §"Existing code" (Consistency F1, Design-Patterns F1)
- Added `src/codegenie/plugins/events.py` as **the** event log with its full shape; demoted `src/codegenie/audit.py` to a "has no `EventLog` — do not route here" warning; added `tests/unit/plugins/test_events.py` as the adjacent test idiom; added the `parse_hex_nonce` pointer.

### Edit 4 — AC-3 reframed (Test-Quality F7)
- The keys-vs-`get_args` check kept as the load-bearing intent test; the seven byte-value assertions reframed honestly as a regression snapshot.

### Edit 5 — AC-4 hardened (Coverage F4, Test-Quality F5, Design-Patterns F2)
- `canary_fired: bool` → `canary: CanaryResult` (sum type) with `canary_fired` a derived `@property`; the `_pattern_id: str | None` escape-hatch explicitly forbidden; `original_byte_length` pinned to the original-input UTF-8 byte length (pre-redaction, pre-truncation).

### Edit 6 — AC-5 hardened (Design-Patterns F3, Test-Quality F10)
- Pinned `CanaryResult` as `Annotated[CanaryClean | CanaryCollision, Field(discriminator="kind")]`; named the `kind` literal values; added a `TypeAdapter` decode test mirroring `test_spanning_union_is_discriminated`.

### Edit 7 — AC-6 hardened (Test-Quality F6, Design-Patterns F7)
- Step 2 now sets `canary: CanaryResult` and folds in the in-body delimiter backstop on the **untruncated** payload; step 3 pins UTF-8-byte/codepoint-safe truncation; the AST-walk switched to `ast.Call` resolution + an allowlist, with the denylist corrected to the real `emit_internal`/`emit_spanning`/`EventLog(` names and expanded (`pathlib`, `datetime`, `sys.stdout`, `logging`, …).

### Edit 8 — AC-7 hardened (Consistency F1/F5, Coverage F5, Design-Patterns F2)
- `event_log` retyped to `codegenie.plugins.events.EventLog`; the "implementer chooses" `_pattern_id` ambiguity replaced with `match result.canary`; the nonce-factory raw cast reconciled with the dropped "smart-constructed" claim; events emitted via `emit_internal`.

### Edit 9 — AC-8 hardened (Test-Quality F1, Coverage F2)
- The Hypothesis strategy now *constructs* the close/open delimiter for the exact nonce and embeds it in the payload, so the property can actually reach the escape case; the TDD-plan Red code block updated to match.

### Edit 10 — AC-9 hardened (Coverage F7, Test-Quality F2)
- Added the exact-at-cap boundary case; the cap comparison pinned as `>` (not `>=`).

### Edit 11 — AC-10 hardened (Coverage F4/F8, Test-Quality F4)
- Pinned `original_byte_length` (original input length), `truncated is False`, and `canary` on a collision; removed the vacuous "post-truncation length" sanity check; collision event asserted via `EventLog.replay()`.

### Edit 12 — AC-11 hardened (Test-Quality F5)
- Parity test parametrized over the clean/truncated/collision branches.

### Edit 13 — AC-12 rewritten (Consistency F1/F2/F3, Design-Patterns F1)
- Replaced the non-existent "event-kind allowlist" + `tests/fence/test_event_kinds_complete.py` with the real mechanism: `WorkflowInternalEvent` Pydantic variants wired into the union + `_INTERNAL_CLASSES` tuple + `__all__`, tested in `tests/unit/plugins/test_events.py`; stated the internal-vs-spanning choice.

### Edit 14 — AC-14..AC-18 added (Coverage F1/F3/F6, Test-Quality F3/F8)
- AC-14: `_RecordingScanner` proves the scan ran on the untruncated payload. AC-15: deterministic close/open-delimiter-in-body redaction. AC-16: byte-exact codepoint-safe truncation with a multi-byte payload. AC-17: empty-payload contract. AC-18: `FenceApplied` event-payload assertions.

### Edit 15 — Implementation outline step 6 (Consistency F1/F2)
- "Register events in the audit allowlist" → add `WorkflowInternalEvent` classes to `plugins/events.py`.

### Edit 16 — Files-to-touch (Consistency F1/F2)
- `src/codegenie/audit.py` → `src/codegenie/plugins/events.py` (MODIFY); `tests/fence/test_event_kinds_complete.py` → `tests/unit/plugins/test_events.py` (MODIFY); AC mappings updated for the new ACs.

### Edit 17 — TDD plan Green section
- Reworded so the in-body delimiter check runs on the **untruncated** payload (consistent with AC-6 step 2), redaction-on-collision named as the chosen behaviour.

### Edit 18 — Out of scope (Coverage F9)
- Added `scan_pure` (S2-03-owned).

### Edit 19 — Notes for the implementer
- Updated the scan-untruncated reminder to point at AC-14; added the event-log module note; added the `pattern_id` → `CanaryPatternId` note for S2-03; rewrote the close-delimiter note; replaced the `assert_never` note with a "do NOT write a `match` ladder over `SourceKind`" note; added a `canary: CanaryResult`-not-`bool` note.

## Verdict rationale

HARDENED. The story's goal is valid and traces cleanly to ADR-0013, ADR-0003, and the phase arch (Consistency F7 confirms the core design has no conflict). The four blockers were stale-codebase assumptions (the event surface) and unpinned load-bearing behaviour (scan ordering, close-delimiter backstop, UTF-8 truncation) — not a wrong goal. Each had a surgical in-place fix: re-point the event references exactly as S2-01 was, and promote the three Notes-only behaviours to numbered ACs. After hardening, every AC is individually verifiable, the laziest wrong `fence_pure` (scan-after-truncate, char-slice truncation, no in-body delimiter check) fails at least one AC, and the implementation shape carries the scanner verdict as a sum type that makes illegal states unrepresentable. The `>3 blocks → likely RESCUE` heuristic does not apply: RESCUE is reserved for blockers whose fixes require rewriting the *goal*, which these do not.

## Recommended next step

`phase-story-executor` can implement S2-02. The executor should: (1) start by reading `_validation/S2-01-provenance-gate-tier-zero.md` and `src/codegenie/plugins/events.py` to absorb the event-sourcing convention; (2) verify S1-01, S1-02, and S1-05 have landed (`HexNonce`/`parse_hex_nonce`, the substrate newtypes, and `tests/fence/test_pyproject_fence_phase4.py`) before starting; (3) write AC-6's AST-walk test and AC-14's `_RecordingScanner` ordering test first — they are the load-bearing structural guards; (4) run the full `make check` gate, since adding event classes to `plugins/events.py` is cross-file-coupled to `tests/unit/plugins/test_events.py`.
