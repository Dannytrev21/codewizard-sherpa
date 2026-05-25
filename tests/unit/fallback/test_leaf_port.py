"""Phase-4 S3-01 — ``LeafLlm`` Protocol + ``LeafResponse`` model behavior tests.

Each negative test mutates exactly one key off the baseline (``_valid_kwargs``)
so the ``ValidationError`` isolates one rule (S3-01 AC-3 / AC-7 / AC-8).

Companion meta-tests live beside this file:
- ``test_port_module_purity.py`` — AC-4 AST source-scan (no SDK / HTTP / socket /
  ssl imports; pydantic + stdlib + ``codegenie.*`` only).
- ``test_leaf_protocol_typecheck.py`` — AC-6 / AC-6a subprocess-mypy meta-test
  (the five negative call shapes + the conforming-stub positive control).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codegenie.fallback.leaf.port import LeafLlm, LeafResponse
from codegenie.fallback.plan_proposal import PlanProposalRefuse
from codegenie.types.identifiers import LeafResponseId, ModelId, TokenCount


def _valid_kwargs() -> dict[str, object]:
    """Fully-populated, valid ``LeafResponse`` kwargs.

    Every negative test mutates exactly one key off this baseline so each
    assertion isolates one rule. ``test_leaf_response_baseline_is_valid`` guards
    the baseline itself — if it ever breaks, every other test in this module
    starts passing for the wrong reason.

    ``reason="out_of_scope"`` is one of the three valid ``PlanProposalRefuse``
    literals (hardened S1-02 AC-3); ``"UNSAFE_BUMP"`` (a draft pre-validation
    value) would itself raise and obscure the test that uses this baseline.
    """
    return {
        "plan": PlanProposalRefuse(reason="out_of_scope", rationale="test"),
        "tokens_in": TokenCount(100),
        "cache_read_tokens": TokenCount(0),
        "cache_creation_tokens": TokenCount(50),
        "tokens_out": TokenCount(200),
        "model": ModelId("claude-sonnet-4-5-20250929"),
        "stop_reason": "end_turn",
        "response_id": LeafResponseId("msg_01abc"),
    }


def test_leaf_response_baseline_is_valid() -> None:
    """Positive control: every negative test below mutates one key off this baseline."""
    resp = LeafResponse(**_valid_kwargs())
    assert resp.tokens_in == 100
    assert resp.model == "claude-sonnet-4-5-20250929"
    assert resp.stop_reason == "end_turn"


def test_leaf_response_is_frozen() -> None:
    """AC-8 (immutability half) — ``frozen=True`` rejects assignment."""
    resp = LeafResponse(**_valid_kwargs())
    with pytest.raises(ValidationError):
        resp.tokens_in = TokenCount(0)  # type: ignore[misc]


def test_leaf_response_forbids_extra() -> None:
    """AC-3 (``extra="forbid"``) — surprise keys rejected.

    The baseline is fully valid so the ONLY violation is the extra key; the
    ``ValidationError`` can therefore only come from the ``extra="forbid"`` rule
    (the original draft test passed only ``plan`` + ``extra``, which failed for
    seven missing required fields and could not isolate extra-forbid).
    """
    with pytest.raises(ValidationError, match="[Ee]xtra"):
        LeafResponse(**_valid_kwargs(), surprise="not-allowed")  # type: ignore[call-arg]


def test_leaf_llm_protocol_is_not_runtime_checkable() -> None:
    """AC-5 — ``LeafLlm`` is not ``runtime_checkable`` (default for ``Protocol``).

    Mirrors the Phase-2 newtype-isinstance pin: ``isinstance(_, LeafLlm)``
    raises ``TypeError`` because no ``@runtime_checkable`` decorator was
    applied.
    """
    with pytest.raises(TypeError):
        isinstance(object(), LeafLlm)  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    ["tokens_in", "cache_read_tokens", "cache_creation_tokens", "tokens_out"],
)
def test_leaf_response_negative_tokens_rejected(field: str) -> None:
    """AC-7 — ``Field(ge=0)`` on each of the four token-count fields rejects ``-1``.

    The rejection comes from the Pydantic ``Field(ge=0)`` constraint declared
    in ``LeafResponse``, **not** from the ``TokenCount`` NewType (a NewType
    carries no runtime validation; Pydantic v2 resolves it to its ``int``
    supertype and applies no check). The parametrize sweeps all four token
    fields so a missing ``Field(ge=0)`` on any single field is caught.
    """
    kwargs = _valid_kwargs()
    kwargs[field] = TokenCount(-1)
    with pytest.raises(ValidationError):
        LeafResponse(**kwargs)


def test_leaf_response_equality_is_structural() -> None:
    """AC-8 (equality half) — byte-identical-field instances compare ``==``.

    The S6-07 determinism property test consumes this equality invariant.
    ``LeafResponse`` is intentionally NOT hashable — ``plan`` may be a
    ``PlanProposalCallsiteRewrite`` whose ``files: list[...]`` field makes
    ``hash()`` raise — so this test pins structural ``==``, not ``hash()``.
    """
    a = LeafResponse(**_valid_kwargs())
    b = LeafResponse(**_valid_kwargs())
    assert a == b


def test_leaf_response_inequality_on_single_field_diff() -> None:
    """AC-8 — differing in any single field yields ``!=``."""
    a = LeafResponse(**_valid_kwargs())
    diff_kwargs = _valid_kwargs()
    diff_kwargs["tokens_in"] = TokenCount(999)
    b = LeafResponse(**diff_kwargs)
    assert a != b


def test_port_module_exposes_exactly_two_public_names() -> None:
    """AC-1 — ``port.__all__`` is exact (``LeafLlm``, ``LeafResponse``)."""
    from codegenie.fallback.leaf import port

    assert tuple(sorted(port.__all__)) == ("LeafLlm", "LeafResponse")


def test_leaf_subpackage_reexports_match_port() -> None:
    """AC-1 — ``codegenie.fallback.leaf`` re-exports the two public names."""
    from codegenie.fallback import leaf

    assert leaf.LeafLlm is __import__("codegenie.fallback.leaf.port", fromlist=["LeafLlm"]).LeafLlm
    assert (
        leaf.LeafResponse
        is __import__("codegenie.fallback.leaf.port", fromlist=["LeafResponse"]).LeafResponse
    )
