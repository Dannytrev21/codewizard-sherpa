# Story S7-05 — Phase-3 regression hard-gate + Phase-5 handoff contract test

**Step:** Step 7 — Harden — adversarial corpus, recall@3, perf canaries, E2E exit criterion, Phase-3 regression, Phase-5 handoff, CI gates
**Status:** Ready
**Effort:** M
**Depends on:** S7-04
**ADRs honored:** ADR-P4-001, ADR-P4-002, ADR-P4-003, ADR-P4-004

## Context

Two distinct guarantees this story locks in. (1) **Phase-3 regression hard-gate (G15):** Phase 4 was allowed exactly two ADR-gated edits into Phase 3 — `Recipe.engine` Literal extension (ADR-P4-001) and the orchestrator's writeback-stub branch (ADR-P4-002). Every other Phase-3 integration test must still pass byte-identically. `test_phase3_unchanged.py` re-runs every Phase-3 integration test verbatim and gates merge. (2) **Phase-5 handoff contract test:** a Phase-5-shaped consumer reads the four contracts Phase 4 hands forward — `LeafLlmAgent` Protocol, `Plan` envelope (with `kind` + `target_files`), `SolvedExample.engine_trajectory`, `OutputValidator.errors[].kind` — by importing **only** the contract modules (`llm/contract.py`, `rag/contract.py`, `rag/models.py`, `llm/output_validator.py`), swaps in a stub `MicroVmLeafLlmAgent`, and exercises the four read patterns. If any contract slips, Phase 5 finds out at merge time, not on integration.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Integration with Phase 5 (next phase)"` — enumerates the four contracts the handoff test must pin (`LeafLlmAgent` Protocol, `Plan` envelope + `PathAllowlistProvider` registry seam, `SolvedExample.engine_trajectory`, `OutputValidator.errors[].kind`).
  - `../phase-arch-design.md §"Goals"` G15 — Phase 3 contract change is exactly two ADRs; no other Phase 0–3 code edited.
  - `../phase-arch-design.md §"Development view" → "Stable contracts vs internal helpers"` — names the three contract files Phase 5 may import.
