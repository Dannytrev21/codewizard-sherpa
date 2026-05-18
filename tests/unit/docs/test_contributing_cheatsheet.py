"""Unit tests for S8-04 AC-6 — the `docs/contributing.md` Layer B/C/D/E/G addendum.

The new content is an **H3 subsection** under the existing `## Adding a probe`
H2 (line ~69), NOT a parallel H2. Rule 7 — surface the conflict, don't blend.
The existing 7-step recipe (citing `LanguageDetectionProbe` from Phase 0)
stays untouched; the new H3 names what Phase 2 added and points at canonical
Phase 2 probes as examples to copy.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRIBUTING = _REPO_ROOT / "docs" / "contributing.md"


def _adding_a_probe_section() -> str:
    """Return the body between the existing `## Adding a probe` H2 and the next H2."""
    text = _CONTRIBUTING.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    end = len(lines)
    for idx, line in enumerate(lines):
        if line.strip() == "## Adding a probe":
            start = idx
            continue
        if start is not None and line.startswith("## "):
            end = idx
            break
    if start is None:
        raise AssertionError("docs/contributing.md: missing '## Adding a probe' H2")
    return "\n".join(lines[start:end])


def test_subsection_under_existing_h2() -> None:
    section = _adding_a_probe_section()

    # AC-6 (1): the new H3 is present *within* the existing H2's section.
    new_h3 = "### Adding a Layer B/C/D/E/G probe (Phase 2 additions)"
    assert new_h3 in section, (
        f"missing new H3 {new_h3!r} under '## Adding a probe' in {_CONTRIBUTING}"
    )

    # AC-6 (2): all seven topics named.
    for topic in (
        "heaviness",
        "run_external_cli",
        "run_allowlisted",
        "@register_index_freshness_check",
        "model_construct",
        "declared_inputs",
        "confidence",
    ):
        assert topic in section, f"new H3 missing topic literal {topic!r}"

    # `model_construct` must be flagged as banned (under output/).
    assert "model_construct" in section
    assert "ban" in section.lower() or "forbidden" in section.lower(), (
        "the model_construct mention should call out the ban"
    )

    # AC-6 (3): all five canonical Phase-2 probes cited.
    for probe in (
        "IndexHealthProbe",
        "RuntimeTraceProbe",
        "SemgrepProbe",
        "SkillsIndexProbe",
        "ConventionsProbe",
    ):
        assert probe in section, f"new H3 missing canonical probe example {probe!r}"

    # AC-6 (4): the existing Phase-0 7-step recipe (citing `LanguageDetectionProbe`)
    # is preserved.
    assert "LanguageDetectionProbe" in section, (
        "the existing Phase-0 recipe (citing LanguageDetectionProbe) appears to "
        "have been edited away — the H3 must be additive."
    )

    # AC-6 (5): no parallel H2 introduced.
    text = _CONTRIBUTING.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("## ") and "Adding a Layer" in line:
            raise AssertionError(
                f"a parallel H2 was introduced: {line!r}. The new content must "
                "be an H3 (`### Adding a Layer B/C/D/E/G probe ...`), not a "
                "second top-level H2."
            )

    # AC-6 (6): both run_external_cli and run_allowlisted are named (the
    # wrapper vs direct distinction the cheat-sheet teaches).
    assert "run_external_cli" in section
    assert "run_allowlisted" in section
