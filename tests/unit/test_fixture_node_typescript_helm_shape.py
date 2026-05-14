"""Shape test for ``tests/fixtures/node_typescript_helm/`` — the Phase-1 canonical fixture.

``_FILE_SPECS`` is the single source of truth for which files the fixture
contains, which probes consume each, and which content invariants each file
must satisfy. Adding a fixture file: one :class:`_FileSpec` entry insertion
+ zero edits to the parametrized test bodies. The same ``Literal[...]``
``_ProbeName`` closed set is enforced both at ``mypy --strict``
(typo-resistance) AND at runtime (AC-18).

This file implements the AC battery from
``docs/phases/01-context-gather-layer-a-node/stories/S2-03-fixture-node-typescript-helm.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, NamedTuple, get_args

import pytest

from codegenie.parsers import jsonc, safe_json, safe_yaml

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "node_typescript_helm"

_ProbeName = Literal[
    "language_detection",
    "node_build_system",
    "node_manifest",
    "ci",
    "deployment",
    "test_inventory",
]

_ParserKind = Literal["safe_json", "safe_yaml", "jsonc", "text"]


class _FileSpec(NamedTuple):
    relpath: str
    consumers: tuple[_ProbeName, ...]
    parser: _ParserKind | None
    content_checks: tuple[Callable[[Any], None], ...]


# --- Pure content predicates (each independently unit-testable) -----------------


def _pkg_declares_express(pkg: dict[str, Any]) -> None:
    assert pkg.get("name") == "node-typescript-helm"
    assert pkg.get("version") == "0.0.1"
    assert pkg.get("dependencies", {}).get("express") == "^4.18.2"
    assert pkg.get("devDependencies", {}).get("typescript") == "^5.3.0"
    assert pkg.get("devDependencies", {}).get("vitest") == "^1.0.0"
    assert pkg.get("engines", {}).get("node") == ">=20.0.0"
    scripts = pkg.get("scripts", {})
    assert scripts.get("build") == "tsc -p ."
    assert scripts.get("test") == "vitest run"
    assert scripts.get("start") == "node dist/index.js"


def _pkg_omits_package_manager(pkg: dict[str, Any]) -> None:
    # AC-2c — must be absent, not None.
    assert "packageManager" not in pkg, (
        "`packageManager` field would trip the S2-02 "
        "package_manager.declaration_lockfile_disagree path and dirty the "
        "S6-01 golden; this fixture must stay in the silent-agree-by-absence regime"
    )


def _pnpm_lock_header(lock: dict[str, Any]) -> None:
    assert lock.get("lockfileVersion") == "6.0"


def _tsconfig_shape(ts: dict[str, Any]) -> None:
    co = ts.get("compilerOptions", {})
    assert co.get("target") == "ES2022"
    assert co.get("module") == "ESNext"
    assert co.get("strict") is True
    assert "extends" not in ts


def _tsconfig_has_both_comment_styles(raw_bytes: bytes) -> None:
    # AC-4b — exercises jsonc.py's state machine on the warm path.
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


def _ci_single_build_job(workflow: dict[str, Any]) -> None:
    jobs = workflow.get("jobs", {})
    assert set(jobs.keys()) == {"build"}, (
        f"expected exactly one job named 'build', got {set(jobs.keys())}"
    )
    steps = jobs["build"].get("steps", [])
    runs = [s.get("run") for s in steps if "run" in s]
    assert "pnpm install && pnpm test" in runs


def _chart_apiversion_v2(chart: dict[str, Any]) -> None:
    assert chart.get("apiVersion") == "v2"
    assert chart.get("name") == "node-typescript-helm"
    assert chart.get("version") == "0.0.1"


def _values_image(values: dict[str, Any]) -> None:
    img = values.get("image", {})
    assert img.get("repository") == "ghcr.io/example/node-typescript-helm"
    assert img.get("tag") == "0.0.1"


def _values_prod_image_override(values: dict[str, Any]) -> None:
    assert values.get("image", {}).get("tag") == "prod-0.0.1"


# --- The single source of truth -------------------------------------------------

_FILE_SPECS: tuple[_FileSpec, ...] = (
    _FileSpec(
        "package.json",
        ("language_detection", "node_build_system", "node_manifest", "test_inventory"),
        "safe_json",
        (_pkg_declares_express, _pkg_omits_package_manager),
    ),
    _FileSpec(
        "pnpm-lock.yaml",
        ("node_build_system", "node_manifest"),
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
    # README is documented by AC-17's separate test; consumers tuple is
    # intentionally empty because the README documents the others.
    _FileSpec("README.md", (), "text", ()),
)


# --- Tests parametrized over _FILE_SPECS ----------------------------------------


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_exists(spec: _FileSpec) -> None:
    """AC-1, AC-16(a) — every spec'd file is present."""
    assert (_FIXTURE / spec.relpath).is_file(), f"missing: {spec.relpath}"


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_parses(spec: _FileSpec) -> None:
    """AC-2b/AC-3/AC-4c/AC-7/AC-8/AC-9/AC-10, AC-16(b) — parses cleanly."""
    if spec.parser is None or spec.parser == "text":
        return
    path = _FIXTURE / spec.relpath
    if spec.parser == "safe_json":
        safe_json.load(path, max_bytes=50 * 1024 * 1024)
    elif spec.parser == "safe_yaml":
        safe_yaml.load(path, max_bytes=50 * 1024 * 1024)
    elif spec.parser == "jsonc":
        jsonc.load(path, max_bytes=10 * 1024 * 1024)


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_content_invariants(spec: _FileSpec) -> None:
    """AC-2a/AC-4a/AC-5/AC-6/AC-7/AC-8/AC-9/AC-10, AC-16(c) — content_checks pass."""
    if not spec.content_checks:
        return
    path = _FIXTURE / spec.relpath
    payload: Any
    if spec.parser == "text" or spec.parser is None:
        payload = path.read_bytes()
    elif spec.parser == "safe_json":
        payload = safe_json.load(path, max_bytes=50 * 1024 * 1024)
    elif spec.parser == "safe_yaml":
        payload = safe_yaml.load(path, max_bytes=50 * 1024 * 1024)
    elif spec.parser == "jsonc":
        payload = jsonc.load(path, max_bytes=10 * 1024 * 1024)
    for check in spec.content_checks:
        check(payload)


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_line_endings(spec: _FileSpec) -> None:
    """AC-19 — LF endings, no CRLF, trailing newline on text-like files."""
    raw = (_FIXTURE / spec.relpath).read_bytes()
    assert b"\r" not in raw, f"{spec.relpath} contains CR — must be LF-only"
    assert raw.endswith(b"\n"), f"{spec.relpath} must end with LF"


