"""S3-06 AC-6 — yarn-legacy parity smoke (probe-level integration).

This is **probe-level integration smoke** — *not* parser correctness.
Parser correctness is owned by S3-04's
``tests/unit/probes/_lockfiles/test_yarn_parser_parity.py`` with its
CI-enforced mutation gate. The job of this file is to prove the
``_yarn.parse`` *dispatcher* integrates correctly with the
``manifests`` slice plumbing under both code paths.

Two arms:

- **Arm 1 — pyarn arm** (``_HAS_PYARN=True``): proves ``pyarn.parse``
  is actually called when the optional extra is installed.
  ``mocker.spy(pyarn, "parse")`` + ``mocker.spy(_yarn,
  "_parse_handrolled")`` — pyarn spy count >= 1, hand-rolled spy count
  == 0. Skipped (with a clear reason) when ``pyarn`` is not installed.
- **Arm 2 — hand-rolled arm** (``_HAS_PYARN=False``): forces the
  fallback path via ``monkeypatch.setattr`` on the
  ``_yarn._HAS_PYARN`` module symbol. Hand-rolled spy count >= 1.
  **Never skipped** — runs in every CI matrix entry.

The byte-equal assertion runs **after** both spy assertions confirm
the arms exercised observably-distinct code paths. A naive byte-equal
only test would pass trivially under any "both arms use the same
parser" mutation; the spy choreography is what distinguishes the two
paths.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from codegenie.cli import cli
from codegenie.probes._lockfiles import _yarn
from tests.integration.probes.conftest import _copy_tree, _load_envelope

FIXTURE: Path = Path(__file__).resolve().parent.parent.parent / "fixtures" / "node_yarn_legacy"


class _CallCounter:
    """Minimal call-counting wrapper — pytest-mock is not in the dev
    extras, so we inline the smallest equivalent for the spy pattern
    AC-6 requires (call-count + call-through to the wrapped function).
    """

    __slots__ = ("call_count", "_wrapped")

    def __init__(self, wrapped: Callable[..., Any]) -> None:
        self.call_count = 0
        self._wrapped = wrapped

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.call_count += 1
        return self._wrapped(*args, **kwargs)


def _spy(monkeypatch: pytest.MonkeyPatch, target: object, attr: str) -> _CallCounter:
    """Install a call-counter on ``target.attr`` that delegates to the original."""
    original = getattr(target, attr)
    counter = _CallCounter(original)
    monkeypatch.setattr(target, attr, counter)
    return counter


def _manifests_slice_bytes(repo: Path) -> bytes:
    """Return the deterministic YAML serialization of the
    ``manifests`` slice (the unit of the AC-6 byte-equal comparison)."""
    envelope = _load_envelope(repo)
    manifests = envelope["probes"]["node_manifest"]["manifests"]
    return yaml.safe_dump(manifests, sort_keys=True).encode("utf-8")


@pytest.mark.skipif(not _yarn._HAS_PYARN, reason="pyarn extra not installed; pyarn arm cannot run")
def test_pyarn_arm_uses_pyarn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-6 Arm 1 — pyarn arm exercises ``_pyarn_parse`` (not the fallback).

    Spies on the two module-internal dispatch endpoints
    (:func:`codegenie.probes._lockfiles._yarn._pyarn_parse` and
    :func:`codegenie.probes._lockfiles._yarn._parse_handrolled`) — they
    are the observable boundary between the two code paths the
    dispatcher selects via ``_HAS_PYARN``.
    """
    pyarn_spy = _spy(monkeypatch, _yarn, "_pyarn_parse")
    hr_spy = _spy(monkeypatch, _yarn, "_parse_handrolled")
    repo = _copy_tree(FIXTURE, tmp_path / "repo")

    result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
    assert result.exit_code == 0, result.output

    # AC-6 mutation killer 1: arm must actually exercise pyarn
    assert pyarn_spy.call_count >= 1, "pyarn arm did not invoke pyarn.parse"
    # AC-6 mutation killer 2: no silent fallback to hand-rolled
    assert hr_spy.call_count == 0, (
        f"pyarn arm leaked into hand-rolled path (call_count={hr_spy.call_count})"
    )


def test_handrolled_arm_uses_handrolled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-6 Arm 2 — hand-rolled arm exercises ``_parse_handrolled``.

    Never skipped: ``_HAS_PYARN`` is forced to ``False`` regardless of
    the matrix entry's install state, so this arm runs in every CI job.
    """
    monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    hr_spy = _spy(monkeypatch, _yarn, "_parse_handrolled")
    repo = _copy_tree(FIXTURE, tmp_path / "repo")

    result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
    assert result.exit_code == 0, result.output

    assert hr_spy.call_count >= 1, "hand-rolled arm did not invoke _parse_handrolled"


def test_two_arms_produce_byte_equal_manifests_slice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-6 byte-equal assertion across both code paths.

    Runs sequentially in two ``tmp_path`` subdirs (the spy assertions
    live in their own tests; this one's contract is the *output*
    equality only). Always exercises the hand-rolled arm; the pyarn
    arm runs whenever the extra is installed in the matrix entry.
    """
    repo_a = _copy_tree(FIXTURE, tmp_path / "arm_a")
    # Arm A — pyarn arm (or hand-rolled if pyarn not installed; either
    # way the bytes recorded are the *production* output for the
    # current matrix entry, which is what we compare against the
    # forced-hand-rolled re-run).
    result_a = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo_a)])
    assert result_a.exit_code == 0, result_a.output
    bytes_a = _manifests_slice_bytes(repo_a)

    # Arm B — forced hand-rolled.
    monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    repo_b = _copy_tree(FIXTURE, tmp_path / "arm_b")
    result_b = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo_b)])
    assert result_b.exit_code == 0, result_b.output
    bytes_b = _manifests_slice_bytes(repo_b)

    assert bytes_a == bytes_b, (
        "manifests slice differs between yarn-parser arms; "
        f"len(a)={len(bytes_a)} len(b)={len(bytes_b)}"
    )
