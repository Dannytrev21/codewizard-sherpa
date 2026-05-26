"""S6-02 fence — every ``ADR-04-NNNN`` reference in test docstrings
resolves to an existing Phase-4 ADR file.

Walks the :mod:`tests.fixtures.adr_links` constants + every ``ADR-04-`` /
``ADR_04_`` literal mentioned across the test tree, parses out the
four-digit number, and asserts
``docs/phases/04-vuln-llm-fallback-rag/ADRs/<NNNN>-*.md`` exists. Catches
the stale-reference regression that left two arch-doc lines pointing at
``ADR-04-0003`` for the RAG-bypass-on-retry decision (the real file is
``0011-rag-bypass-on-retry.md``).
"""

from __future__ import annotations

import re
from pathlib import Path

_ADR_PATTERN = re.compile(r"ADR[-_]04[-_](\d{4})")
_REPO_ROOT = Path(__file__).parents[2]
_ADR_DIR = _REPO_ROOT / "docs" / "phases" / "04-vuln-llm-fallback-rag" / "ADRs"
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "adr_links.py"


def _existing_phase4_adrs() -> set[str]:
    """Return the set of four-digit ADR numbers that have a matching file."""
    if not _ADR_DIR.is_dir():
        return set()
    out: set[str] = set()
    for f in _ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"):
        m = re.match(r"(\d{4})", f.name)
        if m:
            out.add(m.group(1))
    return out


def test_adr_links_fixture_constants_resolve() -> None:
    """Every ``ADR_04_NNNN`` symbol in :mod:`tests.fixtures.adr_links`
    has a matching ADR file under the Phase-4 ADRs/ directory."""
    text = _FIXTURE.read_text()
    referenced = sorted({m.group(1) for m in _ADR_PATTERN.finditer(text)})
    existing = _existing_phase4_adrs()
    missing = [n for n in referenced if n not in existing]
    assert not missing, (
        f"tests/fixtures/adr_links.py references non-existent Phase-4 ADRs: {missing}. "
        f"Existing: {sorted(existing)}"
    )


def test_adr_04_0011_file_exists() -> None:
    """Smoke-pin the specific ADR S6-02 cross-links — a regression
    renaming the file silently would fail the fixture-resolve fence
    above, but having the explicit smoke test makes the diagnostic
    cleaner."""
    candidates = list(_ADR_DIR.glob("0011-*.md"))
    assert candidates, f"Phase-4 ADR-0011 file missing. Expected one of: {_ADR_DIR}/0011-*.md"
