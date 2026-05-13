"""Shared fixtures for the Phase-0 adversarial suite (S4-05).

Every test that drives the CLI through ``click.testing.CliRunner.invoke``
needs ``codegenie.cli._seam_configure_logging`` no-oped — the seam calls
``configure_logging`` which replaces structlog's processor chain, clobbering
the ``LogCapture`` processor that :func:`structlog.testing.capture_logs`
swaps in. Without this autouse fixture, ``capture_logs`` returns an empty
list and the symlink-escape test's event assertions silently pass for the
wrong reason.

Mirrors :mod:`tests.smoke.conftest._disable_cli_configure_logging` (S4-04).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_cli_configure_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """No-op ``cli._seam_configure_logging`` so ``capture_logs`` stays live.

    See module docstring for the false-positive failure mode this closes.
    """
    import codegenie.cli

    monkeypatch.setattr(codegenie.cli, "_seam_configure_logging", lambda verbose: None)
