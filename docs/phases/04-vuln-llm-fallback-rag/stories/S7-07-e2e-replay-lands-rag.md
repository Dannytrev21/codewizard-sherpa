# Story S7-07 — E2E replay-lands-RAG exit criterion #2

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** Ready
**Effort:** M
**Depends on:** S7-05 (`express-rerun` fixture with pre-populated `.codegenie/rag/records/`), S6-03 (`on_validated` harvest hook semantics), S7-06 (first-run cost numbers to compare against)
**ADRs honored:** ADR-0009 (inline harvest — the seed comes from a prior validated run), ADR-0008 (two-threshold band — `RagHit` only above `high_floor`), production-ADR-0034 (event sourcing for `LlmCostAccrued`)

## Context

This is **roadmap exit criterion #2**: "re-running the same case hits RAG, not LLM, and produces an equivalent fix at lower cost." The test runs the express CVE workflow *twice* against the `express-rerun/` fixture (S7-05 ships it pre-seeded with one `SolvedExample` covering the same CVE), with **no operator step between runs** — and asserts on the second run that:
- `RagHit` was observed in events (the retriever scored ≥ `high_floor=0.85` against the seeded record).
- The leaf LLM was still called, but the call's `system[2]` block carried the few-shot record (cache_creation > 0 on system[2] **first time**, cache_read > 0 on subsequent intra-batch runs — Phase 4 ships intra-workflow cache only).
- The second-run `LlmCostAccrued.dollars` is strictly less than first-run × 0.5 — the "lower cost" criterion.
- No operator-invoked harvest happened between runs (no `codegenie rag harvest` CLI call in the test); the seed came from S7-05's fixture-resident `.codegenie/rag/records/`.

