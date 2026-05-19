"""Shared fixtures for ``tests/integration/cli/`` (S8-02).

The autouse fixture here no-ops :func:`codegenie.cli._seam_configure_logging`
so :func:`structlog.testing.capture_logs` survives across the
``CliRunner.invoke`` boundary. Mirrors :file:`tests/smoke/conftest.py` —
without this, every ``codegenie gather`` invocation re-applies the
``structlog`` processor chain and the in-test ``LogCapture`` is silently
clobbered.

:func:`capture_spanning_events` is S3-05 AC-46 — reads the interim
JSON-lines spanning-stream substrate ``<cache_dir>/../events/spanning/
append.jsonl`` and decodes each line into a
:class:`~codegenie.plugins.cache_gc.CacheGcCompletedEvent`. S6-01
absorbs that file additively into the chained zstd format; tests do
not need to rewrite when that lands (decoder swap only).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _disable_cli_configure_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preserve :func:`structlog.testing.capture_logs` across ``CliRunner``."""
    import codegenie.cli

    monkeypatch.setattr(codegenie.cli, "_seam_configure_logging", lambda verbose: None)


@pytest.fixture
def capture_spanning_events() -> Callable[[Path], list]:
    """Return a callable that decodes the spanning JSON-lines log for a cache dir.

    Reads ``<cache_dir>/../events/spanning/append.jsonl`` after CLI
    exit; returns ``list[CacheGcCompletedEvent]`` decoded via
    :meth:`~codegenie.plugins.cache_gc.CacheGcCompletedEvent.model_validate_json`
    on each non-empty line. Interim wire format per S3-05 AC-45.
    """

    def _read(cache_dir: Path) -> list:
        from codegenie.plugins.cache_gc import CacheGcCompletedEvent

        jl = cache_dir.parent / "events" / "spanning" / "append.jsonl"
        if not jl.exists():
            return []
        return [
            CacheGcCompletedEvent.model_validate_json(line)
            for line in jl.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    return _read
