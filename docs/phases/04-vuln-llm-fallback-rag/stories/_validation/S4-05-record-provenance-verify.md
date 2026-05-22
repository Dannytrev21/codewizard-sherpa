# Validation report: S4-05 - `RecordProvenance.verify` + `RagRecordChainOrphan`

**Validated:** 2026-05-22 13:36 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S4-05 ships the read-side provenance predicate for Phase 4 RAG: `codegenie.rag.provenance.verify(record, spanning_log) -> bool`, the one-method `SpanningChainLog` Protocol, and a typed `RagRecordChainOrphan` event emitted by the caller when a candidate record is excluded. The goal is sound and traces to `High-level-impl.md` Step 4, final-design Component 11, ADR-0016, and phase-arch edge case #14.

The draft was not executor-ready. It used an ad hoc `rag/events.py` event class instead of the shipped `codegenie.plugins.events.EventLog` surface, added behavior to the frozen `RecordProvenance` model, copied stale `RecordProvenance` fields that S1-04 had already removed, and tested a store-query shape that does not match `SolvedExampleStore.query(...) -> RetrievalOutcome`. All blockers were fixable in place. The story is now hardened with 15 findings addressed: **4 block, 9 harden, 2 nit**.

## Context brief

- **Story promise:** verify a record's `provenance.event_chain_head` by membership in the spanning event log, keep the verifier pure, and make orphan exclusion observable through `RagRecordChainOrphan`.
- **Source constraints:** S1-04 owns the four-field `RecordProvenance` model (`workflow_id`, `event_chain_head`, `created_at`, `signing_method`); S4-04's manifest `chain_head` is the store content head, not the per-record event-log anchor; Phase-3 ADR-0005 / S6-01 already shipped `codegenie.plugins.events.EventLog`.
- **Pattern constraints:** functional core / imperative shell, dependency inversion through `SpanningChainLog`, event sourcing through the existing typed event union, and extension by addition without editing `rag/models.py`.
- **Open ambiguities:** none after reconciling the story to the real EventLog API and S1-04 model contract.

## Findings by critic

### Coverage critic

**C1 (block) - Event emission used a non-existent registry.** The draft placed `RagRecordChainOrphan` in `src/codegenie/rag/events.py` with a `kind` discriminator. That bypasses the actual event source, so AC-9 could pass a local list while production callers cannot emit the event.
**Fix:** AC-3 now registers `RagRecordChainOrphan` in `src/codegenie/plugins/events.py` as a `WorkflowInternalEvent` and AC-9 emits through `EventLog.emit_internal(...)`.

**C2 (block) - Integration smoke used the wrong store contract.** The draft caller looped over `await store.query(...) -> records`, but S4-03/S5-01 model the store/retriever path as `RetrievalOutcome`, not a raw record list.
**Fix:** AC-9 uses an explicit candidate sequence in a retriever-like caller shim. S5-01 remains responsible for composing the real retriever.

**C3 (harden) - Empty-head behavior needed a reachable setup.** A direct assignment to a frozen Pydantic model would raise before exercising `verify`.
**Fix:** AC-7 uses `model_copy(update=...)` or a direct `ChainHead("")` cast to build the forged in-memory case.

**C4 (harden) - Orphan-event fields were ambiguous.** `record_chain_head` could be mistaken for S4-04's manifest/content chain head.
**Fix:** AC-3 renames it to `record_event_chain_head`, explicitly sourced from `record.provenance.event_chain_head`.

### Test-Quality critic

**T1 (harden) - Alias-equivalence property was tautological.** Checking module function and staticmethod return the same value does not catch always-true, always-false, inverted-membership, or wrong-field mutants.
**Fix:** AC-8 now checks `verify(record, log) == (record.provenance.event_chain_head in known_heads)` with Hypothesis.

**T2 (harden) - Purity test overclaimed and underchecked.** A mock call assertion alone cannot catch accidental `EventLog`, filesystem, network, or logging calls inside the verifier.
**Fix:** AC-6 combines mock call-count assertions with an AST/source side-effect denylist.

**T3 (harden) - Event registration drift was unpinned.** A typo in `event_type`, missing union row, or missing `_INTERNAL_CLASSES` entry would not fail the original tests.
**Fix:** AC-11 asserts the `WorkflowInternalEvent` discriminator mapping contains `"rag_record_chain_orphan"` and that `EventLog.emit_internal(...)` / `replay()` round-trips the typed event.

**T4 (harden) - Stale provenance fields could survive.** A wrong implementation could read `record.provenance.record_chain_head` or `model_id` and still pass happy-path tests if fixtures carried those stale fields.
**Fix:** AC-12 adds an AST/source regression check forbidding stale S1-04-removed field names in `provenance.py`.

### Consistency critic

**K1 (block) - Wrong event-log API.** Prior Phase-4 validations already established that `codegenie.audit.EventLog`, ad hoc `.events` lists, and `rag/events.py` are stale. The real surface is `codegenie.plugins.events.EventLog`, `WorkflowInternalEvent`, `_INTERNAL_CLASSES`, `emit_internal`, and `replay()`.
**Fix:** references, ACs, files-to-touch, and tests now use `src/codegenie/plugins/events.py`.

**K2 (block) - The story edited `RecordProvenance` to add behavior.** A `RecordProvenance.verify` staticmethod alias mixed model data with policy, introduced circular-import pressure, and contradicted S1-04's frozen-data framing.
**Fix:** AC-1 and Notes section make `verify` module-level only; `src/codegenie/rag/models.py` was removed from files-to-touch.

