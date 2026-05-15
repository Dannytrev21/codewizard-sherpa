# Story S2-01 — `SkillsLoader` three-tier merge with `O_NOFOLLOW` + body byte-offset

**Step:** Step 2 — Plant kernel-side loaders (`SkillsLoader`, `ConventionsCatalogLoader`) and reference TCCM
**Status:** Ready
**Effort:** M
**Depends on:** S1-04 (`TCCM` model + loader establishes the `Result[T, E]` + `safe_yaml`-chokepoint + ADR-0033 newtype pattern this story repeats)
**ADRs honored:** 02-ADR-0007 (kernel-side scaffolding only — no plugin loader), Phase 1 ADR-0006 (`safe_yaml` chokepoint preserved), Phase 1 ADR-0008 (in-process parse caps + `O_NOFOLLOW`), Phase 0 ADR-0001 (hashing chokepoint — extension required, see Validation notes), production ADR-0033 §1, §3–4 (newtypes for every domain primitive; make-illegal-states-unrepresentable)

## Validation notes (added 2026-05-15 by phase-story-validator)

This story was hardened against four critic lenses (coverage, test-quality, consistency, design-patterns). **Verdict: HARDENED.** The core shape (three-tier merge, progressive disclosure, `safe_yaml` chokepoint, Pydantic discriminated `SkillsLoadError`) is correct and traces cleanly to arch §"Component design" #9, 02-ADR-0007 §Decision, and production ADR-0033. Block-tier and harden-tier closures applied in place:

- **B1 — Hashing chokepoint extension (block).** Original story prescribed "streaming `os.read(fd, 64 * 1024)` chunks through `codegenie.hashing.content_hash`", but `content_hash(path: Path) -> str` does not accept fd or chunks, and `src/codegenie/hashing.py`'s module docstring forbids any direct `blake3` / `hashlib.sha256` import outside that file (Phase 0 ADR-0001). The story now commits to extending `codegenie.hashing` with `content_hash_fd(fd, *, offset, size) -> str` as a sibling chokepoint (Open/Closed at the file boundary — one new function, no edits to existing call sites). AC-25 enforces the chokepoint discipline.
- **B2 — `body_blake3` format pinned (block).** AC-8 originally allowed "`[:32]` (or project's documented BLAKE3-fingerprint width)" — ambiguous. The hashing module's contract returns `f"blake3:{64-hex}"` (tagged). `body_blake3` is now pinned to the same tagged shape (AC-8 regex `^blake3:[0-9a-f]{64}$`).
- **B3 — `unsafe_yaml` umbrella documented (block).** `safe_yaml.load` translates every `yaml.YAMLError` subclass (including `ConstructorError` for `!!python/object`, plus pure-syntax `ParserError`) to a single `MalformedYAMLError`. The story's `reason="unsafe_yaml"` was inheriting that umbrella implicitly; an operator reading the log would think every `unsafe_yaml` event was a supply-chain attack when it might be a syntax typo. Notes for implementer + AC-6b document this honestly: the reason name is the operationally-prudent umbrella ("treat as hostile until investigated"); the AC suite proves both the `!!python/object` case AND a pure-syntax-error case land in the same bucket, and that *no code executes* for either. Arch §"Edge cases" row 8 retained as authoritative.
- **H1 — Mutation-table closures (harden).** The TDD plan now catches: same-tier collision (AC-16), exact `body_offset` / `body_size` for a hand-constructed fixture (AC-17, off-by-one catcher), exact `os.open` flag set (AC-18, `O_NOFOLLOW` drop catcher), within-tier deterministic ordering (AC-19, cross-OS), TOCTOU file-disappearance during `rglob`→`os.open` window (AC-20), `find_applicable` correctness (AC-21 — pure-monotonicity tolerates the `return []` mutation), `["*"]` wildcard semantics for `applies_to_*` (AC-22, per CLAUDE.md "`['*']` meaning 'all'"), defensive-copy of `find_applicable` return (AC-23), AST source-scan replacing ripgrep AC-12 (AC-24, per S1-04 AC-23 precedent), tempfile cleanup (AC-26).
- **H2 — Primitive obsession on domain fields (harden, ADR-0033 §1).** `applies_to_tasks` and `applies_to_languages` retyped from `list[str]` to `list[TaskClassId]` and `list[Language]` (newtypes already exist in `codegenie.types.identifiers`). `evidence_keys` argument to `find_applicable` retyped from `set[str]` to a typed `EvidenceQuery(task: TaskClassId | None, languages: set[Language])` — `set[str]` was a degenerate flat bag that conflated task and language semantics. AC-21 / AC-22 are written against the typed surface.
- **H3 — `_TIER_NAME` is anti-pattern-adjacent (harden, ADR-0033 §3).** Replaced `dict[int, str]` with `Tier: TypeAlias = Literal["user", "repo", "org"]` + a frozen `_TIERS: Final[tuple[Tier, ...]] = ("user", "repo", "org")` ordering constant. Tier identity is now a typed claim, not an `int`-keyed lookup the type checker can't see. Same observable behavior; same security commitment; ergonomically and structurally typed.
- **H4 — Functional-core / imperative-shell split (harden, Notes-only).** `_load_one_skill` does seven concerns (open, scan, tempfile, parse, hash, validate, classify). Recommended split: pure `_split_frontmatter(data: bytes) -> Result[FrontmatterSplit, FrontmatterUnterminated]` + pure `_build_skill(parsed_frontmatter, body_offset, body_size, body_blake3) -> Result[Skill, SchemaViolation]` + impure `_open_skill_path`, `_read_with_streaming_hash`, `_load_one_skill` composer. **Not promoted to an AC** (Rule 3 / surgical changes — the AC suite already constrains observable behavior); recorded in Notes-for-implementer so a contributor reaching for the obvious-but-monolithic shape sees the alternative.
- **H5 — Consistency w/ sibling `TCCMLoader` (harden, Notes-only).** TCCMLoader (S1-04) uses a marker `CodegenieError` subclass with prefixed `args[0]` strings (`"parse: …"`, `"schema: …"`). This story diverges deliberately to a Pydantic discriminated union because (a) partial-success multi-file semantics require a typed per-file error list, not a thrown exception, and (b) Phase 1's markers-only invariant binds only `codegenie.errors.CodegenieError` subclasses, not `Result.Err` payloads. The convention going forward: single-file loaders use markers + string prefix (S1-04); multi-file partial-success loaders use Pydantic discriminated unions (this story + S2-02). Documented in Notes-for-implementer.
- **NEEDS RESEARCH:** none. All findings closeable from arch + ADRs + verified repo state (Stage 3 skipped).

