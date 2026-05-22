# Validation report: S4-05 - `RecordProvenance.verify(record, spanning_log) -> bool` + `RagRecordChainOrphan`

**Validated:** 2026-05-22 13:35 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S4-05 ships the RAG provenance predicate: a pure `verify(record, spanning_log) -> bool` function over `SolvedExample.provenance.event_chain_head`, a one-method `SpanningChainLog` Protocol, and the typed `RagRecordChainOrphan` event emitted by the future retriever caller. The goal is sound and traces to final-design Component 11, phase-arch edge case #14, and ADR-0016. The draft was not executor-ready because it copied stale assumptions about the event log, S1-04's model fields, and `SolvedExampleStore.query(...)`. All four blockers were fixable in place, so the verdict is HARDENED.

The validation applied the four critic lenses inline after reading the story, phase context, ADR-0016, S1-01/S1-04/S4-01..S4-04 hardened lineage, `src/codegenie/plugins/events.py`, and the repeated Phase-4 event-log validation reports. Parallel critic subagents were not spawned; the concrete defects were all grounded in already-loaded source and prior reports, matching the in-process precedent used by earlier validator reports when the context surface is small.

## Findings by critic

### Coverage critic

**COV1 (block) - AC-9 used the wrong store shape.** The draft integration test said a fake retriever-like caller should `await store.query(...) -> records`. The actual store/retriever contracts do not expose raw records from `SolvedExampleStore.query(...)`; S4-03/S1-04 use `RetrievalOutcome`. A test written that way would force the executor to invent a fake API. Fix: AC-9 now uses an explicit `Sequence[SolvedExample]` caller shim, leaving real retriever composition to S5-01.

**COV2 (harden) - event registration was not observable.** The event class existed only as an unregistered `rag/events.py` model, so nothing proved `EventLog.emit_internal(...)` could accept it. Fix: AC-11 requires discriminator mapping and replay tests in `tests/unit/plugins/test_events.py`.

**COV3 (harden) - empty-head defense mutated a frozen model.** The draft test assigned `record.provenance.event_chain_head = ChainHead("")`, which contradicts S1-04's frozen Pydantic models. Fix: AC-7 uses `model_copy(update=...)` to construct the forged in-memory case without mutating the model.

**COV4 (nit) - current spanning head source was implicit.** The event payload included `spanning_log_head` but the one-method Protocol did not expose a current head. That is correct, but the story did not say how the field is supplied. Fix: AC-2 and AC-9 state it is caller-supplied triage context, not verifier dependency.

### Test-Quality critic

**TQ1 (harden) - alias-equivalence property tested the wrong thing.** The draft AC-8 compared a module function to a staticmethod alias. If both delegated to the same wrong implementation, the property passed. Fix: AC-8 now tests the actual invariant, `verify(record, log) == (head in known_heads)`, with Hypothesis.

**TQ2 (harden) - purity needed a structural guard.** A mock call-count test catches extra `spanning_log` calls but not filesystem, env, or EventLog access. Fix: AC-6 adds an AST side-effect check over `verify`.

**TQ3 (harden) - event emission used an ad hoc sink.** The draft "captured event sink" could pass while the real event source rejected the class. Fix: AC-9 emits through a real `EventLog` and replays.

**TQ4 (harden) - field-name drift needed a regression guard.** The implementation outline referenced stale `RecordProvenance` draft fields; tests could still pass if the verifier accidentally read the wrong field after S1-04. Fix: AC-12 adds a source/AST guard forbidding stale field names in `provenance.py`.

### Consistency critic

**CON1 (block) - event API contradicted the shipped EventLog surface.** Current code uses `codegenie.plugins.events.EventLog`, `WorkflowInternalEvent`, `event_type` discriminators, and `_INTERNAL_CLASSES`. The draft specified `src/codegenie/rag/events.py` with `kind`, which `emit_internal` would reject. Fix: AC-3 moves `RagRecordChainOrphan` into `plugins/events.py` and wires it like the existing variants.

**CON2 (block) - `RecordProvenance` field shape contradicted S1-04.** The draft outline listed `solved_example_id`, `trust_outcome_passed`, `confidence`, `model_id`, `embedding_dim`, `harvested_at`, and `record_chain_head` on `RecordProvenance`. S1-04 hardened the model to exactly `workflow_id`, `event_chain_head`, `created_at`, and `signing_method`. Fix: the story now consumes only `event_chain_head` and adds Notes §7.

**CON3 (harden) - "never raises" overclaimed.** Edge case #14 says chain-orphans continue; it does not say the verifier should swallow event-log corruption or arbitrary adapter exceptions. Fix: the goal/ACs now say the predicate returns `False` for empty/absent heads and performs no side effects; broken spanning-log integrity remains Phase 3 event-log verifier territory.

