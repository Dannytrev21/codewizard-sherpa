# Story S4-05 — Adversarial test suite

**Step:** Step 4 — Cut the vertical slice: CLI, `LanguageDetectionProbe`, fixtures, end-to-end smoke
**Status:** Ready
**Effort:** M
**Depends on:** S4-02
**ADRs honored:** ADR-0008, ADR-0010, ADR-0012

## Context

The architecture commits a posture of "structural defenses, not runtime checks" (`phase-arch-design.md §Agentic best practices — Tool-use safety`; `final-design.md §2.5`). The `tests/adv/` suite is the executable form of that posture: each test pins one structural invariant — no `shell=True`, no network imports, env strip works, paths don't escape, secrets don't leak, YAML loaders are safe — so that a regression silently widening any of these surfaces fails CI on the same PR that introduces it.

Step 2 already covered three of these (`test_no_shell_true.py`, `test_no_network_imports.py`, `test_yaml_unsafe_load.py`) per `High-level-impl.md §Step 2 Done criteria`. This story ships the remaining four: `test_path_traversal.py`, `test_symlink_escape.py`, `test_secret_leak.py`, `test_env_var_strip.py` — each one a behavioral assertion against the CLI or a focused AST scan over `src/codegenie/`.

These tests are deliberately small. Each pins one invariant. The value is the *set* — together they form the structural belt to the harness's suspenders.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy — Adversarial tests` — the seven-test enumeration; this story owns the four not landed in Step 2.
  - `../phase-arch-design.md §Edge cases` — row 4 (symlink-escape), row 5 (secret-shaped field), row 7 (symlink output target), row 9 (fence — already covered).
  - `../phase-arch-design.md §Scenarios — Scenario 4` — the secret-leak path; the test pins the structural defense.
  - `../phase-arch-design.md §Agentic best practices — Tool-use safety` — env-stripping, no network egress.
  - `../phase-arch-design.md §Component design — CLI` — `Path.resolve(strict=True)` rejects path traversal; the test pins the rejection.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — `test_secret_leak.py` pins the defense-in-depth: the validator catches secret-shaped fields; the sanitizer repeats the pass.
  - `../ADRs/0010-pydantic-probe-output-validator.md` — ADR-0010 — `test_secret_leak.py` asserts `_ProbeOutputValidator` raises `SecretLikelyFieldNameError` on a secret-shaped key.
  - `../ADRs/0012-subprocess-allowlist-chokepoint.md` — ADR-0012 — `test_env_var_strip.py` pins `OPENAI_API_KEY` / `AWS_*` / `SSH_AUTH_SOCK` never reaching the child of `run_allowlisted`.
- **Source design:**
  - `../final-design.md §7.3` — adversarial-tests enumeration and rationale.
- **Existing code:**
  - `src/codegenie/cli.py` — `Path.resolve(strict=True)` is the chokepoint for path-traversal; the test invokes `cli` with `..`-bearing paths.
  - `src/codegenie/exec.py` — `run_allowlisted` is the chokepoint for env-strip; the test mocks `asyncio.create_subprocess_exec` and inspects the `env` kwarg.
  - `src/codegenie/probes/language_detection.py` — `probe.symlink.escaped` event is emitted on a symlink resolving out-of-repo; the test plants such a symlink and asserts the event.
  - `src/codegenie/coordinator/validator.py` — `_ProbeOutputValidator` raises `SecretLikelyFieldNameError` on a secret-shaped key; the test asserts the error and the gather's continuation policy.
  - `src/codegenie/errors.py` — `SecretLikelyFieldNameError`, `SymlinkRefusedError`.

## Goal

`pytest tests/adv/ -q` exits 0; the four new test files (`test_path_traversal.py`, `test_symlink_escape.py`, `test_secret_leak.py`, `test_env_var_strip.py`) each pin one structural invariant; a single deliberate regression to the corresponding chokepoint causes the respective test to fail.

## Acceptance criteria

