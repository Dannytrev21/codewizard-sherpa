# DELIBERATELY ADVERSARIAL — do not run outside the test harness; do not copy into production.
#
# Adversarial fixture for S5-06 (Phase 2). The CMD attempts a `chown` of
# `/etc/passwd`, which requires `CAP_CHOWN`. Under `--cap-drop=ALL`, the
# capability is unavailable; `chown` fails with `Operation not permitted`
# and the failure marker is captured in the strace artifact stderr stream
# (S5-02 writes `run_result.stderr` of the strace command to disk).
#
# Expected outcome: `TraceScenarioCompleted`; the captured artifact bytes
# contain the substring `Operation not permitted` (or its lowercase form).
FROM alpine:3.20
CMD ["sh", "-c", "chown 0:0 /etc/passwd; exit 0"]
