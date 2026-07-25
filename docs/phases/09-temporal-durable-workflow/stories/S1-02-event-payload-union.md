# Story S1-02 — 22-variant EventPayload discriminated union

**Step:** Step 1 — Domain primitives, typed event contracts, and structural fences
**Status:** HARDENED (phase-story-validator, 2026-07-24)
**Effort:** M
**Depends on:** S1-01 **GREEN** — must ship the six new Newtypes (`CorrelationId`, `WorkflowSeq`, `ProjectionId`, `TaskQueueName`, `ActivityName`, `PrUrl`) on disk in `codegenie.types.identifiers`. HARDENED is **not sufficient** — this story imports from `codegenie.types.identifiers` and its property tests will fail at import time if the Newtypes are not landed. Executor must verify `identifiers.py` line count against the S1-01 GREEN commit before starting.
**ADRs honored:** ADR-0003 (per-workflow BLAKE3 chain — payload shape drives canonical-JSON hashing), ADR-0006 (`@critical_event` set; S1-03 lands the decorator byte-additively), production ADR-0034 (event sourcing as canonical primitive), production ADR-0043 (additive variants only; loud compiler-policed edits)

## Validation notes (2026-07-24)

Hardened via `/phase-story-validator`. Full report:
[`_validation/S1-02-event-payload-union.md`](_validation/S1-02-event-payload-union.md).

Twenty findings addressed (7 BLOCK, 11 HARDEN, 2 NIT):

