# Story S16-01 — Migration refusal taxonomy: closed `PendingHumanReview` variant set in `outcomes.py`

**Step:** Step 16 — Refusal taxonomy + recipe transformation contract (G5, M2)
**Status:** Ready
**Effort:** M
**Depends on:** S1-03 (seven-variant `Provenance` discriminated union — establishes the nested-discriminated-union / `match`+`assert_never` exhaustiveness pattern this story copies for the refusal sub-union)
**ADRs honored:** [Phase 7 ADR-0025](../ADRs/0025-migration-refusal-taxonomy.md) (refusal is a closed typed taxonomy of `PendingHumanReview` variants, each carrying source-location evidence), [Phase 7 ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) (the ADR-gated additive byte-edit to `src/codegenie/transforms/outcomes.py` — allowlist row 5), [Phase 3 ADR-0010](../../03-vuln-deterministic-recipe/ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md) (domain-modeling discipline — closed sum types + newtypes, the precedent for a closed refusal taxonomy), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) (sum types over booleans; `frozen=True` + `extra="forbid"`; make illegal states unrepresentable)

## Context

`final-design.md §Amendment A §A.1` sets the governing principle for Phase 7: for every migration it attempts, the system must either **gather enough context to transform the case correctly**, or **refuse with typed evidence** naming the exact source location. Shipping a broken image — one that builds clean, passes the gate, merges, then `ENOENT`s at runtime because `/bin/sh` is gone — is the single unacceptable outcome. Refusal is therefore a *first-class outcome*, not an exception and not a silent skip.

Phase 3 already shipped `RemediationOutcome` in `src/codegenie/transforms/outcomes.py` — a four-variant discriminated union (`Validated | RequiresHumanReview | RemediationNotApplicable | RemediationFailed`). The `RequiresHumanReview` arm carries a free-text `reason: HumanReviewReason` (a three-member `Literal`). [ADR-0025](../ADRs/0025-migration-refusal-taxonomy.md) (gap M2, `phase-arch-design.md §Component design — Amendment A §22`) requires Phase 7's migration recipes to refuse with a **closed typed taxonomy** carrying a structured source-location payload — not a free-text reason. A stringly-typed escape hatch defeats `match` exhaustiveness, cannot render a structured source location into the PR description, and lets two recipes refusing "the same way" drift to two different strings.

This story lands that taxonomy as an **additive** edit to `outcomes.py`. It adds a closed six-variant refusal sub-union and one new `PendingHumanReview` arm to the `RemediationOutcome` umbrella. It does NOT edit, rename, or restructure any existing variant — Phase 3's four-variant `RemediationOutcome`, its `kind` literals, and `HumanReviewReason` are untouched. The edit is ADR-gated: [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) row 5 enumerates `src/codegenie/transforms/outcomes.py` as the one allowed additive byte-edit-target for Amendment A's refusal variants; the byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) must carry that row before this story's edit lands, or CI fails.

