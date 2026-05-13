# Story S4-04 — Implement `rag_lookup` node

**Step:** Step 4 — Implement the ten nodes as thin wrappers over Phase 3/4/5 engines
**Status:** Ready
**Effort:** S
**Depends on:** S4-01
**ADRs honored:** ADR-0002 (`model_copy(update=...)`), ADR-0012 (per-node tests)

## Context

`rag_lookup` is the recipe-miss path: when Phase 3's `RecipeMatcher` returns `recipe=None`, the edge `route_after_select_recipe` routes here. The node delegates to Phase 4's `RagTier.lookup()`, populates `rag_hit: RagHit | None`, and the downstream edge `route_after_rag` decides `"hit"` vs `"miss"` against the `rag_score_threshold` (default `0.85`, pinned in `tools/policy/graph-thresholds.yaml`). The node itself does **not** consult the threshold — that's the edge's job (`route_after_rag`, S3-02). `rag_lookup`'s contract is simply: call Phase 4's RAG tier, faithfully record what came back, emit the event.

The two interesting test branches are (a) RAG returns a `RagHit` with a high score (threshold-met, downstream routes to `apply_recipe`) and (b) RAG returns either `None` or a low-score hit (threshold-miss, downstream routes to `replan_with_phase4`). This story exercises **both** in its unit tests so that a future regression in `RagTier` shape (e.g., adding a required field) shows up here before integration.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component 5` nodes table — `rag_lookup` row; `../phase-arch-design.md §Scenario 1` (happy-path RAG hit) and `§Scenario 2` (RAG miss → Phase 4 LLM)
- **Phase ADRs:** `../ADRs/0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md`
- **Prior phases:** `../../04-vuln-llm-fallback-rag/final-design.md §1 RagLlmEngine` and surrounding — `RagTier.lookup(advisory, repo_ctx) -> RagHit | None`; `RagHit` shape includes `score: float`, `example_id: str`, ...
- **Source design:** `../final-design.md §Component 5`; `../final-design.md §Conflict-resolution row 11 (golden topology)` (the threshold lives in YAML, not in the node)

## Goal

Land `graph/nodes/rag_lookup.py` as a `@audited_node` wrapper over Phase 4's `RagTier.lookup()` that stamps `rag_hit` and emits an event; unit-test both the threshold-met and threshold-miss paths.

## Acceptance criteria

- [ ] `graph/nodes/rag_lookup.py` exports `rag_lookup(state: VulnLedger) -> VulnLedger`, decorated with `@audited_node`, calling `RagTier().lookup(advisory=state.advisory, repo_path=state.repo_path)`.
- [ ] Sets `state.rag_hit` to whatever Phase 4 returned (`None` is valid and routes to LLM fallback); sets `last_node="rag_lookup"`; emits one `GraphEvent`.
- [ ] **Does not** consult `rag_score_threshold`. The threshold is a routing concern owned by `route_after_rag` (S3-02). This node is "evidence in, evidence out" only.
- [ ] TDD red tests exercise three branches: (1) high-score hit returned, (2) low-score hit returned (node still records it; the *edge* will route to miss), (3) `None` returned. All are committed before production code.
- [ ] Engine exceptions propagate; the node does not swallow.
- [ ] `mypy --strict`, `ruff`, `pytest` green; fence-CI still green; no sibling-node imports.

## Implementation outline

1. Confirm Phase 4's import path: `from codegenie.planner.rag.tier import RagTier` (verify against shipped code; adjust import path).
2. Write the three red TDD tests in `tests/graph/test_nodes/test_rag_lookup.py`.
3. Implement `graph/nodes/rag_lookup.py` (~ 25 LOC) — instantiate `RagTier`, call `lookup`, build the new state with `state.model_copy(update={"rag_hit": hit, "last_node": "rag_lookup", "events": state.events + [emit_event(...)]})`.
4. Confirm the `rag_score` field, if present in the `RagHit`, is logged in the emitted event for Phase 13's cost-ledger consumption.
5. Run tests; confirm green.

## TDD plan — red / green / refactor

```python
# tests/graph/test_nodes/test_rag_lookup.py
from unittest.mock import MagicMock
import pytest
from codegenie.graph.nodes.rag_lookup import rag_lookup
from tests.graph.test_nodes.conftest import make_ledger