- **Phase ADRs:**
  - `../ADRs/0001-recipe-engine-literal-extends-with-rag-llm.md` — ADR-P4-001; one of the two allowed Phase-3 edits.
  - `../ADRs/0002-two-tier-writeback-pending-promoted.md` — ADR-P4-002; the other allowed Phase-3 edit.
  - `../ADRs/0003-plan-envelope-kind-and-target-files-allowlist.md` — ADR-P4-003; the `Plan` envelope shape Phase 5 inherits.
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004; the Protocol Phase 5's `MicroVmLeafLlmAgent` will satisfy.
- **Production ADRs:**
  - `docs/production/adrs/0012-microvm-isolation.md` (Phase 5's introduction ADR) — the consumer this test stubs.
  - `docs/production/adrs/0014-retry-with-context.md` — Phase 5's retry loop reads `OutputValidator.errors[].kind`; this story pins the field names.
- **Source design:** `../final-design.md §"Roadmap coherence check" → "What later phases need"` — bullet list of what Phase 5 reads from Phase 4.
- **Existing code:**
  - All Phase-3 integration tests under `tests/integration/` (Phase 3) — re-runs as-is.
  - `src/codegenie/llm/contract.py` (S1-02) — the `LeafLlmAgent` Protocol + `Plan` envelope.
  - `src/codegenie/rag/contract.py` (S1-03) — the `EmbeddingProvider` ABC + `SolvedExample` (re-exported subset).
  - `src/codegenie/rag/models.py` (S1-03) — `SolvedExample v0.4.0` schema (with `engine_trajectory`).
  - `src/codegenie/llm/output_validator.py` (S2-01) — emits structured `errors` with `.kind`.

## Goal

Land two integration tests: `tests/integration/test_phase3_unchanged.py` (G15 regression hard-gate) and `tests/integration/test_phase5_handoff_contract.py` (the consumer-side snapshot of the four contracts Phase 5 inherits).

## Acceptance criteria

- [ ] `tests/integration/test_phase3_unchanged.py` exists and re-runs **every** Phase-3 integration test that lived in `tests/integration/` before Phase 4 began (the test collects them dynamically, not via a maintained list, so future Phase-3 tests are picked up automatically). Output assertions are byte-identical to the pre-Phase-4 baseline captured in `tests/integration/_phase3_baseline.json` (file-level hashes of recorded outputs).
- [ ] The baseline JSON is **committed once** during this story; future Phase-3 additions update the baseline through ADR-gated PRs (the ADR amendment is the workflow, not "engineer adds a row and merges").
- [ ] `tests/integration/test_phase5_handoff_contract.py` exists and demonstrates a Phase-5-shaped consumer can:
  - Import only `codegenie.llm.contract`, `codegenie.rag.contract`, `codegenie.rag.models`, `codegenie.llm.output_validator` — **no other Phase 4 internals**. A fence check inside the test confirms `sys.modules` after import contains none of `codegenie.recipes.engines.rag_llm`, `codegenie.rag.store`, `codegenie.rag.writeback`, `codegenie.planner.*`, `codegenie.llm.leaf_anthropic.*`.
  - Define a stub `MicroVmLeafLlmAgent` class that satisfies the `LeafLlmAgent` Protocol via structural typing; `assert isinstance(stub, LeafLlmAgent)` passes (Protocol with `@runtime_checkable`).
  - Read a `Plan` envelope from a fixture, access `.kind` and `.target_files`, confirm both fields exist with the documented types.
  - Read a `SolvedExample` from a fixture, access `.engine_trajectory` (a list), confirm it preserves engine-order semantics.
  - Read an `OutputValidator.errors[0].kind` string from a fixture rejected response and confirm the canonical error kinds are exposed (`canary_echo_failed`, `fence_residual_detected`, `out_of_scope_action_surface`, `extra_field_forbidden`, `path_traversal`).
- [ ] The handoff test fails loudly with a clear message if any of the contract field names drift (e.g. `engine_trajectory` → `engine_history`).
- [ ] The Phase-3 regression test fails loudly with a per-test diff if the baseline drifts; the failure message names the specific Phase-3 test and the output dimension.
- [ ] **Documentation:** both tests have docstrings stating which goal/ADR they pin and what failure mode they catch (so the next reader doesn't delete them as "redundant").
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on both tests clean.
- [ ] `pytest tests/integration/test_phase3_unchanged.py tests/integration/test_phase5_handoff_contract.py` green.

## Implementation outline

1. Author `tests/integration/test_phase3_unchanged.py`:
   - Use `pathlib.Path("tests/integration").glob("test_phase3_*.py")` (Phase 3 used that prefix) to discover Phase-3 integration tests; if Phase 3 used a different prefix, adapt accordingly (read Phase-3 stories to confirm — Phase 3 manifest lives at `docs/phases/03-recipes-foundation/stories/README.md`).
   - Invoke each discovered test via `pytest.main([...])` in a subprocess (or via the `pytester` fixture) and compare exit codes + stdout-extracted outcome lines against the baseline.
   - Author `tests/integration/_phase3_baseline.json`: list of `{"test_id": "...", "expected_outcome": "passed"}` rows captured during this story's red→green cycle.
2. Author `tests/integration/test_phase5_handoff_contract.py`:
   - At test-module top, do the four allowed imports.
   - Define a tiny `class _StubMicroVmLeafLlmAgent: def invoke(...): ...` matching the Protocol signature (`async def invoke(self, request: LlmRequest) -> LlmResponse` — read the actual signature from S3-02 / S1-02).
   - Build a `Plan` fixture, `SolvedExample` fixture, and `ValidatorOutput` fixture inline (small JSON payloads parsed via the contract Pydantic models).
   - Run the four read patterns; each one is a separate `def test_phase5_can_*` function inside the same file.
3. Author the sys.modules fence check as a separate `def test_phase5_does_not_import_phase4_internals()` so it has a precise failure message.
4. Wire both files into the default `pytest` invocation (no special marks); S7-06 marks them merge-gating.

## TDD plan — red / green / refactor

### Red

`tests/integration/test_phase5_handoff_contract.py`

```python
"""Phase-5 consumer-side snapshot of the contracts Phase 4 hands forward.
A Phase-5-shaped consumer imports ONLY the four allowed contract modules and
exercises the four read patterns Phase 5 needs. Drift in any field name or
type fails this test."""

# the only allowed Phase-4 imports
from codegenie.llm.contract import LeafLlmAgent, LlmRequest, LlmResponse, Plan
from codegenie.rag.contract import EmbeddingProvider
from codegenie.rag.models import SolvedExample
from codegenie.llm.output_validator import ValidatorOutput, ValidatorError


def test_phase5_does_not_import_phase4_internals():
    """The Phase-5 consumer surface must NOT pull in any Phase-4 internal.
    If this test fails, a contract module is re-exporting an internal — fix
    the contract module's __init__, not this test."""
    import sys
    forbidden = {
        "codegenie.recipes.engines.rag_llm",
        "codegenie.rag.store",
        "codegenie.rag.writeback",
        "codegenie.planner.fallback_tier",
        "codegenie.planner.query_key_cache",
        "codegenie.llm.leaf_anthropic",
        "codegenie.llm.leaf_anthropic.client",
        "codegenie.llm.leaf_anthropic.jailed",
    }
    bled = forbidden & set(sys.modules)
    assert not bled, f"Phase-4 internals reachable via contract imports: {bled}"


def test_phase5_can_satisfy_leaf_llm_agent_protocol():
    """Phase 5's MicroVmLeafLlmAgent will satisfy the same Protocol.
    Structurally-typed isinstance must hold for a Phase-5-shaped stub."""
    class _StubMicroVmLeafLlmAgent:
        async def invoke(self, request: LlmRequest) -> LlmResponse:
            raise NotImplementedError

    stub = _StubMicroVmLeafLlmAgent()
    assert isinstance(stub, LeafLlmAgent), \
        "Phase-5 stub does not satisfy the LeafLlmAgent Protocol"


def test_phase5_can_read_plan_kind_and_target_files(plan_fixture):
    """Phase 5's retry-with-context inspects Plan.kind and Plan.target_files.
    Both fields must be present with documented types (str + list[str])."""
    plan: Plan = plan_fixture
    assert plan.kind in {"manual_patch", "recipe_invocation"}, \
        f"unexpected Plan.kind value {plan.kind!r}"
    assert isinstance(plan.target_files, list)
    assert all(isinstance(p, str) for p in plan.target_files)


def test_phase5_can_read_solved_example_engine_trajectory(solved_example_fixture):
    """Phase 15's clustering reads SolvedExample.engine_trajectory; Phase 5's
    retry-with-context reads it to know which engines were already tried.
    Field must exist and be a list of engine-name strings."""
    ex: SolvedExample = solved_example_fixture
    assert hasattr(ex, "engine_trajectory"), \
        "SolvedExample missing engine_trajectory — Phase 15 clustering will break"
    assert isinstance(ex.engine_trajectory, list)
    assert all(isinstance(e, str) for e in ex.engine_trajectory)


def test_phase5_can_read_validator_error_kind(validator_output_fixture):
    """Phase 5's retry-with-context loop branches on errors[0].kind to decide
    whether to retry. Canonical error kinds must remain stable strings."""
    out: ValidatorOutput = validator_output_fixture
    canonical = {
        "canary_echo_failed",
        "fence_residual_detected",
        "out_of_scope_action_surface",
        "extra_field_forbidden",
        "path_traversal",
    }
    assert out.errors[0].kind in canonical, \
        f"unknown error kind {out.errors[0].kind!r}; Phase 5 retry-with-context " \
        f"branches on this — add an ADR amendment before changing"
```

`tests/integration/test_phase3_unchanged.py`

```python
def test_every_phase3_integration_test_still_passes(pytester_or_subprocess):
    """G15: Phase 4 was allowed exactly two ADR-gated edits into Phase 3
    (ADR-P4-001 + ADR-P4-002). Every other Phase-3 integration test must
    pass byte-identically. Drift here is the canary that the Phase-3
    no-edit invariant has been violated."""
    import json
    from pathlib import Path

    baseline = json.loads(Path("tests/integration/_phase3_baseline.json").read_text())
    failures = []
    for entry in baseline:
        outcome = _run_phase3_test(entry["test_id"])
        if outcome != entry["expected_outcome"]:
            failures.append({
                "test_id": entry["test_id"],
                "expected": entry["expected_outcome"],
                "got": outcome,
            })

    assert not failures, f"Phase-3 regression detected: {failures}"
```

### Green

For the Phase-5 handoff test: the existing contract modules from S1-02 / S1-03 / S2-01 already export the right shapes; the test passes immediately if those modules are minimal-and-correct. Land fixture-builder helpers under `tests/integration/conftest.py`.

For the Phase-3 regression test: run every existing Phase-3 integration test against current HEAD, record the outcomes into `_phase3_baseline.json`, commit. The test asserts the runtime matches the baseline.

### Refactor

- Hoist `_run_phase3_test` (subprocess or pytester invocation) into `tests/integration/_phase3_runner.py`.
- Add a docstring on `_phase3_baseline.json`'s parent dir noting that **updating the baseline requires an ADR amendment** (the no-Phase-3-edit invariant is what this gate protects).
- The Phase-5 handoff fixtures live in `tests/fixtures/phase5_handoff/` — `plan.json`, `solved_example.json`, `validator_output.json` — they're tiny and human-readable.
- Type-annotate the stubs. Confirm `LeafLlmAgent` is `@runtime_checkable` in `src/codegenie/llm/contract.py` (S1-02 should have made it so; if not, fix in S1-02, not here — Rule 3).

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase3_unchanged.py` | G15 regression hard-gate. |
| `tests/integration/_phase3_baseline.json` | Per-test expected outcomes (initial snapshot). |
| `tests/integration/_phase3_runner.py` | Subprocess/pytester helper. |
| `tests/integration/test_phase5_handoff_contract.py` | Phase-5 consumer-side snapshot. |
| `tests/integration/conftest.py` | `plan_fixture`, `solved_example_fixture`, `validator_output_fixture`. |
| `tests/fixtures/phase5_handoff/plan.json` | Frozen `Plan` payload. |
| `tests/fixtures/phase5_handoff/solved_example.json` | Frozen `SolvedExample` payload. |
| `tests/fixtures/phase5_handoff/validator_output.json` | Frozen `ValidatorOutput` payload. |

## Out of scope

- **Phase 5's microVM implementation** — Phase 5's job. This story tests the **consumer-side contract**, not the producer.
- **Live Anthropic-call drift detection** — `../final-design.md §"VCR cassette discipline"` nightly canary; not landed in Phase 4.
- **Auto-discovery of Phase-3 tests via test-introspection metadata** — explicit baseline is the safer route; rebuild the baseline through ADR amendments.
- **Mutation testing of the contract surface** — Phase 13 concern.
- **A contract-layer Python package boundary** — the fence-CI rules from S1-07 are the boundary; this story doesn't reinvent them.

## Notes for the implementer

- Per `../High-level-impl.md §"Implementation-level risks"` row 1: the `LeafLlmAgent` Protocol + `Plan` envelope is the most consequential review surface in Phase 4. This test is the consumer-side snapshot. If a future PR finds itself "just adding a field" to `SolvedExample` because Phase 5 wants it — write the ADR amendment first. Phase-2 `detect.type` discipline carries forward.
- The Phase-3 regression baseline is **byte-identical** outcomes, not "all green." A Phase-3 test that previously emitted a warning and now does not is also a regression worth surfacing. Capture the relevant signal (exit code + key stdout lines) in the baseline.
- Per Rule 12 (fail loud): the handoff test must name the **specific** drifted field in the failure message ("`SolvedExample.engine_trajectory` missing" beats "AttributeError"). The downstream reader is a Phase-5 author triaging a merge break.
- The `@runtime_checkable` decorator on `LeafLlmAgent` is what makes the structural `isinstance` check work. If S1-02 didn't add it, the handoff test should fix-forward into S1-02, not paper over with a `hasattr` check.
- The fence-check on `sys.modules` is the most subtle part. Run the test in a fresh interpreter (`pytester` or subprocess) or carefully reset `sys.modules` before checking — otherwise an unrelated test's imports pollute the assertion. Document the chosen approach inside the test.
- Per the "exactly two ADR-gated Phase-3 edits" invariant: if anyone wants to touch Phase 3 again, the ADR row in `../ADRs/README.md` must be amended *first*. This test is the runtime guard for that policy. Document it inline.
- The handoff test's stub does not need to actually function — it satisfies the Protocol's signature, that's all. A real microVM is Phase 5's job; this story owns the contract pin, not the implementation.
- Do not add Hypothesis property-based testing here — the contract surface is a fixed shape, and parametric/structural assertions are the right tool. Property tests live in S7-03 for `Planner.is_total` and `TrustScore.strict_and`.
