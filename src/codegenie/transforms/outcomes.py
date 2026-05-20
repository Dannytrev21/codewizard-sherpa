"""Phase-3 outcome sum types — five Pydantic discriminated unions.

Production ADR-0033 rejects booleans-for-state and ``(passed: bool,
error: str | None)``-style returns; Phase-3 ADR-0010 carries the rule into
the orchestrator, recipe engine, sandbox adapter, and subgraph-node return
surfaces. This module is the single declaration point for the five
discriminated unions every later Step-1..Step-9 module dispatches on:

- :data:`RecipeOutcome` — Phase-5 wraps via ``RecipeOutcome`` (ADR-0001
  contract). ``Applied.transform_id`` is the BLAKE3-hex lookup into the
  S1-04 ``Transform`` registry.
- :data:`RemediationOutcome` — top-level orchestrator outcome (S6-04).
  ``Validated.passed`` / ``Validated.failing`` are the flat denormalisation
  of S6-02's ``TrustOutcome``; ADR-0001 forbids rename.
- :data:`NodeTransition` — return type of every ``SubgraphNode.run``
  (S6-03). ``Advance.state`` is primitive-value-only per ADR-0010.
- :data:`AdapterConfidence` — read by ``BundleBuilder`` (S3-04) to trigger
  the deterministic serial fallback.
- :data:`Applicability` — return type of every recipe-engine ``applies``
  (S5-01); ``Applies.plan`` is the typed application plan.

Every variant is ``frozen=True`` + ``extra="forbid"`` (ADR-0010 §Consequences);
every umbrella uses ``Annotated[A | B | C, Field(discriminator="kind")]``
(repo convention — see ``codegenie/indices/freshness.py``,
``codegenie/probes/_shared/scanner_outcome.py``).

ADRs: phase-3 ADR-0010 (sum-type discipline), phase-3 ADR-0001 (Phase-5
contract-snapshot), production ADR-0033 (sum types over booleans).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from codegenie.types.identifiers import (
    BranchName,
    ErrorId,
    PackageId,
    PluginId,
    RecipeId,
    SignalKind,
    TransformId,
    TransformKind,
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

# ---------------------------------------------------------------------------
# Reason literal taxonomies (single declaration point — Phase 4+ widens
# additively; rename breaks the ADR-0001 contract snapshot).
# ---------------------------------------------------------------------------

NotApplicableReason = Literal[
    "PEER_DEP_CONFLICT",
    "MAJOR_BUMP_REFUSE",
    "OVERRIDES_AMBIGUOUS",
    "RECIPE_CATALOG_MISS",
    "ALL_RECIPES_NOT_APPLICABLE",
    "NO_RECIPES_REGISTERED",
]

SkipReason = Literal["plugin_disabled", "registry_skipped"]

EscalationReason = Literal[
    "plugin_extends_cycle",
    "manifest_rejected",
    "capability_missing",
]

HumanReviewReason = Literal[
    "no_concrete_match",
    "trust_outcome_failed",
    "policy_violation_unrecoverable",
]

DegradationReason = Literal["timeout", "partial_results", "rate_limited"]
"""Advisory catalog of orchestrator-domain degradation reasons.

NOT the type of :attr:`Degraded.reason`. The field is ``str`` by design
(amended 2026-05-18, ADR-0010 Amendment): the probe-adapter domain uses
vocabulary disjoint from the orchestrator domain
(e.g. ``"scip_unavailable"``, ``"tool_missing"``, ``"self_check"``), and a
closed Literal would reject those at construction.

Consumers in the orchestrator domain (``BundleBuilder`` S3-04) MAY
validate ``degraded.reason in get_args(DegradationReason)`` and emit a
``degraded_with_unknown_reason`` audit event for drift — that's the
intended migration ramp toward strict reasons if/when a consumer pays
for it.
"""

UnavailabilityReason = Literal["binary_missing", "io_error", "unsupported_version"]
"""Advisory catalog of orchestrator-domain unavailability reasons.

See :data:`DegradationReason` for the discipline rationale; same advisory
discipline applies to :attr:`Unavailable.reason`.
"""


# ---------------------------------------------------------------------------
# Error payloads (AC-7g) + ApplicationPlan placeholder (AC-7).
# ---------------------------------------------------------------------------

_MESSAGE_MAX_LEN = 4096


class RecipeError(BaseModel):
    """Failure payload carried by :class:`RecipeFailed`. ``error_id`` is the
    dotted snake-case error id (Phase-1 ADR-0007); ``message`` is a stable
    human-readable string capped at 4096 chars."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    error_id: ErrorId
    message: str
    details: dict[str, str | int | bool | float] | None = None

    @field_validator("message")
    @classmethod
    def _message_length(cls, v: str) -> str:
        if len(v) > _MESSAGE_MAX_LEN:
            raise ValueError(f"message exceeds {_MESSAGE_MAX_LEN} chars")
        return v


