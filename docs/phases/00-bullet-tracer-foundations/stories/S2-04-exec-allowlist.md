# Story S2-04 — Subprocess allowlist chokepoint

**Step:** Step 2 — Plant the frozen contracts (probe ABC, hashing, exec allowlist, schema, error hierarchy)
**Status:** Ready
**Effort:** M
**Depends on:** S2-01
**ADRs honored:** ADR-0012

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
- [ ] `src/codegenie/exec.py` exports `async def run_allowlisted(argv: list[str], *, cwd: Path, timeout_s: float, env_extra: dict[str, str] | None = None) -> ProcessResult`. **Default for `env_extra` is `None`** then normalized inside the body — never `{}` as a literal default (mutable-default footgun).
- [ ] The wrapper enforces, in order: (a) `argv[0] not in ALLOWED_BINARIES` → `DisallowedSubprocessError` raised **before** any process spawn; (b) `cwd` resolved via `Path.resolve(strict=True)`, must be a directory, must not be a symlink that escapes the analyzed-repo root (caller responsibility to pass a vetted root; the wrapper rejects non-existent or non-directory `cwd`); (c) `shell=False` explicit; (d) `stdin=DEVNULL`; (e) env constructed as `{"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", ""), "LANG": os.environ.get("LANG", "C"), "LC_ALL": os.environ.get("LC_ALL", "C")} | env_extra`; (f) `SSH_AUTH_SOCK`, any `AWS_*`, `GITHUB_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` are **never** present in the child env (verified by the test).
- [ ] Timeout discipline: `asyncio.wait_for(process.communicate(), timeout=timeout_s)`; on `asyncio.TimeoutError`, send `SIGTERM`, give 100 ms grace, then `SIGKILL` at `1.5 × timeout_s` cumulative; raise `ProbeTimeoutError` with elapsed-ms in the message.
- [ ] If the binary is missing on `$PATH` (`FileNotFoundError` from `asyncio.create_subprocess_exec`), raise `ToolMissingError("git")` with an install hint in the message; the wrapper does **not** silently swallow this.
- [ ] A weakref process-tracking table (`weakref.WeakValueDictionary[int, Process]`) registers running children so a coordinator-cancel path can SIGKILL stragglers (`phase-arch-design.md §Component design — Subprocess allowlist`); module-level constant, not per-instance.
- [ ] `tests/unit/test_exec.py` covers: allowlist rejection (`["bash", ...]` raises *before* spawn), env-strip (`OPENAI_API_KEY` in parent env never reaches child), `cwd` rejection for a non-existent path, timeout → `ProbeTimeoutError`, `ToolMissingError` when the binary isn't on `$PATH`, and a `git rev-parse HEAD` happy path against a real git fixture.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/exec.py`, and `pytest tests/unit/test_exec.py -q` are clean.

## Implementation outline

