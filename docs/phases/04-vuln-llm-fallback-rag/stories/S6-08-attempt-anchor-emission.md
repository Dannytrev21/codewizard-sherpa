# Story S6-08 — `AttemptAnchor` event emission + JSONL projection

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** Ready
**Effort:** M
**Depends on:** S6-01 (FallbackTier pipeline + per-step events), S6-03 (`on_validated` hook — drives the `validator_outcome` field)
**ADRs honored:** ADR-04-0017 (`AttemptAnchor` schema), ADR-04-0002 (named-sequential dispatch — anchor emission slots into the existing pipeline), production ADR-0034 (event-sourcing canonical primitive), production ADR-0040 (data retention for audit trails)

## Context

Phase 4's `FallbackTier` already emits a per-step event stream per attempt (S6-01). What's missing is the **joined per-attempt anchor** — the single record that carries `(plan_proposal, retrieved_evidence_chain_head, validator_outcome, trust_outcome, prompt_digest, response_digest, cost)` — that future critic-training, replay debugging, and cross-phase consumers would read.

ADR-04-0017 commits Phase 4 to recording this anchor as a first-class additive event (`AttemptAnchorRecorded`), persisted as JSONL at `.codegenie/fallback/anchors/{utc-date}/{workflow_id}.jsonl`. The anchor is purely additive over S6-01's existing event sequence; no existing event is replaced or renamed. The `trust_outcome` fields are deferred-attached by Phase 5's `GateRunner` via `AttemptAnchor.attach_trust_outcome(...)` — Phase 5 already merged but does not yet call this hook (Phase 5 contract gets one additive line).

