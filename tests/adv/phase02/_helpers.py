"""Shared helpers for the Phase 2 ``tests/adv/phase02/`` corpus.

Provides:

- :func:`build_drift_slice` — synthetic ``runtime_trace`` slice for the
  drift / clean / absent-slice scenarios.
- :func:`forbid_real_subprocess` — pytest fixture that raises
  ``AssertionError`` on any subprocess escape; the adversarial corpus must
  not invoke real ``docker`` / ``strace`` / ``git`` etc.
- :func:`clean_freshness_registry` — snapshot+restore the singleton
  freshness registry so adversarial tests do not leak registrations.

Rule-of-three trigger noted in S5-05's "Notes for the implementer": this
file is the second adversarial helper module (after ``tests/adv/_helpers``);
extraction to a shared base is deferred to the next consumer.
"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Iterator
from typing import Any

import pytest

from codegenie.indices.registry import default_freshness_registry


def build_drift_slice(
    built: str | None,
    last_traced: str | None,
    *,
    last_traced_at: str = "2026-05-17T00:00:00+00:00",
    trace_coverage_confidence: str = "high",
) -> dict[str, object]:
    """Synthetic ``runtime_trace`` slice for drift / clean / absent tests."""
    return {
        "built_image_digest": built,
        "last_traced_image_digest": last_traced,
        "last_traced_at": last_traced_at,
        "trace_coverage_confidence": trace_coverage_confidence,
    }


@pytest.fixture
def forbid_real_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch every subprocess seam to raise on any escape.

    Acts as a structural defense: a future "let's quickly add a real
    end-to-end check" contributor cannot silently un-mock the subprocess
    layer; the stubs raise ``AssertionError`` on every code path that would
    spawn a child process.
    """

    def _refuse(*_a: Any, **_kw: Any) -> Any:
        raise AssertionError(
            "real subprocess forbidden in adversarial layer; "
            "see tests/adv/phase02/_helpers.py::forbid_real_subprocess"
        )

    monkeypatch.setattr(subprocess, "run", _refuse)
    monkeypatch.setattr(subprocess, "check_output", _refuse)
    monkeypatch.setattr(subprocess, "check_call", _refuse)
    monkeypatch.setattr(subprocess.Popen, "__init__", _refuse)

    async def _refuse_async(*_a: Any, **_kw: Any) -> Any:
        _refuse()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _refuse_async)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", _refuse_async)


@pytest.fixture
def clean_freshness_registry() -> Iterator[Any]:
    """Snapshot + restore the singleton freshness registry per test."""
    saved_checks = dict(default_freshness_registry._checks)
    saved_origins = dict(default_freshness_registry._origins)
    try:
        yield default_freshness_registry
    finally:
        default_freshness_registry._checks.clear()
        default_freshness_registry._origins.clear()
        default_freshness_registry._checks.update(saved_checks)
        default_freshness_registry._origins.update(saved_origins)
