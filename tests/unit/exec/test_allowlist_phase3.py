"""Tests for Phase 3 / S4-05 — ``ALLOWED_BINARIES`` four-binary amendment
(03-ADR-0012).

Mirrors the S1-06 (Phase 2) structural template:

* exact-equality test on the closed frozenset (silent additions / deletions fail);
* ADR cross-document gate (every new binary enumerated as a backticked identifier);
* per-binary allowlist-acceptance (not rejected by the allowlist);
* per-binary path-traversal rejection (absolute / relative paths fail before spawn);
* env-strip parametric over (new-binary × sensitive-key) pairs;
* per-binary ``_RUNNING_PROCS`` weakref cleanup on every exit path.

ADR cross-reference: ``docs/phases/03-vuln-deterministic-recipe/ADRs/
0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md``.
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

# Phase 3 03-ADR-0012 — the four new binaries.
NEW_BINARIES: frozenset[str] = frozenset({"npm", "bwrap", "sandbox-exec", "jq"})

# Phase 2 12-entry baseline preserved.
PHASE2_BASELINE: frozenset[str] = frozenset(
    {
        "git",
        "node",
        "semgrep",
        "syft",
        "grype",
        "gitleaks",
        "scip-typescript",
        "ast-grep",
        "rg",
        "tree-sitter",
        "docker",
        "strace",
    }
)
# Phase-4 ADR-04-0015 (S6-04) admits one additional binary: ``"tsc"``. The
# closure-equality assertion grows by one row but stays anchored in this
# Phase-3 family file for AC-4/AC-5 historical-precedent purposes.
PHASE4_ADDITIONS: frozenset[str] = frozenset({"tsc"})
EXPECTED_TOTAL: frozenset[str] = PHASE2_BASELINE | NEW_BINARIES | PHASE4_ADDITIONS  # 17 entries


def _make_spawn_spy(monkeypatch: pytest.MonkeyPatch) -> mock.AsyncMock:
    """Phase 0/1 family-convention spawn-spy."""
    fake_proc = mock.MagicMock()
    fake_proc.pid = 77778
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    return spy


# ───────────────────────────────────────────────────────────────────────────
# AC-1 — exact-equality on the sixteen-entry closed set.
# ───────────────────────────────────────────────────────────────────────────


def test_allowed_binaries_is_exact_sixteen_entry_set() -> None:
    """AC-1 — exact equality. Silent addition (e.g. ``"bash"``) or silent
    deletion (e.g. dropping ``"npm"``) fails this test.

    Phase-4 ADR-04-0015 (S6-04) admits ``"tsc"``: the closed set grows
    from 16 → 17 entries. The historical name preserves the anchor for
    AC-4/AC-5 precedent tests; the assertion uses the updated total.
    """
    assert ALLOWED_BINARIES == EXPECTED_TOTAL
    assert len(ALLOWED_BINARIES) == 17


def test_phase_2_baseline_preserved() -> None:
    """AC-1 (companion) — every Phase-2-baseline entry survives the
    Phase-3 amendment. Catches a regression that drops a Phase-2 binary."""
    for name in PHASE2_BASELINE:
        assert name in ALLOWED_BINARIES, f"Phase-2 baseline binary missing: {name!r}"


def test_every_new_phase3_binary_is_present() -> None:
    """AC-1 (companion) — every binary 03-ADR-0012 admits is present."""
    for name in NEW_BINARIES:
        assert name in ALLOWED_BINARIES, f"03-ADR-0012 binary missing: {name!r}"


# ───────────────────────────────────────────────────────────────────────────
# AC-2 — module docstring records the Phase 3 amendment.
# ───────────────────────────────────────────────────────────────────────────


def test_exec_module_docstring_phase3_present() -> None:
    """AC-2 — ``codegenie.exec``'s docstring references 03-ADR-0012 and
    the four-binaries phrase. Whitespace is normalized because the
    docstring wraps at column-80."""
    import codegenie.exec as exec_mod

    doc_raw = exec_mod.__doc__ or ""
    doc_normalized = " ".join(doc_raw.split())
    assert "03-ADR-0012" in doc_normalized, "exec.py docstring must reference 03-ADR-0012"
    assert "four binaries" in doc_normalized, (
        "exec.py docstring must describe the addition as 'four binaries'"
    )


# ───────────────────────────────────────────────────────────────────────────
# AC-4 — ADR-0012 cross-document gate: every new binary is enumerated.
# ───────────────────────────────────────────────────────────────────────────


def test_adr_0012_enumerates_all_new_binaries() -> None:
    """AC-4 — every entry in ``NEW_BINARIES`` is enumerated as a
    backticked identifier inside the ADR Decision text. Cross-document
    gate: code-side additions cannot land without the matching ADR
    enumeration."""
    adr = Path(__file__).resolve().parents[3] / (
        "docs/phases/03-vuln-deterministic-recipe/ADRs/"
        "0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md"
    )
    text = adr.read_text(encoding="utf-8")
    for binary in NEW_BINARIES:
        assert f"`{binary}`" in text, (
            f"03-ADR-0012 must enumerate `{binary}` as a backticked identifier"
        )


# ───────────────────────────────────────────────────────────────────────────
# AC-5 — per-new-binary allowlist acceptance.
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("binary", sorted(NEW_BINARIES))
async def test_new_binary_not_rejected_by_allowlist(binary: str, tmp_path: Path) -> None:
    """AC-5 — invoking each new binary via :func:`run_allowlisted` must
    *not* raise :class:`DisallowedSubprocessError`. The call may fail at
    runtime (not installed; ``--version`` slow); those are environment
    artifacts, not allowlist behavior."""
    try:
        await run_allowlisted([binary, "--version"], cwd=tmp_path, timeout_s=5.0)
    except DisallowedSubprocessError:
        pytest.fail(f"{binary!r} must be allowlisted; got DisallowedSubprocessError")
    except (ToolMissingError, ProbeTimeoutError, FileNotFoundError):
        pass  # environment artifact, not allowlist behavior


# ───────────────────────────────────────────────────────────────────────────
# AC-6 — path-traversal rejection per new binary.
# ───────────────────────────────────────────────────────────────────────────


_PATH_TRAVERSAL_CASES: list[str] = sorted(
    [f"/usr/bin/{b}" for b in NEW_BINARIES] + [f"./{b}" for b in NEW_BINARIES]
)


@pytest.mark.parametrize("argv0", _PATH_TRAVERSAL_CASES)
async def test_new_binary_rejects_resolved_paths(
    argv0: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6 — ``argv[0]`` must be a bare binary name. Absolute or
    relative paths fail *before* spawn. The spawn-spy asserts no
    process is ever created."""
    spy = mock.AsyncMock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    with pytest.raises(DisallowedSubprocessError):
        await run_allowlisted([argv0, "--version"], cwd=tmp_path, timeout_s=1.0)

    spy.assert_not_awaited()


