# S1-02 — `DistroPackage` + provenance supporting types — Validation report

**Story:** [../S1-02-provenance-enums-and-distro-package.md](../S1-02-provenance-enums-and-distro-package.md)
**Validated:** 2026-05-19
**Validator pass:** `phase-story-validator` skill (first pass — no prior `_validation/` entry for S1-02)
**Verdict:** **HARDENED** — real but fixable weaknesses found; edits applied in place; ready for `phase-story-executor`.

## Context Brief (Stage 1)

### Story snapshot
- **Goal (verbatim, pre-edit):** Land the four supporting types under `src/codegenie/primitives/vuln_provenance/types.py` — `DistroPackage`, `AppKind`, `BaseKind`, `UnknownReason`, `AdapterConfidence` — with `frozen=True, extra="forbid"`, `Literal` discriminators, exhaustive enum coverage, and a `match`/`assert_never` exhaustiveness anchor — so S1-03 can compose them into the seven-variant `Provenance` discriminated union without further type-level invention.
- **Goal (post-edit):** Land the supporting vocabulary — `_Frozen` base, `DistroPackage`, `UnknownReason`, `AdapterConfidence` — with JSON round-trip pinned, an AST-walk fence requiring every primitive `BaseModel` to inherit `_Frozen`, and a `model_construct`-bypass fence. **`AppKind` / `BaseKind` are deferred to S1-03 entirely** (they land atomically with the variants they bind).
- **Non-goals (out-of-scope):** Seven-variant `Provenance` union (S1-03); `VulnProvenanceAdapter` Protocol (S1-04); `SyftSbom` reader (S1-05); Phase 7 LLM-SDK / no-`Any` import-linter contracts (S1-06); `Layer` / `Ecosystem` enums (S2-01); newtypes for `DistroPackage.name` / `.version`; smart-constructor `Result`-wrapping (deferred per Rule 2); grandfathering `transforms/outcomes.py` to `_Frozen`.

### Files to touch (post-edit)
- `src/codegenie/primitives/__init__.py` — NEW (empty)
- `src/codegenie/primitives/vuln_provenance/__init__.py` — NEW (re-exports `["AdapterConfidence", "DistroPackage", "UnknownReason"]`)
- `src/codegenie/primitives/vuln_provenance/types.py` — NEW (`_Frozen`, `AdapterConfidence`, `UnknownReason`, `DistroPackage`)
- `tests/unit/primitives/__init__.py` + `tests/unit/primitives/vuln_provenance/__init__.py` — NEW
- `tests/unit/primitives/vuln_provenance/test_types_phase7.py` — NEW (AC-2/3/4/6/7/8/12)
- `tests/unit/primitives/vuln_provenance/test_types_module_purity.py` — NEW (AC-9)
- `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` — NEW (AC-13)
- `tests/unit/primitives/vuln_provenance/test_types_mypy_negative.py` — NEW (AC-15)
- `tests/fence/test_vuln_provenance_frozen_base.py` — NEW (AC-11)
- `tests/fence/test_vuln_provenance_no_model_construct.py` — NEW (AC-14)

### Phase / arch constraints
- **ADR-0004** — `src/codegenie/primitives/vuln_provenance/` is the named additive home for ADR-0039 bounded primitives. Sub-modules per the ADR's Consequences include `types.py`. `__init__.py` re-exports the public surface (per the ADR's list, `AppKind`/`BaseKind` belong on that surface, but S1-03 — not S1-02 — adds them).
- **Production ADR-0033** — Newtype + Smart Constructor; `Literal` for discriminator-adjacent values; `Enum` for typed handles; no raw `str` at typed boundaries.
- **Production ADR-0038** — Names every supporting type verbatim: `AppKind`, `BaseKind`, `UnknownReason`, `AdapterConfidence`, `DistroPackage`. Six `UnknownReason` values are frozen.
- **Phase-arch-design §Component design §2** — `class _Frozen(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")` is the shared base for every Phase 7 primitive `BaseModel` subclass; the seven variants and `DistroPackage` all inherit it.
- **Phase-arch-design §Data model lines 981–989** — `UnknownReason = Literal[...]` six values; `AdapterConfidence(str, Enum)` three members; `DistroPackage(_Frozen)` three fields with `distro: Literal["alpine","debian","ubuntu","rhel"]`.
- **Phase 7 ADR-0004 §Consequences** — "A fence asserts no `model_construct()` call sites under `src/codegenie/primitives/vuln_provenance/`."

