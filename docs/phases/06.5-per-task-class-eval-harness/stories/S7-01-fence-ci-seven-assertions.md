# Story S7-01 — Fence-CI seven structural assertion tests in `tests/fence/test_eval_fence.py`

**Step:** Step 7 — Extend fence-CI; lock in end-to-end audit; ship cross-phase amendments
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-05 HARDENED (`src/codegenie/eval/_smuggling.SMUGGLING_SUBSTRINGS` + `tests/fence/` convention), S4-05 HARDENED (`docs/trust-tiers.yaml` schema — the source-of-truth for tier ordering), S5-05 (vuln-remediation corpus must exist as the fence target), S6-02 (distroless corpus must exist; `case.toml`s + `digests.yaml` must be clean)
**ADRs honored:** ADR-0001 (rubric subprocess isolation — via reserved `bench.<slug>.` module-namespace convention preserved by fence), ADR-0004 (`failure_modes.yaml` validity), ADR-0006 (held-out floor ≥5 at tier ≥ silver, with tier ordering read from `docs/trust-tiers.yaml`), ADR-0008 (`BreakdownKey` substring ban at AST value level; single source-of-truth `SMUGGLING_SUBSTRINGS`)

## Validation notes (2026-07-26 — phase-story-validator, scheduled `story-validation-corrector` task)

Verdict: **HARDENED**. Original draft was well-structured but carried four block-grade inconsistencies with prior HARDENED stories in this phase, plus nine hardening gaps that would let a wrong implementation pass all tests. Executive summary of the changes applied in this pass:

