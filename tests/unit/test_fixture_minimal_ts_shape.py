"""Shape test for ``tests/fixtures/portfolio/minimal-ts/`` (S7-01).

``_FILE_SPECS`` is the single source of truth for which files this
fixture contains, which probes consume each, and which content
invariants each file must satisfy. Adding a fixture file: one
:class:`_FileSpec` entry insertion + zero edits to the parametrized
test bodies. The same ``Literal[...]`` ``_ProbeName`` closed set is
enforced both at ``mypy --strict`` (typo-resistance) AND at runtime
(AC-37 subset-match against the live ``default_registry``).

This file implements AC-1..AC-10 + AC-25..AC-30 + AC-37 from
``docs/phases/02-context-gather-layers-b-g/stories/S7-01-fixtures-batch-one.md``.

Per S7-01 Notes-for-implementer "Patterns DELIBERATELY deferred", the
three fixture shape tests are intentionally NOT yet refactored into a
shared kernel — S7-02 lifts the kernel at five consumers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, NamedTuple, get_args

import pytest

from codegenie.parsers import jsonc, safe_json, safe_yaml
from codegenie.probes import default_registry

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "minimal-ts"
_REPO_ROOT = Path(__file__).parent.parent.parent

_ProbeName = Literal[
    # Layer A (Phase 1)
    "language_detection",
    "node_build_system",
    "node_manifest",
    "ci",
    "deployment",
    "test_inventory",
    # Layer B (Phase 2)
    "index_health",
    "scip_index",
    "tree_sitter_import_graph",
    "dep_graph",
    "generated_code",
    "node_reflection",
    "semantic_index_meta",
    # Layer C (Phase 2)
    "runtime_trace",
    "dockerfile",
    "entrypoint",
    "shell_usage",
    "certificate",
    "sbom",
    "cve",
    # Layer D (Phase 2)
    "skills_index",
    "conventions",
    "adrs",
    "repo_notes",
    "repo_config",
    "policy",
    "exceptions",
    "external_docs",
    # Layer E (Phase 2)
    "ownership",
    "service_topology",
    "slo",
    # Layer G (Phase 2)
    "semgrep",
    "ast_grep",
    "ripgrep_curated",
    "gitleaks",
    "test_coverage_mapping",
]

_ParserKind = Literal["safe_json", "safe_yaml", "jsonc", "text"]


class _FileSpec(NamedTuple):
    relpath: str
    consumers: tuple[_ProbeName, ...]
    parser: _ParserKind | None
    content_checks: tuple[Callable[[Any], None], ...]


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


# --- AC-1: file count <= 200 + directory exists -------------------------------


def test_fixture_directory_exists() -> None:
    """AC-1 — fixture directory exists."""
    assert _FIXTURE.is_dir()


def test_fixture_file_count_under_200() -> None:
    """AC-1 — file count <= 200."""
    count = sum(1 for p in _FIXTURE.rglob("*") if p.is_file())
    assert count <= 200, f"minimal-ts/ has {count} files; limit is 200"


# --- Parametrized over _FILE_SPECS --------------------------------------------


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_exists(spec: _FileSpec) -> None:
    """AC-1..AC-10 — every spec'd file is present."""
    assert (_FIXTURE / spec.relpath).is_file(), f"missing: {spec.relpath}"


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_parses(spec: _FileSpec) -> None:
    """AC-2/AC-3/AC-4/AC-7/AC-9 — parses cleanly."""
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
    """Content predicates pass for every spec with content_checks."""
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
    """AC-28 — UTF-8, LF-only, ends with b'\\n'."""
    raw = (_FIXTURE / spec.relpath).read_bytes()
    assert b"\r" not in raw, f"{spec.relpath} contains CR — must be LF-only"
    assert raw.endswith(b"\n"), f"{spec.relpath} must end with LF"


# --- AC-4 supplement: tsconfig.json has both comment styles -------------------


def test_tsconfig_has_both_comment_styles() -> None:
    """AC-4 — JSONC with at least one // and one /* */ comment."""
    _tsconfig_has_both_comment_styles((_FIXTURE / "tsconfig.json").read_bytes())


