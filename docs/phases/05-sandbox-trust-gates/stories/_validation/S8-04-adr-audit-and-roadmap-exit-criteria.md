# Validation report: S8-04 — ADR audit + roadmap exit-criteria checklist + final coverage report

**Validated:** 2026-05-26
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S8-04 is the Phase 5 closeout audit story — no new runtime code, only an audit script + a coverage script + documentation updates that *prove* Phase 5 met its bar. The Goal and structure are sound. The critics surfaced four classes of defect that, if shipped as-is, would have produced a script that *passes against fake fixtures but fails on the real ADR set*:

| Draft assumption / shape | Reality / hardened shape |
|---|---|
| `EXPECTED_ADRS = {f"{i:04d}" for i in range(1, 16)}` — hardcoded 15-ADR range; "ADRs honored: ADR-0001 through ADR-0015" | Phase 5 already has **16 ADRs** on disk; ADR-0016 (per-task-class eval harness as trust evidence) was added during the Phase-6.5 preamble per the roadmap. The script as written would either miss 0016 (silent gap) or — paired with the implementer's `--allow-additional` note — fail the audit unhelpfully. Hardened: enumerate `ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")` and assert (a) the discovered numbers form a contiguous range starting at `0001`, (b) no duplicates, (c) the count matches `len(rows-in-ADRs/README.md-index-table)` — the README is the source of truth for "what should exist," not a magic number. |
| Nygard section regex `r"^## (Context\|Decision\|Consequences\|Status)\b"` — four sections | Actual Phase 5 ADRs use **seven** sections: `Context`, `Options considered`, `Decision`, `Tradeoffs`, `Consequences`, `Reversibility`, `Evidence / sources` (verified across all 16 ADRs). There is **no `## Status` section** — `Status` is a header field (`**Status:** Accepted` near the top). The draft regex would falsely pass any ADR that omits `Options considered`, `Tradeoffs`, `Reversibility`, or `Evidence / sources` and would falsely fail every real ADR (none has `## Status`). Hardened: required sections = `{Context, Options considered, Decision, Tradeoffs, Consequences, Reversibility, Evidence / sources}`; status is checked via the header line, not a section. |
| Status regex `r"^\*\*Status:\*\* Accepted$"` — strict end-of-line match | ADR-0016 has `**Status:** Accepted (commitment) — Deferred (implementation; lands before Phase 7 ships)` — a real-world "Accepted-with-qualifier" pattern. The `$` anchor would fail it as if it were `Proposed`. Hardened: regex `^\*\*Status:\*\*\s+Accepted(\s+\([^)]+\))?(\s+—\s+.+)?$` — matches `Accepted` optionally followed by a parenthetical qualifier and an em-dash postscript; rejects `Proposed`, `Deprecated`, `Superseded` outright. |
| `_NYGARD_TEMPLATE` in TDD red tests includes `## Status\nAccepted` | This template is **not Nygard-canonical for this repo**. A passing test against this template proves nothing about the real ADR shape. Hardened: rewrite the template to mirror the actual repo convention — `**Status:** Accepted` header field + the seven `##` sections — so the red tests fail on the *same things* the real audit catches. |
| TDD plan invokes the script via `subprocess.run(...)` with a CWD-staged fake repo and copies the script source into the staged tree | Brittle and slow. The codebase **precedent** (`scripts/check_coverage_carve_outs.py` + `tests/unit/build/test_coverage_carve_outs.py`, S4-04 ADR-0005) is functional-core / imperative-shell: pure `check(...)` function the test imports and calls directly, with a thin `main()` CLI wrapper. Hardened: refactor the audit into `audit_phase5_adrs.check(adr_dir: Path, expected_numbers: set[str]) -> list[Finding]` (pure) + `main()` shell; tests call `check(...)` directly with `tmp_path`-staged ADR trees; one separate subprocess smoke test asserts the CLI exit code. Test-Quality F-TQ-1: rule of three (this audit + carve-outs + coverage-floor audit) — the pattern is now load-bearing. |
| Test path `tests/scripts/test_audit_phase5_adrs.py` | `tests/scripts/` does **not exist** in this repo. The established home for script tests is `tests/unit/build/` (see S4-04). Hardened: place at `tests/unit/build/test_audit_phase5_adrs.py` and `tests/unit/build/test_audit_phase5_coverage.py`. |
| AC: "checklist whose items are 1:1 with the roadmap §"Phase 5" criteria" (~15 checkboxes); Implementation outline step 4: "Mirror the table from `phase-arch-design.md §Goals` 1–15" | **Contradiction.** The roadmap entry has **two** brief exit-criteria items (no transform unverified + 3-retry recovery demo); `final-design.md §Exit-criteria checklist` already enumerates **three**; `phase-arch-design.md §Goals` has **fifteen** verifiable goals. These are different artifacts at different granularity. Hardened: the README §"Exit criteria" section reflects the **roadmap's** items (per the existing `final-design.md §Exit-criteria checklist` shape — 3 items); a *separate* §"Goals completion" table in the README mirrors the 15 arch goals with one row each, story-ID-anchored. Two artifacts, two purposes, no conflation. |
| Coverage floors expanded beyond arch Goal 12: AC adds `gates/contract.py`, `gates/retry_ledger.py`, `sandbox/signals/models.py` to the 95/90 list | Arch Goal 12 only requires 95/90 on `gates/runner.py` + `sandbox/contract.py`. Expanding the set is reasonable defense-in-depth, but it must be justified or trimmed — silent tightening becomes a hidden contract. Hardened: keep only the two arch-mandated modules at the 95/90 floor; surface the three additional modules as a **Notes for the implementer** recommendation (raise via ADR amendment if the implementer wants to bake them into the audit). Source-of-truth wins; pattern-expansion is recorded for follow-up. |
| `.github/workflows/ci.yaml (or equivalent)` | The actual file is `.github/workflows/ci.yml` (verified). "(or equivalent)" is vague — a precise path lets the executor's validator binary-check. Hardened: pin `.github/workflows/ci.yml`; document the exact two `run:` lines to add. |
| Mutation-resistance: `test_audit_fails_on_non_accepted_status` asserts only `"Status" in (result.stderr + result.stdout)` | A `sys.exit(1); print("Status")` script passes. Hardened: assert the *specific failing ADR number* and the *actual offending status string* both appear in the output (e.g., for `Proposed`-stamped 0007, output must include both `"0007"` and `"Proposed"`). Same upgrade for the missing-ADR and missing-section tests. |
| Test stub copies the script into `tmp_path/scripts/` and reads it via `Path("scripts/audit_phase5_adrs.py").read_text()` — uses relative paths | Tests fail if the runner's CWD is not the repo root. Hardened: anchor with `PROJECT_ROOT = Path(__file__).resolve().parents[3]` (precedent: `tests/unit/build/test_coverage_carve_outs.py`); use `PROJECT_ROOT / "scripts" / "audit_phase5_adrs.py"`. Once the script is refactored to a pure `check(...)` function, most tests no longer need the staging dance at all — they import and call directly. |
| Coverage audit gap: no AC asserts the audit fails on **unexpected** ADR numbers (e.g., a planted `9999-future.md`) | Implementation outline says "intentionally fails on *unexpected* ADR numbers too" but no AC enforces it. Hardened: add adversarial test `test_audit_fails_on_unexpected_adr_number` that plants `9999-extra.md` and asserts non-zero exit + the string `"9999"` in the output. |
| `coverage.md` regeneration policy: "Future phase work that touches `sandbox/` or `gates/` will need to re-run the script" — not a fence | A future contributor edits the file by hand and CI does not catch it. Hardened: add an AC requiring a *generation marker* at the top of `coverage.md` (`<!-- AUTOGENERATED by scripts/audit_phase5_coverage.py — do not edit by hand -->`) plus a fence test asserting the file's BLAKE3 matches a freshly regenerated copy. |
| Final phase Status: "update the phase folder's top-level `README.md` to `Status: Done` with the date" | The current README has no `**Status:**` line. Hardened: the README header gains `**Status:** Done — 2026-05-26 (closed by S8-04)`; this header field is also greppable by the audit and by future phase-shakedown runs. |
| Notes for the implementer: "Do NOT relax any coverage floor to make the audit pass" + "ADRs/README §Conventions" + "dated postscript" — solid but informal | Promote one item from Notes to an AC: any "Consequences" amendment must take the form of a `> 2026-05-26: <story-id> verified ...` blockquote, never an inline rewrite. This becomes a *historical-record* AC the audit can spot-check (search for inline rewrites that removed the original prose). |

