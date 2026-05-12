# Story S2-01 — `SkillsLoader` package + `skill.schema.json` + no-home-expansion contract

**Step:** Step 2 — Plant skills loader, catalog expansion, schema-evolution policy, and conventions parity lint
**Status:** Ready
**Effort:** M
**Depends on:** S1-08 (`tools/digests.yaml` pin manifest — `required_tools` cross-checked against it); Phase 1 `parsers/safe_yaml.py` (assumed already on disk from Phase 1); Phase 1 `O_NOFOLLOW` precedent for symlink refusal
**ADRs honored:** ADR-0004 (`tools/digests.yaml` is the supply-chain pin manifest), Phase 1 ADR-0008 (in-process parse caps), Phase 1 ADR-0004 (`additionalProperties: false` at sub-schema root)

## Context

The Skills loader is the Phase-2 mechanism by which organizational uniqueness lands as **data, not prompts** — SKILL.md frontmatter declares what tasks/languages each skill applies to and which tools it needs; the `SkillsIndexProbe` in Step 7 will surface this to the Planner without ever inlining the body. This story plants the loader package, its public types, and the JSON Schema for the frontmatter. The single load-bearing invariant is **no `~/` expansion inside the loader**: the cache-key correctness contract requires the loader to accept absolute paths only — the CLI resolves `~` and env vars *before* calling. Violating this leaks `$HOME` into cache keys and silently diverges two machines.

The loader **never reads the body** — only frontmatter + `os.stat` for `body_char_count`. This is what keeps the Planner's token budget tractable (progressive disclosure: the Planner reads originals at decision time).

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Component design" #3` — public interface, internal structure, performance envelope, failure behavior.
- **Architecture:** `../phase-arch-design.md §"Data model"` — `Skill` and `SkillApplies` Pydantic shape with `schema_version: Literal["v1"]`.
- **Phase ADRs:** `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — ADR-0004 — `required_tools` is cross-referenced against `tools/digests.yaml`; unpinned ⇒ `applicability: "degraded"`.
- **Production ADRs:** `../../../production/design.md §2` — "organizational uniqueness as data, not prompts" — the architectural intent this loader expresses.
- **Source design:** `../final-design.md "Components" §5.1` — the Skills loader provenance (`[B + synth + S]`).
- **Existing code:** none — Phase 2 plants the package. Phase 1's `parsers/safe_yaml.py` is consumed unchanged.

## Goal

Land `src/codegenie/skills/{__init__.py, loader.py, models.py}` plus `src/codegenie/skills/schema/skill.schema.json` such that `discover_skills([abs_path_to_fixture_dir])` over a fixture directory of five SKILL.md files returns a `SkillIndex` with `len(skills) == 5`, validated frontmatter, populated `body_char_count`, and `applicability` set correctly per the `required_tools` cross-check — while a path containing a literal `~` does **not** silently expand.

## Acceptance criteria

- [ ] `src/codegenie/skills/loader.py` exposes `discover_skills(roots: Sequence[Path]) -> SkillIndex`; every root is asserted absolute (`Path.is_absolute()`) — any non-absolute root → `ValueError("discover_skills requires absolute paths; CLI must resolve ~ before calling")`.
- [ ] Frontmatter parsed via `codegenie.parsers.safe_yaml.load` (5 MB cap, depth 64); body **never read** — `body_char_count = stat().st_size - frontmatter_byte_size` (where `frontmatter_byte_size` is computed from the offset after the closing `---`).
- [ ] Frontmatter validated against `src/codegenie/skills/schema/skill.schema.json` (Draft 2020-12, `additionalProperties: false` at root, `schema_version` enum: `["v1"]` — single-element enum forward-compatible with future v2 expansion).
- [ ] `required_tools` cross-referenced against `tools/digests.yaml`: every entry present → `applicability: "available"`; one or more missing → `applicability: "degraded"` and a `skill.tool_unpinned` warning per offending tool.
- [ ] Symlinks under a root directory are **skipped** (not followed) with a `skill.symlink_skipped` warning recorded on the `SkillIndex`; the loader does not raise on symlinks.
- [ ] Malformed YAML or schema violation → `SkillLoadError` (typed exception, `src/codegenie/skills/errors.py`); the CLI wires this to `sys.exit(2)`.
- [ ] `SkillIndex.by_task_and_language: dict[tuple[str, str], list[str]]` is pre-indexed at load time (skill name list per (task_type, language)) and is idempotent across re-loads.
- [ ] TDD red landed first: `tests/unit/skills/test_loader.py`, `tests/unit/skills/test_no_home_expansion.py`, `tests/unit/skills/test_indexing.py` all initially fail.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/skills/` all pass.

