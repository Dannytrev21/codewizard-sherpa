"""Negative mypy --strict fixture for S3-03 AC-2.

Passing a raw ``dict`` to :meth:`Writer.write` must fail mypy --strict
with both substrings ``"incompatible type"`` and
``'expected "RedactedSlice"'`` so a regression that re-widens the
``envelope`` parameter is caught by the type-checker.

This file is invoked as a subprocess inside
``test_writer_signature.py``; it is intentionally NOT included by
``conftest.py`` collection.
"""

from __future__ import annotations

from pathlib import Path

from codegenie.output.writer import Writer

Writer().write({}, [], Path("/tmp"))  # type-error site
