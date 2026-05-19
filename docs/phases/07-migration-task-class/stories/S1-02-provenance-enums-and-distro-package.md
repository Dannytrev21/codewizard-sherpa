# Story S1-02 — `DistroPackage` + `AppKind` / `BaseKind` / `UnknownReason` / `AdapterConfidence` enums

**Step:** Step 1 — Scaffold `vuln.provenance` primitive — newtypes, Provenance union, Protocol, errors, SyftSbom reader, fences
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0004 (the primitive's home — these enums land under `src/codegenie/primitives/vuln_provenance/types.py`), production ADR-0033 (sum-type discipline; `UnknownReason` is a `Literal` union, not a `str`), production ADR-0038 (the `Provenance` contract names `AppKind`, `BaseKind`, `UnknownReason`, `AdapterConfidence`)

## Context

Before the seven-variant `Provenance` discriminated union can land in S1-03, the supporting types it composes — `DistroPackage`, `AppKind`, `BaseKind`, `UnknownReason`, `AdapterConfidence` — must exist with `frozen=True, extra="forbid"` discipline and `mypy --strict` clean. The `Both` variant's nested `app_record: AppKind` / `base_record: BaseKind` discriminated-union constraint (which makes `Both(Both, ...)` unrepresentable at validation time) only works if these two `Annotated[Union[...], Field(discriminator="kind")]` aliases are pinned **before** S1-03 imports them. This story lands the supporting vocabulary as the seed for the union — splitting the work out keeps S1-03 focused on the seven variants + the recursion guard, not on enum bikeshedding.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §2` — names every supporting type the union uses (`AppKind`, `BaseKind`, `UnknownReason`, `AdapterConfidence`) and the verbatim Pydantic shape.
  - `../phase-arch-design.md §Data model` — `class DistroPackage(_Frozen)` with `distro: Literal["alpine", "debian", "ubuntu", "rhel"]`, `name: str`, `version: str`.
  - `../phase-arch-design.md §Data model` "Contract (Phase 7 introduces)" block — `UnknownReason = Literal["sbom_layer_attribution_absent", "no_adapter_resolved", "adapter_error", "base_image_already_distroless", "build_failed", "dockerfile_parse_failed"]` and `class AdapterConfidence(str, Enum): HIGH, DEGRADED, UNAVAILABLE`.
  - `../phase-arch-design.md §Edge cases` rows 1 + 4 + 13 — the `UnknownReason` values each map to a specific edge case; the test matrix mirrors this.
- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — the primitive's `types.py` is the home for these enums.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — sum types via `Literal` + `Enum`; no stringly-typed identifiers.
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — names every supporting type; this story implements the verbatim shape.
- **Existing code:**
  - `src/codegenie/transforms/outcomes.py` — Phase 3 precedent for `class _Frozen(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")` + discriminated union; mirror the style.
  - `src/codegenie/types/identifiers.py` — `CveId`, `PackageId`, `ImageDigest`, `LayerDigest` (S1-01); `DistroPackage.name` / `.version` stay as `str` per the arch (not new newtypes — those would be premature ADR-0033 expansion).
- **External docs:**
  - Pydantic v2 docs §"Discriminated Unions" — the `Annotated[Union[...], Field(discriminator="kind")]` idiom S1-03 will compose `AppKind` / `BaseKind` into.

## Goal

Land the four supporting types under `src/codegenie/primitives/vuln_provenance/types.py` — `DistroPackage`, `AppKind`, `BaseKind`, `UnknownReason`, `AdapterConfidence` — with `frozen=True, extra="forbid"`, `Literal` discriminators, exhaustive enum coverage, and a `match`/`assert_never` exhaustiveness anchor — so S1-03 can compose them into the seven-variant `Provenance` discriminated union without further type-level invention.

## Acceptance criteria

- [ ] **AC-1 — Module + `_Frozen` base.** `src/codegenie/primitives/vuln_provenance/types.py` (new file) carries `class _Frozen(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")` as the shared base. The Pydantic version is the existing repo-pinned v2 (no upgrade).
- [ ] **AC-2 — `DistroPackage`.** Frozen Pydantic model with three fields:
  - `name: str` (non-empty; min_length=1 enforced via Pydantic `Field`).
  - `version: str` (non-empty; min_length=1).
  - `distro: Literal["alpine", "debian", "ubuntu", "rhel"]` (closed set).
  Extra fields raise `ValidationError`. `frozen=True` rejects post-construction attribute mutation.
- [ ] **AC-3 — `AdapterConfidence` enum.** `class AdapterConfidence(str, Enum)` with values `HIGH = "high"`, `DEGRADED = "degraded"`, `UNAVAILABLE = "unavailable"`. String round-trip pinned: `AdapterConfidence("high") is AdapterConfidence.HIGH`; `AdapterConfidence.HIGH.value == "high"`.
- [ ] **AC-4 — `UnknownReason` Literal union.** `UnknownReason = Literal["sbom_layer_attribution_absent", "no_adapter_resolved", "adapter_error", "base_image_already_distroless", "build_failed", "dockerfile_parse_failed"]`. The six values appear verbatim from `phase-arch-design.md §Data model`. A `match` + `assert_never` exhaustiveness test (see TDD plan below) covers every value — adding a new reason without updating the test is a CI failure.
- [ ] **AC-5 — `AppKind` / `BaseKind` forward-declared.** Module-level type aliases declared with `TYPE_CHECKING`-guarded `Annotated[Union[...], Field(discriminator="kind")]` placeholders so S1-03 can import them and bind the union over the actual variants. **This story ships the *names*; S1-03 ships the *bodies*.** A `# TODO(S1-03)` marker names the follow-up.
- [ ] **AC-6 — Exhaustiveness via `match` + `assert_never`.** `tests/unit/primitives/vuln_provenance/test_unknown_reason_exhaustiveness.py` carries a function:
  ```python
  def _describe(r: UnknownReason) -> str:
      match r:
          case "sbom_layer_attribution_absent": ...
          case "no_adapter_resolved": ...
          case "adapter_error": ...
          case "base_image_already_distroless": ...
          case "build_failed": ...
          case "dockerfile_parse_failed": ...
          case _:
              assert_never(r)
      return ...
  ```
  Test exercises every reason. Adding a new reason without updating `_describe` makes `mypy --strict` fail because `assert_never` would receive a non-`Never` argument.
- [ ] **AC-7 — `DistroPackage` rejection matrix.** Parametrized test: extra field → `ValidationError`; `distro="centos"` (not in `Literal`) → `ValidationError`; empty `name` or empty `version` → `ValidationError`; mutation post-construction (`pkg.name = "x"`) → `ValidationError` (frozen).
- [ ] **AC-8 — `AdapterConfidence` round-trip.** JSON round-trip pinned (`AdapterConfidence.HIGH.value == "high"` and `AdapterConfidence("high") == AdapterConfidence.HIGH`). Identity assertions: the three values are distinct (`HIGH is not DEGRADED is not UNAVAILABLE`).
- [ ] **AC-9 — Module imports nothing forbidden.** `tests/unit/primitives/vuln_provenance/test_types_module_purity.py` AST-walks `types.py` and asserts the imports are a subset of `{__future__, typing, enum, pydantic}`. No logging, no filesystem, no sibling-package imports — keeps the type-vocabulary file boundary clean for S1-03 to extend.
- [ ] **AC-10 — Gates.** `mypy --strict src/codegenie/primitives/vuln_provenance/` clean; `ruff check`, `ruff format --check` clean on touched files; `make lint-imports` green (no new contracts needed for this story — S1-06 lands them, but the new `primitives/` package must already be a legitimate import target).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline

1. Create `src/codegenie/primitives/__init__.py` (empty — the bounded-primitive home per ADR-0004; this story is the first to populate it).
2. Create `src/codegenie/primitives/vuln_provenance/__init__.py` (re-exports the four supporting types so S1-03 can `from codegenie.primitives.vuln_provenance import AdapterConfidence, DistroPackage, UnknownReason`).
3. Create `src/codegenie/primitives/vuln_provenance/types.py`:
   - `_Frozen` base.
   - `class AdapterConfidence(str, Enum)` with three values.
   - `UnknownReason = Literal[...]` six values.
   - `class DistroPackage(_Frozen)` three fields.
   - `AppKind` / `BaseKind` `TYPE_CHECKING`-guarded forward placeholders with `# TODO(S1-03)` markers.
4. Land tests (red-first; see TDD plan).
5. Run `mypy --strict` + `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/primitives/vuln_provenance/test_types_phase7.py`

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError
from typing import assert_never, get_args

from codegenie.primitives.vuln_provenance.types import (
    AdapterConfidence,
    DistroPackage,
    UnknownReason,
)


# --- DistroPackage (AC-2 + AC-7) ---------------------------------------------

def test_distro_package_happy_path():
    pkg = DistroPackage(name="openssl", version="3.0.7", distro="alpine")
    assert pkg.name == "openssl"
    assert pkg.distro == "alpine"


def test_distro_package_frozen():
    pkg = DistroPackage(name="openssl", version="3.0.7", distro="alpine")
    with pytest.raises(ValidationError):
        pkg.name = "evil"  # type: ignore[misc]


def test_distro_package_extra_forbid():
    with pytest.raises(ValidationError):
        DistroPackage(name="x", version="1", distro="alpine", extra_field="leak")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "x", "version": "1", "distro": "centos"},     # not in Literal
        {"name": "", "version": "1", "distro": "alpine"},      # empty name
        {"name": "x", "version": "", "distro": "alpine"},      # empty version
        {"name": "x", "version": "1", "distro": "Alpine"},     # case mismatch
    ],
)
def test_distro_package_rejects(kwargs):
    with pytest.raises(ValidationError):
        DistroPackage(**kwargs)


