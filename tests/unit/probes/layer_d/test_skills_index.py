"""Unit + integration tests for SkillsIndexProbe (S6-01).

Each test is keyed to an AC and names the mutation it catches in its
docstring (Rule 9 — tests verify intent).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import tracemalloc
from pathlib import Path
from typing import Any

import pytest

from codegenie.hashing import content_hash_bytes
from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.layer_d import skills_index as si
from codegenie.probes.registry import default_registry
from codegenie.types.identifiers import SkillId


def _make_context(
    tmp_path: Path, *, config_overrides: dict[str, Any] | None = None
) -> ProbeContext:
    """Construct a ``ProbeContext`` with every required field explicit."""
    config: dict[str, Any] = {
        "skills.user_path": str(tmp_path / "user" / "skills"),
        "skills.repo_path": ".codegenie/skills/",
        "skills.org_path": str(tmp_path / "user" / "skills-org"),
    }
    if config_overrides is not None:
        config.update(config_overrides)
    return ProbeContext(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "out",
        workspace=tmp_path / "work",
        logger=logging.getLogger("test"),
        config=config,
    )


def _make_repo(tmp_path: Path) -> RepoSnapshot:
    return RepoSnapshot(root=tmp_path / "repo", git_commit=None, detected_languages={}, config={})


def _write_skill(
    path: Path,
    *,
    applies_to_tasks: list[str],
    applies_to_languages: list[str] | None = None,
    body: str = "body\n",
) -> None:
    """Write a SKILL.md file. Caller pre-creates the parent dir."""
    if applies_to_languages is None:
        applies_to_languages = ["*"]
    path.write_text(
        "---\n"
        f"id: {path.parent.name}\n"
        f"applies_to_tasks: {applies_to_tasks!r}\n"
        f"applies_to_languages: {applies_to_languages!r}\n"
        "---\n" + body
    )


def _run_probe(repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
    """Sync wrapper for ``async def run`` (mirrors test_dep_graph.py:108)."""
    return asyncio.run(si.SkillsIndexProbe().run(repo, ctx))


# --- AC-1, AC-2 — module layout ---------------------------------------------


def test_layer_d_package_marker_exists() -> None:
    """AC-1. Mutation caught: deleting the layer_d package init."""
    from codegenie.probes import layer_d

    assert layer_d.__doc__ is not None
    assert "Layer D" in layer_d.__doc__


def test_skills_index_module_exports_exact_all() -> None:
    """AC-2. Mutation caught: silently adding a non-public symbol to
    ``__all__`` (which would leak it as part of the public surface) or
    removing one (which would break consumers)."""
    assert si.__all__ == ["IndexedSkill", "SkillsIndexProbe", "SkillsIndexSlice"]


# --- AC-3, AC-4, AC-13 ------------------------------------------------------


def test_slice_is_sorted_and_frozen(tmp_path: Path) -> None:
    """AC-3, AC-13. Mutation caught: returning skills in load order
    (would break two-consecutive-gathers determinism) — assertion pins
    lexical sort on ``id``. Also: changing ``tuple`` to ``list`` on
    IndexedSkill — hash-stability of the slice depends on tuple."""
    user_dir = tmp_path / "user" / "skills"
    (user_dir / "zebra").mkdir(parents=True)
    (user_dir / "alpha").mkdir()
    _write_skill(user_dir / "zebra" / "SKILL.md", applies_to_tasks=["distroless_migration"])
    _write_skill(user_dir / "alpha" / "SKILL.md", applies_to_tasks=["vulnerability_remediation"])

    from pydantic import ValidationError

    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    assert [s.id for s in slice_.skills] == ["alpha", "zebra"]
    with pytest.raises(ValidationError):  # frozen Pydantic model
        slice_.skills[0].id = "mutated"  # type: ignore[misc]


def test_two_consecutive_gathers_byte_identical_json(tmp_path: Path) -> None:
    """AC-13 (second clause). Mutation caught: any timestamp leakage,
    dict-iteration-order escape, or non-stable sort."""
    user_dir = tmp_path / "user" / "skills" / "a"
    user_dir.mkdir(parents=True)
    _write_skill(user_dir / "SKILL.md", applies_to_tasks=["t1"])

    out1 = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    out2 = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    assert json.dumps(out1.schema_slice, sort_keys=True) == json.dumps(
        out2.schema_slice, sort_keys=True
    )


# --- AC-5 — probe contract attributes ---------------------------------------


def test_probe_contract_attributes() -> None:
    """AC-5. Mutation caught: silently flipping any class attribute that
    would change coordinator dispatch (e.g., layer "D" → "A" would route
    the probe into the wrong wave)."""
    p = si.SkillsIndexProbe()
    assert p.name == "skills_index"
    assert p.layer == "D"
    assert p.tier == "base"
    assert p.applies_to_tasks == ["*"]
    assert p.applies_to_languages == ["*"]
    assert p.requires == []
    assert p.timeout_seconds == 10


# --- AC-7 — declared_inputs carry tier search-path tokens ------------------


def test_declared_inputs_include_three_tier_tokens() -> None:
    """AC-7. Mutation caught: stripping a tier from ``declared_inputs``
    silently — the cache wouldn't invalidate when the dropped tier's
    config changed."""
    p = si.SkillsIndexProbe()
    tokens = p.declared_inputs
    assert any(tok.startswith("skills_user_search_path:") for tok in tokens)
    assert any(tok.startswith("skills_repo_search_path:") for tok in tokens)
    assert any(tok.startswith("skills_org_search_path:") for tok in tokens)


# --- AC-10, AC-11 — load-bearing progressive-disclosure --------------------


def test_tracemalloc_peak_under_1mb_on_100mb_body(tmp_path: Path) -> None:
    """AC-10. Mutation caught: any future ``path.read_bytes()`` /
    ``open(path).read()`` over the body section. The fixture has a 100 MB
    body; reading it would blow the budget by ~100x.

    Uses a sparse file (os.truncate) so the test wall-clock stays under 1 s
    while the file-size invariant the loader walks is real.
    """
    user_dir = tmp_path / "user" / "skills" / "big"
    user_dir.mkdir(parents=True)
    skill_path = user_dir / "SKILL.md"
    skill_path.write_text(
        "---\nid: big\napplies_to_tasks: ['t1']\napplies_to_languages: ['*']\n---\n"
    )
    # Extend the file to 100 MB via sparse truncate (O(1) on most filesystems).
    with skill_path.open("rb+") as fh:
        fh.seek(100 * 1024 * 1024 - 1)
        fh.write(b"\0")

    tracemalloc.start()
    try:
        output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1024 * 1024, f"peak {peak} bytes exceeds 1 MB ceiling"
    assert output.confidence in ("high", "medium")  # not "low"


def test_probe_module_source_has_no_file_open() -> None:
    """AC-11. Architectural test: source-introspect the WHOLE module
    (not just the class) and confirm no file-opening primitives appear.
    Mutation caught: a "convenience" addition like
    ``body_preview = path.read_text()[:200]`` would fail this test
    immediately, before tracemalloc has to catch it at runtime.
    """
    src = inspect.getsource(si)
    for forbidden in ("os.open", "os.read", ".read_bytes", ".read_text", ".open("):
        assert forbidden not in src, (
            f"SkillsIndex module must not open skill body bytes; found {forbidden!r}. "
            "The loader (S2-01) records body_offset/body_size/body_blake3 once; "
            "the probe re-uses those anchors. Body reads are the Planner's job."
        )


# --- AC-12 — anchors round-trip (BLAKE3 prefix-aware) ----------------------


def test_recorded_anchors_match_actual_body_blake3(tmp_path: Path) -> None:
    """AC-12. Mutation caught: hashing the wrong byte range (e.g.,
    including the closing ``---`` separator), dropping the ``blake3:``
    prefix, or hashing the frontmatter instead of the body."""
    user_dir = tmp_path / "user" / "skills" / "small"
    user_dir.mkdir(parents=True)
    skill_path = user_dir / "SKILL.md"
    _write_skill(skill_path, applies_to_tasks=["t1"], body="body bytes\n")

    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    indexed = slice_.skills[0]
    raw = skill_path.read_bytes()  # test is allowed to read; the probe is not.
    body = raw[indexed.body_offset : indexed.body_offset + indexed.body_size]
    assert content_hash_bytes(body) == indexed.body_blake3
    assert indexed.body_offset + indexed.body_size <= len(raw)
    assert indexed.body_blake3.startswith("blake3:")


# --- AC-14 — tier counts (filesystem-enumeration-derived) ------------------


def test_tier_counts_match_three_tier_layout(tmp_path: Path) -> None:
    """AC-14. Mutation caught: counting *all* skills as "user" tier;
    miscounting empty org tier as 1 instead of 0; missing tier dir
    raising instead of counting 0."""
    user = tmp_path / "user" / "skills"
    repo_root = tmp_path / "repo"
    repo_dir = repo_root / ".codegenie" / "skills"
    # org tier intentionally never created on disk
    user.mkdir(parents=True)
    repo_dir.mkdir(parents=True)
    for name in ("a", "b", "c"):
        (user / name).mkdir()
        _write_skill(user / name / "SKILL.md", applies_to_tasks=["t1"])
    (repo_dir / "x").mkdir()
    _write_skill(repo_dir / "x" / "SKILL.md", applies_to_tasks=["t1"])

    repo = RepoSnapshot(root=repo_root, git_commit=None, detected_languages={}, config={})
    output = _run_probe(repo, _make_context(tmp_path))
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    assert slice_.tier_counts == {"user": 3, "repo": 1, "org": 0}


# --- AC-15 — empty fixture --------------------------------------------------


def test_empty_fixture_yields_high_confidence(tmp_path: Path) -> None:
    """AC-15. Mutation caught: treating zero skills as an error
    (returning ``confidence="low"`` on a clean empty install)."""
    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    assert slice_.skills == ()
    assert slice_.tier_counts == {"user": 0, "repo": 0, "org": 0}
    assert slice_.per_file_errors == ()
    assert output.confidence == "high"


# --- AC-17 — per-file errors round-trip ------------------------------------


def test_symlinked_skill_yields_medium_confidence_no_raise(tmp_path: Path) -> None:
    """AC-17. Mutation caught: re-raising ``SkillsLoadError`` from the
    probe (would break Phase 0 coordinator failure-isolation); swallowing
    ``per_file_errors`` silently; conflating partial-success with
    total-failure."""
    user_dir = tmp_path / "user" / "skills"
    (user_dir / "good").mkdir(parents=True)
    _write_skill(user_dir / "good" / "SKILL.md", applies_to_tasks=["t1"])
    (user_dir / "linked").mkdir()
    real = tmp_path / "real_skill.md"
    real.write_text(
        "---\nid: malicious\napplies_to_tasks: ['*']\napplies_to_languages: ['*']\n---\nx\n"
    )
    (user_dir / "linked" / "SKILL.md").symlink_to(real)

    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    assert output.confidence == "medium"
    assert len(slice_.skills) == 1
    assert len(slice_.per_file_errors) == 1
    assert json.loads(slice_.per_file_errors[0])["reason"] == "symlink_refused"


# --- AC-18 — shadowed-skill de-duplication propagates ----------------------


def test_shadowed_skill_propagates_first_tier_wins(tmp_path: Path) -> None:
    """AC-18. Mutation caught: emitting both copies (de-dup leaked);
    tier_counts collapsing to 1+0 instead of 1+1 (on-disk presence
    intentionally surfaces the shadow to operators)."""
    user = tmp_path / "user" / "skills" / "alpha"
    user.mkdir(parents=True)
    _write_skill(user / "SKILL.md", applies_to_tasks=["user_wins"])

    repo_root = tmp_path / "repo"
    repo_dir = repo_root / ".codegenie" / "skills" / "alpha"
    repo_dir.mkdir(parents=True)
    _write_skill(repo_dir / "SKILL.md", applies_to_tasks=["repo_loses"])

    repo = RepoSnapshot(root=repo_root, git_commit=None, detected_languages={}, config={})
    output = _run_probe(repo, _make_context(tmp_path))
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    assert [s.id for s in slice_.skills] == ["alpha"]
    assert slice_.skills[0].applies_to_tasks == ("user_wins",)
    assert slice_.tier_counts == {"user": 1, "repo": 1, "org": 0}


# --- AC-16 — FatalLoadError -------------------------------------------------


def test_fatal_load_error_yields_low_confidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-16. Mutation caught: re-raising FatalLoadError, emitting empty
    schema_slice (which would fail AC-4's three-key invariant on
    tier_counts)."""
    from codegenie.result import Err
    from codegenie.skills import loader as loader_mod

    def _fake_load_all(self: Any) -> Any:
        return Err(error=loader_mod.FatalLoadError(attempted=[Path("/nonexistent")]))

    monkeypatch.setattr(loader_mod.SkillsLoader, "load_all", _fake_load_all)
    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    assert output.confidence == "low"
    assert slice_.skills == ()
    assert slice_.tier_counts == {"user": 0, "repo": 0, "org": 0}
    assert any("all_tiers_unreadable" in e for e in output.errors)


