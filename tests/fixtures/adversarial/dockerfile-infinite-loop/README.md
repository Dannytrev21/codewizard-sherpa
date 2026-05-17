# dockerfile-infinite-loop — DELIBERATELY ADVERSARIAL

**Do not run outside the test harness; do not copy into production.**

CPU pathology with no fork. Proves the per-scenario timeout fires
independently of `--cap-drop=ALL` (which has nothing to contain here — no
processes are being created beyond the original `sh`).

**Hardening dimension exercised:** per-scenario 120 s timeout.
**Expected outcome:** `TraceScenarioFailed(reason=ScenarioTimeout(...))`,
captured stdout bounded by S5-02's `run_allowlisted` envelope.

Scenario configuration lives in `.codegenie/scenarios.yaml`.
