"""Unit tests for ``codegenie.probes.layer_c.scenario_result`` — story 02 S5-01.

Mirrors the discipline established by ``tests/unit/indices/test_freshness.py``
(S1-01) — the 1st canonical sum-type story in Phase 2. This is the 2nd: the
nested ``reason`` discriminated unions (``TraceFailureReason`` /
``TraceSkipReason``) are rehearsed with their own exhaustive ``match`` ladder
because S5-05 (freshness check) and S8-01 (renderer) will ``match`` on them.
"""

from __future__ import annotations

from pathlib import Path
from typing import assert_never

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.probes.layer_c.scenario_result import (
    DockerBuildFailed,
    ImageBuildUnavailable,
    ImageDigestUnresolved,
    NoDockerfile,
    ScenarioResult,
    ScenarioTimeout,
    StraceUnavailable,
    TraceFailureReason,
    TraceScenarioCompleted,
    TraceScenarioFailed,
    TraceScenarioSkipped,
    TraceSkipReason,
)

# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------

FAILURE_REASONS: list[TraceFailureReason] = [
    StraceUnavailable(),
    DockerBuildFailed(stderr_tail="docker daemon unreachable"),
    ScenarioTimeout(elapsed_ms=30_000),
    ImageDigestUnresolved(ref="nginx:1.25"),
]
SKIP_REASONS: list[TraceSkipReason] = [
    NoDockerfile(),
    ImageBuildUnavailable(),
]

SCENARIO_RESULTS: list[ScenarioResult] = [
    TraceScenarioCompleted(
        scenario_name="startup",
        artifact_uri=Path("/tmp/trace/startup.json"),
        wall_clock_ms=1234,
        syscalls_observed=42,
        shared_libs_count=7,
    ),
    *(TraceScenarioFailed(scenario_name="startup", reason=reason) for reason in FAILURE_REASONS),
    *(TraceScenarioSkipped(scenario_name="startup", reason=reason) for reason in SKIP_REASONS),
]


# ---------------------------------------------------------------------------
# AC-5 — round-trip identity + nested-type preservation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("instance", SCENARIO_RESULTS)
def test_scenario_result_roundtrip_identity(instance: ScenarioResult) -> None:
    adapter: TypeAdapter[ScenarioResult] = TypeAdapter(ScenarioResult)
    encoded = adapter.dump_json(instance)
    decoded = adapter.validate_json(encoded)
    assert decoded == instance
    assert type(decoded) is type(instance)
    if isinstance(instance, TraceScenarioFailed):
        assert isinstance(decoded, TraceScenarioFailed)
        assert type(decoded.reason) is type(instance.reason)
    if isinstance(instance, TraceScenarioSkipped):
        assert isinstance(decoded, TraceScenarioSkipped)
        assert type(decoded.reason) is type(instance.reason)


# ---------------------------------------------------------------------------
# AC-12 — discriminator strings exactly pinned (cross-doc contract).
# ---------------------------------------------------------------------------


def test_scenario_result_discriminator_strings_are_exactly_pinned() -> None:
    assert (
        TraceScenarioCompleted(
            scenario_name="x",
            artifact_uri=Path("/tmp/x"),
            wall_clock_ms=1,
            syscalls_observed=0,
            shared_libs_count=0,
        ).kind
        == "completed"
    )
    assert TraceScenarioFailed(scenario_name="x", reason=StraceUnavailable()).kind == "failed"
    assert TraceScenarioSkipped(scenario_name="x", reason=NoDockerfile()).kind == "skipped"


def test_trace_failure_reason_discriminator_strings_are_exactly_pinned() -> None:
    assert StraceUnavailable().kind == "strace_unavailable"
    assert DockerBuildFailed(stderr_tail="").kind == "docker_build_failed"
    assert ScenarioTimeout(elapsed_ms=1).kind == "scenario_timeout"
    assert ImageDigestUnresolved(ref="x").kind == "image_digest_unresolved"


def test_trace_skip_reason_discriminator_strings_are_exactly_pinned() -> None:
    assert NoDockerfile().kind == "no_dockerfile"
    assert ImageBuildUnavailable().kind == "image_build_unavailable"


# ---------------------------------------------------------------------------
# AC-13 — JSON shape pinned.
# ---------------------------------------------------------------------------


def test_trace_scenario_failed_json_shape_pinned() -> None:
    dump = TraceScenarioFailed(scenario_name="startup", reason=StraceUnavailable()).model_dump(
        mode="json"
    )
    assert dump == {
        "kind": "failed",
        "scenario_name": "startup",
        "reason": {"kind": "strace_unavailable"},
    }


