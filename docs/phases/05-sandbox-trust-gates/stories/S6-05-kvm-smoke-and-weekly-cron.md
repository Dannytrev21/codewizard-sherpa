# Story S6-05 — KVM-gated CI smoke test + weekly cron

**Step:** Step 6 — FirecrackerClient backend + KVM-gated CI smoke test
**Status:** Ready
**Effort:** M
**Depends on:** S6-02, S6-03
**ADRs honored:** ADR-0004, ADR-0009, ADR-0001

## Context

Phase 5 explicitly commits to "real Firecracker, not stub" with one KVM-gated CI smoke test plus a weekly cron — both gate-keeping evidence for ADR-0019 (sandbox stack resolution) and a tripwire that catches rootfs/kernel/digest drift before it bites an operator. With the client (S6-01), network policy (S6-02), and digest-pinned artifacts (S6-03) in place, this story lands the two KVM-only integration tests, wires a self-hosted KVM runner job in CI, and stands up the weekly cron with on-call paging on failure. This is also where Open Q6 (KVM runner ownership) becomes a hard blocker rather than a planning footnote.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — FirecrackerClient` — performance envelope (`npm ci && npm test` in ≤ 300 s on hello-node).
  - `../phase-arch-design.md §Physical view` — "Linux CI self-hosted KVM runner" subgraph and the `firecracker bin → KVM → microVM` boot chain.
  - `../phase-arch-design.md §Testing strategy` — `pytest.mark.skip_if_no_kvm` predicate; the integration band is ~25% of tests and uses `pytest-docker` for DinD, KVM-gating for Firecracker.
  - `../phase-arch-design.md §Risks risk-2` — "Self-hosted KVM CI runner not provisioned" mitigation: split into 6a (code + local) and 6b (cron); 6b is required for §Goal 6.
  - `../phase-arch-design.md §Goal 6` — verbatim: real Firecracker, microVM class, KVM smoke + weekly cron.
  - `../phase-arch-design.md §Open Q6` — weekly cron infrastructure ownership; flagged as blocker if not delivered.
- **Phase ADRs:**
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — "`tests/integration/sandbox/test_firecracker_smoke.py` is `pytest.mark.skip_if_no_kvm`; weekly cron job exercises it on the self-hosted runner."
  - `../ADRs/0009-firecracker-network-policy-host-side-nftables.md` — `test_firecracker_network_policy.py` boots a microVM with `network=scoped` to `registry.npmjs.org`, asserts `npm ci` succeeds and `curl github.com` fails.
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `GateRunner` is the only consumer of `SandboxClient`; the smoke test exercises a real gate, not a raw `client.execute`.
- **Production ADRs:**
  - `../../../production/adrs/0019-sandbox-stack.md` — this is the test that generates evidence for the eventual stack resolution.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Real Firecracker (not stub)"` — KVM smoke + weekly cron is the originating commitment.
- **Existing code:**
  - `src/codegenie/sandbox/firecracker/client.py` (from S6-01) — the client under test.
  - `src/codegenie/sandbox/firecracker/network_policy.py` (from S6-02) — `apply_policy` exercised by the network-policy smoke test.
  - `tests/fixtures/repos/hello-node/` (Phase 3/4 carry-forward) — the fixture both tests run against.
  - `src/codegenie/gates/runner.py` (from S5-02) — used to exercise the smoke test through a real `GateRunner.run` (not a raw `client.execute`).
  - `tests/integration/sandbox/test_firecracker_network_policy.py` (placeholder from S6-02) — populated here.
- **External docs:**
  - GitHub Actions self-hosted runners: <https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners> — `runs-on: [self-hosted, kvm]` label semantics.
  - Workflow `schedule` syntax + on-call paging via PagerDuty action: <https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule>.

## Goal

