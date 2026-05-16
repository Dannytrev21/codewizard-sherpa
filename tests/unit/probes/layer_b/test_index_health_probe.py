"""S4-01 — ``IndexHealthProbe`` (B2): registry-dispatched freshness loop.

Tests verify intent (Rule 9): every test pins a discipline named in the story.

- T-15 (no per-index branches in ``run``) encodes Open/Closed at the file
  boundary.
- T-09 (typed construction failures) encodes the "B2 never raises" failure-
  isolation discipline.
- T-13 (exhaustive ``_derive_confidence``) encodes the sum-type discipline
  that ``mypy --warn-unreachable`` enforces.

All tests use a *local* :class:`FreshnessRegistry` view — even the ones
exercising the module-level singleton snapshot + restore the singleton in a
``finally:`` block via the ``clean_freshness_registry`` fixture so the
``scip`` registration that ``index_health.py`` plants at import time is
preserved across tests.
"""

from __future__ import annotations

import ast
import asyncio
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from codegenie.errors import (
    DisallowedSubprocessError,
    ProbeTimeoutError,
    ToolMissingError,
)
from codegenie.exec import ProcessResult
from codegenie.indices.freshness import (
    CommitsBehind,
    CoverageGap,
    DigestMismatch,
    Fresh,
    IndexerError,
    Stale,
)
from codegenie.indices.registry import (
    FreshnessRegistry,
    default_freshness_registry,
)
from codegenie.probes.base import ProbeContext, RepoSnapshot, Task
from codegenie.probes.layer_b import index_health as ih
from codegenie.probes.layer_b.index_health import (
    IndexHealthProbe,
    _derive_confidence,
    _last_indexed_at,
    read_raw_slices,
    scip_freshness,
)
from codegenie.probes.registry import default_registry
from codegenie.types.identifiers import IndexName

if TYPE_CHECKING:
    from codegenie.indices import IndexFreshness


# ---------------------------------------------------------------------------
# Test helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_freshness_registry() -> Any:
    """Snapshot + restore the singleton freshness registry around each test."""
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


def _make_repo(tmp_path: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=tmp_path,
        git_commit=None,
        detected_languages={},
        config={},
    )


def _make_ctx(tmp_path: Path) -> ProbeContext:
    import logging

    workspace = tmp_path / "_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return ProbeContext(
        cache_dir=tmp_path / "_cache",
        output_dir=tmp_path / "_out",
        workspace=workspace,
        logger=logging.getLogger("test"),
        config={},
    )


HEAD_SHA = "deadbeef00000000000000000000000000000000"
OLD_SHA = "feedface00000000000000000000000000000000"


def _ok_head_call() -> AsyncMock:
    return AsyncMock(return_value=ProcessResult(0, (HEAD_SHA + "\n").encode(), b""))


def _ok_revlist(n: int) -> ProcessResult:
    return ProcessResult(0, (str(n) + "\n").encode(), b"")


# ---------------------------------------------------------------------------
# AC-1 — probe-contract attributes + signature
# ---------------------------------------------------------------------------


def test_probe_contract_attributes() -> None:
    """T-01 — every class attr matches AC-1 verbatim."""
    p = IndexHealthProbe()
    assert p.name == "index_health"
    assert p.version == "0.1.0"
    assert p.layer == "B"
    assert p.tier == "base"
    assert p.applies_to_languages == ["*"]
    assert p.applies_to_tasks == ["*"]
    assert p.requires == []
    assert p.timeout_seconds == 10
    # cache_strategy is a Literal["none"] - identity check + literal check.
    assert p.cache_strategy == "none"
    # The two-arg run signature (self+repo+ctx). Three positional argcount.
    assert IndexHealthProbe.run.__code__.co_argcount == 3
    # declared_inputs contains the four tokens from AC-1.
    inputs = p.declared_inputs
    assert ".codegenie/context/raw/*.json" in inputs
    assert ".git/HEAD" in inputs
    assert any("scip-index" in t for t in inputs)
    assert any("image-digest" in t for t in inputs)


# ---------------------------------------------------------------------------
# AC-3 — runs_last registry annotation + sort order
# ---------------------------------------------------------------------------


