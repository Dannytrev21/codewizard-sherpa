# Validation report — S6-08 `AttemptAnchor` event emission + JSONL projection

**Validated:** 2026-05-24
**Validator:** phase-story-validator (scheduled story-validation-corrector run)
**Verdict:** **HARDENED**
**Findings:** 8 block · 14 harden · 3 nit — all resolved in place

---

## Stage 1 — Context Brief

### Story snapshot
- **Goal (verbatim original):** `FallbackTier.run(...)` emits exactly one `AttemptAnchorRecorded(anchor: AttemptAnchor)` event per attempt (success or refused), and the anchor is persisted as one JSONL line at `.codegenie/fallback/anchors/{utc-date}/{workflow_id}.jsonl` (mode `0600`, fsync per write) carrying every field in ADR-04-0017's schema. Phase 5's `GateRunner` invokes `anchor.attach_trust_outcome(...)` before the line is fsync'd.
- **Phase exit criteria touched:** Phase-arch §Goal G2 (Phase-5 contract preserved); High-level-impl Step 6 "Done" criterion includes audit-anchor write (line 217); `tests/golden/events/attempt_anchor.{success,refusal}.jsonl` byte-equality fence (line 218); Phase 6.5 bench replay reads this schema; Phase 7 / Phase 15 / future critic-training consumers depend on `schema_version=1` stability.

### Authoritative ADRs
- **ADR-04-0017** — `AttemptAnchor` event schema; the dam. Schema is `frozen=True, extra="forbid"`; `schema_version=Literal[1]`; `extras` is the namespaced extension slot; persistence to JSONL.
- **ADR-04-0002** — Named-sequential pipeline; "chain order is the policy"; the new anchor event is the new terminal of that chain — purely additive.
- **ADR-04-0011** — RAG bypass on retry; `retrieved_evidence_chain_head` MUST be `None` and `retrieved_record_ids` MUST be `()` when `prior_attempts != []`.
- **Production ADR-0034** — Append-only event sourcing; no in-place mutation.
- **Production ADR-0040** — Retention class for audit trails; 90-day hot minimum.
- **Production ADR-0008** — `TrustOutcome` shape Phase 5 attaches (`passed`, `confidence`).

### Sibling-story lineage (Design-Patterns + Test-Quality carry-forward)
- **S6-01 (HARDENED, not yet GREEN)** — ten-event-per-branch tape; `Sequence[AttemptSummary] = ()` signature (no list-literal default); `_INTERNAL_CLASSES` registry walk for closed-set discipline. **S6-08 makes the tape eleven events.**
- **S6-02 (HARDENED)** — retry-bypass branch; `bool(prior_attempts)` truthiness predicate (not `!= []`). **S6-08's AC-RAG-1 must match this predicate exactly.**
- **S6-03** — `on_validated` hook; **the host for the deferred JSONL write on the success path.**
- **S6-07 (HARDENED)** — determinism property at 50 runs across all four branches; `EXPECTED_EVENT_COUNT_PER_BRANCH = 10`. **S6-08 must update this constant to 11 and seed `attempt_id: uuid4()` under cassette replay.**
- **S5-02 (Phase 5, HARDENED)** — `GateRunner` lives at `src/codegenie/gates/runner.py` (plural). The original S6-08 typo was `src/codegenie/gate/runner.py` (singular).

### Shipped / declared contracts the story must not contradict
- `WorkflowEventLog.emit_internal(event)` is the actual API (not `event_log.append(event)`); gated by `isinstance(event, _INTERNAL_CLASSES)` at `src/codegenie/plugins/events.py:769`.
- `WorkflowInternalEvent = Annotated[..., Field(discriminator="event_type")]` — every member carries an `event_type: Literal[...]` discriminator field.
- `_INTERNAL_CLASSES: Final[tuple[type[BaseModel], ...]]` — closed-set tuple walked by exhaustiveness fences.
- `FallbackTier.run(advisory, repo_ctx, recipe_selection, *, prior_attempts: Sequence[AttemptSummary] = ()) -> RecipeApplication` — Phase 5's merged signature; story cannot widen.
- `RecipeApplication` is Phase 3's type; cannot widen with the anchor (final-design.md line 176 — "Phase 7's exit criterion forbids the widening").
- `PlanProposal` discriminator tags: `dep_bump`, `override`, `callsite_rewrite`, `refuse` (per phase-arch §Component 2). ADR-04-0017 §Decision's `apply_recipe | apply_transform | request_human | refuse` example was illustrative; the *actual* tags are PlanProposal's.

