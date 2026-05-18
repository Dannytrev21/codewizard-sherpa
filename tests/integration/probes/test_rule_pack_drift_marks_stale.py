"""S6-08 AC-14a + AC-14b + AC-20 — load-bearing Open/Closed proof.

Two layers, parametrized across the three Phase-2 rule-pack /
catalog-versioned indices:

- **AC-14a (registry-level smoke).** Synthetic slice with both
  ``<version_key>`` and ``expected_<version_key>`` is dispatched
  through ``default_freshness_registry.dispatch_all`` directly; the
  per-scanner registration's logic is pinned in isolation.

- **AC-14b (end-to-end through ``IndexHealthProbe``).** The slice is
  written to the canonical raw/ location, B2 is instantiated and run
  via ``asyncio.run(probe.run(repo, ctx))``, and the typed
  ``Stale(DigestMismatch(...))`` shape is asserted on
  ``schema_slice["index_health"][name]["freshness"]``. This proves that
  B2 dispatches through the registry — a B2 that hard-coded only
  ``runtime_trace`` would pass AC-14a but fail this test.

- **AC-20 (bootstrap path).** With no ``expected_<version_key>`` in the
  slice (first gather), the freshness check returns ``Fresh()``. This
  is the documented bootstrap path, not a regression.

The slice files are written directly to raw/ rather than going through
the scanners (semgrep / gitleaks / conventions binaries are not assumed
present in CI). In production the scanners populate
``expected_<version_key>`` by reading the prior raw/{name}.json before
overwriting; the test fakes the post-gather state where both keys are
present.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path

import pytest

# Importing these modules triggers the @register_index_freshness_check
# side-effect — exactly what AC-12 pins as the deliverable contract.
import codegenie.conventions.loader  # noqa: F401
import codegenie.probes.layer_g.gitleaks  # noqa: F401
import codegenie.probes.layer_g.semgrep  # noqa: F401
from codegenie.indices.freshness import DigestMismatch, Fresh, Stale
from codegenie.indices.registry import default_freshness_registry
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_b.index_health import IndexHealthProbe
from codegenie.types.identifiers import IndexName

INDICES: list[tuple[str, str]] = [
    ("semgrep", "rule_pack_version"),
    ("gitleaks", "rule_pack_version"),
    ("conventions", "catalog_version"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_git_repo(root: Path) -> None:
    """Minimal git workdir so ``IndexHealthProbe`` can resolve HEAD."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "config", "user.name", "test"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "init"],
        check=True,
    )


def _write_slice(repo_root: Path, name: str, payload: dict[str, str]) -> None:
    raw = repo_root / ".codegenie" / "context" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{name}.json").write_text(json.dumps(payload, sort_keys=True))


def _make_repo_ctx(tmp_path: Path) -> tuple[RepoSnapshot, ProbeContext]:
    repo_root = tmp_path / "repo"
    repo = RepoSnapshot(
        root=repo_root,
        git_commit=None,
        detected_languages={},
        config={},
    )
    ctx = ProbeContext(
        cache_dir=tmp_path / ".cache",
        output_dir=tmp_path / ".out",
        workspace=tmp_path / ".work",
        logger=logging.getLogger("drift-test"),
        config={},
    )
    return repo, ctx


# ---------------------------------------------------------------------------
# AC-14a — registry-level smoke
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("index_name,version_key", INDICES)
def test_registry_dispatch_marks_index_stale_on_drift(index_name: str, version_key: str) -> None:
    """AC-14a. Per-scanner registration logic in isolation. Mutation
    caught: a regression in the per-scanner decorator body."""
    slice_ = {version_key: "v2", f"expected_{version_key}": "v1"}
    result = default_freshness_registry.dispatch_all(
        {IndexName(index_name): slice_}, head="deadbeef"
    )
    freshness = result[IndexName(index_name)]
    assert isinstance(freshness, Stale)
    assert isinstance(freshness.reason, DigestMismatch)
    assert freshness.reason.expected == "v1"
    assert freshness.reason.actual == "v2"


# ---------------------------------------------------------------------------
# AC-14b — end-to-end through IndexHealthProbe
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("index_name,version_key", INDICES)
def test_index_health_probe_marks_index_stale_on_drift(
    index_name: str, version_key: str, tmp_path: Path
) -> None:
    """AC-14b. The Open/Closed promise of AC-13 made observable at the
    probe level. A B2 that hard-codes only ``runtime_trace`` would pass
    AC-14a but fail this test."""
    repo, ctx = _make_repo_ctx(tmp_path)
    _init_git_repo(repo.root)
    _write_slice(
        repo.root,
        index_name,
        {version_key: "v2", f"expected_{version_key}": "v1"},
    )

    output = asyncio.run(IndexHealthProbe().run(repo, ctx))

    section = output.schema_slice["index_health"]
    assert index_name in section, (
        f"B2 did not dispatch {index_name!r} — Open/Closed promise broken."
    )
    freshness = section[index_name]["freshness"]
    assert freshness["kind"] == "stale"
    assert freshness["reason"]["kind"] == "digest_mismatch"
    assert freshness["reason"]["expected"] == "v1"
    assert freshness["reason"]["actual"] == "v2"


# ---------------------------------------------------------------------------
# AC-20 — first-gather bootstrap (Fresh)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("index_name,version_key", INDICES)
def test_first_gather_yields_fresh(index_name: str, version_key: str, tmp_path: Path) -> None:
    """AC-20. No ``expected_<version_key>`` in the slice (the scanner
    found no prior raw/{name}.json to read) → ``Fresh()``. Bootstrap
    is documented behaviour, not a regression."""
    repo, ctx = _make_repo_ctx(tmp_path)
    _init_git_repo(repo.root)
    _write_slice(repo.root, index_name, {version_key: "v1"})

    output = asyncio.run(IndexHealthProbe().run(repo, ctx))

    freshness = output.schema_slice["index_health"][index_name]["freshness"]
    assert freshness["kind"] == "fresh"


@pytest.mark.parametrize("index_name,version_key", INDICES)
def test_rule_pack_unchanged_yields_fresh(
    index_name: str, version_key: str, tmp_path: Path
) -> None:
    """AC-20. Both gathers agree on the version string → ``Fresh()``."""
    repo, ctx = _make_repo_ctx(tmp_path)
    _init_git_repo(repo.root)
    _write_slice(
        repo.root,
        index_name,
        {version_key: "v1", f"expected_{version_key}": "v1"},
    )

    output = asyncio.run(IndexHealthProbe().run(repo, ctx))

    freshness = output.schema_slice["index_health"][index_name]["freshness"]
    assert freshness["kind"] == "fresh"


# ---------------------------------------------------------------------------
# Registry-level bootstrap smoke (matches AC-14a in shape)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("index_name,version_key", INDICES)
def test_registry_dispatch_bootstrap_yields_fresh(index_name: str, version_key: str) -> None:
    """AC-20 at the registry layer: missing ``expected_<version_key>``
    is the bootstrap signal, not a tautology."""
    slice_ = {version_key: "v1"}
    result = default_freshness_registry.dispatch_all(
        {IndexName(index_name): slice_}, head="deadbeef"
    )
    freshness = result[IndexName(index_name)]
    assert isinstance(freshness, Fresh)
