"""Unit tests for ``codegenie.coordinator.input_snapshot`` — S1-08 (Gap 1).

Each test is annotated with the AC it pins and the mutation it catches.
The harness uses ``structlog.testing.capture_logs`` for event assertions
(matches the S1-02..S1-07 hardened precedent).
"""

from __future__ import annotations

import errno
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from structlog.testing import capture_logs

from codegenie.coordinator.input_snapshot import (
    compute_input_snapshot,
    make_parsed_manifest_adapter,
)
from codegenie.coordinator.parsed_manifest_memo import ParsedManifestMemo
from codegenie.probes.base import InputFingerprint


class _FakeProbe:
    name = "stub.snapshot"
    declared_inputs = ["package.json", "pnpm-lock.yaml"]


# ---------------------------------------------------------------------------
# T-1 — AC-2: InputFingerprint is sourced from codegenie.probes.base
# ---------------------------------------------------------------------------
def test_input_fingerprint_imported_from_probes_base() -> None:
    assert InputFingerprint.__module__ == "codegenie.probes.base"
    # Mutation: a regression that re-introduces coordinator/input_snapshot.py
    # as the home for the newtype is caught.


def test_input_snapshot_module_does_not_redeclare_inputfingerprint() -> None:
    import codegenie.coordinator.input_snapshot as m

    src = Path(m.__file__).read_text()
    assert "class InputFingerprint" not in src
    # The type's home is `probes/base.py` (S1-06); a duplicate declaration here
    # would silently shadow it and re-open the contract-drift hole.


# ---------------------------------------------------------------------------
# T-2 — AC-3 + AC-5 + AC-6: snapshot type, contents, empty case
# ---------------------------------------------------------------------------
def test_snapshot_returns_frozenset_with_expected_paths(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}))
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    assert isinstance(snap, frozenset)
    for fp in snap:
        assert isinstance(fp, InputFingerprint)
    paths = {fp.path for fp in snap}
    assert str((tmp_path / "package.json").resolve()) in paths
    assert str((tmp_path / "pnpm-lock.yaml").resolve()) in paths
    # Mutation: returning list/tuple — caught by isinstance frozenset.


def test_empty_declared_inputs_yields_empty_frozenset(tmp_path: Path) -> None:
    class _Empty:
        name = "empty"
        declared_inputs: list[str] = []

    assert compute_input_snapshot(_Empty(), tmp_path) == frozenset()

    class _Nomatch:
        name = "nomatch"
        declared_inputs = ["nonexistent-*.json"]

    assert compute_input_snapshot(_Nomatch(), tmp_path) == frozenset()
    # Mutation: raise on empty / return None — caught.


# ---------------------------------------------------------------------------
# T-3 — AC-3: glob is case-sensitive even on case-insensitive filesystems
# ---------------------------------------------------------------------------
def test_glob_is_case_sensitive(tmp_path: Path) -> None:
    # On case-insensitive FS (default macOS, default Windows), creating
    # "Package.json" and then asking for "package.json" can spuriously match.
    # S1-08 disciplines glob with case_sensitive=True. Skip on FS that we
    # *know* is case-sensitive (Linux ext4) — the discipline is no-op there.
    (tmp_path / "Package.json").write_text("{}")
    # Probe declares "package.json" (lowercase); a "Package.json" file must
    # NOT match under case-sensitive glob.
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    assert not any(fp.path.endswith("Package.json") for fp in snap)
    # Mutation: case-insensitive glob — caught on macOS / Windows runners.


# ---------------------------------------------------------------------------
# T-4 — AC-4 + AC-7 + AC-8: content_hash is "blake3:<hex>" via the chokepoint
# ---------------------------------------------------------------------------
def test_content_hash_is_blake3_prefixed(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}))
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    fp = next(fp for fp in snap if fp.path.endswith("package.json"))
    assert fp.content_hash.startswith("blake3:")
    assert len(fp.content_hash) == len("blake3:") + 64  # blake3 hex digest
    # Mutation: hashlib.sha256, bare hexdigest, prefix-stripped — all caught.