### Phase / arch constraints
- **CLAUDE.md** load-bearing commitments: "Newtype identifiers" (`AttemptId` newtype is now warranted at the rule-of-three threshold — `WorkflowId`, `AdvisoryId`, `AttemptId`); "Extension by addition" (`AttemptAnchorRecorded` registers in existing `WorkflowInternalEvent` union + `_INTERNAL_CLASSES` tuple, no edits to the existing event types); "Functional core / imperative shell" (anchor model is pure data + validators; writer is the imperative shell; `attach_trust_outcome` returns a new frozen instance).
- **Global Rule 2** — Simplicity. `_AttemptAnchorBuilder` is single-use → stay file-private. `anchor_writer.write` is two-caller-only → single function, not a class.
- **Global Rule 8** — Read before you write. The original story prescribed `event_log.append(...)` and `src/codegenie/gate/runner.py` — both contradicted the actual codebase (`emit_internal` and `src/codegenie/gates/` plural).
- **Global Rule 9** — Tests verify intent, not behavior. Refusal-path tests must distinguish early-refusal (no LLM call) from post-LLM refusal (`LEAF_REFUSED` / `LEAF_SCHEMA_VIOLATION`) so the test would catch a "set everything to None on every refusal" mistake.
- **Global Rule 12** — Fail loud. Naive-timestamp rejected (not silently coerced to UTC); double-attach raises (not silently no-op); refusal-anchor attach raises; `phase07.x` rejected (no zero-pad normalization).

### Pre-existing state on disk (gap analysis at validation time)
- `src/codegenie/fallback/` does NOT exist yet — S6-01..S6-06 are HARDENED (story-level) but not GREEN.
- `src/codegenie/gates/` does NOT exist yet — Phase 5 stories are HARDENED but `GateRunner` (S5-02) is not yet shipped.
- `src/codegenie/plugins/events.py` DOES exist and DOES carry `WorkflowInternalEvent` + `_INTERNAL_CLASSES` (current shape: 16 internal event types from Phases 1–3; S6-01 will add 10 Phase-4 events; S6-08 adds the 11th as `AttemptAnchorRecorded`).
- `src/codegenie/types/identifiers.py` exists; `AttemptId` newtype is NOT yet defined.

**Implication:** S6-08 has hard deps on S6-01 (event types + ten-event tape) and S5-02 (GateRunner). If executed before either, the executor must mark `BLOCKED` and log to `_attempts/S6-08.md`.

### Open ambiguities (Stage 1 exit gate)
Two surfaced, both resolved by the synthesizer (no user intervention needed):

1. **JSONL-write-timing dispatch (refusal vs success).** ADR-04-0017's "anchor emission is unconditional" + "Phase 5 attaches before the anchor is persisted" combine to force two write sites. The original story did not name this split. → Resolved by AC-WRITER-1..-3 (refusal in `run`, success in `on_validated`; one writer module shared).
2. **Required-field contradiction with early refusals.** ADR-04-0017 §Decision spells five LLM-derived fields without `| None`, but PROVENANCE_NOT_APP_LAYER and BUDGET_EXCEEDED refusals never invoke the LLM. → Resolved by AC-SCHEMA-1 making them Optional in `schema_version=1` — a *clarification* of ADR-04-0017's Consequence ("anchor emission is unconditional"), not a schema bump. The executor records the clarification in `_attempts/S6-08.md`.

→ Proceeded to Stage 2.

---

## Stage 2 — Critic findings

