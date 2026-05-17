# dockerfile-setuid — DELIBERATELY ADVERSARIAL

**Do not run outside the test harness; do not copy into production.**

Sets up a setuid-root binary (`/usr/local/bin/su-copy`, mode `4755`) by
copying `/bin/busybox` and runs it as a non-root user (uid 1000). With
`--security-opt=no-new-privileges`, the setuid bit cannot elevate the
process: the binary executes as uid 1000, not as uid 0.

**Why busybox and not a committed C binary?** Linux ignores the setuid bit
on shell scripts (historic safety quirk), so the binary must be a real ELF
executable. Copying the in-image `/bin/busybox` keeps the source tree
binary-free.

**Hardening dimension exercised:** `--security-opt=no-new-privileges`.
**Expected outcome:** `TraceScenarioCompleted`; captured artifact bytes
match the family regex `(uid=1000|setuid|operation not permitted|
permission denied)` (case-insensitive). The most common path is
`uid=1000` — positive proof that the setuid bit failed to elevate.

Scenario configuration lives in `.codegenie/scenarios.yaml`.

## Open question — runner-level cap escalation

Some CI runners (privileged Docker-in-Docker) may *accidentally* allow
setuid elevation because the outer runner has loose security defaults.
The test asserts the *inner* container's behavior (what the strace artifact
captured) — not the host's permissions. If a future CI environment
regresses, surface as an ADR-amend candidate, not a fixture rewrite.
