# DELIBERATELY ADVERSARIAL — do not run outside the test harness; do not copy into production.
#
# Adversarial fixture for S5-06 (Phase 2). The CMD attempts an outbound HTTP
# request. Under `--network=none`, the kernel rejects the syscall before any
# DNS resolution; the test does NOT depend on `example.com` being reachable.
#
# Expected outcome: `TraceScenarioCompleted` with the slice's
# `network_endpoints_touched.outbound == []` (the empty list is the proof of
# `--network=none`).
FROM alpine:3.20
CMD ["sh", "-c", "wget -q http://example.com -O /dev/null"]
