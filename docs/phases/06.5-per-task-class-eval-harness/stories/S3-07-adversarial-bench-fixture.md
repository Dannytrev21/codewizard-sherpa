# Story S3-07 — Adversarial bench fixture portfolio

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready
**Effort:** M
**Depends on:** S3-04 (six failure paths must resolve correctly)
**ADRs honored:** ADR-0001 (subprocess isolation — env-read attempt), ADR-0004 (taxonomy — malformed failure_modes.yaml), ADR-0008 (breakdown-key ban — banned-key fixture)

## Context

The six per-case failure paths from S3-04 prove the runner *responds correctly* to each typed condition. This story builds the adversarial **bench fixture portfolio** that proves the harness as a whole survives a hostile bench: a malicious-PR-shaped task class designed to exercise every isolation, taxonomy, and digest defense the harness owns. The fixture lives at `tests/fixtures/bench/adversarial-task-class/` and is driven by `tests/adv/test_rubric_*.py`. Each scenario is one attack vector → one expected typed failure.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Trust boundaries and threat surface`, `§Edge cases #4, #12, #17, #21`, `§Resilience strategies`
- **Phase ADRs:** `../ADRs/0001-rubric-execution-isolation-via-subprocess.md`, `../ADRs/0004-per-task-class-failure-modes-taxonomy.md`, `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md`, `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md`
- **Source design:** `../final-design.md §Risks #2, #4`, `§Failure modes`

## Goal

Build `tests/fixtures/bench/adversarial-task-class/` covering five attack scenarios, plus the matching `tests/adv/test_rubric_*.py` drivers that assert each scenario produces the typed failure the harness's defenses promise.

## Acceptance criteria

