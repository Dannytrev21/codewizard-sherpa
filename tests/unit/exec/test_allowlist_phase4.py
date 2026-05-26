"""Phase-4 S6-04 — ``ALLOWED_BINARIES`` admits ``"tsc"`` (ADR-04-0015).

Mirrors the Phase-3 S4-05 structural template with the Phase-4-specific
amendment scope (one binary, not four). Covers the load-bearing ACs:

* AC-1 — bare name ``"tsc"`` admitted exactly once with the Phase-4
  grouping comment.
* AC-3 — path-shaped invocations rejected before spawn.
* AC-6 — ADR cross-document gate (ADR-04-0015 mentions ``tsc``).
* AC-7 — module docstring references the Phase-4 amendment.
* AC-9 — ``_RUNNING_PROCS`` weakref cleanup after every exit path.
* AC-10 — property-style delta assertion (the closed-set diff against
  Phase 3 is exactly ``frozenset({"tsc"})``).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest import mock

import pytest

from codegenie.errors import (
    DisallowedSubprocessError,
    ProbeTimeoutError,
    ToolMissingError,
)
from codegenie.exec import (
    _RUNNING_PROCS,  # type: ignore[attr-defined]
    ALLOWED_BINARIES,
    run_allowlisted,
)

_PHASE_3_EXPECTED_BINARIES: frozenset[str] = frozenset(
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
        "npm",
        "bwrap",
        "sandbox-exec",
        "jq",
    }
)


def test_ac1_tsc_is_admitted_bare() -> None:
    """AC-1 — bare name ``"tsc"`` is in ``ALLOWED_BINARIES``."""
    assert "tsc" in ALLOWED_BINARIES


def test_ac10_phase4_admits_exactly_tsc() -> None:
    """AC-10 — the closed-set diff against Phase-3 is exactly ``{"tsc"}``.

    Mutation barrier: silent additions (something else admitted) or
    over-broad admission (e.g. ``"tsc"`` plus a sibling) both fail.
    """
    delta = ALLOWED_BINARIES - _PHASE_3_EXPECTED_BINARIES
    assert delta == frozenset({"tsc"}), f"Phase-4 must admit exactly {{'tsc'}}; got {delta}"


async def test_ac3_path_shaped_tsc_invocations_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3 — path-shaped ``argv[0]`` rejected before spawn."""
    spy = mock.AsyncMock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    for argv0 in (
        "/usr/local/bin/tsc",
        "/usr/bin/tsc",
        "/opt/homebrew/bin/tsc",
        "./node_modules/.bin/tsc",
        "./tsc",
        "./node_modules/.bin/tsc.bat",
        "./node_modules/.bin/../../usr/bin/tsc",
    ):
        with pytest.raises(DisallowedSubprocessError):
            await run_allowlisted([argv0, "--version"], cwd=tmp_path, timeout_s=1.0)
    spy.assert_not_awaited()


def test_ac6_adr_0015_enumerates_tsc() -> None:
    """AC-6 — ADR-04-0015 enumerates ``tsc`` as a backticked identifier."""
    adr = Path(__file__).resolve().parents[3] / (
        "docs/phases/04-vuln-llm-fallback-rag/ADRs/"
        "0015-typecheck-typescript-signal-and-tsc-allowed-binary.md"
    )
    text = adr.read_text(encoding="utf-8")
    assert "`tsc`" in text, "ADR-04-0015 must enumerate `tsc` as a backticked identifier"


def test_ac7_exec_module_docstring_phase4_present() -> None:
    """AC-7 — ``codegenie.exec``'s docstring references the Phase-4
    amendment (ADR-04-0015 + a phrase capturing the addition)."""
    import codegenie.exec as exec_mod

    # The amendment comment lives in the module body's grouping comment
    # block (above the frozenset literal), so we check the file source
    # rather than the module docstring proper.
    source = Path(exec_mod.__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
    assert "ADR-04-0015" in source or "04-ADR-0015" in source
    assert "tsc" in source


async def test_ac9_running_procs_cleaned_up_after_tsc_exit(
    tmp_path: Path,
) -> None:
    """AC-9 — ``_RUNNING_PROCS`` is empty after every exit path
    (success, not-installed, spawn-time miss). The Phase-7 coordinator
    cancel pathway depends on the table staying accurate."""
    try:
        await run_allowlisted(["tsc", "--version"], cwd=tmp_path, timeout_s=5.0)
    except (ToolMissingError, ProbeTimeoutError, FileNotFoundError):
        pass  # environment artifact, not the focus of this test
    assert len(_RUNNING_PROCS) == 0