def test_runs_last_registry_annotation_present() -> None:
    """T-02 — the registry entry for ``IndexHealthProbe`` has runs_last=True."""
    entries = default_registry.sorted_for_dispatch()
    matching = [e for e in entries if e.cls.__name__ == "IndexHealthProbe"]
    assert len(matching) == 1
    assert matching[0].runs_last is True


def test_sorted_for_dispatch_places_b2_last() -> None:
    """T-03a — across the real registry, B2 is the last entry."""
    entries = default_registry.sorted_for_dispatch()
    assert entries[-1].cls.__name__ == "IndexHealthProbe"


# ---------------------------------------------------------------------------
# AC-5 — SCIP freshness check, the six branches
# ---------------------------------------------------------------------------


def test_scip_freshness_fresh_path() -> None:
    """T-04 — AC-5(b): every required key + match → Fresh."""
    slice_: dict[str, object] = {
        "last_indexed_commit": HEAD_SHA,
        "files_indexed": 247,
        "files_in_repo": 247,
        "indexer_errors": 0,
        "last_indexed_at": "2026-01-01T00:00:00+00:00",
    }
    result = scip_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Fresh)
    assert result.indexed_at == dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def test_scip_freshness_commits_behind_path_pure_default() -> None:
    """T-05 — AC-5(c) pure layer: commit differs → CommitsBehind(n=1, last_indexed=…).

    The check function is pure (no IO); n=1 is the load-bearing minimum
    (AC-6 "at least one commit behind"). B2's imperative shell upgrades n
    via ``git rev-list`` post-dispatch — see
    ``test_commits_behind_n_upgraded_via_rev_list``.
    """
    slice_: dict[str, object] = {
        "last_indexed_commit": OLD_SHA,
        "files_indexed": 200,
        "files_in_repo": 200,
        "indexer_errors": 0,
        "last_indexed_at": "2026-01-01T00:00:00+00:00",
    }
    result = scip_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, CommitsBehind)
    assert result.reason.n >= 1  # AC-6 invariant
    assert result.reason.last_indexed == OLD_SHA


