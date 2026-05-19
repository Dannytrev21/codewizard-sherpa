# Story S1-02 — `DistroPackage` + `AppKind` / `BaseKind` / `UnknownReason` / `AdapterConfidence` enums

**Step:** Step 1 — Scaffold `vuln.provenance` primitive — newtypes, Provenance union, Protocol, errors, SyftSbom reader, fences
**Status:** GREEN

## GREEN evidence (2026-05-19, phase-story-executor)

All 15 ACs land with runtime evidence; see [_attempts/S1-02-provenance-enums-and-distro-package.md](_attempts/S1-02-provenance-enums-and-distro-package.md) for the ReAct trace, deviations, and lessons.

| AC | Evidence |
|---|---|
| AC-1 — `_Frozen` base | `src/codegenie/primitives/vuln_provenance/types.py` `class _Frozen` |
| AC-2 — `DistroPackage` shape | `test_distro_package_happy_path`, `_frozen_rejects_mutation`, `_extra_forbid` |
| AC-3 — `AdapterConfidence` enum | `test_adapter_confidence_values_match_arch`, `_round_trips_from_string`, `_is_string_enum` (uses `StrEnum`; see attempt log for the `(str, Enum)` deviation) |
| AC-4 — `UnknownReason` Literal × 6 | `test_unknown_reason_literal_args_match_arch`, `_args_count_is_six` |
| AC-5 — `AppKind`/`BaseKind` OUT | `__init__.py.__all__` carries exactly the three names; `types.py` carries no `AppKind`/`BaseKind` |
| AC-6 — `match` + `assert_never` | `_describe` + `test_describe_every_reason` (parametrized × 6) |
| AC-7 — rejection matrix | `test_distro_package_rejects_invalid_input` (12 cases); `test_distro_package_admits_every_supported_distro` (4 cases); whitespace `field_validator` on `name`/`version` |
| AC-8 — `AdapterConfidence` round-trip | `test_adapter_confidence_values_match_arch`, `_round_trips_from_string`, `_members_are_distinct` |
| AC-9 — exact import set | `tests/unit/primitives/vuln_provenance/test_types_module_purity.py:_ALLOWED_TOP_LEVEL_IMPORTS` (exact-equality assertion) |
| AC-10 — gates | `mypy --strict src/` 188 files clean; `ruff check` clean; `ruff format --check` clean; `lint-imports` 4 kept, 0 broken |
| AC-11 — `_Frozen` inheritance fence | `tests/fence/test_vuln_provenance_frozen_base.py` (4 parametrized cases) |
| AC-12 — JSON round-trip | `test_distro_package_json_round_trip` (4 distros) + `test_distro_package_json_keys_are_exactly_three` |
| AC-13 — `__all__` sorted + exact + no underscore-prefixed | `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` |
| AC-14 — `model_construct` fence | `tests/fence/test_vuln_provenance_no_model_construct.py` (3 parametrized cases) |
| AC-15 — `mypy --strict` negative test | `tests/unit/primitives/vuln_provenance/test_types_mypy_negative.py` (3 rejects + 3 negative-control accepts via subprocess-mypy) |

