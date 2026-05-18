# Story S6-03 — `FallbackTier.on_validated` harvest hook with confidence gate

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** Ready
**Effort:** M
**Depends on:** S6-01 (FallbackTier shell), S4-06 (`SolvedExampleWriter` + `_phase4_local_capability_mint`)
**ADRs honored:** ADR-0009 (inline auto-harvest gated by `TrustOutcome.passed AND confidence == "high"`; Module Boundary not Capability), ADR-0004 (`PlanOutcome` wraps `RecipeOutcome`)

## Context

Roadmap exit criterion #2 — "Re-running the same case hits RAG, not LLM, and produces an equivalent fix at lower cost" — requires that the solved-example store **contains** the harvested outcome by the time the second workflow runs. The critic surfaced (`critique.md §"[B] §4"`) that operator-CLI-only harvest meets the criterion only by test scaffolding; unconditional inline harvest poisons the corpus.

[ADR-04-0009](../ADRs/0009-inline-auto-harvest-confidence-gate.md) threads the needle: inline harvest **wired into `FallbackTier.on_validated(outcome, trust)`** firing **iff** `trust.passed AND trust.confidence == "high"`. Capability is `SolvedExampleWriteCapability` minted via the module-private `_phase4_local_capability_mint(workflow_id, chain_head)` (interim shim — Phase 5 supersedes). The harvest gate is a *named* `ConfidenceGate.passes(trust)` Specification — testable in isolation; future second-knob amendments are additive AND-clauses.

S6-01 stubbed `on_validated` raising `NotImplementedError`. This story lands the production-behavior hook, the `HarvestSkipped` audit event for the gated-out path, and the unit test pinning the gate semantics. The roadmap-exit-criterion E2E test (`tests/integration/test_phase4_e2e_replay_lands_rag.py`) is S7-07 and consumes this hook.

## References — where to look

- **Architecture:** [phase-arch-design.md §Control flow lines 813–818](../phase-arch-design.md) (`on_validated` steps 10–12); §Component 1 internal structure (`on_validated` part); §Component 10 — `SolvedExampleWriter` (capability mint); §Edge case row 18 (harvest gating).
- **Phase ADRs:** [ADR-04-0009](../ADRs/0009-inline-auto-harvest-confidence-gate.md) (the whole story is this ADR's implementation); [ADR-04-0004](../ADRs/0004-plan-outcome-wraps-recipe-outcome.md) (PlanOutcome is what `on_validated` matches on).
- **Production ADRs:** [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) (`TrustOutcome.passed` + `confidence` shape — what the gate reads); [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md) (`SolvedExampleHarvested` / `HarvestSkipped` audit events).
- **Source design:** [final-design.md §Component 9 — SolvedExampleWriter](../final-design.md); §Departures from all three inputs item 4 (inline + confidence gate); §Goal "Inline auto-harvest gate".
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md) Features delivered (`on_validated` bullet); §Step 4 risks (chromadb writer contention).
- **Existing code:** `src/codegenie/fallback/tier.py` (S6-01 stub); `src/codegenie/rag/ingest.py` (S4-06 — `_phase4_local_capability_mint`, `ingest_solved_example`); `src/codegenie/fallback/plan_outcome.py` (S1-03).

## Goal

Implement `FallbackTier.on_validated(outcome: PlanOutcome, trust: TrustOutcome) -> None` so that on `trust.passed AND trust.confidence == "high"` and `outcome` being `AppliedFromLlm` (or the AppliedFromRecipe variants designated for harvest), the tier mints capability via `_phase4_local_capability_mint(workflow_id, chain_head)`, calls `ingest_solved_example(...)` under the store's `asyncio.Lock`, and emits `SolvedExampleHarvested`; otherwise emits `HarvestSkipped(reason)`.

## Acceptance criteria

- [ ] `async def on_validated(self, outcome: PlanOutcome, trust: TrustOutcome) -> None` signature exact; `mypy --strict` clean.
- [ ] **Gate composition is a named `ConfidenceGate.passes(trust)` Specification** (per ADR-0009 §Pattern fit) — `tests/unit/fallback/test_confidence_gate.py` covers each clause separately: `passed=False AND confidence="high"` → False; `passed=True AND confidence="medium"` → False; `passed=True AND confidence="high"` → True; `passed=True AND confidence="low"` → False.
- [ ] **`SolvedExampleHarvested` event emitted** with fields `{plan_outcome_digest, repo_snapshot_sha, solved_example_id}` exactly once when the gate passes and ingest succeeds.
- [ ] **`HarvestSkipped(reason)` event** fires with one of `{"low_confidence", "trust_failed", "outcome_not_harvestable"}` when the gate blocks. Asserted by table-driven test over the three rejection reasons.
- [ ] **Capability minted via `_phase4_local_capability_mint(workflow_id, chain_head)`** — never via raw `SolvedExampleWriteCapability(...)`. Test imports `_phase4_local_capability_mint` from `codegenie.rag.ingest` and asserts the call signature; the existing `import-linter` contract (S4-06) blocks `tier.py` from any *other* mint path.
- [ ] **Outcome-variant dispatch**: `match outcome` over `PlanOutcome`:
  - `AppliedFromLlm` ⇒ candidate for harvest (carries `few_shot_ref`, `response_id`).
  - `AppliedFromRecipe` ⇒ `HarvestSkipped(reason="outcome_not_harvestable")` — recipe-applied outcomes are already represented by their recipe; harvesting them is a known anti-pattern (final-design §Open question on second-knob).
  - `RagOnlyApplicable` ⇒ `HarvestSkipped(reason="outcome_not_harvestable")` — pure-RAG case is not a new example.
  - `Refused` ⇒ `HarvestSkipped(reason="outcome_not_harvestable")`.
  - `case _: assert_never(outcome)` final arm — mypy `--strict` catches missing variant.
