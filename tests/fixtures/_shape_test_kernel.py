"""Shared shape-test kernel — S7-02 AC-23 / AC-24.

A single source of truth for the fixture-shape parametrized tests under
``tests/unit/test_fixture_*_shape.py``. Six consumers (rule-of-three
conclusively past — five Phase-2 portfolio fixtures plus Phase-1's
``node_typescript_helm`` fixture) share:

- :class:`_FileSpec` — the (relpath, consumers, parser, content_checks)
  record each consumer declares per file.
- :data:`_ProbeName` — closed ``Literal[...]`` listing every Phase-1 +
  Phase-2 probe name; consumers' tuples must be a subset (mypy --strict
  catches typos; the runtime subset-semantics check in
  ``tests/unit/test_fixture_shape_kernel.py`` catches probe renames /
  additions whose names don't make it into the Literal).
- :data:`_ParserKind` — closed ``Literal`` admitting only the four
  parsers Phase 2 honors (``safe_json``, ``safe_yaml``, ``jsonc``,
  ``text``); ``None`` opts a file out of all parser-driven checks (used
  for the binary SCIP seed blob under ``stale-scip``).
- :func:`enumerate_tracked` — the single, kernel-owned port to
  ``git ls-files -z <fixture>``. Consumers receive ``tuple[str, ...]``
  of relpaths; subprocess invocation is encapsulated here.
- :func:`enumerate_rglob_minus_noise` — defense-in-depth rglob walk
  minus the explicit noise frozenset.
- Flat assertion helpers (``assert_file_exists`` /
  ``assert_file_parses`` / ``assert_file_content_invariants`` /
  ``assert_file_line_endings`` / ``assert_no_forbidden_subpaths`` /
  ``assert_tree_is_closed_set`` / ``assert_readme_references_every_spec``
  / ``assert_probe_name_literal_is_superset``). Each consumer writes
  minimal ``@pytest.mark.parametrize`` test bodies that delegate to
  these helpers — see ``test_fixture_minimal_ts_shape.py`` for the
  canonical example.

Why the kernel lives at ``tests/fixtures/`` (above the ``portfolio/``
subdirectory): Phase-1's ``tests/fixtures/node_typescript_helm/`` shape
test is the sixth consumer; placing the kernel under ``portfolio/``
would force Phase-1's test to cross a foreign namespace.

Why flat helpers (not test-factories): pytest's natural
module-level ``@pytest.mark.parametrize`` discovery is preserved;
``mypy --strict`` is clean without ergonomic dance; the kernel reads
as a functional core.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, Literal, NamedTuple, get_args

from codegenie.parsers import jsonc, safe_json, safe_yaml

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Closed sets
# ---------------------------------------------------------------------------

_FIXTURE_NOISE_NAMES: Final[frozenset[str]] = frozenset(
    {"__pycache__", ".pytest_cache", ".DS_Store"}
)

_FORBIDDEN_SUBPATHS: Final[tuple[str, ...]] = (
    "node_modules",
    ".codegenie",
    "dist",
    "coverage",
    "build",
    "build/Release",
    ".DS_Store",
)

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Parser dispatch — single chokepoint
# ---------------------------------------------------------------------------


def _load(path: Path, parser: _ParserKind | None) -> Any:
    """Dispatch ``path`` through the appropriate parser.

    ``text`` and ``None`` both return raw bytes; the difference is that
    ``None`` (binary-only specs like the ``stale-scip`` SCIP seed)
    additionally suppresses LF-line-ending and parser-driven checks.
    """
    if parser in (None, "text"):
        return path.read_bytes()
    if parser == "safe_json":
        return safe_json.load(path, max_bytes=50 * 1024 * 1024)
    if parser == "safe_yaml":
        return safe_yaml.load(path, max_bytes=50 * 1024 * 1024)
    if parser == "jsonc":
        return jsonc.load(path, max_bytes=10 * 1024 * 1024)
    raise ValueError(f"unknown parser: {parser!r}")


# ---------------------------------------------------------------------------
# Flat assertion helpers — what consumers call from their parametrize bodies
# ---------------------------------------------------------------------------


def assert_file_exists(fixture: Path, spec: _FileSpec) -> None:
    """Every spec'd file is present on disk."""
    assert (fixture / spec.relpath).is_file(), f"missing: {spec.relpath}"


def assert_file_parses(fixture: Path, spec: _FileSpec) -> None:
    """Parser-driven specs round-trip through their declared parser."""
    if spec.parser is None or spec.parser == "text":
        return
    _load(fixture / spec.relpath, spec.parser)


def assert_file_content_invariants(fixture: Path, spec: _FileSpec) -> None:
    """Run every content predicate the spec declares."""
    if not spec.content_checks:
        return
    payload = _load(fixture / spec.relpath, spec.parser)
    for check in spec.content_checks:
        check(payload)


