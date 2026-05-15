"""Tests for Phase 2 / S1-07 — ``run_external_cli`` Layer B/G subprocess port.

Verifies the six Phase 0 invariants are preserved via the shared private
``_spawn_with_invariants`` extraction, that ``bwrap``/``bubblewrap`` stay out
of ``ALLOWED_BINARIES`` (02-ADR-0001 §Consequences last bullet; S1-06 AC-15
regression), and that the 64 MB tail-truncation, env-strip, warn-once, and
tmpdir-cleanup contracts are honored.

Idioms used here (per the validated TDD plan):

- ``structlog.testing.capture_logs()`` for log-event assertions
- ``ProbeId(...)`` wrappers per S1-04/S1-05 family precedent (mypy --strict
  rejects bare ``str`` where ``ProbeId`` is required)
- ``monkeypatch.setattr(ex, "_BWRAP_WARNED", False)`` autouse fixture so
  warn-once is observable per test
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import structlog
import structlog.testing

from codegenie.errors import DisallowedSubprocessError, ProbeTimeoutError
from codegenie.exec import (
    _TRUNC_MARKER,
    ALLOWED_BINARIES,
    ProcessResult,
    run_external_cli,
)
from codegenie.types.identifiers import ProbeId

P_SEMGREP = ProbeId("semgrep_probe")


@pytest.fixture
def fake_cwd(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture(autouse=True)
def reset_bwrap_warned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with ``_BWRAP_WARNED = False`` so warn-once is observable."""
    import codegenie.exec as ex

    monkeypatch.setattr(ex, "_BWRAP_WARNED", False, raising=False)


# ---------------------------------------------------------------------------
# AC-3a — regression: bwrap stays out of ALLOWED_BINARIES (pins 02-ADR-0001).
# ---------------------------------------------------------------------------


def test_bwrap_not_in_allowed_binaries() -> None:
    assert "bwrap" not in ALLOWED_BINARIES
    assert "bubblewrap" not in ALLOWED_BINARIES


# ---------------------------------------------------------------------------
# AC-1 — public surface
# ---------------------------------------------------------------------------


def test_run_external_cli_in_all() -> None:
    import codegenie.exec as ex

    assert "run_external_cli" in ex.__all__


# ---------------------------------------------------------------------------
# AC-8.1 — happy path on macOS delegates to run_allowlisted
# ---------------------------------------------------------------------------


