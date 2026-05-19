"""Phase 7 S1-03 — seven-variant `Provenance` discriminated union.

Covers AC-1 through AC-8 + AC-10 of the story
`docs/phases/07-migration-task-class/stories/S1-03-provenance-discriminated-union.md`.
AC-9 (exhaustiveness via `match` + `assert_never`) is anchored in the
sibling `test_provenance_exhaustiveness.py`; AC-11 (mypy / ruff / lint
gates) runs at the `make check` level, not here.

ADRs honoured:
- Phase 7 ADR-0004 — primitive home (`primitives/vuln_provenance/`).
- Phase 7 ADR-0006 — `match`/`assert_never` discipline (this story
  guarantees the union shape that makes exhaustiveness checkable).
- production ADR-0033 — `frozen=True, extra="forbid"`.
- production ADR-0038 — verbatim seven-variant contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.primitives.vuln_provenance import (
    AdapterConfidence,
    AppDirect,
    AppTransitive,
    AppVendored,
    BaseImage,
    Both,
    DistroPackage,
    Provenance,
    RuntimeBundled,
    Unknown,
)
from codegenie.types.identifiers import (
    DockerStageName,
    ImageDigest,
    LayerDigest,
    PackageId,
    RuntimeId,
)

# ---------------------------------------------------------------------------
# Happy-path fixtures — one canonical instance per variant. Cross-arc reuse.
# ---------------------------------------------------------------------------


@pytest.fixture
def app_direct() -> AppDirect:
    return AppDirect(
        manifest_path=Path("package.json"),
        package=PackageId("lodash@4.17.21"),
        confidence=AdapterConfidence.HIGH,
    )


@pytest.fixture
def app_transitive() -> AppTransitive:
    return AppTransitive(
        manifest_path=Path("package.json"),
        package=PackageId("nested@1.0.0"),
        chain=(PackageId("a@1.0.0"), PackageId("nested@1.0.0")),
        confidence=AdapterConfidence.HIGH,
    )


@pytest.fixture
def app_vendored() -> AppVendored:
    return AppVendored(
        vendored_path=Path("vendor/some-lib"),
        package=PackageId("vendored@1.0.0"),
        confidence=AdapterConfidence.DEGRADED,
    )


@pytest.fixture
def base_image() -> BaseImage:
    return BaseImage(
        image_digest=ImageDigest("sha256:" + "0" * 64),
        layer_digest=LayerDigest("sha256:" + "a" * 64),
        distro_pkg=DistroPackage(name="openssl", version="3.0.7", distro="alpine"),
        stage=DockerStageName("builder"),
        confidence=AdapterConfidence.HIGH,
    )


@pytest.fixture
def base_image_no_stage() -> BaseImage:
    return BaseImage(
        image_digest=ImageDigest("sha256:" + "0" * 64),
        layer_digest=LayerDigest("sha256:" + "a" * 64),
        distro_pkg=DistroPackage(name="openssl", version="3.0.7", distro="alpine"),
        stage=None,
        confidence=AdapterConfidence.HIGH,
    )


@pytest.fixture
def runtime_bundled() -> RuntimeBundled:
    return RuntimeBundled(
        runtime=RuntimeId("node20"),
        bundled_path=Path("/usr/lib/node_modules/x"),
        package=PackageId("x@1.0.0"),
        confidence=AdapterConfidence.HIGH,
    )


@pytest.fixture
def unknown() -> Unknown:
    return Unknown(reason="no_adapter_resolved")


# ---------------------------------------------------------------------------
# AC-1 — verbatim variant shapes (kind + required fields).
# ---------------------------------------------------------------------------


def test_app_direct_kind_and_fields(app_direct: AppDirect) -> None:
    assert app_direct.kind == "app_direct"
    assert app_direct.manifest_path == Path("package.json")
    assert app_direct.package == "lodash@4.17.21"
    assert app_direct.confidence is AdapterConfidence.HIGH


def test_app_transitive_kind_and_chain(app_transitive: AppTransitive) -> None:
    assert app_transitive.kind == "app_transitive"
    assert len(app_transitive.chain) == 2
    # Tuple, not list — immutability invariant.
    assert isinstance(app_transitive.chain, tuple)


def test_app_vendored_kind(app_vendored: AppVendored) -> None:
    assert app_vendored.kind == "app_vendored"
    assert app_vendored.vendored_path == Path("vendor/some-lib")


def test_base_image_kind_and_optional_stage(
    base_image: BaseImage, base_image_no_stage: BaseImage
) -> None:
    assert base_image.kind == "base_image"
    assert base_image.stage == "builder"
    assert base_image_no_stage.stage is None


def test_runtime_bundled_kind(runtime_bundled: RuntimeBundled) -> None:
    assert runtime_bundled.kind == "runtime_bundled"
    assert runtime_bundled.runtime == "node20"


def test_both_kind_and_nested_records(app_direct: AppDirect, base_image: BaseImage) -> None:
    both = Both(app_record=app_direct, base_record=base_image)
    assert both.kind == "both"
    assert both.app_record == app_direct
    assert both.base_record == base_image


def test_unknown_kind_and_optional_details(unknown: Unknown) -> None:
    assert unknown.kind == "unknown"
    assert unknown.reason == "no_adapter_resolved"
    assert unknown.details is None


def test_unknown_accepts_details_dict_str_str() -> None:
    u = Unknown(reason="adapter_error", details={"npm-adapter": "lockfile missing"})
    assert u.details == {"npm-adapter": "lockfile missing"}


# ---------------------------------------------------------------------------
# AC-2 — AppKind / BaseKind aliases are importable + cover the right set.
# ---------------------------------------------------------------------------


def test_app_kind_and_base_kind_aliases_importable() -> None:
    """A static-typing alias is only useful if the import path is stable —
    every downstream `match` arm (S2-04 assemble_provenance) imports these
    by name. The smoke test pins the surface; the type-level content is
    checked by the AC-4 `Both` recursion-guard tests."""
    from codegenie.primitives.vuln_provenance import AppKind, BaseKind  # noqa: F401


# ---------------------------------------------------------------------------
# AC-3 / AC-7 — Provenance TypeAdapter round-trip with discriminator routing.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variant_fixture",
    [
        "app_direct",
        "app_transitive",
        "app_vendored",
        "base_image",
        "base_image_no_stage",
        "runtime_bundled",
        "unknown",
    ],
)
def test_provenance_round_trip_via_type_adapter(
    request: pytest.FixtureRequest, variant_fixture: str
) -> None:
    instance = request.getfixturevalue(variant_fixture)
    adapter = TypeAdapter(Provenance)
    payload = instance.model_dump()
    rebuilt = adapter.validate_python(payload)
    assert rebuilt == instance
    assert type(rebuilt) is type(instance)


def test_provenance_round_trip_both(app_direct: AppDirect, base_image: BaseImage) -> None:
    both = Both(app_record=app_direct, base_record=base_image)
    adapter = TypeAdapter(Provenance)
    rebuilt = adapter.validate_python(both.model_dump())
    assert rebuilt == both
    assert type(rebuilt) is Both


def test_provenance_round_trip_json_string(
    app_direct: AppDirect,
) -> None:
    """Discriminator-routed deserialization from a JSON string. The
    `model_dump_json` / `model_validate_json` round-trip catches
    serialization drift before the event log nests the payload."""
    adapter = TypeAdapter(Provenance)
    payload = adapter.dump_json(app_direct)
    rebuilt = adapter.validate_json(payload)
    assert rebuilt == app_direct


# ---------------------------------------------------------------------------
# AC-4 — `Both` recursion guard (the load-bearing test).
# ---------------------------------------------------------------------------


def test_both_rejects_both_in_app_record(app_direct: AppDirect, base_image: BaseImage) -> None:
    inner = Both(app_record=app_direct, base_record=base_image)
    with pytest.raises(ValidationError):
        Both(app_record=inner, base_record=base_image)  # type: ignore[arg-type]


def test_both_rejects_both_in_base_record(app_direct: AppDirect, base_image: BaseImage) -> None:
    inner = Both(app_record=app_direct, base_record=base_image)
    with pytest.raises(ValidationError):
        Both(app_record=app_direct, base_record=inner)  # type: ignore[arg-type]


def test_both_rejects_both_in_both_records(app_direct: AppDirect, base_image: BaseImage) -> None:
    inner = Both(app_record=app_direct, base_record=base_image)
    with pytest.raises(ValidationError):
        Both(app_record=inner, base_record=inner)  # type: ignore[arg-type]


def test_both_rejects_unknown_in_app_record(base_image: BaseImage) -> None:
    unk = Unknown(reason="no_adapter_resolved")
    with pytest.raises(ValidationError):
        Both(app_record=unk, base_record=base_image)  # type: ignore[arg-type]


def test_both_rejects_unknown_in_base_record(app_direct: AppDirect) -> None:
    unk = Unknown(reason="no_adapter_resolved")
    with pytest.raises(ValidationError):
        Both(app_record=app_direct, base_record=unk)  # type: ignore[arg-type]


def test_both_rejects_base_image_in_app_record(base_image: BaseImage) -> None:
    """`BaseImage.kind == "base_image"` is not in `AppKind` — the
    discriminator must route to `Both.app_record`'s `AppKind` and reject
    `BaseImage`. This catches a future regression where someone mistakenly
    widens `AppKind` to include base-tier variants."""
    with pytest.raises(ValidationError):
        Both(app_record=base_image, base_record=base_image)  # type: ignore[arg-type]


def test_both_rejects_app_direct_in_base_record(
    app_direct: AppDirect, base_image: BaseImage
) -> None:
    """Symmetric to the above — `AppDirect.kind == "app_direct"` is not in
    `BaseKind`."""
    with pytest.raises(ValidationError):
        Both(app_record=app_direct, base_record=app_direct)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC-5 — frozen=True (post-construction mutation rejected).
# ---------------------------------------------------------------------------


def test_app_direct_frozen(app_direct: AppDirect) -> None:
    with pytest.raises(ValidationError):
        app_direct.package = PackageId("evil@1.0.0")  # type: ignore[misc]


def test_app_transitive_frozen(app_transitive: AppTransitive) -> None:
    with pytest.raises(ValidationError):
        app_transitive.chain = ()  # type: ignore[misc]


def test_app_vendored_frozen(app_vendored: AppVendored) -> None:
    with pytest.raises(ValidationError):
        app_vendored.package = PackageId("evil@1.0.0")  # type: ignore[misc]


def test_base_image_frozen(base_image: BaseImage) -> None:
    with pytest.raises(ValidationError):
        base_image.stage = DockerStageName("evil")  # type: ignore[misc]


def test_runtime_bundled_frozen(runtime_bundled: RuntimeBundled) -> None:
    with pytest.raises(ValidationError):
        runtime_bundled.runtime = RuntimeId("evil")  # type: ignore[misc]


def test_both_frozen(app_direct: AppDirect, base_image: BaseImage) -> None:
    both = Both(app_record=app_direct, base_record=base_image)
    with pytest.raises(ValidationError):
        both.app_record = app_direct  # type: ignore[misc]


def test_unknown_frozen(unknown: Unknown) -> None:
    with pytest.raises(ValidationError):
        unknown.reason = "adapter_error"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AC-6 — extra="forbid" (unknown kwargs rejected).
# ---------------------------------------------------------------------------


def test_app_direct_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        AppDirect(
            manifest_path=Path("package.json"),
            package=PackageId("lodash@4.17.21"),
            confidence=AdapterConfidence.HIGH,
            extra="leak",  # type: ignore[call-arg]
        )


def test_app_transitive_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        AppTransitive(
            manifest_path=Path("package.json"),
            package=PackageId("nested@1.0.0"),
            chain=(PackageId("a@1.0.0"), PackageId("nested@1.0.0")),
            confidence=AdapterConfidence.HIGH,
            extra="leak",  # type: ignore[call-arg]
        )


def test_app_vendored_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        AppVendored(
            vendored_path=Path("vendor/x"),
            package=PackageId("x@1.0.0"),
            confidence=AdapterConfidence.HIGH,
            extra="leak",  # type: ignore[call-arg]
        )


def test_base_image_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        BaseImage(
            image_digest=ImageDigest("sha256:" + "0" * 64),
            layer_digest=LayerDigest("sha256:" + "a" * 64),
            distro_pkg=DistroPackage(name="x", version="1", distro="alpine"),
            stage=None,
            confidence=AdapterConfidence.HIGH,
            extra="leak",  # type: ignore[call-arg]
        )


def test_runtime_bundled_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        RuntimeBundled(
            runtime=RuntimeId("node20"),
            bundled_path=Path("/usr/lib/x"),
            package=PackageId("x@1.0.0"),
            confidence=AdapterConfidence.HIGH,
            extra="leak",  # type: ignore[call-arg]
        )


def test_both_extra_forbidden(app_direct: AppDirect, base_image: BaseImage) -> None:
    with pytest.raises(ValidationError):
        Both(
            app_record=app_direct,
            base_record=base_image,
            extra="leak",  # type: ignore[call-arg]
        )


def test_unknown_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        Unknown(reason="adapter_error", extra="leak")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# AC-8 — AppTransitive.chain length >= 2.
# ---------------------------------------------------------------------------


def test_app_transitive_chain_length_one_rejected() -> None:
    with pytest.raises(ValidationError):
        AppTransitive(
            manifest_path=Path("package.json"),
            package=PackageId("a@1.0.0"),
            chain=(PackageId("a@1.0.0"),),
            confidence=AdapterConfidence.HIGH,
        )


def test_app_transitive_chain_empty_rejected() -> None:
    with pytest.raises(ValidationError):
        AppTransitive(
            manifest_path=Path("package.json"),
            package=PackageId("a@1.0.0"),
            chain=(),
            confidence=AdapterConfidence.HIGH,
        )


def test_app_transitive_chain_length_two_ok() -> None:
    t = AppTransitive(
        manifest_path=Path("package.json"),
        package=PackageId("nested@1.0.0"),
        chain=(PackageId("a@1.0.0"), PackageId("nested@1.0.0")),
        confidence=AdapterConfidence.HIGH,
    )
    assert len(t.chain) == 2


def test_app_transitive_chain_length_three_ok() -> None:
    t = AppTransitive(
        manifest_path=Path("package.json"),
        package=PackageId("nested@1.0.0"),
        chain=(
            PackageId("root@1.0.0"),
            PackageId("a@1.0.0"),
            PackageId("nested@1.0.0"),
        ),
        confidence=AdapterConfidence.HIGH,
    )
    assert len(t.chain) == 3


# ---------------------------------------------------------------------------
# AC-10 — full re-export surface (every variant + alias importable from the
# package root, not just `types`). A successful import is the assertion.
# ---------------------------------------------------------------------------


def test_full_public_surface_importable_from_package() -> None:
    from codegenie.primitives.vuln_provenance import (  # noqa: F401
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
        UnknownReason,
    )


# ---------------------------------------------------------------------------
# AC-12 — Unknown.details: dict[str, str] runtime value-type pin.
#
# The static guarantee (no Any) lands with S1-06's no-`Any` fence; this AC
# pins the runtime layer: an executor who writes `details: dict` (without
# the `[str, str]` annotation) relying on the fence to catch them would
# still want a Pydantic-level rejection on non-`str` values at the field.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_details",
    [
        {"k": 1},  # int value
        {"k": None},  # None value
        {"k": ["x"]},  # list value
        {"k": {"nested": "dict"}},  # dict value
        {"k": True},  # bool (also int subclass)
    ],
    ids=["int_value", "none_value", "list_value", "dict_value", "bool_value"],
)
def test_unknown_details_rejects_non_str_values(bad_details: object) -> None:
    with pytest.raises(ValidationError):
        Unknown(reason="adapter_error", details=bad_details)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC-13 — Discriminator-routed deserialization integrity.
# ---------------------------------------------------------------------------


def test_provenance_discriminator_rejects_unknown_kind() -> None:
    """No fallback to first-member coercion — a `kind` value outside the
    union must fail loud."""
    adapter = TypeAdapter(Provenance)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "not_a_variant"})


def test_provenance_discriminator_routes_by_kind_field(
    app_direct: AppDirect,
) -> None:
    """Sanity: re-serializing under the wrong `kind` makes the adapter pick
    a different variant (and fail validation because the fields don't
    match). Pins the discriminator wiring."""
    adapter = TypeAdapter(Provenance)
    payload = app_direct.model_dump()
    payload["kind"] = "unknown"
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)


def test_provenance_discriminator_rejects_base_shape_under_app_kind(
    base_image: BaseImage,
) -> None:
    """`{"kind": "app_direct", <BaseImage fields>}` must not silently absorb
    into `AppDirect` — discriminator routes by `kind`, and `BaseImage`'s
    fields are not `AppDirect`'s."""
    adapter = TypeAdapter(Provenance)
    payload = base_image.model_dump()
    payload["kind"] = "app_direct"
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)


def test_provenance_discriminator_rejects_nested_both_at_deserialization(
    app_direct: AppDirect, base_image: BaseImage
) -> None:
    """The AC-4 recursion guard must survive deserialization too — a
    handcrafted JSON payload that shapes `Both` inside `Both.app_record`
    rejects at `TypeAdapter.validate_python`, mirroring the construction-
    time guard."""
    adapter = TypeAdapter(Provenance)
    inner_both_payload = {
        "kind": "both",
        "app_record": app_direct.model_dump(),
        "base_record": base_image.model_dump(),
    }
    outer_both_payload = {
        "kind": "both",
        "app_record": inner_both_payload,  # Nested Both — recursion-guard
        "base_record": base_image.model_dump(),
    }
    with pytest.raises(ValidationError):
        adapter.validate_python(outer_both_payload)
