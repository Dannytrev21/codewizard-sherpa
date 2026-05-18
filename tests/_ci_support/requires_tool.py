"""``@requires_tool`` decorator for the ``integration`` CI lane (S8-03 AC-3).

Wraps ``pytest.mark.skipif(shutil.which(name) is None, ...)`` with a loud,
operator-grep-friendly skip reason. Also emits a one-shot ``warnings.warn``
the FIRST time a tool is observed missing in a given pytest session — so
the skip is visible in the CI ``--tb=short`` summary, not just buried in
each test's report line.

The skip-reason literal contains ``SKIPPED LOUD`` so an operator scanning
the CI summary for the tool-presence preflight can grep for it.
"""

from __future__ import annotations

import shutil
import warnings
from collections.abc import Callable
from typing import Any, TypeVar

import pytest

F = TypeVar("F", bound=Callable[..., Any])

_seen_missing: set[str] = set()


def requires_tool(name: str) -> Callable[[F], F]:
    """Skip the decorated test if ``name`` is not on ``$PATH``.

    The decorator:
      * Wraps ``pytest.mark.skipif(shutil.which(name) is None, ...)``
        with the literal skip reason ``"{name} not on PATH — SKIPPED LOUD"``.
      * Emits ``warnings.warn(..., stacklevel=2)`` exactly once per missing
        tool per session (deduped via a module-level set). Subsequent calls
        for the same tool are silent.
      * Composes with any other pytest mark (``parametrize``, ``asyncio``,
        etc.) — it returns a marker, not a transform.
    """
    reason = f"{name} not on PATH — SKIPPED LOUD"
    missing = shutil.which(name) is None
    if missing and name not in _seen_missing:
        _seen_missing.add(name)
        warnings.warn(
            f"requires_tool: {name} missing from PATH; tests decorated with "
            f"@requires_tool({name!r}) will skip with reason: {reason!r}",
            stacklevel=2,
        )
    return pytest.mark.skipif(missing, reason=reason)  # type: ignore[return-value]


def reset_missing_tool_cache() -> None:
    """Test helper — clears the ``_seen_missing`` set between sessions."""
    _seen_missing.clear()
