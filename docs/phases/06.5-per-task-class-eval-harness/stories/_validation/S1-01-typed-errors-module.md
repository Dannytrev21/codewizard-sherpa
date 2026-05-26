# Validation report: S1-01 — Typed errors module

**Validated:** 2026-05-25
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S1-01 lands `src/codegenie/eval/errors.py` — a `CodegenieEvalError` root plus nine behavior-free marker subclasses that the rest of Step 1–4 raises. The story was well-structured and well-referenced; the goal is small and the implementation outline is correct. Three categories of weakness slipped past the writer:

1. **The load-bearing design decision (sibling-not-child of `codegenie.errors.CodegenieError`) lived only in prose.** The implementer notes correctly identify it as the boundary that preserves the import-linter contract S1-05 wires, but no AC and no test pinned it. A future tidy-up rebase under `CodegenieError` would silently collapse the bounded-context boundary and let any `except CodegenieError:` site in Phase 0 swallow eval-harness errors. AC-7 added; red test now mutation-resistant in both directions (subclass + inverse).
2. **Mutation-resistance gaps on the marker discipline.** AC-3's `issubclass` check passes for transitive inheritance — insertion of an intermediate class slips silently. AC-4's docstring test passed for `"""TODO"""`. No AC enforced the "no `__init__`, no class attributes" doctrine that the implementer notes correctly call out. Hardened AC-3 to `__mro__[1]` checks; tightened AC-4 to require ≥ 10 chars + raise-site slug mention (mirroring Phase 0 S2-01 AC-1); added AC-8 (markers-only) and AC-9 (root docstring) — together the mutation set "rebase under Exception," "insert intermediate class," "smuggle constructor signature," "blank-docstring trick" all fail loudly.
3. **`__all__` closure asymmetry.** The original closure-equality test excluded `CodegenieEvalError` from the set, so a PR dropping the root from `__all__` would not fail. Strengthened to `set(e.__all__) == EXPECTED_SUBCLASSES | {"CodegenieEvalError"}`.

One consistency conflict surfaced: `final-design.md` line 63 calls this an "EvalError hierarchy **under** `CodegenieError`," but `phase-arch-design.md` + this story + the executor's import-linter target make it a **sibling** hierarchy. Consistency-critic priority (source-of-truth wins) cuts in favor of the story — the elaborated reasoning supersedes the brief final-design.md mention — but the inconsistency itself is real. Flagged in the story's Out-of-scope + Notes and recommended for a doc-sweep PR; no auto-fix from this validator pass.

Design-pattern review: the story correctly avoids premature abstraction (no `ExceptionRegistry`, no factory). The marker pattern + bounded-context discipline is the right shape. The one design opportunity worth surfacing is that the raise-site slug catalog should live as a `Final[frozenset[str]]` at test-module scope so new errors in future stories are extension-by-addition (one catalog entry + one docstring), not test-body edits. Added to the TDD plan and the implementer notes.

Three blocks, six hardens, two nits applied. No `NEEDS RESEARCH` findings — every pattern is precedented in Phase 0 S2-01.

## Findings by critic

### Coverage critic

#### F-COV-1: AC-4 does not pin the docstring's raise-site content
- **Severity:** block
- **Type:** unverifiable AC
- **Where:** AC-4
- **Why it matters:** AC-4 said "naming the module that raises it" but the red test only asserted `cls.__doc__ is not None and stripped != ""`. A docstring of `"""TODO"""` would pass CI yet violate the contract. Phase 0 S2-01 hit the same gap (F-COV-1 there) and resolved it by enforcing a slug catalog — mirror that.
- **Proposed fix:** Tighten AC-4 to require ≥ 10 chars + lowercased docstring contains one of `{loader, registry, audit, promotion}`. Promote the slug catalog to a module-level `Final[frozenset[str]]` in the test for extension-by-addition.
- **Resolution:** Applied — AC-4 rewritten; red test uses `RAISE_SITE_SLUGS` catalog.