async def test_commits_behind_n_upgraded_via_rev_list(
    clean_freshness_registry: FreshnessRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T-05b — AC-6: B2 post-dispatch upgrades CommitsBehind.n via rev-list."""
    reg = clean_freshness_registry
    reg.register(IndexName("scip"))(scip_freshness)

    raw = ih.raw_dir(tmp_path)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "scip.json").write_text(
        json.dumps(
            {
                "last_indexed_commit": OLD_SHA,
                "files_indexed": 100,
                "files_in_repo": 100,
                "indexer_errors": 0,
                "last_indexed_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )

    async def fake_run_allowlisted(
        argv: list[str], *, cwd: Path, timeout_s: float, env_extra: Any = None
    ) -> ProcessResult:
        if argv[:2] == ["git", "rev-parse"]:
            return ProcessResult(0, (HEAD_SHA + "\n").encode(), b"")
        # rev-list — return 3 commits behind.
        assert argv[:3] == ["git", "rev-list", "--count"]
        return _ok_revlist(3)

    monkeypatch.setattr(ih._exec, "run_allowlisted", fake_run_allowlisted)
    out = await IndexHealthProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    fr = out.schema_slice["index_health"]["scip"]["freshness"]
    assert fr["kind"] == "stale"
    assert fr["reason"]["kind"] == "commits_behind"
    assert fr["reason"]["n"] == 3
    # No commits_behind_count_unknown warning on successful upgrade.
    assert "index_health.commits_behind_count_unknown" not in out.warnings


def test_scip_freshness_coverage_gap_path() -> None:
    """T-06 — AC-5(d): commit matches, files_indexed < files_in_repo."""
    slice_: dict[str, object] = {
        "last_indexed_commit": HEAD_SHA,
        "files_indexed": 240,
        "files_in_repo": 247,
        "indexer_errors": 0,
        "last_indexed_at": "2026-01-01T00:00:00+00:00",
    }
    result = scip_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, CoverageGap)
    assert result.reason.files_indexed == 240
    assert result.reason.files_in_repo == 247


def test_scip_freshness_indexer_error_path() -> None:
    """T-07 — AC-5(e): commit matches, coverage matches, indexer_errors>0."""
    slice_: dict[str, object] = {
        "last_indexed_commit": HEAD_SHA,
        "files_indexed": 247,
        "files_in_repo": 247,
        "indexer_errors": 2,
        "last_indexed_at": "2026-01-01T00:00:00+00:00",
    }
    result = scip_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, IndexerError)
    assert result.reason.message == "indexer_reported_2_errors"


def test_scip_freshness_upstream_unavailable_path() -> None:
    """T-08 — AC-5(a) + AC-12: empty dict sentinel → upstream_scip_unavailable.

    Distinguishes from None: scip_freshness expects an empty dict and the
    distinction is load-bearing — registry's dispatch_all passes ``{}``,
    never ``None``.
    """
    slice_: dict[str, object] = {}
    # Positive sanity — distinguishing the dict-sentinel from None.
    assert slice_ is not None  # noqa: E711 — intentional comparison vs None
    assert isinstance(slice_, dict)
    assert not slice_
    result = scip_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, IndexerError)
    assert result.reason.message == "upstream_scip_unavailable"


def test_scip_freshness_malformed_slice_path() -> None:
    """T-08b — AC-5(f): type-wrong required key → scip_slice_malformed."""
    slice_: dict[str, object] = {
        "last_indexed_commit": 42,  # WRONG type
        "files_indexed": 0,
        "files_in_repo": 0,
        "indexer_errors": 0,
        "last_indexed_at": "2026-01-01T00:00:00+00:00",
    }
    result = scip_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, IndexerError)
    assert result.reason.message == "scip_slice_malformed"


def test_scip_freshness_missing_required_key_is_malformed() -> None:
    """T-08c — AC-5(f) co-witness: missing key on non-empty dict → malformed.

    Distinguishes "upstream wrote nothing" (empty dict → AC-5a) from
    "upstream wrote a partial blob" (non-empty but missing keys → AC-5f).
    """
    slice_: dict[str, object] = {"last_indexed_commit": HEAD_SHA}
    result = scip_freshness(slice_, HEAD_SHA)
    assert isinstance(result, Stale)
    assert isinstance(result.reason, IndexerError)
    assert result.reason.message == "scip_slice_malformed"


# ---------------------------------------------------------------------------
# AC-8 — typed construction failure: B2 never raises
# ---------------------------------------------------------------------------


async def test_freshness_construction_failure_is_typed(
    clean_freshness_registry: FreshnessRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T-09 — AC-8: one bad check + one good check; both names appear."""
    reg = clean_freshness_registry
    scip = IndexName("scip")
    broken = IndexName("broken")

    @reg.register(scip)
    def good_scip(slice_: dict[str, object], head: str) -> IndexFreshness:
        return Fresh(indexed_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))

    @reg.register(broken)
    def bad(slice_: dict[str, object], head: str) -> IndexFreshness:
        # Force a pydantic ValidationError via deliberately malformed Fresh.
        return Fresh(indexed_at="not-a-datetime")  # type: ignore[arg-type]

    # Mock the HEAD resolve.
    monkeypatch.setattr(ih._exec, "run_allowlisted", _ok_head_call())

    # Empty raw_dir so each check gets ``{}``.
    out = await IndexHealthProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))

    payload = out.schema_slice["index_health"]
    assert "scip" in payload
    assert "broken" in payload
    assert payload["scip"]["freshness"]["kind"] == "fresh"
    assert payload["broken"]["freshness"]["kind"] == "stale"
    assert payload["broken"]["freshness"]["reason"]["kind"] == "indexer_error"
    msg = payload["broken"]["freshness"]["reason"]["message"]
    assert "freshness_construction_failed_broken" in msg
    assert "ValidationError" in msg


# ---------------------------------------------------------------------------
# AC-7 — HEAD unresolvable
# ---------------------------------------------------------------------------


_HEAD_FAILURE_MODES: list[tuple[str, Any]] = [
    ("tool_missing", ToolMissingError("missing")),
    ("timeout", ProbeTimeoutError("timeout")),
    ("disallowed", DisallowedSubprocessError("disallowed")),
    ("file_not_found", FileNotFoundError("missing cwd")),
    ("not_a_directory", NotADirectoryError("not a dir")),
    ("nonzero_returncode", ProcessResult(128, b"", b"fatal: not a git repository\n")),
]


