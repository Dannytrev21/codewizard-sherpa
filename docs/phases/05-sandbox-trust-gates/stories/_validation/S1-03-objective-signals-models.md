# Validation report — S1-03 `ObjectiveSignals` + six sub-models + `SignalProvenance`

**Story:** [`../S1-03-objective-signals-models.md`](../S1-03-objective-signals-models.md)
**Validated:** 2026-05-17
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S1-03 ships the strict-AND surface of Phase 5 — `SignalProvenance`, an internal `_SignalBase`, six concrete frozen `extra="forbid"` sub-models (`BuildSignal`, `InstallSignal`, `TestSignal`, `TraceSignal`, `PolicySignal`, `CveDeltaSignal`), and `ObjectiveSignals` — plus the recursive walker that ADR-0014's `tests/schema/test_objective_signals_static.py` fence (lands in S1-07) and Phase 7's extension stories will reuse. The draft was structurally correct: goal traced to arch §Data model + §Agentic best practices + Open Q9 + the four honored ADRs; out-of-scope discipline (collectors → Step 4, registry → S1-05, fence → S1-07, asymmetric delta logic → S4-02) clean; field shapes byte-exact against arch pseudo-code.

But it had **15+ weaknesses** spanning all four critic lenses. Most consequentially:

1. **Coverage C-3 / Tests M-10 / Patterns P-7 (block-tier):** the walker's descent through `Optional[X]` was unenforced — and *every* `ObjectiveSignals` field is `Submodel | None = None`. A walker that ignored `Union[X, None]` would yield only the six container field names; none contain a forbidden substring; CI would pass; ADR-0014 silently dead. The draft Notes proposed a synthetic-fixture sanity check but instructed "Remove the synthetic before committing" — the exact inversion of Rule 9 ("tests verify intent, not behavior"). The hardened plan ships **permanent** synthetic holders (W-1 Optional, W-2 dict-V, W-3 case-insensitivity, W-4 recursion termination) as the walker's mutation tests.
2. **Coverage C-1 / Tests M-1-M-3 (block-tier):** `extra="forbid", frozen=True` was tested only behaviourally on `BuildSignal`. Five sibling sub-models + `SignalProvenance` + `ObjectiveSignals` could have shipped `extra="ignore"` or `frozen=False` silently. Mirrors S1-02's same gap; same fix (parametrize over all 8 + direct `model_config` introspection).
3. **Coverage C-2 / Consistency #5 / Patterns P-1 (block-tier):** `SignalProvenance.signal_kind` open-registry posture was unpinned. ADR-0003 widens kinds to an *open string*; the draft type was bare `str` with no AC rejecting a closed `Literal`. A naive executor reading the six current kinds would naturally write `Literal["build","install","tests","trace","policy","cve_delta"]` and break Phase 7's `baseimage`/`shell_presence` extension.
4. **Patterns P-1 / Consistency #4 (harden):** `SignalKind` newtype is overdue. CLAUDE.md ("newtype when crossing ≥ 2 modules") + S1-02 precedent (`RunId`, `SandboxSpecHash`) + arch line 721 (`SignalKind = str` placeholder in gates/contract.py) + rule-of-three cleared at 6 module boundaries. Promoted to `src/codegenie/types/identifiers.py` now so S1-04 picks it up cleanly; landing later forces post-hoc rewrites.
5. **Patterns P-3 (harden):** the walker was prescribed as a `_`-prefixed "small public helper" co-located in `models.py`. That's contradictory (private convention + cross-module reuse) and the wrong frame — the walker is the trust anchor for ADR-0014 across Phase 5, Phase 7 (`baseimage`/`shell_presence`), and Phase 11 (evidence-bundle field screening). Extracted to `sandbox/signals/_introspection.py` with public `iter_nested_field_names`. Module-private file (purity) + public function (cross-module reuse legit).
6. **Tests M-14 / Consistency #9 (harden):** `bool` ⊂ `int` Python ambiguity + Pydantic 2 non-strict float-coercion to int + Pydantic's union-order behavior. The draft `test_details_accepts_str_int_bool` checked `s.details == {"b": True}` — but `True == 1` in Python, so a `bool`-to-`int` coercion would pass. The hardened plan asserts `type(s.details["b"]) is bool`, adds `strict=True` to `model_config`, and adds a `@field_validator("details", mode="after")` doing runtime type-identity checks.
7. **Patterns P-6 / Coverage C-5 (harden):** `at: datetime` accepts naive datetimes. Phase 5 evidence bundles + `RetryLedger` BLAKE3 chain ordering + Phase 13 telemetry break on naive timestamps across operator timezones. Tightened to `at: AwareDatetime`; parametrized rejection test across all six.
8. **Consistency #1 (harden):** coverage floor wording bug (same as S1-02): "Branch ≥ 95%" vs README's "95 line / 90 branch." Rewritten.