### Critic — Coverage (verdict: block + harden)

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | block | JSONL write timing for success-vs-refusal paths is undefined. ADR-04-0017 says "Phase 5 attaches before persistence" but Phase 5 only sees success paths; refusals must persist *somewhere*. The original story conflates the two. | AC-WRITER-1..-3 split: refusal-in-`run` (trust=None), success-in-`on_validated` (after `attach_trust_outcome`). Same writer. |
| 2 | block | Required fields (`prompt_digest_blake3`, `response_digest_blake3`, `tokens_in`, `tokens_out`, `cost_usd`) cannot be populated on early refusals (PROVENANCE_NOT_APP_LAYER, BUDGET_EXCEEDED). Schema with `extra="forbid"` + non-optional required = construction fails. | AC-SCHEMA-1 makes these `T \| None` in `schema_version=1`; refusal-path tests distinguish early-refusal (None) from post-LLM refusal (non-None). |
| 3 | block | The story says anchor follows `TransformBuilt` / `Refused`, but S6-01's ten-event tape ends in `PlanOutcomeEmitted` (event index 9). Where does anchor go relative to `PlanOutcomeEmitted`? | AC-ORDER-1 pins anchor at index 10; tape grows 10 → 11; S6-01's `EXPECTED_EVENT_COUNT_PER_BRANCH` updates. |
| 4 | block | `plan_proposal_kind: Literal["apply_recipe", "apply_transform", "request_human", "refuse"]` (story line 110) does not match `PlanProposal`'s actual discriminator tags (`dep_bump`, `override`, `callsite_rewrite`, `refuse`). Silent drift between anchor and proposal. | AC-SCHEMA-5 + AC-FENCE-3 force the literal members to match `PlanProposal`'s tags via AST-walk fence. |
| 5 | harden | Identity fields not tested — `workflow_id`, `attempt_index`, `attempt_id` correctness uncovered. | AC-IDENTITY-1 + parameterized test. |
| 6 | harden | `timestamp_utc` tz-aware enforcement not asserted. | AC-SCHEMA-2 + naive-datetime rejection test. |
| 7 | harden | `cost_usd: Decimal` JSON serialization stability (string, not float) uncovered. | AC-SCHEMA-3 + round-trip test. |
| 8 | harden | Refusal paths not differentiated — story treats all four refusals identically; early vs post-LLM is a load-bearing distinction. | Parameterized `test_attempt_anchor_on_refusal_paths` with per-kind assertions on `tokens_in`/`cost_usd`. |
| 9 | harden | `extras` default-immutability not asserted. | AC-SCHEMA-4 + `MappingProxyType` test. |
| 10 | harden | `extras` namespace zero-padding undefined (`phase7` vs `phase07`). | AC-EXTRAS-1 + test asserting `phase07.x` is rejected; regex pinned. |

### Critic — Test Quality (verdict: harden)

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 11 | block | TDD test asserts `anchor_idx == len(events) - 1` — would pass with an empty event log AND would pass if anchor was emitted multiple times (only the *last* one counts). Mutation-fragile. | Rewrote to `Counter(kinds)["AttemptAnchorRecorded"] == 1` + index check at 10 + terminal check + `kinds[9] == "PlanOutcomeEmitted"`. Catches double-emit. |
| 12 | block | `assert anchor.retrieved_evidence_chain_head is not None` is tautological for the happy path because the schema makes it `Optional` — any implementation returning a non-None value passes. Doesn't verify intent ("RAG was actually consulted"). | Tightened to assert chain_head correctness against the RAG fixture's expected head; added `retrieved_record_ids != ()` cross-check. |
| 13 | harden | `extras` namespace tested with one positive + one negative example; misses fuzzed adversarial inputs. | Added Hypothesis property test (`tests/property/test_attempt_anchor_extras_property.py`) — 200 examples from `from_regex(...)`. |
| 14 | harden | JSONL projection test asserts permissions but not round-trip parseability. A bug serializing the wrong field shape would pass the permission check. | AC-WRITER-6 + JSONL round-trip via `TypeAdapter[AttemptAnchor].validate_json(...)`. |
| 15 | harden | Schema-version fence allows a hand-edit to `schema_version=2` with no enforcement. `models.lock`-style allowlist hand-waved. | AC-FENCE-2 — fence reads `git ls-files` and refuses to permit `schema_version=2` until `tests/integration/test_attempt_anchor_v1_v2_coexist.py` exists. Machine-enforced. |
| 16 | harden | Idempotency test ("double attach raises") is one-line; doesn't separate the "trust already attached" case from the "refusal anchor" case. The two failure paths share a method but should fail differently. | Split into AC-ATTACH-2 (double-attach on success anchor) and AC-ATTACH-3 (any attach on a refusal anchor). |
| 17 | harden | No mutation-resistance test for "tape order changed" — if anchor accidentally swapped with `PlanOutcomeEmitted`, the test only catches the terminal violation but not the order swap. | AC-ORDER-1's `kinds[9] == "PlanOutcomeEmitted"` + `kinds.index("AttemptAnchorRecorded") == 10` pins both positions. |
| 18 | harden | `umask` not zeroed in permission test — passes under typical umask 022 even if `mode=` was forgotten. | AC-WRITER-5 explicitly runs under `os.umask(0)`. |
| 19 | harden | No test for `attempt_id` uniqueness across retry attempts. | AC-IDENTITY-1's `test_attempt_id_is_per_attempt_unique`. |
| 20 | nit | Story TDD plan's example test uses `prior_attempts=[]` (list literal); S6-01/S6-02 hardened the signature to `Sequence[AttemptSummary] = ()`. | Updated to `prior_attempts=()`. |

