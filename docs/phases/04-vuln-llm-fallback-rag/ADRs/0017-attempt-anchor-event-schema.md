# ADR-04-0017: `AttemptAnchor` event — schema for future critic-training and replay audit

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** event-sourcing · audit-anchor · schema-versioning · extension-by-addition · option-preservation

## Context

Phase 4's `FallbackTier` already emits a sequence of structured events per attempt: `ProvenanceClassified`, `BudgetPrechecked`, `RagHit | RagDegraded | RagMiss`, `PromptBuilt`, `BudgetPrecharged`, `LeafInvoked`, `LeafReturned`, `BudgetReconciled`, `TransformBuilt`, `PlanOutcomeEmitted` (S6-01). Phase 5's `GateRunner` adds `TrustOutcome` shape and retry events (`RetryRequested`, `AttemptRefused`). Together these form a two-stream event log (Phase 4 attempt stream + Phase 5 gate stream) tied by `workflow_id` and `attempt_index`.

That log is sufficient for replay and post-hoc human review. It is **not** sufficient for the option the 2025–2026 literature flags as the largest deferred lift: training an outcome-critic against `(proposal, evidence_seen_by_critic, critic_decision, verifier_outcome)` tuples — CTRL-style (arXiv:2502.03492), Critique-RL-style (Oct 2025), or any successor. See `../../../reviews/2026-05-18-research-committee-search-paper.md` and `../../../reviews/2026-05-18-agent-orchestration-survey-and-recommendations.md` rows #3 and #7.

The literature recommendation is structural: **record the joined per-attempt tuple as a first-class audit anchor from day one**, not as a downstream projection. Joining the existing event streams later is feasible but lossy in two ways: (a) the `retrieved_evidence_chain_head` Phase 4 emits is the chromadb BLAKE3 head at *retrieval time*; the store mutates as `on_validated` harvest fires, so a post-hoc join cannot reconstruct what evidence the prompt actually saw; (b) `TrustOutcome` lives in Phase 5's stream and joining it to Phase 4's attempt requires a stable cross-stream key that, today, only exists in workflow-run scope and is not durably indexed.

This ADR commits Phase 4 to emit a single `AttemptAnchorRecorded(anchor: AttemptAnchor)` event at the close of each attempt — successful or refused — carrying the joined tuple. It is **purely additive** over S6-01's existing event sequence; no existing event is replaced or renamed.

## Options considered

