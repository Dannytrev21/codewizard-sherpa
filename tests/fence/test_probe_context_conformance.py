"""Fence — runtime structural conformance of coordinator-built ctx to
:class:`codegenie.probes.base.ProbeContext`.

The frozen Phase 0 ADR-0007 probe contract (``ProbeContext``) declares the
attribute surface every probe is allowed to read at runtime. The coordinator
hands probes a different concrete class — :class:`codegenie.coordinator.budget.BudgetingContext` —
constructed via :func:`codegenie.coordinator.coordinator._make_probe_context`.
Python's structural duck-typing erases the mismatch at call sites
(``await probe.run(snap, ctx)`` typechecks because ``probe.run`` accepts
``ProbeContext`` but only fails if a *missing* attribute is actually read at
runtime — which never happens in unit tests because they construct
``ProbeContext`` directly).

This fence asserts every attribute declared on ``ProbeContext`` is also
readable on the concrete ctx the coordinator builds. Adding a new attribute
to ``ProbeContext`` without updating ``BudgetingContext`` in lockstep fires
this fence at CI time.

Discovered 2026-05-19 after a five-attribute drift (``output_dir`` /
``cache_dir`` / ``logger`` / ``config`` / ``image_digest_resolver``)
surfaced as three probes silently AttributeError'ing at runtime
(``scip_index``, ``tree_sitter_import_graph``, ``slo``). The actual fix
lives in a separate task; this fence catches future drift of the shape.

Mirrors the introspection idiom of ``test_plugin_protocol_frozen.py``
(dir + ``__annotations__`` union over the public surface).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from codegenie.coordinator.coordinator import _make_probe_context
from codegenie.probes.base import ProbeContext


def _probe_context_attribute_names() -> frozenset[str]:
    """Public attribute names declared on the frozen :class:`ProbeContext`
    dataclass — every one must be readable on whatever the coordinator
    actually passes to ``probe.run``."""
    return frozenset(f.name for f in dataclasses.fields(ProbeContext))


def test_coordinator_ctx_satisfies_probe_context_attribute_surface(tmp_path: Path) -> None:
    """Every attribute on ``ProbeContext`` is readable on the coordinator-built ctx.

    A probe's ``run(snap, ctx)`` body reads ``ctx.<name>`` for any ``<name>``
    declared on the contract. When the runtime ctx is a *different* class
    that omits an attribute, the probe AttributeError's at runtime — caught
    by coordinator failure-isolation but the probe produces no output and
    nobody notices until somebody runs gather against a repo that actually
    exercises the dead code path.

    This assertion is the structural fence: pin the coordinator-built ctx
    to the frozen ``ProbeContext`` surface.
    """
    ctx = _make_probe_context(workspace=tmp_path, raw_artifact_mb=10)
    declared = _probe_context_attribute_names()
    missing = {name for name in declared if not hasattr(ctx, name)}
    assert not missing, (
        f"Coordinator-built ctx (type={type(ctx).__name__}) is missing "
        f"{sorted(missing)} declared on ProbeContext. Either widen the runtime "
        f"ctx to carry the attribute, or amend ADR-0007 to drop it from the "
        f"contract — never let the runtime silently diverge."
    )
