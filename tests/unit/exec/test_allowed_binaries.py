"""Tests for Phase 2 / S1-06 — ``ALLOWED_BINARIES`` ten additions (02-ADR-0001).

This module pins the Phase-2 closed-set frozen at:

    {"git", "node", "semgrep", "syft", "grype", "gitleaks",
     "scip-typescript", "ast-grep", "ripgrep", "tree-sitter",
     "docker", "strace"}

— exactly twelve entries — and verifies the sensitive-env-strip defense
established in Phase 0 (ADR-0012) continues to apply unchanged to the new
binaries. Mocking style follows the Phase 0/1 family convention
(``monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)`` with
``mock.AsyncMock``) per Rule 11.

The matching forbidden-binary parametrize lives in
``tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression``
and is extended in this same story (AC-15) with the wrapper-pattern
exception (`bwrap`/`bubblewrap`) and seven other adjacent dangerous
binaries.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest import mock

import pytest
import structlog

from codegenie.errors import (
    DisallowedSubprocessError,
    ProbeTimeoutError,
    ToolMissingError,
)
from codegenie.exec import ALLOWED_BINARIES, run_allowlisted

EXPECTED_NEW_BINARIES: frozenset[str] = frozenset(
    {
        "semgrep",
        "syft",
        "grype",
        "gitleaks",
        "scip-typescript",
        "ast-grep",
        "ripgrep",
        "tree-sitter",
        "docker",
        "strace",
    }
)
EXPECTED_TOTAL: frozenset[str] = frozenset({"git", "node"}) | EXPECTED_NEW_BINARIES

SENSITIVE_ENV_KEYS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN",
    "SSH_AUTH_SOCK",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)


def _make_spawn_spy(monkeypatch: pytest.MonkeyPatch) -> mock.AsyncMock:
    """Phase 0/1 family-convention spawn-spy. Returns the spy itself so
    callers can inspect ``spy.await_args.kwargs["env"]`` after the call.
    """
    fake_proc = mock.MagicMock()
    fake_proc.pid = 77777
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    return spy


# ───────────────────────────────────────────────────────────────────────────
# AC-1, AC-2 (codepath), AC-3 — closed-set + sensitive-constants pins
# ───────────────────────────────────────────────────────────────────────────


def test_allowed_binaries_is_exact_twelve_entry_set() -> None:
    """AC-1 — strict equality. A silent addition (e.g. ``"bash"``) or a
    silent deletion (e.g. dropping ``"git"``) fails this test."""
    assert ALLOWED_BINARIES == EXPECTED_TOTAL
    assert len(ALLOWED_BINARIES) == 12


def test_every_new_binary_is_present() -> None:
    """AC-2 (code-side) — every named-trigger entry from 02-ADR-0001 (eight)
    + the two Layer G additions (``ast-grep``, ``ripgrep``; 02-ADR-0001
    amendment per AC-10) is registered."""
    for name in EXPECTED_NEW_BINARIES:
        assert name in ALLOWED_BINARIES, f"missing from ALLOWED_BINARIES: {name!r}"


def test_phase_0_sensitive_constants_unchanged() -> None:
    """AC-3 — ``_SENSITIVE_EXACT`` and ``_SENSITIVE_PREFIX`` are unchanged
    by this story; the env-strip defense is a Phase-0 invariant."""
    from codegenie.exec import _SENSITIVE_EXACT, _SENSITIVE_PREFIX

    assert _SENSITIVE_EXACT == frozenset(
        {"SSH_AUTH_SOCK", "GITHUB_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
    )
    assert _SENSITIVE_PREFIX == ("AWS_",)


# ───────────────────────────────────────────────────────────────────────────
# AC-2 (doc-side) — cross-document gate: ADR enumerates every new binary
# ───────────────────────────────────────────────────────────────────────────


def test_adr_0001_enumerates_all_new_binaries() -> None:
    """AC-2 — the ADR file's Decision section must enumerate every entry in
    ``EXPECTED_NEW_BINARIES`` as a backticked identifier, and must say
    "ten new entries" (not "eight"). Cross-document gate: code-side
    additions cannot land without the matching ADR enumeration. Pins the
    governance policy of 02-ADR-0001 ("the omnibus ADR's enumeration IS
    the audit trail")."""
    adr = Path(__file__).resolve().parents[3] / (
        "docs/phases/02-context-gather-layers-b-g/ADRs/"
        "0001-add-docker-and-security-cli-tools-to-allowed-binaries.md"
    )
    text = adr.read_text(encoding="utf-8")

    assert "ten new entries" in text, "Decision section must say 'ten new entries'"
    assert "eight new entries" not in text, (
        "Decision section must not still say 'eight new entries' after AC-10's amendment"
    )

    for binary in EXPECTED_NEW_BINARIES:
        assert f"`{binary}`" in text, (
            f"ADR must enumerate `{binary}` as a backticked identifier "
            "(audit-trail policy of 02-ADR-0001)"
        )


# ───────────────────────────────────────────────────────────────────────────
# AC-11 — module docstring pin
# ───────────────────────────────────────────────────────────────────────────


def test_exec_module_docstring_phase2_present() -> None:
    """AC-11 — ``codegenie.exec``'s module docstring records the Phase 2
    governance ADR. Without this pin, a wrong impl that lands the
    frozenset edit but forgets the docstring passes every original AC.

    Whitespace is normalized (newline → space) before matching because
    Python source-file docstrings wrap long phrases at column-80; the
    rendered substring lives across the wrap."""
    import codegenie.exec as exec_mod

    doc_raw = exec_mod.__doc__ or ""
    doc_normalized = " ".join(doc_raw.split())
    assert "02-ADR-0001" in doc_normalized, "exec.py docstring must reference 02-ADR-0001"
    assert "ten Layer B/C/G tools" in doc_normalized, (
        "exec.py docstring must describe the addition as 'ten Layer B/C/G tools'"
    )


# ───────────────────────────────────────────────────────────────────────────
# AC-4 (closed-set acceptance + AC-13 weakref cleanup)
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("binary", sorted(EXPECTED_NEW_BINARIES))
async def test_new_binary_not_rejected_by_allowlist(binary: str, tmp_path: Path) -> None:
    """AC-4 — the allowlist accepts each of the ten new binaries. The call
    may fail at *runtime* (binary not installed, ``--version`` slow, OS
    spawn-time miss) — those are environment artifacts, not allowlist
    behavior. The load-bearing assertion is that
    :class:`DisallowedSubprocessError` is **never** raised.

    AC-13 — also pins ``_RUNNING_PROCS`` empty on every exit path so a
    regression that drops the ``finally:`` pop is caught (Phase 7's
    coordinator-cancel pathway depends on this table)."""
    from codegenie.exec import _RUNNING_PROCS

    try:
        await run_allowlisted([binary, "--version"], cwd=tmp_path, timeout_s=5.0)
    except DisallowedSubprocessError:
        pytest.fail(f"{binary!r} must be allowlisted; got DisallowedSubprocessError")
    except ToolMissingError:
        pass  # binary not installed in this environment (e.g. strace on macOS)
    except ProbeTimeoutError:
        pass  # rare: --version slower than 5s; allowlist is still proven open
    except FileNotFoundError:
        pass  # spawn-time miss; semantically equivalent to ToolMissingError
    # Anything else is a real regression and must propagate.

    assert len(_RUNNING_PROCS) == 0, (
        f"_RUNNING_PROCS must be empty after exit; left: {dict(_RUNNING_PROCS)}"
    )


# ───────────────────────────────────────────────────────────────────────────
# AC-4 — sensitive-env-strip parametric (mock spawn, capture env dict).
# Uses a real allowlisted binary (``git``) as the argv; env-strip is
# argv-independent — the parametric per-binary coverage lives in AC-12.
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sensitive_key", SENSITIVE_ENV_KEYS)
async def test_sensitive_env_var_is_dropped_from_child_env(
    sensitive_key: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4 — passing a sensitive key via ``env_extra`` triggers the
    chokepoint env-strip. The child process's ``env`` dict never contains
    the sensitive key."""
    spy = _make_spawn_spy(monkeypatch)

    await run_allowlisted(
        ["git", "--version"],
        cwd=tmp_path,
        timeout_s=5.0,
        env_extra={sensitive_key: "leak-value"},
    )

    assert spy.await_args is not None
    captured_env: dict[str, str] = spy.await_args.kwargs["env"]
    assert sensitive_key not in captured_env, (
        f"sensitive key {sensitive_key!r} must be stripped from child env; "
        f"actual env keys: {sorted(captured_env.keys())}"
    )


# ───────────────────────────────────────────────────────────────────────────
# AC-12 — env-strip parametric over (binary, sensitive_key) for the
# Layer B/G representative (`semgrep`) and Layer C representative
# (`docker`). Family precedent: tests/unit/test_exec.py:370.
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("binary", ["docker", "semgrep"])
@pytest.mark.parametrize(
    "sensitive_key", ["OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"]
)
async def test_env_strip_applies_to_each_new_binary(
    binary: str,
    sensitive_key: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-12 — env-strip is binary-independent. Catches a mutant that
    special-cases env handling for new binaries
    (``if binary in NEW: env = os.environ.copy()``). For each of the two
    representative binaries, every sensitive key must be absent from the
    captured env AND the ``subproc.env_extra.sensitive_key_dropped``
    structlog event must fire at level ``warning``."""
    spy = _make_spawn_spy(monkeypatch)

    with structlog.testing.capture_logs() as captured_events:
        await run_allowlisted(
            [binary, "--version"],
            cwd=tmp_path,
            timeout_s=5.0,
            env_extra={sensitive_key: "leak-value"},
        )

    assert spy.await_args is not None
    captured_env: dict[str, str] = spy.await_args.kwargs["env"]
    assert sensitive_key not in captured_env, (
        f"env-strip must drop {sensitive_key!r} when invoking {binary!r}; "
        f"env keys: {sorted(captured_env.keys())}"
    )

    drop_events = [
        e
        for e in captured_events
        if e.get("event") == "subproc.env_extra.sensitive_key_dropped"
        and e.get("key") == sensitive_key
    ]
    assert drop_events, (
        f"expected a 'subproc.env_extra.sensitive_key_dropped' event for "
        f"{sensitive_key!r}; got events: {captured_events}"
    )
    assert drop_events[0]["log_level"] == "warning"


# ───────────────────────────────────────────────────────────────────────────
# AC-14 — bare-binary-name discipline pinned for the ten new binaries.
# Family precedent: tests/unit/test_exec.py:34-43 (Phase 0 invariant 1).
# ───────────────────────────────────────────────────────────────────────────


_PATH_TRAVERSAL_CASES: list[str] = sorted(
    [f"/usr/bin/{b}" for b in EXPECTED_NEW_BINARIES] + [f"./{b}" for b in EXPECTED_NEW_BINARIES]
)


@pytest.mark.parametrize("argv0", _PATH_TRAVERSAL_CASES)
async def test_new_binaries_reject_resolved_paths(
    argv0: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-14 — ``argv[0]`` must be a bare binary name. Absolute or relative
    paths (``/usr/bin/docker``, ``./docker``) are *not* in
    ``ALLOWED_BINARIES`` and must be rejected *before* any spawn. The
    spy asserts spawn is never reached."""
    spy = mock.AsyncMock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    with pytest.raises(DisallowedSubprocessError):
        await run_allowlisted([argv0, "--version"], cwd=tmp_path, timeout_s=1.0)

    spy.assert_not_awaited()


# ───────────────────────────────────────────────────────────────────────────
# AC-16 — `_SENSITIVE_PREFIX` tuple-path coverage. Phase 0 family
# precedent: tests/unit/test_exec.py:283.
# ───────────────────────────────────────────────────────────────────────────


async def test_aws_prefix_match_strips_arbitrary_key_for_new_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-16 — an arbitrary ``AWS_FOO`` key exercises the
    ``_SENSITIVE_PREFIX`` tuple path (not the ``_SENSITIVE_EXACT`` exact
    match). The key must be absent from the captured env AND the structlog
    drop event must fire at level ``warning``. Carried forward to a new
    binary (``docker``) so the prefix-match path is pinned per Phase 2
    addition, not only for ``git``."""
    spy = _make_spawn_spy(monkeypatch)

    with structlog.testing.capture_logs() as captured_events:
        await run_allowlisted(
            ["docker", "--version"],
            cwd=tmp_path,
            timeout_s=5.0,
            env_extra={"AWS_FOO": "leak-value"},
        )

    assert spy.await_args is not None
    captured_env: dict[str, str] = spy.await_args.kwargs["env"]
    assert "AWS_FOO" not in captured_env, (
        f"AWS_* prefix match must drop AWS_FOO; env keys: {sorted(captured_env.keys())}"
    )

    drop_events = [
        e
        for e in captured_events
        if e.get("event") == "subproc.env_extra.sensitive_key_dropped" and e.get("key") == "AWS_FOO"
    ]
    assert drop_events, "expected a drop event for AWS_FOO"
    assert drop_events[0]["log_level"] == "warning"
