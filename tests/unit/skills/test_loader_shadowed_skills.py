"""S8-02 — :class:`LoadOutcome` carries ``shadowed_skills`` as data.

The loader's existing ``skill_shadowed`` structlog event is the
event-stream surface (S2-01); this story adds the **data-path** mirror
so the CLI summary can read shadows from the typed envelope without
intercepting events. These tests pin the additive contract:

- Zero collisions → ``shadowed_skills == ()``.
- One cross-tier collision → exactly one ``ShadowedSkill`` row carrying
  the same field values the structlog event already records.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import structlog

from codegenie.result import Ok
from codegenie.skills.loader import SkillsLoader
from codegenie.skills.model import ShadowedSkill


def _write_skill(parent: Path, sid: str, body: bytes = b"# body\n") -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    skill = parent / "SKILL.md"
    frontmatter = textwrap.dedent(
        f"""\
        ---
        id: {sid}
        applies_to_tasks: ["vulnerability-remediation"]
        applies_to_languages: ["typescript"]
        ---
        """
    ).encode()
    skill.write_bytes(frontmatter + body)
    return skill


def test_no_collisions_returns_empty_shadowed_skills(tmp_path: Path) -> None:
    """Zero collisions across tiers → empty ``shadowed_skills`` tuple."""
    user_dir = tmp_path / "user" / "only-here"
    _write_skill(user_dir, "only-here")
    loader = SkillsLoader(
        search_paths=[
            tmp_path / "user",
            tmp_path / "absent-repo",
            tmp_path / "absent-org",
        ]
    )
    result = loader.load_all()
    assert isinstance(result, Ok)
    outcome = result.unwrap()
    assert outcome.shadowed_skills == ()


def test_cross_tier_collision_yields_one_shadowed_skill_row(tmp_path: Path) -> None:
    """User-tier wins; org-tier's ``dup`` becomes one :class:`ShadowedSkill`."""
    user_md = _write_skill(tmp_path / "user" / "dup", "dup", body=b"# user wins\n")
    org_md = _write_skill(tmp_path / "org" / "dup", "dup", body=b"# org loses\n")

    loader = SkillsLoader(
        search_paths=[
            tmp_path / "user",
            tmp_path / "absent-repo",
            tmp_path / "org",
        ]
    )
    with structlog.testing.capture_logs() as logs:
        result = loader.load_all()
    assert isinstance(result, Ok)
    outcome = result.unwrap()

    # Data path: ``shadowed_skills`` carries exactly one row, mirroring the
    # event that still fires.
    assert len(outcome.shadowed_skills) == 1
    row: ShadowedSkill = outcome.shadowed_skills[0]
    assert row.skill_id == "dup"
    assert row.winning_tier == "user"
    assert row.shadowed_tier == "org"
    assert row.winning_path == str(user_md)
    assert row.shadowed_path == str(org_md)

    # Event-stream surface preserved (S2-01 emit-once contract unchanged).
    shadow_events = [log for log in logs if log.get("event") == "skill_shadowed"]
    assert len(shadow_events) == 1
    ev = shadow_events[0]
    assert ev["skill_id"] == row.skill_id
    assert ev["winning_tier"] == row.winning_tier
    assert ev["shadowed_tier"] == row.shadowed_tier
    assert ev["winning_path"] == row.winning_path
    assert ev["shadowed_path"] == row.shadowed_path