- [ ] **Idempotence**: calling `on_validated` twice with the same `(plan_outcome_digest, repo_snapshot_sha)` ingests once; the second call detects via chroma's natural ID dedup OR the canonical YAML path-collision path and emits `SolvedExampleHarvestedDeduped` (or skips with `HarvestSkipped(reason="already_harvested")`). Asserted by `tests/unit/fallback/test_on_validated_idempotent.py` (arch §Harness §Idempotence: "second attempt on same key is a no-op write").
- [ ] **Store contention does not deadlock**: `tests/integration/test_phase4_on_validated_under_lock.py` calls `on_validated` twice via `asyncio.gather` against the same store; both eventually return; chain-head advances monotonically (composes with S4-08 / Gap 3).
- [ ] **No-op when gate fails**: `_phase4_local_capability_mint` is **not called**, `ingest_solved_example` is **not called** when the gate blocks; mocked + asserted with `pytest.fail` side-effect.
- [ ] `make check`, `mypy --strict`, `make lint-imports` (capability-mint contract) all green.

## Implementation outline

1. Replace the `NotImplementedError` stub in `src/codegenie/fallback/tier.py` with the real `async def on_validated(...)`.
2. Introduce `class ConfidenceGate` (or a free-function `confidence_gate_passes(trust) -> bool`) as a named Specification with named clauses (`_TrustPassed`, `_HighConfidence`); compose with `AND`. Land at `src/codegenie/fallback/confidence_gate.py`.
3. In `on_validated`:
   - `match outcome` over `PlanOutcome` — only `AppliedFromLlm` is harvest-eligible; others ⇒ `HarvestSkipped(reason="outcome_not_harvestable")`.
   - If eligible: `if not self._confidence_gate.passes(trust): emit HarvestSkipped(reason=...); return`.
   - Else: `capability = _phase4_local_capability_mint(workflow_id=ctx.workflow_id, chain_head=ctx.chain_head)`; `solved_example_id = await ingest_solved_example(outcome, store=self._store, embedder=self._embedder, capability=capability)`; emit `SolvedExampleHarvested(...)`.
4. Deduplication on `(plan_outcome_digest, repo_snapshot_sha)` lives inside `ingest_solved_example` (S4-06). `on_validated` only needs to handle the duplicate-result outcome (emit `HarvestSkipped(reason="already_harvested")` if `ingest_solved_example` returns the `Deduped` variant).
5. **Workflow context**: `FallbackTier.__init__` already receives the event log; the `workflow_id` + `chain_head` flow from the orchestrator into `on_validated` via the `TrustOutcome` or a sibling kwarg. If the kwargs aren't enough, extend the `__init__` to carry a `workflow_context: WorkflowContext` collaborator — keep it minimal.
6. Land `tests/unit/fallback/test_on_validated.py`, `test_confidence_gate.py`, `test_on_validated_idempotent.py`; integration test `tests/integration/test_phase4_on_validated_under_lock.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/fallback/test_on_validated.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from codegenie.fallback.tier import FallbackTier
from codegenie.fallback.plan_outcome import AppliedFromLlm, AppliedFromRecipe, Refused
# TrustOutcome from Phase 3
from codegenie.gates.trust import TrustOutcome  # placeholder import path

@pytest.mark.asyncio
async def test_on_validated_harvests_on_high_confidence_llm_outcome(
    tier_under_test, capturing_event_log, harvester_spy,
):
    """ADR-04-0009: production behavior must satisfy roadmap exit #2.
    Why this matters: operator-CLI-only fails the criterion in production behavior."""
    outcome = AppliedFromLlm(
        recipe_outcome_digest=..., few_shot_ref=None, response_id=...,
    )
    trust = TrustOutcome(passed=True, confidence="high")

    await tier_under_test.on_validated(outcome, trust)

    harvester_spy.ingest_solved_example.assert_awaited_once()
    kinds = [e.kind for e in capturing_event_log.recorded]
    assert "SolvedExampleHarvested" in kinds


@pytest.mark.parametrize("trust, expected_reason", [
    (TrustOutcome(passed=True, confidence="medium"), "low_confidence"),
    (TrustOutcome(passed=True, confidence="low"), "low_confidence"),
    (TrustOutcome(passed=False, confidence="high"), "trust_failed"),
])
@pytest.mark.asyncio
async def test_on_validated_skips_when_gate_blocks(
    tier_under_test, capturing_event_log, harvester_spy, trust, expected_reason,
):
    """ADR-04-0009: poisoned-corpus risk bounded — gate must hold."""
    outcome = AppliedFromLlm(...)
    harvester_spy.ingest_solved_example.side_effect = AssertionError(
        "harvester invoked despite blocked gate")

    await tier_under_test.on_validated(outcome, trust)

    harvester_spy.ingest_solved_example.assert_not_awaited()
    skipped = [e for e in capturing_event_log.recorded if e.kind == "HarvestSkipped"]
    assert skipped and skipped[0].reason == expected_reason


@pytest.mark.parametrize("outcome", [
    AppliedFromRecipe(...),
    RagOnlyApplicable(...),
    Refused(reason="PROVENANCE_NOT_APP_LAYER"),
])
@pytest.mark.asyncio
async def test_on_validated_skips_non_llm_outcomes(
    tier_under_test, capturing_event_log, harvester_spy, outcome,
):
    """ADR-04-0009: recipe-applied + rag-only + refused never harvested."""
    trust = TrustOutcome(passed=True, confidence="high")
    await tier_under_test.on_validated(outcome, trust)
    harvester_spy.ingest_solved_example.assert_not_awaited()
    skipped = [e for e in capturing_event_log.recorded if e.kind == "HarvestSkipped"]
    assert skipped[0].reason == "outcome_not_harvestable"


# tests/unit/fallback/test_confidence_gate.py
import pytest
from codegenie.fallback.confidence_gate import ConfidenceGate

@pytest.mark.parametrize("passed, confidence, expected", [
    (True,  "high",   True),
    (True,  "medium", False),
    (True,  "low",    False),
    (False, "high",   False),
    (False, "medium", False),
])
def test_confidence_gate_named_clauses(passed, confidence, expected):
    gate = ConfidenceGate()
    trust = TrustOutcome(passed=passed, confidence=confidence)
    assert gate.passes(trust) is expected
```

