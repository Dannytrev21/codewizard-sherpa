# Validation report — S5-02 vuln-remediation rubric + bench-author unit tests

**Validated:** 2026-07-25 (third pass; initial 2026-06-04, second pass 2026-06-05)
**Validator:** phase-story-validator
**Verdict:** HARDENED
**Findings this pass:** 9 total — 6 block, 3 harden

The story's *goal* (ship `bench/vuln-remediation/rubric.py` as a deterministic subprocess entrypoint that reads a JSON envelope and emits a `BenchScore`, covered by in-process bench-author unit tests) is sound and traces to phase ADR-0001 (subprocess isolation), ADR-0004 (failure-mode taxonomy), ADR-0008 (BreakdownKey substring ban). The first two validation passes did substantial work: 23 initial findings addressed across BLOCK/HARDEN/NIT lenses, including the dual-surface class-vs-function contract (F-CON-1), the `tests/__init__.py` hard-ban (F-CON-2), the semantic-symmetry inversion enforcement (F-COV-1), the AST-ban on non-determinism (F-COV-2), and the hardcoded-severity + YAML-consistency alternative (F-DP-1).

**But the 2026-06-05 second pass shipped a partial sync.** The Validation-notes bullets described extensive body edits that the editor never actually applied. This third pass forcibly reconciles: **body IS notes** now. The 9 findings this pass are all body-vs-notes drift bugs the second pass introduced or failed to fix. Every issue is patchable in place → **HARDENED**, not RESCUE.

Conflict-resolution priority applied: **Consistency > Coverage > Test-Quality > Design-Patterns**. The dominant lens this pass was Consistency (body-vs-notes sync). One Coverage finding (F-COV-SYNC-1) surfaced a load-bearing AC contradiction between AC-4's "exactly six" and the additional tests introduced by AC-1/AC-2/AC-5..AC-11 — reconciled by rewriting AC-4 as "six *core-condition* tests" with an explicit test-file routing table.

No `NEEDS RESEARCH` items — all fixes are precedented: PEP 420 (S5-01 F-CON-5), subprocess sentinel discipline (ADR-0001 arch line 296), hardcoded-severity mapping (F-DP-1 already resolved in the second-pass notes but not applied to §Green/§Refactor).

---

## Critic: Consistency (lens: does the story body agree with itself, and with the sibling HARDENED stories?)

### F-CON-SYNC-1 (BLOCK) — Implementation outline §4 contradicts Validation notes bullet #4 + S5-01 F-CON-5 hard-ban

The second-pass Validation-notes bullet #4 states: *"`bench/vuln-remediation/tests/__init__.py` hard-banned (BLOCK): the original Implementation outline §4 creates this file as an "empty package marker." That directly contradicts S5-01 F-CON-5's hard ban... Implementation outline §4 rewritten to ship `bench/vuln-remediation/tests/conftest.py` instead."*

But the actual body of Implementation outline §4 (line 122 pre-edit) still said: *"Implement `bench/vuln-remediation/tests/__init__.py` (empty package marker) so pytest discovers the tests when invoked from the repo root."*

An executor following the story literally would ship the `__init__.py` and (a) break the PEP 420 implicit namespace package contract S2-01 HARDENED depends on, and (b) still not fix the import bridge for the hyphenated leaf (which requires the autouse `load_task_class` conftest, not a package marker).

**Resolution:** Implementation outline §4 rewritten in this pass to ship `bench/vuln-remediation/tests/conftest.py` with the autouse `load_task_class("vuln-remediation", bench_root=REPO_ROOT / "bench")` fixture. Hard-ban on `__init__.py` reasserted in-body.

### F-CON-SYNC-2 (BLOCK) — Files-to-touch table still had the `tests/__init__.py` row

Second-pass Validation-notes bullet: *"`Files to touch` aligned: `bench/vuln-remediation/tests/__init__.py` row dropped; `bench/vuln-remediation/tests/conftest.py` row added."*

Actual body of the Files-to-touch table (pre-edit): still contained the row `bench/vuln-remediation/tests/__init__.py | New file — empty package marker`.

**Resolution:** Files-to-touch table rewritten this pass. Now:
- `tests/__init__.py` row removed
- `tests/conftest.py` row added
- `test_rubric_static.py` row added (AC-9)
- `tests/unit/test_eval_package_imports_no_llm_sdk.py` row added (AC-12) with Modify status
- `rubric.py` row status corrected to "Modify (S5-01 shipped stub)" — the byte-for-byte replacement contract from S5-01 F-CON-7

