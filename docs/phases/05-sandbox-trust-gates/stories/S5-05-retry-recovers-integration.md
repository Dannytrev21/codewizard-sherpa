# Story S5-05 — Retry-recovers integration against `breaking-change-cve` fixture

**Step:** Step 5 — GateRunner three-retry loop + Phase 4 replan_hook integration
**Status:** HARDENED
**Effort:** L
**Depends on:** S5-01 (`ReplanHook` Protocol), S5-02 (`GateRunner`), S5-03 (`prior_attempts` kwarg + `compose_prior_attempts` fence helper + canary matcher counter), S5-04 (`assert_stage6_chokepoint_clean` callable export)
**ADRs honored:** ADR-0001, ADR-0002, ADR-0005, ADR-0007; phase-arch-design Gap 2 (`ReplanHook` Protocol pin)

## Validation notes (2026-05-25)

This story was hardened by the phase-story-validator before execution. The original draft expressed the right intent but its strongest-looking assertions were mutation-passing in two recurring ways: (a) the fence-prompt regex matched *any* prompt anywhere in the cassette rather than attempt-2's specifically, so a runner that skipped invoking the hook on the second attempt still passed because the cassette had been recorded with a working runner; (b) `outcome.state == "passed" and outcome.attempt == 2` is fabricable by a runner that returns a hardcoded outcome without ever calling the sandbox. Full audit at `_validation/S5-05-retry-recovers-integration.md`. Summary:

- **`§hook observability` (block).** No way to assert "the hook was invoked exactly once with `len(prior_attempts) == 1` on attempt 2" without leaking through cassette internals. Introduce a `ReplanHookSpy` Decorator at `tests/integration/_helpers/hooks.py` that wraps the real hook, captures `call_count` and `calls[i].prior_attempts`, and delegates. Three known consumers (this story, S5-01 contract test, S7-01 failed-unrecoverable test) clear the rule-of-three threshold. Drives new AC-SPY-1 + AC-PRIOR-1 + AC-MUT-OUTCOME-1.
- **`§fence-prompt assertion targeting` (block).** Replace flat `list[str]` extractor with a typed `Phase4Interaction` NamedTuple (`uri`, `prompt_text`, `prior_attempts_serialized`) returned **in cassette order**. Assertions target `interactions[1]` (the second call) and pin the *count* of fenced prompts to exactly one (AC-FENCE-TARGET-1, AC-FENCE-COUNT-1, AC-HELPER-1).
- **`§canary-pattern check` (block).** ADR-0002 §Tradeoffs row 3 and phase-arch-design Gap 2.c both require the canary matcher to be invoked. The cassette captures the outgoing prompt but not whether the matcher fired. AC-CANARY-1 reads the in-process matcher counter (instrumented by S5-03's `compose_prior_attempts`).
- **`§failing-signal identity` (block).** Goal says "attempt 1 fails on `tests`" — original AC-5 only said `failed_retryable`. AC-SIG-1 pins `failing_signals[0].kind == "tests"` and `details["first_failure"]` references the fixture's `auth/jwt.test.ts`.
- **`§ADR-0002 ≤ 4 KB fence-size invariant` (harden).** Extract the slice between `<BEGIN_PRIOR_ATTEMPT_…>` and `<END_PRIOR_ATTEMPT_…>` from attempt-2's prompt, assert `len(slice.encode("utf-8")) <= 4096` (AC-FENCE-SIZE-1).
- **`§prior_failure_summary content` (harden).** AC-SUMMARY-CONTENT-1 — the extracted slice contains both `"tests"` (signal kind) and `"auth/jwt.test.ts"` (failing path), not just the fence delimiters.
- **`§Stage-6 chokepoint coupling` (block).** Original AC-10 said "re-run `tests/schema/test_stage6_chokepoint.py` in the same pytest session as a dependency." pytest has no first-class dependency primitive. AC-CHOKEPOINT-1 imports + calls the callable `assert_stage6_chokepoint_clean(REPO_ROOT)` that S5-04 (HARDENED) commits to exporting. If not yet exported when this story executes, executor escalates — does NOT re-implement the walker inline.
- **`§ReplanHook Protocol mypy-pin` (harden).** AC-PROTO-1 — annotate the constructed hook as `hook: ReplanHook = make_orchestrator_replan_hook(...)` so `mypy --strict` catches a Protocol-shape regression at lint time.
- **`§offline-replay enforcement` (harden).** AC-OFFLINE-1 — consume `pytest-recording`'s `block_network` fixture; any escape attempt raises rather than silently re-records.
- **`§wall-clock budget enforcement` (harden).** AC-TIMEOUT-1 — `@pytest.mark.timeout(90)` (post-Docker-warm).
- **`§audit chain marker shape` (harden).** AC-CHAIN-MARKER-1 — invoke `RetryLedger.verify_chain()` and assert no `AuditChainCorrupted` raised; chain-head advancement alone is necessary-not-sufficient.
- **`§cassette-replay determinism` (harden).** AC-CASS-DET-1 — separate sibling test `test_stage6_retry_recovers_replay_stable.py` runs the scenario 3 times in one pytest session and asserts byte-identical `(outcome, ledger.head())` tuples.
- **`§evidence_paths distinct precondition` (nit).** AC-EV-PATH-1 — pre-assert `attempts[0].evidence_paths["patch"] != attempts[1].evidence_paths["patch"]` before falling back to hashing files. The `_patch_blake3_for` fallback silently equates if both attempts share the path.
- **`§Specification pattern for .expected/`** (harden) — `.expected/` is the contract for retry-recovers fixtures (Phase 7's `always-fails`, `test-removes-test` will follow). Canonical entries pinned: `phase4_chain_head.bin`, `recipe_patch.diff`, `llm_patch.diff`, `expected_first_failure.txt`.

Internal-doc drift surfaced (not patched here): phase-arch-design Gap 2 says the contract test asserts the canary matcher is invoked, but no concrete instrumentation surface is named — resolved here by adding a counter to S5-03's matcher (additive widening; in-scope for S5-03, surfaced for the implementer here).

## Context

This is the load-bearing exit-criterion test for the whole step (and one of the load-bearing tests for the phase): "the 3-retry loop, retry-1 fail → retry-2 recover, against real Phase 4." It is the integration that proves S5-01 (hook), S5-02 (loop), S5-03 (kwarg + fence helper), and S5-04 (chokepoint) compose into the intended behavior end-to-end. Attempt 1 fails on `tests`; the orchestrator's `replan_hook` calls real `FallbackTier.run` with `prior_attempts=[AttemptSummary(...)]`; Phase 4's prompt builder appends the fence-wrapped `prior_failure_summary` via `compose_prior_attempts`; the LLM produces a new patch (different `patch_blake3`); attempt 2 passes. The VCR cassette captures the Phase 4 LLM call so the test runs offline in CI; the live record-once happens during story implementation.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Process view §Scenario 2` — the exact sequence this test reproduces (attempt 1 fails, replan_hook → Phase 4, attempt 2 passes).
  - `../phase-arch-design.md §Goals` Goal 2 — "3-retry loop demonstrated end-to-end with retry-1 fail → retry-2 recover."
  - `../phase-arch-design.md §Code contracts and APIs` — `AttemptSummary`, `GateContext`, `GateOutcome`.
  - `../phase-arch-design.md §Component design — GateRunner` — `replan_hook` signature.
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `GateRunner.run` is the only sandbox-seam caller in the orchestrator path.
  - `../ADRs/0002-additive-prior-attempts-kwarg.md` — the load-bearing exit-criterion test cited in Consequences: "`tests/integration/gates/test_stage6_retry_recovers.py` is the load-bearing exit-criterion test."
  - `../ADRs/0005-phase4-chain-head-compatibility.md` — `attempts.jsonl` extends Phase 4's chain head; two entries chain into the head produced by Phase 4 for this run.
  - `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — each attempt is preceded by a `pre_execute` JSONL line.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Retry recovers integration row`.
- **Existing code:**
  - `src/codegenie/gates/runner.py` (S5-02), `src/codegenie/orchestrator/replan_hook.py` (S5-01), `src/codegenie/llm/fence.py` (S5-03), `src/codegenie/orchestrator/remediation.py` (S5-04).
  - `tests/fixtures/repos/breaking-change-cve/` — a fixture repo whose patch (recipe-produced) fails the first attempt and whose `FallbackTier.run` re-plan succeeds.

## Goal

Land `tests/integration/gates/test_stage6_retry_recovers.py` — a VCR-cassette-driven integration test that runs `GateRunner.run` against the `breaking-change-cve` fixture, asserts attempt 1 fails on `tests`, asserts attempt 2 passes after real `FallbackTier.run`, and verifies `attempts.jsonl` has two entries with distinct `sandbox_run_id` and `patch_blake3`.

## Acceptance criteria

### Fixture + helper kernels

- [ ] **(fixture)** `tests/fixtures/repos/breaking-change-cve/` exists with a deterministic Node-flavored repo: `package.json` pinned, one failing test on the recipe-produced patch (mutated assertion), passing test once the LLM-fallback patch lands; SBOM + pinned `package-lock.json` committed.
- [ ] **(fixture — Specification-pattern contract)** `tests/fixtures/repos/breaking-change-cve/.expected/` contains the four canonical entries for any retry-recovers fixture: (a) `phase4_chain_head.bin`; (b) `recipe_patch.diff`; (c) `llm_patch.diff`; (d) `expected_first_failure.txt` (the failing-signal `first_failure` value AC-SIG-1 reads). Phase-7 retry-recovers fixtures (`always-fails`, `test-removes-test`) MUST follow this shape.
- [ ] **(AC-HELPER-PKG-1)** `tests/integration/_helpers/__init__.py` exists (empty). Mirrors `tests/fence/__init__.py`, `tests/schema/__init__.py`.
- [ ] **(AC-HELPER-1)** `tests/integration/_helpers/vcr.py` exports `Phase4Interaction = NamedTuple(...)` with fields `uri: str`, `prompt_text: str` (concatenated user-role message text), `prior_attempts_serialized: str` (JSON of the `prior_attempts` kwarg, `""` if absent), AND `extract_phase4_interactions(cassette_path: Path) -> list[Phase4Interaction]` that returns interactions **in cassette order**. Helper consumes the typed fields; tests never `json.dumps(body)` ad-hoc.
- [ ] **(AC-SPY-1)** `tests/integration/_helpers/hooks.py` exports `ReplanHookSpy(inner: ReplanHook) -> ReplanHook` (Decorator). Attributes: `calls: list[GateContext]`, `call_count: int`. Type-annotated as `ReplanHook` so consumers satisfy `mypy --strict`. This story is consumer #1; S5-01 contract test and S7-01 failed-unrecoverable test are #2 and #3.

### Runner construction + Protocol shape

- [ ] **(AC-PROTO-1)** Test constructs the hook as `hook: ReplanHook = make_orchestrator_replan_hook(...)`; the spy is wrapped as `spy: ReplanHook = ReplanHookSpy(hook)`. The explicit `ReplanHook` annotation forces `mypy --strict` to catch any Protocol-shape regression at lint time.
- [ ] Test constructs a real `GateRunner` with: `client=auto_detect()` (DinD on macOS / Linux dev runners), `gate=StrictAndGate.from_yaml("stage6_validate.yaml")`, `ledger=RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=(FIXTURE / ".expected" / "phase4_chain_head.bin").read_bytes())`, `spec_builder=SandboxSpecBuilder(catalog="gates/catalog")`, `replan_hook=spy`; `max_attempts=3`.

### VCR / network discipline

- [ ] Test is decorated `@pytest.mark.vcr("cassettes/stage6_retry_recovers.yaml")` with `Authorization`, `x-api-key`, `anthropic-version` headers scrubbed; request body NOT scrubbed (the body is the prompt the test asserts against).
- [ ] **(AC-OFFLINE-1)** Test consumes `pytest-recording`'s `block_network` fixture (or equivalent VCR `RecordMode.NONE`). Any network escape during replay raises (`vcr.errors.CannotOverwriteExistingCassetteException` or equivalent) — must not silently re-record.
- [ ] **(AC-TIMEOUT-1)** `@pytest.mark.timeout(90)` decorator pins the post-Docker-warm wall-clock budget. Docker pre-pull happens in a session-scoped `pytest-docker` fixture and is excluded from the budget.

### Outcome + ledger assertions (mutation-resistant)

- [ ] **(AC-MUT-OUTCOME-1)** Asserts ALL of: `outcome.state == "passed"`, `outcome.attempt == 2`, `len(ledger.attempts()) == 2`, `attempts[0].attempt_id == 1`, `attempts[1].attempt_id == 2`, `attempts[0].outcome.state == "failed_retryable"`, `attempts[1].outcome.state == "passed"`, `attempts[0].sandbox_run_id != attempts[1].sandbox_run_id`. A runner that fabricates `GateOutcome(state="passed", attempt=2)` without looping fails on `len(attempts) == 2` and on the spy `call_count` check below.
- [ ] **(AC-SIG-1)** `attempts[0].outcome.failing_signals` is non-empty; `attempts[0].outcome.failing_signals[0].kind == "tests"`; `attempts[0].outcome.failing_signals[0].details["first_failure"] == (FIXTURE / ".expected" / "expected_first_failure.txt").read_text().strip()` (which equals `"auth/jwt.test.ts"` for this fixture).
- [ ] **(AC-PRIOR-1)** `spy.call_count == 1` (the hook is invoked exactly once, between attempt 1's failure and attempt 2's plan); `len(spy.calls[0].prior_attempts) == 1`; `spy.calls[0].prior_attempts[0].attempt_id == 1`. This is the load-bearing ADR-0002 contract assertion and cannot be observed through the cassette alone.

### Patch + evidence assertions

- [ ] **(AC-EV-PATH-1)** Pre-assert distinct paths: `attempts[0].evidence_paths["patch"] != attempts[1].evidence_paths["patch"]`. The hash check below is meaningful only when paths differ.
- [ ] Asserts `_patch_blake3_for(attempts[0]) != _patch_blake3_for(attempts[1])` (ADR-0002: "attempt 1 and attempt 2 produce distinct `patch_blake3`"). Helper reads `attempt.outcome.signals.build.details["patch_blake3"]` and falls back to BLAKE3-of-bytes at `evidence_paths["patch"]` only when the field is absent; AC-EV-PATH-1 protects against the silent-equal-paths fallback hole.

### Pre-execute markers + chain integrity (ADR-0007)

- [ ] Asserts `attempts.jsonl` contains exactly two `{"type":"pre_execute",...}` lines and two `{"type":"attempt",...}` lines, in interleaved order `pre_execute(1), attempt(1), pre_execute(2), attempt(2)`.
- [ ] **(AC-CHAIN-MARKER-1)** Asserts the audit chain is intact: `RetryLedger.verify_chain()` (or equivalent S2-01 / S2-03 API exposed by `RetryLedger`) raises no `AuditChainCorrupted`; the chain head after attempt 2 differs from the `prev_chain_head` seed. Chain head advancement alone is necessary-not-sufficient — `verify_chain()` catches a regression where `pre_execute` markers advance the head without proper BLAKE3 chaining.

### Phase-4 prompt assertions — attempt-2-specific (ADR-0002)

- [ ] **(AC-FENCE-TARGET-1)** Pull `interactions = extract_phase4_interactions(cassette_path)`. Assert `len(interactions) >= 2`; assert `re.search(r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>", interactions[1].prompt_text)` matches — i.e., the SECOND call carries the fence.
- [ ] **(AC-FENCE-COUNT-1)** `sum(1 for i in interactions if FENCE_RE.search(i.prompt_text)) == 1` — exactly ONE fenced prompt in the entire cassette, in the second slot. (A runner that double-fences or fences the wrong call fails here.)
- [ ] **(AC-FENCE-SIZE-1)** Extract the byte slice between the first `<BEGIN_PRIOR_ATTEMPT_…>` and the matching `<END_PRIOR_ATTEMPT_…>` in `interactions[1].prompt_text`. Assert `len(slice.encode("utf-8")) <= 4096` (ADR-0002 §Tradeoffs row 3).
- [ ] **(AC-SUMMARY-CONTENT-1)** The same slice contains BOTH the substring `"tests"` (the failing-signal kind) AND `"auth/jwt.test.ts"` (the failing-test path). Substring asserts, not regex over arbitrary positions.
- [ ] **(AC-CANARY-1)** S5-03's `compose_prior_attempts` helper exposes a per-process counter on its canary matcher (S5-03 widens additively if needed). Assert `canary_matcher.match_count >= 1` after the test run, recorded from the in-process matcher — NOT from the cassette.

### Stage-6 chokepoint (re-verified via callable, not test ordering)

- [ ] **(AC-CHOKEPOINT-1)** Test imports and calls `from tests.schema.test_stage6_chokepoint import assert_stage6_chokepoint_clean; assert_stage6_chokepoint_clean(REPO_ROOT)` at the end of `test_retry_recovers_against_breaking_change_cve`. S5-04 (HARDENED) commits to exporting this callable; if not yet exported when this story executes, executor escalates story to BLOCKED-on-S5-04 — does NOT re-implement the walker inline.

### Replay stability + housekeeping

- [ ] **(AC-CASS-DET-1)** Sibling test `tests/integration/gates/test_stage6_retry_recovers_replay_stable.py` (marker `@pytest.mark.cassette_stability`) runs the scenario **3 times in the same pytest session** and asserts byte-identical `(outcome.state, outcome.attempt, ledger.head())` tuples across runs. Faster than 10× but mutation-resistant against per-run state leakage.
- [ ] Cassette `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` is committed with all secrets scrubbed. Recording step documented in `tests/integration/gates/RECORDING.md` (or in the test module docstring).
- [ ] **(AC-DOC-1)** Test module docstring contains substrings `"ADR-0001"`, `"ADR-0002"`, `"ADR-0005"`, `"ADR-0007"`, `"§Goal 2"`. Verified via a sub-test in the same file using `inspect.getdoc`.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff`, `mypy --strict`, `pytest tests/integration/gates/test_stage6_retry_recovers.py tests/integration/gates/test_stage6_retry_recovers_replay_stable.py` pass; all six fence/structural CI tests remain green (including `tests/schema/test_no_subprocess_outside_build_chokepoint.py` — see Notes-for-implementer §subprocess-allowlist).

## Implementation outline

1. **Helper kernels first** (Open/Closed seams — used by this story, S5-01, S7-01):
   - Create `tests/integration/_helpers/__init__.py` (empty, package marker).
   - Create `tests/integration/_helpers/vcr.py` with `Phase4Interaction` NamedTuple + `extract_phase4_interactions(cassette_path: Path) -> list[Phase4Interaction]`. Parse the cassette YAML, walk `data["interactions"]` in order, for each POST to the Anthropic messages endpoint decode the request body, extract `messages[*].content` as a concatenated `prompt_text`, extract `prior_attempts` (default `""`) as `prior_attempts_serialized`. Returns interactions IN CASSETTE ORDER.
   - Create `tests/integration/_helpers/hooks.py` with `ReplanHookSpy(inner: ReplanHook) -> ReplanHook` (Decorator). Records every `__call__` into `self.calls: list[GateContext]`; exposes `call_count`. Type-checks at `mypy --strict` as satisfying `ReplanHook`.

2. **Create the fixture** `tests/fixtures/repos/breaking-change-cve/`:
   - Minimal `package.json` (Node 20, one dep with a fixable CVE).
   - One Jest test file `auth/jwt.test.ts` that asserts `expect(status).toBe(200)`; the recipe-produced patch makes the API return 401 (breaking the test). The fallback-LLM patch fixes it (e.g., updates the token verification call path).
   - Pinned `package-lock.json`, pre-patch SBOM under `tests/fixtures/repos/breaking-change-cve/.sbom.json`.
   - `.expected/` directory follows the **Specification-pattern contract** for retry-recovers fixtures with EXACTLY four canonical entries: `phase4_chain_head.bin`, `recipe_patch.diff`, `llm_patch.diff`, `expected_first_failure.txt`. Phase-7 fixtures (`always-fails`, `test-removes-test`) MUST follow this shape (Notes for the implementer §`.expected/` contract).

3. **Author the integration test** at `tests/integration/gates/test_stage6_retry_recovers.py`:
   - `tmp_path` fixture for the run dir; copy fixture into a worktree.
   - Build `GateContext` with `worktree`, `advisory`, `recipe`, `transform_output` (the recipe-produced patch from `.expected/recipe_patch.diff`), `prior_attempts=[]`.
   - Construct `hook: ReplanHook = make_orchestrator_replan_hook(...)`; wrap as `spy: ReplanHook = ReplanHookSpy(hook)`.
   - Construct `GateRunner` with real components and `replan_hook=spy`.
   - Invoke `runner.run(ctx)` under `@pytest.mark.vcr` + `@pytest.mark.timeout(90)` + `block_network` fixture.
   - Assert per the acceptance criteria above (mutation-resistant order: spy + ledger + signals first, then cassette assertions, then chokepoint callable).

4. **Record the cassette**: run the test once with `--record-mode=once` against a live Anthropic API key in a developer environment; commit the cassette with scrubbed headers (body NOT scrubbed); verify replay-only run with `block_network` active passes. The recorded cassette must contain EXACTLY two outgoing Phase-4 invocations (one un-fenced for attempt 1, one fenced for attempt 2) — AC-FENCE-COUNT-1 catches a drift.

5. **Sibling replay-stability test** at `tests/integration/gates/test_stage6_retry_recovers_replay_stable.py`: marker `@pytest.mark.cassette_stability`; runs `runner.run(ctx)` three times against fresh `tmp_path` directories in the same pytest session; asserts the `(outcome.state, outcome.attempt, ledger.head())` tuple is byte-identical across runs.

6. **Canary-matcher counter wire** (cross-story, additive): if S5-03's `compose_prior_attempts` matcher does not yet expose a `match_count` attribute, the executor widens it additively here — no surface change to existing callers, default `match_count = 0` increments on each match. If S5-03 has already shipped GREEN without it, the widening is a minor edit to `src/codegenie/llm/fence.py`; flag in attempt log.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/gates/test_stage6_retry_recovers.py`

```python
# tests/integration/gates/test_stage6_retry_recovers.py
"""
Stage-6 retry-recovers integration test against the `breaking-change-cve` fixture.

Honors ADR-0001 (single sandbox seam), ADR-0002 (additive `prior_attempts` kwarg with
fence-wrapped, canary-checked summary, ≤ 4 KB), ADR-0005 (Phase-4 chain-head
compatibility), ADR-0007 (pre-execute marker for resume safety). Realizes §Goal 2 of
the phase: "3-retry loop demonstrated end-to-end with retry-1 fail → retry-2 recover."
"""
from __future__ import annotations

import hashlib
import inspect
import json
import re
from pathlib import Path

import pytest

from codegenie.gates.contract import GateContext, ReplanHook
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.gates.runner import GateRunner
from codegenie.gates.strict_and import StrictAndGate
from codegenie.llm.fence import compose_prior_attempts  # S5-03 — exposes .canary_matcher
from codegenie.orchestrator.replan_hook import make_orchestrator_replan_hook
from codegenie.sandbox.registry import auto_detect
from codegenie.sandbox.spec_builder import SandboxSpecBuilder

from tests.integration._helpers.hooks import ReplanHookSpy
from tests.integration._helpers.vcr import (
    Phase4Interaction,
    extract_phase4_interactions,
)
from tests.schema.test_stage6_chokepoint import assert_stage6_chokepoint_clean

REPO_ROOT = Path(__file__).parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "repos" / "breaking-change-cve"
CASSETTE = Path(__file__).parent / "cassettes" / "stage6_retry_recovers.yaml"
FENCE_RE = re.compile(r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>")
FENCE_SLICE_RE = re.compile(
    r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>(?P<body>.*?)<END_PRIOR_ATTEMPT_[A-F0-9]{16}>",
    re.DOTALL,
)


@pytest.fixture
def gate_ctx_breaking_change(tmp_path: Path) -> GateContext:
    # Copy fixture into a worktree; build advisory/recipe/transform_output from .expected/.
    ...


@pytest.fixture
def real_runner(tmp_path: Path, fallback_tier, repo_ctx, recipe_selection):
    ledger = RetryLedger(
        run_dir=tmp_path,
        gate_id="stage6_validate",
        prev_chain_head=(FIXTURE / ".expected" / "phase4_chain_head.bin").read_bytes(),
    )
    hook: ReplanHook = make_orchestrator_replan_hook(
        fallback_tier=fallback_tier,
        repo_ctx=repo_ctx,
        recipe_selection=recipe_selection,
    )
    spy: ReplanHook = ReplanHookSpy(hook)  # Decorator — observe call shape.
    runner = GateRunner(
        client=auto_detect(),
        gate=StrictAndGate.from_yaml("stage6_validate.yaml"),
        ledger=ledger,
        spec_builder=SandboxSpecBuilder(catalog="gates/catalog"),
        replan_hook=spy,
        max_attempts=3,
    )
    return runner, ledger, spy


def _patch_blake3_for(attempt) -> str:
    details = attempt.outcome.signals.build.details
    if "patch_blake3" in details:
        return details["patch_blake3"]
    return hashlib.blake2b(
        Path(details["patch_path"]).read_bytes(), digest_size=16
    ).hexdigest()


def test_module_docstring_cites_load_bearing_adrs() -> None:
    """AC-DOC-1 — docstring is the reader's first hop to the four ADRs."""
    doc = inspect.getdoc(__import__(__name__)) or ""
    for needle in ("ADR-0001", "ADR-0002", "ADR-0005", "ADR-0007", "§Goal 2"):
        assert needle in doc, f"module docstring must cite {needle}"


@pytest.mark.docker
@pytest.mark.timeout(90)
@pytest.mark.vcr("cassettes/stage6_retry_recovers.yaml")
def test_retry_recovers_against_breaking_change_cve(
    real_runner, gate_ctx_breaking_change, tmp_path, block_network
):
    runner, ledger, spy = real_runner

    # Reset canary counter so AC-CANARY-1 measures THIS run, not earlier tests.
    compose_prior_attempts.canary_matcher.reset()  # S5-03 — additive widening.

    outcome = runner.run(gate_ctx_breaking_change)

    # --- AC-MUT-OUTCOME-1: outcome + ledger entries together (mutation-resistant).
    attempts = ledger.attempts()
    assert outcome.state == "passed"
    assert outcome.attempt == 2
    assert len(attempts) == 2
    assert attempts[0].attempt_id == 1
    assert attempts[1].attempt_id == 2
    assert attempts[0].outcome.state == "failed_retryable"
    assert attempts[1].outcome.state == "passed"
    assert attempts[0].sandbox_run_id != attempts[1].sandbox_run_id

    # --- AC-SIG-1: failing-signal identity on attempt 1.
    expected_first_failure = (
        FIXTURE / ".expected" / "expected_first_failure.txt"
    ).read_text().strip()
    failing = attempts[0].outcome.failing_signals
    assert failing, "attempt 1 must have at least one failing signal"
    assert failing[0].kind == "tests"
    assert failing[0].details["first_failure"] == expected_first_failure

    # --- AC-PRIOR-1: hook invoked exactly once, with one prior attempt of id 1.
    assert spy.call_count == 1, "hook must fire exactly once between attempt 1 and 2"
    assert len(spy.calls[0].prior_attempts) == 1
    assert spy.calls[0].prior_attempts[0].attempt_id == 1

    # --- AC-EV-PATH-1 + distinct patches (ADR-0002).
    assert (
        attempts[0].evidence_paths["patch"] != attempts[1].evidence_paths["patch"]
    ), "evidence path collision invalidates the patch-distinctness assertion"
    assert _patch_blake3_for(attempts[0]) != _patch_blake3_for(attempts[1])

    # --- ADR-0007: pre-execute markers interleaved correctly.
    jsonl = (tmp_path / "gates" / "stage6_validate" / "attempts.jsonl").read_text().splitlines()
    types = [json.loads(line)["type"] for line in jsonl]
    assert types == ["pre_execute", "attempt", "pre_execute", "attempt"]

    # --- AC-CHAIN-MARKER-1: ledger chain verifies + head advanced.
    ledger.verify_chain()  # raises AuditChainCorrupted on failure.
    assert ledger.head() != (FIXTURE / ".expected" / "phase4_chain_head.bin").read_bytes()

    # --- AC-FENCE-* + AC-SUMMARY-CONTENT-1: attempt-2-specific prompt assertions.
    interactions: list[Phase4Interaction] = extract_phase4_interactions(CASSETTE)
    assert len(interactions) >= 2, "cassette must contain at least two Phase 4 calls"
    fenced_count = sum(1 for i in interactions if FENCE_RE.search(i.prompt_text))
    assert fenced_count == 1, "exactly one fenced prompt expected (attempt 2's)"
    assert FENCE_RE.search(interactions[1].prompt_text), "fence must target attempt 2"
    match = FENCE_SLICE_RE.search(interactions[1].prompt_text)
    assert match is not None
    slice_body = match.group("body")
    assert len(slice_body.encode("utf-8")) <= 4096, "ADR-0002 ≤ 4 KB fence size"
    assert "tests" in slice_body
    assert "auth/jwt.test.ts" in slice_body

    # --- AC-CANARY-1: canary matcher fired in-process (not just on the wire).
    assert compose_prior_attempts.canary_matcher.match_count >= 1

    # --- AC-CHOKEPOINT-1: re-verify the Stage-6 chokepoint via S5-04's callable.
    assert_stage6_chokepoint_clean(REPO_ROOT)
```

Sibling replay-stability test `tests/integration/gates/test_stage6_retry_recovers_replay_stable.py`:

```python
"""AC-CASS-DET-1 — replay stability: 3 runs in one session, byte-identical tuples."""
from __future__ import annotations

from pathlib import Path

import pytest

# Reuses the fixtures from the sibling test module by relative import.
from .test_stage6_retry_recovers import real_runner, gate_ctx_breaking_change, CASSETTE


@pytest.mark.docker
@pytest.mark.cassette_stability
@pytest.mark.vcr(str(CASSETTE))
def test_replay_stable_3x(real_runner, gate_ctx_breaking_change, block_network) -> None:
    runner, ledger, _spy = real_runner
    runs: list[tuple[str, int, bytes]] = []
    for _ in range(3):
        # Each iteration uses fresh tmp_path via the parametrized fixture cycle.
        outcome = runner.run(gate_ctx_breaking_change)
        runs.append((outcome.state, outcome.attempt, ledger.head()))
    assert runs.count(runs[0]) == 3, f"replay drift: {runs!r}"
```

### Green — make it pass

- Land helper kernels first (`tests/integration/_helpers/{__init__,vcr,hooks}.py`); they are consumed day-1 by this story and pre-positioned for S5-01 contract test + S7-01 failed-unrecoverable test (rule-of-three).
- Fill in the `gate_ctx_breaking_change` fixture by copying the fixture repo into `tmp_path` and constructing `GateContext` from `.expected/recipe_patch.diff` + advisory/recipe/transform_output stubs.
- Record the cassette once: `pytest tests/integration/gates/test_stage6_retry_recovers.py --record-mode=once -k retry_recovers` with a live key; scrub headers via the VCR `before_record_request` hook in `tests/conftest.py`; body NOT scrubbed (the body is the prompt).
- If `compose_prior_attempts.canary_matcher` does not yet expose `match_count` / `reset()`, widen S5-03's matcher additively (no surface change to existing callers; default `match_count = 0`).
- Commit cassette + fixture + helpers; verify replay-only run with `block_network` passes; verify the replay-stability sibling test passes.

### Refactor — clean up

- Confirm `Phase4Interaction` + `extract_phase4_interactions` are typed and clean; add `mypy --strict` to the helper module's CI invocation. Future cassette assertions extend the NamedTuple additively.
- Confirm `ReplanHookSpy` is type-annotated as satisfying `ReplanHook` (so consumers' `mypy --strict` catches Protocol drift).
- Add module docstring per AC-DOC-1; verified by the in-file `test_module_docstring_cites_load_bearing_adrs` sub-test.
- If `_patch_blake3_for` falls back to hashing the file, document the precondition (the build signal collector must populate `details["patch_path"]`) and confirm AC-EV-PATH-1 catches the silent-equal-paths failure mode.
- If non-deterministic replay surfaces in the 3-run stability test, deterministic-seed Phase 4's RNG or trim the cassette to prompt-bearing requests only — do NOT relax the determinism AC.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/_helpers/__init__.py` | Package marker (AC-HELPER-PKG-1). |
| `tests/integration/_helpers/vcr.py` | `Phase4Interaction` NamedTuple + `extract_phase4_interactions` — typed cassette-introspection kernel. |
| `tests/integration/_helpers/hooks.py` | `ReplanHookSpy` Decorator — observes hook-call shape; satisfies `ReplanHook` Protocol. |
| `tests/fixtures/repos/breaking-change-cve/` | New fixture repo. |
| `tests/fixtures/repos/breaking-change-cve/.expected/phase4_chain_head.bin` | Seed chain head produced by Phase 4 for this fixture. |
| `tests/fixtures/repos/breaking-change-cve/.expected/recipe_patch.diff` | Canonical recipe-produced diff (deterministic input for attempt 1). |
| `tests/fixtures/repos/breaking-change-cve/.expected/llm_patch.diff` | Canonical Phase-4 fallback diff (recorded answer for attempt 2). |
| `tests/fixtures/repos/breaking-change-cve/.expected/expected_first_failure.txt` | The `first_failure` string AC-SIG-1 asserts (`auth/jwt.test.ts`). |
| `tests/integration/gates/test_stage6_retry_recovers.py` | The integration test. |
| `tests/integration/gates/test_stage6_retry_recovers_replay_stable.py` | AC-CASS-DET-1 sibling 3-run stability test. |
| `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` | Recorded once, committed. |
| `tests/integration/gates/conftest.py` | `fallback_tier`, `repo_ctx`, `recipe_selection`, `block_network` fixtures. |
| `src/codegenie/llm/fence.py` | Additive: expose `match_count` / `reset()` on `compose_prior_attempts.canary_matcher` if not already present (S5-03 widening, no surface change to existing callers). |
| `pyproject.toml` | Confirm `pytest-recording`, `pytest-docker`, `pytest-timeout` are present in dev deps. |

## Out of scope

- `failed_unrecoverable` 3× integration — covered by `tests/integration/gates/test_failed_unrecoverable.py` listed in `High-level-impl.md §Step 5 Done criteria` (separate concern; can be a follow-up under S7-01).
- KVM/Firecracker backend — Step 6.
- Adversarial fixtures (`always-fails`, `postinstall-exfil`, etc.) — S7-01.
- Cost ledger row assertion — S7-03 (this story does not assert `sandbox.jsonl` contents).
- E2E `codegenie remediate` CLI invocation — S8-03 wraps this test in a CLI-level test.

## Notes for the implementer

- **Cassette discipline.** The cassette is the load-bearing artifact for CI determinism. Scrub `Authorization`, `x-api-key`, `anthropic-version` headers; do **not** scrub the request body — the body is the prompt and the test asserts against it. The cassette must contain EXACTLY two outgoing Phase-4 invocations (one unfenced for attempt 1, one fenced for attempt 2); AC-FENCE-COUNT-1 catches drift. If a re-record produces extra calls, trim deterministically.
- **`.expected/` is the Specification-pattern contract.** Treat it as the contract for ALL retry-recovers fixtures. Future fixtures (`always-fails`, `test-removes-test`, `postinstall-exfil` per Phase 7) MUST follow the same four-entry shape: `phase4_chain_head.bin` + `recipe_patch.diff` + `llm_patch.diff` + `expected_first_failure.txt`. The integration tests then differ only in their fixture path, not in their structure.
- **`ReplanHookSpy` is a kernel, not a one-off.** Three known consumers — this story (AC-PRIOR-1), S5-01 contract test (Gap-2 hook contract), S7-01 failed-unrecoverable test (three identical failures → escalate). Land it at `tests/integration/_helpers/hooks.py` from day-1; the rule-of-three threshold is already cleared. Annotating it `ReplanHook` makes any future Protocol drift a `mypy --strict` failure at every call site.
- **`Phase4Interaction` is the cassette-introspection kernel.** The original draft used a flat `list[str]` of JSON-serialized bodies, which is a leaky abstraction over VCR's envelope shape. The NamedTuple typing means a future cassette assertion (e.g., "the model name on attempt 2 differs from attempt 1") grows the helper additively without rewriting consumers.
- **Canary-matcher counter widening (cross-story).** AC-CANARY-1 reads `compose_prior_attempts.canary_matcher.match_count`. If S5-03's matcher does not yet expose this, widen additively in `src/codegenie/llm/fence.py` — default `match_count = 0` plus a `reset()` method. No existing-caller surface changes. Flag the widening in the attempt log so S5-03's report stays accurate.
- **`_patch_blake3_for` strategy registry — deferred.** Two source paths today (`details["patch_blake3"]` and `evidence_paths["patch"]` fallback). Rule-2 simplicity wins until a third source arrives (Phase 7 distroless will likely emit `dockerfile_patch_blake3`). When it does, elevate to `@register_patch_blake3_source(...)` — but NOT today.
- **Determinism guardrails.** The fixture repo's recipe-produced patch must be byte-stable (same input → same diff). If recipe-selection introduces nondeterminism (timestamps, random IDs), seed it via the `recipe_selection` fixture. Phase 4's recorded response must be the patch that makes the test pass — if a re-record produces a different patch, either re-record again or adjust the fixture's test so one specific patch lands green. The test is NOT an LLM oracle; it tests that the loop behaves correctly given a Phase 4 doing its job.
- **`prev_chain_head` is a fixture seed, not a Phase-4 invocation.** Avoids needing Phase 4 to run in the test setup. Full chain-head-compat is S2-03's job; this story only needs an extension target.
- **Subprocess-allowlist defense.** ADR-0001 §Consequences names `tests/schema/test_no_subprocess_outside_build_chokepoint.py` as a separate structural fence. A fixture helper introduced by this story (or by a future retry-recovers fixture) must NOT import `subprocess` directly. AC-CHOKEPOINT-1 covers the import-level Stage-6 chokepoint; the subprocess fence is independent and runs as part of `make check`. Re-run it locally before commit.
- **Surface-a-real-bug discipline.** If the test surfaces a real bug in `GateRunner` (e.g., the loop calls `replan_hook` *before* recording attempt 1's outcome — the spy's `call_count` would still be 1 but the ledger ordering would break), fix the bug in `runner.py` — that is the test's job — and do not patch around it in this story.
