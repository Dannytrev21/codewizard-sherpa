"""Phase 3 S1-01 — newtype identifier catalog + smart-constructor tests.

Covers AC-1, AC-3, AC-4a, AC-4b (rejection-matrix M1–M14), AC-7, AC-9, AC-10,
AC-11, AC-12, AC-13, AC-14, AC-15 from
``docs/phases/03-vuln-deterministic-recipe/stories/S1-01-phase3-newtype-identifiers.md``.

The cross-newtype mypy negative test (AC-4c) lives in
``test_identifiers_phase3_mypy_negative.py``. Hypothesis totality/determinism
and round-trip identity (AC-17) live in ``test_parsers_properties.py``.
Module purity (AC-16) lives in ``test_module_purity.py``.
"""

from __future__ import annotations

import pytest

from codegenie.result import Err, Ok
from codegenie.types.errors import ParseError
from codegenie.types.identifiers import (
    AttemptNumber,
    BlobDigest,
    BranchName,
    CveId,
    EventId,
    PackageId,
    PluginId,
    PrimitiveName,
    RecipeId,
    RegistryUrl,
    SignalKind,
    TransformId,
    TransformKind,
    WorkflowId,
)
from codegenie.types.parsers import (
    parse_attempt_number,
    parse_blob_digest,
    parse_branch_name,
    parse_cve_id,
    parse_event_id,
    parse_package_id,
    parse_plugin_id,
    parse_primitive_name,
    parse_recipe_id,
    parse_registry_url,
    parse_signal_kind,
    parse_transform_id,
    parse_transform_kind,
    parse_workflow_id,
)

# ---------------------------------------------------------------------------
# AC-4a — happy paths (one per parser)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "parser,good,wrapper",
    [
        (parse_cve_id, "CVE-2024-21501", CveId),
        (parse_branch_name, "feat/add-thing.v1", BranchName),
        (parse_blob_digest, "0" * 64, BlobDigest),
        (parse_workflow_id, "01HXX00000000000000000000Z", WorkflowId),
        (parse_event_id, "01HXX00000000000000000000Z", EventId),
        (parse_registry_url, "https://registry.npmjs.org", RegistryUrl),
        (parse_signal_kind, "build_ok", SignalKind),
        (parse_primitive_name, "subprocess_jail", PrimitiveName),
        (parse_transform_kind, "lockfile_pin", TransformKind),
        (parse_package_id, "lodash@4.17.21", PackageId),
        (parse_package_id, "@scope/pkg@1.0.0", PackageId),
        (parse_plugin_id, "vulnerability-remediation--node--npm", PluginId),
        (parse_recipe_id, "npm-lockfile-pin", RecipeId),
        (parse_transform_id, "a" * 64, TransformId),
    ],
)
def test_parser_happy_path(parser, good, wrapper):  # type: ignore[no-untyped-def]
    r = parser(good)
    assert isinstance(r, Ok)
    assert r.value == wrapper(good)


def test_attempt_number_happy_path() -> None:
    r = parse_attempt_number(3)
    assert isinstance(r, Ok)
    assert r.value == AttemptNumber(3)


def test_attempt_number_upper_bound_inclusive() -> None:
    r = parse_attempt_number(1024)
    assert isinstance(r, Ok)
    assert r.value == AttemptNumber(1024)