17 hardening edits applied in place; no `RESCUE`-tier findings (every gap was patchable by adding ACs, tightening tests, and extracting the walker — not by re-architecting goal or scope). No Stage-3 research needed — every gap was answerable from the four honored ADRs (-0014, -0008, -0015, -0003), arch §Data model + §Agentic best practices + §Open Q9, CLAUDE.md (Extension by addition, Newtype identifiers, Functional core / imperative shell, Rule 9, Rule 11), and codebase precedents (`src/codegenie/result.py`, `src/codegenie/types/identifiers.py`, `src/codegenie/probes/language_detection.py` `_WARNING_IDS` pattern, S1-02's HARDENED report).

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim, hardened):** Ship `src/codegenie/sandbox/signals/models.py` with `SignalProvenance`, an internal `_SignalBase`, six concrete frozen `extra="forbid", strict=True` sub-models (`BuildSignal`, `InstallSignal`, `TestSignal`, `TraceSignal`, `PolicySignal`, `CveDeltaSignal`), and the `ObjectiveSignals` container — with no field name (transitively) containing a forbidden substring. Ship the recursive introspection walker as a public function `iter_nested_field_names` in a sibling module `sandbox/signals/_introspection.py`. Promote `SignalKind = NewType("SignalKind", str)` to `src/codegenie/types/identifiers.py`.
- **Non-goals (from Out-of-scope):** structural CI fence test under `tests/schema/` (S1-07), signal collectors (Step 4), `@register_signal_kind` decorator (S1-05), `StrictAndGate.evaluate` (S4-05), asymmetric `delta_test_count < 0` failure logic (S4-02 + ADR-0015), always-emit invariant on `delta_test_count` (S4-02), `SignalKind` registry uniqueness check (S1-05), `inputs_blake3` hex-shape validation (deferred to collector, mirrors S1-02 `sandbox_spec_hash` precedent).

### Phase 5 exit criteria touched

- Step 1 done-criteria (High-level-impl.md §Step 1): `pytest tests/sandbox/test_signal_models.py tests/sandbox/test_objective_signals_introspection.py tests/sandbox/test_signals_purity.py` green; `mypy --strict src/codegenie/sandbox src/codegenie/gates` clean; line ≥ 95% AND branch ≥ 90% on `signals/models.py` AND `signals/_introspection.py`.
- Goal 8 (arch line 23): `ObjectiveSignals` Pydantic `extra="forbid", frozen=True`; CI introspection asserts no field name contains the four banned substrings.
- ADR-0014 enforcement-by-code: this story owns the *type surface* + the *walker*; S1-07 owns the *fence test under `tests/schema/`*.
- ADR-0003 open-registry posture: `signal_kind` is open string (NOT closed Literal); `ObjectiveSignals` widens additively per ADR amendment.
- ADR-0015 `delta_test_count` semantics: model permits the integer at any sign; collector (S4-02) owns the asymmetric policy.

### Load-bearing commitments touched