### F-CON-SYNC-3 (BLOCK) — Red-section TDD-plan assertions still pre-hardening

The second pass tightened AC-4 extensively (per Validation-notes bullet "Test assertions tightened against trivial mutants (HARDEN): AC-4(a) `result.score >= 0.95` → `result.score == 1.0` (kills a `score = 0.95` hardcoded-return mutant)..." with four F-TQ subitems). But the Red-section TDD-plan code block below (pre-edit, lines 167-254) still contained:

```python
assert result.score >= 0.95                                      # AC-4(a) says == 1.0
assert all(fm.severity != "block" for fm in result.failure_modes)  # AC-4(a) says == ()
block_codes = {fm.code ... if fm.severity == "block"}
assert "validator.tests_failed" in block_codes                    # AC-4(b) says exact set ==
assert set(result.breakdown.keys()) <= declared                   # AC-4(d) says ==
```

An executor following the Red block verbatim would commit a red marker (correct: red because the module doesn't exist) but the mutant-detection tightening AC-4 pins would never actually reach the test file — the executor would move to §Green and either (a) invent tighter assertions from AC bodies (fine, but no traceable red→green delta on the tightening itself) or (b) accept the thin assertions as-is (bad: a subsequent broken `score = 0.95` mutant would pass CI).

**Resolution:** Red-section code block rewritten in this pass. Every AC-4(a–f) assertion now matches the AC body byte-for-byte. Additional-tests-in-same-file (AC-1/AC-5/AC-6/AC-7/AC-8/AC-10/AC-11) enumerated below the code block with an AC-back-reference, so the executor sees the full test-file contract at TDD time.

### F-CON-SYNC-4 (BLOCK) — Green §1 + Refactor §2 contradict AC-10 / F-DP-1

Second-pass Validation-notes bullet: *"Severities hardcoded; YAML consistency test (HARDEN, F-DP-1): ... Pin a tighter alternative: the rubric emits exactly four block codes... Implementation outline §2 now declares `_SEVERITY_FOR_EMITTED_CODE: Final[Mapping[str, Literal["block","warn","info"]]]` hardcoded... Avoids brittle import-time I/O..."* — and AC-10 codifies this: *"rubric.py declares `_SEVERITY_FOR_EMITTED_CODE: Final[Mapping[str, Literal["block","warn","info"]]]` mapping the four codes..."*.

But §Green §1 (pre-edit line 265) still said: *"For each falsy condition, emit a `FailureMode(code=..., severity=..., detail=None)` — the declared severity comes from the YAML; the rubric **does not** hardcode it (read it once at module load)."*

And §Refactor §2 (pre-edit line 272) still said: *"Lift the YAML severity load to module import time (single I/O); cache as `_TAXONOMY: Mapping[str, Literal["block","warn","info"]]`."*

Directly contradicts AC-10 + F-DP-1. An executor following §Green would ship the YAML-read path, which (a) fails AC-10's static test that expects the hardcoded `_SEVERITY_FOR_EMITTED_CODE` symbol; (b) breaks the ADR-0001 subprocess cold-start budget (YAML I/O on every subprocess spawn, ~150 ms/case × 10 cases = 1.5s wasted); (c) trips a cwd-relative-path resolution bug under `subprocess.run(..., cwd=tempfile.TemporaryDirectory())` — the rubric's `Path(__file__).parent / "failure_modes.yaml"` still works, but a naive `Path("failure_modes.yaml")` (a plausible first draft) resolves against the empty tempdir and raises `FileNotFoundError`.

**Resolution:** §Green §1 rewritten this pass. Severity now looked up from `_SEVERITY_FOR_EMITTED_CODE[paired_code]` (hardcoded). §Refactor §2 rewritten to explicitly BAN the YAML-import-time lift and pin the rule-of-three lift target (arch line 564) for Phase 15.

### F-CON-SYNC-5 (HARDEN) — Implementation outline §3 `__main__` block missing `_HarnessOutput` Pydantic model

Second-pass Validation-notes bullet: *"HarnessOutput envelope endorsement (HARDEN, F-DP-2): the Refactor instruction 'destructure with pydantic BaseModel for the envelope' is currently a Notes aside. Promoted to Implementation outline §3 as a concrete `_HarnessOutput(BaseModel, frozen=True, extra="forbid")` with `validator: _ValidatorSignals` and `recipe: _RecipeSignals` sub-models..."*

But §3's actual body (pre-edit, lines 110-121) showed:

```python
if __name__ == "__main__":
    import sys, json
    from codegenie.eval.models import BenchCase, BenchScore
    payload = json.loads(sys.stdin.buffer.read())
    case = BenchCase.model_validate(payload["case"])
    harness_output = payload["harness_output"]    # ← raw dict, NOT _HarnessOutput.model_validate(...)
    result = score(case, harness_output)
    sys.stdout.buffer.write(result.model_dump_json().encode("utf-8"))
    sys.exit(0)
```

An executor following §3 verbatim would ship the raw-dict path — AC-2's Pydantic-validation requirement would be missed, AC-8's `ValidationError` fail-loud path unreachable, F-DP-2's SUT-contract-drift-surfaces-at-envelope-layer design abandoned. The `try/except (JSONDecodeError, ValidationError, KeyError): sys.exit(2)` from AC-2 also missing — the executor would ship a `__main__` that panics with a raw traceback (also a fail-loud path, but the exit-code contract AC-2 pins is `2`, not "whatever Python's default abort code happens to be").

**Resolution:** §3 rewritten this pass with `_ValidatorSignals`, `_RecipeSignals`, `_HarnessOutput` Pydantic model shapes pinned inline, plus the `_SEVERITY_FOR_EMITTED_CODE` mapping, plus the `try/except: sys.exit(2)` wrapper.

### F-CON-SYNC-6 (BLOCK) — Implementation outline §5 too vague to satisfy AC-3's parent-sentinel protocol

Pre-edit §5 said only: *"Write `tests/integration/test_rubric_subprocess_vuln.py` to exercise the subprocess path with `SCRUBBED_ENV` (mirror the runner's contract); assert wall-clock ≤ 60 s on a representative envelope."*

But AC-3 pins a specific protocol: *"The parent process sets `ANTHROPIC_API_KEY=parent-sentinel`, `AWS_ACCESS_KEY_ID=parent-sentinel`, `HOME=/parent-home`, `USER=parent-user` before spawn; the rubric writes a debug line to stderr (stdout is reserved for the `BenchScore`) reporting `os.environ.get("ANTHROPIC_API_KEY")`, `os.environ.get("AWS_ACCESS_KEY_ID")`, `os.environ.get("HOME")`, `os.environ.get("USER")`; the test asserts each is `None` in the rubric's environment."*

An executor could satisfy the vague §5 with a subprocess test that never sets parent sentinels, never captures stderr, never asserts on the scrubbed-values — and technically still pass "mirror the runner's contract." The rubric's stderr debug-line requirement in particular is subtle: `stdout` must stay reserved for `BenchScore`, so the SCRUBBED_ENV evidence has to go through `stderr` — a non-obvious call an executor would miss without §5 pinning it.

**Resolution:** §5 rewritten this pass with the full parent-sentinel + stderr-debug-line protocol pinned inline, plus AC-2's malformed-JSON test explicitly co-located in the same integration file. §6 and §7 added for the AC-9 AST test-file and AC-12's LLM-SDK-fence extension.

### F-CON-SYNC-7 (HARDEN) — Files-to-touch omits AC-9 static test + AC-12 fence-extension file

The pre-edit Files-to-touch table listed only four rows. AC-9 requires a static AST test on `rubric.py` — pattern-precedent is S5-01's `test_breakdown_keys_static.py` sibling file, not a test buried inside `test_rubric_unit.py`. AC-12 explicitly modifies (not creates) `tests/unit/test_eval_package_imports_no_llm_sdk.py`. Neither had a row.

**Resolution:** Files-to-touch expanded this pass with two new rows and a Status column distinguishing New / Modify.

---

## Critic: Coverage (lens: do the ACs collectively guarantee the goal? contradictions?)

### F-COV-SYNC-1 (BLOCK) — AC-4's "exactly six" is inconsistent with the tests introduced by AC-1/AC-2/AC-5..AC-11

Pre-edit AC-4 header: *"`bench/vuln-remediation/tests/test_rubric_unit.py` exists and contains **exactly the following six** named tests (no fewer, no extras for this story's red→green window)"*.

But other ACs demand additional named tests in the same file:
- AC-1 requires `test_class_score_method_delegates_to_module_level_score`
- AC-5 requires `test_each_falsy_breakdown_condition_emits_its_paired_failure_code`
- AC-6 requires `test_half_pass_yields_score_exactly_half_kills_min_max_mutants`
- AC-7 requires `test_failure_modes_tuple_is_sorted_by_code`
- AC-8 requires `test_missing_harness_output_key_propagates_keyerror`
- AC-10 requires `test_hardcoded_severities_match_failure_modes_yaml`
- AC-11 requires `test_score_invariant_under_unrelated_case_field_mutations`

Plus AC-2 pins a test at a different path (`tests/integration/test_rubric_subprocess_vuln.py`), AC-3 pins the SCRUBBED_ENV assertion in the same integration file, AC-9 pins the AST test (best routed to a sibling `test_rubric_static.py` per the S5-01 pattern), AC-12 modifies an existing test-file glob.

An executor asked "exactly six?" cannot resolve this. The two rational readings — (a) drop the six-only pin and let AC-1/AC-5..AC-11 add tests, or (b) split test files — need to be pinned by the story author, not by executor guesswork. Silently choosing wrong yields a story whose `pytest bench/vuln-remediation/tests/` either short-changes the mutation-kill coverage (option a chosen wrong) or misses the six core-condition assertions (option b chosen wrong).

**Resolution:** AC-4 rewritten this pass to say "**six *core-condition* tests** (plus the additional tests pinned by AC-1, AC-5, AC-6, AC-7, AC-8, AC-10, AC-11 in the *same* file — see §Test-file routing below — and the tests pinned by AC-2, AC-3, AC-9, AC-12 in the files named in those ACs)". Explicit test-file routing table added inside AC-4 mapping every AC to its file. Additional-tests enumeration added after the Red-section code block. This is the choice with least body churn — six core-condition + additional tests co-located in the same file mirrors S5-01's HARDENED pattern (one test file per module tested, multiple test functions per file, sibling `test_*_static.py` for AST bans).

---

## Critic: Test Quality (lens: mutation-resistance of the tightened Red block?)

### F-TQ-SYNC-1 (HARDEN) — `passed`-derivation pin missing from Notes-for-implementer

Green §1 pre-edit said `passed = all(v == 1.0 for v in breakdown.values())`. That's observably equivalent to `passed = (score == 1.0)` on the currently-tested rows (AC-1 full-pass, AC-6 half-pass) — no test distinguishes them. But under future extension (a fifth breakdown key added with partial-credit semantics, e.g., `code_style: 0.7`), the two forms diverge:

- `all(v == 1.0 ...)` returns `False` on any partial credit → `passed=False` even when `score >= 0.95` (over-strict)
- `(score == 1.0)` returns `False` only on any partial credit above zero total mean → same over-strictness for `score == 1.0` but breaks the promotion-gate contract `score >= 0.95_lower_bound` because `passed` no longer correlates with that gate

The promotion gate (ADR-0002) reads `lower_bound_95` of `score`, not `all(passed)`. Tying `passed` to `score == 1.0` post-mean keeps the derivation aligned with the gate's evidence surface; tying it to sub-conditions couples `passed` to the specific evidence shape the current rubric emits, which is an anti-Open/Closed extension trap.

**Resolution:** Green §1 pre-edit rewritten to `passed = (score == 1.0)` — computed post-mean. Notes-for-implementer this pass adds a paragraph pinning the rationale so future rubric authors don't regress. Not promoted to a distinct AC — the observable behavior is identical on today's tests; the pin lives in the design-rationale layer, not the AC-verification layer (Rule 2 — don't over-constrain).

---

## Critic: Design Patterns (lens: is the implementation shape extension-friendly?)

Design-endorsements from the second pass all stand:
- **Functional core / imperative shell** — already followed (pure `score()` + `__main__` shell).
- **Open/Closed at `bench/{task-class}/rubric.py`** — Phase 7 copies verbatim.
- **Strategy pattern via `_CONDITION_FAILURE_PAIRS`** — kept in Refactor §.

No new Design-Patterns findings this pass. The `_HarnessOutput` Pydantic-model surface is now correctly ported from Notes-aside into §3, which is the F-DP-2 design endorsement being *implemented* — no additional pattern-work required.

---

## Edits applied

Twelve concrete edits to `stories/S5-02-vuln-rubric-and-unit-tests.md`:

1. **Status line** updated: `HARDENED (phase-story-validator, 2026-07-25 — third pass: full body-vs-validation-notes sync + AC-4/AC-1..AC-11 test-file-routing reconciliation)`.
2. **Validation notes** section expanded with a new "Third-pass changes (2026-07-25)" block enumerating the 9 findings this pass with their F-tags; the pre-existing 23-finding block preserved verbatim.
3. **AC-4 header** rewritten from "exactly the following six" to "**six *core-condition* tests** (plus the additional tests pinned by AC-1, AC-5..AC-11 in the same file — see §Test-file routing below — and the tests pinned by AC-2, AC-3, AC-9, AC-12 in the files named in those ACs)"; explicit test-file routing table appended.
4. **Implementation outline §2** expanded to name the dual-surface contract explicitly, the `_HarnessOutput` model, the `_CONDITION_FAILURE_PAIRS` table, the `_SEVERITY_FOR_EMITTED_CODE` hardcoded mapping, the `passed = (score == 1.0)` derivation, the sorted-failure-modes contract, and the delegation body of `VulnRemediationRubric.score`.
5. **Implementation outline §3** rewritten with the full `_ValidatorSignals`/`_RecipeSignals`/`_HarnessOutput`/`_SEVERITY_FOR_EMITTED_CODE` inline plus the `try/except: sys.exit(2)` wrapper on the `__main__` block.
6. **Implementation outline §4** rewritten from "`bench/vuln-remediation/tests/__init__.py` (empty package marker)" to "`bench/vuln-remediation/tests/conftest.py` (autouse `load_task_class(...)` fixture)"; hard-ban reasserted in body.
7. **Implementation outline §5** rewritten with parent-sentinel protocol, stderr debug-line pattern, AC-2 malformed-JSON test co-location, 60 s budget assertion.
8. **Implementation outline §6** added — AC-9 AST-ban test file `test_rubric_static.py`.
9. **Implementation outline §7** added — AC-12 LLM-SDK-fence extension.
10. **§TDD Red code block** — all six test bodies rewritten to match AC-4(a–f) tightened assertions byte-for-byte; additional-tests-in-same-file enumeration appended with per-AC back-references; test-file routing footer added.
11. **§TDD Green + Refactor** — hardcoded-severity + `_HarnessOutput` model + `passed = (score == 1.0)` + sorted-failure-modes contract pinned; YAML-import-time lift explicitly banned; rule-of-three lift target (arch line 564) named for Phase 15.
12. **Files to touch** table rewritten: removed `tests/__init__.py`, added `tests/conftest.py`, added `test_rubric_static.py`, added `tests/unit/test_eval_package_imports_no_llm_sdk.py` (Modify), added Status column, corrected `rubric.py` row to Modify (S5-01 shipped stub).
13. **Notes-for-implementer** appended with (a) `passed`-derivation rule pin, (b) adversarial mutant catalog enumerating 11 named mutants this §TDD kills, (c) contract-surface decision pin explaining why `_HarnessOutput` is LOCAL not shared.

---

## Verdict

**HARDENED.** Every drift the second-pass sync missed is now reconciled. The story body IS the validation notes now. An executor following the story literally will produce an implementation that:

- Satisfies the S5-01 F-CON-7 byte-for-byte stub-replacement contract (rubric row correctly marked Modify).
- Passes AC-4 (six core-condition tests, correctly tightened) AND AC-1/AC-5..AC-11 (additional named tests co-located in the same file).
- Passes AC-2 + AC-3 (subprocess entrypoint tests correctly routed to `tests/integration/`).
- Passes AC-9 (AST-ban static test in the sibling-file pattern S5-01 established).
- Passes AC-10 (hardcoded `_SEVERITY_FOR_EMITTED_CODE` + YAML-consistency test).
- Passes AC-12 (extends the existing LLM-SDK glob rather than creating a duplicate walker).
- Preserves the `bench/`-PEP-420-implicit-namespace-package contract from S2-01 HARDENED (no `tests/__init__.py`).

No `NEEDS RESEARCH` items. No unresolved conflicts. Ready for executor.
