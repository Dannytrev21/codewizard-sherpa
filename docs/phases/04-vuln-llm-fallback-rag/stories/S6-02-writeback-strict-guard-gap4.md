# Story S6-02 — Writeback strict-guard `(engine_used, TrustScorer.passed, plan_source)` matrix (Gap 4)

**Step:** Step 6 — Ship synchronous gated `writeback_solved_example` + Gap-4 semantics + operator CLI
**Status:** Ready
**Effort:** M
**Depends on:** S6-01 (`writeback_solved_example` happy-path body + triple-write)
**ADRs honored:** ADR-P4-002 (writeback strict-AND guard: `engine_used == "rag_llm"` AND `TrustScorer.passed` AND `plan_source ∈ {rag_fewshot_llm, llm_cold}`), ADR-P4-008 (objective-signal trust — LLM self-confidence is *not* part of the guard), ADR-P4-015 (`SolvedExample` v0.4.0 schema — what counts as a "valid example"), production ADR-0009 (humans always merge — the guard exists to keep the `promoted/` corpus clean), production ADR-0011 (recipe-first three-tier planning — `plan_source` is the discriminator)

## Context
S6-01 landed `writeback_solved_example` as the happy-path triple-write. This story adds the **strict-AND refusal guard** that runs at the top of the function and short-circuits with an audit event whenever any of four conditions fail. The guard is the Phase 4 fix for **Gap 4** as enumerated in `phase-arch-design.md §"Gap analysis"` and in the synthesis ledger row "Writeback timing": it must be **impossible** to grow the solved-example corpus from anything other than a freshly-validated rag-llm run whose plan was produced by a tier that does not already exist in the corpus (`rag_fewshot_llm` or `llm_cold`); cache hits (`query_cache`) and RAG-exact replays (`rag_exact`) refuse to writeback because the example **already exists**. The guard also defends against **engine-spoof attempts** — a `RecipeApplication(engine_used="ncu")` carrying `tier_evidence` shaped like a `rag_llm` run is rejected via cross-field consistency. Failed-validation runs refuse (G4 — no negative-example writeback in Phase 4). Every refusal emits `solved_example.writeback_refused(reason)` carrying the four-condition vector so auditors can replay the decision.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §"Gap analysis" Gap 4` — the verbatim matrix: writeback is on only when `engine_used == "rag_llm"` AND `trust_score.passed` AND `plan_source ∈ {rag_fewshot_llm, llm_cold}` AND the strict-AND signal set is complete. Cache hits and rag-exact replays explicitly skip.
  - `../phase-arch-design.md §"Component design" #6` — `writeback_solved_example` strict guard cross-references this story.
  - `../phase-arch-design.md §"Control flow"` step 9 — Decision point E.
  - `../phase-arch-design.md §"Edge cases"` row EC18 — engine-spoof: `engine_used` claims a different value than `tier_evidence` reveals → refused.
  - `../phase-arch-design.md §"Trust matrix"` — strict-AND TrustScorer signal completeness; missing-field rejection.
  - `../phase-arch-design.md §"Audit chain extension"` — `solved_example.writeback_refused` event payload.
- **Phase ADRs:**
  - `../ADRs/0002-two-tier-writeback-pending-promoted.md` — ADR-P4-002 §Consequences row 2: "writeback refuses when `plan_source ∈ {query_cache, rag_exact}` — the example already exists".
  - `../ADRs/0008-prompt-injection-structural-defenses.md` — ADR-P4-008 — LLM self-confidence is stripped; the guard reads only objective `tier_evidence` + `trust_score`.
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015 — the schema's `extra="forbid"` is a second-line defence against malformed inputs.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — the social contract this guard enforces structurally.
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — `plan_source` is the three-tier discriminator.
- **Source design:**
  - `../final-design.md §"Synthesis ledger" row "Writeback timing"` (winner sum 12/12) — why the guard is strict-AND, not heuristic.
  - `../final-design.md §"Departures from all three inputs"` #1 — the two-tier model only works if `pending/` is provably non-polluting; the guard is the structural enforcement.
