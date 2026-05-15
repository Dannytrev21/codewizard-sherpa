"""Per-module coverage carve-out enforcement — ADR-0005.

Pure functional core (:func:`check`) + minimal imperative shell (:func:`main`).
``check()`` takes a parsed ``coverage.json`` document and the carve-out list
read from ``pyproject.toml`` and returns a list of human-readable violation
strings; an empty list is the pass signal. ``main()`` does the I/O.

Two carve-outs ship today (``codegenie.probes.deployment`` and
``codegenie.probes.ci``, both at 85 line / 75 branch). A third requires
an ADR amendment to ADR-0005 — the test in
``tests/unit/build/test_coverage_carve_outs.py`` is the structural gate.

Renames: each carve-out entry carries BOTH the file path and the
dotted module name. A rename PR that updates only one surface fails
the AC-6 test loudly.

Usage:
    python scripts/check_coverage_carve_outs.py coverage.json pyproject.toml
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any, NamedTuple


class CarveOut(NamedTuple):
    path: str
    module: str
    line: int
    branch: int


def load_carve_outs(pyproject_path: Path) -> list[CarveOut]:
    with pyproject_path.open("rb") as fh:
        data = tomllib.load(fh)
    rows = data["tool"]["coverage_carve_outs"]["entries"]
    return [
        CarveOut(
            path=row["path"],
            module=row["module"],
            line=int(row["line"]),
            branch=int(row["branch"]),
        )
        for row in rows
    ]


def check(coverage_data: dict[str, Any], carve_outs: list[CarveOut]) -> list[str]:
    """Return a list of human-readable violation strings (empty == pass)."""
    files = coverage_data.get("files", {})
    violations: list[str] = []
    for carve in carve_outs:
        entry = files.get(carve.path)
        if entry is None:
            violations.append(
                f"{carve.module} ({carve.path}): no coverage data found "
                f"(rename or omit?); expected >= {carve.line}% line / "
                f"{carve.branch}% branch"
            )
            continue
        summary = entry.get("summary", {})
        line_pct = float(summary.get("percent_covered", 0.0))
        # `coverage.py` emits `percent_branches_covered` in `--cov-report=json`.
        # The synthetic test fixtures use the shorter `percent_covered_branch`
        # alias; tolerate both so the script reads real `coverage.json` AND the
        # AC-7 synthetic-dict inputs without a translation layer.
        branch_pct = float(
            summary.get(
                "percent_branches_covered",
                summary.get("percent_covered_branch", 0.0),
            )
        )
        if line_pct < carve.line or branch_pct < carve.branch:
            violations.append(
                f"{carve.module} ({carve.path}): "
                f"{line_pct:.1f}% line / {branch_pct:.1f}% branch "
                f"< {carve.line}/{carve.branch} floor (ADR-0005). "
                f"Add intent-verifying tests to the parent probe — do NOT "
                f"lower the carve-out without amending ADR-0005."
            )
    return violations


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        sys.stderr.write("usage: check_coverage_carve_outs.py COVERAGE_JSON [PYPROJECT_TOML]\n")
        return 2
    coverage_path = Path(argv[1])
    pyproject_path = Path(argv[2]) if len(argv) == 3 else Path("pyproject.toml")
    if not coverage_path.is_file():
        sys.stderr.write(f"coverage report not found: {coverage_path}\n")
        return 2
    coverage_data = json.loads(coverage_path.read_text())
    carve_outs = load_carve_outs(pyproject_path)
    violations = check(coverage_data, carve_outs)
    if violations:
        for line in violations:
            sys.stderr.write(line + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
