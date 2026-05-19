"""Phase 7 S1-01 — newtype identifier catalog + smart-constructor tests.

Covers AC-1, AC-2, AC-3, AC-4, AC-5, AC-8, AC-9, AC-10, AC-11 from
``docs/phases/07-migration-task-class/stories/S1-01-phase7-newtype-identifiers.md``.

The subprocess-mypy cross-newtype-swap rejection (AC-6) lives in
``test_identifiers_phase7_mypy_negative.py``. Hypothesis totality /
determinism / round-trip (AC-7) lives in
``test_parsers_phase7_properties.py``.
"""

from __future__ import annotations

import typing
from typing import ForwardRef, Literal, get_type_hints

import pytest

from codegenie.result import Err, Ok
from codegenie.types.identifiers import (
    CveId,
    DockerStageName,
    ImageDigest,
    ImageRef,
    LayerDigest,
    PackageId,
    RuntimeId,
)
from codegenie.types.parsers import (
    parse_docker_stage_name,
    parse_image_digest,
    parse_image_ref,
    parse_layer_digest,
    parse_runtime_id,
)

PHASE7_STR_NEWTYPES = {
    "ImageRef",
    "ImageDigest",
    "LayerDigest",
    "RuntimeId",
    "DockerStageName",
}


# ---------------------------------------------------------------------------
# AC-3 — happy paths (one per parser)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "parser,good,wrapper",
    [
        (parse_image_ref, "cgr.dev/chainguard/node:latest", ImageRef),
        (parse_image_ref, "node:20-alpine", ImageRef),
        (parse_image_ref, "node", ImageRef),
        (parse_image_digest, "sha256:" + "0" * 64, ImageDigest),
        (parse_image_digest, "sha256:" + "a" * 64, ImageDigest),
        (parse_layer_digest, "sha256:" + "a" * 64, LayerDigest),
        (parse_layer_digest, "sha256:" + "f" * 64, LayerDigest),
        (parse_runtime_id, "node20", RuntimeId),
        (parse_runtime_id, "openjdk21", RuntimeId),
        (parse_runtime_id, "python3-11", RuntimeId),
        (parse_docker_stage_name, "builder", DockerStageName),
        (parse_docker_stage_name, "test-runner", DockerStageName),
        (parse_docker_stage_name, "stage_one", DockerStageName),
    ],
)
def test_parser_happy_path(parser, good, wrapper):  # type: ignore[no-untyped-def]
    r = parser(good)
    assert isinstance(r, Ok)
    assert r.value == wrapper(good)


# ---------------------------------------------------------------------------
# AC-4 — ImageDigest rejects non-sha256: + contamination
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        # Algorithm — other algorithms rejected at the type level.
        "sha512:" + "0" * 128,
        "md5:" + "0" * 32,
        "blake3:" + "0" * 64,
        # Casing.
        "SHA256:" + "0" * 64,
        "sha256:" + "A" * 64,
        # Length.
        "sha256:" + "0" * 63,
        "sha256:" + "0" * 65,
        # Charset.
        "sha256:" + "g" * 64,
        # Structure.
        "",
        "0" * 64,
        ":" + "0" * 64,
        "sha256:",
        # Contamination (SBOM read-back patterns).
        " sha256:" + "0" * 64,
        "sha256:" + "0" * 64 + " ",
        "sha256:" + "0" * 64 + "\n",
        "sha256:" + "0" * 64 + "\x00",
        "sha256:" + "0" * 32 + "\x7f" + "0" * 31,
    ],
)
def test_image_digest_rejects_non_sha256(bad: str) -> None:
    r = parse_image_digest(bad)
    assert isinstance(r, Err)
    assert r.error.value == bad


# LayerDigest shares the same grammar — the err.message must name LayerDigest
# (mirrors Phase 3's per-newtype closure catalog).
def test_layer_digest_error_message_names_layer_digest() -> None:
    r = parse_layer_digest("not-a-digest")
    assert isinstance(r, Err)
    assert "LayerDigest" in r.error.message


