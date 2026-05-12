# Story S8-04 — ADR audit + roadmap exit-criteria checklist + final coverage report

**Step:** Step 8 — Operator CLI surface + end-to-end smoke
**Status:** Ready
**Effort:** S
**Depends on:** S8-03
**ADRs honored:** ADR-0001 through ADR-0015 (audit target — all)

## Context

This is the closing story for Phase 5. Every implementation story has landed; this one is the audit pass: confirm all fifteen Phase 5 ADRs are present, in Nygard format, status `Accepted`; mark the roadmap §"Phase 5" exit-criteria checklist done in the phase README; and emit a final coverage report demonstrating the floors from `phase-arch-design.md §Goal 12` are met (≥ 90/80 across `sandbox/` + `gates/`; ≥ 95/90 on `runner.py` + `contract.py`). The story produces no new runtime code — it produces documentation and a coverage artifact that proves Phase 5 is done.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals` — the 15 verifiable goals; every one must trace to a `[x]` in the exit-criteria checklist.
  - `../phase-arch-design.md §Goal 12` — coverage floors: ≥ 90% line / 80% branch across `sandbox/` + `gates/`; 95/90 on `gates/runner.py` and `sandbox/contract.py`.
  - `../phase-arch-design.md §Gap analysis` — Gap 1 (pre-execute marker), 2 (ReplanHook contract test), 4 (Firecracker nftables), 5 (cost ledger) — each must be closed by a specific story whose Status is `Done`.
- **Phase ADRs:**
  - `../ADRs/README.md` — the index of all 15 ADRs; this story re-reads it and asserts every numbered file `0001-...md` through `0015-...md` exists, has a `Status: Accepted` line, and follows Nygard format.
  - Each individual ADR (`0001..0015`) — spot-check Status and the "Consequences" section for any story-driven amendments noted by S2-01..S8-03.
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — referenced by ADR-P5-002 and the override flag wired in S8-02; verify cross-link.
- **Source design:**
  - `../final-design.md §Synthesis ledger` — every load-bearing row should have a story that closed it; verify none orphaned.
  - `../../../roadmap.md §"Phase 5"` — verbatim exit criteria; the checklist in the phase `README.md` must map 1:1.
- **Existing code:**
  - `docs/phases/05-sandbox-trust-gates/README.md` — the file whose exit-criteria checklist is updated here.
  - The full Phase 5 test suite — used to generate the coverage report.

## Goal

Audit all fifteen Phase 5 ADRs (present + `Accepted` + Nygard format), mark every roadmap §"Phase 5" exit-criterion as done in the phase `README.md`, and commit a final per-module coverage report proving the §Goal 12 floors are met across `sandbox/` + `gates/`.

## Acceptance criteria

- [ ] All fifteen files `docs/phases/05-sandbox-trust-gates/ADRs/0001-...md` through `0015-...md` exist on disk; the audit script `scripts/audit_phase5_adrs.py` (added by this story) enumerates them and asserts presence.
- [ ] Each ADR file contains `**Status:** Accepted` (case-sensitive) on a single line; the audit script greps for it and fails loudly on any other status string.
- [ ] Each ADR contains the four Nygard sections (`## Context`, `## Decision`, `## Consequences`, `## Status`) — verified by a regex check in the audit script; missing sections fail the audit.
- [ ] Each ADR's "Consequences" section has been re-read; any consequence noted as "TBD when story X lands" has been updated to reflect what actually happened (commit shows the diff per ADR or a no-op log line stating no changes were needed).
- [ ] `docs/phases/05-sandbox-trust-gates/README.md` contains a §"Exit criteria" checklist whose items are 1:1 with the roadmap §"Phase 5" criteria; every checkbox is `- [x]` (checked); each item references the closing story by ID (e.g., `S5-05`, `S8-03`).
- [ ] A coverage report `docs/phases/05-sandbox-trust-gates/coverage.md` is committed with: total line + branch coverage across `src/codegenie/sandbox/**`, `src/codegenie/gates/**`; per-module table for every `.py` file; explicit highlight rows for `gates/runner.py`, `gates/contract.py`, `gates/retry_ledger.py`, `sandbox/contract.py`, `sandbox/signals/models.py`.
- [ ] The coverage table values satisfy: `sandbox/` line ≥ 90% / branch ≥ 80%; `gates/` line ≥ 90% / branch ≥ 80%; `gates/runner.py` line ≥ 95% / branch ≥ 90%; `sandbox/contract.py` line ≥ 95% / branch ≥ 90%; `gates/contract.py` line ≥ 95% / branch ≥ 90%; `gates/retry_ledger.py` line ≥ 95% / branch ≥ 90%; `sandbox/signals/models.py` line ≥ 95% / branch ≥ 90%. Any module that misses the floor blocks merge — surface as a remediation story, not a relaxed floor.
- [ ] The audit script is wired as `scripts/audit_phase5_adrs.py` and the coverage check is wired into CI as `pytest --cov=src/codegenie/sandbox --cov=src/codegenie/gates --cov-fail-under=90 --cov-branch` plus a follow-on `python scripts/audit_phase5_coverage.py` that enforces the 95/90 module-level floors.
- [ ] The audit script returns exit code 0 on a clean Phase 5; non-zero with a list of missing/non-accepted ADRs otherwise.
- [ ] `scripts/audit_phase5_adrs.py` is covered by `tests/scripts/test_audit_phase5_adrs.py` ≥ 90% line coverage; tests use a `tmp_path`-staged fake ADRs dir for both happy and adversarial cases (missing ADR, wrong status, missing Nygard section).
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict scripts/audit_phase5_adrs.py scripts/audit_phase5_coverage.py`, `pytest tests/scripts/` all pass.

## Implementation outline

1. Write `scripts/audit_phase5_adrs.py`:
   - `ADR_DIR = pathlib.Path("docs/phases/05-sandbox-trust-gates/ADRs")`.
   - `EXPECTED_ADRS = {f"{i:04d}" for i in range(1, 16)}`.
   - For each expected number, glob `{ADR_DIR}/{NNNN}-*.md`; assert exactly one match.
   - For each found file, assert `re.search(r"^\*\*Status:\*\* Accepted$", content, re.M)`.
   - For each found file, assert each Nygard section header is present (regex `r"^## (Context|Decision|Consequences|Status)\b"`).
   - On any failure, print a structured report and `sys.exit(1)`.
2. Write `scripts/audit_phase5_coverage.py`:
   - Reads `coverage.json` (produced by `pytest --cov=... --cov-report=json`).
   - Aggregates totals for `sandbox/**` and `gates/**`; asserts the 90/80 floors.
   - Per-module asserts the 95/90 floors for the five named modules.
   - Writes `docs/phases/05-sandbox-trust-gates/coverage.md` from the JSON (templated; no manual editing).
3. Re-read each ADR's "Consequences" section; for any "TBD" placeholder, replace with the actual outcome or remove the placeholder.
4. Update `docs/phases/05-sandbox-trust-gates/README.md` §"Exit criteria":
   - Mirror the table from `phase-arch-design.md §Goals` 1–15; each row is `- [x] Goal N — <verbatim> — closed by SX-YY`.
   - Add closure rows for Gaps 1, 2, 4, 5 referencing S2-02, S5-01, S6-02, S7-03 respectively.
5. Run the full test suite + coverage in CI; commit `coverage.md`.
6. Update `docs/phases/05-sandbox-trust-gates/stories/README.md` §"Backlog stats" with the final story Status counts (`Done: 40`).

## TDD plan — red / green / refactor

### Red

Test file path: `tests/scripts/test_audit_phase5_adrs.py`

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


_NYGARD_TEMPLATE = """# ADR-{n:04d} — placeholder

**Status:** Accepted

## Context
x

## Decision
x

## Consequences
x

## Status
Accepted
"""


def _stage_adrs(root: Path, numbers: list[int], status: str = "Accepted") -> Path:
    adr_dir = root / "docs" / "phases" / "05-sandbox-trust-gates" / "ADRs"
    adr_dir.mkdir(parents=True)
    for n in numbers:
        body = _NYGARD_TEMPLATE.format(n=n).replace("**Status:** Accepted", f"**Status:** {status}")
        (adr_dir / f"{n:04d}-stub.md").write_text(body)
    return adr_dir


def _run_audit(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/audit_phase5_adrs.py"],
        cwd=root, capture_output=True, text=True,
    )


def test_audit_passes_with_all_15_accepted_adrs(tmp_path: Path) -> None:
    _stage_adrs(tmp_path, list(range(1, 16)))
    # also copy the script
    Path("scripts/audit_phase5_adrs.py").read_text()  # ensures script exists in repo
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "audit_phase5_adrs.py").write_text(
        Path("scripts/audit_phase5_adrs.py").read_text()
    )

    result = _run_audit(tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}\nstdout={result.stdout}"


def test_audit_fails_on_missing_adr(tmp_path: Path) -> None:
    _stage_adrs(tmp_path, list(range(1, 15)))  # missing 0015
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "audit_phase5_adrs.py").write_text(
        Path("scripts/audit_phase5_adrs.py").read_text()
    )

    result = _run_audit(tmp_path)
    assert result.returncode != 0
    assert "0015" in (result.stderr + result.stdout)


def test_audit_fails_on_non_accepted_status(tmp_path: Path) -> None:
    _stage_adrs(tmp_path, list(range(1, 16)), status="Proposed")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "audit_phase5_adrs.py").write_text(
        Path("scripts/audit_phase5_adrs.py").read_text()
    )

    result = _run_audit(tmp_path)
    assert result.returncode != 0
    assert "Status" in (result.stderr + result.stdout)


def test_audit_fails_on_missing_nygard_section(tmp_path: Path) -> None:
    _stage_adrs(tmp_path, list(range(1, 16)))
    # Damage one ADR: remove "## Decision"
    target = next((tmp_path / "docs" / "phases" / "05-sandbox-trust-gates" / "ADRs").glob("0007-*.md"))
    target.write_text(target.read_text().replace("## Decision\nx", "x"))

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "audit_phase5_adrs.py").write_text(
        Path("scripts/audit_phase5_adrs.py").read_text()
    )

    result = _run_audit(tmp_path)
    assert result.returncode != 0
    assert "Decision" in (result.stderr + result.stdout)
```

### Green

The script is ~80 LOC of `pathlib` + `re`. Implement only what each red test demands; do not over-engineer the report format. The coverage audit is a separate script reading `coverage.json` from `pytest-cov`; landing it as a parallel function is fine.

### Refactor

- Move the magic numbers (`1..16`, the four Nygard headers) to module-level constants.
- Add `--strict` and `--json` flags for CI consumption.
- Produce a single combined exit code: ADR failure or coverage failure both result in exit 1, with a structured report on stdout.
- Document the script in `scripts/README.md` (one paragraph each).
- Add a `--fix` flag that opens each non-`Accepted` ADR in `$EDITOR` (optional, do not block on this).

## Files to touch

| Path | Why |
|---|---|
| `scripts/audit_phase5_adrs.py` | New audit script. |
| `scripts/audit_phase5_coverage.py` | New coverage-floor audit. |
| `tests/scripts/test_audit_phase5_adrs.py` | Red + adversarial tests. |
| `docs/phases/05-sandbox-trust-gates/README.md` | Exit-criteria checklist closure. |
| `docs/phases/05-sandbox-trust-gates/coverage.md` | New — final per-module coverage report. |
| `docs/phases/05-sandbox-trust-gates/stories/README.md` | Final `Done: 40` bookkeeping. |
| `docs/phases/05-sandbox-trust-gates/ADRs/*.md` | Touch only those needing "TBD" → actual outcome rewrites. |
| `.github/workflows/ci.yaml` (or equivalent) | Add the two audit script invocations to the CI job. |

## Out of scope

- Roadmap-level closure for the *whole project* — this story closes Phase 5 only; Phase 6 starts after.
- Writing new ADRs — every ADR already exists per ADRs/README.md; only audit + minor consequence updates.
- Backporting coverage to earlier phases.
- Phase 6 LangGraph wrap — explicitly Phase 6.
- Performance trend dashboards — Phase 14 ops.

## Notes for the implementer

- The audit script is **the** authoritative checker. If a contributor adds ADR 0016 later, the constant `EXPECTED_ADRS` must be updated alongside — the script intentionally fails on *unexpected* ADR numbers too, so silent additions don't slip through. Add an `--allow-additional` flag if and only if that becomes necessary.
- Do NOT relax any coverage floor to make the audit pass. If `gates/runner.py` is at 94% line, write more tests — that's the contract. Phase 5's whole testing investment was about hitting these floors.
- The `coverage.md` template must be regenerable: do not hand-edit it. Future phase work that touches `sandbox/` or `gates/` will need to re-run the script and commit the new artifact.
- When updating ADR "Consequences" sections, prefer adding a dated postscript (`> 2026-05-12: S8-03 verified ...`) over rewriting the original — preserve the historical record per ADRs/README §Conventions.
- The `README.md` exit-criteria table must reference *story IDs*, not commit hashes — IDs are stable, hashes are not.
- After this story is `Done`, the entire `_attempts/` directory should be either archived or kept; do not delete the per-story attempt logs — they are evidence of the autonomous-implementation loop's behavior and may inform Phase 15 ("agentic recipe authoring").
- The CI workflow change should run the audit on every push to a Phase 5 branch but only block merge to `master` — discuss the gating policy in PR review, do not unilaterally tighten.
- Final phase status: update the phase folder's top-level `README.md` to `Status: Done` with the date.