- **CLAUDE.md "Extension by addition"** — new signal kind = `@register_signal_kind` + additive optional field on `ObjectiveSignals` + ADR amendment; never edit existing sub-models. The walker is the kernel that must keep working under additive widening.
- **CLAUDE.md "Domain identifiers ... newtype when crossing ≥ 2 modules"** — `SignalKind` crosses ≥ 6 module boundaries.
- **CLAUDE.md "Functional core / imperative shell"** — `signals/models.py` and `_introspection.py` are pure (no I/O, no logger, no methods on models beyond `field_validator`); the collectors (Step 4) are the imperative shell.
- **CLAUDE.md Rule 9 (tests verify intent, not behavior)** — the walker mutation tests (permanent synthetic holders) verify INTENT: "the walker descends through Optional / dict-V / mixed case / recursion." Without them the introspection test verifies only behavior on today's clean surface, not the property the test exists to enforce.
- **CLAUDE.md Rule 11 (match conventions)** — `from __future__ import annotations`, module docstring naming ADRs, `__all__` discipline, module-purity invariant — all established by Phase 0/1/2 (`result.py`, `adapters/protocols.py`, S1-02 HARDENED report).
- **ADR-0014** — `extra="forbid", frozen=True` + recursive introspection + four banned substrings. The most-attacked invariant in the phase.
- **ADR-0008** — no LLM judgment fields anywhere in the trust graph; enforced by code (the substring check), not prose.
- **ADR-0015** — `delta_test_count` is always-emitted at collector site; the model permits omission (boundary clarification).
- **ADR-0003** — open signal-kind registry; `signal_kind: SignalKind` (NewType over `str`), NOT `Literal[...]`.

### Open/Closed boundaries (extension-by-addition contract)

- **New signal kind** (Phase 7 `baseimage`, `shell_presence`) → new sub-model + new optional field on `ObjectiveSignals` + `@register_signal_kind` (S1-05) + ADR amendment. ZERO edits to existing sub-models or to the walker.
- **New `details` key** → no schema change required (`details` is open `dict[str, str | int | bool]`). Module-level `Final[frozenset[str]]` catalogs in Notes document known keys for discoverability; collectors append to their own catalog.
- **New forbidden substring on the ADR-0014 fence** → S1-07 (fence test). This story's walker is substring-agnostic — it yields field names; the test's FORBIDDEN tuple is the matcher. New substrings = new tuple entry in S1-07.

### Codebase precedents consulted

- `src/codegenie/result.py` — frozen + `extra="forbid"` + module-purity invariant + module docstring with ADR cross-references. Mirrored.
- `src/codegenie/types/identifiers.py` — `NewType` pattern; single declaration site rule. `SignalKind` lands here per the docstring's discipline.
- `src/codegenie/probes/language_detection.py` `_WARNING_IDS: Final[frozenset[str]]` — module-level catalog pattern. Surfaced as a Notes-only forward seam for `_TEST_SIGNAL_DETAIL_KEYS` etc.
- `src/codegenie/output/redacted_slice.py` `model_validator(mode="after")` — smart-constructor pattern. Used here for `field_validator("details", mode="after")`.
- `tests/property/test_sum_types_roundtrip.py` — hypothesis property test against frozen Pydantic. Pattern reused for the `details` non-primitive rejection property test.
- S1-02 HARDENED report (`_validation/S1-02-sandbox-contract-protocol-models.md`) — coverage-floor wording bug, newtype precedent, `test_contract_purity.py` precedent, parametrized model_config introspection precedent. All transferred.

### Open ambiguities (resolved before Stage 2)

- **Walker location: same module as `models.py`, or sibling `_introspection.py`?** Resolved as sibling `_introspection.py` per Patterns P-3. Rationale: the walker is the trust anchor for ADR-0014 across Phase 5/7/11; calling it a "small public helper" in `models.py` understates its role; the `_` prefix on the function name + cross-module reuse is contradictory.
- **`SignalKind` location: `types/identifiers.py` (kernel-tier) or `sandbox/signals/models.py` (sandbox-local)?** Resolved as `types/identifiers.py`. Rationale: ≥ 6 module boundaries; arch line 721's `SignalKind = str` placeholder in `gates/contract.py` (S1-04) becomes `from codegenie.types.identifiers import SignalKind`; the types module's "single declaration site" docstring is unambiguous.
- **Float-coercion / bool-int ambiguity: strict mode OR field validator OR both?** Resolved as both (belt-and-suspenders). `strict=True` blocks most coercions at parse time; the `field_validator("details", mode="after")` does the runtime `type(v) in {str, int, bool}` check that catches `Decimal`/`Enum`/`complex` and disambiguates `bool` ⊂ `int`.
- **Timezone-aware datetime: `AwareDatetime` or hand-rolled `Annotated[...]`?** Resolved as `AwareDatetime` (Pydantic 2 built-in). Cleaner; supports JSON round-trip; lives on `_SignalBase` for inheritance.
- **`delta_test_count` model-side enforcement?** Resolved as no. ADR-0015's "always emitted, even when zero" is a *collector* invariant. The model permits omission; S4-02 enforces. AC text clarifies the boundary.

