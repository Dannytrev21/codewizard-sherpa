"""Shape test for ``tests/fixtures/portfolio/native-modules/`` (S7-01).

Mirrors the closed-set + content-invariants pattern of the minimal-ts
shape test. The kernel is intentionally duplicated for now — S7-02
lifts a shared shape-test kernel when the fixture count reaches five
(per S7-01 Notes "Patterns DELIBERATELY deferred", Rule of Three
boundary).

Implements AC-11..AC-17 + AC-25..AC-30 + AC-37 from S7-01.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, NamedTuple, get_args

import pytest

from codegenie.parsers import safe_json, safe_yaml
from codegenie.probes import default_registry

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "native-modules"
_REPO_ROOT = Path(__file__).parent.parent.parent

_ProbeName = Literal[
    "language_detection",
    "node_build_system",
    "node_manifest",
    "ci",
    "deployment",
    "test_inventory",
    "index_health",
    "scip_index",
    "tree_sitter_import_graph",
    "dep_graph",
    "generated_code",
    "node_reflection",
    "semantic_index_meta",
    "runtime_trace",
    "dockerfile",
    "entrypoint",
    "shell_usage",
    "certificate",
    "sbom",
    "cve",
    "skills_index",
    "conventions",
    "adrs",
    "repo_notes",
    "repo_config",
    "policy",
    "exceptions",
    "external_docs",
    "ownership",
    "service_topology",
    "slo",
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
    # Strict-JSON discipline: no ``#`` line comments (node-gyp accepts
    # them, RFC-8259 does not). ``safe_json.load`` would reject them
    # anyway but pinning explicitly documents the contract.
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        assert not stripped.startswith("#"), (
            f"binding.gyp line {lineno}: # comments are forbidden — pure RFC-8259 JSON only"
        )
    # No trailing commas: ``,]`` or ``,}`` after whitespace.
    import re as _re

    assert not _re.search(r",\s*[\]}]", text), (
        "binding.gyp must not contain trailing commas — pure RFC-8259 JSON only"
    )


def _addon_cc_trivial(raw_bytes: bytes) -> None:
    """AC-14 — trivial empty C++ source."""
    text = raw_bytes.decode("utf-8")
    assert "#include <node.h>" in text
    assert "NODE_MODULE" in text
    # Pin the line count to keep the fixture small (3-4 lines).
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


# --- Tests -------------------------------------------------------------------


def test_fixture_directory_exists() -> None:
    """AC-11 — fixture directory exists."""
    assert _FIXTURE.is_dir()


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_exists(spec: _FileSpec) -> None:
    """AC-12..AC-17 — every spec'd file is present."""
    assert (_FIXTURE / spec.relpath).is_file(), f"missing: {spec.relpath}"


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_parses(spec: _FileSpec) -> None:
    """AC-12/AC-13/AC-15 — parses cleanly via the declared parser."""
    if spec.parser is None or spec.parser == "text":
        return
    path = _FIXTURE / spec.relpath
    if spec.parser == "safe_json":
        safe_json.load(path, max_bytes=50 * 1024 * 1024)
    elif spec.parser == "safe_yaml":
        safe_yaml.load(path, max_bytes=50 * 1024 * 1024)


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_content_invariants(spec: _FileSpec) -> None:
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


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_line_endings(spec: _FileSpec) -> None:
    """AC-28 — UTF-8, LF-only, ends with b'\\n'."""
    raw = (_FIXTURE / spec.relpath).read_bytes()
    assert b"\r" not in raw, f"{spec.relpath} contains CR — must be LF-only"
    assert raw.endswith(b"\n"), f"{spec.relpath} must end with LF"


# --- AC-13 supplement: strict-JSON bytes contract -----------------------------


def test_binding_gyp_is_strict_json() -> None:
    """AC-13 — binding.gyp body has no Python-style comments, no trailing commas."""
    _binding_gyp_strict_json_bytes((_FIXTURE / "binding.gyp").read_bytes())


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
    """AC-27 — forbidden subpaths absent.

    ``build/Release/`` is the load-bearing one: it would mean a local
    ``node-gyp rebuild`` ran despite the ignore-scripts defense. The
    regen script's AC-16b runtime check is the second line of defense.
    """
    assert not (_FIXTURE / forbidden).exists(), (
        f"{forbidden!r} must not exist in native-modules/ — "
        f"would signal a node-gyp rebuild leaked into the fixture tree"
    )


# --- AC-26: closed-set complement via git ls-files ----------------------------

_FIXTURE_NOISE_NAMES = frozenset({"__pycache__", ".pytest_cache", ".DS_Store"})


def _enumerate_tracked_via_git(fixture: Path) -> set[str]:
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
        stderr = result.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"git ls-files failed (rc={result.returncode}): {stderr}")
    out: set[str] = set()
    for entry in result.stdout.split(b"\x00"):
        if not entry:
            continue
        relpath = entry.decode("utf-8")
        out.add(str(Path(relpath).relative_to(relative)))
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
    """AC-37 — registered ⊆ Literal members (subset semantics)."""
    registered = {p.name for p in (cls() for cls in default_registry.all_probes())}
    literal_members = set(get_args(_ProbeName))
    missing = registered - literal_members
    assert not missing, f"registered probe names not in _ProbeName Literal: {sorted(missing)}"
