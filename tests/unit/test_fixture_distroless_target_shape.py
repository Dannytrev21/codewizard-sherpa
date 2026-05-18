"""Shape test for ``tests/fixtures/portfolio/distroless-target/`` (S7-01).

Consumes the shared shape-test kernel at
``tests/fixtures/_shape_test_kernel.py`` (S7-02 AC-24).

The load-bearing content predicate is
:func:`_dockerfile_final_stage_pins_digest` (AC-21b) — the final-stage
``FROM`` line must pin to a sha256 content digest, never an unpinned
``:latest`` tag. The mutation table in S7-01 §TDD plan calls out the
two ways a wrong pin sneaks in (unpinned tag, short/invalid digest);
both are caught by the regex.

Implements AC-18..AC-24 + AC-21b + AC-25..AC-30 + AC-37.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

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

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "distroless-target"


# --- AC-21b: final-stage digest pin regex -------------------------------------

_DIGEST_PIN_RE: Final[re.Pattern[str]] = re.compile(r"^FROM\s+\S+@sha256:[0-9a-f]{64}\b")


# --- Pure content predicates --------------------------------------------------


def _pkg_minimal_node_app(pkg: dict[str, Any]) -> None:
    """AC-19 — minimal Node manifest, no dependencies."""
    assert pkg.get("name") == "distroless-target"
    assert pkg.get("main") == "index.js"
    assert pkg.get("scripts", {}).get("start") == "node index.js"
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
    final = from_lines[-1]
    assert ("gcr.io/distroless/nodejs20-debian12" in final) or (
        "cgr.dev/chainguard/node" in final
    ), f"Final stage must be a distroless or chainguard base; got {final!r}"
    assert "COPY --from=build /app /app" in text
    assert "WORKDIR /app" in text
    assert 'CMD ["index.js"]' in text
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


# --- Parametrize wrappers -----------------------------------------------------


def test_fixture_directory_exists() -> None:
    """AC-18 — fixture directory exists."""
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


def test_dockerfile_final_stage_pins_digest_predicate_direct() -> None:
    """AC-21b — direct test for the digest-pin predicate.

    Even with the parametrized content_invariants coverage above, a
    dedicated test guards against accidental removal of the predicate
    from the ``Dockerfile`` spec's content_checks tuple.
    """
    _dockerfile_final_stage_pins_digest((_FIXTURE / "Dockerfile").read_bytes())


@pytest.mark.parametrize("forbidden", _FORBIDDEN_SUBPATHS)
def test_no_forbidden_subpaths(forbidden: str) -> None:
    assert_no_forbidden_subpath(_FIXTURE, forbidden)


def test_gitignore_covers_built_image_digest() -> None:
    """AC-23 — .gitignore includes built-image.digest entry."""
    text = (_FIXTURE / ".gitignore").read_text(encoding="utf-8")
    assert ".codegenie/" in text
    assert "built-image.digest" in text


def test_fixture_tree_is_closed_set() -> None:
    """AC-26 — tracked-files set == _FILE_SPECS relpath set.

    Uses ``git ls-files`` so the closed-set check honors .gitignore
    automatically — ``built-image.digest`` (written by regenerate.sh,
    gitignored per AC-23) does not dirty the set.
    """
    assert_tree_is_closed_set(_FIXTURE, _FILE_SPECS)


def test_readme_references_every_spec() -> None:
    """AC-29 — README mentions every spec.relpath and every consumer probe."""
    assert_readme_references_every_spec(_FIXTURE, _FILE_SPECS)
