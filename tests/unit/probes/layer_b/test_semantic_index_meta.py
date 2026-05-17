"""Tests for ``SemanticIndexMetaProbe`` (S4-06)."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest

from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_b import semantic_index_meta as sim
from codegenie.probes.layer_b._indexable_files import _count_indexable_files
from codegenie.probes.layer_b.semantic_index_meta import (
    _ERROR_IDS,
    _WARNING_IDS,
    SemanticIndexMetaProbe,
)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def snapshot(repo_root: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=repo_root,
        git_commit=None,
        detected_languages={"typescript": 1},
        config={},
    )


@pytest.fixture
def ctx(repo_root: Path) -> ProbeContext:
    output_dir = repo_root / ".codegenie" / "context"
    output_dir.mkdir(parents=True, exist_ok=True)
    return ProbeContext(
        cache_dir=repo_root / ".codegenie" / "cache",
        output_dir=output_dir,
        workspace=repo_root / ".codegenie" / "workspace",
        logger=logging.getLogger("test"),
        config={},
    )


def _run(snapshot: RepoSnapshot, ctx: ProbeContext) -> dict[str, Any]:
    probe = SemanticIndexMetaProbe()
    out = asyncio.run(probe.run(snapshot, ctx))
    return {
        "schema_slice": out.schema_slice,
        "confidence": out.confidence,
        "warnings": out.warnings,
        "errors": out.errors,
    }


# ---------------------------------------------------------------------------
# T-M1 — Probe contract attributes (AC-M1)
# ---------------------------------------------------------------------------


def test_probe_contract_attributes() -> None:
    probe = SemanticIndexMetaProbe()
    assert probe.name == "semantic_index_meta"
    assert probe.version == "0.1.0"
    assert probe.layer == "B"
    assert probe.tier == "base"
    assert probe.applies_to_languages == ["javascript", "typescript"]
    assert probe.applies_to_tasks == ["*"]
    assert probe.requires == ["language_detection"]
    assert probe.timeout_seconds == 10
    assert probe.cache_strategy == "content"
    sig = inspect.signature(SemanticIndexMetaProbe.run)
    assert list(sig.parameters) == ["self", "repo", "ctx"]


# ---------------------------------------------------------------------------
# T-M3 — Reads tsconfig via Phase 1 jsonc parser (AC-M2)
# ---------------------------------------------------------------------------


def test_reads_tsconfig_via_phase1_jsonc_parser() -> None:
    src = Path(sim.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    found_jsonc_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = {alias.name for alias in node.names}
            if mod == "codegenie.parsers" and "jsonc" in names:
                found_jsonc_import = True
            if mod == "codegenie.parsers.jsonc":
                found_jsonc_import = True
    assert found_jsonc_import, "semantic_index_meta.py must import the Phase 1 jsonc parser"
    # Must NOT use raw json.load on tsconfig
    assert "json.load" not in src or src.count("json.load") == 0, (
        "raw json.load forbidden; use codegenie.parsers.jsonc.load"
    )


# ---------------------------------------------------------------------------
# T-M4 — Slice shape on minimal tsconfig (AC-M3)
# ---------------------------------------------------------------------------


def test_slice_shape_minimal_ts(repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext) -> None:
    tsconfig = {
        "compilerOptions": {
            "target": "es2022",
            "module": "esnext",
            "moduleResolution": "node",
            "strict": True,
        },
        "include": ["src/**/*"],
        "exclude": ["node_modules"],
    }
    (repo_root / "tsconfig.json").write_text(json.dumps(tsconfig), encoding="utf-8")
    out = _run(snapshot, ctx)
    slice_ = out["schema_slice"]["semantic_index_meta"]
    assert slice_["tsconfig_path"] == "tsconfig.json"
    assert slice_["has_extends"] is False
    assert slice_["target"] == "es2022"
    assert slice_["module"] == "esnext"
    assert slice_["module_resolution"] == "node"
    assert slice_["strict"] is True
    assert slice_["include_globs"] == ["src/**/*"]
    assert slice_["exclude_globs"] == ["node_modules"]
    assert slice_["confidence"] == "high"
    assert out["confidence"] == "high"


def test_extends_chain_warning_when_present(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    tsconfig = {
        "extends": "./tsconfig.base.json",
        "compilerOptions": {"target": "es2022"},
    }
    (repo_root / "tsconfig.json").write_text(json.dumps(tsconfig), encoding="utf-8")
    out = _run(snapshot, ctx)
    slice_ = out["schema_slice"]["semantic_index_meta"]
    assert slice_["has_extends"] is True
    assert "semantic_index_meta.extends_chain_not_resolved" in out["warnings"]


# ---------------------------------------------------------------------------
# T-M5 — files_count_estimate matches SCIP count (AC-M4)
# ---------------------------------------------------------------------------


def test_files_count_estimate_matches_scip_count(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "tsconfig.json").write_text("{}", encoding="utf-8")
    (repo_root / "a.ts").write_text("")
    (repo_root / "b.tsx").write_text("")
    (repo_root / "c.js").write_text("")  # should NOT count (SCIP scope)
    (repo_root / "node_modules").mkdir()
    (repo_root / "node_modules" / "skip.ts").write_text("")
    out = _run(snapshot, ctx)
    expected = _count_indexable_files(repo_root)
    assert out["schema_slice"]["semantic_index_meta"]["files_count_estimate"] == expected
    assert expected == 2


def test_both_probes_import_indexable_files_kernel() -> None:
    """T-M5 second leg: scip_index AND semantic_index_meta both import
    the shared kernel — divergence via copy-paste is mechanically forbidden."""
    for module_path in (
        "src/codegenie/probes/layer_b/scip_index.py",
        "src/codegenie/probes/layer_b/semantic_index_meta.py",
    ):
        src = Path(module_path).read_text(encoding="utf-8")
        tree = ast.parse(src)
        found = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "codegenie.probes.layer_b._indexable_files"
            for node in ast.walk(tree)
        )
        assert found, f"{module_path} must import codegenie.probes.layer_b._indexable_files"


# ---------------------------------------------------------------------------
# T-M6 — No tsconfig → medium confidence (AC-M3)
# ---------------------------------------------------------------------------


def test_no_tsconfig_emits_medium_confidence(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    out = _run(snapshot, ctx)
    assert out["confidence"] == "medium"
    slice_ = out["schema_slice"]["semantic_index_meta"]
    assert slice_["confidence"] == "medium"
    assert slice_["tsconfig_path"] is None
    assert "semantic_index_meta.no_tsconfig" in out["warnings"]


# ---------------------------------------------------------------------------
# T-M7 — Parse failure → low confidence + error (AC-M5)
# ---------------------------------------------------------------------------


def test_tsconfig_parse_failure_path(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "tsconfig.json").write_text("{\n", encoding="utf-8")
    out = _run(snapshot, ctx)
    assert out["confidence"] == "low"
    assert "semantic_index_meta.tsconfig_unparseable" in out["errors"]


# ---------------------------------------------------------------------------
# Warning/error ID convention (AC-X4)
# ---------------------------------------------------------------------------


def test_warning_and_error_ids_match_adr_0007() -> None:
    pattern = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    for ident in _WARNING_IDS | _ERROR_IDS:
        assert pattern.match(ident), f"ADR-0007 violation: {ident!r}"


# ---------------------------------------------------------------------------
# Determinism (AC-X9)
# ---------------------------------------------------------------------------


def test_probe_is_deterministic_on_fixture(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    tsconfig = {
        "compilerOptions": {"target": "es2022", "strict": True},
        "include": ["b/**", "a/**"],
        "exclude": ["dist"],
    }
    (repo_root / "tsconfig.json").write_text(json.dumps(tsconfig), encoding="utf-8")
    (repo_root / "f.ts").write_text("")
    out1 = _run(snapshot, ctx)
    out2 = _run(snapshot, ctx)
    a = json.dumps(out1["schema_slice"], sort_keys=True)
    b = json.dumps(out2["schema_slice"], sort_keys=True)
    assert a == b


# ---------------------------------------------------------------------------
# Pure-helpers / functional-core (AC-X8)
# ---------------------------------------------------------------------------


def test_pure_helpers_have_no_io() -> None:
    module_src = Path(sim.__file__).read_text(encoding="utf-8")
    tree = ast.parse(module_src)
    forbidden_call_names = {"open", "read_bytes", "read_text", "write_bytes", "write_text"}
    forbidden_modules = {"subprocess", "asyncio"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name == "run":
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                callee = inner.func
                attr = callee.attr if isinstance(callee, ast.Attribute) else None
                name = callee.id if isinstance(callee, ast.Name) else None
                if attr in forbidden_call_names or name in forbidden_call_names:
                    raise AssertionError(
                        f"pure helper {node.name!r} contains forbidden I/O call {name or attr!r}"
                    )
                if isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name):
                    if callee.value.id in forbidden_modules:
                        raise AssertionError(
                            f"pure helper {node.name!r} touches forbidden module "
                            f"{callee.value.id!r}"
                        )


# ---------------------------------------------------------------------------
# Edge — malformed compilerOptions (defensive shape)
# ---------------------------------------------------------------------------


def test_malformed_compiler_options_falls_through_to_defaults(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    """compilerOptions: "string-not-an-object" — probe must not crash."""
    (repo_root / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": "bad"}), encoding="utf-8"
    )
    out = _run(snapshot, ctx)
    slice_ = out["schema_slice"]["semantic_index_meta"]
    assert slice_["target"] is None
    assert slice_["strict"] is False
    assert out["confidence"] == "high"
