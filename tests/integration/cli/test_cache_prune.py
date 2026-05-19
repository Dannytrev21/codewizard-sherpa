"""S3-05 — ``codegenie cache prune`` integration tests.

Covers AC-42..AC-46 — sibling-of-stub registration, ``--help`` exit
zero, exactly-one event in both populated + empty cases, JSON-lines
emission to the interim spanning-stream substrate, and a regression
on the preserved Phase-1+ ``cache gc`` stub.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import structlog
from click.testing import CliRunner

from codegenie.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.mark.parametrize("seed_stale", [True, False])
def test_cache_prune_emits_exactly_one_event(
    tmp_path: Path,
    runner: CliRunner,
    capture_spanning_events,
    seed_stale: bool,
) -> None:
    """AC-44 — exactly-one event in both populated and empty cache cases."""
    cache_dir = tmp_path / "cache"
    bundles = cache_dir / "bundles"
    bundles.mkdir(parents=True)
    if seed_stale:
        stale = bundles / ("a" * 64 + ".json")
        stale.write_text('{"x":1}')
        os.utime(stale, (time.time() - 10 * 86_400,) * 2)
    result = runner.invoke(cli, ["cache", "prune", "--cache-dir", str(cache_dir)])
    assert result.exit_code == 0, result.output
    events = capture_spanning_events(cache_dir)
    assert len(events) == 1, "exactly-one-event invariant holds for empty cache too"
    ev = events[0]
    assert ev.event_type == "cache_gc_completed"
    assert ev.trigger == "operator_cli"
    if seed_stale:
        assert ev.entries_evicted == 1 and ev.bytes_reclaimed > 0
    else:
        assert ev.entries_evicted == 0 and ev.bytes_reclaimed == 0


def test_cache_prune_help_exit_zero(runner: CliRunner) -> None:
    """AC-43 — ``--help`` exits 0 and mentions the flag."""
    result = runner.invoke(cli, ["cache", "prune", "--help"])
    assert result.exit_code == 0
    assert "--cache-dir" in result.output


def test_cache_prune_event_file_mode_0600(
    tmp_path: Path,
    runner: CliRunner,
) -> None:
    """AC-45 — append.jsonl created with 0o600 file mode."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    result = runner.invoke(cli, ["cache", "prune", "--cache-dir", str(cache_dir)])
    assert result.exit_code == 0
    jl = cache_dir.parent / "events" / "spanning" / "append.jsonl"
    assert jl.exists()
    assert jl.stat().st_mode & 0o777 == 0o600


def test_cache_gc_stub_preserved(runner: CliRunner) -> None:
    """AC-42 — Phase-1+ migration contract: ``cache gc`` stub still logs."""
    log_events: list[dict] = []
    with structlog.testing.capture_logs() as logs:
        result = runner.invoke(cli, ["cache", "gc"])
        log_events.extend(logs)
    assert result.exit_code == 0
    assert any(ev.get("event") == "cache.gc.stub" for ev in log_events), (
        f"expected cache.gc.stub in captured events; got: {log_events}"
    )
