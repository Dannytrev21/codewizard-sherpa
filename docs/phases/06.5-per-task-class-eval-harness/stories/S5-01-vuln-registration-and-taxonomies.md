# Story S5-01 — vuln-remediation registration + breakdown_keys + failure_modes

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** Ready
**Effort:** S
**Depends on:** S4-02 (`codegenie eval run` subcommand exists end-to-end on a stub bench), and transitively the Step 1 contracts (`@register_task_class`, `BreakdownKey` StrEnum convention, taxonomy loader)
**ADRs honored:** ADR-0001 (subprocess-isolation envelope the rubric will fit), ADR-0004 (per-task-class `failure_modes.yaml` taxonomy with severity), ADR-0006 (curation-class split; `min_cases_for_promotion["silver"]` triggers held-out floor), ADR-0008 (per-task-class `BreakdownKey` StrEnum + substring ban at value level)

## Context

Step 5 produces the worked example every Phase 7 implementer will pattern-match against. Before any cases or rubric land, the **task-class identity** for `vuln-remediation` must exist: a single `@register_task_class("vuln-remediation", ...)` literal call, a `BreakdownKey` StrEnum whose values pass ADR-0008's substring ban, and a `failure_modes.yaml` taxonomy whose entries carry `severity ∈ {block, warn, info}` and a non-empty description per ADR-0004. These three artifacts are the structural contract every subsequent S5-* story extends — the rubric (S5-02) emits keys constrained by `BreakdownKey` and codes constrained by `failure_modes.yaml`; the cases (S5-03/04) carry no taxonomy, but the runner validates rubric output against this taxonomy at score time.

The story is intentionally scoped tight: no cases yet, no rubric yet, no E2E run. It is the *identity* declaration the harness needs to know `vuln-remediation` is a real task class with a real breakdown-key and failure-mode shape.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §`bench/{task-class}/` directory contract` — the four files this story creates and their structural roles.
  - `../phase-arch-design.md §Component design → src/codegenie/eval/loader.py` — how `breakdown_keys.py` is imported and `frozenset({m.value for m in BreakdownKey})` is extracted into `task_class.breakdown_keys`.
  - `../phase-arch-design.md §Fence-CI test` — assertions #4 (literal name only), #5 (StrEnum substring ban), #6 (taxonomy validity) all gate this story.
- **Phase ADRs:**
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md §Decision` — `severity: block|warn|info` per code; non-empty `description`; loader parses into `task_class.failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]]`.
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md §Decision` — `min_cases_for_promotion["silver"]` triggers the fence-CI held-out floor (≥ 5 held-out cases). Declaring silver here commits the bench to the floor S5-04 must satisfy.
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md §Decision` — `BreakdownKey` is a `StrEnum`; member *values* (not just names) are walked by fence-CI assertion #5 for `confidence|llm|self_reported|model_says`.
- **Production ADRs:** `../../../production/adrs/0008-objective-signal-trust-score.md` — the upstream "no LLM self-confidence" commitment ADR-0008 structurally enforces.
- **Source design:** `../High-level-impl.md §Step 5` — initial taxonomy proposal (vuln-remediation block/warn/info entries).

## Goal

Land `bench/vuln-remediation/{registration.py, breakdown_keys.py, failure_modes.yaml}` declaring exactly one `@register_task_class("vuln-remediation", min_cases_for_promotion={"bronze": 10, "silver": 25})`, a `BreakdownKey` StrEnum whose values pass ADR-0008's substring ban, and a taxonomy with `severity` per code — all three files importable by the loader and validated by fence-CI assertions #4–#6.

## Acceptance criteria

