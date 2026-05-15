"""Shape test for ``tests/fixtures/node_monorepo_turbo/`` — the turbo-monorepo fixture.

``_FILE_SPECS_MONOREPO_TURBO`` is the single source of truth for which files
the fixture contains, which probes consume each, and which content invariants
each file must satisfy. Adding a fixture file: one :class:`_FileSpec` entry
insertion + zero edits to the parametrized test bodies. The same
``Literal[...]`` ``_ProbeName`` closed set is enforced both at
``mypy --strict`` (typo-resistance) AND at runtime
(``test_probe_name_literal_matches_phase_1_closed_set``).

This file implements the AC battery from
``docs/phases/01-context-gather-layer-a-node/stories/S5-04-fixtures-monorepo-non-node.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, NamedTuple, get_args

import pytest

from codegenie.parsers import safe_json, safe_yaml
from codegenie.probes.language_detection import _detect_monorepo

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "node_monorepo_turbo"

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


def _pkg_json_root_shape(pkg: dict[str, Any]) -> None:
    """AC-MR-2 — root package.json shape."""
    assert pkg.get("name") == "monorepo-root", (
        f"name must be 'monorepo-root', got {pkg.get('name')!r}"
    )
    assert pkg.get("private") is True, "root package.json must have private: true"
    assert pkg.get("workspaces") == ["packages/*"], (
        f"workspaces must equal ['packages/*'], got {pkg.get('workspaces')!r}"
    )
    assert "packageManager" not in pkg, (
        "`packageManager` field would trip the S2-02 "
        "package_manager.declaration_lockfile_disagree path"
    )


def _turbo_json_minimum_shape(turbo: dict[str, Any]) -> None:
    """AC-MR-4 — turbo.json minimum shape, forward-compatible with v1 and v2."""
    schema = turbo.get("$schema")
    assert isinstance(schema, str) and schema.startswith("https://turbo.build/"), (
        f"$schema must be a string starting with 'https://turbo.build/', got {schema!r}"
    )
    assert "pipeline" in turbo or "tasks" in turbo, (
        "turbo.json must have at least one of 'pipeline' (v1) or 'tasks' (v2)"
    )


def _workspace_member_app_web(pkg: dict[str, Any]) -> None:
    """AC-MR-5 — packages/app-web/package.json shape."""
    assert pkg.get("name") == "@scope/app-web", (
        f"name must be '@scope/app-web', got {pkg.get('name')!r}"
    )
    assert "version" in pkg, "workspace member must have a 'version' field"
    assert "dependencies" in pkg, "workspace member must have a 'dependencies' field (may be empty)"


def _workspace_member_app_api(pkg: dict[str, Any]) -> None:
    """AC-MR-5 — packages/app-api/package.json shape."""
    assert pkg.get("name") == "@scope/app-api", (
        f"name must be '@scope/app-api', got {pkg.get('name')!r}"
    )
    assert "version" in pkg, "workspace member must have a 'version' field"
    assert "dependencies" in pkg, "workspace member must have a 'dependencies' field (may be empty)"


def _pnpm_lock_v6_header(lock: dict[str, Any]) -> None:
    """AC-MR-6 — pnpm-lock.yaml header pin."""
    assert lock.get("lockfileVersion") == "6.0", (
        f"lockfileVersion must be '6.0' (S2-03 precedent), got {lock.get('lockfileVersion')!r}"
    )


# --- The single source of truth -------------------------------------------------

_FILE_SPECS_MONOREPO_TURBO: tuple[_FileSpec, ...] = (
    _FileSpec(
        "package.json",
        ("language_detection", "node_build_system", "node_manifest"),
        "safe_json",
        (_pkg_json_root_shape,),
    ),
    _FileSpec(
        "turbo.json",
        ("language_detection",),
        "safe_json",
        (_turbo_json_minimum_shape,),
    ),
    _FileSpec(
        "packages/app-web/package.json",
        (),
        "safe_json",
        (_workspace_member_app_web,),
    ),
    _FileSpec(
        "packages/app-api/package.json",
        (),
        "safe_json",
        (_workspace_member_app_api,),
    ),
    _FileSpec(
        "pnpm-lock.yaml",
        ("node_build_system", "node_manifest"),
        "safe_yaml",
        (_pnpm_lock_v6_header,),
    ),
    _FileSpec("README.md", (), "text", ()),
)


# --- Tests parametrized over _FILE_SPECS_MONOREPO_TURBO -------------------------


@pytest.mark.parametrize("spec", _FILE_SPECS_MONOREPO_TURBO, ids=lambda s: s.relpath)
def test_fixture_file_exists(spec: _FileSpec) -> None:
    """AC-MR-1 — every spec'd file is present."""
    assert (_FIXTURE / spec.relpath).is_file(), f"missing: {spec.relpath}"