# ---------------------------------------------------------------------------
# AC-4b — rejection matrix M1–M14
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "parser,bad",
    [
        (parse_cve_id, "cve-2024-21501"),  # lowercase
        (parse_cve_id, "CVE-2024-1234567890123"),  # too long suffix
        (parse_cve_id, "CVE-24-1234"),  # short year
        (parse_blob_digest, "A" * 64),  # uppercase hex
        (parse_blob_digest, "0" * 63),  # wrong length
        (parse_blob_digest, "g" * 64),  # non-hex
        (parse_transform_id, "A" * 64),  # uppercase hex
        (parse_transform_id, "g" * 64),  # non-hex
        (parse_registry_url, "http://registry.npmjs.org"),  # wrong scheme
        (parse_registry_url, "HTTPS://registry.npmjs.org"),  # uppercase scheme
        (parse_registry_url, "https://user:pw@registry.npmjs.org"),  # userinfo
        (parse_registry_url, "https://registry.npmjs.org/?p=1"),  # query
        (parse_registry_url, "https://registry.npmjs.org/#frag"),  # fragment
        (parse_registry_url, "https://"),  # no host
        (parse_registry_url, "javascript:alert(1)"),  # bogus scheme
        (parse_signal_kind, "BuildOk"),  # uppercase
        (parse_signal_kind, "1leading"),  # leading digit
        (parse_primitive_name, "1leading_digit"),  # leading digit
        (parse_primitive_name, "kebab-not-snake"),  # kebab disallowed
        (parse_transform_kind, "kebab-not-snake"),  # kebab disallowed
        (parse_transform_kind, "Has Spaces"),  # whitespace
        (parse_package_id, "lodash@4.0"),  # partial semver
        (parse_package_id, "lodash@^4.0.0"),  # caret range
        (parse_package_id, "lodash@~4.0.0"),  # tilde range
        (parse_package_id, "lodash@>=4.0.0"),  # gte range
        (parse_package_id, "LODASH@4.0.0"),  # uppercase name
        (parse_package_id, "lodash"),  # no version
        (parse_package_id, "@scope/pkg"),  # scoped no version
        (parse_plugin_id, "vuln--node"),  # missing third dim
        (parse_plugin_id, "Vuln--node--npm"),  # uppercase
        (parse_recipe_id, "Has Spaces"),  # whitespace
        (parse_recipe_id, "Caps"),  # uppercase
        (parse_workflow_id, "01HXX00000000000000000000z"),  # lowercase
        (parse_workflow_id, "01HXX0000000000000000000"),  # too short
        (parse_workflow_id, "81HXX00000000000000000000Z"),  # leading > 7
        (parse_event_id, "01HXX00000000000000000000z"),  # lowercase
    ],
)
def test_parser_rejects(parser, bad):  # type: ignore[no-untyped-def]
    r = parser(bad)
    assert isinstance(r, Err)
    assert r.error.value == bad


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "feature branch",
        "../escape",
        "A" * 201,
        ".dotleading",
        "trailing/",
        "double//slash",
        "UPPER",
    ],
)
def test_branch_name_rejects(bad: str) -> None:
    r = parse_branch_name(bad)
    assert isinstance(r, Err)
    assert r.error.value == bad


@pytest.mark.parametrize("bad", [0, -1, -(2**31), 1025])
def test_attempt_number_rejects_out_of_range(bad: int) -> None:
    r = parse_attempt_number(bad)
    assert isinstance(r, Err)


def test_attempt_number_rejects_non_int() -> None:
    # str-not-int passed at runtime: str is not int, so the parser must reject.
    r = parse_attempt_number("1")  # type: ignore[arg-type]
    assert isinstance(r, Err)


# ---------------------------------------------------------------------------
# AC-14 — NFKC + ASCII-only adversarial
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "parser,bad",
    [
        (parse_branch_name, "feat​branch"),  # zero-width space
        (parse_branch_name, "﻿branch"),  # BOM
        (parse_branch_name, "feat\x00branch"),  # NUL
        (parse_branch_name, "bránch"),  # latin small a with acute (non-ASCII)
        (parse_package_id, "lodash​@4.17.21"),  # ZWS in name
        # NFKC-normalised full-width digit becomes ASCII "1" but still rejected
        # because the regex requires the name to be lowercase before normalisation
        # collapses it — the parser normalises first, then matches ASCII-only.
        (parse_package_id, "loda­sh@1.0.0"),  # soft hyphen
        (parse_package_id, "lodash@1​.0.0"),  # ZWS in version
    ],
)
def test_adversarial_unicode_rejected(parser, bad):  # type: ignore[no-untyped-def]
    r = parser(bad)
    assert isinstance(r, Err)


# ---------------------------------------------------------------------------
# AC-9 — __name__ pinning
# AC-10 — pairwise distinctness
# AC-11 — exact-set __all__
# AC-12 — identity passthrough via __init__
# AC-13 — isinstance runtime TypeError
# AC-15 — docstring registry
# ---------------------------------------------------------------------------


