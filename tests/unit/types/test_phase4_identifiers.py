"""Phase 4 S1-01 — newtype substrate and smart constructors."""

from __future__ import annotations

import math

import pytest

from codegenie.result import Err, Ok
from codegenie.types.identifiers import (
    _NEWTYPE_REGISTRY,
    BudgetTokenId,
    ChainHead,
    HexNonce,
    ModelId,
    Similarity,
    SolvedExampleId,
    StoreDigest,
    TokenCount,
)
from codegenie.types.parsers import (
    parse_budget_token_id,
    parse_chain_head,
    parse_hex_nonce,
    parse_model_id,
    parse_similarity,
    parse_solved_example_id,
    parse_store_digest,
    parse_token_count,
)

PHASE4_NAMES: frozenset[str] = frozenset(
    {
        "BudgetTokenId",
        "CassetteId",
        "ChainHead",
        "EmbeddingVector",
        "HexNonce",
        "LeafResponseId",
        "ModelId",
        "Similarity",
        "SolvedExampleId",
        "StoreDigest",
        "TokenCount",
    }
)
GOOD_BUDGET_TOKEN_ID = "12345678-1234-4abc-" + "89ab-1234567890ab"
BAD_BUDGET_TOKEN_VERSION = "12345678-1234-1abc-" + "89ab-1234567890ab"
BAD_BUDGET_TOKEN_VARIANT = "12345678-1234-4abc-" + "79ab-1234567890ab"


@pytest.mark.parametrize(
    "parser,good,wrapper",
    [
        (parse_solved_example_id, "a" * 64, SolvedExampleId),
        (parse_store_digest, "0" * 64, StoreDigest),
        (parse_chain_head, "f" * 64, ChainHead),
        (parse_hex_nonce, "0" * 32, HexNonce),
        (parse_model_id, "claude-sonnet-4-5-20250929", ModelId),
        (parse_budget_token_id, GOOD_BUDGET_TOKEN_ID, BudgetTokenId),
    ],
)
def test_phase4_str_parser_happy_paths(parser: object, good: str, wrapper: type[str]) -> None:
    result = parser(good)  # type: ignore[operator]
    assert isinstance(result, Ok)
    assert result.value == wrapper(good)


@pytest.mark.parametrize("value", [-1.0, -0.5, 0.0, 0.5, 0.85, 1.0])
def test_similarity_parser_happy_path(value: float) -> None:
    result = parse_similarity(value)
    assert isinstance(result, Ok)
    assert result.value == Similarity(value)


@pytest.mark.parametrize("value", [0, 2**31 - 1])
def test_token_count_parser_happy_path(value: int) -> None:
    result = parse_token_count(value)
    assert isinstance(result, Ok)
    assert result.value == TokenCount(value)


@pytest.mark.parametrize(
    "parser,bad",
    [
        (parse_solved_example_id, "A" * 64),
        (parse_solved_example_id, "0" * 63),
        (parse_solved_example_id, "g" * 64),
        (parse_store_digest, ""),
        (parse_chain_head, "f" * 65),
        (parse_hex_nonce, "0" * 30),
        (parse_hex_nonce, "0" * 34),
        (parse_hex_nonce, "A" * 32),
        (parse_model_id, "Claude-Sonnet"),
        (parse_model_id, "-leading-hyphen"),
        (parse_model_id, "trailing-dot."),
        (parse_model_id, "x" * 129),
        (parse_budget_token_id, BAD_BUDGET_TOKEN_VERSION),
        (parse_budget_token_id, BAD_BUDGET_TOKEN_VARIANT),
    ],
)
def test_phase4_str_parsers_reject_bad_inputs(parser: object, bad: str) -> None:
    result = parser(bad)  # type: ignore[operator]
    assert isinstance(result, Err)
    assert result.error.value == bad


@pytest.mark.parametrize("value", [1.0001, -1.0001, math.nan, math.inf, -math.inf, True])
def test_similarity_parser_rejects_bad_inputs(value: object) -> None:
    result = parse_similarity(value)  # type: ignore[arg-type]
    assert isinstance(result, Err)


@pytest.mark.parametrize("value", [-1, 2**31, "1", True])
def test_token_count_parser_rejects_bad_inputs(value: object) -> None:
    result = parse_token_count(value)  # type: ignore[arg-type]
    assert isinstance(result, Err)


def test_model_id_nfkc_and_ascii_only() -> None:
    assert isinstance(parse_model_id("claude-sonnet\uff0e4"), Err)
    assert isinstance(parse_model_id("claude-s\xf8nnet"), Err)


def test_phase4_newtype_names_and_supertype_are_pinned() -> None:
    import codegenie.types.identifiers as ids

    for name in PHASE4_NAMES:
        newtype = getattr(ids, name)
        assert newtype.__name__ == name

    assert ids.EmbeddingVector.__supertype__ is tuple
    assert ids.Similarity.__supertype__ is float
    assert ids.TokenCount.__supertype__ is int
    for name in PHASE4_NAMES - {"EmbeddingVector", "Similarity", "TokenCount"}:
        assert getattr(ids, name).__supertype__ is str


def test_phase4_newtypes_are_pairwise_distinct_from_existing_catalog() -> None:
    import codegenie.types.identifiers as ids
    from tests.unit.types.test_identifiers_phase3 import (
        PHASE2_NAMES,
        PHASE3_NAMES,
        PHASE7_NEWTYPE_NAMES,
    )

    names = sorted(
        (PHASE2_NAMES | PHASE3_NAMES | PHASE7_NEWTYPE_NAMES | PHASE4_NAMES) - {"PackageManager"}
    )
    objects = [getattr(ids, name) for name in names]
    for index, left in enumerate(objects):
        for right in objects[index + 1 :]:
            assert left is not right


def test_phase4_newtypes_reexport_identity_passthrough() -> None:
    import codegenie.types as public_types
    import codegenie.types.identifiers as ids

    for name in PHASE4_NAMES:
        assert getattr(public_types, name) is getattr(ids, name)


@pytest.mark.parametrize("name", sorted(PHASE4_NAMES))
def test_phase4_newtypes_raise_typeerror_under_isinstance(name: str) -> None:
    import codegenie.types.identifiers as ids

    with pytest.raises(TypeError):
        isinstance("foo", getattr(ids, name))  # type: ignore[arg-type]


def test_phase4_newtypes_are_documented_in_shared_registry() -> None:
    assert PHASE4_NAMES <= set(_NEWTYPE_REGISTRY)
    for name in PHASE4_NAMES:
        doc = _NEWTYPE_REGISTRY[name]
        assert "Phase-4" in doc
        assert "ADR-000" in doc or "ADR-001" in doc
