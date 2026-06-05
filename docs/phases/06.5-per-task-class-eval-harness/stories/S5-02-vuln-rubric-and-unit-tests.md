# Story S5-02 — vuln-remediation rubric (subprocess entrypoint) + bench-author unit tests

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** HARDENED (phase-story-validator, 2026-06-04)
**Effort:** M
**Depends on:** S5-01 HARDENED (ships the `VulnRemediationRubric` stub class, `BreakdownKey` StrEnum with exactly four members, `failure_modes.yaml` with 11 block + 3 warn + 2 info codes; S5-02 replaces the stub's `score` method body byte-for-byte), S1-02 HARDENED (`BenchScore` / `BenchCase` / `FailureMode` Pydantic wire-type shapes — `score: float [0,1]`, `wall_clock_ms: int >= 0`, `breakdown: dict[str, float]` typed-at-the-edge, `failure_modes: tuple[FailureMode, ...]`, `FailureMode.severity: Literal["block","warn","info"]`, `FailureMode.detail: str | None`), S1-04 (`Rubric` Protocol — class with one `score(self, case, harness_output) -> BenchScore` method; mypy --strict structural check), S2-01 HARDENED (`load_task_class` + autouse conftest is the import surface for the hyphenated `bench/vuln-remediation/` directory). Transitively: S3-03 (the runner that subprocess-invokes this rubric; produces the envelope shape).
**ADRs honored:** ADR-0001 (subprocess entrypoint; `if __name__ == "__main__"` JSON-in/JSON-out; ≤ 60 s budget; SCRUBBED_ENV mirrors Phase 5 ADR-0012; in-process bench-author tests bypass the boundary), ADR-0004 (every emitted `failure_mode.code` is constrained by the taxonomy; unknown codes resolve at the runner to `rubric.unknown_failure_mode`; severities are the rubric's responsibility at emit time, taken from `failure_modes.yaml`), ADR-0008 (every emitted `BenchScore.breakdown` key must be a `BreakdownKey` *value*; runner rejects unknown keys as `rubric.unknown_breakdown_key`), Phase 5 ADR-0012 (env-allowlist `SCRUBBED_ENV` pattern reused for the subprocess invocation), Phase 5 ADR-0014 (banned-substring source-of-truth for `breakdown` keys — shared with ADR-0008)

## Validation notes

Validated: 2026-06-04
Verdict: HARDENED
Findings addressed: 23 total — 7 blocks, 13 hardens, 3 nits

Changes applied (full audit log: `_validation/S5-02-vuln-rubric-and-unit-tests.md`):

- **Status line** updated to `HARDENED (phase-story-validator, 2026-06-04)` (F-CON-9).
- **Depends-on** rewritten to name S5-01 HARDENED, S1-02 HARDENED (wire-type shapes), S1-04 (Rubric Protocol), S2-01 HARDENED (loader is the import surface) (F-CON-8).
- **AC-1 dual-surface contract pinned (BLOCK):** S5-01 HARDENED ships the rubric as a `class VulnRemediationRubric` to satisfy the S1-04 `Rubric` Protocol structural check. The original TDD plan's `from bench.vuln_remediation.rubric import score` would fail because no module-level `score` exists in the S5-01 stub. AC-1 + Implementation outline §2/§3 now pin the dual surface: a module-level pure function `score(case, harness_output) -> BenchScore` (used by both the in-process tests and the `__main__` entrypoint directly) PLUS the `VulnRemediationRubric` class whose `score(self, case, harness_output)` method delegates `return score(case, harness_output)`. The class is the Protocol-conformance surface (S1-04, S5-01); the function is the test/entrypoint surface (this story). S5-01's stub body is replaced byte-for-byte (F-CON-1).
- **`bench/vuln-remediation/tests/__init__.py` hard-banned (BLOCK):** the original Implementation outline §4 creates this file as an "empty package marker." That directly contradicts S5-01 F-CON-5's hard ban: S2-01 HARDENED uses PEP 420 implicit namespace packages — **no `__init__.py` files anywhere under `bench/`**. Tests discovery does not need it (pytest's rootdir-based discovery + a sibling `conftest.py` is sufficient). Implementation outline §4 rewritten to ship `bench/vuln-remediation/tests/conftest.py` instead — an autouse `load_task_class("vuln-remediation", bench_root=...)` fixture that registers `bench.vuln_remediation.*` in sys.modules so `from bench.vuln_remediation.rubric import score` resolves. Files-to-touch row updated (F-CON-2).
- **Bench-author conftest is the import bridge (BLOCK):** without the conftest, standard Python `from bench.vuln_remediation.rubric import score` cannot resolve the hyphenated on-disk directory under standard Python import machinery (same issue as S5-01 F-CON-3). The conftest calls `load_task_class("vuln-remediation", bench_root=REPO_ROOT / "bench")` *before* any test imports, populating sys.modules under the underscore key via `spec_from_file_location`. Implementation outline §4 pins the conftest body; AC-1 pins the import path resolves; Notes-for-implementer documents why the conftest exists and what would break without it (F-CON-3).
- **Semantic-symmetry inversions pinned as ACs (BLOCK):** S5-01 HARDENED documented the four breakdown↔failure-mode pairs (`cve.dropped` ↔ `validator.cve_not_dropped`, `validator.build_passed` ↔ `validator.build_failed`, `validator.tests_passed` ↔ `validator.tests_failed`, `recipe.applied` ↔ `recipe.semantic_drift`) but explicitly deferred enforcement to this story ("the rubric (S5-02) owns the score↔failure inversion"). The original AC-4 only tested two inversions (`validator.tests_failed`, `validator.cve_not_dropped`); a wrong implementation that emitted `rubric.unknown_failure_mode` for the other two would pass the existing tests. New AC-5 explicitly pins all four inversions via a parametrized test (`test_each_falsy_breakdown_condition_emits_its_paired_failure_code`) (F-COV-1).
- **Static AST ban on non-determinism (BLOCK):** the Notes-for-implementer line on determinism ("no `time.time()`, no `random.random()`, no `os.environ` reads, no `uuid.uuid4()`") is not enforceable — a contributor adding `time.time()` to the rubric would silently break the audit chain's byte-stability and cause S5-06's cache hit-rate to fall below 95% with no surfaced cause. New AC-9 + `test_rubric_module_has_no_nondeterministic_imports_or_calls` ASTs `rubric.py` and rejects: `import time` / `time.X`, `import random` / `random.X`, `import uuid` / `uuid.X`, `os.environ` access, `datetime.now(`, `datetime.utcnow(`. Mirrors S5-01's `test_breakdown_key_values_are_ast_constant_strings` pattern (F-COV-2).
- **Subprocess SCRUBBED_ENV ACs pinned (BLOCK):** the original AC-3 only asserted "completes within 60 wall-clock seconds." ADR-0001 §Decision and Phase 5 ADR-0012 require: `ANTHROPIC_API_KEY`, `AWS_*`, `HOME`, `USER` all absent inside the rubric subprocess. The original integration test could pass while leaving any of these reachable. New AC-3 expanded: integration test sets each env var to a sentinel value in the *parent* process, runs the rubric subprocess with `SCRUBBED_ENV`, and asserts via the rubric's debug-emit-on-stderr that `os.environ.get("ANTHROPIC_API_KEY")` is `None`, `os.environ.get("AWS_ACCESS_KEY_ID")` is `None`, `os.environ.get("HOME")` is `None`, `os.environ.get("USER")` is `None`. Mirrors `tests/adv/test_rubric_subprocess_env_scrubbed.py` from arch line 296 (F-COV-7).
- **Malformed-JSON exit-code AC (BLOCK):** ADR-0001 §Consequences pins `rubric.malformed_output` as the runner's reaction to a rubric non-zero exit. The original story does not pin that the rubric's `__main__` exits non-zero on bad input — it could `try/except` and emit a passing `BenchScore`. New AC-2 + `test_main_exits_nonzero_on_malformed_envelope_json` feeds the subprocess `b"not-json"` on stdin and asserts the process exits with code != 0 (F-COV-8).
- **Test assertions tightened against trivial mutants (HARDEN):**
  - AC-4(a) `result.score >= 0.95` → `result.score == 1.0` (kills a "score = 0.95" hardcoded-return mutant) (F-TQ-1).
  - AC-4(a) `all(fm.severity != "block")` → `result.failure_modes == ()` (kills "emit info-severity on full-pass" mutant) (F-TQ-2).
  - AC-4(b)/(c) `"X" in {fm.code ...}` → exact set equality `{fm.code for fm in result.failure_modes} == {"X"}` (kills "also emit a spurious failure" mutant) (F-TQ-3).
  - AC-4(d) `set(result.breakdown.keys()) <= declared` → `== declared` (kills "ship only a subset" mutant; Implementation outline §2 already produces all four keys, so equality is the right contract) (F-TQ-4).
- **Mean-formula mutation test (HARDEN):** new `test_half_pass_yields_score_exactly_half_kills_min_max_mutants` — for `harness_output` with exactly 2 of 4 sub-conditions true, asserts `result.score == 0.5`. Kills mutants where `mean` is replaced by `min` (0.0), `max` (1.0), `len(failing)` (2.0), or `sum` (2.0) (F-TQ-5).
- **BenchCase-invariance property test (HARDEN):** new `test_score_invariant_under_unrelated_case_field_mutations` — the rubric reads `harness_output`, not `case.*` (Notes-for-implementer line 233 is explicit). For a fixed harness_output, mutating `case.case_id`, `case.difficulty`, `case.disposition` must not change the resulting `BenchScore.model_dump_json()`. Catches accidental reads of `case.*` that would couple the rubric to case shape and break cache hit-rate (F-TQ-6).
- **Canonical `failure_modes` ordering AC (HARDEN):** for the determinism contract (audit chain byte-stability), the `failure_modes` tuple ordering must be canonical for any given falsy-condition set. New AC-7 + `test_failure_modes_tuple_is_sorted_by_code` pins lexicographic ordering by `fm.code`. Without this, two equivalent runs could emit `(A, B)` vs `(B, A)` → `model_dump_json` bytes differ → cache miss + audit chain divergence. Implementation outline §2 amended to sort the emit set (F-COV-3).
- **Missing-harness-key behavior pinned (HARDEN):** new AC-8 + `test_missing_harness_output_key_propagates_keyerror` feeds `harness_output = {"validator": {}, "recipe": {"applied": True}}` and asserts `pytest.raises(KeyError)`. Pins the "fail loud" behavior Notes-for-implementer line 234 already documents but no test enforces. A defensive `harness_output.get("validator", {}).get("build_passed", False)` implementation would silently downgrade a missing key to `False` (failing run) instead of surfacing the contract violation (F-COV-4).
- **Exactly six unit tests (HARDEN):** AC-4 changed from "at least 5" to "exactly 6 (named):" pinning the test set so the executor cannot under-cover. The six tests cover the original five plus the deterministic-replay one already in §TDD plan (F-COV-9).
- **Severities hardcoded; YAML consistency test (HARDEN, F-DP-1):** the Refactor section's instruction to "lift the YAML severity load to module import time (single I/O); cache as `_TAXONOMY`" creates a second YAML reader (S5-01's `registration.py` already has `_severity_taxonomy_from_yaml`). By end of Phase 6.5 this is the 4th YAML reader (S5-01 reg + this story's rubric + S6-01 migration reg + S6-03 migration rubric) — well past rule-of-three. **Pin a tighter alternative:** the rubric emits exactly four block codes (`validator.build_failed`, `validator.tests_failed`, `validator.cve_not_dropped`, `recipe.semantic_drift`), all known at bench-author time. Implementation outline §2 now declares `_SEVERITY_FOR_EMITTED_CODE: Final[Mapping[str, Literal["block","warn","info"]]]` hardcoded with these four → "block". A consistency test (`test_hardcoded_severities_match_failure_modes_yaml`) reads the YAML and asserts each hardcoded severity matches; YAML drift surfaces at PR time. Avoids brittle import-time I/O (cwd-relative path resolution under subprocess), avoids the second-loader rule-of-three trigger, and pins the load-bearing severity decision at the bench-author's source-of-truth. The rule-of-three lift (when the third task class lands in Phase 15) becomes a kernel `_load_failure_mode_taxonomy` in `src/codegenie/eval/loader.py` shared by the registration path; rubrics continue to hardcode their *emit-set* severities. Notes-for-implementer explains the tradeoff.
- **HarnessOutput envelope endorsement (HARDEN, F-DP-2):** the Refactor instruction "destructure with pydantic BaseModel for the envelope" is currently a Notes aside. Promoted to Implementation outline §3 as a concrete `_HarnessOutput(BaseModel, frozen=True, extra="forbid")` with `validator: _ValidatorSignals` and `recipe: _RecipeSignals` sub-models. This (a) gives mypy --strict a real shape to verify; (b) surfaces SUT contract drift at the envelope-parse layer instead of at `KeyError` deep in `score()`; (c) makes the contract between Phase 6's `VulnRemediationSut.run_case` and the rubric explicit and testable. Pinned in Notes-for-implementer as a Phase 6→Phase 6.5 contract-surface decision. Local-only (not a shared model) per Rule 2 — Phase 7's migration rubric will have a different SUT contract.
- **Adversarial mutant catalog added (HARDEN, F-TQ-7):** Notes-for-implementer surfaces the six named mutants this §TDD kills, mirroring S5-01's pattern.
- **`Files to touch` aligned:** `bench/vuln-remediation/tests/__init__.py` row dropped; `bench/vuln-remediation/tests/conftest.py` row added.
- **ADRs honored expanded** to name Phase 5 ADR-0012 (env-allowlist source-of-truth for SCRUBBED_ENV) and Phase 5 ADR-0014 (substring-ban source-of-truth shared with ADR-0008).

Design endorsements (no edit; surfaced in Notes-for-implementer):
- **Functional-core / imperative-shell** — already followed (pure `score()` + `__main__` shell). Reaffirmed.
- **Open/Closed seam at `bench/{task-class}/rubric.py`** — Phase 7's migration rubric copies this pattern verbatim. Reaffirmed.
- **Strategy pattern for condition→failure-code mapping** — `_CONDITION_FAILURE_PAIRS: Final[tuple[tuple[BreakdownKey, str], ...]]` keeps the rubric loop-driven and Open/Closed at the inversion table.

No `NEEDS RESEARCH` items — every pattern is precedented in this repo (Phase 5 ADR-0012 env-allowlist test discipline, S5-01 HARDENED AST-walk pattern, S1-02 boundary-inclusivity test pattern).

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

- [ ] **AC-1 (dual-surface contract: module-level `score` + Protocol-conforming class).** `bench/vuln-remediation/rubric.py` defines BOTH (a) a module-level pure function `score(case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore` (used by in-process tests and the `__main__` entrypoint directly), AND (b) `class VulnRemediationRubric` whose `score(self, case, harness_output)` method body is exactly `return score(case, harness_output)`. The class is the S1-04 `Rubric` Protocol-conformance surface S5-01 registered against; the function is the test/entrypoint surface this story exercises. Test `test_class_score_method_delegates_to_module_level_score` asserts identity of the returned `BenchScore` instance under both call paths. The returned `BenchScore` is frozen, has `breakdown` keys drawn *exactly* from `BreakdownKey` values, and `failure_modes[*].code` values drawn exactly from the codes declared in `failure_modes.yaml`.

- [ ] **AC-2 (`__main__` entrypoint shape + non-zero exit on malformed input).** `rubric.py` has an `if __name__ == "__main__":` block that: reads `sys.stdin.buffer.read()`, parses it as JSON, validates into a typed envelope (`BenchCase` + `harness_output`) via the local `_HarnessOutput` Pydantic model, calls `score(...)`, writes the resulting `BenchScore` as JSON to `sys.stdout.buffer`, and exits 0 on success. On `json.JSONDecodeError` or `pydantic.ValidationError` the process exits non-zero (`sys.exit(2)`); test `test_main_exits_nonzero_on_malformed_envelope_json` feeds `b"not-json"` on stdin via `subprocess.run` and asserts `returncode != 0`. The rubric does **not** wrap `score(...)` in a broad `try/except` that would emit a misleadingly-passing `BenchScore` on internal failure (ADR-0001 §Consequences `rubric.malformed_output` is the runner's reaction to non-zero exit).

- [ ] **AC-3 (subprocess SCRUBBED_ENV + ≤60 s wall-clock).** `tests/integration/test_rubric_subprocess_vuln.py` runs `python bench/vuln-remediation/rubric.py` via `subprocess.run` with `env=SCRUBBED_ENV` (containing only `PYTHONPATH`, `PYTHONHASHSEED=0`, minimal `PATH` per ADR-0001 §Decision and Phase 5 ADR-0012 env-allowlist precedent) and `cwd=tempfile.TemporaryDirectory()`. The parent process sets `ANTHROPIC_API_KEY=parent-sentinel`, `AWS_ACCESS_KEY_ID=parent-sentinel`, `HOME=/parent-home`, `USER=parent-user` before spawn; the rubric writes a debug line to **stderr** (stdout is reserved for the `BenchScore`) reporting `os.environ.get("ANTHROPIC_API_KEY")`, `os.environ.get("AWS_ACCESS_KEY_ID")`, `os.environ.get("HOME")`, `os.environ.get("USER")`; the test asserts each is `None` in the rubric's environment. Wall-clock ≤ 60 s on a representative envelope (the four-positive-condition envelope from AC-4(a)).

- [ ] **AC-4 (six in-process unit tests — pinned, named, tightened).** `bench/vuln-remediation/tests/test_rubric_unit.py` exists and contains **exactly the following six** named tests (no fewer, no extras for this story's red→green window):
    - (a) `test_full_pass_yields_score_one_passed_true_no_failure_modes` — when all four sub-conditions are `True`: `result.passed is True`, `result.score == 1.0` (exact, not `>= 0.95`), `result.failure_modes == ()` (exact, not "no block-severity").
    - (b) `test_tests_failed_emits_exactly_validator_tests_failed_block` — when only `validator.tests_passed=False`: `result.passed is False`, `{fm.code for fm in result.failure_modes} == {"validator.tests_failed"}` (exact set), and that one `FailureMode.severity == "block"`.
    - (c) `test_cve_not_dropped_emits_exactly_validator_cve_not_dropped_block` — when only `validator.cve_dropped=False`: `{fm.code for fm in result.failure_modes} == {"validator.cve_not_dropped"}`, that one severity is `"block"`.
    - (d) `test_breakdown_keys_equal_full_declared_breakdown_key_set` — for any `harness_output`, `set(result.breakdown.keys()) == {m.value for m in BreakdownKey}` (exact equality, not subset — Implementation outline §2 produces all four keys always).
    - (e) `test_score_is_deterministic_under_repeated_invocation` — same inputs → byte-identical `model_dump_json()` across 10 invocations (tighter than the original 2).
    - (f) `test_rubric_emits_only_declared_failure_mode_codes_and_breakdown_keys` — sweep the five-row condition matrix from the original §TDD plan; every emitted `fm.code` ∈ YAML-declared codes; every breakdown key ∈ BreakdownKey values.

- [ ] **AC-5 (semantic-symmetry inversions — all four pairs enforced).** A parametrized test `test_each_falsy_breakdown_condition_emits_its_paired_failure_code` pins all four S5-01-documented inversions: `validator.build_passed=False` → `{"validator.build_failed"}` (block); `validator.tests_passed=False` → `{"validator.tests_failed"}` (block); `cve.dropped=False` → `{"validator.cve_not_dropped"}` (block); `recipe.applied=False` → `{"recipe.semantic_drift"}` (block). For each case, all other sub-conditions are `True` and the only emitted failure-code set is the singleton paired code. Kills the "emit `rubric.unknown_failure_mode` for everything" mutant that the original 2-of-4 coverage missed.

- [ ] **AC-6 (mean-formula + half-pass mutant kill).** `test_half_pass_yields_score_exactly_half_kills_min_max_mutants` — for `harness_output` with exactly 2 of the 4 sub-conditions `True` (e.g., `build_passed=True, tests_passed=False, cve_dropped=True, recipe.applied=False`): asserts `result.score == 0.5` (exact). Kills mean→min (0.0), mean→max (1.0), mean→sum (2.0), mean→len(failing) (2.0) mutants. `result.failure_modes` has exactly two entries with `{"validator.tests_failed", "recipe.semantic_drift"}` (defense-in-depth on AC-5).

- [ ] **AC-7 (canonical `failure_modes` tuple ordering).** `test_failure_modes_tuple_is_sorted_by_code` — for a multi-failure case (all four sub-conditions `False`), `result.failure_modes` is a `tuple` and `[fm.code for fm in result.failure_modes] == sorted([fm.code for fm in result.failure_modes])` (lexicographic by `code`). Required for `model_dump_json()` byte-stability across runs — without this, S5-06's cache-hit-rate test silently degrades and the audit chain diverges (ADR-0001 audit-comparability).

- [ ] **AC-8 (fail-loud on missing harness_output keys).** `test_missing_harness_output_key_propagates_keyerror` — feeds `harness_output = {"validator": {}, "recipe": {"applied": True}}` (missing `build_passed`, `tests_passed`, `cve_dropped`) and asserts `pytest.raises(KeyError)`. Pins the "let it propagate; runner records `rubric.malformed_output`" behavior Notes-for-implementer documents. A defensive `harness_output.get("validator", {}).get("build_passed", False)` would silently flip a contract violation into a failing-but-passing score.

- [ ] **AC-9 (static AST ban on non-determinism inside `rubric.py`).** `test_rubric_module_has_no_nondeterministic_imports_or_calls` parses `bench/vuln-remediation/rubric.py` via `ast.parse` and asserts: no `import time`/`from time`, no `import random`/`from random`, no `import uuid`/`from uuid`, no `os.environ` attribute access, no `datetime.now(`/`datetime.utcnow(`/`datetime.today(` calls. Mirrors S5-01's `test_breakdown_key_values_are_ast_constant_strings` AST-walk pattern. Required for `BenchScore.model_dump_json()` byte-stability (audit chain + S5-06 cache hit rate); without it, a contributor adding `wall_clock_ms = int((time.perf_counter() - t0) * 1000)` would break determinism with no surfaced cause until S5-06 fails N stories later. Note: the `__main__` block's `wall_clock_ms` reporting must use a deterministic fixed sentinel (e.g., `wall_clock_ms = 0`) — see Implementation outline §3.

- [ ] **AC-10 (hardcoded-severity ↔ YAML consistency).** `rubric.py` declares `_SEVERITY_FOR_EMITTED_CODE: Final[Mapping[str, Literal["block","warn","info"]]]` mapping the four codes the rubric can emit (`validator.build_failed`, `validator.tests_failed`, `validator.cve_not_dropped`, `recipe.semantic_drift`) to their severities (all `"block"`). Test `test_hardcoded_severities_match_failure_modes_yaml` reads `failure_modes.yaml` and asserts `yaml_taxonomy[code]["severity"] == _SEVERITY_FOR_EMITTED_CODE[code]` for each code. YAML drift (e.g., a contributor downgrading `validator.tests_failed` to `warn` without amending the rubric) surfaces at PR time. Avoids the brittle import-time YAML-read alternative the original Refactor section prescribed (see F-DP-1).

- [ ] **AC-11 (BenchCase-invariance — rubric reads `harness_output`, not `case`).** `test_score_invariant_under_unrelated_case_field_mutations` — fixes `harness_output` and mutates `case.case_id`, `case.difficulty`, `case.disposition` across three constructions; asserts all three produce the same `model_dump_json()`. Pins the "rubric scores from `harness_output` directly" Notes-for-implementer contract; catches accidental coupling that would break cache hit-rate.

- [ ] **AC-12 (no LLM SDK + fence-CI extension).** The rubric does **not** import any LLM SDK (`anthropic`, `openai`, `langchain`, `langgraph`, `transformers`, `torch`, `sentence-transformers`). `tests/unit/test_eval_package_imports_no_llm_sdk.py` is extended to walk `bench/**/rubric.py` (the existing walk currently only covers `src/codegenie/eval/**/*.py`); the extension is a single-glob addition. Test stays green for this story's rubric.

- [ ] **AC-13 (red→green pipeline, lint, typecheck, fence-CI).** Red test from §TDD plan exists, was committed at red marker, now green. `ruff check`, `ruff format --check`, `mypy --strict bench/vuln-remediation/rubric.py bench/vuln-remediation/tests/test_rubric_unit.py bench/vuln-remediation/tests/conftest.py tests/integration/test_rubric_subprocess_vuln.py`, and `pytest bench/vuln-remediation/tests/ tests/integration/test_rubric_subprocess_vuln.py` all pass. S7-01's fence-CI assertions (#4 literal name; #5 BreakdownKey substring ban; #6 taxonomy validity) all stay green on the modified files.

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
