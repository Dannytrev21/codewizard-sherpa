# S1-04 — `VulnProvenanceAdapter` Protocol + `ProvenanceError` hierarchy — Validation report

**Story:** [../S1-04-vuln-provenance-adapter-protocol.md](../S1-04-vuln-provenance-adapter-protocol.md)
**Validated:** 2026-05-19
**Validator pass:** `phase-story-validator` skill (first pass — no prior `_validation/` entry for S1-04)
**Verdict:** **HARDENED** — real but fixable weaknesses across all four critic lenses; edits applied in place; story is now ready for `phase-story-executor`.

## Context Brief (Stage 1)

### Story snapshot
- **Goal (verbatim):** Define the `VulnProvenanceAdapter` Protocol verbatim from the arch under `src/codegenie/primitives/vuln_provenance/protocols.py` and the typed error hierarchy under `src/codegenie/primitives/vuln_provenance/errors.py` — so every Phase 7 adapter story has a stable contract to satisfy and `assemble_provenance` (S2-04) has a base exception type to catch.
- **Effort:** S
- **Depends on (post-edit):** S1-01 (newtype identifiers); S1-02 + S1-03 (`AdapterConfidence`, `Provenance`).
- **Status pre-edit:** `Ready`. Status post-edit: `HARDENED`.

### Files to touch (post-edit)
- `src/codegenie/primitives/vuln_provenance/protocols.py` — NEW (Protocol shape, `runtime_checkable`, two methods, `TYPE_CHECKING` placeholder for `SyftSbom`).
- `src/codegenie/primitives/vuln_provenance/errors.py` — NEW (three markers-only classes).
- `src/codegenie/primitives/vuln_provenance/__init__.py` — EXTEND with ASCII-sorted re-exports of the four new names.
- `tests/unit/primitives/vuln_provenance/test_adapter_protocol_shape.py` — NEW (red test exists in uncommitted state; cross-checked).
- `tests/unit/primitives/vuln_provenance/test_protocols_module_purity.py` — NEW (exists in uncommitted state).
- `tests/unit/primitives/vuln_provenance/test_errors_module_purity.py` — NEW (validator-added; symmetric with protocols.py fence).
- `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` — EXTEND (lock post-S1-04 `__all__` surface).

### Phase / arch constraints
- **Phase 7 ADR-0004** — primitive home; `protocols.py` and `errors.py` are the canonical module names.
- **Phase 7 ADR-0007** — Protocol is a structural duck-typed contract; NO `cost_band`, NO `applies_when`; registry stores classes (S2-01 lands the registry).
- **Production ADR-0032** — DepGraphAdapter Protocol shape; this story mirrors it for vuln provenance.
- **Production ADR-0038** — names this Protocol as the contract.
- **Phase-arch-design.md §Component design §3** — verbatim `@runtime_checkable VulnProvenanceAdapter(Protocol)` with exactly two methods; "No `cost_band`, no `applies_when`" prohibition.
- **Phase-arch-design.md §Error escalation** — `ProvenanceError`-caught path becomes `Unknown(reason="adapter_error")`.

### Phase exit criteria the story contributes to
- Phase 7 ADR-0007 §Consequences — `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}` requires this Protocol to exist.
- Phase 7 final-design Goal 1 (primitive ships) — Step 1 of `High-level-impl.md`.
- All Step 2+ stories (S2-01 registry, S2-04 assemble_provenance, S3-02 npm adapter, S4-02 alpine, S4-03 distroless) depend on this story landing first.

### Prior validation history
- S1-01, S1-02, S1-03 — established mypy-negative test precedent, frozen base / model_construct fences, `__all__` ASCII-sort invariant, gate-widening pattern (`make check` over narrow subdir mypy).