- **Existing code:**
  - `src/codegenie/rag/writeback.py` (S6-01) — the function this story prepends a guard to.
  - `src/codegenie/recipes/contract.py` (S5-02) — `TierEvidence.plan_source` Literal type; `RecipeApplication.engine_used`.
  - `src/codegenie/transforms/trust_scorer.py` (Phase 3) — `TrustScore` carries the strict-AND signal dict; `passed: bool`; per-signal `present: bool` flags.

## Goal
Add a top-of-function strict-AND refusal guard to `writeback_solved_example` that refuses (audits + returns without writing) whenever the four-condition matrix `(engine_used == "rag_llm", trust_score.passed, plan_source ∈ {rag_fewshot_llm, llm_cold}, every strict-AND signal present)` is not satisfied, including a cross-field consistency check that defeats engine-spoof attempts.

## Acceptance criteria
- [ ] `writeback_solved_example` runs its strict-AND guard **before** the body-JSON write. On refusal, emits `solved_example.writeback_refused(reason, decision_vector)` and returns `None` (the orchestrator interprets `None` as "do not include in the run report's writeback section"). The function signature changes to `... -> SolvedExample | None`; S6-03 reads the `None` and skips report-writeback accordingly.
- [ ] The guard refuses when **any** of these fail (each surfaced as a distinct `reason` value):
  1. `engine_mismatch` — `recipe_application.engine_used != "rag_llm"`.
  2. `trust_score_failed` — `trust_score.passed != True`.
  3. `plan_source_skip` — `recipe_application.tier_evidence.plan_source in {"query_cache", "rag_exact"}` (the example already exists; writeback would double-count).
  4. `trust_signal_incomplete` — any of the strict-AND signals (`patch_apply_ok`, `npm_ci_ok`, `npm_test_ok`, `lockfile_policy_ok`, `validator_ok`, `cost_ok`) is missing from the `TrustScore.signals` dict, or any has `present=False`.
  5. `engine_spoof` — `engine_used="rag_llm"` but `tier_evidence` is None / shaped inconsistently (e.g. `plan_source` set but `cost_usd == 0` for a non-cache tier; `tier_used="tier3_llm"` with `cost_usd == 0`; `plan_source="rag_fewshot_llm"` with `few_shots_used == 0`; `tier_used` and `plan_source` from different tiers). Conversely, `engine_used="ncu"` carrying a populated `tier_evidence` of any shape is also `engine_spoof`.
