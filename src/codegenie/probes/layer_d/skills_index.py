"""``SkillsIndexProbe`` — Layer D, ``heaviness="light"`` (S6-01).

Projects :meth:`codegenie.skills.loader.SkillsLoader.load_all` output into
a typed :class:`SkillsIndexSlice` carrying the two indices the Planner
queries (``applies_to_tasks``, ``applies_to_languages``), the body
byte-offset/size/BLAKE3 anchors, a tier-counts derived statistic, and a
per-file-error round-trip surface. **Bodies are never opened by this
probe** — the loader (S2-01) records ``body_offset`` / ``body_size`` /
``body_blake3`` in one streaming pass; this probe re-uses those anchors.
A ``tracemalloc`` ceiling on a 100 MB body is the load-bearing structural
proof that no body bytes flow through this module.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #9 — loader contract.
- ``docs/localv2.md`` §5.4 D2 SkillsIndexProbe — slice shape.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0005-secret-findings-no-plaintext-persistence.md``
  — same "anchors not bytes" discipline applied to a different surface.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0003-coordinator-heaviness-sort-annotation.md``
  — ``heaviness`` is a ``@register_probe(heaviness=...)`` kwarg, not an
  ABC field.
- ``CLAUDE.md`` "Progressive disclosure for context" — load-bearing
  commitment the probe makes operational.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.result import Err, Ok
from codegenie.skills.loader import LoadOutcome, SkillsLoader, SkillsLoadError
from codegenie.skills.model import TIERS, Skill, Tier
from codegenie.types.identifiers import Language, SkillId, TaskClassId

__all__ = ["IndexedSkill", "SkillsIndexProbe", "SkillsIndexSlice"]


# ---------------------------------------------------------------------------
# Pydantic models (slice surface).
# ---------------------------------------------------------------------------


class IndexedSkill(BaseModel):
    """One row in the skills index — anchors only, never body bytes.

    Newtypes preserved end-to-end (ADR-0033 §1 primitive-obsession): a
    ``TaskClassId`` cannot be accidentally passed where a ``Language`` is
    expected, and the Planner consumer gets the same ``mypy --strict``
    protection the loader does.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: SkillId
    applies_to_tasks: tuple[TaskClassId, ...]
    applies_to_languages: tuple[Language, ...]
    body_offset: Annotated[int, Field(ge=0)]
    body_size: Annotated[int, Field(ge=0)]
    body_blake3: Annotated[str, Field(pattern=r"^blake3:[0-9a-f]{64}$")]


