# Story S5-05 — Retry-recovers integration against `breaking-change-cve` fixture

**Step:** Step 5 — GateRunner three-retry loop + Phase 4 replan_hook integration
**Status:** Ready
**Effort:** L
**Depends on:** S5-03, S5-04
**ADRs honored:** ADR-0001, ADR-0002, ADR-0005, ADR-0007

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

- [ ] `tests/fixtures/repos/breaking-change-cve/` exists with a deterministic Node-flavored repo: `package.json` pinned, one failing test on the recipe-produced patch (mutated assertion), passing test once the LLM-fallback patch lands; SBOM + lockfile committed.
- [ ] `tests/integration/gates/test_stage6_retry_recovers.py` constructs a real `GateRunner` with: `client=auto_detect()` (DinD on macOS / Linux dev runners), `gate=StrictAndGate.from_yaml("stage6_validate.yaml")`, `ledger=RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=<phase4_chain_head_for_fixture>)`, `spec_builder=SandboxSpecBuilder(catalog=...)`, `replan_hook=make_orchestrator_replan_hook(...)`; `max_attempts=3`.
- [ ] The test is decorated `@pytest.mark.vcr("cassettes/stage6_retry_recovers.yaml")` with `Authorization` and `x-api-key` headers scrubbed; replays offline (`pytest --no-network`).
- [ ] Asserts `outcome.state == "passed"` and `outcome.attempt == 2`.
- [ ] Asserts `len(ledger.attempts()) == 2`; `ledger.attempts()[0].outcome.state == "failed_retryable"`; `ledger.attempts()[1].outcome.state == "passed"`; `ledger.attempts()[0].sandbox_run_id != ledger.attempts()[1].sandbox_run_id`.
- [ ] Asserts `_patch_blake3(attempt 1) != _patch_blake3(attempt 2)` — distinct patches per ADR-0002 ("attempt 1 and attempt 2 produce distinct `patch_blake3`"). The helper reads `attempt.outcome.signals.build.details["patch_blake3"]` (or the equivalent recorded field; if unavailable, hash the captured diff bytes directly from `evidence_paths["patch"]`).
- [ ] Asserts pre-execute markers: `attempts.jsonl` contains exactly two `{"type":"pre_execute",...}` lines and two `{"type":"attempt",...}` lines, in interleaved order `pre_execute(1), attempt(1), pre_execute(2), attempt(2)` (ADR-0007).
- [ ] Asserts Phase 4 prompt on attempt 2 demonstrably contains the fenced `prior_failure_summary` — pull the captured prompt text from the cassette and `re.search(r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>", text)`.
- [ ] Asserts the audit chain is intact: `ledger.attempts()` round-trips without raising `AuditChainCorrupted`, and the chain head after attempt 2 differs from the `prev_chain_head` seed.
- [ ] Asserts the Stage 6 chokepoint held in this run: no `validation.*` symbol was imported by any module outside the S5-04 allowlist (sanity-checked by re-running `tests/schema/test_stage6_chokepoint.py` in the same pytest session as a dependency).
- [ ] Cassette `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` is committed with all secrets scrubbed; the recording step is documented in a `tests/integration/gates/RECORDING.md` (or a `Notes for the implementer` reference in the test docstring).
- [ ] Test wall-clock budget: ≤ 90 s under cassette replay on a clean checkout (Docker pull excluded; image is pre-warmed by a `pytest-docker` autouse fixture).
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff`, `mypy --strict`, `pytest tests/integration/gates/test_stage6_retry_recovers.py` pass; all six fence/structural CI tests remain green.

## Implementation outline

1. Create the fixture `tests/fixtures/repos/breaking-change-cve/`:
   - Minimal `package.json` (Node 20, one dep with a fixable CVE).
   - One Jest test file `auth/jwt.test.ts` that asserts `expect(status).toBe(200)`; the recipe-produced patch makes the API return 401 (breaking the test). The fallback-LLM patch fixes it (e.g., updates the token verification call path).
   - Pinned `package-lock.json`, pre-patch SBOM under `tests/fixtures/repos/breaking-change-cve/.sbom.json`.
   - A `.expected/` directory documenting the canonical recipe diff and the canonical LLM-fallback diff for ease of cassette regeneration.
2. Author the test:
   - `tmp_path` fixture for the run dir; copy fixture into a worktree.
   - Build `GateContext` with `worktree`, `advisory`, `recipe`, `transform_output` (the recipe-produced patch), and `prior_attempts=[]`.
   - Construct `GateRunner` with real components.
   - Invoke `runner.run(ctx)` under `@pytest.mark.vcr`.
   - Assert per the acceptance criteria.
3. Record the cassette: run the test once with `--record-mode=once` against a live Anthropic API key in a developer environment; commit the cassette with scrubbed credentials; verify `pytest --no-network` replays.
4. Helper `_extract_phase4_prompt(cassette_path) -> str`: parse the cassette YAML, find the POST to the Anthropic messages endpoint, decode the `content` field; return the text. Use this in the fence-pattern assertion.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/gates/test_stage6_retry_recovers.py`

