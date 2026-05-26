"""Phase-4 S6-08 — ``AttemptAnchor`` joined per-attempt audit record.

The single record carrying ``(plan_proposal, retrieved_evidence_chain_head,
validator_outcome, trust_outcome, prompt_digest, response_digest, cost)`` per
fallback attempt. Persisted as one JSONL line at
``.codegenie/fallback/anchors/{utc-date}/{workflow_id}.jsonl`` and emitted as
the terminal ``AttemptAnchorRecorded`` event of S6-01's per-step tape.

Phase-4 ADR-04-0017 §Decision is the schema spec; AC-SCHEMA-1 clarifies that
the five LLM-call-derived fields (``prompt_digest_blake3``,
``response_digest_blake3``, ``tokens_in``, ``tokens_out``, ``cost_usd``) are
``Optional`` in ``schema_version=1`` because early-refusal paths
(``PROVENANCE_NOT_APP_LAYER``, ``BUDGET_EXCEEDED``) short-circuit before any
prompt is built — this is consistent with the ADR's "anchor emission is
unconditional" Consequence, not a schema bump.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from codegenie.types.identifiers import (
    AttemptId,
    ChainHead,
    CveId,
    PromptDigest,
    ResponseDigest,
    SolvedExampleId,
    WorkflowId,
)

__all__ = ["AttemptAnchor", "EXTRAS_KEY_REGEX"]


# Namespaced ``extras`` keys — phase prefix with no zero-padding. Pinning the
# format here prevents the silent-drift bug where one phase writes ``phase7.x``
# and another writes ``phase07.x``.
EXTRAS_KEY_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^phase(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))?\.[a-z][a-z0-9_]*$"
)


# Plan-proposal discriminator literal — MUST match the four
# :data:`~codegenie.fallback.plan_proposal.PlanProposal` discriminated-union
# tags exactly. Fence test ``tests/fence/test_attempt_anchor_plan_kind_matches_proposal.py``
# AST-walks the proposal union and asserts set equality.
_PLAN_PROPOSAL_KINDS = Literal["dep_bump", "override", "callsite_rewrite", "refuse"]

# Validator-outcome discriminator — mirrors :data:`PlanOutcome`'s four ``kind``
# tags (``recipe`` / ``llm`` / ``rag_only`` / ``refused``).
_VALIDATOR_OUTCOMES = Literal["AppliedFromRecipe", "AppliedFromLlm", "RagOnlyApplicable", "Refused"]

# Closed-set refusal reason mirrors :class:`~codegenie.fallback.plan_outcome.Refused.reason`.
_REFUSAL_REASONS = Literal[
    "PROVENANCE_NOT_APP_LAYER",
    "BUDGET_EXCEEDED",
    "LEAF_REFUSED",
    "LEAF_SCHEMA_VIOLATION",
]


# ``MappingProxyType[str, str]`` evaluates as a generic at runtime via
# ``types.MappingProxyType[str, str]`` only on Python 3.9+; for Pydantic field
# typing we accept ``Mapping[str, str]`` and freeze through a validator.
class AttemptAnchor(BaseModel):
    """Joined per-attempt audit record — ADR-04-0017 §Decision.

    Schema-versioned (``schema_version=1``) and ``extra="forbid"``-locked: a
    future field addition demands an ADR amendment + a co-existence release
    cycle test (`tests/integration/test_attempt_anchor_v1_v2_coexist.py`) and
    a schema_version bump.

    Two write sites, one writer: refusal anchors are written inside
    :meth:`FallbackTier.run`; success anchors are written by the deferred
    ``on_validated`` hook after :meth:`attach_trust_outcome`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    attempt_id: AttemptId
    workflow_id: WorkflowId
    cve_id: CveId
    timestamp_utc: datetime
    attempt_index: int = Field(ge=0)

    # Joined fields — the load-bearing tuple.
    plan_proposal_kind: _PLAN_PROPOSAL_KINDS
    validator_outcome: _VALIDATOR_OUTCOMES
    refusal_reason: _REFUSAL_REASONS | None = None
    retrieved_evidence_chain_head: ChainHead | None = None
    retrieved_record_ids: tuple[SolvedExampleId, ...] = ()

    # Trust-outcome fields — populated by :meth:`attach_trust_outcome` after
    # Phase 5's ``GateRunner`` finishes (success path only). ``None`` on
    # refusal anchors and on in-flight success anchors awaiting attach.
    trust_outcome_passed: bool | None = None
    trust_outcome_confidence: Literal["low", "medium", "high"] | None = None

    # LLM-call-derived fields — ``Optional`` because early-refusal paths
    # (``PROVENANCE_NOT_APP_LAYER``, ``BUDGET_EXCEEDED``) short-circuit before
    # any prompt is built (AC-SCHEMA-1).
    prompt_digest_blake3: PromptDigest | None = None
    response_digest_blake3: ResponseDigest | None = None
    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = None

    extras: dict[str, str] = Field(default_factory=dict)

    # ---- Validators ------------------------------------------------------

    @field_validator("timestamp_utc")
    @classmethod
    def _tz_aware_utc(cls, value: datetime) -> datetime:
        """AC-SCHEMA-2: reject naive datetimes — UTC awareness required."""
        if value.tzinfo is None:
            raise ValueError("timestamp_utc must be tz-aware UTC; got a naive datetime")
        return value

    @field_validator("extras")
    @classmethod
    def _validate_extras_keys(cls, value: dict[str, str]) -> dict[str, str]:
        """AC-EXTRAS-1: keys must match ``^phase\\d+(?:\\.\\d+)?\\.[a-z][a-z0-9_]*$``."""
        for key in value:
            if not EXTRAS_KEY_REGEX.fullmatch(key):
                raise ValueError(
                    f"extras key {key!r} does not match the phase-namespace "
                    f"regex {EXTRAS_KEY_REGEX.pattern!r}; keys must be of the "
                    f"form 'phaseN[.M].snake_case_name' (no zero-padding)."
                )
        return value

    @model_validator(mode="after")
    def _freeze_extras(self) -> AttemptAnchor:
        """AC-SCHEMA-4: freeze ``extras`` so post-construction mutation
        raises ``TypeError`` — pinned by the immutability test."""
        # Pydantic ``frozen=True`` prevents reassigning ``self.extras``, but
        # the default ``dict`` is itself still mutable. Replace it with a
        # ``MappingProxyType`` via ``object.__setattr__`` so the runtime
        # instance is unmodifiable. mypy sees ``extras: dict[str, str]`` and
        # cannot know the runtime swap is intentional — silenced narrowly.
        if not isinstance(self.extras, MappingProxyType):  # type: ignore[unreachable]
            object.__setattr__(self, "extras", MappingProxyType(dict(self.extras)))
        return self

    @model_validator(mode="after")
    def _validator_outcome_vs_refusal_reason(self) -> AttemptAnchor:
        """Cross-field consistency: ``refusal_reason`` is set iff
        ``validator_outcome == "Refused"``."""
        if self.validator_outcome == "Refused" and self.refusal_reason is None:
            raise ValueError("refusal_reason must be set when validator_outcome == 'Refused'")
        if self.validator_outcome != "Refused" and self.refusal_reason is not None:
            raise ValueError("refusal_reason must be None when validator_outcome != 'Refused'")
        return self

    @field_serializer("cost_usd", when_used="json")
    def _serialize_cost_usd(self, value: Decimal | None) -> str | None:
        """AC-SCHEMA-3: serialize ``Decimal`` as a JSON *string* (not float).

        Portfolio-scale fan-in of float-encoded cents drifts under cumulative
        arithmetic; the JSONL projection must round-trip Decimal exactly.
        """
        if value is None:
            return None
        return str(value)

    @field_serializer("extras", when_used="json")
    def _serialize_extras(self, value: Any) -> dict[str, str]:
        """``MappingProxyType`` is not JSON-serializable directly — coerce to
        a plain ``dict`` for JSON output (round-trip parsing rebuilds it)."""
        return dict(value)

    # ---- Public API ------------------------------------------------------

    def attach_trust_outcome(self, trust_outcome: Any) -> AttemptAnchor:
        """Return a new instance with ``trust_outcome_passed`` +
        ``trust_outcome_confidence`` populated from ``trust_outcome``.

        AC-ATTACH-1: the receiver is **not** mutated.
        AC-ATTACH-2: double-attach raises ``ValueError("trust_outcome
        already attached")``.
        AC-ATTACH-3: attaching to a ``Refused`` anchor raises ``ValueError``.

        ``trust_outcome`` is typed ``Any`` to avoid the cross-package import
        of :class:`codegenie.transforms.outcomes.TrustOutcome` from this
        kernel-tier module; the runtime contract is that it carries
        ``.passed: bool`` and ``.confidence: Literal["low","medium","high"]``.
        """
        if self.trust_outcome_passed is not None:
            raise ValueError("trust_outcome already attached")
        if self.validator_outcome == "Refused":
            raise ValueError("cannot attach trust_outcome to a Refused anchor")
        return self.model_copy(
            update={
                "trust_outcome_passed": bool(trust_outcome.passed),
                "trust_outcome_confidence": cast(
                    Literal["low", "medium", "high"], trust_outcome.confidence
                ),
            }
        )
