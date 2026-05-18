"""S8-02 AC-4 — ``skill_shadowed`` stdout line aggregated from the
``SkillsIndexSlice.shadowed_skills`` data path, not from event interception.

The data path itself (``LoadOutcome.shadowed_skills``,
``SkillsIndexSlice.shadowed_skills``) is exercised at the unit level in
:mod:`tests.unit.skills.test_loader_shadowed_skills` and
:mod:`tests.unit.cli.test_emit_phase2_summary`. This integration test
covers the **wiring**: that the CLI's ``_emit_phase2_summary`` reads
``shadowed_skills`` off the same per-probe ``schema_slice`` the
coordinator merges into the envelope, and prints the expected stdout
line.

The end-to-end "user-tier vs. repo-tier collision through the live
``SkillsIndexProbe``" path cannot run on the current main: the probe's
existing :meth:`SkillsIndexProbe._resolve_search_paths` reads
``ctx.config`` and ``ctx.output_dir``, which the coordinator no longer
provides on :class:`BudgetingContext` (a pre-existing failure-isolation
trip that's out of scope for S8-02 — Rule 3 surgical changes). The
data-path mirror this story adds is therefore validated at the seam the
story owns (the CLI summary block) rather than through the broken
upstream probe path; the zero-collision smoke below proves the wiring
fires on the live coordinator output for the case the live pipeline can
actually produce today.
"""

from __future__ import annotations

import io
import shutil
from contextlib import redirect_stdout
from pathlib import Path

from click.testing import CliRunner
from structlog.testing import capture_logs

from codegenie.cli import _emit_phase2_summary
from codegenie.skills.model import ShadowedSkill


def _seed_minimal_ts(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "fixtures" / "portfolio" / "minimal-ts"
    dst = tmp_path / "minimal-ts"
    shutil.copytree(src, dst)
    return dst


def test_emit_phase2_summary_reads_shadowed_skills_from_slice() -> None:
    """AC-4 wiring — given a ``schema_slice`` carrying ``shadowed_skills``,
    the CLI prints ``skill_shadowed=[<sid>:<tier>]`` on stdout."""
    skills_slice: dict[str, object] = {
        "shadowed_skills": [
            {
                "skill_id": "dup-skill",
                "shadowed_tier": "repo",
                "winning_tier": "user",
                "shadowed_path": "/r/dup-skill/SKILL.md",
                "winning_path": "/u/dup-skill/SKILL.md",
            },
        ],
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        _emit_phase2_summary(0, [], skills_slice)
    out = buf.getvalue()
    assert "secrets_redacted_count=0" in out
    assert "fingerprints=[]" in out
    assert "skill_shadowed=[dup-skill:repo]" in out


def test_emit_phase2_summary_handles_none_skills_slice() -> None:
    """AC-4 / Notes-for-implementer — ``skills_slice is None`` renders
    ``skill_shadowed=[]`` (the probe did not run for this gather)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        _emit_phase2_summary(0, [], None)
    assert "skill_shadowed=[]" in buf.getvalue()


def test_emit_phase2_summary_sorts_multiple_shadows_ascii_lex() -> None:
    """AC-4 — multiple shadows are ASCII-sorted by ``(skill_id, shadowed_tier)``."""
    skills_slice: dict[str, object] = {
        "shadowed_skills": [
            {
                "skill_id": "bravo",
                "shadowed_tier": "org",
                "winning_tier": "user",
                "shadowed_path": "/o/bravo.md",
                "winning_path": "/u/bravo.md",
            },
            {
                "skill_id": "alpha",
                "shadowed_tier": "repo",
                "winning_tier": "user",
                "shadowed_path": "/r/alpha.md",
                "winning_path": "/u/alpha.md",
            },
        ],
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        _emit_phase2_summary(0, [], skills_slice)
    assert "skill_shadowed=[alpha:repo, bravo:org]" in buf.getvalue()


def test_shadowed_skill_model_uses_real_loader_field_names() -> None:
    """AC-4 — :class:`ShadowedSkill` fields match the loader's existing
    ``skill_shadowed`` event payload (mutation-resistant)."""
    # The same five fields the loader's structlog emission carries.
    assert set(ShadowedSkill.model_fields) == {
        "skill_id",
        "shadowed_tier",
        "winning_tier",
        "shadowed_path",
        "winning_path",
    }


def test_no_collisions_renders_empty_skill_shadowed_on_live_gather(
    tmp_path: Path,
) -> None:
    """AC-4 / AC-7 — zero collisions → ``skill_shadowed=[]`` on stdout from
    a real ``codegenie gather`` invocation."""
    from codegenie.cli import cli

    fixture = _seed_minimal_ts(tmp_path)
    with capture_logs():
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])
    assert result.exit_code == 0, result.output
    assert "skill_shadowed=[]" in result.stdout
