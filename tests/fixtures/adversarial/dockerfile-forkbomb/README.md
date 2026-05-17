# dockerfile-forkbomb — DELIBERATELY ADVERSARIAL

**Do not run outside the test harness; do not copy into production.**

This Dockerfile's CMD is the classic shell forkbomb:

```sh
:(){ :|:& };:
```

A future maintainer who sees the obvious-looking syntax MUST NOT "fix" it — the
literal text above is the test's load-bearing payload. The function `:`
recursively forks itself piped into itself, doubling processes until the
container's cgroup limits or the per-scenario 120 s timeout intervene.

**Hardening dimension exercised:** `--cap-drop=ALL` + per-scenario timeout.
**Expected outcome:** `TraceScenarioFailed(reason=ScenarioTimeout(...))`,
host-side process count delta ≤ ±2 (psutil zombie-retention slack).

Scenario configuration lives in `.codegenie/scenarios.yaml`. The single scenario
is named `forkbomb` and its command IS the adversarial invocation — without the
fixture-level override, `RuntimeTraceProbe` would fall back to the five
canonical scenarios (whose CMDs are `sh -c exit 0` — they would NOT exercise
the forkbomb at all).
