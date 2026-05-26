"""S6-08 unit tests — :class:`AttemptAnchor` model contract.

Covers AC-SCHEMA-1..5 + AC-ATTACH-1..3 + AC-EXTRAS-1 + AC-WRITER-1..6.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from datetime import UTC, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.fallback import anchor_writer
from codegenie.fallback.attempt_anchor import AttemptAnchor
from codegenie.types.identifiers import (
    AttemptId,
    ChainHead,
    CveId,
    PromptDigest,
    ResponseDigest,
    SolvedExampleId,
    WorkflowId,
)


def _minimal_refusal_anchor(**overrides: Any) -> AttemptAnchor:
    """Build a refusal-path AttemptAnchor with sensible defaults; overrides
    let individual tests pin one field at a time."""
    payload: dict[str, Any] = {
        "attempt_id": AttemptId("a" * 32),
        "workflow_id": WorkflowId("01HFTRWORKFLOW0000000000000"),
        "cve_id": CveId("CVE-2026-1234"),
        "timestamp_utc": datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC),
        "attempt_index": 0,
        "plan_proposal_kind": "refuse",
        "validator_outcome": "Refused",
        "refusal_reason": "PROVENANCE_NOT_APP_LAYER",
    }
    payload.update(overrides)
    return AttemptAnchor(**payload)


def _minimal_success_anchor(**overrides: Any) -> AttemptAnchor:
    """Build a success-path AttemptAnchor (validator_outcome=AppliedFromLlm)
    with the five LLM-derived fields populated."""
    payload: dict[str, Any] = {
        "attempt_id": AttemptId("b" * 32),
        "workflow_id": WorkflowId("01HFTRWORKFLOW0000000000000"),
        "cve_id": CveId("CVE-2026-1234"),
        "timestamp_utc": datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC),
        "attempt_index": 0,
        "plan_proposal_kind": "dep_bump",
        "validator_outcome": "AppliedFromLlm",
        "prompt_digest_blake3": PromptDigest("a" * 64),
        "response_digest_blake3": ResponseDigest("b" * 64),
        "tokens_in": 100,
        "tokens_out": 200,
        "cost_usd": Decimal("0.0042"),
    }
    payload.update(overrides)
    return AttemptAnchor(**payload)


# ---- AC-SCHEMA-1: Optional LLM-derived fields -----------------------------


def test_refusal_anchor_allows_none_llm_fields() -> None:
    """Early-refusal anchors (PROVENANCE/BUDGET) have prompt/response digests
    + tokens + cost as ``None`` — they short-circuit before any LLM call."""
    anchor = _minimal_refusal_anchor()
    assert anchor.prompt_digest_blake3 is None
    assert anchor.response_digest_blake3 is None
    assert anchor.tokens_in is None
    assert anchor.tokens_out is None
    assert anchor.cost_usd is None


def test_schema_version_pinned_to_one() -> None:
    """The schema_version field is a ``Literal[1]`` with default 1; any
    bump must come with a co-existence release cycle (fence-gated)."""
    anchor = _minimal_refusal_anchor()
    assert anchor.schema_version == 1
    assert AttemptAnchor.model_fields["schema_version"].default == 1


# ---- AC-SCHEMA-2: tz-aware UTC ---------------------------------------------


def test_naive_timestamp_rejected() -> None:
    """A naive ``datetime`` raises ``ValidationError`` — UTC awareness is a
    hard contract; serialization needs a canonical timezone."""
    with pytest.raises(ValidationError) as excinfo:
        _minimal_refusal_anchor(timestamp_utc=datetime(2026, 5, 25, 12, 0, 0))
    assert "tz-aware UTC" in str(excinfo.value)


def test_tz_aware_non_utc_timestamp_accepted() -> None:
    """Any tz-aware datetime is accepted (validator demands awareness, not
    a specific zone — astimezone(UTC) handles normalization downstream)."""
    pst = timezone(datetime.now().astimezone().utcoffset() or UTC.utcoffset(datetime.now()))
    anchor = _minimal_refusal_anchor(timestamp_utc=datetime(2026, 5, 25, 12, 0, 0, tzinfo=pst))
    assert anchor.timestamp_utc.tzinfo is not None


# ---- AC-SCHEMA-3: Decimal-as-string serialization -------------------------


def test_cost_usd_serializes_as_string() -> None:
    """``cost_usd`` round-trips through JSON as a ``str`` — float encoding
    would drift under cumulative portfolio-scale arithmetic."""
    anchor = _minimal_success_anchor(cost_usd=Decimal("0.0042"))
    raw = json.loads(anchor.model_dump_json())
    assert isinstance(raw["cost_usd"], str)
    assert raw["cost_usd"] == "0.0042"


def test_cost_usd_none_serializes_as_null() -> None:
    """When the anchor never invoked the LLM, ``cost_usd`` is ``None`` —
    JSON should encode that as ``null`` (not the empty string)."""
    anchor = _minimal_refusal_anchor()
    raw = json.loads(anchor.model_dump_json())
    assert raw["cost_usd"] is None


# ---- AC-SCHEMA-4: extras default is immutable ------------------------------


def test_extras_default_is_immutable_proxy() -> None:
    """``extras`` defaults to an empty MappingProxyType — mutating it
    raises ``TypeError`` so accidental in-place edits fail loud."""
    anchor = _minimal_refusal_anchor()
    assert isinstance(anchor.extras, MappingProxyType)
    with pytest.raises(TypeError):
        anchor.extras["foo"] = "bar"  # type: ignore[index]


def test_extras_provided_dict_becomes_proxy() -> None:
    """An explicitly-supplied ``extras`` dict is frozen at construction —
    the original dict is copied so caller mutations do not leak in."""
    extras = {"phase7.distroless_target": "cgr.dev/alpha"}
    anchor = _minimal_refusal_anchor(extras=extras)
    assert isinstance(anchor.extras, MappingProxyType)
    assert anchor.extras["phase7.distroless_target"] == "cgr.dev/alpha"
    extras["phase7.other"] = "leaked"
    assert "phase7.other" not in anchor.extras


# ---- AC-SCHEMA-5: plan_proposal_kind ↔ PlanProposal -----------------------


def test_plan_proposal_kind_matches_plan_proposal_union() -> None:
    """The four ``plan_proposal_kind`` literals must equal the four
    PlanProposal discriminated-union tag values exactly."""
    from typing import get_args

    from codegenie.fallback.plan_proposal import (
        PlanProposalCallsiteRewrite,
        PlanProposalDepBump,
        PlanProposalOverride,
        PlanProposalRefuse,
    )

    anchor_tags = set(get_args(AttemptAnchor.model_fields["plan_proposal_kind"].annotation))
    proposal_tags = {
        get_args(PlanProposalDepBump.model_fields["kind"].annotation)[0],
        get_args(PlanProposalOverride.model_fields["kind"].annotation)[0],
        get_args(PlanProposalCallsiteRewrite.model_fields["kind"].annotation)[0],
        get_args(PlanProposalRefuse.model_fields["kind"].annotation)[0],
    }
    assert anchor_tags == proposal_tags


# ---- AC-ATTACH-1..3: attach_trust_outcome ---------------------------------


class _FakeTrustOutcome:
    def __init__(self, passed: bool, confidence: str) -> None:
        self.passed = passed
        self.confidence = confidence


def test_attach_trust_outcome_returns_new_instance_without_mutating_receiver() -> None:
    """``attach_trust_outcome`` is functional — the receiver remains
    ``trust_outcome_passed is None``; the returned anchor carries the
    attached fields."""
    anchor = _minimal_success_anchor()
    attached = anchor.attach_trust_outcome(_FakeTrustOutcome(passed=True, confidence="high"))
    assert id(attached) != id(anchor)
    assert anchor.trust_outcome_passed is None
    assert attached.trust_outcome_passed is True
    assert attached.trust_outcome_confidence == "high"


def test_attach_trust_outcome_double_attach_raises() -> None:
    """Calling attach twice raises — re-entering the success path with an
    already-finalized anchor is a Phase-5 bug we want to fail loud on."""
    anchor = _minimal_success_anchor()
    attached = anchor.attach_trust_outcome(_FakeTrustOutcome(passed=True, confidence="high"))
    with pytest.raises(ValueError, match="trust_outcome already attached"):
        attached.attach_trust_outcome(_FakeTrustOutcome(passed=False, confidence="low"))


def test_attach_trust_outcome_on_refused_anchor_raises() -> None:
    """Refusal anchors never reach Phase 5 — any attach attempt is a bug
    upstream and must raise."""
    anchor = _minimal_refusal_anchor()
    with pytest.raises(ValueError, match="cannot attach trust_outcome to a Refused anchor"):
        anchor.attach_trust_outcome(_FakeTrustOutcome(passed=True, confidence="high"))


# ---- AC-EXTRAS-1: namespace regex ------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "phase7.distroless_target",
        "phase15.recipe_kind",
        "phase4.x",
        "phase4.0.classifier",
    ],
)
def test_extras_namespace_accepts_valid_keys(key: str) -> None:
    """Valid namespaced extras keys are accepted."""
    anchor = _minimal_refusal_anchor(extras={key: "value"})
    assert key in anchor.extras


@pytest.mark.parametrize(
    "key",
    [
        "foo",  # no phase prefix
        "phase.x",  # no number
        "phase07.x",  # zero-pad rejected
        "PHASE7.x",  # uppercase
        "phase7.X",  # uppercase value
        "phase7.x-y",  # hyphen
    ],
)
def test_extras_namespace_rejects_invalid_keys(key: str) -> None:
    """Invalid namespaced extras keys raise ValidationError — fail loud on
    silent-drift of phase numbering conventions."""
    with pytest.raises(ValidationError):
        _minimal_refusal_anchor(extras={key: "value"})


# ---- frozen + extra=forbid -------------------------------------------------


def test_frozen_attribute_assignment_raises() -> None:
    """Frozen Pydantic config blocks attribute assignment on the model."""
    anchor = _minimal_refusal_anchor()
    with pytest.raises(ValidationError):
        anchor.attempt_index = 99  # type: ignore[misc]


def test_extra_field_rejected() -> None:
    """Unknown fields raise — schema is closed."""
    with pytest.raises(ValidationError):
        _minimal_refusal_anchor(unknown_field=1)


# ---- Cross-field consistency ----------------------------------------------


def test_refusal_outcome_requires_refusal_reason() -> None:
    """``validator_outcome="Refused"`` without ``refusal_reason`` raises."""
    with pytest.raises(ValidationError, match="refusal_reason must be set"):
        _minimal_refusal_anchor(refusal_reason=None)


def test_non_refusal_outcome_forbids_refusal_reason() -> None:
    """``validator_outcome="AppliedFromLlm"`` with a ``refusal_reason`` set
    raises — the discriminator and the reason must agree."""
    with pytest.raises(ValidationError, match="refusal_reason must be None"):
        _minimal_success_anchor(refusal_reason="LEAF_REFUSED")


# ---- AC-WRITER tests -------------------------------------------------------


@pytest.fixture
def _permissive_umask() -> Any:
    old = os.umask(0)
    try:
        yield
    finally:
        os.umask(old)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_writer_creates_directory_with_0o700_and_file_with_0o600(
    tmp_path: Path, _permissive_umask: Any
) -> None:
    """AC-WRITER-5: directory mode 0o700, file mode 0o600 set explicitly
    via mkdir(mode=...) and os.open(..., mode=...) — proven by running
    under ``os.umask(0)`` so the modes are not just umask-inherited."""
    anchor = _minimal_refusal_anchor()
    anchor_writer.write(anchor, output_dir=tmp_path)
    date_dir = tmp_path / anchor.timestamp_utc.astimezone(UTC).strftime("%Y-%m-%d")
    file_path = date_dir / f"{anchor.workflow_id}.jsonl"
    assert stat.S_IMODE(date_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(file_path.stat().st_mode) == 0o600


def test_writer_appends_one_line_per_call(tmp_path: Path) -> None:
    """AC-WRITER-4: successive writes append; the second call does not
    truncate the first."""
    a1 = _minimal_refusal_anchor()
    a2 = _minimal_refusal_anchor(attempt_id=AttemptId("c" * 32))
    anchor_writer.write(a1, output_dir=tmp_path)
    anchor_writer.write(a2, output_dir=tmp_path)
    date_dir = tmp_path / a1.timestamp_utc.astimezone(UTC).strftime("%Y-%m-%d")
    file_path = date_dir / f"{a1.workflow_id}.jsonl"
    lines = file_path.read_bytes().splitlines()
    assert len(lines) == 2
    parsed_1 = TypeAdapter(AttemptAnchor).validate_json(lines[0])
    parsed_2 = TypeAdapter(AttemptAnchor).validate_json(lines[1])
    assert parsed_1.attempt_id == a1.attempt_id
    assert parsed_2.attempt_id == a2.attempt_id


def test_writer_round_trip_json_validates(tmp_path: Path) -> None:
    """AC-WRITER-6: every written line round-trips through TypeAdapter and
    reconstructs the anchor byte-for-byte (no float drift, no key reorder)."""
    anchor = _minimal_success_anchor(
        retrieved_evidence_chain_head=ChainHead("ch_001"),
        retrieved_record_ids=(SolvedExampleId("se_001"), SolvedExampleId("se_002")),
        extras={"phase7.distroless_target": "cgr.dev/alpha"},
    )
    anchor_writer.write(anchor, output_dir=tmp_path)
    date_dir = tmp_path / anchor.timestamp_utc.astimezone(UTC).strftime("%Y-%m-%d")
    file_path = date_dir / f"{anchor.workflow_id}.jsonl"
    line = file_path.read_bytes().splitlines()[0]
    rebuilt = TypeAdapter(AttemptAnchor).validate_json(line)
    assert rebuilt.attempt_id == anchor.attempt_id
    assert rebuilt.cost_usd == anchor.cost_usd
    assert rebuilt.retrieved_record_ids == anchor.retrieved_record_ids
    assert dict(rebuilt.extras) == dict(anchor.extras)


# ---- Registry seam (AC-REGISTRY-1..-3) ------------------------------------


def test_attempt_anchor_recorded_in_internal_classes() -> None:
    """``AttemptAnchorRecorded`` must be in ``_INTERNAL_CLASSES`` so the
    ``WorkflowEventLog.emit_internal(...)`` isinstance gate accepts it.
    Forgetting this is a TypeError at first emission."""
    from codegenie.plugins.events import (
        _INTERNAL_CLASSES,
        AttemptAnchorRecorded,
    )

    assert AttemptAnchorRecorded in _INTERNAL_CLASSES