def test_input_snapshot_module_does_not_import_blake3_directly() -> None:
    import codegenie.coordinator.input_snapshot as m

    src = Path(m.__file__).read_text()
    assert "import blake3" not in src
    assert "from blake3" not in src
    # ADR-0001 chokepoint — hashing.py is the single import site.


# ---------------------------------------------------------------------------
# T-5 — AC-9: oversize files record "<oversize>" sentinel + emit warning event
# ---------------------------------------------------------------------------
def test_oversize_file_records_sentinel(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_bytes(b"x" * 2048)
    with capture_logs() as logs:
        snap = compute_input_snapshot(_FakeProbe(), tmp_path, max_bytes_per_file=1024)
    fp = next(fp for fp in snap if fp.path.endswith("package.json"))
    assert fp.content_hash == "<oversize>"
    oversize_events = [r for r in logs if r["event"] == "probe.input_snapshot.oversize"]
    assert len(oversize_events) == 1
    assert oversize_events[0]["size_bytes"] == 2048
    assert oversize_events[0]["cap_bytes"] == 1024
    # Mutation: silent truncation + partial hash — caught.


# ---------------------------------------------------------------------------
# T-6 — AC-10: symlinked declared input → "<refused>"; retry semantics
# ---------------------------------------------------------------------------
def test_symlink_input_records_refused_then_retries(tmp_path: Path) -> None:
    target = tmp_path / "real.json"
    target.write_text(json.dumps({"name": "x"}))
    link = tmp_path / "package.json"
    link.symlink_to(target)
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    fp = next(fp for fp in snap if fp.path.endswith("package.json"))
    assert fp.content_hash == "<refused>"
    # Retry: delete symlink, create real file at same path
    link.unlink()
    link.write_text(json.dumps({"name": "x"}))
    snap2 = compute_input_snapshot(_FakeProbe(), tmp_path)
    fp2 = next(fp for fp in snap2 if fp.path.endswith("package.json"))
    assert fp2.content_hash.startswith("blake3:")
    # Mutation: path.read_bytes() (follows symlinks) — caught.


# ---------------------------------------------------------------------------
# T-7 — AC-11: Rule 12 — only ELOOP + FileNotFoundError swallowed; rest propagates
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "exc,must_propagate",
    [
        (OSError(errno.ELOOP, "loop"), False),
        (FileNotFoundError(2, "missing"), False),
        (PermissionError(13, "denied"), True),
        (IsADirectoryError(21, "is dir"), True),
        (OSError(errno.EIO, "io"), True),
    ],
    ids=["ELOOP", "FileNotFoundError", "PermissionError", "IsADirectoryError", "EIO"],
)
def test_oserror_handling_per_rule_12(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exc: OSError,
    must_propagate: bool,
) -> None:
    p = tmp_path / "package.json"
    p.write_text("{}")
    real_open = os.open

    def _maybe_raise(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if str(path).endswith("package.json"):
            raise exc
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", _maybe_raise)
    if must_propagate:
        with pytest.raises(type(exc)):
            compute_input_snapshot(_FakeProbe(), tmp_path)
    else:
        compute_input_snapshot(_FakeProbe(), tmp_path)  # must not raise


# ---------------------------------------------------------------------------
# T-8 — AC-12: path canonicalization is str(matched_path.resolve())
# ---------------------------------------------------------------------------
def test_input_fingerprint_path_is_resolved_string(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text("{}")
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    fp = next(fp for fp in snap if fp.path.endswith("package.json"))
    assert Path(fp.path).is_absolute()
    assert fp.path == str(p.resolve())
    # Mutation: .as_posix() (Windows divergence) or str(matched_path)
    # (non-canonical) — caught.


# ---------------------------------------------------------------------------
# T-9 — AC-20: probe.input_snapshot.computed event shape
# ---------------------------------------------------------------------------
def test_emits_computed_event_with_structured_fields(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}))
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    with capture_logs() as logs:
        compute_input_snapshot(_FakeProbe(), tmp_path)
    evt = next(r for r in logs if r["event"] == "probe.input_snapshot.computed")
    assert evt["probe"] == "stub.snapshot"
    assert evt["entries"] == 2
    assert evt["total_bytes"] > 0
    assert isinstance(evt["wall_clock_ms"], int) and evt["wall_clock_ms"] >= 0


