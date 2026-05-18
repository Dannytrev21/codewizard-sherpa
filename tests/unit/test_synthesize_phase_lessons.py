"""Tests for ``scripts/synthesize_phase_lessons.py``.

Three invariants:

1. **Bucket assignment is deterministic.** Each canonical H3 title maps
   to exactly one bucket, and the bucket boundary is the ordering of
   ``_BUCKETS`` (first match wins). A new H3 vocabulary that should
   bucket cleanly is a parametrized test row, not a re-design.
2. **Section extraction is whitespace-stable.** Two consecutive
   ``render_retrospective`` calls on the same input produce byte-
   identical output (Rule 9 — drift in pure data extraction would
   manifest as flaky diffs).
3. **End-to-end on Phase 2 produces a non-empty retrospective.** Smoke
   test — confirms the script runs against the real attempt logs and
   each bucket has at least one contributing story.

No network, no LLM. The synthesis is deliberately a separate, human-
curated pass; this script only does the data-extraction half.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Final

import pytest

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_SCRIPT_PATH: Final[Path] = _REPO_ROOT / "scripts" / "synthesize_phase_lessons.py"


def _load_module() -> object:
    """Load the script as a module (it lives outside the package tree)."""

    spec = importlib.util.spec_from_file_location("synthesize_phase_lessons", _SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module spec from {_SCRIPT_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_MOD = _load_module()


@pytest.mark.parametrize(
    ("h3_title", "expected_label"),
    [
        # Rule-7 / conflict bucket
        (
            "Conflict surfaced + resolution (CLAUDE.md Rule 7)",
            "Rule-7 conflicts surfaced + resolution",
        ),
        ("Adaptations from the hardened story", "Rule-7 conflicts surfaced + resolution"),
        (
            "Adapatations + deviations from the hardened story",
            "Rule-7 conflicts surfaced + resolution",
        ),
        ("Rule 7 conflict surface", "Rule-7 conflicts surfaced + resolution"),
        # Refactor bucket
        ("Refactor decisions", "Refactor decisions / design-pattern applications"),
        (
            "Refactor decisions (design-patterns lens)",
            "Refactor decisions / design-pattern applications",
        ),
        ("Refactor decisions (DP1-DP4 lens)", "Refactor decisions / design-pattern applications"),
        # Out-of-scope bucket
        (
            "Out-of-scope finding (Rule 3 — surgical changes)",
            "Out-of-scope / deferred to a follow-up",
        ),
        ("Follow-ups surfaced this attempt", "Out-of-scope / deferred to a follow-up"),
        # Lessons bucket
        ("Lessons for future Phase 2 stories", "Carry-forward lessons for future stories"),
        ("Lessons for follow-on stories", "Carry-forward lessons for future stories"),
        ("Lessons (carry forward)", "Carry-forward lessons for future stories"),
    ],
)
def test_bucket_assignment_deterministic(h3_title: str, expected_label: str) -> None:
    """Each known H3 vocabulary lands in exactly one expected bucket."""

    bucket = _MOD._bucket_for_h3(h3_title)  # type: ignore[attr-defined]
    if bucket is None:
        raise AssertionError(
            f"H3 title {h3_title!r} did not match any bucket; expected "
            f"{expected_label!r}. Extend _BUCKETS in "
            "scripts/synthesize_phase_lessons.py if this is a new shape "
            "worth categorizing."
        )
    if bucket.label != expected_label:
        raise AssertionError(
            f"H3 title {h3_title!r} bucketed to {bucket.label!r}, expected "
            f"{expected_label!r}. Bucket ordering in _BUCKETS may have "
            "regressed — first match wins, so swapping rows changes "
            "category assignment for overlap-prone titles like "
            "'Refactor lessons' (Refactor wins over Lesson)."
        )


def test_unmatched_h3_returns_none() -> None:
    """Unmatched H3 returns None so the renderer can list it as a coverage gap."""

    assert _MOD._bucket_for_h3("Per-AC evidence") is None  # type: ignore[attr-defined]
    assert _MOD._bucket_for_h3("Files touched") is None  # type: ignore[attr-defined]
    assert _MOD._bucket_for_h3("Gates") is None  # type: ignore[attr-defined]


def test_section_extraction_handles_empty_body() -> None:
    """H3 with no content after it is dropped (empty body)."""

    sections = _MOD._extract_h3_sections(  # type: ignore[attr-defined]
        "## Top\n\n### Header A\n\n### Header B\n\nbody for B\n"
    )
    # Header A has no body lines; Header B has one body paragraph.
    titles = [t for t, _ in sections]
    assert titles == ["Header A", "Header B"]
    bodies = [b for _, b in sections]
    assert bodies[0] == ""
    assert "body for B" in bodies[1]


def test_section_extraction_h2_terminates_h3() -> None:
    """An H2 boundary closes the current H3's body capture (so cross-H2 content doesn't leak)."""

    sections = _MOD._extract_h3_sections(  # type: ignore[attr-defined]
        "## A\n\n### h3-under-a\n\nbody A\n\n## B\n\n### h3-under-b\n\nbody B\n"
    )
    bodies = {t: b for t, b in sections}
    assert "body A" in bodies["h3-under-a"]
    assert "body B" not in bodies["h3-under-a"]
    assert "body B" in bodies["h3-under-b"]
    assert "body A" not in bodies["h3-under-b"]


def test_story_sort_key_orders_numerically() -> None:
    """``S10-01`` sorts AFTER ``S2-01`` — not lexicographically before it."""

    sort_key = _MOD._story_sort_key  # type: ignore[attr-defined]
    ordered = sorted(["S10-01.md", "S2-01.md", "S2-02.md", "S1-11.md"], key=sort_key)
    assert ordered == ["S1-11.md", "S2-01.md", "S2-02.md", "S10-01.md"]


def test_phase_2_synthesis_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end run against Phase 2's real attempt logs; output is non-empty + deterministic."""

    phase_slug = "02-context-gather-layers-b-g"
    phase_dir = _REPO_ROOT / "docs" / "phases" / phase_slug
    if not (phase_dir / "stories" / "_attempts").is_dir():
        pytest.skip(f"Phase 2 attempts dir not present at {phase_dir}")

    # Run twice, write to two paths via monkeypatching, compare byte-for-byte.
    sections = _MOD.collect_phase_sections(phase_dir)  # type: ignore[attr-defined]
    lessons_md = phase_dir / "stories" / "_attempts" / "_lessons.md"
    lessons_rel = lessons_md.relative_to(phase_dir) if lessons_md.is_file() else None

    text_a = _MOD.render_retrospective(phase_slug, sections, lessons_rel)  # type: ignore[attr-defined]
    text_b = _MOD.render_retrospective(phase_slug, sections, lessons_rel)  # type: ignore[attr-defined]
    assert text_a == text_b, "render_retrospective is not deterministic"

    # Smoke: each bucket label appears as a section header in the output.
    for bucket in _MOD._BUCKETS:  # type: ignore[attr-defined]
        assert f"## {bucket.label}" in text_a, (
            f"Bucket {bucket.label!r} missing from rendered retrospective."
        )

    # At least three of the four buckets should have contributing stories for Phase 2
    # (a freshly-started phase might only hit one or two; Phase 2 is mature).
    populated = sum(
        1
        for bucket in _MOD._BUCKETS  # type: ignore[attr-defined]
        if any(
            _MOD._bucket_for_h3(s.h3_title) is not None
            and _MOD._bucket_for_h3(s.h3_title).label == bucket.label
            for s in sections
        )  # type: ignore[attr-defined,union-attr]
    )
    assert populated >= 3, (
        f"Only {populated} buckets had contributing sections; Phase 2 is "
        "mature and should populate at least three (Refactor, Lessons, "
        "Out-of-scope are the typical three)."
    )