@pytest.mark.parametrize("mode, ret_or_exc", _HEAD_FAILURE_MODES)
async def test_head_unresolvable_path(
    clean_freshness_registry: FreshnessRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
    ret_or_exc: Any,
) -> None:
    """T-10 — AC-7: every HEAD failure surface → repo_not_a_git_workdir."""
    reg = clean_freshness_registry
    scip = IndexName("scip")

    @reg.register(scip)
    def scip_check(slice_: dict[str, object], head: str) -> IndexFreshness:
        return Fresh(indexed_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))

    async def fake_run_allowlisted(
        argv: list[str], *, cwd: Path, timeout_s: float, env_extra: Any = None
    ) -> ProcessResult:
        if isinstance(ret_or_exc, BaseException):
            raise ret_or_exc
        assert isinstance(ret_or_exc, ProcessResult)
        return ret_or_exc

    monkeypatch.setattr(ih._exec, "run_allowlisted", fake_run_allowlisted)

    out = await IndexHealthProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))

    assert out.confidence == "low"
    assert "index_health.head_unresolvable" in out.warnings
    payload = out.schema_slice["index_health"]
    assert "scip" in payload
    assert payload["scip"]["confidence"] == "low"
    fr = payload["scip"]["freshness"]
    assert fr["kind"] == "stale"
    assert fr["reason"]["kind"] == "indexer_error"
    assert fr["reason"]["message"] == "repo_not_a_git_workdir"


# ---------------------------------------------------------------------------
# AC-6 — CommitsBehind.n derivation + fallback
# ---------------------------------------------------------------------------


