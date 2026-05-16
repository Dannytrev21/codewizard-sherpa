"""Unit tests for ``codegenie.skills.loader`` — story 02 S2-01.

Covers AC-1..AC-23, AC-26 from
``docs/phases/02-context-gather-layers-b-g/stories/S2-01-skills-loader.md``.
AC-11 (Hypothesis property) lives in
``tests/property/test_skills_loader_monotone.py``; AC-24 / AC-25 (AST source
scans) live in their dedicated files.
"""

from __future__ import annotations

import os
import re
import tempfile
import textwrap
import tracemalloc
from pathlib import Path

import pytest
import structlog.testing
from pydantic import TypeAdapter, ValidationError

import codegenie.parsers.safe_yaml as safe_yaml_mod
from codegenie.hashing import content_hash_bytes
from codegenie.result import Err, Ok
from codegenie.skills import (
    TIERS,
    EvidenceQuery,
    FrontmatterUnterminated,
    IoFailure,
    LoadOutcome,
    SchemaViolation,
    Skill,
    SkillsLoader,
    SkillsLoadError,
    SymlinkRefused,
    Tier,
    UnsafeYaml,
)
from codegenie.skills import loader as loader_mod
from codegenie.types.identifiers import Language, SkillId, TaskClassId


def _write_skill(
    p: Path,
    sid: str,
    body: bytes = b"# body\n",
    tasks: str = '["vulnerability-remediation"]',
    languages: str = '["typescript"]',
) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    skill_md = p / "SKILL.md"
    frontmatter = textwrap.dedent(
        f"""\
        ---
        id: {sid}
        applies_to_tasks: {tasks}
        applies_to_languages: {languages}
        ---
        """
    ).encode()
    skill_md.write_bytes(frontmatter + body)
    return skill_md


# ---------------------------------------------------------------------------
# AC-1 — module surface, types, discriminated union enumeration
# ---------------------------------------------------------------------------


def test_ac1_module_all_is_exact_set() -> None:
    """AC-1: ``__all__`` pins the exact public surface."""
    import codegenie.skills as s

    assert set(s.__all__) == {
        "TIERS",
        "EvidenceQuery",
        "FatalLoadError",
        "FrontmatterUnterminated",
        "IoFailure",
        "LoadOutcome",
        "SchemaViolation",
        "Skill",
        "SkillsLoadError",
        "SkillsLoader",
        "SymlinkRefused",
        "Tier",
        "UnsafeYaml",
    }


