"""S8-03 AC-3 — ``@requires_tool`` decorator contract.

The ``integration`` CI lane skips tests that need third-party binaries when
those binaries are missing on the runner. ``@requires_tool(name)`` standardizes
the skip reason format so an operator can grep ``SKIPPED LOUD`` in the CI log.
"""

from __future__ import annotations

import shutil
import warnings
from unittest import mock

import pytest

from tests._ci_support import requires_tool as rt


@pytest.fixture(autouse=True)
def _reset_seen_missing() -> None:
    rt.reset_missing_tool_cache()


def test_returns_a_pytest_mark() -> None:
    """The decorator returns a pytest mark (not a function transform).

    Composable with ``@pytest.mark.parametrize`` etc. because both sit on the
    same marker chain.
    """
    with mock.patch("tests._ci_support.requires_tool.shutil.which", return_value=None):
        marker = rt.requires_tool("nonexistent-tool")
    assert isinstance(marker, pytest.MarkDecorator), (
        "requires_tool must return a pytest mark — got " + repr(type(marker))
    )


def test_skip_reason_contains_skipped_loud_literal() -> None:
    """AC-3(a) — the skip reason must contain ``SKIPPED LOUD`` literal and the tool name."""
    with mock.patch("tests._ci_support.requires_tool.shutil.which", return_value=None):
        marker = rt.requires_tool("phantom-binary")
    reason = marker.kwargs["reason"]
    assert "SKIPPED LOUD" in reason
    assert "phantom-binary" in reason


def test_tool_present_does_not_skip() -> None:
    """When ``shutil.which`` finds the tool, the marker's condition is False."""
    with mock.patch("tests._ci_support.requires_tool.shutil.which", return_value="/usr/bin/found"):
        marker = rt.requires_tool("found-tool")
    # pytest.mark.skipif(condition, reason=...). args[0] is the condition.
    assert marker.args[0] is False, "tool present → skipif condition must be False"


def test_tool_missing_skips() -> None:
    with mock.patch("tests._ci_support.requires_tool.shutil.which", return_value=None):
        marker = rt.requires_tool("missing-tool")
    assert marker.args[0] is True, "tool missing → skipif condition must be True"


def test_warning_fires_once_per_missing_tool() -> None:
    """AC-3(b) — the warn-once-per-session contract."""
    with mock.patch("tests._ci_support.requires_tool.shutil.which", return_value=None):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            rt.requires_tool("one-shot-tool")
            rt.requires_tool("one-shot-tool")  # second call must be silent.
            rt.requires_tool("one-shot-tool")
        matched = [w for w in caught if "one-shot-tool" in str(w.message)]
        assert len(matched) == 1, (
            f"requires_tool must warn exactly once per missing tool per session; "
            f"got {len(matched)} warnings"
        )


def test_warning_fires_separately_for_different_tools() -> None:
    """Two distinct missing tools warn independently (dedup is per-tool-name)."""
    with mock.patch("tests._ci_support.requires_tool.shutil.which", return_value=None):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            rt.requires_tool("tool-a")
            rt.requires_tool("tool-b")
        names = {w for w in caught if "tool-" in str(w.message)}
        assert len(names) == 2


def test_composable_with_parametrize_mark() -> None:
    """AC-3(c) — composes with other marks."""

    # The decorator returns a marker; pytest's mark machinery stacks markers
    # additively. We assert structurally that two markers can coexist on a
    # synthetic function.
    @rt.requires_tool("anything")
    @pytest.mark.parametrize("x", [1, 2])
    def fake() -> None: ...

    marks = list(fake.pytestmark)  # type: ignore[attr-defined]
    assert any(m.name == "parametrize" for m in marks)
    assert any(m.name == "skipif" for m in marks)


def test_real_tool_lookup_is_not_mocked() -> None:
    """Smoke: shutil.which for ``python`` always succeeds — marker must not skip."""
    assert shutil.which("python") is not None or shutil.which("python3") is not None
    marker = rt.requires_tool("python")
    # The marker's truthiness depends on the actual lookup — python is usually
    # present, so condition is False.
    if shutil.which("python") is not None:
        assert marker.args[0] is False
