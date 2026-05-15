# Validation report — S2-01 `SkillsLoader` three-tier merge with `O_NOFOLLOW` + body byte-offset

**Story:** [`../S2-01-skills-loader.md`](../S2-01-skills-loader.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story ships `src/codegenie/skills/` (three new files + a chokepoint extension to `codegenie.hashing`): the `Skill` Pydantic model (`frozen=True`, `extra="forbid"`, ADR-0033-typed identifiers), the `SkillsLoadError` discriminated union, and `SkillsLoader` with `__init__`-pure-data + three-tier first-tier-wins merge + `O_NOFOLLOW` open + `safe_yaml.load` chokepoint reuse + progressive-disclosure body hashing. All references trace cleanly to `02-ADR-0007` (kernel-only scaffolding, no plugin loader), arch §"Component design" #9, arch §"Scenarios" Scenario 3, arch §"Edge cases" rows 8/9/16, production ADR-0033 §1 + §3–4 (newtype + sum types), CLAUDE.md §"Conventions to follow" (`["*"]` wildcard), Phase 0 ADR-0001 (hashing chokepoint), and Phase 1 ADR-0006 (`safe_yaml` chokepoint).

The draft was structurally sound — three-tier order is correct, security commitments are present, `safe_yaml` chokepoint discipline is preserved, ADR-0007's "no plugin loader" boundary respected — but had **three block-tier executor-halt risks** and **a dozen harden-tier gaps** that would have let a wrong implementation slip past the executor's Validator pass. The block-tier risks all collapse to "the prescribed implementation literally cannot be written as described against the verified repo state."

Stage 3 research **skipped** — no `NEEDS RESEARCH` findings. Every gap was answerable from arch + ADR-0007 + ADR-0033 + ADR-0001 + S1-04 / S1-03 validation precedents + verified repo state (`src/codegenie/hashing.py`, `src/codegenie/parsers/safe_yaml.py`, `src/codegenie/tccm/loader.py`, `src/codegenie/types/identifiers.py`).

Twelve ACs added, six ACs strengthened, one section of design-pattern Notes appended. Implementation outline rewritten to specify the hashing-chokepoint extension and the typed-tier discipline. Story is now ready for `phase-story-executor`.

## Context Brief (Stage 1)

### Story snapshot

- **Goal as written:** Ship `src/codegenie/skills/` (`__init__.py`, `model.py`, `loader.py`) with `Skill` Pydantic model (frozen, extra="forbid"), `SkillsLoader` (pure-data `__init__`, first I/O is `load_all()`), three-tier first-tier-wins merge, `O_NOFOLLOW` per-file open, `safe_yaml.load` chokepoint reuse, body byte-offset-recorded progressive disclosure (`tracemalloc` peak < 20 KB on a 100 MB-body fixture), and `find_applicable(evidence_keys)` monotonicity.
- **Non-goals:** Layer D `SkillsIndexProbe` (S6-01); per-tier signing (Phase 14); `ConventionsCatalogLoader` (S2-02); reference TCCM roundtrip (S2-03); `safe_yaml.loads_bytes` shim (rule of three until S2-02 / S2-03 materialize a second caller); skills body content rendering.

### Phase 2 exit criteria touched

- **G9** — kernel scaffolding ships, no plugin loader (02-ADR-0007). ✓
- **Three-tier merge with first-tier-wins** + loud `skill_shadowed` warning (arch §"Edge cases" row 16). ✓
- **Progressive disclosure** (commitment §2.7; tracemalloc-pinned). ✓
- **`safe_yaml.load` chokepoint** preserved (Phase 1 ADR-0006). ✓

### Load-bearing commitments touched

- CLAUDE.md §"No LLM anywhere in the gather pipeline" — loader is deterministic, no LLM. ✓
- CLAUDE.md §"Facts, not judgments" — `Skill` is data; the Planner (Phase 4+) decides applicability. ✓
- CLAUDE.md §"Honest confidence" — N/A (no confidence rendering in this story).
- CLAUDE.md §"Extension by addition" — three-tier order is ADR-amend-gated; new tier adds (doesn't edit). ✓
- CLAUDE.md §"Conventions to follow" — `["*"]` wildcard for `applies_to_*` (was missing from draft).
- 02-ADR-0007 §Decision/§Consequences — `SkillsLoader` is kernel-side; `O_NOFOLLOW` + three-tier merge + `safe_yaml.load` chokepoint. ✓
- Phase 0 ADR-0001 §"single source of truth for hashing" — *implicated by streaming-hash requirement*; original story would have violated.
- Phase 1 ADR-0006 §"`safe_yaml` chokepoint" — preserved via tempfile dance. ✓
- ADR-0033 §1 (newtypes) — `Skill.applies_to_tasks: list[str]` was primitive-obsession; fixed to `list[TaskClassId]`.
- ADR-0033 §3 (sum types) — `_TIER_NAME: dict[int, str]` was tag-and-dispatch over `int`; fixed to `Tier: Literal[...]`.
- ADR-0033 §4 (illegal states unrepresentable) — `SkillsLoadError` discriminated union is correctly typed; story's choice to diverge from S1-04's marker pattern is justified (partial-success multi-file semantics).

### Sibling-family lineage

- **Third loader-shaped consumer in Phase 2** after `safe_yaml.load` (Phase 1 — single-file, raises) and `TCCMLoader` (S1-04 — single-file, marker exception + string-prefix reason).
- **First multi-file partial-success loader.** This story sets the convention for S2-02 (`ConventionsCatalogLoader`) and any future Phase 4+ loader of the same shape. Convention documented in Notes-for-implementer.
- **Rule-of-three threshold for shared loader-kernel:** NOT YET REACHED. `safe_yaml`, `TCCMLoader`, `SkillsLoader` have meaningfully different shapes (one parser, two loaders; two single-file, one multi-file; one raises, two return `Result`). No single abstraction would compress all three without coupling unrelated concerns. Sharing is structural via `safe_yaml.load` (the YAML chokepoint) and `parsers/_io.py::open_capped` (the `O_NOFOLLOW`+size-cap chokepoint), already established.
- **Rule-of-three threshold for hashing chokepoint:** REACHED on extension. `content_hash(path)` + `content_hash_bytes(b)` + `content_hash_of_inputs(paths)` already exists; `content_hash_fd(fd, offset, size)` is the natural fourth, additive, no edit to existing functions.

### Goal-to-AC trace

- AC-1 → goal: YES (module surface, `__all__`, discriminated union shape).
- AC-2 → goal: STRENGTHENED (constructor purity; expanded I/O monkeypatch set to catch `Path.iterdir`/`Path.glob` smuggling).
- AC-3, AC-3a → goal: STRENGTHENED (full-field assertion; missing-tier silent skip).
- AC-4, AC-4a → goal: STRENGTHENED (added middle-tier-wins case to catch `_TIERS` indexing mutation).
- AC-5 → goal: STRENGTHENED (asserted no leakage of symlink-target contents).
- AC-6, AC-6b, AC-6c, AC-6d → goal: ADDED (umbrella-honesty for `unsafe_yaml`; `FrontmatterUnterminated`; `SchemaViolation`).
- AC-7, AC-7a → goal: STRENGTHENED (exact `body_offset`/`body_size` for hand-constructed fixture).
- AC-8 → goal: STRENGTHENED (format regex pin replaces ambiguous "[:32]" prescription).
- AC-9 → goal: kept (frozen + extra="forbid").
- AC-10 → goal: STRENGTHENED (added JSON-shape pin per S1-04 precedent).
- AC-11, AC-11a, AC-11b → goal: STRENGTHENED (correctness paired with monotonicity; pre-`load_all` state).
- AC-12 → goal: kept (runtime spy).
- AC-13 → goal: kept (`forbidden-patterns` extension).
- AC-14, AC-15 → goal: kept (toolchain, TDD discipline).
- AC-16 → goal: ADDED (same-tier collision).
- AC-17 → alias of AC-7a.
- AC-18 → goal: ADDED (exact `os.open` flag set).
- AC-19 → goal: ADDED (within-tier deterministic ordering).
- AC-20 → goal: ADDED (TOCTOU file-disappearance → typed `IoFailure`).
- AC-21 → alias of AC-11a.
- AC-22 → goal: ADDED (`["*"]` wildcard semantics).
- AC-23 → goal: ADDED (defensive copy from `find_applicable`).
- AC-24 → goal: ADDED (AST source-scan for YAML chokepoint).
- AC-25 → goal: ADDED (AST source-scan for hashing chokepoint; new `content_hash_fd` public symbol).
- AC-26 → goal: ADDED (tempfile cleanup verified).

### Open ambiguities resolved before Stage 2

- **`codegenie.hashing` streaming API** — does not exist (`content_hash(path)` only). Resolution: extend by addition (`content_hash_fd`); ADR-0001 chokepoint preserved.
- **`SkillId`, `TaskClassId`, `Language` newtypes** — exist in `codegenie.types.identifiers` (verified). Resolution: import, do not redefine.
- **`Result[T, E]` Pydantic union** — exists in `codegenie.result` (verified; lifted in S1-04). Resolution: use `Ok(value=...)` / `Err(error=...)` constructors.
- **`safe_yaml.load` signature** — `(path: Path, *, max_bytes: int, max_depth: int = 64) -> Mapping[str, JSONValue]`; raises `MalformedYAMLError` for *every* `yaml.YAMLError` subclass plus non-mapping top-level (verified). Resolution: `unsafe_yaml` is umbrella; AC-6b documents this honestly.
- **`["*"]` wildcard semantics** — CLAUDE.md §"Conventions to follow when writing the POC" pins this. Resolution: AC-22.

## Stage 2 — critic reports

### Coverage (verdict: COVERAGE-HARDEN — 9 findings)

**Block-tier:**
- **C1.1 (block) — `codegenie.hashing.content_hash` API mismatch.** Story prescribed "streaming `os.read(fd, 64 * 1024)` chunks through `codegenie.hashing.content_hash`" but the public API is `content_hash(path: Path) -> str` — accepts neither fd nor chunks. The hashing module's docstring forbids direct `blake3` / `hashlib.sha256` imports outside that file (Phase 0 ADR-0001). Implementer has no Open/Closed-compliant path to satisfy AC-7 as written. **Fix:** Story now commits to extending `codegenie.hashing` with `content_hash_fd(fd, *, offset, size) -> str`; new AC-25 enforces the chokepoint; Implementation outline §0 lays out the addition.
- **C1.2 (block) — `find_applicable(evidence_keys: set[str])` semantics under-specified.** Original spec said `set(applies_to_tasks) <= evidence_keys` AND `set(applies_to_languages) <= evidence_keys` — but `evidence_keys` is a flat `set[str]` that conflates task-class identifiers and language identifiers (e.g., is `"typescript"` a task or a language?). CLAUDE.md prescribes `["*"]` as the wildcard sentinel for `applies_to_*` lists — the story didn't honor it. **Fix:** `find_applicable(evidence: EvidenceQuery)` with a typed `EvidenceQuery(task: TaskClassId | None, languages: set[Language])`; AC-22 pins `["*"]` semantics; AC-11a closes correctness; AC-11 retains monotonicity.

**Harden-tier:**
- C1.3 — AC-3 happy-path doesn't enforce within-tier order across filesystems. **Fix:** AC-19 lexicographic sort.
- C1.4 — No AC exercises `FrontmatterUnterminated` trigger condition. **Fix:** AC-6c.
- C1.5 — No AC exercises `SchemaViolation` reason. **Fix:** AC-6d.
- C1.6 — AC-3a missing (missing-tier silent skip). **Fix:** AC-3a.
- C1.7 — AC for `find_applicable([])` before `load_all()` missing. **Fix:** AC-11b.
- C1.8 — Three-tier order doc trace (user > repo > org) — confirmed against ADR-0007 §Decision. Not a finding.
- C1.9 — No AC for body field full-population in happy path. **Fix:** AC-3 strengthened to assert every field.

### Test quality (verdict: TESTS-HARDEN — 12 findings; 29-row mutation table)

Mutation table excerpts (full table below):

| # | Wrong impl | Caught by draft? | Closure |
|---|---|---|---|
| 1 | `body = f.read(); blake3(body)` | YES — AC-7 tracemalloc | — |
| 2 | Swap tier order silently (org > repo > user) | YES — AC-4 | — |
| 3 | First-tier-LOSES on collision | YES — AC-4 | — |
| 4 | Drop `frozen=True` from `Skill` | YES — AC-9 | — |
| 5 | Drop `extra="forbid"` from `Skill` | YES — AC-9 | — |
| 6 | `os.open` without `O_NOFOLLOW` | YES (behavioral) — AC-5 | Strengthened by AC-18 (code-level) |
| 7 | YAML parsed via `yaml.safe_load` directly | YES (ripgrep) — AC-12 | Strengthened by AC-24 (AST, alias-resistant) |
| 8 | `yaml.load` with default Loader → `!!python/object` executes | YES — AC-6 | — |
| 9 | Symlink case raises instead of returning Result.Err | YES — AC-5 | — |
| 10 | Frontmatter missing terminator → infinite loop / OOM | NO | AC-6c |
| 11 | Schema violation → exception instead of typed error | NO | AC-6d |
| 12 | `find_applicable` returns all skills regardless of evidence | NO (Hypothesis monotonicity vacuous on `return []`) | AC-11a |
| 13 | `find_applicable` returns first match only | NO | AC-11a multi-member fixture |
| 14 | `body_blake3` length/format silent change | PARTIAL — original spec ambiguous | AC-8 regex |
| 15 | `body_blake3` uses SHA-256 instead of BLAKE3 | NO (depends on C1.1 fix) | AC-25 chokepoint |
| 16 | `body_size` set to total file size | NO | AC-7a |
| 17 | `body_offset` off-by-one | NO | AC-7a |
| 18 | Constructor uses `Path.glob` (not `os.listdir`) — bypasses AC-2 monkeypatch | PARTIAL | AC-2 strengthened |
| 19 | `safe_yaml.load` chokepoint circumvented via `from yaml import safe_load as _y` | PARTIAL — ripgrep `yaml\.` misses alias | AC-24 AST |
| 20 | `O_NOFOLLOW` opens but follows internal-path-component symlinks | NA — documented behavior | Notes |
| 21 | `_load_one_skill` propagates non-ELOOP `OSError` (TOCTOU) | NO | AC-20 |
| 22 | Multiple `skill_shadowed` events emitted | YES — AC-4 `len() == 1` | — |
| 23 | Tempfile leaks | NO | AC-26 |
| 24 | `_TIER_NAME` off-by-one (org reported as "repo") | NO — AC-4 only tests user-vs-org | AC-4a |
| 25 | `find_applicable` returns mutable internal list | NO | AC-23 |
| 26 | TOCTOU symlink-replace between rglob and open — `O_NOFOLLOW` defends | — | — |
| 27 | Body hashed across closing `---` line | NO | AC-7a |
| 28 | Billion-laughs YAML — `safe_yaml.load` depth cap defends | — | Confirmed via S1-03 |
| 29 | Same-tier collision silently merged | NO | AC-16 |

Additional test-quality concerns:
- Property-based monotonicity is insufficient (TQ1). **Fix:** AC-11a paired correctness.
- Defensive-copy on `find_applicable` return missing (TQ — mutation safety). **Fix:** AC-23.
- Constructor I/O monkeypatch incomplete (TQ — `os.scandir`, `Path.exists`). **Fix:** AC-2 strengthened.

### Consistency (verdict: CONSISTENCY-HARDEN — 10 findings)

- **CN1** — `SkillsLoader.__init__` signature differs from `TCCMLoader.__init__` (which has zero args). Both are "pure data at __init__" — justified asymmetry; SkillsLoader needs `search_paths` (multi-file walk); TCCMLoader takes `path` per call (single-file). Documented in Notes (H5 in Validation notes).
- **CN2 (resolved)** — `SkillsLoadError` Pydantic union vs `TCCMLoadError` marker. Resolution: both correct, different shapes for different use-cases. Convention documented in Notes-for-implementer.
- **CN3 (block→harden)** — Two `os.open` events per skill (SkillsLoader-side `O_NOFOLLOW` + `safe_yaml.load`'s own `O_NOFOLLOW` on the tempfile). Defense-in-depth claim is correct. **Fix:** AC-18 asserts explicit flag set so a contributor who deletes the SkillsLoader-side `O_NOFOLLOW` fails the test before any symlink fixture runs.
- **CN4** — Tempfile dance documented; AC-26 added to verify cleanup on every path (parse-success and parse-failure).
- **CN5 (block)** — Hashing chokepoint violation (same as C1.1). **Fix:** Story now extends `codegenie.hashing` (AC-25).
- **CN6 (block)** — `body_blake3` format ambiguous ("[:32] or project's documented BLAKE3-fingerprint width"). **Fix:** Pinned to `r"^blake3:[0-9a-f]{64}$"`; AC-8.
- **CN7 (block)** — `unsafe_yaml` covers all `MalformedYAMLError` causes, not just `ConstructorError`. **Fix:** AC-6b documents and tests the umbrella; Notes-for-implementer explains why splitting would be wrong (intent inference from `__cause__` chain).
- **CN8** — Primitive obsession on `applies_to_*` (`list[str]`). **Fix:** `list[TaskClassId]` / `list[Language]`. ADR-0033 §1.
- **CN9** — Three-tier order doc trace confirmed. Not a finding.
- **CN10** — `_TIER_NAME: dict[int, str]` is tag-and-dispatch over `int`. **Fix:** `Tier: TypeAlias = Literal["user", "repo", "org"]` + `_TIERS: Final[tuple[Tier, ...]] = (...)`. ADR-0033 §3.

### Design patterns (verdict: DESIGN-HARDEN — 12 findings)

- **DP1 (block, resolved by CN5/AC-25)** — Hashing chokepoint extension is the load-bearing Open/Closed application. `codegenie.hashing` grows by exactly one symbol; existing call sites unchanged.
- **DP2 (harden, Notes-only)** — `_load_one_skill` does seven concerns. Functional-core / imperative-shell split recommended in Notes; not promoted to AC (Rule 3 / observable-behavior-already-constrained).
- **DP3 (harden, AC)** — `_TIER_NAME` typing. Closed by AC-1 (Tier in `__all__`) + Implementation outline §1 + Notes.
- **DP4 (harden, Notes-only)** — Three-tier order is ADR-amend-gated; documented as intentional friction. Precedent: ADR-0030 "no `Unknown` variant."
- **DP5 (harden, Notes)** — `find_applicable` matching logic moved to pure top-level `_matches(skills, evidence)`. Implementation outline §9.
- **DP6 (harden, AC)** — Primitive obsession on `applies_to_*`. Closed by typed lists in model + Notes.
- **DP7 (harden, Notes-only)** — `LoadOutcome` as a dataclass-shaped value object (two lists). Acceptable; documented choice.
- **DP8 (harden, Notes-only)** — Future plugin-validation extension seam. Not in Phase 2 scope.
- **DP9 (harden, AC)** — `O_NOCTTY` flag bit never asserted. Closed by AC-18.
- **DP10 (Notes-only)** — Smart-constructor pattern on `LoadOutcome`. Overkill for Phase 2; recorded.
- **DP11 — confirmed:** No premature Plugin Loader. ADR-0007 respected. ✓
- **DP12 — confirmed:** No env-var auto-discovery; explicit `search_paths`. Arch §"Anti-patterns avoided" row 11 respected. ✓

## Stage 3 — research

**Skipped.** Zero findings tagged `NEEDS RESEARCH`. Every closure was answerable from arch + ADRs + verified repo state + S1-04 / S1-03 precedents.

## Stage 4 — edits applied

### Story header

- Added `Phase 0 ADR-0001` to "ADRs honored" — hashing chokepoint discipline.
- Added `production ADR-0033 §1` — newtypes for domain primitives (in addition to §3–4 already cited).
- Inserted `## Validation notes (added 2026-05-15 by phase-story-validator)` block right after the metadata, summarizing all changes.

### Goal block

- Retyped `Skill.applies_to_tasks: list[str]` → `list[TaskClassId]`.
- Retyped `Skill.applies_to_languages: list[str]` → `list[Language]`.
- Added `Tier: TypeAlias = Literal["user", "repo", "org"]` to the model surface.
- Added `EvidenceQuery(task: TaskClassId | None, languages: set[Language])`.
- Retyped `body_offset` / `body_size` with `Annotated[int, Field(ge=0)]`.
- Pinned `body_blake3` format in the model docstring.
- Updated `find_applicable` signature to take `EvidenceQuery`, not `set[str]`.
- Updated `load_all` return type to `Result[LoadOutcome, FatalLoadError]`.

### Invariants (numbered list under Goal)

- §3 — Rewrote streaming-hash prescription to use new `content_hash_fd` chokepoint extension. Pinned `r"^blake3:[0-9a-f]{64}$"` format.
- §4 — Rewrote three-tier merge to use typed `Tier` Literal + `_TIERS` constant; added within-tier lexicographic ordering; added same-tier collision behavior.
- §5 — Added `IoFailure` reason for TOCTOU and other non-ELOOP `OSError`; clarified `unsafe_yaml` umbrella semantics.
- §6 — Extended `SkillsLoadError` discriminated union from four to five reasons (added `io_failure`); added convention note distinguishing single-file marker vs multi-file Pydantic-union pattern.
- §7 — Replaced flat `set[str]` semantics with typed `EvidenceQuery`; added `["*"]` wildcard rule; added defensive-copy invariant.

### Acceptance criteria

**Strengthened in place:**
- AC-1 — exact-set `__all__` test; five reasons.
- AC-2 — expanded I/O monkeypatch set (`os.scandir`, `Path.exists`, `Path.is_dir`).
- AC-3 — every-field assertion (was id-only).
- AC-4 — full structured-fields assertion on `skill_shadowed`.
- AC-5 — leakage assertion (no symlink-target bytes in any Skill or log).
- AC-7 — pin deterministic fixture bytes.
- AC-8 — format regex pin replaces ambiguous "[:32]".
- AC-9 — constructable form with proper typed fields.
- AC-10 — JSON-shape pin per S1-04 precedent.
- AC-11 — monotonicity rewritten against `EvidenceQuery` semantics.
- AC-12 — runtime spy clarified; pairs with AC-24 AST.

**Added:**
- AC-3a — missing-tier silent skip.
- AC-4a — middle-tier-wins (catches `_TIERS` indexing mutation).
- AC-6b — pure-syntax YAML also lands as `unsafe_yaml` (umbrella honesty).
- AC-6c — `FrontmatterUnterminated` trigger.
- AC-6d — `SchemaViolation` trigger.
- AC-7a — exact `body_offset` / `body_size` for hand-constructed fixture (off-by-one catcher).
- AC-11a — `find_applicable` correctness paired with monotonicity.
- AC-11b — `find_applicable([])` returns `[]` before `load_all`.
- AC-16 — same-tier collision is `skill_shadowed` with lexicographic-first wins.
- AC-17 — alias to AC-7a (retained for cross-reference).
- AC-18 — exact `os.open` flag set (catches `O_NOFOLLOW` drop before any fixture runs).
- AC-19 — within-tier deterministic ordering across filesystems.
- AC-20 — TOCTOU file disappearance → typed `IoFailure`.
- AC-21 — alias to AC-11a (retained for cross-reference).
- AC-22 — `["*"]` wildcard semantics per CLAUDE.md.
- AC-23 — `find_applicable` defensive-copy.
- AC-24 — AST source-scan for direct YAML import (replaces ripgrep AC-12).
- AC-25 — AST source-scan for direct `blake3`/`hashlib` import; new `content_hash_fd` public symbol.
- AC-26 — tempfile cleanup verified on every path.

### Implementation outline

- §0 added — `codegenie.hashing.content_hash_fd` chokepoint extension.
- §1 rewrote — `Tier` Literal + `_TIERS` ordering constant; typed identifier imports.
- §2 rewrote — discriminated union grew to five reasons; `LoadOutcome` and `FatalLoadError` Pydantic models added.
- §3 rewrote — pure-data init contract strengthened.
- §4 rewrote — `_TIERS` zipped with `search_paths`; within-tier `sorted()` for AC-19; same-tier collision handling.
- §5 rewrote — TOCTOU `OSError` handling; `tempfile.mkstemp` instead of `NamedTemporaryFile`; chokepoint extension call.
- §6 kept (frontmatter scan).
- §7 redirected to `codegenie.hashing.content_hash_fd` (now lives in §0).
- §8 — `find_applicable` thin-wrapper around pure `_matches`.
- §9 — pure `_matches(skills, evidence)` function.
- §10 (was §9) — structlog event-name literals (unchanged).

### Files to touch table

- Added `src/codegenie/hashing.py` (modify, additive — `content_hash_fd`).
- Added `tests/unit/test_hashing.py` (modify, additive — parity tests for new symbol).
- Split `tests/unit/skills/test_loader.py` from `tests/unit/skills/test_no_direct_yaml_import.py` (AC-24) and `tests/unit/skills/test_no_direct_blake3_import.py` (AC-25).

### Notes for the implementer

Appended `### Design-pattern notes (added by validator 2026-05-15)` section with eleven paragraphs:
- Hashing chokepoint extension (Open/Closed).
- Functional-core / imperative-shell split (recommended; not AC-mandated).
- Tier typing (`Literal`, not `int` indices) — ADR-0033 §3 framing.
- `SkillsLoadError` discriminated union vs marker — convention for forward loaders.
- Primitive obsession on `applies_to_*` — ADR-0033 §1 framing.
- `EvidenceQuery` over `set[str]` — illegal-states-unrepresentable framing.
- `["*"]` wildcard sentinel — CLAUDE.md convention.
- Three-tier order is ADR-amend-gated — intentional friction.
- `unsafe_yaml` umbrella — operational honesty.
- `body_blake3` format pin — fail-loud.
- No `O_NOFOLLOW` defense-in-depth via `safe_yaml.load` — load-bearing flag at the SKILL.md open.
- TOCTOU `rglob` is not a snapshot.
- Same-tier collisions exist too.

## Final verdict

**HARDENED.** Story is ready for `phase-story-executor`. Twelve ACs added, six strengthened. Implementation outline rewritten to specify the hashing-chokepoint extension and the typed-tier discipline. Design-pattern Notes paragraphs added covering functional-core split, primitive-obsession remedies, ADR-amend-gated extension friction, and the convention-forward distinction between single-file marker loaders (`TCCMLoader`) and multi-file Pydantic-union loaders (this story).

The patterns that make this story *easy to maintain and extend by addition*:

1. **`codegenie.hashing.content_hash_fd` extension** — adding the streaming-hash capability is a single new function, zero edits to existing call sites. Future fd-streaming callers (`SBOM`, `runtime_trace` blob hashing in Phase 5+) reuse it.
2. **`Tier` Literal + `_TIERS` ordering constant** — adding a fourth tier is an ADR-amend (intentional friction) + Literal extension + `_TIERS` tuple element. No edits to merge logic, no edits to test fixtures (parameterized).
3. **`@register_index_freshness_check` precedent not applicable here** (skills aren't index sources), but the same Open/Closed pattern applies: extending Skill validation rules in Phase 4+ adds new registry-decorated functions, never edits `Skill` model.
4. **`EvidenceQuery` typed surface** — Phase 4+ planners produce queries; the typed signature documents what evidence the loader sees and prevents future callers from passing flat string sets.
5. **`SkillsLoadError` discriminated union** — adding a sixth `reason` is a new Pydantic class + a Literal-extension + a new variant in the `Annotated[Union[...]]`. The `assert_never` in `_load_one_skill`'s error-classification step (recommended in Notes via functional-core split) forces exhaustive matching at compile time.
6. **Pure `_matches` function** — adding fancier matching semantics (e.g., versioned skill applicability, deprecation) is a new pure function or an extension of `_matches`; the loader itself doesn't change.

These are the load-bearing extension points the validator's design-patterns critic surfaced and the synthesizer promoted to ACs or Notes.
