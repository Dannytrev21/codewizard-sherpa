"""S1-11 — Phase 2 ADR inventory + README listing (AC-6, AC-7, AC-11).

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S1-11-forbidden-patterns-mypy-adrs.md``
  §AC-6, §AC-7, §AC-11 (LOCKED — REQUIRED_ADRS = 0001..0009; 0010 tolerated,
  not asserted in existence test).
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md
  §"Path to production end state"`` — source of truth for the nine ADRs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ADR_DIR = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "phases"
    / "02-context-gather-layers-b-g"
    / "ADRs"
)
README = ADR_DIR.parent / "README.md"

# Step-1 nine — 0010 is intentionally excluded (file may exist; not required;
# enforcement code lands in S3-02 per AC-11 lock).
REQUIRED_ADRS = [
    "0001-add-docker-and-security-cli-tools-to-allowed-binaries.md",
    "0002-tree-sitter-grammars-phase-2-amendment.md",
    "0003-coordinator-heaviness-sort-annotation.md",
    "0004-image-digest-as-declared-input-token.md",
    "0005-secret-findings-no-plaintext-persistence.md",
    "0006-index-freshness-sum-type-location.md",
    "0007-no-plugin-loader-in-phase-2.md",
    "0008-no-event-stream-in-phase-2.md",
    "0009-pytest-xdist-veto-preserved.md",
]

NYGARD_SECTIONS = (
    "## Context",
    "## Options considered",
    "## Decision",
    "## Tradeoffs",
    "## Pattern fit",
    "## Consequences",
    "## Reversibility",
    "## Evidence / sources",
)


@pytest.mark.parametrize("name", REQUIRED_ADRS)
def test_adr_file_exists_and_nygard_shape(name: str) -> None:
    """AC-6 — every Step-1 ADR has all 8 Nygard sections + ``Status: Accepted``."""
    path = ADR_DIR / name
    assert path.exists(), f"missing ADR: {name}"
    text = path.read_text(encoding="utf-8")
    for section in NYGARD_SECTIONS:
        assert section in text, f"{name} missing Nygard section: {section}"
    assert "**Status:** Accepted" in text, (
        f"{name} is not marked Accepted (Draft ADRs are rejected at Step-1 gate)"
    )


def test_phase2_readme_lists_every_step1_adr() -> None:
    """AC-7 — README has an ADR-listing section; every Step-1 ADR appears."""
    readme_text = README.read_text(encoding="utf-8")
    for name in REQUIRED_ADRS:
        adr_id = name.split("-", 1)[0]  # "0001"
        assert adr_id in readme_text or name in readme_text, (
            f"docs/phases/02-context-gather-layers-b-g/README.md does not link ADR {name}"
        )


def test_phase2_readme_marks_0010_as_pre_drafted() -> None:
    """AC-7, AC-11 — 02-ADR-0010 file already exists in the tree but its
    enforcement code ships in S3-02. The README's ADR list MUST disambiguate
    this so a reader doesn't assume 0010 is Step-1-active.
    """
    readme_text = README.read_text(encoding="utf-8")
    assert "0010" in readme_text, "README must reference 0010 to explain its pre-drafted status"
    assert "S3-02" in readme_text or "Step 3" in readme_text or "Step-3" in readme_text, (
        "README's 0010 entry must mark it as a Step-3 deliverable (enforcement code)"
    )