### Open ambiguities (resolved in edits)
- ⚠️ **AC-6 mypy-strict-clean-today claim is unworkable as written.** With `SyftSbom` undefined in `protocols.py`'s scope, `mypy --strict` errors with `name-defined` — even with `from __future__ import annotations`, mypy still resolves forward references at type-check time. Resolved by AC-6(b) sub-clause naming two ADR-conformant resolution routes (TYPE_CHECKING placeholder preferred; narrow `# type: ignore[name-defined]` alternative).
- ⚠️ **The story implicitly assumes the existing test file's structure but never pins it.** The uncommitted `test_adapter_protocol_shape.py` already covers AdapterError-Distinct-From-RegistryError (line 107-110) and the rewritten clearer-form negative-Exception test (line 113-125). The ACs were silent on these. Resolved by tightening AC-4 (exclusivity sub-clause) and AC-5 (rewrite of negative test).

## Stage 2 — Critic findings

Critics ran inline (same approach as S1-03 — story is narrow enough that four parallel subagents would have token-burn without information gain). Findings cross-checked against the existing red tests at `tests/unit/primitives/vuln_provenance/test_adapter_protocol_shape.py` and `test_protocols_module_purity.py` to keep hardened ACs achievable.

### Coverage critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C1 | harden | **AC-1 doesn't pin annotation completeness.** A stripped-annotation implementation (`def attribute(self, cve_id, package_id, image_ref, sbom):`) would pass the `inspect.signature` param-name check but defeat the Protocol's typing purpose. | Added **AC-1 sub-clause** asserting the annotation set for `attribute` is exactly `{"cve_id", "package_id", "image_ref", "sbom", "return"}` and for `confidence` is `{"return"}`. |
| C2 | harden | **AC-3 only pins missing-`confidence` rejection.** A method-renamer mutation that drops `attribute` but keeps `confidence` would not be caught. | Added symmetric `_BadAdapterMissingAttribute` stub requirement to **AC-3**. |
| C3 | harden | **AC-4 doesn't pin the sum-type exclusivity** — `AdapterError` and `RegistryError` must be **siblings**, not parent-child. The existing test file enforces this; the AC didn't. | Added **AC-4 sub-clause**: mutual-exclusivity (`not issubclass(AdapterError, RegistryError)` and vice versa). |
| C4 | harden | **AC-8 covers `protocols.py` purity only; `errors.py` is unfenced.** Phase 0's `src/codegenie/errors.py` imports nothing beyond `__future__`. New errors module should mirror that. | Extended **AC-8** to include `test_errors_module_purity.py` with allowlist `{__future__, codegenie.errors}`. |
| C5 | block | **AC-6's "mypy --strict clean today" claim is structurally unworkable.** With `SyftSbom` undefined, mypy errors with `name-defined`. The story acknowledged the tension but didn't resolve it. | Split **AC-6** into two sub-clauses; AC-6(b) names two resolution routes (TYPE_CHECKING placeholder preferred; `# type: ignore[name-defined]` alternative). Rejects `SyftSbom = Any`. |
| C6 | harden | **AC-7 doesn't pin the `__all__` ASCII-sort invariant.** Established by S1-02 / S1-03; the existing `__init__.py:12-14` docstring is explicit. An executor appending names would break the invariant. | Strengthened **AC-7** to require ASCII-sorted insertion + a `test_types_dunder_all.py` extension naming the post-S1-04 surface. |
| C7 | nit | **AC-9 narrows the gate below `make check`** — parallel to S1-02 CO4 / S1-03 CO1. Narrow subdir mypy misses cross-package drift. | Widened **AC-9** to project-wide `make check`. |
| C8 | harden | **No AC pins Protocol-not-ABC.** ADR-0007 mandates `typing.Protocol`; substituting `abc.ABC` would pass AC-2 + AC-3 but break the structural-typing design. | Added **AC-10 NEW** — `typing.Protocol in __mro__` AND `abc.ABC not in __mro__`. |
| C9 | harden | **No AC pins markers-only convention for `errors.py`.** Phase 0's precedent (`src/codegenie/errors.py:20-27`) is "no `__init__`, no `__str__`, no class attributes". The story's implementation outline implies this but doesn't enforce it. | Added **AC-11 NEW** — AST-walk asserts each error class body is exactly one `ast.Expr` (the docstring). |

