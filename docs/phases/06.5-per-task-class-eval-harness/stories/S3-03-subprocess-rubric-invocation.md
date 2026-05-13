# Story S3-03 — Subprocess rubric invocation with scrubbed env

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (asyncio fan-out + aggregator), S1-04 (Rubric Protocol)
**ADRs honored:** ADR-0001 (subprocess + scrubbed env isolation — load-bearing), Phase 5 ADR-0012 (env allowlist discipline), ADR-0004 (rubric subprocess failures map to typed `FailureMode`s, not exceptions)

## Context

The rubric is control-plane code: its `BenchScore` feeds the promotion gate, which determines whether a task class graduates. The rubric is also untrusted in the same sense bench-case data is — it lives at `bench/{task-class}/rubric.py`, a CODEOWNERS-gated path that any contributor may PR. ADR-0001 picks subprocess + scrubbed env (not in-process, not microVM) as the load-bearing isolation posture for Phase 6.5.

This story implements `SubprocessRubricRunner` — the `rubric_runner` callable that S3-02's worker injects. The contract: spawn `python bench/{task-class}/rubric.py` with `env=SCRUBBED_ENV`, `cwd=tempfile.TemporaryDirectory()`, stdin = JSON `{case, harness_output}`, stdout = `BenchScore` JSON, timeout = `case.rubric_wall_clock_seconds or 60`.

