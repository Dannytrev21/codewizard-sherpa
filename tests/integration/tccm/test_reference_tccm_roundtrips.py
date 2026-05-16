"""Phase-2 in-repo proof that the four adapter ``Protocol``s are invocable
against every ``DerivedQuery`` variant declared by S1-04.

Closes Gap 1 from ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
§"Gap analysis": Protocols defined, never called in Phase 2. The mock
dispatcher below is the in-Phase-2 anchor; the cross-phase trip-wire is
``tests/integration/adapters/test_phase3_handoff_smoke.py`` (lands skipped
in S7-04).

The ``_dispatch`` parameters are typed against the *Protocols* (not the
mocks); under ``mypy --strict`` the call sites are checked against the
Protocol signatures — that is the load-bearing signature-drift anchor.
"""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import assert_never

import pytest
from pydantic import ValidationError

from codegenie.adapters.confidence import (
    AdapterConfidence,
    Degraded,
    Trusted,
    Unavailable,
)

# Aliases on import — ``TestInventoryAdapter`` / ``TestsExercising`` / ``TestId``
# collide with pytest's ``Test*`` collector (mirrors tests/unit/adapters and
# tests/unit/tccm conventions).
from codegenie.adapters.protocols import (
    DepGraphAdapter,
    ImportGraphAdapter,
    Occurrence,
    ScipAdapter,
)
from codegenie.adapters.protocols import TestId as InventoryTestId
from codegenie.adapters.protocols import TestInventoryAdapter as InventoryAdapter
from codegenie.errors import TCCMLoadError
from codegenie.parsers import safe_yaml
from codegenie.result import Ok
from codegenie.tccm.loader import TCCMLoader
from codegenie.tccm.model import TCCM
from codegenie.tccm.queries import (
    ConsumersOf,
    DerivedQuery,
    ProducersOf,
    RefsTo,
    ReverseLookup,
)
from codegenie.tccm.queries import TestsExercising as ExerciseTestsQuery
from codegenie.types.identifiers import ProbeId, SkillId, TaskClassId

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_DIR = REPO_ROOT / "docs/phases/02-context-gather-layers-b-g/_reference-tccm"
REFERENCE_PATH = REFERENCE_DIR / "tccm.yaml"
INVALID_DIR = REFERENCE_DIR / "_invalid"
FLOORS_DIR = REFERENCE_DIR / "_floors"


class _ProtocolMethod(StrEnum):
    """Typed enumeration of the nine Phase-2 Protocol methods.

    Recorder and assertions both consume this — typo discipline. Adding a
    Protocol method requires adding one enum value; the test then
    auto-iterates over the new surface.
    """

    DEP_CONSUMERS = "DepGraphAdapter.consumers"
    DEP_PRODUCERS = "DepGraphAdapter.producers"
    DEP_CONFIDENCE = "DepGraphAdapter.confidence"
    IMP_REVERSE_LOOKUP = "ImportGraphAdapter.reverse_lookup"
    IMP_CONFIDENCE = "ImportGraphAdapter.confidence"
    SCIP_REFS = "ScipAdapter.refs"
    SCIP_CONFIDENCE = "ScipAdapter.confidence"
    TESTS_EXERCISING = "TestInventoryAdapter.tests_exercising"
    TESTS_CONFIDENCE = "TestInventoryAdapter.confidence"


# Duplication across the four mocks is intentional: these are deleted when
# Phase 8 ships real adapters. A ``_RecordingAdapter`` mixin would couple
# four one-shot test fixtures to a micro-abstraction with one consumer.


class _MockDepGraph:
    def __init__(self) -> None:
        self.calls: list[_ProtocolMethod] = []

    def consumers(self, pkg: str) -> list[str]:
        self.calls.append(_ProtocolMethod.DEP_CONSUMERS)
        return ["a", "b"]

    def producers(self, pkg: str) -> list[str]:
        self.calls.append(_ProtocolMethod.DEP_PRODUCERS)
        return ["c"]

    def confidence(self) -> AdapterConfidence:
        self.calls.append(_ProtocolMethod.DEP_CONFIDENCE)
        return Trusted()


class _MockImportGraph:
    def __init__(self) -> None:
        self.calls: list[_ProtocolMethod] = []

    def reverse_lookup(self, module: str) -> list[str]:
        self.calls.append(_ProtocolMethod.IMP_REVERSE_LOOKUP)
        return ["x.py"]

    def confidence(self) -> AdapterConfidence:
        self.calls.append(_ProtocolMethod.IMP_CONFIDENCE)
        return Trusted()


