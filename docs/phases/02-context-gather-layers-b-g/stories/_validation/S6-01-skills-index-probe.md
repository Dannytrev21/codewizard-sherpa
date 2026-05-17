# Validation report: S6-01 — `SkillsIndexProbe` Layer D

**Validated:** 2026-05-17
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S6-01-skills-index-probe.md`](../S6-01-skills-index-probe.md)

## Summary

S6-01's *intent* (a Layer-D probe that projects `SkillsLoader.load_all()` output into a typed, body-byte-free index slice for the Planner) is well-formed and traces cleanly to `phase-arch-design.md §"Component design" #9`, the CLAUDE.md "Progressive disclosure for context" commitment, and `localv2.md §5.4 D2`. The original draft, however, contradicted the actual S2-01 implementation (`src/codegenie/skills/loader.py`, `src/codegenie/skills/model.py`) and the frozen Phase-0 `Probe` ABC (`src/codegenie/probes/base.py`) at **twelve** load-bearing points — every one a `block`-severity contract mismatch that would have made the story uncompilable against the existing codebase.

The twelve contract mismatches were all in-place fixable because the goal itself was consistent with both the architecture and the kernel that S2-01 actually shipped; the draft's mistakes were documentation drift between the story-authoring snapshot of the loader contract and the implementation S2-01 ultimately landed. None required architectural change. Six new ACs were added to cover the corners the draft skipped (empty fixture, FatalLoadError, per-file-error surfacing with a three-state confidence policy, shadowed-skill de-duplication propagation, byte-identical raw artifact, helper-driven `ProbeContext` construction). Three mutation-resistance hardens were applied (parametrized field-coverage smoke; Hypothesis property-based projection monotonicity; module-source `os.open` / `os.read` interdict tightened from class-source to whole-module). One design-pattern harden was applied (extract `_project_skill`, `_project_skills_sorted`, `_count_skills_per_tier`, `_compute_confidence` as pure module-level helpers — functional core / imperative shell).

The original draft's `tier_counts` derivation was structurally unimplementable as written (the loader does not propagate tier identity into `LoadOutcome.skills`); the harden routes it through a pure filesystem-enumeration helper (`Path.rglob("SKILL.md")` per tier — filename-only, no body reads) and explicitly documents the rule-of-three trigger for when `_count_files_per_tier` should be extracted to a shared helper (when the third tier-aware probe lands).