### Test-Quality critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| T1 | harden | **The TDD plan's `test_provenance_error_does_not_catch_plain_exception` is Rule 9 thin.** The catch-then-re-raise structure passes vacuously whether or not `ProvenanceError` catches `Exception` — `pytest.raises(Exception)` catches the re-raised error either way. | Rewrote **AC-5** to mandate the `excinfo.value` assertion form: `with pytest.raises(Exception) as excinfo: raise Exception("plain"); assert not isinstance(excinfo.value, ProvenanceError)`. The existing red test file already uses this clearer form (lines 113-125). |
| T2 | harden | **`test_attribute_signature` only asserts param names, not annotations.** A wrong implementation that strips type hints passes. The Protocol's purpose IS the type contract. | Folded into AC-1 sub-clause (annotation completeness). |
| T3 | harden | **No test for the Protocol-not-ABC choice.** The structural design decision (ADR-0007) is implicit in the test suite. | Folded into AC-10 NEW. |
| T4 | nit | **AC-6 forward-reference test uses `inspect.get_annotations(..., eval_str=False)`** which avoids resolution. Today's behavior is correctly pinned; the `# TODO(S1-05)` marker is the right tightening guard. | No change — existing test idiom is correct. |
| T5 | harden | **`test_attribute_signature` may behave differently under `from __future__ import annotations`.** Without future annotations, `inspect.signature` returns resolved annotations (would fail without SyftSbom). With future annotations, returns the raw string. The test reads only `parameters.keys()` (names), which is robust to both — but worth noting. | No AC change; implementer note added under Operational notes naming the `from __future__ import annotations` requirement on `protocols.py`. |

### Consistency critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| CO1 | harden | **AC-9 gate phrasing is narrower than the project gate.** Parallel to S1-02 CO4 / S1-03 CO1 — `make check` is the right end-to-end gate. | Widened **AC-9** to project-wide `make check`. |
| CO2 | block | **The story's `Depends on: S1-01` is insufficient.** AC-6's "mypy strict clean today" requires either S1-05 to land first OR an in-story placeholder strategy. The story acknowledged it but didn't make a call. | Added explicit recipe in **AC-6(b)** + implementer notes. Also broadened `Depends on:` to name S1-02 + S1-03 (the `AdapterConfidence` + `Provenance` types the Protocol returns). |
| CO3 | harden | **The story's implementer notes don't explicitly forbid ABC inheritance.** ADR-0007 mandates `Protocol`; without surfacing this, an executor reading "the Protocol is a structural duck-typed contract" might still default to ABC out of habit. | Added implementer-notes paragraph under "Design-pattern lineage" with the substitution-failure rationale. Folded into AC-10 NEW for structural enforcement. |
| CO4 | nit | **Phase 6.5 regression suite not mentioned.** S1-03 CO3 widened to "Phase 0–6.5 regression suite green via `make check`". | Folded into AC-9 widening. |
| CO5 | harden | **`__all__` ASCII-sort invariant from S1-03 is not surfaced.** S1-03 validation called this out explicitly; S1-04 must maintain it. | Strengthened **AC-7** + added implementer note. |
| CO6 | nit | **`RegistryError` message-prefix convention from `DepGraphRegistryError` is not noted.** S2-01 will raise this with a structured prefix; the convention should be flagged now so S2-01's executor mirrors it. | Added implementer-notes paragraph: future `duplicate_adapter_for_key: (Layer.APP, Ecosystem.NPM)` mirroring `no_strategy_for_ecosystem: <repr>` precedent at `src/codegenie/depgraph/registry.py:178`. |

