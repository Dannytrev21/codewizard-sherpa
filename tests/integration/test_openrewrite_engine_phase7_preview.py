"""AC-Phase7-1 — ``OpenRewriteRecipeEngine`` end-to-end under a real JVM.

This is the Phase-7-preview integration test: it runs the scaffolded engine
against the ``dockerfile-base-image-swap`` fixture under a *real*
:class:`SubprocessJail` adapter with a *real* ``java`` on PATH, and asserts
the produced :class:`DockerfileBaseImageTransform`'s ``diff_bytes`` byte-equals
the committed ``expected.diff`` golden.

It is marked ``@pytest.mark.phase_7_preview`` — the default Phase-3
``addopts`` (``-m "not bench and not phase_7_preview"``) **deselects** it, so
it never runs in Phase-3 CI; ``pytest -m phase_7_preview`` opts it in. The
``skipif(shutil.which("java") is None)`` guard is defence-in-depth.

Phase-7 deferral (mirrors S5-02's AC-Gold-1): the test *infrastructure*
ships now — the marker, the skip guards, the fixture, the ``expected.diff``
golden — but a green run additionally needs Phase 7's authored OpenRewrite
recipe content + a provisioned ``rewrite-cli.jar`` (the fixture's
``recipe.yml`` is a placeholder; ``/opt/openrewrite/rewrite-cli.jar`` is not
provisioned in Phase 3 — ADR-0009 §Consequences). Phase 7 flips this marker
to a per-PR-required mark.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from codegenie.plugins.capabilities import NpmInstallCapability
from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.engines.openrewrite import (
    DockerfileBaseImageTransform,
    OpenRewriteRecipeEngine,
)
from codegenie.transforms.outcomes import ApplicationPlan, Applied
from codegenie.transforms.sandbox.bwrap import BwrapAdapter
from codegenie.transforms.transform_registry import TransformRegistry
from codegenie.types.identifiers import PluginId, RegistryUrl

_FIXTURE = Path(__file__).resolve().parents[1] / ("fixtures/openrewrite/dockerfile-base-image-swap")


@pytest.mark.phase_7_preview
@pytest.mark.skipif(shutil.which("java") is None, reason="requires java on PATH")
async def test_dockerfile_base_image_swap_under_real_jvm(tmp_path: Path) -> None:
    """AC-Phase7-1 — under a real ``BwrapAdapter`` + real JVM the engine
    returns ``Applied`` and the produced transform's ``diff_bytes``
    byte-equals the committed golden."""
    if sys.platform != "linux":
        pytest.skip("macOS path requires a future sandbox-exec OpenRewrite policy")

    for name in ("Dockerfile", "expected.Dockerfile", "recipe.yml"):
        (tmp_path / name).write_bytes((_FIXTURE / name).read_bytes())

    engine = OpenRewriteRecipeEngine(
        jail=BwrapAdapter(),
        transform_registry=(registry := TransformRegistry()),
    )
    outcome = await engine.apply(
        SandboxedPath(absolute=tmp_path),
        ApplicationPlan(summary="dockerfile-base-image-swap"),
        NpmInstallCapability(
            registry=RegistryUrl("https://registry.npmjs.org"),
            minted_by=PluginId("vuln-node-npm"),
        ),
    )
    assert isinstance(outcome, Applied)
    transform = registry.get(outcome.transform_id)
    assert isinstance(transform, DockerfileBaseImageTransform)
    assert transform.diff_bytes == (_FIXTURE / "expected.diff").read_bytes()
