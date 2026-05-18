"""S8-04 AC-7 — Phase 2 README has an exit-criteria sign-off section.

Asserts the appended `## Phase 2 exit-criteria — closed` section:

1. exists as an H2;
2. points at the canonical mapping table (`stories/README.md
   §"Exit-criteria coverage"`) via a markdown link with the
   `#exit-criteria-coverage` anchor;
3. carries exactly 10 `- [x]` checkbox lines (G1–G10) — NONE may be `- [ ]`;
4. each of G1..G10 is named at least once;
5. carries a sign-off line citing all four Step-8 stories (S8-01..S8-04).
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_README = _REPO_ROOT / "docs" / "phases" / "02-context-gather-layers-b-g" / "README.md"


def _signoff_section_text() -> str:
    """Return the body between the new H2 and the next H2 (or EOF)."""
    text = _README.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    end = len(lines)
    target = "## Phase 2 exit-criteria — closed"
    for idx, line in enumerate(lines):
        if line.strip() == target:
            start = idx
            continue
        if start is not None and line.startswith("## "):
            end = idx
            break
    if start is None:
        raise AssertionError(f"{_README}: missing '{target}' H2")
    return "\n".join(lines[start:end])


def test_signoff_section_well_formed() -> None:
    section = _signoff_section_text()

    # (1) H2 exists (implicit from _signoff_section_text not raising).
    # (2) Pointer to canonical table.
    assert "stories/README.md#exit-criteria-coverage" in section, (
        "missing pointer to canonical exit-criteria coverage table in stories/README.md."
    )
    assert "Exit-criteria coverage" in section, (
        "the pointer should name the canonical anchor 'Exit-criteria coverage'."
    )

    # (3) Exactly 10 `- [x]` lines, zero `- [ ]`.
    checked = [line for line in section.splitlines() if line.lstrip().startswith("- [x]")]
    unchecked = [line for line in section.splitlines() if line.lstrip().startswith("- [ ]")]
    assert len(checked) == 10, (
        f"expected exactly 10 `- [x]` checkboxes; got {len(checked)}: {checked}"
    )
    assert not unchecked, f"expected ZERO `- [ ]` checkboxes; got {len(unchecked)}: {unchecked}"

    # (4) Each of G1..G10 named at least once in the section.
    for n in range(1, 11):
        token = f"G{n}"
        assert re.search(rf"\b{token}\b", section), f"checklist missing reference to goal {token}"

    # (5) Sign-off line citing all four Step-8 story IDs.
    for sid in ("S8-01", "S8-02", "S8-03", "S8-04"):
        assert sid in section, f"sign-off section missing story ID {sid!r}"