#### F-COV-2: No AC pins the marker-only discipline
- **Severity:** harden
- **Type:** missing AC
- **Where:** missing
- **Why it matters:** Implementer notes say "no `__init__`, no `__str__`, no behavior" but nothing in the ACs or red test enforces this. A subclass smuggling `def __init__(self, *args, severity: str = "block"):` passes today. ADR-0004 makes the rubric-emitted failure surface `FailureMode`, not `Exception` — the markers must stay markers.
- **Proposed fix:** Add AC-8 pinning `cls.__init__ is e.CodegenieEvalError.__init__` and `cls.__dict__.keys() ⊆ {marker keys + Python-3.13-compiler-injected}`.
- **Resolution:** Applied as AC-8; widened dict-key allowance per Phase 0 `_lessons.md` for Python 3.13.

#### F-COV-3: No AC pins the sibling-not-child relationship
- **Severity:** block
- **Type:** missing AC for stated invariant
- **Where:** missing (was prose only in Notes for implementer)
- **Why it matters:** The story's most important design decision — `CodegenieEvalError` sibling of `codegenie.errors.CodegenieError` — lives only in prose. A future "tidy-up" PR could rebase under `CodegenieError` and silently invalidate the import-linter contract S1-05 will extend. Phase 0's hierarchy and the eval hierarchy serving distinct bounded contexts is a load-bearing architectural choice; "load-bearing prose" is not a contract.
- **Proposed fix:** Add AC-7 pinning both directions: `not issubclass(CodegenieEvalError, CodegenieError)` and `not issubclass(CodegenieError, CodegenieEvalError)` and `CodegenieEvalError is not CodegenieError`.
- **Resolution:** Applied as AC-7; red test `test_codegenie_eval_error_is_sibling_of_codegenie_error_not_child` makes the mutation it guards against explicit.

#### F-COV-4: AC-3 inheritance check is transitive, not direct
- **Severity:** block
- **Type:** weak AC
- **Where:** AC-3
- **Why it matters:** `issubclass(cls, CodegenieEvalError)` is satisfied for any depth of inheritance chain. A future PR inserting `class _LoaderErrors(CodegenieEvalError): pass` and reparenting the loader-side subclasses under it would silently pass. The arch design says "direct subclass," but the test didn't enforce direct.
- **Proposed fix:** Tighten to `cls.__mro__[1] is e.CodegenieEvalError` plus root-side `e.CodegenieEvalError.__mro__[1] is Exception`.
- **Resolution:** Applied — AC-3 rewritten; red test uses `__mro__[1]` checks.

#### F-COV-5: `__init__.py` non-re-export commitment lived only in prose
- **Severity:** nit
- **Type:** missing scope check
- **Where:** Out-of-scope / Implementation outline
- **Why it matters:** Notes for implementer said "do not import this module from `codegenie.eval/__init__.py`" but Out-of-scope did not surface it as a deflection. S1-05 owns the public-name closure; preempting it here would break that contract.
- **Proposed fix:** Promote to Out-of-scope explicitly; reinforce in Implementation outline step 1.
- **Resolution:** Applied — Out-of-scope first bullet expanded; Implementation outline step 1 says "must not `from .errors import *`."

### Test-Quality critic

#### F-TQ-1: `__all__` closure equality excludes the root from the comparison set
- **Severity:** harden
- **Type:** thin test
- **Mutation that slips:** `__all__ = ["TaskClassNotFound", ..., "TierConfigInvalid"]` (root dropped) — the existing test compares `public_names = {n for n in e.__all__ if n != "CodegenieEvalError"}` and would pass.
- **Proposed fix:** `assert set(e.__all__) == EXPECTED_SUBCLASSES | {"CodegenieEvalError"}`.
- **Resolution:** Applied as `test_all_closure_is_exact_in_both_directions`.

#### F-TQ-2: Docstring test asserts non-empty only — content unverified
- **Severity:** block
- **Type:** tautological test
- **Mutation that slips:** Set every subclass's docstring to `"x"`; test passes. Then a future reader has no idea which module raises which subclass. Phase 0 S2-01 found the same and fixed it with a slug-mention test.
- **Proposed fix:** Require ≥ 10 chars + lowercased content contains one of `{loader, registry, audit, promotion}`.
- **Resolution:** Applied as `test_every_subclass_docstring_names_a_documented_raise_site`.

#### F-TQ-3: Root `CodegenieEvalError` docstring not checked
- **Severity:** harden
- **Type:** missing test
- **Mutation that slips:** Remove root docstring; the per-subclass loop excludes the root so no test catches it. The Implementation outline mentions a module-level docstring but no test pins the **class** docstring on `CodegenieEvalError`.
- **Proposed fix:** Add AC-9 + `test_root_has_non_empty_docstring`.
- **Resolution:** Applied.

