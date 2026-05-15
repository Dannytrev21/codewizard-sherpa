"""Adversarial: ``O_NOFOLLOW`` refuses a ``package.json`` symlink across three
defense layers.

Distinct surface from :mod:`tests.adv.test_symlink_escape` (S4-05, Phase 0),
which exercises the walker-side ``LanguageDetectionProbe._classify_symlink``
for *symlinks-elsewhere-in-walk*. This module exercises the **parser-side**
``os.open(..., O_NOFOLLOW)`` defense when the symlink IS ``package.json``
itself — i.e., the parser is asked to open a path whose final component is
a symlink. Three observation layers pin the same defense:

- Layer 1 — parser raises :class:`SymlinkRefusedError` (S1-02).
- Layer 2 — :class:`LanguageDetectionProbe` maps that to
  ``package_json.symlink_refused`` on ``ProbeOutput.errors`` with
  ``confidence: "low"`` (S2-01, ADR-0007).
- Layer 3 — gather completes (surviving-probe gate), the sentinel name +
  version + raw artifacts contain no bytes derived from the symlink
  target, and the structlog walker observable fires exactly once with no
  resolved-target leak (S5-03 §"Three-layer observation pattern").

The sentinel is structurally distinguishable (``"leaked-sentinel"``,
``"99.99.99-sentinel"``): without ``O_NOFOLLOW`` the parser reads the
sentinel JSON and ``_post_walk`` derives ``framework_hints`` from its
``scripts`` block — those bytes WOULD reach the YAML. With ``O_NOFOLLOW``,
ELOOP raises at ``os.open`` time and no bytes are read.
"""

from __future__ import annotations

import asyncio
import os
import sys
from logging import getLogger
from pathlib import Path
from typing import Any, Final

import pytest
from structlog.testing import capture_logs

from codegenie.errors import SymlinkRefusedError
from codegenie.parsers import safe_json
from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.language_detection import LanguageDetectionProbe
from tests.adv._helpers import invoke_gather

# --- module fixtures --------------------------------------------------------

_SENTINEL_JSON: Final[str] = (
    '{"name": "leaked-sentinel", "version": "99.99.99-sentinel", '
    '"scripts": {"start": "leaked-sentinel"}}'
)
"""Sentinel package.json body — substrings provably absent from the gather
output under correct ``O_NOFOLLOW`` semantics. The name + version + a
script value all share the ``leaked-sentinel`` canary so a partial leak
(e.g., a probe reads ``"name"`` only) still fails AC-3."""


def _sentinel_path(tmp_path: Path) -> Path:
    """Sentinel lives at ``tmp_path.parent`` so the symlink target is
    OUTSIDE the analyzed repo (the whole point of the test)."""
    return tmp_path.parent / "S5-03-leaked-sentinel.json"


def _setup_symlink_fixture(tmp_path: Path) -> Path:
    sentinel = _sentinel_path(tmp_path)
    sentinel.write_text(_SENTINEL_JSON, encoding="utf-8")
    link = tmp_path / "package.json"
    os.symlink(str(sentinel), str(link))
    return sentinel


def _build_ctx(repo: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=repo / ".cache",
        output_dir=repo / ".out",
        workspace=repo / ".ws",
        logger=getLogger("test"),
        config={},
    )


# --- Layer 1 — parser-level pin ---------------------------------------------


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only O_NOFOLLOW semantics")
def test_safe_json_refuses_package_json_symlink(tmp_path: Path) -> None:
    """AC-1 — parser raises :class:`SymlinkRefusedError` on ``O_NOFOLLOW``
    ELOOP; the link path appears in the marker message (S1-02 AC-5).

    Catches: a regression that drops ``O_NOFOLLOW`` from the ``os.open``
    flags — the parser would succeed and return the sentinel dict, the
    raise never fires.
    """
    sentinel = _setup_symlink_fixture(tmp_path)
    try:
        with pytest.raises(SymlinkRefusedError, match=str(tmp_path / "package.json")):
            safe_json.load(tmp_path / "package.json", max_bytes=5_000_000)
    finally:
        sentinel.unlink(missing_ok=True)


