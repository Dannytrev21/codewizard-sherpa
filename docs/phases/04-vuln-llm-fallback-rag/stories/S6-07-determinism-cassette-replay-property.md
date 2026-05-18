# Story S6-07 — Determinism-under-cassette-replay property test

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** Ready
**Effort:** M
**Depends on:** S6-01 (FallbackTier shell), S6-02 (retry-bypass branch)
**ADRs honored:** ADR-04-0002 (Pipeline; deterministic when cassette is fixed), ADR-04-0014 (cassette discipline supports deterministic replay), ADR-04-0008 (two-threshold band is pure)

## Context

Phase-arch-design §Harness §Determinism vs probabilism (lines 832–835) commits Phase 4 to deterministic behavior across every component **except** the probabilistic leaf, which becomes deterministic under cassette replay. Phase-arch-design §Idempotence (line 827) names the load-bearing key tuple: `(cassette_id, store_digest, repo_snapshot_sha, embedding_model_digest)` constant ⇒ byte-identical outcomes.

The risk is real: a flaky `dict` iteration order, a sort instability in the retriever, or a clock-based audit field that leaks into a digest can turn deterministic-by-construction into "passes locally, flakes in CI". The property test is the contract: 50 runs with the four-tuple constant must produce byte-identical `Transform.diff_bytes` and byte-identical event order (modulo timestamps and other allowlisted non-deterministic fields).

This story lands `tests/property/test_determinism_under_cassette_replay.py` as the contract test. Phase 6.5 (bench replay) and Phase 7 (E2E) both read this contract; a regression here is a Phase-4-merge blocker.

## References — where to look

- **Architecture:** [phase-arch-design.md §Harness §Determinism vs probabilism](../phase-arch-design.md) (lines 832–835); §Idempotence (line 827); §Concurrency (line 269 — single-async-event-loop); §Goals — G6 (replay).
- **Phase ADRs:** [ADR-04-0002](../ADRs/0002-fallback-tier-pipeline-no-langgraph.md) §Tradeoffs (every step one audit event — debuggability is a sequence); [ADR-04-0014](../ADRs/0014-cassette-discipline-security-control.md) (cassettes are the determinism mechanism for the leaf); [ADR-04-0008](../ADRs/0008-two-threshold-calibration-band.md) (threshold band classifier is pure).
- **Source design:** [final-design.md §Phase 4 Goals — "Deterministic under cassette replay"](../final-design.md); §"Three load-bearing structural lines" item 1.
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md) Done criteria — "Determinism property `tests/property/test_determinism_under_cassette_replay.py` — 50 runs with `(cassette_id, store_digest, repo_snapshot_sha, embedding_model_digest)` constant: byte-identical `Transform.diff_bytes` and event order (modulo timestamps)".
- **Existing code (after S6-01/02):** `src/codegenie/fallback/tier.py`; `tests/cassettes/anthropic/`; `tests/fixtures/fallback_tier_callable.py`.

## Goal

Land `tests/property/test_determinism_under_cassette_replay.py`: run `FallbackTier.run` 50 times with the four-tuple `(cassette_id, store_digest, repo_snapshot_sha, embedding_model_digest)` held constant; assert byte-identical `Transform.diff_bytes` across all 50 runs AND byte-identical event-kind-sequence (modulo a documented allowlist of non-deterministic fields like timestamps and randomly-generated audit-event UUIDs).

## Acceptance criteria

