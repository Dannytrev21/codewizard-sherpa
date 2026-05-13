# Story S2-04 — Subprocess allowlist chokepoint

**Step:** Step 2 — Plant the frozen contracts (probe ABC, hashing, exec allowlist, schema, error hierarchy)
**Status:** Done (2026-05-13)
**Effort:** M
**Depends on:** S2-01
**ADRs honored:** ADR-0012

## Evidence

- Implementation: [`src/codegenie/exec.py`](../../../../src/codegenie/exec.py) — `ALLOWED_BINARIES`, `ProcessResult`, `run_allowlisted`, `_RUNNING_PROCS`, `_filter_env`, `_escalate_and_kill`.
- Tests: [`tests/unit/test_exec.py`](../../../../tests/unit/test_exec.py) — 13 tests (Test 1 is parametrized x4); covers AC-1 through AC-14 plus structural pins.
- Attempt log: [`_attempts/S2-04.md`](_attempts/S2-04.md)
- Gates: `pytest 156/156`, `ruff check` clean, `ruff format --check` clean, `mypy --strict` clean (11 src files), `lint-imports` 2 kept / 0 broken, `scripts/check_forbidden_patterns.py src/codegenie/exec.py` clean.

### AC → test mapping

| AC | Evidence (test name in `tests/unit/test_exec.py`) |
|---|---|
| `ALLOWED_BINARIES == frozenset({"git"})` | `test_disallowed_binary_rejected_before_spawn` (rejects every non-`git` arg) |
| `ProcessResult` frozen + typed | `test_git_rev_parse_happy_path_and_result_frozen_typed` |
| `run_allowlisted` signature `env_extra: ... | None = None` | `test_run_allowlisted_signature_default_is_none` |
| AC-4 (a) allowlist before spawn | `test_disallowed_binary_rejected_before_spawn` — spy `assert_not_awaited()` |
| AC-4 (b) `cwd` existence + directory-ness | `test_cwd_rejection_paths` |
| AC-4 (c) no `shell=` kwarg | `test_spawn_kwargs_pin_stdin_devnull_and_no_shell` |
| AC-4 (d) `stdin=DEVNULL` | `test_spawn_kwargs_pin_stdin_devnull_and_no_shell` |
| AC-4 (e/f) env subset of safe baseline | `test_child_env_keyset_subset_of_safe_baseline` |
| AC-5 timeout escalation + `elapsed_ms` | `test_timeout_escalates_sigterm_then_sigkill` |
| AC-6 missing binary → `ToolMissingError` w/ hint | `test_missing_binary_raises_tool_missing_with_hint` |
| AC-7 weakref table register/clear (all 4 paths) | `test_running_procs_registered_during_run_cleared_after` + assertions in timeout, tool-missing, and happy-path tests |
| AC-10 `ProcessResult` immutable + typed | `test_git_rev_parse_happy_path_and_result_frozen_typed` |
| AC-11 signature default sentinel | `test_run_allowlisted_signature_default_is_none` |
| AC-12 argv shape (empty / abs / rel paths) | `test_disallowed_binary_rejected_before_spawn` (parametrized) |
| AC-13 env_extra sensitive-key drop + structlog event | `test_env_extra_drops_sensitive_keys` (via `structlog.testing.capture_logs`) |

### Action items surfaced (deviations from arch / ADR-0012, tracked in story prologue)

These are documented in the Validation notes at the top of this story; this implementation honors the story's AC text, which is the contract. The arch and ADR amendments are out-of-scope follow-ups:

1. ADR-0012 §Decision bullet 5 + arch line 537 should be amended to read "wrapper enforces existence + directory-ness; the caller enforces under-repo-root."
2. ADR-0012 §Decision + arch §Component design line 534 should be amended to show `env_extra: dict[str, str] | None = None` instead of the literal `{}` default.

## Validation notes

**Validated:** 2026-05-13
**Verdict:** HARDENED (phase-story-validator v1)
**Findings addressed:** 25 total — 6 blocks, 13 hardens, 6 nits/informational

**Surfaced for follow-up (does NOT block executor):**
- ADR-0012 §Decision bullet 5 + `phase-arch-design.md §Component design` line 537 + arch §Edge cases row 4 all say the wrapper enforces "`cwd` resolved + must be under the analyzed-repo root." This story narrows the contract to "wrapper enforces exists + is-a-directory; under-repo-root is caller responsibility" (no `analyzed_repo_root` parameter is added in Phase 0). Reasoning: Phase 0's single callsite already resolves the repo root in the CLI (`Path.resolve(strict=True)`); adding a wrapper parameter for one callsite is YAGNI. **Action item:** amend ADR-0012 §Decision bullet 5 and arch line 537 to read "wrapper enforces existence + directory-ness; the *caller* enforces under-repo-root." Tracked here so the deviation is not silent.
- Arch line 534 + ADR-0012 line 26 show the signature with `env_extra: dict[str, str] = {}` (the Python mutable-default footgun). This story corrects to `env_extra: dict[str, str] | None = None` per AC-3. **Action item:** amend ADR-0012 §Decision and arch §Component design to show the `| None = None` form. Since the signature is a "stable contract" per arch line 271, the deviation must land in writing.

