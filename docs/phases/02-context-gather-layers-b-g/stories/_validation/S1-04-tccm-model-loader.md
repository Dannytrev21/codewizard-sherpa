# Validation report — S1-04 `TCCM` Pydantic model + `DerivedQuery` five variants + `TCCMLoader`

**Story:** [`../S1-04-tccm-model-loader.md`](../S1-04-tccm-model-loader.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story implements `codegenie.tccm` — the `TCCM` Pydantic model, the five-variant `DerivedQuery` discriminated union (`ConsumersOf | ProducersOf | ReverseLookup | RefsTo | TestsExercising`, no `Unknown`), and `TCCMLoader.load(path) -> Result[TCCM, TCCMLoadError]` routing every file read through Phase 1's `safe_yaml.load` chokepoint. All references trace cleanly to `02-ADR-0007`, `phase-arch-design.md §"Component design" #8` / §"Data model" lines 710–722, production ADR-0029 (TCCM purpose), and production ADR-0030 (the five derived-query primitives).

The draft was structurally sound — the discriminated-union shape is correct, the refusal of an `Unknown` fallback variant is correct, the `safe_yaml.load` chokepoint commitment is correct, and `TCCMLoader` is pure-data-at-`__init__` — but had **three block-tier executor-halt risks** and **eleven harden-tier gaps** that would have let a wrong implementation slip past the executor's Validator pass. This is the **third Pydantic discriminated-union family** in Phase 2 (after S1-01 `IndexFreshness` and S1-03 `AdapterConfidence`); the validator's standing job is to enforce the symmetric discipline those siblings ratified.

Twenty-two ACs and substantial Notes-for-implementer text added; the Implementation outline, Files-to-touch table, Red/Green/Refactor sketches, and references section were all edited in place. Story is now ready for `phase-story-executor`. Stage 3 research skipped (no `NEEDS RESEARCH` findings — every gap was answerable from arch + ADR-0007 + ADR-0029 + ADR-0030 + the S1-01 / S1-03 validation precedents + verified repo state).

## Context Brief (Stage 1)

- **Goal as written:** Implement `src/codegenie/tccm/{__init__.py,model.py,queries.py,loader.py}` — `TCCM` Pydantic `frozen=True, extra="forbid"` model, `DerivedQuery` as a five-variant Pydantic discriminated union (no `Unknown`), `TCCMLoader.load(path) -> Result[TCCM, TCCMLoadError]` routing every YAML read through `safe_yaml.load`.
- **Phase 2 exit criteria touched:** Plugin scaffolding ships as documentation-as-code (kernel-only); Phase 3 inherits typed surfaces day-1 (`phase-arch-design.md §"Integration with Phase 3"`); 02-ADR-0007 "Phase 3 first plugin doubles as proof the loader works" survives because S1-04 ships the schema + loader skeleton, not a plugin loader.
- **Load-bearing commitments touched:**
  - CLAUDE.md §"No LLM anywhere in the gather pipeline" — TCCM is a Pydantic schema; the loader is deterministic. ✓
  - CLAUDE.md §"Facts, not judgments" — TCCM is data; the Bundle Builder (Phase 8) is where judgments live. ✓
  - CLAUDE.md §"Honest confidence" — `confidence_floor: AdapterConfidence` is the typed surface for the floor.
  - CLAUDE.md §"Extension by addition" — adding a sixth `DerivedQuery` is deliberately ADR-amendment-gated (not pure addition); the friction is intentional and recorded in Notes.
  - `02-ADR-0007 §Decision/§Consequences` — Phase 2 ships TCCM schema + loader; no plugin loader; reference TCCM lives at `docs/phases/02-context-gather-layers-b-g/_reference-tccm/`.
  - `phase-arch-design.md §"Data model"` lines 710–722 — pins exact Pydantic shape (`frozen=True, extra="forbid"`, `Literal` discriminators).
  - `phase-arch-design.md §"Design patterns applied"` row "Reference TCCM" — under `docs/_reference-tccm/`, not `plugins/`. (Story copy edited to use the phase-scoped path that ADR-0007 §Consequences ratifies.)
  - `phase-arch-design.md §"Anti-patterns avoided"` rows: side-effects-in-constructors (5), `model_construct` bypass (12), stringly-typed identifiers (4), tag-and-dispatch without tagged union (7), untyped `dict[str, Any]` (5).
  - Production ADR-0029 — the manifest's purpose.
  - Production ADR-0030 — five-primitive constraint; no `Unknown`; ADR-amend on a sixth. **Note:** ADR-0030's named primitives (`dep_graph.consumers`, `reverse_lookup`, `transitive_callers`, `scip.refs`, `tests_exercising`) do not perfectly match the phase-arch's five-tuple (`ConsumersOf | ProducersOf | ReverseLookup | RefsTo | TestsExercising`). S1-04 implements the phase-arch literal; reconciliation is documented as an out-of-scope architectural note.
- **Open/Closed boundaries:**
  - New `DerivedQuery` variant → ADR-amendment to ADR-0030 + new variant class + Union extension (intentional friction).
  - New TCCM field → `schema_version: Literal["1"]` is the upgrade door; new field requires `schema_version: Literal["1", "2"]` + loader dispatch.
  - New `LoaderReason` → extend `Literal[...]` alias + extend `_classify` + extend docstring table. Below rule-of-three for a full StrEnum / dispatch object.
- **Sibling-family lineage:** **Third** Pydantic-discriminated-union family in Phase 2 (after S1-01 `IndexFreshness` and S1-03 `AdapterConfidence`). Symmetric discipline carries forward: discriminator-string pinning, JSON-shape pinning, `extra="forbid"` per-variant rejection, frozen runtime-mutation test, exhaustive `match` + `assert_never`, `model_construct` source scan, module-purity test, `__all__` exact-set test.
- **Prior validation history:** S1-01 and S1-03 reports cross-referenced extensively. F1 (Result type missing), F2 (`safe_yaml.load` signature), F3 (marker construction) are new findings unique to this story (loader-shaped concerns; S1-01 and S1-03 were pure-typing stories with no I/O).
- **Open ambiguities resolved before Stage 2:**
  - `Result[T, E]` — does not exist in repo (grep confirmed). S2-01 declares S1-04 as the home. Resolution: S1-04 ships `src/codegenie/result.py`.
  - `ProbeId` — does not exist in repo (grep confirmed). Resolution: S1-04 routes the addition through S1-05; if implementer encounters a missing `ProbeId`, the fix is to extend S1-05's deliverable, not to silently declare a local alias.
  - `_reference-tccm` path — ADR-0007 §Consequences wins (phase-scoped path). Story copy edited.
  - ADR-0030 filename — actual file is `0030-graph-aware-context-queries.md`. Story reference updated.

## Stage 2 — critic reports

### Coverage (verdict: COVERAGE-HARDEN — 17 findings)

**Block-tier:**
- **F1 (block) — `Result` type does not exist in the codebase.** `grep -rn "class Result|is_ok|unwrap" src/codegenie/` returned zero hits. The sketch's `from codegenie._result import Result` will `ImportError`; AC-9's tuple fallback contradicts every TDD-plan test (all use `.is_ok() / .unwrap()`). S2-01's `Depends on: S1-04` explicitly names S1-04 as the home. **Fix:** S1-04 now ships `src/codegenie/result.py` with AC-0a..AC-0e; AC-9 commits to the typed Result; the tuple-fallback alternative is withdrawn.
- **F2 (block) — `safe_yaml.load(path)` will `TypeError`.** Verified signature is `load(path, *, max_bytes, max_depth=64)` with `max_bytes` required keyword-only; every Phase 1 caller passes a module-scope `Final[int]` constant. **Fix:** AC-5 now mandates `_TCCM_MAX_BYTES: Final[int] = 64 * 1024` declared at module scope and passed as `safe_yaml.load(path, max_bytes=_TCCM_MAX_BYTES)`; chokepoint monkeypatch test asserts the keyword reaches `safe_yaml.load`.

**Harden-tier (sibling-family symmetric discipline):**
- F3 — Discriminator-string literal pin missing (symmetric swap mutation). **Fix:** AC-12 + `test_compute_discriminator_strings_are_exactly_pinned`.
- F4 — JSON-shape pin missing (`compute → tag` rename mutation). **Fix:** AC-13 + parametrized `test_derived_query_json_shape_pinned`.
- F5 — No frozen runtime-immutability assertion for `TCCM` and variants. **Fix:** AC-14.
- F6 — Per-variant `extra="forbid"` rejection of foreign payload fields not asserted. **Fix:** AC-15 (matrix of variant × foreign-field) + `test_tccm_rejects_extra_field`.
- F7 — No exhaustive `match` + `assert_never` over `DerivedQuery` (sum-type discipline). **Fix:** AC-16.
- F8 — `model_construct` source-scan ban not in-story (only S1-11 deferred). **Fix:** AC-17.
- F9 — Module-purity invariant for `model.py` / `queries.py` unasserted. **Fix:** AC-18.
- F10 — `__all__` exact-set test missing. **Fix:** AC-19 + AC-0b.
- F11 — `AC-7 confidence_floor` covers only Trusted/Degraded; missing Unavailable. **Fix:** AC-21 parametrized over all three.
- F12 — `unknown_query_primitive` translation brittle to Pydantic version + missing edge cases (missing `compute:`, non-string `compute:`). **Fix:** AC-8 uses prefix pin instead of substring; loader docstring documents translation table; cross-version regression is `fail-loud-fix-translation-not-test` (Notes).
- F13 — Edge cases: empty `derived_queries`, empty `required_probes/skills`, duplicate entries — undeclared. **Fix:** AC-24 with three explicit acceptance decisions.
- F14 — ADR-0030 sixth-primitive trapdoor under-tested. **Fix:** subsumed by AC-16 (`assert_never`) + Notes-for-implementer.
- F15 — `ProbeId` source unverified. **Fix:** AC-2 rewritten with hard precondition routing through S1-05; Notes paragraph + Files-to-touch row.
- F16 (nit) — Wrong ADR-0030 filename. **Fix:** Reference path updated.
- F17 (nit) — Refactor mentions audit log without backing AC. **Fix:** AC-22.

### Test quality (verdict: TESTS-HARDEN — 11 findings; mutation analysis)

19-row mutation table; eight mutations slip past the draft:

| # | Wrong impl | Caught by draft? | Closure |
|---|---|---|---|
| 1 | Drop `frozen=True` from `TCCM` | No | AC-14 |
| 2 | Drop `frozen=True` from one variant | No | AC-14 (parametrized) |
| 3 | Drop `extra="forbid"` from `TCCM` | No | AC-15 (TCCM rejects-extra-field arm) |
| 4 | Drop `extra="forbid"` from one variant | No | AC-15 (per-variant matrix) |
| 5 | Symmetric swap `ConsumersOf.compute` ↔ `ProducersOf.compute` | No (round-trip identity tolerates) | AC-12 |
| 6 | Symmetric rename `compute → tag` | No | AC-13 |
| 7 | Add `Unknown(BaseModel): compute: str` fallback | Caught (draft AC-8) | — |
| 8 | `model_construct()` inside loader | No | AC-17 |
| 9 | Loader bypasses `safe_yaml` via `Path.read_text` | Caught only by monkeypatch spy IF spy intercepts; AST-fragile | AC-23 (AST source-scan) |
| 10 | Loader always returns `reason="schema"` | Caught (draft AC-8) | — |
| 11 | Loader misses `DepthCapExceeded` | No (only `MalformedYAMLError` exercised) | AC-20 (parametrized) |
| 12 | Loader omits `max_bytes=` | Fails loud as TypeError but no positive assertion | AC-5 monkeypatch arm asserts `max_bytes >= 10_240` |
| 13 | Pydantic upgrade changes error code | Fails loud via AC-8 prefix pin | — |
| 14 | Field rename (`pkg` → `package`) | Caught at parametrize ctor import-time | — |
| 15 | Variants share `value: str` payload | Caught at parametrize ctor import-time + AC-13 JSON-shape pin | — |
| 16 | `confidence_floor: Any` (Unavailable never exercised) | No | AC-21 parametrized |
| 17 | `TCCMLoadError(reason: str)` structured init | No | AC-25 (markers-only structural test) |
| 18 | Loader logs secrets in audit | No | AC-22 (field-allowlist test) |
| 19 | Drop `Annotated[Union, Field(discriminator)]` → plain `Union` | Caught (AC-6 type-of-decoded assertion) | — |

Additional test-quality concerns:
- Monkeypatch chokepoint test is fragile to import shadowing (`from codegenie.parsers.safe_yaml import load`). **Fix:** AC-23 AST source-scan as durable enforcement.
- AC-8 `"unknown_query_primitive" in err.args[0]` is borderline-tautological vs the `"schema"` substring. **Fix:** prefix pin (`startswith("unknown_query_primitive:")`).
- Property-based test (Hypothesis) for the Cartesian product of variants × random ASCII payloads closes mutations 2/5/6/19 in one test. **Fix:** `tests/property/test_tccm_roundtrip.py` (AC-11).
- Audit-log AC was named in Refactor but unverified. **Fix:** AC-22 with `structlog.testing.capture_logs` (S2-01 precedent).

### Consistency (verdict: CONSISTENCY-HARDEN — 15 findings; 3 of original RESCUE-tier resolved by synthesizer)

- F1, F2, F3 (block-tier) — Resolved above.
- F4 — `docs/_reference-tccm/` vs `docs/phases/02-context-gather-layers-b-g/_reference-tccm/`. ADR-0007 §Consequences ratifies the phase-scoped path. **Fix:** story Context edited; informational note flagged to S2-03.
- F5 — `ProbeId` source. **Fix:** AC-2 rewrite + Notes.
- F6 — `TaskClassId` / `SkillId` deps on S1-05. **Verified clean.**
- F7 — ADR-0030 vs phase-arch primitive-name disagreement (`ProducersOf` absent from ADR-0030; `transitive_callers` absent from story). **Resolution:** S1-04 implements phase-arch literal (phase-arch is the immediate source of truth for Phase 2); reconciliation surfaced as an out-of-scope architectural note in References + Notes-for-implementer.
- F8 — `Unknown` variant refusal. **Verified clean** (story Notes already forbid).
- F9 — Audit log claim without backing AC. **Fix:** AC-22.
- F10 — `forbidden-patterns` extension to `tccm/**`. **Verified clean** (S1-11's scope) + AC-17 in-story enforcement as belt-and-braces.
- F11 — No-LLM commitment. **Verified clean.**
- F12 — Extension-by-addition tension. **Fix:** Notes-for-implementer paragraph documents intentional friction.
- F13 — `mypy --warn-unreachable` for `tccm/**`. **Verified clean** (S1-11's scope).
- F14 — `pyproject.toml` overrides. **Verified clean** (S1-11's scope).
- F15 — S1-01 / S1-03 sibling-family discipline. **Fix:** AC-12, AC-13, AC-17, AC-18, AC-19, AC-21 (all symmetric carry-forwards).

### Design patterns (verdict: DESIGN-HARDEN with Notes extensions — 11 observations)

- Sum type / discriminated union — correctly modeled. ✓
- Tagged-union closure (no `Unknown`) — observable via AC-8 (loader emits `unknown_query_primitive`). ✓
- Smart constructor via `model_validate` — `model_construct` ban (AC-17) defends. ✓
- Functional core / imperative shell — `model.py` / `queries.py` pure (AC-18); `loader.py` impure. ✓ Notes paragraph documents.
- Open/Closed at file boundary for `LoaderReason` — at three reasons, Literal type alias suffices; full registry is YAGNI. Notes paragraph.
- Primitive obsession — `pkg` / `module` / `symbol` deliberately NOT newtyped (S1-03 precedent). Notes paragraph.
- Markers-only error — bare `TCCMLoadError` (AC-25 structural test). ✓
- Pattern soup — none detected; story is appropriately under-abstracted.
- Hidden state — `TCCMLoader.__init__` is implicit (no `__init__` declared). Notes paragraph.
- Composition over inheritance — no shared loader base class. Notes paragraph.
- Schema before consumer — S2-03 reference-TCCM consumes. ✓ (Out of scope §1.)
- Dependency inversion — direct `safe_yaml.load` dep is correct per "one chokepoint" arch commitment. No injection. ✓

Promoted to Notes-for-implementer (not ACs — pattern names are not testable, but framings prevent the next implementer from misreading the design):

1. `Result[T, E]` is shipped by this story.
2. `ProbeId` precondition routing through S1-05.
3. `LoaderReason: Literal[...]` typed alias.
4. `unknown_query_primitive` translation is brittle — fix the translation, not the test.
5. `safe_yaml.load` is the only file-read path.
6. Markers-only invariant.
7. `schema_version: Literal["1"]` upgrade door.
8. Five variants, no `Unknown`.
9. Union-extension friction is intentional.
10. Deliberate non-newtyping of `pkg` / `module` / `symbol`.
11. `TCCMLoader` no `__init__` discipline.
12. Composition over inheritance — no shared loader base.
13. Phase-arch ↔ ADR-0030 reconciliation out of scope.
14. Audit log allowlist.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap was answerable from arch + ADR-0007 + ADR-0029 + ADR-0030 + S1-01 / S1-03 validation precedents + verified repo state (Bash/Grep). The Hypothesis idiom for `Annotated[Union, Field(discriminator=...)]` strategies (`st.one_of(st.builds(...), ...)`) is library-canonical; no external research needed.

## Stage 4 — Synthesizer edits applied

Conflict resolution: no Consistency-vs-Coverage conflicts (Consistency dominates; nothing required averaging). The Design-Patterns critic's "extract a typed translation table" suggestion was *rejected* under Rule 2 — three reasons is below the rule-of-three; a Literal type alias suffices and is recorded as a Notes paragraph instead.

**Edits to the story (in order):**

1. **Validation notes block** appended after the header — documents every change, severity, and rationale, and points to this report.
2. **Status** annotated with `· HARDENED 2026-05-15` and effort bumped `M → M-to-L` to reflect the lifted `Result` deliverable.
3. **Context** paragraph — reference-TCCM path corrected; new paragraph on `Result[T, E]` deliverable scope.
4. **References — where to look**:
   - Production ADR-0030 filename corrected (`0030-graph-aware-context-queries.md`).
   - Note on ADR-0030 ↔ phase-arch primitive-name disagreement added.
   - `safe_yaml.load` signature note (`max_bytes` required keyword) added.
   - Markers-only convention spelled out.
   - `ProbeId` precondition routing through S1-05 named.
   - S1-01 sibling-family discipline cross-referenced.
   - New section: "New code shipped by this story" → `src/codegenie/result.py`.
5. **Goal** — extended to name the `Result[T, E]` deliverable + the explicit `max_bytes` cap.
6. **Acceptance criteria** — fully rewritten:
   - **AC-0a..AC-0e** (new): Result[T, E] sum type — Ok/Err, methods, immutability, round-trip, `__all__`, module purity.
   - **AC-1** — `__all__` exact-set test promoted to AC.
   - **AC-2** — `ProbeId` precondition rewritten; routes through S1-05.
   - **AC-3** — variant payload-field set spelled out explicitly per primitive; references phase-arch line 721 + the open ADR-0030 reconciliation note.
   - **AC-4** — marker construction switched to positional `args[0]` prefix (matches Phase 1 marker convention); kwarg form removed.
   - **AC-5** — `_TCCM_MAX_BYTES` pinned; explicit `max_bytes=` kwarg required; ban on `safe_yaml.load_all` added.
   - **AC-6** — parametrized over all five variants; equality + `type(decoded) is type(q)` both required.
   - **AC-7** — TCCM round-trip; variant-set coverage moved to AC-21.
   - **AC-8** — prefix pin (`startswith("unknown_query_primitive:")`); explicit anti-tautology note.
   - **AC-9** — tuple-fallback withdrawn; commits to Result type shipped by AC-0a.
   - **AC-10, AC-11** — extended scope to `tests/unit/result/` + `tests/property/`.
   - **AC-12..AC-25** (new): discriminator-string pin; JSON-shape pin; runtime immutability; per-variant `extra=forbid`; exhaustive `match` + `assert_never`; `model_construct` source-scan; module-purity AST scan; `__all__` exact-set; parse-error parametrized; `confidence_floor` parametrized over all three variants; audit log emission; chokepoint AST source-scan; empty-collection / duplicate-entries decisions; markers-only structural test.
7. **Implementation outline** — reordered (Result first; S1-05 precondition step; `_TCCM_MAX_BYTES` + `LoaderReason: Literal[...]` named; audit emission step added).
8. **TDD plan — Red** — full Red test sketch rewritten covering all AC-0..AC-25; includes the Hypothesis property test and the AST scans.
9. **TDD plan — Green** — `result.py` skeleton added; `loader.py` skeleton updated to pass `max_bytes=`, declare `LoaderReason: TypeAlias`, factor out `_classify`, and emit audit log on every exit.
10. **TDD plan — Refactor** — public contract pinned to the three reason prefixes; audit-log field allowlist explicit; ruff/mypy/pytest command lines updated.
11. **Files to touch** — extended (result.py, types/identifiers.py (S1-05 hand-off), tests/unit/result/, tests/property/, three tccm test files: test_loader.py / test_queries.py / test_model.py).
12. **Notes for the implementer** — fourteen paragraphs (was six); each prevents a specific class of executor mistake the critics surfaced.

**No edits made to:**
- Story **Goal** scope expansion beyond Result (not Coverage's intent to widen scope; surfacing as a precondition violation if S1-05's `ProbeId` doesn't land is correct per the validator's anti-goals — does not silently fold improvements outside the story's scope).
- The deliberate non-reconciliation of ADR-0030 vs phase-arch (out of S1-04's authority; recorded as architectural note).

## Verdict — HARDENED

The story is ready for `phase-story-executor`. The third Pydantic-discriminated-union family in Phase 2 inherits the symmetric discipline S1-01 and S1-03 ratified; three executor-halt block-tier risks were resolved (Result type, `safe_yaml.load` signature, marker construction style); fourteen Notes-for-implementer paragraphs prevent the most common executor mistakes; AC count grew from 11 to 30 (AC-0a..AC-0e + AC-1..AC-25). No follow-up validation pass needed. Implementer should be aware that:

1. **`Result[T, E]` is now in scope** — S1-04 ships `src/codegenie/result.py` for use by S2-01, S2-02, and itself.
2. **`ProbeId` requires S1-05** — if `S1-05` hasn't landed `ProbeId`, S1-04 surfaces a precondition violation and extends S1-05's scope; do not declare a local alias.
3. **ADR-0030 ↔ phase-arch primitive disagreement** is an open architectural note; S1-04 implements the phase-arch literal (five variants per line 721) and surfaces the reconciliation question to the next architecture review.
4. **Markers-only invariant** for `TCCMLoadError` — bare marker, positional `args[0]` prefix-encoded reason, no `__init__`.
5. **All sibling-family symmetric tests** (discriminator pin, JSON-shape pin, runtime immutability, per-variant extra=forbid, exhaustive match, model_construct scan, module purity, __all__ exact-set) are in-story enforcement; do not defer any to S1-11.
