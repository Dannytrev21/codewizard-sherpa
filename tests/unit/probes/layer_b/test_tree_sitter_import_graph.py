"""Tests for ``TreeSitterImportGraphProbe`` (S4-04, B3).

Grammar loading goes through the 02-ADR-0011 PyPI-wheel kernel
(:func:`codegenie.grammars.lock.language_for`). The legacy
``load_and_verify`` / ``GrammarLockFile`` surface from S4-03 is gone;
:class:`GrammarLoadRefused` is the only grammar-side exception type.

The triple of structural tests against the probe module
(:func:`test_no_parallelism_imports`,
:func:`test_no_threads_created_during_run`,
:func:`test_no_forbidden_coordination_primitives`) is load-bearing —
hidden parallelism inside a probe lies to the coordinator's single
semaphore. Absence of `threading` imports is necessary but not
sufficient; the runtime thread-count check + AST forbidden-symbol
walk are what enforce the discipline (02-ADR-0003).
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import logging
import threading
import tomllib
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.grammars.lock import GrammarLoadRefused
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_b import tree_sitter_import_graph as tsig
from codegenie.probes.layer_b.tree_sitter_import_graph import (
    _ERROR_IDS,
    _FILE_MAX_BYTES,
    _ID_PATTERN,
    _WARNING_IDS,
    Edge,
    ImportGraphArtifact,
    TreeSitterImportGraphProbe,
    _extract_imports,
)
from codegenie.probes.registry import default_registry

_REPO_ROOT = Path(__file__).resolve().parents[4]


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
    probe = TreeSitterImportGraphProbe()
    out = asyncio.run(probe.run(snapshot, ctx))
    return {
        "schema_slice": out.schema_slice,
        "confidence": out.confidence,
        "warnings": out.warnings,
        "errors": out.errors,
        "raw_artifacts": out.raw_artifacts,
    }


# ---------------------------------------------------------------------------
# T-01 — Probe contract attributes (AC-1)
# ---------------------------------------------------------------------------


def test_probe_contract_attributes() -> None:
    probe = TreeSitterImportGraphProbe()
    assert probe.name == "tree_sitter_import_graph"
    assert probe.version == "0.1.0"
    assert probe.layer == "B"
    assert probe.tier == "base"
    assert probe.applies_to_languages == ["javascript", "typescript"]
    assert probe.applies_to_tasks == ["*"]
    assert probe.requires == ["language_detection"]
    assert probe.timeout_seconds == 120
    assert probe.cache_strategy == "content"
    assert set(probe.declared_inputs) >= {"**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"}
    sig = inspect.signature(TreeSitterImportGraphProbe.run)
    assert list(sig.parameters) == ["self", "repo", "ctx"]


# ---------------------------------------------------------------------------
# T-02 — Kernel surface (AC-2): probe imports language_for + GrammarLoadRefused,
# does NOT redeclare the exception, does NOT touch tools/grammars.lock,
# does NOT import per-grammar PyPI packages directly.
# ---------------------------------------------------------------------------


def test_kernel_surface_imports_and_no_direct_grammar_access() -> None:
    src = Path(tsig.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    # (a) No GrammarLoadRefused class redeclared.
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            assert node.name != "GrammarLoadRefused", (
                "GrammarLoadRefused must be imported from the kernel, not redeclared"
            )

    # (b) No direct import of per-grammar PyPI packages.
    forbidden_imports = {
        "tree_sitter_typescript",
        "tree_sitter_javascript",
        "tree_sitter_python",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_imports, (
                    f"probe must not import {alias.name!r} directly; "
                    f"go through codegenie.grammars.lock.language_for"
                )
        if isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_imports, (
                f"probe must not import from {node.module!r} directly"
            )

    # (c) Kernel surface IS imported.
    kernel_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "codegenie.grammars.lock":
            kernel_names.update(alias.name for alias in node.names)
    assert "language_for" in kernel_names
    assert "GrammarLoadRefused" in kernel_names

    # (d) No tools/grammars.lock filesystem-string reference.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "tools/grammars" not in node.value, (
                f"probe must not reference tools/grammars path string: {node.value!r}"
            )
    # (e) No blake3 imports — kernel boundary is pip --require-hashes now.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "blake3", "probe must not import blake3"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "blake3", "probe must not import from blake3"


# ---------------------------------------------------------------------------
# T-03 — No parallelism imports (AC-4)
# ---------------------------------------------------------------------------


def test_no_parallelism_imports() -> None:
    src = Path(tsig.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden = {
        "threading",
        "concurrent",
        "concurrent.futures",
        "multiprocessing",
        "multiprocessing.pool",
        "asyncio.subprocess",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden, (
                    f"forbidden parallelism module imported: {alias.name!r}"
                )
        if isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden, (
                f"forbidden parallelism module imported via from: {node.module!r}"
            )


# ---------------------------------------------------------------------------
# T-04 — No threads spawned during run (AC-4, load-bearing)
# ---------------------------------------------------------------------------


def test_no_threads_created_during_run(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(b'import x from "lodash";\n')
    (repo_root / "b.ts").write_bytes(b'import { y } from "./utils";\n')

    threads_before = {t.ident for t in threading.enumerate()}
    _run(snapshot, ctx)
    threads_after = {t.ident for t in threading.enumerate()}

    new_threads = threads_after - threads_before
    upstream_owned = {
        t.ident
        for t in threading.enumerate()
        if t.ident in new_threads and "tree_sitter" in (t.name or "").lower()
    }
    assert (new_threads - upstream_owned) == set(), (
        f"probe created threads: {new_threads - upstream_owned}"
    )


# ---------------------------------------------------------------------------
# T-05 — Forbidden coordination primitives (AC-4)
# ---------------------------------------------------------------------------


def _resolve_call_name(node: ast.Call) -> str | None:
    """Return a dotted name for *node.func* if it's an Attribute or Name; else None."""
    parts: list[str] = []
    current: ast.expr = node.func
    while isinstance(current, ast.Attribute):
        parts.insert(0, current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.insert(0, current.id)
        return ".".join(parts)
    return None


def test_no_forbidden_coordination_primitives() -> None:
    src = Path(tsig.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden_calls = {
        "asyncio.gather",
        "asyncio.wait",
        "asyncio.as_completed",
        "asyncio.create_task",
        "asyncio.to_thread",
        "loop.run_in_executor",
        "loop.create_task",
    }
    wait_for_call_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            dotted = _resolve_call_name(node)
            if dotted is None:
                continue
            assert dotted not in forbidden_calls, f"forbidden coordination primitive: {dotted}"
            if dotted == "asyncio.wait_for":
                wait_for_call_count += 1
    assert wait_for_call_count == 1, (
        f"expected exactly one asyncio.wait_for call (the run() boundary); "
        f"found {wait_for_call_count}"
    )


# ---------------------------------------------------------------------------
# T-06 — Pure helper isolation (AC-PURE)
# ---------------------------------------------------------------------------


def test_extract_imports_is_pure(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_extract_imports`` is the functional core: in → out, no I/O.
    Monkeypatch ``Path.read_bytes`` to a sentinel so any filesystem touch
    raises (Rule 9: tests verify intent — the discipline is the contract)."""
    from codegenie.grammars.lock import language_for

    lang_ts = language_for("typescript")

    def _no_io(*_args: Any, **_kw: Any) -> bytes:
        raise AssertionError("filesystem touched from pure helper")

    monkeypatch.setattr(Path, "read_bytes", _no_io)

    src_bytes = b'import x from "lodash";\nimport "./bootstrap";\n'
    edges = _extract_imports(lang_ts, src_bytes, "src/index.ts")
    assert Edge(**{"from": "src/index.ts", "to": "lodash"}) in edges
    assert Edge(**{"from": "src/index.ts", "to": "./bootstrap"}) in edges


# ---------------------------------------------------------------------------
# T-07 — Forward-only adjacency shape (AC-5/AC-6/AC-7)
# ---------------------------------------------------------------------------


def test_forward_only_adjacency_shape(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "src").mkdir()
    (repo_root / "src" / "a.ts").write_bytes(
        b'import lodash from "lodash";\nimport { x } from "./utils";\n'
    )
    (repo_root / "src" / "b.ts").write_bytes(b'import React from "react";\n')

    out = _run(snapshot, ctx)
    artifact_path = ctx.output_dir / "raw" / "import-graph.json"
    assert artifact_path.is_file()

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    edges = payload["edges"]
    expected = [
        {"from": "src/a.ts", "to": "./utils"},
        {"from": "src/a.ts", "to": "lodash"},
        {"from": "src/b.ts", "to": "react"},
    ]
    assert edges == expected

    slice_ = out["schema_slice"]["import_graph"]
    assert slice_["files_with_imports"] == 2
    assert slice_["total_edges"] == 3
    assert slice_["parsed_files"] == 2
    assert slice_["failed_files"] == 0
    assert slice_["confidence"] == "high"
    assert slice_["import_graph_uri"] == ".codegenie/context/raw/import-graph.json"
    assert "typescript" in slice_["grammar_versions"]
    assert "javascript" in slice_["grammar_versions"]


# ---------------------------------------------------------------------------
# T-08 — ImportGraphArtifact well-formed (AC-6)
# ---------------------------------------------------------------------------


def test_import_graph_json_well_formed(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(b'import x from "lodash";\n')
    _run(snapshot, ctx)
    artifact_path = ctx.output_dir / "raw" / "import-graph.json"
    raw = artifact_path.read_text(encoding="utf-8")
    parsed = ImportGraphArtifact.model_validate_json(raw)
    assert parsed.schema_version == 1
    assert parsed.edges[0].from_path == "a.ts"
    assert parsed.edges[0].to == "lodash"


# ---------------------------------------------------------------------------
# T-09 — Edge model: alias, frozen, extra-forbid (AC-5)
# ---------------------------------------------------------------------------


def test_edge_model_alias_and_frozen() -> None:
    from pydantic import ValidationError

    edge = Edge(**{"from": "a.ts", "to": "lodash"})
    assert edge.model_dump(by_alias=True) == {"from": "a.ts", "to": "lodash"}
    with pytest.raises((TypeError, ValidationError)):
        edge.to = "react"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Edge(**{"from": "a.ts", "to": "lodash", "extra": "bad"})


# ---------------------------------------------------------------------------
# T-10 — Per-file parse failure is contained (AC-8)
# ---------------------------------------------------------------------------


def test_per_file_parse_failure_contained(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    """A file whose parse tree has errors increments ``failed_files`` and
    emits the canonical warning. ``run()`` does not raise."""
    (repo_root / "good.ts").write_bytes(b'import x from "lodash";\n')
    (repo_root / "bad.ts").write_bytes(b"function ( ; ; ; +++ ===  ((\n")

    out = _run(snapshot, ctx)
    slice_ = out["schema_slice"]["import_graph"]
    assert slice_["parsed_files"] == 1
    assert slice_["failed_files"] == 1
    assert "tree_sitter.file_parse_failed" in out["warnings"]


# ---------------------------------------------------------------------------
# T-11 — Very-large-file guard (AC-LARGE)
# ---------------------------------------------------------------------------


def test_file_too_large_skipped(repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext) -> None:
    huge = b"// real javascript\nimport x from 'lodash';\n" + b"x" * (_FILE_MAX_BYTES + 10)
    (repo_root / "huge.ts").write_bytes(huge)

    out = _run(snapshot, ctx)
    slice_ = out["schema_slice"]["import_graph"]
    assert slice_["failed_files"] == 1
    assert slice_["parsed_files"] == 0
    assert "tree_sitter.file_too_large" in out["warnings"]


# ---------------------------------------------------------------------------
# T-12 — Empty-repo guard (AC-9)
# ---------------------------------------------------------------------------


def test_no_files_to_parse_is_low_confidence(snapshot: RepoSnapshot, ctx: ProbeContext) -> None:
    out = _run(snapshot, ctx)
    slice_ = out["schema_slice"]["import_graph"]
    assert slice_["confidence"] == "low"
    assert "tree_sitter.no_files_to_parse" in out["warnings"]
    artifact_path = ctx.output_dir / "raw" / "import-graph.json"
    assert not artifact_path.exists()
    assert "import_graph_uri" not in slice_


# ---------------------------------------------------------------------------
# T-13 — GrammarLoadRefused → honest low-confidence slice (AC-3/AC-10)
# ---------------------------------------------------------------------------


def test_grammar_load_refused_full_slice(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    snapshot: RepoSnapshot,
    ctx: ProbeContext,
) -> None:
    (repo_root / "a.ts").write_bytes(b'import x from "never_reached";\n')

    def _refuse(name: str) -> Any:
        raise GrammarLoadRefused(f"forced refusal for {name!r}")

    monkeypatch.setattr("codegenie.probes.layer_b.tree_sitter_import_graph.language_for", _refuse)

    out = _run(snapshot, ctx)
    slice_ = out["schema_slice"]["import_graph"]
    assert slice_["confidence"] == "low"
    assert slice_["files_with_imports"] == 0
    assert slice_["total_edges"] == 0
    assert slice_["parsed_files"] == 0
    assert slice_["failed_files"] == 0
    assert "tree_sitter.grammar_pin_mismatch" in out["errors"]
    assert not (ctx.output_dir / "raw" / "import-graph.json").exists()
    assert "import_graph_uri" not in slice_
    assert "grammar_versions" not in slice_


def test_grammar_pin_mismatch_grammar_code_does_not_execute(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    snapshot: RepoSnapshot,
    ctx: ProbeContext,
) -> None:
    """Once ``language_for`` refuses, no ``Parser`` is constructed and no
    Query runs (Rule 9: encodes WHY of the pin)."""
    (repo_root / "a.ts").write_bytes(b'import x from "never";\n')

    def _refuse(name: str) -> Any:
        raise GrammarLoadRefused(f"refused {name!r}")

    monkeypatch.setattr("codegenie.probes.layer_b.tree_sitter_import_graph.language_for", _refuse)
    import tree_sitter

    sentinel = Mock(side_effect=AssertionError("Parser must not be constructed"))
    monkeypatch.setattr(tree_sitter, "Parser", sentinel)

    out = _run(snapshot, ctx)
    assert out["confidence"] == "low"
    sentinel.assert_not_called()


# ---------------------------------------------------------------------------
# T-14 — Warning/error IDs match ADR-0007 (AC-11)
# ---------------------------------------------------------------------------


def test_warning_error_ids_match_adr_0007() -> None:
    expected_ids = {
        "tree_sitter.grammar_pin_mismatch",
        "tree_sitter.file_parse_failed",
        "tree_sitter.parse_failed_count_exceeded",
        "tree_sitter.no_files_to_parse",
        "tree_sitter.file_too_large",
        "tree_sitter.timeout",
    }
    declared = _WARNING_IDS | _ERROR_IDS
    assert expected_ids <= declared
    for _id in declared:
        assert _ID_PATTERN.match(_id), f"ID does not match ADR-0007 pattern: {_id!r}"


# ---------------------------------------------------------------------------
# T-15 — Registry membership + dispatch filter (AC-13)
# ---------------------------------------------------------------------------


def test_registry_membership_heaviness_medium() -> None:
    classes = default_registry.all_probes()
    assert TreeSitterImportGraphProbe in classes

    entries = default_registry.sorted_for_dispatch()
    entry = next(e for e in entries if e.cls is TreeSitterImportGraphProbe)
    assert entry.heaviness == "medium"
    assert entry.runs_last is False

    ts_match = default_registry.for_task("*", frozenset({"typescript"}))
    js_match = default_registry.for_task("*", frozenset({"javascript"}))
    py_match = default_registry.for_task("*", frozenset({"python"}))
    assert TreeSitterImportGraphProbe in ts_match
    assert TreeSitterImportGraphProbe in js_match
    assert TreeSitterImportGraphProbe not in py_match


# ---------------------------------------------------------------------------
# T-16 — pyproject.toml: tree-sitter + grammars in [project.dependencies]
# (AC-14)
# ---------------------------------------------------------------------------


def test_pyproject_lists_tree_sitter_in_project_dependencies() -> None:
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps: list[str] = pyproject["project"]["dependencies"]
    optional_gather: list[str] = pyproject["project"]["optional-dependencies"]["gather"]

    def _has(pkg_prefix: str, dep_list: list[str]) -> bool:
        return any(d.startswith(pkg_prefix) for d in dep_list)

    assert _has("tree-sitter", deps), "tree-sitter must be in [project.dependencies]"
    assert _has("tree-sitter-typescript", deps), (
        "tree-sitter-typescript grammar must be in [project.dependencies]"
    )
    assert _has("tree-sitter-javascript", deps), (
        "tree-sitter-javascript grammar must be in [project.dependencies]"
    )
    assert not _has("tree-sitter", optional_gather), (
        "tree-sitter must NOT be in [project.optional-dependencies].gather "
        "(Phase 0 ADR-0006: gather extras intentionally empty)"
    )


# ---------------------------------------------------------------------------
# T-17 — Deterministic byte-identical artifact across two runs (AC-DET).
# ---------------------------------------------------------------------------


_specifier = st.sampled_from(
    ["lodash", "react", "@scope/pkg", "./utils", "../shared/foo", "fs-extra"]
)


@settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(specs=st.lists(_specifier, min_size=1, max_size=8, unique=True))
def test_two_runs_produce_byte_identical_artifact(
    specs: list[str], tmp_path_factory: pytest.TempPathFactory
) -> None:
    base = tmp_path_factory.mktemp("idempotent")
    body = b"".join(f'import x{i} from "{spec}";\n'.encode() for i, spec in enumerate(specs))
    (base / "a.ts").write_bytes(body)

    out_dir1 = base / "out1"
    out_dir2 = base / "out2"
    out_dir1.mkdir(parents=True)
    out_dir2.mkdir(parents=True)

    snap = RepoSnapshot(root=base, git_commit=None, detected_languages={"typescript": 1}, config={})

    def _ctx(out: Path) -> ProbeContext:
        return ProbeContext(
            cache_dir=base / "cache",
            output_dir=out,
            workspace=base / "ws",
            logger=logging.getLogger("idempotent"),
            config={},
        )

    asyncio.run(TreeSitterImportGraphProbe().run(snap, _ctx(out_dir1)))
    asyncio.run(TreeSitterImportGraphProbe().run(snap, _ctx(out_dir2)))

    a1 = (out_dir1 / "raw" / "import-graph.json").read_bytes()
    a2 = (out_dir2 / "raw" / "import-graph.json").read_bytes()
    assert a1 == a2, "deterministic-write discipline violated"


# ---------------------------------------------------------------------------
# T-18 — Atomic write discipline: no .tmp leftover (AC-DET)
# ---------------------------------------------------------------------------


def test_atomic_write_no_tmp_leftover(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(b'import x from "lodash";\n')
    _run(snapshot, ctx)
    raw_dir = ctx.output_dir / "raw"
    leftovers = list(raw_dir.glob("import-graph.json*.tmp"))
    assert leftovers == [], f"atomic-write discipline violated: {leftovers}"


# ---------------------------------------------------------------------------
# T-19 — Multiple import shapes (re-export, side-effect, require)
# ---------------------------------------------------------------------------


def test_multiple_import_shapes_extracted(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(
        b'import { x } from "lodash";\n'
        b'import "./bootstrap";\n'
        b'export { y } from "./re-export";\n'
        b'const m = require("commonjs-pkg");\n'
    )
    _run(snapshot, ctx)
    artifact = json.loads((ctx.output_dir / "raw" / "import-graph.json").read_text())
    tos = {e["to"] for e in artifact["edges"]}
    assert {"lodash", "./bootstrap", "./re-export", "commonjs-pkg"} <= tos


# ---------------------------------------------------------------------------
# T-20 — Dynamic non-literal import is omitted (AC-5)
# ---------------------------------------------------------------------------


def test_dynamic_non_literal_import_omitted(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(
        b'const spec = "foo";\nconst m = import(spec);\nimport "lit-literal";\n'
    )
    _run(snapshot, ctx)
    artifact = json.loads((ctx.output_dir / "raw" / "import-graph.json").read_text())
    tos = {e["to"] for e in artifact["edges"]}
    assert "lit-literal" in tos
    assert "<dynamic>" not in tos
    assert "spec" not in tos


# ---------------------------------------------------------------------------
# T-21 — Excluded directories never scanned (AC-INDEXABLE)
# ---------------------------------------------------------------------------


def test_excluded_dirs_not_scanned(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    """node_modules / dist / build / .git are not scanned."""
    for excluded in ("node_modules", "dist", "build", ".git"):
        d = repo_root / excluded
        d.mkdir()
        (d / "junk.ts").write_bytes(b'import x from "should_not_appear";\n')
    (repo_root / "src.ts").write_bytes(b'import x from "real_dep";\n')

    _run(snapshot, ctx)
    artifact = json.loads((ctx.output_dir / "raw" / "import-graph.json").read_text())
    tos = {e["to"] for e in artifact["edges"]}
    assert "real_dep" in tos
    assert "should_not_appear" not in tos


# ---------------------------------------------------------------------------
# T-22 — TSX grammar is used for .tsx files
# ---------------------------------------------------------------------------


def test_tsx_files_parsed_with_tsx_grammar(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    """JSX syntax in a ``.tsx`` file must not break parsing — the tsx
    grammar is what makes that work."""
    (repo_root / "comp.tsx").write_bytes(b'import React from "react";\nconst el = <div>hi</div>;\n')
    out = _run(snapshot, ctx)
    slice_ = out["schema_slice"]["import_graph"]
    assert slice_["parsed_files"] == 1
    assert slice_["failed_files"] == 0
    assert slice_["total_edges"] == 1
