"""Shared fixtures for ``tests/integration/cli/`` (S8-02).

The autouse fixture here no-ops :func:`codegenie.cli._seam_configure_logging`
so :func:`structlog.testing.capture_logs` survives across the
``CliRunner.invoke`` boundary. Mirrors :file:`tests/smoke/conftest.py` —
without this, every ``codegenie gather`` invocation re-applies the
``structlog`` processor chain and the in-test ``LogCapture`` is silently
clobbered.

:func:`capture_spanning_events` (S3-05 AC-46) reads the spanning-stream
substrate ``<cache_dir>/../events/spanning/append.jsonl.zst``. S6-01
absorbed the interim uncompressed ``append.jsonl`` into the BLAKE3-chained
``jsonl.zst`` format, so the fixture now decodes via the canonical
:meth:`codegenie.plugins.events.EventLog.replay` reader — a decoder swap, as
the S3-05 docstring promised.
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
    """Return a callable that decodes the spanning event stream for a cache dir.

    Reads ``<cache_dir>/../events/spanning/append.jsonl.zst`` after CLI exit
    via :meth:`codegenie.plugins.events.EventLog.replay` — the canonical
    BLAKE3-chain-verifying reader — and returns the decoded spanning events.
    """

    def _read(cache_dir: Path) -> list:
        from codegenie.plugins.events import EventLog
        from codegenie.types.identifiers import WorkflowId

        spanning = cache_dir.parent / "events" / "spanning" / "append.jsonl.zst"
        if not spanning.exists():
            return []
        event_log = EventLog(root=cache_dir.parent, workflow_id=WorkflowId("operator_cli"))
        return list(event_log.replay())

    return _read
