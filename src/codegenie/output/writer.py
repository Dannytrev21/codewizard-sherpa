"""Atomic ``repo-context.yaml`` writer (ADR-0008, ADR-0011).

Single chokepoint for YAML serialization in the entire package. The writer:

- Refuses to follow symlinks at ``output_dir``, ``output_dir/raw/``, or
  ``output_dir/repo-context.yaml`` — pre-check **before** any write, raising
  :class:`~codegenie.errors.SymlinkRefusedError` and emitting
  ``writer.symlink.refused`` (ADR-0011 §Symlink refusal).
- Validates every raw-artifact leaf name (``..``, ``/``, empty, ``.``)
  before any IO — closes the chokepoint property of ADR-0008 (the writer is
  the only place leaf names hit disk).
- Publishes each raw artifact atomically via ``<dest>.tmp → os.fsync →
  os.replace``, **then** the envelope ``repo-context.yaml`` last — so if a
  raw write fails the envelope never appears (callers detect partial state
  by envelope absence).
- Serializes the envelope through ``yaml.CSafeDumper`` and falls back to
  ``yaml.SafeDumper`` on ``ImportError`` (libyaml missing), logging
  ``writer.csafe.unavailable`` **exactly once per process** via a module-
  level flag so contributors aren't drowned in repeated warnings.
- Walks ``output_dir`` recursively after every write and applies ``0700`` to
  directories and ``0600`` to regular files — including children that
  pre-exist from a prior ``actions/cache`` restore (ADR-0011 edge case #6).

ADR-0008 §Consequences line 46 reads "``Writer.write`` takes a
``SanitizedProbeOutput``" — that is undeliverable as written because the
writer is downstream of an N-to-1 merge that loses per-probe typing. The
typed-enforcement *intent* survives upstream at
:meth:`~codegenie.output.sanitizer.OutputSanitizer.scrub`; the envelope
arriving here is the merged ``dict`` the coordinator produces. Story S3-03
surfaces this as a follow-up ADR amendment.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog
import yaml

__all__ = ["Writer"]

_log = structlog.get_logger(__name__)

# Module-level flag — the CSafeDumper-fallback warning fires exactly once
# per Python process (AC-15). A function-local flag (or no flag) would emit
# the warning on every ``write()`` call, teaching contributors to ignore it.
_csafe_warned: bool = False


def _import_csafe_dumper() -> Any:
    """Return ``yaml.CSafeDumper`` if libyaml is available.

    Indirection point for tests (AC-15 patches ``_import_csafe_dumper`` to
    simulate the libyaml-missing branch without monkeypatching ``yaml``).
    """
    return yaml.CSafeDumper


def _select_dumper() -> Any:
    """Return CSafeDumper if available, else SafeDumper (logs once)."""
    global _csafe_warned
    try:
        return _import_csafe_dumper()
    except ImportError:
        if not _csafe_warned:
            _log.warning("writer.csafe.unavailable")
            _csafe_warned = True
        return yaml.SafeDumper


def _assert_safe_name(name: str) -> None:
    """Raise ``ValueError`` on raw-artifact leaf names that aren't safe."""
    if not name:
        raise ValueError("raw artifact name must be non-empty")
    if name in {".", ".."}:
        raise ValueError(f"raw artifact name must not be {name!r}")
    if "/" in name or "\\" in name:
        raise ValueError(f"raw artifact name must be a leaf (no separators): {name!r}")
    if name.startswith("."):
        # Dotfiles aren't strictly unsafe, but a leading-dot collision with
        # the writer's own ``.tmp`` shadow files is real — reject defensively.
        if name.endswith(".tmp"):
            raise ValueError(f"raw artifact name must not end with .tmp: {name!r}")


def _refuse_if_symlink(path: Path) -> None:
    if path.is_symlink():
        _log.warning("writer.symlink.refused", path=str(path))
        from codegenie.errors import SymlinkRefusedError

        raise SymlinkRefusedError(str(path))


def _atomic_write_bytes(dest: Path, payload: bytes) -> None:
    """Write ``payload`` to ``dest`` via ``.tmp → fsync → os.replace``.

    The ``.tmp`` file is created with mode ``0o600`` so a crash between
    create and ``os.replace`` cannot leave a world-readable shadow.
    """
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(dest))


def _fix_modes_recursively(root: Path) -> None:
    """Apply ``0o700`` to every dir and ``0o600`` to every file under ``root``."""
    os.chmod(root, 0o700)
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), 0o700)
        for f in filenames:
            os.chmod(os.path.join(dirpath, f), 0o600)


class Writer:
    """Atomic envelope + raw-artifact publisher."""

    def write(
        self,
        envelope: dict[str, Any],
        raw_artifacts: list[tuple[str, bytes]],
        output_dir: Path,
    ) -> None:
        """Publish raw artifacts then the envelope atomically.

        Order is load-bearing: raw artifacts first (each via its own
        ``.tmp → fsync → os.replace``), envelope last. A failed raw write
        propagates the ``OSError`` and the envelope never appears, so the
        caller detects partial state by envelope absence.
        """
        # 1. Pre-write symlink refusal at three planted shapes.
        _refuse_if_symlink(output_dir)
        if output_dir.exists():
            _refuse_if_symlink(output_dir / "raw")
            _refuse_if_symlink(output_dir / "repo-context.yaml")

        # 2. Validate every raw-artifact name before any IO.
        for name, _payload in raw_artifacts:
            _assert_safe_name(name)

        # 3. Ensure output tree exists with tight modes.
        output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        raw_dir = output_dir / "raw"
        _refuse_if_symlink(raw_dir)
        raw_dir.mkdir(mode=0o700, exist_ok=True)

        # 4. Publish raws first.
        for name, payload in raw_artifacts:
            _atomic_write_bytes(raw_dir / name, payload)

        # 5. Serialize + publish the envelope last.
        dumper = _select_dumper()
        body = yaml.dump(envelope, Dumper=dumper, sort_keys=False).encode("utf-8")
        _atomic_write_bytes(output_dir / "repo-context.yaml", body)

        # 6. Re-apply modes recursively (ADR-0011 edge case #6).
        _fix_modes_recursively(output_dir)
