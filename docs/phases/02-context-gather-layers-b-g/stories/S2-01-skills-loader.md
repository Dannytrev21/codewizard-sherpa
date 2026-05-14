# Story S2-01 — `SkillsLoader` three-tier merge with `O_NOFOLLOW` + body byte-offset

**Step:** Step 2 — Plant kernel-side loaders (`SkillsLoader`, `ConventionsCatalogLoader`) and reference TCCM
**Status:** Ready
**Effort:** M
**Depends on:** S1-04 (`TCCM` model + loader establishes the `Result[T, E]` + `safe_yaml`-chokepoint + ADR-0033 newtype pattern this story repeats)
**ADRs honored:** 02-ADR-0007 (kernel-side scaffolding only — no plugin loader), Phase 1 ADR-0006 (`safe_yaml` chokepoint preserved), Phase 1 ADR-0008 (in-process parse caps + `O_NOFOLLOW`), production ADR-0033 §3–4 (make-illegal-states-unrepresentable; newtypes for `SkillId`)

## Context

`SkillsLoader` is the kernel-side loader for `SKILL.md` files — YAML-frontmatter + markdown-body documents that encode organizational uniqueness as data (Skills are Phase 4+'s structured input to the Planner; Phase 2 ships the loader so Phase 3's first plugin has a typed surface from day one — 02-ADR-0007 §"Decision"). Three load-bearing commitments make this story non-trivial: **(a)** three-tier merge across `~/.codegenie/skills/` (user) → `.codegenie/skills/` (repo-local) → optional `~/.codegenie/skills-org/` (org-shared) with **first-tier-wins** + a loud `skill_shadowed` warning on collision (`final-design.md §"Components" #9`, [S]'s open Q §6 resolved); **(b)** progressive disclosure — the markdown **body** is byte-offset-recorded but **never** read into memory (commitment §2.7, verified by `tracemalloc` peak < 20 KB on a 100 MB-body fixture; a future contributor adding `body: str` to `Skill` would silently break the commitment without that test, per `High-level-impl.md §"Risks specific to this step"`); **(c)** per-file `os.open(path, O_NOFOLLOW | O_NOCTTY)` defeats symlink escape, and YAML parsing routes through Phase 1's `codegenie.parsers.safe_yaml.load` chokepoint — there is **no parallel** `_safe_yaml_load_skill` helper (final-design §"Conflict-resolution" row 9; Rule 7 — don't fork conventions).

The three-tier order is a **security regression on inversion** (`High-level-impl.md §"Risks"`): user-tier first means an attacker who plants a hostile `~/.codegenie/skills-org/` cannot override a user-trusted skill. The order is pinned in `SkillsLoader.__init__` argument order **and** asserted in tests; future contributors get a failing test, not a silent flip.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #9` — interface, three-tier merge, `O_NOFOLLOW`, body byte-offset commitment, `safe_yaml.load` chokepoint reuse.
  - `../phase-arch-design.md §"Scenarios" → Scenario 3` — hostile YAML in `SKILL.md` (`!!python/object`) flow; `SkillsLoadError(reason="unsafe_yaml")` outcome.
  - `../phase-arch-design.md §"Edge cases"` rows 8, 9, 16 — hostile YAML; planted symlink; three-tier collision.
  - `../phase-arch-design.md §"Data model"` — `Skill` Pydantic model (`frozen=True, extra="forbid"`) with `id: SkillId`, `applies_to_tasks: list[str]`, `applies_to_languages: list[str]`, `body_offset: int`, `body_size: int`, `body_blake3: str`.
  - `../phase-arch-design.md §"Anti-patterns avoided"` — "Side effects in constructors. Every loader … is pure data at `__init__`; first I/O is `load_all()`."
- **Phase ADRs:**
  - `../ADRs/0007-no-plugin-loader-in-phase-2.md` — `SkillsLoader` is kernel-side; no `plugin.yaml`, no `plugins/` directory.
- **Production ADRs:**
  - `../../production/adrs/0033-domain-modeling-discipline.md` §3–4 — newtype `SkillId`; make-illegal-states-unrepresentable for `SkillsLoadError` reason union.
- **Source design:**
  - `../final-design.md §"Components" #9` — three-tier merge with first-tier-wins + loud `skill_shadowed` warning; `O_NOFOLLOW` discipline; `safe_yaml.load` reused.
  - `../final-design.md §"Conflict-resolution table"` row 9 — Phase 1 chokepoint reused, no parallel helper.
  - `../final-design.md §"Departures from all three inputs"` §8 — Rule 7 framing.
- **Existing code:**
  - `src/codegenie/parsers/safe_yaml.py` (Phase 1 S1-03) — `load(path, *, max_bytes, max_depth=64) -> Mapping[str, JSONValue]`. This is the **only** YAML loader call site; do not add a parallel one.
  - `src/codegenie/parsers/_io.py` (Phase 1 S1-03) — `open_capped(path, *, max_bytes, parser_kind)` already implements `O_NOFOLLOW`. SkillsLoader does **not** call this directly (it routes through `safe_yaml.load`); the `O_NOFOLLOW` discipline at the SkillsLoader call site is a defense-in-depth on the **frontmatter-extraction** open (pre-`safe_yaml.load`), since SkillsLoader must locate the `---` frontmatter terminator before delegating the YAML bytes.
  - `src/codegenie/result.py` (Phase 1, lifted in S1-04) — `Result[T, E]` sum type; `Result.Ok` / `Result.Err` constructors.
  - `src/codegenie/tccm/loader.py` (S1-04) — the established `Result`-returning, `safe_yaml`-routing loader shape this story mirrors.
- **External docs:**
  - `localv2.md` §5.4 (Layer D probes) — `skills_index` probe is the Phase 2 consumer (S6-01); the slice shape includes skill IDs only, never bodies.
  - PyYAML `CSafeLoader` semantics (S1-03 module docstring) — already pinned upstream.

## Goal

Ship `src/codegenie/skills/` (three files: `__init__.py`, `model.py`, `loader.py`) with:

```python
# model.py
class Skill(BaseModel):          # frozen=True, extra="forbid"
    id: SkillId
    applies_to_tasks: list[str]
    applies_to_languages: list[str]
    body_offset: int             # progressive disclosure: body NOT loaded
    body_size: int
    body_blake3: str

# loader.py
class SkillsLoader:
    def __init__(self, search_paths: list[Path]) -> None: ...   # pure data
    def load_all(self) -> Result[list[Skill], SkillsLoadError]: ...
    def find_applicable(self, evidence_keys: set[str]) -> list[Skill]: ...
```

With the following invariants:

1. **Constructor is pure data.** No `os.listdir`, no file reads, no path normalization beyond `Path(p)` coercion in `__init__`. First I/O is `load_all()`.
2. **Per-file open uses `os.open(path, O_RDONLY | O_NOFOLLOW | O_NOCTTY)`.** The fd is read to locate the second `---` frontmatter delimiter (size-capped at `max_bytes=1 MiB` total bytes scanned before locating the terminator; cap exceeded → `Result.Err(SkillsLoadError(reason="frontmatter_unterminated"))`). The frontmatter bytes are then passed to `codegenie.parsers.safe_yaml.load` via an in-memory file (the `safe_yaml.load` signature requires a `Path`; loader writes the frontmatter to a `tempfile.NamedTemporaryFile` opened `delete=False` inside a `with` block and passes that path — alternative implementations may extend `safe_yaml` with a `loads_bytes` shim in a follow-up, but Phase 2 ships the path-based form unchanged).
3. **Body is byte-offset-recorded only.** `body_offset` is the file offset (post-frontmatter `---` line) where the markdown body starts; `body_size = fstat.st_size - body_offset`. `body_blake3` is computed by **streaming** `os.read(fd, 64 * 1024)` chunks through `codegenie.hashing.content_hash` — never materializing the body as a single `bytes`/`str` value. `tracemalloc` peak attributable to the SkillsLoader call frame is < 20 KB on a 100 MB-body fixture.
4. **Three-tier merge: first-tier-wins.** Iteration order is `search_paths` argument order. Concrete `SkillsLoader` factory (in `__init__.py`) pins `[Path("~/.codegenie/skills/").expanduser(), Path(".codegenie/skills/"), Path("~/.codegenie/skills-org/").expanduser()]` — the **user** tier wins over **repo-local** wins over **org-shared** (defensive against a hostile org-shared tier). A collision (same `SkillId` in a later tier) emits a `skill_shadowed` structlog event with `{shadowed_path, winning_path, skill_id, winning_tier, shadowed_tier}` structured fields. Missing optional tier (e.g., no `~/.codegenie/skills-org/`) → skipped silently.
5. **`O_NOFOLLOW` ELOOP** → `Result.Err(SkillsLoadError(reason="symlink_refused", path=path))` for *that file*; other skills load. `safe_yaml.load` raising `MalformedYAMLError` (covers `!!python/object` ConstructorError per S1-03 AC-9) → `Result.Err(SkillsLoadError(reason="unsafe_yaml", path=path))` for that file; other skills load.
6. **`SkillsLoadError` is a Pydantic discriminated union**, not a `CodegenieError` marker subclass. Phase 1's markers-only invariant binds only `codegenie.errors.CodegenieError` subclasses; Phase 2's typed `Result.Err` values are Pydantic models with kind discriminators (`reason: Literal["symlink_refused", "unsafe_yaml", "frontmatter_unterminated", "schema"]`) + a `path: Path` field. This matches ADR-0033 §3 and the arch's `SkillsLoadError(reason=...)` shape (`§"Component design" #9`).
7. **`find_applicable(evidence_keys)` is monotone.** Adding a key never removes a match (Hypothesis property test). A skill matches iff every `applies_to_tasks` / `applies_to_languages` entry is satisfiable from `evidence_keys` (interpretation: `applies_to_*` lists are AND'd; superset of evidence is monotone).

## Acceptance criteria

- [ ] **AC-1 — module surface.** `src/codegenie/skills/__init__.py` exports `Skill`, `SkillsLoader`, `SkillsLoadError` only via `__all__`. `Skill` is `frozen=True, extra="forbid"`. `SkillsLoadError` is a Pydantic discriminated union over the four documented `reason` literals.
- [ ] **AC-2 — pure-data constructor.** `SkillsLoader(search_paths=[non_existent_path])` does **not** raise and does **not** call `os.listdir` / `os.open` / `os.stat`. Asserted by `monkeypatch.setattr(os, "listdir", raise_or_record)` + the constructor must not appear in the recorded calls.
- [ ] **AC-3 — happy path three-tier merge.** Given a fixture with `user/foo/SKILL.md`, `repo/bar/SKILL.md`, `org/baz/SKILL.md` (distinct IDs), `load_all()` returns `Result.Ok([foo, bar, baz])` in iteration order. Asserted by `test_load_all_three_tier_no_collisions`.
- [ ] **AC-4 — first-tier-wins on collision + `skill_shadowed` warning.** Given a fixture with `user/dup/SKILL.md` (id `dup`) and `org/dup/SKILL.md` (id `dup`), `load_all()` returns `Result.Ok([user_dup])` (one entry, the user-tier copy) **and** emits exactly one `skill_shadowed` structlog event with `winning_tier="user", shadowed_tier="org", skill_id="dup"`. Asserted via `structlog.testing.capture_logs`. Inversion (org-wins) is a test-asserted security regression.
- [ ] **AC-5 — `O_NOFOLLOW` symlink refusal yields typed `Result.Err`, other skills load.** Fixture: `user/good/SKILL.md` (legitimate) + `user/evil/SKILL.md` → symlinks to `/etc/passwd`. `load_all()` returns `Result.Ok([good])` and the in-Result-Ok slice of `SkillsLoadError`s contains exactly one `SkillsLoadError(reason="symlink_refused", path=Path("user/evil/SKILL.md"))`. The signature is `Result[LoadOutcome, FatalError]` where `LoadOutcome = list[Skill]` and per-file errors are surfaced via a structlog event AND a returned-list field — see Implementation outline step 6 for the typed shape.
- [ ] **AC-6 — `!!python/object` payload yields `unsafe_yaml` and executes no code.** Fixture: `user/evil/SKILL.md` whose frontmatter contains `!!python/object/apply:os.system ['echo pwned']`. After `load_all()`, the sentinel file is **not** written; the per-file error contains `reason="unsafe_yaml"`; other skills load. Inherits S1-03 AC-9 via `safe_yaml.load`.
- [ ] **AC-7 — progressive disclosure: 100 MB body, peak < 20 KB.** Fixture: `user/big/SKILL.md` with a 32-byte frontmatter and a 100 MB markdown body of random bytes. `tracemalloc.start()` before `load_all()`; `take_snapshot()` after. The peak delta attributable to the loader frame is < 20 KB. Pinned by `test_body_not_loaded_into_memory_under_100mb_fixture`. A future contributor who replaces the streaming hash with `body = f.read(); blake3(body)` makes this test fail.
- [ ] **AC-8 — `body_blake3` matches reference.** For a fixture with a 1 KiB body of known bytes, `body_blake3` equals `codegenie.hashing.content_hash(body_bytes).hex()[:32]` (or the project's documented BLAKE3-fingerprint width). The streaming hash and the one-shot hash agree.
- [ ] **AC-9 — `Skill` model is `frozen=True, extra="forbid"`.** Constructing `Skill(id=..., extra_field="x")` raises Pydantic `ValidationError`. Assigning `skill.id = "other"` raises `ValidationError` (frozen).
- [ ] **AC-10 — `SkillsLoadError` is a discriminated union, four reasons enumerated.** Test parametrizes over `{"symlink_refused", "unsafe_yaml", "frontmatter_unterminated", "schema"}` and asserts each constructs successfully via the discriminator + `path` field; a fifth reason raises `ValidationError`.
- [ ] **AC-11 — `find_applicable` monotonicity (Hypothesis property).** `tests/property/test_skills_loader_monotone.py` — for any two sets `A ⊆ B` of evidence keys, `set(loader.find_applicable(A).map(.id)) ⊆ set(loader.find_applicable(B).map(.id))`. Adding evidence never removes a match.
- [ ] **AC-12 — `safe_yaml.load` chokepoint (Rule 7).** `ripgrep "yaml\\." src/codegenie/skills/` returns zero hits; YAML access is exclusively via `codegenie.parsers.safe_yaml.load`. Asserted by `test_skills_loader_routes_yaml_through_safe_yaml_chokepoint` (uses `monkeypatch.setattr(safe_yaml, "load", spy)` + asserts the spy was called for every loaded skill).
- [ ] **AC-13 — `forbidden-patterns` continues to ban `model_construct`.** Pre-commit hook (Phase 0) scans `src/codegenie/skills/` and finds zero `model_construct` calls. Reinforces ADR-0033 § "no smuggling around validation".
- [ ] **AC-14 — toolchain.** `ruff check`, `ruff format --check`, `mypy --strict`, and `mypy --warn-unreachable` (per-module on `codegenie.skills/**`) are clean. `pytest tests/unit/skills/ tests/property/test_skills_loader_monotone.py` passes.
- [ ] **AC-15 — TDD discipline.** Red tests committed failing; green commit makes them pass; refactor commit is no-op behavior. Validator can reproduce.

## Implementation outline

1. **`src/codegenie/skills/model.py`** — define `SkillId` newtype (lifted from S1-03 if it already exists; otherwise lift here per the ADR-0033 newtype roster Step 1 plants), then the `Skill` Pydantic model (`frozen=True, extra="forbid"`) with the six fields. Use `Annotated[int, Field(ge=0)]` for `body_offset` and `body_size`. Pydantic discriminator validator on the (forthcoming) `SkillsLoadError` union.
2. **`src/codegenie/skills/loader.py`::`SkillsLoadError`** — Pydantic discriminated union over four reasons:
   ```python
   class SymlinkRefused(BaseModel):     # frozen=True, extra="forbid"
       reason: Literal["symlink_refused"] = "symlink_refused"
       path: Path
   class UnsafeYaml(BaseModel):
       reason: Literal["unsafe_yaml"] = "unsafe_yaml"
       path: Path
   class FrontmatterUnterminated(BaseModel):
       reason: Literal["frontmatter_unterminated"] = "frontmatter_unterminated"
       path: Path
   class SchemaViolation(BaseModel):
       reason: Literal["schema"] = "schema"
       path: Path
       details: list[dict]   # Pydantic ValidationError.errors() shape
   SkillsLoadError = Annotated[Union[SymlinkRefused, UnsafeYaml, FrontmatterUnterminated, SchemaViolation],
                               Field(discriminator="reason")]
   ```
3. **`SkillsLoader.__init__(self, search_paths: list[Path]) -> None`** — store `self._search_paths = list(search_paths)` only. **No** `os` calls. The default factory `SkillsLoader.default()` (classmethod) builds the pinned three-tier order (user, repo-local, org-shared), but production callers pass explicit paths in test environments; `default()` is a thin convenience.
4. **`SkillsLoader.load_all(self) -> Result[LoadOutcome, FatalError]`** where `LoadOutcome` is a Pydantic model with `skills: list[Skill]` and `per_file_errors: list[SkillsLoadError]`. `FatalError` is reserved for catastrophic conditions (e.g., none of the search paths are readable); a single bad file is **not** fatal (per arch §"Failure behavior" — "this skill skipped; loud CLI warning; other skills load"). Outline:
   ```
   skills_by_id: dict[SkillId, tuple[int, Skill]] = {}   # tier_index → Skill
   errors: list[SkillsLoadError] = []
   for tier_index, search_path in enumerate(self._search_paths):
       if not search_path.exists():
           continue            # missing optional tier silently skipped
       for skill_md in search_path.rglob("SKILL.md"):
           outcome = _load_one_skill(skill_md)
           match outcome:
               case Result.Ok(skill):
                   if skill.id in skills_by_id:
                       winning_tier, winning_skill = skills_by_id[skill.id]
                       log.warning("skill_shadowed",
                                   skill_id=skill.id,
                                   winning_tier=_TIER_NAME[winning_tier],
                                   shadowed_tier=_TIER_NAME[tier_index],
                                   winning_path=str(winning_skill_md_path_for(winning_skill)),
                                   shadowed_path=str(skill_md))
                       continue        # first-tier-wins
                   skills_by_id[skill.id] = (tier_index, skill)
               case Result.Err(err):
                   errors.append(err)
                   log.warning("skill_load_failed", **err.model_dump())
   return Result.Ok(LoadOutcome(skills=[s for _, s in skills_by_id.values()],
                                per_file_errors=errors))
   ```
5. **`_load_one_skill(path: Path) -> Result[Skill, SkillsLoadError]`** — the per-file routine:
   ```
   try:
       fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOCTTY)
   except OSError as exc:
       if exc.errno == errno.ELOOP:
           return Result.Err(SymlinkRefused(path=path))
       raise           # FileNotFoundError, PermissionError propagate; load_all skips by rglob's snapshot semantics
   try:
       frontmatter_bytes, body_offset = _read_frontmatter(fd, max_scan_bytes=1 << 20)
       if frontmatter_bytes is None:
           return Result.Err(FrontmatterUnterminated(path=path))
       body_blake3, body_size = _stream_hash_body(fd, body_offset)   # never materializes body
   finally:
       os.close(fd)
   # Parse frontmatter via the safe_yaml chokepoint (no parallel loader).
   with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".yaml") as tf:
       tf.write(frontmatter_bytes)
       tmp_path = Path(tf.name)
   try:
       try:
           data = safe_yaml.load(tmp_path, max_bytes=1 << 20)
       except MalformedYAMLError:
           return Result.Err(UnsafeYaml(path=path))   # !!python/object lands here
   finally:
       tmp_path.unlink(missing_ok=True)
   try:
       return Result.Ok(Skill(**data, body_offset=body_offset,
                              body_size=body_size, body_blake3=body_blake3))
   except ValidationError as exc:
       return Result.Err(SchemaViolation(path=path, details=exc.errors()))
   ```
6. **`_read_frontmatter(fd, *, max_scan_bytes)`** — read in 4 KiB chunks; locate the opening `---\n` (first non-empty line MUST be `---`); locate the closing `---\n`; return `(frontmatter_bytes, body_offset)` where `body_offset = bytes_consumed`. Cap at `max_scan_bytes` total scanned before terminator → `(None, _)`.
7. **`_stream_hash_body(fd, body_offset)`** — `os.lseek(fd, body_offset, os.SEEK_SET)`; loop `os.read(fd, 64 << 10)` into the running BLAKE3 hasher; count bytes; return `(hex_digest, total_bytes)`. **No** intermediate `bytes` accumulator. This is the path AC-7 protects.
8. **`SkillsLoader.find_applicable(self, evidence_keys: set[str]) -> list[Skill]`** — pure function over `self._skills` (cached from the last `load_all()`); a skill is applicable iff `set(skill.applies_to_tasks) <= evidence_keys` AND `set(skill.applies_to_languages) <= evidence_keys`. Monotone by set-containment transitivity. Returns the list in stable order (first-encountered).
9. **structlog event names** are literal strings for now (`"skill_shadowed"`, `"skill_load_failed"`); S1-10's `Final[str]` constant promotion convention applies to Phase 1's `probe.parser.cap_exceeded` only — Phase 2 follow-up can promote these later, but YAGNI in Step 2.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test files: `tests/unit/skills/test_loader.py` (15 named tests covering AC-1..AC-14) + `tests/property/test_skills_loader_monotone.py` (Hypothesis).

```python
# tests/unit/skills/test_loader.py — red test pinning the load-bearing AC-7
import os
import textwrap
import tracemalloc
from pathlib import Path

import pytest
import structlog.testing

from codegenie.skills import Skill, SkillsLoader
from codegenie.skills.loader import SymlinkRefused, UnsafeYaml


def _write_skill(p: Path, sid: str, body: bytes = b"# body\n") -> Path:
    p.mkdir(parents=True, exist_ok=True)
    skill_md = p / "SKILL.md"
    frontmatter = textwrap.dedent(f"""\
        ---
        id: {sid}
        applies_to_tasks: [vulnerability-remediation]
        applies_to_languages: [typescript]
        ---
        """).encode()
    skill_md.write_bytes(frontmatter + body)
    return skill_md


def test_constructor_is_pure_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2: __init__ must not perform I/O."""
    calls: list[str] = []
    monkeypatch.setattr(os, "listdir", lambda p: calls.append(("listdir", p)) or [])
    monkeypatch.setattr(os, "open", lambda *a, **kw: calls.append(("open", a)) or (_ for _ in ()).throw(OSError(2, "stub")))
    SkillsLoader(search_paths=[tmp_path / "does-not-exist"])  # must not raise, must not call os
    assert calls == [], f"constructor performed I/O: {calls}"


def test_first_tier_wins_emits_skill_shadowed(tmp_path: Path) -> None:
    """AC-4: user-tier wins over org-tier; collision logs skill_shadowed."""
    user = tmp_path / "user" / "dup"
    org  = tmp_path / "org"  / "dup"
    _write_skill(user, "dup", body=b"# user wins\n")
    _write_skill(org,  "dup", body=b"# org loses\n")

    loader = SkillsLoader(search_paths=[tmp_path / "user", tmp_path / "org"])
    with structlog.testing.capture_logs() as logs:
        result = loader.load_all()

    assert result.is_ok()
    assert [s.id for s in result.unwrap().skills] == ["dup"]
    shadow_events = [l for l in logs if l.get("event") == "skill_shadowed"]
    assert len(shadow_events) == 1
    ev = shadow_events[0]
    assert ev["skill_id"] == "dup"
    assert ev["winning_tier"] == "user"
    assert ev["shadowed_tier"] == "org"


def test_symlink_refused_does_not_dereference(tmp_path: Path) -> None:
    """AC-5: O_NOFOLLOW must refuse a planted symlink; other skills must load."""
    good = tmp_path / "user" / "good"
    _write_skill(good, "good")
    evil_dir = tmp_path / "user" / "evil"
    evil_dir.mkdir(parents=True)
    sentinel = tmp_path / "outside"
    sentinel.write_bytes(b"leaked\n")
    (evil_dir / "SKILL.md").symlink_to(sentinel)

    result = SkillsLoader(search_paths=[tmp_path / "user"]).load_all()
    assert result.is_ok()
    outcome = result.unwrap()
    assert [s.id for s in outcome.skills] == ["good"]
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, SymlinkRefused)
    assert err.path == evil_dir / "SKILL.md"


def test_unsafe_yaml_payload_executes_no_code(tmp_path: Path) -> None:
    """AC-6: !!python/object payload must yield reason='unsafe_yaml' and run nothing."""
    sentinel = tmp_path / "pwned"
    evil = tmp_path / "user" / "evil"
    evil.mkdir(parents=True)
    (evil / "SKILL.md").write_bytes(
        textwrap.dedent(f"""\
            ---
            !!python/object/apply:os.system ['touch {sentinel}']
            ---
            """).encode()
    )
    result = SkillsLoader(search_paths=[tmp_path / "user"]).load_all()
    assert result.is_ok()
    outcome = result.unwrap()
    assert not sentinel.exists(), "!!python/object MUST NOT execute"
    assert len(outcome.per_file_errors) == 1
    assert isinstance(outcome.per_file_errors[0], UnsafeYaml)


def test_body_not_loaded_into_memory_under_100mb_fixture(tmp_path: Path) -> None:
    """AC-7: progressive disclosure — peak loader allocation < 20 KB on a 100 MB body."""
    big = tmp_path / "user" / "big"
    big.mkdir(parents=True)
    skill_md = big / "SKILL.md"
    frontmatter = (b"---\nid: big\napplies_to_tasks: [t]\napplies_to_languages: [l]\n---\n")
    body_size = 100 * 1024 * 1024
    with skill_md.open("wb") as f:
        f.write(frontmatter)
        # 1 MB chunks of os.urandom → 100 MB body, deterministically seeded for cross-run stability.
        chunk = (b"\xab" * (1 << 20))
        for _ in range(100):
            f.write(chunk)

    loader = SkillsLoader(search_paths=[tmp_path / "user"])
    tracemalloc.start()
    result = loader.load_all()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert result.is_ok()
    assert result.unwrap().skills[0].body_size == body_size
    # 20 KB headroom for Pydantic / hash state / dict overhead; load-bearing budget.
    assert peak < 20 * 1024, f"progressive disclosure breached: peak={peak} bytes"
```

Property test:

```python
# tests/property/test_skills_loader_monotone.py — AC-11
from hypothesis import given, strategies as st
from codegenie.skills import SkillsLoader  # built from in-memory fixtures via a helper

@given(st.sets(st.text(min_size=1, max_size=8)),
       st.sets(st.text(min_size=1, max_size=8)))
def test_find_applicable_is_monotone_in_evidence_keys(a: set[str], b: set[str]) -> None:
    loader = _loader_with_skills_from(...)
    matches_a = {s.id for s in loader.find_applicable(a)}
    matches_ab = {s.id for s in loader.find_applicable(a | b)}
    assert matches_a <= matches_ab, "adding evidence removed a match"
```

Run; confirm every test fails because `src/codegenie/skills/` does not exist. Commit as red.

### Green — make it pass

Land the four edits in order:

1. `src/codegenie/skills/model.py` — `SkillId` newtype (or import from `codegenie.adapters.ids` if Step 1 already lifted it), `Skill` Pydantic model.
2. `src/codegenie/skills/loader.py` — `SkillsLoadError` discriminated union, `_read_frontmatter`, `_stream_hash_body`, `_load_one_skill`, `SkillsLoader` class.
3. `src/codegenie/skills/__init__.py` — `__all__ = ["Skill", "SkillsLoader", "SkillsLoadError"]`; re-export from `model` and `loader`.
4. `tests/unit/skills/` and `tests/property/` directory scaffolding (`__init__.py` files only; the tests above land here).

### Refactor — clean up

- Module docstring on `skills/loader.py` cites `phase-arch-design.md §"Component design" #9`, 02-ADR-0007, and the progressive-disclosure commitment §2.7.
- `_TIER_NAME = {0: "user", 1: "repo", 2: "org"}` is a module-level `Final[dict[int, str]]`; the structlog event uses these strings, not raw indices.
- The structlog event name literals (`"skill_shadowed"`, `"skill_load_failed"`) live near their emit sites; do not pre-emptively centralize.
- No `# type: ignore` comments in this module; add Pydantic stubs to `dev` extras only if `mypy --strict` flags a concrete line.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/skills/__init__.py` | New — public surface (`Skill`, `SkillsLoader`, `SkillsLoadError`) |
| `src/codegenie/skills/model.py` | New — `Skill` Pydantic model + `SkillId` newtype (or import) |
| `src/codegenie/skills/loader.py` | New — `SkillsLoader`, `_load_one_skill`, frontmatter scanner, streaming-hash, three-tier merge |
| `tests/unit/skills/__init__.py` | New — package marker |
| `tests/unit/skills/test_loader.py` | New — 15 named tests covering AC-1..AC-14 |
| `tests/property/__init__.py` | New (if absent) — package marker |
| `tests/property/test_skills_loader_monotone.py` | New — Hypothesis property test for AC-11 |

## Out of scope

- **Layer D `SkillsIndexProbe`** (`src/codegenie/probes/layer_d/skills_index.py`) — S6-01; consumes this loader but does not ship here.
- **Per-tier signing (Sigstore-style)** for `~/.codegenie/skills-org/` — Phase 14 multi-tenant concern; `ADRs/README.md "Decisions noted" #5` records the deferral; this story ships first-tier-wins + loud `skill_shadowed` only.
- **`ConventionsCatalogLoader`** — S2-02 (parallel-after-S1-04 with this story).
- **Reference TCCM roundtrip + Protocol-mock dispatcher** — S2-03 (depends on this story landing because S2-03's mock dispatcher closes Gap 1 by exercising every Protocol method, but its setup borrows the typed `Result`-returning loader shape).
- **Extending `safe_yaml` with a `loads_bytes(data, *, ...)` shim** — out of scope; this story uses the documented `safe_yaml.load(path, ...)` interface via a temp file. A follow-up may add `loads_bytes` if a second caller (e.g., `ConventionsCatalogLoader`'s inline-doc path) materializes; Rule of Three until then.
- **Hostile YAML adversarial corpus tests** — Phase 1 S5-01 already pins `safe_yaml`'s `!!python/object` + alias-amplification defenses; this story exercises the SkillsLoader-side outcome only.
- **Skills body content rendering / Markdown parsing** — never in scope; Phase 2 records `(body_offset, body_size, body_blake3)` only. The Planner (Phase 4+) reads bodies lazily through a different code path.

## Notes for the implementer

- **Three-tier order is load-bearing.** The arg order `[user, repo, org]` is the security commitment. If `__init__` ever flips the order silently, the `test_first_tier_wins_emits_skill_shadowed` test fails — that's intentional. Do not "fix" the test; fix the order.
- **`O_NOFOLLOW | O_NOCTTY` is the literal flag set.** Adding `O_CLOEXEC` is fine (defensive); omitting `O_NOFOLLOW` is a security regression. The `O_NOCTTY` is paranoia for terminal-device paths and matches Phase 1's `parsers/_io.py` convention.
- **Streaming-hash discipline.** AC-7 is enforced by a `tracemalloc` budget — if you replace the chunked `os.read` loop with `body = f.read()` the test fails on a 100 MB fixture. Do not "optimize" by reading the whole body even for small files; the implementation must be uniformly streaming.
- **`safe_yaml.load` chokepoint is non-negotiable.** Phase 1 ratified one YAML loader (S1-03); do not import `yaml` directly anywhere in `src/codegenie/skills/`. AC-12 ripgreps for `yaml\.` and asserts zero hits. If you need a YAML capability `safe_yaml` doesn't expose, file an issue extending `safe_yaml` — don't fork it.
- **`SkillsLoadError` is Pydantic, not a `CodegenieError` subclass.** Phase 1's markers-only invariant (`tests/unit/test_errors.py::test_subclasses_are_markers_only`) binds only `codegenie.errors.CodegenieError` subclasses; Phase 2's `Result.Err` values are typed Pydantic models with reason discriminators. Do not subclass `CodegenieError`; do not try to fit `SkillsLoadError` into the markers-only contract — that is a different contract for a different purpose.
- **Per-file errors are NOT fatal.** A symlink, an unsafe-YAML payload, or a schema violation on ONE skill must NOT cause `load_all()` to return `Result.Err`. The signature returns `Result.Ok(LoadOutcome(...))` with a per-file-error list; the only `Result.Err` path is catastrophic (e.g., all search paths unreadable). Arch §"Failure behavior" is explicit: "this skill skipped; loud CLI warning; other skills load."
- **Tempfile dance for `safe_yaml.load`.** `safe_yaml.load` takes a `Path`. The frontmatter-bytes-to-temp-file step is ugly but preserves the Phase 1 chokepoint without a `loads_bytes` shim. The `tempfile.NamedTemporaryFile(delete=False)` + `finally: tmp_path.unlink(missing_ok=True)` shape leaks no fd; use `delete=False` because Windows would otherwise lock the file (we run on macOS / Linux but the discipline is portable). If a `loads_bytes` shim lands later, replace this dance — one place to update.
- **`find_applicable` must remain a pure function over the cached `_skills` list.** Do not re-load on every call; the loader's state is the cached list from the last `load_all()`. If `load_all()` was never called, `find_applicable` returns `[]` (do not auto-call `load_all()` — explicit > implicit, per Rule 3).