PHASE3_NAMES = {
    "PluginId",
    "RecipeId",
    "TransformId",
    "WorkflowId",
    "EventId",
    "CveId",
    "PackageId",
    "BranchName",
    "BlobDigest",
    "RegistryUrl",
    "SignalKind",
    "PrimitiveName",
    "TransformKind",
    "AttemptNumber",
    "ErrorId",
    # S3-02 additive — VulnIndex kernel-tier additions.
    "PackageName",
    # S3-03 additive — semver-2.0.0 newtype for AffectedRange parsing.
    "SemverVersion",
    # S3-05 additive — Bundle cache key (compose_bundle_cache_key smart constructor).
    "BundleCacheKey",
}
# Closed-set ``Literal[...]`` aliases — counted in ``__all__`` but not in the
# NewType-specific assertions (``__name__``, ``isinstance``, distinctness).
PHASE3_LITERAL_NAMES = {"Ecosystem"}
PHASE2_NAMES = {
    "ConventionId",
    "IndexId",
    "IndexName",
    "Language",
    "PackageManager",
    "ProbeId",
    "SkillId",
    "TaskClassId",
}
# Phase 7 S1-01 — additive catalog extensions. Five str-backed NewTypes plus
# the ``ProvenanceAdapterId`` ``TypeAlias`` (``tuple[Layer, Ecosystem]`` —
# NewType over a generic tuple is unsupported under mypy --strict, so this
# row is in ``__all__`` but NOT in ``_NEWTYPE_REGISTRY`` — see Phase 7
# ADR-0006).
PHASE7_NEWTYPE_NAMES = {
    "ImageRef",
    "ImageDigest",
    "LayerDigest",
    "RuntimeId",
    "DockerStageName",
}
PHASE7_TYPE_ALIAS_NAMES = {"ProvenanceAdapterId"}


def test_newtype_names_pinned() -> None:
    """AC-9 — every NewType's ``__name__`` matches its export name."""
    import codegenie.types.identifiers as ids

    for name in PHASE3_NAMES:
        nt = getattr(ids, name)
        assert nt.__name__ == name, f"{name!r} has __name__={nt.__name__!r}"


def test_pairwise_distinct() -> None:
    """AC-10 — every NewType is a distinct object from every other."""
    import codegenie.types.identifiers as ids

    # PackageManager + PHASE3_LITERAL_NAMES (Ecosystem) are Literal aliases,
    # not NewTypes — exclude from identity check.
    names = sorted((PHASE2_NAMES | PHASE3_NAMES) - {"PackageManager"})
    objs = [getattr(ids, n) for n in names]
    for i, a in enumerate(objs):
        for b in objs[i + 1 :]:
            assert a is not b


def test_all_is_exact_set() -> None:
    """AC-11 — ``__all__`` is exactly Phase-2 ∪ Phase-3 ∪ literals ∪ Phase-7, sorted."""
    import codegenie.types.identifiers as ids

    assert (
        set(ids.__all__)
        == PHASE2_NAMES
        | PHASE3_NAMES
        | PHASE3_LITERAL_NAMES
        | PHASE7_NEWTYPE_NAMES
        | PHASE7_TYPE_ALIAS_NAMES
    )
    assert ids.__all__ == sorted(ids.__all__), "__all__ must be sorted"


def test_identity_passthrough_via_init() -> None:
    """AC-12 — package re-exports the same object identities, not re-wrapped."""
    import codegenie.types as pkg
    import codegenie.types.identifiers as ids

    for name in PHASE3_NAMES:
        assert getattr(pkg, name) is getattr(ids, name)


@pytest.mark.parametrize("name", sorted(PHASE3_NAMES - {"AttemptNumber"}))
def test_isinstance_raises_typeerror(name: str) -> None:
    """AC-13 — NewType is not a class; ``isinstance`` must raise TypeError."""
    import codegenie.types.identifiers as ids

    nt = getattr(ids, name)
    with pytest.raises(TypeError):
        isinstance("foo", nt)  # type: ignore[arg-type]


def test_attempt_number_isinstance_raises_typeerror() -> None:
    """AC-13 — even the int-backed NewType is not a class."""
    import codegenie.types.identifiers as ids

    with pytest.raises(TypeError):
        isinstance(1, ids.AttemptNumber)  # type: ignore[arg-type]