Land the two KVM-gated integration tests (`test_firecracker_smoke.py`, `test_firecracker_network_policy.py`), the self-hosted KVM runner workflow that runs them on every PR, and the weekly cron that re-runs them + pages the on-call owner on failure.

## Acceptance criteria

- [ ] `tests/integration/sandbox/test_firecracker_smoke.py` exists and is decorated `pytest.mark.skip_if_no_kvm` at module scope; it (a) constructs a `FirecrackerClient` via `from_digests_yaml()`, (b) drives a real `GateRunner.run` against `tests/fixtures/repos/hello-node/`, (c) asserts the run completes within 300 s wall-clock, (d) asserts `attempts.jsonl` line shows `gate_isolation_class == "microvm"` and `backend == "firecracker"`, (e) asserts `npm ci && npm test` exit code 0.
- [ ] `tests/integration/sandbox/test_firecracker_network_policy.py` exists, is `skip_if_no_kvm`, and asserts: (a) with `network="scoped"` and `egress_allowlist=["registry.npmjs.org"]`, `npm ci` inside the guest succeeds; (b) `curl https://github.com` from inside the same guest fails (exit non-zero, no body returned); (c) the host's `nft list ruleset` is empty (no leaked rules) after the test tears down.
- [ ] `pytest.mark.skip_if_no_kvm` is registered once in `tests/conftest.py` (or `tests/integration/sandbox/conftest.py`) with the predicate `os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)`; both smoke tests use the same marker.
- [ ] A new GitHub Actions workflow `.github/workflows/firecracker-smoke.yml` runs the two tests on `runs-on: [self-hosted, kvm]`, triggered by (a) `pull_request` paths-filter on `src/codegenie/sandbox/firecracker/**`, `tools/firecracker/**`, `tools/digests.yaml`; (b) `workflow_dispatch`; (c) `schedule: cron: "0 7 * * 1"` (Mondays 07:00 UTC — weekly cron).
- [ ] On `schedule` event with a failing test outcome, the workflow invokes a PagerDuty incident-create step (or the org's equivalent action — capture the exact action name in the workflow `uses:` line and as a top-line comment) with severity `error`, summary `"codegenie firecracker weekly smoke failed"`, and a link to the failed run.
- [ ] The workflow caches *nothing* across runs (intentional — the test exercises cold-start; cache would defeat the latency assertion).
- [ ] The workflow's setup step calls `codegenie sandbox prepare --backend firecracker --check` (S6-03) before running pytest; if `--check` fails, the workflow fails fast with the digest-mismatch error surfaced to the run log.
- [ ] Both tests record per-attempt wall-clock and exit code into `.codegenie/perf/firecracker_smoke.jsonl` (consumed by S7-02 perf regression gates); the JSONL line schema is `{run_id, backend, wall_seconds, exit_code, run_ts}`.
- [ ] `codegenie sandbox health` (S8-01 will fully wire) is invoked as a post-test step on failure to capture diagnostic state; output uploaded as a workflow artifact named `sandbox-health-<run-id>.json`.
- [ ] A README block under `.github/workflows/firecracker-smoke.yml.README.md` (or top-of-workflow comment) documents the runner-label requirement, the PagerDuty service routing, and the rotation owner — Open Q6 is closed here.
- [ ] If the self-hosted KVM runner is unavailable (no machines labeled `kvm` online), the workflow stays *queued* (does not fall back); a separate alert fires after a 24h queue threshold via PagerDuty's queue-monitor mechanism (configuration captured in workflow comments).
- [ ] The two smoke tests *also* pass when run locally on a contributor's KVM-capable Linux box (`pytest tests/integration/sandbox/test_firecracker_smoke.py`); no CI-only assumptions in the test bodies.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on touched modules, `pytest tests/integration/sandbox/test_firecracker_smoke.py tests/integration/sandbox/test_firecracker_network_policy.py` (with `--runxfail`) all pass on the KVM runner.

## Implementation outline

1. Register the marker in `tests/conftest.py`:
   ```python
   def pytest_configure(config):
       config.addinivalue_line(
           "markers",
           "skip_if_no_kvm: skip unless /dev/kvm is readable+writable")

   def pytest_collection_modifyitems(config, items):
       has_kvm = (os.path.exists("/dev/kvm")
                  and os.access("/dev/kvm", os.R_OK | os.W_OK))
       if has_kvm:
           return
       skip_marker = pytest.mark.skip(reason="No /dev/kvm — KVM-gated test")
       for item in items:
           if "skip_if_no_kvm" in item.keywords:
               item.add_marker(skip_marker)
   ```
2. Write `tests/integration/sandbox/test_firecracker_smoke.py`:
   - Build `SandboxClient` via `FirecrackerClient.from_digests_yaml()` (S6-03).
   - Build a minimal `StrictAndGate` against `gates/catalog/stage6_validate.yaml` (S3-05) — or, if that is too coupled, exercise `client.execute(spec)` directly with a spec mirroring stage6.
   - Use `tests/fixtures/repos/hello-node/` as the workdir; copy-in produces the npm project.
   - Time the run via `time.monotonic()`; assert ≤ 300 s.
   - Assert `attempts.jsonl` parses, last attempt has `gate_isolation_class == "microvm"` and `backend == "firecracker"`.
   - Write the perf JSONL line on success and failure (use a `try/finally`).
3. Write `tests/integration/sandbox/test_firecracker_network_policy.py`:
   - Spec with `network="scoped"`, `egress_allowlist=["registry.npmjs.org"]`.
   - Test 1: cmd `npm ci` against hello-node copy-in → exit 0.
   - Test 2: cmd `curl -sf https://github.com -o /dev/null` → exit non-zero.
   - Post-test: `subprocess.check_output(["nft","list","ruleset"])` returns empty (or no `cgsbx-*` table) — the chokepoint here is the test, not runtime code; allow it in this *test* file via the same exemption pattern used in S3-03 tests.
4. Add `.github/workflows/firecracker-smoke.yml`:
   ```yaml
   name: firecracker-smoke
   on:
     pull_request:
       paths:
         - "src/codegenie/sandbox/firecracker/**"
         - "tools/firecracker/**"
         - "tools/digests.yaml"
     workflow_dispatch:
     schedule:
       - cron: "0 7 * * 1"   # Mondays 07:00 UTC — weekly cron
   jobs:
     smoke:
       runs-on: [self-hosted, kvm]
       timeout-minutes: 20
       steps:
         - uses: actions/checkout@v4
         - name: prepare firecracker artifacts (digest check)
           run: codegenie sandbox prepare --backend firecracker --check
         - name: run KVM-gated tests
           run: |
             pytest tests/integration/sandbox/test_firecracker_smoke.py \
                    tests/integration/sandbox/test_firecracker_network_policy.py \
                    --tb=short -ra
         - name: capture sandbox health on failure
           if: failure()
           run: codegenie sandbox health > sandbox-health-${{ github.run_id }}.json
         - name: upload health
           if: failure()
           uses: actions/upload-artifact@v4
           with:
             name: sandbox-health-${{ github.run_id }}
             path: sandbox-health-*.json
         - name: page on-call (weekly cron failure only)
           if: failure() && github.event_name == 'schedule'
           uses: PagerDuty/pagerduty-change-events-action@v1   # replace with org-standard action
           with:
             integration-key: ${{ secrets.PAGERDUTY_KVM_RUNNER_KEY }}
             summary: "codegenie firecracker weekly smoke failed"
             severity: error
             links: '[{"href":"https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}","text":"workflow run"}]'
   ```
5. Add the top-of-workflow comment block documenting: runner label `[self-hosted, kvm]`, on-call rotation = `<owner>` (placeholder for Open Q6 closure), PagerDuty service = `codegenie-firecracker-smoke`, alert thresholds.
6. Wire the perf JSONL write at the boundary of the smoke test in a `pytest` autouse fixture so failure paths still emit a row.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/sandbox/test_firecracker_smoke.py` (and `test_firecracker_network_policy.py`).

```python
# tests/integration/sandbox/test_firecracker_smoke.py
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from codegenie.sandbox.firecracker.client import FirecrackerClient
from codegenie.gates.runner import GateRunner
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.gates.strict_and import StrictAndGate
from codegenie.sandbox.spec_builder import SandboxSpecBuilder
from codegenie.gates.contract import GateContext


pytestmark = pytest.mark.skip_if_no_kvm


def test_firecracker_runs_hello_node_in_microvm_within_budget(tmp_path: Path) -> None:
    client = FirecrackerClient.from_digests_yaml()
    gate = StrictAndGate.from_yaml(Path("src/codegenie/gates/catalog/stage6_validate.yaml"))
    ledger = RetryLedger(run_dir=tmp_path / "rem", gate_id="stage6_validate",
                         prev_chain_head=None)
    runner = GateRunner(client=client, gate=gate, ledger=ledger,
                        spec_builder=SandboxSpecBuilder.from_catalog())

    fixture = Path("tests/fixtures/repos/hello-node").resolve()
    ctx = GateContext(worktree=fixture, run_id=tmp_path.name)

    start = time.monotonic()
    outcome = runner.run(ctx)
    elapsed = time.monotonic() - start

    assert outcome.passed, f"hello-node gate did not pass: {outcome.summary}"
    assert elapsed <= 300, f"smoke exceeded 300 s budget: {elapsed:.1f}s"

    attempts = list((tmp_path / "rem" / "gates" / "stage6_validate" / "attempts.jsonl").read_text().splitlines())
    last = json.loads(attempts[-1])
    assert last["signals"]["backend"] == "firecracker", "backend annotation missing"
    assert last["signals"]["gate_isolation_class"] == "microvm"


# tests/integration/sandbox/test_firecracker_network_policy.py
import subprocess

import pytest

from codegenie.sandbox.contract import SandboxSpec
from codegenie.sandbox.firecracker.client import FirecrackerClient


pytestmark = pytest.mark.skip_if_no_kvm


def test_scoped_allowlist_permits_npm_blocks_github(tmp_path: Path) -> None:
    client = FirecrackerClient.from_digests_yaml()
    spec_npm = SandboxSpec(
        cmd=["sh","-c","npm ci --silent"],
        copy_in=[("tests/fixtures/repos/hello-node", "/work")],
        logs_dir=tmp_path / "logs_npm", copy_out_root=tmp_path / "out_npm",
        time_budget_seconds=180, memory_limit_mib=1024,
        network="scoped", egress_allowlist=["registry.npmjs.org"],
        env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
    )
    run = client.execute(spec_npm)
    assert run.exit_code == 0, "npm ci must succeed via allowlist"

    spec_gh = spec_npm.model_copy(update={
        "cmd": ["sh","-c","curl -sf https://github.com -o /dev/null"],
        "logs_dir": tmp_path / "logs_gh", "copy_out_root": tmp_path / "out_gh",
    })
    run2 = client.execute(spec_gh)
    assert run2.exit_code != 0, "github.com egress must be blocked by nftables"

    # No leaked nft tables.
    out = subprocess.check_output(["nft","list","tables"]).decode()
    assert "cgsbx-" not in out, "TAP/nftables table leaked across runs"
```

Use `pytest.mark.skip_if_no_kvm` for both files. The CI workflow asserts they run on the labeled runner.

### Green — make it pass

- Tests above are the contract; satisfying them requires no new production code beyond what S6-01–S6-03 landed.
- Workflow file is committed at `.github/workflows/firecracker-smoke.yml`.
- Marker registered in `tests/conftest.py`.
- Perf JSONL fixture lives in `tests/integration/sandbox/conftest.py` (autouse, opt-in via marker).

### Refactor — clean up

- Move the per-test perf-emit into a shared `tests/integration/sandbox/conftest.py` autouse fixture so additional KVM tests get it for free.
- Promote any hand-rolled `SandboxSpec` construction in the network test into a `_spec_from(...)` helper to keep the assertion lines short.
- Add a top-of-file docstring in each test file pointing to ADR-0004 / ADR-0009 / Goal 6.
- Replace the literal cron string with a constant + comment so the next reviewer understands "Monday 07:00 UTC" without decoding.

## Files to touch

| Path | Why |
|---|---|
| `tests/conftest.py` | Register `skip_if_no_kvm` marker globally. |
| `tests/integration/sandbox/test_firecracker_smoke.py` | New — KVM-gated full gate run. |
| `tests/integration/sandbox/test_firecracker_network_policy.py` | Populated from the S6-02 placeholder. |
| `tests/integration/sandbox/conftest.py` | Autouse perf-emit fixture. |
| `.github/workflows/firecracker-smoke.yml` | New CI + cron workflow. |
| `.github/workflows/firecracker-smoke.yml.README.md` (or inline header) | Document runner label, PagerDuty service, rotation owner. |
| `docs/phases/05-sandbox-trust-gates/README.md` | Mark Open Q6 closed once the runner + paging are operational. |

## Out of scope

- Operator CLI implementations (`codegenie sandbox health/inspect/gc`) — S8-01 (this story only *invokes* `health` from the workflow; the command exists from S6-03's CLI scaffolding).
- Perf-budget regression gates (p50/p95 / retry-2 budget) — S7-02 (this story records JSONL; S7-02 reads it).
- Multi-arch KVM testing — Phase 5 is x86_64 only.
- E2E `codegenie remediate` smoke on Linux KVM — S8-03 (this story exercises the gate primitives, not the orchestrator).
- Cron-failure runbook content — captured in the workflow comment header, but a full runbook is a Phase 14 ops artifact.

## Notes for the implementer

- The 300 s wall budget is non-negotiable for ADR-0019 evidence; if a contributor finds it tight, the right answer is a profiling pass, not bumping the budget. Coordinate with S7-02's owner.
- `runs-on: [self-hosted, kvm]` requires *both* labels — a generic self-hosted runner without the `kvm` label is not picked up. Document this in the workflow header so on-call understands why a queue may grow.
- The cron is `0 7 * * 1` (Monday 07:00 UTC) — picked to land before US/EU work hours so the on-call sees the page before the team starts. Do not change without an ADR amendment.
- PagerDuty action choice matters: prefer the org's standardized action (replace the placeholder `PagerDuty/pagerduty-change-events-action@v1`). The exact action goes through the same review as a code dependency.
- The `--check` invocation of `codegenie sandbox prepare --backend firecracker` is the load-bearing pre-flight; if S6-03's `--check` lands before this story, gate the workflow on it. If not, this story's pre-flight is a `blake3sum` invocation directly against `tools/digests.yaml`.
- The hello-node fixture is shared with S3-07 and S5-05; do not vendor a second copy.
- A "no nft table leaked" assertion is one of the few places we shell out from a *test* — keep it in the test file, not production, and adjust the chokepoint AST test (S5-04) only if necessary (it should already exempt `tests/`).
- If the self-hosted KVM runner is not provisioned at story start, escalate per `phase-arch-design.md §Risks risk-2`: split delivery into 6a (the two test files + marker + local-KVM runs) and 6b (workflow + paging). 6a can merge ahead of 6b but the phase exit criterion is **not** met until 6b is also green at least once.
- A passing weekly cron *is* the evidence ADR-0019 needs — make sure the run captures cold-start latency, kernel feature requirements (uname output), and per-evaluation wall-clock in the JSONL so Phase 13/16 has data to consume.
