"""``SloStubProbe`` — Layer E, light heaviness, deferred stub.

The real SLO catalog (per-provider SLO definitions, error budgets,
on-call schedules) is deferred to Phase 9 or later. Phase 2 ships a
registered stub that emits a typed :class:`NotOptedInSloSlice` with
``opted_in=False, reason="phase_9_or_later"`` and ``confidence="high"``
— absence is the data (S6-04 ``NotOptedInExternalDocsSlice`` precedent).

Discriminator key for the eventual tagged union: ``discriminator="opted_in"``.
The Phase-9+ opted-in variant lands as a *new* sibling Pydantic model
(``OptedInSloSlice``) joined under
``Annotated[NotOptedInSloSlice | OptedInSloSlice,
Field(discriminator="opted_in")]``, dispatched via ``match`` on
``repo.config.get("slo")`` inside ``run`` — never via subclass.
Composition over inheritance; Open/Closed at the file boundary.

NONE of the Phase-9 opted-in logic ships in Phase 2.
"""

from __future__ import annotations

import json
import os
import time
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["NotOptedInSloSlice", "SloStubProbe"]

_PROBE_ID: Final[ProbeId] = ProbeId("slo")


class NotOptedInSloSlice(BaseModel):
    """Phase-2 closed shape — not-opted-in variant of the eventual
    ``Annotated[NotOptedInSloSlice | OptedInSloSlice,
    Field(discriminator="opted_in")]`` tagged union."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    opted_in: Literal[False]
    reason: Literal["phase_9_or_later"]


@register_probe(heaviness="light")
class SloStubProbe(Probe):
    """Null Object for Phase 2 — satisfies the :class:`Probe` ABC so the
    coordinator, renderer, and Planner consume it without special-casing.
    See the module docstring for the deferred-implementation contract.
    """

    name: str = str(_PROBE_ID)
    version: str = "0.1.0"
    layer: Literal["E"] = "E"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = []
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        slice_ = NotOptedInSloSlice(opted_in=False, reason="phase_9_or_later")
        payload = slice_.model_dump(mode="json")

        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = ctx.output_dir / "slo.json"
        tmp_path = out_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, sort_keys=True, indent=2))
        os.replace(tmp_path, out_path)

        return ProbeOutput(
            schema_slice=payload,
            raw_artifacts=[out_path],
            confidence="high",
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