# --- AC-4b: tsconfig.json has both comment styles --------------------------------


def test_tsconfig_has_both_comment_styles() -> None:
    _tsconfig_has_both_comment_styles((_FIXTURE / "tsconfig.json").read_bytes())


# --- AC-13: forbidden subpaths absent -------------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    ["node_modules", ".codegenie", ".gitignore", "dist", "coverage"],
)
def test_no_forbidden_subpaths(forbidden: str) -> None:
    assert not (_FIXTURE / forbidden).exists(), (
        f"{forbidden!r} must not exist in this fixture — would either pollute "
        f"the golden or break test isolation"
    )


# --- AC-14: closed-set complement ------------------------------------------------

_FIXTURE_NOISE_NAMES = frozenset({"__pycache__", ".pytest_cache", ".DS_Store"})


def _enumerate_tracked(root: Path) -> set[str]:
    out: set[str] = set()
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        parts = p.relative_to(root).parts
        if any(part in _FIXTURE_NOISE_NAMES or part.startswith(".pytest") for part in parts):
            continue
        out.add(str(p.relative_to(root)))
    return out


def test_fixture_tree_is_closed_set() -> None:
    """AC-14 — REQUIRED_FILES is exhaustive. A stray file fails before it can
    dirty the S6-01 golden silently."""
    expected = {spec.relpath for spec in _FILE_SPECS}
    actual = _enumerate_tracked(_FIXTURE)
    extra = actual - expected
    missing = expected - actual
    assert not extra and not missing, (
        f"extra files: {sorted(extra)}; missing files: {sorted(missing)}"
    )


# --- AC-17: README references every spec.relpath + every consumer ----------------


def test_readme_references_every_spec() -> None:
    readme_text = (_FIXTURE / "README.md").read_text(encoding="utf-8")
    for spec in _FILE_SPECS:
        if spec.relpath == "README.md":
            continue
        assert spec.relpath in readme_text, f"README missing reference to {spec.relpath}"
        for consumer in spec.consumers:
            assert consumer in readme_text, (
                f"README missing consumer {consumer!r} for {spec.relpath}"
            )


# --- AC-18: _ProbeName Literal is the Phase-1 closed set -------------------------


def test_probe_name_literal_matches_phase_1_closed_set() -> None:
    assert set(get_args(_ProbeName)) == {
        "language_detection",
        "node_build_system",
        "node_manifest",
        "ci",
        "deployment",
        "test_inventory",
    }


# --- AC-12: no fixture file byte-identical to a production source -----------------


def test_fixture_bytes_not_copied_from_production_sources() -> None:
    """AC-12 — defensive: a fixture file must not duplicate src/codegenie/*
    bytes."""
    src_root = Path(__file__).parent.parent.parent / "src" / "codegenie"
    production_hashes: dict[bytes, Path] = {}
    if src_root.exists():
        for p in src_root.rglob("*.py"):
            production_hashes[p.read_bytes()] = p
    for spec in _FILE_SPECS:
        fixture_bytes = (_FIXTURE / spec.relpath).read_bytes()
        assert fixture_bytes not in production_hashes, (
            f"{spec.relpath} is byte-identical to "
            f"{production_hashes.get(fixture_bytes)} — fixtures must be "
            f"self-contained"
        )
