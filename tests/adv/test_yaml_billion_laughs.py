"""Adversarial: billion-laughs-shaped ``pnpm-lock.yaml`` triggers ``DepthCapExceeded``.

Pins ``phase-arch-design.md §"Adversarial tests"`` row 1 + ADR-0008's in-process
depth cap. The post-parse depth walker (``parsers/_depth.py``) is the
load-bearing defense — ``CSafeLoader`` has no native depth limit, so a YAML
DAG with extreme nesting passes the parse stage and is killed in the walker.

NOTE: alias-amplification (``*alias`` references resolving to a previously-
defined ``&anchor``) is NOT exercised here — that lives in
``tests/unit/parsers/test_safe_yaml.py::test_depth_walker_dedupes_alias_targets_no_amplification``.
This file exercises the depth ceiling only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from codegenie.errors import DepthCapExceeded
from codegenie.parsers import safe_yaml
from tests.adv._helpers import expected_lockfile_error_id, invoke_gather


def _billion_laughs_yaml(depth: int) -> bytes:
    """Pure builder: depth-N nested-list shape encoded as YAML.

    Constructs ``lockfileVersion: '6.0'\\nanchors: [[[..1..]]]\\n`` with
    ``depth`` left + right brackets — the depth-walker target. Plain depth
    (no anchors / no aliases) keeps this distinct from alias-amplification
    coverage in S1-03.
    """
    return f"lockfileVersion: '6.0'\nanchors: {'[' * depth}1{']' * depth}\n".encode()


@pytest.mark.adv
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="adversarial parser caps require POSIX O_NOFOLLOW semantics",
)
def test_billion_laughs_pnpm_lock_raises_depth_cap(tmp_path: Path) -> None:
    """AC-1 — direct ``safe_yaml.load`` raises ``DepthCapExceeded`` with
    the file path in the message.
    """
    f = tmp_path / "pnpm-lock.yaml"
    f.write_bytes(_billion_laughs_yaml(depth=200))
    with pytest.raises(DepthCapExceeded) as exc:
        safe_yaml.load(f, max_bytes=1_000_000, max_depth=64)
    # Markers-only contract per S1-01: the path lives in the message.
    assert str(f) in str(exc.value)


@pytest.mark.adv
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="adversarial parser caps require POSIX O_NOFOLLOW semantics",
)
def test_billion_laughs_under_gather_exits_zero_with_low_confidence(
    tmp_path: Path,
) -> None:
    """AC-1b — under the CLI, the hostile lockfile degrades the slice
    rather than crashing the gather. The typed-exception ID
    ``pnpm_lock.depth_cap_exceeded`` lands on ``manifests.errors``;
    ``manifests.warnings`` does NOT carry any cap_exceeded ID (ADR-0007:
    typed-exception IDs go to errors[], not warnings[]).
    """
    (tmp_path / "package.json").write_text('{"name": "x", "version": "0.0.0"}\n')
    (tmp_path / "pnpm-lock.yaml").write_bytes(_billion_laughs_yaml(depth=200))

    result = invoke_gather(tmp_path)
    assert result.exit_code == 0, result.output

    nm_manifests = result.context["probes"]["node_manifest"]["manifests"]
    expected = expected_lockfile_error_id("pnpm", DepthCapExceeded)
    # expected == "pnpm_lock.depth_cap_exceeded" (ADR-0007; node_manifest registry)
    assert nm_manifests["errors"] == [expected], nm_manifests
    # ADR-0007: typed-exception IDs go to errors[], not warnings[].
    assert all("cap_exceeded" not in w for w in nm_manifests.get("warnings", [])), nm_manifests