**CON4 (nit) - direct dependencies were under-declared.** The story depended only on S4-04, but imports S1-01 newtypes and S1-04 models. Fix: header now declares S1-01, S1-04, and S4-04.

### Design-Patterns critic

**DP1 (block) - staticmethod alias violated the data/policy split.** The draft simultaneously said "not a method on the Pydantic model" and then required `RecordProvenance.verify(...)` as a staticmethod alias. That mixes verification policy into the frozen data model and creates a circular-import workaround. Fix: no `models.py` edit; `codegenie.rag.provenance.verify` is the only implementation surface.

**DP2 (harden) - parallel event registry would erode event sourcing.** `rag/events.py` would become a second source of event truth outside `WorkflowInternalEvent`. Fix: the story uses the existing event-sourcing registry and explicitly forbids a parallel module for this story.

**DP3 (harden) - Protocol surface needed Open/Closed discipline.** It was tempting to add `current_head`, `get_chain_segment`, or record-id lookup to support richer proof or event payloads. Final-design chose head-membership only. Fix: AC-2 pins the one-method Protocol and places richer proof in out-of-scope / future ADR territory.

## Research briefs

None. No finding required external research. The decisive references were in-repo: `src/codegenie/plugins/events.py`, S1-04's hardened model story/report, S1-01's newtype story/report, ADR-0016, final-design Component 11, and prior Phase-4 validation reports correcting the same stale event-log assumption.

## Conflict resolutions

- **Design-Patterns vs arch shorthand.** The arch prose says `RecordProvenance.verify(record, spanning_log)`. S1-04's hardened model shape and the story's own "model pure data" statement won over the shorthand. Resolution: module-level `codegenie.rag.provenance.verify` implements the contract; the docstring carries the arch wording.
- **Future S5-03 draft vs final-design.** Unvalidated future S5-03 currently asks for `(record_id, chain_head)` collision detection. Final-design Component 11 and S4-05's governing goal specify simple head-presence verification. Resolution: S4-05 stays head-membership only; any stronger pair-bound proof needs a later ADR/final-design amendment.
- **Event payload triage vs Protocol minimalism.** `spanning_log_head` is useful in the event payload, but adding `current_head()` to `SpanningChainLog` would expand the verifier port for a caller concern. Resolution: caller supplies `spanning_log_head`; Protocol remains one method.

## Edits applied

1. Header `Status: Ready -> HARDENED`; dependencies expanded to S1-01, S1-04, S4-04; validation notes inserted.
2. Context and goal rewritten to distinguish chain-orphan continuation from broken event-log integrity, and to state head-membership rather than chain-segment or pair-bound proof.
3. AC-1 rewritten: module-level `verify`; no staticmethod alias; no `models.py` edit.
4. AC-2 tightened to one-method `SpanningChainLog`; caller-owned current head clarified.
5. AC-3 rewritten: `RagRecordChainOrphan` is a `WorkflowInternalEvent` in `src/codegenie/plugins/events.py` with `event_type`, `event_id`, `workflow_id`, `timestamp`, `record_id`, `record_event_chain_head`, and `spanning_log_head`.
6. AC-4/AC-5 updated to use valid 64-hex `ChainHead` examples and exact call-count assertions.
7. AC-6 hardened with mock and AST purity checks.
8. AC-7 corrected to use `model_copy(update=...)` for the forged empty-head case.
9. AC-8 replaced alias-equivalence with the membership property test.
10. AC-9 rewritten to use a caller shim and real `EventLog.emit_internal(...)` / replay.
11. AC-11 and AC-12 added for event registration drift and S1-04 field-shape drift.
12. Implementation outline simplified: create `provenance.py`, register event in `plugins/events.py`, update tests/fixture. Removed the staticmethod alias and stale `RecordProvenance` model snippet.
13. Files-to-touch reconciled: removed `src/codegenie/rag/models.py` and `src/codegenie/rag/events.py`; added `src/codegenie/plugins/events.py` and `tests/unit/plugins/test_events.py`.
14. Notes for implementer rewritten around module-level verify, event-log API, Protocol scope, and S1-04 field names.

## Verdict rationale

HARDENED. The story's goal is valid and directly supports Step 4 plus edge case #14; no RESCUE condition was present. The blockers were concrete contract mismatches: wrong event API, stale model fields, circular staticmethod alias, and an impossible integration-test shape. Each was local and fixable without changing the underlying goal. The story is now ready for `phase-story-executor`, with the caveat that later S5-01/S5-03 stories should be reconciled against this head-membership contract during their own validation passes.

## Recommended next step

Run `phase-story-executor` on S4-05 when its declared prerequisites are implemented. During future validation of S5-01/S5-03, reconcile any `RagMiss(reason=...)` or pair-bound chain-proof language against S1-04's bare `RagMiss` and S4-05's head-membership contract.
