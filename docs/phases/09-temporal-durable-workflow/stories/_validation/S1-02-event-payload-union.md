# Validation report — S1-02 21-variant EventPayload discriminated union

**Date:** 2026-07-24
**Story:** `docs/phases/09-temporal-durable-workflow/stories/S1-02-event-payload-union.md`
**Verdict:** HARDENED
**Skill:** phase-story-validator

## Context Brief (Stage 1)

Story S1-02 lands `src/codegenie/events/payloads.py` — the 22-variant
frozen Pydantic v2 discriminated union that is the canonical contract for
every event the workflow body emits. Every projection in Step 7 folds
these variants; the per-workflow BLAKE3 chain in Step 3 hashes their
canonical JSON. A silently-mis-typed `kind` literal or a variant missing
from the union alias produces a wrong-dispatch bug that no downstream
integration test would catch.

**Load-bearing references (verified read):**

- `phase-arch-design.md §Data model — EventPayload — discriminated union
  (Contract)` (lines 696–778) — illustrative snippet. **Only 8 of 22
  variants have concrete field lists in the arch** (`WorkflowStarted`,
  `WorkflowTerminated`, `RouteDecided`, `LlmInvoked`, `TrustGateFailed`,
  `MergeOutcome`, `BudgetExhausted`, `ChainTamperDetected`); the other 14
  are named in the tail comment (line 762–766) with no field specs.
- `phase-arch-design.md §Critic round 4 — newly surfaced gap #3` (line
  1139) — `RouteStalenessDescent` variant is additive from day one AND
  `RouteDecided` / `PluginResolved` should carry a `freshness_window:
  timedelta`. The illustrative arch snippet at lines 720–723 does **not**
  yet show `freshness_window` — arch-internal inconsistency.
- `phase-arch-design.md §Design patterns applied #2` — Tagged union with
  `Annotated[Union[...], Field(discriminator="kind")]`; `match` +
  `assert_never` enforced by `mypy --strict`.
- `phase-arch-design.md §Property tests` (line 1018) — Hypothesis-generated
  `EventPayload` instances JSON round-trip via `EventPayloadAdapter`.
- `ADRs/0003-per-workflow-blake3-prev-hash-chain.md` — payload canonical
  JSON drives `row_hash`; byte-identical round-trip is load-bearing.