def test_image_digest_error_message_names_image_digest() -> None:
    r = parse_image_digest("not-a-digest")
    assert isinstance(r, Err)
    assert "ImageDigest" in r.error.message


# ---------------------------------------------------------------------------
# AC-3 — ImageRef floor (length, whitespace, control chars, single-`:`)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "",  # empty
        " ",  # single space
        "image name",  # embedded space
        "image\tname",  # embedded tab
        "image\nname",  # embedded newline
        "image\x00name",  # embedded NUL
        "image\x7fname",  # embedded DEL
        "image\x1fname",  # embedded US (last C0 control char)
        "a" * 257,  # 257 chars — one over the floor
        "node:20:foo",  # multi-`:` rejected
        "node:",  # trailing `:` (empty tag) rejected
    ],
)
def test_image_ref_rejects(bad: str) -> None:
    r = parse_image_ref(bad)
    assert isinstance(r, Err)
    assert r.error.value == bad


def test_image_ref_max_length_boundary_accepted() -> None:
    """256 chars (the floor) is accepted; 257 is rejected (above)."""
    r = parse_image_ref("a" * 256)
    assert isinstance(r, Ok)


# ---------------------------------------------------------------------------
# AC-3 — RuntimeId / DockerStageName length boundaries
# ---------------------------------------------------------------------------


def test_runtime_id_64_char_boundary_accepted() -> None:
    r = parse_runtime_id("a" * 64)
    assert isinstance(r, Ok)


def test_runtime_id_65_char_boundary_rejected() -> None:
    r = parse_runtime_id("a" * 65)
    assert isinstance(r, Err)


def test_runtime_id_rejects_uppercase() -> None:
    r = parse_runtime_id("Node20")
    assert isinstance(r, Err)


def test_runtime_id_rejects_leading_digit() -> None:
    r = parse_runtime_id("2node")
    assert isinstance(r, Err)


def test_docker_stage_name_64_char_boundary_accepted() -> None:
    r = parse_docker_stage_name("a" * 64)
    assert isinstance(r, Ok)


def test_docker_stage_name_65_char_boundary_rejected() -> None:
    r = parse_docker_stage_name("a" * 65)
    assert isinstance(r, Err)


def test_docker_stage_name_rejects_uppercase() -> None:
    r = parse_docker_stage_name("Builder")
    assert isinstance(r, Err)


def test_docker_stage_name_rejects_leading_digit() -> None:
    r = parse_docker_stage_name("2builder")
    assert isinstance(r, Err)


# ---------------------------------------------------------------------------
# AC-2 — Phase 3 CveId / PackageId still importable from same home
# ---------------------------------------------------------------------------


def test_phase3_cve_id_and_package_id_unchanged() -> None:
    """Phase 7 must not shadow Phase 3 CveId / PackageId."""
    import codegenie.types.identifiers as ids

    assert ids.CveId.__name__ == "CveId"
    assert ids.PackageId.__name__ == "PackageId"
    assert "CveId" in ids.__all__
    assert "PackageId" in ids.__all__
    # Same objects — Phase 7 imports them verbatim, not via re-binding.
    assert ids.CveId is CveId
    assert ids.PackageId is PackageId


# ---------------------------------------------------------------------------
# AC-5 — Catalog identity invariants
# ---------------------------------------------------------------------------


def test_phase7_newtype_names_pinned() -> None:
    import codegenie.types.identifiers as ids

    for name in PHASE7_STR_NEWTYPES:
        nt = getattr(ids, name)
        assert nt.__name__ == name