- [ ] `bench/vuln-remediation/registration.py` contains exactly one `@register_task_class` call whose first positional arg is the literal string `"vuln-remediation"` and whose `min_cases_for_promotion` kwarg is exactly `{"bronze": 10, "silver": 25}`.
- [ ] Importing `bench.vuln_remediation.registration` once (in a fresh registry) registers the task class; a second import in the same test process does **not** raise `TaskClassAlreadyRegistered` (module-import dedup is the standard side-effect pattern).
- [ ] `bench/vuln-remediation/breakdown_keys.py` defines `class BreakdownKey(StrEnum)` with at least 4 members (e.g., `VALIDATOR_TESTS_PASSED`, `VALIDATOR_BUILD_PASSED`, `CVE_DROPPED`, `RECIPE_APPLIED`); every member *value* is a literal `ast.Constant` string (no `f"..."`, no `prefix + suffix`).
- [ ] No `BreakdownKey` member value contains the substrings `confidence`, `llm`, `self_reported`, or `model_says` — `tests/unit/test_breakdown_keys_static.py` (S1-05) walks the registered enum and stays green.
- [ ] `bench/vuln-remediation/failure_modes.yaml` declares **every** code listed in ADR-0004's "initial vuln-remediation taxonomy" (block: `validator.build_failed`, `validator.tests_failed`, `validator.cve_not_dropped`, `recipe.semantic_drift`, `rubric.timeout`, `rubric.unknown_failure_mode`, `sut.exception`, `sut.cancelled`; warn: `recipe.unused_field`, `cassette.tier_mismatch`, `cost.over_estimate`; info: `recipe.optimized_path`, `rag.first_hit`); each entry has `severity ∈ {block, warn, info}` and a non-empty `description` string.
- [ ] After loading, `task_class.breakdown_keys` is a `frozenset[str]` matching the StrEnum values; `task_class.failure_mode_taxonomy[code]` returns the declared severity for every declared code.
- [ ] Fence-CI assertions #4 (literal name), #5 (BreakdownKey substring ban), #6 (taxonomy validity) all pass on these three files; the S7-01 fence test runs them in its ≤ 2 s budget.
- [ ] Red test from §TDD plan exists, was committed at red marker, now green; `ruff check`, `ruff format --check`, `mypy --strict bench/vuln-remediation/registration.py bench/vuln-remediation/breakdown_keys.py`, and `pytest tests/unit/test_bench_vuln_registration.py` all pass.

## Implementation outline

1. Create the directory skeleton: `bench/vuln-remediation/{__init__.py, registration.py, breakdown_keys.py, failure_modes.yaml, README.md}` (README is a stub; S5-05 fills it).
2. Write the red test `tests/unit/test_bench_vuln_registration.py` first — see §TDD plan.
3. `breakdown_keys.py`:
   ```python
   from enum import StrEnum
   class BreakdownKey(StrEnum):
       VALIDATOR_BUILD_PASSED = "validator.build_passed"
       VALIDATOR_TESTS_PASSED = "validator.tests_passed"
       CVE_DROPPED = "cve.dropped"
       RECIPE_APPLIED = "recipe.applied"
       # extend as the rubric needs; no banned substrings; literal values only
   ```
