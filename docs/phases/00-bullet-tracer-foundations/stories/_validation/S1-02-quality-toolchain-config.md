# Validation report: S1-02 — Quality toolchain config (ruff + mypy + pytest + coverage)

**Validated:** 2026-05-12
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story file:** [`../S1-02-quality-toolchain-config.md`](../S1-02-quality-toolchain-config.md)

## Summary

S1-02 wires the four quality tools (`ruff` lint+format, `mypy --strict`, `pytest` with `pytest-asyncio`+`pytest-cov`, branch-coverage settings) into `pyproject.toml`. As written, the story's goal, ACs, and `[tool.*]`-table list all traced cleanly to `High-level-impl.md §Step 1` and `phase-arch-design.md §Testing strategy` — no `block`-class structural issues. The original TDD plan, however, was *config-introspection only* and used assertion patterns that would have let several obviously wrong implementations pass: (a) `issubset` against the `T20` family without checking `ignore`/`extend-ignore`/`per-file-ignores` for downstream weakening; (b) substring matching on the `module` field of the mypy tests-override, which never verified the override's actual flag values; (c) `in omit` rather than equality for the coverage exemption list; (d) no test for `[tool.coverage.run]`, so `--cov-branch` could be a no-op; (e) no test for `warn_unreachable=true` (which `--strict` does *not* enable by default); and (f) no behavioral test that proved `ruff` actually flags `print()` in `src/`. We rewrote the four original tests into stronger forms and added two new tests (a `[tool.coverage.run]` shape test and a subprocess-driven behavioral test that runs `ruff check` against a `print('canary')` fixture under `src/`). Two new ACs (AC-8, AC-9) were added; AC-1, AC-2, AC-4 were strengthened in place; AC-5's unverifiable "was committed at the red phase" clause was relaxed. No structural rewrites; the story's goal, scope, and dependency on S1-01 are unchanged.

## Findings by critic

### Coverage critic findings — S1-02

#### F1 — AC-1 `line-length = 100` named in AC but not test-verified
- **Severity:** harden
- **What's wrong:** AC-1 mandates `line-length = 100` but Test 1 reads only `target-version` and `lint.select`. A lazy impl with `line-length = 80` passes every test; pre-commit hooks in S1-04 then reformat all S2/S3 code to the wrong width, locking in a divergence.
- **Proposed fix:** Add `assert ruff["line-length"] == 100` to Test 1.
- **Confidence:** high
- **Source:** mutation thought experiment + story-smell "Some/any without quantifier"

#### F2 — AC-1 `[tool.ruff.format] enabled` named in AC but not test-verified
- **Severity:** harden
- **What's wrong:** AC-1 ends with "`[tool.ruff.format]` enabled". Test 1 never reads `ruff["format"]`. Lazy impl: omit the `[tool.ruff.format]` table → `ruff format --check` falls back to defaults; AC-1 silently violated.
- **Proposed fix:** Assert `"format" in ruff` (the table is declared).
- **Confidence:** high
- **Source:** AC-to-test trace

#### F3 — AC-2 `warn_unreachable = true` named in AC but not test-verified
- **Severity:** harden
- **What's wrong:** AC-2 calls out `warn_unreachable = true`. mypy's `--strict` does *not* enable `warn_unreachable` by default (it is a strict-extra flag). Test 2 reads only `mypy["strict"]` and `mypy["python_version"]`. Lazy impl: omit `warn_unreachable` entirely → `mypy --strict src/` still exits 0 on the current tree (AC-7 still passes); AC-2's explicit clause is silently violated; dead-code-after-narrowing slips through in later phases.
- **Proposed fix:** Add `assert mypy["warn_unreachable"] is True`.
- **Confidence:** high
- **Source:** mutation thought experiment + mypy documentation cross-reference

