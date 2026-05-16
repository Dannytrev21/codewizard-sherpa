"""Phase 2 roadmap exit criterion — `IndexHealthProbe` catches stale SCIP.

Build FAILS if `IndexHealthProbe` (B2, S4-01) does not catch the
deliberately-seeded staleness encoded in
``tests/fixtures/portfolio/stale-scip/``. See
``docs/phases/02-context-gather-layers-b-g/stories/S4-02-stale-scip-adversarial.md``.

Every assertion has a multi-line, actionable diagnostic. When this test
fails in CI months from now, the person fixing it must not need to read
the test source to understand the failure (Rule 12 — fail loud).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from logging import getLogger
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from codegenie.indices.freshness import (
    CommitsBehind,
    Fresh,  # noqa: F401 — referenced inline via TypeAdapter discriminator
    IndexFreshness,
    Stale,
)
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_b.index_health import IndexHealthProbe

pytestmark = pytest.mark.phase02_adv

# AC-10 — adversarial walltime budget (10 s). `pytest-timeout` is not on the
# Phase 0/1 dev-dep list, so the story permits a `time.perf_counter` fallback.
_BUDGET_SECONDS = 10.0

_FRESHNESS_ADAPTER: TypeAdapter[IndexFreshness] = TypeAdapter(IndexFreshness)


def _current_head(repo: Path) -> str:
    """Mirror B2's exact byte-decode path so encoding drift is impossible."""
    result = subprocess.run(  # noqa: S603 — fixture path; test-only.
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, check=True
    )
    return result.stdout.decode("utf-8").strip()


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


def test_index_health_catches_stale_scip(fixture_path: Path) -> None:
    """Roadmap exit criterion: B2 surfaces a real staleness case.

    Five assertions in order, each with its own loud diagnostic.
    """
    started = time.perf_counter()

    # AC-8 — pre-flight: git must be on PATH. NO `pytest.skip` path.
    if shutil.which("git") is None:
        pytest.fail(
            "`git` is not on $PATH; this is a developer-environment bug, not "
            "a skip condition. Install git and rerun. (Phase 0 fence job "
            "ensures git on the CI runner; if you're seeing this on CI, the "
            "fence job regressed.)"
        )
    slice_path = fixture_path / ".codegenie" / "context" / "raw" / "scip.json"
    if not fixture_path.exists() or not slice_path.exists():
        pytest.fail(
            f"stale-scip fixture missing or not regenerated. "
            f"Run `{fixture_path}/regenerate.sh`. Looked for {slice_path}."
        )

    head = _current_head(fixture_path)
    probe = IndexHealthProbe()
    out = asyncio.run(probe.run(_snapshot(fixture_path), _ctx(fixture_path)))
    index_health = out.schema_slice["index_health"]

    # AC-1 step 1 — outer-key invariant (catches singleton pollution).
    assert set(index_health.keys()) == {"scip"}, (
        f"Expected slice['index_health'].keys() == {{'scip'}}, got "
        f"{set(index_health.keys())!r}. Either the freshness registry has "
        "been polluted by a prior test (use the `clean_freshness_registry` "
        "snapshot fixture), or B2's outer-key invariant (S4-01 AC-10) "
        "regressed. See docs/phases/02-context-gather-layers-b-g/stories/"
        "S4-02-stale-scip-adversarial.md."
    )

    # AC-1 step 2 — discriminated-union round-trip (DP3 in the story).
    raw = index_health["scip"]["freshness"]
    freshness = _FRESHNESS_ADAPTER.validate_python(raw)
    assert isinstance(freshness, Stale), (
        f"Expected `Stale`, got `{type(freshness).__name__}` with value:\n"
        f"{json.dumps(raw, indent=2)}\n"
        "See docs/production/design.md §2.3 (honest confidence) — silent "
        "freshness (B2 emits Fresh against the stale-seeded fixture) is "
        "THE load-bearing failure mode this adversarial gates."
    )

    # AC-1 step 3 — reason variant pinned.
    assert isinstance(freshness.reason, CommitsBehind), (
        f"Expected `Stale(reason=CommitsBehind)`, got "
        f"`Stale(reason={type(freshness.reason).__name__})`.\n"
        f"Full freshness:\n{json.dumps(raw, indent=2)}\n"
        "If reason=IndexerError, the fixture's "
        "`.codegenie/context/raw/scip.json` may be absent or malformed — "
        "rerun `regenerate.sh`. If reason=CoverageGap or DigestMismatch, "
        "B2's `scip` freshness check (S4-01 AC-5) misclassified the "
        "staleness."
    )

    # AC-1 step 4 — BOTH inequalities (implementation risk #3).
    assert freshness.reason.n >= 1, (
        f"Expected CommitsBehind.n >= 1, got n={freshness.reason.n}. "
        f"Full freshness:\n{json.dumps(raw, indent=2)}"
    )
    assert freshness.reason.last_indexed != head, (
        f"Expected CommitsBehind.last_indexed != current HEAD, but both are "
        f"{head!r}. The fixture's seeded last_indexed_commit must be the "
        "parent commit, NOT HEAD. Did regenerate.sh's guard fail? See "
        "tests/fixtures/portfolio/stale-scip/README.md."
    )

    # AC-1 step 5 — per-source confidence demote-min wiring.
    assert index_health["scip"]["confidence"] == "medium", (
        f"Expected per-source confidence=='medium' for "
        f"`Stale(CommitsBehind(...))` (S4-01 AC-9 mapping), got "
        f"{index_health['scip']['confidence']!r}. The typed value may be "
        "correct but the flat `confidence` field wasn't re-derived — the "
        "honest-confidence demote-min mechanism regressed."
    )

    # AC-10 — walltime budget.
    elapsed = time.perf_counter() - started
    assert elapsed < _BUDGET_SECONDS, (
        f"Adversarial exceeded {_BUDGET_SECONDS}s budget ({elapsed:.2f}s). "
        "Adversarials are on the CI critical path; see S8-03's "
        "`bench_index_health_overhead` for the secondary defense."
    )
