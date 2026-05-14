"""Doc-grep test for ADR-0002 S1-08 amendment (AC-22)."""

from __future__ import annotations

from pathlib import Path


def test_adr_0002_records_s1_08_landing() -> None:
    body = Path(
        "docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md"
    ).read_text()
    assert "content_hash" in body
    assert "S1-08" in body
    assert "compute_input_snapshot" in body
