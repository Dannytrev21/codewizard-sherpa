"""S6-08 fence — pin ``AttemptAnchor.schema_version`` to ``Literal[1]``
and refuse a bump to 2 until a co-existence integration test exists.

ADR-04-0017 demands one full release cycle of coexistence before any
schema migration. This fence makes that machine-enforced: bumping the
default away from 1 (without also creating
``tests/integration/test_attempt_anchor_v1_v2_coexist.py``) fails CI.
"""

from __future__ import annotations

import subprocess
from typing import Literal, get_args

from codegenie.fallback.attempt_anchor import AttemptAnchor


def _git_tracks(path: str) -> bool:
    """Return True if ``path`` is tracked by git from the repo root."""
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def test_schema_version_field_is_literal_one() -> None:
    """``schema_version`` is ``Literal[1]`` with default 1 — pinned at
    the type-system level so a bump must edit the type AND the default
    AND this fence simultaneously."""
    field = AttemptAnchor.model_fields["schema_version"]
    assert field.default == 1
    assert get_args(field.annotation) == get_args(Literal[1])


def test_schema_bump_requires_coexistence_integration_test() -> None:
    """If ``schema_version`` ever defaults to ``> 1``, a co-existence
    integration test MUST exist alongside the bump. The integration
    test path is the dam — its absence keeps the bump locked behind
    explicit migration work, never a one-line edit."""
    if AttemptAnchor.model_fields["schema_version"].default == 1:
        return
    assert _git_tracks("tests/integration/test_attempt_anchor_v1_v2_coexist.py"), (
        "AttemptAnchor.schema_version default bumped above 1 but the "
        "coexistence integration test does not exist; create "
        "tests/integration/test_attempt_anchor_v1_v2_coexist.py and pin "
        "the v1↔v2 read/write contract before this fence will pass."
    )
