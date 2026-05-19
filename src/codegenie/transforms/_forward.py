"""Phase-3-Step-1 forward-reference shim — S1-04 / S4-04 / S4-05 substitutions.

This module is the one-way ``codegenie.transforms.* → codegenie.transforms._forward``
import surface for the two Step-1 contract types that are *eventually* owned
by their real homes:

* :class:`SandboxedPath` — S4-04 substituted the Step-1 ``TypeAlias`` with a
  re-export of :class:`codegenie.plugins.sandbox_path.SandboxedPath`.
* :class:`CapabilityBundle` — S4-05 substituted the empty Step-1 stub with a
  re-export of :class:`codegenie.plugins.capabilities.CapabilityBundle`.

Both substitutions are **extension-by-addition** — every consumer keeps
importing from ``codegenie.transforms._forward`` (or the top-level
``codegenie.transforms``) and the import path stays stable. The widening is
additive: new fields, no removals, no ``model_rebuild`` dance at substitution
time.

The direction is one-way: ``codegenie.transforms.* → codegenie.transforms._forward``
import is allowed; the inverse (``plugins.* → transforms``) is forbidden.
S4-04 admitted ``codegenie.plugins.sandbox_path``; S4-05 admits
``codegenie.plugins.capabilities`` — both fenced by
:mod:`tests.fence.test_transforms_module_purity` (the ``_FORWARD_ALLOWED``
set names both modules; the reverse purity fence
:mod:`tests.fence.test_plugins_sandbox_path_purity` keeps the inverse closed).
"""

from __future__ import annotations

from codegenie.plugins.capabilities import CapabilityBundle
from codegenie.plugins.sandbox_path import SandboxedPath

__all__ = ["CapabilityBundle", "SandboxedPath"]