- [ ] Each refusal emits `solved_example.writeback_refused(run_id, reason, decision_vector)` exactly once. The `decision_vector` is a Pydantic `BaseModel(extra="forbid", frozen=True)` carrying `engine_used`, `trust_score_passed`, `plan_source`, `signal_present_flags`, `tier_evidence_present`, `tier_evidence_consistent` so audit replay is mechanical.
- [ ] `tests/unit/rag/test_writeback_refuses_on_engine_mismatch.py` — parametrises `engine_used ∈ {"ncu", "openrewrite", None, ""}` × `trust_passed=True` × `plan_source="llm_cold"` → all refused with `reason="engine_mismatch"`; body file is **not** written; chromadb upsert is **not** called; query-key cache is **not** updated.
- [ ] `tests/unit/rag/test_writeback_refuses_on_trustscore_fail.py` — `engine_used="rag_llm"` × `trust_passed=False` × `plan_source="llm_cold"` → refused with `reason="trust_score_failed"`. No writes.
- [ ] `tests/unit/rag/test_writeback_skipped_on_query_cache_source.py` (Gap 4) — `engine_used="rag_llm"` × `trust_passed=True` × `plan_source="query_cache"` → refused with `reason="plan_source_skip"`; no writes; audit emitted. **Rationale:** the example whose plan was replayed already exists in the corpus; writing it again creates duplicates and inflates `count`.
- [ ] `tests/unit/rag/test_writeback_skipped_on_rag_exact_source.py` (Gap 4) — `engine_used="rag_llm"` × `trust_passed=True` × `plan_source="rag_exact"` → refused with `reason="plan_source_skip"`. No writes.
- [ ] `tests/unit/rag/test_writeback_allows_llm_cold.py` — `engine_used="rag_llm"` × `trust_passed=True` × `plan_source="llm_cold"` × all signals present → **allowed**; the triple-write fires per S6-01.
- [ ] `tests/unit/rag/test_writeback_allows_rag_fewshot_llm.py` — `engine_used="rag_llm"` × `trust_passed=True` × `plan_source="rag_fewshot_llm"` × all signals present → **allowed**; triple-write fires.
- [ ] `tests/unit/rag/test_writeback_refuses_on_missing_signal.py` — parametrises each strict-AND signal absent in turn; each individual absence refuses with `reason="trust_signal_incomplete"`. A property test (Hypothesis: any non-empty subset of signals missing) confirms the rejection is universal, not signal-by-signal hard-coded.
- [ ] `tests/unit/rag/test_writeback_rejects_engine_spoof.py` (adversarial) — at least four sub-cases, all refused with `reason="engine_spoof"`:
  1. `engine_used="ncu"` + populated `tier_evidence` (`plan_source="llm_cold"`, `cost_usd > 0`).
  2. `engine_used="rag_llm"` + `tier_evidence=None`.
  3. `engine_used="rag_llm"` + `tier_evidence.tier_used="tier3_llm"` + `cost_usd == 0` (a tier-3 call can't be free).
  4. `engine_used="rag_llm"` + `tier_evidence.plan_source="rag_fewshot_llm"` + `tier_evidence.few_shots_used == 0`.
- [ ] `tests/unit/rag/test_negative_example_not_written.py` (G4) — `engine_used="rag_llm"` × `trust_passed=False` (a failed-validation `rag_llm` run) → refused with `reason="trust_score_failed"`; chromadb has zero rows in `vuln_solved_examples_pending` AND `vuln_solved_examples_negative` AND `vuln_solved_examples_promoted`; query-key cache untouched; bodies dir empty. Phase 4 explicitly forbids negative-example writeback (`final-design.md §Goals #4`).
- [ ] `tests/unit/rag/test_writeback_refusal_audit_decision_vector.py` — every refusal emits exactly one `solved_example.writeback_refused` event whose `decision_vector` Pydantic-validates and exactly reflects the input state (round-trips). Two refusals from the same call site must not be possible (the guard returns on the first failure; subsequent checks are short-circuited — Python `and` semantics).
- [ ] `tests/unit/rag/test_writeback_refusal_order_priority.py` — when *multiple* conditions fail simultaneously, the refusal reason is the **highest-priority** one in this order: `engine_mismatch` > `trust_score_failed` > `plan_source_skip` > `trust_signal_incomplete` > `engine_spoof`. Pinning the priority makes audit replay deterministic.
- [ ] `WritebackDecisionVector` is added to `src/codegenie/rag/writeback.py` (or a sibling `_decision_vector.py`) as a `BaseModel(extra="forbid", frozen=True)`. Contract-snapshot test `tests/contracts/test_writeback_decision_vector_snapshot.py` freezes the shape.
- [ ] `mypy --strict`, `ruff check`, `ruff format --check` clean on `src/codegenie/rag/writeback.py`. Coverage floor 95/90 holds (the new branches add ~6 paths; tests above cover all).

## Implementation outline
1. Define `WritebackDecisionVector` Pydantic model and the `WritebackRefusalReason` `Literal["engine_mismatch", "trust_score_failed", "plan_source_skip", "trust_signal_incomplete", "engine_spoof"]` type.
2. Add a private module-level helper `_check_writeback_guard(recipe_application, trust_score) -> WritebackRefusalReason | None`:
   - Order the five checks in the priority above. Return the first failure's reason; return `None` if all pass.
   - For `engine_spoof`, factor out `_is_tier_evidence_consistent(engine_used, tier_evidence) -> bool` — pure, side-effect-free, easy to property-test.
3. Refactor `writeback_solved_example`: insert the guard call as the first statement; on `reason is not None`, emit `solved_example.writeback_refused(run_id=run_id, reason=reason, decision_vector=...)` and `return None`. Change the return type annotation to `SolvedExample | None`.
4. Update S6-01's happy-path tests that called the function expecting non-None — they all configure inputs that satisfy the guard, so the assertion `assert example is not None` is the only change.
5. Write the eleven new tests above. Many share a parametrised fixture builder `_application_for(plan_source, engine_used, trust_passed, signals_missing=frozenset(), tier_evidence_overrides=None)` — extract it under `tests/unit/rag/_writeback_fixtures.py`.
6. Wire the strict-AND signal completeness check by reading `trust_score.signals` (a `dict[str, SignalRecord]` per Phase 3). The set of required signals is `frozenset({"patch_apply_ok", "npm_ci_ok", "npm_test_ok", "lockfile_policy_ok", "validator_ok", "cost_ok"})` — pull this from a single named constant in `transforms/trust_scorer.py` so a future addition is one place. If the Phase-3 constant doesn't exist, add it now (this is a Phase 3 in-place edit? No — it's a *new* named constant; the existing strict-AND logic stays byte-identical).
7. Audit-emit discipline: every refusal path emits exactly once. Use a `try/finally`-free linear flow; the function shape is `reason = _check_writeback_guard(...); if reason: audit.emit(...); return None; <happy path from S6-01>`.

