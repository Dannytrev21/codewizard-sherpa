# Story S7-02 — Phase 5 sync-vs-Phase 6 cycle `attempts.jsonl` byte-parity test (G4)

**Step:** Step 7 — HITL replay + Phase 5 parity + retry-feedback-distinct-bytes tests (G3 + G4 + G5)
**Status:** Ready
**Effort:** M
**Depends on:** S7-01 (provides the shared mock infrastructure under `tests/integration/mocks.py`, the canonical `initial_ledger.py` fixture, and the `normalize_wallclock_fields` helper in `tests/integration/conftest.py`). Transitively: S4-06 (`validate_in_sandbox` consumes Phase 5's `GateRunner.run_one`), S4-07 (`record_attempt` writes via Phase 5's `RetryLedger.record`), S5-01 (factory), all of Step 1–6.
**ADRs honored:** ADR-0003 (per-gate retry counter — the **canonical canary** for this decision, per ADR-0003 §Consequences "the parity test `tests/integration/test_retry_semantics_parity.py` is the canonical canary for this decision; the day it drifts, one of the two implementations is wrong"), ADR-0004 (retry re-enters `replan_with_phase4` — both Phase 5 and Phase 6 take the same path), ADR-0010 (`run_one` public promotion — both code paths call the same primitive), production ADR-0014 (`max_attempts=3` per-gate). Phase 5's ADR-P5-002 (the `prior_attempts` additive kwarg) is consumed but not amended.

## Context

This test is the byte-parity gate between Phase 5's synchronous `for`-loop retry semantics (the canonical reference implementation, shipped in Phase 5 and gated by `tests/integration/gates/test_stage6_retry_recovers.py`) and Phase 6's LangGraph cycle. ADR-0003 names this test verbatim as the **canonical canary** for the per-gate retry-counter decision: "the day it drifts, one of the two implementations is wrong."

The mechanism is straightforward — the contents are not. Phase 5's `GateRunner.run()` writes `attempts.jsonl` lines via `RetryLedger.record(Attempt(...))`. Phase 6's `record_attempt` node calls the **same** `RetryLedger.record` primitive. If the writes are byte-identical, the per-gate counter, the `prior_attempts` extension, the `failing_signals` serialization, the BLAKE3 chain extension, and the `AttemptSummary` shape are all preserved. If they drift, exactly one is wrong — and the test names which file changed in the diff output.

The challenge is **wall-clock normalization**. Both code paths populate per-attempt `at`, `started_at`, `duration_ms`, `sandbox_run_id` (UUID4), and chain-head `prev_hash` (BLAKE3 of the prior line). The raw bytes will never byte-equal across two runs. The normalization is deliberately *narrow*: only fields the two code paths **cannot** make deterministic without losing information get zeroed. The fields that **must** be byte-identical (the structural ones — `attempt_id`, `failing_signals`, `prior_failure_summary`, `retryable`, `gate_id`, `engine_used`, `patch_blake3`) are compared raw.

The test runs the same scripted `GateOutcome` sequence through both code paths in the same `tmp_path` session. The Phase 5 path drives `GateRunner.run()` directly (no LangGraph). The Phase 6 path drives `build_vuln_loop().ainvoke()` with the same mocked engines and the same initial `VulnLedger`. Both write to **separate** `<run-dir>/gates/stage6_validate/attempts.jsonl` files. The test reads both, normalizes the wall-clock fields per the documented rules, and asserts `lhs_bytes == rhs_bytes`.

The fixture is the same `cve-fixture` used by Phase 5's `test_stage6_retry_recovers.py`. The `GateOutcome` sequence is `[fail, fail, pass]` so both code paths produce a 3-line `attempts.jsonl` — the smallest non-trivial parity surface. (A 1-line file would pass parity by accident; a 2-line file wouldn't exercise the `prior_attempts` propagation across the second retry.)

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals#4 (G4)` — "Per-gate retry counter honors ADR-0014: `retry_count` resets to 0 on every entry to a *new* `current_gate_id`. The Phase 5 sync `for`-loop ledger and Phase 6's LangGraph cycle produce **byte-identical** `attempts.jsonl`."
  - `../phase-arch-design.md §"Testing strategy" → Layer 5 (Phase 5 parity)` — ~60 s CI budget.
  - `../phase-arch-design.md §Component 4 "@pure_edge — route_after_attempt"` — the retry routing predicate both paths exercise identically.