### Design-Patterns critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| DP1 | harden | **The Hexagonal Port pattern is unnamed.** This story IS the port; concrete adapters are the adapters. ADR-0032 lineage. Naming the pattern helps executors understand why Protocol-not-ABC is load-bearing. | Added implementer-notes "Design-pattern lineage" section naming the pattern + cross-referencing ADR-0032. |
| DP2 | harden | **The Protocol-not-ABC choice is the load-bearing design seam.** Without ABC, plugin adapters don't import the Protocol — structural duck typing. With ABC, you get inheritance coupling. | Surfaced in both the implementer notes (rationale) AND structurally pinned in AC-10 NEW. |
| DP3 | harden | **The `"SyftSbom"` string forward reference is a workaround for story-ordering.** The cleaner pattern would be TYPE_CHECKING-guarded import after S1-05 lands; today it's a placeholder. Worth surfacing the trade-off explicitly. | Resolved in AC-6(b) + implementer notes naming the placeholder pattern. |
| DP4 | harden | **The typed-error sum-type pattern (closed boundary) is unstated.** `ProvenanceError → {RegistryError, AdapterError}` is the closed sibling set. Adding a third (e.g., `FactoryError`) is an ADR-0007 amendment, not a free edit. | Added implementer-notes paragraph + AC-4 mutual-exclusivity sub-clause. |
| DP5 | harden | **The markers-only-errors convention from `codegenie.errors` is implicit.** Phase 0's docstring (`src/codegenie/errors.py:20-27`) is explicit but the story doesn't carry the rule forward. An executor adding `__init__` for "convenience" would break the convention. | Added AC-11 NEW (structural fence) + implementer notes (precedent pointer to file:line). |
| DP6 | nit | **The `RegistryError` future-message-prefix convention is unstated.** Mirrors `DepGraphRegistryError`'s `no_strategy_for_ecosystem: <repr>` precedent. | Added implementer-notes paragraph (with file:line precedent pointer). |
| DP7 | nit | **The Adapter is a port without explicit "Failure behavior" wording in the ACs.** The arch §3 is explicit ("Adapters return `Unknown(reason=...)` rather than raising for 'I don't apply' cases. Raising is reserved for genuine errors (`ProvenanceError` subclasses)."). The story implementer notes touch this; could be stronger. | No AC change — this is the consumer-side contract (adapters in S3-02 / S4-02 / S4-03 will pin it). Story scope is the Protocol surface only. |

## Stage 3 — Research

**Skipped.** No findings tagged `NEEDS RESEARCH`. Every pattern in scope (PEP 544 Protocol + `@runtime_checkable`, typed-error markers, AST-walk fences, `TYPE_CHECKING` forward-reference placeholders, ASCII-sorted `__all__`) is already idiomatic in this codebase. Precedents:

- `src/codegenie/errors.py:64-65` — `class CodegenieError(Exception): pass` marker convention.
- `src/codegenie/depgraph/registry.py:66-69` — `TYPE_CHECKING`-guarded import pattern.
- `src/codegenie/depgraph/registry.py:178` — structured-message-prefix convention for registry errors.
- `tests/unit/primitives/vuln_provenance/test_protocols_module_purity.py` (red, uncommitted) — module-purity fence shape.
- `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` (green, committed) — ASCII-sorted `__all__` invariant precedent.

## Stage 4 — Edits applied

All edits land in [`../S1-04-vuln-provenance-adapter-protocol.md`](../S1-04-vuln-provenance-adapter-protocol.md). Changes by section:

| Section | Change | Rationale (critic IDs) |
|---|---|---|
| Header | `Status: Ready` → `Status: HARDENED`. | Validator pass. |
| Header | Broadened `Depends on:` to name S1-02 + S1-03 (the types the Protocol returns). | CO2. |
| Header | Added `Validation notes` block summarizing every applied edit. | Editor protocol. |
| AC-1 | Added annotation-completeness sub-clause. | C1, T2. |
| AC-3 | Added symmetric `_BadAdapterMissingAttribute` test requirement. | C2. |
| AC-4 | Added mutual-exclusivity sub-clause (sibling-not-chain). | C3. |
| AC-5 | Rewrote the negative-Exception test to use `excinfo.value` (clearer form; matches the existing red test). | T1. |
| AC-6 | Split into (a) runtime forward-reference and (b) mypy-strict-clean-today recipe with two ADR-conformant resolution routes. | C5, CO2, DP3. |
| AC-7 | Strengthened to require ASCII-sorted `__all__` invariant + lock-test extension. | C6, CO5. |
| AC-8 | Extended fence to `errors.py` (new `test_errors_module_purity.py` test). | C4. |
| AC-9 | Widened to project-wide `make check`. | C7, CO1, CO4. |
| **AC-10 NEW** | Protocol-not-ABC structural pin (`typing.Protocol in __mro__` AND `abc.ABC not in __mro__`). | C8, CO3, DP2. |
| **AC-11 NEW** | Markers-only convention for `errors.py` — AST-walk asserts each error class body is exactly one docstring. | C9, DP5. |
| Files to touch | Added `test_errors_module_purity.py` (NEW, AC-8 part 2); added `test_types_dunder_all.py` (EXTEND, AC-7). Annotated existing rows with the additional structural pins they carry. | C4, C6. |
| Implementer notes | Added a structured "Design-pattern lineage" section: (1) Hexagonal Port + Adapter (ADR-0032); (2) Protocol-not-ABC mandate (ADR-0007); (3) Markers-only errors precedent (`codegenie.errors:20-27`); (4) Typed-error sum-type closed boundary; (5) Future RegistryError message-prefix convention (`DepGraphRegistryError` precedent at `depgraph/registry.py:178`). | DP1–DP6. |
| Implementer notes | Strengthened the SyftSbom forward-reference note with the two-route mypy-strict recipe. | DP3, CO2. |
| Implementer notes | Added "`__all__` ASCII-sort invariant" note (precedent pointer to `__init__.py:12-14`). | CO5. |
| Implementer notes | Added "`make check` is the gate" note. | CO1, CO4. |

### Verdict justification

**HARDENED**, not RESCUE, because:

- The goal traces cleanly to ADR-0007 (Phase 7) + production ADR-0032 + ADR-0038. The Protocol's two-method shape is the verbatim contract from the arch.
- The ACs pre-edit *covered* the load-bearing invariants but undershot in three structural places that the existing (uncommitted) red tests already enforce:
  - AC-6's "mypy strict clean today" was unworkable as stated without the placeholder recipe (would block the executor).
  - AC-10 (Protocol-not-ABC) was implicit — the existing test file doesn't pin it, so an executor substituting `ABC` would have shipped silently.
  - AC-11 (markers-only-errors) was implicit — Phase 0's `errors.py` carries the convention as a docstring, not a structural fence.
- Edits strengthen verifiability without inventing scope. No goal rewrite; no new design surface — every new AC enforces an invariant the existing arch / ADR already mandated.

**Cross-check against existing uncommitted implementation:** the red tests at `test_adapter_protocol_shape.py` already cover AC-1, AC-2, AC-3 (partial — only missing-`confidence`), AC-4 + mutual exclusivity, AC-5 (clearer form), AC-6 (raw-string), AC-7 (re-exports). They do NOT cover AC-1 annotation completeness, AC-3 missing-`attribute`, AC-8 errors-module purity, AC-10 Protocol-not-ABC, AC-11 markers-only — these are the structural gaps the validator closes.

### Anti-goals honored

- Did not rewrite the goal or scope (Rule 3 — surgical changes).
- Did not add ACs the goal does not imply (Rule 4 — every new AC enforces an existing invariant).
- Did not touch the implementation source under `src/codegenie/primitives/vuln_provenance/` (validator stays out of code; only edits the story file + writes this report).
- Did not commit the story manually (the scheduled-task invocation explicitly requests commit + push of the story-file + report edits as the final step).
