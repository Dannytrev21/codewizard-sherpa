"""``codegenie.probes.layer_c`` — runtime + container probes.

Phase 2 lands the pure-typing kernel (:mod:`scenario_result`) in S5-01
and the canonical :class:`RuntimeTraceProbe` consumer in S5-02. The
marker-shape probes ship in S5-03 / S5-04.

See ``docs/phases/02-context-gather-layers-b-g/stories/S5-02-runtime-trace-probe.md``
for the probe's architectural rationale; S5-01 holds the sum-type
discipline.
"""

from codegenie.probes.layer_c.certificate import CertificateProbe
from codegenie.probes.layer_c.dockerfile import DockerfileProbe
from codegenie.probes.layer_c.entrypoint import EntrypointProbe
from codegenie.probes.layer_c.runtime_trace import RuntimeTraceProbe
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
from codegenie.probes.layer_c.shell_usage import ShellUsageProbe

__all__ = [
    "CertificateProbe",
    "DockerBuildFailed",
    "DockerfileProbe",
    "EntrypointProbe",
    "ImageBuildUnavailable",
    "ImageDigestUnresolved",
    "NoDockerfile",
    "RuntimeTraceProbe",
    "ScenarioResult",
    "ScenarioTimeout",
    "ShellUsageProbe",
    "StraceUnavailable",
    "TraceFailureReason",
    "TraceScenarioCompleted",
    "TraceScenarioFailed",
    "TraceScenarioSkipped",
    "TraceSkipReason",
]
