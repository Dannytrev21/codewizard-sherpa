"""Shape test for ``tests/fixtures/portfolio/native-modules/`` (S7-01).

Consumes the shared shape-test kernel at
``tests/fixtures/_shape_test_kernel.py`` (S7-02 AC-24). This consumer
declares only its ``_FIXTURE`` + ``_FILE_SPECS`` + content predicates.

Implements AC-11..AC-17 + AC-25..AC-30 + AC-37 from S7-01.
"""

from __future__ import annotations

import re
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

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "native-modules"


# --- Pure content predicates --------------------------------------------------


def _pkg_declares_native_dep(pkg: dict[str, Any]) -> None:
    """AC-12 — one C-extension dep + node-gyp install script."""
    deps = pkg.get("dependencies", {})
    assert deps.get("bcrypt") == "5.1.0", (
        f"native-modules/package.json must declare bcrypt@5.1.0; got dependencies={deps}"
    )
    scripts = pkg.get("scripts", {})
    assert scripts.get("install") == "node-gyp rebuild", (
        f"native-modules/package.json must declare an install script "
        f"invoking node-gyp rebuild (the trigger marker NodeManifestProbe "
        f"and NodeReflectionProbe detect); got scripts={scripts}"
    )


def _binding_gyp_minimal_strict_json(binding: dict[str, Any]) -> None:
    """AC-13 — pure RFC-8259 JSON body with the minimal targets shape."""
    targets = binding.get("targets")
    assert isinstance(targets, list) and len(targets) == 1, (
        f"binding.gyp targets must be a single-element list; got {targets!r}"
    )
    target = targets[0]
    assert target.get("target_name") == "addon"
    assert target.get("sources") == ["src/addon.cc"]


def _binding_gyp_strict_json_bytes(raw_bytes: bytes) -> None:
    """AC-13 — no Python-style comments, no trailing commas."""
    text = raw_bytes.decode("utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        assert not stripped.startswith("#"), (
            f"binding.gyp line {lineno}: # comments are forbidden — pure RFC-8259 JSON only"
        )
    assert not re.search(r",\s*[\]}]", text), (
        "binding.gyp must not contain trailing commas — pure RFC-8259 JSON only"
    )


def _addon_cc_trivial(raw_bytes: bytes) -> None:
    """AC-14 — trivial empty C++ source."""
    text = raw_bytes.decode("utf-8")
    assert "#include <node.h>" in text
    assert "NODE_MODULE" in text
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) <= 5, f"addon.cc should be a trivial stub, got {len(lines)} non-blank lines"


def _pnpm_lock_pins_bcrypt(lock: dict[str, Any]) -> None:
    """AC-15 — lockfile pins bcrypt at exact 5.1.0."""
    assert lock.get("lockfileVersion") == "6.0"
    deps = lock.get("dependencies", {})
    assert deps.get("bcrypt", {}).get("version") == "5.1.0", (
        f"pnpm-lock.yaml must pin bcrypt@5.1.0; got {deps!r}"
    )


def _npmrc_ignore_scripts(raw_bytes: bytes) -> None:
    """AC-16 — exact bytes ``ignore-scripts=true\\n``."""
    assert raw_bytes == b"ignore-scripts=true\n", (
        f".npmrc must be exactly b'ignore-scripts=true\\n', got {raw_bytes!r}"
    )


# --- The single source of truth -----------------------------------------------

_FILE_SPECS: tuple[_FileSpec, ...] = (
    _FileSpec(
        "package.json",
        ("language_detection", "node_build_system", "node_manifest", "node_reflection"),
        "safe_json",
        (_pkg_declares_native_dep,),
    ),
    _FileSpec(
        "pnpm-lock.yaml",
        ("node_build_system", "node_manifest", "dep_graph"),
        "safe_yaml",
        (_pnpm_lock_pins_bcrypt,),
    ),
    _FileSpec(
        "binding.gyp",
        ("node_reflection", "generated_code"),
        "safe_json",
        (_binding_gyp_minimal_strict_json,),
    ),
    _FileSpec(
        "src/addon.cc",
        ("language_detection", "generated_code"),
        "text",
        (_addon_cc_trivial,),
    ),
    _FileSpec(".npmrc", ("node_manifest",), "text", (_npmrc_ignore_scripts,)),
    _FileSpec("README.md", (), "text", ()),
    _FileSpec("regenerate.sh", (), "text", ()),
    _FileSpec(".gitignore", (), "text", ()),
)


# --- Parametrize wrappers -----------------------------------------------------


def test_fixture_directory_exists() -> None:
    """AC-11 — fixture directory exists."""
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


def test_binding_gyp_is_strict_json() -> None:
    """AC-13 — binding.gyp body has no Python-style comments, no trailing commas."""
    _binding_gyp_strict_json_bytes((_FIXTURE / "binding.gyp").read_bytes())


@pytest.mark.parametrize("forbidden", _FORBIDDEN_SUBPATHS)
def test_no_forbidden_subpaths(forbidden: str) -> None:
    """AC-27 — forbidden subpaths absent.

    ``build/Release/`` is the load-bearing one: it would mean a local
    ``node-gyp rebuild`` ran despite the ignore-scripts defense. The
    regen script's AC-16b runtime check is the second line of defense.
    """
    assert_no_forbidden_subpath(_FIXTURE, forbidden)


def test_fixture_tree_is_closed_set() -> None:
    """AC-26 — tracked-files set == _FILE_SPECS relpath set."""
    assert_tree_is_closed_set(_FIXTURE, _FILE_SPECS)


def test_readme_references_every_spec() -> None:
    """AC-29 — README mentions every spec.relpath and every consumer probe."""
    assert_readme_references_every_spec(_FIXTURE, _FILE_SPECS)
