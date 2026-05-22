# Validation report: S5-03 — Embedding-model-mismatch exclusion filter + combined exclusion order

**Validated:** 2026-05-22 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S5-03 ships `EmbeddingModelMismatchFilter` — the concrete production case of S5-01's `model_digest_filter` hook — and pins the order in which chain-orphan and model-mismatch exclusion compose inside the retriever. The core goal (exclude records embedded under a stale model digest; emit one audit event per query) is sound and traces to phase-arch edge case #19, Gap 1, High-level-impl Step 5, ADR-04-0007, ADR-04-0016, and production ADR-0033.

The draft, however, was written against pre-hardening sibling contracts. Since it was written, S1-04, S4-05, S5-01, and S5-02 were all hardened, and the draft contradicted every one of them. **Seven block-level findings.** All are fixable in place — the story's primary goal survives intact — so the verdict is **HARDENED**, with one explicit pre-execution reconciliation (S5-01 AC-17).

18 findings — 7 block, 8 harden, 3 nit.

## Context brief

- **Story promise:** a frozen, callable filter that partitions `Sequence[ScoredSolvedExample]` on `record.embedding_model == embedder.model_digest()`, emits one `RagRecordModelMismatch` per query, and plugs byte-identically into S5-01's hook; plus the chain-orphan-before-model-mismatch dispatch-order pins.
- **Phase constraints:** RAG events are `WorkflowInternalEvent`s in `plugins/events.py`; `RagMiss` is bare; `verify` is a head-only module-level function; the embedder digest is pinned for its lifetime.
- **Sibling lineage:** this is the *first* record filter — below the rule-of-three threshold, so no `RecordFilter` Protocol/registry is warranted (Rule 2). S5-01 (HARDENED) froze the hook signature; S5-02 (HARDENED) established the "realign to S5-01's frozen DTO" pattern this report repeats.
- **Open ambiguities after edit:** none for this story. The one remaining cross-story item — S5-01 AC-17's double-emission — is a named pre-execution reconciliation, not an ambiguity.

## Findings by critic

### Coverage critic

**C1 (harden) — Retriever-integration ACs had no precondition handling.** AC-5/AC-6 (and the combined-order ACs) exercise `SolvedExampleRetriever`, which is HARDENED, not GREEN. The draft did not say what happens if the executor reaches S5-03 before S5-01 is GREEN.
*Fix:* AC-5/AC-6/AC-8/AC-9 carry an `xfail(strict=True, reason="depends on S5-01 GREEN")` deferral with an attempt-log note — mirroring the precedent set by S5-02 AC-14.

**C2 (harden) — Hypothesis property covered only `k > 0`.** The draft's once-per-query property asserted "for any non-empty list where k > 0 …", leaving the "emits when nothing is excluded" mutant alive.
*Fix:* AC-12 now spans any input (including empty) and asserts `1 if k > 0 else 0` events; the `k = 0` arm kills the unconditional-emit mutant, `event.count == k` kills the count-from-wrong-list mutant.

**C3 (nit) — Empty-input behavior was only implied.** `excluded_count == 0` covers it logically; made explicit as an AC-4 clause and a Red-test sibling case.

### Test-Quality critic

**T1 (harden) — Red snippet's filename did not match its subject.** The draft's Red test was named `test_retriever_with_model_mismatch_filter.py` but its body tested the *filter* directly, not the retriever.
*Fix:* renamed to `tests/unit/rag/test_model_mismatch_filter.py`; `test_retriever_with_model_mismatch_filter.py` is now the genuine retriever-integration file (AC-5).

**T2 (harden) — Red test passed bare `SolvedExample`s and asserted on `.emit`.** After the signature correction (K3) the filter consumes `ScoredSolvedExample`; the test must wrap records. `EventLog` has no bare `emit` — only `emit_internal`.
*Fix:* Red snippet wraps records in `ScoredSolvedExample`, drops the unused `embedder.embed` `AsyncMock`, sets `event_log.workflow_id`, and asserts on `emit_internal.call_args_list`.

**T3 (harden) — Event registration could drift silently.** The draft's event-shape test checked Pydantic validation only; a forgotten union/`_INTERNAL_CLASSES` wiring would still pass while `emit_internal` rejects the event at runtime.
*Fix:* AC-11 adds a discriminator-mapping assertion + an `emit_internal`/`replay` round-trip in `tests/unit/plugins/test_events.py` — the S4-05 AC-11 precedent.

**T4 (harden) — `workflow_id` / `event_id` source was unspecified.** `RagRecordModelMismatch` is a `WorkflowInternalEvent` and needs both; the draft's outline left them as `...`, inviting the executor to invent them.
*Fix:* AC-3 + the outline pin `workflow_id=self.event_log.workflow_id` (public on `EventLog`) and a minted `event_id` per sibling-emitter convention.

### Consistency critic