- [ ] **50-iteration replay**: the test invokes `FallbackTier.run` exactly 50 times under VCR cassette replay (`pytest --record-mode=none`) with the same advisory, repo_ctx, recipe_selection, store, embedder, prior_attempts=[].
- [ ] **Byte-identical `Transform.diff_bytes` across all 50 runs**: `set(diff_bytes for _ in range(50))` has exactly 1 element. Assertion failure surfaces the first diverging byte index per Global Rule 12 ("fail loud") — print `len(diff_bytes_a)` vs `len(diff_bytes_b)` and the first mismatched offset.
- [ ] **Byte-identical event-kind sequence**: `[(e.kind, e.payload_digest_blake3) for e in run_events]` is identical across all 50 runs.
- [ ] **Non-deterministic-fields allowlist**: timestamps (`emitted_at`), audit-event UUIDs, and `BudgetTokenId` (uuid4) are explicitly listed as allowed to differ. The test strips them before comparison; the allowlist lives as a `Final` tuple in the test module with a docstring citing this AC.
- [ ] **Same property holds for retry-bypass path**: a second test `test_determinism_under_cassette_replay_retry` runs the same 50-iteration loop with `prior_attempts=[summary]` (S6-02 path); same byte-identical assertion. Confirms the retry branch is just as deterministic.
- [ ] **Performance budget**: 50 cassette-replay iterations complete within an acceptable wall-clock cap (target ≤ 60 s total for the property test); if it overruns, drop iteration count to a number that still gives statistical confidence (≥ 20) and surface per Global Rule 12.
- [ ] **Single-event-loop discipline asserted**: the test runs each iteration inside a fresh `asyncio.run(...)` to confirm no leaked state across loops; if a state leak across loops appears (e.g., a module-level `dict` mutated by a probe), the test fails loud.
- [ ] **Failure diagnostic is actionable**: when the test fails, the error message must name (a) which run number first diverged, (b) which event index diverged, and (c) the diff between the two events. A `pprint.pformat`-style diff is acceptable; raw `assert a == b` failure messages are not (they truncate dicts).
- [ ] `make check`, `make test` green; the property test runs as part of the default suite (not gated behind `-m bench`); ≥ 20 iterations is the floor per Global Rule 6 (token budget) — the goal is 50 but truthful 20 beats fake 50.

## Implementation outline

1. New test file `tests/property/test_determinism_under_cassette_replay.py`. Use `pytest-recording`'s `@pytest.mark.vcr` to lock the cassette; mode `none` (replay-only).
2. Use the `tests/fixtures/fallback_tier_callable.py` factory from S6-01 to build a tier wired to a deterministic store + embedder + cassette-backed adapter.
3. Loop 50 times: `result_i = asyncio.run(tier.run(advisory, repo_ctx, sel))`; capture `result_i.transform.diff_bytes` and the captured event tape.
4. Assertion helpers:
   ```python
   ALLOWED_NONDET_FIELDS: Final[tuple[str, ...]] = (
       "emitted_at", "audit_event_id", "budget_token_id_uuid",
   )
   def _strip_nondet(event: Event) -> dict:
       return {k: v for k, v in event.model_dump().items() if k not in ALLOWED_NONDET_FIELDS}
   ```
5. Use a small `_diff_runs(run_a, run_b) -> str` helper that returns a `pprint.pformat`-style diff highlighting the first divergence — call it from the assertion failure message via `assert ..., f"runs diverge:\n{_diff_runs(...)}"`.
6. The second test (retry-bypass) mirrors the same structure with `prior_attempts=[AttemptSummary(...)]`.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/property/test_determinism_under_cassette_replay.py
import asyncio
from typing import Final
import pytest
from tests.fixtures.fallback_tier_callable import make_fallback_tier_for_fixtures

ALLOWED_NONDET_FIELDS: Final[tuple[str, ...]] = (
    "emitted_at",        # ISO-8601 timestamp; clock-derived
    "audit_event_id",    # uuid4 per event
    "budget_token_id",   # uuid4 per precharge
)

ITERATIONS = 50

@pytest.mark.vcr(cassette_library_dir="tests/cassettes/anthropic/test_determinism")
def test_fallback_tier_byte_identical_under_replay(
    advisory_fix, repo_ctx_fix, recipe_selection_fix,
    seeded_rag_store, fastembed_real,
):
    """ADR-04-0002 + arch §Determinism: same four-tuple ⇒ byte-identical outcome.
    Why this matters: a regression here means Phase 6.5 bench replay and Phase 7
    E2E both flake non-deterministically — and the production-behavior exit
    criterion #2 (replay-lands-RAG) is no longer trustworthy."""
    results = []
    event_tapes = []

    for i in range(ITERATIONS):
        tier = make_fallback_tier_for_fixtures(
            store=seeded_rag_store, embedder=fastembed_real,
        )
        event_log = tier.event_log  # capturing
        result = asyncio.run(tier.run(advisory_fix, repo_ctx_fix, recipe_selection_fix))
        results.append(result.transform.diff_bytes)
        event_tapes.append([_strip_nondet(e) for e in event_log.recorded])

    distinct_diffs = set(results)
    assert len(distinct_diffs) == 1, (
        f"diff_bytes diverged across {ITERATIONS} runs: "
        f"{len(distinct_diffs)} distinct outputs. First divergence at run "
        f"{_first_divergence(results)}."
    )
    distinct_tapes = {tuple((e["kind"], e.get("payload_digest_blake3")) for e in tape)
                      for tape in event_tapes}
    assert len(distinct_tapes) == 1, _diff_runs(event_tapes)