The adversarial test is the proof: a hand-crafted rubric that attempts `os.environ.get("ANTHROPIC_API_KEY")` must receive `None`. That single test is the structural enforcement of ADR-0001's "defeats credential read" claim.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Agentic best practices → Tool-use safety` — full specification of `SCRUBBED_ENV`, `cwd`, FS scope, resource caps, residual risk (network egress not blocked).
  - `../phase-arch-design.md §Edge cases #3, #4, #5` — rubric crash (non-zero exit), timeout, malformed JSON. Each maps to a `FailureMode(severity="block")` and the run continues.
  - `../phase-arch-design.md §Components → rubric.py` — "two call sites, two execution models" (bench-author tests use in-process; runner never does).
  - `../phase-arch-design.md §Scenarios → Scenario 2` background; this story owns the subprocess invocation that scenario relies on.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — the canonical isolation contract. Read §Decision and §Consequences fully.
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — the rubric subprocess failure surface is **typed `FailureMode`**, not Python exceptions. The runner does not re-raise.
- **Phase 5 ADR:** `../../05-sandbox-trust-gates/ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — `env_allowlist.filter({})` precedent. The SCRUBBED_ENV here mirrors that discipline.
- **Source design:** `../final-design.md §Components → SubprocessRubricRunner` — "asyncio.create_subprocess_exec with env={}, cwd=<scratch>, stdin=PIPE, stdout=PIPE, stderr=PIPE."

## Goal

Land `SubprocessRubricRunner.__call__(case, harness_output) -> BenchScore` that invokes the rubric across a process boundary with a scrubbed environment, an isolated tempdir `cwd`, JSON stdin/stdout, and a per-case wall-clock timeout — defeating credential read and arbitrary FS write outside the wiped tempdir.

## Acceptance criteria

- [ ] `src/codegenie/eval/rubric_subprocess.py` exports `SubprocessRubricRunner` (class with `async __call__`) and `SCRUBBED_ENV` (module-level `Mapping[str, str]` constant).
- [ ] `SCRUBBED_ENV` contains exactly: `PATH="/usr/bin:/bin"`, `LANG="C.UTF-8"`, `PYTHONHASHSEED="0"`, `PYTHONIOENCODING="utf-8"`. No `ANTHROPIC_API_KEY`, no `AWS_*`, no `HOME`, no `USER`, no `OPENAI_API_KEY`. A test enumerates exactly these four keys.
- [ ] `SCRUBBED_ENV` is wrapped in `types.MappingProxyType` — mutation raises `TypeError`; a test asserts this.
- [ ] Invocation uses `asyncio.create_subprocess_exec(sys.executable, str(rubric_path), env=dict(SCRUBBED_ENV), cwd=str(tmpdir), stdin=PIPE, stdout=PIPE, stderr=PIPE)`; `tempfile.TemporaryDirectory()` provides `tmpdir`; tempdir is removed on context exit even if the subprocess raised.
- [ ] Timeout: `await asyncio.wait_for(proc.communicate(input=stdin_bytes), timeout=case.rubric_wall_clock_seconds or 60.0)`. On `asyncio.TimeoutError`: `proc.kill(); await proc.wait()`; return `BenchScore(passed=False, score=0.0, breakdown={}, failure_modes=(FailureMode(code="rubric.timeout", severity="block"),), cost_usd=0.0, wall_clock_ms=<measured>)`.
- [ ] Non-zero exit: return `BenchScore(passed=False, ..., failure_modes=(FailureMode(code="rubric.malformed_output", severity="block", detail=stderr_bytes[:200].decode("utf-8", "replace")),))`.
- [ ] Malformed stdout (Pydantic `ValidationError` on `BenchScore.model_validate_json`): same `FailureMode(code="rubric.malformed_output", severity="block", detail=<short validation summary>)`.
- [ ] **Adversarial guarantee**: a fixture rubric that prints `os.environ.get("ANTHROPIC_API_KEY")` returns `None` from inside the subprocess — even when the parent process has the env var set to a known secret. The test asserts (a) `ANTHROPIC_API_KEY` is not in the subprocess's environ keys, (b) the secret value does not appear anywhere in the captured stderr.
- [ ] Tempdir cleanup: after `__call__` returns, the tempdir path does not exist (asserted via a stub rubric that writes its `os.getcwd()` to a known external path and a follow-up `Path.exists` check).
- [ ] `mypy --strict`, `ruff format --check`, `ruff check` clean.
- [ ] The runner does **not** re-raise on rubric subprocess failure; the `BenchScore` carries the failure as `FailureMode` and the run continues (verified by an integration test running two cases, one passing, one with a crashing rubric — both produce per-case entries).
- [ ] All red tests in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

1. Create `src/codegenie/eval/rubric_subprocess.py`.
2. Define `SCRUBBED_ENV: Mapping[str, str]` as a module constant via `types.MappingProxyType({"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"})`.
3. Define `class SubprocessRubricRunner:` with `__init__(self, rubric_root: Path, timeout_default: float = 60.0)`.
4. Implement `async def __call__(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore:`. Body:
   - `rubric_path = self.rubric_root / case.task_class / "rubric.py"`.
   - `stdin_payload = json.dumps({"case": case.model_dump(mode="json"), "harness_output": harness_output}).encode("utf-8")`.
   - `timeout = case.rubric_wall_clock_seconds or self.timeout_default`.
   - `start_ns = time.monotonic_ns()`.
   - `with tempfile.TemporaryDirectory() as tmpdir:` —
     - `proc = await asyncio.create_subprocess_exec(sys.executable, str(rubric_path), env=dict(SCRUBBED_ENV), cwd=tmpdir, stdin=PIPE, stdout=PIPE, stderr=PIPE)`.
     - `try: stdout, stderr = await asyncio.wait_for(proc.communicate(stdin_payload), timeout=timeout)`.
     - `except asyncio.TimeoutError: proc.kill(); await proc.wait();` return timeout `BenchScore`.
   - `wall_clock_ms = (time.monotonic_ns() - start_ns) // 1_000_000`.
   - `if proc.returncode != 0:` return malformed `BenchScore` with stderr detail (`stderr[:200].decode("utf-8", "replace")`).
   - `try: score = BenchScore.model_validate_json(stdout)`.
   - `except pydantic.ValidationError as e:` return malformed `BenchScore` with validation-error summary.
   - Return `score.model_copy(update={"wall_clock_ms": wall_clock_ms})` (preserve rubric-reported score; override measured wall-clock).
5. Wire `SubprocessRubricRunner` into `Runner.run_eval` as the default `rubric_runner` (S3-02 exposed the injection seam).

## TDD plan — red / green / refactor

### Red — write failing tests first

Test file: `tests/unit/test_rubric_subprocess.py`

```python
import asyncio
import os
import sys
import json
import pytest
from pathlib import Path
from codegenie.eval.rubric_subprocess import SubprocessRubricRunner, SCRUBBED_ENV
from codegenie.eval.models import BenchScore, FailureMode
from tests.helpers.bench import make_bench_case


def test_scrubbed_env_contains_exactly_four_keys():
    """Allowlist discipline (Phase 5 ADR-0012 mirror)."""
    assert set(SCRUBBED_ENV) == {"PATH", "LANG", "PYTHONHASHSEED", "PYTHONIOENCODING"}
    assert "ANTHROPIC_API_KEY" not in SCRUBBED_ENV
    assert "AWS_ACCESS_KEY_ID" not in SCRUBBED_ENV
    assert "HOME" not in SCRUBBED_ENV
    assert "USER" not in SCRUBBED_ENV


def test_scrubbed_env_is_immutable():
    with pytest.raises(TypeError):
        SCRUBBED_ENV["EVIL"] = "1"  # MappingProxyType rejects


@pytest.mark.asyncio
async def test_happy_path_subprocess_rubric(tmp_path):
    """Rubric prints a valid BenchScore; runner returns it (with measured wall_clock_ms)."""
    rubric_root = tmp_path / "bench"
    (rubric_root / "stub-task-class").mkdir(parents=True)
    rubric = rubric_root / "stub-task-class" / "rubric.py"
    rubric.write_text(
        "import json, sys; _ = json.loads(sys.stdin.read());"
        "out = {'passed': True, 'score': 0.75, 'breakdown': {}, 'failure_modes': [],"
        " 'cost_usd': 0.0, 'wall_clock_ms': 0};"
        "sys.stdout.write(json.dumps(out))"
    )
    runner = SubprocessRubricRunner(rubric_root=rubric_root)
    score = await runner(make_bench_case(task_class="stub-task-class"), {"any": "thing"})
    assert score.passed is True
    assert score.score == 0.75
    assert score.failure_modes == ()
    assert score.wall_clock_ms > 0  # measured by runner, not rubric


@pytest.mark.asyncio
async def test_subprocess_cannot_read_anthropic_api_key(tmp_path, monkeypatch):
    """Load-bearing ADR-0001 guarantee."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-do-not-leak")
    rubric_root = tmp_path / "bench"
    (rubric_root / "stub-task-class").mkdir(parents=True)
    rubric = rubric_root / "stub-task-class" / "rubric.py"
    rubric.write_text(
        "import os, sys, json;"
        "keys = sorted(os.environ.keys());"
        "leak = os.environ.get('ANTHROPIC_API_KEY');"
        "sys.stderr.write(json.dumps({'keys': keys, 'leak': leak}));"
        "sys.exit(2)"
    )
    runner = SubprocessRubricRunner(rubric_root=rubric_root)
    score = await runner(make_bench_case(task_class="stub-task-class"), {})
    # Non-zero exit → malformed_output; detail carries stderr first 200 bytes.
    assert score.passed is False
    assert len(score.failure_modes) == 1
    fm = score.failure_modes[0]
    assert fm.code == "rubric.malformed_output"
    assert fm.severity == "block"
    # The leaked key must NOT appear in the captured detail.
    assert "sk-ant-secret" not in (fm.detail or "")
    assert '"leak": null' in (fm.detail or "")
    # And ANTHROPIC_API_KEY is not in the subprocess's enumerated keys.
    assert "ANTHROPIC_API_KEY" not in (fm.detail or "")


@pytest.mark.asyncio
async def test_subprocess_timeout_maps_to_failure_mode(tmp_path):
    rubric_root = tmp_path / "bench"
    (rubric_root / "stub-task-class").mkdir(parents=True)
    rubric = rubric_root / "stub-task-class" / "rubric.py"
    rubric.write_text("import time; time.sleep(60)")
    runner = SubprocessRubricRunner(rubric_root=rubric_root, timeout_default=0.5)
    score = await runner(make_bench_case(task_class="stub-task-class"), {})
    assert score.failure_modes[0].code == "rubric.timeout"
    assert score.failure_modes[0].severity == "block"
    assert score.passed is False


@pytest.mark.asyncio
async def test_malformed_json_stdout_maps_to_failure_mode(tmp_path):
    rubric_root = tmp_path / "bench"
    (rubric_root / "stub-task-class").mkdir(parents=True)
    rubric = rubric_root / "stub-task-class" / "rubric.py"
    rubric.write_text("import sys; sys.stdout.write('not json')")
    runner = SubprocessRubricRunner(rubric_root=rubric_root)
    score = await runner(make_bench_case(task_class="stub-task-class"), {})
    assert score.failure_modes[0].code == "rubric.malformed_output"
    assert score.failure_modes[0].severity == "block"


@pytest.mark.asyncio
async def test_tempdir_is_cleaned_after_subprocess(tmp_path):
    """The rubric can write to cwd; the tempdir must vanish after return."""
    rubric_root = tmp_path / "bench"
    (rubric_root / "stub-task-class").mkdir(parents=True)
    leaked_path_holder = tmp_path / "leaked_path.txt"
    rubric = rubric_root / "stub-task-class" / "rubric.py"
    rubric.write_text(
        f"import os, sys, json, pathlib;"
        f"pathlib.Path({str(leaked_path_holder)!r}).write_text(os.getcwd());"
        f"sys.stdout.write(json.dumps({{'passed': True, 'score': 1.0, 'breakdown': {{}},"
        f" 'failure_modes': [], 'cost_usd': 0.0, 'wall_clock_ms': 0}}))"
    )
    runner = SubprocessRubricRunner(rubric_root=rubric_root)
    await runner(make_bench_case(task_class="stub-task-class"), {})
    cwd_used = Path(leaked_path_holder.read_text())
    assert not cwd_used.exists(), "tempdir should be removed after subprocess returns"
```

Run all six tests; confirm import failures. Commit as the red marker.

### Green — make them pass

`SubprocessRubricRunner` with `asyncio.create_subprocess_exec` + `tempfile.TemporaryDirectory()` + the four-key `SCRUBBED_ENV`. Map the three failure paths (non-zero exit, timeout, malformed JSON) to typed `FailureMode`s. Use `BenchScore.model_validate_json` for the happy path. `wall_clock_ms` measured by runner via `time.monotonic_ns()`.

### Refactor — clean up

- Pull the failure-path mapping into a private `_to_failure_score(...)` helper so S3-04 can extend it for the additional three failure modes (`rubric.unknown_breakdown_key`, `rubric.unknown_failure_mode`, `sut.*`) without restructuring this module.
- Docstring on `SubprocessRubricRunner.__call__` enumerates the four failure paths owned by this story plus a pointer to S3-04 for the breakdown-key / failure-mode runtime validation.
- `structlog.bind(case_id=case.case_id, rubric_path=...).info("rubric_subprocess_complete", returncode=proc.returncode, wall_clock_ms=...)`.
- Comment the FS-scope guarantee near `cwd=tmpdir`: "Tempdir is wiped on context exit. Network egress is the explicit residual (ADR-0001 §Tradeoffs row 1)."

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/rubric_subprocess.py` | New module: `SubprocessRubricRunner` + `SCRUBBED_ENV` |
| `src/codegenie/eval/runner.py` | Wire `SubprocessRubricRunner` as the default `rubric_runner` in `run_eval` |
| `tests/unit/test_rubric_subprocess.py` | New tests: SCRUBBED_ENV shape, immutability, happy path, env-scrub adversarial, timeout, malformed JSON, tempdir cleanup |
| `tests/helpers/bench.py` | Add `make_bench_case(...)` helper if not present from S2-02 |

## Out of scope

- The three additional rubric failure modes (`unknown_breakdown_key`, `unknown_failure_mode`) and the two SUT failure modes (`sut.exception`, `sut.timeout`) — S3-04.
- The full adversarial bench fixture portfolio (timeout fixture, banned-breakdown-key fixture, poisoned-case fixture, malformed-YAML fixture) — S3-07.
- Cost-cap cancellation — S3-06.
- microVM upgrade — Phase 16 (ADR-0001 §Reversibility).
- Network egress blocking — explicit residual; CODEOWNERS on `bench/**/rubric.py` is the compensating control.
- Process-group-kill on tempdir teardown for rubric-spawned children — `final-design.md §Open Q #3` defers to Phase 16.

## Notes for the implementer

- **`SCRUBBED_ENV` is the load-bearing surface.** Every key added is a CODEOWNERS-visible audit risk per ADR-0001 §Tradeoffs. The four-key allowlist is the documented floor; if a rubric legitimately needs another env var (e.g., `TZ`), open an ADR amendment, do not silently extend.
- **`sys.executable` not `"python"`**. The latter resolves via `PATH` in a way that may pick up the wrong interpreter on CI; `sys.executable` is the harness's own Python and is stable.
- **`MappingProxyType` matters.** A mutable `dict` default exposes a footgun: anywhere the runner is imported, `SCRUBBED_ENV["EVIL"] = "1"` would mutate the constant. `types.MappingProxyType` rejects assignment. The immutability test is the structural guard.
- **`proc.kill()` then `await proc.wait()`** — not just `proc.kill()`. Without the `await`, the child process is a zombie until the next event loop tick and the tempdir teardown can race; the test for tempdir cleanup will be flaky.
- **stderr is captured but only logged on non-zero exit** (arch §Logging strategy "Bench-author rubric stderr is captured but logged only on rubric subprocess non-zero exit"). On the happy path, stderr is discarded.
- **Do not extend SCRUBBED_ENV to include `PYTHONPATH`** unless the rubric depends on it. The default `PYTHONPATH=""` means the subprocess only sees the stdlib + whatever `sys.executable` was installed with — exactly the trust posture we want. If a bench-author rubric legitimately needs to import a helper module from `bench/{tc}/_lib/`, that helper must be co-located and the rubric can `sys.path.insert(0, str(Path(__file__).parent / "_lib"))` itself.
- **Adversarial test must run on Linux *and* macOS in CI** (per `High-level-impl.md §Implementation-level risks #3`). The test as written should be portable; if a macOS-specific env var sneaks into the SCRUBBED_ENV (e.g., `__CF_USER_TEXT_ENCODING`), surface it explicitly — don't paper over it.
- **The `Rubric` Protocol (S1-04) is what bench-author unit tests type-check against** — the subprocess invocation does not type-check across the process boundary. This story is purely a runtime contract; the Protocol's value is in `bench/{tc}/tests/test_rubric_unit.py`, not here.