Suite delta: **+56 net new pytest items**; full suite 5367 passed (S1-01 baseline 5311); the 7 pre-existing env failures are identical to the S1-01-documented set (secret-in-source SCIP fixture×2, golden, docker sandbox×2, lint-imports PATH×2).
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0004 (the primitive's home — these enums land under `src/codegenie/primitives/vuln_provenance/types.py`), production ADR-0033 (sum-type discipline; `UnknownReason` is a `Literal` union, not a `str`), production ADR-0038 (the `Provenance` contract names `AppKind`, `BaseKind`, `UnknownReason`, `AdapterConfidence`)

## Validation notes (2026-05-19, phase-story-validator)

This story has been hardened. Cross-reference: [_validation/S1-02-provenance-enums-and-distro-package.md](_validation/S1-02-provenance-enums-and-distro-package.md). Material changes:

- **AC-5 rewritten** (was: `block`). The original `TYPE_CHECKING`-guarded `AppKind = "AppKind"` placeholder pattern would have shipped a runtime `ImportError` — at runtime `TYPE_CHECKING is False`, so the bare names would be undefined when `__init__.py` re-exports them. Resolved per Rule 2 (no pre-emptive abstractions): **S1-02 ships only `DistroPackage`, `AdapterConfidence`, `UnknownReason` + `_Frozen` base. S1-03 lands `AppKind`/`BaseKind` alongside the variants they bind.** The story's earlier framing — "the union aliases must be pinned before S1-03 imports them" — was inverted; S1-03 lands the variants AND the aliases atomically in one file, so no forward-declaration is needed.
- **AC-6 file-path collision resolved** (was: `block`). Original wording listed file `test_unknown_reason_exhaustiveness.py` but the TDD plan placed `_describe` inside `test_types_phase7.py`. Single test file pinned: `test_types_phase7.py` carries the exhaustiveness anchor.
- **AC-7 contamination matrix expanded** (was: `harden`). Original matrix didn't cover whitespace-only / leading-space contamination on `name` / `version` / `distro` (`min_length=1` admits `" "`). Added cases; added the four happy-path `distro` values (alpine/debian/ubuntu/rhel) since only `alpine` was exercised. Pydantic v2's `Literal` validation is exact-match, so case mismatch + whitespace are rejected — the test pins the behavior.
- **AC-9 module purity tightened** (was: `harden`). Stated allowed-import set is now exact (not just subset); a frozen tuple `_ALLOWED_TOP_LEVEL_IMPORTS` lives in the test, and the test is the one that fails if a future drift occurs.
- **AC-11 added — `_Frozen` inheritance fence** (was: `harden`, DP1). The `_Frozen` base is **new to Phase 7** (`transforms/outcomes.py` uses inline `model_config = ConfigDict(frozen=True, extra="forbid")` per Phase 3 precedent — there is no shared base today). An AST-walk fence ensures every `BaseModel` subclass inside `primitives/vuln_provenance/` extends `_Frozen`, locking the new convention from S1-03 onward.
- **AC-12 added — JSON round-trip for `DistroPackage`** (was: `harden`). The type lands inside `BaseImage` (per arch §Data model line 587), which serializes via `Pydantic.model_dump_json()` into the event log. A round-trip test (`pkg → JSON → DistroPackage.model_validate_json → equals`) catches silent serialization drift before downstream phases consume it.
- **AC-13 added — `__all__` sortedness + exactness** (was: `harden`). Promoted from Refactor-step prose to a typed assertion; matches the S1-01 convention (`identifiers.py.__all__` is sorted + exact).
- **AC-14 added — `model_construct` defense** (was: `harden`, T2). A mutation-resistant implementation cannot bypass validation via `BaseModel.model_construct(...)`. AST-walk fence asserts `model_construct` is absent from `types.py`. Matches Phase 7 ADR-0004 §Consequences ("a fence asserts no `model_construct()` call sites under `src/codegenie/primitives/vuln_provenance/`").
- **`Notes for the implementer` corrected** (was: `harden`, CO1). Original note claimed "Phase 3 S1-03 established the `_Frozen` base"; in fact Phase 3 uses repeated inline `model_config = ConfigDict(...)`. Note now states that `_Frozen` is introduced **by Phase 7**, with the AST-walk fence (AC-11) locking the convention going forward.

Verdict: **HARDENED**. No `NEEDS RESEARCH` findings — patterns are all idiomatic Pydantic v2 + ADR-0033 sum-type discipline already established in the codebase.

## Context

Before the seven-variant `Provenance` discriminated union can land in S1-03, three of the supporting types it composes — `DistroPackage`, `UnknownReason`, `AdapterConfidence` — plus the shared `_Frozen` base every variant inherits must exist with `frozen=True, extra="forbid"` discipline and `mypy --strict` clean. S1-03 will land `AppKind` / `BaseKind` atomically with the seven variants they bind (the `Annotated[Union[AppDirect, AppTransitive, AppVendored], Field(discriminator="kind")]` shape can't be evaluated until the variant classes exist; pre-placing the names this story would create a forward-reference graveyard, see Validation notes AC-5). Splitting the supporting vocabulary out keeps S1-03 focused on the seven variants + the recursion guard, not on enum bikeshedding, and lets the AST-walk fence introduced here (`_Frozen` inheritance) lock the convention before S1-03 lands the variants.

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

Land the supporting vocabulary under `src/codegenie/primitives/vuln_provenance/types.py` — the `_Frozen` shared base, `DistroPackage`, `UnknownReason`, `AdapterConfidence` — with `frozen=True, extra="forbid"`, `Literal` discriminators, exhaustive enum coverage, a `match`/`assert_never` exhaustiveness anchor, JSON round-trip pinned, and an AST-walk fence requiring every primitive `BaseModel` to inherit `_Frozen` — so S1-03 can land the seven `Provenance` variants + `AppKind` / `BaseKind` aliases atomically without further type-level invention or convention drift.

## Acceptance criteria

- [ ] **AC-1 — Module + `_Frozen` base.** `src/codegenie/primitives/vuln_provenance/types.py` (new file) carries `class _Frozen(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")` as the shared base. The Pydantic version is the existing repo-pinned v2 (no upgrade).
- [ ] **AC-2 — `DistroPackage`.** Frozen Pydantic model with three fields:
  - `name: str` (non-empty; min_length=1 enforced via Pydantic `Field`).
  - `version: str` (non-empty; min_length=1).
  - `distro: Literal["alpine", "debian", "ubuntu", "rhel"]` (closed set).
  Extra fields raise `ValidationError`. `frozen=True` rejects post-construction attribute mutation.
- [ ] **AC-3 — `AdapterConfidence` enum.** `class AdapterConfidence(str, Enum)` with values `HIGH = "high"`, `DEGRADED = "degraded"`, `UNAVAILABLE = "unavailable"`. String round-trip pinned: `AdapterConfidence("high") is AdapterConfidence.HIGH`; `AdapterConfidence.HIGH.value == "high"`.
- [ ] **AC-4 — `UnknownReason` Literal union.** `UnknownReason = Literal["sbom_layer_attribution_absent", "no_adapter_resolved", "adapter_error", "base_image_already_distroless", "build_failed", "dockerfile_parse_failed"]`. The six values appear verbatim from `phase-arch-design.md §Data model`. A `match` + `assert_never` exhaustiveness test (see TDD plan below) covers every value — adding a new reason without updating the test is a CI failure.
- [ ] **AC-5 — `AppKind` / `BaseKind` are explicitly OUT-OF-SCOPE for this story.** S1-03 lands the variant classes (`AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`, `Unknown`) and the `AppKind` / `BaseKind` `Annotated[Union[...], Field(discriminator="kind")]` aliases atomically in the same module. This story MUST NOT introduce string sentinels, `TypeAlias = Any`, or `TYPE_CHECKING`-guarded placeholders for these names — doing so would either (a) raise `ImportError` from `__init__.py` re-exports at runtime, or (b) widen the typed surface to `Any` in a way the next story would have to undo. The `__init__.py` re-export list this story ships is exactly `["AdapterConfidence", "DistroPackage", "UnknownReason"]` (sorted); S1-03 grows it additively.
- [ ] **AC-6 — Exhaustiveness via `match` + `assert_never`.** A single test file (`tests/unit/primitives/vuln_provenance/test_types_phase7.py`, same file as AC-7/AC-8/AC-12) carries a function:
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
- [ ] **AC-7 — `DistroPackage` rejection matrix (mutation-resistant).** Parametrized test covers every wrong-implementation an executor could plausibly ship:
  - **Extra field:** `extra_field="leak"` → `ValidationError` (`extra="forbid"`).
  - **`distro` Literal violations:** `"centos"`, `"Alpine"` (case mismatch), `" alpine"` (leading whitespace), `"alpine "` (trailing whitespace), `"ALPINE"`, `""` (empty) → `ValidationError`.
  - **`distro` happy-path coverage:** parametrize over all four admitted values `("alpine", "debian", "ubuntu", "rhel")` — each must construct without error. (A wrong `Literal` body would fail at least one row.)
  - **`name` / `version` empty + whitespace-only:** `name=""`, `name=" "`, `name="\t"`, `version=""`, `version=" "` → `ValidationError`. **Implementation hint:** `Field(min_length=1)` alone admits whitespace-only — use a `field_validator` enforcing `s.strip() == s and s != ""` (or equivalent), matching the rationale that downstream consumers index `DistroPackage` by `(distro, name, version)` and whitespace contamination poisons the index.
  - **Mutation post-construction:** `pkg.name = "x"` → `ValidationError` (`frozen=True`).
  - **`model_construct` does NOT appear in `types.py`:** linked to AC-14 fence — assert via AST walk that the call is absent. (A bypass via `DistroPackage.model_construct(name="", ...)` would skip validation; the fence forbids it in the production module.)
- [ ] **AC-8 — `AdapterConfidence` round-trip.** JSON round-trip pinned (`AdapterConfidence.HIGH.value == "high"` and `AdapterConfidence("high") == AdapterConfidence.HIGH`). Identity assertions: the three values are distinct (`HIGH is not DEGRADED is not UNAVAILABLE`).
- [ ] **AC-9 — Module imports are an exact set, not a subset.** `tests/unit/primitives/vuln_provenance/test_types_module_purity.py` AST-walks `types.py` and asserts the set of top-level imported module names equals exactly `{__future__, typing, enum, pydantic}` (no more, no less). No logging, no filesystem, no sibling-package imports, no `dataclasses`, no `pathlib`. The test exposes a module-level constant `_ALLOWED_TOP_LEVEL_IMPORTS: frozenset[str]` so future stories see one canonical place to amend (and any drift is a CI failure).
- [ ] **AC-10 — Gates.** `mypy --strict src/codegenie/primitives/vuln_provenance/` clean; `ruff check`, `ruff format --check` clean on touched files; `make lint-imports` green (no new contracts needed for this story — S1-06 lands them, but the new `primitives/` package must already be a legitimate import target); `make check` passes end-to-end on the touched scope.
- [ ] **AC-11 — `_Frozen` inheritance fence (AST-walk).** `tests/fence/test_vuln_provenance_frozen_base.py` walks every `class X(BaseModel)` definition under `src/codegenie/primitives/vuln_provenance/` (today: `DistroPackage`; tomorrow: all S1-03 variants + S1-05 `SyftSbom`) and asserts the base list contains `_Frozen` (or transitively inherits via a `_Frozen`-derived base). This locks the new convention: **no Phase 7 primitive may bypass `_Frozen` via inline `ConfigDict(frozen=True, extra="forbid")` shortcuts.** Phase 3's `transforms/outcomes.py` inline-config style is grandfathered (it predates `_Frozen`); the fence scope is `primitives/vuln_provenance/` only.
- [ ] **AC-12 — `DistroPackage` JSON round-trip.** `pkg = DistroPackage(name="openssl", version="3.0.7", distro="alpine"); s = pkg.model_dump_json(); back = DistroPackage.model_validate_json(s); assert back == pkg` for every admitted `distro` value. Also: `json.loads(s)` returns a dict with exactly the three keys `{"name", "version", "distro"}` (no extras, no `_kind` markers, no Pydantic internals). Pins serialization shape before S1-03 nests `DistroPackage` inside `BaseImage` (which then nests inside `Both` and `Provenance` and serializes into the event log — drift here is silent and downstream).
- [ ] **AC-13 — `__all__` sortedness + exactness.** `src/codegenie/primitives/vuln_provenance/types.py` exports `__all__ = ["AdapterConfidence", "DistroPackage", "UnknownReason"]` (sorted, exact, **omitting `_Frozen`** — underscore-prefixed names are package-internal and not part of the public API surface); `src/codegenie/primitives/vuln_provenance/__init__.py` re-exports the same three (sorted, exact). A unit test pins both `__all__` tuples (matches the S1-01 convention; see `src/codegenie/types/identifiers.py.__all__` is sorted + exact + asserted). The fence (AC-11) still locates `_Frozen` via direct module attribute access, so excluding it from `__all__` does not impair the inheritance check.
- [ ] **AC-14 — `model_construct` bypass fence.** `tests/fence/test_vuln_provenance_no_model_construct.py` AST-walks every `.py` file under `src/codegenie/primitives/vuln_provenance/` and asserts no `Call` node with `attr == "model_construct"` exists. (A bypass via `DistroPackage.model_construct(name="", version="", distro="centos")` would skip validation and admit illegal states — Phase 7 ADR-0004 §Consequences names this fence verbatim.)
- [ ] **AC-15 — mypy-strict negative test.** `tests/unit/primitives/vuln_provenance/test_types_mypy_negative.py` (or an equivalent `reveal_type` / `# type: ignore[arg-type]` strategy mirroring `tests/unit/types/test_identifiers_phase7_mypy_negative.py` from S1-01) asserts that:
  - `DistroPackage(distro="centos", name="x", version="1")` is a `mypy --strict` error (`Literal` mismatch);
  - Passing a raw `str` (`"high"`) where `AdapterConfidence` is annotated is a `mypy --strict` error;
  - Returning a non-`UnknownReason` `str` from a function annotated `-> UnknownReason` is a `mypy --strict` error.
  Without this, the runtime tests pass but the type system gives nothing — Rule 9 (tests verify intent).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline

1. Create `src/codegenie/primitives/__init__.py` (empty — the bounded-primitive home per ADR-0004; this story is the first to populate it).
2. Create `src/codegenie/primitives/vuln_provenance/__init__.py` re-exporting exactly `["AdapterConfidence", "DistroPackage", "UnknownReason"]` (sorted, exact). **No `AppKind` / `BaseKind`** — S1-03 will additively grow the re-export list when it lands the variants.
3. Create `src/codegenie/primitives/vuln_provenance/types.py`:
   - `_Frozen` base (`class _Frozen(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")`).
   - `class AdapterConfidence(str, Enum)` with three values.
   - `UnknownReason = Literal[...]` six values.
   - `class DistroPackage(_Frozen)` three fields with `field_validator`-enforced non-blank `name` / `version` (whitespace-only rejected).
   - `__all__ = ["AdapterConfidence", "DistroPackage", "UnknownReason"]` (sorted, exact — `_Frozen` is package-internal).
   - **No `AppKind` / `BaseKind`, no TYPE_CHECKING placeholders, no `# TODO(S1-03)` sentinels for those names.** S1-03 will add the variant classes + aliases as one additive landing.
4. Land tests (red-first; see TDD plan):
   - `tests/unit/primitives/vuln_provenance/test_types_phase7.py` (ACs 2/3/4/6/7/8/12).
   - `tests/unit/primitives/vuln_provenance/test_types_module_purity.py` (AC-9).
   - `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` (AC-13).
   - `tests/unit/primitives/vuln_provenance/test_types_mypy_negative.py` (AC-15).
   - `tests/fence/test_vuln_provenance_frozen_base.py` (AC-11).
   - `tests/fence/test_vuln_provenance_no_model_construct.py` (AC-14).
5. Run `mypy --strict src/` + `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/primitives/vuln_provenance/test_types_phase7.py`

```python
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from typing import assert_never, get_args

from codegenie.primitives.vuln_provenance.types import (
    AdapterConfidence,
    DistroPackage,
    UnknownReason,
)


# --- DistroPackage happy path (AC-2 + AC-7 — all four distro values) --------

ADMITTED_DISTROS = ("alpine", "debian", "ubuntu", "rhel")


@pytest.mark.parametrize("distro", ADMITTED_DISTROS)
def test_distro_package_happy_path(distro):
    pkg = DistroPackage(name="openssl", version="3.0.7", distro=distro)
    assert pkg.name == "openssl"
    assert pkg.version == "3.0.7"
    assert pkg.distro == distro


def test_distro_package_frozen():
    pkg = DistroPackage(name="openssl", version="3.0.7", distro="alpine")
    with pytest.raises(ValidationError):
        pkg.name = "evil"  # type: ignore[misc]


def test_distro_package_extra_forbid():
    with pytest.raises(ValidationError):
        DistroPackage(name="x", version="1", distro="alpine", extra_field="leak")  # type: ignore[call-arg]


# AC-7 rejection matrix — every contamination an executor could plausibly admit.
@pytest.mark.parametrize(
    "kwargs",
    [
        # --- distro Literal violations ---
        {"name": "x", "version": "1", "distro": "centos"},      # not in Literal
        {"name": "x", "version": "1", "distro": "Alpine"},      # case mismatch
        {"name": "x", "version": "1", "distro": "ALPINE"},      # case mismatch
        {"name": "x", "version": "1", "distro": " alpine"},     # leading whitespace
        {"name": "x", "version": "1", "distro": "alpine "},     # trailing whitespace
        {"name": "x", "version": "1", "distro": ""},            # empty distro
        # --- name empty / blank ---
        {"name": "",   "version": "1", "distro": "alpine"},
        {"name": " ",  "version": "1", "distro": "alpine"},
        {"name": "\t", "version": "1", "distro": "alpine"},
        # --- version empty / blank ---
        {"name": "x", "version": "",   "distro": "alpine"},
        {"name": "x", "version": " ",  "distro": "alpine"},
    ],
)
def test_distro_package_rejects(kwargs):
    with pytest.raises(ValidationError):
        DistroPackage(**kwargs)


# AC-12 — JSON round-trip for every admitted distro.
@pytest.mark.parametrize("distro", ADMITTED_DISTROS)
def test_distro_package_json_round_trip(distro):
    pkg = DistroPackage(name="openssl", version="3.0.7", distro=distro)
    s = pkg.model_dump_json()
    back = DistroPackage.model_validate_json(s)
    assert back == pkg
    payload = json.loads(s)
    assert set(payload.keys()) == {"name", "version", "distro"}
    assert payload["distro"] == distro


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


def test_adapter_confidence_membership_exact():
    # Adding a fourth member without updating the test is a CI failure.
    assert {c.value for c in AdapterConfidence} == {"high", "degraded", "unavailable"}


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


# --- Exhaustiveness anchor (AC-6) — colocated in this file, not a separate ---
# file. The arch (phase-arch-design.md §Edge cases rows 1+4+13) maps each reason
# to a concrete edge case; `assert_never` makes the type system the source of
# truth for "have we handled every reason?".

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

State why it fails: `ImportError` — `codegenie.primitives.vuln_provenance.types` and the three supporting types (`AdapterConfidence`, `DistroPackage`, `UnknownReason`) do not exist; `_Frozen` base does not exist; the `__init__.py` re-export list is missing.

### Green — make it pass
- Create `src/codegenie/primitives/__init__.py` (empty).
- Create `src/codegenie/primitives/vuln_provenance/__init__.py` re-exporting exactly `["AdapterConfidence", "DistroPackage", "UnknownReason"]` (sorted, exact).
- Create `src/codegenie/primitives/vuln_provenance/types.py` with `_Frozen`, `AdapterConfidence`, `UnknownReason`, `DistroPackage`. **No `AppKind` / `BaseKind`.**
- Land the four fence / purity / mypy-negative tests (AC-9, AC-11, AC-13, AC-14, AC-15) so subsequent stories inherit a locked convention from day one.

### Refactor — clean up
- One-line docstring on each top-level name naming the ADR it instantiates (ADR-0004 + production ADR-0038).
- Confirm `__all__` is sorted and exact, both in `types.py` and `__init__.py` (AC-13 fails otherwise).
- Confirm the module's top-level imports equal exactly `{__future__, typing, enum, pydantic}` — the module-purity fence in AC-9 catches drift.
- Verify no `model_construct(` calls (AC-14 fence covers this).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/primitives/__init__.py` | NEW — empty package init for the ADR-0004 home. |
| `src/codegenie/primitives/vuln_provenance/__init__.py` | NEW — re-export exactly `["AdapterConfidence", "DistroPackage", "UnknownReason"]` (sorted). **No `AppKind` / `BaseKind`.** |
| `src/codegenie/primitives/vuln_provenance/types.py` | NEW — `_Frozen`, `AdapterConfidence`, `UnknownReason`, `DistroPackage`. **No `AppKind` / `BaseKind`** (S1-03 lands them). |
| `tests/unit/primitives/__init__.py` + `tests/unit/primitives/vuln_provenance/__init__.py` | NEW — test package inits. |
| `tests/unit/primitives/vuln_provenance/test_types_phase7.py` | NEW — anchors TDD red; covers DistroPackage / AdapterConfidence / UnknownReason + JSON round-trip + exhaustiveness. |
| `tests/unit/primitives/vuln_provenance/test_types_module_purity.py` | NEW — module-purity fence on `types.py` imports (AC-9). |
| `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` | NEW — `__all__` sortedness + exactness (AC-13). |
| `tests/unit/primitives/vuln_provenance/test_types_mypy_negative.py` | NEW — mypy-strict negative cases (AC-15). |
| `tests/fence/test_vuln_provenance_frozen_base.py` | NEW — AST-walk `_Frozen` inheritance fence over `src/codegenie/primitives/vuln_provenance/` (AC-11). |
| `tests/fence/test_vuln_provenance_no_model_construct.py` | NEW — AST-walk forbids `model_construct` calls under `src/codegenie/primitives/vuln_provenance/` (AC-14). |

## Out of scope

- **The seven-variant `Provenance` union AND the `AppKind` / `BaseKind` discriminated-union aliases** — both landed by S1-03 in one atomic file. This story explicitly does NOT pre-place `AppKind` / `BaseKind` (validator finding CO2 — TYPE_CHECKING-guarded forward placeholders are a runtime `ImportError` waiting to happen, and string sentinels widen the type surface to `str` which the next story would have to undo).
- **`VulnProvenanceAdapter` Protocol** — landed by S1-04.
- **`SyftSbom` reader** — landed by S1-05.
- **Phase 7 LLM-SDK / no-`Any` import-linter contracts** — landed by S1-06.
- **`Layer` / `Ecosystem` enums** — landed by S2-01 (those are registry-side; this story is types-side).
- **Newtypes for `DistroPackage.name` / `.version`** — deliberately not landed; the arch keeps them as `str` (ADR-0033 admits raw `str` for non-identifier fields).
- **Smart constructor `make_distro_package(...) -> Result[DistroPackage, ParseError]`** — Pydantic's `model_validate` already returns the equivalent failure via `ValidationError`, and `DistroPackage` is a value record (not an identifier). Per Rule 2, the additional wrapping is premature; if a later story discovers a real consumer that wants `Result`-style adapter-error plumbing, that's the time to add it.
- **Grandfathering `transforms/outcomes.py` to `_Frozen`** — Phase 3 ships inline `model_config = ConfigDict(frozen=True, extra="forbid")` lines and AC-11's fence scope is `primitives/vuln_provenance/` only. Backporting `_Frozen` to Phase 3 is a separate cleanup story (Rule 3).

## Notes for the implementer

- **The arch is verbatim.** Every value of `AdapterConfidence` and every reason in `UnknownReason` appears in `phase-arch-design.md §Data model` as the contract Phase 7 ships. Do not "improve" the names or add a seventh `UnknownReason` value — admitting a new reason is an ADR-0004 amendment, not a story tweak.
- **`AppKind` / `BaseKind` are S1-03's job, not yours.** The validator removed the original "TYPE_CHECKING placeholder" pattern because at runtime `TYPE_CHECKING is False`, the names would be undefined, and any `from codegenie.primitives.vuln_provenance import AppKind` (which the `__init__.py` re-export per ADR-0004 §Consequences would attempt) would raise `ImportError`. The cleaner architectural choice — and what S1-03 will execute — is to land the variants AND the aliases atomically in `types.py` (one PR, one diff, one set of tests). **Do NOT pre-place `AppKind` / `BaseKind` as `Any`, `str`, `TypeAlias = "AppKind"`, or any other sentinel.** If S1-03's executor needs them earlier than expected, the right answer is to merge S1-03 first, not to leave behind a sentinel.
- **`UnknownReason` is a `Literal`, not an `Enum`.** The arch made this choice deliberately: Pydantic discriminated unions discriminate on `Literal` values, and `Unknown.reason: UnknownReason` is a value inside the `Provenance` discriminated union (not the discriminator itself, but a field whose contents must round-trip in JSON). Using `str` `Enum` here would force `.value` lookups everywhere. Source-of-truth for the set: `typing.get_args(UnknownReason)` — do NOT introduce a parallel `_UNKNOWN_REASONS: frozenset[str]` constant; consumers iterate `get_args(...)`. (Open/Closed: extending requires one edit in `types.py`; no auxiliary catalog to keep in sync.)
- **`DistroPackage.distro` is a `Literal`, not an `Enum`, for the same reason** — it appears as a field inside `BaseImage`, which appears inside `Provenance`'s discriminated union. Round-tripping the JSON shape is the goal; AC-12 pins it.
- **`_Frozen` is introduced by Phase 7 — not Phase 3.** A prior draft of this story claimed Phase 3 already shipped `_Frozen`; that was incorrect. `transforms/outcomes.py` uses repeated inline `model_config = ConfigDict(frozen=True, extra="forbid")` lines. This story introduces the `_Frozen` base for `primitives/vuln_provenance/` and locks the convention via the AST-walk fence (AC-11). Backporting `_Frozen` to Phase 3 is out of scope.
- **`field_validator` enforces non-blank `name` / `version`.** `Field(min_length=1)` alone admits whitespace-only strings. Use a `field_validator("name", "version")` that rejects `s` if `s.strip() != s or s == ""`. Downstream consumers will index `DistroPackage` by `(distro, name, version)`; whitespace contamination silently fragments that index.
- **`Field(strip_whitespace=...)` is NOT enabled.** Validation must reject — not silently fix — contaminated input. Auto-stripping would mask SBOM tampering (per phase-arch-design §Edge cases row 1).
- **No identifiers regenerated.** `DistroPackage.name` is a `str`, not a `PackageId` — the arch is explicit. `PackageId` is a *resolution coordinate* (`<name>@<version>`); `DistroPackage` is a *package-database row* (separate name + separate version + separate distro). Conflating them would force every adapter to fabricate a synthetic `@`-joined string.
- **`make lint-imports` may need an additive line.** The primitive's new home (`src/codegenie/primitives/vuln_provenance/`) is now an importable target. If the existing `import-linter` contracts have a "no new top-level packages" rule, surface it — but per ADR-0004, `primitives/` is the named additive home, so this should already be admitted. Verify before landing.
- **Design-pattern observations (for context, not new ACs):**
  - **Tagged union / sum type.** `UnknownReason` (Literal) + `AdapterConfidence` (Enum) split is principled: Literals serialize as their value with no `.value` indirection (load-bearing inside discriminated unions); Enums give a typed handle to a closed set (`AdapterConfidence.HIGH` reads cleaner than `"high"` at call sites).
  - **Make illegal states unrepresentable.** `extra="forbid"` + `frozen=True` + `Literal` discriminators close every door a defensive reader would otherwise have to check. The `_Frozen` fence (AC-11) means the convention can't drift inside this primitive.
  - **Smart constructor (deferred).** Pydantic's `model_validate` IS the smart constructor here — it returns `ValidationError` on bad input. Wrapping it in `Result[T, ParseError]` is premature (Rule 2) until a real consumer demonstrates the need.
  - **Open/Closed at the data-shape boundary.** Adding a seventh `UnknownReason` value is a one-line edit in `types.py` + one new `case` in `_describe`; the `assert_never` arm makes the type system the gatekeeper. Adding a fifth `distro` is the same shape. No registry, no factory, no plugin scaffold needed at this level.
