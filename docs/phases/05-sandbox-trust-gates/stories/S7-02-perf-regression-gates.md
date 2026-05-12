# Story S7-02 — Performance regression gates (latency + retry-2 budget)

**Step:** Step 7 — Adversarial test suite + performance regression gates
**Status:** Ready
**Effort:** M
**Depends on:** S7-01
**ADRs honored:** ADR-0004 (DiD default macOS), ADR-0011 (no verdict cache in Phase 5)

## Context

Phase 5 commits to two latency invariants: per-gate p50/p95 budgets against the `hello-node` fixture (§Goal 10) and a retry-2 wall-clock ≤ 1.6× retry-1 wall-clock (§Goal 11). This story lands the two pytest files that enforce them, the `.codegenie/perf/` trend store the architecture names, and the warm-pull `pytest-docker` fixture that keeps cold image pulls from polluting the measurements. The tests are marked `slow` and gated on a `[perf]` PR label + weekly cron — they do not gate every PR (Step 7 §Risks).

## References — where to look

- **Architecture:** `../phase-arch-design.md §Performance regression tests` — both test specs in 2 bullets
- **Architecture:** `../phase-arch-design.md §Component 3 DinD performance envelope` — p50 ≤ 90s, p95 ≤ 180s wall (where the budgets come from)
- **Architecture:** `../phase-arch-design.md §Goals` — Goals 10 and 11 verbatim
- **Phase ADRs:** `../ADRs/0011-no-verdict-cache-in-phase-5.md` — the "no cache" stance the retry-2 budget assumes
- **Phase ADRs:** `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — backend choice for the reference perf runner
- **Implementation plan:** `../High-level-impl.md §Step 7` — exact budgets + done criteria
- **Existing code:** `tests/fixtures/repos/hello-node/` — perf measurement baseline
- **Existing code:** `tests/fixtures/repos/breaking-change-cve/` (from Phase 4 / S5-05) — retry-2 fixture
- **Existing code:** `tests/fixtures/vcr/cassette-attempt-1.yaml`, `cassette-attempt-2.yaml` — recorded Phase 4 responses; perf test must replay deterministically
- **Existing code:** `src/codegenie/gates/runner.py` (from S5-02) — the timed unit
- **Existing code:** `src/codegenie/sandbox/did/client.py` (from S3-02) — DinD backend the perf budgets target

## Goal

Land `tests/perf/test_gate_latency.py` and `tests/perf/test_retry_2_budget.py` such that they enforce the §Goal 10 / 11 budgets on the reference DinD runner and write per-run trend data to `.codegenie/perf/`.

## Acceptance criteria

- [ ] `tests/perf/test_gate_latency.py` exists and runs `build`, `test`, and `trace` gates against `hello-node` 5 times each, computes p50 + p95, and asserts: build p50 ≤ 90 s / p95 ≤ 180 s; test p50 ≤ 60 s / p95 ≤ 120 s; trace p50 ≤ 15 s / p95 ≤ 45 s.
- [ ] `tests/perf/test_retry_2_budget.py` exists, runs the `breaking-change-cve` fixture through `GateRunner.run` with the recorded VCR cassettes, measures retry-1 and retry-2 wall-clock separately, and asserts `retry_2_wall / retry_1_wall <= 1.6`.
- [ ] Both files are marked `@pytest.mark.slow` AND `@pytest.mark.perf` so they can be skipped on default PR CI and selected via `pytest -m perf`.
- [ ] A `tests/perf/conftest.py` provides a `warm_pull` autouse session-scoped fixture that issues `docker pull <base-image-digest>` once before any test runs, so the first measured gate is not paying the cold-pull cost.
- [ ] Results are appended (not overwritten) to `.codegenie/perf/latency.jsonl` and `.codegenie/perf/retry_budget.jsonl` as JSONL rows with `{ts, git_sha, runner_name, gate_id, samples, p50, p95}` and `{ts, git_sha, retry_1_wall, retry_2_wall, ratio}` shapes respectively.
- [ ] Flake check: a `tools/perf/loop50.sh` script runs both tests 50 times locally; flake rate (failures / 50) must be `≤ 1%` (≤ 0 failures expected; up to 1 failure tolerated) on the reference runner (Docker Desktop on M-series Mac or 8-core CI Linux).
- [ ] CI workflow `.github/workflows/perf.yml` runs the perf suite on the `[perf]` PR label and on the weekly cron defined for the KVM runner (S6-05 already provisions cron infrastructure).
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. Add a `[tool.pytest.ini_options] markers` entry for `perf` and `slow` in `pyproject.toml`.
2. Write `tests/perf/conftest.py` with the `warm_pull` autouse session-scoped fixture; pull the digest from `tools/digests.yaml`.
3. Write `tests/perf/_latency.py` — a small recorder module exposing `record_sample(path, row)` that appends a JSONL row. Use `time.monotonic()` for measurements; never `time.time()`.
4. Write `tests/perf/test_gate_latency.py`. Use `statistics.median` for p50 and `statistics.quantiles(n=20)[18]` for p95 — explicit and deterministic. Run 5 samples per gate; document why 5 (smallest N that produces a stable p50 within the budget).
5. Write `tests/perf/test_retry_2_budget.py`. Configure the test to replay the recorded VCR cassettes (no live LLM call). Wrap `GateRunner.run` so per-attempt wall-clock is captured; the architecture's §Component 5 already emits per-attempt timing — read from `attempts.jsonl` if simpler than wrapping the runner.
6. Add `.github/workflows/perf.yml` with two triggers — `pull_request.labels: [perf]` and `schedule: cron weekly`.
7. Add `tools/perf/loop50.sh` (bash, ≤ 30 lines) that runs the perf marker 50 times and counts failures; document expected runtime (~2 hours).
8. Confirm the budgets are written as constants at the top of each test file with `# Source: phase-arch-design.md §Goal 10` comments so a future reader knows the budget is contractual, not arbitrary.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/perf/test_gate_latency.py`

