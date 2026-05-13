# Story S7-03 — Retry-feedback-distinct-bytes test (G5 / Phase 5 exit-criterion #19)

**Step:** Step 7 — HITL replay + Phase 5 parity + retry-feedback-distinct-bytes tests (G3 + G4 + G5)
**Status:** Ready
**Effort:** M
**Depends on:** S7-01 (shared mocks, `initial_ledger.py` fixture, conftest normalization). Transitively: S4-05 (`replan_with_phase4` node calls `FallbackTier.run(advisory, repo_ctx, recipe_selection, prior_attempts=state.prior_attempts)` and sets `last_engine="phase4_llm"`), S4-07 (`record_attempt` appends to `prior_attempts`), S5-01 (factory), S6-02 (`loop run` operator surface for the optional CLI-level variant).
**ADRs honored:** ADR-0004 (retry re-enters Phase 4's `FallbackTier.run` — and consumes `prior_attempts` additively per Phase 5 ADR-P5-002), production ADR-0014 (`max_attempts=3` per-gate default), Phase 5 ADR-P5-002 (the `prior_attempts: list[AttemptSummary] = []` additive kwarg the test exercises). Reinforces ADR-0003 (per-gate retry counter — the test runs 3 retries at the same `current_gate_id="stage6_validate"` so the counter never resets mid-test).

## Context

Phase 5's final-design lists this as **exit-criterion #19** (`docs/phases/05-sandbox-trust-gates/final-design.md` line 614):

> *"Three-retry loop demonstrated end-to-end with at least one case that fails on retry-1 and recovers on retry-2."* — `tests/integration/gates/test_stage6_retry_recovers.py` runs the breaking-change-cve fixture through Phase 4's `FallbackTier.run(... prior_attempts=[...])` and asserts `attempts.jsonl` has 2 entries with distinct `attempt_id`s, distinct `prior_failure_summary`s, distinct `sandbox_run_id`s, and **distinct patch bytes**. The Phase 4 prompt on attempt 2 demonstrably contains the fence-wrapped prior failure summary.

Phase 6 is forbidden from regressing this exit criterion: the LangGraph cycle's `replan_with_phase4 → apply_recipe → validate_in_sandbox → record_attempt → route_after_attempt → replan_with_phase4` cycle must produce three patches with three distinct `blake3` digests when run against three VCR-recorded LLM responses. This is the **G5 gate** in arch-design §Goals#5:

> *"G5 — Retry feedback honors Phase 5 exit-criterion #19. Retry-1 re-enters Phase 4 with `prior_attempts`; produces distinct patch bytes; Phase 4's prompt on attempt 2 contains the fence-wrapped summary."*

The shape this story extends is **three attempts, not two** (Phase 5's original gate was two). Three attempts give two retry-feedback boundaries: attempt-2 sees `prior_attempts=[attempt-1]`; attempt-3 sees `prior_attempts=[attempt-1, attempt-2]`. The test asserts the Phase 4 prompt on attempts 2 *and* 3 contains the fence-wrapped summary of every prior failure, in order. The third attempt then *passes* (a fourth attempt would trip `max_attempts=3` retry-exhausted into HITL — that's S7-01's path, not this story's).

The mechanism is **VCR cassettes**. Phase 4's LLM call (the only LLM in the system) is recorded against the Anthropic API on a first authoring pass; the cassettes are committed; subsequent test runs replay them deterministically with no network access. The three cassettes live under `tests/cassettes/cve_fixture_3retries/` per the High-level-impl spec.

The test must verify three things:

1. **Patch byte distinctness.** `blake3(patch-attempt-1.diff) ≠ blake3(patch-attempt-2.diff) ≠ blake3(patch-attempt-3.diff)`. Three distinct digests, three distinct files on disk.
2. **Fence-wrapped summary in Phase 4 prompt.** Attempt-2's prompt (captured via VCR or via instrumentation of `FallbackTier.run`) contains the fence-wrapped, truncated, canary-checked `prior_failure_summary` from attempt-1's `AttemptSummary`. Attempt-3's prompt contains both prior summaries. The fence syntax is Phase 4's existing `<<<UNTRUSTED_INPUT_START>>>` / `<<<UNTRUSTED_INPUT_END>>>` markers (per Phase 4's `FenceWrapper`).
3. **Engine attribution.** Each of the three attempts records `engine_used="phase4_llm"` in its `attempts.jsonl` entry (and the ledger's `last_engine == "phase4_llm"` post-record). This pins that Phase 6's `replan_with_phase4` is wired through the right engine — not silently delegating to `select_recipe` or `rag_lookup`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals#5 (G5)` — the goal verbatim.
  - `../phase-arch-design.md §Scenario 2` (lines 411–429) — the three replan→validate cycles before HITL fires.
  - `../phase-arch-design.md §Component 4 "@pure_edge — route_after_attempt"` — the retry routing predicate.
  - `../phase-arch-design.md §Testing strategy → Layer 5 (Phase 5 parity)` — ~60 s CI budget.
- **Phase ADRs:**
  - `../ADRs/0004-retry-re-enters-phase4-fallback-tier.md` — retry edge target.
  - `../ADRs/0003-per-gate-retry-counter-scope.md` — per-gate counter ensures 3 retries at the same gate are exercised.
- **Source design:** `../final-design.md §Goals#5`.
- **High-level-impl:** `../High-level-impl.md §Step 7` — names the test, the cassette path, and the cassette-attempt files.
- **Prior phases:**
  - `../../05-sandbox-trust-gates/final-design.md` line 511 — the original 2-attempt version this story extends to 3.
  - `../../05-sandbox-trust-gates/final-design.md` §"Retry feedback semantics" — `prior_attempts` propagation; `AttemptSummary` shape (`failing_signals`, `prior_failure_summary`, `evidence_paths`); 4 KB summary cap, fence-wrapping, canary-collision check.
  - `../../04-vuln-llm-fallback-rag/final-design.md` (if it exists) §FenceWrapper, §FallbackTier prompt builder — the prompt builder's fence-wrapping logic the test verifies.

## Goal

Land `tests/integration/test_phase4_retry_feedback_distinct_bytes.py` that runs a 3-attempt retry cycle through Phase 6's LangGraph (`select_recipe→miss → rag_lookup→miss → replan_with_phase4 → apply_recipe → validate_in_sandbox→fail → record_attempt → replan_with_phase4 → … → pass`) using three VCR cassettes for the three Phase 4 LLM calls; asserts the three patches on disk have distinct `blake3` digests; asserts the Phase 4 prompt on attempts 2 and 3 contains the fence-wrapped `prior_failure_summary` of every prior attempt; asserts `last_engine="phase4_llm"` on all three `attempts.jsonl` entries. Closes G5 and forward-secures Phase 5 exit-criterion #19 against silent regression by Phase 6.

## Acceptance criteria

- [ ] `tests/integration/test_phase4_retry_feedback_distinct_bytes.py` exists, is `@pytest.mark.integration` + `@pytest.mark.slow`, and is green.
- [ ] **Three VCR cassettes shipped** at `tests/cassettes/cve_fixture_3retries/cassette-attempt-1.yaml`, `cassette-attempt-2.yaml`, `cassette-attempt-3.yaml`. Each is recorded against the real Anthropic API on first authoring (with the `--record-mode=once` flag); after that, the cassettes are committed and the test runs without network access.
- [ ] **The fixture is `tests/fixtures/repos/cve-fixture/`** (or `breaking-change-cve` if Phase 5's name is preserved) with a known CVE that requires a structural patch. The same fixture Phase 5's `test_stage6_retry_recovers.py` uses; sharing the fixture is part of the parity story.
- [ ] **`GateRunner.run_one` is scripted to fail on attempts 1 and 2, pass on 3.** Distinct `failing_signals` per attempt (`["tests"]`, `["build"]`, `[]`) so the same-signature flake detector doesn't fire. Distinct `prior_failure_summary` strings naturally follow from distinct signals.
- [ ] **The three patch files exist on disk** at `<run-dir>/patches/patch-attempt-1.diff`, `patch-attempt-2.diff`, `patch-attempt-3.diff` (or whatever the Phase 6 patch-write convention is — confirm against S4-03's implementation). The test reads all three.
- [ ] **`blake3(patch-attempt-1) != blake3(patch-attempt-2) != blake3(patch-attempt-3)`** asserted as `len({blake3(p).hexdigest() for p in patches}) == 3`. The transitive `blake3(patch-1) != blake3(patch-3)` is implied by set cardinality 3 but the message on failure should name *which pair* matched (use `pytest.fail` with a structured message listing the three digests).
- [ ] **Phase 4 prompt verification on attempt 2.** The test captures the prompt sent on attempt 2 (via VCR cassette inspection or via `monkeypatch`ing `FallbackTier.run` to record the prompt). It asserts:
  - The prompt contains the literal `<<<UNTRUSTED_INPUT_START>>>` and `<<<UNTRUSTED_INPUT_END>>>` fence markers (Phase 4's `FenceWrapper` syntax — verify against Phase 4's source for the exact tokens; the names above are illustrative).
  - Between the fence markers, the attempt-1 `prior_failure_summary` substring appears.
  - The prompt does **not** contain raw stderr bytes from the sandbox; it contains only the structured `AttemptSummary.prior_failure_summary` field.
- [ ] **Phase 4 prompt verification on attempt 3.** Same as above, but the prompt contains **both** attempt-1 *and* attempt-2 `prior_failure_summary` substrings, each individually fence-wrapped (the fence wraps the whole `prior_attempts` payload, not each entry — verify the actual `FenceWrapper` semantics; the assertion should match Phase 4's implementation, not invent a shape).
- [ ] **Engine attribution: `last_engine == "phase4_llm"` on every attempt.** Read `attempts.jsonl`; assert every line's `engine_used == "phase4_llm"`. Assert the final `VulnLedger.last_engine == "phase4_llm"` post-record.
- [ ] **Cycle topology assertion.** The test inspects `graph.aget_state_history(config)` and asserts the node-execution sequence contains `replan_with_phase4` three times, `apply_recipe` three times, `validate_in_sandbox` three times, and `record_attempt` three times, all before the run completes via `emit_artifact` (no `await_human` fires — the third attempt passes).
- [ ] **`prior_attempts` propagation across cycles.** The test asserts `len(state.prior_attempts) == 0` when `replan_with_phase4` is entered for attempt 1, `== 1` for attempt 2, `== 2` for attempt 3. (Capture state via `aget_state_history`.)
- [ ] **HITL does not fire.** The third attempt passes (`GateOutcome(passed=True)`); the run exits via `emit_artifact → END`. `final_state.human_request is None`; the audit chain contains no `interrupt.raised` events.
- [ ] **Wall-clock budget.** ≤ 60 s on CI (Layer 5 budget). With VCR cassettes (no real LLM round-trip), the test should run in ~5 s; the budget covers CI variance and the `record_attempt` BLAKE3 chain writes × 3.
- [ ] **`mypy --strict tests/integration/test_phase4_retry_feedback_distinct_bytes.py`** passes. `ruff check` + `ruff format --check` pass.
- [ ] **VCR configuration discipline.** The `vcr_cassette_dir` is parametrized via a pytest fixture in `tests/integration/conftest.py`; `record_mode` defaults to `"none"` in CI (cassettes are read-only; missing cassettes red-fail rather than silently re-record). A one-time `record_mode="once"` authoring run is the only way to regenerate cassettes; the procedure is documented in `tests/cassettes/README.md`.
- [ ] **Cassette authenticity.** Each cassette has a header comment naming: the date recorded, the model ID (e.g., `claude-3-5-sonnet-20241022`), the system prompt hash, the fixture commit SHA. The test asserts the model ID matches Phase 4's pinned model (so a Phase 4 model-bump invalidates the cassettes loudly).
- [ ] **No real LLM, no real sandbox.** Same as S7-01: Phase 5 `GateRunner.run_one` is mocked at the import boundary; only Phase 4's LLM call is "real" (against the cassette).
- [ ] **Test docstring** names: (a) Phase 5 exit-criterion #19 verbatim, (b) the three patches must have distinct `blake3` (with the explicit invariant `len(distinct_digests) == 3`), (c) the fence-wrapped summary discipline (Phase 4's `FenceWrapper` is the producer; the test verifies the consumer-side prompt), (d) the cassette regeneration procedure ("record once → commit → never re-record automatically"), (e) the amendment procedure if Phase 4's prompt shape ever changes ("amend Phase 4 ADR + regenerate cassettes + update assertion in the same PR").

## Implementation outline

1. **Cassette authoring.** Authoring is a one-time procedure documented in `tests/cassettes/README.md`. The first author runs the test once with a live `ANTHROPIC_API_KEY` and `record_mode="once"`; the cassettes are committed; thereafter `record_mode="none"`.
2. **VCR fixture.** Extend `tests/integration/conftest.py` with a `vcr_cve_fixture_3retries` fixture that loads the three cassettes and patches `httpx`/`anthropic`'s transport.
3. **Mock `GateRunner.run_one`.** Same `MockGateRunner` pattern as S7-02. Scripted `[fail-tests, fail-build, pass]` sequence.
4. **Capture the Phase 4 prompt.** Two options:
   - **(preferred)** `monkeypatch.setattr` on `FallbackTier.run` to wrap the real call and capture `kwargs` + the assembled prompt before delegating. Append captures to a list; assert on the list post-run.
   - **(fallback)** Inspect the VCR cassette's `request.body` field; parse the JSON; extract the `messages[0].content`. More brittle to the Anthropic API shape; only use if (preferred) is impractical.
5. **Build the graph + ainvoke.** Same shape as S7-01; the cycle naturally takes the `replan_with_phase4` path because `RagTier.lookup` returns a `RagHit` with `score < 0.85` (forced via `MockRagTier(score=0.10)` so the rag-miss → replan edge is the route).
6. **Read the three patches** from disk; compute `blake3` digests; assert distinctness.
7. **Read `attempts.jsonl`** and assert `engine_used == "phase4_llm"` × 3.

## TDD plan — red / green / refactor

### Red

Path: `tests/integration/test_phase4_retry_feedback_distinct_bytes.py`

```python
"""Phase 5 exit-criterion #19 + Phase 6 G5: three retries through replan_with_phase4
produce three distinct patch_blake3 digests; Phase 4's prompt on attempts 2 and 3
contains the fence-wrapped prior_failure_summary of every prior attempt.

Cassette regeneration procedure:
1. Set ANTHROPIC_API_KEY locally.
2. Delete tests/cassettes/cve_fixture_3retries/cassette-attempt-{1,2,3}.yaml.
3. Run: pytest tests/integration/test_phase4_retry_feedback_distinct_bytes.py --record-mode=once
4. Inspect the cassettes; redact any accidentally-captured key fragments.
5. Commit cassettes; never re-record automatically.

Amendment procedure: if Phase 4's prompt shape changes, amend the relevant Phase 4 ADR,
regenerate cassettes, and update the prompt-content assertions in the same PR.
"""

import pytest
from blake3 import blake3
from pathlib import Path
from codegenie.graph import build_vuln_loop, AuditedSqliteSaver
from tests.integration.mocks import scripted_outcomes_iter

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.timeout(60)
async def test_three_retries_produce_three_distinct_patch_blake3(
    tmp_path, monkeypatch, vcr_cve_fixture_3retries
) -> None:
    outcomes = [
        GateOutcome(passed=False, retryable=True, failing_signals=["tests"], ...),
        GateOutcome(passed=False, retryable=True, failing_signals=["build"], ...),
        GateOutcome(passed=True, retryable=True, failing_signals=[], ...),
    ]
    # ... build graph, ainvoke

    patches = sorted((tmp_path / "patches").glob("patch-attempt-*.diff"))
    assert len(patches) == 3
    digests = {blake3(p.read_bytes()).hexdigest() for p in patches}
    if len(digests) != 3:
        pytest.fail(
            f"Phase 5 exit-criterion #19 FAILED — expected 3 distinct patch digests, got {len(digests)}:\n"
            + "\n".join(f"  {p.name}: {blake3(p.read_bytes()).hexdigest()[:16]}" for p in patches)
        )

@pytest.mark.integration
@pytest.mark.slow
async def test_attempt_2_prompt_contains_fence_wrapped_attempt_1_summary(
    tmp_path, monkeypatch, vcr_cve_fixture_3retries, captured_phase4_prompts
) -> None:
    # captured_phase4_prompts fixture monkeypatches FallbackTier.run to record prompts
    ...
    attempt_2_prompt = captured_phase4_prompts[1]
    assert "<<<UNTRUSTED_INPUT_START>>>" in attempt_2_prompt
    assert "<<<UNTRUSTED_INPUT_END>>>" in attempt_2_prompt
    assert "1 test failed" in attempt_2_prompt  # the attempt-1 summary substring

@pytest.mark.integration
@pytest.mark.slow
async def test_attempt_3_prompt_contains_both_prior_summaries(...) -> None:
    ...

@pytest.mark.integration
@pytest.mark.slow
async def test_every_attempts_jsonl_entry_has_engine_used_phase4_llm(...) -> None:
    ...

@pytest.mark.integration
@pytest.mark.slow
async def test_hitl_does_not_fire_when_third_attempt_passes(...) -> None:
    # No interrupt.raised in audit chain; human_request is None.
    ...
```

Run; commit red.

### Green

- The first failure on a fresh run is likely **cassette mismatch** — the request body the test builds doesn't match the recorded cassette. The remedy is *not* to re-record (that masks real drift); the remedy is to compare the diff between the request the test sends and the request the cassette expects, identify the drift, and fix the side that moved.
- The second-most-likely red is **fence-marker syntax** — the test asserts `<<<UNTRUSTED_INPUT_START>>>` but Phase 4's `FenceWrapper` uses a different token. Read Phase 4's source first; the test should match the producer's syntax, not invent its own.
- The third-most-likely is **patch-on-disk path** — S4-03 may write to `.codegenie/remediation/<run-id>/patches/` rather than `tmp_path/patches/`. Confirm against S4-03's implementation and align.

### Refactor

- **The captured-prompt fixture is the load-bearing seam.** Factor it into `tests/integration/conftest.py` as `captured_phase4_prompts` — a `list[str]` that survives the test invocation. S7-04's malformed-decision test does not need it; this story owns the fixture.
- **Do not parametrize this test on `max_attempts`.** The test is about the retry-feedback loop, not the cap; running 3 retries with `max_attempts=3` is the canonical shape.
- **Do not import Phase 4's `FenceWrapper` directly to compute the expected prompt content.** The test's assertion is on the *observed* prompt content. If `FenceWrapper`'s output format changes silently, the test catches it; if the test computed expected via `FenceWrapper`, the test would silently follow the change.
- **`pytest.fail` with a structured message** when patch digests aren't distinct — naming the three digest prefixes makes the failure mode immediately actionable.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase4_retry_feedback_distinct_bytes.py` | New — the G5 / Phase 5 exit #19 gate. |
| `tests/cassettes/cve_fixture_3retries/cassette-attempt-1.yaml` | New — recorded Phase 4 LLM response for attempt 1 (no `prior_attempts`). |
| `tests/cassettes/cve_fixture_3retries/cassette-attempt-2.yaml` | New — response with `prior_attempts=[attempt-1]`. |
| `tests/cassettes/cve_fixture_3retries/cassette-attempt-3.yaml` | New — response with `prior_attempts=[attempt-1, attempt-2]`. |
| `tests/cassettes/README.md` | New — cassette regeneration procedure; `record_mode=none` discipline. |
| `tests/integration/conftest.py` | Extend — `vcr_cve_fixture_3retries` fixture; `captured_phase4_prompts` monkeypatch fixture. |
| `tests/integration/mocks.py` | Extend — `MockRagTier(score=...)` if not yet present to force the rag-miss path. |
| `pyproject.toml` | Extend — `pytest-recording` (or `vcrpy`) dependency added under `[tool.uv.dev-dependencies]`. |

## Out of scope

- **Phase 5 byte-parity** — S7-02. This story exercises Phase 6 only; parity gate is separate.
- **HITL interrupt** — S7-01. The third attempt passes; HITL never fires.
- **Phase 4 prompt content beyond fence-wrapping** — the test verifies the fence markers and the prior-summary substring; it does not verify the full prompt template (which is Phase 4's own concern and is tested in Phase 4's contract-snapshot test).
- **VCR cassette content auditing** — operator-facing concern; documented in `tests/cassettes/README.md`. The test asserts cassettes exist and load; it does not lint cassette content for accidentally-captured secrets (a pre-commit hook covers that).
- **`max_attempts=2` variant** — exercised by S7-01 for HITL; the 3-retry-feedback gate is `max_attempts=3` only.
- **Replay-after-kill mid-cycle** — Step 8.

## Notes for the implementer

- **The three cassettes must be authentic.** Record them against the real Anthropic API with a real CVE input. Faking cassettes (hand-writing the YAML) defeats the test: the whole point is that Phase 4's LLM, in production-shaped conditions, returns three distinct responses to three distinct (fence-wrapped, `prior_attempts`-bearing) prompts.
- **The patches must be distinct because the LLM produced distinct responses.** If the three cassettes happen to contain identical patches (an LLM determinism quirk), regenerate the cassettes with a slightly varied fixture until the LLM produces distinct outputs. The test's premise is that fence-wrapped prior failures change the LLM's output; if they don't, Phase 4's prompt builder is broken (the prior summary isn't reaching the LLM at all).
- **Cassette regeneration is a manual, audited procedure.** A maintainer who runs the test with `record_mode=once` and commits new cassettes must include in the PR description: (a) why regeneration was necessary, (b) the diff in prompt or response, (c) confirmation that the new cassettes don't leak API keys or PII. CI must reject PRs that change cassettes without that disclosure (a `tests/cassettes/` pre-commit hook can enforce a "cassette change requires explicit disclosure" footer).
- **The fence-marker tokens are Phase 4's source, not invention.** Read `src/codegenie/llm/fence.py` (or wherever Phase 4's `FenceWrapper` lives) and copy the exact `START`/`END` tokens into the assertion. If Phase 4 uses `[[INPUT]]` instead of `<<<UNTRUSTED_INPUT_START>>>`, the assertion uses `[[INPUT]]`. The test follows the producer; the producer doesn't follow the test.
- **`prior_failure_summary` truncation is 4 KB per Phase 5's ADR-P5-002.** If the test's `MockSandboxClient` returns a longer summary (a stress test), the fence-wrapped substring in the prompt should be the truncated form. Assert the truncation explicitly only if the test deliberately exercises an over-budget summary; the happy-path summaries should be well under 4 KB.
- **Forcing the rag-miss path.** `MockRagTier(score=0.10)` returns a `RagHit` with score below the 0.85 threshold; `route_after_rag` routes to `replan_with_phase4`. If `RagTier.lookup` is patched to return `None`, the same edge fires. Pick one and document the choice in the mock fixture.
- **Test naming discipline.** The four sub-tests have descriptive names so a CI red-fail names the *what*, not just the *which test*:
  - `test_three_retries_produce_three_distinct_patch_blake3`
  - `test_attempt_2_prompt_contains_fence_wrapped_attempt_1_summary`
  - `test_attempt_3_prompt_contains_both_prior_summaries`
  - `test_every_attempts_jsonl_entry_has_engine_used_phase4_llm`
  - `test_hitl_does_not_fire_when_third_attempt_passes`
- **The wall-clock budget is loose.** With VCR replay, the test should run in 3–5 s. The 60 s budget covers CI variance and the `record_attempt` chain writes; if the test routinely runs over 30 s, surface a perf concern.
- **If Phase 4's prompt builder ever drops the fence wrapping** (e.g., a refactor that "cleans up" the markers), this test red-fails on attempt 2's prompt assertion — and the right response is to revert the Phase 4 change (the fence is a load-bearing security primitive, per Phase 4's prompt-injection adversarial tests), not to relax the assertion.
- **Effort sizing rationale.** M because (a) cassette authoring is a 1–2 hour one-time procedure, (b) the captured-prompt fixture is a single monkeypatch, (c) the five sub-tests are straightforward once the fixtures are in place, (d) the only subtle part is the fence-marker syntax which is a 5-minute Phase-4-source-read. A junior implementer should expect half a day; an experienced one ~2 hours.
