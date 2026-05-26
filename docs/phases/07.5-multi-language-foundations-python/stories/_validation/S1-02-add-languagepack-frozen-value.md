# Validation report: S1-02 — Add the `LanguagePack` frozen total value

**Validated:** 2026-05-26
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [../S1-02-add-languagepack-frozen-value.md](../S1-02-add-languagepack-frozen-value.md)

## Summary

The story as written was **structurally sound** — its goal traces cleanly to phase exit criterion G2, its references are accurate, and its three named ADRs (0001 frozen total value, 0003 one-to-many grammars, 0006 retrofit discriminator) actually constrain the implementation. No `RESCUE`-level findings; verdict: **HARDENED**.

The hardening targets three classes of weakness:

1. **AC coverage holes** — three load-bearing facts had no AC: the default value of `probes_self_registered` (a wrong default would silently make every Python pack a retrofit and skip its probe fan-out), the canonical field *order* (which the S7-05 snapshot fence will pin), and the "import does not pull grammar wheels" guarantee (mentioned in Notes but unenforced). All three are now ACs with concrete assertion templates.

2. **Thin mutation surface in the TDD plan** — the original frozen test mutated a single `Literal` newtype field, leaving tuple/mapping fields uncovered; the `arbitrary_types_allowed` test exercised one arbitrary type rather than both; the test snippets were pseudocode `#` comments. The hardened plan covers all three field categories under `frozen`, both arbitrary types under `arbitrary_types_allowed=True`, and ships near-executable assertions plus a hypothesis property test for `package_managers ≡ tuple(dep_graph_strategies.keys())` that kills a "cached second source of truth" mutation.

3. **Reservation discipline + maintenance ergonomics** — the `__all__` AC pinned only `≤ 6` count, allowing accidental name squatting on reserved slots; the `_valid_pack()` helper was implicit; Files-to-touch used ambiguous "new/append" verbs given S1-03/S1-04 already create the files. All three are now explicit: `__all__` is pinned to the **exact** six-name set, the helper is mandated to live in `conftest.py` (so S1-04 can reuse it without duplicating stubs), and Files-to-touch uses `append`/`new`/`update` verbs precisely.

A fourth concern — that an executor might add format validation for `search_adapter_module` ("module:ClassName") inside the model — is surfaced as a Notes paragraph: that validation is S2-02's responsibility (a `validate_pack` policy check), not `LanguagePack`'s. Adding it here would couple construction to module-import time and duplicate S2-02 logic.

## Context Brief

### Story snapshot (original)
- **Goal:** Land `src/codegenie/languages/` with frozen Pydantic `LanguagePack` carrying six required capability fields, the `probes_self_registered` discriminator, and a derived `package_managers` `@property`.
- **Effort:** M; depends on S1-01 (foundation `PackageManager += pip/poetry/uv` + `LanguageRegistryError`) and S1-04 (`ProjectDetector` Protocol — which transitively requires S1-03 `DetectionResult`).
- **ADRs honored:** 0001 (frozen total value, `Provisional Accepted` with third-language review trigger), 0003 (one-to-many `grammars` relation; reuse `Language` newtype), 0006 (`probes_self_registered` typed retrofit discriminator).

### ACs as written (original, numbered)
- AC-1: `LanguagePack` is `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`.
- AC-2: It carries the exact six fields + discriminator + derived `@property`.
- AC-3: Incomplete `LanguagePack(...)` is `mypy --strict` error (compile-time deferred to S1-06; runtime `ValidationError` here).
- AC-4: Extra/typo'd field → `ValidationError`; value is genuinely frozen.
- AC-5: `arbitrary_types_allowed=True` still enforces `frozen` and `extra="forbid"`.
- AC-6: `package_managers` returns `tuple(dep_graph_strategies.keys())`; tracks the mapping.
- AC-7: `__all__ ≤ 6`; `import-linter` contract for the new package; `make fence` green.
- AC-8: Red test exists; ruff/mypy/pytest pass.
- AC-9: Status set to Done.