## Stage 2 — critic reports

### 2A · Coverage critic (verdict: COVERAGE-HARDEN)

15 findings, 3 block-tier:

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| **C-1** | **block** | **`extra="forbid", frozen=True` enforced only behaviourally on `BuildSignal`.** Five sibling sub-models + `SignalProvenance` + `ObjectiveSignals` could ship `extra="ignore"` / `frozen=False` silently. | **AC-2 + AC-2a + AC-2b + AC-2c parametrize over all 8 public models; direct `model_config` dict introspection asserted explicitly.** |
| **C-2** | **block** | **`SignalProvenance.signal_kind` open-registry posture unpinned.** Naive executor would close to `Literal[...]`; breaks Phase 7 extension. | **AC-4 + AC-4a + AC-4b + AC-4c assert `SignalKind` NewType, reject `Literal` origin, positive-construction with `"baseimage"`/`"shell_presence"`, AST scan forbidding redefinition.** |
| **C-3** | **block** | **Walker `Optional[X]` descent unenforced.** `ObjectiveSignals` fields all `Submodel | None`; shallow walker = vacuous test. | **AC-8b ships 4 permanent synthetic models (W-1 Optional, W-2 dict-V, W-3 case-insensitivity, W-4 recursion termination) as walker mutation tests.** |
| C-4 | harden | `__all__` exactness unenforced (`_SignalBase`, walker function exclusion). | AC-1b + AC-1c byte-exact set equality; both modules' `__all__` pinned. |
| C-5 | harden | Timezone-awareness on `at` unenforced. | AC-6 + AC-6a parametrize naive-rejected / aware-accepted across the six. |
| C-6 | harden | `details` value-type policy missing `Decimal`/`bool`-vs-`int`/`complex`/`Enum` checks. | AC-5 parametrize extended; AC-5a asserts `type(v) is bool` vs `type(v) is int`; AC-5d hypothesis property covers the open set. |
| C-7 | harden | JSON round-trip / canonical-dump shape unpinned. | AC-9a parametrizes round-trip across all six; AC-9b covers `ObjectiveSignals`. |
| C-8 | harden | Walker invocation only on empty `ObjectiveSignals`; type-driven-not-instance-driven property unstated. | AC-8 asserts both invocations yield same set. |
| C-9 | harden | Coverage floor wording ("Branch ≥ 95%" vs README's "95 line / 90 branch"). | AC-13 rewritten as "line ≥ 95% AND branch ≥ 90%." |
| C-10 | harden | Hash + equality semantics on frozen models unpinned. | AC-9 added — set membership / hash equality. |
| C-11 | harden | `SignalProvenance.inputs_blake3` type-pinning absent. | AC-3c byte-exact annotation set. Hex-shape validation deferred to collector (mirrors S1-02 `sandbox_spec_hash` precedent). |
| C-12 | harden | Sub-model field-set exactness unenforced. | AC-3 / AC-3a / AC-3b parametrize set equality. |
| C-13 | harden | `ObjectiveSignals` literal field names unenforced (typo path). | AC-3a + AC-3f byte-exact set + annotation pinning. |
| C-14 | nit | `_SignalBase` package-level surface absence unenforced. | AC-1d covers. |
| C-15 | nit | `delta_test_count` scope clarification absent. | AC-7c text + Notes paragraph clarify collector-side responsibility per ADR-0015 §Consequences. |

### 2B · Test-quality critic (verdict: TESTS-HARDEN)

20 mutations evaluated. Headline misses caught by the harden:

| # | Wrong implementation | Caught by draft TDD? | Caught after harden? |
|---|---|---|---|
| M-1 | Sub-model omits `model_config` (relies on inheritance) | No — only `BuildSignal` tested | Yes — parametrized over all 6 + AC-2a explicit class-body declaration |
| M-2 | One sub-model ships `extra="ignore"` | No — only `BuildSignal` tested | Yes — parametrized |
| M-3 | `frozen=False` on `SignalProvenance` / `ObjectiveSignals` | No — only `BuildSignal` tested | Yes — parametrized over all 8 |
| M-4 | `details: dict[str, Any]` | Partial — runtime tests would catch some values | Yes — `get_type_hints` annotation pin |
| M-5 | `details: dict[str, str \| int \| float \| bool]` | Partial — `3.14` rejected at runtime but `3.0` may coerce | Yes — annotation pin + `strict=True` + field_validator + `3.0` in parametrize list |
| **M-6** | **`signal_kind: Literal["build","install",...,...]`** | **No** | **Yes — AC-4a rejects Literal origin; AC-4b positive `"baseimage"`** |
| **M-7** | **`at: datetime` (naive)** | **No** | **Yes — `AwareDatetime` + AC-6 parametrized rejection** |
| **M-8** | **Walker yields only top-level field names (no recursion)** | **No** | **Yes — AC-8b W-1 with `_OptHolder._ForbiddenInner`** |
| **M-9** | **Walker doesn't descend dict[K, V]** | **No** | **Yes — AC-8b W-2 `_DictHolder`** |
| **M-10** | **Walker doesn't descend `Union[X, None]`** | **No (most critical hole)** | **Yes — AC-8b W-1; every `ObjectiveSignals` field is `Submodel | None`** |
| M-11 | Case-sensitive substring check | No | Yes — AC-8b W-3 `_UpperHolder.Confidence` |
| M-12 | `_SignalBase` / walker exported via `__all__` | No | Yes — AC-1b / AC-1c |
| M-13 | `ObjectiveSignals` declares early `baseimage` field | Partial | Yes — AC-3a byte-exact set |
| **M-14** | **`details={"k": True}` coerced to `1`** | **No (== comparison passes)** | **Yes — AC-5a asserts `type(v) is bool`** |
| M-15 | `delta_test_count` model-side enforcement | n/a (deferred to S4-02) | Acceptable; Notes clarifies |
| **M-16** | **Walker infinite-loops on recursive model** | **No** | **Yes — AC-8b W-4 `_Recur` model** |
| M-17 | Hypothesis property absent | No | Yes — AC-5d |
| M-18 | JSON round-trip absent | No | Yes — AC-9a + AC-9b |
| M-19 | `signal_kind` raw `str` (no NewType) | No | Yes — AC-4 + AC-4a (NewType + canonical home) |
| M-20 | Walker has hidden I/O | No (overkill) | AC-10 module-purity AST scan handles |

The Notes paragraph that said "remove the synthetic before committing" was **inverted** — kept as permanent in-test-file holders (W-1..W-4). They are the mutation tests for the walker itself; deleting them removes the only positive proof that the walker isn't vacuous.

### 2C · Consistency critic (verdict: CONSIST-HARDEN)

12 findings — all patchable in place; no contradiction with arch, ADRs, or production design:

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| 1 | harden | Coverage floor wording (`Branch ≥ 95%` vs README `95 line / 90 branch`) | AC-13 rewritten as "line ≥ 95% AND branch ≥ 90%." |
| 2 | harden | `from __future__ import annotations` not at AC level | AC-1a asserts via AST scan. |
| 3 | harden | Module docstring + `__all__` discipline not at AC level | AC-1a + AC-1b. |
| 4 | harden | `SignalKind` newtype missing (≥ 6 modules) | Promoted to `types/identifiers.py`; AC-4 + AC-4a + AC-4b + AC-4c. |
| 5 | harden | `signal_kind` open-registry posture unpinned | Same as Coverage C-2 / Patterns P-1; AC-4a rejects `Literal` origin. |
| 6 | harden | `coverage_evidence_strength` rename docstring-only | Refactor step + Notes documents in `TraceSignal.__doc__`; deferred from AC level (docstring is not testable beyond presence). Optional Forward seam in catalogs. |
| 7 | harden | Walker naming vs cross-module reuse | Extracted to `sandbox/signals/_introspection.py` (Patterns P-3); function name public (`iter_nested_field_names`). |
| 8 | harden | Banned-substring case-sensitivity unspecified | AC-8a documents `.lower()` normalization; AC-8b W-3 verifies. |
| 9 | harden | Float-coercion / bool-int gap in Pydantic 2 | `strict=True` + `field_validator("details", mode="after")`; AC-5a + AC-5b. |
| 10 | nit | Test paths `tests/sandbox/` consistent | ✓ no fix |
| 11 | nit | `Mapping` not used | ✓ no fix |
| 12 | harden | Fence-test non-regression AC absent | AC-14 documents. |

### 2D · Design-patterns critic (verdict: PATTERNS-HARDEN)

7 promote-to-AC + 3 note-only:

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| **P-1** | **harden** | **Primitive obsession on `signal_kind: str` — ≥ 6 module boundaries** | **`SignalKind = NewType("SignalKind", str)` in `types/identifiers.py`; AC-4 + AC-4a + AC-4b + AC-4c.** |
| P-2 | harden | `_SignalBase` inheritance fragility unenforced (Pydantic v2 config drift) | AC-2a parametrizes "each sub-model declares `model_config` in own class body." |
| P-3 | harden | Walker is a real abstraction, not a "small helper" — kernel for ADR-0014 / Phase 7 / Phase 11 | Extracted to `sandbox/signals/_introspection.py`; public `iter_nested_field_names`; AC-1, AC-1c, AC-8c. |
| P-4 | harden | Module-purity invariant not asserted | AC-10 AST scan; mirrors S1-02 `test_contract_purity.py`. |
| P-5 | harden | Anaemic `details` dict — known keys live in prose only | Module-level `Final[frozenset[str]]` catalogs surfaced in Notes (informational; not enforced; extension-friendly). Pattern: `probes/language_detection.py` `_WARNING_IDS`. |
| P-6 | harden | Timezone-aware `at` unenforced | `AwareDatetime` on `_SignalBase`; AC-6 + AC-6a. |
| P-7 | harden | "Remove the synthetic before committing" inverted Rule 9 | Inverted: permanent in-test-file synthetic holders (W-1..W-4) ship as walker mutation tests. |
| P-8 | note-only | `ObjectiveSignals` record-not-list shape is correct | Notes documents the rationale. |
| P-9 | note-only | `Blake3Hex` newtype deferred to collector | Notes forward-seam (mirrors S1-02 `sandbox_spec_hash`). |
| P-10 | note-only | Phase 7 widening worked example | Notes forward-seam. |

## Conflict resolution (Stage 4 synthesizer)

- **Coverage C-11 (hex shape on `inputs_blake3`) vs Patterns P-9 (defer to collector):** Patterns wins per S1-02 precedent — contract envelope stays opaque; shape validation lives at the collector site. Documented in Out of scope + Notes forward-seam.
- **Patterns P-3 (walker as own module) vs Consistency #7 (keep underscore or rename):** Patterns wins. The walker is the kernel for ADR-0014 across Phase 5/7/11; co-locating in `models.py` understates its role. Resolution: module-private file (`_introspection.py`), public function (`iter_nested_field_names`).
- **Patterns P-5 (Final catalogs for details keys) vs Rule 2 (no premature abstraction):** Compromise — catalogs surfaced in Notes for the implementer (Forward seam), NOT promoted to AC. Informational discoverability; collector authors (S4-02..S4-06) consume; extension-by-addition stays clean.
- **Consistency #9 (strict mode vs field validator) — not a conflict, complementary:** both applied. `strict=True` blocks parse-time coercion; `field_validator("details", mode="after")` does runtime type-identity check for `bool` ⊂ `int` and exotic types (`Decimal`, `complex`, `Enum`).
- **Coverage C-2 / Consistency #5 / Patterns P-1 — all converge:** `SignalKind` NewType in `types/identifiers.py`; one fix lands all three.
- **Tests M-15 (`delta_test_count` model-side enforcement) vs ADR-0015 §Consequences (collector-side invariant):** ADR-0015 wins. Model permits omission; collector enforces. Notes paragraph clarifies the boundary; AC-7c documents.

## Edits applied (summary)

1. New `Validation notes` block under the story header with 17 numbered headline edits.
2. **Status** updated: `Ready` → `Ready (HARDENED 2026-05-17)`.
3. **References** expanded with codebase precedents (`result.py`, `types/identifiers.py`, `probes/language_detection.py`, S1-02 validation report).
4. **Goal** rewritten to include the walker extraction (`_introspection.py`) and the `SignalKind` NewType promotion to `types/identifiers.py`.
5. **Acceptance criteria** rewritten from 9 ACs to 27 ACs (grouped A–K): import surface + module hygiene; `model_config` discipline (parametrized); field sets + annotation pinning; `signal_kind` open-registry; `details` value-type policy + bool/int disambiguation + property test; timezone-aware `at`; `ObjectiveSignals` shape; introspection walker (with permanent W-1..W-4 mutation tests); equality / hash / JSON round-trip; module purity; process gates.
6. **Implementation outline** rewritten from 7 numbered steps to 11 with explicit code-level prescriptions: `from __future__ import annotations`, module docstring, `SignalKind` in `types/identifiers.py` first, walker in `_introspection.py` second, `strict=True` in `model_config`, `@field_validator("details", mode="after")`, each sub-model re-declares `model_config`, `AwareDatetime` on `_SignalBase`.
7. **TDD plan** rewritten from 2 test files (~80 LOC) to 3 test files (~370 LOC) with parametrized fixtures across all 8 models, hypothesis property test, JSON round-trip, annotation pinning via `get_type_hints`, walker mutation suite with 4 permanent synthetic holders, module-purity AST scan.
8. **Files to touch** updated: added `src/codegenie/sandbox/signals/_introspection.py`, `src/codegenie/types/identifiers.py` (extension), `tests/sandbox/test_signals_purity.py`.
9. **Out of scope** updated: explicit on `delta_test_count` always-emit invariant (S4-02), `SignalKind` registry uniqueness (S1-05), `inputs_blake3` hex-shape (collector), mypy negative-typecheck infra (deferral if absent).
10. **Notes for the implementer** rewritten and 3× longer: Pydantic v2 `model_config` drift across subclasses, `bool` ⊂ `int` + `strict=True` + field validator rationale, walker visited-set ordering (mistake = infinite loop), walker debug technique, `SignalKind` canonical home + arch line 721 cleanup forward note, `AwareDatetime` choice, coverage discipline, module purity, `__all__` discipline, and three forward-seam notes (Final catalogs P-5, Phase 7 widening P-10, `Blake3Hex` P-9).

No story restructuring; goal, scope, dependencies (S1-01), out-of-scope discipline, and ADR mapping (-0014, -0008, -0015, -0003) are unchanged.

## Final verdict

**HARDENED.** Story ready for `phase-story-executor`. Every AC is individually verifiable; the AC set collectively guarantees the Goal 8 / ADR-0014 enforcement-by-code commitment and the ADR-0003 open-registry posture; every test in the TDD plan would fail on at least one named mutation (especially the M-10 / M-14 / M-16 / M-7 holes the draft missed); CLAUDE.md Rule 11 (codebase convention), Rule 9 (intent-not-behavior), and the load-bearing "Extension by addition" + "Newtype identifiers" + "Functional core / imperative shell" commitments are honored; the walker is now a first-class abstraction owned by `_introspection.py` (the trust anchor that Phase 5 / 7 / 11 share); `SignalKind` NewType is in its canonical kernel-tier home before S1-04 / S1-05 need it; the closed-`Literal`-as-tightening trap is documented as a forward seam, not silently widened.