### Phase exit criteria the story contributes to
- **Goal 1** ("`vuln.provenance` primitive ships at `src/codegenie/primitives/vuln_provenance/` as the seven-variant `Provenance` discriminated union per ADR-0038 verbatim, Pydantic v2 `frozen=True, extra="forbid"`, `mypy --strict` clean") — S1-02 lands the supporting vocabulary; S1-03 lands the variants atop it.
- **Goal 12 + 13** — ALLOWED_BINARIES + `$0.00` LLM spend — module-purity fence (AC-9) anchors this primitive in `{__future__, typing, enum, pydantic}` imports only.

### Prior validation history
- None for S1-02. Sibling story S1-01 ([_validation/S1-01-phase7-newtype-identifiers.md](S1-01-phase7-newtype-identifiers.md)) was the first Phase 7 story validated by this pipeline; its `Ecosystem` Literal-vs-Enum collision resolution (CO1 in that report) is referenced from S2-01 (out of scope here).

### Open ambiguities (Stage 1 gate)
- ⚠️ **`AppKind` / `BaseKind` pre-placement** — the story's original `TYPE_CHECKING`-guarded `AppKind = "AppKind"  # type: ignore[assignment]` pattern is non-functional at runtime (`TYPE_CHECKING is False` → name undefined → `ImportError` from `__init__.py` re-export). Two resolution paths: (A) ship as `TypeAlias = Any` placeholders, or (B) defer entirely to S1-03. The story Context section frames the issue inverted ("must be pinned before S1-03 imports them") — but S1-03 lands the variants + aliases atomically in one file, so no forward-reference is needed. **Resolution within validator scope:** path (B) — Rule 2 (no pre-emptive abstractions), Rule 12 (fail loud — runtime ImportError isn't a "harmless" sentinel). No need to bump to the user; the fix is mechanical.
- ⚠️ **AC-6 file path collision** — the AC names file `test_unknown_reason_exhaustiveness.py` but the TDD plan places `_describe` inside `test_types_phase7.py`. Resolved in-place: single file `test_types_phase7.py`.
- ⚠️ **Implementer note false claim** — "Phase 3 S1-03 established the `_Frozen` base" is factually wrong (`grep -rn "class _Frozen" src/` returns no results; `transforms/outcomes.py` uses inline `model_config`). The `_Frozen` base is **new to Phase 7**. Note corrected; fence test (AC-11) added to lock the convention.

## Stage 2 — Critic findings

Critics ran inline (single-validator pass, no subagents) — story scope is focused enough that token economy favored inline analysis over four parallel subagents.