A full audit log is at [`_validation/S2-01-skills-loader.md`](_validation/S2-01-skills-loader.md).

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
Tier: TypeAlias = Literal["user", "repo", "org"]

class Skill(BaseModel):          # frozen=True, extra="forbid"
    id: SkillId
    applies_to_tasks: list[TaskClassId]       # ADR-0033 §1 — newtype list, not list[str]
    applies_to_languages: list[Language]      # ADR-0033 §1 — newtype list, not list[str]
    body_offset: Annotated[int, Field(ge=0)]  # progressive disclosure: body NOT loaded
    body_size: Annotated[int, Field(ge=0)]
    body_blake3: str                          # pinned format: r"^blake3:[0-9a-f]{64}$"

class EvidenceQuery(BaseModel):  # frozen=True, extra="forbid"
    task: TaskClassId | None     # None = no task constraint in this query
    languages: set[Language]

# loader.py
class SkillsLoader:
    def __init__(self, search_paths: list[Path]) -> None: ...   # pure data; no I/O
    def load_all(self) -> Result[LoadOutcome, FatalLoadError]: ...
    def find_applicable(self, evidence: EvidenceQuery) -> list[Skill]: ...
```

With the following invariants:

1. **Constructor is pure data.** No `os.listdir`, no file reads, no path normalization beyond `Path(p)` coercion in `__init__`. First I/O is `load_all()`.
2. **Per-file open uses `os.open(path, O_RDONLY | O_NOFOLLOW | O_NOCTTY)`.** The fd is read to locate the second `---` frontmatter delimiter (size-capped at `max_bytes=1 MiB` total bytes scanned before locating the terminator; cap exceeded → `Result.Err(SkillsLoadError(reason="frontmatter_unterminated"))`). The frontmatter bytes are then passed to `codegenie.parsers.safe_yaml.load` via an in-memory file (the `safe_yaml.load` signature requires a `Path`; loader writes the frontmatter to a `tempfile.NamedTemporaryFile` opened `delete=False` inside a `with` block and passes that path — alternative implementations may extend `safe_yaml` with a `loads_bytes` shim in a follow-up, but Phase 2 ships the path-based form unchanged).
3. **Body is byte-offset-recorded only.** `body_offset` is the file offset (post-frontmatter `---\n` line) where the markdown body starts; `body_size = fstat.st_size - body_offset`. `body_blake3` is computed by **streaming** 64 KiB chunks through a new public API on the hashing chokepoint — `codegenie.hashing.content_hash_fd(fd, *, offset: int, size: int) -> str` (extension by addition, Open/Closed at the chokepoint; ADR-0001 preserved). The implementation reads in 64 KiB chunks and never materializes the body as a single `bytes`/`str` value. Return value format is `r"^blake3:[0-9a-f]{64}$"` (identical to `content_hash(path)`). `tracemalloc` peak attributable to the SkillsLoader call frame is < 20 KB on a 100 MB-body fixture. **No direct `blake3` import outside `src/codegenie/hashing.py`** — AC-25 enforces this via AST source scan.
4. **Three-tier merge: first-tier-wins.** Iteration order is `search_paths` argument order. Concrete `SkillsLoader.default()` classmethod factory pins `[Path("~/.codegenie/skills/").expanduser(), Path(".codegenie/skills/"), Path("~/.codegenie/skills-org/").expanduser()]` — the **user** tier wins over **repo-local** wins over **org-shared** (defensive against a hostile org-shared tier). Tier identity is `Tier: TypeAlias = Literal["user", "repo", "org"]` with a frozen `_TIERS: Final[tuple[Tier, ...]] = ("user", "repo", "org")` ordering constant — *not* a `dict[int, str]` (ADR-0033 §3, typed-claim-not-int-keyed-lookup). A cross-tier collision (same `SkillId` resolved earlier, seen again later) emits exactly one `skill_shadowed` structlog event per collision with `{skill_id, winning_tier, shadowed_tier, winning_path, shadowed_path}` structured fields and the later occurrence is discarded. A **same-tier** collision (two `SKILL.md` with the same `id` under the *same* tier root) is operationally indistinguishable from a cross-tier one — same `skill_shadowed` event with `winning_tier == shadowed_tier` and the lexicographically-first path winning (so collision behavior is deterministic; AC-16). Missing optional tier (e.g., no `~/.codegenie/skills-org/`) → skipped silently (AC-3a). Within a single tier, results are emitted in lexicographic order of `path.relative_to(tier_root)` so the load order is deterministic across filesystems (xfs/ext4/APFS `rglob` order is *not* guaranteed; AC-19).
5. **`O_NOFOLLOW` ELOOP** → `Result.Err(SymlinkRefused(path=path))` for *that file*; other skills load. `safe_yaml.load` raising `MalformedYAMLError` (covers `!!python/object` ConstructorError per S1-03 AC-9 **AND** any other `yaml.YAMLError` subclass — `ParserError`, `ScannerError`, top-level non-mapping) → `Result.Err(UnsafeYaml(path=path))` for that file; other skills load. The reason name `unsafe_yaml` is deliberately the operationally-prudent umbrella ("treat as hostile until investigated"); the AC suite proves both the `!!python/object` case AND a pure-syntax-error case land in the same bucket and that *no code executes for either* (AC-6, AC-6b). Any other `OSError` raised during open/read (e.g., `FileNotFoundError` from a TOCTOU race between `rglob` yielding a path and `os.open` seeing it deleted; `PermissionError`; `IsADirectoryError`) → `Result.Err(IoFailure(path=path, errno_name=errno.errorcode[exc.errno]))` for that file; other skills load (AC-20). The only `Result.Err(FatalLoadError(...))` path on `load_all()` is catastrophic — e.g., the search path itself fails `os.access` in a way that says "no tier is readable"; per-file failures are non-fatal.
6. **`SkillsLoadError` is a Pydantic discriminated union**, not a `CodegenieError` marker subclass. Phase 1's markers-only invariant binds only `codegenie.errors.CodegenieError` subclasses; Phase 2's typed `Result.Err` values are Pydantic models with kind discriminators (`reason: Literal["symlink_refused", "unsafe_yaml", "frontmatter_unterminated", "schema", "io_failure"]`) + a `path: Path` field. This matches ADR-0033 §3 and the arch's `SkillsLoadError(reason=...)` shape (`§"Component design" #9`). **Convention note** (carried in `Notes for the implementer`): single-file loaders (`TCCMLoader`, S1-04) use `CodegenieError` marker subclasses with string-prefixed `args[0]`; multi-file *partial-success* loaders (this story, S2-02) use Pydantic discriminated unions because per-file errors must round-trip as values inside a `LoadOutcome` list.
7. **`find_applicable(evidence)` is correct AND monotone.** The matching rule, with `["*"]` wildcard per CLAUDE.md:
   - Tasks-component matches iff `"*"` (cast to `TaskClassId`) is in `skill.applies_to_tasks` OR `evidence.task is not None and evidence.task in skill.applies_to_tasks`.
   - Languages-component matches iff `"*"` (cast to `Language`) is in `skill.applies_to_languages` OR `set(skill.applies_to_languages) & evidence.languages != ∅`.
   - A skill is *applicable* iff both components match (AND).

   Two test obligations: **correctness** (AC-21 — a hand-constructed fixture with predictable membership: a `vulnerability-remediation` / `typescript` skill matches an `EvidenceQuery(task="vulnerability-remediation", languages={"typescript"})` but not `EvidenceQuery(task="distroless-migration", languages={"typescript"})`; a wildcard skill matches both) and **monotonicity** (AC-11 — adding a language to `evidence.languages` never removes a match; setting `evidence.task` from `None` to a value never *adds* a match unless the skill was wildcard-or-matching anyway). Pure monotonicity is insufficient on its own — a `return []` implementation is vacuously monotone — which is why AC-21 carries the correctness obligation. The function returns a **fresh `list`** per call (defensive copy; never the cached internal `_skills` reference; AC-23) so a caller mutating the returned list cannot corrupt loader state.

