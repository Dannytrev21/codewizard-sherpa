"""S4-02 AC-9 — adversarial does NOT silently pass under an empty registry.

If the freshness registry is somehow empty (e.g., a future test forgets to
re-register `scip`), B2 emits `slice == {}` (S4-01 AC-11). The adversarial's
AC-1 step 1 (`set(slice.keys()) == {"scip"}`) then fails — `set() == {"scip"}`
is False. Pinning that with a unit test is the anti-false-pass guard for the
closed-world property the adversarial depends on.
"""

from __future__ import annotations

import asyncio
from logging import getLogger
from pathlib import Path
from typing import Any

import pytest

from codegenie.indices.registry import default_freshness_registry
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_b.index_health import IndexHealthProbe

FIXTURE = Path(__file__).parent.parent.parent.parent / "fixtures" / "portfolio" / "stale-scip"


@pytest.fixture
def clean_freshness_registry() -> Any:
    """Snapshot + restore the singleton freshness registry around each test.

    Matches the pattern from S4-01's TDD preamble — `_clear_for_tests()` is
    phantom; we mutate the dicts directly inside the try/finally.
    """
    saved_checks = dict(default_freshness_registry._checks)
    saved_origins = dict(default_freshness_registry._origins)
    default_freshness_registry._checks.clear()
    default_freshness_registry._origins.clear()
    try:
        yield default_freshness_registry
    finally:
        default_freshness_registry._checks.clear()
        default_freshness_registry._origins.clear()
        default_freshness_registry._checks.update(saved_checks)
        default_freshness_registry._origins.update(saved_origins)


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})


def _ctx(root: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=root / ".cache",
        output_dir=root / ".codegenie" / "context",
        workspace=root / ".ws",
        logger=getLogger("test"),
        config={},
    )


def test_empty_registry_fails_adversarial(
    clean_freshness_registry: Any,  # noqa: ARG001 — fixture by side effect
) -> None:
    """With no checks registered, B2 emits `{}` — and `{} != {"scip"}`.

    This proves the adversarial's AC-1 step 1 is not silently satisfied
    when the registry is empty (regression: a future contributor disables
    the scip check, the adversarial would otherwise pass for the wrong
    reason).
    """
    if (
        not FIXTURE.exists()
        or not (FIXTURE / ".codegenie" / "context" / "raw" / "scip.json").exists()
    ):
        pytest.fail(f"stale-scip fixture not regenerated; run {FIXTURE}/regenerate.sh")

    probe = IndexHealthProbe()
    out = asyncio.run(probe.run(_snapshot(FIXTURE), _ctx(FIXTURE)))
    index_health = out.schema_slice["index_health"]

    # Closed-world: registry is empty, slice has zero per-source entries.
    assert index_health == {}, (
        f"Expected empty index_health under empty registry, got {index_health!r}"
    )

    # The adversarial's AC-1 step 1 expression reduces to False under
    # this condition — confirming we don't silently pass.
    assert set(index_health.keys()) != {"scip"}, (
        "AC-1 step 1 must NOT be satisfied under empty registry — otherwise "
        "the adversarial silently passes for the wrong reason."
    )