The remaining slice — what S8-04 actually owns once these surfaces are pinned:

1. A **pure-function audit kernel** at `scripts/audit_phase5_adrs.py:check(...)` + a thin `main()` CLI shell, fully tested via direct import.
2. A **coverage-floor audit** at `scripts/audit_phase5_coverage.py` following the same shell/core split (precedent: `scripts/check_coverage_carve_outs.py`).
3. An **autogenerated** `docs/phases/05-sandbox-trust-gates/coverage.md` with a fence-pinned regeneration marker.
4. The phase **README** gaining a §"Exit criteria" block (3 roadmap-mirroring items) **and** a §"Goals completion" table (15 arch-mirroring rows + 4 gap-closure rows), each story-ID-anchored.
5. CI workflow `.github/workflows/ci.yml` running both audit scripts.

The hardened story is now ready for the executor. **No `NEEDS RESEARCH` items remain** — every fix has a same-repo precedent (S4-04 for the script shape; ADR-0008 / ADR-0016 for status-string variants; `final-design.md §Exit-criteria checklist` for the README structure).

---

## Critic findings — full audit

### Coverage critic — 8 findings (2 BLOCK, 5 HARDEN, 1 NIT)

- **F-COV-1 (BLOCK)**: ADR count drifted to 16 — hardcoded `range(1, 16)` is a factual error. → Enumerate from disk + cross-check with README index table.
- **F-COV-2 (BLOCK)**: README "Exit criteria" 1:1-with-roadmap vs Implementation outline mirror-the-15-Goals → two separate sections per the established `final-design.md §Exit-criteria checklist` shape.
- **F-COV-3 (HARDEN)**: No AC for unexpected/extra ADR numbers. → Add adversarial test + AC.
- **F-COV-4 (HARDEN)**: 95/90 floor over-specified beyond arch Goal 12. → Restrict to the two arch-mandated modules; surface the expansion candidates as Notes.
- **F-COV-5 (HARDEN)**: `coverage.md` has no regeneration fence; hand-edit risk. → Add autogen marker + BLAKE3 fence test.
- **F-COV-6 (HARDEN)**: No AC requires that the audit-output names the offending ADR by number — generic "failed" output is unhelpful for the operator. → Add to ACs.
- **F-COV-7 (HARDEN)**: Phase folder `README.md` lacks the `**Status:** Done — <date>` header field the rest of the audit infrastructure (and `phase-shakedown`) can grep. → Add to ACs.
- **F-COV-8 (NIT)**: `.github/workflows/ci.yaml` should be `ci.yml`. → Fix.

