# Validation report — S2-02 `ConventionsCatalogLoader` with discriminated-union pattern types

**Story:** [`../S2-02-conventions-catalog-loader.md`](../S2-02-conventions-catalog-loader.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story ships `src/codegenie/conventions/` (four files: `__init__.py`, `model.py`, `loader.py`, `catalog.py`, plus a single-helper `_io.py`) and a single-symbol additive extension to `src/codegenie/types/identifiers.py` (adds `ConventionId`). The core shape — Pydantic discriminated union over four pattern variants + `ConventionResult = Pass | Fail | NotApplicable` + `Catalog.apply` as a `match` with `assert_never` + `safe_yaml.load` chokepoint reuse + multi-file partial-success `CatalogLoadOutcome` — traces cleanly to arch §"Component design" #10, arch §"Design patterns applied" rows 5 (sum type / illegal-states-unrepresentable) and 8 (one file per scanner — Rule of Three), 02-ADR-0007 §Decision, Phase 0 ADR-0007 (RepoSnapshot contract freeze), Phase 1 ADR-0006 + ADR-0008, and production ADR-0033 §1, §3–4.

The draft was structurally sound — the four pattern variants are well-chosen, `NotApplicable` as load-bearing third value is the right move, the `match`+`assert_never` + per-module `mypy --warn-unreachable` discipline is correct, and the `safe_yaml.load` chokepoint reuse mirrors the Phase 1 convention. But it had **six block-tier executor-halt risks** and **a dozen harden-tier gaps** that would have let a wrong implementation slip past the executor's Validator pass. Several of these are direct echoes of S2-01 hardening (the sibling multi-file loader story validated yesterday): umbrella YAML error naming, partial-success outcome shape, AST source-scans for chokepoint discipline, and primitive-obsession on domain identifiers.

Stage 3 research **skipped** — no `NEEDS RESEARCH` findings. Every gap was answerable from arch + ADRs (02-ADR-0007, Phase 0 ADR-0007, ADR-0033, Phase 1 ADR-0006/0008) + verified repo state (`src/codegenie/probes/base.py`, `src/codegenie/parsers/safe_yaml.py`, `src/codegenie/result.py`, `src/codegenie/types/identifiers.py`, `src/codegenie/tccm/loader.py`) + S2-01 / S1-04 validation precedents.

Fourteen ACs added, ten ACs strengthened, one Design-pattern-notes section appended. Implementation outline rewritten to specify the `ConventionId` lift, the raw-`repo.root` read pattern, the module-level `_apply_one`, the seven-reason `ConventionsError` union, and the partial-success `CatalogLoadOutcome` shape. Story is now ready for `phase-story-executor`.

## Context Brief (Stage 1)

### Story snapshot

- **Goal as written:** Ship `src/codegenie/conventions/` (`__init__.py`, `model.py`, `catalog.py`) with four `ConventionRule*` Pydantic variants + `ConventionRule` discriminated union, `Pass`/`Fail`/`NotApplicable` + `ConventionResult` discriminated union, `Catalog.apply(repo)` as exhaustive `match` with `assert_never`, and `ConventionsCatalogLoader.load_all() -> Result[Catalog, ConventionsError]`.
- **Non-goals:** Layer D `ConventionsProbe` (S6-02); Layer E probes (S6-05); OPA/Rego policy backends (Phase 16); per-file `Fail` fan-out from a `file_pattern` match-set; cross-catalog rule-ID dedup; hostile-YAML adversarial tests (already pinned in S1-03 / S1-05); `SkillsLoader` (S2-01, parallel); reference TCCM round-trip (S2-03).

### Phase 2 exit criteria touched

- **Kernel scaffolding ships, no plugin loader (02-ADR-0007).** ✓ (`ConventionsCatalogLoader` is kernel-side.)
- **Conventions as data, not prompts** (CLAUDE.md commitment). ✓
- **`safe_yaml.load` chokepoint** preserved (Phase 1 ADR-0006). ✓
- **Make-illegal-states-unrepresentable** for `ConventionResult` and `ConventionsError` (ADR-0033 §3–4). ✓
- **Open/Closed at the file boundary** for adding a fifth pattern variant. ✓

### Load-bearing commitments touched

- CLAUDE.md §"No LLM anywhere in the gather pipeline" — loader is deterministic. ✓
- CLAUDE.md §"Facts, not judgments" — `Catalog.apply` emits `Pass | Fail | NotApplicable`; Planner decides. ✓
- CLAUDE.md §"Honest confidence" — `NotApplicable` is the third value preventing absent-input green-flagging. ✓
- CLAUDE.md §"Extension by addition" — fifth pattern variant adds new file + new arm + new helper; mypy ratchet on missing arm. ✓
- CLAUDE.md §"Conventions to follow" — `["*"]` wildcard semantics N/A (`ConventionRule*` variants have no `applies_to_*` lists; the Planner-side applicability lives on Skills, not Conventions).
- 02-ADR-0007 §Decision — `ConventionsCatalogLoader` is kernel-side; no `plugin.yaml`. ✓
- Phase 0 ADR-0007 — RepoSnapshot contract freeze. *Original story violated by prescribing `RepoSnapshot.build()` / `repo.read_text()`. Closed by B1.*
- Phase 1 ADR-0006 — `safe_yaml.load` chokepoint. ✓ (Strengthened by AC-10 AST source-scan.)
- Phase 1 ADR-0008 — `O_NOFOLLOW` + size cap. ✓ (Inherited via `safe_yaml.load`.)
- ADR-0033 §1 (newtypes) — `ConventionId` originally proposed in "`codegenie.adapters.ids` if exposed" (a path that does not exist); fixed to `codegenie.types.identifiers` by B2.
- ADR-0033 §3–4 — discriminated unions for `ConventionRule`, `ConventionResult`, `ConventionsError`. ✓ (Strengthened: seven reasons in `ConventionsError`; field-set minimality pinned by AC-9a.)

### Sibling-family lineage

- **Second multi-file partial-success loader in Phase 2** after `SkillsLoader` (S2-01). Convention now codified: multi-file partial-success loaders use `LoadOutcome`-shaped envelopes + Pydantic discriminated `<Loader>Error` unions; single-file loaders (`TCCMLoader`, S1-04) use marker `CodegenieError` subclasses with prefixed `args[0]`.
- **Rule-of-three threshold for shared loader-kernel:** STILL NOT REACHED. `safe_yaml.load`, `TCCMLoader`, `SkillsLoader`, `ConventionsCatalogLoader` have meaningfully different shapes; no single abstraction would compress all four without coupling unrelated concerns. Sharing is structural via `safe_yaml.load` (the YAML chokepoint).
- **Rule-of-three threshold for shared `_PatternEngine` (across the four `_apply_*` helpers):** NOT REACHED. Four ~30-LOC helpers with four genuinely different I/O shapes (one-file read with regex; one-file read with regex inverted; glob+per-file regex; glob+presence-as-assertion). Arch §"Design patterns applied" row 8 explicitly forbids the abstraction.

### Goal-to-AC trace

- AC-1 → goal: STRENGTHENED (exact-set `__all__`; seven-variant `ConventionsError`; expanded class exports).
- AC-1a → goal: ADDED (`ConventionId` canonical-home AST ratchet).
- AC-2 → goal: STRENGTHENED (full I/O monkeypatch set, mirrors S2-01 AC-2).
- AC-3 → goal: STRENGTHENED (every-field assertion, not kind-only).
- AC-3a, AC-3b → goal: ADDED (multi-rule single-file; multi-file lexicographic merge).
- AC-4 → goal: STRENGTHENED (`rule_id` assertion-strict; reason literal pinned).
- AC-4d → goal: ADDED (`re.MULTILINE` mutation killer).
- AC-5 → goal: STRENGTHENED (`rule_id` strict; three-outcome symmetric).
- AC-5a → goal: ADDED (`_apply_dockerfile_pattern_inverted` independence AST ratchet).
- AC-6 → goal: STRENGTHENED (`rule_id` + reason literal pinned).
- AC-6a → goal: ADDED (`file_pattern` happy-Pass over multi-file match-set).
- AC-6b → goal: ADDED (`Fail.evidence` lexicographic-first ordering).
- AC-6c → goal: ADDED (library / recursive `**` / dot-component exclusion semantics).
- AC-7 → goal: STRENGTHENED (`rule_id` strict; evidence substring assertion).
- AC-8 → goal: STRENGTHENED (partial-success contract; well-formed-sibling-survives).
- AC-8a, AC-8b, AC-8c → goal: ADDED (umbrella `unsafe_yaml`; `size_cap_exceeded`; `depth_cap_exceeded`).
- AC-9 → goal: STRENGTHENED (`AssertionError` only; compile-time + negative-fixture half).
- AC-9a → goal: ADDED (field-set minimality on `Pass`/`Fail`/`NotApplicable`).
- AC-10 → goal: STRENGTHENED (AST source-scan replaces ripgrep; alias-resistant).
- AC-11 → goal: kept (extra="forbid" → `SchemaError`).
- AC-11a → goal: ADDED (uncompilable regex → `SchemaError` at load).
- AC-12 → goal: STRENGTHENED (counter-monkeypatch on `pathlib.Path` not `RepoSnapshot`).
- AC-13 → goal: STRENGTHENED (seven reasons enumerated; eighth raises; JSON-shape pin).
- AC-13a, AC-13b → goal: ADDED (TOCTOU `catalog_file_unreadable`; partial-success contract under mixed-quality catalogs).
- AC-13c, AC-13d → goal: ADDED (empty `search_paths`; fatal `no_search_path_readable`).
- AC-14 → goal: STRENGTHENED (AST source-scan replaces `forbidden-patterns` pre-commit; alias-resistant).
- AC-15, AC-16 → goal: kept (toolchain; TDD discipline).

### Open ambiguities resolved before Stage 2

- **`RepoSnapshot.build(tmp_path)` + `repo.read_text(relpath)`** — neither exists. `RepoSnapshot` is a plain dataclass per `src/codegenie/probes/base.py:32-36`, Phase 0 contract-frozen. Resolution: read via `repo.root / relpath` + local `_io.read_capped_text` helper. B1 closure.
- **`codegenie.adapters.ids`** — does not exist. Canonical newtype home is `src/codegenie/types/identifiers.py`. Resolution: extend by addition. B2 closure.
- **`safe_yaml.load` raise set** — six exception classes (`SymlinkRefusedError`, `MalformedYAMLError`, `SizeCapExceeded`, `DepthCapExceeded`, plus generic `OSError`). Resolution: seven-reason `ConventionsError` covers all. B6 closure.
- **`Catalog.apply` import location for `_apply_one`** — story mixes method-on-Catalog and module-level. Resolution: pin module-level (B5).
- **Regex `re` flags** — story prescribed bare `re.search(rule.pattern, contents)`. Resolution: `re.MULTILINE` (H4; AC-4d).
- **`file_glob` library** — `pathlib.Path.glob` vs `Path.rglob` vs `glob.glob`. Resolution: `pathlib.Path.glob` with `**` recursion; dot-component exclusion default (H5; AC-6c).
- **Multi-file glob order** — non-deterministic across filesystems. Resolution: `sorted(...)` over results (H6; AC-6b).

## Stage 2 — critic reports

### Coverage (verdict: COVERAGE-HARDEN — 10 findings)

**Block-tier:**
- **C1.1 (block) — `RepoSnapshot.build(tmp_path)` and `repo.read_text(relpath)` do not exist.** Verified by reading `src/codegenie/probes/base.py:32-36` — `RepoSnapshot` is a plain `@dataclass` with `root`, `git_commit`, `detected_languages`, `config`. Phase 0 ADR-0007 freezes the probe-contract surface; the original story's prescription is unimplementable without an ADR amendment. **Fix:** Story now reads via `repo.root / relpath` + local `_io.read_capped_text(path, *, max_bytes)` helper (no new method on `RepoSnapshot`). AC-12 wraps `pathlib.Path` methods (not `RepoSnapshot` methods) for the idempotence counter.
- **C1.2 (block) — `ConventionId` location wrong.** Original story said "lift from `codegenie.adapters.ids` if exposed; otherwise add here." `codegenie.adapters.ids` does not exist; canonical home is `codegenie/types/identifiers.py`. **Fix:** Story extends `codegenie.types.identifiers` additively; AC-1a is the AST source-scan ratchet.
- **C1.3 (block) — `rule_id` never asserted on `ConventionResult`.** Every AC checked `isinstance(result, Pass|Fail|NotApplicable)` but never `result.rule_id == rule.id`. A constant-rule-id mutation slips past the entire suite. **Fix:** AC-4 / AC-5 / AC-6 / AC-7 now assert `result.rule_id == ConventionId("<expected>")` exactly.

**Harden-tier:**
- C1.4 — AC-3 happy-path only asserts kind literal; doesn't pin `id` / `description` / `pattern` populated. **Fix:** AC-3 strengthened to every-field assertion.
- C1.5 — Multi-rule single-file catalog absent. **Fix:** AC-3a.
- C1.6 — Multi-file catalog merge order never pinned. **Fix:** AC-3b (lexicographic sort).
- C1.7 — Regex compilation at load not pinned. **Fix:** AC-11a.
- C1.8 — `re.MULTILINE` semantics never pinned. **Fix:** AC-4d.
- C1.9 — `file_glob` library / recursive `**` / dot-exclusion semantics never pinned. **Fix:** AC-6c.
- C1.10 — `_apply_file_pattern` first-offending file ordering non-deterministic. **Fix:** AC-6b (sorted).

### Test quality (verdict: TESTS-HARDEN — 12 findings)

**Block-tier:**
- **TQ1 (block) — `assert_never` exception-type laxity.** Story's AC-9 allowed `pytest.raises((AssertionError, TypeError, ValueError))`. `typing.assert_never` raises `AssertionError` in Python 3.11+. Allowing TypeError/ValueError lets the `isinstance`-whitelist anti-pattern pass. **Fix:** AC-9 now `pytest.raises(AssertionError)` only.

**Harden-tier:**
- TQ2 — Mutation killer for `_apply_dockerfile_pattern_inverted` delegating to `_apply_dockerfile_pattern`. **Fix:** AC-5a AST source-scan.
- TQ3 — Mutation killer for `_apply_missing_file` returning constant `Pass`. **Fix:** AC-7 sub-tests cover both branches with exact `rule_id` + evidence substring.
- TQ4 — `Pass` field-set minimality not pinned. **Fix:** AC-9a (`model_dump()` exact equality).
- TQ5 — Mutation for `unsafe_yaml` bucket: parser typo vs constructor exploit fused. **Fix:** AC-8a covers both, documents umbrella honesty.
- TQ6 — `forbidden-patterns` AST source-scan (alias-resistance). **Fix:** AC-14 (replaces pre-commit-only with colocated AST test).
- TQ7 — TOCTOU on catalog-file disappearance. **Fix:** AC-13a.
- TQ8 — Partial-success contract under mixed-quality catalogs. **Fix:** AC-13b.
- TQ9 — Fatal-path coverage: every search path unreadable. **Fix:** AC-13d.
- TQ10 — Empty `search_paths` edge case. **Fix:** AC-13c.
- TQ11 — JSON-shape pin for `ConventionsError` variant `model_dump()`. **Fix:** AC-13 second clause.
- TQ12 — Constructor I/O monkeypatch incomplete in red. **Fix:** AC-2 strengthened (full set).

### Consistency (verdict: CONSISTENCY-HARDEN — 8 findings)

- **CN1 (block) — `RepoSnapshot` API mismatch.** Same as C1.1. Phase 0 ADR-0007 binds.
- **CN2 (block) — `ConventionId` newtype location.** Same as C1.2.
- **CN3 (block) — `ConventionsError` reasons under-enumerated vs `safe_yaml.load` raise set.** Story enumerated four reasons (`unknown_pattern_type`, `schema`, `symlink_refused`, `catalog_file_unreadable`); `safe_yaml.load` raises six distinct exceptions plus generic `OSError`. **Fix:** seven-reason union (B6); same convention as S2-01.
- CN4 — `_apply_one` method-vs-module-level inconsistency between Implementation outline and TDD plan. **Fix:** Pinned module-level (B5).
- CN5 — `re.search` default mode vs `re.MULTILINE`. Inconsistent with example pattern's `^` anchor. **Fix:** AC-4d.
- CN6 — `ConventionsError` reason-discriminator vs class-name discriminator inconsistency. **Fix:** Pinned `reason: Literal[...]` discriminator on Pydantic union, matching S2-01 `SkillsLoadError` convention.
- CN7 — `Result[Catalog, ConventionsError]` (single-error fail-fast) vs `LoadOutcome`-shaped partial-success. **Fix:** Pinned `CatalogLoadOutcome` + `FatalLoadError` (H12); matches S2-01 `LoadOutcome` shape.
- CN8 — No `O_NOFOLLOW` defense-in-depth at the catalog-file open. **Resolved as not-a-finding:** `safe_yaml.load` itself opens with `O_NOFOLLOW` per Phase 1 ADR-0008 (verified at `src/codegenie/parsers/_io.py::open_capped`). One layer of defense suffices when the loader uses no parallel open path. Convention documented in Notes.

### Design patterns (verdict: DESIGN-HARDEN — 10 findings)

- **DP1 (harden, AC) — Regex as smart-constructor at load time.** Pydantic `model_validator(mode="after")` compiles `re.compile(self.pattern)`; failure surfaces as `SchemaError` at load, not as `RuntimeError` mid-`apply`. **Closure:** AC-11a + Implementation outline §1.
- **DP2 (harden, AC) — Seven-reason `ConventionsError` discriminated union shape matches `SkillsLoadError` (S2-01).** **Closure:** AC-13 + Goal block.
- **DP3 (Notes-only) — Module-level `_apply_*` helpers + `_apply_one` (functional core, imperative shell at `Catalog.apply` boundary).** Already in original `Refactor` block. Re-affirmed in Notes.
- **DP4 (harden, ADR-amend-gated) — Adding a fifth variant is `new file + new arm + ADR-amend on the Literal`.** Not promoted to AC (the `mypy --warn-unreachable` ratchet + Notes-for-implementer makes the friction visible). Documented in Notes.
- **DP5 (harden, AC) — `_apply_dockerfile_pattern_inverted` independence.** **Closure:** AC-5a AST source-scan.
- **DP6 (harden, AC) — `Pass`/`Fail`/`NotApplicable` field-set minimality.** **Closure:** AC-9a.
- **DP7 (harden, AC) — `ConventionId` newtype lift to canonical home.** ADR-0033 §1; **closure:** Implementation outline §0 + AC-1a.
- **DP8 (Notes-only) — `RepoSnapshot` as the I/O boundary; `_apply_*` helpers as functional core.** Reaffirmed; documented in Notes.
- **DP9 (Notes-only) — Partial-success multi-file convention matches S2-01.** Documented in Notes.
- **DP10 (Notes-only) — No env-var auto-discovery; `default()` classmethod factory is the only resolution site.** Mirrors S2-01 / arch §"Anti-patterns avoided" row 11.

## Stage 3 — research

**Skipped.** Zero findings tagged `NEEDS RESEARCH`. Every closure was answerable from:
- Phase 2 arch design (`phase-arch-design.md` §"Component design" #10, §"Data model", §"Design patterns applied" rows 5/8, §"Anti-patterns avoided")
- Phase 2 ADR-0007 (no plugin loader)
- Phase 0 ADR-0007 (RepoSnapshot contract freeze)
- Phase 1 ADR-0006 (`safe_yaml` chokepoint), ADR-0008 (parse caps + `O_NOFOLLOW`)
- Production ADR-0033 §1 + §3–4 (newtypes + sum types)
- Verified repo state: `src/codegenie/probes/base.py` (RepoSnapshot shape), `src/codegenie/parsers/safe_yaml.py` (raise set), `src/codegenie/result.py` (Result API), `src/codegenie/types/identifiers.py` (newtype roster), `src/codegenie/tccm/loader.py` (sibling loader pattern)
- S2-01 hardening precedent (multi-file partial-success convention; umbrella YAML error naming; AST source-scan for chokepoint discipline)

## Stage 4 — edits applied

### Story header

- Added `Phase 0 ADR-0007` to "ADRs honored" — RepoSnapshot contract freeze (B1).
- Added `production ADR-0033 §1` — newtypes for `ConventionId`, `RegexPatternSource` (in addition to §3–4 already cited).
- Added S2-01 sibling reference to "Depends on" line — codifies the multi-file partial-success convention.
- Inserted `## Validation notes (added 2026-05-15 by phase-story-validator)` block right after the metadata, summarizing all changes (B1–B6 + H1–H12).

### Goal block

- Replaced `Result[Catalog, ConventionsError]` return type with `Result[CatalogLoadOutcome, FatalLoadError]` (partial-success shape).
- Added `CatalogLoadOutcome(catalog: Catalog, per_file_errors: list[ConventionsError])` + `FatalLoadError` Pydantic models.
- Expanded `ConventionsError` from four reasons to seven (`unknown_pattern_type`, `schema`, `symlink_refused`, `unsafe_yaml`, `size_cap_exceeded`, `depth_cap_exceeded`, `catalog_file_unreadable`).
- Pinned `_apply_one` as module-level function (not method on Catalog).
- Replaced "regex compiled lazily" with "regex compiled at load time via `model_validator(mode="after")`".
- Pinned `re.MULTILINE` flag on Dockerfile pattern matching.
- Pinned `pathlib.Path.glob` library + sorted iteration order.
- Pinned `repo.root / relpath` read pattern (no new method on `RepoSnapshot`).
- Added invariant §11 (RepoSnapshot read-at-boundary) and §12 (partial-success contract).

### Acceptance criteria

**Strengthened in place:**
- AC-1 — exact-set `__all__`; seven-variant `ConventionsError`; expanded class exports.
- AC-2 — full I/O monkeypatch set (mirrors S2-01 AC-2).
- AC-3 — every-field assertion replaces kind-only.
- AC-4 — `rule_id` assertion-strict; reason literal pinned.
- AC-5 — `rule_id` assertion-strict; symmetric three-outcome.
- AC-6 — `rule_id` + reason literal pinned.
- AC-7 — `rule_id` strict + evidence substring pinned.
- AC-8 — partial-success contract; sibling-rule-survives invariant.
- AC-9 — `pytest.raises(AssertionError)` only; compile-time + negative-fixture half.
- AC-10 — AST source-scan (alias-resistant) replaces ripgrep.
- AC-12 — counter-monkeypatch on `pathlib.Path` (no `RepoSnapshot.read_text` method).
- AC-13 — seven reasons enumerated; eighth raises; JSON-shape pin.
- AC-14 — AST source-scan colocated with test suite.

**Added:**
- AC-1a — `ConventionId` canonical-home AST ratchet.
- AC-3a — multi-rule single-file catalog.
- AC-3b — multi-file lexicographic merge.
- AC-4d — `re.MULTILINE` mutation killer.
- AC-5a — `_apply_dockerfile_pattern_inverted` independence AST source-scan.
- AC-6a — `file_pattern` `Pass` over multi-file match-set.
- AC-6b — `Fail.evidence` lexicographic-first ordering.
- AC-6c — `pathlib.Path.glob` library + recursive `**` + dot-exclusion.
- AC-8a — `unsafe_yaml` umbrella (constructor exploit + parser typo same bucket).
- AC-8b — `size_cap_exceeded` (> 1 MiB catalog).
- AC-8c — `depth_cap_exceeded` (> 64 nesting levels).
- AC-9a — `Pass`/`Fail`/`NotApplicable` field-set minimality (`model_dump()` exact).
- AC-11a — uncompilable regex `pattern` → `SchemaError` at load.
- AC-13a — TOCTOU `catalog_file_unreadable` with `errno_name`.
- AC-13b — partial-success contract under mixed-quality catalogs.
- AC-13c — empty `search_paths` returns `Result.Ok(empty)`.
- AC-13d — fatal `no_search_path_readable` when every search path unreadable.

### Implementation outline

- §0 added — `ConventionId` newtype lift to `codegenie.types.identifiers`.
- §1 rewrote — regex `model_validator(mode="after")` + compiled stash; ConfigDict.
- §2 rewrote — seven `ConventionsError` variants + `CatalogLoadOutcome` + `FatalLoadError` + `_classify_validation_error` helper.
- §3–§6 rewrote — `repo.root / relpath` pattern; `re.MULTILINE`; sorted glob results; AC-5a independence.
- §7 added — module-level `_apply_one` shape.
- §8 added — multi-file partial-success driver pseudocode (exception-by-exception classification into the seven `ConventionsError` reasons).
- §9 added — `_io.read_capped_text` helper.
- §10 added — `__init__.py` + `default()` factory.

### Files to touch table

- Added `src/codegenie/types/identifiers.py` (modify, additive — `ConventionId`).
- Added `src/codegenie/conventions/_io.py` (new — `read_capped_text` helper).
- Split test files: main `test_catalog.py` + four colocated AST source-scan tests (`test_no_direct_yaml_import.py`, `test_no_model_construct.py`, `test_inverted_helper_is_independent.py`, `test_no_local_convention_id.py`) + one `mypy`-driven compile-time test (`test_apply_match_is_exhaustive_compile_time.py`) + a negative-fixture directory.

### Notes for the implementer

Appended `### Design-pattern notes (added by validator 2026-05-15)` section with ten paragraphs:
- `ConventionId` canonical home (newtype lift; ADR-0033 §1).
- `RepoSnapshot` as the I/O boundary; functional core + imperative shell at the `pathlib.Path` seam (B1 framing).
- Regex as smart-constructor (load-time compilation).
- `unsafe_yaml` umbrella naming is operationally-prudent.
- Partial-success multi-file pattern matches S2-01.
- Four independent `_apply_*` helpers — Rule of Three NOT reached.
- `Pass`/`Fail`/`NotApplicable` field-set minimality (illegal-states-unrepresentable).
- Module-level `_apply_one` (not a method on Catalog) — enables AC-9 smoke test.
- Three-and-counting newtype lift moments to watch.
- No env-var auto-discovery; `default()` classmethod factory is the only resolution site.
- `Catalog.apply` is consumed by Layer D / E probes inside `register_probe(heaviness="light")` — keep pure.

## Final verdict

**HARDENED.** Story is ready for `phase-story-executor`. Fourteen ACs added, ten strengthened. Implementation outline rewritten to specify the `ConventionId` lift, the raw-`repo.root` read pattern, the module-level `_apply_one`, the seven-reason `ConventionsError` union, and the partial-success `CatalogLoadOutcome` shape.

The patterns that make this story *easy to maintain and extend by addition*:

1. **`ConventionId` newtype lift to `codegenie.types.identifiers`** — adding a fourth+ consumer of the newtype is zero-edit (just import); the next probe / loader / probe that needs to reference convention IDs imports from the canonical home.
2. **Open/Closed at the file boundary for adding a fifth pattern variant** — new `ConventionRule*` class + new `_apply_<kind>` helper + new `case` arm in `_apply_one`. The `mypy --warn-unreachable` per-module ratchet makes a missing arm a build failure. Zero edits to existing helpers, `Catalog`, or `ConventionsCatalogLoader`.
3. **Seven-reason `ConventionsError` discriminated union** — adding an eighth `reason` is a new Pydantic class + Literal extension + new variant in the `Annotated[Union[...]]`. Pydantic discriminator-tag failures surface naturally via `_classify_validation_error`; no central dispatch table to edit.
4. **Partial-success multi-file shape (`CatalogLoadOutcome`)** — Phase 4+ probe consumers that want to surface per-catalog errors to operators read `outcome.per_file_errors` directly; no defensive `try/except` around `load_all()` ergonomic-failure modes.
5. **Module-level `_apply_*` helpers + `_apply_one`** — adding fancier matching semantics (e.g., a `regex_flags` field on `ConventionRuleFilePattern`) is an edit to the one helper; the dispatcher is a thin `match`.
6. **`Catalog.apply` is pure-given-snapshot** — Phase 4+ probes can call it inside a `@register_probe(heaviness="light")` slot without I/O surprises; AC-12 is the contract pin.
7. **`unsafe_yaml` umbrella** — operationally-prudent name; same posture for parser typo and constructor exploit; future contributors don't need to know Pydantic-v2's `__cause__` chain encoding to triage a CLI warning.

These are the load-bearing extension points the validator's design-patterns critic surfaced and the synthesizer promoted to ACs or Design-pattern Notes.
