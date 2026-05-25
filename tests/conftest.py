"""Root test-suite conftest.

Two responsibilities:

- **S3-03** — exposes the :func:`egress_test_loopback` fixture, the only
  sanctioned opt-in to loopback admission under :class:`EgressGuard`
  (ADR-0006). The production path never sets the flag.
- **S3-04** — exposes the :func:`vcr_config` fixture, the ``pytest-recording``
  integration point. Hooks ``before_record_request`` /
  ``before_record_response`` to the ADR-0014 sanitizer so the first byte any
  cassette ever writes is already clean.

``CODEGENIE_LIVE_LLM=1`` flips ``record_mode`` to ``"all"`` (operator-only;
:mod:`tests/fence/test_cassette_discipline` enforces that no Makefile target
sets this var today). Otherwise ``record_mode="none"`` — a cassette miss is a
hard CI fail per ADR-0014 §Consequences.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from codegenie.fallback.cassette.sanitizer import (
    sanitize_request,
    sanitize_response,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CASSETTE_LIBRARY_DIR = _REPO_ROOT / "tests" / "cassettes"


@pytest.fixture
def egress_test_loopback() -> Iterator[None]:
    """Set the thread-scoped loopback opt-in for the duration of the test.

    The ``ContextVar`` is reset on teardown via
    :meth:`EgressGuard.reset_for_test`. Other threads spawned during the
    test run in an empty ``Context`` so the flag is invisible to them
    (the AC-8 isolation guarantee).
    """
    from codegenie.fallback.leaf.egress_guard import (
        EgressGuard,
        _test_only_loopback_enabled,
    )

    _test_only_loopback_enabled.set(True)
    try:
        yield
    finally:
        EgressGuard.reset_for_test()


@pytest.fixture
def vcr_config() -> dict[str, Any]:
    """``pytest-recording`` integration: hook the ADR-0014 sanitizer.

    AC-10 + AC-12. ``CODEGENIE_LIVE_LLM=1`` is the operator-only override
    (S3-06 will ship ``make refresh-cassettes`` as the sanctioned setter).
    The default in CI is unset → ``record_mode="none"`` → a cassette miss
    is a hard CI fail.
    """
    record_mode = "all" if os.environ.get("CODEGENIE_LIVE_LLM") == "1" else "none"
    return {
        "before_record_request": sanitize_request,
        "before_record_response": sanitize_response,
        # Belt-and-suspenders — pytest-recording's own header filter on top of
        # our sanitizer (so a regression in either layer still strips headers).
        "filter_headers": [
            "authorization",
            "x-api-key",
            "cookie",
            "set-cookie",
            "anthropic-version",
        ],
        "record_mode": record_mode,
        "cassette_library_dir": str(_CASSETTE_LIBRARY_DIR),
    }