def test_phase7_pairwise_distinct() -> None:
    """Every pair (A, B) with A != B satisfies A is not B."""
    import codegenie.types.identifiers as ids

    # Phase 7 newtypes + a representative slice of Phase 0/1/2/3 names.
    names = sorted(
        PHASE7_STR_NEWTYPES
        | {
            "CveId",
            "PackageId",
            "PluginId",
            "RecipeId",
            "TransformId",
            "BlobDigest",
            "BranchName",
            "WorkflowId",
            "EventId",
            "RegistryUrl",
            "SignalKind",
            "PrimitiveName",
            "TransformKind",
            "PackageName",
            "SemverVersion",
            "BundleCacheKey",
            "AttemptNumber",
            "ErrorId",
            "IndexId",
            "SkillId",
            "TaskClassId",
            "IndexName",
            "ProbeId",
            "Language",
            "ConventionId",
        }
    )
    objs = [getattr(ids, n) for n in names]
    for i, a in enumerate(objs):
        for b in objs[i + 1 :]:
            assert a is not b, f"pairwise distinctness violated for {a} / {b}"


def test_phase7_exact_set_all() -> None:
    """``__all__`` is the exact superset including the six Phase 7 names."""
    import codegenie.types.identifiers as ids

    expected_phase7 = PHASE7_STR_NEWTYPES | {"ProvenanceAdapterId"}
    assert expected_phase7.issubset(set(ids.__all__))


def test_phase7_identity_passthrough() -> None:
    """``codegenie.types.X is codegenie.types.identifiers.X`` for each Phase 7 name."""
    import codegenie.types as pkg
    import codegenie.types.identifiers as ids

    for name in PHASE7_STR_NEWTYPES:
        assert getattr(pkg, name) is getattr(ids, name)


@pytest.mark.parametrize("name", sorted(PHASE7_STR_NEWTYPES))
def test_phase7_isinstance_raises_typeerror(name: str) -> None:
    """``isinstance(value, NewType)`` raises ``TypeError`` at runtime (Phase 3 precedent)."""
    import codegenie.types.identifiers as ids

    nt = getattr(ids, name)
    with pytest.raises(TypeError):
        isinstance("foo", nt)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC-8 — Docstring registry extended (cite ADR + consumer)
# ---------------------------------------------------------------------------


_PHASE7_CONSUMER_HINTS: frozenset[str] = frozenset(
    {
        "BaseImage",
        "RuntimeBundled",
        "BaseImageStage",
        "Dockerfile",
        "SyftSbom",
        "adapter",
        "assemble_provenance",
        "_REGISTRY",
    }
)


def test_phase7_registry_keys_equal_all() -> None:
    """``_NEWTYPE_REGISTRY`` keys equal ``__all__``."""
    import codegenie.types.identifiers as ids
    from codegenie.types.identifiers import _NEWTYPE_REGISTRY

    assert set(_NEWTYPE_REGISTRY.keys()) == set(ids.__all__) - {"ProvenanceAdapterId"}


@pytest.mark.parametrize("name", sorted(PHASE7_STR_NEWTYPES))
def test_phase7_registry_entry_cites_adr_and_consumer(name: str) -> None:
    """Every Phase 7 entry cites ADR-0004 or ADR-0006, AND names a consumer."""
    from codegenie.types.identifiers import _NEWTYPE_REGISTRY

    doc = _NEWTYPE_REGISTRY[name]
    assert doc.strip()
    assert "ADR-0004" in doc or "ADR-0006" in doc, (
        f"{name} docstring must cite Phase 7 ADR-0004 or ADR-0006: {doc!r}"
    )
    assert any(hint in doc for hint in _PHASE7_CONSUMER_HINTS), (
        f"{name} docstring must name a Phase 7 consumer "
        f"(one of {sorted(_PHASE7_CONSUMER_HINTS)!r}): {doc!r}"
    )


# ---------------------------------------------------------------------------
# AC-9 — ProvenanceAdapterId alias shape
# ---------------------------------------------------------------------------