**K1 (block) — Wrong event module.** The draft imported `RagRecordModelMismatch` from `src/codegenie/rag/events.py` and listed that file in Files-to-touch. The module does not exist and is explicitly forbidden — S4-05 (HARDENED, block) and S5-01 (HARDENED, K3) both route every RAG event into `src/codegenie/plugins/events.py`.
*Fix:* the event lands in `plugins/events.py`, wired into the union, `_INTERNAL_CLASSES`, and `__all__`.

**K2 (block) — `RagMiss(reason=...)`.** The ADRs-honored line, References, and AC-6 constructed `RagMiss(reason="all_candidates_model_mismatch")`. S1-04 (HARDENED F5), S5-01 (HARDENED K1), and S5-02 (HARDENED K1) all fixed `RagMiss` to bare per ADR-04-0008.
*Fix:* AC-6 returns bare `RagMiss()`; the reason rides S5-01's `RagMissEvent`.

**K3 (block) — Filter signature operated on `SolvedExample`.** The draft typed the filter `Iterable[SolvedExample] -> tuple[list[SolvedExample], int]`. S5-01 (HARDENED, AC-17) froze the hook as `Callable[[Sequence[ScoredSolvedExample]], tuple[list[ScoredSolvedExample], int]]`. `SolvedExample` is not `ScoredSolvedExample`, so the draft filter is not assignable to the hook — a mypy `--strict` error, and it would not plug in at all.
*Fix:* every AC, the outline, the TDD plan, and the property consume `Sequence[ScoredSolvedExample]` and partition on `candidate.record.embedding_model`; AC-2 adds a mypy-assignability test.

**K4 (block) — `RecordProvenance.verify` does not exist.** S4-05 (HARDENED, AC-1) ships a *module-level* `codegenie.rag.provenance.verify(record, spanning_log)` and explicitly removed the staticmethod alias; `RecordProvenance` is frozen data with no behavior.
*Fix:* every reference corrected to the module-level function.

**K5 (block) — AC-9 contradicted a HARDENED decision.** The draft's AC-9 demanded `verify` check the `(record_id, chain_head)` pair and labelled head-only verification "a verification bug … surface per Rule 7." S4-05 (HARDENED) and final-design §Component 11 *deliberately* chose head-only membership ("not a `(record_id, chain_head)` proof"); `SpanningChainLog` has exactly one method and `record_id_for_head` is explicitly forbidden. Head-only is the design, not a bug.
*Fix:* the AC was removed. The intent (document the boundary of the head-only model) is preserved as an Out-of-scope entry that names the final-design + S4-05 ADR-amendment path if record-id binding is ever wanted.

**K6 (block) — Adversarial file ownership collision.** The draft created `tests/adversarial/test_rag_poisoning_chain_orphan.py` (AC-8/AC-10). That file is owned by S7-09 (Files-to-touch + done-criteria line 60) and named there by S4-05 (line 37). The draft's cases duplicated coverage already in S4-05 AC-9 (orphan-emit smoke) and S7-09 (adversarial corpus).
*Fix:* the duplicative AC-8/AC-10 were removed; the forged-head adversarial corpus is delegated to S7-09 in Out-of-scope. S5-03's genuine, non-duplicative chain-orphan contribution — the *combined exclusion order* — is retained and strengthened as the new AC-8/AC-9.

**K7 (block, Rule 7) — `RagRecordModelMismatch` double-emission.** S5-01 AC-17 has the *retriever* emit `RagRecordModelMismatch(count=excluded_count)` and lists the event in its Files-to-touch; S5-03 AC-3 has the *filter* emit it with the richer `current_model` / `sample_stale_model` payload. Both emitting = two events per query, violating AC-3's "exactly one." The shapes also disagree (`count`-only vs three-field).
*Resolution:* the **filter owns the emission** — only it holds `current_model` and `sample_stale_model`; the retriever, given just an `int`, cannot populate the richer event. S5-03 defines the full-shape event class. **Pre-execution reconciliation:** S5-01 AC-17 + Files-to-touch must drop the retriever-side emission and the retriever-side event-class definition (the retriever keeps using the returned `excluded_count` only to decide the all-excluded → bare `RagMiss()` branch). Recorded in S5-03's Out-of-scope and below under "Recommended next step." S5-01 is HARDENED, not GREEN, so this is amendable.

**K8 (harden) — AC-13 redefined `RagRecordChainOrphan`.** The draft re-declared the orphan event with `chain_head` / `expected_chain_head` fields. S4-05 (HARDENED, AC-3) already ships it with `record_id`, `record_event_chain_head`, `spanning_log_head`.
*Fix:* AC-10 defines *only* `RagRecordModelMismatch`; the `RagRecordChainOrphan` clause was dropped — S4-05 owns that shape.

### Design-Patterns critic

