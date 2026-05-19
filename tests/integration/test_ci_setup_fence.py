"""AC-15 — CI setup fence.

Greps ``.github/workflows/*.yml`` for ``bubblewrap`` / ``bwrap``. The test
``xfail``-s today (S9-01 owns the CI YAML edit); once S9-01 lands, the
``xfail`` flips to a hard fail-if-missing — the absence of the
``apt-get install -y bubblewrap`` step would block CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github/workflows"


def _workflows_mention_bubblewrap() -> bool:
    if not _WORKFLOWS_DIR.is_dir():
        return False
    for yml in _WORKFLOWS_DIR.glob("*.yml"):
        text = yml.read_text(encoding="utf-8", errors="ignore")
        if "bubblewrap" in text or "bwrap" in text:
            return True
    return False


def test_ci_yaml_installs_bubblewrap() -> None:
    """Once S9-01 lands the CI YAML edit, this assertion is the hard gate.
    Until then, the assertion ``xfail``-s with a structured TODO.
    """
    if not _workflows_mention_bubblewrap():
        pytest.xfail(
            "S9-01 pending — CI YAML edit deferred. Required step on Linux jobs: "
            "`apt-get install -y bubblewrap`. When S9-01 lands, remove this xfail; "
            "the assertion below becomes the gate."
        )
    assert _workflows_mention_bubblewrap()