class RemediationError(BaseModel):
    """Failure payload carried by :class:`RemediationFailed`. Same shape as
    :class:`RecipeError` but a distinct type — the discriminator + Pydantic
    can't tell two structurally-identical models apart at the umbrella, but
    the field annotation on the Failed variants is type-time enforced."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    error_id: ErrorId
    message: str
    details: dict[str, str | int | bool | float] | None = None

    @field_validator("message")
    @classmethod
    def _message_length(cls, v: str) -> str:
        if len(v) > _MESSAGE_MAX_LEN:
            raise ValueError(f"message exceeds {_MESSAGE_MAX_LEN} chars")
        return v


class ApplicationPlan(BaseModel):
    """Typed application plan returned by :class:`Applies` and consumed by a
    :class:`~codegenie.transforms.recipe_engine.RecipeEngine`.

    S5-02 widens this **additively** (ADR-0010 amendment): the four optional
    npm-semver-bump fields below carry ``None`` defaults so every existing
    ``ApplicationPlan(summary=...)`` / ``ApplicationPlan()`` call site keeps
    working. Phase 4's ``LLMFallbackEngine`` widens additively again with its
    own ``for_llm_fallback(...)`` smart constructor — never edit existing
    fields (extension by addition).

    ``from_version`` / ``to_version`` are npm dependency *range specifiers*
    (e.g. ``^4.17.1``), not bare semver — caret / tilde / comparator
    operators are valid, so no semver regex is applied (the S5-02 fixture
    data ``^4.17.1`` is the canonical counter-example to a strict pin).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    summary: str | None = None
    package: PackageId | None = None
    from_version: str | None = None
    to_version: str | None = None
    transform_kind: TransformKind | None = None

    @classmethod
    def for_npm_semver_bump(
        cls,
        *,
        package: PackageId,
        from_version: str,
        to_version: str,
        transform_kind: TransformKind,
    ) -> ApplicationPlan:
        """Smart constructor — build a fully-populated npm-semver-bump plan.

        Returns a frozen plan with all four npm fields set and ``summary``
        left ``None``; this is the plan shape :class:`~codegenie.transforms
        .engines.npm_lockfile.NpmLockfileRecipeEngine` reads."""
        return cls(
            summary=None,
            package=package,
            from_version=from_version,
            to_version=to_version,
            transform_kind=transform_kind,
        )


# ---------------------------------------------------------------------------
# RecipeOutcome variants (Phase-5 wrap surface — ADR-0001 freezes shape).
# ---------------------------------------------------------------------------


class Applied(BaseModel):
    """``Applied`` — produced by a recipe engine on a successful transform
    apply. ``transform_id`` is the BLAKE3-hex digest of the applied diff
    (S1-04 ``Transform.transform_id`` is the lookup key)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["applied"] = "applied"
    transform_id: TransformId
    plugin_id: PluginId
    recipe_id: RecipeId


class Skipped(BaseModel):
    """``Skipped`` — plugin pre-``applies()`` hook declines to even evaluate.
    Phase 3 reserves this variant for Phase 4+ plugins; the NpmLockfileRecipe
    never emits ``Skipped`` in normal flow."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["skipped"] = "skipped"
    reason: SkipReason
    plugin_id: PluginId


class RecipeNotApplicable(BaseModel):
    """``RecipeNotApplicable`` — recipe ``applies()`` returned ``NotApplies``;
    no transform can be produced. ``reason`` is the same Literal alias as
    :class:`RemediationNotApplicable.reason` (single source of truth).

    ``considered`` (S5-01 additive) carries the per-recipe ``NotApplies``
    trace produced by the :func:`codegenie.transforms.recipe_engine.match_recipes`
    walker when every recipe declines. Phase-4's prompt builder reads this
    structured trace; Phase-5 callers reading only ``.reason`` continue to
    work via the empty-list default. ADR-0001 §Consequences row 6 names the
    Phase-5 contract-snapshot regeneration triggered by this widening.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["not_applicable"] = "not_applicable"
    reason: NotApplicableReason
    considered: list[NotApplies] = Field(default_factory=list)


class RecipeFailed(BaseModel):
    """``RecipeFailed`` — recipe execution raised. ``error`` is a structured
    :class:`RecipeError`, not a free-form string."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["failed"] = "failed"
    error: RecipeError


