"""Phase-4 S7-08 — diff-allow-list final-verification gate.

Walks ``git diff --name-only $(git merge-base master HEAD)..HEAD`` and
asserts every changed path lives in at least one allow-list bucket.
Refuses to silently expand the buckets (Rule 12 — fail loud). A path
outside the allow-list surfaces with a structured diagnostic naming
the violator list + the bucket-classification map.

The same allow-list serves both this gate and the story's AC-5 prose
documentation; the two MUST stay byte-equal (a future PR that adds a
new bucket must update both the test file and the AC-5 entry).

AC-7 — on the master branch (HEAD == merge-base), there is no diff
to gate, so the test ``pytest.skip``s with a structured reason.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import pytest

# AC-5 — the canonical allow-list (in lockstep with the story prose).
ALLOWED_PREFIXES: Final[tuple[str, ...]] = (
    "src/codegenie/fallback/",
    "src/codegenie/rag/",
    "src/codegenie/workflows/",  # Phase-6 sibling; harmless on Phase-4 diff
    "plugins/vulnerability-remediation--node--npm/",
    "tests/",
    "docs/phases/04-vuln-llm-fallback-rag/",
    "docs/phases/06-sherpa-vuln-loop/",  # Phase-6 sibling
)

ALLOWED_EXACT: Final[frozenset[str]] = frozenset(
    {
        "pyproject.toml",
        "uv.lock",
        ".importlinter",
        "Makefile",
        "CODEOWNERS",
        ".codeowners",
        ".github/workflows/ci.yml",
        "docs/operations/secrets.md",
        "docs/operations/cassettes.md",
        "docs/operations/embeddings.md",
        # Phase-4 kernel-allowlist additions allowed by S1-05's
        # path-scoped fence amendment (see _fence.py + the
        # kernel-frozen fence's _KERNEL_ALLOWLIST):
        "src/codegenie/_fence.py",
        "src/codegenie/cli.py",
        "src/codegenie/output/sanitizer.py",
        "src/codegenie/plugins/events.py",
        "src/codegenie/types/__init__.py",
        "src/codegenie/types/datetime.py",
        "src/codegenie/types/identifiers.py",
        "src/codegenie/types/parsers.py",
        "src/codegenie/logging.py",
        # Phase-6 baseline file (S1-07) — tests/fence is already a
        # prefix bucket, but the data file at the top of tests/fence
        # also fits the test prefix.
    }
)


# AC-9 — pure helper extracted for table-tested classification.
def _classify(
    path: str, prefixes: Sequence[str], exact: frozenset[str]
) -> bool:
    """Return True iff ``path`` lives in an allow-list bucket."""
    if path in exact:
        return True
    return any(path.startswith(p) for p in prefixes)


def _merge_base() -> str | None:
    """Return the merge-base sha against `master`, or None if unresolvable."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "master", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _diff_paths(base_sha: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_sha}..HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


# AC-5/AC-6 live gate.


def test_phase4_diff_within_allow_list(tmp_path: Path) -> None:
    """Every path touched by the current branch lives in an allow-list
    bucket. A violator surfaces with the structured diagnostic AC-6
    requires."""
    base = _merge_base()
    if base is None:
        pytest.skip("merge-base not resolvable (detached HEAD or missing master)")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    # AC-7 — no-op skip when HEAD == merge-base.
    if base == head:
        pytest.skip(
            "running on master/empty-diff branch; nothing to gate "
            "(merge-base == HEAD)"
        )
    paths = _diff_paths(base)
    classification = {p: _classify(p, ALLOWED_PREFIXES, ALLOWED_EXACT) for p in paths}
    # AC-12 — full classification artifact for reviewer audit.
    artifact = tmp_path / "phase4-diff-paths.txt"
    artifact.write_text(
        "\n".join(f"{'OK' if v else 'VIOLATOR'} {p}" for p, v in classification.items()),
        encoding="utf-8",
    )
    violators = [p for p, ok in classification.items() if not ok]
    assert not violators, (
        f"{len(violators)} path(s) outside the Phase-4 allow-list: "
        f"{violators}. Either fit a bucket via ADR-0003 amendment or "
        f"revert the change. Full classification map at {artifact}."
    )


# AC-8 — vacuous-allow-list invariants.


def test_allowed_prefixes_are_non_empty_and_rooted() -> None:
    for prefix in ALLOWED_PREFIXES:
        assert prefix, "empty prefix"
        assert prefix != "/", "vacuous '/' prefix"
        assert prefix.endswith("/"), f"prefix {prefix!r} must end with '/'"


def test_allowed_exact_are_non_empty_and_not_root() -> None:
    for path in ALLOWED_EXACT:
        assert path, "empty exact path"
        assert not path.startswith("/"), f"exact path {path!r} must not start with '/'"


# AC-9 — planted-violation table tests for the pure classifier.


@pytest.mark.parametrize(
    "path,expected_inside",
    [
        # Inside (allow-listed):
        ("src/codegenie/fallback/leaf/anthropic_adapter.py", True),
        ("src/codegenie/rag/store.py", True),
        ("tests/unit/fallback/test_x.py", True),
        ("pyproject.toml", True),
        ("docs/phases/04-vuln-llm-fallback-rag/foo.md", True),
        ("plugins/vulnerability-remediation--node--npm/__init__.py", True),
        # Outside (NOT allow-listed — would surface as a violator):
        ("src/codegenie/probes/_dummy.py", False),
        ("src/codegenie/coordinator/_dummy.py", False),
        ("src/codegenie/cache/_dummy.py", False),
        ("src/codegenie/schema/repo_context.schema.json", False),
        ("src/codegenie/plugins/protocols.py", False),
        ("src/codegenie/transforms/recipe_engine.py", False),
    ],
)
def test_classify_planted_inputs(path: str, expected_inside: bool) -> None:
    assert _classify(path, ALLOWED_PREFIXES, ALLOWED_EXACT) is expected_inside, (
        f"Classifier verdict for {path!r} disagrees with planted expectation "
        f"{expected_inside!r}"
    )
