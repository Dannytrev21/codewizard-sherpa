# Validation report — S1-11 `forbidden-patterns` extension + `mypy --warn-unreachable` rollout + nine ADRs

**Story:** [`../S1-11-forbidden-patterns-mypy-adrs.md`](../S1-11-forbidden-patterns-mypy-adrs.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

Two ground-truth shifts forced substantial revision of the original draft, and seven harden-tier gaps were closed:

1. **`warn_unreachable = true` is already set REPO-WIDE in `pyproject.toml` line 134** — committed by Phase 0 S1-02 (commit `3944f02`, 2026-05-13) months before this story was written. The original draft's premise of "per-module rollout" is structurally outdated: Phase 0 elected broader-than-arch scope from day 1. The validator rewrote AC-4 from a *configuration* AC into a *verification* AC (the repo-wide setting is preserved; no override silently weakens it for the five named modules), and replaced the manual `delete-an-arm; observe mypy fails` procedure (AC-5) with an automated subprocess-mypy fixture test that runs in CI. Phase 0's deviation from arch is recorded as honored-broader-than-arch — not silently narrowed (narrowing would be a Phase-0 surgical edit, outside this story's scope; S8-04 owns the backlog decision).

2. **02-ADR-0010 file already exists** under `ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md`. The original draft's AC-11 punted the reconciliation decision ("Pick at impl time"). The validator locked it: the Step-1 nine are 0001–0009; the 0010 file's pre-existing presence is tolerated (README disambiguates via a "Pre-drafted; enforcement code lands in S3-02" sub-bullet); its enforcement code still ships in S3-02 per the dependency DAG. The test's `REQUIRED_ADRS` list stops at 0009.

Other harden-tier edits applied to the story file:

- **AC-1 strengthening**: the regex `\.model_construct\s*\(|\bmodel_construct\s*=` is named verbatim; the error-message contract tightened from `or` to `and` (both `02-ADR-0010 §Decision` AND `production ADR-0033 §3` must appear in every emitted line).
- **AC-2 mutation-resistance**: the positive matrix expanded from 7 cells (one per banned package) to 28 cells (7 packages × 4 source forms: class call, instance call, renamed-class call, kwarg-style). A regex that catches only `Foo.<dot>` would have passed the 7-cell matrix; the 28-cell matrix collapses one column instead of one cell.
- **AC-3 negative coverage**: extended to pin the `applies_when` predicate as the SINGLE source of path-scoping; documents the comment-form false-positive as acceptable (regex is structural defense, not AST-precise).
- **AC-6 Nygard sections**: expanded from 5 to all 8 actual sections used by this phase's ADRs (verified across `0001`, `0006`, `0009`, `0010`); added a `**Status:** Accepted` check to prevent Draft ADRs from passing.
- **AC-7 reframing**: from VERIFY to WRITE. The Phase 2 README does NOT currently list ADRs (verified at validation time, 2026-05-15) — AC-7 mandates ADDING the section, not just checking it exists.
- **AC-14 added** — Phase-0 regression invariant. The existing 11 ADR-0008/ADR-0012 rules must still fire after the `_RULES` refactor. A loop-body refactor that silently truncated the list would pass AC-1/AC-2/AC-3 but fail AC-14.
- **AC-15 added** — Open/Closed structural invariant. Elevated from Notes-for-implementer to an observable AC because the design pattern crosses the rule-of-three threshold (`_RULES` previously carried two rule kinds — literal-pattern regex and anchored regex; this story adds a third — path-scoped regex; CLAUDE.md "Three similar lines is better than premature abstraction" is satisfied AT the third site). The refactored `_RULES` row shape is a `Rule` dataclass with `applies_when: Callable[[Path], bool]` predicate. Future path-scoped rules require zero edits to `_scan_file()` / `main()` — only a new `Rule(...)` entry. Pinned via a structural test that imports `_RULES` and asserts every row exposes a callable `applies_when` + that the model_construct rule's predicate honors path scoping correctly + that the 11 Phase-0 rules retain the default-always predicate.
- **Test-script path corrected** from `scripts/forbidden_patterns.py` → `scripts/check_forbidden_patterns.py` (verified existence at validation time).
- **Implementation outline rewritten** to lead with the `Rule` dataclass refactor (the load-bearing design change), follow with the new path-scoped rule entry, and explicitly mark `pyproject.toml` as untouched.
- **Files-to-touch table rewritten** with explicit create/modify markers and the corrected script path.
- **Notes-for-implementer expanded** to lock the AC-11 decision, document the broader-than-arch `warn_unreachable` reality, surface the regex-precision trade-off as a deliberate structural choice, and call out the pytest collection exclusion for the mypy fixture.

The Acceptance criteria block expanded from 13 ACs to 15 ACs. The TDD plan grew from 3 test files to 5 test files + 1 fixture; total tests grew from ~10 to ~40 (driven mostly by the 28-cell parametrize matrix in AC-2 and the structural rule-shape tests in AC-15).

No `NEEDS RESEARCH` findings — Stage 3 skipped (every gap was answerable from the arch, phase ADRs, direct source scan of `scripts/check_forbidden_patterns.py` + `pyproject.toml` + `.pre-commit-config.yaml`, and `git blame` on `pyproject.toml`).

## Context Brief (Stage 1)

### Story snapshot

- **Goal (rewritten):** (1) Extend `scripts/check_forbidden_patterns.py` to ban `model_construct` under seven Phase 2 packages — refactoring the rule loop to make path-scoping a first-class predicate; (2) **verify** the already-repo-wide `mypy warn_unreachable = true` works end-to-end via an automated fixture-based exhaustiveness test (Phase 0 S1-02 enabled it broader-than-arch — this story does NOT narrow); (3) verify the nine Step-1 ADRs (0001–0009) exist, are 8-section-Nygard-format, and are listed in the phase README (currently no ADR-listing section — this story adds it).
- **Non-goals:** RedactedSlice/SecretRedactor code (S3-01/S3-02); per-module mypy overrides (already covered by repo-wide setting); 02-ADR-0010 enforcement code (S3-02); ADR-listing semantics in any other phase's README.

### Phase 2 exit criteria touched

- **G3.** Phase 0/1 frozen surfaces unchanged — verified by AC-14 regression test (existing 11 rules still fire).
- **G10.** Nine new ADRs landed alongside code — verified by AC-6/AC-7 tests; 0010 is documented as Step-3 deliverable.

### Load-bearing commitments touched

- **CLAUDE.md "Extension by addition"** — AC-15 is the explicit Open/Closed seam: future path-scoped rules are new `Rule(...)` entries, never edits to the loop body.
- **CLAUDE.md "Determinism over probabilism"** — the rule is deterministic regex, no LLM.
- **CLAUDE.md "Three similar lines is better than premature abstraction"** — the `Rule` dataclass refactor is triggered AT the third rule kind, not preemptively.
- **CLAUDE.md "Surgical changes"** — `pyproject.toml` is NOT touched (the `warn_unreachable` setting is already broader-than-arch; narrowing is out of scope).
- **02-ADR-0010 §Decision + production ADR-0033 §3** — the rule's `advice` message names both verbatim; AC-1 and AC-2 enforce the `and` contract.

### Sibling-family lineage

- This story is the **3rd story in the family of structural-defense-as-script work** in this codebase: Phase 0 S1-04 shipped the original `check_forbidden_patterns.py` with the 11-rule list (ADR-0008 + ADR-0012); Phase 0 S2-02 added the `forbidden-patterns` hook entry in `.pre-commit-config.yaml`; S1-11 is the 3rd addition.
- **Rule-of-three threshold:** REACHED — the procedural shape (flat `_RULES` tuple + path-scoping-by-yaml-glob) is now demonstrably insufficient. The dataclass refactor is the natural Open/Closed extract at this exact site.

### Phase / arch constraints

- **02-ADR-0010** (smart-constructor at writer boundary) — the rule's `advice` field cites §Decision verbatim.
- **Production ADR-0033 §3** (no primitive obsession on domain identifiers) — the rule's `advice` field cites §3 verbatim; the `_RULES` row's path predicate uses `_PHASE2_BANNED_PACKAGES: frozenset[str]` (raw `str` is acceptable for filesystem path components — primitive obsession discipline does not apply to filesystem APIs that themselves traffic in `str`).
- **`phase-arch-design.md §"CI gates"` job 7** — repo-wide `--strict` + per-module `warn_unreachable`. Reality is broader: `warn_unreachable = true` at top level (Phase 0 S1-02 deviation). Documented; no override silently weakens the named modules.
- **`phase-arch-design.md §"Anti-patterns avoided"` row 12** — `model_construct` ban; the structural defense.
- **02-ADR-0006 §Consequences** — every `IndexFreshness` consumer closes its match with `assert_never`; the AC-5 fixture is the test target for this invariant.

### Goal-to-AC trace (post-edit)

- AC-1 → goal (1) — pins regex + advice contract.
- AC-2 → goal (1) — 28-cell positive matrix.
- AC-3 → goal (1) — path-scoping negative.
- AC-4 → goal (2) — verifies repo-wide invariant + no-override-weakens-it.
- AC-5 → goal (2) — automated fixture-based mypy test.
- AC-6 → goal (3) — nine ADRs exist + 8-section Nygard + Status: Accepted.
- AC-7 → goal (3) — README adds ADR-listing section.
- AC-8 → cross-cut — Step-1 smoke test.
- AC-9, AC-10 → preserve frozen Phase 0/1 surfaces.
- AC-11 → goal (3) — Step-1 ADR set locked to 0001–0009.
- AC-12, AC-13 → quality gates.
- AC-14 → goal (1) — Phase-0 regression invariant.
- AC-15 → goal (1) — Open/Closed structural invariant.

### Open ambiguities (Stage 1 exit gate)

None remaining post-edit. The Phase 0 `warn_unreachable` deviation is now documented; AC-11 is locked; the README ADR-listing semantics are written, not inferred.

## Stage 2 — Critic findings (synthesized inline; four lenses)

### Coverage critic

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| C-1 | block | AC-4/AC-5 premise FALSE — `warn_unreachable=true` already enabled repo-wide (verified via `git blame`). | Rewrote AC-4 as verification gate; replaced AC-5's manual procedure with automated subprocess-mypy fixture test. |
| C-2 | harden | AC-7 says "README contains" but README has NO ADR section. | Reframed AC-7 as WRITE; specified placement after "Reading order"; pinned 0010 sub-bullet. |
| C-3 | harden | AC-11 punts decision to impl time. | Locked: REQUIRED_ADRS = 0001–0009; 0010 file tolerated; README disambiguates. |
| C-4 | harden | AC-6 lists 5 Nygard sections; actual ADRs have 8. | Expanded to all 8 + `**Status:** Accepted` check. |
| C-5 | harden | AC-1 error-message check is `or`; story prose says "names both". | Tightened to `and` — both substrings must appear in every line. |
| C-6 | harden | No regression coverage for existing 11 Phase-0 rules. | Added AC-14 + regression test. |
| C-7 | harden | No structural pin on Open/Closed shape of `_RULES`. | Added AC-15 + structural rule-shape test. |

### Test Quality critic

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| T-1 | block | Script path `scripts/forbidden_patterns.py` wrong (FileNotFoundError on red). | Corrected to `scripts/check_forbidden_patterns.py` everywhere; pinned in References. |
| T-2 | harden | Only `Foo.model_construct(x=1)` covered — class-call form. A regex that ignores instance-call or kwarg-style passes. | 28-cell parametrize: 7 packages × 4 forms (class_call, instance_call, renamed_class, kwarg). Mutation guard. |
| T-3 | harden | Path-scoping surface ambiguous (script vs. pre-commit yaml). | Pinned in AC-1: scoping MUST live in script via `applies_when`; pre-commit yaml `files:` regex stays loose. Test surface = runtime surface. |
| T-4 | harden | No mutation test for regex precision (comment-form false positive). | Documented in AC-3 + Notes; deliberate structural choice. |
| T-5 | harden | `test_mypy_top_level_warn_unreachable_is_NOT_set` would fail on current main. | Replaced with `test_repo_wide_warn_unreachable_is_true` (locks the broader-than-arch invariant). |

### Consistency critic

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| K-1 | block | Story's per-module premise contradicts Phase 0 reality. | Validation notes document the broader-than-arch deviation; story refocused. |
| K-2 | harden | 02-ADR-0010 file already exists; story AC-11 is undecided. | Locked AC-11. |
| K-3 | harden | Phase 2 README has no ADR section (verified at validation time). | AC-7 reframed as WRITE. |

### Design Patterns critic

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| D-1 | harden, elevate-to-AC | Prescribed impl (`_is_in_phase2_banned()` + loop branch) is procedural special-casing. Third rule kind → Open/Closed extract justified. | Added AC-15 + Rule dataclass + `applies_when` predicate. Implementation outline rewritten. |
| D-2 | nit (no change) | `_PHASE2_BANNED_PACKAGES` as `tuple[str, ...]` — could be `Literal[...]`. | Defer — primitive obsession discipline does not apply to filesystem-path components; raw `frozenset[str]` is honest about what filesystem APIs traffic in. |
| D-3 | nit (no change) | ADR-Nygard-section validation could be a reusable helper. | Single consumer; defer until a second consumer appears. |

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap was answerable from:

- `phase-arch-design.md` (anti-patterns row 12, CI-gates job 7, Path-to-production end state table)
- The 9 referenced ADRs (Nygard shape verified)
- Direct source scan of `scripts/check_forbidden_patterns.py`, `.pre-commit-config.yaml`, `pyproject.toml`
- `git blame -L 129,140 pyproject.toml` (revealed Phase 0 S1-02 origin of repo-wide `warn_unreachable`)
- `git log --all --oneline -- pyproject.toml` (confirmed Phase 0 was the first author of the file's mypy section)

## Stage 4 — Edits applied

All edits applied to [`../S1-11-forbidden-patterns-mypy-adrs.md`](../S1-11-forbidden-patterns-mypy-adrs.md) in place. Summary of sections modified:

| Section | Edit type | Notes |
|---------|-----------|-------|
| Header | Title clarified | "rollout" → "verification" reflects the post-Phase-0 reality. |
| Header | ADRs-honored line trimmed | 0001-0009 (was 0001-0010). |
| Validation notes | NEW block | Documents the two ground-truth shifts. |
| Context | Rewritten | Reflects verification-not-configuration framing; cites Phase 0 commit. |
| References — where to look | Rewritten | Corrected script path; added line-precise references; named `[tool.mypy]` line 134 origin. |
| Goal | Rewritten | Now describes refactor + verification + write semantics. |
| Acceptance criteria | Expanded 13→15 | All ACs strengthened; 14/15 added. |
| Implementation outline | Rewritten | Leads with `Rule` dataclass refactor; pins `pyproject.toml` as untouched. |
| TDD plan | Expanded | 3 test files → 5 test files + 1 fixture; 28-cell parametrize matrix in AC-2. |
| Files to touch | Rewritten | Explicit create/modify markers; corrected script path; `pyproject.toml` removed. |
| Notes for the implementer | Expanded + rewritten | Adds dataclass-refactor rationale, AC-11 lock, broader-than-arch documentation, regex-precision trade-off, pytest collection exclusion. |

## Verdict

**HARDENED.** The story passes all four critics post-edit. The original draft was sound in intent (extend forbidden-patterns; document the nine ADRs) but built on two false premises (per-module mypy work; 02-ADR-0010 deferred). The validator absorbed both shifts without changing the story's identity. The phase-story-executor can now proceed against this hardened story without needing to make implementation-time judgment calls on items that the validator should have removed.
