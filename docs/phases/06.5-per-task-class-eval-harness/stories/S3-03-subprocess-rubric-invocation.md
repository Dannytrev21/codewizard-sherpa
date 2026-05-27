# Story S3-03 — Subprocess rubric invocation with scrubbed env

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready (HARDENED 2026-05-27)
**Effort:** M
**Depends on:** S3-02 (asyncio fan-out + aggregator — HARDENED; introduces `RubricRunner` Protocol at `src/codegenie/eval/rubric_runner.py`; this story substitutes the concrete `SubprocessRubricRunner` **by addition**, without re-shaping the Protocol), S1-04 (Rubric Protocol — HARDENED), S1-02 (`BenchScore`, `BenchCase`, `FailureMode` wire models — HARDENED).
**ADRs honored:** ADR-0001 (subprocess + scrubbed env isolation — load-bearing; canonical `SCRUBBED_ENV` source), ADR-0004 (rubric subprocess failures map to typed `FailureMode`s, not exceptions — runner never re-raises), ADR-0010 (`isolation_class="subprocess"` is the audit-chain annotation this story's runner shape *causes* to be true), Phase 5 ADR-0012 (env allowlist discipline — divergence is CODEOWNERS-visible). **Conformance pin:** matches S3-02 AC-3 `RubricRunner` Protocol bytes-for-bytes.

## Context

The rubric is control-plane code: its `BenchScore` feeds the promotion gate, which determines whether a task class graduates. The rubric is also untrusted in the same sense bench-case data is — it lives at `bench/{task-class}/rubric.py`, a CODEOWNERS-gated path that any contributor may PR. ADR-0001 picks subprocess + scrubbed env (not in-process, not microVM) as the load-bearing isolation posture for Phase 6.5.

S3-02 (HARDENED 2026-05-27) introduced the `RubricRunner` Protocol at `src/codegenie/eval/rubric_runner.py`:

```python
@runtime_checkable
class RubricRunner(Protocol):
    async def run(
        self,
        rubric_path: Path,
        case: BenchCase,
        harness_output: Mapping[str, Any],
        *,
        wall_clock_cap_seconds: float,
    ) -> BenchScore: ...
```

This story implements `SubprocessRubricRunner` — the concrete `RubricRunner` that S3-02's worker injects. The class is added to the **same module** that holds the Protocol (sibling Protocol-port files in this repo, e.g. `vuln_index/protocol.py`, `fallback/leaf/port.py`, co-locate the Protocol with its canonical implementation). The substitution is **by addition** — no edit to the Protocol or to `Runner.execute`'s signature.

Invocation contract: `asyncio.create_subprocess_exec(sys.executable, "-I", "-B", str(rubric_path), env=dict(SCRUBBED_ENV), cwd=<tempdir>, stdin=PIPE, stdout=PIPE, stderr=PIPE)`; stdin = JSON `{case, harness_output}`; stdout = `BenchScore` JSON; timeout = `wall_clock_cap_seconds` (the kwarg, **not** `case.rubric_wall_clock_seconds` — case-level selection is the worker's job and lands in S3-04).

The adversarial test is the proof: a hand-crafted rubric that attempts `os.environ.get("ANTHROPIC_API_KEY")` must receive `None`, AND the subprocess's `os.environ` must contain *exactly* the three keys in `SCRUBBED_ENV` (no carryover). That pair of assertions is the structural enforcement of ADR-0001's "defeats credential read" claim.

## Validation notes (HARDENED 2026-05-27)

This story was rewritten to close 27 critic findings (7 block, 15 harden, 5 nit). Full audit in `_validation/S3-03-subprocess-rubric-invocation.md`. Key changes from the original draft:

- **Module path corrected** — `rubric_subprocess.py` → `rubric_runner.py` (co-locates with the Protocol S3-02 introduces; sibling Protocol-port convention).
- **Class shape corrected** — `async __call__(self, case, harness_output)` (callable) → `async def run(self, rubric_path, case, harness_output, *, wall_clock_cap_seconds)` (matches S3-02 AC-3 Protocol bytes-for-bytes).
- **No constructor parameters** — `rubric_root` and `timeout_default` removed (parameters flow via `run(...)` per the Protocol; the worker is responsible for resolving `rubric_path` and `wall_clock_cap_seconds`). This is what makes the eventual `MicroVMRubricRunner` (Phase 16) substitutable by addition.
- **`SCRUBBED_ENV` aligned to ADR-0001** — story's original 4-key allowlist (PATH, LANG, PYTHONHASHSEED, PYTHONIOENCODING) silently contradicted ADR-0001's 3-key spec (PYTHONPATH, PYTHONHASHSEED, PATH). Aligned to the ADR. PYTHONPATH=""; the `-I` flag below makes the value moot anyway, providing defense-in-depth. Any future divergence requires an ADR-0001 §SCRUBBED_ENV amendment landed in the same PR (Rule 7).
- **`python -I -B` flags added** — final-design.md lines 168–179 mandate isolated mode (`-I` ignores PYTHONPATH / PYTHONHOME / user site-packages even if env tries to leak them in) + no `.pyc` writes (`-B`). Without `-I`, the env scrub is not the full defense the ADR claims.
- **Timeout source corrected** — `case.rubric_wall_clock_seconds or 60.0` → `wall_clock_cap_seconds` kwarg. Per-case timeout selection is the worker's job (S3-04 amendment).
- **No runtime wiring in this story** — original story said "wire as default in `Runner.run_eval`"; runner method is `Runner.execute` per S3-02 and `rubric_runner` is a no-default kwarg. CLI default construction lands in S4-02.
- **Protocol-conformance AC added** — `isinstance(SubprocessRubricRunner(), RubricRunner)` AND `typing._get_protocol_attrs(RubricRunner)` symmetry. This is the structural enforcement of "extension by addition" — when `MicroVMRubricRunner` ships in Phase 16, the same test must pass for it.
- **Mutation-resistant tests added** — Hypothesis JSON round-trip; metamorphic determinism; isolated-flag assertion; exact-env-key-set enumeration; elapsed-wall-clock cap proof; cwd-is-actually-tempdir; `proc.wait()`-after-`kill()` enforcement; concurrent-invocation tempdir isolation.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Agentic best practices → Tool-use safety` — full specification of `SCRUBBED_ENV`, `cwd`, FS scope, resource caps, residual risk (network egress not blocked).
  - `../phase-arch-design.md §Edge cases #3, #4, #5` — rubric crash (non-zero exit), timeout, malformed JSON. Each maps to a `FailureMode(severity="block")` and the run continues.
  - `../phase-arch-design.md §Components → rubric.py` — "two call sites, two execution models" (bench-author tests use in-process; runner never does).
  - `../phase-arch-design.md §Scenarios → Scenario 2` background; this story owns the subprocess invocation that scenario relies on.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — the canonical isolation contract. Read §Decision and §Consequences fully. **`SCRUBBED_ENV` spec lives here; this story conforms.**
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — the rubric subprocess failure surface is **typed `FailureMode`**, not Python exceptions. The runner does not re-raise.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — `isolation_class="subprocess"` is set by S3-02 unconditionally; this story's runner shape is what makes that label *true*.
- **Sibling HARDENED stories:**
  - `S3-02-asyncio-fan-out-and-aggregator.md §AC-3` — the `RubricRunner` Protocol shape this story conforms to. **Read this AC verbatim before implementing.**
  - `S1-04-rubric-protocol.md` — the in-process `Rubric` Protocol for bench-author tests; orthogonal to this story but referenced by `bench/{tc}/rubric.py` files.
- **Phase 5 ADR:** `../../05-sandbox-trust-gates/ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — `env_allowlist.filter({})` precedent. The SCRUBBED_ENV here mirrors that discipline.
- **Source design:** `../final-design.md §Components → SubprocessRubricRunner` (lines 170-179) — `python -I -B <entrypoint>`; rubric `.py` bytes copied into scratch; `env={}` baseline; subprocess `BenchScore` shape is invariant across the eventual microVM upgrade.
- **Sibling Protocol-port files in this repo (the codebase convention to mirror):**
  - `src/codegenie/vuln_index/protocol.py` + concrete `Feed` implementations — Protocol + canonical implementation co-located in the same package.
  - `src/codegenie/fallback/leaf/port.py` + `anthropic_adapter.py` — cross-process-boundary precedent (Protocol typed surface; subprocess/adapter wire).

## Goal

Implement `SubprocessRubricRunner` as a concrete `RubricRunner` (the Protocol introduced by S3-02 AC-3) in `src/codegenie/eval/rubric_runner.py`. The class **takes no constructor parameters** and invokes the rubric across a process boundary with `python -I -B <rubric_path>`, a 3-key `SCRUBBED_ENV` matching ADR-0001, an isolated `tempfile.TemporaryDirectory()` as `cwd`, JSON stdin/stdout, and a `wall_clock_cap_seconds` kwarg-driven timeout — defeating credential read, ignoring inherited `PYTHONPATH` / `PYTHONHOME` / user site-packages (via `-I`), and arbitrary FS write outside the wiped tempdir. The seam is what makes a future `MicroVMRubricRunner` (Phase 16) substitutable **by addition**: zero edits to `rubric_runner.py`'s Protocol, zero edits to `Runner.execute`.

## Acceptance criteria

### Protocol conformance (the load-bearing extension-by-addition seam)

- [ ] **AC-1.** `isinstance(SubprocessRubricRunner(), RubricRunner) is True`. AND `typing._get_protocol_attrs(RubricRunner) == frozenset({"run"})` (only one Protocol method — pinned to match S3-02). A red test asserts both; a wrong impl that adds a second public method (extending the Protocol surface) or omits `run` (failing conformance) fails one of the two.
- [ ] **AC-2.** `SubprocessRubricRunner.run` signature is bytes-for-bytes equivalent to S3-02 AC-3's `RubricRunner.run` Protocol: `async def run(self, rubric_path: Path, case: BenchCase, harness_output: Mapping[str, Any], *, wall_clock_cap_seconds: float) -> BenchScore`. A signature-introspection test (`inspect.signature(SubprocessRubricRunner.run)`) verifies parameter names, ordering, kwarg-only marker on `wall_clock_cap_seconds`, and return annotation.
- [ ] **AC-3.** `SubprocessRubricRunner` lives in `src/codegenie/eval/rubric_runner.py` (the same module S3-02 introduced for the Protocol). No new module created.
- [ ] **AC-4.** `SubprocessRubricRunner` is added to `codegenie.eval.__all__` and re-exported at the package level. A test asserts `from codegenie.eval import SubprocessRubricRunner` succeeds without touching `rubric_runner` directly.
- [ ] **AC-5.** **Wiring out-of-scope.** This story does NOT modify `Runner.execute` (`src/codegenie/eval/runner.py`). The CLI default construction of `SubprocessRubricRunner()` lands in S4-02 (`eval run` subcommand assembly); the in-process `InProcessStubRubric` already lives in `tests/helpers/rubrics.py` (S3-02). A test asserts `Runner.execute`'s signature is unchanged from HARDENED S3-02.

### SCRUBBED_ENV — ADR-0001-conformant

- [ ] **AC-6.** `SCRUBBED_ENV: Final[Mapping[str, str]]` is a module-level constant in `rubric_runner.py`, declared via `types.MappingProxyType`. Contents (matching ADR-0001 §Decision exactly): `PATH="/usr/bin:/bin"`, `PYTHONHASHSEED="0"`, `PYTHONPATH=""`. **Exactly three keys** — no `ANTHROPIC_API_KEY`, no `AWS_*`, no `HOME`, no `USER`, no `OPENAI_API_KEY`, no `LANG`, no `PYTHONIOENCODING`. A test asserts `set(SCRUBBED_ENV) == {"PATH", "PYTHONHASHSEED", "PYTHONPATH"}` exactly (set equality, not membership).
- [ ] **AC-6a.** `SCRUBBED_ENV` is wrapped in `types.MappingProxyType`; mutation raises `TypeError`. A test asserts `with pytest.raises(TypeError): SCRUBBED_ENV["EVIL"] = "1"`.

### Subprocess invocation contract

- [ ] **AC-7.** Invocation argv: `[sys.executable, "-I", "-B", str(rubric_path)]`. `-I` (isolated mode: ignore `PYTHON*` env, no user site-packages) and `-B` (no `.pyc` writes) are load-bearing — `-I` is what makes `SCRUBBED_ENV` the *full* defense the ADR claims. A test executes the rubric and the rubric prints `{"isolated": sys.flags.isolated, "dont_write_bytecode": sys.flags.dont_write_bytecode}`; both `== 1` (AC-15 below).
- [ ] **AC-8.** `subprocess` call: `await asyncio.create_subprocess_exec(*argv, env=dict(SCRUBBED_ENV), cwd=tmpdir, stdin=PIPE, stdout=PIPE, stderr=PIPE)`. `tmpdir` comes from `tempfile.TemporaryDirectory()` inside a `with` block; tempdir is removed on context exit even if the subprocess raised (AC-12).
- [ ] **AC-9.** `cwd` is *actually* an OS tempdir: the path resolves under `Path(tempfile.gettempdir()).resolve()` (verified by a rubric that writes its `os.getcwd()` to an external sentinel file). A wrong impl using `cwd=os.getcwd()` (the harness's working tree) fails this AC.

### Timeout, reap, cleanup

- [ ] **AC-10.** Timeout: `await asyncio.wait_for(proc.communicate(input=stdin_bytes), timeout=wall_clock_cap_seconds)`. On `asyncio.TimeoutError`: `proc.kill()` then `await proc.wait()` (the `await` is load-bearing — without it the child is a zombie until the next event-loop tick and tempdir teardown can race). Then return `BenchScore(passed=False, score=0.0, breakdown={}, failure_modes=(FailureMode(code="rubric.timeout", severity="block"),), cost_usd=0.0, wall_clock_ms=<measured>)`. A test patches `proc.kill` and `proc.wait` (via `asyncio.create_subprocess_exec` patch) and asserts the call sequence `kill → wait` is observed.
- [ ] **AC-11.** Timeout cap is enforced by the runner, not by the rubric: a test with `wall_clock_cap_seconds=0.5` and a rubric that `time.sleep(60)` returns a `rubric.timeout` `FailureMode` AND the test's measured wall clock is ≤ 5 s. (Mutation: a wrong impl that ignores the kwarg and waits the rubric's natural exit would take ~60 s and time out the test.)
- [ ] **AC-12.** Tempdir cleanup: after `run(...)` returns (or raises through a non-handled path), `Path(<the cwd used>).exists() is False`. Verified by a stub rubric that writes its `os.getcwd()` to an external sentinel; the test reads the sentinel and asserts the path no longer exists.

### Failure-mode mapping (typed, not raised)

- [ ] **AC-13.** Non-zero exit: `BenchScore(passed=False, score=0.0, breakdown={}, failure_modes=(FailureMode(code="rubric.malformed_output", severity="block", detail=stderr_bytes[:200].decode("utf-8", "replace")),), cost_usd=0.0, wall_clock_ms=<measured>)`. AC-13a: a rubric that exits non-zero with **empty stderr** still produces a valid `BenchScore` (`detail == ""`) — no `IndexError` on empty bytes, no None propagation.
- [ ] **AC-14.** Malformed stdout (Pydantic `ValidationError` on `BenchScore.model_validate_json`): same `FailureMode(code="rubric.malformed_output", severity="block", detail=<short validation summary>)`. AC-14a: `detail` is non-empty AND contains either a Pydantic field name from `BenchScore` (one of `passed`, `score`, `breakdown`, `failure_modes`, `cost_usd`, `wall_clock_ms`) or the substring `"validation"` — a wrong impl returning `detail=""` fails.
- [ ] **AC-14b.** The runner does **not** re-raise on rubric subprocess failure (per ADR-0004); a `BenchScore` always returns. A test verifies by running two cases in sequence under the same `Runner.execute` integration: one passes, one with a crashing rubric — both produce per-case entries; the run does not abort. (Integration depends on S3-02's `Runner.execute`; in this story, an equivalent in-test loop calling `SubprocessRubricRunner.run` twice in a `gather` suffices.)

### Adversarial — load-bearing ADR-0001 guarantee

- [ ] **AC-15.** **Adversarial — credential read defeated.** A fixture rubric prints `os.environ.get("ANTHROPIC_API_KEY")` → `None`. The test asserts (a) `ANTHROPIC_API_KEY` is not in the subprocess's `os.environ.keys()`, (b) the secret value (set on the parent process via `monkeypatch.setenv`) does not appear anywhere in the captured stderr or in the returned `FailureMode.detail`, (c) `len(os.environ) == 3 AND set(os.environ) == {"PATH", "PYTHONHASHSEED", "PYTHONPATH"}` (exact-set enumeration — a wrong impl that strips one specific key but leaks others fails).
- [ ] **AC-15a.** **Adversarial — `-I` isolation flag applied.** A fixture rubric prints `{"isolated": sys.flags.isolated, "dont_write_bytecode": sys.flags.dont_write_bytecode}`; both `== 1`. (Mutation: without `-I`, an attacker who can set `PYTHONSTARTUP=/malicious.py` outside `SCRUBBED_ENV` still gets code execution at interpreter init. The flag is the defense-in-depth that closes the implicit `~/.pythonrc` channel.)

### Wall-clock measurement honesty

- [ ] **AC-16.** `wall_clock_ms` on the returned `BenchScore` is **measured by the runner** via `time.monotonic_ns()`, *not* passed through from the rubric. A test: rubric emits `wall_clock_ms=999_999_999`; runner returns `score.model_copy(update={"wall_clock_ms": <measured>})` where measured is `1 ≤ ms ≤ 5000` AND `ms != 999_999_999`. (Mutation: a wrong impl that trusts the rubric-emitted value fails.)

### Determinism, concurrency, property-based

- [ ] **AC-17.** **Metamorphic — determinism.** Running the same `(rubric_path, case, harness_output, wall_clock_cap_seconds)` twice produces two `BenchScore`s that are byte-identical under `model_dump_json()` modulo `wall_clock_ms` (the two `wall_clock_ms` values may differ by ≤ 50 ms but the other 5 fields are equal byte-for-bytes). A test verifies.
- [ ] **AC-17a.** **Concurrent invocations are tempdir-isolated.** `asyncio.gather(runner.run(...), runner.run(...))` with two slow rubrics that each `time.sleep(0.3)` and write a marker to `os.getcwd()` produces two distinct tempdir paths (assertion: marker file paths differ) AND both tempdirs are cleaned up.
- [ ] **AC-17b.** **Hypothesis — JSON round-trip.** Property: arbitrary `BenchScore` (Hypothesis-generated, valid wire shape) round-trips through stdin/stdout via an echo rubric (`json.dumps(json.loads(sys.stdin.read())["harness_output"]["score"])`) and `model_validate_json`'s the runner's output equals the input modulo `wall_clock_ms`.

### Hygiene

- [ ] **AC-18.** `mypy --strict`, `ruff format --check`, `ruff check` clean. `mypy --strict src/codegenie/eval/rubric_runner.py` produces zero errors (Protocol structural conformance is the static-type witness).
- [ ] **AC-19.** All red tests below exist, were committed at the red marker, and are now green.

## Implementation outline

1. Open `src/codegenie/eval/rubric_runner.py` (S3-02 introduced it for the `RubricRunner` Protocol). Add the new constant, the new class, and update `__all__`.
2. Define `SCRUBBED_ENV: Final[Mapping[str, str]]` as a module constant via `types.MappingProxyType({"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0", "PYTHONPATH": ""})`. Pin in a module-level comment: "Conformant with [ADR-0001 §Decision]. Divergence requires ADR amendment."
3. Define `class SubprocessRubricRunner:` **with no constructor parameters** (no `rubric_root`, no `timeout_default` — both flow via `run(...)` per the Protocol).
4. Implement `async def run(self, rubric_path: Path, case: BenchCase, harness_output: Mapping[str, Any], *, wall_clock_cap_seconds: float) -> BenchScore:` — body:
   - `stdin_payload = json.dumps({"case": case.model_dump(mode="json"), "harness_output": harness_output}).encode("utf-8")`.
   - `start_ns = time.monotonic_ns()`.
   - `with tempfile.TemporaryDirectory() as tmpdir:` —
     - `argv = [sys.executable, "-I", "-B", str(rubric_path)]`.
     - `proc = await asyncio.create_subprocess_exec(*argv, env=dict(SCRUBBED_ENV), cwd=tmpdir, stdin=PIPE, stdout=PIPE, stderr=PIPE)`.
     - `try: stdout, stderr = await asyncio.wait_for(proc.communicate(stdin_payload), timeout=wall_clock_cap_seconds)`.
     - `except asyncio.TimeoutError:`
       - `proc.kill()`
       - `await proc.wait()`  # load-bearing — see AC-10 Notes
       - return `_to_failure_score("rubric.timeout", detail="", wall_clock_ms=_elapsed_ms(start_ns))`.
   - `wall_clock_ms = _elapsed_ms(start_ns)`.
   - `if proc.returncode != 0:` return `_to_failure_score("rubric.malformed_output", detail=stderr[:200].decode("utf-8", "replace"), wall_clock_ms=wall_clock_ms)`.
   - `try: score = BenchScore.model_validate_json(stdout)`.
   - `except pydantic.ValidationError as e:` return `_to_failure_score("rubric.malformed_output", detail=_short_validation_summary(e), wall_clock_ms=wall_clock_ms)`.
   - return `score.model_copy(update={"wall_clock_ms": wall_clock_ms})` — preserve rubric-reported score; **always** override the rubric-emitted `wall_clock_ms` with measured (AC-16).
5. Define module-private helpers:
   - `def _elapsed_ms(start_ns: int) -> int:` — `(time.monotonic_ns() - start_ns) // 1_000_000`.
   - `def _short_validation_summary(e: pydantic.ValidationError) -> str:` — `str(e)[:200]` (Pydantic's `str()` includes field names + reasons).
   - `def _to_failure_score(code: str, *, detail: str, wall_clock_ms: int) -> BenchScore:` — returns `BenchScore(passed=False, score=0.0, breakdown={}, failure_modes=(FailureMode(code=code, severity="block", detail=detail),), cost_usd=0.0, wall_clock_ms=wall_clock_ms)`. **Extension hook**: S3-04 lands `rubric.unknown_breakdown_key` and `rubric.unknown_failure_mode` and may elevate this helper to a dispatch table (rule-of-three threshold hits when S3-04 adds the third failure-mode family).
6. Update `__all__` in `rubric_runner.py` to include `"SubprocessRubricRunner"` and `"SCRUBBED_ENV"`. Re-export both from `codegenie.eval.__init__`.

**Out of scope here** (do not modify): `Runner.execute` in `runner.py` (S3-02 HARDENED contract); CLI default-runner construction (S4-02); `case.rubric_wall_clock_seconds` selection (S3-04 worker concern).

## TDD plan — red / green / refactor

### Red — write failing tests first

Test file: `tests/unit/test_rubric_subprocess.py`

```python
import asyncio
import inspect
import json
import os
import sys
import tempfile
import time
import typing
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from codegenie.eval.rubric_runner import (
    RubricRunner,
    SCRUBBED_ENV,
    SubprocessRubricRunner,
)
from codegenie.eval.models import BenchScore, FailureMode
from tests.helpers.bench import make_bench_case


# --- Protocol conformance (AC-1, AC-2) ---


def test_subprocess_runner_satisfies_rubric_runner_protocol():
    assert isinstance(SubprocessRubricRunner(), RubricRunner)
    # The Protocol surface must remain a single method (S3-02 contract):
    assert typing._get_protocol_attrs(RubricRunner) == frozenset({"run"})


def test_subprocess_runner_run_signature_matches_protocol():
    sig = inspect.signature(SubprocessRubricRunner.run)
    params = list(sig.parameters.values())
    # self, rubric_path, case, harness_output, *, wall_clock_cap_seconds
    assert [p.name for p in params] == [
        "self", "rubric_path", "case", "harness_output", "wall_clock_cap_seconds",
    ]
    assert params[-1].kind is inspect.Parameter.KEYWORD_ONLY
    # Return annotation
    assert sig.return_annotation is BenchScore


def test_subprocess_runner_constructor_takes_no_args():
    # Constructor injects nothing — extension-by-addition seam (AC-2 / F-DP-1).
    SubprocessRubricRunner()  # no args, no kwargs


def test_subprocess_runner_exported_at_package_top():
    # AC-4
    from codegenie.eval import SubprocessRubricRunner as Exported
    assert Exported is SubprocessRubricRunner


# --- SCRUBBED_ENV (AC-6, AC-6a) ---


def test_scrubbed_env_contains_exactly_three_keys():
    """ADR-0001 §Decision: PYTHONPATH, PYTHONHASHSEED, PATH."""
    assert set(SCRUBBED_ENV) == {"PATH", "PYTHONHASHSEED", "PYTHONPATH"}
    # Negative enumeration:
    for forbidden in (
        "ANTHROPIC_API_KEY", "AWS_ACCESS_KEY_ID", "HOME", "USER",
        "OPENAI_API_KEY", "LANG", "PYTHONIOENCODING",
    ):
        assert forbidden not in SCRUBBED_ENV


def test_scrubbed_env_values_match_adr_0001():
    assert SCRUBBED_ENV["PATH"] == "/usr/bin:/bin"
    assert SCRUBBED_ENV["PYTHONHASHSEED"] == "0"
    assert SCRUBBED_ENV["PYTHONPATH"] == ""


def test_scrubbed_env_is_immutable():
    with pytest.raises(TypeError):
        SCRUBBED_ENV["EVIL"] = "1"  # MappingProxyType rejects


# --- Happy path (AC-7, AC-8, AC-15a, AC-16) ---


@pytest.mark.asyncio
async def test_happy_path_subprocess_rubric(tmp_path):
    rubric = _write_rubric(
        tmp_path,
        "import json, sys; _ = json.loads(sys.stdin.read());"
        "out = {'passed': True, 'score': 0.75, 'breakdown': {},"
        " 'failure_modes': [], 'cost_usd': 0.0, 'wall_clock_ms': 999_999_999};"
        "sys.stdout.write(json.dumps(out))",
    )
    score = await SubprocessRubricRunner().run(
        rubric, make_bench_case(task_class="stub-task-class"), {"any": "thing"},
        wall_clock_cap_seconds=10.0,
    )
    assert score.passed is True
    assert score.score == 0.75
    assert score.failure_modes == ()
    # AC-16: runner-measured wall_clock, NOT the rubric-emitted 999_999_999.
    assert 1 <= score.wall_clock_ms <= 5_000
    assert score.wall_clock_ms != 999_999_999


@pytest.mark.asyncio
async def test_subprocess_runs_with_isolated_flag(tmp_path):
    """AC-15a: -I and -B applied. Defense-in-depth on env scrub."""
    rubric = _write_rubric(
        tmp_path,
        "import json, sys;"
        "out = {'passed': True, 'score': 1.0, 'breakdown': {},"
        " 'failure_modes': [], 'cost_usd': 0.0, 'wall_clock_ms': 0,"
        " 'isolated': sys.flags.isolated, 'dont_write_bytecode': sys.flags.dont_write_bytecode};"
        "sys.stderr.write(json.dumps({'isolated': sys.flags.isolated,"
        " 'dwb': sys.flags.dont_write_bytecode}));"
        "out.pop('isolated'); out.pop('dont_write_bytecode');"
        "sys.stdout.write(json.dumps(out))",
    )
    # Pipe stderr through by intercepting the runner's _to_failure_score on non-zero exit;
    # here the rubric exits 0. Use a non-zero variant to capture stderr in detail:
    rubric_fail = _write_rubric(
        tmp_path,
        "import sys, json;"
        "sys.stderr.write(json.dumps({'isolated': sys.flags.isolated,"
        " 'dwb': sys.flags.dont_write_bytecode}));"
        "sys.exit(7)",
        subdir="iso",
    )
    fm_score = await SubprocessRubricRunner().run(
        rubric_fail, make_bench_case(task_class="iso"), {},
        wall_clock_cap_seconds=5.0,
    )
    detail = fm_score.failure_modes[0].detail or ""
    assert '"isolated": 1' in detail
    assert '"dwb": 1' in detail


# --- Adversarial credential-read (AC-15) ---


@pytest.mark.asyncio
async def test_subprocess_env_keys_are_exactly_scrubbed(tmp_path, monkeypatch):
    """AC-15 (a) + (c): exact-set enumeration. Pollute parent with 5 secrets;
    subprocess sees only the 3 SCRUBBED_ENV keys."""
    for k, v in {
        "ANTHROPIC_API_KEY": "sk-ant-secret",
        "AWS_ACCESS_KEY_ID": "AKIAsecret",
        "OPENAI_API_KEY": "sk-openai-secret",
        "HOME": "/home/secret",
        "USER": "secretuser",
    }.items():
        monkeypatch.setenv(k, v)
    rubric = _write_rubric(
        tmp_path,
        "import os, sys, json;"
        "sys.stderr.write(json.dumps({'keys': sorted(os.environ.keys()),"
        " 'count': len(os.environ),"
        " 'leak_anthropic': os.environ.get('ANTHROPIC_API_KEY'),"
        " 'leak_aws': os.environ.get('AWS_ACCESS_KEY_ID')}));"
        "sys.exit(2)",
    )
    score = await SubprocessRubricRunner().run(
        rubric, make_bench_case(task_class="stub-task-class"), {},
        wall_clock_cap_seconds=10.0,
    )
    fm = score.failure_modes[0]
    assert fm.code == "rubric.malformed_output"
    assert fm.severity == "block"
    detail = fm.detail or ""
    # AC-15 (b): no secret value leaks through.
    assert "sk-ant-secret" not in detail
    assert "AKIAsecret" not in detail
    assert "sk-openai-secret" not in detail
    assert "/home/secret" not in detail
    # AC-15 (a) + (c): exact-set enumeration in the rubric's view.
    assert '"count": 3' in detail
    assert '"keys": ["PATH", "PYTHONHASHSEED", "PYTHONPATH"]' in detail
    assert '"leak_anthropic": null' in detail
    assert '"leak_aws": null' in detail


# --- Timeout (AC-10, AC-11, AC-12) ---


@pytest.mark.asyncio
async def test_subprocess_timeout_maps_to_failure_mode_and_caps_elapsed(tmp_path):
    """AC-10 + AC-11: timeout cap enforced by runner, not rubric."""
    rubric = _write_rubric(tmp_path, "import time; time.sleep(60)")
    start = time.monotonic()
    score = await SubprocessRubricRunner().run(
        rubric, make_bench_case(task_class="stub-task-class"), {},
        wall_clock_cap_seconds=0.5,
    )
    elapsed = time.monotonic() - start
    assert score.failure_modes[0].code == "rubric.timeout"
    assert score.failure_modes[0].severity == "block"
    assert score.passed is False
    # AC-11: cap enforced (not waiting for natural 60s exit).
    assert elapsed <= 5.0


# --- Malformed JSON (AC-14, AC-14a) ---


@pytest.mark.asyncio
async def test_malformed_json_stdout_maps_to_failure_mode_with_summary(tmp_path):
    rubric = _write_rubric(tmp_path, "import sys; sys.stdout.write('not json')")
    score = await SubprocessRubricRunner().run(
        rubric, make_bench_case(task_class="stub-task-class"), {},
        wall_clock_cap_seconds=5.0,
    )
    fm = score.failure_modes[0]
    assert fm.code == "rubric.malformed_output"
    assert fm.severity == "block"
    detail = fm.detail or ""
    assert len(detail) > 0  # AC-14a: not empty
    # detail mentions a BenchScore field name OR contains "validation"
    field_names = {"passed", "score", "breakdown", "failure_modes", "cost_usd", "wall_clock_ms"}
    assert any(name in detail for name in field_names) or "validation" in detail.lower()


# --- Non-zero exit with empty stderr (AC-13a) ---


@pytest.mark.asyncio
async def test_nonzero_exit_with_empty_stderr_produces_valid_failure_score(tmp_path):
    rubric = _write_rubric(tmp_path, "import sys; sys.exit(3)")
    score = await SubprocessRubricRunner().run(
        rubric, make_bench_case(task_class="stub-task-class"), {},
        wall_clock_cap_seconds=5.0,
    )
    assert score.failure_modes[0].code == "rubric.malformed_output"
    assert score.failure_modes[0].detail == ""  # empty stderr decodes to empty string
    assert score.passed is False


# --- Tempdir is actual tempdir + cleanup (AC-9, AC-12) ---


@pytest.mark.asyncio
async def test_cwd_is_actual_tempdir_and_cleaned(tmp_path):
    sentinel = tmp_path / "cwd_used.txt"
    rubric = _write_rubric(
        tmp_path,
        f"import os, sys, json, pathlib;"
        f"pathlib.Path({str(sentinel)!r}).write_text(os.getcwd());"
        f"sys.stdout.write(json.dumps({{'passed': True, 'score': 1.0,"
        f" 'breakdown': {{}}, 'failure_modes': [], 'cost_usd': 0.0, 'wall_clock_ms': 0}}))",
    )
    await SubprocessRubricRunner().run(
        rubric, make_bench_case(task_class="stub-task-class"), {},
        wall_clock_cap_seconds=10.0,
    )
    cwd_used = Path(sentinel.read_text())
    # AC-9: cwd is under the OS tempdir, not the harness cwd.
    assert tempfile.gettempdir() in str(cwd_used.parent.resolve())
    # AC-12: tempdir vanishes after run() returns.
    assert not cwd_used.exists()


# --- Concurrent invocations isolated (AC-17a) ---


@pytest.mark.asyncio
async def test_concurrent_invocations_have_isolated_tempdirs(tmp_path):
    sentinel_a = tmp_path / "cwd_a.txt"
    sentinel_b = tmp_path / "cwd_b.txt"
    rubric_a = _write_rubric(
        tmp_path,
        f"import os, sys, json, time, pathlib;"
        f"pathlib.Path({str(sentinel_a)!r}).write_text(os.getcwd());"
        f"time.sleep(0.3);"
        f"sys.stdout.write(json.dumps({{'passed': True, 'score': 1.0,"
        f" 'breakdown': {{}}, 'failure_modes': [], 'cost_usd': 0.0, 'wall_clock_ms': 0}}))",
        subdir="a",
    )
    rubric_b = _write_rubric(
        tmp_path,
        f"import os, sys, json, time, pathlib;"
        f"pathlib.Path({str(sentinel_b)!r}).write_text(os.getcwd());"
        f"time.sleep(0.3);"
        f"sys.stdout.write(json.dumps({{'passed': True, 'score': 1.0,"
        f" 'breakdown': {{}}, 'failure_modes': [], 'cost_usd': 0.0, 'wall_clock_ms': 0}}))",
        subdir="b",
    )
    runner = SubprocessRubricRunner()
    await asyncio.gather(
        runner.run(rubric_a, make_bench_case(task_class="a"), {}, wall_clock_cap_seconds=10.0),
        runner.run(rubric_b, make_bench_case(task_class="b"), {}, wall_clock_cap_seconds=10.0),
    )
    cwd_a = Path(sentinel_a.read_text())
    cwd_b = Path(sentinel_b.read_text())
    assert cwd_a != cwd_b  # distinct tempdirs
    assert not cwd_a.exists()
    assert not cwd_b.exists()


# --- Determinism (AC-17) ---


@pytest.mark.asyncio
async def test_rubric_invocation_is_deterministic_modulo_wall_clock(tmp_path):
    rubric = _write_rubric(
        tmp_path,
        "import json, sys; _ = json.loads(sys.stdin.read());"
        "out = {'passed': True, 'score': 0.5, 'breakdown': {},"
        " 'failure_modes': [], 'cost_usd': 0.0, 'wall_clock_ms': 0};"
        "sys.stdout.write(json.dumps(out))",
    )
    runner = SubprocessRubricRunner()
    case = make_bench_case(task_class="stub-task-class")
    s1 = await runner.run(rubric, case, {"k": "v"}, wall_clock_cap_seconds=10.0)
    s2 = await runner.run(rubric, case, {"k": "v"}, wall_clock_cap_seconds=10.0)
    d1 = s1.model_dump()
    d2 = s2.model_dump()
    # All fields except wall_clock_ms are byte-equal.
    d1.pop("wall_clock_ms")
    d2.pop("wall_clock_ms")
    assert d1 == d2


# --- Hypothesis JSON round-trip (AC-17b) ---


_bench_score_strategy = st.builds(
    BenchScore,
    passed=st.booleans(),
    score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    breakdown=st.dictionaries(st.text(min_size=1, max_size=8), st.floats(min_value=0.0, max_value=1.0, allow_nan=False), max_size=3),
    failure_modes=st.just(()),
    cost_usd=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    wall_clock_ms=st.integers(min_value=0, max_value=300_000),
)


@given(target=_bench_score_strategy)
def test_json_round_trip_through_subprocess(target: BenchScore, tmp_path_factory):
    """AC-17b: arbitrary BenchScore round-trips through the subprocess wire."""
    tmp_path = tmp_path_factory.mktemp("rt")
    payload_json = target.model_dump_json()
    rubric = _write_rubric(
        tmp_path,
        f"import sys; sys.stdout.write({payload_json!r})",
    )
    score = asyncio.run(
        SubprocessRubricRunner().run(
            rubric, make_bench_case(task_class="stub-task-class"), {},
            wall_clock_cap_seconds=10.0,
        )
    )
    out = score.model_dump()
    expected = target.model_dump()
    out.pop("wall_clock_ms")  # measured by runner per AC-16
    expected.pop("wall_clock_ms")
    assert out == expected


# --- Runner does not re-raise (AC-14b) ---


@pytest.mark.asyncio
async def test_runner_does_not_re_raise_two_cases_back_to_back(tmp_path):
    rubric_pass = _write_rubric(
        tmp_path,
        "import json, sys;"
        "sys.stdout.write(json.dumps({'passed': True, 'score': 1.0,"
        " 'breakdown': {}, 'failure_modes': [], 'cost_usd': 0.0, 'wall_clock_ms': 0}))",
        subdir="pass",
    )
    rubric_crash = _write_rubric(
        tmp_path,
        "raise SystemExit(99)",
        subdir="crash",
    )
    runner = SubprocessRubricRunner()
    s1 = await runner.run(rubric_pass, make_bench_case(task_class="pass"), {},
                          wall_clock_cap_seconds=5.0)
    s2 = await runner.run(rubric_crash, make_bench_case(task_class="crash"), {},
                          wall_clock_cap_seconds=5.0)
    assert s1.passed is True
    assert s2.passed is False
    assert s2.failure_modes[0].code == "rubric.malformed_output"


# --- helpers ---


def _write_rubric(tmp_path: Path, body: str, *, subdir: str = "stub-task-class") -> Path:
    rubric_dir = tmp_path / "bench" / subdir
    rubric_dir.mkdir(parents=True, exist_ok=True)
    rubric = rubric_dir / "rubric.py"
    rubric.write_text(body)
    return rubric
```

Run all ~16 tests; confirm import / attribute failures. Commit as the red marker.

### Green — make them pass

Implement `SubprocessRubricRunner` per the Implementation outline. The class-body skeleton:

```python
import asyncio, json, sys, tempfile, time, types
from asyncio.subprocess import PIPE
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import pydantic

from codegenie.eval.models import BenchCase, BenchScore, FailureMode

SCRUBBED_ENV: Final[Mapping[str, str]] = types.MappingProxyType({
    "PATH": "/usr/bin:/bin",
    "PYTHONHASHSEED": "0",
    "PYTHONPATH": "",
})  # Conformant with ADR-0001 §Decision. Divergence requires ADR amendment.


class SubprocessRubricRunner:
    """Default RubricRunner: spawns python -I -B <rubric_path> across a process
    boundary with SCRUBBED_ENV and a tempdir cwd. Defeats credential read +
    arbitrary FS write outside the wiped tempdir. Does NOT defeat network egress
    (ADR-0001 §Tradeoffs row 1 — explicit residual; CODEOWNERS is the
    compensating control). Failure paths owned by this story: rubric.timeout,
    rubric.malformed_output (non-zero exit and Pydantic ValidationError). S3-04
    extends to rubric.unknown_breakdown_key / rubric.unknown_failure_mode.
    """

    async def run(
        self,
        rubric_path: Path,
        case: BenchCase,
        harness_output: Mapping[str, Any],
        *,
        wall_clock_cap_seconds: float,
    ) -> BenchScore:
        ...  # per Implementation outline
```

### Refactor — clean up

- Keep `_to_failure_score(code, *, detail, wall_clock_ms)` as a module-private helper. **S3-04 will land 3 more failure modes** (rule-of-three threshold); the helper is the staging surface for elevation to a dispatch table or `@register_rubric_failure_mode(code)` registry. Do not pre-introduce the registry — wait for the third concrete consumer to land in S3-04.
- Docstring on `SubprocessRubricRunner.run` enumerates the two failure-mode families owned by this story + a pointer to S3-04 for the breakdown-key / failure-mode runtime validation.
- `structlog.bind(case_id=case.case_id, rubric_path=str(rubric_path)).info("rubric_subprocess_complete", returncode=proc.returncode, wall_clock_ms=...)`.
- Comment near `cwd=tmpdir`: "Tempdir is wiped on context exit. Network egress is the explicit residual (ADR-0001 §Tradeoffs row 1; Phase 16 may add)."
- Comment near `argv`: "-I = isolated mode (ignores PYTHON* env + user site-packages even if SCRUBBED_ENV is somehow breached). -B = no .pyc writes. Defense-in-depth per final-design.md lines 168-179."

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/rubric_runner.py` | **Modify (S3-02 created)**: add `SCRUBBED_ENV` constant + `SubprocessRubricRunner` class + helpers. Do NOT touch the `RubricRunner` Protocol — its shape is HARDENED. |
| `src/codegenie/eval/__init__.py` | Re-export `SubprocessRubricRunner` and `SCRUBBED_ENV` (`__all__` additions). |
| `tests/unit/test_rubric_subprocess.py` | NEW: 16 tests (Protocol conformance, signature, exports, SCRUBBED_ENV shape / immutability / values, happy path, isolated-flag, env-keys-exact-set, timeout cap, malformed JSON, empty-stderr, cwd-is-tempdir, concurrent isolation, determinism, Hypothesis round-trip, no-re-raise). |
| `tests/helpers/bench.py` | Ensure `make_bench_case(task_class=...)` exists (S2-02 may have already shipped it; add only if missing — do not duplicate). |

## Out of scope

- The three additional rubric failure modes (`unknown_breakdown_key`, `unknown_failure_mode`) and the two SUT failure modes (`sut.exception`, `sut.timeout`) — **S3-04**.
- Per-case timeout selection (`case.rubric_wall_clock_seconds or 60.0`) — **worker layer, S3-04** (the worker resolves `wall_clock_cap_seconds` from the case + the threaded `timeout_per_case_seconds` kwarg before invoking `run`).
- CLI default-runner construction (instantiating `SubprocessRubricRunner()` at `codegenie eval run` assembly time) — **S4-02**.
- Promotion of `_to_failure_score` helper to a `@register_rubric_failure_mode` registry — **S3-04** rule-of-three threshold.
- The full adversarial bench fixture portfolio (timeout fixture, banned-breakdown-key fixture, poisoned-case fixture, malformed-YAML fixture) — **S3-07**.
- Cost-cap cancellation — **S3-06**.
- microVM upgrade — **Phase 16** (ADR-0001 §Reversibility). The Protocol seam is what makes that upgrade additive: `MicroVMRubricRunner` substitutes by passing `isinstance(MicroVMRubricRunner(), RubricRunner) is True` — no edit to `rubric_runner.py`'s seam, no edit to `Runner.execute`.
- Network egress blocking — explicit residual; CODEOWNERS on `bench/**/rubric.py` is the compensating control.
- Process-group-kill on tempdir teardown for rubric-spawned children — `final-design.md §Open Q #3` defers to Phase 16.

## Notes for the implementer

- **`SCRUBBED_ENV` is canonical per ADR-0001 §Decision.** Three keys, exact values. The original story draft proposed 4 keys (with `LANG`, `PYTHONIOENCODING` and *without* `PYTHONPATH`); that contradicted the ADR and was rejected by the validator. If a rubric legitimately needs another env var (`TZ`, etc.), open an ADR-0001 amendment in the same PR — do not silently extend (Rule 7 — surface conflicts).
- **`-I` is the load-bearing isolation flag.** `SCRUBBED_ENV` controls the *env block* the child inherits. `-I` additionally tells the interpreter to ignore `PYTHONHOME`, `PYTHONPATH`, `PYTHONSTARTUP`, and user site-packages *even if* they somehow leaked in (CI runner with a misconfigured systemd unit; a future regression that adds a key to `SCRUBBED_ENV`). Defense-in-depth. Without `-I`, an attacker who controls `PYTHONSTARTUP=/malicious.py` outside the env still gets code execution at interpreter init.
- **`sys.executable` not `"python"`.** `"python"` resolves via `PATH` in a way that may pick up the wrong interpreter on CI; `sys.executable` is the harness's own Python and is stable.
- **`MappingProxyType` matters.** A mutable `dict` default exposes a footgun: anywhere the runner is imported, `SCRUBBED_ENV["EVIL"] = "1"` would mutate the constant. `types.MappingProxyType` rejects assignment; the immutability test is the structural guard.
- **`proc.kill()` then `await proc.wait()`** — not just `proc.kill()`. Without the `await`, the child process is a zombie until the next event loop tick and the tempdir teardown can race; AC-12 / AC-17a become flaky.
- **`wall_clock_ms` always overridden.** Per AC-16, the runner overrides whatever the rubric emitted with the measured value. This is not optional — a rubric author who emits a stale or doctored `wall_clock_ms` would otherwise smuggle a false signal into the audit chain.
- **stderr captured but only surfaced on non-zero exit** (arch §Logging strategy). On the happy path, stderr is discarded. AC-15 tests verify the captured detail is non-secret.
- **No constructor parameters.** `SubprocessRubricRunner()` takes nothing. This is the Strategy/DIP seam: the worker passes `rubric_path` and `wall_clock_cap_seconds` per-invocation. When `MicroVMRubricRunner` ships in Phase 16, it will have the same shape — `__init__(self)`, `async def run(self, rubric_path, case, harness_output, *, wall_clock_cap_seconds)`. Constructor injection of `rubric_root` or `timeout_default` here would *break* that seam.
- **`_to_failure_score` is the rule-of-three staging surface.** Phase 6.5 S3-03 lands 1 helper for 2 failure-mode families (timeout, malformed_output). S3-04 lands 3 more (`unknown_breakdown_key`, `unknown_failure_mode`, `sut.exception` / `sut.timeout` at the worker layer). When S3-04 wires the third family of *rubric* failures, that is the rule-of-three trigger — the helper elevates to a dispatch table or `@register_rubric_failure_mode(code, factory)` registry. Don't pre-introduce; the helper-extraction in S3-03 is precisely the cheap optionality that pays the rule-of-three rent (Rule 2 — three similar lines is better than a premature abstraction).
- **Adversarial test must run on Linux *and* macOS in CI** (per `High-level-impl.md §Implementation-level risks #3`). The test as written should be portable; if a macOS-specific env var sneaks into the SCRUBBED_ENV view (e.g., `__CF_USER_TEXT_ENCODING`), surface it explicitly — don't paper over it. The exact-set enumeration in AC-15 will catch it.
- **The `Rubric` Protocol (S1-04) is what bench-author unit tests type-check against** — the subprocess invocation does not type-check across the process boundary. This story is purely a runtime contract; the Protocol's value is in `bench/{tc}/tests/test_rubric_unit.py`, not here.
