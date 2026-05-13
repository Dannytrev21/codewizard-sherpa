# Story S7-01 — Fence-CI seven structural assertions in `tests/unit/test_eval_fence.py`

**Step:** Step 7 — Extend fence-CI; lock in end-to-end audit; ship cross-phase amendments
**Status:** Ready
**Effort:** M
**Depends on:** S5-05 (vuln-remediation corpus must exist as the fence target), S6-02 (distroless corpus must exist; case.tomls + digests.yaml must be clean)
**ADRs honored:** ADR-0004 (`failure_modes.yaml` validity), ADR-0006 (held-out floor ≥5 at tier ≥ silver), ADR-0008 (`BreakdownKey` substring ban at AST value level)

## Context

Fence-CI is the *structural* defense against PRs that bypass the bench-directory contract. A contributor adding `@register_task_class("foo")` without `bench/foo/cases/digests.yaml` should fail at PR time with a path-specific diagnostic — not at nightly bench runs days later. The seven assertions are AST + filesystem walks; they share a ≤2-second combined wall-clock budget so they can run on every PR. Six come from the architecture (`phase-arch-design.md §"Fence-CI test"`); the seventh closes Gap #3 (case-id uniqueness, which the synthesis missed). Each assertion ships with a synthetic-failure adversarial test that proves the diagnostic fires correctly.

The seven assertions are also the *contract* Phase 7+ inherits — a contributor adding `bench/agentic-recipe-authoring/` in Phase 15 will hit exactly these seven gates. They must produce path-specific diagnostics, not generic "test failed" exits.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Fence-CI test (tests/unit/test_eval_fence.py)"` — names the six original assertions verbatim.
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

Land `tests/unit/test_eval_fence.py` with seven structural assertions, each producing a path-specific diagnostic, all running in ≤2 s combined wall-clock; add seven adversarial fixtures (one per assertion) that prove the diagnostic fires when the violation is present.

## Acceptance criteria

