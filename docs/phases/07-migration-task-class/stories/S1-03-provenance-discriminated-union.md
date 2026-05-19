# Story S1-03 — Seven-variant `Provenance` discriminated union + nested `Both` guard

**Step:** Step 1 — Scaffold `vuln.provenance` primitive — newtypes, Provenance union, Protocol, errors, SyftSbom reader, fences
**Status:** GREEN
**Effort:** M
**Depends on:** S1-01, S1-02
**ADRs honored:** ADR-0004 (the primitive's home — the union lands at `src/codegenie/primitives/vuln_provenance/types.py`), ADR-0006 (consumers of `Provenance` must `match`/`assert_never` — this story makes that exhaustiveness possible), production ADR-0033 (sum types + frozen + extra="forbid"), production ADR-0038 (the verbatim seven-variant contract this story implements)

## Validation notes (2026-05-19, `phase-story-validator` pass)

**Verdict:** HARDENED. Real but fixable weaknesses across all four critic lenses; edits applied. Full report at [`_validation/S1-03-provenance-discriminated-union.md`](_validation/S1-03-provenance-discriminated-union.md).

Edits applied:
- **AC-1** — added explicit `BaseImage.stage` happy-path coverage requirement (both `None` and `DockerStageName(...)` cases).
- **AC-4** — enumerated all six structural-rejection cases for `Both.app_record` / `Both.base_record` (was three); surfaced the dual-layer invariant (mypy --strict + Pydantic runtime).
- **AC-5** — strengthened from single-instance to explicit per-variant parametrize over all seven.
- **AC-7** — expanded round-trip coverage from 3 of 7 variants to all seven (incl. `Both` nested-discriminator routing and `Unknown`); added JSON-string round-trip via `TypeAdapter.dump_json` / `validate_json`.
- **AC-8** — added empty-tuple `chain=()` invalid case alongside the length-1 case.
- **AC-10** — restricted scope statement: this story lands the union surface only; protocols / registry / assembly arrive in S1-04 / S2-01 / S2-04.
- **AC-11** — widened gate to project-wide `make check` (was `mypy --strict src/codegenie/primitives/vuln_provenance/` only).
- **AC-12 NEW** — `Unknown.details: dict[str, str]` rejects non-str values at construction (no-`Any` runtime pin complementing the S1-06 static fence).
- **AC-13 NEW** — discriminator-routing integrity: payload with `kind` value mismatched to fields rejects at deserialization.
- **AC-14 NEW** — mypy-negative test at `test_provenance_mypy_negative.py` mirrors the S1-01 precedent; pins the static-typing layer of the recursion guard.
- **Implementer notes** — added the closed-boundary statement (no `@register_provenance_variant`), the Make-Illegal-States-Unrepresentable lineage, the forward-reference ordering rationale, the `outcomes.py` `Annotated[..., Field(...)]` precedent, the `_Frozen` + `model_construct` fence cross-references, the Rule-9 docstring-encodes-WHY note, and the explicit ban on defensive `@field_validator` checks on `Both.app_record` / `Both.base_record`.

## Context

The seven-variant `Provenance` discriminated union is the load-bearing contract everything else in Phase 7 hangs on: every adapter returns it; `assemble_provenance` composes it; the `Both` variant's emission is the headline "Phase 7 produces evidence, not coordination" exit-criterion. The non-obvious correctness pin is the `Both` recursion guard: `Both.app_record: AppKind` and `Both.base_record: BaseKind` must be themselves discriminated unions **over non-`Both`, non-`Unknown` variants only**, so `Both(Both(...), ...)` raises `ValidationError` at construction time, not at some downstream `match` arm. The arch is explicit: "the type system itself enforces the recursion guard, not a runtime check." This story implements that contract verbatim and pins the recursion-rejection invariant with a parametrized red test.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §2` — verbatim Pydantic shape for all seven variants; the `AppKind` / `BaseKind` discriminated-union aliases; the `Both` nested-union constraint.
  - `../phase-arch-design.md §Data model` — the contract block names every variant + the `Provenance` final alias.
  - `../phase-arch-design.md §Design patterns applied` row 1 — "Tagged union with discriminator (ADR-0033 + ADR-0038); make illegal states unrepresentable; nested `Both` rejects `Both(Both, ...)` at validation time."
  - `../phase-arch-design.md §Edge cases` row 4 — the `Both` variant fires when CVE present in both layers; this story's union enables that downstream emission (S11-01+S11-02).
  - `../phase-arch-design.md §Control flow` — the `match (app_result, base_result)` in `assemble_provenance` (S2-04) depends on this story's `AppKind` / `BaseKind` aliases.
- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — names every variant the primitive's `__init__.py` re-exports.
  - `../ADRs/0006-adapter-dispatch-explicit-final-tuple.md` — `assemble_provenance` does `match (app, base)` on this story's `AppKind` / `BaseKind`; without the nested-union shape, the `match` arms would be open.
  - `../ADRs/0017-both-provenance-exits-code-8-with-coordination-summary.md` — the `Both` shape this story ships is what S11-01 / S11-02 emit.
- **Production ADRs:**
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — the seven-variant contract; this story is its Phase 7 implementation.
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — `frozen=True, extra="forbid"`; no half-valid states.
- **Source design:**
  - `../final-design.md §Synthesis ledger` row "Provenance seven-variant union + nested Both"; row "Both recursion guard at validation time, not runtime."
- **Existing code:**
  - `src/codegenie/transforms/outcomes.py` — Phase 3's `TransformOutcome` discriminated union with `Field(discriminator="kind")` + `_Frozen` base. Mirror the style verbatim.
  - `src/codegenie/primitives/vuln_provenance/types.py` (from S1-02) — `_Frozen`, `AdapterConfidence`, `UnknownReason`, `DistroPackage` already exist; the `AppKind` / `BaseKind` forward placeholders this story replaces with real values.
  - `src/codegenie/types/identifiers.py` (from S1-01) — `ImageDigest`, `LayerDigest`, `RuntimeId`, `DockerStageName`, `CveId`, `PackageId`.
- **External docs:**
  - Pydantic v2 docs §"Discriminated Unions" — `Annotated[Union[...], Field(discriminator="kind")]` is the idiom; nested discriminated unions are supported and produce the recursion-rejection behavior this story relies on.

## Goal

Implement the verbatim seven-variant `Provenance` discriminated union from `phase-arch-design.md §Component design §2` — `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`, `Unknown` — under `src/codegenie/primitives/vuln_provenance/types.py`, with every variant `frozen=True, extra="forbid"`, `kind` discriminator pinned per variant, `AppKind` / `BaseKind` as nested discriminated unions over non-`Both`/non-`Unknown` variants, and a parametrized red test asserting `Both(Both(...), ...)` raises `ValidationError`.

## Acceptance criteria

- [ ] **AC-1 — Seven variants, verbatim.** `src/codegenie/primitives/vuln_provenance/types.py` carries the seven variants exactly as `phase-arch-design.md §Component design §2` shows:
  - `class AppDirect(_Frozen)`: `kind: Literal["app_direct"] = "app_direct"`, `manifest_path: Path`, `package: PackageId`, `confidence: AdapterConfidence`.
  - `class AppTransitive(_Frozen)`: `kind: Literal["app_transitive"]`, `manifest_path: Path`, `package: PackageId`, `chain: tuple[PackageId, ...]` (length ≥ 2 enforced via Pydantic `Field(min_length=2)`), `confidence: AdapterConfidence`.
  - `class AppVendored(_Frozen)`: `kind: Literal["app_vendored"]`, `vendored_path: Path`, `package: PackageId`, `confidence: AdapterConfidence`.
  - `class BaseImage(_Frozen)`: `kind: Literal["base_image"]`, `image_digest: ImageDigest`, `layer_digest: LayerDigest`, `distro_pkg: DistroPackage`, `stage: DockerStageName | None`, `confidence: AdapterConfidence`. **Happy-path coverage MUST exercise both `stage=None` (single-stage Dockerfile) and `stage=DockerStageName("builder")` (multi-stage) — both shapes round-trip through the discriminated union.**
  - `class RuntimeBundled(_Frozen)`: `kind: Literal["runtime_bundled"]`, `runtime: RuntimeId`, `bundled_path: Path`, `package: PackageId`, `confidence: AdapterConfidence`.
  - `class Both(_Frozen)`: `kind: Literal["both"]`, `app_record: AppKind`, `base_record: BaseKind`. (No `confidence` field — the nested records carry their own.)
  - `class Unknown(_Frozen)`: `kind: Literal["unknown"]`, `reason: UnknownReason`, `details: dict[str, str] | None = None`.
- [ ] **AC-2 — `AppKind` / `BaseKind` are nested discriminated unions.**
  ```python
  AppKind = Annotated[Union[AppDirect, AppTransitive, AppVendored], Field(discriminator="kind")]
  BaseKind = Annotated[Union[BaseImage, RuntimeBundled], Field(discriminator="kind")]
  ```
  Both aliases are exported from `types.py` and re-exported from `vuln_provenance/__init__.py`.
- [ ] **AC-3 — `Provenance` final alias.**
  ```python
  Provenance = Annotated[
      Union[AppDirect, AppTransitive, AppVendored, BaseImage, RuntimeBundled, Both, Unknown],
      Field(discriminator="kind"),
  ]
  ```
  Round-trip via Pydantic `TypeAdapter(Provenance).validate_python(...)` works for every variant.
- [ ] **AC-4 — `Both` recursion guard rejects every structurally-invalid shape (dual layer: mypy + Pydantic).** The load-bearing invariant. Two independent safety layers must hold simultaneously: (a) **mypy --strict** rejects each invalid construction at type-check time (the `# type: ignore[arg-type]` markers below pin this), and (b) **Pydantic v2** raises `ValidationError` at runtime via discriminated-union routing on `AppKind` / `BaseKind`. Both layers MUST be present — a loosened type annotation (e.g., `Both.app_record: AppKind | Both`) would silently pass the runtime test, so AC-15 pins the static layer separately. Six structural-rejection cases (all six MUST be parametrized tests, not just three):
  ```python
  inner_both = Both(app_record=app_direct, base_record=base_image)
  # (1) Both nested inside Both.app_record
  with pytest.raises(ValidationError):
      Both(app_record=inner_both, base_record=base_image)         # type: ignore[arg-type]
  # (2) Both nested inside Both.base_record
  with pytest.raises(ValidationError):
      Both(app_record=app_direct, base_record=inner_both)         # type: ignore[arg-type]
  # (3) Unknown in app_record — AppKind excludes Unknown
  with pytest.raises(ValidationError):
      Both(app_record=Unknown(reason="no_adapter_resolved"),
           base_record=base_image)                                # type: ignore[arg-type]
  # (4) Unknown in base_record — BaseKind excludes Unknown
  with pytest.raises(ValidationError):
      Both(app_record=app_direct,
           base_record=Unknown(reason="no_adapter_resolved"))     # type: ignore[arg-type]
  # (5) BaseImage in app_record — AppKind excludes base-layer variants
  with pytest.raises(ValidationError):
      Both(app_record=base_image, base_record=base_image)         # type: ignore[arg-type]
  # (6) AppDirect in base_record — BaseKind excludes app-layer variants
  with pytest.raises(ValidationError):
      Both(app_record=app_direct, base_record=app_direct)         # type: ignore[arg-type]
  ```
- [ ] **AC-5 — `frozen=True` rejects post-construction mutation, every variant.** **Parametrize over all seven variants explicitly** (the TDD plan MUST land seven distinct test cases, one per variant, not just `test_app_direct_frozen` — a single-variant test would not catch a regression where one variant forgets to inherit `_Frozen`).
- [ ] **AC-6 — `extra="forbid"` rejects unknown fields, every variant.** Parametrized test over all seven variants: constructing with an extra kwarg raises `ValidationError`.
- [ ] **AC-7 — Round-trip via the outer discriminator, every variant (dict path AND JSON-string path).** Two parametrize sweeps, each over **all seven variants** (`app_direct`, `app_transitive`, `app_vendored`, `base_image`, `base_image_no_stage`, `runtime_bundled`, `both`, `unknown`):
  - **Dict path:** `TypeAdapter(Provenance).validate_python(p.model_dump()) == p`.
  - **JSON-string path:** `adapter.validate_json(adapter.dump_json(p)) == p` (catches `Path` ↔ `str`, `tuple` ↔ `list` coercion drift that the dict path can mask — the event log per ADR-0034 and `coordination-summary.yaml` writer per S11-02 serialize through this surface).
  - **`Both` round-trip specifically MUST be exercised** — the nested discriminated unions in `app_record` / `base_record` resolve their own `kind` independently of the outer alias; this is exactly where round-trip drift can hide.
- [ ] **AC-8 — `AppTransitive.chain` length ≥ 2.** Pydantic `Annotated[tuple[PackageId, ...], Field(min_length=2)]` (codebase precedent style, mirroring `transforms/outcomes.py`) enforces the architecture's "chain length 1 → `AppDirect`; chain length > 1 → `AppTransitive`" rule at the type level. Tests pin three boundary cases:
  - `chain=()` → `ValidationError` (empty tuple).
  - `chain=(pkg,)` → `ValidationError` (length 1).
  - `chain=(pkg, pkg2)` → ok (minimum valid length).
  - `chain=(pkg, pkg2, pkg3)` → ok (typical depth).
- [ ] **AC-9 — Exhaustiveness via `match` + `assert_never`.** `tests/unit/primitives/vuln_provenance/test_provenance_exhaustiveness.py`:
  ```python
  def _summarize(p: Provenance) -> str:
      match p:
          case AppDirect(): ...
          case AppTransitive(): ...
          case AppVendored(): ...
          case BaseImage(): ...
          case RuntimeBundled(): ...
          case Both(): ...
          case Unknown(): ...
          case _:
              assert_never(p)
      return ...
  ```
  Test runs `_summarize` over a happy-path instance of every variant; mypy --strict would catch a missing arm.
- [ ] **AC-10 — `vuln_provenance/__init__.py` re-exports the union surface this story lands (and only this).** The import `from codegenie.primitives.vuln_provenance import AppDirect, AppTransitive, AppVendored, BaseImage, RuntimeBundled, Both, Unknown, AppKind, BaseKind, Provenance, AdapterConfidence, UnknownReason, DistroPackage` succeeds. **Scope clarification:** S1-03 lands the **union surface only**. `VulnProvenanceAdapter` Protocol arrives in S1-04; `Layer`/`Ecosystem`/`register_provenance_adapter` arrive in S2-01; `assemble_provenance`/`_ADAPTER_DISPATCH_ORDER` arrive in S2-04. The `__all__` list MUST stay sorted (locked by `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py`, established by S1-02 AC-13).
- [ ] **AC-11 — Project-wide gate.** `make check` end-to-end clean: `ruff check`, `ruff format --check`, `mypy --strict src/` (all of `src/`, not just the subdir — catches cross-package drift), `make lint-imports`, full `pytest` suite green (Phase 0–6.5 regression). The narrow subdir-only `mypy --strict src/codegenie/primitives/vuln_provenance/` is INSUFFICIENT — mirror the S1-02 widening precedent (see `_validation/S1-02-provenance-enums-and-distro-package.md` CO4).
- [ ] **AC-12 — `Unknown.details: dict[str, str]` value-type runtime pin.** Constructing `Unknown(reason="adapter_error", details={"err": 42})` raises `ValidationError` (non-`str` value is rejected by Pydantic's runtime type-check of `dict[str, str]`). The no-`Any` static fence S1-06 catches the typing layer; this AC catches an executor who writes `details: dict` and relies on the fence. Parametrize: `{"k": 1}` (int value), `{"k": None}` (None value), `{"k": ["x"]}` (list value) — all reject.
- [ ] **AC-13 — Discriminator-routing integrity at deserialization.** A payload whose `kind` value mismatches its field shape MUST reject at `TypeAdapter(Provenance).validate_python(...)` — Pydantic v2's discriminator-routing fast path is what makes round-trip safe, and a future implementation that loosens the outer `Field(discriminator="kind")` could silently coerce one variant's payload into another's shape. Pin three cases: `{"kind": "app_direct", "image_digest": "sha256:..."}` rejects (no `BaseImage`-shape absorption); `{"kind": "unknown_variant"}` rejects (no fallback to first member); `{"kind": "both", "app_record": {...Both shape...}, ...}` rejects (the recursion guard at AC-4 must survive deserialization too).
- [ ] **AC-14 — mypy-negative test pins the static-typing layer of the recursion guard.** New file `tests/unit/primitives/vuln_provenance/test_provenance_mypy_negative.py` mirrors the S1-01 precedent at `tests/unit/types/test_identifiers_phase7_mypy_negative.py`. Three explicit `# type: ignore[arg-type]` assertions on the `Both(app_record=..., ...)` surface: (a) passing a `Both` instance, (b) passing an `Unknown` instance, (c) passing a `BaseImage` instance — each MUST be a mypy --strict error. Without this AC, a future implementation that widens `Both.app_record: AppKind | Both` would pass every runtime test while silently regressing the static guarantee that gives the recursion guard its "the type system itself enforces it" status.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline

1. Replace S1-02's `AppKind` / `BaseKind` `TYPE_CHECKING` placeholders in `types.py` with real `Annotated[Union[...], Field(discriminator="kind")]` aliases over the actual variants this story lands.
2. Declare the seven variant classes in this order (forward references aren't needed — the file is read top-to-bottom): `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, then `AppKind` / `BaseKind` aliases, then `Both` (which references the aliases), then `Unknown`.
3. Declare the final `Provenance` alias at the bottom.
4. Update `src/codegenie/primitives/vuln_provenance/__init__.py` to re-export all seven variant classes + `AppKind`, `BaseKind`, `Provenance`.
5. Land tests (red-first).
6. Run `mypy --strict` + `make check` + Phase 3 regression suite.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/primitives/vuln_provenance/test_provenance_union.py`

```python
from __future__ import annotations

from pathlib import Path
from typing import assert_never

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.types.identifiers import (
    ImageDigest,
    LayerDigest,
    PackageId,
    DockerStageName,
    RuntimeId,
)
from codegenie.primitives.vuln_provenance import (
    AdapterConfidence,
    AppDirect,
    AppKind,
    AppTransitive,
    AppVendored,
    BaseImage,
    BaseKind,
    Both,
    DistroPackage,
    Provenance,
    RuntimeBundled,
    Unknown,
)


# --- Construction happy paths (AC-1) -----------------------------------------

@pytest.fixture
def app_direct():
    return AppDirect(
        manifest_path=Path("package.json"),
        package=PackageId("lodash@4.17.21"),
        confidence=AdapterConfidence.HIGH,
    )


@pytest.fixture
def app_transitive():
    return AppTransitive(
        manifest_path=Path("package.json"),
        package=PackageId("nested@1.0.0"),
        chain=(PackageId("a@1.0.0"), PackageId("nested@1.0.0")),
        confidence=AdapterConfidence.HIGH,
    )


@pytest.fixture
def base_image():
    return BaseImage(
        image_digest=ImageDigest("sha256:" + "0" * 64),
        layer_digest=LayerDigest("sha256:" + "a" * 64),
        distro_pkg=DistroPackage(name="openssl", version="3.0.7", distro="alpine"),
        stage=DockerStageName("builder"),
        confidence=AdapterConfidence.HIGH,
    )


def test_app_direct_constructs(app_direct):
    assert app_direct.kind == "app_direct"


def test_app_transitive_chain_min_length(app_direct):
    with pytest.raises(ValidationError):
        AppTransitive(
            manifest_path=Path("package.json"),
            package=PackageId("a@1.0.0"),
            chain=(PackageId("a@1.0.0"),),  # length 1 → invalid
            confidence=AdapterConfidence.HIGH,
        )


# --- frozen + extra="forbid" (AC-5, AC-6) -----------------------------------

def test_app_direct_frozen(app_direct):
    with pytest.raises(ValidationError):
        app_direct.package = PackageId("evil@1.0.0")  # type: ignore[misc]


def test_app_direct_extra_forbidden(app_direct):
    with pytest.raises(ValidationError):
        AppDirect(
            manifest_path=Path("package.json"),
            package=PackageId("lodash@4.17.21"),
            confidence=AdapterConfidence.HIGH,
            extra="leak",  # type: ignore[call-arg]
        )


# --- Both recursion guard (AC-4 — the load-bearing test) ---------------------

def test_both_rejects_both_in_app_record(app_direct, base_image):
    inner = Both(app_record=app_direct, base_record=base_image)
    with pytest.raises(ValidationError):
        Both(app_record=inner, base_record=base_image)  # type: ignore[arg-type]


def test_both_rejects_both_in_base_record(app_direct, base_image):
    inner = Both(app_record=app_direct, base_record=base_image)
    with pytest.raises(ValidationError):
        Both(app_record=app_direct, base_record=inner)  # type: ignore[arg-type]


def test_both_rejects_unknown_in_app_record(base_image):
    unk = Unknown(reason="no_adapter_resolved")
    with pytest.raises(ValidationError):
        Both(app_record=unk, base_record=base_image)  # type: ignore[arg-type]


def test_both_rejects_unknown_in_base_record(app_direct):
    unk = Unknown(reason="no_adapter_resolved")
    with pytest.raises(ValidationError):
        Both(app_record=app_direct, base_record=unk)  # type: ignore[arg-type]


# --- JSON round-trip via TypeAdapter (AC-7) ---------------------------------

@pytest.mark.parametrize("variant_name", [
    "app_direct", "app_transitive", "base_image",
])
def test_provenance_round_trip(variant_name, app_direct, app_transitive, base_image):
    p = locals()[variant_name]
    adapter = TypeAdapter(Provenance)
    payload = p.model_dump()
    rebuilt = adapter.validate_python(payload)
    assert rebuilt == p


# --- Exhaustiveness via match + assert_never (AC-9) -------------------------

def _summarize(p: Provenance) -> str:
    match p:
        case AppDirect():
            return "app_direct"
        case AppTransitive():
            return "app_transitive"
        case AppVendored():
            return "app_vendored"
        case BaseImage():
            return "base_image"
        case RuntimeBundled():
            return "runtime_bundled"
        case Both():
            return "both"
        case Unknown():
            return "unknown"
        case _:
            assert_never(p)


def test_summarize_covers_every_variant(app_direct, app_transitive, base_image):
    assert _summarize(app_direct) == "app_direct"
    assert _summarize(app_transitive) == "app_transitive"
    assert _summarize(base_image) == "base_image"
    assert _summarize(Unknown(reason="adapter_error")) == "unknown"
```

State why it fails: `ImportError` — the seven variant classes + `Provenance`/`AppKind`/`BaseKind` aliases do not exist.

### Green — make it pass
- In `types.py`, replace S1-02's `AppKind` / `BaseKind` `TYPE_CHECKING` placeholders with the real `Annotated[Union[...], Field(discriminator="kind")]` aliases.
- Add the seven variant `class _Frozen` subclasses in the order described in the implementation outline.
- Update `vuln_provenance/__init__.py` to re-export the seven variant classes + `AppKind`, `BaseKind`, `Provenance`.

### Refactor — clean up
- Each variant carries a one-line docstring naming its semantic ("`AppDirect` — package appears as a direct dep in the manifest; resolved by `NpmVulnProvenanceAdapter` (S3-02).").
- Run the exhaustiveness test under `mypy --strict` to confirm a missing `match` arm is a type error (intentional regression test: temporarily comment out one arm, confirm mypy reports it, restore).
- Phase 3 regression suite green — the `Provenance` import path does not collide with any Phase 3 module.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/primitives/vuln_provenance/types.py` | Replace S1-02 placeholders with real `AppKind`/`BaseKind`; add the 7 variant classes + `Provenance` alias. |
| `src/codegenie/primitives/vuln_provenance/__init__.py` | Extend re-exports with the 7 variants + `AppKind`/`BaseKind`/`Provenance`. |
| `tests/unit/primitives/vuln_provenance/test_provenance_union.py` | NEW — anchors TDD red; covers AC-1..AC-8, AC-10, AC-12, AC-13. |
| `tests/unit/primitives/vuln_provenance/test_provenance_exhaustiveness.py` | NEW — `match`/`assert_never` over every variant (AC-9). |
| `tests/unit/primitives/vuln_provenance/test_provenance_mypy_negative.py` | NEW — mypy-negative pins of the recursion-guard static-typing layer (AC-14). Mirrors `tests/unit/types/test_identifiers_phase7_mypy_negative.py` precedent. |

## Out of scope

- **`VulnProvenanceAdapter` Protocol** — landed by S1-04 (consumes this story's `Provenance` as its `attribute` return type).
- **`SyftSbom` reader** — landed by S1-05.
- **Phase 7 LLM-SDK + no-`Any` fences** — landed by S1-06.
- **`assemble_provenance` free function** — landed by S2-04 (consumes this story's `AppKind` / `BaseKind` in its `match (app, base)`).
- **`@register_provenance_adapter` decorator** — landed by S2-01.
- **A `ProvenanceError` raising path inside the union** — variants do not raise; errors land in `Unknown(reason="adapter_error")` per the arch.

## Notes for the implementer

- **The `Both` recursion guard is the load-bearing piece.** The arch is explicit: "the type system itself enforces the recursion guard, not a runtime check." Pydantic v2's discriminated-union resolution does this automatically when `Both.app_record: AppKind` (and `AppKind` is `Union[AppDirect, AppTransitive, AppVendored]` — a discriminated union that does NOT include `Both` or `Unknown`). **Do NOT add a custom `@field_validator` or `model_validator` that does a kind check on `Both.app_record` / `Both.base_record` at runtime** — any defensive runtime check there is a code smell. It implies the structural type guarantee is uncertain, duplicates Pydantic's discriminated-union routing, and creates a maintenance burden the moment ADR-0038 amends the union (a future eighth variant would have to be added in two places: the type, AND the validator). The structural guarantee IS the guard.
- **Design-pattern lineage — Make-Illegal-States-Unrepresentable.** S1-02's validation surfaced this pattern as the umbrella over Phase 7's primitive surface (`_Frozen` base, `Literal` discriminators, `Enum` typed handles, AST-walk fences). S1-03 is the structural exemplar: nested discriminated unions make `Both(Both, ...)` not just-rejected-at-runtime but **literally unrepresentable** in the type system. Production ADR-0033 names this discipline; the recursion guard is its load-bearing application here.
- **The `Provenance` union is a closed contract, NOT an Open/Closed plugin seam.** Many surfaces in this codebase use registry-based extension (`@register_probe`, `@register_dep_graph_strategy`, `@register_provenance_adapter` arriving in S2-01). The `Provenance` variant set is intentionally NOT one of them — ADR-0038 fixes the seven variants by amendment, not by additive plugin. **Do NOT introduce a `@register_provenance_variant` decorator or any similar dispatch table for variants.** A future eighth variant arrives via ADR-0038 amendment + this file's edit + a story; that's the *intended* friction. Open/Closed lives one layer up (adapters), not at the data shape.
- **Pydantic v2 forward-reference order matters — file layout is deliberate, not stylistic.** The implementation outline orders declarations top-to-bottom as `AppDirect` → `AppTransitive` → `AppVendored` → `BaseImage` → `RuntimeBundled` → `AppKind` / `BaseKind` aliases → `Both` (references the aliases) → `Unknown` → `Provenance` final alias. **An executor who alphabetizes the file would break the build:** Pydantic v2 resolves discriminated-union member types at class-body evaluation time; if `Both` is declared before `AppKind` exists, the field annotation cannot resolve. Keep the declaration order as written.
- **`Annotated[..., Field(min_length=2)]` is the codebase idiom for `AppTransitive.chain`.** See `src/codegenie/transforms/outcomes.py` for the precedent style (`RecipeOutcome`, `Applicability`, etc. — every variant uses `Annotated[A | B | C, Field(discriminator="kind")]` umbrellas; field-level constraints use `Annotated[tuple[...], Field(min_length=N)]`). Do NOT reach for `Field(default=..., min_length=2)` — that's the deprecated v1-style form and would smell wrong against the rest of the codebase.
- **`_Frozen` inheritance fence + `model_construct` ban transitively apply to this story.** S1-02 planted two AST-walk fences scoped to `src/codegenie/primitives/vuln_provenance/`:
  - `tests/fence/test_vuln_provenance_frozen_base.py` — every `class X(BaseModel)` under the subpackage MUST inherit `_Frozen`. Forgetting `_Frozen` on any of the seven new variants (or on a future fixture-helper subclass) fails this fence.
  - `tests/fence/test_vuln_provenance_no_model_construct.py` — no `Model.model_construct(...)` call sites. **Do NOT use `model_construct()` in test fixtures or in the production code** — it bypasses validation, defeats AC-4's recursion guard at the fixture surface, and breaks the fence. Use the normal constructor: validation IS the test.
- **Tests verify intent, not just behavior (Rule 9).** Every test pinning a Pydantic constraint MUST carry a one-line docstring naming the arch rule it pins. Example: `test_app_transitive_chain_length_one_rejected` → `"""Chain length 1 collapses to AppDirect — arch §Component design §2. A future PR that admits length-1 here would silently mis-classify direct deps as transitive."""`. Without the WHY, a future executor "fixing" `min_length` to admit a corner case loses the historical reason.
- **Smart-constructor pattern (`make_provenance(...) -> Result[Provenance, ParseError]`) deliberately omitted.** Per Rule 2 (no abstractions for single-use code). Pydantic's `ValidationError` IS the equivalent failure signal — adapters return `Unknown(reason="adapter_error")` for "I don't apply", and raise `ProvenanceError` (S1-04) for genuine errors. Do NOT introduce a `Result`-wrapper "for consistency with S1-01's smart constructors" — the smart-constructor pattern in S1-01 protects against parsing raw strings into newtypes (a different problem).
- **`AppKind` excludes `Unknown`.** The arch is explicit: `Both` carries non-`Unknown` records. If the app layer resolved to `Unknown`, `assemble_provenance` (S2-04) takes the `(None, base)` or `(None, None)` arm instead — it never wraps an `Unknown` in `Both`. AC-4's `test_both_rejects_unknown_in_app_record` pins this.
- **`AppTransitive.chain` length ≥ 2 is the type-level shape of "transitive."** The arch's `NpmVulnProvenanceAdapter` rule ("chain length 1 → `AppDirect`; chain length > 1 → `AppTransitive`") only holds if the type system enforces ≥ 2. Use Pydantic's `Field(min_length=2)`. Without this, an adapter could mis-classify a direct dep as `AppTransitive(chain=(pkg,))`.
- **Use the existing `_Frozen` base from S1-02.** Do not redeclare `_Frozen`. Inheritance: every variant subclasses `_Frozen`, never `BaseModel` directly.
- **`Path` not `str`.** The `manifest_path`, `vendored_path`, `bundled_path` fields are `pathlib.Path`, per the arch §Component design §2 code block. Pydantic v2 handles the JSON serialization (`Path` ↔ `str`) automatically.
- **`stage: DockerStageName | None`.** The `BaseImage.stage` field is optional — a single-stage Dockerfile has no stage name. Default to `None`; do NOT add a `DockerStageName("")` sentinel.
- **`Unknown.details: dict[str, str] | None`.** The arch deliberately uses `dict[str, str]`, not `dict[str, Any]` — the no-`Any` fence S1-06 will plant catches the latter. Keep it `dict[str, str]`.
- **Round-trip via `TypeAdapter`, not via per-class `model_validate`.** The discriminator on the outer `Provenance` alias is what routes incoming JSON to the right variant; `TypeAdapter(Provenance).validate_python(payload)` exercises that wiring. AC-7 must use this idiom, not `AppDirect.model_validate(payload)` (which short-circuits the discriminator path).
- **Phase 0–6.5 regression suite stays green.** This story does not touch any pre-Phase-7 source file — verify via `make check` end-to-end (per the hardened AC-11). Per-phase narrow runs (`pytest tests/unit/transforms/ tests/unit/plugins/vulnerability_remediation_node_npm/ -q`) are useful for triage but not sufficient for the gate. If a test fails, the cause is typically Pydantic version drift, an `import-linter` contract that did not yet admit `codegenie.primitives.vuln_provenance`, or a coverage subset issue (see CLAUDE.md pytest config — narrow subsets need `--no-cov`). Surface either as a follow-up.
- **No `model_construct()` call sites.** ADR-0004's Consequences clause names a deferred fence: "a fence asserts no `model_construct()` call sites under `src/codegenie/primitives/vuln_provenance/`" (the smart-constructor bypass). This story does not land that fence — S1-06 does — but do not use `model_construct()` in this story's code either; it would force a same-PR fence edit.
