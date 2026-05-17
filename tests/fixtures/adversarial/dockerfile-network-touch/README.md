# dockerfile-network-touch — DELIBERATELY ADVERSARIAL

**Do not run outside the test harness; do not copy into production.**

Attempts an outbound HTTP request via `wget`. Under `--network=none`, the
kernel refuses the underlying `connect()` syscall before DNS even runs, so
this test does **not** depend on `example.com` being reachable from the
host CI runner.

**Hardening dimension exercised:** `--network=none`.
**Expected outcome:** `TraceScenarioCompleted`; the slice's
`network_endpoints_touched.outbound` is empty; `binaries_executed` contains
`wget`; `wall_clock_ms < 30_000` (fast fail).

Scenario configuration lives in `.codegenie/scenarios.yaml`.