- [ ] `tests/unit/test_eval_fence.py` defines exactly seven test functions:
  1. `test_fence_1_directory_contract` — AST-walk `bench/*/registration.py`; for each `@register_task_class("<literal>")`, assert `bench/<literal>/{registration.py, rubric.py, breakdown_keys.py, failure_modes.yaml, cases/digests.yaml}` all exist; diagnostic names the missing path.
  2. `test_fence_2_minimum_case_count` — 10 for vuln-remediation; 3 for migration-chainguard-distroless; per task-class floor declared in `min_cases_for_promotion` (lowest tier) is the source of truth.
  3. `test_fence_3_held_out_floor` — for any task class whose `min_cases_for_promotion` declares any tier ≥ silver, count `case.curation_class == "held-out"` ≥ 5; diagnostic names task class and observed held-out count.
  4. `test_fence_4_literal_registration_name` — the first positional arg to every `@register_task_class(...)` call is `ast.Constant[str]` (not a variable, not an `f"..."`).
  5. `test_fence_5_breakdown_key_substring_ban` — walk every `bench/{name}/breakdown_keys.py` AST; collect `StrEnum` member values (must be `ast.Constant`); reject any value containing `confidence|llm|self_reported|model_says`.
  6. `test_fence_6_failure_mode_taxonomy_validity` — walk every `bench/{name}/failure_modes.yaml`; assert each entry has `severity ∈ {block, warn, info}` and `description` non-empty.
  7. `test_fence_7_case_id_uniqueness` (Gap #3) — parse every `case.toml`; assert `case_id` field set has no duplicates; assert each `case_id` matches its containing directory name.
- [ ] `time pytest tests/unit/test_eval_fence.py -q` reports combined wall-clock ≤ 2.0 s on a cold-cache CI runner; CI canary fails on regression.
- [ ] Each assertion's diagnostic names the offending path (e.g., `"bench/foo/cases/digests.yaml missing"`, `"case_id 'X' duplicated in bench/.../cases/{Y,Z}"`).
- [ ] Seven adversarial-failure tests live under `tests/adv/`, each provoking exactly one diagnostic on a synthetic fixture:
  - `test_fence_missing_digests_yaml.py` (assertion #1)
  - `test_fence_case_count_below_floor.py` (assertion #2)
  - `test_fence_silver_tier_without_holdouts.py` (assertion #3)
  - `test_fence_dynamic_registration_name.py` (assertion #4)
  - `test_breakdown_key_smuggling.py` (assertion #5; this name pre-exists per ADR-0008)
  - `test_fence_failure_mode_missing_severity.py` (assertion #6)
  - `test_fence_case_id_collision.py` (assertion #7)
- [ ] The red test from §TDD plan exists, was committed at red, and is now green.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict tests/unit/test_eval_fence.py` clean.

## Implementation outline

1. **Test scaffolding** — `test_eval_fence.py` discovers task classes via filesystem walk of `bench/*/registration.py`; each assertion is one `def test_fence_N_*` function.
2. **Assertion #1** — `ast.parse` each `bench/*/registration.py`; find `Call` nodes where `func.id == "register_task_class"`; extract `args[0].value` (must be `ast.Constant` — that's assertion #4). For each literal, `Path("bench") / literal` paths must exist.
3. **Assertion #2** — for each registered task class, load `min_cases_for_promotion` (parse the kwarg literal from `ast.Call`'s keywords). Lowest tier value is the floor. Count `Path("bench") / name / "cases"` directories; assert `count >= floor`.
4. **Assertion #3** — same `min_cases_for_promotion` parse; if any key ≥ silver (use `docs/trust-tiers.yaml` ordering — silver/gold/platinum), parse each `case.toml` for `curation_class`, count `held-out`s; assert `≥ 5`.
5. **Assertion #4** — during the AST walk in #1, assert `isinstance(args[0], ast.Constant)`. f-strings, name refs, formatted strings are all rejected.
6. **Assertion #5** — `ast.parse` each `bench/{name}/breakdown_keys.py`; find `StrEnum`-subclass `ClassDef`; walk member assignments; each `value` must be `ast.Constant` (substring of value walked).
7. **Assertion #6** — `yaml.safe_load` each `bench/{name}/failure_modes.yaml`; iterate entries; assert schema.
8. **Assertion #7** — walk every `case.toml`; `tomllib.loads`; collect `(case_id, path)` pairs; assert no duplicates; assert `case_id == path.parent.name`.
9. **Adversarial fixtures** — for each assertion, build a tiny `tests/fixtures/fence/<assertion>/` mirror-bench directory with the specific violation; the adversarial test imports the fence functions and runs them against the fixture directory (parameterize the BENCH_ROOT argument).
10. **Wall-clock canary** — wrap the test module in a `pytest-timeout` of 2 s or assert via `time.monotonic()` in a fixture; CI fails if any single fence-CI run exceeds.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/test_eval_fence.py`

```python
# tests/unit/test_eval_fence.py
# All seven assertions ship as separate test functions in this module.
# Red: the module doesn't exist; one assertion fixture also does not exist.
from pathlib import Path

import pytest

BENCH_ROOT = Path(__file__).resolve().parents[2] / "bench"


def test_fence_1_directory_contract():
    from codegenie.eval._fence import walk_registrations, required_paths_for
    for task_class_name in walk_registrations(BENCH_ROOT):
        for required in required_paths_for(BENCH_ROOT, task_class_name):
            assert required.exists(), f"task class '{task_class_name}' registered but {required} missing"


def test_fence_2_minimum_case_count():
    from codegenie.eval._fence import walk_registrations, case_count_floor_for
    for tc in walk_registrations(BENCH_ROOT):
        floor = case_count_floor_for(BENCH_ROOT, tc)
        case_dirs = [p for p in (BENCH_ROOT / tc / "cases").iterdir() if p.is_dir()]
        assert len(case_dirs) >= floor, (
            f"task class '{tc}' has {len(case_dirs)} cases; floor is {floor}"
        )


def test_fence_3_held_out_floor():
    from codegenie.eval._fence import walk_registrations, declares_tier_ge_silver, count_held_out
    for tc in walk_registrations(BENCH_ROOT):
        if declares_tier_ge_silver(BENCH_ROOT, tc):
            n = count_held_out(BENCH_ROOT, tc)
            assert n >= 5, f"task class '{tc}' declares silver but has {n} held-out cases (need >=5)"


def test_fence_4_literal_registration_name():
    from codegenie.eval._fence import walk_registration_arg_nodes
    import ast
    for tc_arg in walk_registration_arg_nodes(BENCH_ROOT):
        assert isinstance(tc_arg, ast.Constant) and isinstance(tc_arg.value, str), (
            "@register_task_class first arg must be a string literal, not dynamic"
        )


def test_fence_5_breakdown_key_substring_ban():
    from codegenie.eval._fence import walk_breakdown_key_values
    banned = ("confidence", "llm", "self_reported", "model_says")
    for tc, member_value in walk_breakdown_key_values(BENCH_ROOT):
        for sub in banned:
            assert sub not in member_value, (
                f"breakdown_keys.py in '{tc}' contains banned substring '{sub}' in value '{member_value}'"
            )


def test_fence_6_failure_mode_taxonomy_validity():
    from codegenie.eval._fence import walk_failure_modes
    for tc, code, entry in walk_failure_modes(BENCH_ROOT):
        assert entry.get("severity") in {"block", "warn", "info"}, (
            f"failure_modes.yaml in '{tc}': code '{code}' has invalid severity {entry.get('severity')!r}"
        )
        assert (entry.get("description") or "").strip() != "", (
            f"failure_modes.yaml in '{tc}': code '{code}' has empty description"
        )


def test_fence_7_case_id_uniqueness():
    from codegenie.eval._fence import walk_case_ids
    seen: dict[str, Path] = {}
    for tc, case_id, path in walk_case_ids(BENCH_ROOT):
        key = f"{tc}::{case_id}"
        if key in seen:
            pytest.fail(f"case_id '{case_id}' duplicated in {tc}: {seen[key]} and {path}")
        seen[key] = path
        assert case_id == path.parent.name, (
            f"case_id '{case_id}' in {path} does not match its containing directory '{path.parent.name}'"
        )


def test_fence_combined_wall_clock_under_two_seconds():
    import subprocess, time
    start = time.monotonic()
    subprocess.run(
        ["pytest", "-q", "tests/unit/test_eval_fence.py",
         "--deselect", "tests/unit/test_eval_fence.py::test_fence_combined_wall_clock_under_two_seconds"],
        check=True, capture_output=True,
    )
    elapsed = time.monotonic() - start
    assert elapsed <= 2.0, f"fence-CI wall-clock {elapsed:.2f}s exceeds 2.0s budget"
```

Run; confirm `ModuleNotFoundError: codegenie.eval._fence`. Commit as red marker.

### Green

Create `src/codegenie/eval/_fence.py` with the helpers each test imports (`walk_registrations`, `required_paths_for`, `case_count_floor_for`, `declares_tier_ge_silver`, `count_held_out`, `walk_registration_arg_nodes`, `walk_breakdown_key_values`, `walk_failure_modes`, `walk_case_ids`). Pure stdlib (`ast`, `tomllib`, `pathlib`) + `pyyaml`. Then write the seven adversarial-fixture pairs under `tests/adv/` and `tests/fixtures/fence/`.

### Refactor

- Combine repeated AST walks into one parse-per-file (cache `ast.parse` results across assertions sharing a file).
- The `_fence.py` helpers carry the diagnostic strings as `f"..."` format templates so the tests' assertion messages and the helpers stay aligned.
- Add a `pytest --fence-only` marker so dev loops can run all seven in one shot.
- Confirm `tests/unit/test_eval_fence.py` is the *only* place the seven assertions live — no duplication with `tests/unit/test_eval_models.py` or `test_breakdown_keys_static.py` (those are runtime defenses; this is the AST/filesystem-at-PR-time defense).

## Files to touch

| Path | Why |
|---|---|
| `tests/unit/test_eval_fence.py` | New — seven assertions as separate test functions |
| `src/codegenie/eval/_fence.py` | New — AST/YAML/TOML walker helpers (underscore-prefixed = internal) |
| `tests/adv/test_fence_missing_digests_yaml.py` | New — assertion #1 synthetic failure |
| `tests/adv/test_fence_case_count_below_floor.py` | New — assertion #2 |
| `tests/adv/test_fence_silver_tier_without_holdouts.py` | New — assertion #3 |
| `tests/adv/test_fence_dynamic_registration_name.py` | New — assertion #4 |
| `tests/adv/test_breakdown_key_smuggling.py` | New (or extend if S1-05 stubbed it) — assertion #5; ADR-0008 names this file |
| `tests/adv/test_fence_failure_mode_missing_severity.py` | New — assertion #6 |
| `tests/adv/test_fence_case_id_collision.py` | New — assertion #7 |
| `tests/fixtures/fence/<assertion>/...` | New — synthetic mini-bench dirs per adversarial test |

## Out of scope

- **Wiring fence-CI into the GitHub Actions workflow** — assumed in scope of the broader repo's CI config; if not, a one-line addition to `.github/workflows/ci.yml` is in scope but trivial.
- **Audit chain integration test** — S7-02.
- **Cross-phase ADR amendments + roadmap** — S7-03.
- **Adding more assertions** (e.g., naming conventions, `case_id` format regex) — Phase 7+ may extend; this story ships exactly seven.

## Notes for the implementer

- **The ≤2s budget is per-run, not per-assertion.** AST parsing is O(file-count); the entire `bench/` tree at this phase is ≤20 files. The budget is generous; if any single assertion exceeds ~300 ms, refactor.
- **Path-specific diagnostics are load-bearing.** "fence assertion #3 failed" is useless; `"task class 'foo' declares silver but has 3 held-out cases (need >=5)"` is what the contributor needs. Phrase every assertion's failure message to name *the task class*, *the path*, and *the threshold or expected value*.
- **Assertion #4's strictness matters** (ADR-0008 §Tradeoffs note). A dev who writes `@register_task_class(f"{prefix}-foo")` bypasses assertion #1's literal-name walk. Reject dynamic args at the AST level; fail loud.
- **Assertion #5 also requires `ast.Constant`** on StrEnum member values, not just on the registration name. ADR-0008 calls this out explicitly — `LLM_CONFIDENCE = some_global` would slip past a string-content check.
- **Tier ordering** for assertion #3 is canonical from `docs/trust-tiers.yaml` (S4-05), not hardcoded — read the YAML, find the index of each tier, treat any tier whose index ≥ silver's index as "tier ≥ silver". This keeps Phase 7+ free to add new tier slugs without editing fence-CI code.
- **The seventh assertion is new this phase** (Gap #3). It catches the curator-collision Scenario described in `phase-arch-design.md §"Edge cases #7"`. S6-02's `tests/unit/test_distroless_cases.py` is the same shape but runtime-defended-in-depth — that test running in unit suite alongside this fence test is correct (`Rule 9 Tests verify intent`).
- **The fence runs in `pytest` not in a separate runner.** It's a unit test by design — no CI flag toggles, no `--fence` mode. The reason it lives in `tests/unit/` is precisely because every PR runs all unit tests.
- **Adversarial fixtures live under `tests/fixtures/fence/<N>-<name>/`** and each is a self-contained mini-bench with exactly one violation. Keep them small (~5 files each); the synthetic-failure tests must run quickly too.