**K3 (block) - `RecordProvenance` field shape drifted from S1-04.** The draft used stale fields such as `record_chain_head`, `model_id`, `embedding_dim`, `trust_outcome_passed`, and `confidence`.
**Fix:** implementation notes lock the four-field S1-04 contract and AC-12 forbids stale field references in the verifier.

**K4 (harden) - Missing dependencies on S1-01 and S1-04.** The story depended on `ChainHead`, `SolvedExampleId`, `EventId`, `WorkflowId`, `SolvedExample`, and `RecordProvenance` without declaring those prerequisites.
**Fix:** the header now lists S1-01, S1-04, and S4-04.

### Design-Patterns critic

**D1 (harden) - Keep the Protocol narrow.** Adding `current_head`, `iter_events`, or chain-segment methods would couple the verifier to the event-log adapter and violate final-design Component 11's membership-only decision.
**Fix:** `SpanningChainLog` remains a one-method dependency-inverted port; `spanning_log_head` is caller-supplied event triage context.

**D2 (harden) - Event should be workflow-internal, not spanning.** A retrieval query's exclusion decision is local to one workflow and should not carry `prev_hash`; the global spanning chain is the evidence source being consulted.
**Fix:** AC-3 makes `RagRecordChainOrphan` a `WorkflowInternalEvent` and tests it through `emit_internal`.

**D3 (harden) - Functional core / imperative shell.** The verifier should not emit events, log, open files, or know about `EventLog`.
**Fix:** AC-1/AC-6 pin `verify` as a pure predicate; AC-9 keeps emission in the caller shim.

**D4 (nit) - No batch verifier.** `verify_all(records, log)` is tempting but unnecessary for the S5-01 `top_k=5` path and would blur per-record event context.
**Fix:** Notes explicitly say not to add batch verification in this story.

**D5 (nit) - Distinguish content heads from event-log heads.** The word "chain head" appears in both S4-04's manifest and S4-05's provenance anchor.
**Fix:** context, AC-3, and Notes use `record_event_chain_head` for the absent provenance anchor and reserve manifest/content heads for S4-04.

## Research briefs

None. No finding required external research. The fixes came from the current repo (`src/codegenie/plugins/events.py`, `tests/unit/plugins/test_events.py`), sibling validation reports (S2-01/S2-02/S2-05), S1-04's hardened model contract, ADR-0016, final-design Component 11, and phase-arch edge case #14.

## Conflict resolutions

- **Arch shorthand vs model purity:** the arch prose says `RecordProvenance.verify(record, spanning_log)`, but S1-04 makes `RecordProvenance` frozen data. The story preserves the prose intent with a module-level `verify` function and removes the staticmethod alias.
- **`spanning_log_head` on event vs Protocol minimalism:** the event may carry the caller's current head for triage, but the verifier Protocol still exposes only `contains_chain_head`. No accessor is added.
- **Event observability vs spanning stream semantics:** `RagRecordChainOrphan` is observable through the event log, but it is workflow-internal. It describes a retrieval decision; it is not itself a chain-advancing spanning event.
- **Pattern desire for a richer proof vs final-design decision:** record-id-bound proofs and chain-segment proofs are explicitly out of scope. S4-05 implements membership in the spanning log only.

## Edits applied

1. Header updated to `HARDENED`; dependencies expanded to S1-01, S1-04, and S4-04.
2. Validation notes block added with the 15 finding summary and this report path.
3. References updated to the real event source: `src/codegenie/plugins/events.py` and sibling validator precedents.
4. Goal narrowed to module-level `verify`, one-method Protocol, pure predicate, and caller-owned event emission.
5. AC-1 removes `RecordProvenance.verify(...)` staticmethod and forbids editing `rag/models.py`.
6. AC-3 moves `RagRecordChainOrphan` into `WorkflowInternalEvent`, uses `event_type`, `event_id`, `workflow_id`, `timestamp`, `record_id`, `record_event_chain_head`, and `spanning_log_head`, and requires union / `_INTERNAL_CLASSES` / `__all__` wiring.
7. AC-6 adds AST/source side-effect checks for `verify`.
8. AC-7 fixes empty-head setup using `model_copy(update=...)`.
9. AC-8 replaces alias equivalence with the membership property.
10. AC-9 rewrites the integration smoke around a caller shim and real `EventLog.emit_internal(...)`.
11. AC-11 adds event registration and replay drift tests.
12. AC-12 adds the S1-04 stale-field lock.
13. Implementation outline, TDD plan, Files to touch, Out of scope, and Notes were rewritten to match the real event API and model shape.

## Verdict rationale

**HARDENED.** The story's intent is correct and the final shape is small: one pure predicate, one narrow Protocol, and one typed internal event. The blockers were stale codebase assumptions and model-shape drift, not a broken goal. After hardening, the story is executor-ready and preserves the design patterns the phase depends on: dependency inversion, functional core / imperative shell, typed event sourcing, and extension by addition through the existing event union.

## Recommended next step

`phase-story-executor` can implement S4-05. The executor should start with `src/codegenie/plugins/events.py` and `tests/unit/plugins/test_events.py` to mirror the existing event registration pattern, then implement `src/codegenie/rag/provenance.py` as the pure three-branch predicate.
