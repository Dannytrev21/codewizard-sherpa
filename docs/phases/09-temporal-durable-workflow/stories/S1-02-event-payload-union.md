# Story S1-02 — 21-variant EventPayload discriminated union

**Step:** Step 1 — Domain primitives, typed event contracts, and structural fences
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0003 (per-workflow BLAKE3 chain — payload shape drives canonical-JSON hashing), ADR-0006 (`@critical_event` set), production ADR-0034 (event sourcing as canonical primitive), production ADR-0043 (additive variants only)

## Context
The canonical Postgres event log (`events.events`) holds every typed event the workflow body emits. The 21-variant discriminated union is the contract: every `EventLog.append` takes one of these variants; every projection in Step 7 folds them; the per-workflow BLAKE3 chain in Step 3 hashes their canonical JSON. Get a `kind: Literal[...] = "..."` discriminator wrong and Pydantic's union dispatch silently routes the wrong way — the round-trip property test is the only defense. Includes `RouteStalenessDescent` from day one (Gap-3 per arch §"Critic round 4 — newly surfaced gap #3").

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Data model — EventPayload — discriminated union (Contract)` — illustrative code block; the variant list at the bottom is the canonical 21
  - `../phase-arch-design.md §Design patterns applied #2 — Tagged union / sum type` — why `Annotated[Union[...], Field(discriminator="kind")]` and not a runtime registry
  - `../phase-arch-design.md §Critic round 4 — newly surfaced gap #3` — `RouteStalenessDescent` rationale (the freshness-window resume check; landed in the union ahead of S5-03)
  - `../phase-arch-design.md §Property tests` — Hypothesis-generated `EventPayload` instances JSON round-trip via `EventPayloadAdapter`
