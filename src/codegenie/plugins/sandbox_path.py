"""``SandboxedPath`` — second-line TOCTOU defence (ADR-0011) — S4-04.

``SandboxedPath`` is **in-jail at construction** — a snapshot-time guarantee
only. Per 03-ADR-0011, the smart-constructor :meth:`SandboxedPath.create`
resolves both the jail and the candidate with ``Path.resolve(strict=True)``
and rejects any candidate that does not pass an ``is_relative_to`` check
against the resolved jail. The primitive does NOT pretend to keep the path
inside the jail for the lifetime of the value.

A symlink swap *between* :meth:`create` and :meth:`open` re-introduces the
TOCTOU. The second-line defence is :meth:`open`-time ``O_NOFOLLOW``:
``os.open(path, flags | O_NOFOLLOW | O_CLOEXEC)`` raises
``OSError(errno=ELOOP)`` when the final component became a symlink. Consumers
(S5-02 ``NpmLockfileRecipeEngine``, S6-04 ``LocalGitOps``) catch that and
emit ``FilesystemRaceDetected``; ``SandboxedPath.open`` itself catches
**nothing** (Rule 12 — fail loud).

Enforcement is **audit + lint**, not runtime impossibility. A future ruff
rule (AC-17 / S4-05) will ban direct ``SandboxedPath(...)`` construction
outside this module + ``tests/`` so the audit trail keeps a single
mint-point through :meth:`create`. Today the discipline is convention.

Known limitations the second-line defence does NOT catch (enumerated as
living-documentation tests in :mod:`tests.unit.plugins.test_sandbox_path`):

1. **Intermediate-component symlink.** ``O_NOFOLLOW`` only fires on the
   final component (``man 2 open``). An attacker who can write to an
   intermediate directory is already a higher-level compromise than this
   primitive defends against.
2. **Hardlink swap.** Hardlinks share an inode; ``O_NOFOLLOW`` does not
   block them. Defending against this needs inode pinning (``O_PATH`` +
   ``openat``), Linux-only, and is out of scope for Phase 3.
3. **FIFO / socket / device replacement.** ``O_NOFOLLOW`` covers symlinks
   only. A FIFO swap may make ``os.open`` block; a defensive ``fstat`` for
   ``S_IFREG`` would itself be a TOCTOU layer and is deferred.
4. **Atomic real-file replacement.** ``os.replace`` swaps a regular file
   under the jail; not a TOCTOU defence target — only symlink-swap is.

Sources: 03-ADR-0011 §Decision §SandboxedPath; phase-arch-design.md
§Component design C10 + §Edge case E12; story S4-04.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO, Final, Literal, cast

from pydantic import BaseModel, ConfigDict

from codegenie.result import Err, Ok, Result

__all__ = ["PathEscape", "SandboxedPath"]


_MANDATORY_FLAGS: Final[int] = os.O_NOFOLLOW | os.O_CLOEXEC
"""Single source of truth for mandatory ``open()`` flags.

AC-7 pins both bits. Future hardening (e.g., ``O_NOATIME`` if Phase 11
demands it) lands in one place and :meth:`SandboxedPath.open` picks it up
automatically.
"""


_MODE_TO_BASE_FLAGS: Final[dict[str, int]] = {
    "r": os.O_RDONLY,
    "rb": os.O_RDONLY,
    "w": os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
    "wb": os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
    "a": os.O_WRONLY | os.O_CREAT | os.O_APPEND,
    "ab": os.O_WRONLY | os.O_CREAT | os.O_APPEND,
    "r+": os.O_RDWR,
    "rb+": os.O_RDWR,
    "x": os.O_WRONLY | os.O_CREAT | os.O_EXCL,
    "xb": os.O_WRONLY | os.O_CREAT | os.O_EXCL,
}


def _flags_for_mode(mode: str) -> int:
    """Return the base ``os.open`` flag mask for *mode* (excluding mandatory bits).

    Unknown modes raise ``ValueError`` — silent fall-through to ``O_RDONLY``
    is a Rule-12 violation. :meth:`SandboxedPath.open` ORs in
    ``_MANDATORY_FLAGS`` afterwards so this helper's contract stays narrow.
    """
    try:
        return _MODE_TO_BASE_FLAGS[mode]
    except KeyError as exc:
        raise ValueError(f"unsupported mode for SandboxedPath.open: {mode!r}") from exc


class PathEscape(BaseModel):
    """Audit-payload returned by :meth:`SandboxedPath.create` on failure.

    The closed ``reason`` literal set is the sum-type discriminant; every
    variant is exercised by the AC-sum-type-coverage test. ``attempted_path``
    and ``jail`` carry the resolved (or attempted-resolved) absolute paths so
    the audit trail records what the smart constructor saw, not what the
    caller passed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["path_escape"] = "path_escape"
    attempted_path: str
    jail: str
    reason: Literal[
        "not_under_jail",
        "not_resolvable",
        "missing",
        "absolute",
        "invalid_jail",
    ]


