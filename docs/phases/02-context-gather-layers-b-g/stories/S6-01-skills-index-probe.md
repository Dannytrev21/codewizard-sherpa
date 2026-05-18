# Story S6-01 — `SkillsIndexProbe` Layer D

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Done — GREEN 2026-05-17 (phase-story-executor; see [`_attempts/S6-01.md`](_attempts/S6-01.md) for the per-AC evidence table + gate log)
**Effort:** S
**Depends on:** S2-01 (`SkillsLoader` three-tier merge with `O_NOFOLLOW` + `body_offset`/`body_size`/`body_blake3` recorded on `Skill`; per-file errors surfaced via `LoadOutcome.per_file_errors`)
**ADRs honored:** 02-ADR-0005 (no plaintext persistence — body bytes are never read into memory; only the offset/size/BLAKE3 anchors persist), Phase 1 ADR-0006 (`safe_yaml` chokepoint — frontmatter loads exclusively via `safe_yaml.load`), 02-ADR-0003 (`@register_probe(heaviness=…)` is decorator-side, not an ABC field)
**Phase-2 commitment honored:** "Progressive disclosure for context" (CLAUDE.md, [`final-design.md` §"Open Q 3"](../final-design.md)) — the probe records *anchors to* skill bodies, not the bodies themselves. The Planner reads bodies directly via the recorded `body_offset` at decision time.

## Validation notes (2026-05-17, phase-story-validator v1)