1. Write `tests/unit/test_exec.py` first — six anchoring tests as described above. Use `pytest.mark.asyncio` for the async tests; the fixture `dev` extra (S1-02) already includes `pytest-asyncio`. Confirm `ImportError`.
2. Author `src/codegenie/exec.py`. Module docstring naming ADR-0012; `from __future__ import annotations`; `import asyncio`, `import os`, `import signal`, `import weakref`; `from dataclasses import dataclass`; `from pathlib import Path`; `from codegenie.errors import DisallowedSubprocessError, ProbeTimeoutError, ToolMissingError`.
3. Define `ALLOWED_BINARIES: frozenset[str] = frozenset({"git"})` and `ProcessResult` dataclass. Define module-level `_RUNNING_PROCS: weakref.WeakValueDictionary[int, asyncio.subprocess.Process] = weakref.WeakValueDictionary()`.
4. Implement `_filter_env(env_extra)`: build the four-key safe baseline, merge `env_extra`, return a new dict. Never mutate `os.environ`.
5. Implement `run_allowlisted`. Steps: (a) check allowlist; (b) resolve `cwd` and assert it exists + is a directory; (c) `proc = await asyncio.create_subprocess_exec(*argv, cwd=cwd, env=_filter_env(env_extra), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)`; (d) `_RUNNING_PROCS[proc.pid] = proc`; (e) try `stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)`; on `TimeoutError`, escalate (SIGTERM → 100 ms → SIGKILL), then raise `ProbeTimeoutError`; (f) return `ProcessResult(proc.returncode, stdout, stderr)`.
6. Map `FileNotFoundError` (binary missing) to `ToolMissingError`; map permission errors on `cwd` to `OSError` propagation (caller's bug).
7. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/exec.py`, `pytest tests/unit/test_exec.py -q`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_exec.py`.

Six behaviors anchor this story. Pin them one per test; each should fail before the implementation exists.

```python
# tests/unit/test_exec.py
import os
from pathlib import Path
import pytest

@pytest.mark.asyncio
async def test_disallowed_binary_rejected_before_spawn(tmp_path: Path, monkeypatch):
    # arrange: ensure bash exists on PATH so a real spawn would succeed
    from codegenie.exec import run_allowlisted
    from codegenie.errors import DisallowedSubprocessError
    # act/assert: bash is NOT in ALLOWED_BINARIES; the error must be raised
    # before any process is spawned. A spy on create_subprocess_exec asserts no call.
    with pytest.raises(DisallowedSubprocessError):
        await run_allowlisted(["bash", "-c", "echo hi"], cwd=tmp_path, timeout_s=1.0)

@pytest.mark.asyncio
async def test_env_strips_secret_shaped_vars(tmp_path: Path, monkeypatch):
    # arrange: set OPENAI_API_KEY in the parent env
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-real")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "AKIA-not-real")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/ssh-agent.sock")
    # act: invoke `git --version` (cheap, available everywhere)
    from codegenie.exec import run_allowlisted
    result = await run_allowlisted(["git", "--version"], cwd=tmp_path, timeout_s=10.0)
    # assert: we can't inspect the child env directly from outside, so the
    #         tightest pin is to invoke `env` (NOT allowlisted) — equivalent is
    #         a unit test on the `_filter_env` helper directly:
    from codegenie.exec import _filter_env
    env = _filter_env(None)
    assert "OPENAI_API_KEY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "SSH_AUTH_SOCK" not in env
    assert "PATH" in env  # baseline preserved
    assert result.returncode == 0

@pytest.mark.asyncio
async def test_cwd_must_exist_and_be_directory(tmp_path: Path):
    from codegenie.exec import run_allowlisted
    bogus = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):  # OSError subclass; caller's responsibility
        await run_allowlisted(["git", "--version"], cwd=bogus, timeout_s=1.0)

@pytest.mark.asyncio
async def test_timeout_raises_probe_timeout_and_sigkills(tmp_path: Path):
    # arrange: run `git -c http.lowSpeedLimit=0 ls-remote https://10.255.255.1/` —
    #          a deliberately unreachable host so git hangs in DNS/TCP.
    #          (Use any reliably-hangs invocation appropriate to the CI runner.)
    # act/assert: timeout fires; ProbeTimeoutError raised; the child is gone.
    from codegenie.exec import run_allowlisted
    from codegenie.errors import ProbeTimeoutError
    with pytest.raises(ProbeTimeoutError):
        await run_allowlisted(
            ["git", "-c", "http.lowSpeedLimit=0", "ls-remote", "https://10.255.255.1/"],
            cwd=tmp_path, timeout_s=0.5,
        )

@pytest.mark.asyncio
async def test_missing_binary_raises_tool_missing(tmp_path: Path, monkeypatch):
    # arrange: empty PATH so `git` can't be found
    monkeypatch.setenv("PATH", "/nonexistent")
    # also: temporarily add the binary to ALLOWED_BINARIES if needed for the
    # error to be ToolMissing and not Disallowed (here we use "git" which IS allowed)
    from codegenie.exec import run_allowlisted
    from codegenie.errors import ToolMissingError
    with pytest.raises(ToolMissingError):
        await run_allowlisted(["git", "--version"], cwd=tmp_path, timeout_s=1.0)

@pytest.mark.asyncio
async def test_git_rev_parse_happy_path(tmp_path: Path):
    # arrange: init a real git repo with one commit
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@e.com", "-c", "user.name=t",
                    "commit", "--allow-empty", "-m", "x"], cwd=tmp_path, check=True)
    # act
    from codegenie.exec import run_allowlisted
    result = await run_allowlisted(["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=10.0)
    # assert
    assert result.returncode == 0
    assert len(result.stdout.strip()) == 40  # full SHA-1
```

Run; confirm all six fail with `ImportError`. Commit as the red marker.

### Green — make it pass

`src/codegenie/exec.py`: implement the minimum that turns the six tests green.

- `ALLOWED_BINARIES = frozenset({"git"})`.
- `ProcessResult` dataclass.
- `_RUNNING_PROCS` weakref dict at module scope.
- `_filter_env(env_extra: dict[str, str] | None) -> dict[str, str]`: returns a fresh dict with the four-key safe baseline plus any `env_extra`. Never reads `OPENAI_API_KEY`/`AWS_*`/`SSH_AUTH_SOCK`/`GITHUB_TOKEN`/`ANTHROPIC_API_KEY` — by *omission*, not by deletion (safer: never copy them in).
- `run_allowlisted`: allowlist check raises early; resolve cwd; spawn with the filtered env; track in `_RUNNING_PROCS`; await with timeout; on timeout, escalate signals; map `FileNotFoundError` to `ToolMissingError`; return `ProcessResult`.

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