class SandboxedPath(BaseModel):
    """In-jail-at-construction value type with ``O_NOFOLLOW`` ``open()``.

    Construct via :meth:`create` (smart constructor returning ``Result``).
    Direct ``SandboxedPath(absolute=...)`` is permitted today (the
    capability-construction lint rule is deferred to S4-05 / AC-17) but
    bypasses the resolve + jail check and is conventionally reserved for
    this module + ``tests/``.

    See module docstring for the honest framing and known limitations.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    absolute: Path

    def __fspath__(self) -> str:
        """``os.PathLike`` support — :mod:`os`-level APIs accept a SandboxedPath
        anywhere a string-or-bytes path is accepted (``os.open``, ``os.replace``,
        ``os.chmod``, ``os.fspath``). The returned string is ``str(absolute)``."""
        return str(self.absolute)

    def __str__(self) -> str:
        """Return the underlying path string so call sites doing
        ``str(sandboxed_path)`` (audit logs, ``tempfile.dir=``,
        ``string.Template`` substitutions) keep working after the S4-04
        flip. Pydantic v2's default ``__str__`` returns ``field=value`` —
        useless for path use. AC-2 still locks ``isinstance(sp, BaseModel)``
        and ``not isinstance(sp, Path)``."""
        return str(self.absolute)

    def __truediv__(self, other: str | Path) -> Path:
        """Path arithmetic returns a *bare* :class:`pathlib.Path`, NOT a
        SandboxedPath — the resulting path is no longer the capability that
        passed the smart-constructor's jail check. Consumers needing a
        SandboxedPath for a child path should call :meth:`create` again."""
        return self.absolute / other

    @classmethod
    def create(cls, jail: Path, relative: str | Path) -> Result[SandboxedPath, PathEscape]:
        """Smart constructor — see module docstring for the discipline.

        Step order is load-bearing: the absolute-arg reject happens *before*
        any filesystem call, so an attacker-controlled absolute path cannot
        accidentally escape via ``(jail_abs / "/etc/passwd")``'s pathlib
        drop-LHS behaviour. The two ``OSError`` branches at the candidate
        resolve are strictly disjoint: ``FileNotFoundError`` → ``missing``,
        every other ``OSError`` (broken-symlink-chain ``ELOOP`` / ``ENOTDIR``
        / etc.) → ``not_resolvable``.
        """
        rel_path = Path(relative)
        if rel_path.is_absolute():
            return Err(
                error=PathEscape(
                    attempted_path=str(rel_path),
                    jail=str(jail),
                    reason="absolute",
                )
            )

        try:
            jail_abs = jail.resolve(strict=True)
        except FileNotFoundError:
            return Err(
                error=PathEscape(
                    attempted_path=str(jail / rel_path),
                    jail=str(jail),
                    reason="invalid_jail",
                )
            )

        candidate = jail_abs / rel_path
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError:
            # ``Path.resolve(strict=True)`` raises ``FileNotFoundError`` for
            # both a missing leaf and a broken-symlink leaf. Disambiguate via
            # ``lstat``-based ``is_symlink`` (doesn't follow): a broken
            # symlink that exists-as-link maps to ``not_resolvable``; a
            # genuinely-missing leaf maps to ``missing``. AC-5 mutation guard
            # depends on the two reasons being strictly disjoint.
            reason: Literal[
                "not_under_jail",
                "not_resolvable",
                "missing",
                "absolute",
                "invalid_jail",
            ] = "not_resolvable" if candidate.is_symlink() else "missing"
            return Err(
                error=PathEscape(
                    attempted_path=str(candidate),
                    jail=str(jail_abs),
                    reason=reason,
                )
            )
        except OSError:
            return Err(
                error=PathEscape(
                    attempted_path=str(candidate),
                    jail=str(jail_abs),
                    reason="not_resolvable",
                )
            )

        if not resolved.is_relative_to(jail_abs):
            return Err(
                error=PathEscape(
                    attempted_path=str(resolved),
                    jail=str(jail_abs),
                    reason="not_under_jail",
                )
            )

        return Ok(value=cls(absolute=resolved))

    def open(self, mode: str) -> IO[bytes] | IO[str]:
        """Open the underlying path with mandatory ``O_NOFOLLOW`` + ``O_CLOEXEC``.

        Catches NO exceptions — ``OSError(errno=ELOOP)`` from a TOCTOU
        symlink swap propagates loud to the consumer (ADR-0011 §Decision
        §SandboxedPath). The ``try/finally`` shape is only the fd-leak
        cleanup if ``os.fdopen`` itself raises.
        """
        flags = _flags_for_mode(mode) | _MANDATORY_FLAGS
        fd = os.open(self.absolute, flags)
        handed_off = False
        try:
            wrapper = os.fdopen(fd, mode)
            handed_off = True
            return cast("IO[bytes] | IO[str]", wrapper)
        finally:
            if not handed_off:
                os.close(fd)
