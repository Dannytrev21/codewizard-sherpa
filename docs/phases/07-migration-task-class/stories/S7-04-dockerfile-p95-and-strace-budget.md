# Story S7-04 — Dockerfile-engine p95 + strace budget distribution

**Step:** Step 7 — Performance canaries + fence-CI extension
**Status:** Ready
**Effort:** S
**Depends on:** S7-03
**ADRs honored:** ADR-P7-014 (baseline-relative pattern, runner-class metadata), ADR-P7-013 (shell-trace gate-time chokepoint — budget configurable in `tools/digests.yaml`)

## Context

Two narrower perf canaries: (1) the Dockerfile recipe engine's parse-mutate-serialize round-trip must hold p95 ≤ 100 ms (the engine is invoked once per workflow; a regression here multiplies across every distroless workflow) and (2) the strace gate's wall-clock distribution must be measured empirically — Risk #3 in `High-level-impl.md` names the 30 s budget as "the highest-risk variable" and this canary is the *only* signal the team has that the budget is correctly calibrated. The strace test is intentionally a *warning* canary, not a *failing* canary, until Phase 13 calibrates — failing on budget exhaust at this phase risks silencing real signal during the calibration period.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 4 — DockerfileRecipeEngine` — `available()` semantics, round-trip safety contract, byte-only canonicalization (no semantic rewrites).
  - `../phase-arch-design.md §Component 2 — ShellInvocationTraceProbe` — strace budget (30 s default), strace-in-sidecar architecture (Gap 4 mitigation), the `tools/digests.yaml#gate.shell_trace.budget_s` configurable.
  - `../phase-arch-design.md §Goals G14` — round-trip safety property (related; this story's p95 canary sits next to but doesn't replace S4-02's correctness property).
  - `../phase-arch-design.md §Testing strategy ›Performance regression tests` bullets 4 and 5 — the canary file names and thresholds.
  - `../phase-arch-design.md §Edge cases #5` — strace 30 s budget exhaust manifests as `subprocess.TimeoutExpired` with `confidence=medium`.
  - `../phase-arch-design.md §Open questions deferred to implementation #1` — strace 30 s budget calibration.
- **Phase ADRs:**
  - `../ADRs/0014-regression-suite-wall-clock-canary.md` — ADR-P7-014 — baseline-file + flag pattern.
  - `../ADRs/0013-shell-trace-runs-gate-time-in-phase5-chokepoint.md` — ADR-P7-013 — confirms the 30 s budget is a configurable in `tools/digests.yaml#gate.shell_trace.budget_s` (not a hardcoded constant) — this story's strace canary asserts the configurable is read.
- **Source design:**
  - `../High-level-impl.md §Implementation-level risks #3` and `#5` — toolchain pinning drift and DinD-on-macOS strace tightness; the strace canary surfaces both.
- **Existing code:**
  - `src/codegenie/recipes/engines/dockerfile_engine.py` (S4-01) — the engine under test for the p95 canary.
  - `src/codegenie/probes/shell_invocation_trace.py` (S3-02) — the probe under test for the strace canary.
  - `tools/digests.yaml#gate.shell_trace.budget_s` (S2-07) — the configurable.

## Goal

`pytest tests/perf/test_dockerfile_engine_p95.py` asserts engine round-trip p95 ≤ 100 ms over a representative input mix and `pytest tests/perf/test_strace_budget_distribution.py` records empirical strace p50/p95 across the warm distroless portfolio and warns (does *not* fail) if p95 > 24 s.

## Acceptance criteria

- [ ] `tests/perf/test_dockerfile_engine_p95.py` exists, exercises `DockerfileRecipeEngine` on a representative input mix (≥ 100 invocations sampled from `tests/adversarial/dockerfiles/` non-rejected fixtures + the 3-fixture distroless portfolio Dockerfiles), measures wall-clock per round-trip, asserts p95 ≤ 100 ms.
- [ ] The p95 canary uses `time.monotonic_ns()` for measurement (sub-millisecond precision); excludes the first 5 invocations as warm-up (interpreter + import + first JIT-ish caching) — documented in test docstring.
- [ ] `tests/perf/test_strace_budget_distribution.py` exists, runs `ShellInvocationTraceProbe` against the 3-fixture warm portfolio (express-distroless, static-go-distroless, alpine-to-glibc-distroless) under realistic candidate-image conditions, records empirical p50 and p95 wall-clock, *warns* via `warnings.warn(StraceBudgetTightWarning)` when p95 > 24 s.
- [ ] Strace canary *hard-fails* if p95 ≥ `tools/digests.yaml#gate.shell_trace.budget_s` (i.e. workflows are actually timing out in steady-state operation) — the warning band (24 s ≤ p95 < 30 s) is informational; the hard-fail band (p95 ≥ 30 s) is a correctness failure dressed as perf.
- [ ] Strace canary reads the budget from `tools/digests.yaml#gate.shell_trace.budget_s` — not a hardcoded `30`. Asserted by an explicit test that mutates the YAML in a tmp dir and verifies the canary picks it up (closes Risk #3 latent-hardcode bug).
- [ ] Baseline keys added to `tests/perf/baseline.json`: `dockerfile_engine_roundtrip_p95_ms`, `strace_steady_state_p50_s`, `strace_steady_state_p95_s`. Bumps via `--update-perf-baseline` (S7-01).
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] Both canaries in CI's merge-gate lane.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` clean on touched files.

## Implementation outline

1. Add `tests/perf/test_dockerfile_engine_p95.py`. Build the input mix from `tests/adversarial/dockerfiles/` (filter to those that parse — exclude the rejected fixtures) plus the 3 distroless fixtures' Dockerfiles. Loop ≥ 100 invocations, time each round-trip with `time.monotonic_ns()`, compute p95 with `statistics.quantiles(... n=20)[18]` or `numpy.percentile(..., 95)`.
2. Add `tests/perf/test_strace_budget_distribution.py`. Re-use the `throughput_run.warm_distroless` fixture from S7-03 — the warm distroless leg already invokes `ShellInvocationTraceProbe` on each workflow. Pull per-invocation strace wall-clock from the gate audit chain (every probe invocation is recorded with `wall_clock_ms`; structured access via `from codegenie.gates.audit_chain import iter_events`).
3. The strace canary asserts: `p95 < budget_from_digests` (hard) and warns when `p95 > 24` (informational). Read the budget via the `tools/digests.py` accessor (or whatever S2-07 lands as the precedence-aware reader: CLI > env > digests.yaml > default).
4. Add a `StraceBudgetTightWarning` class in `tests/perf/_warnings.py` so PR reviewers see a categorized warning in CI logs.
5. Pin baseline values from one measured run on the reference runner; commit `baseline.json` updates.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Two test files, two red commits.

```python
# tests/perf/test_dockerfile_engine_p95.py
def test_dockerfile_engine_roundtrip_p95_under_100ms(dockerfile_engine_invocations):
    # arrange: ≥100 round-trip measurements collected
    durations_ms = dockerfile_engine_invocations.durations_ms
    # act
    p95 = percentile(durations_ms, 95)
    # assert
    assert p95 <= 100.0, (
        f"DockerfileRecipeEngine round-trip p95 {p95:.2f} ms > 100 ms; "
        f"slowest 5: {sorted(durations_ms, reverse=True)[:5]}"
    )
```

```python
# tests/perf/test_strace_budget_distribution.py
def test_strace_steady_state_p95_does_not_exceed_budget(strace_distribution):
    budget_s = strace_distribution.budget_s_from_digests
    p95_s = strace_distribution.p95_s
    assert p95_s < budget_s, (
        f"strace p95 {p95_s:.1f}s >= configured budget {budget_s:.1f}s — "
        f"workflows are timing out in steady-state operation"
    )

def test_strace_steady_state_warns_when_p95_over_24s(strace_distribution, recwarn):
    if strace_distribution.p95_s > 24.0:
        # warning is expected; if the warning didn't fire, the canary is silently broken
        assert any(issubclass(w.category, StraceBudgetTightWarning) for w in recwarn.list)
    else:
        # under 24s — no warning expected
        assert not any(issubclass(w.category, StraceBudgetTightWarning) for w in recwarn.list)

def test_strace_canary_reads_budget_from_digests_yaml(tmp_path, monkeypatch):
    # arrange: synthesize a digests.yaml with a 60s budget
    fake = tmp_path / "digests.yaml"
    fake.write_text("gate:\n  shell_trace:\n    budget_s: 60\n")
    monkeypatch.setenv("CODEGENIE_DIGESTS_YAML", str(fake))
    # act
    budget = read_strace_budget()
    # assert
    assert budget == 60.0  # not the hardcoded 30
```

Each red test fails because the helper / fixture doesn't exist. Commit the failing tests.

### Green — make it pass

- Add `tests/perf/_warnings.py` with `class StraceBudgetTightWarning(UserWarning): pass`.
- Add `tests/perf/_distribution.py` with `percentile(values: list[float], q: float) -> float` and `read_strace_budget() -> float` (delegating to `codegenie.tools.digests` if S2-07 exposes a reader; otherwise inline a tiny precedence-aware reader).
- Add the `dockerfile_engine_invocations` and `strace_distribution` fixtures in `tests/perf/conftest.py`.
- Implement the two canary tests.

### Refactor — clean up

- Type hints + frozen Pydantic models for the fixture return shapes (`DockerfileEngineInvocations`, `StraceDistribution`).
- Docstring on `test_dockerfile_engine_roundtrip_p95_under_100ms` explicitly documenting the 5-invocation warm-up exclusion and why (interpreter cold-start dominates first calls).
- Docstring on the strace canary explicitly distinguishing the *warning band* (24–30 s) from the *failure band* (≥ 30 s) — per Risk #3.
- Edge case from `phase-arch-design.md §Edge cases #5`: when strace exhausts the budget (`subprocess.TimeoutExpired`), the audit chain records `wall_clock_ms == budget_ms` — the canary's p95 *includes* timed-out invocations because a strace that hits the wall is still wall-clock-charged.
- Per Global Rule 12 (Fail loud): if the gate-audit chain has zero strace events (e.g. because S7-03's throughput run skipped or the chain was rotated mid-test), raise `EmptyStraceDistribution` and fail — never assert on an empty distribution.

## Files to touch

| Path | Why |
|---|---|
| `tests/perf/test_dockerfile_engine_p95.py` | New file — dockerfile engine p95 canary. |
| `tests/perf/test_strace_budget_distribution.py` | New file — strace distribution canary (Risk #3). |
| `tests/perf/_distribution.py` | New file — `percentile()`, `read_strace_budget()` helpers. |
| `tests/perf/_warnings.py` | New file — `StraceBudgetTightWarning`. |
| `tests/perf/conftest.py` | Add `dockerfile_engine_invocations` and `strace_distribution` fixtures. |
| `tests/perf/baseline.json` | Add `dockerfile_engine_roundtrip_p95_ms`, `strace_steady_state_p50_s`, `strace_steady_state_p95_s`. |
| `.github/workflows/ci.yml` | Add both canaries to merge-gate lane. |

## Out of scope

- **Bumping the strace budget.** If S7-04's measurement shows p95 > 24 s in practice, *do not* silently raise `gate.shell_trace.budget_s` to suppress the warning — file a follow-up to amend ADR-P7-013 with the measured distribution as evidence. The warning *is* the deliverable.
- **Round-trip *correctness* property.** Owned by S4-02 (`tests/property/test_dockerfile_engine_roundtrip.py`); this story is the *perf* canary, not the correctness canary.
- **Strace under DinD on macOS.** Gap 4 (sibling sidecar pattern) is closed by S3-02 + S3-03. This story consumes their output; it does *not* re-test the sidecar arrangement.
- **Per-LLM-call wall-clock.** Phase 13 (cost observability) owns that; not in Phase 7.
- **Workflow throughput.** Owned by S7-03.

## Notes for the implementer

- **The strace canary is intentionally a *warning*, not a *fail*, between 24 s and 30 s.** This is unusual; document it loudly in the test docstring. Reviewers tend to assume canaries fail on threshold breach — this one warns to preserve signal during the Phase 13 calibration period named in `phase-arch-design.md §Open questions deferred to implementation #1`.
- **Read the budget from `tools/digests.yaml`** via the existing reader (or inline a minimal precedence-aware reader: CLI > env > digests.yaml > default 30). Per `phase-arch-design.md §Harness engineering ›Configuration`. Do *not* hardcode 30 in the canary — Risk #3 specifically calls this out.
- **The p95 computation uses linear interpolation by default in `numpy.percentile`.** If you use `statistics.quantiles`, the exclusive-method default is fine but document the choice. Don't mix methods between the dockerfile canary and the strace canary — pick one and use it in `tests/perf/_distribution.py`.
- **Warm-up exclusion is 5 invocations, not 1.** First-call import cost + `dockerfile-parse` lib's lazy load + interpreter caching all show up in the first few calls; 5 is the conservative tail.
- **The strace distribution includes timeouts.** A strace that wall-clocks out at 30 s contributes 30 s to the distribution — *that's* the failure mode the canary is watching. Don't filter timeouts out.
- **Honor Global Rule 11 (Match the codebase's conventions).** If S2-07 exposed `codegenie.tools.digests.read_setting(path: str, default: T) -> T`, use it — don't roll a parallel YAML reader.
- **Per Global Rule 8 (Read before you write):** the gate audit chain's event shape was defined in Phase 5 / extended in Phase 6. Read `src/codegenie/gates/audit_chain.py` for the existing event-iteration API before parsing files yourself.
- **`time.monotonic_ns()` not `time.time()` not `time.perf_counter()`.** `monotonic_ns` is the right choice for sub-millisecond wall-clock that's also resilient to wall-clock jumps mid-test. Document the choice in the helper module.
- **The 100 ms threshold is generous** for a pure-Python AST round-trip on a small Dockerfile — if you measure 250 ms in practice, you have a bug in the engine, not a perf issue to defer.
