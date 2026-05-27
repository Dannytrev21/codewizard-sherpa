"""Phase-4 S7-09 AC-10 — typed corpus models.

Frozen, ``extra="forbid"`` Pydantic models for the three adversarial
corpora the suite loads at test-collection time. A corrupted YAML row
(missing field, unknown extra key, wrong type) surfaces as a typed
:class:`pydantic.ValidationError` at load time — never as a ``KeyError``
mid-test. Mirrors CLAUDE.md's "no untyped ``dict`` shuffling" load-bearing
commitment + Phase-3 S8-02 + S7-06 AC-15's typed-event precedent.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class InjectionPayload(BaseModel):
    """One row of the injection-corpus YAML — exercises
    :class:`FenceWrapper` + :class:`CanaryGuard`.

    ``expected_outcome`` is the **discriminator** AC-1's parametrized
    test asserts against (vs an OR-disjunction that silently masks
    drift in a row's intent — V1 of the S2-03 lesson, replayed here).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    text: str
    source: str
    expected_outcome: Literal[
        "canary_collision",
        "fence_contains_only_via_redaction",
        "both",
    ]


class RedTeamScenario(BaseModel):
    """One row of the red-team-scenarios YAML — exercises the closed
    :class:`PlanProposal` sum type's smart-constructor rejection.

    ``payload`` is the raw LLM-shaped JSON dict;
    ``expected_rejection_keyword`` is the distinct keyword the
    :class:`pydantic.ValidationError` message MUST contain (per
    S1-02 AC-4 F9 — distinct-keyword discipline).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    variant: Literal["dep_bump", "override", "callsite_rewrite", "refuse"]
    source: str
    payload: dict[str, Any]
    expected_rejection_keyword: Literal[
        "path",
        "escape",
        "binary",
        "no-op",
        "empty",
        "64 KB",
        "exceeds",
        "unknown_kind",
        "missing",
        "invalid",
    ]


class TruncationProbe(BaseModel):
    """One row of the truncation-probes YAML — exercises
    ADR-04-0013's scan-before-truncate invariant per :data:`SourceKind`.

    ``filler_len`` MUST be strictly greater than the source-kind's
    ``_TRUNCATION_CAPS`` entry; the test harness asserts this at
    parametrize time (per S2-03 V3 byte-arithmetic hardening).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    source_kind: str  # validated against get_args(SourceKind) by the test harness
    pattern_id: str
    filler_len: int


__all__ = [
    "InjectionPayload",
    "RedTeamScenario",
    "TruncationProbe",
]
