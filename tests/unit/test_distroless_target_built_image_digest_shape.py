"""S7-01 AC-38 — built-image.digest content-shape contract.

``ProbeContext.image_digest_resolver: Callable[[Path], str | None]``
(Phase 2 ADR-0004) consumes this file. The bytes-on-disk shape must be
a stable contract so any future resolver implementation can read it
via ``Path.read_text().strip()`` without per-probe parser drift.

The test is skipped unless the file exists locally (after a real
``bash regenerate.sh`` run) or ``CODEGENIE_REGEN_FIXTURES=1`` is set.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final

import pytest

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "distroless-target"
_DIGEST_FILE = _FIXTURE / "built-image.digest"

_DIGEST_SHAPE_RE: Final[re.Pattern[bytes]] = re.compile(rb"^sha256:[0-9a-f]{64}\n$")


def _should_skip() -> bool:
    if os.environ.get("CODEGENIE_REGEN_FIXTURES") == "1":
        return False
    return not _DIGEST_FILE.is_file()


@pytest.mark.skipif(_should_skip(), reason="built-image.digest not present and CODEGENIE_REGEN_FIXTURES != 1")
def test_built_image_digest_shape() -> None:
    """AC-38 — exactly one line matching ``^sha256:[0-9a-f]{64}\\n$``."""
    raw = _DIGEST_FILE.read_bytes()
    assert _DIGEST_SHAPE_RE.match(raw), (
        f"built-image.digest must match {_DIGEST_SHAPE_RE.pattern!r}; got {raw!r}"
    )