### Constraints discovered during context loading
- **ADR-0001 (phase):** frozen Pydantic v2; `package_managers` is a derived `@property`, NOT a field; `Provisional Accepted` — narrow + earned + with review trigger per production ADR-0043 commitment 5.
- **ADR-0003 (phase):** `language: Language` reuses the existing newtype (no `LanguageId` mint); `grammars: tuple[SupportedLanguage, ...]` models the one-to-many relation.
- **ADR-0006 (phase):** `probes_self_registered: bool = False` is the typed retrofit discriminator; `register_language` skips probe fan-out when `True`; the no-shadow check skips `probes_self_registered=True` packs.
- **Phase arch §Component design:** the canonical public-interface block pins the model_config line, the six required fields in order, the discriminator default, and the `@property`. The arch §Data model block pins the canonical field order again — this *is* the snapshot fence's source.
- **Phase arch §Component design — internal structure:** "The pack holds *references only* — probe classes, strategy callables, a tuple of grammar Literal keys, an import-path string — no behavior, no I/O." This rules out format validation for `search_adapter_module` inside the model.
- **Phase arch §Risks #1 ("Step-1 risk"):** `arbitrary_types_allowed=True` *might* weaken `frozen` / `extra="forbid"` — it does not, but the unit tests must *assert* it, not assume it. The story already references this in AC and Notes; the hardening widens the assertion to cover both arbitrary-typed fields.
- **Phase arch §Development view:** the `__all__` of `codegenie.languages` is reserved to exactly 6 names (`LanguagePack`, `LanguageRegistry`, `register_language`, `default_language_registry`, `LanguageRegistryError`, `language_packs`), mirroring the 6-name `codegenie.depgraph` surface.
- **S7-05 (sibling story):** the `LanguagePack` contract-snapshot fence pins the *exact* field set and order — making this story's field-order AC load-bearing for the snapshot's stability.
- **S2-02 (sibling story):** owns the `validate_pack` checks including the `"module:ClassName"` adapter-resolvable check — this story must NOT add that validation.

### Shipped style precedent that interacts with the story's edits
- `src/codegenie/result.py` (`Ok` / `Err` / `Result`) is the project's canonical Pydantic-v2 frozen-value-object module. Same `ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`. Mirror its line shape and module co-location of related types.
- `src/codegenie/depgraph/registry.py` carries the `DepGraphStrategy = Callable[...]` alias that `LanguagePack.dep_graph_strategies` values are typed against — referenced unchanged.
- `pyproject.toml` `[[tool.importlinter.contracts]]` entries for `codegenie.plugins` and `codegenie.transforms` are the canonical shape — `type = "forbidden"`, `source_modules = [...]`, `forbidden_modules = [...]`, `as_packages = true`. S1-02 mirrors this.

### Goal-to-AC trace (original)
- AC-1, AC-2 → goal ("frozen total value with six fields"): YES, but AC-2 leaves field *order* unpinned.
- AC-3, AC-4 → goal ("incomplete is unrepresentable"): YES, but the missing-field test omits five fields at once rather than parameterizing per field.
- AC-5 → goal (Step-1 risk): YES, but exercises only ONE arbitrary type.
- AC-6 → goal ("`package_managers` is derived"): YES, but doesn't pin the class-level descriptor type — a `Field(default_factory=...)` could satisfy a naive read.
- AC-7 → goal (`__all__` reservation): partial — pins count but not the reserved name set.
- Missing trace: no AC pins the default of `probes_self_registered` (ADR-0006), the canonical field order (S7-05 snapshot fence), or the "no grammar-wheel import" guarantee (Notes-only).

## Findings by critic