# --- AdapterConfidence (AC-3 + AC-8) -----------------------------------------

def test_adapter_confidence_values():
    assert AdapterConfidence.HIGH.value == "high"
    assert AdapterConfidence.DEGRADED.value == "degraded"
    assert AdapterConfidence.UNAVAILABLE.value == "unavailable"


def test_adapter_confidence_round_trip():
    assert AdapterConfidence("high") is AdapterConfidence.HIGH
    assert AdapterConfidence("degraded") is AdapterConfidence.DEGRADED
    assert AdapterConfidence("unavailable") is AdapterConfidence.UNAVAILABLE


def test_adapter_confidence_distinct():
    members = list(AdapterConfidence)
    for i, a in enumerate(members):
        for b in members[i + 1:]:
            assert a is not b


def test_adapter_confidence_rejects_unknown():
    with pytest.raises(ValueError):
        AdapterConfidence("medium")


# --- UnknownReason (AC-4) ----------------------------------------------------

EXPECTED_REASONS = {
    "sbom_layer_attribution_absent",
    "no_adapter_resolved",
    "adapter_error",
    "base_image_already_distroless",
    "build_failed",
    "dockerfile_parse_failed",
}


def test_unknown_reason_exhaustive():
    assert set(get_args(UnknownReason)) == EXPECTED_REASONS