This story is the *option-preservation* anchor for everything CTRL-style / Critique-RL-style. It costs ~80 LOC of production code + ~120 LOC of tests; it pays back the day a critic is trained or the day someone needs to replay a five-month-old refusal.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 1 — FallbackTier` — the dispatch shell anchor emission appends to
  - `../phase-arch-design.md §Control flow happy-path 1–9` — anchor is event #10, emitted *after* `TransformBuilt` / `Refused`
  - `../phase-arch-design.md §State` — `FallbackTier` is stateless; anchor builder is a per-call object instantiated at `run` entry
- **Phase ADRs:**
  - `../ADRs/0017-attempt-anchor-event-schema.md` — the schema this story implements; `schema_version=1`; `extras` reserved for future extension
  - `../ADRs/0002-fallback-tier-pipeline-no-langgraph.md` — anchor emission is the *last* step in the named sequential pipeline; do not introduce a separate node
  - `../ADRs/0011-rag-bypass-on-retry.md` — `retrieved_evidence_chain_head` MUST be `None` and `retrieved_record_ids` MUST be `()` when `prior_attempts != []`
- **Production ADRs:**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — append-only discipline; no in-place mutation
  - `../../../production/adrs/0040-data-lifecycle-retention-and-classification.md` — anchors are audit-class; 90 day hot retention minimum
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — `TrustOutcome` shape Phase 5 attaches (`passed`, `confidence`)
- **Existing code (S6-01 must have landed):**
  - `src/codegenie/fallback/tier.py` — `FallbackTier.run(...)` — where anchor builder is instantiated and emitted
  - `src/codegenie/fallback/plan_outcome.py` — `PlanOutcome` discriminated union (drives `validator_outcome` field)
  - `src/codegenie/events/` (or wherever S6-01 lands the event-log adapter) — the `AttemptAnchorRecorded` event is appended here
- **Source design:**
  - `../final-design.md §Components 1 (FallbackTier), 14 (PlanOutcome)` — event contract
- **External reference (background; do not implement against):**
  - `../../../reviews/2026-05-18-research-committee-search-paper.md §Recommended next moves` — *why* this story exists
  - `../../../reviews/2026-05-18-agent-orchestration-survey-and-recommendations.md` rows #3, #7

## Goal

`FallbackTier.run(...)` emits exactly one `AttemptAnchorRecorded(anchor: AttemptAnchor)` event per attempt (success or refused), and the anchor is persisted as one JSONL line at `.codegenie/fallback/anchors/{utc-date}/{workflow_id}.jsonl` (mode `0600`, fsync per write) carrying every field in ADR-04-0017's schema. Phase 5's `GateRunner` invokes `anchor.attach_trust_outcome(...)` before the line is fsync'd.

## Acceptance criteria

- [ ] `src/codegenie/fallback/attempt_anchor.py` exports `AttemptAnchor` — Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`, fields exactly as in ADR-04-0017 §Decision, `schema_version: Literal[1] = 1`.
- [ ] `AttemptAnchor.attach_trust_outcome(trust_outcome: TrustOutcome) -> AttemptAnchor` is a pure method returning a new instance with `trust_outcome_passed` + `trust_outcome_confidence` set; raises `ValueError` if called twice on the same instance (idempotency violation surfaces as an immediate failure).
- [ ] `FallbackTier.run(...)` emits exactly one `AttemptAnchorRecorded` event per attempt; emission is the *last* event in the per-step sequence — asserted by extending the S6-01 event-order tape test.
- [ ] **Anchor emission is unconditional** — both happy-path (`TransformBuilt` → anchor) and every refusal path (`Refused(PROVENANCE_NOT_APP_LAYER)`, `Refused(BUDGET_EXCEEDED)`, `Refused(LEAF_SCHEMA_VIOLATION)`, `Refused(LEAF_REFUSED)`) emit an anchor. Refusal anchors set `trust_outcome_passed=None` and `trust_outcome_confidence=None` (Phase 5 never sees them).
- [ ] **`retrieved_evidence_chain_head` correctness:** when `prior_attempts != []` (retry path, ADR-04-0011), the anchor's `retrieved_evidence_chain_head == None` and `retrieved_record_ids == ()`. When RAG returns `RagMiss`, both are also empty. Asserted by a parameterized test covering `{initial-hit, initial-degraded, initial-miss, retry-bypass}`.
- [ ] **JSONL projection** at `.codegenie/fallback/anchors/{utc-date}/{workflow_id}.jsonl`: one line per anchor, mode `0600` on both directory and file, `fsync(2)` per write. Re-running the same workflow appends; never truncates.
- [ ] **Fence test** `tests/fence/test_attempt_anchor_is_terminal_event.py` — AST walk over `src/codegenie/fallback/tier.py` confirms no `event_log.append(...)` call follows an `AttemptAnchorRecorded` emission in any control-flow branch. Runtime assertion in the event-log adapter raises if a second event is appended after `AttemptAnchorRecorded` in the same attempt.
- [ ] **Schema-version fence** `tests/fence/test_attempt_anchor_schema_version.py` — confirms `AttemptAnchor.schema_version == 1` (constant); a hand-edit to bump must come with both versions co-existing for one release cycle (the test reads a `models.lock`-style allowlist).
- [ ] **`extras` slot is namespaced** — Pydantic validator rejects `extras` keys not matching `^phase\d+(?:\.\d+)?\.[a-z][a-z0-9_]*$`. Asserted by `tests/unit/fallback/test_attempt_anchor_extras_namespace.py`.
- [ ] **Phase 5 deferred-attach hook**: a one-line additive change to Phase 5's `GateRunner` (or its anchor-attach adapter, depending on Phase 5's seam) calls `anchor.attach_trust_outcome(trust_outcome)` before the JSONL line is written. The Phase-5-side contract change is documented inside this story (no separate cross-phase ADR — Phase 5 already merged and the hook is purely additive).
- [ ] `mypy --strict` clean on the new module and tests; `ruff check`, `ruff format --check`, `make typecheck`, `make test` all green.
- [ ] Story file status flipped `Ready` → `Done` after the executor verifies; updates `docs/phases/04-vuln-llm-fallback-rag/stories/README.md` Step 6 to reflect S6-08 as the new last story in the step.

## Implementation outline

