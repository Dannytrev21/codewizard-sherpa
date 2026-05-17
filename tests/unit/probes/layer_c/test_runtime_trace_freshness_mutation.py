"""S5-05 — Mutation-resistance suite (AC-9).

The test would itself fail (false-pass) if any stub were behaviorally
correct; that is the structural defense. Each stub is intentionally wrong
in a single, narrow way; at least one of the named AC-6/7/8/branch tests
must fail when the stub replaces the real check.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from codegenie.exec import ProcessResult
from codegenie.indices.freshness import (
    DigestMismatch,
    Fresh,
    IndexerError,
    IndexFreshness,
    Stale,
)
from codegenie.indices.registry import default_freshness_registry
from codegenie.output.paths import raw_dir
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_b.index_health import IndexHealthProbe
from codegenie.probes.layer_c.runtime_trace import (
    _MSG_UPSTREAM_UNAVAILABLE,
)
from codegenie.types.identifiers import IndexName

HEAD_SHA = "deadbeef00000000000000000000000000000000"


# ---------------------------------------------------------------------------
# Mutant stubs — each is wrong in exactly one way.
# ---------------------------------------------------------------------------


def _always_fresh(slice_: dict[str, object], head: str) -> IndexFreshness:
    """Returns Fresh regardless of input — must fail drift AND absent-slice tests."""
    return Fresh(indexed_at=_dt.datetime(2026, 1, 1, tzinfo=_dt.UTC))


def _always_stale(slice_: dict[str, object], head: str) -> IndexFreshness:
    """Returns Stale regardless of input — must fail the clean (Fresh) case."""
    return Stale(reason=IndexerError(message="x"))


def _swap_expected_actual(slice_: dict[str, object], head: str) -> IndexFreshness:
    """Emits DigestMismatch with expected/actual swapped — must fail
    the field-value assertions on the drift case."""
    built = slice_.get("built_image_digest")
    last_traced = slice_.get("last_traced_image_digest")
    if isinstance(built, str) and isinstance(last_traced, str) and built != last_traced:
        return Stale(reason=DigestMismatch(expected=last_traced, actual=built))
    return Fresh(indexed_at=_dt.datetime(2026, 1, 1, tzinfo=_dt.UTC))


def _wrong_reason_kind(slice_: dict[str, object], head: str) -> IndexFreshness:
    """Collapses the drift case onto IndexerError — must fail the
    ``reason.kind == "digest_mismatch"`` discriminator check."""
    built = slice_.get("built_image_digest")
    last_traced = slice_.get("last_traced_image_digest")
    if isinstance(built, str) and isinstance(last_traced, str) and built != last_traced:
        return Stale(reason=IndexerError(message="digest_mismatch"))
    return Fresh(indexed_at=_dt.datetime(2026, 1, 1, tzinfo=_dt.UTC))


def _drops_upstream_unavailable_branch(slice_: dict[str, object], head: str) -> IndexFreshness:
    """Returns the wrong message string for empty-dict — must fail the
    absent-slice assertion on ``_MSG_UPSTREAM_UNAVAILABLE``."""
    if not slice_:
        return Stale(reason=IndexerError(message="scip_slice_malformed"))
    return Fresh(indexed_at=_dt.datetime(2026, 1, 1, tzinfo=_dt.UTC))


_MUTANTS = [
    ("always_fresh", _always_fresh),
    ("always_stale", _always_stale),
    ("swap_expected_actual", _swap_expected_actual),
    ("wrong_reason_kind", _wrong_reason_kind),
    ("drops_upstream_unavailable_branch", _drops_upstream_unavailable_branch),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_freshness_registry() -> Iterator[Any]:
    saved_checks = dict(default_freshness_registry._checks)
    saved_origins = dict(default_freshness_registry._origins)
    try:
        yield default_freshness_registry
    finally:
        default_freshness_registry._checks.clear()
        default_freshness_registry._origins.clear()
        default_freshness_registry._checks.update(saved_checks)
        default_freshness_registry._origins.update(saved_origins)


def _make_ctx(tmp_path: Path) -> ProbeContext:
    workspace = tmp_path / "_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return ProbeContext(
        cache_dir=tmp_path / "_cache",
        output_dir=tmp_path / "_out",
        workspace=workspace,
        logger=logging.getLogger("test"),
        config={},
    )


def _patch_head_resolver(monkeypatch: pytest.MonkeyPatch, head: str = HEAD_SHA) -> None:
    from codegenie import exec as ce

    async def _run_allow(*args: Any, **kwargs: Any) -> ProcessResult:
        return ProcessResult(0, (head + "\n").encode(), b"")

    monkeypatch.setattr(ce, "run_allowlisted", AsyncMock(side_effect=_run_allow))


def _write_slice(
    repo_root: Path,
    *,
    built: str | None,
    last_traced: str | None,
    confidence: str = "high",
) -> None:
    raw = raw_dir(repo_root)
    raw.mkdir(parents=True, exist_ok=True)
    payload = {
        "built_image_digest": built,
        "last_traced_image_digest": last_traced,
        "last_traced_at": "2026-05-17T00:00:00+00:00",
        "trace_coverage_confidence": confidence,
    }
    (raw / "runtime_trace.json").write_text(json.dumps(payload))


def _b2_freshness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    repo = RepoSnapshot(root=tmp_path, git_commit=None, detected_languages={}, config={})
    ctx = _make_ctx(tmp_path)
    _patch_head_resolver(monkeypatch)
    out = asyncio.run(IndexHealthProbe().run(repo, ctx))
    return out.schema_slice["index_health"]["runtime_trace"]["freshness"]


# ---------------------------------------------------------------------------
# The mutation table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,stub", _MUTANTS)
def test_mutant_fails_at_least_one_named_check(
    name: str,
    stub: Any,
    clean_freshness_registry: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """For each intentionally-wrong stub, assert at least one of the named
    AC-6 (drift) / AC-7 (clean Fresh) / AC-8 (absent slice) checks fails.

    The structure mirrors S5-04 T2: a single AC-only assertion (e.g., on
    ``kind == "stale"``) is too weak to catch every stub; the asserted
    bundle here is the bare minimum that flags each wrong implementation.
    """
    default_freshness_registry._checks[IndexName("runtime_trace")] = stub

    failures: list[str] = []

    # AC-6 drift case
    drift_root = tmp_path / "drift"
    drift_root.mkdir()
    _write_slice(drift_root, built="sha256:def", last_traced="sha256:abc")
    f = _b2_freshness(drift_root, monkeypatch)
    if not (
        f["kind"] == "stale"
        and f.get("reason", {}).get("kind") == "digest_mismatch"
        and f.get("reason", {}).get("expected") == "sha256:def"
        and f.get("reason", {}).get("actual") == "sha256:abc"
    ):
        failures.append("AC-6")

    # AC-7 clean case
    clean_root = tmp_path / "clean"
    clean_root.mkdir()
    _write_slice(clean_root, built="sha256:abc", last_traced="sha256:abc")
    f = _b2_freshness(clean_root, monkeypatch)
    if f["kind"] != "fresh":
        failures.append("AC-7")

    # AC-8 absent slice
    absent_root = tmp_path / "absent"
    absent_root.mkdir()
    f = _b2_freshness(absent_root, monkeypatch)
    if not (
        f["kind"] == "stale"
        and f.get("reason", {}).get("kind") == "indexer_error"
        and f.get("reason", {}).get("message") == _MSG_UPSTREAM_UNAVAILABLE
    ):
        failures.append("AC-8")

    assert failures, (
        f"mutant {name!r} passed every assertion — either the stub is not "
        f"actually wrong, or the assertions are too weak to catch it"
    )