def test_rag_lookup_records_high_score_hit(mock_phase4):
    """INTENT: edge will read score; node faithfully records whatever came back."""
    hit = MagicMock(score=0.91, example_id="ex-42")
    mock_phase4["RagTier"].return_value.lookup.return_value = hit

    out = rag_lookup(make_ledger())

    assert out.rag_hit is hit
    assert out.last_node == "rag_lookup"
    assert any(e.node_name == "rag_lookup" for e in out.events)


def test_rag_lookup_records_low_score_hit(mock_phase4):
    """Below-threshold hits are STILL recorded; route_after_rag decides the routing."""
    hit = MagicMock(score=0.42, example_id="ex-99")
    mock_phase4["RagTier"].return_value.lookup.return_value = hit
    out = rag_lookup(make_ledger())
    assert out.rag_hit is hit  # the node does NOT filter by threshold


def test_rag_lookup_records_no_hit(mock_phase4):
    mock_phase4["RagTier"].return_value.lookup.return_value = None
    out = rag_lookup(make_ledger())
    assert out.rag_hit is None


def test_rag_lookup_propagates_engine_failure(mock_phase4):
    mock_phase4["RagTier"].return_value.lookup.side_effect = RuntimeError("index unreachable")
    with pytest.raises(RuntimeError, match="index unreachable"):
        rag_lookup(make_ledger())
```

**Red:** Tests fail — module missing.
**Green:** Implement the node; tests pass.
**Refactor:** Confirm the threshold is NOT imported or read in this file (lint pass — `grep -F rag_score_threshold src/codegenie/graph/nodes/rag_lookup.py` should be empty). Confirm the emitted event's `fields` include `{"score": "..."}` when `hit is not None`.

## Files to touch

| Path | Action |
|---|---|
| `src/codegenie/graph/nodes/rag_lookup.py` | New |
| `tests/graph/test_nodes/test_rag_lookup.py` | New (TDD red) |

## Out of scope

- Threshold logic — owned by `route_after_rag` (S3-02).
- Caching the RAG index — Phase 4's `RagTier` owns its cache; instantiate fresh per call.
- Mutating `recipe_selection` here — `recipe_selection` was set by `select_recipe` and is *read-only* from `rag_lookup`'s point of view. The new selection composition for the Phase 4 LLM path is `replan_with_phase4`'s job.
- Vector-store warm-up logic — Phase 4 owns startup; Phase 6 just calls.

## Notes for the implementer

- The `RagHit` Pydantic model lives in Phase 4 (`src/codegenie/planner/rag/`); import it as a type only (`from codegenie.planner.rag.types import RagHit` or similar). Phase 6 must not redefine it.
- If `RagTier.lookup` blocks on a network call (it shouldn't — RAG is local-disk-only per Phase 4 design), this node will block too. That's fine — Phase 6 nodes are sync; the LangGraph runtime bridges to async at the checkpointer.
- Per `../phase-arch-design.md §Component 5`, p50 ≤ 100 ms; the local-disk-vector-search assumption holds.
- The fence-CI gate from S1-01 forbids `graph/` from importing `chromadb` or `sentence-transformers`. Confirm Phase 4 wraps both — the node should be importing only Phase-4 abstractions, never the raw vector libs.
- If Phase 4 ships `RagHit` with a `Path` field (evidence path), it'll need to serialize through `model_dump(mode="json")` for the checkpointer. The S1-02 round-trip golden fixture should already exercise this — if it doesn't, surface it.
