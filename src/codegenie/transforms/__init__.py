"""``codegenie.transforms`` — Phase-3 outcome unions + ApplyContext surface.

For S1-03 this package contains exactly one module — :mod:`outcomes` —
exporting the five Pydantic discriminated unions every later Phase-3 module
dispatches on:

- :data:`RecipeOutcome` (``Applied | Skipped | RecipeNotApplicable | RecipeFailed``)
- :data:`RemediationOutcome` (``Validated | RequiresHumanReview |
  RemediationNotApplicable | RemediationFailed``)
- :data:`NodeTransition` (``Advance | ShortCircuit | Escalate``)
- :data:`AdapterConfidence` (``Trusted | Degraded | Unavailable``)
- :data:`Applicability` (``Applies | NotApplies``)

Each variant is ``frozen=True`` + ``extra="forbid"`` (ADR-0010). The
discriminated-union shape is the Phase-5 wrap surface frozen by phase-3
ADR-0001 (rename of any ``kind`` literal or umbrella alias breaks the
S6-06 contract-snapshot test).

S1-04 will add ``Transform`` ABC + ``ApplyContext`` + ``AttemptSummary``
alongside; ``transforms/`` is the package home for the whole Phase-3
contract surface.
"""

from codegenie.transforms.outcomes import (
    AdapterConfidence,
    Advance,
    Applicability,
    ApplicationPlan,
    Applied,
    Applies,
    DegradationReason,
    Degraded,
    Escalate,
    EscalationReason,
    HumanReviewReason,
    NodeTransition,
    NotApplicableReason,
    NotApplies,
    RecipeError,
    RecipeFailed,
    RecipeNotApplicable,
    RecipeOutcome,
    RemediationError,
    RemediationFailed,
    RemediationNotApplicable,
    RemediationOutcome,
    RequiresHumanReview,
    ShortCircuit,
    Skipped,
    SkipReason,
    Trusted,
    UnavailabilityReason,
    Unavailable,
    Validated,
)

__all__ = [
    "AdapterConfidence",
    "Advance",
    "Applicability",
    "Applied",
    "ApplicationPlan",
    "Applies",
    "DegradationReason",
    "Degraded",
    "Escalate",
    "EscalationReason",
    "HumanReviewReason",
    "NodeTransition",
    "NotApplicableReason",
    "NotApplies",
    "RecipeError",
    "RecipeFailed",
    "RecipeNotApplicable",
    "RecipeOutcome",
    "RemediationError",
    "RemediationFailed",
    "RemediationNotApplicable",
    "RemediationOutcome",
    "RequiresHumanReview",
    "ShortCircuit",
    "SkipReason",
    "Skipped",
    "Trusted",
    "Unavailable",
    "UnavailabilityReason",
    "Validated",
]
