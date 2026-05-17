"""``codegenie.probes.layer_c`` — runtime + container probes.

Phase 2 lands the pure-typing kernel here (:mod:`scenario_result`); the
``RuntimeTraceProbe`` consumer ships in S5-02 and the marker-shape
probes ship in S5-03 / S5-04. No probe consumes ``ScenarioResult`` in
this story.

See ``docs/phases/02-context-gather-layers-b-g/stories/S5-01-scenario-scanner-outcome-types.md``
for the architectural rationale.
"""

from codegenie.probes.layer_c.scenario_result import (
    DockerBuildFailed,
    ImageBuildUnavailable,
    ImageDigestUnresolved,
    NoDockerfile,
    ScenarioResult,
    ScenarioTimeout,
    StraceUnavailable,
    TraceFailureReason,
    TraceScenarioCompleted,
    TraceScenarioFailed,
    TraceScenarioSkipped,
    TraceSkipReason,
)

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