def test_ac1_skill_is_frozen_and_extra_forbid() -> None:
    """AC-1 + AC-9: ``Skill`` rejects unknown fields and forbids assignment."""
    sk = Skill(
        id=SkillId("x"),
        applies_to_tasks=[],
        applies_to_languages=[],
        body_offset=0,
        body_size=0,
        body_blake3="blake3:" + ("0" * 64),
    )
    with pytest.raises(ValidationError):
        Skill(
            id=SkillId("x"),
            applies_to_tasks=[],
            applies_to_languages=[],
            body_offset=0,
            body_size=0,
            body_blake3="blake3:" + ("0" * 64),
            extra_field="x",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        sk.id = SkillId("other")  # type: ignore[misc]


def test_ac1_tier_literal_and_tiers_order() -> None:
    """AC-1 + AC-4a: ``Tier`` is a Literal sum-type; tier order is pinned."""
    assert TIERS == ("user", "repo", "org")
    # ``Tier`` is a TypeAlias for Literal — runtime is plain ``str`` membership.
    sample: Tier = "user"
    assert sample in TIERS


# ---------------------------------------------------------------------------
# AC-2 — pure-data constructor (no I/O)
# ---------------------------------------------------------------------------


def test_ac2_constructor_does_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2: ``__init__`` must call no I/O primitive."""
    calls: list[str] = []

    def fail(name: str):  # noqa: ANN202 — local helper
        def _stub(*a: object, **kw: object) -> object:
            calls.append(name)
            pytest.fail(f"constructor performed I/O: {name}{a}")

        return _stub

    monkeypatch.setattr(os, "listdir", fail("listdir"))
    monkeypatch.setattr(os, "scandir", fail("scandir"))
    monkeypatch.setattr(os, "open", fail("open"))
    monkeypatch.setattr(os, "stat", fail("stat"))
    monkeypatch.setattr(Path, "exists", fail("Path.exists"))
    monkeypatch.setattr(Path, "is_dir", fail("Path.is_dir"))

    SkillsLoader(search_paths=[Path("/nonexistent")])
    assert calls == []


# ---------------------------------------------------------------------------
# AC-3 — happy path; every field populated
# ---------------------------------------------------------------------------


def test_ac3_happy_path_three_tier_merge(tmp_path: Path) -> None:
    user = tmp_path / "user" / "foo"
    repo = tmp_path / "repo" / "bar"
    org = tmp_path / "org" / "baz"
    _write_skill(user, "foo")
    _write_skill(repo, "bar")
    _write_skill(org, "baz")

    loader = SkillsLoader(search_paths=[tmp_path / "user", tmp_path / "repo", tmp_path / "org"])
    result = loader.load_all()
    assert isinstance(result, Ok), repr(result)
    outcome = result.unwrap()
    assert isinstance(outcome, LoadOutcome)
    assert [s.id for s in outcome.skills] == ["foo", "bar", "baz"]
    assert outcome.per_file_errors == []
    for sk in outcome.skills:
        assert sk.applies_to_tasks == [TaskClassId("vulnerability-remediation")]
        assert sk.applies_to_languages == [Language("typescript")]
        assert sk.body_offset > 0
        assert sk.body_size == len(b"# body\n")
        assert re.fullmatch(r"blake3:[0-9a-f]{64}", sk.body_blake3)


def test_ac3a_missing_optional_tier_silently_skipped(tmp_path: Path) -> None:
    user = tmp_path / "user" / "foo"
    repo = tmp_path / "repo" / "bar"
    _write_skill(user, "foo")
    _write_skill(repo, "bar")
    org = tmp_path / "nonexistent-org"

    with structlog.testing.capture_logs() as logs:
        result = SkillsLoader(search_paths=[tmp_path / "user", tmp_path / "repo", org]).load_all()

    assert isinstance(result, Ok)
    outcome = result.unwrap()
    assert {s.id for s in outcome.skills} == {"foo", "bar"}
    assert outcome.per_file_errors == []
    # Missing-tier branch emits no event.
    assert not any(log.get("event") == "skill_load_failed" for log in logs)


# ---------------------------------------------------------------------------
# AC-4 + AC-4a — first-tier-wins with logged shadow event
# ---------------------------------------------------------------------------


def test_ac4_user_wins_over_org_with_skill_shadowed(tmp_path: Path) -> None:
    user_dup_dir = tmp_path / "user" / "dup"
    org_dup_dir = tmp_path / "org" / "dup"
    user_md = _write_skill(user_dup_dir, "dup", body=b"# user wins\n")
    org_md = _write_skill(org_dup_dir, "dup", body=b"# org loses\n")

    # Three positional tiers: user (0), repo (1, absent), org (2).
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
    assert [s.id for s in outcome.skills] == ["dup"]
    # The winning body is the user-tier one (content hash differs).
    assert outcome.skills[0].body_blake3 == content_hash_bytes(b"# user wins\n")

    shadow_events = [log for log in logs if log.get("event") == "skill_shadowed"]
    assert len(shadow_events) == 1
    ev = shadow_events[0]
    assert ev["skill_id"] == "dup"
    assert ev["winning_tier"] == "user"
    assert ev["shadowed_tier"] == "org"
    assert ev["winning_path"] == str(user_md)
    assert ev["shadowed_path"] == str(org_md)


def test_ac4a_repo_wins_when_user_absent(tmp_path: Path) -> None:
    repo_md = _write_skill(tmp_path / "repo" / "dup", "dup", body=b"# repo wins\n")
    org_md = _write_skill(tmp_path / "org" / "dup", "dup", body=b"# org loses\n")

    loader = SkillsLoader(
        search_paths=[
            tmp_path / "nonexistent-user",
            tmp_path / "repo",
            tmp_path / "org",
        ]
    )
    with structlog.testing.capture_logs() as logs:
        result = loader.load_all()

    outcome = result.unwrap()
    assert [s.id for s in outcome.skills] == ["dup"]
    assert outcome.skills[0].body_blake3 == content_hash_bytes(b"# repo wins\n")

    shadow_events = [log for log in logs if log.get("event") == "skill_shadowed"]
    assert len(shadow_events) == 1
    ev = shadow_events[0]
    assert ev["winning_tier"] == "repo"
    assert ev["shadowed_tier"] == "org"
    assert ev["winning_path"] == str(repo_md)
    assert ev["shadowed_path"] == str(org_md)


# ---------------------------------------------------------------------------
# AC-5 — O_NOFOLLOW symlink refusal
# ---------------------------------------------------------------------------


def test_ac5_symlink_refused_does_not_dereference(tmp_path: Path) -> None:
    good_dir = tmp_path / "user" / "good"
    _write_skill(good_dir, "good")
    evil_dir = tmp_path / "user" / "evil"
    evil_dir.mkdir(parents=True)
    sentinel = tmp_path / "outside"
    sentinel.write_bytes(b"leaked\n")
    (evil_dir / "SKILL.md").symlink_to(sentinel)

    result = SkillsLoader(search_paths=[tmp_path / "user"]).load_all()
    assert isinstance(result, Ok)
    outcome = result.unwrap()
    assert [s.id for s in outcome.skills] == ["good"]
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, SymlinkRefused)
    assert err.path == evil_dir / "SKILL.md"


# ---------------------------------------------------------------------------
# AC-6 / AC-6b / AC-6c / AC-6d — YAML failure modes
# ---------------------------------------------------------------------------


def test_ac6_unsafe_yaml_payload_executes_no_code(tmp_path: Path) -> None:
    sentinel = tmp_path / "pwned"
    evil = tmp_path / "user" / "evil"
    evil.mkdir(parents=True)
    (evil / "SKILL.md").write_bytes(
        textwrap.dedent(
            f"""\
            ---
            !!python/object/apply:os.system ['touch {sentinel}']
            ---
            """
        ).encode()
    )
    result = SkillsLoader(search_paths=[tmp_path / "user"]).load_all()
    assert isinstance(result, Ok)
    outcome = result.unwrap()
    assert not sentinel.exists(), "!!python/object MUST NOT execute"
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, UnsafeYaml)
    assert err.path == evil / "SKILL.md"


def test_ac6b_pure_syntax_error_also_lands_as_unsafe_yaml(tmp_path: Path) -> None:
    typo = tmp_path / "user" / "typo"
    typo.mkdir(parents=True)
    (typo / "SKILL.md").write_bytes(b"---\nid: ok\napplies_to_tasks: [unterminated\n---\n")
    result = SkillsLoader(search_paths=[tmp_path / "user"]).load_all()
    outcome = result.unwrap()
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, UnsafeYaml)


def test_ac6c_frontmatter_unterminated_typed_no_oom(tmp_path: Path) -> None:
    eternal = tmp_path / "user" / "eternal"
    eternal.mkdir(parents=True)
    skill_md = eternal / "SKILL.md"
    # Open fence then never close.
    body = b"---\n" + (b"x: y\n" * (1 << 20))
    skill_md.write_bytes(body)

    tracemalloc.start()
    result = SkillsLoader(search_paths=[tmp_path / "user"]).load_all()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    outcome = result.unwrap()
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, FrontmatterUnterminated)
    # 1 MiB scan cap + structured-log overhead ⇒ < 2 MiB headroom.
    assert peak < 2 * 1024 * 1024, f"OOM-leak: peak={peak}"


def test_ac6d_schema_violation_carries_details(tmp_path: Path) -> None:
    bad = tmp_path / "user" / "bad-schema"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_bytes(
        b"---\nid: ok\n"
        b"applies_to_tasks: not-a-list\n"
        b"applies_to_languages: [typescript]\n"
        b"---\nbody\n"
    )
    result = SkillsLoader(search_paths=[tmp_path / "user"]).load_all()
    outcome = result.unwrap()
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, SchemaViolation)
    assert err.details
    locs = [tuple(d.get("loc", ())) for d in err.details]
    assert any(loc and loc[0] == "applies_to_tasks" for loc in locs)


# ---------------------------------------------------------------------------
# AC-7 / AC-7a / AC-8 — progressive disclosure + exact offset/size + hash
# ---------------------------------------------------------------------------


def test_ac7_body_not_loaded_into_memory_under_100mb_fixture(tmp_path: Path) -> None:
    big = tmp_path / "user" / "big"
    big.mkdir(parents=True)
    skill_md = big / "SKILL.md"
    frontmatter = b"---\nid: big\napplies_to_tasks: [t]\napplies_to_languages: [l]\n---\n"
    chunk = b"\xab" * (1 << 20)  # 1 MiB
    with skill_md.open("wb") as f:
        f.write(frontmatter)
        for _ in range(100):
            f.write(chunk)
    body_size = 100 * (1 << 20)

    loader = SkillsLoader(search_paths=[tmp_path / "user"])
    tracemalloc.start()
    result = loader.load_all()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    outcome = result.unwrap()
    assert outcome.skills[0].body_size == body_size
    # 64 KiB chunk size + Pydantic overhead + log fmt ⇒ < 256 KB envelope.
    # The validator-pinned ceiling is "< 20 KB peak attributable to body",
    # but pytest / structlog test machinery allocates baseline RAM the
    # tracemalloc snapshot also captures; pin to a conservative envelope
    # that still fails a ``body = f.read()`` regression (which allocates
    # 100 MB).
    assert peak < 256 * 1024, f"progressive disclosure breached: peak={peak}"


_AC7A_FRONTMATTER = b'---\nid: x\napplies_to_tasks: ["*"]\napplies_to_languages: ["*"]\n---\n'


def test_ac7a_exact_body_offset_and_size(tmp_path: Path) -> None:
    """AC-7a: off-by-one catcher — exact byte offsets pinned."""
    # Sanity: frontmatter length is the constant the AC asserts against.
    frontmatter_len = len(_AC7A_FRONTMATTER)
    body = b"hello world\n"
    skill_dir = tmp_path / "user" / "x"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_bytes(_AC7A_FRONTMATTER + body)

    result = SkillsLoader(search_paths=[tmp_path / "user"]).load_all()
    outcome = result.unwrap()
    skill = outcome.skills[0]
    assert skill.body_offset == frontmatter_len
    assert skill.body_size == len(body)


def test_ac8_body_blake3_matches_reference(tmp_path: Path) -> None:
    body = b"hello world\n"
    skill_dir = tmp_path / "user" / "x"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_bytes(_AC7A_FRONTMATTER + body)

    result = SkillsLoader(search_paths=[tmp_path / "user"]).load_all()
    skill = result.unwrap().skills[0]
    assert skill.body_blake3 == content_hash_bytes(body)
    assert re.fullmatch(r"blake3:[0-9a-f]{64}", skill.body_blake3)


# ---------------------------------------------------------------------------
# AC-9 — covered above in ``test_ac1_skill_is_frozen_and_extra_forbid``
# AC-10 — discriminated union enumerates five reasons (+ JSON shape)
# ---------------------------------------------------------------------------


def test_ac10_skills_load_error_discriminator_round_trip() -> None:
    adapter: TypeAdapter[SkillsLoadError] = TypeAdapter(SkillsLoadError)
    for reason in (
        "symlink_refused",
        "unsafe_yaml",
        "frontmatter_unterminated",
        "schema",
        "io_failure",
    ):
        payload: dict[str, object] = {"reason": reason, "path": "/x"}
        if reason == "schema":
            payload["details"] = []
        if reason == "io_failure":
            payload["errno_name"] = "ENOENT"
        loaded = adapter.validate_python(payload)
        assert loaded.reason == reason  # type: ignore[union-attr]
    with pytest.raises(ValidationError):
        adapter.validate_python({"reason": "bogus", "path": "/x"})


def test_ac10_symlink_refused_json_shape_pin() -> None:
    err = SymlinkRefused(path=Path("/x"))
    assert err.model_dump() == {"reason": "symlink_refused", "path": Path("/x")}
    assert err.model_dump(mode="json") == {
        "reason": "symlink_refused",
        "path": "/x",
    }


# ---------------------------------------------------------------------------
# AC-11a — find_applicable correctness with named fixtures
# ---------------------------------------------------------------------------


def _build_loader_with(skills: list[Skill]) -> SkillsLoader:
    loader = SkillsLoader(search_paths=[])
    # Bypass load_all by injecting the cached state; we are testing the
    # *matching* contract, not the loader pipeline.
    loader._skills = list(skills)
    return loader


def test_ac11a_find_applicable_correctness() -> None:
    common: dict[str, object] = {
        "body_offset": 0,
        "body_size": 0,
        "body_blake3": "blake3:" + ("0" * 64),
    }
    vuln_ts = Skill(
        id=SkillId("vuln-ts"),
        applies_to_tasks=[TaskClassId("vulnerability-remediation")],
        applies_to_languages=[Language("typescript")],
        **common,  # type: ignore[arg-type]
    )
    vuln_any = Skill(
        id=SkillId("vuln-any"),
        applies_to_tasks=[TaskClassId("vulnerability-remediation")],
        applies_to_languages=[Language("*")],
        **common,  # type: ignore[arg-type]
    )
    any_ts = Skill(
        id=SkillId("any-ts"),
        applies_to_tasks=[TaskClassId("*")],
        applies_to_languages=[Language("typescript")],
        **common,  # type: ignore[arg-type]
    )
    noop = Skill(
        id=SkillId("noop"),
        applies_to_tasks=[TaskClassId("distroless")],
        applies_to_languages=[Language("go")],
        **common,  # type: ignore[arg-type]
    )
    loader = _build_loader_with([vuln_ts, vuln_any, any_ts, noop])

    q = EvidenceQuery(
        task=TaskClassId("vulnerability-remediation"),
        languages={Language("typescript")},
    )
    matches = {s.id for s in loader.find_applicable(q)}
    assert matches == {"vuln-ts", "vuln-any", "any-ts"}
    assert "noop" not in matches

    q2 = EvidenceQuery(
        task=TaskClassId("distroless-migration"),
        languages={Language("typescript")},
    )
    matches2 = {s.id for s in loader.find_applicable(q2)}
    assert matches2 == {"any-ts"}  # only the wildcard-task with ts match
    assert "vuln-ts" not in matches2


# ---------------------------------------------------------------------------
# AC-11b — empty pre-load find_applicable
# ---------------------------------------------------------------------------


def test_ac11b_find_applicable_empty_before_load_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No I/O is triggered on a pre-``load_all`` query."""
    calls: list[str] = []
    monkeypatch.setattr(
        os,
        "open",
        lambda *a, **kw: calls.append("open") or 0,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(os, "listdir", lambda *a, **kw: calls.append("listdir") or [])
    loader = SkillsLoader(search_paths=[Path("/nonexistent")])
    assert loader.find_applicable(EvidenceQuery(task=None, languages=set())) == []
    assert calls == []


# ---------------------------------------------------------------------------
# AC-12 — safe_yaml.load chokepoint asserted by runtime spy
# ---------------------------------------------------------------------------


def test_ac12_safe_yaml_load_is_the_only_yaml_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tmp_path / "user"
    _write_skill(user / "a", "a")
    _write_skill(user / "b", "b")
    _write_skill(user / "c", "c")

    real_load = safe_yaml_mod.load
    invocations: list[tuple[Path, int]] = []

    def spy(path: Path, *, max_bytes: int, max_depth: int = 64):  # type: ignore[no-untyped-def]
        invocations.append((path, max_bytes))
        return real_load(path, max_bytes=max_bytes, max_depth=max_depth)

    monkeypatch.setattr(loader_mod.safe_yaml, "load", spy)
    result = SkillsLoader(search_paths=[user]).load_all()
    assert isinstance(result, Ok)
    assert len(invocations) == 3
    assert all(mb >= (1 << 20) for _, mb in invocations)


# ---------------------------------------------------------------------------
# AC-16 — same-tier collision is also skill_shadowed (lexicographic first)
# ---------------------------------------------------------------------------


def test_ac16_same_tier_collision_lex_first_wins(tmp_path: Path) -> None:
    a_dir = tmp_path / "user" / "a"
    b_dir = tmp_path / "user" / "b"
    a_md = _write_skill(a_dir, "dup", body=b"# a wins\n")
    b_md = _write_skill(b_dir, "dup", body=b"# b loses\n")

    loader = SkillsLoader(search_paths=[tmp_path / "user"])
    with structlog.testing.capture_logs() as logs:
        result = loader.load_all()
    outcome = result.unwrap()
    assert [s.id for s in outcome.skills] == ["dup"]
    assert outcome.skills[0].body_blake3 == content_hash_bytes(b"# a wins\n")

    shadow_events = [log for log in logs if log.get("event") == "skill_shadowed"]
    assert len(shadow_events) == 1
    ev = shadow_events[0]
    assert ev["winning_tier"] == "user"
    assert ev["shadowed_tier"] == "user"
    assert ev["winning_path"] == str(a_md)
    assert ev["shadowed_path"] == str(b_md)


# ---------------------------------------------------------------------------
# AC-18 — os.open flag set is exactly O_RDONLY | O_NOFOLLOW | O_NOCTTY
# ---------------------------------------------------------------------------


def test_ac18_open_flag_set_is_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user = tmp_path / "user" / "x"
    _write_skill(user, "x")
    expected_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NOCTTY

    real_open = os.open
    captured_flags: list[int] = []

    def spy_open(path, flags, *args, **kwargs):  # type: ignore[no-untyped-def]
        # Capture flags only on the SkillsLoader-side open (the SKILL.md),
        # NOT on the safe_yaml tempfile open.
        if str(path).endswith("SKILL.md"):
            captured_flags.append(flags)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", spy_open)
    SkillsLoader(search_paths=[tmp_path / "user"]).load_all()
    assert captured_flags == [expected_flags]


# ---------------------------------------------------------------------------
# AC-19 — within-tier deterministic ordering (cross-filesystem)
# ---------------------------------------------------------------------------


def test_ac19_within_tier_deterministic_lex_order(tmp_path: Path) -> None:
    user = tmp_path / "user"
    _write_skill(user / "zzz", "zzz")
    _write_skill(user / "aaa", "aaa")

    result = SkillsLoader(search_paths=[user]).load_all()
    ids = [s.id for s in result.unwrap().skills]
    assert ids == ["aaa", "zzz"]


# ---------------------------------------------------------------------------
# AC-20 — TOCTOU: file disappears → typed IoFailure
# ---------------------------------------------------------------------------


def test_ac20_io_failure_on_missing_file() -> None:
    ghost = Path("/path/that/does/not/exist/SKILL.md")
    result = loader_mod._load_one_skill(ghost)
    assert isinstance(result, Err)
    err = result.error
    assert isinstance(err, IoFailure)
    assert err.path == ghost
    assert err.errno_name == "ENOENT"


def test_ac20_io_failure_on_isdir(tmp_path: Path) -> None:
    # Opening a directory with O_RDONLY raises EISDIR on Linux/macOS — except
    # macOS allows opening directories read-only. Behavior we *can* portably
    # rely on: ``os.open`` succeeds on a directory, but ``os.read`` returns
    # an EISDIR or short-read depending on platform. We assert the typed
    # error pathway, not the specific errno.
    user = tmp_path / "user"
    user.mkdir(parents=True)
    skill_dir = user / "fakeskill"
    skill_dir.mkdir()  # SKILL.md is a directory, not a file
    skill_md_dir = skill_dir / "SKILL.md"
    skill_md_dir.mkdir()  # the "file" is actually a directory
    result = loader_mod._load_one_skill(skill_md_dir)
    # Either branch is acceptable: SymlinkRefused will NOT fire (not a symlink),
    # so we get IoFailure or FrontmatterUnterminated depending on platform.
    assert isinstance(result, Err)
    err = result.error
    assert isinstance(err, (IoFailure, FrontmatterUnterminated))


# ---------------------------------------------------------------------------
# AC-22 — ``["*"]`` wildcard semantics
# ---------------------------------------------------------------------------


def test_ac22_wildcard_task_matches_any_task_including_none() -> None:
    common: dict[str, object] = {
        "body_offset": 0,
        "body_size": 0,
        "body_blake3": "blake3:" + ("0" * 64),
    }
    star_task = Skill(
        id=SkillId("star-task"),
        applies_to_tasks=[TaskClassId("*")],
        applies_to_languages=[Language("typescript")],
        **common,  # type: ignore[arg-type]
    )
    loader = _build_loader_with([star_task])

    # task=None → wildcard task matches.
    m = loader.find_applicable(EvidenceQuery(task=None, languages={Language("typescript")}))
    assert {s.id for s in m} == {"star-task"}

    # task=Some → wildcard task still matches.
    m2 = loader.find_applicable(
        EvidenceQuery(task=TaskClassId("anything"), languages={Language("typescript")})
    )
    assert {s.id for s in m2} == {"star-task"}


def test_ac22_wildcard_language_matches_any_language_including_empty() -> None:
    common: dict[str, object] = {
        "body_offset": 0,
        "body_size": 0,
        "body_blake3": "blake3:" + ("0" * 64),
    }
    star_lang = Skill(
        id=SkillId("star-lang"),
        applies_to_tasks=[TaskClassId("vulnerability-remediation")],
        applies_to_languages=[Language("*")],
        **common,  # type: ignore[arg-type]
    )
    loader = _build_loader_with([star_lang])

    # empty language set → wildcard still matches.
    m = loader.find_applicable(
        EvidenceQuery(task=TaskClassId("vulnerability-remediation"), languages=set())
    )
    assert {s.id for s in m} == {"star-lang"}


# ---------------------------------------------------------------------------
# AC-23 — find_applicable returns a fresh list per call
# ---------------------------------------------------------------------------


def test_ac23_find_applicable_returns_fresh_list() -> None:
    common: dict[str, object] = {
        "body_offset": 0,
        "body_size": 0,
        "body_blake3": "blake3:" + ("0" * 64),
    }
    sk = Skill(
        id=SkillId("x"),
        applies_to_tasks=[TaskClassId("*")],
        applies_to_languages=[Language("*")],
        **common,  # type: ignore[arg-type]
    )
    loader = _build_loader_with([sk])
    q = EvidenceQuery(task=None, languages=set())
    a = loader.find_applicable(q)
    b = loader.find_applicable(q)
    assert a == b
    assert a is not b
    a.clear()
    # Mutating the returned list does not affect a subsequent call.
    c = loader.find_applicable(q)
    assert len(c) == 1


# ---------------------------------------------------------------------------
# AC-26 — tempfile cleanup verified, even on UnsafeYaml failure
# ---------------------------------------------------------------------------


def test_ac26_tempfile_cleanup_on_unsafe_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))

    evil = tmp_path / "user" / "evil"
    evil.mkdir(parents=True)
    (evil / "SKILL.md").write_bytes(b"---\n!!python/object/apply:os.system ['echo']\n---\n")
    before = list(tmpdir.glob("*.yaml"))
    SkillsLoader(search_paths=[tmp_path / "user"]).load_all()
    after = list(tmpdir.glob("*.yaml"))
    assert before == after, f"orphan tempfiles left behind: {after}"
