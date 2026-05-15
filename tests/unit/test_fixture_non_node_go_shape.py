"""Shape test for ``tests/fixtures/non_node_go/`` — the non-Node Go fixture.

``_FILE_SPECS_NON_NODE_GO`` is the single source of truth for which files the
fixture contains. The fixture is the load-bearing contract test for ADR-0010
(Layer-A slices optional at envelope): a purely-Go repo must flow through
Phase 1 producing a valid envelope with only ``language_stack`` populated.

The ``test_no_forbidden_subpaths`` battery (AC-NN-2) is the regression net
for that contract — adding ANY Node marker to the fixture breaks the test
at land-time, not at operator-discretion.

This file implements the AC battery from
``docs/phases/01-context-gather-layer-a-node/stories/S5-04-fixtures-monorepo-non-node.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, NamedTuple, get_args

import pytest

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "non_node_go"

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


# --- Pure content predicates ----------------------------------------------------


_GO_MOD_EXACT_BYTES = b"module example.com/non-node-fixture\n\ngo 1.22\n"


def _go_mod_exact_bytes(raw: bytes) -> None:
    """AC-NN-3 — go.mod exact bytes pin."""
    assert raw == _GO_MOD_EXACT_BYTES, (
        f"go.mod must be exactly {_GO_MOD_EXACT_BYTES!r}, got {raw!r}"
    )


def _main_go_starts_with_package_main(raw: bytes) -> None:
    """AC-NN-4 — main.go has ``package main`` on its first non-empty line."""
    text = raw.decode("utf-8")
    first_nonempty = next((line.strip() for line in text.splitlines() if line.strip()), "")
    assert first_nonempty == "package main", (
        f"main.go first non-empty line must be 'package main', got {first_nonempty!r}"
    )
    assert "func main()" in text, "main.go must contain a 'func main()' body"


def _handler_go_starts_with_package_internal(raw: bytes) -> None:
    """AC-NN-4 — internal/handler.go has ``package internal`` on its first non-empty line."""
    text = raw.decode("utf-8")
    first_nonempty = next((line.strip() for line in text.splitlines() if line.strip()), "")
    assert first_nonempty == "package internal", (
        f"handler.go first non-empty line must be 'package internal', got {first_nonempty!r}"
    )


def _readme_mentions_adr_0010_and_three(raw: bytes) -> None:
    """AC-NN-8 — README mentions ADR-0010 and 'three' (not 'five')."""
    text = raw.decode("utf-8")
    assert "ADR-0010" in text, "README must mention 'ADR-0010' literally"
    assert "three" in text, (
        "README must say 'three' Phase-1 probes are filtered out "
        "(not 'five' — that was a first-draft inconsistency; ci and "
        "deployment are applies_to_languages=['*'] and run on every repo)"
    )
    assert "test_non_node_repo.py" in text, (
        "README must name consuming integration test 'test_non_node_repo.py' (S5-05)"
    )
    assert "Fixture portfolio" in text, "README must cite phase-arch-design.md §'Fixture portfolio'"


# --- The single source of truth -------------------------------------------------

_FILE_SPECS_NON_NODE_GO: tuple[_FileSpec, ...] = (
    _FileSpec(
        "go.mod",
        ("language_detection",),
        "text",
        (_go_mod_exact_bytes,),
    ),
    _FileSpec(
        "main.go",
        ("language_detection",),
        "text",
        (_main_go_starts_with_package_main,),
    ),
    _FileSpec(
        "internal/handler.go",
        ("language_detection",),
        "text",
        (_handler_go_starts_with_package_internal,),
    ),
    _FileSpec(
        "README.md",
        (),
        "text",
        (_readme_mentions_adr_0010_and_three,),
    ),
)


# --- Tests parametrized over _FILE_SPECS_NON_NODE_GO ---------------------------


@pytest.mark.parametrize("spec", _FILE_SPECS_NON_NODE_GO, ids=lambda s: s.relpath)
def test_fixture_file_exists(spec: _FileSpec) -> None:
    """AC-NN-1 — every spec'd file is present."""
    assert (_FIXTURE / spec.relpath).is_file(), f"missing: {spec.relpath}"


@pytest.mark.parametrize("spec", _FILE_SPECS_NON_NODE_GO, ids=lambda s: s.relpath)
def test_fixture_file_content_invariants(spec: _FileSpec) -> None:
    """AC-NN-3/AC-NN-4/AC-NN-8 — content predicates pass."""
    if not spec.content_checks:
        return
    payload = (_FIXTURE / spec.relpath).read_bytes()
    for check in spec.content_checks:
        check(payload)


@pytest.mark.parametrize("spec", _FILE_SPECS_NON_NODE_GO, ids=lambda s: s.relpath)
def test_fixture_file_line_endings(spec: _FileSpec) -> None:
    """AC-SHARED-4/AC-SHARED-6 — LF endings, no CRLF, trailing newline."""
    raw = (_FIXTURE / spec.relpath).read_bytes()
    assert b"\r" not in raw, f"{spec.relpath} contains CR — must be LF-only"
    assert raw.endswith(b"\n"), f"{spec.relpath} must end with LF"


# --- AC-NN-2: forbidden subpaths absent (ADR-0010 contract guardrail) -----------


@pytest.mark.parametrize(
    "forbidden",
    [
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "tsconfig.json",
        "tsconfig.base.json",
        ".nvmrc",
        "node_modules",
        ".codegenie",
        "dist",
        "coverage",
        ".DS_Store",
        ".idea",
        ".vscode",
    ],
)
def test_no_forbidden_subpaths(forbidden: str) -> None:
    """AC-NN-2 — no Node marker / build artifact / IDE config anywhere recursively.

    This is the load-bearing contract test for ADR-0010: adding any of these
    paths would either turn the fixture into a Node repo (defeating its
    purpose) or pollute downstream test isolation.
    """
    # check recursive — every directory under root
    for p in _FIXTURE.rglob(forbidden):
        if p.exists():
            raise AssertionError(
                f"forbidden path {forbidden!r} must not exist anywhere under "
                f"non_node_go/, found at {p.relative_to(_FIXTURE)}"
            )


# --- AC-NN-1: closed-set complement (no stray files) ----------------------------

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
    """AC-NN-1 — fixture path set equals ``{spec.relpath for spec in _FILE_SPECS_NON_NODE_GO}``."""
    expected = {spec.relpath for spec in _FILE_SPECS_NON_NODE_GO}
    actual = _enumerate_tracked(_FIXTURE)
    extra = actual - expected
    missing = expected - actual
    assert not extra and not missing, (
        f"extra files: {sorted(extra)}; missing files: {sorted(missing)}"
    )


# --- AC-NN-8: README references every consumer name -----------------------------


def test_readme_references_every_spec() -> None:
    readme_text = (_FIXTURE / "README.md").read_text(encoding="utf-8")
    for spec in _FILE_SPECS_NON_NODE_GO:
        if spec.relpath == "README.md":
            continue
        assert spec.relpath in readme_text, f"README missing reference to {spec.relpath}"
        for consumer in spec.consumers:
            assert consumer in readme_text, (
                f"README missing consumer {consumer!r} for {spec.relpath}"
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