class SkillsIndexSlice(BaseModel):
    """The slice the probe writes into ``RepoContext.probes.skills_index``.

    ``tier_counts`` is always exactly the three tier keys (never partial):
    a missing tier path counts as 0, not as "absent" — this makes the
    Planner's ``match`` exhaustive without an "else: raise" trapdoor.

    ``per_file_errors`` carries JSON-dumps of the loader's discriminated
    error union (``SymlinkRefused | UnsafeYaml | FrontmatterUnterminated
    | SchemaViolation | IoFailure``) so a future schema change in the
    loader's error variants surfaces as a json-load failure on the
    consumer side, not as silent drift.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    skills: tuple[IndexedSkill, ...]
    tier_counts: dict[Literal["user", "repo", "org"], int]
    per_file_errors: tuple[str, ...]


# ---------------------------------------------------------------------------
# Functional core — pure helpers, independently testable.
# ---------------------------------------------------------------------------


def _project_skill(skill: Skill) -> IndexedSkill:
    """Project a loaded :class:`Skill` into the indexable slice shape."""
    return IndexedSkill(
        id=skill.id,
        applies_to_tasks=tuple(skill.applies_to_tasks),
        applies_to_languages=tuple(skill.applies_to_languages),
        body_offset=skill.body_offset,
        body_size=skill.body_size,
        body_blake3=skill.body_blake3,
    )


def _project_skills_sorted(skills: Sequence[Skill]) -> tuple[IndexedSkill, ...]:
    """Project + lexicographic-stable sort by ``id``.

    Sorted output makes two consecutive gathers byte-identical in their
    JSON serialization (AC-13). Stable on ties (Python ``sorted`` is
    guaranteed-stable; ``Skill.id`` is unique post-loader-dedup so ties
    cannot actually occur on the live path — the sort key is unique).
    """
    return tuple(_project_skill(s) for s in sorted(skills, key=lambda s: s.id))


def _count_skills_per_tier(search_paths: Sequence[Path]) -> dict[Tier, int]:
    """Count ``SKILL.md`` filenames per tier — enumeration only, no body reads.

    Missing tier paths count as 0. The count is pre-de-duplication so a
    shadowed skill is visible to operators (presence-on-disk statistic):
    ``sum(tier_counts.values()) >= len(slice.skills)``.

    The ``rglob`` walks directory entries via opendir/readdir only; it
    does NOT open file contents. AC-11's source-grep interdict over this
    module passes because ``Path.rglob`` is implemented in terms of
    ``scandir`` and does not touch file bodies.
    """
    counts: dict[Tier, int] = {t: 0 for t in TIERS}
    for tier, path in zip(TIERS, search_paths, strict=False):
        if path.exists():
            counts[tier] = sum(1 for _ in path.rglob("SKILL.md"))
    return counts


def _compute_confidence(
    skills: Sequence[Skill], per_file_errors: Sequence[SkillsLoadError]
) -> Literal["high", "medium", "low"]:
    """Three-state confidence (story AC-9).

    - ``high`` iff no per-file errors (clean load — including the empty
      install).
    - ``medium`` iff at least one success AND at least one failure
      (partial success — surfaces the partial-load signal the Planner
      uses to widen its uncertainty bounds).
    - ``low`` iff every discovered file failed (the loader found
      candidates but produced nothing usable). ``FatalLoadError`` also
      maps to ``low`` at the caller (the ``Err`` branch).
    """
    if not per_file_errors:
        return "high"
    if skills:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Imperative shell — the probe class.
# ---------------------------------------------------------------------------


@register_probe(heaviness="light")
class SkillsIndexProbe(Probe):
    """Layer-D skills-index probe. See module docstring for invariants."""

    name: str = "skills_index"
    version: str = "0.1.0"
    layer: Literal["D"] = "D"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 10

    def __init__(self) -> None:
        super().__init__()
        # ``declared_inputs`` carries one token per tier search-path so the
        # cache invalidates when any tier config changes (mirrors the
        # ``dep_graph_strategy_set:<resolved>`` precedent at
        # ``src/codegenie/probes/layer_b/dep_graph.py:420``).
        self.declared_inputs = [
            "skills_user_search_path:~/.codegenie/skills/",
            "skills_repo_search_path:.codegenie/skills/",
            "skills_org_search_path:~/.codegenie/skills-org/",
        ]

    def _resolve_search_paths(self, repo: RepoSnapshot, ctx: ProbeContext) -> list[Path]:
        """Pure resolution — no I/O (filesystem touch happens in load_all)."""
        user = Path(ctx.config.get("skills.user_path", "~/.codegenie/skills/")).expanduser()
        repo_tier = repo.root / Path(ctx.config.get("skills.repo_path", ".codegenie/skills/"))
        org = Path(ctx.config.get("skills.org_path", "~/.codegenie/skills-org/")).expanduser()
        return [user, repo_tier, org]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        search_paths = self._resolve_search_paths(repo, ctx)
        result = SkillsLoader(search_paths=search_paths).load_all()
        if isinstance(result, Err):
            empty_slice = SkillsIndexSlice(
                skills=(),
                tier_counts={t: 0 for t in TIERS},
                per_file_errors=(),
            )
            return ProbeOutput(
                schema_slice=empty_slice.model_dump(mode="json"),
                raw_artifacts=[],
                confidence="low",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                warnings=[],
                errors=[result.error.model_dump_json()],
            )
        assert isinstance(result, Ok)
        outcome: LoadOutcome = result.value
        per_file_errors_json = tuple(err.model_dump_json() for err in outcome.per_file_errors)
        slice_ = SkillsIndexSlice(
            skills=_project_skills_sorted(outcome.skills),
            tier_counts=_count_skills_per_tier(search_paths),
            per_file_errors=per_file_errors_json,
        )
        confidence = _compute_confidence(outcome.skills, outcome.per_file_errors)
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        raw_path = ctx.output_dir / "skills-index.json"
        raw_path.write_text(json.dumps(slice_.model_dump(mode="json"), sort_keys=True, indent=2))
        return ProbeOutput(
            schema_slice=slice_.model_dump(mode="json"),
            raw_artifacts=[raw_path],
            confidence=confidence,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=list(per_file_errors_json),
        )
