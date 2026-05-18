"""Shape test for ``tests/fixtures/portfolio/distroless-target/`` (S7-01).

Phase-7 forward-looking fixture. The load-bearing content predicate is
:func:`_dockerfile_final_stage_pins_digest` (AC-21b) — the final-stage
``FROM`` line must pin to a sha256 content digest, never an unpinned
``:latest`` tag. The mutation table in S7-01 §TDD plan calls out the
two ways a wrong pin sneaks in (unpinned tag, short/invalid digest);
both are caught by the regex.

Implements AC-18..AC-24 + AC-21b + AC-25..AC-30 + AC-37.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, Literal, NamedTuple, get_args

import pytest

from codegenie.parsers import safe_json
from codegenie.probes import default_registry

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "distroless-target"
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


# --- AC-21b: final-stage digest pin regex -------------------------------------

_DIGEST_PIN_RE: Final[re.Pattern[str]] = re.compile(r"^FROM\s+\S+@sha256:[0-9a-f]{64}\b")


# --- Pure content predicates --------------------------------------------------


def _pkg_minimal_node_app(pkg: dict[str, Any]) -> None:
    """AC-19 — minimal Node manifest, no dependencies."""
    assert pkg.get("name") == "distroless-target"
    assert pkg.get("main") == "index.js"
    assert pkg.get("scripts", {}).get("start") == "node index.js"
    # No dependencies — the distroless image runs a zero-dep app.
    assert not pkg.get("dependencies"), (
        f"distroless-target/package.json must declare zero dependencies; "
        f"got {pkg.get('dependencies')!r}"
    )


def _index_js_minimal(raw_bytes: bytes) -> None:
    """AC-20 — 5 lines: shebang + comment + console.log + process.exit."""
    text = raw_bytes.decode("utf-8")
    assert text.startswith("#!/usr/bin/env node"), (
        "index.js must start with a #!/usr/bin/env node shebang"
    )
    assert 'console.log("ok")' in text
    assert "process.exit(0)" in text
    # Cap line count to keep the fixture minimal.
    lines = text.splitlines()
    assert len(lines) <= 8, f"index.js should be a 5-line stub; got {len(lines)} lines"


def _dockerfile_two_stages_distroless(raw_bytes: bytes) -> None:
    """AC-21 — two stages; final stage is distroless; no USER directive."""
    text = raw_bytes.decode("utf-8")
    from_lines = [line for line in text.splitlines() if line.startswith("FROM ")]
    assert len(from_lines) == 2, (
        f"distroless-target/Dockerfile must have exactly two stages; got FROM lines {from_lines}"
    )
    assert "FROM node:20-slim AS build" in text, "First stage must be `FROM node:20-slim AS build`"
    # Final stage must mention a known distroless base. Two acceptable
    # roots per S7-01 AC-21; the regex predicate below handles the
    # digest-pin invariant.
    final = from_lines[-1]
    assert ("gcr.io/distroless/nodejs20-debian12" in final) or (
        "cgr.dev/chainguard/node" in final
    ), f"Final stage must be a distroless or chainguard base; got {final!r}"
    assert "COPY --from=build /app /app" in text
    assert "WORKDIR /app" in text
    assert 'CMD ["index.js"]' in text
    # AC-21 — no USER directive (distroless runs as non-root by
    # default; declaring USER would either be a no-op or a contradiction).
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        assert not stripped.startswith("USER "), (
            f"distroless-target/Dockerfile line {lineno}: USER directive forbidden — "
            f"distroless runs as non-root by default"
        )


def _dockerfile_final_stage_pins_digest(raw_bytes: bytes) -> None:
    """AC-21b — final-stage FROM line matches the digest-pin regex.

    This is the mutation-table-load-bearing predicate. A
    ``FROM ...:latest`` (unpinned tag) and a ``FROM ...@sha256:abc123``
    (invalid-length digest) are both caught here.
    """
    text = raw_bytes.decode("utf-8")
    from_lines = [line for line in text.splitlines() if line.startswith("FROM ")]
    assert from_lines, "Dockerfile must contain at least one FROM line"
    final = from_lines[-1].strip()
    assert _DIGEST_PIN_RE.match(final), (
        f"Final-stage FROM line must match {_DIGEST_PIN_RE.pattern!r}; got {final!r}. "
        f"This catches unpinned :latest tags and short/invalid digests."
    )


# --- The single source of truth -----------------------------------------------

_FILE_SPECS: tuple[_FileSpec, ...] = (
    _FileSpec(
        "package.json",
        ("language_detection", "node_build_system", "node_manifest"),
        "safe_json",
        (_pkg_minimal_node_app,),
    ),
    _FileSpec(
        "index.js",
        ("language_detection", "runtime_trace", "entrypoint"),
        "text",
        (_index_js_minimal,),
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
        (_dockerfile_two_stages_distroless, _dockerfile_final_stage_pins_digest),
    ),
    _FileSpec("README.md", (), "text", ()),
    _FileSpec("regenerate.sh", (), "text", ()),
    _FileSpec(".gitignore", (), "text", ()),
)


# --- Tests --------------------------------------------------------------------


def test_fixture_directory_exists() -> None:
    """AC-18 — fixture directory exists."""
    assert _FIXTURE.is_dir()


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_exists(spec: _FileSpec) -> None:
    """AC-19..AC-24 — every spec'd file is present."""
    assert (_FIXTURE / spec.relpath).is_file(), f"missing: {spec.relpath}"


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_parses(spec: _FileSpec) -> None:
    if spec.parser is None or spec.parser == "text":
        return
    path = _FIXTURE / spec.relpath
    if spec.parser == "safe_json":
        safe_json.load(path, max_bytes=50 * 1024 * 1024)


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
    for check in spec.content_checks:
        check(payload)


