"""Synthesize a phase RETROSPECTIVE.md from per-story attempt logs.

Walks ``docs/phases/{phase}/stories/_attempts/_lessons.md`` and every
``docs/phases/{phase}/stories/_attempts/S*.md`` for the named phase,
extracts H2 / H3 sections by keyword bucket, and emits
``docs/phases/{phase}/RETROSPECTIVE.md`` — a structured roll-up the next
phase's planner / validator / executor can read.

Five buckets (data-driven; add a row to ``_BUCKETS`` to extend):

1. **Cross-story lessons** — `_lessons.md` H2 blocks, deduplicated by ID.
2. **Rule-7 conflicts** — per-story sections whose H3 mentions
   "conflict", "adaptation", "deviation", or "Rule 7".
3. **Refactor decisions** — per-story sections whose H3 starts with
   "Refactor".
4. **Deferred / out-of-scope** — per-story sections whose H3 contains
   "Out-of-scope", "Follow-up", or "Carry forward".
5. **Lessons-for-follow-on** — per-story sections whose H3 contains
   "Lesson".

The script is **pure aggregation**: no LLM, no judgment, no re-ranking.
The output is the curation surface a human (or a downstream Claude
session) edits into a synthesis. Determinism: running the script twice
on the same input produces byte-identical output.

Run with::

    python scripts/synthesize_phase_lessons.py \\
        --phase 02-context-gather-layers-b-g

The phase argument is the folder name under ``docs/phases/`` (not the
phase number — phases like ``06.5-...`` would be ambiguous).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_PHASES_DIR: Final[Path] = _REPO_ROOT / "docs" / "phases"

_STORY_FILENAME_RE: Final[re.Pattern[str]] = re.compile(r"^S(\d+)-(\d+)\.md$")
_H2_RE: Final[re.Pattern[str]] = re.compile(r"^## (?!#)(.+)$")
_H3_RE: Final[re.Pattern[str]] = re.compile(r"^### (?!#)(.+)$")


@dataclass(frozen=True)
class Bucket:
    """One categorization rule.

    ``label`` is the rendered section title in the retrospective. ``patterns``
    is matched case-insensitively against H3 titles (an H3 matches if ANY
    pattern is a substring). Mutually-exclusive: the first bucket that matches
    wins, so order the patterns from most-specific to least-specific.
    """

    label: str
    patterns: tuple[str, ...]


# Order matters: the first bucket whose pattern matches an H3 wins.
# "Refactor decisions (design-patterns lens)" must hit the Refactor
# bucket BEFORE the generic Lessons bucket can claim it on "lessons".
_BUCKETS: Final[tuple[Bucket, ...]] = (
    Bucket(
        label="Rule-7 conflicts surfaced + resolution",
        patterns=("conflict surfaced", "adaptation", "deviation", "rule 7"),
    ),
    Bucket(
        label="Refactor decisions / design-pattern applications",
        patterns=("refactor",),
    ),
    Bucket(
        label="Out-of-scope / deferred to a follow-up",
        patterns=("out-of-scope", "out of scope", "follow-up", "follow up"),
    ),
    Bucket(
        label="Carry-forward lessons for future stories",
        patterns=("lesson", "carry forward"),
    ),
)


@dataclass(frozen=True)
class Section:
    """One H3 section extracted from a per-story attempt log."""

    story_id: str
    attempt_log: Path
    h3_title: str
    body: str = field(compare=False)


def _bucket_for_h3(title: str) -> Bucket | None:
    """Return the bucket whose first matching pattern claims this H3."""

    lowered = title.lower()
    for bucket in _BUCKETS:
        if any(p in lowered for p in bucket.patterns):
            return bucket
    return None


def _extract_h3_sections(text: str) -> list[tuple[str, str]]:
    """Return [(h3_title, body_text), ...] from a markdown file's text.

    Body is every line after the H3 until the next H2 or H3 (whichever comes
    first). Trailing whitespace is stripped; leading blank lines are removed.
    """

    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        h3_match = _H3_RE.match(line)
        h2_match = _H2_RE.match(line)
        if h3_match is not None or h2_match is not None:
            if current_title is not None:
                sections.append((current_title, _trim_section_body("\n".join(current_lines))))
            current_title = h3_match.group(1).strip() if h3_match else None
            current_lines = []
        elif current_title is not None:
            current_lines.append(line)
    if current_title is not None:
        sections.append((current_title, _trim_section_body("\n".join(current_lines))))
    return sections


def _trim_section_body(body: str) -> str:
    """Drop leading + trailing blank lines; preserve internal whitespace."""

    return "\n".join(body.split("\n")).strip("\n")


def _story_sort_key(filename: str) -> tuple[int, int]:
    """``S4-02.md`` → ``(4, 2)`` so attempts sort numerically, not lexicographically."""

    m = _STORY_FILENAME_RE.match(filename)
    if m is None:
        return (10_000, 10_000)
    return (int(m.group(1)), int(m.group(2)))


def collect_phase_sections(phase_dir: Path) -> list[Section]:
    """Walk every ``S*.md`` attempt log under the phase, bucket each H3."""

    attempts_dir = phase_dir / "stories" / "_attempts"
    if not attempts_dir.is_dir():
        raise FileNotFoundError(
            f"Expected attempts dir at {attempts_dir} — has phase-story-executor "
            "ever run for this phase?"
        )

    sections: list[Section] = []
    log_paths = sorted(
        (p for p in attempts_dir.glob("S*.md")),
        key=lambda p: _story_sort_key(p.name),
    )
    for log_path in log_paths:
        story_id = log_path.stem  # "S4-02"
        text = log_path.read_text(encoding="utf-8")
        for h3_title, body in _extract_h3_sections(text):
            if not body.strip():
                continue
            sections.append(
                Section(
                    story_id=story_id,
                    # Path relative to the phase_dir — the retrospective
                    # lives there, so relative links resolve cleanly.
                    attempt_log=log_path.relative_to(phase_dir),
                    h3_title=h3_title,
                    body=body,
                )
            )
    return sections


def render_retrospective(
    phase_slug: str, sections: list[Section], lessons_md_rel: Path | None
) -> str:
    """Render the retrospective markdown text. Pure function."""

    out: list[str] = []
    out.append(f"# Phase `{phase_slug}` — retrospective (auto-aggregated)")
    out.append("")
    out.append(
        "**Generated by:** `scripts/synthesize_phase_lessons.py` — pure "
        "data-extraction. Re-run anytime; output is deterministic byte-for-byte."
    )
    out.append("")
    out.append(
        "This roll-up walks every `_attempts/S*.md` log for this phase and "
        "groups H3 sections by keyword bucket. Buckets are mutually exclusive: "
        "the first matching pattern wins (see `_BUCKETS` in the script). "
        "Sections are NOT re-ranked by frequency or re-summarized — the "
        "synthesis pass is intentionally a separate, human-curated step."
    )
    out.append("")

    if lessons_md_rel is not None:
        out.append("## Cross-story lessons index")
        out.append("")
        out.append(
            f"See [`{lessons_md_rel}`]({lessons_md_rel.as_posix()}) for the "
            "append-only `_lessons.md` ledger (one H2 entry per durable "
            "lesson). This retrospective does NOT duplicate that file; the "
            "per-story sections below capture the in-context detail that "
            "feeds the durable-lesson distillation."
        )
        out.append("")

    by_bucket: dict[str, list[Section]] = {b.label: [] for b in _BUCKETS}
    unbucketed: list[Section] = []
    for section in sections:
        bucket = _bucket_for_h3(section.h3_title)
        if bucket is None:
            unbucketed.append(section)
        else:
            by_bucket[bucket.label].append(section)

    for bucket in _BUCKETS:
        bucket_sections = by_bucket[bucket.label]
        out.append(f"## {bucket.label}")
        out.append("")
        out.append(f"**Story count contributing:** {len({s.story_id for s in bucket_sections})}")
        out.append(f"**Sections aggregated:** {len(bucket_sections)}")
        out.append("")
        if not bucket_sections:
            out.append("_No sections matched this bucket in this phase._")
            out.append("")
            continue
        for section in bucket_sections:
            out.append(
                f"### {section.story_id} — {section.h3_title}  "
                f"<sub>[source]({section.attempt_log.as_posix()})</sub>"
            )
            out.append("")
            out.append(section.body)
            out.append("")

    out.append("## Coverage gaps — H3 sections that did NOT match any bucket")
    out.append("")
    out.append(
        f"**Count:** {len(unbucketed)}. Listed for the curator to either "
        "extend `_BUCKETS` (if a recurring shape exists) or accept as "
        "story-specific noise."
    )
    out.append("")
    if unbucketed:
        for section in unbucketed:
            out.append(
                f"- `{section.story_id}` — {section.h3_title}  "
                f"<sub>[source]({section.attempt_log.as_posix()})</sub>"
            )
    out.append("")
    out.append("---")
    out.append("")
    out.append(
        "**Next step (manual curation pass):** read this file end-to-end; "
        "promote any pattern that recurs in ≥ 3 stories to a durable lesson "
        "in `_lessons.md`; flag any pattern that should change the next "
        "phase's story-template / validator. The retrospective itself is a "
        "snapshot — `_lessons.md` is the running ledger."
    )
    out.append("")
    return "\n".join(out)


def synthesize(phase_slug: str) -> Path:
    """End-to-end: parse phase attempts, render, write the retrospective."""

    phase_dir = _PHASES_DIR / phase_slug
    if not phase_dir.is_dir():
        raise FileNotFoundError(
            f"Phase directory not found: {phase_dir}. "
            f"Available phases: "
            f"{sorted(p.name for p in _PHASES_DIR.iterdir() if p.is_dir())}"
        )

    sections = collect_phase_sections(phase_dir)
    lessons_md = phase_dir / "stories" / "_attempts" / "_lessons.md"
    lessons_md_rel: Path | None = (
        lessons_md.relative_to(phase_dir) if lessons_md.is_file() else None
    )
    text = render_retrospective(phase_slug, sections, lessons_md_rel)
    out_path = phase_dir / "RETROSPECTIVE.md"
    out_path.write_text(text, encoding="utf-8")
    return out_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--phase",
        required=True,
        help="Phase folder name under docs/phases/ (e.g. '02-context-gather-layers-b-g').",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    out_path = synthesize(args.phase)
    sys.stderr.write(f"wrote {out_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