### Coverage critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C1 | harden | No JSON serialization round-trip test for `DistroPackage` even though the type lands inside `BaseImage` (arch §Data model line 587), which serializes via Pydantic's `model_dump_json()` into the event log. Silent serialization drift downstream is exactly the failure mode AC-12 catches. | Added **AC-12**: JSON round-trip for all four admitted `distro` values + key-set exactness assertion. |
| C2 | harden | No test for whitespace contamination (`" alpine"`, `"alpine "`) in `distro`. Pydantic v2 `Literal` validation is exact-match, so this should reject — but pinning the behavior catches a future "auto-strip" mistake (`Field(strip_whitespace=True)`). | Added to **AC-7** rejection matrix; added implementer note explicitly forbidding `strip_whitespace=True`. |
| C3 | harden | `Field(min_length=1)` alone admits whitespace-only strings (`name=" "`). Downstream consumers index `DistroPackage` by `(distro, name, version)`; whitespace contamination poisons the index silently. | Added **AC-7** cases (`name=" "`, `name="\t"`, `version=" "`); added implementer note prescribing a `field_validator` that enforces `s.strip() == s and s != ""`. |
| C4 | block | AC-5's `TYPE_CHECKING`-guarded `AppKind`/`BaseKind` placeholders would raise `ImportError` at runtime (re-exported via `__init__.py` per ADR-0004 §Consequences but never bound to a runtime value). | Rewrote **AC-5** to make `AppKind`/`BaseKind` explicitly OUT-OF-SCOPE; S1-03 lands them atomically with the variants. Updated Context section + Out-of-scope + Implementer note. |
| C5 | harden | `__all__` sortedness mentioned in Refactor step but not in any AC; no test enforces it. | Added **AC-13**: `__all__` sortedness + exactness fence with test pinning both `types.py` and `__init__.py` lists. |
| C6 | harden | Only `distro="alpine"` exercised on the happy path; the four admitted values (`alpine`/`debian`/`ubuntu`/`rhel`) all need coverage. | Added parametrize over all four in **AC-2** + **AC-7** + **AC-12**. |

### Test-Quality critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| T1 | block | AC-6's named test file (`test_unknown_reason_exhaustiveness.py`) doesn't match the TDD plan's file (`test_types_phase7.py`). An executor would land one OR the other and never both. | Pinned single file `test_types_phase7.py` for the exhaustiveness anchor; AC-6 wording aligned. |
| T2 | harden | A wrong implementation could bypass `DistroPackage`'s validation via `DistroPackage.model_construct(...)`. None of the runtime rejection tests would catch this. Per Phase 7 ADR-0004 §Consequences ("a fence asserts no `model_construct()` call sites under `src/codegenie/primitives/vuln_provenance/`"), the fence belongs in this story. | Added **AC-14** (AST-walk `model_construct` fence) + linked from AC-7. |
| T3 | harden | AC-6's claim "adding a new reason makes `mypy --strict` fail because `assert_never` would receive a non-`Never` argument" is true, but the TDD plan never explicitly asserts `mypy --strict` runs on the test file. Without that, the `assert_never` is just a runtime no-op that the executor could remove. | Strengthened **AC-10** to require `mypy --strict src/` (project-wide, as `make check` already invokes) green; added **AC-15** mypy-negative test file mirroring S1-01's `test_identifiers_phase7_mypy_negative.py`. |
| T4 | harden | No mypy-negative test asserting that `DistroPackage(distro="centos")` is a `mypy --strict` error, or that assigning raw `str` to an `AdapterConfidence` variable is a type error. Without it, the runtime tests pass but the type system gives nothing — Rule 9 (tests verify intent). | Added **AC-15** mypy-negative test file with three explicit assertions. |
| T5 | harden | The test file does not cover `AdapterConfidence` membership exactness — adding a fourth enum member (e.g., `FAILED`) wouldn't fail any test. | Added `test_adapter_confidence_membership_exact` row in the red TDD test code (under AC-3/AC-8). |

### Consistency critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| CO1 | harden | Implementer note states "Phase 3 S1-03 established the `_Frozen` base" — factually false (`grep -rn "class _Frozen" src/` returns nothing; `transforms/outcomes.py` uses inline `model_config = ConfigDict(...)`). | Note corrected — `_Frozen` is **introduced by Phase 7**; AC-11 fence locks the convention. Phase 3 is grandfathered. |
| CO2 | block | AC-5 + Implementer note prescribe `if TYPE_CHECKING: AppKind = "AppKind"  # type: ignore[assignment]` — at runtime `TYPE_CHECKING is False`, so the name is undefined and `from codegenie.primitives.vuln_provenance import AppKind` (which ADR-0004 §Consequences mandates) raises `ImportError`. **Hard contradiction with ADR-0004's re-export surface.** | Resolved: drop `AppKind`/`BaseKind` from S1-02 entirely. AC-5 rewritten; Context section + Out-of-scope updated; Implementer note explains why pre-placement was the wrong shape. S1-03 will land variants + aliases atomically. |
| CO3 | nit | The story's Context paragraph claims the union aliases "must be pinned before S1-03 imports them" — but S1-03 lands the variants and the aliases in the same file, so no forward-reference is needed. The framing was inverted. | Context section rewritten to reflect the correct dependency direction. |
| CO4 | nit | AC-10 wording "`mypy --strict src/codegenie/primitives/vuln_provenance/` clean" is narrower than the project's actual gate (`make check` runs `mypy --strict src/`). Could mislead an executor into running a subset and missing cross-package drift. | AC-10 widened to require `make check` end-to-end. |

