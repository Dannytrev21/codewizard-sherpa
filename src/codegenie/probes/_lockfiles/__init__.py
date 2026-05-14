"""Lockfile parser family — pnpm, npm, yarn siblings.

Each file in this package is a thin ``safe_*.load`` wrapper that
returns a format-specific TypedDict and translates exactly one
exception class to :class:`codegenie.errors.MalformedLockfileError`.
Sibling parsers do not import each other; the kernel they share is
:mod:`codegenie.parsers` + :mod:`codegenie.errors`. Adding a new
format (e.g. ``bun.lockb``) is a new file with zero edits to existing
siblings (CLAUDE.md "Extension by addition").

S3-01 ships :mod:`._pnpm`; S3-02 ships ``_npm``; S3-03 ships
``_yarn``. ``__all__`` stays empty here — each sibling exports from
its own module to keep import order unsurprising.
"""

from __future__ import annotations

__all__: list[str] = []
