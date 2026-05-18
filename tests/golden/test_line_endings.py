"""S7-03 AC-33 — LF endings + trailing newline on every committed golden."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_ROOT = _REPO_ROOT / "tests" / "golden" / "probes"


def _golden_paths() -> list[Path]:
    return sorted(_GOLDEN_ROOT.rglob("*.json"))


@pytest.mark.parametrize("path", _golden_paths(), ids=lambda p: str(p.relative_to(_REPO_ROOT)))
def test_golden_uses_lf_endings_and_trailing_newline(path: Path) -> None:
    raw = path.read_bytes()
    assert b"\r" not in raw, f"{path} contains CR (CRLF on Windows?)"
    assert raw.endswith(b"\n"), f"{path} missing trailing LF"