# --- Exhaustiveness anchor (AC-6) -------------------------------------------

def _describe(r: UnknownReason) -> str:
    match r:
        case "sbom_layer_attribution_absent":
            return "sbom"
        case "no_adapter_resolved":
            return "no_adapter"
        case "adapter_error":
            return "adapter_error"
        case "base_image_already_distroless":
            return "distroless"
        case "build_failed":
            return "build"
        case "dockerfile_parse_failed":
            return "dockerfile"
        case _:
            assert_never(r)


@pytest.mark.parametrize("reason", sorted(EXPECTED_REASONS))
def test_describe_every_reason(reason):
    assert _describe(reason) != ""  # type: ignore[arg-type]
```

State why it fails: `ImportError` — `codegenie.primitives.vuln_provenance.types` and all four supporting types do not exist.

### Green — make it pass
- Create `src/codegenie/primitives/__init__.py` (empty).
- Create `src/codegenie/primitives/vuln_provenance/__init__.py` re-exporting `AdapterConfidence`, `DistroPackage`, `UnknownReason` (and the forward `AppKind` / `BaseKind` placeholders).
- Create `src/codegenie/primitives/vuln_provenance/types.py` with `_Frozen`, `AdapterConfidence`, `UnknownReason`, `DistroPackage`, and the `TYPE_CHECKING`-guarded `AppKind` / `BaseKind` forward names.

### Refactor — clean up
- One-line docstring on each top-level name naming the ADR it instantiates (ADR-0004 + production ADR-0038).
- Confirm `__all__` is sorted and exact.
- Confirm the module imports exactly `{annotations, Enum, Literal, ConfigDict, BaseModel}` — the module-purity fence in AC-9 catches drift.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/primitives/__init__.py` | NEW — empty package init for the ADR-0004 home. |
| `src/codegenie/primitives/vuln_provenance/__init__.py` | NEW — re-export `AdapterConfidence`, `DistroPackage`, `UnknownReason`, forward `AppKind`/`BaseKind`. |
| `src/codegenie/primitives/vuln_provenance/types.py` | NEW — `_Frozen`, `AdapterConfidence`, `UnknownReason`, `DistroPackage`, forward `AppKind`/`BaseKind`. |
| `tests/unit/primitives/__init__.py` + `tests/unit/primitives/vuln_provenance/__init__.py` | NEW — test package inits. |
| `tests/unit/primitives/vuln_provenance/test_types_phase7.py` | NEW — anchors TDD red; covers DistroPackage / AdapterConfidence / UnknownReason. |
| `tests/unit/primitives/vuln_provenance/test_types_module_purity.py` | NEW — module-purity fence on `types.py` imports. |

