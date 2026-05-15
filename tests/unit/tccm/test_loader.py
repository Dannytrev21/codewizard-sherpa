"""Unit tests for ``codegenie.tccm.loader`` — story 02 S1-04.

Covers AC-4 (Result variants), AC-5 (chokepoint), AC-8 (unknown_query_primitive
prefix), AC-9 (Result type), AC-20 (parse-error parametrization), AC-21
(confidence_floor variants), AC-22 (audit log), AC-23 (chokepoint AST scan).
"""

from __future__ import annotations

import ast
import pathlib
import textwrap
from pathlib import Path

import pytest
from structlog.testing import capture_logs

import codegenie.tccm.loader as loader_mod
from codegenie.adapters import Degraded, Trusted, Unavailable
from codegenie.errors import (
    DepthCapExceeded,
    MalformedYAMLError,
    SizeCapExceeded,
    TCCMLoadError,
)
from codegenie.result import Err, Ok
from codegenie.tccm import (
    TCCM,
    ConsumersOf,
    ProducersOf,
    RefsTo,
    ReverseLookup,
    TCCMLoader,
)
from codegenie.tccm import TestsExercising as ExerciseTestsQuery
from codegenie.types.identifiers import ProbeId, SkillId, TaskClassId

VALID_TCCM_YAML = textwrap.dedent(
    """\
    schema_version: "1"
    task_class: "index-health-self-check"
    required_probes: ["index_health", "scip_index"]
    required_skills: ["scip.maintenance"]
    derived_queries:
      - compute: "consumers_of"
        pkg: "@org/payments"
      - compute: "producers_of"
        pkg: "@org/payments"
      - compute: "reverse_lookup"
        module: "src/payments/processor.ts"
      - compute: "refs_to"
        symbol: "PaymentProcessor.charge"
      - compute: "tests_exercising"
        symbol: "PaymentProcessor.charge"
    confidence_floor:
      kind: "trusted"
    """
)


def _write(tmp_path: Path, body: str, name: str = "tccm.yaml") -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


# AC-4, AC-5, AC-9 — happy path returns Ok(value=TCCM).
def test_load_happy_path(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID_TCCM_YAML)
    result = TCCMLoader().load(path)
    assert isinstance(result, Ok), repr(result)
    assert result.is_ok()
    tccm = result.unwrap()
    assert isinstance(tccm, TCCM)
    assert tccm.schema_version == "1"
    assert tccm.task_class == TaskClassId("index-health-self-check")
    assert SkillId("scip.maintenance") in tccm.required_skills
    assert ProbeId("index_health") in tccm.required_probes
    assert len(tccm.derived_queries) == 5
    assert {type(q) for q in tccm.derived_queries} == {
        ConsumersOf,
        ProducersOf,
        ReverseLookup,
        RefsTo,
        ExerciseTestsQuery,
    }


# AC-8 — unknown compute: → exact "unknown_query_primitive:" prefix pin.
def test_load_unknown_compute_prefix_pin(tmp_path: Path) -> None:
    bad = VALID_TCCM_YAML.replace('compute: "consumers_of"', 'compute: "implementations_of"')
    result = TCCMLoader().load(_write(tmp_path, bad))
    assert isinstance(result, Err)
    err = result.unwrap_err()
    assert isinstance(err, TCCMLoadError)
    assert err.args[0].startswith("unknown_query_primitive:")


# AC-4 — schema violation: positional prefix pin.
def test_load_schema_violation_prefix_pin(tmp_path: Path) -> None:
    bad = 'schema_version: "1"\n'  # missing every other required field
    result = TCCMLoader().load(_write(tmp_path, bad))
    assert isinstance(result, Err)
    assert result.unwrap_err().args[0].startswith("schema:")


# AC-20 — parse-error parametrized over all three safe_yaml markers.
@pytest.mark.parametrize(
    "exc_cls",
    [MalformedYAMLError, SizeCapExceeded, DepthCapExceeded],
    ids=["malformed", "size_cap", "depth_cap"],
)
def test_load_parse_errors_routed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exc_cls: type[Exception],
) -> None:
    from codegenie.parsers import safe_yaml as sy

    def boom(*args: object, **kwargs: object) -> object:
        raise exc_cls("synthetic")

    monkeypatch.setattr(sy, "load", boom)
    path = _write(tmp_path, VALID_TCCM_YAML)
    result = TCCMLoader().load(path)
    assert isinstance(result, Err)
    assert result.unwrap_err().args[0].startswith("parse:")


# AC-5 — chokepoint: monkeypatch positive arm (loader routes through safe_yaml.load
# and passes the documented max_bytes floor).
def test_load_routes_through_safe_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from codegenie.parsers import safe_yaml as sy

    seen: list[tuple[Path, int]] = []
    original = sy.load

    def spy(path: Path, *, max_bytes: int, max_depth: int = 64) -> object:
        seen.append((path, max_bytes))
        return original(path, max_bytes=max_bytes, max_depth=max_depth)

    monkeypatch.setattr(sy, "load", spy)
    path = _write(tmp_path, VALID_TCCM_YAML)
    TCCMLoader().load(path)
    assert len(seen) == 1
    assert seen[0][0] == path
    assert seen[0][1] >= 10_240  # at least the documented "< 10 KB" floor


