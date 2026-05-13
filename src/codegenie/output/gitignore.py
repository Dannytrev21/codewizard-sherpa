""".gitignore mutation routine for the analyzed repository.

Implements the ``.codegenie/`` entry append described by:

- ``CLAUDE.md`` §Conventions — "offer to add it to that repo's .gitignore on
  first run".
- ``docs/phases/00-bullet-tracer-foundations/final-design.md`` §2.15 — the
  prompt routine spec; TTY vs non-TTY policy.
- ``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md`` §Harness
  engineering — Idempotence (line-anchored match, NOT a file-substring) and
  §Edge cases row 8 (append failure on disk-full → warn + continue, gather
  succeeds).
- ``ADRs/0011-codegenie-directory-permissions-model.md`` §Consequences — the
  analyzed repo's ``.gitignore`` is NOT under ``.codegenie/``; we do not
  ``chmod 0600`` on it and we keep the platform default mode after umask.

Atomic write is intentionally module-local — the ``output/writer.py`` writer
applies the ``.codegenie/`` permissions policy (``0o600`` files), which is
the wrong policy for the analyzed repo's ``.gitignore``. The two atomic
writers are independent on purpose (ADR-0011).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import click
import structlog

from codegenie.logging import (
    GITIGNORE_APPEND_ACCEPTED,
    GITIGNORE_APPEND_DECLINED,
    GITIGNORE_APPEND_FAILED,
    GITIGNORE_APPEND_IDEMPOTENT,
    GITIGNORE_APPEND_SKIPPED,
)

__all__ = ["maybe_append_gitignore"]

_CANONICAL_BLOCK = b"# codewizard-sherpa generated artifacts; safe to delete\n.codegenie/\n"
_TMP_NAME = ".gitignore.tmp"
# Line-anchored, bytes-mode: avoids decoding errors and prevents
# `# do not commit .codegenie/` (a *comment*) from falsely registering
# as idempotent. The trailing `\s*` also swallows the `\r` in CRLF
# (`.codegenie/\r\n`), so a Windows-style file rounds-trips clean.
_IDEMPOTENT_RE = re.compile(rb"^\.codegenie/?\s*$", re.MULTILINE)


def _logger() -> structlog.stdlib.BoundLogger:
    """Resolve the structlog logger at call time, NOT module-import time.

    Module-level ``_log = get_logger(...)`` binds the proxy's underlying
    PrintLogger to whatever ``sys.stderr`` is at import time. Under pytest
    that's the very first test's ``CaptureIO``, which gets closed when that
    test ends — every subsequent test would then hit
    ``ValueError: I/O operation on closed file``. Resolving per call costs
    one extra lookup and stays correct across the lifecycle.
    """
    log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)
    return log


def maybe_append_gitignore(repo_root: Path, *, auto: bool, skip: bool) -> None:
    """Maybe append ``.codegenie/`` to ``<repo_root>/.gitignore``.

    Branch order is contract (matches the story's AC precedence):

    1. ``skip``                 → ``gitignore.append.skipped`` DEBUG ``reason=never_flag``.
    2. ``.gitignore`` exists and is a symlink / non-regular file
                                  → ``gitignore.append.skipped`` WARNING ``reason=unsafe_path``.
    3. existing content matches ``^\\.codegenie/?\\s*$`` (MULTILINE)
                                  → ``gitignore.append.idempotent`` DEBUG.
    4. ``not auto and not is_tty`` → ``gitignore.append.skipped`` WARNING ``reason=non_tty``.
    5. ``not auto``               → ``click.confirm(...)``; on ``False``
                                  → ``gitignore.append.declined`` INFO ``reason=tty_decline``.
    6. otherwise atomic append    → ``gitignore.append.accepted`` INFO
                                  (``reason="auto_flag"`` if ``auto`` else ``"tty_accept"``).

    OSError (and subclasses — ``PermissionError`` etc.) raised inside the
    atomic write step is caught, surfaced as ``gitignore.append.failed`` at
    WARNING, the tmp file is best-effort unlinked, and the function returns
    ``None``. Non-OS exceptions (``KeyboardInterrupt``, ``SystemExit``,
    ``MemoryError``, …) propagate — only ``OSError`` is part of the documented
    degrade-to-warning contract (edge case #8: gather exit code unaffected).
    """
    # Precedence #1 — skip flag wins over everything else.
    if skip:
        _logger().debug(GITIGNORE_APPEND_SKIPPED, reason="never_flag")
        return

    gitignore_path = repo_root / ".gitignore"

    # Precedence #2 — refuse non-regular files (symlink first, then dir/fifo/socket).
    # NOTE: ``is_symlink`` does NOT follow the link; ``is_file`` DOES — so
    # the symlink check must come first or a symlink-to-regular-file would
    # slip past.
    if gitignore_path.is_symlink() or (gitignore_path.exists() and not gitignore_path.is_file()):
        _logger().warning(GITIGNORE_APPEND_SKIPPED, reason="unsafe_path", path=str(gitignore_path))
        return

    existing = gitignore_path.read_bytes() if gitignore_path.exists() else b""

    # Precedence #3 — idempotent (line-anchored, NOT file-substring).
    if _IDEMPOTENT_RE.search(existing):
        _logger().debug(GITIGNORE_APPEND_IDEMPOTENT, path=str(gitignore_path))
        return

    is_tty = sys.stdin.isatty() and sys.stdout.isatty()

    # Precedence #4 — non-TTY skip (no prompt, file untouched).
    if not auto and not is_tty:
        _logger().warning(GITIGNORE_APPEND_SKIPPED, reason="non_tty")
        return

    # Precedence #5 — prompt (TTY, no auto flag).
    if not auto:
        if not click.confirm("Append .codegenie/ to .gitignore?", default=True):
            _logger().info(GITIGNORE_APPEND_DECLINED, reason="tty_decline")
            return

    # Precedence #6 — compose + atomic write.
    if existing == b"" or existing.endswith(b"\n"):
        new_content = existing + _CANONICAL_BLOCK
    else:
        new_content = existing + b"\n" + _CANONICAL_BLOCK

    if _atomic_write(repo_root, new_content):
        reason = "auto_flag" if auto else "tty_accept"
        _logger().info(GITIGNORE_APPEND_ACCEPTED, reason=reason, path=str(gitignore_path))


def _atomic_write(repo_root: Path, new_content: bytes) -> bool:
    """Atomic ``<tmp> → fsync → os.replace`` writer. Returns True on success.

    On ``OSError`` (and subclasses), emits ``gitignore.append.failed`` at
    WARNING with ``exc_class``, best-effort unlinks ``<tmp>``, and returns
    False — never re-raises (edge case #8). Non-OS exceptions propagate
    (AC-17) — do NOT widen this except.
    """
    tmp = repo_root / _TMP_NAME
    dst = repo_root / ".gitignore"
    try:
        with tmp.open("wb") as f:
            f.write(new_content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dst)
    except OSError as exc:
        _logger().warning(GITIGNORE_APPEND_FAILED, exc_class=type(exc).__name__, message=str(exc))
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True
