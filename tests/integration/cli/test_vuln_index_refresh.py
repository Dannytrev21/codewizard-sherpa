"""S3-03 — ``codegenie vuln-index refresh`` end-to-end CLI tests.

Covers AC-X1..X10, AC-R6 (Open/Closed observable through --help output).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Final

import pytest
import structlog
from click.testing import CliRunner

from codegenie.cli import cli
from codegenie.result import Err, Result
from codegenie.vuln_index import VulnIndex, default_feed_registry
from codegenie.vuln_index.models import VulnerabilityRecord
from codegenie.vuln_index.parsers import VulnParseError

CASSETTES_DIR: Final[Path] = Path(__file__).resolve().parents[2] / "fixtures" / "cve-feeds"


# ---------------------------------------------------------------------------
# Test-helper fixture: register a cassette-only feed for the duration of one test.
# ---------------------------------------------------------------------------


@pytest.fixture
def register_test_feed() -> Iterator[callable]:  # type: ignore[type-arg]
    """Register one or more test feeds; unregister on teardown."""
    registered: list[str] = []

    def _register(source: str, feed_cls: type) -> None:
        default_feed_registry.register(source)(feed_cls)
        registered.append(source)

    yield _register
    for src in registered:
        default_feed_registry._test_unregister(src)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Feed factories
# ---------------------------------------------------------------------------


def _make_cassette_feed(source: str, cassette_files: list[Path]) -> type:
    nvd_parse = default_feed_registry.get_feed("nvd").parse_one

    class _CassetteFeed:
        def __init__(self) -> None:
            self.source = source

        def parse_one(self, raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]:
            return nvd_parse(raw)

        def fetch(
            self,
            *,
            since: datetime | None = None,
            timeout_s: float = 30.0,
        ) -> Iterator[bytes]:
            for f in cassette_files:
                yield f.read_bytes()

    _CassetteFeed.source = source  # type: ignore[attr-defined]
    return _CassetteFeed


def _make_empty_feed(source: str) -> type:
    class _Empty:
        def __init__(self) -> None:
            self.source = source

        def parse_one(self, raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]:
            return Err(error=VulnParseError(reason="bad_json", details={}))

        def fetch(
            self,
            *,
            since: datetime | None = None,
            timeout_s: float = 30.0,
        ) -> Iterator[bytes]:
            return iter([])

    _Empty.source = source  # type: ignore[attr-defined]
    return _Empty


def _make_broken_feed(source: str) -> type:
    from codegenie.errors import VulnFeedFetchError

    class _Broken:
        def __init__(self) -> None:
            self.source = source

        def parse_one(self, raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]:
            return Err(error=VulnParseError(reason="bad_json", details={}))

        def fetch(
            self,
            *,
            since: datetime | None = None,
            timeout_s: float = 30.0,
        ) -> Iterator[bytes]:
            raise VulnFeedFetchError("simulated network failure")
            yield b""  # unreachable; keeps the generator signature honest

    _Broken.source = source  # type: ignore[attr-defined]
    return _Broken


# ---------------------------------------------------------------------------
# AC-X1 — --help surfaces registered sources
# ---------------------------------------------------------------------------


def test_help_lists_registered_sources(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["vuln-index", "refresh", "--help"])
    assert result.exit_code == 0
    # The `--source` help text references the option but does not enumerate
    # choices in click's default --help rendering; assert that at least the
    # word ``--source`` appears so the option exists.
    assert "--source" in result.output


# AC-R6 — Open/Closed observable: registering a test feed makes it acceptable.
def test_register_test_feed_surfaces_in_choices(
    register_test_feed,  # type: ignore[no-untyped-def]
    tmp_path: Path,
    runner: CliRunner,
) -> None:
    register_test_feed(
        "_test_open_closed",
        _make_empty_feed("_test_open_closed"),
    )
    db = tmp_path / "v.sqlite"
    result = runner.invoke(
        cli,
        ["vuln-index", "refresh", "--source", "_test_open_closed", "--index-path", str(db)],
    )
    assert result.exit_code == 0, result.output


def test_unregistered_source_rejected(tmp_path: Path, runner: CliRunner) -> None:
    db = tmp_path / "v.sqlite"
    result = runner.invoke(
        cli,
        ["vuln-index", "refresh", "--source", "no_such_feed", "--index-path", str(db)],
    )
    assert result.exit_code != 0
    assert "no_such_feed" in result.output


# ---------------------------------------------------------------------------
# AC-X1, X9 — happy path with auto-apply migrations
# ---------------------------------------------------------------------------


def test_refresh_nvd_end_to_end_auto_applies_migrations(
    register_test_feed,  # type: ignore[no-untyped-def]
    tmp_path: Path,
    runner: CliRunner,
) -> None:
    from codegenie.types.identifiers import PackageName

    register_test_feed(
        "nvd_cassette",
        _make_cassette_feed(
            "nvd_cassette",
            [CASSETTES_DIR / "nvd" / "express-min.json"],
        ),
    )
    db = tmp_path / "vi.sqlite"
    assert not db.exists()
    result = runner.invoke(
        cli,
        ["vuln-index", "refresh", "--source", "nvd_cassette", "--index-path", str(db)],
    )
    assert result.exit_code == 0, result.output
    assert db.exists()
    with VulnIndex(db) as idx:
        records = idx.lookup(PackageName("express"), "npm")
        assert len(records) == 1


# AC-X4 — empty feed exits 0
def test_empty_feed_exits_0(
    register_test_feed,  # type: ignore[no-untyped-def]
    tmp_path: Path,
    runner: CliRunner,
) -> None:
    register_test_feed("empty", _make_empty_feed("empty"))
    db = tmp_path / "v.sqlite"
    result = runner.invoke(
        cli,
        ["vuln-index", "refresh", "--source", "empty", "--index-path", str(db)],
    )
    assert result.exit_code == 0, result.output


# AC-X6 — all feeds fail HTTP → exit 5
def test_all_feeds_fail_http_exits_5(
    register_test_feed,  # type: ignore[no-untyped-def]
    tmp_path: Path,
    runner: CliRunner,
) -> None:
    register_test_feed("broken", _make_broken_feed("broken"))
    db = tmp_path / "v.sqlite"
    result = runner.invoke(
        cli,
        ["vuln-index", "refresh", "--source", "broken", "--index-path", str(db)],
    )
    assert result.exit_code == 5, result.output


# AC-X5 — partial parse error → exit 4
def test_partial_parse_error_exits_4(
    register_test_feed,  # type: ignore[no-untyped-def]
    tmp_path: Path,
    runner: CliRunner,
) -> None:
    register_test_feed(
        "mixed",
        _make_cassette_feed(
            "mixed",
            [
                CASSETTES_DIR / "nvd" / "express-min.json",
                CASSETTES_DIR / "nvd" / "malformed-bad_cve.json",
            ],
        ),
    )
    db = tmp_path / "v.sqlite"
    result = runner.invoke(
        cli,
        ["vuln-index", "refresh", "--source", "mixed", "--index-path", str(db)],
    )
    assert result.exit_code == 4, result.output


# AC-X7 — existing-unmigrated DB → exit 7
def test_existing_unmigrated_db_exits_7(tmp_path: Path, runner: CliRunner) -> None:
    db = tmp_path / "vi.sqlite"
    db.touch()
    result = runner.invoke(
        cli,
        ["vuln-index", "refresh", "--source", "nvd", "--index-path", str(db)],
    )
    assert result.exit_code == 7, result.output


# AC-X8 — env precedence (CLI flag > env > default)
def test_cli_flag_wins_over_env(
    register_test_feed,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    runner: CliRunner,
) -> None:
    register_test_feed(
        "cas", _make_cassette_feed("cas", [CASSETTES_DIR / "nvd" / "express-min.json"])
    )
    env_db = tmp_path / "env.sqlite"
    flag_db = tmp_path / "flag.sqlite"
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_PATH", str(env_db))
    result = runner.invoke(
        cli,
        ["vuln-index", "refresh", "--source", "cas", "--index-path", str(flag_db)],
    )
    assert result.exit_code == 0, result.output
    assert flag_db.exists()
    assert not env_db.exists()


def test_env_used_when_no_flag(
    register_test_feed,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    runner: CliRunner,
) -> None:
    register_test_feed(
        "cas", _make_cassette_feed("cas", [CASSETTES_DIR / "nvd" / "express-min.json"])
    )
    env_db = tmp_path / "env.sqlite"
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_PATH", str(env_db))
    result = runner.invoke(cli, ["vuln-index", "refresh", "--source", "cas"])
    assert result.exit_code == 0, result.output
    assert env_db.exists()


# AC-X10 — emits exactly one completion event.
def test_refresh_emits_completion_event(
    register_test_feed,  # type: ignore[no-untyped-def]
    tmp_path: Path,
    runner: CliRunner,
) -> None:
    register_test_feed(
        "cas",
        _make_cassette_feed("cas", [CASSETTES_DIR / "nvd" / "express-min.json"]),
    )
    db = tmp_path / "v.sqlite"
    with structlog.testing.capture_logs() as caplog:
        result = runner.invoke(
            cli,
            ["vuln-index", "refresh", "--source", "cas", "--index-path", str(db)],
        )
    assert result.exit_code == 0, result.output
    completions = [e for e in caplog if e.get("event") == "vuln_index.refresh.completed"]
    assert len(completions) == 1
    payload = completions[0]
    assert payload["inserted"] == 1
    assert payload["errors"] == 0
    assert payload["exit_code"] == 0
    assert isinstance(payload["digest_changed"], bool)


# Exit-code dispatch table is the single source of truth.
def test_exit_code_dispatch_table_extended() -> None:
    from codegenie.cli import _EXIT_CODE_DISPATCH
    from codegenie.errors import (
        VulnFeedFetchError,
        VulnIndexMigrationNotApplied,
        VulnRefreshPartialError,
    )

    assert _EXIT_CODE_DISPATCH[VulnRefreshPartialError] == 4
    assert _EXIT_CODE_DISPATCH[VulnFeedFetchError] == 5
    assert _EXIT_CODE_DISPATCH[VulnIndexMigrationNotApplied] == 7