# AC-23 — chokepoint AST source-scan (durable against import-shadowing).
def test_loader_module_does_not_bypass_safe_yaml() -> None:
    tree = ast.parse(pathlib.Path(loader_mod.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "yaml", "loader.py must not import yaml directly (AC-23)"
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "yaml", "loader.py must not import from yaml directly (AC-23)"
            if node.module == "codegenie.parsers.safe_yaml":
                names = {alias.name for alias in node.names}
                assert "load_all" not in names, (
                    "loader.py must use safe_yaml.load, not safe_yaml.load_all (AC-23)"
                )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "read_text":
                pytest.fail("loader.py must not call Path.read_text (AC-23)")
            if isinstance(func, ast.Name) and func.id == "open":
                pytest.fail("loader.py must not call builtin open() (AC-23)")


# AC-21 — confidence_floor accepts every AdapterConfidence variant.
@pytest.mark.parametrize(
    "floor_yaml, expected_cls",
    [
        ('confidence_floor:\n  kind: "trusted"', Trusted),
        ('confidence_floor:\n  kind: "degraded"\n  reason: "index_stale"', Degraded),
        ('confidence_floor:\n  kind: "unavailable"\n  reason: "tool_missing"', Unavailable),
    ],
    ids=["trusted", "degraded", "unavailable"],
)
def test_confidence_floor_accepts_all_variants(
    tmp_path: Path, floor_yaml: str, expected_cls: type
) -> None:
    body = VALID_TCCM_YAML.replace('confidence_floor:\n  kind: "trusted"', floor_yaml)
    result = TCCMLoader().load(_write(tmp_path, body))
    assert isinstance(result, Ok), repr(result)
    assert isinstance(result.unwrap().confidence_floor, expected_cls)


# AC-22 — audit log emission on Ok and Err.
def test_loader_emits_audit_log_on_ok(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID_TCCM_YAML)
    with capture_logs() as caplog:
        TCCMLoader().load(path)
    events = [e for e in caplog if e["event"] in ("tccm.load.ok", "tccm.load.err")]
    assert len(events) == 1
    e = events[0]
    assert e["event"] == "tccm.load.ok"
    assert e["path"] == str(path)
    assert e["derived_queries_count"] == 5


def test_loader_emits_audit_log_on_unknown_primitive(tmp_path: Path) -> None:
    bad = VALID_TCCM_YAML.replace('compute: "consumers_of"', 'compute: "implementations_of"')
    path = _write(tmp_path, bad)
    with capture_logs() as caplog:
        TCCMLoader().load(path)
    err_events = [e for e in caplog if e["event"] == "tccm.load.err"]
    assert len(err_events) == 1
    assert err_events[0]["reason"] == "unknown_query_primitive"
    assert err_events[0]["path"] == str(path)


def test_loader_emits_audit_log_on_schema_err(tmp_path: Path) -> None:
    bad = 'schema_version: "1"\n'
    path = _write(tmp_path, bad)
    with capture_logs() as caplog:
        TCCMLoader().load(path)
    err_events = [e for e in caplog if e["event"] == "tccm.load.err"]
    assert len(err_events) == 1
    assert err_events[0]["reason"] == "schema"


def test_loader_emits_audit_log_on_parse_err(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codegenie.parsers import safe_yaml as sy

    def boom(*args: object, **kwargs: object) -> object:
        raise MalformedYAMLError("synthetic")

    monkeypatch.setattr(sy, "load", boom)
    path = _write(tmp_path, VALID_TCCM_YAML)
    with capture_logs() as caplog:
        TCCMLoader().load(path)
    err_events = [e for e in caplog if e["event"] == "tccm.load.err"]
    assert len(err_events) == 1
    assert err_events[0]["reason"] == "parse"


# AC-22 (negative arm) — audit-log field allowlist: no YAML body, no
# validation-error detail leaked as separate structlog kwargs.
def test_audit_log_fields_are_allowlisted(tmp_path: Path) -> None:
    bad = VALID_TCCM_YAML.replace('compute: "consumers_of"', 'compute: "implementations_of"')
    path = _write(tmp_path, bad)
    with capture_logs() as caplog:
        TCCMLoader().load(path)
    events = [e for e in caplog if e["event"].startswith("tccm.load.")]
    assert len(events) == 1
    allowed_keys = {"event", "log_level", "path", "reason", "derived_queries_count"}
    for k in events[0]:
        assert k in allowed_keys, (
            f"audit log emitted forbidden key {k!r}; allowlist is {allowed_keys}"
        )