def assert_file_line_endings(fixture: Path, spec: _FileSpec) -> None:
    """UTF-8 LF-only; binary specs (``parser is None``) are exempt."""
    if spec.parser is None:
        return
    raw = (fixture / spec.relpath).read_bytes()
    assert b"\r" not in raw, f"{spec.relpath} contains CR — must be LF-only"
    assert raw.endswith(b"\n"), f"{spec.relpath} must end with LF"


def assert_no_forbidden_subpath(fixture: Path, forbidden: str) -> None:
    """Forbidden subpaths absent — would dirty goldens or signal leaks."""
    assert not (fixture / forbidden).exists(), (
        f"{forbidden!r} must not exist in {fixture.name}/ — would dirty goldens "
        f"or signal a build/install leak into the fixture tree"
    )


def enumerate_tracked(fixture: Path) -> tuple[str, ...]:
    """Return tracked-files relpaths via ``git ls-files -z <fixture>``.

    This is the single call site for ``git ls-files`` across all six
    shape-test consumers; subprocess invocation is encapsulated here.
    Consumers receive a ``tuple[str, ...]`` of fixture-relative paths.
    """
    from codegenie.exec import run_allowlisted

    relative = fixture.resolve().relative_to(_REPO_ROOT)
    result = asyncio.run(
        run_allowlisted(
            ["git", "ls-files", "-z", str(relative)],
            cwd=_REPO_ROOT,
            timeout_s=10.0,
        )
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"git ls-files failed (rc={result.returncode}): {stderr}")
    out: list[str] = []
    for entry in result.stdout.split(b"\x00"):
        if not entry:
            continue
        relpath = entry.decode("utf-8")
        out.append(str(Path(relpath).relative_to(relative)))
    return tuple(out)


def enumerate_rglob_minus_noise(fixture: Path) -> set[str]:
    """Defense-in-depth rglob walk minus the noise frozenset."""
    out: set[str] = set()
    for p in fixture.rglob("*"):
        if p.is_dir():
            continue
        parts = p.relative_to(fixture).parts
        if any(part in _FIXTURE_NOISE_NAMES or part.startswith(".pytest") for part in parts):
            continue
        out.add(str(p.relative_to(fixture)))
    return out


def assert_tree_is_closed_set(fixture: Path, file_specs: tuple[_FileSpec, ...]) -> None:
    """Tracked-files set == ``{spec.relpath for spec in file_specs}``."""
    expected = {spec.relpath for spec in file_specs}
    tracked = set(enumerate_tracked(fixture))
    extra = tracked - expected
    missing = expected - tracked
    assert not extra and not missing, (
        f"extra tracked files: {sorted(extra)}; missing tracked files: {sorted(missing)}"
    )


def assert_readme_references_every_spec(fixture: Path, file_specs: tuple[_FileSpec, ...]) -> None:
    """README mentions every spec.relpath and every consumer probe."""
    readme_text = (fixture / "README.md").read_text(encoding="utf-8")
    for spec in file_specs:
        if spec.relpath == "README.md":
            continue
        assert spec.relpath in readme_text, f"README missing reference to {spec.relpath}"
        for consumer in spec.consumers:
            assert consumer in readme_text, (
                f"README missing consumer {consumer!r} for {spec.relpath}"
            )


def assert_probe_name_literal_is_superset() -> None:
    """Subset semantics — every registered probe name is in ``_ProbeName``.

    Phase-3+ probes added later do NOT retroactively break Phase-2
    fixtures (extra Literal members are allowed); but a renamed or
    newly-added Phase-2 probe whose name isn't reflected in the Literal
    IS a build failure.
    """
    from codegenie.probes import default_registry

    registered = {p.name for p in (cls() for cls in default_registry.all_probes())}
    literal_members = set(get_args(_ProbeName))
    missing = registered - literal_members
    assert not missing, (
        f"registered probe names not in _ProbeName Literal: {sorted(missing)}. "
        f"Update the Literal in tests/fixtures/_shape_test_kernel.py to include "
        f"them (this is a deliberate fixture-update PR)."
    )


# ---------------------------------------------------------------------------
# Exported contract
# ---------------------------------------------------------------------------

__all__: Final[tuple[str, ...]] = (
    "_FIXTURE_NOISE_NAMES",
    "_FORBIDDEN_SUBPATHS",
    "_FileSpec",
    "_ParserKind",
    "_ProbeName",
    "assert_file_content_invariants",
    "assert_file_exists",
    "assert_file_line_endings",
    "assert_file_parses",
    "assert_no_forbidden_subpath",
    "assert_probe_name_literal_is_superset",
    "assert_readme_references_every_spec",
    "assert_tree_is_closed_set",
    "enumerate_rglob_minus_noise",
    "enumerate_tracked",
)