# --- AC-20 — registry annotation -------------------------------------------


def test_registry_heaviness_is_light() -> None:
    """AC-20. Mutation caught: bumping to ``heaviness="medium"`` would
    cause the coordinator to reserve the wrong scheduling slot;
    forgetting the kwarg form would default to "light" silently."""
    # Ensure the probe module is imported so registration has fired.
    import codegenie.probes  # noqa: F401

    entry = next(e for e in default_registry._entries if e.cls.name == "skills_index")
    assert entry.heaviness == "light"
    assert entry.runs_last is False


# --- AC-22 — field-coverage parametrized smoke -----------------------------


@pytest.mark.parametrize("field_name", list(si.IndexedSkill.model_fields.keys()))
def test_every_indexed_skill_field_populated_from_canonical_fixture(
    tmp_path: Path, field_name: str
) -> None:
    """AC-22. Mutation caught: silently dropping a field in
    ``_project_skill`` (e.g., forgetting ``applies_to_languages``)."""
    user = tmp_path / "user" / "skills" / "canonical"
    user.mkdir(parents=True)
    _write_skill(
        user / "SKILL.md",
        applies_to_tasks=["distroless_migration"],
        applies_to_languages=["python"],
        body="body body body\n",
    )
    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    indexed = slice_.skills[0]
    value = getattr(indexed, field_name)
    if field_name == "body_blake3":
        assert isinstance(value, str) and value.startswith("blake3:") and len(value) == 71
    elif field_name in ("body_offset", "body_size"):
        assert isinstance(value, int) and value > 0
    elif field_name == "id":
        assert isinstance(value, str) and value == "canonical"
    elif field_name in ("applies_to_tasks", "applies_to_languages"):
        assert isinstance(value, tuple) and len(value) >= 1
    else:
        pytest.fail(f"AC-22 not updated for new field {field_name!r}")