- [ ] `tests/adv/__init__.py` exists (empty; pytest package marker — may already be in place from Step 2's `test_no_shell_true.py`).
- [ ] `tests/adv/test_path_traversal.py` exists and pins the invariant: invoking `cli` with a `<path>` containing `..` that resolves outside the analyzed-repo root is rejected. Specifically:
  - Invoking `cli` with `gather /some/tmp/safe/../../etc` is refused (the resolved path is outside any reasonable repo root, and `Path.resolve(strict=True)` either rejects or the CLI's repo-root check rejects).
  - A non-zero exit code is returned (1 for unhandled, or a more specific code if the CLI surfaces one).
  - The test does **not** depend on a specific exit code beyond non-zero — the structural invariant is "this is rejected," not "exit code X."
- [ ] `tests/adv/test_symlink_escape.py` exists and pins the invariant: a symlink inside the analyzed repo pointing at `/etc/hosts` (or any path outside the repo root) is skipped by `LanguageDetectionProbe`'s walker, and a `probe.symlink.escaped` structlog event is emitted referencing the offending entry's repo-relative path. Specifically:
  - The test creates `tmp_path/a.js` (valid file), `tmp_path/link.js` (symlink → `/etc/hosts`), runs the probe (or the CLI), and captures structlog output.
  - Asserts the gather succeeds (exit 0).
  - Asserts the `language_stack.counts["javascript"]` equals 1 (the valid `a.js`; the symlink was skipped — not counted, not followed).
  - Asserts a `probe.symlink.escaped` event was emitted exactly once for `link.js`.
- [ ] `tests/adv/test_secret_leak.py` exists and pins the invariant: a synthetic probe emitting `schema_slice = {"github_token": "ghp_AAA..."}` is caught by `_ProbeOutputValidator` at the coordinator boundary; the probe is marked failed (`confidence="low"`, `errors=[...]`); the gather continues. Specifically:
  - Defines a one-off `class _SecretLeakingProbe(Probe)` whose `run(...)` returns `ProbeOutput(schema_slice={"github_token": "ghp_AAAAAAAAAA"}, ...)`.
  - Dispatches it through the coordinator (direct API call against `coordinator.gather(...)` is fine — does not need to be CLI-level).
  - Asserts `_ProbeOutputValidator(...)` raised `SecretLikelyFieldNameError`.
  - Asserts the coordinator caught the error: `executions["_secret_leak"].output.errors` contains the validator's error string; `confidence == "low"`.
  - If `LanguageDetectionProbe` also ran in the same gather, asserts the gather as a whole exited 0 (other probes succeeded; per ADR-0009 the surviving probe's success is enough).
- [ ] `tests/adv/test_env_var_strip.py` exists and pins the invariant: `run_allowlisted` filters env vars before invoking the subprocess; sensitive vars (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AWS_*`, `SSH_AUTH_SOCK`, `GITHUB_TOKEN`) set in the parent env never reach the child. Specifically:
  - The test uses `monkeypatch.setenv("OPENAI_API_KEY", "test-secret-must-not-leak")` (and same for `AWS_SECRET_ACCESS_KEY`, `SSH_AUTH_SOCK`, `GITHUB_TOKEN`).
  - The test patches `asyncio.create_subprocess_exec` (the underlying call) to a `MagicMock` and runs `await exec.run_allowlisted(["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=10)`.
  - Inspects the `env=` kwarg passed to `create_subprocess_exec`; asserts none of the sensitive var names are present as keys; asserts `{PATH, HOME, LANG, LC_ALL}` (or whatever the filtered allowlist is per `exec.py`) are present.
- [ ] All four tests pass on a clean Phase 0 implementation.
- [ ] Each test's docstring names the invariant being pinned (one sentence) and the ADR / `phase-arch-design.md §Edge cases` row it traces to.
- [ ] `ruff check`, `ruff format --check`, and `pytest tests/adv/test_path_traversal.py tests/adv/test_symlink_escape.py tests/adv/test_secret_leak.py tests/adv/test_env_var_strip.py -q` all pass.

## Implementation outline

1. **`test_path_traversal.py`** — Smallest test. Use `CliRunner` to invoke `cli` with a deliberately escapeful path. Assert non-zero exit and that no `.codegenie/` directory was created outside the test's `tmp_path`. The exact rejection mechanism (`Path.resolve(strict=True)` raising `FileNotFoundError`, or a `CodegenieError` subclass) is implementation detail — pin the *outcome*, not the mechanism.
2. **`test_symlink_escape.py`** — Create the symlink via `os.symlink("/etc/hosts", tmp_path/"link.js")`. Use `capture_logs()` (or the project's `structlog` capture fixture) around the CLI invocation. Assert exit 0 and the event. The test must skip on Windows (where symlinks require admin) — add `@pytest.mark.skipif(sys.platform == "win32", reason="symlink test requires POSIX")`.
3. **`test_secret_leak.py`** — Define the synthetic probe inline in the test file (it doesn't pollute `src/`; it lives in `tests/adv/`). Use `default_registry`'s test harness (or instantiate a fresh `Registry`) to dispatch it. The coordinator is the SUT.
4. **`test_env_var_strip.py`** — `monkeypatch.setenv(...)` for each sensitive var. `monkeypatch.setattr("asyncio.create_subprocess_exec", mock)` (or patch in a way that lets the test inspect the `env=` kwarg). Use `asyncio.run(exec.run_allowlisted(...))` to drive the call synchronously.
5. Add `tests/adv/__init__.py` if it doesn't exist (Step 2's adversarial tests should have already added it; verify).
6. Per `phase-arch-design.md §Testing strategy — Adversarial tests`, each test pins **one** invariant — resist the temptation to assert on multiple things in the same test. Behavioral assertion + one or two structural asserts is the right shape.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/adv/test_path_traversal.py`, `tests/adv/test_symlink_escape.py`, `tests/adv/test_secret_leak.py`, `tests/adv/test_env_var_strip.py`.

Each test pins one behavior. Write one red test per file.

```python
# tests/adv/test_path_traversal.py
"""Pins: <path> arguments containing `..` that resolve outside the repo root are refused.
Traces to: phase-arch-design.md §Edge cases (path traversal is a structural defense)."""
from click.testing import CliRunner

def test_path_traversal_rejected(tmp_path):
    # arrange: a path with `..` that resolves outside tmp_path
    escapeful = str(tmp_path / "sub" / ".." / ".." / "etc")
    from codegenie.cli import cli
    # act
    result = CliRunner().invoke(cli, ["gather", escapeful])
    # assert: rejected (non-zero exit); no `.codegenie/` written under the invalid path
    assert result.exit_code != 0
```

```python
# tests/adv/test_symlink_escape.py
"""Pins: symlinks resolving outside the analyzed-repo root are skipped by the probe walker.
Traces to: ADR-0007 (LanguageDetectionProbe contract); phase-arch-design.md §Edge cases row 4."""
import os, sys, pytest
from pathlib import Path
from click.testing import CliRunner
from structlog.testing import capture_logs

@pytest.mark.skipif(sys.platform == "win32", reason="symlink test requires POSIX")
def test_symlink_out_of_repo_skipped(tmp_path):
    # arrange: a valid .js file + a symlink to /etc/hosts
    (tmp_path / "a.js").write_text("//")
    os.symlink("/etc/hosts", tmp_path / "link.js")
    from codegenie.cli import cli
    # act
    with capture_logs() as logs:
        result = CliRunner().invoke(cli, ["gather", str(tmp_path), "--no-gitignore"])
    # assert
    assert result.exit_code == 0, result.output
    escaped = [e for e in logs if e.get("event") == "probe.symlink.escaped"]
    assert len(escaped) == 1
    # The valid .js was counted; the symlink was not.
    yaml_text = (tmp_path / ".codegenie" / "context" / "repo-context.yaml").read_text()
    assert "javascript: 1" in yaml_text or '"javascript": 1' in yaml_text
```

```python
# tests/adv/test_secret_leak.py
"""Pins: schema_slice containing a secret-shaped field name is rejected by _ProbeOutputValidator.
Traces to: ADR-0010; phase-arch-design.md §Edge cases row 5; §Scenarios — Scenario 4."""
import pytest

def test_secret_field_rejected_by_validator():
    from codegenie.coordinator.validator import _ProbeOutputValidator
    from codegenie.errors import SecretLikelyFieldNameError
    # act + assert
    with pytest.raises(SecretLikelyFieldNameError):
        _ProbeOutputValidator(
            schema_slice={"github_token": "ghp_AAAAAAAAAA"},
            confidence="high",
        )

def test_secret_leaking_probe_does_not_poison_gather(tmp_path, monkeypatch):
    # arrange: a one-off probe class that emits a secret-shaped field
    from codegenie.probes.base import Probe, ProbeOutput
    class _SecretLeakingProbe(Probe):
        name = "_secret_leak"
        version = "0.0.0"
        tier = "task_specific"
        applies_to_tasks = ["*"]
        applies_to_languages = ["*"]
        declared_inputs = ["**/*"]
        timeout_seconds = 10
        async def run(self, repo, ctx):
            return ProbeOutput(
                schema_slice={"github_token": "ghp_AAAAAAAAAA"},
                raw_artifacts=[], confidence="high",
                duration_ms=0, warnings=[], errors=[],
            )
    # act: dispatch via coordinator with LanguageDetectionProbe also in the set
    # assert: gather exits 0 (LanguageDetectionProbe succeeded);
    #         _secret_leak's ProbeExecution shows errors and confidence="low"
    # (Implementation: use coordinator.gather(...) directly; assertions per ADR-0010.)
    ...  # full body in green phase
```

```python
# tests/adv/test_env_var_strip.py
"""Pins: sensitive env vars never reach a subprocess via exec.run_allowlisted.
Traces to: ADR-0012; phase-arch-design.md §Agentic best practices — Tool-use safety."""
import asyncio
from unittest.mock import AsyncMock, patch

def test_env_strip_blocks_sensitive_vars(tmp_path, monkeypatch):
    # arrange: parent env contains the sensitive vars
    for v in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY",
              "AWS_SECRET_ACCESS_KEY", "SSH_AUTH_SOCK", "GITHUB_TOKEN"):
        monkeypatch.setenv(v, "secret-must-not-leak")
    # arrange: mock the underlying subprocess call
    captured = {}
    async def fake_create(*args, **kwargs):
        captured["env"] = kwargs.get("env", {})
        mock = AsyncMock()
        mock.communicate = AsyncMock(return_value=(b"", b""))
        mock.returncode = 0
        return mock
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create)
    # act
    from codegenie import exec as cg_exec
    asyncio.run(cg_exec.run_allowlisted(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=10,
    ))
    # assert: none of the sensitive vars made it through
    env = captured["env"]
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                "AWS_SECRET_ACCESS_KEY", "SSH_AUTH_SOCK", "GITHUB_TOKEN"):
        assert var not in env, f"{var} leaked into subprocess env"
    # assert: the filtered allowlist IS present (at least one of {PATH, HOME, LANG, LC_ALL})
    assert "PATH" in env
```

Run each. Expected failures:
- `test_path_traversal.py` — fails if S4-02's `Path.resolve(strict=True)` is missing or weakly enforced.
- `test_symlink_escape.py` — fails if S4-01's walker doesn't emit the structured event or counts the symlink.
- `test_secret_leak.py` — fails if S3-02's `_ProbeOutputValidator` doesn't raise on the secret-shaped key.
- `test_env_var_strip.py` — fails if S2-04's `run_allowlisted` doesn't filter the env.

Commit all four failing tests as the red marker.

### Green — make it pass

In most cases, the four tests should pass against a properly implemented Phase 0. If a test reveals a real defect (e.g., `_ProbeOutputValidator` doesn't actually raise on `"github_token"` because the regex is too permissive), open a one-line fix PR in the relevant upstream story's module (S3-02 for the validator, S2-04 for the exec wrapper, etc.) **before** marking this story Done — surface the issue per `CLAUDE.md`'s global Rule 12.

If the tests pass straight away, that's the expected behavior: each adversarial test is a regression gate for an invariant the harness already honors. The tests' value is *future* regression detection, not present defect uncovering.

### Refactor — clean up

- Add docstrings on each test file (top-of-file, one paragraph) explaining the invariant and the ADR / phase-arch row it traces to.
- Where the test uses `capture_logs()` or `monkeypatch.setattr` over a specific module, add a comment with the rationale — these tests are read by future contributors who need to understand "why is this brittle-looking patch necessary?"
- Confirm `pytest tests/adv/` runs all seven tests (the three from Step 2 plus the four from this story); the suite should be a hermetic, fast-running set (target: each test < 500 ms; the full adversarial suite < 5 s).
- If a test relies on `CliRunner`, prefer `result.output` over `result.stderr` for assertions about logged events (click's `CliRunner` captures stdout and stderr together by default).
- Run `ruff format` over the new test files.

## Files to touch

| Path | Why |
|---|---|
| `tests/adv/test_path_traversal.py` | New test — pins the `Path.resolve(strict=True)` chokepoint |
| `tests/adv/test_symlink_escape.py` | New test — pins the `LanguageDetectionProbe` walker's symlink-escape skip |
| `tests/adv/test_secret_leak.py` | New test — pins `_ProbeOutputValidator`'s secret-shaped-field rejection + the coordinator's "gather continues" policy |
| `tests/adv/test_env_var_strip.py` | New test — pins `exec.run_allowlisted`'s env-allowlist filter |
| `tests/adv/__init__.py` | New if not already from Step 2 — pytest package marker |

## Out of scope

- **`test_no_shell_true.py`, `test_no_network_imports.py`, `test_yaml_unsafe_load.py`** — already landed in Step 2 per `High-level-impl.md §Step 2 Done criteria`. This story does not duplicate them.
- **`test_pyproject_fence.py`** — landed in Step 1 per `High-level-impl.md §Step 1`. The `fence` job is its own CI step; this story does not extend it.
- **Adversarial fuzz testing of attacker-controlled inputs** (e.g., crafted YAML files in the analyzed repo) — Phase 1 introduces the first probe (`NodeManifestProbe`) that reads attacker-controllable files; the fuzz suite lives there.
- **CVE feed adversarials** — Phase 3, per `phase-arch-design.md §Testing strategy — Adversarial tests`.
- **Prompt-injection adversarials** — Phase 4, per the same.
- **Performance regression tests** (`tests/bench/`) — handled by S5-01.
- **Documentation of the adversarial-suite contributor convention** — Phase 5 (`docs/contributing.md` extension per S5-02).

## Notes for the implementer

- Each adversarial test pins **one** invariant. If you find yourself adding a second assertion, ask: is that assertion the same invariant phrased differently, or a new invariant? If new, it goes in its own test file.
- The tests are not load-bearing in the bullet-tracer sense (S4-04 owns that). These are *regression* gates: they catch a future PR that silently weakens an invariant. The right shape is "small, fast, focused, and brittle in the *right* way — they fail if the invariant fails."
- `test_symlink_escape.py` requires POSIX. Skip on Windows. Symlink tests are notoriously flaky on Windows even with admin (developer-mode varies); the `@pytest.mark.skipif` is the right defense.
- `test_env_var_strip.py` mocks `asyncio.create_subprocess_exec`. This is intentional: the goal is to inspect what `run_allowlisted` *would have passed* to the subprocess, not to actually spawn one. A real-subprocess test is a Phase 2+ concern (real `git` invocation against the chokepoint) and lives in the `test_exec.py` unit test from S2-04.
- `test_secret_leak.py`'s synthetic `_SecretLeakingProbe` class is **only** in the test file — do **not** register it via `@register_probe` (it would pollute `default_registry`). Either instantiate the coordinator with a fresh `Registry()` containing just this probe (and `LanguageDetectionProbe`), or pass the probe class explicitly to `coordinator.gather(probes=[...])`.
- The secret regex from S3-02's `_ProbeOutputValidator` is `(?i)(token|secret|password|api[_-]?key|credential|private[_-]?key|ghp_|sk-)` (per `final-design.md §2.6`). `"github_token"` matches `"token"`; `"api_key"` matches `"api[_-]?key"`. If a test fails because the regex didn't match a name you expected, the regex needs widening — surface this as a follow-up to S3-02, do not loosen the adversarial assertion.
- The path-traversal test deliberately does **not** assert a specific exit code. Different rejection mechanisms (`Path.resolve(strict=True)` raising `FileNotFoundError` → unhandled → exit 1; a `CodegenieError` subclass → exit per the dispatch table) are both acceptable; the structural invariant is "this is refused with a non-zero exit." Pinning a specific exit code couples the test to the mechanism, which violates `CLAUDE.md` Rule 3 ("Surgical changes — don't refactor what isn't broken"): if S4-02 later picks a different rejection code, the test should not need to follow.
- Avoid `pytest.mark.parametrize` here. Each test pins one invariant; parametrized adversarial tests obscure which invariant failed. Per `phase-arch-design.md §Testing strategy — Adversarial tests`, the suite is a set of clearly named individual tests.
