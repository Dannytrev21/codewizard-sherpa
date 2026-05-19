"""Phase 7 S1-01 AC-7 — Hypothesis totality + determinism + round-trip identity.

For any ``s: str`` drawn from ``hypothesis.strategies.text(max_size=300)``:

- Totality: every Phase 7 parser returns ``isinstance(r, (Ok, Err))`` and never
  raises.
- Determinism: ``parse_<x>(s) == parse_<x>(s)``.

For ``s`` drawn from each parser's own regex (``from_regex(..., fullmatch=True)``):

- Round-trip identity: ``parse_<x>(s).unwrap() == <X>(s)``.

Mirrors Phase 3's ``test_parsers_properties.py`` shape.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from codegenie.result import Err, Ok
from codegenie.types import parsers as P
from codegenie.types.identifiers import (
    DockerStageName,
    ImageDigest,
    LayerDigest,
    RuntimeId,
)

PHASE7_PARSERS = [
    P.parse_image_ref,
    P.parse_image_digest,
    P.parse_layer_digest,
    P.parse_runtime_id,
    P.parse_docker_stage_name,
]


@pytest.mark.parametrize("parser", PHASE7_PARSERS, ids=lambda p: p.__name__)
@given(s=st.text(max_size=300))
def test_total(parser, s):  # type: ignore[no-untyped-def]
    """Every parser is total — never raises on any string input."""
    try:
        r = parser(s)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"{parser.__name__}({s!r}) raised {type(e).__name__}: {e!r}")
    assert isinstance(r, (Ok, Err))


@pytest.mark.parametrize("parser", PHASE7_PARSERS, ids=lambda p: p.__name__)
@given(s=st.text(max_size=300))
def test_deterministic(parser, s):  # type: ignore[no-untyped-def]
    """``parse_<x>(s) == parse_<x>(s)`` for every input."""
    assert parser(s) == parser(s)


# --- Round-trip identity per parser-regex ----------------------------------


@given(s=st.from_regex(r"\Asha256:[0-9a-f]{64}\Z", fullmatch=True))
def test_image_digest_round_trip(s: str) -> None:
    r = P.parse_image_digest(s)
    assert isinstance(r, Ok)
    assert r.value == ImageDigest(s)


@given(s=st.from_regex(r"\Asha256:[0-9a-f]{64}\Z", fullmatch=True))
def test_layer_digest_round_trip(s: str) -> None:
    r = P.parse_layer_digest(s)
    assert isinstance(r, Ok)
    assert r.value == LayerDigest(s)


@given(s=st.from_regex(r"\A[a-z][a-z0-9_-]{0,63}\Z", fullmatch=True))
def test_runtime_id_round_trip(s: str) -> None:
    r = P.parse_runtime_id(s)
    assert isinstance(r, Ok)
    assert r.value == RuntimeId(s)


@given(s=st.from_regex(r"\A[a-z][a-z0-9_-]{0,63}\Z", fullmatch=True))
def test_docker_stage_name_round_trip(s: str) -> None:
    r = P.parse_docker_stage_name(s)
    assert isinstance(r, Ok)
    assert r.value == DockerStageName(s)
