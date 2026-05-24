"""Phase 4 S1-02 — schema-totality property tests for ``PlanProposal``."""

from __future__ import annotations

import json

from pydantic import TypeAdapter

from codegenie.fallback.plan_proposal import PlanProposal


def test_schema_round_trips_through_json() -> None:
    schema = TypeAdapter(PlanProposal).json_schema()
    assert json.loads(json.dumps(schema)) == schema


def test_schema_lists_exactly_four_tags() -> None:
    schema = TypeAdapter(PlanProposal).json_schema()
    mapping = schema.get("discriminator", {}).get("mapping", {})
    assert set(mapping) == {"dep_bump", "override", "callsite_rewrite", "refuse"}, (
        f"discriminator mapping must be exactly the four tags; got {set(mapping)}"
    )


def test_schema_is_sdk_shaped() -> None:
    schema = TypeAdapter(PlanProposal).json_schema()
    assert isinstance(schema, dict)
    assert "discriminator" in schema and "mapping" in schema["discriminator"]
    assert "$defs" in schema or "oneOf" in schema
    # No Pydantic-internal keys may leak into an SDK-bound schema.
    assert "__pydantic" not in json.dumps(schema), (
        "Pydantic-internal key leaked into the JSON schema"
    )


def test_schema_is_idempotent() -> None:
    a = TypeAdapter(PlanProposal).json_schema()
    b = TypeAdapter(PlanProposal).json_schema()
    assert a == b