4. `failure_modes.yaml`: enumerate every code with `severity` + `description`. Use the ADR-0004 §Consequences "initial vuln-remediation taxonomy" verbatim as the starting set. Severities are literal lowercase strings.
5. `registration.py`:
   ```python
   from pathlib import Path
   from codegenie.eval.registry import register_task_class
   from bench.vuln_remediation.breakdown_keys import BreakdownKey  # imported so the loader resolves it
   from bench.vuln_remediation.rubric import VulnRemediationRubric  # forward import; S5-02 lands the class

   @register_task_class(
       "vuln-remediation",
       bench_path=Path(__file__).parent,
       min_cases_for_promotion={"bronze": 10, "silver": 25},
       rubric_class=VulnRemediationRubric,
       breakdown_key_enum=BreakdownKey,
   )
   class _VulnRemediationRegistration:  # marker class; the decorator owns the registration
       pass
   ```
   *(Note: the rubric class is imported here even though S5-02 hasn't landed; this story may temporarily stub the import — see §Notes for the implementer.)*
6. Run `mypy --strict` and the fence-CI test against the three files; iterate to green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_bench_vuln_registration.py`

```python
# tests/unit/test_bench_vuln_registration.py
import importlib
from enum import StrEnum

import pytest

from codegenie.eval.registry import TaskClassRegistry, default_registry


BANNED_SUBSTRINGS = ("confidence", "llm", "self_reported", "model_says")

REQUIRED_BLOCK_CODES = frozenset({
    "validator.build_failed",
    "validator.tests_failed",
    "validator.cve_not_dropped",
    "recipe.semantic_drift",
    "rubric.timeout",
    "rubric.unknown_failure_mode",
    "sut.exception",
    "sut.cancelled",
})

REQUIRED_WARN_CODES = frozenset({
    "recipe.unused_field",
    "cassette.tier_mismatch",
    "cost.over_estimate",
})

REQUIRED_INFO_CODES = frozenset({
    "recipe.optimized_path",
    "rag.first_hit",
})


@pytest.fixture()
def fresh_registry(monkeypatch):
    # Isolate side-effect import from the global default_registry.
    reg = TaskClassRegistry()
    monkeypatch.setattr("codegenie.eval.registry.default_registry", reg)
    # Force a fresh import of the registration module so the decorator fires
    # against the patched registry.
    for mod in [
        "bench.vuln_remediation.registration",
        "bench.vuln_remediation.breakdown_keys",
    ]:
        if mod in importlib.sys.modules:
            del importlib.sys.modules[mod]
    return reg


def test_registration_imports_and_uses_literal_name_and_promotion_floors(fresh_registry):
    importlib.import_module("bench.vuln_remediation.registration")
    tc = fresh_registry.get("vuln-remediation")
    assert tc.name == "vuln-remediation"
    # ADR-0006: declaring silver triggers the held-out-≥5 fence assertion.
    assert tc.min_cases_for_promotion == {"bronze": 10, "silver": 25}


def test_breakdown_key_strenum_passes_substring_ban():
    from bench.vuln_remediation.breakdown_keys import BreakdownKey
    assert issubclass(BreakdownKey, StrEnum)
    members = list(BreakdownKey)
    assert len(members) >= 4
    for m in members:
        v = m.value
        assert isinstance(v, str) and v != ""
        for banned in BANNED_SUBSTRINGS:
            assert banned not in v, f"banned substring {banned!r} in BreakdownKey value {v!r}"


def test_failure_modes_yaml_declares_full_taxonomy(fresh_registry):
    importlib.import_module("bench.vuln_remediation.registration")
    tc = fresh_registry.get("vuln-remediation")
    tax = tc.failure_mode_taxonomy
    # Every required code present with the right severity.
    for code in REQUIRED_BLOCK_CODES:
        assert tax[code] == "block", f"{code} should be block-severity"
    for code in REQUIRED_WARN_CODES:
        assert tax[code] == "warn"
    for code in REQUIRED_INFO_CODES:
        assert tax[code] == "info"
    # Every declared code has a non-empty description (loaded as part of taxonomy load,
    # surfaced via task_class.failure_mode_descriptions or analogous mapping).
    descs = getattr(tc, "failure_mode_descriptions", None)
    assert descs is not None
    for code in REQUIRED_BLOCK_CODES | REQUIRED_WARN_CODES | REQUIRED_INFO_CODES:
        assert descs[code].strip() != ""


def test_breakdown_keys_loaded_into_task_class(fresh_registry):
    importlib.import_module("bench.vuln_remediation.registration")
    tc = fresh_registry.get("vuln-remediation")
    from bench.vuln_remediation.breakdown_keys import BreakdownKey
    assert tc.breakdown_keys == frozenset(m.value for m in BreakdownKey)
```

Run it; confirm `ModuleNotFoundError` or `KeyError`. Commit as red marker.

### Green — smallest impl shape

1. Create the three files above. `failure_modes.yaml` as a flat mapping `{code: {severity, description}}`.
2. If `task_class.failure_mode_descriptions` is not yet exposed on `TaskClass` (S1-03), extend the dataclass with that `Mapping[str, str]` field. The loader (S2-01) already parses the YAML — extend it to also populate this map.
3. The decorator side-effect import must run *once* — the test uses a fresh registry per test to isolate.

### Refactor — clean up

- Module docstrings on `registration.py` and `breakdown_keys.py` cite ADR-0004, ADR-0006, ADR-0008.
- `failure_modes.yaml` top-of-file comment names the ADR.
- Type-narrow the `min_cases_for_promotion` literal so mypy `--strict` accepts it without `# type: ignore`.
- The README stub names what S5-02/03/04/05 will add; do not include cases or rubric details — those land in their stories.

## Files to touch

| Path | Why |
|---|---|
| `bench/vuln-remediation/__init__.py` | New file — package marker (empty or single docstring) |
| `bench/vuln-remediation/registration.py` | New file — the single `@register_task_class("vuln-remediation", ...)` literal |
| `bench/vuln-remediation/breakdown_keys.py` | New file — `BreakdownKey` StrEnum with literal values |
| `bench/vuln-remediation/failure_modes.yaml` | New file — full taxonomy with severity per code |
| `bench/vuln-remediation/README.md` | New file — stub; S5-05 expands |
| `tests/unit/test_bench_vuln_registration.py` | New file — pins identity, StrEnum, taxonomy |
| `src/codegenie/eval/loader.py` (possibly) | Extend taxonomy load to populate `failure_mode_descriptions` if S2-01 hasn't already |

## Out of scope

- **The rubric implementation.** S5-02 lands `rubric.py`. This story imports the rubric class as a forward dependency; if S5-02 hasn't merged, ship `rubric.py` as a minimal stub (`class VulnRemediationRubric: def score(self, *_): raise NotImplementedError`). The stub is replaced byte-for-byte in S5-02 and must not be merged to main without S5-02 landing in the same train.
- **Bench cases.** S5-03 and S5-04 land cases.
- **`digests.yaml`.** S5-05 signs cases; no cases exist yet.
- **Cassette pin selection.** Story-level decision is "every case will carry a 32-hex `cassette_canary_pin`"; the *values* are the cases' problem (S5-03/04).
- **Wiring into `codegenie eval run`.** Already wired by S4-02; this story does not modify CLI or runner code.

## Notes for the implementer

- The substring ban in ADR-0008 applies to *values*, not names. `STYLE_QUALITY = "llm_confidence"` is the failure mode the fence catches — a member named `STYLE_QUALITY` is harmless if its value is, e.g., `"style.quality"`. Reviewers reading `breakdown_keys.py` should be able to see every value at a glance — keep them on one line each.
- Declaring `"silver": 25` in `min_cases_for_promotion` is an explicit ADR-0006 commitment that S5-04's 5 held-out cases must land before fence-CI passes. If S5-04 slips and you cannot ship 5 held-out cases in the same train, **drop `"silver"` from `min_cases_for_promotion`** (ship `{"bronze": 10}` only) — adding silver later is one line; shipping silver without held-out floor fails fence-CI #3 and blocks the phase merge.
- The `failure_modes.yaml` initial taxonomy in ADR-0004 §Consequences is illustrative. Use it verbatim as the seed; future task classes (Phase 7) get their own taxonomy. The runner's "always-block" set (`sut.exception`, `sut.timeout`, `rubric.timeout`, `rubric.unknown_failure_mode`, `rubric.unknown_breakdown_key`, `rubric.malformed_output`) must appear here — the ADR-0004 §Tradeoffs row "Codes shared across task classes ... must be replicated per task class" is the rationale.
- The rubric forward-import is a known load-order quirk. Two acceptable resolutions: (a) ship S5-01 and S5-02 in the same PR; (b) stub `VulnRemediationRubric` in `rubric.py` as a `NotImplementedError`-raising class within this story, then have S5-02 replace the body. Pick whichever the team's review velocity supports.
- `bench/__init__.py` may also need to exist so `bench.vuln_remediation` is importable; the S2-01 loader's `sys.path` prep contract should already handle this — verify before adding extra `__init__.py`s.
- Do not edit `src/codegenie/eval/**` beyond what's strictly needed to surface `failure_mode_descriptions`. Per CLAUDE.md "Extension by addition", this story should be near-zero touch to the harness package.
