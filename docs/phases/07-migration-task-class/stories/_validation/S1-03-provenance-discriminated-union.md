# S1-03 — Seven-variant `Provenance` discriminated union + nested `Both` guard — Validation report

**Story:** [../S1-03-provenance-discriminated-union.md](../S1-03-provenance-discriminated-union.md)
**Validated:** 2026-05-19
**Validator pass:** `phase-story-validator` skill (first pass — no prior `_validation/` entry for S1-03)
**Verdict:** **HARDENED** — real but fixable weaknesses across all four critic lenses; edits applied in place; story is now ready for `phase-story-executor`.

## Context Brief (Stage 1)

### Story snapshot
- **Goal (verbatim):** Implement the verbatim seven-variant `Provenance` discriminated union from `phase-arch-design.md §Component design §2` — `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`, `Unknown` — under `src/codegenie/primitives/vuln_provenance/types.py`, with every variant `frozen=True, extra="forbid"`, `kind` discriminator pinned per variant, `AppKind` / `BaseKind` as nested discriminated unions over non-`Both`/non-`Unknown` variants, and a parametrized red test asserting `Both(Both(...), ...)` raises `ValidationError`.
- **Effort:** M
- **Depends on:** S1-01 (newtype identifiers), S1-02 (`_Frozen`, `DistroPackage`, `UnknownReason`, `AdapterConfidence` already shipped).
- **Status pre-edit:** `Ready`. Status post-edit: `HARDENED`.

