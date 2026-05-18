"""Shape test for ``tests/fixtures/portfolio/monorepo-pnpm/`` (S7-02).

Consumes the shared shape-test kernel at
``tests/fixtures/_shape_test_kernel.py`` (S7-02 AC-24). The kernel
owns: the ``_FileSpec`` NamedTuple, the ``_ProbeName`` Literal, the
parser-dispatch chokepoint, the parametrize-friendly flat assertion
helpers, and the single call site for ``git ls-files``.

This consumer declares only:

- ``_FIXTURE`` — the fixture path
- ``_FILE_SPECS`` — the closed-set tracked-files list with per-file
  consumers and content predicates
- pure content predicates (each independently unit-testable)
- thin parametrize wrappers that delegate to the kernel helpers

Implements AC-1..AC-14 + AC-27 + AC-30..AC-31 from S7-02.
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

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "monorepo-pnpm"


# --- Pure content predicates --------------------------------------------------


def _workspace_declares_packages(workspace: dict[str, Any]) -> None:
    """AC-2 — pnpm-workspace.yaml declares packages glob."""
    assert workspace.get("packages") == ["packages/*"], (
        f"pnpm-workspace.yaml must declare packages: ['packages/*']; got {workspace!r}"
    )


def _root_pkg_shape(pkg: dict[str, Any]) -> None:
    """AC-3 — root package.json shape."""
    assert pkg.get("name") == "monorepo-pnpm-fixture"
    assert pkg.get("private") is True
    assert pkg.get("workspaces") == ["packages/*"]
    assert pkg.get("devDependencies", {}).get("typescript") == "^5.3.0"
    assert "dependencies" not in pkg, (
        "root package.json must not declare root dependencies (workspaces own deps)"
    )


def _lib_a_pkg_shape(pkg: dict[str, Any]) -> None:
    """AC-4 — packages/lib-a/package.json shape; no dependencies."""
    assert pkg.get("name") == "@monorepo-pnpm/lib-a"
    assert pkg.get("version") == "0.0.1"
    assert pkg.get("main") == "src/index.ts"
    assert "dependencies" not in pkg, (
        "lib-a must have no dependencies (it's the leaf of the workspace graph)"
    )


def _lib_a_exports_add(raw_bytes: bytes) -> None:
    """AC-5 — lib-a exports add(a, b)."""
    text = raw_bytes.decode("utf-8")
    assert "export function add" in text, "lib-a/src/index.ts must export `add`"
    assert "number" in text, "lib-a's add must be typed"


def _lib_b_pkg_shape(pkg: dict[str, Any]) -> None:
    """AC-6 — packages/lib-b/package.json shape."""
    assert pkg.get("name") == "@monorepo-pnpm/lib-b"
    assert pkg.get("version") == "0.0.1"
    assert pkg.get("main") == "src/index.ts"


def _lib_b_declares_workspace_dep_on_lib_a(pkg: dict[str, Any]) -> None:
    """AC-6 — lib-b depends on lib-a via workspace:*."""
    deps = pkg.get("dependencies", {})
    assert deps.get("@monorepo-pnpm/lib-a") == "workspace:*", (
        f"lib-b must declare lib-a via workspace:* protocol; got dependencies={deps!r}"
    )


def _lib_b_imports_from_lib_a(raw_bytes: bytes) -> None:
    """AC-7 — lib-b imports from @monorepo-pnpm/lib-a."""
    text = raw_bytes.decode("utf-8")
    assert 'from "@monorepo-pnpm/lib-a"' in text, (
        "lib-b/src/index.ts must import from @monorepo-pnpm/lib-a — the load-bearing edge "
        "tree_sitter_import_graph records"
    )


def _app_pkg_shape(pkg: dict[str, Any]) -> None:
    """AC-8 — packages/app/package.json shape."""
    assert pkg.get("name") == "@monorepo-pnpm/app"
    assert pkg.get("version") == "0.0.1"
    assert pkg.get("main") == "src/index.ts"


def _app_declares_workspace_deps_on_both_libs(pkg: dict[str, Any]) -> None:
    """AC-8 — app depends on both libs via workspace:* + express."""
    deps = pkg.get("dependencies", {})
    assert deps.get("@monorepo-pnpm/lib-a") == "workspace:*", (
        f"app must declare lib-a via workspace:*; got {deps!r}"
    )
    assert deps.get("@monorepo-pnpm/lib-b") == "workspace:*", (
        f"app must declare lib-b via workspace:*; got {deps!r}"
    )
    assert deps.get("express") == "^4.18.2", f"app must depend on express@^4.18.2; got {deps!r}"


def _app_imports_from_both_libs(raw_bytes: bytes) -> None:
    """AC-9 — app imports from both libs + express."""
    text = raw_bytes.decode("utf-8")
    assert 'from "@monorepo-pnpm/lib-a"' in text, (
        "app must import from lib-a — load-bearing for tree_sitter_import_graph"
    )
    assert 'from "@monorepo-pnpm/lib-b"' in text, (
        "app must import from lib-b — load-bearing for tree_sitter_import_graph"
    )
    assert "express" in text, "app must import express"


def _lock_v6_header(lock: dict[str, Any]) -> None:
    """AC-10 — pnpm-lock.yaml has lockfileVersion '6.0'."""
    assert lock.get("lockfileVersion") == "6.0", (
        f"pnpm-lock.yaml must be lockfileVersion '6.0' (hand-authored bytes; "
        f"pnpm is NOT in ALLOWED_BINARIES); got {lock.get('lockfileVersion')!r}"
    )


def _lock_resolves_workspace_packages(lock: dict[str, Any]) -> None:
    """AC-10 — lockfile resolves all three workspace packages."""
    importers = lock.get("importers", {})
    for pkg in ("packages/app", "packages/lib-a", "packages/lib-b"):
        assert pkg in importers, (
            f"pnpm-lock.yaml importers must include {pkg!r}; got keys={list(importers)!r}"
        )


def _npmrc_ignore_scripts(raw_bytes: bytes) -> None:
    """Defense-in-depth — .npmrc pins ignore-scripts=true."""
    assert raw_bytes == b"ignore-scripts=true\n", (
        f".npmrc must be exactly b'ignore-scripts=true\\n'; got {raw_bytes!r}"
    )


def _tsconfig_root_references_all_three(ts: dict[str, Any]) -> None:
    """AC-11 — root tsconfig has TS project-references for all three packages."""
    refs = ts.get("references", [])
    paths = {r.get("path") for r in refs if isinstance(r, dict)}
    assert paths == {"packages/lib-a", "packages/lib-b", "packages/app"}, (
        f"root tsconfig.json must reference all three packages; got {paths!r}"
    )


def _tsconfig_strict_es2022(ts: dict[str, Any]) -> None:
    """Per-package tsconfig — strict, ES2022, composite."""
    co = ts.get("compilerOptions", {})
    assert co.get("target") == "ES2022"
    assert co.get("strict") is True
    assert co.get("composite") is True


def _dockerfile_multistage(raw_bytes: bytes) -> None:
    """AC-12 — multi-stage Dockerfile."""
    text = raw_bytes.decode("utf-8")
    from_lines = [line for line in text.splitlines() if line.startswith("FROM ")]
    assert len(from_lines) >= 2, f"Dockerfile must be multi-stage (>= 2 FROM); got {from_lines!r}"


def _dockerfile_uses_node_slim(raw_bytes: bytes) -> None:
    """AC-12 — uses node:20-slim base."""
    text = raw_bytes.decode("utf-8")
    assert "node:20-slim" in text, "Dockerfile must use node:20-slim"


def _dockerfile_runs_as_node_user(raw_bytes: bytes) -> None:
    """AC-12 — USER node + final CMD."""
    text = raw_bytes.decode("utf-8")
    assert "USER node" in text
    assert 'CMD ["node", "packages/app/dist/index.js"]' in text


def _ci_runs_recursive_build(workflow: dict[str, Any]) -> None:
    """AC-13 — single `build` job with recursive pnpm build/test."""
    jobs = workflow.get("jobs", {})
    assert "build" in jobs, f"CI workflow must declare a `build` job; got {list(jobs)!r}"
    steps = jobs["build"].get("steps", [])
    runs = [s.get("run") for s in steps if "run" in s]
    joined = " ".join(r for r in runs if r)
    assert "pnpm install --frozen-lockfile" in joined
    assert "pnpm -r build" in joined
    assert "pnpm -r test" in joined


def _readme_documents_phase3_entry_gate_target(raw_bytes: bytes) -> None:
    """AC-14 — README names Phase 3 entry-gate target (Risk #8 handoff)."""
    text = raw_bytes.decode("utf-8")
    assert "Phase 3 entry-gate target" in text, (
        "monorepo-pnpm/README.md must explicitly name Phase 3 entry-gate target — "
        "the Risk-#8 named handoff in S7-02"
    )


# --- The single source of truth (closed set; AC-27) ---------------------------

_FILE_SPECS: tuple[_FileSpec, ...] = (
    _FileSpec(
        "pnpm-workspace.yaml",
        ("node_build_system", "dep_graph"),
        "safe_yaml",
        (_workspace_declares_packages,),
    ),
    _FileSpec(
        "package.json",
        ("node_build_system", "node_manifest"),
        "safe_json",
        (_root_pkg_shape,),
    ),
    _FileSpec(
        "packages/lib-a/package.json",
        ("node_manifest", "dep_graph"),
        "safe_json",
        (_lib_a_pkg_shape,),
    ),
    _FileSpec(
        "packages/lib-a/src/index.ts",
        ("language_detection", "tree_sitter_import_graph"),
        "text",
        (_lib_a_exports_add,),
    ),
    _FileSpec(
        "packages/lib-b/package.json",
        ("node_manifest", "dep_graph"),
        "safe_json",
        (_lib_b_pkg_shape, _lib_b_declares_workspace_dep_on_lib_a),
    ),
    _FileSpec(
        "packages/lib-b/src/index.ts",
        ("language_detection", "tree_sitter_import_graph"),
        "text",
        (_lib_b_imports_from_lib_a,),
    ),
    _FileSpec(
        "packages/app/package.json",
        ("node_manifest", "dep_graph"),
        "safe_json",
        (_app_pkg_shape, _app_declares_workspace_deps_on_both_libs),
    ),
    _FileSpec(
        "packages/app/src/index.ts",
        ("language_detection", "tree_sitter_import_graph"),
        "text",
        (_app_imports_from_both_libs,),
    ),
    _FileSpec(
        "pnpm-lock.yaml",
        ("node_build_system", "node_manifest", "dep_graph"),
        "safe_yaml",
        (_lock_v6_header, _lock_resolves_workspace_packages),
    ),
    _FileSpec(".npmrc", ("node_manifest",), "text", (_npmrc_ignore_scripts,)),
    _FileSpec(
        "tsconfig.json",
        ("node_build_system",),
        "jsonc",
        (_tsconfig_root_references_all_three,),
    ),
    _FileSpec(
        "packages/lib-a/tsconfig.json",
        ("node_build_system",),
        "jsonc",
        (_tsconfig_strict_es2022,),
    ),
    _FileSpec(
        "packages/lib-b/tsconfig.json",
        ("node_build_system",),
        "jsonc",
        (_tsconfig_strict_es2022,),
    ),
    _FileSpec(
        "packages/app/tsconfig.json",
        ("node_build_system",),
        "jsonc",
        (_tsconfig_strict_es2022,),
    ),
    _FileSpec(
        "Dockerfile",
        ("dockerfile", "runtime_trace", "entrypoint"),
        "text",
        (_dockerfile_multistage, _dockerfile_uses_node_slim, _dockerfile_runs_as_node_user),
    ),
    _FileSpec(
        ".github/workflows/ci.yml",
        ("ci",),
        "safe_yaml",
        (_ci_runs_recursive_build,),
    ),
    _FileSpec("README.md", (), "text", (_readme_documents_phase3_entry_gate_target,)),
    _FileSpec("regenerate.sh", (), "text", ()),
    _FileSpec(".gitignore", (), "text", ()),
)


# --- Parametrize wrappers (delegate to kernel helpers) ------------------------


def test_fixture_directory_exists() -> None:
    """AC-1 — fixture directory exists."""
    assert _FIXTURE.is_dir()


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


@pytest.mark.parametrize("forbidden", _FORBIDDEN_SUBPATHS)
def test_no_forbidden_subpaths(forbidden: str) -> None:
    """AC-27 — node_modules/, .codegenie/, dist/, etc. are absent."""
    assert_no_forbidden_subpath(_FIXTURE, forbidden)


def test_fixture_tree_is_closed_set() -> None:
    """AC-27 — tracked-files set == _FILE_SPECS relpath set."""
    assert_tree_is_closed_set(_FIXTURE, _FILE_SPECS)


def test_readme_references_every_spec() -> None:
    """README mentions every relpath + every consumer probe."""
    assert_readme_references_every_spec(_FIXTURE, _FILE_SPECS)