## Acceptance criteria

- [ ] **AC-1 — module surface.** `src/codegenie/skills/__init__.py` exports `Skill`, `SkillsLoader`, `SkillsLoadError`, `LoadOutcome`, `FatalLoadError`, `EvidenceQuery`, `Tier` only via `__all__` (exact-set test). `Skill` is `frozen=True, extra="forbid"`. `SkillsLoadError` is a `Annotated[Union[...], Field(discriminator="reason")]` discriminated union over five `reason` literals (`symlink_refused`, `unsafe_yaml`, `frontmatter_unterminated`, `schema`, `io_failure`). `Tier = Literal["user", "repo", "org"]`.
- [ ] **AC-2 — pure-data constructor (no I/O).** `SkillsLoader(search_paths=[non_existent_path])` does **not** raise and does **not** call any I/O primitive. Asserted by `monkeypatch.setattr` on all of `os.listdir`, `os.scandir`, `os.open`, `os.stat`, `pathlib.Path.exists`, `pathlib.Path.is_dir`, each replaced by a `lambda *a, **kw: pytest.fail("constructor performed I/O")`. (Strengthens against `Path.iterdir` / `Path.glob` smuggling.)
- [ ] **AC-3 — happy path three-tier merge.** Given a fixture with `user/foo/SKILL.md`, `repo/bar/SKILL.md`, `org/baz/SKILL.md` (distinct IDs), `load_all()` returns `Result.Ok(LoadOutcome(skills=[foo, bar, baz], per_file_errors=[]))` in iteration order. Each loaded `Skill` is fully populated — `id`, `applies_to_tasks`, `applies_to_languages`, `body_offset`, `body_size`, `body_blake3` — every field asserted, not just `id`.
- [ ] **AC-3a — missing optional tier silently skipped.** With `search_paths=[user_dir, repo_dir, /nonexistent/org]`, `load_all()` succeeds with `LoadOutcome.skills` containing only the user+repo skills and `per_file_errors == []`. The missing-tier branch emits no log event (silent skip per arch §"Failure behavior").
- [ ] **AC-4 — first-tier-wins on cross-tier collision + `skill_shadowed` warning.** Given a fixture with `user/dup/SKILL.md` (id `dup`) and `org/dup/SKILL.md` (id `dup`), `load_all()` returns `LoadOutcome.skills == [user_dup]` (one entry, the user-tier copy) **and** emits exactly one `skill_shadowed` structlog event with structured fields `{event: "skill_shadowed", skill_id: "dup", winning_tier: "user", shadowed_tier: "org", winning_path: <user path>, shadowed_path: <org path>}`. Asserted via `structlog.testing.capture_logs`. Inversion (org-wins) is a test-asserted security regression.
- [ ] **AC-4a — middle-tier wins when first tier absent.** Fixture: no user `dup`, but `repo/dup` and `org/dup` both present. Repo wins; `skill_shadowed` event has `winning_tier="repo"`, `shadowed_tier="org"`. (Catches an off-by-one `_TIERS` indexing mutation that AC-4 alone misses.)
- [ ] **AC-5 — `O_NOFOLLOW` symlink refusal yields typed per-file error, other skills load.** Fixture: `user/good/SKILL.md` (legitimate) + `user/evil/SKILL.md` → symlink to `tmp_path/outside`. `load_all()` returns `Result.Ok(LoadOutcome(skills=[good], per_file_errors=[err]))` where `isinstance(err, SymlinkRefused)` and `err.path == user/evil/SKILL.md`. The sentinel target is **not** read (no `b"leaked\n"` bytes appear in the in-memory `Skill` body fields or any log event).
- [ ] **AC-6 — `!!python/object` payload yields `unsafe_yaml` and executes no code.** Fixture: `user/evil/SKILL.md` whose frontmatter contains `!!python/object/apply:os.system ['touch {sentinel}']`. After `load_all()`: `not sentinel.exists()`; the per-file error is `UnsafeYaml(path=user/evil/SKILL.md)`; other skills load. Inherits S1-03 AC-9 via `safe_yaml.load` → `MalformedYAMLError`.
- [ ] **AC-6b — pure-syntax-error YAML also lands as `unsafe_yaml` (umbrella honesty).** Fixture: `user/typo/SKILL.md` whose frontmatter is `id: ok\napplies_to_tasks: [unterminated` (legal trigger of `yaml.ScannerError`, not a constructor exploit). The per-file error is `UnsafeYaml(path=...)` — same bucket as AC-6. Documented in Notes-for-implementer: the reason name is the operationally-prudent umbrella ("treat as hostile until investigated"); operators read `unsafe_yaml` and inspect; no code path discriminates parse-failure-flavor.
- [ ] **AC-6c — frontmatter unterminated → typed `FrontmatterUnterminated`, no OOM.** Fixture: `user/eternal/SKILL.md` is exactly `b"---\n" + b"x: y\n" * (1 << 20)` — opens correctly with `---` but the second `---` never appears within the 1 MiB scan cap. `load_all()` returns `per_file_errors=[FrontmatterUnterminated(path=...)]`; the 1 MiB-scan-cap bound is asserted by `tracemalloc` peak < 2 MiB.
- [ ] **AC-6d — `SchemaViolation` on invalid frontmatter.** Fixture: `user/bad-schema/SKILL.md` whose frontmatter is `id: ok\napplies_to_tasks: "not-a-list"\napplies_to_languages: [ts]\n`. Per-file error is `SchemaViolation(path=..., details=[{...Pydantic ValidationError shape...}])`; `details` is a `list[dict]`, non-empty, includes a row with `loc=("applies_to_tasks",)`.
- [ ] **AC-7 — progressive disclosure: 100 MB body, peak < 20 KB.** Fixture: `user/big/SKILL.md` with a 32-byte frontmatter and a 100 MB markdown body of fixed bytes (`b"\xab" * (1 << 20)` repeated 100×, deterministic). `tracemalloc.start()` before `load_all()`; `take_snapshot()` after. The peak delta attributable to the loader frame is < 20 KB. Pinned by `test_body_not_loaded_into_memory_under_100mb_fixture`. A future contributor who replaces the streaming hash with `body = f.read(); content_hash_bytes(body)` makes this test fail.
- [ ] **AC-7a — exact `body_offset` / `body_size` for a hand-constructed fixture (off-by-one catcher).** Fixture: frontmatter is exactly `b"---\nid: x\napplies_to_tasks: [\"*\"]\napplies_to_languages: [\"*\"]\n---\n"` (length 73 bytes, asserted constant), body is `b"hello world\n"` (12 bytes). `load_all()` returns a `Skill` with `body_offset == 73` and `body_size == 12`. An implementation that includes the closing `---\n` in the body (sets `body_offset = 69`) or excludes one extra leading byte fails this test.
- [ ] **AC-8 — `body_blake3` matches reference AND format pinned.** For the AC-7a fixture, `body_blake3 == codegenie.hashing.content_hash_bytes(b"hello world\n")` (which is `f"blake3:{hexdigest}"`). The streaming hash and the one-shot hash agree byte-for-byte. The string matches `re.fullmatch(r"blake3:[0-9a-f]{64}", body_blake3)`. An implementation that drops the `blake3:` prefix, truncates to 32 hex, or silently switches to SHA-256 fails the regex.
- [ ] **AC-9 — `Skill` model is `frozen=True, extra="forbid"`.** Constructing `Skill(id=SkillId("x"), applies_to_tasks=[], applies_to_languages=[], body_offset=0, body_size=0, body_blake3="blake3:" + "0"*64, extra_field="x")` raises Pydantic `ValidationError`. Assigning `skill.id = SkillId("other")` on a constructed instance raises `ValidationError` (frozen).
- [ ] **AC-10 — `SkillsLoadError` is a discriminated union, five reasons enumerated.** Test parametrizes over `{"symlink_refused", "unsafe_yaml", "frontmatter_unterminated", "schema", "io_failure"}` and asserts each constructs successfully via the discriminator + `path` field; a sixth reason (`reason="bogus"`) raises `ValidationError`. JSON-shape pin: `SymlinkRefused(path=Path("/x")).model_dump() == {"reason": "symlink_refused", "path": "/x"}` for stability across Pydantic minor versions (cross-version mutation catcher; per S1-04 precedent).
- [ ] **AC-11 — `find_applicable` monotonicity (Hypothesis property).** `tests/property/test_skills_loader_monotone.py` — for any two `EvidenceQuery` values where `q1.languages ⊆ q2.languages` and `(q1.task is None) or (q1.task == q2.task)`, `set(s.id for s in loader.find_applicable(q1)) ⊆ set(s.id for s in loader.find_applicable(q2))`. (Strict subset on languages; task None→Some is also monotone-increasing.) Adding evidence never removes a match.
- [ ] **AC-11a — `find_applicable` correctness (paired positive test, not just monotonicity).** Pure monotonicity tolerates `return []`. With a fixture containing:
  - `vuln-ts` (`applies_to_tasks=[vulnerability-remediation]`, `applies_to_languages=[typescript]`),
  - `vuln-any` (`applies_to_tasks=[vulnerability-remediation]`, `applies_to_languages=["*"]`),
  - `any-ts` (`applies_to_tasks=["*"]`, `applies_to_languages=[typescript]`),
  - `noop` (`applies_to_tasks=[distroless]`, `applies_to_languages=[go]`):

  `find_applicable(EvidenceQuery(task="vulnerability-remediation", languages={"typescript"}))` returns exactly `{vuln-ts, vuln-any, any-ts}` (order: cached `_skills` first-encountered); `noop` is *not* present. Each membership assertion is individual (the union of "what's in" and "what's out" is the mutation-resistant shape).
