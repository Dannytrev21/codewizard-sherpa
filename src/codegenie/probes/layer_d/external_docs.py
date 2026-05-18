"""``ExternalDocsProbe`` — Layer D, light heaviness, deferred-implementation stub.

Phase 2 ships the skip-cleanly stub; the opted-in schema lands when
the first real user opts in (final-design.md Open Q 4).

The probe is registered so it runs in every gather and emits a typed
:class:`NotOptedInExternalDocsSlice` with ``opted_in=False,
reason="not_opted_in"`` and ``confidence="high"`` — the
absence-is-the-data precedent from S6-01: the probe successfully
*determined* that the feature is not opted in; the slice carries the
state and the confidence reports the quality of the determination. The
probe performs no I/O beyond writing a single canonical raw artifact to
``ctx.output_dir / "external_docs.json"``; no network calls, no
configuration-surface reads.

Eventual tagged union: the Phase-4+ opted-in variant lands as a *new*
sibling Pydantic model, joined under
``Annotated[<...> | <...>, Field(discriminator="opted_in")]`` and
dispatched via ``match`` inside ``run`` — never via subclass.
Composition over inheritance; Open/Closed at the file boundary.

When a future user wants an external-docs integration:

1. ADR-amend on the ``external_docs:`` allowlist schema (host list +
   credential plumbing + size cap).
2. ADR-amend on Phase 0's ``fence`` job to permit an HTTP client.
3. Add a new sibling slice model; widen the public slice type to the
   tagged union (no edits to :class:`NotOptedInExternalDocsSlice`).
4. Implement the opted-in branch as a ``match`` arm in ``run``.

NONE of those four steps happens in Phase 2. This module is
deliberately inert.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/final-design.md`` Open Q 4.
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Open questions deferred to implementation" #4.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0007-no-plugin-loader-in-phase-2.md``
  — canonical "ship the boundary, defer the implementation" precedent.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0003-coordinator-heaviness-sort-annotation.md``
  — ``heaviness`` is a ``@register_probe(heaviness=...)`` kwarg.
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

__all__ = ["ExternalDocsProbe", "NotOptedInExternalDocsSlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("external_docs")


class NotOptedInExternalDocsSlice(BaseModel):
    """Phase-2 closed shape — the not-opted-in variant of the eventual
    tagged union.

    ``opted_in: Literal[False]`` is load-bearing: it IS the discriminator
    key for the future tagged union that will join this model with its
    opted-in sibling via ``Field(discriminator="opted_in")``. Relaxing
    to ``bool`` would silently admit an opted-in slice before ``run``
    knows how to produce one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    opted_in: Literal[False]
    reason: Literal["not_opted_in"]


@register_probe(heaviness="light")
class ExternalDocsProbe(Probe):
    """Null Object for Phase 2 — satisfies the :class:`Probe` ABC so the
    coordinator, renderer, and Planner consume it without special-casing.
    See the module docstring for the deferred-implementation contract.
    """

    name: str = str(_PROBE_ID)
    version: str = "0.1.0"
    layer: Literal["D"] = "D"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = []
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        slice_ = NotOptedInExternalDocsSlice(opted_in=False, reason="not_opted_in")
        payload = slice_.model_dump(mode="json")

        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = ctx.output_dir / "external_docs.json"
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
