# Story S6-01 — `SkillsIndexProbe` Layer D

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Ready
**Effort:** S
**Depends on:** S2-01 (`SkillsLoader` three-tier merge with `O_NOFOLLOW` + `body_offset`/`body_size`/`body_blake3` recorded on `Skill`)
**ADRs honored:** 02-ADR-0005 (no plaintext persistence — body bytes are never read into memory; only the offset/size/BLAKE3 anchors persist), Phase 1 ADR-0006 (`safe_yaml` chokepoint — frontmatter loads exclusively via `safe_yaml.load`)
**Phase-2 commitment honored:** "Progressive disclosure for context" (CLAUDE.md, [`final-design.md` §"Open Q 3"](../final-design.md)) — the probe records *anchors to* skill bodies, not the bodies themselves. The Planner reads bodies directly via the recorded `body_offset` at decision time.

## Context

The Planner needs to know **which Skills apply to which task classes and languages** when it dispatches a remediation. It does **not** need the skill bodies inlined into `repo-context.yaml` — that would explode the artifact (a typical skill body is ~3 KB; a typical install has 100+ skills; bodies are markdown the Planner will read fresh anyway). The body byte-offset + size + BLAKE3 are the recorded **anchors**; the gather pipeline never opens the body bytes.

`SkillsLoader` (S2-01) already does the three-tier merge (`~/.codegenie/skills/`, `.codegenie/skills/`, `~/.codegenie/skills-org/`) and returns `list[Skill]` where each `Skill` carries `body_offset: int`, `body_size: int`, and `body_blake3: str` from the loader's single pass over the file. The probe's job is **purely indexing**: project each `Skill` into a typed slice with the two query keys the Planner uses — `applies_to_tasks` and `applies_to_languages` — plus the offset/size/blake3 anchors.

The load-bearing observable: a 100 MB-body skill fixture (one `SKILL.md` with a 100 MB body section) gathers without the body ever entering process memory. `tracemalloc` peak attributable to `_run` must stay under 20 KB — the only allocations are the small Pydantic models for `applies_to_*` lists and the anchor ints/strings.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Component design" #9 `SkillsLoader`](../phase-arch-design.md) — the loader returns `Skill` with `body_offset`/`body_size`/`body_blake3`; constructor pure, first I/O is `load_all()`.
  - [`../phase-arch-design.md` §"Edge cases"](../phase-arch-design.md) — `O_NOFOLLOW` ELOOP path → `SkillsLoadError(reason="symlink_refused")`; the probe propagates this as `confidence="low"` (it does not retry).
  - [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) row "Schema before consumer" — the slice has at least one Phase 2 consumer (`tests/integration/probes/test_skills_index_probe.py`).
- **Phase ADRs:**
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — bodies are never loaded; the probe's commitment to anchors-only is the same chokepoint discipline applied to a different surface.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) first bullet — slice shape and the body-offset-recorded / bodies-not-loaded commitment.
  - [`../../localv2.md` §5.4 D2 SkillsIndexProbe](../../../localv2.md) — slice shape; "Adding a new variant is dropping a new SKILL.md. No probe changes."
- **Existing kernel:**
  - `src/codegenie/skills/loader.py` (S2-01) — `SkillsLoader.load_all() -> Result[list[Skill], SkillsLoadError]`.
  - `src/codegenie/skills/model.py` (S2-01) — `Skill` Pydantic model, `frozen=True, extra="forbid"`.
  - `src/codegenie/probes/base.py` — `Probe` ABC + `@register_probe` decorator (Phase 0).

## Goal

