"""Phase 4 S1-01 — parser totality, determinism, and round trips."""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.result import Err, Ok
from codegenie.types import parsers as P

PHASE4_STR_PARSERS = [
    P.parse_solved_example_id,
    P.parse_store_digest,
    P.parse_chain_head,
    P.parse_model_id,
    P.parse_budget_token_id,
    P.parse_hex_nonce,
]


@pytest.mark.parametrize("parser", PHASE4_STR_PARSERS, ids=lambda parser: parser.__name__)
@given(value=st.text(max_size=300))
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_phase4_str_parsers_are_total(parser: object, value: str) -> None:
    try:
        result = parser(value)  # type: ignore[operator]
    except Exception as exc:
        pytest.fail(f"{parser!r}({value!r}) raised {type(exc).__name__}: {exc!r}")
    assert isinstance(result, (Ok, Err))


@pytest.mark.parametrize("parser", PHASE4_STR_PARSERS, ids=lambda parser: parser.__name__)
@given(value=st.text(max_size=300))
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_phase4_str_parsers_are_deterministic(parser: object, value: str) -> None:
    assert parser(value) == parser(value)  # type: ignore[operator]


@given(value=st.floats(allow_nan=True, allow_infinity=True, width=64))
@settings(max_examples=50)
def test_similarity_parser_is_total_and_deterministic(value: float) -> None:
    result = P.parse_similarity(value)
    assert isinstance(result, (Ok, Err))
    assert result == P.parse_similarity(value) or math.isnan(value)


@given(value=st.integers(min_value=-(2**31), max_value=2**31))
@settings(max_examples=50)
def test_token_count_parser_is_total_and_deterministic(value: int) -> None:
    result = P.parse_token_count(value)
    assert isinstance(result, (Ok, Err))
    assert result == P.parse_token_count(value)


@given(value=st.from_regex(r"^[0-9a-f]{64}\Z", fullmatch=True))
@settings(max_examples=30)
def test_solved_example_id_round_trip(value: str) -> None:
    result = P.parse_solved_example_id(value)
    assert isinstance(result, Ok)
    assert result.value == value


@given(value=st.from_regex(r"^[0-9a-f]{64}\Z", fullmatch=True))
@settings(max_examples=30)
def test_store_digest_round_trip(value: str) -> None:
    result = P.parse_store_digest(value)
    assert isinstance(result, Ok)
    assert result.value == value


@given(value=st.from_regex(r"^[0-9a-f]{64}\Z", fullmatch=True))
@settings(max_examples=30)
def test_chain_head_round_trip(value: str) -> None:
    result = P.parse_chain_head(value)
    assert isinstance(result, Ok)
    assert result.value == value


@given(value=st.from_regex(r"^[0-9a-f]{32}\Z", fullmatch=True))
@settings(max_examples=30)
def test_hex_nonce_round_trip(value: str) -> None:
    result = P.parse_hex_nonce(value)
    assert isinstance(result, Ok)
    assert result.value == value


@given(
    value=st.from_regex(
        r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
        r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*(?:-[0-9]{8})?\Z",
        fullmatch=True,
    ).filter(lambda value: len(value) <= 128)
)
@settings(max_examples=30)
def test_model_id_round_trip(value: str) -> None:
    result = P.parse_model_id(value)
    assert isinstance(result, Ok)
    assert result.value == value


@given(
    value=st.from_regex(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z",
        fullmatch=True,
    )
)
@settings(max_examples=30)
def test_budget_token_id_round_trip(value: str) -> None:
    result = P.parse_budget_token_id(value)
    assert isinstance(result, Ok)
    assert result.value == value


@given(value=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=30)
def test_similarity_round_trip(value: float) -> None:
    result = P.parse_similarity(value)
    assert isinstance(result, Ok)
    assert result.value == value


@given(value=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=30)
def test_token_count_round_trip(value: int) -> None:
    result = P.parse_token_count(value)
    assert isinstance(result, Ok)
    assert result.value == value


def test_similarity_rejects_non_finite_values() -> None:
    assert isinstance(P.parse_similarity(math.nan), Err)
    assert isinstance(P.parse_similarity(math.inf), Err)
    assert isinstance(P.parse_similarity(-math.inf), Err)
