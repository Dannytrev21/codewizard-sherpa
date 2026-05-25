"""Phase-4 S3-05 — inverted-assertion test for the dirty fixtures (AC-9/10).

The fixtures live OUTSIDE ``tests/cassettes/`` so the CI walker
(``tests/security/test_cassettes_clean.py``) stays green. This test loads
each fixture directly via :func:`verify_cassette` and asserts the
sanitizer flagged at least one violation per shape — proof the scanner
is not silently passing on a known-bad payload.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.fallback.cassette.sanitizer import verify_cassette

_FIXTURES = Path(__file__).parent / "fixtures" / "intentionally_dirty_cassettes"


@pytest.mark.parametrize(
    "name",
    [
        "with_sk_ant.yaml",
        "with_cookie.yaml",
        "with_body_base64.yaml",
        "with_claude_underscore_prefix.yaml",
    ],
)
def test_dirty_fixture_fails_verification(name: str) -> None:
    """Each fixture under ``intentionally_dirty_cassettes/`` must fail."""
    path = _FIXTURES / name
    assert path.exists(), f"missing fixture: {path}"
    v = verify_cassette(path)
    assert v.passed is False, f"{name} unexpectedly passed verify_cassette"
    assert len(v.violations) >= 1


def test_every_fixture_is_covered_by_the_parametrize_list() -> None:
    """Mutation guard: a new fixture added to the dir must be added here too."""
    on_disk = {p.name for p in _FIXTURES.glob("*.yaml")}
    covered = {
        "with_sk_ant.yaml",
        "with_cookie.yaml",
        "with_body_base64.yaml",
        "with_claude_underscore_prefix.yaml",
    }
    assert on_disk == covered, f"fixture set diverged from parametrize: {on_disk ^ covered}"