- **Option A — Project the anchor later (do nothing now).** Wait until critic training is funded; re-derive `AttemptAnchor` rows by joining Phase 4 and Phase 5 event streams against the chromadb mutation log.
- **Option B — Emit `AttemptAnchor` as a first-class additive event in Phase 4** (this ADR's decision). One frozen Pydantic model, one schema version field, one extension slot (`extras: Mapping[str, str]`). Projects to `.codegenie/fallback/anchors/{utc-date}/{workflow_id}.jsonl`.
- **Option C — Replace per-step events with a single anchor.** Drop `ProvenanceClassified`, `BudgetPrechecked`, etc. and emit only `AttemptAnchor`.

## Decision

**Option B.** `FallbackTier.run(...)` emits exactly one `AttemptAnchorRecorded` event per attempt, after the terminal outcome (either `TransformBuilt` for a happy path or `Refused(...)` for any refusal). Phase 5's `GateRunner` attaches the `TrustOutcome` slice via a deferred-attach hook (`AttemptAnchor.attach_trust_outcome(trust_outcome) -> AttemptAnchor`) before the anchor is persisted. The persisted shape:

```python
class AttemptAnchor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Versioning — every consumer asserts schema_version on read
    schema_version: Literal[1] = 1

    # Identity
    attempt_id: UUID                           # newly minted per attempt
    workflow_id: WorkflowId                    # cross-stream join key (Phase 5 stable)
    attempt_index: int                         # 0 = initial; ≥1 = retry under prior_attempts

    # Inputs the LLM saw
    advisory_id: AdvisoryId
    prompt_digest_blake3: PromptDigest         # exact bytes sent to the leaf
    retrieved_evidence_chain_head: ChainHead | None   # None ⇔ RAG bypassed (retry path, ADR-0011)
    retrieved_record_ids: tuple[RagRecordId, ...]     # () when RAG bypassed or miss

    # Output the LLM produced
    plan_proposal_kind: Literal["apply_recipe", "apply_transform", "request_human", "refuse"]
    response_digest_blake3: ResponseDigest

    # Verifier outcomes (deferred-attach: Phase 4 sets validator_outcome, Phase 5 sets trust_outcome)
    validator_outcome: PlanOutcomeTag          # "AppliedFromRecipe" | "AppliedFromLlm" | "RagOnlyApplicable" | "Refused"
    refusal_reason: RefusalReason | None       # set iff validator_outcome == "Refused"
    trust_outcome_passed: bool | None          # set by Phase 5; None on Phase-4-side refusal before reaching Phase 5
    trust_outcome_confidence: Literal["high", "medium", "low"] | None

    # Cost (joined from BudgetReconciled)
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal

    # Time + extension slot
    timestamp_utc: datetime                    # tz-aware, UTC
    extras: Mapping[str, str]                  # frozen via MappingProxyType; future schema_version=2 extension
```

**Storage:** JSONL files at `.codegenie/fallback/anchors/{utc-date-yyyy-mm-dd}/{workflow_id}.jsonl`, mode `0600`, fsync per write. Append-only; no in-place mutation. Existing event log is unchanged.

**Schema versioning rule:** any new required field requires `schema_version` bump and a corresponding fence test asserting both versions co-exist for one release cycle. New *optional* fields go into `extras` (string-valued only — keeps the JSON stable; consumers parse on read).

## Tradeoffs

| Gain | Cost |
|---|---|
| Preserves the option of CTRL-style critic training without retroactive data archaeology | One additional event type to maintain (~80 LOC including tests) |
| Cross-stream join key (`workflow_id`, `attempt_index`) is durable and indexable from day one | Storage cost: ~1.5 KB per attempt × ~3 attempts/workflow × portfolio-scale; rolls daily, GC'd per ADR-0040 retention |
| Anchor shape is documented, not implicit-via-join — Phase 7 / Phase 15 / future critic consumers read a single schema | Schema choices made today calcify under usage; the `extras` slot is the deliberate escape hatch |
| Fixes the chromadb-mutates-under-the-join failure mode for `retrieved_evidence_chain_head` | Adds one Phase-5 deferred-attach call (`anchor.attach_trust_outcome(...)`) — small additional Phase-5 ↔ Phase-4 contract surface |

## Consequences

- **Becomes easier.** Phase 7 (distroless migration) can reuse the anchor schema verbatim by extending the `plan_proposal_kind` enum (additive). Future critic-training (deferred) reads JSONL with one `pydantic.TypeAdapter[AttemptAnchor]`. Replay debugging across the two streams uses `attempt_id` as the join key.
- **Becomes harder / constrained.** The four "verifier outcomes" fields (`validator_outcome`, `refusal_reason`, `trust_outcome_passed`, `trust_outcome_confidence`) are now schema-load-bearing — any future change to `PlanOutcome` or `TrustOutcome` shapes triggers a `schema_version` bump.
- **New invariants.** (1) `AttemptAnchorRecorded` is the *last* event emitted per attempt; nothing fires after it in that attempt's frame. (2) `retrieved_evidence_chain_head` is captured *at retrieval time*, not at anchor-write time. (3) `extras` keys are namespaced with the consumer phase (`phase7.foo`, `phase15.bar`) to prevent key collisions when multiple phases extend.
- **Storage retention.** Anchors fall under ADR-0040's data-lifecycle class for *audit trails*: minimum 90 days hot, archived to long-term cold storage by Phase 14's data lifecycle worker.
- **Fence test.** A new `tests/fence/test_attempt_anchor_is_terminal_event.py` asserts that no Phase 4 emission follows `AttemptAnchorRecorded` in any code path (AST walk + runtime assertion in the event-log adapter).

## Reversibility

**Low cost — for now.** Adding `AttemptAnchor` is purely additive; the existing event stream is unchanged, so removing it later is a deletion plus a fence-test removal. **Medium cost once consumers exist.** Phase 7 / Phase 15 / future critic-training consumers will lock into the schema; bumping `schema_version` will require a co-existence release cycle. **High cost** once a trained critic is in production keying on `schema_version=1`.

This is acceptable: the future-cost is the *whole point* of recording the anchor today. The deliberate non-decision is "what to do with the data" — that decision lives in a future ADR (post-Phase-3 runtime evidence), per `../../../reviews/2026-05-18-agent-orchestration-survey-and-recommendations.md` Tier-2 deferred row.

## Evidence / sources

- `../final-design.md §Components 1 (FallbackTier), 14 (PlanOutcome)` — event-emission contract
- `../phase-arch-design.md §Control flow` — the per-step event order S6-01 implements
- [ADR-04-0002](0002-fallback-tier-pipeline-no-langgraph.md) — named-sequential dispatch
- [ADR-04-0011](0011-rag-bypass-on-retry.md) — why `retrieved_evidence_chain_head` is `None` on retry
- [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md) — append-only event-sourcing discipline this anchor inherits
- [production ADR-0040](../../../production/adrs/0040-data-lifecycle-retention-and-classification.md) — retention class for audit trails
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) — `TrustOutcome` shape Phase 5 attaches
- `../../../reviews/2026-05-18-research-committee-search-paper.md §Recommended next moves` — "Phase 3 story: audit-anchor schema" rationale
- `../../../reviews/2026-05-18-agent-orchestration-survey-and-recommendations.md` rows #3 and #7 — "audit-anchor schema designed for future critic training — preserves the option of CTRL-style RL critic training"
- CTRL (Xie et al., arXiv:2502.03492) — the deferred-but-preserved use case