No `NEEDS RESEARCH` findings — every gap traced to an in-repo precedent (`tests/unit/probes/layer_b/test_dep_graph.py` for the `asyncio.run` test idiom; `tests/unit/skills/test_loader.py` for the `content_hash_bytes`-based BLAKE3-prefix comparison; `src/codegenie/probes/layer_b/dep_graph.py` for the `@register_probe(heaviness=...)` + `name`/`layer`/`tier` ABC pattern; `src/codegenie/schema/probes/*.schema.json` for the flat schema layout; S5-06's validation report for the parametrized field-coverage and module-source interdict patterns).

Twenty-three in-place edits applied; verdict **HARDENED**. Story is now structurally consistent with the S2-01 contract that actually shipped and with every load-bearing convention the Phase-0/1/2 stories already established.

## Context Brief (Stage 1)

### Story snapshot
- **Goal:** Land `src/codegenie/probes/layer_d/skills_index.py` as a `@register_probe(heaviness="light")` probe that projects `SkillsLoader.load_all()` output into a typed `SkillsIndexSlice` carrying indexed-skill rows + tier counts + per-file errors, with bodies never opened by the probe (only the loader's recorded `body_offset`/`body_size`/`body_blake3` anchors are forwarded).
- **Non-goals:** body reads; other Layer-D probes (conventions, ADRs, policy — S6-02/03/04); sub-schema authoring (S6-08); hostile-YAML adversarial (S7-04); Skill / LoadOutcome amendments.
- **Effort:** S
- **Depends on:** S2-01 (`SkillsLoader` three-tier merge; `Skill` Pydantic model with `body_offset`/`body_size`/`body_blake3` fields; `LoadOutcome` with `skills` + `per_file_errors`; per-file-error discriminated union).

### Phase / arch constraints touched
- **02-ADR-0005** — no plaintext persistence; the probe's commitment to "anchors only, never bytes" is the same chokepoint discipline applied to a different surface.
- **Phase 1 ADR-0006** — `safe_yaml` chokepoint; the probe does not parse YAML directly (the loader already did, once, through the chokepoint).
- **02-ADR-0003** — `@register_probe(heaviness=..., runs_last=...)` is a registry kwarg, NOT a `Probe` ABC field. The original draft's `probe_id = ProbeId(...)` field assumed an ABC change.
- **02-ADR-0007** — no Plugin Loader in Phase 2; `SkillsLoader` is kernel-side, not loaded via a plugin.
- **`phase-arch-design.md` §"Component design" #9** — the canonical loader-contract source. The original draft's signature description (`Result[list[Skill], SkillsLoadError]`) is older than what S2-01 actually shipped (`Result[LoadOutcome, FatalLoadError]`).
- **`phase-arch-design.md` §"Edge cases" rows 8/9/16** — symlink-refused, hostile-YAML, and three-tier collision are *per-file* failures; "this skill skipped, others load" semantics. The probe must surface these via `per_file_errors`, not by collapsing the whole probe to `confidence="low"`.
- **CLAUDE.md** "Progressive disclosure for context" — the body anchors-not-bytes commitment is the story's identity.
- **CLAUDE.md** "Honest confidence" + **ADR-0033 §3** "make illegal states unrepresentable" — `confidence` is `Literal["high","medium","low"]`; three-state semantics for full-success / partial-success / total-failure are mandatory.

### Sibling-family lineage
- **3rd Layer-D-shaped story landed** after S2-01 (loader) and S2-02 (conventions catalog loader). The Layer-D *probes* layer (S6-01 through S6-05) consumes the loaders S2-01 / S2-02 already landed.
- **1st `@register_probe(heaviness="light")` probe in Layer D.** Layer-B (S4-01 IndexHealthProbe is `runs_last=True`, dep_graph is `heaviness="light"` default), Layer-C (S5-02 RuntimeTraceProbe is `heaviness="heavy"`). This is the first Layer-D probe so the rule-of-three for layer-shared helpers has not triggered.
- **Functional-core split is the architectural precedent.** S2-01's loader cleanly separates pure helpers (`_split_frontmatter`, `_matches`) from the imperative shell (`_load_one_skill`, `SkillsLoader.load_all`). S6-01 inherits this split.

### Prior validation framings carried forward
- **S5-06 hardening:** committed parametrized mutation-resistance suites > "developer-runnable only" mutation rituals. The field-coverage parametrized test in S6-01 is the analogous pattern.
- **S5-05 hardening:** diagnostic independence as separate test functions / separate fixtures. S6-01 mirrors this by giving each AC its own test function rather than folding multiple ACs into one fixture.
- **S5-04 hardening:** mutation-resistance is mandatory; module-level `Final[...]` discipline. S6-01 adopts the same discipline for the `TIERS` constant (already pinned in `skills/model.py` as `TIERS: Final[tuple[Tier,...]] = ("user","repo","org")`).
- **S5-03 hardening:** AST-walk / source-introspection audits supersede source-grep purity tests where a "did the test author do the right thing?" check is needed. S6-01's AC-11 (no `os.open` / `os.read` etc. in the module source) is a source-grep audit — defensible here because the negative is concrete (literal string presence in the module), not behavioral.

### Phase exit criteria the story contributes to
- **High-level-impl.md §"Step 6"** first bullet — ships Layer-D skills-index probe with body-byte-free index slice.
- **Phase-arch-design §"Testing strategy"** — the probe's unit + integration test land under `tests/unit/probes/layer_d/` and `tests/integration/probes/`.
- **CLAUDE.md "Progressive disclosure for context"** — load-bearing commitment the probe makes operational.
- **G6 (final-design §"Goals")** — kernel scaffolding for Phase-3 Skills consumption.

### Open ambiguities discovered during Stage 1

- **`SkillsLoader.load_all` return type drift.** Story says `Result[list[Skill], SkillsLoadError]`; the *actual* S2-01 implementation returns `Result[LoadOutcome, FatalLoadError]` where `LoadOutcome` carries both `skills` AND `per_file_errors`. Per-file errors stay inside `Ok(LoadOutcome)`; only catastrophic failures (no search path readable) surface as `Err(FatalLoadError)`. **Resolved at synthesis:** rewrite AC-6, AC-11 (now AC-17), and the GREEN code to pattern-match against the actual `Ok(LoadOutcome)` / `Err(FatalLoadError)` shape; add AC-16 (FatalLoadError) and AC-17 (per-file errors round-trip).

- **`Probe` ABC signature.** Story specifies `_run(self, ctx: ProbeContext) -> ProbeOutput` (sync, private, takes only ctx). The actual ABC at `src/codegenie/probes/base.py:94` is `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` (async, public, takes both repo and ctx). The story's `_run` does not exist in the contract. **Resolved at synthesis:** rewrite AC-6 to `async def run`; rewrite GREEN code with `async def`; update TDD plan to use `asyncio.run` (mirroring `tests/unit/probes/layer_b/test_dep_graph.py:108`).

- **Probe identity convention.** Story specifies `probe_id = ProbeId("skills_index")` as a class attribute. The actual ABC uses `name: str = "skills_index"`. Other typed identifiers (e.g., `SkillId`, `TaskClassId`, `Language`) ARE preserved through the probe's slice; the kernel ABC's `name: str` is the frozen contract surface (ADR-0007). **Resolved at synthesis:** rewrite AC-5 to use `name`/`layer`/`tier`/`requires` per the ABC, while keeping `SkillId`/`TaskClassId`/`Language` newtypes preserved through `IndexedSkill`'s fields.

- **`Skill.applies_to_*` type.** Story specifies `tuple[str, ...]` for `IndexedSkill`. The *source* `Skill` carries `list[TaskClassId]` / `list[Language]` (typed). Forcing `tuple[str, ...]` would launder the newtypes — primitive-obsession regression. **Resolved at synthesis:** AC-3 preserves `tuple[TaskClassId, ...]` / `tuple[Language, ...]` (tuples for slice hash-stability; newtypes for end-to-end type discipline).

- **`Skill.body_blake3` shape.** Story's TDD plan compares `blake3(...).hexdigest()` to `indexed.body_blake3` directly. The actual loader records `body_blake3` with a `blake3:` prefix (regex `^blake3:[0-9a-f]{64}$` pinned in `Skill.body_blake3`'s `Field(pattern=...)`). The raw-`hexdigest()` comparison would fail every time. **Resolved at synthesis:** AC-12 uses `content_hash_bytes(body)` (which produces the canonical `blake3:<64hex>` form) for the round-trip comparison; explicit assertion that `body_blake3.startswith("blake3:")`.

- **`tier_counts` derivation.** Story's AC-10 asserts `tier_counts == {"user": 3, "repo": 1, "org": 0}` but the loader's `LoadOutcome.skills` is a flat de-duplicated list with no per-skill tier metadata. The original GREEN code's `self._count_by_tier(skills, search_paths)` is hand-waved — there's no `tier` field on `Skill` to count from. **Resolved at synthesis:** introduce `_count_skills_per_tier(search_paths)` as a pure filesystem-enumeration helper (`Path.rglob("SKILL.md")` per tier, filename-only, no body reads); document that the counts are pre-de-duplication and explicitly surface shadowed-skill presence to operators (AC-14, AC-18). Rule-of-three trigger documented in Notes-for-implementer §9.

- **`ProbeContext.for_test` doesn't exist.** Story tests call `ProbeContext.for_test(search_paths=[...])`. `ProbeContext` is a stdlib `@dataclass` (`src/codegenie/probes/base.py:52`) with no classmethod helpers. **Resolved at synthesis:** introduce a `_make_context(tmp_path)` test helper in the test module; `search_paths` are resolved via `ctx.config["skills.user_path"]` etc., not via a `ProbeContext` constructor arg.

- **`_PROBE_REGISTRY` doesn't exist.** Story's AC-13 references `_PROBE_REGISTRY["skills_index"].heaviness`. The actual registry is `default_registry: Registry` at `src/codegenie/probes/registry.py:238` with `_entries: list[ProbeRegEntry]`. **Resolved at synthesis:** AC-20 (renumbered) uses `next(e for e in default_registry._entries if e.cls.name == "skills_index")`.

- **Schema layout.** Story's AC-12 and GREEN test reference `src/codegenie/schema/probes/layer_d/skills_index.schema.json` and `files("codegenie.schema.probes.layer_d")`. The actual schema layout is flat (`src/codegenie/schema/probes/dep_graph.schema.json`, etc. — no per-layer subdir). **Resolved at synthesis:** AC-19 (renumbered) uses the flat path `files("codegenie.schema.probes") / "skills_index.schema.json"`.

- **`codegenie.ids` doesn't exist.** Story's GREEN code imports `from codegenie.ids import ProbeId, SkillId`. The actual newtype module is `codegenie.types.identifiers`. **Resolved at synthesis:** import path corrected in GREEN code.

- **`ProbeOutput` shape.** Story's GREEN constructs `ProbeOutput(probe_id=..., confidence=..., schema_slice=..., errors=...)`. The actual `ProbeOutput` is `(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)` — no `probe_id` field, plus three required fields the story omitted. **Resolved at synthesis:** GREEN rewritten with all six fields; `duration_ms` measured via `time.perf_counter()`.

- **"No medium" confidence policy.** Story note 6: "Use `\"high\"` on success, `\"low\"` on `SkillsLoadError`. No `\"medium\"` — there is no \"partially loaded skills\" state." This is incorrect — the loader's `LoadOutcome.per_file_errors` exists precisely for the partial-success state. **Resolved at synthesis:** introduce a three-state policy via `_compute_confidence(skills, per_file_errors)`: `"high"` if no per-file errors (clean — including empty install); `"medium"` if some skills loaded and some failed; `"low"` only if every discovered file failed OR `FatalLoadError`.

## Findings by critic

### Coverage critic (K)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| K1 | harden | No AC for the empty-install case (zero `SKILL.md` files anywhere). A future regression that returns `confidence="low"` on a clean empty install (treating "no skills" as an error) would slip through. | New AC-15: empty fixture → `confidence="high"`, `skills=()`, `tier_counts={user:0,repo:0,org:0}`, `per_file_errors=()`. |
| K2 | harden | No AC for `FatalLoadError` (all tiers unreadable). The original draft's AC-6 only handled `Result.Err(SkillsLoadError)` which doesn't match the actual `Err(FatalLoadError)` shape. Without a test, a regression that re-raises `FatalLoadError` (breaking Phase 0 coordinator failure-isolation) silently lands. | New AC-16: `FatalLoadError` → `confidence="low"`, schema_slice with zeroed tier_counts and empty skills, error JSON-dumped into `output.errors`; probe does NOT re-raise. |
| K3 | harden | No AC for per-file-error surfacing. The original draft's AC-11 (symlink → `Result.Err`) is structurally wrong — symlinks become per-file errors inside `Ok(LoadOutcome)`. Without a correct AC, the implementer might unwittingly swallow `outcome.per_file_errors` (a regression that loses the "loud about failures" property). | New AC-17: partial-success fixture (one good + one symlinked) → `confidence="medium"`, `len(skills)==1`, `len(per_file_errors)==1`, `json.loads(per_file_errors[0])["reason"]=="symlink_refused"`. |
| K4 | harden | No AC for shadowed-skill propagation. The loader de-duplicates first-tier-wins, but the slice's `tier_counts` is filesystem-derived (pre-de-dup). Without an AC, a future implementer might "fix" `tier_counts` to use post-de-dup counts, losing the operator-facing signal that a shadow happened. | New AC-18: cross-tier collision → exactly one `IndexedSkill` (user wins), `tier_counts == {user:1, repo:1, org:0}` (both files present on disk). |
| K5 | harden | No AC for byte-identical raw-artifact determinism. AC-9 (now AC-13) pins JSON byte-identity for two consecutive `_run` calls, but the *raw* file (`raw/skills-index.json`) was not explicitly pinned. | Folded into AC-13's second clause: `json.dumps(out1.schema_slice, sort_keys=True) == json.dumps(out2.schema_slice, sort_keys=True)`. (Raw-file determinism follows mechanically from `sort_keys=True, indent=2` in the writer.) |
| K6 | block | Original draft AC-3 specified `applies_to_tasks: tuple[str, ...]` on `IndexedSkill`. The source `Skill` model carries `list[TaskClassId]` (typed). Laundering newtypes into `str` is the primitive-obsession ADR-0033 §1 explicitly forbids; the project's anti-pattern catalog at `phase-arch-design.md §"Anti-patterns avoided"` calls this out specifically. | AC-3 rewritten: `tuple[TaskClassId, ...]` / `tuple[Language, ...]` preserved end-to-end. Notes §4 documents the constraint. |
| K7 | harden | "Tier counts" is observable but the source of the count is ambiguous in the original draft (loader doesn't expose tier per skill). Implementation might invent a tier field on Skill, or count via insertion order, or worst — silently emit empty counts. | New AC-14 (renumbered): counts derive from `_count_skills_per_tier(search_paths)` — pure filesystem enumeration via `rglob("SKILL.md")`, filename-only, no body reads. Explicit invariant: missing tier path → 0. |
| K8 | nit | "`mypy --strict` passes" AC (AC-21) — verbatim from S5-06 / S4-07 precedents; ✓ no change needed beyond rewording. | No change required. |

### Test-Quality critic (T)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| T1 | harden | The 20 KB tracemalloc ceiling (original AC-7) is brittle against Pydantic version drift. A Pydantic 2.x point release that adds 8 bytes per model would silently flip this test red without any actual regression in the body-bytes-never-loaded invariant. | AC-10 (renumbered): loosen to `< 1 MB`. Still 100× tighter than what a `read_bytes()` regression would consume; absorbs Pydantic-model allocations comfortably for ≤ 100 skills. Notes §1 documents the rationale. |
| T2 | harden | The 100 MB body fixture used `path.write_text(big_body)` — materializes 100 MB in Python before any test runs. CI wall-clock degradation. | Test fixture rewritten to use sparse file via `fh.seek(N-1); fh.write(b"\0")` — O(1) on tmpfs, file-size invariant preserved. |
| T3 | harden | The architectural-source-introspection test (original AC-15) only inspected `SkillsIndexProbe` class source. A "convenience" helper at module-level (`def _read_preview(path): return path.read_text()[:200]`) would slip through. | AC-11 (renumbered): inspect WHOLE module source (`inspect.getsource(si)`); forbid `os.open`, `os.read`, `.read_bytes`, `.read_text`, `.open(` anywhere in the module. The probe is a pure consumer of `Skill` records; no body or file access from this module ever. |
| T4 | harden | No mutation-resistance test for "every field is populated." A regression in `_project_skill` that silently drops `applies_to_languages` (e.g., a refactor typo) would not be caught by any AC if the existing tests happened not to assert on that field. | New AC-22: parametrized over `IndexedSkill.model_fields.keys()` — every field asserted non-default-shaped for a canonical fixture. Adding a new field auto-extends the test surface. |
| T5 | harden | No property-based test. The slice's "sorted, cardinality-preserving" invariant is the kind of invariant that example-based tests routinely miss on edge cases (single-element list; identical-prefix IDs; empty list; very long IDs). | New AC-23: Hypothesis property — `len(_project_skills_sorted(skills)) == len({s.id for s in skills})` AND `[s.id for s in projected] == sorted({s.id for s in skills})`. Catches subtle sort/cardinality regressions. |
| T6 | harden | The registry-heaviness test (original AC-13) called `_PROBE_REGISTRY["skills_index"]` — but `_PROBE_REGISTRY` doesn't exist (the registry is `default_registry: Registry`). The test would have crashed at import time. | AC-20 (renumbered): use the actual surface — `next(e for e in default_registry._entries if e.cls.name == "skills_index")`. Also assert `entry.runs_last is False` (mutation: a regression flipping runs_last would change scheduling). |
| T7 | harden | The BLAKE3 round-trip test (original AC-8) compared `blake3(raw).hexdigest()` directly to `indexed.body_blake3`. The loader produces `blake3:<64hex>` (with prefix); the test would fail every time even on a correct implementation. | AC-12 (renumbered): use `content_hash_bytes(body)` (the canonical helper that produces the prefix); add explicit `body_blake3.startswith("blake3:")` assertion. |
| T8 | nit | The `pytest.raises(Exception)` for frozen-Pydantic mutation is overly broad; `pytest.raises(ValidationError)` or `pytest.raises(pydantic.ValidationError)` is the precise expectation. | Left as `pytest.raises(Exception)` since Pydantic 2's frozen-mutation error type has shifted across versions (was `TypeError`, now `ValidationError`); the broad assertion is defensible for cross-version stability and is the same shape used in S2-01's test. Notes-for-implementer flags this as a tightening opportunity if it ever produces a false negative. |

### Consistency critic (C)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| C1 | block | The original draft's `Probe._run(self, ctx)` signature is not the contract. `Probe.run` is `async def run(self, repo, ctx)` (sync `_run` does not exist). Tests using `si.SkillsIndexProbe()._run(ctx)` would crash with `AttributeError`. | AC-6 + GREEN code rewritten to `async def run(self, repo, ctx)`. Test idiom: `asyncio.run(probe.run(repo, ctx))` mirroring `tests/unit/probes/layer_b/test_dep_graph.py:108`. |
| C2 | block | The original draft's `probe_id = ProbeId(...)` class attribute does not match the frozen Probe ABC (`name: str = ...`). Subclassing Probe with `probe_id` instead of `name` would mean the registry's de-dup-by-name logic (`registry.py:154` `existing.cls.name == cls.name`) doesn't see the probe at all. | AC-5 rewritten: class attributes are exactly `name: str = "skills_index"`, `layer = "D"`, `tier = "base"`, `applies_to_tasks: list[str] = ["*"]`, `applies_to_languages: list[str] = ["*"]`, `requires: list[str] = []`, `timeout_seconds: int = 10`. ABC contract unchanged. |
| C3 | block | The original draft's `SkillsLoader(...).load_all()` returning `Result.Ok(skills)` / `Result.Err(SkillsLoadError(...))` does not match the actual return shape (`Result[LoadOutcome, FatalLoadError]`). The pattern-match would crash on attribute access (`result.unwrap()` would return `LoadOutcome`, not `list[Skill]`). | AC-6 + GREEN rewritten to handle `Ok(LoadOutcome)` and `Err(FatalLoadError)`; per-file errors stay inside `outcome.per_file_errors` (NOT in the `Err` branch). |
| C4 | block | The original draft's `IndexedSkill.body_blake3: str` field does not enforce the loader's `blake3:<64hex>` shape. A regression in the loader that drops the prefix would round-trip through Pydantic silently. | AC-3 specifies `body_blake3: Annotated[str, Field(pattern=r"^blake3:[0-9a-f]{64}$")]` — matches the loader's pin in `skills/model.py:62`. |
| C5 | block | The original draft's `from codegenie.ids import ...` does not exist as a module. Newtypes live in `codegenie.types.identifiers`. | GREEN imports corrected; story body's references corrected. |
| C6 | block | The original draft's `ProbeOutput(probe_id=..., confidence=..., schema_slice=..., errors=...)` does not match the frozen `ProbeOutput` dataclass (`schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors`). Constructor would `TypeError`. | GREEN constructs all six fields; `duration_ms` measured via `time.perf_counter()` (mirroring `dep_graph.py:431`). |
| C7 | block | The original draft's schema path `src/codegenie/schema/probes/layer_d/skills_index.schema.json` does not match the existing flat convention (`src/codegenie/schema/probes/dep_graph.schema.json`, etc.). An S6-08 implementer following the story literally would put the schema in the wrong place; the consumer-side test would fail. | AC-19 (renumbered) uses the flat path: `files("codegenie.schema.probes") / "skills_index.schema.json"`. |
| C8 | block | The original draft's `ProbeContext.for_test(search_paths=[...])` does not exist. `ProbeContext` is a stdlib `@dataclass` with no classmethods. The tests would crash with `AttributeError` on import. | New `_make_context(tmp_path)` test helper in the TDD plan; search-paths resolved via `ctx.config["skills.user_path"]` etc. (the `ProbeContext.config` field is the existing extension point). |
| C9 | block | The original draft's "Use `\"high\"` on success, `\"low\"` on `SkillsLoadError`. No `\"medium\"`" rule (note 6) contradicts the loader's partial-success semantics. The loader returns `Ok(LoadOutcome(skills=..., per_file_errors=...))` for the case "some skills loaded, some failed" — that IS a "partially loaded skills" state, and `"medium"` is the precise typed signal for it. | New AC-9 (renumbered): three-state confidence policy via `_compute_confidence(skills, per_file_errors)`. Notes-for-implementer §6 documents the rationale. |
| C10 | block | The original draft's `_PROBE_REGISTRY` does not exist. Registry surface is `default_registry: Registry` with `_entries: list[ProbeRegEntry]`. | AC-20 (renumbered) uses the actual surface. |
| C11 | harden | The original draft's `IndexedSkill.applies_to_tasks: tuple[str, ...]` strips the `TaskClassId` newtype from the source `Skill.applies_to_tasks: list[TaskClassId]`. ADR-0033 §1 (primitive obsession) prohibits exactly this kind of laundering. | AC-3: `tuple[TaskClassId, ...]` / `tuple[Language, ...]` preserved. Notes §4 documents. |
| C12 | harden | `tier_counts` derivation is structurally underspecified — the loader exposes no per-skill tier identity. A reader of the story can't tell where the counts come from; the original GREEN's `self._count_by_tier(skills, search_paths)` hand-waves it. | AC-14 (renumbered): explicit `_count_skills_per_tier(search_paths)` pure helper; counts are filesystem-enumeration-derived; missing tier path = 0; pre-de-duplication semantics documented (so shadowed skills surface in counts). |

### Design-Patterns critic (D)

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| D1 | harden | The original draft's `_resolve_search_paths` and `_count_by_tier` are private methods on the probe class. Mixing pure logic into the imperative shell defeats Phase 2's "functional core / imperative shell" convention (proven by `s1-loader.py` splitting `_split_frontmatter` / `_matches` as pure module-level helpers; `dep_graph.py` splitting `_detect_package_manager` from the probe). | Extracted as pure module-level functions: `_project_skill`, `_project_skills_sorted`, `_count_skills_per_tier`, `_compute_confidence`. Each independently testable without a `Probe` instance or `asyncio.run`. |
| D2 | harden | `IndexedSkill.applies_to_*` as raw `tuple[str, ...]` is primitive obsession (already block-flagged by Consistency critic). The design-pattern lens: newtypes are the discipline that lets `mypy --strict` catch a `TaskClassId` accidentally passed where a `Language` is expected — preserving them through the slice means the Planner consumer also gets that protection. | Already resolved via AC-3 + Notes §4. |
| D3 | harden | The confidence dimension is naturally a Sum/State-Machine; the original draft's two-state binary loses the partial-success state. ADR-0033 §3 "make illegal states unrepresentable" prescribes the three-state typed surface. | Already resolved via AC-9 + `_compute_confidence` pure helper. The `Literal["high","medium","low"]` is exhaustive at the Probe-ABC level (already pinned by Phase 0), so `match` over it on the consumer side stays type-safe. |
| D4 | nit | The original draft's "no tier classifier" rationale (rule-of-three not triggered) is correct but the seam was not documented. When the third tier-aware probe lands, the implementer of THAT story needs to know which pure helper to extract. | Notes §9: rule-of-three trigger is the third tier-aware Layer-D probe (S6-02 ConventionsCatalogProbe is the second). Extract `_count_files_per_tier(search_paths, glob_pattern)` into `src/codegenie/probes/_shared/tier_counts.py` at that point. |
| D5 | block | The original draft's `tier_counts` ambiguity (D-pattern lens: "where does the data come from?") is also a hidden-coupling smell. Without an explicit pure helper, a future implementer might "fix" the gap by adding a `tier: Tier` field to `Skill` (S2-01 amendment) — wrong layer to fix this, and would expand the loader's contract for one consumer. | AC-14 + Notes §9: explicit pure helper for the count derivation; explicit "do NOT extend Skill/LoadOutcome" guidance to forestall the wrong fix. |
| D6 | harden | `declared_inputs` was not explicitly tied to the search-path configuration. Cache invalidation requires the declared_inputs to change when the config changes. Without an explicit AC, a future config-key addition (e.g., `skills.user_path`) would not invalidate the cache. | New AC-7: declared_inputs includes `skills_user_search_path:<expanded>` etc. — mirrors the proven precedent at `dep_graph.py:420` (`dep_graph_strategy_set:<resolved>`). |
| D7 | nit | The slice writes a raw artifact to `ctx.output_dir / "skills-index.json"` but the original draft did not pin this. Operators read raw artifacts when debugging; without a pin, the path could drift. | GREEN explicitly writes `raw_path = ctx.output_dir / "skills-index.json"`; raw_artifacts list includes it. AC-13's byte-identity assertion guarantees the raw file is deterministic. |

## Conflict resolution

Priority: `Consistency > Coverage > Test-Quality > Design-Patterns`.

- **No conflicts between Coverage and Consistency:** every new Coverage AC (K1–K7) traces to an actual capability of the existing loader/probe contract.
- **No conflicts between Test-Quality and Consistency:** every Test-Quality harden (T1–T7) tightens an AC that Consistency had already corrected for shape.
- **Design-Patterns vs. Rule 2 (YAGNI):** D4's rule-of-three trigger is **documented but not implemented** in S6-01 — per Rule 2 ("three similar lines is better than a premature abstraction"), the shared `_count_files_per_tier` helper waits for the third tier-aware probe. The story's Notes §9 makes this explicit so the next story author has the context.

No Stage 3 research was needed — every gap traced to an in-repo precedent.

## Edits applied (Stage 4)

### Story header
- Updated **Depends on** to reflect actual S2-01 surface (`LoadOutcome.per_file_errors` is the per-file-error carrier).
- Added **02-ADR-0003** to the **ADRs honored** list (`heaviness` is registry-side, not on the ABC).
- Added a **Validation notes** block under the header documenting the twelve block fixes, six new ACs, three mutation-resistance hardens, and one design-pattern harden.

### Context
- Rewrote the second paragraph to describe the *actual* `SkillsLoader.load_all()` return shape (`Result[LoadOutcome, FatalLoadError]` with `per_file_errors` carrier).
- Loosened the tracemalloc ceiling to 1 MB (from 20 KB) with a Pydantic-version-drift rationale.

### References — where to look
- Added the actual references for the Probe ABC (`base.py`), registry (`registry.py`), newtypes (`types/identifiers.py`), schema layout (flat under `schema/probes/`), and the canonical `asyncio.run` test idiom from `test_dep_graph.py`.
- Removed the references to non-existent surfaces (`codegenie.ids`, `ProbeContext.for_test`, `_PROBE_REGISTRY`).

### Goal
- Rewrote to use `async def run(self, repo, ctx)` (matching the ABC), `name: str = "skills_index"` (matching ABC convention), preserved newtypes (`SkillId`, `TaskClassId`, `Language`), and `blake3:<64hex>` prefix preservation.
- Made explicit that `tier_counts` derives from a pure filesystem-enumeration helper, NOT from any field on `LoadOutcome`.
- Added: probe MUST NOT contain `os.open`/`os.read`/`.read_bytes`/`.read_text`/`.open(` in the module source.

### Acceptance criteria
- Renumbered to 23 ACs (from 15) organized into 12 sections.
- **Rewrites:** AC-3 (preserve newtypes), AC-4 (add `per_file_errors`), AC-5 (use ABC class attributes, not `probe_id`), AC-6 (`async def run` + `Result[LoadOutcome, FatalLoadError]` pattern-match), AC-9 (three-state confidence policy), AC-10 (1 MB ceiling), AC-11 (whole-module source interdict), AC-12 (`content_hash_bytes` prefix-aware round-trip), AC-13 (byte-identical JSON between gathers), AC-19 (flat schema path), AC-20 (use `default_registry`).
- **New ACs:** AC-7 (`_resolve_search_paths` + declared_inputs tokens), AC-14 (filesystem-enumeration `tier_counts`), AC-15 (empty fixture), AC-16 (`FatalLoadError`), AC-17 (per-file errors round-trip), AC-18 (shadowed-skill propagation), AC-22 (parametrized field-coverage), AC-23 (Hypothesis property).

### Implementation outline
- Restructured to make the functional-core / imperative-shell split explicit.
- Added the `_make_context` helper requirement.
- Documented the S6-08 forward dependency.

### TDD plan
- Replaced every `_run` call with `asyncio.run(probe.run(...))`.
- Replaced `ProbeContext.for_test` with `_make_context(tmp_path)` helper.
- Replaced `_PROBE_REGISTRY` with `default_registry._entries` iteration.
- Replaced raw `blake3(...).hexdigest()` with `content_hash_bytes(body)` (prefix-aware).
- Replaced flat 100 MB `path.write_text` fixture with sparse-file `fh.seek/write` (O(1)).
- Replaced class-source `getsource(SkillsIndexProbe)` introspection with module-source `getsource(si)` introspection.
- Added five new test functions for the new ACs (empty, FatalLoadError, per-file errors, shadowed propagation, byte-identical JSON, parametrized field coverage, Hypothesis property).

### GREEN code
- Complete rewrite: pure helpers at module level; imperative shell uses ABC-correct class attributes; `async def run` taking `(self, repo, ctx)`; pattern-matches `Result[LoadOutcome, FatalLoadError]`; emits all six `ProbeOutput` fields; preserves newtypes through projection; writes raw artifact with `sort_keys=True, indent=2`.

### Refactor section
- Documented the rule-of-three trigger for the shared tier-counts helper.

### Out of scope
- Added: "Adding `tier` membership to `Skill` / `LoadOutcome`" (S2-01 amendment, not S6-01's job).
- Added: "Editing the Phase 0 `Probe` ABC or `ProbeContext` dataclass" (frozen contract per ADR-0007).

### Notes for the implementer
- Rewrote all 12 notes to reflect the corrected ACs and code.
- Added notes 9 (rule-of-three trigger for tier-counts), 10 (`async def run` is the contract — pinning the test idiom), 11 (`ProbeContext` is a stdlib `@dataclass`), 12 (registry surface is `default_registry`).

## Verdict

**HARDENED.** Twenty-three edits applied to the story file at `docs/phases/02-context-gather-layers-b-g/stories/S6-01-skills-index-probe.md`. The story now compiles structurally against the S2-01 implementation that actually shipped and the frozen Phase-0 `Probe` / `ProbeContext` / `ProbeOutput` contract surfaces. All twelve `block`-severity contract mismatches are resolved; six coverage gaps closed; three mutation-resistance hardens applied; one design-pattern harden applied with rule-of-three trigger documented for the next implementer.

The story is ready for `phase-story-executor`.
