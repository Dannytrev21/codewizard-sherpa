# Validation report — S5-01 vuln-remediation registration + breakdown_keys + failure_modes

**Validated:** 2026-06-04
**Validator:** phase-story-validator
**Verdict:** HARDENED
**Findings:** 21 total — 7 block, 11 harden, 3 nit

The story's *goal* (land `bench/vuln-remediation/{registration.py, breakdown_keys.py, failure_modes.yaml}` as the structural identity for the vuln-remediation task class, validated by fence-CI #4/#5/#6 and consumable by the harness loader) is sound and traces directly to phase ADR-0004, ADR-0006, ADR-0008. **But the story as authored predates the HARDENED S1-03 (registry decorator) and S2-01 (loader) contracts, and an executor following it verbatim would (a) write a `@register_task_class(..., rubric_class=..., breakdown_key_enum=...)` call that contradicts S1-03's actual kwarg names (`breakdown_keys`, `failure_mode_taxonomy`); (b) decorate a marker class (`_VulnRemediationRegistration: pass`) that fails the `type[Rubric]` Protocol structural check under `mypy --strict`; (c) test via `importlib.import_module("bench.vuln_remediation.registration")` which cannot resolve the hyphenated on-disk dir `bench/vuln-remediation/` under standard Python import machinery (the hyphen→underscore translation is the loader's job per S2-01 AC-9); (d) require a 7th `failure_mode_descriptions` field on TaskClass that S1-03 AC-2 explicitly pins against; (e) leave the `rubric.py` stub-vs-stagger decision to "whichever the team's review velocity supports" — exactly the unspecified decision the validator should pin; (f) hedge on `bench/__init__.py` that S2-01 HARDENED forbids under PEP 420 implicit namespace packages; (g) omit the runner-internal always-block codes (`sut.timeout`, `rubric.unknown_breakdown_key`, `rubric.malformed_output`) that ADR-0004 §Tradeoffs "must be replicated per task class" requires.** Every issue is patchable in place → **HARDENED**, not RESCUE. The goal is correct; the contract surface is stale.

Conflict-resolution priority applied: **Consistency > Coverage > Test-Quality > Design-Patterns**. The dominant lens was Consistency — the story inherited several drifts from a pre-S1-03/S2-01 draft. The Design-Patterns critic added one AC promotion (extract a typed `_severity_from_yaml_entry` helper in registration.py so YAML parsing is testable in isolation) and otherwise surfaced extension-path opportunities (failure-mode-taxonomy reader kernel for rule-of-three at Phase 7, `_MIN_CASES_FOR_PROMOTION` Final constant) without promoting them to ACs, per Rule 2.

No `NEEDS RESEARCH` items — every pattern is precedented in this repo (`probes/registry.py`, `plugins/registry.py`, `transforms/signal_kinds.py`, the HARDENED S1-03 and S2-01 contracts immediately upstream).

---

## Critic: Consistency (lens: does the story contradict the hardened arch / ADRs / sibling HARDENED stories?)

### F-CON-1 (BLOCK) — `@register_task_class` signature contradicts HARDENED S1-03 contract

The story's example `registration.py` (lines 64-74) calls:

```python
@register_task_class(
    "vuln-remediation",
    bench_path=Path(__file__).parent,
    min_cases_for_promotion={"bronze": 10, "silver": 25},
    rubric_class=VulnRemediationRubric,         # ← NOT a kwarg per S1-03
    breakdown_key_enum=BreakdownKey,            # ← NOT a kwarg name per S1-03
)
class _VulnRemediationRegistration:  # marker class; the decorator owns the registration
    pass
```

HARDENED S1-03 (`stories/S1-03-taskclass-dataclass-and-registry.md` lines 100-110) pins the decorator signature as:

```python
def register_task_class(
    name: str,
    *,
    bench_path: Path,
    min_cases_for_promotion: Mapping[str, int],
    breakdown_keys: frozenset[str] | set[str],
    failure_mode_taxonomy: Mapping[str, Literal["block", "warn", "info"]],
    registry: TaskClassRegistry | None = None,
) -> Callable[[type[Rubric]], type[Rubric]]: ...
```

Three contradictions: (a) `rubric_class` is NOT a kwarg — it is the *decorated class itself* (S1-03 implementation outline line 119: `rubric_class=rubric_class` is captured from the decorator target, not the kwargs); (b) the breakdown-keys kwarg is named `breakdown_keys`, not `breakdown_key_enum`, and takes a `frozenset[str] | set[str]` (the enum values), not the enum class; (c) `failure_mode_taxonomy` is REQUIRED — the original story does not pass it at all, so the call would `TypeError` at decoration time. **Resolution:** §Implementation outline now shows the imperative-application pattern that the file layout (rubric class in `rubric.py`, registration in `registration.py`) requires:

```python
register_task_class(
    "vuln-remediation",
    bench_path=_HERE,
    min_cases_for_promotion={"bronze": 10, "silver": 25},
    breakdown_keys=frozenset(m.value for m in BreakdownKey),
    failure_mode_taxonomy=_TAXONOMY,
)(VulnRemediationRubric)
```

AC-1 was rewritten to pin the literal kwarg names + the imperative-application form. Notes-for-implementer points the reader at S1-03 implementation outline for the kwarg shape.

### F-CON-2 (BLOCK) — Marker-class decoration violates `type[Rubric]` Protocol contract

The original §Implementation outline §5 decorates `class _VulnRemediationRegistration: pass`. S1-03 AC-5 (`rubric_class: type[Rubric]`) requires the decorated class to satisfy the `Rubric` Protocol (S1-04: one method, `score(case, harness_output) -> BenchScore`). A bare `class _VulnRemediationRegistration: pass` fails the Protocol structural check — `mypy --strict` would reject the resulting `TaskClass(rubric_class=_VulnRemediationRegistration)` because `_VulnRemediationRegistration` is not `type[Rubric]`. At runtime, the registry stores it anyway (Protocol is structural; runtime `isinstance(c, type)` passes per S1-03 AC-7a), but the type contract is broken — the runner (S3-03) will eventually invoke `task_class.rubric_class.__module__` for subprocess invocation, and the marker class points to nowhere actionable. **Resolution:** AC-1 + AC-2 + §Implementation outline pin the imperative-application form on the **actual rubric class** imported from `bench.vuln_remediation.rubric` (which this story stubs per F-CON-7's hard decision). The marker-class pattern is explicitly forbidden in Notes-for-implementer.

### F-CON-3 (BLOCK) — TDD fixture imports the wrong path; bypasses the loader

The original §TDD fixture clears `sys.modules["bench.vuln_remediation.registration"]` then calls `importlib.import_module("bench.vuln_remediation.registration")` directly. The on-disk directory is `bench/vuln-remediation/` (hyphenated per S2-01 HARDENED F-CON-8); standard Python import machinery cannot find `bench.vuln_remediation` because the package directory has a hyphen, not an underscore. The hyphen→underscore translation is the **loader's** job — HARDENED S2-01 AC-9 pins `importlib.util.spec_from_file_location(f"bench.{module_name}.registration", bench_root / name / "registration.py")` followed by manual `sys.modules` registration under the underscore key, with the package's `__path__` set to the hyphenated directory so transitive imports of `bench.vuln_remediation.breakdown_keys` also resolve. An executor following the original §TDD verbatim would hit `ModuleNotFoundError: No module named 'bench.vuln_remediation'` and "fix" it by either (a) renaming the on-disk dir to underscore (breaks S2-01 AC-9 + arch line 1016), or (b) adding manual `sys.path` munging in the test (parallel infrastructure to the loader). **Resolution:** §TDD rewritten to call `load_task_class("vuln-remediation", bench_root=tmp_bench_root, registry=fresh_registry)` — the loader is the test's import surface. Fixture relocated to `tests/unit/eval/test_bench_vuln_registration.py` to inherit S2-01 HARDENED AC-22's autouse `tests/unit/eval/conftest.py` (sys.path/sys.modules/default_registry snapshot+restore). The fixture's manual `sys.modules` deletion is removed — the conftest handles it.

### F-CON-4 (BLOCK) — `task_class.failure_mode_descriptions` invents a 7th field on TaskClass

The original AC `task_class.failure_mode_taxonomy[code] returns the declared severity for every declared code` is consistent with S1-03 AC-2 (`failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]]`). But §TDD line 168 then asserts `descs = getattr(tc, "failure_mode_descriptions", None); assert descs is not None`. There is no `failure_mode_descriptions` field on `TaskClass` — S1-03 AC-2 pins the field set to exactly 6 names (`name`, `bench_path`, `min_cases_for_promotion`, `rubric_class`, `breakdown_keys`, `failure_mode_taxonomy`) via `dataclasses.fields(TaskClass)` introspection. Adding a 7th would fail S1-03's structural assertion. And per ADR-0004 §Consequences: "loader parses into `task_class.failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]]`" — descriptions are NOT part of the runtime contract; they exist in the YAML for operator/reviewer documentation, validated by fence-CI #6 at PR time (every entry has a non-empty `description`). **Resolution:** Dropped the `failure_mode_descriptions` assertion from §TDD entirely. The description-non-empty discipline is owned by fence-CI #6 (S7-01) at PR time and asserted in this story by reading the YAML directly in a separate test (`test_failure_modes_yaml_has_non_empty_descriptions`) — not via TaskClass. Notes-for-implementer pins this split: "descriptions live in YAML; severities live on TaskClass; both are validated, in different layers."

### F-CON-5 (BLOCK) — `bench/__init__.py` "may also need to exist" contradicts HARDENED S2-01

The original Notes-for-implementer line 222: `bench/__init__.py` may also need to exist so `bench.vuln_remediation` is importable; the S2-01 loader's `sys.path` prep contract should already handle this — verify before adding extra `__init__.py`s. HARDENED S2-01 explicitly uses **PEP 420 implicit namespace packages** (no `__init__.py` files at all in `bench/` or `bench/{name}/`) — this is pinned in S2-01 line 39: "`bench/` becomes a PEP 420 implicit namespace package (no `__init__.py`)" and reaffirmed in S2-01 Validation notes line 32 (the doc-drift surfacing that `phase-arch-design.md` line 1159's `__init__.py`-bearing wording is wrong; PEP 420 implicit packages have NO `__init__.py`). An executor following the hedge would add `bench/__init__.py` and `bench/vuln-remediation/__init__.py`, which (a) breaks the PEP 420 contract; (b) the second file can't exist anyway because Python identifiers can't have hyphens (so `bench/vuln-remediation/__init__.py` would be an unimportable orphan). **Resolution:** Notes-for-implementer rewritten to hard-ban both: "Do NOT create `bench/__init__.py`. Do NOT create `bench/vuln-remediation/__init__.py`. S2-01's loader uses PEP 420 implicit namespace packages + `spec_from_file_location` for the hyphenated leaf — both `__init__.py` files would break that contract." Files-to-touch table updated: `bench/vuln-remediation/__init__.py` row removed.

### F-CON-6 (BLOCK) — Runner-internal always-block codes are missing from the required taxonomy set

ADR-0004 §Tradeoffs (`Codes shared across task classes ... must be replicated per task class`) requires the runner-internal always-block codes to appear in **every** task class's `failure_modes.yaml`. Notes-for-implementer line 220 names them: `sut.exception`, `sut.timeout`, `rubric.timeout`, `rubric.unknown_failure_mode`, `rubric.unknown_breakdown_key`, `rubric.malformed_output`. But the original AC's `REQUIRED_BLOCK_CODES` set (from §TDD lines 97-105) lists only ADR-0004 §Consequences' eight initial codes — three runner-internal codes are missing: `sut.timeout`, `rubric.unknown_breakdown_key`, `rubric.malformed_output`. An executor would ship a YAML that the runner immediately blows up on: a single SUT subprocess timeout in production would emit `sut.timeout` → resolver sees unknown code → falls back to `rubric.unknown_failure_mode` (block) → operator gets a misleading error. **Resolution:** AC-5 rewritten to require the union of ADR-0004 §Consequences's initial taxonomy + the three runner-internal always-block codes (11 block codes total). §TDD's `REQUIRED_BLOCK_CODES` set updated to match. ADR-0008's `rubric.unknown_breakdown_key` reference pinned in §References.

### F-CON-7 (BLOCK) — `rubric.py` stub decision is left to "whichever the team's review velocity supports"

The original §Out of scope line 210 says: `if S5-02 hasn't merged, ship `rubric.py` as a minimal stub (`class VulnRemediationRubric: def score(self, *_): raise NotImplementedError`). The stub is replaced byte-for-byte in S5-02 and must not be merged to main without S5-02 landing in the same train.` Notes-for-implementer line 221 then says: `Pick whichever the team's review velocity supports.` This pushes a load-bearing merge-ordering decision onto the implementer at code-write time — exactly the unspecified-decision flavor the validator catches. The choice has consequences: (a) ship-the-stub keeps S5-01 independently mergeable, lets S5-02 land later; (b) co-merge-S5-02 ties two stories' merge windows. **Resolution:** Decision pinned to (a) — ship a minimal stub in this story. Rationale: it makes S5-01 independently mergeable, isolates merge-blast-radius, mirrors the "incremental scaffolds" discipline used in S1-01 / S1-04 / S2-01. Note-for-implementer rewritten as a hard instruction with the exact stub body (`class VulnRemediationRubric:\n    def score(self, case, harness_output): raise NotImplementedError("S5-02 replaces this body")`). Files-to-touch table gets a new row: `bench/vuln-remediation/rubric.py` (this story; minimal stub). §Out-of-scope clarifies "S5-02 replaces the body" with the stub-replacement contract.

### F-CON-8 (HARDEN) — `Depends on:` line undersells the HARDENED loader contract

The original `Depends on: S4-02 (codegenie eval run subcommand exists end-to-end on a stub bench), and transitively the Step 1 contracts` does not name S1-03 (registry decorator) or S2-01 (loader) — both of which the story's implementation outline depends on **at the kwarg-name level**. F-CON-1 / F-CON-3 are the visible consequence. **Resolution:** Depends-on line rewritten to: `S1-03 (HARDENED `@register_task_class` kwarg surface: `breakdown_keys`, `failure_mode_taxonomy`, `bench_path`, `min_cases_for_promotion`), S2-01 (HARDENED `load_task_class` is the import surface for tests; hyphen→underscore translation lives there), S1-04 (`Rubric` Protocol — the stub rubric class must satisfy it structurally), S4-02 (CLI exit-code mapping the typed errors feed)`.

### F-CON-9 (HARDEN) — `Status:` line format does not match HARDENED siblings

S1-03's HARDENED status line reads `**Status:** HARDENED`. S4-05's reads `**Status:** HARDENED (phase-story-validator, 2026-06-01)`. **Resolution:** Status line updated to `**Status:** HARDENED (phase-story-validator, 2026-06-04)`.

### F-CON-10 (NIT) — `bench.vuln_remediation` vs `bench/vuln-remediation/` distinction is mentioned but not pinned

The story uses both forms but doesn't say *why* they differ. **Resolution:** Notes-for-implementer adds a one-paragraph pin: "On-disk: `bench/vuln-remediation/` (hyphen — Python source isn't valid in a hyphenated package name, but S2-01's `spec_from_file_location` loader handles the bridge). In code: `bench.vuln_remediation.X` (underscore — Python identifier discipline). The two forms are NOT alternatives; both must be used in their respective contexts. S2-01 HARDENED AC-9 owns the translation."

---

## Critic: Coverage (lens: do the ACs collectively guarantee the goal? edge cases?)

### F-COV-1 (BLOCK) — Subsumed by F-CON-4

`failure_mode_descriptions` is not a runtime contract; §TDD assertion dropped; description-non-emptiness asserted via direct YAML read.

### F-COV-2 (BLOCK) — Subsumed by F-CON-6

Runner-internal always-block codes added to required set.

### F-COV-3 (HARDEN) — No AC for `failure_modes.yaml` schema shape

The original story §TDD parses the YAML implicitly via the loader but never asserts the YAML schema itself: top-level is a `dict[str, dict[str, str]]`; entry keys are exactly `{severity, description}` (no extra keys; ADR-0004 §Decision pins these two only); `severity` value is exactly one of `{block, warn, info}`; `description` is `str` and non-empty; YAML is `yaml.safe_load` parseable. An executor could ship a YAML with `{code: {severity, description, owner, sla}}` — the loader would parse, the runtime taxonomy would carry only `severity`, the extra `owner`/`sla` would silently survive in the file, and a future reader would assume they're load-bearing. **Resolution:** AC-7 pins the YAML schema with two parametrized tests: `test_failure_modes_yaml_top_level_is_dict_of_dicts_with_exactly_two_keys` (rejects extra keys per entry, asserting `set(entry) == {"severity", "description"}`) and `test_failure_modes_yaml_severity_values_are_in_literal_set` (asserting `entry["severity"] in {"block", "warn", "info"}` for every entry). Plus a `test_failure_modes_yaml_loads_via_safe_load_only` that monkeypatches `yaml.load` to raise and asserts the read still works (safe_load path is taken).

### F-COV-4 (HARDEN) — No AC for the `cve.dropped` BreakdownKey vs `validator.cve_not_dropped` FailureMode symmetry

The story's BreakdownKey includes `CVE_DROPPED = "cve.dropped"` (a positive scoring component) and the taxonomy includes `validator.cve_not_dropped` (the negative-outcome failure code). These two MUST stay in sync semantically — a rubric scoring against `breakdown["cve.dropped"]` and emitting `failure_modes=("validator.cve_not_dropped",)` for the same case is internally consistent only if the breakdown-key and failure-code naming reflect inverse semantics. **Resolution:** AC-3 + AC-5 + §TDD comment pin the four breakdown/failure-mode pairs that S5-02's rubric will use: `cve.dropped` ↔ `validator.cve_not_dropped`; `validator.build_passed` ↔ `validator.build_failed`; `validator.tests_passed` ↔ `validator.tests_failed`; `recipe.applied` ↔ `recipe.semantic_drift`. Documentation only — does NOT force a test; the rubric (S5-02) owns the score↔failure inversion.

### F-COV-5 (HARDEN) — No AC for double-import cache (sys.modules) behavior

The original AC `Importing bench.vuln_remediation.registration once (in a fresh registry) registers the task class; a second import in the same test process does not raise TaskClassAlreadyRegistered` is stated but no test pins it. Per F-CON-3 the test surface is `load_task_class`, not `importlib.import_module`. HARDENED S2-01 AC-6 owns this assertion for the loader generically; the question is whether this story's bench-fixture-specific test should re-assert. **Resolution:** AC-6 added: a single `test_double_load_task_class_does_not_raise_and_returns_same_taskclass` that calls `load_task_class("vuln-remediation", ...)` twice and asserts (a) no `TaskClassAlreadyRegistered`; (b) `tc1 is tc2`; (c) `tc1 is fresh_registry.get("vuln-remediation")`. Defense-in-depth: the bench-fixture-specific test catches a regression that the loader-generic test in S2-01 misses if `bench/vuln-remediation/`'s registration.py has a quirk that re-fires the decorator (e.g., a `for _ in range(2)` mistakenly wrapping the `register_task_class(...)(...)` call).

### F-COV-6 (NIT) — `min_cases_for_promotion["silver"]` rollback path is described but not asserted

Notes-for-implementer line 219 explains the silver-fallback (drop silver if S5-04 slips). But there is no AC asserting the *current* state contains `"silver": 25`. **Resolution:** AC-2 pins the literal dict `{"bronze": 10, "silver": 25}` via `assert tc.min_cases_for_promotion == MappingProxyType({"bronze": 10, "silver": 25})` (mapping-proxy per S1-03 AC-9a). Notes-for-implementer keeps the fallback instruction with the explicit AC change required ("if you drop `silver`, also update AC-2 in this story to remove `silver`").

---

## Critic: Test-Quality (lens: would the TDD plan catch an obviously wrong implementation? thin tests?)

### F-TQ-1 (BLOCK) — `tc.breakdown_keys == frozenset(m.value for m in BreakdownKey)` is tautological

The original `test_breakdown_keys_loaded_into_task_class` asserts:

```python
assert tc.breakdown_keys == frozenset(m.value for m in BreakdownKey)
```

A mutant implementation where `BreakdownKey` has zero members AND `tc.breakdown_keys = frozenset()` would pass this test. A more subtle mutant: the loader reads only the *first* `BreakdownKey` member's value (skipping the rest); both sides of the equality contract on the same empty/partial set. **Resolution:** §TDD rewritten with two layered assertions: (a) `assert tc.breakdown_keys == frozenset({"validator.build_passed", "validator.tests_passed", "cve.dropped", "recipe.applied"})` — pins the **literal** expected value set so a mutant that skips members fails loudly; (b) `assert len(tc.breakdown_keys) == 4` — guards against silent extension that the literal-set check would miss only if both sides drift identically. Adversarial mutant catalog (Notes-for-implementer): constant-empty-set, single-member-only, all-members-lowercased.

### F-TQ-2 (HARDEN) — No test pins `MappingProxyType` immutability on `tc.failure_mode_taxonomy`

S1-03 AC-9 pins `failure_mode_taxonomy` is normalized to `MappingProxyType` at decoration time. The S5-01 path goes through the decorator, so the same immutability holds — but the original §TDD never asserts it. A regression in S1-03 that drops the normalization would only fail S1-03's tests; this story should pin it locally too (defense-in-depth, per the same pattern S1-03 itself uses for cross-story discipline). **Resolution:** AC-5 + §TDD adds: `assert isinstance(tc.failure_mode_taxonomy, types.MappingProxyType)`; `with pytest.raises(TypeError): tc.failure_mode_taxonomy["new.code"] = "block"`. Two-line addition; high mutant-kill yield.

### F-TQ-3 (HARDEN) — BreakdownKey ast.Constant-value discipline is asserted by fence-CI #5 (S7-01) but not by this story

The original AC `every member value is a literal ast.Constant string (no f"...", no prefix + suffix)` describes the fence-CI #5 invariant (S7-01) but neither asserts it nor explicitly defers it. **Resolution:** AC-3 marked `(asserted by fence-CI #5 in S7-01)` and a one-line local test `test_breakdown_key_values_are_ast_constant_strings` ASTs `bench/vuln-remediation/breakdown_keys.py` and asserts every `Assign.value` inside `class BreakdownKey(StrEnum)` is `ast.Constant`. Defense-in-depth: the local test fires *before* the fence-CI step in a typical PR pipeline, catching the violation in the bench-author's IDE pytest run.

### F-TQ-4 (HARDEN) — No test pins the YAML *structure* (parses-via-safe-load + flat-dict + entry schema)

Subsumed by F-COV-3.

### F-TQ-5 (HARDEN) — No test for "decorator does not transform the rubric class"

S1-03 AC-5 pins `decorated_cls is OriginalClass` — the decorator returns the class unmodified. This story's imperative form `register_task_class(...)(VulnRemediationRubric)` returns the same class. An AC pinning `from bench.vuln_remediation.rubric import VulnRemediationRubric as RubricCls; assert fresh_registry.get("vuln-remediation").rubric_class is RubricCls` guards against a regression that wraps the rubric class with a side-effecting proxy. **Resolution:** AC-1 + §TDD adds `test_registered_rubric_class_is_imported_class_unmodified` asserting `is`-identity between the imported `VulnRemediationRubric` and `tc.rubric_class`.

### F-TQ-6 (HARDEN) — No test for `tc.bench_path` being the absolute resolved directory

The original story sets `bench_path=Path(__file__).parent` in registration.py. The loader, called as `load_task_class("vuln-remediation", bench_root=tmp_path / "bench")`, will see this resolved differently per test setup. **Resolution:** AC-2 adds `assert tc.bench_path == (bench_root / "vuln-remediation").resolve()`. Pins the resolved-absolute discipline (matches S2-01 AC-13's symlink-resolution AC).

### F-TQ-7 (HARDEN) — Substring-ban test only walks the static enum; runtime `tc.breakdown_keys` should also be walked

§TDD's `test_breakdown_key_strenum_passes_substring_ban` walks `BreakdownKey` members. But the loader-produced `tc.breakdown_keys` could (under a hypothetical mutant) inject a non-StrEnum-derived key. **Resolution:** AC-4 adds the runtime-side check: `for v in tc.breakdown_keys: for banned in BANNED_SUBSTRINGS: assert banned not in v`. Defense-in-depth — the static check is already there; this catches a loader-injected drift the static check would miss.

### F-TQ-8 (HARDEN) — No test that confirms `failure_mode_taxonomy` excludes runtime-only keys like `description`

If a regression in the YAML→taxonomy projection accidentally includes the `description` field in the `failure_mode_taxonomy` mapping (e.g., `{code: {severity: "block", description: "..."}}` instead of `{code: "block"}`), the runtime contract breaks (`Literal["block","warn","info"]` is the value type, not a dict). **Resolution:** AC-5 + §TDD adds `for code, sev in tc.failure_mode_taxonomy.items(): assert isinstance(sev, str); assert sev in {"block", "warn", "info"}`. Three-line addition.

### F-TQ-9 (NIT) — `BANNED_SUBSTRINGS` is duplicated between this story's tests and Phase 5 ADR-0014

The static-introspection test in S1-05 (per S1-05 AC) defines `BANNED_SUBSTRINGS` from a central source. This story redefines them. The duplication is acceptable (single line; cheap), but a comment pointing at the shared source would help future readers. **Resolution:** §TDD adds an inline comment `# BANNED_SUBSTRINGS mirrors Phase 5 ADR-0014 + ADR-0008 §Decision; any change here must amend both ADRs.`

### F-TQ-10 (NIT) — Adversarial mutant catalog not stated

The validator's editor template suggests stating the adversarial-mutant catalog so the executor (and reviewers) can see which specific wrong implementations the tests are designed to kill. **Resolution:** Notes-for-implementer adds a §Adversarial mutant catalog block with five named mutants the §TDD plan kills: (a) empty BreakdownKey, (b) BreakdownKey value list of length 1, (c) failure_modes.yaml with `severity: "fatal"` (out of Literal), (d) failure_modes.yaml entry with extra `owner` key, (e) registration.py decorating a marker class instead of the rubric class.

---

## Critic: Design-Patterns (lens: will the implementation be easy to extend by addition?)

### F-DP-1 (HARDEN) — YAML→taxonomy projection should be a named helper, testable in isolation

The original §Implementation outline embeds the YAML parse + projection inline in `registration.py`:

```python
_taxonomy_raw = yaml.safe_load((_HERE / "failure_modes.yaml").read_text())
_TAXONOMY = {code: spec["severity"] for code, spec in _taxonomy_raw.items()}
```

Today there are two consumers (vuln-remediation and migration-chainguard-distroless — both ship `failure_modes.yaml`); the third (Phase 15 recipe-authoring) is the rule-of-three trigger to extract a shared kernel. Today's right move per Rule 2 + the S1-03 precedent (line 32: "do not extract a shared base today, per signal_kinds.py:16-29 explicit YAGNI") is to extract a *file-local* private helper `_severity_taxonomy_from_yaml(path: Path) -> Mapping[str, Literal["block", "warn", "info"]]` so the projection is testable in isolation, while explicitly **not** lifting it into the harness package (`src/codegenie/eval/`). The lift trigger is rule-of-three at Phase 15. **Resolution:** §Implementation outline pins the helper signature + its placement (registration.py-local, not a shared module). AC-7 references it. Notes-for-implementer documents the extension path: "When Phase 15's task class lands and is the third consumer of `failure_modes.yaml`, the rule-of-three triggers extraction into `src/codegenie/eval/loader.py` as `_load_failure_mode_taxonomy(bench_path) -> Mapping[...]`. The arch already names this function (line 564); the lift is mechanical when the third caller exists."

### F-DP-2 (NIT) — `_MIN_CASES_FOR_PROMOTION` Final constant elevates the silver-fallback edit to a one-line data change

The Notes-for-implementer fallback ("drop silver if S5-04 slips") is currently a "go find the dict literal in the decorator call" instruction. If `min_cases_for_promotion={"bronze": 10, "silver": 25}` were lifted to a module-level `_MIN_CASES_FOR_PROMOTION: Final[Mapping[str, int]] = MappingProxyType({"bronze": 10, "silver": 25})`, the fallback edit is one constant line. Not promoted to AC (Rule 2 — one literal today; the cost of a constant is small but the benefit is small too). **Resolution:** Surfaced in Notes-for-implementer as an optional cleanup; not an AC.

### F-DP-3 (NIT) — Open/Closed seam at `bench/{task-class}/` directory contract is implicit

Phase 7 will add `bench/migration-chainguard-distroless/{registration.py, breakdown_keys.py, failure_modes.yaml}` and zero edits to `src/codegenie/eval/`. The Open/Closed seam is the directory contract. **Resolution:** Notes-for-implementer adds: "Extension-by-addition discipline: Phase 7 ships `bench/migration-chainguard-distroless/` by copying this story's pattern verbatim — three files + a stub rubric. Zero edits to `src/codegenie/eval/` should be required. If Phase 7 needs a kernel edit, that's a contract surface bug to fix here, not there."

---

## Researcher

No `NEEDS RESEARCH` items. Every pattern is precedented in this repo or in the HARDENED upstream stories (S1-03, S1-04, S2-01).

---

## Edits applied to the story

1. **Status line:** `Ready` → `HARDENED (phase-story-validator, 2026-06-04)`.
2. **Depends-on:** rewritten to name S1-03, S2-01, S1-04 explicitly (F-CON-8).
3. **ADRs honored:** added ADR-0008's `rubric.unknown_breakdown_key` reference and Phase 5 ADR-0014's substring-ban-source mention.
4. **Validation notes section** appended before Context with the full change log (this report).
5. **Acceptance criteria** renumbered to AC-1..AC-8 with the new schema-validation, runtime-immutability, and rubric-identity ACs (F-CON-4, F-CON-6, F-COV-3, F-COV-5, F-COV-6, F-TQ-1, F-TQ-2, F-TQ-5, F-TQ-6, F-TQ-7, F-TQ-8).
6. **Implementation outline §3 + §5 rewritten** to (a) drop the marker class; (b) use the imperative-application form `register_task_class(...)(VulnRemediationRubric)` with correct kwarg names; (c) pin the YAML→taxonomy projection as a named helper; (d) hard-pin the rubric.py stub body.
7. **§TDD plan** rewritten to use `load_task_class` instead of `importlib.import_module`; relocated to `tests/unit/eval/test_bench_vuln_registration.py`; added the additional tests for YAML schema, immutability, rubric-identity, BreakdownKey AST literals, runtime substring ban, and double-load cache (F-CON-3, F-COV-3, F-COV-5, F-TQ-1..F-TQ-8).
8. **Files to touch:** added `bench/vuln-remediation/rubric.py` (stub); removed `bench/vuln-remediation/__init__.py` (F-CON-5).
9. **Out of scope:** S5-02 stub-replacement contract pinned.
10. **Notes-for-implementer:** rewritten — bench-`__init__.py` hard-banned (F-CON-5); rubric.py stub decision pinned to (a) (F-CON-7); hyphen-vs-underscore pin added (F-CON-10); adversarial mutant catalog added (F-TQ-10); extension-path note for rule-of-three at Phase 15 (F-DP-1); `_MIN_CASES_FOR_PROMOTION` constant optionality noted (F-DP-2); Open/Closed seam at directory contract documented (F-DP-3).
11. **Goal:** sharpened to name the imperative-application pattern + the three-file contract + the loader as the test import surface, not standard importlib.

---

## Verdict

**HARDENED.** Goal preserved; every BLOCK / HARDEN edit applies in place. The story is ready for the executor.

Conflict ledger:

| Source | Resolution |
|---|---|
| F-CON-1 (decorator kwarg-name drift) vs original §Implementation outline | S1-03 HARDENED wins; story rewrites to `breakdown_keys=`, `failure_mode_taxonomy=`, imperative-application form. |
| F-CON-2 (marker class) vs `_VulnRemediationRegistration: pass` example | S1-03 + S1-04 Protocol contract wins; marker pattern is forbidden in Notes. |
| F-CON-3 (importlib.import_module) vs hyphenated on-disk dir | S2-01 HARDENED wins; tests go through `load_task_class`. |
| F-CON-4 (`failure_mode_descriptions` field) vs S1-03 AC-2 six-field pin | S1-03 wins; descriptions stay in YAML, validated by fence-CI #6 + direct YAML-read test. |
| F-CON-5 (`bench/__init__.py` hedge) vs S2-01 PEP 420 contract | S2-01 wins; both `__init__.py` files hard-banned. |
| F-CON-6 (runner-internal codes omitted) vs ADR-0004 §Tradeoffs replication clause | ADR wins; three additional always-block codes added to required set. |
| F-CON-7 (rubric.py decision punted) vs implementer-action-cost | Pinned to (a) ship-the-stub; rationale documented. |
| F-DP-1 (helper-extract) vs Rule 2 YAGNI | File-local private helper today; lift at rule-of-three (Phase 15 trigger documented). |