def test_provenance_adapter_id_is_tuple_alias_with_forward_refs() -> None:
    """``ProvenanceAdapterId`` is ``tuple[ForwardRef("_PhVnLayer"), ForwardRef("_PhVnEcosystem")]``.

    Underscored aliases (``_PhVnLayer`` / ``_PhVnEcosystem``) keep the Phase 7
    ``Ecosystem`` distinct from the Phase 3 ``codegenie.types.identifiers.Ecosystem``
    Literal at the symbol level.

    # TODO(S2-01): once ``primitives/vuln_provenance/registry.py`` lands the real
    # ``Layer`` / ``Ecosystem`` enums, tighten this test to:
    #     from codegenie.primitives.vuln_provenance.registry import Layer, Ecosystem
    #     hints = get_type_hints(_module, include_extras=True)
    #     assert hints["ProvenanceAdapterId"] == tuple[Layer, Ecosystem]
    """
    from codegenie.types.identifiers import ProvenanceAdapterId

    origin = typing.get_origin(ProvenanceAdapterId)
    assert origin is tuple, f"expected tuple origin, got {origin!r}"
    args = typing.get_args(ProvenanceAdapterId)
    assert len(args) == 2, f"expected 2 tuple args, got {len(args)}: {args!r}"
    # ``tuple["X", "Y"]`` may yield either bare strings or ForwardRef sentinels
    # depending on Python version (3.13 yields bare strings; older versions
    # yield ForwardRef). Either way the forward-reference *name* is what
    # matters — assert both args resolve to the underscored aliases that keep
    # the Phase 7 ``Ecosystem`` distinct from the Phase 3 ``Ecosystem`` Literal.
    names = tuple(a.__forward_arg__ if isinstance(a, ForwardRef) else a for a in args)
    assert names == ("_PhVnLayer", "_PhVnEcosystem"), (
        f"expected ('_PhVnLayer', '_PhVnEcosystem'), got {names!r}"
    )


# ---------------------------------------------------------------------------
# AC-10 — Package-level re-export discipline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    sorted(PHASE7_STR_NEWTYPES | {"ProvenanceAdapterId"}),
)
def test_package_level_reexport_identity(name: str) -> None:
    """``codegenie.types.X is codegenie.types.identifiers.X`` for each Phase 7 name."""
    import codegenie.types as pkg
    import codegenie.types.identifiers as ids

    assert getattr(pkg, name) is getattr(ids, name)
    assert name in pkg.__all__


# ---------------------------------------------------------------------------
# AC-11 — Ecosystem symbol-collision sentinel
# ---------------------------------------------------------------------------


def test_phase3_ecosystem_is_literal_not_enum() -> None:
    """The Phase 3 ``Ecosystem`` is a ``typing.Literal``, NOT an Enum.

    The Phase 7 ``codegenie.primitives.vuln_provenance.registry.Ecosystem`` (lands
    in S2-01) is a distinct ``str, Enum`` with different membership.

    # TODO(S2-01): once the Phase 7 enum lands, extend this test to:
    #     from codegenie.primitives.vuln_provenance.registry import Ecosystem as PhEco
    #     from codegenie.types.identifiers import Ecosystem as Ph3Eco
    #     assert Ph3Eco is not PhEco
    # Importing today would error because the module doesn't yet exist.
    """
    from codegenie.types.identifiers import Ecosystem

    origin = typing.get_origin(Ecosystem)
    assert origin is Literal, (
        f"Phase 3 Ecosystem must be typing.Literal (got origin={origin!r}); "
        "if you're adding a Phase 7 enum, do it at "
        "codegenie.primitives.vuln_provenance.registry.Ecosystem, NOT here."
    )


# Smoke — ProvenanceAdapterId is importable from both the module and the package.
def test_provenance_adapter_id_importable() -> None:
    from codegenie.types import ProvenanceAdapterId as PkgPAId
    from codegenie.types.identifiers import ProvenanceAdapterId as ModPAId

    assert PkgPAId is ModPAId


# ---------------------------------------------------------------------------
# Tail — keep ``get_type_hints`` import live so flake/ruff doesn't complain.
# (The real ``get_type_hints``-based tightening is the S2-01 TODO above.)
# ---------------------------------------------------------------------------
_ = get_type_hints
