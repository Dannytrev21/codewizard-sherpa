"""Tests for ``GeneratedCodeProbe`` (S4-06)."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_b import generated_code as gc
from codegenie.probes.layer_b.generated_code import (
    _GENERATED_DIRS,
    _GENERATOR_HEADER_MARKERS,
    _MAX_HEAD_BYTES,
    _WARNING_IDS,
    GeneratedCodeProbe,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    probe = GeneratedCodeProbe()
    out = asyncio.run(probe.run(snapshot, ctx))
    return {
        "schema_slice": out.schema_slice,
        "confidence": out.confidence,
        "warnings": out.warnings,
        "errors": out.errors,
    }


# ---------------------------------------------------------------------------
# T-G1 — Probe contract attributes (AC-G1)
# ---------------------------------------------------------------------------


def test_probe_contract_attributes() -> None:
    probe = GeneratedCodeProbe()
    assert probe.name == "generated_code"
    assert probe.version == "0.1.0"
    assert probe.layer == "B"
    assert probe.tier == "base"
    assert probe.applies_to_languages == ["javascript", "typescript"]
    assert probe.applies_to_tasks == ["*"]
    assert probe.requires == ["language_detection"]
    assert probe.timeout_seconds == 30
    assert probe.cache_strategy == "content"
    # Two-arg signature per frozen ABC.
    sig = inspect.signature(GeneratedCodeProbe.run)
    assert list(sig.parameters) == ["self", "repo", "ctx"]


# ---------------------------------------------------------------------------
# T-G3 — Per-generator marker detection (AC-G2, AC-G5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "needle"), list(_GENERATOR_HEADER_MARKERS))
def test_per_generator_marker_detection(
    name: str, needle: bytes, repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    src = repo_root / "src"
    src.mkdir()
    (src / f"{name.replace('-', '_')}.ts").write_bytes(b"// " + needle + b"\nexport const x = 1;\n")
    out = _run(snapshot, ctx)
    files = out["schema_slice"]["generated_code"]["files"]
    assert len(files) == 1, f"expected 1 detection for {name}, got {files}"
    assert files[0]["generator"] == name


# ---------------------------------------------------------------------------
# T-G4 — Every generator marker has a test (AC-G5 enumeration guard)
# ---------------------------------------------------------------------------


def test_every_generator_marker_has_a_test() -> None:
    """The parametrize IDs of T-G3 cover every entry in
    ``_GENERATOR_HEADER_MARKERS``. Mechanically forbids adding a marker
    without adding fixture coverage."""
    expected = {name for name, _ in _GENERATOR_HEADER_MARKERS}
    # Re-parse this test module to find the parametrize and assert all
    # names are covered.
    src = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    covered: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "parametrize"
        ):
            # parametrize('arg, arg', list(_GENERATOR_HEADER_MARKERS))
            for arg in node.args:
                if isinstance(arg, ast.Call) and ast.unparse(arg.func) == "list":
                    if (
                        len(arg.args) == 1
                        and isinstance(arg.args[0], ast.Name)
                        and arg.args[0].id == "_GENERATOR_HEADER_MARKERS"
                    ):
                        covered = expected
    assert covered == expected, f"missing parametrize coverage: {expected - covered}"


# ---------------------------------------------------------------------------
# T-G5 — Build outputs from package.json#files (AC-G3)
# ---------------------------------------------------------------------------


def test_build_outputs_from_package_json_files(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    pkg = {
        "name": "x",
        "files": ["dist/index.js", "dist/**/*.js"],
    }
    (repo_root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["generated_code"]["build_outputs"] == sorted(
        ["dist/index.js", "dist/**/*.js"]
    )


def test_build_outputs_empty_when_no_files_field(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "package.json").write_text("{}", encoding="utf-8")
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["generated_code"]["build_outputs"] == []


def test_build_outputs_empty_when_no_package_json(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["generated_code"]["build_outputs"] == []


# ---------------------------------------------------------------------------
# T-G6 — Marker-absent path is honest 'medium' (AC-G4, AC-X3)
# ---------------------------------------------------------------------------


def test_marker_absent_emits_medium_confidence(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    """Empty repo: no markers detected → confidence='medium', NOT 'low'.
    'low' is reserved for parser failures."""
    out = _run(snapshot, ctx)
    assert out["confidence"] == "medium"
    assert out["schema_slice"]["generated_code"]["confidence"] == "medium"
    assert out["schema_slice"]["generated_code"]["files"] == []
    assert "generated_code.no_markers_detected" in out["warnings"]


def test_marker_present_promotes_to_high_confidence(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "gen.ts").write_bytes(
        b"// This file was automatically generated by graphql-codegen\nexport const q = 1;\n"
    )
    out = _run(snapshot, ctx)
    assert out["confidence"] == "high"


# ---------------------------------------------------------------------------
# T-G-Directory — Well-known directory convention detection (AC-G2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dir_name", sorted(_GENERATED_DIRS))
def test_directory_convention_detected(
    dir_name: str, repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    target_dir = repo_root / dir_name
    target_dir.mkdir(parents=True)
    (target_dir / "a.ts").write_bytes(b"export const a = 1;\n")
    out = _run(snapshot, ctx)
    files = out["schema_slice"]["generated_code"]["files"]
    assert any(f["generator"] == "directory_convention" for f in files), files


# ---------------------------------------------------------------------------
# T-G-Regen — package.json#scripts surfaces regenerate_command (AC-G3)
# ---------------------------------------------------------------------------


def test_regenerate_command_from_scripts(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    pkg = {"scripts": {"codegen": "graphql-codegen"}}
    (repo_root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    (repo_root / "schema.ts").write_bytes(
        b"// This file was automatically generated by graphql-codegen\n"
    )
    out = _run(snapshot, ctx)
    files = out["schema_slice"]["generated_code"]["files"]
    assert files[0]["regenerate_command"] == "pnpm run codegen"


# ---------------------------------------------------------------------------
# T-G7 — Marker catalog is Open/Closed (AC-X2)
# ---------------------------------------------------------------------------


def test_marker_catalog_is_open_closed() -> None:
    """No `Compare` node outside the constant declaration compares to a
    string literal that is present as a marker name — i.e., no
    ``if generator == "graphql-codegen"`` branches. Dispatch is via
    iteration over the tuple."""
    module_src = Path(gc.__file__).read_text(encoding="utf-8")
    tree = ast.parse(module_src)
    forbidden = {name for name, _ in _GENERATOR_HEADER_MARKERS}

    # Find the assignment of _GENERATOR_HEADER_MARKERS so we can
    # exclude it from the scan.
    assign_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign | ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_GENERATOR_HEADER_MARKERS"
            for t in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets)
        ):
            for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                assign_lines.add(ln)
        # Also exclude the _REGEN_SCRIPT_KEYS_BY_GENERATOR (uses names as keys).
        if isinstance(node, ast.AnnAssign | ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_REGEN_SCRIPT_KEYS_BY_GENERATOR"
            for t in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets)
        ):
            for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                assign_lines.add(ln)

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and node.lineno not in assign_lines:
            for comp in [node.left, *node.comparators]:
                if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                    assert comp.value not in forbidden, (
                        f"branch-on-marker forbidden: {comp.value!r} at "
                        f"line {node.lineno} (use catalog iteration instead)"
                    )


# ---------------------------------------------------------------------------
# T-G-Determinism — Byte-identical reruns (AC-X9)
# ---------------------------------------------------------------------------


def test_probe_is_deterministic_on_fixture(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(
        b"// This file was automatically generated by graphql-codegen\n"
    )
    (repo_root / "b.ts").write_bytes(b"// This file is auto-generated by Prisma\n")
    pkg = {"files": ["dist/x.js", "dist/y.js"], "scripts": {"codegen": "x"}}
    (repo_root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    out1 = _run(snapshot, ctx)
    out2 = _run(snapshot, ctx)
    a = json.dumps(out1["schema_slice"], sort_keys=True)
    b = json.dumps(out2["schema_slice"], sort_keys=True)
    assert a == b
    assert out1["warnings"] == out2["warnings"]


# ---------------------------------------------------------------------------
# T-G-Warnings — All warning IDs match ADR-0007 (AC-X4)
# ---------------------------------------------------------------------------


def test_warning_ids_match_adr_0007() -> None:
    import re

    pattern = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    for wid in _WARNING_IDS:
        assert pattern.match(wid), f"ADR-0007 violation: {wid!r}"


# ---------------------------------------------------------------------------
# T-G-PureHelpers — No I/O in pure helpers (AC-X8)
# ---------------------------------------------------------------------------


def test_pure_helpers_have_no_io() -> None:
    """Module-level helpers (not ``run``, not the imperative shell)
    must contain no ``open``/``Path.read_*``/``Path.write_*``/
    ``subprocess`` calls. Imperative I/O lives only in ``run``."""
    module_src = Path(gc.__file__).read_text(encoding="utf-8")
    tree = ast.parse(module_src)
    forbidden_call_names = {
        "open",
        "read_bytes",
        "read_text",
        "write_bytes",
        "write_text",
    }
    forbidden_modules = {"subprocess", "asyncio"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name in {"run"} or node.name.startswith("_read_"):
            # imperative shell + class-method readers — allowed
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
# T-G-MaxHead — first _MAX_HEAD_BYTES are read for header detection
# ---------------------------------------------------------------------------


def test_header_must_be_within_max_head_bytes(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    """A header marker buried past _MAX_HEAD_BYTES is NOT detected — the
    canonical position of these headers is the first few lines."""
    payload = b"x" * (_MAX_HEAD_BYTES + 100) + b"// This file is auto-generated by Prisma\n"
    (repo_root / "buried.ts").write_bytes(payload)
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["generated_code"]["files"] == []


# ---------------------------------------------------------------------------
# T-G-PackageJsonUnparseable — graceful fallback (AC-G2 edge)
# ---------------------------------------------------------------------------


def test_package_json_unparseable_warning(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "package.json").write_text("{not valid json", encoding="utf-8")
    out = _run(snapshot, ctx)
    assert "generated_code.package_json_unparseable" in out["warnings"]


# ---------------------------------------------------------------------------
# T-G-ParsedManifest — uses ctx.parsed_manifest when supplied
# ---------------------------------------------------------------------------


def test_uses_parsed_manifest_memo_when_present(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    called: list[Path] = []

    def memo(path: Path) -> Mapping[str, Any] | None:
        called.append(path)
        return {"files": ["dist/foo.js"], "scripts": {}}

    (repo_root / "package.json").write_text("ignored-content", encoding="utf-8")
    ctx_with_memo = ProbeContext(
        cache_dir=ctx.cache_dir,
        output_dir=ctx.output_dir,
        workspace=ctx.workspace,
        logger=ctx.logger,
        config=ctx.config,
        parsed_manifest=memo,
    )
    out = _run(snapshot, ctx_with_memo)
    assert called == [repo_root / "package.json"]
    assert out["schema_slice"]["generated_code"]["build_outputs"] == ["dist/foo.js"]
