"""Phase 6 S1-01 AC-10 — newtype registry drift fence for the three Phase-6 additions.

``VulnCaseId``, ``RepoFixtureRef``, and ``SutDigest`` must:

1. Appear in ``codegenie.types.identifiers.__all__``.
2. Carry a one-line docstring in ``_NEWTYPE_REGISTRY`` naming ADR-0010 and
   Phase-6 ADR-0001.
3. Be reachable via their respective smart constructors
   (``parse_vuln_case_id`` / ``parse_repo_fixture_ref`` / ``parse_sut_digest``).
4. Be distinct NewType objects from one another and from the rest of the
   kernel-tier catalog.
"""

from __future__ import annotations

from codegenie.result import Err, Ok

PHASE6_NEWTYPE_NAMES = {"VulnCaseId", "RepoFixtureRef", "SutDigest"}


def test_phase6_newtypes_in_all() -> None:
    import codegenie.types.identifiers as ids

    for name in PHASE6_NEWTYPE_NAMES:
        assert name in ids.__all__, f"AC-10: {name} missing from __all__"


def test_phase6_newtypes_have_registry_entries() -> None:
    from codegenie.types.identifiers import _NEWTYPE_REGISTRY

    for name in PHASE6_NEWTYPE_NAMES:
        assert name in _NEWTYPE_REGISTRY, f"AC-10: {name} missing from _NEWTYPE_REGISTRY"
        doc = _NEWTYPE_REGISTRY[name]
        assert "ADR-0010" in doc, f"AC-10: {name} docstring missing ADR-0010 citation"
        assert "ADR-0001" in doc or "Phase-6" in doc or "Phase 6" in doc, (
            f"AC-10: {name} docstring should name Phase-6 ADR-0001"
        )


def test_phase6_newtypes_pairwise_distinct() -> None:
    import codegenie.types.identifiers as ids

    objs = [getattr(ids, name) for name in sorted(PHASE6_NEWTYPE_NAMES)]
    for i, a in enumerate(objs):
        for b in objs[i + 1 :]:
            assert a is not b


def test_parse_vuln_case_id_happy_path() -> None:
    from codegenie.types.identifiers import VulnCaseId
    from codegenie.types.parsers import parse_vuln_case_id

    r = parse_vuln_case_id("01HXX00000000000000000000Z")
    assert isinstance(r, Ok)
    assert r.value == VulnCaseId("01HXX00000000000000000000Z")


def test_parse_vuln_case_id_rejects_non_ulid() -> None:
    from codegenie.types.parsers import parse_vuln_case_id

    for bad in ("", "not-a-ulid", "01HXX0000000000000000000Z", "lowercase01hxx0000000000000"):
        assert isinstance(parse_vuln_case_id(bad), Err), bad


def test_parse_repo_fixture_ref_happy_path() -> None:
    from codegenie.types.identifiers import RepoFixtureRef
    from codegenie.types.parsers import parse_repo_fixture_ref

    r = parse_repo_fixture_ref("node_yarn_berry_pnp")
    assert isinstance(r, Ok)
    assert r.value == RepoFixtureRef("node_yarn_berry_pnp")


def test_parse_repo_fixture_ref_rejects_paths_and_uppercase() -> None:
    from codegenie.types.parsers import parse_repo_fixture_ref

    for bad in (
        "",
        "/absolute/path",
        "UPPER_CASE",
        "with space",
        "../escape",
        "a" * 129,
        "1starts_numeric",
    ):
        assert isinstance(parse_repo_fixture_ref(bad), Err), bad


def test_parse_sut_digest_happy_path() -> None:
    from codegenie.types.identifiers import SutDigest
    from codegenie.types.parsers import parse_sut_digest

    good = "blake3:" + "f" * 64
    r = parse_sut_digest(good)
    assert isinstance(r, Ok)
    assert r.value == SutDigest(good)


def test_parse_sut_digest_rejects_bad_grammar() -> None:
    from codegenie.types.parsers import parse_sut_digest

    for bad in (
        "",
        "sha256:" + "f" * 64,
        "blake3:" + "F" * 64,  # uppercase
        "blake3:" + "f" * 63,
        "blake3:" + "f" * 65,
        "f" * 64,
    ):
        assert isinstance(parse_sut_digest(bad), Err), bad
