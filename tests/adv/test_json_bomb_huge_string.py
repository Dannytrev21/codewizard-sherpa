"""Adversarial: a 600 MB single-string ``package.json`` triggers ``SizeCapExceeded``
**before** any bytes are read.

Pins ``phase-arch-design.md §"Adversarial tests"`` row 3 + ADR-0008's pre-parse
``fstat`` defense. ``open_capped`` checks ``os.fstat(fd).st_size > max_bytes``
**before** the first ``os.read``; a hostile 600 MB file must therefore die at
the size-cap branch without allocating its body.

Two canaries pin this:

1. ``json.loads`` is patched to raise :class:`RuntimeError`. If the size
   check regresses and the file is parsed, the test surfaces the sentinel
   ``RuntimeError`` instead of :class:`SizeCapExceeded` — and the regression
   is loud (Rule 12). Mirrors
   ``tests/unit/parsers/test_safe_json.py::test_size_cap_raises_before_read``.
2. ``os.read`` is instrumented: it must never be called when the size cap
   fires. A non-empty ``read_calls`` list flags a regression where the size
   check happens after a partial read.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from codegenie.errors import SizeCapExceeded
from codegenie.parsers import safe_json


def _write_huge_string_package_json(path: Path, *, megabytes: int) -> None:
    """Stream a 1 MB-chunk ``{"name": "aaa...aaa"}`` payload to disk.

    Necessarily an imperative shell (cannot fit ``megabytes`` MiB in memory);
    keeps the pure-bytes / pure-Path data surface explicit.
    """
    chunk = b"a" * (1024 * 1024)
    with path.open("wb") as out:
        out.write(b'{"name": "')
        for _ in range(megabytes):
            out.write(chunk)
        out.write(b'"}')


@pytest.mark.adv
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="adversarial parser caps require POSIX O_NOFOLLOW semantics",
)
def test_huge_string_package_json_size_cap_pre_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3 — ``safe_json.load`` raises :class:`SizeCapExceeded` pre-parse on
    a 600 MB file; ``json.loads`` is never called (sentinel canary); ``os.read``
    is never invoked (the size check precedes the read).
    """
    # AC-15 — refuse to write 600 MB on a constrained runner.
    if shutil.disk_usage(tmp_path).free < (1 << 30):  # < 1 GiB free
        pytest.skip("insufficient disk space for 600 MB fixture")

    f = tmp_path / "package.json"
    _write_huge_string_package_json(f, megabytes=600)

    # Verify the file is genuinely > 5 MB cap (defensive; not load-bearing).
    assert f.stat().st_size > 5_000_000

    # os.read instrumentation: if safe_json reads bytes BEFORE checking size,
    # the call list is non-empty and the assertion below catches it.
    real_read = os.read
    read_calls: list[int] = []

    def tracing_read(fd: int, n: int) -> bytes:
        read_calls.append(fd)
        return real_read(fd, n)

    monkeypatch.setattr(os, "read", tracing_read)

    # json.loads patch: this is the sentinel canary. If size cap regresses
    # and we reach the parse step, the test fails with RuntimeError instead
    # of SizeCapExceeded — the failure mode names itself.
    with patch(
        "codegenie.parsers.safe_json.json.loads",
        side_effect=RuntimeError("json.loads must not be reached"),
    ):
        with pytest.raises(SizeCapExceeded):
            safe_json.load(f, max_bytes=5_000_000)

    assert read_calls == [], f"size cap must precede any os.read; got {read_calls!r}"
