# Story S6-01 — `bench/migration-chainguard-distroless/` registration, taxonomies, and stub rubric

**Step:** Step 6 — Seed `bench/migration-chainguard-distroless/`
**Status:** Ready
**Effort:** M
**Depends on:** S5-05 (the worked vuln-remediation pattern to mirror)
**ADRs honored:** ADR-0001 (subprocess rubric), ADR-0004 (failure-mode taxonomy), ADR-0006 (curation-class — Phase 7 will own the silver eligibility surface), ADR-0008 (`BreakdownKey` StrEnum + substring ban)

## Context

Phase 7 introduces `migration-chainguard-distroless` as the second task class without editing any Phase 0–6 source — the *extension-by-addition* invariant in `CLAUDE.md`. For that to work, Phase 6.5 must ship a complete directory skeleton (`registration.py`, `breakdown_keys.py`, `failure_modes.yaml`, `rubric.py`) that fence-CI is already asserting against and that mirrors the `bench/vuln-remediation/` pattern landed in S5. The rubric is a *stub*: at N=3 we only need to demonstrate the subprocess contract and the Dockerfile-derived signals; Phase 7 will harden scoring as the corpus grows.

The registration declares **only** `bronze: 10` in `min_cases_for_promotion` — silver/gold are Phase 7's call. This deliberately keeps fence-CI assertion #3 (held-out floor ≥ 5 for tier ≥ silver) inactive for this task class until Phase 7 raises the bar.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"bench/{task-class}/ directory contract"` — the directory shape fence-CI asserts.
  - `../phase-arch-design.md §"What new task classes will need" §Step 1` (bench/migration-chainguard-distroless/ subsection).
  - `../phase-arch-design.md §"Component design → loader.py"` — how `_load_breakdown_keys` and `_load_failure_mode_taxonomy` consume these files.
  - `../phase-arch-design.md §"Scenarios → Scenario 3"` — fence-CI walking `bench/*/registration.py`.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — `if __name__ == "__main__"` entrypoint contract, JSON over stdin/stdout, no module-level side effects.
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — `failure_modes.yaml` schema (`severity ∈ {block, warn, info}`, non-empty `description`).
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md` — why we declare only `bronze` here.
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md` — `BreakdownKey` StrEnum value-level substring ban.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — facts not judgments; the Dockerfile-derived signals are the right shape.
- **Source design:** `../High-level-impl.md §"Step 6"`.
- **Existing precedent:** `bench/vuln-remediation/{registration.py, rubric.py, breakdown_keys.py, failure_modes.yaml}` from S5-01/S5-02.

## Goal

Land the four task-class artifact files (`registration.py`, `breakdown_keys.py`, `failure_modes.yaml`, `rubric.py`) plus `bench/migration-chainguard-distroless/tests/test_rubric_unit.py` so that `loader.load_task_class("migration-chainguard-distroless")` succeeds and fence-CI assertions #1, #4, #5, #6 pass even with zero cases.

## Acceptance criteria