```python
# tests/integration/gates/test_stage6_retry_recovers.py
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

from codegenie.gates.contract import GateContext
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.gates.runner import GateRunner
from codegenie.gates.strict_and import StrictAndGate
from codegenie.orchestrator.replan_hook import make_orchestrator_replan_hook
from codegenie.sandbox.registry import auto_detect
from codegenie.sandbox.spec_builder import SandboxSpecBuilder

FIXTURE = Path(__file__).parents[3] / "tests" / "fixtures" / "repos" / "breaking-change-cve"


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
    return GateRunner(
        client=auto_detect(),
        gate=StrictAndGate.from_yaml("stage6_validate.yaml"),
        ledger=ledger,
        spec_builder=SandboxSpecBuilder(catalog="gates/catalog"),
        replan_hook=make_orchestrator_replan_hook(
            fallback_tier=fallback_tier,
            repo_ctx=repo_ctx,
            recipe_selection=recipe_selection,
        ),
        max_attempts=3,
    ), ledger


def _patch_blake3_for(attempt) -> str:
    return attempt.outcome.signals.build.details.get("patch_blake3") or hashlib.blake2b(
        Path(attempt.outcome.signals.build.details["patch_path"]).read_bytes(),
        digest_size=16,
    ).hexdigest()


def _extract_phase4_prompts(cassette_path: Path) -> list[str]:
    data = yaml.safe_load(cassette_path.read_text())
    prompts: list[str] = []
    for interaction in data["interactions"]:
        req = interaction["request"]
        if "messages" in (req.get("uri") or "") and req.get("body"):
            body = json.loads(req["body"]["string"] if isinstance(req["body"], dict) else req["body"])
            prompts.append(json.dumps(body))
    return prompts


@pytest.mark.docker
@pytest.mark.vcr("cassettes/stage6_retry_recovers.yaml")
def test_retry_recovers_against_breaking_change_cve(
    real_runner, gate_ctx_breaking_change, tmp_path
):
    runner, ledger = real_runner

    outcome = runner.run(gate_ctx_breaking_change)

    # Loop terminated on attempt 2 with pass.
    assert outcome.state == "passed"
    assert outcome.attempt == 2

    # Ledger has exactly two attempt entries.
    attempts = ledger.attempts()
    assert len(attempts) == 2
    assert attempts[0].outcome.state == "failed_retryable"
    assert attempts[1].outcome.state == "passed"
    assert attempts[0].sandbox_run_id != attempts[1].sandbox_run_id

    # Distinct patches across attempts (ADR-0002).
    assert _patch_blake3_for(attempts[0]) != _patch_blake3_for(attempts[1])

    # Pre-execute markers interleaved correctly (ADR-0007).
    jsonl = (tmp_path / "gates" / "stage6_validate" / "attempts.jsonl").read_text().splitlines()
    types = [json.loads(line)["type"] for line in jsonl]
    assert types == ["pre_execute", "attempt", "pre_execute", "attempt"]

    # Phase 4 prompt on attempt 2 contains a fenced prior_failure_summary (ADR-0002).
    prompts = _extract_phase4_prompts(
        Path(__file__).parent / "cassettes" / "stage6_retry_recovers.yaml"
    )
    assert prompts, "cassette must contain at least one Phase 4 LLM call"
    fenced = [p for p in prompts if re.search(r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>", p)]
    assert fenced, "attempt 2's prompt must include the fenced prior_failure_summary block"

    # Chain head advanced.
    assert ledger.head() != (FIXTURE / ".expected" / "phase4_chain_head.bin").read_bytes()
```