**Changes applied:** new ACs AC-10 through AC-14; strengthened ACs AC-1, AC-4(a), AC-4(b), AC-4(c)+(d), AC-4(f), AC-5, AC-6, AC-7; replaced flaky network-based timeout test with a deterministic mock-based escalation test; added explicit child-env spy pattern in env-strip test; added kwargs-spy test for `stdin=DEVNULL`; pinned `ProcessResult` immutability; pinned the signature default sentinel via `inspect.signature`. Full audit log: [`_validation/S2-04-exec-allowlist.md`](_validation/S2-04-exec-allowlist.md).

## Context

`src/codegenie/exec.py` is the **only** path from `codegenie` source to an external binary — for the entire project lifetime, not just Phase 0. ADR-0012 is the load-bearing chokepoint: Phase 7's distroless probes will add ~30 subprocess callsites and retrofitting an allowlist after the fact is "not bounded work" (`critique.md §1.3`). Phase 0 has exactly one subprocess call (`git rev-parse HEAD` for `RepoSnapshot.git_commit`), but the wrapper is the discipline that scales. The wrapper enforces six invariants in one place: allowlist membership, `shell=False`, `stdin=DEVNULL`, filtered env (PATH/HOME/LANG/LC_ALL + extras; strips `OPENAI_API_KEY`, `AWS_*`, `SSH_AUTH_SOCK`, `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`), `cwd`-under-repo-root, and SIGKILL at `1.5 × timeout_s`. By Phase 7 this story's costs are sunk and the wrapper has saved 30 audit conversations.

Foundational: S3-05's coordinator constructs `RepoSnapshot` via this wrapper, S4-02's tool-readiness check probes `git` through it, and every Phase 1+ probe that shells out (tree-sitter, scip-typescript, semgrep, syft, dive…) is one line of `ALLOWED_BINARIES`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Subprocess allowlist` — public API: `ALLOWED_BINARIES: frozenset[str]`, `ProcessResult` frozen dataclass, `async def run_allowlisted(argv, *, cwd, timeout_s, env_extra) -> ProcessResult`; six enforced invariants; weakref process-tracking table for coordinator-cancel SIGKILL.
  - `../phase-arch-design.md §Edge cases` — row 2 (timeout → SIGKILL via `1.5× × timeout_s` grace), row 4 (symlink-out-of-repo refusal also applies to `cwd`), the implicit invariant that the wrapper is the *only* importer of `asyncio.create_subprocess_exec` in `src/codegenie/`.
  - `../phase-arch-design.md §Agentic best practices — Tool-use safety` — restates the env-strip and filesystem-scope rules and names `tests/adv/test_no_shell_true.py` and `test_env_var_strip.py` as the structural pins.
  - `../phase-arch-design.md §Harness engineering — Determinism` — Phase 0 has no probabilistic component; this wrapper is part of the deterministic chassis.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0012-subprocess-allowlist-chokepoint.md` — ADR-0012 — the decision this story implements; the `forbidden-patterns` pre-commit hook and `tests/adv/test_no_shell_true.py` AST scan are the belt-and-suspenders enforcements (S1-04 ships the hook, this story ships the wrapper).
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — defines the parallel chokepoint discipline that S3-03 implements; this story's wrapper is the subprocess sibling of that one.
- **Source design:**
  - `../final-design.md §2.5` — Subprocess allowlist; adopted as load-bearing.
- **Existing code (if any):**
  - `src/codegenie/errors.py` — `DisallowedSubprocessError`, `ProbeTimeoutError`, `ToolMissingError` (all from S2-01).
- **External docs:**
  - `asyncio.create_subprocess_exec` docs — the wrapper invokes this, not `subprocess.run`, because the coordinator is async (ADR-0005 — coordinator async from day one).

## Goal

`from codegenie.exec import ALLOWED_BINARIES, run_allowlisted` succeeds; `await run_allowlisted(["git", "rev-parse", "HEAD"], cwd=<repo>, timeout_s=10)` returns a `ProcessResult(returncode=0, stdout=b"...sha\n", stderr=b"")`; `await run_allowlisted(["bash", "-c", "echo"], cwd=<repo>, timeout_s=1)` raises `DisallowedSubprocessError` *before* spawning anything.

## Acceptance criteria

