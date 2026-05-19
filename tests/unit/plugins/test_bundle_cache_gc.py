"""S3-05 — :class:`BundleCacheGc` pure helpers + run + amortisation tests.

Covers AC-20..AC-41 — pure-helper Hypothesis properties, TTL env
parametrize (accept + reject corpora), strict-``>`` boundary, exact
``bytes_reclaimed`` accounting, constructor-does-no-IO, event
exactly-once, ``.gc-stamp`` semantics (missing / corrupt / future-dated
/ concurrent / 24h-elapsed / within-24h).
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import codegenie.plugins.cache_gc as cg
from codegenie.plugins.cache import BundleCacheRaise
from codegenie.plugins.cache_gc import (
    BundleCacheGc,
    CacheGcCompletedEvent,
    CacheGcResult,
    _is_evictable,
    _parse_ttl_seconds,
    _should_run_amortized,
)
from codegenie.transforms._forward import SandboxedPath

# ---------------------------------------------------------------------------
# Pure helpers — Hypothesis + parametrize (AC-24, AC-25 — fence test elsewhere)
# ---------------------------------------------------------------------------


class TestPureHelpers:
    @given(
        now=st.floats(min_value=0, max_value=1e10),
        mtime=st.floats(min_value=0, max_value=1e10),
        ttl=st.integers(min_value=1, max_value=365 * 86_400),
    )
    @settings(max_examples=100)
    def test_is_evictable_monotone_in_age(self, now: float, mtime: float, ttl: int) -> None:
        """Metamorphic: older entries are at-least-as-evictable as newer ones."""
        older = mtime - 1
        assert _is_evictable(now, older, ttl) >= _is_evictable(now, mtime, ttl)

    def test_is_evictable_strict_boundary(self) -> None:
        """AC-29 — exactly-TTL-old kept; one second older evicted."""
        now = 1_000_000.0
        ttl = 7 * 86_400
        assert not _is_evictable(now, now - ttl, ttl)
        assert _is_evictable(now, now - ttl - 1, ttl)

    @given(
        now=st.floats(min_value=0, max_value=1e10),
        stamp=st.floats(min_value=0, max_value=1e10),
        interval=st.integers(min_value=1, max_value=86_400),
    )
    @settings(max_examples=100)
    def test_should_run_amortized_idempotent_within_interval(
        self, now: float, stamp: float, interval: int
    ) -> None:
        if stamp <= now and not _should_run_amortized(now, stamp, interval):
            assert not _should_run_amortized(now + interval // 2, stamp, interval)

    def test_should_run_amortized_future_dated_stamp_runs(self) -> None:
        """AC-38 — clock-skew resilience."""
        now = 1_000.0
        assert _should_run_amortized(now, last_stamp=now + 86_400, interval_seconds=86_400)

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("7", 7 * 86_400),
            (" 7 ", 7 * 86_400),
            ("7\n", 7 * 86_400),
            ("1", 86_400),
            ("30", 30 * 86_400),
            ("365", 365 * 86_400),
        ],
    )
    def test_parse_ttl_accepts(self, raw: str, expected: int) -> None:
        assert _parse_ttl_seconds({"CODEGENIE_BUNDLE_CACHE_TTL_DAYS": raw}) == expected

    @pytest.mark.parametrize(
        "bad",
        ["", "0", "-1", "7.5", "+7", "not-an-int", "  ", "1e2", "0x7"],
    )
    def test_parse_ttl_reject_corpus(self, bad: str) -> None:
        """AC-31 reject corpus."""
        with pytest.raises(BundleCacheRaise) as exc:
            _parse_ttl_seconds({"CODEGENIE_BUNDLE_CACHE_TTL_DAYS": bad})
        assert exc.value.model.reason == "invalid_ttl_env"
        assert exc.value.model.details["value"] == bad

    def test_parse_ttl_defaults_to_seven(self) -> None:
        assert _parse_ttl_seconds({}) == 7 * 86_400


# ---------------------------------------------------------------------------
# Constructor + run() — impure shell
# ---------------------------------------------------------------------------


class TestConstructorAndRun:
    def test_constructor_does_no_io(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """AC-26 — invalid env must NOT raise at ``__init__``."""
        monkeypatch.setenv("CODEGENIE_BUNDLE_CACHE_TTL_DAYS", "not-an-int")
        gc = BundleCacheGc(SandboxedPath(absolute=tmp_path))
        with pytest.raises(BundleCacheRaise) as exc:
            gc.run()
        assert exc.value.model.reason == "invalid_ttl_env"

    def test_evicts_only_files_older_than_ttl(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-27 / AC-30 — only the stale file is evicted; bytes are exact."""
        monkeypatch.setenv("CODEGENIE_BUNDLE_CACHE_TTL_DAYS", "7")
        bundles = tmp_path / "bundles"
        bundles.mkdir(parents=True)
        old = bundles / ("a" * 64 + ".json")
        old.write_text('{"x":1}')
        size_old = old.stat().st_size
        os.utime(old, (time.time() - 8 * 86_400,) * 2)
        fresh = bundles / ("b" * 64 + ".json")
        fresh.write_text('{"x":1}')
        result = BundleCacheGc(SandboxedPath(absolute=tmp_path)).run()
        assert not old.exists() and fresh.exists()
        assert result.entries_evicted == 1
        assert result.bytes_reclaimed == size_old
        assert result.duration_ms >= 0
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", result.wall_clock_iso)

    def test_run_on_missing_bundles_dir_returns_zero(self, tmp_path: Path) -> None:
        """AC-28 — missing ``bundles/`` does not raise."""
        result = BundleCacheGc(SandboxedPath(absolute=tmp_path)).run()
        assert result.entries_evicted == 0 and result.bytes_reclaimed == 0

    def test_run_on_empty_bundles_dir_returns_zero(self, tmp_path: Path) -> None:
        (tmp_path / "bundles").mkdir(parents=True)
        result = BundleCacheGc(SandboxedPath(absolute=tmp_path)).run()
        assert result.entries_evicted == 0 and result.bytes_reclaimed == 0

    def test_run_skips_non_hex_files_and_special_paths(self, tmp_path: Path) -> None:
        """AC-27 — non-hex names, dotfiles, subdirs, symlinks all preserved."""
        bundles = tmp_path / "bundles"
        bundles.mkdir(parents=True)
        (bundles / ".lock").write_text("")
        (tmp_path / ".gc-stamp").write_text(str(time.time() - 100 * 86_400))
        (bundles / "README.md").write_text("ignore me")
        (bundles / "not-hex.json").write_text("{}")
        (bundles / "subdir").mkdir()
        stale = time.time() - 100 * 86_400
        os.utime(tmp_path / ".gc-stamp", (stale, stale))
        for p in bundles.iterdir():
            if p.is_file():
                os.utime(p, (stale, stale))
        BundleCacheGc(SandboxedPath(absolute=tmp_path)).run()
        for p in [
            bundles / ".lock",
            bundles / "README.md",
            bundles / "not-hex.json",
            bundles / "subdir",
            tmp_path / ".gc-stamp",
        ]:
            assert p.exists(), f"non-hex / special path must NOT be touched: {p}"

    def test_run_skips_symlinks(self, tmp_path: Path) -> None:
        bundles = tmp_path / "bundles"
        bundles.mkdir(parents=True)
        real = tmp_path / "real.json"
        real.write_text("{}")
        link = bundles / ("a" * 64 + ".json")
        link.symlink_to(real)
        stale = time.time() - 100 * 86_400
        os.utime(real, (stale, stale))
        os.utime(link, (stale, stale), follow_symlinks=False)
        BundleCacheGc(SandboxedPath(absolute=tmp_path)).run()
        assert link.is_symlink(), "symlinks must not be unlinked"
        assert real.exists()


