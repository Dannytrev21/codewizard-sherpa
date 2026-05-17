"""Unit tests for :mod:`codegenie.probes.layer_c.runtime_trace` (S5-02).

Covers the probe's class-attribute pins, declared inputs, scenarios loader,
sequential-execution invariant, macOS short-circuit, hardening flags,
timeout constants, image-digest unresolved paths, and slice schema. The
pure helpers ( ``_image_ref_for_digest`` / ``_build_*_argv`` /
``_parse_strace_lines`` / ``_derive_trace_coverage_confidence`` /
``_aggregate_scenarios`` / ``_envelope_confidence`` ) live in their own
test files under ``tests/unit/probes/layer_c/`` so each is testable
without subprocess mocking.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import sys
from pathlib import Path
from typing import Any, get_args

import pytest

from codegenie.exec import ProcessResult
from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.layer_c import runtime_trace as rt
from codegenie.probes.layer_c.runtime_trace import (
    _AGGREGATE_TIMEOUT_S,
    _DEFAULT_SCENARIO_NAMES,
    _DEFAULT_SCENARIOS,
    _EXPECTED_SLICE_KEYS,
    _HARDENING_FLAGS,
    _IMAGE_REF_PREFIX,
    _PER_SCENARIO_TIMEOUT_S,
    _SCENARIO_TASK_NAME_PREFIX,
    RuntimeTraceProbe,
    ScenarioSpec,
)
from codegenie.probes.registry import default_registry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ctx(
    tmp_path: Path,
    image_digest_resolver: Any = None,
) -> ProbeContext:
    ctx = ProbeContext(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "out",
        workspace=tmp_path / "ws",
        logger=logging.getLogger("test"),
        config={},
        image_digest_resolver=image_digest_resolver,
    )
    ctx.cache_dir.mkdir(parents=True, exist_ok=True)
    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    ctx.workspace.mkdir(parents=True, exist_ok=True)
    return ctx


def _make_snapshot(repo_root: Path) -> RepoSnapshot:
    (repo_root / "Dockerfile").write_text("FROM scratch\n")
    return RepoSnapshot(
        root=repo_root,
        git_commit=None,
        detected_languages={},
        config={},
    )


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture()
def snapshot(repo_root: Path) -> RepoSnapshot:
    return _make_snapshot(repo_root)


@pytest.fixture()
def ctx(tmp_path: Path) -> ProbeContext:
    return _make_ctx(tmp_path / "ctx")


# ---------------------------------------------------------------------------
# AC-1 / AC-3 — registry registration + class attributes
# ---------------------------------------------------------------------------


def test_runtime_trace_registered_heavy_runs_last_false() -> None:
    """The probe is registered with heaviness="heavy" and runs_last=False."""
    matches = [e for e in default_registry.sorted_for_dispatch() if e.cls.name == "runtime_trace"]
    assert len(matches) == 1
    entry = matches[0]
    assert entry.heaviness == "heavy"
    assert entry.runs_last is False


def test_runtime_trace_class_attributes_pinned() -> None:
    """Pin the literal class-attribute shape so future drift is caught."""
    assert RuntimeTraceProbe.name == "runtime_trace"
    assert RuntimeTraceProbe.layer == "C"
    assert RuntimeTraceProbe.tier == "base"
    assert RuntimeTraceProbe.applies_to_tasks == ["*"]
    assert RuntimeTraceProbe.applies_to_languages == ["*"]
    assert RuntimeTraceProbe.requires == []
    assert RuntimeTraceProbe.timeout_seconds == 300
    assert RuntimeTraceProbe.cache_strategy == "content"


def test_declared_inputs_literal_three_entries() -> None:
    """Exact three-entry list including the literal special-token string."""
    assert RuntimeTraceProbe.declared_inputs == [
        "Dockerfile",
        ".codegenie/scenarios.yaml",
        "image-digest:<resolved>",
    ]


# ---------------------------------------------------------------------------
# Hardening flags
# ---------------------------------------------------------------------------


def test_hardening_flags_constant_pinned() -> None:
    assert _HARDENING_FLAGS == (
        "--network=none",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
    )


# ---------------------------------------------------------------------------
# Timeout constants
# ---------------------------------------------------------------------------


def test_per_scenario_timeout_120s_constant() -> None:
    assert _PER_SCENARIO_TIMEOUT_S == 120


def test_aggregate_timeout_600s_constant() -> None:
    assert _AGGREGATE_TIMEOUT_S == 600


# ---------------------------------------------------------------------------
# Source-scan tests (Rule 11 — match codebase precedent + L22)
# ---------------------------------------------------------------------------


def test_runtime_trace_module_routes_through_run_allowlisted() -> None:
    source = Path(rt.__file__).read_text(encoding="utf-8")
    # Allowlisted entry point is present at least once.
    assert "run_allowlisted" in source
    # The Layer B/G wrapper is not used by Layer C (02-ADR-0001).
    assert "run_external_cli" not in source


def test_runtime_trace_module_has_no_pydantic_validation_bypass_ctor() -> None:
    """The validation-bypass Pydantic ctor must not appear in the module —
    the forbidden-patterns hook is the structural defense; this source-scan
    test backstops it. Module docstring describes the ban without spelling
    the banned token (per L22).
    """
    source = Path(rt.__file__).read_text(encoding="utf-8")
    assert "model_construct" not in source


def test_default_scenarios_uniqueness_in_source() -> None:
    """``_DEFAULT_SCENARIOS`` appears in exactly one source file."""
    root = Path(rt.__file__).resolve().parents[3] / "codegenie"
    hits = [p for p in root.rglob("*.py") if "_DEFAULT_SCENARIOS" in p.read_text()]
    assert len(hits) == 1
    assert hits[0].name == "runtime_trace.py"


def test_default_scenario_names_unchanged() -> None:
    assert _DEFAULT_SCENARIO_NAMES == (
        "startup",
        "smoke_test",
        "healthcheck",
        "shutdown",
        "error_path",
    )


def test_default_scenarios_carry_five_specs() -> None:
    assert len(_DEFAULT_SCENARIOS) == 5
    for spec in _DEFAULT_SCENARIOS:
        assert isinstance(spec, ScenarioSpec)
        assert spec.name in _DEFAULT_SCENARIO_NAMES


# ---------------------------------------------------------------------------
# Envelope `confidence` contract preservation
# ---------------------------------------------------------------------------


def test_envelope_confidence_literal_unchanged() -> None:
    """``Probe.confidence`` (annotated on :class:`ProbeOutput`) is the frozen
    tri-state."""
    anno = inspect.get_annotations(ProbeOutput, eval_str=True)["confidence"]
    assert get_args(anno) == ("high", "medium", "low")


# ---------------------------------------------------------------------------
# applies() — only when Dockerfile present
# ---------------------------------------------------------------------------


def test_applies_returns_false_without_dockerfile(tmp_path: Path) -> None:
    repo = tmp_path / "no-docker"
    repo.mkdir()
    snap = RepoSnapshot(root=repo, git_commit=None, detected_languages={}, config={})
    probe = RuntimeTraceProbe()
    assert probe.applies(snap, None) is False  # type: ignore[arg-type]


def test_applies_returns_true_with_dockerfile(repo_root: Path) -> None:
    (repo_root / "Dockerfile").write_text("FROM scratch\n")
    snap = RepoSnapshot(root=repo_root, git_commit=None, detected_languages={}, config={})
    probe = RuntimeTraceProbe()
    assert probe.applies(snap, None) is True  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Image-digest unresolved paths (all → envelope confidence="low" +
# slice trace_coverage_confidence="unavailable" + Failed scenarios)
# ---------------------------------------------------------------------------


def _assert_failed_image_digest_unresolved(output: ProbeOutput) -> None:
    """Shared assertion shape for the three unresolved paths."""
    assert output.confidence == "low"
    slice_dict = output.schema_slice
    assert slice_dict["trace_coverage_confidence"] == "unavailable"
    assert slice_dict["built_image_digest"] is None
    assert slice_dict["last_traced_image_digest"] is None
    assert slice_dict["scenarios_run"] == []
    # Five failure entries — one per default scenario name.
    assert sorted(slice_dict["scenarios_failed"]) == sorted(_DEFAULT_SCENARIO_NAMES)


def test_image_digest_resolver_unbound_produces_envelope_low(
    snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    """``ctx.image_digest_resolver is None`` short-circuits to envelope=low."""
    probe = RuntimeTraceProbe()
    output = asyncio.run(probe.run(snapshot, ctx))
    _assert_failed_image_digest_unresolved(output)


def test_image_digest_resolver_returns_none(snapshot: RepoSnapshot, tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path / "ctx", image_digest_resolver=lambda _root: None)
    probe = RuntimeTraceProbe()
    output = asyncio.run(probe.run(snapshot, ctx))
    _assert_failed_image_digest_unresolved(output)


def test_image_digest_resolver_raises_translated(snapshot: RepoSnapshot, tmp_path: Path) -> None:
    def boom(_root: Path) -> str:
        raise RuntimeError("boom")

    ctx = _make_ctx(tmp_path / "ctx", image_digest_resolver=boom)
    probe = RuntimeTraceProbe()
    output = asyncio.run(probe.run(snapshot, ctx))
    _assert_failed_image_digest_unresolved(output)


# ---------------------------------------------------------------------------
# macOS / non-Linux path — every scenario is StraceUnavailable
# ---------------------------------------------------------------------------


def test_non_linux_short_circuits_strace_unavailable(
    snapshot: RepoSnapshot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On any non-Linux platform, every scenario emits a typed
    :class:`StraceUnavailable` failure WITHOUT invoking subprocess."""
    monkeypatch.setattr(sys, "platform", "darwin")

    spawned: list[list[str]] = []

    async def _spy(*args: Any, **kwargs: Any) -> ProcessResult:
        # If this ever fires on the macOS path, the probe leaked subprocess.
        spawned.append(args[0] if args else [])
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(rt, "run_allowlisted", _spy)
    ctx = _make_ctx(tmp_path / "ctx", image_digest_resolver=lambda _root: "sha256:" + "a" * 40)
    probe = RuntimeTraceProbe()
    output = asyncio.run(probe.run(snapshot, ctx))

    assert output.confidence == "low"
    assert output.schema_slice["trace_coverage_confidence"] == "unavailable"
    assert output.schema_slice["built_image_digest"] is None
    assert spawned == []


