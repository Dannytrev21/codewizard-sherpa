# Story S8-05 — G3 no-retry-loop in workflow body fence

**Step:** Step 8 — Durability test pass + adversarial sweep + CI gates
**Status:** Ready
**Effort:** S
**Depends on:** S8-01 (the durability test that proves framework-level retries work — this fence prevents the regression where application code regrows its own retry loop)
**ADRs honored:** P9-ADR-0004 (workflow determinism three layers — this fence joins the existing AST + import-linter + Replayer layers as the fourth, "no application-level retry constructs" layer), P9-ADR-0010 (activity granularity — `RetryPolicy` lives on the activity registration, not in the workflow body, which is exactly what this fence enforces). Closes roadmap exit criterion 3 ("All retries are framework-level — application code contains no retry loops").

## Context

Roadmap Phase 9 exit criterion 3 reads verbatim: **"All retries are framework-level — application code contains no retry loops."** Step 4's `retry_policies._POLICIES` `Final` table (S4-01) ships the framework-level policies; Step 5's workflows are designed retry-loop-free (S5-02 acceptance criterion); but **neither protects against the regression** where a future contributor adds `for _ in range(3): ... try: ... except: continue` to a workflow body because "the framework retries weren't enough for this edge case". That regression silently re-introduces the failure mode Phase 9 was designed to prevent (workflow body that's not deterministic + that doesn't surface failures cleanly to the `match`-on-`VulnLedger` escalation arm).

This story ships the **fence that catches the regression at PR time**, not at staging-deploy time:

1. An **`import-linter`** contract added to `pyproject.toml` rejecting imports of `tenacity`, `backoff`, `retrying`, and `urllib3.util.retry` from any module under `codegenie.durable.workflows.*` (the "retry-library" angle).
2. A **`forbidden-patterns` pre-commit regex** rejecting `while ... < max`/`for _ in range(N)`-near-`try:` patterns under `src/codegenie/durable/workflows/*.py` (the "DIY retry loop" angle).
3. A **structural AST test** `tests/fence/test_no_retry_loops.py` that walks `src/codegenie/durable/workflows/*.py`, finds every `For` / `While` node whose body contains a `Try` node, and asserts none of them carry an attempt-counter / max-retries-shaped variable (the "regex evades, AST catches" backup).
4. A **deliberate-violation xfail fixture** so the rule is exercised every CI run (parity with S1-07's discipline + the Phase 3 `_phase3_fence` pattern).

The architect named this as a CI gate explicitly: High-level-impl §Step 8 line 241 (the G3 phrasing) + §Exit-criteria mapping line 258 ("`import-linter` + `forbidden-patterns` regex over `src/codegenie/durable/workflows/*.py`; code-search assertion in CI rejecting `while ... attempt < max` / `for _ in range(retries)` constructs").

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals item 3` — G3 acceptance phrasing.
  - `../phase-arch-design.md §Testing strategy §CI gates` line 1033 — `make check` gates every PR; this story adds the no-retry-loop gate.
  - `../phase-arch-design.md §Error escalation` (line 940 area) — explains why retries belong on the activity, not the workflow body.
- **Phase ADRs:**
  - `../ADRs/0004-workflow-determinism-enforcement-three-layers.md` — the layered-defense pattern this fence joins.
  - `../ADRs/0010-activity-granularity-asymmetric.md` — `RetryPolicy` is per-activity, the source of truth.
- **Stories that feed this:**
  - `S1-07-workflow-determinism-fences.md` — same pattern (import-linter + AST + xfail fixture); reuse the testing scaffolding wherever it makes sense.
  - `S4-01-retry-policies-table.md` — the `_POLICIES` `Final` table is the legitimate home of retry config.
  - `S5-02-vuln-remediation-workflow.md` — already asserts "no retry loops in workflow body" (acceptance criterion); this story fences the assertion.
- **High-level-impl:** `../High-level-impl.md §Step 8 §Done criteria` line 241 (G3 phrasing); §Exit-criteria mapping line 258.
- **Existing precedent:** the `forbidden-patterns` pre-commit hook in `.pre-commit-config.yaml` (Phase 0/1 era — bans `subprocess.run(..., shell=True)`, `os.system`, `pickle.loads`).

## Goal

Ship a four-layer fence (`import-linter` + `forbidden-patterns` regex + AST walker + xfail fixture) that hard-rejects retry constructs under `src/codegenie/durable/workflows/*.py` at PR time, with the deliberate-violation fixture exercising all three live layers on every CI run.

## Acceptance criteria

**`import-linter` layer (AC-1)**

- [ ] **AC-1** `pyproject.toml [tool.importlinter]` extends with a new `forbidden` contract:
  - `name = "codegenie.durable.workflows must not import retry libraries"`.
  - `type = "forbidden"`.
  - `source_modules = ["codegenie.durable.workflows"]`.
  - `as_packages = true`.
  - `forbidden_modules = ["tenacity", "backoff", "retrying", "urllib3.util.retry"]`.
  - Verified by `tests/fence/test_no_retry_loops_importlinter_contract_shape.py` parsing `pyproject.toml` and asserting the contract is present with all four `forbidden_modules` (no drift).

**`forbidden-patterns` regex layer (AC-2)**

- [ ] **AC-2** `.pre-commit-config.yaml`'s `forbidden-patterns` hook gains four new regex rules, scoped via `files: ^src/codegenie/durable/workflows/.*\.py$`:
  - `r"\bwhile\b.*\bretry\b"` — catches `while retry < N:` and `while retry_count < max_retries:`.
  - `r"\bwhile\b.*\battempt\b.*<"` — catches `while attempt < max_attempts:`.
  - `r"\bfor\b\s+\w+\s+in\s+range\(.*retr"` — catches `for _ in range(retries):` / `for i in range(num_retries):`.
  - `r"\bfor\b\s+\w+\s+in\s+range\(.*attempt"` — catches `for attempt in range(max_attempts):`.
  - Each rule has a human-readable message naming ADR-0010 / the Step-4 `_POLICIES` table as the legitimate home of retry config. Verified by `tests/fence/test_forbidden_patterns_no_retry_loops.py` running the hook against a planted-violation fixture and asserting each rule fires on the appropriate planted shape.

**AST walker layer (AC-3 through AC-5)**

- [ ] **AC-3** `tests/fence/test_no_retry_loops.py` walks `src/codegenie/durable/workflows/*.py` and asserts no `For` / `While` AST node whose body contains a `Try` AST node carries an attempt-counter variable. Implementation: extract walker to `src/codegenie/durable/workflows/_no_retry_fence.py` (parity with the `_phase3_fence` pattern — same function called by live + xfail tests so a regression in the production walker kills both).
  - The walker function is `find_retry_loops(src: str, path: Path) -> list[Violation]` where `Violation` is `@dataclass(frozen=True)` with `file`, `line`, `kind: Literal["for-range-retries", "while-attempt-lt-max", "while-with-try-and-counter"]`, `snippet`.
  - Heuristic: a `For`/`While` node is a retry construct if (i) its body contains a `Try` node AND (ii) either the loop iterable contains a `range(` call with an argument whose source text contains `retry|attempt` (case-insensitive), OR the loop body assigns or compares a variable whose name contains `retry|attempt` near the `Try`. The exact heuristic ships in a parametrized shape-matrix test (AC-4).
- [ ] **AC-4** Parametrized shape matrix in `test_no_retry_loops.py`:
  | snippet | expected_hit |
  |---|---|
  | `for _ in range(3):\n    try: ...\n    except: continue` | True |
  | `for attempt in range(max_attempts):\n    try: ...\n    except: continue` | True |
  | `while attempt < max_attempts:\n    try: ...\n    except: attempt += 1` | True |
  | `while retry_count < N:\n    try: ...\n    except: retry_count += 1` | True |
  | `for item in items:\n    try: process(item)\n    except: pass` | False (not a retry loop — iterates over a collection) |
  | `while True:\n    msg = await receive_signal()\n    if msg.cancel: break` | False (signal-wait loop, not retry) |
  | `for _ in range(10):\n    items.append(i)` | False (no `Try`) |
  Each row exercises the same `find_retry_loops` function and is one independent mutation guard.
- [ ] **AC-5** Live scan of `src/codegenie/durable/workflows/*.py` returns `[]` at story-landing time (S5-02 / S5-03 / S5-04 already comply by design).

**Deliberate-violation xfail fixture (AC-6)**

- [ ] **AC-6** A fixture file `tests/fence/_fixtures/_no_retry_violations.py` contains a known-violating snippet `for _ in range(3):\n    try: ...\n    except: continue`; a test `test_walker_catches_known_violation` calls `find_retry_loops` on it and asserts `len(violations) == 1`. The fixture file is **not** under `src/` (so the live scan does not see it), but it is exercised on every CI run — red-by-construction whenever the walker regresses (parity with the `_phase3_fence`'s known-bypass catalog pattern).

**Integration with `make check` (AC-7 through AC-8)**

- [ ] **AC-7** The new `test_no_retry_loops.py` runs under `make check` (transitively via `make test` → `testpaths = ["tests"]`). The pre-commit `forbidden-patterns` hook runs at commit time AND under `make lint` (because pre-commit hooks are wired into `make lint` via the standard codebase pattern). The `import-linter` contract is exercised via `make lint-imports`. All three live layers are reachable from `make check` exit 0.
- [ ] **AC-8** A `make`-target meta-assertion: `tests/fence/test_no_retry_loops_integration.py` parses the `Makefile` and asserts the `check:` target's dependency chain includes `lint`, `lint-imports`, and `test` (the three gates this fence rides on). Verified once — drift detection for a future contributor who silently removes `lint-imports` from `make check`.

**Hygiene (AC-9 through AC-11)**

- [ ] **AC-9** `_attempts/S8-05.md` records a one-time **out-of-test planted-violation evidence block** (Rule 12 fail-loud): plant `for _ in range(3): try: ... except: continue` into a real workflow file on a throwaway branch; assert `make check` exits non-zero and the failure message names the file/line; remove; assert green. Three layers means three planted-violation runs (one per live layer), each green-after-removal SHA recorded.
- [ ] **AC-10** `ruff check`, `ruff format --check`, `mypy --strict` clean on touched files.
- [ ] **AC-11** Story Status → `Done` after AC-9 evidence lands.

## Implementation outline

1. Create `src/codegenie/durable/workflows/_no_retry_fence.py` (production walker):
   - `@dataclass(frozen=True) class Violation` per AC-3.
   - `def find_retry_loops(src: str, path: Path) -> list[Violation]`: parse + AST-walk, returning sorted violations.
   - `def scan_workflows_dir(root: Path = Path("src/codegenie/durable/workflows")) -> list[Violation]`: orchestrator that iterates `*.py` (excluding the fence file itself + `__init__.py`).
2. Extend `pyproject.toml [tool.importlinter]` with the AC-1 contract.
3. Extend `.pre-commit-config.yaml`'s `forbidden-patterns` hook with the four AC-2 regex rules (scoped via `files:`).
4. Add `tests/fence/test_no_retry_loops_importlinter_contract_shape.py` (AC-1 verifier).
5. Add `tests/fence/test_forbidden_patterns_no_retry_loops.py` — runs the pre-commit hook (`pre-commit run forbidden-patterns --files <planted>`) against a `tmp_path` planted fixture; asserts non-zero exit + message substring.
6. Add `tests/fence/_fixtures/_no_retry_violations.py` (AC-6).
7. Add `tests/fence/test_no_retry_loops.py` — shape matrix (AC-4) + live scan (AC-5) + known-violation fixture exercise (AC-6).
8. Add `tests/fence/test_no_retry_loops_integration.py` (AC-8).
9. Run `make check` end-to-end; record AC-9 three-layer planted-violation evidence in `_attempts/S8-05.md`.

## TDD plan — red / green / refactor

**Red:** Write `tests/fence/test_no_retry_loops.py` against the not-yet-existing `_no_retry_fence.find_retry_loops`. Import fails → red. Same for the importlinter-shape and forbidden-patterns hook tests — write them first, against contracts not yet added to `pyproject.toml` / `.pre-commit-config.yaml`.

**Green:** Implement the walker. The shape matrix (AC-4) drives the implementation row-by-row — the `False`-expected rows (the loop-over-items case, the signal-wait case, the no-`Try` case) are where the heuristic needs care; a too-aggressive walker false-positives on legitimate `while True: ... receive_signal()` loops and fails AC-4. Ship the importlinter contract + the forbidden-patterns rules; run `make check`; the three live layers green simultaneously.

**Refactor:** Lift the four forbidden-patterns regex strings into a `_RETRY_LOOP_REGEXES: Final[tuple[Pattern[str], ...]]` tuple inside `_no_retry_fence.py` so they're reachable from both the pre-commit hook config and the test (the test compiles them and runs them against the fixture as a backup to the actual hook invocation — defense in depth against a hook misconfiguration that silently disables the rules).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/workflows/_no_retry_fence.py` | NEW — production walker. Houses `Violation`, `find_retry_loops`, `scan_workflows_dir`, `_RETRY_LOOP_REGEXES`. |
| `pyproject.toml` | EDIT — extend `[tool.importlinter]` with the AC-1 contract. |
| `.pre-commit-config.yaml` | EDIT — extend `forbidden-patterns` with the four AC-2 regex rules scoped to `src/codegenie/durable/workflows/`. |
| `tests/fence/test_no_retry_loops_importlinter_contract_shape.py` | NEW — AC-1 verifier. |
| `tests/fence/test_forbidden_patterns_no_retry_loops.py` | NEW — AC-2 verifier (runs the hook against planted shapes). |
| `tests/fence/test_no_retry_loops.py` | NEW — shape matrix + live scan + known-violation fixture exercise (AC-3, AC-4, AC-5, AC-6). |
| `tests/fence/test_no_retry_loops_integration.py` | NEW — `make check` chain integrity (AC-8). |
| `tests/fence/_fixtures/_no_retry_violations.py` | NEW — known-violation snippets exercised on every CI run (AC-6). |

## Out of scope

- **Banning retry libraries everywhere else in the codebase** — `tenacity` may be perfectly fine inside activity code (not workflow code). The fence is scoped to `codegenie.durable.workflows.*`, not the whole tree.
- **Generic loop-with-try detection** — the heuristic intentionally requires `retry|attempt` naming hints. Catching every `for ... try: ... except:` would false-positive on legitimate per-item error-tolerant iteration. The architect's exit-criterion phrasing names "retry loops" specifically, not "all error-tolerant loops".
- **Banning recursive retry** (`def f(n=3): try: ... except: if n > 0: f(n-1)`) — out of scope; trace evidence shows recursive retry is not a pattern in this codebase. If a future contributor introduces it, a follow-up story extends the walker. Surface in `_attempts/S8-05.md` as a forward dependency.
- **Activity-side retry loops** — activities legitimately may retry on inner sub-operations (e.g., a flaky GitHub API call); the activity's own `RetryPolicy` is the canonical retry mechanism but local retry-on-sub-call is fine. Fence scope is workflow body only.
- **Pre-commit cassette tests** — pre-commit's own machinery has its own test patterns; AC-2's verifier exercises the rule against a tmp file, not the full pre-commit infrastructure.

## Notes for the implementer

- **Mirror Phase 0's `_fence.py` + Phase 3's `_phase3_fence.py` patterns.** Same function called by live and xfail/known-violation tests = mutation resistance. The Phase 3 story (S1-05 of phase 03) is the load-bearing precedent — reread it before starting.
- **The four regex rules and the AST walker are intentionally redundant.** Regex is cheap (runs at commit time, catches the 90% case before it's even pushed); AST is precise (runs at `make check`, catches the cases regex misses — e.g., a `for` loop whose `range(...)` argument is a variable name like `MAX_RETRIES` that the regex's literal-`retry`-near-`range` rule misses). Both layers green = strongest evidence. If you find them genuinely redundant in practice (i.e., the AST never catches anything the regex misses), surface in `_attempts/S8-05.md` as a Rule-2 simplification candidate for a future story — but ship both layers here.
- **The `while True:` exception is load-bearing.** Temporal workflow bodies legitimately use `while True: await workflow.wait_condition(...)` to await human-review signals (S5-02). The walker must not false-positive on this — AC-4's shape matrix includes the signal-wait case for that reason. Test the heuristic against `s5-02`'s actual code, not a synthetic snippet, before declaring green.
- **`as_packages = true` on the importlinter contract** matters — without it, only `codegenie.durable.workflows` (the package's `__init__.py`) is scanned. Submodules like `codegenie.durable.workflows.vuln_remediation` need the `as_packages = true` flag to be reached. Verified by AC-1's shape test.
- **The pre-commit hook scope (`files: ^src/codegenie/durable/workflows/.*\.py$`)** is what keeps this from being a whole-tree lint. Get the regex right; test it on a path inside the scope and a path outside the scope.
- **Rule 12 fail-loud applies to the planted-violation evidence.** Three layers means three blocks in `_attempts/S8-05.md`, each showing red-then-green with commit SHAs. A single "trust me, all three layers work" line is insufficient — that's the failure mode S1-05 of phase 03 was explicitly hardened against.
- **The `_no_retry_fence.py` file lives under `src/codegenie/durable/workflows/` — does it self-trip?** The walker excludes `__init__.py` and the fence file itself by name. Verify the exclusion via a unit test (`test_walker_excludes_itself`); this is the kind of self-reference bug that's easy to miss and embarrassing when caught at review.
- **The legitimate home of retry config is `src/codegenie/durable/activities/retry_policies.py` `_POLICIES`** (S4-01). The pre-commit failure message names this path so a contributor who hits the fence sees the migration path, not just a rejection.
