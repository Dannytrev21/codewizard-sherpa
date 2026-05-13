"""Pins the :mod:`codegenie.exec` allowlist chokepoint (S2-04 / ADR-0012).

Each test pins one structural invariant of the wrapper. The unifying pattern is
that the OS boundary — ``asyncio.create_subprocess_exec`` — is spied so we
observe what the chokepoint actually passes to the kernel, rather than
introspecting private helpers (which a mutant could trivially bypass).

Sources:
- ``docs/phases/00-bullet-tracer-foundations/stories/S2-04-exec-allowlist.md``
  §TDD plan — Tests 1–10.
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md``
  — six enforced invariants in one place.
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import re
import subprocess
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import structlog

# ───────────────────────────────────────────────────────────────────────────
# Test 1 — Allowlist rejection happens BEFORE any spawn
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "argv",
    [
        ["bash", "-c", "echo hi"],
        ["/usr/bin/git", "rev-parse", "HEAD"],  # absolute path is NOT in the set
        ["./git", "rev-parse", "HEAD"],  # relative path is NOT in the set
        [],  # empty argv
    ],
)
async def test_disallowed_binary_rejected_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    from codegenie.errors import DisallowedSubprocessError
    from codegenie.exec import run_allowlisted

    spy = mock.AsyncMock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    with pytest.raises(DisallowedSubprocessError):
        await run_allowlisted(argv, cwd=tmp_path, timeout_s=1.0)
    spy.assert_not_awaited()


# ───────────────────────────────────────────────────────────────────────────
# Test 2 — Child env keyset is a subset of the safe baseline ∪ env_extra
# ───────────────────────────────────────────────────────────────────────────


async def test_child_env_keyset_subset_of_safe_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches the ``env=os.environ.copy()`` mutant that leaves the private
    helper correct. By omission an unlisted parent-env key is structurally
    absent — this single assertion subsumes "the five sensitive keys are
    absent."
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

    await run_allowlisted(
        ["git", "--version"],
        cwd=tmp_path,
        timeout_s=10.0,
        env_extra={"GIT_SSH_COMMAND": "ssh -i /tmp/k"},
    )

    captured_env = spy.await_args.kwargs["env"]
    allowed = {"PATH", "HOME", "LANG", "LC_ALL", "GIT_SSH_COMMAND"}
    leaked = set(captured_env) - allowed
    assert not leaked, f"leaked keys: {leaked}"
    for k in (
        "OPENAI_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "SSH_AUTH_SOCK",
        "GITHUB_TOKEN",
        "ANTHROPIC_API_KEY",
    ):
        assert k not in captured_env


# ───────────────────────────────────────────────────────────────────────────
# Test 3 — stdin=DEVNULL + no shell= kwarg are pinned via the spawn-spy
# ───────────────────────────────────────────────────────────────────────────


async def test_spawn_kwargs_pin_stdin_devnull_and_no_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches the ``stdin=PIPE`` mutant and any switch to ``subprocess.run(
    ..., shell=True)``."""
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


async def test_cwd_rejection_paths(tmp_path: Path) -> None:
    from codegenie.exec import run_allowlisted

    bogus = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):
        await run_allowlisted(["git", "--version"], cwd=bogus, timeout_s=1.0)

    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    with pytest.raises(NotADirectoryError):
        await run_allowlisted(["git", "--version"], cwd=a_file, timeout_s=1.0)


# ───────────────────────────────────────────────────────────────────────────
# Test 5 — Timeout escalation: SIGTERM → ~100 ms grace → SIGKILL
# ───────────────────────────────────────────────────────────────────────────


