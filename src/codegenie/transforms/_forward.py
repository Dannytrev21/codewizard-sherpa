"""Phase-3-Step-1 forward-reference shim — S1-04 AC-5 / AC-5a / AC-5b
(post-S4-04 substitution).

``CapabilityBundle`` and ``SandboxedPath`` are *eventually* owned by their
respective S4-05 / S4-04 modules. Until S4-05 lands, this shim is the
single import site every Step-1 contract-surface module reaches for. The
direction is one-way: ``codegenie.transforms.*`` modules import
``codegenie.transforms._forward``; the inverse (``plugins.* → transforms``)
remains forbidden. S4-04 admitted one re-export from
``codegenie.plugins.sandbox_path`` (ADR-0001 amendment, fenced by
``tests/fence/test_transforms_module_purity.py``).

When S4-05 lands:

* S4-04 — Replaced the ``SandboxedPath`` ``TypeAlias`` with a re-export of
  ``codegenie.plugins.sandbox_path.SandboxedPath``. Every consumer keeps
  importing from ``codegenie.transforms``; the import path stays stable.
* S4-05 — Move ``CapabilityBundle`` to ``codegenie.plugins.capabilities``
  and re-export from this module. The class itself widens *additively*:
  new fields, no removals, no ``model_rebuild`` dance at substitution time.

Both transitions are extension-by-addition. The Phase-3-Step-1 shape is
``class CapabilityBundle(BaseModel): pass`` plus ``model_config`` —
intentionally empty, intentionally frozen / extra-forbid.

Module imports are limited to the allowlist
``{__future__, pathlib, typing, pydantic, codegenie.plugins.sandbox_path}``
— fenced by ``tests/fence/test_transforms_module_purity.py`` (subset
check, so pathlib/typing are admitted-but-unused after the S4-04 flip).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from codegenie.plugins.sandbox_path import SandboxedPath

__all__ = ["CapabilityBundle", "SandboxedPath"]


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
