"""Pure-function tests for parse / derive / aggregate helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.probes.layer_c.runtime_trace import (
    ParsedTrace,
    _aggregate_scenarios,
    _derive_trace_coverage_confidence,
    _envelope_confidence,
    _parse_strace_lines,
)
from codegenie.probes.layer_c.scenario_result import (
    DockerBuildFailed,
    ImageBuildUnavailable,
    ImageDigestUnresolved,
    StraceUnavailable,
    TraceScenarioCompleted,
    TraceScenarioFailed,
    TraceScenarioSkipped,
)


# ---------------------------------------------------------------------------
# _parse_strace_lines
# ---------------------------------------------------------------------------


def _golden_strace_path() -> Path:
    return Path(__file__).resolve().parents[3] / "fixtures" / "strace" / "minimal.strace"


def test_parse_strace_lines_golden_fixture_captures_known_fields() -> None:
    lines = _golden_strace_path().read_text(encoding="utf-8").splitlines()
    parsed = _parse_strace_lines(lines)
    assert "sh" in parsed.binaries_executed
    assert "bash" in parsed.binaries_executed
    assert any("libc.so" in p for p in parsed.shared_libs_loaded)
    assert any(".crt" in p or "ca-certificates" in p for p in parsed.cert_paths_read)
    assert parsed.shell_invocations >= 2  # two execve calls into shells
    assert ("1.2.3.4", "443") in parsed.network_endpoints_touched


def test_parse_strace_lines_malformed_returns_all_empty() -> None:
    parsed = _parse_strace_lines(["this is not strace output", "neither is this"])
    assert parsed.binaries_executed == frozenset()
    assert parsed.shared_libs_loaded == frozenset()
    assert parsed.cert_paths_read == frozenset()
    assert parsed.files_read_at_runtime == frozenset()
    assert parsed.shell_invocations == 0
    assert parsed.network_endpoints_touched == frozenset()


def test_parse_strace_lines_permutation_stability_for_set_fields() -> None:
    """Reversing the lines preserves all set-valued fields exactly."""
    lines = _golden_strace_path().read_text(encoding="utf-8").splitlines()
    forward = _parse_strace_lines(lines)
    backward = _parse_strace_lines(list(reversed(lines)))
    assert forward.binaries_executed == backward.binaries_executed
    assert forward.shared_libs_loaded == backward.shared_libs_loaded
    assert forward.cert_paths_read == backward.cert_paths_read
    assert forward.files_read_at_runtime == backward.files_read_at_runtime
    assert forward.network_endpoints_touched == backward.network_endpoints_touched
    # shell_invocations is the documented count-valued non-commutative
    # exception (counts are stable but ordering of execve lineages may not be).
    assert forward.shell_invocations == backward.shell_invocations


# ---------------------------------------------------------------------------
# _derive_trace_coverage_confidence  (tetra-state mapping)
# ---------------------------------------------------------------------------


def _completed(name: str) -> TraceScenarioCompleted:
    return TraceScenarioCompleted(
        scenario_name=name,
        artifact_uri=Path(f"/tmp/{name}.strace"),
        wall_clock_ms=10,
        syscalls_observed=1,
        shared_libs_count=0,
    )


def _failed(name: str) -> TraceScenarioFailed:
    return TraceScenarioFailed(
        scenario_name=name,
        reason=StraceUnavailable(),
    )


@pytest.mark.parametrize(
    "results, expected",
    [
        (
            [
                _completed("startup"),
                _completed("smoke_test"),
                _completed("healthcheck"),
                _completed("shutdown"),
                _completed("error_path"),
            ],
            "high",
        ),
        ([_completed("startup"), _completed("smoke_test")], "medium"),
        ([_completed("smoke_test")], "medium"),
        ([_completed("startup")], "low"),
        ([_failed("startup")], "unavailable"),
        ([], "unavailable"),
    ],
)
def test_derive_trace_coverage_confidence_mapping(
    results: list, expected: str
) -> None:
    assert _derive_trace_coverage_confidence(results) == expected


# ---------------------------------------------------------------------------
# _envelope_confidence  (contract preservation — clip to tri-state)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slice_confidence, expected",
    [
        ("high", "high"),
        ("medium", "medium"),
        ("low", "low"),
        ("unavailable", "low"),
    ],
)
def test_envelope_confidence_clips_to_tri_state(
    slice_confidence: str, expected: str
) -> None:
    assert _envelope_confidence(slice_confidence) == expected  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _aggregate_scenarios — routing of Completed / Failed / Skipped
# ---------------------------------------------------------------------------


def test_aggregate_routes_completed_failed_skipped_correctly() -> None:
    results = [
        _completed("a"),
        _failed("b"),
        TraceScenarioSkipped(
            scenario_name="c",
            reason=ImageBuildUnavailable(),
        ),
        _completed("d"),
        _failed("e"),
    ]
    agg = _aggregate_scenarios(results, {})
    assert agg.scenarios_run == ["a", "d"]
    assert agg.scenarios_failed == ["b", "e"]
    assert set(agg.per_scenario_artifacts.keys()) == {"a", "b", "c", "d", "e"}
    assert agg.per_scenario_artifacts["c"] is None
    assert agg.per_scenario_artifacts["b"] is None


def test_aggregate_folds_parsed_traces_for_completed_only() -> None:
    results = [_completed("a"), _failed("b")]
    parsed = {
        "a": ParsedTrace(
            binaries_executed=frozenset({"sh"}),
            shared_libs_loaded=frozenset({"/libc.so"}),
        )
    }
    agg = _aggregate_scenarios(results, parsed)
    assert "sh" in agg.binaries_executed
    assert "/libc.so" in agg.shared_libs_loaded