### Green — make it pass

- Fill in the `gate_ctx_breaking_change` fixture by copying the fixture repo into `tmp_path` and constructing `GateContext` from `.expected/` artifacts.
- Record the cassette once: `pytest tests/integration/gates/test_stage6_retry_recovers.py --record-mode=once -k retry_recovers` with a live key; scrub headers in the VCR `before_record_request` hook configured in `tests/conftest.py`.
- Commit cassette + fixture; verify replay-only run passes.

### Refactor — clean up

- Extract `_extract_phase4_prompts` into a shared helper under `tests/integration/_helpers/vcr.py`.
- Add a docstring on the test citing the four ADRs and Goal 2.
- If `_patch_blake3_for` falls back to hashing the file, document the precondition (the build signal collector must populate `details["patch_path"]`).
- Verify the cassette is replay-stable by running 10 consecutive `pytest --no-network` cycles; if non-deterministic, deterministic-seed Phase 4's RNG or trim the cassette to the prompt-bearing requests only.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/repos/breaking-change-cve/` | New fixture repo + `.expected/` artifacts. |
| `tests/fixtures/repos/breaking-change-cve/.expected/phase4_chain_head.bin` | Seed chain head produced by Phase 4 for this fixture. |
| `tests/integration/gates/test_stage6_retry_recovers.py` | The integration test. |
| `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` | Recorded once, committed. |
| `tests/integration/gates/conftest.py` | `fallback_tier`, `repo_ctx`, `recipe_selection` fixtures. |
| `tests/integration/_helpers/vcr.py` | Shared cassette-prompt extractor. |
| `pyproject.toml` | Confirm `pytest-recording` / `pytest-docker` are present. |

## Out of scope

- `failed_unrecoverable` 3× integration — covered by `tests/integration/gates/test_failed_unrecoverable.py` listed in `High-level-impl.md §Step 5 Done criteria` (separate concern; can be a follow-up under S7-01).
- KVM/Firecracker backend — Step 6.
- Adversarial fixtures (`always-fails`, `postinstall-exfil`, etc.) — S7-01.
- Cost ledger row assertion — S7-03 (this story does not assert `sandbox.jsonl` contents).
- E2E `codegenie remediate` CLI invocation — S8-03 wraps this test in a CLI-level test.

## Notes for the implementer

- The cassette is the load-bearing artifact for CI determinism. Scrub `Authorization`, `x-api-key`, `anthropic-version` headers; do **not** scrub the request body — the body is the prompt and the test asserts against it.
- The fixture repo's recipe-produced patch must be deterministic (same input → same diff) so the attempt-1 failure is repeatable. If the recipe path uses any nondeterminism (timestamps, random IDs), seed it via the `recipe_selection` fixture.
- Phase 4's response in the cassette must be the patch that *makes the test pass*. If during recording the model produces a different patch, re-record or adjust the fixture's test so that one specific patch lands the green run. The point is **not** to bake an oracle; the point is to test the loop's behavior given a Phase 4 that does its job.
- `prev_chain_head` for the ledger is read from a fixture binary — this avoids needing Phase 4 to run in the test setup. The full chain-head-compat check (S2-03) is exercised independently; this story only needs an extension target.
- Wall-clock budget: 90 s under cassette replay assumes Docker pre-pull. Add `@pytest.mark.docker` and a `pytest-docker` warm-pull fixture; do not include `docker pull` time in the budget.
- If the test surfaces a real bug in `GateRunner` (e.g., the loop calls `replan_hook` *before* recording attempt 1's outcome), fix the bug in `runner.py` — that is the test's job — and do not patch around it in this story.
- The chokepoint check at the end is a session-scoped sanity-check, not a redundant test. It catches regressions where this story accidentally introduces a direct `validation.*` reach (e.g., in a fixture helper). Keep it.