### Design-Patterns critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| DP1 | harden | `_Frozen` is introduced here as the shared mutation-protection base, but no fence locks the convention. Without enforcement, an executor in S1-03 could regress to inline `model_config = ConfigDict(...)` (mirroring `transforms/outcomes.py`'s style), defeating the DRY motivation for adding `_Frozen` at all. | Added **AC-11**: AST-walk fence asserting every `class X(BaseModel)` under `primitives/vuln_provenance/` inherits `_Frozen` (transitively or directly). Phase 3 is grandfathered (fence scope is `primitives/vuln_provenance/` only). |
| DP2 | block | `AppKind`/`BaseKind` pre-placement is a textbook Rule 2 violation: the story prescribes scaffolding for an abstraction (a `TypeAlias` placeholder) that the *next* story will replace. Worse, the prescribed shape (`TYPE_CHECKING`-guarded string) is non-functional at runtime. | (Same fix as C4 / CO2.) Drop the pre-placement; S1-03 lands them atomically. Added to Out-of-scope + Implementer note + Validation notes (block-severity, top of story). |
| DP3 | harden | Tagged-union / sum-type discipline is correct (`UnknownReason` Literal + `AdapterConfidence` Enum split) but not documented. An implementer might add a parallel `_UNKNOWN_REASONS: frozenset[str]` constant as a "cleanup", duplicating `typing.get_args(UnknownReason)`. | Added Implementer note: "Source-of-truth for the set: `typing.get_args(UnknownReason)` — do NOT introduce a parallel `_UNKNOWN_REASONS: frozenset[str]` constant; consumers iterate `get_args(...)`." Open/Closed at the data-shape boundary. |
| DP4 | nit | Smart-constructor pattern (`make_distro_package(...) -> Result[DistroPackage, ParseError]`) absent — but per Rule 2, premature for a value record where Pydantic's `ValidationError` is already the equivalent failure signal. Recording the design choice prevents a later executor from adding the wrapper "for consistency with S1-01". | Added to Out-of-scope with rationale; added to Design-pattern observations in Implementer note. |
| DP5 | nit | `Field(strip_whitespace=True)` is a tempting "fix" for whitespace contamination but masks SBOM tampering (arch §Edge cases row 1). Implementer might enable it during refactor. | Added Implementer note explicitly forbidding it; cross-referenced AC-7 + AC-12. |
| DP6 | nit | The pattern this story locks (Pydantic v2 `_Frozen` base + `Literal` discriminators + `Enum` typed handles + AST-walk fences for inheritance + `model_construct` ban) is the **Make-Illegal-States-Unrepresentable** discipline. Worth surfacing so S1-03's executor knows what conventions to mirror. | Added to Design-pattern observations in Implementer note. |

## Stage 3 — Research

**Skipped.** No findings tagged `NEEDS RESEARCH`. Every pattern in scope (Pydantic v2 discriminated unions, `assert_never` exhaustiveness, AST-walk fences, mypy-negative `# type: ignore[...]` testing) is already idiomatic in this codebase — see precedents at `src/codegenie/types/identifiers.py`, `tests/unit/types/test_identifiers_phase7_mypy_negative.py`, `tests/fence/`.