## TDD plan — red / green / refactor

### Red
Test file path: `tests/unit/rag/test_writeback_skipped_on_query_cache_source.py`
```python
from unittest.mock import MagicMock
from codegenie.rag.writeback import writeback_solved_example


def test_query_cache_source_refuses_writeback():
    """Gap 4: a plan replayed from query_key_cache is not written back — the example already exists."""
    store, cache, audit, embedding = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    recipe_application = _application_for(
        engine_used="rag_llm",
        plan_source="query_cache",
        tier_used="tier1_cache",
        cost_usd=0,
        few_shots_used=0,
    )
    trust_score = _trust_passed()

    result = writeback_solved_example(
        run_id="r1", advisory=..., recipe_selection=..., recipe_application=recipe_application,
        validation_outcomes=..., cost_report=..., store=store, query_key_cache=cache,
        audit=audit, embedding=embedding, trust_score=trust_score,
    )

    assert result is None, "writeback must refuse on query_cache plan_source"
    store.write.assert_not_called()
    cache.put.assert_not_called()
    audit.emit.assert_called_once()
    name, payload = audit.emit.call_args.args
    assert name == "solved_example.writeback_refused"
    assert payload["reason"] == "plan_source_skip"
    assert payload["decision_vector"]["plan_source"] == "query_cache"
```

`tests/unit/rag/test_writeback_rejects_engine_spoof.py`
```python
import pytest


@pytest.mark.parametrize(
    "engine_used,tier_evidence_overrides,expected_reason",
    [
        # 1. ncu engine with rag-shaped tier_evidence — classic spoof
        ("ncu", {"plan_source": "llm_cold", "cost_usd": "0.06", "tier_used": "tier3_llm"}, "engine_spoof"),
        # 2. rag_llm but no tier_evidence
        ("rag_llm", None, "engine_spoof"),
        # 3. rag_llm + tier3_llm + zero cost — impossible
        ("rag_llm", {"tier_used": "tier3_llm", "plan_source": "llm_cold", "cost_usd": "0"}, "engine_spoof"),
        # 4. rag_llm + fewshot + zero few-shots — impossible
        ("rag_llm", {"tier_used": "tier3_llm", "plan_source": "rag_fewshot_llm", "few_shots_used": 0,
                     "cost_usd": "0.05"}, "engine_spoof"),
    ],
)
def test_engine_spoof_rejected(engine_used, tier_evidence_overrides, expected_reason):
    app = _application_for(engine_used=engine_used, tier_evidence_overrides=tier_evidence_overrides)
    result = writeback_solved_example(..., recipe_application=app, ...)
    assert result is None
    # ...audit assertions...
```