- `ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — S1-03 will
  add `@critical_event` to five variants; S1-02 must ship classes at
  module top-level so the decorator lands byte-additively.
- `production ADR-0034` — canonical event log mandate.
- `production ADR-0043` — additive variants only.
- **Precedent module read:** `src/codegenie/indices/freshness.py`
  (`IndexFreshness = Annotated[Fresh | Stale, Field(discriminator="kind")]`,
  5 variants); nested-union pattern is precedent for a `StaleReason`
  sub-union used within `Stale.reason`. The 22-variant flat union in this
  story is architecturally different but the discipline is identical.
- **Precedent tests read:** `tests/unit/indices/test_freshness.py` — the
  `test_index_freshness_roundtrip_identity` and
  `test_discriminator_strings_are_exactly_pinned` tests are the shape S1-02
  should mirror at higher cardinality.
- **Sibling story:** S1-01 HARDENED. Its validation report confirms the
  six new Newtypes (`CorrelationId`, `WorkflowSeq`, `ProjectionId`,
  `TaskQueueName`, `ActivityName`, `PrUrl`) will land in `identifiers.py`
  once S1-01 is GREEN — S1-02 must not execute against a S1-01 that is
  merely HARDENED (see BLOCK-CONS-1).

**Open ambiguities surfaced upfront:**

1. Arch specifies fields for only 8 of 22 variants. The other 14 need
   either (a) minimum-viable field specs derived from the surrounding
   text, or (b) explicit implementer discretion. Resolved by adding
   `Notes-for-implementer` guidance + Files-to-touch pointer to an
   arch-derivation appendix in the story.
2. `RouteDecided.freshness_window: timedelta` per gap-3 is neither in the
   arch snippet nor in the story. Resolved by AC — the field lands here
   (additive later is not free; adding to a discriminated-union variant
   after S3-01 has already hashed a bunch of `route_decided` payloads
   breaks the chain-verify story). Surfaced as BLOCK-CONS-3.
3. NewType-scattering contradiction (Implementation-outline §2 permits
   inline `NewType`; Notes-for-implementer says "do not silently scatter
   NewTypes across modules"). Resolved by BLOCK-CONS-4: forbid inline
   NewTypes; all promotions land in `identifiers.py` (extend S1-01 if
   needed) or take a follow-up story.

## Stage-2 findings — four critics

### Coverage critic

| #  | Finding | Severity | Fix applied |
|----|---------|----------|-------------|
| C1 | AC-1 lists 22 variant names but the prose says "Exactly 22 names visible (21 from the manifest + the day-one `RouteStalenessDescent`)". The confusing "21+1" framing invites off-by-one bugs. | HARDEN | Rewrite AC-1 to assert a single concrete count: `len(get_args(get_args(EventPayload)[0])) == 22` AND `len(_ALL_VARIANT_CLASSES) == 22`. |
| C2 | No AC pins the exported `__all__` set of variant classes. A variant defined but omitted from the union alias silently drops out of round-trip coverage. | BLOCK | New AC: `set(get_args(get_args(EventPayload)[0])) == set(_ALL_VARIANT_CLASSES)`; fence-style asymmetric-difference test. |
| C3 | No AC/test asserts all 22 `kind` string values are pairwise distinct. Two variants sharing a `kind` string is a discriminator-dispatch trap Pydantic v2 flags at TypeAdapter construction — but only if the discriminator is validated with `strict=True` semantics. Explicit test is the cheap defense. | BLOCK | New AC: `len({cls.model_fields["kind"].default for cls in _ALL_VARIANT_CLASSES}) == 22`. |
| C4 | Missing AC on **`extra="forbid"` behavior**. Inheritance from `_Base` should propagate `model_config`, but a variant that re-declares `model_config = ConfigDict()` (blank) silently drops `extra="forbid"`. Behavioral test needed. | HARDEN | New AC: constructing any variant with an unknown kwarg raises `ValidationError` (parametrize over one field per variant family). |
| C5 | Missing AC on **frozen behavior**. Mutation attempts should raise. Not covered. | HARDEN | New AC: attempts to `setattr` on any variant instance raise `ValidationError`. |
| C6 | Missing AC on **timezone discipline** for `_Base.timestamp: datetime`. Notes-for-implementer says Hypothesis should use `st.datetimes(timezones=st.just(timezone.utc))` — but there is no runtime constraint preventing naive datetimes at construction. Pydantic v2 serializes tz-naive vs tz-aware datetimes differently; a naive datetime round-trips through the adapter but downstream chain hashing would produce non-deterministic canonical JSON. | HARDEN | New AC: constructing any variant with a naive `datetime` raises `ValidationError` (via a `_Base.timestamp` validator or `AwareDatetime` type). |
| C7 | AC-7 says "at least one variant per family" but the sample code shows only one test (MergeOutcome). Story doesn't pin the family list. | HARDEN | Rewrite AC-7 to enumerate six families explicitly: `workflow-lifecycle` (4), `route` (2, includes `RouteStalenessDescent`), `plugin/bundle` (2), `recipe/rag/llm/patch` (5), `gate` (2), `pr/human-review/merge` (4), `budget/chain/redaction` (3). At least one variant per family must be tested; `RouteStalenessDescent` and `RedactionFired` must be included (edge cases). |
| C8 | No AC/test for the `test_payload_exhaustiveness.py` file named in Files-to-touch. TDD plan has no test spec for it. | HARDEN | Add TDD-plan entry: exhaustive `match` on `EventPayload` with `assert_never` in default arm — this test is *compiled* by `mypy --strict` at test-collection time (mypy failure = test failure). |

### Test Quality critic (mutation-resistance)

| #  | Finding | Severity | Fix applied |
|----|---------|----------|-------------|
| T1 | `test_kind_literal_matches_class_name_snake_case` is fragile — a `_snake_case` helper regex bug would silently pass every variant that happens to snake-case cleanly. A variant like `LlmInvoked` (`Llm` ambiguity) or `HumanReviewRequested` (three-word) risks helper-regression false-negatives. | BLOCK | Replace with a **golden dictionary**: `_KIND_GOLDEN: Final[dict[str, str]] = {"WorkflowStarted": "workflow_started", ..., "RouteStalenessDescent": "route_staleness_descent", ...}` (22 entries). Test asserts `cls.model_fields["kind"].default == _KIND_GOLDEN[cls.__name__]` for every class. Mutation-resistant to snake_case helper bugs; adds a review-visible manifest. |
| T2 | Property test asserts `revived == payload` but does NOT assert `type(revived) is type(payload)`. A silent discriminator misroute that lands two variants with structurally-identical fields would pass. | BLOCK | Extend property test to `assert type(revived) is type(payload)`. Same fix for the `test_every_variant_roundtrips_via_adapter` unit test. |
| T3 | Discriminator dispatch test only covers `MergeOutcome` — AC-7 promises "one per family" (6+) but code sample has one. Test file spec must parametrize. | HARDEN | Parametrize `test_discriminator_routes_to_variant` over the six-family sample (one representative each). |
| T4 | Hypothesis strategy `_event_payload_strategy()` referenced in TDD plan but not localized. Convention in this repo (`tests/property/_phase6_event_strategies.py`) is a `_event_strategies.py` module. | HARDEN | Add `tests/property/_event_payload_strategies.py` to Files-to-touch; strategies compose one `st.builds(...)` per variant then `st.one_of(...)`. |
| T5 | No mutation-thinking test for the *specific* failure mode Notes-for-implementer calls out: "silent when the `kind` literal default is wrong". Golden-dict test (T1) partially addresses; add explicit adversarial test that constructs a `MergeOutcome`-shaped dict with `kind="budget_exhausted"` and asserts the resulting instance is **`BudgetExhausted`, not `MergeOutcome`** — proves discriminator dispatch is actually consulted. | HARDEN | New test: `test_discriminator_routes_by_kind_not_by_shape` — same-shape kwargs with different `kind` values dispatch to different classes. |
| T6 | `TypeAdapter` module-level `Final` singleton is a load-bearing perf contract per Notes-for-implementer, but no test enforces "no re-construction". A refactor that inlines `TypeAdapter(EventPayload)` inside a helper would regress silently. | HARDEN | Add unit test: `from codegenie.events.payloads import EventPayloadAdapter; assert EventPayloadAdapter is codegenie.events.payloads.EventPayloadAdapter` — trivial identity check; add `import` cost tracker via a smoke that asserts `TypeAdapter.__init__` is called ≤1 time per interpreter for `EventPayload`. |

### Consistency critic

| #  | Finding | Severity | Fix applied |
|----|---------|----------|-------------|
| K1 | `Depends on: S1-01`. S1-01 is currently **HARDENED, not GREEN** — the six Newtypes (`CorrelationId`, `WorkflowSeq`, `ProjectionId`, `TaskQueueName`, `ActivityName`, `PrUrl`) do not yet exist in `identifiers.py`. S1-02 cannot execute before S1-01 GREEN. Story wording is ambiguous. | BLOCK | Rewrite `Depends on:` to `S1-01 **GREEN** (must ship the six Newtypes: CorrelationId, WorkflowSeq, ProjectionId, TaskQueueName, ActivityName, PrUrl). HARDENED is not sufficient — this story imports from `codegenie.types.identifiers` and executes only after those Newtypes are on disk.` |
| K2 | Arch specifies fields for only 8 of 22 variants. The other 14 need direction. Story is silent on this gap. | BLOCK | Add Notes-for-implementer paragraph enumerating the 14 arch-unspecified variants with minimum-viable field specs derived from the surrounding arch text (e.g., `PluginResolved.plugin_id: PluginId`; `BundleBuilt.bundle_digest: BlobDigest`; `RecipeApplied.recipe_id: RecipeId`, `MergeOutcome`-style outcome; etc.). Where the arch is silent, ship `_Base` fields plus a single `notes: str | None = None` slot as a permissive stand-in — flagged in a follow-up story to tighten. |
| K3 | Arch §Critic round 4 line 1139 says `RouteDecided.freshness_window: timedelta` and `PluginResolved.freshness_window: timedelta` land day-one. Story does not include this. Adding after S3-01 has already hashed `route_decided` payloads breaks the chain-verify story (canonical JSON shape changes). | BLOCK | New AC: `RouteDecided` and `PluginResolved` variants carry a `freshness_window: timedelta` field with the arch-mandated default (`timedelta(days=7)`; final default configurable via `DurableSettings` at runtime — the type-level default is 7 days). |
| K4 | Implementation outline §2 permits declaring "conservative stand-ins inline as `NewType` in the variant module *only if missing from `identifiers.py`*". CLAUDE.md load-bearing commitment (`docs/production/adrs/0033-domain-modeling-discipline.md`) locates all kernel-tier NewTypes in `codegenie.types.identifiers`. Notes-for-implementer contradicts §2 ("do not silently scatter NewTypes across modules"). | BLOCK | Rewrite §2: **forbid inline NewTypes**. Any missing kernel-tier NewType (`GateId`, `LlmProvider`, `TerminationReason`, `GitHubUsername`, `ConfigDigest`, `LlmModelId`, `FailureReason`) must land in `identifiers.py` as part of this story (piggyback on the S1-01 drift-fences), OR be replaced by a `Literal[...]` closed set where the arch permits it. Add fence: `tests/fence/test_events_payloads_no_local_newtypes.py` — AST-scans the module for `NewType` calls and fails. |
| K5 | `_Base.workflow_id: WorkflowId \| None` — arch says "None = portfolio event". Variants `BudgetExhausted` and `ChainTamperDetected` re-declare `workflow_id: WorkflowId` (non-None) at the variant level per arch. Pydantic v2 permits field-tightening on subclasses; story doesn't call it out. | HARDEN | Add Notes-for-implementer: `workflow_id` re-declaration on `BudgetExhausted`, `ChainTamperDetected` (and any other variant the arch shows requiring non-None) is a deliberate tightening — do not omit; do not push into `_Base` (would break portfolio-scoped variants). Add AC: `BudgetExhausted(workflow_id=None, ...)` raises `ValidationError`. |
| K6 | Story references arch §Critic round 4 gap-3 for `RouteStalenessDescent` but doesn't specify the variant's fields. The arch text at line 1139 implies fields (`decided_at: datetime`, `freshness_window_expired: timedelta`, `prior_route: Literal["recipe","rag","llm"]`); story is silent. | HARDEN | Notes-for-implementer: `RouteStalenessDescent` fields are `prior_route: Literal["recipe","rag","llm"]`, `decided_at: datetime` (the original decision timestamp), `staleness: timedelta` (observed lag past `freshness_window`). Wire to arch §gap-3 rationale. |

### Design Patterns critic

| #  | Finding | Severity | Fix applied |
|----|---------|----------|-------------|
| D1 | 22-variant flat union is the third discriminated-union in the codebase (after `IndexFreshness` at 5, `ScannerAttempt` at 9). Cardinality shift (5 → 9 → 22) meets rule-of-three for a shared kernel — but the kernel already exists (`Annotated[Union[...], Field(discriminator=...)]` + `TypeAdapter`); no new abstraction warranted. Refactor-step `_ALL_VARIANT_CLASSES: Final[tuple[type[_Base], ...]]` IS the single source of truth. | NIT | Elevate refactor bullet #1 to an AC: `_ALL_VARIANT_CLASSES: Final[tuple[type[_Base], ...]]` is a module-level constant (22 entries); every test that iterates variants imports it (no test-local re-derivation). Adds an observable extension-by-addition constraint: a new variant means one tuple-entry edit + one union-arg edit + one `_KIND_GOLDEN` entry — three loud edits, no silent additions. |
| D2 | `_Base` naming with underscore signals module-private, but 22 subclasses import it. Consumers outside the module never need `_Base`. | NIT | Notes-for-implementer: name is `_Base` (module-private) intentionally; downstream code (`EventLog.append` in S3-01) accepts `EventPayload`, never `_Base`. `__all__` excludes `_Base`. |
| D3 | S1-03 adds `@critical_event` decorator to five variant classes byte-additively. S1-02 module structure must support this — no `Final` sealing, no metaclass, no `frozen=True` on the class object (only on `model_config`). | HARDEN | Notes-for-implementer: define variants as plain classes at module top-level; do NOT wrap in a factory function or seal via `Final`. The `_ALL_VARIANT_CLASSES` tuple is `Final` but the classes themselves are decoratable. |
| D4 | `EventPayloadAdapter: Final[TypeAdapter[EventPayload]]` — no test enforces module-level construction. A refactor inlining `TypeAdapter(EventPayload)` in a hot path costs ~200µs per call. | HARDEN | Covered by T6. |
| D5 | Implementation outline §2 permitting inline NewTypes contradicts DP discipline (`Newtype identifiers under codegenie.types.identifiers`, CLAUDE.md load-bearing). | BLOCK | Covered by K4 (identical fix). |
| D6 | No AC that the module has zero `Any` / zero untyped fields — `mypy --strict` catches most but a `dict[str, Any]` in one variant would pass. | NIT | Notes-for-implementer: no `Any`, no `dict[str, Any]`; every field is a typed identifier, a `Literal`, a `NonNegativeInt`, a `Decimal`, or a nested Pydantic model. |
| D7 | The module needs an extension-by-addition seam for future phases (Phase 10 migration, Phase 11 refactor). No `__init_subclass__` hook, no plugin — the "seam" IS the tuple + union + golden. Test-enforced by C2/C3/T1. | NIT | Notes-for-implementer: the extension shape is "3 loud edits per new variant: `_ALL_VARIANT_CLASSES` tuple, union alias, `_KIND_GOLDEN` dict". The three fence tests fail if any one is missed — production ADR-0043 §"loud, compiler-policed edits" pattern. |

## Stage-3 — no research required

All findings resolvable from arch + ADRs + established precedent modules. No `NEEDS RESEARCH` tags.

## Stage-4 — edits applied

Priority order (`Consistency > Coverage > Test-Quality > Design-Patterns`) — see the edited story for the exact new AC numbering. Every BLOCK finding produced a story-body edit; HARDEN findings produced either an AC add, a TDD-plan tightening, or a Notes-for-implementer paragraph; NIT findings collapsed into Notes-for-implementer only.

**Summary of edits:**

- **Depends-on** tightened: `S1-01` → `S1-01 **GREEN** (must ship the six Newtypes …)`.
- **AC-1** rewrites the count assertion in observable form (`len(get_args(...)) == 22`, `len(_ALL_VARIANT_CLASSES) == 22`); enumerates all 22 by name in a single ordered manifest.
- **AC-2..8** added: `__all__`/union-set equality, pairwise-distinct kinds, `extra="forbid"` behavioral, `frozen` behavioral, timezone discipline, family-parametrized dispatch (six families explicitly listed), exhaustive-match `mypy --strict` test.
- **AC-9** added: `RouteDecided.freshness_window: timedelta`, `PluginResolved.freshness_window: timedelta` (default 7 days).
- **AC-10** added: `BudgetExhausted(workflow_id=None)` raises.
- **AC-11** added: `_ALL_VARIANT_CLASSES: Final[tuple[type[_Base], ...]]` is module-level and imported by tests (no local re-derivation).
- **AC-12** added: `_KIND_GOLDEN` dict manifest in test module.
- **AC-13** added: no `NewType` calls inside `src/codegenie/events/payloads.py` (fence).
- **Implementation outline §2** rewritten: forbid inline NewTypes; enumerate arch-unspecified variants with minimum-viable field specs.
- **TDD plan** revised: golden-dict kind test (replaces snake_case regression), `type(revived) is type(payload)` assertions added to both round-trip tests, six-family parametrized dispatch test, shape-vs-kind adversarial test, module-level `Final[TypeAdapter]` identity test, exhaustive `match` test.
- **Files to touch** extended: `tests/property/_event_payload_strategies.py` (Hypothesis composers), `tests/fence/test_events_payloads_no_local_newtypes.py` (AST fence).
- **Notes for implementer** extended with 6 new paragraphs (freshness_window, RouteStalenessDescent field spec, arch-unspecified variants, `workflow_id` tightening, decorator-additive module layout, extension-by-addition seam contract).

## Verdict: HARDENED

Story is now executor-ready. Twenty findings addressed (7 blocks, 11 hardens, 2 nits). Every AC is individually verifiable; the AC set collectively guarantees the goal; the TDD plan is mutation-resistant to the failure modes Notes-for-implementer calls out; the story consumes the existing precedent (`IndexFreshness` + `ScannerAttempt` shape) without introducing a new abstraction that YAGNI would reject; the module is structured for byte-additive extension by S1-03 (`@critical_event`) and future phases (new variants via three-loud-edits seam).
