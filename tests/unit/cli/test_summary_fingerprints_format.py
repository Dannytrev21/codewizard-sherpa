"""S8-02 AC-3 — fingerprints stdout line: 8-hex only, sorted, dedup.

Property-based + targeted tests covering the line's format regex
(``^fingerprints=\\[(?:[0-9a-f]{8}(?:, [0-9a-f]{8})*)?\\]$``) — never
plaintext, never a hash longer than 8 hex. The plaintext-boundary
integration test lives at
``tests/integration/cli/test_summary_plaintext_boundary.py``; this file
is the unit-level format-and-sort check.
"""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from codegenie.cli_summary import summary_block

_FP_LINE_RE = re.compile(r"^fingerprints=\[(?:[0-9a-f]{8}(?:, [0-9a-f]{8})*)?\]$")

_HEX8 = st.text(alphabet="0123456789abcdef", min_size=8, max_size=8)


def test_fingerprints_format_regex_empty() -> None:
    block = summary_block(count=0, fingerprints=(), shadowed=())
    assert _FP_LINE_RE.match(block.fingerprints_line)


def test_fingerprints_format_regex_three_known() -> None:
    block = summary_block(
        count=3,
        fingerprints=("cafef00d", "abcdef01", "12345678"),
        shadowed=(),
    )
    assert _FP_LINE_RE.match(block.fingerprints_line)
    assert block.fingerprints_line == "fingerprints=[12345678, abcdef01, cafef00d]"


@given(st.lists(_HEX8, min_size=0, max_size=30))
def test_fingerprints_format_regex_property(fps: list[str]) -> None:
    """Any list of 8-hex strings produces a regex-conforming line."""
    block = summary_block(count=len(fps), fingerprints=fps, shadowed=())
    assert _FP_LINE_RE.match(block.fingerprints_line), block.fingerprints_line


@given(st.lists(_HEX8, min_size=1, max_size=30))
def test_fingerprints_line_sorted_unique(fps: list[str]) -> None:
    """The fingerprints body parses to a sorted unique list."""
    block = summary_block(count=len(fps), fingerprints=fps, shadowed=())
    body = block.fingerprints_line[len("fingerprints=[") : -1]
    parsed = body.split(", ")
    assert parsed == sorted(set(fps))
