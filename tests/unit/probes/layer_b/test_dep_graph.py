"""S4-05 — ``DepGraphProbe``: registry-dispatched dep-graph kernel.

Phase 2 ships the Open/Closed seam (``@register_dep_graph_strategy``) with
**zero** strategies registered. The load-bearing tests:

- T-04 (per-PackageManager-variant fallback) encodes "dispatch is total over
  the Literal" — a future ADR-amend that extends ``PackageManager`` and
  forgets to register a strategy flips this red.
- T-06 (mock-strategy round-trip) encodes the Phase-3 seam: adding a strategy
  is one decorator + one file; the probe body never changes.
- T-07 (zero strategies in Phase 2) encodes the explicit Phase-3 boundary —
  the test failing on the first Phase-3 PR is the loud transition signal.

Every test that touches :data:`default_dep_graph_registry` snapshots +
restores it in a ``finally:`` via the ``clean_dep_graph_registry`` fixture so
the module-level singleton stays empty between tests (the Phase-2 invariant
T-07 pins).
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, get_args

import networkx as nx
import pytest
from pydantic import ValidationError

from codegenie.depgraph import (
    DepGraphProbeOutput,
    default_dep_graph_registry,
)
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_b import dep_graph as dg
from codegenie.probes.layer_b.dep_graph import _WARNING_IDS, DepGraphProbe
from codegenie.probes.registry import default_registry
from codegenie.types.identifiers import PackageManager

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_dep_graph_registry() -> Any:
    """Snapshot + restore the singleton dep-graph registry around each test."""
    saved_strategies = dict(default_dep_graph_registry._strategies)
    saved_origins = dict(default_dep_graph_registry._origins)
    default_dep_graph_registry._strategies.clear()
    default_dep_graph_registry._origins.clear()
    try:
        yield default_dep_graph_registry
    finally:
        default_dep_graph_registry._strategies.clear()
        default_dep_graph_registry._origins.clear()
        default_dep_graph_registry._strategies.update(saved_strategies)
        default_dep_graph_registry._origins.update(saved_origins)


def _make_repo(tmp_path: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=tmp_path,
        git_commit=None,
        detected_languages={"javascript": 1},
        config={},
    )


def _make_ctx(
    tmp_path: Path,
    *,
    parsed_manifest: Any = None,
) -> ProbeContext:
    workspace = tmp_path / "_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return ProbeContext(
        cache_dir=tmp_path / "_cache",
        output_dir=tmp_path / "_out",
        workspace=workspace,
        logger=logging.getLogger("test"),
        config={},
        parsed_manifest=parsed_manifest,
    )


def _write_pkg_json(repo: Path, payload: dict[str, Any]) -> None:
    (repo / "package.json").write_text(json.dumps(payload), encoding="utf-8")


def _make_parsed_manifest(repo_root: Path) -> Any:
    """Return a ``parsed_manifest`` closure that reads JSON off disk."""

    def _fn(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    return _fn


def _run(probe: DepGraphProbe, repo: Path, ctx: ProbeContext) -> Any:
    return asyncio.run(probe.run(_make_repo(repo), ctx))


# ---------------------------------------------------------------------------
# T-01 — AC-1 probe contract attributes
# ---------------------------------------------------------------------------


def test_probe_contract_attributes() -> None:
    p = DepGraphProbe()
    assert p.name == "dep_graph"
    assert p.version == "0.1.0"
    assert p.layer == "B"
    # tier=task_specific (validator note: Rule 7 — followed
    # NodeBuildSystemProbe's better-tested precedent over the draft's
    # ``tier="base"``).
    assert p.tier == "task_specific"
    assert p.applies_to_languages == ["javascript", "typescript"]
    assert p.applies_to_tasks == ["*"]
    # Validator note #13: re-detect inline → no topological dependency.
    assert p.requires == []
    assert p.timeout_seconds == 60
    inputs = p.declared_inputs
    # Lockfile inputs (cache key sensitive to filesystem state).
    for tok in (
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lockb",
        "pnpm-workspace.yaml",
    ):
        assert tok in inputs, f"missing declared_input {tok!r}"
    # AC-1: includes the dep_graph_strategy_set:<resolved> token.
    strategy_tokens = [t for t in inputs if t.startswith("dep_graph_strategy_set:")]
    assert len(strategy_tokens) == 1, (
        f"expected exactly one strategy-set token, got {strategy_tokens!r}"
    )
    # Phase 2 reality: zero strategies → empty resolved list.
    assert strategy_tokens[0] == "dep_graph_strategy_set:"
    # Two-arg run() signature (self+repo+ctx).
    assert DepGraphProbe.run.__code__.co_argcount == 3


# ---------------------------------------------------------------------------
# T-02 — no direct parser imports (AC-2 spirit)
# ---------------------------------------------------------------------------


def test_no_direct_parser_imports() -> None:
    """The probe consumes ``ctx.parsed_manifest`` — never reaches around it."""
    src = Path(dg.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"safe_yaml", "jsonc", "pyarn"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in banned, f"forbidden import {alias.name!r}"
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            assert mod not in banned, f"forbidden import-from {node.module!r}"


# ---------------------------------------------------------------------------
# T-03 — no manifest detected → typed low-confidence
# ---------------------------------------------------------------------------


def test_no_manifest_detected_emits_low_confidence(tmp_path: Path) -> None:
    """Empty repo (no package.json, no lockfile) → typed low-confidence slice."""
    ctx = _make_ctx(tmp_path, parsed_manifest=_make_parsed_manifest(tmp_path))
    out = _run(DepGraphProbe(), tmp_path, ctx)
    slice_ = out.schema_slice["dep_graph"]
    assert out.confidence == "low"
    assert slice_["confidence"] == "low"
    assert slice_["reason"] == "no_manifest_detected"
    assert slice_["ecosystem"] is None
    assert slice_["nodes_count"] == 0
    assert slice_["edges_count"] == 0
    assert "dep_graph.no_manifest_detected" in out.warnings


# ---------------------------------------------------------------------------
# T-04 — per-PackageManager-variant fallback (AC-4, AC-8)
# ---------------------------------------------------------------------------


_PM_LOCKFILES: dict[PackageManager, dict[str, Any]] = {
    "bun": {"lockfile": "bun.lockb", "pkg": None},
    "pnpm": {"lockfile": "pnpm-lock.yaml", "pkg": {"packageManager": "pnpm@8.6.0"}},
    "yarn-classic": {"lockfile": "yarn.lock", "pkg": {"packageManager": "yarn@1.22.19"}},
    "yarn-berry": {"lockfile": "yarn.lock", "pkg": {"packageManager": "yarn@4.0.0"}},
    "npm": {"lockfile": "package-lock.json", "pkg": None},
}


def _provision_repo_for(pm: PackageManager, repo: Path) -> None:
    """Lay down the on-disk markers that re-detect to ``pm``."""
    spec = _PM_LOCKFILES[pm]
    (repo / spec["lockfile"]).write_bytes(b"")  # presence only
    if spec["pkg"] is not None:
        _write_pkg_json(repo, spec["pkg"])
    else:
        # Need a manifest to avoid no_manifest_detected; minimal pkg JSON.
        _write_pkg_json(repo, {"name": "fixture"})


@pytest.mark.parametrize("pm", list(get_args(PackageManager)))
def test_no_strategy_per_package_manager_variant(
    pm: PackageManager,
    tmp_path: Path,
    clean_dep_graph_registry: Any,
) -> None:
    """For every PackageManager Literal value, the no-strategy path emits
    typed low-confidence + writes a valid empty graph artifact."""
    _provision_repo_for(pm, tmp_path)
    ctx = _make_ctx(tmp_path, parsed_manifest=_make_parsed_manifest(tmp_path))
    out = _run(DepGraphProbe(), tmp_path, ctx)
    slice_ = out.schema_slice["dep_graph"]
    assert slice_["confidence"] == "low", f"{pm}: expected low confidence"
    assert slice_["reason"] == "no_strategy_for_ecosystem", f"{pm}: wrong reason"
    assert slice_["ecosystem"] == pm, f"{pm}: ecosystem echo wrong"
    assert slice_["nodes_count"] == 0
    assert slice_["edges_count"] == 0
    # Raw artifact well-formed-empty.
    raw_path = tmp_path / ".codegenie" / "context" / "raw" / "dep-graph.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert raw["ecosystem"] == pm
    assert raw["nodes"] == []
    # NetworkX modern API uses ``edges`` (not ``links``).
    assert raw["edges"] == []


# ---------------------------------------------------------------------------
# T-05 — unrecognized packageManager string (AC-5)
# ---------------------------------------------------------------------------


def test_unrecognized_package_manager_emits_typed_warning(tmp_path: Path) -> None:
    """``packageManager: deno@2.0.0`` (future ecosystem) → unrecognized fallback."""
    _write_pkg_json(tmp_path, {"packageManager": "deno@2.0.0"})
    ctx = _make_ctx(tmp_path, parsed_manifest=_make_parsed_manifest(tmp_path))
    out = _run(DepGraphProbe(), tmp_path, ctx)
    slice_ = out.schema_slice["dep_graph"]
    assert slice_["confidence"] == "low"
    assert slice_["reason"] == "unrecognized_package_manager"
    assert "dep_graph.unrecognized_package_manager" in out.warnings
    # Ecosystem echoes the unrecognized field VERBATIM so operators can grep.
    assert slice_["ecosystem"] == "deno@2.0.0"


# ---------------------------------------------------------------------------
# T-06 — mock strategy round-trip (AC-7, the Open/Closed exercise)
# ---------------------------------------------------------------------------


def test_mock_strategy_round_trip(tmp_path: Path, clean_dep_graph_registry: Any) -> None:
    """Register a mock pnpm strategy, run the probe, assert high confidence +
    well-formed artifact AND that the strategy received ctx + manifests
    identity-preserved (mutation resistance — validator note #17a)."""
    captured: dict[str, Any] = {}

    @default_dep_graph_registry.register("pnpm")
    def _mock_pnpm(ctx: ProbeContext, manifests: list[Any]) -> nx.DiGraph:
        captured["ctx"] = ctx
        captured["manifests"] = manifests
        g: nx.DiGraph = nx.DiGraph()
        g.add_edge("payments-api", "shared-models")
        g.add_edge("payments-api", "payments-core")
        return g

    _write_pkg_json(tmp_path, {"name": "fixture", "packageManager": "pnpm@8.6.0"})
    (tmp_path / "pnpm-lock.yaml").write_bytes(b"")
    ctx = _make_ctx(tmp_path, parsed_manifest=_make_parsed_manifest(tmp_path))
    out = _run(DepGraphProbe(), tmp_path, ctx)

    slice_ = out.schema_slice["dep_graph"]
    assert slice_["confidence"] == "high"
    assert slice_["reason"] is None
    assert slice_["ecosystem"] == "pnpm"
    assert slice_["nodes_count"] == 3
    assert slice_["edges_count"] == 2

    raw_path = tmp_path / ".codegenie" / "context" / "raw" / "dep-graph.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert raw["ecosystem"] == "pnpm"
    assert {n["id"] for n in raw["nodes"]} == {
        "payments-api",
        "shared-models",
        "payments-core",
    }
    assert len(raw["edges"]) == 2

    # Validator note #17a: identity-preserved on the way to the strategy.
    assert captured["ctx"] is ctx
    assert isinstance(captured["manifests"], list)
    # The parsed package.json is in the manifests list.
    assert any(isinstance(m, dict) and m.get("name") == "fixture" for m in captured["manifests"])


# ---------------------------------------------------------------------------
# T-07 — zero strategies registered in Phase 2 (AC-13)
# ---------------------------------------------------------------------------


def test_no_strategies_registered_in_phase_2() -> None:
    """After importing ``codegenie.probes`` (which transitively imports every
    Phase 2 probe module), no dep-graph strategy is registered.

    **Phase-3 boundary signal.** The first Phase-3 PR registering
    ``build_pnpm`` / ``build_npm`` / etc. will fail this test; that's the
    explicit "Phase 3 transition" gate. Delete this test in that PR and
    replace with assertions over the concrete strategies.
    """
    import codegenie.probes  # noqa: F401 — force decorator-time registrations

    assert default_dep_graph_registry.registered_ecosystems() == frozenset()


# ---------------------------------------------------------------------------
# T-08 — raw artifact valid-empty on no-strategy (AC-9)
# ---------------------------------------------------------------------------


def test_raw_dep_graph_json_well_formed_on_no_strategy(tmp_path: Path) -> None:
    _write_pkg_json(tmp_path, {"name": "fx"})
    (tmp_path / "package-lock.json").write_bytes(b"")
    ctx = _make_ctx(tmp_path, parsed_manifest=_make_parsed_manifest(tmp_path))
    _run(DepGraphProbe(), tmp_path, ctx)
    raw_path = tmp_path / ".codegenie" / "context" / "raw" / "dep-graph.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    assert raw == {
        "schema_version": 1,
        "ecosystem": "npm",
        "nodes": [],
        "edges": [],
    }