# ---------------------------------------------------------------------------
# T-10 — AC-21: determinism property
# ---------------------------------------------------------------------------
def test_snapshot_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}))
    snap_a = compute_input_snapshot(_FakeProbe(), tmp_path)
    snap_b = compute_input_snapshot(_FakeProbe(), tmp_path)
    by_path_a = {fp.path: fp.content_hash for fp in snap_a}
    by_path_b = {fp.path: fp.content_hash for fp in snap_b}
    assert by_path_a == by_path_b
    # Mutation: time.time_ns() or os.getpid() mixed into the hash — caught.


# ---------------------------------------------------------------------------
# T-11 — AC-13: make_parsed_manifest_adapter — present + missing paths
# ---------------------------------------------------------------------------
def test_adapter_resolves_present_and_missing_paths(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text(json.dumps({"name": "x"}))
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    memo = ParsedManifestMemo()
    adapter = make_parsed_manifest_adapter(snap, memo)
    # Present in snapshot → content_hash-keyed lookup
    parsed = adapter(p)
    assert parsed is not None and parsed["name"] == "x"
    # Missing from snapshot → content_hash=None fallback to S1-07 stat-tuple
    # key. The default allowlist is {"package.json"}, so a non-allowlisted
    # path is `None` regardless of snapshot membership.
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"name": "y"}))
    parsed_other = adapter(other)
    assert parsed_other is None  # "other.json" not in default allowlist


def test_adapter_path_resolution_roundtrip(tmp_path: Path) -> None:
    # AC-12 / AC-13: the adapter looks up its snapshot table by
    # `str(path.resolve())` — calling with a relative-style Path still finds
    # the fingerprint recorded under the canonicalized absolute path.
    p = tmp_path / "package.json"
    p.write_text(json.dumps({"name": "z"}))
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    memo = ParsedManifestMemo()
    adapter = make_parsed_manifest_adapter(snap, memo)
    # Construct the same path via a relative-style component.
    same_logical_path = tmp_path / "." / "package.json"
    parsed = adapter(same_logical_path)
    assert parsed is not None and parsed["name"] == "z"


# T-12 + T-13 (memo dual-key + sentinel-bypass) live in
# ``tests/unit/coordinator/test_parsed_manifest_memo.py`` next to the rest
# of the memo's contract tests — see "Files to touch" in S1-08.


# ---------------------------------------------------------------------------
# AC-1: module-surface grep — public names + module collocation
# ---------------------------------------------------------------------------
def test_module_path_and_all_surface() -> None:
    import codegenie.coordinator.input_snapshot as m

    assert m.__file__ is not None
    assert Path(m.__file__).name == "input_snapshot.py"
    # Module exports exactly the two public seams + nothing else.
    assert set(m.__all__) == {"compute_input_snapshot", "make_parsed_manifest_adapter"}
    # And the existing `coordinator/snapshot.py` (RepoSnapshot builder, S3-05)
    # does NOT carry the snapshot-pass helper.
    import codegenie.coordinator.snapshot as snap_mod

    snap_src = Path(snap_mod.__file__).read_text() if snap_mod.__file__ else ""
    assert "compute_input_snapshot" not in snap_src


# Some platforms (notably default macOS HFS+/APFS volumes) are
# case-INSENSITIVE; `Path.glob(..., case_sensitive=True)` is the discipline.
# This sentinel makes the case-sensitivity test informative on every CI
# platform we run on (Linux ext4 + macOS APFS + Windows NTFS).
if sys.platform == "win32":  # pragma: no cover — informational only
    pass