The recipes that *emit* these variants (`DockerfileBaseImageSwapTransform`, `DockerfileMultiStageRefactorTransform`) are amended in **S16-02**; the gap-G5 entrypoint rewrite that emits `RefusedNonDeterministicEntrypoint` is **S16-03**. This story lands the *type surface only* — the closed variant set, the source-location payload, the umbrella wiring, and the exhaustiveness machinery — so S16-02/S16-03 have a typed contract to construct against.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §22` — "Migration refusal taxonomy (M2)": the six variant names, the closed-set rule, the structured source-location payload (file + line/instruction index), `match`/`assert_never` exhaustiveness at every consumer.
  - `../phase-arch-design.md §Component design — Amendment A §15 / §18` — `DockerfileSecretPatternProbe` (triggers `RefusedOpaqueSecretScript`) and `RuntimeShellInvocationProbe` (triggers `RefusedRuntimeShellOutInProductionCode`); read for the evidence shape each refusal preserves.
  - `../phase-arch-design.md §Data model` — the `Provenance` seven-variant `Union` block + `UnknownReason` `Literal`; the refusal sub-union mirrors this nested-discriminated-union shape.
- **Phase ADRs:**
  - [`../ADRs/0025-migration-refusal-taxonomy.md`](../ADRs/0025-migration-refusal-taxonomy.md) — the canonical decision. §Decision enumerates all six variants and their semantics; §Consequences names the property test (every variant carries a non-empty source-location payload) and the exhaustiveness test (a synthetic seventh variant breaks `mypy --strict` at every consumer).
  - [`../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md`](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) — §Decision row 5: `src/codegenie/transforms/outcomes.py` gains additive `PendingHumanReview` refusal variants. The fence-allowlist row must land alongside (or before) this story's edit.
- **Source design:**
  - `../final-design.md §Amendment A §A.1` (gather-or-refuse governing principle), §A.2 gap M2 row, §A.3 departure #2 ("the recipe is no longer 'always produces a diff' — it produces a diff *or* a typed refusal").
- **Existing code:**
  - `src/codegenie/transforms/outcomes.py` — the Phase 3 file this story additively edits. Mirror its style **verbatim**: `model_config = ConfigDict(frozen=True, extra="forbid")`, `kind: Literal["..."] = "..."` per variant, `Annotated[A | B | C, Field(discriminator="kind")]` umbrellas, sorted `__all__`.
  - `src/codegenie/primitives/vuln_provenance/types.py` (S1-03) — the seven-variant `Provenance` union + nested `AppKind` / `BaseKind` discriminated unions; the structural precedent for the closed refusal sub-union.
  - `tests/unit/transforms/test_exhaustiveness.py` — Phase 3's existing `match`/`assert_never` exhaustiveness test over `RemediationOutcome`; this story extends it for the new `PendingHumanReview` arm.
  - `tests/unit/transforms/test_outcomes.py` — Phase 3's per-variant construction / `frozen` / `extra="forbid"` suite; this story extends it.
  - `src/codegenie/types/identifiers.py` — newtype home; this story may need a `DockerfileInstructionIndex` newtype (see AC-3).

## Goal

Additively edit `src/codegenie/transforms/outcomes.py` to add the migration refusal taxonomy from [ADR-0025](../ADRs/0025-migration-refusal-taxonomy.md):

1. A `RefusalSourceLocation` payload model — a frozen `(file_path, line_or_instruction_index)` pair, the structured evidence every refusal carries.
2. Six closed refusal variant classes — `RefusedOpaqueSecretScript`, `RefusedRuntimeShellOutInProductionCode`, `RefusedNativeModulesUnclassified`, `RefusedNonDeterministicEntrypoint`, `RefusedArchitectureLoss`, `RefusedExternalRegistryBaseImage` — each `frozen=True`, `extra="forbid"`, each with a distinct `kind` literal and a `source: RefusalSourceLocation` field.
3. A `MigrationRefusal` discriminated-union alias over exactly those six variants (`Annotated[..., Field(discriminator="kind")]`).
4. A new `PendingHumanReview` variant on the `RemediationOutcome` umbrella — `kind: Literal["pending_human_review"]` — carrying a `refusal: MigrationRefusal` field, wired into the `RemediationOutcome` `Annotated[...]` alias as a fifth arm.

Every consumer that `match`es on `RemediationOutcome` gains an exhaustive arm; a synthetic seventh refusal variant must break `mypy --strict`. Phase 3's existing four `RemediationOutcome` consumers (`tests/unit/transforms/test_exhaustiveness.py` and any orchestrator dispatch) still pass. The byte-edit allowlist fence (ADR-0029 row 5) is green.

## Acceptance criteria

### Source-location payload

- [ ] **AC-1 — `RefusalSourceLocation` payload model.** `outcomes.py` defines `class RefusalSourceLocation(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and two fields: `file_path: str` (a repo-relative path — the Dockerfile or the offending source file) and `index: int` (a 0-based line number for source files, or a 0-based Dockerfile-instruction index for Dockerfile refusals). `index` is constrained `>= 0` via `Field(ge=0)`. The model carries a docstring naming "make-illegal-states-unrepresentable" and ADR-0025.
- [ ] **AC-2 — `file_path` is non-empty.** Constructing `RefusalSourceLocation(file_path="", index=0)` raises `ValidationError` (a `field_validator` rejecting the empty string). The refusal MUST name a source location; an empty path is not a location. Test pins this with a docstring naming ADR-0025 §A.1 ("naming the exact source location").
- [ ] **AC-3 — Newtype discipline check.** If a `DockerfileInstructionIndex` / `SourceLineNumber` newtype is introduced under `codegenie.types.identifiers` for `index`, it follows the existing newtype pattern (`NewType` + smart-constructor or `Annotated` constraint) and is exported. If a bare `int` with `Field(ge=0)` is chosen instead (acceptable — `index` is a positional offset, not a domain identifier per the S1-01 newtype rubric), the story states that choice explicitly in `## Notes for the implementer` and does NOT introduce an unused newtype. **Pick one and document the rationale.**

### Six closed refusal variants

- [ ] **AC-4 — Six variant classes, each constructible with its payload.** `outcomes.py` defines six classes, each `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`, each with a distinct `kind: Literal[...]` (defaulted) and a `source: RefusalSourceLocation` field:
  - `RefusedOpaqueSecretScript` — `kind: Literal["refused_opaque_secret_script"]`. Carries `source` + `script_path: str` (the `COPY`'d-then-`RUN` shell script the secret-pattern probe could not parse — ADR-0018 ships no `tree-sitter-bash`).
  - `RefusedRuntimeShellOutInProductionCode` — `kind: Literal["refused_runtime_shell_out_in_production_code"]`. Carries `source` + `argv0: str` (the `argv[0]` literal outside `{node, npm, yarn}` from a `blocking` `RuntimeShellInvocationProbe` hit in `src/**`).
  - `RefusedNativeModulesUnclassified` — `kind: Literal["refused_native_modules_unclassified"]`. Carries `source` + `unclassified_packages: tuple[str, ...]` (build-toolchain packages absent from the `apk`/`apt` classification catalog; `Field(min_length=1)` — refusing with zero unclassified packages is an illegal state).
  - `RefusedNonDeterministicEntrypoint` — `kind: Literal["refused_non_deterministic_entrypoint"]`. Carries `source` + `directive: Literal["ENTRYPOINT", "CMD"]` + `raw_form: str` (the shell-form / env-substituted / `npm start` directive text the recipe could not rewrite — gap G5).
  - `RefusedArchitectureLoss` — `kind: Literal["refused_architecture_loss"]`. Carries `source` + `lost_architectures: tuple[str, ...]` (`Field(min_length=1)` — architectures the source supports that the recommended Chainguard image does not).
  - `RefusedExternalRegistryBaseImage` — `kind: Literal["refused_external_registry_base_image"]`. Carries `source` + `registry: str` (the non-public / mirror registry host the migration cannot resolve or attest against).
- [ ] **AC-5 — Each variant individually round-trips through Pydantic.** A parametrized test over **all six** variants: for each, construct a happy-path instance, `model_dump()` it, and `TypeAdapter(MigrationRefusal).validate_python(payload)` reconstructs an equal object. A second parametrize sweep does the JSON-string round-trip (`adapter.validate_json(adapter.dump_json(p)) == p`) — catches `tuple` ↔ `list` coercion drift on the `tuple[str, ...]` fields.
- [ ] **AC-6 — `frozen=True` + `extra="forbid"`, every variant.** Two parametrized tests over all six variants: (a) post-construction mutation (`r.source = ...`) raises `ValidationError`; (b) constructing with an unknown kwarg raises `ValidationError`. Plus the same two checks on `RefusalSourceLocation`.
- [ ] **AC-7 — Non-empty source-location payload, every variant (property test).** A property test (`tests/property/transforms/test_refusal_taxonomy.py`) over Hypothesis-generated instances of every refusal variant asserts `r.source.file_path != ""` and `r.source.index >= 0` for every constructible instance. This pins ADR-0025 §Consequences: "every `PendingHumanReview` variant carries a non-empty source-location payload."

### Closed sub-union + umbrella wiring

- [ ] **AC-8 — `MigrationRefusal` discriminated-union alias.** `outcomes.py` defines:
  ```python
  MigrationRefusal = Annotated[
      RefusedOpaqueSecretScript
      | RefusedRuntimeShellOutInProductionCode
      | RefusedNativeModulesUnclassified
      | RefusedNonDeterministicEntrypoint
      | RefusedArchitectureLoss
      | RefusedExternalRegistryBaseImage,
      Field(discriminator="kind"),
  ]
  ```
  Exactly six arms; closed at the type. `TypeAdapter(MigrationRefusal).validate_python(...)` routes every variant correctly.
- [ ] **AC-9 — `PendingHumanReview` arm on `RemediationOutcome`.** `outcomes.py` defines `class PendingHumanReview(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")`, `kind: Literal["pending_human_review"] = "pending_human_review"`, and a `refusal: MigrationRefusal` field. The `RemediationOutcome` umbrella alias is widened **additively** to a five-arm union:
  ```python
  RemediationOutcome = Annotated[
      Validated | RequiresHumanReview | RemediationNotApplicable
      | RemediationFailed | PendingHumanReview,
      Field(discriminator="kind"),
  ]
  ```
  The four existing arms and their `kind` literals are **unchanged** — `pending_human_review` is a new discriminator value, distinct from `requires_human_review` (Phase 3's universal-fallback arm, which is NOT a migration refusal).
- [ ] **AC-10 — `__all__` and `transforms/__init__.py` re-exports extended, sorted.** `outcomes.py`'s `__all__` gains `MigrationRefusal`, `PendingHumanReview`, `RefusalSourceLocation`, and the six variant class names — inserted in sorted position (the list is alphabetically sorted; an inserted-at-the-end entry fails the existing sort check). `src/codegenie/transforms/__init__.py` re-exports the same nine names, also in sorted `__all__` position. `from codegenie.transforms import PendingHumanReview, MigrationRefusal, RefusalSourceLocation, RefusedOpaqueSecretScript` succeeds.

### Exhaustiveness

- [ ] **AC-11 — Consumer `match` over `RemediationOutcome` is exhaustive.** A test (`tests/unit/transforms/test_refusal_exhaustiveness.py`) defines a `_describe(o: RemediationOutcome) -> str` that `match`es all five arms (`Validated`, `RequiresHumanReview`, `RemediationNotApplicable`, `RemediationFailed`, `PendingHumanReview`) with a final `case _: assert_never(o)`, and runs it over a happy-path instance of every arm. The test asserts `_describe(PendingHumanReview(refusal=...))` returns the expected label for each of the six refusal variants (an inner `match` over `MigrationRefusal` with its own `assert_never`).
- [ ] **AC-12 — Inner `match` over `MigrationRefusal` is exhaustive.** The same test file (or a sibling) defines `_describe_refusal(r: MigrationRefusal) -> str` `match`ing all six refusal variants with a final `case _: assert_never(r)`, exercised over one instance of each. mypy --strict would flag a missing arm.
- [ ] **AC-13 — Synthetic-seventh-variant mypy-negative pin.** `tests/unit/transforms/test_refusal_taxonomy_mypy_negative.py` (mirrors the S1-03 `test_provenance_mypy_negative.py` precedent) carries a commented exemplar: adding a hypothetical seventh refusal variant to `MigrationRefusal` without updating `_describe_refusal` MUST surface as a `mypy --strict` error on the `assert_never` arm. The test documents this contract (closed taxonomy → adding a variant is a coordinated edit per ADR-0025 §Tradeoffs) and, where the project's mypy-negative harness supports it (the S1-01 / S1-03 precedent), asserts it mechanically.

### Regression — Phase 3 consumers unbroken

- [ ] **AC-14 — Phase 3's existing `RemediationOutcome` consumers still pass.** `tests/unit/transforms/test_exhaustiveness.py` (Phase 3's `match`/`assert_never` over the original four-arm `RemediationOutcome`) is updated to add the fifth `PendingHumanReview` arm so it stays exhaustive — this is the *intended* coordinated edit of a closed taxonomy (ADR-0025 §Tradeoffs). Every other Phase 3 consumer of `RemediationOutcome` that `match`es it gains the fifth arm. No existing `kind` literal is renamed; no existing variant's fields change.
- [ ] **AC-15 — Byte-edit allowlist fence green.** `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` carries the ADR-0029 row 5 allowance for `src/codegenie/transforms/outcomes.py`. The fence is green after this story's additive edit. If the fence row is not yet present (S13's ADR-0029 amendment landed it), this story adds the row; if already present, no fence edit is needed — state which in the attempt log.

### Gates

- [ ] **AC-16** — `mypy --strict src/` clean (project-wide, not just `transforms/` — catches cross-package drift in any module importing `RemediationOutcome`).
- [ ] **AC-17** — `ruff check` and `ruff format --check` clean on `src/codegenie/transforms/outcomes.py`, `src/codegenie/transforms/__init__.py`, and every touched test file.
- [ ] **AC-18** — `make lint-imports` green (no LLM SDK in the `transforms` runtime closure; the refusal variants import only `pydantic` + `codegenie.types.identifiers`).
- [ ] **AC-19** — `make check` end-to-end green; Phase 3–6.5 regression suite passes; `bench/vuln-remediation/` cassette replay byte-equal (ε ≤ $0.01) — confirms the additive `outcomes.py` edit did not perturb the Phase 3 contract snapshot (S6-06).

## Implementation outline

1. **Decide `index` typing.** Per AC-3: either a bare `int` with `Field(ge=0)` (recommended — `index` is a positional offset, not a domain identifier) or a newtype. If a newtype, add it to `codegenie.types.identifiers` first. Document the choice.
2. **`RefusalSourceLocation`** — add the frozen `(file_path: str, index: int)` model with the empty-`file_path` `field_validator` (AC-1, AC-2). Place it near the top of the new Amendment-A section in `outcomes.py`, after the existing reason-literal taxonomies.
3. **Six refusal variant classes** — add each with its `kind` literal default, its `source: RefusalSourceLocation` field, and its variant-specific payload field(s). Use `Field(min_length=1)` on the `tuple[str, ...]` fields that must be non-empty (`unclassified_packages`, `lost_architectures`). Mirror `outcomes.py`'s existing variant style verbatim (one-line semantic docstring per class naming ADR-0025).
4. **`MigrationRefusal` alias** — the six-arm `Annotated[..., Field(discriminator="kind")]` union (AC-8). Declare after all six variant classes.
5. **`PendingHumanReview`** — the new umbrella arm carrying `refusal: MigrationRefusal` (AC-9). Declare after `MigrationRefusal`.
6. **Widen `RemediationOutcome`** — add `| PendingHumanReview` to the existing `Annotated[...]` alias (AC-9). This is the only edit to an *existing* line in `outcomes.py`; everything else is pure addition.
7. **Extend `__all__`** in `outcomes.py` and the re-export `__all__` in `transforms/__init__.py`, both in sorted position (AC-10).
8. **Update Phase 3's `tests/unit/transforms/test_exhaustiveness.py`** — add the fifth `PendingHumanReview` arm so the existing exhaustiveness test stays green (AC-14).
9. **New tests** — `test_refusal_taxonomy.py` (construction / frozen / extra / round-trip — AC-4..AC-6), `test_refusal_exhaustiveness.py` (AC-11, AC-12), `test_refusal_taxonomy_mypy_negative.py` (AC-13), `tests/property/transforms/test_refusal_taxonomy.py` (AC-7).
10. **Byte-edit allowlist fence** — confirm or add ADR-0029 row 5 in `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (AC-15).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_refusal_taxonomy.py`

```python
from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError


def _loc():
    from codegenie.transforms import RefusalSourceLocation

    return RefusalSourceLocation(file_path="Dockerfile", index=4)


def test_refusal_source_location_rejects_empty_path() -> None:
    """ADR-0025 §A.1: a refusal MUST name the exact source location.
    An empty file_path is not a location — reject it at construction."""
    from codegenie.transforms import RefusalSourceLocation

    with pytest.raises(ValidationError):
        RefusalSourceLocation(file_path="", index=0)


def test_refused_opaque_secret_script_constructs() -> None:
    """RefusedOpaqueSecretScript carries the COPY'd shell script the
    secret-pattern probe (ADR-0018, no tree-sitter-bash) could not parse."""
    from codegenie.transforms import RefusedOpaqueSecretScript

    r = RefusedOpaqueSecretScript(source=_loc(), script_path="scripts/fetch-token.sh")
    assert r.kind == "refused_opaque_secret_script"
    assert r.source.file_path == "Dockerfile"
    assert r.script_path == "scripts/fetch-token.sh"


def test_refused_native_modules_requires_at_least_one_package() -> None:
    """Refusing 'native modules unclassified' with an empty package tuple is
    an illegal state — the refusal must name what could not be classified."""
    from codegenie.transforms import RefusedNativeModulesUnclassified

    with pytest.raises(ValidationError):
        RefusedNativeModulesUnclassified(source=_loc(), unclassified_packages=())


@pytest.mark.parametrize(
    "build",
    [
        lambda loc: __import__(
            "codegenie.transforms", fromlist=["RefusedOpaqueSecretScript"]
        ).RefusedOpaqueSecretScript(source=loc, script_path="s.sh"),
        lambda loc: __import__(
            "codegenie.transforms", fromlist=["RefusedNonDeterministicEntrypoint"]
        ).RefusedNonDeterministicEntrypoint(
            source=loc, directive="CMD", raw_form="npm start"
        ),
        lambda loc: __import__(
            "codegenie.transforms", fromlist=["RefusedArchitectureLoss"]
        ).RefusedArchitectureLoss(source=loc, lost_architectures=("armv7",)),
    ],
)
def test_migration_refusal_round_trips(build) -> None:
    """Every refusal variant round-trips through the MigrationRefusal
    discriminated union — the closed sub-union routes each variant by kind."""
    from codegenie.transforms import MigrationRefusal

    r = build(_loc())
    adapter = TypeAdapter(MigrationRefusal)
    assert adapter.validate_python(r.model_dump()) == r
    assert adapter.validate_json(adapter.dump_json(r)) == r


def test_pending_human_review_wraps_a_refusal() -> None:
    """PendingHumanReview is the RemediationOutcome arm a refusing recipe
    emits — it carries a typed MigrationRefusal, not a free-text reason."""
    from codegenie.transforms import (
        PendingHumanReview,
        RefusedRuntimeShellOutInProductionCode,
        RemediationOutcome,
    )

    refusal = RefusedRuntimeShellOutInProductionCode(
        source=_loc(), argv0="ffmpeg"
    )
    outcome = PendingHumanReview(refusal=refusal)
    assert outcome.kind == "pending_human_review"
    rebuilt = TypeAdapter(RemediationOutcome).validate_python(outcome.model_dump())
    assert rebuilt == outcome
```

State why it fails: `ImportError` — `RefusalSourceLocation`, the six refusal variant classes, `MigrationRefusal`, and `PendingHumanReview` do not exist in `codegenie.transforms` yet.

### Green — minimal pass

- Add `RefusalSourceLocation` (frozen model + empty-path `field_validator`) to `outcomes.py`.
- Add the six refusal variant classes, each `frozen=True` + `extra="forbid"`, each with its `kind` literal and `source` field plus variant-specific payload, with `Field(min_length=1)` on the non-empty `tuple[str, ...]` fields.
- Add the `MigrationRefusal` six-arm discriminated-union alias.
- Add `PendingHumanReview` carrying `refusal: MigrationRefusal`; widen `RemediationOutcome` by appending `| PendingHumanReview`.
- Extend both `__all__` lists (in `outcomes.py` and `transforms/__init__.py`) in sorted position.
- Update `tests/unit/transforms/test_exhaustiveness.py` with the fifth arm.

### Refactor

- Group the new symbols under a clearly-commented `# Amendment A — migration refusal taxonomy (ADR-0025)` section header in `outcomes.py`, after the existing `Applicability` block — keep the Phase 3 section visually untouched.
- Give each refusal variant a one-line docstring naming the gap it serves (`RefusedOpaqueSecretScript` → "G1; ADR-0018 ships no tree-sitter-bash, so a COPY'd-then-RUN script's secret path cannot be preserved").
- Confirm the inner-`match` exhaustiveness test (`_describe_refusal`) is green and that temporarily commenting out one `case` arm makes `mypy --strict` flag the `assert_never` arm (intentional regression check; restore afterward).
- Verify the byte-edit allowlist fence (ADR-0029 row 5) is green; verify the Phase 3 cassette replay (`bench/vuln-remediation/`) is byte-equal.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/outcomes.py` | ADR-gated additive edit (ADR-0029 row 5) — add `RefusalSourceLocation`, six refusal variants, `MigrationRefusal` alias, `PendingHumanReview`; widen `RemediationOutcome` by one arm; extend `__all__`. No existing variant edited or renamed. |
| `src/codegenie/transforms/__init__.py` | Re-export the nine new names in sorted `__all__` position. |
| `src/codegenie/types/identifiers.py` | ONLY IF a newtype is chosen for `index` (AC-3) — add `DockerfileInstructionIndex` / `SourceLineNumber`. Recommended: skip (bare `int` + `Field(ge=0)`). |
| `tests/unit/transforms/test_refusal_taxonomy.py` | NEW — anchors TDD red; AC-1, AC-2, AC-4, AC-5, AC-6. |
| `tests/unit/transforms/test_refusal_exhaustiveness.py` | NEW — `match`/`assert_never` over `RemediationOutcome` (5 arms) and `MigrationRefusal` (6 arms); AC-11, AC-12. |
| `tests/unit/transforms/test_refusal_taxonomy_mypy_negative.py` | NEW — synthetic-seventh-variant mypy-negative pin (AC-13); mirrors `tests/unit/primitives/vuln_provenance/test_provenance_mypy_negative.py`. |
| `tests/property/transforms/test_refusal_taxonomy.py` | NEW — Hypothesis property: every refusal variant carries a non-empty source-location payload (AC-7). |
| `tests/unit/transforms/test_exhaustiveness.py` | Extend — add the fifth `PendingHumanReview` arm to the existing Phase 3 `RemediationOutcome` exhaustiveness test (AC-14). |
| `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` | Confirm or add the ADR-0029 row 5 allowance for `outcomes.py` (AC-15). |

## Out of scope

- **The recipes that *emit* these variants** — `DockerfileBaseImageSwapTransform` / `DockerfileMultiStageRefactorTransform` gaining typed gather inputs and the ability to refuse is **S16-02**. This story lands the type surface only.
- **The gap-G5 entrypoint rewrite** that emits `RefusedNonDeterministicEntrypoint` from a real Dockerfile is **S16-03**. This story only makes the variant *constructible*.
- **`DockerfilePolicyGate` consuming the refusal taxonomy** — Step 16's done-criteria names it; the gate edit is S10-03's amended scope, not this story.
- **`MigrationConfidence` rollup** (`High | Degraded | Refused`) — that is Step 17 / ADR-0026 / a separate story. `MigrationConfidence.Refused` and `MigrationRefusal` are distinct types: the former is a confidence rollup, the latter a recipe-outcome taxonomy.
- **PR-description rendering of the source-location payload** — Step 18 / ADR-0027 observability bundle. This story makes the payload *structured*; rendering it is downstream.
- **Adding a seventh refusal variant** — closed taxonomy; a seventh variant is an ADR-0025 amendment plus a coordinated consumer edit, not this story.

## Notes for the implementer

- **This is an ADR-gated additive edit to a Phase 3 file.** `outcomes.py` is locked by the byte-edit allowlist fence (ADR-0009 / ADR-0029). Edit it **only additively**: add new classes, add to `__all__`, append exactly one arm to the `RemediationOutcome` `Annotated[...]` alias. Do NOT rename a `kind` literal, do NOT touch a Phase 3 variant's fields, do NOT reorder the existing four arms. The Phase 3 contract-snapshot test (S6-06) and the cassette replay are the behavioral tripwires (AC-19).
- **`pending_human_review` is a distinct `kind` from `requires_human_review`.** Phase 3's `RequiresHumanReview` is the *universal-fallback-exhausted* arm (`HumanReviewReason` — `no_concrete_match` / `trust_outcome_failed` / `policy_violation_unrecoverable`). The new `PendingHumanReview` is the *migration-recipe-refused* arm. They are not the same outcome and must not share a discriminator value — a `match` needs to tell "the fallback gave up" from "the recipe declined with evidence" apart. ADR-0025 §Decision names `PendingHumanReview` explicitly; honor the name.
- **The closed taxonomy is NOT an Open/Closed plugin seam.** The codebase has many registry-extension seams (`@register_probe`, `@register_provenance_adapter`). The refusal variant set is deliberately not one of them — ADR-0025 §Pattern fit fixes the six variants by ADR amendment, mirroring S1-03's closed `Provenance` union. **Do NOT introduce a `@register_refusal_variant` decorator or any dispatch table for variants.** A seventh variant arrives via an ADR-0025 amendment + a coordinated consumer edit — that friction is the *intended* cost of a closed taxonomy (ADR-0025 §Tradeoffs).
- **`index` is a positional offset, not a domain identifier.** The S1-01 newtype rubric reserves newtypes for domain IDs that must not be confused with each other (`ProbeId`, `CveId`, `PackageId`). A line number / instruction index is a plain ordinal. Recommendation: bare `int` with `Field(ge=0)` — do not mint a `DockerfileInstructionIndex` newtype just for symmetry (Rule 2: no abstractions for single-use code). If you disagree, state the case in the attempt log; do not fork silently (Rule 11). AC-3 requires the choice be documented either way.
- **`field_validator` for the empty-path check, not a bare `assert`.** Bare `assert` is banned by the `forbidden-patterns` hook. Mirror `outcomes.py`'s existing `RecipeError._message_length` `@field_validator` style: `raise ValueError("file_path must be non-empty")`.
- **Mirror `outcomes.py` verbatim.** Phase 3's file is the style template: `model_config = ConfigDict(frozen=True, extra="forbid")` (not the `_Frozen` base — `outcomes.py` uses `ConfigDict` inline; `vuln_provenance/types.py` uses `_Frozen`; these are two different files with two different conventions — match the file you are editing). `kind: Literal["..."] = "..."` with the default. `Annotated[A | B | C, Field(discriminator="kind")]` umbrellas. Sorted `__all__`. Conformance > taste (Rule 11).
- **`Field(min_length=1)` on the must-be-non-empty tuples.** `RefusedNativeModulesUnclassified.unclassified_packages` and `RefusedArchitectureLoss.lost_architectures` are illegal when empty — a refusal that names *nothing* is not evidence. Use `Annotated[tuple[str, ...], Field(min_length=1)]`, the same idiom S1-03 uses for `AppTransitive.chain` (`min_length=2`).
- **The property test (AC-7) is the load-bearing invariant.** ADR-0025 §Consequences: "a property test asserts every `PendingHumanReview` variant carries a non-empty source-location payload." Generate Hypothesis strategies for every variant; assert `r.source.file_path != ""` and `r.source.index >= 0` holds for every instance. This is the mechanical guarantee that "refusal names a location" cannot regress.
- **The synthetic-seventh-variant test (AC-13) pins the closed-taxonomy property.** Mirror `tests/unit/primitives/vuln_provenance/test_provenance_mypy_negative.py` (S1-03's recursion-guard mypy-negative pin). The contract: a seventh `MigrationRefusal` arm added without updating `_describe_refusal` must be a `mypy --strict` error on the `assert_never`. That is what makes "every consumer handles every refusal" a compile-time guarantee, not a runtime hope (ADR-0025 §Tradeoffs).
- **Phase 3 consumers gaining a fifth arm is intended, not a regression.** AC-14's edit to `test_exhaustiveness.py` is the *cost* of a closed taxonomy made visible — the `assert_never` arm forces the coordinated edit. Do not work around it by making the new arm a `case _:` fallthrough; add an explicit `case PendingHumanReview():` arm. The whole point of the taxonomy is that "forgot to handle a refusal" is a type error.
- **`make check` end-to-end, not a narrow subset.** Per CLAUDE.md's pytest config, a narrow subset run can falsely fail the `--cov-fail-under=85` gate; use `--no-cov` for ad-hoc triage but the AC-19 gate is the full `make check`. The cassette replay (`bench/vuln-remediation/`) is the proof the additive edit did not perturb Phase 3's behavior — if it drifts, the `outcomes.py` edit was not purely additive.
