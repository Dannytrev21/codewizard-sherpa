"""Tests for ``codegenie.exec.tool_versions`` (S4-03 AC-19).

T-20 — process-wide single-subprocess invariant + tool-missing safety.
"""

from __future__ import annotations

import pytest

from codegenie.errors import ToolMissingError
from codegenie.exec import ProcessResult
from codegenie.exec import tool_versions as tv


@pytest.fixture(autouse=True)
def _reset_memo() -> None:
    """Each test starts with an empty process-wide memo."""
    tv.clear_for_tests()
    yield
    tv.clear_for_tests()


async def test_resolve_caches_after_first_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-20: two consecutive calls trigger run_external_cli exactly once."""
    calls: list[tuple[str, list[str]]] = []

    async def _spy(probe_name, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
        calls.append((str(probe_name), list(argv)))
        return ProcessResult(returncode=0, stdout=b"scip-typescript 0.3.21\n", stderr=b"")

    monkeypatch.setattr("codegenie.exec.tool_versions.run_external_cli", _spy)

    v1 = await tv.resolve_tool_version("scip-typescript")
    v2 = await tv.resolve_tool_version("scip-typescript")
    assert v1 == "scip-typescript 0.3.21"
    assert v2 == v1
    assert len(calls) == 1, f"expected 1 subprocess, got {len(calls)}: {calls}"

    tv.clear_for_tests()
    v3 = await tv.resolve_tool_version("scip-typescript")
    assert v3 == v1
    assert len(calls) == 2, "clear_for_tests must reset the memo"


async def test_resolve_returns_unknown_on_tool_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-20: ToolMissingError → 'unknown' (does NOT raise)."""

    async def _raise(probe_name, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
        raise ToolMissingError("missing-binary not found")

    monkeypatch.setattr("codegenie.exec.tool_versions.run_external_cli", _raise)

    result = await tv.resolve_tool_version("missing-binary")
    assert result == "unknown"

    # Repeat call — memo holds "unknown"; no second subprocess.
    calls: list[int] = []

    async def _spy(probe_name, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
        calls.append(1)
        raise ToolMissingError("missing-binary not found")

    monkeypatch.setattr("codegenie.exec.tool_versions.run_external_cli", _spy)
    second = await tv.resolve_tool_version("missing-binary")
    assert second == "unknown"
    assert calls == []


async def test_resolve_returns_unknown_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-zero exit code → 'unknown' (also memoized — degraded forever)."""

    async def _exit_one(probe_name, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
        return ProcessResult(returncode=1, stdout=b"", stderr=b"oops\n")

    monkeypatch.setattr("codegenie.exec.tool_versions.run_external_cli", _exit_one)

    result = await tv.resolve_tool_version("broken-binary")
    assert result == "unknown"


async def test_sync_wrapper_reuses_async_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sync wrapper reads from the same memo as the async resolver."""

    async def _stub(probe_name, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
        return ProcessResult(returncode=0, stdout=b"primed-version", stderr=b"")

    monkeypatch.setattr("codegenie.exec.tool_versions.run_external_cli", _stub)
    primed = await tv.resolve_tool_version("scip-typescript")
    assert primed == "primed-version"

    # The sync wrapper finds the value in the memo without spawning.
    sync_value = tv.resolve_tool_version_sync("scip-typescript")
    assert sync_value == "primed-version"


def test_sync_wrapper_runs_async_when_no_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """No running loop + cold cache → asyncio.run() resolves the version."""

    async def _stub(probe_name, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
        return ProcessResult(returncode=0, stdout=b"sync-fired", stderr=b"")

    monkeypatch.setattr("codegenie.exec.tool_versions.run_external_cli", _stub)
    value = tv.resolve_tool_version_sync("scip-typescript")
    assert value == "sync-fired"


def test_default_parser_first_line() -> None:
    assert tv._default_parser(b"scip-typescript 0.3.21\nNode v20\n") == "scip-typescript 0.3.21"
    assert tv._default_parser(b"") == "unknown"
    assert tv._default_parser(b"   \n  v1\n") == "v1"
