# Reporting — the e2e-report markdown template

Every shakedown run produces exactly one report file at:

```
docs/phases/{phase}/_e2e/e2e-report-{ISO-utc}.md
```

Where `{ISO-utc}` is `YYYY-MM-DDTHHMMSSZ` (filename-safe ISO 8601;
seconds-precision so back-to-back runs in the same minute don't
collide). On the rare same-second collision, append `-{counter}`.

The report is committed (or staged, if `--no-commit`) — it lives in
git as the phase's audit trail.

## Required sections (in this exact order)

```markdown
---
phase: 03-vuln-deterministic-recipe
run_id: 01J9X8Y7Z6Q5P4N3M2L1K0
generated_at: 2026-05-19T03:24:18Z
git_sha: 7f83cd0ea550f9f9e245b81530f75e94adb03a1e
shakedown_version: 0.2.0
auto_detected_phase: true   # was the phase auto-detected, or named?
total_findings:
  trivial: 0
  bounded: 1
  sub_system: 2
  architectural: 1
  critical: 0
findings_by_scope:
  own_phase: 3
  cross_phase: 1
gate_summary:
  ruff: pass
  ruff_format: pass
  mypy: pass
  pytest: pass (4263)
  fence: pass (80)
  lint_imports: pass (4)
  make_check: pass
total_wall_clock_seconds: 412
total_tokens_consumed: 28430
---

# Shakedown report — Phase 03 (vuln-deterministic-recipe) — 2026-05-19

## Executive summary

Three findings, none critical. Highest is a Phase-1↔Phase-3 contract
drift around `PackageManager` re-export that crosses module
boundaries (architectural — ADR draft at
`ADRs/_drafts/0014-package-manager-ownership.md`). One bounded bug in
the coordinator-built ctx (spawned task `<task-id>`) and two
sub-system gaps in the `roadmap.md`-promised test architecture (story
drafts under `stories/_drafts/`).

All structural-defence fences green. The phase's exit criteria are
within reach pending the architectural decision.

## Execution plan

What we ran, derived from the discovery cascade. See
`references/discovery.md` for how this was assembled.

| # | Source | Command | Mutates | Exit | Wall-clock |
|---|---|---|---|---|---|
| 1 | contributing.md | `make check` | no | 0 | 105s |
| 2 | contributing.md | `make lint-imports` | no | 0 | 4s |
| 3 | contributing.md | `make fence` | no | 0 | 1s |
| 4 | High-level-impl §Step 4 | `pytest tests/property/test_cache_invariant.py -v` | no | 5 (file missing) | 0s |
| 5 | High-level-impl §Step 4 | `pytest tests/contract/ -m contract` | no | 5 (dir missing) | 0s |
| 6 | generic floor | `codegenie gather tests/fixtures/polyglot/` | yes (.codegenie/) | 0 | 18s |
| 7 | generic floor | `codegenie audit verify --runs-dir … --cache-dir … --yaml-path …` | no | 0 | 1s |
| 8 | generic floor | `pytest tests/fence/ -q --no-cov` | no | 0 | 28s |
| 9 | generic floor | `pytest tests/smoke/ -q --no-cov` | no | 0 | 56s |
| 10 | previous-report carry-forward | recheck `BudgetingContext.output_dir` | no | 1 (xfail) | 0s |

## Findings

### F-01 — Architectural — `PackageManager` ownership crosses Phase 1 / Phase 3

**Scope:** `cross_phase` (Phase 1 ↔ Phase 3 — surfaced through Phase 3's
own discovery, not Phase 3's authored code drift)

**Evidence:** `tests/fence/test_per_submodule_cold_start.py` has 28
entries in `_KNOWN_BROKEN_PRE_FIX`; static cycle confirmed
(`types/identifiers → probes/node_build_system → probes/__init__ →
layer_b/dep_graph → depgraph/__init__ → depgraph/registry →
types/identifiers`). Phase 1 ADR-0013 puts `PackageManager` in
`probes/node_build_system`; Phase 3 stories consume it through
`types/identifiers`'s re-export, which closes the cycle.

**Route:** `phase-architect` → draft ADR at
`ADRs/_drafts/0014-package-manager-ownership.md` (link)

**Why architectural, not bounded:** the fix changes module ownership,
which is contract; doing it without an ADR amendment would silently
drift the Phase 1 commitment. The technical fix is small; the
decision is consequential.

### F-02 — Bounded — `BudgetingContext` missing `ProbeContext` attrs

**Evidence:** runtime witness at
`tests/fence/test_probe_context_conformance.py` (xfail today). Drift:
`output_dir`, `cache_dir`, `logger`, `config`,
`image_digest_resolver`. Three probes (`scip_index`,
`tree_sitter_import_graph`, `slo`) AttributeError silently under
coordinator failure-isolation.

**Route:** `mcp__ccd_session__spawn_task` — task ID `<id>` (link)

**Why bounded, not architectural:** the contract itself (ADR-0007) is
fine; only the implementation drifted. Single-file fix in
`coordinator/budget.py`; one new field set in `_make_probe_context`.

### F-03 — Sub-system — `tests/property/test_cache_invariant.py` missing

**Evidence:** `roadmap.md` line 50 (Phase 3 row, item a) names this
file as a shipped Phase 3 capability. File does not exist.

**Route:** `phase-story-writer` → draft story at
`stories/_drafts/S10-01-cache-invariant-property-test.md` (link)

**Why sub-system:** needs ACs (which Hypothesis strategies? what
budget?), a TDD plan (red test for cache invariance violation), and
multi-file touch (the property test + a fixture generator + a new
pytest marker registration in `pyproject.toml`).

### F-04 — Sub-system — `tests/contract/` tier doesn't exist

**Evidence:** `roadmap.md` line 50 (Phase 3 row, item d) names the
`tests/contract/` tier for npm/pnpm/yarn/jq. Directory absent.

**Route:** `phase-story-writer` → draft story at
`stories/_drafts/S10-02-contract-tests-tier.md` (link)

## Gate summary

| Gate | Status | Detail |
|---|---|---|
| ruff check | ✅ pass | All checks passed |
| ruff format --check | ✅ pass | 532 files formatted |
| mypy --strict src/ | ✅ pass | 150 source files |
| pytest (full) | ✅ pass | 4263 passed, 33 skipped, 2 xfailed |
| make fence | ✅ pass | 80 passed |
| make lint-imports | ✅ pass | 4 contracts kept, 0 broken |
| codegenie audit verify | ✅ pass | mismatch_count=0 |

## Inline fixes applied this run

None.

## Critical escalation

None this run.

## Verification footer (Next-run primer)

The next shakedown for this phase should read this section first.

**Carry-forward (still open as of this run):**
- F-01 (Architectural) — ADR draft is open; recheck whether it has
  been promoted out of `_drafts/`. If promoted and the static cycle is
  fixed, the cold-start fence skip-set should shrink; promote any
  sentinel that XPASSes.
- F-02 (Bounded) — spawned task `<task-id>`; recheck whether
  `_KNOWN_BROKEN_PRE_FIX` entry "BudgetingContext drift" is gone.
- F-03 (Sub-system) — story draft is open; recheck whether
  `tests/property/test_cache_invariant.py` now exists and passes.
- F-04 (Sub-system) — story draft is open; recheck whether
  `tests/contract/` directory exists.

**Promotion thresholds:** if F-01 appears in the next run still
unfixed, **page** (it's a recurrence of architectural — humans
underrating the seriousness).

**Recently closed (don't re-flag):**
- None this run.

---

*Generated by phase-shakedown v0.1.0 on 2026-05-19T03:24:18Z.*
```