- **Phase ADRs:**
  - `../ADRs/0003-per-gate-retry-counter-scope.md` — names this test as the canonical canary.
  - `../ADRs/0004-retry-re-enters-phase4-fallback-tier.md` — the retry edge target both paths share.
  - `../ADRs/0010-phase5-runner-run-one-public-promotion.md` — both code paths consume the same `run_one` primitive (S4-10).
- **Source design:** `../final-design.md §Synthesis ledger row 2 "Retry-counter scope"`; `../final-design.md §Goals#4`.
- **High-level-impl:** `../High-level-impl.md §Step 7` — "Phase 5's sync `GateRunner.run()` byte format may differ from Phase 6's cycle in event ordering (e.g., `at` timestamps); the parity test must normalize wall-clock fields before byte-diff. Document the normalization rules in `tests/integration/conftest.py`."
- **Prior phases:**
  - `../../05-sandbox-trust-gates/final-design.md §"Retry feedback semantics"` — the `AttemptSummary` shape.
  - `../../05-sandbox-trust-gates/final-design.md §"Internal design" of RetryLedger` (line 346) — `.codegenie/remediation/<run-id>/gates/<gate_id>/attempts.jsonl` path; first line's `prev_hash` is the Phase 4 chain head.
  - `tests/integration/gates/test_stage6_retry_recovers.py` (Phase 5) — the sync-side reference; this test invokes the same `GateRunner.run()` entrypoint.

## Goal

Land `tests/integration/test_retry_semantics_parity.py` that runs an identical `GateOutcome` sequence (`[fail("tests"), fail("build"), pass]`) through both Phase 5's synchronous `GateRunner.run()` and Phase 6's compiled LangGraph cycle, reads the two `attempts.jsonl` files written under separate `tmp_path` run directories, applies the documented wall-clock normalization, and asserts the two byte streams are equal. The test is the canonical canary ADR-0003 names; any drift fires this gate before drift reaches production.

## Acceptance criteria

