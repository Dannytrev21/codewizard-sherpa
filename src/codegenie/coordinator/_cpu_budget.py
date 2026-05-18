"""CPU-budget wrapper for the coordinator's Semaphore sizing (S8-03 AC-10a).

The coordinator historically read ``os.cpu_count() or 1`` directly. The
hosted-runner bench (`bench_portfolio_walltime_hosted_runner.py`, Gap 2 closer)
needs to emulate the GitHub Actions runner shape (`cpu_count() == 2`) on
arbitrarily-sized developer laptops, so we route the read through this
single helper. ``CODEGENIE_FORCE_CPU_COUNT`` (positive int) wins when set;
empty / unset falls back to ``os.cpu_count() or 1``.

Pure function; no side effects beyond reading the environment. The coordinator
imports ``effective_cpu_count`` at module-import time but calls it on each
``gather()`` so a test can monkeypatch ``os.environ`` between invocations.
"""

from __future__ import annotations

import os
from typing import Final

_ENV_VAR: Final[str] = "CODEGENIE_FORCE_CPU_COUNT"


def effective_cpu_count() -> int:
    """Return the CPU count the coordinator should size its Semaphore against.

    Reads ``CODEGENIE_FORCE_CPU_COUNT`` (positive integer) and falls back to
    ``os.cpu_count() or 1`` when the env-var is absent or empty.

    Raises ``ValueError`` when the env-var is set to a non-empty string that
    is not a positive integer. The error message names the env-var so an
    operator hitting this in CI can locate the offending workflow line.
    """
    raw = os.environ.get(_ENV_VAR, "")
    if raw == "":
        return os.cpu_count() or 1
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{_ENV_VAR}={raw!r} is not an integer; "
            "set a positive int (e.g. '2' for hosted-runner emulation) or unset"
        ) from exc
    if value <= 0:
        raise ValueError(f"{_ENV_VAR}={raw!r} must be a positive integer; got {value}")
    return value