async def test_timeout_escalates_sigterm_then_sigkill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic, network-free. Catches: immediate-SIGKILL mutant, missing
    elapsed_ms mutant, leaked-child mutant, missing-finally-pop mutant.
    """
    from codegenie.errors import ProbeTimeoutError
    from codegenie.exec import _RUNNING_PROCS, run_allowlisted

    hang = asyncio.Event()  # never set

    async def _comm() -> tuple[bytes, bytes]:
        await hang.wait()
        return (b"", b"")

    fake_proc = mock.MagicMock()
    fake_proc.pid = 77777
    fake_proc.returncode = -9
    fake_proc.communicate = mock.AsyncMock(side_effect=_comm)
    fake_proc.terminate = mock.MagicMock()
    fake_proc.kill = mock.MagicMock()
    fake_proc.wait = mock.AsyncMock(return_value=-9)

    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    loop = asyncio.get_event_loop()
    start = loop.time()
    with pytest.raises(ProbeTimeoutError) as exc_info:
        await run_allowlisted(["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=0.2)
    elapsed = loop.time() - start

    assert fake_proc.terminate.call_count == 1
    assert fake_proc.kill.call_count >= 1
    # SIGKILL happens after grace, within 1.5×timeout + slack.
    assert 0.2 <= elapsed <= (1.5 * 0.2) + 0.5
    assert re.search(r"elapsed_ms=\d+", str(exc_info.value))
    assert 77777 not in _RUNNING_PROCS  # cleaned up in finally


# ───────────────────────────────────────────────────────────────────────────
# Test 6 — Missing binary → ToolMissingError with git+install/PATH hint
# ───────────────────────────────────────────────────────────────────────────


async def test_missing_binary_raises_tool_missing_with_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    from codegenie.errors import ToolMissingError
    from codegenie.exec import _RUNNING_PROCS, run_allowlisted

    with pytest.raises(ToolMissingError, match=r"git.*(install|PATH)"):
        await run_allowlisted(["git", "--version"], cwd=tmp_path, timeout_s=1.0)
    # No orphan weakref entry from the failed spawn.
    assert len(_RUNNING_PROCS) == 0


# ───────────────────────────────────────────────────────────────────────────
# Test 7 — Happy path with real git: ProcessResult immutable + typed fields
# ───────────────────────────────────────────────────────────────────────────


async def test_git_rev_parse_happy_path_and_result_frozen_typed(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@e.com",
            "-c",
            "user.name=t",
            "commit",
            "--allow-empty",
            "-m",
            "x",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    from codegenie.exec import _RUNNING_PROCS, ProcessResult, run_allowlisted

    result = await run_allowlisted(["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=10.0)
    assert result.returncode == 0
    assert isinstance(result.stdout, bytes)
    assert isinstance(result.stderr, bytes)
    assert isinstance(result.returncode, int)
    assert len(result.stdout.strip()) == 40

    assert ProcessResult.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.returncode = 1  # type: ignore[misc]

    assert len(_RUNNING_PROCS) == 0


# ───────────────────────────────────────────────────────────────────────────
# Test 8 — Signature default sentinel (mutable-default-footgun guard)
# ───────────────────────────────────────────────────────────────────────────


def test_run_allowlisted_signature_default_is_none() -> None:
    """One-line mutation-proof guard. A revert to ``= {}`` is a build-breaker."""
    from codegenie.exec import run_allowlisted

    sig = inspect.signature(run_allowlisted)
    assert sig.parameters["env_extra"].default is None


# ───────────────────────────────────────────────────────────────────────────
# Test 9 — env_extra hygiene: sensitive keys dropped + structlog event
# ───────────────────────────────────────────────────────────────────────────


async def test_env_extra_drops_sensitive_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``env_extra`` is a narrow passthrough, not a backdoor for re-introducing
    the keys the baseline filtered out.
    """
    from codegenie.exec import run_allowlisted

    fake_proc = mock.MagicMock()
    fake_proc.pid = 88888
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    with structlog.testing.capture_logs() as captured_events:
        await run_allowlisted(
            ["git", "--version"],
            cwd=tmp_path,
            timeout_s=10.0,
            env_extra={
                "OPENAI_API_KEY": "sk-leak",
                "AWS_FOO": "leak",
                "GIT_SSH_COMMAND": "ssh -i /k",
            },
        )

    captured = spy.await_args.kwargs["env"]
    assert "OPENAI_API_KEY" not in captured
    assert "AWS_FOO" not in captured
    assert "GIT_SSH_COMMAND" in captured  # legitimate extra survives

    drop_events = [
        e for e in captured_events if e.get("event") == "subproc.env_extra.sensitive_key_dropped"
    ]
    dropped_keys = {e["key"] for e in drop_events}
    assert dropped_keys == {"OPENAI_API_KEY", "AWS_FOO"}
    for e in drop_events:
        assert e["log_level"] == "warning"


# ───────────────────────────────────────────────────────────────────────────
# Test 10 — Weakref table: registered during run, cleared after
# ───────────────────────────────────────────────────────────────────────────


async def test_running_procs_registered_during_run_cleared_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the Phase-7 coordinator-cancel chokepoint promise."""
    from codegenie.exec import _RUNNING_PROCS, run_allowlisted

    seen_during_run: list[bool] = []

    fake_proc = mock.MagicMock()
    fake_proc.pid = 66666
    fake_proc.returncode = 0

    async def _comm() -> tuple[bytes, bytes]:
        seen_during_run.append(66666 in _RUNNING_PROCS)
        return (b"", b"")

    fake_proc.communicate = mock.AsyncMock(side_effect=_comm)

    spy: Any = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    await run_allowlisted(["git", "--version"], cwd=tmp_path, timeout_s=5.0)
    assert seen_during_run == [True]
    assert 66666 not in _RUNNING_PROCS  # finally: pop ran