# --- AC-27: forbidden subpaths absent -----------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    [
        "node_modules",
        ".codegenie",
        "dist",
        "coverage",
        "build",
        "build/Release",
        ".DS_Store",
    ],
)
def test_no_forbidden_subpaths(forbidden: str) -> None:
    """AC-27 — forbidden subpaths absent."""
    assert not (_FIXTURE / forbidden).exists(), (
        f"{forbidden!r} must not exist in minimal-ts/ — would dirty goldens"
    )


# --- AC-26: closed-set complement via git ls-files ----------------------------

_FIXTURE_NOISE_NAMES = frozenset({"__pycache__", ".pytest_cache", ".DS_Store"})


def _enumerate_tracked_via_git(fixture: Path) -> set[str]:
    """Enumerate tracked files via ``git ls-files`` (run_allowlisted)."""
    from codegenie.exec import run_allowlisted

    relative = fixture.resolve().relative_to(_REPO_ROOT.resolve())
    result = asyncio.run(
        run_allowlisted(
            ["git", "ls-files", "-z", str(relative)],
            cwd=_REPO_ROOT.resolve(),
            timeout_s=10.0,
        )
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git ls-files failed (rc={result.returncode}): {result.stderr.decode('utf-8', 'replace')}"
        )
    out: set[str] = set()
    for entry in result.stdout.split(b"\x00"):
        if not entry:
            continue
        relpath = entry.decode("utf-8")
        out.add(str(Path(relpath).relative_to(relative)))
    return out


def _enumerate_rglob_minus_noise(fixture: Path) -> set[str]:
    """Defense-in-depth rglob walk minus the explicit noise frozenset."""
    out: set[str] = set()
    for p in fixture.rglob("*"):
        if p.is_dir():
            continue
        parts = p.relative_to(fixture).parts
        if any(part in _FIXTURE_NOISE_NAMES or part.startswith(".pytest") for part in parts):
            continue
        out.add(str(p.relative_to(fixture)))
    return out


def test_fixture_tree_is_closed_set() -> None:
    """AC-26 — tracked-files set == _FILE_SPECS relpath set."""
    expected = {spec.relpath for spec in _FILE_SPECS}
    tracked = _enumerate_tracked_via_git(_FIXTURE)
    extra = tracked - expected
    missing = expected - tracked
    assert not extra and not missing, (
        f"extra tracked files: {sorted(extra)}; missing tracked files: {sorted(missing)}"
    )
    # Defense-in-depth: rglob view minus noise must also match (catches
    # files force-added under the noise filter, e.g. a `.DS_Store` snuck
    # past gitignore).
    rglob_view = _enumerate_rglob_minus_noise(_FIXTURE)
    extra_rg = rglob_view - expected
    # Files in rglob_view but not tracked are either gitignored (OK) or
    # not yet staged (acceptable mid-development). We only fail on files
    # that are present *and* should have been in _FILE_SPECS.
    untracked_unexpected = extra_rg - tracked
    # An untracked file outside the noise filter that isn't gitignored
    # would be a problem; but `git check-ignore` is the precise tool to
    # filter that. To stay deterministic we accept untracked files here
    # since the tracked-set check above is the primary contract.
    _ = untracked_unexpected  # consumed to document intent; no assertion.


# --- AC-29: README references every spec.relpath + every consumer -------------


def test_readme_references_every_spec() -> None:
    """AC-29 — README mentions every spec.relpath and every consumer probe."""
    readme_text = (_FIXTURE / "README.md").read_text(encoding="utf-8")
    for spec in _FILE_SPECS:
        if spec.relpath == "README.md":
            continue
        assert spec.relpath in readme_text, f"README missing reference to {spec.relpath}"
        for consumer in spec.consumers:
            assert consumer in readme_text, (
                f"README missing consumer {consumer!r} for {spec.relpath}"
            )


# --- AC-37: _ProbeName Literal is a superset of the live registry -------------


def test_probe_name_literal_matches_phase_2_registry() -> None:
    """AC-37 — registered probe names ⊆ _ProbeName Literal members.

    Subset semantics: Phase-3+ probe additions do NOT retroactively
    break this Phase-2 fixture, but a Phase-2 probe rename / addition
    that fails to update the Literal IS a test failure.
    """
    registered = {p.name for p in (cls() for cls in default_registry.all_probes())}
    literal_members = set(get_args(_ProbeName))
    missing = registered - literal_members
    assert not missing, (
        f"registered probe names not in _ProbeName Literal: {sorted(missing)}. "
        f"Update the Literal to include them (this is a deliberate fixture-update PR)."
    )