The arch is firm: "no operator step between runs" is the production-behavior guarantee that distinguishes this from a test-scaffolding shortcut. The seed in S7-05's `express-rerun/` fixture represents what S7-06's run *would have harvested* (i.e., the fixture mirrors S7-06's post-run state); this story tests the **second** run only — the first run is the seed.

Three non-obvious points:
1. **The fixture's seed must match the embedder's `model_digest()`**. If S5-03's model-mismatch exclusion drops the record, the retriever degrades to `RagMiss` and the test silently fails the wrong way (degenerates to S7-06's path). The S7-05 fixture acceptance criteria pin this; this story trusts it.
2. **"Lower cost" is asserted via event-stream `LlmCostAccrued`**, not by re-running S7-06 inside this test. The constant against which the second-run cost is compared must be either (a) captured during S7-06's first run and persisted (test fixture or expected-cost constant) or (b) re-run via cassette replay in the same test — pick (b) for hermeticity (the second cassette pair). Surface this choice in the implementation notes.
3. **`RagHit` event must appear *before* `LeafInvoked`** — order matters. The retriever fires first; the leaf call uses the hit as few-shot.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals — G1` (second sentence) — "second run on the same case hits RAG and shapes a cheaper LLM call. Asserted by `tests/integration/test_phase4_e2e_replay_lands_rag.py` (no operator step between runs)."
  - `../phase-arch-design.md §Scenario 1` — full sequence diagram of the RAG-hit-reshapes-LLM path. Each numbered arrow is an assertable event order.
  - `../phase-arch-design.md §Prompt template structure` — "Three cached system blocks per call: `system[0]` skill ... `system[1]` instruction template ... `system[2]` per-workflow RAG few-shot (~1–3 KB; only hits cache on intra-batch re-runs)."
  - `../phase-arch-design.md §Component 9 — SolvedExampleRetriever` and §Component 11 — `confidence.py` (two-threshold band).
- **Phase ADRs:**
  - `../ADRs/0009-inline-auto-harvest-confidence-gate.md` — "The integration test `tests/integration/test_phase4_e2e_replay_lands_rag.py` runs the same CVE case twice with *no operator step between runs* — the second run must hit RAG with the inline-harvested record."
  - `../ADRs/0008-two-threshold-calibration-band.md` — `RagHit` requires score ≥ `high_floor=0.85`.
- **Source design:**
  - `../final-design.md §Component 9` and §"Goal: Inline auto-harvest gate."
- **High-level impl:**
  - `../High-level-impl.md §Step 7` — "Roadmap exit criterion #2 ... second run on same case hits RAG (`RagHit` event present); leaf call shaped by few-shot; `LlmCostAccrued` second-run delta < first-run × 0.5; no operator step between runs."
- **Existing code:**
  - `tests/fixtures/repos/express-rerun/` (S7-05) — the fixture with `.codegenie/rag/records/<id>.yaml` already pre-populated.
  - `tests/integration/test_phase4_e2e_breaking_change.py` (S7-06) — sibling test; shared helpers extracted to `_phase4_e2e_helpers.py`.
  - `src/codegenie/rag/retriever.py` (S5-01) — emits `RagHit | RagDegraded | RagMiss`.
  - `src/codegenie/fallback/tier.py` (S6-01) — RAG-hit-shapes-LLM path.

## Goal

Land `tests/integration/test_phase4_e2e_replay_lands_rag.py` as a cassette-replayed integration test that runs `codegenie remediate ./tests/fixtures/repos/express-rerun --cve CVE-2026-1234` and asserts: (a) `RagHit` fires with score ≥ 0.85; (b) the seeded record is the matched `few_shot`; (c) `LeafInvoked` fires *after* `RagHit`; (d) the leaf call's prompt includes the few-shot as `system[2]`; (e) `LlmCostAccrued.dollars` is strictly less than the first-run baseline × 0.5; (f) no operator-invoked harvest CLI call occurred in the test; (g) strict-AND passes and `confidence == "high"`; (h) (optionally) the second-run `SolvedExampleHarvested` is **skipped** (the seed is already harvested) or asserts a `HarvestSkipped(reason=already_present)` if the harvester is dedup-aware (read S6-03 first to confirm).

## Acceptance criteria

- [ ] `tests/integration/test_phase4_e2e_replay_lands_rag.py` exists, is collected by pytest, marked `@pytest.mark.integration` + `@pytest.mark.phase4`.
- [ ] The test runs via `click.testing.CliRunner` and hermetically copies `tests/fixtures/repos/express-rerun/` to `tmp_path` before invocation. The `.codegenie/rag/records/<id>.yaml` seed is preserved in the copy.
- [ ] `tests/cassettes/anthropic/test_phase4_e2e_replay_lands_rag.yaml` exists, is sanitized (S3-04), and entered in `cassettes.lock` (S3-05) with BLAKE3.
- [ ] **`RagHit` assertion:** the event stream contains a `RagHitClassified` (or whatever S5-02's emitter names it) event with `score >= 0.85`; assert it occurs **before** any `LeafInvoked` event in the stream's natural order.
- [ ] **Few-shot-matched assertion:** the `RagHitClassified.matched_record.solved_example_id` equals the `solved_example_id` of the record pre-populated in the fixture's `.codegenie/rag/records/`.
- [ ] **LeafInvoked-after-RagHit assertion:** scanning the event stream by index, the `RagHitClassified` event's index is strictly less than the `LeafInvoked` event's index.
- [ ] **Few-shot-in-prompt assertion:** the `LeafInvoked` event carries `system_blocks_count == 3` (i.e., system[2] is present); cassette inspection (deserialize the cassette body) confirms the request payload has 3 cached system blocks. Acceptable alternative: the `LeafInvoked` event carries a structured `system_blocks_metadata` array of length 3 — pick the shape that S3-02's adapter emits; surface a conflict per Global Rule 7 if neither is available.
- [ ] **No-operator-harvest assertion:** the test source contains no call to a `codegenie rag harvest` CLI invocation between the fixture copy and the CLI invocation. (This is a static-text guard: `assert "codegenie rag harvest" not in inspect.getsource(test_function)` — defends against future maintainers adding scaffolding.)
- [ ] **Cost-delta assertion:** the second-run `LlmCostAccrued.dollars < first_run_baseline_dollars * 0.5`. The first-run baseline comes from either:
  - **(a)** Re-running `test_phase4_e2e_breaking_change.py`'s cassette in this test, capturing its `LlmCostAccrued`, and using that as the baseline. **Preferred** — fully hermetic.
  - **(b)** A persisted constant in `tests/integration/_phase4_e2e_helpers.py::FIRST_RUN_BASELINE_DOLLARS` updated when S7-06's cassette is refreshed.
  Pick (a). Document the choice in the test docstring.
- [ ] **Strict-AND-passed assertion:** the second-run `TrustOutcome` has `passed=True`, `confidence="high"`.
- [ ] **Harvest-on-second-run behavior:** read S6-03 first. If the harvester dedup-skips when a matching record already exists, assert `HarvestSkipped(reason="already_present")` or similar event. If S6-03 has no dedup, assert one new `SolvedExampleHarvested` event (and document that the store now contains two records covering the same CVE — acceptable per arch §Edge case #5 chroma writer contention).
- [ ] **Determinism guard:** running the test twice in a row produces byte-identical `remediation-report.yaml` after masking `workflow_id`/timestamps/`event_id`.
- [ ] The test fails-loud (not skips) if `bwrap` / `sandbox-exec` is missing — mirror Phase-3 S8-02 contract.
- [ ] Test module docstring documents cassette regeneration via `make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1` and cross-links the CODEOWNERS entry (S3-06).
- [ ] `make check` clean.
- [ ] TDD red test exists, committed, green.

## Implementation outline

1. **Read first**: open S6-03 to confirm dedup behavior; open S7-06 to lift its shared helpers into `_phase4_e2e_helpers.py`; open S7-05 to confirm the seed record's `solved_example_id` and embedding model digest.
2. Build the test skeleton: hermetic fixture copy + CLI invocation.
3. Record the second-run cassette via `make refresh-cassettes`. The recording must be done with the seed record present so the live API sees the few-shot — otherwise the cassette's response shape will differ from the post-RAG-hit shape.
4. Add the cassette to `cassettes.lock`.
5. Write the assertions in the order they appear in the event stream (chronological) so a regression's failure point is unambiguous.
6. For the cost-delta assertion, use option (a): inside the test, before invoking the CLI on the rerun fixture, invoke the CLI on the original express-cve-2026-1234 fixture (with its own cassette) and capture the first-run cost. Use the captured value as the baseline.
7. Add the `inspect.getsource` static guard against `codegenie rag harvest` strings appearing in the test function.
8. Flake-check by running 10× in a row.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/integration/test_phase4_e2e_replay_lands_rag.py
"""
Phase 4 roadmap exit criterion #2 — replay lands RAG; second run is cheaper.

Critically: **no operator step between runs.** The seed under
tests/fixtures/repos/express-rerun/.codegenie/rag/records/ stands in for
what S7-06's first run would have harvested. This test runs only the
second workflow; the seed is the production-behavior precondition.

Regenerating cassettes: same procedure as S7-06.
"""
from __future__ import annotations
import inspect
import json
import shutil
from pathlib import Path
import pytest
import zstandard as zstd
from click.testing import CliRunner

from codegenie.cli import remediate
from tests.integration._phase4_e2e_helpers import (
    parse_events, load_cve_yaml, load_repo_ctx, run_first_run_for_baseline,
)


FIXTURE_RERUN = Path("tests/fixtures/repos/express-rerun")
CASSETTE = Path("tests/cassettes/anthropic/test_phase4_e2e_replay_lands_rag.yaml")


@pytest.fixture
def hermetic_rerun(tmp_path):
    target = tmp_path / "express-rerun"
    shutil.copytree(FIXTURE_RERUN, target)
    # Sanity: the seeded record is present pre-run.
    seed_dir = target / ".codegenie" / "rag" / "records"
    assert any(seed_dir.glob("*.yaml")), "fixture missing pre-seeded RAG record"
    return target


@pytest.mark.integration
@pytest.mark.phase4
@pytest.mark.vcr(CASSETTE.name, record_mode="none")
def test_phase4_e2e_replay_lands_rag(hermetic_rerun, tmp_path):
    # Capture first-run baseline from a separate hermetic invocation
    # of the breaking-change cassette (option (a) — fully hermetic).
    first_run_dollars = run_first_run_for_baseline(tmp_path)
    assert first_run_dollars > 0

    runner = CliRunner()
    result = runner.invoke(
        remediate,
        [str(hermetic_rerun), "--cve", "CVE-2026-1234"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    events = parse_events(hermetic_rerun / ".codegenie" / "events" / "workflow-internal")

    # (a) RagHit fired with score >= high_floor.
    rag_hits = [e for e in events if e["kind"] == "RagHitClassified"]
    assert len(rag_hits) == 1
    assert rag_hits[0]["score"] >= 0.85

    # (b) The matched record is the seeded one.
    seed_id = _read_seeded_record_id(FIXTURE_RERUN)
    assert rag_hits[0]["matched_record"]["solved_example_id"] == seed_id

    # (c) RagHit before LeafInvoked in stream order.
    idx_rag = next(i for i, e in enumerate(events) if e["kind"] == "RagHitClassified")
    idx_leaf = next(i for i, e in enumerate(events) if e["kind"] == "LeafInvoked")
    assert idx_rag < idx_leaf

    # (d) Few-shot present as system[2].
    [leaf_evt] = [e for e in events if e["kind"] == "LeafInvoked"]
    assert leaf_evt.get("system_blocks_count") == 3

    # (e) Cost is strictly below 50% of the first-run baseline.
    [cost] = [e for e in events if e["kind"] == "LlmCostAccrued"]
    second_run_dollars = float(cost["dollars"])
    assert second_run_dollars < first_run_dollars * 0.5, (
        f"replay cost {second_run_dollars} not < 0.5 * first-run baseline {first_run_dollars}"
    )

    # (f) No operator-invoked harvest in this test.
    src = inspect.getsource(test_phase4_e2e_replay_lands_rag)
    assert "codegenie rag harvest" not in src
    assert "rag_harvest_cli" not in src  # second-line defense

    # (g) Strict-AND passed.
    [trust] = [e for e in events if e["kind"] == "TrustOutcomeEmitted"]
    assert trust["passed"] is True
    assert trust["confidence"] == "high"

    # (h) Harvest behavior (read S6-03 first; pick assertion accordingly).
    harvest_events = [e for e in events if e["kind"] in {"SolvedExampleHarvested", "HarvestSkipped"}]
    assert len(harvest_events) == 1
    # If S6-03 dedups: expect HarvestSkipped(reason=already_present).
    # Otherwise: expect SolvedExampleHarvested (second copy of the same CVE).


def _read_seeded_record_id(fixture: Path) -> str:
    import yaml
    [rec_path] = list((fixture / ".codegenie" / "rag" / "records").glob("*.yaml"))
    rec = yaml.safe_load(rec_path.read_text())
    return rec["solved_example_id"]
```