# ---------------------------------------------------------------------------
# Event emission (AC-32, AC-33)
# ---------------------------------------------------------------------------


class TestEventEmission:
    def test_event_emitter_called_exactly_once(self, tmp_path: Path) -> None:
        seen: list[CacheGcCompletedEvent] = []
        gc = BundleCacheGc(SandboxedPath(absolute=tmp_path), event_emitter=seen.append)
        gc.run()
        assert len(seen) == 1
        assert seen[0].trigger == "amortized"
        assert seen[0].event_type == "cache_gc_completed"

    def test_event_emitter_none_emits_zero(self, tmp_path: Path) -> None:
        gc = BundleCacheGc(SandboxedPath(absolute=tmp_path), event_emitter=None)
        result = gc.run()
        assert isinstance(result, CacheGcResult)

    def test_emitter_exceptions_propagate(self, tmp_path: Path) -> None:
        """AC-33 — Rule 12, fail loud."""

        def bad(_event: CacheGcCompletedEvent) -> None:
            raise RuntimeError("emitter blew up")

        gc = BundleCacheGc(SandboxedPath(absolute=tmp_path), event_emitter=bad)
        with pytest.raises(RuntimeError, match="emitter blew up"):
            gc.run()


# ---------------------------------------------------------------------------
# Amortisation + .gc-stamp (AC-34..AC-41)
# ---------------------------------------------------------------------------