class _MockScip:
    def __init__(self) -> None:
        self.calls: list[_ProtocolMethod] = []

    def refs(self, symbol: str) -> list[Occurrence]:
        self.calls.append(_ProtocolMethod.SCIP_REFS)
        return []

    def confidence(self) -> AdapterConfidence:
        self.calls.append(_ProtocolMethod.SCIP_CONFIDENCE)
        return Degraded(reason="self_check")


class _MockTestInventory:
    def __init__(self) -> None:
        self.calls: list[_ProtocolMethod] = []

    def tests_exercising(self, symbol: str) -> list[InventoryTestId]:
        self.calls.append(_ProtocolMethod.TESTS_EXERCISING)
        return []

    def confidence(self) -> AdapterConfidence:
        self.calls.append(_ProtocolMethod.TESTS_CONFIDENCE)
        return Trusted()


def _dispatch(
    query: DerivedQuery,
    *,
    dep: DepGraphAdapter,
    imp: ImportGraphAdapter,
    scip: ScipAdapter,
    tests: InventoryAdapter,
) -> None:
    """Route a ``DerivedQuery`` to the appropriate Protocol method.

    Parameter types are the *Protocols*, not the concrete mocks: under
    ``mypy --strict`` the call sites below are checked against the
    Protocol signatures — that is the Gap-1 signature-drift anchor.
    """
    match query:
        case ConsumersOf(pkg=p):
            dep.consumers(p)
        case ProducersOf(pkg=p):
            dep.producers(p)
        case ReverseLookup(module=m):
            imp.reverse_lookup(m)
        case RefsTo(symbol=s):
            scip.refs(s)
        case ExerciseTestsQuery(symbol=s):
            tests.tests_exercising(s)
        case _ as unreachable:
            assert_never(unreachable)


def _expected_tccm() -> TCCM:
    return TCCM(
        schema_version="1",
        task_class=TaskClassId("index-health-self-check"),
        required_probes=[
            ProbeId("b2_index_health"),
            ProbeId("b1_scip"),
            ProbeId("b3_tree_sitter_imports"),
        ],
        required_skills=[SkillId("diagnose-stale-scip")],
        confidence_floor=Degraded(reason="stale_scip_acceptable_for_self_check"),
        derived_queries=[
            ConsumersOf(pkg="@codegenie/scip"),
            ProducersOf(pkg="@codegenie/scip"),
            ReverseLookup(module="codegenie/probes/layer_b/index_health.py"),
            RefsTo(symbol="codegenie/indices/freshness.IndexFreshness"),
            ExerciseTestsQuery(symbol="codegenie/probes/layer_b/index_health.py"),
        ],
    )


# ---- AC-1, AC-8 (location discipline) --------------------------------------


def test_reference_tccm_lives_under_docs_not_under_plugins() -> None:
    assert REFERENCE_PATH.exists(), f"missing fixture: {REFERENCE_PATH}"
    assert str(REFERENCE_PATH).startswith(str(REPO_ROOT / "docs"))
    plugins_root = REPO_ROOT / "plugins"
    if plugins_root.exists():
        stray = list(plugins_root.rglob("tccm.yaml"))
        assert stray == [], (
            "02-ADR-0007 violation: reference TCCMs MUST live under docs/, "
            f"not plugins/. Found: {stray}"
        )


# ---- AC-9 (fixture-validity smoke) -----------------------------------------


def test_reference_tccm_is_safe_yaml_parseable() -> None:
    data = safe_yaml.load(REFERENCE_PATH, max_bytes=64 << 10)
    assert isinstance(data, dict)
    assert data["schema_version"] == "1"


# ---- AC-3 (round-trip equality) --------------------------------------------


def test_reference_tccm_loads_and_equals_expected_pydantic_instance() -> None:
    result = TCCMLoader().load(REFERENCE_PATH)
    assert result.is_ok(), f"TCCMLoader failed: {result}"
    assert isinstance(result, Ok)
    assert result.unwrap() == _expected_tccm()


# ---- AC-2 (Counter-style multiset) -----------------------------------------


def test_reference_tccm_exercises_every_derived_query_variant() -> None:
    tccm = TCCMLoader().load(REFERENCE_PATH).unwrap()
    assert len(tccm.derived_queries) == 5
    counts = Counter(type(q).__name__ for q in tccm.derived_queries)
    assert counts == Counter(
        {
            "ConsumersOf": 1,
            "ProducersOf": 1,
            "ReverseLookup": 1,
            "RefsTo": 1,
            "TestsExercising": 1,
        }
    )


