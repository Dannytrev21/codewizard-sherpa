# Validation report — S2-03 Reference TCCM + roundtrip integration exercising every Protocol method

**Story:** [`../S2-03-reference-tccm-roundtrip.md`](../S2-03-reference-tccm-roundtrip.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story ships a reference TCCM under `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` plus an integration-test file `tests/integration/tccm/test_reference_tccm_roundtrips.py` that closes Gap 1 from the phase arch (Adapter Protocols defined in S1-03, never invoked in Phase 2). The conceptual shape — exercise every `DerivedQuery` variant, dispatch each to a structurally-conformant mock implementing all four Phase 2 `Protocol`s, assert every Protocol method is invoked — is correct and traces cleanly to arch §"Gap analysis" Gap 1, 02-ADR-0007 §Consequences, production ADR-0029, ADR-0030, and ADR-0032.

But the original draft had **four block-tier defects** caused by drift between the story's prescribed test code and the actually-shipped S1-04 modules:

1. The fixture YAML used a function-call DSL form (`compute: dep_graph.consumers_of("@codegenie/scip")`) that S1-04's `TCCMLoader` never parses — the live loader is a thin `safe_yaml.load → TCCM.model_validate` shim with discriminator-form Pydantic variants only.
2. `_expected_tccm()` constructed `ConsumersOf(name=..., max_files=...)` etc. — neither field exists on any variant, and `extra="forbid"` would raise on every constructor call.
3. AC-7 asserted `err.reason == "unknown_query_primitive"` but `TCCMLoadError` is a marker with no `.reason` attribute; the reason lives as a positional `args[0]` prefix.
4. References mixed ADR-0030's author-facing alias `scip.refs` with the literal Pydantic discriminator `refs_to`.

Every test would have failed red on `phase-story-executor`'s first attempt for non-design reasons. The executor's three-attempt loop would have burned attempts hunting parser bugs that don't exist.

A further dozen harden-tier gaps were closed: missing `confidence_floor` round-trip coverage for `Trusted` and `Unavailable`, missing `frozen=True` / `extra="forbid"` enforcement, missing per-variant JSON round-trip identity, over-broad `pytest.raises((AssertionError, TypeError, ValueError))`, multi-defect invalid fixture, missing `mypy --strict` scope on the test directory, missing Protocol-typed `_dispatch` parameters (the actual signature-drift closer for Gap 1), unused `MagicMock` import, redundant `kind=` kwargs on `Trusted` / `Degraded` / `Unavailable`, set-equality where multiset-equality belongs, and the missing inverse coverage ratchet (`mypy --warn-unreachable` on a synthetic deleted-arm copy of `_dispatch`).

Three design-pattern strengthenings: introduced `_ProtocolMethod(StrEnum)` as the typed nine-method surface (recorder + assertions both consume it — typo discipline); preserved mock-class duplication explicitly (deleted in Phase 8, not worth a mixin); flagged Protocol-side primitive obsession (`pkg: str`, `module: str`, `symbol: str`) for a future Phase-3-entry amendment ADR (out of S2-03's scope).

Stage 3 research **skipped** — no `NEEDS RESEARCH` findings. Every gap was answerable from arch + ADRs (02-ADR-0007, ADR-0029, ADR-0030, ADR-0032, ADR-0033) + verified live source (`src/codegenie/tccm/{queries,loader,model}.py`, `src/codegenie/result.py`, `src/codegenie/errors.py`, `src/codegenie/adapters/{protocols,confidence}.py`, `src/codegenie/types/identifiers.py`).

Twelve ACs original → **fifteen ACs** after hardening (AC-3b, AC-3c, AC-3d, AC-4b, AC-7b, AC-11b, AC-13 added; AC-1, AC-2, AC-3, AC-4, AC-6, AC-7, AC-9 reworded). Implementation outline §1 / §2 / §4 / §5 rewritten. Files-to-touch table grew from 6 entries to 13. Notes-for-implementer gained a "Design patterns" subsection. Story is now ready for `phase-story-executor`.

## Context Brief (Stage 1)

### Story snapshot

- **Goal as written:** Ship a reference TCCM at `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` (one illustrative manifest exercising every TCCM field + every `DerivedQuery` variant) + `tests/integration/tccm/test_reference_tccm_roundtrips.py` (loads via `TCCMLoader`, asserts equality with hand-constructed Pydantic, dispatches each variant to a mock implementing all four Phase 2 `Protocol`s, asserts every Protocol method is invoked at least once — the in-Phase-2 anchor for Gap 1 / signature-drift discovery).
- **Non-goals:** Real adapter implementations (Phase 3), Bundle Builder (Phase 8), per-task-class second TCCM (Phase 3 ships first plugin TCCM), `SkillsLoader.find_applicable(...)` (S2-01 owns; this story names skills as data only), `tests/integration/adapters/test_phase3_handoff_smoke.py` (S7-04 cross-phase trip-wire).

### Phase 2 exit criteria touched

- **Gap 1 closed in-phase** (arch §"Gap analysis" — Adapter Protocol drift). ✓
- **Kernel scaffolding only, no plugin loader** (02-ADR-0007). ✓ (fixture lives under `docs/`, not `plugins/`).
- **`safe_yaml.load` chokepoint preserved** (Phase 1 ADR-0006). ✓ (TCCMLoader routes through it; AC-9 smokes it independently).
- **Five-primitive `DerivedQuery` taxonomy exhausted** (production ADR-0030). ✓
- **Discriminated unions + `assert_never` ratchet** (ADR-0033 §3–4, arch §"Agentic best practices"). ✓ (AC-6 + AC-13 inverse ratchet).
- **Open/Closed at the Protocol surface** for adding a fifth Protocol or sixth method. ✓ (`_ProtocolMethod` StrEnum is the single-place edit point).

### Load-bearing commitments touched

- CLAUDE.md §"No LLM anywhere in the gather pipeline" — all loaders are deterministic. ✓
- CLAUDE.md §"Honest confidence" — `AdapterConfidence` three-variant union with reason strings; AC-3b verifies all three round-trip. ✓
- CLAUDE.md §"Extension by addition" — sixth `DerivedQuery` variant adds a `case` arm + new enum value + new YAML entry; mypy `--warn-unreachable` and the AC-4 enum-iteration both fire on omission. ✓
- CLAUDE.md §"Conventions to follow" — `.codegenie/` namespace N/A here (test artifact only).
- 02-ADR-0007 §Decision — fixture under `docs/`, not `plugins/`; AC-8 walk asserts. ✓
- ADR-0029 — TCCM schema; AC-3 + AC-3b/c/d round-trip every field. ✓
- ADR-0030 — five derived-query primitives; AC-2 multiset assertion. ✓ (Author-facing alias `scip.refs` reconciled with literal `refs_to` token in story prose.)
- ADR-0032 — four `Protocol`s; AC-4 + AC-4b enforce invocation + Protocol-typed dispatch signatures. ✓
- ADR-0033 — newtypes for identifiers (`SkillId`, `ProbeId`, `TaskClassId`); `_expected_tccm()` constructors now use them. ✓

### Sibling-family lineage

- **Third Phase-2 integration test that round-trips a typed Pydantic model under `docs/`** (after S1-04's TCCMLoader unit tests and S2-02's catalog-loader integration tests). Convention codified: the in-phase reference fixture lives under `docs/phases/{phase}/_reference-{thing}/`, single-defect siblings under `_invalid/`, variant-coverage siblings under `_floors/`/`_variants/`. Future fixtures should match this layout.
- **Fourth consumer of the sum-type + exhaustive `match` + `assert_never` ratchet** — after S1-01 (`StaleReason`), S1-04 (`_classify`/`LoaderReason`), and `AdapterConfidence` consumers. Pattern is now load-bearing.
- **First test in the codebase to use `mypy --warn-unreachable` as an inverse coverage ratchet via subprocess** (AC-13). Extension-by-addition forcing function — sixth `DerivedQuery` variant cannot land green without a `case` arm.
- **Rule-of-three threshold for shared dispatcher kernel:** NOT REACHED. One dispatcher in this phase; Phase 8's Bundle Builder is the production dispatcher (different shape, different concerns). Mocks-as-duplicate-classes is the right call (Rule 3 + intentional-deletion lifecycle).

### Goal-to-AC trace

- AC-1 → goal: STRENGTHENED (allow `README.md`, codify `_invalid/` + `_floors/` siblings).
- AC-2 → goal: STRENGTHENED (`Counter`-style multiset, explicit `len == 5` — was: set-equality only).
- AC-3 → goal: BLOCK-FIXED (corrected constructors against live `queries.py`; corrected `Result.Ok` namespacing to top-level `Ok`; added `isinstance(result, Ok)` assertion).
- AC-3b → goal: ADDED (every `AdapterConfidence` variant round-trips for `confidence_floor`).
- AC-3c → goal: ADDED (`frozen=True` + `extra="forbid"` enforced).
- AC-3d → goal: ADDED (per-variant JSON round-trip identity).
- AC-4 → goal: STRENGTHENED (string-literal-fan replaced by typed `_ProtocolMethod` enum iteration).
- AC-4b → goal: ADDED (Protocol-typed `_dispatch` parameters — the actual Gap-1 signature-drift closer).
- AC-5 → goal: unchanged (already strong).
- AC-6 → goal: STRENGTHENED (`pytest.raises(AssertionError)` only; previous `(AssertionError, TypeError, ValueError)` umbrella hid bugs).
- AC-7 → goal: BLOCK-FIXED (`err.args[0].startswith("unknown_query_primitive:")` — `TCCMLoadError` has no `.reason`).
- AC-7b → goal: ADDED (parametrized over `parse:` / `schema:` / `unknown_query_primitive:` taxonomy).
- AC-8 → goal: unchanged (already strong).
- AC-9 → goal: REWORDED (smoke, not parser test).
- AC-10 → goal: unchanged (already strong).
- AC-11 → goal: unchanged.
- AC-11b → goal: ADDED (`mypy --strict` scoped to test directory).
- AC-12 → goal: unchanged.
- AC-13 → goal: ADDED (inverse coverage ratchet via subprocess `mypy --warn-unreachable`).

## Stage 2 — Critic findings

### Critic A — Coverage

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C1 | harden | AC-4 only asserts "every method called at least once" — traces to Gap 1's letter, not its spirit (Gap 1 worries about *signature drift*). A test calling `dep.consumers("@x")` passes against either signature. | **Applied.** Added AC-4b: `_dispatch` parameters typed against the `Protocol`s (not the mocks); mypy validates call sites against Protocol signatures. AC-11b scopes `mypy --strict` to `tests/integration/tccm/`. |
| C2 | block | `confidence_floor` only exercises `Degraded` — `Trusted` and `Unavailable` discriminator paths could ship broken. | **Applied.** Added AC-3b: three `_floors/` fixtures + parametrized round-trip test. |
| C3 | harden | No AC verifies `frozen=True` / `extra="forbid"` invariants on the loaded `TCCM`. Arch §"Data model" requires both. | **Applied.** Added AC-3c: mutation raises `ValidationError`; extra top-level key returns `Err` with `schema:` prefix. |
| C4 | harden | `_invalid/` coverage thin: only `unknown_compute.yaml`. Realistic on-disk failures include malformed YAML, missing required field, unknown top-level key. | **Applied.** Added three sibling fixtures + AC-7b parametrization across the full `LoaderReason` taxonomy. |
| C5 | nit | AC-9 (`safe_yaml.load`) duplicates S1-04 cheaply — keep but reframe as fixture-validity smoke. | **Applied.** AC-9 reworded. |
| C6 | block | No AC for `mypy --strict` on the test file itself. Without it, AC-4b's Protocol-typed signatures are just comments. | **Applied.** Added AC-11b. |
| C7 | harden | AC-6's `pytest.raises((AssertionError, TypeError, ValueError))` is over-defensive — `typing.assert_never` raises `AssertionError` deterministically (3.11+). | **Applied.** Narrowed to `pytest.raises(AssertionError)`. |
| C8 | nit | AC-1 says directory holds "only the reference TCCM and `_invalid/`" — contradicts AC-10 (mandates `README.md`). | **Applied.** AC-1 reworded to allow `README.md`, `_invalid/`, `_floors/`. |
| C9 | harden | No JSON round-trip identity per variant — discriminator-tag-name mismatches could ship uncaught before Phase 3. | **Applied.** Added AC-3d. |
| C10 | nit | No escape-hatch hedges in ACs — clean. | No action. |

### Critic B — Test Quality

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| T1 | block | `_expected_tccm()` uses constructor args (`name`, `max_files`) that don't exist on any variant in `queries.py`; `extra="forbid"` raises. | **Applied.** Dropped from `_expected_tccm()` and YAML; constructors now match live model. |
| T2 | block | YAML `compute: dep_graph.consumers_of("@x")` form does not match the actual loader (no DSL parser; `compute: Literal[...]` discriminator + flat payload field only). | **Applied.** YAML rewritten to discriminator-form `compute: consumers_of` + `pkg: "@x"`. |
| T3 | block | `TCCMLoadError(reason=...)` constructor and `err.reason` access don't work — `TCCMLoadError` is a marker; reason is positional `args[0]` prefix. | **Applied.** AC-7 asserts `err.args[0].startswith("unknown_query_primitive:")`. |
| T4 | harden | `Result.Ok` / `Result.Err` not callable as namespaced constructors — `Ok` / `Err` are top-level exports. | **Applied.** Story prose mentions corrected; test imports `from codegenie.result import Ok`. |
| T5 | harden | AC-6 `pytest.raises((AssertionError, TypeError, ValueError))` over-broad. | **Applied.** Narrowed (cf. C7). |
| T6 | harden | AC-3 equality could pass under near-wrong implementations — add property-style round-trip `TCCM.model_validate(tccm.model_dump()) == tccm`. | Partially applied via AC-3d (per-variant JSON round-trip — stronger than dict round-trip for discriminator coverage). |
| T7 | harden | `MagicMock` import is dead; `ruff` would fail AC-11. | **Applied.** Dropped. |
| T8 | harden | Mock `confidence()` returns `Trusted(kind="trusted")` — `kind` is defaulted; explicit pass is misleading. | **Applied.** All `Trusted()` / `Degraded(reason=...)` / `Unavailable(reason=...)` calls. |
| T9 | nit | `_dispatch` itself doesn't invoke `confidence()` — production invariant Phase 8 will need. | Deferred — Phase 8's Bundle Builder owns that. Notes-for-implementer flags `_dispatch` is test-only. |
| T10 | nit | `_Imposter` `__match_args__` distraction — Pydantic-model `case` arms match by class identity, not `__match_args__`. | **Applied.** Removed `__match_args__ = ()`; added comment explaining why an arbitrary object falls through. |
| T11 | nit | AC-2 set equality misses multiset semantics — `[Consumers, Producers, Reverse, Refs, Tests, Tests]` would fail set check by length only. | **Applied.** `Counter`-style multiset + explicit `len == 5`. |

### Critic C — Consistency

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| CO1 | block | YAML `compute:` strings do not parse under S1-04's loader. | **Applied** (cf. T2). |
| CO2 | block | Story line ~35 lists `scip.refs` (ADR-0030 alias) instead of `refs_to` (literal token shipped by S1-04). | **Applied.** References section reworded; alias documented as alias only. |
| CO3 | block | `_expected_tccm()` constructors include `name=` / `max_files=` fields that don't exist. | **Applied** (cf. T1). |
| CO4 | confirmed | `confidence_floor: AdapterConfidence` correct in story prose; mock `Trusted(kind="trusted")` redundancy harmless. | No action (T8 fixed the redundancy anyway). |
| CO5 | harden | AC-7 invalid fixture has extras — multi-defect; couples to Pydantic v2 error-emission order. | **Applied.** Single-defect: dropped `name`/`max_files` from the invalid fixture. |
| CO6 | harden | `Result.Ok(value=...)` namespacing in story prose — `Ok` / `Err` are top-level exports. | **Applied** (cf. T4). |
| CO7 | block | `TCCMLoadError(reason="unknown_query_primitive")` and `err.reason` don't work. | **Applied** (cf. T3). |
| CO8 | harden | `Depends on: S2-01` is misleading — story does not call `SkillsLoader`; `required_skills` is data only. | **Applied.** Header now lists S1-04 + S1-05 (`SkillId` newtype). Out-of-scope §5 already documented this. |
| CO9 | nit | Over-broad `pytest.raises` umbrella. | **Applied** (cf. C7). |
| CO10 | confirmed | Reference path matches 02-ADR-0007 §Consequences ¶5. | No action. |

### Critic D — Design Patterns

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| DP1 | harden | The `mypy --warn-unreachable` claim is documentation, not enforcement — no AC asserts that *removing* a `case` arm makes mypy fail. | **Applied.** Added AC-13: subprocess-driven inverse coverage ratchet via synthetic deleted-arm fixture. |
| DP2 | harden | Primitive obsession on Protocol method names — nine string literals in the recorder, nine in the assertions; typos silent. | **Applied.** Introduced `_ProtocolMethod(StrEnum)`; recorder + assertions both consume it. |
| DP3 | harden | The fan of nine `assert called(...)` lines IS the "Protocol coverage map" the original Refactor §6 forbid — but uncentralized. The right form is the StrEnum (declarative typed surface), not nine independent asserts. | **Applied.** Test body now iterates the StrEnum; single missing-method failure with named method. Refactor §6 reframed in Notes-for-implementer. |
| DP4 | nit | Four sibling mocks share `__init__` + `confidence()` shape — three-strikes fires on its face. | Resisted (Rule 3 + Phase-8 deletion lifecycle). Notes-for-implementer flags it explicitly. |
| DP5 | nit | Newtype opportunity (`PackageName`, `ModulePath`, `SymbolName`) on Protocols — primitive obsession at the Protocol boundary. | Deferred to Phase-3-entry amendment ADR. Notes-for-implementer flags it. |
| DP6 | nit | Registry pattern (`@register_dispatcher_for(...)`) premature — Phase 8 owns production dispatcher. | No action. Notes-for-implementer reinforces "do not export". |
| DP7 | nit | `_dispatch` mutates mocks — pure version would obscure intent (side effect IS the assertion target). | No action. Notes-for-implementer documents. |

## Stage 3 — Research

**Skipped.** No `NEEDS RESEARCH` findings. Every gap was answerable from arch + ADRs + verified live source code (`src/codegenie/tccm/`, `src/codegenie/result.py`, `src/codegenie/errors.py`, `src/codegenie/adapters/`, `src/codegenie/types/identifiers.py`).

## Stage 4 — Edits applied

The story file was edited in place. All edits are surgical and preserve the original structure:

1. **Header** — `Status: Ready (HARDENED 2026-05-15)`; `Depends on:` corrected to S1-04 + S1-05 (was: S1-04 + S2-01 misleading).
2. **Validation notes block** appended after the header — full edit log with critic IDs.
3. **References → Production ADRs → ADR-0030 line** — reworded to use the literal `compute` tokens (`refs_to`) with `scip.refs` documented as ADR-0030's author-facing alias.
4. **Goal §1 last bullet** — explicit "no `name`, no `max_files`" callout.
5. **Goal §2 first sub-bullet** (`test_reference_tccm_loads_and_equals_expected_pydantic_instance`) — `Result.Ok` → `Ok` (top-level export) clarified.
6. **Goal §2 fifth sub-bullet** (`test_unknown_compute_primitive_returns_typed_err_prefix`) — corrected to `args[0]` prefix; renamed test for accuracy.
7. **Acceptance criteria** — fifteen ACs replacing twelve. Block-tier rewrites on AC-3, AC-7. New ACs: AC-3b, AC-3c, AC-3d, AC-4b, AC-7b, AC-11b, AC-13. Reword: AC-1, AC-2, AC-4, AC-6, AC-9.
8. **Implementation outline §1** — YAML rewritten to discriminator-form (no DSL strings, no `name`/`max_files`).
9. **Implementation outline §2** — invalid fixtures restructured: single-defect `unknown_compute.yaml` + three new siblings (`malformed.yaml`, `missing_required_probes.yaml`, `extra_top_level_key.yaml`) + three `_floors/` siblings.
10. **Implementation outline §4** — full test-file rewrite: `_ProtocolMethod(StrEnum)` introduction, Protocol-typed `_dispatch` signature, `Trusted()` / `Degraded(reason=...)` / `Unavailable(reason=...)` constructors, `Counter`-style multiset, parametrized fixtures, `args[0]` prefix assertions, narrow `pytest.raises(AssertionError)`, `MagicMock` import dropped. Sibling AC-13 ratchet test referenced.
11. **Implementation outline §5** — sanity-check command rewritten to verify the live two-field shape.
12. **Files to touch** — grew from 6 entries to 13 (incl. seven new fixtures + AC-13 ratchet test).
13. **Notes for the implementer** — appended "Design patterns" subsection covering the StrEnum, the inverse-ratchet, the deliberate mock duplication, the deferred newtype amendment, and the functional-core-vs-imperative-shell rationale.

## Verdict — HARDENED

The story is now ready for `phase-story-executor`. Every block-tier defect has been corrected against live source code. Every harden-tier gap has been closed with an AC + a corresponding test in the prescribed test file. Three design-pattern strengthenings preserve the original "extension by addition" intent without introducing premature abstraction.

A `phase-story-executor` run against this hardened story should:

1. Land 11 named tests (8 standalone + 3 parametrized expansions = 17 actual `pytest` IDs once `pytest --collect-only` runs) red on the first commit because the YAML fixtures don't exist.
2. Author the seven YAML fixtures + README.md.
3. Watch all tests turn green without YAML hand-tuning, because the `_expected_tccm()` constructors and YAML now agree with `queries.py`.
4. Land the AC-13 ratchet test in a sibling file.
5. Pass `ruff check`, `ruff format --check`, `mypy --strict`, `mypy --strict tests/integration/tccm/`, `mypy --warn-unreachable`.

Estimated executor attempts: 1 (single attempt happy-path).