- [ ] `tests/integration/test_retry_semantics_parity.py` exists, is `@pytest.mark.integration` + `@pytest.mark.slow` (Layer 5 budget), and is green on `main`.
- [ ] **The fixture is the same `cve-fixture`** used by Phase 5's `test_stage6_retry_recovers.py` (`tests/fixtures/repos/cve-fixture/` if shipped, else the `breaking-change-cve` fixture per Phase 5 final-design line 511). If both code paths consume the same fixture, the parity gate is meaningful; if they consume different fixtures, the gate is theatre.
- [ ] **The `GateOutcome` sequence is exactly `[fail, fail, pass]`** with three distinct attempts: attempt-1 fails with `failing_signals=["tests"]`, attempt-2 fails with `failing_signals=["build"]` (distinct signals so same-signature flake doesn't fire), attempt-3 passes with `failing_signals=[]`. The 3-line `attempts.jsonl` is the smallest non-trivial parity surface and exercises the `prior_attempts` propagation on both code paths.
- [ ] **Phase 5 side: invoke `GateRunner.run()` directly.** Construct a `GateRunner(sandbox_client=MockSandboxClient(scripted=[outcome1, outcome2, outcome3]), retry_ledger=RetryLedger(run_dir=phase5_run_dir))` and call `runner.run(transition, ctx)`. The Phase 5 path writes `<phase5_run_dir>/gates/stage6_validate/attempts.jsonl`.
- [ ] **Phase 6 side: invoke `build_vuln_loop().ainvoke()`.** Construct an `AuditedSqliteSaver(tmp_path / "wf.sqlite3")`, build the graph with `max_attempts=3`, force_rebuild=True. The Phase 6 nodes (specifically `validate_in_sandbox` + `record_attempt`) consume the same `MockGateRunner` (or its `run_one` accessor) and the same `RetryLedger` (against `phase6_run_dir`). Invoke `await graph.ainvoke(initial, config)`. The Phase 6 path writes `<phase6_run_dir>/gates/stage6_validate/attempts.jsonl`.
- [ ] **Wall-clock normalization is documented in `tests/integration/conftest.py`.** The `normalize_attempts_jsonl(path: Path) -> bytes` helper (extending the `normalize_wallclock_fields` primitive S7-01 introduced):
  - Parses each line as JSON.
  - **Zeros**: `at` → `"1970-01-01T00:00:00+00:00"`, `started_at` → same, `duration_ms` → `0`.
  - **Replaces with sentinel**: `sandbox_run_id` → `"00000000-0000-0000-0000-000000000000"`, `attempt_id` (if it embeds a UUID) → stable index `1`/`2`/`3`.
  - **Recomputes `prev_hash`**: after normalizing every other field, recompute the BLAKE3 chain over the normalized lines (the chain links bytes; if the bytes change, the chain breaks). The normalization helper recomputes `prev_hash` line-by-line using the normalized predecessor. The recomputation is deterministic given the same `_PHASE5_CHAIN_SEED` (or `prev_chain_head` from the Phase 4 head — the test sets this to a fixed sentinel for both code paths).
  - **Leaves untouched**: `attempt_id`'s numeric index, `failing_signals`, `prior_failure_summary`, `retryable`, `gate_id`, `engine_used`, `patch_blake3`, `evidence_paths` (relativized to the run dir), `outcome` discriminator. These are the structural fields whose drift means one of the two implementations is wrong.
- [ ] **The byte-diff assertion is on the normalized bytes.** `assert phase5_bytes == phase6_bytes` (after `normalize_attempts_jsonl(...)` on both). The failure mode on mismatch prints `difflib.unified_diff` with file labels `"phase5/attempts.jsonl"` and `"phase6/attempts.jsonl"` so the on-call sees the field that drifted.
- [ ] **Both `attempts.jsonl` files have exactly 3 lines.** A 1- or 2-line file means one of the two code paths short-circuited the retry loop (and ADR-0003 / ADR-0014 are broken on that side). Assert line count first; a clear `assert len(phase5_lines) == 3 == len(phase6_lines)` fails before the byte-diff so the failure message is informative.
- [ ] **`patch_blake3` distinct across attempts.** Each of the 3 attempts has a distinct `patch_blake3` value — both code paths exercise `replan_with_phase4` on attempt 2 and 3 (per Phase 5 exit #19). The test asserts `len({line["patch_blake3"] for line in phase5_lines}) == 3` and same for Phase 6.
- [ ] **`prior_failure_summary` propagation.** Attempt-2's `prior_failure_summary` is non-empty (Phase 5's fence-wrapped summary of attempt-1's failure); attempt-3's `prior_failure_summary` references attempt-2. Both code paths produce the same fence-wrapped summary bytes. (If `FenceWrapper` ever introduces non-determinism — e.g., a random salt — this test catches it.)
- [ ] **Chain-head propagation.** The first line of both `attempts.jsonl` files has the same `prev_hash` (the Phase 4 chain head sentinel the test injects). The chain validates end-to-end on both files. (The normalization recomputes the chain, so this is a precondition check before normalization.)
- [ ] **Mock identity discipline.** The `MockGateRunner` is **the same instance** consumed by both code paths within a single test run — the scripted `[outcome1, outcome2, outcome3]` is consumed in order by Phase 5's `run()` then re-loaded with a fresh copy for Phase 6's `ainvoke()`. The test does not allow the two paths to silently see different outcomes.
- [ ] **`max_attempts=3` only.** This test does not parametrize `max_attempts` — the parity check is about *what gets written when both paths run to completion*. The `max_attempts=2` and `max_attempts=1` cases are exercised by S7-01 for HITL; the parity gate is the production-default path.
- [ ] **Performance budget.** ≤ 60 s on CI (Layer 5 budget per arch §Testing strategy). The mocked sandbox boot is `~0 s`; the budget headroom covers the `RetryLedger.record` + audit chain writes × 6 (3 per side).
- [ ] **`mypy --strict tests/integration/test_retry_semantics_parity.py tests/integration/conftest.py`** passes. `ruff check` + `ruff format --check` pass.
- [ ] **Test docstring** names: (a) this is the canonical canary per ADR-0003 §Consequences, (b) which fields are normalized vs which are byte-compared, (c) the rationale for the `[fail, fail, pass]` sequence (minimal non-trivial parity surface), (d) the amendment procedure ("if a future Phase 5 change deliberately alters `attempts.jsonl` format, amend ADR-P5-X and update this test's normalization helper in the same PR").

## Implementation outline

1. **Extend `tests/integration/conftest.py`** with `normalize_attempts_jsonl(path: Path) -> bytes`. Composition with `normalize_wallclock_fields` from S7-01.
2. **Build `MockSandboxClient` / `MockGateRunner`** if S7-01's `MockGateRunner` isn't a drop-in fit. The shared `tests/integration/mocks.py` should already expose a `scripted_outcomes_iter(outcomes: list[GateOutcome])` helper; the test consumes it.
3. **Phase 5 invocation.** Build a `GateRunner` directly. The Phase 5 `GateContext` may need to be constructed with a sentinel `prev_chain_head` (a fixed BLAKE3 hex) to anchor the chain. If Phase 5's `GateRunner.__init__` doesn't accept an injected chain head, this story surfaces a Gap-2-style follow-up — but ADR-0003 §Consequences makes the test mandatory, so the right escalation is a Phase 5 ADR amendment to expose the seam, not skipping the test.
4. **Phase 6 invocation.** Build the graph with the same `MockGateRunner.run_one` patched into `validate_in_sandbox` via `monkeypatch.setattr`. The Phase 4 mock returns deterministic `RecipeApplication` bytes derived from the attempt index so `patch_blake3` is distinct but reproducible.
5. **Normalize + diff.** Read both files; pass through `normalize_attempts_jsonl`; assert equality; on mismatch, print `difflib.unified_diff` and fail with a message naming ADR-0003 as the canary.

## TDD plan — red / green / refactor

### Red

Path: `tests/integration/test_retry_semantics_parity.py`

```python
"""ADR-0003 canonical canary: Phase 5's sync GateRunner.run() and Phase 6's LangGraph
cycle write byte-identical attempts.jsonl files when run against the same scripted
[fail, fail, pass] GateOutcome sequence.

Normalization (documented in tests/integration/conftest.py):
- Zeroed: at, started_at, duration_ms.
- Sentinel: sandbox_run_id, attempt_id-embedded UUIDs.
- Recomputed: prev_hash (BLAKE3 chain over normalized lines).
- BYTE-COMPARED (must match): attempt_id index, failing_signals, prior_failure_summary,
  retryable, gate_id, engine_used, patch_blake3, evidence_paths (relativized), outcome.

If this test red-fails, exactly one of (Phase 5 GateRunner.run, Phase 6 record_attempt)
is wrong. The diff names the field; the on-call's job is to figure out which side moved
and revert / amend an ADR.

Amendment procedure: if a Phase 5 change deliberately alters attempts.jsonl format,
amend ADR-P5-X and update normalize_attempts_jsonl + this test in the same PR.
"""

import difflib
import pytest
from pathlib import Path
from blake3 import blake3
from codegenie.graph import build_vuln_loop, AuditedSqliteSaver
from codegenie.gates.runner import GateRunner
from codegenie.gates.ledger import RetryLedger
from tests.integration.conftest import normalize_attempts_jsonl
from tests.integration.mocks import scripted_outcomes_iter, MockSandboxClient

_PHASE4_CHAIN_HEAD_SENTINEL = "0" * 64

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.timeout(60)
async def test_attempts_jsonl_byte_parity_between_phase5_and_phase6(tmp_path) -> None:
    outcomes = [
        GateOutcome(passed=False, retryable=True, failing_signals=["tests"], ...),
        GateOutcome(passed=False, retryable=True, failing_signals=["build"], ...),
        GateOutcome(passed=True, retryable=True, failing_signals=[], ...),
    ]

    # Phase 5 side
    phase5_run_dir = tmp_path / "phase5"
    phase5_runner = GateRunner(
        sandbox_client=MockSandboxClient(scripted_outcomes_iter(outcomes)),
        retry_ledger=RetryLedger(run_dir=phase5_run_dir, prev_chain_head=_PHASE4_CHAIN_HEAD_SENTINEL),
        max_attempts=3,
    )
    phase5_result = phase5_runner.run(transition="stage6_validate", ctx=...)
    phase5_jsonl = phase5_run_dir / "gates" / "stage6_validate" / "attempts.jsonl"

    # Phase 6 side
    phase6_run_dir = tmp_path / "phase6"
    # ... build_vuln_loop + monkeypatch run_one + ainvoke
    phase6_jsonl = phase6_run_dir / "gates" / "stage6_validate" / "attempts.jsonl"

    # Precondition: 3 lines each
    p5_lines = phase5_jsonl.read_text().splitlines()
    p6_lines = phase6_jsonl.read_text().splitlines()
    assert len(p5_lines) == 3 == len(p6_lines), f"Expected 3 attempts; got phase5={len(p5_lines)} phase6={len(p6_lines)}"

    # Normalize + byte-diff
    p5_bytes = normalize_attempts_jsonl(phase5_jsonl)
    p6_bytes = normalize_attempts_jsonl(phase6_jsonl)
    if p5_bytes != p6_bytes:
        diff = "\n".join(difflib.unified_diff(
            p5_bytes.decode().splitlines(),
            p6_bytes.decode().splitlines(),
            fromfile="phase5/attempts.jsonl",
            tofile="phase6/attempts.jsonl",
            lineterm="",
        ))
        pytest.fail(f"ADR-0003 canonical canary FAILED — attempts.jsonl drift:\n{diff}")

@pytest.mark.integration
async def test_patch_blake3_distinct_across_three_attempts(tmp_path) -> None:
    # Both code paths produce 3 distinct patch_blake3 (Phase 5 exit-criterion #19).
    ...

@pytest.mark.integration
async def test_prior_failure_summary_propagates_to_attempt_2_and_3(tmp_path) -> None:
    ...
```

Run; commit red.

### Green

- The most likely first red signal is **field naming drift** — Phase 6's `record_attempt` may write `"signals"` while Phase 5 writes `"failing_signals"` (or some equivalent). The fix is in Phase 6's node, not the test. ADR-0003 is the authority.
- The second-most-likely is **chain-head injection** — Phase 5's `RetryLedger` may not accept a `prev_chain_head` kwarg directly; the test may need to write a sentinel Phase 4 audit entry before invoking Phase 5. Either approach is fine; document the choice in the conftest.

### Refactor

- **`normalize_attempts_jsonl` lives in conftest** because S7-01 already established the pattern. Keep one source of truth; do not duplicate normalization logic into the test file.
- **Do not parametrize this test on `max_attempts`.** Parity is a production-default-path gate; the `max_attempts={1,2}` variants don't exercise full retry feedback.
- **Do not over-normalize.** The fields the design says **must** byte-equal across the two paths are listed explicitly. If a test reviewer asks "should we also normalize `engine_used`?" the answer is no — `engine_used` is the structural field whose drift is the canary firing.
- **Print `unified_diff` on failure** so the operator immediately sees which line / field drifted.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_retry_semantics_parity.py` | New — the ADR-0003 canonical canary. |
| `tests/integration/conftest.py` | Extend — add `normalize_attempts_jsonl` building on `normalize_wallclock_fields` from S7-01. |
| `tests/integration/mocks.py` | Extend — `MockSandboxClient` if not yet present; ensure `scripted_outcomes_iter` is exposed. |

## Out of scope

- **Retry-feedback distinct patch bytes** — S7-03 ships the dedicated test; the parity test asserts distinct-`patch_blake3` as a precondition but does not verify Phase 4 prompt content.
- **HITL interrupt path** — S7-01. This test runs to completion (3 attempts, pass on 3); no `interrupt()` fires.
- **Phase 4 prompt fence-wrapping content verification** — S7-03's responsibility.
- **`max_attempts` parametrization** — production default only; HITL parametrization is S7-01.
- **Replay-after-kill** — Step 8.
- **Adversarial corruption of `attempts.jsonl`** — Phase 5's `tests/adversarial/test_audit_chain_tamper.py` already covers tamper detection.

## Notes for the implementer

- **The canary is binary.** If `attempts.jsonl` drifts in any structural field, the test red-fails. That's the design. Do not introduce "tolerant" comparators — the byte-diff is the discipline.
- **Wall-clock normalization is narrow on purpose.** Five fields zeroed/sentineled (`at`, `started_at`, `duration_ms`, `sandbox_run_id`, embedded UUIDs); one field recomputed (`prev_hash`). Anything else changing is a real drift.
- **`prev_hash` recomputation is the subtle part.** After normalizing fields, recompute the BLAKE3 chain over the normalized line bytes. The first line's `prev_hash` is the Phase 4 chain head sentinel both code paths inject. The second line's `prev_hash` is `blake3(normalized_line_1).hexdigest()`. The third is `blake3(normalized_line_2).hexdigest()`. If both code paths produce the same normalized line bytes, the recomputed chains agree by construction — the chain becomes a *consequence* of parity, not a confounder.
- **Why `[fail, fail, pass]` and not `[fail, fail, fail]`.** The all-fail sequence exits via `route_after_attempt → "retry_exhausted" → await_human` which trips `interrupt()` — that path is S7-01. The pass-on-3 sequence runs the cycle to completion and produces a 3-line `attempts.jsonl` with all three attempts written, which is what the parity gate exists to compare. Both code paths must take exactly the same `[recipe → rag → replan → apply → validate → record]` × 3 path.
- **Why distinct `failing_signals` per attempt.** Same reason as S7-01: avoid same-signature flake detection. The third attempt passes, so the flake detector is irrelevant on attempt 3, but the second attempt would route to `non_retryable` if `failing_signals` matched attempt 1. Different signals → different `prior_failure_summary` → no flake.
- **Phase 5's `_PHASE5_CHAIN_SEED` may already define a test sentinel.** If so, reuse it for both code paths so the test is consistent with Phase 5's existing test conventions. Read `tests/integration/gates/conftest.py` (Phase 5) first; do not duplicate seed values.
- **If `GateRunner` doesn't expose a clean seam for injecting a `prev_chain_head`,** this surfaces Gap 2 (Phase 5 `head_from_phase5` accessor missing). The right escalation is the same as S2-02's: either land a one-line public accessor on Phase 5 + a regression test, or parse the audit JSONL directly + ship a Phase-6 ADR. Do **not** skip the parity gate; ADR-0003 names it as load-bearing.
- **The test is `@pytest.mark.slow`** because the 60 s budget is generous to absorb CI variance; in practice it should run in ~5 s with mocked engines. The marker is a defensive hint to the merge queue, not a statement about typical wall-clock.
- **Difflib output is the failure-mode value-add.** A bare `assert lhs == rhs` would print 4 KB of diff with no structure. `difflib.unified_diff` gives an operator-friendly 6-line context per drift. Worth the four extra lines of test code.
- **If a future ADR-P5-X amendment changes `attempts.jsonl` format,** the amendment lands on the Phase 5 side; Phase 6 inherits via `RetryLedger.record`; this test stays green because both paths use the same primitive. If the amendment changes a *node-side* serialization (e.g., a Phase 6 wrapper that adds a field before calling `record`), this test surfaces it as drift — which is correct: Phase 6 is forbidden from adding to the on-disk format unilaterally.
- **Regression risk: high if the test is skipped or weakened.** A passing parity test is the cheapest reassurance that Phase 5's existing test suite still constrains Phase 6. A skipped or `@pytest.mark.xfail` parity test is silent permission to drift.