### Coverage critic
- **C1 (harden)** — No AC pins `probes_self_registered: bool = False` *default value*. A wrong default (e.g., `= True`) would silently make **every** Python pack a retrofit, skip its probe fan-out, and bypass the no-shadow check (ADR-0006). The Pydantic shape test alone doesn't catch this — `model_fields["probes_self_registered"].default` is what's load-bearing. Proposed fix: AC-5 explicitly asserts `LanguagePack.model_fields["probes_self_registered"].default is False`.
- **C2 (harden)** — No AC pins the canonical **field order** in `model_fields`. The S7-05 snapshot fence pins this exactly. If S1-02 ships with a reordered field set that happens to type-check, S7-05's snapshot will lock in a wrong order. Proposed fix: AC-2 explicitly asserts `tuple(LanguagePack.model_fields.keys()) == (<the seven names in canonical order>)`.
- **C3 (harden)** — "`import codegenie.languages` must not import any grammar wheel" is in Notes-for-implementer but has no AC. The Notes-only status is the failure mode the prior critic on the parent design flagged — "paper claims, not tested facts." Proposed fix: AC-10 added — a subprocess test that imports `codegenie.languages` and asserts no `tree_sitter*` module is in `sys.modules`.
- **C4 (harden)** — The frozen-mutation AC only tests mutating `language` (a `Literal` newtype). Pydantic's `frozen=True` is documented to cover all assignment, but the test gives no evidence it covers tuple-typed or mapping-typed fields. A regression where only scalar fields were frozen would pass the original test. Proposed fix: AC-7 widened — three separate `pytest.raises` cases covering `Literal` newtype (`pack.language = ...`), tuple (`pack.grammars = ...`), and mapping (`pack.dep_graph_strategies = ...`) plus an `AttributeError` check that `pack.grammars.append(...)` fails (structural-immutability sanity).
- **C5 (harden)** — `arbitrary_types_allowed=True` test exercises only ONE arbitrary type (typically `type[Probe]` in `layer_a_probes`). The mode is required for BOTH `type[Probe]` AND the `DepGraphStrategy` callable values inside `dep_graph_strategies` — if Pydantic's handling diverged between the two, the original test wouldn't notice. Proposed fix: AC-8 explicitly requires the test to carry a real `type[Probe]` AND a real `DepGraphStrategy` callable, and assert both `frozen` and `extra="forbid"` still fire.
- **C6 (harden)** — Original AC-4's missing-field test omits five fields at once with a single `LanguagePack(language=...)` call. That's one `ValidationError` — a passing test only proves *at least one* required field is enforced. Proposed fix: AC-6 is a `pytest.parametrize` over each of the six required fields independently; six `pytest.raises` cases.

### Test-Quality critic
- **T1 (harden)** — Original TDD snippets are pseudocode `#` comments rather than executable `def test_...` blocks. An executor has to translate intent under attempt-budget pressure. Proposed fix: rewrite all TDD test entries as near-executable templates (concrete `assert` lines, real imports, parametrize annotations).
- **T2 (harden)** — The `_valid_pack()` helper is referenced but not specified. Risk: each test reimplements its own stub `ProjectDetector` / stub `Probe` / stub strategy, and the stubs drift. Proposed fix: helper lives in `tests/unit/languages/conftest.py` (NOT in the test module), with an explicit shape; S1-04 reuses it; S2-01+ stories also reuse it.
- **T3 (harden)** — Mutation thinking: an executor implementing `package_managers` as a Pydantic `Field(default_factory=lambda: ())` that returns the keys at construction time would pass a naive "returns the keys" test. The test must also assert the *descriptor type* at the class level — `inspect.getattr_static(LanguagePack, "package_managers")` is an instance of `property`. Proposed fix: AC-3 added as a class-level descriptor assertion.
- **T4 (harden)** — Hypothesis property test opportunity: the metamorphic relation `pack.package_managers == tuple(pack.dep_graph_strategies.keys())` should hold for **any** non-empty subset of `PackageManager` values, not just the one fixture happens to pick. A property test kills a "cached at construction" mutation that would pass a single-case test. Proposed fix: AC-4 is the property test (`tests/property/test_language_pack_derived.py`), drawing from `get_args(PackageManager)` via `hypothesis.strategies.sampled_from`.