### Critic — Consistency (verdict: block + harden)

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 21 | block | `src/codegenie/gate/runner.py` (singular) does not exist; Phase 5's actual path is `src/codegenie/gates/runner.py` (plural) per S5-02. The executor would not find the file. | Fixed Files-to-touch + Notes-for-implementer. Linked S5-02 for the canonical reference. |
| 22 | block | `event_log.append(AttemptAnchorRecorded(...))` is not the actual API. `WorkflowEventLog` exposes `emit_internal(event)` (gated by `isinstance(event, _INTERNAL_CLASSES)` at `events.py:769`) and `emit_spanning(event)`. | Fixed Implementation outline + TDD example to use `event_log.emit_internal(...)`. |
| 23 | block | Story silently omits the `AttemptAnchorRecorded` registry registration. Without adding it to both `WorkflowInternalEvent` and `_INTERNAL_CLASSES`, `emit_internal(...)` raises `TypeError`. | AC-REGISTRY-1..-3 + Files-to-touch row for `src/codegenie/plugins/events.py`. |
| 24 | block | Directory mode internal contradiction: AC says `mode 0600 on both directory and file`; Notes-for-implementer says `directory mode 0700`. `0600` on a directory is unreachable (no `+x`, cannot `cd`). | Aligned to `0o700` directory, `0o600` file (the Notes were correct; the AC was wrong). |
| 25 | harden | `WorkflowInternalEvent` members all carry `event_type: Literal[...]` discriminator; story's `AttemptAnchorRecorded(BaseModel)` sketch omits it. | AC-REGISTRY-1 makes the discriminator explicit. |
| 26 | harden | `prior_attempts: list[AttemptSummary] = []` (story line 94) contradicts the S6-01/S6-02 hardened signature `Sequence[AttemptSummary] = ()` (mutable default forbidden). | Test example updated. |
| 27 | harden | The `models.lock`-style allowlist referenced in AC-FENCE-2 (schema-version fence) does not exist in the codebase and the story doesn't ship it. | Replaced with a `git ls-files`-existence-gate on the v1↔v2 coexistence test path — machine-enforceable today. |
| 28 | harden | Story claims `~80 LOC production`; actual estimate after Optional fields, registry edits, builder, writer, two write sites, and `_pending_anchors` plumbing is closer to `~120 LOC`. | Updated estimate in Green block. |