async def test_happy_path_macos_delegates_to_run_allowlisted(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    expected = ProcessResult(returncode=0, stdout=b"ok", stderr=b"")
    fake = AsyncMock(return_value=expected)
    monkeypatch.setattr("codegenie.exec.run_allowlisted", fake)

    result = await run_external_cli(
        P_SEMGREP,
        ["semgrep", "--version"],
        cwd=fake_cwd,
        timeout_s=5.0,
    )
    assert result == expected
    fake.assert_awaited_once()
    assert fake.await_args is not None
    assert fake.await_args.args[0] == ["semgrep", "--version"]


# ---------------------------------------------------------------------------
# AC-8.2 — small-cap algorithmic truncation
# ---------------------------------------------------------------------------


async def test_small_cap_truncates_tail(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    payload = b"A" * 500
    monkeypatch.setattr(
        "codegenie.exec.run_allowlisted",
        AsyncMock(return_value=ProcessResult(0, payload, b"")),
    )
    result = await run_external_cli(
        P_SEMGREP,
        ["semgrep", "x"],
        cwd=fake_cwd,
        timeout_s=5.0,
        max_stdout_bytes=128,
    )
    assert len(result.stdout) == 128
    assert result.stdout.startswith(_TRUNC_MARKER)
    assert result.stdout.endswith(b"A" * (128 - len(_TRUNC_MARKER)))


# ---------------------------------------------------------------------------
# AC-8.3 — head-vs-tail discrimination (kills head-bug mutant)
# ---------------------------------------------------------------------------


async def test_truncation_keeps_tail_not_head(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    payload = b"A" * 50 + b"B" * 50  # head=A, tail=B
    monkeypatch.setattr(
        "codegenie.exec.run_allowlisted",
        AsyncMock(return_value=ProcessResult(0, payload, b"")),
    )
    result = await run_external_cli(
        P_SEMGREP,
        ["semgrep", "x"],
        cwd=fake_cwd,
        timeout_s=5.0,
        max_stdout_bytes=64,
    )
    assert result.stdout.startswith(_TRUNC_MARKER)
    body = result.stdout[len(_TRUNC_MARKER) :]
    assert body == b"B" * (64 - len(_TRUNC_MARKER))
    assert b"A" not in body


# ---------------------------------------------------------------------------
# AC-8.4 — macOS warn-once via structlog capture
# ---------------------------------------------------------------------------


async def test_macos_warns_once_across_two_calls(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        "codegenie.exec.run_allowlisted",
        AsyncMock(return_value=ProcessResult(0, b"", b"")),
    )
    with structlog.testing.capture_logs() as events:
        await run_external_cli(P_SEMGREP, ["semgrep", "a"], cwd=fake_cwd, timeout_s=5.0)
        await run_external_cli(P_SEMGREP, ["semgrep", "b"], cwd=fake_cwd, timeout_s=5.0)
    skipped = [e for e in events if e.get("event") == "subproc.bwrap.skipped"]
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "not_linux"
    assert skipped[0]["log_level"] == "warning"


# ---------------------------------------------------------------------------
# AC-3b + AC-8.5 + AC-7 — Linux+bwrap wraps argv; spawn captured via
# _spawn_with_invariants
# ---------------------------------------------------------------------------


async def test_linux_with_bwrap_wraps_argv(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    import codegenie.exec as ex

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "codegenie.exec.shutil.which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )
    monkeypatch.setattr(
        "codegenie.exec.tempfile.mkdtemp",
        lambda prefix: str(fake_cwd / f"{prefix}fixed"),
    )
    seen: list[tuple[list[str], dict[str, str]]] = []

    async def fake_spawn(
        argv: list[str], *, cwd: Path, timeout_s: float, env: dict[str, str]
    ) -> ProcessResult:
        seen.append((argv, env))
        return ProcessResult(0, b"", b"")

    monkeypatch.setattr(ex, "_spawn_with_invariants", fake_spawn)

    with structlog.testing.capture_logs() as events:
        await run_external_cli(P_SEMGREP, ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0)

    argv, env = seen[0]
    assert argv[0] == "bwrap"
    assert "--unshare-net" in argv
    assert "--ro-bind" in argv
    assert "--bind" in argv
    assert "--" in argv
    sep = argv.index("--")
    assert argv[sep + 1 :] == ["semgrep", "x"]
    # AC-7 — env is the 4-key Phase 0 baseline exactly
    assert set(env.keys()) == {"PATH", "HOME", "LANG", "LC_ALL"}
    # AC-10 — wrapped event at DEBUG with probe_name + egress fields
    wrapped = [e for e in events if e.get("event") == "subproc.bwrap.wrapped"]
    assert len(wrapped) == 1
    assert wrapped[0]["probe_name"] == "semgrep_probe"
    assert wrapped[0]["egress"] is False


# ---------------------------------------------------------------------------
# AC-8.6 — egress omits --unshare-net
# ---------------------------------------------------------------------------


async def test_linux_with_bwrap_egress_omits_unshare_net(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    import codegenie.exec as ex

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "codegenie.exec.shutil.which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )
    monkeypatch.setattr(
        "codegenie.exec.tempfile.mkdtemp",
        lambda prefix: str(fake_cwd / f"{prefix}fixed"),
    )
    seen: list[list[str]] = []

    async def fake_spawn(
        argv: list[str], *, cwd: Path, timeout_s: float, env: dict[str, str]
    ) -> ProcessResult:
        seen.append(argv)
        return ProcessResult(0, b"", b"")

    monkeypatch.setattr(ex, "_spawn_with_invariants", fake_spawn)

    await run_external_cli(
        P_SEMGREP,
        ["semgrep", "x"],
        cwd=fake_cwd,
        timeout_s=5.0,
        allowlisted_egress=frozenset({"github.com"}),
    )
    assert "--unshare-net" not in seen[0]
    assert "--ro-bind" in seen[0]
    assert "--bind" in seen[0]
    assert "--" in seen[0]


# ---------------------------------------------------------------------------
# AC-8.7 — Linux + bwrap missing — graceful no-op + warn-once
# ---------------------------------------------------------------------------


async def test_linux_without_bwrap_warns_once(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("codegenie.exec.shutil.which", lambda name: None)
    fake = AsyncMock(return_value=ProcessResult(0, b"", b""))
    monkeypatch.setattr("codegenie.exec.run_allowlisted", fake)
    with structlog.testing.capture_logs() as events:
        await run_external_cli(P_SEMGREP, ["semgrep", "a"], cwd=fake_cwd, timeout_s=5.0)
        await run_external_cli(P_SEMGREP, ["semgrep", "b"], cwd=fake_cwd, timeout_s=5.0)
    skipped = [e for e in events if e.get("event") == "subproc.bwrap.skipped"]
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "not_installed"
    assert fake.await_args is not None
    assert fake.await_args.args[0] == ["semgrep", "b"]


# ---------------------------------------------------------------------------
# AC-8.8 — timeout propagates
# ---------------------------------------------------------------------------


async def test_timeout_propagates(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    async def fake_run_allowlisted(argv: list[str], **kwargs: object) -> ProcessResult:
        raise ProbeTimeoutError("semgrep exceeded timeout_s=5 (elapsed_ms=5001)")

    monkeypatch.setattr("codegenie.exec.run_allowlisted", fake_run_allowlisted)
    with pytest.raises(ProbeTimeoutError):
        await run_external_cli(
            P_SEMGREP,
            ["semgrep", "x"],
            cwd=fake_cwd,
            timeout_s=5.0,
        )


# ---------------------------------------------------------------------------
# AC-8.9 — non-zero exit returned, not raised
# ---------------------------------------------------------------------------


async def test_nonzero_exit_returned_not_raised(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        "codegenie.exec.run_allowlisted",
        AsyncMock(return_value=ProcessResult(2, b"out", b"err")),
    )
    result = await run_external_cli(
        P_SEMGREP,
        ["semgrep", "x"],
        cwd=fake_cwd,
        timeout_s=5.0,
    )
    assert result.returncode == 2
    assert result.stdout == b"out"
    assert result.stderr == b"err"


# ---------------------------------------------------------------------------
# AC-8.10 — inner-argv allowlist enforcement: rejects before any spawn or tmpdir
# ---------------------------------------------------------------------------


async def test_inner_argv_must_be_in_allowed_binaries(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    mkdtemp_called = {"v": False}

    def fake_mkdtemp(prefix: str) -> str:
        mkdtemp_called["v"] = True
        raise AssertionError("mkdtemp must not run for a disallowed inner binary")

    monkeypatch.setattr("codegenie.exec.tempfile.mkdtemp", fake_mkdtemp)
    with pytest.raises(DisallowedSubprocessError):
        await run_external_cli(P_SEMGREP, ["nmap", "-sV"], cwd=fake_cwd, timeout_s=5.0)
    assert mkdtemp_called["v"] is False


async def test_inner_argv_empty_rejected(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(DisallowedSubprocessError):
        await run_external_cli(P_SEMGREP, [], cwd=fake_cwd, timeout_s=5.0)


# ---------------------------------------------------------------------------
# AC-3c — tmpdir cleanup across all three exit paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "outcome,raises",
    [
        ("success", False),
        ("nonzero", False),
        ("timeout", True),
    ],
)
async def test_bwrap_tmpdir_cleaned_up(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
    outcome: str,
    raises: bool,
) -> None:
    import codegenie.exec as ex

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "codegenie.exec.shutil.which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )
    tmpdir = fake_cwd / "stub_tmp"
    tmpdir.mkdir()
    assert tmpdir.exists()
    monkeypatch.setattr("codegenie.exec.tempfile.mkdtemp", lambda prefix: str(tmpdir))

    async def fake_spawn(
        argv: list[str], *, cwd: Path, timeout_s: float, env: dict[str, str]
    ) -> ProcessResult:
        if outcome == "success":
            return ProcessResult(0, b"", b"")
        if outcome == "nonzero":
            return ProcessResult(2, b"out", b"err")
        raise ProbeTimeoutError("timed out (elapsed_ms=5001)")

    monkeypatch.setattr(ex, "_spawn_with_invariants", fake_spawn)

    if raises:
        with pytest.raises(ProbeTimeoutError):
            await run_external_cli(
                P_SEMGREP,
                ["semgrep", "x"],
                cwd=fake_cwd,
                timeout_s=5.0,
            )
    else:
        await run_external_cli(
            P_SEMGREP,
            ["semgrep", "x"],
            cwd=fake_cwd,
            timeout_s=5.0,
        )

    assert not tmpdir.exists(), f"tmpdir leaked on outcome={outcome}"


# ---------------------------------------------------------------------------
# AC-10 — subproc.stdout.truncated emitted per truncated stream
# ---------------------------------------------------------------------------


async def test_truncation_emits_log_event(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        "codegenie.exec.run_allowlisted",
        AsyncMock(return_value=ProcessResult(0, b"A" * 500, b"B" * 500)),
    )
    with structlog.testing.capture_logs() as events:
        await run_external_cli(
            P_SEMGREP,
            ["semgrep", "x"],
            cwd=fake_cwd,
            timeout_s=5.0,
            max_stdout_bytes=128,
        )
    truncated = [e for e in events if e.get("event") == "subproc.stdout.truncated"]
    streams = {e["stream"] for e in truncated}
    assert streams == {"stdout", "stderr"}
    for e in truncated:
        assert e["log_level"] == "warning"
        assert e["probe_name"] == "semgrep_probe"


# ---------------------------------------------------------------------------
# AC-14 — probe_name regex validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_name", ["../bad", "foo bar", "", "Foo", "1abc"])
async def test_invalid_probe_name_rejected(
    monkeypatch: pytest.MonkeyPatch,
    fake_cwd: Path,
    bad_name: str,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(ValueError, match="invalid probe_name"):
        await run_external_cli(
            ProbeId(bad_name),
            ["semgrep", "x"],
            cwd=fake_cwd,
            timeout_s=5.0,
        )


# ---------------------------------------------------------------------------
# AC-9 — only src/codegenie/exec.py contains asyncio.create_subprocess_exec
# ---------------------------------------------------------------------------


def test_only_exec_module_calls_create_subprocess_exec() -> None:
    """AC-9: no new spawn callsite outside src/codegenie/exec.py."""
    src_root = Path(__file__).resolve().parents[3] / "src" / "codegenie"
    offenders: list[Path] = []
    for py in src_root.rglob("*.py"):
        if py.name == "exec.py":
            continue
        text = py.read_text()
        if "asyncio.create_subprocess_exec" in text:
            offenders.append(py)
    assert offenders == [], f"asyncio.create_subprocess_exec found outside exec.py in: {offenders}"
