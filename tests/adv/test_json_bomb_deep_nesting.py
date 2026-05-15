"""Adversarial: deeply-nested ``package.json`` triggers ``DepthCapExceeded``.

Pins ``phase-arch-design.md §"Adversarial tests"`` row 2 + ADR-0008's in-process
depth cap. ``json`` (the stdlib C extension) has no native depth limit, so
the post-parse depth walker in ``parsers/_depth.py`` is the load-bearing
defense. Test bytes are small (< 5 MB) — depth, not size, is what fires.

Also pins AC-14: the ``probe.parser.cap_exceeded`` structlog event records
``cap_kind == "depth"``, ``cap == max_depth``, and the absolute file path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from codegenie.errors import DepthCapExceeded
from codegenie.parsers import safe_json
from tests.adv._helpers import (
    assert_parser_cap_event,
    invoke_gather,
)


def _deeply_nested_package_json(depth: int) -> bytes:
    """Pure builder: depth-N ``{"a": {"a": {"a": ... 1 ...}}}`` mapping.

    A single innermost integer leaf at depth ``depth``. The whole payload
    is far under the 5 MB ``safe_json`` cap (each level adds 7 bytes of
    overhead — depth=200 is ≈ 1.4 kB). Bounded above by Python's
    ``json.loads`` recursive scanner (≈ 1000 frames); we only need depth
    > 64 to trigger the depth walker. 200 is the comfortable middle.
    """
    payload = "1"
    for _ in range(depth):
        payload = '{"a": ' + payload + "}"
    return payload.encode()


@pytest.mark.adv
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="adversarial parser caps require POSIX O_NOFOLLOW semantics",
)
def test_deeply_nested_package_json_raises_depth_cap(tmp_path: Path) -> None:
    """AC-2 — direct ``safe_json.load`` raises ``DepthCapExceeded`` on a
    depth-200 nested object; the file is well under the 5 MB size cap, so
    depth (not size) is what fired. (Story called for 10k; Python's
    ``json.loads`` recursive scanner caps at ~1000 frames, so we use 200 —
    far above the 64 ``max_depth`` cap, far below the parser ceiling.)
    """
    f = tmp_path / "package.json"
    payload = _deeply_nested_package_json(depth=200)
    f.write_bytes(payload)
    # Sanity: depth, not size, must be the cause of failure.
    assert f.stat().st_size < 5_000_000, f.stat().st_size

    with pytest.raises(DepthCapExceeded) as exc:
        safe_json.load(f, max_bytes=5_000_000)
    assert str(f) in str(exc.value)


@pytest.mark.adv
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="adversarial parser caps require POSIX O_NOFOLLOW semantics",
)
def test_deeply_nested_package_json_under_gather_degrades_node_manifest(
    tmp_path: Path,
) -> None:
    """AC-2b — under the CLI, both Layer-A Node probes (language_detection
    and node_manifest) read the deeply-nested ``package.json`` and demote
    via the AC-12 retrofit. The typed-exception ID lands on
    ``manifests.errors`` for ``node_manifest``; gather still exits 0.

    Without the AC-12 retrofit, ``DepthCapExceeded`` escapes the catch-tuple
    and the slice's ``errors`` list is empty — the closed-world assertion
    here is the canary.
    """
    f = tmp_path / "package.json"
    f.write_bytes(_deeply_nested_package_json(depth=200))

    result = invoke_gather(tmp_path)
    assert result.exit_code == 0, result.output

    # The slice errors live under `manifests.errors` (per the
    # `node_manifest.schema.json` shape). Closed-world equality kills the
    # "errors was empty because the retrofit was dropped" regression.
    nm_manifests = result.context["probes"]["node_manifest"]["manifests"]
    assert nm_manifests["errors"] == ["package_json.depth_cap_exceeded"], nm_manifests
    # primary short-circuits to null on package.json read failure.
    assert nm_manifests["primary"] is None, nm_manifests


@pytest.mark.adv
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="adversarial parser caps require POSIX O_NOFOLLOW semantics",
)
def test_depth_cap_event_payload_complete(tmp_path: Path) -> None:
    """AC-14 — depth-cap fires exactly one ``probe.parser.cap_exceeded``
    event with the full structured payload: ``parser_kind == "safe_json"``,
    ``cap_kind == "depth"``, ``cap == max_depth`` (the int passed in), and
    ``path == str(absolute_path)``. The ``Literal["size", "depth"]`` on
    ``assert_parser_cap_event``'s ``cap_kind`` is the type-level guard
    against ``cap_kind="bytes"`` drift.
    """
    f = tmp_path / "package.json"
    f.write_bytes(_deeply_nested_package_json(depth=200))

    with capture_logs() as logs:
        with pytest.raises(DepthCapExceeded):
            safe_json.load(f, max_bytes=5_000_000, max_depth=64)

    assert_parser_cap_event(
        logs,
        parser_kind="safe_json",
        cap_kind="depth",
        cap=64,
        path=f,
    )