### Consistency critic
- **B1 (harden)** — Files-to-touch marks `pack.py` and `__init__.py` as "new/append". Given the explicit dependency on S1-04 (which depends on S1-03), the files **already exist** by the time S1-02 lands. The ambiguous verb risks an executor either (a) recreating the files (wiping S1-03/S1-04 work) or (b) leaving stale half-built stubs from a recovered worktree. Proposed fix: Files-to-touch uses `append` precisely; Implementation outline step 1 reads "**Append** to the existing `src/codegenie/languages/pack.py`" not "Ensure … exists".
- **B2 (nit)** — `Depends on: S1-01, S1-04` is technically complete, but S1-03 is the *transitive* dependency carrying `DetectionResult` / `Detected` / `NotDetected` — used by the conftest helper's `_StubDetector.detect()`. Proposed fix: depend-line now reads "S1-01, S1-04 (transitively S1-03 via S1-04)" so an executor running the dependency-resolved order doesn't drop S1-03.
- **B3 (no action)** — The story's claim that this is foundational, downstream-blocking type work is consistent with the phase arch (`LanguagePack` is "the load-bearing value of the phase"). No contradiction.

### Design-Patterns critic
- **D1 (nit, kept)** — Frozen Pydantic `BaseModel` + derived `@property` for `package_managers` is the canonical **Value Object + Make-Illegal-States-Unrepresentable + Single-Source-of-Truth** pattern. ADR-0001 §Pattern fit names this exactly. No structural change.
- **D2 (nit, kept)** — `probes_self_registered: bool` is the canonical **typed discriminator on an immutable value** (ADR-0006 §Pattern fit). The toolkit's "boolean flags on methods" anti-pattern doesn't apply — this is a field on a value, set once at pack construction. Kept.
- **D3 (harden)** — `search_adapter_module: str` is the kind of stringly-typed field that would normally trigger the "primitive obsession" alarm — except production ADR-0032 explicitly defines the "module:ClassName" adapter-resolvable format as a *string* import path, and `validate_pack` (S2-02) is the sanctioned validator. The story's risk is that an executor reads ADR-0001 + sees the `str` type + adds a Pydantic validator inside `LanguagePack` to format-check the string. That would couple `LanguagePack` *construction* to module-import-time side effects, violate the arch's "the pack holds references / strings only — no behavior, no I/O" property, and duplicate S2-02's check. Proposed fix: Notes paragraph forbids format validation here; refers to S2-02.
- **D4 (harden)** — `__all__` reservation: `≤ 6` count alone allows an executor to ship `__all__ = ["LanguagePack", "AccidentalName"]` — two items, count-rule passed, but a reserved slot squatted. The reserved set is fixed (arch §Development view names the six). Proposed fix: AC-9 pins `__all__` to the **exact** six-name set; Notes warn that names whose modules don't yet exist appear in `__all__` but importing them raises `ImportError` until their owning story lands — the executor MUST NOT create stub modules to make the imports resolve.
- **D5 (harden, surfaced as Notes)** — `src/codegenie/result.py` is the project's canonical Pydantic-v2 frozen-value precedent (`Ok` / `Err` carry the same `ConfigDict` line). Mirror its style for review-style consistency. This is a "match the existing convention" reminder (Rule 11) — not an AC, because style is contextual.
- **D6 (harden, surfaced as Notes)** — Resist any urge to add abstract base classes, extension hooks, or "registry-of-packs" machinery to `LanguagePack` itself. The value-object's job is to *be a language*. Plugin/strategy-pattern extension hooks live one level up — at `LanguageRegistry` (S2-01) and at the strategy registries (S2-03 / S5-02..S5-04). Adding ABC scaffolding here would (a) violate ADR-0001's "Value object, not Builder" rejection and (b) cross the "three similar lines is better than premature abstraction" line (Rule 2) — there is exactly one consumer of the pack value's shape per registered language; abstraction earns its keep only at the registry level.

## Research briefs

