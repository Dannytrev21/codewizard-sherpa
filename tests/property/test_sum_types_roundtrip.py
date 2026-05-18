"""Hypothesis property test for ``ScannerOutcome`` and ``ScenarioResult``.

AC-15 of story 02 S5-01. Required deliverable per 02-ADR-0006 §Consequences
pattern (Hypothesis round-trip for every sum-type kernel) — symmetric with
``tests/property/test_index_freshness_roundtrip.py`` (S1-01).

Bounds match the per-outcome smart-constructor caps:

- ``exit_code ∈ [0, 255]`` (POSIX exit-code range)
- ``stderr_tail`` length ∈ ``[0, STDERR_TAIL_CAP_BYTES]`` (4096 bytes)
- ``scenario_name`` printable ASCII length ∈ [1, 64]
- ``findings`` list length ∈ [0, 16]
- ``metadata`` is recursive JSON with depth bound 4 (matches Phase 1's
  ``JSONValue`` depth cap policy)
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import TypeAdapter

from codegenie.probes._shared.scanner_outcome import (
    STDERR_TAIL_CAP_BYTES,
    Finding,
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.layer_c.scenario_result import (
    DockerBuildFailed,
    ImageBuildUnavailable,
    ImageDigestUnresolved,
    NoDockerfile,
    ScenarioResult,
    ScenarioTimeout,
    StraceUnavailable,
    TraceScenarioCompleted,
    TraceScenarioFailed,
    TraceScenarioSkipped,
)

# ---------------------------------------------------------------------------
# Strategies — JSONValue tree, bounded depth.
# ---------------------------------------------------------------------------

_printable_ascii = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=0,
    max_size=64,
)

_scenario_name = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=64,
)

_json_value = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**31), max_value=2**31 - 1),
        st.floats(allow_nan=False, allow_infinity=False, width=32),
        _printable_ascii,
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(_printable_ascii, children, max_size=4),
    ),
    max_leaves=8,
)

_metadata = st.dictionaries(_printable_ascii, _json_value, max_size=4)

_finding = st.builds(
    Finding,
    id=_printable_ascii.filter(lambda s: len(s) >= 1),
    severity=st.sampled_from(["info", "low", "medium", "high", "critical"]),
    metadata=_metadata,
)

# ---------------------------------------------------------------------------
# Strategies — ScannerOutcome variants.
# ---------------------------------------------------------------------------

_scanner_ran = st.builds(
    ScannerRan,
    findings=st.lists(_finding, max_size=16),
)
_scanner_skipped = st.builds(
    ScannerSkipped,
    reason=st.sampled_from(["tool_missing", "tool_unhealthy", "upstream_unavailable"]),
)
_scanner_failed = st.builds(
    ScannerFailed,
    exit_code=st.integers(min_value=0, max_value=255),
    stderr_tail=st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        min_size=0,
        max_size=STDERR_TAIL_CAP_BYTES,
    ),
)
_scanner_outcomes: st.SearchStrategy[ScannerOutcome] = st.one_of(
    _scanner_ran, _scanner_skipped, _scanner_failed
)
_scanner_adapter: TypeAdapter[ScannerOutcome] = TypeAdapter(ScannerOutcome)


# ---------------------------------------------------------------------------
# Strategies — ScenarioResult variants.
# ---------------------------------------------------------------------------

_trace_completed = st.builds(
    TraceScenarioCompleted,
    scenario_name=_scenario_name,
    artifact_uri=_printable_ascii.filter(lambda s: len(s) >= 1).map(Path),
    wall_clock_ms=st.integers(min_value=0, max_value=10**7),
    syscalls_observed=st.integers(min_value=0, max_value=10**7),
    shared_libs_count=st.integers(min_value=0, max_value=1000),
)

_failure_reason = st.one_of(
    st.builds(StraceUnavailable),
    st.builds(
        DockerBuildFailed,
        stderr_tail=st.text(
            alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            min_size=0,
            max_size=STDERR_TAIL_CAP_BYTES,
        ),
    ),
    st.builds(ScenarioTimeout, elapsed_ms=st.integers(min_value=0, max_value=10**7)),
    st.builds(
        ImageDigestUnresolved,
        ref=_printable_ascii.filter(lambda s: len(s) >= 1),
    ),
)
_skip_reason = st.one_of(st.builds(NoDockerfile), st.builds(ImageBuildUnavailable))

_trace_failed = st.builds(TraceScenarioFailed, scenario_name=_scenario_name, reason=_failure_reason)
_trace_skipped = st.builds(TraceScenarioSkipped, scenario_name=_scenario_name, reason=_skip_reason)
_scenario_results: st.SearchStrategy[ScenarioResult] = st.one_of(
    _trace_completed, _trace_failed, _trace_skipped
)
_scenario_adapter: TypeAdapter[ScenarioResult] = TypeAdapter(ScenarioResult)


# ---------------------------------------------------------------------------
# Properties.
# ---------------------------------------------------------------------------


@given(value=_scanner_outcomes)
@settings(max_examples=200, deadline=None, database=None)  # S7-05 AC-11, AC-35
def test_scanner_outcome_roundtrips_identity(value: ScannerOutcome) -> None:
    decoded = _scanner_adapter.validate_json(_scanner_adapter.dump_json(value))
    assert decoded == value
    assert type(decoded) is type(value)
    if isinstance(value, ScannerRan):
        assert isinstance(decoded, ScannerRan)
        assert [type(f) for f in decoded.findings] == [type(f) for f in value.findings]


@given(value=_scenario_results)
@settings(max_examples=200, deadline=None, database=None)  # S7-05 AC-11, AC-35
def test_scenario_result_roundtrips_identity(value: ScenarioResult) -> None:
    decoded = _scenario_adapter.validate_json(_scenario_adapter.dump_json(value))
    assert decoded == value
    assert type(decoded) is type(value)
    if isinstance(value, TraceScenarioFailed):
        assert isinstance(decoded, TraceScenarioFailed)
        assert type(decoded.reason) is type(value.reason)
    if isinstance(value, TraceScenarioSkipped):
        assert isinstance(decoded, TraceScenarioSkipped)
        assert type(decoded.reason) is type(value.reason)
