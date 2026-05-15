"""``codegenie.tccm`` — Task-Class Context Manifest schema and loader.

A Task-Class Context Manifest (TCCM, production ADR-0029) declares what
evidence a task class needs: required probes, required skills, derived
graph-aware queries (the five ADR-0030 primitives translated by phase-arch
line 721 to ``ConsumersOf | ProducersOf | ReverseLookup | RefsTo |
TestsExercising``), and a confidence floor. Phase 2 ships the schema +
loader; Phase 8 ships the Bundle Builder that consumes them. The Phase-2
exercise is the reference TCCM at ``docs/phases/02-context-gather-layers-b-g/_reference-tccm/``
(S2-03), which proves the schema is shaped right before any plugin ships in
Phase 3.

Three modules:

- :mod:`codegenie.tccm.queries` — five ``DerivedQuery`` variants + the
  discriminated-union alias. Pure typing.
- :mod:`codegenie.tccm.model` — ``TCCM`` Pydantic model. Pure typing.
- :mod:`codegenie.tccm.loader` — ``TCCMLoader.load(path) -> Result[...]``.
  The one impure module; routes every file read through
  :func:`codegenie.parsers.safe_yaml.load`.

The discriminator strings (``"consumers_of"``, ``"producers_of"``,
``"reverse_lookup"``, ``"refs_to"``, ``"tests_exercising"``) are a
cross-ADR / cross-phase contract — Phase 3 plugin renderers, golden files
and the operator-facing TCCM YAML all read these literal values.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/ADRs/0007-no-plugin-loader-in-phase-2.md``
  (02-ADR-0007) — Phase 2 ships the TCCM schema; Phase 3 ships the loader's
  first real consumer (a plugin's ``plugin.yaml`` → TCCM).
- ``docs/production/adrs/0029-task-class-context-manifests.md`` (ADR-0029) —
  the manifest's purpose.
- ``docs/production/adrs/0030-graph-aware-context-queries.md`` (ADR-0030) —
  graph-aware derived queries.
"""

from __future__ import annotations

# Note: TCCMLoadError lives in codegenie.errors per markers-only convention,
# but is re-exported here so consumers can ``from codegenie.tccm import
# TCCMLoadError`` alongside the loader they catch it from.
from codegenie.errors import TCCMLoadError
from codegenie.tccm.loader import TCCMLoader
from codegenie.tccm.model import TCCM
from codegenie.tccm.queries import (
    ConsumersOf,
    DerivedQuery,
    ProducersOf,
    RefsTo,
    ReverseLookup,
    TestsExercising,
)

__all__ = [
    "ConsumersOf",
    "DerivedQuery",
    "ProducersOf",
    "RefsTo",
    "ReverseLookup",
    "TCCM",
    "TCCMLoadError",
    "TCCMLoader",
    "TestsExercising",
]
