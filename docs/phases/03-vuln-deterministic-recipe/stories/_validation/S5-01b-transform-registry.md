# Validation report: S5-01b — `TransformRegistry`

**Validated:** 2026-05-20 23:27 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S5-01b-transform-registry.md`

## Summary

S5-01b is a post-execution validation of the already-GREEN `TransformRegistry` story. The story goal is sound and matches ADR-0014: preserve `RecipeEngine.apply(...) -> RecipeOutcome`, constructor-inject a per-workflow registry, and look up the produced `Transform` by `Applied.transform_id`. No implementation edits were needed. The hardening pass tightened the story's own acceptance criteria and TDD plan where tests were thinner than the contract they described.

## Context brief

- **Goal:** Ship `src/codegenie/transforms/transform_registry.py` exposing a per-workflow, in-memory registry keyed by `TransformId`, with `register` and `get` so a `RecipeEngine` can surface its produced `Transform` without widening `RecipeEngine.apply`.
- **Phase constraints:** Phase 3 must preserve the Phase-5 contract surface (`RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext`, `RecipeEngine`, `remediation-report.yaml`) and keep LLM SDKs out of `src/codegenie/{plugins,transforms}/`.
- **ADR-0014:** `TransformRegistry` is the sanctioned channel for produced transforms; per-workflow injection, no `default_*` singleton, not a Phase-5 contract symbol, not exported from `codegenie.transforms.__all__`.
- **ADR-0010:** `TransformId` is a newtype domain key; typed failure markers carry structured fields rather than parse-only messages.
- **ADR-0002:** Registry shape precedent exists, but ADR-0014 deliberately diverges from process-wide `default_registry` because transforms are runtime artifacts, not import-time plugin/recipe declarations.
- **As-built code checked:** `src/codegenie/transforms/transform_registry.py`, `tests/unit/transforms/test_transform_registry.py`, `src/codegenie/plugins/recipe_registry.py`, `src/codegenie/transforms/transform.py`, `src/codegenie/transforms/outcomes.py`.
- **Prior validation history:** None for S5-01b. S5-02 and S5-03 validations were read because ADR-0014 exists to resolve their earlier engine-layer contradiction.
- **Open ambiguities:** None. The only nuance is that the story is already `Done`; this validator run records the missing hardening report and tightens the story text without changing scope.

## Findings by critic

### Coverage critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C1 | harden | AC-Surface-3 promises no `default_transform_registry`, but the test only looked for `TransformRegistry` instances. A bad placeholder such as `default_transform_registry = None` would pass while violating ADR-0014's naming constraint. | Hardened AC-Surface-3 and the TDD snippet to assert `"default_transform_registry" not in vars(tr_mod)` in addition to the module-level instance scan. |
| C2 | nit | The post-execution status made it hard to see that this story had now been through the validator. | Updated the status line and inserted a validation-notes block under the header. |

### Test-Quality critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| T1 | harden | AC-Surface-1 says `__all__` is the exact sorted list, but the TDD snippet used only `set(tr_mod.__all__)`. A duplicate or reordered list could satisfy that test. | Rewrote the AC and TDD snippet to assert `tr_mod.__all__ == ["TransformAlreadyRegistered", "TransformNotFound", "TransformRegistry"]`. |
| T2 | harden | AC-Reg-4 requires the duplicate-registration message to name both colliding `module.qualname` origins, but the TDD duplicate case used two instances of the same class and did not assert the real registry-generated message. | Added `_OtherFakeTransform` to the TDD snippet and asserted both concrete origin strings are present in `str(exc_info.value)`. |

### Consistency critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| K1 | none | Story goal, ADR-0014, High-level-impl Step 5, and as-built `transform_registry.py` agree: `apply` remains `-> RecipeOutcome`; `TransformRegistry` is not exported from `codegenie.transforms.__all__`; errors subclass `CodegenieError` and carry `TransformId`. | No consistency edit needed. |
| K2 | none | Import-set AC agrees with as-built module imports (`__future__`, `typing`, `codegenie.errors`, `codegenie.transforms.transform` under `TYPE_CHECKING`, `codegenie.types.identifiers`). | No edit needed. |

### Design-Patterns critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| D1 | harden | This is another registry-shaped surface after `PluginRegistry` and `RecipeRegistry`; the story should explicitly justify why it does not introduce a shared registry kernel. | Added a Notes-for-implementer paragraph: do not extract yet because this registry has per-workflow lifetime, no `default_*`, no decorator, no `all()`, and no reset hook. Extract only when a second per-workflow runtime-object registry needs the same surface. |
| D2 | none | The actual design is strong: constructor injection preserves dependency inversion, `TransformId` avoids primitive obsession, typed markers make illegal parsing states unnecessary, and the small concrete class is easier to maintain than a generic base here. | No edit needed. |

## Research briefs

Skipped. No finding required external research; the relevant patterns are already represented in ADR-0014, ADR-0010, ADR-0002, and the sibling registry modules.

## Conflict resolutions

No critic conflicts. The design-pattern suggestion to consider a shared registry kernel was resolved by Rule 2 / Rule 3: document the extraction trigger, but keep the current concrete class because the lifecycle differs from process-wide registries.

## Edits applied

### Edit 1 — Validation status and notes

- Source: Coverage C2
- Before: status only recorded executor GREEN.
- After: status records validator HARDENED and the story includes a `Validation notes` block with findings addressed and the report path.
- Rationale: this story was the first unvalidated story; the completion marker is now visible without opening `_validation/`.

### Edit 2 — AC-Surface-1 exact `__all__`

- Source: Test-Quality T1
- Before: meta-test asserted set equality only.
- After: meta-test asserts the exact sorted list.
- Rationale: the AC promised exact order and no duplicates; the test now catches those mutants.

### Edit 3 — AC-Surface-3 singleton-name check

- Source: Coverage C1
- Before: test rejected module-level `TransformRegistry` instances only.
- After: test also rejects `default_transform_registry` by name.
- Rationale: ADR-0014 rejects the singleton surface itself, not only instantiated global mutable state.

### Edit 4 — Duplicate-origin TDD hardening

- Source: Test-Quality T2
- Before: duplicate test used two `_FakeTransform` objects and did not inspect the actual origin strings in the raised registry error.
- After: duplicate test uses `_FakeTransform` and `_OtherFakeTransform` with the same id and asserts both origin strings are present.
- Rationale: catches a registry that raises the right marker but loses one side of the collision evidence.

### Edit 5 — Registry-kernel extraction note

- Source: Design-Patterns D1
- Before: Notes explained per-workflow lifetime but did not address the growing number of registry-like classes.
- After: Notes explicitly defer shared-kernel extraction until another per-workflow runtime-object registry needs the same surface.
- Rationale: preserves Open/Closed and maintainability without premature abstraction.

## Verdict rationale

HARDENED. The story's architecture is correct and already implemented, but the acceptance criteria and TDD plan had three thin spots: exact `__all__`, singleton-name absence, and duplicate-origin evidence. Those are fixable in place and do not require implementation changes because the as-built code already satisfies the strengthened contract.

## Recommended next step

No executor rerun is required for S5-01b. Future engine/orchestrator stories should consume the existing `TransformRegistry` contract directly and keep `RecipeEngine.apply` returning `RecipeOutcome`.
