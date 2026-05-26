# Story S8-04 — ADR audit + roadmap exit-criteria checklist + final coverage report

**Step:** Step 8 — Operator CLI surface + end-to-end smoke
**Status:** HARDENED
**Effort:** S
**Depends on:** S8-03
**ADRs honored:** all ADRs in `../ADRs/` (audit target — enumerated from disk, not hardcoded)

## Validation notes

**Validated:** 2026-05-26 → **HARDENED**. Full report: [`_validation/S8-04-adr-audit-and-roadmap-exit-criteria.md`](_validation/S8-04-adr-audit-and-roadmap-exit-criteria.md). Changes applied in place (each one rooted in a same-repo precedent — no `NEEDS RESEARCH`):

- **F-COV-1 / F-CONS-1 (BLOCK)** — Draft hardcoded `EXPECTED_ADRS = range(1, 16)`; ADR-0016 (per-task-class eval harness) already exists. Replaced with enumerate-from-disk + cross-check against `../ADRs/README.md` index table; "ADRs honored" header widened from `0001..0015` to "all ADRs in `../ADRs/`".
- **F-CONS-3 (BLOCK→HARDEN)** — Draft Nygard regex required four sections (`Context`, `Decision`, `Consequences`, `Status`); real Phase-5 ADRs use **seven** (`Context`, `Options considered`, `Decision`, `Tradeoffs`, `Consequences`, `Reversibility`, `Evidence / sources`) with **no `## Status` section** (Status is a `**Status:**` header field). Required sections + status regex realigned to actual repo convention; TDD `_NYGARD_TEMPLATE` rewritten.
- **F-CONS-4 (HARDEN)** — Status regex `^\*\*Status:\*\* Accepted$` falsely rejects ADR-0016's real `**Status:** Accepted (commitment) — Deferred (implementation; lands before Phase 7 ships)`. Loosened to `^\*\*Status:\*\*\s+Accepted(\s+\([^)]+\))?(\s+—\s+.+)?$`.
- **F-COV-2 / F-CONS-2 (BLOCK)** — Draft said "checklist 1:1 with roadmap §"Phase 5"" *and* "Mirror the table from `phase-arch-design.md §Goals` 1–15". Roadmap has 2 items; arch has 15. Split into two distinct README sections: §"Exit criteria" (3 roadmap-mirroring items, shape from existing `final-design.md §Exit-criteria checklist`) + §"Goals completion" (15 arch-mirroring rows + 4 gap-closure rows), each story-ID-anchored.
- **F-CONS-5 / F-COV-4 (HARDEN)** — Draft expanded the 95/90 floor list to five modules; arch Goal 12 only mandates `gates/runner.py` + `sandbox/contract.py`. Trimmed AC to those two; the other three (`gates/contract.py`, `gates/retry_ledger.py`, `sandbox/signals/models.py`) surfaced as **Notes** — raise via ADR amendment if the implementer wants to bake them in.
- **F-TQ-1 (BLOCK)** — Draft tested the script via `subprocess.run(...)` from a staged tmp_path with the script copied in. Codebase precedent (`scripts/check_coverage_carve_outs.py` + `tests/unit/build/test_coverage_carve_outs.py`, S4-04 / ADR-0005) is functional-core / imperative-shell with direct-import tests. Refactored: pure `check(adr_dir, expected_numbers, ...) -> list[Finding]` + thin `main()`; tests import and call `check(...)` directly. Test path moved from non-existent `tests/scripts/` to the established `tests/unit/build/`.
- **F-DP-1 (HARDEN)** — Audit findings carried as raw strings; tagged-union opportunity missed. Added `Finding = NamedTuple("Finding", kind, adr_number, message)` with `kind: Literal["missing", "wrong_status", "missing_section", "unexpected_extra"]` so illegal states are unrepresentable and tests assert structured shape, not stringified output.
- **F-DP-3 (HARDEN)** — Primitive obsession on ADR id strings. Module boundary uses `tuple[int, str]` (number + filename); zero-padded string formatting happens only at report time.
- **F-DP-2 (HARDEN — Notes only)** — Per Rule 2 / CLAUDE.md "three similar lines is better than premature abstraction", do NOT extract a shared `scripts/_adr_audit.py` kernel today. Phase 5 is the first ADR-audit script; Phase 6/7 closeouts will be #2 and #3. Note records the future-kernel signpost.
- **F-TQ-3 / F-TQ-4 / F-TQ-5 (HARDEN)** — Tests now assert specific ADR number + offending status string (mutation-resistant against `sys.exit(1); print("Status")`); `PROJECT_ROOT = Path(__file__).resolve().parents[3]` anchor; parameterised count.
- **F-COV-3 / F-COV-5 / F-COV-6 / F-COV-7 / F-COV-8 (HARDEN/NIT)** — New ACs added for: unexpected-extra-ADR rejection; `coverage.md` autogen-marker + BLAKE3 fence; audit output naming the offending ADR id; phase-folder README gains `**Status:** Done — <date>` header; `.github/workflows/ci.yml` path pinned (not `.yaml`).
- **F-DP-4 (NIT)** — Dropped the speculative `--fix` flag from Refactor; auto-remediation belongs in its own story.

