# Story S3-07 — Adversarial bench fixture portfolio

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready (HARDENED 2026-05-28)
**Effort:** M
**Depends on:**
- **S3-01 HARDENED** — `Runner.plan` signature + `BenchCaseDigestMismatch` unwrapped propagation (Scenario 4).
- **S3-02 HARDENED** — `Runner.execute` required-kwarg signature (`system_under_test`, `rubric_runner`, `cache_dir`, `timeout_per_case_seconds`); `make_stub_plan` seam.
- **S3-03 HARDENED** — `SubprocessRubricRunner` shape + `wall_clock_cap_seconds` kwarg; SCRUBBED_ENV / tempdir-cwd / `python -I -B` isolation (Scenarios 1, 2, 1b).
- **S3-04 HARDENED** — six per-case failure paths; reserved-namespace rewrite (AC-7, Scenario 6); runtime banned-breakdown-key defense (Scenario 3).
- **S2-01 HARDENED** — `load_task_class(name: str, bench_root: Path, *, registry=None)` (Scenario 5).
- **S2-04 HARDENED** — `audit.write_run_record` / `audit.verify` for the chain-unchanged assertion (Scenario 4).
- **S1-01 (amendment precondition)** — must add `FailureModeTaxonomyInvalid` as a 10th typed error (see ADR amendment precondition below).
**ADRs honored:** ADR-0001 (subprocess isolation — env-read attempt + cwd-tempdir wipe), ADR-0004 (taxonomy — malformed failure_modes.yaml), ADR-0008 (breakdown-key substring ban — runtime defense across all four banned substrings), ADR-0006 (curation-class held-out floor — adversarial cases tagged `held-out` as defense-in-depth)

## Validation notes (phase-story-validator, 2026-05-28)

This story was hardened against the actual HARDENED upstream stack (S3-01..S3-06, S2-01, S2-04, S1-01). 24 findings (12 block, 10 harden, 2 nit) folded in. Full report: [`_validation/S3-07-adversarial-bench-fixture.md`](_validation/S3-07-adversarial-bench-fixture.md). The largest structural corrections:
1. Scenarios 1+2 MUST inject `rubric_runner=SubprocessRubricRunner()` — otherwise the SCRUBBED_ENV / tempdir / `python -I -B` defenses are never exercised (the test would run against the in-process stub rubric, which has no isolation).
2. The Scenario-2 timeout source is `Runner.execute(..., timeout_per_case_seconds=0.5)`, NOT `case.rubric_wall_clock_seconds` (S3-03 AC-2 forbids the per-case field as the timeout source).
3. Every `Runner.plan` / `Runner.execute` call uses the canonical `make_adversarial_plan(tmp_path, *, case_id=...)` helper (thin wrapper over `make_stub_plan`) rather than reinventing the call site with placeholder kwargs.
4. `FailureModeTaxonomyInvalid` does not exist in HARDENED S1-01's 9-error set — routed via an explicit S1-01 amendment precondition.
5. Scenario-1 leak detection moves to a sentinel-file mechanic read through a `RecordingSubprocessRubricRunner` (the secret never reaches `FailureMode.detail`, so the old `not in fm.detail` assertion was indirect and could pass for the wrong reason).

### ADR amendment precondition (executor lands in the same PR)

S1-01's typed-error set must widen from 9 to 10 errors by adding `FailureModeTaxonomyInvalid` (raised by the loader when `failure_modes.yaml` declares an out-of-range `severity` or omits `description`). Reusing `TierConfigInvalid` would semantically mislead (tiers ≠ taxonomy); reusing `BenchCaseLoadError` degrades the error→exit-code mapping. The amendment is additive (Open/Closed) and is a precondition for Scenario 5.

## Context

The six per-case failure paths from S3-04 prove the runner *responds correctly* to each typed condition. This story builds the adversarial **bench fixture portfolio** that proves the harness as a whole survives a hostile bench: a malicious-PR-shaped task class designed to exercise every isolation, taxonomy, and digest defense the harness owns.

