"""Phase 4 S1-03 — happy/sad paths + discriminator-mapping totality over PlanOutcome.

Mirrors the HARDENED S1-02 ``test_plan_proposal.py`` style: route-by-discriminator
roundtrips (F7: every input field must survive), JSON identity roundtrip (F8),
discriminator-mapping strict-set totality (F9 / AC-11), and the closed sad-paths
from AC-4 (unknown ``kind``, ``extra="forbid"``, ``frozen=True``,
``Refused.reason`` literal, optional-vs-required ``few_shot_ref``).
"""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.fallback.plan_outcome import (
    AppliedFromLlm,
    AppliedFromRecipe,
    PlanOutcome,
    RagOnlyApplicable,
    Refused,
)

GOOD_DIGEST = "a" * 64
GOOD_SEX_ID = "b" * 64
GOOD_RESP_ID = "msg_01ABCDEFGHIJKLMNOPQRSTUV"

VALID_RECIPE: dict[str, object] = {
    "kind": "recipe",
    "recipe_outcome_digest": GOOD_DIGEST,
}
VALID_LLM: dict[str, object] = {
    "kind": "llm",
    "recipe_outcome_digest": GOOD_DIGEST,
    "few_shot_ref": GOOD_SEX_ID,
    "response_id": GOOD_RESP_ID,
}
VALID_RAG: dict[str, object] = {"kind": "rag_only", "few_shot_ref": GOOD_SEX_ID}
VALID_REFUSED: dict[str, object] = {"kind": "refused", "reason": "PROVENANCE_NOT_APP_LAYER"}


@pytest.mark.parametrize(
    "payload,cls",
    [
        (VALID_RECIPE, AppliedFromRecipe),
        (VALID_LLM, AppliedFromLlm),
        (VALID_RAG, RagOnlyApplicable),
        (VALID_REFUSED, Refused),
    ],
)
def test_discriminator_routes_and_preserves_every_field(
    payload: dict[str, object], cls: type[object]
) -> None:
    """F7 — assert the routed class AND that every input field survived.

    An impl that routes correctly but drops or defaults a field (e.g., a
    silently-dropped ``few_shot_ref``) must fail here, not just an
    ``isinstance`` check.
    """
    out = TypeAdapter(PlanOutcome).validate_python(payload)
    assert isinstance(out, cls)
    for key, value in payload.items():
        assert getattr(out, key) == value, f"field {key!r} not preserved on {cls.__name__}"


@pytest.mark.parametrize("payload", [VALID_RECIPE, VALID_LLM, VALID_RAG, VALID_REFUSED])
def test_json_round_trip_identity(payload: dict[str, object]) -> None:
    """F8 — every variant survives a ``model_dump`` → JSON → ``validate`` cycle.

    Catches asymmetric serializer/deserializer bugs that the
    ``test_discriminator_routes_*`` parametrize would silently miss.
    """
    adapter = TypeAdapter(PlanOutcome)
    obj = adapter.validate_python(payload)
    serialized = json.dumps(obj.model_dump(mode="json"))
    again = adapter.validate_python(json.loads(serialized))
    assert again == obj


def test_discriminator_mapping_is_exactly_four_tags() -> None:
    """F9 / AC-11 — strict set equality on the JSON-schema discriminator map.

    No ``len(...) == 4`` escape hatch — four wrong tags, or four canonical
    plus a smuggled fifth, must fail. Fast runtime guard complementary to the
    slower subprocess-mypy meta-test.
    """
    schema = TypeAdapter(PlanOutcome).json_schema()
    mapping = schema.get("discriminator", {}).get("mapping", {})
    assert set(mapping) == {"recipe", "llm", "rag_only", "refused"}, (
        f"discriminator mapping must be exactly the four tags; got {set(mapping)}"
    )


def test_unknown_kind_rejected() -> None:
    adapter = TypeAdapter(PlanOutcome)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "applied_from_void"})


def test_extra_keys_rejected_by_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        AppliedFromRecipe.model_validate({**VALID_RECIPE, "shell": "rm"})


def test_frozen_rejects_assignment() -> None:
    m = AppliedFromLlm.model_validate(VALID_LLM)
    with pytest.raises(ValidationError):
        m.response_id = "other"  # type: ignore[misc]


def test_refused_reason_outside_literal_rejected() -> None:
    with pytest.raises(ValidationError):
        Refused.model_validate({"kind": "refused", "reason": "NOT_IN_THE_LITERAL"})


def test_few_shot_ref_optional_on_llm_variant() -> None:
    m = AppliedFromLlm.model_validate({**VALID_LLM, "few_shot_ref": None})
    assert m.few_shot_ref is None


def test_few_shot_ref_required_on_rag_only_variant() -> None:
    with pytest.raises(ValidationError):
        RagOnlyApplicable.model_validate({"kind": "rag_only"})


def test_kind_default_omittable_in_direct_construction() -> None:
    """AC-1 / F10 — each ``kind`` carries a default matching its tag; direct
    construction can omit ``kind=`` and still get the right discriminator
    value (mirrors S1-02's ``plan_proposal.py``)."""
    assert AppliedFromRecipe(recipe_outcome_digest=GOOD_DIGEST).kind == "recipe"
    assert RagOnlyApplicable(few_shot_ref=GOOD_SEX_ID).kind == "rag_only"
    assert Refused(reason="LEAF_REFUSED").kind == "refused"