Run: `pytest tests/integration/test_phase4_e2e_replay_lands_rag.py -v` — all assertions fail before the chain is wired.

### Green — make it pass

1. Extract shared helpers from S7-06 into `_phase4_e2e_helpers.py` (`parse_events`, `load_cve_yaml`, `load_repo_ctx`, `run_first_run_for_baseline`).
2. Record the second-run cassette via `make refresh-cassettes` *with the seed record present in the live run's `.codegenie/rag/records/`*.
3. Add cassette + lock entry.
4. Iterate until each assertion is green; pay attention to the `RagHit` → `LeafInvoked` ordering (a regression in `FallbackTier`'s named-sequential dispatch is the most likely failure mode).

### Refactor — clean up

- Move the seed-record-id reader into the helpers module if it's reused.
- Document the harvest-on-second-run choice (dedup vs duplicate) in the test docstring with cross-link to S6-03.
- Flake-check 10× in a row.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase4_e2e_replay_lands_rag.py` | The exit-criterion #2 test. |
| `tests/integration/_phase4_e2e_helpers.py` | Shared helpers (extended by this story; created if absent). |
| `tests/cassettes/anthropic/test_phase4_e2e_replay_lands_rag.yaml` | Second-run cassette (recorded with seed record present). |
| `tests/cassettes/anthropic/cassettes.lock` | New entry with BLAKE3. |

## Out of scope

- The first-run E2E itself (S7-06).
- Calibration of `high_floor` (S5-04 owns the smoke test; this story trusts the configured value).
- Adversarial RAG-poisoning tests (S7-09).
- Phase-11 post-merge webhook harvest path — Phase-4 ships only the inline path.

## Notes for the implementer

- **The "no operator step between runs" framing is load-bearing for ADR-0009.** The static-text guard catches the most obvious regression (a future maintainer adding `runner.invoke(rag_harvest, ...)` between the fixture copy and the CLI invocation as a "convenience"); but the real defense is the seeded fixture standing in for the prior production-behavior harvest.
- The cost delta is the most likely-to-flake assertion: token counts depend on Anthropic's tokenizer, which changes silently across SDK versions. If the cassette is re-recorded under a new SDK pin, the delta-vs-baseline ratio may shift. The `< 0.5x` threshold is generous to absorb this; if it tightens over time, surface per Global Rule 12 and bump it explicitly in this story's acceptance criteria, not silently in the threshold constant.
- The `RagHit before LeafInvoked` assertion is the witness that `FallbackTier`'s named-sequential pipeline (S6-01) is preserved — if a future refactor parallelizes the retriever and the leaf call, this test fails immediately and that's the right outcome.
- The `system_blocks_count == 3` assertion depends on S3-02's `AnthropicLeafAdapter` emitting that metadata on `LeafInvoked`. If it doesn't, surface per Global Rule 7: either add the metadata (small surgical edit to S3-02) or change this story's assertion to inspect the cassette body directly via the cassette-reading helpers.
- The cost-baseline via option (a) means this test invokes the CLI twice — once on `express-cve-2026-1234` for the baseline, once on `express-rerun` for the assertion. Both invocations are cassette-replayed; total wall-clock should still be ≤ 60s.
- If S6-03 doesn't yet implement dedup, the harvest-on-second-run assertion is the simpler "one new `SolvedExampleHarvested` event"; document the choice explicitly so a future S6-03 amendment that adds dedup also updates this story's assertion in lockstep.