- [ ] Fixture directory `tests/fixtures/bench/adversarial-task-class/` exists with the standard task-class shape: `registration.py`, `rubric.py`, `breakdown_keys.py`, `failure_modes.yaml`, `cases/digests.yaml`, plus 5 case directories named for each scenario.
- [ ] **Scenario 1 — Env-read attempt.** Rubric attempts to read `ANTHROPIC_API_KEY` and emit it in the score's `detail`. Driver: `tests/adv/test_rubric_env_read_attempt.py`. Assertion: the subprocess returns no credential value; `os.environ.get("ANTHROPIC_API_KEY")` is `None` from inside the rubric (already covered by S3-03's adversarial test — reuse here as an integration fixture).
- [ ] **Scenario 2 — Rubric timeout.** Rubric sleeps for 120 s with `case.rubric_wall_clock_seconds = 5`. Driver: `tests/adv/test_rubric_timeout.py`. Assertion: `FailureMode(code="rubric.timeout", severity="block")` is recorded; no stranded subprocess after the run (use `psutil` or `os.waitpid` to confirm cleanup).
- [ ] **Scenario 3 — Banned breakdown key emitted at runtime.** Rubric returns `BenchScore.breakdown = {"llm_confidence": 0.9}`. Static fence-CI (S7-01 assertion #5) catches this at PR time, but the runtime defense (S3-04) must also catch it. Driver: `tests/adv/test_runtime_breakdown_key_ban.py`. Assertion: `FailureMode(code="rubric.unknown_breakdown_key", severity="block")`; the banned key is dropped from the persisted `BenchScore`.
- [ ] **Scenario 4 — Poisoned case (digest mismatch).** A case directory's `case.toml` has been edited but `cases/digests.yaml` was not updated. Driver: `tests/adv/test_poisoned_case_digest_mismatch.py`. Assertion: `BenchCaseDigestMismatch(case_id, expected_blake3, computed_blake3)` raised at plan time (S3-01); the run aborts before any SUT call.
- [ ] **Scenario 5 — Malformed `failure_modes.yaml`.** YAML declares an entry with `severity: critical` (not in `{block, warn, info}`) or a missing `description`. Driver: `tests/adv/test_malformed_failure_modes_yaml.py`. Assertion: loader raises `TierConfigInvalid` (or a dedicated `FailureModeTaxonomyInvalid`) at task-class registration time; the run never starts.
- [ ] All five drivers are runnable via `pytest tests/adv/` in under 30 s combined wall-clock.
- [ ] Adversarial fixture cases are tagged `curation_class="held-out"` so the fence-CI held-out floor (ADR-0006) is exercised on an adversarial corpus — defense in depth.
- [ ] `mypy --strict`, ruff clean; no skipped tests; each driver explicitly cites the ADR that promises the defense.

## Implementation outline

1. Create `tests/fixtures/bench/adversarial-task-class/`:
   - `registration.py`: `@register_task_class("adversarial-task-class", min_cases_for_promotion={})` (no tiers — fence-CI assertion #3 then doesn't require held-out floor).
   - `rubric.py`: a `if __name__ == "__main__"` entrypoint that branches on case_id (`env_read_attempt`, `rubric_timeout`, `banned_breakdown_key`).
   - `breakdown_keys.py`: empty `StrEnum BreakdownKey` (or one valid key like `PASSED`).
   - `failure_modes.yaml`: minimal valid taxonomy declaring the six runner-internal codes.
   - `cases/`: 5 case dirs; one is intentionally digest-mismatched.
   - `cases/digests.yaml`: 4 valid entries + 1 stale entry for scenario 4.
2. For scenario 5, store a second `tests/fixtures/bench/adversarial-task-class-malformed-yaml/` mirror with `failure_modes.yaml` carrying `severity: critical`; loader-level test loads it directly.
3. Drivers in `tests/adv/` each import the fixture path, set up the SUT (a trivial stub that returns empty harness_output), invoke `Runner().run_eval(...)`, and assert on the resulting `BenchRunReport` or the raised exception.

## TDD plan — red / green / refactor

### Red

`tests/adv/test_runtime_breakdown_key_ban.py`:

```python
@pytest.mark.asyncio
async def test_banned_breakdown_key_at_runtime_blocks(adversarial_bench_root):
    plan = make_plan(adversarial_bench_root, task_class="adversarial-task-class",
                     cases=["banned_breakdown_key"])
    report = await Runner().execute(plan, system_under_test=NullSUT())

    score = report.per_case[0]
    codes = {fm.code for fm in score.failure_modes}
    assert "rubric.unknown_breakdown_key" in codes
    assert "llm_confidence" not in score.breakdown  # persisted score is sanitized
    assert "rubric.unknown_breakdown_key" in report.block_severity_failure_modes
```

Similar red tests for the other four scenarios — each asserts one ADR-promised defense.

### Green

Author the fixture rubric branches; ensure case `case.toml`s and digests file are wired; drivers assert on report shape.

### Refactor

Promote shared driver helpers (`make_plan(...)`, `NullSUT`, `assert_block_severity`) into `tests/adv/conftest.py`; document each scenario's threat-model row in the fixture's `README.md`; tag each driver's docstring with the ADR it defends ("This test enforces ADR-0001 §Decision"); add a single integration test that runs all five scenarios in one `run_eval` invocation and asserts the report carries every expected block-severity code.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/bench/adversarial-task-class/**` | New fixture corpus (5 scenarios) |
| `tests/fixtures/bench/adversarial-task-class-malformed-yaml/**` | Scenario 5 mirror with malformed YAML |
| `tests/adv/test_rubric_env_read_attempt.py` | Scenario 1 driver |
| `tests/adv/test_rubric_timeout.py` | Scenario 2 driver |
| `tests/adv/test_runtime_breakdown_key_ban.py` | Scenario 3 driver |
| `tests/adv/test_poisoned_case_digest_mismatch.py` | Scenario 4 driver |
| `tests/adv/test_malformed_failure_modes_yaml.py` | Scenario 5 driver |
| `tests/adv/conftest.py` | Shared helpers (`NullSUT`, `make_plan`, fixture path injection) |

## Out of scope

- **Network-egress prevention** from the rubric — ADR-0001 acknowledges this as a residual risk; not covered until Phase 16's microVM upgrade. Do not add a scenario for it (it would be a known-failing test).
- **RSS / fork-bomb / setrlimit** — same Phase 16 deferral.
- **Process-group-kill** — OQ #4; deferred. Scenario 2 asserts cleanup of the immediate child, not of grandchildren the rubric forked.
- **Mutation testing of `rubric.py`** — Phase 16 (production ADR-0008 / phase ADR-0016 OQ #5).

## Notes for the implementer

- **Treat this fixture as a regression corpus.** Every future ADR that adds a defense should add a scenario here. The fixture is the long-term running record of "what attacks the harness claims to defeat."
- The `failure_modes.yaml` for `adversarial-task-class` must still declare the six runner-internal codes (`sut.exception`, `sut.timeout`, `rubric.malformed_output`, `rubric.timeout`, `rubric.unknown_breakdown_key`, `rubric.unknown_failure_mode`, `sut.cancelled`) — otherwise loader rejects the task class for taxonomy gaps.
- Scenario 4's digest mismatch must be reproducible from a script — don't hand-edit `digests.yaml` and forget to commit the stale state. A `scripts/seed_adversarial_fixtures.py` (or `conftest.py` `pytest_sessionstart` hook) is the cleanest way; commit the stale entry deliberately.
- Scenario 5's separate fixture directory avoids loader-import-order coupling. Loading the malformed YAML from the same task class as the runtime scenarios would prevent the runtime tests from running.
- Each driver should fail loudly on the wrong defense — e.g., scenario 1 should fail if the env scrub regresses, not just if the rubric prints something. Assert on the specific credential value being `None`, not on the rubric's exit code alone.
- The `cwd=TemporaryDirectory()` cleanup invariant: after the run, `os.listdir(tempfile.gettempdir())` should not contain stale `tmp...` dirs owned by the test user. Use `pytest-cleanup` or the `_check_tempdir_clean()` helper from S3-03's adversarial test.
- Resist building a sixth scenario for "rubric makes a network call." That's the residual ADR-0001 calls out by name. Anything that pretends to test it without Phase 16's substrate would be theater.
