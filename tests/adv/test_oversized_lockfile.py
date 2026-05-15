"""Adversarial: an oversized ``pnpm-lock.yaml`` triggers ``SizeCapExceeded``
**before** any bytes are parsed.

Pins ``phase-arch-design.md §"Adversarial tests"`` row 10 + ADR-0008's
pre-parse ``fstat`` defense (mirrored at the YAML boundary). Also pins
AC-13: the ``probe.parser.cap_exceeded`` structlog event records
``cap_kind == "size"``, ``cap == max_bytes``, and the absolute file path —
at both the ``safe_yaml`` and ``safe_json`` boundaries.

The patched ``yaml.load`` is the canary symmetric to AC-3's
``json.loads`` patch: a size-cap regression that reaches the parser fires
:class:`RuntimeError` instead of :class:`SizeCapExceeded`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from structlog.testing import capture_logs

from codegenie.errors import SizeCapExceeded
from codegenie.parsers import safe_json, safe_yaml
from tests.adv._helpers import (
    assert_parser_cap_event,
    expected_lockfile_error_id,
    invoke_gather,
)


def _write_padded_lockfile(path: Path, *, megabytes: int) -> None:
    """Stream ``megabytes`` MiB of YAML-comment padding to ``path``.

    Imperative shell — necessary for >tens-of-MB files. Body is comment
    lines (``# pad\\n``-style) so the bytes are valid YAML even though
    parsing must never happen (the size cap fires first).
    """
    line = b"# pad\n"
    line_count = (megabytes * 1024 * 1024) // len(line)
    chunk = line * 1024  # ~6 kB per chunk
    chunks = line_count // 1024
    with path.open("wb") as out:
        out.write(b"lockfileVersion: '6.0'\n")
        for _ in range(chunks):
            out.write(chunk)


@pytest.mark.adv
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="adversarial parser caps require POSIX O_NOFOLLOW semantics",
)
def test_oversized_lockfile_size_cap_pre_parse(tmp_path: Path) -> None:
    """AC-4 — direct ``safe_yaml.load`` raises :class:`SizeCapExceeded`
    before ``yaml.load`` is invoked; the patched ``yaml.load`` is the
    sentinel canary (a regression that reaches parse fires
    :class:`RuntimeError` instead).
    """
    f = tmp_path / "pnpm-lock.yaml"
    _write_padded_lockfile(f, megabytes=60)
    assert f.stat().st_size > 50_000_000

    # yaml.load is looked up dynamically by safe_yaml at call time;
    # patching the symbol on the `yaml` module catches the regression.
    with patch("yaml.load", side_effect=RuntimeError("yaml.load must not be reached")):
        with pytest.raises(SizeCapExceeded):
            safe_yaml.load(f, max_bytes=50_000_000)


@pytest.mark.adv
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="adversarial parser caps require POSIX O_NOFOLLOW semantics",
)
def test_oversized_lockfile_under_gather_degrades_node_manifest(
    tmp_path: Path,
) -> None:
    """AC-4b — under the CLI, the oversized lockfile lands the typed
    ``pnpm_lock.size_cap_exceeded`` ID on ``manifests.errors`` and gather
    still exits 0. Closed-world equality on the errors list — a regression
    that fires a different ID (or none) breaks the assertion.
    """
    (tmp_path / "package.json").write_text('{"name": "x", "version": "0.0.0"}\n')
    _write_padded_lockfile(tmp_path / "pnpm-lock.yaml", megabytes=60)

    result = invoke_gather(tmp_path)
    assert result.exit_code == 0, result.output

    nm_manifests = result.context["probes"]["node_manifest"]["manifests"]
    expected = expected_lockfile_error_id("pnpm", SizeCapExceeded)
    # expected == "pnpm_lock.size_cap_exceeded" (ADR-0007; node_manifest registry)
    assert nm_manifests["errors"] == [expected], nm_manifests


@pytest.mark.adv
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="adversarial parser caps require POSIX O_NOFOLLOW semantics",
)
def test_size_cap_event_payload_complete_safe_yaml(tmp_path: Path) -> None:
    """AC-13 (yaml boundary) — size-cap fires exactly one ``probe.parser.cap_exceeded``
    event with ``parser_kind == "safe_yaml"``, ``cap_kind == "size"``,
    ``cap == max_bytes``, ``path == str(absolute_path)``. The
    ``Literal["size", "depth"]`` on ``assert_parser_cap_event``'s ``cap_kind``
    is the type-level guard against ``cap_kind="bytes"`` drift.
    """
    f = tmp_path / "pnpm-lock.yaml"
    _write_padded_lockfile(f, megabytes=60)

    with capture_logs() as logs:
        with pytest.raises(SizeCapExceeded):
            safe_yaml.load(f, max_bytes=50_000_000)

    assert_parser_cap_event(
        logs,
        parser_kind="safe_yaml",
        cap_kind="size",
        cap=50_000_000,
        path=f,
    )


@pytest.mark.adv
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="adversarial parser caps require POSIX O_NOFOLLOW semantics",
)
def test_size_cap_event_payload_complete_safe_json(tmp_path: Path) -> None:
    """AC-13 (json boundary) — symmetric to the safe_yaml case. A 6 MB
    ``package.json`` trips the 5 MB cap; the structured payload pins
    ``parser_kind == "safe_json"``.
    """
    f = tmp_path / "package.json"
    f.write_bytes(b'{"x": "' + (b"a" * (6 * 1024 * 1024)) + b'"}')

    with capture_logs() as logs:
        with pytest.raises(SizeCapExceeded):
            safe_json.load(f, max_bytes=5_000_000)

    assert_parser_cap_event(
        logs,
        parser_kind="safe_json",
        cap_kind="size",
        cap=5_000_000,
        path=f,
    )