## Implementation outline

1. Create `src/codegenie/skills/__init__.py` exporting `discover_skills`, `Skill`, `SkillApplies`, `SkillIndex`, `SkillLoadError`.
2. Create `src/codegenie/skills/errors.py` with `class SkillLoadError(CodegenieError)` — extend the Phase 0 error hierarchy (`codegenie.errors`).
3. Create `src/codegenie/skills/models.py` with the Pydantic shapes from `phase-arch-design.md §"Data model"` (`Skill`, `SkillApplies`, `SkillIndex`). Set `model_config = ConfigDict(extra="forbid")` on every model. `schema_version: Literal["v1"]` is the literal type.
4. Create `src/codegenie/skills/schema/skill.schema.json` — Draft 2020-12, `additionalProperties: false`, `required: ["schema_version", "name", "version", "applies_to", "required_tools"]`. `schema_version.enum: ["v1"]`. Reference `../../../docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md` in a root-level `$comment` (S2-07 lands the policy doc).
5. Create `src/codegenie/skills/loader.py`:
   - `def discover_skills(roots: Sequence[Path]) -> SkillIndex`. Walk each root with `os.walk(followlinks=False)`; for each `SKILL.md`, open with `O_NOFOLLOW` (Phase 1 precedent; `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)`); read just enough to extract the frontmatter window (between first and second `---` on a line); pass to `safe_yaml.load`; validate against schema; cross-reference `required_tools` against `tools/digests.yaml` (load once at startup, cache).
   - `frontmatter_byte_size`: byte offset of the line *after* the closing `---` in the file.
   - `body_char_count`: `stat().st_size - frontmatter_byte_size`.
   - Build `by_task_and_language` by iterating `applies_to.task_types × applies_to.languages`; deterministic-sort.
6. Wire `SkillIndex` immutability: return a `dataclass(frozen=True)` (or `model_config = ConfigDict(frozen=True)`). The Step-7 `SkillsIndexProbe` consumes this; immutability prevents accidental mutation between probes.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths:

- `tests/unit/skills/test_loader.py`
- `tests/unit/skills/test_no_home_expansion.py`
- `tests/unit/skills/test_indexing.py`

```python
# tests/unit/skills/test_loader.py
import pytest
from pathlib import Path

def test_discover_skills_happy_path(tmp_path: Path) -> None:
    # arrange: a fixture directory of 5 SKILL.md files
    # act: discover_skills([tmp_path])
    # assert: 5 skills, all "available", body_char_count > 0 for each
    ...

def test_unpinned_tool_marks_skill_degraded(tmp_path: Path, monkeypatch) -> None:
    # arrange: SKILL.md declaring required_tools: ["nonexistent-tool"]
    # assert: applicability == "degraded", warning "skill.tool_unpinned"
    ...

def test_symlink_skipped_with_warning(tmp_path: Path) -> None:
    # assert: loader does not raise, warning "skill.symlink_skipped" present
    ...

def test_malformed_yaml_raises_skill_load_error(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError):
        ...

# tests/unit/skills/test_no_home_expansion.py
def test_relative_path_rejected() -> None:
    with pytest.raises(ValueError, match="absolute paths"):
        discover_skills([Path("./skills")])

def test_path_with_tilde_not_expanded() -> None:
    # The literal "~/codegenie/skills" must not be silently expanded.
    # Either ValueError (preferred — non-absolute) or FileNotFoundError, never silent success.
    ...

# tests/unit/skills/test_indexing.py
from hypothesis import given, strategies as st

@given(...)  # Hypothesis: generate frontmatter dicts with varying task_types/languages
def test_by_task_and_language_is_idempotent(...):
    # property: discover_skills(roots) twice produces identical by_task_and_language
    ...
```