### Test Quality critic — 5 findings (1 BLOCK, 3 HARDEN, 1 NIT)

- **F-TQ-1 (BLOCK)**: TDD plan uses subprocess-only testing of a script with hardcoded relative paths — slow, brittle, mutation-tolerant. The repo precedent (S4-04 `check_coverage_carve_outs.py` + `tests/unit/build/test_coverage_carve_outs.py`) is functional-core / imperative-shell with direct-import tests. → Refactor script + tests to match precedent.
- **F-TQ-2 (HARDEN)**: `_NYGARD_TEMPLATE` does not mirror the actual repo's ADR shape (`## Status` section vs `**Status:**` header field; missing four real sections). A passing test against this template proves the wrong thing. → Rewrite template to mirror real ADR convention.
- **F-TQ-3 (HARDEN)**: Mutation-resistance — `"Status" in output` passes a trivial-failure script. → Assert specific failing ADR id + offending status string.
- **F-TQ-4 (HARDEN)**: Tests use relative `Path("scripts/...")` rather than anchored `PROJECT_ROOT`. → Anchor.
- **F-TQ-5 (NIT)**: `test_audit_passes_with_all_15_accepted_adrs` should be `_all_NN_accepted` with NN parameterised from `EXPECTED_NUMBERS` — keeps the name accurate as ADR count grows.

### Consistency critic — 6 findings (1 BLOCK, 4 HARDEN, 1 NIT)

- **F-CONS-1 (BLOCK)**: Story header says "ADRs honored: ADR-0001 through ADR-0015" but ADR-0016 exists. The story's own audit-target enumeration is wrong. → Widen to `0001 through ADR-NNNN (audit target — all present on disk)` or simply "all ADRs in `../ADRs/`".
- **F-CONS-2 (HARDEN)**: "checklist whose items are 1:1 with the roadmap §"Phase 5" criteria" — roadmap has 2 items; story implies ~15. → Two distinct sections (roadmap-mirror + goals-mirror).
- **F-CONS-3 (HARDEN)**: Nygard sections enumerated are not what this repo uses. → Realign to the 7-section convention.
- **F-CONS-4 (HARDEN)**: Status regex too strict — falsely rejects valid Accepted-with-qualifier (ADR-0016). → Loosen to `Accepted(\s+\([^)]+\))?(\s+—\s+.+)?`.
- **F-CONS-5 (HARDEN)**: AC list expands the 95/90 floor list past arch Goal 12 without an ADR amendment. → Trim or amend an ADR; this validation chooses *trim + surface*.
- **F-CONS-6 (NIT)**: Gap closure rows reference S2-02, S5-01, S6-02, S7-03; verified — all four stories exist and are `Done`/`GREEN` in the current backlog.