### Critic — Design Patterns (verdict: harden + nit)

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 29 | harden | `AttemptId` is the third domain identifier in Phase 4 (after `WorkflowId`, `AdvisoryId`) — rule-of-three reached; CLAUDE.md "Newtype identifiers" commitment now warrants a `NewType` extraction. The original story uses raw `UUID`. | Surfaced as Notes-for-implementer (not a hard AC — implementer chooses the smart-constructor flavor). |
| 30 | harden | `AttemptAnchorBuilder` is exported in the original Implementation outline; single-use → keep file-private (Rule 2). | Specified `_AttemptAnchorBuilder` (underscore prefix) + Notes line. |
| 31 | harden | `anchor_writer.write` proposed as a class in the original; two callers → single function (Rule 2). | Specified single-function form; Notes call out the conversation point if a third caller emerges. |
| 32 | harden | Open/Closed at `PlanProposal` ↔ `plan_proposal_kind` not enforced; Phase 7 adding a 5th variant would silently drift the anchor's `Literal[...]`. | AC-FENCE-3 — AST-walk-based exhaustiveness fence; widening one without the other fails at CI time. |
| 33 | harden | `_pending_anchors: dict[AttemptId, AttemptAnchor]` on `FallbackTier` is hidden state across `.run()` and `.on_validated()` calls — functional-core/imperative-shell discipline says this should be explicit. | Surface in Notes-for-implementer; if S6-01's `FallbackTier` shape rejects adding the field, alternate seam is a per-workflow registry passed in `RepoContext`. |
| 34 | nit | `MappingProxyType` for `extras` is read-only ergonomics; `Mapping[str, str]` already is the read-only structural contract. Choice retained for "frozen at runtime, not just at typecheck time" — the Pydantic frozen=True only freezes the model, not the inner dict. | Kept as AC-SCHEMA-4; documented rationale. |
| 35 | nit | `attach_trust_outcome` reads `trust.passed` and `trust.confidence` — coupling to `TrustOutcome` shape. Decompose via "small data, deep function" or accept the coupling. | Kept (the coupling IS the contract per ADR-04-0017's Consequence row about `TrustOutcome`-shape changes triggering schema bumps). |

---

## Stage 3 — Researcher

**Skipped.** No critic finding tagged `NEEDS RESEARCH`. Hypothesis (already in `pyproject.toml`) is the canonical property-based pattern for the regex critic's recommendation; no arXiv lookup needed. JSON round-trip with `pydantic.TypeAdapter` is established codebase practice (precedent: S4-07 sub-schema validators). Two-write-site dispatch is a direct application of split-write event-sourcing — the canonical reference is production ADR-0034 already in the story's References block.

---

## Stage 4 — Synthesizer + Editor

### Conflict resolution

- **Coverage #1 (split write-site) vs Design-Patterns #33 (hidden state on `FallbackTier`).** Consistency wins — ADR-04-0017's "anchor emission is unconditional" + "deferred-attach" combine to *require* a split. The hidden-state critique is surfaced in Notes-for-implementer with two acceptable seams (instance field vs `RepoContext` registry).
- **Test-Quality #14 (round-trip parse) vs Coverage #2 (Optional fields).** Compatible. The round-trip test consumes the Optional-field schema.
- **Design-Patterns #29 (`AttemptId` newtype) vs Rule 2 (first use, do not extract).** Rule-of-three reached (`WorkflowId`, `AdvisoryId`, third = `AttemptId`) → extraction is correct. Surfaced as Notes-for-implementer guidance (not a hard AC).
- **Consistency #28 (LOC estimate) is informational; updated quietly.**

### Edits applied (summary)

1. **Status** flipped `Ready` → `HARDENED`.
2. **Validation notes** block appended after header listing every material change.
3. **Goal** rewritten — terminal-event-index-10 + split-write-site dispatch + plural-`gates` Phase-5 path.
4. **Acceptance criteria** restructured into seven titled groups (Schema · Functional · Registry · JSONL · Fence · Phase-5 hook · Quality gates) — 22 ACs total (up from 12), each individually verifiable, each traceable to a specific failure mode.
5. **Implementation outline** rewritten — 8 numbered steps with concrete paths, mode flags, and the events-registry edit.
6. **TDD plan** rewritten — example test mutation-resistant; 14 additional named red tests including the new property test.
7. **Files to touch** expanded — `src/codegenie/plugins/events.py` row added; Phase-5 path corrected to `gates/runner.py`; three fence-test rows; property-test row; S6-01 tape extension row.
8. **Notes for the implementer** rewritten — added the split-write-site rationale, the `AttemptId` newtype rule-of-three justification, the Optional-field ADR-clarification note, the determinism interaction with S6-07, the umask-zero subtlety, and the registry-seam reminder.

### Final verdict

**HARDENED.** The story's goal was correct and the architectural intent was sound — what was missing was concrete-codebase alignment (paths, APIs, registry seams), terminal-event positioning relative to S6-01's tape, the refusal-path schema clarification, and mutation-resistant test phrasing. Eight blockers fixed, fourteen ACs added or strengthened, three Notes-for-implementer paragraphs added. Ready for `phase-story-executor`.

### Residual risks (not gating, but executor should attend)

- **S5-02 not yet shipped.** AC-PHASE5-2 makes this a `BLOCKED` failure mode the executor should detect early and log to `_attempts/S6-08.md`. Do not invent the `GateRunner` file.
- **S6-01 not yet shipped.** Without S6-01's ten-event tape in place, the `EXPECTED_EVENT_COUNT_PER_BRANCH = 10 → 11` transition has no anchor to attach to. Treat as `BLOCKED-PARTIAL` if encountered.
- **S6-07 determinism interaction.** The new `uuid4()` call for `attempt_id` is the only new non-determinism source; under cassette replay it must be seeded or stripped. Surface the choice; do not silently break S6-07.