#### F-TQ-5: Direct-inheritance check missing (intermediate-class smuggling)
- **Severity:** block (dup with F-COV-4)
- **Type:** weak test
- **Mutation that slips:** Insert `class _Base(CodegenieEvalError): pass; class TaskClassNotFound(_Base): pass`. `issubclass(..., CodegenieEvalError)` is `True`; the test passes; the "direct subclass" contract from AC-3 silently violated.
- **Proposed fix:** Use `cls.__mro__[1] is e.CodegenieEvalError`.
- **Resolution:** Applied as `test_every_subclass_inherits_directly_from_codegenie_eval_error`.

#### F-TQ-6: Markers-only test missing (smuggled constructor / class attrs)
- **Severity:** harden (dup with F-COV-2)
- **Type:** missing test
- **Mutation that slips:** `class TaskClassAlreadyRegistered(CodegenieEvalError): def __init__(self, *args, **kw): super().__init__(*args)` — passes today because no test inspects `cls.__init__` or `cls.__dict__`. Behavior-free claim becomes prose-only.
- **Proposed fix:** Pin `cls.__init__ is CodegenieEvalError.__init__` and `cls.__dict__.keys() ⊆ marker-keys ∪ Python-3.13-compiler-injected`.
- **Resolution:** Applied as `test_every_subclass_is_marker_only`; explicit comment cites Phase 0 `_lessons.md` for the 3.13 widening.

#### F-TQ-7: Sibling relationship test missing
- **Severity:** block (dup with F-COV-3)
- **Type:** missing test for stated invariant
- **Mutation that slips:** `class CodegenieEvalError(CodegenieError): ...` — the existing tests would all pass, AC-3 (`__mro__[1] is Exception`) would actually fail under this mutation in the new hardened form, but a more subtle mutation `class CodegenieEvalError(SomeBoundedError): pass` where `SomeBoundedError(CodegenieError)` could still bridge the namespaces. Belt and braces: pin both directions explicitly.
- **Proposed fix:** `test_codegenie_eval_error_is_sibling_of_codegenie_error_not_child` covers both `not issubclass(..., ...)` directions plus `is not` identity.
- **Resolution:** Applied.

### Consistency critic

#### F-CON-1: `final-design.md` line 63 says "EvalError hierarchy under CodegenieError"
- **Severity:** harden (surfaced; not auto-fixed)
- **Type:** doc contradiction
- **Where:** `../final-design.md:63` vs `../phase-arch-design.md` + story + implementer notes
- **Why it matters:** `final-design.md` reads as if the hierarchy were a child of Phase 0's `CodegenieError`. The story makes them siblings. Consistency-critic priority: source-of-truth wins, and the story's reasoning (preserves import-linter contract, bounded-context boundary) is concrete and elaborated; the final-design.md mention is one line. Story wins; final-design.md is the one to update — but that is out of scope for the validator.
- **Proposed fix:** Surface in story Notes for implementer + Out-of-scope; flag for a doc-sweep PR. Do not auto-fix `final-design.md`.
- **Resolution:** Applied — Notes for implementer last bullet + Out-of-scope last bullet name the conflict and the resolution.

#### F-CON-2: AC-3 "direct subclass" wording but `issubclass` test (already-covered)
- **Severity:** block (dup with F-COV-4 / F-TQ-5)
- **Where:** AC-3 / TDD red sample
- **Why it matters:** The AC text said "direct," the test did not. Consistency-internal: AC and test must align.
- **Resolution:** AC-3 rewritten; test uses `__mro__[1]`.

#### F-CON-3: ADR-0004 boundary preserved (no auto-fix needed)
- **Severity:** info
- **Where:** Out-of-scope
- **Verdict:** Aligned. The story's Out-of-scope correctly defers `FailureMode` to S1-02 and `BenchScoreInvalid` to S3-04 per ADR-0004's "rubric subprocess failure surface is `FailureMode`, not Exception."

### Design-Patterns critic