@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_line_endings(spec: _FileSpec) -> None:
    """AC-28 — UTF-8, LF-only, ends with b'\\n'."""
    raw = (_FIXTURE / spec.relpath).read_bytes()
    assert b"\r" not in raw, f"{spec.relpath} contains CR — must be LF-only"
    assert raw.endswith(b"\n"), f"{spec.relpath} must end with LF"


# --- AC-21b dedicated test ---------------------------------------------------


def test_dockerfile_final_stage_pins_digest() -> None:
    """AC-21b — direct test for the digest-pin predicate.

    Even with the parametrized content_invariants coverage above, a
    dedicated test guards against accidental removal of the predicate
    from the ``Dockerfile`` spec's content_checks tuple.
    """
    _dockerfile_final_stage_pins_digest((_FIXTURE / "Dockerfile").read_bytes())


# --- AC-27: forbidden subpaths absent ----------------------------------------


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
    assert not (_FIXTURE / forbidden).exists(), (
        f"{forbidden!r} must not exist in distroless-target/ — would dirty goldens"
    )


# --- AC-23: .gitignore covers built-image.digest -----------------------------


def test_gitignore_covers_built_image_digest() -> None:
    """AC-23 — .gitignore includes built-image.digest entry."""
    text = (_FIXTURE / ".gitignore").read_text(encoding="utf-8")
    assert ".codegenie/" in text
    assert "built-image.digest" in text


# --- AC-26: closed-set complement via git ls-files ---------------------------

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
    """AC-26 — tracked-files set == _FILE_SPECS relpath set.

    Uses ``git ls-files`` so the closed-set check honors .gitignore
    automatically — ``built-image.digest`` (written by regenerate.sh,
    gitignored per AC-23) does not dirty the set.
    """
    expected = {spec.relpath for spec in _FILE_SPECS}
    tracked = _enumerate_tracked_via_git(_FIXTURE)
    extra = tracked - expected
    missing = expected - tracked
    assert not extra and not missing, (
        f"extra tracked files: {sorted(extra)}; missing tracked files: {sorted(missing)}"
    )


# --- AC-29: README references every spec.relpath + every consumer ------------


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


# --- AC-37: _ProbeName Literal is a superset of the live registry -----------


def test_probe_name_literal_matches_phase_2_registry() -> None:
    """AC-37 — registered ⊆ Literal members (subset semantics)."""
    registered = {p.name for p in (cls() for cls in default_registry.all_probes())}
    literal_members = set(get_args(_ProbeName))
    missing = registered - literal_members
    assert not missing, f"registered probe names not in _ProbeName Literal: {sorted(missing)}"