- **BLOCK-CONS-1 (S1-01 dependency status).** `Depends on:` rewritten to require S1-01 GREEN, not merely HARDENED. This story imports from `codegenie.types.identifiers` at property-test import time.
- **BLOCK-CONS-2 (arch-unspecified variants).** Arch specifies field lists for only 8 of 22 variants. Implementation outline §2 now enumerates minimum-viable field specs for the 14 arch-silent variants; a follow-up story tightens.
- **BLOCK-CONS-3 (`freshness_window` gap-3).** Arch §Critic round 4 line 1139 mandates `RouteDecided.freshness_window: timedelta` and `PluginResolved.freshness_window: timedelta` land day-one. New AC-9 requires the field with default `timedelta(days=7)`; runtime override via `DurableSettings` lands later.
- **BLOCK-CONS-4 / DP-5 (inline-NewType contradiction).** Implementation outline §2 previously permitted inline `NewType`; Notes-for-implementer forbade the same. Contradiction resolved: **all missing kernel-tier NewTypes land in `codegenie.types.identifiers`** (piggyback on S1-01's drift-fences) or use `Literal[...]` closed sets where the arch permits. New fence `tests/fence/test_events_payloads_no_local_newtypes.py` AST-scans for `NewType` calls.
- **BLOCK-COV-2 (`__all__` / union set equality).** New AC-3 pins `set(get_args(get_args(EventPayload)[0])) == set(_ALL_VARIANT_CLASSES)`. A variant defined but omitted from the union alias silently escapes round-trip coverage; this fence catches it.
- **BLOCK-COV-3 (pairwise-distinct `kind`).** New AC-4 pins `len({cls.model_fields["kind"].default for cls in _ALL_VARIANT_CLASSES}) == 22`.
- **BLOCK-TQ-1 (fragile snake_case helper).** Original test's `_snake_case(cls.__name__)` regex could silently pass helper-regression bugs. Replaced with a **golden dictionary** `_KIND_GOLDEN: Final[dict[str, str]]` (22 entries) that pins every class→kind mapping explicitly.
- **BLOCK-TQ-2 (missing `type(revived) is type(payload)`).** Round-trip property test previously asserted only value equality. A silent discriminator misroute between structurally-identical variants would pass. Both round-trip tests now assert type identity.
- **HARDEN-COV-4/5 (`extra="forbid"` + `frozen` behavioral).** New AC-5 and AC-6.
- **HARDEN-COV-6 (timezone discipline).** New AC-7 requires naive-datetime construction to raise `ValidationError`.
- **HARDEN-COV-7 (six-family dispatch enumeration).** AC-8 enumerates the six families explicitly; test parametrizes over one representative each; `RouteStalenessDescent` and `RedactionFired` mandatory (edge cases).
- **HARDEN-COV-8 (exhaustive `match` test).** AC-12 requires `tests/events/test_payload_exhaustiveness.py` — mypy-strict exhaustive match with `assert_never`.
- **HARDEN-CONS-5 (`workflow_id` tightening).** Notes-for-implementer now describes the deliberate pattern: `BudgetExhausted` and `ChainTamperDetected` re-declare `workflow_id: WorkflowId` (non-None) at the variant level. AC-10 tests `BudgetExhausted(workflow_id=None, ...)` raises.
- **HARDEN-CONS-6 (`RouteStalenessDescent` field spec).** Notes-for-implementer pins: `prior_route: Literal["recipe","rag","llm"]`, `decided_at: datetime`, `staleness: timedelta`.
- **HARDEN-TQ-3/4 (dispatch parametrization + strategy module).** Test file layout adds `tests/property/_event_payload_strategies.py`.
- **HARDEN-TQ-5 (shape-vs-kind adversarial).** New test constructs a `MergeOutcome`-shaped dict with `kind="budget_exhausted"` and asserts dispatch to `BudgetExhausted` — proves the discriminator is actually consulted.
- **HARDEN-TQ-6 (`TypeAdapter` singleton fence).** New unit test verifies `EventPayloadAdapter` identity is stable across imports.
- **HARDEN-DP-3 (decorator-additive module layout).** Notes-for-implementer: variants at module top-level, no `Final`-sealing on classes; `_ALL_VARIANT_CLASSES` tuple is `Final` but classes stay decoratable so S1-03's `@critical_event` lands byte-additively.
- **NIT-DP-1/7 (extension-by-addition seam).** AC-11 pins `_ALL_VARIANT_CLASSES` module-level and imported by tests; three-loud-edits seam ("`_ALL_VARIANT_CLASSES` tuple + union alias + `_KIND_GOLDEN` dict") is the extension pattern.
- **NIT-DP-2/6 (`_Base` privacy + no `Any`).** Notes-for-implementer clarifies.

## Context
The canonical Postgres event log (`events.events`) holds every typed event the workflow body emits. The 22-variant discriminated union is the contract: every `EventLog.append` takes one of these variants; every projection in Step 7 folds them; the per-workflow BLAKE3 chain in Step 3 hashes their canonical JSON. Get a `kind: Literal[...] = "..."` discriminator wrong and Pydantic's union dispatch silently routes to the wrong variant — the round-trip property test + the golden-dict kind fence are the two defenses. `RouteStalenessDescent` lands day one (Gap-3 per arch §"Critic round 4 — newly surfaced gap #3"); `RouteDecided.freshness_window` and `PluginResolved.freshness_window` also land day one because adding a field to a discriminated-union variant after S3-01 has hashed payloads breaks chain-verify.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Data model — EventPayload — discriminated union (Contract)` — illustrative code block; note **only 8 of 22 variants have concrete field lists here**; the other 14 are named in the tail comment (line 762–766)
  - `../phase-arch-design.md §Design patterns applied #2 — Tagged union / sum type` — why `Annotated[Union[...], Field(discriminator="kind")]` and not a runtime registry
  - `../phase-arch-design.md §Critic round 4 — newly surfaced gap #3` — `RouteStalenessDescent` + `freshness_window` day-one rationale (freshness-window resume check)
  - `../phase-arch-design.md §Property tests` — Hypothesis-generated `EventPayload` instances JSON round-trip via `EventPayloadAdapter`
- **Phase ADRs:**
  - `../ADRs/0003-per-workflow-blake3-prev-hash-chain.md` — payload canonical JSON drives `row_hash`; byte-identical round-trip is load-bearing
  - `../ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — five variants will be marked `@critical_event` by S1-03 (don't apply it here; do keep variant classes decoratable)
- **Production ADRs:**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — canonical event log mandate
  - `../../../production/adrs/0033-sum-types-for-domain-state.md` — discriminated union is the canonical sum-type pattern in this codebase
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — three-loud-edits seam (variant class + union arg + `_KIND_GOLDEN` entry)
- **Source design:**
  - `../final-design.md §Synthesis ledger` — "21-variant typed EventPayload" row (22 with gap-3)
- **Precedent (read before implementing):**
  - `src/codegenie/indices/freshness.py` — the 5-variant discriminated-union precedent (`Annotated[Fresh | Stale, Field(discriminator="kind")]`); `Stale.reason: StaleReason` shows the nested-union pattern
  - `tests/unit/indices/test_freshness.py` — `test_index_freshness_roundtrip_identity` + `test_discriminator_strings_are_exactly_pinned` are the shapes to mirror at higher cardinality
  - `src/codegenie/probes/_shared/scanner_outcome.py` + `src/codegenie/probes/layer_c/scenario_result.py` — additional multi-variant precedents (9-ish variants each) using the same `Annotated[Union[...], Field(discriminator="kind")]` pattern
- **Existing code:**
  - `src/codegenie/types/identifiers.py` — Newtypes consumed by the variants (`WorkflowId`, `EventId`, `WorkflowSeq`, `CorrelationId`, `TaskClassId`, `PrUrl`, `BlobDigest`, plus S1-02 additions per §2)
  - Pydantic v2 docs on discriminated unions: `https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions-with-str-discriminators`

## Goal
Land `src/codegenie/events/payloads.py` with all 22 frozen Pydantic v2 variants, the `Annotated[Union[...], Field(discriminator="kind")]` alias, a module-level `EventPayloadAdapter: Final[TypeAdapter[EventPayload]]`, and a module-level `_ALL_VARIANT_CLASSES: Final[tuple[type[_Base], ...]]` tuple that the test module imports as the single source of truth. Round-trip-byte-identical via that adapter with type-identity preservation is the load-bearing test.

## Acceptance criteria
- [ ] **AC-1 (variant manifest, 22 exact).** `src/codegenie/events/payloads.py` defines all 22 variants: `WorkflowStarted`, `WorkflowResumed`, `WorkflowCompleted`, `WorkflowTerminated`, `PluginResolved`, `BundleBuilt`, `RouteDecided`, `RouteStalenessDescent`, `RecipeApplied`, `RecipeMissed`, `RagInvoked`, `LlmInvoked`, `PatchApplied`, `TrustGatePassed`, `TrustGateFailed`, `PrOpened`, `HumanReviewRequested`, `HumanReviewDecision`, `MergeOutcome`, `BudgetExhausted`, `ChainTamperDetected`, `RedactionFired`. Assertion: `len(_ALL_VARIANT_CLASSES) == 22` AND `len(typing.get_args(typing.get_args(EventPayload)[0])) == 22`.
- [ ] **AC-2 (base + common fields).** Every variant inherits from a shared `_Base(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and the common fields (`event_id: EventId`, `workflow_id: WorkflowId | None`, `timestamp: datetime`, `correlation_id: CorrelationId | None`, `wf_seq: WorkflowSeq | None`).
- [ ] **AC-3 (union ↔ tuple set equality).** `set(typing.get_args(typing.get_args(EventPayload)[0])) == set(_ALL_VARIANT_CLASSES)`. Fence-style assertion — asymmetric-difference test surfaces a variant defined-but-not-in-union or in-union-but-not-in-tuple.
- [ ] **AC-4 (pairwise-distinct `kind` values).** `len({cls.model_fields["kind"].default for cls in _ALL_VARIANT_CLASSES}) == 22`. Every variant declares `kind: Literal["<snake_case_name>"] = "<snake_case_name>"`; the mapping is pinned by `_KIND_GOLDEN` (AC-12), not derived by a regex helper.
- [ ] **AC-5 (`extra="forbid"` behavioral).** Constructing any variant with an unknown kwarg raises `ValidationError`. Parametrized over one representative per family (6+ tests).
- [ ] **AC-6 (`frozen` behavioral).** Attempts to `setattr` on any variant instance raise `ValidationError`. Parametrized over one representative per family.
- [ ] **AC-7 (timezone discipline).** Constructing any variant with a naive `datetime` (no tzinfo) raises `ValidationError`. Enforced via a `_Base.timestamp` field-validator or `AwareDatetime` typing.
- [ ] **AC-8 (six-family discriminator dispatch).** `tests/events/test_payload_discriminator_dispatch.py` parametrizes over one representative per family: `workflow-lifecycle` (`WorkflowStarted`), `route` (`RouteStalenessDescent` — edge case), `plugin/bundle` (`PluginResolved`), `recipe/rag/llm/patch` (`LlmInvoked`), `gate` (`TrustGateFailed`), `pr/human-review/merge` (`MergeOutcome`), `budget/chain/redaction` (`RedactionFired` — edge case). Each test builds a payload dict with the family variant's `kind` and asserts `type(EventPayloadAdapter.validate_python(blob)).__name__` equals the class name.
- [ ] **AC-9 (day-one `freshness_window`).** `RouteDecided` carries `freshness_window: timedelta = timedelta(days=7)`; `PluginResolved` carries `freshness_window: timedelta = timedelta(days=7)`. Default is the type-level fallback; runtime override via `DurableSettings` lands in a later Step-2 story.
- [ ] **AC-10 (`workflow_id` tightening).** `BudgetExhausted(workflow_id=None, ...)` and `ChainTamperDetected(workflow_id=None, ...)` raise `ValidationError`. The variant-level tightening from `WorkflowId | None` to `WorkflowId` is deliberate (per arch); a variant that permits `None` where arch requires non-None is a coverage bug.
- [ ] **AC-11 (`_ALL_VARIANT_CLASSES` is the source of truth).** `_ALL_VARIANT_CLASSES: Final[tuple[type[_Base], ...]]` is a module-level constant in `payloads.py` (22 entries). Every test that iterates variants imports it directly; no test-local re-derivation via reflection over `dir(payloads)` or via `_Base.__subclasses__()`.
- [ ] **AC-12 (`_KIND_GOLDEN` is the source of truth for kind values).** The test module defines `_KIND_GOLDEN: Final[dict[str, str]]` with 22 entries (class-name → kind-literal-default). Test asserts `cls.model_fields["kind"].default == _KIND_GOLDEN[cls.__name__]` for every class in `_ALL_VARIANT_CLASSES`. Golden-dict — not a snake_case regex helper — is what a `Literal["mergeoutcome"]` typo has to defeat.
- [ ] **AC-13 (fence — no local NewTypes).** `tests/fence/test_events_payloads_no_local_newtypes.py` AST-scans `src/codegenie/events/payloads.py` and asserts zero calls to `NewType`. Enforces production-ADR-0033: all kernel-tier NewTypes live in `codegenie.types.identifiers`.
- [ ] **AC-14 (Hypothesis property — JSON + Python round-trip WITH type identity).** `tests/property/test_event_payload_hypothesis.py` uses composed strategies from `tests/property/_event_payload_strategies.py` to generate ≥200 examples across all 22 variants; asserts BOTH `EventPayloadAdapter.validate_python(EventPayloadAdapter.dump_python(x)) == x AND type(revived) is type(x)` AND the JSON analogue.
- [ ] **AC-15 (unit round-trip — one realistic instance per variant).** `tests/events/test_payload_roundtrip.py` instantiates one realistic instance of every variant (imported list from `_ALL_VARIANT_CLASSES`), round-trips via `dump_json`/`validate_json`, asserts `revived == instance AND type(revived) is type(instance)`.
- [ ] **AC-16 (`TypeAdapter` singleton fence).** Unit test asserts `EventPayloadAdapter is codegenie.events.payloads.EventPayloadAdapter` across two imports (module-level `Final[TypeAdapter[...]]` is the perf contract).
- [ ] **AC-17 (shape-vs-kind adversarial).** `test_discriminator_routes_by_kind_not_by_shape` — constructs a payload dict that satisfies `BudgetExhausted`'s field shape but sets `kind="merge_outcome"`; asserts the resulting instance's `type().__name__` is neither `BudgetExhausted` nor a false match; if fields don't align with `MergeOutcome`, asserts `ValidationError`. Proves discriminator dispatch actually consults `kind`, not field-shape.
- [ ] **AC-18 (exhaustive `match` under `mypy --strict`).** `tests/events/test_payload_exhaustiveness.py` `match`es a `EventPayload` value against every variant with `assert_never(x)` in the default arm; the file is included in `mypy --strict` scope so a missing arm is a mypy failure at test-collection time.
- [ ] **AC-19 (TDD-plan red-then-green + toolchain).** The TDD plan's red test exists, was committed, and is green. `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/events/payloads.py`, and `pytest tests/events tests/property/test_event_payload_hypothesis.py tests/fence/test_events_payloads_no_local_newtypes.py` all pass.

## Implementation outline
1. Create `src/codegenie/events/__init__.py` (empty marker package + module docstring citing ADR-0034).
2. **Land any missing kernel-tier NewTypes in `codegenie.types.identifiers`** (piggyback on the S1-01 drift-fences — each addition needs `__all__` + `_NEWTYPE_REGISTRY` entries + pairwise-distinct test extension). Missing today (verify against latest `identifiers.py` at execution time): `GateId`, `LlmProvider`, `LlmModelId`, `TerminationReason`, `ConfigDigest`, `GitHubUsername`, `FailureReason` (and any others the arch text mentions). **Inline `NewType` calls inside `payloads.py` are forbidden** (AC-13 fence). Where arch permits a closed set, prefer `Literal[...]` (e.g., `TerminationReason` could be `Literal["operator","budget","failure_unrecoverable","chain_tamper","budget_exhausted"]` — check arch for the exact set before promoting).
3. Create `src/codegenie/events/payloads.py`:
   - Module docstring citing ADR-0003 (chain) + ADR-0006 (`@critical_event` lands in S1-03 byte-additively — S1-02 must keep variant classes decoratable, i.e. no metaclass, no `Final`-sealing on the class objects) + ADR-0034.
   - `_Base(BaseModel)` with `ConfigDict(frozen=True, extra="forbid")` + the five common fields; `timestamp: AwareDatetime` (or a `@field_validator("timestamp")` that rejects naive) — enforces AC-7.
   - **22 variant classes at module top level.** For the 8 variants specified in arch (`WorkflowStarted`, `WorkflowTerminated`, `RouteDecided`, `LlmInvoked`, `TrustGateFailed`, `MergeOutcome`, `BudgetExhausted`, `ChainTamperDetected`), use the arch's field lists verbatim (add `freshness_window: timedelta = timedelta(days=7)` to `RouteDecided` per AC-9). For the 14 arch-silent variants, use these minimum-viable specs derived from the surrounding arch text (a follow-up story may tighten):
     - `WorkflowResumed`: no additional fields
     - `WorkflowCompleted`: `decision: Literal["merged","closed","modified","aborted"]`
     - `PluginResolved`: `plugin_id: PluginId`, `bundle_digest: BlobDigest`, `freshness_window: timedelta = timedelta(days=7)` (AC-9)
     - `BundleBuilt`: `bundle_digest: BlobDigest`, `plugin_id: PluginId`
     - `RouteStalenessDescent`: `prior_route: Literal["recipe","rag","llm"]`, `decided_at: datetime`, `staleness: timedelta` (per Notes-for-implementer)
     - `RecipeApplied`: `recipe_id: RecipeId`, `patch_digest: BlobDigest`
     - `RecipeMissed`: `recipe_id: RecipeId`, `reason: Literal["no_match","conflict","preflight_failed"]`
     - `RagInvoked`: `retrieved: NonNegativeInt`, `top_similarity: float | None`
     - `PatchApplied`: `patch_digest: BlobDigest`, `attempt_id: AttemptId`
     - `TrustGatePassed`: `gate: GateId`, `passing_signals: tuple[SignalKind, ...]`
     - `PrOpened`: `pr_url: PrUrl`, `attempt_id: AttemptId`
     - `HumanReviewRequested`: `pr_url: PrUrl`, `reason: FailureReason | None`
     - `HumanReviewDecision`: `pr_url: PrUrl`, `decision: Literal["approve","reject","defer"]`, `reviewer: GitHubUsername`
     - `RedactionFired`: `secret_type: str`, `redaction_count: NonNegativeInt` (bounded string, not a NewType — this is diagnostic-only data)
   - `_ALL_VARIANT_CLASSES: Final[tuple[type[_Base], ...]] = (...)` — 22 entries in the same order as the union alias (AC-11).
   - `EventPayload = Annotated[Union[<all 22>], Field(discriminator="kind")]`.
   - `EventPayloadAdapter: Final[TypeAdapter[EventPayload]] = TypeAdapter(EventPayload)`.
   - `__all__` exports the 22 variants + `EventPayload` + `EventPayloadAdapter` + `_ALL_VARIANT_CLASSES`; excludes `_Base`.
4. Land `tests/property/_event_payload_strategies.py` — one `@st.composite` builder per variant, plus a top-level `event_payload_strategy() -> st.SearchStrategy[EventPayload]` that `st.one_of(...)`s them.
5. Land the unit tests + property test + fence test (see TDD plan).
6. Run `ruff check` + `ruff format --check` + `mypy --strict src/codegenie/events/payloads.py` + `pytest tests/events tests/property/test_event_payload_hypothesis.py tests/fence/test_events_payloads_no_local_newtypes.py`; iterate until clean.

## TDD plan — red / green / refactor
### Red — write the failing tests first

Test file path: `tests/property/test_event_payload_hypothesis.py`
```python
from hypothesis import given, settings
from codegenie.events.payloads import EventPayload, EventPayloadAdapter
from tests.property._event_payload_strategies import event_payload_strategy

@given(event_payload_strategy())
@settings(max_examples=200, deadline=None)
def test_event_payload_json_roundtrip(payload: EventPayload) -> None:
    blob = EventPayloadAdapter.dump_json(payload)
    revived = EventPayloadAdapter.validate_json(blob)
    assert revived == payload
    assert type(revived) is type(payload), "silent discriminator misroute"

@given(event_payload_strategy())
@settings(max_examples=200, deadline=None)
def test_event_payload_python_roundtrip(payload: EventPayload) -> None:
    revived = EventPayloadAdapter.validate_python(EventPayloadAdapter.dump_python(payload))
    assert revived == payload
    assert type(revived) is type(payload)
```

Test file path: `tests/events/test_payload_roundtrip.py`
```python
from codegenie.events.payloads import EventPayloadAdapter, _ALL_VARIANT_CLASSES
from tests.events._realistic_variant_instances import ONE_OF_EACH_VARIANT  # length 22, one per class

def test_every_variant_roundtrips_via_adapter_with_type_identity():
    assert len(ONE_OF_EACH_VARIANT) == 22
    for instance in ONE_OF_EACH_VARIANT:
        blob = EventPayloadAdapter.dump_json(instance)
        revived = EventPayloadAdapter.validate_json(blob)
        assert revived == instance
        assert type(revived) is type(instance)

# --- Golden manifest — AC-12: mutation-resistant to snake_case helper bugs ---
_KIND_GOLDEN: Final[dict[str, str]] = {
    "WorkflowStarted": "workflow_started",
    "WorkflowResumed": "workflow_resumed",
    "WorkflowCompleted": "workflow_completed",
    "WorkflowTerminated": "workflow_terminated",
    "PluginResolved": "plugin_resolved",
    "BundleBuilt": "bundle_built",
    "RouteDecided": "route_decided",
    "RouteStalenessDescent": "route_staleness_descent",
    "RecipeApplied": "recipe_applied",
    "RecipeMissed": "recipe_missed",
    "RagInvoked": "rag_invoked",
    "LlmInvoked": "llm_invoked",
    "PatchApplied": "patch_applied",
    "TrustGatePassed": "trust_gate_passed",
    "TrustGateFailed": "trust_gate_failed",
    "PrOpened": "pr_opened",
    "HumanReviewRequested": "human_review_requested",
    "HumanReviewDecision": "human_review_decision",
    "MergeOutcome": "merge_outcome",
    "BudgetExhausted": "budget_exhausted",
    "ChainTamperDetected": "chain_tamper_detected",
    "RedactionFired": "redaction_fired",
}

def test_kind_literal_matches_golden_dict():
    assert set(_KIND_GOLDEN.keys()) == {cls.__name__ for cls in _ALL_VARIANT_CLASSES}
    for cls in _ALL_VARIANT_CLASSES:
        assert cls.model_fields["kind"].default == _KIND_GOLDEN[cls.__name__]

def test_pairwise_distinct_kind_values():
    kinds = {cls.model_fields["kind"].default for cls in _ALL_VARIANT_CLASSES}
    assert len(kinds) == 22

def test_union_and_all_variant_classes_are_set_equal():
    import typing
    union_args = set(typing.get_args(typing.get_args(EventPayload)[0]))
    assert union_args == set(_ALL_VARIANT_CLASSES)
    assert len(union_args) == 22

def test_extra_forbid_rejects_unknown_kwarg():
    for cls in [WorkflowStarted, MergeOutcome, ChainTamperDetected]:
        with pytest.raises(ValidationError):
            cls(unknown_kwarg=1, ...)  # supply required fields per variant

def test_frozen_rejects_mutation():
    instance = ONE_OF_EACH_VARIANT[0]
    with pytest.raises(ValidationError):
        instance.event_id = "different"

def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        WorkflowStarted(timestamp=datetime(2026, 1, 1), ...)  # naive — no tzinfo

def test_budget_exhausted_requires_workflow_id():
    with pytest.raises(ValidationError):
        BudgetExhausted(workflow_id=None, ...)

def test_type_adapter_is_module_level_singleton():
    from codegenie.events.payloads import EventPayloadAdapter as A1
    from codegenie.events.payloads import EventPayloadAdapter as A2
    assert A1 is A2
```

Test file path: `tests/events/test_payload_discriminator_dispatch.py`
```python
import pytest
from codegenie.events.payloads import EventPayloadAdapter

_FAMILIES = [
    ("workflow-lifecycle", "WorkflowStarted", "workflow_started", <realistic kwargs>),
    ("route", "RouteStalenessDescent", "route_staleness_descent", <realistic kwargs>),
    ("plugin/bundle", "PluginResolved", "plugin_resolved", <realistic kwargs>),
    ("recipe/rag/llm/patch", "LlmInvoked", "llm_invoked", <realistic kwargs>),
    ("gate", "TrustGateFailed", "trust_gate_failed", <realistic kwargs>),
    ("pr/human-review/merge", "MergeOutcome", "merge_outcome", <realistic kwargs>),
    ("budget/chain/redaction", "RedactionFired", "redaction_fired", <realistic kwargs>),
]

@pytest.mark.parametrize("family,classname,kind_value,kwargs", _FAMILIES)
def test_discriminator_routes_per_family(family, classname, kind_value, kwargs):
    blob = {"kind": kind_value, **kwargs}
    obj = EventPayloadAdapter.validate_python(blob)
    assert type(obj).__name__ == classname

def test_discriminator_routes_by_kind_not_by_shape():
    # BudgetExhausted-shaped blob but kind="merge_outcome" — dispatch should
    # attempt MergeOutcome (which will fail validation due to shape mismatch),
    # proving `kind` — not field shape — is what selects the variant.
    budget_shape = {"kind": "merge_outcome",
                    "event_id": <valid>, "workflow_id": <valid>, "timestamp": <valid utc>,
                    "correlation_id": None, "wf_seq": 7,
                    "cap_usd": "10.00", "spent_usd": "12.34"}
    with pytest.raises(ValidationError):
        EventPayloadAdapter.validate_python(budget_shape)
```

Test file path: `tests/events/test_payload_exhaustiveness.py`
```python
from typing import assert_never
from codegenie.events.payloads import (
    EventPayload, WorkflowStarted, WorkflowResumed, WorkflowCompleted,
    WorkflowTerminated, PluginResolved, BundleBuilt, RouteDecided,
    RouteStalenessDescent, RecipeApplied, RecipeMissed, RagInvoked,
    LlmInvoked, PatchApplied, TrustGatePassed, TrustGateFailed, PrOpened,
    HumanReviewRequested, HumanReviewDecision, MergeOutcome,
    BudgetExhausted, ChainTamperDetected, RedactionFired,
)

def handle(e: EventPayload) -> str:
    match e:
        case WorkflowStarted(): return "workflow_started"
        case WorkflowResumed(): return "workflow_resumed"
        case WorkflowCompleted(): return "workflow_completed"
        case WorkflowTerminated(): return "workflow_terminated"
        case PluginResolved(): return "plugin_resolved"
        case BundleBuilt(): return "bundle_built"
        case RouteDecided(): return "route_decided"
        case RouteStalenessDescent(): return "route_staleness_descent"
        case RecipeApplied(): return "recipe_applied"
        case RecipeMissed(): return "recipe_missed"
        case RagInvoked(): return "rag_invoked"
        case LlmInvoked(): return "llm_invoked"
        case PatchApplied(): return "patch_applied"
        case TrustGatePassed(): return "trust_gate_passed"
        case TrustGateFailed(): return "trust_gate_failed"
        case PrOpened(): return "pr_opened"
        case HumanReviewRequested(): return "human_review_requested"
        case HumanReviewDecision(): return "human_review_decision"
        case MergeOutcome(): return "merge_outcome"
        case BudgetExhausted(): return "budget_exhausted"
        case ChainTamperDetected(): return "chain_tamper_detected"
        case RedactionFired(): return "redaction_fired"
        case _:
            assert_never(e)  # mypy --strict: unreachable-if-exhaustive
```

Test file path: `tests/fence/test_events_payloads_no_local_newtypes.py`
```python
import ast
from pathlib import Path

def test_events_payloads_declares_zero_newtypes():
    src = Path("src/codegenie/events/payloads.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "NewType", (
                f"payloads.py must not declare local NewTypes (production ADR-0033); "
                f"promote to codegenie.types.identifiers instead"
            )
```

### Green — make it pass
22 frozen Pydantic classes + the `Annotated` alias + the `TypeAdapter` + the `_ALL_VARIANT_CLASSES` tuple. Hypothesis composers live in `tests/property/_event_payload_strategies.py` — one `@st.composite` per variant, top-level `event_payload_strategy() -> st.one_of(*)`.

### Refactor — clean up
- `_ALL_VARIANT_CLASSES` is the single source of truth iterated by every test — module-private tuple, imported explicitly (no `_Base.__subclasses__()` reflection).
- The `_KIND_GOLDEN` dict lives in the test file (not production); it's the review-visible manifest of every discriminator string.
- Every variant's docstring cites the arch §EventPayload code block (or the arch tail-comment for arch-silent variants) and the variant's role.
- Variant classes are plain classes at module top level — no `Final` sealing, no metaclass, no factory function; S1-03's `@critical_event` decorator lands byte-additively above five of these classes.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/events/__init__.py` | New marker package |
| `src/codegenie/events/payloads.py` | The 22 variants + `EventPayload` alias + `EventPayloadAdapter` + `_ALL_VARIANT_CLASSES` tuple |
| `src/codegenie/types/identifiers.py` | Additions for arch-referenced NewTypes missing today (`GateId`, `LlmProvider`, `LlmModelId`, `TerminationReason`, `ConfigDigest`, `GitHubUsername`, `FailureReason`) — extends S1-01's drift-fences (`__all__`, `_NEWTYPE_REGISTRY`, pairwise-distinct) |
| `tests/events/__init__.py` | New marker package |
| `tests/events/_realistic_variant_instances.py` | One realistic instance per variant, imported by round-trip tests |
| `tests/events/test_payload_roundtrip.py` | One realistic instance per variant; round-trip WITH type identity; golden-dict kind; pairwise-distinct kinds; union-set equality; extra-forbid; frozen; naive-datetime rejection; workflow-id tightening; adapter singleton |
| `tests/events/test_payload_discriminator_dispatch.py` | Six-family parametrized dispatch + shape-vs-kind adversarial |
| `tests/events/test_payload_exhaustiveness.py` | `match`/`assert_never` exhaustive; mypy-strict scope |
| `tests/property/__init__.py` | Confirm marker exists (already present per repo layout) |
| `tests/property/_event_payload_strategies.py` | Per-variant Hypothesis composers + top-level `event_payload_strategy()` |
| `tests/property/test_event_payload_hypothesis.py` | Hypothesis JSON + Python round-trip property WITH type identity |
| `tests/fence/test_events_payloads_no_local_newtypes.py` | AST fence — payloads.py declares zero `NewType` calls (production ADR-0033) |

## Out of scope
- **`@critical_event` decoration** — applied by S1-03 to exactly five variants (`MergeOutcome`, `BudgetExhausted`, `TrustGateFailed`, `WorkflowTerminated`, `ChainTamperDetected`). This story lands the variants undecorated. Module layout must keep classes at top level so the decorator lands byte-additively.
- **`EventLog.append` / `EventBatchWriter`** — Step 3 (S3-01, S3-02). The adapter is the only Phase-9 consumer this story needs.
- **Postgres schema for `events.events`** — Step 2 (S2-03).
- **Per-workflow BLAKE3 chain** — S3-01 hashes the canonical JSON this story produces; the round-trip property test is the cross-cutting guarantee.
- **`RouteStalenessDescent`-emitter logic** — S5-03 in Step 5 fires the variant; this story only ships the type + fields (`prior_route`, `decided_at`, `staleness`).
- **Runtime override of `freshness_window`** — the type-level default `timedelta(days=7)` lands here; runtime `DurableSettings` override lands in a Step-2 story.
- **Tightening the 14 arch-silent variants beyond the minimum-viable field specs in §2** — a follow-up story may add richer typing (e.g., promote `WorkflowCompleted.decision: Literal[...]` to a top-level `WorkflowCompletionDecision` sum type).

## Notes for the implementer
- **Silent discriminator misroutes are the #1 failure mode this story defends against.** Pydantic v2's discriminated-union dispatch is silent when the `kind` literal default is wrong (`Literal["mergeoutcome"]` vs `"merge_outcome"`). The golden-dict test (AC-12) is the review-visible defense; `type(revived) is type(payload)` in every round-trip test (AC-14, AC-15) is the runtime defense.
- **The extension seam is three loud edits per new variant:** `_ALL_VARIANT_CLASSES` tuple entry, `Annotated[Union[...]]` alias arg, `_KIND_GOLDEN` dict entry. AC-3/4/11/12 form the fence — any single missing edit fails a test. Production ADR-0043 §"loud, compiler-policed edits" pattern.
- **No local NewTypes in `payloads.py`.** Enforced by AC-13. If arch references a NewType not yet in `identifiers.py`, land it in `identifiers.py` (piggyback S1-01's drift-fences). Where the arch uses what could be either a NewType or a closed literal set (e.g., `TerminationReason`, `LlmProvider`), prefer `Literal[...]` — it's structurally stronger and doesn't require a fence-file amendment.
- **`_Base` is module-private (leading underscore + excluded from `__all__`).** Downstream consumers (`EventLog.append` in S3-01) accept `EventPayload`, never `_Base`.
- **Variant-level `workflow_id: WorkflowId` (non-None) is deliberate tightening for `BudgetExhausted`, `ChainTamperDetected`.** Pydantic v2 permits field-tightening on subclasses. Do NOT push these back into `_Base` — that would forbid portfolio-scoped variants. AC-10 tests the tightening.
- **`Final[TypeAdapter[EventPayload]]` matters** — re-constructing the adapter per call is a measurable perf loss in Step 3's batcher hot path; the module-level instance is the contract. AC-16 fences it.
- **Hypothesis strategies must generate timezone-aware datetimes** via `st.datetimes(timezones=st.just(timezone.utc))` or the property test will fail with the naive-datetime `ValidationError` from AC-7.
- **`RouteStalenessDescent` field spec (from Notes-for-implementer):** `prior_route: Literal["recipe","rag","llm"]`, `decided_at: datetime` (the original `RouteDecided.timestamp`), `staleness: timedelta` (observed lag past `freshness_window`). Wire to arch §Critic round 4 gap-3 rationale.
- **Do not `assert isinstance(x, _Base)` in downstream code.** The public contract is the `EventPayload` union alias; `_Base` is an implementation detail (`__all__` excludes it).
- **Watch out for `Decimal` precision on `LlmInvoked.cost_usd` and `BudgetExhausted.cap_usd`/`spent_usd`** — Pydantic v2's `Decimal` serialization is JSON-safe but the round-trip test needs `Decimal("0.001") == Decimal("0.001")` which is by value, so this is fine.
- **The arch shows `frozenset` on `EventLogWriteCapability.allowed_kinds`** — Pydantic v2 supports `frozenset[str]`; if any variant ends up needing one, do not collapse to `tuple` for serializability (Pydantic handles it).
- **No `Any` in this module. No `dict[str, Any]`.** Every field is a typed identifier, a `Literal`, a `NonNegativeInt`, a `Decimal`, a `timedelta`, or a nested Pydantic model. `mypy --strict` catches the common cases; a `dict[str, Any]` slipped in as "future-proofing" would defeat the whole point of the discriminated union.
- **S1-03 is the next story in this family.** It adds `@critical_event` to five variants and a `_CRITICAL_EVENTS: Final[set[str]]` registry. Keep the module structure clean of anything that would block a decorator (no `Final` on class objects, no metaclass, no factory function returning classes).
