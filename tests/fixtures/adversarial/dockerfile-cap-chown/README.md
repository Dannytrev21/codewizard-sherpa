# dockerfile-cap-chown — DELIBERATELY ADVERSARIAL

**Do not run outside the test harness; do not copy into production.**

Attempts `chown 0:0 /etc/passwd`. The container runs as root (default
`alpine:3.20` user) so the failure path is the absence of `CAP_CHOWN`, not
the absence of root: `--cap-drop=ALL` removes every capability, including
`CAP_CHOWN`, so `chown` returns `Operation not permitted`.

**Hardening dimension exercised:** `--cap-drop=ALL` (specifically dropping
`CAP_CHOWN`).
**Expected outcome:** `TraceScenarioCompleted`; the captured strace artifact
bytes contain the failure marker substring (case-insensitive regex
`operation not permitted|chown.*permitted`).

Scenario configuration lives in `.codegenie/scenarios.yaml`.
