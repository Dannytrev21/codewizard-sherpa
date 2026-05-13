# Validation report: S3-02 — Pydantic `_ProbeOutputValidator` trust boundary

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S3-02-probe-output-validator.md`](../S3-02-probe-output-validator.md)

## Summary

S3-02 lands the Pydantic v2 `_ProbeOutputValidator` trust boundary inside the coordinator — the structural enforcement of "facts, not judgments" (`production/design.md §2.2`) that ADR-0010 makes load-bearing in Phase 0. The story's goal, ADR fidelity, and out-of-scope are correct; the AC set and TDD plan, however, had three classes of weakness: (1) a self-contradicting AC-4/test-3/implementer-note triad about whether Pydantic wraps validator-raised exceptions; (2) thin tests that asserted only "a `ValidationError` was raised" (defeated by any wrong impl that raises for any reason); (3) named ADR-0010 requirements (deeply-nested `bytes`, depth-N secret keys) that no AC enforced. Three critics returned **28 findings** (8 block, 17 harden, 3 nit) with **zero `NEEDS RESEARCH` tags** — every fix was answerable from in-repo docs (ADR-0010, ADR-0008, ADR-0007, `phase-arch-design.md`, `final-design.md §L5`, the local test idiom in `tests/unit/test_audit_models.py`).

The validator applied edits in place:

- Renumbered AC-1 .. AC-8 (no body changes to AC-1, AC-2, AC-3, AC-7, AC-8 beyond clarifications and explicit error-locus assertions); rewrote AC-4 to reflect Pydantic v2 wrapping; split AC-5 into a verifiable form; expanded AC-6 + new AC-15 for the SECRET_FIELD_PATTERN single-source split.
- Appended **AC-9 through AC-19** — eleven new ACs covering: `model_validate(asdict)` round-trip, ADR-0007 import-seam, depth-N secret keys, depth-N bytes, `bool`-vs-`int` Union ordering, empty-slice acceptance, compiled-regex pinning, non-string-key rejection, lazy-import cold-start preservation, frozen-mutation rejection, and `RecursionError` resilience.
- **Rewrote the TDD plan end-to-end** as concrete, runnable Python — parametrized forbidden-type matrix (10 cases), parametrized secret-regex alternatives (20 cases incl. casing/separator/false-positive variants), parametrized confidence negative-space (10 cases), and standalone tests for round-trip, frozenness, packaging, lazy-import, and recursion-safety. Every `ValidationError` assertion pins `errors()[0]["loc"]` and `["type"]` to defeat "any-error-passes" mutants.
- Added a `Validation notes` block under the story header summarizing every change and surfaced two architectural inconsistencies as follow-ups (not auto-fixed — outside this story's surgical scope).
- Added `ADR-0007` to the honored-ADRs line (the validator/dataclass seam is an ADR-0007 conformance contract).

Two architectural inconsistencies surfaced as follow-ups (not auto-fixed):

1. `docs/phases/00-bullet-tracer-foundations/High-level-impl.md` Step 3 line ~94 names a different secret regex than ADR-0010 / this story's AC-4. ADR-0010 is authoritative (Nygard: ADRs win over impl plan). Impl plan should be amended.
2. AC-6 originally read as a cross-story coupling that S3-02 couldn't fully verify. Split into AC-6 (S3-02 owns the source-of-truth constant) + AC-15 (mechanical verification that it exists). S3-03's sanitizer story owns the AC that verifies the *import*.

## Findings by critic

### Coverage critic

12 findings (3 block, 8 harden, 1 nit):

- **F1 (block)** — Goal names `model_validate(asdict(probe_output))` but no AC or test exercises that exact shape. A lazy impl that overrides `__init__` but breaks `model_validate` (or fails to handle the `asdict` dict-shape with extra dataclass fields like `raw_artifacts`/`duration_ms`/etc. landing as "extras") would satisfy every original AC and fail the goal.
- **F2 (block)** — `asdict(probe_output)` carries the *full* `ProbeOutput` dataclass (6+ fields), but the validator only declares `schema_slice` and `confidence` with `extra="forbid"`. The goal's `model_validate(asdict(...))` call will *always* raise on the other fields. Either the model needs all fields, or the coordinator must project — neither was specified.
- **F3 (block)** — AC-7 says "all four red-test behaviors below" but the TDD plan lists six tests. Off-by-two AC wording.
- **F4 (block)** — AC-5 "not exported from `coordinator/__init__.py`" is unverifiable as written; no test enforces it. A future contributor who adds `from .validator import _ProbeOutputValidator` to `__init__.py` would silently violate ADR-0010 §Consequences.
- **F5 (block)** — Secret-name regex at *depth* is asserted in implementer-notes only, never in an AC or test. AC-4 says "walks all keys recursively" but the only secret test uses a top-level key. A lazy impl that only checks top-level keys passes every test.
- **F6 (block)** — `bytes`/`Callable` rejection is tested only at the top level; ADR-0010 §Consequences line 52 explicitly requires "deeply-nested `bytes` → rejection" but no test covers it.
- **F7 (harden)** — `JSONValue` closure under exotic Python types (`tuple`, `set`, `datetime`, `Decimal`, `Path`, custom objects, NaN/inf floats) is untested. Only `bytes` and `Callable` covered.
- **F8 (harden)** — `dict[str, JSONValue]` requires string keys but no test asserts non-string keys are rejected. A probe emitting `{1: "x"}` should fail.
- **F9 (harden)** — `SECRET_FIELD_PATTERN` "single source of truth" (AC-6) has no test in *this* story that the constant exists at module scope with the exact name. A lazy impl that defines the regex inline inside the validator passes every other AC.
- **F10 (harden)** — Empty `schema_slice` boundary unstated; very-large / deeply-recursive `schema_slice` unmentioned. Python's recursion limit on a naive recursive walker is a real concern.
- **F11 (harden)** — Pydantic-wraps-exception contradiction inside the story itself between AC-4, TDD test 3, and implementer-notes line 136.
- **F12 (nit)** — Out-of-scope is missing an item: regex tuning / false-positive triage (ADR-0010 §Tradeoffs line 41 acknowledges false positives but story doesn't, so an executor might widen the regex).

### Test-Quality critic

11 findings (3 block, 7 harden, 1 nit):

- **F1 (block)** — Test 3 will fail against a correct Pydantic-v2 implementation. Pydantic wraps validator exceptions in `ValidationError`; the test's assertion that "`SecretLikelyFieldNameError` is raised (not generic ValidationError)" contradicts implementer-note line 136.
- **F2 (block)** — All five `pytest.raises(ValidationError)` tests are thin: they pass for *any* validation failure. A mutant impl that always raises `ValidationError("schema_slice missing")` regardless of input passes all of them.
- **F3 (harden)** — Bytes/Callable tests are single-instance; mutation-survivable. An impl typing `schema_slice: dict[str, str | int | bool | None]` (dropping `list`/`dict`/`float`) still rejects bytes and lambdas, passes the test, and silently breaks valid nested-JSON probes.
- **F4 (block)** — Test 3 doesn't pin *which* secret token matched, so the regex can be silently weakened to `(?i).*token.*` and still pass.
- **F5 (harden)** — Recursive-walk depth is never tested; a mutant `_walk_keys` that only checks top-level keys passes every current test.
- **F6 (harden)** — Test 5's "frozen model returned" claim is asserted by comment only. The test body is `...`; frozenness isn't checked. A mutant `ConfigDict(frozen=False)` passes the test.
- **F7 (harden)** — Goal verbatim says `model_validate(asdict(probe_output))` but no test exercises that call shape.
- **F8 (harden)** — No property-based test, despite hypothesis being the natural fit for "any JSONValue round-trips." Codebase has no hypothesis dep. **Validator decision:** defer adding hypothesis (Rule 2 — no speculative dependency); parameterize aggressively to achieve equivalent mutation resistance. (Was tentatively `NEEDS RESEARCH`; resolved without external research from repo state.)
- **F9 (harden)** — No negative-space test for `confidence`: only `"high_with_caveats"` is rejected. Mutants like `Literal["HIGH","MEDIUM","LOW"]` (case-mutated) or `str` instead of `Literal` survive.
- **F10 (nit)** — AC-8 says `mypy --strict src/codegenie/coordinator/validator.py` is clean but no test surfaces a `JSONValue` type error. CI catches it; lower priority.
- **F11 (harden)** — Extra-fields test is single-instance and doesn't pin *which* extra field triggered the error.

### Consistency critic

8 findings (2 block, 4 harden, 2 nit):

- **F1 (harden)** — Regex drift between `High-level-impl.md` Step 3 and ADR-0010/story. ADR-0010 is authoritative (Nygard: ADRs win over impl plan). Story is consistent with ADR. Surfaced as out-of-band follow-up.
- **F2 (block)** — Internal contradiction in the story: AC-4 / TDD test 3 vs. implementer-note line 136 about whether Pydantic wraps `SecretLikelyFieldNameError`.
- **F3 (harden)** — AC count drift: AC-7 says "four red-test behaviors" but TDD plan ships six tests and Files-to-touch table says "six rejection / acceptance behaviors."
- **F4 (harden)** — Missing deeply-nested `bytes` test that ADR-0010 §Consequences line 52 explicitly requires as a Phase-0 named commitment.
- **F5 (nit)** — Coordinator import-linter / lazy-import expectation under-specified vs. `phase-arch-design.md §CLI` line 419 (`import-linter` blocks `pydantic` from `cli.py`) and `final-design.md §2.11`. No AC pins the cold-start defense.
- **F6 (harden)** — `JSONValue` typed-alias `Union` ordering is under-specified vs. Pydantic v2 reality (`bool` is a subclass of `int`; `int` first coerces `True` to `1`).
- **F7 (nit)** — Schema-slice dual representation seam (dataclass `dict[str, Any]` vs Pydantic `dict[str, JSONValue]`) is described in context but not asserted as an ADR-0007 contract — no AC says `validator.py` doesn't import `ProbeOutput`.
- **F8 (block)** — AC-6 introduces an undeclared cross-story coupling that S3-02 cannot satisfy alone (`output/sanitizer.py` doesn't exist yet). Split required.

## Research briefs

**None.** Stage 3 was skipped. Test-Quality F8 was tentatively `NEEDS RESEARCH` (hypothesis introduction) but resolved without external research: the codebase has no hypothesis dependency, Phase 0 does not list adding one, and Rule 2 ("Simplicity First — no speculative dependencies") favors aggressive `pytest.mark.parametrize` over introducing a new test framework. The rewritten TDD plan parametrizes 10 forbidden-leaf types, 20 secret-key variants, 10 invalid confidence values, and 10 permitted inputs — 50+ generated cases, equivalent mutation resistance to a property-based suite for this story's invariants.

## Conflict resolutions

- **Coverage F11 ≡ Test-Quality F1 ≡ Consistency F2** (the Pydantic-wrap contradiction): merged into AC-4 rewrite + TDD `_unwrap_typed_error` helper + implementer-notes Pydantic-wrapping section. AC-4 now states the Pydantic v2 reality (`errors()[0]["ctx"]["error"]` OR `__cause__` surface); test 3 uses the helper. ADR-0010 §Consequences is unambiguous about "typed error surfaces to coordinator" — that survives via the unwrap.
- **Coverage F2** (`asdict` carries extra fields, breaks `extra="forbid"`): resolved by AC-9 explicitly stating S3-05 (the *caller*) projects the `asdict` dict down to the two declared keys. The validator's contract is the two-key model_validate, not the full-dataclass one. This matches `final-design.md §L5`'s resolution of the two-representation seam.
- **Coverage F3 ≡ Consistency F3** (AC-7 count): merged — AC-7 now says "all behaviors listed in the TDD plan below (≥ 14 test cases after parameter expansion)."
- **Coverage F4 ≡ Consistency F5** (privacy + lazy-import unverifiable): split — AC-5 mechanically verifies privacy via `hasattr` + `__all__` check, AC-17 mechanically verifies lazy-import via `sys.modules` snapshot.
- **Coverage F5 ≡ Test-Quality F5 ≡ Consistency F4** (depth-N rejection): merged into AC-11 (secret-key at depth ≥ 3 including through `list[dict]`) + AC-12 (bytes at depth ≥ 2). Both have explicit nested-shape test snippets in the TDD plan.
- **Coverage F8 ≡ Test-Quality F9** (negative-space coverage): merged into AC-16 (non-string keys) + parametrized confidence rejection test (10 cases).
- **Coverage F9 ≡ Consistency F8** (SECRET_FIELD_PATTERN visibility + cross-story coupling): split into AC-6 (S3-02 owns the constant; cross-story note) + AC-15 (mechanical re-import test in S3-02; S3-03 will add its own AC for the sanitizer's import).
- **Test-Quality F2** (thin tests, "any-error-passes" mutants): resolved via locus-pinning convention added to AC-3, AC-4, AC-11, AC-12, AC-16 — every `pytest.raises(ValidationError)` block must assert `errors()[0]["loc"]` and `errors()[0]["type"]`. Documented in the TDD plan preamble.
- **Test-Quality F6** (frozen unverified): AC-18 + concrete mutation test (mirrors `test_audit_models.py::test_frozen_mutation_raises` per Rule 11).
- **Test-Quality F8** (hypothesis): resolved against introducing the dep; parametrized coverage achieves equivalent mutation resistance. Recorded in research-briefs section.
- **Consistency F1** (regex drift in High-level-impl.md): not auto-fixed (out of scope — only the story file may be edited). Surfaced as Surfaced-Inconsistencies item in the Validation notes block and implementer notes.
- **Consistency F6** (Pydantic Union ordering): merged into AC-2 (note in the type declaration) + AC-13 (concrete `bool`-vs-`int` round-trip test).
- **Consistency F7** (ADR-0007 seam not asserted): AC-10 + `test_validator_module_does_not_import_from_probes_base` (parses `validator.py` via `ast`).

## Edits applied

### Edit 1 — `Validation notes` block added under the story header
- **Source:** validator convention.
- **What:** New `## Validation notes` block (verdict, finding totals, summary of edits, surfaced architectural inconsistencies).
- **Rationale:** Breadcrumb for the next reader.

