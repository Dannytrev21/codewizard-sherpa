"""S8-03 AC-8 — baseline metadata header contract.

Both committed baselines (``portfolio_walltime.json`` and
``portfolio_walltime_hosted_runner.json``) must carry the three metadata
keys ``refreshed_at``, ``refreshed_by``, ``reason`` so a future reviewer
can audit baseline-refresh PRs via ``git log``. A baseline that drops the
header is a deception risk: it lets a contributor regenerate the JSON
silently to hide a real regression.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASELINES_DIR = _REPO_ROOT / "tests" / "bench" / "baselines"

_BASELINES = [
    _BASELINES_DIR / "portfolio_walltime.json",
    _BASELINES_DIR / "portfolio_walltime_hosted_runner.json",
]


@pytest.mark.parametrize("path", _BASELINES, ids=lambda p: p.name)
def test_metadata_header_present_and_non_empty(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in ("refreshed_at", "refreshed_by", "reason"):
        assert key in raw, f"{path.name} missing '{key}' metadata header key"
        assert raw[key], f"{path.name}: '{key}' must be non-empty (audit trail)"


@pytest.mark.parametrize("path", _BASELINES, ids=lambda p: p.name)
def test_measurements_map_present_and_typed_as_floats(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "measurements" in raw, f"{path.name} missing 'measurements' map"
    measurements = raw["measurements"]
    assert isinstance(measurements, dict) and measurements, (
        f"{path.name}: 'measurements' must be a non-empty mapping"
    )
    for name, value in measurements.items():
        assert isinstance(name, str)
        assert isinstance(value, (int, float)), (
            f"{path.name}: measurement {name} is {type(value).__name__}, expected number"
        )


def test_refreshed_at_is_iso_8601_utc() -> None:
    """``refreshed_at`` must end with ``Z`` (UTC) so audit logs are unambiguous."""
    for path in _BASELINES:
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["refreshed_at"].endswith("Z"), (
            f"{path.name}: refreshed_at must be UTC ISO-8601 ending in 'Z'; "
            f"got {raw['refreshed_at']!r}"
        )
