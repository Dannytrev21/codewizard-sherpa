"""S8-04 AC-10a — the THREE Step-8 done-criteria boxes this story owns are checked.

The other five Step-8 boxes belong to S8-01/02/03 and are intentionally NOT
asserted here (see ``test_step8_other_boxes_closed.py`` for the soft check).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HIGH_LEVEL = _REPO_ROOT / "docs" / "phases" / "02-context-gather-layers-b-g" / "High-level-impl.md"

_OWNED_LINE_SUBSTRINGS: tuple[str, ...] = (
    "All five Phase-3 handoff issues",
    "mkdocs build --strict",
    "checklist marked complete",
)


def _step8_section() -> str:
    """Return the body of `## Step 8 ...` (until the next H2 or EOF)."""
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


def test_three_owned_boxes_checked() -> None:
    section = _step8_section()
    s8_04_lines = [
        line
        for line in section.splitlines()
        if line.lstrip().startswith("- [") and "(S8-04)" in line
    ]
    assert len(s8_04_lines) == 3, (
        f"expected exactly 3 Step-8 done-criteria lines tagged (S8-04); "
        f"got {len(s8_04_lines)}: {s8_04_lines}"
    )
    for required in _OWNED_LINE_SUBSTRINGS:
        matching = [line for line in s8_04_lines if required in line]
        assert len(matching) == 1, (
            f"expected exactly one S8-04 line containing {required!r}; "
            f"got {len(matching)}: {matching}"
        )
        line = matching[0]
        assert "[x]" in line, f"S8-04 line not checked: {line!r}"
        assert line.rstrip().endswith("(S8-04)"), (
            f"S8-04 line must end with the literal '(S8-04)' annotation; got: {line!r}"
        )