### Edit 2 — `ADR-0007` added to `ADRs honored` line
- **Source:** Consistency F7.
- **Rationale:** The decoupling between `_ProbeOutputValidator` and `ProbeOutput` (dataclass) is an ADR-0007 conformance contract. Making it header-level keeps the seam explicit.

### Edit 3 — AC-4 rewritten to match Pydantic v2 wrapping reality
- **Source:** Coverage F11, Test-Quality F1, Consistency F2.
- **Before:** "A field-validator on `schema_slice` walks all keys recursively and raises `SecretLikelyFieldNameError` when any key matches ..."
- **After:** Explicitly states Pydantic v2 wraps the raise into `ValidationError` and names the two surfaces (`errors()[0]["ctx"]["error"]` or `__cause__`) from which the typed error is retrievable. Adds error-locus pinning.
- **Rationale:** Resolves the internal contradiction with the implementer note. Tests as previously written would have failed against a correct implementation.

### Edit 4 — AC-5 made mechanically verifiable
- **Source:** Coverage F4.
- **Before:** "not exported from `coordinator/__init__.py`" (unverifiable as written).
- **After:** Adds explicit `__all__` and `hasattr` checks, names a unit test that snapshots `sys.modules` to enforce.

### Edit 5 — AC-6 split into AC-6 + AC-15
- **Source:** Consistency F8.
- **Before:** "The same compiled secret-regex is referenced (or re-imported) by `output/sanitizer.py` in S3-03" (S3-02 cannot verify a not-yet-existing file).
- **After:** AC-6 narrows to the single-source-of-truth declaration; AC-15 adds a mechanical "the constant exists at module scope as `re.Pattern`" test that S3-02 can execute alone.

