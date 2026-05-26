# Validation report: S1-03 — Add the `DetectionResult` sum type

**Validated:** 2026-05-26
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [../S1-03-add-detectionresult-sum-type.md](../S1-03-add-detectionresult-sum-type.md)

## Summary

The story as written was **structurally sound** — its goal traces cleanly to ADR-0005 (Option D — `Detected | NotDetected` sum type), to phase-arch §Data model (`@dataclass(frozen=True)` canonical block), and to phase exit criterion G2 ("incomplete is unrepresentable"). Three named references hold up under audit. No `RESCUE`-level findings; verdict: **HARDENED**.

The hardening targets four classes of weakness:

1. **AC granularity** — the original AC-1 collapsed `Detected` and `NotDetected` into one composite criterion; AC-3 conflated runtime witness with static-time exhaustiveness; AC-2 left `Confidence`'s definition site, syntactic form (`: TypeAlias = Literal[...]`), and `Literal` argument order unpinned. Split each composite into individually-verifiable assertions and pinned the syntactic form + argument order (load-bearing for ADR-0005's "real manifest → `confidence="high"`" semantics).

2. **Thin mutation surface in the TDD plan** — the original snippets were pseudocode `#` comments; the frozen test mutated one scalar field, leaving the tuple field uncovered; the exhaustiveness test only verified runtime dispatch on both arms (a tautological "match returns something" check) without using `assert_never` as the actual witness; no equality/hash assertions (the dataclass-generated semantics `match` relies on); no property test. The hardened plan ships near-executable assertion templates, covers every field category under `frozen=True`, uses `assert_never` as the load-bearing exhaustiveness signal, pins equality + hash semantics, and adds one hypothesis property test that kills "construction-time-only-frozen" mutations.

3. **Module-level surface discipline** — the story's References pointed to `src/codegenie/result.py` as the "frozen-dataclass + union-alias idiom" precedent, but `result.py` is **Pydantic `BaseModel`**, not `@dataclass`. The arch §Data model block is the actual precedent for `DetectionResult` (intentionally `@dataclass`, not Pydantic, because this is an internal sum type, not a validated user-facing value). The misleading pointer is corrected in `Notes`. Additionally, no AC pinned that `Detected` / `NotDetected` / `DetectionResult` / `Confidence` are **module-level only** in `pack.py` — they are NOT in `codegenie.languages.__all__` (which S1-02 hardening reserved to exactly six names). An executor reading "may stay module-level" could have added them and broken S1-02's reservation contract.

4. **Sum-type structural invariants** — no AC verified `isinstance(d, Detected)` discriminates from `isinstance(d, NotDetected)`. An executor accidentally making `NotDetected` extend `Detected` (or vice versa) would pass every original AC. The hardened plan pins strict isinstance discrimination and verifies `get_args(DetectionResult) == (Detected, NotDetected)` against the union alias itself.

A fifth concern — that the static-time non-exhaustiveness proof (mypy rejects a `match` missing a variant) is *runtime-testable* — is correctly deferred to S1-06's mypy-must-fail harness. The hardened story commits the **runtime** witness (`assert_never` in `case _:`) here and points the executor at S1-06 for the static fence. Surfaced as a `Notes` paragraph.

## Context Brief

### Story snapshot (original)
- **Goal:** Define `Detected`, `NotDetected`, and `DetectionResult = Detected | NotDetected` as a frozen-dataclass tagged union so a `match` with a missing case is a `mypy --strict` / `assert_never` error.
- **Effort:** S; no dependencies.
- **ADRs honored:** ADR-0005 (`ProjectDetector` Protocol returning a sum type, Option D over `detected: bool`).

### ACs as written (original, numbered)
- AC-1: `Detected` is `@dataclass(frozen=True)` w/ `confidence: Confidence` + `marker_files: tuple[Path, ...]`; `NotDetected` is `@dataclass(frozen=True)` no fields.
- AC-2: `Confidence` defined (or imported if canonical exists) as `Literal["high", "medium", "low"]`; `DetectionResult: TypeAlias = Detected | NotDetected`.
- AC-3: Exhaustiveness test — both-arm `match` type-checks; planted missing case rejected via `assert_never` else branch.
- AC-4: Genuinely frozen; mutation raises `FrozenInstanceError`.
- AC-5: ruff/format/mypy/pytest green.
- AC-6: Status set to Done.

