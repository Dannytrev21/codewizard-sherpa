"""Hypothesis property test — ``SkillsLoader.find_applicable`` is monotone.

AC-11 of S2-01: adding evidence never removes a match.

- ``q1.languages ⊆ q2.languages`` → ``matches(q1) ⊆ matches(q2)``.
- ``q1.task is None`` and ``q2.task is not None`` (or equal) → same direction.

Pure monotonicity *is insufficient* by itself — a degenerate ``return []``
is vacuously monotone. AC-11a (in ``tests/unit/skills/test_loader.py``)
pins correctness against a hand-built fixture; this test catches mutation
witnesses across random evidence pairs.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from codegenie.skills import EvidenceQuery, Skill, SkillsLoader
from codegenie.types.identifiers import Language, SkillId, TaskClassId

_TASK_ALPHABET = st.sampled_from(["vuln", "distroless", "*", "alpha", "beta"])
_LANG_ALPHABET = st.sampled_from(["typescript", "javascript", "go", "python", "*", "rust"])


def _mk_skill(sid: str, tasks: list[str], langs: list[str]) -> Skill:
    return Skill(
        id=SkillId(sid),
        applies_to_tasks=[TaskClassId(t) for t in tasks],
        applies_to_languages=[Language(lang) for lang in langs],
        body_offset=0,
        body_size=0,
        body_blake3="blake3:" + ("0" * 64),
    )


def _make_loader(corpus: list[Skill]) -> SkillsLoader:
    loader = SkillsLoader(search_paths=[])
    loader._skills = list(corpus)
    return loader


_CORPUS = [
    _mk_skill("vuln-ts", ["vuln"], ["typescript"]),
    _mk_skill("vuln-any", ["vuln"], ["*"]),
    _mk_skill("any-ts", ["*"], ["typescript"]),
    _mk_skill("distroless-go", ["distroless"], ["go"]),
    _mk_skill("any-any", ["*"], ["*"]),
]


@given(
    languages_subset=st.sets(_LANG_ALPHABET, max_size=4),
    languages_extra=st.sets(_LANG_ALPHABET, max_size=3),
    task_value=st.one_of(st.none(), _TASK_ALPHABET),
)
def test_find_applicable_monotone_on_languages(
    languages_subset: set[str],
    languages_extra: set[str],
    task_value: str | None,
) -> None:
    loader = _make_loader(_CORPUS)
    q_small = EvidenceQuery(
        task=TaskClassId(task_value) if task_value is not None else None,
        languages={Language(lang) for lang in languages_subset},
    )
    q_big = EvidenceQuery(
        task=TaskClassId(task_value) if task_value is not None else None,
        languages={Language(lang) for lang in (languages_subset | languages_extra)},
    )
    small = {s.id for s in loader.find_applicable(q_small)}
    big = {s.id for s in loader.find_applicable(q_big)}
    assert small <= big, f"adding languages removed a match: {small - big}"


@given(
    languages=st.sets(_LANG_ALPHABET, max_size=4),
    task_value=_TASK_ALPHABET,
)
def test_find_applicable_monotone_on_task_none_to_some(
    languages: set[str], task_value: str
) -> None:
    loader = _make_loader(_CORPUS)
    q_none = EvidenceQuery(task=None, languages={Language(lang) for lang in languages})
    q_some = EvidenceQuery(
        task=TaskClassId(task_value),
        languages={Language(lang) for lang in languages},
    )
    matches_none = {s.id for s in loader.find_applicable(q_none)}
    matches_some = {s.id for s in loader.find_applicable(q_some)}
    assert matches_none <= matches_some, (
        f"setting task None→{task_value} removed a match: {matches_none - matches_some}"
    )