- [ ] `src/codegenie/exec.py` exports `ALLOWED_BINARIES: frozenset[str] = frozenset({"git"})` at module scope (Phase 0 set is exactly `{"git"}`; future binaries are deliberate-PR additions per ADR-0012).
- [ ] `src/codegenie/exec.py` exports `ProcessResult` as a `@dataclass(frozen=True)` with fields `returncode: int`, `stdout: bytes`, `stderr: bytes`.
- [ ] `src/codegenie/exec.py` exports `async def run_allowlisted(argv: list[str], *, cwd: Path, timeout_s: float, env_extra: dict[str, str] | None = None) -> ProcessResult`. **Default for `env_extra` is `None`** then normalized inside the body — never `{}` as a literal default (mutable-default footgun). *(Note: this signature differs from arch line 534 / ADR-0012 line 26 which both show the literal `{}` mutable default. The deviation is the safer Python form; see Validation notes for the ADR-amendment action item.)*
- [ ] The wrapper enforces, in order: (a) `argv[0] not in ALLOWED_BINARIES` → `DisallowedSubprocessError` raised **before** any process spawn — pinned in the test by patching `asyncio.create_subprocess_exec` with a spy whose `side_effect` is `AssertionError("must not spawn")`; the test asserts the spy was **never awaited** when the call raises `DisallowedSubprocessError` (validator: hardened — original test would pass under a spawn-then-kill mutant); (b) `cwd` resolved via `Path.resolve(strict=True)`, must be a directory; the wrapper rejects non-existent or non-directory `cwd` with `FileNotFoundError` / `NotADirectoryError`. **Under-repo-root enforcement is the caller's responsibility**, not the wrapper's, in Phase 0 — see Validation notes for the ADR-amendment action item that reconciles this with ADR-0012 §Decision bullet 5 and arch line 537; (c) `shell=False` is the implicit behavior of `asyncio.create_subprocess_exec`; this is pinned by a test that spies `asyncio.create_subprocess_exec`, runs the happy path, and asserts the captured `kwargs` contains **no** `shell` key (defense against a refactor that switches to `subprocess.run(..., shell=True)`); (d) `stdin=asyncio.subprocess.DEVNULL` is passed explicitly and pinned by the same spy asserting `captured_kwargs["stdin"] is asyncio.subprocess.DEVNULL` (validator: added — original ACs were unpinned and a mutant passing `stdin=PIPE` would have slipped through); (e) env constructed by **omission** (never `os.environ.copy()`) as `{"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", ""), "LANG": os.environ.get("LANG", "C"), "LC_ALL": os.environ.get("LC_ALL", "C")} | env_extra`; (f) The test spies `asyncio.create_subprocess_exec` and asserts the captured `env=` kwarg's **keyset is a subset of** `{"PATH", "HOME", "LANG", "LC_ALL"} ∪ env_extra.keys()` — this single structural assertion subsumes "the five sensitive keys are absent" because env-by-omission means **any** unlisted key is structurally absent (validator: hardened — original test only inspected the private `_filter_env` helper and would not catch a mutant that called `create_subprocess_exec(env=os.environ.copy())` while leaving the helper correct).
- [ ] Timeout discipline: `asyncio.wait_for(process.communicate(), timeout=timeout_s)`; on `asyncio.TimeoutError`, send `SIGTERM`, give 100 ms grace, then `SIGKILL` at `1.5 × timeout_s` cumulative; raise `ProbeTimeoutError` whose `str(exc)` contains the substring `"elapsed_ms="` followed by at least one digit (pinned via `re.search(r"elapsed_ms=\d+", str(exc))`). The escalation order — SIGTERM first, then SIGKILL — is pinned in the test via a fake `Process` whose `terminate`/`kill`/`wait` methods are spies; assertions: (i) `terminate` called exactly once, (ii) `kill` called after `terminate` and within `[timeout_s, 1.5·timeout_s + 0.2s]` wall-time, (iii) the call to `kill` happens after at least ~100 ms of grace following `terminate`. The fake `Process.communicate()` awaits an `asyncio.Event` that the test never sets, guaranteeing the timeout fires deterministically (no network dependency; validator: replaced flaky `ls-remote https://10.255.255.1/` pattern). After the wrapper returns/raises, `_RUNNING_PROCS` must contain no entry for the fake pid (cleanup-on-timeout).
- [ ] If the binary is missing on `$PATH` (`FileNotFoundError` from `asyncio.create_subprocess_exec`), raise `ToolMissingError` whose `str(exc)` matches the regex `r"git.*(install|PATH)"` (binary name plus an install/PATH hint); the wrapper does **not** silently swallow `FileNotFoundError`. The test asserts via `pytest.raises(ToolMissingError, match=r"git.*(install|PATH)")` (validator: hardened — original AC said "with an install hint in the message" but no test inspected the message; a mutant raising bare `ToolMissingError()` would have passed).
- [ ] A weakref process-tracking table (`weakref.WeakValueDictionary[int, Process]`) registers running children so a coordinator-cancel path can SIGKILL stragglers (`phase-arch-design.md §Component design — Subprocess allowlist`); module-level constant, not per-instance. **Observable invariants** pinned in the test (validator: hardened — original AC was unpinned and the table could be silently removed without any test failing, leaving Phase 7's coordinator-cancel a no-op): (i) **register-during-run** — while a fake `Process` is mid-`communicate()` (event-gated), `proc.pid in _RUNNING_PROCS` evaluates `True`; (ii) **clear-after-success** — after happy-path return, `_RUNNING_PROCS.get(proc.pid)` is `None`; (iii) **clear-after-timeout** — after a `ProbeTimeoutError` raise, the table contains no entry for that pid; (iv) **clear-after-tool-missing** — after a `ToolMissingError` raise (binary missing), no orphan entry exists. Implementation must `pop(pid, None)` in a `finally:` block (not rely on GC).
- [ ] `ProcessResult` is immutable and typed: `with pytest.raises(dataclasses.FrozenInstanceError): result.returncode = 1`; `assert ProcessResult.__dataclass_params__.frozen is True`; `assert isinstance(result.stdout, bytes) and isinstance(result.stderr, bytes) and isinstance(result.returncode, int)` (validator: added AC-10 — original happy-path test only checked `returncode == 0` and `len(stdout.strip()) == 40`; a mutant typing `stderr: str` or omitting `frozen=True` would have passed).
- [ ] **Signature default sentinel pin** (mutation-proof guard against the mutable-default footgun regressing): `import inspect; sig = inspect.signature(run_allowlisted); assert sig.parameters["env_extra"].default is None` (validator: added AC-11 — implementer-note prose is not a test; this one-liner makes the footgun a build-breaker if a future refactor reverts to `= {}`).
- [ ] **Argv shape validation** (validator: added AC-12 — original spec was silent on these; the wrapper is forever, the cost of pinning now is one extra test): (a) `argv=[]` raises `DisallowedSubprocessError` (matched first, before any other check; pin with a test); (b) `argv[0]` is matched against `ALLOWED_BINARIES` **as-is** (no `os.path.basename`); `argv=["/usr/bin/git", ...]` and `argv=["./git", ...]` both raise `DisallowedSubprocessError`. Callers MUST pass bare binary names; PATH resolution is the OS's job. This is the safer default — basename-stripping can be added later via an ADR amendment if needed.
- [ ] **Env-extra hygiene** (validator: added AC-13 — original spec left `env_extra` as a free passthrough, defeating the omission discipline if a future caller passes `{"OPENAI_API_KEY": "..."}` or overrides `PATH`): (a) keys in `env_extra` whose **uppercased** form matches any of `{"SSH_AUTH_SOCK", "GITHUB_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}` or starts with `"AWS_"` are **silently dropped** (omitted from the child env) and a structlog `subproc.env_extra.sensitive_key_dropped` event is emitted at WARNING level naming the offending key; (b) `PATH` in `env_extra` overrides the baseline `PATH` (intentional — supports test fixtures monkeypatching PATH); pin with a test. The intent: `env_extra` is a *narrow* passthrough for legitimate extras (`GIT_SSH_COMMAND`, `LANG`), not a backdoor for re-introducing what the baseline filtered out.
- [ ] `tests/unit/test_exec.py` covers (validator: expanded — every AC above must have ≥1 mutation-resistant test): (1) allowlist rejection with **spy assertion that `asyncio.create_subprocess_exec` was never awaited** for `["bash", ...]`, `["/usr/bin/git", ...]`, `["./git", ...]`, and `[]`; (2) env-strip via **kwarg-spy on `asyncio.create_subprocess_exec`** asserting `captured.kwargs["env"]`'s keyset is a subset of the four-baseline keys ∪ `env_extra.keys()` minus sensitive keys; (3) `cwd` rejection for non-existent path (`FileNotFoundError`) and for a regular file (`NotADirectoryError`); (4) timeout via fake `Process` with event-gated `communicate`, asserting SIGTERM-then-SIGKILL escalation order, wall-time bound, `elapsed_ms=` in the error message, and `_RUNNING_PROCS` cleanup; (5) `ToolMissingError` with `match=r"git.*(install|PATH)"`; (6) `git rev-parse HEAD` happy path against a real git fixture, asserting `ProcessResult` immutability and field types; (7) signature-default-sentinel one-liner via `inspect.signature`; (8) `stdin=DEVNULL` and absence of `shell=` kwarg via kwarg-spy; (9) `env_extra` sensitive-key drop with structlog event capture; (10) weakref-table register-during-run and clear-after for the four exit paths.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/exec.py`, and `pytest tests/unit/test_exec.py -q` are clean.

## Implementation outline

1. Write `tests/unit/test_exec.py` first — ten anchoring tests as described in the TDD plan. Use `pytest.mark.asyncio` for the async tests; the fixture `dev` extra (S1-02) already includes `pytest-asyncio` (`asyncio_mode = "auto"`). Confirm `ImportError`.
2. Author `src/codegenie/exec.py`. Module docstring naming ADR-0012; `from __future__ import annotations`; `import asyncio`, `import os`, `import signal`, `import weakref`; `from dataclasses import dataclass`; `from pathlib import Path`; `from codegenie.errors import DisallowedSubprocessError, ProbeTimeoutError, ToolMissingError`.
3. Define `ALLOWED_BINARIES: frozenset[str] = frozenset({"git"})` and `ProcessResult` dataclass. Define module-level `_RUNNING_PROCS: weakref.WeakValueDictionary[int, asyncio.subprocess.Process] = weakref.WeakValueDictionary()`.
4. Implement `_filter_env(env_extra)`: build the four-key safe baseline, merge `env_extra`, return a new dict. Never mutate `os.environ`.
5. Implement `run_allowlisted`. Steps: (a) check allowlist; (b) resolve `cwd` and assert it exists + is a directory; (c) `proc = await asyncio.create_subprocess_exec(*argv, cwd=cwd, env=_filter_env(env_extra), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)`; (d) `_RUNNING_PROCS[proc.pid] = proc`; (e) try `stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)`; on `TimeoutError`, escalate (SIGTERM → 100 ms → SIGKILL), then raise `ProbeTimeoutError`; (f) return `ProcessResult(proc.returncode, stdout, stderr)`.
6. Map `FileNotFoundError` (binary missing) to `ToolMissingError`; map permission errors on `cwd` to `OSError` propagation (caller's bug).
7. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/exec.py`, `pytest tests/unit/test_exec.py -q`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_exec.py`.

Ten mutation-resistant behaviors anchor this story (validator: expanded from 6 to 10). Each pins one chokepoint invariant. Each should fail before the implementation exists. The unifying pattern: tests **spy `asyncio.create_subprocess_exec`** to observe what the chokepoint actually passes to the OS — that's the boundary every AC lives on. Helper-introspection (`_filter_env(...)`) is rejected as the primary test surface because it doesn't catch a mutant that bypasses the helper.

```python
# tests/unit/test_exec.py
import asyncio
import dataclasses
import inspect
import re
import subprocess
from pathlib import Path
from unittest import mock
import pytest

# ───────────────────────────────────────────────────────────────────────────
# Test 1 — Allowlist rejection happens BEFORE any spawn
# ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("argv", [
    ["bash", "-c", "echo hi"],
    ["/usr/bin/git", "rev-parse", "HEAD"],   # absolute path is NOT in the set
    ["./git", "rev-parse", "HEAD"],          # relative path is NOT in the set
    [],                                       # empty argv
])
async def test_disallowed_binary_rejected_before_spawn(tmp_path: Path, monkeypatch, argv):
    from codegenie.exec import run_allowlisted
    from codegenie.errors import DisallowedSubprocessError
    # Guards the spawn-then-kill mutant and the basename-stripping mutant.
    spy = mock.AsyncMock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    with pytest.raises(DisallowedSubprocessError):
        await run_allowlisted(argv, cwd=tmp_path, timeout_s=1.0)
    spy.assert_not_awaited()

# ───────────────────────────────────────────────────────────────────────────
# Test 2 — Child env is constructed by omission (chokepoint-level, not helper)
# ───────────────────────────────────────────────────────────────────────────
async def test_child_env_keyset_subset_of_safe_baseline(tmp_path: Path, monkeypatch):
    """Spy on the chokepoint and assert env keyset is a subset of the safe baseline.

    Subsumes 'OPENAI_API_KEY/AWS_*/SSH_AUTH_SOCK/GITHUB_TOKEN/ANTHROPIC_API_KEY never reach
    the child' — by omission, an unlisted parent-env key is structurally absent.
    Catches the `env=os.environ.copy()` mutant that leaves _filter_env correct.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-real")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "AKIA-not-real")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/x")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-not-real")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-real")

    from codegenie.exec import run_allowlisted

    fake_proc = mock.MagicMock()
    fake_proc.pid = 99999
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"git version 2.0\n", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    await run_allowlisted(["git", "--version"], cwd=tmp_path, timeout_s=10.0,
                          env_extra={"GIT_SSH_COMMAND": "ssh -i /tmp/k"})

    captured_env = spy.await_args.kwargs["env"]
    allowed = {"PATH", "HOME", "LANG", "LC_ALL", "GIT_SSH_COMMAND"}
    assert set(captured_env.keys()) <= allowed, f"leaked: {set(captured_env) - allowed}"
    # None of the five sensitive keys are present:
    for k in ("OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "SSH_AUTH_SOCK",
              "GITHUB_TOKEN", "ANTHROPIC_API_KEY"):
        assert k not in captured_env

# ───────────────────────────────────────────────────────────────────────────
# Test 3 — stdin=DEVNULL + no shell= kwarg are pinned via the same spy
# ───────────────────────────────────────────────────────────────────────────
async def test_spawn_kwargs_pin_stdin_devnull_and_no_shell(tmp_path: Path, monkeypatch):
    """Catches the stdin=PIPE mutant and any switch to subprocess.run(..., shell=True)."""
    from codegenie.exec import run_allowlisted

    fake_proc = mock.MagicMock()
    fake_proc.pid = 99998
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    await run_allowlisted(["git", "--version"], cwd=tmp_path, timeout_s=10.0)

    kwargs = spy.await_args.kwargs
    assert kwargs["stdin"] is asyncio.subprocess.DEVNULL
    assert "shell" not in kwargs  # create_subprocess_exec has no shell kwarg by design

# ───────────────────────────────────────────────────────────────────────────
# Test 4 — cwd must exist and be a directory
# ───────────────────────────────────────────────────────────────────────────
async def test_cwd_rejection_paths(tmp_path: Path):
    from codegenie.exec import run_allowlisted
    bogus = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):
        await run_allowlisted(["git", "--version"], cwd=bogus, timeout_s=1.0)
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    with pytest.raises(NotADirectoryError):
        await run_allowlisted(["git", "--version"], cwd=a_file, timeout_s=1.0)

# ───────────────────────────────────────────────────────────────────────────
# Test 5 — Timeout escalation: SIGTERM → ~100ms grace → SIGKILL; elapsed_ms in msg;
#                              _RUNNING_PROCS cleared on the way out.
# ───────────────────────────────────────────────────────────────────────────
async def test_timeout_escalates_sigterm_then_sigkill(tmp_path: Path, monkeypatch):
    """Deterministic, network-free. Catches: immediate-SIGKILL mutant, missing-elapsed-
    ms mutant, leaked-child mutant, missing-finally-pop mutant."""
    from codegenie.exec import run_allowlisted, _RUNNING_PROCS
    from codegenie.errors import ProbeTimeoutError

    hang = asyncio.Event()  # never set
    fake_proc = mock.MagicMock()
    fake_proc.pid = 77777
    fake_proc.returncode = -9
    fake_proc.communicate = mock.AsyncMock(side_effect=lambda: hang.wait())
    fake_proc.terminate = mock.MagicMock()
    fake_proc.kill = mock.MagicMock()
    fake_proc.wait = mock.AsyncMock(return_value=-9)

    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    start = asyncio.get_event_loop().time()
    with pytest.raises(ProbeTimeoutError) as exc_info:
        await run_allowlisted(["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=0.2)
    elapsed = asyncio.get_event_loop().time() - start

    assert fake_proc.terminate.call_count == 1
    assert fake_proc.kill.call_count >= 1
    # SIGKILL happens after grace, within 1.5×timeout + slack
    assert 0.2 <= elapsed <= (1.5 * 0.2) + 0.5
    assert re.search(r"elapsed_ms=\d+", str(exc_info.value))
    assert 77777 not in _RUNNING_PROCS  # cleaned up in finally:

# ───────────────────────────────────────────────────────────────────────────
# Test 6 — Missing binary → ToolMissingError with git+install/PATH in message
# ───────────────────────────────────────────────────────────────────────────
async def test_missing_binary_raises_tool_missing_with_hint(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    from codegenie.exec import run_allowlisted, _RUNNING_PROCS
    from codegenie.errors import ToolMissingError
    with pytest.raises(ToolMissingError, match=r"git.*(install|PATH)"):
        await run_allowlisted(["git", "--version"], cwd=tmp_path, timeout_s=1.0)
    # No orphan weakref entry from the failed spawn:
    assert len(_RUNNING_PROCS) == 0

# ───────────────────────────────────────────────────────────────────────────
# Test 7 — Happy path with real git: ProcessResult immutable + typed fields
# ───────────────────────────────────────────────────────────────────────────
async def test_git_rev_parse_happy_path_and_result_frozen_typed(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@e.com", "-c", "user.name=t",
                    "commit", "--allow-empty", "-m", "x"], cwd=tmp_path, check=True)
    from codegenie.exec import run_allowlisted, ProcessResult, _RUNNING_PROCS
    result = await run_allowlisted(["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=10.0)
    assert result.returncode == 0
    assert isinstance(result.stdout, bytes) and isinstance(result.stderr, bytes)
    assert isinstance(result.returncode, int)
    assert len(result.stdout.strip()) == 40
    # Immutability:
    assert ProcessResult.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.returncode = 1  # type: ignore[misc]
    # Weakref table cleared on the success path:
    assert len(_RUNNING_PROCS) == 0

# ───────────────────────────────────────────────────────────────────────────
# Test 8 — Signature default sentinel pin (mutable-default-footgun guard)
# ───────────────────────────────────────────────────────────────────────────
def test_run_allowlisted_signature_default_is_none():
    """One-line mutation-proof guard. Reverts to `= {}` are build-breakers."""
    from codegenie.exec import run_allowlisted
    sig = inspect.signature(run_allowlisted)
    assert sig.parameters["env_extra"].default is None

# ───────────────────────────────────────────────────────────────────────────
# Test 9 — env_extra hygiene: sensitive keys dropped + structlog event
# ───────────────────────────────────────────────────────────────────────────
async def test_env_extra_drops_sensitive_keys(tmp_path: Path, monkeypatch, caplog):
    """env_extra is a narrow passthrough, not a backdoor."""
    from codegenie.exec import run_allowlisted

    fake_proc = mock.MagicMock()
    fake_proc.pid = 88888
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    await run_allowlisted(
        ["git", "--version"], cwd=tmp_path, timeout_s=10.0,
        env_extra={"OPENAI_API_KEY": "sk-leak",
                   "AWS_FOO": "leak",
                   "GIT_SSH_COMMAND": "ssh -i /k"},
    )
    captured = spy.await_args.kwargs["env"]
    assert "OPENAI_API_KEY" not in captured
    assert "AWS_FOO" not in captured
    assert "GIT_SSH_COMMAND" in captured  # legitimate extra survives

# ───────────────────────────────────────────────────────────────────────────
# Test 10 — Weakref table: registered during run, cleared after
# ───────────────────────────────────────────────────────────────────────────
async def test_running_procs_registered_during_run_cleared_after(tmp_path: Path, monkeypatch):
    """Pins the Phase-7 coordinator-cancel chokepoint promise."""
    from codegenie.exec import run_allowlisted, _RUNNING_PROCS

    seen_during_run: list[bool] = []
    release = asyncio.Event()

    fake_proc = mock.MagicMock()
    fake_proc.pid = 66666
    fake_proc.returncode = 0

    async def comm():
        seen_during_run.append(66666 in _RUNNING_PROCS)
        release.set()
        return (b"", b"")
    fake_proc.communicate = mock.AsyncMock(side_effect=comm)

    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    await run_allowlisted(["git", "--version"], cwd=tmp_path, timeout_s=5.0)
    assert seen_during_run == [True]
    assert 66666 not in _RUNNING_PROCS  # finally: pop ran
```

Run; confirm all ten fail with `ImportError`. Commit as the red marker.

### Green — make it pass

`src/codegenie/exec.py`: implement the minimum that turns the ten tests green.

- `ALLOWED_BINARIES = frozenset({"git"})`.
- `ProcessResult` dataclass — `@dataclass(frozen=True)`.
- `_RUNNING_PROCS` weakref dict at module scope, registered during run, popped in `finally:`.
- `_filter_env(env_extra: dict[str, str] | None) -> dict[str, str]`: returns a fresh dict with the four-key safe baseline plus any `env_extra` *minus* its sensitive keys (the `OPENAI_API_KEY`/`AWS_*`/`SSH_AUTH_SOCK`/`GITHUB_TOKEN`/`ANTHROPIC_API_KEY` set is filtered from both `os.environ` and `env_extra`). Never reads those keys from `os.environ` — by *omission*, not by deletion (safer: never copy them in). Emit a structlog WARNING when an `env_extra` sensitive key is dropped.
- `run_allowlisted`: (i) allowlist check on `argv` — handle `argv=[]` and absolute/relative paths by raising `DisallowedSubprocessError` before any spawn; (ii) `Path.resolve(strict=True)` on `cwd`, assert is_dir; (iii) spawn with the filtered env; (iv) `_RUNNING_PROCS[proc.pid] = proc`; (v) await with timeout; (vi) on timeout: `proc.terminate()`, wait ~100 ms, `proc.kill()`, `await proc.wait()`, raise `ProbeTimeoutError(f"... elapsed_ms={int(elapsed*1000)} ...")`; (vii) map `FileNotFoundError` (binary missing on PATH) to `ToolMissingError(f"{argv[0]} not on PATH — install it or fix PATH")` so the regex `r"git.*(install|PATH)"` matches; (viii) `try/finally:` ensure `_RUNNING_PROCS.pop(proc.pid, None)` on every exit path; (ix) return `ProcessResult(returncode, stdout, stderr)`.

### Refactor — clean up

- Type hints on every parameter and return; `mypy --strict` clean.
- Docstring on `run_allowlisted` enumerating the six invariants verbatim from ADR-0012 §Decision.
- Module docstring naming the chokepoint discipline and pointing at `tests/adv/test_no_shell_true.py` (S2's adversarial suite) as the structural defense.
- Add structured logging at DEBUG: `subproc.spawn` (with `argv[0]`, `cwd`, `timeout_s`), `subproc.exit` (with `returncode`, `elapsed_ms`), `subproc.timeout` (with `elapsed_ms`). Use `structlog.get_logger()` — `logging.py` (S2-01) already configures it.
- Idempotence on `_RUNNING_PROCS` cleanup: weakrefs handle GC, but explicitly `_RUNNING_PROCS.pop(proc.pid, None)` in the `finally` block to make the table accurate during the run.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec.py` | New — the allowlist chokepoint per ADR-0012 |
| `tests/unit/test_exec.py` | New — pins the six invariants |

## Out of scope

- **`tests/adv/test_no_shell_true.py` AST scan** — handled by S2-05 or S4-05's adversarial suite (the manifest places it in S4-05). This story does not need a self-AST-scan; the wrapper *is* the implementation.
- **`forbidden-patterns` pre-commit hook regex set** — handled by S1-04. This story relies on that hook to block `subprocess.run(..., shell=True)` in any new code; it does not configure the hook.
- **`tool-readiness` check that probes `git` at startup and caches at `~/.codegenie/.tool-cache.json`** — handled by S4-02 (CLI startup wiring). This story exposes the primitive; the cache is one level up.
- **Coordinator-cancel SIGKILL invocation** — handled by S3-05. This story exposes the `_RUNNING_PROCS` table; S3-05's coordinator iterates it on cancel.
- **`gh` CLI, `tree-sitter`, `scip-typescript` additions to `ALLOWED_BINARIES`** — handled in Phase 1+; this story ships `{"git"}` and nothing else.

## Notes for the implementer

- **Mutable default footgun.** `env_extra: dict[str, str] = {}` is the textbook Python bug; use `env_extra: dict[str, str] | None = None` and normalize inside. Mypy in strict mode will catch the literal-`{}`-default, but the lesson is worth noting.
- **The allowlist check must run *before* the spawn.** Spawning then killing a disallowed binary is functionally equivalent but defeats the audit story — the chokepoint is "no disallowed binary ever runs," not "no disallowed binary completes." Put the allowlist check as the very first statement in the function body; the test `test_disallowed_binary_rejected_before_spawn` pins this.
- **Env construction by omission, not deletion.** Build the safe-baseline env from scratch and then `| env_extra`; never start from `os.environ.copy()` and `del` the sensitive keys. The omission pattern means a new sensitive key added to the parent environment in Phase 9 doesn't silently leak — it's just not in the baseline, period.
- **`shell=False` is the default for `asyncio.create_subprocess_exec` but be explicit.** Some reviewers may scan for `shell=` in code review and miss "wrapper uses `_exec` which is implicitly shell=False." Adding a `# shell=False enforced by the use of create_subprocess_exec rather than subprocess.run` comment in the body is fine; what's not fine is using `subprocess.run` here at all.
- **SIGKILL escalation timing.** Spec is "SIGKILL at `1.5 × timeout_s`." A naive implementation runs `wait_for(timeout=timeout_s)`, sleeps 100 ms after SIGTERM, then SIGKILLs — which from-issue-of-timeout takes ~100 ms additional. That's fine for Phase 0. Phase 14's webhook load may surface tighter requirements; revisit then.
- **`ProbeTimeoutError` vs `asyncio.TimeoutError`.** Convert the asyncio exception to the project's typed error at the wrapper boundary; do not leak `asyncio.TimeoutError` to callers. Other coordinator code matches on `CodegenieError` subclasses.
- **Don't import `subprocess` at module scope.** `asyncio.subprocess.DEVNULL` and `Process` are the right primitives; `subprocess.run` belongs to a different concurrency model and shouldn't appear in `src/codegenie/`. The `forbidden-patterns` hook may not catch `import subprocess` if it's tucked behind a star import; just keep it out.
- **Cross-cutting per the manifest's "Definition of done":** `ruff format`, `ruff check`, `mypy --strict`, all green. The `mypy --strict` on `weakref.WeakValueDictionary[int, asyncio.subprocess.Process]` may need a literal type alias (`_RUNNING_PROCS: "weakref.WeakValueDictionary[int, asyncio.subprocess.Process]" = ...`); use it.
- **Reversibility tax is real.** Per ADR-0012 §Reversibility, removing this chokepoint becomes prohibitively expensive by Phase 5. If a reviewer asks "do we really need this for one git call?" — yes; the cost is paid now or unbounded later.