1. **New module `src/codegenie/fallback/attempt_anchor.py`** — `AttemptAnchor` Pydantic model exactly per ADR-04-0017 §Decision. Use `tuple[RagRecordId, ...]` for the records list (immutable), `Mapping[str, str]` for `extras` (frozen via `MappingProxyType` returned from a validator).
2. **`AttemptAnchorBuilder` helper** at the same path — instantiated at `FallbackTier.run` entry; accumulates fields as the pipeline progresses; finalizes via `.build() -> AttemptAnchor` before emission. This isolates the "accumulate-as-we-go" concern from `FallbackTier`'s otherwise stateless `run`.
3. **Wire emission in `src/codegenie/fallback/tier.py`** — at the end of `run`, after `TransformBuilt` (happy path) or any `Refused` branch (refusal paths), call `event_log.append(AttemptAnchorRecorded(anchor=builder.build()))` and persist the JSONL line.
4. **JSONL writer** `src/codegenie/fallback/anchor_writer.py` — pure I/O: `write_anchor(anchor: AttemptAnchor, output_dir: Path) -> None`. `0700` on `{utc-date}` directory; `0600` on `{workflow_id}.jsonl`; `os.fsync(fd)` per line; UTF-8; `\n`-terminated. JSON serialization via `anchor.model_dump_json()` — frozen + extra=forbid guarantees stable shape.
5. **Phase 5 deferred-attach** — add the one-line call (`anchor = anchor.attach_trust_outcome(trust_outcome)`) in `GateRunner` before the writer fires. This is the only Phase-5-side change.
6. **Fence tests** — the two `tests/fence/` modules (terminal-event + schema-version) plus the unit/parameterized tests in `tests/unit/fallback/`.
7. **Update `docs/phases/04-vuln-llm-fallback-rag/stories/README.md`** — Step 6 manifest table gets a new row `S6-08 | AttemptAnchor emission ...`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/fallback/test_attempt_anchor_emission.py`

```python
# tests/unit/fallback/test_attempt_anchor_emission.py
async def test_fallback_tier_emits_attempt_anchor_last_on_happy_path(
    fallback_tier_with_fakes: FallbackTier,
    capturing_event_log: list[Event],
    happy_path_inputs: HappyPathFixture,
) -> None:
    """
    Per ADR-04-0017: AttemptAnchorRecorded MUST be the final event in the
    per-attempt sequence. A future critic-training pipeline reads the JSONL
    projection of these anchors; if any event fires after the anchor in the
    same attempt, the projection is incomplete and the replay guarantee is
    broken.
    """
    await fallback_tier_with_fakes.run(
        happy_path_inputs.advisory,
        happy_path_inputs.repo_ctx,
        happy_path_inputs.recipe_selection,
        prior_attempts=[],
    )
    # arrange: event log captured every emission in order
    # act: locate the AttemptAnchorRecorded index
    anchor_idx = next(
        i for i, e in enumerate(capturing_event_log)
        if isinstance(e, AttemptAnchorRecorded)
    )
    # assert: it's the last event in the attempt
    assert anchor_idx == len(capturing_event_log) - 1, (
        f"AttemptAnchorRecorded must be terminal; "
        f"found {len(capturing_event_log) - anchor_idx - 1} events after it"
    )
    # assert: anchor carries the joined tuple
    anchor = capturing_event_log[anchor_idx].anchor
    assert anchor.schema_version == 1
    assert anchor.plan_proposal_kind in {"apply_recipe", "apply_transform", "request_human", "refuse"}
    assert anchor.retrieved_evidence_chain_head is not None  # happy path = RAG ran
    assert anchor.validator_outcome == "AppliedFromLlm"
    assert anchor.trust_outcome_passed is None  # Phase 5 hasn't attached yet
