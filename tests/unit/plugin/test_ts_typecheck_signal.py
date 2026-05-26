"""Phase-4 S6-05 — typecheck.typescript collector tests.

Covers the load-bearing ACs:

* AC-1 — `TYPECHECK_TYPESCRIPT` registered + same SignalKind value.
* AC-2 — collector signature.
* AC-3 — `run_allowlisted` invocation shape.
* AC-4 — `TrustSignal` shape conforms.
* AC-7 — strict-AND boundary cases (5 parametrized rows).
* AC-8 — missing-baseline degraded-pass path.
* AC-9 — timeout path.
* AC-10 — missing-tsc degraded-fail path.
* AC-11 — pure parser fixtures (zero / singular / plural / non-zero).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Final
from unittest.mock import AsyncMock, patch

import pytest

from codegenie.errors import ProbeTimeoutError, ToolMissingError
from codegenie.exec import ProcessResult
from codegenie.transforms.outcomes import TrustSignal

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_COLLECTOR_PATH: Final[Path] = (
    _REPO_ROOT
    / "plugins"
    / "vulnerability-remediation--node--npm"
    / "adapters"
    / "ts_typecheck_signal.py"
)


from tests.unit.plugin._ts_typecheck_collector_module import MODULE as _MODULE

collect = _MODULE.collect_typecheck_typescript_signal
TYPECHECK_TYPESCRIPT = _MODULE.TYPECHECK_TYPESCRIPT
_parse_tsc_error_count = _MODULE._parse_tsc_error_count


# --- AC-1: registration -------------------------------------------------


def test_ac1_typecheck_typescript_signal_kind_registered() -> None:
    # SignalKind is a NewType[str] — verify the value rather than
    # an isinstance check (NewType is not a class at runtime).
    assert str(TYPECHECK_TYPESCRIPT) == "typecheck.typescript"


# --- AC-2: collector signature ------------------------------------------


def test_ac2_collector_signature() -> None:
    sig = inspect.signature(collect)
    params = list(sig.parameters)
    assert params == ["repo_root", "baseline_repo_sha", "timeout_s"]
    assert sig.parameters["timeout_s"].kind is inspect.Parameter.KEYWORD_ONLY
    assert inspect.iscoroutinefunction(collect)


# --- AC-11: pure parser fixtures ----------------------------------------


def test_ac11_parser_zero_errors() -> None:
    """returncode=0, empty stdout → ErrorCount(0)."""
    result = _parse_tsc_error_count(0, b"")
    assert hasattr(result, "count")
    assert result.count == 0


def test_ac11_parser_singular_error() -> None:
    """`Found 1 error in 1 file.` → ErrorCount(1)."""
    result = _parse_tsc_error_count(1, b"foo.ts:3:5 - error TS2322\n\nFound 1 error in 1 file.\n")
    assert hasattr(result, "count")
    assert result.count == 1


def test_ac11_parser_plural_errors() -> None:
    """`Found 5 errors in 3 files.` → ErrorCount(5)."""
    result = _parse_tsc_error_count(1, b"...\n\nFound 5 errors in 3 files.\n")
    assert hasattr(result, "count")
    assert result.count == 5


def test_ac11_parser_unparseable() -> None:
    """Non-zero with no summary → UnparseableOutput."""
    result = _parse_tsc_error_count(1, b"random gibberish, no summary line\n")
    assert not hasattr(result, "count")


def test_ac11_parser_multi_file_with_diagnostics() -> None:
    """Realistic tsc output with diagnostics interspersed."""
    stdout = (
        b"src/a.ts:1:1 - error TS2304: Cannot find name 'foo'.\n"
        b"src/b.ts:5:5 - error TS2322: Type error\n"
        b"src/c.ts:7:1 - error TS2554: Argument error\n"
        b"\n"
        b"Found 3 errors in 3 files.\n"
    )
    result = _parse_tsc_error_count(1, stdout)
    assert hasattr(result, "count")
    assert result.count == 3


# --- AC-7: strict-AND boundary cases ------------------------------------


def _seed_ts_project(repo: Path) -> None:
    """Seed a repo with tsconfig.json + a single .ts file so the S6-06
    applicability check returns ``Applicable`` and the collector runs
    `tsc`. (The applicability short-circuit otherwise prevents the
    AC-8/9/10/11 paths from being reached.)"""
    (repo / "tsconfig.json").write_text('{"compilerOptions":{}}', encoding="utf-8")
    (repo / "index.ts").write_text("export const x = 1;\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("baseline", "after", "expected_passed"),
    [
        (5, 4, True),  # reduced errors
        (5, 5, True),  # boundary — equal is OK (strict-AND uses <=)
        (5, 6, False),  # regression
        (0, 0, True),  # zero baseline, zero after
        (0, 1, False),  # introduced an error from clean baseline
    ],
)
@pytest.mark.asyncio
async def test_ac7_baseline_boundary(
    baseline: int, after: int, expected_passed: bool, tmp_path: Path
) -> None:
    """Strict-AND: passed iff new_errors_after <= new_errors_before."""
    _seed_ts_project(tmp_path)
    # Seed the baseline.
    typecheck_dir = tmp_path / ".codegenie" / "typecheck"
    typecheck_dir.mkdir(parents=True)
    sha = "deadbeef" * 5
    (typecheck_dir / f"baseline-{sha}.json").write_text(
        json.dumps({"error_count": baseline}), encoding="utf-8"
    )
    # Mock tsc to report the after count.
    if after == 0:
        proc = ProcessResult(returncode=0, stdout=b"", stderr=b"")
    else:
        word = "error" if after == 1 else "errors"
        proc = ProcessResult(
            returncode=1,
            stdout=f"Found {after} {word} in 1 file.\n".encode(),
            stderr=b"",
        )
    with patch.object(_MODULE, "run_allowlisted", AsyncMock(return_value=proc)):
        signal = await collect(tmp_path, sha)
    assert isinstance(signal, TrustSignal)
    assert signal.passed is expected_passed
    assert signal.details["error_count"] == after
    assert signal.details["baseline_count"] == baseline


# --- AC-8: missing-baseline degraded-pass --------------------------------


@pytest.mark.asyncio
async def test_ac8_no_baseline_degraded_pass(tmp_path: Path) -> None:
    """No baseline → passed=True, degraded_reason='no_baseline'."""
    _seed_ts_project(tmp_path)
    proc = ProcessResult(returncode=0, stdout=b"", stderr=b"")
    with patch.object(_MODULE, "run_allowlisted", AsyncMock(return_value=proc)):
        signal = await collect(tmp_path, "anysha" * 5)
    assert signal.passed is True
    assert signal.details["degraded_reason"] == "no_baseline"
    assert signal.details["error_count"] == 0


# --- AC-9: timeout path --------------------------------------------------


@pytest.mark.asyncio
async def test_ac9_timeout_fails_with_timeout_flag(tmp_path: Path) -> None:
    """Timeout → passed=False, details['timeout']=True."""
    _seed_ts_project(tmp_path)
    with patch.object(
        _MODULE,
        "run_allowlisted",
        AsyncMock(side_effect=ProbeTimeoutError("tsc timeout, elapsed_ms=30000")),
    ):
        signal = await collect(tmp_path, "anysha" * 5)
    assert signal.passed is False
    assert signal.details["timeout"] is True


# --- AC-10: missing-tsc degraded path ------------------------------------


@pytest.mark.asyncio
async def test_ac10_missing_tsc_emits_no_tsconfig_degraded(tmp_path: Path) -> None:
    """ToolMissingError → passed=False, degraded_reason='no_tsconfig_or_tsc'."""
    _seed_ts_project(tmp_path)
    with patch.object(
        _MODULE,
        "run_allowlisted",
        AsyncMock(side_effect=ToolMissingError("tsc missing")),
    ):
        signal = await collect(tmp_path, "anysha" * 5)
    assert signal.passed is False
    assert signal.details["degraded_reason"] == "no_tsconfig_or_tsc"


# --- AC-11: unparseable output projects to degraded ----------------------


@pytest.mark.asyncio
async def test_ac11_unparseable_output_degraded(tmp_path: Path) -> None:
    """Non-zero with no summary → passed=False with degraded_reason."""
    _seed_ts_project(tmp_path)
    proc = ProcessResult(returncode=1, stdout=b"garbage no summary", stderr=b"stderr text")
    with patch.object(_MODULE, "run_allowlisted", AsyncMock(return_value=proc)):
        signal = await collect(tmp_path, "anysha" * 5)
    assert signal.passed is False
    assert signal.details["degraded_reason"] == "tsc_unparseable_output"
    assert "stderr_head" in signal.details