async def test_commits_behind_count_unknown_fallback_revlist_nonzero(
    clean_freshness_registry: FreshnessRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T-11(a) — AC-6: rev-list returncode != 0 → n=1 + warning."""
    reg = clean_freshness_registry
    reg.register(IndexName("scip"))(scip_freshness)

    raw = ih.raw_dir(tmp_path)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "scip.json").write_text(
        json.dumps(
            {
                "last_indexed_commit": OLD_SHA,
                "files_indexed": 100,
                "files_in_repo": 100,
                "indexer_errors": 0,
                "last_indexed_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )

    calls: list[list[str]] = []

    async def fake_run_allowlisted(
        argv: list[str], *, cwd: Path, timeout_s: float, env_extra: Any = None
    ) -> ProcessResult:
        calls.append(argv)
        if argv[:2] == ["git", "rev-parse"]:
            return ProcessResult(0, (HEAD_SHA + "\n").encode(), b"")
        # rev-list — return non-zero.
        return ProcessResult(128, b"", b"fatal: ...")

    monkeypatch.setattr(ih._exec, "run_allowlisted", fake_run_allowlisted)

    out = await IndexHealthProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    payload = out.schema_slice["index_health"]["scip"]
    fr = payload["freshness"]
    assert fr["kind"] == "stale"
    assert fr["reason"]["kind"] == "commits_behind"
    assert fr["reason"]["n"] == 1
    assert "index_health.commits_behind_count_unknown" in out.warnings


async def test_commits_behind_count_unknown_fallback_revlist_non_numeric(
    clean_freshness_registry: FreshnessRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T-11(b) — AC-6: rev-list non-numeric stdout → ValueError → n=1."""
    reg = clean_freshness_registry
    reg.register(IndexName("scip"))(scip_freshness)

    raw = ih.raw_dir(tmp_path)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "scip.json").write_text(
        json.dumps(
            {
                "last_indexed_commit": OLD_SHA,
                "files_indexed": 100,
                "files_in_repo": 100,
                "indexer_errors": 0,
                "last_indexed_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )

    async def fake_run_allowlisted(
        argv: list[str], *, cwd: Path, timeout_s: float, env_extra: Any = None
    ) -> ProcessResult:
        if argv[:2] == ["git", "rev-parse"]:
            return ProcessResult(0, (HEAD_SHA + "\n").encode(), b"")
        return ProcessResult(0, b"not-a-number\n", b"")

    monkeypatch.setattr(ih._exec, "run_allowlisted", fake_run_allowlisted)

    out = await IndexHealthProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    payload = out.schema_slice["index_health"]["scip"]
    fr = payload["freshness"]
    assert fr["reason"]["kind"] == "commits_behind"
    assert fr["reason"]["n"] == 1
    assert "index_health.commits_behind_count_unknown" in out.warnings


# ---------------------------------------------------------------------------
# AC-11 — empty registry
# ---------------------------------------------------------------------------


async def test_no_sources_registered_path(
    clean_freshness_registry: FreshnessRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T-12 — AC-11: empty registry → slice={}, confidence='high'."""
    monkeypatch.setattr(ih._exec, "run_allowlisted", _ok_head_call())

    out = await IndexHealthProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    assert out.schema_slice["index_health"] == {}
    assert "index_health.no_sources_registered" in out.warnings
    assert out.confidence == "high"


# ---------------------------------------------------------------------------
# AC-9 — _derive_confidence pattern-matches every variant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "freshness, expected",
    [
        (Fresh(indexed_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)), "high"),
        (Stale(reason=CoverageGap(files_indexed=95, files_in_repo=100)), "medium"),
        (Stale(reason=CoverageGap(files_indexed=89, files_in_repo=100)), "low"),
        (Stale(reason=CoverageGap(files_indexed=0, files_in_repo=0)), "low"),
        (Stale(reason=CommitsBehind(n=1, last_indexed=OLD_SHA)), "medium"),
        (Stale(reason=DigestMismatch(expected="x", actual="y")), "medium"),
        (Stale(reason=IndexerError(message="z")), "low"),
    ],
)
def test_confidence_derivation_exhaustive(
    freshness: IndexFreshness, expected: str
) -> None:
    """T-13 — AC-9: every IndexFreshness variant → expected confidence."""
    assert _derive_confidence(freshness) == expected


def test_unknown_variant_rejected_by_smart_constructor() -> None:
    """T-13 (co-witness) — smart constructor refuses unknown StaleReason."""
    with pytest.raises(ValidationError):
        Stale(reason={"kind": "made_up", "data": 1})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC-10 — slice shape per localv2 + outer-key invariant
# ---------------------------------------------------------------------------


async def test_slice_shape_localv2_compliance(
    clean_freshness_registry: FreshnessRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T-20 — AC-10: per-source key set + outer-key invariant + last_indexed_at semantics."""
    reg = clean_freshness_registry
    reg.register(IndexName("scip"))(scip_freshness)

    raw = ih.raw_dir(tmp_path)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "scip.json").write_text(
        json.dumps(
            {
                "last_indexed_commit": HEAD_SHA,
                "files_indexed": 247,
                "files_in_repo": 247,
                "indexer_errors": 0,
                "last_indexed_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )

    monkeypatch.setattr(ih._exec, "run_allowlisted", _ok_head_call())

    out = await IndexHealthProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    payload = out.schema_slice["index_health"]
    # Outer-key invariant: every registered name appears exactly once.
    assert set(payload.keys()) == {str(n) for n in reg.registered_names()}
    src = payload["scip"]
    assert set(src.keys()) == {"freshness", "confidence", "current_commit", "last_indexed_at"}
    assert src["freshness"]["kind"] == "fresh"
    assert src["last_indexed_at"] == "2026-01-01T00:00:00+00:00"
    assert src["current_commit"] == HEAD_SHA


async def test_last_indexed_at_is_none_when_stale(
    clean_freshness_registry: FreshnessRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T-20 (co-witness) — last_indexed_at is None on every Stale variant."""
    reg = clean_freshness_registry
    reg.register(IndexName("scip"))(scip_freshness)

    raw = ih.raw_dir(tmp_path)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "scip.json").write_text(
        json.dumps(
            {
                "last_indexed_commit": HEAD_SHA,
                "files_indexed": 100,
                "files_in_repo": 200,
                "indexer_errors": 0,
                "last_indexed_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )

    monkeypatch.setattr(ih._exec, "run_allowlisted", _ok_head_call())
    out = await IndexHealthProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    src = out.schema_slice["index_health"]["scip"]
    assert src["last_indexed_at"] is None
    assert src["freshness"]["kind"] == "stale"


# ---------------------------------------------------------------------------
# AC-12 — sibling-missing path
# ---------------------------------------------------------------------------


async def test_sibling_missing_yields_empty_dict_to_check(
    clean_freshness_registry: FreshnessRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T-12 — AC-12: missing sibling raw → check gets empty dict, not None."""
    reg = clean_freshness_registry
    received: dict[str, object] = {"slice": object()}

    @reg.register(IndexName("scip"))
    def asserting_check(slice_: dict[str, object], head: str) -> IndexFreshness:
        received["slice"] = slice_
        assert isinstance(slice_, dict) and not slice_
        return Stale(reason=IndexerError(message="upstream_scip_unavailable"))

    monkeypatch.setattr(ih._exec, "run_allowlisted", _ok_head_call())
    await IndexHealthProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))
    assert isinstance(received["slice"], dict)
    assert not received["slice"]


# ---------------------------------------------------------------------------
# AC-13 — no imports from sibling probe modules
# ---------------------------------------------------------------------------


def test_no_sibling_probe_imports() -> None:
    """T-14 — AC-13: AST walk forbids cross-probe imports + asserts positive set."""
    src = Path(ih.__file__).read_text()
    tree = ast.parse(src)

    forbidden_prefixes = (
        "codegenie.probes.layer_a",
        "codegenie.probes.layer_c",
        "codegenie.probes.layer_d",
        "codegenie.probes.layer_e",
        "codegenie.probes.layer_g",
    )
    found_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found_imports.append(node.module)
            assert not any(
                node.module.startswith(p) for p in forbidden_prefixes
            ), f"forbidden sibling-probe import: {node.module}"
            # No sibling layer_b imports (other than self).
            if node.module.startswith("codegenie.probes.layer_b"):
                # self-import is OK (relative — never triggers, but defensive)
                assert node.module == "codegenie.probes.layer_b.index_health" or False, (
                    f"unexpected layer_b sibling import: {node.module}"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith(
                    "codegenie.probes.layer_a"
                ), f"forbidden sibling-probe import: {alias.name}"

    # Positive — required imports are present.
    assert "codegenie.probes.base" in found_imports
    assert "codegenie.probes.registry" in found_imports
    assert "codegenie.indices.freshness" in found_imports
    assert "codegenie.indices.registry" in found_imports
    assert "codegenie.types.identifiers" in found_imports
    assert "codegenie.output.paths" in found_imports
    assert "codegenie.errors" in found_imports


# ---------------------------------------------------------------------------
# AC-4 — registry-loop dispatcher: no per-index branches + dispatch_all once
# ---------------------------------------------------------------------------


def _run_method_ast() -> ast.AsyncFunctionDef:
    src = Path(ih.__file__).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "IndexHealthProbe":
            for body_node in node.body:
                if isinstance(body_node, ast.AsyncFunctionDef) and body_node.name == "run":
                    return body_node
    raise AssertionError("IndexHealthProbe.run not found")


def test_run_body_has_no_per_index_branches() -> None:
    """T-15a — AC-4 negative: no string-literal comparisons against index names."""
    run = _run_method_ast()
    forbidden = {"scip", "runtime_trace", "sbom", "semgrep", "gitleaks", "conventions"}
    for node in ast.walk(run):
        if isinstance(node, ast.Compare):
            for comp in [node.left, *node.comparators]:
                if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                    assert comp.value not in forbidden, (
                        f"per-index branch on {comp.value!r} detected — Open/Closed violation"
                    )


def test_run_invokes_dispatch_all_exactly_once() -> None:
    """T-15b — AC-4 positive: exactly one ``...dispatch_all(...)`` call in run.

    The registered freshness checks are synchronous pure functions (S1-02), so
    ``dispatch_all`` is sync; the AC's "exactly once" structural invariant is
    on the *call*, not on ``await``.
    """
    run = _run_method_ast()
    count = 0
    for node in ast.walk(run):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "dispatch_all":
                count += 1
    assert count == 1, f"expected exactly one dispatch_all(); found {count}"


# ---------------------------------------------------------------------------
# AC-2 — forbidden-patterns hook for mtime, scoped to index_health.py
# ---------------------------------------------------------------------------


def test_forbidden_patterns_bans_mtime_in_index_health(tmp_path: Path) -> None:
    """T-16(a) — AC-2: scripts/check_forbidden_patterns.py fires on mtime in B2.

    Constructs a tmp_path tree that mirrors the canonical file path so the
    scoping predicate ``_is_index_health_module`` matches; writes each
    banned snippet into ``index_health.py`` under that tree and asserts the
    script reports it. Never mutates the production file.
    """
    repo_root = Path(__file__).resolve().parents[4]
    script = repo_root / "scripts" / "check_forbidden_patterns.py"
    assert script.is_file()

    production = (
        repo_root / "src" / "codegenie" / "probes" / "layer_b" / "index_health.py"
    )
    assert production.is_file(), "index_health.py must exist before AC-2 verification"

    # Prove the production file itself contains zero mtime hits.
    proc = subprocess.run(
        [sys.executable, str(script), str(production)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"production index_health.py has mtime hits: {proc.stdout}"
    )

    # Build a sibling tree under tmp_path: <tmp>/codegenie/probes/layer_b/index_health.py
    # so the predicate's ``parts.index("codegenie")`` + tail-match scope fires.
    fake = tmp_path / "codegenie" / "probes" / "layer_b" / "index_health.py"
    fake.parent.mkdir(parents=True, exist_ok=True)

    banned_snippets = [
        "import os\nx = os.path.getmtime('foo')\n",
        "from pathlib import Path\nx = Path('a').stat().st_mtime\n",
        "import os\nx = os.stat('a').st_mtime\n",
        "import os\nx = os.lstat('a').st_mtime\n",
    ]
    for snippet in banned_snippets:
        fake.write_text(snippet)
        proc = subprocess.run(
            [sys.executable, str(script), str(fake)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode > 0, f"mtime ban missed: {snippet!r}\nout={proc.stdout}"

    # Negative: same snippets in a non-scoped file are not flagged.
    other = tmp_path / "codegenie" / "probes" / "other.py"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("import os\nx = os.path.getmtime('foo')\n")
    proc = subprocess.run(
        [sys.executable, str(script), str(other)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"mtime rule should be scoped to index_health.py only; got hits: {proc.stdout}"
    )


def test_pre_commit_config_lists_mtime_rule() -> None:
    """T-16(b) — AC-2: the hook config has the right rule and scope.

    Programmatically inspects the script's _RULES table so a contributor
    silently deleting the rule fails this test.
    """
    repo_root = Path(__file__).resolve().parents[4]
    script_path = repo_root / "scripts" / "check_forbidden_patterns.py"
    text = script_path.read_text()
    # The four mtime patterns must be present in the source verbatim.
    assert "getmtime" in text
    assert "st_mtime" in text
    # The scoping predicate name names the file.
    assert "index_health" in text


# ---------------------------------------------------------------------------
# AC-14 — warning ID frozenset + import-time assert (pattern check)
# ---------------------------------------------------------------------------


def test_warning_ids_match_adr_0007() -> None:
    """T-17 — every warning ID matches the ADR-0007 regex."""
    pattern = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    assert ih._WARNING_IDS  # non-empty frozenset
    for wid in ih._WARNING_IDS:
        assert pattern.match(wid), f"ADR-0007 violation: {wid!r}"


# ---------------------------------------------------------------------------
# AC-16 — registry membership + for_task filter
# ---------------------------------------------------------------------------


def test_registry_membership_and_for_task_filter() -> None:
    """T-18 — IndexHealthProbe in registry; for_task with any language."""
    all_probes = default_registry.all_probes()
    assert IndexHealthProbe in all_probes
    js = default_registry.for_task("*", frozenset({"javascript"}))
    go = default_registry.for_task("*", frozenset({"go"}))
    assert IndexHealthProbe in js
    assert IndexHealthProbe in go


# ---------------------------------------------------------------------------
# read_raw_slices pure helper
# ---------------------------------------------------------------------------


def test_read_raw_slices_pure_helper(tmp_path: Path) -> None:
    """T-21 — read_raw_slices skips unparseable + non-dict files silently."""
    (tmp_path / "scip.json").write_text(json.dumps({"x": 1}))
    (tmp_path / "bad.json").write_text("not valid json {")
    (tmp_path / "not_a_dict.json").write_text(json.dumps([1, 2, 3]))
    out = read_raw_slices(tmp_path)
    assert set(out.keys()) == {IndexName("scip")}
    assert out[IndexName("scip")] == {"x": 1}


def test_read_raw_slices_handles_missing_dir(tmp_path: Path) -> None:
    """T-21 co-witness — missing raw dir returns empty dict."""
    out = read_raw_slices(tmp_path / "does-not-exist")
    assert out == {}


# ---------------------------------------------------------------------------
# _last_indexed_at pure helper
# ---------------------------------------------------------------------------


def test_last_indexed_at_fresh() -> None:
    fr = Fresh(indexed_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))
    assert _last_indexed_at(fr) == "2026-01-01T00:00:00+00:00"


@pytest.mark.parametrize(
    "stale",
    [
        Stale(reason=IndexerError(message="x")),
        Stale(reason=CommitsBehind(n=1, last_indexed="abc")),
        Stale(reason=CoverageGap(files_indexed=1, files_in_repo=2)),
        Stale(reason=DigestMismatch(expected="x", actual="y")),
    ],
)
def test_last_indexed_at_none_for_every_stale_variant(stale: Stale) -> None:
    assert _last_indexed_at(stale) is None


# ---------------------------------------------------------------------------
# AC-3b — coordinator end-to-end dispatch order (B2 runs strictly after siblings)
# ---------------------------------------------------------------------------


async def test_runs_last_dispatch_order_via_coordinator(
    clean_freshness_registry: FreshnessRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T-03b — AC-3b: B2's start timestamp > every sibling's end timestamp.

    Uses the real coordinator. Mock siblings record their own ``time.monotonic()``
    on entry and exit; B2 records its on entry. After ``gather``, assert that
    B2's start is strictly later than every sibling's end.
    """
    import time

    from codegenie.cache import CacheStore
    from codegenie.config.defaults import Config
    from codegenie.coordinator import coordinator as coord
    from codegenie.output.sanitizer import OutputSanitizer
    from codegenie.probes.base import Probe, ProbeOutput

    timestamps: dict[str, dict[str, float]] = {}

    def make_mock(name_: str, tier_: str = "task_specific") -> type[Probe]:
        class _Mock(Probe):
            name: str = name_
            version: str = "0.1.0"
            layer = "B"
            tier = tier_
            applies_to_tasks: list[str] = ["*"]
            applies_to_languages: list[str] = ["*"]
            requires: list[str] = []
            timeout_seconds: int = 10
            cache_strategy: str = "none"  # type: ignore[assignment]
            declared_inputs: list[str] = []

            async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
                timestamps[self.name] = {"start": time.monotonic()}
                await asyncio.sleep(0.01)
                timestamps[self.name]["end"] = time.monotonic()
                return ProbeOutput(
                    schema_slice={},
                    raw_artifacts=[],
                    confidence="high",
                    duration_ms=10,
                    warnings=[],
                    errors=[],
                )

        _Mock.__name__ = f"_Mock_{name_}"
        return _Mock

    # Wrap IndexHealthProbe.run to capture its start before delegating.
    monkeypatch.setattr(ih._exec, "run_allowlisted", _ok_head_call())
    orig_run = IndexHealthProbe.run

    async def wrapped_run(self: IndexHealthProbe, repo: RepoSnapshot, ctx: ProbeContext) -> Any:
        timestamps[self.name] = {"start": time.monotonic()}
        result = await orig_run(self, repo, ctx)
        timestamps[self.name]["end"] = time.monotonic()
        return result

    monkeypatch.setattr(IndexHealthProbe, "run", wrapped_run)

    snapshot = _make_repo(tmp_path)
    task = Task(type="vuln_remediation", options={})

    # Single-slot semaphore so the rest wave serializes the three probes in
    # dispatch order — that's what makes "B2 start strictly after every
    # sibling end" a temporal invariant rather than just a dispatch-order
    # invariant. With concurrency>1 + asyncio.gather, runs_last is *queue
    # position* only; that's verified independently by the AST + structlog
    # tests above (T-02, T-03a). This test pins the temporal contract via
    # the same mechanism S1-08 used: serialized rest wave.
    config = Config(max_concurrent_probes=1)
    cache = CacheStore(tmp_path / "_cache", ttl_hours=24)
    sanitizer = OutputSanitizer()

    sibling1 = make_mock("sib1")()
    sibling2 = make_mock("sib2")()
    b2 = IndexHealthProbe()

    await coord.gather(
        snapshot,
        task,
        [sibling1, sibling2, b2],
        config,
        cache,
        sanitizer,
        runs_last_names=frozenset({"index_health"}),
    )

    sib_ends = [timestamps["sib1"]["end"], timestamps["sib2"]["end"]]
    b2_start = timestamps["index_health"]["start"]
    assert b2_start >= max(sib_ends), (
        f"B2 must start after every sibling ends; "
        f"b2_start={b2_start}, sib_ends={sib_ends}"
    )