## Conventions

- **Sections are in fixed order** — don't reorder. The frontmatter +
  Executive summary + Execution plan + Findings + Gate summary +
  Inline fixes + Critical + Verification footer ordering is the
  contract the grading scripts and the next-run carry-forward step
  depend on.
- **Findings are numbered F-01, F-02, …** in the order discovered.
  Don't re-number across reports.
- **Every finding has these subsections**: `Scope`, `Evidence`, `Route`, `Why-this-class`.
  The "Why-this-class" sentence is what a reviewer reads first when
  questioning a triage decision.
- **The `Scope` field** is one of:
  - `own_phase` — the finding is genuinely scoped to the phase being shaken down
  - `cross_phase` — the finding surfaced in this phase's run but its
    root cause lives in another phase (it came through the generic
    floor sweep, not the phase's own commands)

  Cross-phase findings should also name the originating phase in the
  finding title (e.g. "F-01 — Architectural — `PackageManager`
  ownership **crosses Phase 1 / Phase 3**"). Audit-trail readers
  filter by scope: a Phase 0 closeout reviewer doesn't want a long
  list of Phase 7 contaminations cluttering their view — but they
  also want to know they exist.
- **Links in the Route line point to the actual downstream artifact**
  (task ID, draft story file path, draft ADR file path). If the
  downstream skill errored, link to a placeholder + flag the error
  as a separate finding.
- **The Verification footer is the load-bearing section for cross-run
  continuity.** Future shakedowns read it first. Be thorough.

## YAML frontmatter schema

Required keys:
- `phase` (string — folder name)
- `run_id` (ULID — generated at start of run)
- `generated_at` (ISO-8601 UTC, seconds precision)
- `git_sha` (commit at start of run)
- `shakedown_version` (semver — match the skill's version)
- `auto_detected_phase` (bool)
- `total_findings` (object with 5 integer keys: trivial, bounded,
  sub_system, architectural, critical)
- `findings_by_scope` (object with 2 integer keys: own_phase, cross_phase;
  sum must equal sum of `total_findings`)
- `gate_summary` (object — one key per gate, value is "pass" or "fail
  (<count>)" or "skipped (<reason>)")
- `total_wall_clock_seconds` (number)
- `total_tokens_consumed` (number — best-effort; from the harness's
  notification)

A future report can be machine-parsed against this schema (the
project's doc-consistency fence at `tests/unit/test_doc_consistency.py`
is the natural home for adding a shakedown-report parser).
