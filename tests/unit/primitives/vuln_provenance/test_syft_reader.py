"""Phase 7 S1-05 — `SyftSbom` Pydantic reader model contract tests.

Pins the three models (`SyftSbom`, `SyftArtifact`, `SyftLocation`) declared
in `src/codegenie/primitives/vuln_provenance/syft_reader.py`:

- ``extra="allow"`` is the *deliberate* posture (Phase 2 carry-forward;
  ADR-0038). The upstream syft schema evolves; the model boundary admits
  unknown fields silently so adapters can keep working. Defense is at the
  *consumer* boundary — S4-04's AST-walk fence pins adapters to read only
  the fields listed in the module-level ``_KNOWN_*_FIELDS`` catalogs.
- ``layerID`` is camelCase (not ``layer_id``) — that is the load-bearing
  field name the Alpine / Distroless adapters read to attribute a CVE to
  a layer.
- The two ``_KNOWN_*_FIELDS`` ``Final[frozenset[str]]`` catalogs are the
  source of truth for S4-04's fence. Tightening / loosening them is a
  two-line change here.

Mirrors S1-02 / S1-03 / S1-04 test discipline — one test per AC, named for
the AC, ``ValidationError`` asserted via ``pytest.raises(...)`` (Rule 9).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.primitives.vuln_provenance import (
    SyftArtifact,
    SyftLocation,
    SyftSbom,
)
from codegenie.primitives.vuln_provenance import syft_reader as sr

FIXTURE = Path("tests/fixtures/syft/minimal_alpine.json")


# --- AC-2 — extra="allow" admits unknown fields ------------------------------


def test_syft_sbom_admits_unknown_fields() -> None:
    payload = {
        "artifacts": [],
        "spdx_version": "2.3",
        "unknown_field": [1, 2, 3],
    }
    sbom = SyftSbom.model_validate(payload)
    assert sbom.artifacts == []


def test_syft_artifact_admits_unknown_fields() -> None:
    artifact = SyftArtifact.model_validate(
        {
            "name": "openssl",
            "version": "3.0.7",
            "cpes": ["cpe:2.3:a:openssl:openssl:3.0.7:*:*:*:*:*:*:*"],
            "purl": "pkg:apk/alpine/openssl@3.0.7-r0?distro=alpine-3.18",
        }
    )
    assert artifact.name == "openssl"
    assert artifact.locations == []


def test_syft_location_admits_unknown_fields() -> None:
    loc = SyftLocation.model_validate(
        {
            "path": "/usr/bin/openssl",
            "layerID": "sha256:abc",
            "annotations": {"evidence": "primary"},
            "accessPath": "/usr/bin/openssl",
        }
    )
    assert loc.path == "/usr/bin/openssl"
    assert loc.layerID == "sha256:abc"


# --- AC-2.5 — empty-SBOM happy path ------------------------------------------


def test_empty_sbom_happy_path() -> None:
    """A no-unknowns empty SBOM is a legitimate adapter input state."""
    sbom = SyftSbom.model_validate({"artifacts": []})
    assert sbom.artifacts == []
    assert len(sbom.artifacts) == 0


def test_empty_artifact_list_default() -> None:
    """`artifacts` defaults to `[]` when omitted entirely."""
    sbom = SyftSbom.model_validate({})
    assert sbom.artifacts == []


def test_empty_locations_default() -> None:
    """`locations` defaults to `[]` so adapters can iterate unconditionally."""
    art = SyftArtifact.model_validate({"name": "x", "version": "1"})
    assert art.locations == []


# --- AC-3 — known fields typed + validated -----------------------------------


def test_syft_artifact_happy_path() -> None:
    art = SyftArtifact(name="openssl", version="3.0.7")
    assert art.name == "openssl"
    assert art.version == "3.0.7"
    assert art.locations == []


def test_syft_artifact_multi_location_preserves_order_and_optional_layer_id() -> None:
    """Real syft outputs frequently carry several `locations[]` entries per
    artifact. The model contract must admit + preserve them and keep
    `layerID` independently optional per location."""
    art = SyftArtifact.model_validate(
        {
            "name": "x",
            "version": "1",
            "locations": [
                {"path": "/a", "layerID": "sha256:aaa"},
                {"path": "/b", "layerID": "sha256:bbb"},
                {"path": "/c"},
            ],
        }
    )
    assert len(art.locations) == 3
    assert [loc.path for loc in art.locations] == ["/a", "/b", "/c"]
    assert [loc.layerID for loc in art.locations] == [
        "sha256:aaa",
        "sha256:bbb",
        None,
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {"name": None, "version": "1"},
        {"name": "x", "version": None},
        {"version": "1"},
        {"name": "x"},
    ],
)
def test_syft_artifact_rejects_invalid(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SyftArtifact.model_validate(bad)


@pytest.mark.parametrize(
    "bad",
    [
        {"path": None},
        {},
    ],
)
def test_syft_location_rejects_invalid(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SyftLocation.model_validate(bad)


def test_syft_location_layer_id_optional() -> None:
    loc = SyftLocation.model_validate({"path": "/x"})
    assert loc.layerID is None


# --- AC-4 — round-trip realistic fixture -------------------------------------


def test_minimal_alpine_fixture_round_trips() -> None:
    raw = FIXTURE.read_text()
    sbom = SyftSbom.model_validate_json(raw)
    assert len(sbom.artifacts) == 1
    art = sbom.artifacts[0]
    assert art.name == "openssl"
    assert art.version == "3.0.7-r0"
    assert len(art.locations) == 1
    loc = art.locations[0]
    assert loc.path == "/usr/bin/openssl"
    assert loc.layerID == "sha256:abc123"
    # Pre-condition: the fixture carries unknown top-level fields. If this
    # ever fails, the fixture lost its "unknowns admitted via extra=allow"
    # property and the test is no longer pinning AC-2 at the JSON layer.
    payload = json.loads(raw)
    assert "schema" in payload
    assert "descriptor" in payload
    assert "source" in payload


def test_minimal_alpine_fixture_lossless_for_known_fields() -> None:
    raw = FIXTURE.read_text()
    sbom = SyftSbom.model_validate_json(raw)
    dumped = json.loads(sbom.model_dump_json())
    assert dumped["artifacts"][0]["name"] == "openssl"
    assert dumped["artifacts"][0]["version"] == "3.0.7-r0"
    assert dumped["artifacts"][0]["locations"][0]["layerID"] == "sha256:abc123"


def test_full_encode_decode_encode_cycle_preserves_unknowns() -> None:
    """AC-4 mutation guard — an impl that silently drops unknown fields on
    serialization (e.g., switched to ``extra="ignore"`` or used
    ``model_dump(exclude_unset=True)``) would pass AC-2 but fail this
    test. The cycle ``parse → dump → re-parse → equal`` is the structural
    defense.
    """
    raw = FIXTURE.read_text()
    sbom1 = SyftSbom.model_validate_json(raw)

    dump1 = sbom1.model_dump(mode="json")
    # Unknown top-level fields survive the dump.
    assert "schema" in dump1
    assert "descriptor" in dump1
    assert "source" in dump1
    # Known fields survive the dump.
    assert dump1["artifacts"][0]["name"] == "openssl"
    assert dump1["artifacts"][0]["locations"][0]["layerID"] == "sha256:abc123"

    sbom2 = SyftSbom.model_validate(dump1)
    # Round-trip equality on the load-bearing known fields.
    assert sbom2.artifacts[0].locations[0].layerID == sbom1.artifacts[0].locations[0].layerID
    assert sbom2.artifacts[0].name == sbom1.artifacts[0].name
    assert sbom2.artifacts[0].version == sbom1.artifacts[0].version


# --- AC-5 — `layerID` is camelCase, load-bearing -----------------------------


def test_location_layer_id_field_name_is_camelcase() -> None:
    loc = SyftLocation.model_validate({"path": "/x", "layerID": "sha256:abc"})
    assert loc.layerID == "sha256:abc"
    # And NOT via snake_case — a future "harmonize names" refactor would
    # silently break the Alpine / Distroless adapters.
    with pytest.raises(AttributeError):
        loc.layer_id  # type: ignore[attr-defined]  # noqa: B018


# --- AC-6 — `_KNOWN_*_FIELDS` catalog pinned ---------------------------------


def test_known_location_fields_pinned() -> None:
    assert sr._KNOWN_LOCATION_FIELDS == frozenset({"path", "layerID"})


def test_known_artifact_fields_pinned() -> None:
    assert sr._KNOWN_ARTIFACT_FIELDS == frozenset({"name", "version", "locations"})


def test_known_fields_are_frozenset_not_set() -> None:
    """The catalogs are immutable on purpose; S4-04's fence reads them at
    import time. A mutable `set` would let any sibling module mutate the
    allowlist behind the fence's back."""
    assert isinstance(sr._KNOWN_LOCATION_FIELDS, frozenset)
    assert isinstance(sr._KNOWN_ARTIFACT_FIELDS, frozenset)


# --- AC-7 — public re-export -------------------------------------------------


def test_public_reexports_succeed() -> None:
    from codegenie.primitives.vuln_provenance import (
        SyftArtifact as PubArtifact,
    )
    from codegenie.primitives.vuln_provenance import (
        SyftLocation as PubLocation,
    )
    from codegenie.primitives.vuln_provenance import (
        SyftSbom as PubSbom,
    )

    assert PubSbom is sr.SyftSbom
    assert PubArtifact is sr.SyftArtifact
    assert PubLocation is sr.SyftLocation


def test_private_catalogs_not_in_public_all() -> None:
    """`_KNOWN_*_FIELDS` are module-private. Tests / fences read them via
    direct-module import, not via `__all__`."""
    import codegenie.primitives.vuln_provenance as pkg

    assert "_KNOWN_LOCATION_FIELDS" not in pkg.__all__
    assert "_KNOWN_ARTIFACT_FIELDS" not in pkg.__all__