### Edit 6 — AC-7 count corrected
- **Source:** Coverage F3, Consistency F3.
- **Before:** "covers all four red-test behaviors below."
- **After:** "covers all behaviors listed in the TDD plan below (≥ 14 test cases after parameter expansion)."

### Edit 7 — Eleven new ACs (AC-9 through AC-19) appended
- **Source:** Coverage F1, F2, F5, F6, F8, F10; Test-Quality F5, F6, F7; Consistency F4, F5, F6, F7.
- **What:** AC-9 (`model_validate(asdict)` round-trip), AC-10 (no `probes.base` import), AC-11 (secret key at depth ≥ 3), AC-12 (bytes at depth ≥ 2), AC-13 (`bool`-vs-`int` Union ordering), AC-14 (empty slice accepted), AC-15 (compiled regex importable), AC-16 (non-string keys rejected), AC-17 (lazy-import preserved), AC-18 (frozen-mutation raises), AC-19 (recursion-safe walker).
- **Rationale:** Closes goal-trace gaps, makes ADR-0010 named requirements (deeply-nested bytes, depth-N secret keys) testable, preserves the ADR-0007 dataclass seam structurally, and defends the CLI cold-start fence.

### Edit 8 — TDD plan rewritten end-to-end with concrete runnable snippets
- **Source:** Test-Quality F1, F2, F3, F4, F5, F6, F7, F9, F11; Coverage F5, F6.
- **What:** Replaced six `...`-stubbed tests with a full pytest module containing:
  - `FORBIDDEN_LEAVES` parametrize matrix (10 cases: bytes, bytearray, lambda, tuple, set, frozenset, datetime, Path, Decimal, custom object) for top-level and depth-2.
  - `PERMITTED_INPUTS` parametrize matrix (10 cases) covering empty-slice + every `JSONValue` leaf type + deep-nesting.
  - `INVALID_CONFIDENCES` parametrize (10 cases: empty, casing, trailing-space, extended, extra-value, None, integer, list-wrap) and `["high","medium","low"]` positives.
  - `SECRET_KEYS` parametrize (20 cases covering every alternative in the ADR regex + casing + separator variants).
  - `_unwrap_typed_error` helper for the Pydantic-wrap surface — tries `errors()[0]["ctx"]["error"]` then `__cause__`.
  - Benign-key-with-substring rejection tests (ADR-0010 §Tradeoffs documented false positives).
  - `test_secret_field_pattern_is_compiled_at_module_scope` (AC-15).
  - `test_extra_field_rejected` with locus-pinning.
  - `test_frozen_model_mutation_raises` (AC-18 — mirrors local idiom).
  - `test_non_string_keys_rejected` (AC-16).
  - `test_model_validate_from_asdict_round_trip` (AC-9 — constructs a real `ProbeOutput`, projects, validates).
  - `test_validator_module_does_not_import_from_probes_base` (AC-10 — `ast.parse` inspection).
  - `test_validator_not_exported_from_coordinator_package` (AC-5).
  - `test_importing_coordinator_does_not_pull_pydantic` (AC-17 — `sys.modules` snapshot).
  - `test_deeply_nested_dict_does_not_recursion_error` (AC-19 — depth-200 input).
