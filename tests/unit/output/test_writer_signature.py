"""S3-03 — Writer.write signature tightening (02-ADR-0010).

Covers ACs 1, 2, 2b, 3, 3b: the writer + the seam narrow from
``dict[str, Any]`` to :class:`RedactedSlice` in lock-step; ``mypy
--strict`` rejects raw-dict callers (negative fixture) and clean-passes
``RedactedSlice`` callers (positive control); a runtime ``isinstance``
guard rejects raw dicts with a :class:`TypeError` whose message points
at 02-ADR-0010; and a source-level regex check pins the guard's
presence so a regression that drops it is caught even though Python
strips type hints at runtime.
"""

from __future__ import annotations

import inspect
import os
import re
import subprocess
import sys
import typing
from pathlib import Path

import pytest

import codegenie.cli as cli_mod
from codegenie.output.redacted_slice import RedactedSlice
from codegenie.output.sanitizer import redact_secrets
from codegenie.output.writer import Writer
from codegenie.types.identifiers import ProbeId

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = Path(__file__).resolve().parent / "_fixtures"


# ---------------------------------------------------------------------------
# AC-1 — Annotation propagation (both surfaces narrow in lock-step)
# ---------------------------------------------------------------------------


def test_ac1_writer_write_envelope_is_redacted_slice() -> None:
    hints = typing.get_type_hints(Writer.write)
    assert hints["envelope"] is RedactedSlice, hints


def test_ac1_seam_write_envelope_is_redacted_slice() -> None:
    # ``RedactedSlice`` is imported under ``TYPE_CHECKING`` in ``cli.py``
    # (the import-linter contract bans top-level ``pydantic`` in
    # ``codegenie.cli``), so ``get_type_hints`` needs a localns hint to
    # resolve the forward reference at test time.
    hints = typing.get_type_hints(
        cli_mod._seam_write_envelope, localns={"RedactedSlice": RedactedSlice}
    )
    assert hints["envelope"] is RedactedSlice, hints


def test_ac1_seam_redact_envelope_returns_redacted_slice() -> None:
    hints = typing.get_type_hints(
        cli_mod._seam_redact_envelope, localns={"RedactedSlice": RedactedSlice}
    )
    assert hints["return"] is RedactedSlice, hints


# ---------------------------------------------------------------------------
# AC-2 / AC-2b — mypy --strict fixture pair
# ---------------------------------------------------------------------------


def _run_mypy_strict(fixture: Path) -> subprocess.CompletedProcess[str]:
    # ``codegenie`` does not ship a ``py.typed`` marker, so a single-file
    # mypy invocation treats it as an untyped third-party package. Point
    # ``MYPYPATH`` at ``src/`` so mypy uses the actual source tree as the
    # type-information surface (matching the CI ``mypy --strict src/``
    # invocation).
    env = {**os.environ, "MYPYPATH": str(REPO_ROOT / "src")}
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--explicit-package-bases",
            "--no-incremental",
            str(fixture),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )


def test_ac2_writer_refuses_raw_dict_at_typecheck() -> None:
    fixture = FIXTURES_DIR / "raw_dict_to_writer.py"
    assert fixture.exists(), fixture
    result = _run_mypy_strict(fixture)
    assert result.returncode != 0, (
        f"mypy unexpectedly accepted raw-dict-to-writer fixture:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "incompatible type" in result.stdout, result.stdout
    assert 'expected "RedactedSlice"' in result.stdout, result.stdout


def test_ac2b_writer_accepts_redacted_slice_at_typecheck() -> None:
    fixture = FIXTURES_DIR / "redacted_slice_to_writer.py"
    assert fixture.exists(), fixture
    result = _run_mypy_strict(fixture)
    assert result.returncode == 0, (
        f"mypy rejected the positive-control fixture:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )


# ---------------------------------------------------------------------------
# AC-3 — Runtime isinstance guard + TypeError message contract
# ---------------------------------------------------------------------------


def test_ac3_writer_raises_typeerror_for_raw_dict(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match=r"RedactedSlice.*02-ADR-0010"):
        # Passing a raw dict — intentionally bypassing mypy via cast through
        # ``object`` so the runtime guard is what's under test.
        bad: object = {"schema_version": "0.1.0", "probes": {}}
        Writer().write(bad, [], tmp_path)  # type: ignore[arg-type]


def test_ac3_seam_raises_typeerror_for_raw_dict(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match=r"RedactedSlice.*02-ADR-0010"):
        bad: object = {"schema_version": "0.1.0", "probes": {}}
        cli_mod._seam_write_envelope(bad, [], tmp_path)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC-3b — Source-level regex check (the guard is present in both surfaces)
# ---------------------------------------------------------------------------


_ISINSTANCE_GUARD_RE = re.compile(r"isinstance\s*\(\s*envelope\s*,\s*[A-Za-z_.]*RedactedSlice\s*\)")


def test_ac3b_writer_source_has_isinstance_guard() -> None:
    src = inspect.getsource(Writer.write)
    assert _ISINSTANCE_GUARD_RE.search(src), src


def test_ac3b_seam_source_has_isinstance_guard() -> None:
    src = inspect.getsource(cli_mod._seam_write_envelope)
    assert _ISINSTANCE_GUARD_RE.search(src), src


# ---------------------------------------------------------------------------
# Happy path — RedactedSlice flows through end-to-end
# ---------------------------------------------------------------------------


def test_writer_accepts_redacted_slice_runtime(tmp_path: Path) -> None:
    redacted, _ = redact_secrets({"schema_version": "0.1.0", "probes": {}}, ProbeId("p"))
    Writer().write(redacted, [], tmp_path)
    assert (tmp_path / "repo-context.yaml").is_file()
