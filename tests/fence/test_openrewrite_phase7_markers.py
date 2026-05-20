"""AC-CI-3 fence — the Phase-7 capability-widening marker is present.

S5-01's ``RecipeEngine.apply`` signature pins ``capability:
NpmInstallCapability`` (the Phase-3-narrow type). OpenRewrite is not npm; the
scaffold accepts the parameter only to satisfy the Protocol shape and pins a
``# TODO(Phase-7): widen capability union`` marker at the signature site.
Phase 7's first PR widens S5-01's Protocol and deletes this marker + this
fence. Removing the marker without the Phase-7 ADR amendment is a contract
break — this fence catches it.
"""

from __future__ import annotations

from pathlib import Path

_ENGINE_SOURCE = Path(__file__).resolve().parents[2] / (
    "src/codegenie/transforms/engines/openrewrite.py"
)
_MARKER = "TODO(Phase-7): widen capability union"


def test_capability_widening_todo_marker_present() -> None:
    """AC-CI-3 — the ``# TODO(Phase-7): widen capability union`` marker is
    present in ``openrewrite.py`` until Phase 7 widens the capability union."""
    source = _ENGINE_SOURCE.read_text("utf-8")
    assert _MARKER in source, (
        "Phase-3 marker must be present until Phase 7 widens RecipeEngine.apply "
        "to accept a capability sum. Deleting this marker without the Phase-7 "
        "ADR amendment is a contract break."
    )