### Constraints discovered during context loading
- **ADR-0005 (phase, §Decision):** Option D over Option C — `Detected | NotDetected` makes "detected with no markers" unrepresentable; a `match` missing a case is a compile error. Crucially: `Detected(confidence="high")` only on a *real* manifest; `Detected(confidence="low")` for bare `*.py` — so `Confidence`'s argument order ("high", "medium", "low") is not aesthetic, it's a contract.
- **Phase arch §Data model (the `DetectionResult — contract (in-memory sum type)` block):** canonical declaration is `@dataclass(frozen=True)` for both variants — explicitly **not** Pydantic. `Detected` has `confidence: Confidence` + `marker_files: tuple[Path, ...]`; `NotDetected: ...` is "singleton-shaped, no fields".
- **Phase arch §Component design — `ProjectDetector` + `DetectionResult` + `markers.py`:** the public-interface code block reaffirms the dataclass-frozen form and pins `Confidence` as a `Literal["high", "medium", "low"]` inline comment.
- **Phase arch §Cross-cutting concerns:** "`DetectionResult` is a `Detected | NotDetected` sum type — a missing case is a `match`/`assert_never` compile error" — establishes the **runtime** exhaustiveness witness (`assert_never`) AND the **static** witness (`mypy --strict`). The two are different mechanisms; the story must pick one as the in-scope AC.
- **Phase ADRs (ADR-0005 §Consequences):** detection is **monotone / additive** — a polyglot repo is detected as both languages; a detector never demotes another. This is a `ProjectDetector` *implementation* concern (S3-03 / S4-03), NOT a `DetectionResult` *value* concern — confirms S1-03's scope is correctly narrow.
- **Production ADR-0033 (sum-type discipline):** the canonical project-level commitment to closed-set `Literal` for state-like primitives + sum-type-not-bool-with-loose-siblings. Confirms ADR-0005's Option D rationale.
- **Production ADR-0043 (extension-by-addition):** duplication is a standing review criterion; `Confidence` defined here does **not** replace inline `Literal["high", "medium", "low"]` usages in `src/codegenie/probes/layer_g/semgrep.py:190`, `ripgrep_curated.py:172`, `test_coverage_mapping.py:140` — those are pre-existing, and silently editing them is forbidden. The new canonical alias is for *future* consumers of detection results; migration of existing inline literals is a separate addition-only story.
- **Sibling S1-02 hardening (this validator's prior pass, 2026-05-26):** `codegenie.languages.__all__` is reserved to **exactly six names** — `LanguagePack`, `LanguageRegistry`, `register_language`, `default_language_registry`, `LanguageRegistryError`, `language_packs`. `Detected` / `NotDetected` / `DetectionResult` / `Confidence` are **NOT** in this set and **MUST NOT** be added. Consumers import via `from codegenie.languages.pack import DetectionResult`. The story's "Re-export … only if a downstream consumer needs them" line is in tension with this fence — clarify to MUST NOT.
- **S1-06 (sibling story, deferred):** the mypy-must-fail harness is the static-time fence; this story's `assert_never` test is the runtime witness. Two complementary mechanisms.

### Shipped style precedent that interacts with the story's edits
- `src/codegenie/result.py` (`Ok` / `Err` / `Result`) — **NOT** the technology precedent for `DetectionResult` (it's Pydantic `BaseModel`, not `@dataclass`). The story's References block points to `result.py` for the "frozen-dataclass + union-alias idiom" — that line is misleading. `result.py` is the *naming* / *co-location* precedent (sum types live in one module with `TypeAlias`); the *technology* choice is decided by arch §Data model = `@dataclass(frozen=True)`.
- `src/codegenie/types/identifiers.py:29` — canonical `from typing import ... TypeAlias` + `Foo: TypeAlias = ...` style for type aliases. Mirror this.
- `src/codegenie/probes/layer_g/semgrep.py:190`, `ripgrep_curated.py:172`, `test_coverage_mapping.py:140` — three inline `Literal["high", "medium", "low"]` usages that pre-date this canonical alias. **Not edited** (ADR-0043 — extension by addition; a migration is a separate sanctioned sweep).

### Module-shape diagnosis (Design-Patterns critic prefetch)
- **Public surface:** four module-level names in `pack.py` — `Confidence` (`TypeAlias`), `Detected` (frozen dataclass), `NotDetected` (frozen dataclass), `DetectionResult` (`TypeAlias`). All four are pure type definitions; none carry behavior or side effects.
- **Pure helpers:** none — the story defines types, not functions. Functional core / imperative shell is trivially satisfied (no `run()` to speak of).
- **Side effects:** zero. `pack.py` must remain stdlib-only for this story's contribution (`dataclasses`, `pathlib`, `typing`). S1-02 / S1-04 add codegenie sibling imports for `LanguagePack` / `ProjectDetector` respectively — out of scope here.
- **Existing kernel consumed:** none — this story *defines* a new kernel-shaped value (the sum type) that S1-04's `ProjectDetector` and S3-03/S4-03's concrete detectors consume.
- **Existing files edited:** none — `pack.py` and `__init__.py` are net-new in this story (or net-new in S1-03's sibling Step-1 story; coordinate). The S1-02 hardening clarified that by the time S1-02 lands, `pack.py` exists; but S1-03 has no dependency, so it's the natural creator.

### Sibling-family lineage (Design-Patterns critic)
- **This story is the 1st concrete consumer of `pack.py`** — the module-creating story for `src/codegenie/languages/`. The arch §Module/development view names `pack.py` as the home for `LanguagePack`, `ProjectDetector`, and `DetectionResult` — three siblings under one module.
- **Prior validation framings carried forward:**
  - S1-02 hardening established that `codegenie.languages.__all__` is reserved to exactly six names. This story MUST honor that fence (`Detected` / `NotDetected` / `DetectionResult` / `Confidence` are module-level only).
  - S1-02 hardening also established that `pack.py` is grammar-wheel-free (AC-10). This story's contribution must not break that invariant.
- **Rule-of-three threshold:** NOT YET REACHED for `DetectionResult` itself — the only consumer is the `ProjectDetector` Protocol (S1-04). The sum type is the right abstraction at the first consumer because the alternative (`detected: bool` + loose siblings) is the anti-pattern ADR-0005 explicitly rejects; abstraction is "earned by ADR", not "earned by repetition".

### Goal-to-AC trace (original)
- AC-1 → goal ("sum-type tagged union, both variants frozen"): YES, but conflates two type definitions into one criterion.
- AC-2 → goal ("`Confidence` Literal + `DetectionResult` alias"): WEAK — leaves the syntactic form (`TypeAlias`), the argument order (`"high"`, `"medium"`, `"low"`), and the definition site unpinned.
- AC-3 → goal ("exhaustive match"): WEAK — pseudocode comment runs the risk of an executor writing a tautological "match returns something" test rather than the `assert_never` witness; also conflates runtime witness with static-time fence (S1-06's job).
- AC-4 → goal (frozen): partial — only one field category exercised; tuple field uncovered.
- AC-5, AC-6 → process gates, not behavioral. Fine as written.
- Missing trace: no AC pins `isinstance` discrimination, equality/hash semantics, module-level reservation (vs `__all__`), or stdlib-only imports.

## Findings by critic

### Coverage critic
- **C1 (harden)** — AC-2's "`Confidence` is defined (or imported if a canonical one exists)" is a vague disjunction. The canonical does NOT exist yet (only inline `Literal["high","medium","low"]` usages in `semgrep.py` / `ripgrep_curated.py` / `test_coverage_mapping.py`). Pin the definition: **`Confidence: TypeAlias = Literal["high", "medium", "low"]`** in `src/codegenie/languages/pack.py`, in **exactly that argument order** (ADR-0005 §Decision uses `confidence="high"` as the strong signal and `confidence="low"` as the weak signal — order is contract). Test asserts `typing.get_args(Confidence) == ("high", "medium", "low")`.
- **C2 (harden)** — AC-1 conflates `Detected` and `NotDetected` into one composite criterion. Split: one AC per type, each pinning field names, types, and field count. Add a parametric check that `dataclasses.fields(Detected)` matches the canonical (name, type) tuple and `dataclasses.fields(NotDetected) == ()`.
- **C3 (harden)** — AC-3 says "covering both variants type-checks" without a concrete assertion. The runtime witness for exhaustiveness is `typing.assert_never(other)` in a `case _:` arm — at runtime, if a future variant reaches that arm, `assert_never` raises (and `mypy --strict` flags it statically). Pin: the test function uses `typing.assert_never` in the catch-all arm; both `classify(Detected(...))` and `classify(NotDetected())` return the variant-specific value; no value reaches the `assert_never` arm in the test fixtures. **Separate** the runtime witness (this story) from the static-time mypy-must-fail proof (S1-06's harness — a planted-`match`-missing-a-case snippet).
- **C4 (harden)** — AC-4's frozen test exercises one field category. Split into three `pytest.raises(FrozenInstanceError)` cases: scalar (`Detected.confidence = "low"`), tuple (`Detected.marker_files = ()`), and arbitrary attribute on `NotDetected` (`NotDetected().__setattr__("foo", 1)`). Frozen-attribute creation on a no-field dataclass is the failure mode an "I removed `@dataclass`" mutation produces.
- **C5 (harden)** — No AC verifies sum-type structural integrity. `isinstance(Detected(...), NotDetected)` must be `False` and vice versa. An executor mistakenly making `NotDetected` extend `Detected` (or even both inherit a common base) would silently pass every original AC. Pin: strict isinstance discrimination + `typing.get_args(DetectionResult) == (Detected, NotDetected)`.
- **C6 (harden)** — No AC pins module-level placement vs. `codegenie.languages.__all__`. Per S1-02 hardening, `__all__` is reserved to six names; `Detected` / `NotDetected` / `DetectionResult` / `Confidence` are NOT in it and MUST NOT be added. Pin: `set(codegenie.languages.__all__).isdisjoint({"Detected","NotDetected","DetectionResult","Confidence"})` AND consumers must import via `from codegenie.languages.pack import ...`.

### Test-Quality critic
- **T1 (harden)** — TDD plan is pseudocode `#` comments — same failure mode as S1-02. Rewrite as near-executable test templates: real imports, real `assert` lines, concrete parametrize annotations.
- **T2 (harden)** — Mutation thinking: a frozen test that mutates only `confidence` would pass even against a partial freeze where only the `Literal` field was protected. The hardened plan covers all three failure categories (scalar, tuple, no-field attribute-creation) so a `@dataclass(frozen=False)` or `@dataclass(eq=True)` (without `frozen=True`) regression fails loudly.
- **T3 (harden)** — Equality + hash semantics: `match Detected(): ...` dispatch relies on the dataclass-generated `__eq__` / `__hash__`. Pin: `Detected("high", ()) == Detected("high", ())`, `NotDetected() == NotDetected()`, `Detected("high", ()) != NotDetected()`, `hash(Detected("high", ()))` stable, `hash(NotDetected())` stable. Without this, an executor doing `@dataclass(frozen=True, eq=False)` would pass the original AC-1 but break `match` semantics in downstream consumers.
- **T4 (harden)** — Hypothesis property test: one focused property test (`tests/property/test_detection_result.py`) drawing `confidence ∈ {"high","medium","low"}` and a small tuple of `pathlib.Path`s, asserting (a) `Detected(...)` is constructible, (b) it is frozen (any field-set assignment raises), (c) it is hashable and equality is value-based. Kills mutations that pass single-case tests (e.g., "frozen at construction time but a `__setattr__` shim allows updates").
- **T5 (harden)** — The runtime exhaustiveness test as written ("`match` over a `DetectionResult` covering both variants type-checks") is tautological — any function that returns a string after a 2-arm match would pass it. The load-bearing signal is **`assert_never` in the catch-all arm**: at runtime it raises if a variant escapes the explicit arms; at static-check time `mypy --strict` flags an inexhaustive match because the catch-all variable's narrowed type must be `Never`. Pin the `assert_never` call explicitly in the test template — the test is the documented runtime witness; S1-06 owns the static-time witness.
- **T6 (nit)** — `tuple[Path, ...]` is mypy-only enforcement (dataclasses don't validate at runtime). The AC should distinguish: "the *correctly-typed* construction site uses a tuple" (runtime-observable: `isinstance(d.marker_files, tuple)`) vs. "passing a `list` is a mypy error" (deferred to S1-06's mypy-must-fail harness). Avoid an AC that promises runtime type validation `dataclasses` doesn't provide.

### Consistency critic
- **B1 (harden)** — References block points to `src/codegenie/result.py` as the "frozen-dataclass + union-alias idiom" precedent. **`result.py` is Pydantic `BaseModel`, not `@dataclass`.** The arch §Data model code block is the actual technology source-of-truth (explicit `@dataclass(frozen=True)`). Two possible reads: either the story author conflated Pydantic and dataclass forms (likely), or this is a hidden technology-choice contradiction. Resolution: keep `@dataclass(frozen=True)` per arch §Data model (it's the named technology). Reframe the `result.py` pointer as a *naming* / *co-location* precedent (sum-type variants + alias live in one module), NOT a technology precedent.
- **B2 (nit)** — The story's Goal says "frozen-dataclass tagged union" while References mentions `result.py` (Pydantic). Same B1 contradiction surfaces at two locations; fixed alongside.
- **B3 (harden)** — Story says "`pack.py` … the module that will also hold `LanguagePack` from S1-02 and `ProjectDetector` from S1-04". S1-02 hardening confirmed this co-location. But S1-02's hardened Implementation outline reads "**Append** to the existing `src/codegenie/languages/pack.py` (created by S1-03 …)". That makes **S1-03 the creator of `pack.py`** — but S1-03's own Implementation outline says "Create `src/codegenie/languages/` package (if not already created by a sibling)". Make creation responsibility explicit: S1-03 creates both `src/codegenie/languages/__init__.py` and `pack.py`; S1-02 and S1-04 append.
- **B4 (no action)** — ADR-0005 §Decision pins `Detected(confidence, marker_files) | NotDetected` exactly as the story prescribes. No contradiction. The monotonicity / additivity property (a polyglot repo is detected as both languages) is a `ProjectDetector` *implementation* concern (S3-03 / S4-03), correctly out of scope per the story's Out-of-scope block.
- **B5 (harden)** — `Confidence` defined as a new alias does NOT replace the inline `Literal["high","medium","low"]` usages already in `semgrep.py:190`, `ripgrep_curated.py:172`, `test_coverage_mapping.py:140`. Per production ADR-0043 (extension by addition; silent edits forbidden), this story must NOT touch those files. Notes paragraph clarifies the dual existence is intentional, and migration is a separate addition-only sweep.

### Design-Patterns critic
- **D1 (kept)** — **Tagged union / sum type** + **Make-Illegal-States-Unrepresentable** is correctly named in the story and in ADR-0005 §Pattern fit. The anti-pattern explicitly rejected (`detected: bool` + loose siblings) is documented. No structural change.
- **D2 (kept)** — `Confidence: TypeAlias = Literal["high", "medium", "low"]` is a closed-set `Literal`, not a `NewType` — this is the correct choice (state-like values, not identity-like). ADR-0033 names this as the canonical state-primitive idiom. Kept.
- **D3 (harden)** — No premature kernel / registry. The sum type is for *result* values; there is no `DetectionResultRegistry` or `DetectionResultFactory` to introduce. Rule 2 ("three similar lines is better than premature abstraction"): the *consumers* of `DetectionResult` (S1-04 Protocol, S3-03 / S4-03 detectors) are where Open/Closed seams belong — at the registry level, not at the value level. Pin in Notes: do NOT introduce abstract base classes, `Variant` sentinels, or a "ResultBuilder" helper. The sum type **is** the abstraction.
- **D4 (harden)** — `NotDetected` is "singleton-shaped" per arch §Data model, but a zero-field frozen dataclass is **NOT** a singleton — every `NotDetected()` call returns a fresh instance (which compares equal to every other `NotDetected()` via dataclass-generated `__eq__`). Do NOT introduce a `_NOTDETECTED_INSTANCE: Final = NotDetected()` sentinel — it's an anti-pattern (couples consumers to identity rather than to type; `match case NotDetected():` works on type, not identity). Surface in Notes.
- **D5 (harden)** — `__all__` discipline: S1-02 hardening reserved `codegenie.languages.__all__` to six names; this story's symbols are NOT in that set. Pin: consumers import from `codegenie.languages.pack` (module path), NOT from `codegenie.languages` (package surface). Pin in Notes + AC-9.
- **D6 (kept)** — Functional core / imperative shell: trivially satisfied (no `run()` to speak of — this is a type-definition module). Kept.
- **D7 (harden)** — `pack.py` stdlib-only invariant: this story's contribution must use only `dataclasses`, `pathlib`, `typing`. No `codegenie.*` sibling imports yet (S1-02 / S1-04 add them later). An AST-scan or text-scan test asserts S1-03's introduced symbols use only stdlib. Pin as AC-9.
- **D8 (kept)** — Composition over inheritance: `NotDetected` does NOT extend `Detected`; both are standalone dataclasses. The sum type is by `|` (union), not by inheritance. Kept.

## Research briefs

None — no `NEEDS RESEARCH` findings. All patterns are canonical Python typing:

- `@dataclass(frozen=True)` semantics — Python `dataclasses` documented behavior.
- `typing.assert_never` as the exhaustiveness witness — PEP 647, well-documented mypy behavior.
- `TypeAlias` + `Literal` for state-like primitives — production ADR-0033 + codebase precedent in `src/codegenie/types/identifiers.py`.
- Hypothesis property tests — already in `tests/property/` (S1-02 ships `test_language_pack_derived.py` under this pattern).
- AST-scan import-purity tests — codebase precedent (S1-02 ships `test_import_purity.py` for the package surface; mirror at module level here).

Stage 3 skipped.

## Conflict resolutions

- **Consistency B1 (`result.py` is Pydantic, not dataclass) vs Story's References pointer**: Consistency wins. The arch §Data model code block names `@dataclass(frozen=True)` explicitly; that's source-of-truth. The `result.py` pointer is reframed in Notes as a *naming / co-location* precedent (sum-type variants in one module), NOT a *technology* precedent.
- **Coverage C3 (runtime `assert_never` witness here) vs Coverage's instinct to also fence statically**: split. Runtime witness lives in this story's AC; static-time mypy-fail is **deferred to S1-06**. Both mechanisms are valuable; mixing them in one story would violate Rule 3 (surgical changes).
- **Coverage C6 (pin `__all__` non-inclusion) vs Rule 3 (Surgical Changes — don't touch S1-02's territory)**: kept. The non-inclusion AC is *asserting an invariant the prior story established*, not editing the prior story. The cost is one assertion line; the benefit is the reservation contract can't be silently broken by a future story author who reads only S1-03.
- **Design-Patterns D4 (no singleton sentinel) vs apparent arch language "singleton-shaped"**: arch language is descriptive, not prescriptive — "singleton-shaped" means "zero fields, instances are interchangeable", NOT "one canonical instance exists". Kept as Notes guidance; an AC would over-specify (the dataclass-generated `__eq__` already makes the singleton-or-fresh distinction invisible to callers).
- **Coverage C1 (pin `Literal` argument order to "high","medium","low") vs aesthetic invariance**: kept. ADR-0005 uses `confidence="high"` and `confidence="low"` as semantic markers (high = real manifest; low = bare `*.py`). If a future reader sees `Literal["low", "medium", "high"]`, the `get_args` ordering changes — and downstream tests that iterate or pin the args (Phase-7.5 conformance assertions, S1-06 mypy-fail harness) become flaky.

## Edits applied

### Edit 1 — Header block: Status → `HARDENED`
- Source: validator pass
- Before: `**Status:** Ready`
- After: `**Status:** HARDENED`

### Edit 2 — `Validation notes` block added under header
- Records the validator pass with breadcrumbs to this report.

### Edit 3 — Acceptance criteria rewritten (6 ACs → 13 ACs, each individually verifiable)
- Source: all four critics
- Original ACs were collapsed and pseudocode-shaped. Hardened ACs split each into individual binary checks with concrete assertion templates. New / split ACs:
  - AC-1 — `Confidence` alias definition site + form + argument order pinned (was a vague disjunction in original AC-2)
  - AC-2 — `Detected` shape pinned via `dataclasses.fields` (was conflated with AC-3 in original AC-1)
  - AC-3 — `NotDetected` shape pinned independently (was conflated with AC-2 in original AC-1)
  - AC-4 — `DetectionResult` alias pinned via `get_args` (was a sub-clause of original AC-2)
  - AC-5 — Frozen across three field categories (was scalar-only in original AC-4)
  - AC-6 — Equality + hash semantics pinned (was missing)
  - AC-7 — `marker_files` is structurally a `tuple` at runtime (was missing — mypy-only enforcement is deferred to S1-06)
  - AC-8 — Match exhaustiveness with `assert_never` witness; static-time deferred to S1-06 (was conflated in original AC-3)
  - AC-9 — Module purity: `pack.py` imports stdlib-only for this story's contribution (was a Notes line, no AC)
  - AC-10 — `codegenie.languages.__all__` non-inclusion + consumer import path pinned (was missing — S1-02 fence)
  - AC-11 — `isinstance` discrimination + `get_args(DetectionResult) == (Detected, NotDetected)` (was missing — defends sum-type structural integrity)
  - AC-12 — Full local gate (renumbered from original AC-5; mirrors S1-02's AC-12 phrasing)
  - AC-13 — Status set to Done (renumbered)
- Rationale: each AC is now individually verifiable; the AC set collectively constrains a correct implementation against the mutations a naive executor would attempt — partial-freeze, structural-integrity, `__all__`-squat, and the `result.py`-as-Pydantic confusion.

### Edit 4 — Implementation outline rewritten (4 → 8 steps)
- Source: Consistency B3 + Design-Patterns D5/D7
- Step 1: explicit "S1-03 **creates** `__init__.py` (S1-02 hardening confirmed S1-03 is the creator)"
- Step 2: explicit "Create `pack.py` with **only stdlib imports** for this story's contribution (`dataclasses`, `pathlib`, `typing`); S1-02 / S1-04 add codegenie sibling imports later"
- Steps 3–6: one step per symbol (`Confidence`, `Detected`, `NotDetected`, `DetectionResult`) so the executor can checkpoint
- Step 7: explicit non-inclusion in `__all__` (S1-02 reservation honored)
- Step 8: red test first → green → `make check` + `make fence` + `make lint-imports` as the sealing gate

### Edit 5 — TDD plan rewritten with executable templates + new property test
- Source: Test-Quality T1, T2, T3, T4, T5 + Coverage C2, C3, C4, C5, C6
- Pseudocode `#` comments are replaced by near-executable test functions in `tests/unit/languages/test_detection_result.py` covering: `Confidence` argument order, both shape predicates, frozen across three categories, equality/hash, marker_files-is-tuple, match-with-assert_never, isinstance discrimination, `__all__` non-inclusion.
- Adds `tests/property/test_detection_result.py` — a hypothesis property test drawing `confidence` and `marker_files` over their full input space.
- Adds an AST-scan import-purity test inside the unit module asserting `pack.py`'s S1-03 symbols use only stdlib (Coverage C5, AC-9).

### Edit 6 — Files to touch updated
- Source: Consistency B3 + Test-Quality T4 + Coverage C5
- `src/codegenie/languages/__init__.py` — `new` (S1-03 creates; S1-02 / S1-04 append)
- `src/codegenie/languages/pack.py` — `new` (S1-03 creates; S1-02 / S1-04 append)
- `tests/unit/languages/__init__.py` — `new` (test package skeleton, if not already present)
- `tests/unit/languages/test_detection_result.py` — `new` (10+ test functions per AC)
- `tests/property/test_detection_result.py` — `new` (hypothesis property test)

### Edit 7 — Notes for the implementer reframed and widened
- Source: Consistency B1/B5 + Design-Patterns D3/D4/D5/D7 + Test-Quality T5
- **Removed/reframed**: the misleading "mirror `result.py`'s frozen-dataclass + union-alias idiom" pointer. `result.py` is **Pydantic**, not `@dataclass`. The arch §Data model code block is the technology precedent; `result.py` is the *naming / co-location* precedent only.
- **Added**: `Confidence` defined here does NOT replace inline `Literal["high","medium","low"]` usages elsewhere (ADR-0043 — extension by addition; silent edits forbidden); migration is a separate sanctioned sweep.
- **Added**: `Detected` / `NotDetected` / `DetectionResult` / `Confidence` are **module-level only** in `pack.py`; they are **NOT** in `codegenie.languages.__all__` (six-name reservation per S1-02 hardening); consumers import via `from codegenie.languages.pack import ...`.
- **Added**: do NOT introduce a `_NOTDETECTED_INSTANCE` singleton — `NotDetected()` instances are interchangeable via the dataclass-generated `__eq__`; the "singleton-shaped" arch language is descriptive, not prescriptive.
- **Added**: do NOT introduce abstract base classes, `Variant` enums, or `ResultBuilder` helpers — Rule 2 (the sum type IS the abstraction); Open/Closed seams live at the registry level (S2-01, S5-02..S5-04), not at the value-type level.
- **Added**: runtime exhaustiveness witness is `assert_never` here; static-time non-exhaustiveness proof (a planted `match` missing a variant) is **deferred to S1-06's mypy-must-fail harness** — two complementary mechanisms.
- **Added**: `pack.py` must remain stdlib-only for this story's contribution; S1-02 / S1-04 add codegenie sibling imports later; no I/O, no logger, no grammar wheels ever in this module (S1-02 AC-10 is the package-level guarantee; this story's AC-9 is the module-level invariant).

## Verdict rationale

The story had no `block`-severity findings — its goal, ADR-0005 honor, scope (exclude monotonicity / additivity properties, exclude concrete detectors, exclude markers catalog), and references to the arch §Data model + ADR-0005 are all correct. The weaknesses were in **AC granularity** (composite ACs hid individual checks), **mutation surface** (single-case tests admitted naive executor mutations), **module-surface discipline** (no AC honored S1-02's six-name `__all__` reservation), and one **misleading reference** (`result.py` named as the technology precedent when arch §Data model unambiguously chose `@dataclass`). All are fixable in place; verdict: **HARDENED**, not RESCUE.

The hardened story now:

- Has 13 individually-verifiable ACs that collectively constrain a correct implementation;
- Carries near-executable TDD test templates including a hypothesis property test that exercises `Detected` over its full input space;
- Pins the `assert_never` runtime exhaustiveness witness explicitly and defers the static-time fence to S1-06 (no test-mechanism conflation);
- Honors the S1-02 six-name `__all__` reservation by pinning `Detected` / `NotDetected` / `DetectionResult` / `Confidence` as module-level-only;
- Clarifies the `result.py` reference (naming precedent, NOT technology) so an executor doesn't accidentally use Pydantic `BaseModel` instead of `@dataclass`;
- Forbids singleton sentinels (`_NOTDETECTED_INSTANCE`) and premature kernel scaffolding (`Variant` enums, `ResultBuilder`) — Rule 2; extension seams live at the registry level (S2-01, S5-02..S5-04), not at the value-type level.

The hardened story follows the **Tagged Union / Sum Type + Make-Illegal-States-Unrepresentable + Module-Boundary Discipline** pattern, leaves the **Protocol** + **Registry** + **Plugin Architecture** Open/Closed seams for S1-04 / S2-01 / S5-02..S5-04 to ship, and respects Rule 2's "three similar lines is better than premature abstraction" line (no speculative extension hooks, no singleton instance, no `Variant` enum).

## Recommended next step

`phase-story-executor docs/phases/07.5-multi-language-foundations-python/stories/S1-03-add-detectionresult-sum-type.md`

The story is now self-consistent (no `result.py`-as-Pydantic confusion), the ACs are individually verifiable and collectively guarantee the goal, the TDD plan would catch the canonical mutations a wrong implementation would attempt (partial freeze, missing `assert_never`, structural-integrity break, `__all__` squat), and the prescribed implementation respects S1-02's `__all__` six-name reservation while leaving extension seams at the proper architectural layer (the `ProjectDetector` Protocol at S1-04, the `LanguageRegistry` at S2-01, the per-language detectors at S3-03 / S4-03).
