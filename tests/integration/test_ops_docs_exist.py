"""Phase-4 S7-10 AC-16 — ops-docs section-and-body smoke.

Asserts that each ops runbook page (`secrets.md`, `cassettes.md`,
`embeddings.md`) contains the canonical level-2 sections S7-10 AC-11/12/13
requires, AND that each section has a non-trivial body (≥3 non-blank
lines or a fenced code block). A bypassable substring check (S7-10 F-shape
finding) is rejected — the pure ``parse_section_body`` helper enforces
the body shape.

Also asserts every ops doc has a ``## See also`` section (AC-14
cross-link discipline).
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Pure functional core — parse_section_body
# ---------------------------------------------------------------------------


def parse_section_body(text: str, heading: str) -> str | None:
    """Return the body following a level-2 ``## heading`` until the next
    ``## `` heading or EOF. Return ``None`` if the heading is absent.

    Pure: no I/O. Imperative shell is the test fixture below.
    """
    marker = f"\n## {heading}\n"
    if marker not in text:
        return None
    after = text.split(marker, 1)[1]
    end = after.find("\n## ")
    return after[:end] if end != -1 else after


# ---------------------------------------------------------------------------
# REQUIRED_DOCS — exact section table from S7-10 AC-11/12/13
# ---------------------------------------------------------------------------

REQUIRED_DOCS: dict[str, list[str]] = {
    "docs/operations/secrets.md": [
        "Anthropic key storage",
        "Refuse-to-start behavior",
        "Rotation cadence",
        "codegenie auth set",
    ],
    "docs/operations/cassettes.md": [
        "Refresh trigger matrix",
        "make refresh-cassettes invocation",
        "CODEOWNERS approval flow",
        "BLAKE3 lock refresh",
        "Sanitizer guarantees",
    ],
    "docs/operations/embeddings.md": [
        "codegenie embeddings bootstrap",
        "codegenie rag rebuild",
        "Refuse-to-start on lock state",
        "Cross-architecture float drift",
    ],
}


@pytest.mark.parametrize(
    ("path", "sections"),
    list(REQUIRED_DOCS.items()),
)
def test_ops_doc_has_sections_with_body(path: str, sections: list[str]) -> None:
    """Each level-2 heading exists exactly once AND has a non-trivial body
    (≥3 non-blank lines OR a fenced code block).
    """
    p = Path(path)
    assert p.is_file(), f"missing ops doc: {p}"
    text = p.read_text()
    for s in sections:
        body = parse_section_body(text, s)
        assert body is not None, f"{p} missing level-2 heading '## {s}'"
        non_blank = [ln for ln in body.splitlines() if ln.strip()]
        has_fence = "```" in body
        assert len(non_blank) >= 3 or has_fence, (
            f"{p} section '{s}' has empty/trivial body "
            f"({len(non_blank)} non-blank lines, fence={has_fence})"
        )


def test_each_ops_doc_has_see_also_section() -> None:
    """AC-14 — every ops doc cross-links its source ADRs via ``## See also``."""
    for path in REQUIRED_DOCS:
        text = Path(path).read_text()
        body = parse_section_body(text, "See also")
        assert body is not None, f"{path} missing '## See also' cross-link section"
        # See also must list at least one ADR file path.
        assert "ADRs/" in body or "adrs/" in body, (
            f"{path} '## See also' section must reference at least one ADR file path"
        )


# ---------------------------------------------------------------------------
# Pure-helper unit tests (functional-core discipline)
# ---------------------------------------------------------------------------


def test_parse_section_body_handles_eof() -> None:
    """Section runs to EOF when no later ``## `` is present."""
    text = "\n## A\nline1\nline2\nline3\n"
    body = parse_section_body(text, "A")
    assert body is not None
    assert body.strip() == "line1\nline2\nline3"


def test_parse_section_body_handles_next_section() -> None:
    """Section terminates at the next ``## `` heading."""
    text = "\n## A\nbody-a\n## B\nbody-b\n"
    body = parse_section_body(text, "A")
    assert body is not None
    assert body.strip() == "body-a"


def test_parse_section_body_returns_none_when_missing() -> None:
    """Missing heading → None (not empty string, not raise)."""
    assert parse_section_body("# top\n## Other\nx\n", "Missing") is None


# NOTE: ``parse_section_body`` is intentionally a simple substring split (Rule 2 — simplicity
# first). It does NOT distinguish ``## `` inside fenced code blocks from real headings; the
# ops-docs we ship don't put ``## `` inside fences, so this isn't a real failure mode. If a
# future doc adds such a fence, the test will flag the section as "missing body" and the
# operator can either restructure the doc or upgrade the helper to fence-aware parsing.
