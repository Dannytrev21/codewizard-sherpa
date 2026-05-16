"""``Writer.write`` — atomic publish with symlink refusal and mode discipline.

Pins ACs 14-22, 24-25 from story S3-03 (Phase 0): CSafeDumper-first YAML
serialization, fsync→replace ordering, raw-then-yaml publish order,
partial-failure modes, symlink refusal at three paths, raw-name safety,
``_csafe_warned`` once-per-process, recursive chmod tree-walk (edge case
#6), empty inputs.

Phase 2 (S3-03 of phase 02-context-gather-layers-b-g) tightened
:meth:`Writer.write`'s ``envelope`` parameter to
:class:`~codegenie.output.redacted_slice.RedactedSlice`. The fixture
below constructs a real ``RedactedSlice`` via the only public path —
``redact_secrets`` — so this file continues to exercise the writer
against the same conceptual payload it always has, just wrapped in the
type-level guarantee.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import structlog.testing
import yaml

import codegenie.output.writer as writer_mod
from codegenie.errors import SymlinkRefusedError
from codegenie.output.redacted_slice import RedactedSlice
from codegenie.output.sanitizer import redact_secrets
from codegenie.output.writer import Writer
from codegenie.types.identifiers import ProbeId

ENV_DICT: dict[str, Any] = {"schema_version": "0.1.0", "probes": {}}
ENV: RedactedSlice
ENV, _ENV_FINDINGS = redact_secrets(ENV_DICT, ProbeId("__envelope__"))


# AC-14 + AC-15 — happy-path write produces valid YAML via CSafe or Safe
def test_writer_writes_yaml_via_csafe_or_safe(tmp_path: Path) -> None:
    Writer().write(envelope=ENV, raw_artifacts=[], output_dir=tmp_path)
    body = (tmp_path / "repo-context.yaml").read_text()
    assert yaml.safe_load(body) == ENV.slice


# AC-22 — modes applied recursively to a new tree
def test_writer_modes_applied_recursively_to_new_tree(tmp_path: Path) -> None:
    raws = [("a.json", b"{}"), ("nested.json", b"{}")]
    Writer().write(envelope=ENV, raw_artifacts=raws, output_dir=tmp_path)
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700
    for p in tmp_path.rglob("*"):
        mode = stat.S_IMODE(p.stat().st_mode)
        if p.is_dir():
            assert mode == 0o700, f"{p} dir mode {oct(mode)}"
        else:
            assert mode == 0o600, f"{p} file mode {oct(mode)}"


def test_writer_fixes_preexisting_loose_modes(tmp_path: Path) -> None:
    """AC-22 edge case #6: post-CI-cache-restore mode flattening."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(mode=0o755)
    preexist = raw_dir / "stale.json"
    preexist.write_bytes(b"{}")
    os.chmod(preexist, 0o644)
    Writer().write(envelope=ENV, raw_artifacts=[], output_dir=tmp_path)
    assert stat.S_IMODE(raw_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(preexist.stat().st_mode) == 0o600


# AC-16 — fsync called before replace
def test_writer_fsync_called_before_replace(tmp_path: Path) -> None:
    manager = mock.Mock()
    with (
        mock.patch.object(writer_mod.os, "fsync", wraps=os.fsync) as fsync_spy,
        mock.patch.object(writer_mod.os, "replace", wraps=os.replace) as replace_spy,
    ):
        manager.attach_mock(fsync_spy, "fsync")
        manager.attach_mock(replace_spy, "replace")
        Writer().write(envelope=ENV, raw_artifacts=[], output_dir=tmp_path)
    names = [c[0] for c in manager.mock_calls]
    assert names.index("fsync") < names.index("replace")


# AC-17 — raws replaced before yaml
def test_writer_replaces_raws_before_yaml(tmp_path: Path) -> None:
    seen: list[str] = []
    real_replace = os.replace

    def spy(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        seen.append(Path(dst).name)
        real_replace(src, dst)

    with mock.patch.object(writer_mod.os, "replace", side_effect=spy):
        Writer().write(
            envelope=ENV,
            raw_artifacts=[("a.json", b"{}"), ("b.json", b"{}")],
            output_dir=tmp_path,
        )
    assert seen[-1] == "repo-context.yaml"
    assert all(n != "repo-context.yaml" for n in seen[:-1])
    assert "a.json" in seen
    assert "b.json" in seen


# AC-18 — partial-raw failure leaves envelope absent
def test_writer_partial_raw_failure_no_envelope(tmp_path: Path) -> None:
    call_count = {"n": 0}
    real_replace = os.replace

    def maybe_fail(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        call_count["n"] += 1
        if call_count["n"] == 2 and Path(dst).name != "repo-context.yaml":
            raise OSError("simulated disk full mid-raw")
        real_replace(src, dst)

    with (
        mock.patch.object(writer_mod.os, "replace", side_effect=maybe_fail),
        pytest.raises(OSError),
    ):
        Writer().write(
            envelope=ENV,
            raw_artifacts=[("a.json", b"{}"), ("b.json", b"{}")],
            output_dir=tmp_path,
        )
    assert not (tmp_path / "repo-context.yaml").exists()


# AC-19 — envelope replace failure: no yaml, no insecure-mode leak
def test_writer_envelope_replace_failure_no_partial_yaml(tmp_path: Path) -> None:
    real_replace = os.replace

    def fail_yaml(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        if Path(dst).name == "repo-context.yaml":
            raise OSError("simulated")
        real_replace(src, dst)

    with (
        mock.patch.object(writer_mod.os, "replace", side_effect=fail_yaml),
        pytest.raises(OSError),
    ):
        Writer().write(envelope=ENV, raw_artifacts=[], output_dir=tmp_path)
    assert not (tmp_path / "repo-context.yaml").exists()
    tmp = tmp_path / "repo-context.yaml.tmp"
    if tmp.exists():
        assert stat.S_IMODE(tmp.stat().st_mode) == 0o600


# AC-20 — symlink refusal at three planted locations
@pytest.mark.parametrize("victim", ["output_dir", "raw", "repo-context.yaml"])
def test_writer_refuses_symlink_planted(tmp_path: Path, victim: str) -> None:
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    decoy_file = sentinel / "decoy.txt"
    decoy_file.write_bytes(b"original")
    out_dir = tmp_path / "out"
    if victim == "output_dir":
        out_dir.symlink_to(sentinel)
    else:
        out_dir.mkdir(mode=0o700)
        target = out_dir / ("raw" if victim == "raw" else "repo-context.yaml")
        if victim == "raw":
            target.symlink_to(sentinel)
        else:
            target.symlink_to(decoy_file)
    with pytest.raises(SymlinkRefusedError):
        Writer().write(envelope=ENV, raw_artifacts=[], output_dir=out_dir)
    assert decoy_file.read_bytes() == b"original"
    # No .tmp produced anywhere under tmp_path that isn't a deliberate sentinel.
    tmp_files = [p for p in tmp_path.rglob("*.tmp")]
    assert tmp_files == []


# AC-21 — raw-artifact filename safety
@pytest.mark.parametrize("bad", ["../escape.json", "/abs/path.json", "", "a/b/c.json", "."])
def test_writer_refuses_unsafe_raw_names(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError):
        Writer().write(envelope=ENV, raw_artifacts=[(bad, b"{}")], output_dir=tmp_path)
    assert not (tmp_path / "repo-context.yaml").exists()


# AC-15 — _csafe_warned: log once per process
def test_writer_csafe_unavailable_logs_once_per_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(writer_mod, "_csafe_warned", False, raising=False)

    def no_csafe() -> object:
        raise ImportError("no libyaml")

    monkeypatch.setattr(writer_mod, "_import_csafe_dumper", no_csafe)
    with structlog.testing.capture_logs() as captured:
        for sub in ("a", "b", "c"):
            d = tmp_path / sub
            d.mkdir()
            Writer().write(envelope=ENV, raw_artifacts=[], output_dir=d)
            assert (d / "repo-context.yaml").exists()
    events = [r for r in captured if r.get("event") == "writer.csafe.unavailable"]
    assert len(events) == 1


# AC-24 — empty inputs
def test_writer_empty_raws_creates_raw_dir_at_0700(tmp_path: Path) -> None:
    Writer().write(envelope=ENV, raw_artifacts=[], output_dir=tmp_path)
    raw = tmp_path / "raw"
    assert raw.is_dir() and not raw.is_symlink()
    assert stat.S_IMODE(raw.stat().st_mode) == 0o700


# AC-25 — happy-path writer emits zero error/refusal events
def test_writer_happy_path_emits_no_error_events(tmp_path: Path) -> None:
    with structlog.testing.capture_logs() as captured:
        Writer().write(
            envelope=ENV,
            raw_artifacts=[("a.json", b"{}")],
            output_dir=tmp_path,
        )
    bad = {"writer.symlink.refused", "writer.csafe.unavailable"}
    assert not [r for r in captured if r.get("event") in bad]
