"""Unit tests for ``codegenie.coordinator._cpu_budget`` (S8-03 AC-10a).

Covers the env-var override + fallback contract used by the hosted-runner
bench to emulate ``cpu_count() == 2`` regardless of the host's actual
CPU count. A bench script that imports the coordinator BEFORE setting
``CODEGENIE_FORCE_CPU_COUNT`` would still get the override because
``effective_cpu_count()`` reads the env-var on each call, not at import.
"""

from __future__ import annotations

import os
from typing import Final
from unittest import mock

import pytest

from codegenie.coordinator._cpu_budget import effective_cpu_count

_ENV_VAR: Final[str] = "CODEGENIE_FORCE_CPU_COUNT"


@pytest.fixture(autouse=True)
def _clear_env_var() -> None:
    """Strip the env-var before each test so the fallback path is reachable."""
    os.environ.pop(_ENV_VAR, None)


def test_env_var_absent_falls_back_to_os_cpu_count() -> None:
    expected = os.cpu_count() or 1
    assert effective_cpu_count() == expected


def test_env_var_empty_string_falls_back() -> None:
    os.environ[_ENV_VAR] = ""
    expected = os.cpu_count() or 1
    assert effective_cpu_count() == expected


@pytest.mark.parametrize("raw,expected", [("1", 1), ("2", 2), ("8", 8), ("32", 32)])
def test_env_var_positive_integer_is_honored(raw: str, expected: int) -> None:
    os.environ[_ENV_VAR] = raw
    assert effective_cpu_count() == expected


@pytest.mark.parametrize("raw", ["abc", "1.5", "two", "2x", "  ", "0x2"])
def test_env_var_non_integer_raises_value_error(raw: str) -> None:
    os.environ[_ENV_VAR] = raw
    with pytest.raises(ValueError, match=_ENV_VAR):
        effective_cpu_count()


@pytest.mark.parametrize("raw", ["0", "-1", "-100"])
def test_env_var_non_positive_int_raises_value_error(raw: str) -> None:
    os.environ[_ENV_VAR] = raw
    with pytest.raises(ValueError, match=_ENV_VAR):
        effective_cpu_count()


def test_value_error_message_names_env_var_for_operator_debugging() -> None:
    os.environ[_ENV_VAR] = "nope"
    with pytest.raises(ValueError) as exc:
        effective_cpu_count()
    # Operator scanning CI logs must see the env-var name and the offending value.
    assert _ENV_VAR in str(exc.value)
    assert "nope" in str(exc.value)


def test_fallback_when_os_cpu_count_returns_none() -> None:
    with mock.patch("codegenie.coordinator._cpu_budget.os.cpu_count", return_value=None):
        assert effective_cpu_count() == 1


def test_coordinator_imports_and_uses_effective_cpu_count() -> None:
    """AC-10a(f): coordinator's Semaphore reads via ``effective_cpu_count()``.

    Structural check: ``coordinator.py`` source imports ``effective_cpu_count``
    from ``_cpu_budget`` AND invokes it in the gather Semaphore sizing
    expression. The literal ``os.cpu_count() or 1`` form is gone.
    """
    import inspect

    from codegenie.coordinator import coordinator

    src = inspect.getsource(coordinator)
    assert "from codegenie.coordinator._cpu_budget import effective_cpu_count" in src, (
        "coordinator must import effective_cpu_count from _cpu_budget"
    )
    assert "cpu = effective_cpu_count()" in src, (
        "coordinator must size its Semaphore via effective_cpu_count()"
    )
    assert "os.cpu_count() or 1" not in src, (
        "coordinator must not read os.cpu_count() directly — go through "
        "effective_cpu_count() so CODEGENIE_FORCE_CPU_COUNT is honored"
    )