# --- AC-23 — Hypothesis projection property --------------------------------


def test_projection_is_cardinality_and_order_preserving() -> None:
    """AC-23. Property: for any list of Skill instances with unique ids,
    ``_project_skills_sorted`` returns a tuple of the same length whose
    ids are the sorted set of input ids. Mutation caught: stable-sort
    bugs on single-element or identical-prefix IDs; accidental
    de-duplication; sort-key drift."""
    from hypothesis import given
    from hypothesis import strategies as st

    from codegenie.skills.model import Skill
    from codegenie.types.identifiers import Language, TaskClassId

    @st.composite
    def _skills(draw: Any) -> list[Skill]:
        ids = draw(
            st.lists(
                st.text(min_size=1, max_size=8, alphabet="abcdefg"),
                min_size=0,
                max_size=12,
                unique=True,
            )
        )
        return [
            Skill(
                id=SkillId(i),
                applies_to_tasks=[TaskClassId("*")],
                applies_to_languages=[Language("*")],
                body_offset=10,
                body_size=10,
                body_blake3="blake3:" + ("0" * 64),
            )
            for i in ids
        ]

    @given(_skills())
    def _prop(skills: list[Skill]) -> None:
        projected = si._project_skills_sorted(skills)
        assert len(projected) == len({s.id for s in skills})
        assert [s.id for s in projected] == sorted({s.id for s in skills})

    _prop()