### Design Patterns critic — 4 findings (3 HARDEN, 1 NIT)

- **F-DP-1 (HARDEN)**: The audit logic is conflated with I/O and reporting in one file. The codebase prefers functional-core/imperative-shell (CLAUDE.md load-bearing commitment; `scripts/check_coverage_carve_outs.py` precedent). → Pure `check(adr_dir, expected, status_regex, sections) -> list[Finding]` + thin `main()` shell; data shape `Finding = NamedTuple("Finding", kind, adr_number, message)` so the test asserts structured findings, not a stringified report. **Tagged-union opportunity:** `Finding.kind: Literal["missing", "wrong_status", "missing_section", "unexpected_extra"]` — illegal states unrepresentable.
- **F-DP-2 (HARDEN)**: Audit constants (the `0001..NNNN` range, the required sections, the status regex) are hardcoded into the Phase-5 script. The rule-of-three threshold is not yet hit (Phase 5 is the first phase to ship this audit), but it is *foreseeable* — Phase 6 closeout will need an identical audit shape. → Per Rule 2 / CLAUDE.md (`Three similar lines is better than premature abstraction`), do NOT extract a shared kernel today. Instead, surface a **`Notes for the implementer`** paragraph that records: "When Phase 6 or later closeout stories add the third ADR-audit script, extract the pure `check(...)` body to `scripts/_adr_audit.py` (per the rule-of-three precedent established by `parsers/_io.py` and `coordinator/budgeting.py`)." This keeps the option open without forcing premature abstraction.
- **F-DP-3 (HARDEN)**: Primitive obsession on ADR identifiers — strings like `"0007"` are passed around raw. → Use `tuple[int, str]` (number + filename) at module boundaries; format the four-digit zero-padded string only at report time. Avoids the `int("0001") == 1` round-tripping the draft script's regex assumes.
- **F-DP-4 (NIT)**: The "Refactor" step proposes `--fix` opening `$EDITOR` — out-of-band, hard-to-test side effect. → Drop; the audit's job is to *detect*, not to *fix*. If automated remediation is needed later, it goes through its own story.

---

## Resolution table — critic-finding → action taken

| Finding | Action |
|---|---|
| F-COV-1 (BLOCK) | AC + outline rewritten to enumerate ADRs from disk + cross-check the README index. |
| F-COV-2 (BLOCK) | AC + outline split into two distinct README sections: roadmap-mirror (3 items) + goals-mirror (15 rows). |
| F-COV-3, 5, 6, 7 | New ACs added. |
| F-COV-4 | 95/90 floor list trimmed to arch Goal 12; expansion candidates moved to Notes. |
| F-COV-8 | Path fixed throughout. |
| F-TQ-1 (BLOCK) | TDD plan rewritten to direct-import the pure `check(...)`; subprocess only for one CLI smoke. Test path moved to `tests/unit/build/`. |
| F-TQ-2 | `_NYGARD_TEMPLATE` rewritten. |
| F-TQ-3, 4, 5 | TDD test bodies tightened. |
| F-CONS-1 (BLOCK) | Story header `ADRs honored` line widened to "all ADRs in `../ADRs/`". |
| F-CONS-2, 3, 4 | ACs realigned to actual repo convention; status regex loosened. |
| F-CONS-5 | Floor scope trimmed. |
| F-CONS-6 | No change required; verified. |
| F-DP-1 | `Finding` NamedTuple + functional-core split documented as ACs. |
| F-DP-2 | Notes paragraph added — no premature abstraction, but the future-kernel signpost is laid down. |
| F-DP-3 | `tuple[int, str]` boundary documented in outline. |
| F-DP-4 | `--fix` flag dropped. |

---

## Open conflicts surfaced (none unresolved)

All four critics agreed on the substantive defects. The only resolved-via-priority case: F-COV-4 (expand the 95/90 floor) vs F-CONS-5 (don't tighten beyond arch). Consistency wins — the arch is source-of-truth; the expansion candidates are surfaced as a Note for a future ADR amendment.

---

## Verdict rationale

**HARDENED.** The story's *goal* and *structure* are correct — it is a coherent closeout audit. The defects were concrete, fact-checkable, and patchable in place without changing the goal or scope: factual drift (16 not 15 ADRs), repo-shape drift (7 not 4 sections, header field not section for Status), test-pattern drift (subprocess vs direct-import), and one source-of-truth conflation (roadmap vs goals). All fixable without restating intent. Edits applied in place; a `## Validation notes` block appended to the story under the header documenting each change with a one-line rationale.