The fixture lives at `tests/fixtures/bench/adversarial-task-class/` and is driven by `tests/adv/eval/test_*.py`. Each scenario is one attack vector → one expected typed failure. This is the long-term running record of "what attacks the harness claims to defeat" — every future ADR that adds a defense adds one row to `SCENARIOS.md` + one scenario directory + one dispatch entry.

The fixture also doubles as the closest thing to a real bench corpus that exists pre-Phase-5 vuln-remediation backfill, so it must be wire-format clean: it must register correctly, parse correctly, and survive fence-CI (where fence assertions allow — scenario 5's malformed YAML is intentionally fence-rejected, hence the separate sibling fixture directory).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Agentic best practices → Tool-use safety` — the SCRUBBED_ENV / cwd / FS-scope guarantees this fixture stress-tests.
  - `../phase-arch-design.md §Edge cases #3, #4, #5, #7, #11, #12` — the edges this fixture exercises.
  - `../phase-arch-design.md §Testing strategy → Adversarial tests` — `tests/adv/eval/` is the home directory for these drivers.
  - `../phase-arch-design.md §Fixture portfolio` — the canonical list this story implements.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — env-read attempt + cwd-isolation scenarios test the SCRUBBED_ENV / tempdir-wipe claims.
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — malformed YAML scenario tests the taxonomy parser's loud-fail discipline.
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md` — runtime banned-key emission tests the second-layer defense (fence-CI is the first; runtime is the second).
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md` — adversarial cases are tagged `held-out` as defense-in-depth (the floor is vacuously satisfied here via empty `min_cases_for_promotion`).
- **Source design:** `../final-design.md §Risks #2, #4`, `§Failure modes`.
- **Upstream HARDENED contracts (read these before writing red tests):** S3-01 `Runner.plan` signature; S3-02 `Runner.execute` kwarg signature + `tests/helpers/bench.py:make_stub_plan`; S3-03 `SubprocessRubricRunner.run(rubric_path, case, harness_output, *, wall_clock_cap_seconds)`; S3-04 `_RESERVED_RUNNER_CODES` + reserved-namespace rewrite (AC-7); S2-01 `load_task_class` `Path` signature; S2-04 `audit.write_run_record` / `audit.verify`.

### Adversarial-test ownership matrix (phase-arch §Adversarial tests lists 8 + extensions)

| Attack vector | Lands in |
|---|---|
| Env-scrubbed (credential read) | **THIS** — Scenario 1 |
| cwd-tempdir isolation + wipe | **THIS** — Scenario 1b |
| Rubric timeout reaped | **THIS** — Scenario 2 |
| Banned breakdown key at runtime | **THIS** — Scenario 3 (all 4 ADR-0008 substrings) |
| Case poisoning (digest mismatch) | **THIS** — Scenario 4 |
| Malformed `failure_modes.yaml` | **THIS** — Scenario 5 |
| Reserved-namespace code smuggling | **THIS** — Scenario 6 |
| LLM-field smuggling (`extra="forbid"`) | S1-02 |
| Breakdown-key smuggling at parse time | S7-01 fence (assertion #5) |
| Audit-chain tamper | S2-04 |
| Promotion-apply raises | S4-04 |
| Cost-ledger pollution | S2-06 |

## Goal

Build `tests/fixtures/bench/adversarial-task-class/` covering six attack scenarios, plus the matching `tests/adv/eval/test_*.py` drivers that assert each scenario produces the typed failure the harness's defenses promise — using the actual HARDENED upstream contracts and the established structural seams.

## Acceptance criteria

- [ ] Fixture directory `tests/fixtures/bench/adversarial-task-class/` exists with the standard task-class shape: `registration.py`, `rubric.py`, `breakdown_keys.py`, `failure_modes.yaml`, `cases/digests.yaml`, plus a `SCENARIOS.md` defense-regression table and case directories named for each scenario.
- [ ] `SCENARIOS.md` is a fixed-format table with columns `(scenario_id, attack_vector, defended_by_ADR, driver_path, expected_failure_code)` — one row per scenario. Adding a future defense = one row + one scenario dir + one `_SCENARIO_DISPATCH` entry.
- [ ] **Scenario 1 — Env-read attempt** (`rubric_runner=SubprocessRubricRunner()`). Rubric writes `os.environ.get("ANTHROPIC_API_KEY")` (or the literal `NOTPRESENT` when absent) into a `sentinel` file inside its cwd-tempdir, then `sys.exit(1)`. Driver: `tests/adv/eval/test_rubric_env_read_attempt.py`. Assertions: (a) the `FailureMode` carries `code="rubric.malformed_output"` because the rubric exits non-zero; (b) a `RecordingSubprocessRubricRunner` snapshots the tempdir BEFORE teardown and the test asserts the captured sentinel bytes == `b"NOTPRESENT"` (a wrong impl that passes parent env would write the real secret and fail); (c) `fm.detail` length ≤ 200 (S3-04 truncation guarantee); (d) the run continues.
- [ ] **Scenario 1b — cwd-tempdir isolation + wipe** (`RecordingSubprocessRubricRunner`). After the run, the recorded tempdir path does not exist (wiped on `with` exit, even though the rubric raised), and the sentinel file is unreachable from the parent test. Driver: `tests/adv/eval/test_rubric_subprocess_cwd_isolated.py` (or folded into Scenario 1's driver).
- [ ] **Scenario 2 — Rubric timeout** (`rubric_runner=SubprocessRubricRunner()`). Rubric calls `time.sleep(120)`; the runner caps via `Runner().execute(..., timeout_per_case_seconds=0.5)` (NOT `case.rubric_wall_clock_seconds`). Driver: `tests/adv/eval/test_rubric_timeout.py`. Assertions: (a) `FailureMode(code="rubric.timeout", severity="block")` recorded; (b) measured wall-clock ≤ 5 s (the runner enforced the cap, not the rubric); (c) the `RecordingSubprocessRubricRunner`'s recorded tempdir does not exist after `run()` returns (single deterministic path, no glob over `tempfile.gettempdir()`).
- [ ] **Scenario 3 — Banned breakdown key emitted at runtime** (rubric-runner-agnostic). Rubric returns `BenchScore.breakdown` carrying a banned substring key. Parameterized across all four ADR-0008 banned substrings: `["llm_confidence", "model_says_pass", "self_reported_score", "raw_confidence"]`. Driver: `tests/adv/eval/test_runtime_breakdown_key_ban.py`. Assertions per variant: `FailureMode(code="rubric.unknown_breakdown_key", severity="block", detail=<the banned key>)`; the banned key is **not present** in the persisted `BenchScore.breakdown`.
- [ ] **Scenario 4 — Poisoned case (digest mismatch)** (no rubric — plan-time). A case directory's `case.toml` was edited but `cases/digests.yaml` was not. The test first **seeds** the audit chain with one valid `audit.write_run_record(...)` (asserts `chain_before == 1`). Driver: `tests/adv/eval/test_poisoned_case_digest_mismatch.py`. Assertions: `BenchCaseDigestMismatch(case_id, expected_blake3, computed_blake3)` raised at plan time via `make_adversarial_plan(tmp_path, case_id="poisoned_case")` (S3-01); the run aborts before any SUT call; `chain_after == 1` AND `audit.verify(out_dir).ok is True` (the prior record survives).
- [ ] **Scenario 5 — Malformed `failure_modes.yaml`** (no rubric — registration-time). Lives in sibling fixture `tests/fixtures/bench/adversarial-task-class-malformed-yaml/`. YAML declares one entry with `severity: critical` (not in `{block, warn, info}`) and another with a missing `description`. Driver: `tests/adv/eval/test_malformed_failure_modes_yaml.py`. Assertion: `load_task_class("adversarial-task-class-malformed-yaml", bench_root=Path("tests/fixtures/bench"), registry=TaskClassRegistry())` raises `FailureModeTaxonomyInvalid` (S1-01 amendment); the run never starts. Uses a fresh `TaskClassRegistry()` to avoid cross-test pollution.
- [ ] **Scenario 6 — Reserved-namespace code smuggling** (rubric-runner-agnostic). Rubric emits `BenchScore(failure_modes=(FailureMode(code="sut.exception", severity="warn", detail="fake"),))`. Driver: `tests/adv/eval/test_reserved_namespace_smuggling.py`. Assertion: the runner replaces it with `FailureMode(code="rubric.unknown_failure_mode", severity="block", detail="reserved_code:sut.exception")` per S3-04 AC-7 (a buggy rubric cannot fabricate runner-internal events).
- [ ] Each scenario asserts `len(report.per_case[0][1].failure_modes) == 1` explicitly (no brittle first-element-of-many indexing).
- [ ] Each scenario asserts the expected structlog event-id appears via `structlog.testing.capture_logs()` (e.g., Scenario 4 emits `loader.case_digest_mismatch`).
- [ ] **Metamorphic determinism:** running the full scenario suite twice (cold cache, fresh `tmp_path`) produces identical fixture digests AND identical per-scenario block-severity tuples.
- [ ] All drivers are runnable via `pytest tests/adv/eval/` in under 30 s combined wall-clock; no `@pytest.mark.asyncio` markers (the repo's `asyncio_mode = "auto"` makes them redundant — convention-match S3-02/S3-04).
- [ ] Adversarial fixture cases are tagged `curation_class="held-out"` so the *naming convention* matches the fence-protected one. The fence-CI held-out floor (ADR-0006 assertion #3) is **vacuously** satisfied here via `min_cases_for_promotion={}` — the tagging is defense-in-depth, NOT exercise of the floor. (Notes-for-implementer pins this so a future curator doesn't misread it.)
- [ ] `failure_modes.yaml` for `adversarial-task-class` declares all seven runner-internal codes (`sut.exception`, `sut.timeout`, `sut.cancelled`, `rubric.malformed_output`, `rubric.timeout`, `rubric.unknown_breakdown_key`, `rubric.unknown_failure_mode`) — defense-in-depth so a rubric may deliberately emit them and the reserved-namespace defense still catches (Scenario 6).
- [ ] `scripts/seed_adversarial_fixtures.py` is idempotent: running it twice on a clean fixture yields byte-identical `cases/digests.yaml` and byte-identical case directory contents (assert via a `tar`-serialized `hashlib.sha256` equality across two runs).
- [ ] `mypy --strict`, `ruff format --check`, `ruff check` clean on touched files; no skipped tests; each driver's docstring explicitly cites the ADR that promises the defense.
- [ ] All red tests in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

1. Create `tests/fixtures/bench/adversarial-task-class/`:
   - `registration.py`: `@register_task_class("adversarial-task-class", bench_path=..., min_cases_for_promotion={})` (no tiers — fence-CI assertion #3 is then vacuously satisfied).
   - `rubric.py`: a `if __name__ == "__main__"` entrypoint that reads stdin, parses the case_id, and dispatches via a module-level `_SCENARIO_DISPATCH: Final[Mapping[str, Callable[..., None]]] = {"env_read_attempt": _do_env_read_attempt, "rubric_timeout": _do_rubric_timeout, ...}` (Open/Closed — adding a scenario is one entry + one function, zero edits to dispatch logic; mirrors the grammar-kernel `_DISPATCH` and `_REFLECTION_QUERIES`/`_LOCKFILE_PRECEDENCE` catalogs).
   - `breakdown_keys.py`: `class BreakdownKey(StrEnum): PASSED = "passed"` (one valid key).
   - `failure_modes.yaml`: minimal valid taxonomy declaring the seven runner-internal codes.
   - `cases/`: case dirs (one per scenario); one is intentionally digest-mismatched.
   - `cases/digests.yaml`: valid entries + 1 stale entry for scenario 4.
   - `SCENARIOS.md`: the fixed-format defense-regression table (F-DP-3).
2. For scenario 5, store a second `tests/fixtures/bench/adversarial-task-class-malformed-yaml/` mirror with `failure_modes.yaml` carrying `severity: critical` on one entry and a missing `description` on another; loader-level test loads it directly with a fresh `TaskClassRegistry()`.
3. Drivers live in a NEW `tests/adv/eval/` subdirectory (NOT the existing `tests/adv/`, which hosts the gather-pipeline adversarial suite + an autouse `_disable_cli_configure_logging` fixture irrelevant here). Each driver imports the fixture path, sets up the SUT (`NullSUT` returning empty harness_output), invokes `Runner().execute(...)` (or `Runner().plan(...)` for scenarios 4/5), and asserts on the resulting `BenchRunReport` or the raised exception.
4. Shared helpers — consume existing seams, do NOT duplicate call sites:
   - `make_adversarial_plan(tmp_path, *, case_id) -> RunPlan` in `tests/helpers/bench.py` — a thin wrapper over `make_stub_plan` bound to the adversarial bench root (F-DP-1).
   - `RecordingSubprocessRubricRunner` in `tests/helpers/rubrics.py` — a `SubprocessRubricRunner` subclass that records (a) the tempdir path it created and (b) a snapshot of its contents BEFORE teardown; reusable for cwd-isolation + leak-detection (F-DP-4).
   - `NullSUT` + `adversarial_bench_root` fixture in `tests/adv/eval/conftest.py`.
5. `scripts/seed_adversarial_fixtures.py` — operator tool to regenerate the stale-digest case deterministically; commit the stale entry deliberately, do not hand-edit. Idempotent (byte-stable).

## TDD plan — red / green / refactor

### Red — write failing tests first

`tests/adv/eval/test_runtime_breakdown_key_ban.py`:

```python
import pytest
from codegenie.eval.runner import Runner
from tests.adv.eval.conftest import NullSUT
from tests.helpers.bench import make_adversarial_plan
from tests.helpers.rubrics import InProcessStubRubric  # banned-key check is runner-side


@pytest.mark.parametrize(
    "banned_key",
    ["llm_confidence", "model_says_pass", "self_reported_score", "raw_confidence"],
)
async def test_banned_breakdown_key_at_runtime_blocks(tmp_path, banned_key):
    """ADR-0008 §Decision: runtime validation rejects banned-substring breakdown keys."""
    plan = make_adversarial_plan(tmp_path, case_id="banned_breakdown_key")
    report = await Runner().execute(
        plan,
        system_under_test=NullSUT(),
        rubric_runner=InProcessStubRubric(breakdown={banned_key: 0.9}),
        cache_dir=tmp_path / "cache",
        timeout_per_case_seconds=5.0,
    )
    s = report.per_case[0][1]
    assert len(s.failure_modes) == 1
    fm = s.failure_modes[0]
    assert fm.code == "rubric.unknown_breakdown_key"
    assert fm.detail == banned_key
    assert banned_key not in s.breakdown  # persisted score is sanitized
    assert "rubric.unknown_breakdown_key" in report.block_severity_failure_modes
```

`tests/adv/eval/test_rubric_env_read_attempt.py`:

```python
from codegenie.eval.rubric import SubprocessRubricRunner
from codegenie.eval.runner import Runner
from tests.adv.eval.conftest import NullSUT
from tests.helpers.bench import make_adversarial_plan
from tests.helpers.rubrics import RecordingSubprocessRubricRunner


async def test_rubric_cannot_read_anthropic_api_key(monkeypatch, tmp_path):
    """ADR-0001 §Decision: SCRUBBED_ENV defeats credential read."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak-do-not-print")
    plan = make_adversarial_plan(tmp_path, case_id="env_read_attempt")
    runner = RecordingSubprocessRubricRunner()  # snapshots cwd-tempdir before teardown
    report = await Runner().execute(
        plan,
        system_under_test=NullSUT(),
        rubric_runner=runner,
        cache_dir=tmp_path / "cache",
        timeout_per_case_seconds=5.0,
    )
    s = report.per_case[0][1]
    assert len(s.failure_modes) == 1
    fm = s.failure_modes[0]
    assert fm.code == "rubric.malformed_output"   # rubric exits non-zero
    assert len(fm.detail or "") <= 200             # S3-04 truncation guarantee
    # Primary leak assertion: the sentinel the rubric wrote inside its scrubbed cwd
    assert runner.sentinel_bytes == b"NOTPRESENT"  # parent env did NOT reach the child
    # cwd-tempdir wiped on exit even though the rubric raised
    assert not runner.recorded_tempdir.exists()
```

`tests/adv/eval/test_rubric_timeout.py`:

```python
import time

from codegenie.eval.runner import Runner
from tests.adv.eval.conftest import NullSUT
from tests.helpers.bench import make_adversarial_plan
from tests.helpers.rubrics import RecordingSubprocessRubricRunner


async def test_rubric_timeout_yields_typed_failure(tmp_path):
    """ADR-0001 §Consequences: rubric.timeout is typed; subprocess reaped; cwd wiped."""
    plan = make_adversarial_plan(tmp_path, case_id="rubric_timeout")
    runner = RecordingSubprocessRubricRunner()
    t0 = time.monotonic()
    report = await Runner().execute(
        plan,
        system_under_test=NullSUT(),
        rubric_runner=runner,
        cache_dir=tmp_path / "cache",
        timeout_per_case_seconds=0.5,   # runner enforces the cap, NOT the rubric
    )
    elapsed = time.monotonic() - t0
    s = report.per_case[0][1]
    assert len(s.failure_modes) == 1
    assert s.failure_modes[0].code == "rubric.timeout"
    assert s.failure_modes[0].severity == "block"
    assert elapsed <= 5.0                        # the 0.5s cap fired, not the 120s sleep
    assert not runner.recorded_tempdir.exists()  # single deterministic path, no glob
```

`tests/adv/eval/test_poisoned_case_digest_mismatch.py`:

```python
import pytest
from codegenie.eval import audit
from codegenie.eval.errors import BenchCaseDigestMismatch
from codegenie.eval.runner import Runner
from tests.helpers.bench import make_adversarial_plan, make_stub_run_report


def test_poisoned_case_aborts_before_sut(tmp_path):
    """ADR-0004 §Risks #2: digest mismatch aborts at plan time; audit chain untouched."""
    out_dir = tmp_path / "audit"
    out_dir.mkdir()
    audit.write_run_record(out_dir, make_stub_run_report())   # seed the chain
    assert len(list(out_dir.glob("*.json"))) == 1

    with pytest.raises(BenchCaseDigestMismatch) as exc:
        make_adversarial_plan(tmp_path, case_id="poisoned_case", out_dir=out_dir)

    assert exc.value.case_id == "poisoned_case"
    assert len(list(out_dir.glob("*.json"))) == 1   # no new record written
    assert audit.verify(out_dir).ok is True          # the seeded record survives
```

`tests/adv/eval/test_malformed_failure_modes_yaml.py`:

```python
from pathlib import Path

import pytest

from codegenie.eval.errors import FailureModeTaxonomyInvalid  # S1-01 amendment
from codegenie.eval.loader import load_task_class
from codegenie.eval.registry import TaskClassRegistry


def test_malformed_yaml_rejected_at_registration():
    """ADR-0004 §Consequences: fail loud on taxonomy drift; run never starts."""
    with pytest.raises(FailureModeTaxonomyInvalid):
        load_task_class(
            "adversarial-task-class-malformed-yaml",
            bench_root=Path("tests/fixtures/bench"),
            registry=TaskClassRegistry(),   # fresh registry; no cross-test pollution
        )
```

`tests/adv/eval/test_reserved_namespace_smuggling.py`:

```python
from codegenie.eval.runner import Runner
from tests.adv.eval.conftest import NullSUT
from tests.helpers.bench import make_adversarial_plan
from tests.helpers.rubrics import InProcessStubRubric


async def test_rubric_cannot_fabricate_runner_internal_code(tmp_path):
    """S3-04 AC-7: a buggy rubric emitting a reserved code is rewritten, not trusted."""
    plan = make_adversarial_plan(tmp_path, case_id="reserved_code_smuggling")
    report = await Runner().execute(
        plan,
        system_under_test=NullSUT(),
        rubric_runner=InProcessStubRubric(emit_code="sut.exception", emit_severity="warn"),
        cache_dir=tmp_path / "cache",
        timeout_per_case_seconds=5.0,
    )
    s = report.per_case[0][1]
    assert len(s.failure_modes) == 1
    fm = s.failure_modes[0]
    assert fm.code == "rubric.unknown_failure_mode"
    assert fm.severity == "block"
    assert fm.detail == "reserved_code:sut.exception"
```

Run all drivers; confirm fixture-missing failures. Commit as the red marker.

### Green — make them pass

Author the fixture rubric's `_SCENARIO_DISPATCH` branches; ensure case `case.toml`s and digests file are wired; drivers assert on report shape. The malformed-yaml fixture is a separate sibling directory so it does not poison the main adversarial-task-class fixture's load path. Land the S1-01 `FailureModeTaxonomyInvalid` amendment in the same PR.

### Refactor — clean up

- Confirm shared helpers live in their canonical homes: `make_adversarial_plan` → `tests/helpers/bench.py`; `RecordingSubprocessRubricRunner` → `tests/helpers/rubrics.py`; `NullSUT` + `adversarial_bench_root` → `tests/adv/eval/conftest.py`.
- `SCENARIOS.md` carries the threat-model table; each driver docstring cites its ADR.
- Add a single integration test that runs all non-fence-rejected scenarios in one `Runner.execute(...)` invocation and asserts the report carries every expected block-severity code (cross-scenario smoke).
- Add the metamorphic-determinism test (run the suite twice; assert identical fixture digests + identical per-scenario block-severity tuples).
- `scripts/seed_adversarial_fixtures.py` is reproducible: running it twice yields byte-identical output; commit the resulting stale-digest entry as a frozen artifact.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/bench/adversarial-task-class/**` | New fixture corpus (6 scenarios) + `SCENARIOS.md` |
| `tests/fixtures/bench/adversarial-task-class-malformed-yaml/**` | Scenario 5 mirror with malformed YAML |
| `tests/adv/eval/conftest.py` | `NullSUT`, `adversarial_bench_root` fixture (eval-harness adversarial home, distinct from gather-pipeline `tests/adv/`) |
| `tests/adv/eval/test_rubric_env_read_attempt.py` | Scenario 1 (+1b cwd-isolation) driver |
| `tests/adv/eval/test_rubric_subprocess_cwd_isolated.py` | Scenario 1b driver (if not folded into Scenario 1) |
| `tests/adv/eval/test_rubric_timeout.py` | Scenario 2 driver |
| `tests/adv/eval/test_runtime_breakdown_key_ban.py` | Scenario 3 driver (parameterized × 4 banned substrings) |
| `tests/adv/eval/test_poisoned_case_digest_mismatch.py` | Scenario 4 driver |
| `tests/adv/eval/test_malformed_failure_modes_yaml.py` | Scenario 5 driver |
| `tests/adv/eval/test_reserved_namespace_smuggling.py` | Scenario 6 driver |
| `tests/helpers/bench.py` | Additive `make_adversarial_plan(tmp_path, *, case_id)` over `make_stub_plan` |
| `tests/helpers/rubrics.py` | Additive `RecordingSubprocessRubricRunner` |
| `src/codegenie/eval/errors.py` | S1-01 amendment — add `FailureModeTaxonomyInvalid` (10th typed error) |
| `scripts/seed_adversarial_fixtures.py` | Reproducible, idempotent adversarial-fixture builder |

## Out of scope

- **Network-egress prevention** from the rubric — ADR-0001 acknowledges this as a residual risk; not covered until Phase 16's microVM upgrade. Do not add a scenario for it (it would be a known-failing test / theater).
- **RSS / fork-bomb / setrlimit** — same Phase 16 deferral.
- **Process-group-kill** — OQ #4; deferred. Scenario 2 asserts cleanup of the immediate child, not of grandchildren the rubric forked.
- **Mutation testing of `rubric.py`** — Phase 16 (production ADR-0008 / phase ADR-0016 OQ #5).
- **Hypothesis-property loader hardening** (`test_loader_taxonomy_mutations.py` — programmatic mutation of valid YAML asserting every mutation is rejected) — future hardening; this story is the fixed-attack-vector portfolio.
- **Cassette canary mismatch** (Phase 4 integration drift) — covered by Phase 4's own adversarial tests; not duplicated here.
- **`Canary.mint(seed=...)` Phase 4 amendment** — S2-05.
- **`ScenarioId` newtype** — not introduced (Rule 2 — three consumers not yet reached; see Notes).

## Notes for the implementer

- **Treat this fixture as a regression corpus.** `SCENARIOS.md` is the structural long-term record of "what attacks the harness claims to defeat" — every future ADR that adds a defense adds one row + one scenario dir + one `_SCENARIO_DISPATCH` entry. Prefer the data-driven table over prose.
- **Scenarios 1, 2 MUST use `SubprocessRubricRunner` (via `RecordingSubprocessRubricRunner`).** Using the in-process stub rubric would silently skip the SCRUBBED_ENV / tempdir / `python -I -B` isolation the scenarios claim to test. Scenarios 3 and 6 are runner-side (rubric-runner-agnostic); Scenarios 4, 5 are plan/registration-time (no rubric).
- **Scenario 2's timeout source is `Runner.execute(..., timeout_per_case_seconds=...)`, NOT `case.rubric_wall_clock_seconds`** (S3-03 AC-2 forbids the per-case field as the source). Assert both the typed `rubric.timeout` code AND elapsed wall-clock ≤ 5 s so a regression that ignores the cap fails.
- **Scenario 1 leak detection uses a sentinel file, not `fm.detail`.** The secret never reaches `FailureMode.detail`; the rubric writes `os.environ.get("ANTHROPIC_API_KEY", "NOTPRESENT")` into a file in its scrubbed cwd-tempdir, and `RecordingSubprocessRubricRunner` snapshots it before teardown. A wrong impl that passes parent env would write the real secret and fail.
- **The `failure_modes.yaml` must declare every runner-internal code** (`sut.exception`, `sut.timeout`, `sut.cancelled`, `rubric.malformed_output`, `rubric.timeout`, `rubric.unknown_breakdown_key`, `rubric.unknown_failure_mode`) — defense-in-depth. Runner-emitted codes BYPASS taxonomy resolution (S3-04 AC-8), so this declaration exists so a rubric may *deliberately* emit them and the reserved-namespace defense (Scenario 6) still catches.
- **`min_cases_for_promotion={}` is intentional.** The `held-out` tagging is defense-in-depth — the ADR-0006 fence floor (assertion #3) is *vacuously* satisfied here, NOT exercised. Do not read the held-out AC as "the floor was exercised on this corpus."
- **Adversarial cases are cassette-free** (mirroring `stub-task-class` per phase-arch §Fixture portfolio). The `cassette_root` kwarg can be a no-op path; `NullSUT` does not go through cassette replay.
- **Scenario 4's digest mismatch must be reproducible from a script** — don't hand-edit `digests.yaml` and forget to commit the stale state. `scripts/seed_adversarial_fixtures.py` is the cleanest way; commit the stale entry deliberately. A `conftest.py` `pytest_sessionstart` hook is a future alternative (F-DP-5) — do not introduce a third path now.
- **Each driver should fail loudly on the wrong defense** — Scenario 1 fails if the env scrub regresses (sentinel ≠ `NOTPRESENT`), not merely if the rubric prints something.
- **`ScenarioId = NewType("ScenarioId", str)` future trigger:** once `SCENARIOS.md` crosses 3+ readers (rubric dispatch, fence test, doc generator), the newtype pays. Not yet — bare strings today.
- **Phase 16 microVM:** when the new isolation class lands, Scenarios 1+2 grow a sibling `@pytest.mark.parametrize("rubric_runner", [SubprocessRubricRunner, MicroVMRubricRunner])`. Surface as a Note then; do not introduce now.