@pytest.mark.parametrize("spec", _FILE_SPECS_MONOREPO_TURBO, ids=lambda s: s.relpath)
def test_fixture_file_parses(spec: _FileSpec) -> None:
    """AC-MR-2/AC-MR-4/AC-MR-5/AC-MR-6 — each file parses cleanly."""
    if spec.parser is None or spec.parser == "text":
        return
    path = _FIXTURE / spec.relpath
    if spec.parser == "safe_json":
        safe_json.load(path, max_bytes=50 * 1024 * 1024)
    elif spec.parser == "safe_yaml":
        safe_yaml.load(path, max_bytes=50 * 1024 * 1024)


@pytest.mark.parametrize("spec", _FILE_SPECS_MONOREPO_TURBO, ids=lambda s: s.relpath)
def test_fixture_file_content_invariants(spec: _FileSpec) -> None:
    """AC-MR-2/AC-MR-4/AC-MR-5/AC-MR-6 — content predicates pass."""
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
    for check in spec.content_checks:
        check(payload)


@pytest.mark.parametrize("spec", _FILE_SPECS_MONOREPO_TURBO, ids=lambda s: s.relpath)
def test_fixture_file_line_endings(spec: _FileSpec) -> None:
    """AC-SHARED-4/AC-SHARED-6 — LF endings, no CRLF, trailing newline."""
    raw = (_FIXTURE / spec.relpath).read_bytes()
    assert b"\r" not in raw, f"{spec.relpath} contains CR — must be LF-only"
    assert raw.endswith(b"\n"), f"{spec.relpath} must end with LF"


# --- AC-MR-3: multi-marker invariant (THE reason this fixture exists) -----------


def test_monorepo_two_markers_detected() -> None:
    """AC-MR-3 — both ``turbo.json`` AND ``package.json#workspaces`` detected.

    Runs ``LanguageDetectionProbe._detect_monorepo`` over the fixture root
    with the parsed root ``package.json``. The result must yield
    ``tool == "turbo"`` (first-precedence hit between the two) AND
    ``markers == ["package.json", "turbo.json"]`` (sorted union of both
    hits). This pins the precedence-chain code path the fixture exists
    to exercise — a single-marker happy path would only catch one entry.
    """
    pkg = safe_json.load(_FIXTURE / "package.json", max_bytes=5 * 1024 * 1024)
    block = _detect_monorepo(_FIXTURE, pkg)
    assert block is not None, "_detect_monorepo must return a block, got None"
    assert block["tool"] == "turbo", f"tool must be 'turbo', got {block['tool']!r}"
    assert block["markers"] == ["package.json", "turbo.json"], (
        f"markers must be sorted union ['package.json', 'turbo.json'], got {block['markers']!r}"
    )


# --- AC-MR-7: README references every spec.relpath + consumer -------------------


def test_readme_references_every_spec() -> None:
    readme_text = (_FIXTURE / "README.md").read_text(encoding="utf-8")
    for spec in _FILE_SPECS_MONOREPO_TURBO:
        if spec.relpath == "README.md":
            continue
        assert spec.relpath in readme_text, f"README missing reference to {spec.relpath}"
        for consumer in spec.consumers:
            assert consumer in readme_text, (
                f"README missing consumer {consumer!r} for {spec.relpath}"
            )
    assert "test_monorepo_turbo.py" in readme_text, (
        "README must name consuming integration test 'test_monorepo_turbo.py' (S5-05)"
    )
    assert "phase-arch-design.md" in readme_text and "Fixture portfolio" in readme_text, (
        "README must cite phase-arch-design.md §'Fixture portfolio'"
    )


# --- AC-MR-1: closed-set complement (no stray files) ----------------------------

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
    """AC-MR-1 — path set equals ``{spec.relpath for spec in _FILE_SPECS_MONOREPO_TURBO}``."""
    expected = {spec.relpath for spec in _FILE_SPECS_MONOREPO_TURBO}
    actual = _enumerate_tracked(_FIXTURE)
    extra = actual - expected
    missing = expected - actual
    assert not extra and not missing, (
        f"extra files: {sorted(extra)}; missing files: {sorted(missing)}"
    )


# --- AC-SHARED-3: _ProbeName Literal is the Phase-1 closed set ------------------


def test_probe_name_literal_matches_phase_1_closed_set() -> None:
    assert set(get_args(_ProbeName)) == {
        "language_detection",
        "node_build_system",
        "node_manifest",
        "ci",
        "deployment",
        "test_inventory",
    }