```python
import statistics
import time

import pytest

from codegenie.gates.runner import GateRunner
from tests.fixtures.load import load_fixture
from tests.perf._latency import record_sample

# Source: phase-arch-design.md §Goal 10. Do not relax without an ADR amendment.
BUDGETS = {
    "build": {"p50": 90.0, "p95": 180.0},
    "test": {"p50": 60.0, "p95": 120.0},
    "trace": {"p50": 15.0, "p95": 45.0},
}


@pytest.mark.perf
@pytest.mark.slow
@pytest.mark.parametrize("gate_id", ["build", "test", "trace"])
def test_gate_latency_within_budget(tmp_path, gate_id: str) -> None:
    """Phase 5 §Goal 10 — per-gate p50/p95 wall-clock budgets on hello-node.

    Why this matters: the budgets are the operator-facing promise. A regression
    here means a remediation that fits the cost cap today silently misses it
    after a deploy. The test fails loud the moment a change introduces an
    >2× regression on any gate.
    """
    repo = load_fixture("hello-node", into=tmp_path)
    samples: list[float] = []
    runner = GateRunner.from_default_catalog(repo=repo)

    for _ in range(5):
        start = time.monotonic()
        runner.run_single_gate(gate_id=gate_id)
        samples.append(time.monotonic() - start)

    p50 = statistics.median(samples)
    p95 = statistics.quantiles(samples, n=20)[18]
    record_sample(
        ".codegenie/perf/latency.jsonl",
        {"gate_id": gate_id, "samples": samples, "p50": p50, "p95": p95},
    )

    assert p50 <= BUDGETS[gate_id]["p50"], f"{gate_id} p50 {p50:.1f}s > {BUDGETS[gate_id]['p50']}s"
    assert p95 <= BUDGETS[gate_id]["p95"], f"{gate_id} p95 {p95:.1f}s > {BUDGETS[gate_id]['p95']}s"
```

### Green

1. Land `tests/perf/_latency.py` + the autouse warm-pull fixture.
2. Confirm `GateRunner.run_single_gate` exists (helper added in S5-02; if not, add a thin wrapper around `run` that scopes to one gate id).
3. Run the test on the reference runner; tune sample count if the p95 is unstable. Document the tuning in a comment if N changes from 5.
4. Write `test_retry_2_budget.py` and replay VCR cassettes.

### Refactor

- Pull the budget table into a module-level constant; do not inline magic numbers.
- Confirm `record_sample` appends, never overwrites — golden test in `tests/perf/test__latency_recorder.py` (≤ 20 lines) asserts append-only.
- Skip the perf suite on default PR CI via `pyproject.toml [tool.pytest.ini_options] addopts = "-m 'not perf'"`.

## Files to touch

| Path | Why |
|---|---|
| `tests/perf/__init__.py` | Pytest collection |
| `tests/perf/conftest.py` | Warm-pull autouse fixture |
| `tests/perf/_latency.py` | Sample recorder (append-only JSONL) |
| `tests/perf/test_gate_latency.py` | §Goal 10 budgets enforced |
| `tests/perf/test_retry_2_budget.py` | §Goal 11 ratio enforced |
| `tests/perf/test__latency_recorder.py` | Append-only unit test |
| `tools/perf/loop50.sh` | Flake-rate harness |
| `.github/workflows/perf.yml` | `[perf]` label + weekly cron CI |
| `pyproject.toml` | Add `perf`, `slow` markers; default `addopts` skips `perf` |

## Out of scope

- Adding adversarial tests (S7-01).
- Adding cost emission (S7-03).
- Adding any cache or memoization to make budgets easier — ADR-0011 forbids it in Phase 5.
- Cross-runner budget normalization. The budgets are stated against the reference DinD runner; CI runners that differ must run the perf suite on a self-hosted job.

## Notes for the implementer

1. **`time.monotonic()`, not `time.time()`.** A wall-clock jump (NTP slew, DST) can produce negative deltas that silently pass the assertion. The test must be insensitive to system-clock changes.
2. **Five samples is the floor, not the target.** If p95 on the reference runner is unstable at N=5, lift to N=10 and record the change in a code comment with the measured variance.
3. **Warm pull is essential.** Without it, the first `build` gate eats the image-pull cost (~5 s per architecture) and skews p50 above budget. Pull once per session, before any timed code runs.
4. **The retry-2 budget assumes no verdict cache** (ADR-0011). If a future story lands a cache, the retry-2 ratio becomes meaningless and the test must be updated alongside the ADR amendment.
5. **VCR replay must be deterministic.** Confirm `pyvcr` (or whatever Phase 4 uses) is configured with `record_mode='none'` for the perf test; a live LLM call in a perf test is a flake source.
6. **`.codegenie/perf/` is gitignored.** Trend data is per-runner; do not commit. The CI cron job should upload the JSONL to artifact storage for trend analysis — that wiring is out of scope here but flag it for Phase 14 ops.