None — no `NEEDS RESEARCH` findings. The patterns (frozen value object, typed discriminator, derived-property single-source-of-truth, hypothesis property tests) are all canonical and well-documented in the codebase's existing precedents (`codegenie.result`, `codegenie.depgraph.registry`, `tests/property/test_dep_graph_strategy_dispatch.py`) and the named ADRs. Stage 3 skipped.

## Conflict resolutions

- **Coverage C2 (pin field order) vs Rule 3 (Surgical Changes)**: kept. Field order is *contract*, pinned by S7-05's snapshot fence; failing to assert it now means S7-05 locks in whatever order the executor happens to write. Not scope creep — pure correctness.
- **Coverage C3 (subprocess test for import purity) vs cost of test infra**: kept. The "lazy grammar wheel" guarantee is one of the few testable claims in the phase that would catch a class of bug (eager wheel load → cold-start regression → CI slowdown surfaces only later). The subprocess approach is the standard Python idiom for import-graph assertions.
- **Test-Quality T4 (hypothesis property test) vs Rule 2 (Simplicity First)**: kept. Single-case test admits a "cached at construction" mutation; the property test is exactly the kind of "would catch a wrong implementation" coverage Rule 9 demands. The hypothesis dependency is already in `pyproject.toml` (Phase 2 property tests).
- **Design-Patterns D4 (pin `__all__` to exact name set) vs convenience**: kept. The reservation list is fixed by arch §Development view; the cost is zero (the executor types six names instead of one count); the benefit is the reservation slots can't be accidentally squatted by other names.
- **Design-Patterns D3 (no format validation in `LanguagePack`) vs Coverage urge**: D3 wins via Consistency. The arch component spec says "no behavior, no I/O"; S2-02 owns the format check. Format validation in `LanguagePack` would violate two source-of-truth documents.

## Edits applied

### Edit 1 — Header block: Status → `HARDENED`; Depends-on clarified
- Source: Consistency B2
- Before: `**Status:** Ready` / `**Depends on:** S1-01, S1-04`
- After: `**Status:** HARDENED` / `**Depends on:** S1-01, S1-04 (transitively S1-03 via S1-04)`
- Rationale: dependency chain is now explicit; downstream tools and humans can read it without traversing S1-04's depend-line.

### Edit 2 — `Validation notes` block added under header
- Records the validator pass with breadcrumbs to this report.

### Edit 3 — Acceptance criteria rewritten (9 ACs → 13 ACs, each individually verifiable)
- Source: all four critics
- Original ACs were collapsed (e.g., "model is frozen AND extra-forbid" was one AC). Hardened ACs split each into individual binary checks with concrete assertion templates. New ACs:
  - AC-2: canonical field order pinned (was implicit in original AC-2)
  - AC-3: `inspect.getattr_static` descriptor check (was missing — original AC-6 was weaker)
  - AC-4: hypothesis property test (was a single concrete case in original AC-6)
  - AC-5: `probes_self_registered` default pinned (was missing)
  - AC-6: parameterized per-field missing-required test (was a single five-field-missing test)
  - AC-7: frozen across `Literal` / tuple / mapping field categories (was Literal-only)
  - AC-8: `arbitrary_types_allowed` exercises both arbitrary types (was one)
  - AC-9: `__all__` pinned to the exact six-name reservation set (was count-only)
  - AC-10: grammar-wheel-free import test (was Notes-only)
- Rationale: each AC is now individually verifiable; the AC set collectively constrains a correct implementation against the mutations a naive executor would attempt.

### Edit 4 — Implementation outline rewritten (6 → 8 steps)
- Source: Consistency B1 + Design-Patterns D3/D4 + Test-Quality T2
- Step 1: "Ensure exists" → "**Append** to the existing" (the files exist post-S1-03/S1-04).
- Step 2: adds explicit "Do **not** import any `tree_sitter*` wheel here" (binds Step 2 to AC-10).
- Step 4: explicit `__all__` reservation discipline + "executor MUST NOT add stub modules to satisfy import".
- Step 5: import-linter contract shape pinned ("mirror the `codegenie.plugins` / `codegenie.transforms` shape").
- Step 6: conftest helper landing location explicit (`tests/unit/languages/conftest.py`).
- Step 8: `make check` + `make fence` + `make lint-imports` as the sealing gate.