- **Rationale:** Every prior test was either thin (Test-Quality F2), single-instance (F3, F4, F9), or self-contradicting (F1). The rewrite makes every assertion mutation-resistant.

### Edit 9 — Green-section guidance updated
- **Source:** synthesis of Consistency F6, Test-Quality F1, Coverage F10.
- **What:** Pinned `bool` precedes `int` in `JSONValue`; pinned that the walker must be iterative (deque/stack), not recursive; added a Pydantic-wrapping section explaining the contract end-to-end.

### Edit 10 — Implementer notes expanded
- **Source:** synthesis of Pydantic-wrap finding cluster + surfaced regex drift.
- **What:** Added `model_validate` call-shape note, AC-10 reminder ("do not import `ProbeOutput`"), `Union`-ordering rationale, iterative-walker requirement, Pydantic-wrap unwrap surface, and the High-level-impl.md regex drift note.

### Edit 11 — Files-to-touch description updated
- **Source:** Coverage F3.
- **Before:** "covers six rejection / acceptance behaviors."
- **After:** "covers all AC-1 .. AC-19 behaviors (≥ 14 test cases after parameter expansion)."

## Verdict rationale

**HARDENED.** The story's *goal* and *scope* are correct — ADR-0010 is the source of truth and the story honors it. The weaknesses were all in the AC/test specification surface: a self-contradicting trio of statements about Pydantic exception wrapping, missing enforcement of named ADR requirements (depth-N rejection), thin tests that any wrong impl could pass, and one block-level inconsistency (AC-6 referencing a file that doesn't exist yet). All of these were patchable in place without rewriting the goal. The single highest-impact change was rewriting AC-4 + test 3 + implementer notes to internally agree on how Pydantic v2 handles validator-raised typed errors — the prior story would have produced a test that fails against a correct implementation, costing executor attempts. Two architectural inconsistencies (High-level-impl.md regex drift, cross-story coupling) were surfaced rather than fixed because they require edits outside this story's scope.

## Recommended next step

`phase-story-executor` to implement. The story now has 19 concrete ACs, a runnable TDD plan with locus-pinning and parametrized mutation defenses, and an unambiguous Pydantic-wrapping contract. After S3-02 is green, `phase-story-validator` should also revisit S3-03 (sanitizer) to pin the cross-import of `SECRET_FIELD_PATTERN` and the path-scrub regex.