- [ ] **AC-11b — `find_applicable([])` returns `[]` before `load_all()`.** Constructing the loader and calling `find_applicable(EvidenceQuery(task=None, languages=set()))` without first calling `load_all()` returns `[]` and does **not** implicitly trigger I/O (verified by the same monkeypatch set as AC-2). Notes: explicit > implicit.
- [ ] **AC-12 — `safe_yaml.load` chokepoint asserted by runtime spy.** Monkeypatch `codegenie.parsers.safe_yaml.load` with a wrapping spy; `load_all()` over a 3-skill fixture invokes the spy 3 times with `max_bytes >= 1 << 20`. No direct `yaml.load` / `yaml.CSafeLoader` / `yaml.safe_load` call can produce skill values (verified by replacing the spy with a `pytest.fail` and confirming no skills are loaded).
- [ ] **AC-13 — `forbidden-patterns` continues to ban `model_construct`.** Pre-commit hook (Phase 0) scans `src/codegenie/skills/` and finds zero `model_construct` calls. Reinforces ADR-0033 § "no smuggling around validation".
- [ ] **AC-14 — toolchain.** `ruff check`, `ruff format --check`, `mypy --strict`, and `mypy --warn-unreachable` (per-module on `codegenie.skills/**`) are clean. `pytest tests/unit/skills/ tests/property/test_skills_loader_monotone.py` passes.
- [ ] **AC-15 — TDD discipline.** Red tests committed failing; green commit makes them pass; refactor commit is no-op behavior. Validator can reproduce.
- [ ] **AC-16 — same-tier collision is also `skill_shadowed`, lexicographic-first wins.** Fixture: `user/a/SKILL.md` (id `dup`) and `user/b/SKILL.md` (id `dup`) — both under the same `user` tier root. `load_all()` returns `LoadOutcome.skills == [user_a]` (lexicographic first) **and** emits exactly one `skill_shadowed` event with `winning_tier == shadowed_tier == "user"` and `shadowed_path == user/b/SKILL.md`. Same-tier collisions are operationally indistinguishable from cross-tier ones; the deterministic-load commitment (`§2.6`) requires both cases be handled.
- [ ] **AC-17 — exact `body_offset` / `body_size` (subsumed into AC-7a; retained as alias).** See AC-7a.
- [ ] **AC-18 — `os.open` flag set exactly enforced.** Spy `monkeypatch.setattr(os, "open", spying_open)` on the SkillsLoader-side open (NOT the `safe_yaml`-side; capture only the SKILL.md path opens). For each `SKILL.md` opened, `flags == os.O_RDONLY | os.O_NOFOLLOW | os.O_NOCTTY` exactly. An implementation that drops `O_NOFOLLOW` (silent security regression — AC-5 catches the *behavioral* consequence, AC-18 catches the *code-level* drop before any symlink fixture even runs) fails this test.
- [ ] **AC-19 — within-tier deterministic ordering (cross-filesystem reproducibility).** Fixture: `user/zzz/SKILL.md` (id `zzz`) and `user/aaa/SKILL.md` (id `aaa`). `load_all()` returns skills in lexicographic order of `path.relative_to(tier_root)` — i.e., `[aaa, zzz]`, irrespective of `rglob`'s filesystem-dependent yield order. Assertion uses two-skill order, not insertion order.
- [ ] **AC-20 — TOCTOU file disappearance → typed `IoFailure`, no unhandled exception.** Fixture: directly invoke `_load_one_skill(Path("/path/that/does/not/exist/SKILL.md"))`. Returns `Result.Err(IoFailure(path=..., errno_name="ENOENT"))`. (Catches the race window between `rglob` yielding a path and `os.open` opening it.) Other observed errnos catch as well — `EACCES → "EACCES"`, `EISDIR → "EISDIR"` — via `errno.errorcode[exc.errno]`.
- [ ] **AC-21 — `find_applicable` correctness (subsumed into AC-11a; retained as alias).** See AC-11a.
- [ ] **AC-22 — `["*"]` wildcard semantics.** A skill with `applies_to_tasks=[cast(TaskClassId, "*")]` matches *any* `EvidenceQuery.task` (including `None`); a skill with `applies_to_languages=[cast(Language, "*")]` matches an `EvidenceQuery.languages` that is empty or any value. Documented in the module docstring; pinned by parametrized test. Note: `"*"` is the documented wildcard sentinel per `CLAUDE.md §"Conventions to follow"` ("`['*']` meaning 'all'").
- [ ] **AC-23 — `find_applicable` returns a fresh list per call (defensive copy).** `loader.find_applicable(q) is not loader.find_applicable(q)` (identity inequality). Mutating the returned list (`result.clear()`) does not affect a subsequent call's return. Internal `_skills` reference is not exposed.
- [ ] **AC-24 — AST source-scan: no direct YAML import outside `safe_yaml`.** `tests/unit/skills/test_no_direct_yaml_import.py` uses `ast.parse` on every `.py` under `src/codegenie/skills/` and asserts no `Import` / `ImportFrom` node names `yaml`. Replaces the ripgrep `yaml\.` check — durable against alias smuggling (`from yaml import safe_load as _y`). Per S1-04 AC-23 precedent.
- [ ] **AC-25 — hashing chokepoint (Open/Closed extension).** `tests/unit/skills/test_no_direct_blake3_import.py` uses `ast.parse` on every `.py` under `src/codegenie/skills/` and asserts no `Import` / `ImportFrom` node names `blake3` or `hashlib`. All hash computation routes through `codegenie.hashing.content_hash_fd`. A new public symbol `content_hash_fd(fd: int, *, offset: int, size: int) -> str` is added to `src/codegenie/hashing.py`'s `__all__`; the existing `__all__` list grows by exactly one entry; no edits to existing `content_hash` / `content_hash_bytes` / etc.
- [ ] **AC-26 — tempfile cleanup verified, even on parse failure.** After `load_all()` over a fixture that triggers `UnsafeYaml` (AC-6), `len(list(Path(tempfile.gettempdir()).glob("*.yaml")))` is identical before and after the call (no orphans). The `try/finally` cleanup in `_load_one_skill` is exercised. Uses `tempfile.tempdir` monkeypatched to a per-test `tmp_path / "tmp"` for hermetic measurement.

