# Story S6-03 — TemporalVulnRemediationSut bridge + SutDigest invariance

**Step:** Step 6 — Worker process model + LangGraph↔Temporal bridge
**Status:** Ready
**Effort:** M
**Depends on:** S6-02 (worker bootstrap + capability minting), implicitly S5-02 (`VulnRemediationWorkflow`), S5-01 (checkpointer), Phase-6.5 `VulnRemediationSut` Protocol
**ADRs honored:** ADR-0011 (Postgres checkpointer backend; the SUT must round-trip through it for G5), ADR-0013 (no `TemporalPort` abstraction — single `temporalio.client.Client` use), production ADR-0034 (event-sourcing canonical primitive — terminal `BlobRef`s read back from the canonical log), production ADR-0016 (checkpointer backend — Postgres)

## Context

Phase 6 shipped `VulnRemediationSut(Protocol)` and a `LocalVulnRemediationSut` that runs the LangGraph subgraph in-process against the SQLite checkpointer. Every Phase-6 canonical case under `tests/conformance/vuln/cases/*.json` produces a `SutDigest` (BLAKE3 over the case's terminal state, normalized). The Phase-6.5 harness asserts byte-identical digests across SUTs.

Phase 9 introduces a NEW concrete SUT — `TemporalVulnRemediationSut` — that runs the SAME canonical cases but through the Temporal substrate: starts `VulnRemediationWorkflow`, awaits the result, reads terminal `BlobRef`s, constructs a `VulnRemediationResult`. **G5 (SutDigest invariance) is the exit criterion** for this story: every Phase-6 canonical case must digest byte-identically under `LocalVulnRemediationSut` and `TemporalVulnRemediationSut`. If they diverge, the Temporal wrap is changing observable behavior — and the deterministic-pipeline promise (production ADR-0001 / ADR-0008 "facts, not judgments") is broken.

This is the load-bearing bridge between Phase-6's LangGraph subgraph and Phase-9's Temporal workflow envelope. The bridge has a small public surface (`run_case`, `digest`) but a large semantic claim: the *only* observable difference between Local and Temporal SUTs is the dispatch path, never the result.

The `digest()` method delegates to the Phase-6 builder under `freezegun` — per `phase-arch-design.md §C3 §Internal structure`: "`digest()` delegates to the in-process Phase-6 builder for the case at hand under `freezegun` (the G5 risk #4 fix)." Without `freezegun`, two `datetime.now(UTC)` calls in the digest computation produce different bytes for Local vs Temporal runs (the Temporal run is ~50 ms slower); the test would flake forever.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C3 — LangGraph ↔ Temporal bridge (codegenie.durable.bridge)` — `TemporalVulnRemediationSut(VulnRemediationSut)` signature; `run_case` does (a) write large case inputs to `BlobStore` → `BlobRef`; (b) `temporal_client.start_workflow(VulnRemediationWorkflow, request=..., id=...)`; (c) `await handle.result()`; (d) read terminal `BlobRef`s; (e) construct `VulnRemediationResult`.
  - `../phase-arch-design.md §C3 §Performance envelope` — `+1 gRPC round-trip + 1 workflow-history-append (≈30–50 ms total)`.
  - `../phase-arch-design.md §C3 §Failure behavior` — `ServiceUnavailableError` is test infrastructure, NOT a SUT failure; `SutDigest` divergence → harness-test build break.
  - `../phase-arch-design.md §Goals G5` L20 — "tests/durability/test_sut_digest_invariance.py runs every Phase-6 canonical case through both `LocalVulnRemediationSut` and `TemporalVulnRemediationSut` and asserts byte-equal digests under `freezegun`."
  - `../phase-arch-design.md §Risks` — "Risk #4: SutDigest divergence under timing-sensitive computation"; the `freezegun` mitigation is named here.
- **Phase ADRs:**
  - `../ADRs/0011-checkpointer-backend-postgres.md` — Postgres is the production checkpointer; the SUT must round-trip through `PostgresCheckpointerAdapter` (S5-01).
  - `../ADRs/0013-no-temporal-port-abstraction.md` — direct `temporalio.client.Client`; no Protocol wrapping the Temporal substrate.
- **Existing code:**
  - Phase-6 `VulnRemediationSut(Protocol)` + `LocalVulnRemediationSut` — the contract the new SUT implements.
  - `src/codegenie/events/blob_refs.py` (S3-05) — `write_blob_ref`, `resolve_blob_ref`, `BlobRef` smart constructor.
  - `src/codegenie/durable/workflows/vuln_remediation.py` (S5-02) — `VulnRemediationWorkflow.run(request)` + `state()` query.
  - `tests/conformance/vuln/cases/*.json` (Phase 6) — canonical fixtures.
- **External:**
  - `temporalio.client.Client.start_workflow(VulnRemediationWorkflow.run, request, id=..., task_queue="workflow")`.
  - `temporalio.testing.WorkflowEnvironment.start_local()` for the unit-test SUT (no Postgres needed).
  - `freezegun.freeze_time(...)` for the digest computation.

## Goal

Land `src/codegenie/durable/bridge.py` defining `TemporalVulnRemediationSut(VulnRemediationSut)` with `__init__(*, temporal_client: Client, blob_store: BlobStore, frozen_at: datetime)`, `async def run_case(case: VulnRemediationCase) -> VulnRemediationResult`, and `def digest() -> SutDigest`. Ship `tests/durability/test_sut_digest_invariance.py` (G5 exit-criterion test) that parametrizes over every Phase-6 canonical case, runs each through both `LocalVulnRemediationSut` and `TemporalVulnRemediationSut` under `freezegun.freeze_time(frozen_at)`, and asserts byte-identical `SutDigest`s. The test is the **single deciding piece of evidence** that the Temporal wrap is observably equivalent to the Local implementation.

## Acceptance criteria

### `TemporalVulnRemediationSut` shape

- [ ] **AC-1 — `TemporalVulnRemediationSut` implements the Phase-6 `VulnRemediationSut` Protocol** (load-bearing — without the Protocol relation, Phase-6.5's harness rejects the instance). Class-level type annotations + `cast` if needed to satisfy mypy's structural typing check.
- [ ] **AC-2 — Constructor signature is keyword-only.** `def __init__(self, *, temporal_client: Client, blob_store: BlobStore, frozen_at: datetime) -> None`. `frozen_at` is the `datetime` passed to `freezegun.freeze_time` inside `digest()`; without it the digest of two SUT instances diverges by ~50 ms-of-wall-clock. Naive `datetime` raises `ValueError` (mirror `TransformProvenance.applied_at` convention; tz-aware UTC).
- [ ] **AC-3 — `async def run_case(case: VulnRemediationCase) -> VulnRemediationResult` does exactly the five steps from `phase-arch-design.md §C3`**:
  1. Write any `case.inputs` field >8 KiB (per ADR-0005 threshold) to `BlobStore` via `write_blob_ref`; replace with `BlobRef`.
  2. `handle = await temporal_client.start_workflow(VulnRemediationWorkflow.run, request=WorkflowRequest.from_case(case), id=f"sut-{case.case_id}-{uuid4().hex[:8]}", task_queue="workflow")`.
  3. `terminal = await handle.result()` (this is the blocking await).
  4. For each `BlobRef` in `terminal.outputs`, call `resolve_blob_ref` to materialize bytes.
  5. Construct `VulnRemediationResult(case_id=case.case_id, outputs=<materialized>, ledger=terminal.ledger)`.
- [ ] **AC-3a — Workflow ID convention.** `id = f"sut-{case.case_id}-{run_id_hex}"` where `run_id_hex = uuid4().hex[:8]` so concurrent `run_case` invocations don't collide; the `sut-` prefix marks SUT-launched workflows for observability filters; per `phase-arch-design.md §Edge case #13`, this is the convention to avoid duplicate-`workflow_id` collision.
- [ ] **AC-3b — `temporal_client` is a constructor-injected dependency.** No global / module-level `Client.connect(...)`; the harness fixture builds the client. Per ADR-0013: direct `temporalio.client.Client` — no Protocol wrapping. The test fixture uses `WorkflowEnvironment.start_local()` for unit tests; the integration test in S6-04 uses a real dev cluster.
- [ ] **AC-3c — Bridge is stateless across `run_case` invocations.** Per `phase-arch-design.md §C3 §State`: "Stateless adapter; one instance per harness session." No instance state between calls; concurrent `run_case` calls on the same instance produce correct independent results. Test: launch 3 cases concurrently via `asyncio.gather`; assert each returns its own correct result, no cross-talk.

### `digest()` delegates to Phase-6 builder under `freezegun`

- [ ] **AC-4 — `def digest() -> SutDigest` delegates to the Phase-6 in-process builder under `freezegun.freeze_time(self.frozen_at)`.** The Phase-6 builder reads `datetime.now(UTC)` somewhere in its normalization step; without `freezegun`, the Local-SUT digest (called at time T) and the Temporal-SUT digest (called at T+50 ms) diverge byte-wise. The bridge's `digest` method MUST wrap the builder call in `freezegun.freeze_time(self.frozen_at)`. (This is risk #4's documented mitigation per `phase-arch-design.md §C3 §Internal structure`.)
- [ ] **AC-4a — `digest()` does NOT call `temporal_client`.** Pure delegation to Phase-6 builder; no Temporal round-trip. The digest is over the *Phase-6 canonical case state*, not over Temporal history. Asserted by mocking `temporal_client` to raise on any call during `digest()`.
- [ ] **AC-4b — `digest()` is deterministic across N invocations on the same SUT instance.** Same instance, same `frozen_at`, same canonical case set ⇒ same `SutDigest` across 10 calls. Property test.

### G5 invariance test (the exit criterion)

- [ ] **AC-5 — `tests/durability/test_sut_digest_invariance.py` is the G5 exit-criterion test.** Parametrizes over **every** Phase-6 canonical case file under `tests/conformance/vuln/cases/*.json`. For each case:
  - Construct `local = LocalVulnRemediationSut(frozen_at=FIXED_T)`.
  - Construct `temporal = TemporalVulnRemediationSut(temporal_client=env.client, blob_store=..., frozen_at=FIXED_T)`.
  - With `freezegun.freeze_time(FIXED_T)`: run both `await local.run_case(case)` and `await temporal.run_case(case)`.
  - Assert `local.digest() == temporal.digest()` byte-identically.
  - Assert `local_result.outputs == temporal_result.outputs` byte-identically (sanity check on the materialization path).
- [ ] **AC-5a — `FIXED_T` is module-level `Final` and tz-aware UTC.** `FIXED_T: Final = datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC)`. Time-walking out of band changes the digest; the test fixture pins it.
- [ ] **AC-5b — The test runs in `make test`, NOT behind `@pytest.mark.e2e`.** Per `phase-arch-design.md §Testing strategy §Durability` and S5-05's risk #1 closure: the durability tests are gated to run in CI on every PR. `WorkflowEnvironment.start_local()` boots an in-memory Temporal cluster (no testcontainers needed) so the test stays fast (target: <30 s for the full canonical case set).
- [ ] **AC-5c — On divergence, the test fails LOUD with which case + which field.** Custom assertion helper: when digests diverge, also compute a structural diff of `local_result.outputs` vs `temporal_result.outputs` and surface the first divergent field path. Without this, the contributor sees only "digest mismatch: abc... != def..." with zero forensic value (per the global Rule 12: fail loud).
- [ ] **AC-5d — Test MUST NOT be `@pytest.mark.flaky` / `@pytest.mark.skipif`.** This is the load-bearing G5 evidence. Flake-shielding the G5 test is silently relaxing the exit criterion. The story's Definition of Done explicitly forbids flake markers (mirrors S5-05's risk #1 closure for the Replayer test).
- [ ] **AC-5e — Bridge-only canary: zero LLM tokens in cassette mode.** While running cases through `TemporalVulnRemediationSut`, the test asserts `total_tokens == 0` (G11 — `phase-arch-design.md §Goals G11`). The Temporal wrap must not introduce any LLM call beyond what the Local SUT does.

### Failure-mode handling

- [ ] **AC-6 — `ServiceUnavailableError` from Temporal is a test-infrastructure error.** Per `phase-arch-design.md §C3 §Failure behavior`: "Temporal-cluster unavailable → `ServiceUnavailableError`; harness fixture treats as test infrastructure error (not a SUT failure)." The bridge does NOT catch and convert this to a `VulnRemediationResult.Failed`. The harness fixture catches at the pytest layer and skips with a clear message. Test: monkeypatch `temporal_client.start_workflow` to raise `ServiceUnavailableError`; assert `run_case` propagates the exception un-wrapped.
- [ ] **AC-6a — Workflow result that is itself a typed-failure (`WorkflowFailureError` from inside the workflow body) DOES propagate as `VulnRemediationResult.Failed`.** Distinguish: cluster-side errors (`ServiceUnavailableError`) bubble; workflow-side typed errors (the workflow itself raised) are SUT outputs. Test: workflow that internally raises `RecipeMissedError`; assert `run_case` returns a `VulnRemediationResult` with the typed error embedded, not an exception.
- [ ] **AC-6b — Idempotence on retried `run_case`.** Same `case.case_id` invoked twice ⇒ second invocation re-uses the prior workflow's result (Temporal's workflow-id-reuse policy `WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY`). Per Temporal's at-least-once → exactly-once-at-data-layer pattern. Test: invoke twice; assert second call returns byte-identical result and dispatches zero new activities. (Achieved by setting `id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE` and re-using prior `handle` — implementation chooses; test asserts the behavior, not the mechanism.)

### Performance envelope

- [ ] **AC-7 — `run_case` overhead vs `LocalVulnRemediationSut` is ≤80 ms p95.** Per `phase-arch-design.md §C3 §Performance envelope`: "`+1 gRPC round-trip to Temporal frontend + 1 workflow-history-append (≈30–50 ms total)`. The Phase-6.5 harness runs N cases sequentially; total overhead is N × 50 ms." 80 ms gives 30 ms headroom over 50 ms. Marked `@pytest.mark.bench` (not gating on PR; nightly ratchet baseline per S3-07 / S8-04 pattern). Baseline file: `tests/bench/baselines/phase09_sut_bridge_overhead.json`.

### Wire-up + import discipline

- [ ] **AC-8 — `codegenie.durable.bridge` imports are clean.** `tests/fence/test_bridge_module_purity.py` AST-walks `bridge.py`: imports ⊆ `{__future__, asyncio, datetime, typing, uuid, pydantic, temporalio.client, freezegun, codegenie.events.blob_refs, codegenie.durable.workflows.vuln_remediation, codegenie.conformance.vuln.sut, codegenie.types.identifiers}`. NO imports from `codegenie.durable.workers.*` (the bridge is harness-side, not worker-side); NO imports from `codegenie.plugins.*` (one-way direction).
- [ ] **AC-9 — `tests/conformance/vuln/sut/` exposes `TemporalVulnRemediationSut` as the second SUT alongside `LocalVulnRemediationSut`.** The Phase-6.5 harness picks both up automatically via the SUT registry (Phase-6's existing pattern); this story's wire-up is one additive registration line.

### Gates

- [ ] **AC-10** — `mypy --strict src/codegenie/durable/bridge.py tests/durability/` clean.
- [ ] **AC-11** — `ruff check` + `ruff format --check` clean.
- [ ] **AC-12** — `make lint-imports` green (AC-8 contract).
- [ ] **AC-13** — TDD plan's red test (G5 invariance failing because the bridge doesn't exist) committed before green.

## Implementation outline

1. **`src/codegenie/durable/bridge.py` (NEW)**: `TemporalVulnRemediationSut` class; `__init__` with kw-only args + UTC-tz validator on `frozen_at`; `async def run_case`; `def digest`. Imports limited per AC-8.
2. **`tests/durability/test_sut_digest_invariance.py` (NEW)**: parametrizes over Phase-6 cases; `WorkflowEnvironment.start_local()` fixture; runs both SUTs under `freezegun.freeze_time(FIXED_T)`; asserts byte-identical digests; custom-helper diff on divergence (AC-5c); zero-token assertion (AC-5e).
3. **`tests/unit/durable/test_bridge_run_case.py` (NEW)**: AC-3 (5-step flow), AC-3a (workflow-id convention), AC-3c (statelessness), AC-6 (`ServiceUnavailableError` propagation), AC-6a (typed-failure-as-result), AC-6b (idempotence on retry).
4. **`tests/unit/durable/test_bridge_digest.py` (NEW)**: AC-4 (delegates under freezegun), AC-4a (no Temporal calls), AC-4b (deterministic).
5. **`tests/fence/test_bridge_module_purity.py` (NEW)**: AC-8 import-set check.
6. **`tests/perf/test_phase09_sut_bridge_overhead.py` (NEW, `bench`-marked)**: AC-7; ratchet baseline file.
7. **`tests/conformance/vuln/sut/__init__.py` (EXTEND)**: register `TemporalVulnRemediationSut` alongside `LocalVulnRemediationSut`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/durability/test_sut_digest_invariance.py`

```python
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import freezegun
import pytest
from temporalio.testing import WorkflowEnvironment

from codegenie.conformance.vuln.sut.local import LocalVulnRemediationSut
from codegenie.durable.bridge import TemporalVulnRemediationSut
from codegenie.events.blob_refs import BlobStore
from tests.conformance.fixtures import load_case

FIXED_T: Final = datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC)
CASES = sorted(Path("tests/conformance/vuln/cases").glob("*.json"))


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
async def test_sut_digest_invariance_g5(case_path: Path) -> None:
    case = load_case(case_path)
    async with await WorkflowEnvironment.start_local() as env:
        blob_store = BlobStore.in_memory()
        local = LocalVulnRemediationSut(frozen_at=FIXED_T, blob_store=blob_store)
        temporal = TemporalVulnRemediationSut(
            temporal_client=env.client, blob_store=blob_store, frozen_at=FIXED_T,
        )
        with freezegun.freeze_time(FIXED_T):
            local_result = await local.run_case(case)
            temporal_result = await temporal.run_case(case)
        assert local.digest() == temporal.digest(), _diff(local_result, temporal_result)
        assert local_result.outputs == temporal_result.outputs


def _diff(a, b) -> str:
    """Forensic helper for AC-5c — surfaces first divergent field path."""
    # Implementation pinned to deepdiff or custom recursive walk; emit on assertion failure.
    ...
```

Why it fails: `ModuleNotFoundError: codegenie.durable.bridge`.

### Green — minimal pass
- Land `bridge.py` with `TemporalVulnRemediationSut.__init__`, `run_case`, `digest`.
- Wire the SUT into the Phase-6.5 harness registry.
- Make the G5 test green for *one* canonical case first; then expand.

### Refactor
- Pull the BlobRef materialization helper (`materialize_outputs(terminal: WorkflowResult, blob_store: BlobStore) -> dict[str, bytes]`) into `bridge._materialize.py` so it's unit-testable independent of Temporal.
- Add a structured-log `bridge.run_case.started` (case_id, workflow_id) and `bridge.run_case.completed` (case_id, duration_ms) for harness-side observability.
- Pin the `_diff` helper to `deepdiff.DeepDiff` (already a dev dep) instead of hand-rolling — the helper rotting is worse than the dep.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/bridge.py` | NEW — `TemporalVulnRemediationSut` class. |
| `src/codegenie/durable/_materialize.py` | NEW — BlobRef materialization helper extracted for testability. |
| `tests/durability/test_sut_digest_invariance.py` | NEW — G5 exit-criterion test; parametrized over every Phase-6 case. |
| `tests/unit/durable/test_bridge_run_case.py` | NEW — AC-3 / AC-3a / AC-3c / AC-6 / AC-6a / AC-6b suite. |
| `tests/unit/durable/test_bridge_digest.py` | NEW — AC-4 / AC-4a / AC-4b suite. |
| `tests/fence/test_bridge_module_purity.py` | NEW — AC-8 import-set fence. |
| `tests/perf/test_phase09_sut_bridge_overhead.py` | NEW (`@pytest.mark.bench`) — AC-7. |
| `tests/bench/baselines/phase09_sut_bridge_overhead.json` | NEW — ratchet baseline (initial sample). |
| `tests/conformance/vuln/sut/__init__.py` | EXTEND — register `TemporalVulnRemediationSut`. |

## Out of scope

- **Real Postgres + real Temporal integration test** — S6-04. This story uses `WorkflowEnvironment.start_local()` (in-memory cluster + ephemeral state) for the unit + G5 path; S6-04 boots the real dev cluster.
- **Kill-worker resume durability** — S8-01. G5 (`SutDigest` invariance) is THIS story; G1 (`kill-worker-resume`) is S8-01 and builds on this bridge.
- **`MultiPluginParentWorkflow` bridging.** Phase 9 ships single-workflow SUT only; if portfolio-scale SUTs become a harness need, that's a follow-up story.
- **Cluster-restart durability** — S8-02. Same pattern as S8-01: builds on this bridge.
- **Continue-as-new for cases exceeding `start_to_close_timeout=20m`** — open question #1 in the manifest; surfaces in S4-05; if it bites, lands as a follow-up.

## Notes for the implementer

- **`freezegun.freeze_time(self.frozen_at)` around `digest()` is load-bearing.** The Phase-6 builder's normalization step reads `datetime.now(UTC)` somewhere; without the freeze, Local-SUT digests at `T` and Temporal-SUT digests at `T+50 ms` produce different bytes. AC-4 names this; risk #4 in `phase-arch-design.md §Risks` documents the rationale. If you find yourself "fixing flakes" in the G5 test, the answer is "the freeze isn't covering the digest path", not "loosen the assertion to `~==`".
- **`frozen_at` is constructor-injected, NOT a `digest()` parameter.** Two reasons: (1) the same `frozen_at` must be used across `run_case` and `digest` for the SUT instance, (2) the Phase-6.5 harness builds the SUT once and calls `run_case` N times then `digest` once — the convention is set-at-construction. Tz-aware UTC validator on the field mirrors `TransformProvenance.applied_at` (S1-04 precedent).
- **`run_case` is stateless across invocations.** Per `phase-arch-design.md §C3 §State`: "Stateless adapter; one instance per harness session." Don't accumulate per-call state on `self`; concurrent `run_case` calls must produce independent results. The `BlobStore` IS thread-safe (content-addressed, ON CONFLICT DO NOTHING) so sharing one across calls is fine.
- **Workflow ID convention `f"sut-{case.case_id}-{uuid4().hex[:8]}"` prevents collision.** `case.case_id` is fixed per case; without the `uuid` suffix, running the same case twice (legitimate harness pattern) collides on `workflow_id` (per `phase-arch-design.md §Edge case #13`). The `sut-` prefix lets a harness operator filter SUT-launched workflows from production workflows in `temporal-ui`.
- **`ServiceUnavailableError` is propagated, NOT converted.** Per AC-6: cluster-side errors are test-infrastructure (`pytest.skip` at harness layer); workflow-side typed-failures (`RecipeMissedError`, etc.) are SUT outputs. Mixing the two collapses G5's semantics. The bridge does no error conversion.
- **Idempotence on `case.case_id` retry uses Temporal's `WorkflowIDReusePolicy`, NOT application-level dedupe.** Setting `id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE` and catching `WorkflowAlreadyStartedError` to re-fetch the existing handle is the idiomatic path. Don't add an in-bridge cache; Temporal's data layer IS the cache.
- **Direct `temporalio.client.Client`, no `TemporalPort`.** Per ADR-0013: single substrate in sight ⇒ premature pluggability. The constructor takes a `Client` directly; the test fixture builds it via `WorkflowEnvironment.start_local()`.
- **The G5 test runs in `make test`, NOT `@pytest.mark.e2e`.** Per S5-05's risk #1 closure pattern: durability evidence that can be flake-shielded is silently relaxing the exit criterion. `WorkflowEnvironment.start_local()` is in-memory + fast (target <30 s for the full canonical case set); cost of running is small, cost of moving to e2e gate is "G5 stops being verified on every PR."
- **`SutDigest` divergence MUST surface the first divergent field path** (AC-5c). A "digest mismatch: abc... != def..." failure with no forensic context costs the next debugger 2+ hours. `deepdiff.DeepDiff(local_result.outputs, temporal_result.outputs).to_json()` in the assertion message is the cheap fix.
- **`bridge.py` MUST NOT import `codegenie.durable.workers.*`.** The bridge is *harness-side*; the workers are *runtime-side*. They share the workflow class (the contract) but not the worker plumbing. AC-8's import-set fence enforces this; if you find yourself wanting to import `build_worker` from the bridge, you're conflating "harness starts a workflow" with "worker hosts the workflow" — the harness's `WorkflowEnvironment.start_local()` brings its own worker.
- **Phase-6.5 harness picks up the new SUT via the SUT registry** (Phase-6's existing pattern); the wire-up is one additive line in `tests/conformance/vuln/sut/__init__.py`. Don't edit the Phase-6.5 harness code itself — extension by addition.
- **Zero-token canary in G5 (AC-5e)** doubles as a Phase-9 G11 check (`total_tokens == 0` on cassette-replay). If a contributor accidentally lights up an LLM call inside the workflow body, the cassette will see a recording-miss and `total_tokens > 0`; both G5 (divergence between Local and Temporal — they'd both miss but at different rates) and G11 (token count) catch it.