#### F-DP-1: Marker-pattern + sibling-hierarchy is the right shape (no edit)
- **Severity:** info
- **Verdict:** The story correctly avoids `ExceptionRegistry`, factory, or marker-decorator. Rule of three (one consumer family) is not met; premature abstraction would violate Rule 2. The marker pattern + bounded-context discipline is the canonical choice for this surface.

#### F-DP-2: Surface the bounded-context decision explicitly in Notes
- **Severity:** harden
- **Type:** unsurfaced design rationale
- **Where:** Notes for implementer
- **Why it matters:** The sibling-not-child decision is the load-bearing design choice. It deserves an explicit name (bounded context / package boundary) so the executor (and future readers) understand *why* the validator added AC-7. Naming the pattern also signals that future packages with similar isolation needs should follow the same template — `codegenie.eval.errors.CodegenieEvalError` is a precedent.
- **Proposed fix:** Rewrite the third Notes bullet to name "bounded-context discipline," cite hexagonal / DIP framing, name the mutation AC-7 guards against, name the downstream payoff (distribution package lift-out).
- **Resolution:** Applied — third Notes bullet rewritten with explicit pattern naming and rationale.

#### F-DP-3: Catalog-driven slug list for extension-by-addition
- **Severity:** nit
- **Type:** extensibility seam
- **Where:** TDD plan
- **Why it matters:** Adding a new error in a later story (e.g., `cache.*` or `runner.*`) should be one catalog entry + one matching docstring, not a test-body edit. Mirrors the data-driven-registry pattern used elsewhere in the codebase (`_GENERATOR_HEADER_MARKERS`, `_LOCKFILE_PRECEDENCE`).
- **Proposed fix:** Promote `RAISE_SITE_SLUGS` to a module-level `Final[frozenset[str]]` in the test; mention the discipline in Notes for implementer.
- **Resolution:** Applied — `RAISE_SITE_SLUGS` is `Final[frozenset[str]]` at module scope; fourth Notes bullet names the catalog discipline.

#### F-DP-4: No premature abstraction (no edit)
- **Severity:** info
- **Verdict:** The story does not introduce an `ErrorRegistry`, `@error_marker` decorator, or a base-class metaclass. Rule of three not met. Correct call. Validator explicitly endorses the no-abstraction posture in Notes for implementer (fourth-from-last bullet, added during synthesis).

## Conflict resolution

| Conflict | Resolution |
|---|---|
| `final-design.md` says "under `CodegenieError`"; story says sibling | Consistency-critic priority: source-of-truth (more elaborated, more recent, more justified) wins. Story stands; `final-design.md` flagged for doc-sweep. No auto-edit of `final-design.md`. |
| No conflicts between critics — all four agreed on direction. | — |

## Edits applied

Story file edited in place. New `Validation notes` block under the story header. ACs renumbered (was 6 unnumbered; now 9 explicit AC-N). Implementation outline, Green/Refactor, Out-of-scope, Notes for implementer all touched in line with the new ACs.

Pre/post diff summary:

| Section | Before | After |
|---|---|---|
| Status | `Ready` | `HARDENED` |
| ACs | 6 unnumbered | 9 explicit (AC-1..AC-9) |
| Red test count | 3 tests | 7 tests (closure, root-direct-Exception, subclass-direct-root, sibling, root-docstring, slug-docstring, markers-only) |
| Out-of-scope items | 4 bullets | 5 bullets (added: inheritance under `CodegenieError`) |
| Notes for implementer | 6 bullets | 8 bullets (added: bounded-context, rule-of-three, catalog discipline, final-design.md conflict callout) |

## Verdict

**HARDENED.** Three blocks (F-COV-1, F-COV-3, F-COV-4 / F-TQ-2, F-TQ-5, F-TQ-7), six hardens (F-COV-2, F-TQ-1, F-TQ-3, F-TQ-6, F-CON-1, F-DP-2), two nits (F-COV-5, F-DP-3) applied. The story is now ready for `phase-story-executor`. Every AC is individually verifiable; the AC set collectively guarantees the goal (behavior-free typed-error contract, marker discipline, bounded-context boundary). The mutation set the test suite resists: aliasing-collapse, intermediate-class insertion, root-rebase under `CodegenieError`, smuggled constructor signature, blank-docstring trick, dropped-from-`__all__`. The bounded-context discipline is surfaced as a load-bearing design pattern with explicit pattern naming; future sibling error hierarchies in other packages should follow this template.