`tests/unit/rag/test_negative_example_not_written.py`
```python
def test_failed_validation_rag_llm_run_does_not_writeback(tmp_path):
    """G4 — Phase 4 explicitly forbids negative-example writeback."""
    store, cache, audit, embedding = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    recipe_application = _application_for(engine_used="rag_llm", plan_source="llm_cold")
    trust_score = _trust_failed(failing_signals={"npm_test_ok"})  # npm test red

    result = writeback_solved_example(..., recipe_application=recipe_application,
                                       trust_score=trust_score, ...)

    assert result is None
    bodies_dir = tmp_path / ".codegenie/rag/bodies"
    assert not any(bodies_dir.iterdir()) if bodies_dir.exists() else True
    store.write.assert_not_called()
    cache.put.assert_not_called()
```

### Green
- Implement `_check_writeback_guard` with the five checks in the priority order above; return the first matching `WritebackRefusalReason`.
- Implement `_is_tier_evidence_consistent` as a switch on `(engine_used, tier_evidence)`: `("ncu", _)` → False unless `tier_evidence is None`; `("rag_llm", None)` → False; `("rag_llm", te)` → consult the per-tier shape: tier3 → `cost_usd > 0`; `rag_fewshot_llm` → `few_shots_used > 0`; `(tier_used, plan_source)` agreement check.
- Wire the guard call at the top of `writeback_solved_example`; on refusal, emit the audit event with the populated `WritebackDecisionVector` and `return None`.
- Update `writeback_solved_example`'s return annotation to `SolvedExample | None`.