Implement `src/codegenie/probes/layer_d/skills_index.py` as a `@register_probe(heaviness="light")` probe that calls `SkillsLoader.load_all()`, projects each `Skill` into an `IndexedSkill` model carrying `id`, `applies_to_tasks`, `applies_to_languages`, `body_offset`, `body_size`, `body_blake3` (and **nothing else** from the body), and returns a `ProbeOutput` whose `schema_slice` is a sorted list of `IndexedSkill` rows plus a `tier_counts` dict. The probe MUST NOT open any skill body byte; the loader already paid the open-and-stat cost during S2-01 (`O_NOFOLLOW | O_NOCTTY` → `safe_yaml.load` on the frontmatter only).

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** `src/codegenie/probes/layer_d/__init__.py` exists (empty package marker; module docstring referencing Layer D's role).
- [ ] **AC-2.** `src/codegenie/probes/layer_d/skills_index.py` exports exactly `__all__ = ["SkillsIndexProbe", "IndexedSkill", "SkillsIndexSlice"]`.
- [ ] **AC-3.** `IndexedSkill` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` carrying exactly: `id: SkillId`, `applies_to_tasks: tuple[str, ...]`, `applies_to_languages: tuple[str, ...]`, `body_offset: int`, `body_size: int`, `body_blake3: str`. Tuples (not lists) because the slice is hash-stable.
- [ ] **AC-4.** `SkillsIndexSlice` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` carrying: `skills: tuple[IndexedSkill, ...]` (sorted by `id`), `tier_counts: dict[Literal["user", "repo", "org"], int]`.
- [ ] **AC-5.** `SkillsIndexProbe` is `@register_probe(heaviness="light")`; `probe_id = ProbeId("skills_index")`; `applies_to_tasks = ("*",)`; `applies_to_languages = ("*",)`; `timeout_seconds=10`.
- [ ] **AC-6.** `_run()` calls `SkillsLoader(search_paths=self._resolve_search_paths(ctx)).load_all()` and on `Result.Ok(skills)` constructs the slice; on `Result.Err(SkillsLoadError(...))` emits `confidence="low"` with the typed reason on `errors`.
- [ ] **AC-7.** **Bodies never loaded.** A `tracemalloc.start()` → `_run()` → `tracemalloc.get_traced_memory()` test with a fixture whose `SKILL.md` carries a 100 MB body section asserts `peak < 20 * 1024` (20 KB). Mutation caught: any future `open(path).read()` over the skill body would blow the budget by ~5,000x.
- [ ] **AC-8.** **Anchors round-trip.** For each indexed skill, `body_offset + body_size <= os.stat(path).st_size`; opening the file at `body_offset`, reading `body_size` bytes, and computing BLAKE3 over the read bytes equals `body_blake3`. The test reads the body bytes (the test is allowed to; the probe is not).
- [ ] **AC-9.** **Slice is sorted.** `tuple(s.id for s in slice_.skills) == tuple(sorted(s.id for s in slice_.skills))`. Determinism gate: two consecutive gathers on the same fixture produce byte-identical `raw/skills-index.json`.
- [ ] **AC-10.** **Tier counts.** When the fixture has 3 skills under `~/.codegenie/skills/`, 1 under `.codegenie/skills/`, 0 under `~/.codegenie/skills-org/`, `tier_counts == {"user": 3, "repo": 1, "org": 0}` exactly.
- [ ] **AC-11.** **Symlink-refused propagates as `confidence="low"`.** A fixture with a symlinked `SKILL.md` triggers `SkillsLoader` to return `Result.Err(SkillsLoadError(reason="symlink_refused", path=...))`; the probe emits `ProbeOutput(confidence="low", errors=[...])` without raising.
- [ ] **AC-12.** **Schema slice validates.** `tests/unit/probes/layer_d/test_skills_index.py::test_slice_matches_layer_d_subschema` asserts the JSON-dumped slice round-trips through `src/codegenie/schema/probes/layer_d/skills_index.schema.json` (sub-schema lands in S6-08; this AC pins the *consumer* — the test imports the schema path and `jsonschema.validate`-s).
- [ ] **AC-13.** **`heaviness="light"`** — the `@register_probe(heaviness="light")` annotation is the registry value verified by `tests/unit/probes/layer_d/test_skills_index.py::test_registry_heaviness` reading `_PROBE_REGISTRY["skills_index"].heaviness == "light"`.
- [ ] **AC-14.** **`mypy --strict`** passes on `src/codegenie/probes/layer_d/skills_index.py`; no `Any` escapes the slice. `SkillId` is the Phase 1 / Step 1 newtype — no stringly-typed IDs.
- [ ] **AC-15.** **No body byte read.** Architectural test: `inspect.getsource(skills_index)` does not contain `read(`, `read_bytes`, `read_text`, or `pathlib.Path.open` inside `SkillsIndexProbe`. The loader does the reads (and only of frontmatter); the probe is byte-free.

## Implementation outline

1. Create `src/codegenie/probes/layer_d/__init__.py` with module docstring.
2. Create `src/codegenie/probes/layer_d/skills_index.py`:
   - Module docstring naming arch §"Component design" #9 and the progressive-disclosure commitment.
   - `IndexedSkill(BaseModel)` and `SkillsIndexSlice(BaseModel)` per AC-3/AC-4.
   - `@register_probe(heaviness="light")` `class SkillsIndexProbe(Probe):`
     - `probe_id = ProbeId("skills_index")`
     - `applies_to_tasks: tuple[str, ...] = ("*",)`, `applies_to_languages: tuple[str, ...] = ("*",)`
     - `timeout_seconds = 10`
     - `declared_inputs`: the three search-path glob roots resolved against `ctx`
     - `_run(self, ctx: ProbeContext) -> ProbeOutput`: call `SkillsLoader.load_all()`; pattern-match the `Result`; on Ok project to `IndexedSkill` tuple sorted by `id`; on Err emit `confidence="low"` slice with the error in `errors`.
3. Write `tests/unit/probes/layer_d/test_skills_index.py` per the TDD plan.
4. Write `tests/integration/probes/test_skills_index_probe.py` exercising the 100 MB-body fixture under `tracemalloc`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/probes/layer_d/test_skills_index.py`. Each test is keyed to one or more ACs and names the mutation it catches.

```python
# tests/unit/probes/layer_d/test_skills_index.py
"""Unit + integration tests for SkillsIndexProbe (S6-01).

Each test is keyed to an AC and names the mutation it catches in
its docstring (Rule 9 — tests verify intent).
"""
from __future__ import annotations

import tracemalloc
from pathlib import Path

import pytest
from blake3 import blake3

from codegenie.probes.base import ProbeContext, _PROBE_REGISTRY
from codegenie.probes.layer_d import skills_index as si


def _write_skill(path: Path, *, applies_to_tasks: list[str], body: str = "body\n") -> None:
    path.write_text(
        "---\n"
        f"id: {path.parent.name}\n"
        f"applies_to_tasks: {applies_to_tasks!r}\n"
        "applies_to_languages: ['*']\n"
        "---\n"
        + body
    )


# --- AC-3, AC-4, AC-9 ----------------------------------------------------------


def test_slice_is_sorted_and_frozen(tmp_path: Path) -> None:
    """AC-3, AC-9. Mutation caught: returning skills in load order (would
    break two-consecutive-gathers determinism) — assertion pins lexical
    sort on `id`. Also: changing `tuple` to `list` on IndexedSkill —
    hash-stability of the slice depends on tuple."""
    user_dir = tmp_path / "user" / "skills"
    user_dir.mkdir(parents=True)
    (user_dir / "zebra").mkdir()
    (user_dir / "alpha").mkdir()
    _write_skill(user_dir / "zebra" / "SKILL.md", applies_to_tasks=["distroless_migration"])
    _write_skill(user_dir / "alpha" / "SKILL.md", applies_to_tasks=["vulnerability_remediation"])

    ctx = ProbeContext.for_test(search_paths=[user_dir])  # helper from S2-01
    output = si.SkillsIndexProbe()._run(ctx)
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    assert [s.id for s in slice_.skills] == ["alpha", "zebra"]
    with pytest.raises(Exception):  # frozen Pydantic model
        slice_.skills[0].id = "mutated"  # type: ignore[misc]


# --- AC-7, AC-15 — load-bearing progressive-disclosure ------------------------


def test_tracemalloc_peak_under_20kb_on_100mb_body(tmp_path: Path) -> None:
    """AC-7. Mutation caught: any future ``Path(path).read_bytes()`` /
    ``open(path).read()`` over the body section. The fixture has a 100 MB
    body; reading it would blow the budget by ~5,000x.

    The probe MUST receive the body offset from `SkillsLoader` (S2-01)
    and never re-open the file.
    """
    user_dir = tmp_path / "user" / "skills" / "big"
    user_dir.mkdir(parents=True)
    skill_path = user_dir / "SKILL.md"
    big_body = "x" * (100 * 1024 * 1024)  # 100 MB
    _write_skill(skill_path, applies_to_tasks=["t1"], body=big_body)

    ctx = ProbeContext.for_test(search_paths=[user_dir.parent])
    tracemalloc.start()
    try:
        output = si.SkillsIndexProbe()._run(ctx)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 20 * 1024, f"peak {peak} bytes exceeds 20 KB ceiling"
    assert output.confidence in ("high", "medium")  # not "low"


def test_probe_source_does_not_open_skill_bodies() -> None:
    """AC-15. Architectural test: source-introspect `SkillsIndexProbe`
    and confirm no `read_bytes`, `read_text`, or `open(` appears in the
    class body. Mutation caught: a "convenience" addition like
    ``body_preview = path.read_text()[:200]`` would fail this test
    immediately, before tracemalloc has to catch it at runtime.
    """
    import inspect

    src = inspect.getsource(si.SkillsIndexProbe)
    for forbidden in ("read_bytes", "read_text", ".open(", "open(skill"):
        assert forbidden not in src, (
            f"SkillsIndexProbe must not open skill body bytes; found {forbidden!r}. "
            "The loader (S2-01) records body_offset/body_size/body_blake3 once; the "
            "probe re-uses those anchors. Body reads are the Planner's job."
        )


# --- AC-8 — anchors round-trip ------------------------------------------------


def test_recorded_anchors_match_actual_body_blake3(tmp_path: Path) -> None:
    """AC-8. Mutation caught: hashing the wrong byte range (e.g.,
    including the closing `---` separator) — the round-trip would fail."""
    user_dir = tmp_path / "user" / "skills" / "small"
    user_dir.mkdir(parents=True)
    skill_path = user_dir / "SKILL.md"
    _write_skill(skill_path, applies_to_tasks=["t1"], body="body bytes\n")

    ctx = ProbeContext.for_test(search_paths=[user_dir.parent])
    output = si.SkillsIndexProbe()._run(ctx)
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    indexed = slice_.skills[0]
    raw = skill_path.read_bytes()
    actual = blake3(raw[indexed.body_offset : indexed.body_offset + indexed.body_size]).hexdigest()
    assert actual == indexed.body_blake3
    assert indexed.body_offset + indexed.body_size <= len(raw)


# --- AC-10 — tier counts ------------------------------------------------------


def test_tier_counts_match_three_tier_layout(tmp_path: Path) -> None:
    """AC-10. Mutation caught: counting *all* skills as "user" tier;
    miscounting empty `~/.codegenie/skills-org/` as 1 instead of 0."""
    user = tmp_path / "user" / "skills"
    repo = tmp_path / "repo" / ".codegenie" / "skills"
    org = tmp_path / "user" / "skills-org"
    user.mkdir(parents=True)
    repo.mkdir(parents=True)
    org.mkdir(parents=True)
    for name in ("a", "b", "c"):
        (user / name).mkdir()
        _write_skill(user / name / "SKILL.md", applies_to_tasks=["t1"])
    (repo / "x").mkdir()
    _write_skill(repo / "x" / "SKILL.md", applies_to_tasks=["t1"])
    # org left empty.

    ctx = ProbeContext.for_test(search_paths=[user, repo, org])
    output = si.SkillsIndexProbe()._run(ctx)
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    assert slice_.tier_counts == {"user": 3, "repo": 1, "org": 0}


# --- AC-11 — symlink → confidence="low", no raise -----------------------------


def test_symlinked_skill_yields_low_confidence_no_raise(tmp_path: Path) -> None:
    """AC-11. Mutation caught: re-raising `SkillsLoadError` from the
    probe (would break Phase 0 coordinator failure-isolation) — the
    probe MUST construct a typed `ProbeOutput` with `confidence="low"`."""
    user_dir = tmp_path / "user" / "skills" / "linked"
    user_dir.mkdir(parents=True)
    real = tmp_path / "real_skill.md"
    _write_skill(real, applies_to_tasks=["t1"])
    (user_dir / "SKILL.md").symlink_to(real)

    ctx = ProbeContext.for_test(search_paths=[user_dir.parent])
    output = si.SkillsIndexProbe()._run(ctx)
    assert output.confidence == "low"
    assert any("symlink_refused" in str(e) for e in output.errors)


# --- AC-13 — registry heaviness annotation ------------------------------------


def test_registry_heaviness_is_light() -> None:
    """AC-13. Mutation caught: bumping to `heaviness="medium"` would
    cause the coordinator to reserve the wrong scheduling slot."""
    assert _PROBE_REGISTRY["skills_index"].heaviness == "light"


# --- AC-12 — sub-schema validation (consumer side) ----------------------------


def test_slice_matches_layer_d_subschema(tmp_path: Path) -> None:
    """AC-12. Mutation caught: schema drift — a future change to
    `IndexedSkill` (e.g., renaming `body_offset` → `offset`) would
    fail the JSON-Schema round-trip. Schema file ships in S6-08; this
    test references it by path so the schema is `Schema before
    consumer` (arch §"Design patterns applied")."""
    import json
    from importlib.resources import files

    import jsonschema

    schema = json.loads(
        (files("codegenie.schema.probes.layer_d") / "skills_index.schema.json").read_text()
    )
    user = tmp_path / "user" / "skills" / "a"
    user.mkdir(parents=True)
    _write_skill(user / "SKILL.md", applies_to_tasks=["t1"])
    ctx = ProbeContext.for_test(search_paths=[user.parent])
    output = si.SkillsIndexProbe()._run(ctx)
    jsonschema.validate(output.schema_slice, schema)
```

Run `pytest tests/unit/probes/layer_d/test_skills_index.py` — fails with `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

```python
# src/codegenie/probes/layer_d/skills_index.py
"""SkillsIndexProbe — Layer D, light heaviness.

Projects `SkillsLoader.load_all()` output into a typed slice carrying
only the indices the Planner queries (`applies_to_tasks`,
`applies_to_languages`) plus the body byte-offset anchors. Bodies are
NEVER opened by this probe — the loader (S2-01) records
`body_offset`/`body_size`/`body_blake3` in one pass over frontmatter
via `safe_yaml.load`; this probe re-uses those anchors.

Sources:
- ../phase-arch-design.md §"Component design" #9 — loader contract.
- ../../localv2.md §5.4 D2 — slice shape.
- ../ADRs/0005-secret-findings-no-plaintext-persistence.md — same
  "no plaintext" discipline applied to a different surface (skill bodies
  are not secrets, but the principle generalizes: persist anchors, not
  payloads).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from codegenie.ids import ProbeId, SkillId
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, register_probe
from codegenie.skills.loader import SkillsLoader

__all__ = ["SkillsIndexProbe", "IndexedSkill", "SkillsIndexSlice"]


class IndexedSkill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: SkillId
    applies_to_tasks: tuple[str, ...]
    applies_to_languages: tuple[str, ...]
    body_offset: int
    body_size: int
    body_blake3: str


class SkillsIndexSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    skills: tuple[IndexedSkill, ...]
    tier_counts: dict[Literal["user", "repo", "org"], int]


@register_probe(heaviness="light")
class SkillsIndexProbe(Probe):
    probe_id = ProbeId("skills_index")
    applies_to_tasks: tuple[str, ...] = ("*",)
    applies_to_languages: tuple[str, ...] = ("*",)
    timeout_seconds = 10

    def _run(self, ctx: ProbeContext) -> ProbeOutput:
        search_paths = self._resolve_search_paths(ctx)
        result = SkillsLoader(search_paths=search_paths).load_all()
        if result.is_err():
            return ProbeOutput(
                probe_id=self.probe_id,
                confidence="low",
                schema_slice={},
                errors=[str(result.unwrap_err())],
            )
        skills = sorted(result.unwrap(), key=lambda s: s.id)
        indexed = tuple(
            IndexedSkill(
                id=s.id,
                applies_to_tasks=tuple(s.applies_to_tasks),
                applies_to_languages=tuple(s.applies_to_languages),
                body_offset=s.body_offset,
                body_size=s.body_size,
                body_blake3=s.body_blake3,
            )
            for s in skills
        )
        tier_counts = self._count_by_tier(skills, search_paths)
        slice_ = SkillsIndexSlice(skills=indexed, tier_counts=tier_counts)
        return ProbeOutput(
            probe_id=self.probe_id,
            confidence="high",
            schema_slice=slice_.model_dump(mode="json"),
            errors=[],
        )
```

### Refactor

- `_resolve_search_paths` and `_count_by_tier` stay private methods on the probe class; no shared "tier classifier" — Layer D has exactly one tier-aware probe (this one) and Rule-of-Three has not been triggered.
- The Pydantic models live in the same file as the probe (not split). Layer D's sub-schemas are co-located with the probe that owns them; cross-probe sharing within Layer D is not anticipated.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_d/__init__.py` | New file — package marker; module docstring. |
| `src/codegenie/probes/layer_d/skills_index.py` | New file — `IndexedSkill`, `SkillsIndexSlice`, `SkillsIndexProbe`. |
| `tests/unit/probes/layer_d/__init__.py` | New file — empty package marker. |
| `tests/unit/probes/layer_d/test_skills_index.py` | New file — eight tests keyed to ACs. |

## Out of scope

- **Skill body reading.** The probe records anchors only. The Planner reads bodies at decision time via the recorded `body_offset`.
- **Conventions, ADRs, policy, exceptions, repo notes, repo config, external docs.** Separate Layer D probes (S6-02, S6-03, S6-04).
- **Layer D sub-schema authoring.** Ships in S6-08 alongside the freshness registrations.
- **Three-tier-merge collision handling.** S2-01's `SkillsLoader` emits `skill_shadowed` warnings; the probe consumes the de-duplicated list. Surfacing the warning in the slice is a Phase-3 concern.
- **Hostile-skills-yaml adversarial.** Ships in S7-04 (`tests/adv/phase02/test_hostile_skills_yaml.py`).

## Notes for the implementer

1. **The 100 MB-body fixture is load-bearing.** Do not lower its size to "make CI fast" — the 5,000x amplification factor is what makes the `tracemalloc` assertion mutation-resistant. If the test is genuinely slow on tmpfs, generate the body via `os.truncate` (sparse file) so disk write is O(1); the test still reads the offset/size from a real on-disk path.
2. **`SkillsLoader` already paid the open cost.** S2-01's loader does `os.open(path, O_NOFOLLOW | O_NOCTTY)` → `safe_yaml.load(frontmatter_only)` → records `body_offset = end_of_frontmatter`, `body_size = file_size - body_offset`, `body_blake3 = blake3(body_bytes).hexdigest()` in one streaming pass. This probe re-uses those values verbatim. Do **not** re-open the file.
3. **No body preview field, ever.** A "convenience" `body_preview: str` field on `IndexedSkill` would force the probe to read bytes, breaking AC-7 and AC-15. If the Planner needs a preview, it reads `body_offset[:200]` itself at decision time (the operation is O(1) and per-decision, not per-gather).
4. **`SkillId` is the Phase 1 / Step 1 newtype.** Do not use `str` (primitive obsession — flagged by the design-pattern critic in the Phase 2 validation log). The `IndexedSkill.id: SkillId` annotation is what makes `slice_.skills[0].id` carry semantic typing through to the Planner.
5. **`tier_counts` is a `dict[Literal[...], int]`, not `dict[str, int]`.** The three tiers are a closed set; a string-keyed dict invites primitive obsession ("org" vs. "Org" typos at consumer side). The `Literal` makes the consumer's `match` exhaustive.
6. **`ProbeOutput.confidence` levels.** Use `"high"` on success, `"low"` on `SkillsLoadError`. No `"medium"` — there is no "partially loaded skills" state; the loader is all-or-error per file, and a per-file error means that one file is excluded with a `skill_shadowed`-style warning, not the whole probe.
7. **`tracemalloc` is the right instrument.** Phase 2 has no `memory_profiler` dep; `tracemalloc` is stdlib and deterministic. The 20 KB ceiling is empirical-but-loose — typical peak on a 4-skill fixture is ~6 KB. Leaving headroom guards against a Pydantic version that allocates slightly more per-model without breaking the contract.
8. **Sub-schema location.** S6-08 lands `src/codegenie/schema/probes/layer_d/skills_index.schema.json`. AC-12 references it via `importlib.resources` so the test fails loudly if S6-08 forgets to ship it (or ships it under the wrong name). Don't inline the schema into the probe file — Phase 2 keeps schemas as JSON resources.