## Implementation outline

0. **`src/codegenie/hashing.py`** — extend by addition (Open/Closed): add public `content_hash_fd(fd: int, *, offset: int, size: int) -> str` returning `f"blake3:{hex64}"` identical in format to `content_hash(path)`. Lazy-imports `blake3` per existing convention; reads in 64 KiB chunks via `os.read(fd, 1 << 16)` after `os.lseek(fd, offset, os.SEEK_SET)`. Add to `__all__`. No edits to existing functions; new tests in `tests/unit/test_hashing.py` for the new symbol parity with `content_hash_bytes` (round-trip identity).
1. **`src/codegenie/skills/model.py`** — `Tier: TypeAlias = Literal["user", "repo", "org"]`; `_TIERS: Final[tuple[Tier, ...]] = ("user", "repo", "org")`. Import `SkillId`, `TaskClassId`, `Language` from `codegenie.types.identifiers` (do **not** redefine — newtypes are kernel-side per S1-05). Define `Skill` Pydantic model (`frozen=True, extra="forbid"`) with fields: `id: SkillId`, `applies_to_tasks: list[TaskClassId]`, `applies_to_languages: list[Language]`, `body_offset: Annotated[int, Field(ge=0)]`, `body_size: Annotated[int, Field(ge=0)]`, `body_blake3: Annotated[str, Field(pattern=r"^blake3:[0-9a-f]{64}$")]`. Define `EvidenceQuery` model (`frozen=True, extra="forbid"`) with `task: TaskClassId | None`, `languages: set[Language]`.
2. **`src/codegenie/skills/loader.py`::`SkillsLoadError`** — Pydantic discriminated union over five reasons:
   ```python
   class SymlinkRefused(BaseModel):           # frozen=True, extra="forbid"
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
       details: list[dict]                    # Pydantic ValidationError.errors() shape
   class IoFailure(BaseModel):
       reason: Literal["io_failure"] = "io_failure"
       path: Path
       errno_name: str                        # errno.errorcode[exc.errno] — "ENOENT", "EACCES", "EISDIR", ...
   SkillsLoadError = Annotated[
       Union[SymlinkRefused, UnsafeYaml, FrontmatterUnterminated, SchemaViolation, IoFailure],
       Field(discriminator="reason"),
   ]
   class LoadOutcome(BaseModel):              # frozen=True, extra="forbid"
       skills: list[Skill]
       per_file_errors: list[SkillsLoadError]
   class FatalLoadError(BaseModel):           # only path: catastrophic (no tier readable, etc.)
       reason: Literal["all_tiers_unreadable"] = "all_tiers_unreadable"
       attempted: list[Path]
   ```
