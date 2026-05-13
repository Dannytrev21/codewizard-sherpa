# Story S5-02 — vuln-remediation rubric (subprocess entrypoint) + bench-author unit tests

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** Ready
**Effort:** M
**Depends on:** S5-01 (task-class registration + taxonomies must exist; rubric emits codes constrained by both)
**ADRs honored:** ADR-0001 (subprocess entrypoint; `if __name__ == "__main__"` JSON-in/JSON-out; ≤ 60 s budget), ADR-0004 (every emitted `failure_mode_code` is constrained by the taxonomy; unknown codes will produce `rubric.unknown_failure_mode`), ADR-0008 (every emitted `BenchScore.breakdown` key must be a `BreakdownKey` value)

## Context

The rubric is **control-plane code**: it produces `BenchScore`, which feeds the promotion gate, which determines whether a task class graduates. ADR-0001 makes the rubric a **subprocess entrypoint** specifically because it lives under `bench/**`, a CODEOWNERS-gated path that any contributor may PR — the runner therefore never imports it. The bench-author writes the rubric to a precise contract: read a JSON envelope (containing the `BenchCase` shape + the SUT's `harness_output`) from `stdin`; emit a `BenchScore` JSON to `stdout`; terminate in ≤ 60 s; produce no other side effects.

The trusted boundary distinction is load-bearing: `bench/vuln-remediation/tests/test_rubric_unit.py` may import the rubric module directly (in-process) and test its `score(...)` function with hand-built fixtures. The harness runner *never* imports it. This split is what makes the rubric simultaneously (a) testable with normal pytest ergonomics during bench-author development and (b) safe to invoke across a process boundary in production runs.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/rubric.py` — the `Rubric` Protocol (`score(case, harness_output) -> BenchScore`); the bench-author's `score(...)` function must satisfy it for in-process unit tests, even though the runner crosses a subprocess boundary.
  - `../phase-arch-design.md §Control flow` — the subprocess invocation shape (`subprocess.run(rubric.py, env=SCRUBBED, stdin=JSON, timeout)`).
  - `../phase-arch-design.md §Edge cases #3, #4, #5` — non-zero exit, timeout, malformed JSON: all become `FailureMode(severity="block")` at the runner; the rubric does not need to handle them, but **must not** swallow internal exceptions and emit a misleadingly-passing score.
  - `../phase-arch-design.md §Harness engineering → Tracing strategy` — the rubric is allowed to emit `structlog` JSON on stderr; stdout is reserved for the `BenchScore` envelope.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md §Decision, §Consequences` — `if __name__ == "__main__":` entrypoint is the bench-author's load-bearing surface; bench-author tests verify both `score(...)` (in-process) and the subprocess CLI (`python rubric.py < stdin > stdout`).
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md §Consequences` — the rubric emits `failure_mode_code: str`; the runner resolves it against the taxonomy. Unknown codes become `rubric.unknown_failure_mode` (block-severity) — fail loud on drift.
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md §Consequences` — `BenchScore.breakdown` dict keys must be `BreakdownKey` *values*; mismatched keys produce `rubric.unknown_breakdown_key` at runtime.
- **Source design:** `../High-level-impl.md §Step 5` — the rubric scores recipe-applied + validator-passed + cve-dropped signals; specific scoring formula is rubric-author judgment.

## Goal

Implement `bench/vuln-remediation/rubric.py` as a deterministic subprocess entrypoint that reads a JSON envelope from `stdin`, emits a `BenchScore` JSON to `stdout` in ≤ 60 s per case, and is covered by in-process bench-author unit tests in `bench/vuln-remediation/tests/test_rubric_unit.py`.

## Acceptance criteria

- [ ] `bench/vuln-remediation/rubric.py` defines a callable `score(case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore` that returns a frozen `BenchScore` whose `breakdown` keys are exactly drawn from `BreakdownKey` values and whose `failure_modes[*].code` values are exactly drawn from the codes declared in `failure_modes.yaml`.
- [ ] `bench/vuln-remediation/rubric.py` has an `if __name__ == "__main__":` block that: reads `sys.stdin.buffer.read()`, parses it as JSON, validates it into a typed envelope (`BenchCase` + `harness_output`), calls `score(...)`, writes the resulting `BenchScore` as JSON to `sys.stdout.buffer`, and exits 0 on success / non-zero on internal error.
- [ ] Running `python bench/vuln-remediation/rubric.py < envelope.json` in an empty `cwd` with `SCRUBBED_ENV` (no `ANTHROPIC_API_KEY`, no `HOME`, no `AWS_*`) completes within 60 wall-clock seconds for a representative envelope; the integration test `tests/integration/test_rubric_subprocess_vuln.py` enforces this.
- [ ] `bench/vuln-remediation/tests/test_rubric_unit.py` exists and contains at least 5 unit tests covering: (a) a fully-passing case (`passed=True`, `score >= 0.95`); (b) a recipe-applied-but-tests-failed case (emits `validator.tests_failed`, `passed=False`, severity propagates); (c) a CVE-not-dropped case (`validator.cve_not_dropped`); (d) a `breakdown` key set is a subset of `BreakdownKey` values; (e) a deterministic re-invocation of `score(...)` on the same inputs produces an identical `BenchScore` (byte-for-byte JSON).
- [ ] Bench-author unit tests **import the module directly** (`from bench.vuln_remediation.rubric import score`); the integration test exercising the subprocess CLI (`subprocess.run([...])`) lives separately under `tests/integration/`.
- [ ] The rubric does **not** import any LLM SDK (`anthropic`, `openai`, `langchain`, `langgraph`, `transformers`) — its scoring is mechanical against `harness_output`. `tests/unit/test_eval_package_imports_no_llm_sdk.py` extends to walk `bench/**/rubric.py` and stays green.
- [ ] Every emitted `failure_modes[*].code` is in `task_class.failure_mode_taxonomy`; every `breakdown` key is in `task_class.breakdown_keys`. A unit test (`test_rubric_emits_only_declared_codes`) asserts this on a synthetic-input matrix.
- [ ] Red test from §TDD plan exists and is now green; `ruff check`, `ruff format --check`, `mypy --strict bench/vuln-remediation/rubric.py bench/vuln-remediation/tests/test_rubric_unit.py`, and `pytest bench/vuln-remediation/tests/` all pass.

## Implementation outline

1. Write the red test `bench/vuln-remediation/tests/test_rubric_unit.py` first — see §TDD plan.
2. Implement `score(case, harness_output)` as a pure function. Read scoring signals from `harness_output` (e.g., `harness_output["validator"]["build_passed"]: bool`, `harness_output["validator"]["tests_passed"]: bool`, `harness_output["validator"]["cve_dropped"]: bool`, `harness_output["recipe"]["applied"]: bool`). Compute `breakdown` as `{BreakdownKey.X.value: 1.0 if condition else 0.0, ...}`. Compute `passed = all(condition_set)`. Compute `score = mean(breakdown.values())`. Compute `failure_modes` by mapping each failing condition to the corresponding declared code from `failure_modes.yaml`.
3. Implement the `if __name__ == "__main__":` entrypoint:
   ```python
   if __name__ == "__main__":
       import sys, json
       from codegenie.eval.models import BenchCase, BenchScore
       payload = json.loads(sys.stdin.buffer.read())
       case = BenchCase.model_validate(payload["case"])
       harness_output = payload["harness_output"]
       result = score(case, harness_output)
       sys.stdout.buffer.write(result.model_dump_json().encode("utf-8"))
       sys.exit(0)
   ```
4. Implement `bench/vuln-remediation/tests/__init__.py` (empty package marker) so pytest discovers the tests when invoked from the repo root.
5. Write `tests/integration/test_rubric_subprocess_vuln.py` to exercise the subprocess path with `SCRUBBED_ENV` (mirror the runner's contract); assert wall-clock ≤ 60 s on a representative envelope.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `bench/vuln-remediation/tests/test_rubric_unit.py`

```python
# bench/vuln-remediation/tests/test_rubric_unit.py
"""In-process bench-author tests. The runner crosses a subprocess boundary;
these tests bypass that boundary because bench/**/tests/ is a trusted edge
(per ADR-0001 §Decision)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bench.vuln_remediation.breakdown_keys import BreakdownKey
from bench.vuln_remediation.rubric import score
from codegenie.eval.models import BenchCase, BenchScore


def _make_case(case_id: str = "001-cve-2025-12345-rag-corpus-derived") -> BenchCase:
    return BenchCase(
        case_id=case_id,
        task_class="vuln-remediation",
        disposition="positive",
        difficulty="easy",
        source="curated",
        curation_class="rag-corpus-derived",
        commit_sha=None,
        added_at=datetime(2026, 5, 12, tzinfo=UTC),
        last_validated_at=datetime(2026, 5, 12, tzinfo=UTC),
        input_path=Path("/tmp/fake/input"),
        expected_path=Path("/tmp/fake/expected"),
        cassette_path=Path("/tmp/fake/cassette"),
        cassette_canary_pin="0" * 32,
        case_digest="blake3:" + "0" * 64,
    )


def test_full_pass_yields_score_one_passed_true_no_block_failures():
    case = _make_case()
    harness_output = {
        "validator": {"build_passed": True, "tests_passed": True, "cve_dropped": True},
        "recipe": {"applied": True},
    }
    result = score(case, harness_output)
    assert isinstance(result, BenchScore)
    assert result.passed is True
    assert result.score >= 0.95
    assert all(fm.severity != "block" for fm in result.failure_modes)


def test_tests_failed_yields_block_failure_validator_tests_failed():
    case = _make_case()
    harness_output = {
        "validator": {"build_passed": True, "tests_passed": False, "cve_dropped": True},
        "recipe": {"applied": True},
    }
    result = score(case, harness_output)
    assert result.passed is False
    block_codes = {fm.code for fm in result.failure_modes if fm.severity == "block"}
    assert "validator.tests_failed" in block_codes


def test_cve_not_dropped_yields_block_failure_validator_cve_not_dropped():
    case = _make_case()
    harness_output = {
        "validator": {"build_passed": True, "tests_passed": True, "cve_dropped": False},
        "recipe": {"applied": True},
    }
    result = score(case, harness_output)
    assert result.passed is False
    assert "validator.cve_not_dropped" in {fm.code for fm in result.failure_modes}


def test_breakdown_keys_are_subset_of_declared_breakdown_key_enum():
    case = _make_case()
    harness_output = {
        "validator": {"build_passed": True, "tests_passed": False, "cve_dropped": False},
        "recipe": {"applied": True},
    }
    result = score(case, harness_output)
    declared = {m.value for m in BreakdownKey}
    assert set(result.breakdown.keys()) <= declared, (
        f"unexpected breakdown keys: {set(result.breakdown.keys()) - declared}"
    )


def test_score_is_deterministic_under_repeated_invocation():
    """ADR-0006 + audit chain: the rubric must be byte-stable. If this test fails,
    the cache hit-rate test (S5-06) and the canary-replay test will also fail."""
    case = _make_case()
    harness_output = {
        "validator": {"build_passed": True, "tests_passed": True, "cve_dropped": True},
        "recipe": {"applied": True},
    }
    j1 = score(case, harness_output).model_dump_json()
    j2 = score(case, harness_output).model_dump_json()
    assert j1 == j2


def test_rubric_emits_only_declared_failure_mode_codes_and_breakdown_keys():
    """Defense-in-depth: even though the runner validates against task_class
    taxonomies, the rubric itself must not emit drift."""
    # Run a matrix of harness outputs and verify no failure_mode emitted
    # is outside the YAML-declared set.
    from importlib import resources
    import yaml
    yaml_text = (Path(__file__).parent.parent / "failure_modes.yaml").read_text()
    declared_codes = set(yaml.safe_load(yaml_text).keys())
    declared_keys = {m.value for m in BreakdownKey}

    case = _make_case()
    for build, tests, cve, recipe in [
        (True, True, True, True),
        (False, True, True, True),
        (True, False, True, True),
        (True, True, False, True),
        (True, True, True, False),
    ]:
        result = score(case, {
            "validator": {"build_passed": build, "tests_passed": tests, "cve_dropped": cve},
            "recipe": {"applied": recipe},
        })
        for fm in result.failure_modes:
            assert fm.code in declared_codes, f"undeclared code: {fm.code}"
        assert set(result.breakdown.keys()) <= declared_keys
```

Run it; confirm `ModuleNotFoundError: No module named 'bench.vuln_remediation.rubric'` or `ImportError: cannot import name 'score'`. Commit as red marker.

### Green — smallest impl shape

1. Implement `score(case, harness_output) -> BenchScore`:
   - Build `breakdown` by mapping each truthy condition in `harness_output` to a `BreakdownKey` value with score 1.0; falsy → 0.0.
   - Compute `passed = all(v == 1.0 for v in breakdown.values())`.
   - Compute `score = sum(breakdown.values()) / len(breakdown)`.
   - For each falsy condition, emit a `FailureMode(code="<declared code>", severity="<declared severity>", detail=None)` — the declared severity comes from the YAML; the rubric **does not** hardcode it (read it once at module load).
2. Implement the `__main__` entrypoint as in §Implementation outline.
3. Run the test suite; iterate until green.

### Refactor — clean up

- Pull the condition-to-code mapping into a module-level `_CONDITION_MAP: Mapping[str, BreakdownKey]` for readability.
- Lift the YAML severity load to module import time (single I/O); cache as `_TAXONOMY: Mapping[str, Literal["block","warn","info"]]`.
- Add a module docstring naming ADR-0001, ADR-0004, ADR-0008 and the "trusted boundary distinction" between in-process bench-author tests and the runner's subprocess invocation.
- `mypy --strict` clean: every `harness_output` access is `cast`-typed or destructure with `pydantic` BaseModel for the envelope.
- `wall_clock_ms` and `cost_usd` in the emitted `BenchScore` are time-since-`score()`-start and 0.0 respectively (no LLM calls in the rubric).

## Files to touch

| Path | Why |
|---|---|
| `bench/vuln-remediation/rubric.py` | New file — `score()` function + `__main__` subprocess entrypoint |
| `bench/vuln-remediation/tests/__init__.py` | New file — empty package marker |
| `bench/vuln-remediation/tests/test_rubric_unit.py` | New file — 6 in-process bench-author tests |
| `tests/integration/test_rubric_subprocess_vuln.py` | New file — subprocess-CLI test with SCRUBBED_ENV (mirrors runner contract) |

## Out of scope

- **The runner-side subprocess invocation.** S3-03 owns `asyncio.create_subprocess_exec(...)` with `SCRUBBED_ENV` and `TemporaryDirectory()` `cwd`; this story honors that contract but does not modify it.
- **Cases.** S5-03 (RAG-corpus-derived) and S5-04 (held-out) land cases that exercise the rubric. The unit tests here use hand-built `BenchCase` objects.
- **The `score(...)` formula tuning.** The story commits to "mechanical against `harness_output`" — fine-grained weights are bench-author judgment; do not over-engineer in this story.
- **Cassette validation.** The rubric does not re-verify cassettes; `harness_output` is whatever the SUT emitted, and trust in it is delegated to Phase 4's canary mechanism.
- **The integration-test wall-clock budget (≤ 60 s).** The story asserts the case-level budget at this size; portfolio-scale budgets (≤ 12 min cold cache) are S5-05's concern.

## Notes for the implementer

- The rubric must work in a stdlib-only subprocess context. No transitive imports of `codegenie.eval.runner`, no FS access outside the `cwd` `TemporaryDirectory`. Read the `BenchCase` paths only if you need to (most rubrics don't — they score from `harness_output` directly).
- Do not catch `Exception` and emit a misleading "passed" score. If `score(...)` fails internally, let the exception propagate; the runner will record `rubric.malformed_output` (block-severity) — that is the correct fail-loud behavior.
- The `__main__` entrypoint must accept the envelope shape the runner produces (S3-03 owns the producer side). The contract is: `{"case": <BenchCase JSON>, "harness_output": <whatever the SUT emitted>}`. If S3-03's envelope shape differs, that is a contract bug — fix at the harness level, not by adapting the rubric.
- Coverage: `pytest --cov=bench.vuln_remediation.rubric --cov-fail-under=90` should hit ≥ 90 % line, ≥ 80 % branch. The `__main__` block is hard to cover in pytest; use `subprocess.run` in the integration test to exercise it.
- `tests/unit/test_eval_package_imports_no_llm_sdk.py` currently walks `src/codegenie/eval/**/*.py` (per ADR-0008 / S1-05). Extend its AST walk to `bench/**/rubric.py` in this story — the ban is structurally identical, and rubrics are a logical extension of the no-LLM-SDK package boundary.
- The "deterministic" property the audit chain depends on means: no `time.time()`, no `random.random()`, no `os.environ` reads, no `uuid.uuid4()`. If the rubric needs a per-case identifier, use `case.case_id`. If you find yourself reaching for randomness or wall-clock, you are doing something the rubric should not do.