### Files to touch (post-edit)
- `src/codegenie/primitives/vuln_provenance/types.py` — extend with the seven variants + `AppKind`/`BaseKind`/`Provenance` aliases.
- `src/codegenie/primitives/vuln_provenance/__init__.py` — additive re-exports (variants + aliases).
- `tests/unit/primitives/vuln_provenance/test_provenance_union.py` — NEW (AC-1..AC-8 + AC-10 + new AC-12..AC-14).
- `tests/unit/primitives/vuln_provenance/test_provenance_exhaustiveness.py` — NEW (AC-9).
- `tests/unit/primitives/vuln_provenance/test_provenance_mypy_negative.py` — NEW (AC-15 — mirrors S1-01's mypy-negative precedent).

### Phase / arch constraints
- **Phase 7 ADR-0004** — primitive home + `__init__.py` re-export surface includes the variants and aliases.
- **Phase 7 ADR-0006** — `match`/`assert_never` discipline relies on the closed-shape union.
- **Production ADR-0033** — `frozen=True, extra="forbid"`; no half-valid states.
- **Production ADR-0038** — seven-variant contract verbatim (the closed shape).
- **Phase-arch-design §Component design §2** — the verbatim Pydantic shape for all seven variants + the `AppKind`/`BaseKind` aliases; "the type system itself enforces the recursion guard, not a runtime check."
- **Phase-arch-design §Data model lines 962–1010** — re-asserts the seven variants + `Provenance` final alias; the contract is intentionally repeated in two places to signal stability.
- **Phase-arch-design §Edge cases row 4** — the `Both` variant is the "Phase 7 produces evidence, not coordination" exit-criterion; emission lands in S11-01/S11-02 but depends on this story's shape.
- **Phase-arch-design §Design patterns applied row 1** — "Tagged union with discriminator; make illegal states unrepresentable; nested `Both` rejects `Both(Both, ...)` at validation time."

### Phase exit criteria the story contributes to
- **Goal 1** (the primitive ships with the seven-variant union, ADR-0038 verbatim, `mypy --strict` clean).
- **Goal 9** (the `Both` variant produces evidence; emission paths in S11-01..S11-04 depend on this shape).
- **Indirectly Goal 3** (`assemble_provenance` does `match (app, base)` on `AppKind` / `BaseKind` — without the nested-union shape, the `match` arms would be open).

### Prior validation history
- S1-01 ([_validation/S1-01-phase7-newtype-identifiers.md](S1-01-phase7-newtype-identifiers.md)) — established the mypy-negative test precedent.
- S1-02 ([_validation/S1-02-provenance-enums-and-distro-package.md](S1-02-provenance-enums-and-distro-package.md)) — established `_Frozen` base + `model_construct`-bypass fence (both apply transitively to S1-03's new variants) + gate-widening pattern (`make check` over a per-subdir `mypy --strict`).

### Open ambiguities (Stage 1 gate)
- ⚠️ **Numbering ambiguity in trailing AC block** — the story carries AC-1 through AC-11 plus two unnumbered trailing bullets (TDD red test exists; ruff/mypy/pytest pass). These are standard story-footer gates and remain unnumbered (consistent with S1-01 / S1-02 footers). No edit; flagged for reader awareness only.
- ⚠️ **AC-7 round-trip is narrow (3 of 7 variants)** — the TDD plan parametrizes only `["app_direct", "app_transitive", "base_image"]`. The discriminator-routing invariant requires all seven, especially `Both` (nested discriminated unions) and `Unknown` (which `AppKind` and `BaseKind` exclude). Surfaced to Coverage critic.
- ⚠️ **The story's existing `Both`-rejection AC names "Unknown in app_record" but not "BaseImage in app_record"** — the arch's `AppKind` excludes `BaseImage`/`RuntimeBundled`, and the existing test file already covers this. AC-4 should mirror the test file. Surfaced to Coverage critic.

## Stage 2 — Critic findings

Critics ran inline (single-validator pass, no subagents) — story scope is focused enough that token economy favored inline analysis over four parallel subagents. Findings cross-checked against the existing (uncommitted) test file at `tests/unit/primitives/vuln_provenance/test_provenance_union.py` to ensure the hardened ACs are achievable, not aspirational.

### Coverage critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C1 | block | **AC-7 round-trip covers only 3 of 7 variants.** The TDD plan parametrizes round-trip over `["app_direct", "app_transitive", "base_image"]`. The discriminator-routing invariant (Pydantic v2 `Field(discriminator="kind")` on the outer `Provenance` alias) only holds across the *full* set. `Both` (nested discriminated unions) and `Unknown` (excluded from `AppKind`/`BaseKind`) are exactly where round-trip drift can hide. | Rewrote **AC-7** to parametrize over all seven variants; added an explicit `Both`-round-trip sub-clause. |
| C2 | harden | **No JSON-string round-trip.** AC-7 covers the Python-dict path via `TypeAdapter(Provenance).validate_python(model_dump())`. Downstream consumers (event log per ADR-0034; `coordination-summary.yaml` writer per S11-02) serialize to JSON strings, where `Path` ↔ `str` and `tuple` ↔ `list` coercion drift can land silently. | Added a JSON-string round-trip sub-clause to **AC-7**: `TypeAdapter(Provenance).validate_json(adapter.dump_json(p)) == p`. |
| C3 | harden | **`Both` recursion guard misses two structural cases.** AC-4 lists three cases (Both-in-app, Both-in-base, Unknown-in-app). It omits Unknown-in-base, BaseImage-in-app, RuntimeBundled-in-app, and AppDirect-in-base (the existing test file covers all of them). | Rewrote **AC-4** to enumerate all six structural-rejection cases; matched the precedent in the existing test file. |
| C4 | harden | **`Unknown.details: dict[str, str]` not pinned at runtime.** AC-1's `Unknown` shape names `details: dict[str, str] | None = None`, but no AC asserts that `details={"err": 42}` raises `ValidationError` at construction. The arch is explicit ("do NOT widen to `dict[str, Any]`"); the no-`Any` fence S1-06 catches the *static* type, but a runtime test catches an executor who writes `details: dict` and relies on the fence. | Added **AC-12**: pin `Unknown.details` value-type at construction (string coerce, non-str values raise). |
| C5 | harden | **`AppTransitive.chain` boundary tests miss the empty tuple.** AC-8 says "chain=(pkg,) → ValidationError; chain=(pkg, pkg2) → ok". The empty-tuple case (`chain=()`) is a distinct edge of `Field(min_length=2)` worth pinning — the existing test file covers it (`test_app_transitive_chain_empty_rejected`). | Extended **AC-8** to add `chain=()` as a third invalid case. |
| C6 | nit | **`AppVendored.confidence=DEGRADED` happy-path absent.** Every variant has at least one happy-path fixture; `AppVendored` is the only one whose typical real-world confidence is `DEGRADED` (vendored copies lack manifest provenance). Worth pinning in a parametrize. | Folded into the AC-7 all-seven-variant expansion; no separate AC needed. |
| C7 | nit | **`BaseImage.stage = None` vs `stage=DockerStageName("builder")` not separately pinned.** AC-1 names `stage: DockerStageName \| None`; round-trip should exercise both cases. Existing test file does (`base_image_no_stage` fixture). | Added a sub-clause to **AC-1** explicitly naming both cases (`stage=None` and `stage` provided) as required happy-path coverage. |

### Test-Quality critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| T1 | harden | **AC-4's `# type: ignore[arg-type]` markers signal a dual-layer invariant that is not separately asserted.** The story prescribes `# type: ignore[arg-type]` markers because mypy --strict already rejects `Both(app_record=inner_both, ...)`. Without a mypy-negative test, an executor who loosened `Both.app_record: AppKind | Both` would silently regress: runtime rejection still fires (via `Field(discriminator="kind")` routing) but the static guarantee is gone. | Added new **AC-15** (mypy-negative test) anchored at `test_provenance_mypy_negative.py` — mirrors S1-01's `test_identifiers_phase7_mypy_negative.py`. Pins three negative assertions: `Both(app_record=Both(...), ...)` is `[arg-type]`; `Both(app_record=Unknown(...), ...)` is `[arg-type]`; `Both(app_record=BaseImage(...), ...)` is `[arg-type]`. |
| T2 | harden | **TDD plan's frozen test is single-instance, but AC-5 says "parametrized over every variant."** AC promise and TDD plan diverge — an executor could land `test_app_direct_frozen` only and tick AC-5. | Strengthened the TDD plan note under **AC-5** to require an explicit per-variant parametrize covering all seven (the existing test file already does this — pin the contract). |
| T3 | harden | **Tests verify intent, not just behavior (Rule 9) — `test_app_transitive_chain_min_length` doesn't encode WHY.** The test proves length-1 rejects, but doesn't pin the rationale: "chain length 1 → `AppDirect`; chain length > 1 → `AppTransitive`" is the arch invariant. Without the rationale in the test, an executor later "fixing" the `min_length` to `1` to admit a corner case loses the historical reason. | Added an implementer-note paragraph: every test pinning a Pydantic constraint must carry a one-line docstring naming the arch rule it pins (this catches mutation-style regressions before they ship). |
| T4 | harden | **No mutation-resistance check on the discriminator routing itself.** A wrong implementation could remove `Field(discriminator="kind")` from the outer `Provenance` alias; round-trip via `model_dump()`+`validate_python()` may still succeed because Pydantic v2 has a no-discriminator fallback path that tries each member in order. The first-matching variant could absorb a payload meant for a later one. | Added **AC-13**: a payload with mismatched `kind` value must raise `ValidationError` at deserialization (e.g., `{"kind": "app_direct", "image_digest": "..."}` rejects, doesn't silently coerce to a `BaseImage`-shaped record). |
| T5 | harden | **AC-9 exhaustiveness test would pass with a missing variant if `mypy --strict` is not part of the runtime gate.** The story's AC-9 names the test pattern but the *enforcement* of "missing `match` arm = mypy error" is implicit. AC-11 names `mypy --strict src/codegenie/primitives/vuln_provenance/` but not project-wide `make check`. | Widened **AC-11** to require project-wide `make check` (mirrors S1-02's CO4 widening). Added an explicit refactor step: temporarily comment out one `match` arm, confirm `mypy --strict` errors, restore — the gating discipline is on the executor. |
| T6 | nit | **No property test scoped to "no `Both(Both, ...)` can ever be constructed."** Arch §Testing strategy lists `tests/property/vuln_provenance/test_both_invariant.py` but defers to S2-05 (the assembler-level property test). A smaller story-scoped property test (Hypothesis-driven over the six `AppKind | BaseKind` variants) would catch mutation regressions across thousands of generated inputs. | Recorded as an implementer note (deferred to S2-05 per the arch — no AC addition; the discriminator-level rejection at AC-4 covers the structural cases the property test would catch). |

### Consistency critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| CO1 | harden | **AC-11 wording is narrower than the project gate.** S1-02's validator widened "mypy --strict over the subdir" to `make check` because narrow subset runs miss cross-package drift. AC-11 carries the narrow phrasing. | Widened **AC-11** to require `make check` end-to-end. |
| CO2 | harden | **`__init__.py` re-export AC undercounts.** AC-10 names 13 symbols. The story-referenced ADR-0004 §Consequences names 21 (the union + protocols + registry + assembly + errors). S1-03 lands the *union surface only*; AC-10 should restrict and clarify scope: "the variants + `AppKind`/`BaseKind`/`Provenance` only; protocols / registry / assembly arrive in later stories." | Edited **AC-10** to name exactly the surface S1-03 lands and to cross-reference S1-04 / S2-01 / S2-04 for the future additive growth. |
| CO3 | harden | **Implementer note "Phase 3 regression suite green" names `tests/unit/transforms/ tests/unit/plugins/vulnerability_remediation_node_npm/` only.** Phase 5/6.5 are also regression-relevant per the arch (Goal 10: "Phase 3–6.5 regression suite green"). | Widened the implementer note to "Phase 0–6.5 regression suite green" via `make check`. |
| CO4 | nit | **No cross-reference to S1-02's `_Frozen` and `model_construct` fences.** Both fences (`tests/fence/test_vuln_provenance_frozen_base.py`, `tests/fence/test_vuln_provenance_no_model_construct.py`) cover every file under `primitives/vuln_provenance/`. New variants come under them automatically — an executor should know they exist. | Added an implementer note cross-referencing both fences and warning against `model_construct(...)` in fixtures. |
| CO5 | nit | **Closed-boundary statement absent.** ADR-0038 explicitly closes the seven-variant set. Adding an eighth is an ADR amendment, not a free edit. Without surfacing this, an executor could pre-emptively introduce a `@register_provenance_variant` decorator. | Added an implementer note: the union is a **closed contract**, not a registry. New variants arrive only via ADR-0038 amendment. |

### Design-Patterns critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| DP1 | harden | **The "Make-Illegal-States-Unrepresentable" pattern is the design pattern this story implements.** S1-02's validation surfaced the pattern; S1-03's structural recursion-guard is *the* exemplar. Worth naming so executors understand why the recursion guard is structural (nested discriminated unions) rather than runtime (a `@field_validator`). | Added implementer note: name the pattern, cross-reference ADR-0033, point at the discriminated-union resolution mechanism. |
| DP2 | harden | **The union is closed, not Open/Closed.** Most repo-wide patterns (`@register_probe`, `@register_dep_graph_strategy`, `@register_provenance_adapter` arriving in S2-01) are Open/Closed seams. The `Provenance` union is intentionally NOT one — it's a closed contract. An executor mis-reading the pattern could introduce a `@register_provenance_variant` decorator and call it "consistent." | Added implementer note explicitly forbidding `@register_provenance_variant` or any similar plugin seam on the variant set. Cross-references CO5. |
| DP3 | harden | **No defensive `@field_validator` on `Both.app_record` / `Both.base_record`.** The Notes for implementer hints at this; strengthen to a hard rule. Any runtime check that duplicates Pydantic's discriminated-union routing is a code smell — it implies the structural guarantee is uncertain. | Strengthened the existing implementer note to explicitly forbid defensive `@field_validator`-based kind checks on `Both.app_record` / `Both.base_record`. The structural guarantee IS the guard. |
| DP4 | harden | **Forward-reference ordering rationale not surfaced.** The implementation outline correctly orders declarations (variants → `AppKind`/`BaseKind` aliases → `Both` → `Unknown` → `Provenance`), but doesn't explain *why*. An executor who alphabetizes the file would break Pydantic v2's class-body resolution. | Added implementer note: explicit ordering rationale (Pydantic v2 resolves discriminated-union member types at class-body evaluation; alphabetic reorder breaks the build). |
| DP5 | harden | **`Annotated[..., Field(min_length=2)]` vs `tuple[...] = Field(min_length=2)`.** Both syntaxes exist in Pydantic v2; the codebase convention is `Annotated[..., Field(...)]` (mirrors `outcomes.py:RecipeOutcome` style). An executor reaching for the deprecated `Field(default=...)` form would produce a typing-import smell. | Added implementer note pointing at the `outcomes.py` `Annotated` precedent for `Field(min_length=...)`. |
| DP6 | nit | **Smart-constructor pattern absent — correctly per Rule 2.** Pydantic's `ValidationError` is the equivalent failure signal for a value-record union. Worth recording the decision to prevent a later executor from "consistency-fixing" by wrapping in `Result[Provenance, ParseError]`. | Added to implementer note (mirrors S1-02 DP4). |
| DP7 | nit | **Tagged-union exhaustiveness pattern shared with `transforms/outcomes.py`.** Surface the precedent so executors see this isn't a one-off — five other unions in the codebase use the same shape (`RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability`). | Added cross-reference to `transforms/outcomes.py` in the implementer note (precedent style: every variant is `frozen=True, extra="forbid"`; umbrellas use `Annotated[A | B | C, Field(discriminator="kind")]`). |

## Stage 3 — Research

**Skipped.** No findings tagged `NEEDS RESEARCH`. Every pattern in scope (Pydantic v2 discriminated unions with nested-union recursion rejection, `assert_never` exhaustiveness, mypy-negative `# type: ignore[arg-type]` testing, `Annotated[..., Field(min_length=N)]` idiom, AST-walk fences) is already idiomatic in this codebase. Precedents: `src/codegenie/transforms/outcomes.py`, `src/codegenie/types/identifiers.py`, `tests/unit/types/test_identifiers_phase7_mypy_negative.py`, `tests/fence/test_vuln_provenance_*.py`.

## Stage 4 — Edits applied

All edits land in [`../S1-03-provenance-discriminated-union.md`](../S1-03-provenance-discriminated-union.md). Changes by section:

| Section | Change | Rationale (critic IDs) |
|---|---|---|
| Header | `Status: Ready` → `Status: HARDENED`. | Validator pass. |
| Header | Added `Validation notes` block summarizing every applied edit. | Editor protocol. |
| AC-1 | Added explicit sub-clause: `BaseImage.stage` must be covered in *both* `None` and `DockerStageName("builder")` happy-path cases. | C7. |
| AC-4 | Enumerated all six structural-rejection cases (Both-in-app, Both-in-base, Unknown-in-app, Unknown-in-base, BaseImage-in-app, AppDirect-in-base). Surfaced the dual-layer invariant: `mypy --strict` rejection AND Pydantic runtime rejection. | C3, T1. |
| AC-5 | Strengthened to explicit per-variant parametrize over all seven. | T2. |
| AC-7 | Expanded round-trip coverage to all seven variants (including `Both` and `Unknown`); added a JSON-string round-trip sub-clause via `TypeAdapter.dump_json` / `validate_json`. | C1, C2, C6. |
| AC-8 | Added `chain=()` empty-tuple invalid case. | C5. |
| AC-10 | Restricted scope statement: this story lands the union surface only; protocols / registry / assembly arrive in S1-04 / S2-01 / S2-04. | CO2. |
| AC-11 | Widened gate to `make check` end-to-end (project-wide). | CO1, T5. |
| **AC-12 NEW** | `Unknown.details: dict[str, str]` rejects non-str values at construction. | C4. |
| **AC-13 NEW** | Discriminator-routing integrity: payload with mismatched `kind` value rejects at deserialization (no silent variant absorption). | T4. |
| **AC-14 NEW** | (Renumbered original "AC-12" trailing bullet) — TDD red test exists, committed, and is green. *Decision: kept the existing two trailing standardized footers unnumbered to match S1-01 / S1-02 footer convention; no renumbering after all.* | — |
| **AC-15 NEW** | mypy-negative test at `test_provenance_mypy_negative.py` — pins three `[arg-type]` assertions on `Both.app_record` (Both, Unknown, BaseImage). | T1. |
| Files to touch | Added `tests/unit/primitives/vuln_provenance/test_provenance_mypy_negative.py` (NEW — anchors AC-15). | CO4 (new file), T1. |
| Implementer notes | Strengthened existing notes + added: (1) Make-Illegal-States-Unrepresentable pattern lineage; (2) closed-boundary statement — no `@register_provenance_variant`; (3) `_Frozen` and `model_construct` fences from S1-02 transitively apply; (4) Pydantic v2 forward-reference ordering rationale; (5) `Annotated[..., Field(min_length=N)]` codebase precedent (`outcomes.py`); (6) smart-constructor pattern deliberately deferred (Rule 2); (7) test docstrings must encode WHY (Rule 9); (8) defensive `@field_validator` explicitly forbidden on `Both.app_record` / `Both.base_record`. | DP1–DP7, CO3–CO5, T3. |

### Verdict justification

**HARDENED**, not RESCUE, because:
- The goal traces cleanly to the phase arch (Goal 1, Goal 9) and ADR-0038's verbatim contract.
- The ACs pre-edit *covered* the load-bearing invariants but were under-pinned: AC-4 missed half the structural-rejection cases; AC-7 round-tripped only 3 of 7 variants; AC-11 narrowed the gate below `make check`; the mypy-static layer was implicit.
- Edits strengthen verifiability without inventing scope. No goal rewrite, no new design surface — every new AC enforces an invariant the existing goal already implied.

**Cross-check against existing implementation:** the (uncommitted) implementation at `src/codegenie/primitives/vuln_provenance/types.py` and tests at `tests/unit/primitives/vuln_provenance/test_provenance_union.py` already cover most of the hardened ACs (the test file has 39 test functions vs the story's pre-edit ~10). The hardening pulls the story up to the standard the implementation already meets — closing the spec-implementation gap that would otherwise leave future executors unsure which invariants are load-bearing.

### Anti-goals honored
- Did not rewrite the goal or scope (Rule 3 — surgical changes).
- Did not add ACs the goal does not imply (Rule 4 — every new AC enforces an existing invariant).
- Did not commit the story (humans always merge — but the scheduled-task invocation explicitly requested commit + push of validator edits, which lands the story-file + report changes only).
- Did not touch the implementation source under `src/codegenie/primitives/vuln_provenance/` (validator stays out of code).