## Context

This is the closing story for Phase 5. Every implementation story has landed; this one is the audit pass: confirm every Phase-5 ADR present on disk is in the repo's actual ADR convention (seven Nygard sections + `**Status:** Accepted...` header field), is `Accepted`, and that the count matches `../ADRs/README.md`'s index table; mark the roadmap §"Phase 5" exit-criteria checklist done in the phase `README.md`; add a parallel §"Goals completion" table mirroring `phase-arch-design.md §Goals` 1–15 + the four gap-closure rows; and emit a final coverage report demonstrating the §Goal 12 floors (≥ 90/80 across `sandbox/` + `gates/`; ≥ 95/90 on `gates/runner.py` + `sandbox/contract.py`). The story produces no new runtime code — it produces an audit script, a coverage script, and documentation that proves Phase 5 is done.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals` — the 15 verifiable goals; every one becomes a row in the README §"Goals completion" table.
  - `../phase-arch-design.md §Goal 12` — coverage floors: ≥ 90% line / 80% branch across `sandbox/` + `gates/`; 95/90 on `gates/runner.py` and `sandbox/contract.py`.
  - `../phase-arch-design.md §Gap analysis` — Gap 1 (pre-execute marker), 2 (ReplanHook contract test), 4 (Firecracker nftables), 5 (cost ledger) — each must be closed by a specific story whose Status is `Done`.
- **Phase ADRs:**
  - `../ADRs/README.md` — the **source of truth** for "what ADRs should exist"; the audit asserts the index table's row count matches the on-disk file count.
  - Each individual ADR — survey: real shape is `**Status:** Accepted` header field + seven `##` sections (`Context`, `Options considered`, `Decision`, `Tradeoffs`, `Consequences`, `Reversibility`, `Evidence / sources`).
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — referenced by phase ADR-0002 and the override flag wired in S8-02; verify cross-link still resolves.
- **Source design:**
  - `../final-design.md §Synthesis ledger` — every load-bearing row should have a story that closed it; verify none orphaned.
  - `../final-design.md §Exit-criteria checklist` — **the existing 3-item shape** the new README §"Exit criteria" section mirrors.
  - `../../../roadmap.md §"Phase 5"` — verbatim roadmap exit criteria (2 items: no-transform-unverified + 3-retry-recover-end-to-end).
- **Existing code precedents (consume; do not re-invent):**
  - `scripts/check_coverage_carve_outs.py` — functional-core / imperative-shell precedent: pure `check(...)` + thin `main()`.
  - `tests/unit/build/test_coverage_carve_outs.py` — the test-shape precedent: `PROJECT_ROOT = Path(__file__).resolve().parents[3]`; direct-import tests of the pure core; one separate subprocess CLI smoke.
- **Existing docs to mutate:**
  - `docs/phases/05-sandbox-trust-gates/README.md` — gains `**Status:**` header + §"Exit criteria" + §"Goals completion".
  - The full Phase 5 test suite — used to generate the coverage report.

## Goal

