"""``codegenie.depgraph.model`` — typed slice shape for ``DepGraphProbe``.

The model is shipped in S1-10 (this story) so the eventual
:class:`codegenie.probes.layer_b.dep_graph.DepGraphProbe` (S4-05) can import
it without circularity. Phase 2 itself does not instantiate the model — it
is the contract S4-05's probe will return when no strategy is registered
(low-confidence shape) or when an ecosystem strategy yields a graph.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S1-10-depgraph-strategy-registry.md`` (AC-1).
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md`` §"Component design" #11.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DepGraphProbeOutput(BaseModel):
    """Typed slice shape for the future ``DepGraphProbe`` (S4-05).

    Three fields: ``graph_path`` (on-disk path to the serialised
    ``networkx.node_link_data`` JSON, or ``None`` when no graph was built),
    ``confidence`` (the ADR-0007 ``"high" | "medium" | "low"`` ladder), and
    ``reason`` (free-form string when ``confidence`` is not ``"high"``).
    Frozen + ``extra=forbid`` per Phase 2 model discipline (mirrors
    :class:`codegenie.indices.freshness.IndexFreshness`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_path: Path | None
    confidence: Literal["high", "medium", "low"]
    reason: str | None = None
