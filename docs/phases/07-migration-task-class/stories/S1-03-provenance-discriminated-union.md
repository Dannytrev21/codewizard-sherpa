# Story S1-03 — Seven-variant `Provenance` discriminated union + nested `Both` guard

**Step:** Step 1 — Scaffold `vuln.provenance` primitive — newtypes, Provenance union, Protocol, errors, SyftSbom reader, fences
**Status:** Ready
**Effort:** M
**Depends on:** S1-01, S1-02
**ADRs honored:** ADR-0004 (the primitive's home — the union lands at `src/codegenie/primitives/vuln_provenance/types.py`), ADR-0006 (consumers of `Provenance` must `match`/`assert_never` — this story makes that exhaustiveness possible), production ADR-0033 (sum types + frozen + extra="forbid"), production ADR-0038 (the verbatim seven-variant contract this story implements)

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
  - `class BaseImage(_Frozen)`: `kind: Literal["base_image"]`, `image_digest: ImageDigest`, `layer_digest: LayerDigest`, `distro_pkg: DistroPackage`, `stage: DockerStageName | None`, `confidence: AdapterConfidence`.
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
- [ ] **AC-4 — `Both(Both(...), ...)` rejected at construction.** The load-bearing recursion guard: a parametrized test attempts to construct `Both` with a `Both`-shaped `app_record` (or a `Both`-shaped `base_record`, or both) and asserts `ValidationError`. Variants:
  ```python
  inner_both = Both(app_record=app_direct, base_record=base_image)
  with pytest.raises(ValidationError):
      Both(app_record=inner_both, base_record=base_image)   # type: ignore[arg-type]
  with pytest.raises(ValidationError):
      Both(app_record=app_direct, base_record=inner_both)   # type: ignore[arg-type]
  with pytest.raises(ValidationError):
      Both(app_record=unknown_kind, base_record=base_image)  # Unknown not in AppKind
  ```
- [ ] **AC-5 — `frozen=True` rejects post-construction mutation.** Parametrized test over every variant: `with pytest.raises(ValidationError): variant.field = ...`.
- [ ] **AC-6 — `extra="forbid"` rejects unknown fields.** Parametrized test over every variant: constructing with an extra kwarg raises `ValidationError`.
- [ ] **AC-7 — JSON round-trip.** `TypeAdapter(Provenance).validate_python(provenance.model_dump()) == provenance` for at least one happy-path instance of each variant. Asserts the discriminator wiring picks the right variant on deserialization.
- [ ] **AC-8 — `AppTransitive.chain` length ≥ 2.** Pydantic `Field(min_length=2)` (or equivalent validator) enforces the architecture's "chain length > 1 → `AppTransitive`" rule at the type level. Test: `chain=(pkg,)` → `ValidationError`; `chain=(pkg, pkg2)` → ok.
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
- [ ] **AC-10 — `vuln_provenance/__init__.py` re-exports the full surface.** `from codegenie.primitives.vuln_provenance import AppDirect, AppTransitive, AppVendored, BaseImage, RuntimeBundled, Both, Unknown, AppKind, BaseKind, Provenance, AdapterConfidence, UnknownReason, DistroPackage` succeeds.
- [ ] **AC-11 — Gates.** `mypy --strict src/codegenie/primitives/vuln_provenance/` clean; `ruff check`, `ruff format --check` clean; `make lint-imports` green; existing Phase 0/1/2/3 + Phase 5/6.5 regression suite green.
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
| `tests/unit/primitives/vuln_provenance/test_provenance_union.py` | NEW — anchors TDD red; covers all 11 ACs above. |
| `tests/unit/primitives/vuln_provenance/test_provenance_exhaustiveness.py` | NEW — `match`/`assert_never` over every variant (AC-9). |

## Out of scope

- **`VulnProvenanceAdapter` Protocol** — landed by S1-04 (consumes this story's `Provenance` as its `attribute` return type).
- **`SyftSbom` reader** — landed by S1-05.
- **Phase 7 LLM-SDK + no-`Any` fences** — landed by S1-06.
- **`assemble_provenance` free function** — landed by S2-04 (consumes this story's `AppKind` / `BaseKind` in its `match (app, base)`).
- **`@register_provenance_adapter` decorator** — landed by S2-01.
- **A `ProvenanceError` raising path inside the union** — variants do not raise; errors land in `Unknown(reason="adapter_error")` per the arch.

## Notes for the implementer

- **The `Both` recursion guard is the load-bearing piece.** The arch is explicit: "the type system itself enforces the recursion guard, not a runtime check." Pydantic v2's discriminated-union resolution does this automatically when `Both.app_record: AppKind` (and `AppKind` is `Union[AppDirect, AppTransitive, AppVendored]` — a discriminated union that does NOT include `Both` or `Unknown`). Do NOT add a custom `@field_validator` that does the check at runtime — the validation-time rejection is what the test pins.
- **`AppKind` excludes `Unknown`.** The arch is explicit: `Both` carries non-`Unknown` records. If the app layer resolved to `Unknown`, `assemble_provenance` (S2-04) takes the `(None, base)` or `(None, None)` arm instead — it never wraps an `Unknown` in `Both`. AC-4's `test_both_rejects_unknown_in_app_record` pins this.
- **`AppTransitive.chain` length ≥ 2 is the type-level shape of "transitive."** The arch's `NpmVulnProvenanceAdapter` rule ("chain length 1 → `AppDirect`; chain length > 1 → `AppTransitive`") only holds if the type system enforces ≥ 2. Use Pydantic's `Field(min_length=2)`. Without this, an adapter could mis-classify a direct dep as `AppTransitive(chain=(pkg,))`.
- **Use the existing `_Frozen` base from S1-02.** Do not redeclare `_Frozen`. Inheritance: every variant subclasses `_Frozen`, never `BaseModel` directly.
- **`Path` not `str`.** The `manifest_path`, `vendored_path`, `bundled_path` fields are `pathlib.Path`, per the arch §Component design §2 code block. Pydantic v2 handles the JSON serialization (`Path` ↔ `str`) automatically.
- **`stage: DockerStageName | None`.** The `BaseImage.stage` field is optional — a single-stage Dockerfile has no stage name. Default to `None`; do NOT add a `DockerStageName("")` sentinel.
- **`Unknown.details: dict[str, str] | None`.** The arch deliberately uses `dict[str, str]`, not `dict[str, Any]` — the no-`Any` fence S1-06 will plant catches the latter. Keep it `dict[str, str]`.
- **Round-trip via `TypeAdapter`, not via per-class `model_validate`.** The discriminator on the outer `Provenance` alias is what routes incoming JSON to the right variant; `TypeAdapter(Provenance).validate_python(payload)` exercises that wiring. AC-7 must use this idiom, not `AppDirect.model_validate(payload)` (which short-circuits the discriminator path).
- **Phase 3 regression suite stays green.** This story does not touch any Phase 3 file — verify by running `pytest tests/unit/transforms/ tests/unit/plugins/vulnerability_remediation_node_npm/ -q` after green. If a test fails, the cause is a Pydantic version drift or an `import-linter` contract that did not yet admit `codegenie.primitives.vuln_provenance` — surface either as a follow-up.
- **No `model_construct()` call sites.** ADR-0004's Consequences clause names a deferred fence: "a fence asserts no `model_construct()` call sites under `src/codegenie/primitives/vuln_provenance/`" (the smart-constructor bypass). This story does not land that fence — S1-06 does — but do not use `model_construct()` in this story's code either; it would force a same-PR fence edit.