```

The test must fail because `attempt_anchor.py` doesn't exist yet, `FallbackTier` doesn't emit the event yet, and `AttemptAnchorRecorded` isn't imported. `ImportError` is the expected red failure.

Additional red tests to land in the same commit (each fails for the same reason):
- `test_attempt_anchor_on_refusal_paths` — parameterized over 4 refusal reasons; asserts anchor emitted, `trust_outcome_*` are `None`.
- `test_retrieved_evidence_chain_head_none_on_retry` — `prior_attempts` non-empty → `retrieved_evidence_chain_head is None`.
- `test_extras_namespace_validator` — `extras={"foo": "bar"}` raises; `extras={"phase7.distroless_target": "cgr.dev/alpha"}` succeeds.
- `test_attach_trust_outcome_is_idempotent_violation` — calling `.attach_trust_outcome` twice raises `ValueError`.
- `test_jsonl_projection_is_appended_with_correct_permissions` — runs `FallbackTier.run` twice; second call appends a second line to the same file; `stat().st_mode & 0o777 == 0o600`.

### Green — make it pass

The minimum implementation:

1. `src/codegenie/fallback/attempt_anchor.py` — the Pydantic model + builder + `attach_trust_outcome` method.
2. New event type `AttemptAnchorRecorded(BaseModel)` carrying `anchor: AttemptAnchor`.
3. `src/codegenie/fallback/anchor_writer.py` — JSONL write with 0600/fsync.
4. Modify `src/codegenie/fallback/tier.py` — instantiate builder at `run` entry; populate fields as pipeline progresses; emit at end.
5. Modify Phase 5's `GateRunner` — one line to call `anchor.attach_trust_outcome(...)` before persistence.

No new packages. No new dependencies. ~80 LOC production.

### Refactor — clean up

- Confirm `AttemptAnchor` is frozen and `extra="forbid"`; verify with a runtime test that `anchor.foo = ...` raises.
- Move builder to a module-private helper if it doesn't need to be exported.
- Confirm `extras` is wrapped in `MappingProxyType` so consumers cannot mutate.
- Confirm the JSONL writer uses `os.O_CREAT | os.O_APPEND | os.O_WRONLY` with `0o600` mode explicitly, not relying on umask.
- Run the full event-order tape test from S6-01; confirm it still passes with anchor as the appended event.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/attempt_anchor.py` | New — the `AttemptAnchor` model, `AttemptAnchorBuilder`, `AttemptAnchorRecorded` event type |
| `src/codegenie/fallback/anchor_writer.py` | New — JSONL projection writer (0600, fsync, append-only) |
| `src/codegenie/fallback/tier.py` | Modify — instantiate builder, accumulate fields, emit `AttemptAnchorRecorded` as the terminal event in every branch |
| `src/codegenie/gate/runner.py` (or wherever Phase 5's `GateRunner` lives) | Modify — one line: `anchor = anchor.attach_trust_outcome(trust_outcome)` before JSONL write |
| `tests/unit/fallback/test_attempt_anchor_emission.py` | New — TDD red tests (terminal-event + refusal paths + retry bypass + extras namespace + idempotency violation + JSONL append) |
| `tests/fence/test_attempt_anchor_is_terminal_event.py` | New — AST walk fence over `tier.py`; runtime assertion in event-log adapter |
| `tests/fence/test_attempt_anchor_schema_version.py` | New — pins `schema_version == 1`; gated by `models.lock`-style allowlist for future bumps |
| `docs/phases/04-vuln-llm-fallback-rag/stories/README.md` | Modify — add S6-08 row to Step 6 manifest |

## Out of scope

- **Critic training, critic inference, comparator selection.** This story preserves the *option* of CTRL-style critic training; it does not implement any critic. The orchestration survey memo Tier 2 / Tier 3 rows describe what comes later and explicitly defer until Phase 4 has runtime evidence.
- **Reading the JSONL anywhere.** No production code consumes the anchors in Phase 4; the only consumer in this story is the unit/fence tests. Phase 7 / Phase 15 / future critic-training consumers will add read paths under their own ADRs.
- **Cross-stream join with Phase 5's event stream.** Phase 5 attaches `TrustOutcome` to the same `AttemptAnchor` instance via `attach_trust_outcome`; no projection joins the Phase 4 and Phase 5 streams in this story. The join *primitive* is the `workflow_id` + `attempt_index` pair; a downstream consumer doing analytics work owns the join.
- **Anchor retention enforcement.** Anchors fall under ADR-0040's audit-trail class; Phase 14's data-lifecycle worker enforces the 90-day-hot / cold-storage policy. This story writes the data; the lifecycle worker reads it.
- **`schema_version=2` migration plan.** When (and if) anchors gain a non-`extras` field, a follow-up ADR will document the co-existence-release-cycle rule and the migration test.

## Notes for the implementer

- **The anchor is the *last* event per attempt — this is a load-bearing invariant.** The fence test enforces it because the JSONL projection's "one line per attempt" promise depends on it. Any future feature that wants to emit a post-anchor event must restructure (e.g., emit *before* anchor, or introduce a `PostAttemptAnchorRecorded` event with its own schema versioning).
- **`extras` is string-valued only.** Resist the urge to allow `Mapping[str, Any]`. Stable JSON shape matters more than ergonomics; consumers can parse string values on read.
- **`extras` keys are namespaced** by phase prefix (`phase7.*`, `phase15.*`). The validator regex enforces this so consumer phases cannot collide.
- **`AttemptAnchor.attach_trust_outcome` is functional, not mutating.** Returns a new frozen instance. This matches the frozen-by-default Pydantic discipline (ADR-0033).
- **The JSONL file's directory mode is `0700`** (operator-only). The file is `0600`. Both must be set explicitly — do not rely on umask.
- **Phase 5's one-line addition is *not* a separate cross-phase ADR.** Phase 5 already merged and `GateRunner` already exists. The hook is purely additive (one method call). If the executor finds the Phase 5 seam is not where this story expects, surface the gap and pause — do *not* refactor Phase 5 inside this story.
- **The schema_version=1 pin is the dam.** Any pressure to bump to 2 in the future must come with: (a) a Phase 4 ADR amendment, (b) a co-existence release cycle test, (c) a documented migration path for the JSONL projection. The fence test exists to make that pressure visible.
- **Storage cost is real.** ~1.5 KB per attempt × ~3 attempts/workflow × portfolio-scale. At 10K workflows/day that's ~45 MB/day, ~16 GB/year hot. Acceptable per ADR-0040 retention; document it in the runbook the closeout story (S7-10) ships.