### Edit 5 — TDD plan rewritten with executable templates + new files
- Source: Test-Quality T1, T2, T3, T4 + Coverage C3, C4, C5, C6
- The pseudocode `#` comments are replaced by four concrete test files: `test_language_pack.py` (AC-1..AC-3, AC-5..AC-8), `test_import_purity.py` (AC-10), `test_package_surface.py` (AC-9), `test_language_pack_derived.py` (AC-4). Each carries near-executable `assert` lines, real imports, and parametrize annotations.
- `tests/unit/languages/conftest.py` is now explicit, with the `_valid_pack(**overrides)` helper, stub `ProjectDetector`, stub `Probe` subclass, and stub strategy callable.

### Edit 6 — Files-to-touch expanded and verbs clarified
- Source: Consistency B1 + Test-Quality T2 + Coverage C3
- "new/append" → precise `append` / `new` / `update` verbs
- New files: `conftest.py`, `test_import_purity.py`, `test_package_surface.py`, `test_language_pack_derived.py`
- Appended files: `pack.py`, `__init__.py`

### Edit 7 — Notes for the implementer reframed and widened
- Source: Design-Patterns D3, D4, D5, D6 + Test-Quality T2 + Coverage C5
- Added: style precedent reference to `codegenie.result.py` (D5)
- Added: explicit "do not validate `search_adapter_module` format here — that's S2-02" paragraph (D3)
- Added: `__all__` reservation explanation + "do NOT create stub modules" prohibition (D4)
- Added: "resist ABC scaffolding here — extension lives at the registry level" paragraph (D6)
- Added: conftest hygiene paragraph (T2)
- Widened: `arbitrary_types_allowed` note explicitly mentions both arbitrary-typed fields (C5)

## Verdict rationale

The story had no `block`-severity findings — its goal, ADRs, and references all hold up under audit, and its scope ("provide the type; S1-06 provides the compile-time-failure machinery") is honest. The weaknesses were in **AC granularity** (composite ACs hid individual checks), **mutation surface** (single-case tests admitted naive executor mutations), and **reservation discipline** (`__all__` count vs name-set; "new/append" ambiguity vs precise verb choice). All are fixable in place; verdict: **HARDENED**, not RESCUE.

The hardened story now:

- Has 13 individually-verifiable ACs that collectively constrain a correct implementation;
- Carries near-executable TDD test templates including a hypothesis property test that kills the "second source of truth" mutation;
- Pins the `__all__` reservation to the **exact** six-name set the arch §Development view names;
- Forbids `LanguagePack`-level format validation for `search_adapter_module` (S2-02's job);
- Surfaces the canonical style precedent (`codegenie.result.py`) the executor should mirror;
- Forbids ABC scaffolding inside `LanguagePack` itself — extension hooks live at the registry / strategy-registry level, not at the value-object level.

The story follows the **Value Object + Make-Illegal-States-Unrepresentable + Single-Source-of-Truth** pattern at the value level, leaves **Registry + Plugin Architecture + Open/Closed** seams for S2-01+ to ship, and respects Rule 2's "three similar lines is better than premature abstraction" line (no speculative extension hooks, no Builder, no abstract base class).

## Recommended next step

`phase-story-executor docs/phases/07.5-multi-language-foundations-python/stories/S1-02-add-languagepack-frozen-value.md`

The story is now self-consistent, the ACs are individually verifiable and collectively guarantee the goal, the TDD plan would catch the canonical mutations a wrong implementation would attempt, and the prescribed implementation respects the arch's "the pack holds references only — no behavior, no I/O" property while leaving the plugin / strategy extension seams open at the proper architectural layer (the registry, not the value).
