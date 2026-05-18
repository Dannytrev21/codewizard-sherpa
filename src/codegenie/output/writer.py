"""Atomic ``repo-context.yaml`` writer (ADR-0008, ADR-0011, 02-ADR-0010, 02-ADR-0005).

Single chokepoint for YAML serialization in the entire package. The writer:

- Accepts ONLY :class:`~codegenie.output.redacted_slice.RedactedSlice`
  for the ``envelope`` parameter (02-ADR-0010 — type-level "redactor was
  called"). A raw ``dict`` is rejected at ``mypy --strict`` time (no
  structural-subtyping escape hatch) and at runtime via an
  ``isinstance`` guard that raises :class:`TypeError` with a message
  pointing back at 02-ADR-0010. The findings list lives only in memory
  per 02-ADR-0005 — the writer never sees it (it's the sibling tuple
  element of :func:`~codegenie.output.sanitizer.redact_secrets` and the
  smart-constructor refuses it).
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
- Serializes ``envelope.slice`` (the redacted payload) through
  ``yaml.CSafeDumper`` and falls back to ``yaml.SafeDumper`` on
  ``ImportError`` (libyaml missing), logging ``writer.csafe.unavailable``
  **exactly once per process** via a module- level flag so contributors
  aren't drowned in repeated warnings.
- Walks ``output_dir`` recursively after every write and applies ``0700`` to
  directories and ``0600`` to regular files — including children that
  pre-exist from a prior ``actions/cache`` restore (ADR-0011 edge case #6).
- Emits exactly ONE structured-log event ``envelope.written`` carrying
  ``secrets_redacted_count=<RedactedSlice.findings_count>`` on the
  success path (after ``_atomic_write_bytes`` returns). A 0-count run
  emits the field explicitly so ``grep secrets_redacted_count: <log>``
  remains an auditor's clean-run signal. Failure paths are silent on
  ``envelope.written`` per 02-ADR-0008's single-event discipline.
- After ``repo-context.yaml`` is published, the writer invokes
  ``codegenie.report.render_confidence_section`` on the in-memory
  envelope and persists ``CONTEXT_REPORT.md`` via the same ``.tmp →
  fsync → os.replace`` atomic pattern (S8-01). The canonical artifact is
  ``repo-context.yaml``; ``CONTEXT_REPORT.md`` is the human-readable
  companion. A renderer failure (defense-in-depth — the renderer
  promises never to raise) logs ``report.confidence_section.render_failed``
  and is otherwise non-fatal so ``repo-context.yaml`` integrity is never
  compromised by the companion artifact.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog
import yaml

from codegenie.logging import EVENT_ENVELOPE_WRITTEN, SECRETS_REDACTED_COUNT_FIELD
from codegenie.output.redacted_slice import RedactedSlice

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
    """Write ``payload`` to ``dest`` via per-writer ``.tmp`` + fsync + os.replace.

    The ``.tmp`` file is created with mode ``0o600`` so a crash between
    create and ``os.replace`` cannot leave a world-readable shadow. The
    tmp filename embeds ``os.getpid()`` + a random short token so two
    concurrent ``codegenie gather`` processes publishing the same
    destination do not collide on the shared tmp slot (edge case #12
    extended to the envelope-write path).
    """
    import secrets as _secrets

    tmp = dest.with_suffix(dest.suffix + f".{os.getpid()}.{_secrets.token_hex(4)}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(dest))


def _publish_context_report(envelope_slice: dict[str, Any], output_dir: Path) -> None:
    """Render and atomically publish ``CONTEXT_REPORT.md`` (S8-01).

    Imports the renderer lazily so a Phase-2 writer that ships before
    the consumer (or a future caller that monkey-patches the module)
    sees no module-import surprise. Renderer failures are best-effort
    and structurally-logged — the canonical ``repo-context.yaml`` is
    already on disk by the time we reach here.
    """
    try:
        from codegenie.report import render_confidence_section

        body = render_confidence_section(envelope_slice).encode("utf-8")
        _atomic_write_bytes(output_dir / "CONTEXT_REPORT.md", body)
    except Exception as exc:  # noqa: BLE001 — defense-in-depth, never fatal
        _log.warning(
            "report.confidence_section.render_failed",
            error_type=type(exc).__name__,
        )


def _fix_modes_recursively(root: Path) -> None:
    """Apply ``0o700`` to every dir and ``0o600`` to every file under ``root``.

    ``FileNotFoundError`` is tolerated mid-walk — another concurrent
    ``gather`` may publish + replace its own tmp slot between the
    ``os.walk`` snapshot and our ``os.chmod`` call.
    """
    try:
        os.chmod(root, 0o700)
    except FileNotFoundError:
        return
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            try:
                os.chmod(os.path.join(dirpath, d), 0o700)
            except FileNotFoundError:
                continue
        for f in filenames:
            try:
                os.chmod(os.path.join(dirpath, f), 0o600)
            except FileNotFoundError:
                continue


class Writer:
    """Atomic envelope + raw-artifact publisher."""

    def write(
        self,
        envelope: RedactedSlice,
        raw_artifacts: list[tuple[str, bytes]],
        output_dir: Path,
    ) -> None:
        """Publish raw artifacts then the envelope atomically.

        Order is load-bearing: raw artifacts first (each via its own
        ``.tmp → fsync → os.replace``), envelope last. A failed raw write
        propagates the ``OSError`` and the envelope never appears, so the
        caller detects partial state by envelope absence.
        """
        # 0. Runtime guard against raw-dict callers (defense in depth on top
        #    of the mypy --strict signature narrowing; Python type hints are
        #    stripped at runtime, so a non-type-checked caller could still
        #    pass a dict — 02-ADR-0010 names this as the chokepoint).
        if not isinstance(envelope, RedactedSlice):
            raise TypeError(
                f"Writer.write requires RedactedSlice (02-ADR-0010); got {type(envelope).__name__}"
            )

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
        body = yaml.dump(envelope.slice, Dumper=dumper, sort_keys=False).encode("utf-8")
        _atomic_write_bytes(output_dir / "repo-context.yaml", body)

        # 5.5. Render and publish the human-readable Confidence section
        #      companion (S8-01). The renderer is the type-level enforcement
        #      of B2's "honest confidence" commitment — every IndexFreshness
        #      variant is exhaustively pattern-matched. A renderer failure
        #      (defense-in-depth — the renderer is documented as
        #      never-raising) does NOT compromise repo-context.yaml.
        _publish_context_report(envelope.slice, output_dir)

        # 6. Re-apply modes recursively (ADR-0011 edge case #6).
        _fix_modes_recursively(output_dir)

        # 7. Success-path log event (02-ADR-0008 — single new field on a
        #    single new event; emitted only after ``_atomic_write_bytes``
        #    returns so a failed write is silent on ``envelope.written``).
        #    The constant pair is imported by name from ``codegenie.logging``
        #    so a typo at the call site is caught at import time and the
        #    audit-time grep target stays drift-resistant.
        _log.info(
            EVENT_ENVELOPE_WRITTEN,
            **{SECRETS_REDACTED_COUNT_FIELD: envelope.findings_count},
        )
