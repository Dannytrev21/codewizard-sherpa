"""S1-10 AC-3 / AC-3b — pin the per-probe sub-schema convention doc.

The doc at ``src/codegenie/schema/probes/_subschema_convention.md`` is the
human-facing rationale for three ADRs (0004, 0007, 0010) every Phase-1
sub-schema must conform to. The structural enforcement of those rules
lives in ``tests/unit/test_sub_schemas.py`` (landing in S2-01); this test
pins the doc itself so the convention is not load-bearing as prose alone.
"""

from __future__ import annotations

from pathlib import Path


def test_subschema_convention_doc_exists_and_links_adrs() -> None:
    doc = Path("src/codegenie/schema/probes/_subschema_convention.md")
    assert doc.exists(), "convention doc must live alongside the sub-schemas"
    text = doc.read_text(encoding="utf-8")

    # The three load-bearing ADRs are linked by filename.
    assert "0004-per-probe-subschema-additional-properties-false" in text
    assert "0007-warnings-id-pattern" in text
    assert "0010-layer-a-slices-optional-at-envelope" in text

    # The WarningId regex is quoted verbatim.
    assert "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$" in text

    # The canonical fragment is present, not merely described.
    assert '"additionalProperties": false' in text

    # The enforcing test is named so the doc is not load-bearing alone.
    assert "test_sub_schemas.py" in text

    # The doc stays a reference, not a tutorial.
    line_count = sum(1 for _ in text.splitlines())
    assert line_count <= 80, f"convention doc is {line_count} lines; cap is 80"