Audit every Phase-5 ADR present on disk (matches the repo's seven-section Nygard convention + has an `Accepted...` status); mirror the roadmap §"Phase 5" exit-criteria in the phase `README.md` (3 items) plus a parallel §"Goals completion" table for the 15 arch goals + 4 gap closures; and commit a fence-pinned auto-generated per-module coverage report proving the §Goal 12 floors are met.

## Acceptance criteria

### ADR audit (`scripts/audit_phase5_adrs.py`)

- [ ] AC-A1 — `scripts/audit_phase5_adrs.py` exists with a **pure** `check(adr_dir: Path, expected_numbers: set[int], *, status_regex: re.Pattern[str], required_sections: frozenset[str]) -> list[Finding]` function plus a thin `main()` CLI shell. `Finding` is a `NamedTuple` with fields `kind: Literal["missing", "wrong_status", "missing_section", "unexpected_extra"]`, `adr_number: int`, `message: str`. (precedent: `scripts/check_coverage_carve_outs.py`).
- [ ] AC-A2 — `expected_numbers` is **derived from `../ADRs/README.md`** at runtime: the script parses the index Markdown table, extracts the leading `[NNNN](NNNN-...md)` column, and asserts the discovered on-disk numbers form a contiguous range starting at 1 with no duplicates. Hardcoded numeric ranges are forbidden — the test asserts the script source contains no integer literal range `range(1, NN)` for `NN > 1`.
- [ ] AC-A3 — The script discovers ADRs by `ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")`, parses each filename as `(int(NNNN), filename)`, and reports `Finding(kind="missing", adr_number=N, ...)` for any expected number with no file, `Finding(kind="unexpected_extra", adr_number=N, ...)` for any on-disk file whose number is *not* in the expected set, and `Finding(kind="wrong_status", ...)` / `Finding(kind="missing_section", ...)` for the per-file checks.
- [ ] AC-A4 — Status regex: `^\*\*Status:\*\*\s+Accepted(\s+\([^)]+\))?(\s+—\s+.+)?$` (Multiline). Matches `**Status:** Accepted`, `**Status:** Accepted (commitment)`, and `**Status:** Accepted (commitment) — Deferred (implementation; …)` — the last is the real ADR-0016 line; rejects `Proposed`, `Deprecated`, `Superseded`.
- [ ] AC-A5 — Required sections (per real repo convention; survey-verified across all 16 ADRs): `frozenset({"Context", "Options considered", "Decision", "Tradeoffs", "Consequences", "Reversibility", "Evidence / sources"})`. The check is `re.search(rf"^## {re.escape(section)}\b", content, re.M)` per section.
- [ ] AC-A6 — `main()` exits 0 when `check(...)` returns `[]`; exits 1 otherwise. The non-zero report prints one line per `Finding` containing the **zero-padded ADR number** (e.g., `0016`) AND the **offending data** (status string excerpt or section name). A reviewer can grep the failure output for the ADR id and immediately know which file to open.
- [ ] AC-A7 — `scripts/audit_phase5_adrs.py` is covered by `tests/unit/build/test_audit_phase5_adrs.py` ≥ 90% line coverage. Tests **import** `check` and call it with `tmp_path`-staged ADR trees (not subprocess); a separate single subprocess test exercises the CLI exit code as a smoke. `PROJECT_ROOT = Path(__file__).resolve().parents[3]` anchors all path references.

### Coverage audit (`scripts/audit_phase5_coverage.py`)

- [ ] AC-C1 — `scripts/audit_phase5_coverage.py` exists with a pure `check(coverage_json: dict, floors: PhaseCoverageFloors) -> list[Violation]` function + `main()` shell. `PhaseCoverageFloors` is a `NamedTuple` carrying the aggregate floor (90/80 for `sandbox/` + `gates/`) and per-module floors (95/90 on `gates/runner.py` + `sandbox/contract.py` — the two arch-Goal-12-mandated modules, no more).
- [ ] AC-C2 — The script reads `coverage.json` (produced by `pytest --cov=src/codegenie/sandbox --cov=src/codegenie/gates --cov-branch --cov-report=json:coverage.json`), aggregates totals for the two packages, asserts the 90/80 aggregate floors, and per-module asserts the 95/90 floors for the two named modules.
- [ ] AC-C3 — On `check(...) == []`, the script writes `docs/phases/05-sandbox-trust-gates/coverage.md` from a template; the file's first non-blank line is the literal HTML comment `<!-- AUTOGENERATED by scripts/audit_phase5_coverage.py — do not edit by hand -->`. A fence test (`tests/unit/build/test_coverage_md_autogenerated.py`) regenerates the file from a frozen `coverage.json` fixture and asserts the on-disk file is byte-identical (BLAKE3) — a hand-edit fails CI.
- [ ] AC-C4 — Per-module table in `coverage.md` includes a row for **every** `.py` file under `src/codegenie/sandbox/**` and `src/codegenie/gates/**` (no curation), plus two explicit highlight rows (bold-typeset) for `gates/runner.py` and `sandbox/contract.py` showing they cleared the 95/90 floor.
- [ ] AC-C5 — `scripts/audit_phase5_coverage.py` is covered by `tests/unit/build/test_audit_phase5_coverage.py` ≥ 90% line — tests import `check` and assert it returns `Violation`s of the right kind on planted under-floor fixtures.

### Documentation closure

- [ ] AC-D1 — `docs/phases/05-sandbox-trust-gates/README.md` gains a top-of-file header field `**Status:** Done — 2026-05-26 (closed by S8-04)`. This field is greppable by the audit and by future `phase-shakedown` runs.
- [ ] AC-D2 — `README.md` gains a §"Exit criteria" section whose items are **1:1 with the roadmap §"Phase 5"** entry (3 items, matching `final-design.md §Exit-criteria checklist`); every checkbox is `- [x]` and references the closing story by ID.
- [ ] AC-D3 — `README.md` gains a *separate* §"Goals completion" section mirroring `phase-arch-design.md §Goals` 1–15 — one row per goal, format `- [x] Goal N — <verbatim text> — closed by SX-YY`. Plus a §"Gap closure" sub-section with 4 rows: Gap 1 → S2-02, Gap 2 → S5-01, Gap 4 → S6-02, Gap 5 → S7-03.
- [ ] AC-D4 — `docs/phases/05-sandbox-trust-gates/stories/README.md` §"Backlog stats" updated with final `Done: 40` count.
- [ ] AC-D5 — Each ADR's "Consequences" section spot-checked for `TBD when story X lands` placeholders. Any update takes the form of a **dated blockquote postscript** (`> 2026-05-26: <story-id> verified ...`), never an inline rewrite of the original prose. The audit script has a sibling helper test (`test_consequences_no_inline_rewrite_after_acceptance`) that flags any ADR whose `## Consequences` body shrank between commits without a corresponding `>` postscript being added.

### CI wiring

- [ ] AC-CI1 — `.github/workflows/ci.yml` runs both audit scripts: `python scripts/audit_phase5_adrs.py` and `pytest --cov=src/codegenie/sandbox --cov=src/codegenie/gates --cov-branch --cov-report=json:coverage.json && python scripts/audit_phase5_coverage.py coverage.json`. Failure of either gates merge to `master`.

### TDD + gate

- [ ] AC-TDD — TDD plan's red tests exist, are committed, and are green; tests for both audit scripts hit the ≥ 90% line floor.
- [ ] AC-GATE — `ruff check`, `ruff format --check`, `mypy --strict scripts/audit_phase5_adrs.py scripts/audit_phase5_coverage.py`, `pytest tests/unit/build/test_audit_phase5_adrs.py tests/unit/build/test_audit_phase5_coverage.py tests/unit/build/test_coverage_md_autogenerated.py --no-cov` all pass.

## Implementation outline

1. Write `scripts/audit_phase5_adrs.py` (pure core + thin shell):
   - Module-level `Final` constants: `_STATUS_REGEX = re.compile(r"^\*\*Status:\*\*\s+Accepted(\s+\([^)]+\))?(\s+—\s+.+)?$", re.M)`; `_REQUIRED_SECTIONS = frozenset({"Context", "Options considered", "Decision", "Tradeoffs", "Consequences", "Reversibility", "Evidence / sources"})`; `_FILENAME_RX = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")`.
   - `Finding` `NamedTuple` with the four `kind` literals.
   - `def parse_index_expected_numbers(readme_path: Path) -> set[int]` — parses `../ADRs/README.md` Markdown table, returns the set of expected ADR numbers (source of truth).
   - `def check(adr_dir: Path, expected_numbers: set[int], *, status_regex=_STATUS_REGEX, required_sections=_REQUIRED_SECTIONS) -> list[Finding]` — pure: discovers on-disk via glob, returns structured findings for every defect.
   - `def main(argv: list[str]) -> int` — argparse `--adr-dir`, `--readme` (defaults that resolve to Phase-5 paths); calls `check`, prints findings (one line each, zero-padded ADR id + offending excerpt), returns 0/1.
2. Write `scripts/audit_phase5_coverage.py` mirroring `check_coverage_carve_outs.py`:
   - `class PhaseCoverageFloors(NamedTuple)` carrying aggregate + per-module floors.
   - `def check(coverage_json: dict, floors: PhaseCoverageFloors) -> list[Violation]` — pure.
   - `def render_markdown(coverage_json: dict, floors: PhaseCoverageFloors) -> str` — returns the templated `coverage.md` body starting with the autogen-marker HTML comment.
   - `main()` reads `coverage.json`, runs `check`, writes `coverage.md` on success.
3. Re-read each ADR's "Consequences" section for `TBD when story X lands`; replace with dated blockquote postscript per AC-D5.
4. Update `docs/phases/05-sandbox-trust-gates/README.md`:
   - Add `**Status:** Done — 2026-05-26 (closed by S8-04)` header line.
   - Append §"Exit criteria" — copy the three items from `final-design.md §Exit-criteria checklist`; check each box; append `→ closed by SX-YY` to each.
   - Append §"Goals completion" — one row per arch Goal 1–15 (verbatim text + closing story id); plus §"Gap closure" sub-section with 4 rows.
5. Run the full test suite + coverage in CI; commit `coverage.md`.
6. Update `docs/phases/05-sandbox-trust-gates/stories/README.md` §"Backlog stats" with the final story Status counts (`Done: 40`).
7. Add CI invocations per AC-CI1.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/build/test_audit_phase5_adrs.py`.

```python
"""Phase-5 ADR audit — story S8-04.

Direct-import tests of the pure `check(...)` core. One subprocess test
exercises the CLI exit code as a smoke. Path precedent:
`tests/unit/build/test_coverage_carve_outs.py` (S4-04 / ADR-0005).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / "scripts" / "audit_phase5_adrs.py"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from audit_phase5_adrs import (  # noqa: E402  — path-inserted import
    Finding,
    check,
    parse_index_expected_numbers,
)

_NYGARD_TEMPLATE = """# ADR-{n:04d} — placeholder

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** stub

## Context
x
## Options considered
x
## Decision
x
## Tradeoffs
x
## Consequences
x
## Reversibility
x
## Evidence / sources
x
"""


def _stage(root: Path, numbers: list[int], *, status_line: str | None = None,
           drop_section: dict[int, str] | None = None) -> Path:
    drop_section = drop_section or {}
    for n in numbers:
        body = _NYGARD_TEMPLATE.format(n=n)
        if status_line is not None:
            body = re.sub(r"^\*\*Status:\*\*.*$", status_line, body, count=1, flags=re.M)
        if n in drop_section:
            body = re.sub(rf"^## {re.escape(drop_section[n])}\b.*?(?=^## |\Z)",
                          "", body, count=1, flags=re.M | re.S)
        (root / f"{n:04d}-stub.md").write_text(body)
    return root


def test_check_passes_against_canonical_repo_set(tmp_path: Path) -> None:
    # Real repo invariant: all on-disk ADRs are Accepted + 7-section.
    _stage(tmp_path, list(range(1, 17)))  # 16 ADRs — matches real Phase 5
    findings = check(tmp_path, set(range(1, 17)))
    assert findings == [], f"expected clean audit; got: {findings}"


def test_check_passes_for_accepted_with_qualifier(tmp_path: Path) -> None:
    """Mirrors real ADR-0016: `**Status:** Accepted (commitment) — Deferred (...)`."""
    _stage(tmp_path, [16], status_line="**Status:** Accepted (commitment) — Deferred (implementation)")
    _stage(tmp_path, [n for n in range(1, 16)])
    assert check(tmp_path, set(range(1, 17))) == []


def test_check_reports_missing_adr(tmp_path: Path) -> None:
    _stage(tmp_path, list(range(1, 16)))  # missing 0016
    findings = check(tmp_path, set(range(1, 17)))
    kinds = {(f.kind, f.adr_number) for f in findings}
    assert ("missing", 16) in kinds, findings


def test_check_reports_unexpected_extra(tmp_path: Path) -> None:
    _stage(tmp_path, list(range(1, 17)) + [9999])
    findings = check(tmp_path, set(range(1, 17)))
    assert any(f.kind == "unexpected_extra" and f.adr_number == 9999 for f in findings), findings


def test_check_reports_wrong_status(tmp_path: Path) -> None:
    _stage(tmp_path, list(range(1, 16)))
    _stage(tmp_path, [16], status_line="**Status:** Proposed")
    findings = check(tmp_path, set(range(1, 17)))
    [bad] = [f for f in findings if f.kind == "wrong_status"]
    assert bad.adr_number == 16, bad
    assert "Proposed" in bad.message, bad


def test_check_reports_missing_section(tmp_path: Path) -> None:
    _stage(tmp_path, list(range(1, 16)))
    _stage(tmp_path, [7], drop_section={7: "Tradeoffs"})
    findings = check(tmp_path, set(range(1, 17)))
    [bad] = [f for f in findings if f.kind == "missing_section" and f.adr_number == 7]
    assert "Tradeoffs" in bad.message, bad


def test_check_rejects_deprecated_and_superseded(tmp_path: Path) -> None:
    for bad in ("Deprecated", "Superseded by ADR-0099"):
        _stage(tmp_path, [16], status_line=f"**Status:** {bad}")
        findings = check(tmp_path, {16})
        assert any(f.kind == "wrong_status" for f in findings), (bad, findings)
        (tmp_path / "0016-stub.md").unlink()


def test_no_hardcoded_range_in_script_source() -> None:
    """Guard against the original drift: hardcoded `range(1, 16)`."""
    src = SCRIPT.read_text()
    assert not re.search(r"range\(\s*1\s*,\s*\d{2,}\s*\)", src), (
        "audit must enumerate from disk, not via hardcoded range"
    )


def test_parse_index_extracts_numbers_from_readme(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "| # | Title |\n|---|---|\n"
        "| [0001](0001-x.md) | foo |\n"
        "| [0002](0002-y.md) | bar |\n"
        "| [0016](0016-z.md) | baz |\n"
    )
    assert parse_index_expected_numbers(readme) == {1, 2, 16}


def test_main_cli_smoke_exits_nonzero_on_violation(tmp_path: Path) -> None:
    adr_dir = tmp_path / "ADRs"
    adr_dir.mkdir()
    readme = adr_dir / "README.md"
    readme.write_text("| [0001](0001-x.md) | foo |\n")  # expects ADR-0001
    # …but no on-disk file → missing
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--adr-dir", str(adr_dir), "--readme", str(readme)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "0001" in (result.stdout + result.stderr)
    assert "missing" in (result.stdout + result.stderr).lower()
```

Test file path: `tests/unit/build/test_audit_phase5_coverage.py` — mirrors the above shape: import `check` directly; assert structured `Violation`s on planted under-floor `coverage.json` fixtures; one CLI smoke for non-zero exit.

Test file path: `tests/unit/build/test_coverage_md_autogenerated.py` — load a frozen `coverage.json` fixture; call `render_markdown(...)`; assert the on-disk `coverage.md` is byte-identical (BLAKE3).

### Green

Both scripts are pure-core / shell as documented. Implement only what each red test demands. The `check(...)` core in `audit_phase5_adrs.py` is ~60 LOC of `pathlib` + `re`; the shell is ~25 LOC of `argparse` + printing. Same shape for `audit_phase5_coverage.py`. Do not over-engineer the report format — one finding per line is fine.

### Refactor

- Promote magic strings (the seven required section names, the status regex) to module-level `Final` constants — already done in the outline; ensure they remain at module scope so future ADRs that need a different shape (e.g., Phase 6 closeout) can import them.
- Split per-file checks (`_status_findings`, `_section_findings`) into separate pure helpers each ≤ 20 LOC for unit-level mutation coverage.
- Add a `--json` flag emitting findings as a JSON array to stdout — useful for the CI summary view; not required for the audit gate.

## Files to touch

| Path | Why |
|---|---|
| `scripts/audit_phase5_adrs.py` | New audit script (pure core + thin shell). |
| `scripts/audit_phase5_coverage.py` | New coverage-floor audit (mirrors S4-04 / ADR-0005 shape). |
| `tests/unit/build/test_audit_phase5_adrs.py` | Direct-import red + adversarial tests; one CLI smoke. |
| `tests/unit/build/test_audit_phase5_coverage.py` | Same shape; planted-violation fixtures. |
| `tests/unit/build/test_coverage_md_autogenerated.py` | Fence: hand-edits to `coverage.md` fail CI. |
| `docs/phases/05-sandbox-trust-gates/README.md` | Add `**Status:** Done` header + §"Exit criteria" + §"Goals completion" + §"Gap closure". |
| `docs/phases/05-sandbox-trust-gates/coverage.md` | New — autogenerated per-module coverage report. |
| `docs/phases/05-sandbox-trust-gates/stories/README.md` | Final `Done: 40` bookkeeping. |
| `docs/phases/05-sandbox-trust-gates/ADRs/*.md` | Touch only those needing `TBD` → dated postscript rewrites. |
| `.github/workflows/ci.yml` | Add the two audit-script invocations (note: `.yml`, not `.yaml`). |

## Out of scope

- Roadmap-level closure for the *whole project* — this story closes Phase 5 only; Phase 6 starts after.
- Writing new ADRs — every ADR already exists per `../ADRs/README.md`; only audit + dated-postscript consequence updates.
- Backporting coverage to earlier phases.
- Phase 6 LangGraph wrap — explicitly Phase 6.
- Performance trend dashboards — Phase 14 ops.
- Extracting a shared cross-phase ADR-audit kernel (`scripts/_adr_audit.py`) — Phase 5 is the *first* such audit; per Rule 2, defer the kernel until the third closeout story needs it (rule-of-three). See Notes.

## Notes for the implementer

- **Source of truth for "what ADRs should exist" is `../ADRs/README.md`'s index table — not a hardcoded range.** The audit parses the table at runtime. The previous draft of this story shipped `range(1, 16)` and would have silently mis-counted ADR-0016 the day it landed; do not regress on this.
- **Repo Nygard convention is seven `##` sections, not four** — surveyed across all 16 Phase-5 ADRs as of 2026-05-26. `Status` is a `**Status:**` header field near the top, **not** a `## Status` section. The required-sections constant must reflect this.
- **Accepted-with-qualifier is canonical.** ADR-0016's status line is `**Status:** Accepted (commitment) — Deferred (implementation; lands before Phase 7 ships)` — a real-world pattern for ADRs whose commitment is locked but whose implementation slot lives in a later phase. The status regex must accept this and only this kind of qualifier.
- **Floor-expansion candidates** — the three modules `gates/contract.py`, `gates/retry_ledger.py`, `sandbox/signals/models.py` would be reasonable to add to the 95/90 floor list, but arch Goal 12 only mandates two. If the implementer wants to add them, **amend an ADR first** (likely `phase-arch-design.md §Goals` clarification + ADR-NN-NNNN); do not silently tighten.
- **Coverage report must be regenerable.** `coverage.md` ships with a `<!-- AUTOGENERATED ... -->` marker as its first line and a fence test asserts byte-identity against a fresh regeneration. Hand edits will fail CI.
- **README exit-criteria table must reference story IDs, not commit hashes** — IDs are stable, hashes are not.
- **Future ADR-audit kernel.** When Phase 6 or later closeout stories add the third ADR-audit script, extract the pure `check(...)` body to `scripts/_adr_audit.py` and parameterise by `(phase_slug, expected_count_source, required_sections, status_regex)` — at that point the rule-of-three threshold is hit and the abstraction earns its keep. Until then, copying the ~60 LOC core is cheaper than the wrong shared kernel (per the parsers/_io.py + coordinator/budgeting.py precedents).
- **CI workflow file is `.yml`, not `.yaml`.** Trivial but the script's smoke test should pin the right path.
- **Do NOT relax any coverage floor to make the audit pass.** If `gates/runner.py` is at 94% line, write more tests — that's the contract. Phase 5's whole testing investment was about hitting these floors.
- **Do not delete `_attempts/`.** After this story is `Done`, the per-story attempt logs remain — they are evidence of the autonomous-implementation loop's behavior and may inform Phase 15 ("agentic recipe authoring").
- **Final phase status:** update the phase folder's top-level `README.md` to include `**Status:** Done — 2026-05-26 (closed by S8-04)` as a header line. This becomes greppable for `phase-shakedown` and the future cross-phase status dashboard.