# --- AC-19 — sub-schema validation (consumer side) -------------------------


def test_slice_matches_subschema(tmp_path: Path) -> None:
    """AC-19. Mutation caught: schema drift — a future change to
    ``IndexedSkill`` (e.g., renaming ``body_offset`` → ``offset``) would
    fail the JSON-Schema round-trip."""
    from importlib.resources import files

    import jsonschema

    schema = json.loads((files("codegenie.schema.probes") / "skills_index.schema.json").read_text())
    user = tmp_path / "user" / "skills" / "a"
    user.mkdir(parents=True)
    _write_skill(user / "SKILL.md", applies_to_tasks=["t1"])
    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    jsonschema.validate(output.schema_slice, schema)


# --- AC-21 — mypy strict (handled by `make typecheck` gate) ---------------
# AC-21 is verified by the `mypy --strict src/codegenie` invocation in the
# repo-wide gate, not by an in-process test. See Stage 3 validator section
# of the attempt log for the recorded gate output.


# --- AC-6 — Result pattern-match on success returns ProbeOutput shape ------


def test_run_returns_probeoutput_with_all_six_fields(tmp_path: Path) -> None:
    """AC-6. Mutation caught: constructing ProbeOutput with the wrong
    field set (e.g., a stale ``probe_id`` field from an older draft)
    would TypeError at construction; missing ``duration_ms`` would also
    TypeError. This test pins the public dataclass shape."""
    user_dir = tmp_path / "user" / "skills" / "a"
    user_dir.mkdir(parents=True)
    _write_skill(user_dir / "SKILL.md", applies_to_tasks=["t1"])

    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    assert isinstance(output, ProbeOutput)
    assert isinstance(output.schema_slice, dict)
    assert isinstance(output.raw_artifacts, list)
    assert output.confidence in ("high", "medium", "low")
    assert isinstance(output.duration_ms, int)
    assert isinstance(output.warnings, list)
    assert isinstance(output.errors, list)
    # On success: writer wrote skills-index.json into ctx.output_dir
    assert any(p.name == "skills-index.json" for p in output.raw_artifacts)


# --- Pure helper unit tests (functional core) ------------------------------


def test_compute_confidence_high_on_clean_load() -> None:
    """AC-9 (clause 1). Mutation caught: returning "low" on empty install."""
    assert si._compute_confidence([], []) == "high"


def test_compute_confidence_medium_on_partial_success(tmp_path: Path) -> None:
    """AC-9 (clause 2). Pure helper: at least one error + at least one
    success → ``medium``."""
    from codegenie.skills.loader import SymlinkRefused
    from codegenie.skills.model import Skill

    skill = Skill(
        id=SkillId("a"),
        applies_to_tasks=[],
        applies_to_languages=[],
        body_offset=0,
        body_size=0,
        body_blake3="blake3:" + ("0" * 64),
    )
    err = SymlinkRefused(path=tmp_path / "x")
    assert si._compute_confidence([skill], [err]) == "medium"


def test_compute_confidence_low_when_all_failed(tmp_path: Path) -> None:
    """AC-9 (clause 3). Pure helper: no successes + at least one error
    → ``low``."""
    from codegenie.skills.loader import SymlinkRefused

    err = SymlinkRefused(path=tmp_path / "x")
    assert si._compute_confidence([], [err]) == "low"