class TestAmortization:
    def test_first_call_writes_stamp(self, tmp_path: Path) -> None:
        """AC-34 + AC-36 — first call runs and writes the stamp."""
        t_before = time.time()
        result = BundleCacheGc(SandboxedPath(absolute=tmp_path)).run_amortized()
        t_after = time.time()
        stamp_path = tmp_path / ".gc-stamp"
        assert result is not None
        assert stamp_path.exists()
        assert t_before - 1 <= float(stamp_path.read_text()) <= t_after + 1

    def test_within_24h_is_noop_and_does_not_emit(self, tmp_path: Path) -> None:
        """AC-32 (no-op branch) + AC-41."""
        seen: list[CacheGcCompletedEvent] = []
        gc = BundleCacheGc(SandboxedPath(absolute=tmp_path), event_emitter=seen.append)
        first = gc.run_amortized()
        second = gc.run_amortized()
        assert first is not None and second is None
        assert len(seen) == 1, "no-op branch must NOT emit a second event"

    def test_24h_elapsed_runs_again(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """AC-40 — monkeypatch the module-bound ``time`` to avoid recursion."""
        gc = BundleCacheGc(SandboxedPath(absolute=tmp_path))
        assert gc.run_amortized() is not None
        stamp_before = float((tmp_path / ".gc-stamp").read_text())
        real_time = time.time
        t_jump = stamp_before + 86_401
        called = {"n": 0}

        def fake_time() -> float:
            called["n"] += 1
            return t_jump if called["n"] <= 4 else real_time()

        monkeypatch.setattr(cg.time, "time", fake_time)
        assert gc.run_amortized() is not None
        stamp_after = float((tmp_path / ".gc-stamp").read_text())
        assert stamp_after > stamp_before

    def test_stamp_atomic_no_tmp_residue(self, tmp_path: Path) -> None:
        """AC-35 — atomic stamp write leaves no tmp residue."""
        BundleCacheGc(SandboxedPath(absolute=tmp_path)).run_amortized()
        tmps = list(tmp_path.glob(".gc-stamp.*.tmp"))
        assert not (tmp_path / ".gc-stamp.tmp").exists()
        assert tmps == []
        assert float((tmp_path / ".gc-stamp").read_text()) > 0

    def test_corrupt_gc_stamp_fails_loud(self, tmp_path: Path) -> None:
        """AC-37 — non-float content raises ``BundleCacheRaise``."""
        (tmp_path / ".gc-stamp").write_text("not-a-float")
        with pytest.raises(BundleCacheRaise) as exc:
            BundleCacheGc(SandboxedPath(absolute=tmp_path)).run_amortized()
        assert exc.value.model.reason == "corrupt_gc_stamp"

    def test_future_dated_stamp_treated_as_stale(self, tmp_path: Path) -> None:
        """AC-38 — clock-skew resilience: future stamp ⇒ run + rewrite."""
        future = time.time() + 86_400
        (tmp_path / ".gc-stamp").write_text(str(future))
        result = BundleCacheGc(SandboxedPath(absolute=tmp_path)).run_amortized()
        assert result is not None
        new_stamp = float((tmp_path / ".gc-stamp").read_text())
        assert new_stamp < future, "future-dated stamp must be rewritten to time.time()"

    def test_concurrent_callers_serialized(self, tmp_path: Path) -> None:
        """AC-39 — only one of two concurrent calls runs the GC."""
        gc = BundleCacheGc(SandboxedPath(absolute=tmp_path))
        results: list[CacheGcResult | None] = []

        def call() -> None:
            results.append(gc.run_amortized())

        t1 = threading.Thread(target=call)
        t2 = threading.Thread(target=call)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert sum(r is not None for r in results) == 1
        assert sum(r is None for r in results) == 1


# ---------------------------------------------------------------------------
# Result + Event model AC-20..AC-22
# ---------------------------------------------------------------------------


class TestResultAndEventModels:
    def test_result_serialises_cache_dir_as_string(self, tmp_path: Path) -> None:
        result = CacheGcResult(
            entries_evicted=0,
            bytes_reclaimed=0,
            cache_dir=SandboxedPath(absolute=tmp_path),
            ttl_days=7,
            duration_ms=0,
            wall_clock_iso="2026-05-19T00:00:00.000Z",
        )
        payload = result.model_dump(mode="json")
        assert payload["cache_dir"] == str(tmp_path)

    def test_from_result_classmethod_constructs_event(self, tmp_path: Path) -> None:
        """AC-22 — drift canary constructor."""
        result = CacheGcResult(
            entries_evicted=3,
            bytes_reclaimed=512,
            cache_dir=SandboxedPath(absolute=tmp_path),
            ttl_days=7,
            duration_ms=12,
            wall_clock_iso="2026-05-19T00:00:00.000Z",
        )
        event = CacheGcCompletedEvent.from_result(result, trigger="operator_cli")
        assert event.trigger == "operator_cli"
        assert event.entries_evicted == 3
        assert event.bytes_reclaimed == 512
        assert event.ttl_days == 7
        assert event.duration_ms == 12
        assert event.wall_clock_iso == "2026-05-19T00:00:00.000Z"
        assert event.cache_dir == str(tmp_path)
        assert event.event_type == "cache_gc_completed"

    def test_result_to_event_field_overlap_canary(self) -> None:
        """AC-22 — drift canary on field-name set relationship."""
        result_fields = set(CacheGcResult.model_fields.keys()) - {"cache_dir"}
        event_fields = set(CacheGcCompletedEvent.model_fields.keys())
        assert result_fields <= event_fields, (
            "CacheGcResult fields (minus cache_dir) must be a subset of "
            "CacheGcCompletedEvent fields"
        )