### Refactor
- Move `_check_writeback_guard`, `_is_tier_evidence_consistent`, `WritebackDecisionVector`, `WritebackRefusalReason` into `src/codegenie/rag/_writeback_guard.py` — keeps `writeback.py` under the LOC ceiling and makes the guard independently unit-testable.
- The five `Literal` reason values are an enum-shaped contract — snapshot-test them under `tests/contracts/test_writeback_refusal_reasons_snapshot.py` so any addition is conspicuous (Phase 5+ may add reasons; the Literal expansion is the audit trail).
- Add a structured `rag.writeback.guard.evaluated` debug event (one per call, always emitted, payload = `decision_vector`) — Step 7's audit-completeness test (G14) wants every guard evaluation, not just refusals, on the chain. Confirm with the audit-events table in `phase-arch-design.md §"Audit chain extension"` before adding.
- Property-test the priority ordering: Hypothesis generates a `WritebackDecisionVector` with multiple failing fields, asserts the returned reason is always the priority-winning one.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/rag/writeback.py` | Prepend guard call; change return type to `SolvedExample \| None`. |
| `src/codegenie/rag/_writeback_guard.py` | NEW — `_check_writeback_guard`, `_is_tier_evidence_consistent`, `WritebackDecisionVector`, `WritebackRefusalReason`. |
| `src/codegenie/transforms/trust_scorer.py` | Add the named constant `REQUIRED_STRICT_AND_SIGNALS: frozenset[str]` (additive; no behaviour change). |
| `tests/unit/rag/_writeback_fixtures.py` | NEW — `_application_for(...)`, `_trust_passed()`, `_trust_failed(failing_signals)` helpers shared by the eleven test files below. |
| `tests/unit/rag/test_writeback_refuses_on_engine_mismatch.py` | NEW |
| `tests/unit/rag/test_writeback_refuses_on_trustscore_fail.py` | NEW |
| `tests/unit/rag/test_writeback_skipped_on_query_cache_source.py` | NEW — Gap 4 |
| `tests/unit/rag/test_writeback_skipped_on_rag_exact_source.py` | NEW — Gap 4 |
| `tests/unit/rag/test_writeback_allows_llm_cold.py` | NEW — happy path 1 |
| `tests/unit/rag/test_writeback_allows_rag_fewshot_llm.py` | NEW — happy path 2 |
| `tests/unit/rag/test_writeback_refuses_on_missing_signal.py` | NEW — Hypothesis property |
| `tests/unit/rag/test_writeback_rejects_engine_spoof.py` | NEW — adversarial |
| `tests/unit/rag/test_negative_example_not_written.py` | NEW — G4 |
| `tests/unit/rag/test_writeback_refusal_audit_decision_vector.py` | NEW |
| `tests/unit/rag/test_writeback_refusal_order_priority.py` | NEW |
| `tests/contracts/test_writeback_decision_vector_snapshot.py` | NEW — Pydantic schema dump. |
| `tests/contracts/test_writeback_refusal_reasons_snapshot.py` | NEW — Literal expansion is conspicuous. |

## Out of scope
- **The triple-write body itself** — handled by S6-01; this story only prepends a guard.
- **Orchestrator branch promotion to call this function** — handled by S6-03. The Step-1 stub still doesn't call `writeback_solved_example` after this story; it's the next story that lights the wire.
- **`--no-rag` / `--no-llm` CLI semantics** — handled by S6-03 (Gap 4 CLI side); this story is the **runtime guard** half of Gap 4.
- **Calibration / list / show CLI** — handled by S6-04.
- **Phase 11 promoter** — `merge_status="pending_human"` is still the only status this writer writes; promotion is Phase 11 territory.
- **Negative-example anti-pattern collection** — explicitly forbidden in Phase 4 (G4); Phase 15's recipe-authoring lens reopens this question.

## Notes for the implementer
- **Priority ordering is load-bearing.** When multiple conditions fail, audit-replay determinism matters more than completeness; pick one reason and surface it. The priority encoded in `test_writeback_refusal_order_priority.py` is the contract — do not reorder without an ADR amendment.
- **Engine-spoof checks are cross-field, not single-field.** A reviewer who sees `if engine_used == "rag_llm": ...` without checking `tier_evidence` shape consistency should reject the PR. The four sub-cases in `test_writeback_rejects_engine_spoof.py` are the floor, not the ceiling — add a fifth if you can think of one (encouraged).
- **`plan_source ∈ {query_cache, rag_exact}` is a refusal, not an error.** The audit event reason is `plan_source_skip` (not `_failed`) because the example already exists in the corpus — writing it again would inflate `count`, drift cosine distributions, and break the recall@3 canary's baseline. This is correct behaviour from the user's perspective: tier-1 / tier-2-exact hits are reuse, not learning.
- **G4 — no negative-example writeback in Phase 4.** A failed-validation `rag_llm` run is the most tempting "almost successful" case to record. Resist. Phase 15's recipe-authoring lens may want negatives as anti-patterns, but introducing a `negative` collection in Phase 4 means operators see it, query it accidentally, and the schema migration becomes a Phase 15 problem with users in the field. The `vuln_solved_examples_negative` chromadb collection from S4-04 exists for forward compatibility but is never written by this function in Phase 4.
- **LLM self-reported confidence is *not* a guard input** (ADR-P4-008). If a future engineer suggests "well, the LLM said it was 95% confident, let's relax the strict-AND signal completeness check" — that's exactly the failure mode the production ADR-0008 forbids. The guard reads only `tier_evidence` (objective, from `RagLlmEngine`) and `trust_score` (objective, from Phase 3 `TrustScorer`). `confidence_self_reported` is stripped by `OutputValidator` in Step 2 and never reaches this guard.
- **The `decision_vector` audit payload is for forensic replay.** A reviewer reading a `solved_example.writeback_refused` event months later must be able to reconstruct the exact decision input — that's why every field is explicit (`engine_used`, `trust_score_passed`, `plan_source`, `signal_present_flags`, `tier_evidence_present`, `tier_evidence_consistent`) rather than just the reason. Don't compress it.
- **Coverage 95/90 means every guard branch is tested.** The eleven test files above cover the matrix; if a refactor reorders the checks, every test must still pin its reason. If you find yourself adding a new check, write a new ADR (this matrix is ADR-P4-002's `Consequences` row 2) — do not silently add a sixth reason.
- The Step-1 orchestrator stub is **still a `pass`** after this story. S6-03 promotes it to call `writeback_solved_example`; until then this function exists, has its guard, and is unit-tested in isolation. That's intentional — the guard is testable without an orchestrator integration, and the integration story can focus on `--no-rag` / `--no-llm` semantics rather than re-litigating the guard.
