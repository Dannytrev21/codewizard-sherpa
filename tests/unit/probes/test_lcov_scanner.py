"""Tests for ``_lcov_scanner`` (S4-03).

Pins AC-22..AC-29 for the standalone scanner module: dispatch registry
shape, NamedTuple totals, kernel reuse (open_capped), structural
ReDoS defense (no ``re`` import), symlink refusal, byte-budget fuzz,
and lcov-dialect tolerance.
"""

from __future__ import annotations

import ast
import inspect
import time
from pathlib import Path

import pytest

from codegenie.errors import SizeCapExceeded, SymlinkRefusedError
from codegenie.probes._lcov_scanner import (
    _LCOV_MAX_BYTES,
    _LCOV_PREFIX_MAP,
    LcovTotals,
    scan,
)

# ---------- AC-22: dispatch registry ----------------------------------------


def test_lcov_prefix_map_keys() -> None:
    """AC-22 — closed prefix set."""
    assert set(_LCOV_PREFIX_MAP.keys()) == {"LF:", "LH:", "FNF:", "FNH:", "BRF:", "BRH:"}


def test_lcov_prefix_map_values() -> None:
    """AC-22 — every value is a valid LcovTotals field name."""
    for value in _LCOV_PREFIX_MAP.values():
        assert value in LcovTotals._fields


# ---------- AC-23: LcovTotals shape ----------------------------------------


def test_lcov_totals_namedtuple() -> None:
    """AC-23."""
    t = LcovTotals(1, 2, 3, 4, 5, 6)
    assert t._fields == (
        "lines_found",
        "lines_hit",
        "functions_found",
        "functions_hit",
        "branches_found",
        "branches_hit",
    )
    assert t.lines_found == 1
    assert t.branches_hit == 6


# ---------- AC-24: max bytes constant --------------------------------------


def test_max_bytes_50mb() -> None:
    """AC-24."""
    assert _LCOV_MAX_BYTES == 50 * 1024 * 1024


# ---------- AC-25: open_capped kernel reused -------------------------------


def test_scanner_imports_open_capped() -> None:
    """AC-25 — kernel reuse (no local O_NOFOLLOW re-implementation)."""
    src = Path(inspect.getsourcefile(scan) or "").read_text()
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "codegenie.parsers._io":
            for alias in node.names:
                if alias.name == "open_capped":
                    found = True
    assert found, "lcov scanner MUST import open_capped from parsers._io"
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "O_NOFOLLOW" not in names
    assert "fstat" not in names


# ---------- AC-26: regex-free over bytes -----------------------------------


def test_scanner_has_no_re_import() -> None:
    """AC-26 — structural ReDoS defense."""
    src = Path(inspect.getsourcefile(scan) or "").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "re"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "re"


# ---------- AC-27: symlink refusal -----------------------------------------


def test_symlink_refused(tmp_path: Path) -> None:
    """AC-27 — O_NOFOLLOW propagates SymlinkRefusedError."""
    leak = tmp_path.parent / "SENTINEL_TARGET.info"
    leak.write_text("LF:31337\nend_of_record\n")
    try:
        link = tmp_path / "lcov.info"
        link.symlink_to(leak)
        with pytest.raises(SymlinkRefusedError):
            scan(link)
    finally:
        if leak.exists():
            leak.unlink()


# ---------- AC-28: byte-budget fuzz ----------------------------------------


def test_pathological_input_byte_budget(tmp_path: Path) -> None:
    """AC-28 — ≥ 5 MB/s throughput on pathological 1 MB input."""
    p = tmp_path / "lcov.info"
    pathological = ("SF:" * 200_000 + "\n").encode() + b"GARBAGE\n" * 50_000
    p.write_bytes(pathological)
    size = p.stat().st_size
    t0 = time.monotonic()
    totals = scan(p)
    elapsed = max(time.monotonic() - t0, 1e-6)
    rate = size / elapsed
    assert rate >= 5_000_000, f"too slow: {rate:.0f} B/s (size={size}, elapsed={elapsed:.4f}s)"
    assert elapsed < 5.0
    assert totals == LcovTotals(0, 0, 0, 0, 0, 0)


def test_size_cap_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-24 / AC-28 — size cap fires before any read."""
    from codegenie.probes import _lcov_scanner

    monkeypatch.setattr(_lcov_scanner, "_LCOV_MAX_BYTES", 16)
    p = tmp_path / "lcov.info"
    p.write_bytes(b"x" * 32)
    with pytest.raises(SizeCapExceeded):
        scan(p)


# ---------- AC-29: lcov-dialect tolerance ----------------------------------


@pytest.mark.parametrize(
    "body, expected",
    [
        (
            "SF:/a.js\nLF:10\nLH:8\nFNF:3\nFNH:2\nBRF:4\nBRH:3\nend_of_record\n",
            LcovTotals(10, 8, 3, 2, 4, 3),
        ),
        (
            "LF:10\nLH:8\nend_of_record\nLF:5\nLH:3\nend_of_record\n",
            LcovTotals(15, 11, 0, 0, 0, 0),
        ),
        (
            "LF:10\nLH:8\nend_of_record\n",
            LcovTotals(10, 8, 0, 0, 0, 0),
        ),
        (
            "DA:1,2\nLF:10\nLH:8\nend_of_record\n",
            LcovTotals(10, 8, 0, 0, 0, 0),
        ),
    ],
)
def test_lcov_dialect_tolerance(tmp_path: Path, body: str, expected: LcovTotals) -> None:
    """AC-29."""
    p = tmp_path / "lcov.info"
    p.write_text(body)
    assert scan(p) == expected


def test_malformed_numeric_silently_dropped(tmp_path: Path) -> None:
    """AC-29 corollary — malformed counter does not raise."""
    p = tmp_path / "lcov.info"
    p.write_text("LF:not_a_number\nLH:8\nend_of_record\n")
    totals = scan(p)
    assert totals.lines_found == 0
    assert totals.lines_hit == 8
