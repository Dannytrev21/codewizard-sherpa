# Story S3-07 — Adversarial bench fixture portfolio

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready
**Effort:** M
**Depends on:** S3-04 (six failure paths must resolve correctly)
**ADRs honored:** ADR-0001 (subprocess isolation — env-read attempt), ADR-0004 (taxonomy — malformed failure_modes.yaml), ADR-0008 (breakdown-key ban — banned-key fixture), ADR-0006 (curation-class held-out floor — adversarial cases tagged `held-out`)

## Context

The six per-case failure paths from S3-04 prove the runner *responds correctly* to each typed condition. This story builds the adversarial **bench fixture portfolio** that proves the harness as a whole survives a hostile bench: a malicious-PR-shaped task class designed to exercise every isolation, taxonomy, and digest defense the harness owns.

The fixture lives at `tests/fixtures/bench/adversarial-task-class/` and is driven by `tests/adv/test_rubric_*.py`. Each scenario is one attack vector → one expected typed failure. This is the long-term running record of "what attacks the harness claims to defeat" — every future ADR that adds a defense should add a scenario here.

The fixture also doubles as the closest thing to a real bench corpus that exists pre-Phase-5 vuln-remediation backfill, so it must be wire-format clean: it must register correctly, parse correctly, and survive fence-CI (where fence assertions allow — scenario 5's malformed YAML is intentionally fence-rejected, hence the separate sibling fixture directory).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Agentic best practices → Tool-use safety` — the SCRUBBED_ENV / cwd / FS-scope guarantees this fixture stress-tests.
  - `../phase-arch-design.md §Edge cases #3, #4, #5, #7, #11, #12` — the six edges this fixture exercises.
  - `../phase-arch-design.md §Testing strategy → Adversarial tests` — `tests/adv/` is the home directory for these drivers.
  - `../phase-arch-design.md §Fixture portfolio` — the canonical list this story implements.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — env-read attempt scenario tests the SCRUBBED_ENV claim.
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — malformed YAML scenario tests the taxonomy parser's loud-fail discipline.
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md` — runtime banned-key emission tests the second-layer defense (fence-CI is the first; runtime is the second).
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md` — adversarial cases are tagged `held-out` so even the adversarial corpus exercises the held-out floor structurally.
- **Source design:** `../final-design.md §Risks #2, #4`, `§Failure modes`.

## Goal

Build `tests/fixtures/bench/adversarial-task-class/` covering five attack scenarios, plus the matching `tests/adv/test_rubric_*.py` drivers that assert each scenario produces the typed failure the harness's defenses promise.

## Acceptance criteria

- [ ] Fixture directory `tests/fixtures/bench/adversarial-task-class/` exists with the standard task-class shape: `registration.py`, `rubric.py`, `breakdown_keys.py`, `failure_modes.yaml`, `cases/digests.yaml`, plus 5 case directories named for each scenario.
- [ ] **Scenario 1 — Env-read attempt.** Rubric attempts `os.environ.get("ANTHROPIC_API_KEY")` and emits it in stderr. Driver: `tests/adv/test_rubric_env_read_attempt.py`. Assertion: the subprocess returns no credential value; the captured stderr (when present) does not contain the parent's secret value; the `FailureMode` carries `code="rubric.malformed_output"` (because the rubric exits non-zero); the run continues.
- [ ] **Scenario 2 — Rubric timeout.** Rubric sleeps for 120 s with `case.rubric_wall_clock_seconds = 1`. Driver: `tests/adv/test_rubric_timeout.py`. Assertion: `FailureMode(code="rubric.timeout", severity="block")` is recorded; the subprocess is reaped (`proc.returncode is not None` after the test); no stranded tempdirs in the test workdir.
- [ ] **Scenario 3 — Banned breakdown key emitted at runtime.** Rubric returns `BenchScore.breakdown = {"llm_confidence": 0.9}`. Static fence-CI (S7-01 assertion #5) catches this at PR time, but the runtime defense (S3-04) must also catch it. Driver: `tests/adv/test_runtime_breakdown_key_ban.py`. Assertion: `FailureMode(code="rubric.unknown_breakdown_key", severity="block", detail="llm_confidence")`; the banned key is **not present** in the persisted `BenchScore.breakdown`.
- [ ] **Scenario 4 — Poisoned case (digest mismatch).** A case directory's `case.toml` has been edited but `cases/digests.yaml` was not updated. Driver: `tests/adv/test_poisoned_case_digest_mismatch.py`. Assertion: `BenchCaseDigestMismatch(case_id, expected_blake3, computed_blake3)` raised at plan time (S3-01); the run aborts before any SUT call; the audit chain length is unchanged.
- [ ] **Scenario 5 — Malformed `failure_modes.yaml`.** Lives in a sibling fixture `tests/fixtures/bench/adversarial-task-class-malformed-yaml/`. YAML declares an entry with `severity: critical` (not in `{block, warn, info}`) and another with a missing `description`. Driver: `tests/adv/test_malformed_failure_modes_yaml.py`. Assertion: loader raises a typed error (`FailureModeTaxonomyInvalid` or the existing `TierConfigInvalid`-style typed error) at task-class registration time; the run never starts.
- [ ] All five drivers are runnable via `pytest tests/adv/` in under 30 s combined wall-clock.
- [ ] Adversarial fixture cases are tagged `curation_class="held-out"` so the fence-CI held-out floor (ADR-0006) is exercised on an adversarial corpus — defense in depth.
- [ ] `mypy --strict`, `ruff format --check`, `ruff check` clean on touched files; no skipped tests; each driver's docstring explicitly cites the ADR that promises the defense.
- [ ] All red tests in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

1. Create `tests/fixtures/bench/adversarial-task-class/`:
   - `registration.py`: `@register_task_class("adversarial-task-class", bench_path=..., min_cases_for_promotion={})` (no tiers — fence-CI assertion #3 then doesn't require silver/gold held-out floor).
   - `rubric.py`: a `if __name__ == "__main__"` entrypoint that reads stdin, parses the case_id, and branches on `case_id` (`env_read_attempt`, `rubric_timeout`, `banned_breakdown_key`, `poisoned_case`, `valid_baseline`).
   - `breakdown_keys.py`: `class BreakdownKey(StrEnum): PASSED = "passed"` (one valid key).
   - `failure_modes.yaml`: minimal valid taxonomy declaring the seven runner-internal codes (`sut.exception`, `sut.timeout`, `sut.cancelled`, `rubric.malformed_output`, `rubric.timeout`, `rubric.unknown_breakdown_key`, `rubric.unknown_failure_mode`).
   - `cases/`: 5 case dirs (one per scenario); one is intentionally digest-mismatched.
   - `cases/digests.yaml`: 4 valid entries + 1 stale entry for scenario 4.
2. For scenario 5, store a second `tests/fixtures/bench/adversarial-task-class-malformed-yaml/` mirror with `failure_modes.yaml` carrying `severity: critical` on one entry and a missing `description` on another; loader-level test loads it directly.
3. Drivers in `tests/adv/` each import the fixture path, set up the SUT (a trivial stub that returns empty harness_output), invoke `Runner().run_eval(...)`, and assert on the resulting `BenchRunReport` or the raised exception.
4. `scripts/seed_adversarial_fixtures.py` (or a `conftest.py` `pytest_sessionstart` hook) — operator tool to regenerate the stale-digest case deterministically; commit the stale entry deliberately, do not hand-edit.

## TDD plan — red / green / refactor

### Red — write failing tests first

`tests/adv/test_runtime_breakdown_key_ban.py`:

```python
import pytest
from codegenie.eval.runner import Runner
from tests.adv.conftest import adversarial_bench_root, NullSUT, make_plan_for


@pytest.mark.asyncio
async def test_banned_breakdown_key_at_runtime_blocks(adversarial_bench_root):
    """ADR-0008 §Decision: runtime validation rejects banned keys."""
    plan = make_plan_for(adversarial_bench_root, case_id="banned_breakdown_key")
    report = await Runner().execute(plan, system_under_test=NullSUT())

    s = report.per_case[0][1]
    codes = {fm.code for fm in s.failure_modes}
    assert "rubric.unknown_breakdown_key" in codes
    assert "llm_confidence" not in s.breakdown  # persisted score is sanitized
    assert "rubric.unknown_breakdown_key" in report.block_severity_failure_modes
```

`tests/adv/test_rubric_env_read_attempt.py`:

```python
@pytest.mark.asyncio
async def test_rubric_cannot_read_anthropic_api_key(monkeypatch, adversarial_bench_root):
    """ADR-0001 §Decision: SCRUBBED_ENV defeats credential read."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak-do-not-print")
    plan = make_plan_for(adversarial_bench_root, case_id="env_read_attempt")
    report = await Runner().execute(plan, system_under_test=NullSUT())
    fm = report.per_case[0][1].failure_modes[0]
    assert fm.code == "rubric.malformed_output"
    assert "sk-ant-leak" not in (fm.detail or "")
```

`tests/adv/test_rubric_timeout.py`:

```python
@pytest.mark.asyncio
async def test_rubric_timeout_yields_typed_failure(adversarial_bench_root):
    """ADR-0001 §Consequences: rubric.timeout is typed; subprocess reaped."""
    plan = make_plan_for(adversarial_bench_root, case_id="rubric_timeout")
    report = await Runner().execute(plan, system_under_test=NullSUT())
    fm = report.per_case[0][1].failure_modes[0]
    assert fm.code == "rubric.timeout"
    assert fm.severity == "block"
```

`tests/adv/test_poisoned_case_digest_mismatch.py`:

```python
import pytest
from codegenie.eval.errors import BenchCaseDigestMismatch
from codegenie.eval.runner import Runner
from tests.adv.conftest import adversarial_bench_root


def test_poisoned_case_aborts_before_sut(adversarial_bench_root, tmp_path):
    out_dir = tmp_path / "audit"
    chain_before = len(list(out_dir.glob("*.json"))) if out_dir.exists() else 0
    with pytest.raises(BenchCaseDigestMismatch) as exc:
        # Synchronous: plan raises before any SUT invocation.
        Runner().plan(
            task_class_name="adversarial-task-class",
            bench_root=adversarial_bench_root,
            out_dir=out_dir,
            ...,
        )
    assert exc.value.case_id == "poisoned_case"
    chain_after = len(list(out_dir.glob("*.json"))) if out_dir.exists() else 0
    assert chain_after == chain_before  # no new record written
```

`tests/adv/test_malformed_failure_modes_yaml.py`:

```python
def test_malformed_yaml_rejected_at_registration():
    """ADR-0004 §Consequences: fail loud on taxonomy drift."""
    from codegenie.eval.loader import load_task_class
    from codegenie.eval.errors import (
        FailureModeTaxonomyInvalid,  # or whichever typed error is canonical
    )
    with pytest.raises(FailureModeTaxonomyInvalid):
        load_task_class("adversarial-task-class-malformed-yaml",
                        bench_root="tests/fixtures/bench")
```

Run all five drivers; confirm fixture-missing failures. Commit as the red marker.

### Green — make them pass

Author the fixture rubric branches; ensure case `case.toml`s and digests file are wired; drivers assert on report shape. The malformed-yaml fixture is a separate sibling directory so it does not poison the main adversarial-task-class fixture's load path.

### Refactor — clean up

- Promote shared driver helpers (`make_plan_for(...)`, `NullSUT`, `assert_block_severity`, `adversarial_bench_root` fixture) into `tests/adv/conftest.py`.
- Document each scenario's threat-model row in the fixture's `README.md` with a link to its ADR.
- Add `# This test enforces ADR-0001 §Decision` (or whichever ADR) on each driver's docstring.
- Add a single integration test that runs all five non-fence-rejected scenarios in one `Runner.run_eval(...)` invocation and asserts the report carries every expected block-severity code (cross-scenario integration smoke).
- `scripts/seed_adversarial_fixtures.py` is reproducible: running it twice yields identical bytes; commit the resulting stale-digest entry as a frozen artifact.

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
| `tests/adv/conftest.py` | Shared helpers (`NullSUT`, `make_plan_for`, fixture path injection) |
| `scripts/seed_adversarial_fixtures.py` | Reproducible adversarial-fixture builder (idempotent) |

## Out of scope

- **Network-egress prevention** from the rubric — ADR-0001 acknowledges this as a residual risk; not covered until Phase 16's microVM upgrade. Do not add a scenario for it (it would be a known-failing test).
- **RSS / fork-bomb / setrlimit** — same Phase 16 deferral.
- **Process-group-kill** — OQ #4; deferred. Scenario 2 asserts cleanup of the immediate child, not of grandchildren the rubric forked.
- **Mutation testing of `rubric.py`** — Phase 16 (production ADR-0008 / phase ADR-0016 OQ #5).
- **Cassette canary mismatch** (Phase 4 integration drift) — covered by Phase 4's own adversarial tests; not duplicated here.
- **`Canary.mint(seed=...)` Phase 4 amendment** — S2-05.

## Notes for the implementer

- **Treat this fixture as a regression corpus.** Every future ADR that adds a defense should add a scenario here. The fixture is the long-term running record of "what attacks the harness claims to defeat."
- The `failure_modes.yaml` for `adversarial-task-class` must still declare every runner-internal code the runner can emit (`sut.exception`, `sut.timeout`, `sut.cancelled`, `rubric.malformed_output`, `rubric.timeout`, `rubric.unknown_breakdown_key`, `rubric.unknown_failure_mode`) — otherwise loader rejects the task class for taxonomy gaps and you cannot test the runtime defenses.
- Scenario 4's digest mismatch must be reproducible from a script — don't hand-edit `digests.yaml` and forget to commit the stale state. `scripts/seed_adversarial_fixtures.py` (or `conftest.py` `pytest_sessionstart`) is the cleanest way; commit the stale entry deliberately.
- Scenario 5's separate fixture directory avoids loader-import-order coupling. Loading the malformed YAML from the same task class as the runtime scenarios would prevent the runtime tests from running.
- Each driver should fail loudly on the wrong defense — e.g., scenario 1 should fail if the env scrub regresses, not just if the rubric prints something. Assert on the specific credential value being `None`, not on the rubric's exit code alone.
- The `cwd=TemporaryDirectory()` cleanup invariant: after the run, `os.listdir(tempfile.gettempdir())` should not contain stale rubric-tempdirs owned by the test user. Use a `_check_tempdir_clean()` helper from S3-03's adversarial test.
- Resist building a sixth scenario for "rubric makes a network call." That's the residual ADR-0001 calls out by name. Anything that pretends to test it without Phase 16's substrate would be theater.
- The "tagged `held-out`" requirement is subtle: `curation_class="held-out"` on adversarial cases means the fence-CI held-out floor (ADR-0006) is exercised on this corpus too. If you tag them `rag-corpus-derived`, you've created an unprotected hole in the held-out invariant. Re-read ADR-0006 §Decision to confirm.
- The fixture's `min_cases_for_promotion={}` is intentional: this corpus exists to test failure paths, not to be promotable. The empty dict means fence-CI assertion #3 (silver→held-out floor) is vacuously satisfied; the corpus is fence-clean even though every case is a hostile test.