## Out of scope

- **The seven-variant `Provenance` union** — landed by S1-03 (which composes `AppKind` / `BaseKind` over the variants this story declares as placeholders).
- **`VulnProvenanceAdapter` Protocol** — landed by S1-04.
- **`SyftSbom` reader** — landed by S1-05.
- **Phase 7 LLM-SDK / no-`Any` import-linter contracts** — landed by S1-06.
- **`Layer` / `Ecosystem` enums** — landed by S2-01 (those are registry-side; this story is types-side).
- **Newtypes for `DistroPackage.name` / `.version`** — deliberately not landed; the arch keeps them as `str` (ADR-0033 admits raw `str` for non-identifier fields).

## Notes for the implementer

- **The arch is verbatim.** Every value of `AdapterConfidence` and every reason in `UnknownReason` appears in `phase-arch-design.md §Data model` as the contract Phase 7 ships. Do not "improve" the names or add a seventh `UnknownReason` value — admitting a new reason is an ADR-0004 amendment, not a story tweak.
- **`AppKind` / `BaseKind` are placeholders this story.** S1-03 binds them to the actual variant unions. The `TYPE_CHECKING` marker keeps `mypy --strict` happy without S1-03 needing to land first. Use the form:
  ```python
  if TYPE_CHECKING:
      # S1-03 binds AppKind = Annotated[Union[AppDirect, AppTransitive, AppVendored], Field(discriminator="kind")]
      AppKind = "AppKind"  # type: ignore[assignment]
      BaseKind = "BaseKind"  # type: ignore[assignment]
  ```
  …or an equivalent forward-reference shape; the important property is that *importing the names succeeds today* and S1-03 can bind real values without circular imports.
- **`UnknownReason` is a `Literal`, not an `Enum`.** The arch made this choice deliberately: Pydantic discriminated unions discriminate on `Literal` values, and `Unknown.reason: UnknownReason` is a value inside the `Provenance` discriminated union (not the discriminator itself, but a field whose contents must round-trip in JSON). Using `str` `Enum` here would force `.value` lookups everywhere.
- **`DistroPackage.distro` is a `Literal`, not an `Enum`, for the same reason** — it appears as a field inside `BaseImage`, which appears inside `Provenance`'s discriminated union. Round-tripping the JSON shape is the goal.
- **Match `transforms/outcomes.py`'s style.** Phase 3 S1-03 established the `_Frozen` base, the `frozen=True, extra="forbid"` discipline, and the discriminated-union idiom; this story extends the same pattern into `primitives/`.
- **No identifiers regenerated.** `DistroPackage.name` is a `str`, not a `PackageId` — the arch is explicit. `PackageId` is a *resolution coordinate* (`<name>@<version>`); `DistroPackage` is a *package-database row* (separate name + separate version + separate distro). Conflating them would force every adapter to fabricate a synthetic `@`-joined string.
- **`make lint-imports` may need an additive line.** The primitive's new home (`src/codegenie/primitives/vuln_provenance/`) is now an importable target. If the existing `import-linter` contracts have a "no new top-level packages" rule, surface it — but per ADR-0004, `primitives/` is the named additive home, so this should already be admitted. Verify before landing.
