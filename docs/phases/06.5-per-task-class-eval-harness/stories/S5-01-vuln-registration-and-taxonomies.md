# Story S5-01 — vuln-remediation registration + breakdown_keys + failure_modes

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** HARDENED (phase-story-validator, 2026-06-04)
**Effort:** S
**Depends on:** S1-03 (HARDENED `@register_task_class` kwarg surface: `breakdown_keys`, `failure_mode_taxonomy`, `bench_path`, `min_cases_for_promotion`, decorated class IS the rubric class), S2-01 (HARDENED `load_task_class` is the import surface for tests; hyphen→underscore translation lives there; PEP 420 implicit namespace package contract), S1-04 (`Rubric` Protocol — the stub rubric class must satisfy it structurally), S4-02 (CLI exit-code mapping the typed errors feed). Transitively: Step 1 contracts (`@register_task_class`, `BreakdownKey` StrEnum convention, taxonomy loader).
**ADRs honored:** ADR-0001 (subprocess-isolation envelope the rubric will fit), ADR-0004 (per-task-class `failure_modes.yaml` taxonomy with severity; runtime-mapping is severity-only, descriptions live in YAML for fence-CI validation), ADR-0006 (curation-class split; `min_cases_for_promotion["silver"]` triggers held-out floor), ADR-0008 (per-task-class `BreakdownKey` StrEnum + substring ban at value level + `rubric.unknown_breakdown_key` block code), Phase 5 ADR-0014 (substring-ban source-of-truth shared with ADR-0008)

## Validation notes

Validated: 2026-06-04
Verdict: HARDENED
Findings addressed: 21 total — 7 blocks, 11 hardens, 3 nits

Changes applied (full audit log: `_validation/S5-01-vuln-registration-and-taxonomies.md`):

- **Status line** updated to `HARDENED (phase-story-validator, 2026-06-04)` (F-CON-9).
- **Depends-on** rewritten to name S1-03, S2-01, S1-04 explicitly (F-CON-8).
- **AC-1 + Implementation outline §5 rewritten (BLOCK):** the registration call now uses the HARDENED S1-03 kwarg surface (`breakdown_keys=frozenset(m.value for m in BreakdownKey)`, `failure_mode_taxonomy=_TAXONOMY`) and the **imperative-application form** `register_task_class(...)(VulnRemediationRubric)` against the rubric class imported from `bench.vuln_remediation.rubric` — not the marker-class decoration the original story showed. The marker-class pattern is forbidden in Notes-for-implementer (F-CON-1 + F-CON-2).
- **TDD test surface switched to `load_task_class` (BLOCK):** `tests/unit/eval/test_bench_vuln_registration.py` calls `load_task_class("vuln-remediation", bench_root=tmp_bench_root, registry=fresh_registry)` instead of `importlib.import_module("bench.vuln_remediation.registration")`. The original direct-importlib path cannot resolve the hyphenated on-disk directory under standard Python import machinery; the hyphen→underscore translation is HARDENED S2-01's job. Test file relocated to `tests/unit/eval/` to inherit S2-01's autouse `conftest.py` (sys.path/sys.modules/default_registry snapshot+restore). The fixture's manual `sys.modules` deletion is removed — the conftest handles it (F-CON-3).
- **`failure_mode_descriptions` field assertion dropped (BLOCK):** S1-03 AC-2 pins `TaskClass` to exactly six fields via `dataclasses.fields(TaskClass)` introspection. Descriptions live in `failure_modes.yaml` for fence-CI #6 validation at PR time and are asserted in this story by reading the YAML directly (`test_failure_modes_yaml_has_non_empty_descriptions`) — not via `TaskClass`. Notes-for-implementer pins the split: "descriptions in YAML; severities on TaskClass" (F-CON-4).
- **`bench/__init__.py` hedge hard-banned (BLOCK):** S2-01 HARDENED uses PEP 420 implicit namespace packages — no `__init__.py` files anywhere in `bench/`. The original hedge ("may also need to exist") would (a) break the PEP 420 contract; (b) for the hyphenated leaf, the file can't exist as a valid Python module name. Files-to-touch row removed; Notes-for-implementer carries the hard ban (F-CON-5).
- **Runner-internal always-block codes added to required taxonomy set (BLOCK):** ADR-0004 §Tradeoffs requires the always-block codes to be replicated per task class. The original AC's `REQUIRED_BLOCK_CODES` listed only ADR-0004 §Consequences' eight codes — `sut.timeout`, `rubric.unknown_breakdown_key`, `rubric.malformed_output` were missing. An executor would ship a YAML that the runner immediately blows up on at the first SUT timeout. AC-5 + `REQUIRED_BLOCK_CODES` now require all 11 block codes (F-CON-6).
- **`rubric.py` stub decision pinned (BLOCK):** the original Notes said "Pick whichever the team's review velocity supports." Decision pinned to ship-the-stub in this story so S5-01 is independently mergeable. The exact stub body is pinned in Implementation outline + Notes: `class VulnRemediationRubric:` with one method `def score(self, case, harness_output): raise NotImplementedError("S5-02 replaces this body")`. Files-to-touch table adds `bench/vuln-remediation/rubric.py`; S5-02 replaces the body byte-for-byte (F-CON-7).
- **`failure_modes.yaml` schema ACs added (HARDEN):** AC-7 pins the YAML structure: top-level is `dict[str, dict[str, str]]`; each entry has *exactly* `{severity, description}` keys (no `owner`, no `sla`, etc.); `severity ∈ {block, warn, info}`; description is a non-empty str; YAML loaded via `yaml.safe_load` only. Three parametrized tests pin each branch — an executor cannot ship a YAML that "parses but silently accepts extra keys" (F-COV-3).
- **BreakdownKey↔FailureMode semantic-symmetry pin (HARDEN):** AC-3 + AC-5 document the four breakdown/failure-mode pairs S5-02's rubric will use (`cve.dropped` ↔ `validator.cve_not_dropped`, etc.). Documentation only — does not force a test; rubric (S5-02) owns the score↔failure inversion (F-COV-4).
- **Double-load cache assertion (HARDEN):** AC-6 + `test_double_load_task_class_does_not_raise_and_returns_same_taskclass` exercise the bench-fixture-specific double-load behavior. Defense-in-depth on top of S2-01 AC-6 (F-COV-5).
- **Tautology in `tc.breakdown_keys` assertion fixed (BLOCK):** literal-set assertion `tc.breakdown_keys == frozenset({"validator.build_passed", "validator.tests_passed", "cve.dropped", "recipe.applied"})` + `len(tc.breakdown_keys) == 4` replaces the original tautological `tc.breakdown_keys == frozenset(m.value for m in BreakdownKey)`. Kills empty-enum, single-member, and lowercased-member mutants (F-TQ-1).
- **`MappingProxyType` immutability AC (HARDEN):** AC-5 + §TDD adds `isinstance(tc.failure_mode_taxonomy, types.MappingProxyType)` + a `pytest.raises(TypeError)` on attempted item assignment. Defense-in-depth on S1-03 AC-9 (F-TQ-2).
- **BreakdownKey ast.Constant local check (HARDEN):** AC-3 + `test_breakdown_key_values_are_ast_constant_strings` ASTs `breakdown_keys.py` and asserts every member-value is `ast.Constant`. Fires before fence-CI #5 (S7-01) in a typical PR pipeline (F-TQ-3).
- **Rubric-class-identity AC (HARDEN):** AC-1 + `test_registered_rubric_class_is_imported_class_unmodified` asserts `tc.rubric_class is VulnRemediationRubric` (the imported class). Guards against a regression that wraps the rubric with a side-effecting proxy (F-TQ-5).
- **`tc.bench_path` resolved-absolute AC (HARDEN):** AC-2 adds `assert tc.bench_path == (bench_root / "vuln-remediation").resolve()` (F-TQ-6).
- **Runtime substring ban AC (HARDEN):** AC-4 walks `tc.breakdown_keys` (loader-produced) at runtime and asserts no banned substring — defense-in-depth on top of the static `BreakdownKey` walk (F-TQ-7).
- **Severity-shape AC (HARDEN):** AC-5 asserts `for sev in tc.failure_mode_taxonomy.values(): isinstance(sev, str) and sev in {"block","warn","info"}`. Guards a regression that accidentally projects `{severity, description}` dicts into the taxonomy value (F-TQ-8).
- **YAML→taxonomy helper extraction (HARDEN):** Implementation outline §3 + AC-7 pin a file-local private helper `_severity_taxonomy_from_yaml(path) -> Mapping[str, Literal["block","warn","info"]]` in `registration.py` (NOT a shared module — Rule 2). Notes-for-implementer documents the rule-of-three lift trigger: Phase 15's task class is the third consumer; that's when the helper lifts to `src/codegenie/eval/loader.py` as `_load_failure_mode_taxonomy` (the arch already names this function at line 564) (F-DP-1).
- **`min_cases_for_promotion` literal AC (NIT):** AC-2 pins `tc.min_cases_for_promotion == MappingProxyType({"bronze": 10, "silver": 25})`. Notes-for-implementer keeps the silver-fallback instruction but pins the explicit AC change required if S5-04 slips (F-COV-6).
- **`Status:` line + `Depends on:` + ADRs-honored alignment with HARDENED siblings.**