Run; confirm red on missing module / `KeyError` / wrong applicability; commit; then Green.

### Green — make it pass

Smallest impl: `discover_skills` walks roots, opens each SKILL.md with `O_NOFOLLOW`, extracts frontmatter window byte-for-byte, calls `safe_yaml.load`, validates via `jsonschema`, builds the index. No optimization beyond what the contract requires.

### Refactor — clean up

- Hoist the `tools/digests.yaml` load to a module-level lazy property; do not re-read it per skill.
- Pull the frontmatter-window byte-offset routine into a private `_extract_frontmatter_window(path: Path) -> tuple[bytes, int]` helper; covered by its own micro-test.
- `mypy --strict` clean; docstrings on every public symbol naming the load-bearing invariant (no-home-expansion) and pointing at this story.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/skills/__init__.py` | New package; export public surface. |
| `src/codegenie/skills/loader.py` | The `discover_skills` function; the no-home-expansion contract; `O_NOFOLLOW` open. |
| `src/codegenie/skills/models.py` | `Skill`, `SkillApplies`, `SkillIndex` Pydantic models. |
| `src/codegenie/skills/errors.py` | `SkillLoadError` typed exception. |
| `src/codegenie/skills/schema/skill.schema.json` | Frontmatter Draft 2020-12 schema; `additionalProperties: false`; `schema_version: ["v1"]`. |
| `tests/unit/skills/test_loader.py` | Happy path + degraded + symlink + malformed YAML. |
| `tests/unit/skills/test_no_home_expansion.py` | The cache-key correctness contract. |
| `tests/unit/skills/test_indexing.py` | Hypothesis idempotency property. |
| `tests/unit/skills/fixtures/skills_5/SKILL_*.md` (×5) | Fixture corpus. |

## Out of scope

- **`SkillsIndexProbe`** — handled by Step 7 (S7-08). This story plants the loader only; the probe is the consumer.
- **CLI flag wiring** (`--skills-root`, env var resolution) — the CLI's responsibility; the loader accepts absolute `Path` objects only.
- **`schema_version: "v1"` CI lint** — handled by S2-05.
- **`SCHEMA-EVOLUTION-POLICY.md`** — handled by S2-07.
- **Body-content indexing for retrieval** — Phase 4 (RAG over `ExternalDocsIndexProbe`). The body is never loaded in Phase 2.

## Notes for the implementer

- **No `Path.expanduser()` anywhere in `loader.py`.** Grep for `expanduser` in the diff; it must not appear. This is the load-bearing invariant; the test asserts both directions.
- **`O_NOFOLLOW` is per-open, not per-walk.** `os.walk(followlinks=False)` is the directory-traversal half; `os.open(..., O_NOFOLLOW)` is the file-open half. Both are required (a symlinked SKILL.md inside a normal directory would slip past `followlinks=False` alone).
- **Body byte vs char count.** The spec says `body_char_count`; UTF-8 means bytes and chars diverge on multibyte content. Phase 2 stipulates *bytes* (cheap; from `os.stat`), but the field name comes from `localv2.md`. Use `body_char_count: int` as a field name, populate with `stat().st_size - frontmatter_byte_size` (bytes), and add a `# byte count per spec note in localv2.md §5.5` comment so the next reader doesn't audit-trail the inconsistency.
- **`tools/digests.yaml` may be empty in Phase 2** (Step 1 plants it but Phase 2 doesn't pin every tool). `applicability: "degraded"` is therefore the *expected* state for several Phase-2 dev fixtures; the test fixture corpus must include both available and degraded skills.
- **Frontmatter delimiter is `---` on its own line.** Markdown headings start with `#`; do not confuse with H1. Use `re.match(rb"^---\s*$", line)`.
- **Errors at module import vs runtime.** Schema violation in a SKILL.md → `SkillLoadError` at `discover_skills` time (not at module import). Test must construct the loader, not import the module, to trigger the error.