# ---------------------------------------------------------------------------
# T-09 — DepGraphProbeOutput is frozen + extra=forbid (AC-6)
# ---------------------------------------------------------------------------


def test_dep_graph_probe_output_strict() -> None:
    with pytest.raises(ValidationError):
        DepGraphProbeOutput(
            graph_path=None,
            confidence="low",
            reason="no_strategy_for_ecosystem",
            unknown_field="x",  # type: ignore[call-arg]
        )
    inst = DepGraphProbeOutput(
        graph_path=None, confidence="low", reason="no_strategy_for_ecosystem"
    )
    with pytest.raises((ValidationError, TypeError)):
        inst.confidence = "high"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# T-09b — DepGraphProbeOutput single-source-of-truth (validator note #17b)
# ---------------------------------------------------------------------------


def test_dep_graph_probe_output_field_set_pinned() -> None:
    """Pin the shipped model's field set so a future story can't silently fork
    it inside the probe module."""
    assert set(DepGraphProbeOutput.model_fields) == {
        "graph_path",
        "confidence",
        "reason",
    }


# ---------------------------------------------------------------------------
# T-10 — PackageManager imported from codegenie.types.identifiers
# ---------------------------------------------------------------------------


def test_package_manager_imported_from_types_identifiers() -> None:
    """Validator note #4: import source MUST be the kernel-tier re-export."""
    src = Path(dg.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    pm_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "PackageManager":
                    pm_imports.append(node.module or "")
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "PackageManager":
                    pytest.fail("PackageManager re-assigned at module level")
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "PackageManager":
                pytest.fail("PackageManager re-annotated at module level")
    assert pm_imports == ["codegenie.types.identifiers"], pm_imports


# ---------------------------------------------------------------------------
# T-11 — warning ID regex compliance (AC-11)
# ---------------------------------------------------------------------------


def test_warning_ids_match_adr_0007_regex() -> None:
    pattern = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    for wid in _WARNING_IDS:
        assert pattern.match(wid), f"ADR-0007 violation: {wid!r}"
    # Validator note #11 — required IDs present.
    required = {
        "dep_graph.upstream_build_system_unavailable",
        "dep_graph.unrecognized_package_manager",
        "dep_graph.strategy_timeout",
        "dep_graph.package_manager_field_unparseable",
        "dep_graph.yarn_variant_inferred",
        "dep_graph.no_manifest_detected",
    }
    assert required <= _WARNING_IDS


# ---------------------------------------------------------------------------
# T-12 — registry membership + for_task filter (AC-12)
# ---------------------------------------------------------------------------


def test_registry_membership_and_for_task_filter() -> None:
    import codegenie.probes  # noqa: F401 — ensure decorator ran.

    assert DepGraphProbe in default_registry.all_probes()
    ts = default_registry.for_task("*", frozenset({"typescript"}))
    js = default_registry.for_task("*", frozenset({"javascript"}))
    py = default_registry.for_task("*", frozenset({"python"}))
    assert DepGraphProbe in ts
    assert DepGraphProbe in js
    # Negative control — Python is NOT a Node language; the probe must NOT
    # appear (validator note #17e).
    assert DepGraphProbe not in py


# ---------------------------------------------------------------------------
# T-13 — strategy timeout path (validator note #11)
# ---------------------------------------------------------------------------


def test_strategy_timeout_path(tmp_path: Path, clean_dep_graph_registry: Any) -> None:
    """A slow strategy is bounded by the probe's timeout; the probe emits
    a typed low-confidence slice rather than hanging the gather."""
    import time

    @default_dep_graph_registry.register("pnpm")
    def _slow_pnpm(ctx: ProbeContext, manifests: list[Any]) -> nx.DiGraph:
        # Block the worker thread for ~1.05s; the probe's 1s wait_for
        # cancels the wrapping coro before the strategy returns. The thread
        # itself finishes shortly after — ``asyncio.run`` waits for the
        # default executor on close, so total test time is ~1.05s.
        time.sleep(1.05)
        return nx.DiGraph()

    _write_pkg_json(tmp_path, {"packageManager": "pnpm@8.6.0"})
    (tmp_path / "pnpm-lock.yaml").write_bytes(b"")
    ctx = _make_ctx(tmp_path, parsed_manifest=_make_parsed_manifest(tmp_path))
    probe = DepGraphProbe()
    probe.timeout_seconds = 1
    out = _run(probe, tmp_path, ctx)
    slice_ = out.schema_slice["dep_graph"]
    assert slice_["confidence"] == "low"
    assert slice_["reason"] == "strategy_timeout"
    assert "dep_graph.strategy_timeout" in out.warnings


# ---------------------------------------------------------------------------
# T-14 — yarn-classic vs yarn-berry detection split (validator note #17c)
# ---------------------------------------------------------------------------


def test_yarn_classic_detection(tmp_path: Path) -> None:
    _write_pkg_json(tmp_path, {"packageManager": "yarn@1.22.19"})
    (tmp_path / "yarn.lock").write_bytes(b"")
    ctx = _make_ctx(tmp_path, parsed_manifest=_make_parsed_manifest(tmp_path))
    out = _run(DepGraphProbe(), tmp_path, ctx)
    assert out.schema_slice["dep_graph"]["ecosystem"] == "yarn-classic"


def test_yarn_berry_detection_via_package_manager_field(tmp_path: Path) -> None:
    _write_pkg_json(tmp_path, {"packageManager": "yarn@4.0.0"})
    (tmp_path / "yarn.lock").write_bytes(b"")
    ctx = _make_ctx(tmp_path, parsed_manifest=_make_parsed_manifest(tmp_path))
    out = _run(DepGraphProbe(), tmp_path, ctx)
    assert out.schema_slice["dep_graph"]["ecosystem"] == "yarn-berry"


def test_yarn_berry_detection_via_yarnrc_yml(tmp_path: Path) -> None:
    _write_pkg_json(tmp_path, {"name": "fx"})
    (tmp_path / "yarn.lock").write_bytes(b"")
    (tmp_path / ".yarnrc.yml").write_text("nodeLinker: pnp\n", encoding="utf-8")
    ctx = _make_ctx(tmp_path, parsed_manifest=_make_parsed_manifest(tmp_path))
    out = _run(DepGraphProbe(), tmp_path, ctx)
    assert out.schema_slice["dep_graph"]["ecosystem"] == "yarn-berry"


def test_yarn_inferred_classic_emits_warning(tmp_path: Path) -> None:
    """Plain ``yarn.lock`` with no berry markers and no packageManager field
    → infer classic + emit ``dep_graph.yarn_variant_inferred`` warning."""
    _write_pkg_json(tmp_path, {"name": "fx"})
    (tmp_path / "yarn.lock").write_bytes(b"")
    ctx = _make_ctx(tmp_path, parsed_manifest=_make_parsed_manifest(tmp_path))
    out = _run(DepGraphProbe(), tmp_path, ctx)
    assert out.schema_slice["dep_graph"]["ecosystem"] == "yarn-classic"
    assert "dep_graph.yarn_variant_inferred" in out.warnings


# ---------------------------------------------------------------------------
# T-15 — deterministic serialization (validator note #15, #17d)
# ---------------------------------------------------------------------------


def test_raw_artifact_byte_identical_reruns(tmp_path: Path, clean_dep_graph_registry: Any) -> None:
    """Two consecutive runs of the same probe against the same fixture
    produce byte-identical raw artifacts. Phase 3 cache stability hinges on
    this."""

    @default_dep_graph_registry.register("pnpm")
    def _mock_pnpm(ctx: ProbeContext, manifests: list[Any]) -> nx.DiGraph:
        g: nx.DiGraph = nx.DiGraph()
        # Add edges in a non-sorted order; serialization must canonicalize.
        g.add_edge("z", "a")
        g.add_edge("m", "n")
        g.add_edge("a", "b")
        return g

    _write_pkg_json(tmp_path, {"packageManager": "pnpm@8.6.0"})
    (tmp_path / "pnpm-lock.yaml").write_bytes(b"")
    ctx = _make_ctx(tmp_path, parsed_manifest=_make_parsed_manifest(tmp_path))
    raw_path = tmp_path / ".codegenie" / "context" / "raw" / "dep-graph.json"

    _run(DepGraphProbe(), tmp_path, ctx)
    bytes_a = raw_path.read_bytes()
    _run(DepGraphProbe(), tmp_path, ctx)
    bytes_b = raw_path.read_bytes()
    assert bytes_a == bytes_b, "non-deterministic serialization"


# ---------------------------------------------------------------------------
# T-16 — heaviness annotation + no runs_last (02-ADR-0003)
# ---------------------------------------------------------------------------


def test_heaviness_annotation_default_light() -> None:
    import codegenie.probes  # noqa: F401

    entry = next(e for e in default_registry.sorted_for_dispatch() if e.cls is DepGraphProbe)
    assert entry.heaviness == "light"
    assert entry.runs_last is False