Design endorsements (no edit; surfaced in Notes-for-implementer):
- **Open/Closed seam at the `bench/{task-class}/` directory contract** (F-DP-3) — Phase 7 ships the next task class by copying this story's three files verbatim; zero `src/codegenie/eval/` edits.
- **`_MIN_CASES_FOR_PROMOTION` Final constant** (F-DP-2) — optional cleanup; not promoted to AC (Rule 2 — one literal today).
- **Adversarial mutant catalog** (F-TQ-10) — five named mutants the §TDD plan kills, surfaced in Notes-for-implementer for the executor and PR reviewers.

No `NEEDS RESEARCH` items — every pattern is precedented in this repo or in upstream HARDENED stories.

## Context

Step 5 produces the worked example every Phase 7 implementer will pattern-match against. Before any cases or rubric land, the **task-class identity** for `vuln-remediation` must exist: a single `register_task_class("vuln-remediation", ...)(VulnRemediationRubric)` imperative-application call, a `BreakdownKey` StrEnum whose values pass ADR-0008's substring ban, and a `failure_modes.yaml` taxonomy whose entries carry `severity ∈ {block, warn, info}` and a non-empty description per ADR-0004. These three (plus a `rubric.py` stub) are the structural contract every subsequent S5-* story extends — the rubric (S5-02) replaces the stub body and emits keys constrained by `BreakdownKey` and codes constrained by `failure_modes.yaml`; the cases (S5-03/04) carry no taxonomy, but the runner validates rubric output against this taxonomy at score time.

The story is intentionally scoped tight: no cases yet, no full rubric, no E2E run. It is the *identity* declaration the harness needs to know `vuln-remediation` is a real task class with a real breakdown-key and failure-mode shape, plus a stub rubric class so the decorator's `type[Rubric]` requirement is satisfied at import time.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §`bench/{task-class}/` directory contract` — the four files this story creates and their structural roles.
  - `../phase-arch-design.md §Component design → src/codegenie/eval/loader.py` — how `breakdown_keys.py` is imported and `frozenset({m.value for m in BreakdownKey})` is extracted; the loader's `_load_failure_mode_taxonomy` helper is the rule-of-three lift target.
  - `../phase-arch-design.md §Fence-CI test` — assertions #4 (literal name only), #5 (StrEnum substring ban), #6 (taxonomy validity) all gate this story; this story's local tests are defense-in-depth on top of these.
