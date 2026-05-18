"""Shared fixtures for ``tests/integration/cli/`` (S8-02).

The single autouse fixture here no-ops :func:`codegenie.cli._seam_configure_logging`
so :func:`structlog.testing.capture_logs` survives across the
``CliRunner.invoke`` boundary. Mirrors :file:`tests/smoke/conftest.py` —
without this, every ``codegenie gather`` invocation re-applies the
``structlog`` processor chain and the in-test ``LogCapture`` is silently
clobbered.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_cli_configure_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preserve :func:`structlog.testing.capture_logs` across ``CliRunner``."""
    import codegenie.cli

    monkeypatch.setattr(codegenie.cli, "_seam_configure_logging", lambda verbose: None)
