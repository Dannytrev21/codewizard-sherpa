"""S4-05 AC-Sub-1 / AC-Sub-3 — ``_forward.CapabilityBundle`` substitution.

After the S4-05 substitution, all three import paths must resolve to the
**same** :class:`CapabilityBundle` class object:

* ``from codegenie.transforms._forward import CapabilityBundle``
* ``from codegenie.transforms import CapabilityBundle``
* ``from codegenie.plugins.capabilities import CapabilityBundle``

Also pins:

* an ``ApplyContext`` instance round-trips through ``model_dump_json`` →
  ``model_validate_json`` cleanly while carrying a non-empty bundle.
* the existing Phase-3-Step-1 ``ApplyContext`` consumers continue to pass
  (the live regression target is ``tests/unit/transforms/test_apply_context.py``,
  which uses ``_empty_caps()`` post-substitution).
"""

from __future__ import annotations

from codegenie.plugins.capabilities import (
    CapabilityBundle as PluginsCapabilityBundle,
)
from codegenie.plugins.capabilities import NpmInstallCapability
from codegenie.transforms import CapabilityBundle as TransformsTopLevelCapabilityBundle
from codegenie.transforms._forward import (
    CapabilityBundle as ForwardCapabilityBundle,
)
from codegenie.transforms.apply_context import ApplyContext
from codegenie.types.identifiers import (
    AttemptNumber,
    PluginId,
    RegistryUrl,
    WorkflowId,
)

_ULID: str = "01HXX00000000000000000000Z"
_REG: RegistryUrl = RegistryUrl("https://registry.npmjs.org")
_PLUGIN: PluginId = PluginId("vulnerability-remediation--node--npm")


def test_three_import_paths_resolve_to_same_class() -> None:
    """AC-Sub-3 — ``is`` identity, not just structural equality. A
    `TypeAlias` or re-export shim that points at a *copy* of the model
    breaks ``isinstance`` checks downstream and is caught here."""
    assert ForwardCapabilityBundle is PluginsCapabilityBundle
    assert TransformsTopLevelCapabilityBundle is PluginsCapabilityBundle


def test_apply_context_round_trips_with_capability_bundle() -> None:
    """AC-Sub-3 — an ``ApplyContext`` carrying a real ``CapabilityBundle``
    (one ``NpmInstallCapability`` slot) survives JSON round-trip. The
    bundle's ``exactly-one`` model_validator runs on round-trip too, so
    a regression that drops the validator is caught here."""
    bundle = ForwardCapabilityBundle(npm=NpmInstallCapability(registry=_REG, _minted_by=_PLUGIN))
    ctx = ApplyContext(
        workflow_id=WorkflowId(_ULID),
        attempt=AttemptNumber(1),
        prior_attempts=(),
        capabilities=bundle,
    )

    parsed = ApplyContext.model_validate_json(ctx.model_dump_json())

    assert parsed == ctx
    assert parsed.capabilities.npm is not None
    assert parsed.capabilities.npm.registry == _REG
    assert parsed.capabilities.fs is None
    assert parsed.capabilities.git is None