# ---- AC-3b (every confidence_floor variant round-trips) --------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("trusted.yaml", Trusted()),
        ("degraded.yaml", Degraded(reason="self_check_acceptable")),
        ("unavailable.yaml", Unavailable(reason="scip_offline")),
    ],
)
def test_confidence_floor_round_trips_for_every_variant(
    filename: str, expected: AdapterConfidence
) -> None:
    result = TCCMLoader().load(FLOORS_DIR / filename)
    assert result.is_ok(), f"{filename}: {result}"
    assert result.unwrap().confidence_floor == expected


# ---- AC-3c (frozen + extra=forbid) -----------------------------------------


def test_loaded_tccm_is_frozen_and_forbids_extras() -> None:
    tccm = TCCMLoader().load(REFERENCE_PATH).unwrap()
    with pytest.raises(ValidationError):
        tccm.task_class = TaskClassId("x")
    result = TCCMLoader().load(INVALID_DIR / "extra_top_level_key.yaml")
    assert result.is_err()
    assert result.unwrap_err().args[0].startswith("schema:")


# ---- AC-3d (per-variant JSON round-trip) -----------------------------------


def test_every_derived_query_round_trips_through_json() -> None:
    tccm = TCCMLoader().load(REFERENCE_PATH).unwrap()
    for q in tccm.derived_queries:
        same = type(q).model_validate_json(q.model_dump_json())
        assert q == same, f"JSON round-trip drift on {type(q).__name__}"


# ---- AC-4, AC-5 (Gap-1 closer — invocation) --------------------------------


def test_mock_dispatcher_invokes_every_protocol_method_at_least_once() -> None:
    tccm = TCCMLoader().load(REFERENCE_PATH).unwrap()
    dep = _MockDepGraph()
    imp = _MockImportGraph()
    scip = _MockScip()
    tests = _MockTestInventory()

    # AC-5 — structural Protocol conformance via runtime_checkable.
    assert isinstance(dep, DepGraphAdapter)
    assert isinstance(imp, ImportGraphAdapter)
    assert isinstance(scip, ScipAdapter)
    assert isinstance(tests, InventoryAdapter)

    for query in tccm.derived_queries:
        _dispatch(query, dep=dep, imp=imp, scip=scip, tests=tests)
    for adapter in (dep, imp, scip, tests):
        adapter.confidence()

    all_calls: set[_ProtocolMethod] = (
        set(dep.calls) | set(imp.calls) | set(scip.calls) | set(tests.calls)
    )
    missing = set(_ProtocolMethod) - all_calls
    assert not missing, f"never invoked: {sorted(m.value for m in missing)}"


# ---- AC-6 (assert_never fires on imposter — narrow exception) --------------


def test_dispatcher_match_is_exhaustive_assert_never_fires_on_smuggled_variant() -> None:
    class _Imposter:
        pass

    with pytest.raises(AssertionError):
        _dispatch(
            _Imposter(),  # type: ignore[arg-type]
            dep=_MockDepGraph(),
            imp=_MockImportGraph(),
            scip=_MockScip(),
            tests=_MockTestInventory(),
        )


# ---- AC-7 (unknown_query_primitive: prefix on args[0]) ---------------------


def test_unknown_compute_primitive_returns_typed_err_prefix() -> None:
    result = TCCMLoader().load(INVALID_DIR / "unknown_compute.yaml")
    assert result.is_err(), f"expected Err, got {result}"
    err = result.unwrap_err()
    assert isinstance(err, TCCMLoadError)
    assert err.args[0].startswith("unknown_query_primitive:"), err.args


# ---- AC-7b (LoaderReason taxonomy via sibling fixtures) --------------------


@pytest.mark.parametrize(
    ("filename", "expected_prefix"),
    [
        ("malformed.yaml", "parse:"),
        ("missing_required_probes.yaml", "schema:"),
        ("extra_top_level_key.yaml", "schema:"),
        ("unknown_compute.yaml", "unknown_query_primitive:"),
    ],
)
def test_invalid_fixtures_cover_loader_reason_taxonomy(filename: str, expected_prefix: str) -> None:
    result = TCCMLoader().load(INVALID_DIR / filename)
    assert result.is_err(), f"{filename}: expected Err, got {result}"
    err = result.unwrap_err()
    assert isinstance(err, TCCMLoadError)
    assert err.args[0].startswith(expected_prefix), (
        f"{filename}: expected '{expected_prefix}…' got '{err.args[0]}'"
    )