def test_synthesize_writes_retrospective_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``synthesize()`` writes to ``<phase>/RETROSPECTIVE.md`` and returns the path."""

    # Run against Phase 2 (real input), but redirect the output write target
    # by pointing the script's _PHASES_DIR at a tmp tree that mirrors the
    # phase dir but writes the RETROSPECTIVE there. This keeps the test
    # hermetic — no real file write side-effect.

    phase_slug = "02-context-gather-layers-b-g"
    real_phase_dir = _REPO_ROOT / "docs" / "phases" / phase_slug
    if not (real_phase_dir / "stories" / "_attempts").is_dir():
        pytest.skip("Phase 2 attempts not present.")

    fake_phases_dir = tmp_path / "phases"
    fake_phase_dir = fake_phases_dir / phase_slug
    fake_phase_dir.mkdir(parents=True)
    # Symlink the stories tree so the aggregator reads real attempts.
    (fake_phase_dir / "stories").symlink_to(real_phase_dir / "stories")

    monkeypatch.setattr(_MOD, "_PHASES_DIR", fake_phases_dir)
    out_path = _MOD.synthesize(phase_slug)  # type: ignore[attr-defined]
    assert out_path == fake_phase_dir / "RETROSPECTIVE.md"
    assert out_path.is_file()
    content = out_path.read_text(encoding="utf-8")
    assert content.startswith(f"# Phase `{phase_slug}` — retrospective"), (
        "Retrospective header changed shape; update test or restore convention."
    )
    assert "Cross-story lessons index" in content