# --- Layer 2 — probe-level mapping ------------------------------------------


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only O_NOFOLLOW semantics")
def test_language_detection_surfaces_symlink_refused_on_errors(tmp_path: Path) -> None:
    """AC-2 — :class:`LanguageDetectionProbe` maps ``SymlinkRefusedError``
    to ``package_json.symlink_refused`` on ``ProbeOutput.errors`` with
    ``confidence: "low"``.

    Closed-world assertion: ``out.errors == ["package_json.symlink_refused"]``
    AND ``out.warnings == []`` AND ``out.confidence == "low"``. Typed-exception
    IDs land on ``errors[]`` per ADR-0007; ``schema_slice.*.warnings`` is the
    soft-degrade vocabulary and stays empty for this failure mode.

    Convention: ``asyncio.run(probe.run(...))`` not ``pytest.mark.asyncio``
    (Rule 11; mirrors ``tests/unit/probes/test_node_build_system.py:93``).
    """
    sentinel = _setup_symlink_fixture(tmp_path)
    try:
        repo = RepoSnapshot(root=tmp_path, git_commit=None, detected_languages={}, config={})
        ctx = _build_ctx(tmp_path)
        out: ProbeOutput = asyncio.run(LanguageDetectionProbe().run(repo, ctx))
        assert out.errors == ["package_json.symlink_refused"], out.errors
        assert out.confidence == "low", out.confidence
        assert out.warnings == [], out.warnings
    finally:
        sentinel.unlink(missing_ok=True)


# --- Layer 3 — CLI data-leak canary + structlog observable ------------------


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only O_NOFOLLOW semantics")
def test_gather_under_symlink_no_sentinel_leak(tmp_path: Path) -> None:
    """AC-3 + AC-4 — gather completes, sentinel content never reaches the
    YAML / raw artifacts / audit record, and the walker observable fires
    exactly once without a resolved-target leak.

    The smoking-gun is structural: without ``O_NOFOLLOW``, the parser
    successfully reads the sentinel and ``_post_walk`` derives
    ``framework_hints`` from the ``scripts`` block — those bytes WOULD
    surface as ``primary == "leaked-sentinel"``-shaped slice fields. With
    ``O_NOFOLLOW``, ``framework_hints`` stays empty and no sentinel byte
    enters the slice.
    """
    sentinel = _setup_symlink_fixture(tmp_path)
    try:
        with capture_logs() as logs:
            result = invoke_gather(tmp_path)

        # (i) Surviving-probe gate stays green.
        assert result.exit_code == 0, (result.exit_code, result.output)

        # (ii) - (iv) sentinel substrings absent from every emitted byte:
        # YAML envelope, every raw-artifact JSON, every per-run audit record.
        scanned_bytes = [result.context_yaml_text, *result.raw_jsons.values()]
        runs_dir = tmp_path / ".codegenie" / "context" / "runs"
        if runs_dir.is_dir():
            for run_json in sorted(runs_dir.iterdir()):
                if run_json.is_file():
                    scanned_bytes.append(run_json.read_text(encoding="utf-8"))
        all_text = "\n".join(scanned_bytes)
        assert "leaked-sentinel" not in all_text, "sentinel name reached gather output"
        # (v) second-axis canary — pins the version-only leak path.
        assert "99.99.99-sentinel" not in all_text, "sentinel version reached gather output"

        # AC-4: walker observable fires exactly once, no resolved-target leak.
        escaped = [e for e in logs if e.get("event") == "probe.symlink.escaped"]
        assert len(escaped) == 1, f"expected 1 probe.symlink.escaped event, got {escaped!r}"
        assert escaped[0].get("path") == "package.json", escaped[0]
        ev_repr = repr(escaped[0])
        assert str(sentinel) not in ev_repr, f"resolved target leaked into event payload: {ev_repr}"
        assert "S5-03-leaked-sentinel" not in ev_repr, f"sentinel filename leaked: {ev_repr}"

        # AC-4: no cap_exceeded events — the parser raises ELOOP, not size-cap.
        cap_events: list[Any] = [e for e in logs if e.get("event") == "probe.parser.cap_exceeded"]
        assert cap_events == [], f"unexpected cap_exceeded events: {cap_events!r}"
    finally:
        sentinel.unlink(missing_ok=True)
