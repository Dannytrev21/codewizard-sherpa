"""Phase-3-Step-1 forward-reference shim — S1-04 AC-5 / AC-5a / AC-5b.

``CapabilityBundle`` and ``SandboxedPath`` are *eventually* owned by their
respective S4-05 / S4-04 modules. Until those stories land, this shim is the
single import site every Step-1 contract-surface module reaches for. The
direction is strictly one-way: ``codegenie.transforms.*`` modules import
``codegenie.transforms._forward``, never the inverse — there is no
``codegenie.plugins.*`` import here.

When S4-04 / S4-05 land:

* S4-04 — Replace the ``SandboxedPath`` ``TypeAlias`` with a re-export of
  ``codegenie.plugins.sandbox_path.SandboxedPath``. Every consumer keeps
  importing from ``codegenie.transforms``; the import path stays stable.
* S4-05 — Move ``CapabilityBundle`` to ``codegenie.plugins.capabilities``
  and re-export from this module. The class itself widens *additively*:
  new fields, no removals, no ``model_rebuild`` dance at substitution time.

Both transitions are extension-by-addition. The Phase-3-Step-1 shape is
``class CapabilityBundle(BaseModel): pass`` plus ``model_config`` —
intentionally empty, intentionally frozen / extra-forbid. ADR-0011 frames
this as honest-framing: Phase 3 does not pretend to have a real sandboxed
path until S4-04 ships ``O_NOFOLLOW``.

Module imports are limited to ``{__future__, pathlib, typing, pydantic}`` —
fenced by ``tests/fence/test_transforms_module_purity.py``.
"""

from __future__ import annotations

import pathlib
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict

__all__ = ["CapabilityBundle", "SandboxedPath"]


SandboxedPath: TypeAlias = pathlib.Path
"""Phase-3-Step-1 alias for :class:`pathlib.Path`.

Substituted by S4-04 with a re-export of
``codegenie.plugins.sandbox_path.SandboxedPath`` (which carries the
``O_NOFOLLOW`` jail check). Every consumer keeps importing
``SandboxedPath`` from ``codegenie.transforms`` — the import path is
stable across the substitution.
"""


class CapabilityBundle(BaseModel):
    """Empty Pydantic shell for the S4-05 capability surface.

    Body is intentionally ``pass`` — S4-05 *adds* fields by extension; there
    is no ``_placeholder`` flag to remove later (V-D-F1 closure). Carrying
    ``frozen=True`` and ``extra="forbid"`` now means S4-05 inherits a
    hardened parent: every future field gets validated through the same
    smart-constructor boundary.

    Phase 4's ``LLMProducedTransform`` will continue to receive a
    ``CapabilityBundle`` instance; the contract surface does not change.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
