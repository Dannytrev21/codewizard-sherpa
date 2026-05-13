"""Shared fixtures for the smoke suite (S4-04).

Three helpers live here:

- :func:`_copy_fixture` (function not pytest fixture) — clones one of the
  three Phase-0 fixtures (``empty_repo`` / ``js_only`` / ``polyglot``) into
  ``tmp_path`` so each test's mutations of ``<fixture>/.codegenie/`` stay
  hermetic. ``shutil.copytree`` follows symlinks-as-files; none of the
  ship-bundled fixtures contain symlinks, so the default behavior is safe.
- :func:`_install_scandir_counter` — replaces the ``os`` *name binding* on
  the ``codegenie.probes.language_detection`` module with a
  :class:`types.SimpleNamespace` shim that mirrors every public attribute of
  :mod:`os` and overrides ``scandir`` with a counting wrapper. The patch
  scope is module-local (only ``language_detection`` sees the counter); the
  global :mod:`os` module is untouched, so cache / writer / audit / pytest
  internals that call ``os.scandir`` during the warm run do NOT increment
  the counter. See ``S4-04`` story §"Notes for the implementer / TQ-1" for
  the false-RED failure mode this design closes.
- :func:`_disable_cli_configure_logging` — autouse monkeypatch that no-ops
  ``codegenie.cli._seam_configure_logging`` for the smoke tests. The seam
  calls :func:`codegenie.logging.configure_logging` inside the
  :class:`click.testing.CliRunner.invoke` body, which replaces structlog's
  processor chain and clobbers :func:`structlog.testing.capture_logs`. By
  no-oping the seam, the chain capture_logs swaps in stays live for the
  duration of the ``with`` block. Events still flow because
  ``structlog.get_logger`` was set up at module import time.
"""

from __future__ import annotations

import os
import shutil
import types
from pathlib import Path

import pytest

__all__ = ["_copy_fixture", "_install_scandir_counter"]


def _copy_fixture(name: str, dst: Path) -> Path:
    """Clone ``tests/fixtures/<name>/`` into ``<dst>/<name>/``; return the dst."""
    src = Path(__file__).parent.parent / "fixtures" / name
    target = dst / name
    shutil.copytree(src, target)
    return target


def _install_scandir_counter(
    monkeypatch: pytest.MonkeyPatch, ld_mod: types.ModuleType
) -> dict[str, int]:
    """Module-local scandir-counting shim — see module docstring for why.

    Replaces ``ld_mod.os`` (the ``os`` name binding *inside* the
    ``language_detection`` module) with a :class:`SimpleNamespace` carrying
    every attribute of :mod:`os` plus a counting ``scandir``. The global
    :mod:`os` module is NOT mutated; only the probe's lookup path sees the
    counter.

    Why not ``monkeypatch.setattr(ld_mod.os, "scandir", ...)``? Because
    ``ld_mod.os IS os``: that form mutates the shared :mod:`os` module and
    produces false-RED whenever cache / writer / audit / pytest internals
    call ``os.scandir`` during the warm run.
    """
    calls = {"count": 0}
    real_scandir = os.scandir

    def counting_scandir(*args: object, **kwargs: object) -> object:
        calls["count"] += 1
        return real_scandir(*args, **kwargs)  # type: ignore[arg-type]

    shim = types.SimpleNamespace()
    for attr in dir(os):
        if not attr.startswith("_"):
            setattr(shim, attr, getattr(os, attr))
    shim.scandir = counting_scandir
    monkeypatch.setattr(ld_mod, "os", shim)
    return calls


@pytest.fixture(autouse=True)
def _disable_cli_configure_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """No-op ``_seam_configure_logging`` for smoke tests.

    The seam calls :func:`codegenie.logging.configure_logging` which replaces
    structlog's active processor chain. :func:`structlog.testing.capture_logs`
    works by swapping its own ``LogCapture`` processor into that chain; a
    re-configure inside ``CliRunner.invoke`` blows it away and the test sees
    no events. Disabling the seam for smoke tests preserves the
    capture_logs chain for the duration of the ``with`` block.
    """
    import codegenie.cli

    monkeypatch.setattr(codegenie.cli, "_seam_configure_logging", lambda verbose: None)