@pytest.mark.vcr(cassette_library_dir="tests/cassettes/anthropic/test_determinism_retry")
def test_fallback_tier_byte_identical_under_replay_retry_path(
    advisory_fix, repo_ctx_fix, recipe_selection_fix, attempt_summary_fix,
    seeded_rag_store, fastembed_real,
):
    """S6-02 retry-bypass path must be just as deterministic as the happy path."""
    results = []
    for _ in range(ITERATIONS):
        tier = make_fallback_tier_for_fixtures(
            store=seeded_rag_store, embedder=fastembed_real,
        )
        r = asyncio.run(tier.run(
            advisory_fix, repo_ctx_fix, recipe_selection_fix,
            prior_attempts=[attempt_summary_fix],
        ))
        results.append(r.transform.diff_bytes)
    assert len(set(results)) == 1
```

### Green — make it pass

- The first time this test runs, it will likely surface a real non-determinism — possibly:
  - A `dict` iteration order leaking into a prompt body — fix by sorting before serializing.
  - A `set` iteration leaking into a fence-segment ordering — fix by `sorted(...)`.
  - A `time.time()` call leaking into the prompt — replace with a deterministic field or move to event metadata.
- **Do not** weaken the test to make it pass. Fail loud (Global Rule 12); fix the source of non-determinism in `FallbackTier`, `PromptBuilder`, or `SolvedExampleRetriever`.

### Refactor — clean up

- The `_strip_nondet` helper and `ALLOWED_NONDET_FIELDS` allowlist must stay small and documented. Every entry needs a comment explaining why it's allowed to differ.
- If a real source of non-determinism is found, fix it; do not add it to the allowlist.

## Files to touch

| Path | Why |
|---|---|
| `tests/property/test_determinism_under_cassette_replay.py` | New — the property test. |
| `tests/cassettes/anthropic/test_determinism/` | New — cassette directory; record via `make refresh-cassettes`. |
| `tests/cassettes/anthropic/test_determinism_retry/` | New — second cassette for retry path. |
| `src/codegenie/fallback/tier.py` (only if real non-determinism is uncovered) | Fix the source; do not weaken the test. |
| `src/codegenie/rag/retriever.py` (only if real non-determinism is uncovered) | Same — sort iteration orders, etc. |

## Out of scope

- The full E2E roadmap-exit tests — **S7-06**, **S7-07** read this property as a precondition.
- Phase 6.5 bench replay determinism — that's a higher-order assertion that depends on this property holding.
- Cross-architecture float-drift handling — already mitigated by the two-threshold band (ADR-04-0008); not re-tested here.
- The `make refresh-cassettes` workflow itself — S3-06.

## Notes for the implementer

- **Fail loud is the contract.** If the property fails the first time you run it, that's the test working — there's real non-determinism somewhere. Find it. Do not add fields to `ALLOWED_NONDET_FIELDS` to make the test pass (Global Rule 12).
- **50 iterations is the goal, ≥ 20 the floor.** If 50 iterations exceeds 60 s wall clock, drop to a count that fits the suite's perf envelope and surface per Global Rule 12. Don't fake the iteration count.
- **The retry-path test (S6-02 branch) is just as important as the happy path.** A regression that only affects the retry path would be invisible to E2E #1 (S7-06) which doesn't exercise retry. Don't skip the second test even if it doubles cassette work.
- **`asyncio.run(...)` per iteration** is intentional — it surfaces leaked module-level state. If a global cache or registry mutates across loops, this catches it.
- **Cassette recording** (`make refresh-cassettes` from S3-06) is operator-touch — coordinate with the cassette-steward (CODEOWNERS entry from S3-06) before re-recording. The cassettes for the determinism test must NOT be re-recorded casually; they're the immutable substrate for the property.
- **Diagnostic quality matters.** `assert a == b` on big dicts truncates output and a flake becomes un-debuggable. Use `pprint.pformat` + a `_diff_runs` helper. Future-you will thank present-you.
- This property test makes the Phase-6.5 bench replay and Phase-7 E2E tests *trustworthy*. A weak version of this test invalidates the downstream claims.