- **F-CON-1 [BLOCK — fence-test location].** Moved file from `tests/unit/test_eval_fence.py` to `tests/fence/test_eval_fence.py` per HARDENED S1-05 F-DP-8 (all eval-subsystem fence tests live in `tests/fence/`; the pyproject-fence in `tests/unit/` is a pre-existing exception, not the convention). Rippled through Files-to-touch, TDD plan, wall-clock canary, and Notes.
- **F-CON-2 [BLOCK — smuggling substrings not from single source].** Assertion #5's `banned = ("confidence", "llm", ...)` literal duplicates the four-string set S1-05 AC-6 canonicalised at `codegenie.eval._smuggling.SMUGGLING_SUBSTRINGS`. S1-05 AC-7 *names S7-01 explicitly* as a consumer that must import — the literal set must NOT appear inline. Rewrote assertion #5 to `from codegenie.eval._smuggling import SMUGGLING_SUBSTRINGS`.
- **F-CON-3 [BLOCK — missing alias-dodge assertion #4b].** `final-design.md §Fence-CI test extension` requires *two* Stage-1 checks: (a) first positional arg is a string literal (current assertion #4), and (b) the decorator symbol is the literal identifier `register_task_class`, not an alias (`from codegenie.eval import register_task_class as rtc; @rtc("foo")`). Original story covered only (a). Added assertion #4 sub-check (b) so the fence assertion count becomes **eight** (four remains a single test function that runs both checks against the same `ast.Call`; alternatively split — this pass keeps them fused per Rule 3 surgical-changes). Also renamed AC-1 header from "exactly seven test functions" to "exactly seven test functions (assertion #4 fuses two AST-level rejections)" to keep the count stable while accurately describing coverage. See "Notes for the implementer" below for the split-vs-fuse decision rubric.
- **F-CON-4 [BLOCK — wall-clock canary fragility].** Original canary shelled out to `subprocess.run(["pytest", ...])` recursively — this is expensive (~1–2s of pytest cold-start alone, blowing the 2s budget under measurement), flaky under CI matrix (`pytest` binary path differences), and violates the invariant that a fence test must be cheap enough to run every PR. Replaced with a per-assertion `time.monotonic()` fixture + a final `test_fence_combined_wall_clock_under_two_seconds` that reads the accumulated sum from a session-scoped fixture. No subprocess; no recursion.
- **F-COV-1..F-COV-6 [HARDEN — edge cases missing ACs].** Added ACs for: empty `bench/` tree (fence must not crash); malformed AST in a `bench/*/registration.py` (diagnostic must name the file, not raise raw `SyntaxError`); non-literal `min_cases_for_promotion` kwarg value (must be rejected — otherwise assertions #2/#3 silently pass on `min_cases_for_promotion=SOME_CONSTANT`); `case.toml`-filter on `iterdir()` for assertion #2 (skip `__pycache__` / dotdirs — otherwise floor is over-counted); assertion #7 `case_id == path.parent.name` semantics pinned to exact-string equality (not substring); assertion #5's `StrEnum` collection must handle both the class-declaration form (`class BreakdownKey(StrEnum): ...`) and the functional form (`BreakdownKey = StrEnum("BreakdownKey", ...)`) — the latter is rejected with a diagnostic.
- **F-TQ-1..F-TQ-3 [HARDEN — mutation-thinness in tests].** Adversarial tests originally required only that "the diagnostic fires"; a mutation that emits `assert False` with no message would pass. Every adversarial test now asserts *both* `pytest.raises(AssertionError)` AND that `str(exc.value)` contains the expected path/task-class substring (the load-bearing "Path-specific diagnostics" AC). Added a positive-control mirror: every adversarial fixture directory is paired with a `_control/` sibling that passes the same assertion, so the test proves it fires *only* on the violation.
- **F-DP-1 [HARDEN — diagnostic sum-type].** `_fence.py` helpers surface violations as a frozen `FenceViolation(assertion_id: int, task_class: str, path: Path, message: str)` dataclass instead of raising bare `AssertionError`s with f-string messages. Each test function then asserts `violations == ()`; failure diagnostics stringify the dataclass tuple. This makes violations *checkable* (adversarial tests assert on `.path` / `.task_class` fields, not on regex-of-message), keeps message templates in one place, and makes the fence's output structurally consumable by future tooling (e.g., a CI comment bot).
- **F-DP-2 [HARDEN — newtype identifiers].** `_fence.py` helpers accept and return `TaskClassName = NewType("TaskClassName", str)` and `CaseId = NewType("CaseId", str)` (import from `codegenie.types.identifiers` if a slot exists there; otherwise declare locally as `Final`). Prevents accidentally swapping a task-class name for a case-id in call signatures — a real defect for helpers that take three `str` args.
- **F-DP-3 [NOTE — extension seam for 8th+ assertion].** Recorded in Notes-for-implementer that adding a ninth assertion crosses the rule-of-three from the current fused-#4 pair. When Phase 7+ adds a naming-convention or `case_id`-format regex assertion, extract a `FenceAssertion` registry (kernel: iterate `_ASSERTIONS: Final[tuple[FenceAssertion, ...]]`; add-by-registration in a new module). Not applied now (three assertion families in this story is exactly the rule-of-three threshold; a fourth would force it).

Full findings, before/after snippets, and mutation-resistance analysis: [`_validation/S7-01-fence-ci-seven-assertions.md`](_validation/S7-01-fence-ci-seven-assertions.md).

## Context

Fence-CI is the *structural* defense against PRs that bypass the bench-directory contract. A contributor adding `@register_task_class("foo")` without `bench/foo/cases/digests.yaml` should fail at PR time with a path-specific diagnostic — not at nightly bench runs days later. The seven assertions are AST + filesystem walks; they share a ≤2-second combined wall-clock budget so they can run on every PR. Six come from the architecture (`phase-arch-design.md §"Fence-CI test"`); the seventh closes Gap #3 (case-id uniqueness, which the synthesis missed). Each assertion ships with a synthetic-failure adversarial test that proves the diagnostic fires correctly.

The seven assertions are also the *contract* Phase 7+ inherits — a contributor adding `bench/agentic-recipe-authoring/` in Phase 15 will hit exactly these seven gates. They must produce path-specific diagnostics, not generic "test failed" exits.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Fence-CI test (tests/unit/test_eval_fence.py)"` — names the six original assertions verbatim. **NB:** the arch doc's path (`tests/unit/`) predates HARDENED S1-05 F-DP-8, which relocated eval-subsystem fence tests to `tests/fence/`. This story lands at `tests/fence/` per the S1-05 convention; an arch-doc amendment is out of scope for this story (see [`_validation/S7-01-fence-ci-seven-assertions.md`](_validation/S7-01-fence-ci-seven-assertions.md) F-CON-1).
  - `../phase-arch-design.md §"Gap analysis Gap 3"` — case-id uniqueness as the seventh assertion.
  - `../phase-arch-design.md §"Scenarios → Scenario 3"` — the AST-walk diagnostic shape.
  - `../phase-arch-design.md §"Edge cases #7, #8, #9, #12"` — each fence assertion's failure surface.
  - `../phase-arch-design.md §"Performance and observability — Fence-CI overhead canary"` — ≤2s budget canary.
- **Phase ADRs:**
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — taxonomy YAML schema (assertion #6).
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md` — held-out floor (assertion #3).
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md` — substring ban at member-value level (assertion #5); StrEnum values must be `ast.Constant` literals.
- **Source design:** `../High-level-impl.md §"Step 7" §"Features delivered"` — enumerates all seven.
- **Existing precedent:** Phase 5 fence patterns; Phase 0 import-linter contract.

## Goal

Land `tests/fence/test_eval_fence.py` with seven structural assertion tests (assertion #4 fuses two AST-level rejections into one test — literal-arg AND literal-decorator-symbol per HARDENED F-CON-3), each producing a path-specific diagnostic surfaced as a frozen `FenceViolation` dataclass, all running in ≤2 s combined wall-clock (measured via a session-scoped `pytest_runtest_call` hook — NO recursive subprocess); add adversarial fixtures with paired `violation/` + `_control/` mini-benches (per HARDENED F-TQ-2) that prove each diagnostic fires *only* on its violation.

## Acceptance criteria

- [ ] **AC-1** `tests/fence/test_eval_fence.py` (NOT `tests/unit/` — HARDENED S1-05 F-DP-8 convention) defines exactly seven test functions (assertion #4 fuses two AST-level rejections into one test — literal-arg AND literal-decorator-symbol; see Notes-for-implementer for the split-vs-fuse rationale):
  1. `test_fence_1_directory_contract` — AST-walk `bench/*/registration.py`; for each `@register_task_class("<literal>")`, assert `bench/<literal>/{registration.py, rubric.py, breakdown_keys.py, failure_modes.yaml, cases/digests.yaml}` all exist; each violation surfaces as a `FenceViolation(assertion_id=1, task_class=<name>, path=<missing>, message="task class '<name>' registered but <path> missing")`.
  2. `test_fence_2_minimum_case_count` — 10 for vuln-remediation; 3 for migration-chainguard-distroless; per task-class floor is the lowest-tier value from the decorator's `min_cases_for_promotion` kwarg. Iteration counts *only* directories that contain a `case.toml` (skip `__pycache__`, dotdirs, stray directories) — see AC-6 for the filter contract.
  3. `test_fence_3_held_out_floor` — for any task class whose `min_cases_for_promotion` declares any tier ≥ silver (**silver-index resolved by reading `docs/trust-tiers.yaml`, not by hardcoded tier-name comparison** — see AC-7), count `case.curation_class == "held-out"` ≥ 5; diagnostic names task class and observed held-out count.
  4. `test_fence_4_literal_registration_argname_and_decorator_symbol` — **fused check** per `final-design.md §Fence-CI test extension`: (a) the first positional arg to every `@register_task_class(...)` call is `ast.Constant[str]` (not a variable, not an `f"..."`, not a `Name`, not a `BinOp`); AND (b) the decorator's *symbol* is the literal identifier `register_task_class` in the source — an aliased import (`from codegenie.eval import register_task_class as rtc; @rtc("foo")`) is rejected with a diagnostic naming the file + line + the aliased identifier. Rationale: without (b), a contributor who aliases the import bypasses the AST literal-name walk of assertion #1 (the walker looks for the *string* `"register_task_class"`).
  5. `test_fence_5_breakdown_key_substring_ban` — walk every `bench/{name}/breakdown_keys.py` AST; collect the values of every `StrEnum`-subclass member (values MUST be `ast.Constant[str]`; a member whose value is a `Name`, `BinOp`, `f"..."`, or a `Call` — e.g., the functional `BreakdownKey = StrEnum("BreakdownKey", ...)` construction — is rejected with a diagnostic); reject any value containing any substring from `SMUGGLING_SUBSTRINGS`. **The test MUST `from codegenie.eval._smuggling import SMUGGLING_SUBSTRINGS`** and use it as the ONLY source-of-truth — the literal four-string set (`confidence`, `llm`, `self_reported`, `model_says`) MUST NOT appear inline in this test file (per HARDENED S1-05 AC-7, which names S7-01 as a consumer). A `grep -E '"confidence"|"llm"|"self_reported"|"model_says"' tests/fence/test_eval_fence.py` MUST return empty.
  6. `test_fence_6_failure_mode_taxonomy_validity` — walk every `bench/{name}/failure_modes.yaml` (via `yaml.safe_load` only — monkeypatched-`yaml.load` guard as a defense-in-depth); assert the top-level is a `dict` (empty file / non-dict → diagnostic); each entry has exactly `{severity, description}` keys (extras rejected); `severity ∈ {block, warn, info}`; `description` non-empty after `.strip()`.
  7. `test_fence_7_case_id_uniqueness` (Gap #3) — parse every `case.toml` via `tomllib`; assert `(task_class, case_id)` pairs are globally unique across the tree (collisions surface as `FenceViolation(assertion_id=7, ..., path=<second>, message="case_id 'X' duplicated in <task_class>: <first_path> and <second_path>")`); assert `case_id == path.parent.name` by exact string equality (no substring, no case-fold — the directory name IS the case id).
- [ ] **AC-2 (diagnostic surface).** `_fence.py` helpers surface violations as `@dataclass(frozen=True, slots=True) FenceViolation(assertion_id: int, task_class: str, path: Path, message: str)` (declared in `_fence.py`). Every test function collects violations into a tuple and asserts `violations == ()`; the failure message stringifies the tuple. This lets adversarial tests introspect `violations[0].path` / `.task_class` fields instead of regex-matching the human message.
- [ ] **AC-3 (diagnostic content).** Each assertion's `FenceViolation.message` names the offending path AND the task class (e.g., `"task class 'foo' declares silver in min_cases_for_promotion but has 3 held-out cases (need >=5)"`; `"case_id 'X' duplicated in vuln-remediation: bench/vuln-remediation/cases/Y/case.toml and bench/vuln-remediation/cases/Z/case.toml"`). A parametrised meta-test asserts, for each assertion, that a synthetic violation's stringified message contains BOTH the task-class name AND the path — mutation-resists an implementer who logs `"assertion #3 failed"` with no context.
- [ ] **AC-4 (wall-clock budget).** A session-scoped conftest fixture in `tests/fence/conftest.py` records per-test durations for every `test_fence_*` function in `test_eval_fence.py` via a `pytest_runtest_teardown` hook; a final `test_fence_combined_wall_clock_under_two_seconds` (last test in module) asserts the accumulated sum ≤ 2.0 s on a cold-cache runner. **No recursive `subprocess.run(["pytest", ...])`** — the previous draft's canary blew the budget with its own pytest cold-start and was CI-matrix-fragile. Failure diagnostic names the slowest three assertions and their individual wall-clock.
- [ ] **AC-5 (empty bench edge case).** With an empty `bench/` tree (no `bench/*/registration.py`), every assertion returns `violations == ()` without raising — the fence must not crash on a fresh repo checkout that hasn't landed a task class yet. Verified by `test_fence_empty_bench_returns_no_violations` (in `test_eval_fence.py`, one extra test — the "exactly seven" count in AC-1 is over the seven assertion tests only; the meta/wall-clock/empty tests are supporting and not counted).
- [ ] **AC-6 (case-dir filter).** Assertion #2's iteration and assertion #7's `case.toml` walk use the shared helper `iter_case_dirs(bench_root, tc) -> Iterable[Path]` which yields exactly the child dirs of `bench/{tc}/cases/` that (a) do not start with `.` or `_` (skips `__pycache__`, `.pytest_cache`, dotdirs), AND (b) contain a `case.toml` file. Unit-tested in `tests/fence/test_eval_fence_helpers.py`.
- [ ] **AC-7 (tier ordering from YAML).** Assertion #3's "tier ≥ silver" comparison is computed from `docs/trust-tiers.yaml` (S4-05 owned): the helper reads the YAML's ordered tier list, finds `silver`'s index, and treats any tier whose index ≥ silver's index as "tier ≥ silver". No hardcoded tier-name comparison anywhere in `_fence.py` (`grep -w 'silver\|gold\|platinum' src/codegenie/eval/_fence.py` MUST return empty). If `docs/trust-tiers.yaml` doesn't list `silver`, the fence emits a `FenceViolation(assertion_id=3, ..., message="docs/trust-tiers.yaml is missing the 'silver' tier — fence-CI cannot compute the held-out floor")` and every silver-eligible task class is treated as needing held-out ≥5 (fail-loud on config drift).
- [ ] **AC-8 (malformed AST / non-literal kwargs).** If any `bench/*/registration.py` fails to parse (`ast.parse` raises `SyntaxError`), fence assertions #1, #2, #3, #4 emit a `FenceViolation(..., message="bench/{name}/registration.py failed to parse: {err}")` — the fence does NOT raise `SyntaxError` upward; it names the file. Similarly, if the `min_cases_for_promotion` kwarg value is not an inline `ast.Dict` with `ast.Constant[str]` keys and `ast.Constant[int]` values (e.g., `min_cases_for_promotion=MIN_CASES` where `MIN_CASES` is a name reference), fence #4b rejects with a diagnostic — otherwise assertions #2/#3 silently pass on unresolvable kwargs.
- [ ] **AC-9 (adversarial fixtures with control siblings).** Seven adversarial-failure tests live under `tests/adv/`, each provoking exactly one diagnostic on a synthetic fixture directory AND asserting that the same `_fence.py` helpers return `violations == ()` on a paired `_control/` fixture (same tree minus the violation). Each adversarial test asserts BOTH (a) that the violation-fixture returns at least one `FenceViolation` for the expected assertion_id, AND (b) that `violations[0].message` contains the expected task-class name AND path (mutation-resistant to an implementer whose message is `"assertion #N failed"`):
  - `test_fence_missing_digests_yaml.py` (assertion #1)
  - `test_fence_case_count_below_floor.py` (assertion #2)
  - `test_fence_silver_tier_without_holdouts.py` (assertion #3)
  - `test_fence_dynamic_registration_name.py` (assertion #4a — non-literal arg)
  - `test_fence_aliased_decorator_symbol.py` (assertion #4b — `register_task_class as rtc`) — **new per F-CON-3**
  - `test_breakdown_key_smuggling.py` (assertion #5; this name pre-exists per ADR-0008)
  - `test_fence_failure_mode_missing_severity.py` (assertion #6)
  - `test_fence_case_id_collision.py` (assertion #7)
- [ ] **AC-10 (helper newtypes).** `_fence.py` helper signatures use `TaskClassName = NewType("TaskClassName", str)` and `CaseId = NewType("CaseId", str)` for parameters/returns that carry those domain identifiers (declared locally as `Final NewType` if `codegenie.types.identifiers` has no matching slot; add to the identifiers module if the story executor finds a natural fit). Prevents callers from swapping a case-id for a task-class name in three-`str` signatures.
- [ ] **AC-11 (red test).** The red test from §TDD plan exists at `tests/fence/test_eval_fence.py`, was committed at red with `ModuleNotFoundError: codegenie.eval._fence`, and is now green.
- [ ] **AC-12 (lint clean).** `ruff format --check`, `ruff check`, `mypy --strict tests/fence/test_eval_fence.py tests/fence/test_eval_fence_helpers.py src/codegenie/eval/_fence.py` all clean; `mypy` on the `NewType`s catches a swap in the helper signatures.

## Implementation outline

1. **Test scaffolding** — `tests/fence/test_eval_fence.py` discovers task classes via filesystem walk of `bench/*/registration.py`; each assertion is one `def test_fence_N_*` function that collects a tuple of `FenceViolation`s from its helper and asserts the tuple is empty.
2. **`_fence.py` module structure** — pure helpers (deterministic, no logging, no I/O outside filesystem reads passed a `bench_root: Path` argument). Public helper surface: `walk_registrations`, `required_paths_for`, `case_count_floor_for`, `declares_tier_ge_silver`, `count_held_out`, `walk_registration_arg_nodes`, `walk_registration_decorator_symbols`, `walk_breakdown_key_values`, `walk_failure_modes`, `walk_case_ids`, `iter_case_dirs`, `read_trust_tier_index`. Each returns a tuple / generator of `FenceViolation`s (or the raw data that a caller pairs with a violation constructor). Signatures use `TaskClassName` / `CaseId` NewTypes.
3. **Assertion #1** — `ast.parse` each `bench/*/registration.py`; `SyntaxError` becomes a `FenceViolation(assertion_id=1, ..., message="bench/{tc}/registration.py failed to parse: {err}")` per AC-8. For each `ast.Call` whose decorator symbol is the literal identifier `register_task_class` (`func.id == "register_task_class"` OR `func.attr == "register_task_class"` on an Attribute), extract `args[0]`; if `ast.Constant[str]`, resolve required paths.
4. **Assertion #2** — for each registered task class, parse `min_cases_for_promotion` from the `ast.Call`'s `keywords`; kwarg value MUST be `ast.Dict` with `Constant[str]` keys and `Constant[int]` values (per AC-8). Lowest kwarg value is the floor. Count `iter_case_dirs(bench_root, tc)` (per AC-6 filter); assert `count >= floor`.
5. **Assertion #3** — reuse the parsed `min_cases_for_promotion` from #2. Compute silver-tier index via `read_trust_tier_index(docs/trust-tiers.yaml)` (per AC-7). If any of the kwarg's tier-string keys has index ≥ silver-index, walk `iter_case_dirs(bench_root, tc)`, `tomllib`-parse each `case.toml`, count `curation_class == "held-out"`, require ≥ 5.
6. **Assertion #4 (fused)** — during the AST walk in #1, per AC-1 sub-point 4:
   - (a) assert `isinstance(args[0], ast.Constant) and isinstance(args[0].value, str)` — reject f-strings (`JoinedStr`), name refs (`Name`), BinOps, Calls.
   - (b) assert the decorator's symbol identifier IS literally `register_task_class`. Enforcement: at the top of each `bench/*/registration.py`, walk `ImportFrom` nodes; if `register_task_class` is imported with an `alias.asname != None`, emit `FenceViolation(assertion_id=4, ..., message="bench/{tc}/registration.py imports register_task_class as an alias '{asname}'; the fence requires the literal symbol")`. Similarly reject `import codegenie.eval as ev; @ev.register_task_class(...)` unless the attribute-name is preserved (defer chained-alias detection to CODEOWNERS review; document as acknowledged residual).
7. **Assertion #5** — `ast.parse` each `bench/{name}/breakdown_keys.py`; find `ClassDef` whose bases include `StrEnum`; walk member `Assign` nodes; each `value` MUST be `ast.Constant[str]` (per AC-1 sub-point 5 — the functional form `StrEnum("BreakdownKey", ...)` is rejected because it's an `Assign` whose `value` is a `Call`, not a `ClassDef`). Import `SMUGGLING_SUBSTRINGS` from `codegenie.eval._smuggling` (per AC-1 sub-point 5 — literal set MUST NOT appear inline).
8. **Assertion #6** — `yaml.safe_load` each `bench/{name}/failure_modes.yaml` (monkeypatched-`yaml.load`-raises guard mirrors HARDENED S5-01 F-COV-3); the top-level MUST be a `dict[str, dict]`; each entry MUST have exactly `{severity, description}` keys (no extras); `severity ∈ {"block", "warn", "info"}`; `description` non-empty after `.strip()`.
9. **Assertion #7** — walk every `iter_case_dirs(bench_root, tc)`; `tomllib.loads` each `case.toml`; collect `(tc, case_id, path)` tuples; assert `(tc, case_id)` pairs unique across the tree; assert `case_id == path.parent.name` (exact string equality — no substring, no case-fold).
10. **Adversarial fixtures** — for each assertion, build `tests/fixtures/fence/<N>-<name>/` with two subdirectories: `violation/` (mini-bench with the specific violation) and `_control/` (same tree without the violation). Each adversarial test imports the `_fence.py` helpers and asserts (per AC-9): violation-fixture yields ≥ 1 `FenceViolation` of the expected `assertion_id` AND with `.message` containing the expected task-class + path substrings; control-fixture yields `()`.
11. **Wall-clock instrumentation** — `tests/fence/conftest.py` hooks `pytest_runtest_teardown` to accumulate `test_fence_*` durations into a session-scoped `dict` on `request.session`. The final `test_fence_combined_wall_clock_under_two_seconds` reads the dict, sums, asserts ≤ 2.0 s. On failure the diagnostic lists the three slowest tests + their individual wall-clock. NO recursive `subprocess.run(["pytest", ...])`.

## TDD plan — red / green / refactor

### Red

Test file paths: `tests/fence/test_eval_fence.py` (main assertions), `tests/fence/test_eval_fence_helpers.py` (helper unit tests), `tests/fence/conftest.py` (wall-clock instrumentation).

```python
# tests/fence/test_eval_fence.py
# All seven assertions ship as separate test functions in this module. Assertion #4
# fuses two AST-level rejections (literal-arg + literal-decorator-symbol) into one
# test — see Notes-for-implementer for the fuse-vs-split rationale.
# Red: the module doesn't exist; the SMUGGLING_SUBSTRINGS import may fail if S1-05
# hasn't landed (it has: HARDENED). One adversarial-test fixture also does not exist.
from pathlib import Path

import pytest

BENCH_ROOT = Path(__file__).resolve().parents[2] / "bench"


def _assert_no_violations(violations, assertion_id: int) -> None:
    """Uniform failure-shape helper. All FenceViolations must stringify to
    (assertion_id, task_class, path, message) — so the raised AssertionError
    is greppable in CI logs."""
    if violations:
        pytest.fail(
            f"fence assertion #{assertion_id} raised {len(violations)} violation(s):\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


def test_fence_1_directory_contract():
    from codegenie.eval._fence import find_directory_contract_violations
    _assert_no_violations(find_directory_contract_violations(BENCH_ROOT), 1)


def test_fence_2_minimum_case_count():
    from codegenie.eval._fence import find_case_count_violations
    _assert_no_violations(find_case_count_violations(BENCH_ROOT), 2)


def test_fence_3_held_out_floor():
    from codegenie.eval._fence import find_held_out_floor_violations
    _assert_no_violations(find_held_out_floor_violations(BENCH_ROOT), 3)


def test_fence_4_literal_registration_argname_and_decorator_symbol():
    # Fused: rejects both (a) non-literal first arg AND (b) aliased decorator symbol.
    from codegenie.eval._fence import find_literal_registration_violations
    _assert_no_violations(find_literal_registration_violations(BENCH_ROOT), 4)


def test_fence_5_breakdown_key_substring_ban():
    # NB per AC-1 sub-point 5: SMUGGLING_SUBSTRINGS MUST import from the canonical
    # source; the literal four-string set MUST NOT appear inline in this file.
    from codegenie.eval._fence import find_breakdown_key_substring_violations
    _assert_no_violations(find_breakdown_key_substring_violations(BENCH_ROOT), 5)


def test_fence_6_failure_mode_taxonomy_validity():
    from codegenie.eval._fence import find_failure_mode_taxonomy_violations
    _assert_no_violations(find_failure_mode_taxonomy_violations(BENCH_ROOT), 6)


def test_fence_7_case_id_uniqueness():
    from codegenie.eval._fence import find_case_id_uniqueness_violations
    _assert_no_violations(find_case_id_uniqueness_violations(BENCH_ROOT), 7)


# ── supporting (not counted in "exactly seven assertion tests" per AC-1) ──


def test_fence_empty_bench_returns_no_violations(tmp_path):
    """AC-5: fresh checkout without any bench/ registration must not crash."""
    from codegenie.eval._fence import (
        find_directory_contract_violations,
        find_case_count_violations,
        find_held_out_floor_violations,
        find_literal_registration_violations,
        find_breakdown_key_substring_violations,
        find_failure_mode_taxonomy_violations,
        find_case_id_uniqueness_violations,
    )
    empty_bench = tmp_path / "bench"
    empty_bench.mkdir()
    for finder in (
        find_directory_contract_violations,
        find_case_count_violations,
        find_held_out_floor_violations,
        find_literal_registration_violations,
        find_breakdown_key_substring_violations,
        find_failure_mode_taxonomy_violations,
        find_case_id_uniqueness_violations,
    ):
        assert finder(empty_bench) == ()


def test_fence_combined_wall_clock_under_two_seconds(request):
    """AC-4: session-scoped fixture records per-test durations; this test runs last
    (module-order-dependent — enforced by naming) and reads the accumulated sum from
    the session store populated by pytest_runtest_teardown in tests/fence/conftest.py.
    NO subprocess.run(pytest ...) — recursion is fragile under CI matrix and its
    own cold-start blows the budget."""
    durations = request.session.stash.get("fence_eval_durations", {})
    total = sum(durations.values())
    if total > 2.0:
        slowest = sorted(durations.items(), key=lambda kv: -kv[1])[:3]
        slow_report = ", ".join(f"{k}={v:.3f}s" for k, v in slowest)
        pytest.fail(
            f"fence-CI combined wall-clock {total:.2f}s exceeds 2.0s budget; "
            f"three slowest: {slow_report}"
        )
```

```python
# tests/fence/conftest.py — session-scoped per-test-duration accumulator for AC-4.
# Only tracks tests in test_eval_fence.py::test_fence_* — skips the wall-clock
# canary itself so the canary doesn't count its own runtime.
import time
import pytest


_FENCE_STASH_KEY = "fence_eval_durations"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if item.location[0].endswith("test_eval_fence.py") and item.name.startswith("test_fence_") \
            and item.name != "test_fence_combined_wall_clock_under_two_seconds" \
            and item.name != "test_fence_empty_bench_returns_no_violations":
        start = time.monotonic()
        yield
        elapsed = time.monotonic() - start
        durations = item.session.stash.setdefault(_FENCE_STASH_KEY, {})
        durations[item.name] = elapsed
    else:
        yield
```

Run `pytest tests/fence/test_eval_fence.py -q`; confirm `ModuleNotFoundError: codegenie.eval._fence`. Commit as red marker.

### Green

Create `src/codegenie/eval/_fence.py` with the `FenceViolation` frozen dataclass, the seven `find_*_violations(bench_root: Path) -> tuple[FenceViolation, ...]` finder functions, and the shared helpers listed in Implementation-outline §2. Pure stdlib (`ast`, `tomllib`, `pathlib`, `dataclasses`, `typing.NewType`) + `pyyaml`. Import `SMUGGLING_SUBSTRINGS` from `codegenie.eval._smuggling`. Then write the seven adversarial-fixture pairs under `tests/adv/` and `tests/fixtures/fence/<N>-<name>/{violation,_control}/` per AC-9. Also write `tests/fence/test_eval_fence_helpers.py` covering `iter_case_dirs` (AC-6) and `read_trust_tier_index` (AC-7) as independent unit tests.

### Refactor

- Parse each source file ONCE per fence run via an `@functools.cache`-decorated `_parse_registration(path: Path) -> ast.AST | SyntaxError`. Assertions #1, #2, #3, #4 all traverse the cached AST.
- Diagnostic-string templates live in `_fence.py` module constants (`_DIAG_MISSING_PATH = "task class '{tc}' registered but {path} missing"`). Tests import them where content-matching matters (mutation-resistance without regex).
- Confirm `tests/fence/test_eval_fence.py` is the *only* place the seven assertions live — no duplication with `tests/fence/test_bench_score_static.py` or `test_breakdown_keys_static.py` (those are the runtime static defenses S1-05 / S3-04 own; this is the AST/filesystem-at-PR-time defense).
- Confirm the smuggling-substring literal-set grep on the test file returns empty per AC-1 sub-point 5.
- Confirm the hardcoded-tier-name grep on `_fence.py` returns empty per AC-7.

## Files to touch

| Path | Why |
|---|---|
| `tests/fence/test_eval_fence.py` | New — seven assertion tests + one empty-bench edge-case test + one wall-clock canary (AC-1, AC-4, AC-5). **Not** `tests/unit/` — HARDENED S1-05 F-DP-8 convention |
| `tests/fence/test_eval_fence_helpers.py` | New — unit tests for `iter_case_dirs` (AC-6), `read_trust_tier_index` (AC-7), and the `_parse_registration` cache (refactor) |
| `tests/fence/conftest.py` | New (or extend if S1-05 stubbed it) — `pytest_runtest_call` hookwrapper accumulating per-assertion wall-clocks into `session.stash` (AC-4) |
| `src/codegenie/eval/_fence.py` | New — `FenceViolation` frozen dataclass + `TaskClassName` / `CaseId` NewTypes + the seven `find_*_violations` finders + `SMUGGLING_SUBSTRINGS` import (underscore-prefixed = internal to `codegenie.eval`) |
| `tests/adv/test_fence_missing_digests_yaml.py` | New — assertion #1 synthetic failure + `_control` mirror per AC-9 |
| `tests/adv/test_fence_case_count_below_floor.py` | New — assertion #2 + `_control` |
| `tests/adv/test_fence_silver_tier_without_holdouts.py` | New — assertion #3 + `_control` |
| `tests/adv/test_fence_dynamic_registration_name.py` | New — assertion #4a (non-literal arg) + `_control` |
| `tests/adv/test_fence_aliased_decorator_symbol.py` | New (F-CON-3 add) — assertion #4b (`register_task_class as rtc`) + `_control` |
| `tests/adv/test_breakdown_key_smuggling.py` | New (or extend if S1-05 stubbed it) — assertion #5; ADR-0008 names this file; MUST import `SMUGGLING_SUBSTRINGS` per AC-1 sub-point 5 |
| `tests/adv/test_fence_failure_mode_missing_severity.py` | New — assertion #6 + `_control` |
| `tests/adv/test_fence_case_id_collision.py` | New — assertion #7 + `_control` |
| `tests/fixtures/fence/<N>-<name>/{violation,_control}/...` | New — paired synthetic mini-bench dirs per adversarial test (violation and control sibling per AC-9) |

## Out of scope

- **Wiring fence-CI into the GitHub Actions workflow** — assumed in scope of the broader repo's CI config; if not, a one-line addition to `.github/workflows/ci.yml` is in scope but trivial.
- **Audit chain integration test** — S7-02.
- **Cross-phase ADR amendments + roadmap** — S7-03.
- **Adding more assertions** (e.g., naming conventions, `case_id` format regex) — Phase 7+ may extend; this story ships exactly seven.

## Notes for the implementer

- **The ≤2s budget is per-run, not per-assertion.** AST parsing is O(file-count); the entire `bench/` tree at this phase is ≤20 files. The budget is generous; if any single assertion exceeds ~300 ms, refactor. The wall-clock canary now records per-assertion time in a session stash (AC-4), so a regression names the slowest three assertions in the diagnostic — no more subprocess-recursion.
- **Path-specific diagnostics are load-bearing** and now structurally enforced via `FenceViolation` (AC-2). "fence assertion #3 failed" is useless; the `FenceViolation.message` template mandates task-class + path + threshold naming, and AC-3's meta-test rejects any assertion whose stringified message doesn't include both the task-class name AND the path.
- **Assertion #4's strictness matters** (ADR-0008 §Tradeoffs note). It's a *fused* check — (a) the arg is a string literal AND (b) the decorator symbol is the literal identifier `register_task_class`. Without (b), a contributor who writes `from codegenie.eval import register_task_class as rtc\n@rtc("foo")` bypasses assertion #1's literal-name walk (which greps for the `"register_task_class"` string). The fuse keeps the assertion-test count at seven; the split would be a matter of taste (see extension-seam note below). Reject dynamic args AND aliased symbols at the AST level; fail loud.
- **Assertion #5 also requires `ast.Constant`** on StrEnum member values, not just on the registration name. ADR-0008 calls this out explicitly — `LLM_CONFIDENCE = some_global` would slip past a string-content check. The functional-form `BreakdownKey = StrEnum("BreakdownKey", ...)` is likewise rejected because it's an `Assign` whose value is a `Call`, not a `ClassDef` — the AC-1 sub-point 5 test walks `ClassDef` nodes only.
- **`SMUGGLING_SUBSTRINGS` is the single source-of-truth** (S1-05 HARDENED AC-6). Assertion #5 MUST `from codegenie.eval._smuggling import SMUGGLING_SUBSTRINGS`; the literal four-string set MUST NOT appear inline in `tests/fence/test_eval_fence.py` (AC-1 sub-point 5). S1-05 AC-7 named S7-01 as a future consumer; this story is that consumer.
- **Tier ordering** for assertion #3 is canonical from `docs/trust-tiers.yaml` (S4-05 HARDENED), not hardcoded (AC-7). No `silver | gold | platinum` string literals in `_fence.py`. This keeps Phase 7+ free to add new tier slugs (`titanium`, `hardened`, whatever) without editing fence-CI code — the tier-ordering slot in `docs/trust-tiers.yaml` is the extension point. If the YAML doesn't list `silver`, the fence fails loud with a diagnostic — not silently.
- **Case-directory filter (AC-6)** is `iter_case_dirs(bench_root, tc)`. Skip any dir whose name starts with `.` or `_` (drops `__pycache__`, `.pytest_cache`, `_control` fixture dirs by construction — the last is important because `tests/fixtures/fence/*/_control/` shares the mini-bench shape and could otherwise be miscounted by assertions #2 and #7 when the adversarial-test suite runs). Skip any dir without a `case.toml`. Unit-tested in `tests/fence/test_eval_fence_helpers.py`.
- **The seventh assertion is new this phase** (Gap #3). It catches the curator-collision Scenario described in `phase-arch-design.md §"Edge cases #7"`. S6-02's runtime `test_distroless_cases.py` is the defense-in-depth counterpart at load-time; this fence is the AST/filesystem-at-PR-time defense. Both coexist by design (`Rule 9 Tests verify intent`).
- **The fence runs in `pytest`, not in a separate runner.** No CI flag toggles, no `--fence` mode. The fence lives at `tests/fence/` (S1-05 HARDENED F-DP-8 convention — all eval-subsystem fence tests) and is picked up by the default `pytest -q` sweep in `make test`. The pyproject fence in `tests/unit/test_pyproject_fence.py` is a pre-existing location; new fences follow the S1-05 convention.
- **Adversarial fixtures live under `tests/fixtures/fence/<N>-<name>/{violation,_control}/`** and each pair is a self-contained mini-bench: `violation/` contains exactly one violation; `_control/` is the same tree with the violation removed. Each adversarial test asserts BOTH (a) violation-fixture yields the expected `FenceViolation`, AND (b) control-fixture yields `()` — the second is what proves the assertion fires *only* on the violation, mutation-resisting a check that always fires. Keep each pair small (~5 files each); the synthetic-failure tests must run quickly too.
- **`FenceViolation` sum-type discipline (AC-2 / F-DP-1).** Every fence helper returns a tuple of `FenceViolation`s — never raises `AssertionError` directly. The uniform shape (`assertion_id`, `task_class`, `path`, `message`) is what makes AC-3's meta-test and AC-9's adversarial-content assertions possible. It also makes the fence output structurally consumable by a future CI comment-bot (out of scope this phase — recorded as a design note).
- **Extension seam (F-DP-3 — deferred, not applied).** The current design carries seven finder functions in `_fence.py`; the tests iterate them explicitly. Rule of Three: this is the third fence-family in the repo (the pyproject fence, the eval-package-imports fence, and this eval-directory-contract fence), but each fence-family has its own module and its own set of finders — no repeated-registry pressure yet. **When Phase 7+ adds an eighth or ninth assertion** to this file (naming-convention, `case_id`-format regex, `min_cases_for_promotion` tier-completeness — all called out in Out-of-scope), extract a `FenceAssertion` registry: `@register_fence_assertion(id=N, name="…") def find_X_violations(...) -> tuple[FenceViolation, ...]`; the fence test module then iterates the registry. Kernel: `src/codegenie/eval/_fence_registry.py`. Extension by addition (per CLAUDE.md §"Extension by addition"). Do NOT extract now — three finders is exactly the rule-of-three threshold; four forces it.
- **Alias-dodge residuals (F-CON-3 acknowledged).** The (b) part of assertion #4 catches `from codegenie.eval import register_task_class as rtc` at the import-level of the `bench/*/registration.py` file. It does NOT catch:
  - `getattr(codegenie.eval, "register_task_class")("foo")` — dynamic attribute access; CODEOWNERS compensating control on `bench/**` review.
  - `_x = codegenie.eval.register_task_class; @_x("foo")` — indirection via a local name; not detected at PR time; CODEOWNERS.
  - Both are documented as acknowledged residuals in the same posture as [ADR-0008 §Tradeoffs](../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md) row 3 for dynamic StrEnum-value computation. The linter closes the obvious case; humans review the exotic case.
- **Newtype identifiers (AC-10 / F-DP-2).** `TaskClassName` and `CaseId` NewTypes prevent parameter-swap defects in three-`str` signatures like `_diagnose(tc: str, case_id: str, path: str)`. Declare locally as `TaskClassName = NewType("TaskClassName", str)` in `_fence.py` unless `codegenie.types.identifiers` has a natural slot; if it does, prefer that (project convention).