# ---------------------------------------------------------------------------
# AC-14 — unknown discriminator rejected at every level.
# ---------------------------------------------------------------------------


def test_scenario_result_unknown_discriminator_is_rejected() -> None:
    adapter: TypeAdapter[ScenarioResult] = TypeAdapter(ScenarioResult)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "bogus_scenario"})


def test_trace_failure_reason_unknown_discriminator_is_rejected() -> None:
    adapter: TypeAdapter[TraceFailureReason] = TypeAdapter(TraceFailureReason)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "bogus_reason"})


def test_trace_skip_reason_unknown_discriminator_is_rejected() -> None:
    adapter: TypeAdapter[TraceSkipReason] = TypeAdapter(TraceSkipReason)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "bogus_skip"})


# ---------------------------------------------------------------------------
# AC-6 — exhaustive match at every level of the sum.
# ---------------------------------------------------------------------------


def test_scenario_result_match_is_exhaustive() -> None:
    seen: set[str] = set()
    for result in SCENARIO_RESULTS:
        match result:
            case TraceScenarioCompleted():
                seen.add("completed")
            case TraceScenarioFailed():
                seen.add("failed")
            case TraceScenarioSkipped():
                seen.add("skipped")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"completed", "failed", "skipped"}


def test_trace_failure_reason_match_is_exhaustive() -> None:
    seen: set[str] = set()
    for reason in FAILURE_REASONS:
        match reason:
            case StraceUnavailable():
                seen.add("strace_unavailable")
            case DockerBuildFailed():
                seen.add("docker_build_failed")
            case ScenarioTimeout():
                seen.add("scenario_timeout")
            case ImageDigestUnresolved():
                seen.add("image_digest_unresolved")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {
        "strace_unavailable",
        "docker_build_failed",
        "scenario_timeout",
        "image_digest_unresolved",
    }


def test_trace_skip_reason_match_is_exhaustive() -> None:
    seen: set[str] = set()
    for reason in SKIP_REASONS:
        match reason:
            case NoDockerfile():
                seen.add("no_dockerfile")
            case ImageBuildUnavailable():
                seen.add("image_build_unavailable")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"no_dockerfile", "image_build_unavailable"}


# ---------------------------------------------------------------------------
# AC-17 — frozen + extra="forbid".
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("instance", SCENARIO_RESULTS)
def test_scenario_results_are_frozen(instance: ScenarioResult) -> None:
    with pytest.raises(ValidationError):
        instance.kind = "other"  # type: ignore[misc]


def test_trace_scenario_completed_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        TraceScenarioCompleted.model_validate(
            {
                "kind": "completed",
                "scenario_name": "x",
                "artifact_uri": "/tmp/x",
                "wall_clock_ms": 1,
                "syscalls_observed": 0,
                "shared_libs_count": 0,
                "extra_field": 1,
            }
        )


def test_trace_scenario_failed_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        TraceScenarioFailed.model_validate(
            {
                "kind": "failed",
                "scenario_name": "x",
                "reason": {"kind": "strace_unavailable"},
                "extra_field": 1,
            }
        )


def test_trace_scenario_skipped_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        TraceScenarioSkipped.model_validate(
            {
                "kind": "skipped",
                "scenario_name": "x",
                "reason": {"kind": "no_dockerfile"},
                "extra_field": 1,
            }
        )


# ---------------------------------------------------------------------------
# AC-18 — ``__all__`` pinned literally.
# ---------------------------------------------------------------------------


EXPECTED_SCENARIO_NAMES = {
    "DockerBuildFailed",
    "ImageBuildUnavailable",
    "ImageDigestUnresolved",
    "NoDockerfile",
    "ScenarioResult",
    "ScenarioTimeout",
    "StraceUnavailable",
    "TraceFailureReason",
    "TraceScenarioCompleted",
    "TraceScenarioFailed",
    "TraceScenarioSkipped",
    "TraceSkipReason",
}


def test_scenario_result_all_exports_are_pinned() -> None:
    import codegenie.probes.layer_c.scenario_result as mod

    assert set(mod.__all__) == EXPECTED_SCENARIO_NAMES


# ---------------------------------------------------------------------------
# Source-scan against ``model_construct``.
# ---------------------------------------------------------------------------


def test_scenario_result_module_has_no_model_construct() -> None:
    import codegenie.probes.layer_c.scenario_result as mod

    source = Path(mod.__file__).read_text()
    assert "model_construct" not in source
