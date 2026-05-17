"""``ScenarioResult`` — typed outcome of one ``RuntimeTraceProbe`` scenario.

``RuntimeTraceProbe`` (S5-02) executes up to 5 scenarios per gather
(``startup``, ``smoke_test``, ``healthcheck``, ``shutdown``,
``error_path`` per ``High-level-impl.md §165``). Each scenario can
complete with an artifact, fail (timeout / docker-build error /
strace-unavailable / image-digest-unresolved), or be skipped (no
Dockerfile / image-build unavailable). The macOS path is **permanent**:
on any non-Linux host the probe emits ``TraceScenarioFailed(reason=
StraceUnavailable())`` — never a string error.

Variant set (closed; extension is ADR-amendment-gated per
``02-ADR-0006 §Consequences``, NOT registry-by-addition):

- ``TraceScenarioCompleted`` — scenario ran; artifact path + counters.
- ``TraceScenarioFailed(reason: TraceFailureReason)`` — typed failure.
- ``TraceScenarioSkipped(reason: TraceSkipReason)`` — typed skip.

The two inner ``reason`` types (``TraceFailureReason`` / ``TraceSkipReason``)
are themselves discriminated unions because S5-05 (runtime-trace freshness
+ drift) and S8-01 (renderer) ``match`` on them. The exhaustiveness
discipline is rehearsed at every level of the sum (see
``tests/unit/probes/layer_c/test_scenario_result.py``).

Producer/consumer ``assert_never`` ladder:

- **Producer:** this module is the producer (no consumer in this story;
  S5-02 is the first).
- **Consumers:** S5-02 (``RuntimeTraceProbe``), S5-05 (freshness check),
  S8-01 (renderer). Every consumer's ``match`` ladder must
  ``assert_never`` on the otherwise branch.

``scenario_name`` is a raw ``str`` for now; S1-05 is the canonical
newtype kernel and may promote it to ``NewType("ScenarioName", str)``
once cross-module usage is concrete (today it is one boundary). Resisting
newtype creep here per Rule 2.

The validation-bypass pydantic ctor is banned under this module by
``scripts/check_forbidden_patterns.py`` (S5-01 extension to S1-11's
ban) — use ``Model(...)`` / ``Model.model_validate(...)`` so the smart-
constructor invariants are honored.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S5-01-scenario-scanner-outcome-types.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #6, §"Data model", §"Edge cases" rows 2/3/5/6.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``
  — sum-type discipline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Inner sum — TraceFailureReason (TraceScenarioFailed.reason).
# ---------------------------------------------------------------------------


class StraceUnavailable(BaseModel):
    """Emitted on any non-Linux host (the macOS / Windows / other path is
    permanent — final-design.md §"Where security/best-practices traded off
    perf"). Carries no payload — the failure is structural."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["strace_unavailable"] = "strace_unavailable"


class DockerBuildFailed(BaseModel):
    """Emitted when ``docker build`` itself fails before the scenario can
    run. ``stderr_tail`` carries the trailing bytes of stderr for
    diagnostic surfacing."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["docker_build_failed"] = "docker_build_failed"
    stderr_tail: str


class ScenarioTimeout(BaseModel):
    """Emitted when the scenario exceeded the per-scenario wall-clock
    budget. ``elapsed_ms`` is what was observed before the kill (>= the
    budget)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["scenario_timeout"] = "scenario_timeout"
    elapsed_ms: int


class ImageDigestUnresolved(BaseModel):
    """Emitted when the upstream ``image_digest_resolver`` (S1-09) could not
    pin the image reference to a digest (e.g., registry unreachable).
    ``ref`` is the raw image reference that failed to resolve."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["image_digest_unresolved"] = "image_digest_unresolved"
    ref: str


TraceFailureReason = Annotated[
    StraceUnavailable | DockerBuildFailed | ScenarioTimeout | ImageDigestUnresolved,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Inner sum — TraceSkipReason (TraceScenarioSkipped.reason).
# ---------------------------------------------------------------------------


class NoDockerfile(BaseModel):
    """Emitted when no ``Dockerfile`` is present in the analyzed repo; the
    runtime-trace family is image-shaped and silently skipping it without a
    typed reason would erode the honest-confidence commitment."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["no_dockerfile"] = "no_dockerfile"


class ImageBuildUnavailable(BaseModel):
    """Emitted when the local environment cannot build images (``docker``
    binary missing, daemon unreachable, etc.) — distinct from
    ``DockerBuildFailed`` which means the build attempt itself ran but
    failed."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["image_build_unavailable"] = "image_build_unavailable"


TraceSkipReason = Annotated[
    NoDockerfile | ImageBuildUnavailable,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Top-level sum — ScenarioResult.
# ---------------------------------------------------------------------------


class TraceScenarioCompleted(BaseModel):
    """The scenario ran; ``artifact_uri`` is the on-disk path to the trace
    artifact (a JSON / pickle blob the consumer reads lazily), and the four
    counters are summary statistics surfaced in the Confidence section
    (S8-01)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["completed"] = "completed"
    scenario_name: str
    artifact_uri: Path
    wall_clock_ms: int
    syscalls_observed: int
    shared_libs_count: int


class TraceScenarioFailed(BaseModel):
    """The scenario failed; ``reason`` carries the typed why."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["failed"] = "failed"
    scenario_name: str
    reason: TraceFailureReason


class TraceScenarioSkipped(BaseModel):
    """The scenario was skipped without attempting to run; ``reason``
    carries the typed why."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["skipped"] = "skipped"
    scenario_name: str
    reason: TraceSkipReason


ScenarioResult = Annotated[
    TraceScenarioCompleted | TraceScenarioFailed | TraceScenarioSkipped,
    Field(discriminator="kind"),
]


__all__ = [
    "DockerBuildFailed",
    "ImageBuildUnavailable",
    "ImageDigestUnresolved",
    "NoDockerfile",
    "ScenarioResult",
    "ScenarioTimeout",
    "StraceUnavailable",
    "TraceFailureReason",
    "TraceScenarioCompleted",
    "TraceScenarioFailed",
    "TraceScenarioSkipped",
    "TraceSkipReason",
]