This story was hardened in place against twelve `block`-severity contract mismatches with the actual S2-01 implementation (the loader returns `Result[LoadOutcome, FatalLoadError]`, not `Result[list[Skill], SkillsLoadError]`; the `Probe` ABC is `async def run(self, repo, ctx)` with `name: str = …` not `_run(self, ctx)` with `probe_id = ProbeId(…)`; `Skill.applies_to_*` carry the `TaskClassId`/`Language` newtypes, not `str`; `Skill.body_blake3` is `blake3:<64hex>` not bare hex; `ProbeOutput` carries `raw_artifacts`/`duration_ms`/`warnings`, not `probe_id`; schemas live flat at `src/codegenie/schema/probes/*.schema.json`, not under a `layer_d/` subdir; `ProbeContext` is a stdlib `@dataclass` with no `for_test` classmethod; the registry is `default_registry: Registry`, not `_PROBE_REGISTRY`; tier identity is *not* propagated through `LoadOutcome` so `tier_counts` is derived from a separate filesystem walk, not from the loader's return). Six new ACs added (empty fixture, FatalLoadError handling, per-file-error surfacing with the three-level confidence policy, shadowed-skill de-duplication propagation, byte-identical raw artifact, helper-driven `ProbeContext` construction), three mutation-resistance hardens (parametrized field-coverage smoke; property-based projection monotonicity; module-source `os.open`/`os.read` interdict), and one design-pattern harden (extract `_project_skill` and `_count_skills_per_tier` as pure helpers — functional core / imperative shell). The original draft's `tier_counts` derivation was unimplementable as written (the loader does not expose tier membership per skill); the harden routes it through a pure filesystem-enumeration helper that does *not* read body bytes and is therefore consistent with AC-16. Full report: [`_validation/S6-01-skills-index-probe.md`](_validation/S6-01-skills-index-probe.md). Verdict: **HARDENED**.

## Context

The Planner needs to know **which Skills apply to which task classes and languages** when it dispatches a remediation. It does **not** need the skill bodies inlined into `repo-context.yaml` — that would explode the artifact (a typical skill body is ~3 KB; a typical install has 100+ skills; bodies are markdown the Planner will read fresh anyway). The body byte-offset + size + BLAKE3 are the recorded **anchors**; the gather pipeline never opens the body bytes for this probe.

`SkillsLoader` (S2-01) already does the three-tier merge (`~/.codegenie/skills/`, `.codegenie/skills/`, `~/.codegenie/skills-org/`) and returns `Result[LoadOutcome, FatalLoadError]`. On `Ok`, `LoadOutcome` carries `skills: list[Skill]` (de-duplicated first-tier-wins) and `per_file_errors: list[SkillsLoadError]` (the discriminated union over `SymlinkRefused | UnsafeYaml | FrontmatterUnterminated | SchemaViolation | IoFailure`). Each `Skill` carries `body_offset: int`, `body_size: int`, and `body_blake3: str` (regex-pinned `^blake3:[0-9a-f]{64}$`) from the loader's single streaming pass over the file. `applies_to_tasks` and `applies_to_languages` are typed `list[TaskClassId]` and `list[Language]` respectively.

The probe's job is **purely indexing**: project each `Skill` into a typed slice with the two query keys the Planner uses — `applies_to_tasks` and `applies_to_languages` — plus the offset/size/blake3 anchors, plus a tier-counts derived statistic. The body bytes never enter process memory inside this probe (the loader already paid the streaming hash cost).

The load-bearing observable: a 100 MB-body skill fixture (one `SKILL.md` with a 100 MB body section) gathers without the body ever entering process memory. `tracemalloc` peak attributable to `SkillsIndexProbe.run` plus the loader call it triggers must stay under 1 MB total (a generous ceiling that comfortably covers Pydantic-model allocations for the typical install of ≤ 100 skills; the loader's own envelope is ~256 KiB per its docstring §2). The 5,000x amplification factor (1 MB ceiling vs. 100 MB body) is what makes the assertion mutation-resistant: any future `.read_bytes()` over the body would blow the budget immediately.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Component design" #9 `SkillsLoader`](../phase-arch-design.md) — the loader returns `Result[LoadOutcome, FatalLoadError]`; `LoadOutcome.skills` is the de-duplicated first-tier-wins list; `LoadOutcome.per_file_errors` carries the discriminated union of `SymlinkRefused | UnsafeYaml | FrontmatterUnterminated | SchemaViolation | IoFailure`; constructor pure, first I/O is `load_all()`.
  - [`../phase-arch-design.md` §"Edge cases" rows 8/9/16](../phase-arch-design.md) — symlink-refused, hostile-YAML, and three-tier collision are *per-file* failures (this skill skipped; other skills load; loud CLI warning). They do NOT collapse the whole probe to `confidence="low"`.
  - [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) row "Schema before consumer" — the slice has at least one Phase 2 consumer (`tests/integration/probes/test_skills_index_probe.py`).
- **Phase ADRs:**
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — bodies are never loaded; the probe's commitment to anchors-only is the same chokepoint discipline applied to a different surface.
  - [`../ADRs/0003-coordinator-heaviness-sort-annotation.md`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) — `heaviness` is a `@register_probe(heaviness=…)` kwarg, NOT a `Probe` ABC field; verified via `default_registry`.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) first bullet — slice shape and the body-offset-recorded / bodies-not-loaded commitment.
  - [`../../localv2.md` §5.4 D2 SkillsIndexProbe](../../../localv2.md) — slice shape; "Adding a new variant is dropping a new SKILL.md. No probe changes."
- **Existing kernel (S2-01 landed):**
  - `src/codegenie/skills/loader.py` (S2-01) — `SkillsLoader.load_all() -> Result[LoadOutcome, FatalLoadError]`; `SkillsLoader.default()` classmethod returns the pinned three-tier ordering.
  - `src/codegenie/skills/model.py` (S2-01) — `Skill`, `EvidenceQuery`, `Tier: TypeAlias = Literal["user","repo","org"]`, `TIERS: Final[tuple[Tier,...]] = ("user","repo","org")`.
  - `src/codegenie/probes/base.py` — `Probe` ABC (`name: str`, `layer`, `tier`, `applies_to_*: list[str]`, `requires: list[str]`, `timeout_seconds: int`, `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`). Frozen contract — story DOES NOT propose edits.
  - `src/codegenie/probes/registry.py` — `default_registry: Registry`; `@register_probe(heaviness=…, runs_last=…)` decorator; `ProbeRegEntry(cls, heaviness, runs_last, registration_index)`.
  - `src/codegenie/types/identifiers.py` — `SkillId`, `TaskClassId`, `Language`, `ProbeId` newtypes (re-exported by import).
  - `src/codegenie/schema/probes/dep_graph.schema.json` etc. — Phase 2 schemas live FLAT under `src/codegenie/schema/probes/` (no per-layer subdir).
- **Test precedent:**
  - `tests/unit/probes/layer_b/test_dep_graph.py` — canonical sibling test using `asyncio.run(probe.run(_make_repo(...), ctx))` to invoke an `async` probe. Mirror this idiom.
  - `tests/unit/skills/test_loader.py` (S2-01) — pattern for fixture construction, `content_hash_bytes` for BLAKE3-prefixed comparison, `_write_skill`-style helpers.

## Goal

Implement `src/codegenie/probes/layer_d/skills_index.py` as a `@register_probe(heaviness="light")` probe that calls `SkillsLoader.default().load_all()` (or accepts caller-resolved search paths via `ctx.config`), projects each loaded `Skill` into an `IndexedSkill` typed-record carrying `id: SkillId`, `applies_to_tasks: tuple[TaskClassId, ...]`, `applies_to_languages: tuple[Language, ...]`, `body_offset: int`, `body_size: int`, `body_blake3: str` (the `blake3:<64hex>` form the loader produces — preserved verbatim, **no re-hash**), and emits a `ProbeOutput` whose `schema_slice` is a deterministic sorted list of `IndexedSkill` rows, a `tier_counts: dict[Literal["user","repo","org"], int]`, and a `per_file_errors: list[…]` summary. The probe MUST NOT open any skill file (`os.open`, `Path.open`, `read_bytes`, `read_text` are all forbidden in the probe module's source); the loader paid the open/scan/hash cost once. Tier counts derive from a pure enumeration helper that walks `SKILL.md` filenames under each tier (filename-only — `Path.rglob("SKILL.md")`, no file reads), not from any field on `LoadOutcome`.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

### Module layout & types

- [ ] **AC-1.** `src/codegenie/probes/layer_d/__init__.py` exists (empty package marker; one-line module docstring naming "Layer D — organizational-knowledge probes (skills, conventions, ADRs, policy, exceptions, repo notes, repo config, external docs)").
- [ ] **AC-2.** `src/codegenie/probes/layer_d/skills_index.py` exports exactly `__all__ = ["IndexedSkill", "SkillsIndexProbe", "SkillsIndexSlice"]` (alphabetical).
- [ ] **AC-3.** `IndexedSkill` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` carrying exactly: `id: SkillId`, `applies_to_tasks: tuple[TaskClassId, ...]`, `applies_to_languages: tuple[Language, ...]`, `body_offset: Annotated[int, Field(ge=0)]`, `body_size: Annotated[int, Field(ge=0)]`, `body_blake3: Annotated[str, Field(pattern=r"^blake3:[0-9a-f]{64}$")]`. Tuples (not lists) because the slice is hash-stable. The three newtypes are preserved end-to-end (NO `tuple[str, ...]` — primitive-obsession regression flagged by `ADR-0033 §1` and `phase-arch-design §"Anti-patterns avoided"`).
- [ ] **AC-4.** `SkillsIndexSlice` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` carrying: `skills: tuple[IndexedSkill, ...]` (sorted by `id` ascending; lexicographic stable), `tier_counts: dict[Literal["user", "repo", "org"], int]` (always exactly the three keys, never partial), `per_file_errors: tuple[str, ...]` (each element is the JSON dump `model_dump_json()` of one `SkillsLoadError` variant — strings, not raw models, because `dict[str, Any]` slice surface forbids nested Pydantic).

### Probe registration

- [ ] **AC-5.** `SkillsIndexProbe` is `@register_probe(heaviness="light")` (kwarg form — 02-ADR-0003); class attributes are exactly `name: str = "skills_index"`, `layer = "D"`, `tier = "base"`, `applies_to_tasks: list[str] = ["*"]`, `applies_to_languages: list[str] = ["*"]`, `requires: list[str] = []`, `timeout_seconds: int = 10`, `declared_inputs: list[str] = [...]` (set in `__init__` to the three search-path tokens — see AC-7). **All list-typed** because the frozen Phase-0 `Probe` ABC is `list[str]`, not tuple (the Pydantic *slice* uses tuples; the ABC contract is unchanged).
- [ ] **AC-6.** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:` is the implementation entry point (NOT a private `_run` — story aligns to the `async`-Probe contract proven by `DepGraphProbe`, `IndexHealthProbe`, etc.). The method calls `SkillsLoader(search_paths=self._resolve_search_paths(repo, ctx)).load_all()` and pattern-matches the `Result`:
  - On `Ok(LoadOutcome(skills=skills, per_file_errors=errors))` it projects skills via `_project_skill`, sorts by `id`, counts tiers via `_count_skills_per_tier(search_paths)`, and emits `ProbeOutput(schema_slice=slice_.model_dump(mode="json"), raw_artifacts=[raw_path], confidence=<see AC-9>, duration_ms=elapsed_ms, warnings=[], errors=[err.model_dump_json() for err in errors])`.
  - On `Err(FatalLoadError(attempted=…))` it emits `ProbeOutput(schema_slice={"skills": [], "tier_counts": {"user":0,"repo":0,"org":0}, "per_file_errors": []}, raw_artifacts=[], confidence="low", duration_ms=elapsed_ms, warnings=[], errors=[fatal.model_dump_json()])`.

### Search-path resolution

- [ ] **AC-7.** `_resolve_search_paths(self, repo, ctx) -> list[Path]` is a pure method on the probe (no I/O) that returns `[user_tier, repo_tier, org_tier]` resolved as follows: `user_tier` is `Path(ctx.config.get("skills.user_path", "~/.codegenie/skills/")).expanduser()`; `repo_tier` is `repo.root / Path(ctx.config.get("skills.repo_path", ".codegenie/skills/"))`; `org_tier` is `Path(ctx.config.get("skills.org_path", "~/.codegenie/skills-org/")).expanduser()`. The probe's `declared_inputs` (set in `__init__`) names the three string tokens `"skills_user_search_path:<expanded>"`, `"skills_repo_search_path:.codegenie/skills/"`, `"skills_org_search_path:<expanded>"` so cache invalidation fires when any tier path config changes (mirrors the `dep_graph_strategy_set:<resolved>` precedent at `src/codegenie/probes/layer_b/dep_graph.py:420`).

### Confidence policy (three-state, mutation-resistant)

- [ ] **AC-9.** Confidence is computed by a pure helper `_compute_confidence(skills, per_file_errors) -> Literal["high","medium","low"]`:
  - `"high"` iff `per_file_errors == []` (every discovered file loaded cleanly), independent of whether `skills == []` (an empty install is still a clean state).
  - `"medium"` iff `per_file_errors != []` AND `skills != []` (partial success — some skills loaded, some failed).
  - `"low"` iff `per_file_errors != []` AND `skills == []` (every discovered file failed; the loader found candidates but produced nothing usable).

### Bodies-never-loaded — load-bearing structural proof

- [ ] **AC-10.** **Bodies never loaded (tracemalloc).** A `tracemalloc.start()` → `asyncio.run(probe.run(...))` → `tracemalloc.get_traced_memory()` test with a fixture whose `SKILL.md` carries a 100 MB body section asserts `peak < 1024 * 1024` (1 MB). Mutation caught: any future `path.read_bytes()` over the skill body would blow the budget by ~100x. The 1 MB ceiling comfortably absorbs the loader's own ~256 KiB envelope plus Pydantic-model allocations for a 4-skill fixture; tightening to 20 KB (the original draft's ceiling) is brittle against Pydantic version drift.
- [ ] **AC-11.** **No file open in the probe module (source-level interdict).** `inspect.getsource(skills_index_module)` does NOT contain any of the strings `"os.open"`, `"os.read"`, `".read_bytes"`, `".read_text"`, `".open("` anywhere in the module. (The pattern `Path(...).open` is also forbidden via the substring `".open("`.) The loader does every open; the probe is a pure consumer of `Skill` records.

### Anchor integrity

- [ ] **AC-12.** **Anchors round-trip — BLAKE3 prefix-aware.** For each indexed skill, `body_offset + body_size <= os.stat(path).st_size`; opening the file in the *test* (not the probe) at `body_offset`, reading `body_size` bytes, and computing `codegenie.hashing.content_hash_bytes(body)` (which produces the canonical `blake3:<64hex>` form) equals `indexed.body_blake3` exactly. The test is allowed to read; the probe is not. Mutation caught: hashing the wrong byte range, dropping the `blake3:` prefix, or recomputing with a different hash function.

### Determinism & sorting

- [ ] **AC-13.** **Slice is sorted, sort is stable, JSON is byte-identical.** `[s.id for s in slice_.skills] == sorted([s.id for s in slice_.skills])`. Two consecutive `asyncio.run(probe.run(...))` invocations on the same fixture produce byte-identical `json.dumps(output.schema_slice, sort_keys=True)`. Mutation caught: dict-iteration-order leakage, non-stable sort, recomputed timestamps escaping into the slice.

### Tier counts (filesystem-enumeration-derived, body-free)

- [ ] **AC-14.** **Tier counts via pure enumeration.** When the fixture has 3 SKILL.md files under `user_tier`, 1 under `repo_tier`, 0 under `org_tier`, the slice's `tier_counts == {"user": 3, "repo": 1, "org": 0}` exactly. Counts are derived from `_count_skills_per_tier(search_paths: list[Path]) -> dict[Tier, int]` (pure helper that does `len(list(path.rglob("SKILL.md")))` per tier — filename enumeration only, no file reads, no symlink follow; missing tier paths count as 0). Counts are pre-de-duplication (a shadowed skill counts as 1 in the tier where the file lives) so `sum(tier_counts.values()) >= len(slice_.skills)`.

### Empty & fatal corners

- [ ] **AC-15.** **Empty fixture.** With no `SKILL.md` files anywhere under any tier, the slice has `skills == ()`, `tier_counts == {"user":0,"repo":0,"org":0}`, `per_file_errors == ()`, and `confidence == "high"` (clean empty state, not an error).
- [ ] **AC-16.** **FatalLoadError handling.** If `SkillsLoader.load_all()` returns `Err(FatalLoadError(reason="all_tiers_unreadable", attempted=[…]))`, the probe emits `confidence="low"`, schema_slice with empty skills and zeroed tier_counts, and `errors=[<json of FatalLoadError>]`. The probe does NOT re-raise the FatalLoadError.

### Per-file errors surface (do not swallow)

- [ ] **AC-17.** **Per-file errors round-trip.** A fixture with one good `SKILL.md` and one symlinked `SKILL.md` produces `confidence="medium"`, `len(slice_.skills) == 1`, `len(slice_.per_file_errors) == 1`, and `json.loads(slice_.per_file_errors[0])["reason"] == "symlink_refused"`. Mutation caught: silently dropping `per_file_errors`, conflating "some failed" with "all failed", erroneously raising on symlink. (Replaces the original draft's AC-11 which incorrectly assumed `Result.Err` on symlink — per-file failures stay inside `Ok(LoadOutcome)`.)

### Shadowing propagation

- [ ] **AC-18.** **Shadowed-skill de-duplication propagates.** A fixture with the same `id: alpha` skill under both user and repo tiers produces exactly one `IndexedSkill(id=SkillId("alpha"))` in the slice (first-tier-wins; user wins), AND `tier_counts == {"user": 1, "repo": 1, "org": 0}` (both files are *present on disk*; only one survives de-dup; the count reflects on-disk presence — operators reading the report see that a shadow happened). The loader's `skill_shadowed` structlog warning is observable but the probe does NOT need to re-emit it (already-loud at S2-01).

### Schema validation

- [ ] **AC-19.** **Schema slice validates.** `tests/unit/probes/layer_d/test_skills_index.py::test_slice_matches_subschema` asserts the JSON-dumped slice round-trips through `src/codegenie/schema/probes/skills_index.schema.json` (FLAT layout — `schema/probes/`, NOT `schema/probes/layer_d/`; the existing `dep_graph.schema.json`, `index_health.schema.json` etc. precedents prove the flat convention). The sub-schema ships in S6-08; this AC pins the *consumer-side import path* so S6-08 failing to ship the schema (or shipping it under the wrong name) is loud, not silent. Test imports via `from importlib.resources import files; files("codegenie.schema.probes") / "skills_index.schema.json"`.

### Registry annotation

- [ ] **AC-20.** **Registry annotation — `heaviness="light"`.** A test imports `from codegenie.probes.registry import default_registry`, finds the entry via `entry = next(e for e in default_registry._entries if e.cls.name == "skills_index")` (or via a public `Registry.for_task(...)` if one exists), and asserts `entry.heaviness == "light"` and `entry.runs_last is False`. Uses the actual registry surface — there is no `_PROBE_REGISTRY` dict (the original draft was a documentation-bug; the canonical surface is `default_registry: Registry`).

### Static typing

- [ ] **AC-21.** **`mypy --strict`** passes on `src/codegenie/probes/layer_d/skills_index.py`; no `Any` escapes the slice. `SkillId`/`TaskClassId`/`Language` are preserved through projection (no `cast(str, …)` to launder the newtypes into raw `str`). The pydantic models forbid `Any` field types.

### Mutation-resistance / property-based

- [ ] **AC-22.** **Field-coverage parametrized smoke.** A parametrized test iterates over `IndexedSkill.model_fields.keys()` and asserts the projected `IndexedSkill` for a canonical fixture has every field set to a non-default value (e.g., `body_offset > 0`, `body_size > 0`, `body_blake3` starts with `"blake3:"`, `id` non-empty, both `applies_to_*` tuples non-empty). Mutation caught: silently dropping a field in `_project_skill` (e.g., forgetting `applies_to_languages`).
- [ ] **AC-23.** **Hypothesis property — projection is order-preserving and cardinality-preserving.** A `@given(skill_lists())` property test (using a Hypothesis strategy that builds `Skill` instances directly, no filesystem) asserts:
  - `len(_project_skills_sorted(skills)) == len({s.id for s in skills})` (cardinality matches the input's unique-by-id count — proves projection neither duplicates nor drops).
  - The projected tuple is sorted: `[s.id for s in _project_skills_sorted(skills)] == sorted({s.id for s in skills})`.

  Catches subtle bugs the example-based tests miss (e.g., a stable-sort-but-not-actually-sorted regression on edge cases like single-element or identical-prefix IDs).

## Implementation outline

1. Create `src/codegenie/probes/layer_d/__init__.py` with the one-line module docstring (per AC-1).
2. Create `src/codegenie/probes/layer_d/skills_index.py`:
   - Module docstring naming arch §"Component design" #9 and the progressive-disclosure commitment.
   - **Functional core** (top of file): `_project_skill(skill: Skill) -> IndexedSkill`, `_project_skills_sorted(skills: Sequence[Skill]) -> tuple[IndexedSkill, ...]`, `_count_skills_per_tier(search_paths: list[Path]) -> dict[Tier, int]`, `_compute_confidence(skills, per_file_errors) -> Literal["high","medium","low"]`. All pure (no I/O except `_count_skills_per_tier`'s `rglob`, which reads directory entries only — not file bodies). Each helper is independently testable without a Probe instance.
   - `IndexedSkill(BaseModel)` and `SkillsIndexSlice(BaseModel)` per AC-3/AC-4.
   - **Imperative shell**: `@register_probe(heaviness="light")` `class SkillsIndexProbe(Probe):` with the ABC-correct class attributes (AC-5).
     - `__init__(self) -> None`: sets `self.declared_inputs` based on the resolved search-path tokens (AC-7).
     - `_resolve_search_paths(self, repo: RepoSnapshot, ctx: ProbeContext) -> list[Path]`: pure resolution (AC-7).
     - `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`: dispatches to `SkillsLoader(search_paths=...).load_all()`, pattern-matches the `Result`, calls the four pure helpers, writes the raw artifact to `ctx.output_dir / "skills-index.json"`, and returns the `ProbeOutput`.
3. Add `src/codegenie/schema/probes/skills_index.schema.json` placeholder OR — preferred — leave the schema file as an S6-08 dependency and have AC-19 fail loudly until S6-08 lands it. The implementer flags this as an explicit S6-08 dependency in the PR description.
4. Write `tests/unit/probes/layer_d/__init__.py` (empty marker) and `tests/unit/probes/layer_d/test_skills_index.py` per the TDD plan.
5. Write `tests/integration/probes/test_skills_index_probe.py` exercising the 100 MB-body fixture under `tracemalloc` (AC-10) — sparse-file generation (`os.truncate`) to keep CI wall-clock under 1 s.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/probes/layer_d/test_skills_index.py`. Each test is keyed to one or more ACs and names the mutation it catches.

```python
# tests/unit/probes/layer_d/test_skills_index.py
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


def _make_context(tmp_path: Path, *, config_overrides: dict[str, Any] | None = None) -> ProbeContext:
    """Construct a ``ProbeContext`` with every required field explicit.

    Catches missing-required-field regressions immediately: any future
    addition to the dataclass without an ADR amendment fails *this* line
    rather than each individual test in a flaky way.
    """
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
    path: Path, *, applies_to_tasks: list[str], applies_to_languages: list[str] = ["*"], body: str = "body\n"
) -> None:
    """Write a SKILL.md file. Caller pre-creates the parent dir."""
    path.write_text(
        "---\n"
        f"id: {path.parent.name}\n"
        f"applies_to_tasks: {applies_to_tasks!r}\n"
        f"applies_to_languages: {applies_to_languages!r}\n"
        "---\n"
        + body
    )


def _run_probe(repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
    """Sync wrapper for ``async def run`` (mirrors test_dep_graph.py:108 idiom)."""
    return asyncio.run(si.SkillsIndexProbe().run(repo, ctx))


# --- AC-3, AC-4, AC-13 --------------------------------------------------------


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

    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    assert [s.id for s in slice_.skills] == ["alpha", "zebra"]
    with pytest.raises(Exception):  # frozen Pydantic model
        slice_.skills[0].id = "mutated"  # type: ignore[misc]


def test_two_consecutive_gathers_byte_identical_json(tmp_path: Path) -> None:
    """AC-13 (second clause). Mutation caught: any timestamp leakage,
    dict-iteration-order escape, or non-stable sort."""
    user_dir = tmp_path / "user" / "skills" / "a"
    user_dir.mkdir(parents=True)
    _write_skill(user_dir / "SKILL.md", applies_to_tasks=["t1"])

    out1 = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    out2 = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    assert json.dumps(out1.schema_slice, sort_keys=True) == json.dumps(out2.schema_slice, sort_keys=True)


# --- AC-10, AC-11 — load-bearing progressive-disclosure -----------------------


def test_tracemalloc_peak_under_1mb_on_100mb_body(tmp_path: Path) -> None:
    """AC-10. Mutation caught: any future ``path.read_bytes()`` /
    ``open(path).read()`` over the body section. The fixture has a 100 MB
    body; reading it would blow the budget by ~100x.

    Uses a sparse file (os.truncate) so the test wall-clock stays under 1 s
    while the file-size invariant the loader walks is real.
    """
    import os as _os

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
    _os.utime(skill_path, None)

    tracemalloc.start()
    try:
        output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1024 * 1024, f"peak {peak} bytes exceeds 1 MB ceiling"
    assert output.confidence in ("high", "medium")  # not "low"


def test_probe_module_source_has_no_file_open(tmp_path: Path) -> None:
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


# --- AC-12 — anchors round-trip (BLAKE3 prefix-aware) ------------------------


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
    assert content_hash_bytes(body) == indexed.body_blake3  # ``blake3:<64hex>``
    assert indexed.body_offset + indexed.body_size <= len(raw)
    assert indexed.body_blake3.startswith("blake3:")


# --- AC-14 — tier counts (filesystem-enumeration-derived) ---------------------


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


# --- AC-15 — empty fixture ----------------------------------------------------


def test_empty_fixture_yields_high_confidence(tmp_path: Path) -> None:
    """AC-15. Mutation caught: treating zero skills as an error
    (returning ``confidence="low"`` on a clean empty install)."""
    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    assert slice_.skills == ()
    assert slice_.tier_counts == {"user": 0, "repo": 0, "org": 0}
    assert slice_.per_file_errors == ()
    assert output.confidence == "high"


# --- AC-17 — per-file errors round-trip --------------------------------------


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
    real.write_text("---\nid: malicious\napplies_to_tasks: ['*']\napplies_to_languages: ['*']\n---\nx\n")
    (user_dir / "linked" / "SKILL.md").symlink_to(real)

    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    slice_ = si.SkillsIndexSlice.model_validate(output.schema_slice)
    assert output.confidence == "medium"
    assert len(slice_.skills) == 1
    assert len(slice_.per_file_errors) == 1
    assert json.loads(slice_.per_file_errors[0])["reason"] == "symlink_refused"


# --- AC-18 — shadowed-skill de-duplication propagates -----------------------


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


# --- AC-16 — FatalLoadError ---------------------------------------------------


def test_fatal_load_error_yields_low_confidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


# --- AC-20 — registry annotation ---------------------------------------------


def test_registry_heaviness_is_light() -> None:
    """AC-20. Mutation caught: bumping to ``heaviness="medium"`` would
    cause the coordinator to reserve the wrong scheduling slot;
    forgetting the kwarg form would default to "light" silently. Verifies
    against the actual registry surface (``default_registry``), not a
    stand-in ``_PROBE_REGISTRY``."""
    entry = next(e for e in default_registry._entries if e.cls.name == "skills_index")
    assert entry.heaviness == "light"
    assert entry.runs_last is False


# --- AC-22 — field-coverage parametrized smoke ------------------------------


@pytest.mark.parametrize("field_name", list(si.IndexedSkill.model_fields.keys()))
def test_every_indexed_skill_field_populated_from_canonical_fixture(
    tmp_path: Path, field_name: str
) -> None:
    """AC-22. Mutation caught: silently dropping a field in
    ``_project_skill`` (e.g., forgetting ``applies_to_languages``).
    Parametrized over the model's declared fields so adding a new field
    auto-extends the test surface."""
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
    # Each field must be populated to a non-default-shaped value.
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


# --- AC-23 — Hypothesis projection property ----------------------------------


def test_projection_is_cardinality_and_order_preserving() -> None:
    """AC-23. Property: for any list of Skill instances with unique ids,
    ``_project_skills_sorted`` returns a tuple of the same length whose
    ids are the sorted set of input ids. Mutation caught: stable-sort
    bugs on single-element or identical-prefix IDs; accidental
    de-duplication; sort-key drift."""
    from hypothesis import given, strategies as st

    from codegenie.skills.model import Skill
    from codegenie.types.identifiers import Language, SkillId, TaskClassId

    @st.composite
    def _skills(draw: Any) -> list[Skill]:
        ids = draw(st.lists(st.text(min_size=1, max_size=8, alphabet="abcdefg"), min_size=0, max_size=12, unique=True))
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

    _prop()  # type: ignore[call-arg]


# --- AC-19 — sub-schema validation (consumer side) ---------------------------


def test_slice_matches_subschema(tmp_path: Path) -> None:
    """AC-19. Mutation caught: schema drift — a future change to
    ``IndexedSkill`` (e.g., renaming ``body_offset`` → ``offset``) would
    fail the JSON-Schema round-trip. Schema file ships in S6-08; this
    test references it by ``importlib.resources`` so the schema is
    `Schema before consumer` (arch §"Design patterns applied")."""
    import jsonschema
    from importlib.resources import files

    schema = json.loads(
        (files("codegenie.schema.probes") / "skills_index.schema.json").read_text()
    )
    user = tmp_path / "user" / "skills" / "a"
    user.mkdir(parents=True)
    _write_skill(user / "SKILL.md", applies_to_tasks=["t1"])
    output = _run_probe(_make_repo(tmp_path), _make_context(tmp_path))
    jsonschema.validate(output.schema_slice, schema)
```

Run `pytest tests/unit/probes/layer_d/test_skills_index.py` — fails with `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

```python
# src/codegenie/probes/layer_d/skills_index.py
"""SkillsIndexProbe — Layer D, light heaviness.

Projects ``SkillsLoader.load_all()`` output into a typed slice carrying
only the indices the Planner queries (``applies_to_tasks``,
``applies_to_languages``) plus the body byte-offset anchors. Bodies are
NEVER opened by this probe — the loader (S2-01) records
``body_offset``/``body_size``/``body_blake3`` in one pass over
frontmatter via ``safe_yaml.load``; this probe re-uses those anchors.

Sources:
- ../phase-arch-design.md §"Component design" #9 — loader contract.
- ../../localv2.md §5.4 D2 — slice shape.
- ../ADRs/0005-secret-findings-no-plaintext-persistence.md — same
  "no plaintext" discipline applied to a different surface.
- ../ADRs/0003-coordinator-heaviness-sort-annotation.md — ``heaviness``
  is registry-side, not on the Probe ABC.
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
from codegenie.skills.loader import FatalLoadError, LoadOutcome, SkillsLoader, SkillsLoadError
from codegenie.skills.model import TIERS, Skill, Tier
from codegenie.result import Err, Ok
from codegenie.types.identifiers import Language, SkillId, TaskClassId

__all__ = ["IndexedSkill", "SkillsIndexProbe", "SkillsIndexSlice"]


# ---------------------------------------------------------------------------
# Pydantic models (slice surface).
# ---------------------------------------------------------------------------


class IndexedSkill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: SkillId
    applies_to_tasks: tuple[TaskClassId, ...]
    applies_to_languages: tuple[Language, ...]
    body_offset: Annotated[int, Field(ge=0)]
    body_size: Annotated[int, Field(ge=0)]
    body_blake3: Annotated[str, Field(pattern=r"^blake3:[0-9a-f]{64}$")]


class SkillsIndexSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    skills: tuple[IndexedSkill, ...]
    tier_counts: dict[Literal["user", "repo", "org"], int]
    per_file_errors: tuple[str, ...]


# ---------------------------------------------------------------------------
# Functional core — pure helpers, independently testable.
# ---------------------------------------------------------------------------


def _project_skill(skill: Skill) -> IndexedSkill:
    """Project a loaded ``Skill`` into the indexable slice shape.

    Newtypes preserved end-to-end (ADR-0033 §1 primitive-obsession).
    """
    return IndexedSkill(
        id=skill.id,
        applies_to_tasks=tuple(skill.applies_to_tasks),
        applies_to_languages=tuple(skill.applies_to_languages),
        body_offset=skill.body_offset,
        body_size=skill.body_size,
        body_blake3=skill.body_blake3,
    )


def _project_skills_sorted(skills: Sequence[Skill]) -> tuple[IndexedSkill, ...]:
    """Project + lexicographic-stable sort by ``id``."""
    return tuple(_project_skill(s) for s in sorted(skills, key=lambda s: s.id))


def _count_skills_per_tier(search_paths: Sequence[Path]) -> dict[Tier, int]:
    """Count SKILL.md filenames per tier — enumeration only, no body reads.

    Missing tier paths count as 0. Symlinked SKILL.md still counts as a
    discovery (the per-file load is the loader's concern; this is a
    presence-on-disk statistic).
    """
    counts: dict[Tier, int] = {t: 0 for t in TIERS}
    for tier, path in zip(TIERS, search_paths):
        if path.exists():
            counts[tier] = sum(1 for _ in path.rglob("SKILL.md"))
    return counts


def _compute_confidence(
    skills: Sequence[Skill], per_file_errors: Sequence[SkillsLoadError]
) -> Literal["high", "medium", "low"]:
    """Three-state confidence (see story AC-9)."""
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
    name: str = "skills_index"
    layer = "D"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 10

    def __init__(self) -> None:
        super().__init__()
        # Search-path tokens land in declared_inputs so cache invalidates
        # when any tier path config changes (mirrors dep_graph.py:420
        # ``dep_graph_strategy_set:<resolved>`` precedent).
        self.declared_inputs = [
            "skills_user_search_path:~/.codegenie/skills/",
            "skills_repo_search_path:.codegenie/skills/",
            "skills_org_search_path:~/.codegenie/skills-org/",
        ]

    def _resolve_search_paths(self, repo: RepoSnapshot, ctx: ProbeContext) -> list[Path]:
        user = Path(ctx.config.get("skills.user_path", "~/.codegenie/skills/")).expanduser()
        repo_tier = repo.root / Path(ctx.config.get("skills.repo_path", ".codegenie/skills/"))
        org = Path(ctx.config.get("skills.org_path", "~/.codegenie/skills-org/")).expanduser()
        return [user, repo_tier, org]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        search_paths = self._resolve_search_paths(repo, ctx)
        result = SkillsLoader(search_paths=search_paths).load_all()
        if isinstance(result, Err):
            slice_ = SkillsIndexSlice(
                skills=(),
                tier_counts={t: 0 for t in TIERS},
                per_file_errors=(),
            )
            return ProbeOutput(
                schema_slice=slice_.model_dump(mode="json"),
                raw_artifacts=[],
                confidence="low",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                warnings=[],
                errors=[result.error.model_dump_json()],
            )
        assert isinstance(result, Ok)
        outcome: LoadOutcome = result.value
        slice_ = SkillsIndexSlice(
            skills=_project_skills_sorted(outcome.skills),
            tier_counts=_count_skills_per_tier(search_paths),
            per_file_errors=tuple(err.model_dump_json() for err in outcome.per_file_errors),
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
            errors=[e for e in slice_.per_file_errors],
        )
```

### Refactor

- `_project_skill`, `_project_skills_sorted`, `_count_skills_per_tier`, `_compute_confidence` are pure module-level functions (functional core). The probe class is the imperative shell — opens no files, reads no bodies, performs no business logic beyond orchestration. This makes every business invariant unit-testable without `asyncio.run` or filesystem fixtures.
- No shared "tier classifier" abstraction yet — Layer D has exactly one tier-aware probe (this one); rule-of-three has not triggered. **Open/Closed seam documented:** when the third tier-aware Layer-D probe appears (S6-02 `ConventionsCatalogProbe` is tier-aware but with a different tier set; a third would push past rule-of-three), extract `_count_files_per_tier(search_paths, glob_pattern)` into `src/codegenie/probes/_shared/tier_counts.py`. Tracker: file an issue when S6-02 lands.
- The Pydantic models stay co-located with the probe (Layer D's sub-schemas are probe-owned; cross-probe sharing within Layer D is not anticipated).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_d/__init__.py` | New file — package marker; one-line module docstring naming Layer D's role. |
| `src/codegenie/probes/layer_d/skills_index.py` | New file — pure helpers + `IndexedSkill` + `SkillsIndexSlice` + `SkillsIndexProbe`. |
| `tests/unit/probes/layer_d/__init__.py` | New file — empty package marker. |
| `tests/unit/probes/layer_d/test_skills_index.py` | New file — 14 tests keyed to ACs (including the parametrized field-coverage and Hypothesis property). |
| (S6-08 dependency) `src/codegenie/schema/probes/skills_index.schema.json` | Forward dependency. AC-19 fails loudly until S6-08 ships the schema; implementer flags in PR description. |

## Out of scope

- **Skill body reading.** The probe records anchors only. The Planner reads bodies at decision time via the recorded `body_offset`.
- **Conventions, ADRs, policy, exceptions, repo notes, repo config, external docs.** Separate Layer D probes (S6-02, S6-03, S6-04).
- **Layer D sub-schema authoring.** Ships in S6-08 alongside the freshness registrations; AC-19 surfaces the dependency.
- **Three-tier-merge collision handling.** S2-01's `SkillsLoader` emits `skill_shadowed` warnings; the probe consumes the de-duplicated list. Surfacing the warning in the slice (separate from `per_file_errors`) is a Phase-3 concern.
- **Hostile-skills-yaml adversarial.** Ships in S7-04 (`tests/adv/phase02/test_hostile_skills_yaml.py`).
- **Adding `tier` membership to `Skill` / `LoadOutcome`.** That is an S2-01 amendment and out of scope for S6-01; `tier_counts` derives from a separate filesystem walk instead. Documented in "Notes for the implementer" §9 as the rule-of-three trigger.
- **Editing the Phase 0 `Probe` ABC or `ProbeContext` dataclass.** Frozen contract per ADR-0007.

## Notes for the implementer

1. **The 100 MB-body fixture is load-bearing.** Use `os.truncate` (sparse file) so disk write is O(1); the test still reads the offset/size from a real on-disk path. The 1 MB ceiling on `tracemalloc` peak is loose-but-load-bearing — it absorbs Pydantic-model allocations comfortably for ≤ 100 skills, and is still 100× tighter than what a `read_bytes()` regression would consume. Do not tighten to 20 KB; the original draft's 20 KB ceiling was brittle against Pydantic version drift, and the 1 MB margin keeps the test green across Pydantic 2.x point releases.
2. **`SkillsLoader` already paid the open cost.** S2-01's loader does `os.open(path, O_NOFOLLOW | O_NOCTTY)` → streaming-scan frontmatter → `safe_yaml.load` on a tempfile → `content_hash_fd(fd, offset=body_offset, size=body_size)` (which produces the `blake3:<64hex>` form). This probe re-uses those values verbatim. Do **not** re-open the file. Do **not** re-hash. Do **not** strip the `blake3:` prefix (the regex on `IndexedSkill.body_blake3` enforces the prefix).
3. **No body preview field, ever.** A "convenience" `body_preview: str` field on `IndexedSkill` would force the probe to read bytes, breaking AC-10 and AC-11. If the Planner needs a preview, it reads `body[:200]` itself at decision time (the operation is O(1) and per-decision, not per-gather).
4. **Newtypes preserved.** `SkillId`, `TaskClassId`, `Language` are the Phase-2 `NewType`s in `codegenie.types.identifiers`. Do not `cast(str, …)` to launder them away — that re-introduces the primitive-obsession ADR-0033 §1 explicitly forbids. The runtime cost of preserving a `NewType` is zero (identity-to-str).
5. **`tier_counts` is `dict[Literal[...], int]`, not `dict[str, int]`.** The three tiers are a closed set; a string-keyed dict invites primitive obsession ("org" vs. "Org" typos at consumer side). The `Literal` makes the consumer's `match` exhaustive.
6. **Confidence is three-state, not two.** `"high"` on a clean load (including the empty-install case), `"medium"` on partial success, `"low"` only on total failure or `FatalLoadError`. The original draft's "no medium" rule was based on the (incorrect) belief that the loader is all-or-error per call; it is in fact partial-success per file (the loader's `LoadOutcome.per_file_errors` exists precisely for this case).
7. **`tracemalloc` is the right instrument.** Phase 2 has no `memory_profiler` dep; `tracemalloc` is stdlib and deterministic.
8. **Sub-schema location.** S6-08 lands `src/codegenie/schema/probes/skills_index.schema.json` (FLAT layout — no `layer_d/` subdir; matches the existing `dep_graph.schema.json`, `index_health.schema.json`, etc. precedents). AC-19 references it via `importlib.resources` so the test fails loudly if S6-08 forgets to ship it (or ships it under the wrong name). Don't inline the schema into the probe file — Phase 2 keeps schemas as JSON resources.
9. **Rule-of-three threshold (design-pattern open question).** `SkillsLoader` does not currently expose tier membership per loaded `Skill`. This story derives `tier_counts` via a separate `Path.rglob("SKILL.md")` walk. When the *second* tier-aware Layer-D probe needs the same derivation (`ConventionsCatalogProbe` in S6-02 has tier-like layout but a different tier set; the *third* such consumer is the trigger), extract `_count_files_per_tier(search_paths, glob_pattern)` into a shared module. Until then, three similar lines (the per-tier `rglob` count) is better than premature abstraction (Rule 2). **Do not** extend `Skill` or `LoadOutcome` with a `tier` field as part of S6-01 — that is an S2-01 amendment and would be the wrong layer to fix it (the loader's discriminated-union on `tier` is internal to its `_load_all` method).
10. **`async def run` is the contract.** The Probe ABC is `async def run(self, repo, ctx)`; the test uses `asyncio.run(probe.run(repo, ctx))` (mirroring `tests/unit/probes/layer_b/test_dep_graph.py:108`). Do not introduce a sync wrapper — the original draft's `_run` private sync method does not exist in the Phase-0 contract and was a documentation bug.
11. **`ProbeContext` is a stdlib `@dataclass`.** Construct it with every required field set; there is no `ProbeContext.for_test` classmethod (the original draft assumed one). The test helper `_make_context(tmp_path)` exists in the test module only.
12. **Registry surface is `default_registry`.** Not `_PROBE_REGISTRY` (no such symbol). The entry is found via `next(e for e in default_registry._entries if e.cls.name == "skills_index")`; if a public `Registry` accessor lands later, swap to it then.