- **Phase ADRs:**
  - `../ADRs/0003-per-workflow-blake3-prev-hash-chain.md` — payload canonical JSON drives `row_hash`; byte-identical round-trip is load-bearing
  - `../ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — five variants will be marked `@critical_event` by S1-03 (don't apply it here)
- **Production ADRs:**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — canonical event log mandate
  - `../../../production/adrs/0033-sum-types-for-domain-state.md` — discriminated union is the canonical sum-type pattern in this codebase
- **Source design:**
  - `../final-design.md §Synthesis ledger` — "21-variant typed EventPayload" row
- **Existing code:**
  - `src/codegenie/types/identifiers.py` — Newtypes consumed by the variants (`WorkflowId`, `EventId`, `WorkflowSeq`, `CorrelationId`, `TaskClassId`, `PrUrl`, `BlobDigest`)
  - Pydantic v2 docs on discriminated unions: `https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions-with-str-discriminators`

## Goal
Land `src/codegenie/events/payloads.py` with all 21 frozen Pydantic v2 variants, the `Annotated[Union[...], Field(discriminator="kind")]` alias, and a module-level `EventPayloadAdapter: Final[TypeAdapter[EventPayload]]` — round-trip-byte-identical via that adapter is the load-bearing test.

## Acceptance criteria
- [ ] `src/codegenie/events/payloads.py` defines all 21 variants listed in arch §EventPayload tail comment plus `RouteStalenessDescent`: `WorkflowStarted`, `WorkflowResumed`, `WorkflowCompleted`, `WorkflowTerminated`, `PluginResolved`, `BundleBuilt`, `RouteDecided`, `RouteStalenessDescent`, `RecipeApplied`, `RecipeMissed`, `RagInvoked`, `LlmInvoked`, `PatchApplied`, `TrustGatePassed`, `TrustGateFailed`, `PrOpened`, `HumanReviewRequested`, `HumanReviewDecision`, `MergeOutcome`, `BudgetExhausted`, `ChainTamperDetected`, `RedactionFired`. Exactly 22 names visible (21 from the manifest + the day-one `RouteStalenessDescent` Gap-3 variant per arch §Critic round 4).
- [ ] Every variant inherits from a shared `_Base(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and the common fields (`event_id: EventId`, `workflow_id: WorkflowId | None`, `timestamp: datetime`, `correlation_id: CorrelationId | None`, `wf_seq: WorkflowSeq | None`).
- [ ] Every variant declares `kind: Literal["<snake_case_name>"] = "<snake_case_name>"`; the literal value matches a `kind` map test (no typos, no drift).
- [ ] `EventPayload = Annotated[Union[<all 22>], Field(discriminator="kind")]` and `EventPayloadAdapter: Final[TypeAdapter[EventPayload]] = TypeAdapter(EventPayload)` are exported.
- [ ] Hypothesis property test in `tests/property/test_event_payload_hypothesis.py` generates ≥200 random instances across all variants and asserts `EventPayloadAdapter.validate_python(EventPayloadAdapter.dump_python(x)) == x` AND `EventPayloadAdapter.validate_json(EventPayloadAdapter.dump_json(x)) == x` round-trip equality.
- [ ] Unit test `tests/events/test_payload_roundtrip.py` instantiates one of every variant with realistic fields and asserts JSON round-trip byte-identical via `dump_json`/`validate_json`.
- [ ] Unit test `tests/events/test_payload_discriminator_dispatch.py` asserts a payload `{"kind":"merge_outcome", ...}` deserializes specifically to `MergeOutcome` (and would *fail* if the discriminator were misspelled) for at least one variant per "family" (workflow-lifecycle / route / gate / pr / chain / redaction).
- [ ] `mypy --strict src/codegenie/events/payloads.py` is clean; `match` on `EventPayload` with `assert_never` is exhaustive (a separate `tests/events/test_payload_exhaustiveness.py` exercises the `match` arm).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on touched files.

## Implementation outline
1. Create `src/codegenie/events/__init__.py` (empty marker package + module docstring citing ADR-0034).
2. Create `src/codegenie/events/payloads.py`:
   - Module docstring citing ADR-0003 (chain) + ADR-0006 (`@critical_event` lands in S1-03) + ADR-0034.
   - `_Base(BaseModel)` with `ConfigDict(frozen=True, extra="forbid")` + the five common fields.
   - 22 variant classes; each carries its `kind: Literal[...]` plus the variant-specific fields per arch (e.g., `MergeOutcome.pr_url: PrUrl`, `MergeOutcome.decision: Literal["merged","closed","modified"]`, `MergeOutcome.reviewer: GitHubUsername | None`). For fields referenced in arch but not yet typed in `codegenie.types.identifiers` (e.g., `ConfigDigest`, `LlmProvider`, `LlmModelId`, `CassetteId`, `TokenCount`, `TerminationReason`, `GateId`, `GitHubUsername`, `SignalKind`, `FailureReason`), declare conservative stand-ins inline as `NewType` in the variant module *only if missing from `identifiers.py`*; surface in the implementer notes if you add any so a follow-up PR can promote them.
   - `EventPayload` `Annotated` alias.
   - `EventPayloadAdapter: Final[TypeAdapter[EventPayload]]`.
3. Land the unit tests and property test (Hypothesis strategy: one `st.one_of(...)` over per-variant builders).
4. Run `mypy --strict` + `pytest`; iterate until clean.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/property/test_event_payload_hypothesis.py`
```python
from hypothesis import given, settings, strategies as st
from codegenie.events.payloads import EventPayload, EventPayloadAdapter

@given(_event_payload_strategy())  # st.one_of(_workflow_started_st(), _merge_outcome_st(), ...)
@settings(max_examples=200, deadline=None)
def test_event_payload_json_roundtrip(payload: EventPayload) -> None:
    blob = EventPayloadAdapter.dump_json(payload)
    revived = EventPayloadAdapter.validate_json(blob)
    assert revived == payload, "round-trip not byte-identical via discriminator"

@given(_event_payload_strategy())
def test_event_payload_python_roundtrip(payload):
    assert EventPayloadAdapter.validate_python(
        EventPayloadAdapter.dump_python(payload)
    ) == payload
```

Test file path: `tests/events/test_payload_roundtrip.py`
```python
def test_every_variant_roundtrips_via_adapter():
    # one realistic instance per variant in a fixture list
    for variant in _ONE_OF_EACH_VARIANT:
        blob = EventPayloadAdapter.dump_json(variant)
        assert EventPayloadAdapter.validate_json(blob) == variant

def test_kind_literal_matches_class_name_snake_case():
    # Every variant's `kind` literal default equals snake_case(class name)
    for cls in _ALL_VARIANT_CLASSES:
        default_kind = cls.model_fields["kind"].default
        assert default_kind == _snake_case(cls.__name__)
```

Test file path: `tests/events/test_payload_discriminator_dispatch.py`
```python
def test_discriminator_routes_to_merge_outcome():
    blob = {"kind": "merge_outcome", "event_id": "...", "workflow_id": "...",
            "timestamp": "...", "correlation_id": None, "wf_seq": 7,
            "pr_url": "https://github.com/x/y/pull/1", "decision": "merged",
            "reviewer": None}
    obj = EventPayloadAdapter.validate_python(blob)
    assert type(obj).__name__ == "MergeOutcome"
```

### Green — make it pass
22 frozen Pydantic classes + the `Annotated` alias + the `TypeAdapter`. Hypothesis strategy builders one-per-variant composed via `st.one_of`.

### Refactor — clean up
- Pull the 22-tuple of variant classes into a module-private `_ALL_VARIANT_CLASSES: Final[tuple[type[_Base], ...]]` so the test file imports it directly (no string scraping).
- The `kind` snake-case helper used in tests is one regex; keep it in the test file (not in production code).
- Every variant's docstring cites the arch §EventPayload code block and the variant's role.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/events/__init__.py` | New marker package |
| `src/codegenie/events/payloads.py` | The 22 variants + `EventPayload` alias + `EventPayloadAdapter` |
| `tests/events/__init__.py` | New marker package |
| `tests/events/test_payload_roundtrip.py` | One realistic instance per variant; round-trip |
| `tests/events/test_payload_discriminator_dispatch.py` | Discriminator routes correctly per family |
| `tests/events/test_payload_exhaustiveness.py` | `match`/`assert_never` exhaustive |
| `tests/property/__init__.py` | New marker (if absent) |
| `tests/property/test_event_payload_hypothesis.py` | Hypothesis JSON + Python round-trip property |

## Out of scope
- **`@critical_event` decoration** — applied by S1-03 to exactly five variants (`MergeOutcome`, `BudgetExhausted`, `TrustGateFailed`, `WorkflowTerminated`, `ChainTamperDetected`). This story lands the variants undecorated.
- **`EventLog.append` / `EventBatchWriter`** — Step 3 (S3-01, S3-02). The adapter is the only Phase-9 consumer this story needs.
- **Postgres schema for `events.events`** — Step 2 (S2-03).
- **Per-workflow BLAKE3 chain** — S3-01 hashes the canonical JSON this story produces; the round-trip property test is the cross-cutting guarantee.
- **`RouteStalenessDescent`-emitter logic** — S5-03 in Step 5 fires the variant; this story only ships the type.

## Notes for the implementer
- Pydantic v2's discriminated-union dispatch is **silent** when the `kind` literal default is wrong (e.g., `Literal["mergeoutcome"]` vs `"merge_outcome"`): you get a successful round-trip via the *wrong* variant. The "kind matches snake_case(class name)" test is the cheap defense.
- `Final[TypeAdapter[EventPayload]]` matters — re-constructing the adapter per call is a measurable perf loss in Step 3's batcher hot path; the module-level instance is the contract.
- Some variant-specific fields reference types not yet in `codegenie.types.identifiers` (`GateId`, `LlmProvider`, `TerminationReason`, etc.). Surface every such addition in the PR description so they can be promoted to `identifiers.py` in a follow-up; do **not** silently scatter NewTypes across modules.
- Hypothesis strategies should generate `datetime` via `st.datetimes(timezones=st.just(timezone.utc))` so the round-trip stays timezone-stable.
- `_Base` is **private** to the module — every variant inherits, but nothing else imports `_Base`.
- Watch out for `Decimal` precision on `LlmInvoked.cost_usd` and `BudgetExhausted.cap_usd`/`spent_usd` — Pydantic v2's `Decimal` serialization is JSON-safe but the round-trip test needs `Decimal("0.001") == Decimal("0.001")` which is by value, so this is fine.
- The arch shows `frozenset` on `EventLogWriteCapability.allowed_kinds` — Pydantic v2 supports `frozenset[str]`; if any variant ends up needing one, do not collapse to `tuple` for serializability (Pydantic handles it).
