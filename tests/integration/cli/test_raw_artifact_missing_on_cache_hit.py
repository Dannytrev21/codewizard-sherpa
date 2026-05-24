"""Capability-shakedown finding (2026-05-24) — silent raw-artifact loss on cache hit.

Reproduces and pins the fix: when a cached probe output's
``raw_artifacts`` path no longer exists on disk (e.g. the operator
manually cleared ``.codegenie/context/`` while preserving the cache),
``cli.py`` previously silently skipped the artifact. This test asserts
that a structured ``probe.raw_artifact.missing_on_cache_hit`` event is
emitted instead — Rule 12, fail loud.

Why this matters
----------------
The user-visible promise (``CLAUDE.md`` — *"JSON for raw probe outputs
under ``.codegenie/context/raw/``"*) silently degrades on cache hit when
intermediate probe-staging files are missing. Without this event the
operator has no way to detect the partial materialization from logs;
the only signal is a manual ``ls .codegenie/context/raw/ | wc -l``.

Test shape
----------
1. Cold gather against ``minimal-ts`` — populates cache + raw artifacts.
2. Delete ``.codegenie/_probe_raw/`` and ``.codegenie/context/raw/`` —
   simulates the "I cleared outputs" operator action.
3. Warm gather — every probe hits cache; raw_path files are gone.
4. Assert at least one ``probe.raw_artifact.missing_on_cache_hit`` event
   was emitted with the contracted payload shape.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import CliRunner
from structlog.testing import capture_logs


def _seed_minimal_ts(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "fixtures" / "portfolio" / "minimal-ts"
    dst = tmp_path / "minimal-ts"
    shutil.copytree(src, dst)
    return dst


def _invoke(fixture: Path) -> tuple[object, list[dict[str, object]]]:
    from codegenie.cli import cli

    with capture_logs() as captured:
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])
    return result, list(captured)


def test_warm_run_with_missing_raw_paths_emits_missing_event(tmp_path: Path) -> None:
    """Cache-hit run whose source raw_path is gone emits a fail-loud event.

    Kills mutant: cli.py raw-artifact loop silently skips a non-existent
    ``raw_path`` and therefore produces an empty ``raw/`` dir on warm runs.
    """
    fixture = _seed_minimal_ts(tmp_path)

    # 1. Cold run to populate cache + raw artifacts.
    cold_result, _cold_logs = _invoke(fixture)
    assert cold_result.exit_code == 0, cold_result.output

    cg_root = fixture / ".codegenie"
    probe_raw_dir = cg_root / "_probe_raw"
    context_raw_dir = cg_root / "context" / "raw"
    # Sanity: the cold run materialized at least one raw artifact source.
    cold_raw_count = (len(list(probe_raw_dir.iterdir())) if probe_raw_dir.is_dir() else 0) + (
        len(list(context_raw_dir.iterdir())) if context_raw_dir.is_dir() else 0
    )
    assert cold_raw_count > 0, "cold run produced no raw artifacts to lose"

    # 2. Simulate operator clearing outputs while cache stays warm.
    #    This mirrors the capability-shakedown reproduction step.
    if probe_raw_dir.is_dir():
        shutil.rmtree(probe_raw_dir)
    if context_raw_dir.is_dir():
        shutil.rmtree(context_raw_dir)

    # 3. Warm run — every probe hits cache; raw_path files no longer exist.
    warm_result, warm_logs = _invoke(fixture)
    assert warm_result.exit_code == 0, warm_result.output

    # 4. The fail-loud event was emitted for at least one missing path.
    missing_events = [
        e for e in warm_logs if e.get("event") == "probe.raw_artifact.missing_on_cache_hit"
    ]
    assert missing_events, (
        "expected at least one probe.raw_artifact.missing_on_cache_hit event on "
        "a cache-warm run whose raw-source paths were deleted; got events: "
        f"{[e.get('event') for e in warm_logs]}"
    )

    # Contracted payload keys — probe name + path so an operator can grep.
    envelope_keys = {"timestamp", "level", "log_level", "logger", "run_id"}
    ev = missing_events[0]
    payload_keys = set(ev.keys()) - envelope_keys
    assert {"event", "probe", "path"}.issubset(payload_keys), (
        f"missing-event payload must carry probe + path; got {payload_keys}"
    )