RecipeOutcome = Annotated[
    Applied | Skipped | RecipeNotApplicable | RecipeFailed,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# RemediationOutcome variants (orchestrator-outer-loop — ADR-0001 freezes).
# ---------------------------------------------------------------------------


class Validated(BaseModel):
    """``Validated`` — orchestrator finished a remediation cycle and the
    sandbox + trust scorer produced a verdict. ``passed`` / ``failing`` are
    the flat denormalisation of S6-02's ``TrustOutcome``; S6-02 widens
    additively (ADR-0001 forbids rename). ``report_path`` is ``str`` in
    Phase 3 — S4-01 widens to ``SandboxedPath`` via a ``field_validator``."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["validated"] = "validated"
    branch: BranchName
    report_path: str
    passed: bool
    failing: list[SignalKind]

    @model_validator(mode="after")
    def _passed_iff_no_failing(self) -> Validated:
        if self.passed != (len(self.failing) == 0):
            raise ValueError("Validated invariant violated: passed must equal (failing == [])")
        return self


class RequiresHumanReview(BaseModel):
    """``RequiresHumanReview`` — universal-fallback exhausted. ``reason``
    pins the why; ``handoff_path`` is the path to the human-readable handoff
    artifact (``None`` if the orchestrator failed before allocating it)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["requires_human_review"] = "requires_human_review"
    reason: HumanReviewReason
    handoff_path: str | None = None


class RemediationNotApplicable(BaseModel):
    """``RemediationNotApplicable`` — every plugin's recipe catalog declined
    (all recipes returned ``NotApplies``). Distinct class from
    :class:`RecipeNotApplicable` (different umbrella) but shares the
    ``reason`` Literal — see AC-8g identity test."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["not_applicable"] = "not_applicable"
    reason: NotApplicableReason


class RemediationFailed(BaseModel):
    """``RemediationFailed`` — orchestrator caught an unrecoverable error.
    ``partial_report_path`` is ``None`` if failure occurred before the
    report path was allocated; the orchestrator writes a partial
    ``remediation-report.yaml`` whenever the path exists (arch line 452)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["failed"] = "failed"
    error: RemediationError
    partial_report_path: str | None = None


RemediationOutcome = Annotated[
    Validated | RequiresHumanReview | RemediationNotApplicable | RemediationFailed,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# NodeTransition variants (S6-03 SubgraphNode return contract).
#
# Arch line 1154 example shows ``ShortCircuit(outcome: RecipeOutcome)`` — that
# is a documentation typo. The orchestrator short-circuits at the *workflow*
# level (``RemediationOutcome.Failed`` / ``NotApplicable``), not the recipe
# level. Arch §Edge cases line 899-904 confirms; S6-03's implementation
# tracks this surface verbatim.
# ---------------------------------------------------------------------------


class Advance(BaseModel):
    """``Advance`` — node finished and the next node should run. ``state`` is
    a small flat dict of primitive values; richer state must use a new
    typed payload model (ADR-0010 forbids ``dict[str, Any]`` under
    ``transforms/``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["advance"] = "advance"
    state: dict[str, str | int | bool | float]


class ShortCircuit(BaseModel):
    """``ShortCircuit`` — node decided the outer-loop orchestrator should
    stop and emit ``outcome`` directly. ``outcome`` is a fully-formed
    :data:`RemediationOutcome`."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["short_circuit"] = "short_circuit"
    outcome: RemediationOutcome


class Escalate(BaseModel):
    """``Escalate`` — node hit a precondition violation that the workflow
    can't recover from (e.g., plugin manifest rejected). The orchestrator
    promotes the workflow to ``RequiresHumanReview``."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["escalate"] = "escalate"
    reason: EscalationReason


NodeTransition = Annotated[
    Advance | ShortCircuit | Escalate,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# AdapterConfidence variants (S3-04 BundleBuilder serial-fallback trigger).
# ---------------------------------------------------------------------------


class Trusted(BaseModel):
    """``Trusted`` — the adapter ran and the result is consumable as-is.

    Canonical declaration. ``codegenie.adapters.confidence`` re-exports this
    name (ADR-0010 Amendment 2026-05-18) — both Phase 2 adapter Protocols
    and Phase 3 ``BundleBuilder`` dispatch on the same class object.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["trusted"] = "trusted"


class Degraded(BaseModel):
    """``Degraded`` — adapter completed but with reduced confidence (timeout,
    partial results, rate-limit, stale index, etc.). Downstream may still
    consume but should mark its own confidence as ``degraded``.

    ``reason`` is ``str`` by design (ADR-0010 Amendment 2026-05-18). The
    probe-adapter domain (Phase 2) uses vocabulary disjoint from the
    orchestrator domain (Phase 3) — see :data:`DegradationReason` docstring
    for the advisory-catalog discipline.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["degraded"] = "degraded"
    reason: str


class Unavailable(BaseModel):
    """``Unavailable`` — adapter could not run (binary missing, I/O error,
    unsupported version, etc.). ``BundleBuilder`` triggers the deterministic
    serial fallback.

    ``reason`` is ``str`` by design (ADR-0010 Amendment 2026-05-18); see
    :data:`UnavailabilityReason` docstring.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["unavailable"] = "unavailable"
    reason: str


AdapterConfidence = Annotated[
    Trusted | Degraded | Unavailable,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Applicability variants (S5-01 recipe-engine ``applies()`` return type).
# ---------------------------------------------------------------------------


class Applies(BaseModel):
    """``Applies`` — recipe can run; ``plan`` is the typed application plan
    the engine will execute."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["applies"] = "applies"
    plan: ApplicationPlan


class NotApplies(BaseModel):
    """``NotApplies`` — recipe declines. ``reason`` is the same Literal alias
    used by :class:`RecipeNotApplicable` / :class:`RemediationNotApplicable`
    so the orchestrator can pass the reason through the umbrella without
    re-mapping."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["not_applies"] = "not_applies"
    reason: NotApplicableReason


Applicability = Annotated[
    Applies | NotApplies,
    Field(discriminator="kind"),
]
