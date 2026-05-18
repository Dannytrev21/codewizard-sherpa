"""S8-04 AC-10b — soft check that other Step-8 done-criteria boxes are closed.

Intentionally soft: S8-04 lands before S8-01/02/03 may have closed all their
boxes; this test warns rather than fails so S8-04's executor pass doesn't
get coupled to the other stories' completion. The closing-PR's manual
checklist is the hard gate.
"""

from __future__ import annotations

import warnings
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HIGH_LEVEL = _REPO_ROOT / "docs" / "phases" / "02-context-gather-layers-b-g" / "High-level-impl.md"


def _step8_section() -> str:
    text = _HIGH_LEVEL.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    end = len(lines)
    for idx, line in enumerate(lines):
        if line.startswith("## Step 8"):
            start = idx
            continue
        if start is not None and line.startswith("## "):
            end = idx
            break
    if start is None:
        raise AssertionError(f"{_HIGH_LEVEL}: missing '## Step 8 ...' H2")
    return "\n".join(lines[start:end])


def test_other_boxes_warn_if_unchecked() -> None:
    section = _step8_section()
    unchecked = [line for line in section.splitlines() if line.lstrip().startswith("- [ ]")]
    if unchecked:
        warnings.warn(
            f"Step 8 has {len(unchecked)} unchecked done-criteria boxes "
            f"(owned by S8-01/02/03): {unchecked}",
            UserWarning,
            stacklevel=2,
        )
    # Always pass — soft assertion only.