3. **`SkillsLoader.__init__(self, search_paths: list[Path]) -> None`** — store `self._search_paths = list(search_paths)`, initialize `self._skills: list[Skill] = []`. **No** `os` calls — no `Path.exists`, no `Path.iterdir`, no `Path.glob`, no `os.scandir`. The default factory `SkillsLoader.default()` (classmethod) builds the pinned three-tier order (user, repo-local, org-shared) zipped with `_TIERS`. Tier addition is ADR-amend-gated (intentional friction matches ADR-0030's "no `Unknown` variant" precedent).
4. **`SkillsLoader.load_all(self) -> Result[LoadOutcome, FatalLoadError]`**. A single bad file is **not** fatal (arch §"Failure behavior"). Outline:
   ```python
   from codegenie.skills.model import _TIERS, Tier
   skills_by_id: dict[SkillId, tuple[Tier, Path, Skill]] = {}   # tier → (path, skill)
   errors: list[SkillsLoadError] = []
   for tier, search_path in zip(_TIERS, self._search_paths, strict=True):
       if not search_path.exists():
           continue            # missing optional tier silently skipped (AC-3a)
       # Sort within-tier for cross-FS determinism (AC-19).
       skill_mds = sorted(search_path.rglob("SKILL.md"),
                          key=lambda p: p.relative_to(search_path).as_posix())
       for skill_md in skill_mds:
           outcome = _load_one_skill(skill_md)
           match outcome:
               case Ok(value=skill):
                   if skill.id in skills_by_id:
                       prior_tier, prior_path, _ = skills_by_id[skill.id]
                       log.warning("skill_shadowed",
                                   skill_id=skill.id,
                                   winning_tier=prior_tier,
                                   shadowed_tier=tier,
                                   winning_path=str(prior_path),
                                   shadowed_path=str(skill_md))
                       continue        # first-tier-wins; lexicographic-first within tier (AC-16)
                   skills_by_id[skill.id] = (tier, skill_md, skill)
               case Err(error=err):
                   errors.append(err)
                   log.warning("skill_load_failed", **err.model_dump(mode="json"))
   self._skills = [s for (_, _, s) in skills_by_id.values()]
   return Ok(value=LoadOutcome(skills=list(self._skills), per_file_errors=errors))
   ```
5. **`_load_one_skill(path: Path) -> Result[Skill, SkillsLoadError]`** — the per-file routine. Recommended functional-core split (see Notes-for-implementer §"Functional-core split"); the monolithic shape below is acceptable but split is preferred:
   ```python
   try:
       fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOCTTY)   # AC-18 asserts exact flags
   except OSError as exc:
       if exc.errno == errno.ELOOP:
           return Err(error=SymlinkRefused(path=path))
       # AC-20: every other OSError → typed IoFailure (NOT raise); covers TOCTOU file-disappearance.
       return Err(error=IoFailure(path=path, errno_name=errno.errorcode.get(exc.errno or 0, "EUNKNOWN")))
   try:
       frontmatter_bytes, body_offset = _read_frontmatter(fd, max_scan_bytes=1 << 20)
       if frontmatter_bytes is None:
           return Err(error=FrontmatterUnterminated(path=path))
       body_size = os.fstat(fd).st_size - body_offset
       body_blake3 = content_hash_fd(fd, offset=body_offset, size=body_size)   # AC-25 — chokepoint
   finally:
       os.close(fd)
   # Parse frontmatter via the safe_yaml chokepoint (no parallel loader).
   tmp_fd, tmp_name = tempfile.mkstemp(suffix=".yaml")
   tmp_path = Path(tmp_name)
   try:
       with os.fdopen(tmp_fd, "wb") as tf:
           tf.write(frontmatter_bytes)
       try:
           data = safe_yaml.load(tmp_path, max_bytes=1 << 20)
       except MalformedYAMLError:
           return Err(error=UnsafeYaml(path=path))   # AC-6 + AC-6b — umbrella for ALL yaml.YAMLError
   finally:
       tmp_path.unlink(missing_ok=True)          # AC-26 — cleanup on every path
   try:
       return Ok(value=Skill(**data, body_offset=body_offset,
                             body_size=body_size, body_blake3=body_blake3))
   except ValidationError as exc:
       return Err(error=SchemaViolation(path=path, details=exc.errors()))
   ```
6. **`_read_frontmatter(fd, *, max_scan_bytes)`** — read in 4 KiB chunks; locate the opening `---\n` (the file's first 4 bytes MUST be `---\n` or `---\r\n`, otherwise return `(None, _)` immediately — frontmatter is mandatory); locate the closing `---\n`; return `(frontmatter_bytes, body_offset)` where `body_offset = bytes_consumed_through_closing_delimiter` (the offset of the FIRST byte AFTER the closing `---\n`). Cap at `max_scan_bytes` total scanned before terminator → `(None, body_offset_default)`.
7. **`content_hash_fd(fd, *, offset, size)`** (from Step 0 above; lives in `codegenie.hashing`, not in `skills/`) — `os.lseek(fd, offset, os.SEEK_SET)`; loop `os.read(fd, 1 << 16)` into the running BLAKE3 hasher; count bytes (assert == `size`); return `f"blake3:{hasher.hexdigest()}"`. **No** intermediate `bytes` accumulator. This is the path AC-7 protects.
8. **`find_applicable(self, evidence: EvidenceQuery) -> list[Skill]`** — thin instance method that delegates to a pure module-level function `_matches(skills: Sequence[Skill], evidence: EvidenceQuery) -> list[Skill]` (functional-core; testable without a loader). Matching rule per Invariant §7. Returns `list(matches)` — a fresh `list`, never the cached `self._skills` reference (AC-23). Pre-`load_all` state returns `[]` without I/O (AC-11b).
9. **Pure matching function** `_matches(skills, evidence)`:
   ```python
   def _matches(skills: Sequence[Skill], evidence: EvidenceQuery) -> list[Skill]:
       _WILDCARD_TASK = cast(TaskClassId, "*")
       _WILDCARD_LANG = cast(Language, "*")
       out: list[Skill] = []
       for skill in skills:
           tasks_ok = (_WILDCARD_TASK in skill.applies_to_tasks) or \
                      (evidence.task is not None and evidence.task in skill.applies_to_tasks)
           langs_ok = (_WILDCARD_LANG in skill.applies_to_languages) or \
                      (bool(set(skill.applies_to_languages) & evidence.languages))
           if tasks_ok and langs_ok:
               out.append(skill)
       return out
   ```
10. **structlog event names** are literal strings for now (`"skill_shadowed"`, `"skill_load_failed"`); S1-10's `Final[str]` constant promotion convention applies to Phase 1's `probe.parser.cap_exceeded` only — Phase 2 follow-up can promote these later, but YAGNI in Step 2.

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
| `src/codegenie/hashing.py` | **Modify (additive)** — add `content_hash_fd(fd, *, offset, size) -> str` to `__all__`; no edits to existing `content_hash` / `content_hash_bytes` / `identity_hash` (AC-25) |
| `src/codegenie/skills/__init__.py` | New — public surface (`Skill`, `SkillsLoader`, `SkillsLoadError`, `LoadOutcome`, `FatalLoadError`, `EvidenceQuery`, `Tier`) |
| `src/codegenie/skills/model.py` | New — `Tier` Literal alias, `_TIERS` ordering constant, `Skill` Pydantic model (typed with `SkillId` / `TaskClassId` / `Language` imported from `codegenie.types.identifiers`), `EvidenceQuery` model |
| `src/codegenie/skills/loader.py` | New — `SkillsLoadError` discriminated union (five reasons), `LoadOutcome`, `FatalLoadError`, `_load_one_skill`, `_read_frontmatter`, `_matches` pure function, `SkillsLoader` class |
| `tests/unit/test_hashing.py` | **Modify (additive)** — round-trip parity tests for `content_hash_fd` vs `content_hash_bytes` on identical bodies (AC-25 parity) |
| `tests/unit/skills/__init__.py` | New — package marker |
| `tests/unit/skills/test_loader.py` | New — named tests covering AC-1..AC-23, AC-26 |
| `tests/unit/skills/test_no_direct_yaml_import.py` | New — AST source-scan for AC-24 |
| `tests/unit/skills/test_no_direct_blake3_import.py` | New — AST source-scan for AC-25 |
| `tests/property/__init__.py` | New (if absent) — package marker |
| `tests/property/test_skills_loader_monotone.py` | New — Hypothesis property test for AC-11 (monotonicity); AC-11a positive correctness lives in `tests/unit/skills/test_loader.py` (deterministic fixture, not Hypothesis) |

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
- **`find_applicable` must remain a pure function over the cached `_skills` list.** Do not re-load on every call; the loader's state is the cached list from the last `load_all()`. If `load_all()` was never called, `find_applicable` returns `[]` (do not auto-call `load_all()` — explicit > implicit, per Rule 3). The matching logic lives in a top-level pure function `_matches(skills, evidence)` (functional-core); the instance method is a thin wrapper. This lets the matching contract be unit-tested without a filesystem fixture.

### Design-pattern notes (added by validator 2026-05-15)

- **Hashing chokepoint extension (Open/Closed at the file boundary).** The streaming-hash requirement forces a new public symbol on `codegenie.hashing`. **Do not** import `blake3` directly under `src/codegenie/skills/` — that violates ADR-0001 §"single source of truth for hashing" (Phase 0). The Open/Closed-compliant move is to extend `codegenie.hashing` with a new function, leaving every existing call site unchanged. This is the same pattern as `parsers/_io.py::open_capped` — one kernel, many parser-kind callers — applied to hashing.
- **Functional-core / imperative-shell split.** `_load_one_skill` does seven concerns. Pure-function shape preferred:
  - Pure: `_split_frontmatter(data: bytes) -> Result[FrontmatterSplit, FrontmatterUnterminated]` (where `FrontmatterSplit = NamedTuple(frontmatter_bytes: bytes, body_offset: int)`).
  - Pure: `_build_skill(parsed: dict, body_offset: int, body_size: int, body_blake3: str) -> Result[Skill, SchemaViolation]` (wraps the `try/except ValidationError`).
  - Pure: `_matches(skills, evidence) -> list[Skill]` (the `find_applicable` engine).
  - Impure: `_open_skill_path(path) -> Result[int, SymlinkRefused | IoFailure]` (the `os.open` call).
  - Impure: `_read_with_streaming_hash(fd, body_offset) -> tuple[int, str]` (the fd-based loop).
  - Impure: `_load_one_skill` is the imperative shell composing the above.

  Each pure helper is unit-testable with bytes inputs — no filesystem fixture, no tempfile, no monkeypatch. The mutation-table closures (AC-7a, AC-11a) become trivial against pure functions. **Not promoted to AC** (Rule 3 / surgical changes — observable behavior is constrained by the AC suite; the shape is the implementer's call). But if the implementer writes a 200-LOC monolithic `_load_one_skill`, expect the executor's Validator pass to push back on test-isolation grounds.
- **Tier typing — `Literal`, not `int` indices.** `_TIER_NAME = {0: "user", 1: "repo", 2: "org"}` is a tag-and-dispatch over `int` (ADR-0033 §3 flags this as anti-pattern adjacent). Use `Tier: TypeAlias = Literal["user", "repo", "org"]` + `_TIERS: Final[tuple[Tier, ...]] = ("user", "repo", "org")`. `zip(_TIERS, self._search_paths, strict=True)` iterates with typed tier identity; log events emit `winning_tier: Tier` directly. The type checker now enforces "no fourth tier without an ADR amendment to `_TIERS` + `Tier`."
- **`SkillsLoadError` is a Pydantic discriminated union, but `TCCMLoadError` (S1-04) is a marker `CodegenieError` subclass — both are correct.** Convention forward: single-file loaders that raise on parse failure (`safe_yaml.load`, `TCCMLoader`) use marker exceptions with prefixed `args[0]`; multi-file partial-success loaders that *return* per-file errors as values (this story, S2-02 `ConventionsCatalogLoader`) use Pydantic discriminated unions. Phase 1's markers-only invariant (`tests/unit/test_errors.py::test_subclasses_are_markers_only`) binds only `codegenie.errors.CodegenieError` subclasses; `Result.Err` payloads are out-of-scope for that test and require their own typed-value discipline (ADR-0033 §3).
- **Primitive obsession on `applies_to_*` (ADR-0033 §1).** `list[str]` is *syntactically* correct but *semantically* wrong — `applies_to_tasks` is a list of task-class identifiers, not arbitrary strings; same for languages. Use `list[TaskClassId]` and `list[Language]` so a mistake like passing a `Language` where a `TaskClassId` is expected fails at type-check time. The newtypes already live in `codegenie.types.identifiers`; import them.
- **`EvidenceQuery` over `set[str]` (ADR-0033 §3, illegal-states-unrepresentable).** A flat `set[str]` of mixed task/language identifiers cannot distinguish "the empty set of languages, no task" from "a query with no task and any language" — and silently conflates `applies_to_tasks` matching with `applies_to_languages` matching. The typed `EvidenceQuery(task: TaskClassId | None, languages: set[Language])` makes the two axes structurally separate; the wildcard semantics (`"*"`) live in the Skill, not the query. Phase 4+ planners that produce queries get typed call sites.
- **`["*"]` wildcard sentinel — CLAUDE.md convention.** Per `CLAUDE.md §"Conventions to follow when writing the POC"`: "Each probe declares `applies_to_tasks` and `applies_to_languages` with `['*']` meaning 'all'." This is *the* documented wildcard. Do not invent a `applies_to_tasks: list[TaskClassId] | None = None` "any" sentinel — that's primitive-obsession resurfacing.
- **Three-tier order is ADR-amend-gated (intentional friction).** Adding a fourth tier (e.g., "container-mounted" or "monorepo-shared") requires editing `Tier` Literal + `_TIERS` constant + `default()` factory + this story's ACs. That friction is intentional — the security model depends on tier *count* and *order*, not just on the merge semantics. Per the precedent of ADR-0030's "no `Unknown` `DerivedQuery` variant" trapdoor.
- **`unsafe_yaml` is operationally umbrella, not strictly accurate.** `safe_yaml.load` translates *every* `yaml.YAMLError` subclass to `MalformedYAMLError` — `ConstructorError` (the `!!python/...` case), `ParserError` (the syntax-typo case), `ScannerError`, `ComposerError`. The `unsafe_yaml` reason name is the operationally-prudent umbrella ("treat as hostile until investigated"). Operators reading `unsafe_yaml=true` in a log inspect the file; the inspection itself distinguishes attack-attempt from typo. Do not split into `unsafe_yaml` / `malformed_yaml` — the cost-of-distinguishing exceeds the value (we'd be inferring intent from a `__cause__` chain). AC-6 + AC-6b prove both arms land in the same bucket and that no code executes for either. Arch §"Edge cases" row 8 is authoritative.
- **`body_blake3` format pin.** The hashing module returns `f"blake3:{64-hex}"`. `body_blake3` is pinned to that format via `Field(pattern=...)`; AC-8 asserts the regex. An implementation that strips the prefix, truncates, or silently switches to SHA-256 fails the model construction itself — fail-loud, ADR-0033-style.
- **No `O_NOFOLLOW` defense-in-depth via `safe_yaml.load`.** `safe_yaml.load` *itself* uses `O_NOFOLLOW` on the path it's given (the tempfile). The SkillsLoader-side `O_NOFOLLOW` on `path` (the real `SKILL.md`) is the load-bearing defense — the tempfile-side check is incidental (tempfiles aren't symlinks). AC-18 pins the SkillsLoader-side flag set explicitly.
- **TOCTOU: `rglob` does NOT snapshot the filesystem.** Between `search_path.rglob("SKILL.md")` yielding a path and `os.open(path)` opening it, an attacker (or a concurrent process) can delete the file. The original story claimed "load_all skips by rglob's snapshot semantics" — that's incorrect; Python's `pathlib.Path.rglob` is a generator over `os.scandir` results, not a snapshot. AC-20 mandates typed `IoFailure` instead of an unhandled `FileNotFoundError`. Catch *all* `OSError` (except `ELOOP` which is `SymlinkRefused`) and surface as `IoFailure(errno_name=errno.errorcode[exc.errno])`. The errno-name is a structural fingerprint operators can grep; the per-file error does not let the gather fail.
- **Same-tier collisions exist too.** Two `SKILL.md` files under `~/.codegenie/skills/` with the same `id: foo` is a real misconfiguration. The story treats this the same as cross-tier — same `skill_shadowed` event, with `winning_tier == shadowed_tier`. Lexicographic-first wins (deterministic). AC-16 closes this case.
