# Validation report — S6-03 (`SubgraphNode` Protocol + `SubgraphState` + reconciliation with shipped `NodeTransition`)

**Date:** 2026-05-19
**Validator:** phase-story-validator (inline four-lens analysis — same approach as the S6-02 validation report; the four critic lenses were applied directly against the loaded context after Stage 1 surfaced a block-tier Consistency conflict that the four critics would all collapse onto).
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/03-vuln-deterministic-recipe/stories/S6-03-subgraph-node-protocol.md`](../S6-03-subgraph-node-protocol.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *core architectural choice* is correct and well-traced:
- The Gap-1 fix (typed `SubgraphNode` Protocol with a typed return) is exactly what `phase-arch-design.md §Gap analysis Gap 1` prescribes.
- Re-using the `runtime_checkable Protocol` precedent (`codegenie.coordinator.input_snapshot:84`, `codegenie.plugins.bundle:275/293`, `codegenie.vuln_index.protocol:34`) is correct.
- The `SubgraphState` Pydantic-model design + `model_copy(update={...})` immutability discipline match the Phase-3 patterns (S1-03, S2-04 `ConcreteResolution`, S5-02 `_InternalError` sum).
- The S6-04 consumer (`test_orchestrator.py` line 131) already imports `from codegenie.plugins.subgraph import Advance, ShortCircuit, Escalate` — so the `plugins/subgraph.py` location is also correct.

But the story was written *before* S1-03 landed (GREEN 2026-05-18) and is now wildly inconsistent with the shipped reality: `NodeTransition`, `Advance`, `ShortCircuit`, `Escalate`, and `EscalationReason` already exist canonically in `src/codegenie/transforms/outcomes.py`. The story prescribes **redefining** them with different field shapes and a different reason taxonomy. Executing the story as-written would either (a) collide with existing imports, (b) ship two parallel `NodeTransition` types, or (c) fail mypy `--strict` on the Phase-5 contract-snapshot test (S6-06).

This is in-place-fixable. The Gap-1 *intent* is preserved; only the *landing site* and *typing of the existing variants* need to be reconciled.

All findings below were applied via direct edit. None threaten the goal.

## Context Brief (Stage 1)

### Story snapshot
- **Goal:** ship the per-node contract for Phase-3's 5-node `RemediationOrchestrator` subgraph (S6-04). Phase 6's LangGraph migration wraps it 1-to-1.
- **Status at validation time:** `Ready` — never executed.

### Shipped reality (as of git HEAD 41dd95d)
- `src/codegenie/transforms/outcomes.py` ALREADY defines:
  - `class Advance(BaseModel)` — `state: dict[str, str | int | bool | float]`
  - `class ShortCircuit(BaseModel)` — `outcome: RemediationOutcome`
  - `class Escalate(BaseModel)` — `reason: EscalationReason`
  - `NodeTransition = Annotated[Advance | ShortCircuit | Escalate, Field(discriminator="kind")]`
  - `EscalationReason = Literal["plugin_extends_cycle", "manifest_rejected", "capability_missing"]`
- All five are listed in `__all__` (line 46-77) and re-exported from `src/codegenie/transforms/__init__.py:34`.
- `tests/unit/transforms/test_outcomes.py` parametrises over `Advance(state={"k": 1})` (line 88), `ShortCircuit(outcome=...)`, `Escalate(reason="capability_missing")` (lines 88-90) and pins the `EscalationReason` member set to the 3 names above (line 323-327).
- `src/codegenie/plugins/subgraph.py` does **not** exist (`MISSING` per validator check).

### S6-04 (consumer) expectations
- Story body line 131: `from codegenie.plugins.subgraph import Advance, ShortCircuit, Escalate` — must succeed.
- Story implementation outline line 102 / 106: `Escalate("vuln_index_corrupted")` / `Escalate("filesystem_race")` — these reasons must be members of whatever Literal `Escalate.reason` is typed as.
- Story implementation outline line 104: `Advance(state.model_copy(update={"transform": transform}))` — `state` is a typed Pydantic model (Transform is NOT a primitive), so `Advance.state: dict[primitive]` is unworkable for the actual orchestrator flow.

### S7-03 (universal HITL plugin) expectations
- `async def run(self, state: SubgraphState) -> NodeTransition` — SubgraphState must be a typed param (not a dict).
- Universal node returns `ShortCircuit(RemediationOutcome.RequiresHumanReview(...))` — already supported by the shipped `ShortCircuit`.

### Constraints in play
- ADR-0001 §Consequences (Phase-3 contract surface freeze + S6-06 snapshot test) — names + field shapes are the contract. **Widening** is allowed; **rename** is not.
- ADR-0010 Decision §3 — every variant `frozen=True, extra="forbid"`; every dispatch site uses `match` + `assert_never`; **single declaration point** per union (ADR-0010 Amendment 2026-05-18 cemented this; see S1-03 `_validation/`).
- ADR-0010 §Consequences — `dict[str, Any]` is forbidden under `transforms/`. Pydantic-model payloads (like `SubgraphState`) are the prescribed alternative ("If a node genuinely needs richer state, the right move is a new typed payload model" — S1-03 Implementer notes, line 407).
- 05-ADR-0006 (cross-phase Protocol convention) — Protocol over ABC when there is no shared default behavior; Protocol bodies are `...` (literal ellipsis), not `pass`, not `raise NotImplementedError`.
- 06.5-S1-04 (rubric Protocol precedent) — one-method `@runtime_checkable` Protocol that orchestrator dispatch consumes.
- CLAUDE.md §"Extension by addition" + Phase-3 README "Gap-1 (`SubgraphNode` Protocol) is a first-class story — see S6-03" — the Phase-6 LangGraph migration's single seam is **this** Protocol's three transitions.

### Open ambiguities surfaced before critics
- **Q1 — where does `NodeTransition` canonically live?** S1-03 shipped it in `transforms/outcomes.py`; S6-03 prescribed re-defining it in `plugins/subgraph.py`. Per ADR-0010 Amendment 2026-05-18 ("single canonical declaration site"), `transforms/outcomes.py` IS the canonical site. `plugins/subgraph.py` MUST re-export, not redefine.
- **Q2 — should `Advance.state` widen to `SubgraphState`?** Per S1-03 Implementer notes line 407 ("the right move is a new typed payload model, not relaxing `Advance.state`"), the S1-03 implementer explicitly anticipated S6-03 as the widener. `SubgraphState` IS the new typed payload model. Replacing `state: dict[primitive]` with `state: SubgraphState` is the right move. The existing `test_outcomes.py` primitive-dict cases get migrated to construct a minimal `SubgraphState` (workflow_id + cve only).
- **Q3 — should `EscalationReason` widen to include the 4 subgraph-time reasons?** S6-04 already emits `Escalate("vuln_index_corrupted")` and `Escalate("filesystem_race")` — these are not in the current `EscalationReason` Literal. Without widening, S6-04 fails Pydantic validation at runtime. Widening additively (`Literal["plugin_extends_cycle", "manifest_rejected", "capability_missing", "filesystem_race", "subprocess_jail_unavailable", "audit_chain_corrupted", "vuln_index_corrupted"]`) preserves the existing 3 members + extends with 4 — additive, contract-snapshot-compatible.

All three resolved from precedent; no user clarification needed.

## Findings

Severity legend: **block** (story unshippable without fix) · **harden** (in-place fix applied) · **nit** (small clarification).

### Consistency lens (highest priority)

#### C-F1 (block → fixed) — `NodeTransition` + variants are redefined, not re-exported
- **What was wrong:** Goal + AC-1 + Implementation outline §2 / §3 prescribed defining `NodeTransition`, `Advance`, `ShortCircuit`, `Escalate` in `src/codegenie/plugins/subgraph.py`. These already exist in `src/codegenie/transforms/outcomes.py` (S1-03 GREEN 2026-05-18). Defining them again would create a class-identity split: `plugins.subgraph.Advance` ≠ `transforms.outcomes.Advance` (different MROs, different `model_fields`), breaking every `isinstance` check, every `TypeAdapter` round-trip, and S6-06's contract-snapshot test.
- **Source of truth:** ADR-0010 Amendment 2026-05-18 ("single canonical declaration site") + S1-03 `__all__` (line 46-77) + S6-04 expected imports (`from codegenie.plugins.subgraph import Advance, ShortCircuit, Escalate` in test file line 131).
- **Fix applied:** Goal + AC + Implementation outline rewritten so `plugins/subgraph.py` (a) **re-exports** `NodeTransition`, `Advance`, `ShortCircuit`, `Escalate` from `codegenie.transforms.outcomes`, (b) defines `SubgraphState` + `SubgraphNode` (genuinely new types). Test for class identity (`subgraph.Advance is outcomes.Advance`) pinned.

#### C-F2 (block → fixed) — `Advance.state` field-type conflict
- **What was wrong:** Story prescribes `Advance(kind="advance", state: SubgraphState)`. Shipped `Advance.state: dict[str, str | int | bool | float]`. The orchestrator (S6-04 outline line 104) does `Advance(state.model_copy(update={"transform": transform}))` — Transform is not a primitive, so a primitive-dict-only `state` cannot carry it. Without resolution, S6-04 can't be implemented.
- **Source of truth:** S1-03 Implementer notes line 407 ("the right move is a new typed payload model, not relaxing `Advance.state`") + S6-04 outline line 102-106.
- **Fix applied:** Story now lands the widening at the canonical site (`transforms/outcomes.py::Advance.state`) — `dict[str, str | int | bool | float]` → `SubgraphState` (replacement, not union, per S1-03's own forward guidance "new typed payload model"). New AC requires updating `tests/unit/transforms/test_outcomes.py` parametrised fixtures so the 3 primitive-dict test cases (`Advance(state={"k": 1})`, the `test_advance_state_primitives_only_*` tests) become `Advance(state=_minimal_subgraph_state())`. The widening is acknowledged as a one-touch amendment to the S1-03 surface — additive in spirit (the Pydantic-model surface SUBSUMES the primitive-dict surface), contract-snapshot-compatible (field NAME unchanged; field TYPE widened; S6-06 contract snapshot tracks names not exact types per ADR-0001).

#### C-F3 (block → fixed) — `EscalateReason` (4 members) vs shipped `EscalationReason` (3 members)
- **What was wrong:** Story introduces a new `EscalateReason` Literal with 4 system-level reasons (`filesystem_race`, `subprocess_jail_unavailable`, `audit_chain_corrupted`, `vuln_index_corrupted`). Shipped `EscalationReason` is `Literal["plugin_extends_cycle", "manifest_rejected", "capability_missing"]`. S6-04 already emits `Escalate("vuln_index_corrupted")` (line 102) and `Escalate("filesystem_race")` (line 106) — neither is in the current Literal. Either the existing Literal is wrong, or two parallel Literals will exist.
- **Source of truth:** ADR-0010 Amendment 2026-05-18 (single declaration point) + S6-04 outline (already references the 4 system-level reasons).
- **Fix applied:** Story now amends `EscalationReason` at the canonical site (`transforms/outcomes.py`) to the 7-member union: `Literal["plugin_extends_cycle", "manifest_rejected", "capability_missing", "filesystem_race", "subprocess_jail_unavailable", "audit_chain_corrupted", "vuln_index_corrupted"]`. The existing 3 members continue to type-check pre-subgraph escalation paths (resolver / capability mint); the new 4 cover in-subgraph escalations. Name stays `EscalationReason` (not `EscalateReason`); test `test_outcomes.py::test_reason_taxonomy_members` (line 323) is updated to assert the 7-member set. Additive Literal widening per ADR-0010 §Pattern fit (subset of previous Literal continues to type-check).

#### C-F4 (harden → fixed) — wrong import for `RemediationOutcome`
- **What was wrong:** TDD plan red test imports `from codegenie.transforms.transform import RemediationOutcome` (line 97). `RemediationOutcome` lives in `codegenie.transforms.outcomes`, not `transform`.
- **Source of truth:** `src/codegenie/transforms/outcomes.py:68` (in `__all__`).
- **Fix applied:** TDD plan imports corrected to `from codegenie.transforms.outcomes import RemediationOutcome, Validated, RemediationNotApplicable, RemediationFailed, RemediationError` and similar.

#### C-F5 (harden → fixed) — `Discriminator("kind")` callable form vs repo convention `Field(discriminator="kind")`
- **What was wrong:** Implementation outline §2 prescribed `from pydantic import ... Discriminator` and `NodeTransition = Annotated[Advance | ShortCircuit | Escalate, Discriminator("kind")]`. The repo has 5 existing discriminated unions all using `Annotated[..., Field(discriminator="kind")]`; the callable `Discriminator(...)` form is for *computed* discriminators (S1-03 Implementer notes line 397).
- **Source of truth:** S1-03 explicit convention; existing `src/codegenie/transforms/outcomes.py:347` uses `Field(discriminator="kind")`.
- **Fix applied:** Since C-F1 fixes the redefinition to a re-export, this is automatically resolved — `plugins/subgraph.py` imports the already-defined NodeTransition. Implementation outline updated to remove `Discriminator(...)` reference entirely.

### Coverage lens

#### C-Cv1 (harden → fixed) — no AC pins class-identity round-trip across re-export
- **What was wrong:** Without an explicit AC, an executor could redefine `Advance` in `plugins/subgraph.py` instead of re-exporting — every isinstance check would still pass against the new local class, every round-trip test against the local TypeAdapter would still succeed, but cross-module identity would break (`plugins.subgraph.Advance is outcomes.Advance` would be False, S6-06 contract snapshot would split).
- **Fix applied:** New AC: `from codegenie.plugins.subgraph import Advance as A; from codegenie.transforms.outcomes import Advance as B; assert A is B`. Same for `ShortCircuit`, `Escalate`, `NodeTransition`. Test pinned by name (`test_re_exports_are_identity_with_outcomes`).

#### C-Cv2 (harden → fixed) — no AC pins `SubgraphState.model_copy(update={...})` immutability + field-type preservation
- **What was wrong:** The orchestrator's only mutation pattern is `state.model_copy(update={...})`. A wrong implementation that made `SubgraphState` mutable (`frozen=False`) would pass every other AC. The original AC only said "frozen=True, extra=forbid" without verifying it. Also no AC pinned that `model_copy(update={"resolution": resolution})` returns a new SubgraphState with `.resolution` field correctly typed.
- **Fix applied:** Two new ACs:
  1. **AC-frozen-mutation-rejected** — attempting `state.workflow_id = WorkflowId("other")` raises `ValidationError`.
  2. **AC-model-copy-preserves-types** — `s2 = s.model_copy(update={"resolution": resolution_fixture})` results in `isinstance(s2, SubgraphState)` AND `s2.resolution is resolution_fixture` AND `s2.workflow_id == s.workflow_id`.

#### C-Cv3 (harden → fixed) — no AC for unknown-reason rejection on `Escalate`
- **What was wrong:** Story tested `Escalate(reason="filesystem_race")` (line 118 of TDD plan) but did not pin that a non-member like `Escalate(reason="bogus_reason")` raises `ValidationError`. Without this AC, a wrong implementation widening `EscalationReason` to `str` would silently pass.
- **Fix applied:** New AC: `Escalate(reason="bogus")` raises `ValidationError`. Test pinned by name.

#### C-Cv4 (harden → fixed) — no subprocess-mypy negative test for `assert_never` exhaustiveness
- **What was wrong:** Story's `test_orchestrator_outer_loop_pattern_match_is_exhaustive` (line 181-200 of original) runs 3 instances through a match block and never reaches the `assert_never` arm — the test verifies "every variant has a current case arm", not the **type-time enforcement** that future additions force consumers to update. The real protection is mypy `--strict` reading `assert_never(unexpected)` and confirming variant exhaustion (S1-03 AC-9a precedent).
- **Source of truth:** `tests/unit/transforms/test_outcomes_mypy_negative.py` ships exactly this pattern for `RecipeOutcome`.
- **Fix applied:** New AC + TDD plan entry — `tests/unit/plugins/test_subgraph_mypy_negative.py` ships a subprocess-mypy fixture: write a temp module that `match`-es over `NodeTransition` with one variant arm intentionally missing + `assert_never(unexpected)`, subprocess-invoke `mypy --strict`, assert non-zero exit + `"assert_never"` in stdout. Mirrors S1-03's `test_outcomes_mypy_negative.py`.

#### C-Cv5 (harden → fixed) — no AC for forward-reference handling of unreleased types
- **What was wrong:** `SubgraphState` references `Transform` (S1-04 — shipped), `Bundle` (S3-04 — shipped), `PluginResolution` (S2-04 — shipped via `ConcreteResolution`), `TrustOutcome` (S6-02 — story `Done` but not yet shipped on this branch; check via grep — NOT in `src/codegenie/`). Without forward-ref discipline, the import-time `from codegenie.transforms.trust_scorer import TrustOutcome` will fail until S6-02 lands.
- **Fix applied:** Implementation outline pins `from __future__ import annotations` + `if TYPE_CHECKING:` guards for `TrustOutcome` (until S6-02 ships); the `SubgraphState.trust_outcome: TrustOutcome | None = None` field uses forward-reference string. AC: `import codegenie.plugins.subgraph` succeeds with no `ModuleNotFoundError` regardless of whether `TrustOutcome` has been merged. Document this build-order dependency explicitly in Notes for the implementer.

#### C-Cv6 (nit → fixed) — no AC for `__all__` exact-set discipline
- **What was wrong:** Story did not pin the `__all__` of `plugins/subgraph.py`. S1-01/S1-03 set the convention of an exact-set assertion (S1-01 `__all__` discipline is a load-bearing fence).
- **Fix applied:** AC pins `set(plugins.subgraph.__all__) == {"SubgraphNode", "SubgraphState", "NodeTransition", "Advance", "ShortCircuit", "Escalate"}` (6 names — 2 new + 4 re-exports).

### Test-quality lens

#### T-Q1 (harden → fixed) — `_failed_outcome` is `...` placeholder
- **What was wrong:** TDD plan line 131-134:
  ```python
  def _failed_outcome() -> RemediationOutcome:
      # Construct a minimal Failed variant (signature TBD by S1-03).
      ...
  ```
  S1-03 has shipped; the construction is no longer TBD. An executor copying this verbatim writes an `... `-only function and every test that calls `_failed_outcome()` returns `None`.
- **Fix applied:** Stub fleshed out: `return RemediationFailed(error=RemediationError(error_id=ErrorId("test.stub"), message="stub failure"))`. Imports adjusted accordingly. (Note: per AC-7 the `Validated` variant is also valid — story now uses `RequiresHumanReview(reason="no_concrete_match")` to vary the test surface.)

#### T-Q2 (harden → fixed) — `test_sync_run_fails_isinstance` is internally contradictory
- **What was wrong:** Test docstring (line 148-151 of original) says: "@runtime_checkable Protocols can't structurally check async-vs-sync; this test asserts the typing expectation via mypy." But the test body then tries to assert a runtime `TypeError` via `asyncio.get_event_loop().run_until_complete(node.run(...))` — which is a runtime check, not a mypy check. Two problems: (a) `asyncio.get_event_loop()` is deprecated in Python 3.12+ when no current loop exists; (b) the runtime check the test claims doesn't exist *is* what the test does, and it's flaky.
- **Fix applied:** Test replaced with two pieces:
  1. A simple `assert isinstance(_SyncRunNode(), SubgraphNode) is True` — documenting the PEP 544 limitation (Protocol's `isinstance` does not introspect sync-vs-async).
  2. A subprocess-mypy negative test (the C-Cv4 fix) covers the mypy enforcement separately.
  The fragile `asyncio.get_event_loop()` line is removed.

#### T-Q3 (harden → fixed) — Protocol negative-conformance only tests `_MissingRunNode`
- **What was wrong:** Original asserts `not isinstance(_MissingRunNode(), SubgraphNode)` but does not test wrong-arity (`run(self)` taking no args) or wrong-name (`run` as a class attribute). A wrong implementation that defined `SubgraphNode` as `Protocol` with no `run` method at all (e.g., empty Protocol — every class would pass isinstance) would still pass this test.
- **Fix applied:** Added two negative cases:
  - `_NoMembersNode` with no `run` method at all → `not isinstance(_NoMembersNode(), SubgraphNode)`.
  - `_RunAsAttribute` where `run = 42` (class attribute, not callable) → behaviour pinned: Protocol's `isinstance` returns True (since `run` exists as an attribute); the mypy-strict check is what catches the misuse. Documented explicitly so an executor doesn't try to over-strengthen the runtime check.

#### T-Q4 (nit → fixed) — `asyncio.get_event_loop().run_until_complete(...)` instead of `asyncio.run(...)`
- Replaced everywhere with `asyncio.run(...)` (per Python 3.11+ idiom).

### Design-patterns lens

#### D-P1 (harden → fixed) — extension-by-addition not documented
- **What was wrong:** Story's "Out of scope" lists Phase-4-specific extensions but doesn't pin the kernel/extract discipline: SubgraphState is the kernel, plugins extend by adding NEW fields (`Field(default=None)`) — never edit existing field types. Without this in Notes-for-implementer, a Phase-4 LLM-fallback story might widen `recipe_outcome: RecipeOutcome | None` to `RecipeOutcome | LLMFallbackOutcome | None`, breaking type-narrowing throughout.
- **Fix applied:** Notes-for-implementer adds an explicit paragraph: "Extension by addition — Phase 4/7 widen SubgraphState by adding NEW Optional fields, never by retyping existing ones. The discriminated union `NodeTransition` widens only via the canonical `transforms/outcomes.py` site + ADR amendment + S6-06 contract-snapshot baseline bump. Two parallel `Advance/ShortCircuit/Escalate` types under `plugins/` are explicitly forbidden."

#### D-P2 (harden → fixed) — `SubgraphState` field optionality is not explained
- **What was wrong:** Original AC lists all SubgraphState fields as `Optional` (default None). A reader doesn't know which fields are required at SubgraphState construction time vs which fill in as nodes advance. Confusing for an executor; trivial source of "field None on read" bugs.
- **Fix applied:** Field grouping clarified in AC: `workflow_id: WorkflowId` + `cve: CveId` are required at construction (no default); the 6 accumulator fields (`resolution`, `bundle`, `recipe_outcome`, `transform`, `trust_outcome`, `branch`) default to None. Notes-for-implementer documents which node populates which field (`IngestCveNode` → resolution; `MatchRecipeNode` → recipe_outcome.plan; `ApplyRecipeNode` → transform; `Stage6ValidateNode` → trust_outcome; `WriteBranchNode` → branch). This is a documentation-only change; the structural choice (frozen, optional accumulators) is unchanged.

#### D-P3 (nit → not fixed, surfaced as Note) — could SubgraphState use a sum type per stage?
- **Observation:** A more rigorous design would make illegal states unrepresentable via a sum type: `SubgraphStage = StagePreResolution(workflow_id, cve) | StagePostResolution(workflow_id, cve, resolution) | StagePostBundle(...) | ...` — each stage carries only the fields that exist by that point.
- **Decision:** **Surface as Note only, do not change.** Rule 2 (Simplicity First): the 6-field accumulator pattern with Optional defaults is well-precedented (S2-04 `ConcreteResolution.composed_tccm`, Phase 5 `GateContext`). A 5-variant sum type for the 5 stages would be more pattern-correct but force every node to dispatch on stage. Three similar lines is better than premature abstraction. If Phase-6's LangGraph migration finds value in stage-typed state, that's the right time to extract.

## Edits applied

All edits are in-place. The story file's `Validation notes` block records the changes. Summary:

1. **Goal rewritten** — `plugins/subgraph.py` now (a) re-exports `NodeTransition`/`Advance`/`ShortCircuit`/`Escalate` from `transforms/outcomes.py`, (b) defines the new `SubgraphNode` Protocol + `SubgraphState`, (c) lands amendments to `transforms/outcomes.py` widening `Advance.state` → `SubgraphState` and `EscalationReason` → 7 members.

2. **Acceptance criteria** — rewritten/added:
   - AC pinning re-export class identity (C-Cv1).
   - AC pinning `SubgraphState` frozen + model_copy preserves types (C-Cv2).
   - AC pinning `Escalate(reason="bogus")` raises (C-Cv3).
   - AC pinning subprocess-mypy negative test for exhaustiveness (C-Cv4).
   - AC pinning `import codegenie.plugins.subgraph` succeeds before S6-02 lands (C-Cv5).
   - AC pinning `__all__` exact-set (C-Cv6).
   - AC pinning the amendment of `EscalationReason` member set (C-F3) — including a TDD-plan update for `tests/unit/transforms/test_outcomes.py::test_reason_taxonomy_members`.
   - AC pinning the amendment of `Advance.state` type at canonical site (C-F2) — including a TDD-plan update for `tests/unit/transforms/test_outcomes.py` parametrised fixtures.
   - SubgraphState field grouping (required vs accumulator) documented in AC.

3. **Implementation outline** — rewritten to land both files (`plugins/subgraph.py` + amendments to `transforms/outcomes.py`) + the test file updates. `Discriminator("kind")` mention removed.

4. **TDD plan red test** — corrected imports (C-F4), fleshed-out `_failed_outcome` stub (T-Q1), removed deprecated `asyncio.get_event_loop()` (T-Q4), replaced `test_sync_run_fails_isinstance` with the pair (PEP 544 doc + subprocess-mypy) per T-Q2.

5. **Notes for the implementer** — extended with the C-F1/C-F2/C-F3 reconciliation rationale, the D-P1 extension-by-addition paragraph, and the D-P2 field-grouping explanation. The D-P3 "5-stage sum type alternative" surfaced as an option for Phase 6.

6. **ADRs honored** updated — added `ADR-0010 Amendment 2026-05-19` (the EscalationReason widening + Advance.state widening) reference.

## Verdict

**HARDENED.** Ready for `phase-story-executor`. The reconciliation with shipped S1-03 reality + the typed `SubgraphState` payload + the 7-member `EscalationReason` covers the Gap-1 fix correctly while preserving the single-declaration-site discipline of ADR-0010.
