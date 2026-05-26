# Story S6-08 — `AttemptAnchor` event emission + JSONL projection

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** GREEN-partial — 2026-05-25 (phase-story-executor; see [`_attempts/S6-08.md`](_attempts/S6-08.md) — schema model + attach API + refusal-path emission + JSONL writer + three fence tests + AttemptId/PromptDigest/ResponseDigest newtypes shipped GREEN. AC-PHASE5-1 BLOCKED per the story's own AC-PHASE5-2 guard: `src/codegenie/gates/runner.py` does not yet exist (Phase 5 not built). `FallbackTier.finalize_success_anchor(...)` is the additive hook Phase 5's `GateRunner` will call in two lines once it ships. AC-ORDER-1 strict 11-event index assertion deferred until S6-01 GREEN-complete; today's terminal-position fence is stronger than nothing. 144 tests green; mypy --strict + ruff + lint-imports (12/12) all clean.)
**Effort:** M
**Depends on:** S6-01 (FallbackTier pipeline + per-step events; lands `_INTERNAL_CLASSES` Phase-4 entries in `src/codegenie/plugins/events.py`), S6-03 (`on_validated` hook — drives the `validator_outcome` field and is the host of the deferred JSONL write on the success path)
**ADRs honored:** ADR-04-0017 (`AttemptAnchor` schema), ADR-04-0002 (named-sequential dispatch — anchor emission slots into the existing pipeline as the *new* terminal event after `PlanOutcomeEmitted`), production ADR-0034 (event-sourcing canonical primitive — append-only, no in-place mutation), production ADR-0040 (data retention for audit trails)

## Validation notes (added 2026-05-24 by phase-story-validator — HARDENED)

This story was hardened in place. Material changes recorded here so the executor can trace each new constraint to its origin. Full audit log: `_validation/S6-08-attempt-anchor-emission.md`.

- **Resolved a JSONL-write-timing contradiction** (split between Phase 4 refusal paths and Phase 5 success path). New AC-WRITER-1..-3 pin the dispatch: Phase 4 writes refusal anchors immediately (trust fields `None`); Phase 5's `on_validated` deferred-attach call writes success anchors after `attach_trust_outcome(...)`. Both write sites use the same `anchor_writer.write(...)` adapter. Two write sites, one writer, one file shape.
- **Resolved required-field contradiction with early refusals** (PROVENANCE_NOT_APP_LAYER / BUDGET_EXCEEDED refuse before any prompt is built, so `prompt_digest_blake3` / `response_digest_blake3` / `tokens_in` / `tokens_out` / `cost_usd` are not available). New AC-SCHEMA-1 makes these five fields `T | None` in the `schema_version=1` model — a *clarification* of ADR-04-0017 §Decision consistent with the ADR's "anchor emission is unconditional" Consequence, not a schema bump. ADR amendment note added to Notes-for-implementer.
- **Fixed three concrete-codebase mismatches** the original story would have surfaced as runtime errors:
  - `src/codegenie/gate/runner.py` (singular) → `src/codegenie/gates/runner.py` (plural — matches Phase 5's [`S5-02`](../../05-sandbox-trust-gates/stories/S5-02-gate-runner-retry-loop.md) shipped path).
  - `event_log.append(AttemptAnchorRecorded(...))` → `event_log.emit_internal(AttemptAnchorRecorded(...))` (the actual `WorkflowEventLog` adapter in `src/codegenie/plugins/events.py` exposes `emit_internal` / `emit_spanning`, no `append`).
  - Directory mode self-contradiction (AC said `0600`, Notes said `0700`): aligned to `0o700` for the date directory, `0o600` for the JSONL file. `0o600` on a directory is unreachable.
- **Added the extension-by-addition registry edit** the original story silently omitted: AC-REGISTRY-1..-3 require `AttemptAnchorRecorded` to land in `WorkflowInternalEvent` (discriminated union) AND `_INTERNAL_CLASSES` tuple AND carry an `event_type: Literal["attempt_anchor_recorded"]` discriminator field, matching the established Phase 1/2/3 event pattern (`PluginsLoaded`, `RecipeMatched`, etc.). Without this, `emit_internal(...)` raises `TypeError` at the isinstance gate (`src/codegenie/plugins/events.py:769`).
- **Pinned the terminal-event invariant against the ten-event tape** S6-01 freezes. New AC-ORDER-1 specifies anchor is event index 11 (0-based 10) of the per-attempt tape, emitted *after* `PlanOutcomeEmitted` (S6-01's previous terminal event). The S6-01 tape test grows by one entry; the S6-07 determinism property's `EXPECTED_EVENT_COUNT_PER_BRANCH` constant goes 10 → 11 across all four branches.
- **Hardened the test plan against six obvious-but-uncovered failure modes**: round-trip JSONL parse (not just permissions), tz-aware UTC timestamp, identity-field correctness (`workflow_id` matches the run, `attempt_index` matches `len(prior_attempts)`, `attempt_id` is per-attempt-unique), `plan_proposal_kind` discriminator exhaustiveness against `PlanProposal`'s variants, `cost_usd` Decimal serialization stability (string, not float), and a Hypothesis property for the `extras` namespace regex.
- **Surfaced design-pattern opportunities** in Notes-for-implementer (rule-of-three not reached for any — kept inline, not extracted): the `AttemptId` newtype is the third domain identifier in this phase after `WorkflowId` + `AdvisoryId` so newtype extraction is now warranted (CLAUDE.md "Newtype identifiers" commitment); `AttemptAnchorBuilder` is single-use, so stay file-private (Rule 2); the writer is sole-call-site, so a single function not a class.
- **Marked one residual risk as Notes-for-implementer, not AC**: in-place file growth (an anchor's JSONL line is appended on attempt close; the same workflow may emit ≤3 attempts; readers must tolerate partial trailing writes on crash). The append-only `O_APPEND` write guarantees atomicity per line up to PIPE_BUF on POSIX. The writer is not asked to ship a reader.

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

`FallbackTier.run(...)` constructs exactly one `AttemptAnchor` per attempt (success or refused) and emits an `AttemptAnchorRecorded(anchor)` event as the *new terminal event* of S6-01's per-step tape (event index 10, after `PlanOutcomeEmitted`). The anchor is persisted as one JSONL line at `.codegenie/fallback/anchors/{utc-date}/{workflow_id}.jsonl` (directory mode `0o700`, file mode `0o600`, `O_APPEND | O_CREAT | O_WRONLY` open, `fsync(2)` per write). Refusal-path anchors are written *inside* `FallbackTier.run` before return; success-path anchors are written *deferred* by Phase 5's `on_validated`-driven call site (`src/codegenie/gates/runner.py`) after `anchor.attach_trust_outcome(trust_outcome)`. Both write sites import the same `anchor_writer.write(...)` adapter.

## Acceptance criteria

### Schema (the persisted shape)

- [ ] **AC-SCHEMA-1.** `src/codegenie/fallback/attempt_anchor.py` exports `AttemptAnchor` — Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`, `schema_version: Literal[1] = 1`, and fields per ADR-04-0017 §Decision *with the following early-refusal clarification* (consistent with the ADR's "anchor emission is unconditional" Consequence — recorded as a Notes-for-implementer ADR-amendment item, not a schema bump): the five LLM-call-derived fields are `Optional` in `schema_version=1` — `prompt_digest_blake3: PromptDigest | None`, `response_digest_blake3: ResponseDigest | None`, `tokens_in: int | None`, `tokens_out: int | None`, `cost_usd: Decimal | None`. Refusal paths that short-circuit before `LeafLlm.invoke` set these to `None`; happy-path and post-LLM refusals (`LEAF_REFUSED`, `LEAF_SCHEMA_VIOLATION`) populate them.
- [ ] **AC-SCHEMA-2.** `timestamp_utc: datetime` is tz-aware UTC — a Pydantic field validator rejects naive datetimes with a clear message. Asserted by a parameterized test passing `datetime.now()` (naive) and `datetime.now(tz=timezone.utc)` (aware).
- [ ] **AC-SCHEMA-3.** `cost_usd` (when not `None`) serializes to a JSON *string* via `Decimal`-to-`str` (not float) — pinned by a round-trip test (`model_dump_json` → parse → assert string type). Float serialization is forbidden because portfolio-scale fan-in of float-encoded cents drifts under cumulative arithmetic.
- [ ] **AC-SCHEMA-4.** `extras: Mapping[str, str]` defaults to an empty `dict` frozen via a `model_validator(mode="after")` returning `MappingProxyType({})`. Reassigning `anchor.extras["k"] = "v"` raises `TypeError`.
- [ ] **AC-SCHEMA-5.** `plan_proposal_kind: Literal["dep_bump", "override", "callsite_rewrite", "refuse"]` — the four literal members MUST match the four discriminator tag values of `PlanProposal`'s discriminated union (phase-arch-design.md §Component 2). Fence test `tests/fence/test_attempt_anchor_plan_kind_matches_proposal.py` AST-walks `PlanProposal`'s union members and asserts set equality with the `Literal[...]` members. ADR-04-0017 §Decision's `"apply_recipe" | "apply_transform" | "request_human" | "refuse"` example was illustrative; the *correct* members are `PlanProposal`'s own tags.

### Functional behaviour

- [ ] **AC-ATTACH-1.** `AttemptAnchor.attach_trust_outcome(trust_outcome: TrustOutcome) -> AttemptAnchor` returns a new instance with `trust_outcome_passed` + `trust_outcome_confidence` set from `trust_outcome.passed` and `trust_outcome.confidence`. The receiver instance is **not** mutated.
- [ ] **AC-ATTACH-2.** Calling `attach_trust_outcome` on an instance whose `trust_outcome_passed is not None` (i.e., already attached) raises `ValueError("trust_outcome already attached")`. This makes the "Phase 5 retried but the anchor was already finalized" mistake fail loud.
- [ ] **AC-ATTACH-3.** Calling `attach_trust_outcome` on a refusal anchor (any `validator_outcome == "Refused"` value) raises `ValueError("cannot attach trust_outcome to a Refused anchor")` — refusal anchors never reach Phase 5 and any attach attempt is a bug upstream.
- [ ] **AC-EMIT-1.** `FallbackTier.run(...)` emits exactly one `AttemptAnchorRecorded` event per attempt (success or refused). Asserted by a `Counter(type(e).__name__ for e in events)["AttemptAnchorRecorded"] == 1` check inside the S6-01 ten-event-tape test, extended to eleven events.
- [ ] **AC-ORDER-1.** Anchor event is the *new terminal event* of S6-01's per-step tape (index 10 in 0-based ordering). The S6-01 tape test's `EXPECTED_EVENT_COUNT_PER_BRANCH` constant updates from 10 → 11 across all four branches. Anchor follows `PlanOutcomeEmitted` (the previous terminal); nothing follows the anchor in the same attempt frame.
- [ ] **AC-EMIT-2.** Anchor emission is unconditional — happy-path (after `TransformBuilt` + `PlanOutcomeEmitted`) and every refusal path (`Refused(PROVENANCE_NOT_APP_LAYER)`, `Refused(BUDGET_EXCEEDED)`, `Refused(LEAF_SCHEMA_VIOLATION)`, `Refused(LEAF_REFUSED)`) emit. Refusal anchors set `trust_outcome_passed=None` and `trust_outcome_confidence=None`.
- [ ] **AC-RAG-1.** `retrieved_evidence_chain_head` correctness — when `bool(prior_attempts) is True` (retry path, ADR-04-0011), `retrieved_evidence_chain_head is None` and `retrieved_record_ids == ()`. When RAG returns `RagMiss`, both are also empty. Asserted by a parameterized test covering `{initial-hit, initial-degraded, initial-miss, retry-bypass}`.
- [ ] **AC-IDENTITY-1.** `workflow_id` equals the `workflow_id` of the enclosing `FallbackTier.run` invocation (passed via `RepoContext` or an explicit constructor arg — implementer chooses; the existing S6-01 plumbing dictates which). `attempt_index == len(prior_attempts)` (initial=0; first retry=1; etc.). `attempt_id` is freshly minted per attempt (`uuid4()`) and never re-used. A parameterized test asserts all three across `{initial, retry-1, retry-2}`.

### Registry seam (extension by addition — CLAUDE.md commitment)

- [ ] **AC-REGISTRY-1.** `AttemptAnchorRecorded` carries `event_type: Literal["attempt_anchor_recorded"]` as a top-level discriminator field, matching every other member of `WorkflowInternalEvent` (`src/codegenie/plugins/events.py:476`).
- [ ] **AC-REGISTRY-2.** `AttemptAnchorRecorded` is added to **both** the `WorkflowInternalEvent` `Annotated[..., Field(discriminator="event_type")]` union and the `_INTERNAL_CLASSES: Final[tuple[type[BaseModel], ...]]` tuple in `src/codegenie/plugins/events.py`. Without both edits, `WorkflowEventLog.emit_internal(...)` raises `TypeError` at the isinstance gate (`events.py:769`).
- [ ] **AC-REGISTRY-3.** The Phase-4-side event registration is purely additive over S6-01's additions; the S6-07-mentioned `_INTERNAL_CLASSES` exhaustiveness fence (the one that walks the tuple for closed-set discipline) stays green.

### JSONL projection

- [ ] **AC-WRITER-1.** `src/codegenie/fallback/anchor_writer.py` exposes one function `write(anchor: AttemptAnchor, output_dir: Path) -> None` — pure I/O, no event-log writes. Implementation: `mkdir(parents=True, exist_ok=True, mode=0o700)` on `{output_dir}/{utc-date-yyyy-mm-dd}/`; `os.open(path, O_APPEND | O_CREAT | O_WRONLY, 0o600)`; write `anchor.model_dump_json().encode("utf-8") + b"\n"`; `os.fsync(fd)`; close.
- [ ] **AC-WRITER-2.** **Dispatch — refusal path.** `FallbackTier.run` calls `anchor_writer.write(anchor, output_dir=...)` **inside** the `run` frame *before* returning, for every refusal branch (`PROVENANCE_NOT_APP_LAYER`, `BUDGET_EXCEEDED`, `LEAF_REFUSED`, `LEAF_SCHEMA_VIOLATION`). The anchor's `trust_outcome_*` fields are `None` because Phase 5 never sees refusals.
- [ ] **AC-WRITER-3.** **Dispatch — success path.** `FallbackTier.run` emits the `AttemptAnchorRecorded` event but does **not** write the JSONL itself. The anchor instance flows to the existing `FallbackTier.on_validated(outcome, trust)` hook (S6-03) via in-memory state on the `FallbackTier` instance (keyed by `attempt_id` so multi-attempt workflows do not collide). `on_validated` (or its Phase 5 callsite in `src/codegenie/gates/runner.py`) calls `attached = anchor.attach_trust_outcome(trust)`, then `anchor_writer.write(attached, output_dir=...)`. The Phase-5-side change is exactly two lines (`attach_trust_outcome` + `write`), purely additive.
- [ ] **AC-WRITER-4.** **Append, never truncate** — two successive `write(...)` calls on the same `(utc-date, workflow_id)` produce a two-line file; line 1 byte-equals the first write's serialization; line 2 byte-equals the second's. Asserted by reading the file back and parsing each line as `AttemptAnchor` via `pydantic.TypeAdapter`.
- [ ] **AC-WRITER-5.** **Permissions** — directory mode `0o700` (operator-only); file mode `0o600`. Asserted by `path.stat().st_mode & 0o777 == 0o700` and `0o600` respectively. Set explicitly via `os.open(..., mode=0o600)` and `mkdir(..., mode=0o700)`; the test runs under a deliberately-permissive umask (`os.umask(0)` in fixture) to prove `mode=` was passed, not inherited.
- [ ] **AC-WRITER-6.** **JSON round-trip stability** — `pydantic.TypeAdapter[AttemptAnchor].validate_json(line) == anchor` for every line written. Pins schema-shape stability for future critic-training consumers.

### Fence tests

- [ ] **AC-FENCE-1.** `tests/fence/test_attempt_anchor_is_terminal_event.py` — AST walk over `src/codegenie/fallback/tier.py` confirms no `event_log.emit_internal(...)` call follows an `AttemptAnchorRecorded` emission in any control-flow branch (uses the established `tests/fence/` AST-walk pattern from S6-01/S6-02). Plus a runtime assertion: `FallbackTier` carries a per-attempt boolean `_anchor_emitted_for_attempt: dict[AttemptId, bool]`; emitting any other event after the anchor on the same `attempt_id` raises `AnchorTerminalEventViolation`.
- [ ] **AC-FENCE-2.** `tests/fence/test_attempt_anchor_schema_version.py` — pins `AttemptAnchor.model_fields["schema_version"].annotation == Literal[1]` AND `AttemptAnchor.model_fields["schema_version"].default == 1`. A bump to 2 requires editing this fence test AND landing a `tests/integration/test_attempt_anchor_v1_v2_coexist.py` (which does not exist today — the fence test refuses to permit the bump until the coexistence test exists; checked by `git ls-files`). This makes the "one release cycle of coexistence" rule machine-enforced, not norm-enforced.
- [ ] **AC-FENCE-3.** `tests/fence/test_attempt_anchor_plan_kind_matches_proposal.py` — AST walks `PlanProposal`'s discriminated union in `src/codegenie/fallback/plan_proposal.py` and asserts `set(AttemptAnchor.model_fields["plan_proposal_kind"].annotation.__args__) == set(PlanProposal discriminator values)`. Without this, adding a 5th `PlanProposal` variant in Phase 7 silently drifts the anchor.
- [ ] **AC-EXTRAS-1.** `extras` is namespaced — a Pydantic `field_validator("extras")` rejects keys not matching `^phase\d+(?:\.\d+)?\.[a-z][a-z0-9_]*$`. Asserted by `tests/unit/fallback/test_attempt_anchor_extras_namespace.py` *and* a Hypothesis property test (`tests/property/test_attempt_anchor_extras_property.py`) that draws strings from `from_regex(r"^phase\d+(\.\d+)?\.[a-z][a-z0-9_]*$")` (accepted) vs strings drawn from `text(alphabet=characters(blacklist_categories=["Cs"]))` and asserts the regex matchers agree.

### Phase 5 deferred-attach hook

- [ ] **AC-PHASE5-1.** A two-line additive change to `src/codegenie/gates/runner.py`'s success-path validator block: `attached = anchor.attach_trust_outcome(trust)` then `anchor_writer.write(attached, output_dir=anchor_output_dir)`. The `anchor` value is recovered from the per-attempt state on the shared `FallbackTier` instance keyed by `attempt_id` (the `on_validated` hook receives `outcome` which carries `attempt_id` — implementer adds the field to `PlanOutcome.AppliedFromLlm` / `AppliedFromRecipe` if not already present; S6-03 should already carry it). The Phase-5-side change is purely additive — no edits to `GateRunner.__init__` signature, no new constructor arg, no contract widening. The story does **not** ship a cross-phase ADR; the executor records the contract crossing in `_attempts/S6-08.md`.
- [ ] **AC-PHASE5-2.** If `src/codegenie/gates/runner.py` does not yet exist (Phase 5 partially built at execution time), the executor **stops, surfaces the gap, and does not invent the file**. The Depends-on chain assumes Phase 5's `GateRunner` is in place via S5-02; if not, treat as `BLOCKED` and log to `_attempts/S6-08.md`.

### Quality gates + closeout

- [ ] **AC-QG-1.** `mypy --strict` clean on `src/codegenie/fallback/attempt_anchor.py`, `src/codegenie/fallback/anchor_writer.py`, and every new test module. No `Any`. No untyped dict shuffling.
- [ ] **AC-QG-2.** `ruff check`, `ruff format --check`, `make typecheck`, `make test`, `make lint-imports`, `make fence` all green.
- [ ] **AC-QG-3.** Story file status flipped `HARDENED` → `Done` after the executor verifies; updates `docs/phases/04-vuln-llm-fallback-rag/stories/README.md` Step 6 to reflect S6-08 as the new last story in the step.

## Implementation outline

1. **New module `src/codegenie/fallback/attempt_anchor.py`** — `AttemptAnchor` Pydantic model per ADR-04-0017 §Decision with the AC-SCHEMA-1 `Optional` clarification for the five LLM-call-derived fields. Module-private `AttemptAnchorBuilder` (single-use; do *not* export — Rule 2: first use, do not extract) instantiated at `FallbackTier.run` entry; accumulates fields as the pipeline progresses; finalizes via `.build() -> AttemptAnchor` before emission. Field validators: tz-aware UTC timestamp (AC-SCHEMA-2), `Decimal`-as-string `cost_usd` (AC-SCHEMA-3), `MappingProxyType({})`-default `extras` (AC-SCHEMA-4), namespace-regex `extras` keys (AC-EXTRAS-1).
2. **New event type `AttemptAnchorRecorded`** — same module *or* `src/codegenie/plugins/events.py` (implementer's choice; the latter matches the established Phase-1/2/3 event-class location). Carries `event_type: Literal["attempt_anchor_recorded"]`, `event_id: EventId`, `workflow_id: WorkflowId`, `timestamp: datetime`, `anchor: AttemptAnchor`. Register in `WorkflowInternalEvent` discriminated union AND `_INTERNAL_CLASSES` tuple (AC-REGISTRY-1..-3).
3. **Wire emission in `src/codegenie/fallback/tier.py`** — at the end of `run`, after `PlanOutcomeEmitted` (the S6-01 terminal event), call `event_log.emit_internal(AttemptAnchorRecorded(anchor=builder.build(), ...))`. Refusal branches do the same (each refusal branch already emits `PlanOutcomeEmitted` per S6-01, then the anchor). The `FallbackTier` instance gains a `_pending_anchors: dict[AttemptId, AttemptAnchor]` field guarded by an `asyncio.Lock` (Phase 4 is single-loop but the field is shared across `.run()` and `.on_validated()` calls — surface this in `_attempts/` if S6-01's `FallbackTier` shape rejected adding the field).
4. **Dispatch — refusal anchor write inside `FallbackTier.run`** — for every `Refused(...)` branch, after the anchor event is emitted, call `anchor_writer.write(anchor, output_dir=self._anchor_output_dir)`. The anchor's `trust_outcome_*` are `None`.
5. **Dispatch — success anchor write in `FallbackTier.on_validated`** — `on_validated(outcome, trust)` recovers the pending anchor via `self._pending_anchors.pop(outcome.attempt_id)`, calls `attached = anchor.attach_trust_outcome(trust)`, then `anchor_writer.write(attached, output_dir=self._anchor_output_dir)`. (If S6-03's `on_validated` is owned by Phase 5's `GateRunner` rather than `FallbackTier` itself, this logic lives in `src/codegenie/gates/runner.py`'s success-path validator block — AC-PHASE5-1.)
6. **JSONL writer** `src/codegenie/fallback/anchor_writer.py` — `def write(anchor: AttemptAnchor, output_dir: Path) -> None`. Single function, not a class (single call surface — Rule 2). Implementation: `(output_dir / utc_date_str).mkdir(parents=True, exist_ok=True, mode=0o700)`; `fd = os.open(file_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, mode=0o600)`; `os.write(fd, anchor.model_dump_json().encode("utf-8") + b"\n")`; `os.fsync(fd)`; `os.close(fd)`. No `Path.write_text` — that family does not let you pass `mode=` on creation and is umask-sensitive.
7. **Fence tests** — three `tests/fence/` modules (terminal-event AST walk + runtime assertion; schema-version pin gated by coexistence-test existence; `plan_proposal_kind` ↔ `PlanProposal` exhaustiveness) plus unit + property tests under `tests/unit/fallback/` and `tests/property/`.
8. **Update `docs/phases/04-vuln-llm-fallback-rag/stories/README.md`** — Step 6 manifest table already references S6-08; verify the entry's "Done" status flips correctly.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/fallback/test_attempt_anchor_emission.py`

```python
# tests/unit/fallback/test_attempt_anchor_emission.py
async def test_fallback_tier_emits_attempt_anchor_last_on_happy_path(
    fallback_tier_with_fakes: FallbackTier,
    capturing_event_log: list[WorkflowInternalEvent],
    happy_path_inputs: HappyPathFixture,
) -> None:
    """
    Per ADR-04-0017 + AC-ORDER-1: AttemptAnchorRecorded is the new terminal
    event of S6-01's per-step tape (index 10), emitted *after* PlanOutcomeEmitted.
    A future critic-training pipeline reads the JSONL projection of these anchors;
    if any event fires after the anchor in the same attempt, the projection is
    incomplete and the replay guarantee is broken. This test would FAIL on a
    naive (and wrong) implementation that emits the anchor before PlanOutcomeEmitted
    OR that emits a second event after the anchor.
    """
    await fallback_tier_with_fakes.run(
        happy_path_inputs.advisory,
        happy_path_inputs.repo_ctx,
        happy_path_inputs.recipe_selection,
        prior_attempts=(),
    )
    # arrange: capturing_event_log fixture replays the internal stream in append order
    kinds = [type(e).__name__ for e in capturing_event_log]
    # assert: anchor count exactly one (mutation-resistant: a "for x in ...: emit" bug
    # that emits twice would fail here, not at some downstream consumer).
    assert Counter(kinds)["AttemptAnchorRecorded"] == 1, kinds
    # assert: anchor is index 10; PlanOutcomeEmitted is index 9 (terminal pre-anchor).
    assert kinds.index("AttemptAnchorRecorded") == 10, kinds
    assert kinds[9] == "PlanOutcomeEmitted", kinds
    assert kinds[-1] == "AttemptAnchorRecorded", kinds  # terminal
    # assert: anchor carries the joined tuple (intent, not just "non-None")
    anchor = next(e for e in capturing_event_log if type(e).__name__ == "AttemptAnchorRecorded").anchor
    assert anchor.schema_version == 1
    assert anchor.workflow_id == happy_path_inputs.expected_workflow_id  # AC-IDENTITY-1
    assert anchor.attempt_index == 0  # initial attempt
    assert anchor.validator_outcome == "AppliedFromLlm"
    assert anchor.plan_proposal_kind in set(get_args(PlanProposal.__discriminator_args__))  # AC-SCHEMA-5
    assert anchor.retrieved_evidence_chain_head is not None  # happy path = RAG ran
    assert anchor.retrieved_record_ids != ()
    assert anchor.trust_outcome_passed is None  # Phase 5 has not attached on the in-process anchor
    assert anchor.tokens_in is not None and anchor.tokens_in > 0  # LLM was invoked
    assert anchor.cost_usd is not None
    assert anchor.timestamp_utc.tzinfo is not None  # AC-SCHEMA-2
```

The test must fail because `attempt_anchor.py` doesn't exist yet, `FallbackTier` doesn't emit the event yet, `AttemptAnchorRecorded` isn't registered in `WorkflowInternalEvent`, and `capturing_event_log` won't surface a type that fails the `isinstance` gate in `emit_internal`. `ImportError` *or* `TypeError` at first run is the expected red failure.

Additional red tests to land in the same commit (each fails for the same `ImportError`/`TypeError` reason — the suite is one cohesive red wave):

- **`test_attempt_anchor_on_refusal_paths`** — `@pytest.mark.parametrize("refusal_kind", ["PROVENANCE_NOT_APP_LAYER", "BUDGET_EXCEEDED", "LEAF_REFUSED", "LEAF_SCHEMA_VIOLATION"])`; for each, asserts (a) exactly one anchor emitted, (b) `validator_outcome == "Refused"`, (c) `refusal_reason == refusal_kind`, (d) `trust_outcome_passed is None`, (e) early-refusal kinds (`PROVENANCE_NOT_APP_LAYER`, `BUDGET_EXCEEDED`) have `tokens_in is None` and `cost_usd is None`, (f) post-LLM refusal kinds (`LEAF_REFUSED`, `LEAF_SCHEMA_VIOLATION`) have `tokens_in is not None`.
- **`test_retrieved_evidence_chain_head_none_on_retry`** — non-empty `prior_attempts` ⇒ `retrieved_evidence_chain_head is None and retrieved_record_ids == ()`. Asserts `attempt_index == len(prior_attempts)`.
- **`test_attempt_id_is_per_attempt_unique`** — run two attempts back-to-back on the same `FallbackTier` instance with the same workflow_id; assert `anchor_attempt_1.attempt_id != anchor_attempt_2.attempt_id` AND `attempt_index_1 == 0`, `attempt_index_2 == 1`.
- **`test_extras_namespace_validator`** — `extras={"foo": "bar"}` raises `ValidationError`; `extras={"phase7.distroless_target": "cgr.dev/alpha"}` succeeds; `extras={"phase07.x": "y"}` raises (no zero-pad — fail loud on inconsistent phase numbering).
- **`test_extras_default_is_immutable_proxy`** — `anchor = AttemptAnchor(...)`; assert `isinstance(anchor.extras, MappingProxyType)`; `with pytest.raises(TypeError): anchor.extras["x"] = "y"`.
- **`test_attach_trust_outcome_returns_new_instance`** — call once; assert receiver is unchanged (`id(anchor) != id(attached)`); assert `attached.trust_outcome_passed == True`, `attached.trust_outcome_confidence == "high"`.
- **`test_attach_trust_outcome_double_attach_raises`** — call once, then again on the returned instance; assert `ValueError("trust_outcome already attached")`.
- **`test_attach_trust_outcome_on_refused_anchor_raises`** — build a refusal anchor; assert `ValueError("cannot attach trust_outcome to a Refused anchor")`.
- **`test_naive_timestamp_rejected`** — pass `datetime.now()` (naive); assert `ValidationError`.
- **`test_cost_usd_serializes_as_string`** — round-trip `model_dump_json()` → `json.loads(...)`; assert `type(parsed["cost_usd"]) is str` (or `is None`).
- **`test_plan_proposal_kind_matches_proposal_union`** (fence-test colocated with unit): asserts `set(AttemptAnchor.model_fields["plan_proposal_kind"].annotation.__args__) == set(p.model_fields["kind"].annotation.__args__[0] for p in PlanProposal.__args__)`.
- **`test_jsonl_projection_appended_with_correct_permissions`** — under `os.umask(0)`, run two refusal attempts on the same workflow; second-call read shows two lines; `dir.stat().st_mode & 0o777 == 0o700`; `file.stat().st_mode & 0o777 == 0o600`. Round-trip each line via `TypeAdapter[AttemptAnchor].validate_json(...)` and assert equality with the in-memory anchor.
- **`test_anchor_event_registered_in_internal_classes`** (registry seam): asserts `AttemptAnchorRecorded in _INTERNAL_CLASSES` and `emit_internal(AttemptAnchorRecorded(...))` does NOT raise `TypeError` (the existing isinstance gate must accept it).
- **Property test `test_extras_regex_property`** (`tests/property/test_attempt_anchor_extras_property.py`) — Hypothesis `from_regex(r"^phase\d+(\.\d+)?\.[a-z][a-z0-9_]*$", fullmatch=True)`-drawn keys MUST be accepted; `from_regex`-drawn-fullmatch=False keys that fail the regex MUST be rejected. Assert the validator's decision agrees with `re.fullmatch(...)` on 200 examples.

### Green — make it pass

The minimum implementation:

1. `src/codegenie/fallback/attempt_anchor.py` — `AttemptAnchor` Pydantic model (`Optional` LLM-derived fields per AC-SCHEMA-1) + module-private `AttemptAnchorBuilder` + `attach_trust_outcome` method + four field validators (tz-aware UTC, `Decimal`-as-string, `MappingProxyType` extras default, namespace-regex extras keys).
2. Event type `AttemptAnchorRecorded(BaseModel)` with `event_type: Literal["attempt_anchor_recorded"]` discriminator, registered in **both** `WorkflowInternalEvent` `Annotated[..., Field(discriminator="event_type")]` union AND `_INTERNAL_CLASSES: Final[tuple[...]]` tuple in `src/codegenie/plugins/events.py`.
3. `src/codegenie/fallback/anchor_writer.py` — single `write(anchor, output_dir)` function using `os.open(O_APPEND | O_CREAT | O_WRONLY, mode=0o600)` + `os.fsync` + `mkdir(mode=0o700)`. Not a class.
4. Modify `src/codegenie/fallback/tier.py` — instantiate builder at `run` entry; populate fields as pipeline progresses; emit anchor after `PlanOutcomeEmitted` in every branch; **refusal branches additionally call `anchor_writer.write(anchor, ...)` inside `run`**; happy-path leaves the anchor in `self._pending_anchors[attempt_id]` for `on_validated` to consume.
5. Modify `src/codegenie/fallback/tier.py`'s `on_validated` (or Phase 5's `src/codegenie/gates/runner.py` success-path validator block, per S6-03's seam): `anchor = self._pending_anchors.pop(outcome.attempt_id)`; `attached = anchor.attach_trust_outcome(trust)`; `anchor_writer.write(attached, output_dir=self._anchor_output_dir)`.

No new packages. No new dependencies. ~120 LOC production (model + builder + writer + tier wiring + events.py edits).

### Refactor — clean up

- Confirm `AttemptAnchor` is frozen and `extra="forbid"` (runtime test: `with pytest.raises(ValidationError): AttemptAnchor(..., not_a_field=1)`).
- Confirm `AttemptAnchorBuilder` is module-private (`_AttemptAnchorBuilder` or not in `__all__`).
- Confirm `extras` is `MappingProxyType` on default-construction (runtime test: `with pytest.raises(TypeError): anchor.extras["x"] = "y"`).
- Confirm the JSONL writer uses `os.O_CREAT | os.O_APPEND | os.O_WRONLY` with `mode=0o600` explicitly under `os.umask(0)`.
- Confirm S6-01's ten-event-tape test now expects eleven events; the `EXPECTED_EVENT_COUNT_PER_BRANCH = 10` constant must update to `11`, and the four `Refused` branch sub-tests must update similarly.
- Run `make check` and confirm the S6-07 determinism property still passes — the eleventh event is deterministic-by-construction (`attempt_id` is the only `uuid4()` call, seeded under cassette replay).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/attempt_anchor.py` | New — `AttemptAnchor` model + module-private `_AttemptAnchorBuilder` + `attach_trust_outcome` method + four field validators (tz-aware UTC, `Decimal`-as-string, `MappingProxyType` extras default, namespace-regex extras keys) |
| `src/codegenie/fallback/anchor_writer.py` | New — single `write(anchor, output_dir) -> None` function; `O_APPEND \| O_CREAT \| O_WRONLY` open with `mode=0o600`; `mkdir(mode=0o700)`; `os.fsync` per write |
| `src/codegenie/plugins/events.py` | Modify — define `AttemptAnchorRecorded` (with `event_type: Literal["attempt_anchor_recorded"]` discriminator); add to `WorkflowInternalEvent` `Annotated` union AND `_INTERNAL_CLASSES` tuple (AC-REGISTRY-1..-3). Purely additive — same shape as the other 16 `WorkflowInternalEvent` members |
| `src/codegenie/fallback/tier.py` | Modify — instantiate `_AttemptAnchorBuilder` at `run` entry; accumulate fields step by step; emit `AttemptAnchorRecorded` after `PlanOutcomeEmitted` in every branch; refusal branches call `anchor_writer.write(...)` inside `run`; happy-path stores anchor in `self._pending_anchors[attempt_id]` for `on_validated` to consume |
| `src/codegenie/gates/runner.py` (Phase 5's actual path — *plural* `gates`, not `gate`; matches [S5-02](../../05-sandbox-trust-gates/stories/S5-02-gate-runner-retry-loop.md)) | Modify (success-path validator block) — two lines: `attached = anchor.attach_trust_outcome(trust)`; `anchor_writer.write(attached, output_dir=...)`. Only edit if S5-02 has shipped; otherwise BLOCKED per AC-PHASE5-2 |
| `tests/unit/fallback/test_attempt_anchor_emission.py` | New — TDD red tests (anchor terminal + per-branch refusal + retry bypass + identity correctness + extras namespace + extras immutability + idempotency-violation + double-attach + naive-timestamp + cost-stringification + JSONL round-trip + registry-seam + plan_proposal_kind discriminator) |
| `tests/property/test_attempt_anchor_extras_property.py` | New — Hypothesis property test against the `extras` namespace regex (200 examples; matcher agreement with `re.fullmatch`) |
| `tests/fence/test_attempt_anchor_is_terminal_event.py` | New — AST walk over `src/codegenie/fallback/tier.py` (no `event_log.emit_internal(...)` follows an `AttemptAnchorRecorded` emission in any control-flow branch) + runtime assertion on the `FallbackTier._anchor_emitted_for_attempt: dict[AttemptId, bool]` field |
| `tests/fence/test_attempt_anchor_schema_version.py` | New — pins `schema_version == 1`; coexistence-test-existence gate refuses to permit a bump until `tests/integration/test_attempt_anchor_v1_v2_coexist.py` exists (`git ls-files`-checked) |
| `tests/fence/test_attempt_anchor_plan_kind_matches_proposal.py` | New — AST-walk fence pinning `Literal[...]` members of `plan_proposal_kind` against `PlanProposal`'s discriminated union tags |
| `tests/unit/fallback/test_attempt_anchor_tape_extension.py` | Modify or extend S6-01's existing ten-event-tape test — `EXPECTED_EVENT_COUNT_PER_BRANCH` goes 10 → 11; anchor expected at index 10 across all four branches |
| `docs/phases/04-vuln-llm-fallback-rag/stories/README.md` | Modify — flip S6-08's status to Done on closeout (the row already exists per `docs/.../stories/README.md:186`) |

## Out of scope

- **Critic training, critic inference, comparator selection.** This story preserves the *option* of CTRL-style critic training; it does not implement any critic. The orchestration survey memo Tier 2 / Tier 3 rows describe what comes later and explicitly defer until Phase 4 has runtime evidence.
- **Reading the JSONL anywhere.** No production code consumes the anchors in Phase 4; the only consumer in this story is the unit/fence tests. Phase 7 / Phase 15 / future critic-training consumers will add read paths under their own ADRs.
- **Cross-stream join with Phase 5's event stream.** Phase 5 attaches `TrustOutcome` to the same `AttemptAnchor` instance via `attach_trust_outcome`; no projection joins the Phase 4 and Phase 5 streams in this story. The join *primitive* is the `workflow_id` + `attempt_index` pair; a downstream consumer doing analytics work owns the join.
- **Anchor retention enforcement.** Anchors fall under ADR-0040's audit-trail class; Phase 14's data-lifecycle worker enforces the 90-day-hot / cold-storage policy. This story writes the data; the lifecycle worker reads it.
- **`schema_version=2` migration plan.** When (and if) anchors gain a non-`extras` field, a follow-up ADR will document the co-existence-release-cycle rule and the migration test.

## Notes for the implementer

- **The anchor is the *last* event per attempt — this is a load-bearing invariant.** The fence test enforces it because the JSONL projection's "one line per attempt" promise depends on it. Any future feature that wants to emit a post-anchor event must restructure (e.g., emit *before* anchor, or introduce a `PostAttemptAnchorRecorded` event with its own schema versioning).
- **The split write-site dispatch (refusal-in-`run` vs success-in-`on_validated`) is the load-bearing architectural choice this hardening pinned.** ADR-04-0017's "anchor emission is unconditional" Consequence demanded that refusals get anchors; the deferred-attach hook demands that success-path JSONL be written *after* Phase 5 attaches trust. These two requirements force two write sites. Both call the same `anchor_writer.write(...)` adapter — one file shape, two callers. Resist the urge to "simplify" by writing all anchors in `run` (success-path trust would be `None` forever) or by writing all anchors in `on_validated` (refusals never reach there).
- **The five LLM-call-derived fields are `Optional` in `schema_version=1`.** ADR-04-0017 §Decision's shape elides the `| None` for brevity; the AC-SCHEMA-1 clarification is consistent with the ADR's "anchor emission is unconditional" Consequence (early-refusal anchors cannot populate prompt/response digests). Surface this as an ADR-04-0017 §Decision-text-clarification in the executor's `_attempts/S6-08.md` (not a new ADR — this is a clarification of an existing one, gated by the schema_version=1 fence).
- **Newtype opportunity — `AttemptId`.** This anchor introduces `attempt_id: UUID` as the third domain identifier in Phase 4 (after `WorkflowId` and `AdvisoryId`). Per CLAUDE.md "Newtype identifiers" load-bearing commitment, `AttemptId = NewType("AttemptId", UUID)` (or a `class AttemptId(UUID)` smart-constructor pattern matching `codegenie.types.identifiers`) is now warranted — three call sites is the rule-of-three threshold. Land the newtype in `src/codegenie/types/identifiers.py` and use it across the anchor module + builder + writer + the `FallbackTier._pending_anchors` dict key. If S6-01 has already shipped `AttemptId`, just consume it.
- **`AttemptAnchorBuilder` stays file-private (first use — Rule 2).** Do not export. Do not generalize. If a future story needs a second "accumulate-as-we-go" event builder for some other domain, that will be the second use — the kernel-extract conversation happens then, not now.
- **`anchor_writer.write` stays a single function (single call surface — Rule 2).** Do not wrap in a class. Do not make it an injectable dependency on `FallbackTier`. The two callers (`tier.py` refusal branches; `gates/runner.py` success block) import the function directly. If a third call site emerges (Phase 7 distroless extending the anchor write path), revisit.
- **`extras` is string-valued only.** Resist the urge to allow `Mapping[str, Any]`. Stable JSON shape matters more than ergonomics; consumers can parse string values on read.
- **`extras` keys are namespaced** by phase prefix (`phase7.*`, `phase15.*`). The validator regex enforces this so consumer phases cannot collide. No zero-padding (`phase07.x` is rejected) — pinning the format prevents the silent-drift bug where one phase writes `phase7.x` and another writes `phase07.x`.
- **`AttemptAnchor.attach_trust_outcome` is functional, not mutating.** Returns a new frozen instance. This matches the frozen-by-default Pydantic discipline (ADR-0033). Double-attach raises (Phase 5 retry that re-enters this path is a bug Phase 5 must avoid).
- **The JSONL file's directory mode is `0o700`** (operator-only). The file is `0o600`. Both must be set explicitly via `mkdir(mode=...)` and `os.open(..., mode=...)` — do not rely on umask (test asserts the mode under `os.umask(0)` to prove explicit passing).
- **Phase 5's two-line addition is *not* a separate cross-phase ADR.** Phase 5's `GateRunner` lives at `src/codegenie/gates/runner.py` (plural — matches S5-02 shipped path; the story originally said `src/codegenie/gate/runner.py` singular, which was a typo). The hook is purely additive (two method calls in the success-path validator block). If the executor finds the Phase 5 seam is not where this story expects, surface the gap and pause — do *not* refactor Phase 5 inside this story; treat as `BLOCKED` per AC-PHASE5-2.
- **Registry seam (extension-by-addition):** The event log adapter (`src/codegenie/plugins/events.py`'s `WorkflowEventLog`) gates `emit_internal(...)` calls on `isinstance(event, _INTERNAL_CLASSES)` (`events.py:769`). Forgetting to register `AttemptAnchorRecorded` in both the `WorkflowInternalEvent` `Annotated` union AND the `_INTERNAL_CLASSES` tuple yields a `TypeError` at first emission. This is the same seam S6-01 uses for the ten new Phase 4 events; treat AttemptAnchorRecorded as the eleventh and follow the established pattern.
- **The schema_version=1 pin is the dam.** Any pressure to bump to 2 in the future must come with: (a) a Phase 4 ADR amendment, (b) a co-existence release cycle test (`tests/integration/test_attempt_anchor_v1_v2_coexist.py`), (c) a documented migration path for the JSONL projection. The fence test's `git ls-files`-existence-gate exists to make that pressure machine-enforced, not norm-enforced.
- **`plan_proposal_kind` ↔ `PlanProposal` discriminator must stay synchronised.** ADR-04-0017 §Decision's `"apply_recipe" | "apply_transform" | "request_human" | "refuse"` example was illustrative; the *actual* `PlanProposal` variants are `dep_bump`, `override`, `callsite_rewrite`, `refuse` per phase-arch §Component 2. The new fence (`tests/fence/test_attempt_anchor_plan_kind_matches_proposal.py`) keeps these synced. When Phase 7 adds a 5th `PlanProposal` variant, the fence fails until the anchor's `Literal[...]` is widened — extension-by-addition, machine-enforced.
- **Storage cost is real.** ~1.5 KB per attempt × ~3 attempts/workflow × portfolio-scale. At 10K workflows/day that's ~45 MB/day, ~16 GB/year hot. Acceptable per ADR-0040 retention; document it in the runbook the closeout story (S7-10) ships.
- **Determinism interaction with S6-07.** The eleventh-event extension breaks the existing 10-event tape expectation in the S6-07 determinism property. The `attempt_id: uuid4()` call is the only new source of non-determinism in the anchor; under cassette replay (S6-07's setup), `uuid4` must be seeded by the same fixture S6-07 uses, or `attempt_id` must move into the `_strip_nondet(event)` canonical-bytes stripper. Surface the choice in `_attempts/S6-08.md` — do not silently break S6-07.