### Green — make it pass

- Land `confidence_gate.py` with named clauses.
- Land the real `on_validated` body in `tier.py` per outline.
- Wire `_phase4_local_capability_mint` import and call.

### Refactor — clean up

- Keep `ConfidenceGate` clauses separable for future second-knob additions (e.g., per-task-class trust gating per open question 7).
- Confirm the import-linter contract for `_phase4_local_capability_mint` admits the `tier.py` callsite (per S4-06 already names `src/codegenie/gates/` and `src/codegenie/rag/ingest.py`; `tier.py` must be added to the allowed-callers set in this story if not already).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/tier.py` | Implement `on_validated`. |
| `src/codegenie/fallback/confidence_gate.py` | New — named-clause Specification (ADR-0009 §Pattern fit). |
| `tests/unit/fallback/test_on_validated.py` | New. |
| `tests/unit/fallback/test_confidence_gate.py` | New — clauses table-driven. |
| `tests/unit/fallback/test_on_validated_idempotent.py` | New — `(plan_outcome_digest, repo_snapshot_sha)` idempotence (arch §Harness §Idempotence). |
| `tests/integration/test_phase4_on_validated_under_lock.py` | New — two `asyncio.gather` calls, monotonic chain head (composes with S4-08). |
| `pyproject.toml` or `importlinter` config | Extend S4-06's `_phase4_local_capability_mint` allowed-callers contract if `tier.py` isn't already admitted. |

## Out of scope

- The roadmap-exit-criterion E2E (second-run-hits-RAG) — **S7-07**.
- Phase 5's `GateRunner` swap of `_phase4_local_capability_mint` → `gates._capability_mint` — Phase 5; the shim docstring carries the `# TODO(phase-5)` marker per S4-06.
- Phase 11's merge-webhook post-validate harvest — that's a *second* ingestion path; both call `ingest_solved_example` with different capabilities (Phase 11's concern).
- Operator quarantine path for subtly-wrong harvested examples — Phase 6.5 / Phase 11.

## Notes for the implementer

- The capability is **Module Boundary, not GoF Capability** — Python doesn't have runtime-unforgeable capabilities; `import-linter` is the lint-time backstop. Don't overclaim in docstrings (ADR-0009 §Pattern fit).
- The `ConfidenceGate` must be *named* — a free-form `if trust.passed and trust.confidence == "high" and ...` ladder inside `on_validated` violates the Specification pattern (ADR-0009 §Tradeoffs). Keep the gate composable.
- The `outcome_not_harvestable` skip for `AppliedFromRecipe` is intentional: recipes are deterministic and already in the corpus by virtue of the recipe definition; harvesting them creates duplicate near-identical few-shots and degrades retrieval (final-design open question on second-knob refinement).
- `ingest_solved_example` runs under `asyncio.Lock` inside `SolvedExampleStore` (S4-03). `on_validated` does NOT lock externally — that would double-lock and deadlock under `asyncio.gather`.
- If the integration test under `asyncio.gather` hangs, it's likely the chromadb embedded-mode `add()` blocking the event loop — High-level-impl Step 4 §Risks bullet 3 names the mitigation: wrap in `loop.run_in_executor`. Surface per Global Rule 12 if the 30s contention contract can't be met.