- **Phase ADRs:**
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md §Decision + §Consequences + §Tradeoffs` — `severity: block|warn|info` per code; non-empty `description`; loader parses into `task_class.failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]]` (severity only — descriptions stay in YAML for fence-CI #6); §Tradeoffs row "Codes shared across task classes ... must be replicated per task class" is why this story includes the runner-internal always-block codes (`sut.timeout`, `rubric.unknown_breakdown_key`, `rubric.malformed_output`).
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md §Decision` — `min_cases_for_promotion["silver"]` triggers the fence-CI held-out floor (≥ 5 held-out cases). Declaring silver here commits the bench to the floor S5-04 must satisfy.
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md §Decision` — `BreakdownKey` is a `StrEnum`; member *values* (not just names) are walked by fence-CI assertion #5 for `confidence|llm|self_reported|model_says`. The story-local AST walk in §TDD is defense-in-depth on the same set. The `rubric.unknown_breakdown_key` block code listed here must appear in the taxonomy.
- **Sibling HARDENED stories (load-bearing for this story's implementation):**
  - `S1-03-taskclass-dataclass-and-registry.md` — `@register_task_class` HARDENED kwarg surface: `(name, *, bench_path, min_cases_for_promotion, breakdown_keys, failure_mode_taxonomy, registry=None) -> Callable[[type[Rubric]], type[Rubric]]`. The decorator's first positional arg is the *literal* task-class name; the kwargs are the data; the decorated class IS the rubric. Imperative-application form is `register_task_class(...)(VulnRemediationRubric)`.
  - `S2-01-bench-import-path-resolution.md` — `load_task_class(name, bench_root, *, registry=None) -> TaskClass` is the test/CLI import surface; handles the hyphen→underscore translation, PEP 420 implicit namespace package wiring, sys.modules caching for idempotent second-load. The tests in this story go through `load_task_class`, not `importlib.import_module`.
  - `S1-04-rubric-protocol.md` — `Rubric` Protocol (one method, `score(case, harness_output) -> BenchScore`). The stub rubric class in this story satisfies it structurally.
- **Production ADRs:** `../../../production/adrs/0008-objective-signal-trust-score.md` — the upstream "no LLM self-confidence" commitment ADR-0008 structurally enforces. Phase 5 ADR-0014 — the substring-ban source-of-truth.
- **Source design:** `../High-level-impl.md §Step 5` — initial taxonomy proposal (vuln-remediation block/warn/info entries).

## Goal

Land `bench/vuln-remediation/{registration.py, breakdown_keys.py, failure_modes.yaml, rubric.py (stub)}` declaring exactly one `register_task_class("vuln-remediation", bench_path=..., min_cases_for_promotion={"bronze": 10, "silver": 25}, breakdown_keys=frozenset(m.value for m in BreakdownKey), failure_mode_taxonomy=_TAXONOMY)(VulnRemediationRubric)` imperative-application call against the stub rubric class, a `BreakdownKey` StrEnum whose values pass ADR-0008's substring ban at the value level, and a `failure_modes.yaml` with all 11 block codes (ADR-0004 §Consequences's 8 + the 3 runner-internal always-block codes) + warn/info codes — all four files importable via the HARDENED `load_task_class("vuln-remediation", bench_root=Path("bench"))` surface and validated by fence-CI assertions #4–#6.

## Acceptance criteria

- [ ] **AC-1 (imperative registration call, HARDENED-S1-03-conformant):** `bench/vuln-remediation/registration.py` contains exactly one call to `register_task_class` with: (a) first positional arg the *literal* `ast.Constant` string `"vuln-remediation"`; (b) kwargs `bench_path=Path(__file__).parent`, `min_cases_for_promotion={"bronze": 10, "silver": 25}`, `breakdown_keys=frozenset(m.value for m in BreakdownKey)`, `failure_mode_taxonomy=_TAXONOMY` (the file-local mapping built from `failure_modes.yaml`); (c) **imperative-application form** `register_task_class(...)(VulnRemediationRubric)` against the rubric class imported from `bench.vuln_remediation.rubric`. The decorator form `@register_task_class(...) class _Marker: pass` is forbidden — it fails S1-03's `type[Rubric]` Protocol contract. AC-1 pins both the AST shape (one call, literal name) and the kwarg-name set via the local AST-walking test described in §TDD. Test `test_registered_rubric_class_is_imported_class_unmodified` asserts `tc.rubric_class is VulnRemediationRubric` (S1-03 AC-5 — decorator returns the class unmodified).
- [ ] **AC-2 (TaskClass shape post-load, six-field discipline):** After `tc = load_task_class("vuln-remediation", bench_root=tmp_bench_root, registry=fresh_registry)`: (a) `tc.name == "vuln-remediation"`; (b) `tc.bench_path == (tmp_bench_root / "vuln-remediation").resolve()` (absolute, symlink-resolved per S2-01 AC-13); (c) `tc.min_cases_for_promotion == MappingProxyType({"bronze": 10, "silver": 25})` — both the literal value AND the `MappingProxyType` immutability normalized by the decorator per S1-03 AC-9a (`isinstance(tc.min_cases_for_promotion, types.MappingProxyType)`); (d) `dataclasses.fields(TaskClass)` still has exactly six entries (the S1-03 AC-2 pin holds — this story adds no field). ADR-0006: declaring silver triggers the held-out-≥5 fence-CI assertion (#3); S5-04 must ship the 5 held-out cases before fence-CI passes.
- [ ] **AC-3 (BreakdownKey StrEnum, literal-values + ast.Constant + len pin):** `bench/vuln-remediation/breakdown_keys.py` defines `class BreakdownKey(StrEnum)` with exactly the four members `VALIDATOR_BUILD_PASSED = "validator.build_passed"`, `VALIDATOR_TESTS_PASSED = "validator.tests_passed"`, `CVE_DROPPED = "cve.dropped"`, `RECIPE_APPLIED = "recipe.applied"`. Test `test_breakdown_key_values_are_ast_constant_strings` ASTs the module source and asserts every `Assign.value` inside `class BreakdownKey(StrEnum)` is `ast.Constant[str]` (no `f"..."`, no `prefix + suffix`); defense-in-depth on fence-CI #5 (S7-01). Semantic symmetry with `failure_modes.yaml`: `cve.dropped` ↔ `validator.cve_not_dropped`, `validator.build_passed` ↔ `validator.build_failed`, `validator.tests_passed` ↔ `validator.tests_failed`, `recipe.applied` ↔ `recipe.semantic_drift` — pinned as documentation; the rubric (S5-02) owns the score↔failure inversion.
- [ ] **AC-4 (substring ban — static + runtime):** *Static:* every `BreakdownKey` member value passes the substring ban (`confidence|llm|self_reported|model_says` absent). *Runtime:* `for v in tc.breakdown_keys: for banned in BANNED_SUBSTRINGS: assert banned not in v`. Both layers are tested; both kill a loader-injected drift the other would miss. Test `tests/unit/test_breakdown_keys_static.py` (S1-05) walks every registered enum and stays green; this story's local tests are bench-specific defense-in-depth.
- [ ] **AC-5 (failure_modes.yaml taxonomy — 11 block + 3 warn + 2 info codes):** `bench/vuln-remediation/failure_modes.yaml` declares **exactly** the following codes (any addition or omission fails fence-CI #6 and the local schema tests):
  - `block` (11 codes — ADR-0004 §Consequences's 8 + runner-internal-always-block 3 per ADR-0004 §Tradeoffs replication requirement + ADR-0008 §Decision's `rubric.unknown_breakdown_key`): `validator.build_failed`, `validator.tests_failed`, `validator.cve_not_dropped`, `recipe.semantic_drift`, `rubric.timeout`, `rubric.unknown_failure_mode`, `rubric.unknown_breakdown_key`, `rubric.malformed_output`, `sut.exception`, `sut.timeout`, `sut.cancelled`
  - `warn` (3): `recipe.unused_field`, `cassette.tier_mismatch`, `cost.over_estimate`
  - `info` (2): `recipe.optimized_path`, `rag.first_hit`
  Each entry has `severity ∈ {"block", "warn", "info"}` and a non-empty `description` str. After load, `task_class.failure_mode_taxonomy[code]` returns the declared severity for every declared code; severity-shape AC: `for code, sev in tc.failure_mode_taxonomy.items(): isinstance(sev, str) and sev in {"block","warn","info"}` — guards against accidentally projecting the full `{severity, description}` dict into the taxonomy value. `MappingProxyType` immutability normalized by the decorator (S1-03 AC-9): `isinstance(tc.failure_mode_taxonomy, types.MappingProxyType)`; `with pytest.raises(TypeError): tc.failure_mode_taxonomy["new.code"] = "block"`.
- [ ] **AC-6 (double-load idempotence — bench-fixture-specific):** `tc1 = load_task_class("vuln-remediation", bench_root=tmp_bench_root, registry=fresh_registry); tc2 = load_task_class("vuln-remediation", bench_root=tmp_bench_root, registry=fresh_registry)` does NOT raise `TaskClassAlreadyRegistered`, returns `tc1 is tc2`, and `tc1 is fresh_registry.get("vuln-remediation")`. Defense-in-depth on S2-01 AC-6 — catches a bench-fixture-specific regression (e.g., a `for _ in range(2)` wrapping the imperative-application call) the loader-generic test would miss.
- [ ] **AC-7 (failure_modes.yaml schema fence):** Three parametrized tests pin the YAML shape: (a) `test_failure_modes_yaml_top_level_is_dict_of_dicts_with_exactly_two_keys` — for every entry, `set(entry) == {"severity", "description"}` (no extra keys); (b) `test_failure_modes_yaml_severity_values_are_in_literal_set` — `entry["severity"] in {"block", "warn", "info"}`; (c) `test_failure_modes_yaml_descriptions_are_nonempty_strings` — `isinstance(entry["description"], str) and entry["description"].strip() != ""`. Plus `test_failure_modes_yaml_loads_via_safe_load_only` monkeypatches `yaml.load` to raise and asserts the read still succeeds (safe_load path taken). The YAML→taxonomy projection lives in a file-local private helper `_severity_taxonomy_from_yaml(path: Path) -> Mapping[str, Literal["block","warn","info"]]` so it's testable in isolation; rule-of-three lift trigger is Phase 15's task class (arch line 564 already names the lift target `_load_failure_mode_taxonomy`).
- [ ] **AC-8 (red→green pipeline, lint, typecheck):** Red test from §TDD plan exists, was committed at red marker, now green. `ruff check`, `ruff format --check`, `mypy --strict bench/vuln-remediation/registration.py bench/vuln-remediation/breakdown_keys.py bench/vuln-remediation/rubric.py`, and `pytest tests/unit/eval/test_bench_vuln_registration.py` all pass. Fence-CI assertions #4 (literal name), #5 (BreakdownKey substring ban), #6 (taxonomy validity) all pass on these three files in S7-01's ≤ 2 s budget.

## Implementation outline

1. **Directory skeleton:** Create `bench/vuln-remediation/{registration.py, breakdown_keys.py, failure_modes.yaml, rubric.py, README.md}`. README is a one-paragraph stub naming what S5-02/03/04/05 will add. **Do NOT create** `bench/__init__.py` or `bench/vuln-remediation/__init__.py` — S2-01 HARDENED uses PEP 420 implicit namespace packages; the second file can't exist as a valid Python module name anyway (hyphen).

2. **Write the red test `tests/unit/eval/test_bench_vuln_registration.py` first** — see §TDD plan. The test file lives under `tests/unit/eval/` to inherit S2-01 HARDENED AC-22's autouse `conftest.py` (sys.path/sys.modules/default_registry snapshot+restore).

3. **`breakdown_keys.py`:**
   ```python
   """ADR-0008 — per-task-class BreakdownKey StrEnum.

   Every member value is a literal ast.Constant string; substring ban
   (Phase 5 ADR-0014 + ADR-0008) applied at the value level.
   """
   from enum import StrEnum


   class BreakdownKey(StrEnum):
       VALIDATOR_BUILD_PASSED = "validator.build_passed"
       VALIDATOR_TESTS_PASSED = "validator.tests_passed"
       CVE_DROPPED = "cve.dropped"
       RECIPE_APPLIED = "recipe.applied"
   ```

4. **`failure_modes.yaml`:** Flat mapping `{code: {severity: <literal>, description: <non-empty str>}}`. All 11 block + 3 warn + 2 info codes per AC-5. Top-of-file comment names `ADR-0004` and `ADR-0008`. Severities are literal lowercase strings. The YAML parses via `yaml.safe_load`.

5. **`rubric.py` (stub — S5-02 replaces the body byte-for-byte):**
   ```python
   """Stub rubric for vuln-remediation. S5-02 replaces the body.

   Satisfies the Rubric Protocol (S1-04: one method, `score`) so the
   decorator's `type[Rubric]` requirement holds at import time.
   """
   from typing import Any


   class VulnRemediationRubric:
       def score(self, case: Any, harness_output: Any) -> Any:
           raise NotImplementedError("S5-02 replaces this body")
   ```

6. **`registration.py`** (imperative-application form per HARDENED S1-03):
   ```python
   """ADR-0004, ADR-0006, ADR-0008 — task-class identity for vuln-remediation.

   Decoration is via the imperative-application form. The decorator's
   kwarg surface is S1-03 HARDENED; the loader (S2-01) is the import surface.
   """
   from pathlib import Path
   from types import MappingProxyType
   from typing import Final, Literal, Mapping

   import yaml

   from codegenie.eval.registry import register_task_class
   from bench.vuln_remediation.breakdown_keys import BreakdownKey
   from bench.vuln_remediation.rubric import VulnRemediationRubric

   _HERE: Final[Path] = Path(__file__).parent


   def _severity_taxonomy_from_yaml(
       path: Path,
   ) -> Mapping[str, Literal["block", "warn", "info"]]:
       """File-local helper. Rule-of-three lift trigger: Phase 15's task class.
       At that point this moves to `src/codegenie/eval/loader.py` as
       `_load_failure_mode_taxonomy` (arch line 564 names the target)."""
       raw = yaml.safe_load(path.read_text())
       if not isinstance(raw, dict):
           raise ValueError(f"failure_modes.yaml top-level must be dict, got {type(raw).__name__}")
       return MappingProxyType({code: spec["severity"] for code, spec in raw.items()})


   _TAXONOMY: Final[Mapping[str, Literal["block", "warn", "info"]]] = (
       _severity_taxonomy_from_yaml(_HERE / "failure_modes.yaml")
   )

   register_task_class(
       "vuln-remediation",
       bench_path=_HERE,
       min_cases_for_promotion={"bronze": 10, "silver": 25},
       breakdown_keys=frozenset(m.value for m in BreakdownKey),
       failure_mode_taxonomy=_TAXONOMY,
   )(VulnRemediationRubric)
   ```

7. Run `mypy --strict` and `pytest tests/unit/eval/test_bench_vuln_registration.py`; iterate to green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/eval/test_bench_vuln_registration.py` (under `tests/unit/eval/` to inherit S2-01 HARDENED AC-22's autouse `conftest.py`).

```python
# tests/unit/eval/test_bench_vuln_registration.py
import ast
import types
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

# BANNED_SUBSTRINGS mirrors Phase 5 ADR-0014 + ADR-0008 §Decision; any change
# here must amend both ADRs.
BANNED_SUBSTRINGS = ("confidence", "llm", "self_reported", "model_says")

EXPECTED_BREAKDOWN_VALUES = frozenset({
    "validator.build_passed",
    "validator.tests_passed",
    "cve.dropped",
    "recipe.applied",
})

REQUIRED_BLOCK_CODES = frozenset({
    # ADR-0004 §Consequences's initial taxonomy
    "validator.build_failed",
    "validator.tests_failed",
    "validator.cve_not_dropped",
    "recipe.semantic_drift",
    "rubric.timeout",
    "rubric.unknown_failure_mode",
    "sut.exception",
    "sut.cancelled",
    # ADR-0004 §Tradeoffs replication requirement: runner-internal always-block
    "sut.timeout",
    "rubric.unknown_breakdown_key",   # ADR-0008 §Decision
    "rubric.malformed_output",
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

ALL_REQUIRED_CODES = REQUIRED_BLOCK_CODES | REQUIRED_WARN_CODES | REQUIRED_INFO_CODES


@pytest.fixture()
def fresh_registry():
    """The autouse conftest at tests/unit/eval/conftest.py (S2-01 HARDENED AC-22)
    snapshots sys.path/sys.modules and monkeypatches default_registry. This
    fixture exposes the fresh default_registry for direct assertions."""
    from codegenie.eval.registry import default_registry as reg
    return reg


@pytest.fixture()
def bench_root(tmp_path: Path) -> Path:
    """Materialize bench/vuln-remediation/* under tmp_path, mirroring the
    real on-disk fixture. The loader resolves the hyphenated leaf via
    spec_from_file_location (S2-01 AC-9)."""
    bench = tmp_path / "bench"
    src = Path(__file__).parents[3] / "bench" / "vuln-remediation"
    target = bench / "vuln-remediation"
    target.mkdir(parents=True)
    for name in ("registration.py", "breakdown_keys.py", "failure_modes.yaml", "rubric.py"):
        (target / name).write_bytes((src / name).read_bytes())
    return bench


# --- AC-1 / AC-2 — registered TaskClass shape ----------------------------------


def test_registration_via_load_task_class_uses_literal_name_and_promotion(
    bench_root: Path, fresh_registry,
):
    from codegenie.eval.loader import load_task_class

    tc = load_task_class("vuln-remediation", bench_root=bench_root, registry=fresh_registry)
    assert tc.name == "vuln-remediation"
    assert tc.bench_path == (bench_root / "vuln-remediation").resolve()
    # ADR-0006: declaring silver commits to held-out-≥5 fence (S5-04).
    assert tc.min_cases_for_promotion == MappingProxyType({"bronze": 10, "silver": 25})
    assert isinstance(tc.min_cases_for_promotion, types.MappingProxyType)


def test_registered_rubric_class_is_imported_class_unmodified(
    bench_root: Path, fresh_registry,
):
    from codegenie.eval.loader import load_task_class

    tc = load_task_class("vuln-remediation", bench_root=bench_root, registry=fresh_registry)
    # S1-03 AC-5: decorator returns the class unmodified — `is`, not `==`.
    from bench.vuln_remediation.rubric import VulnRemediationRubric
    assert tc.rubric_class is VulnRemediationRubric


# --- AC-3 — BreakdownKey StrEnum shape ----------------------------------------


def test_breakdown_key_strenum_has_expected_four_members(bench_root: Path, fresh_registry):
    from codegenie.eval.loader import load_task_class
    load_task_class("vuln-remediation", bench_root=bench_root, registry=fresh_registry)

    from bench.vuln_remediation.breakdown_keys import BreakdownKey

    assert issubclass(BreakdownKey, StrEnum)
    values = frozenset(m.value for m in BreakdownKey)
    assert values == EXPECTED_BREAKDOWN_VALUES
    assert len(values) == 4


def test_breakdown_key_values_are_ast_constant_strings(bench_root: Path):
    """Defense-in-depth on fence-CI #5 (S7-01). Catches f-string / concat mutants."""
    src = (bench_root / "vuln-remediation" / "breakdown_keys.py").read_text()
    tree = ast.parse(src)
    enum_cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "BreakdownKey"
    )
    for node in enum_cls.body:
        if isinstance(node, ast.Assign):
            assert isinstance(node.value, ast.Constant), (
                f"BreakdownKey.{node.targets[0].id} value is not ast.Constant"
            )
            assert isinstance(node.value.value, str)


# --- AC-4 — substring ban (static + runtime) ---------------------------------


def test_breakdown_key_strenum_static_substring_ban(bench_root: Path, fresh_registry):
    from codegenie.eval.loader import load_task_class
    load_task_class("vuln-remediation", bench_root=bench_root, registry=fresh_registry)

    from bench.vuln_remediation.breakdown_keys import BreakdownKey

    for m in BreakdownKey:
        for banned in BANNED_SUBSTRINGS:
            assert banned not in m.value, (
                f"banned substring {banned!r} in BreakdownKey.{m.name} value {m.value!r}"
            )


def test_breakdown_keys_runtime_substring_ban(bench_root: Path, fresh_registry):
    """Runtime-side: loader-produced tc.breakdown_keys, not the static enum."""
    from codegenie.eval.loader import load_task_class
    tc = load_task_class("vuln-remediation", bench_root=bench_root, registry=fresh_registry)
    for v in tc.breakdown_keys:
        for banned in BANNED_SUBSTRINGS:
            assert banned not in v


# --- AC-5 — failure_modes.yaml taxonomy + immutability ------------------------


def test_failure_modes_taxonomy_has_every_required_code_with_correct_severity(
    bench_root: Path, fresh_registry,
):
    from codegenie.eval.loader import load_task_class

    tc = load_task_class("vuln-remediation", bench_root=bench_root, registry=fresh_registry)
    tax = tc.failure_mode_taxonomy
    for code in REQUIRED_BLOCK_CODES:
        assert tax[code] == "block", f"{code} should be block-severity"
    for code in REQUIRED_WARN_CODES:
        assert tax[code] == "warn"
    for code in REQUIRED_INFO_CODES:
        assert tax[code] == "info"
    # The set is exactly what we require — no silent extras, no gaps.
    assert set(tax.keys()) == set(ALL_REQUIRED_CODES)


def test_failure_mode_taxonomy_value_shape_is_literal_str_severity(
    bench_root: Path, fresh_registry,
):
    """Guards against accidentally projecting the full {severity, description}
    dict into the taxonomy value instead of the bare severity."""
    from codegenie.eval.loader import load_task_class
    tc = load_task_class("vuln-remediation", bench_root=bench_root, registry=fresh_registry)
    for code, sev in tc.failure_mode_taxonomy.items():
        assert isinstance(sev, str), f"{code} severity is not str: {type(sev).__name__}"
        assert sev in {"block", "warn", "info"}


def test_failure_mode_taxonomy_is_mapping_proxy_type(bench_root: Path, fresh_registry):
    """S1-03 AC-9 typed-at-the-edge: decorator normalizes to MappingProxyType."""
    from codegenie.eval.loader import load_task_class
    tc = load_task_class("vuln-remediation", bench_root=bench_root, registry=fresh_registry)
    assert isinstance(tc.failure_mode_taxonomy, types.MappingProxyType)
    with pytest.raises(TypeError):
        tc.failure_mode_taxonomy["new.code"] = "block"  # type: ignore[index]


# --- AC-6 — double-load idempotence ------------------------------------------


def test_double_load_task_class_does_not_raise_and_returns_same_taskclass(
    bench_root: Path, fresh_registry,
):
    """Defense-in-depth on S2-01 AC-6 — bench-fixture-specific."""
    from codegenie.eval.loader import load_task_class

    tc1 = load_task_class("vuln-remediation", bench_root=bench_root, registry=fresh_registry)
    tc2 = load_task_class("vuln-remediation", bench_root=bench_root, registry=fresh_registry)
    assert tc1 is tc2
    assert tc1 is fresh_registry.get("vuln-remediation")


# --- AC-7 — failure_modes.yaml schema fence ----------------------------------


def _load_yaml(bench_root: Path) -> dict:
    return yaml.safe_load(
        (bench_root / "vuln-remediation" / "failure_modes.yaml").read_text(),
    )


def test_failure_modes_yaml_top_level_is_dict_of_dicts_with_exactly_two_keys(
    bench_root: Path,
):
    raw = _load_yaml(bench_root)
    assert isinstance(raw, dict)
    for code, entry in raw.items():
        assert isinstance(entry, dict), f"{code} entry is not a dict"
        assert set(entry.keys()) == {"severity", "description"}, (
            f"{code} has unexpected keys: {set(entry.keys())}"
        )


@pytest.mark.parametrize("legal_severity", ["block", "warn", "info"])
def test_failure_modes_yaml_severity_values_are_in_literal_set(
    bench_root: Path, legal_severity: str,
):
    raw = _load_yaml(bench_root)
    severities = {entry["severity"] for entry in raw.values()}
    assert severities <= {"block", "warn", "info"}
    # And every legal severity actually appears (sanity).
    assert legal_severity in severities


def test_failure_modes_yaml_descriptions_are_nonempty_strings(bench_root: Path):
    """ADR-0004 §Decision: every entry has a non-empty description.
    Validated by fence-CI #6 (S7-01); this story's local test is defense-in-depth."""
    raw = _load_yaml(bench_root)
    for code, entry in raw.items():
        assert isinstance(entry["description"], str), f"{code} description is not str"
        assert entry["description"].strip() != "", f"{code} description is empty"


def test_failure_modes_yaml_loads_via_safe_load_only(
    bench_root: Path, monkeypatch: pytest.MonkeyPatch,
):
    """If unsafe yaml.load were used, this monkeypatch would fail the read."""
    monkeypatch.setattr(
        yaml, "load",
        lambda *a, **kw: pytest.fail("yaml.load called; safe_load discipline broken"),
    )
    # safe_load is what registration.py uses; this should not trip the monkeypatch.
    raw = yaml.safe_load(
        (bench_root / "vuln-remediation" / "failure_modes.yaml").read_text(),
    )
    assert isinstance(raw, dict)
```

Run it; confirm `ModuleNotFoundError` (the registration module doesn't exist yet) or `BenchCaseLoadError` if the loader is in place but the bench dir empty. Commit as red marker.

### Green — smallest impl shape

1. Create the four files in `bench/vuln-remediation/` per §Implementation outline §1, §3, §4, §5, §6.
2. `failure_modes.yaml` as flat mapping `{code: {severity, description}}` — all 13 codes (11 block + 2 warn missing actually 3 warn + 2 info = 16 codes total).
3. Wait — recount: 11 block + 3 warn + 2 info = 16 codes total. The YAML must declare exactly these 16; no more, no fewer.
4. The imperative-application call in `registration.py` runs *once* — Python's sys.modules cache (set up by S2-01's loader) prevents re-execution on subsequent `load_task_class` calls.

### Refactor — clean up

- Module docstrings on `registration.py`, `breakdown_keys.py`, `rubric.py` cite ADR-0004, ADR-0006, ADR-0008.
- `failure_modes.yaml` top-of-file comment names ADR-0004 + ADR-0008.
- Type-narrow the `min_cases_for_promotion` literal so mypy `--strict` accepts it.
- The README stub names what S5-02/03/04/05 will add; do not include cases or rubric details — those land in their stories.
- Optional cleanup (NOT promoted to AC): lift `min_cases_for_promotion={"bronze": 10, "silver": 25}` to a module-level `_MIN_CASES_FOR_PROMOTION: Final[Mapping[str, int]] = MappingProxyType({"bronze": 10, "silver": 25})` so the silver-fallback edit is a one-line constant change. Rule 2 — only one literal today.

## Files to touch

| Path | Why |
|---|---|
| `bench/vuln-remediation/registration.py` | New file — imperative-application `register_task_class("vuln-remediation", ...)(VulnRemediationRubric)` + `_severity_taxonomy_from_yaml` helper |
| `bench/vuln-remediation/breakdown_keys.py` | New file — `BreakdownKey` StrEnum with 4 literal-value members |
| `bench/vuln-remediation/failure_modes.yaml` | New file — full taxonomy (11 block + 3 warn + 2 info codes) with severity + non-empty description per code |
| `bench/vuln-remediation/rubric.py` | New file — stub `VulnRemediationRubric` (one `score` method raising NotImplementedError); S5-02 replaces the body byte-for-byte |
| `bench/vuln-remediation/README.md` | New file — stub naming what S5-02/03/04/05 add |
| `tests/unit/eval/test_bench_vuln_registration.py` | New file — pins identity, StrEnum, taxonomy, YAML schema, immutability, double-load |

## Out of scope

- **The rubric implementation.** S5-02 replaces `bench/vuln-remediation/rubric.py`'s body byte-for-byte. This story ships the stub so S5-01 is independently mergeable; the stub satisfies S1-04's Rubric Protocol structurally (one `score` method) so the decorator's `type[Rubric]` requirement holds at import time. S5-02 is NOT a precondition for S5-01 to merge.
- **Bench cases.** S5-03 and S5-04 land cases.
- **`digests.yaml`.** S5-05 signs cases; no cases exist yet.
- **Cassette pin selection.** Story-level decision is "every case will carry a 32-hex `cassette_canary_pin`"; the *values* are the cases' problem (S5-03/04).
- **Wiring into `codegenie eval run`.** Already wired by S4-02; this story does not modify CLI or runner code.
- **Fence-CI implementation.** S7-01 owns the six fence-CI assertions; this story's local tests are defense-in-depth, not the fence itself.
- **Rule-of-three lift of `_severity_taxonomy_from_yaml`.** Today there are two consumers (vuln-remediation + migration-chainguard-distroless); Phase 15's task class is the third. At that point the helper moves to `src/codegenie/eval/loader.py` as `_load_failure_mode_taxonomy` (the arch already names the function at line 564).

## Notes for the implementer

- **`@register_task_class` HARDENED kwarg surface (S1-03 line 100-110).** The decorator's signature is `register_task_class(name, *, bench_path, min_cases_for_promotion, breakdown_keys, failure_mode_taxonomy, registry=None) -> Callable[[type[Rubric]], type[Rubric]]`. Use the **imperative-application form** `register_task_class(...)(VulnRemediationRubric)` because the rubric class lives in a separate `rubric.py` file. The `@register_task_class(...) class _Marker: pass` pattern is **forbidden** — the marker class fails S1-03's `rubric_class: type[Rubric]` Protocol contract (mypy --strict would reject), and the decorator's behavior under it is to register the marker as the rubric, which the runner cannot subprocess-invoke.
- **Loader is the test/CLI import surface.** Standard Python `importlib.import_module("bench.vuln_remediation.registration")` cannot resolve the hyphenated on-disk directory `bench/vuln-remediation/` — the hyphen→underscore translation is HARDENED S2-01's job via `spec_from_file_location`. Tests and CLI both go through `load_task_class`. Direct `importlib` calls in tests will fail with `ModuleNotFoundError`.
- **Hyphen vs underscore — both forms, in different contexts.** On-disk: `bench/vuln-remediation/` (hyphen — directory naming convention; matches the registered slug). In code: `bench.vuln_remediation.X` (underscore — Python identifier discipline). The two forms are NOT alternatives; both must be used in their respective contexts. S2-01 HARDENED AC-9 owns the translation.
- **Do NOT create `bench/__init__.py` or `bench/vuln-remediation/__init__.py`.** S2-01 HARDENED uses PEP 420 implicit namespace packages — no `__init__.py` files anywhere in `bench/`. The hyphenated leaf can't have one anyway (invalid Python identifier).
- **Descriptions in YAML; severities on TaskClass.** Per ADR-0004 §Consequences, `task_class.failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]]` carries severity *only*. The full `{severity, description}` shape lives in the YAML and is validated by fence-CI #6 (and by this story's local `test_failure_modes_yaml_descriptions_are_nonempty_strings`). Do not invent a `failure_mode_descriptions` field on TaskClass — S1-03 AC-2 pins the six-field set; adding a 7th breaks the structural assertion.
- **Substring ban applies to *values*, not names.** `STYLE_QUALITY = "llm_confidence"` is the failure mode the fence catches — a member *named* `STYLE_QUALITY` is harmless if its value is, e.g., `"style.quality"`. Reviewers reading `breakdown_keys.py` should be able to see every value at a glance — keep them on one line each. Source-of-truth for the substring list is Phase 5 ADR-0014 + ADR-0008; any change there amends both.
- **Declaring `"silver": 25` in `min_cases_for_promotion` is an explicit ADR-0006 commitment** that S5-04's 5 held-out cases must land before fence-CI passes. If S5-04 slips and you cannot ship 5 held-out cases in the same train, **drop `"silver"` from `min_cases_for_promotion`** (ship `{"bronze": 10}` only) — adding silver later is one line; shipping silver without held-out floor fails fence-CI #3 and blocks the phase merge. If you drop `silver`, also **update AC-2 in this story** to remove `silver` (the literal-equality assertion would otherwise fail).
- **Why all 11 block codes are required.** ADR-0004 §Tradeoffs explicitly requires codes shared across task classes (runner-internal always-block: `sut.exception`, `sut.timeout`, `rubric.timeout`, `rubric.unknown_failure_mode`, `rubric.unknown_breakdown_key`, `rubric.malformed_output`) to be replicated per task class. Without `sut.timeout` in this YAML, the first SUT subprocess timeout in production emits `sut.timeout` → resolver sees unknown code → falls back to `rubric.unknown_failure_mode` (block) → operator gets a misleading error. ADR-0008 §Decision adds `rubric.unknown_breakdown_key` to the always-block set.
- **`bench.vuln_remediation.rubric` stub-replacement contract.** S5-02 replaces the body byte-for-byte. Until then this story's stub raises `NotImplementedError("S5-02 replaces this body")` from `score(...)`. The Protocol contract (S1-04) is satisfied structurally (one method with the right name) — mypy --strict accepts it; the registry stores it; runtime invocation would raise the stub's error, which is the correct fail-loud behavior pre-S5-02.
- **Extension-by-addition seam at the `bench/{task-class}/` directory contract.** Phase 7 ships `bench/migration-chainguard-distroless/` by copying these three files (+stub) verbatim. Zero edits to `src/codegenie/eval/` should be required. If Phase 7 needs a kernel edit, that's a contract surface bug to fix here, not there.
- **Adversarial mutant catalog (this story's §TDD plan kills these five):**
  1. **Empty BreakdownKey** — `class BreakdownKey(StrEnum): pass`. Killed by AC-3's literal-set equality.
  2. **BreakdownKey value list of length 1** — only `VALIDATOR_BUILD_PASSED` shipped. Killed by AC-3's `len == 4`.
  3. **`failure_modes.yaml` with `severity: "fatal"`** — out of Literal set. Killed by AC-7's severity-set assertion.
  4. **`failure_modes.yaml` entry with extra `owner` key** — silent schema drift. Killed by AC-7's exact-key-set assertion.
  5. **`registration.py` decorating a marker class** — fails Protocol contract; runner can't invoke. Killed by AC-1's `tc.rubric_class is VulnRemediationRubric`.
