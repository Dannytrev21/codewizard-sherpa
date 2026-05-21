"""``codegenie.transforms`` — Phase-3 outcome unions + ApplyContext surface.

This package is the Phase-3 contract-surface home (ADR-0001). It carries
three layers of public symbols:

* The five Pydantic discriminated unions from :mod:`outcomes` (S1-03):
  :data:`RecipeOutcome`, :data:`RemediationOutcome`, :data:`NodeTransition`,
  :data:`AdapterConfidence`, :data:`Applicability`.
* The Phase-5 contract surface (S1-04): :class:`Transform` ABC,
  :class:`TransformProvenance`, :class:`ApplyContext`,
  :class:`AttemptSummary`, plus the :class:`CapabilityBundle` /
  :data:`SandboxedPath` forward-reference shims that S4-04 / S4-05
  substitute additively.
* The S5-04 lockfile-policy surface (Gap 2 fix): :class:`LockfilePolicy`,
  the :data:`PolicyViolation` / :data:`PolicyLoadError` discriminated unions,
  and :class:`UnauthorizedRegistry` — from :mod:`policy.lockfile_policy`.

Every variant is ``frozen=True`` + ``extra="forbid"`` (ADR-0010).
Discriminated-union umbrellas use ``Annotated[A | B | C,
Field(discriminator="kind")]`` (single repo convention). Rename of any
``kind`` literal, umbrella alias, or contract-surface field name breaks the
S6-06 contract-snapshot test.
"""

from codegenie.transforms._forward import CapabilityBundle, SandboxedPath
from codegenie.transforms.apply_context import ApplyContext, AttemptSummary
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
from codegenie.transforms.policy.lockfile_policy import (
    LockfilePolicy,
    PolicyLoadError,
    PolicyViolation,
    UnauthorizedRegistry,
)
from codegenie.transforms.recipe_engine import (
    MatchedRecipe,
    RecipeEngine,
    RecipeProtocol,
    match_recipes,
)
from codegenie.transforms.transform import Transform, TransformProvenance

__all__ = [
    "AdapterConfidence",
    "Advance",
    "Applicability",
    "Applied",
    "ApplicationPlan",
    "Applies",
    "ApplyContext",
    "AttemptSummary",
    "CapabilityBundle",
    "DegradationReason",
    "Degraded",
    "Escalate",
    "EscalationReason",
    "HumanReviewReason",
    "LockfilePolicy",
    "MatchedRecipe",
    "NodeTransition",
    "NotApplicableReason",
    "NotApplies",
    "PolicyLoadError",
    "PolicyViolation",
    "RecipeEngine",
    "RecipeError",
    "RecipeFailed",
    "RecipeNotApplicable",
    "RecipeOutcome",
    "RecipeProtocol",
    "RemediationError",
    "RemediationFailed",
    "RemediationNotApplicable",
    "RemediationOutcome",
    "RequiresHumanReview",
    "SandboxedPath",
    "ShortCircuit",
    "SkipReason",
    "Skipped",
    "Transform",
    "TransformProvenance",
    "Trusted",
    "UnauthorizedRegistry",
    "Unavailable",
    "UnavailabilityReason",
    "Validated",
    "match_recipes",
]
