# DELIBERATELY ADVERSARIAL — do not run outside the test harness; do not copy into production.
#
# Adversarial fixture for S5-06 (Phase 2). The CMD is the classic shell forkbomb
#  (:(){ :|:& };:) — pure resource exhaustion, no chown, no setuid, no network.
# This fixture exercises:
#   - `--cap-drop=ALL`        (process containment under cgroup limits)
#   - per-scenario 120 s timeout (the only stop condition that is guaranteed
#     to fire on a runaway forkbomb)
#
# The hardening proof: the inner container is contained; the host's process
# count does not balloon; the per-scenario timeout fires and emits
# `TraceScenarioFailed(reason=ScenarioTimeout(...))`.
FROM alpine:3.20
CMD ["sh", "-c", ":(){ :|:& };:"]