def test_newtype_registry_matches_all() -> None:
    """AC-15 — _NEWTYPE_REGISTRY mirrors ``__all__`` modulo TypeAlias rows.

    ``ProvenanceAdapterId`` (Phase 7 S1-01) is a ``TypeAlias`` over a generic
    tuple, not a ``NewType``; it appears in ``__all__`` but not in
    ``_NEWTYPE_REGISTRY``. Phase 7 entries cite ADR-0004 / ADR-0006 instead
    of Phase 3's ADR-0010 — the per-entry-doc citation assertion below honours
    both (Phase 7 entries are validated in
    ``tests/unit/types/test_identifiers_phase7.py``).
    """
    from codegenie.types.identifiers import _NEWTYPE_REGISTRY, __all__

    assert set(_NEWTYPE_REGISTRY.keys()) == set(__all__) - PHASE7_TYPE_ALIAS_NAMES
    for name, doc in _NEWTYPE_REGISTRY.items():
        assert doc.strip(), f"{name} has empty docstring"
        if name in PHASE7_NEWTYPE_NAMES:
            assert "ADR-0004" in doc or "ADR-0006" in doc, (
                f"{name} Phase 7 docstring missing ADR-0004 / ADR-0006 citation"
            )
        else:
            assert "ADR-0010" in doc, f"{name} docstring missing ADR-0010 citation"


# ---------------------------------------------------------------------------
# AC-1 — every NewType is a NewType over the right supertype
# AC-2 — ParseError shape
# ---------------------------------------------------------------------------


def test_phase3_newtypes_are_newtype_over_correct_supertype() -> None:
    """AC-1 — 13 str-backed and 1 int-backed NewType in the Phase 3 catalog."""
    import codegenie.types.identifiers as ids

    for name in PHASE3_NAMES - {"AttemptNumber"}:
        nt = getattr(ids, name)
        assert nt.__supertype__ is str, f"{name} must be NewType over str"
    assert ids.AttemptNumber.__supertype__ is int


def test_parse_error_is_frozen_pydantic() -> None:
    """AC-2 — ParseError is a frozen Pydantic model with exactly two fields."""
    err = ParseError(message="bad", value="lol")
    assert err.message == "bad"
    assert err.value == "lol"

    # Frozen: mutation must raise.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        err.message = "changed"  # type: ignore[misc]

    # extra="forbid": unknown fields rejected.
    with pytest.raises(ValidationError):
        ParseError(message="x", value="y", extra="nope")  # type: ignore[call-arg]


def test_parse_error_module_exports_only_parse_error() -> None:
    """AC-2 — ``codegenie.types.errors.__all__`` is exactly ['ParseError']."""
    import codegenie.types.errors as e

    assert e.__all__ == ["ParseError"]


# ---------------------------------------------------------------------------
# AC-18 — helper extraction (rule-of-three)
# ---------------------------------------------------------------------------


def test_only_one_fullmatch_outside_helper() -> None:
    """AC-18 — five regex-shaped parsers go through ``_regex_parser``.

    AST-walk ``parsers.py``; assert at most ONE ``re.compile(...).fullmatch(``
    occurs outside the body of the ``_regex_parser`` helper. (One = the helper
    itself; URL host check uses its own structural validator.)
    """
    import ast
    import inspect

    import codegenie.types.parsers as parsers_mod

    src = inspect.getsource(parsers_mod)
    tree = ast.parse(src)

    # Find _regex_parser body.
    helper_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_regex_parser":
            for sub in ast.walk(node):
                if hasattr(sub, "lineno") and sub.lineno is not None:
                    helper_lines.add(sub.lineno)

    # Count Attribute(value=..., attr='fullmatch') outside helper.
    outside_count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "fullmatch"
        ):
            ln = getattr(node, "lineno", None)
            if ln is None or ln not in helper_lines:
                outside_count += 1

    assert outside_count <= 1, (
        f"{outside_count} call(s) to .fullmatch( outside _regex_parser — "
        "regex-shaped parsers must go through the helper (AC-18)."
    )