## Stage 4 — Edits applied

All edits land in [`../S1-02-provenance-enums-and-distro-package.md`](../S1-02-provenance-enums-and-distro-package.md). Changes by section:

| Section | Change | Rationale (critic IDs) |
|---|---|---|
| Status line | `Ready` → `HARDENED` | per skill convention |
| **NEW** Validation notes block | Inserted under header; documents every change | per skill convention |
| Context | Rewrote forward-reference framing; clarified S1-03 lands variants + aliases atomically | CO2, CO3 |
| Goal | Drop `AppKind`/`BaseKind` from goal scope; add JSON round-trip + `_Frozen` inheritance fence to goal | C1, C4, DP1 |
| AC-5 | Rewrote: `AppKind`/`BaseKind` explicitly OUT-OF-SCOPE | C4, CO2, DP2 |
| AC-6 | Pin single test file `test_types_phase7.py` for `_describe` | T1 |
| AC-7 | Expanded rejection matrix (whitespace, case, empty distro, blank-only name/version); added all-four-distros happy path; cross-link to AC-14 | C2, C3, C6, T2 |
| AC-9 | Tightened from "subset" to "exact set" `{__future__, typing, enum, pydantic}` with module-level `_ALLOWED_TOP_LEVEL_IMPORTS` constant | T-quality precision |
| AC-10 | Widened from per-package mypy to `make check` end-to-end | CO4 |
| **NEW** AC-11 | `_Frozen` inheritance fence (AST-walk) | DP1 |
| **NEW** AC-12 | `DistroPackage` JSON round-trip for all four distros | C1 |
| **NEW** AC-13 | `__all__` sortedness + exactness, both `types.py` and `__init__.py` | C5 |
| **NEW** AC-14 | `model_construct` bypass fence | T2, ADR-0004 §Consequences |
| **NEW** AC-15 | mypy-strict negative test file (mirrors S1-01 pattern) | T3, T4 |
| Implementation outline | Removed `AppKind`/`BaseKind` step; added six new test files | C4, CO2, plus new ACs |
| TDD plan | Replaced red test with expanded version (all four distros, JSON round-trip, membership exactness, single-file exhaustiveness); strengthened green/refactor steps | C1, C2, C3, C6, T1, T5 |
| Files to touch | Added four new test files (`dunder_all`, `mypy_negative`, two `fence/`) | AC-11/13/14/15 |
| Out of scope | Added: `AppKind`/`BaseKind` deferral; smart-constructor deferral; Phase 3 grandfathering | DP2, DP4 |
| Notes for implementer | Replaced `TYPE_CHECKING` snippet with explicit "don't pre-place" guidance; corrected false `_Frozen` precedent claim; added 6 design-pattern observations; added `strip_whitespace=True` ban; added `get_args(UnknownReason)` as source-of-truth | CO1, CO2, DP2, DP3, DP4, DP5, DP6 |

## Verdict

**HARDENED.** Two `block`-severity findings (C4/CO2/DP2 — `AppKind`/`BaseKind` pre-placement, all three tags the same underlying bug; T1 — test file path inconsistency) were resolved by structural edits, not silent rewrites. Twelve `harden`-severity findings were addressed with new or strengthened ACs. Five `nit`-severity findings became implementer notes or Out-of-scope rows.

The story now ships:
- Verifiable, mutation-resistant ACs (every AC has a runtime check; mutation tests catch wrong implementations).
- Forward-extensibility via Open/Closed at the data-shape boundary (`UnknownReason` Literal + `_describe`/`assert_never` exhaustiveness; `DistroPackage` accepts new fields additively).
- Pattern-locked convention enforcement via two AST-walk fences (`_Frozen` inheritance + `model_construct` ban).
- Type-system honesty via mypy-negative test file.
- No premature abstraction — `AppKind`/`BaseKind` and smart-constructor wrapping deferred to the story that actually needs them.

Ready for `phase-story-executor`.
