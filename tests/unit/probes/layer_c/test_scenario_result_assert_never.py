"""S7-05 AC-23 — exhaustive ``match`` over ``ScenarioResult`` variants.

Mirror of ``tests/unit/indices/test_freshness_assert_never.py`` (AC-5).
Repo-wide ``warn_unreachable = true`` (pyproject.toml) fires a build
error if any variant is missed at the ``case _: assert_never(_)`` arm.
"""

from __future__ import annotations

from pathlib import Path
from typing import assert_never

from codegenie.probes.layer_c.scenario_result import (
    ImageBuildUnavailable,
    NoDockerfile,
    ScenarioResult,
    StraceUnavailable,
    TraceScenarioCompleted,
    TraceScenarioFailed,
    TraceScenarioSkipped,
)


def _stringify(x: ScenarioResult) -> str:
    """Exhaustive match across the closed ``ScenarioResult`` sum."""
    match x:
        case TraceScenarioCompleted():
            return f"completed:{x.scenario_name}"
        case TraceScenarioFailed():
            return f"failed:{x.scenario_name}"
        case TraceScenarioSkipped():
            return f"skipped:{x.scenario_name}"
        case _:  # pragma: no cover — mypy enforces exhaustiveness
            assert_never(x)


def test_exhaustive_match_scenario_result_assert_never() -> None:
    """One instance per variant; runtime cross-check of dispatch arms."""
    completed = TraceScenarioCompleted(
        scenario_name="startup",
        artifact_uri=Path("/tmp/x.json"),
        wall_clock_ms=10,
        syscalls_observed=0,
        shared_libs_count=0,
    )
    failed = TraceScenarioFailed(scenario_name="run", reason=StraceUnavailable())
    skipped_no_dockerfile = TraceScenarioSkipped(scenario_name="run", reason=NoDockerfile())
    skipped_image_build = TraceScenarioSkipped(scenario_name="run", reason=ImageBuildUnavailable())

    assert _stringify(completed) == "completed:startup"
    assert _stringify(failed) == "failed:run"
    assert _stringify(skipped_no_dockerfile) == "skipped:run"
    assert _stringify(skipped_image_build) == "skipped:run"
