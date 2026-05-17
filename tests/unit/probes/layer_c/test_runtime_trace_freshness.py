"""S5-05 — ``runtime_trace`` freshness check + B2 integration tests.

Covers ACs 1, 5, 6, 7, 8, 11, 15, 16. The companion files
``test_runtime_trace_freshness_purity.py`` (ACs 3, 4) and
``test_runtime_trace_freshness_mutation.py`` (AC-9) carry the rest.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import json
import logging
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from codegenie.errors import FreshnessRegistryError
from codegenie.exec import ProcessResult
from codegenie.indices.freshness import (
    DigestMismatch,
    Fresh,
    IndexerError,
    Stale,
)
from codegenie.indices.registry import default_freshness_registry
from codegenie.output.paths import raw_dir
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_b.index_health import IndexHealthProbe
from codegenie.probes.layer_c.runtime_trace import (
    _MSG_NO_BUILT_IMAGE,
    _MSG_NO_TRACE_RECORDED,
    _MSG_SLICE_MALFORMED,
    _MSG_UPSTREAM_UNAVAILABLE,
    _check_runtime_trace_freshness,
)
from codegenie.types.identifiers import IndexName

HEAD_SHA = "deadbeef00000000000000000000000000000000"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_freshness_registry() -> Iterator[Any]:
    """Snapshot + restore the singleton freshness registry per test."""
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


def _make_repo(tmp_path: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=tmp_path,
        git_commit=None,
        detected_languages={},
        config={},
    )


def _write_runtime_trace_raw(
    repo_root: Path,
    *,
    built_image_digest: str | None,
    last_traced_image_digest: str | None,
    last_traced_at: str = "2026-05-17T00:00:00+00:00",
    trace_coverage_confidence: str = "high",
) -> None:
    raw = raw_dir(repo_root)
    raw.mkdir(parents=True, exist_ok=True)
    payload = {
        "built_image_digest": built_image_digest,
        "last_traced_image_digest": last_traced_image_digest,
        "last_traced_at": last_traced_at,
        "trace_coverage_confidence": trace_coverage_confidence,
    }
    (raw / "runtime_trace.json").write_text(json.dumps(payload))


def _patch_head_resolver(monkeypatch: pytest.MonkeyPatch, head: str = HEAD_SHA) -> None:
    """Make ``IndexHealthProbe``'s git rev-parse return ``head`` deterministically.

    ``IndexHealthProbe`` calls ``_exec.run_allowlisted`` (where ``_exec`` is
    ``codegenie.exec`` imported as an alias inside ``index_health.py``). The
    monkeypatch must target the alias attribute on the imported module.
    """
    from codegenie import exec as ce

    async def _run_allow(*args: Any, **kwargs: Any) -> ProcessResult:
        return ProcessResult(0, (head + "\n").encode(), b"")

    monkeypatch.setattr(ce, "run_allowlisted", AsyncMock(side_effect=_run_allow))


# ---------------------------------------------------------------------------
# AC-1 — Function placement, decorator, signature
# ---------------------------------------------------------------------------


def test_function_signature_matches_registry_contract() -> None:
    sig = inspect.signature(_check_runtime_trace_freshness)
    params = list(sig.parameters.values())
    assert len(params) == 2
    assert params[0].name == "slice_"
    assert params[1].name == "head"
    # Annotation strings — exact spelling matters for the registry contract.
    assert params[0].annotation == "dict[str, object]"
    assert params[1].annotation == "str"


def test_function_exported_in_all() -> None:
    from codegenie.probes.layer_c import runtime_trace as rt

    assert "_check_runtime_trace_freshness" in rt.__all__


# ---------------------------------------------------------------------------
# AC-2 — Branch table (the seven cases)
# ---------------------------------------------------------------------------


def test_branch_a_empty_dict_upstream_unavailable() -> None:
    result = _check_runtime_trace_freshness({}, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, IndexerError)
    assert result.reason.message == _MSG_UPSTREAM_UNAVAILABLE


def test_branch_b_trace_coverage_unavailable() -> None:
    slice_: dict[str, object] = {
        "trace_coverage_confidence": "unavailable",
        "built_image_digest": "sha256:abc",
        "last_traced_image_digest": "sha256:abc",
        "last_traced_at": "2026-01-01T00:00:00+00:00",
    }
    result = _check_runtime_trace_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, IndexerError)
    assert result.reason.message == _MSG_UPSTREAM_UNAVAILABLE


@pytest.mark.parametrize(
    "slice_",
    [
        # last_traced_at missing entirely.
        {
            "built_image_digest": "sha256:abc",
            "last_traced_image_digest": "sha256:abc",
            "trace_coverage_confidence": "high",
        },
        # last_traced_at is an int, not a str.
        {
            "built_image_digest": "sha256:abc",
            "last_traced_image_digest": "sha256:abc",
            "last_traced_at": 42,
            "trace_coverage_confidence": "high",
        },
        # built_image_digest is an int (neither None nor str).
        {
            "built_image_digest": 123,
            "last_traced_image_digest": "sha256:abc",
            "last_traced_at": "2026-01-01T00:00:00+00:00",
            "trace_coverage_confidence": "high",
        },
        # last_traced_image_digest is a list.
        {
            "built_image_digest": "sha256:abc",
            "last_traced_image_digest": ["sha256:abc"],
            "last_traced_at": "2026-01-01T00:00:00+00:00",
            "trace_coverage_confidence": "high",
        },
    ],
)
def test_branch_c_slice_malformed_wrong_type(slice_: dict[str, object]) -> None:
    result = _check_runtime_trace_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, IndexerError)
    assert result.reason.message == _MSG_SLICE_MALFORMED


def test_branch_d_no_built_image() -> None:
    slice_: dict[str, object] = {
        "built_image_digest": None,
        "last_traced_image_digest": "sha256:abc",
        "last_traced_at": "2026-01-01T00:00:00+00:00",
        "trace_coverage_confidence": "high",
    }
    result = _check_runtime_trace_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, IndexerError)
    assert result.reason.message == _MSG_NO_BUILT_IMAGE


def test_branch_e_no_trace_recorded() -> None:
    slice_: dict[str, object] = {
        "built_image_digest": "sha256:abc",
        "last_traced_image_digest": None,
        "last_traced_at": "2026-01-01T00:00:00+00:00",
        "trace_coverage_confidence": "high",
    }
    result = _check_runtime_trace_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, IndexerError)
    assert result.reason.message == _MSG_NO_TRACE_RECORDED


def test_branch_f_digest_mismatch_argument_order_load_bearing() -> None:
    slice_: dict[str, object] = {
        "built_image_digest": "sha256:def",
        "last_traced_image_digest": "sha256:abc",
        "last_traced_at": "2026-01-01T00:00:00+00:00",
        "trace_coverage_confidence": "high",
    }
    result = _check_runtime_trace_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, DigestMismatch)
    # Argument order is load-bearing: expected = currently-built;
    # actual = what-was-traced. A swap would silently corrupt confidence
    # rendering downstream.
    assert result.reason.expected == "sha256:def"
    assert result.reason.actual == "sha256:abc"


def test_branch_g_fresh_when_digests_match() -> None:
    slice_: dict[str, object] = {
        "built_image_digest": "sha256:abc",
        "last_traced_image_digest": "sha256:abc",
        "last_traced_at": "2026-05-17T00:00:00+00:00",
        "trace_coverage_confidence": "high",
    }
    result = _check_runtime_trace_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Fresh)
    assert result.indexed_at == dt.datetime(2026, 5, 17, tzinfo=dt.UTC)


def test_branch_g_malformed_iso_falls_through_to_slice_malformed() -> None:
    slice_: dict[str, object] = {
        "built_image_digest": "sha256:abc",
        "last_traced_image_digest": "sha256:abc",
        "last_traced_at": "not-a-timestamp",
        "trace_coverage_confidence": "high",
    }
    result = _check_runtime_trace_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, IndexerError)
    assert result.reason.message == _MSG_SLICE_MALFORMED


def test_function_never_raises_on_arbitrary_object_values() -> None:
    # Defensive: even if a slice key carries an unexpected value type, the
    # function returns a typed value rather than letting an exception
    # escape (mirrors scip_freshness's "never raises" property).
    weird_slices: list[dict[str, object]] = [
        {"trace_coverage_confidence": object()},
        {"built_image_digest": [], "last_traced_image_digest": "x", "last_traced_at": "x"},
        {"last_traced_at": object()},
    ]
    for s in weird_slices:
        result = _check_runtime_trace_freshness(s, HEAD_SHA)
        assert isinstance(result, Stale)


# ---------------------------------------------------------------------------
# AC-5 — Registry membership + retrieval (identity)
# ---------------------------------------------------------------------------


def test_runtime_trace_registered_in_default_registry() -> None:
    assert IndexName("runtime_trace") in default_freshness_registry.registered_names()
    assert (
        default_freshness_registry._checks[IndexName("runtime_trace")]
        is _check_runtime_trace_freshness
    )


# ---------------------------------------------------------------------------
# AC-6 / AC-7 / AC-8 — B2 end-to-end integration
# ---------------------------------------------------------------------------


def test_b2_emits_drift_for_runtime_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_runtime_trace_raw(
        tmp_path,
        built_image_digest="sha256:def",
        last_traced_image_digest="sha256:abc",
    )
    _patch_head_resolver(monkeypatch)
    repo = _make_repo(tmp_path)
    ctx = _make_ctx(tmp_path)
    out = asyncio.run(IndexHealthProbe().run(repo, ctx))
    freshness = out.schema_slice["index_health"]["runtime_trace"]["freshness"]
    # Four-part inequality — the load-bearing mutation-resistance pin.
    assert freshness["kind"] == "stale"
    assert freshness["reason"]["kind"] == "digest_mismatch"
    assert freshness["reason"]["expected"] == "sha256:def"
    assert freshness["reason"]["actual"] == "sha256:abc"
    assert out.schema_slice["index_health"]["runtime_trace"]["confidence"] == "medium"
    assert IndexName("runtime_trace") in default_freshness_registry.registered_names()


def test_b2_emits_fresh_for_runtime_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_runtime_trace_raw(
        tmp_path,
        built_image_digest="sha256:abc",
        last_traced_image_digest="sha256:abc",
    )
    _patch_head_resolver(monkeypatch)
    repo = _make_repo(tmp_path)
    ctx = _make_ctx(tmp_path)
    out = asyncio.run(IndexHealthProbe().run(repo, ctx))
    freshness = out.schema_slice["index_health"]["runtime_trace"]["freshness"]
    assert freshness["kind"] == "fresh"
    # Pydantic ``model_dump(mode="json")`` renders UTC datetimes with the
    # ``Z`` suffix, not ``+00:00``; pin the wire shape, not the source.
    assert freshness["indexed_at"] == "2026-05-17T00:00:00Z"
    assert out.schema_slice["index_health"]["runtime_trace"]["confidence"] == "high"


def test_b2_emits_stale_for_absent_runtime_trace_slice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # NO runtime_trace.json written.
    _patch_head_resolver(monkeypatch)
    repo = _make_repo(tmp_path)
    ctx = _make_ctx(tmp_path)
    out = asyncio.run(IndexHealthProbe().run(repo, ctx))
    freshness = out.schema_slice["index_health"]["runtime_trace"]["freshness"]
    assert freshness["kind"] == "stale"
    assert freshness["reason"]["kind"] == "indexer_error"
    assert freshness["reason"]["message"] == _MSG_UPSTREAM_UNAVAILABLE


# ---------------------------------------------------------------------------
# AC-11 — Argument-order canary
# ---------------------------------------------------------------------------


def test_arg_order_is_slice_then_head() -> None:
    good_slice: dict[str, object] = {
        "built_image_digest": "sha256:abc",
        "last_traced_image_digest": "sha256:abc",
        "last_traced_at": "2026-01-01T00:00:00+00:00",
        "trace_coverage_confidence": "high",
    }
    assert isinstance(_check_runtime_trace_freshness(good_slice, "deadbeef"), Fresh)

    # Swapped args — string-as-slice has no ``.get`` of the right shape;
    # ``str.get`` does not exist, so this raises AttributeError.
    with pytest.raises((TypeError, AttributeError)):
        _check_runtime_trace_freshness("deadbeef", good_slice)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC-15 — Duplicate-registration smoke
# ---------------------------------------------------------------------------


def test_runtime_trace_duplicate_registration_rejected(
    clean_freshness_registry: Any,
) -> None:
    def _dummy(slice_: dict[str, object], head: str) -> Any:  # pragma: no cover
        raise AssertionError("never invoked")

    with pytest.raises(FreshnessRegistryError) as exc_info:
        default_freshness_registry.register(IndexName("runtime_trace"))(_dummy)
    msg = exc_info.value.args[0]
    assert "duplicate index_name" in msg
    assert "runtime_trace" in msg
    # Both call sites named.
    assert "_check_runtime_trace_freshness" in msg
    assert "_dummy" in msg


# ---------------------------------------------------------------------------
# AC-16 — No edits to IndexHealthProbe (structural promise)
# ---------------------------------------------------------------------------


def test_no_edit_to_index_health_module() -> None:
    """The Open/Closed promise is observable: adding a new index source
    must require zero edits to B2's module."""
    repo_root = Path(__file__).resolve().parents[4]
    try:
        result = subprocess.run(  # noqa: S603 — git, fixed argv
            ["git", "-C", str(repo_root), "diff", "--name-only", "origin/master..HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("git not available; skipping no-edit audit")
    if result.returncode != 0:
        pytest.skip(f"git diff unavailable (rc={result.returncode}); skipping")
    changed = set(result.stdout.splitlines())
    assert "src/codegenie/probes/layer_b/index_health.py" not in changed