# ───────────────────────────────────────────────────────────────────────────
# AC-7 — env-strip parametric over (new-binary × sensitive-key).
# Uses npm + jq as representative new binaries (bwrap/sandbox-exec
# may not exist on the test runner; the env-strip path is
# argv-independent so two representatives suffice).
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("binary", ["npm", "jq"])
@pytest.mark.parametrize(
    "sensitive_key", ["OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"]
)
async def test_env_strip_applies_to_each_new_binary(
    binary: str,
    sensitive_key: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-7 — env-strip is binary-independent. Each sensitive key is
    absent from the captured child env AND the
    ``subproc.env_extra.sensitive_key_dropped`` structlog event fires
    at level ``warning``."""
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
# AC-8 — ``_RUNNING_PROCS`` weakref cleanup per new binary.
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("binary", sorted(NEW_BINARIES))
async def test_new_binary_running_procs_cleaned_up(binary: str, tmp_path: Path) -> None:
    """AC-8 — ``_RUNNING_PROCS`` is empty after every exit path
    (success / not-installed / spawn-time miss). Phase 7's
    coordinator-cancel pathway depends on this table being accurate."""
    from codegenie.exec import _RUNNING_PROCS

    try:
        await run_allowlisted([binary, "--version"], cwd=tmp_path, timeout_s=5.0)
    except DisallowedSubprocessError:
        pytest.fail(f"{binary!r} must be allowlisted")
    except (ToolMissingError, ProbeTimeoutError, FileNotFoundError):
        pass

    assert len(_RUNNING_PROCS) == 0, (
        f"_RUNNING_PROCS must be empty after exit; left: {dict(_RUNNING_PROCS)}"
    )
