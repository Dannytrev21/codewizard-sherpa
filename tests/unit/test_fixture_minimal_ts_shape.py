"""Shape test for ``tests/fixtures/portfolio/minimal-ts/`` (S7-01).

Consumes the shared shape-test kernel at
``tests/fixtures/_shape_test_kernel.py`` (S7-02 AC-24). This consumer
declares only ``_FIXTURE`` + ``_FILE_SPECS`` + content predicates;
the parametrize machinery + closed-set + line-ending helpers live in
the kernel.

Implements AC-1..AC-10 + AC-25..AC-30 + AC-37 from
``docs/phases/02-context-gather-layers-b-g/stories/S7-01-fixtures-batch-one.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.fixtures._shape_test_kernel import (
    _FORBIDDEN_SUBPATHS,
    _FileSpec,
    assert_file_content_invariants,
    assert_file_exists,
    assert_file_line_endings,
    assert_file_parses,
    assert_no_forbidden_subpath,
    assert_readme_references_every_spec,
    assert_tree_is_closed_set,
)

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "minimal-ts"


# --- Pure content predicates --------------------------------------------------


def _pkg_declares_express(pkg: dict[str, Any]) -> None:
    assert pkg.get("name") == "minimal-ts"
    assert pkg.get("version") == "0.0.1"
    assert pkg.get("dependencies", {}).get("express") == "^4.18.2"
    assert pkg.get("devDependencies", {}).get("typescript") == "^5.3.0"
    assert pkg.get("devDependencies", {}).get("vitest") == "^1.0.0"
    assert pkg.get("engines", {}).get("node") == ">=20.0.0"
    scripts = pkg.get("scripts", {})
    assert scripts.get("build") == "tsc -p ."
    assert scripts.get("test") == "vitest run"
    assert scripts.get("start") == "node dist/index.js"


def _pnpm_lock_header(lock: dict[str, Any]) -> None:
    assert lock.get("lockfileVersion") == "6.0"


def _tsconfig_shape(ts: dict[str, Any]) -> None:
    co = ts.get("compilerOptions", {})
    assert co.get("target") == "ES2022"
    assert co.get("module") == "ESNext"
    assert co.get("strict") is True


def _tsconfig_has_both_comment_styles(raw_bytes: bytes) -> None:
    text = raw_bytes.decode("utf-8")
    assert "//" in text, "tsconfig.json must contain at least one // line comment"
    assert "/*" in text and "*/" in text, (
        "tsconfig.json must contain at least one /* */ block comment"
    )


def _nvmrc_exact(raw_bytes: bytes) -> None:
    assert raw_bytes == b"v20.11.0\n", f".nvmrc must be exactly b'v20.11.0\\n', got {raw_bytes!r}"


def _index_ts_imports_express(raw_bytes: bytes) -> None:
    text = raw_bytes.decode("utf-8")
    assert 'import express from "express"' in text
    assert "server.listen(3000)" in text


def _ci_single_build_job(workflow: dict[str, Any]) -> None:
    jobs = workflow.get("jobs", {})
    assert set(jobs.keys()) == {"build"}, (
        f"expected exactly one job named 'build', got {set(jobs.keys())}"
    )
    steps = jobs["build"].get("steps", [])
    runs = [s.get("run") for s in steps if "run" in s]
    assert "pnpm install && pnpm test" in runs


def _dockerfile_single_stage(raw_bytes: bytes) -> None:
    text = raw_bytes.decode("utf-8")
    from_lines = [line for line in text.splitlines() if line.startswith("FROM ")]
    assert len(from_lines) == 1, f"minimal-ts/Dockerfile must be single-stage, got {from_lines}"
    assert "FROM node:20-slim" in text
    assert "USER node" in text
    assert "EXPOSE 3000" in text
    assert 'CMD ["node", "dist/index.js"]' in text


def _chart_apiversion_v2(chart: dict[str, Any]) -> None:
    assert chart.get("apiVersion") == "v2"
    assert chart.get("name") == "minimal-ts"
    assert chart.get("version") == "0.0.1"


def _values_image(values: dict[str, Any]) -> None:
    img = values.get("image", {})
    assert img.get("repository") == "ghcr.io/example/minimal-ts"
    assert img.get("tag") == "0.0.1"


def _values_prod_image_override(values: dict[str, Any]) -> None:
    assert values.get("image", {}).get("tag") == "prod-0.0.1"


# --- The single source of truth -----------------------------------------------

_FILE_SPECS: tuple[_FileSpec, ...] = (
    _FileSpec(
        "package.json",
        ("language_detection", "node_build_system", "node_manifest", "test_inventory"),
        "safe_json",
        (_pkg_declares_express,),
    ),
    _FileSpec(
        "pnpm-lock.yaml",
        ("node_build_system", "node_manifest", "dep_graph"),
        "safe_yaml",
        (_pnpm_lock_header,),
    ),
    _FileSpec(
        "tsconfig.json",
        ("node_build_system",),
        "jsonc",
        (_tsconfig_shape,),
    ),
    _FileSpec(".nvmrc", ("node_build_system",), "text", (_nvmrc_exact,)),
    _FileSpec(
        "src/index.ts",
        ("language_detection",),
        "text",
        (_index_ts_imports_express,),
    ),
    _FileSpec(
        ".github/workflows/ci.yml",
        ("ci",),
        "safe_yaml",
        (_ci_single_build_job,),
    ),
    _FileSpec(
        "Dockerfile",
        (
            "dockerfile",
            "entrypoint",
            "shell_usage",
            "certificate",
            "runtime_trace",
            "sbom",
            "cve",
        ),
        "text",
        (_dockerfile_single_stage,),
    ),
    _FileSpec(
        "deploy/chart/Chart.yaml",
        ("deployment",),
        "safe_yaml",
        (_chart_apiversion_v2,),
    ),
    _FileSpec(
        "deploy/chart/values.yaml",
        ("deployment",),
        "safe_yaml",
        (_values_image,),
    ),
    _FileSpec(
        "deploy/chart/values-prod.yaml",
        ("deployment",),
        "safe_yaml",
        (_values_prod_image_override,),
    ),
    _FileSpec("README.md", (), "text", ()),
    _FileSpec("regenerate.sh", (), "text", ()),
    _FileSpec(".gitignore", (), "text", ()),
)


# --- Parametrize wrappers (delegate to kernel helpers) ------------------------


def test_fixture_directory_exists() -> None:
    """AC-1 — fixture directory exists."""
    assert _FIXTURE.is_dir()


def test_fixture_file_count_under_200() -> None:
    """AC-1 — file count <= 200."""
    count = sum(1 for p in _FIXTURE.rglob("*") if p.is_file())
    assert count <= 200, f"minimal-ts/ has {count} files; limit is 200"


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_exists(spec: _FileSpec) -> None:
    assert_file_exists(_FIXTURE, spec)


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_parses(spec: _FileSpec) -> None:
    assert_file_parses(_FIXTURE, spec)


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_content_invariants(spec: _FileSpec) -> None:
    assert_file_content_invariants(_FIXTURE, spec)


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_line_endings(spec: _FileSpec) -> None:
    assert_file_line_endings(_FIXTURE, spec)


def test_tsconfig_has_both_comment_styles() -> None:
    """AC-4 — JSONC with at least one // and one /* */ comment."""
    _tsconfig_has_both_comment_styles((_FIXTURE / "tsconfig.json").read_bytes())


@pytest.mark.parametrize("forbidden", _FORBIDDEN_SUBPATHS)
def test_no_forbidden_subpaths(forbidden: str) -> None:
    """AC-27 — forbidden subpaths absent."""
    assert_no_forbidden_subpath(_FIXTURE, forbidden)


def test_fixture_tree_is_closed_set() -> None:
    """AC-26 — tracked-files set == _FILE_SPECS relpath set."""
    assert_tree_is_closed_set(_FIXTURE, _FILE_SPECS)


def test_readme_references_every_spec() -> None:
    """AC-29 — README mentions every spec.relpath and every consumer probe."""
    assert_readme_references_every_spec(_FIXTURE, _FILE_SPECS)