**D1 (harden) — `Embedder` is a fat dependency for a one-call need.** The filter only ever calls `embedder.model_digest()` once, then caches. Depending on the whole `Embedder` (and the frozen-cache `object.__setattr__` dance) is heavier than the need.
*Resolution:* surfaced as a Notes-for-implementer paragraph offering `current_model_digest: BlobDigest` injected directly — which deletes the `field(init=False)` / `__post_init__` / `object.__setattr__` machinery and makes the filter trivially test-constructible. This is the *first* filter (below rule-of-three), so per the editor discipline it is offered as the implementer's call, not mandated as an AC.

**D2 (nit) — Premature-abstraction guard preserved.** The draft's Refactor note already resists a `RecordFilter` Protocol until a second concrete filter exists. Kept verbatim — correct application of Rule 2.

**D3 (nit) — Outline import gap.** `field` was used but not imported. Fixed in the outline (`from dataclasses import dataclass, field`), alongside the corrected `plugins.events` / `rag.retriever` imports.

## Research briefs

None. Every finding was resolved against in-repo HARDENED sibling stories, their validation reports, and the current `plugins/events.py` source. No external pattern lookup was needed.

## Conflict resolutions

- **S5-03 vs S5-01 (event ownership):** S5-01 is the source of truth on the hook *signature* (`Sequence[ScoredSolvedExample]`). On *who emits* `RagRecordModelMismatch`, neither story can hold — surfaced per Rule 7; the filter wins on the merits (it alone has the payload data) and S5-01 AC-17 is flagged for reconciliation.
- **S5-03 vs S4-05 (verify semantics):** S4-05 (HARDENED) + final-design win. Head-only verification stands; AC-9's contradicting premise was removed, not averaged.
- **S5-03 vs S7-09 (adversarial file):** S7-09 + S4-05 (HARDENED line 37) win on file ownership. S5-03 keeps only the combined-exclusion-order coverage that is uniquely its own.
- **S5-03 vs S1-04/ADR-04-0008 (`RagMiss`):** S1-04/ADR win — bare `RagMiss`, typed reason event.

## Edits applied

1. Status `Ready` → `HARDENED`; title narrowed to reflect the de-scoped chain-orphan adversarial work; Validation notes block inserted.
2. Dependency line corrected: S5-01/S5-02/S4-05 marked HARDENED-not-GREEN; the `model_digest_filter` hook typed over `Sequence[ScoredSolvedExample]`; S4-05 described as a module-level `verify`.
3. ADRs-honored line: production ADR-0033 clause rewritten to bare `RagMiss()` + typed event.
4. Context rewritten — model-mismatch as the primary deliverable, combined exclusion order as the secondary, the adversarial corpus explicitly delegated to S7-09.
5. References corrected — dropped the `rag/events.py` and `RecordProvenance.verify` pointers; added `plugins/events.py` and the module-level verifier.
6. Goal rewritten — `ScoredSolvedExample`; second clause retargeted from "pin the adversarial test" to "pin the combined exclusion order".
7. Acceptance criteria: 15 → 12. AC-1–AC-4/AC-7 retyped to `ScoredSolvedExample` + `emit_internal`; AC-5/AC-6 de-`reason`-ed and given the `xfail` precondition; draft AC-8/AC-9/AC-10 removed (K5/K6); draft AC-11/AC-12 retained and strengthened as AC-8/AC-9; AC-13/AC-14/AC-15 renumbered AC-10/AC-11/AC-12 with the full event shape, discriminator-registration test, and broadened property.
8. Implementation outline: corrected imports, `ScoredSolvedExample`, `emit_internal`, pinned `workflow_id`/`event_id`.
9. TDD plan: Red snippet rewritten for the filter; Green steps reordered (event class first).
10. Files-to-touch: `rag/events.py` removed; `plugins/events.py` + `tests/unit/plugins/test_events.py` added; the adversarial file removed.
11. Out-of-scope: added the S7-09 delegation, the head-only-verify boundary, and the S5-01 AC-17 reconciliation.
12. Notes: added the `ScoredSolvedExample` typing note, the impure-filter note, the `workflow_id` source, the bare-`RagMiss` note, and the `Embedder`-vs-`BlobDigest` design option.

## Verdict rationale

**HARDENED.** The story's core goal — a concrete model-mismatch filter that plugs into S5-01's hook and emits one audit event per query — is sound and untouched. Every block was a stale-contract contradiction fixable in place by realigning to the now-HARDENED siblings, exactly as S5-01 and S5-02 themselves were realigned. No goal rewrite was required (the chain-orphan clause was a mis-scoped/contradictory *sub*-goal, not the story's intent), so this is not a RESCUE.

## Recommended next step

Before executing **either** S5-01 or S5-03, reconcile S5-01 AC-17: the retriever must **not** emit `RagRecordModelMismatch` and must **not** define the event class — the concrete filter (S5-03) owns both. The retriever uses the filter's returned `excluded_count` only to decide the all-excluded → bare `RagMiss()` branch. A targeted re-validation or hand-edit of S5-01 is the cleanest path. Separately, S5-03's retriever-integration ACs (AC-5/AC-6/AC-8/AC-9) require S5-01 GREEN; until then they execute as `xfail(strict=True)`.