# ---------------------------------------------------------------------------
# Slice schema is the complete observable surface
# ---------------------------------------------------------------------------


def test_slice_schema_keys_complete_for_macos_path(
    snapshot: RepoSnapshot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    ctx = _make_ctx(tmp_path / "ctx", image_digest_resolver=lambda _root: "sha256:" + "b" * 40)
    output = asyncio.run(RuntimeTraceProbe().run(snapshot, ctx))
    assert set(output.schema_slice.keys()) == set(_EXPECTED_SLICE_KEYS)


def test_slice_schema_keys_complete_for_image_digest_unresolved(
    snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    output = asyncio.run(RuntimeTraceProbe().run(snapshot, ctx))
    assert set(output.schema_slice.keys()) == set(_EXPECTED_SLICE_KEYS)


# ---------------------------------------------------------------------------
# scenarios.yaml — defaults vs operator-provided
# ---------------------------------------------------------------------------


def test_load_scenarios_falls_back_to_defaults(
    snapshot: RepoSnapshot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    ctx = _make_ctx(tmp_path / "ctx", image_digest_resolver=lambda _root: "sha256:" + "c" * 40)
    output = asyncio.run(RuntimeTraceProbe().run(snapshot, ctx))
    assert sorted(output.schema_slice["scenarios_failed"]) == sorted(_DEFAULT_SCENARIO_NAMES)


def test_seven_scenario_yaml_extends_without_source_edit(
    snapshot: RepoSnapshot,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding a 6th + 7th scenario via YAML requires zero source edit."""
    fixture_root = Path(__file__).resolve().parents[3]
    yaml_src = (fixture_root / "fixtures" / "scenarios" / "seven_scenarios.yaml").read_text()
    (repo_root / ".codegenie").mkdir()
    (repo_root / ".codegenie" / "scenarios.yaml").write_text(yaml_src)

    monkeypatch.setattr(sys, "platform", "darwin")
    ctx = _make_ctx(tmp_path / "ctx", image_digest_resolver=lambda _root: "sha256:" + "d" * 40)
    output = asyncio.run(RuntimeTraceProbe().run(snapshot, ctx))

    expected_names = {
        "startup",
        "smoke_test",
        "healthcheck",
        "shutdown",
        "error_path",
        "db_migrate",
        "worker_drain",
    }
    assert set(output.schema_slice["scenarios_failed"]) == expected_names


def test_malformed_scenarios_yaml_routes_to_typed_failure(
    snapshot: RepoSnapshot,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    (repo_root / ".codegenie").mkdir()
    (repo_root / ".codegenie" / "scenarios.yaml").write_text(
        "scenarios:\n  - 123\n  - not_a_mapping\n"
    )
    ctx = _make_ctx(tmp_path / "ctx", image_digest_resolver=lambda _root: "sha256:" + "e" * 40)
    output = asyncio.run(RuntimeTraceProbe().run(snapshot, ctx))
    assert output.confidence == "low"
    assert output.schema_slice["trace_coverage_confidence"] == "unavailable"


# ---------------------------------------------------------------------------
# Image-ref prefix
# ---------------------------------------------------------------------------


def test_image_ref_prefix_constant() -> None:
    assert _IMAGE_REF_PREFIX == "codegenie-trace:"


# ---------------------------------------------------------------------------
# Task-name prefix — used by sequential-execution observer
# ---------------------------------------------------------------------------


def test_scenario_task_name_prefix_constant() -> None:
    assert _SCENARIO_TASK_NAME_PREFIX == "runtime_trace_scenario_"