#### F4 — AC-2 tests-override flag values not test-verified
- **Severity:** harden
- **What's wrong:** AC-2 says the override must "relax `disallow_untyped_defs` and `disallow_untyped_decorators`". Test 2 only asserts that some `tests`-shaped override block *exists* (and uses substring matching at that — `"tests" in str(o.get("module"))` would accept `module = "src/foo/contests.py"`). Lazy impl: declare a `[[tool.mypy.overrides]] module = "tests.*"` block with no flags → AC-2 silently violated; S1-04's pre-commit mypy hits `disallow_untyped_defs` errors on every fixture function.
- **Proposed fix:** Locate the tests-rooted override via exact pattern match; assert `disallow_untyped_defs is False` AND `disallow_untyped_decorators is False`.
- **Confidence:** high
- **Source:** mutation thought experiment + AC-2 text

#### F5 — AC-4 `[tool.coverage.run]` shape not test-verified
- **Severity:** harden
- **What's wrong:** AC-4 (as originally written) compounded `[tool.coverage.run]` + `[tool.coverage.report]`. Test 4 only reads `report.omit`. Lazy impl: omit `[tool.coverage.run]` entirely → pytest-cov falls back to derived behavior, `--cov-branch` becomes a no-op, the 75% branch floor (`phase-arch §Tradeoffs`) becomes unenforceable for every later phase.
- **Proposed fix:** Promote the run-table assertions into a new AC (AC-8) and add a dedicated Test 5 that asserts `run["branch"] is True` and `run["source"] == ["src/codegenie"]`.
- **Confidence:** high
- **Source:** mutation thought experiment + phase-arch §Tradeoffs

