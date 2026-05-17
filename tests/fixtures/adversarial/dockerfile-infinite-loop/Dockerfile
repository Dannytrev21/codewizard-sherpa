# DELIBERATELY ADVERSARIAL — do not run outside the test harness; do not copy into production.
#
# Adversarial fixture for S5-06 (Phase 2). The CMD is a busy-loop with no
# fork — pure CPU/stdout pathology. Distinguishes the per-scenario timeout
# from the cap-drop containment proof:
#   - `dockerfile-forkbomb`: cap-drop + timeout together
#   - `dockerfile-infinite-loop`: timeout alone (no fork to contain)
#
# Expected outcome: `TraceScenarioFailed(reason=ScenarioTimeout(...))`.
FROM alpine:3.20
CMD ["sh", "-c", "while true; do echo .; done"]