- [ ] `bench/migration-chainguard-distroless/registration.py` contains exactly one `@register_task_class("migration-chainguard-distroless", bench_path=..., min_cases_for_promotion={"bronze": 10})` call; `silver`/`gold` are absent (Phase 7's surface).
- [ ] `bench/migration-chainguard-distroless/breakdown_keys.py` declares `class BreakdownKey(StrEnum)` whose members include at least `BASE_IMAGE_SWAPPED = "base_image_swapped"`, `SHELL_FREE = "shell_free"`, `BUILD_PASSES = "build_passes"`; every member value is an `ast.Constant` literal (ADR-0008 strictness).
- [ ] `bench/migration-chainguard-distroless/failure_modes.yaml` declares at least `migration.base_image_not_chainguard`, `migration.shell_invocation_present`, `migration.build_failed`, each with `severity ∈ {block, warn, info}` and a non-empty `description` (ADR-0004).
- [ ] `bench/migration-chainguard-distroless/rubric.py` exposes `if __name__ == "__main__":` reading a JSON `{"case": ..., "harness_output": ...}` payload from stdin and writing a `BenchScore` JSON to stdout in ≤ 60 s wall-clock; the module has **no module-level I/O or import side effects** (ADR-0001).
- [ ] `loader.load_task_class("migration-chainguard-distroless", bench_root=...)` returns a `TaskClass` whose `breakdown_keys` frozenset equals `{m.value for m in BreakdownKey}` and whose `failure_modes` map covers every YAML entry.
- [ ] No breakdown-key value contains `confidence|llm|self_reported|model_says`; `tests/unit/test_breakdown_keys_static.py` extended to walk this task class proves it (or the existing fence already does — verify which).
- [ ] The red test from §TDD plan exists, was committed at red, and is now green.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict` clean on touched files; `pytest bench/migration-chainguard-distroless/tests/` and the new unit test pass.

## Implementation outline

1. Mirror `bench/vuln-remediation/` skeleton; copy *structure* not *content*.
2. **registration.py** — one decorator call; literal task-class slug; `min_cases_for_promotion={"bronze": 10}` only; no other side effects at import time.
3. **breakdown_keys.py** — `StrEnum BreakdownKey` with the three required members above (Phase 7 may add e.g., `RUNTIME_CAPABILITY_MATCH` later). Values must pass the substring ban.
4. **failure_modes.yaml** — YAML mapping `code → {severity, description}` for the three required codes plus any rubric-internal ones the stub might emit (e.g., `migration.dockerfile_unparseable`).
5. **rubric.py** — subprocess entrypoint:
   - read stdin JSON,
   - parse `harness_output.dockerfile` (the SUT's produced Dockerfile string),
   - compute three boolean signals: (a) `FROM` line points at a `cgr.dev/chainguard/*` image (`BASE_IMAGE_SWAPPED`); (b) no `RUN sh|bash|/bin/sh` invocations in the produced Dockerfile (`SHELL_FREE`); (c) `expected/build.log` last line says `Successfully built` or equivalent if present (`BUILD_PASSES`),
   - emit `BenchScore(score=mean_of_three_booleans, breakdown={...}, failure_mode_code=None or "migration.base_image_not_chainguard" etc., cost_usd=0.0)` to stdout.
   - **Determinism** is on the bench-author's shoulders — pure string parsing, no clocks, no network.
6. **tests/test_rubric_unit.py** — in-process import + direct `score(case, harness_output)` calls covering: all-pass, swap-not-done, shell-present, build-failed; assert breakdown keys equal `BreakdownKey` enum values; assert `failure_mode_code` resolves against `failure_modes.yaml`.
7. Update `tests/unit/test_breakdown_keys_static.py` to assert the new task class's enum values also pass the substring ban (defense-in-depth — fence will catch it but unit test should be loud too).

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/test_distroless_registration.py`

```python
# tests/unit/test_distroless_registration.py
from pathlib import Path

import pytest

from codegenie.eval.loader import load_task_class

BENCH_ROOT = Path(__file__).resolve().parents[2] / "bench"


def test_distroless_task_class_registers_with_only_bronze_floor():
    tc = load_task_class("migration-chainguard-distroless", bench_root=BENCH_ROOT)
    assert tc.name == "migration-chainguard-distroless"
    assert tc.min_cases_for_promotion == {"bronze": 10}
    # Silver/gold absent — Phase 7's surface (ADR-0006 held-out floor inactive here).
    assert "silver" not in tc.min_cases_for_promotion
    assert "gold" not in tc.min_cases_for_promotion


def test_distroless_breakdown_keys_cover_required_signals():
    tc = load_task_class("migration-chainguard-distroless", bench_root=BENCH_ROOT)
    required = {"base_image_swapped", "shell_free", "build_passes"}
    assert required.issubset(tc.breakdown_keys)
    # ADR-0008 substring ban applies uniformly.
    for value in tc.breakdown_keys:
        for banned in ("confidence", "llm", "self_reported", "model_says"):
            assert banned not in value


def test_distroless_failure_modes_have_severities_and_descriptions():
    tc = load_task_class("migration-chainguard-distroless", bench_root=BENCH_ROOT)
    for code in ("migration.base_image_not_chainguard",
                 "migration.shell_invocation_present",
                 "migration.build_failed"):
        fm = tc.failure_modes[code]
        assert fm.severity in {"block", "warn", "info"}
        assert fm.description.strip() != ""


def test_distroless_rubric_is_subprocess_entrypoint_only():
    import importlib, sys
    # No module-level side effects — importing should not run scoring.
    mod = importlib.import_module("_codegenie_bench.migration_chainguard_distroless.rubric")
    # The module exposes a `__main__` guard, not a top-level `score()` invocation.
    assert hasattr(mod, "__name__")
```

Run; confirm `ModuleNotFoundError` or `TaskClassNotFound`. Commit as red marker.

### Green

Create the four artifact files + the bench-author test directory. Smallest shape: registration is one decorator call; breakdown_keys lists exactly the three members; YAML lists exactly the three codes; rubric is a `main()` reading stdin, parsing the Dockerfile string with regex, writing JSON to stdout.

### Refactor

- Add docstrings citing ADR-0001, ADR-0004, ADR-0008.
- Confirm `mypy --strict bench/migration-chainguard-distroless/` clean (rubric.py is a script; annotate `main() -> None`).
- Confirm the rubric's regex set is conservative (false-positive on shell detection is preferable to false-negative in a stub).
- `bench/migration-chainguard-distroless/README.md` placeholder — actual N=3 verdict-context text lands in S6-03.

## Files to touch

| Path | Why |
|---|---|
| `bench/migration-chainguard-distroless/registration.py` | New — `@register_task_class` literal-name call, bronze-only floor |
| `bench/migration-chainguard-distroless/breakdown_keys.py` | New — `BreakdownKey` StrEnum with three required values |
| `bench/migration-chainguard-distroless/failure_modes.yaml` | New — three required codes with severity + description |
| `bench/migration-chainguard-distroless/rubric.py` | New — subprocess entrypoint scoring Dockerfile-derived signals |
| `bench/migration-chainguard-distroless/tests/test_rubric_unit.py` | New — bench-author unit tests, in-process |
| `bench/migration-chainguard-distroless/__init__.py` | New — package marker for loader import (Option A `sys.path` prep) |
| `bench/migration-chainguard-distroless/cases/__init__.py` | New — package marker (empty; cases land in S6-02) |
| `tests/unit/test_distroless_registration.py` | New — pins registration + taxonomies contract |

## Out of scope

- **Seed cases** (`cases/001-*`, `cases/002-*`, `cases/003-*`, `cases/digests.yaml`) — S6-02 owns case curation and signing.
- **E2E `codegenie eval run`** + N=3 verdict documentation — S6-03.
- **Hardening the rubric** (multi-stage detection, build sandboxing, semver checks on Chainguard image tags) — Phase 7.
- **Adding `silver`/`gold` to `min_cases_for_promotion`** — Phase 7 raises the bar once ≥10 cases with ≥5 held-out exist.

## Notes for the implementer

- **Stub-quality is correct.** The signals are coarse (regex on `FROM` line, regex on `RUN sh|bash`). That is the Phase 6.5 commitment; Phase 7 expands. Resist gold-plating — `Rule 2 Simplicity First` and `Rule 3 Surgical Changes`.
- **The `if __name__ == "__main__"` discipline is load-bearing.** The runner spawns `python rubric.py` as a subprocess (ADR-0001); any module-level import of e.g., `docker` would either fail at subprocess startup or slow every case by hundreds of ms. Keep imports minimal — stdlib only is ideal.
- **Breakdown-key values are the substring-ban surface, not member names** (ADR-0008). `BASE_IMAGE_SWAPPED = "base_image_swapped"` — the `value` is what fence-CI walks.
- **`bench_path` in `@register_task_class`** must be the `Path(__file__).parent` of `registration.py` so the loader can locate sibling files. Mirror exactly how `bench/vuln-remediation/registration.py` does it (S5-01).
- **The runtime test_breakdown_keys_static.py** auto-discovers registered task classes — if you wired registration correctly, the existing static test picks this task class up without edit. Verify before adding a new test; do not duplicate.
- **`migration-chainguard-distroless` slug uses hyphens** in `@register_task_class("...")` but the Python package directory must use underscores (`migration_chainguard_distroless/`) for Option A `sys.path`-prep imports. Loader handles the slug→module-name translation; mirror vuln-remediation's pattern.