#### F6 — Goal clauses "ruff check / ruff format / mypy --strict exit 0" not bridged to behavioral tests
- **Severity:** harden
- **What's wrong:** Goal asserts four commands exit 0. ACs 5–7 promise it. But the TDD plan is *introspection only* — it reads `pyproject.toml` and never *runs* ruff or mypy. Lazy mutations not caught by introspection (e.g., a `[tool.ruff.lint.extend-ignore] = ["T201"]` block — Test 1 originally didn't read `extend-ignore`) would ship.
- **Proposed fix:** Add a behavioral subprocess test (AC-9 / Test 6) that runs `ruff check` against a `print('canary')` fixture under `src/codegenie/` and asserts non-zero exit + `"T201"` in the diagnostic output. (mypy's introspection-vs-behavioral gap is smaller — `mypy --strict src/` is implicitly run by the executor's CI; we don't add a redundant subprocess test for it.)
- **Confidence:** high
- **Source:** goal-to-test trace + mutation thought experiment

#### F7 — AC-5 "was committed at the red phase" is a process clause unverifiable from working tree
- **Severity:** nit
- **What's wrong:** "Was committed at the red phase" requires inspecting git history; the executor's Validator pass works against the working tree.
- **Proposed fix:** Drop the clause; restate as "exists and is green." The TDD plan's Red → Green → Refactor section already documents the workflow.
- **Confidence:** high
- **Source:** AC verifiability check

#### F8 — Negative-space AC: no test for "print() in src/ is rejected"
- **Severity:** harden
- **What's wrong:** The phase-arch-design.md §Harness engineering / Logging strategy commitment ("`print()` is banned in `src/` … enforced by lint") is the load-bearing reason `T20`/`T201` is in `select` at all. But no AC or test exercises the negative space — that a `print()` planted in `src/` would actually be rejected. This is exactly the goal-vs-AC gap that earlier S1-01 validation flagged (production ADR-0005 / fence test asymmetry pattern).
- **Proposed fix:** Add AC-9 plus the behavioral Test 6 described in F6.
- **Confidence:** high
- **Source:** story-smell "Negative-space gap"

### Test-Quality critic findings — S1-02

#### F1 — Test 1's `T20` selection check is structural, not behavioral
- **Severity:** harden
- **What's wrong:** Test 1 asserts `{"E","F","I","B","UP","T20"}.issubset(selected)`. Selecting the family `T20` includes `T201` (print) and `T203` (pprint). Mutation: add `extend-ignore = ["T201"]` to `[tool.ruff.lint]`. Test 1 passes because `T20` is still in `select`. The print ban is silently lifted.
- **Proposed fix:** Accept `T20` *or* `T201` in `select` (behavior-equivalent), and additionally assert neither token appears in `lint.ignore`, `lint.extend-ignore`, or any `per-file-ignores` pattern targeting `src/`. Tighten the rule code set to `PRINT_BAN_TOKENS = {"T20", "T201"}` constant.
- **Confidence:** high
- **Source:** mutation thought experiment + ruff config schema

#### F2 — Test 2's tests-override search is substring-fragile and doesn't verify flag values
- **Severity:** harden
- **What's wrong:** `[o for o in overrides if o["module"].startswith("tests") or "tests" in str(o.get("module", ""))]` will accept `module = "src/foo/contests.py"`. And the subsequent assertion is just `assert test_overrides` — the flag values are never read.
- **Proposed fix:** Iterate overrides; accept the override only if `module` (or any entry in a list-valued `module`) equals `"tests"`, equals `"tests.*"`, or starts with `"tests."`. Then assert both `disallow_untyped_defs is False` and `disallow_untyped_decorators is False`.
- **Confidence:** high
- **Source:** mutation thought experiment

#### F3 — Test 3 substring-matches on `addopts` string
- **Severity:** nit
- **What's wrong:** `"--cov=src/codegenie" in addopts` would be satisfied by a pathological `addopts = "--cov=src/codegenie-fake --cov=src/codegenie ..."`. The specific tokens chosen are stable enough that this isn't a realistic mutation surface.
- **Proposed fix:** Leave as-is; the substring check is acceptable.
- **Confidence:** medium
- **Source:** mutation thought experiment (low realism)

#### F4 — TDD plan is config-introspection only; no test invokes ruff or mypy
- **Severity:** harden
- **What's wrong:** Same root cause as Coverage F6. A test plan that only reads TOML cannot prove the configured tools enforce what their configuration says.
- **Proposed fix:** Add Test 6 (subprocess-driven). One behavioral test is sufficient — it bridges the gap and serves as the regression anchor for "unknown future ruff config keys that weaken T201".
- **Confidence:** high
- **Source:** mutation thought experiment + Rule 9 (Tests verify intent, not just behavior)

#### F5 — Test 4's `in omit` allows extra exemptions
- **Severity:** nit
- **What's wrong:** `assert "src/codegenie/cli.py" in omit` passes for `omit = ["src/codegenie/cli.py", "src/codegenie/probes/*"]`. The arch is explicit: only `cli.py`.
- **Proposed fix:** Tighten to exact-list equality: `assert omit == ["src/codegenie/cli.py"]`.
- **Confidence:** high
- **Source:** mutation thought experiment + phase-arch §Test pyramid

### Consistency critic findings — S1-02

#### F1 — Story selects ruff family `T20`; arch names rule `T201`
- **Severity:** nit
- **What's wrong:** `phase-arch-design.md §Harness engineering` names `T201` specifically. Story selects the family `T20`. Functionally equivalent (T20 ⊇ T201) but a documentation-precision drift.
- **Proposed fix:** Accept both — Test 1 now passes if either token is in `select`. Story AC-1 explicitly notes the equivalence.
- **Confidence:** high
- **Source:** doc-vs-doc cross-reference

#### F2 — Goal "pytest -q exits 0" vs Refactor §3 "coverage may fail" — mild tension
- **Severity:** nit
- **What's wrong:** Goal says the four commands exit 0 from a clean checkout. Refactor §3 says `pytest` may fail on coverage in Step 1 (carve-out via `--cov-fail-under=0` on the Step 1 CI invocation per `High-level-impl §Step 1 Done-criteria`). Not a contradiction — the carve-out is named in the implementer notes — but a reader could trip on it.
- **Proposed fix:** No edit. The implementer notes already document the carve-out; surfacing it again in the goal would dilute the goal's brevity.
- **Confidence:** medium
- **Source:** doc cross-reference

#### F3 — 75% branch coverage floor is collected but not gate-enforced from `addopts`
- **Severity:** nit (observational)
- **What's wrong:** `phase-arch §Tradeoffs` row "85/75 coverage floor" implies both line *and* branch enforcement. `pytest-cov`/`coverage.py` does not expose a separate `--cov-fail-under-branch=75` flag. The story wires `--cov-branch` (which *collects* branch coverage) and `--cov-fail-under=85` (which enforces *line* coverage). Branch enforcement is structurally limited by the tool surface.
- **Proposed fix:** No edit at story level. Surface in this report; the gap is a phase-arch / S4-04 concern (S4-04 owns the flip from "wired" to "merge gate" — that's the right place to decide whether to enforce branch separately via a coverage report step).
- **Confidence:** high
- **Source:** pytest-cov / coverage.py documentation

#### F4 — All other ACs trace cleanly
- **Severity:** —
- **What's wrong:** No orphan ACs; every AC traces to `High-level-impl §Step 1` line 25 or to the goal sentence; no contradiction with any ADR (ADR-0007 is named for snapshot-coverage exemption — not directly relevant to AC-4 but cited correctly for downstream coverage-exclusion discipline).

## Research briefs

None. No findings were tagged `NEEDS RESEARCH`. The patterns invoked (mutation thought experiments, subprocess-based behavioral assertions, exact-equality vs subset, structural vs behavioral test coupling) are catalog techniques already in `references/techniques.md` and `references/story-smells.md`. No external research was needed.

## Conflict resolutions

- **Coverage F1/F2/F3/F4/F5/F8 vs Test-Quality F1/F2/F4** — these are different lenses on the same underlying gap (introspection-only TDD plan). Merged into a single set of edits: Tests 1, 2, 4 rewritten; Tests 5, 6 added; ACs 1, 2, 4 strengthened; ACs 8, 9 added.
- **Consistency F1 (T20 vs T201) vs Test-Quality F1 (T20-family looseness)** — Consistency wants documentation precision; Test-Quality wants mutation resistance. Resolution: keep both expressions acceptable (`PRINT_BAN_TOKENS = {"T20", "T201"}` in the test, AC-1 wording explicitly notes either is valid) AND defense-in-depth the `ignore`/`extend-ignore`/`per-file-ignores` weakening surface.
- **Consistency F3 (branch-floor enforceability)** — surfaced but not edited at story level; it's a phase-level observation, not a story-level fix.

## Edits applied

### Edit 1 — AC-1 strengthened (Coverage F1, F2, F8 + Test-Quality F1 + Consistency F1)
- **Before:** "`pyproject.toml` contains `[tool.ruff]` with `target-version = "py311"`, `line-length = 100`, and `[tool.ruff.lint]` selecting at minimum `E`, `F`, `I` (imports), `B` (bugbear), `UP` (pyupgrade), `T20` (no-`print`); and `[tool.ruff.format]` enabled."
- **After:** Now explicitly accepts `T20` or `T201` and prohibits `[tool.ruff.lint].ignore`, `extend-ignore`, or `per-file-ignores` from stripping the print ban from `src/`. `[tool.ruff.format]` table existence is now a separately-verifiable clause.
- **Rationale:** Original wording named four properties (`target-version`, `line-length`, rule selection, format table); the original Test 1 verified only the first and a subset of the third.

### Edit 2 — AC-2 strengthened (Coverage F3, F4 + Test-Quality F2)
- **Before:** "`pyproject.toml` contains `[tool.mypy]` with `python_version = "3.11"`, `strict = true`, `warn_unreachable = true`, plus a `[[tool.mypy.overrides]]` block targeting `tests/*` that relaxes `disallow_untyped_defs` and `disallow_untyped_decorators`."
- **After:** Same intent; spells out that `warn_unreachable` is *not* enabled by `strict` and must be explicit; spells out that the override must match a `tests`-rooted pattern and must set both flags to `false` (a bare override is insufficient).
- **Rationale:** mypy `--strict` is not the same as "strict + all strict-extras"; the wording now matches behavior.

### Edit 3 — AC-4 tightened (Test-Quality F5)
- **Before:** "`pyproject.toml` contains `[tool.coverage.run]` with `branch = true` and `source = ["src/codegenie"]`; and `[tool.coverage.report]` with `omit = ["src/codegenie/cli.py"]` (the architectural exemption)."
- **After:** Split. AC-4 keeps the report-side clause and now asserts *exact* equality on `omit` (`["src/codegenie/cli.py"]` only). AC-8 (new) carries the run-side clause.
- **Rationale:** Original Test 4 used `in omit`, allowing extra exemptions to ship undetected.

### Edit 4 — AC-5 relaxed (Coverage F7)
- **Before:** "The TDD red test at `tests/unit/test_toolchain_config.py` exists, was committed at the red phase, and is green."
- **After:** "The TDD test file `tests/unit/test_toolchain_config.py` exists, and `pytest -q tests/unit/test_toolchain_config.py` exits 0."
- **Rationale:** "Was committed at the red phase" requires inspecting git history; the executor's Validator pass works against the working tree.

### Edit 5 — AC-8 added (Coverage F5)
- **New AC:** `[tool.coverage.run]` declares `branch = true` AND `source = ["src/codegenie"]`.
- **Rationale:** Without these, `--cov-branch` in `addopts` is a no-op; the 75% branch floor becomes unenforceable. This was implied by the original AC-4 but never tested.

### Edit 6 — AC-9 added (Coverage F6, F8 + Test-Quality F4)
- **New AC:** `ruff check` (with this story's config) on a `src/codegenie/` file containing `print('canary')` exits non-zero with a `T201` diagnostic.
- **Rationale:** The only behavioral test in the plan; bridges from "config shape is right" to "configured tool actually enforces the load-bearing invariant"; catches unknown-unknown weakenings that introspection tests can't enumerate.

### Edit 7 — TDD plan rewritten (all critic findings)
- **Before:** Four tests, all TOML-introspection.
- **After:** Six tests. Tests 1, 2, 4 strengthened (added `line-length`, `[tool.ruff.format]`, `T20`/`T201` weakening checks, `warn_unreachable`, tests-override flag values, exact-equality on `omit`). Test 5 added (`[tool.coverage.run]` shape). Test 6 added (behavioral subprocess test for `ruff check` against a canary `print()`).
- **Rationale:** Every finding from Coverage F1–F8 and Test-Quality F1–F5 is now covered by an executable assertion.

### Edit 8 — Red-phase narrative updated
- **Before:** "The test fails initially because no `[tool.ruff]` … blocks exist … Run it, confirm `KeyError`, commit as the red marker."
- **After:** "The six tests fail initially … Tests 1–5 fail with `KeyError`; Test 6 fails because … the canary file's `print('canary')` is not flagged."
- **Rationale:** Documents the expected red signal for the new test count and the new behavioral test.

### Edit 9 — Status line + Validation notes block
- Status: "Ready" → "Ready (validated 2026-05-12 — HARDENED)".
- Inserted `## Validation notes` block under the header with the changes summary and conflict resolutions.

## Verdict rationale

HARDENED. Zero `block` findings — the story's goal, scope, references, and AC traceability were sound. Seven `harden` findings clustered around two root causes: (1) the AC text named load-bearing properties (`line-length`, `[tool.ruff.format]`, `warn_unreachable`, tests-override flag values, `[tool.coverage.run]` shape) that the TDD plan didn't actually verify; (2) the TDD plan was config-introspection only, with no behavioral bridge to "the configured tool actually enforces what its config says." Both are fixable in place — strengthen the assertions; add one subprocess-driven behavioral test. Five `nit` findings were resolved with minor edits or surfaced-but-not-fixed (the branch-coverage `--cov-fail-under-branch` gap is a tool-surface limitation, not a story bug).

After the edits, an obviously wrong implementation — `omit = ["src/codegenie/cli.py", "src/codegenie/probes/*"]`, or `[tool.ruff.lint.extend-ignore] = ["T201"]`, or a bare `[[tool.mypy.overrides]]` block targeting tests with no flags, or omitting `warn_unreachable`, or omitting `[tool.coverage.run]` entirely — would now fail at least one TDD assertion. The story meets the "STRONG bar" for executor handoff.

## Recommended next step

Run `phase-story-executor` against the hardened story file. Executor's Validator pass should verify all six TDD tests are green, the toolchain commands (AC-6, AC-7) exit 0 on the current tree, and the behavioral canary test (Test 6 / AC-9) demonstrably reports a `T201` diagnostic.
